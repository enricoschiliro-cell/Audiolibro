// Interruttori dell'aspetto (Registro > Aspetto): Caramella, scanline, alone sui titoli, testo del libro proporzionale.
// Le scelte restano salvate nel telefono (chiave "al.aspetto") e si traducono in classi sul <body>, come negli interruttori del tema:
//   cc-caramella-off · cc-scanlines-off · cc-glow-off · cc-body-sans

import { log } from './registro.js';

const CHIAVE = 'al.aspetto';
const PREDEFINITI = { caramella: true, scanline: true, glow: true, sans: false };
const CASELLE = { 'asp-caramella': 'caramella', 'asp-scanline': 'scanline', 'asp-glow': 'glow', 'asp-sans': 'sans' };

function leggi() {
  try {
    const v = JSON.parse(localStorage.getItem(CHIAVE) || 'null');
    return { ...PREDEFINITI, ...(v && typeof v === 'object' ? v : {}) };
  } catch (e) { return { ...PREDEFINITI }; }
}

function applica(p) {
  const c = document.body.classList;
  c.toggle('cc-caramella-off', !p.caramella);
  c.toggle('cc-scanlines-off', !p.scanline);
  c.toggle('cc-glow-off', !p.glow);
  c.toggle('cc-body-sans', !!p.sans);
}

export function inizializzaAspetto() {
  const p = leggi();
  applica(p);
  for (const [id, chiave] of Object.entries(CASELLE)) {
    const casella = document.getElementById(id);
    if (!casella) continue;
    casella.checked = !!p[chiave];
    casella.onchange = () => {
      p[chiave] = casella.checked;
      try { localStorage.setItem(CHIAVE, JSON.stringify(p)); } catch (e) { /* pazienza */ }
      applica(p);
      log('aspetto: ' + chiave + ' = ' + (casella.checked ? 'sì' : 'no'));
    };
  }
}
