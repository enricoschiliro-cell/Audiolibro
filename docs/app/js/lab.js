// Laboratorio: strumenti di prova nascosti nel pannello Registro. Servono per il primo giro sull'iPhone
// (importazione vera, tre modi di passare al capitolo successivo a schermo bloccato) e per capire gli errori.
// Non cambiano come funziona l'app per chi la usa normalmente.

import { log, errore } from './registro.js';
import * as arch from './archivio.js';
import * as lettore from './lettore.js';
import { mbLeggibili } from './util.js';

const $ = (id) => document.getElementById(id);

// importaFile(file): la stessa funzione dell'importazione normale (barra di avanzamento compresa)
export function inizializzaLab({ importaFile }) {
  // Variante di cambio capitolo
  for (const r of document.querySelectorAll('input[name=variante]')) {
    r.checked = r.value === lettore.variante();
    r.onchange = () => { lettore.impostaVariante(r.value); aggiornaInfoLab(); };
  }
  // Come si salva l'audio (rimedio se il blob desse problemi su iPhone: vale dalla prossima importazione)
  for (const r of document.querySelectorAll('input[name=formato]')) {
    r.checked = r.value === arch.formatoAudio();
    r.onchange = () => { arch.impostaFormatoAudio(r.value); log('laboratorio: formato di salvataggio dell’audio = ' + r.value + ' (vale per le prossime importazioni)'); aggiornaInfoLab(); };
  }
  // Pacchetto dimostrativo (tre capitoli di "bip", senza diritti d'autore), pubblicato insieme all'app
  $('lab-demo').onclick = async () => {
    try {
      log('laboratorio: scarico il pacchetto dimostrativo');
      const r = await fetch('lab/pacchetto-demo.dat');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const blob = await r.blob();
      await importaFile(new File([blob], 'pacchetto-demo.dat'));
    } catch (e) { errore('pacchetto dimostrativo', e); }
  };
  // Saltare vicino alla fine del capitolo, per provare il cambio senza aspettare tutto l'ascolto
  $('lab-20s').onclick = () => lettore.vaiAllaFine(20);
  $('lab-3m').onclick = () => lettore.vaiAllaFine(180);
  aggiornaInfoLab();
}

export async function aggiornaInfoLab() {
  const righe = [];
  righe.push('Browser: ' + navigator.userAgent);
  const standalone = window.navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches);
  righe.push('Aperta dall’icona della schermata Home: ' + (standalone ? 'SÌ' : 'no'));
  righe.push('Connessione sicura (https o localhost): ' + (window.isSecureContext ? 'sì' : 'NO'));
  let deflate = 'no';
  try { if (typeof DecompressionStream !== 'undefined') { new DecompressionStream('deflate-raw'); deflate = 'sì'; } } catch (e) { deflate = 'no'; }
  righe.push('Decompressione zip (deflate-raw): ' + deflate + ' · Media Session: ' + ('mediaSession' in navigator ? 'sì' : 'NO'));
  const sp = await arch.spazio();
  if (sp.usato != null) righe.push('Spazio usato: ' + mbLeggibili(sp.usato) + ' su circa ' + (sp.quota / 1e9).toFixed(1).replace('.', ',') + ' GB · dati protetti: ' + (sp.protetti ? 'sì' : 'no'));
  righe.push('Variante cambio capitolo: ' + lettore.variante() + ' · audio salvato come: ' + arch.formatoAudio());
  const el = $('lab-info');
  if (el) { el.textContent = ''; for (const r of righe) { const d = document.createElement('div'); d.textContent = r; el.appendChild(d); } }
}
