"""Conservar dictados ante timeouts sin volver a capturar ni aceptar una compra."""

import argparse
import unittest
from unittest.mock import Mock, patch

from google.cloud import dialogflow as df

import cliente_voz as voz

SKU = "ESP32-LX6D-WBT-4M"
CONTEXTO = df.Context(
    name="projects/prueba/agent/sessions/voz/contexts/solicitud",
    lifespan_count=2, parameters={"codigo_sku": "", "ubicacion": ""},
)


def respuesta(texto, error=0, ayuda=False, codigo=""):
    return df.DetectIntentResponse(
        query_result=df.QueryResult(
            query_text=texto, speech_recognition_confidence=0.38,
            intent=df.Intent(display_name="solicitar_producto_amazon"),
            parameters={"codigo_sku": codigo, "ubicacion": ""},
            output_contexts=[CONTEXTO],
            webhook_payload={"ayuda_sku": {"tipo": "confirmar"}} if ayuda else {},
        ),
        webhook_status={"code": error},
    )


class ReenvioCodigoTests(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()
        self.cliente.session_path.return_value = "projects/prueba/agent/sessions/voz"
        for parche in (
            patch.object(voz, "clientes", self.cliente),
            patch.object(voz, "codigo_pendiente", None),
            patch.object(voz, "propuesta_sku", None),
            patch.object(voz, "contextos_propuesta", []),
            patch.object(voz, "contextos_conversacion", [CONTEXTO]),
            patch("builtins.print"),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def test_recupera_propuesta_sin_otro_audio_ni_aceptar_sku(self):
        self.cliente.detect_intent.side_effect = [
            respuesta("asistencia", error=4), respuesta("asistencia", ayuda=True),
        ]
        original = respuesta("esp32 L x 6 de W t4m")
        voz.procesar_codigo_de_voz(original, [CONTEXTO])
        self.assertIsNotNone(voz.codigo_pendiente)
        self.assertIsNone(voz.propuesta_sku)
        recuperada = voz.reintentar_codigo_pendiente()
        self.assertIsNone(voz.codigo_pendiente)
        self.assertEqual(voz.propuesta_sku, SKU)
        self.assertEqual(recuperada.query_result.diagnostic_info["transcripcion_original"], original.query_result.query_text)
        self.assertFalse(recuperada.query_result.parameters["codigo_sku"])
        for llamada in self.cliente.detect_intent.call_args_list:
            peticion = llamada.kwargs["request"]
            self.assertNotIn("input_audio", peticion)
            self.assertEqual(peticion["query_params"].contexts[0], CONTEXTO)

    def test_confirmacion_codigo_se_conserva_hasta_aceptar_y_pide_ciudad(self):
        voz.propuesta_sku = SKU
        voz.contextos_propuesta = [CONTEXTO]
        self.cliente.detect_intent.side_effect = [
            respuesta(SKU, error=4), respuesta(SKU, codigo=SKU),
        ]
        voz.procesar_codigo_de_voz(respuesta("sí es correcto"), [CONTEXTO])
        self.assertEqual(voz.propuesta_sku, SKU)
        recuperada = voz.reintentar_codigo_pendiente()
        self.assertIsNone(voz.propuesta_sku)
        self.assertIsNone(voz.codigo_pendiente)
        self.assertEqual(recuperada.query_result.parameters["codigo_sku"], SKU)
        self.assertEqual(self.cliente.detect_intent.call_args.kwargs["request"]["query_input"].text.text, SKU)

    def test_otro_timeout_conserva_original_sin_reintentos_automaticos(self):
        self.cliente.detect_intent.return_value = respuesta("asistencia", error=4)
        original = respuesta("esp32 L x 6 de W t4m")
        voz.procesar_codigo_de_voz(original, [CONTEXTO])
        voz.reintentar_codigo_pendiente()
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        self.assertEqual(voz.codigo_pendiente[0].query_result.query_text, original.query_result.query_text)
        self.assertEqual(voz.contextos_conversacion, [CONTEXTO])

    def test_enter_reenvia_y_r_permite_nueva_grabacion(self):
        opciones = argparse.Namespace(
            listar_microfonos=False, probar_microfono=False, probar_reconocimiento=False,
            segundos=8, segundos_sku=12, microfono=None, sin_recorte_silencio=False,
        )
        self.cliente.detect_intent.return_value = respuesta("asistencia", error=4)
        voz.procesar_codigo_de_voz(respuesta("esp32 L x 6 de W t4m"), [CONTEXTO])
        with (
            patch.object(voz, "leer_opciones", return_value=opciones),
            patch("builtins.input", side_effect=["", "r", "q"]),
            patch.object(voz, "escuchar", return_value=b"") as escuchar,
        ):
            voz.main()
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        escuchar.assert_called_once()
        self.assertIsNone(voz.codigo_pendiente)


if __name__ == "__main__":
    unittest.main()
