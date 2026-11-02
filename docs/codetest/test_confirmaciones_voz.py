"""Selección del reconocedor y recuperación de confirmaciones sin transcripción."""

import unittest
from unittest.mock import Mock, patch

from google.cloud import dialogflow as df

import cliente_voz as voz

SKU = "ESP32-LX6D-WBT-4M"
SESION = "projects/prueba/agent/sessions/confirmacion"
CONTEXTO = df.Context(
    name=f"{SESION}/contexts/solicitar_producto_amazon-followup",
    lifespan_count=3, parameters={"estado": "pendiente", "codigo_sku": SKU},
)


def respuesta(texto="", error=0):
    return df.DetectIntentResponse(
        query_result=df.QueryResult(
            query_text=texto,
            intent=df.Intent(display_name="solicitar_producto_amazon" if texto else ""),
            parameters={},
        ),
        webhook_status={"code": error},
    )


class ConfirmacionesVozTests(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()
        self.cliente.session_path.return_value = SESION
        for parche in (
            patch.object(voz, "clientes", self.cliente),
            patch.object(voz, "contextos_conversacion", []),
            patch.object(voz, "propuesta_sku", None),
            patch.object(voz, "contextos_propuesta", []),
            patch.object(voz, "MODELO_VOZ", "latest_long"),
            patch.object(voz, "MODELO_CONFIRMACION", "latest_short"),
            patch.object(voz, "resolver_codigo_de_voz", side_effect=lambda r, c: r),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def test_modelo_corto_para_confirmaciones_y_largo_para_sku(self):
        self.cliente.detect_intent.return_value = respuesta("sí")
        voz.hablar_con_el_agente(b"sku", esperando_sku=True)
        voz.propuesta_sku = SKU
        voz.hablar_con_el_agente(b"si codigo", esperando_sku=True)
        voz.propuesta_sku = None
        voz.contextos_conversacion = [CONTEXTO]
        voz.hablar_con_el_agente(b"si compra")
        modelos = [
            c.kwargs["request"]["query_input"].audio_config.model
            for c in self.cliente.detect_intent.call_args_list
        ]
        self.assertEqual(modelos, ["latest_long", "latest_short", "latest_short"])

    def test_si_vacio_reintenta_una_vez_con_mismo_audio_y_contexto(self):
        voz.propuesta_sku = SKU
        voz.contextos_conversacion = [CONTEXTO]
        self.cliente.detect_intent.side_effect = [respuesta(), respuesta("sí")]
        with patch("builtins.print"):
            resultado = voz.hablar_con_el_agente(b"pcm de la misma toma", esperando_sku=True)
        self.assertEqual(resultado.query_result.query_text, "sí")
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        primera, segunda = [c.kwargs["request"] for c in self.cliente.detect_intent.call_args_list]
        self.assertEqual(primera["input_audio"], segunda["input_audio"])
        self.assertEqual(primera["session"], segunda["session"])
        self.assertEqual(primera["query_input"].audio_config.model, "latest_short")
        self.assertEqual(segunda["query_input"].audio_config.model, "latest_long")
        self.assertEqual(segunda["query_params"].contexts[0].name, CONTEXTO.name)

    def test_no_inventa_confirmacion_si_ambos_modelos_fallan_ni_reintenta_timeout(self):
        voz.propuesta_sku = SKU
        voz.contextos_conversacion = [CONTEXTO]
        self.cliente.detect_intent.side_effect = [respuesta(), respuesta()]
        with patch("builtins.print"):
            resultado = voz.hablar_con_el_agente(b"pcm", esperando_sku=True)
        self.assertFalse(resultado.query_result.query_text)
        self.assertEqual(voz.propuesta_sku, SKU)
        self.assertEqual(voz.contextos_conversacion, [CONTEXTO])
        self.assertEqual(self.cliente.detect_intent.call_count, 2)
        self.cliente.detect_intent.reset_mock()
        self.cliente.detect_intent.side_effect = [respuesta(error=4)]
        voz.hablar_con_el_agente(b"pcm", esperando_sku=True)
        self.assertEqual(self.cliente.detect_intent.call_count, 1)
        self.assertEqual(voz.propuesta_sku, SKU)


if __name__ == "__main__":
    unittest.main()
