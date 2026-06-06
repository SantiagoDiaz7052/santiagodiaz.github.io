"""
core/tareas.py — Módulo de tareas y recordatorios para Zelic
Zelic interpreta el mensaje del usuario y decide qué acción tomar.
"""

from google import genai
from google.genai import types
import sqlite3                      ### libreria de python para hacer base de datos
import os                           ### interacturar con el sistema
from datetime import datetime       ### tiempo

from CONFIG.config import PERSONALIDAD_COMPACTA_ZELIC   ### personalidad

DB_PATH = "data/zelic.db"


# ── Base de datos ──────────────────────────────────────────────────────────────

#crea las tablas con la info necesaria ccomo, id de la conversacion, titulo, descripcion, etc
def inicializar_tablas():
    """Crea las tablas de tareas y recordatorios si no existen."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS tareas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo      TEXT NOT NULL,
            descripcion TEXT,
            completada  INTEGER DEFAULT 0,
            fecha_crear TEXT NOT NULL,
            fecha_limite TEXT
        );

        CREATE TABLE IF NOT EXISTS recordatorios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo      TEXT NOT NULL,
            fecha_hora  TEXT NOT NULL,         -- YYYY-MM-DD HH:MM
            completado  INTEGER DEFAULT 0,
            fecha_crear TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _conectar():
    os.makedirs("data", exist_ok=True)
    return sqlite3.connect(DB_PATH)


# ── Operaciones de tareas ──────────────────────────────────────────────────────
## simplñemente agrega es para agregar las tareas o recordatorios
def agregar_tarea(titulo: str, descripcion: str = "", fecha_limite: str = "") -> int:
    conn = _conectar()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO tareas (titulo, descripcion, fecha_crear, fecha_limite) VALUES (?,?,?,?)",
        (titulo, descripcion, _ahora(), fecha_limite)
    )
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    return tid

## si se completo la tarea la marca como colpleta
def completar_tarea(tarea_id: int):
    conn = _conectar()
    conn.execute("UPDATE tareas SET completada=1 WHERE id=?", (tarea_id,))
    conn.commit()
    conn.close()

# si ya esta completa una tarea la borra
def eliminar_tarea(tarea_id: int):
    conn = _conectar()
    conn.execute("DELETE FROM tareas WHERE id=?", (tarea_id,))
    conn.commit()
    conn.close()

## lsita solo tareas pendientes
def listar_tareas(solo_pendientes: bool = True) -> list:
    conn = _conectar()
    cur  = conn.cursor()
    if solo_pendientes:
        cur.execute("SELECT id, titulo, descripcion, fecha_limite FROM tareas WHERE completada=0 ORDER BY id ASC")
    else:
        cur.execute("SELECT id, titulo, descripcion, fecha_limite, completada FROM tareas ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows


# ── Operaciones de recordatorios ───────────────────────────────────────────────

## sirve para agrefar recordatorios
def agregar_recordatorio(titulo: str, fecha_hora: str) -> int:
    conn = _conectar()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO recordatorios (titulo, fecha_hora, fecha_crear) VALUES (?,?,?)",
        (titulo, fecha_hora, _ahora())
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid

### mira los recordatorios
def listar_recordatorios(solo_pendientes: bool = True) -> list:
    conn = _conectar()
    cur  = conn.cursor()
    if solo_pendientes:
        cur.execute(
            "SELECT id, titulo, fecha_hora FROM recordatorios WHERE completado=0 ORDER BY fecha_hora ASC"
        )
    else:
        cur.execute("SELECT id, titulo, fecha_hora, completado FROM recordatorios ORDER BY fecha_hora DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

## los marca completados
def completar_recordatorio(rid: int):
    conn = _conectar()
    conn.execute("UPDATE recordatorios SET completado=1 WHERE id=?", (rid,))
    conn.commit()
    conn.close()


# ── Responder con Zelic ────────────────────────────────────────────────────────

### reglas de respuesta y personalidad de zelic, en cuanto a las tareas
PROMPT_TAREAS = """

Fecha y hora actual: {fecha_hora_actual}

Tareas pendientes actuales:
{tareas}

Recordatorios pendientes actuales:
{recordatorios}

