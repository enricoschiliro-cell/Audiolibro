"""Controllo di qualita' con Whisper: trascrive ogni frase di un audio gia' prodotto e la confronta con il testo.

A cosa serve: XTTS ogni tanto dice parole IN PIU' che non sono nel testo (tipico: "punto" in fondo alla frase)
o ne salta qualcuna. Il controllo sulle pause di genera_capitolo.py non le vede: queste si trovano solo
ascoltando, e Whisper ascolta per noi. NON modifica niente: legge l'MP3 (o WAV) e il JSON dei tempi e scrive
un rapporto in output/<libro>/controlli/<nome>.json.

Uso (con l'ambiente .venv-xtts, dove ci sono torch e transformers):
    python -I controlla_whisper.py <libro> <nome-base-audio> [--cartella-audio PERCORSO] [--lingua italian]
    esempio: python -I controlla_whisper.py whyte-it-gemma 07-food__xtts-Filip_Traverse

Modello: modelli/whisper-large-v3-turbo (openai/whisper-large-v3-turbo, licenza MIT secondo la scheda del modello),
scaricato con il permesso dell'utente il 12/11/2026 e verificato con SHA-256. Funziona senza internet.
Usa la scheda video: prende lo stesso blocco di XTTS (un solo lavoro alla volta sulla scheda).

Limiti (da non dimenticare):
- Whisper puo' sbagliare: un nome proprio raro viene scritto in altro modo, un numero come cifre.
  Per questo le frasi di 1-2 parole non vengono giudicate e il rapporto dice sempre COSA e' diverso,
  non decide al posto dell'utente. L'ultima parola e' l'ascolto.
- Non vede difetti che non sono parole (voce strana, respiri, tono).
"""
import argparse
import collections
import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # serve con "python -I", che non guarda la cartella dello script
import voci  # noqa: E402

os.environ.setdefault("HF_HUB_OFFLINE", "1")   # il modello e' gia' sul disco: niente internet

MODELLO = voci.RADICE / "modelli" / "whisper-large-v3-turbo"
PAROLE_SPIA = {"punto", "punti", "virgola", "virgole"}   # punteggiatura letta ad alta voce
SOGLIA_SOMIGLIANZA = 0.85
PAROLE_MINIME = 3     # una frase di 1-2 parole (es. un nome proprio) non si puo' giudicare con la somiglianza


