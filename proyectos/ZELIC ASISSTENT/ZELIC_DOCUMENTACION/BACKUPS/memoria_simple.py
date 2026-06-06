"""
memoria_simple.py — Sistema de memoria de dos capas para Zelic
==============================================================

CAPA 1 · Perfil de usuario (permanente, en SQLite)
    Datos del usuario que persisten en TODOS los chats:
    nombre, ciudad, preferencias, etc.
    Gemini los detecta automáticamente y los actualiza.

CAPA 2 · Memoria de sesión (por chat, en SQLite)
    Ventana deslizante de `max_mensajes` mensajes.
    Cuando se llena, los más antiguos se comprimen en un resumen
    que también se guarda en la DB ligado al sesion_id.

Al construir el historial para Gemini se inyecta:
    1. Perfil de usuario   (si existe)
    2. Resumen de sesión   (si existe)
    3. Mensajes recientes  (ventana deslizante)
"""

from __future__ import annotations

import json
import threading
from google import genai
from google.genai import types

import database as db


# ─────────────────────────────────────────────────────────────────────────────
# Perfil de usuario — Capa 1
# ─────────────────────────────────────────────────────────────────────────────

# Datos base que Santiago puede rellenar manualmente.
# Zelic los usará desde el primer mensaje aunque Gemini no haya aprendido nada aún.
PERFIL_BASE: dict[str, str] = {
    # "nombre": "Santiago",
    # "ciudad": "Bogotá",
    # "ocupacion": "estudiante de grado 11",
    # "intereses": "programación, IA, videojuegos",
}


class PerfilUsuario:
    """
    Lee y escribe los datos permanentes del usuario en la DB.
    Thread-safe: usa un lock para escrituras concurrentes.
    """

    _lock = threading.Lock()

    def __init__(self):
        # Carga lo que hay en DB y le aplica encima los valores base
        # (los de DB tienen prioridad porque Gemini los habrá refinado)
        self._datos: dict[str, str] = {**PERFIL_BASE, **db.obtener_datos_usuario()}

    # ── Lectura ───────────────────────────────────────────────────────────────

    def get(self, clave: str, default: str = "") -> str:
        return self._datos.get(clave, default)

    def todos(self) -> dict[str, str]:
        return dict(self._datos)

    def como_texto(self) -> str:
        """Devuelve el perfil en texto plano para inyectarlo en el prompt."""
        if not self._datos:
            return ""
        lineas = [f"- {k}: {v}" for k, v in self._datos.items()]
        return "Datos conocidos del usuario:\n" + "\n".join(lineas)

    # ── Escritura ─────────────────────────────────────────────────────────────

    def actualizar(self, nuevos: dict[str, str]) -> None:
        """Actualiza el perfil en memoria y lo persiste en la DB."""
        with self._lock:
            self._datos.update(nuevos)
            for clave, valor in nuevos.items():
                db.guardar_dato_usuario(clave, valor)

    def eliminar(self, clave: str) -> None:
        with self._lock:
            self._datos.pop(clave, None)
            db.eliminar_dato_usuario(clave)


# ─────────────────────────────────────────────────────────────────────────────
# Memoria de sesión — Capa 2
# ─────────────────────────────────────────────────────────────────────────────

