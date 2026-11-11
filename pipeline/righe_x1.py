"""Mostra x0, x1 e altezza delle righe che contengono certe parole, per misurare le distanze.
Uso: python righe_x1.py "libro.pdf" pagina "parola" ["parola" ...]"""
import sys
import pymupdf

doc = pymupdf.open(sys.argv[1])
n = int(sys.argv[2])
for b in doc[n - 1].get_text("dict")["blocks"]:
    if b["type"] != 0:
        continue
    for l in b["lines"]:
        t = "".join(s["text"] for s in l["spans"])
        if any(p in t for p in sys.argv[3:]):
            print(f"x0={l['bbox'][0]:5.0f} x1={l['bbox'][2]:5.0f} y={l['bbox'][1]:5.0f} size={max(s['size'] for s in l['spans']):4.1f} | {t[:60]}")
