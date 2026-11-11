"""Prepara un breve campione in italiano (inizio del Capitolo primo di Ivanhoe) per provare le voci.
Crea output/ivanhoe/frasi/00-prova-italiano.json nello stesso formato dei capitoli di Whyte,
cosi' prova_voci.py lo legge senza modifiche.

Uso: python campione_italiano.py "scott_ivanhoe.pdf" [pagina=8]
(Provvisorio: la pulizia completa di Ivanhoe, con il testo doppio per pagina, viene dopo.)"""
import json
import re
import sys
from pathlib import Path

import pymupdf
import pysbd

RADICE = Path(__file__).resolve().parent.parent
pdf = sys.argv[1]
pagina = int(sys.argv[2]) if len(sys.argv) > 2 else 8

righe = pymupdf.open(pdf)[pagina - 1].get_text().split("\n")
# Il testo della pagina compare due volte: tengo solo la prima copia (fino al numero di pagina)
prima_copia = []
for r in righe:
    if r.strip() == str(pagina):
        break
    prima_copia.append(r.strip())
prima_copia = [r for r in prima_copia if r and not r.upper().startswith("CAPITOLO")]

# Paragrafi: una riga che finisce con un punto ed e' piu' corta del normale chiude il paragrafo
lung_max = max(len(r) for r in prima_copia)
paragrafi, corrente = [], []
for r in prima_copia:
    corrente.append(r)
    if r.endswith((".", "!", "?")) and len(r) < lung_max * 0.85:
        paragrafi.append(" ".join(corrente))
        corrente = []
if corrente:
    paragrafi.append(" ".join(corrente))

seg = pysbd.Segmenter(language="it", clean=False)
blocchi = []
for p in paragrafi:
    frasi = [f.strip() for f in seg.segment(re.sub(r"\s+", " ", p)) if f.strip()]
    frasi = [f for f in frasi if f[-1] in ".!?»”"]       # scarto l'ultima frase se la pagina la tronca
    if frasi:
        blocchi.append({"tipo": "paragrafo", "frasi": frasi})

uscita = RADICE / "output" / "ivanhoe" / "frasi"
uscita.mkdir(parents=True, exist_ok=True)
dati = {"capitolo": 1, "titolo": "Capitolo primo", "annuncio": "Capitolo uno.", "blocchi": blocchi}
(uscita / "00-prova-italiano.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
n = sum(len(b["frasi"]) for b in blocchi)
print(f"{len(blocchi)} paragrafi, {n} frasi, {sum(len(f.split()) for b in blocchi for f in b['frasi'])} parole")
for b in blocchi:
    print("-", b["frasi"][0][:70], "...", b["frasi"][-1][-50:])
