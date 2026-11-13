"""Crea le icone dell'app (docs/app/icona-180.png e docs/app/icona-512.png): Caramella che legge, su fondo nero caldo, stile "Claude Code Retro".

Uso (con l'ambiente .venv-xtts, dove c'e' Pillow):
    python -I pipeline/crea_icone_app.py

Legge lo sprite 24x24 di Caramella da pipeline/risorse/caramella-legge.png (la posa con il libro) e lo ingrandisce di un numero
intero di volte (senza sfumature), centrato su un quadrato pieno: iOS arrotonda da solo gli angoli. L'ombra sotto i piedi e il
centro verticale si calcolano dai pixel dello sprite, cosi' funziona con qualunque posa. L'icona sulla schermata Home si
aggiorna solo togliendola e aggiungendola di nuovo (iOS la salva quando si installa l'app).
"""
from pathlib import Path

from PIL import Image, ImageDraw

RADICE = Path(__file__).resolve().parent.parent
SPRITE = RADICE / "pipeline" / "risorse" / "caramella-legge.png"
USCITA = RADICE / "docs" / "app"
FONDO = "#141413"      # cc-bg
OMBRA = "#4a463f"      # cc-border-strong


def icona(lato):
    sprite0 = Image.open(SPRITE).convert("RGBA")
    sx0, sy0, sx1, sy1 = sprite0.getbbox()          # il rettangolo occupato dal personaggio (colonne e righe dello sprite)
    riga_ombra = sy1 + 1                            # una riga vuota sotto i piedi, poi l'ombra (come nel tema)
    k = max(1, round(lato * 18 / 512))              # 512 -> x18, 180 -> x6
    scatola = 24 * k
    x = (lato - scatola) // 2 + ((24 - (sx0 + sx1)) * k) // 2   # centro orizzontale del personaggio = centro dell'icona
    y = (lato - (sy0 + riga_ombra + 1) * k) // 2                # centro verticale di personaggio + ombra = centro dell'icona
    img = Image.new("RGBA", (lato, lato), FONDO)
    d = ImageDraw.Draw(img)
    d.rectangle([x + 6 * k, y + riga_ombra * k, x + 18 * k - 1, y + (riga_ombra + 1) * k - 1], fill=OMBRA)
    sprite = sprite0.resize((scatola, scatola), Image.NEAREST)
    img.alpha_composite(sprite, (x, y))
    return img.convert("RGB")


for lato in (180, 512):
    percorso = USCITA / f"icona-{lato}.png"
    icona(lato).save(percorso, "PNG", optimize=True)
    print("scritta", percorso, percorso.stat().st_size, "byte")
