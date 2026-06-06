"""
core/voz.py — Gemini Live para Zelic
Basado en la implementación real de JARVIS demo.
Usa sounddevice + gemini-2.5-flash-native-audio-preview-12-2025
"""

import asyncio
import queue
import threading
import warnings
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from CONFIG.config import API_KEY

# Silenciar warning de non-data parts de Gemini
warnings.filterwarnings("ignore", message=".*non-data parts.*")

MODELO_VOZ       = "gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS         = 1
SEND_SAMPLE_RATE = 16000
RECV_SAMPLE_RATE = 24000
CHUNK_SIZE       = 1600   # 100ms — bloques más grandes reducen fragmentación
PLAY_CHUNK_SIZE  = 480    # 20ms — reproducción

SYSTEM_PROMPT_VOZ = (
    "Eres Zelic, una asistente de voz sarcástica, ingeniosa y útil, como Jarvis de Iron Man pero femenina. "
    "Respuestas cortas y conversacionales. "
    "Usa el nombre del usuario frecuentemente. "
    "Usa las herramientas disponibles para completar tareas — nunca simules resultados. "
    "Responde siempre en el mismo idioma del usuario."
)

# Herramientas disponibles para Gemini Live
TOOL_DECLARATIONS = [
    {
        "name": "abrir_app",
        "description": "Abre una aplicación en el PC del usuario",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Nombre de la app a abrir"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "ver_tareas",
        "description": "Muestra las tareas y recordatorios pendientes del usuario",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "agregar_tarea",
        "description": "Agrega una tarea o recordatorio",
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título de la tarea"},
                "fecha_hora": {"type": "string", "description": "Fecha y hora para recordatorio (YYYY-MM-DD HH:MM), vacío si es solo tarea"}
            },
            "required": ["titulo"]
        }
    },
    {
        "name": "ver_clima",
        "description": "Consulta el clima actual",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "ver_sistema",
        "description": "Muestra el estado del sistema: CPU, RAM, disco",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "abrir_url",
        "description": "Abre una URL en el navegador",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL a abrir"}
            },
            "required": ["url"]
        }
    },
]


