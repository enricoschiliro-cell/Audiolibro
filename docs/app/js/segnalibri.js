// Segnalibri: un punto (l'inizio di una frase) di un capitolo, con una nota facoltativa.
// Salvataggio locale (localStorage), una chiave per libro: "al.seg.<libro>" = lista di
//   { id, cap (id del capitolo), t (secondi, inizio della frase), testo (l'inizio della frase), nota, creato (ms) }
// Quando si elimina un libro, archivio.js cancella anche la sua chiave.

const chiave = (libroId) => 'al.seg.' + libroId;

function leggi(libroId) {
  try {
    const v = JSON.parse(localStorage.getItem(chiave(libroId)) || '[]');
    return Array.isArray(v) ? v : [];
  } catch (e) { return []; }
}

function scrivi(libroId, lista) {
  try { localStorage.setItem(chiave(libroId), JSON.stringify(lista)); return true; } catch (e) { return false; }
}

export function elenco(libroId) { return leggi(libroId); }
export function quanti(libroId) { return leggi(libroId).length; }

// Aggiunge un segnalibro. Se nello stesso capitolo ce n'è già uno sulla stessa frase non ne crea un altro.
// Restituisce { nuovo, segnalibro } oppure { errore: true } se il telefono non riesce a salvare.
export function aggiungi(libroId, { cap, t, testo }) {
  const lista = leggi(libroId);
  const t1 = Math.round(t * 10) / 10;
  const esiste = lista.find((s) => s.cap === cap && Math.abs(s.t - t1) < 0.5);
  if (esiste) return { nuovo: false, segnalibro: esiste };
  const sg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), cap, t: t1, testo: testo || '', nota: '', creato: Date.now() };
  lista.push(sg);
  if (!scrivi(libroId, lista)) return { errore: true };
  return { nuovo: true, segnalibro: sg };
}

export function impostaNota(libroId, id, nota) {
  const lista = leggi(libroId);
  const s = lista.find((x) => x.id === id);
  if (!s) return false;
  s.nota = String(nota || '').trim().slice(0, 300);
  return scrivi(libroId, lista);
}

export function elimina(libroId, id) {
  const lista = leggi(libroId);
  const nuova = lista.filter((x) => x.id !== id);
  if (nuova.length === lista.length) return false;
  return scrivi(libroId, nuova);
}
