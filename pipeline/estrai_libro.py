"""PASSO 1 - Estrae e pulisce il testo di un libro in PDF, capitolo per capitolo.

Uso:   python estrai_libro.py libri\\whyte.json [numero_capitolo ...]

Cosa fa (legge soltanto il PDF, non lo modifica):
  - tiene solo il testo vero del libro: toglie numeri di pagina, titoli grandi,
    didascalie delle foto, etichette di grafici e testo senza senso;
  - ricostruisce i paragrafi (dal rientro della prima riga) e riunisce le parole
    spezzate a fine riga ("peo- ple" -> "people");
  - scrive un file per capitolo in  output/<id>/testo/
  - scrive due rapporti da controllare a occhio: scartati.txt e revisione.txt
"""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from spellchecker import SpellChecker

RADICE = Path(__file__).resolve().parent.parent
FINE_FRASE = tuple('.?!:;"”’)»…')
dizionario = SpellChecker()  # inglese; serve per capire se una parola spezzata va riunita


# ------------------------------------------------------------------ lettura pagina
def leggi_blocchi(pagina):
    """Restituisce i blocchi di testo della pagina con righe, posizione e dimensione del carattere."""
    blocchi = []
    for b in pagina.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        righe = []
        for l in b["lines"]:
            testo = "".join(s["text"] for s in l["spans"]).strip()
            if not testo:
                continue
            pesi = [len(s["text"].strip()) for s in l["spans"]]
            tot = sum(pesi)
            if not tot:
                continue
            size = sum(s["size"] * p for s, p in zip(l["spans"], pesi)) / tot
            righe.append({"x0": l["bbox"][0], "x1": l["bbox"][2], "y0": l["bbox"][1], "t": testo, "size": size})
        righe = fondi_righe(righe)
        if righe:
            blocchi.append(crea_blocco(righe, b["bbox"][1], b["bbox"][3]))
    return blocchi


def fondi_righe(righe):
    """Il riconoscimento a volte spezza UNA riga fisica in pezzi (e aggiunge letture doppie o disturbi).
    Qui ricompongo: pezzi vicini alla stessa altezza -> una riga sola, da sinistra a destra;
    due letture sovrapposte della stessa zona -> tengo quella piu' lunga."""
    out = []
    for L in righe:
        for R in out[-8:]:
            if abs(L["y0"] - R["y0"]) > 4:
                continue
            sovrapp = min(L["x1"], R["x1"]) - max(L["x0"], R["x0"])
            piccola = max(1.0, min(L["x1"] - L["x0"], R["x1"] - R["x0"]))
            if sovrapp > 0.4 * piccola:
                if len(L["t"]) > len(R["t"]):
                    R.update(L)
                break
            if L["x0"] <= R["x1"] + 12 and R["x0"] <= L["x1"] + 12:
                a, b = (R, L) if R["x0"] <= L["x0"] else (L, R)
                pa, pb = len(a["t"]), len(b["t"])
                R.update({
                    "t": a["t"] + " " + b["t"],
                    "size": (a["size"] * pa + b["size"] * pb) / (pa + pb),
                    "x0": min(a["x0"], b["x0"]), "x1": max(a["x1"], b["x1"]), "y0": min(a["y0"], b["y0"]),
                })
                break
        else:
            out.append(dict(L))
    return out


def crea_blocco(righe, y0, y1):
    """Costruisce un blocco a partire dalle sue righe (dimensione media pesata sui caratteri)."""
    peso = sum(len(r["t"]) for r in righe)
    size = sum(r["size"] * len(r["t"]) for r in righe) / peso
    return {"righe": righe, "size": size, "y0": y0, "y1": y1, "testo": " ".join(r["t"] for r in righe)}


def motivo_scarto_riga(r, rif, x0_tipico, blocco_lungo):
    """Scarta singole righe che si sono infilate nel testo: didascalie di foto e disturbi."""
    t = r["t"]
    if r["size"] < rif * 0.6:
        return "disturbo (carattere minuscolo)"
    if r["size"] < rif * 0.84:
        return "didascalia (riga)"
    # riga piccola e spostata in un'altra colonna: didascalia infilata tra le righe del testo
    if r["size"] < rif * 0.92 and abs(r["x0"] - x0_tipico) > 40:
        return "didascalia (riga fuori colonna)"
    if not blocco_lungo:
        return None  # nei blocchi cortissimi (sottotitoli come "Sun") le regole sotto non valgono
    if len(t) <= 3 and not t.endswith((".", ",", ";", ":", "?", "!", "”", "’", '"', ")", "-")):
        return "frammento (riga)"
    lettere = [c for c in t if c.isalpha()]
    if len(t) < 12 and len(lettere) >= 2 and sum(c.isupper() for c in lettere) / len(lettere) > 0.6:
        return "disturbo (riga)"
    return None


