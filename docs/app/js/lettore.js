// Il "motore" dell'ascolto: carica i capitoli dall'archivio, li fa suonare, gestisce i tasti della schermata di blocco,
// salva la posizione e passa al capitolo successivo.
//
// Scelte (vedi il piano della Fase 3 e i risultati della prova di fase 1):
//  - pausa NORMALE, niente trucchi (iOS congela le web app in pausa a schermo bloccato);
//  - il capitolo si ascolta da un Blob letto dal database (indirizzo "blob:"), non dal service worker;
//  - un solo elemento <audio> sbloccato dal primo tocco su Play (il secondo serve solo alla variante C della prova);
//  - tasti schermata di blocco: play, pausa, ±10 s e barra di posizione. Niente tasti capitolo.

import { log, errore } from './registro.js';
import * as arch from './archivio.js';
import { inizioFrase } from './util.js';

const SALVA_OGNI_MS = 5000;
const ANTICIPO_B_S = 0.6;   // variante B: cambio quando t >= fine dell'ultima frase + 0,6 s (dentro il silenzio finale di 1,5 s)

const S = {
  libro: null,            // record del libro aperto
  idx: -1,                // indice del capitolo caricato
  tempi: null,            // tempi del capitolo caricato
  url: null,              // indirizzo blob: del capitolo caricato
  blob: null,             // il blob del capitolo caricato (serve per il ripiego in memoria)
  prossimo: null,         // capitolo successivo già pronto: { idx, url, blob, tempi }
  preparando: -1,         // indice del capitolo che sto preparando
  attivo: null,           // elemento <audio> che suona
  riserva: null,          // secondo elemento (variante C)
  variante: 'B',
  cambioFatto: false,     // per non cambiare capitolo due volte
  cambiando: false,       // true mentre sto cambiando la sorgente (dentro usaCapitolo)
  ultimoCambio: -1000,    // quando ho cambiato sorgente l'ultima volta (performance.now())
  ripiego: false,
  seq: 0,                 // per ignorare le risposte vecchie se l'utente tocca due capitoli di seguito
  ui: {},
};
const sbloccati = new WeakSet();   // gli elementi <audio> già avviati da un tocco dell'utente

function totale() { return S.libro ? S.libro.manifest.capitoli.length : 0; }
function capitolo(idx = S.idx) { return S.libro && S.libro.manifest.capitoli[idx]; }

// ---------- Avvio ----------
export function init({ audio, audio2, ui }) {
  S.attivo = audio;
  S.riserva = audio2;
  S.ui = ui;
  try { const v = localStorage.getItem('al.variante'); if (v === 'A' || v === 'B' || v === 'C') S.variante = v; } catch (e) { /* pazienza */ }
  collega(audio);
  collega(audio2);
  impostaMediaSession();
  setInterval(() => { if (staSuonando()) salvaPosizione(); }, SALVA_OGNI_MS);
  document.addEventListener('visibilitychange', () => {
    log(document.hidden ? 'app in background' : 'app di nuovo visibile');
    if (document.hidden) salvaPosizione();
    else S.ui.riallinea && S.ui.riallinea();
  });
  window.addEventListener('pagehide', salvaPosizione);
}

// Eventi di un elemento audio. Quelli del lettore "di riserva" si ignorano (conta solo quello attivo).
function collega(el) {
  const mio = () => el === S.attivo;
  el.addEventListener('timeupdate', () => { if (!mio()) return; aggiornaTempo(); controllaAnticipo(); });
  el.addEventListener('durationchange', () => { if (mio()) aggiornaTempo(); });
  el.addEventListener('loadedmetadata', () => { if (mio()) { aggiornaTempo(); aggiornaPosizioneSessione(); } });
  el.addEventListener('play', () => {
    if (!mio()) return;
    S.ui.stato(true); statoSessione('playing'); aggiornaPosizioneSessione(); log('play');
  });
  el.addEventListener('pause', () => {
    // Gli eventi arrivano DOPO che la funzione che ha cambiato la sorgente è finita: per ignorare un'eventuale "pausa"
    // causata dal cambio uso il tempo trascorso dall'ultimo cambio (300 ms).
    if (!mio() || performance.now() - S.ultimoCambio < 300) return;
    S.ui.stato(false); statoSessione('paused'); salvaPosizione(); log('pausa');
  });
  el.addEventListener('seeked', () => { if (mio()) { aggiornaTempo(); aggiornaPosizioneSessione(); salvaPosizione(); } });
  el.addEventListener('ended', () => { if (mio()) quandoFinito(); });
  el.addEventListener('waiting', () => { if (mio()) log('lettore: in attesa di dati'); });
  el.addEventListener('stalled', () => { if (mio()) log('lettore: dati bloccati'); });
  el.addEventListener('error', () => { if (mio()) erroreAudio(); });
}