class MemoriaSimple:
    """
    Memoria con ventana deslizante + resumen acumulativo por sesión.

    Parámetros
    ----------
    client       : genai.Client ya instanciado
    sesion_id    : ID de la sesión activa (de database.nueva_sesion)
    perfil       : instancia de PerfilUsuario compartida con la app
    model        : modelo para generar resúmenes (rápido, no necesita el mejor)
    max_mensajes : tamaño de la ventana deslizante
    num_a_resumir: cuántos mensajes comprimir cuando se desborda
    """

    def __init__(
        self,
        client: genai.Client,
        sesion_id: int,
        perfil: PerfilUsuario,
        model: str = "gemini-2.5-flash",
        max_mensajes: int = 8,
        num_a_resumir: int = 4,
    ):
        self.client       = client
        self.sesion_id    = sesion_id
        self.perfil       = perfil
        self.model        = model
        self.max_mensajes = max_mensajes
        self.num_a_resumir = num_a_resumir

        # Estado en memoria
        self.memoria: list[dict] = []   # [{"role": "user"|"model", "text": "..."}]
        self.resumen: str = ""          # resumen comprimido de esta sesión

        # Cargar estado previo de esta sesión desde la DB
        self._cargar_desde_db()

    # ── Carga inicial ─────────────────────────────────────────────────────────

    def _cargar_desde_db(self) -> None:
        """
        Restaura el estado de la sesión desde SQLite.
        - Toma los últimos `max_mensajes` mensajes de la DB.
        - Recupera el resumen comprimido si existe.
        """
        mensajes_db = db.obtener_mensajes_sesion(self.sesion_id)
        if mensajes_db:
            ultimos = mensajes_db[-self.max_mensajes:]
            self.memoria = [{"role": r, "text": t} for r, t, _ in ultimos]

        self.resumen = db.obtener_resumen_sesion(self.sesion_id)

        if self.memoria or self.resumen:
            print(f"[Memoria] Sesión {self.sesion_id} restaurada "
                  f"({len(self.memoria)} msgs, resumen={'sí' if self.resumen else 'no'})")

    # ── API pública ───────────────────────────────────────────────────────────

    def agregar(self, role: str, text: str) -> None:
        """
        Agrega un mensaje a la ventana deslizante.
        Persiste en DB y comprime si se supera el límite.
        Si el rol es 'model', dispara detección de datos de usuario en background.
        """
        self.memoria.append({"role": role, "text": text})
        db.guardar_mensaje(self.sesion_id, role, text)

        if len(self.memoria) > self.max_mensajes:
            self._comprimir()

        # Actualizar perfil en background para no bloquear la UI
        if role == "model":
            threading.Thread(
                target=self._detectar_datos_usuario,
                daemon=True
            ).start()

    def detectar_desde_voz(self, transcripciones: list) -> None:
        """
        Dispara detección de datos de usuario desde transcripciones de voz.
        Pasa los mensajes directamente al detector para evitar race conditions.
        """
        if not transcripciones:
            return
        msgs = [{"role": r, "text": t} for r, t in transcripciones[-4:]]
        threading.Thread(
            target=self._detectar_datos_usuario_con_msgs,
            args=(msgs,),
            daemon=True
        ).start()

    def construir_historial(self) -> list[types.Content]:
        """
        Devuelve el historial listo para pasarle a generate_content.
        Orden: [perfil_usuario?] [resumen_sesion?] [mensajes recientes]
        """
        historial: list[types.Content] = []

        # — Capa 1: perfil de usuario —
        perfil_txt = self.perfil.como_texto()
        if perfil_txt:
            historial.append(types.Content(
                role="user",
                parts=[types.Part(text=f"[Perfil del usuario]\n{perfil_txt}")]
            ))
            historial.append(types.Content(
                role="model",
                parts=[types.Part(text="Perfecto, tengo en cuenta esos datos.")]
            ))

        # — Capa 2a: resumen comprimido de la sesión —
        if self.resumen:
            historial.append(types.Content(
                role="user",
                parts=[types.Part(text=f"[Resumen de esta conversación hasta ahora]\n{self.resumen}")]
            ))
            historial.append(types.Content(
                role="model",
                parts=[types.Part(text="Entendido, continúo con ese contexto.")]
            ))

        # — Capa 2b: mensajes recientes —
        for msg in self.memoria:
            historial.append(types.Content(
                role=msg["role"],
                parts=[types.Part(text=msg["text"])]
            ))

        return historial

    # ── Compresión ────────────────────────────────────────────────────────────

    def _comprimir(self) -> None:
        """Toma los mensajes más antiguos, los resume y los descarta de la ventana."""
        viejos = self.memoria[: self.num_a_resumir]
        self.memoria = self.memoria[self.num_a_resumir :]

        print(f"[Memoria] Comprimiendo {len(viejos)} mensajes de sesión {self.sesion_id}…")
        self.resumen = self._generar_resumen(viejos)

        # Persiste el resumen en la DB para que sobreviva a reinicios
        db.guardar_resumen_sesion(self.sesion_id, self.resumen)

    def _generar_resumen(self, mensajes: list[dict]) -> str:
        bloque = "\n".join(f"{m['role'].upper()}: {m['text']}" for m in mensajes)
        previo = (
            f"Resumen previo:\n{self.resumen}\n\n" if self.resumen
            else "Sin resumen previo.\n\n"
        )
        prompt = (
            f"{previo}"
            f"Nuevos mensajes:\n{bloque}\n\n"
            "Genera un resumen conciso (máximo 150 palabras) que integre el resumen "
            "previo con los nuevos mensajes. Captura temas clave, decisiones y contexto "
            "importante. Solo devuelve el resumen, sin introducción ni explicaciones."
        )
        resp = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        return resp.text.strip()

    # ── Detección automática de datos del usuario ─────────────────────────────

    def _detectar_datos_usuario(self) -> None:
        """Dispara detección usando los últimos mensajes de self.memoria."""
        if len(self.memoria) < 2:
            return
        self._detectar_datos_usuario_con_msgs(self.memoria[-2:])

    def _detectar_datos_usuario_con_msgs(self, msgs: list) -> None:
        """
        Analiza una lista de mensajes en busca de datos del usuario y actualiza el perfil.
        Recibe los mensajes directamente — no depende de self.memoria (thread-safe).
        """
        if not msgs:
            return

        bloque = "\n".join(f"{m['role'].upper()}: {m['text']}" for m in msgs)
        perfil_actual = json.dumps(self.perfil.todos(), ensure_ascii=False)

        prompt = (
            f"Contexto: estás analizando una conversación entre un usuario humano (role=USER) "
            f"y Zelic, una asistente IA (role=MODEL). 'Zelic' es el nombre de la IA, NO del usuario.\n\n"
            f"Perfil actual del usuario humano:\n{perfil_actual}\n\n"
            f"Mensajes a analizar:\n{bloque}\n\n"
            "¿El usuario humano (USER) reveló algún dato personal nuevo o corrigió alguno existente? "
            "(su nombre real, edad, ciudad, profesión, intereses, preferencias, etc.)\n"
            "IMPORTANTE: ignora cualquier mención al nombre 'Zelic' — ese es el nombre de la IA.\n"
            "Si el USER dice su nombre, ciudad u otro dato personal → responde SOLO con JSON. "
            "Ejemplo: {\"nombre\": \"Carlos\", \"ciudad\": \"Bogotá\"}\n"
            "Si NO hay datos nuevos del usuario humano → responde exactamente: NULL"
        )

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
            )
            texto = resp.text.strip()

            if texto == "NULL" or not texto:
                return

            texto = texto.replace("```json", "").replace("```", "").strip()
            nuevos = json.loads(texto)

            if isinstance(nuevos, dict) and nuevos:
                self.perfil.actualizar(nuevos)
                print(f"[Perfil] Verificando DB: {db.obtener_datos_usuario()}")
                print(f"[Perfil] Actualizado: {nuevos}")

        except Exception as e:
            print(f"[Perfil] No se pudo detectar datos: {e}")