"""Registro de disponibilidad del LLM sin llamadas a servicios externos."""

import importlib
import os
import unittest
from unittest.mock import patch

from google.genai import errors


class ErroresLLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (
            patch.dict(os.environ, {"GOOGLE_API_KEY": "clave-de-prueba"}),
            patch("documentacion_ocr.cargar_documentos", return_value={}),
            patch("google.genai.Client"),
        ):
            cls.main = importlib.import_module("main")

    def consultar(self, error):
        with (
            patch.object(self.main, "seleccionar_documentos", return_value="Texto OCR"),
            patch.object(self.main, "preguntar_al_modelo", side_effect=error),
            self.assertLogs("uvicorn.error", level="ERROR") as registro,
        ):
            respuesta = self.main.gestionar_fallback("Especificaciones del producto")
        self.assertIn("Ahora mismo no puedo responder", respuesta["fulfillmentText"])
        return "\n".join(registro.output)

    def test_disponibilidad_503(self):
        error = errors.ServerError(
            503, {"error": {"status": "UNAVAILABLE", "message": "High demand"}}
        )
        registro = self.consultar(error)
        self.assertIn("LLM NO DISPONIBLE", registro)
        self.assertIn("HTTP 503 UNAVAILABLE", registro)
        self.assertIn(f"modelo={self.main.MODELO_GEMINI}", registro)
        self.assertIn("más tarde", registro)

    def test_otro_error_no_se_confunde_con_indisponibilidad(self):
        error = errors.ClientError(
            429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota"}}
        )
        registro = self.consultar(error)
        self.assertIn("ERROR LLM", registro)
        self.assertIn("429", registro)
        self.assertNotIn("LLM NO DISPONIBLE", registro)

    def test_respuesta_correcta_no_registra_error(self):
        with (
            patch.object(self.main, "seleccionar_documentos", return_value="Texto OCR"),
            patch.object(self.main, "preguntar_al_modelo", return_value="Datos del documento"),
            self.assertNoLogs("uvicorn.error", level="ERROR"),
        ):
            respuesta = self.main.gestionar_fallback("Especificaciones del producto")
        self.assertEqual(respuesta["fulfillmentText"], "Datos del documento")


if __name__ == "__main__":
    unittest.main()
