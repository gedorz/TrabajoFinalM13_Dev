"""Entrada de audio por bloques para pruebas sin hardware."""

import numpy as np


class FlujoAudioSimulado:
    def __init__(self, muestras, orden=None):
        self.muestras = np.asarray(muestras).reshape(-1, 1)
        self.posicion = 0
        self.orden = orden

    def __enter__(self):
        self.posicion = 0
        if self.orden is not None:
            self.orden.append("captura iniciada")
        return self

    def __exit__(self, *args):
        if self.orden is not None:
            self.orden.append("fin captura")
        return False

    def read(self, cantidad):
        fin = self.posicion + cantidad
        if fin > len(self.muestras):
            raise AssertionError("La captura ha sobrepasado el audio simulado")
        bloque = self.muestras[self.posicion:fin].copy()
        self.posicion = fin
        return bloque, False
