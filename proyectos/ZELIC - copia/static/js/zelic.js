/**
 * zelic.js — Lógica frontend completa de Zelic
 * Base: zelic.js original (uploads/zelic.js) — solo se modifica la sección
 * de NAV/TABS/VISTAS para implementar las 5 vistas de sidebar.
 * Todo el resto (socket, chat, sesiones, tareas, voz, archivos) es idéntico.
 */

'use strict';

/* ══════════════════════════════════════════════════════════════════════════════
   1. ESTADO LOCAL + SOCKET
══════════════════════════════════════════════════════════════════════════════ */

const socket      = io();
let mySocketId    = null;
let sesionActiva  = null;
let vozActiva     = false;
let archivoNombre = null;
let enviando      = false;
const STORAGE_KEY = 'zelic_sesion_id';

/* ── Helper fetch con X-Socket-ID ── */
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Socket-ID': mySocketId || '' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return res.json();
}

async function apiForm(path, formData) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'X-Socket-ID': mySocketId || '' },
    body: formData,
  });
  return res.json();
}

/* ══════════════════════════════════════════════════════════════════════════════
   2. PARTÍCULAS — conservado exacto
══════════════════════════════════════════════════════════════════════════════ */

const cv = document.getElementById('gc');
const cx = cv.getContext('2d');
cv.width  = cv.offsetWidth  || 800;
cv.height = cv.offsetHeight || 660;
const PTS = [];
for (let i = 0; i < 30; i++) {
  PTS.push({
    x: Math.random() * cv.width, y: Math.random() * cv.height,
    r: Math.random() * .8 + .15,
    dx: (Math.random() - .5) * .13, dy: (Math.random() - .5) * .13,
    a: Math.random() * .22 + .06,
    h: Math.random() < .65 ? 222 : 264,
  });
}
function drawC() {
  cx.clearRect(0, 0, cv.width, cv.height);
  const g = cx.createRadialGradient(cv.width/2,0,0,cv.width/2,0,cv.width*.55);
  g.addColorStop(0,'rgba(45,90,240,.04)'); g.addColorStop(1,'transparent');
  cx.fillStyle=g; cx.fillRect(0,0,cv.width,cv.height);
  PTS.forEach(p => {
    p.x+=p.dx; p.y+=p.dy;
    if(p.x<0)p.x=cv.width; if(p.x>cv.width)p.x=0;
    if(p.y<0)p.y=cv.height; if(p.y>cv.height)p.y=0;
    cx.beginPath(); cx.arc(p.x,p.y,p.r,0,Math.PI*2);
    cx.fillStyle=`hsla(${p.h},72%,72%,${p.a})`; cx.fill();
  });
  requestAnimationFrame(drawC);
}
drawC();

/* ══════════════════════════════════════════════════════════════════════════════
   3. RELOJ — conservado exacto
══════════════════════════════════════════════════════════════════════════════ */

const clk = document.getElementById('clk');
function tick() {
  clk.textContent = new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit',hour12:false});
}
tick(); setInterval(tick, 9000);

/* ══════════════════════════════════════════════════════════════════════════════
   4. VISTAS + NAV + TABS
   5 vistas en el panel central: home | chat | workspace | files | settings
   El sidebar controla qué vista se muestra.
   Los tabs del topbar son accesos rápidos a home/chats/files.
══════════════════════════════════════════════════════════════════════════════ */

// Mapa: data-ni → id del panel central
const VISTA_MAP = {
  home:     'pv-home',
  chat:     'pv-chat',
  voz:      'pv-chat',      // voz usa el mismo thread de chat
  files:    'pv-files',
  settings: 'pv-settings',
  workspace:'pv-workspace',
};

// Mapa: data-tab → data-ni equivalente
const TAB_MAP = {
  home:  'home',
  chats: 'chat',
  files: 'files',
};

let vistaActual = 'home';

/**
 * activarVista(ni)
 * Cambia la vista del panel central y actualiza el estado del sidebar y topbar.
 * ni: 'home' | 'chat' | 'voz' | 'files' | 'settings' | 'workspace'
 */
