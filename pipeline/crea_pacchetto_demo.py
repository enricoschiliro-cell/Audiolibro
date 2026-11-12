"""Crea un PACCHETTO DIMOSTRATIVO per provare l'app: nessun libro, solo "bip".

Ha lo stesso formato dei pacchetti veri (vedi FORMATO_PACCHETTO.md, versione 1): manifest.json con le firme SHA-256,
capitoli/<id>.mp3 (MP3 mono 24 kHz 64 kbit/s, come quelli veri) e capitoli/<id>.json con i tempi di ogni frase, cover.jpg.
Non c'e' nessun diritto d'autore: l'audio e' un tono sinusoidale (ogni frase ha un'altezza diversa, cosi' si sente
quando cambia) e il testo e' scritto da noi. Per questo il file puo' stare anche dentro docs/ (pubblicato su GitHub Pages).

Uso (basta il Python di sistema o .venv-xtts; serve ffmpeg):
    python crea_pacchetto_demo.py                       # scrive docs/app/lab/pacchetto-demo.dat
    python crea_pacchetto_demo.py --uscita C:\\percorso\\prova.zip --difetto versione2
Difetti per provare i rifiuti dell'app (da NON mettere in docs/):
    versione2   il manifest dice versione 2 (l'app deve rifiutarlo: "aggiorna l'app")
    firma       la firma SHA-256 dell'audio di un capitolo e' sbagliata (l'app deve fermarsi con un messaggio chiaro)
    manca       un capitolo e' nel manifest ma il suo MP3 non e' nello zip
    formato     il manifest ha un altro nome di formato
L'estensione del file di uscita per il pacchetto buono e' .dat (non .zip): il .gitignore ignora *.zip, e cosi' un file
messo in docs/ non puo' venire scambiato per un libro vero.
"""
import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import zipfile
from datetime import datetime
from pathlib import Path

VERSIONE_FORMATO = 1
FREQ_CAMPIONAMENTO = 24000  # come gli MP3 veri (MPEG-2 Layer III, 24 kHz, mono)

# Pause previste dal formato (secondi di silenzio DOPO il segmento)
PAUSA_FRASE = 0.45        # tra frasi dello stesso paragrafo
PAUSA_PARAGRAFO = 1.0     # dopo l'ultima frase di un paragrafo
PAUSA_SOTTOTITOLO = 0.9
PAUSA_ANNUNCIO = 1.3
PAUSA_FINALE = 1.5        # in fondo al capitolo

# Durate dei "bip" (secondi), ripetute a ciclo
DURATE = [2.6, 3.4, 2.9, 3.8, 2.2, 3.1, 3.5, 2.7, 3.0]

# Tre capitoli: id, numero (0 = senza numero, come una prefazione), titolo, tono di base (Hz), paragrafi (frasi per paragrafo)
CAPITOLI = [
    {"id": "01-prefazione-demo", "numero": 0, "titolo": "Prefazione di prova", "base": 330, "paragrafi": [3, 3, 3], "sottotitolo": None},
    {"id": "02-bip-gravi", "numero": 1, "titolo": "I bip gravi", "base": 220, "paragrafi": [3, 3, 3], "sottotitolo": "Un sottotitolo di prova"},
    {"id": "03-bip-acuti", "numero": 2, "titolo": "I bip acuti", "base": 440, "paragrafi": [3, 3, 3], "sottotitolo": None},
]


def trova_ffmpeg():
    percorso = shutil.which("ffmpeg")
    if percorso:
        return percorso
    alternativo = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if alternativo.exists():
        return str(alternativo)
    sys.exit("Non trovo ffmpeg")


def ffprobe_di(ffmpeg):
    p = Path(ffmpeg)
    candidato = p.with_name("ffprobe" + p.suffix)
    return str(candidato if candidato.exists() else (shutil.which("ffprobe") or "ffprobe"))


def sha256_byte(dati):
    return hashlib.sha256(dati).hexdigest()


