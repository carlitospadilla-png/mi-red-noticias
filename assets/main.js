// assets/main.js - Gestión de interfaz, búsqueda y paginación para AnimePulse

let noticiasVisibles = 6;
const NOTICIAS_POR_PAGINA = 6;
let categoriaSeleccionada = 'TODAS';

// Se ejecuta al cargar por completo la página web
document.addEventListener('DOMContentLoaded', () => {
    inicializarProgresoLectura();
    ejecutarFiltro(); // Evalúa y muestra las noticias disponibles inmediatamente
});

/**
 * Controla la barra de progreso de lectura en páginas de artículo.
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
 * Copia la dirección web del artículo al portapapeles.
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
 * Filtra por categoría (chips) y actualiza la vista.
 * @param {string} categoria - Categoría seleccionada (ej: 'SHONEN', 'TODAS')
 */
function filtrarPorCategoria(categoria) {
    categoriaSeleccionada = categoria.toUpperCase();
    
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
 * Filtra las noticias en tiempo real. Si el cuadro está vacío, muestra todas las noticias.
 */
function ejecutarFiltro() {
    const buscador = document.getElementById('buscador');
    const inputTexto = buscador ? buscador.value.toLowerCase().trim() : '';
    const tarjetas = document.querySelectorAll('.noticia-card');
    let encontradas = 0;

    tarjetas.forEach(tarjeta => {
        const tituloElem = tarjeta.querySelector('.titulo-noticia') || tarjeta.querySelector('h2');
        const descElem = tarjeta.querySelector('p');
        
        const titulo = tituloElem ? tituloElem.innerText.toLowerCase() : '';
        const descripcion = descElem ? descElem.innerText.toLowerCase() : '';
        const categoria = tarjeta.getAttribute('data-categoria') ? tarjeta.getAttribute('data-categoria').toUpperCase() : '';

        // Si inputTexto está vacío (""), coincideTexto será verdadero para todas
        const coincideTexto = (inputTexto === '') || titulo.includes(inputTexto) || descripcion.includes(inputTexto);
        const coincideCategoria = (categoriaSeleccionada === 'TODAS') || (categoria === categoriaSeleccionada);

        if (coincideTexto && coincideCategoria) {
            tarjeta.classList.remove('hidden-filter');
            encontradas++;
        } else {
            tarjeta.classList.add('hidden-filter');
        }
    });

    // Control del aviso de no resultados
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
 * Administra la paginación de la cuadrícula mediante el botón "Cargar más".
 * @param {boolean} reset - Reinicia el límite visual a 6 elementos.
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
 * Incrementa las tarjetas mostradas en pantalla al hacer clic.
 */
function cargarMasNoticias() {
    noticiasVisibles += NOTICIAS_POR_PAGINA;
    inicializarPaginacion();
}