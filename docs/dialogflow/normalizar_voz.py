"""Normalización estricta de un SKU dictado completo, sin completar fragmentos."""

import re
import unicodedata

from docs.dialogflow.pistas_voz import ALIAS_SKU, PISTAS_SKU


def compactar_dictado(texto: str) -> str:
    limpio = " ".join(texto.casefold().split())
    limpio = "".join(
        c for c in unicodedata.normalize("NFKD", limpio)
        if not unicodedata.combining(c)
    )
    limpio = re.sub(r"^(?:(?:el|la)\s+)?(?:producto|codigo(?:\s+sku)?|sku)\s*[: ]\s*", "", limpio)
    limpio = re.sub(r"^el\s+(?=esp\s*32\b)", "", limpio)
    if re.match(r"esp\s*32\b", limpio):
        limpio = re.sub(r"\bde\b", "d", limpio)
    return re.sub(r"[^a-z0-9]", "", limpio)


def codigo_dictado(texto: str) -> str | None:
    alias = " ".join(texto.casefold().split())
    if alias in ALIAS_SKU:
        return ALIAS_SKU[alias]
    compacto = compactar_dictado(texto)
    for codigo in PISTAS_SKU:
        if compacto == re.sub(r"[^a-z0-9]", "", codigo.casefold()):
            return codigo
    return None


def distancia_edicion(izquierda: str, derecha: str) -> int:
    anterior = list(range(len(derecha) + 1))
    for fila, letra in enumerate(izquierda, 1):
        actual = [fila]
        for columna, otra in enumerate(derecha, 1):
            actual.append(min(
                actual[-1] + 1, anterior[columna] + 1,
                anterior[columna - 1] + (letra != otra),
            ))
        anterior = actual
    return anterior[-1]


def sugerir_codigo(texto: str) -> str | None:
    """Una propuesta nunca equivale a aceptar el código sin confirmación."""
    compacto = compactar_dictado(texto)
    memoria = re.search(r"\d+[mr](?:\d+r)?$", compacto)
    if not compacto.startswith("esp32") or len(compacto) < 12 or not memoria:
        return None
    candidatos = sorted(
        (distancia_edicion(compacto, re.sub(r"[^a-z0-9]", "", codigo.casefold())), codigo)
        for codigo in PISTAS_SKU
        if codigo.split("-")[-1].casefold() == memoria.group()
    )
    if not candidatos or candidatos[0][0] > 2:
        return None
    if len(candidatos) > 1 and candidatos[1][0] - candidatos[0][0] < 2:
        return None
    return candidatos[0][1]


def confirmacion_dictada(texto: str) -> bool | None:
    limpio = " ".join(re.sub(r"[^a-záéíóúüñ0-9 ]", " ", texto.casefold()).split())
    negativa = r"(?:no(?:\s+es\s+correcto|\s+confirmo)?|incorrecto)"
    afirmativa = r"(?:s[ií]|(?:es\s+)?correcto|confirmo|(?:estoy\s+)?de\s+acuerdo)"
    if re.fullmatch(rf"{negativa}(?:\s+{negativa})*", limpio):
        return False
    if re.fullmatch(rf"{afirmativa}(?:\s+{afirmativa})*", limpio):
        return True
    return None


def ciudad_dictada(texto: str) -> str | None:
    coincidencia = re.fullmatch(
        r"\s*(?:(?:para|en|a)\s+)?(?:la\s+)?ciudad\s+de\s+"
        r"([a-záéíóúüñ]+(?:[ -][a-záéíóúüñ]+){0,3})\s*[.!?]?\s*",
        texto, re.IGNORECASE,
    )
    return coincidencia.group(1).strip().title() if coincidencia else None
