"""Parada de captura por silencio continuo, sin activar el micrófono."""

import unittest
from unittest.mock import patch

import numpy as np

from audio_voz import DetectorSilencio
import cliente_voz
from docs.codetest.audio_simulado import FlujoAudioSimulado

FS = 16000


def voz(segundos):
    tiempo = np.arange(int(segundos * FS)) / FS
    return (3000 * np.sin(2 * np.pi * 200 * tiempo)).astype("<i2")


def silencio(segundos):
    return np.zeros(int(segundos * FS), dtype="<i2")


class ParadaSilencioTests(unittest.TestCase):
    def capturar(self, muestras, maximo):
        orden = []
        flujo = FlujoAudioSimulado(muestras, orden)
        with (
            patch.object(cliente_voz.sd, "InputStream", return_value=flujo),
            patch("builtins.print") as salida,
        ):
            resultado = cliente_voz.capturar_hasta_silencio(maximo, 1)
        self.assertEqual(orden, ["captura iniciada", "fin captura"])
        return resultado, salida

    def test_parada_tras_voz_y_mas_de_tres_segundos_de_silencio(self):
        muestras = np.concatenate((voz(1), silencio(5)))
        resultado, salida = self.capturar(muestras, 12)
        self.assertEqual(len(resultado), 4 * FS + 320)
        np.testing.assert_array_equal(resultado[:, 0], muestras[:4 * FS + 320])
        self.assertTrue(any("Grabación detenida" in str(llamada) for llamada in salida.call_args_list))

    def test_silencio_inicial_y_limite_exacto(self):
        detector = DetectorSilencio(FS, segundos=3)
        self.assertFalse(detector.actualizar(silencio(3)))
        self.assertTrue(detector.actualizar(silencio(0.020)))
        resultado, _ = self.capturar(silencio(5), 12)
        self.assertEqual(len(resultado), 3 * FS + 320)

    def test_pausa_corta_se_conserva_y_el_sonido_reinicia_el_contador(self):
        muestras = np.concatenate((voz(0.5), silencio(2.5), voz(0.5), silencio(4)))
        resultado, _ = self.capturar(muestras, 12)
        fin = int(6.5 * FS) + 320
        self.assertEqual(len(resultado), fin)
        np.testing.assert_array_equal(resultado[:, 0], muestras[:fin])

    def test_sonido_continuo_respeta_el_tiempo_maximo(self):
        muestras = voz(3)
        resultado, salida = self.capturar(muestras, 2)
        self.assertEqual(len(resultado), 2 * FS)
        np.testing.assert_array_equal(resultado[:, 0], muestras[:2 * FS])
        self.assertFalse(any("Grabación detenida" in str(llamada) for llamada in salida.call_args_list))


if __name__ == "__main__":
    unittest.main()