function aggiornaTempo() {
  S.ui.tempo(S.attivo.currentTime, S.attivo.duration);
}

// ---------- Caricamento dei capitoli ----------
async function caricaCapitolo(idx) {
  const cap = capitolo(idx);
  const t0 = performance.now();
  const [blob, tempi] = await Promise.all([arch.leggiAudioBlob(S.libro.id, cap.id), arch.leggiTempi(S.libro.id, cap.id)]);
  if (!blob || !tempi) throw new Error('il capitolo «' + (cap.titolo_completo || cap.id) + '» non è nell’archivio (reimporta il libro)');
  log('capitolo ' + cap.id + ' letto dal database in ' + Math.round(performance.now() - t0) + ' ms (' + (blob.size / 1e6).toFixed(1) + ' MB)');
  return { idx, blob, url: URL.createObjectURL(blob), tempi };
}

// Mette un capitolo già caricato nel lettore. Con { scambia: true } (variante C) usa il lettore di riserva, già pronto.
function usaCapitolo(pronto, inizio, riproduci, { scambia = false } = {}) {
  S.cambiando = true;
  S.ultimoCambio = performance.now();
  const urlVecchio = S.url;
  let el = S.attivo;
  if (scambia) {
    const vecchioEl = S.attivo;
    el = S.riserva;
    S.attivo = el;
    S.riserva = vecchioEl;
  }
  S.idx = pronto.idx;
  S.tempi = pronto.tempi;
  S.url = pronto.url;
  S.blob = pronto.blob;
  S.cambioFatto = false;
  S.ripiego = false;
  if (!scambia) el.src = pronto.url;
  S.ui.capitolo(S.idx, capitolo(), S.tempi);
  aggiornaMetadataSessione();

  let promessa = null;
  if (!scambia && inizio > 0) {
    // Su iPhone si può spostare il punto solo dopo aver letto i dati iniziali: aspetto, poi (se serve) parto
    promessa = new Promise((ok, no) => {
      el.addEventListener('loadedmetadata', () => {
        el.currentTime = inizio;
        if (riproduci) { const p = el.play(); if (p) p.then(ok, no); else ok(); } else ok();
      }, { once: true });
    });
  } else {
    if (scambia) el.currentTime = 0;
    if (riproduci) promessa = el.play() || Promise.resolve();
  }
  if (scambia) {
    // Il lettore che ha finito si ferma e viene svuotato (poi riceverà il capitolo ancora successivo)
    const vecchio = S.riserva;
    try { vecchio.pause(); vecchio.removeAttribute('src'); vecchio.load(); } catch (e) { /* pazienza */ }
  }
  S.cambiando = false;
  if (urlVecchio) setTimeout(() => URL.revokeObjectURL(urlVecchio), 3000);   // dopo aver cambiato sorgente
  aggiornaTempo();
  preparaProssimo();
  return promessa;
}

// Dopo aver aperto un capitolo preparo già il successivo (letto dal database e con il suo indirizzo): al cambio non si aspetta niente.
async function preparaProssimo() {
  const i = S.idx + 1;
  if (!S.libro || i >= totale()) { S.prossimo = null; return; }
  if ((S.prossimo && S.prossimo.idx === i) || S.preparando === i) return;
  S.preparando = i;
  const libroId = S.libro.id;
  try {
    const p = await caricaCapitolo(i);
    if (!S.libro || S.libro.id !== libroId || S.idx + 1 !== i) { URL.revokeObjectURL(p.url); return; }   // nel frattempo è cambiato qualcosa
    if (S.prossimo) URL.revokeObjectURL(S.prossimo.url);
    S.prossimo = p;
    if (S.variante === 'C') { S.riserva.src = p.url; S.riserva.load(); }
    log('capitolo successivo pronto: ' + capitolo(i).id);
  } catch (e) {
    errore('preparazione capitolo successivo', e);
  } finally {
    if (S.preparando === i) S.preparando = -1;
  }
}

