"""Mostra i blocchi di testo di una pagina: posizione, dimensione e nome del carattere.
Serve a capire come distinguere testo del libro, didascalie e numeri di pagina.
Uso: python blocchi_pagina.py "libro.pdf" pagina [pagina ...]"""
import sys
import pymupdf

doc = pymupdf.open(sys.argv[1])
for n in map(int, sys.argv[2:]):
    p = doc[n - 1]
    print(f"\n===== PAGINA {n}  (larghezza {p.rect.width:.0f}, altezza {p.rect.height:.0f}) =====")
    for b in p.get_text("dict")["blocks"]:
        if b["type"] != 0:
            print(f"  [immagine] y={b['bbox'][1]:.0f}-{b['bbox'][3]:.0f}")
            continue
        sizes, fonts, testo = [], set(), []
        for l in b["lines"]:
            for s in l["spans"]:
                sizes.append(s["size"]); fonts.add(s["font"])
            testo.append("".join(s["text"] for s in l["spans"]).strip())
        riga = " ".join(testo)
        x0, y0, x1, y1 = b["bbox"]
        print(f"  x={x0:5.0f}-{x1:5.0f} y={y0:5.0f}-{y1:5.0f} size={sum(sizes)/len(sizes):4.1f} {','.join(sorted(fonts))[:28]:28} | {riga[:70]}")
