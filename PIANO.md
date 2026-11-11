# Piano del progetto Audiolibro

Documento di riferimento: decisioni prese, cosa abbiamo scoperto, cosa resta da fare.

## Decisioni prese
- **App**: PWA su GitHub Pages (`docs/`), HTML/CSS/JS semplici, **niente Tailwind**.
- **Libri**: non vanno mai online (diritti d'autore). Il PC crea un pacchetto per libro, che si importa nell'app dall'app File dell'iPhone (passando da OneDrive o Google Drive, cartella fuori dal vault).
- **In più**: per ogni libro il PC crea anche un file **M4B con capitoli**, da usare in un'app gratuita per audiolibri quando serve controllare tutto dalle cuffie.
- **Progetto**: in `C:\Users\enric\Progetti\audiolibro` (fuori da Drive e OneDrive).
- **Commit** con email anonima di GitHub, non il Gmail.

## Fase 1: risultati della prova su iPhone (Chrome, app sulla schermata Home)
Funziona:
- audio in background a schermo bloccato;
- titolo e tasti nella schermata di blocco (Media Session);
- pausa e ripresa dalle cuffie se la pausa dura pochi secondi;
- ±10 secondi nell'app, funzionamento offline, ripresa dal punto salvato.

Non funziona (limite di iOS per le web app):
- dopo una pausa di più di qualche secondo a schermo bloccato, la ripresa da schermata di blocco o cuffie non parte.
- Provate senza successo: audio in memoria (B), tasti gestiti da iOS (C), pausa in muto (D), audio di silenzio (E: l'app resta sveglia ma il libro non riparte), velocità zero (F), volume zero con Web Audio (G: l'audio si ferma appena si blocca lo schermo).
- Dal registro: con il libro in pausa iOS congela la web app e i comandi arrivano solo quando la si riapre.

Conseguenza per l'app: pausa normale. L'audio del capitolo va caricato intero in memoria (blob), senza passare dal service worker. Niente trucchi.

## Fase 2: procedura sul PC (prossima)
1. **Estrazione** con PyMuPDF: testo con posizione e dimensione del carattere.
2. **Pulizia**: tolgo intestazioni e piè di pagina (righe ripetute), numeri di pagina, note, didascalie delle foto (Whyte è una scansione con OCR: ci saranno errori da correggere).
3. **Capitoli**: riconosciuti dai titoli. Testo pulito salvato in Markdown per capitolo, da controllare.
4. **Frasi**: divisione in frasi (inglese e italiano).
5. **Voce**: audio generato frase per frase, poi unito con pause decise da me (frase, paragrafo, capitolo). Così i tempi di ogni frase si conoscono senza strumenti di allineamento.
6. **Uscita per capitolo**: audio leggero (mono, circa 48 kbps) + file JSON con i tempi di ogni frase.
7. **Pacchetti**: zip per l'app (manifest, copertina, capitoli, tempi) + M4B con capitoli e copertina.
8. **Second brain**: aggiorno la nota del libro nel vault con i riassunti per capitolo (e la traduzione in italiano se il libro è in inglese).

Da installare (chiedendo prima): ffmpeg, Python 3.12 accanto al 3.15, PyMuPDF, poi PyTorch per la scheda video (alcuni GB) e i modelli di voce.

Voci da confrontare: Kokoro per l'inglese; per l'italiano XTTS-v2, Chatterbox multilingue, Piper, Kokoro italiano. Prima della scelta verifico online lo stato attuale dei modelli.

## Fasi successive
3. Lettore di base (libreria, capitoli, testo sincronizzato, importazione dei pacchetti).
4. Funzioni: ripresa con scelta, annuncio del capitolo successivo, segnalibri con nota, statistiche.
5. Grafica "Claude Code Retro" e Caramella lettrice (riusando gli sprite del plugin tizzo-mascotte, con un piccolo libro aggiunto).
6. Ivanhoe in italiano, con narratore e voci per i personaggi.
