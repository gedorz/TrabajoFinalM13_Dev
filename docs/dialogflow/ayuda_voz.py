"""Respuestas habladas para confirmar o repetir un SKU dudoso."""


def responder_ayuda_sku(body: dict, productos: dict) -> dict | None:
    payload = body.get("originalDetectIntentRequest", {}).get("payload", {})
    ayuda = payload.get("ayuda_sku")
    if not isinstance(ayuda, dict):
        return None
    tipo = ayuda.get("tipo")
    if tipo == "escuchar_confirmacion":
        return {"fulfillmentText": "", "payload": {"ayuda_sku": {"tipo": tipo}}}
    if tipo == "confirmar" and ayuda.get("codigo") in productos:
        codigo = ayuda["codigo"]
        return {"payload": {"ayuda_sku": {"tipo": tipo, "codigo": codigo}}, "fulfillmentText": (
            f"¿Te refieres a {productos[codigo]['titular']}, código {codigo}? "
            "Confirma el código respondiendo sí o no."
        )}
    return {"payload": {"ayuda_sku": {"tipo": "repetir"}}, "fulfillmentText": (
        "Todavía no he confirmado el producto. Repite el código completo "
        "o di placa uno para el ESP32 clásico de cuatro megas."
    )}
