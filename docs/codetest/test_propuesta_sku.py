"""Recuperación de dictados incompletos con confirmación explícita del código."""

import unittest
from unittest.mock import Mock, patch

from google.cloud import dialogflow as df

import cliente_voz as voz
from docs.dialogflow.ayuda_voz import responder_ayuda_sku
from docs.dialogflow.normalizar_voz import codigo_dictado, confirmacion_dictada, sugerir_codigo

SKU = "ESP32-LX6D-WBT-4M"
SESION = "projects/prueba/agent/sessions/codigo"
CONTEXTO = df.Context(
    name=f"{SESION}/contexts/solicitar_producto_amazon_dialog_context",
    lifespan_count=2, parameters={"codigo_sku": "", "ubicacion": ""},
)


def respuesta(texto, intencion="solicitar_producto_amazon", codigo="", mensaje="", ayuda=None):
    return df.DetectIntentResponse(
        query_result=df.QueryResult(
            query_text=texto, intent=df.Intent(display_name=intencion),
            parameters={"codigo_sku": codigo}, output_contexts=[CONTEXTO],
            fulfillment_text=mensaje,
            webhook_payload={"ayuda_sku": {"tipo": ayuda}} if ayuda else {},
        ),
        output_audio=b"voz de prueba",
    )


class PropuestaSkuTests(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()
        self.cliente.session_path.return_value = SESION
        self.parches = [
            patch.object(voz, "clientes", self.cliente),
            patch.object(voz, "contextos_conversacion", [CONTEXTO]),
            patch.object(voz, "propuesta_sku", None),
            patch.object(voz, "contextos_propuesta", []),
        ]
        for parche in self.parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_equivalencia_fonetica_completa_sin_aproximar(self):
        self.assertEqual(codigo_dictado("el esp32 lx6 de WBT 4m"), SKU)
        self.assertIsNone(codigo_dictado("el esp32 lx6 de W t4m"))

    def test_variantes_del_usuario_solo_generan_propuesta(self):
        for texto in (
            "el esp32 lx6 de W t4m", "esp32 lx6 DWV 4m", "esp32 GX 6D W t4m"
        ):
            self.assertIsNone(codigo_dictado(texto))
            self.assertEqual(sugerir_codigo(texto), SKU)
        for texto in ("4m", "EMI", "x6b", "ESP32 4m", "esp32 lx6d wbt 5m", "no quiero " + SKU):
            self.assertIsNone(sugerir_codigo(texto))

    def test_propuesta_no_rellena_sku_hasta_recibir_si(self):
        self.cliente.detect_intent.side_effect = [
            respuesta("esp32 lx6 DWV 4m", "consultar_disponibiliadad"),
            respuesta("ayuda", mensaje="¿Es este código?", ayuda="confirmar"),
            respuesta("es correcto sí"),
            respuesta(SKU, codigo=SKU, mensaje="¿En qué ciudad?"),
        ]
        propuesta = voz.hablar_con_el_agente(b"grabacion1", esperando_sku=True)
        self.assertEqual(voz.propuesta_sku, SKU)
        self.assertFalse(propuesta.query_result.parameters["codigo_sku"])
        peticion_ayuda = self.cliente.detect_intent.call_args_list[1].kwargs["request"]
        self.assertNotEqual(peticion_ayuda["query_input"].text.text, SKU)
        self.assertEqual(peticion_ayuda["query_params"].payload["ayuda_sku"]["tipo"], "confirmar")
        confirmada = voz.hablar_con_el_agente(b"grabacion2", esperando_sku=True)
        self.assertEqual(confirmada.query_result.parameters["codigo_sku"], SKU)
        self.assertIsNone(voz.propuesta_sku)
        correccion = self.cliente.detect_intent.call_args_list[3].kwargs["request"]
        self.assertEqual(correccion["query_input"].text.text, SKU)
        self.assertEqual(correccion["query_params"].contexts[0].name, CONTEXTO.name)

    def test_no_rechaza_la_propuesta_y_pide_otro_codigo(self):
        voz.propuesta_sku = SKU
        voz.contextos_propuesta = [CONTEXTO]
        self.cliente.detect_intent.side_effect = [respuesta("no"), respuesta("ayuda")]
        resultado = voz.hablar_con_el_agente(b"no", esperando_sku=True)
        self.assertIsNone(voz.propuesta_sku)
        self.assertFalse(resultado.query_result.parameters["codigo_sku"])
        peticion = self.cliente.detect_intent.call_args.kwargs["request"]
        self.assertEqual(peticion["query_params"].payload["ayuda_sku"]["tipo"], "repetir")

    def test_afirmaciones_combinadas(self):
        for texto in ("es correcto sí", "sí, es correcto", "correcto sí", "sí sí", "estoy de acuerdo, sí"):
            self.assertIs(confirmacion_dictada(texto), True)

    def test_negaciones_y_respuestas_contradictorias(self):
        for texto in ("no", "no es correcto", "no no es correcto", "no confirmo"):
            self.assertIs(confirmacion_dictada(texto), False)
        for texto in ("sí pero no", "es correcto no", "no es correcto sí", "tal vez"):
            self.assertIsNone(confirmacion_dictada(texto))

    def test_confirmacion_compuesta_con_timeout_conserva_propuesta(self):
        voz.propuesta_sku = SKU
        voz.contextos_propuesta = [CONTEXTO]
        fallo = respuesta(SKU, codigo=SKU)
        fallo.webhook_status = {"code": 4, "message": "TIMEOUT_WEB"}
        self.cliente.detect_intent.side_effect = [respuesta("es correcto sí"), fallo]
        resultado = voz.hablar_con_el_agente(b"afirmacion", esperando_sku=True)
        self.assertEqual(resultado.webhook_status.code, 4)
        self.assertEqual(voz.propuesta_sku, SKU)
        self.assertEqual(voz.contextos_propuesta, [CONTEXTO])
        self.assertEqual(voz.contextos_conversacion, [CONTEXTO])
        peticion = self.cliente.detect_intent.call_args.kwargs["request"]
        self.assertEqual(peticion["query_input"].text.text, SKU)

    def test_fragmento_inutil_restaura_solicitud_y_webhook_solo_pregunta(self):
        self.cliente.detect_intent.side_effect = [
            respuesta("EMI", "consultar_disponibiliadad"), respuesta("ayuda")
        ]
        resultado = voz.hablar_con_el_agente(b"fragmento", esperando_sku=True)
        self.assertTrue(resultado.query_result.diagnostic_info["esperando_sku"])
        peticion = self.cliente.detect_intent.call_args.kwargs["request"]
        self.assertTrue(peticion["query_params"].reset_contexts)
        self.assertEqual(peticion["query_params"].contexts[0].name, CONTEXTO.name)
        body = {"originalDetectIntentRequest": {"payload": {
            "ayuda_sku": {"tipo": "confirmar", "codigo": SKU}
        }}}
        ayuda = responder_ayuda_sku(body, {SKU: {"titular": "ESP32 clásico"}})
        self.assertIn("sí o no", ayuda["fulfillmentText"])
        self.assertNotIn("outputContexts", ayuda)

    def test_timeout_conserva_contexto_para_repetir_cancelacion(self):
        pendiente = df.Context(
            name=f"{SESION}/contexts/solicitar_producto_amazon-followup",
            lifespan_count=3, parameters={"codigo_sku": SKU, "estado": "pendiente"},
        )
        voz.contextos_conversacion = [pendiente]
        fallo = respuesta("no", "solicitar_producto_amazon - no")
        fallo.webhook_status = {"code": 4, "message": "TIMEOUT_WEB"}
        cancelada = respuesta("no", "solicitar_producto_amazon - no", mensaje="Solicitud cancelada")
        cancelada.query_result.output_contexts = []
        self.cliente.detect_intent.side_effect = [fallo, cancelada]
        voz.hablar_con_el_agente(b"no")
        self.assertEqual(voz.contextos_conversacion, [pendiente])
        voz.hablar_con_el_agente(b"no repetido")
        for llamada in self.cliente.detect_intent.call_args_list:
            parametros = llamada.kwargs["request"]["query_params"]
            self.assertTrue(parametros.reset_contexts)
            self.assertEqual(parametros.contexts[0].name, pendiente.name)
        self.assertEqual(voz.contextos_conversacion, [])


if __name__ == "__main__":
    unittest.main()
