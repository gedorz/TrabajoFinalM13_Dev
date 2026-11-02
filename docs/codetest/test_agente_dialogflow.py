"""Cinco comprobaciones locales sin llamadas a Google ni ejecución de OCR."""

import asyncio
import importlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import zipfile

from fastapi import Request
from google.cloud import dialogflow
from google.protobuf.json_format import ParseDict

from negocio import CONTEXTO_SOLICITUD, INTENCION_NO, INTENCION_SI, INTENCION_SOLICITUD

RAIZ = Path(__file__).resolve().parents[2]
SESION = "projects/prueba/agent/sessions/conversacion-1"
SKU = "ESP32-LX6D-WBT-4M"
AGENTE = RAIZ / "docs" / "dialogflow" / "Kitia_mejorado.zip"


class AgenteDialogflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (
            patch.dict(os.environ, {"GOOGLE_API_KEY": "clave-de-prueba"}),
            patch("documentacion_ocr.cargar_documentos", return_value={}),
            patch("google.genai.Client"),
        ):
            cls.main = importlib.import_module("main")
        with zipfile.ZipFile(AGENTE) as archivo:
            cls.intenciones = {
                json.loads(archivo.read(nombre))["name"]: json.loads(archivo.read(nombre))
                for nombre in archivo.namelist()
                if nombre.startswith("intents/") and "_usersays_" not in nombre
            }

    def solicitar(self, intencion, parametros=None, contextos=None):
        # Reproduce el contexto recibido en el webhook de cierre: conserva
        # los parámetros aunque el lifespan llegue a cero y se omita en JSON.
        activos = {contexto["name"]: dict(contexto) for contexto in contextos or []}
        for salida in self.intenciones[intencion]["responses"][0]["affectedContexts"]:
            nombre = f"{SESION}/contexts/{salida['name']}"
            if salida["lifespan"] == 0:
                if nombre in activos:
                    activos[nombre].pop("lifespanCount", None)
            else:
                contexto = activos.setdefault(nombre, {"name": nombre, "parameters": {}})
                contexto["lifespanCount"] = salida["lifespan"]
        body = {
            "session": SESION,
            "responseId": "peticion-de-prueba",
            "queryResult": {
                "intent": {"displayName": intencion},
                "parameters": parametros or {},
                "allRequiredParamsPresent": True,
                "queryText": "¿Qué dice la documentación?",
                "outputContexts": list(activos.values()),
            },
        }

        async def recibir():
            return {
                "type": "http.request",
                "body": json.dumps(body).encode(),
                "more_body": False,
            }

        peticion = Request({"type": "http", "method": "POST", "path": "/webhook"}, recibir)
        resultado = asyncio.run(self.main.webhook(peticion))
        ParseDict(resultado, dialogflow.WebhookResponse.pb()())
        return resultado

    def pendiente(self):
        return self.solicitar(
            INTENCION_SOLICITUD, {"codigo_sku": SKU, "ubicacion": "Barcelona"}
        )

    def test_zip_coherente_con_el_webhook(self):
        with zipfile.ZipFile(AGENTE) as archivo:
            self.assertIsNone(archivo.testzip())
            archivos = {nombre: json.loads(archivo.read(nombre)) for nombre in archivo.namelist()}
        intenciones = [
            valor for nombre, valor in archivos.items()
            if nombre.startswith("intents/") and "_usersays_" not in nombre
        ]
        self.assertEqual(len(intenciones), 8)
        entidad = archivos["entities/codigo_sku.json"]
        self.assertTrue(entidad["isRegexp"])
        patron = archivos["entities/codigo_sku_entries_es.json"][0]["value"]
        self.assertTrue(all(re.fullmatch(patron, codigo) for codigo in self.main.PRODUCTOS))
        self.assertFalse(re.fullmatch(patron, "inventado"))
        for intencion in intenciones:
            nombre = intencion["name"]
            if nombre != "Default Welcome Intent":
                self.assertTrue(intencion["webhookUsed"])
            if nombre in (INTENCION_SI, INTENCION_NO):
                self.assertEqual(intencion["contexts"], [CONTEXTO_SOLICITUD])
                self.assertEqual(intencion["responses"][0]["affectedContexts"], [])
            else:
                self.assertEqual(intencion["contexts"], [])
            if nombre != "Default Fallback Intent":
                frases = archivos[f"intents/{nombre}_usersays_es.json"]
                parametros = {
                    p["name"] for p in intencion["responses"][0]["parameters"]
                }
                for frase in frases:
                    for parte in frase["data"]:
                        if "alias" in parte:
                            self.assertIn(parte["alias"], parametros)
        original = RAIZ / "docs" / "Kitia.zip"
        with zipfile.ZipFile(original) as archivo:
            self.assertFalse(json.loads(archivo.read("entities/codigo_sku.json"))["isRegexp"])

    def test_solicitud_y_confirmacion(self):
        pendiente = self.pendiente()
        self.assertIn("¿Confirmas?", pendiente["fulfillmentText"])
        contexto = pendiente["outputContexts"]
        self.assertEqual(contexto[0]["parameters"]["estado"], "pendiente")
        referencia = contexto[0]["parameters"]["referencia"]
        contexto[0].pop("lifespanCount")
        confirmada = self.solicitar(INTENCION_SI, contextos=contexto)
        self.assertIn(referencia, confirmada["fulfillmentText"])
        self.assertIn("simulación", confirmada["fulfillmentText"])
        self.assertEqual(confirmada["outputContexts"][0]["lifespanCount"], 0)

    def test_cancelacion_y_aislamiento_de_sesion(self):
        contexto = self.pendiente()["outputContexts"]
        contexto[0].pop("lifespanCount")
        cancelada = self.solicitar(INTENCION_NO, contextos=contexto)
        self.assertIn("cancelada", cancelada["fulfillmentText"])
        self.assertEqual(cancelada["outputContexts"][0]["lifespanCount"], 0)
        contexto[0]["name"] = contexto[0]["name"].replace("conversacion-1", "otra-sesion")
        aislada = self.solicitar(INTENCION_SI, contextos=contexto)
        self.assertIn("No hay una solicitud pendiente", aislada["fulfillmentText"])

    def test_rechazo_de_solicitudes_invalidas(self):
        invalida = self.solicitar(
            INTENCION_SOLICITUD, {"codigo_sku": "incorrecto", "ubicacion": "Barcelona"}
        )
        self.assertIn("formato válido", invalida["fulfillmentText"])
        self.assertEqual(invalida["outputContexts"][0]["lifespanCount"], 0)
        agotada = self.solicitar(
            INTENCION_SOLICITUD,
            {"codigo_sku": "ESP32-LX6D-WBT-16M", "ubicacion": "Barcelona"},
        )
        self.assertIn("no está disponible", agotada["fulfillmentText"])
        otra_ciudad = self.solicitar(
            INTENCION_SOLICITUD, {"codigo_sku": SKU, "ubicacion": "Madrid"}
        )
        self.assertIn("solo está disponible en Barcelona", otra_ciudad["fulfillmentText"])

    def test_consultas_dinamicas_y_documentales(self):
        catalogo = self.solicitar("Consultar_productos", {"marca": "Xtensa"})
        self.assertIn(SKU, catalogo["fulfillmentText"])
        stock = self.solicitar("consultar_disponibiliadad", {"codigo_sku": SKU})
        self.assertIn("25 euros", stock["fulfillmentText"])
        documental = self.solicitar("consulta_especificaciones_producto")
        self.assertIn("No tengo documentación", documental["fulfillmentText"])
        with patch.object(
            self.main,
            "gestionar_fallback",
            return_value={"fulfillmentText": "Dato del documento"},
        ) as consulta:
            respuesta = self.solicitar("consulta_especificaciones_producto")
            self.assertEqual(respuesta["fulfillmentText"], "Dato del documento")
            consulta.assert_called_once_with("¿Qué dice la documentación?")


if __name__ == "__main__":
    unittest.main()
