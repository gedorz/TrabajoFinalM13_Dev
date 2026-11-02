"""Alias orales del SKU sin llamadas externas ni captura de audio."""

import json
from pathlib import Path
import re
import unittest
import zipfile

from docs.dialogflow.generar_agente import mejorar_agente
from docs.dialogflow.pistas_voz import PATRON_ALIAS_SKU
from negocio import (
    INTENCION_SI,
    INTENCION_SOLICITUD,
    buscar_producto,
    gestionar_negocio,
    normalizar_codigo_producto,
)

SKU = "ESP32-LX6D-WBT-4M"
PRODUCTOS = {
    SKU: {
        "titular": "ESP32 clásico", "marca": "Xtensa", "ubicacion": "Barcelona",
        "disponible": True, "costo": 25,
    }
}


class AliasSkuTests(unittest.TestCase):
    def test_alias_normalizados_y_sku_original(self):
        self.assertEqual(normalizar_codigo_producto("  PLACA   uno  "), SKU)
        self.assertEqual(normalizar_codigo_producto("placa 1"), SKU)
        self.assertEqual(normalizar_codigo_producto(SKU.lower()), SKU)
        self.assertIsNotNone(re.fullmatch(PATRON_ALIAS_SKU, "placa uno"))
        self.assertIsNotNone(re.fullmatch(PATRON_ALIAS_SKU, "placa 1"))

    def test_otro_numero_no_se_asigna_al_producto(self):
        _, producto, error = buscar_producto({"codigo_sku": "placa dos"}, PRODUCTOS)
        self.assertIsNone(producto)
        self.assertIn("formato válido", error)
        self.assertIsNone(re.fullmatch(PATRON_ALIAS_SKU, "placa 10"))

    def test_solicitud_por_alias_y_confirmacion_con_sku_canonico(self):
        body = {
            "session": "projects/prueba/agent/sessions/alias",
            "responseId": "peticion-alias",
            "queryResult": {
                "intent": {"displayName": INTENCION_SOLICITUD},
                "allRequiredParamsPresent": True,
                "parameters": {"codigo_sku": "placa uno", "ubicacion": "Barcelona"},
            },
        }
        pendiente = gestionar_negocio(body, PRODUCTOS)
        self.assertEqual(pendiente["outputContexts"][0]["parameters"]["codigo_sku"], SKU)
        body["queryResult"] = {
            "intent": {"displayName": INTENCION_SI},
            "parameters": {},
            "outputContexts": pendiente["outputContexts"],
        }
        confirmada = gestionar_negocio(body, PRODUCTOS)
        self.assertIn(SKU, confirmada["fulfillmentText"])
        self.assertIn("confirmada", confirmada["fulfillmentText"])
        self.assertEqual(confirmada["outputContexts"][0]["lifespanCount"], 0)

    def test_generador_mantiene_regex_y_agrega_alias(self):
        raiz = Path(__file__).resolve().parents[2]
        with zipfile.ZipFile(raiz / "docs" / "Kitia.zip") as archivo:
            archivos = {
                nombre: json.loads(archivo.read(nombre))
                for nombre in archivo.namelist() if nombre.endswith(".json")
            }
        mejorar_agente(archivos)
        self.assertTrue(archivos["entities/codigo_sku.json"]["isRegexp"])
        patrones = archivos["entities/codigo_sku_entries_es.json"]
        self.assertTrue(any(re.fullmatch(p["value"], SKU) for p in patrones))
        self.assertTrue(any(re.fullmatch(p["value"], "placa uno") for p in patrones))


if __name__ == "__main__":
    unittest.main()