function activarVista(ni) {
  vistaActual = ni;

  // Ocultar todas las vistas
  document.querySelectorAll('.pv').forEach(p => p.style.display = 'none');

  // Mostrar la vista correspondiente
  const pvId = VISTA_MAP[ni] || 'pv-home';
  const pv = document.getElementById(pvId);
  if (pv) pv.style.display = 'flex';

  // Actualizar sidebar activo
  document.querySelectorAll('.ni').forEach(n => n.classList.remove('on'));
  const niEl = document.querySelector(`[data-ni="${ni}"]`);
  if (niEl) niEl.classList.add('on');

  // Actualizar tab del topbar si corresponde
  document.querySelectorAll('.tb-tab').forEach(t => t.classList.remove('on'));
  const tabEquiv = { home:'home', chat:'chats', voz:'chats', files:'files' }[ni];
  if (tabEquiv) {
    const tabEl = document.querySelector(`[data-tab="${tabEquiv}"]`);
    if (tabEl) tabEl.classList.add('on');
  }

  // Acciones por vista
  if (ni === 'workspace') cargarSesionesWorkspace();
  if (ni === 'settings')  cargarSettings();
  if (ni === 'voz' && !vozActiva) iniciarVoz();
}

/* Sidebar — click en íconos */
document.querySelectorAll('.ni').forEach(b => {
  b.addEventListener('click', () => {
    const ni = b.dataset.ni;
    // Si clickea chat y no hay sesión → crear una
    if (ni === 'chat' && !sesionActiva) {
      nuevaConversacion().then(() => activarVista('chat'));
      return;
    }
    activarVista(ni);
  });
});

/* Tabs del topbar */
document.querySelectorAll('.tb-tab').forEach(t => {
  t.addEventListener('click', () => {
    const tab = t.dataset.tab;
    const ni  = TAB_MAP[tab] || 'home';
    activarVista(ni);
  });
});

/**
 * iniciarDesdeHome()
 * Crea nueva conversación y cambia a la vista chat.
 * Llamado desde los botones del home y del panel derecho.
 */
async function iniciarDesdeHome() {
  await nuevaConversacion();
  activarVista('chat');
}

/**
 * activarTab(tab) — helper para llamadas externas (e.g. desde HTML onclick)
 */
function activarTab(tab) {
  activarVista(TAB_MAP[tab] || tab);
}

/* ══════════════════════════════════════════════════════════════════════════════
   5. WAVE BARS — conservado exacto
══════════════════════════════════════════════════════════════════════════════ */

const waveEl    = document.getElementById('vf-wave');
const BAR_COUNT = 10;
const bars=[], targets=[], current=[], speeds=[];
for (let i=0;i<BAR_COUNT;i++){
  const b=document.createElement('div'); b.className='vfb';
  waveEl.appendChild(b); bars.push(b);
  targets[i]=Math.random()*20+4; current[i]=Math.random()*20+4;
  speeds[i]=Math.random()*.06+.02;
}
let animatingWave=false;
function animateBars(){
  if(!animatingWave) return;
  bars.forEach((b,i)=>{
    current[i]+=(targets[i]-current[i])*speeds[i];
    if(Math.random()<.015) targets[i]=Math.random()*22+4;
    b.style.height=current[i]+'px';
  });
  requestAnimationFrame(animateBars);
}

/* ══════════════════════════════════════════════════════════════════════════════
   6. CHAT — addMsg, send, typing
══════════════════════════════════════════════════════════════════════════════ */

const chatEl = document.getElementById('chat');
const thread = document.getElementById('thread');
const trow   = document.getElementById('trow');
const tlbl   = document.getElementById('tlbl');
const inp    = document.getElementById('inp');
const sb     = document.getElementById('sb');
const mdl    = document.getElementById('mdl');
const rpst   = document.getElementById('rpst');
const ctxi   = document.getElementById('ctx-i');
const ctxm   = document.getElementById('ctx-m');