class ModuloVoz:
    def __init__(self, client: genai.Client,
                 callback_texto=None,
                 callback_estado=None,
                 callback_apagar=None,
                 callback_memoria=None,
                 memoria=None):
        self.client           = client
        self.callback_texto   = callback_texto
        self.callback_estado  = callback_estado
        self.callback_apagar  = callback_apagar
        self.callback_memoria = callback_memoria
        self.memoria          = memoria  # instancia de MemoriaSimple
        self._activo          = False
        self._hablando        = False
        self._loop            = None
        self._hilo            = None
        self.session          = None
        self.out_queue        = None   # audio mic → Gemini
        self.audio_in_queue   = None   # audio Gemini → parlantes
        self._speaking_lock   = threading.Lock()
        self._stop_requested  = threading.Event()
        self._play_queue      = queue.Queue()   # hilo dedicado de reproducción

    def iniciar(self):
        self._activo = True
        # Hilo dedicado de reproducción — queue.Queue estándar, sin asyncio
        self._hilo_play = threading.Thread(target=self._hilo_reproduccion, daemon=True)
        self._hilo_play.start()
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()

    def detener(self):
        self._activo = False
        self._stop_requested.set()
        self._play_queue.put(None)  # señal de cierre al hilo de reproducción

    def _correr(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except Exception as e:
            print(f"[Voz] Error: {e}")
        finally:
            self._loop.close()
            self._loop = None

    def _build_system_prompt(self) -> str:
        """Construye el system prompt con contexto actual de memoria."""
        base = (
            "Eres Zelic, una asistente de voz sarcástica, ingeniosa y útil, como Jarvis de Iron Man pero femenina. "
            "Respuestas cortas y conversacionales. "
            "Usa el nombre del usuario frecuentemente. "
            "Usa las herramientas disponibles para completar tareas — nunca simules resultados. "
            "Responde siempre en el mismo idioma del usuario."
        )

        if not self.memoria:
            return base

        secciones = [base]

        # Perfil del usuario
        perfil_txt = self.memoria.perfil.como_texto()
        if perfil_txt:
            secciones.append(f"\n{perfil_txt}")

        # Resumen de la sesión actual
        if self.memoria.resumen:
            secciones.append(
                f"\nResumen de la conversación reciente:\n{self.memoria.resumen}"
            )

        # Últimos mensajes del chat (contexto inmediato)
        if self.memoria.memoria:
            ultimos = self.memoria.memoria[-4:]
            bloque = "\n".join(
                f"{'Usuario' if m['role'] == 'user' else 'Zelic'}: {m['text']}"
                for m in ultimos
            )
            secciones.append(f"\nÚltimos mensajes del chat:\n{bloque}")

        return "\n".join(secciones)

    def _build_config(self) -> types.LiveConnectConfig:
        cfg_kwargs = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=self._build_system_prompt(),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                ),
            ),
        )

        # VAD — igual que JARVIS demo
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=400,
                    silence_duration_ms=2000,
                )
            )
            print("[Voz] VAD configurado (typed)")
        except Exception:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 200,
                        "silence_duration_ms": 1500,
                    }
                }
                print("[Voz] VAD configurado (dict)")
            except Exception:
                print("[Voz] VAD no configurado")

        # Velocidad de habla
        try:
            cfg_kwargs["output_audio_config"] = types.OutputAudioConfig(
                audio_encoding="LINEAR16",
                speaking_rate=1.1,
            )
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _run(self):
        client = genai.Client(
            api_key=API_KEY,
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay = 1.0

        while self._activo:
            try:
                self.out_queue      = asyncio.Queue()
                self.audio_in_queue = asyncio.Queue()
                config              = self._build_config()

                print(f"[Voz] Conectando con {MODELO_VOZ}...")
                self._estado("escuchando")

                async with client.aio.live.connect(
                    model=MODELO_VOZ, config=config
                ) as session:
                    self.session = session
                    print("[Voz] ✅ Sesión live iniciada.")
                    reconnect_delay = 1.0

                    await asyncio.gather(
                        self._listen_audio(),
                        self._send_realtime(),
                        self._receive_audio(session),
                        self._play_audio(),
                    )

            except Exception as e:
                msg = str(e)
                if not self._activo:
                    break
                print(f"[Voz] Error: {e} — reconectando en {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 15)

        self.session = None
        self._estado("idle")

    async def _listen_audio(self):
        """Captura micrófono con sounddevice y envía a Gemini."""
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if self._activo and not self._hablando:  # ← no capturar mientras Zelic habla
                data = indata.tobytes()
                try:
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"}
                    )
                except Exception:
                    pass

        with sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=callback,
        ):
            print("[Voz] 🎤 Micrófono activo")
            while self._activo:
                await asyncio.sleep(0.01)

    async def _send_realtime(self):
        """Acumula chunks del micrófono y los envía en bloques de ~200ms a Gemini."""
        SAMPLES_200MS = SEND_SAMPLE_RATE * 200 // 1000 * 2  # 200ms en bytes (int16)
        buf = bytearray()
        while self._activo:
            try:
                msg = await asyncio.wait_for(self.out_queue.get(), timeout=0.05)
                buf.extend(msg["data"])
                # Drenar todo lo disponible
                while not self.out_queue.empty():
                    extra = self.out_queue.get_nowait()
                    buf.extend(extra["data"])
                # Enviar cuando tenemos suficiente audio acumulado
                if len(buf) >= SAMPLES_200MS:
                    await self.session.send_realtime_input(
                        media={"data": bytes(buf), "mime_type": "audio/pcm"}
                    )
                    buf = bytearray()
            except asyncio.TimeoutError:
                # Enviar lo que hay aunque no llegue a 200ms
                if buf:
                    await self.session.send_realtime_input(
                        media={"data": bytes(buf), "mime_type": "audio/pcm"}
                    )
                    buf = bytearray()

    async def _receive_audio(self, session):
        """Recibe respuestas de Gemini — audio y transcripciones."""
        in_buf, out_buf = [], []

        while self._activo:
            async for response in session.receive():
                if not self._activo:
                    break

                # response.data — fuente principal de audio en v1beta
                if response.data and not self._stop_requested.is_set():
                    self.audio_in_queue.put_nowait(response.data)

                sc = response.server_content
                if sc:
                    # part.inline_data — fuente secundaria (solo si no viene en response.data)
                    if sc.model_turn and not response.data:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                mime = part.inline_data.mime_type or ""
                                if mime.startswith("audio/"):
                                    if not self._stop_requested.is_set():
                                        self.audio_in_queue.put_nowait(part.inline_data.data)

                    # Transcripción del usuario — acumular sin separar palabras
                    if sc.input_transcription and sc.input_transcription.text:
                        txt = sc.input_transcription.text
                        if txt:
                            in_buf.append(txt)

                    # Transcripción de Zelic — acumular sin separar palabras
                    if sc.output_transcription and sc.output_transcription.text:
                        txt = sc.output_transcription.text
                        if txt:
                            out_buf.append(txt)

                    # Turno completo — concatenar directo sin join con espacio
                    if sc.turn_complete:
                        self._stop_requested.clear()
                        texto_usuario = "".join(in_buf).strip()
                        texto_zelic   = "".join(out_buf).strip()

                        if texto_usuario:
                            print(f"[Voz] ✅ Usuario: {texto_usuario}")
                        if texto_zelic:
                            print(f"[Voz] ✅ Zelic: {texto_zelic}")

                        # Guardar en memoria compartida con el chat (en background)
                        if self.callback_memoria:
                            if texto_usuario:
                                threading.Thread(
                                    target=self.callback_memoria,
                                    args=("user", texto_usuario),
                                    daemon=True
                                ).start()
                            if texto_zelic:
                                threading.Thread(
                                    target=self.callback_memoria,
                                    args=("model", texto_zelic),
                                    daemon=True
                                ).start()

                        if self.callback_texto:
                            if texto_usuario:
                                self.callback_texto(("usuario", texto_usuario))
                            if texto_zelic:
                                self.callback_texto(("zelic", f"🎙 {texto_zelic}"))

                        # Detectar apagado
                        if texto_usuario and any(
                            c in texto_usuario.lower()
                            for c in ["apágate", "apagate", "apagar", "cierra", "hasta luego zelic"]
                        ):
                            if self.callback_apagar:
                                self.callback_apagar()

                        in_buf, out_buf = [], []
                        self._estado("escuchando")

                # Tool calls
                if response.tool_call:
                    fn_responses = []
                    for fc in response.tool_call.function_calls:
                        print(f"[Voz] 🔧 Herramienta: {fc.name}")
                        result = await self._ejecutar_herramienta(fc.name, dict(fc.args or {}))
                        fn_responses.append(types.FunctionResponse(
                            id=fc.id, name=fc.name,
                            response={"result": result}
                        ))
                    if fn_responses:
                        await session.send_tool_response(function_responses=fn_responses)

    def _hilo_reproduccion(self):
        """Hilo dedicado que reproduce audio con sounddevice usando queue.Queue estándar.
        No usa asyncio — escritura directa y continua, sin fragmentación."""
        stream = sd.RawOutputStream(
            samplerate=RECV_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=PLAY_CHUNK_SIZE,
        )
        stream.start()
        audio_buf = bytearray()
        BLOQUE = PLAY_CHUNK_SIZE * 2  # 40ms por escritura

        try:
            while True:
                try:
                    chunk = self._play_queue.get(timeout=0.1)
                    if chunk is None:  # señal de cierre
                        break
                    with self._speaking_lock:
                        self._hablando = True
                    self._estado("hablando")
                    audio_buf.extend(chunk)

                    # Drenar todo lo disponible antes de escribir
                    while not self._play_queue.empty():
                        extra = self._play_queue.get_nowait()
                        if extra is None:
                            break
                        audio_buf.extend(extra)

                    # Escribir en bloques fijos directamente — sin asyncio
                    while len(audio_buf) >= BLOQUE:
                        stream.write(bytes(audio_buf[:BLOQUE]))
                        audio_buf = audio_buf[BLOQUE:]

                except queue.Empty:
                    # Vaciar buffer restante solo si la cola lleva tiempo vacía
                    if audio_buf:
                        stream.write(bytes(audio_buf))
                        audio_buf = bytearray()
                    with self._speaking_lock:
                        self._hablando = False
                    self._estado("escuchando")
        finally:
            if audio_buf:
                stream.write(bytes(audio_buf))
            stream.stop()
            stream.close()

    async def _play_audio(self):
        """Transfiere chunks de audio desde asyncio.Queue al hilo de reproducción (queue.Queue)."""
        while self._activo:
            try:
                chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.05)
                if not self._stop_requested.is_set():
                    self._play_queue.put(chunk)
            except asyncio.TimeoutError:
                pass

    async def _ejecutar_herramienta(self, nombre: str, args: dict) -> str:
        """Ejecuta una herramienta del backend de Zelic."""
        loop = asyncio.get_event_loop()
        try:
            if nombre == "abrir_app":
                from core.sistema import _abrir_app
                r = await loop.run_in_executor(None, lambda: _abrir_app(args.get("app_name", "").lower()))
                return "Listo." if r == "ok" else r

            elif nombre == "abrir_url":
                from core.sistema import _abrir_url
                r = await loop.run_in_executor(None, lambda: _abrir_url(args.get("url", "")))
                return "Listo." if r == "ok" else r

            elif nombre == "ver_tareas":
                from core.tareas import listar_tareas, listar_recordatorios
                tareas = listar_tareas(solo_pendientes=True)
                recs   = listar_recordatorios(solo_pendientes=True)
                t_txt  = "\n".join(f"- {t[1]}" for t in tareas) or "Sin tareas pendientes"
                r_txt  = "\n".join(f"- {r[1]} ({r[2]})" for r in recs) or "Sin recordatorios"
                return f"Tareas:\n{t_txt}\n\nRecordatorios:\n{r_txt}"

            elif nombre == "agregar_tarea":
                from core.tareas import agregar_tarea, agregar_recordatorio
                titulo     = args.get("titulo", "")
                fecha_hora = args.get("fecha_hora", "")
                if fecha_hora:
                    agregar_recordatorio(titulo, fecha_hora)
                    return f"Recordatorio '{titulo}' agregado para {fecha_hora}."
                else:
                    agregar_tarea(titulo)
                    return f"Tarea '{titulo}' agregada."

            elif nombre == "ver_clima":
                from core.clima import obtener_ubicacion, obtener_clima
                loc   = await loop.run_in_executor(None, obtener_ubicacion)
                clima = await loop.run_in_executor(None, lambda: obtener_clima(loc.get("ciudad", "")))
                if clima.get("ok"):
                    return (f"En {clima['ciudad']}: {clima['temp_c']}°C, {clima['desc']}. "
                            f"Humedad {clima['humedad']}%.")
                return "No pude obtener el clima."

            elif nombre == "ver_sistema":
                from core.sistema_info import obtener_metricas
                m = await loop.run_in_executor(None, obtener_metricas)
                return (f"CPU: {m['cpu_uso']}%, RAM: {m['ram_usado']}/{m['ram_total']} "
                        f"({m['ram_porcentaje']}%), Disco libre: {m['disco_libre']}.")

            else:
                return f"Herramienta '{nombre}' no reconocida."

        except Exception as e:
            return f"Error: {e}"

    def _estado(self, estado: str):
        if self.callback_estado:
            self.callback_estado(estado)