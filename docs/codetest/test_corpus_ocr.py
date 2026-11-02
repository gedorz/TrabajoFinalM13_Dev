"""Persistencia OCR, extracción completa y uso documental sin repetir Tesseract."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from documentacion_ocr import RUTA_CORPUS, cargar_documentos
import ocr

RAIZ = Path(__file__).resolve().parents[2]


class CorpusOCRTests(unittest.TestCase):
    def test_regex_extrae_codigos_completos_y_no_fragmentos(self):
        texto = "ESP32-LX6D-WBT-4M y ESP32-S3D-WBLE-16M8R, 25 euros, 02/11/2026"
        datos = ocr.extraer_datos(texto)
        self.assertEqual(datos["SKU"], ["ESP32-LX6D-WBT-4M", "ESP32-S3D-WBLE-16M8R"])
        self.assertEqual(datos["importe"], ["25 euros"])
        self.assertEqual(datos["fecha"], ["02/11/2026"])
        self.assertEqual(ocr.extraer_datos("ESP32-LX6D-WBT-4M-EXTRA-MAS")["SKU"], [])

    def test_corpus_ausente_o_corrupto_no_dispara_ocr_automatico(self):
        with tempfile.TemporaryDirectory() as temporal, patch.object(ocr, "leer_documento") as leer:
            ruta = Path(temporal) / "texto_ocr.json"
            with self.assertRaisesRegex(ValueError, "python ocr.py"):
                cargar_documentos(ruta)
            ruta.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No se puede leer"):
                cargar_documentos(ruta)
            ruta.write_text(json.dumps({"version": 1, "documentos": {
                "a.png": {"texto": "", "datos_extraidos": {}},
            }}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Falta texto"):
                cargar_documentos(ruta)
            leer.assert_not_called()

    def test_generacion_incompleta_no_sobrescribe_corpus_previo(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            (carpeta / "a.png").write_bytes(b"imagen de prueba")
            (carpeta / "b.png").write_bytes(b"imagen de prueba")
            evidencia = carpeta / "evidencias"
            evidencia.mkdir()
            (evidencia / "captura.png").write_bytes(b"no pertenece al corpus")
            destino = carpeta / "texto_ocr.json"
            with patch.object(ocr, "leer_documento", return_value="SKU: ESP32-LX6D-WBT-4M") as leer:
                ocr.generar_corpus(carpeta, destino)
                self.assertEqual(leer.call_count, 2)
            anterior = destino.read_bytes()
            self.assertEqual(len(cargar_documentos(destino)), 2)
            with patch.object(ocr, "leer_documento", side_effect=["Texto válido", ""]):
                with self.assertRaisesRegex(ValueError, "corpus incompleto"):
                    ocr.generar_corpus(carpeta, destino)
            self.assertEqual(destino.read_bytes(), anterior)

    def test_servidor_usa_cuatro_documentos_reales_y_envia_contexto_persistido(self):
        corpus = json.loads(RUTA_CORPUS.read_text(encoding="utf-8"))
        self.assertEqual(len(corpus["documentos"]), 4)
        codigos = []
        importes = []
        for nombre, documento in corpus["documentos"].items():
            self.assertEqual(
                documento["sha256_imagen"],
                hashlib.sha256((RAIZ / "documentos" / nombre).read_bytes()).hexdigest(),
            )
            self.assertEqual(documento["datos_extraidos"], ocr.extraer_datos(documento["texto"]))
            codigos.extend(documento["datos_extraidos"]["SKU"])
            importes.extend(documento["datos_extraidos"]["importe"])
            self.assertEqual(documento["datos_extraidos"]["fecha"], ["02/11/2026"])
        self.assertEqual(len(set(codigos)), 11)
        self.assertEqual(len(importes), 11)
        especificacion = importlib.util.spec_from_file_location("servidor_prueba_ocr", RAIZ / "main.py")
        servidor = importlib.util.module_from_spec(especificacion)
        with (
            patch.dict(os.environ, {"GOOGLE_API_KEY": "clave-de-prueba"}),
            patch("google.genai.Client"),
            patch.object(ocr, "leer_documento", side_effect=AssertionError("OCR durante el arranque")) as leer,
        ):
            especificacion.loader.exec_module(servidor)
            self.assertEqual(servidor.raiz()["documentos_cargados"], 4)
            with patch.object(servidor, "preguntar_al_modelo", return_value="Respuesta simulada") as modelo:
                servidor.gestionar_fallback("¿Qué memoria tiene ESP32-S3D-WBLE-8M8R?")
                prompt = modelo.call_args.args[0]
                self.assertIn(corpus["documentos"]["02_catalogo_esp32_s3.png"]["texto"], prompt)
                self.assertIn("8MB Flash + 8MB PSRAM", prompt)
                self.assertIn("No completes con conocimiento propio", prompt)
                modelo.reset_mock()
                negativa = servidor.gestionar_fallback("¿Qué órbita tiene Neptuno?")
                self.assertIn("No tengo documentación", negativa["fulfillmentText"])
                modelo.assert_not_called()
            leer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
# por fin funciona correctamente