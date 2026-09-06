// assets/main.js - Control del frontend para AnimePulse

let noticiasVisibles = 6;
const NOTICIAS_POR_PAGINA = 6;
let categoriaSeleccionada = 'TODAS';

document.addEventListener('DOMContentLoaded', () => {
    inicializarProgresoLectura();
    ejecutarFiltro(); // Carga las noticias guardadas al iniciar la página
});

/**
 * Calcula el avance de la lectura en páginas de artículos individuales.
 */
function inicializarProgresoLectura() {
    const progressBar = document.getElementById('progress-bar');
    if (!progressBar) return;

    window.addEventListener('scroll', () => {
        const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
        const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (winScroll / height) * 100;
        progressBar.style.width = scrolled + '%';
    });
}

/**
 * Permite copiar el enlace de la noticia al portapapeles del usuario.
 */
function copiarEnlace() {
    navigator.clipboard.writeText(window.location.href);
    const copyText = document.getElementById('copy-text');
    if (copyText) {
        copyText.innerText = '¡Copiado!';
        setTimeout(() => { copyText.innerText = 'Copiar Enlace'; }, 2000);
    }
}

/**
 * Filtra las noticias según la categoría seleccionada por el usuario.
 * @param {string} categoria - Categoría a filtrar (ej. 'SHONEN', 'MANGA', 'TODAS').
 */
function filtrarPorCategoria(categoria) {
    categoriaSeleccionada = categoria.toUpperCase();
    
    // Actualizar apariencia visual de los botones (chips)
    const botones = document.querySelectorAll('.chip-categoria');
    botones.forEach(btn => {
        const btnCat = btn.getAttribute('data-categoria') ? btn.getAttribute('data-categoria').toUpperCase() : '';
        if (btnCat === categoriaSeleccionada) {
            btn.classList.add('bg-purple-600', 'text-white');
            btn.classList.remove('bg-slate-800', 'text-slate-400');
        } else {
            btn.classList.remove('bg-purple-600', 'text-white');
            btn.classList.add('bg-slate-800', 'text-slate-400');
        }
    });

    ejecutarFiltro();
}

/**
 * Realiza la búsqueda por texto y categoría sobre todas las tarjetas presentes.
 */
function ejecutarFiltro() {
    const buscador = document.getElementById('buscador');
    const inputTexto = buscador ? buscador.value.toLowerCase().trim() : '';
    const tarjetas = document.querySelectorAll('.noticia-card');
    let encontradas = 0;

    tarjetas.forEach(tarjeta => {
        // Obtener el texto del título dentro de la tarjeta
        const tituloElem = tarjeta.querySelector('.titulo-noticia') || tarjeta.querySelector('h2');
        const titulo = tituloElem ? tituloElem.innerText.toLowerCase() : '';
        const categoria = tarjeta.getAttribute('data-categoria') ? tarjeta.getAttribute('data-categoria').toUpperCase() : '';

        const coincideTexto = inputTexto === '' || titulo.includes(inputTexto);
        const coincideCategoria = (categoriaSeleccionada === 'TODAS') || (categoria === categoriaSeleccionada);

        if (coincideTexto && coincideCategoria) {
            tarjeta.classList.remove('hidden-filter');
            encontradas++;
        } else {
            tarjeta.classList.add('hidden-filter');
        }
    });

    // Mostrar el contenedor de "Sin resultados" solo si la búsqueda no arroja coincidencias
    const noResultados = document.getElementById('no-resultados');
    if (noResultados) {
        if (encontradas === 0) {
            noResultados.classList.remove('hidden');
            noResultados.style.display = 'block';
        } else {
            noResultados.classList.add('hidden');
            noResultados.style.display = 'none';
        }
    }

    inicializarPaginacion(true);
}

/**
 * Controla la paginación con el botón "Cargar más noticias".
 * @param {boolean} reset - Si es verdadero, reinicia el límite visual a 6 noticias.
 */
function inicializarPaginacion(reset = false) {
    if (reset) noticiasVisibles = NOTICIAS_POR_PAGINA;

    const tarjetasValidas = document.querySelectorAll('.noticia-card:not(.hidden-filter)');
    const btnCargarMas = document.getElementById('btn-cargar-mas');

    tarjetasValidas.forEach((tarjeta, index) => {
        if (index < noticiasVisibles) {
            tarjeta.style.display = 'flex';
        } else {
            tarjeta.style.display = 'none';
        }
    });

    const tarjetasOcultas = document.querySelectorAll('.noticia-card.hidden-filter');
    tarjetasOcultas.forEach(tarjeta => {
        tarjeta.style.display = 'none';
    });

    if (btnCargarMas) {
        if (noticiasVisibles >= tarjetasValidas.length) {
            btnCargarMas.style.display = 'none';
        } else {
            btnCargarMas.style.display = 'inline-block';
        }
    }
}

/**
 * Incrementa las noticias a mostrar al hacer clic en el botón de paginación.
 */
function cargarMasNoticias() {
    noticiasVisibles += NOTICIAS_POR_PAGINA;
    inicializarPaginacion();
}