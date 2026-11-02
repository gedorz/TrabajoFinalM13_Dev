"""Decodificación de archivos de audio a PCM16 mono para Dialogflow."""

from pathlib import Path

import av


def cargar_audio(ruta: Path, frecuencia: int = 16000) -> bytes:
    bloques = []
    conversor = av.AudioResampler(format="s16", layout="mono", rate=frecuencia)
    with av.open(str(ruta)) as contenedor:
        for frame in contenedor.decode(audio=0):
            for convertido in conversor.resample(frame):
                bloques.append(convertido.to_ndarray().astype("<i2").tobytes())
        for convertido in conversor.resample(None):
            bloques.append(convertido.to_ndarray().astype("<i2").tobytes())
    if not bloques:
        raise ValueError(f"El archivo no contiene audio: {ruta.name}")
    return b"".join(bloques)
