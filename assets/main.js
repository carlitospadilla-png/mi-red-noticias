// Variable global para controlar la paginación
let noticiasVisibles = 6;
const NOTICIAS_POR_PAGINA = 6;

document.addEventListener('DOMContentLoaded', () => {
    inicializarProgresoLectura();
    inicializarPaginacion();
});

// Barra de progreso de lectura para artículos individuales
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

// Copiar enlace al portapapeles
function copiarEnlace() {
    navigator.clipboard.writeText(window.location.href);
    const copyText = document.getElementById('copy-text');
    if (copyText) {
        copyText.innerText = '¡Copiado!';
        setTimeout(() => { copyText.innerText = 'Copiar Enlace'; }, 2000);
    }
}

// Filtro combinado: Buscador por texto + Categorías (Chips)
let categoriaSeleccionada = 'TODAS';

function filtrarPorCategoria(categoria) {
    categoriaSeleccionada = categoria.toUpperCase();
    
    // Actualizar estilos visuales de los botones de categoría
    const botones = document.querySelectorAll('.chip-categoria');
    botones.forEach(btn => {
        if (btn.dataset.categoria === categoriaSeleccionada) {
            btn.classList.add('bg-purple-600', 'text-white');
            btn.classList.remove('bg-slate-800', 'text-slate-400');
        } else {
            btn.classList.remove('bg-purple-600', 'text-white');
            btn.classList.add('bg-slate-800', 'text-slate-400');
        }
    });

    ejecutarFiltro();
}

function ejecutarFiltro() {
    const inputTexto = document.getElementById('buscador') ? document.getElementById('buscador').value.toLowerCase() : '';
    const tarjetas = document.querySelectorAll('.noticia-card');
    let encontradas = 0;

    tarjetas.forEach(tarjeta => {
        const titulo = tarjeta.querySelector('.titulo-noticia').innerText.toLowerCase();
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

    // Controlar visibilidad de aviso "sin resultados"
    const noResultados = document.getElementById('no-resultados');
    if (noResultados) {
        noResultados.style.display = (encontradas === 0) ? 'block' : 'none';
    }

    inicializarPaginacion(true);
}

// Sistema de Paginación ("Cargar Más")
function inicializarPaginacion(reset = false) {
    if (reset) noticiasVisibles = NOTICIAS_POR_PAGINA;

    const tarjetas = document.querySelectorAll('.noticia-card:not(.hidden-filter)');
    const btnCargarMas = document.getElementById('btn-cargar-mas');

    tarjetas.forEach((tarjeta, index) => {
        if (index < noticiasVisibles) {
            tarjeta.style.display = 'flex';
        } else {
            tarjeta.style.display = 'none';
        }
    });

    if (btnCargarMas) {
        if (noticiasVisibles >= tarjetas.length) {
            btnCargarMas.style.display = 'none';
        } else {
            btnCargarMas.style.display = 'inline-block';
        }
    }
}

function cargarMasNoticias() {
    noticiasVisibles += NOTICIAS_POR_PAGINA;
    inicializarPaginacion();
}