// ---------- Aprire un capitolo ----------
// opz: da (secondi), riprendiDa (secondi: riparte dall'INIZIO della frase in cui ci si era fermati), riproduci (true/false)
export async function apriCapitolo(idx, { da = 0, riprendiDa = null, riproduci = false } = {}) {
  if (!S.libro || idx < 0 || idx >= totale()) return;
  const seq = ++S.seq;
  S.ui.caricamento(true);
  let pronto;
  try {
    if (S.prossimo && S.prossimo.idx === idx) { pronto = S.prossimo; S.prossimo = null; }
    else pronto = await caricaCapitolo(idx);
  } catch (e) {
    errore('apertura capitolo', e);
    S.ui.caricamento(false);
    S.ui.messaggio('Non riesco a leggere il capitolo: ' + e.message);
    return;
  }
  if (seq !== S.seq) { URL.revokeObjectURL(pronto.url); return; }
  const inizio = riprendiDa != null ? inizioFrase(pronto.tempi.segmenti, riprendiDa) : da;
  const eraInPlay = !!S.attivo && !S.attivo.paused;
  const p = usaCapitolo(pronto, inizio, riproduci || eraInPlay);
  S.ui.caricamento(false);
  if (p) p.catch((e) => { log('play rifiutato: ' + e.name + ' ' + e.message, true); S.ui.stato(false); });
}

export function impostaLibro(libro) {
  if (S.libro && libro && S.libro.id === libro.id) { S.libro = libro; return; }
  scarica();
  S.libro = libro;
}

// Ferma tutto e dimentica il libro caricato (per esempio dopo averlo eliminato)
export function scarica() {
  S.seq++;
  for (const el of [S.attivo, S.riserva]) {
    if (!el) continue;
    try { el.pause(); el.removeAttribute('src'); el.load(); } catch (e) { /* pazienza */ }
  }
  for (const u of [S.url, S.prossimo && S.prossimo.url]) if (u) URL.revokeObjectURL(u);
  S.libro = null; S.idx = -1; S.tempi = null; S.url = null; S.blob = null; S.prossimo = null; S.cambioFatto = false;
  statoSessione('none');
  S.ui.stato && S.ui.stato(false);
}

// ---------- Comandi ----------
// IMPORTANTE: play() deve partire SUBITO nel gestore del tocco (iPhone lo permette solo così): nessun "await" prima.
export function play() {
  const el = S.attivo;
  if (!el || !el.getAttribute('src')) return Promise.resolve();
  sbloccati.add(el);
  if (S.variante === 'C') sbloccaRiserva();
  const p = el.play();
  return p ? p.catch((e) => { log('play rifiutato: ' + e.name + ' ' + e.message, true); S.ui.stato(false); }) : Promise.resolve();
}
export function pausa() { if (S.attivo) S.attivo.pause(); }
export function vaiA(secondi) {
  const el = S.attivo;
  if (!el || !el.getAttribute('src')) return;
  const durata = isFinite(el.duration) ? el.duration : Infinity;
  el.currentTime = Math.min(Math.max(0, secondi), durata);   // i salti si fermano ai bordi del capitolo
  aggiornaTempo();
}
export function salta(secondi) { if (S.attivo) vaiA(S.attivo.currentTime + secondi); }
export function vaiAllaFine(secondiDallaFine) {
  const el = S.attivo;
  if (!el || !isFinite(el.duration)) return;
  vaiA(Math.max(0, el.duration - secondiDallaFine));
  log('laboratorio: salto a ' + secondiDallaFine + ' s dalla fine');
}

