"""Diagnosi: sintetizza UNA frase alla volta di un capitolo-campione con una voce XTTS e si ferma al primo errore,
cosi' si capisce se il problema e' una frase precisa o la scheda video.
Uso (con CUDA_LAUNCH_BLOCKING=1 per avere l'errore esatto):
    python xtts_diagnosi.py <libro> <capitolo> <Nome_Voce>"""
import sys
import time

import torch
from TTS.api import TTS

import voci

libro, capitolo, voce = sys.argv[1], sys.argv[2], sys.argv[3].replace("_", " ")
_, segmenti = voci.carica_capitolo(libro, capitolo)
print("CUDA:", torch.cuda.is_available(), flush=True)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
for i, (tipo, testo, _) in enumerate(segmenti):
    t0 = time.time()
    try:
        wav = tts.tts(text=testo, speaker=voce, language="it")
        torch.cuda.synchronize()
        print(f"{i:2} OK    {len(testo):3} caratteri  {len(wav) / 24000:5.1f} s audio in {time.time() - t0:4.1f} s | {testo[:60]}", flush=True)
    except Exception as e:
        print(f"{i:2} ERRORE {len(testo):3} caratteri | {testo}", flush=True)
        print("   ->", type(e).__name__, str(e).splitlines()[0][:120], flush=True)
        break
