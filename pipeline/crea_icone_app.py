"""Crea le icone dell'app (docs/app/icona-180.png e docs/app/icona-512.png): Caramella su fondo nero caldo, stile "Claude Code Retro".

Uso (con l'ambiente .venv-xtts, dove c'e' Pillow):
    python -I pipeline/crea_icone_app.py

Legge lo sprite 24x24 di Caramella da pipeline/risorse/caramella-fermo.png e lo ingrandisce di un numero intero di volte
(senza sfumature), centrato su un quadrato pieno: iOS arrotonda da solo gli angoli. L'icona sulla schermata Home si aggiorna solo
togliendola e aggiungendola di nuovo (iOS la salva quando si installa l'app).
"""
from pathlib import Path

from PIL import Image, ImageDraw

RADICE = Path(__file__).resolve().parent.parent
SPRITE = RADICE / "pipeline" / "risorse" / "caramella-fermo.png"
USCITA = RADICE / "docs" / "app"
FONDO = "#141413"      # cc-bg
OMBRA = "#4a463f"      # cc-border-strong


def icona(lato):
    img = Image.new("RGBA", (lato, lato), FONDO)
    d = ImageDraw.Draw(img)
    k = max(1, round(lato * 18 / 512))        # 512 -> x18, 180 -> x6
    scatola = 24 * k
    x = (lato - scatola) // 2
    y = lato // 2 - 15 * k                    # il corpo e l'ombra occupano le righe 6-24 dello sprite: il centro e' la riga 15
    d.rectangle([x + 6 * k, y + 23 * k, x + 18 * k - 1, y + 24 * k - 1], fill=OMBRA)
    sprite = Image.open(SPRITE).convert("RGBA").resize((scatola, scatola), Image.NEAREST)
    img.alpha_composite(sprite, (x, y)) if y >= 0 else img.paste(sprite, (x, y), sprite)
    return img.convert("RGB")


for lato in (180, 512):
    percorso = USCITA / f"icona-{lato}.png"
    icona(lato).save(percorso, "PNG", optimize=True)
    print("scritta", percorso, percorso.stat().st_size, "byte")
