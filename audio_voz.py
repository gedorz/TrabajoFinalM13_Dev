"""Recorte conservador de los bordes de grabaciones PCM16 mono."""

import numpy as np


class DetectorSilencio:
    """Cuenta silencio consecutivo por bloques, reiniciándolo al detectar señal."""

    def __init__(self, frecuencia: int = 16000, segundos: float = 3.0):
        self.limite_muestras = int(frecuencia * segundos)
        self.muestras_silenciosas = 0

    def actualizar(self, muestras: np.ndarray) -> bool:
        amplitudes = muestras.astype(np.float64) / 32768
        nivel = float(np.sqrt(np.mean(amplitudes ** 2)))
        if nivel >= 0.002:
            self.muestras_silenciosas = 0
        else:
            self.muestras_silenciosas += len(muestras)
        return self.muestras_silenciosas > self.limite_muestras


def recortar_silencio(
    audio: bytes, frecuencia: int = 16000, margen_ms: int = 300
) -> bytes:
    if frecuencia <= 0 or margen_ms < 0:
        raise ValueError("La frecuencia debe ser positiva y el margen no negativo")
    if not audio:
        return audio

    muestras = np.frombuffer(audio, dtype="<i2")
    amplitudes = muestras.astype(np.float64) / 32768
    bloque = max(1, int(frecuencia * 0.020))
    relleno = (-len(amplitudes)) % bloque
    ventanas = np.pad(amplitudes, (0, relleno)).reshape(-1, bloque)
    niveles = np.sqrt(np.mean(ventanas ** 2, axis=1))
    umbral = max(0.002, float(np.percentile(niveles, 90)) * 0.10)
    activos = np.flatnonzero(niveles >= umbral)
    if activos.size == 0:
        # No asumir que una voz muy baja es silencio: conservar la toma.
        return audio

    margen = int(frecuencia * margen_ms / 1000)
    inicio = max(0, int(activos[0]) * bloque - margen)
    fin = min(len(muestras), (int(activos[-1]) + 1) * bloque + margen)
    # Un único corte conserva pausas internas, muestras y nivel originales.
    return audio[inicio * 2:fin * 2]