def dimensione_testo_normale(blocchi):
    """Dimensione tipica del testo del libro: mediana dei blocchi lunghi (i paragrafi)."""
    grandi = [b["size"] for b in blocchi if len(b["testo"]) >= 200]
    return statistics.median(grandi) if grandi else None


# ------------------------------------------------------------------ scarto dei blocchi inutili
def motivo_scarto(b, altezza, rif):
    """Se il blocco non fa parte del testo del libro, dice perche'. Altrimenti None."""
    t = b["testo"]
    if re.fullmatch(r"\d{1,3}", t) and (b["y0"] > altezza * 0.88 or b["y1"] < altezza * 0.1):
        return "numero di pagina"
    if b["size"] > rif * 1.3:
        return "titolo grande"
    # didascalia: carattere piccolo. I blocchi lunghi (didascalie di grafici) li scarto solo se molto piccoli.
    if b["size"] < rif * 0.9 and (len(t) < 600 or b["size"] < rif * 0.86):
        return "didascalia"
    parole = re.findall(r"[A-Za-z]{3,}", t)
    if len(t.split()) and len(parole) / len(t.split()) < 0.5:
        return "testo senza senso (grafico?)"
    if len(t) <= 12 and not any(c.islower() for c in t) and not re.search(r"\d", t):
        return "disturbo (poche lettere maiuscole)"
    lettere = [c for c in t if c.isalpha()]
    if len(lettere) >= 8 and sum(c.isupper() for c in lettere) / len(lettere) > 0.8 and len(t) < 250:
        return "etichetta in maiuscolo (grafico?)"
    if re.match(r"(CHART|FIGURE|TABLE)\b", t):
        return "grafico"
    return None


# ------------------------------------------------------------------ unione delle righe
def unisci_righe(righe):
    """Unisce righe di testo; se una riga finisce con '-' riunisce la parola quando e' una parola vera."""
    out = ""
    for t in righe:
        if out.endswith("=") and t and t[0].islower():
            out = out[:-1] + "-"             # il riconoscimento ha letto il trattino come "="
        if out.endswith("-") and t and t[0].islower():
            testa = re.search(r"([A-Za-z]+)-$", out)
            coda = re.match(r"([A-Za-z]+)", t)
            if not (testa and coda):
                out = out + t
                continue
            h, c = testa.group(1).lower(), coda.group(1).lower()
            if dizionario.known([h + c]):
                out = out[:-1] + t           # "peo-" + "ple" -> "people"
            elif dizionario.known([h]) and dizionario.known([c]):
                out = out + t                # composto vero ("three-" + "phase"): tengo il trattino
            else:
                out = out[:-1] + t           # pezzi di parola ("megastruc-" + "tures"): li unisco
        else:
            out = (out + " " + t) if out else t
    return out


# ------------------------------------------------------------------ paragrafi
def margini_pagina(blocchi):
    """Margini sinistri delle colonne: dalla mediana delle righe (esclusa la prima) dei blocchi lunghi."""
    m = []
    for b in blocchi:
        if len(b["righe"]) >= 3:
            m.append(statistics.median(r["x0"] for r in b["righe"][1:]))
    return m


SOGLIA_RIENTRO = 5.5  # punti: una riga spostata a destra di almeno cosi' rispetto alla vicina inizia un paragrafo


