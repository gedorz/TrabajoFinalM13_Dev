"""
OCR offline con Tesseract + extraccion de datos con expresiones regulares.

Bloque 2 de la entrega: documentacion y busqueda documental.

Se ejecuta offline para guardar texto y campos extraídos en un JSON.
El webhook carga ese archivo sin volver a procesar las imágenes.

Uso suelto, para probar:
    python ocr.py
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytesseract
from PIL import Image

from documentacion_ocr import RUTA_CORPUS

# Configuracion

if shutil.which("tesseract") is None:
    ejecutable_windows = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if ejecutable_windows.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(ejecutable_windows)

CARPETA = Path(__file__).parent / "documentos"
EXTENSIONES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

# --psm 6 = "un bloque de texto uniforme". Si vuestros documentos tienen
# columnas, tablas o texto disperso, probad otros modos (--psm 3, 4, 11).
CONFIG_TESSERACT = "--psm 6"


# Extraccion de texto

def leer_documento(ruta: Path) -> str:
    """Pasa una imagen por Tesseract y devuelve el texto reconocido."""
    imagen = Image.open(ruta)

    # Preprocesado minimo: escala de grises. Es lo que mas mejora el resultado
    # por lo poco que cuesta. Si vuestras fotos salen mal, lo siguiente a
    # probar es subir resolucion y enderezar la imagen.
    imagen = imagen.convert("L")

    return pytesseract.image_to_string(
        imagen,
        lang="spa",              # sin esto, Tesseract asume ingles y rompe acentos
        config=CONFIG_TESSERACT,
    )


def cargar_documentos(carpeta: Path = CARPETA) -> dict[str, str]:
    """Devuelve {nombre_fichero: texto_reconocido} para toda la carpeta."""
    if not carpeta.exists():
        print(f"AVISO: no existe la carpeta {carpeta}. El RAG ira sin documentos.")
        return {}

    documentos = {}
    for ruta in sorted(carpeta.iterdir()):
        if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
            continue
        try:
            documentos[ruta.name] = leer_documento(ruta)
            print(f"  OCR OK: {ruta.name} ({len(documentos[ruta.name])} caracteres)")
        except Exception as e:
            print(f"  OCR FALLO en {ruta.name}: {e}")

    return documentos


# Extraccion de datos estructurados (requisito de regex del enunciado)

PATRONES = {
    #Placa de auto española: 4 digitos + 3 consonantes (sin vocales, N ni Q)
    "Placa": r"\b\d{4}\s?[B-DF-HJ-NP-TV-Z]{3}\b",
    # Los límites impiden aceptar un fragmento de una referencia más larga.
    "SKU": r"(?<![\w-])ESP32(?:-[A-Z0-9]+){2,4}(?![\w-])",
    # SKU: alterno
    "SKU_alterno": r"^[A-Za-z0-9_-]{1,40}$",
    # NIF: 8 digitos + letra
    "nif": r"\b\d{8}\s?[A-Z]\b",
    # Fechas tipo 14/03/2026, 14-3-26
    "fecha": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    # Importes: 1.234,56 EUR / 300 euros
    "importe": r"\b\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s?(?:€|EUR|euros?)\b",
    # Numero de poliza tipo AB-123456
    "poliza": r"\b[A-Z]{2,3}-?\d{6,}\b",
}


def extraer_datos(texto: str) -> dict[str, list[str]]:
    """Busca los patrones de PATRONES dentro de un texto ya reconocido."""
    return {
        campo: re.findall(patron, texto, re.IGNORECASE)
        for campo, patron in PATRONES.items()
    }


def normalizar_ocr(texto: str) -> str:
    """
    Corrige las confusiones tipicas del OCR antes de aplicar las regex.

    Tesseract confunde O/0, l/1, S/5, B/8 de forma sistematica. Una regex
    perfecta contra texto escrito falla contra texto reconocido.

    OJO: esto es destructivo. Usadlo solo sobre la copia que vais a pasar por
    las regex, nunca sobre el texto que le dais al modelo de lenguaje.
    """
    return (
        texto.replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace("S", "5")
        .replace("B", "8")
    )


def generar_corpus(carpeta: Path = CARPETA, destino: Path = RUTA_CORPUS) -> dict:
    rutas = sorted(
        ruta for ruta in carpeta.iterdir()
        if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES
    )
    if not rutas:
        raise ValueError(f"No hay imágenes para procesar en {carpeta}")
    textos = cargar_documentos(carpeta)
    fallidos = [ruta.name for ruta in rutas if not textos.get(ruta.name, "").strip()]
    if fallidos:
        raise ValueError(
            "No se guarda un corpus incompleto. Revisa el OCR de: " + ", ".join(fallidos)
        )
    corpus = {
        "version": 1,
        "motor": "Tesseract",
        "idioma": "spa",
        "configuracion": CONFIG_TESSERACT,
        "documentos": {
            ruta.name: {
                "sha256_imagen": hashlib.sha256(ruta.read_bytes()).hexdigest(),
                "texto": textos[ruta.name],
                "datos_extraidos": extraer_datos(textos[ruta.name]),
            }
            for ruta in rutas
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(destino)
    return corpus


def main():
    try:
        corpus = generar_corpus()
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR OCR: {error}") from error
    for nombre, documento in corpus["documentos"].items():
        print(f"\n{nombre}: {len(documento['texto'])} caracteres")
        for campo, valores in documento["datos_extraidos"].items():
            if valores:
                print(f"  {campo}: {valores}")
    print(f"\nCorpus guardado: {RUTA_CORPUS}")

if __name__ == "__main__":
    main()
