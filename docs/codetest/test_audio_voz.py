"""Recorte de bordes sin eliminar voz ni pausas internas."""

import unittest
from unittest.mock import patch

import numpy as np

from audio_voz import recortar_silencio
import cliente_voz
from docs.codetest.audio_simulado import FlujoAudioSimulado

FS = 16000


def tono(segundos):
    tiempo = np.arange(int(segundos * FS)) / FS
    return (3000 * np.sin(2 * np.pi * 200 * tiempo)).astype("<i2")


def silencio(segundos):
    return np.zeros(int(segundos * FS), dtype="<i2")


class AudioVozTests(unittest.TestCase):
    def test_recorta_bordes_y_conserva_margen_y_muestras(self):
        muestras = np.concatenate((silencio(2), tono(1), silencio(5)))
        resultado = recortar_silencio(muestras.tobytes())
        esperado = muestras[2 * FS - 4800:3 * FS + 4800].tobytes()
        self.assertEqual(resultado, esperado)
        self.assertAlmostEqual(len(resultado) / (FS * 2), 1.6)

    def test_pausas_internas_y_silabas_de_bajo_nivel_se_conservan(self):
        # Este tramo débil queda dentro del margen previo al primer bloque fuerte.
        comienzo = (tono(0.2).astype(np.float64) * 0.005).astype("<i2")
        muestras = np.concatenate((
            silencio(1), comienzo, tono(0.4), silencio(1), tono(0.4), silencio(1)
        ))
        resultado = recortar_silencio(muestras.tobytes())
        esperado = muestras[int(0.9 * FS):int(3.3 * FS)].tobytes()
        self.assertEqual(resultado, esperado)

    def test_no_descarta_audio_de_bajo_nivel_ni_altera_toma_sin_bordes(self):
        debil = (tono(1).astype(np.float64) * 0.005).astype("<i2").tobytes()
        continua = tono(1).tobytes()
        self.assertEqual(recortar_silencio(debil), debil)
        self.assertEqual(recortar_silencio(continua), continua)
        self.assertEqual(recortar_silencio(silencio(1).tobytes()), silencio(1).tobytes())
        self.assertEqual(recortar_silencio(b""), b"")

    def test_captura_aplica_recorte_y_permite_desactivarlo(self):
        muestras = np.concatenate((silencio(2), tono(1), silencio(5))).reshape(-1, 1)
        with (
            patch.object(cliente_voz.sd, "query_devices", return_value={"name": "Prueba", "index": 1}),
            patch.object(cliente_voz.sd, "check_input_settings"),
            patch.object(cliente_voz.sd, "InputStream", return_value=FlujoAudioSimulado(muestras)),
            patch("builtins.print") as salida,
        ):
            preparada = cliente_voz.escuchar(8)
            completa = cliente_voz.escuchar(8, recortar=False)
        self.assertEqual(preparada, recortar_silencio(muestras.tobytes()))
        self.assertEqual(completa, muestras[:6 * FS + 320].tobytes())
        self.assertTrue(any("audio preparado: 1.60s" in str(llamada) for llamada in salida.call_args_list))


if __name__ == "__main__":
    unittest.main()
