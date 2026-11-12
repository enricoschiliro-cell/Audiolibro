// Timer di spegnimento: ferma l'audio dopo un certo tempo di ASCOLTO oppure alla fine del capitolo.
// Il tempo scorre solo mentre l'audio suona (se metti in pausa, il timer aspetta). Non viene salvato: se chiudi l'app, il timer si spegne.
// Chi conta il tempo è lettore.js (a ogni "timeupdate" e ogni secondo): qui c'è solo lo stato.

import { mmss } from './util.js';

// null = spento; un numero = minuti di ascolto; 'capitolo' = ferma alla fine del capitolo in corso
const OPZIONI = [null, 10, 20, 30, 45, 60, 'capitolo'];
let indice = 0;
let restanteMs = 0;

// Passa all'opzione successiva (dopo "fine capitolo" torna a "spento") e restituisce l'etichetta del pulsante
export function ciclo() {
  indice = (indice + 1) % OPZIONI.length;
  const o = OPZIONI[indice];
  restanteMs = typeof o === 'number' ? o * 60000 : 0;
  return etichetta();
}

export function spegni() { indice = 0; restanteMs = 0; }

export function attivo() { return indice !== 0; }

// true se il timer è su "fine capitolo"
export function aFineCapitolo() { return OPZIONI[indice] === 'capitolo'; }

// Toglie dal tempo rimasto i millisecondi appena ascoltati. Restituisce true quando il tempo è finito (e il timer si spegne).
export function consuma(ms) {
  if (typeof OPZIONI[indice] !== 'number') return false;
  restanteMs -= ms;
  if (restanteMs <= 0) { spegni(); return true; }
  return false;
}

export function etichetta() {
  const o = OPZIONI[indice];
  if (o === null) return 'Timer';
  if (o === 'capitolo') return 'fine cap.';
  return mmss(Math.ceil(restanteMs / 1000));
}
