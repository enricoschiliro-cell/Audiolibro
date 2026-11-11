"""Strumenti comuni per trasformare le frasi di un capitolo in audio.

- legge il capitolo diviso in frasi (output/<libro>/frasi/*.json);
- sintetizza ogni frase con un motore di voce (Kokoro, Piper...);
- unisce le frasi inserendo le PAUSE decise da noi: cosi' sappiamo con precisione
  quando inizia ogni frase (serve al testo che scorre in sincrono);
- salva MP3 leggeri con ffmpeg.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

RADICE = Path(__file__).resolve().parent.parent

# Pause in secondi (le regole di ritmo del libro)
PAUSA_FRASE = 0.45        # tra una frase e la successiva dentro lo stesso paragrafo
PAUSA_PARAGRAFO = 1.00    # dopo l'ultima frase di un paragrafo
PAUSA_SOTTOTITOLO = 0.90  # dopo un sottotitolo
PAUSA_ANNUNCIO = 1.30     # dopo "Chapter four. Food."
PAUSA_FINE = 1.50         # in fondo al capitolo


def trova_ffmpeg():
    """ffmpeg installato con winget: lo cerco nel PATH e, se non c'e', nella cartella dei collegamenti."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    alt = Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"
    if alt.exists():
        return str(alt)
    raise FileNotFoundError("ffmpeg non trovato")


def carica_capitolo(libro, etichetta):
    """Restituisce il capitolo come lista di segmenti: (tipo, testo, pausa_dopo_in_secondi)."""
    dati = json.loads((RADICE / "output" / libro / "frasi" / f"{etichetta}.json").read_text(encoding="utf-8"))
    segmenti = [("annuncio", dati["annuncio"], PAUSA_ANNUNCIO)]
    for b in dati["blocchi"]:
        if b["tipo"] == "sottotitolo":
            segmenti.append(("sottotitolo", b["frasi"][0], PAUSA_SOTTOTITOLO))
            continue
        for i, f in enumerate(b["frasi"]):
            ultima = i == len(b["frasi"]) - 1
            segmenti.append(("frase", f, PAUSA_PARAGRAFO if ultima else PAUSA_FRASE))
    segmenti[-1] = (segmenti[-1][0], segmenti[-1][1], PAUSA_FINE)
    return dati, segmenti


def inizio_capitolo(segmenti, parole_max):
    """Prende l'inizio del capitolo (per le prove di voce), fermandosi a fine frase."""
    out, conta = [], 0
    for tipo, testo, pausa in segmenti:
        out.append((tipo, testo, pausa))
        conta += len(testo.split())
        if conta >= parole_max and tipo == "frase":
            break
    return out


def assembla(segmenti, sintetizza, sr):
    """Sintetizza ogni segmento e li unisce con le pause. Restituisce (audio, tempi).
    tempi = lista di dizionari con inizio e fine (in secondi) di ogni segmento."""
    pezzi, tempi, t = [], [], 0.0
    for tipo, testo, pausa in segmenti:
        audio = np.asarray(sintetizza(testo), dtype=np.float32).reshape(-1)
        dur = len(audio) / sr
        tempi.append({"tipo": tipo, "testo": testo, "inizio": round(t, 3), "fine": round(t + dur, 3)})
        silenzio = np.zeros(int(sr * pausa), dtype=np.float32)
        pezzi += [audio, silenzio]
        t += dur + pausa
    return np.concatenate(pezzi), tempi


def salva_mp3(audio, sr, percorso, kbps=64):
    """Scrive un WAV temporaneo e lo converte in MP3 mono con ffmpeg."""
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    wav = percorso.with_suffix(".tmp.wav")
    sf.write(str(wav), audio, sr)
    subprocess.run(
        [trova_ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1",
         "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(percorso)],
        check=True,
    )
    wav.unlink()


# ------------------------------------------------------------------ motori di voce
class Piper:
    """Piper (veloce e leggero, gira anche senza scheda video). nome = ad es. 'en_US-ryan-high'.
    I file della voce stanno in modelli/piper/ (scaricati con: python -m piper.download_voices)."""

    def __init__(self, nome, velocita=1.0):
        from piper import PiperVoice, SynthesisConfig
        self.voce = PiperVoice.load(RADICE / "modelli" / "piper" / f"{nome}.onnx")
        self.sr = self.voce.config.sample_rate
        # length_scale piu' alto = parlato piu' lento
        self.cfg = SynthesisConfig(length_scale=1.0 / velocita)

    def __call__(self, testo):
        pezzi = [c.audio_float_array for c in self.voce.synthesize(testo, self.cfg)]
        return np.concatenate(pezzi) if pezzi else np.zeros(1, dtype=np.float32)


class Kokoro:
    """Kokoro (82 milioni di parametri, licenza Apache 2.0). lang: 'a' americano, 'b' britannico."""
    sr = 24000

    def __init__(self, lang, voce, velocita=1.0, dispositivo=None):
        from kokoro import KPipeline
        self.pipe = KPipeline(lang_code=lang, device=dispositivo)
        self.voce = voce
        self.velocita = velocita

    def __call__(self, testo):
        pezzi = [np.asarray(a) for _, _, a in self.pipe(testo, voice=self.voce, speed=self.velocita)]
        return np.concatenate(pezzi) if pezzi else np.zeros(1, dtype=np.float32)
