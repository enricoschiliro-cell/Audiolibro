"""TRADUZIONE AUTOMATICA INGLESE -> ITALIANO di un libro gia' diviso in frasi, tutta sul tuo PC.

Uso:
  python traduci_libro.py <libro> <libro_it> [capitolo ...] [--cuda] [--rigenera] [--prova]

Esempio (dalla cartella pipeline, con l'ambiente .venv):
  ..\\.venv\\Scripts\\python.exe traduci_libro.py whyte whyte-it 07-food
  (senza nomi di capitolo traduce tutti i capitoli trovati in output/whyte/frasi/)

Cosa fa:
  - legge output/<libro>/frasi/<capitolo>.json (stesso formato prodotto da dividi_frasi.py);
  - traduce frase per frase con il modello open source Helsinki-NLP/opus-mt-tc-big-en-it
    (licenza CC-BY-4.0; modello scaricato una volta sola da Hugging Face e poi usato in locale);
  - scrive output/<libro_it>/frasi/<capitolo>.json con la STESSA struttura, quindi il generatore di capitolo
    lo legge senza modifiche:  genera_capitolo.py <libro_it> <capitolo> xtts:it:Filip_Traverse
  - scrive anche output/<libro_it>/confronto/<capitolo>.txt (inglese e italiano a coppie, con "!" sulle frasi
    sospette) per controllare la traduzione a occhio.
  - i titoli dei capitoli vengono da pipeline/libri/<libro_it>.json (scritti a mano); l'annuncio diventa
    "Capitolo quattro. Il cibo." (per Foreword/Preface/Introduction solo il titolo).

Limiti da conoscere (e' una traduzione automatica, non umana):
  - ogni frase e' tradotta da sola: il modello non vede le frasi vicine, quindi pronomi e termini ricorrenti
    possono risultare incoerenti (es. 'plaza', 'ledge'); e' un limite del metodo, non un difetto del programma;
  - lo stile sara' corretto ma non letterario; possono esserci errori di senso: si controlla su un capitolo prima;
  - le unita' di misura non vengono convertite (feet e inches restano tali);
  - gli errori di riconoscimento del testo (OCR) rimasti nell'inglese si portano dietro nella traduzione.

Uso PERSONALE: la traduzione resta nella cartella output/ del progetto (fuori da Git, da Drive e da OneDrive).
Non va pubblicata ne' condivisa.

Per impostazione predefinita gira sul processore (piu' lento ma senza rischi per la scheda video).
--cuda usa la scheda: da evitare mentre gira XTTS. --prova usa un finto traduttore (scrive "[IT] " davanti
a ogni frase) per controllare solo la struttura dei file, senza modello.
"""
import json
import re
import sys
import time
from pathlib import Path

from num2words import num2words

RADICE = Path(__file__).resolve().parent.parent
MODELLO = "Helsinki-NLP/opus-mt-tc-big-en-it"
FRASI_PER_LOTTO = 16
# Rapporto tra lunghezza italiana e inglese: fuori da questi limiti la frase e' sospetta (scelta mia, da tarare;
# di solito l'italiano e' un 10-25% piu' lungo dell'inglese).
RAPPORTO_MIN, RAPPORTO_MAX = 0.7, 1.8

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class Traduttore:
    """Modello Opus-MT (MarianMT). Carica il modello una volta sola e traduce liste di frasi."""

    def __init__(self, cuda):
        import os
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        import torch
        from transformers import MarianMTModel, MarianTokenizer
        self.torch = torch
        self.dispositivo = "cuda" if cuda else "cpu"
        print(f"Carico il modello {MODELLO} su {self.dispositivo}...", flush=True)
        self.tok = MarianTokenizer.from_pretrained(MODELLO)
        self.modello = MarianMTModel.from_pretrained(MODELLO).to(self.dispositivo).eval()

    def __call__(self, frasi):
        """Lista di frasi inglesi -> lista di frasi italiane, nello stesso ordine.
        Le frasi si raggruppano per lunghezza (meno spazio sprecato), poi si rimettono in ordine."""
        ordine = sorted(range(len(frasi)), key=lambda i: len(frasi[i]))
        risultati = [None] * len(frasi)
        for k in range(0, len(ordine), FRASI_PER_LOTTO):
            indici = ordine[k:k + FRASI_PER_LOTTO]
            lotto = self.tok([frasi[i] for i in indici], return_tensors="pt", padding=True,
                             truncation=True, max_length=512).to(self.dispositivo)
            with self.torch.inference_mode():
                uscita = self.modello.generate(**lotto, num_beams=4, max_new_tokens=512)
            for i, testo in zip(indici, self.tok.batch_decode(uscita, skip_special_tokens=True)):
                risultati[i] = testo.strip()
            print(f"  tradotte {min(k + FRASI_PER_LOTTO, len(ordine))}/{len(ordine)}", flush=True)
        return risultati


