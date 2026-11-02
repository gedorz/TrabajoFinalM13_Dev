"""Compara las cuatro confirmaciones usando la secuencia STT del cliente real."""

import hashlib
import json
from pathlib import Path
import re
import unicodedata
import uuid
from unittest.mock import patch

from google.cloud import dialogflow

from archivos_audio import cargar_audio
from audio_voz import recortar_silencio
import cliente_voz as voz

RAIZ = Path(__file__).resolve().parents[2]
CASOS = {
    "4_Respuesta_positiva.m4a": "estoy de acuerdo",
    "5_Respuesta_negativa.m4a": "no cancela el pedido",
    "si.m4a": "sí",
    "no.m4a": "no",
}


def comparar(texto):
    sin_acentos = "".join(
        letra for letra in unicodedata.normalize("NFKD", texto.casefold())
        if not unicodedata.combining(letra)
    )
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sin_acentos).split())


class ClienteAuditado:
    def __init__(self):
        self.cliente = dialogflow.SessionsClient()
        self.intentos = []

    def session_path(self, *args):
        return self.cliente.session_path(*args)

    def detect_intent(self, request, **kwargs):
        self.intentos.append({
            "modelo": request["query_input"].audio_config.model,
            "audio_sha256": hashlib.sha256(request["input_audio"]).hexdigest(),
        })
        return self.cliente.detect_intent(request=request, **kwargs)


def main():
    cliente = ClienteAuditado()
    registros = []
    # Se prueba STT en el estado de confirmar código, sin aplicar una decisión
    # de negocio: los nombres/expectativas nunca se envían al reconocedor.
    with (
        patch.object(voz, "clientes", cliente),
        patch.object(voz, "resolver_codigo_de_voz", side_effect=lambda r, c: r),
    ):
        for nombre, esperado in CASOS.items():
            voz.SESSION_ID = f"confirmacion-{uuid.uuid4().hex}"
            voz.contextos_conversacion = []
            voz.contextos_propuesta = []
            voz.propuesta_sku = "ESP32-LX6D-WBT-4M"
            cliente.intentos = []
            audio = recortar_silencio(cargar_audio(RAIZ / "AudioEntrenamiento" / nombre))
            resultado = voz.hablar_con_el_agente(audio, esperando_sku=True).query_result
            registro = {
                "archivo": nombre, "esperado": esperado,
                "transcripcion": resultado.query_text,
                "confianza": resultado.speech_recognition_confidence,
                "duracion_segundos": len(audio) / 32000,
                "intentos": list(cliente.intentos),
                "correcto": comparar(resultado.query_text) == comparar(esperado),
                "misma_toma": len({i["audio_sha256"] for i in cliente.intentos}) == 1,
            }
            registros.append(registro)
            print(json.dumps(registro, ensure_ascii=True), flush=True)
    voz.propuesta_sku = None
    destino = RAIZ / "docs" / "codetest" / "voz_confirmaciones_cliente.json"
    destino.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(r["correcto"] and r["misma_toma"] for r in registros):
        raise SystemExit("Hay confirmaciones que siguen sin reconocerse correctamente")
    print("OK: cuatro confirmaciones reconocidas con la secuencia del cliente")


if __name__ == "__main__":
    main()
