"""Genera el ZIP corregido: python -m docs.dialogflow.generar_agente."""

import argparse
import json
from pathlib import Path
import uuid
import zipfile

from negocio import CONTEXTO_SOLICITUD, PATRON_SKU
from docs.dialogflow.pistas_voz import PATRON_ALIAS_SKU

RAIZ = Path(__file__).resolve().parents[2]
SOLICITUD = "solicitar_producto_amazon"
DOCUMENTAL = "consulta_especificaciones_producto"


def mensaje(texto: str) -> dict:
    return {"type": "0", "lang": "es", "speech": [texto]}


def parametro(nombre: str, entidad: str, pregunta: str) -> dict:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"kitia/parametro/{nombre}")),
        "name": nombre,
        "required": True,
        "dataType": entidad,
        "value": f"${nombre}",
        "defaultValue": "",
        "isList": False,
        "prompts": [{"lang": "es", "value": pregunta}],
    }


def frase(*partes) -> dict:
    datos = []
    for parte in partes:
        dato = {"text": parte if isinstance(parte, str) else parte[0], "userDefined": False}
        if not isinstance(parte, str):
            dato.update(meta=parte[1], alias=parte[2], userDefined=True)
        datos.append(dato)
    identidad = json.dumps(datos, ensure_ascii=False)
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, identidad)),
        "data": datos,
        "isTemplate": False,
        "count": 0,
        "lang": "es",
        "updated": 0,
    }


def configurar_intenciones(archivos: dict) -> None:
    for ruta, intencion in archivos.items():
        if not ruta.startswith("intents/") or "_usersays_" in ruta:
            continue
        nombre = intencion["name"]
        respuesta = intencion["responses"][0]
        intencion["contexts"] = []
        respuesta["affectedContexts"] = []
        respuesta["messages"] = [mensaje("Ahora mismo no puedo completar la consulta. Inténtalo de nuevo.")]
        intencion["webhookUsed"] = nombre != "Default Welcome Intent"
        intencion["webhookForSlotFilling"] = False
        if nombre == "Default Welcome Intent":
            respuesta["messages"] = [mensaje(
                "Hola, soy el asistente de Kit Robotic. Puedes consultar productos, "
                "su disponibilidad, la documentación o iniciar una solicitud de prueba."
            )]
        elif nombre == SOLICITUD:
            respuesta["parameters"] = [
                parametro("codigo_sku", "@codigo_sku", "¿Qué producto quieres solicitar? Puedes decir placa uno para ESP32-LX6D-WBT-4M."),
                parametro("ubicacion", "@sys.geo-city", "¿En qué ciudad quieres recogerlo?"),
            ]
            respuesta["affectedContexts"] = [{"name": CONTEXTO_SOLICITUD, "lifespan": 3}]
            intencion["webhookForSlotFilling"] = True
        elif nombre in (f"{SOLICITUD} - yes", f"{SOLICITUD} - no"):
            intencion["contexts"] = [CONTEXTO_SOLICITUD]
            # El webhook necesita leer los datos antes de cerrar el contexto.
            # El cierre lo devuelve finalizar_solicitud tras confirmar o cancelar.
            respuesta["affectedContexts"] = []
            respuesta["parameters"] = []
            respuesta["messages"] = [mensaje(
                "No puedo cerrar la solicitud en este momento. Inténtalo de nuevo."
            )]
        elif nombre == "consultar_disponibiliadad":
            respuesta["parameters"] = [parametro(
                "codigo_sku", "@codigo_sku", "¿De qué SKU quieres conocer la disponibilidad?"
            )]
            intencion["webhookForSlotFilling"] = True
        elif nombre == DOCUMENTAL:
            # La pregunta completa llega al webhook; no se obliga a dar SKU
            # para consultar garantías, montaje u otros documentos generales.
            sku_opcional = parametro("codigo_sku", "@codigo_sku", "")
            sku_opcional.update(required=False, prompts=[])
            respuesta["parameters"] = [sku_opcional]


