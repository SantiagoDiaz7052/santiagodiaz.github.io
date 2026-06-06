/**
 * zelic-layout.js
 * JS mínimo para el nuevo layout de vistas.
 * Se carga DESPUÉS de zelic.js — extiende sin reescribir.
 *
 * Gestiona:
 *  - Navegación de vistas del panel central (.pv)
 *  - Sincronización sidebar ↔ panel derecho
 *  - Estados visuales del voice float (state-listening / processing / speaking)
 *  - Vista home y opciones
 *  - Archivos adjuntos en pv-archivos
 */

'use strict';

/* ── Mapa de vistas ──────────────────────────────────────────────────────────
   ni.data-ni  →  { pv: id panel central, rp: id panel derecho }
─────────────────────────────────────────────────────────────────────────────*/
const VISTA_MAP = {
  home:     { pv: 'pv-home',     rp: 'rp-main' },
  chat:     { pv: 'pv-chat',     rp: 'rp-main' },
  voz:      { pv: 'pv-chat',     rp: 'rp-main' },      // voz usa el mismo chat
  archivos: { pv: 'pv-archivos', rp: 'rp-archivos' },
  opciones: { pv: 'pv-opciones', rp: 'rp-opciones' },
};

// Todos los paneles centrales y derechos
const PV_IDS = ['pv-home', 'pv-chat', 'pv-archivos', 'pv-opciones'];
const RP_IDS = ['rp-main', 'rp-workspace', 'rp-archivos', 'rp-opciones'];

/**
 * activarVista(niKey)
 * Muestra el panel central y derecho correspondiente al item de nav.
 * Oculta todos los demás. Replica la lógica de _mostrar_chat() / _mostrar_inicio().
 */
function activarVista(niKey) {
  const mapa = VISTA_MAP[niKey];
  if (!mapa) return;

  // Ocultar todos los paneles centrales
  PV_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  // Ocultar todos los paneles derechos
  RP_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  // Mostrar los correctos
  const pvEl = document.getElementById(mapa.pv);
  const rpEl = document.getElementById(mapa.rp);
  if (pvEl) pvEl.style.display = 'flex';
  if (rpEl) rpEl.style.display = 'flex';

  // Si es VOZ: iniciar voz también
  if (niKey === 'voz') {
    // Asegurar que el chat esté en modo chat antes de abrir voz
    if (typeof iniciarVoz === 'function') iniciarVoz();
  }

  // Si es OPCIONES: actualizar datos
  if (niKey === 'opciones') actualizarOpciones();

  // Marcar ni activo
  document.querySelectorAll('.ni').forEach(n => n.classList.remove('on'));
  const niEl = document.querySelector(`[data-ni="${niKey}"]`);
  if (niEl) niEl.classList.add('on');
}

/**
 * activarTab(tabKey)
 * Sincroniza un tab del topbar con la vista correcta.
 * Usado también desde botones del home.
 */
function activarTab(tabKey) {
  // Sincronizar topbar
  document.querySelectorAll('.tb-tab').forEach(t => t.classList.remove('on'));
  const tabEl = document.querySelector(`[data-tab="${tabKey}"]`);
  if (tabEl) tabEl.classList.add('on');

  // Mapa tab → ni
  const tabNiMap = {
    sistema:   'chat',
    workspace: 'chat',   // workspace abre historial en panel derecho
    archivos:  'archivos',
  };

  const niKey = tabNiMap[tabKey] || tabKey;

  if (tabKey === 'workspace') {
    // Tab Chats → mostrar rp-workspace en panel derecho, mantener chat en centro
    PV_IDS.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    RP_IDS.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    const pvChat = document.getElementById('pv-chat');
    const rpWs   = document.getElementById('rp-workspace');
    if (pvChat) pvChat.style.display = 'flex';
    if (rpWs)   rpWs.style.display   = 'flex';
    if (typeof cargarSesiones === 'function') cargarSesiones();
  } else {
    activarVista(niKey);
  }
}

