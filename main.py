import hashlib
import json
import logging
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from html import escape
from urllib.parse import urljoin

import bleach
import feedparser
import markdown
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from anime_api.apis import NekosAPI  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - dependencia opcional
    NekosAPI = None

load_dotenv()

# Configuracion de logging estructurado.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Configuracion principal del sitio.
HISTORIAL_FILE = "noticias.json"
INDICE_FILE = "noticias_index.json"
CARPETA_NOTICIAS = "noticias"
ARCHIVO_SITEMAP = "sitemap.xml"
ARCHIVO_ROBOTS = "robots.txt"
LIMITE_INDEX = 30
NOTICIAS_POR_FEED = 5
GEMINI_MIN_INTERVAL_SECONDS = 12
GEMINI_LAST_REQUEST_TS = 0.0
IMAGEN_PLACEHOLDER = "https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=800&auto=format&fit=crop"
IMAGENES_TEMATICAS = {
    'anime': 'https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=800&auto=format&fit=crop',
    'mecha': 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=800&auto=format&fit=crop',
    'manga': 'https://images.unsplash.com/photo-1613376023733-0a73315d9b06?q=80&w=800&auto=format&fit=crop',
    'peliculas': 'https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=800&auto=format&fit=crop',
    'industria': 'https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=800&auto=format&fit=crop',
}
MAPA_CATEGORIAS = {
    'PELICULAS': 'PELÍCULAS', 'PELÍCULAS': 'PELÍCULAS',
    'SHONEN': 'SHONEN', 'SEINEN': 'SEINEN', 'MANGA': 'MANGA',
    'ESTRENOS': 'ESTRENOS', 'INDUSTRIA': 'INDUSTRIA',
}
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
TAGS_PERMITIDOS = ['p', 'h2', 'h3', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'blockquote', 'br']
ATRIBUTOS_PERMITIDOS = {'a': ['href', 'title', 'rel']}


def cargar_configuracion():
    """Carga los valores auxiliares del proyecto sin permitir que cambien el dominio canonico."""
    ruta_config = "config.json"
    if os.path.exists(ruta_config):
        with open(ruta_config, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    return {}


CONFIG = cargar_configuracion()
DOMINIO_BASE = CONFIG.get("dominio_base", "https://carlitospadilla-png.github.io/mi-red-noticias/")
IMAGEN_PLACEHOLDER = CONFIG.get("imagen_placeholder", IMAGEN_PLACEHOLDER)
IMAGEN_ANIME_FALLBACK = IMAGENES_TEMATICAS['anime']


def cargar_json(ruta, valor_por_defecto):
    """Lee un JSON y devuelve un valor seguro si el archivo no existe o esta dañado."""
    if not os.path.exists(ruta):
        return valor_por_defecto
    with open(ruta, "r", encoding="utf-8") as archivo:
        try:
            return json.load(archivo)
        except json.JSONDecodeError:
            logging.warning("No se pudo leer %s; se usara un valor vacio.", ruta)
            return valor_por_defecto


def guardar_json(ruta, datos):
    """Guarda JSON con formato legible y caracteres Unicode intactos."""
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)


def cargar_noticias_db():
    """Carga el historial que se usa para no reprocesar URLs RSS repetidas."""
    return cargar_json(HISTORIAL_FILE, [])


def guardar_noticias_db(noticias):
    """Guarda el historial respetando el limite configurado."""
    limite = CONFIG.get("max_historial_registros", 200)
    guardar_json(HISTORIAL_FILE, noticias[:limite])


def slugify(texto):
    """Genera un slug ASCII estable para filenames y URLs nuevas."""
    texto = unicodedata.normalize('NFKD', str(texto).lower()).encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^\w\s-]', '', texto)
    texto = re.sub(r'[\s_-]+', '-', texto)
    return texto.strip('-') or 'noticia-anime'


