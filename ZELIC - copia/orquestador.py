import re
from google import genai
from google.genai import types

CATEGORIAS = {
    "chat":         "Conversación general, preguntas, análisis de texto, resumir o leer páginas web (URLs http/https), o cualquier consulta de información",
    "imagen":       "El usuario pide generar, crear o dibujar una imagen",
    "documento":    "El usuario pide leer, analizar o resumir un ARCHIVO adjunto (PDF, Word, txt, etc.) que ya subió. NO aplica si hay una URL.",
    "sistema":      "El usuario quiere abrir una app, o VER/LISTAR archivos y carpetas del PC (escritorio, descargas, documentos, imágenes, etc.)",
    "tareas":       "El usuario quiere agregar, ver, completar o eliminar tareas o recordatorios. También aplica para preguntas de seguimiento como 'o algo?', 'y recordatorios?'",
    "clima":        "El usuario pregunta por el clima, temperatura, lluvia, pronóstico del tiempo o si debe llevar paraguas",
    "sistema_info": "El usuario pregunta por el RENDIMIENTO o ESTADO TÉCNICO del PC: uso de CPU, RAM, GPU, disco, batería o temperatura. NO incluye ver o listar archivos.",
    "vision":       "El usuario pregunta qué hay en su pantalla, qué está haciendo, pide que Zelic mire o analice lo que ve en pantalla",
}

_URL_RE = re.compile(r'https?://\S+')


def _contiene_url(texto: str) -> bool:
    """Detecta si el mensaje tiene al menos una URL http/https."""
    return bool(_URL_RE.search(texto))


def clasificar_intencion(
    client: genai.Client,
    mensaje: str,
    model: str = "gemini-2.5-flash",
    ultimo_modulo: str = "",
    hay_contexto_web: bool = False,
) -> str:
    """
    Clasifica la intención del mensaje.

    Args:
        hay_contexto_web: True si leer_urls() ya procesó URLs del mensaje.
                          Fuerza 'chat' directamente sin llamar al LLM.
    """
    # ── Cortocircuito: si ya extrajimos contenido web → siempre chat ─────────
    # (No tiene sentido que el LLM lo clasifique como 'documento' o 'sistema')
    if hay_contexto_web or _contiene_url(mensaje):
        print("[Orquestador] URL detectada → chat (con contexto web)")
        return "chat"
    # ─────────────────────────────────────────────────────────────────────────

    lista    = "\n".join(f"- {k}: {v}" for k, v in CATEGORIAS.items())
    claves   = ", ".join(CATEGORIAS.keys())
    contexto = f"El módulo anterior fue: {ultimo_modulo}. " if ultimo_modulo else ""

    prompt = (
        f"{contexto}"
        f"Clasifica el siguiente mensaje en UNA sola categoría:\n"
        f"{lista}\n\n"
        f"Mensaje: \"{mensaje}\"\n\n"
        f"Responde ÚNICAMENTE con una de estas palabras clave: {claves}. "
        f"Sin explicaciones ni puntuación extra."
    )

    try:
        respuesta = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        intencion = respuesta.text.strip().lower()
        if intencion not in CATEGORIAS:
            print(f"[Orquestador] Categoría desconocida: '{intencion}', usando chat")
            return "chat"
        return intencion
    except Exception as e:
        print(f"[Orquestador] Error: {e}")
        return "chat"