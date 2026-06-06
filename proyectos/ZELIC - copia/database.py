import sqlite3
import os
from datetime import datetime

DB_PATH = "data/zelic.db"


def conectar():
    """Crea conexión a la base de datos."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # escrituras más rápidas
    conn.execute("PRAGMA synchronous=NORMAL") # sin perder datos, más veloz
    return conn


def inicializar():
    """Crea todas las tablas si no existen. Llamar una vez al arrancar Zelic."""
    conn = conectar()
    cur = conn.cursor()

    cur.executescript("""
        -- Historial de chat
        CREATE TABLE IF NOT EXISTS conversaciones (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id INTEGER NOT NULL,
            role      TEXT NOT NULL,
            mensaje   TEXT NOT NULL,
            fecha     TEXT NOT NULL
        );

        -- Imágenes generadas
        CREATE TABLE IF NOT EXISTS imagenes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id INTEGER,
            prompt    TEXT NOT NULL,
            ruta      TEXT,
            fecha     TEXT NOT NULL
        );

        -- Documentos analizados
        CREATE TABLE IF NOT EXISTS documentos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id INTEGER,
            nombre    TEXT NOT NULL,
            resumen   TEXT,
            fecha     TEXT NOT NULL
        );

        -- Acciones del sistema
        CREATE TABLE IF NOT EXISTS acciones (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id INTEGER,
            accion    TEXT NOT NULL,
            fecha     TEXT NOT NULL
        );

        -- Sesiones de uso  (resumen_memoria: resumen comprimido de ESA sesión)
        CREATE TABLE IF NOT EXISTS sesiones (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            inicio           TEXT NOT NULL,
            fin              TEXT,
            total_msgs       INTEGER DEFAULT 0,
            nombre           TEXT DEFAULT '',
            resumen_memoria  TEXT DEFAULT ''   -- resumen comprimido de la sesión
        );

        -- Memoria permanente del usuario (capa 1)
        CREATE TABLE IF NOT EXISTS memoria_usuario (
            clave  TEXT PRIMARY KEY,
            valor  TEXT NOT NULL,
            fecha  TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()


# ── Sesiones ───────────────────────────────────────────────────────────────────

def nueva_sesion() -> int:
    conn = conectar()
    cur = conn.cursor()
    cur.execute("INSERT INTO sesiones (inicio) VALUES (?)", (ahora(),))
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def cerrar_sesion(sesion_id: int, total_msgs: int):
    conn = conectar()
    conn.execute(
        "UPDATE sesiones SET fin=?, total_msgs=? WHERE id=?",
        (ahora(), total_msgs, sesion_id)
    )
    conn.commit()
    conn.close()


def guardar_resumen_sesion(sesion_id: int, resumen: str):
    """Persiste el resumen comprimido de la sesión en la DB."""
    conn = conectar()
    conn.execute(
        "UPDATE sesiones SET resumen_memoria=? WHERE id=?",
        (resumen, sesion_id)
    )
    conn.commit()
    conn.close()


def obtener_resumen_sesion(sesion_id: int) -> str:
    """Recupera el resumen comprimido de una sesión."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT resumen_memoria FROM sesiones WHERE id=?", (sesion_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


# ── Conversaciones ─────────────────────────────────────────────────────────────

def guardar_mensaje(sesion_id: int, role: str, mensaje: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO conversaciones (sesion_id, role, mensaje, fecha) VALUES (?,?,?,?)",
        (sesion_id, role, mensaje, ahora())
    )
    conn.commit()
    conn.close()


def obtener_mensajes_sesion(sesion_id: int) -> list:
    """Devuelve todos los mensajes de una sesión específica."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, mensaje, fecha FROM conversaciones WHERE sesion_id=? ORDER BY id ASC",
        (sesion_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def obtener_historial(limite: int = 50) -> list:
    """Devuelve los últimos N mensajes globales (para debug / stats)."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, mensaje, fecha FROM conversaciones ORDER BY id DESC LIMIT ?",
        (limite,)
    )
    rows = cur.fetchall()
    conn.close()
    return list(reversed(rows))


# ── Memoria permanente del usuario ─────────────────────────────────────────────

def guardar_dato_usuario(clave: str, valor: str):
    """Inserta o actualiza un dato permanente del usuario."""
    conn = conectar()
    conn.execute(
        "INSERT INTO memoria_usuario (clave, valor, fecha) VALUES (?,?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, fecha=excluded.fecha",
        (clave, valor, ahora())
    )
    conn.commit()
    conn.close()


def obtener_datos_usuario() -> dict:
    """Devuelve todos los datos permanentes del usuario como dict."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT clave, valor FROM memoria_usuario")
    rows = cur.fetchall()
    conn.close()
    return {k: v for k, v in rows}


def eliminar_dato_usuario(clave: str):
    conn = conectar()
    conn.execute("DELETE FROM memoria_usuario WHERE clave=?", (clave,))
    conn.commit()
    conn.close()


# ── Imágenes ───────────────────────────────────────────────────────────────────

def guardar_imagen(sesion_id: int, prompt: str, ruta: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO imagenes (sesion_id, prompt, ruta, fecha) VALUES (?,?,?,?)",
        (sesion_id, prompt, ruta, ahora())
    )
    conn.commit()
    conn.close()


# ── Documentos ─────────────────────────────────────────────────────────────────

def guardar_documento(sesion_id: int, nombre: str, resumen: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO documentos (sesion_id, nombre, resumen, fecha) VALUES (?,?,?,?)",
        (sesion_id, nombre, resumen, ahora())
    )
    conn.commit()
    conn.close()


# ── Acciones ───────────────────────────────────────────────────────────────────

def guardar_accion(sesion_id: int, accion: str):
    conn = conectar()
    conn.execute(
        "INSERT INTO acciones (sesion_id, accion, fecha) VALUES (?,?,?)",
        (sesion_id, accion, ahora())
    )
    conn.commit()
    conn.close()


# ── Gestión de sesiones ────────────────────────────────────────────────────────

def actualizar_nombre_sesion(sesion_id: int, nombre: str):
    conn = conectar()
    conn.execute("UPDATE sesiones SET nombre=? WHERE id=?", (nombre, sesion_id))
    conn.commit()
    conn.close()


def eliminar_sesion(sesion_id: int):
    conn = conectar()
    conn.execute("DELETE FROM conversaciones WHERE sesion_id=?", (sesion_id,))
    conn.execute("DELETE FROM sesiones WHERE id=?", (sesion_id,))
    conn.commit()
    conn.close()


def obtener_sesiones() -> list:
    """Devuelve todas las sesiones ordenadas de más reciente a más antigua."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.inicio, COUNT(c.id) as total, COALESCE(s.nombre,'') as nombre
        FROM sesiones s
        LEFT JOIN conversaciones c ON c.sesion_id=s.id AND c.role='user'
        GROUP BY s.id
        ORDER BY s.id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


# ── Estadísticas ───────────────────────────────────────────────────────────────

def estadisticas() -> dict:
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM conversaciones WHERE role='user'")
    total_mensajes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM imagenes")
    total_imagenes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documentos")
    total_documentos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sesiones")
    total_sesiones = cur.fetchone()[0]
    conn.close()
    return {
        "mensajes":   total_mensajes,
        "imagenes":   total_imagenes,
        "documentos": total_documentos,
        "sesiones":   total_sesiones,
    }


# ── Utilidad ───────────────────────────────────────────────────────────────────

def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")