export function staSuonando() { return !!S.attivo && !S.attivo.paused && !!S.attivo.getAttribute('src'); }
export function haCapitolo() { return S.idx >= 0 && !!S.libro; }
export function eCorrente(libroId, idx) { return !!S.libro && S.libro.id === libroId && S.idx === idx && !!S.attivo.getAttribute('src'); }
export function stato() { return { libroId: S.libro && S.libro.id, idx: S.idx, cap: capitolo() || null, tempo: S.attivo ? S.attivo.currentTime : 0, variante: S.variante }; }

export function impostaVariante(v) {
  if (v !== 'A' && v !== 'B' && v !== 'C') return;
  S.variante = v;
  try { localStorage.setItem('al.variante', v); } catch (e) { /* pazienza */ }
  log('laboratorio: variante cambio capitolo = ' + v);
  if (v === 'C') {
    S.prossimo = null; S.preparando = -1;   // riparto: il successivo va messo anche nel lettore di riserva
    preparaProssimo();
  } else if (S.riserva) {
    try { S.riserva.pause(); S.riserva.removeAttribute('src'); S.riserva.load(); } catch (e) { /* pazienza */ }
  }
}
export function variante() { return S.variante; }

// ---------- Posizione ----------
function salvaPosizione() {
  const cap = capitolo();
  if (!S.libro || !cap || !S.attivo || !S.attivo.getAttribute('src')) return;
  arch.salvaPosizione(S.libro.id, cap.id, S.attivo.currentTime || 0);
}

// ---------- Cambio di capitolo ----------
// Variante B: poco prima della fine, dentro il silenzio finale (così il lettore non arriva mai a "finito").
function controllaAnticipo() {
  if (S.variante !== 'B' || S.cambioFatto || S.cambiando || !S.tempi) return;
  const seg = S.tempi.segmenti;
  const soglia = seg[seg.length - 1].fine + ANTICIPO_B_S;
  if (S.attivo.currentTime >= soglia && S.idx + 1 < totale()) passaAlSuccessivo('anticipo');
}

// Variante A (e rete di sicurezza di B e C): quando l'audio è finito
function quandoFinito() {
  log('fine audio del capitolo ' + (capitolo() ? capitolo().id : '?'));
  if (S.cambioFatto) return;
  passaAlSuccessivo('fine audio');
}

function passaAlSuccessivo(motivo) {
  if (S.cambioFatto || S.cambiando) return;
  const i = S.idx + 1;
  if (i >= totale()) {
    log('fine del libro');
    S.ui.stato(false);
    salvaPosizione();
    return;
  }
  S.cambioFatto = true;
  const v = S.variante;
  const schermo = document.hidden ? 'NASCOSTO/bloccato' : 'visibile';
  const t0 = performance.now();
  const esegui = (pronto) => {
    // C: se il lettore di riserva ha già caricato questo capitolo, lo uso (scambio dei lettori)
    const scambia = v === 'C' && S.riserva.getAttribute('src') === pronto.url && sbloccati.has(S.riserva);
    if (v === 'C' && !scambia) log('variante C: lettore di riserva non pronto o non sbloccato, uso quello normale');
    let p;
    try { S.prossimo = null; p = usaCapitolo(pronto, 0, true, { scambia }); } catch (e) { errore('cambio capitolo', e); S.cambioFatto = false; return; }
    const etichetta = 'cambio capitolo [' + v + (scambia ? ' con scambio' : '') + ', ' + motivo + ', schermo ' + schermo + '] verso ' + capitolo().id;
    const t1 = S.attivo.currentTime;
    Promise.resolve(p)
      .then(() => log(etichetta + ': play ok dopo ' + Math.round(performance.now() - t0) + ' ms'))
      .catch((e) => { log(etichetta + ': play RIFIUTATO (' + e.name + ': ' + e.message + ')', true); S.ui.stato(false); });
    const elControllato = S.attivo;
    setTimeout(() => {
      log('controllo +3 s dopo il cambio: da ' + t1.toFixed(1) + ' a ' + elControllato.currentTime.toFixed(1) + ' s · fermo=' + elControllato.paused + ' · schermo ' + (document.hidden ? 'nascosto' : 'visibile'));
    }, 3000);
  };
  if (S.prossimo && S.prossimo.idx === i) { esegui(S.prossimo); return; }
  log('cambio capitolo [' + v + ', ' + motivo + ', schermo ' + schermo + ']: il successivo NON era pronto, lo carico (attesa)');
  caricaCapitolo(i).then(esegui).catch((e) => { errore('cambio capitolo (caricamento)', e); S.cambioFatto = false; });
}