def traduttore_finto(frasi):
    return ["[IT] " + f for f in frasi]


def motivo_sospetto(originale, tradotta):
    """None se la traduzione sembra a posto, altrimenti il motivo del sospetto."""
    if not tradotta:
        return "traduzione vuota"
    parole = originale.split()
    if len(parole) > 3 and tradotta.strip().lower() == originale.strip().lower():
        return "uguale all'originale (non tradotta?)"
    if re.search(r"\b(\w+)(\s+\1\b){3,}", tradotta, flags=re.IGNORECASE):
        return "parola ripetuta (il modello si e' incantato?)"
    rapporto = len(tradotta) / max(1, len(originale))
    if len(originale) > 25 and not (RAPPORTO_MIN <= rapporto <= RAPPORTO_MAX):
        return f"lunghezza strana (italiano {rapporto:.1f} volte l'inglese)"
    return None


def carica_titoli(libro_it):
    f = RADICE / "pipeline" / "libri" / f"{libro_it}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8")).get("titoli", {})
    return {}


def traduci_capitolo(traduci, libro, libro_it, etichetta, titoli, rigenera):
    origine = RADICE / "output" / libro / "frasi" / f"{etichetta}.json"
    uscita = RADICE / "output" / libro_it / "frasi" / f"{etichetta}.json"
    if uscita.exists() and not rigenera:
        print(f"{etichetta}: gia' tradotto, salto (usa --rigenera per rifarlo)", flush=True)
        return
    dati = json.loads(origine.read_text(encoding="utf-8"))
    inglesi = [f for b in dati["blocchi"] for f in b["frasi"]]
    print(f"{etichetta}: {len(inglesi)} frasi", flush=True)
    t0 = time.time()
    italiane = traduci(inglesi)

    # titolo e annuncio
    titolo_it = titoli.get(etichetta)
    if not titolo_it:
        titolo_it = traduci([dati["titolo"]])[0].rstrip(".")
        print(f"  titolo non scritto a mano, tradotto dalla macchina: '{titolo_it}' (controllalo)", flush=True)
    if dati["annuncio"].startswith("Chapter"):
        annuncio = f"Capitolo {num2words(dati['capitolo'], lang='it')}. {titolo_it}."
    else:
        annuncio = f"{titolo_it}."          # Foreword, Preface, Introduction: solo il titolo

    # stessa struttura dell'originale
    it = iter(italiane)
    blocchi = [{"tipo": b["tipo"], "frasi": [next(it) for _ in b["frasi"]]} for b in dati["blocchi"]]
    risultato = {"capitolo": dati["capitolo"], "titolo": titolo_it, "annuncio": annuncio,
                 "blocchi": blocchi, "traduzione": MODELLO}
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(json.dumps(risultato, ensure_ascii=False, indent=1), encoding="utf-8")

    # file di confronto per il controllo a occhio
    righe, sospette = [], 0
    for n, (en, it_) in enumerate(zip(inglesi, italiane), 1):
        motivo = motivo_sospetto(en, it_)
        marca = "!" if motivo else " "
        sospette += bool(motivo)
        righe.append(f"{marca} {n:4}  EN: {en}\n       IT: {it_}" + (f"\n       ({motivo})" if motivo else "") + "\n")
    confronto = RADICE / "output" / libro_it / "confronto" / f"{etichetta}.txt"
    confronto.parent.mkdir(parents=True, exist_ok=True)
    confronto.write_text("\n".join(righe), encoding="utf-8")
    print(f"  fatto in {time.time() - t0:.0f} s: {uscita.relative_to(RADICE)}  "
          f"({sospette} frasi sospette, vedi {confronto.relative_to(RADICE)})", flush=True)


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    flag = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(argv) < 2:
        sys.exit(__doc__)
    libro, libro_it, capitoli = argv[0], argv[1], argv[2:]
    if not capitoli:
        capitoli = sorted(p.stem for p in (RADICE / "output" / libro / "frasi").glob("*.json") if not p.stem.startswith("_"))
    titoli = carica_titoli(libro_it)
    traduci = traduttore_finto if "--prova" in flag else Traduttore("--cuda" in flag)
    for etichetta in capitoli:
        traduci_capitolo(traduci, libro, libro_it, etichetta, titoli, "--rigenera" in flag)


if __name__ == "__main__":
    main()
