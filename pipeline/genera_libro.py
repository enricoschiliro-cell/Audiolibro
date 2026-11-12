"""Genera l'audio di TUTTI i capitoli di un libro, uno dopo l'altro, e controlla ognuno con Whisper.

Uso (con l'ambiente .venv-xtts):
    python genera_libro.py <libro> <voce> [--capitoli 02-preface,03-introduction] [--prova]
    esempio: python genera_libro.py whyte-it-gemma xtts:it:Filip_Traverse --prova     (solo il piano, non genera nulla)
             python genera_libro.py whyte-it-gemma xtts:it:Filip_Traverse              (genera i capitoli mancanti)

Cosa fa, in ordine, per ogni capitolo che non ha ancora l'MP3:
  1. aspetta che il portatile sia collegato alla corrente (a batteria la scheda rallenta di circa 2,7 volte);
  2. lancia genera_capitolo.py (che si riprende da solo se si ferma e rigenera le frasi con pause strane);
  3. lancia controlla_whisper.py (trascrive e confronta con il testo: cerca le parole in piu', es. "punto").
Intanto: tiene il computer sveglio e scrive un registro della scheda video ogni 30 secondi
(temperatura, frequenza, potenza, motivo dell'eventuale rallentamento) in output/<libro>/log/gpu-<data>.csv,
per capire PERCHE' la generazione a volte rallenta (causa non ancora verificata).
Un solo processo sulla scheda alla volta, sempre (regola del progetto dopo il blue screen dell'11/11/2026).
I capitoli gia' pronti non si rifanno; se il lavoro si interrompe basta rilanciarlo.
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import voci

QUI = Path(__file__).resolve().parent
ATTESA_CORRENTE_MAX = 2 * 3600   # se resta a batteria piu' di 2 ore mi fermo
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


class StatoEnergia(ctypes.Structure):
    _fields_ = [("AC", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("percento", ctypes.c_ubyte),
                ("flag2", ctypes.c_ubyte), ("secondi", ctypes.c_ulong), ("secondi_pieno", ctypes.c_ulong)]


def collegato_alla_corrente():
    """True/False; None se non si riesce a sapere (in quel caso non blocco il lavoro)."""
    try:
        s = StatoEnergia()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return {0: False, 1: True}.get(s.AC)
    except Exception:
        pass
    return None


def ora():
    return datetime.now().strftime("%H:%M:%S")


def dire(testo):
    print(f"[{ora()}] {testo}", flush=True)


def nome_base(voce, capitolo):
    """Nome del file audio, come lo decide genera_capitolo.py (<capitolo>__<etichetta>)."""
    motore, *resto = voce.split(":")
    if motore == "xtts" and len(resto) == 2:
        return f"{capitolo}__xtts-{resto[1].replace(' ', '_')}"
    if motore == "piper" and len(resto) == 1:
        return f"{capitolo}__piper-{resto[0]}"
    sys.exit(f"Voce non valida: {voce!r}")


def lancia(comando, log):
    """Esegue un programma scrivendo tutto nel file di registro. Restituisce il codice d'uscita."""
    env = dict(os.environ, COQUI_TOS_AGREED="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    with open(log, "wb") as f:
        return subprocess.run(comando, cwd=QUI, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


def leggi(log):
    try:
        return Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def aspetta_corrente():
    """Se il portatile e' a batteria aspetta che lo colleghino (controlla ogni 30 secondi)."""
    if collegato_alla_corrente() is not False:
        return True
    dire("ATTENZIONE: il portatile e' a batteria: aspetto che lo colleghino alla corrente...")
    inizio = time.time()
    while collegato_alla_corrente() is False:
        if time.time() - inizio > ATTESA_CORRENTE_MAX:
            dire("Sono passate 2 ore a batteria: mi fermo.")
            return False
        time.sleep(30)
    dire("Corrente collegata, riprendo.")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("libro")
    ap.add_argument("voce", help="xtts:<lingua>:<Nome_Voce> oppure piper:<modello>")
    ap.add_argument("--capitoli", help="solo questi capitoli, separati da virgola (default: tutti quelli senza MP3)")
    ap.add_argument("--prova", action="store_true", help="mostra solo il piano, non genera niente")
    ap.add_argument("--senza-whisper", action="store_true", help="salta il controllo con Whisper")
    args = ap.parse_args()

    radice = voci.RADICE / "output" / args.libro
    tutti = sorted(p.stem for p in (radice / "frasi").glob("*.json"))
    scelti = [c.strip() for c in args.capitoli.split(",")] if args.capitoli else tutti
    mancano_nomi = [c for c in scelti if c not in tutti]
    if mancano_nomi:
        sys.exit(f"Capitoli che non esistono: {mancano_nomi}. Quelli disponibili: {tutti}")
    audio = radice / "audio"
    da_fare = [c for c in scelti if not (audio / f"{nome_base(args.voce, c)}.mp3").exists()]
    pronti = [c for c in scelti if c not in da_fare]

    dire(f"Libro {args.libro}, voce {args.voce}: {len(da_fare)} capitoli da fare, {len(pronti)} gia' pronti.")
    if pronti:
        dire("Gia' pronti: " + ", ".join(pronti))
    if not da_fare:
        return
    # stima grezza della durata: 0,0726 s di audio per carattere (misurato su Food), calcolo 0,55-1,7 s per s di audio
    car = 0
    for c in da_fare:
        d = json.loads((radice / "frasi" / f"{c}.json").read_text(encoding="utf-8"))
        n = sum(len(t) for b in d["blocchi"] for t in b["frasi"])
        car += n
        dire(f"  da fare: {c:36} {n:6} caratteri, circa {n * 0.0726 / 60:4.1f} min di audio")
    ore_audio = car * 0.0726 / 3600
    dire(f"Totale: circa {ore_audio:.1f} ore di audio; calcolo stimato da {ore_audio * 0.55:.1f} a {ore_audio * 1.7:.1f} ore "
         f"(stima grezza: la velocita' e' variata da 0,55 a 1,7 s di calcolo per s di audio).")
    if args.prova:
        stato = {True: "SI'", False: "NO (a batteria: aspetterei)", None: "non so"}[collegato_alla_corrente()]
        dire(f"Portatile collegato alla corrente: {stato}")
        dire("Prova: non genero niente.")
        return

    (radice / "log").mkdir(exist_ok=True)
    adesso = datetime.now().strftime("%Y%m%d-%H%M")
    csv = radice / "log" / f"gpu-{adesso}.csv"
    monitor = None
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)   # computer sveglio finche' lavoro
    except Exception:
        dire("Non riesco a tenere il computer sveglio da solo: controlla le impostazioni di sospensione.")
    try:
        monitor = subprocess.Popen(
            ["nvidia-smi", "--query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.max.sm,power.draw,utilization.gpu,"
             "memory.used,clocks_throttle_reasons.active", "--format=csv", "-l", "30", "-f", str(csv)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dire(f"Registro della scheda video: {csv}")
    except Exception:
        dire("nvidia-smi non parte: niente registro della scheda.")

    riepilogo, falliti_di_fila = [], 0
    inizio_tutto = time.time()
    try:
        for n, cap in enumerate(da_fare, 1):
            if not aspetta_corrente():
                break
            base = nome_base(args.voce, cap)
            log_gen = radice / "log" / f"{cap}.log"
            log_wh = radice / "log" / f"{cap}-whisper.log"
            dire(f"=== [{n}/{len(da_fare)}] {cap}: genero l'audio ===")
            t0 = time.time()
            codice = lancia([sys.executable, "-u", str(QUI / "genera_capitolo.py"), args.libro, cap, args.voce], log_gen)
            minuti = (time.time() - t0) / 60
            testo = leggi(log_gen)
            if codice == voci.CODICE_OCCUPATO:
                dire("Un altro processo sta usando la scheda: mi fermo, non tocco niente.")
                break
            if codice != 0 or not (audio / f"{base}.mp3").exists():
                falliti_di_fila += 1
                dire(f"{cap}: NON riuscito (codice {codice}, {minuti:.1f} min). Vedi {log_gen}")
                riepilogo.append((cap, "NON RIUSCITO", minuti, 0, "", ""))
                if falliti_di_fila >= 2:
                    dire("Due capitoli di fila falliti: mi fermo (puo' essere la scheda video). Rilancia dopo aver controllato.")
                    break
                continue
            falliti_di_fila = 0
            rigenerate = len(re.findall(r"tentativo \d/\d", testo))
            m = re.search(r"FATTO:.*?durata (\d+) min (\d+) s", testo)
            durata = int(m.group(1)) * 60 + int(m.group(2)) if m else 0
            dire(f"{cap}: audio pronto, {durata // 60} min {durata % 60} s di audio, {minuti:.1f} min di calcolo, "
                 f"{rigenerate} tentativi scartati dal controllo pause")
            esito = "Whisper saltato"
            if not args.senza_whisper:
                dire(f"{cap}: controllo con Whisper...")
                codice_w = lancia([sys.executable, "-I", str(QUI / "controlla_whisper.py"), args.libro, base], log_wh)
                r = re.search(r"RISULTATO punto=(\d+) in_piu=(\d+) da_ascoltare=(\d+)", leggi(log_wh))
                if codice_w == 0 and r:
                    esito = f"punto={r.group(1)}, frasi con parole in piu'={r.group(2)}, da ascoltare={r.group(3)}"
                else:
                    esito = f"Whisper NON riuscito (codice {codice_w})"
                dire(f"{cap}: {esito}")
            riepilogo.append((cap, "ok", minuti, durata, f"{rigenerate} scartati", esito))
    finally:
        if monitor:
            monitor.terminate()
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    dire(f"=== FINE: {len(riepilogo)} capitoli trattati in {(time.time() - inizio_tutto) / 3600:.2f} ore ===")
    for cap, stato, minuti, durata, scarti, esito in riepilogo:
        rapporto = f"{minuti * 60 / durata:.2f} s calcolo/s audio" if durata else "-"
        dire(f"  {cap:36} {stato:13} {durata // 60:3} min audio, {minuti:5.1f} min calcolo ({rapporto}); {scarti}; {esito}")
    dire(f"Registro scheda: {csv}")


if __name__ == "__main__":
    main()
