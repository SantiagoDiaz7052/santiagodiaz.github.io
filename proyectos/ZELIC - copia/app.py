"""
app.py — Servidor principal de Zelic
Flask + Flask-SocketIO. Migración de ZelicApp (Tkinter) a web.

Estado por cliente: sesiones_activas[socket.sid]
Módulos core no modificados — solo importados.
"""

import threading
import time
import base64
import os
import io
import uuid
from datetime import datetime

from core.lector_web import leer_urls

from flask import Flask, request, jsonify, render_template, abort
from flask_socketio import SocketIO
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

# ── Módulos core (sin modificar) ───────────────────────────────────────────────
from google import genai
from CONFIG.config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    API_KEY,
    APP_DEBUG,
    APP_HOST,
    APP_PORT,
    APP_SECRET_KEY,
    CORS_ALLOWED_ORIGINS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
)
from memoria_simple import MemoriaSimple, PerfilUsuario
from orquestador import clasificar_intencion
from core import chat, imagen, documento, sistema
from core import tareas
from core import clima as clima_mod
from core import sistema_info as sysinfo_mod
from core import vision_pantalla
from core.voz import ModuloVoz
import database as db

# ── App Flask ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = APP_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=CORS_ALLOWED_ORIGINS)

# ── Globales compartidos (sin estado de sesión) ────────────────────────────────
client = genai.Client(api_key=API_KEY)
perfil = PerfilUsuario()

# ── Estado por cliente conectado ───────────────────────────────────────────────
# Clave: request.sid (socket ID de Flask-SocketIO)
sesiones_activas: dict[str, dict] = {}

# Lock global para proteger escrituras concurrentes sobre sesiones_activas
_lock = threading.Lock()

# ── Inicialización de tablas ───────────────────────────────────────────────────
db.inicializar()
tareas.inicializar_tablas()

# ── Directorio temporal para archivos adjuntos ─────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _extension_permitida(nombre: str) -> bool:
    return os.path.splitext(nombre)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _ruta_upload_unica(nombre: str) -> tuple[str, str]:
    seguro = secure_filename(nombre or "")
    if not seguro:
        seguro = "adjunto"

    base, ext = os.path.splitext(seguro)
    base = (base or "adjunto")[:80]
    ext = ext.lower()
    nombre_final = f"{base}_{uuid.uuid4().hex[:10]}{ext}"
    return nombre_final, os.path.join(UPLOAD_DIR, nombre_final)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_estado_cliente() -> dict:
    """
    Obtiene el dict de estado asociado al cliente que hace la request HTTP.
    El frontend envía su socket.id en el header X-Socket-ID en cada fetch.
    """
    sid = request.headers.get("X-Socket-ID")
    if not sid:
        abort(400, description="Missing X-Socket-ID header")
    estado = sesiones_activas.get(sid)
    if not estado:
        abort(404, description="Socket session not found. Reconnect and retry.")
    return estado


def _nueva_memoria(sesion_id: int) -> MemoriaSimple:
    """Crea una instancia de MemoriaSimple ligada a la sesión activa."""
    return MemoriaSimple(
        client=client,
        sesion_id=sesion_id,
        perfil=perfil,
        model="gemini-2.5-flash",
        max_mensajes=8,
        num_a_resumir=4,
    )


