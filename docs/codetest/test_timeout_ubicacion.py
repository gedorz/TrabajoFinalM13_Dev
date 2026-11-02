"""Reintento acotado de ciudad y aislamiento de llamadas LLM lentas."""

import asyncio
import importlib
import json
import os
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi import Request
from google.cloud import dialogflow as df

import cliente_voz as voz

SKU = "ESP32-LX6D-WBT-4M"
SESION = "projects/prueba/agent/sessions/ubicacion"
CONTEXTO = df.Context(
    name=f"{SESION}/contexts/solicitar_producto_amazon_dialog_context",
    lifespan_count=2, parameters={"codigo_sku": SKU, "ubicacion": ""},
)


def respuesta(texto="Barcelona", ciudad="Barcelona", error=0):
    return df.DetectIntentResponse(
        query_result=df.QueryResult(
            query_text=texto, speech_recognition_confidence=0.76,
            intent=df.Intent(display_name="solicitar_producto_amazon"),
            parameters={"codigo_sku": SKU, "ubicacion": ciudad},
            output_contexts=[CONTEXTO], fulfillment_text="¿Confirmas?",
        ),
        webhook_status={"code": error},
    )


class TimeoutUbicacionTests(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()
        self.cliente.session_path.return_value = SESION
        for parche in (
            patch.object(voz, "clientes", self.cliente),
            patch.object(voz, "contextos_conversacion", [CONTEXTO]),
            patch.object(voz, "propuesta_sku", None),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def test_barcelona_con_timeout_reintenta_texto_con_sku_conservado(self):
        self.cliente.detect_intent.side_effect = [respuesta(error=4), respuesta()]
        with patch("builtins.print"):
            resultado = voz.hablar_con_el_agente(b"audio de Barcelona", esperando_ubicacion=True)
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        segunda = self.cliente.detect_intent.call_args.kwargs["request"]
        self.assertEqual(segunda["query_input"].text.text, "Barcelona")
        self.assertEqual(segunda["query_params"].contexts[0].parameters["codigo_sku"], SKU)
        self.assertEqual(resultado.webhook_status.code, 0)
        self.assertTrue(resultado.query_result.diagnostic_info["reintento_webhook_ubicacion"])
        self.assertEqual(resultado.query_result.diagnostic_info["transcripcion_original"], "Barcelona")

    def test_dos_timeouts_no_generan_tercer_intento_ni_pierden_contexto(self):
        self.cliente.detect_intent.side_effect = [respuesta(error=4), respuesta(error=4)]
        with patch("builtins.print"):
            resultado = voz.hablar_con_el_agente(b"audio", esperando_ubicacion=True)
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        self.assertEqual(resultado.webhook_status.code, 4)
        self.assertEqual(voz.contextos_conversacion, [CONTEXTO])

    def test_no_reintenta_compra_ni_ubicacion_dudosa_ni_otro_error(self):
        for datos, esperando in (
            (respuesta(texto="sí", error=4), False),
            (respuesta(texto="no entiendo", ciudad="", error=4), True),
            (respuesta(error=7), True),
        ):
            self.cliente.detect_intent.reset_mock()
            self.cliente.detect_intent.side_effect = None
            self.cliente.detect_intent.return_value = datos
            voz.hablar_con_el_agente(b"audio", esperando_ubicacion=esperando)
            self.assertEqual(self.cliente.detect_intent.call_count, 1)

    def test_ubicacion_correcta_sin_timeout_no_duplica_peticion(self):
        self.cliente.detect_intent.return_value = respuesta()
        resultado = voz.hablar_con_el_agente(b"audio", esperando_ubicacion=True)
        self.assertEqual(resultado.query_result.parameters["ubicacion"], "Barcelona")
        self.assertEqual(self.cliente.detect_intent.call_count, 1)

    def test_llm_lento_no_bloquea_peticion_de_negocio(self):
        with (
            patch.dict(os.environ, {"GOOGLE_API_KEY": "clave-de-prueba"}),
            patch("ocr.cargar_documentos", return_value={}),
            patch("google.genai.Client"),
        ):
            main = importlib.import_module("main")
        inicio = threading.Event()
        terminar = threading.Event()

        def llm_lento(pregunta):
            inicio.set()
            terminar.wait(timeout=3)
            return {"fulfillmentText": "Respuesta documental"}

        def peticion(intencion):
            async def recibir():
                body = {"session": SESION, "queryResult": {
                    "intent": {"displayName": intencion}, "parameters": {},
                    "queryText": "Consulta", "allRequiredParamsPresent": True,
                }}
                return {"type": "http.request", "body": json.dumps(body).encode()}
            return Request({"type": "http", "method": "POST", "path": "/webhook"}, recibir)

        async def comprobar():
            consulta = asyncio.create_task(main.webhook(peticion("consulta_especificaciones_producto")))
            try:
                self.assertTrue(await asyncio.to_thread(inicio.wait, 1))
                catalogo = await asyncio.wait_for(main.webhook(peticion("Consultar_productos")), 1)
                self.assertIn("catálogo", catalogo["fulfillmentText"])
                self.assertFalse(consulta.done())
            finally:
                terminar.set()
                await consulta

        with (
            patch.object(main, "gestionar_fallback", side_effect=llm_lento),
            patch.object(main, "registrar_intercambio"),
        ):
            asyncio.run(comprobar())


if __name__ == "__main__":
    unittest.main()