def configurar_frases(archivos: dict) -> None:
    sku = ("ESP32-LX6D-WBT-4M", "@codigo_sku", "codigo_sku")
    ciudad = ("Barcelona", "@sys.geo-city", "ubicacion")
    ejemplos = {
        "Default Welcome Intent": [frase(t) for t in ("hola", "buenos días", "buenas tardes", "quiero ayuda")],
        "Consultar_productos": [
            frase("¿Qué productos tenéis?"),
            frase("Muéstrame el catálogo"),
            frase("¿Qué placas vendéis?"),
            frase("¿Qué productos de ", ("Xtensa", "@Marca", "marca"), " tenéis?"),
            frase("Busco placas de ", ("RISC-V", "@Marca", "marca")),
            frase("¿Tenéis productos ", ("Arduino", "@Marca", "marca"), "?"),
        ],
        "consultar_disponibiliadad": [
            frase("¿Está disponible ", sku, "?"),
            frase("¿Tenéis existencias de ", sku, "?"),
            frase("Consulta la disponibilidad del producto ", sku),
            frase("¿Cuánto cuesta ", sku, "?"),
            frase("Quiero consultar el stock"),
            frase("Dime el precio de un producto"),
        ],
        SOLICITUD: [
            frase("Quiero solicitar ", sku, " en ", ciudad),
            frase("Quiero comprar ", sku),
            frase("Prepara una solicitud del producto ", sku),
            frase("Quiero iniciar una solicitud"),
            frase("Quiero comprar una placa"),
            frase("Quiero recoger un producto en ", ciudad),
        ],
        f"{SOLICITUD} - yes": [frase(t) for t in (
            "sí", "confirmo", "sí, los datos son correctos", "adelante", "de acuerdo", "confirmar solicitud"
        )],
        f"{SOLICITUD} - no": [frase(t) for t in (
            "no", "no confirmo", "cancela la solicitud", "no lo quiero", "prefiero cancelar", "los datos no son correctos"
        )],
        DOCUMENTAL: [
            frase("¿Qué garantía tienen las placas?"),
            frase("¿Cómo se monta el kit?"),
            frase("¿Qué voltaje admite ", sku, "?"),
            frase("Dame las especificaciones de ", sku),
            frase("¿Qué dice el manual sobre las conexiones?"),
            frase("Quiero consultar la documentación"),
            frase("¿Qué condiciones de devolución hay?"),
        ],
    }
    for nombre, frases in ejemplos.items():
        archivos[f"intents/{nombre}_usersays_es.json"] = frases


def mejorar_agente(archivos: dict) -> None:
    archivos["agent.json"]["description"] = (
        "Asistente de Kit Robotic: catálogo de placas, disponibilidad, solicitudes "
        "simuladas con confirmación y consultas sobre documentación OCR."
    )
    entidad = archivos["entities/codigo_sku.json"]
    entidad.update(isRegexp=True, isEnum=False, allowFuzzyExtraction=False)
    archivos["entities/codigo_sku_entries_es.json"] = [
        {"value": patron, "synonyms": [patron]}
        for patron in (PATRON_SKU, PATRON_ALIAS_SKU)
    ]
    marcas = {}
    for entrada in archivos["entities/Marca_entries_es.json"]:
        sinonimos = marcas.setdefault(entrada["value"], [])
        for sinonimo in entrada["synonyms"]:
            if sinonimo not in sinonimos:
                sinonimos.append(sinonimo)
    archivos["entities/Marca_entries_es.json"] = [
        {"value": valor, "synonyms": sinonimos} for valor, sinonimos in marcas.items()
    ]
    configurar_intenciones(archivos)
    configurar_frases(archivos)


def generar(origen: Path, destino: Path) -> None:
    if origen.resolve() == destino.resolve():
        raise ValueError("El archivo original debe conservarse como copia de seguridad.")
    with zipfile.ZipFile(origen) as archivo:
        archivos = {
            nombre: json.loads(archivo.read(nombre))
            for nombre in archivo.namelist()
            if nombre.endswith(".json")
        }
    mejorar_agente(archivos)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as archivo:
        for nombre, contenido in sorted(archivos.items()):
            archivo.writestr(nombre, json.dumps(contenido, ensure_ascii=False, indent=2))
    print(f"Agente generado: {destino}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origen", type=Path, default=RAIZ / "docs" / "Kitia.zip")
    parser.add_argument(
        "--destino", type=Path,
        default=RAIZ / "docs" / "dialogflow" / "Kitia_mejorado.zip",
    )
    args = parser.parse_args()
    generar(args.origen, args.destino)


if __name__ == "__main__":
    main()
