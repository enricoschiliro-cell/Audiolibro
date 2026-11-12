// Archivio dei libri sul telefono: IndexedDB (il "database" interno del browser, che sa conservare anche file interi).
// Contenuto:
//   libri  -> un record per libro (manifest, stato, capitoli già salvati con le firme, copertina)
//   audio  -> l'MP3 di ogni capitolo, chiave "<libro>/<capitolo>"
//   tempi  -> i tempi delle frasi di ogni capitolo, stessa chiave
// In più, nel salvataggio locale (localStorage): la posizione di ascolto "al.pos.<libro>" e due preferenze.
// Regola: tutte le chiavi dell'app cominciano con "al." e il database si chiama "audiolibro".

import { log } from './registro.js';

const NOME_DB = 'audiolibro';
const VERSIONE_DB = 1;
let dbPromessa = null;

export function apriDb() {
  if (!dbPromessa) {
    dbPromessa = new Promise((ok, no) => {
      const r = indexedDB.open(NOME_DB, VERSIONE_DB);
      r.onupgradeneeded = () => {
        const db = r.result;
        db.createObjectStore('libri', { keyPath: 'id' });
        db.createObjectStore('audio');
        db.createObjectStore('tempi');
      };
      r.onsuccess = () => {
        const db = r.result;
        // iOS può chiudere la connessione in qualunque momento: al prossimo uso la riapro
        db.onclose = () => { dbPromessa = null; };
        db.onversionchange = () => { db.close(); dbPromessa = null; };
        ok(db);
      };
      r.onerror = () => { dbPromessa = null; no(r.error); };
      r.onblocked = () => log('database bloccato da un’altra scheda', true);
    });
  }
  return dbPromessa;
}

function richiesta(req) {
  return new Promise((ok, no) => { req.onsuccess = () => ok(req.result); req.onerror = () => no(req.error); });
}

// Una "transazione" è un gruppo di scritture che riesce o fallisce tutto insieme.
function fineTransazione(tx) {
  return new Promise((ok, no) => {
    tx.oncomplete = () => ok();
    tx.onerror = () => no(tx.error);
    tx.onabort = () => no(tx.error || new Error('transazione annullata'));
  });
}

// ---------- Preferenze di prova (laboratorio) ----------
export function formatoAudio() {
  try { return localStorage.getItem('al.formatoAudio') === 'buffer' ? 'buffer' : 'blob'; } catch (e) { return 'blob'; }
}
export function impostaFormatoAudio(f) {
  try { localStorage.setItem('al.formatoAudio', f === 'buffer' ? 'buffer' : 'blob'); } catch (e) { /* pazienza */ }
}

// ---------- Libri ----------
export async function elencoLibri() {
  const db = await apriDb();
  const libri = await richiesta(db.transaction('libri').objectStore('libri').getAll());
  libri.sort((a, b) => (b.importatoIl || 0) - (a.importatoIl || 0));
  return libri;
}

export async function leggiLibro(id) {
  const db = await apriDb();
  return (await richiesta(db.transaction('libri').objectStore('libri').get(id))) || null;
}

export async function salvaLibro(record) {
  const db = await apriDb();
  const tx = db.transaction('libri', 'readwrite');
  const fine = fineTransazione(tx);
  tx.objectStore('libri').put(record);
  await fine;
}

// Salva UN capitolo (audio + tempi) e aggiorna il record del libro, tutto nella stessa transazione.
// Attenzione: qui dentro non si deve aspettare nient'altro che IndexedDB, altrimenti la transazione si chiude da sola.
export async function salvaCapitolo(libroId, capId, byteAudio, tempi, record) {
  const db = await apriDb();
  const chiave = libroId + '/' + capId;
  const valore = formatoAudio() === 'buffer'
    ? byteAudio.buffer.slice(byteAudio.byteOffset, byteAudio.byteOffset + byteAudio.byteLength)
    : new Blob([byteAudio], { type: 'audio/mpeg' });
  const tx = db.transaction(['audio', 'tempi', 'libri'], 'readwrite');
  const fine = fineTransazione(tx);
  tx.objectStore('audio').put(valore, chiave);
  tx.objectStore('tempi').put(tempi, chiave);
  tx.objectStore('libri').put(record);
  await fine;
}

// Toglie dal database i capitoli indicati (per esempio quelli che non sono più nel pacchetto aggiornato)
export async function eliminaCapitoli(libroId, capIds) {
  if (!capIds.length) return;
  const db = await apriDb();
  const tx = db.transaction(['audio', 'tempi'], 'readwrite');
  const fine = fineTransazione(tx);
  for (const id of capIds) {
    tx.objectStore('audio').delete(libroId + '/' + id);
    tx.objectStore('tempi').delete(libroId + '/' + id);
  }
  await fine;
}

export async function eliminaLibro(id) {
  const db = await apriDb();
  const intervallo = IDBKeyRange.bound(id + '/', id + '/￿');   // tutte le chiavi che cominciano con "<libro>/"
  const tx = db.transaction(['audio', 'tempi', 'libri'], 'readwrite');
  const fine = fineTransazione(tx);
  tx.objectStore('audio').delete(intervallo);
  tx.objectStore('tempi').delete(intervallo);
  tx.objectStore('libri').delete(id);
  await fine;
  try { localStorage.removeItem('al.pos.' + id); } catch (e) { /* pazienza */ }
}

// ---------- Lettura di un capitolo ----------
// Restituisce un Blob audio (anche se è stato salvato come buffer)
export async function leggiAudioBlob(libroId, capId) {
  const db = await apriDb();
  const v = await richiesta(db.transaction('audio').objectStore('audio').get(libroId + '/' + capId));
  if (!v) return null;
  return v instanceof Blob ? v : new Blob([v], { type: 'audio/mpeg' });
}

export async function leggiTempi(libroId, capId) {
  const db = await apriDb();
  return (await richiesta(db.transaction('tempi').objectStore('tempi').get(libroId + '/' + capId))) || null;
}

// ---------- Posizione di ascolto (per libro: capitolo e secondi) ----------
export function leggiPosizione(libroId) {
  try { return JSON.parse(localStorage.getItem('al.pos.' + libroId) || 'null'); } catch (e) { return null; }
}
export function salvaPosizione(libroId, capId, secondi) {
  try { localStorage.setItem('al.pos.' + libroId, JSON.stringify({ cap: capId, t: Math.round(secondi * 10) / 10, quando: Date.now() })); } catch (e) { /* pazienza */ }
}

// ---------- Spazio e protezione dei dati ----------
export async function spazio() {
  const r = { usato: null, quota: null, protetti: null };
  try {
    if (navigator.storage && navigator.storage.estimate) {
      const e = await navigator.storage.estimate();
      r.usato = e.usage; r.quota = e.quota;
    }
    if (navigator.storage && navigator.storage.persisted) r.protetti = await navigator.storage.persisted();
  } catch (e) { /* pazienza */ }
  return r;
}

// Chiede al browser di non cancellare i dati da solo. Non è garantito: decide iOS.
export async function chiediPersistenza() {
  try {
    if (navigator.storage && navigator.storage.persist) return await navigator.storage.persist();
  } catch (e) { /* pazienza */ }
  return false;
}
