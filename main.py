import os
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urljoin
import feedparser
from google import genai
from google.genai import types

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
DOMINIO_BASE = "https://tu-usuario.github.io/red-noticias-ia/"
FEEDS_RSS = [
    "https://www.animenewsnetwork.com/all/rss.xml?ann-format=rail",
    "https://somoskudasai.com/feed/",
]
MAX_NOTICIAS_POR_FEED = 5
HISTORIAL_FILE = "historial.json"
CARPETA_NOTICIAS = "noticias"

def cargar_historial():
    """Lee el archivo JSON para evitar duplicados."""
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def guardar_historial(historial):
    """Guarda el historial actualizado."""
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)

def slugify(texto):
    """Convierte el título en un slug para la URL."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    texto = re.sub(r'[\s_-]+', '-', texto)
    return texto.strip('-')

def reescribir_con_gemini(cliente, titulo, descripcion):
    """Solicita a Gemini reescribir la noticia con metadatos de anime."""
    prompt = f"""
    Reescribe este artículo de noticias sobre ANIME/MANGA en español.
    Usa un tono apasionado y entretenido para la comunidad otaku/anime, manteniendo un excelente SEO.

    Noticia Original:
    Título: {titulo}
    Descripción: {descripcion}

    Responde ÚNICAMENTE en formato JSON con la siguiente estructura exacta:
    {{
      "titulo_seo": "Título épico y atractivo sin caer en clickbait engañoso",
      "categoria": "Elegir UNA: Shonen, Seinen, Manga, Películas, Estrenos o Industria",
      "meta_descripcion": "Resumen conciso de 150 caracteres para SEO",
      "contenido_markdown": "Cuerpo redactado en formato Markdown usando subtítulos ## y párrafos claros."
    }}
    """
    try:
        response = cliente.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error procesando la noticia con Gemini: {e}")
        return None

def generar_html_noticia(datos_noticia, filename):
    """Genera la plantilla de lectura individual con Dark Mode y componentes modernos."""
    contenido_html = datos_noticia["contenido_markdown"].replace("\n\n", "</p><p>")
    contenido_html = re.sub(r'##\s*(.*?)\n', r'</h2><h2 class="text-2xl font-bold mt-8 mb-4 text-purple-400 border-l-4 border-purple-500 pl-3">\1</h2><p>', contenido_html)
    contenido_html = f"<p>{contenido_html}</p>"

    html = f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{datos_noticia['titulo_seo']} - AnimePulse</title>
    <meta name="description" content="{datos_noticia['meta_descripcion']}">
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen flex flex-col antialiased">
    
    <!-- Barra de progreso superior -->
    <div id="progress-bar" class="fixed top-0 left-0 h-1 bg-gradient-to-r from-purple-500 to-pink-500 z-50 transition-all duration-150" style="width: 0%;"></div>

    <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSTERRA/YLLIX/POPADS) -->

    <header class="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40">
        <div class="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
            <a href="../index.html" class="text-2xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                ANIME<span class="text-white">PULSE</span>
            </a>
            <a href="../index.html" class="text-sm font-semibold text-slate-400 hover:text-purple-400 transition-colors">
                ← Volver al Inicio
            </a>
        </div>
    </header>

    <main class="max-w-3xl mx-auto my-8 px-4 flex-grow w-full">
        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSTERRA/YLLIX/POPADS) -->

        <header class="mb-8 border-b border-slate-800 pb-6">
            <div class="flex items-center gap-3 mb-4 text-xs font-semibold">
                <span class="bg-purple-500/10 text-purple-400 border border-purple-500/20 px-3 py-1 rounded-full uppercase tracking-wider">
                    {datos_noticia.get('categoria', 'Anime')}
                </span>
                <span class="text-slate-500">•</span>
                <span class="text-slate-400">{datetime.now().strftime('%d/%m/%Y')}</span>
            </div>
            
            <h1 class="text-3xl md:text-4xl font-extrabold text-white leading-tight mb-4">
                {datos_noticia['titulo_seo']}
            </h1>
            
            <p class="text-lg text-slate-400 leading-relaxed italic">
                "{datos_noticia['meta_descripcion']}"
            </p>
        </header>

        <article class="prose prose-invert max-w-none text-slate-300 leading-relaxed space-y-5 text-base md:text-lg">
            {contenido_html}
        </article>

        <div class="mt-10 pt-6 border-t border-slate-800 flex items-center justify-between">
            <button onclick="copiarEnlace()" class="bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-bold py-2.5 px-5 rounded-lg border border-slate-700 transition-all">
                <span id="copy-text">Copiar Enlace</span>
            </button>
            <a href="../index.html" class="bg-purple-600 hover:bg-purple-500 text-white text-sm font-bold py-2.5 px-5 rounded-lg transition-all">
                Más Noticias
            </a>
        </div>

        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSTERRA/YLLIX/POPADS) -->
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 text-slate-500 text-center py-6 text-sm">
        <p>&copy; {datetime.now().year} AnimePulse. Todos los derechos reservados.</p>
    </footer>

    <script>
        window.onscroll = function() {{
            let winScroll = document.body.scrollTop || document.documentElement.scrollTop;
            let height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            let scrolled = (winScroll / height) * 100;
            document.getElementById("progress-bar").style.width = scrolled + "%";
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
    with open(os.path.join(CARPETA_NOTICIAS, filename), "w", encoding="utf-8") as f:
        f.write(html)

def actualizar_index():
    """Genera la página principal con diseño de tarjetas modernas y buscador dinámico."""
    archivos = [f for f in os.listdir(CARPETA_NOTICIAS) if f.endswith('.html')]
    tarjetas_html = ""
    
    for archivo in archivos:
        titulo_display = archivo.replace('.html', '').replace('-', ' ').capitalize()
        url_noticia = f"{CARPETA_NOTICIAS}/{archivo}"
        tarjetas_html += f"""
        <article class="noticia-card bg-slate-900 rounded-xl overflow-hidden border border-slate-800 hover:border-purple-500/50 transition-all duration-300 hover:-translate-y-1 flex flex-col justify-between">
            <div class="p-6">
                <span class="bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2.5 py-0.5 rounded-full text-xs font-bold inline-block mb-3">
                    ANIME
                </span>
                <h2 class="text-xl font-bold text-white mb-3 hover:text-purple-400 transition-colors">
                    <a href="{url_noticia}" class="titulo-noticia">{titulo_display}</a>
                </h2>
            </div>
            <div class="px-6 pb-6 pt-0 mt-auto flex items-center justify-between border-t border-slate-800/50 pt-4">
                <span class="text-xs text-slate-500">Reciente</span>
                <a href="{url_noticia}" class="text-xs font-bold text-purple-400 hover:text-purple-300">
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
    <title>AnimePulse - Noticias de Anime & Manga</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen flex flex-col antialiased">

    <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSTERRA/YLLIX/POPADS) -->

    <header class="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40">
        <div class="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row justify-between items-center gap-4">
            <a href="index.html" class="text-3xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                ANIME<span class="text-white">PULSE</span>
            </a>
            <div class="relative w-full sm:w-72">
                <input type="text" id="buscador" onkeyup="filtrarNoticias()" placeholder="Buscar noticia..." 
                    class="w-full bg-slate-950 text-slate-200 text-sm pl-4 pr-4 py-2 rounded-lg border border-slate-800 focus:outline-none focus:border-purple-500 transition-colors">
            </div>
        </div>
    </header>

    <section class="bg-gradient-to-b from-purple-900/20 to-transparent border-b border-slate-800/50 py-12 px-4 text-center">
        <div class="max-w-4xl mx-auto">
            <h1 class="text-4xl md:text-5xl font-black text-white mt-2 mb-3">
                Noticias de Anime & Manga
            </h1>
            <p class="text-slate-400 text-base md:text-lg">
                Actualizaciones automáticas procesadas con Inteligencia Artificial.
            </p>
        </div>
    </section>

    <main class="max-w-6xl mx-auto my-10 px-4 flex-grow w-full">
        <!-- INSERTAR AQUÍ CÓDIGO JS DE ANUNCIOS (ADSTERRA/YLLIX/POPADS) -->

        <div id="grid-noticias" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {tarjetas_html}
        </div>

        <p id="no-resultados" class="hidden text-center text-slate-500 py-12 text-lg">
            No se encontraron noticias relacionadas.
        </p>
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 text-slate-500 text-center py-8 text-sm mt-auto">
        <p>&copy; {datetime.now().year} AnimePulse. Todos los derechos reservados.</p>
    </footer>

    <script>
        function filtrarNoticias() {{
            let input = document.getElementById('buscador').value.toLowerCase();
            let tarjetas = document.getElementsByClassName('noticia-card');
            let encontrados = 0;

            for (let i = 0; i < tarjetas.length; i++) {{
                let titulo = tarjetas[i].querySelector('.titulo-noticia').innerText.toLowerCase();
                if (titulo.includes(input)) {{
                    tarjetas[i].style.display = "";
                    encontrados++;
                }} else {{
                    tarjetas[i].style.display = "none";
                }}
            }}

            document.getElementById('no-resultados').style.display = (encontrados === 0) ? "block" : "none";
        }}
    </script>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

