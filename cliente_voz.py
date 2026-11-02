"""
Cliente de voz: graba por microfono, lo manda a Dialogflow y reproduce
la respuesta hablada.

ANTES DE EJECUTAR:
  1. Crea una cuenta de servicio en Google Cloud (IAM -> Cuentas de servicio)
     con el rol "Dialogflow API Client".
  2. Generar una clave JSON en el apartado claves dentro de la cuenta de servicio y descargarla.
  3. Apuntar a ella con la variable de entorno:
       Windows : GOOGLE_APPLICATION_CREDENTIALS=C:\\ruta\\clave.json

  El JSON es una contraseña. Al .gitignore antes de nada.

Uso:
    python cliente_voz.py
"""

import os
import uuid
import wave
from pathlib import Path

import sounddevice as sd
from google.cloud import dialogflow
from dotenv import load_dotenv

# Configuracion

load_dotenv(Path(__file__).resolve().parent / ".env")

PROJECT_ID = os.environ.get("DIALOGFLOW_PROJECT_ID", "my-project-agente-v1") # Aqui poned vuestro ID de proyecto de Dialogflow, está puesto el mío
IDIOMA = "es"
FS = 16000          # Dialogflow espera 16 kHz para LINEAR_16
SEGUNDOS = 5

# El SESSION_ID identifica la CONVERSACION. Los contextos, los parametros
# guardados y los follow-up viven colgados de el. Si lo generais nuevo en cada
# llamada, cada frase empieza de cero: sin slot filling y sin memoria.
# Uno por conversacion, no uno por frase.
SESSION_ID = str(uuid.uuid4())

clientes = dialogflow.SessionsClient()
sesion = clientes.session_path(PROJECT_ID, SESSION_ID)


# Grabacion y reproduccion

def escuchar(segundos: int = SEGUNDOS) -> bytes:
    print(f"\nHabla ({segundos}s)...")
    audio = sd.rec(int(segundos * FS), samplerate=FS, channels=1, dtype="int16")
    sd.wait()
    print("Procesando...")
    return audio.tobytes()


def reproducir(wav_bytes: bytes, fichero: str = "respuesta.wav") -> None:
    """
    El audio que devuelve Dialogflow en LINEAR_16 ya es un WAV completo:
    el base64 empieza por 'UklGRg', que decodificado es 'RIFF', la cabecera
    de un fichero WAV. Vamos, que lo podéis escuchar directamente.
    """
    with open(fichero, "wb") as f:
        f.write(wav_bytes)

    with wave.open(fichero, "rb") as w:
        datos = w.readframes(w.getnframes())
        tasa = w.getframerate()

    import numpy as np
    muestras = np.frombuffer(datos, dtype=np.int16)
    sd.play(muestras, tasa)
    sd.wait()


# Llamada a Dialogflow

def hablar_con_el_agente(audio_bytes: bytes):
    entrada = dialogflow.QueryInput(
        audio_config=dialogflow.InputAudioConfig(
            audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
            language_code=IDIOMA,
            sample_rate_hertz=FS,
        )
    )

    salida = dialogflow.OutputAudioConfig(
        audio_encoding=dialogflow.OutputAudioEncoding.OUTPUT_AUDIO_ENCODING_LINEAR_16
    )

    return clientes.detect_intent(
        request={
            "session": sesion,
            "query_input": entrada,
            "input_audio": audio_bytes,
            "output_audio_config": salida,
        }
    )


# Bucle de conversacion

def main():
    print("=" * 55)
    print("Cliente de voz de Dialogflow")
    print(f"Proyecto : {PROJECT_ID}")
    print(f"Sesion   : {SESSION_ID}")
    print("Enter para hablar, 'q' + Enter para salir.")
    print("=" * 55)

    while True:
        if input("\n> ").strip().lower() == "q":
            break

        respuesta = hablar_con_el_agente(escuchar())
        r = respuesta.query_result

        # query_text es vuestro speech-to-text. No hemos llamado a ningun
        # servicio de transcripcion: va dentro del mismo detect_intent.
        print(f"  Has dicho  : {r.query_text}")
        print(f"  Intencion  : {r.intent.display_name} ({r.intent_detection_confidence:.2f})")
        print(f"  Parametros : {dict(r.parameters) if r.parameters is not None else {}}")
        print(f"  Responde   : {r.fulfillment_text}")

        if respuesta.output_audio:
            reproducir(respuesta.output_audio)


if __name__ == "__main__":
    main()
