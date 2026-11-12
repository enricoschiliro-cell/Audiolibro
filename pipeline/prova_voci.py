"""PROVA DI VOCI - legge l'inizio di un capitolo con piu' voci e salva un MP3 per ciascuna,
cosi' puoi ascoltarle e scegliere.

Uso:   python prova_voci.py <libro> <capitolo> <parole> voce1 voce2 ... [--rigenera]
Esempio: python prova_voci.py ivanhoe 00-prova-italiano 90 xtts:it:Damien_Black xtts:it:Luis_Moray

Formato delle voci:
  xtts:<lingua>:<Nome_Voce>   (gli underscore diventano spazi)   es. xtts:it:Damien_Black
  piper:<nome_modello>                                            es. piper:it_IT-riccardo-x_low
I file escono in output/<libro>/prove-voci/

Robustezza (dopo un arresto del PC causato dalla scheda video):
  - il modello XTTS si carica UNA volta sola e poi si cambia solo la voce;
  - ogni voce viene salvata appena e' pronta;
  - le voci gia' generate vengono saltate (usa --rigenera per rifarle), quindi dopo un'interruzione
    basta rilanciare lo stesso comando e riparte da dove si era fermato.
"""
import sys
import time

import voci

args = [a for a in sys.argv[1:] if a != "--rigenera"]
rigenera = "--rigenera" in sys.argv
libro, capitolo, parole = args[0], args[1], int(args[2])
dati, segmenti = voci.carica_capitolo(libro, capitolo)
campione = voci.inizio_capitolo(segmenti, parole)
n_parole = sum(len(t.split()) for _, t, _ in campione)
print(f"Campione: {len(campione)} segmenti, {n_parole} parole di '{dati['titolo']}'", flush=True)

xtts = None  # il modello XTTS si carica una volta sola
for specifica in args[3:]:
    motore, *resto = specifica.split(":")
    if motore == "xtts":
        lingua, nome_voce = resto[0], resto[1].replace("_", " ")
        nome = nome_voce.replace(" ", "_")
    elif motore == "piper":
        nome = resto[0]
    else:
        print("motore sconosciuto:", motore, flush=True)
        continue

    uscita = voci.RADICE / "output" / libro / "prove-voci" / f"{capitolo}__{motore}-{nome}.mp3"
    if uscita.exists() and not rigenera:
        print(f"{specifica:28} gia' presente, salto", flush=True)
        continue

    voci.attendi_scheda_fresca()
    if motore == "xtts":
        if xtts is None:
            xtts = voci.Xtts(lingua, nome_voce)
        xtts.lingua, xtts.speaker = lingua, nome_voce
        voce = xtts
    else:
        voce = voci.Piper(nome)

    t0 = time.time()
    audio, tempi = voci.assembla(campione, voce, voce.sr)
    secondi = time.time() - t0
    voci.salva_mp3(audio, voce.sr, uscita)
    durata = len(audio) / voce.sr
    print(f"{specifica:28} durata {durata:5.1f} s, generata in {secondi:4.1f} s  ->  {uscita.name}", flush=True)