def dividi_blocco(b, margini):
    """Divide un blocco in segmenti (paragrafi) usando il rientro.
    Il rientro si misura rispetto alla riga vicina (non a un margine fisso): le pagine
    scansionate sono leggermente storte. Restituisce [(testo, rientrato_all_inizio)]."""
    righe = b["righe"]
    if len(righe) >= 2:
        primo_rientrato = righe[0]["x0"] - righe[1]["x0"] > SOGLIA_RIENTRO
    else:
        # blocco di una sola riga: confronto con il margine delle colonne della pagina
        candidati = [m for m in margini if m <= righe[0]["x0"] + 3]
        primo_rientrato = bool(candidati) and righe[0]["x0"] - max(candidati) > SOGLIA_RIENTRO
    gruppi, corrente = [], []
    for i, r in enumerate(righe):
        if i > 0 and r["x0"] - righe[i - 1]["x0"] > SOGLIA_RIENTRO and corrente:
            gruppi.append(corrente)
            corrente = []
        corrente.append(r["t"])
    gruppi.append(corrente)
    return [(unisci_righe(g), primo_rientrato if k == 0 else True) for k, g in enumerate(gruppi)]


def sembra_sottotitolo(testo, n_righe):
    """Sottotitolo vero: una sola riga, corto, senza punto finale e con le parole importanti maiuscole
    ("Sitting Heights", "In Praise of Odds and Ends"). Un frammento di frase in minuscolo NON lo e'."""
    if n_righe != 1 or not (3 <= len(testo) < 60) or testo.endswith(FINE_FRASE):
        return False
    parole = testo.split()
    if len(parole) > 6 or not testo[0].isupper() or not any(c.islower() for c in testo):
        return False
    return all(w[0].isupper() for w in parole if len(w) > 3 and w[0].isalpha())


def costruisci_paragrafi(pagine_blocchi, rif_capitolo):
    """Mette in ordine i paragrafi del capitolo, riunendo quelli spezzati da colonna o pagina."""
    paragrafi = []  # {"t": testo, "sotto": bool}
    scartati = []
    for num_pagina, altezza, blocchi in pagine_blocchi:
        # dimensione tipica del testo: quella della pagina, ma solo se vicina a quella del capitolo
        # (una pagina fatta solo di didascalie non deve prendere la loro dimensione come "normale")
        rif = dimensione_testo_normale(blocchi)
        if rif is None or not (0.88 * rif_capitolo <= rif <= 1.12 * rif_capitolo):
            rif = rif_capitolo
        # prima scarto le singole righe di disturbo, poi ricostruisco i blocchi
        puliti = []
        for b in blocchi:
            buone = []
            x0_tipico = statistics.median(r["x0"] for r in b["righe"])
            lungo = len(b["testo"]) >= 60
            for r in b["righe"]:
                m = motivo_scarto_riga(r, rif, x0_tipico, lungo)
                if m:
                    scartati.append((num_pagina, m, r["t"][:80]))
                else:
                    buone.append(r)
            if buone:
                puliti.append(crea_blocco(buone, b["y0"], b["y1"]) if len(buone) != len(b["righe"]) else b)
        blocchi = puliti
        margini = margini_pagina(blocchi)
        for b in blocchi:
            motivo = motivo_scarto(b, altezza, rif)
            if motivo:
                scartati.append((num_pagina, motivo, b["testo"][:80]))
                continue
            segmenti = dividi_blocco(b, margini)
            for k, (testo, rientrato) in enumerate(segmenti):
                if sembra_sottotitolo(testo, len(b["righe"])) and len(segmenti) == 1:
                    paragrafi.append({"t": testo, "sotto": True})
                    continue
                precedente = paragrafi[-1] if paragrafi else None
                # un paragrafo non finisce con un trattino: se succede, il seguito e' nel blocco dopo
                continuazione = bool(
                    precedente and not precedente["sotto"] and (
                        (precedente["t"].endswith("-") and testo[:1].islower())
                        # un paragrafo nuovo non comincia mai in minuscolo: e' il seguito di quello prima
                        # (vale anche nelle liste, dove le righe di continuazione sono rientrate)
                        or (testo[:1].islower() and not precedente["t"].endswith(FINE_FRASE))
                        or (k == 0 and not rientrato and not precedente["t"].endswith(FINE_FRASE))
                    )
                )
                if continuazione:
                    precedente["t"] = unisci_righe([precedente["t"], testo])
                else:
                    paragrafi.append({"t": testo, "sotto": False})
    return paragrafi, scartati


# ------------------------------------------------------------------ pulizia finale
LIGATURE = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
# errori tipici del riconoscimento automatico (cifra '1' al posto di 'i'/'l')
CORREZIONI = [
    (r"\b1f\b", "if"), (r"\b1n\b", "in"), (r"\b1t\b", "it"), (r"\b1s\b", "is"),
    (r"\bI1\b", "It"), (r"\btbe\b", "the"), (r"\bwbich\b", "which"),
]


