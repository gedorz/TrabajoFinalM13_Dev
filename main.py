"""
Webhook de Dialogflow ES en FastAPI.

Arrancar:
    python -m venv .venv
    .venv\\Scripts\\activate          # Windows
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Despues: exponer el puerto 8000 a internet (PORTS -> Port Visibility -> Public,
o ngrok http 8000) y pegar la URL + /webhook en Fulfillment.

Acordaos de activar "Enable webhook call for this intent" EN CADA INTENCION.
"""

import logging
import os
import re

from fastapi import FastAPI, Request
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from starlette.concurrency import run_in_threadpool

from documentacion_ocr import cargar_documentos
from negocio import gestionar_negocio, responder
from docs.dialogflow.diagnostico import registrar_intercambio
from docs.dialogflow.ayuda_voz import responder_ayuda_sku
from docs.dialogflow.respuestas_voz import agregar_ssml

load_dotenv()  # carga GOOGLE_API_KEY desde el .env

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

# Datos de negocio simulados
#
# En un sistema real esto seria una consulta a base de datos. Para la entrega
# un diccionario vale perfectamente: lo que se evalua es que la respuesta la
# decide vuestro codigo, no una plantilla de Dialogflow.

PRODUCTOS = {
    "ESP32-LX6D-WBT-4M": {
        "titular": "ESP32 original, Procesador Xtensa LX6 Dual-core",
        "marca": "Xtensa",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-LX6D-WBT-16M": {
        "titular": "ESP32 original, Procesador Xtensa LX6 Dual-core, Wi-Fi + Bluetooth",
        "marca": "Xtensa",
        "ubicacion": "Barcelona",
        "disponible": False,
        "costo": 35
    },
    "ESP32-S2S-W-4M": {
        "titular": "Serie S2 Single-core (LX7), Solo Wi-Fi",
        "marca": "Xtensa",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-S3D-WBLE-8M8R": {
        "titular": "Serie S3 Dual-core (LX7), Wi-Fi + BLE 5.0, 8MB Flash + 8MB PSRAM",
        "marca": "Xtensa",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-S3D-WBLE-16M8R": {
        "titular": "Serie S3 Dual-core (LX7), Wi-Fi + BLE 5.0, 16MB Flash + 8MB PSRAM",
        "marca": "Xtensa",
        "ubicacion": "Barcelona",
        "disponible": False,
        "costo": 35
    },
    "ESP32-C2S-WBLE-2M": {
        "titular": "Serie C2 RISC-V Single-core, Wi-Fi + BLE, 2MB Flash",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-C3S-WBLE-4M": {
        "titular": "Serie C3 RISC-V Single-core, Wi-Fi + BLE, 4MB Flash",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-C5S-W6DB-4M": {
        "titular": "Serie C5 RISC-V Single-core, Wi-Fi 6 Doble Banda + BLE, 4MB Flash",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25,
    },
    "ESP32-C6S-W6ZT-8M": {
        "titular": "Serie C6 RISC-V Single-core, Wi-Fi 6 + Zigbee/Thread + BLE, 8MB Flash",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-H2S-ZBLE-4M": {
        "titular": "Serie H2 RISC-V Single-core, Sin Wi-Fi (Solo Zigbee/Thread + BLE), 4MB Flash",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": True,
        "costo": 25
    },
    "ESP32-P4D-NC-16R": {
        "titular": "Serie P4 RISC-V Dual-core (400MHz), No Connectivity, 16MB PSRAM",
        "marca": "RISC-V",
        "ubicacion": "Barcelona",
        "disponible": False,
        "costo": 35
    },
}



# Documentos para la respuesta documental (OCR)
# Se lee el corpus generado offline; Tesseract no se ejecuta en el servidor.

print("Cargando texto OCR persistido...")
DOCUMENTOS = cargar_documentos()
print(f"Documentos cargados: {len(DOCUMENTOS)}\n")


