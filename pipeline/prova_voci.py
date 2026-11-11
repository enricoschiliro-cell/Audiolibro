"""PROVA DI VOCI - legge l'inizio di un capitolo con piu' voci e salva un MP3 per ciascuna,
cosi' puoi ascoltarle e scegliere.

Uso:   python prova_voci.py <libro> <capitolo> <parole> voce1 voce2 ...
Esempio: python prova_voci.py whyte 07-food 150 kokoro:b:bm_george kokoro:a:am_michael

Formato delle voci:  kokoro:<lingua>:<nome>      (lingua: a = americano, b = britannico, i = italiano)
I file escono in output/<libro>/prove-voci/
"""
import sys
import time

import voci

libro, capitolo, parole = sys.argv[1], sys.argv[2], int(sys.argv[3])
dati, segmenti = voci.carica_capitolo(libro, capitolo)
campione = voci.inizio_capitolo(segmenti, parole)
n_parole = sum(len(t.split()) for _, t, _ in campione)
print(f"Campione: {len(campione)} segmenti, {n_parole} parole di '{dati['titolo']}'")

for specifica in sys.argv[4:]:
    motore, *resto = specifica.split(":")
    if motore == "kokoro":
        lingua, nome = resto
        voce = voci.Kokoro(lingua, nome)
    elif motore == "piper":
        nome = resto[0]
        voce = voci.Piper(nome)
    else:
        print("motore sconosciuto:", motore)
        continue
    t0 = time.time()
    audio, tempi = voci.assembla(campione, voce, voce.sr)
    secondi = time.time() - t0
    uscita = voci.RADICE / "output" / libro / "prove-voci" / f"{capitolo}__{motore}-{nome}.mp3"
    voci.salva_mp3(audio, voce.sr, uscita)
    durata = len(audio) / voce.sr
    print(f"{specifica:28} durata {durata:5.1f} s, generata in {secondi:4.1f} s  ->  {uscita.name}")
