"""Comprobaciones de captura con audio simulado, sin activar el micrófono."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

import cliente_voz
from docs.codetest.audio_simulado import FlujoAudioSimulado


class ClienteVozTests(unittest.TestCase):
    def test_aviso_de_hablar_despues_de_iniciar_grabacion(self):
        orden = []

        def mostrar(*args, **kwargs):
            if args and str(args[0]).startswith("\nHabla"):
                orden.append("aviso de hablar")
                self.assertTrue(kwargs.get("flush"))

        with (
            patch.object(cliente_voz.sd, "query_devices", return_value={"name": "Prueba", "index": 2}),
            patch.object(cliente_voz.sd, "check_input_settings"),
            patch.object(cliente_voz.sd, "InputStream", return_value=FlujoAudioSimulado(
                np.full((16000, 1), 1000, dtype=np.int16), orden
            )),
            patch("builtins.print", side_effect=mostrar),
        ):
            cliente_voz.escuchar(segundos=1)
        self.assertEqual(orden, ["captura iniciada", "aviso de hablar", "fin captura"])

    def test_pistas_sku_solo_al_recoger_codigo(self):
        cliente = Mock()
        cliente.detect_intent.return_value = cliente_voz.dialogflow.DetectIntentResponse(
            query_result=cliente_voz.dialogflow.QueryResult(query_text="")
        )
        cliente.session_path.return_value = "projects/prueba/agent/sessions/voz"
        with patch.object(cliente_voz, "clientes", cliente):
            cliente_voz.hablar_con_el_agente(b"audio", esperando_sku=True)
            cliente_voz.hablar_con_el_agente(b"audio", esperando_sku=False)
        peticion_sku = cliente.detect_intent.call_args_list[0].kwargs["request"]
        configuracion = peticion_sku["query_input"].audio_config
        self.assertIn("ESP32-LX6D-WBT-4M", configuracion.speech_contexts[0].phrases)
        self.assertIn("placa uno", configuracion.speech_contexts[0].phrases)
        self.assertIn("placa 1", configuracion.speech_contexts[0].phrases)
        self.assertEqual(configuracion.speech_contexts[0].boost, 10)
        peticion_normal = cliente.detect_intent.call_args_list[1].kwargs["request"]
        self.assertEqual(len(peticion_normal["query_input"].audio_config.speech_contexts), 0)
        self.assertEqual(peticion_sku["session"], peticion_normal["session"])

    def grabar(self, muestras, microfono=2):
        with (
            patch.object(
                cliente_voz.sd, "query_devices",
                return_value={"name": "Prueba", "index": 2},
            ) as consulta,
            patch.object(cliente_voz.sd, "check_input_settings") as configuracion,
            patch.object(cliente_voz.sd, "InputStream", return_value=FlujoAudioSimulado(muestras)) as grabacion,
            patch("builtins.print") as salida,
        ):
            audio = cliente_voz.escuchar(segundos=1, microfono=microfono)
        consulta.assert_called_once_with(microfono, "input")
        self.assertEqual(configuracion.call_args.kwargs["device"], 2)
        return audio, grabacion, salida

    def test_silencio_no_se_envia(self):
        audio, _, salida = self.grabar(np.zeros((16000, 1), dtype=np.int16))
        self.assertEqual(audio, b"")
        self.assertTrue(any("contiene silencio" in str(llamada) for llamada in salida.call_args_list))

    def test_audio_se_conserva_y_se_elige_microfono(self):
        muestras = np.full((16000, 1), -32768, dtype=np.int16)
        audio, grabacion, salida = self.grabar(muestras, microfono=None)
        self.assertEqual(audio, muestras.tobytes())
        self.assertEqual(grabacion.call_args.kwargs["device"], 2)
        self.assertEqual(grabacion.call_args.kwargs["samplerate"], 16000)
        self.assertEqual(grabacion.call_args.kwargs["dtype"], "int16")
        self.assertTrue(any("predeterminado del sistema" in str(llamada) for llamada in salida.call_args_list))

    def test_listado_solo_muestra_entradas(self):
        dispositivos = [
            {"name": "Micrófono", "max_input_channels": 1, "hostapi": 0},
            {"name": "Altavoces", "max_input_channels": 0, "hostapi": 0},
        ]
        with (
            patch.object(cliente_voz.sd, "query_devices", return_value=dispositivos),
            patch.object(cliente_voz.sd, "query_hostapis", return_value={"name": "MME"}),
            patch("builtins.print") as salida,
        ):
            cliente_voz.listar_microfonos()
        salida.assert_called_once()
        self.assertIn("0: Micrófono", salida.call_args.args[0])

    def test_transcripcion_vacia_muestra_aviso(self):
        respuesta = SimpleNamespace(query_result=SimpleNamespace(
            query_text="", intent=SimpleNamespace(display_name="")
        ))
        with (
            patch.object(cliente_voz, "leer_opciones", return_value=SimpleNamespace(
                listar_microfonos=False, probar_microfono=False,
                probar_reconocimiento=False, sin_recorte_silencio=False,
                segundos=5, microfono=2
            )),
            patch("builtins.input", side_effect=["", "q"]),
            patch("builtins.print") as salida,
            patch.object(cliente_voz, "escuchar", return_value=b"audio"),
            patch.object(cliente_voz, "hablar_con_el_agente", return_value=respuesta),
            patch.object(cliente_voz, "reproducir") as reproducir,
        ):
            cliente_voz.main()
        self.assertTrue(any("no ha reconocido palabras" in str(llamada) for llamada in salida.call_args_list))
        reproducir.assert_not_called()

    def test_prueba_local_reproduce_audio_sin_llamar_a_dialogflow(self):
        muestras = np.array([100, -200, 300], dtype=np.int16)
        with (
            patch.object(cliente_voz, "leer_opciones", return_value=SimpleNamespace(
                listar_microfonos=False, probar_microfono=True,
                probar_reconocimiento=False, sin_recorte_silencio=False,
                segundos=8, microfono=None
            )),
            patch("builtins.input", return_value=""),
            patch("builtins.print"),
            patch.object(cliente_voz, "escuchar", return_value=muestras.tobytes()) as escuchar,
            patch.object(cliente_voz.sd, "play") as reproducir,
            patch.object(cliente_voz.sd, "wait"),
            patch.object(cliente_voz, "hablar_con_el_agente") as dialogflow,
        ):
            cliente_voz.main()
        escuchar.assert_called_once_with(8, None, recortar=True)
        np.testing.assert_array_equal(reproducir.call_args.args[0], muestras)
        self.assertEqual(reproducir.call_args.args[1], 16000)
        dialogflow.assert_not_called()

    def test_prueba_local_silenciosa_no_reproduce(self):
        with (
            patch("builtins.input", return_value=""),
            patch("builtins.print"),
            patch.object(cliente_voz, "escuchar", return_value=b""),
            patch.object(cliente_voz.sd, "play") as reproducir,
        ):
            cliente_voz.probar_microfono(8, None)
        reproducir.assert_not_called()

    def test_reconocimiento_envia_la_misma_toma_reproducida(self):
        muestras = np.array([100, -200, 300], dtype=np.int16)
        audio = muestras.tobytes()
        respuesta = SimpleNamespace(query_result=SimpleNamespace(
            query_text="hola", speech_recognition_confidence=0.95,
            intent=SimpleNamespace(display_name="Default Welcome Intent"),
            fulfillment_text="Hola",
        ))
        with (
            patch.object(cliente_voz, "leer_opciones", return_value=SimpleNamespace(
                listar_microfonos=False, probar_microfono=False,
                probar_reconocimiento=True, sin_recorte_silencio=False,
                segundos=8, microfono=None
            )),
            patch("builtins.input", return_value=""),
            patch("builtins.print") as salida,
            patch.object(cliente_voz, "escuchar", return_value=audio),
            patch.object(cliente_voz.sd, "play") as reproducir,
            patch.object(cliente_voz.sd, "wait"),
            patch.object(cliente_voz, "hablar_con_el_agente", return_value=respuesta) as enviar,
        ):
            cliente_voz.main()
        np.testing.assert_array_equal(reproducir.call_args.args[0], muestras)
        enviar.assert_called_once_with(audio)
        self.assertTrue(any("Confianza de voz: 0.95" in str(llamada) for llamada in salida.call_args_list))


if __name__ == "__main__":
    unittest.main()
