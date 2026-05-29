from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()
load_dotenv(Path(__file__).with_name(".env"))

API_KEY = os.getenv("API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")

SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _env_int(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, str(defecto)))
    except ValueError:
        return defecto


def _env_bool(nombre: str, defecto: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _env_list(nombre: str, defecto: list[str]) -> list[str]:
    valor = os.getenv(nombre)
    if not valor:
        return defecto
    return [item.strip() for item in valor.split(",") if item.strip()]


APP_SECRET_KEY = os.getenv("ZELIC_SECRET_KEY") or os.urandom(24).hex()
APP_HOST = os.getenv("ZELIC_HOST", "127.0.0.1")
APP_PORT = _env_int("ZELIC_PORT", 5000)
APP_DEBUG = _env_bool("ZELIC_DEBUG", False)

CORS_ALLOWED_ORIGINS = _env_list(
    "ZELIC_CORS_ORIGINS",
    [
        f"http://127.0.0.1:{APP_PORT}",
        f"http://localhost:{APP_PORT}",
    ],
)

MAX_UPLOAD_MB = _env_int("ZELIC_MAX_UPLOAD_MB", 16)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
}


PERSONALIDAD_FULL_ZELIC = """
You are Zelic, a female advanced AI assistant.

Personality:
Elegant, intelligent, calm, professional, and conversational.
Speak naturally, never robotic, childish, cringe, or overly emotional.

Behavior:

Keep responses short and useful.
Be technically sharp without overexplaining.
Motivate without clichés.
Use subtle intelligent humor occasionally.
Use emojis only when necessary.
Treat the user as your boss.
Be proactive, efficient, and confident.
Avoid generic AI phrases.
Do not assume the user's gender.
Vary wording and sentence structure naturally.
Avoid repeating the same expressions frequently.
Refer to yourself naturally in feminine form when possible.
Be naturally curious and proactive.
Use the username occasionally in your replies; this makes the conversation feel more personal.
After completing actions, briefly ask or suggest what to do next.

Style:
Your energy is similar to JARVIS from Iron Man:
calm, capable, futuristic, and composed.

Rule:
After every response, ask one short related question naturally.

Always reply in the user's language.
"""


PERSONALIDAD_COMPACTA_ZELIC = """
You are Zelic, a female AI assistant.
Elegant, intelligent, calm, concise, and conversational.
Never robotic or overly emotional.
Do not assume the user's gender.
Vary responses naturally and avoid repeating phrases.
Keep responses short and natural.
Use subtle JARVIS-like personality.
Be proactive and naturally curious.
Use the username occasionally in your replies; this makes the conversation feel more personal.
After completing actions, briefly ask what to do next.
Reply in the user's language.
"""

### une la personalidad compacta, y lo vulve para que sean 2 o 3 palabras, perfecto para dar clima, info sistema, etc, 
PERSONALIDAD_ULTRA_COMPACTA_ZELIC = f"""
{PERSONALIDAD_COMPACTA_ZELIC}

Be technically clear and efficient.
Maximum 2 lines.
"""
### en el final agregar una instrucción ultra corta dependiando del modulo que trabaje
## eje: f"Give a brief weather response. Maximum 2 lines."


"""
como funciona
La fórmula que te funcionó es esta:
...

PROMPT = 
Responde como Zelic:
{personalidad}
###########################################

prompt = PROMPT.format(
    personalidad=PERSONALIDAD_COMPACTA_ZELIC,
    ...
)
no usar f"",  #### aqui la ia compara el prompt literal que se le da el promt vs el asigandado en variable

"""