def _generar_nombre_chat(sesion_id: int, primer_mensaje: str, socket_sid: str):
    """
    Genera un nombre corto para la conversación usando Gemini.
    Corre en thread separado. Replica ZelicApp._generar_nombre_chat().
    Emite 'chat_nombre' al cliente cuando termina.
    """
    from google.genai import types as gtypes
    prompt = (
        f'Genera un nombre MUY corto (máximo 4 palabras) para una conversación '
        f'que empieza con: "{primer_mensaje}"\n'
        f'Responde SOLO con el nombre, sin comillas ni puntuación.'
    )
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[gtypes.Content(role="user", parts=[gtypes.Part(text=prompt)])]
        )
        nombre = resp.text.strip()[:40]
        db.actualizar_nombre_sesion(sesion_id, nombre)
        socketio.emit("chat_nombre", {"sesion_id": sesion_id, "nombre": nombre},
                      to=socket_sid)
    except Exception as e:
        print(f"[Nombre] Error generando nombre: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  LÓGICA DE PROCESAMIENTO (migrada de ZelicApp._procesar)
# ══════════════════════════════════════════════════════════════════════════════

def _procesar(texto: str, estado: dict, socket_sid: str) -> dict:
    """
    Núcleo de procesamiento de mensajes. Replica ZelicApp._procesar().
    Corre en thread separado. Devuelve dict con respuesta e intención.
    No modifica UI — eso lo hace el endpoint vía jsonify.
    """
    respuesta = "No entendí la solicitud."
    intencion = "chat"
    nombre_generado = None

    # ── Detectar y leer URLs antes de clasificar la intención ────────────────
    resultado_web = leer_urls(texto)
    contexto_web  = resultado_web["contexto_web"]   # "" si no hay URLs
    # ─────────────────────────────────────────────────────────────────────────

    try:
        intencion = clasificar_intencion(
            client, texto,
            ultimo_modulo=estado.get("ultimo_modulo", ""),
            hay_contexto_web=resultado_web["hay_urls"],
        )
        with _lock:
            estado["ultimo_modulo"] = intencion

        if intencion == "chat":
            memoria = estado.get("memoria")
            if memoria is None:
                return {"respuesta": "No hay sesión activa. Inicia una nueva conversación.",
                        "intencion": intencion}
            # Si hay contenido web, enriquecemos el mensaje antes de guardarlo
            texto_enriquecido = sistema.construir_prompt_con_web(texto, contexto_web)
            memoria.agregar("user", texto_enriquecido)
            respuesta = chat.responder(client, memoria)
            memoria.agregar("model", respuesta)

            with _lock:
                estado["total_msgs"] = estado.get("total_msgs", 0) + 1
                es_primer_msg = estado["total_msgs"] == 1

            if es_primer_msg:
                sesion_id = estado.get("sesion_id")
                threading.Thread(
                    target=_generar_nombre_chat,
                    args=(sesion_id, texto, socket_sid),
                    daemon=True
                ).start()

        elif intencion == "tareas":
            respuesta = tareas.procesar(client, texto)

        elif intencion == "vision":
            respuesta = vision_pantalla.analizar(client, texto)

        elif intencion == "clima":
            respuesta = clima_mod.responder(client, texto)

        elif intencion == "sistema_info":
            respuesta = sysinfo_mod.responder(client, texto)

        elif intencion == "imagen":
            sesion_id = estado.get("sesion_id")
            respuesta = imagen.generar(client, texto)
            if sesion_id:
                db.guardar_imagen(sesion_id, texto, imagen.ruta_imagen_generada())

        elif intencion == "documento":
            ruta = estado.get("archivo_adjunto")
            if not ruta:
                respuesta = "Primero adjunta un archivo con el botón ＋"
            else:
                nombre_archivo = ruta.replace("\\", "/").split("/")[-1]
                sesion_id = estado.get("sesion_id")
                respuesta = documento.analizar(client, ruta, texto)
                if sesion_id:
                    db.guardar_documento(sesion_id, nombre_archivo, respuesta)
                with _lock:
                    estado["archivo_adjunto"] = None

        elif intencion == "sistema":
            sesion_id = estado.get("sesion_id")
            respuesta = sistema.ejecutar(client, texto, contexto_web=contexto_web)
            if sesion_id:
                db.guardar_accion(sesion_id, texto)

    except Exception as e:
        respuesta = f"Ocurrió un error: {e}"
        print(f"[_procesar] Error: {e}")

    return {
        "respuesta": respuesta,
        "intencion": intencion,
        "sesion_id": estado.get("sesion_id"),
        "nombre_generado": nombre_generado,
    }


def _procesar_voz_captura(img_b64: str) -> str:
    """
    Analiza una captura de pantalla recibida como base64.
    Replica ZelicApp._procesar_voz() para el caso __CAPTURA__.
    """
    try:
        img_bytes = base64.b64decode(img_b64)
        return vision_pantalla._analizar_imagen(
            client, img_bytes,
            "Describe brevemente qué está haciendo el usuario.",
            "gemini-2.5-flash"
        )
    except Exception as e:
        return f"No pude analizar la pantalla: {e}"


def _on_texto_voz(datos: tuple, estado: dict, socket_sid: str):
    """
    Procesa transcripciones de voz en tiempo real.
    Replica ZelicApp._on_texto_voz().
    Guarda en DB y acumula en transcripciones_voz del estado del cliente.
    """
    if not isinstance(datos, tuple) or len(datos) != 2:
        return
    rol, texto = datos

    # Emitir al browser del cliente correcto
    socketio.emit("voz_texto", {"rol": rol, "texto": texto}, to=socket_sid)

    sesion_id = estado.get("sesion_id")
    if not sesion_id or not texto:
        return

    role_db = "user" if rol == "usuario" else "model"

    # Guardar en DB (voz.py no guarda — lo hacemos aquí)
    db.guardar_mensaje(sesion_id, role_db, texto)

    with _lock:
        estado["transcripciones_voz"].append((role_db, texto))

    if rol == "usuario":
        with _lock:
            estado["total_msgs"] = estado.get("total_msgs", 0) + 1
            es_primer_msg = estado["total_msgs"] == 1

        if es_primer_msg:
            threading.Thread(
                target=_generar_nombre_chat,
                args=(sesion_id, texto, socket_sid),
                daemon=True
            ).start()


def _cerrar_sesion_voz(estado: dict):
    """
    Vuelca transcripciones de voz a la memoria de sesión al cerrar voz.
    Replica ZelicApp._ventana_voz_cerrada().
    """
    memoria = estado.get("memoria")
    transcripciones = estado.get("transcripciones_voz", [])

    if memoria and transcripciones:
        for role_db, texto in transcripciones:
            memoria.memoria.append({"role": role_db, "text": texto})
            if len(memoria.memoria) > memoria.max_mensajes:
                memoria._comprimir()
        print(f"[Voz→Chat] {len(transcripciones)} transcripciones volcadas a memoria.")

    if transcripciones:
        try:
            memoria._detectar_datos_usuario_con_msgs(
                [{"role": r, "text": t} for r, t in transcripciones[-4:]]
            )
        except Exception as e:
            print(f"[Voz→Chat] Error detectando datos usuario: {e}")

    with _lock:
        estado["transcripciones_voz"] = []


# ══════════════════════════════════════════════════════════════════════════════
#  MONITOR DE RECORDATORIOS (reemplaza root.after(30000, ...))
# ══════════════════════════════════════════════════════════════════════════════

def _revisar_recordatorios():
    """Comprueba recordatorios vencidos y emite push al browser."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        for rid, titulo, fecha_hora in tareas.listar_recordatorios(solo_pendientes=True):
            if fecha_hora <= ahora:
                tareas.completar_recordatorio(rid)
                # Broadcast a todos los clientes conectados
                socketio.emit("recordatorio", {"titulo": titulo})
                print(f"[Monitor] Recordatorio disparado: {titulo}")
    except Exception as e:
        print(f"[Monitor] Error revisando recordatorios: {e}")


def _monitor_recordatorios():
    """
    Thread daemon que reemplaza root.after(30000, _revisar_recordatorios).
    Corre indefinidamente cada 30 segundos.
    """
    while True:
        time.sleep(30)
        _revisar_recordatorios()


# ══════════════════════════════════════════════════════════════════════════════
#  SOCKETIO — EVENTOS DE CONEXIÓN
# ══════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def handle_connect():
    """
    Crea el estado inicial del cliente al conectar.
    Siempre se inicializa completo para que ningún endpoint encuentre KeyError.
    """
    sid = request.sid
    with _lock:
        sesiones_activas[sid] = {
            "sesion_id":           None,
            "memoria":             None,
            "total_msgs":          0,
            "ultimo_modulo":       "",
            "archivo_adjunto":     None,
            "transcripciones_voz": [],
            "modulo_voz":          None,
        }
    print(f"[SocketIO] Cliente conectado: {sid}")


@socketio.on("disconnect")
def handle_disconnect():
    """
    Limpia el estado del cliente al desconectar.
    Para ModuloVoz con try/except para streams ya muertos.
    """
    sid = request.sid
    estado = sesiones_activas.get(sid, {})

    mod = estado.get("modulo_voz")
    if mod:
        try:
            mod.detener()
        except Exception as e:
            print(f"[SocketIO] Error deteniendo voz en disconnect: {e}")

    sesiones_activas.pop(sid, None)
    print(f"[SocketIO] Cliente desconectado: {sid}")


# ══════════════════════════════════════════════════════════════════════════════
#  SOCKETIO — EVENTOS DE VOZ
# ══════════════════════════════════════════════════════════════════════════════

@socketio.on("voz_iniciar")
def handle_voz_iniciar():
    """
    Arranca ModuloVoz para el cliente que lo solicita.
    Replica ZelicApp._abrir_ventana_voz() + VentanaVoz._iniciar_voz().
    Los callbacks emiten solo al sid correcto (clausura sobre sid).
    """
    sid = request.sid
    estado = sesiones_activas.get(sid)
    if not estado:
        return

    # Guard: no crear otra instancia si ya hay una activa
    if estado.get("modulo_voz") is not None:
        print(f"[Voz] ModuloVoz ya activo para {sid}, ignorando voz_iniciar.")
        return

    # Clausuras sobre sid para emitir solo al cliente correcto
    def cb_texto(datos: tuple):
        _on_texto_voz(datos, estado, sid)

    def cb_estado(estado_voz: str):
        socketio.emit("voz_estado", {"estado": estado_voz}, to=sid)

    def cb_apagar():
        socketio.emit("voz_estado", {"estado": "idle"}, to=sid)
        # Limpiar instancia
        with _lock:
            estado["modulo_voz"] = None

    # callback_memoria: agregar a la MemoriaSimple activa si existe
    memoria = estado.get("memoria")
    cb_memoria = memoria.agregar if memoria is not None else None

    mod = ModuloVoz(
        client=client,
        callback_texto=cb_texto,
        callback_estado=cb_estado,
        callback_apagar=cb_apagar,
        callback_memoria=cb_memoria,
    )

    with _lock:
        estado["modulo_voz"] = mod

    mod.iniciar()
    print(f"[Voz] ModuloVoz iniciado para {sid}")


@socketio.on("voz_detener")
def handle_voz_detener():
    """
    Detiene ModuloVoz y vuelca transcripciones a memoria.
    Replica ZelicApp._ventana_voz_cerrada().
    """
    sid = request.sid
    estado = sesiones_activas.get(sid)
    if not estado:
        return

    mod = estado.get("modulo_voz")
    if mod:
        try:
            mod.detener()
        except Exception as e:
            print(f"[Voz] Error deteniendo ModuloVoz: {e}")
        with _lock:
            estado["modulo_voz"] = None

    _cerrar_sesion_voz(estado)
    socketio.emit("voz_estado", {"estado": "idle"}, to=sid)
    print(f"[Voz] ModuloVoz detenido para {sid}")


@socketio.on("voz_captura")
def handle_voz_captura():
    """
    Captura la pantalla del servidor y la describe.
    Replica VentanaVoz._capturar_pantalla() vía SocketIO.
    """
    sid = request.sid
    estado = sesiones_activas.get(sid)
    if not estado:
        return

    def _hacer():
        try:
            import mss
            from PIL import Image

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                captura = sct.grab(monitor)
                img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")
                img = img.resize((1280, 720), Image.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=65)
                img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            respuesta = _procesar_voz_captura(img_b64)

            # Emitir respuesta al browser como mensaje de voz
            socketio.emit("voz_texto", {"rol": "zelic", "texto": f"👁 {respuesta}"}, to=sid)

            # Guardar en DB si hay sesión activa
            sesion_id = estado.get("sesion_id")
            if sesion_id and respuesta:
                db.guardar_mensaje(sesion_id, "model", f"👁 {respuesta}")

        except Exception as e:
            print(f"[voz_captura] Error: {e}")
            socketio.emit("voz_texto",
                          {"rol": "zelic", "texto": f"No pude capturar la pantalla: {e}"},
                          to=sid)

    threading.Thread(target=_hacer, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
#  RUTA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════════════════════════
#  API — SESIONES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/sesion/nueva", methods=["POST"])
def api_sesion_nueva():
    """
    Crea una nueva conversación.
    Replica ZelicApp._nueva_conversacion().
    """
    estado = get_estado_cliente()

    # Cerrar sesión anterior si existía
    sesion_id_anterior = estado.get("sesion_id")
    if sesion_id_anterior:
        total = estado.get("total_msgs", 0)
        if total == 0:
            db.eliminar_sesion(sesion_id_anterior)
        else:
            db.cerrar_sesion(sesion_id_anterior, total)

    # Nueva sesión en DB
    nuevo_sid = db.nueva_sesion()

    with _lock:
        estado["sesion_id"]           = nuevo_sid
        estado["memoria"]             = _nueva_memoria(nuevo_sid)
        estado["total_msgs"]          = 0
        estado["ultimo_modulo"]       = ""
        estado["archivo_adjunto"]     = None
        estado["transcripciones_voz"] = []

    return jsonify({"ok": True, "data": {"sesion_id": nuevo_sid}})


@app.route("/api/sesion/cargar/<int:sid>", methods=["POST"])
def api_sesion_cargar(sid: int):
    """
    Restaura una sesión existente desde DB.
    Replica ZelicApp._cargar_sesion(sid).
    """
    estado = get_estado_cliente()

    # Cerrar sesión anterior si había una distinta
    sesion_id_anterior = estado.get("sesion_id")
    if sesion_id_anterior and sesion_id_anterior != sid:
        total = estado.get("total_msgs", 0)
        if total == 0:
            db.eliminar_sesion(sesion_id_anterior)
        else:
            db.cerrar_sesion(sesion_id_anterior, total)

    with _lock:
        estado["sesion_id"]           = sid
        estado["total_msgs"]          = 999   # sesión existente — nunca eliminar
        estado["ultimo_modulo"]       = ""
        estado["archivo_adjunto"]     = None
        estado["transcripciones_voz"] = []
        estado["memoria"]             = _nueva_memoria(sid)

    # Obtener mensajes históricos para renderizar en el browser
    mensajes_db = db.obtener_mensajes_sesion(sid)
    mensajes = []
    if mensajes_db:
        for role, texto, ts in mensajes_db:
            mensajes.append({
                "role":  role,   # "user" | "model"
                "texto": texto,
                "ts":    ts,
            })

    return jsonify({"ok": True, "data": {"sesion_id": sid, "mensajes": mensajes}})


@app.route("/api/sesion/<int:sid>", methods=["DELETE"])
def api_sesion_eliminar(sid: int):
    """
    Elimina una sesión de DB.
    Replica ZelicApp._eliminar_chat(sid) → confirmar().
    """
    estado = get_estado_cliente()

    db.eliminar_sesion(sid)

    # Si era la sesión activa del cliente, limpiar su estado
    if estado.get("sesion_id") == sid:
        with _lock:
            estado["sesion_id"]     = None
            estado["memoria"]       = None
            estado["total_msgs"]    = 0
            estado["ultimo_modulo"] = ""

    return jsonify({"ok": True, "data": {"eliminado": sid}})


@app.route("/api/sesion/<int:sid>/nombre", methods=["PATCH"])
def api_sesion_renombrar(sid: int):
    """
    Renombra una sesión.
    Replica ZelicApp._editar_nombre_chat().
    """
    # Este endpoint no necesita estado de cliente — es solo DB
    body = request.get_json(silent=True) or {}
    nombre = (body.get("nombre") or "").strip()[:40]
    if not nombre:
        return jsonify({"ok": False, "error": "nombre vacío"}), 400

    db.actualizar_nombre_sesion(sid, nombre)
    return jsonify({"ok": True, "data": {"sesion_id": sid, "nombre": nombre}})


@app.route("/api/sesiones", methods=["GET"])
def api_sesiones():
    """
    Lista las últimas 15 sesiones.
    Replica ZelicApp._cargar_historial_sidebar() → db.obtener_sesiones()[:15].
    """
    sesiones_db = db.obtener_sesiones()
    sesiones = []
    for sid, inicio, total, nombre in sesiones_db[:15]:
        sesiones.append({
            "sid":    sid,
            "inicio": inicio,
            "total":  total,
            "nombre": nombre,
        })
    return jsonify({"ok": True, "data": sesiones})


@app.route("/api/mensajes/<int:sid>", methods=["GET"])
def api_mensajes(sid: int):
    """Devuelve los mensajes de una sesión específica."""
    mensajes_db = db.obtener_mensajes_sesion(sid)
    mensajes = []
    if mensajes_db:
        for role, texto, ts in mensajes_db:
            mensajes.append({"role": role, "texto": texto, "ts": ts})
    return jsonify({"ok": True, "data": mensajes})


# ══════════════════════════════════════════════════════════════════════════════
#  API — CHAT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Recibe un mensaje de texto y devuelve la respuesta de Zelic.
    Replica ZelicApp._enviar() + ZelicApp._procesar() en un endpoint.
    El procesamiento pesado corre en thread separado para no bloquear.
    """
    estado = get_estado_cliente()
    socket_sid = request.headers.get("X-Socket-ID")

    body = request.get_json(silent=True) or {}
    texto = (body.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "error": "texto vacío"}), 400

    if estado.get("sesion_id") is None:
        return jsonify({"ok": False, "error": "No hay sesión activa. Inicia una nueva conversación."}), 400

    # Procesar de forma síncrona (el frontend ya muestra el typing indicator)
    # El thread de Flask maneja la espera — no bloquea otros requests por socketio threading
    resultado = _procesar(texto, estado, socket_sid)

    return jsonify({"ok": True, "data": resultado})