const CHECK_SVG = '<svg width="8" height="6" viewBox="0 0 8 6" fill="none"><path d="M1 3l2 2 4-4" stroke="#4d78f8" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function addMsg(role, html, tag=null) {
  const welcome = document.getElementById('msg-welcome');
  if (welcome) welcome.remove();

  if (role === 'sys') {
    const row=document.createElement('div'); row.className='msg sys';
    const mt=document.createElement('div'); mt.className='mt'; mt.textContent=html;
    row.appendChild(mt); thread.insertBefore(row,trow);
    chatEl.scrollTop=99999; return;
  }

  const row=document.createElement('div');
  row.className='msg'+(role==='u'?' u':'');
  const mb=document.createElement('div'); mb.className='mb';
  const mw=document.createElement('div'); mw.className='mw';
  const mt=document.createElement('div'); mt.className='mt'; mt.innerHTML=html;
  const moduleTag=tag||(role==='u'?'':'chat');

  if(role==='u'){
    mw.style.justifyContent='flex-end'; mw.textContent='tú';
    mb.appendChild(mw); mb.appendChild(mt);
    const av=document.createElement('div'); av.className='av u'; av.textContent='S';
    row.appendChild(mb); row.appendChild(av);
  } else {
    mw.innerHTML=`zelic <span class="mw-tag">// ${moduleTag}</span>`;
    mb.appendChild(mw); mb.appendChild(mt);
    const av=document.createElement('div'); av.className='av z';
    row.appendChild(av); row.appendChild(mb);
  }
  thread.insertBefore(row,trow);
  chatEl.scrollTop=99999;
}

function mostrarTyping(label='procesando') {
  tlbl.textContent=label; trow.style.display='flex'; chatEl.scrollTop=99999;
}
function quitarTyping() { trow.style.display='none'; }

function updateContext(intencion) {
  if(ctxi) ctxi.textContent=intencion||'—';
  if(ctxm) ctxm.textContent=intencion||'—';
  // session en panel derecho
  const ctxSes=document.getElementById('ctx-session');
  if(ctxSes && sesionActiva) ctxSes.textContent=`#${sesionActiva}`;
}

async function send() {
  if(enviando) return;
  const texto=inp.value.trim(); if(!texto) return;

  if(!sesionActiva){
    await nuevaConversacion();
    if(!sesionActiva) return;
  }
  // Auto-switch a vista chat cuando el usuario envía
  if(vistaActual !== 'chat' && vistaActual !== 'voz') activarVista('chat');

  enviando=true;
  sb.style.opacity='.4'; sb.style.pointerEvents='none';
  inp.value=''; inp.style.height='auto';
  addMsg('u', escapeHtml(texto));
  mostrarTyping('procesando');
  if(rpst) rpst.textContent='thinking';
  if(mdl) mdl.textContent='gemini-2.5-flash · thinking';

  try {
    const data=await api('POST','/api/chat',{texto});
    quitarTyping();
    if(!data.ok){
      addMsg('z',`<span style="color:#ff6666">${escapeHtml(data.error||'Error desconocido')}</span>`,'error');
    } else {
      const{respuesta,intencion,nombre_generado}=data.data;
      addMsg('z',escapeHtml(respuesta),intencion);
      updateContext(intencion);
      if(intencion==='tareas') cargarTareas();
      if(nombre_generado) actualizarNombreSesion(sesionActiva,nombre_generado);
    }
  } catch(err) {
    quitarTyping();
    addMsg('z',`<span style="color:#ff6666">Error de conexión: ${escapeHtml(String(err))}</span>`,'error');
  } finally {
    enviando=false;
    sb.style.opacity='1'; sb.style.pointerEvents='auto';
    if(rpst) rpst.textContent='online';
    if(mdl) mdl.textContent='gemini-2.5-flash';
    inp.focus();
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function limpiarThread() {
  Array.from(thread.children).forEach(c=>{ if(c.id!=='trow') c.remove(); });
  quitarTyping();
  thread.appendChild(trow);
}

sb.addEventListener('click', send);
inp.addEventListener('keydown', e=>{
  if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); }
});
inp.addEventListener('input', ()=>{
  inp.style.height='auto';
  inp.style.height=Math.min(inp.scrollHeight,96)+'px';
});
document.addEventListener('keydown', e=>{
  if(e.ctrlKey&&e.key==='z'){ e.preventDefault(); toggleVoz(); }
});

/* ══════════════════════════════════════════════════════════════════════════════
   7. SESIONES — nueva, cargar, borrar, renombrar
══════════════════════════════════════════════════════════════════════════════ */

async function nuevaConversacion() {
  try {
    const data=await api('POST','/api/sesion/nueva');
    if(!data.ok){ console.error('[Sesión]',data.error); return; }
    sesionActiva=data.data.sesion_id;
    localStorage.setItem(STORAGE_KEY,sesionActiva);
    limpiarThread();
    updateContext('—');
    if(rpst) rpst.textContent='online';
  } catch(err){ console.error('[Sesión]',err); }
}

