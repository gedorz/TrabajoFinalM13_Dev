"""Consultas de catálogo y solicitudes simuladas para Dialogflow ES."""

import re
import uuid

from docs.dialogflow.pistas_voz import ALIAS_SKU

CONTEXTO_SOLICITUD = "solicitar_producto_amazon-followup"
PATRON_SKU = r"(?i)\bESP32(?:-[A-Z0-9]+){2,4}\b"
INTENCION_SOLICITUD = "solicitar_producto_amazon"
INTENCION_SI = f"{INTENCION_SOLICITUD} - yes"
INTENCION_NO = f"{INTENCION_SOLICITUD} - no"


def responder(texto: str) -> dict:
    return {"fulfillmentText": texto}


def normalizar_codigo_producto(valor: str) -> str:
    alias = " ".join(valor.casefold().split())
    valor = ALIAS_SKU.get(alias, valor)
    return valor.upper().replace(" ", "").strip()


def obtener_contexto(body: dict) -> dict:
    nombre = f"{body.get('session', '')}/contexts/{CONTEXTO_SOLICITUD}"
    for contexto in body["queryResult"].get("outputContexts", []):
        # En el turno de cierre Dialogflow puede enviar los parámetros sin
        # lifespanCount (cero por defecto). Siguen siendo válidos para este turno.
        if contexto.get("name") == nombre:
            return contexto.get("parameters", {})
    return {}


def responder_con_contexto(body: dict, texto: str, parametros: dict) -> dict:
    respuesta = responder(texto)
    respuesta["outputContexts"] = [
        {
            "name": f"{body['session']}/contexts/{CONTEXTO_SOLICITUD}",
            "lifespanCount": 3 if parametros else 0,
            "parameters": parametros,
        }
    ]
    return respuesta


def buscar_producto(parametros: dict, productos: dict) -> tuple:
    codigo = normalizar_codigo_producto(parametros.get("codigo_sku") or "")
    if not re.fullmatch(PATRON_SKU, codigo):
        return codigo, None, "El SKU no tiene un formato válido, como ESP32-LX6D-WBT-4M."
    producto = productos.get(codigo)
    if producto is None:
        return codigo, None, f"No encuentro el SKU {codigo} en nuestro catálogo."
    return codigo, producto, ""


def comprobar_disponibilidad(producto: dict, ubicacion: str) -> str:
    if not producto["disponible"]:
        return "Este producto no está disponible para venta."
    if ubicacion.casefold() != producto["ubicacion"].casefold():
        return f"Este producto solo está disponible en {producto['ubicacion']}."
    return ""


def preparar_solicitud(body: dict, productos: dict) -> dict:
    resultado = body["queryResult"]
    if not resultado.get("allRequiredParamsPresent", False):
        # Dialogflow continúa con sus preguntas de parámetros obligatorios.
        return {}
    parametros = resultado.get("parameters", {})
    codigo, producto, error = buscar_producto(parametros, productos)
    ubicacion = (parametros.get("ubicacion") or "").strip()
    if not error and not ubicacion:
        error = "Necesito la ciudad de la tienda. Vuelve a iniciar la solicitud."
    if not error:
        error = comprobar_disponibilidad(producto, ubicacion)
    if error:
        return responder_con_contexto(
            body, f"{error} Puedes iniciar otra solicitud con los datos correctos.", {}
        )
    # Una misma petición reintentada conserva la referencia del prototipo.
    identificador = body.get("responseId") or str(uuid.uuid4())
    referencia = uuid.uuid5(uuid.NAMESPACE_URL, f"{body['session']}:{identificador}")
    pendientes = {
        "codigo_sku": codigo,
        "ubicacion": producto["ubicacion"],
        "referencia": f"DEMO-{referencia.hex[:12].upper()}",
        "estado": "pendiente",
    }
    return responder_con_contexto(
        body,
        f"Prepararemos una solicitud de prueba de {codigo}, {producto['titular']}, "
        f"por {producto['costo']} euros en {producto['ubicacion']}. "
        "¿Confirmas? Responde sí o no.",
        pendientes,
    )


def finalizar_solicitud(body: dict, productos: dict, confirmar: bool) -> dict:
    pendientes = obtener_contexto(body)
    if pendientes.get("estado") != "pendiente" or not pendientes.get("referencia"):
        return responder_con_contexto(
            body, "No hay una solicitud pendiente. Indica primero qué quieres comprar.", {}
        )
    if not confirmar:
        return responder_con_contexto(
            body, "Solicitud cancelada. No se ha realizado ninguna compra.", {}
        )
    codigo, producto, error = buscar_producto(pendientes, productos)
    if not error:
        error = comprobar_disponibilidad(producto, pendientes.get("ubicacion", ""))
    if error:
        return responder_con_contexto(body, error, {})
    return responder_con_contexto(
        body,
        f"Solicitud de prueba {pendientes['referencia']} confirmada para {codigo} "
        f"en {producto['ubicacion']}, por {producto['costo']} euros. "
        "Es una simulación: no se ha realizado una compra ni un envío real.",
        {},
    )


def consultar_catalogo(parametros: dict, productos: dict) -> dict:
    marca = (parametros.get("marca") or "").casefold()
    codigos = [
        codigo
        for codigo, producto in productos.items()
        if not marca or marca in producto["marca"].casefold() or marca in codigo.casefold()
    ]
    if not codigos:
        return responder("No tengo productos de esa marca en el catálogo de prueba.")
    return responder(
        f"Hay {len(codigos)} modelos en el catálogo para esa consulta. "
        f"Por ejemplo, {', '.join(codigos[:2])}. "
        "Puedes preguntar por la disponibilidad de un SKU o solicitarlo."
    )


def gestionar_negocio(body: dict, productos: dict) -> dict | None:
    resultado = body["queryResult"]
    intencion = resultado["intent"]["displayName"]
    parametros = resultado.get("parameters", {})
    if intencion == INTENCION_SOLICITUD:
        return preparar_solicitud(body, productos)
    if intencion in (INTENCION_SI, INTENCION_NO):
        return finalizar_solicitud(body, productos, intencion == INTENCION_SI)
    if intencion == "Consultar_productos":
        return consultar_catalogo(parametros, productos)
    if intencion == "consultar_disponibiliadad":
        if not resultado.get("allRequiredParamsPresent", False):
            return {}
        codigo, producto, error = buscar_producto(parametros, productos)
        if error:
            return responder(error)
        disponible = "está disponible" if producto["disponible"] else "no está disponible"
        return responder(
            f"El producto {codigo} {disponible} en {producto['ubicacion']}. "
            f"Su precio de catálogo es {producto['costo']} euros."
        )
    return None
