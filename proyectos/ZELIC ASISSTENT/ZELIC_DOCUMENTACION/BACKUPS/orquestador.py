from google import genai
from google.genai import types

CATEGORIAS = {
    "chat":       "Conversación general, preguntas generales, o de interes",
    "imagen":     "El usuario pide generar, crear o dibujar una imagen",
    "documento":  "El usuario pide leer, analizar o resumir un archivo",
    "sistema":    "El usuario quiere abrir una app, abrir una URL, o VER/LISTAR archivos y carpetas del PC (escritorio, descargas, documentos, imágenes, etc.)",
    "tareas":     "El usuario quiere agregar, ver, completar o eliminar tareas o recordatorios. También aplica para preguntas de seguimiento como 'o algo?', 'y recordatorios?'",
    "clima":      "El usuario pregunta por el clima, temperatura, lluvia, pronóstico del tiempo o si debe llevar paraguas",
    "sistema_info": "El usuario pregunta por el RENDIMIENTO o ESTADO TÉCNICO del PC: uso de CPU, RAM, GPU, disco, batería o temperatura. NO incluye ver o listar archivos.",
    "vision":       "El usuario pregunta qué hay en su pantalla, qué está haciendo, pide que Zelic mire o analice lo que ve en pantalla",
}


def clasificar_intencion(client: genai.Client, mensaje: str, model: str = "gemini-2.5-flash", ultimo_modulo: str = "") -> str:
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