# ══════════════════════════════════════════════════════════════════════════════
#  API — ARCHIVO ADJUNTO
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/archivo", methods=["POST"])
def api_archivo():
    """
    Recibe un archivo adjunto (multipart/form-data) y lo guarda en disco.
    Replica ZelicApp._adjuntar_archivo().
    El archivo queda en estado["archivo_adjunto"] para el próximo mensaje.
    """
    estado = get_estado_cliente()

    if "archivo" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió archivo"}), 400

    archivo = request.files["archivo"]
    nombre_original = archivo.filename or "adjunto"
    nombre, ruta = _ruta_upload_unica(nombre_original)

    if not _extension_permitida(nombre):
        permitidas = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        return jsonify({"ok": False, "error": f"Formato no soportado. Usa: {permitidas}"}), 400

    archivo.save(ruta)

    with _lock:
        estado["archivo_adjunto"] = ruta

    return jsonify({"ok": True, "data": {"nombre": nombre, "ruta": ruta}})


@app.route("/api/archivo", methods=["DELETE"])
def api_archivo_limpiar():
    """Limpia el adjunto pendiente de la sesión activa."""
    estado = get_estado_cliente()
    ruta = estado.get("archivo_adjunto")

    if ruta:
        ruta_abs = os.path.abspath(ruta)
        upload_abs = os.path.abspath(UPLOAD_DIR)
        if ruta_abs.startswith(upload_abs + os.sep) and os.path.isfile(ruta_abs):
            try:
                os.remove(ruta_abs)
            except OSError:
                pass

    with _lock:
        estado["archivo_adjunto"] = None

    return jsonify({"ok": True, "data": {"archivo_adjunto": None}})