async function cargarSesion(sid) {
  try {
    const data=await api('POST',`/api/sesion/cargar/${sid}`);
    if(!data.ok){ console.error('[Sesión]',data.error); return; }
    sesionActiva=sid;
    localStorage.setItem(STORAGE_KEY,sid);
    limpiarThread();
    const{mensajes}=data.data;
    if(!mensajes||!mensajes.length){
      addMsg('sys','Esta conversación no tiene mensajes.');
    } else {
      const fecha=mensajes[0].ts?mensajes[0].ts.substring(0,10):'';
      if(fecha) addMsg('sys',`── ${fecha} ──`);
      mensajes.forEach(m=>{ addMsg(m.role==='user'?'u':'z', escapeHtml(m.texto)); });
    }
    updateContext('—');
    // Cambiar a vista chat
    activarVista('chat');
  } catch(err){ console.error('[Sesión]',err); }
}

async function eliminarSesion(sid, e) {
  e.stopPropagation();
  if(!confirm('¿Eliminar esta conversación?')) return;
  try {
    const data=await api('DELETE',`/api/sesion/${sid}`);
    if(data.ok){
      if(sid===sesionActiva){
        sesionActiva=null;
        localStorage.removeItem(STORAGE_KEY);
        limpiarThread(); updateContext('—');
      }
      cargarSesionesWorkspace();
    }
  } catch(err){ console.error('[Sesión]',err); }
}

async function renombrarSesion(sid, nombreActual, e) {
  e.stopPropagation();
  const nuevo=prompt('Nuevo nombre:',nombreActual||'');
  if(!nuevo||!nuevo.trim()) return;
  try {
    await api('PATCH',`/api/sesion/${sid}/nombre`,{nombre:nuevo.trim()});
    cargarSesionesWorkspace();
  } catch(err){ console.error('[Sesión]',err); }
}

function actualizarNombreSesion(sid, nombre) {
  // Actualizar en workspace si está visible
  const item=document.querySelector(`[data-ws-sid="${sid}"] .ws-item-title`);
  if(item) item.textContent=nombre;
}

/* ── cargarSesionesWorkspace — renderiza en #ws-sesiones-list (vista central) ── */
async function cargarSesionesWorkspace() {
  const list=document.getElementById('ws-sesiones-list');
  if(!list) return;
  try {
    const data=await api('GET','/api/sesiones');
    if(!data.ok){ list.innerHTML='<div class="rp-empty">Error cargando historial.</div>'; return; }
    const sesiones=data.data;
    if(!sesiones.length){
      list.innerHTML='<div class="rp-empty">Sin conversaciones.</div>'; return;
    }
    list.innerHTML='';
    sesiones.forEach(s=>{
      const display=s.nombre||`${(s.inicio||'').substring(5,10)} ${(s.inicio||'').substring(11,16)}`;
      const esActual=s.sid===sesionActiva;

      const item=document.createElement('div');
      item.className='ws-item'+(esActual?' activa':'');
      item.dataset.wsSid=s.sid;
      item.title='Click para cargar · Doble click para renombrar';

      const icon=document.createElement('div');
      icon.className='ws-item-icon';
      icon.innerHTML='<i class="ti ti-message-2"></i>';

      const body=document.createElement('div');
      body.className='ws-item-body';

      const title=document.createElement('div');
      title.className='ws-item-title'; title.textContent=display;

      const meta=document.createElement('div');
      meta.className='ws-item-meta';
      const msgs=s.total?`${s.total} msg${s.total!==1?'s':''}`:' nueva';
      const fecha=(s.inicio||'').substring(5,10);
      meta.innerHTML=`<span>${fecha}</span><span class="ws-item-msgs"><i class="ti ti-message" style="font-size:9px"></i> ${msgs}</span>`;

      body.appendChild(title); body.appendChild(meta);

      const del=document.createElement('div');
      del.className='ws-item-del';
      del.innerHTML='<i class="ti ti-trash" style="font-size:11px"></i>';
      del.title='Eliminar';
      del.addEventListener('click', ev=>eliminarSesion(s.sid,ev));

      item.appendChild(icon); item.appendChild(body); item.appendChild(del);
      item.addEventListener('click', ()=>cargarSesion(s.sid));
      item.addEventListener('dblclick', ev=>renombrarSesion(s.sid,display,ev));
      list.appendChild(item);
    });
  } catch(err){
    list.innerHTML='<div class="rp-empty">Error de conexión.</div>';
    console.error('[Sesiones]',err);
  }
}

