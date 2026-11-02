"""Vocabulario del catálogo de prueba para el reconocimiento del SKU."""

PISTAS_SKU = (
    "ESP32-LX6D-WBT-4M",
    "ESP32-LX6D-WBT-16M",
    "ESP32-S2S-W-4M",
    "ESP32-S3D-WBLE-8M8R",
    "ESP32-S3D-WBLE-16M8R",
    "ESP32-C2S-WBLE-2M",
    "ESP32-C3S-WBLE-4M",
    "ESP32-C5S-W6DB-4M",
    "ESP32-C6S-W6ZT-8M",
    "ESP32-H2S-ZBLE-4M",
    "ESP32-P4D-NC-16R",
)

ALIAS_SKU = {
    "placa uno": "ESP32-LX6D-WBT-4M",
    "placa 1": "ESP32-LX6D-WBT-4M",
}
PATRON_ALIAS_SKU = r"(?i)\bplaca\s+(?:uno|1)\b"
PISTAS_RECONOCIMIENTO_SKU = PISTAS_SKU + tuple(ALIAS_SKU)
