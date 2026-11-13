"""Crea i pacchetti di un libro gia' generato: lo ZIP per l'app e il file M4B con i capitoli.

Uso (con l'ambiente .venv-xtts, dove c'e' Pillow per la copertina):
    python crea_pacchetto.py <libro> <voce> [--solo-zip] [--solo-m4b] [--bitrate 64]
    esempio: python crea_pacchetto.py whyte-it-gemma xtts:it:Filip_Traverse

Legge, per ogni capitolo, output/<libro>/audio/<capitolo>__<etichetta voce>.mp3 e .json (tempi delle frasi) e i dati del libro
da pipeline/libri/<libro>.meta.json. Scrive in output/<libro>/pacchetti/:
  - <slug>.zip   per l'app: manifest.json, cover.jpg, capitoli/<capitolo>.mp3, capitoli/<capitolo>.json (formato: FORMATO_PACCHETTO.md)
  - <slug>.m4b   un solo file con i capitoli (AAC mono), la copertina e i dati, per le app di audiolibri
Poi controlla i file prodotti (firma di ogni file, durate, capitoli) e stampa un riepilogo.
Non usa la scheda video. Il libro non va mai online: la cartella output/ e' fuori da Git, e il pacchetto contiene il testo
tradotto e l'audio di un libro protetto da diritto d'autore (uso personale).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voci  # noqa: E402

VERSIONE_FORMATO = 1


def etichetta_voce(voce):
    """Nome del file audio, come lo decide genera_capitolo.py (<capitolo>__<etichetta>)."""
    motore, *resto = voce.split(":")
    if motore == "xtts" and len(resto) == 2:
        return "xtts-" + resto[1].replace(" ", "_")
    if motore == "piper" and len(resto) == 1:
        return "piper-" + resto[0]
    sys.exit(f"Voce non valida: {voce!r}")


def slug(testo):
    return re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def durata_ffprobe(path):
    ffprobe = str(Path(voci.trova_ffmpeg()).with_name("ffprobe.exe"))
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def trova_font(nomi, misura):
    from PIL import ImageFont
    for nome in nomi:
        try:
            return ImageFont.truetype(nome, misura)
        except OSError:
            continue
    return ImageFont.load_default(misura)


def a_capo(disegno, testo, font, larghezza_max):
    """Divide un testo in righe che stanno nella larghezza data."""
    righe, corrente = [], ""
    for parola in testo.split():
        prova = (corrente + " " + parola).strip()
        if disegno.textlength(prova, font=font) <= larghezza_max or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = parola
    return righe + [corrente]


def crea_copertina(percorso, meta):
    """Copertina semplice (solo testo, nessuna immagine del libro): titolo, autore, voce. Da sostituire con la grafica definitiva."""
    from PIL import Image, ImageDraw
    S = 1400
    crema, oro = "#f2ead8", "#c9a24d"
    img = Image.new("RGB", (S, S), meta.get("copertina_colore", "#22403d"))
    d = ImageDraw.Draw(img)
    d.rectangle([60, 60, S - 60, S - 60], outline=oro, width=6)
    serif = [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\timesbd.ttf"]
    serif_norm = [r"C:\Windows\Fonts\georgia.ttf", r"C:\Windows\Fonts\times.ttf"]
    sans = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]

    def centrato(testo, y, font, colore):
        d.text(((S - d.textlength(testo, font=font)) / 2, y), testo, font=font, fill=colore)

    centrato(meta.get("copertina_sottotitolo", "Audiolibro").upper(), 150, trova_font(sans, 46), oro)
    font_t = trova_font(serif, 130)
    y = 330
    for riga in a_capo(d, meta["titolo"], font_t, S - 260):
        centrato(riga, y, font_t, crema)
        y += 160
    d.line([S / 2 - 160, y + 40, S / 2 + 160, y + 40], fill=oro, width=5)
    centrato(meta["autore"], y + 90, trova_font(serif_norm, 64), crema)
    centrato("Voce: " + meta.get("voce_nome", ""), S - 250, trova_font(sans, 44), oro)
    img.save(percorso, "JPEG", quality=90)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("libro")
    ap.add_argument("voce", help="xtts:<lingua>:<Nome_Voce> oppure piper:<modello>")
    ap.add_argument("--solo-zip", action="store_true")
    ap.add_argument("--solo-m4b", action="store_true")
    ap.add_argument("--bitrate", type=int, default=64, help="kbit/s dell'AAC mono del M4B (default 64)")
    args = ap.parse_args()

    radice = voci.RADICE / "output" / args.libro
    meta_path = voci.RADICE / "pipeline" / "libri" / f"{args.libro}.meta.json"
    if not meta_path.exists():
        sys.exit(f"Manca {meta_path} (titolo, autore, ...)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    titoli_file = voci.RADICE / "pipeline" / "libri" / meta.get("titoli_capitoli", "")
    titoli = json.loads(titoli_file.read_text(encoding="utf-8")).get("titoli", {}) if titoli_file.is_file() else {}

    etichetta = etichetta_voce(args.voce)
    cap_ids = sorted(p.name.split("__")[0] for p in (radice / "audio").glob(f"*__{etichetta}.mp3"))
    if not cap_ids:
        sys.exit("Non trovo nessun capitolo con questa voce")
    uscita = radice / "pacchetti"
    uscita.mkdir(exist_ok=True)
    nome = f"{slug(meta['autore'].split()[-1])}-{slug(meta['titolo'])}-{meta['lingua']}"
    print(f"{len(cap_ids)} capitoli di {args.libro}; uscita in {uscita}")

    # ---- dati di ogni capitolo
    capitoli = []
    for cid in cap_ids:
        base = radice / "audio" / f"{cid}__{etichetta}"
        tempi = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        frasi_path = radice / "frasi" / f"{cid}.json"
        numero = json.loads(frasi_path.read_text(encoding="utf-8")).get("capitolo", 0) if frasi_path.exists() else 0
        titolo = titoli.get(cid) or tempi.get("titolo") or cid
        capitoli.append({"id": cid, "numero": numero if isinstance(numero, int) else 0, "titolo": titolo,
                         "mp3": base.with_suffix(".mp3"), "tempi": tempi, "durata": durata_ffprobe(base.with_suffix(".mp3"))})
    durata_totale = sum(c["durata"] for c in capitoli)

    def titolo_capitolo(c):
        return f"Capitolo {c['numero']}: {c['titolo']}" if c["numero"] else c["titolo"]

    copertina = uscita / "cover.jpg"
    crea_copertina(copertina, meta)

    # ---- ZIP per l'app
    if not args.solo_m4b:
        zip_path = uscita / f"{nome}.zip"
        manifest = {
            "formato": "audiolibro-pacchetto", "versione": VERSIONE_FORMATO,
            "creato": datetime.now().isoformat(timespec="seconds"),
            "libro": {"id": args.libro, "titolo": meta["titolo"], "autore": meta["autore"], "lingua": meta["lingua"]},
            "voce": {"nome": meta.get("voce_nome", ""), "motore": meta.get("voce_motore", ""), "licenza": meta.get("voce_licenza", "")},
            "traduzione": meta.get("traduzione", ""), "avviso": meta.get("avviso", ""),
            "copertina": "cover.jpg", "durata": round(durata_totale, 3), "capitoli": [],
        }
        with zipfile.ZipFile(zip_path, "w") as z:
            for c in capitoli:
                tempi_puliti = {"versione": VERSIONE_FORMATO, "capitolo": c["id"], "numero": c["numero"], "titolo": c["titolo"],
                                "durata": c["durata"], "segmenti": [
                                    {"tipo": s["tipo"], "testo": s["testo"], "inizio": s["inizio"], "fine": s["fine"], "pausa": s["pausa"]}
                                    for s in c["tempi"]["segmenti"]]}
                dati_json = json.dumps(tempi_puliti, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                nome_mp3, nome_json = f"capitoli/{c['id']}.mp3", f"capitoli/{c['id']}.json"
                z.write(c["mp3"], nome_mp3, compress_type=zipfile.ZIP_STORED)      # gli MP3 sono gia' compressi
                z.writestr(zipfile.ZipInfo(nome_json, date_time=datetime.now().timetuple()[:6]), dati_json, compress_type=zipfile.ZIP_DEFLATED)
                manifest["capitoli"].append({
                    "id": c["id"], "numero": c["numero"], "titolo": c["titolo"], "titolo_completo": titolo_capitolo(c),
                    "audio": nome_mp3, "tempi": nome_json, "durata": round(c["durata"], 3),
                    "frasi": sum(1 for s in c["tempi"]["segmenti"] if s["tipo"] in ("frase", "sottotitolo")),
                    "byte_audio": c["mp3"].stat().st_size, "sha256_audio": sha256(c["mp3"]),
                    "byte_tempi": len(dati_json), "sha256_tempi": hashlib.sha256(dati_json).hexdigest()})
            z.write(copertina, "cover.jpg", compress_type=zipfile.ZIP_STORED)
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1), compress_type=zipfile.ZIP_DEFLATED)
        print(f"ZIP: {zip_path.name}  {zip_path.stat().st_size / 1e6:.1f} MB")

    # ---- M4B con capitoli
    if not args.solo_zip:
        m4b_path = uscita / f"{nome}.m4b"
        lista, ffmeta = uscita / "_lista.txt", uscita / "_capitoli.ffmeta"
        lista.write_text("".join("file '" + str(c["mp3"]).replace("\\", "/").replace("'", "'\\''") + "'\n" for c in capitoli), encoding="utf-8")
        righe = [";FFMETADATA1", f"title={meta['titolo']}", f"artist={meta['autore']}", f"album_artist={meta['autore']}",
                 f"album={meta['titolo']}", "genre=Audiobook",
                 f"comment={meta.get('traduzione', '')}. Voce: {meta.get('voce_nome', '')} ({meta.get('voce_motore', '')}). {meta.get('avviso', '')}".strip()]
        t = 0.0
        for c in capitoli:
            inizio, fine = round(t * 1000), round((t + c["durata"]) * 1000)
            righe += ["", "[CHAPTER]", "TIMEBASE=1/1000", f"START={inizio}", f"END={fine}", f"title={titolo_capitolo(c)}"]
            t += c["durata"]
        ffmeta.write_text("\n".join(righe) + "\n", encoding="utf-8")
        comando = [voci.trova_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                   "-i", str(ffmeta), "-i", str(copertina), "-map", "0:a", "-map", "2:v", "-map_metadata", "1",
                   "-c:a", "aac", "-b:a", f"{args.bitrate}k", "-ac", "1", "-c:v", "copy", "-disposition:v:0", "attached_pic",
                   "-movflags", "+faststart", "-f", "ipod", str(m4b_path)]
        print("Creo il M4B (ricodifica in AAC, circa 1-3 minuti)...", flush=True)
        r = subprocess.run(comando, capture_output=True, text=True)
        if r.returncode != 0 or not m4b_path.exists():
            sys.exit("ffmpeg ha fallito:\n" + r.stderr[-1500:])
        lista.unlink(missing_ok=True)
        ffmeta.unlink(missing_ok=True)
        print(f"M4B: {m4b_path.name}  {m4b_path.stat().st_size / 1e6:.1f} MB")

    print(f"Durata totale dei capitoli: {durata_totale / 3600:.2f} ore ({durata_totale:.1f} s)")
    print("Per controllare i file prodotti: python verifica_pacchetto.py", args.libro)


if __name__ == "__main__":
    main()
