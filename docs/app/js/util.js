// Piccole funzioni di uso comune (tempi, dimensioni, firme SHA-256, ricerca della frase).

// 754 s -> "12:34"
export function mmss(s) {
  s = Math.max(0, Math.floor(s || 0));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// 13268 s -> "3 h 41 min"; 754 s -> "12 min"
export function durataLunga(s) {
  const minuti = Math.round((s || 0) / 60);
  if (minuti < 60) return minuti + ' min';
  return Math.floor(minuti / 60) + ' h ' + String(minuti % 60).padStart(2, '0') + ' min';
}

// 106416950 -> "106,4 MB"  (megabyte "normali", 1 MB = 1.000.000 byte)
export function mbLeggibili(byte) {
  return (byte / 1e6).toFixed(1).replace('.', ',') + ' MB';
}

// Firma SHA-256 di un blocco di byte, in esadecimale minuscolo. Serve https (o localhost): è una regola del browser.
export async function sha256Hex(bytes) {
  const h = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  let s = '';
  for (const b of h) s += b.toString(16).padStart(2, '0');
  return s;
}

// Indice del segmento "corrente" al tempo t: l'ultimo che è già cominciato (inizio <= t).
// Durante le pause tra una frase e l'altra resta quella appena finita. Prima della prima frase: -1.
// Ricerca binaria: si dimezza l'elenco a ogni passo, quindi è veloce anche con centinaia di frasi.
export function indiceSegmento(segmenti, t) {
  let a = 0, b = segmenti.length - 1, risultato = -1;
  while (a <= b) {
    const m = (a + b) >> 1;
    if (segmenti[m].inizio <= t) { risultato = m; a = m + 1; } else { b = m - 1; }
  }
  return risultato;
}

// Dove far ripartire l'ascolto: l'inizio della frase in cui ci si era fermati (non il secondo esatto).
export function inizioFrase(segmenti, t) {
  const i = indiceSegmento(segmenti, t);
  return i < 0 ? 0 : segmenti[i].inizio;
}
