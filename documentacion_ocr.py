"""Lectura del corpus persistido, sin ejecutar OCR en el servidor."""

import json
from pathlib import Path

RUTA_CORPUS = Path(__file__).resolve().parent / "documentos" / "texto_ocr.json"


def cargar_documentos(ruta: Path = RUTA_CORPUS) -> dict[str, str]:
    try:
        corpus = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"Falta el corpus OCR: {ruta}. Ejecuta primero: python ocr.py"
        ) from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"No se puede leer el corpus OCR {ruta}: {error}") from error

    if not isinstance(corpus, dict) or corpus.get("version") != 1:
        raise ValueError("Formato de corpus OCR no compatible. Ejecuta: python ocr.py")
    documentos = corpus.get("documentos")
    if not isinstance(documentos, dict) or not documentos:
        raise ValueError("El corpus OCR no contiene documentos.")
    textos = {}
    for nombre, documento in documentos.items():
        if not isinstance(documento, dict):
            raise ValueError(f"Documento OCR inválido: {nombre}")
        texto = documento.get("texto")
        datos = documento.get("datos_extraidos")
        if not isinstance(texto, str) or not texto.strip() or not isinstance(datos, dict):
            raise ValueError(f"Falta texto OCR o datos extraídos en {nombre}")
        textos[nombre] = texto
    return textos