/* ── cargarSettings ── */
async function cargarSettings() {
  const optSid=document.getElementById('opt-sid');
  const optCpu=document.getElementById('opt-cpu');
  const optRam=document.getElementById('opt-ram');
  if(optSid && sesionActiva) optSid.textContent=`#${sesionActiva}`;

  // Sesiones count
  try {
    const data=await api('GET','/api/sesiones');
    if(data.ok){
      const optChats=document.getElementById('opt-chats');
      if(optChats) optChats.textContent=data.data.length;
    }
  } catch(_){}

  // Sysinfo
  try {
    const data=await fetch('/api/sysinfo').then(r=>r.json());
    if(data.ok){
      if(optCpu) optCpu.textContent=data.data.cpu;
      if(optRam) optRam.textContent=data.data.ram;
    }
  } catch(_){}
}

/* ══════════════════════════════════════════════════════════════════════════════
   8. TAREAS
══════════════════════════════════════════════════════════════════════════════ */

async function cargarTareas() {
  const list=document.getElementById('tareas-list'); if(!list) return;
  try {
    const data=await api('GET','/api/tareas');
    if(!data.ok){ list.innerHTML='<div class="rp-empty">Error.</div>'; return; }
    const tareas=data.data;
    if(!tareas.length){ list.innerHTML='<div class="rp-empty">Sin tareas pendientes.</div>'; return; }
    list.innerHTML='';
    tareas.forEach(t=>{
      const row=document.createElement('div'); row.className='task'; row.dataset.tid=t.tid;
      const box=document.createElement('div'); box.className='tbox'; box.dataset.d='0';
      const tk=document.createElement('span'); tk.className='tk'; tk.textContent=t.titulo;
      row.appendChild(box); row.appendChild(tk);
      row.addEventListener('click',()=>completarTarea(t.tid,row));
      list.appendChild(row);
    });
  } catch(err){ list.innerHTML='<div class="rp-empty">Error de conexión.</div>'; }
}

async function completarTarea(tid, row) {
  const box=row.querySelector('.tbox'); const tk=row.querySelector('.tk');
  box.classList.add('done'); box.innerHTML=CHECK_SVG; tk.classList.add('done');
  try {
    await api('POST',`/api/tareas/completar/${tid}`);
    setTimeout(cargarTareas,600);
  } catch(err){
    box.classList.remove('done'); box.innerHTML=''; tk.classList.remove('done');
  }
}

/* ══════════════════════════════════════════════════════════════════════════════
   9. RECORDATORIOS + TOAST
══════════════════════════════════════════════════════════════════════════════ */

async function cargarRecordatorios() {
  const list=document.getElementById('recordatorios-list'); if(!list) return;
  try {
    const data=await api('GET','/api/recordatorios');
    if(!data.ok){ list.innerHTML='<div class="rp-empty">Error.</div>'; return; }
    const recs=data.data;
    if(!recs.length){ list.innerHTML='<div class="rp-empty">Sin recordatorios.</div>'; return; }
    list.innerHTML='';
    recs.forEach(r=>{
      const row=document.createElement('div'); row.className='task';
      const box=document.createElement('div'); box.className='tbox';
      const tk=document.createElement('span'); tk.className='tk';
      tk.textContent=`${r.titulo}${r.hora?' · '+r.hora:''}`;
      row.appendChild(box); row.appendChild(tk); list.appendChild(row);
    });
  } catch(err){ console.error('[Recordatorios]',err); }
}

let _toastTimer=null;
function mostrarToast(titulo) {
  const toast=document.getElementById('toast');
  const toastMsg=document.getElementById('toast-msg');
  toastMsg.textContent=titulo;
  toast.classList.add('show');
  if(sesionActiva) addMsg('z',`⏰ Recordatorio: ${escapeHtml(titulo)}`,'sistema');
  if(_toastTimer) clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>toast.classList.remove('show'),6000);
}
document.getElementById('toast-close').addEventListener('click',()=>{
  document.getElementById('toast').classList.remove('show');
  if(_toastTimer){clearTimeout(_toastTimer);_toastTimer=null;}
});

