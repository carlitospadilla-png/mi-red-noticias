import os
import json
import re
import logging
from html import escape
import xml.etree.ElementTree as ET
import time
from datetime import datetime
from urllib.parse import urljoin
import feedparser
from bs4 import BeautifulSoup
import markdown
from tenacity import retry, stop_after_attempt, wait_exponential
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configuración de Logging Estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Cargar archivo de configuración
def cargar_configuracion():
    ruta_config = "config.json"
    if os.path.exists(ruta_config):
        with open(ruta_config, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError("El archivo config.json no existe.")

CONFIG = cargar_configuracion()
DOMINIO_BASE = CONFIG["dominio_base"]
HISTORIAL_FILE = "noticias.json"
CARPETA_NOTICIAS = "noticias"

def cargar_noticias_db():
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def guardar_noticias_db(noticias):
    # Mantener rotación del historial según la configuración
    noticias_limitadas = noticias[:CONFIG.get("max_historial_registros", 200)]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(noticias_limitadas, f, ensure_ascii=False, indent=2)

def slugify(texto):
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    texto = re.sub(r'[\s_-]+', '-', texto)
    return texto.strip('-')

def extraer_imagen_rss(entry):
    """Extrae la URL de la imagen del feed RSS o usa una por defecto."""
    # 1. Buscar en media_content o media_thumbnail
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url')
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0].get('url')
    
    # 2. Buscar etiquetas <img> dentro del contenido HTML/Summary
    contenido = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
    if contenido:
        soup = BeautifulSoup(contenido, 'html.parser')
        img = soup.find('img')
        if img and img.get('src'):
            return img['src']

    # 3. Imagen fallback
    return CONFIG.get("imagen_placeholder")

# Reintentos automáticos con tenacity ante fallos en la API de Gemini
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def reescribir_con_gemini(cliente, titulo, descripcion):
    prompt = f"""
    Reescribe este artículo de noticias sobre ANIME/MANGA en español.
    Aporta valor editorial con un tono entretenido para fans del anime, optimizado para SEO.

    Noticia Original:
    Título: {titulo}
    Descripción: {descripcion}

    Responde ÚNICAMENTE en formato JSON con la siguiente estructura exacta:
    {{
      "titulo_seo": "Título descriptivo y atractivo",
      "categoria": "Elegir una: SHONEN, SEINEN, MANGA, PELÍCULAS, ESTRENOS o INDUSTRIA",
      "meta_descripcion": "Resumen conciso de 150 caracteres para SEO",
      "contenido_markdown": "Cuerpo redactado en Markdown con subtítulos ## y párrafos estructurados."
    }}
    """
    response = cliente.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

def generar_html_noticia(item):
    """Genera el HTML individual con metadatos de SEO on-page, Open Graph y Schema.org."""

    # Renderizado robusto de Markdown a HTML
    contenido_html = markdown.markdown(item["contenido_markdown"])

    titulo = escape(str(item.get('titulo_seo', 'Noticia de anime')), quote=True)
    meta_descripcion = escape(str(item.get('meta_descripcion', '')), quote=True)
    imagen_url = escape(str(item.get('imagen_url', CONFIG.get('imagen_placeholder', ''))), quote=True)
    url_original = escape(str(item.get('url_original', '')), quote=True)
    categoria = escape(str(item.get('categoria', 'ANIME')), quote=True)
    fecha_iso = escape(str(item.get('fecha_iso', '')), quote=True)
    fecha_formateada = escape(str(item.get('fecha_formateada', '')), quote=True)
    url_canonical = urljoin(DOMINIO_BASE, f"{CARPETA_NOTICIAS}/{item['filename']}")
    url_canonical_html = escape(url_canonical, quote=True)
    
    # JSON-LD Schema.org Article
    schema_org = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": item["titulo_seo"],
        "image": [item["imagen_url"]],
        "datePublished": item["fecha_iso"],
        "description": item["meta_descripcion"],
        "author": {
            "@type": "Organization",
            "name": "AnimePulse"
        }
    }
    schema_json = json.dumps(schema_org, ensure_ascii=False).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titulo} - AnimePulse</title>
    <meta name="description" content="{meta_descripcion}">
    <link rel="icon" href="/favicon.ico">
    <link rel="canonical" href="{url_canonical_html}">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="article">
    <meta property="og:title" content="{titulo}">
    <meta property="og:description" content="{meta_descripcion}">
    <meta property="og:image" content="{imagen_url}">
    <meta property="og:url" content="{url_canonical_html}">
    
    <!-- Twitter Cards -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{titulo}">
    <meta name="twitter:description" content="{meta_descripcion}">
    <meta name="twitter:image" content="{imagen_url}">

    <!-- Schema.org JSON-LD -->
    <script type="application/ld+json">
    {schema_json}
    </script>

    <script src="https://cdn.tailwindcss.com"></script>
    <script src="../assets/main.js" defer></script>