def normalizar_fecha(fecha):
    """Conserva fechas historicas y completa a medianoche las fechas antiguas sin hora."""
    fecha = str(fecha or "")
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha):
        return f"{fecha}T00:00:00"
    return fecha or datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def calcular_tiempo_lectura(contenido_markdown):
    """Calcula minutos de lectura aproximados a partir de unas 200 palabras por minuto."""
    palabras = re.findall(r"\b\w+\b", str(contenido_markdown or ''), flags=re.UNICODE)
    minutos = max(1, (len(palabras) + 199) // 200)
    return f"Lectura de {minutos} min"


def extraer_imagen_rss(entry):
    """Extrae una imagen real del RSS, respetando el orden de prioridad pedido."""
    # 1. Campos multimedia estandar del feed.
    for campo in ('media_content', 'media_thumbnail'):
        elementos = entry.get(campo, []) or []
        for elemento in elementos:
            url_imagen = elemento.get('url') or elemento.get('href')
            if url_imagen:
                return url_imagen

    # 2. Enclosures, habituales en algunos RSS.
    for enclosure in entry.get('enclosures', []) or []:
        tipo = enclosure.get('type', '')
        url_enclosure = enclosure.get('href') or enclosure.get('url')
        if (tipo.startswith('image') or not tipo) and url_enclosure:
            return url_enclosure

    # 3. Imagen incluida en summary, description o content.
    bloques = [entry.get('summary', '') or entry.get('description', '')]
    for contenido in entry.get('content', []) or []:
        bloques.append(contenido.get('value', ''))
    for bloque in bloques:
        if bloque:
            imagen = BeautifulSoup(bloque, 'html.parser').find('img')
            if imagen and imagen.get('src'):
                return imagen['src']

    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _consultar_pexels_por_keyword(keyword):
    """Consulta la API de Pexels para una palabra clave concreta con reintentos limitados."""
    api_key = str(PEXELS_API_KEY or "")
    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": keyword, "per_page": 5, "orientation": "landscape"},
        timeout=10,
    )
    if response.status_code != 200:
        raise requests.HTTPError(f"status HTTP {response.status_code} desde Pexels para '{keyword}'")

    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError(f"respuesta JSON invalida para '{keyword}'") from error

    photos = payload.get('photos') or []
    if not photos:
        return None

    imagen = photos[0].get('src', {})
    return imagen.get('large') or imagen.get('medium') or IMAGEN_PLACEHOLDER


def normalizar_url_anime(respuesta):
    """Normaliza posibles respuestas de NekosAPI a una URL valida."""
    if respuesta is None:
        return None
    if isinstance(respuesta, str):
        return respuesta.strip() or None
    url_atributo = getattr(respuesta, 'url', None)
    if url_atributo:
        return str(url_atributo).strip() or None
    if isinstance(respuesta, dict):
        for clave in ('url', 'image', 'image_url', 'src', 'link'):
            valor = respuesta.get(clave)
            if valor:
                return str(valor).strip()
        for valor in respuesta.values():
            url = normalizar_url_anime(valor)
            if url:
                return url
    if isinstance(respuesta, (list, tuple)):
        for item in respuesta:
            url = normalizar_url_anime(item)
            if url:
                return url
    return None


def obtener_imagen_anime_pura():
    """Intenta traer una imagen anime pura usando NekosAPI; si no existe, devuelve None."""
    if NekosAPI is None:
        return None

    try:
        nekos = NekosAPI()
        respuesta = nekos.get_random_image()
        imagen_url = normalizar_url_anime(respuesta)
        if imagen_url:
            logging.info("Imagen anime desde NekosAPI: %s", imagen_url)
            return imagen_url
        logging.warning("NekosAPI devolvio una respuesta sin URL valida.")
    except Exception as error:
        logging.warning("Fallo de NekosAPI; se usara fallback: %s", error)

    return None


