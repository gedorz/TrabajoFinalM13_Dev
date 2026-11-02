"""Mantiene un túnel temporal mientras esta terminal permanece abierta."""

from pathlib import Path
import subprocess


def main():
    ejecutable = Path(__file__).with_name("tools") / "cloudflared.exe"
    if not ejecutable.is_file():
        raise SystemExit(
            "Falta tools/cloudflared.exe. Descarga el ejecutable Windows de "
            "https://developers.cloudflare.com/tunnel/downloads/"
        )
    print("Mantén FastAPI activo en el puerto 8000 y esta terminal abierta.", flush=True)
    print("Copia la URL HTTPS anunciada y añade /webhook en Dialogflow.", flush=True)
    try:
        return subprocess.call([
            str(ejecutable), "tunnel", "--no-autoupdate", "--protocol", "http2",
            "--url", "http://127.0.0.1:8000",
        ])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