def pulisci(testo, correzioni_libro=None):
    for a, b in LIGATURE.items():
        testo = testo.replace(a, b)
    for pattern, sost in CORREZIONI:
        testo = re.sub(pattern, sost, testo)
    # "I" letta come apostrofo: "’'ve" -> "I’ve"
    testo = re.sub(r"(?<![A-Za-z])[’']['’](ve|m|ll|d)\b", r"I’\1", testo)
    # parentesi quadre dovute al riconoscimento: le trasformo in tonde
    testo = testo.replace("[", "(").replace("]", ")")
    # correzioni specifiche del libro (elenco nel file di configurazione)
    for sbagliata, giusta in (correzioni_libro or {}).items():
        testo = re.sub(rf"(?<!\w){re.escape(sbagliata)}(?!\w)", giusta, testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    testo = re.sub(r"\s+([,.;:!?])", r"\1", testo)
    return testo


def slug(testo):
    return re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")


# ------------------------------------------------------------------ programma principale
def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    solo = {int(x) for x in sys.argv[2:]}
    doc = pymupdf.open(config["pdf"])
    uscita = RADICE / "output" / config["id"]
    (uscita / "testo").mkdir(parents=True, exist_ok=True)
    rapporto_scarti, rapporto_rev = [], []
    progressivo = 0

    for cap in config["capitoli"]:
        if not cap.get("includi", True):
            continue
        progressivo += 1
        if solo and cap["n"] not in solo:
            continue
        a, b = cap["pagine"]
        pagine = [(n, doc[n - 1].rect.height, leggi_blocchi(doc[n - 1])) for n in range(a, b + 1)]
        tutte = [dimensione_testo_normale(bl) for _, _, bl in pagine]
        tutte = [x for x in tutte if x]
        rif_cap = statistics.median(tutte) if tutte else 9.5

        paragrafi, scartati = costruisci_paragrafi(pagine, rif_cap)
        testi = [pulisci(p["t"], config.get("correzioni")) for p in paragrafi]

        etichetta = f"{progressivo:02d}-{slug(cap['titolo'])}"
        righe_md = [f"# {cap['titolo']}", ""]
        for p, t in zip(paragrafi, testi):
            righe_md.append(("## " if p["sotto"] else "") + t)
            righe_md.append("")
        (uscita / "testo" / f"{etichetta}.md").write_text("\n".join(righe_md), encoding="utf-8")

        parole = sum(len(t.split()) for t in testi)
        print(f"{etichetta:50} pagine {a}-{b}  paragrafi {len(paragrafi):3}  parole {parole:5}  scartati {len(scartati)}")

        rapporto_scarti.append(f"\n=== {etichetta} ===")
        rapporto_scarti += [f"  p.{n:>3} [{m}] {t}" for n, m, t in scartati]

        # parole sconosciute al dizionario: possibili errori del riconoscimento (OCR)
        tutto = " ".join(testi)
        # le parole con apostrofo (don't, Whyte's...) le salto: il dizionario non le gestisce bene
        senza_apostrofi = re.sub(r"[A-Za-z]*[’'][A-Za-z]+", " ", tutto)
        sconosciute = Counter(
            w for w in re.findall(r"[A-Za-z]{3,}", senza_apostrofi)
            if not dizionario.known([w.lower()])
        )
        sospette = sorted((w, c) for w, c in sconosciute.items() if c <= 2 and not w[0].isupper())
        nomi = sorted((w, c) for w, c in sconosciute.items() if w[0].isupper())
        rapporto_rev.append(f"\n=== {etichetta} ===")
        rapporto_rev.append("  Parole minuscole sconosciute (possibili errori): " + ", ".join(f"{w}({c})" for w, c in sospette))
        rapporto_rev.append("  Nomi propri / maiuscole sconosciute: " + ", ".join(f"{w}({c})" for w, c in nomi))

    (uscita / "scartati.txt").write_text("\n".join(rapporto_scarti), encoding="utf-8")
    (uscita / "revisione.txt").write_text("\n".join(rapporto_rev), encoding="utf-8")
    print(f"\nFatto. File in: {uscita}")


if __name__ == "__main__":
    main()
