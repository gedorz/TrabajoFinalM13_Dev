"""Prueba de propuesta real usando una transcripción simulada del registro del usuario."""

import json
from pathlib import Path
import uuid

from google.cloud import dialogflow as df

from archivos_audio import cargar_audio
from audio_voz import recortar_silencio
import cliente_voz as voz

RAIZ = Path(__file__).resolve().parents[2]
SKU = "ESP32-LX6D-WBT-4M"


def main():
    archivos = sorted((RAIZ / "AudioEntrenamiento").glob("*.m4a"))
    voz.SESSION_ID = f"propuesta-{uuid.uuid4().hex}"
    voz.contextos_conversacion = []
    voz.propuesta_sku = None
    voz.contextos_propuesta = []
    registros = []

    def registrar(etapa, respuesta):
        resultado = respuesta.query_result
        diagnostico = resultado.diagnostic_info or {}
        registro = {
            "etapa": etapa,
            "transcripcion": diagnostico.get("transcripcion_original", resultado.query_text),
            "parametros": dict(resultado.parameters or {}),
            "respuesta": resultado.fulfillment_text,
            "webhook_codigo": respuesta.webhook_status.code,
            "audio_respuesta_bytes": len(respuesta.output_audio),
            "propuesta_pendiente": voz.propuesta_sku,
        }
        registros.append(registro)
        print(json.dumps(registro, ensure_ascii=True), flush=True)
        if respuesta.webhook_status.code:
            raise RuntimeError(respuesta.webhook_status.message)
        return resultado

    def enviar_archivo(indice, **opciones):
        return voz.hablar_con_el_agente(
            recortar_silencio(cargar_audio(archivos[indice])), **opciones
        )

    try:
        registrar("inicio_audio_real", enviar_archivo(0))
        simulada = df.DetectIntentResponse(query_result=df.QueryResult(
            query_text="esp32 lx6 DWV 4m", speech_recognition_confidence=0.44,
            intent=df.Intent(display_name="consultar_disponibiliadad"),
            parameters={"codigo_sku": ""},
        ))
        propuesta = voz.resolver_codigo_de_voz(simulada, list(voz.contextos_conversacion))
        resultado = registrar("sku_transcripcion_simulada", propuesta)
        voz.contextos_conversacion = list(resultado.output_contexts)
        assert voz.propuesta_sku == SKU
        assert not (resultado.parameters or {}).get("codigo_sku")
        assert propuesta.output_audio
        assert "¿Te refieres" in resultado.fulfillment_text
        resultado = registrar("confirmacion_codigo_audio_real", enviar_archivo(3, esperando_sku=True))
        assert resultado.parameters.get("codigo_sku") == SKU
        registrar("ciudad_audio_real", enviar_archivo(2, esperando_ubicacion=True))
        resultado = registrar("cancelacion_compra_audio_real", enviar_archivo(4))
        assert "cancelada" in resultado.fulfillment_text
        print("OK: propuesta hablada, código confirmado y solicitud cancelada", flush=True)
    finally:
        destino = RAIZ / "docs" / "codetest" / "voz_propuesta_sku.json"
        destino.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
