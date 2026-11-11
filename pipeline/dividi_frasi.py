"""PASSO 2 - Divide il testo pulito di ogni capitolo in frasi.

Uso:   python dividi_frasi.py libri\\whyte.json [numero_capitolo ...]

Legge  output/<id>/testo/*.md  (creati da estrai_libro.py)
Scrive output/<id>/frasi/*.json  con, per ogni capitolo:
  - "annuncio": la frase che la voce legge all'inizio ("Chapter four. Food.")
  - "blocchi":  titolo, sottotitoli e paragrafi, ognuno con la lista delle sue frasi
Scrive anche output/<id>/frasi/_da_controllare.txt: frasi molto corte o sospette,
per verificare a occhio che la divisione sia giusta.
"""
import json
import re
import sys
from pathlib import Path

import pysbd
from num2words import num2words

RADICE = Path(__file__).resolve().parent.parent

# Frasi che la voce legge per annunciare un capitolo, per lingua
ANNUNCI = {
    "en": "Chapter {num}. {titolo}.",
    "it": "Capitolo {num}. {titolo}.",
}


def slug(testo):
    return re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")


def spezza(segmentatore, testo):
    """Divide un paragrafo in frasi e ripulisce gli spazi."""
    return [f.strip() for f in segmentatore.segment(testo) if f.strip()]


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    solo = {int(x) for x in sys.argv[2:]}
    lingua = config["lingua"]
    seg = pysbd.Segmenter(language=lingua, clean=False)
    base = RADICE / "output" / config["id"]
    (base / "frasi").mkdir(parents=True, exist_ok=True)
    da_controllare = []
    progressivo = 0

    for cap in config["capitoli"]:
        if not cap.get("includi", True):
            continue
        progressivo += 1
        if solo and cap["n"] not in solo:
            continue
        etichetta = f"{progressivo:02d}-{slug(cap['titolo'])}"
        origine = base / "testo" / f"{etichetta}.md"
        righe = [r.rstrip() for r in origine.read_text(encoding="utf-8").split("\n")]

        blocchi = []
        for r in righe:
            if not r.strip() or r.startswith("# "):
                continue                                   # il titolo grande lo gestisce "annuncio"
            if r.startswith("## "):
                blocchi.append({"tipo": "sottotitolo", "frasi": [r[3:].strip()]})
            else:
                blocchi.append({"tipo": "paragrafo", "frasi": spezza(seg, r)})

        if cap["n"] > 0:
            annuncio = ANNUNCI[lingua].format(num=num2words(cap["n"], lang=lingua), titolo=cap["titolo"])
        else:
            annuncio = cap["titolo"] + "."          # Foreword, Preface, Introduction: solo il titolo

        n_frasi = sum(len(b["frasi"]) for b in blocchi)
        n_parole = sum(len(f.split()) for b in blocchi for f in b["frasi"])
        (base / "frasi" / f"{etichetta}.json").write_text(
            json.dumps({"capitolo": cap["n"], "titolo": cap["titolo"], "annuncio": annuncio, "blocchi": blocchi},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"{etichetta:50} blocchi {len(blocchi):3}  frasi {n_frasi:4}  parole {n_parole:5}")

        for b in blocchi:
            for f in b["frasi"]:
                parole = f.split()
                if b["tipo"] == "paragrafo" and (len(parole) <= 3 or len(parole) > 70 or f[-1] not in '.?!"”’)'):
                    da_controllare.append(f"{etichetta} | {len(parole):3} parole | {f[:110]}")

    (base / "frasi" / "_da_controllare.txt").write_text("\n".join(da_controllare), encoding="utf-8")
    print(f"\nFrasi da controllare a occhio: {len(da_controllare)}  (vedi _da_controllare.txt)")


if __name__ == "__main__":
    main()
