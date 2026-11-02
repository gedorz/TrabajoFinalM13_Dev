"""Último intercambio de negocio para diagnosticar contextos de Dialogflow."""

import json
import logging
from pathlib import Path

RUTA_DIAGNOSTICO = Path(__file__).with_name("ultimo_webhook.json")


def registrar_intercambio(body: dict, respuesta: dict) -> None:
    resultado = body["queryResult"]
    registro = {
        "session": body.get("session"),
        "intencion": resultado["intent"]["displayName"],
        "parametros": resultado.get("parameters", {}),
        "contextos_recibidos": resultado.get("outputContexts", []),
        "contextos_devueltos": respuesta.get("outputContexts", []),
        "respuesta": respuesta.get("fulfillmentText", ""),
        "mensajes_devueltos": respuesta.get("fulfillmentMessages", []),
    }
    try:
        RUTA_DIAGNOSTICO.write_text(
            json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logging.exception("No se pudo guardar el diagnóstico del webhook")
