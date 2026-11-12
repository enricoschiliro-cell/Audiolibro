# Formato del pacchetto del libro (versione 1)

Definito il 12/11/2026 da `crea_pacchetto.py`. L'app (`docs/app/`, in lavorazione, non ancora provata su iPhone) legge questo formato: questo file e' il contratto da rispettare. Per provare l'app senza un libro vero c'e' `crea_pacchetto_demo.py`, che scrive un pacchetto dimostrativo (3 capitoli di "bip", estensione `.dat`) con lo stesso formato.
Un pacchetto contiene un libro protetto da diritto d'autore (audio + testo tradotto): **uso personale, mai online** (la cartella `output/` e i file `*.zip` sono nel `.gitignore`).

## File prodotti (in `output/<libro>/pacchetti/`)
- `<autore>-<titolo>-<lingua>.zip`: il pacchetto per l'app (da importare dall'app File dell'iPhone).
- `<autore>-<titolo>-<lingua>.m4b`: un solo file con i capitoli (AAC mono), copertina e dati, per le app di audiolibri.
- `cover.jpg`: la copertina (per ora solo testo, 1400x1400; da sostituire con la grafica definitiva).

## Contenuto dello zip
```
manifest.json
cover.jpg
capitoli/<id-capitolo>.mp3     audio del capitolo (MP3 mono, frasi separate da pause decise da noi)
capitoli/<id-capitolo>.json    tempi di ogni frase (vedi sotto)
```
Gli MP3 sono salvati senza ulteriore compressione (STORED); i JSON sono compressi (DEFLATED).

## manifest.json
```
formato: "audiolibro-pacchetto"     versione: 1 (numero intero: l'app deve rifiutare versioni piu' nuove di quelle che conosce)
creato: data e ora ISO
libro:   { id, titolo, autore, lingua }
voce:    { nome, motore, licenza }              traduzione: testo libero      avviso: testo libero
copertina: "cover.jpg"                          durata: secondi totali (somma dei capitoli)
capitoli: [ { id, numero, titolo, titolo_completo, audio, tempi, durata, frasi,
              byte_audio, sha256_audio, byte_tempi, sha256_tempi } ]   (nell'ordine di lettura)
```
- `numero`: numero del capitolo nel libro, 0 per prefazione/introduzione senza numero. `titolo_completo` = "Capitolo N: titolo" oppure il solo titolo.
- `durata` e' misurata sull'MP3 (ffprobe), in secondi. `frasi` conta i segmenti di tipo `frase` e `sottotitolo`.
- `sha256_*`: l'app puo' controllare che un file importato non sia danneggiato.

## capitoli/<id>.json
```
versione: 1   capitolo: id   numero   titolo   durata
segmenti: [ { tipo, testo, inizio, fine, pausa } ]
```
- `tipo`: `annuncio` (es. "Capitolo quattro. Il cibo."), `sottotitolo`, `frase`.
- `inizio` e `fine` in secondi dall'inizio dell'MP3 del capitolo; `pausa` = secondi di silenzio dopo la frase (1,0 s dopo l'ultima frase di un paragrafo, 0,45 s tra frasi dello stesso paragrafo, 0,9 dopo un sottotitolo, 1,3 dopo l'annuncio, 1,5 in fondo).
- I segmenti sono in ordine e non si sovrappongono. Il testo e' quello letto: serve per far scorrere il testo in sincrono con la voce.
- I tempi sono misurati sull'audio prima della codifica MP3; l'MP3 puo' differire di pochi centesimi di secondo (non verificato frase per frase).

## M4B
AAC-LC mono 64 kbit/s (ricodificato dagli MP3: una piccola perdita di qualita', per la voce poco udibile), capitoli con titolo "Capitolo N: titolo",
copertina, titolo e autore nei dati, genere "Audiobook". Prodotto con ffmpeg (`-f ipod`, estensione .m4b).
**Non e' stato provato su un'app dell'iPhone**: come le diverse app leggono i capitoli di un M4B va verificato con quella che scegli.