/* ══════════════════════════════════════════════════════════════════════════════
   10. VOZ
══════════════════════════════════════════════════════════════════════════════ */

const micBtn   = document.getElementById('mic');
const vfEl     = document.getElementById('vf');
const vfxEl    = document.getElementById('vfx');
const vfProcEl = document.getElementById('vf-proc');
const vfAnalEl = document.getElementById('vf-analyzing');

const VOZ_ESTADOS = {
  escuchando: {proc:'ESCUCHANDO',  sub:'habla cuando quieras'},
  procesando: {proc:'PROCESANDO',  sub:'analizando audio...'},
  hablando:   {proc:'RESPONDIENDO',sub:'generando respuesta...'},
  idle:       {proc:'EN ESPERA',   sub:'di "Zelic" para activar'},
};

function mostrarVozFloat() { vfEl.classList.add('show'); animatingWave=true; animateBars(); }
function ocultarVozFloat()  { vfEl.classList.remove('show'); animatingWave=false; }

async function toggleVoz() { vozActiva ? detenerVoz() : iniciarVoz(); }

async function iniciarVoz() {
  if(vozActiva) return;
  if(!sesionActiva){ await nuevaConversacion(); if(!sesionActiva) return; }
  vozActiva=true;
  micBtn.classList.add('mic-on');
  mostrarVozFloat();
  setVozEstado('escuchando');
  socket.emit('voz_iniciar');
}

function detenerVoz() {
  if(!vozActiva) return;
  vozActiva=false;
  micBtn.classList.remove('mic-on');
  ocultarVozFloat();
  socket.emit('voz_detener');
  // Volver a chat si estábamos en vista voz
  if(vistaActual==='voz') activarVista('chat');
}

function setVozEstado(estado) {
  const s=VOZ_ESTADOS[estado]||VOZ_ESTADOS.idle;
  vfProcEl.textContent=s.proc; vfAnalEl.textContent=s.sub;
  const rpVoice=document.getElementById('rp-voice');
  if(rpVoice){ rpVoice.textContent=estado==='idle'?'ready':estado; rpVoice.style.color=estado==='idle'?'':'var(--cyan)'; }
}

micBtn.addEventListener('click', toggleVoz);
vfxEl.addEventListener('click', detenerVoz);

socket.on('voz_texto', ({rol,texto})=>{
  const role=rol==='usuario'?'u':'z';
  addMsg(role, escapeHtml(texto),'voz');
});
socket.on('voz_estado', ({estado})=>{
  setVozEstado(estado);
  if(estado==='idle'&&vozActiva){ vozActiva=false; micBtn.classList.remove('mic-on'); ocultarVozFloat(); }
});
socket.on('recordatorio', ({titulo})=>{ mostrarToast(titulo); cargarRecordatorios(); });
socket.on('chat_nombre', ({sesion_id,nombre})=>{
  actualizarNombreSesion(sesion_id,nombre);
  if(vistaActual==='workspace') cargarSesionesWorkspace();
});

function capturaDesdeVoz() { if(!vozActiva) return; socket.emit('voz_captura'); }

/* ══════════════════════════════════════════════════════════════════════════════
   11. ARCHIVO ADJUNTO — conservado exacto
══════════════════════════════════════════════════════════════════════════════ */

const fileInput   = document.getElementById('file-input');
const btnAdjuntar = document.getElementById('btn-adjuntar');
const adjuntoInfo = document.getElementById('adjunto-info');

btnAdjuntar.addEventListener('click', ()=>fileInput.click());

fileInput.addEventListener('change', async ()=>{
  const file=fileInput.files[0]; if(!file) return;
  if(!sesionActiva){ await nuevaConversacion(); if(!sesionActiva){fileInput.value='';return;} }
  const form=new FormData(); form.append('archivo',file);
  try {
    const data=await apiForm('/api/archivo',form);
    if(data.ok){
      archivoNombre=data.data.nombre;
      mostrarAdjuntoBadge(archivoNombre);
      addMsg('sys',`📎 Archivo adjunto: ${archivoNombre}`);
      // Añadir a la vista files
      agregarArchivoAVista(archivoNombre);
    } else { addMsg('sys',`❌ Error al adjuntar: ${data.error}`); }
  } catch(err){ addMsg('sys','❌ Error de conexión al subir archivo.'); }
  fileInput.value='';
});