</head>
<body class="bg-slate-950 text-slate-200 font-sans min-h-screen flex flex-col antialiased">
    
    <div id="progress-bar" class="fixed top-0 left-0 h-1 bg-gradient-to-r from-purple-500 to-pink-500 z-50 transition-all duration-150" style="width: 0%;"></div>

    <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSENSE / ADSTERRA) -->

    <header class="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40">
        <div class="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
            <a href="../index.html" class="text-2xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                ANIME<span class="text-white">PULSE</span>
            </a>
            <a href="../index.html" class="text-sm font-semibold text-slate-300 hover:text-purple-400 transition-colors">
                ← Volver al Inicio
            </a>
        </div>
    </header>

    <main class="max-w-3xl mx-auto my-8 px-4 flex-grow w-full">
        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS -->

        <header class="mb-8 border-b border-slate-800 pb-6">
            <div class="flex items-center gap-3 mb-4 text-xs font-semibold">
                <span class="bg-purple-500/10 text-purple-400 border border-purple-500/20 px-3 py-1 rounded-full uppercase tracking-wider">
                    {categoria}
                </span>
                <span class="text-slate-500">•</span>
                <time class="text-slate-400" datetime="{fecha_iso}">{fecha_formateada}</time>
            </div>
            
            <h1 class="text-3xl md:text-4xl font-extrabold text-white leading-tight mb-6">
                {titulo}
            </h1>
            
            <div class="rounded-xl overflow-hidden mb-6 border border-slate-800">
                <img src="{imagen_url}" alt="{titulo}" loading="eager" class="w-full h-auto object-cover max-h-[450px]">
            </div>

            <p class="text-lg text-slate-300 leading-relaxed italic">
                "{meta_descripcion}"
            </p>
        </header>

        <article class="prose prose-invert max-w-none text-slate-200 leading-relaxed space-y-5 text-base md:text-lg">
            {contenido_html}
        </article>

        <!-- Atribución de fuente original -->
        <div class="mt-8 p-4 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-400">
            <span>Fuente original: </span>
            <a href="{url_original}" target="_blank" rel="noopener noreferrer" class="text-purple-400 hover:underline font-semibold">
                Ver artículo original en fuente oficial
            </a>
        </div>

        <div class="mt-8 pt-6 border-t border-slate-800 flex items-center justify-between">
            <button onclick="copiarEnlace()" class="bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-bold py-2.5 px-5 rounded-lg border border-slate-700 transition-all focus:ring-2 focus:ring-purple-500">
                <span id="copy-text">Copiar Enlace</span>
            </button>
            <a href="../index.html" class="bg-purple-600 hover:bg-purple-500 text-white text-sm font-bold py-2.5 px-5 rounded-lg transition-all">
                Más Noticias
            </a>
        </div>

        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS -->
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 text-slate-400 text-center py-6 text-sm">
        <p>&copy; {datetime.now().year} AnimePulse. Portal informativo automatizado.</p>
    </footer>
