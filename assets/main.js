// assets/main.js - Lógica cliente para AnimePulse

// Variables globales de control para la paginación
let noticiasVisibles = 6;
const NOTICIAS_POR_PAGINA = 6;
let categoriaSeleccionada = 'TODAS';

// Evento principal: se ejecuta cuando el DOM está completamente cargado
document.addEventListener('DOMContentLoaded', () => {
    inicializarProgresoLectura();
    ejecutarFiltro(); // Aplica el filtro inicial y la paginación
});

/**
 * Mide el avance del scroll en artículos individuales y actualiza la barra.
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
 * Copia la URL actual al portapapeles y cambia el texto del botón temporalmente.
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
 * Selecciona una categoría, actualiza el estilo de los botones (chips) y filtra.
 * @param {string} categoria - Nombre de la categoría seleccionada.
 */
function filtrarPorCategoria(categoria) {
    categoriaSeleccionada = categoria.toUpperCase();
    
    // Actualizar estilos visuales en las etiquetas/botones
    const botones = document.querySelectorAll('.chip-categoria');
    botones.forEach(btn => {
        const btnCat = btn.dataset.categoria ? btn.dataset.categoria.toUpperCase() : '';
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
 * Filtra las tarjetas comparando el texto del buscador y la categoría activa.
 */
function ejecutarFiltro() {
    const buscador = document.getElementById('buscador');
    const inputTexto = buscador ? buscador.value.toLowerCase().trim() : '';
    const tarjetas = document.querySelectorAll('.noticia-card');
    let encontradas = 0;

    tarjetas.forEach(tarjeta => {
        const tituloElem = tarjeta.querySelector('.titulo-noticia');
        const titulo = tituloElem ? tituloElem.innerText.toLowerCase() : '';
        const categoria = tarjeta.dataset.categoria ? tarjeta.dataset.categoria.toUpperCase() : '';

        const coincideTexto = titulo.includes(inputTexto);
        const coincideCategoria = (categoriaSeleccionada === 'TODAS') || (categoria === categoriaSeleccionada);

        if (coincideTexto && coincideCategoria) {
            tarjeta.classList.remove('hidden-filter');
            encontradas++;
        } else {
            tarjeta.classList.add('hidden-filter');
        }
    });

    // Gestionar mensaje de "no hay resultados"
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

    // Reiniciar paginación al filtrar
    inicializarPaginacion(true);
}

/**
 * Controla cuántas tarjetas filtradas se muestran en pantalla ("Cargar Más").
 * @param {boolean} reset - Si es true, reinicia la cuenta a las primeras 6 noticias.
 */
function inicializarPaginacion(reset = false) {
    if (reset) noticiasVisibles = NOTICIAS_POR_PAGINA;

    // Obtener únicamente las tarjetas que pasaron el filtro de texto y categoría
    const tarjetasValidas = document.querySelectorAll('.noticia-card:not(.hidden-filter)');
    const btnCargarMas = document.getElementById('btn-cargar-mas');

    tarjetasValidas.forEach((tarjeta, index) => {
        if (index < noticiasVisibles) {
            tarjeta.style.display = 'flex';
        } else {
            tarjeta.style.display = 'none';
        }
    });

    // Ocultar tarjetas no válidas completamente
    const tarjetasOcultas = document.querySelectorAll('.noticia-card.hidden-filter');
    tarjetasOcultas.forEach(tarjeta => {
        tarjeta.style.display = 'none';
    });

    // Controlar visibilidad del botón "Cargar más"
    if (btnCargarMas) {
        if (noticiasVisibles >= tarjetasValidas.length) {
            btnCargarMas.style.display = 'none';
        } else {
            btnCargarMas.style.display = 'inline-block';
        }
    }
}

/**
 * Incrementa el número de noticias visibles y actualiza la cuadrícula.
 */
function cargarMasNoticias() {
    noticiasVisibles += NOTICIAS_POR_PAGINA;
    inicializarPaginacion();
}