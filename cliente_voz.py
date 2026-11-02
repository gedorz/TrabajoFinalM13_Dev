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

import argparse
import os
import uuid
import wave
from pathlib import Path

import sounddevice as sd
import numpy as np
from google.cloud import dialogflow
from dotenv import load_dotenv

from audio_voz import DetectorSilencio, recortar_silencio
from docs.dialogflow.pistas_voz import PISTAS_RECONOCIMIENTO_SKU

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

clientes = None


# Grabacion y reproduccion

def listar_microfonos() -> None:
    predeterminado = sd.default.device[0]
    for indice, dispositivo in enumerate(sd.query_devices()):
        if dispositivo["max_input_channels"] > 0:
            api = sd.query_hostapis(dispositivo["hostapi"])["name"]
            marca = " (predeterminado)" if indice == predeterminado else ""
            print(f"{indice}: {dispositivo['name']} [{api}]{marca}")


def escuchar(
    segundos: int = SEGUNDOS, microfono: int | None = None,
    recortar: bool = True,
) -> bytes:
    dispositivo = sd.query_devices(microfono, "input")
    indice_microfono = dispositivo["index"]
    sd.check_input_settings(
        device=indice_microfono, channels=1, dtype="int16", samplerate=FS
    )
    seleccion = " (predeterminado del sistema)" if microfono is None else ""
    print(f"Micrófono: {dispositivo['name']}{seleccion}")
    print("Preparando micrófono; espera al aviso 'Habla'...")
    audio = capturar_hasta_silencio(segundos, indice_microfono)
    pico = float(np.max(np.abs(audio.astype(np.float32)))) / 32768
    print(f"Nivel máximo grabado: {pico:.1%}")
    if pico < 0.001:
        print(
            "La grabación contiene silencio o un nivel muy bajo. "
            "Revisa el micrófono elegido, el botón de silencio y el volumen "
            "de entrada de Windows. No se enviará esta grabación a Dialogflow."
        )
        return b""
    grabacion = audio.tobytes()
    preparada = recortar_silencio(grabacion, FS) if recortar else grabacion
    print(
        f"Duración capturada: {len(grabacion) / (FS * 2):.2f}s; "
        f"audio preparado: {len(preparada) / (FS * 2):.2f}s "
        f"(recorte {'activado' if recortar else 'desactivado'})."
    )
    print("Procesando...")
    return preparada


def capturar_hasta_silencio(segundos: int, microfono: int) -> np.ndarray:
    if segundos <= 0:
        raise ValueError("La duración máxima debe ser mayor que cero")
    tamano_bloque = int(FS * 0.020)
    limite = int(segundos * FS)
    detector = DetectorSilencio(FS, segundos=3)
    bloques = []
    capturadas = 0
    aviso_desbordamiento = False
    with sd.InputStream(
        samplerate=FS, channels=1, dtype="int16",
        device=microfono, blocksize=tamano_bloque,
    ) as flujo:
        print(f"\nHabla (máximo {segundos}s; parada tras más de 3s de silencio)...", flush=True)
        while capturadas < limite:
            bloque, desbordamiento = flujo.read(min(tamano_bloque, limite - capturadas))
            if desbordamiento and not aviso_desbordamiento:
                print("ADVERTENCIA AUDIO: el dispositivo ha perdido muestras durante la captura.")
                aviso_desbordamiento = True
            bloques.append(bloque.copy())
            capturadas += len(bloque)
            if detector.actualizar(bloque):
                print("Grabación detenida: más de 3 segundos de silencio.")
                break
    return np.concatenate(bloques, axis=0)


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

    muestras = np.frombuffer(datos, dtype=np.int16)
    sd.play(muestras, tasa)
    sd.wait()


# Llamada a Dialogflow