Mensaje del usuario: "{mensaje}"

Analiza el mensaje y responde en JSON con este formato exacto (sin markdown, sin texto extra):
{{
  "accion": "agregar_tarea" | "completar_tarea" | "eliminar_tarea" | "agregar_recordatorio" | "completar_recordatorio" | "listar_tareas" | "listar_recordatorios" | "listar_todo" | "ninguna",
  "titulo": "texto de la tarea o recordatorio (si aplica)",
  "descripcion": "descripción adicional (opcional, puede ser vacío)",
  "fecha_hora": "YYYY-MM-DD HH:MM (solo para recordatorios, puede ser vacío)",
  "fecha_limite": "YYYY-MM-DD (solo para tareas con fecha límite, puede ser vacío)",
  "id": 0,
  "respuesta": "respuesta de Zelic con su personalidad al usuario"
}}

Reglas:
- Si el usuario dice 'hecho', 'listo', 'terminé' + nombre de tarea → completar_tarea
- Si menciona hora o fecha específica → agregar_recordatorio
- Si solo menciona una tarea sin hora → agregar_tarea
- Si pregunta qué tiene pendiente → listar_todo, y en "respuesta" lista TODAS las tareas y recordatorios pendientes de forma clara
- Para completar/eliminar, busca el id correcto en la lista de tareas/recordatorios
- Si no hay tareas pendientes, dilo con humor
- responde como zelic: {personalidad}
- Responde siempre en el mismo idioma del usuario
"""

## modelo a utilizar para analizar que accion corresponde

def procesar(client: genai.Client, mensaje: str, model: str = "gemini-2.5-flash") -> str:
    """
    Punto de entrada principal. Zelic interpreta el mensaje,
    ejecuta la acción correspondiente y devuelve una respuesta en lenguaje natural.
    """
    inicializar_tablas()

    # Construir contexto actual
    tareas        = listar_tareas(solo_pendientes=True)
    recordatorios = listar_recordatorios(solo_pendientes=True)

    tareas_txt = "\n".join(
        f"  [{t[0]}] {t[1]}" + (f" (límite: {t[3]})" if t[3] else "")
        for t in tareas
    ) or "  (sin tareas pendientes)"

    recordatorios_txt = "\n".join(
        f"  [{r[0]}] {r[1]} — {r[2]}"
        for r in recordatorios
    ) or "  (sin recordatorios pendientes)"
    
    #####################################################################################################3
    #### aqui la ia compara el prompt literal que se le da el promt vs el asigandado en variable
    prompt = PROMPT_TAREAS.format(
        personalidad = PERSONALIDAD_COMPACTA_ZELIC,
        fecha_hora_actual=_ahora(),
        tareas=tareas_txt,
        recordatorios=recordatorios_txt,
        mensaje=mensaje,
    )

    # Llamar a Gemini
    respuesta_raw = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
    )

    # Parsear JSON
    import json
    texto = respuesta_raw.text.strip()
    texto = texto.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        return "Entendí que quieres gestionar una tarea, pero no pude procesarlo bien. ¿Puedes repetirlo?"

    accion    = data.get("accion", "ninguna")
    titulo    = data.get("titulo", "")
    desc      = data.get("descripcion", "")
    fecha_hora = data.get("fecha_hora", "")
    fecha_lim = data.get("fecha_limite", "")
    item_id   = data.get("id", 0)
    respuesta = data.get("respuesta", "Listo.")

    # Ejecutar acción
    if accion == "agregar_tarea" and titulo:
        agregar_tarea(titulo, desc, fecha_lim)

    elif accion == "completar_tarea" and item_id:
        completar_tarea(item_id)

    elif accion == "eliminar_tarea" and item_id:
        eliminar_tarea(item_id)

    elif accion == "agregar_recordatorio" and titulo and fecha_hora:
        agregar_recordatorio(titulo, fecha_hora)

    elif accion == "completar_recordatorio" and item_id:
        completar_recordatorio(item_id)

    elif accion in ("listar_tareas", "listar_recordatorios", "listar_todo"):
        # La respuesta ya viene formateada desde el prompt
        pass

    return respuesta


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")