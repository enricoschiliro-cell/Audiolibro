"""Strumenti comuni per trasformare le frasi di un capitolo in audio.

- legge il capitolo diviso in frasi (output/<libro>/frasi/*.json);
- sintetizza ogni frase con un motore di voce (Kokoro, Piper...);
- unisce le frasi inserendo le PAUSE decise da noi: cosi' sappiamo con precisione
  quando inizia ogni frase (serve al testo che scorre in sincrono);
- salva MP3 leggeri con ffmpeg.
"""
import json
import re
import shutil
import subprocess
import sys
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
PAUSA_SPEZZATA = 0.15     # dentro una frase troppo lunga per XTTS, tra le due parti in cui la dividiamo (scelta mia, da tarare ascoltando)

CODICE_OCCUPATO = 75      # codice d'uscita: un altro processo XTTS e' gia' in esecuzione


def trova_ffmpeg():
    """ffmpeg installato con winget: lo cerco nel PATH e, se non c'e', nella cartella dei collegamenti."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    alt = Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"
    if alt.exists():
        return str(alt)
    raise FileNotFoundError("ffmpeg non trovato")


def attendi_scheda_fresca(max_c=82, ok_c=72):
    """Protezione per la scheda video: se supera max_c gradi aspetta che scenda sotto ok_c.
    (Se nvidia-smi non risponde, non fa nulla.)"""
    import time
    def temperatura():
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            return int(out.splitlines()[0])
        except Exception:
            return None
    t = temperatura()
    if t is not None and t >= max_c:
        print(f"  scheda a {t} gradi: aspetto che si raffreddi...", flush=True)
        while t is not None and t > ok_c:
            time.sleep(20)
            t = temperatura()
        print(f"  scheda a {t} gradi, riprendo", flush=True)


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


def unisci(segmenti, audio_per_segmento, sr):
    """Unisce gli audio GIA' PRONTI (uno per segmento, nello stesso ordine) inserendo le pause.
    Restituisce (audio, tempi). tempi = un dizionario per segmento con inizio e fine (in secondi)
    e la pausa che segue (da questa si capisce dove finisce un paragrafo).
    I tempi si calcolano sui campioni realmente scritti, cosi' non si accumulano errori di arrotondamento."""
    pezzi, tempi, campioni = [], [], 0
    for (tipo, testo, pausa), audio in zip(segmenti, audio_per_segmento):
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        silenzio = np.zeros(int(round(sr * pausa)), dtype=np.float32)
        tempi.append({"tipo": tipo, "testo": testo,
                      "inizio": round(campioni / sr, 3), "fine": round((campioni + len(audio)) / sr, 3),
                      "pausa": pausa})
        pezzi += [audio, silenzio]
        campioni += len(audio) + len(silenzio)
    return np.concatenate(pezzi), tempi


def assembla(segmenti, sintetizza, sr):
    """Sintetizza ogni segmento e li unisce con le pause. Restituisce (audio, tempi)."""
    return unisci(segmenti, [sintetizza(testo) for _, testo, _ in segmenti], sr)


def spezza_frase(testo, limite):
    """Se il testo supera 'limite' caratteri lo divide in parti piu' corte, tagliando dove si respira:
    prima dopo ; o :, poi dopo una virgola (solo se seguita da spazio, per non rompere '1,000'),
    in ultima scelta sullo spazio piu' vicino alla meta'. Restituisce la lista delle parti."""
    testo = testo.strip()
    if len(testo) <= limite:
        return [testo]
    meta = len(testo) / 2
    n = len(testo)
    taglio = None
    for separatori in ((";", ":"), (",",)):
        tagli = [i + 1 for i, c in enumerate(testo)
                 if c in separatori and testo[i + 1:i + 2] == " " and 20 <= i + 1 <= n - 20]
        if tagli:
            taglio = min(tagli, key=lambda p: abs(p - meta))
            break
    if taglio is None:
        spazi = [i for i, c in enumerate(testo) if c == " " and 20 <= i <= n - 20]
        taglio = min(spazi, key=lambda p: abs(p - meta)) if spazi else limite
    return spezza_frase(testo[:taglio], limite) + spezza_frase(testo[taglio:], limite)


_lock_xtts = None  # tiene aperto il file di blocco finche' il processo e' vivo


def blocca_xtts():
    """Impedisce di avere DUE processi XTTS insieme sulla scheda (due insieme hanno causato un blue screen).
    Il blocco sta su un file e lo toglie da solo il sistema quando il processo finisce o si chiude male,
    quindi non restano blocchi 'orfani'. Se un altro XTTS e' attivo, stampa un avviso ed esce con CODICE_OCCUPATO."""
    global _lock_xtts
    percorso = RADICE / "modelli" / ".xtts.lock"
    percorso.parent.mkdir(parents=True, exist_ok=True)
    f = open(percorso, "a+b")
    try:
        try:
            import msvcrt  # Windows
        except ImportError:
            msvcrt = None
        if msvcrt:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        print("ERRORE: un altro processo XTTS e' gia' in esecuzione (prove di voce o generazione di un capitolo).\n"
              "Due processi insieme sulla scheda hanno causato un blue screen: aspetta che il primo finisca.",
              file=sys.stderr, flush=True)
        sys.exit(CODICE_OCCUPATO)
    _lock_xtts = f


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


