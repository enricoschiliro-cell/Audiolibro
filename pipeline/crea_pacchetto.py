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


def asterisco(d, cx, cy, raggio, colore, spessore):
    """Il glifo ✻ del tema (otto raggi con le punte tonde), disegnato a mano: non dipende dai caratteri installati."""
    import math
    for k in range(4):
        a = math.pi / 4 * k
        dx, dy = raggio * math.cos(a), raggio * math.sin(a)
        d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=colore, width=spessore)
        for segno in (-1, 1):
            x, y = cx + segno * dx, cy + segno * dy
            d.ellipse([x - spessore / 2, y - spessore / 2, x + spessore / 2, y + spessore / 2], fill=colore)


def crea_copertina(percorso, meta):
    """Copertina nello stile "Claude Code Retro" (il design system dell'utente: nero caldo, arancione Claude, monospace,
    scanline, barra di stato) con Caramella che legge. Nessuna immagine del libro: titolo, autore, voce.
    Lo sprite di Caramella (24x24) e' in pipeline/risorse/caramella-legge.png; se manca, la copertina esce senza."""
    from PIL import Image, ImageDraw, ImageFilter
    S = 1400
    M = 90
    FONDO, SCURO, BORDO = "#141413", "#0f0f0e", "#33312d"
    TESTO, TENUE, ARANCIO, AMBRA = "#e8e6dc", "#8f8b81", "#d97757", "#d4a27f"
    mono_b = [r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\cascadiamono.ttf"]
    mono = [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cascadiamono.ttf"]

    img = Image.new("RGBA", (S, S), FONDO)
    d = ImageDraw.Draw(img)

    # In alto: il glifo ✻ e l'etichetta (come un tag del tema: ambra, bordo sottile, fondo scurissimo)
    asterisco(d, M + 45, M + 45, 42, ARANCIO, 16)
    f_tag = trova_font(mono, 40)
    testo_tag = meta.get("copertina_sottotitolo", "Audiolibro").lower()
    larg_tag = d.textlength(testo_tag, font=f_tag)
    x0, y0 = M + 130, M + 12
    d.rounded_rectangle([x0, y0, x0 + larg_tag + 40, y0 + 66], radius=8, fill="#1b1815", outline="#6b5a49", width=3)
    d.text((x0 + 20, y0 + 33), testo_tag, font=f_tag, fill=AMBRA, anchor="lm")

    # Titolo: monospace grassetto arancione, con l'alone dei titoli del tema
    f_titolo = trova_font(mono_b, 118)
    righe = a_capo(d, meta["titolo"], f_titolo, S - 2 * M)
    y = 330
    alone = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    da = ImageDraw.Draw(alone)
    for riga in righe:
        da.text((M, y), riga, font=f_titolo, fill=ARANCIO, anchor="ls")
        y += 140
    alone = alone.filter(ImageFilter.GaussianBlur(16))
    alone.putalpha(alone.getchannel("A").point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(img, alone)
    d = ImageDraw.Draw(img)
    y = 330
    for riga in righe:
        d.text((M, y), riga, font=f_titolo, fill=ARANCIO, anchor="ls")
        y += 140
    y_fine = y - 140
    d.line([(M, y_fine + 48), (S - M, y_fine + 48)], fill=BORDO, width=3)
    d.text((M, y_fine + 120), meta["autore"], font=trova_font(mono, 56), fill=TESTO, anchor="ls")

    # In basso: la barra di stato (✻ arancione, voci separate da una linea sottile)
    H = 112
    d.rectangle([0, S - H, S, S], fill=SCURO)
    d.line([(0, S - H), (S, S - H)], fill=BORDO, width=3)
    asterisco(d, M + 4, S - H / 2, 15, ARANCIO, 6)
    f_stato = trova_font(mono, 34)
    voci_stato = [v for v in ("voce: " + meta.get("voce_nome", ""), meta.get("voce_motore", ""), "uso personale") if v and not v.endswith(": ")]
    x = M + 40
    for i, v in enumerate(voci_stato):
        if i:
            d.line([(x, S - H + 30), (x, S - 30)], fill=BORDO, width=3)
            x += 24
        d.text((x, S - H / 2), v, font=f_stato, fill=TENUE, anchor="lm")
        x += d.textlength(v, font=f_stato) + 24

    # Caramella che legge, ingrandita x14 senza sfumature, con la sua ombra, e la nuvoletta
    sprite_png = Path(__file__).resolve().parent / "risorse" / "caramella-legge.png"
    if sprite_png.is_file():
        k = 18
        sprite = Image.open(sprite_png).convert("RGBA").resize((24 * k, 24 * k), Image.NEAREST)
        sx, sy = S - M - 24 * k + 70, S - H - 24 * k   # il corpo (colonne 4-19) finisce sul margine destro
        d.rectangle([sx + 6 * k, sy + 23 * k, sx + 18 * k - 1, sy + 24 * k - 1], fill="#4a463f")
        img.alpha_composite(sprite, (sx, sy))
        f_nuv = trova_font(mono, 40)
        t = "buon ascolto…"
        lw = d.textlength(t, font=f_nuv)
        bx1 = sx + 20 * k
        bx0, by0 = bx1 - lw - 44, sy + 6 * k - 96
        d.rectangle([bx0, by0, bx1, by0 + 78], fill=SCURO, outline=ARANCIO, width=4)
        d.text((bx0 + 22, by0 + 39), t, font=f_nuv, fill=TESTO, anchor="lm")

    # Scanline del CRT: una riga scura da 1 px ogni 3 px su tutto
    righe_cr = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(righe_cr)
    for yy in range(2, S, 3):
        dr.line([(0, yy), (S, yy)], fill=(0, 0, 0, 26), width=1)
    img = Image.alpha_composite(img, righe_cr)
    img.convert("RGB").save(percorso, "JPEG", quality=92)


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