/* ── Reemplazar handlers de nav y tabs del zelic.js original ─────────────────
   zelic.js pone listeners en querySelectorAll('.ni') y '.tb-tab'.
   Este archivo los reemplaza después de que zelic.js cargó.
   Usamos un pequeño delay para que zelic.js inicialice primero.
─────────────────────────────────────────────────────────────────────────────*/
window.addEventListener('DOMContentLoaded', () => {
  // Reemplazar listeners de .ni con la nueva lógica de vistas
  document.querySelectorAll('.ni').forEach(b => {
    // Clonar y reemplazar el nodo elimina los listeners anteriores de zelic.js
    const clone = b.cloneNode(true);
    b.parentNode.replaceChild(clone, b);
    clone.addEventListener('click', () => {
      const niKey = clone.dataset.ni;
      if (!niKey) return;
      activarVista(niKey);
    });
  });

  // Reemplazar listeners de .tb-tab
  document.querySelectorAll('.tb-tab').forEach(t => {
    const clone = t.cloneNode(true);
    t.parentNode.replaceChild(clone, t);
    clone.addEventListener('click', () => {
      activarTab(clone.dataset.tab);
    });
  });

  // Estado inicial: home visible
  activarVista('home');
});

/* ── iniciarDesdeHome ────────────────────────────────────────────────────────
   Botón "Nueva conversación" del home.
   Crea sesión + cambia a vista chat.
─────────────────────────────────────────────────────────────────────────────*/
async function iniciarDesdeHome() {
  if (typeof nuevaConversacion === 'function') {
    await nuevaConversacion();
  }
  activarVista('chat');
}

/* ── actualizarOpciones ──────────────────────────────────────────────────────
   Carga datos reales en la vista opciones.
─────────────────────────────────────────────────────────────────────────────*/
async function actualizarOpciones() {
  // Sesión activa
  const optSid = document.getElementById('opt-sid');
  if (optSid) {
    // sesionActiva viene de zelic.js
    optSid.textContent = (typeof sesionActiva !== 'undefined' && sesionActiva)
      ? `#${sesionActiva}` : '—';
  }

  // CPU / RAM desde /api/sysinfo
  try {
    const data = await fetch('/api/sysinfo').then(r => r.json());
    if (data.ok) {
      const optCpu = document.getElementById('opt-cpu');
      const optRam = document.getElementById('opt-ram');
      if (optCpu) optCpu.textContent = data.data.cpu;
      if (optRam) optRam.textContent = data.data.ram;
    }
  } catch (_) {}

  // Número de conversaciones desde /api/sesiones
  try {
    const data = await fetch('/api/sesiones').then(r => r.json());
    if (data.ok) {
      const optChats = document.getElementById('opt-chats');
      if (optChats) optChats.textContent = data.data.length;
      const total = data.data.reduce((acc, s) => acc + (s.total || 0), 0);
      const optMsgs = document.getElementById('opt-msgs');
      if (optMsgs) optMsgs.textContent = total;
    }
  } catch (_) {}

  // Voice
  const optVoice = document.getElementById('opt-voice');
  if (optVoice) {
    optVoice.textContent = (typeof vozActiva !== 'undefined' && vozActiva)
      ? 'activa' : 'ready';
  }
}

/* ── Sincronizar ctx-session con sesionActiva ────────────────────────────────
   Cada vez que zelic.js actualice sesionActiva, reflejar en #ctx-session.
   Usamos un MutationObserver-free approach: polling liviano cada 2s.
─────────────────────────────────────────────────────────────────────────────*/
setInterval(() => {
  const ctxSession = document.getElementById('ctx-session');
  if (!ctxSession) return;
  const sid = typeof sesionActiva !== 'undefined' ? sesionActiva : null;
  ctxSession.textContent = sid ? `#${sid}` : '—';
}, 2000);

/* ── Estado visual del voice float ──────────────────────────────────────────
   Extiende setVozEstado() de zelic.js para añadir clases CSS de estado.
   Las clases .state-listening / .state-processing / .state-speaking
   controlan los colores de .vfr y .vfs-dot desde zelic-layout.css.
─────────────────────────────────────────────────────────────────────────────*/
const VOZ_STATE_CLASSES = ['state-listening', 'state-processing', 'state-speaking'];