</body>
</html>"""

    os.makedirs(CARPETA_NOTICIAS, exist_ok=True)
    with open(os.path.join(CARPETA_NOTICIAS, item['filename']), "w", encoding="utf-8") as f:
        f.write(html)

def actualizar_index(noticias):
    """
    Lee la lista de noticias procesadas y reescribe el archivo index.html.
    Ordena las publicaciones por fecha y genera las tarjetas para el grid.
    """
    
    # Ordenar noticias por fecha ISO descendente
    noticias_ordenadas = sorted(noticias, key=lambda x: x.get('fecha_iso', ''), reverse=True)
    
    tarjetas_html = ""
    for item in noticias_ordenadas:
        url_noticia = escape(f"{CARPETA_NOTICIAS}/{item['filename']}", quote=True)
        categoria = escape(str(item.get('categoria', 'ANIME')), quote=True)
        titulo = escape(str(item.get('titulo_seo', 'Noticia de anime')))
        imagen_url = escape(str(item.get('imagen_url', CONFIG.get('imagen_placeholder', ''))), quote=True)
        fecha_formateada = escape(str(item.get('fecha_formateada', '')))
        meta_descripcion = escape(str(item.get('meta_descripcion', '')))
        tarjetas_html += f"""
        <article class="noticia-card bg-slate-900 rounded-xl overflow-hidden border border-slate-800 hover:border-purple-500/50 transition-all duration-300 hover:-translate-y-1 flex flex-col justify-between" data-categoria="{categoria}">
            <div>
                <div class="h-48 overflow-hidden relative border-b border-slate-800">
                    <img src="{imagen_url}" alt="{titulo}" loading="lazy" class="w-full h-full object-cover">
                    <span class="absolute top-3 left-3 bg-purple-600/90 backdrop-blur-sm text-white px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">
                        {categoria}
                    </span>
                </div>
                <div class="p-5">
                    <span class="text-xs text-slate-400 block mb-2">{fecha_formateada}</span>
                    <h2 class="text-lg font-bold text-white mb-2 line-clamp-2 hover:text-purple-400 transition-colors">
                        <a href="{url_noticia}" class="titulo-noticia">{titulo}</a>
                    </h2>
                    <p class="descripcion-noticia text-xs text-slate-400 line-clamp-2">{meta_descripcion}</p>
                </div>
            </div>
            <div class="px-5 pb-5 pt-0 mt-auto">
                <a href="{url_noticia}" class="text-xs font-bold text-purple-400 hover:text-purple-300 inline-flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-purple-500 rounded">
                    Leer artículo →
                </a>
            </div>
        </article>
        """

    index_html = f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AnimePulse - Noticias de Anime & Manga al Instante</title>
    <meta name="description" content="Tu portal con las últimas novedades, estrenos y tendencias del mundo del anime y manga.">
    <link rel="icon" href="/favicon.ico">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="assets/main.js" defer></script>
    <style>
        .oculta-busqueda, .oculta-categoria, .oculta-paginacion {{ display: none !important; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-200 font-sans min-h-screen flex flex-col antialiased">

    <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS -->

    <header class="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40">
        <div class="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row justify-between items-center gap-4">
            <a href="index.html" class="text-3xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                ANIME<span class="text-white">PULSE</span>
            </a>
            <div class="relative w-full sm:w-72">
                <input type="text" id="buscador" onkeyup="ejecutarFiltro()" placeholder="Buscar por título..." aria-label="Buscar noticias por título"
                    class="w-full bg-slate-950 text-slate-200 text-sm pl-4 pr-4 py-2 rounded-lg border border-slate-800 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-colors">
            </div>
        </div>
    </header>

    <section class="bg-gradient-to-b from-purple-900/20 to-transparent border-b border-slate-800/50 py-10 px-4 text-center">
        <div class="max-w-4xl mx-auto">
            <h1 class="text-3xl md:text-5xl font-black text-white mb-3">
                Noticias de Anime & Manga
            </h1>
            <p class="text-slate-400 text-sm md:text-base mb-6">
                Tu portal con las últimas novedades, estrenos y tendencias del mundo del anime y manga.
            </p>

            <!-- Filtros por Categoría (Chips) -->
            <div class="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto">
                <button onclick="filtrarPorCategoria('TODAS')" data-categoria="TODAS" class="chip-categoria bg-purple-600 text-white text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all focus:ring-2 focus:ring-purple-500">TODAS</button>
                <button onclick="filtrarPorCategoria('SHONEN')" data-categoria="SHONEN" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all hover:text-white focus:ring-2 focus:ring-purple-500">SHONEN</button>
                <button onclick="filtrarPorCategoria('SEINEN')" data-categoria="SEINEN" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all hover:text-white focus:ring-2 focus:ring-purple-500">SEINEN</button>
                <button onclick="filtrarPorCategoria('MANGA')" data-categoria="MANGA" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all hover:text-white focus:ring-2 focus:ring-purple-500">MANGA</button>
                <button onclick="filtrarPorCategoria('PELÍCULAS')" data-categoria="PELÍCULAS" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all hover:text-white focus:ring-2 focus:ring-purple-500">PELÍCULAS</button>
                <button onclick="filtrarPorCategoria('ESTRENOS')" data-categoria="ESTRENOS" class="chip-categoria bg-slate-800 text-slate-400 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-700 transition-all hover:text-white focus:ring-2 focus:ring-purple-500">ESTRENOS</button>
            </div>
        </div>
    </section>

    <main class="max-w-6xl mx-auto my-10 px-4 flex-grow w-full">
        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS -->

        <div id="grid-noticias" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {tarjetas_html}
        </div>

        <!-- Estado Vacío -->
        <div id="no-resultados" class="hidden text-center py-16">
            <p class="text-slate-400 text-lg font-semibold" role="status">No se encontraron noticias que coincidan con la búsqueda.</p>
        </div>

        <!-- Botón Cargar Más -->
        <div class="text-center mt-10">
            <button id="btn-cargar-mas" type="button" onclick="cargarMasNoticias()" class="bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 px-8 rounded-lg shadow-lg transition-all focus:ring-2 focus:ring-purple-500" aria-label="Cargar más noticias">
                Cargar más noticias
            </button>
        </div>
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 text-slate-400 text-center py-8 text-sm mt-auto">
        <p>&copy; {datetime.now().year} AnimePulse. Todos los derechos reservados.</p>
    </footer>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

def generar_sitemap(noticias):
    """Genera sitemap.xml con las fechas de publicación reales (lastmod)."""
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    
    # URL del Index
    url_node = ET.SubElement(urlset, "url")
    ET.SubElement(url_node, "loc").text = DOMINIO_BASE
    ET.SubElement(url_node, "lastmod").text = datetime.now().strftime('%Y-%m-%d')
    
    for item in noticias:
        url_node = ET.SubElement(urlset, "url")
        ET.SubElement(url_node, "loc").text = urljoin(DOMINIO_BASE, f"{CARPETA_NOTICIAS}/{item['filename']}")
        ET.SubElement(url_node, "lastmod").text = item.get('fecha_iso', datetime.now().strftime('%Y-%m-%d'))

    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ", level=0)
    tree.write("sitemap.xml", encoding="utf-8", xml_declaration=True)

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.warning("No se detectó GEMINI_API_KEY. Saliendo del script.")
        return

    cliente = genai.Client(api_key=api_key)
    noticias_db = cargar_noticias_db()
    urls_procesadas = {item["url_original"] for item in noticias_db}

    procesadas_count = 0
    fallidas_count = 0

    logging.info("Iniciando escaneo de Feeds RSS...")

    for feed_url in CONFIG.get("feeds_rss", []):
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:CONFIG.get("max_noticias_por_feed", 5)]:
            url_original = entry.link
            
            if url_original in urls_procesadas:
                continue

            logging.info(f"Procesando nueva noticia: {entry.title}")
            
            try:
                datos_ia = reescribir_con_gemini(cliente, entry.title, getattr(entry, 'summary', ''))
                if datos_ia:
                    filename = f"{slugify(datos_ia['titulo_seo'])}.html"
                    imagen_url = extraer_imagen_rss(entry)
                    if getattr(entry, 'published_parsed', None):
                        fecha_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    else:
                        fecha_dt = datetime.now()

                    item_noticia = {
                        "url_original": url_original,
                        "filename": filename,
                        "titulo_seo": datos_ia["titulo_seo"],
                        "categoria": datos_ia.get("categoria", "ANIME").upper(),
                        "meta_descripcion": datos_ia["meta_descripcion"],
                        "contenido_markdown": datos_ia["contenido_markdown"],
                        "imagen_url": imagen_url,
                        "fecha_iso": fecha_dt.strftime('%Y-%m-%d'),
                        "fecha_formateada": fecha_dt.strftime('%d/%m/%Y')
                    }

                    generar_html_noticia(item_noticia)
                    noticias_db.append(item_noticia)
                    urls_procesadas.add(url_original)
                    procesadas_count += 1

            except Exception as e:
                logging.error(f"Error procesando noticia '{entry.title}': {e}")
                fallidas_count += 1

    # Guardar cambios y reconstruir índices
    guardar_noticias_db(noticias_db)
    actualizar_index(noticias_db)
    generar_sitemap(noticias_db)

    logging.info(f"Proceso finalizado. Noticia(s) procesada(s): {procesadas_count}. Fallida(s): {fallidas_count}.")

if __name__ == "__main__":
    main()