// Variante C: il lettore di riserva va "sbloccato" con un tocco dell'utente (play in muto e subito pausa)
function sbloccaRiserva() {
  const r = S.riserva;
  if (!r || sbloccati.has(r)) return;
  if (!r.getAttribute('src')) { log('variante C: lettore di riserva non ancora pronto (sarà sbloccato al prossimo Play)'); return; }
  r.muted = true;
  const p = r.play();
  if (!p) return;
  p.then(() => {
    r.pause(); r.currentTime = 0; r.muted = false; sbloccati.add(r);
    log('variante C: lettore di riserva sbloccato');
  }).catch((e) => { r.muted = false; log('variante C: sblocco del lettore di riserva RIFIUTATO (' + e.name + ')', true); });
}

// ---------- Errori audio e ripiego in memoria ----------
async function erroreAudio() {
  if (!S.attivo.getAttribute('src')) return;   // il lettore è stato svuotato di proposito: non è un errore
  const e = S.attivo.error;
  log('lettore: ERRORE audio ' + (e ? e.code + ' ' + (e.message || '') : ''), true);
  if (S.ripiego || !S.blob) return;
  S.ripiego = true;
  log('ripiego memoria: rileggo il capitolo con arrayBuffer e riprovo');
  try {
    const t = S.attivo.currentTime || 0;
    const copia = new Blob([await S.blob.arrayBuffer()], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(copia);
    const vecchio = S.url;
    S.cambiando = true;
    S.url = url;
    S.attivo.src = url;
    S.attivo.addEventListener('loadedmetadata', () => { if (t > 0) S.attivo.currentTime = t; }, { once: true });
    S.cambiando = false;
    if (vecchio) URL.revokeObjectURL(vecchio);
  } catch (err) {
    errore('ripiego memoria', err);
  }
}

// ---------- Media Session: titolo e tasti nella schermata di blocco e nelle cuffie ----------
function statoSessione(s) { try { navigator.mediaSession.playbackState = s; } catch (e) { /* pazienza */ } }

function aggiornaMetadataSessione() {
  if (!('mediaSession' in navigator) || !S.libro) return;
  const cap = capitolo();
  const lib = S.libro.manifest.libro;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: cap ? (cap.titolo_completo || cap.titolo) : '',
      artist: lib.autore || '',
      album: lib.titolo || '',
      artwork: [{ src: new URL('icona-512.png', location.href).href, sizes: '512x512', type: 'image/png' }],
    });
  } catch (e) { log('metadata non impostati: ' + e.message); }
}

function aggiornaPosizioneSessione() {
  const el = S.attivo;
  if (!('mediaSession' in navigator) || !el || !isFinite(el.duration) || el.duration <= 0) return;
  try { navigator.mediaSession.setPositionState({ duration: el.duration, playbackRate: 1, position: Math.min(el.currentTime, el.duration) }); } catch (e) { /* pazienza */ }
}

function impostaMediaSession() {
  if (!('mediaSession' in navigator)) { log('Media Session NON supportata'); return; }
  const ms = navigator.mediaSession;
  const h = (azione, fn) => { try { ms.setActionHandler(azione, fn); } catch (e) { log('azione non supportata: ' + azione); } };
  h('play', () => { log('tasto: play'); play(); });
  h('pause', () => { log('tasto: pausa'); pausa(); });
  h('seekbackward', () => { log('tasto: indietro 10 s'); salta(-10); });
  h('seekforward', () => { log('tasto: avanti 10 s'); salta(10); });
  h('seekto', (d) => { log('tasto: barra a ' + Math.round(d.seekTime) + ' s'); vaiA(d.seekTime); });
  // Niente tasti "capitolo precedente/successivo": scelta di progetto (solo ±10 s)
}