function mostrarAdjuntoBadge(nombre) {
  if(!adjuntoInfo) return;
  adjuntoInfo.innerHTML=`<span class="adjunto-badge">📎 ${escapeHtml(nombre)}<span class="adj-rm" id="adj-rm-btn" title="Quitar">✕</span></span>`;
  adjuntoInfo.classList.add('visible');
  document.getElementById('adj-rm-btn').addEventListener('click', quitarAdjunto);
}

async function quitarAdjunto() {
  archivoNombre=null;
  if(adjuntoInfo){ adjuntoInfo.innerHTML=''; adjuntoInfo.classList.remove('visible'); }
  try { await api('DELETE','/api/archivo'); } catch(_){}
}

function agregarArchivoAVista(nombre) {
  const grid=document.getElementById('files-grid'); if(!grid) return;
  const empty=grid.querySelector('.files-empty'); if(empty) empty.remove();
  const ext=nombre.split('.').pop().toLowerCase();
  const iconMap={pdf:'ti-file-type-pdf',jpg:'ti-photo',jpeg:'ti-photo',png:'ti-photo',
                  txt:'ti-file-text',md:'ti-markdown',py:'ti-brand-python',
                  js:'ti-brand-javascript',csv:'ti-table',json:'ti-braces'};
  const icon=iconMap[ext]||'ti-file';
  const card=document.createElement('div'); card.className='file-card';
  card.innerHTML=`<div class="file-icon"><i class="ti ${icon}"></i></div>
    <div><div class="file-name">${escapeHtml(nombre)}</div>
    <div class="file-meta">adjunto · sesión #${sesionActiva||'—'}</div></div>`;
  grid.appendChild(card);
}

/* ══════════════════════════════════════════════════════════════════════════════
   12. SYSINFO
══════════════════════════════════════════════════════════════════════════════ */

async function cargarSysinfo() {
  try {
    const data=await fetch('/api/sysinfo').then(r=>r.json());
    if(data.ok){
      const rpc=document.getElementById('rpc'); const rpr=document.getElementById('rpr');
      if(rpc) rpc.textContent=data.data.cpu;
      if(rpr) rpr.textContent=data.data.ram;
    }
  } catch(_){}
}
setInterval(cargarSysinfo,4500);

/* ══════════════════════════════════════════════════════════════════════════════
   13. SOCKETIO — conexión y reconexión
══════════════════════════════════════════════════════════════════════════════ */

socket.on('connect', async ()=>{
  mySocketId=socket.id;
  console.log('[SocketIO] Conectado:',mySocketId);
  const savedSid=localStorage.getItem(STORAGE_KEY);
  if(savedSid){
    const sid=parseInt(savedSid,10);
    if(!isNaN(sid)){
      try {
        const data=await api('POST',`/api/sesion/cargar/${sid}`);
        if(data.ok){
          sesionActiva=sid;
          if(thread.children.length<=1) await cargarSesion(sid);
        } else { localStorage.removeItem(STORAGE_KEY); sesionActiva=null; }
      } catch(_){ sesionActiva=null; }
    }
  }
});

socket.on('disconnect', ()=>{
  if(vozActiva){ vozActiva=false; micBtn.classList.remove('mic-on'); ocultarVozFloat(); }
});
socket.on('connect_error', err=>console.error('[SocketIO]',err.message));

/* ══════════════════════════════════════════════════════════════════════════════
   14. INICIALIZACIÓN
══════════════════════════════════════════════════════════════════════════════ */

(function init() {
  // Mostrar vista home por defecto
  activarVista('home');

  cargarTareas();
  cargarRecordatorios();
  cargarSysinfo();

  // Asegurar #adjunto-info en ig-meta
  const igMeta=document.querySelector('.ig-meta');
  if(igMeta && !document.getElementById('adjunto-info')){
    const div=document.createElement('div'); div.id='adjunto-info';
    igMeta.insertBefore(div,igMeta.firstChild);
  }
  console.log('[Zelic] Frontend inicializado.');
})();