# (Kokoro e' stato provato e scartato: voci italiane non convincenti. Eliminato.)


# Lunghezza massima (in caratteri) che XTTS accetta per un testo senza rischiare l'audio troncato.
# Valori letti dal tokenizer installato (coqui-tts): inglese 250, italiano 213. Per altre lingue uso 200 (prudente).
LIMITI_XTTS = {"en": 250, "it": 213}
# Il testo viene "espanso" (numeri, abbreviazioni...) prima del controllo del limite: tengo un margine.
MARGINE_LIMITE = 0.9

# Abbreviazioni italiane che il tokenizer di XTTS espande in parola intera SOLO se seguite dal punto
# (lista letta in TTS/tts/layers/xtts/tokenizer.py): se la frase finisce cosi' il punto va lasciato.
ABBREVIAZIONI_XTTS_IT = ("sig", "dr", "st", "co", "jr", "ltd")


def togli_punto_finale(testo):
    """Toglie il punto finale dal testo che si da' a XTTS.
    Perche': XTTS spesso pronuncia "punto" (o un suono simile) dopo l'ultima parola se il testo finisce con '.'.
    Misurato con Whisper su Food (12/11/2026, una sola prova): con il punto finale 13 volte "punto" in 12 frasi
    su 65, senza punto finale 0 su 65. La pausa tra le frasi non cambia: la decide unisci().
    Lascia intatti: '?', '!', ':' (non provati), i puntini di sospensione e le abbreviazioni che XTTS espande
    solo con il punto. Se dopo il punto c'e' una chiusura (virgolette, parentesi) la tiene.
    Provato solo in italiano: per le altre lingue non va usata (vedi Xtts.__call__)."""
    m = re.search(r"\.([\"”»’')\]]*)$", testo)
    if not m:
        return testo
    prima = testo[:m.start()].rstrip()
    if not prima or prima.endswith("."):
        return testo
    parole = re.findall(r"[^\W\d_]+", prima)
    if parole and parole[-1].lower() in ABBREVIAZIONI_XTTS_IT:
        return testo
    return prima + m.group(1)


class Xtts:
    """XTTS-v2 di Coqui. Gira nell'ambiente .venv-xtts.
    LICENZA DEL MODELLO (CPML): solo uso non commerciale, anche per l'audio prodotto.
    Richiede la variabile d'ambiente COQUI_TOS_AGREED=1 (accettazione della licenza).
    speaker: una delle 58 voci di serie (es. 'Damien Black'); in alternativa un file audio di riferimento.
    Le frasi piu' lunghe del limite di XTTS vengono divise alla punteggiatura (vedi spezza_frase).
    Un solo processo XTTS alla volta: lo garantisce blocca_xtts()."""
    sr = 24000

    def __init__(self, lingua, speaker):
        blocca_xtts()
        from TTS.api import TTS
        self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
        self.lingua, self.speaker = lingua, speaker

    def limite(self):
        return int(LIMITI_XTTS.get(self.lingua, 200) * MARGINE_LIMITE)

    def __call__(self, testo):
        pezzi = []
        parti = spezza_frase(testo, self.limite())
        for i, parte in enumerate(parti):
            if i:
                pezzi.append(np.zeros(int(self.sr * PAUSA_SPEZZATA), dtype=np.float32))
            if self.lingua == "it":
                # Evita il "punto" detto da XTTS (solo italiano, provato). La libreria divide da sola la parte in frasi
                # (pysbd) e lascia il '.' in fondo a OGNI pezzo, anche a quelli interni (es. "Capitolo sette. Il cibo.",
                # frasi tra parentesi con due frasi dentro). Faccio io la stessa divisione, tolgo il punto finale di ogni
                # pezzo e chiamo XTTS pezzo per pezzo senza lasciargli dividere ancora: il silenzio dopo ogni pezzo
                # (PAD_SILENCE_SAMPLES) lo aggiunge comunque la libreria, quindi le pause restano quelle di prima.
                if i == len(parti) - 1:
                    parte = togli_punto_finale(parte)   # prima di dividere: cosi' ".)" non lascia un pezzo con la sola ")"
                sotto = [s.strip() for s in self.tts.synthesizer.split_into_sentences(parte, self.lingua)]
                sotto = [s for s in sotto if re.search(r"\w", s)]   # scarto i pezzi senza lettere/cifre (solo punteggiatura)
                for s in sotto:
                    wav = self.tts.tts(text=togli_punto_finale(s), speaker=self.speaker, language=self.lingua,
                                       split_sentences=False)
                    pezzi.append(np.asarray(wav, dtype=np.float32).reshape(-1))
            else:
                wav = self.tts.tts(text=parte, speaker=self.speaker, language=self.lingua)
                pezzi.append(np.asarray(wav, dtype=np.float32).reshape(-1))
        return np.concatenate(pezzi)


# (Chatterbox e' stato provato e scartato: lento e voce non convincente. Eliminato.)