class Traccia:
    """Costruisce l'audio di un capitolo (campioni a 16 bit) e l'elenco dei segmenti con i loro tempi esatti."""

    def __init__(self):
        self.campioni = []
        self.segmenti = []

    def tempo(self):
        return len(self.campioni) / FREQ_CAMPIONAMENTO

    def silenzio(self, secondi):
        self.campioni.extend([0] * round(secondi * FREQ_CAMPIONAMENTO))

    def bip(self, secondi, frequenza):
        n = round(secondi * FREQ_CAMPIONAMENTO)
        rampa = round(0.03 * FREQ_CAMPIONAMENTO)  # 30 ms di entrata e uscita: niente "click"
        for i in range(n):
            inviluppo = min(1.0, i / rampa, (n - 1 - i) / rampa)
            self.campioni.append(int(9000 * inviluppo * math.sin(2 * math.pi * frequenza * i / FREQ_CAMPIONAMENTO)))

    def segmento(self, tipo, testo, durata_bip, frequenza, pausa):
        inizio = self.tempo()
        self.bip(durata_bip, frequenza)
        fine = self.tempo()
        self.silenzio(pausa)
        self.segmenti.append({"tipo": tipo, "testo": testo, "inizio": round(inizio, 3), "fine": round(fine, 3), "pausa": pausa})

    def salva_wav(self, percorso):
        with wave.open(str(percorso), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(FREQ_CAMPIONAMENTO)
            w.writeframes(struct.pack("<%dh" % len(self.campioni), *self.campioni))


def costruisci_capitolo(c):
    t = Traccia()
    numero_frase = 0
    # Annuncio, come nei libri veri ("Capitolo uno. Titolo.")
    testo_annuncio = f"Capitolo {c['numero']}. {c['titolo']}." if c["numero"] else f"{c['titolo']}."
    t.segmento("annuncio", testo_annuncio, 1.8, c["base"] * 1.5, PAUSA_ANNUNCIO)
    if c["sottotitolo"]:
        t.segmento("sottotitolo", c["sottotitolo"], 1.2, c["base"] * 1.25, PAUSA_SOTTOTITOLO)
    for n_par, frasi in enumerate(c["paragrafi"], start=1):
        for k in range(frasi):
            numero_frase += 1
            durata = DURATE[(numero_frase - 1) % len(DURATE)]
            ultima_del_capitolo = n_par == len(c["paragrafi"]) and k == frasi - 1
            ultima_del_paragrafo = k == frasi - 1
            pausa = PAUSA_FINALE if ultima_del_capitolo else (PAUSA_PARAGRAFO if ultima_del_paragrafo else PAUSA_FRASE)
            secondi = f"{durata:.1f}".replace(".", ",")  # virgola decimale, come in italiano
            testo = f"Questa è la frase numero {numero_frase} del paragrafo {n_par}: un bip di {secondi} secondi."
            t.segmento("frase", testo, durata, c["base"] + 30 * numero_frase, pausa)
    return t


def codifica_mp3(ffmpeg, wav, mp3):
    r = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame",
                        "-b:a", "64k", "-ar", str(FREQ_CAMPIONAMENTO), "-ac", "1", str(mp3)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(mp3).exists():
        sys.exit("ffmpeg ha fallito (serve libmp3lame):\n" + r.stderr[-1000:])


def durata_mp3(ffmpeg, mp3):
    out = subprocess.run([ffprobe_di(ffmpeg), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(mp3)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def crea_copertina(ffmpeg, percorso):
    r = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x22403d:s=400x400",
                        "-frames:v", "1", "-update", "1", str(percorso)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(percorso).exists():
        sys.exit("Copertina non creata:\n" + r.stderr[-800:])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    radice = Path(__file__).resolve().parents[1]
    ap.add_argument("--uscita", default=str(radice / "docs" / "app" / "lab" / "pacchetto-demo.dat"))
    ap.add_argument("--difetto", choices=["versione2", "firma", "manca", "formato"], default=None)
    args = ap.parse_args()

    ffmpeg = trova_ffmpeg()
    uscita = Path(args.uscita)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    if args.difetto is None and uscita.suffix.lower() == ".zip":
        sys.exit("Il pacchetto buono deve avere estensione .dat (non .zip): vedi la spiegazione in cima al file.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        crea_copertina(ffmpeg, tmp / "cover.jpg")
        manifest = {
            "formato": "audiolibro-pacchetto", "versione": VERSIONE_FORMATO,
            "creato": datetime.now().isoformat(timespec="seconds"),
            "libro": {"id": "demo-bip", "titolo": "Libro di prova (bip)", "autore": "Audiolibro", "lingua": "it"},
            "voce": {"nome": "Bip", "motore": "sinusoide", "licenza": "nessuna"},
            "traduzione": "", "avviso": "Pacchetto dimostrativo: nessun libro, solo bip.",
            "copertina": "cover.jpg", "durata": 0.0, "capitoli": [],
        }
        elementi = []  # (nome nello zip, byte, compressione)
        durata_totale = 0.0
        for c in CAPITOLI:
            traccia = costruisci_capitolo(c)
            wav, mp3 = tmp / f"{c['id']}.wav", tmp / f"{c['id']}.mp3"
            traccia.salva_wav(wav)
            codifica_mp3(ffmpeg, wav, mp3)
            durata = durata_mp3(ffmpeg, mp3)
            durata_totale += durata
            dati_mp3 = mp3.read_bytes()
            tempi = {"versione": VERSIONE_FORMATO, "capitolo": c["id"], "numero": c["numero"], "titolo": c["titolo"],
                     "durata": durata, "segmenti": traccia.segmenti}
            dati_json = json.dumps(tempi, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            nome_mp3, nome_json = f"capitoli/{c['id']}.mp3", f"capitoli/{c['id']}.json"
            titolo_completo = f"Capitolo {c['numero']}: {c['titolo']}" if c["numero"] else c["titolo"]
            manifest["capitoli"].append({
                "id": c["id"], "numero": c["numero"], "titolo": c["titolo"], "titolo_completo": titolo_completo,
                "audio": nome_mp3, "tempi": nome_json, "durata": round(durata, 3),
                "frasi": sum(1 for s in traccia.segmenti if s["tipo"] in ("frase", "sottotitolo")),
                "byte_audio": len(dati_mp3), "sha256_audio": sha256_byte(dati_mp3),
                "byte_tempi": len(dati_json), "sha256_tempi": sha256_byte(dati_json)})
            elementi.append((nome_mp3, dati_mp3, zipfile.ZIP_STORED))
            elementi.append((nome_json, dati_json, zipfile.ZIP_DEFLATED))
            print(f"{c['id']}: {durata:.1f} s, {len(traccia.segmenti)} segmenti, MP3 {len(dati_mp3) / 1e3:.0f} kB")
        manifest["durata"] = round(durata_totale, 3)

        # Difetti voluti, solo per provare i rifiuti dell'app
        if args.difetto == "versione2":
            manifest["versione"] = 2
        elif args.difetto == "firma":
            f = manifest["capitoli"][1]["sha256_audio"]
            manifest["capitoli"][1]["sha256_audio"] = ("0" if f[0] != "0" else "1") + f[1:]
        elif args.difetto == "manca":
            elementi = [e for e in elementi if e[0] != manifest["capitoli"][2]["audio"]]
        elif args.difetto == "formato":
            manifest["formato"] = "altro-formato"

        with zipfile.ZipFile(uscita, "w") as z:
            for nome, dati, compressione in elementi:
                z.writestr(zipfile.ZipInfo(nome, date_time=datetime.now().timetuple()[:6]), dati, compress_type=compressione)
            z.writestr(zipfile.ZipInfo("cover.jpg", date_time=datetime.now().timetuple()[:6]), (tmp / "cover.jpg").read_bytes(),
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1), compress_type=zipfile.ZIP_DEFLATED)

    print(f"Scritto {uscita} ({uscita.stat().st_size / 1e6:.2f} MB), durata totale {durata_totale:.1f} s"
          + (f", difetto: {args.difetto}" if args.difetto else ""))


if __name__ == "__main__":
    main()
