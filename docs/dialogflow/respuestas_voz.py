"""SSML para las respuestas dinámicas de Dialogflow ES."""

from html import escape
import re

PATRON_VOZ = re.compile(r"(?<![\w-])ESP32(?:-[A-Z0-9]+){2,4}(?![\w-])|¿", re.IGNORECASE)


def crear_ssml(texto: str) -> str:
    partes = ["<speak>"]
    posicion = 0
    for coincidencia in PATRON_VOZ.finditer(texto):
        partes.append(escape(texto[posicion:coincidencia.start()]))
        valor = coincidencia.group()
        if valor == "¿":
            partes.append('<break time="180ms"/>¿')
        else:
            partes.append(f'<say-as interpret-as="characters">{escape(valor)}</say-as>')
        posicion = coincidencia.end()
    partes.append(escape(texto[posicion:]))
    partes.append("</speak>")
    return "".join(partes)


def agregar_ssml(respuesta: dict) -> dict:
    texto = respuesta.get("fulfillmentText")
    if not isinstance(texto, str) or not texto.strip():
        # Slot filling y la escucha de confirmaciones deben poder quedar vacíos.
        return respuesta
    return {
        **respuesta,
        "fulfillmentMessages": [{"text": {"text": [crear_ssml(texto)]}}],
    }
