"""Normalización del dictado y conservación de los contextos de conversación."""

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from google.cloud import dialogflow

from archivos_audio import cargar_audio
import cliente_voz as voz
from docs.dialogflow.normalizar_voz import ciudad_dictada, codigo_dictado

SKU = "ESP32-LX6D-WBT-4M"


class NormalizarVozTests(unittest.TestCase):
    def test_codigo_completo_dictado_con_espacios(self):
        self.assertEqual(codigo_dictado("el producto esp32 L x 6 d WBT 4m"), SKU)
        self.assertEqual(codigo_dictado("Código SKU: ESP32 LX6D WBT 4M"), SKU)
        self.assertEqual(codigo_dictado("placa uno"), SKU)

    def test_no_completa_fragmentos_ni_ignora_negaciones(self):
        for fragmento in ("x6b", "4m", "cuatro", "EMI", "no quiero ESP32-LX6D-WBT-4M"):
            self.assertIsNone(codigo_dictado(fragmento))

    def test_ciudad_expresa_sin_inventar_ubicacion(self):
        self.assertEqual(ciudad_dictada("para la ciudad de Barcelona"), "Barcelona")
        self.assertEqual(ciudad_dictada("en la ciudad de Madrid"), "Madrid")
        self.assertIsNone(ciudad_dictada("no"))
        self.assertIsNone(ciudad_dictada("quiero cancelar"))

    def test_correccion_restaura_contexto_y_conserva_transcripcion_original(self):
        sesion = "projects/prueba/agent/sessions/voz"
        contexto = dialogflow.Context(
            name=f"{sesion}/contexts/solicitar_producto_amazon_dialog_context",
            lifespan_count=2, parameters={"codigo_sku": "", "ubicacion": ""},
        )
        original = "el producto esp32 L x 6 d WBT 4m"
        audio = dialogflow.DetectIntentResponse(query_result=dialogflow.QueryResult(
            query_text=original, speech_recognition_confidence=0.47,
            intent=dialogflow.Intent(display_name="consultar_disponibiliadad"),
            parameters={"codigo_sku": ""},
        ))
        corregida = dialogflow.DetectIntentResponse(query_result=dialogflow.QueryResult(
            query_text=SKU, intent=dialogflow.Intent(display_name="solicitar_producto_amazon"),
            parameters={"codigo_sku": SKU, "ubicacion": ""},
            output_contexts=[contexto], fulfillment_text="¿En qué ciudad?",
        ))
        cliente = Mock()
        cliente.session_path.return_value = sesion
        cliente.detect_intent.side_effect = [audio, corregida]
        with (
            patch.object(voz, "clientes", cliente),
            patch.object(voz, "contextos_conversacion", [contexto]),
        ):
            respuesta = voz.hablar_con_el_agente(b"pcm", esperando_sku=True)
        self.assertEqual(cliente.detect_intent.call_count, 2)
        primera = cliente.detect_intent.call_args_list[0].kwargs["request"]
        segunda = cliente.detect_intent.call_args_list[1].kwargs["request"]
        self.assertEqual(primera["session"], segunda["session"])
        self.assertEqual(segunda["query_input"].text.text, SKU)
        self.assertTrue(segunda["query_params"].reset_contexts)
        self.assertEqual(segunda["query_params"].contexts[0].name, contexto.name)
        self.assertEqual(respuesta.query_result.diagnostic_info["transcripcion_original"], original)
        self.assertEqual(respuesta.query_result.parameters["codigo_sku"], SKU)

    def test_sin_transcripcion_no_pierde_contexto_para_reintentar(self):
        contexto = dialogflow.Context(name="projects/p/agent/sessions/s/contexts/pendiente")
        cliente = Mock()
        cliente.detect_intent.return_value = dialogflow.DetectIntentResponse(
            query_result=dialogflow.QueryResult()
        )
        with (
            patch.object(voz, "clientes", cliente),
            patch.object(voz, "contextos_conversacion", [contexto]),
        ):
            voz.hablar_con_el_agente(b"pcm", esperando_sku=True)
            self.assertEqual(voz.contextos_conversacion, [contexto])
        self.assertEqual(cliente.detect_intent.call_count, 1)

    def test_decodifica_las_cinco_grabaciones_originales(self):
        raiz = Path(__file__).resolve().parents[2]
        archivos = sorted((raiz / "AudioEntrenamiento").glob("*.m4a"))
        self.assertGreaterEqual(len(archivos), 5)
        for archivo in archivos:
            audio = cargar_audio(archivo)
            self.assertGreater(len(audio), 16000)
            self.assertEqual(len(audio) % 2, 0)


if __name__ == "__main__":
    unittest.main()