# Endpoint

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    resultado = body["queryResult"]
    intencion = resultado["intent"]["displayName"]
    pregunta = resultado.get("queryText", "")

    registrar_intercambio(body, {})
    respuesta = responder_ayuda_sku(body, PRODUCTOS)
    if respuesta is None:
        respuesta = gestionar_negocio(body, PRODUCTOS)
    if respuesta is None:
        if intencion in ("consulta_especificaciones_producto", "Default Fallback Intent"):
            respuesta = await run_in_threadpool(gestionar_fallback, pregunta)
        else:
            respuesta = responder("Todavía no sé gestionar esa petición.")
    respuesta = agregar_ssml(respuesta)
    registrar_intercambio(body, respuesta)
    return respuesta


@app.get("/")
def raiz():
    """Para comprobar de un vistazo que el tunel llega hasta aqui."""
    return {"estado": "ok", "documentos_cargados": len(DOCUMENTOS)}


# Fallback con modelo de lenguaje + RAG sobre los documentos
#
# Requiere:  pip install google-genai python-dotenv
# y una variable de entorno GOOGLE_API_KEY 

cliente = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

INSTRUCCIONES = """Eres el asistente telefónico de kit robotic.
Respondes en español, en dos o tres frases como mucho, porque tu respuesta
se va a convertir en voz. No inventes datos concretos de productos, precios ni
marcas. Si no sabes algo, dilo claramente y ofrece pasar con un agente."""

PLANTILLA = """Responde a la pregunta del usuario usando UNICAMENTE la
informacion del CONTEXTO que viene a continuacion. Si la respuesta no
esta en el contexto, di que no dispones de ese dato y ofrece pasar con
un agente. No completes con conocimiento propio.

CONTEXTO:
{contexto}

PREGUNTA: {pregunta}"""


def seleccionar_documentos(pregunta: str, n: int = 2) -> str:
    """
    Recuperacion pobre: cuenta cuantas palabras de la pregunta aparecen en
    cada documento y se queda con los n mejores.

    Funciona con 5 documentos y se derrumba con 500, porque busca coincidencia
    literal: si el documento dice "datasheet" y el usuario dice "especificación", no
    encuentra nada. Ese problema exacto es el que resuelven los embeddings y
    las bases vectoriales (extra del enunciado).

    Si vuestros documentos son pocos y cortos, no filtreis: devolved todos.
    Se llama context stuffing y es valido para el minimo.
    """
    if not DOCUMENTOS:
        return ""

    palabras = set(re.findall(r"\w{4,}", pregunta.lower()))

    puntuados = []
    for nombre, texto in DOCUMENTOS.items():
        coincidencias = sum(1 for p in palabras if p in texto.lower())
        puntuados.append((coincidencias, nombre, texto))

    puntuados.sort(key=lambda x: x[0], reverse=True)
    elegidos = [t for c, _, t in puntuados[:n] if c > 0]

    return "\n\n---\n\n".join(elegidos)


def preguntar_al_modelo(prompt: str) -> str:
    respuesta = cliente.models.generate_content(
        model=MODELO_GEMINI,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES,
            temperature=0.1,
            max_output_tokens=150,
            # Esto es para no dejar al modelo llamar a funciones de python
            # por su cuenta
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        ),
    )
    return respuesta.text.strip()


def gestionar_fallback(pregunta: str) -> dict:
    contexto = seleccionar_documentos(pregunta)

    if not contexto:
        return responder(
            "No tengo documentación sobre eso. ¿Quieres que te pase con un agente?"
        )

    prompt = PLANTILLA.format(contexto=contexto, pregunta=pregunta)

    # El try/except no es decorativo: si el modelo falla o tarda, hay que
    # devolver algo igualmente. Dialogflow corta a los 5 segundos y un webhook
    # que lanza una excepcion deja al usuario escuchando un silencio.
    try:
        return responder(preguntar_al_modelo(prompt))
    except Exception as e:
        if isinstance(e, errors.APIError) and e.code == 503:
            logger.error(
                "LLM NO DISPONIBLE | HTTP 503 UNAVAILABLE | modelo=%s | "
                "Gemini no está disponible temporalmente. "
                "Puede deberse a alta demanda; vuelve a intentarlo más tarde.",
                MODELO_GEMINI,
            )
        else:
            logger.error("ERROR LLM | modelo=%s | %s", MODELO_GEMINI, e)
        return responder(
            "Ahora mismo no puedo responder a eso. ¿Quieres que te pase con un agente?"
        )