def buscar_imagen_pexels(imagen_keywords=None):
    """Devuelve una imagen puramente anime con NekosAPI y cae a placeholder si no funciona."""
    imagen_url = obtener_imagen_anime_pura()
    if imagen_url:
        return imagen_url

    if PEXELS_API_KEY:
        keywords = [str(imagen_keywords or 'anime').strip() or 'anime']
        if keywords[0].lower() != 'anime':
            keywords.append('anime')

        for keyword in keywords:
            try:
                imagen_url = _consultar_pexels_por_keyword(keyword)
                if imagen_url:
                    logging.info("Imagen desde Pexels para '%s': %s", keyword, imagen_url)
                    return imagen_url
                logging.warning("Pexels no devolvio resultados para '%s'.", keyword)
            except (requests.Timeout, requests.RequestException, ValueError, TypeError) as error:
                logging.warning("Fallo de red o respuesta invalida en Pexels para '%s': %s", keyword, error)
            except Exception as error:
                logging.warning("Error inesperado consultando Pexels para '%s': %s", keyword, error)

    logging.warning("Se usara el fallback visual anime porque no hubo una fuente remota valida.")
    return IMAGEN_ANIME_FALLBACK


def extraer_fecha_entry(entry):
    """Obtiene la fecha real de publicacion del RSS o usa el instante de procesamiento como fallback."""
    if getattr(entry, 'published_parsed', None):
        fecha_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
    else:
        fecha_dt = datetime.now()
    return fecha_dt.strftime('%Y-%m-%dT%H:%M:%S'), fecha_dt.strftime('%d/%m/%Y')


def esperar_cupo_gemini():
    """Evita saturar Gemini forzando un intervalo mínimo entre llamadas."""
    global GEMINI_LAST_REQUEST_TS
    ahora = time.monotonic()
    diferencia = ahora - GEMINI_LAST_REQUEST_TS
    if diferencia < GEMINI_MIN_INTERVAL_SECONDS:
        espera = GEMINI_MIN_INTERVAL_SECONDS - diferencia
        logging.info("Esperando %.1f s antes de otra petición a Gemini para evitar rate limit.", espera)
        time.sleep(espera)
    GEMINI_LAST_REQUEST_TS = time.monotonic()


