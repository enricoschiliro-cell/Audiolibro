"""GENERATORE DI CAPITOLO (resiliente) - trasforma un capitolo gia' diviso in frasi
in un MP3 mono 64 kbps + un file JSON con i tempi di ogni frase.

Uso:
  python genera_capitolo.py <libro> <capitolo> <voce> [--rigenera] [--tieni-frasi] [--tentativi N]

Esempi (da PowerShell, dentro la cartella pipeline):
  ..\\.venv-xtts\\Scripts\\python.exe genera_capitolo.py ivanhoe 01-prova-dialogo xtts:it:Filip_Traverse
  ..\\.venv\\Scripts\\python.exe genera_capitolo.py ivanhoe 01-prova-dialogo piper:it_IT-riccardo-x_low
  (il secondo usa Piper: gira sul processore, senza scheda video, utile per provare la procedura)

Formato della voce:  xtts:<lingua>:<Nome_Voce>   oppure   piper:<nome_modello>

Come funziona (pensato per la scheda video instabile):
  1. Ogni frase viene salvata su disco SUBITO dopo essere stata generata
     (cartella di lavoro output/<libro>/audio/_lavoro/<capitolo>__<voce>/).
  2. Se compare un errore (tipicamente CUDA) il processo muore, e questo programma ne avvia
     UNO NUOVO che riparte dalla prima frase mancante. Dopo un errore CUDA un processo non e' piu'
     utilizzabile, per questo serve proprio un processo nuovo.
  3. Se un processo non riesce a fare nemmeno una frase nuova per N volte di fila (--tentativi, default 3),
     ci si ferma e si dice quale frase da' problemi. Se il processo resta muto per 10 minuti viene chiuso.
  4. Solo un processo XTTS alla volta (blocco in voci.py). Il lavoro e' nel disco, quindi se il PC si
     riavvia basta rilanciare lo STESSO comando: riparte da dove era arrivato.
  5. A frasi complete: unione con le pause decise in voci.py, MP3 e JSON in output/<libro>/audio/.
     La cartella di lavoro si cancella (usa --tieni-frasi per conservarla).

Controllo base di ogni frase: audio vuoto, muto o non valido (NaN) = errore; audio troppo corto o troppo
lungo rispetto al testo = si riprova (XTTS e' casuale, un altro tentativo puo' andare meglio) e, se resta
sospetto, la frase entra comunque ma finisce tra gli "avvisi" del JSON, da ascoltare.
Le soglie sono scelte mie, da tarare sui capitoli veri.
(Il controllo vero di quando XTTS "parla male" e' un altro passo: riconoscimento vocale.)

Per le prove senza scheda: la variabile d'ambiente AUDIOLIBRO_SIMULA_ERRORE=N fa fallire ogni processo
dopo N frasi nuove, per verificare che la ripartenza funzioni.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

import voci

# --- scelte mie, da tarare ---
PROVE_PER_FRASE = 4          # tentativi per una frase "sospetta", dentro lo stesso processo
SILENZIO_MAX = 600           # secondi senza nessuna novita' su disco prima di chiudere un processo bloccato
ATTESA_RIAVVIO = 10          # secondi di pausa prima di avviare un nuovo processo dopo un errore
CONTROLLO_SCHEDA_OGNI = 5    # ogni quante frasi controllare la temperatura della scheda
MIN_SEC_PER_CAR = 0.03       # sotto questa durata per carattere l'audio e' sospetto (parlato normale: circa 0,07)
MAX_SEC_PER_CAR = 0.35       # sopra questa durata per carattere l'audio e' sospetto
MIN_ASSOLUTO = 0.25          # durata minima (secondi) di qualsiasi frase
# Controllo acustico (soglie ricavate dall'audio di prova di Food, 12/11/2026: da tarare con piu' capitoli).
# Una frase "sana" ha circa 0,057 s di PARLATO per carattere e nessuna pausa lunga in mezzo. Le frasi che l'utente
# ha sentito "bloccarsi" o leggere la punteggiatura avevano una pausa interna di 1,1-1,6 s e, in due casi, 1,5 volte
# il parlato normale. Le pause normali tra due parti di una frase spezzata da noi sono circa 0,75 s.
SOGLIA_SILENZIO_DB = -45     # sotto questo livello (in dB) un frammento di 20 ms conta come silenzio
PARLATO_PER_CAR_MEDIO = 0.057
RAPPORTO_PARLATO_MAX = 1.4   # oltre: forse ripete o legge parole in piu' (solo per frasi di almeno 40 caratteri)
PAUSA_INTERNA_MAX = 1.0      # secondi di silenzio in mezzo alla frase: oltre, forse si blocca o legge "punto"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ------------------------------------------------------------------ voce e percorsi
def leggi_voce(specifica):
    """'xtts:it:Filip_Traverse' -> ('xtts', 'it', 'Filip Traverse', 'xtts-Filip_Traverse')"""
    motore, *resto = specifica.split(":")
    if motore == "xtts" and len(resto) == 2:
        return motore, resto[0], resto[1].replace("_", " "), "xtts-" + resto[1].replace(" ", "_")
    if motore == "piper" and len(resto) == 1:
        return motore, resto[0].split("_")[0], resto[0], "piper-" + resto[0]
    sys.exit(f"Voce non valida: {specifica!r}. Formato: xtts:<lingua>:<Nome_Voce> oppure piper:<nome_modello>")


def percorsi(libro, capitolo, etichetta):
    base = voci.RADICE / "output" / libro / "audio"
    nome = f"{capitolo}__{etichetta}"
    return {"mp3": base / f"{nome}.mp3", "json": base / f"{nome}.json", "lavoro": base / "_lavoro" / nome}


def costruisci_voce(motore, lingua, nome):
    if motore == "xtts":
        os.environ.setdefault("COQUI_TOS_AGREED", "1")  # licenza CPML gia' accettata dall'utente (uso personale)
        return voci.Xtts(lingua, nome)
    return voci.Piper(nome)


# ------------------------------------------------------------------ frasi salvate su disco
def chiave(i, testo):
    """Nome del file di una frase: numero + impronta del testo, cosi' se il testo viene corretto
    la frase vecchia non viene riutilizzata per sbaglio."""
    return f"{i:05d}_{hashlib.sha1(testo.encode('utf-8')).hexdigest()[:8]}"


def e_pronta(lavoro, i, testo):
    k = chiave(i, testo)
    return (lavoro / f"{k}.json").exists() and (lavoro / f"{k}.wav").exists()


def mancanti(lavoro, segmenti):
    return [i for i, (_, testo, _) in enumerate(segmenti) if not e_pronta(lavoro, i, testo)]


def salva_frase(lavoro, i, testo, audio, sr, avviso):
    """Scrive prima l'audio, poi il file 'meta' (che e' il segno che la frase e' completa).
    Ogni file si scrive con un nome provvisorio e poi si rinomina: un'interruzione non lascia file a meta'."""
    k = chiave(i, testo)
    tmp = lavoro / f"{k}.tmp.wav"
    sf.write(str(tmp), np.clip(audio, -1.0, 1.0), sr, format="WAV", subtype="PCM_16")
    os.replace(tmp, lavoro / f"{k}.wav")
    meta = {"indice": i, "durata": round(len(audio) / sr, 3), "sr": sr, "avviso": avviso}
    tmp = lavoro / f"{k}.tmp.json"
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, lavoro / f"{k}.json")


def elimina_frase(lavoro, i, testo):
    k = chiave(i, testo)
    for estensione in ("wav", "json"):
        (lavoro / f"{k}.{estensione}").unlink(missing_ok=True)


# ------------------------------------------------------------------ controllo di una frase
def analisi_acustica(audio, sr):
    """Restituisce (secondi di parlato, pausa interna piu' lunga in secondi).
    Il silenzio all'inizio e in fondo (compreso quello aggiunto dalla libreria TTS dopo ogni pezzo) non conta:
    interessa solo il silenzio IN MEZZO al parlato, segno di un 'blocco' o di una parola letta in piu'."""
    frame = int(0.02 * sr)
    n = len(audio) // frame
    if n == 0:
        return 0.0, 0.0
    rms = np.sqrt((audio[:n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    silenzio = 20 * np.log10(rms) < SOGLIA_SILENZIO_DB
    attivi = np.where(~silenzio)[0]
    if attivi.size == 0:
        return 0.0, 0.0
    massimo = corrente = 0
    for v in silenzio[attivi[0]:attivi[-1] + 1]:
        corrente = corrente + 1 if v else 0
        massimo = max(massimo, corrente)
    return float((~silenzio).sum() * 0.02), massimo * 0.02


def controlla_audio(audio, sr, testo):
    """Restituisce (motivo, grave, punteggio). motivo None = a posto. grave = audio inutilizzabile (vuoto, muto, NaN).
    punteggio: piu' e' basso meglio e'; serve a scegliere il tentativo migliore quando nessuno e' perfetto."""
    if audio.size == 0:
        return "audio vuoto", True, 99.0
    if not np.isfinite(audio).all():
        return "audio con valori non validi (NaN)", True, 99.0
    if float(np.abs(audio).max()) < 0.01:
        return "audio quasi muto", True, 99.0
    dur = audio.size / sr
    minimo = max(MIN_ASSOLUTO, MIN_SEC_PER_CAR * len(testo))
    massimo = 3.0 + MAX_SEC_PER_CAR * len(testo)
    if dur < minimo:
        return f"troppo corto ({dur:.1f} s per {len(testo)} caratteri): forse tagliato", False, 10.0
    if dur > massimo:
        return f"troppo lungo ({dur:.1f} s per {len(testo)} caratteri): forse ha farfugliato", False, 10.0
    parlato, pausa = analisi_acustica(audio, sr)
    rapporto = (parlato / len(testo)) / PARLATO_PER_CAR_MEDIO if len(testo) >= 40 else 1.0
    punteggio = pausa / PAUSA_INTERNA_MAX + rapporto / RAPPORTO_PARLATO_MAX
    if pausa >= PAUSA_INTERNA_MAX:
        return f"pausa di {pausa:.1f} s in mezzo alla frase: forse si blocca o legge la punteggiatura", False, punteggio
    if rapporto >= RAPPORTO_PARLATO_MAX:
        return f"parlato {rapporto:.1f} volte piu' lungo del normale: forse ripete o legge parole in piu'", False, punteggio
    return None, False, punteggio


def genera_frase(voce, testo):
    """Genera una frase, riprovando se il risultato e' sospetto (XTTS e' casuale: un altro tentativo puo' andare meglio).
    Restituisce (audio, avviso o None). Tra i tentativi tiene il MIGLIORE, non l'ultimo.
    Se nessun tentativo e' utilizzabile (vuoto, muto, NaN) alza un errore: il processo muore e riparte."""
    migliore = None            # (grave, punteggio, numero tentativo, audio, motivo)
    for tentativo in range(1, PROVE_PER_FRASE + 1):
        audio = np.asarray(voce(testo), dtype=np.float32).reshape(-1)
        motivo, grave, punteggio = controlla_audio(audio, voce.sr, testo)
        if motivo is None:
            return audio, None
        print(f"       tentativo {tentativo}/{PROVE_PER_FRASE}: {motivo}", flush=True)
        candidato = (grave, punteggio, tentativo, audio, motivo)
        if migliore is None or candidato[:3] < migliore[:3]:
            migliore = candidato
    grave, _, _, audio, motivo = migliore
    if grave:
        raise RuntimeError(f"audio non valido dopo {PROVE_PER_FRASE} tentativi: {motivo}")
    return audio, motivo


# ------------------------------------------------------------------ il LAVORATORE (processo che genera)
# Core su cui fissare il processo che genera l'audio (numero di processore logico; -1 = non fissare; si cambia con la
# variabile d'ambiente AUDIOLIBRO_CORE). PERCHE': su questo portatile (i9-13900H: processori logici 0-11 "grandi",
# 12-19 "piccoli") la velocita' alternava fasi veloci (0,4-0,6 s di calcolo per s di audio) e fasi lente di alcuni
# minuti (1,5-2,2); nelle fasi lente il processore risultava a circa il 70% delle prestazioni e il programma saltava
# tra core diversi. Con il processo fissato su un core grande: capitolo 11 da 2,19 a 0,49 s/s appena fissato, capitolo
# 14 intero costante a 0,46-0,49 s/s (12/11/2026, due osservazioni: indizio forte, non prova). Il 6 e' una scelta mia
# (un core grande, non lo 0 che usa Windows per molte cose): da validare sul capitolo 08. Non e' un'impostazione di
# sistema: vale solo per questo processo e sparisce quando finisce.
CORE_LAVORATORE = int(os.environ.get("AUDIOLIBRO_CORE", "6") or 6)


def fissa_su_un_core(core=None):
    core = CORE_LAVORATORE if core is None else core
    if core < 0 or sys.platform != "win32" or (os.cpu_count() or 0) <= core:
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        if k.SetProcessAffinityMask(k.GetCurrentProcess(), 1 << core):
            print(f"  processo fissato sul processore logico {core}", flush=True)
        else:
            print("  non sono riuscito a fissare il processo su un core: si va avanti senza", flush=True)
    except Exception as e:
        print(f"  non sono riuscito a fissare il processo su un core ({e}): si va avanti senza", flush=True)


def lavoratore(libro, capitolo, specifica):
    motore, lingua, nome, etichetta = leggi_voce(specifica)
    lavoro = percorsi(libro, capitolo, etichetta)["lavoro"]
    lavoro.mkdir(parents=True, exist_ok=True)
    _, segmenti = voci.carica_capitolo(libro, capitolo)
    da_fare = mancanti(lavoro, segmenti)
    if not da_fare:
        return 0
    print(f"Carico la voce ({specifica})...", flush=True)
    voce = costruisci_voce(motore, lingua, nome)
    fissa_su_un_core()   # dopo il caricamento della voce, come nell'esperimento del 12/11/2026
    simula = int(os.environ.get("AUDIOLIBRO_SIMULA_ERRORE", "0") or 0)
    t0 = time.time()
    for n, i in enumerate(da_fare, 1):
        _, testo, _ = segmenti[i]
        if motore == "xtts" and (n - 1) % CONTROLLO_SCHEDA_OGNI == 0:
            voci.attendi_scheda_fresca()
        if simula and n - 1 >= simula:
            raise RuntimeError(f"errore simulato dopo {simula} frasi (AUDIOLIBRO_SIMULA_ERRORE)")
        t_frase = time.time()
        audio, avviso = genera_frase(voce, testo)
        salva_frase(lavoro, i, testo, audio, voce.sr, avviso)
        stima = (time.time() - t0) / n * (len(da_fare) - n)
        nota = f"  ! {avviso}" if avviso else ""
        print(f"  [{n:4}/{len(da_fare)}] frase {i + 1:4}  {len(testo):3} car.  audio {len(audio) / voce.sr:5.1f} s"
              f"  (calcolo {time.time() - t_frase:4.1f} s, mancano circa {stima / 60:3.0f} min){nota}", flush=True)
    return 0


# ------------------------------------------------------------------ il SUPERVISORE (avvia e riavvia i lavoratori)
def ultimo_segno_di_vita(lavoro, t_avvio):
    """Momento dell'ultima novita' su disco (o dell'avvio del processo): serve a capire se e' bloccato."""
    t = t_avvio
    if lavoro.exists():
        for f in lavoro.iterdir():
            try:
                t = max(t, f.stat().st_mtime)
            except OSError:
                pass   # il file era temporaneo (.tmp.wav) ed e' stato rinominato/cancellato proprio ora: succede, e va ignorato
                       # (12/11/2026: senza questo il supervisore si fermava con FileNotFoundError e lasciava il lavoratore da solo)
    return t


def esegui_lavoratore(libro, capitolo, specifica, lavoro):
    comando = [sys.executable, "-W", "ignore", str(Path(__file__).resolve()), libro, capitolo, specifica, "--lavoratore"]
    # HF_HUB_OFFLINE=1: il modello e' gia' sul disco; senza questo, se huggingface.co non risponde il caricamento della voce
    # resta fermo anche 3 minuti a provare a collegarsi (visto il 12/11/2026). Provato: la voce si carica e genera senza rete.
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", HF_HUB_DISABLE_SYMLINKS_WARNING="1", HF_HUB_OFFLINE="1")
    t_avvio = time.time()
    processo = subprocess.Popen(comando, env=ambiente)
    try:
        while True:
            try:
                return processo.wait(timeout=30)
            except subprocess.TimeoutExpired:
                if time.time() - ultimo_segno_di_vita(lavoro, t_avvio) > SILENZIO_MAX:
                    print(f"  nessuna novita' da {SILENZIO_MAX // 60} minuti: chiudo il processo", flush=True)
                    processo.kill()
                    processo.wait()
                    return -9
    except BaseException:
        # qualunque errore del supervisore (non solo Ctrl+C): il lavoratore non deve restare in giro da solo,
        # perche' terrebbe occupata la scheda (e il blocco XTTS) e il capitolo successivo non partirebbe
        processo.kill()
        processo.wait()
        raise


def leggi_frasi(lavoro, segmenti):
    """Rilegge tutte le frasi salvate. Se una e' illeggibile la cancella e restituisce None (andra' rigenerata)."""
    audio_per_segmento, metas = [], []
    for i, (_, testo, _) in enumerate(segmenti):
        k = chiave(i, testo)
        try:
            audio, sr = sf.read(str(lavoro / f"{k}.wav"), dtype="float32")
            meta = json.loads((lavoro / f"{k}.json").read_text(encoding="utf-8"))
            if sr != meta["sr"]:
                raise ValueError("frequenza diversa")
        except Exception as e:
            print(f"  la frase {i + 1} salvata e' illeggibile ({e}): la rigenero", flush=True)
            elimina_frase(lavoro, i, testo)
            return None
        audio_per_segmento.append(audio)
        metas.append(meta)
    return audio_per_segmento, metas


def supervisore(libro, capitolo, specifica, rigenera, tieni_frasi, max_senza_progressi):
    motore, lingua, nome, etichetta = leggi_voce(specifica)
    p = percorsi(libro, capitolo, etichetta)
    dati, segmenti = voci.carica_capitolo(libro, capitolo)

    if p["mp3"].exists() and p["json"].exists() and not rigenera:
        print(f"Gia' pronto: {p['mp3'].name} (usa --rigenera per rifarlo)")
        return 0
    if rigenera:
        shutil.rmtree(p["lavoro"], ignore_errors=True)
        p["mp3"].unlink(missing_ok=True)
        p["json"].unlink(missing_ok=True)
    p["lavoro"].mkdir(parents=True, exist_ok=True)

    da_fare = mancanti(p["lavoro"], segmenti)
    print(f"'{dati['titolo']}' con la voce {nome}: {len(segmenti)} frasi, "
          f"{len(segmenti) - len(da_fare)} gia' pronte, {len(da_fare)} da generare.", flush=True)

    riavvii, senza_progressi, giri_lettura = 0, 0, 0
    while True:
        da_fare = mancanti(p["lavoro"], segmenti)
        if da_fare:
            if senza_progressi >= max_senza_progressi:
                i = da_fare[0]
                print(f"\nMi fermo: {senza_progressi} processi di fila senza riuscire a fare nemmeno una frase nuova.\n"
                      f"Prima frase mancante: numero {i + 1} di {len(segmenti)}:\n  {segmenti[i][1][:200]}\n"
                      f"Il lavoro fatto e' salvato: rilanciando lo stesso comando si riparte da li'.", flush=True)
                return 1
            print(f"\n--- avvio un processo ({len(da_fare)} frasi da fare)", flush=True)
            codice = esegui_lavoratore(libro, capitolo, specifica, p["lavoro"])
            if codice == voci.CODICE_OCCUPATO:
                return 1
            dopo = mancanti(p["lavoro"], segmenti)
            senza_progressi = 0 if len(dopo) < len(da_fare) else senza_progressi + 1
            if dopo:
                riavvii += 1
                print(f"--- il processo si e' fermato (codice {codice}), mancano {len(dopo)} frasi. "
                      f"Riavvio tra {ATTESA_RIAVVIO} s (riavvio numero {riavvii})", flush=True)
                time.sleep(ATTESA_RIAVVIO)
            continue

        # tutte le frasi sono pronte: le rileggo e le unisco
        giri_lettura += 1
        letto = leggi_frasi(p["lavoro"], segmenti)
        if letto is None:
            if giri_lettura >= 3:
                print("Troppe frasi illeggibili: mi fermo.", flush=True)
                return 1
            continue
        break

    audio_per_segmento, metas = letto
    sr = metas[0]["sr"]
    audio, tempi = voci.unisci(segmenti, audio_per_segmento, sr)
    voci.salva_mp3(audio, sr, p["mp3"])
    avvisi = [{"frase": m["indice"] + 1, "motivo": m["avviso"], "testo": segmenti[m["indice"]][1]}
              for m in metas if m["avviso"]]
    risultato = {
        "libro": libro, "capitolo": capitolo, "titolo": dati["titolo"],
        "motore": motore, "lingua": lingua, "voce": nome, "sr": sr,
        "durata": round(len(audio) / sr, 3), "mp3": p["mp3"].name,
        "riavvii": riavvii, "generato": datetime.now().isoformat(timespec="seconds"),
        "segmenti": tempi, "avvisi": avvisi,
    }
    p["json"].write_text(json.dumps(risultato, ensure_ascii=False, indent=1), encoding="utf-8")

    cartella_output = (voci.RADICE / "output").resolve()
    if not tieni_frasi and p["lavoro"].resolve().is_relative_to(cartella_output):
        shutil.rmtree(p["lavoro"], ignore_errors=True)

    durata = len(audio) / sr
    mb = p["mp3"].stat().st_size / 1e6
    print(f"\nFATTO: {p['mp3'].name}  durata {int(durata // 60)} min {int(durata % 60)} s, {mb:.1f} MB, "
          f"{riavvii} riavvii, {len(avvisi)} frasi da ascoltare con attenzione.", flush=True)
    for a in avvisi:
        print(f"  frase {a['frase']}: {a['motivo']}\n    {a['testo'][:120]}", flush=True)
    print(f"Tempi per frase: {p['json'].name}")
    return 0


# ------------------------------------------------------------------ avvio
def main():
    argv = sys.argv[1:]

    def opzione(nome, default=None):
        if nome in argv:
            i = argv.index(nome)
            valore = argv[i + 1]
            del argv[i:i + 2]
            return valore
        return default

    max_tentativi = int(opzione("--tentativi", 3))
    flag = {f: f in argv for f in ("--rigenera", "--tieni-frasi", "--lavoratore")}
    argv = [a for a in argv if a not in flag]
    if len(argv) != 3:
        sys.exit(__doc__)
    libro, capitolo, specifica = argv
    if flag["--lavoratore"]:
        sys.exit(lavoratore(libro, capitolo, specifica))
    sys.exit(supervisore(libro, capitolo, specifica, flag["--rigenera"], flag["--tieni-frasi"], max_tentativi))


if __name__ == "__main__":
    main()
