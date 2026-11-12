// Statistiche di ascolto: quanti secondi hai ascoltato, per giorno e per libro.
// Si conta il tempo vero in cui l'audio suona (non i secondi del libro: a velocità 2× un minuto di ascolto sono 2 minuti di libro).
// Salvataggio locale (localStorage), chiave "al.stat": { giorni: { "2026-11-12": { "<libro>": secondi } }, titoli: { "<libro>": "titolo" } }.
// I dati si tengono in memoria e si scrivono su disco ogni tanto (salva()), non a ogni "timeupdate".

const CHIAVE = 'al.stat';
const MAX_GIORNI = 400;
let dati = null;
let sporco = false;

function carica() {
  if (dati) return dati;
  try { dati = JSON.parse(localStorage.getItem(CHIAVE) || 'null'); } catch (e) { dati = null; }
  if (!dati || typeof dati !== 'object' || typeof dati.giorni !== 'object' || !dati.giorni) dati = { giorni: {}, titoli: {} };
  if (!dati.titoli || typeof dati.titoli !== 'object') dati.titoli = {};
  return dati;
}

// "2026-11-12" nell'ora locale del telefono. Con giorniFa = 3 dà il giorno di tre giorni fa.
function chiaveGiorno(giorniFa = 0) {
  const d = new Date();
  d.setDate(d.getDate() - giorniFa);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

// Aggiunge i millisecondi appena ascoltati al giorno di oggi e al libro
export function aggiungi(libroId, titolo, ms) {
  if (!(ms > 0) || !libroId) return;
  const d = carica();
  const g = chiaveGiorno();
  const giorno = d.giorni[g] || (d.giorni[g] = {});
  giorno[libroId] = (giorno[libroId] || 0) + ms / 1000;
  if (titolo) d.titoli[libroId] = titolo;
  sporco = true;
}

// Scrive su disco (se è cambiato qualcosa). Tiene al massimo gli ultimi MAX_GIORNI giorni.
export function salva() {
  if (!sporco) return;
  const d = carica();
  const giorni = Object.keys(d.giorni).sort();
  while (giorni.length > MAX_GIORNI) delete d.giorni[giorni.shift()];
  try { localStorage.setItem(CHIAVE, JSON.stringify(d)); sporco = false; } catch (e) { /* pazienza: riprova al prossimo salvataggio */ }
}

function somma(giorno) {
  let s = 0;
  if (giorno) for (const k of Object.keys(giorno)) s += giorno[k] || 0;
  return s;
}

// Numeri pronti da mostrare: oggi, ultimi 7 giorni, totale, per libro e gli ultimi 14 giorni uno per uno
export function riepilogo() {
  const d = carica();
  const ultimi = [];
  for (let n = 13; n >= 0; n--) {
    const g = chiaveGiorno(n);
    ultimi.push({ data: g, secondi: somma(d.giorni[g]) });
  }
  const perLibro = {};
  let totale = 0;
  for (const g of Object.keys(d.giorni)) {
    for (const id of Object.keys(d.giorni[g])) {
      perLibro[id] = (perLibro[id] || 0) + (d.giorni[g][id] || 0);
      totale += d.giorni[g][id] || 0;
    }
  }
  return {
    oggi: ultimi[ultimi.length - 1].secondi,
    settimana: ultimi.slice(-7).reduce((a, x) => a + x.secondi, 0),
    totale,
    perLibro: Object.keys(perLibro).map((id) => ({ id, titolo: d.titoli[id] || id, secondi: perLibro[id] })).sort((a, b) => b.secondi - a.secondi),
    giorni: ultimi,
  };
}