// Sobrescribir setVozEstado después de que zelic.js lo define
window.addEventListener('load', () => {
  const originalSetVozEstado = typeof setVozEstado === 'function' ? setVozEstado : null;

  window.setVozEstado = function(estado) {
    // Llamar al original de zelic.js primero
    if (originalSetVozEstado) originalSetVozEstado(estado);

    // Añadir clase CSS al #vf
    const vfEl = document.getElementById('vf');
    if (!vfEl) return;

    VOZ_STATE_CLASSES.forEach(c => vfEl.classList.remove(c));

    const classMap = {
      escuchando: 'state-listening',
      procesando: 'state-processing',
      hablando:   'state-speaking',
      idle:       null,
    };
    const cls = classMap[estado];
    if (cls) vfEl.classList.add(cls);
  };

  // Cuando se abre voz: cambiar ni-voz a activo con clase especial
  const niVoz = document.querySelector('[data-ni="voz"]');
  if (niVoz) {
    // Observar si #vf tiene clase .show para marcar el ni
    const observer = new MutationObserver(() => {
      const vfEl = document.getElementById('vf');
      if (!vfEl) return;
      const activo = vfEl.classList.contains('show');
      niVoz.classList.toggle('voz-activa', activo);
    });
    const vfEl = document.getElementById('vf');
    if (vfEl) observer.observe(vfEl, { attributes: true, attributeFilter: ['class'] });
  }
});

/* ── Archivos: registrar adjunto subido en la vista archivos ─────────────────
   Cuando zelic.js sube un archivo, lo añadimos a la grid de archivos.
─────────────────────────────────────────────────────────────────────────────*/
const _archivosSubidos = []; // registro local de la sesión

function registrarArchivoEnGrid(nombre) {
  _archivosSubidos.push({ nombre, fecha: new Date().toLocaleDateString('es-CO') });
  renderizarArchivos();
}

function renderizarArchivos() {
  const grid = document.getElementById('files-grid');
  if (!grid) return;

  if (!_archivosSubidos.length) {
    grid.innerHTML = '<div class="file-empty">No hay archivos adjuntos en esta sesión.</div>';
    return;
  }

  grid.innerHTML = '';
  _archivosSubidos.forEach(f => {
    const ext = f.nombre.split('.').pop().toLowerCase();
    const iconMap = {
      pdf: 'ti-file-type-pdf', txt: 'ti-file-type-txt',
      doc: 'ti-file-type-doc', docx: 'ti-file-type-doc',
      png: 'ti-photo', jpg: 'ti-photo', jpeg: 'ti-photo',
      csv: 'ti-table', json: 'ti-braces',
      py: 'ti-brand-python', js: 'ti-brand-javascript',
      html: 'ti-brand-html5', md: 'ti-markdown',
    };
    const icon = iconMap[ext] || 'ti-file';

    const card = document.createElement('div');
    card.className = 'file-card';
    card.innerHTML = `
      <i class="ti ${icon} file-card-icon"></i>
      <div class="file-card-name" title="${f.nombre}">${f.nombre}</div>
      <div class="file-card-date">${f.fecha}</div>
    `;
    grid.appendChild(card);
  });
}

// Interceptar mostrarAdjuntoBadge de zelic.js para también registrar en grid
window.addEventListener('load', () => {
  const originalMostrarBadge = typeof mostrarAdjuntoBadge === 'function'
    ? mostrarAdjuntoBadge : null;

  if (originalMostrarBadge) {
    window.mostrarAdjuntoBadge = function(nombre) {
      originalMostrarBadge(nombre);
      registrarArchivoEnGrid(nombre);
    };
  }
});

/* ── nuevaConversacion: cambiar a vista chat después de crear ────────────────
   Cuando se llama nuevaConversacion() y la vista no es chat, navegar a chat.
─────────────────────────────────────────────────────────────────────────────*/
window.addEventListener('load', () => {
  const originalNuevaConv = typeof nuevaConversacion === 'function'
    ? nuevaConversacion : null;

  if (originalNuevaConv) {
    window.nuevaConversacion = async function() {
      await originalNuevaConv();
      // Si estamos en home u otra vista, ir a chat
      const pvChat = document.getElementById('pv-chat');
      if (pvChat && pvChat.style.display === 'none') {
        activarVista('chat');
      }
    };
  }
});

console.log('[Zelic Layout] Inicializado.');