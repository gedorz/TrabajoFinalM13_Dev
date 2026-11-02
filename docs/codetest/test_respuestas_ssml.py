"""SSML de Dialogflow ES sin llamadas a Google ni reproducción de audio. por fin funciona correctamente."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from fastapi import Request
from google.cloud import dialogflow
from google.protobuf.json_format import ParseDict

from docs.dialogflow.respuestas_voz import agregar_ssml, crear_ssml

SKU = "ESP32-LX6D-WBT-4M"
SESION = "projects/prueba/agent/sessions/ssml"


class RespuestasSSMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raiz = Path(__file__).resolve().parents[2]
        especificacion = importlib.util.spec_from_file_location("servidor_prueba_ssml", raiz / "main.py")
        cls.servidor = importlib.util.module_from_spec(especificacion)
        with (
            patch.dict(os.environ, {"GOOGLE_API_KEY": "clave-de-prueba"}),
            patch("google.genai.Client"),
        ):
            especificacion.loader.exec_module(cls.servidor)

    def enviar(self, intencion, parametros=None, contextos=None, ayuda=None, completo=True):
        body = {
            "session": SESION,
            "queryResult": {
                "queryText": "Texto de prueba", "intent": {"displayName": intencion},
                "parameters": parametros or {}, "outputContexts": contextos or [],
                "allRequiredParamsPresent": completo,
            },
            "originalDetectIntentRequest": {"payload": {"ayuda_sku": ayuda} if ayuda else {}},
        }

        async def recibir():
            return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}

        with patch.object(self.servidor, "registrar_intercambio"):
            respuesta = asyncio.run(self.servidor.webhook(Request(
                {"type": "http", "method": "POST", "path": "/webhook"}, recibir
            )))
        ParseDict(respuesta, dialogflow.WebhookResponse.pb()())
        if respuesta.get("fulfillmentText"):
            arbol = ElementTree.fromstring(respuesta["fulfillmentMessages"][0]["text"]["text"][0])
            self.assertEqual(arbol.tag, "speak")
            self.assertEqual("".join(arbol.itertext()), respuesta["fulfillmentText"])
        return respuesta

    def test_escapa_texto_dinamico_y_deletrea_sku_sin_inyectar_etiquetas(self):
        texto = f'Kit <audio src="externo"/> & placa {SKU}. ¿Confirmas?'
        arbol = ElementTree.fromstring(crear_ssml(texto))
        self.assertEqual("".join(arbol.itertext()), texto)
        self.assertIsNone(arbol.find("audio"))
        self.assertEqual(arbol.find("say-as").attrib, {"interpret-as": "characters"})
        self.assertEqual(arbol.find("say-as").text, SKU)
        self.assertEqual(arbol.find("break").attrib, {"time": "180ms"})

    def test_respuestas_vacias_y_payload_no_generan_locucion(self):
        self.assertEqual(agregar_ssml({}), {})
        recogida = self.enviar("solicitar_producto_amazon", completo=False)
        self.assertEqual(recogida, {})
        escucha = self.enviar("Default Fallback Intent", ayuda={"tipo": "escuchar_confirmacion"})
        self.assertEqual(escucha["fulfillmentText"], "")
        self.assertNotIn("fulfillmentMessages", escucha)
        self.assertEqual(escucha["payload"]["ayuda_sku"]["tipo"], "escuchar_confirmacion")

    def test_preparar_confirmar_y_cancelar_conservan_contextos_y_simulacion(self):
        preparada = self.enviar("solicitar_producto_amazon", {"codigo_sku": SKU, "ubicacion": "Barcelona"})
        contexto = preparada["outputContexts"]
        self.assertEqual(contexto[0]["parameters"]["estado"], "pendiente")
        for intencion, esperado in (
            ("solicitar_producto_amazon - yes", "Es una simulación"),
            ("solicitar_producto_amazon - no", "Solicitud cancelada"),
        ):
            cerrada = self.enviar(intencion, contextos=contexto)
            self.assertIn(esperado, cerrada["fulfillmentText"])
            self.assertEqual(cerrada["outputContexts"][0]["lifespanCount"], 0)

    def test_ayuda_sku_y_documental_tienen_ssml_sin_alterar_payload(self):
        ayuda = self.enviar("Default Fallback Intent", ayuda={"tipo": "confirmar", "codigo": SKU})
        self.assertEqual(ayuda["payload"]["ayuda_sku"]["codigo"], SKU)
        self.assertIn("¿Te refieres", ayuda["fulfillmentText"])
        with patch.object(self.servidor, "gestionar_fallback", return_value={"fulfillmentText": "Dato documental & prueba"}):
            documental = self.enviar("consulta_especificaciones_producto")
        self.assertEqual(documental["fulfillmentText"], "Dato documental & prueba")

    def test_catalogo_y_errores_tienen_ssml_y_texto_legible(self):
        catalogo = self.enviar("Consultar_productos")
        self.assertIn(SKU, catalogo["fulfillmentText"])
        self.assertNotIn("<speak>", catalogo["fulfillmentText"])
        invalida = self.enviar("solicitar_producto_amazon", {"codigo_sku": "invalido", "ubicacion": "Barcelona"})
        self.assertIn("formato válido", invalida["fulfillmentText"])
        desconocida = self.enviar("intencion_desconocida")
        self.assertIn("Todavía no sé", desconocida["fulfillmentText"])


if __name__ == "__main__":
    unittest.main()
# por fin funciona correctamente