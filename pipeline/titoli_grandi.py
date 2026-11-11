"""Elenca, pagina per pagina, le righe scritte con carattere molto piu' grande del testo normale.
Serve a trovare i titoli dei capitoli. Uso: python titoli_grandi.py "libro.pdf" [soglia_pt]"""
import sys
import pymupdf

pdf = sys.argv[1]
soglia = float(sys.argv[2]) if len(sys.argv) > 2 else 13.0
doc = pymupdf.open(pdf)
for n, p in enumerate(doc, 1):
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            testo = "".join(s["text"] for s in l["spans"]).strip()
            if not testo:
                continue
            size = max(s["size"] for s in l["spans"])
            if size >= soglia:
                print(f"p.{n:>3}  {size:5.1f}pt  y={l['bbox'][1]:6.1f}  {testo[:90]}")
