"""TRADUZIONE INGLESE -> ITALIANO con TranslateGemma (modello linguistico in locale), PARAGRAFO PER PARAGRAFO.

Uso:
  python traduci_libro_llm.py <libro> <libro_it> [capitolo ...] [--titoli NOME] [--rigenera]

Esempio (dalla cartella pipeline, con l'ambiente .venv):
  ..\\.venv\\Scripts\\python.exe traduci_libro_llm.py whyte whyte-it-gemma 07-food --titoli whyte-it

Differenze rispetto a traduci_libro.py (Opus-MT, una frase alla volta):
  - ogni PARAGRAFO viene tradotto intero, quindi il modello vede il contesto (e' il limite principale di Opus-MT);
  - poi il paragrafo tradotto viene diviso in frasi italiane con pysbd (come dividi_frasi.py), quindi il numero
    di frasi per paragrafo puo' cambiare rispetto all'inglese. Il formato del file resta quello del generatore.
  - il confronto (output/<libro_it>/confronto/<capitolo>.txt) e' per paragrafo, non per frase.

Come gira:
  - avvia llama-server (llama.cpp) SOLO sul tuo PC (127.0.0.1), carica il modello TranslateGemma 12B
    (quantizzazione Q4_K_S) e lo ferma alla fine, anche in caso di errore;
  - usa lo stesso blocco di XTTS (voci.blocca_xtts): non puo' girare insieme a XTTS, e viceversa;
  - ogni paragrafo tradotto viene salvato subito in output/<libro_it>/_lavoro/<capitolo>.json: se il server si
    ferma (errore CUDA...) viene riavviato da solo (fino a 3 volte per paragrafo) e si riparte da li';
    se si interrompe tutto basta rilanciare lo stesso comando.
  - i titoli dei capitoli vengono da pipeline/libri/<NOME>.json (di default NOME = libro_it).

Limiti da conoscere (e' una traduzione automatica, non umana): possibili errori di senso, stile non letterario,
unita' di misura non convertite, errori del riconoscimento del testo (OCR) che si portano dietro.
Uso PERSONALE: il testo tradotto resta in output/ (fuori da Git, Drive e OneDrive), non va pubblicato.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pysbd
from num2words import num2words

import traduci_libro as tl
import voci

RADICE = voci.RADICE
LLAMA = RADICE / "modelli" / "llama-cpp-b12284" / "llama-server.exe"
MODELLO = RADICE / "modelli" / "translategemma-12b-gguf" / "translategemma-12b-it-Q4_K_S.gguf"
NOME_MODELLO = "TranslateGemma 12B (Q4_K_S, llama.cpp b12284)"
PORTA = 8089
CONTESTO = 4096          # token: paragrafo in ingresso + traduzione in uscita
TENTATIVI = 3            # per ogni paragrafo, riavviando il server se serve
MAX_TOKEN_USCITA = 1600


# ------------------------------------------------------------------ il server llama.cpp
class Server:
    def __init__(self, log):
        self.log = Path(log)
        self.proc = None
        self.file_log = None

    def avvia(self):
        self.ferma()
        voci.attendi_scheda_fresca()
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.file_log = open(self.log, "ab")
        comando = [str(LLAMA), "-m", str(MODELLO), "--host", "127.0.0.1", "--port", str(PORTA),
                   "-c", str(CONTESTO), "-np", "1", "--jinja"]
        print("Avvio llama-server (carico il modello, puo' volerci un minuto)...", flush=True)
        self.proc = subprocess.Popen(comando, stdout=self.file_log, stderr=subprocess.STDOUT, cwd=str(LLAMA.parent))
        t0 = time.time()
        while time.time() - t0 < 600:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server si e' chiuso (codice {self.proc.returncode}): vedi {self.log}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/health", timeout=5) as r:
                    if r.status == 200:
                        print(f"  server pronto dopo {time.time() - t0:.0f} s", flush=True)
                        return
            except (urllib.error.URLError, OSError):
                pass                      # ancora in caricamento (risponde 503 finche' non e' pronto)
            time.sleep(3)
        raise RuntimeError("llama-server non e' pronto dopo 10 minuti")

    def ferma(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None
        if self.file_log:
            self.file_log.close()
            self.file_log = None


# ------------------------------------------------------------------ la richiesta al modello
_template = None   # il template delle istruzioni del modello, letto una volta dal server


def carica_template():
    """Legge dal server il template delle istruzioni del modello (/props) e lo prepara con jinja2.
    NOTA (provato l'11/11/2026): l'endpoint /v1/chat/completions di llama-server scarta i campi source_lang_code e
    target_lang_code, e il modello rispondeva in inglese. Quindi il testo delle istruzioni lo costruiamo noi con lo
    STESSO template del modello e lo mandiamo a /completion."""
    global _template
    if _template is None:
        import jinja2
        from jinja2.sandbox import ImmutableSandboxedEnvironment
        with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/props", timeout=30) as r:
            tpl = json.load(r)["chat_template"]
        env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)

        def errore(messaggio):
            raise jinja2.exceptions.TemplateError(messaggio)
        env.globals["raise_exception"] = errore
        _template = env.from_string(tpl)
    return _template


def costruisci_prompt(testo):
    """Il testo delle istruzioni per tradurre 'testo' da inglese a italiano. Il BOS lo aggiunge il server."""
    messaggi = [{"role": "user", "content": [{
        "type": "text", "source_lang_code": "en", "target_lang_code": "it", "text": testo}]}]
    return carica_template().render(messages=messaggi, add_generation_prompt=True, bos_token="", eos_token="<eos>")


def chiedi(testo):
    corpo = {
        "prompt": costruisci_prompt(testo),
        "temperature": 0,            # niente casualita': stessa traduzione a ogni prova
        "n_predict": MAX_TOKEN_USCITA,
        "cache_prompt": False,
        "stop": ["<end_of_turn>"],
    }
    richiesta = urllib.request.Request(
        f"http://127.0.0.1:{PORTA}/completion",
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(richiesta, timeout=900) as r:
        dati = json.load(r)
    if dati.get("stop_type") == "limit" or dati.get("stopped_limit"):
        raise ValueError("risposta troncata dal limite di lunghezza")
    return dati["content"].strip()


def traduci_paragrafo(server, testo):
    """Traduce un paragrafo. Se il server non risponde lo riavvia e riprova."""
    for tentativo in range(1, TENTATIVI + 1):
        try:
            return chiedi(testo)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            print(f"    problema ({type(e).__name__}: {e}), tentativo {tentativo}/{TENTATIVI}", flush=True)
            if tentativo == TENTATIVI:
                raise
            server.avvia()


# ------------------------------------------------------------------ lavoro su disco e controlli
def chiave(testo):
    return hashlib.sha1(testo.encode("utf-8")).hexdigest()[:16]


def carica_lavoro(percorso):
    return json.loads(percorso.read_text(encoding="utf-8")) if percorso.exists() else {}


def salva_lavoro(percorso, lavoro):
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(lavoro, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, percorso)


def motivo_sospetto(originale, tradotto):
    """None se la traduzione di un paragrafo sembra a posto, altrimenti il motivo del sospetto."""
    # attenzione: "Ecco ..." da solo e' italiano normale ("Ecco una meravigliosa invenzione"): cerco solo le formule
    # con cui un modello introduce di solito la propria traduzione
    if re.match(r"\s*(ecco (qui )?(la|una) traduzione|here is (the |a )?translation|traduzione:|translation:)",
                tradotto, flags=re.IGNORECASE):
        return "il modello ha aggiunto un commento davanti alla traduzione"
    return tl.motivo_sospetto(originale, tradotto)


# ------------------------------------------------------------------ capitolo
def traduci_capitolo(server, segmentatore, libro, libro_it, etichetta, titoli, rigenera):
    origine = RADICE / "output" / libro / "frasi" / f"{etichetta}.json"
    uscita = RADICE / "output" / libro_it / "frasi" / f"{etichetta}.json"
    if uscita.exists() and not rigenera:
        print(f"{etichetta}: gia' tradotto, salto (usa --rigenera per rifarlo)", flush=True)
        return
    dati = json.loads(origine.read_text(encoding="utf-8"))
    file_lavoro = RADICE / "output" / libro_it / "_lavoro" / f"{etichetta}.json"
    lavoro = {} if rigenera else carica_lavoro(file_lavoro)
    totale = len(dati["blocchi"])
    print(f"{etichetta}: {totale} paragrafi ({len(lavoro)} gia' tradotti)", flush=True)
    t0 = time.time()

    blocchi, righe, sospetti = [], [], 0
    for n, b in enumerate(dati["blocchi"], 1):
        inglese = " ".join(b["frasi"])
        k = chiave(inglese)
        if k not in lavoro:
            if n % 4 == 0:
                voci.attendi_scheda_fresca()      # protezione: se la scheda e' troppo calda aspetta che scenda
            t1 = time.time()
            lavoro[k] = traduci_paragrafo(server, inglese)
            salva_lavoro(file_lavoro, lavoro)
            print(f"  [{n:3}/{totale}] {len(inglese):4} car. in {time.time() - t1:5.1f} s", flush=True)
        italiano = lavoro[k]
        if b["tipo"] == "paragrafo":
            frasi = [f.strip() for f in segmentatore.segment(italiano) if f.strip()]
        else:
            frasi = [italiano]
        blocchi.append({"tipo": b["tipo"], "frasi": frasi})
        motivo = motivo_sospetto(inglese, italiano)
        sospetti += bool(motivo)
        righe.append(f"{'!' if motivo else ' '} {n:3}  EN: {inglese}\n      IT: {italiano}"
                     + (f"\n      ({motivo})" if motivo else "") + "\n")

    # titolo e annuncio (titoli scritti a mano in pipeline/libri/<NOME>.json)
    titolo_it = titoli.get(etichetta)
    if not titolo_it:
        titolo_it = traduci_paragrafo(server, dati["titolo"]).rstrip(".")
        print(f"  titolo non scritto a mano, tradotto dalla macchina: '{titolo_it}' (controllalo)", flush=True)
    if dati["annuncio"].startswith("Chapter"):
        annuncio = f"Capitolo {num2words(dati['capitolo'], lang='it')}. {titolo_it}."
    else:
        annuncio = f"{titolo_it}."

    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(json.dumps({"capitolo": dati["capitolo"], "titolo": titolo_it, "annuncio": annuncio,
                                  "blocchi": blocchi, "traduzione": NOME_MODELLO}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    confronto = RADICE / "output" / libro_it / "confronto" / f"{etichetta}.txt"
    confronto.parent.mkdir(parents=True, exist_ok=True)
    confronto.write_text("\n".join(righe), encoding="utf-8")
    print(f"  fatto in {time.time() - t0:.0f} s: {uscita.relative_to(RADICE)}  "
          f"({sospetti} paragrafi sospetti, vedi {confronto.relative_to(RADICE)})", flush=True)


def main():
    argv = sys.argv[1:]
    titoli_nome = None
    if "--titoli" in argv:
        i = argv.index("--titoli")
        titoli_nome = argv[i + 1]
        del argv[i:i + 2]
    flag = {a for a in argv if a.startswith("--")}
    argv = [a for a in argv if not a.startswith("--")]
    if len(argv) < 2:
        sys.exit(__doc__)
    libro, libro_it, capitoli = argv[0], argv[1], argv[2:]
    if not capitoli:
        capitoli = sorted(p.stem for p in (RADICE / "output" / libro / "frasi").glob("*.json")
                          if not p.stem.startswith("_"))
    for percorso in (LLAMA, MODELLO):
        if not percorso.exists():
            sys.exit(f"Manca il file: {percorso}")
    titoli = tl.carica_titoli(titoli_nome or libro_it)
    segmentatore = pysbd.Segmenter(language="it", clean=False)

    voci.blocca_xtts()        # una sola cosa alla volta sulla scheda (anche se qui non gira XTTS)
    server = Server(RADICE / "output" / libro_it / "llama-server.log")
    try:
        server.avvia()
        for etichetta in capitoli:
            traduci_capitolo(server, segmentatore, libro, libro_it, etichetta, titoli, "--rigenera" in flag)
    finally:
        server.ferma()


if __name__ == "__main__":
    main()