def contenido_fallback_seo(titulo, descripcion):
    """Genera un contenido seguro cuando Gemini falla por cuota o servicio saturado."""
    titulo_limpio = str(titulo or 'Noticia de anime').strip() or 'Noticia de anime'
    descripcion_limpia = str(descripcion or 'Noticias del mundo del anime y manga.').strip() or 'Noticias del mundo del anime y manga.'
    meta = descripcion_limpia[:150].strip()
    contenido = f"""## {titulo_limpio}

{descripcion_limpia}

### Lo más destacado
- Anime y manga en el centro de la actualidad.
- Noticias relevantes para la comunidad otaku.
- Actualización rápida y clara del tema.

### En resumen
La industria del anime y manga sigue creciendo con nuevos lanzamientos, estrenos y novedades que mantienen a la comunidad muy activa.
"""
    return {
        'titulo_seo': titulo_limpio,
        'categoria': 'INDUSTRIA',
        'meta_descripcion': meta,
        'contenido_markdown': contenido,
        'imagen_keywords': 'anime manga',
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def llamar_gemini_con_reintento(cliente, prompt):
    """Realiza la llamada a Gemini y deja que tenacity gestione los reintentos."""
    esperar_cupo_gemini()
    respuesta = cliente.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    texto = getattr(respuesta, 'text', '') or ''
    if not texto:
        raise ValueError("Gemini devolvio una respuesta vacia")
    datos = json.loads(texto)
    if not isinstance(datos, dict):
        raise ValueError("Gemini no devolvio un objeto JSON")
    return datos


def reescribir_con_gemini(cliente, titulo, descripcion):
    """Pide a Gemini contenido SEO y usa fallback solo tras agotar los reintentos."""
    prompt = f"""
    Reescribe esta noticia de ANIME/MANGA en español con tono entretenido y optimizado para SEO.

    Titulo original: {titulo}
    Descripcion original: {descripcion}

    Responde UNICAMENTE JSON con esta estructura exacta:
    {{
      "titulo_seo": "Titulo descriptivo y atractivo",
      "categoria": "SHONEN, SEINEN, MANGA, PELICULAS, ESTRENOS o INDUSTRIA",
      "meta_descripcion": "Resumen conciso de 150 caracteres",
      "contenido_markdown": "Cuerpo completo en Markdown con ##, negritas y listas cuando corresponda",
      "imagen_keywords": "2 o 3 palabras clave en ingles sobre el tema visual"
    }}
    """
    try:
        return llamar_gemini_con_reintento(cliente, prompt)
    except Exception as error:
        logging.error("Gemini fallo tras varios reintentos para '%s'; usando contenido fallback. Motivo: %s", titulo or 'noticia', error)
        time.sleep(10)
        return contenido_fallback_seo(titulo, descripcion)


def escapar_datos_noticia(datos_noticia):
    """Prepara valores seguros para insertar en HTML sin modificar el contenido persistido."""
    return {
        'titulo_seo': escape(str(datos_noticia.get('titulo_seo') or 'Noticia de anime'), quote=True),
        'meta_descripcion': escape(str(datos_noticia.get('meta_descripcion') or ''), quote=True),
        'imagen_url': escape(str(datos_noticia.get('imagen_url') or IMAGEN_ANIME_FALLBACK), quote=True),
        'url_original': escape(str(datos_noticia.get('url_original') or datos_noticia.get('link_original') or ''), quote=True),
        'categoria': escape(str(datos_noticia.get('categoria') or 'ANIME'), quote=True),
        'fecha_iso': escape(normalizar_fecha(datos_noticia.get('fecha_iso')), quote=True),
        'fecha_formateada': escape(str(datos_noticia.get('fecha_formateada') or ''), quote=True),
        'tiempo_lectura': escape(str(datos_noticia.get('tiempo_lectura') or 'Lectura de 1 min'), quote=True),
    }


def generar_html_noticia(datos_noticia, filename):
    """Genera el HTML individual con metadatos SEO, contenido Markdown y JavaScript inline."""
    contenido_html = markdown.markdown(str(datos_noticia.get('contenido_markdown') or ''))
    contenido_html = bleach.clean(
        contenido_html,
        tags=TAGS_PERMITIDOS,
        attributes=ATRIBUTOS_PERMITIDOS,
        strip=True
    )
    datos_noticia['contenido_html'] = contenido_html
    seguros = escapar_datos_noticia(datos_noticia)
    url_completa = urljoin(DOMINIO_BASE, f"{CARPETA_NOTICIAS}/{filename}")
    url_completa_html = escape(url_completa, quote=True)
    schema_org = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": datos_noticia.get('titulo_seo') or 'Noticia de anime',
        "image": [datos_noticia.get('imagen_url') or IMAGEN_ANIME_FALLBACK],
        "datePublished": normalizar_fecha(datos_noticia.get('fecha_iso')),
        "description": datos_noticia.get('meta_descripcion') or '',
    }
    schema_json = json.dumps(schema_org, ensure_ascii=False).replace('</', '<\\/')

    html_content = f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{seguros['titulo_seo']} - AnimePulse</title>
    <meta name="description" content="{seguros['meta_descripcion']}">
    <link rel="canonical" href="{url_completa_html}">
    <link rel="icon" href="/favicon.ico">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{seguros['titulo_seo']}">
    <meta property="og:description" content="{seguros['meta_descripcion']}">
    <meta property="og:image" content="{seguros['imagen_url']}">
    <meta property="og:url" content="{url_completa_html}">
    <meta property="og:site_name" content="AnimePulse">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{seguros['titulo_seo']}">
    <meta name="twitter:description" content="{seguros['meta_descripcion']}">
    <meta name="twitter:image" content="{seguros['imagen_url']}">
    <script type="application/ld+json">{schema_json}</script>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-200 font-sans min-h-screen flex flex-col antialiased">
    <div id="progress-bar" class="fixed top-0 left-0 h-1 bg-purple-600 z-50 transition-all duration-150" style="width: 0%"></div>
    <header class="bg-slate-900 border-b border-slate-800 p-4 sticky top-0 z-40">
        <div class="max-w-4xl mx-auto flex justify-between items-center">
            <a href="../index.html" class="text-2xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">ANIME<span class="text-white">PULSE</span></a>
            <a href="../index.html" class="text-xs font-bold text-slate-400 hover:text-white transition-colors">← Volver al inicio</a>
        </div>
    </header>
    <main class="max-w-3xl mx-auto my-10 px-4 flex-grow">
        <article>
            <span class="bg-purple-600/90 text-white px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">{seguros['categoria']}</span>
            <h1 class="text-3xl md:text-4xl font-black text-white mt-4 mb-2">{seguros['titulo_seo']}</h1>
            <p class="text-xs text-slate-400 mb-6"><time datetime="{seguros['fecha_iso']}">{seguros['fecha_formateada']}</time> • {seguros['tiempo_lectura']}</p>
            <div class="rounded-xl overflow-hidden mb-8 border border-slate-800"><img src="{seguros['imagen_url']}" alt="{seguros['titulo_seo']}" class="w-full h-auto object-cover" loading="lazy"></div>
            <div class="my-6 p-4 bg-slate-900/50 border border-slate-800/80 rounded-lg text-center text-xs text-slate-500"><!-- Banner Publicitario Superior --></div>
            <div class="prose prose-invert max-w-none text-slate-300 space-y-4 leading-relaxed">{contenido_html}</div>
            <div class="mt-8 p-4 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-400">Fuente original: <a href="{seguros['url_original']}" target="_blank" rel="noopener noreferrer" class="text-purple-400 hover:underline">Ver artículo original</a></div>
            <div class="mt-10 pt-6 border-t border-slate-800 flex justify-between items-center">
                <button onclick="copiarEnlace()" class="bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold py-2 px-4 rounded-lg transition-colors"><span id="copy-text">Copiar Enlace</span></button>
                <a href="../index.html" class="bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold py-2 px-4 rounded-lg transition-all">Más Noticias</a>
            </div>
        </article>
    </main>
    <footer class="bg-slate-900 border-t border-slate-800 text-slate-400 text-center py-6 text-sm"><p>&copy; AnimePulse. Todos los derechos reservados.</p></footer>
    <script>
    window.onscroll = function() {{
        const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
        const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        document.getElementById("progress-bar").style.width = (height ? (winScroll / height) * 100 : 0) + "%";
    }};
    function copiarEnlace() {{
        navigator.clipboard.writeText(window.location.href);
        const copyText = document.getElementById("copy-text");
        copyText.innerText = "¡Copiado!";
        setTimeout(() => {{ copyText.innerText = "Copiar Enlace"; }}, 2000);
    }}
    </script>
