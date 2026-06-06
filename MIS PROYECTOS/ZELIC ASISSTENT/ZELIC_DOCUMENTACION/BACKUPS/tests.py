"""
test_live_basico.py
Prueba mínima de Gemini Live API — solo terminal, sin interfaz.
Basado exactamente en el ejemplo oficial de Google.

Uso: python test_live_basico.py
Presiona Ctrl+C para salir.
"""

import asyncio
import pyaudio
from google import genai
from google.genai import types
from CONFIG.config import API_KEY

# ── Constantes ─────────────────────────────────────────────────────────────────
MODEL          = "gemini-3.1-flash-live-preview"
TASA_ENVIO     = 16000
TASA_RECEPCION = 24000
CHUNK          = 1024
FORMAT         = pyaudio.paInt16
CHANNELS       = 1

pya = pyaudio.PyAudio()

async def main():
    client = genai.Client(api_key=API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text="Eres Zelic, una asistente concisa y formal, Responde siempre en español.")]
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            turn_coverage="TURN_INCLUDES_ONLY_ACTIVITY",
        ),
    )

    print("Conectando a Gemini Live...")

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("✅ Conectado. Habla ahora. Ctrl+C para salir.\n")

        # Stream de entrada (micrófono)
        mic = pya.open(
            format=FORMAT, channels=CHANNELS,
            rate=TASA_ENVIO, input=True,
            frames_per_buffer=CHUNK
        )

        # Stream de salida (parlantes)
        speaker = pya.open(
            format=FORMAT, channels=CHANNELS,
            rate=TASA_RECEPCION, output=True,
            frames_per_buffer=CHUNK
        )

        async def enviar():
            print("[Mic activo]")
            while True:
                datos = await asyncio.to_thread(
                    mic.read, CHUNK, False
                )
                await session.send_realtime_input(
                    audio=types.Blob(data=datos, mime_type="audio/pcm;rate=16000")
                )

        async def recibir():
            while True:
                async for resp in session.receive():
                    sc = resp.server_content
                    if not sc:
                        continue

                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                speaker.write(part.inline_data.data)

                    if sc.input_transcription and sc.input_transcription.text:
                        print(f"Tú:    {sc.input_transcription.text}")

                    if sc.output_transcription and sc.output_transcription.text:
                        print(f"Zelic: {sc.output_transcription.text}")

                    if sc.turn_complete:
                        print()

        try:
            await asyncio.gather(enviar(), recibir())
        except KeyboardInterrupt:
            print("\nCerrando...")
        finally:
            mic.stop_stream()
            mic.close()
            speaker.stop_stream()
            speaker.close()
            pya.terminate()

asyncio.run(main())