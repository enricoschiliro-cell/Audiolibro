"""Test rapidissimo di XTTS: una sola frase breve, non salva nulla.
Serve a capire se la scheda video funziona dopo un arresto o un errore.
Uso: python xtts_test_rapido.py [Nome_Voce]   (nell'ambiente .venv-xtts)"""
import sys
import time

import torch
from TTS.api import TTS

voce = (sys.argv[1] if len(sys.argv) > 1 else "Damien_Black").replace("_", " ")
print("CUDA:", torch.cuda.is_available(), flush=True)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
t0 = time.time()
wav = tts.tts(text="Questa è una prova molto breve della voce.", speaker=voce, language="it")
torch.cuda.synchronize()
print(f"OK: voce '{voce}', {len(wav) / 24000:.1f} s di audio in {time.time() - t0:.1f} s", flush=True)