def parole(testo):
    """Il testo ridotto alle sole parole: minuscolo, senza punteggiatura."""
    t = unicodedata.normalize("NFC", testo.lower())
    t = re.sub(r"[’']", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return t.split()


def confronta(testo, trascritto):
    """Confronta le parole del testo con quelle sentite da Whisper.
    Restituisce (somiglianza da 0 a 1, parole in piu', parole mancanti, in_piu_e_in_coda, numero di parole del testo)."""
    a, b = parole(testo), parole(trascritto)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    in_piu, mancanti, in_coda = [], [], False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert" or (tag == "replace" and (j2 - j1) > (i2 - i1)):
            da = j1 + ((i2 - i1) if tag == "replace" else 0)
            in_piu += b[da:j2]
            if j2 == len(b):
                in_coda = True
        if tag == "delete" or (tag == "replace" and (i2 - i1) > (j2 - j1)):
            da = i1 + ((j2 - j1) if tag == "replace" else 0)
            mancanti += a[da:i2]
    return sm.ratio(), in_piu, mancanti, in_coda, len(a)


def motivi_da_ascoltare(r):
    """Perche' una frase merita di essere ascoltata (lista vuota = niente da segnalare)."""
    motivi = []
    if any(p in PAROLE_SPIA for p in r["in_piu"]):
        motivi.append("punteggiatura letta ad alta voce")
    if len(r["in_piu"]) >= 2:
        motivi.append(f"{len(r['in_piu'])} parole in piu': {' '.join(r['in_piu'][:6])}")
    elif r["in_piu"] and r["in_coda"]:
        motivi.append(f"parola in piu' in fondo: {r['in_piu'][0]}")
    if r["verificabile"] and r["somiglianza"] < SOGLIA_SOMIGLIANZA:
        motivi.append(f"somiglianza bassa ({r['somiglianza']:.2f})")
    return motivi


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("libro")
    ap.add_argument("nome", help="nome base dell'audio, senza estensione (es. 07-food__xtts-Filip_Traverse)")
    ap.add_argument("--cartella-audio", help="cartella dell'MP3/WAV e del JSON (default: output/<libro>/audio)")
    ap.add_argument("--lingua", default="italian", help="lingua parlata, in inglese per Whisper (default: italian)")
    ap.add_argument("--dispositivo", choices=["gpu", "cpu"], default="gpu",
                    help="gpu (default, prende il blocco della scheda) oppure cpu (lento, non tocca la scheda: per prove)")
    ap.add_argument("--frasi", help="solo queste frasi (numeri separati da virgola): per prove; il rapporto va in <nome>-parziale.json")
    args = ap.parse_args()

    audio_dir = Path(args.cartella_audio) if args.cartella_audio else voci.RADICE / "output" / args.libro / "audio"
    sorgente = audio_dir / f"{args.nome}.mp3"
    if not sorgente.exists():
        sorgente = audio_dir / f"{args.nome}.wav"
    if not sorgente.exists() or not (audio_dir / f"{args.nome}.json").exists():
        sys.exit(f"Non trovo {args.nome}.mp3/.wav e .json in {audio_dir}")
    if not MODELLO.exists():
        sys.exit(f"Non trovo il modello Whisper in {MODELLO}")

    cartella = voci.RADICE / "output" / args.libro / "controlli"
    cartella.mkdir(parents=True, exist_ok=True)
    rapporto_path = cartella / f"{args.nome}.json"
    wav = cartella / f"_tmp_{args.nome}_16k.wav"

    if args.dispositivo == "gpu":
        voci.blocca_xtts()   # una sola cosa alla volta sulla scheda video (con --dispositivo cpu la scheda non si usa)

    import soundfile as sf
    import torch
    from transformers import pipeline
    import transformers
    transformers.logging.set_verbosity_error()
    if args.frasi:
        rapporto_path = cartella / f"{args.nome}-parziale.json"   # una prova su poche frasi non sovrascrive il rapporto completo

    subprocess.run([voci.trova_ffmpeg(), "-y", "-loglevel", "error", "-i", str(sorgente),
                    "-ac", "1", "-ar", "16000", str(wav)], check=True)
    audio, sr = sf.read(str(wav), dtype="float32")
    segmenti = json.loads((audio_dir / f"{args.nome}.json").read_text(encoding="utf-8"))["segmenti"]

    print(f"Carico Whisper ({MODELLO.name})...", flush=True)
    usa_gpu = args.dispositivo == "gpu" and torch.cuda.is_available()
    if not usa_gpu:
        torch.set_num_threads(4)   # sul processore uso pochi thread per non rallentare altri lavori
    asr = pipeline("automatic-speech-recognition", model=str(MODELLO),
                   dtype=torch.float16 if usa_gpu else torch.float32, device=0 if usa_gpu else -1)
    numeri = [int(n) for n in args.frasi.split(",")] if args.frasi else list(range(1, len(segmenti) + 1))
    clip = [{"raw": audio[int(segmenti[n - 1]["inizio"] * sr):int(segmenti[n - 1]["fine"] * sr)].copy(), "sampling_rate": sr}
            for n in numeri]
    print(f"Trascrivo {len(clip)} frasi su {'GPU' if usa_gpu else 'processore'}...", flush=True)
    # chunk_length_s=30: Whisper legge al massimo 30 secondi per volta; una frase piu' lunga (es. 40 s) altrimenti
    # blocca tutto il lavoro ("expanded size of the tensor"), come e' successo al capitolo 11 (frase da 39,7 s).
    risultati = asr(clip, batch_size=8, chunk_length_s=30, generate_kwargs={"language": args.lingua, "task": "transcribe"})
    wav.unlink(missing_ok=True)

    righe = []
    for i, r in zip(numeri, risultati):
        s = segmenti[i - 1]
        somiglianza, in_piu, mancanti, in_coda, n_parole = confronta(s["testo"], r["text"])
        riga = {"frase": i, "inizio": s["inizio"], "somiglianza": round(somiglianza, 3), "in_piu": in_piu,
                "mancanti": mancanti, "in_coda": in_coda, "verificabile": n_parole >= PAROLE_MINIME,
                "trascritto": r["text"].strip()}
        riga["motivi"] = motivi_da_ascoltare(riga)
        righe.append(riga)
    rapporto_path.write_text(json.dumps(righe, ensure_ascii=False, indent=1), encoding="utf-8")

    con_punto = [r for r in righe if any(p in PAROLE_SPIA for p in r["in_piu"])]
    con_extra = [r for r in righe if r["in_piu"]]
    da_ascoltare = [r for r in righe if r["motivi"]]
    verificabili = [r["somiglianza"] for r in righe if r["verificabile"]]
    media = sum(verificabili) / len(verificabili) if verificabili else 0
    print(f"\n{args.nome}: {len(righe)} frasi, somiglianza media {media:.3f} (esclusi i nomi/frasi di 1-2 parole)")
    print(f"  'punto/virgola' letti ad alta voce: {len(con_punto)} frasi | frasi con parole in piu': {len(con_extra)}")
    for r in da_ascoltare:
        print(f"  DA ASCOLTARE frase {r['frase']:3} a {mmss(r['inizio'])}: {'; '.join(r['motivi'])}")
    print(f"RISULTATO punto={len(con_punto)} in_piu={len(con_extra)} da_ascoltare={len(da_ascoltare)}")
    print(f"Rapporto completo: {rapporto_path}")


if __name__ == "__main__":
    main()
