"""Esplora un PDF: pagine, testo estratto, indice (se c'e'), font piu' usati.
Uso: python esplora_pdf.py "percorso.pdf" [pagina_inizio pagina_fine]
Non modifica nulla: legge soltanto."""
import sys
from collections import Counter
import pymupdf

pdf = sys.argv[1]
doc = pymupdf.open(pdf)
print("Pagine:", len(doc))
print("Indice (TOC):", doc.get_toc()[:40] or "nessuno")

# Quanta pagina ha testo estraibile
senza_testo = [i + 1 for i, p in enumerate(doc) if len(p.get_text().strip()) < 30]
print("Pagine quasi senza testo:", len(senza_testo), senza_testo[:20])

# Dimensioni del carattere: la piu' frequente e' il testo normale, le piu' grandi sono i titoli
dim = Counter()
for p in doc:
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                dim[round(s["size"], 1)] += len(s["text"])
print("Dimensioni carattere (dimensione: n. caratteri):", dim.most_common(8))

a = int(sys.argv[2]) if len(sys.argv) > 2 else 1
b = int(sys.argv[3]) if len(sys.argv) > 3 else 3
for n in range(a, b + 1):
    print(f"\n===== PAGINA {n} =====")
    print(doc[n - 1].get_text()[:1800])
