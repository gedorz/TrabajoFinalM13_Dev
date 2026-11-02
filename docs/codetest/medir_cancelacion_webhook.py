"""Compara una cancelación simulada por localhost y por el túnel público."""

import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid


def crear_peticion():
    sesion = f"projects/my-project-agente-v1/locations/global/agent/sessions/diagnostico-{uuid.uuid4()}"
    return {
        "session": sesion,
        "responseId": str(uuid.uuid4()),
        "queryResult": {
            "queryText": "no",
            "intent": {"displayName": "solicitar_producto_amazon - no"},
            "parameters": {},
            "allRequiredParamsPresent": True,
            "outputContexts": [{
                "name": f"{sesion}/contexts/solicitar_producto_amazon-followup",
                "parameters": {
                    "codigo_sku": "ESP32-LX6D-WBT-4M",
                    "ubicacion": "Barcelona",
                    "referencia": "DEMO-DIAGNOSTICO",
                    "estado": "pendiente",
                },
            }],
        },
    }


def medir(url, cuerpo):
    peticion = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    inicio = time.perf_counter()
    resultado = {"url": url}
    try:
        with urllib.request.urlopen(peticion, timeout=8) as respuesta:
            resultado["http"] = respuesta.status
            resultado["respuesta"] = json.load(respuesta)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        resultado["error"] = str(error)
    resultado["segundos"] = round(time.perf_counter() - inicio, 3)
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", help="URL completa; admite varias")
    parser.add_argument("--resultado", type=Path)
    opciones = parser.parse_args()
    cuerpo = crear_peticion()
    direcciones = opciones.url or (
        "http://127.0.0.1:8000/webhook",
        "https://1s8sngz1-8000.eun1.devtunnels.ms/webhook",
    )
    resultados = [medir(url, cuerpo) for url in direcciones]
    informe = {
        "tipo": "POST directo; no es una llamada desde Dialogflow",
        "sesion_independiente": cuerpo["session"],
        "resultados": resultados,
    }
    destino = opciones.resultado or (
        Path(__file__).resolve().parents[2] / "documentos/evidencias/cancelacion-mediciones.json"
    )
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    for resultado in resultados:
        print(json.dumps(resultado, ensure_ascii=False))
    return 0 if all(
        r.get("http") == 200 and r.get("respuesta", {}).get("fulfillmentText")
        == "Solicitud cancelada. No se ha realizado ninguna compra."
        for r in resultados
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
