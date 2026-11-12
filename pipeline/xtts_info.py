"""Carica XTTS-v2 e stampa le voci di serie e la firma delle funzioni (nessuna sintesi).
Uso (nell'ambiente .venv-xtts):  python xtts_info.py
Richiede la variabile COQUI_TOS_AGREED=1 (accettazione della licenza CPML, uso non commerciale)."""
import inspect

import torch
from TTS.api import TTS

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
print("CUDA:", torch.cuda.is_available())
print("firma tts():", inspect.signature(tts.tts))
voci = tts.speakers
print(f"voci di serie: {len(voci)}")
print(", ".join(voci))
print("lingue:", tts.languages)