</body>
</html>"""
    os.makedirs(CARPETA_NOTICIAS, exist_ok=True)
    with open(os.path.join(CARPETA_NOTICIAS, filename), "w", encoding="utf-8") as archivo:
        archivo.write(html_content)


def construir_registro_indice(noticia, existente=None):
    """Convierte una noticia del historial al formato publico persistente del indice."""
    existente = existente or {}
    contenido = noticia.get('contenido_markdown', '')
    fecha_iso = normalizar_fecha(noticia.get('fecha_iso') or existente.get('fecha_iso'))
    return {
        'filename': noticia.get('filename') or existente.get('filename', ''),
        'titulo_seo': noticia.get('titulo_seo') or existente.get('titulo_seo', 'Noticia de anime'),
        'categoria': (noticia.get('categoria') or existente.get('categoria') or 'ANIME').upper(),
        'meta_descripcion': noticia.get('meta_descripcion') or existente.get('meta_descripcion', ''),
        'imagen_url': noticia.get('imagen_url') or existente.get('imagen_url') or IMAGEN_PLACEHOLDER,
        'fecha_iso': fecha_iso,
        'fecha_formateada': noticia.get('fecha_formateada') or existente.get('fecha_formateada') or datetime.fromisoformat(fecha_iso).strftime('%d/%m/%Y'),
        'tiempo_lectura': noticia.get('tiempo_lectura') or existente.get('tiempo_lectura') or calcular_tiempo_lectura(contenido),
        'link_original': noticia.get('url_original') or noticia.get('link_original') or existente.get('link_original', ''),
    }


def sincronizar_indice(noticias):
    """Crea o actualiza noticias_index.json sin perder metadatos ya publicados."""
    indice_anterior = cargar_json(INDICE_FILE, [])
    anteriores = {item.get('link_original', ''): item for item in indice_anterior}
    indice = [construir_registro_indice(noticia, anteriores.get(noticia.get('url_original', ''))) for noticia in noticias]
    indice = [item for item in indice if item.get('filename')]
    indice.sort(key=lambda item: item.get('fecha_iso', ''), reverse=True)
    guardar_json(INDICE_FILE, indice)
    return indice


def actualizar_index():
    """Regenera el indice desde noticias_index.json y muestra como maximo 30 tarjetas."""
    noticias = sorted(cargar_json(INDICE_FILE, []), key=lambda item: item.get('fecha_iso', ''), reverse=True)[:LIMITE_INDEX]
    tarjetas_html = ""
    for item in noticias:
        seguros = escapar_datos_noticia({**item, 'url_original': item.get('link_original', '')})
        url_noticia = escape(f"{CARPETA_NOTICIAS}/{item['filename']}", quote=True)
        tiempo = escape(item.get('tiempo_lectura', 'Lectura de 1 min'), quote=True)
        tarjetas_html += f"""
        <article class="noticia-card bg-slate-900 rounded-xl overflow-hidden border border-slate-800 hover:border-purple-500/50 transition-all duration-300 hover:-translate-y-1 flex flex-col justify-between" data-categoria="{seguros['categoria']}">
            <div><div class="h-48 overflow-hidden relative border-b border-slate-800"><img src="{seguros['imagen_url']}" alt="{seguros['titulo_seo']}" loading="lazy" class="w-full h-full object-cover"><span class="absolute top-3 left-3 bg-purple-600/90 text-white px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">{seguros['categoria']}</span></div>
            <div class="p-5"><span class="text-xs text-slate-400 block mb-2">{seguros['fecha_formateada']} • {tiempo}</span><h2 class="text-lg font-bold text-white mb-2 line-clamp-2 hover:text-purple-400 transition-colors"><a href="{url_noticia}" class="titulo-noticia">{seguros['titulo_seo']}</a></h2><p class="descripcion-noticia text-xs text-slate-400 line-clamp-2">{seguros['meta_descripcion']}</p></div></div>
            <div class="px-5 pb-5 pt-0 mt-auto"><a href="{url_noticia}" class="text-xs font-bold text-purple-400 hover:text-purple-300 inline-flex items-center gap-1">Leer artículo →</a></div>
        </article>
        """

    dominio_html = escape(DOMINIO_BASE, quote=True)
    placeholder_html = escape(IMAGEN_PLACEHOLDER, quote=True)
    index_html = f"""<!DOCTYPE html>
