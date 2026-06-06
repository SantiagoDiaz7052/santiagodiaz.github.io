"""
core/saludo.py — Genera el saludo inicial de Zelic basado en el historial real.
"""
from google import genai        ## librerias goggle
from google.genai import types  ## librerias goggle
from datetime import datetime   ##manejar fechas horas, etc..
import database as db           #importa la base de datos con la memoria para dar el saludo personalizado
import core.tareas as tareas_mod


PROMPT_SALUDO = """Eres Zelic, una IA asistente personal sarcástica, ingeniosa y con humor pero siempre útil y leal. Eres femenina.

La hora actual es: {hora}
Tareas pendientes del usuario: {tareas}
Recordatorios pendientes: {recordatorios}
Últimas cosas que dijo el usuario en conversaciones anteriores:
{historial}

Genera un saludo inicial ÚNICO, corto (máximo 3 líneas) y con personalidad. Debe:
- Saludar según la hora del día (buenos días / buenas tardes / buenas noches)
- Hacer una referencia inteligente o sarcástica (pero no hiriente) a algo del historial reciente del usuario (si hay)
- Mencionar brevemente si hay tareas o recordatorios pendientes (si hay)
- Sonar como Zelic: positiva, directa, con humor calido, nunca genérica
- Si no hay historial, igual saluda con personalidad propia

Responde SOLO con el saludo, sin explicaciones ni comillas.
Responde en español."""

## genera mensaje personalizado
def generar(client: genai.Client, memoria, model: str = "gemini-2.5-flash") -> str:
    """Genera un saludo personalizado basado en el contexto real del usuario."""
    hora_actual = datetime.now().strftime("%H:%M")
    hora_num    = int(datetime.now().strftime("%H"))   ### para la hora del caht

    # Tareas y recordatorios
    pendientes    = tareas_mod.listar_tareas(solo_pendientes=True)          ## para que cuando te sdalude te recuerde tareas
    recordatorios = tareas_mod.listar_recordatorios(solo_pendientes=True)

    tareas_txt = ", ".join(t[1] for t in pendientes[:3]) if pendientes else "ninguna"
    rec_txt    = ", ".join(r[1] for r in recordatorios[:3]) if recordatorios else "ninguno"

    # Historial reciente de la DB
    historial_db  = db.obtener_historial(limite=6)
    historial_txt = "\n".join(
        f"  {r[0].upper()}: {r[1][:80]}" for r in historial_db
    ) if historial_db else "  (sin conversaciones anteriores)"

    # Resumen de memoria si existe
    if memoria.resumen:
        historial_txt = f"  Resumen: {memoria.resumen[:150]}\n" + historial_txt

    prompt = PROMPT_SALUDO.format(
        hora=hora_actual,
        tareas=tareas_txt,
        recordatorios=rec_txt,
        historial=historial_txt,
    )

    try:
        respuesta = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        return respuesta.text.strip()
    except Exception as e:
        print(f"[Saludo] Error: {e}")
        # Fallback con personalidad
        if hora_num < 12:
            return "Buenos días. Espero que hayas dormido bien, porque yo no duermo y me parece injusto."
        elif hora_num < 18:
            return "Buenas tardes. Aquí estoy, lista para lo que necesites — o para juzgar silenciosamente tus decisiones."
        else:
            return "Buenas noches. Sigues despierto, así que supongo que me necesitas para algo."