def hablar_con_el_agente(audio_bytes: bytes, esperando_sku: bool = False):
    global clientes
    if clientes is None:
        clientes = dialogflow.SessionsClient()
    sesion = clientes.session_path(PROJECT_ID, SESSION_ID)
    entrada = dialogflow.QueryInput(
        audio_config=dialogflow.InputAudioConfig(
            audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
            language_code=IDIOMA,
            sample_rate_hertz=FS,
            # Las pistas explícitas sustituyen la adaptación automática.
            # Se aplican solo mientras se recoge el código del producto.
            speech_contexts=[
                dialogflow.SpeechContext(phrases=PISTAS_RECONOCIMIENTO_SKU, boost=10)
            ] if esperando_sku else [],
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

def probar_microfono(
    segundos: int, microfono: int | None, comprobar_reconocimiento: bool = False,
    recortar: bool = True,
) -> None:
    if comprobar_reconocimiento:
        print("Prueba de reconocimiento: se reproducirá y enviará la misma toma a Dialogflow.")
    else:
        print("Prueba local: la grabación no se guarda ni se envía a Dialogflow.")
    print("Cuando aparezca 'Habla', di: Hola, quiero iniciar una solicitud.")
    input("Pulsa Enter para empezar...")
    try:
        audio = escuchar(segundos, microfono, recortar=recortar)
        if not audio:
            return
        print("Reproduciendo lo que ha captado el micrófono...")
        sd.play(np.frombuffer(audio, dtype=np.int16), FS)
        sd.wait()
        print("Comprueba si oyes tu frase completa, clara y sin distorsión.")
        if comprobar_reconocimiento:
            print(f"Audio enviado: {len(audio)} bytes, {len(audio) / (FS * 2):.2f}s, mono PCM16, {FS} Hz.")
            respuesta = hablar_con_el_agente(audio)
            resultado = respuesta.query_result
            print(f"Has dicho: {resultado.query_text or '(sin transcripción)'}")
            print(f"Confianza de voz: {resultado.speech_recognition_confidence:.2f}")
            print(f"Intención: {resultado.intent.display_name or '(sin intención)'}")
            print(f"Respuesta: {resultado.fulfillment_text or '(sin respuesta)'}")
    except (sd.PortAudioError, ValueError) as error:
        print(f"ERROR AUDIO: {error}")


def leer_opciones():
    parser = argparse.ArgumentParser(description="Cliente de voz de Kitia")
    parser.add_argument(
        "--listar-microfonos", action="store_true", help="Muestra las entradas de audio"
    )
    parser.add_argument(
        "--probar-microfono", action="store_true",
        help="Graba y reproduce una prueba local, sin enviar audio a Dialogflow",
    )
    parser.add_argument(
        "--probar-reconocimiento", action="store_true",
        help="Graba, reproduce y envía la misma toma a Dialogflow para comparar",
    )
    parser.add_argument(
        "--microfono", type=int, default=None,
        help="Entrada de audio; si se omite, usa el micrófono predeterminado del sistema",
    )
    parser.add_argument("--segundos", type=int, default=SEGUNDOS, help="Duración de cada grabación")
    parser.add_argument(
        "--segundos-sku", type=int, default=12,
        help="Duración al dictar el SKU (12 segundos por defecto)",
    )
    parser.add_argument(
        "--sin-recorte-silencio", action="store_true",
        help="Envía la grabación completa para comparar con el recorte de bordes",
    )
    opciones = parser.parse_args()
    if opciones.segundos < 1 or opciones.segundos_sku < 1:
        parser.error("Las duraciones de grabación deben ser mayores que cero")
    return opciones


def main():
    opciones = leer_opciones()
    if opciones.listar_microfonos:
        listar_microfonos()
        return
    if opciones.probar_reconocimiento:
        probar_microfono(
            opciones.segundos, opciones.microfono, comprobar_reconocimiento=True,
            recortar=not opciones.sin_recorte_silencio,
        )
        return
    if opciones.probar_microfono:
        probar_microfono(
            opciones.segundos, opciones.microfono,
            recortar=not opciones.sin_recorte_silencio,
        )
        return
    print("=" * 55)
    print("Cliente de voz de Dialogflow")
    print(f"Proyecto : {PROJECT_ID}")
    print(f"Sesion   : {SESSION_ID}")
    print("Enter para hablar, 'q' + Enter para salir.")
    print("=" * 55)

    esperando_sku = False
    while True:
        if input("\n> ").strip().lower() == "q":
            break

        try:
            segundos = opciones.segundos_sku if esperando_sku else opciones.segundos
            if esperando_sku:
                print(
                    "Puedes decir 'placa uno' para ESP32-LX6D-WBT-4M "
                    "si has añadido el alias a la entidad codigo_sku en Dialogflow."
                )
            audio = escuchar(
                segundos, opciones.microfono, recortar=not opciones.sin_recorte_silencio
            )
        except (sd.PortAudioError, ValueError) as error:
            print(f"ERROR MICRÓFONO: {error}")
            print("Consulta las entradas con --listar-microfonos y elige una con --microfono ID.")
            continue
        if not audio:
            continue
        respuesta = hablar_con_el_agente(audio, esperando_sku=esperando_sku)
        r = respuesta.query_result

        if not r.query_text.strip() and not r.intent.display_name:
            print(
                "Dialogflow no ha reconocido palabras en la grabación. "
                "Habla después de 'Habla', prueba otra entrada con --microfono "
                "o aumenta la duración con --segundos 8."
            )
            continue

        esperando_sku = (
            r.intent.display_name in ("solicitar_producto_amazon", "consultar_disponibiliadad")
            and not r.parameters.get("codigo_sku")
        )

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