def generar_sitemap():
    """Genera el archivo sitemap.xml."""
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    
    url_node = ET.SubElement(urlset, "url")
    ET.SubElement(url_node, "loc").text = DOMINIO_BASE
    ET.SubElement(url_node, "lastmod").text = datetime.now().strftime('%Y-%m-%d')
    
    if os.path.exists(CARPETA_NOTICIAS):
        for archivo in os.listdir(CARPETA_NOTICIAS):
            if archivo.endswith(".html"):
                url_node = ET.SubElement(urlset, "url")
                ET.SubElement(url_node, "loc").text = urljoin(DOMINIO_BASE, f"{CARPETA_NOTICIAS}/{archivo}")
                ET.SubElement(url_node, "lastmod").text = datetime.now().strftime('%Y-%m-%d')

    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ", level=0)
    tree.write("sitemap.xml", encoding="utf-8", xml_declaration=True)

def main():
    """Coordinador general."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Aviso: No se detectó GEMINI_API_KEY. Configura la variable de entorno.")
        return

    cliente = genai.Client(api_key=api_key)
    historial = cargar_historial()

    for feed_url in FEEDS_RSS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:MAX_NOTICIAS_POR_FEED]:
            if entry.link in historial:
                continue

            datos_ia = reescribir_con_gemini(cliente, entry.title, getattr(entry, 'summary', ''))
            if datos_ia:
                filename = f"{slugify(datos_ia['titulo_seo'])}.html"
                generar_html_noticia(datos_ia, filename)
                historial.append(entry.link)

    guardar_historial(historial)
    actualizar_index()
    generar_sitemap()

if __name__ == "__main__":
    main()