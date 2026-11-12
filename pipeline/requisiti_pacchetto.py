"""Stampa i requisiti dichiarati da un pacchetto Python scaricato (file .whl), senza installarlo.
Uso: python requisiti_pacchetto.py file.whl"""
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as z:
    meta = next(n for n in z.namelist() if n.endswith("METADATA"))
    for riga in z.read(meta).decode("utf-8").splitlines():
        if riga.startswith(("Name:", "Version:", "Requires-Python:", "Requires-Dist:", "License")):
            if "extra ==" in riga:
                continue
            print(riga)