# ══════════════════════════════════════════════════════════════════════════════
#  API — TAREAS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tareas", methods=["GET"])
def api_tareas():
    """
    Lista tareas pendientes.
    Replica ZelicApp._cargar_tareas_sidebar() → tareas.listar_tareas().
    """
    pendientes = tareas.listar_tareas(solo_pendientes=True)
    resultado = []
    for tid, titulo, _, fecha_lim in pendientes:
        resultado.append({
            "tid":       tid,
            "titulo":    titulo,
            "fecha_lim": fecha_lim or "",
        })
    return jsonify({"ok": True, "data": resultado})


@app.route("/api/tareas/completar/<int:tid>", methods=["POST"])
def api_tarea_completar(tid: int):
    """
    Marca una tarea como completada.
    Replica ZelicApp._completar_tarea(tid).
    """
    tareas.completar_tarea(tid)
    return jsonify({"ok": True, "data": {"completada": tid}})


# ══════════════════════════════════════════════════════════════════════════════
#  API — RECORDATORIOS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/recordatorios", methods=["GET"])
def api_recordatorios():
    """
    Lista recordatorios pendientes.
    Replica ZelicApp._cargar_recordatorios_sidebar().
    """
    pendientes = tareas.listar_recordatorios(solo_pendientes=True)
    resultado = []
    for rid, titulo, fecha_hora in pendientes:
        hora = fecha_hora[11:16] if len(fecha_hora) > 10 else fecha_hora
        resultado.append({
            "rid":        rid,
            "titulo":     titulo,
            "fecha_hora": fecha_hora,
            "hora":       hora,
        })
    return jsonify({"ok": True, "data": resultado})


