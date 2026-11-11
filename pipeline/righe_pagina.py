"""Mostra riga per riga una pagina: blocco, posizione, dimensione e testo.
Uso: python righe_pagina.py "libro.pdf" pagina [pagina ...]"""
import sys
import pymupdf

doc = pymupdf.open(sys.argv[1])
for n in map(int, sys.argv[2:]):
    print(f"\n===== PAGINA {n} =====")
    for i, b in enumerate(doc[n - 1].get_text("dict")["blocks"]):
        if b["type"] != 0:
            continue
        print(f"-- blocco {i}  y={b['bbox'][1]:.0f}-{b['bbox'][3]:.0f}")
        for l in b["lines"]:
            t = "".join(s["text"] for s in l["spans"])
            size = max(s["size"] for s in l["spans"])
            print(f"   x0={l['bbox'][0]:5.0f} y={l['bbox'][1]:5.0f} size={size:4.1f} | {t[:70]}")
