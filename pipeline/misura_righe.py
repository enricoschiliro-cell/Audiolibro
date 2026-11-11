"""Misura quanto varia la dimensione delle righe nei paragrafi veri (blocchi lunghi),
rispetto alla dimensione tipica della pagina. Serve a scegliere la soglia per le didascalie.
Uso: python misura_righe.py "libro.pdf" inizio fine"""
import statistics
import sys
from collections import Counter

import pymupdf

doc = pymupdf.open(sys.argv[1])
a, b = int(sys.argv[2]), int(sys.argv[3])
rapporti = []
for n in range(a, b + 1):
    blocchi = []
    for bl in doc[n - 1].get_text("dict")["blocks"]:
        if bl["type"] != 0:
            continue
        righe = []
        for l in bl["lines"]:
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                righe.append((t, sum(s["size"] * len(s["text"]) for s in l["spans"]) / max(1, sum(len(s["text"]) for s in l["spans"]))))
        if righe:
            blocchi.append(righe)
    lunghi = [r for bl in blocchi if sum(len(t) for t, _ in bl) >= 200 for r in bl]
    if not lunghi:
        continue
    rif = statistics.median(s for _, s in lunghi)
    for t, s in lunghi:
        rapporti.append((s / rif, n, t[:50]))

fasce = Counter(round(r, 2) // 0.05 * 0.05 for r, _, _ in rapporti)
print("Rapporto riga/dimensione tipica (fascia: n. righe) nei paragrafi veri:")
for f in sorted(fasce):
    print(f"  {f:4.2f}-{f+0.05:4.2f}: {fasce[f]}")
print("\nRighe dei paragrafi veri sotto 0.90 (potrebbero essere scartate per errore):")
for r, n, t in sorted(rapporti)[:15]:
    if r < 0.90:
        print(f"  {r:4.2f}  p.{n}  {t}")