# ══════════════════════════════════════════════════════════════════════════════
#  API — CAPTURA DE PANTALLA
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/captura", methods=["POST"])
def api_captura():
    """
    Captura la pantalla del servidor y la analiza con vision_pantalla.
    Disponible también como endpoint HTTP además del evento SocketIO voz_captura.
    """
    estado = get_estado_cliente()

    result_holder = {}
    done = threading.Event()

    def _hacer():
        try:
            import mss
            from PIL import Image

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                captura = sct.grab(monitor)
                img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")
                img = img.resize((1280, 720), Image.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=65)
                img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            result_holder["respuesta"] = _procesar_voz_captura(img_b64)
        except Exception as e:
            result_holder["respuesta"] = f"No pude capturar la pantalla: {e}"
        finally:
            done.set()

    threading.Thread(target=_hacer, daemon=True).start()
    done.wait(timeout=30)

    return jsonify({"ok": True, "data": {"respuesta": result_holder.get("respuesta", "")}})


# ══════════════════════════════════════════════════════════════════════════════
#  API — SYSINFO (para panel derecho Neural)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/sysinfo", methods=["GET"])
def api_sysinfo():
    """
    Devuelve CPU y RAM actuales para actualizar #rpc y #rpr en el panel derecho.
    Reemplaza el setInterval con valores random del HTML demo.
    """
    try:
        import psutil
        cpu = f"{psutil.cpu_percent(interval=0.1):.0f}%"
        ram_gb = psutil.virtual_memory().used / (1024 ** 3)
        ram = f"{ram_gb:.1f} gb"
    except ImportError:
        # psutil no instalado — fallback a valores estáticos
        cpu = "—"
        ram = "—"
    except Exception:
        cpu = "—"
        ram = "—"

    return jsonify({"ok": True, "data": {"cpu": cpu, "ram": ram}})


# ══════════════════════════════════════════════════════════════════════════════
#  MANEJO DE ERRORES
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"ok": False, "error": str(e.description)}), 400


@app.errorhandler(RequestEntityTooLarge)
def request_entity_too_large(e):
    return jsonify({"ok": False, "error": f"Archivo demasiado grande. Máximo {MAX_UPLOAD_MB} MB."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": str(e.description)}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"ok": False, "error": "Error interno del servidor"}), 500


# ══════════════════════════════════════════════════════════════════════════════
#  ARRANQUE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Lanzar monitor de recordatorios (reemplaza root.after(30000, ...))
    threading.Thread(target=_monitor_recordatorios, daemon=True).start()
    print("[Zelic] Monitor de recordatorios iniciado.")
    print(f"[Zelic] Servidor arrancando en http://{APP_HOST}:{APP_PORT}")

    socketio.run(app, host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
