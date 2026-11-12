"""Elimina dalla cache di Hugging Face i file di UN solo modello, senza toccare gli altri.
(La cache condivide i file tra modelli: cancellare la cartella a mano e' pericoloso.)

Uso:  python pulisci_cache.py <repo_id>            -> mostra cosa verrebbe cancellato (non cancella)
      python pulisci_cache.py <repo_id> --esegui   -> cancella davvero
Esempio: python pulisci_cache.py ResembleAI/chatterbox"""
import sys

from huggingface_hub import scan_cache_dir

repo_id = sys.argv[1]
esegui = "--esegui" in sys.argv
info = scan_cache_dir()
print("Modelli nella cache:")
for r in info.repos:
    print(f"  {r.repo_id:35} {r.size_on_disk_str}")

revisioni = [rev.commit_hash for r in info.repos if r.repo_id == repo_id for rev in r.revisions]
if not revisioni:
    sys.exit(f"\nNessun modello '{repo_id}' nella cache.")
piano = info.delete_revisions(*revisioni)
print(f"\nCancellando '{repo_id}' si liberano {piano.expected_freed_size_str} (solo file non usati da altri modelli).")
if esegui:
    piano.execute()
    print("Fatto.")
else:
    print("(Prova: non ho cancellato niente.)")
