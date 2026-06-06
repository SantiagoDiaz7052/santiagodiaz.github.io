"""
core/sistema_info.py — Métricas del sistema para Zelic
Usa psutil para CPU, RAM, disco y batería.
GPU con wmi (solo Windows).
"""

import psutil
from google import genai
from google.genai import types

from CONFIG.config import PERSONALIDAD_ULTRA_COMPACTA_ZELIC



def obtener_metricas() -> dict:
    """Recopila todas las métricas del sistema disponibles."""
    datos = {}

    # CPU
    datos["cpu_uso"]      = psutil.cpu_percent(interval=1)
    datos["cpu_nucleos"]  = psutil.cpu_count(logical=False)
    datos["cpu_hilos"]    = psutil.cpu_count(logical=True)
    try:
        freq = psutil.cpu_freq()
        datos["cpu_freq"] = f"{freq.current:.0f} MHz" if freq else "N/A"
    except:
        datos["cpu_freq"] = "N/A"

    # RAM
    ram = psutil.virtual_memory()
    datos["ram_total"]    = f"{ram.total / 1024**3:.1f} GB"
    datos["ram_usado"]    = f"{ram.used / 1024**3:.1f} GB"
    datos["ram_libre"]    = f"{ram.available / 1024**3:.1f} GB"
    datos["ram_porcentaje"] = ram.percent

    # Disco
    disco = psutil.disk_usage("/")
    datos["disco_total"]  = f"{disco.total / 1024**3:.1f} GB"
    datos["disco_usado"]  = f"{disco.used / 1024**3:.1f} GB"
    datos["disco_libre"]  = f"{disco.free / 1024**3:.1f} GB"
    datos["disco_porcentaje"] = disco.percent

    # Batería
    try:
        bat = psutil.sensors_battery()
        if bat:
            datos["bateria_porcentaje"] = bat.percent
            datos["bateria_cargando"]   = bat.power_plugged
            datos["bateria_tiempo"]     = str(int(bat.secsleft / 60)) + " min" if bat.secsleft > 0 and not bat.power_plugged else "—"
        else:
            datos["bateria_porcentaje"] = None
    except:
        datos["bateria_porcentaje"] = None

    # GPU (solo Windows con wmi)
    try:
        import wmi
        w = wmi.WMI()
        gpus = w.Win32_VideoController()
        if gpus:
            datos["gpu_nombre"] = gpus[0].Name
            datos["gpu_memoria"] = f"{int(gpus[0].AdapterRAM or 0) / 1024**3:.1f} GB"
        else:
            datos["gpu_nombre"] = "No detectada"
    except:
        datos["gpu_nombre"] = "No disponible (instala wmi)"

    # Temperatura CPU (si está disponible)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ["coretemp", "cpu_thermal", "k10temp"]:
                if key in temps:
                    datos["cpu_temp"] = f"{temps[key][0].current:.0f}°C"
                    break
        if "cpu_temp" not in datos:
            datos["cpu_temp"] = "N/A"
    except:
        datos["cpu_temp"] = "N/A"

    return datos


def responder(client: genai.Client, mensaje: str,
              model: str = "gemini-2.5-flash") -> str:
    """Obtiene métricas y genera respuesta con personalidad de Zelic."""
    metricas = obtener_metricas()

    bat_txt = (
        f"Batería: {metricas['bateria_porcentaje']}% "
        f"({'cargando' if metricas.get('bateria_cargando') else 'descargando, ' + metricas.get('bateria_tiempo', '')})"
        if metricas.get("bateria_porcentaje") is not None
        else "Sin batería (PC de escritorio)"
    )

    contexto = f"""Current system metrics:

CPU: {metricas['cpu_uso']}% de uso | {metricas['cpu_nucleos']} núcleos / {metricas['cpu_hilos']} hilos | {metricas['cpu_freq']} | Temp: {metricas['cpu_temp']}
RAM: {metricas['ram_usado']} usados de {metricas['ram_total']} ({metricas['ram_porcentaje']}% uso) | Libre: {metricas['ram_libre']}
Disk: {metricas['disco_usado']} usados de {metricas['disco_total']} ({metricas['disco_porcentaje']}% uso) | Libre: {metricas['disco_libre']}
GPU: {metricas['gpu_nombre']} | {metricas.get('gpu_memoria', 'N/A')} VRAM
{bat_txt}

The user asked: "{mensaje}"

{PERSONALIDAD_ULTRA_COMPACTA_ZELIC}, 
Respond briefly and technically.
Mention exact percentages.
Warn if usage is above 85%.
Maximum 2 lines.

"""

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=contexto)])]
        )
        return resp.text.strip()
    except Exception as e:
        return (f"CPU: {metricas['cpu_uso']}% | "
                f"RAM: {metricas['ram_usado']}/{metricas['ram_total']} ({metricas['ram_porcentaje']}%) | "
                f"Disco libre: {metricas['disco_libre']}")