<html lang="es" class="dark"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>AnimePulse - Noticias de Anime & Manga al Instante</title><meta name="description" content="Tu portal con las últimas novedades, estrenos y tendencias del mundo del anime y manga."><link rel="canonical" href="{dominio_html}"><link rel="icon" href="/favicon.ico"><meta property="og:type" content="website"><meta property="og:title" content="AnimePulse - Noticias de Anime & Manga al Instante"><meta property="og:description" content="Últimas novedades, estrenos y tendencias del mundo del anime y manga."><meta property="og:url" content="{dominio_html}"><meta property="og:site_name" content="AnimePulse"><meta property="og:image" content="{placeholder_html}"><script src="https://cdn.tailwindcss.com"></script><script src="assets/main.js" defer></script><style>.oculta-busqueda, .oculta-categoria, .oculta-paginacion {{ display: none !important; }}</style></head>
<body class="bg-slate-950 text-slate-200 font-sans min-h-screen flex flex-col antialiased"><header class="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40"><div class="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row justify-between items-center gap-4"><a href="index.html" class="text-3xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">ANIME<span class="text-white">PULSE</span></a><div class="relative w-full sm:w-72"><input type="text" id="buscador" onkeyup="ejecutarFiltro()" placeholder="Buscar por título o descripción..." aria-label="Buscar noticias" class="w-full bg-slate-950 text-slate-200 text-sm pl-4 pr-4 py-2 rounded-lg border border-slate-800 focus:outline-none focus:ring-2 focus:ring-purple-500"></div></div></header>
<section class="bg-gradient-to-b from-purple-900/20 to-transparent border-b border-slate-800/50 py-10 px-4 text-center"><div class="max-w-4xl mx-auto"><h1 class="text-3xl md:text-5xl font-black text-white mb-3">Noticias de Anime & Manga</h1><p class="text-slate-400 text-sm md:text-base mb-6">Tu portal con las últimas novedades, estrenos y tendencias del mundo del anime y manga.</p><div class="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto"><button onclick="filtrarPorCategoria('TODAS')" data-categoria="TODAS" class="chip-categoria bg-purple-600 text-white text-xs font-bold px-3 py-1.5 rounded-full">TODAS</button><button onclick="filtrarPorCategoria('SHONEN')" data-categoria="SHONEN" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">SHONEN</button><button onclick="filtrarPorCategoria('SEINEN')" data-categoria="SEINEN" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">SEINEN</button><button onclick="filtrarPorCategoria('MANGA')" data-categoria="MANGA" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">MANGA</button><button onclick="filtrarPorCategoria('PELÍCULAS')" data-categoria="PELÍCULAS" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">PELÍCULAS</button><button onclick="filtrarPorCategoria('ESTRENOS')" data-categoria="ESTRENOS" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">ESTRENOS</button><button onclick="filtrarPorCategoria('INDUSTRIA')" data-categoria="INDUSTRIA" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full">INDUSTRIA</button></div></div></section>
<main class="max-w-6xl mx-auto my-10 px-4 flex-grow w-full"><div id="grid-noticias" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{tarjetas_html}</div><div id="no-resultados" class="hidden text-center py-16"><p class="text-slate-400 text-lg font-semibold" role="status">No se encontraron noticias que coincidan con la búsqueda.</p></div><div class="text-center mt-10"><button id="btn-cargar-mas" type="button" onclick="cargarMasNoticias()" class="bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 px-8 rounded-lg shadow-lg">Cargar más noticias</button></div></main><footer class="bg-slate-900 border-t border-slate-800 text-slate-400 text-center py-8 text-sm mt-auto"><p>&copy; {datetime.now().year} AnimePulse. Todos los derechos reservados.</p></footer></body></html>"""
    with open("index.html", "w", encoding="utf-8") as archivo:
        archivo.write(index_html)


def generar_sitemap():
    """Genera sitemap.xml desde noticias_index.json y conserva la fecha real de cada artículo."""
    indice = sorted(cargar_json(INDICE_FILE, []), key=lambda item: item.get('fecha_iso', ''), reverse=True)
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    nodo_inicio = ET.SubElement(urlset, "url")
    ET.SubElement(nodo_inicio, "loc").text = DOMINIO_BASE
    ET.SubElement(nodo_inicio, "lastmod").text = normalizar_fecha(indice[0].get('fecha_iso')) if indice else datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    for item in indice:
        nodo = ET.SubElement(urlset, "url")
        ET.SubElement(nodo, "loc").text = urljoin(DOMINIO_BASE, f"{CARPETA_NOTICIAS}/{item['filename']}")
        ET.SubElement(nodo, "lastmod").text = normalizar_fecha(item.get('fecha_iso'))
    arbol = ET.ElementTree(urlset)
    ET.indent(arbol, space="  ", level=0)
    arbol.write(ARCHIVO_SITEMAP, encoding="utf-8", xml_declaration=True)


def generar_robots():
    """Mantiene robots con el sitemap derivado del dominio canonico."""
    with open(ARCHIVO_ROBOTS, "w", encoding="utf-8") as archivo:
        archivo.write(f"User-agent: *\nAllow: /\n\nSitemap: {urljoin(DOMINIO_BASE, 'sitemap.xml')}\n")


def elegir_filename(titulo, link_original, filenames_existentes):
    """Evita colisiones añadiendo seis caracteres del hash del enlace original."""
    base = f"{slugify(titulo)}.html"
    if base not in filenames_existentes:
        return base
    sufijo = hashlib.md5(str(link_original).encode('utf-8')).hexdigest()[:6]
    return f"{slugify(titulo)}-{sufijo}.html"


def preparar_noticia(datos_ia, entry, filenames_existentes):
    """Combina RSS, fallback SEO y una imagen de anime pura lista para publicar."""
    url_original = entry.get('link', '')
    titulo = datos_ia.get('titulo_seo') or entry.get('title', 'Noticia de anime')
    imagen_url = buscar_imagen_pexels(datos_ia.get('imagen_keywords'))
    if imagen_url == IMAGEN_ANIME_FALLBACK:
        logging.warning("Fallback visual anime usado para '%s' porque no hubo una fuente remota valida.", titulo)
    else:
        logging.info("Imagen anime pura usada para '%s': %s", titulo, imagen_url)
    fecha_iso, fecha_formateada = extraer_fecha_entry(entry)
    contenido = datos_ia.get('contenido_markdown', '')
    categoria_normalizada = MAPA_CATEGORIAS.get((datos_ia.get('categoria') or 'ANIME').upper(), 'ANIME')
    return {
        'url_original': url_original,
        'filename': elegir_filename(titulo, url_original, filenames_existentes),
        'titulo_seo': titulo,
        'categoria': categoria_normalizada,
        'meta_descripcion': datos_ia.get('meta_descripcion') or '',
        'contenido_markdown': contenido,
        'imagen_keywords': datos_ia.get('imagen_keywords') or 'anime manga',
        'imagen_url': imagen_url,
        'fecha_iso': fecha_iso,
        'fecha_formateada': fecha_formateada,
        'tiempo_lectura': calcular_tiempo_lectura(contenido),
    }


def regenerar_publicaciones(noticias):
    """Regenera articulos existentes y todos los artefactos publicos desde los datos persistidos."""
    indice = sincronizar_indice(noticias)
    por_link = {item.get('link_original'): item for item in indice}
    for noticia in noticias:
        registro = construir_registro_indice(noticia, por_link.get(noticia.get('url_original')))
        generar_html_noticia({**noticia, **registro}, registro['filename'])
    actualizar_index()
    generar_sitemap()
    generar_robots()


def regenerar_publicaciones_existentes():
    """Reconstruye el sitio y sus metadatos usando el historial disponible."""
    noticias_db = cargar_noticias_db()
    regenerar_publicaciones(noticias_db)
    logging.info("Sitio regenerado desde %s: %s noticias existentes.", HISTORIAL_FILE, len(noticias_db))


def main():
    """Procesa RSS nuevos y regenera todas las salidas estaticas del sitio."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.warning("No se detecto GEMINI_API_KEY. Regenerando sitio con noticias existentes.")
        regenerar_publicaciones_existentes()
        return

    cliente = genai.Client(api_key=api_key)
    noticias_db = cargar_noticias_db()
    urls_procesadas = {item.get('url_original') for item in noticias_db}
    filenames_existentes = {item.get('filename') for item in noticias_db}
    procesadas_count = 0
    fallidas_count = 0

    logging.info("Iniciando escaneo de feeds RSS...")
    for feed_url in CONFIG.get("feeds_rss", []):
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            logging.warning("Feed con problemas (%s): %s", feed_url, feed.bozo_exception)
        for entry in feed.entries[:CONFIG.get("max_noticias_por_feed", NOTICIAS_POR_FEED)]:
            url_original = entry.get('link', '')
            if not url_original or url_original in urls_procesadas:
                continue
            logging.info("Procesando nueva noticia: %s", entry.get('title', 'sin titulo'))
            try:
                datos_ia = reescribir_con_gemini(cliente, entry.get('title', ''), entry.get('summary', ''))
                if datos_ia:
                    noticia = preparar_noticia(datos_ia, entry, filenames_existentes)
                    logging.info("Imagen seleccionada para '%s': %s", entry.get('title', ''), noticia['imagen_url'])
                    generar_html_noticia(noticia, noticia['filename'])
                    time.sleep(3)
                    noticias_db.append(noticia)
                    urls_procesadas.add(url_original)
                    filenames_existentes.add(noticia['filename'])
                    procesadas_count += 1
            except Exception as error:
                logging.error("Error procesando noticia '%s': %s", entry.get('title', ''), error)
                fallidas_count += 1

    guardar_noticias_db(noticias_db)
    regenerar_publicaciones(noticias_db)
    logging.info("Proceso finalizado. Procesadas: %s. Fallidas: %s.", procesadas_count, fallidas_count)


if __name__ == "__main__":
    main()
