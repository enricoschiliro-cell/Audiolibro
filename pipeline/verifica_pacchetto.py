"""Controlla i pacchetti prodotti da crea_pacchetto.py (sola lettura).

Uso: python verifica_pacchetto.py <libro>
Controlla:
  ZIP: integrita' dello zip, manifest valido, ogni file presente, dimensione e firma SHA-256 di ogni file, tempi coerenti
       (le frasi sono in ordine, non si sovrappongono, l'ultima finisce entro la durata del capitolo).
  M4B: ffprobe (durata, numero e orari dei capitoli, flusso audio, copertina) e confronto con la somma dei capitoli.
Stampa OK/PROBLEMA per ogni controllo e un riepilogo finale. Non modifica niente."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voci  # noqa: E402

problemi = []


def esito(ok, testo):
    print(("OK       " if ok else "PROBLEMA ") + testo)
    if not ok:
        problemi.append(testo)


def main():
    libro = sys.argv[1]
    cartella = voci.RADICE / "output" / libro / "pacchetti"
    zips, m4bs = sorted(cartella.glob("*.zip")), sorted(cartella.glob("*.m4b"))
    esito(len(zips) == 1, f"trovato 1 zip ({[z.name for z in zips]})")
    esito(len(m4bs) == 1, f"trovato 1 m4b ({[m.name for m in m4bs]})")

    if zips:
        with zipfile.ZipFile(zips[0]) as z:
            esito(z.testzip() is None, "lo zip non e' danneggiato (testzip)")
            nomi = set(z.namelist())
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            esito(manifest.get("formato") == "audiolibro-pacchetto", f"manifest: formato {manifest.get('formato')!r}, versione {manifest.get('versione')}")
            esito("cover.jpg" in nomi, "c'e' la copertina")
            somma = 0.0
            for c in manifest["capitoli"]:
                a, t = c["audio"], c["tempi"]
                if a not in nomi or t not in nomi:
                    esito(False, f"{c['id']}: manca {a if a not in nomi else t}")
                    continue
                dati_mp3, dati_json = z.read(a), z.read(t)
                firma_ok = hashlib.sha256(dati_mp3).hexdigest() == c["sha256_audio"] and hashlib.sha256(dati_json).hexdigest() == c["sha256_tempi"]
                dim_ok = len(dati_mp3) == c["byte_audio"] and len(dati_json) == c["byte_tempi"]
                tempi = json.loads(dati_json.decode("utf-8"))
                seg = tempi["segmenti"]
                ordine_ok = all(seg[i]["fine"] <= seg[i + 1]["inizio"] + 1e-6 and seg[i]["inizio"] < seg[i]["fine"] for i in range(len(seg) - 1))
                fine_ok = seg[-1]["fine"] <= c["durata"] + 0.5
                n_frasi = sum(1 for s in seg if s["tipo"] in ("frase", "sottotitolo"))
                esito(firma_ok and dim_ok and ordine_ok and fine_ok and n_frasi == c["frasi"],
                      f"{c['id']:34} firma/dimensione {'ok' if firma_ok and dim_ok else 'NO'}, tempi in ordine {'ok' if ordine_ok else 'NO'}, "
                      f"ultima frase a {seg[-1]['fine']:.1f} s su {c['durata']:.1f} s, {n_frasi} frasi")
                somma += c["durata"]
            esito(abs(somma - manifest["durata"]) < 0.01, f"somma delle durate dei capitoli {somma:.1f} s = durata nel manifest {manifest['durata']:.1f} s")
            print(f"         zip: {zips[0].stat().st_size / 1e6:.1f} MB, {len(manifest['capitoli'])} capitoli")
    else:
        manifest = None

    if m4bs:
        ffprobe = str(Path(voci.trova_ffmpeg()).with_name("ffprobe.exe"))
        r = json.loads(subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", str(m4bs[0])],
                                      capture_output=True, text=True, encoding="utf-8", check=True).stdout)   # utf-8: i titoli hanno accenti
        audio = [s for s in r["streams"] if s["codec_type"] == "audio"]
        copertina = [s for s in r["streams"] if s["codec_type"] == "video"]
        durata = float(r["format"]["duration"])
        capitoli = r["chapters"]
        esito(len(audio) == 1 and audio[0]["codec_name"] == "aac", f"m4b: 1 flusso audio {audio[0]['codec_name'] if audio else '-'}, {audio[0].get('channels') if audio else '-'} canale, "
              f"{audio[0].get('sample_rate') if audio else '-'} Hz, {int(audio[0].get('bit_rate', 0)) // 1000 if audio else 0} kbit/s")
        esito(len(copertina) == 1, "m4b: c'e' la copertina (flusso video attached_pic)")
        if manifest:
            esito(len(capitoli) == len(manifest["capitoli"]), f"m4b: {len(capitoli)} capitoli (attesi {len(manifest['capitoli'])})")
            esito(abs(durata - manifest["durata"]) < 1.0, f"m4b: durata {durata:.1f} s contro {manifest['durata']:.1f} s dei capitoli (differenza {durata - manifest['durata']:+.2f} s)")
            # il capitolo i del M4B deve iniziare dove finisce la somma dei capitoli precedenti (tolleranza 0,5 s)
            t, scarto_max = 0.0, 0.0
            for cm, cz in zip(capitoli, manifest["capitoli"]):
                scarto_max = max(scarto_max, abs(float(cm["start_time"]) - t))
                t += cz["durata"]
            esito(scarto_max < 0.5, f"m4b: l'inizio di ogni capitolo coincide con il previsto (scarto massimo {scarto_max:.3f} s)")
        for cm in capitoli:
            print(f"         {float(cm['start_time']) / 60:7.2f} min  {cm.get('tags', {}).get('title', '?')}")
        print(f"         m4b: {m4bs[0].stat().st_size / 1e6:.1f} MB, durata {durata / 60:.1f} min")
        tag = r["format"].get("tags", {})
        esito(bool(tag.get("title")) and bool(tag.get("artist")), f"m4b: titolo/autore nei dati ({tag.get('title')!r}, {tag.get('artist')!r})")
        # prova di decodifica completa (senza salvare niente): trova file rovinati
        dec = subprocess.run([voci.trova_ffmpeg(), "-v", "error", "-i", str(m4bs[0]), "-map", "0:a", "-f", "null", "-"], capture_output=True, text=True)
        esito(dec.returncode == 0 and not dec.stderr.strip(), "m4b: si decodifica tutto senza errori" + (f" ({dec.stderr.strip()[:120]})" if dec.stderr.strip() else ""))

    print(f"\nRiepilogo: {len(problemi)} problemi")
    sys.exit(1 if problemi else 0)


if __name__ == "__main__":
    main()
