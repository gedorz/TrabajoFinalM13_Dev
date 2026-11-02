"""Evalúa grabaciones reales contra Dialogflow, sin activar el micrófono."""

import argparse
import json
from pathlib import Path
import time
import uuid

from google.cloud import dialogflow

from archivos_audio import cargar_audio
from audio_voz import recortar_silencio
import cliente_voz as voz
from docs.dialogflow.pistas_voz import PISTAS_RECONOCIMIENTO_SKU

RAIZ = Path(__file__).resolve().parents[2]


def leer_opciones():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo", default="")
    parser.add_argument("--idioma", default=voz.IDIOMA)
    parser.add_argument("--recortar", action="store_true")
    parser.add_argument("--sin-pistas", action="store_true")
    parser.add_argument("--solo", default="")
    parser.add_argument("--resultado", default="baseline")
    parser.add_argument("--ciclos", action="store_true")
    parser.add_argument("--ciclo", choices=("positivo", "negativo"))
    parser.add_argument("--confirmaciones", action="store_true")
    return parser.parse_args()


def crear_planes(args):
    archivos = sorted((RAIZ / "AudioEntrenamiento").glob("*.m4a"))
    if args.confirmaciones:
        nombres = {"si.m4a", "no.m4a", "4_Respuesta_positiva.m4a", "5_Respuesta_negativa.m4a"}
        seleccionados = [archivo for archivo in archivos if archivo.name in nombres]
        if len(seleccionados) != len(nombres):
            raise ValueError("Faltan grabaciones de confirmaciones largas o cortas")
        return [("confirmaciones", seleccionados)]
    if not args.ciclos:
        return [("transcripciones", archivos)]
    originales = [archivo for archivo in archivos if archivo.name[:1] in "12345"]
    if len(originales) != 5:
        raise ValueError("Faltan las cinco grabaciones del ciclo original")
    planes = [
        ("positivo", originales[:4]),
        ("negativo", originales[:3] + originales[4:5]),
    ]
    return [plan for plan in planes if not args.ciclo or plan[0] == args.ciclo]


def transcribir_muestra(cliente, ruta, audio, args):
    pistas = []
    if ruta.name.startswith("2_") and not args.sin_pistas:
        pistas = [dialogflow.SpeechContext(phrases=PISTAS_RECONOCIMIENTO_SKU, boost=10)]
    elif args.confirmaciones:
        pistas = [dialogflow.SpeechContext(
            phrases=["sí", "no", "correcto", "de acuerdo", "no es correcto", "estoy de acuerdo"],
            boost=10,
        )]
    configuracion = dialogflow.InputAudioConfig(
        audio_encoding=dialogflow.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
        sample_rate_hertz=16000,
        language_code=args.idioma,
        model=args.modelo,
        speech_contexts=pistas,
    )
    return cliente.detect_intent(
        request={
            "session": cliente.session_path(voz.PROJECT_ID, f"evaluacion-{uuid.uuid4().hex}"),
            "query_input": dialogflow.QueryInput(audio_config=configuracion),
            "input_audio": audio,
            "query_params": dialogflow.QueryParameters(
                payload={"ayuda_sku": {"tipo": "escuchar_confirmacion"}}
            ) if args.confirmaciones else dialogflow.QueryParameters(),
        },
        timeout=20,
    )


def datos_respuesta(respuesta):
    resultado = respuesta.query_result
    diagnostico = resultado.diagnostic_info or {}
    return {
        "transcripcion": diagnostico.get("transcripcion_original", resultado.query_text),
        "texto_procesado": resultado.query_text,
        "confianza_voz": diagnostico.get(
            "confianza_voz_original", resultado.speech_recognition_confidence
        ),
        "intencion": resultado.intent.display_name,
        "parametros": dict(resultado.parameters or {}),
        "respuesta": resultado.fulfillment_text,
        "webhook_estado": {
            "codigo": respuesta.webhook_status.code,
            "mensaje": respuesta.webhook_status.message,
        },
    }


def evaluar_plan(ciclo, rutas, cliente, args):
    voz.SESSION_ID = f"evaluacion-{uuid.uuid4().hex}"
    voz.contextos_conversacion = []
    voz.propuesta_sku = None
    voz.contextos_propuesta = []
    esperando_sku = False
    esperando_ubicacion = False
    registros = []
    for ruta in rutas:
        if args.solo and not ruta.name.startswith(args.solo):
            continue
        audio = cargar_audio(ruta)
        original = len(audio) / 32000
        if args.recortar:
            audio = recortar_silencio(audio)
        registro = {
            "ciclo": ciclo, "archivo": ruta.name,
            "original_segundos": original, "enviado_segundos": len(audio) / 32000,
        }
        inicio = time.perf_counter()
        try:
            if args.ciclos:
                respuesta = voz.hablar_con_el_agente(
                    audio, esperando_sku=esperando_sku,
                    esperando_ubicacion=esperando_ubicacion,
                )
            else:
                respuesta = transcribir_muestra(cliente, ruta, audio, args)
            registro.update(datos_respuesta(respuesta))
            parametros = registro["parametros"]
            esperando_sku = (
                registro["intencion"] in ("solicitar_producto_amazon", "consultar_disponibiliadad")
                and not parametros.get("codigo_sku")
            )
            esperando_ubicacion = (
                registro["intencion"] == "solicitar_producto_amazon"
                and bool(parametros.get("codigo_sku"))
                and not parametros.get("ubicacion")
            )
        except Exception as error:
            registro["error"] = str(error)
        registro["latencia_segundos"] = round(time.perf_counter() - inicio, 3)
        registros.append(registro)
        print(json.dumps(registro, ensure_ascii=True), flush=True)
    return registros


def comprobar_ciclos(resultados, args):
    if not args.ciclos:
        return
    for ciclo, esperado in (("positivo", "confirmada"), ("negativo", "cancelada")):
        if args.ciclo and ciclo != args.ciclo:
            continue
        registros = [r for r in resultados if r["ciclo"] == ciclo]
        if len(registros) != 4 or esperado not in registros[-1].get("respuesta", ""):
            raise SystemExit(f"Ciclo {ciclo} incompleto")
        if registros[-1].get("webhook_estado", {}).get("codigo", 1):
            raise SystemExit(f"Ciclo {ciclo} con error de webhook en el cierre")
        errores_intermedios = sum(
            bool(r.get("webhook_estado", {}).get("codigo", 1)) for r in registros[:-1]
        )
        if errores_intermedios:
            print(
                f"ADVERTENCIA: ciclo {ciclo} con {errores_intermedios} "
                "errores de webhook intermedios; el cierre sí fue confirmado.",
                flush=True,
            )
        print(f"OK: ciclo {ciclo} completo", flush=True)


def main():
    args = leer_opciones()
    cliente = dialogflow.SessionsClient()
    if args.ciclos:
        voz.MODELO_VOZ = args.modelo or voz.MODELO_VOZ
        voz.IDIOMA = args.idioma
    resultados = []
    for ciclo, rutas in crear_planes(args):
        resultados.extend(evaluar_plan(ciclo, rutas, cliente, args))
    destino = RAIZ / "docs" / "codetest" / f"voz_{args.resultado}.json"
    destino.write_text(
        json.dumps({"configuracion": vars(args), "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    comprobar_ciclos(resultados, args)


if __name__ == "__main__":
    main()
