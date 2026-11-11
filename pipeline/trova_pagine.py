"""Trova in quali pagine del PDF compaiono certe parole o frasi.
Uso: python trova_pagine.py "libro.pdf" inizio fine "frase1" "frase2" ..."""
import sys
import pymupdf

doc = pymupdf.open(sys.argv[1])
a, b = int(sys.argv[2]), int(sys.argv[3])
for n in range(a, b + 1):
    testo = doc[n - 1].get_text().replace("\n", " ")
    for frase in sys.argv[4:]:
        if frase in testo:
            print(f"p.{n}  ->  {frase}")
