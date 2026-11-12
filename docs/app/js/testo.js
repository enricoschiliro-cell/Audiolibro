// Testo sincronizzato con la voce: mostra il testo del capitolo, evidenzia la frase che si sta ascoltando,
// la fa scorrere al centro dello schermo e permette di saltare a una frase toccandola.
// Per risparmiare batteria: si tocca la pagina solo quando la frase CAMBIA (in media ogni circa 8 s) e mai a schermo spento.

import { indiceSegmento } from './util.js';

export class VistaTesto {
  // onSalta(secondi): chiamata quando si tocca una frase. onAutoScroll(bool): quando lo scorrimento automatico si ferma/riparte.
  constructor(contenitore, { onSalta, onAutoScroll }) {
    this.el = contenitore;
    this.onSalta = onSalta;
    this.onAutoScroll = onAutoScroll;
    this.segmenti = [];
    this.spans = [];
    this.logico = -1;      // la frase giusta al tempo corrente (sempre aggiornata, anche in background)
    this.mostrato = -1;    // la frase evidenziata davvero sulla pagina
    this.autoScroll = true;

    // Tocco su una frase = salto lì. (Mentre si scorre col dito iOS non manda il "click", quindi non si salta per sbaglio.)
    this.el.addEventListener('click', (ev) => {
      const sp = ev.target.closest && ev.target.closest('.frase');
      if (!sp) return;
      const i = Number(sp.dataset.i);
      if (!this.segmenti[i]) return;
      this.setAutoScroll(true);
      this.onSalta(this.segmenti[i].inizio);
    });
    // Se l'utente scorre a mano, lo scorrimento automatico si ferma finché non tocca "Torna alla voce".
    // (Si ascoltano solo gesti dell'utente, non l'evento "scroll", che scatta anche per gli scorrimenti automatici.)
    const manuale = () => { if (this.autoScroll) this.setAutoScroll(false); };
    this.el.addEventListener('touchmove', manuale, { passive: true });
    this.el.addEventListener('wheel', manuale, { passive: true });
  }

  // Costruisce il testo di un capitolo. Annuncio e sottotitolo diventano titoli; un paragrafo nuovo comincia dopo una pausa >= 0,9 s.
  carica(tempi) {
    this.segmenti = tempi.segmenti;
    this.spans = [];
    this.logico = -1;
    this.mostrato = -1;
    this.el.textContent = '';
    const frammento = document.createDocumentFragment();
    let p = null;
    this.segmenti.forEach((s, i) => {
      const sp = document.createElement('span');
      sp.className = 'frase';
      sp.dataset.i = String(i);
      sp.textContent = s.testo;           // textContent: il testo non viene mai interpretato come HTML
      this.spans.push(sp);
      if (s.tipo === 'annuncio' || s.tipo === 'sottotitolo') {
        const h = document.createElement(s.tipo === 'annuncio' ? 'h2' : 'h3');
        h.appendChild(sp);
        frammento.appendChild(h);
        p = null;
        return;
      }
      if (!p) { p = document.createElement('p'); frammento.appendChild(p); }
      p.appendChild(sp);
      p.appendChild(document.createTextNode(' '));
      if (s.pausa >= 0.9) p = null;       // fine paragrafo
    });
    this.el.appendChild(frammento);
    this.el.scrollTop = 0;
    this.setAutoScroll(true);
  }

  setAutoScroll(acceso) {
    if (this.autoScroll === acceso) return;
    this.autoScroll = acceso;
    if (this.onAutoScroll) this.onAutoScroll(acceso);
    if (acceso) this.riallinea();
  }

  _evidenzia(i, istantaneo) {
    const vecchio = this.spans[this.mostrato];
    if (vecchio) vecchio.classList.remove('attiva');
    this.mostrato = i;
    const nuovo = this.spans[i];
    if (!nuovo) return;
    nuovo.classList.add('attiva');
    if (this.autoScroll) nuovo.scrollIntoView({ block: 'center', behavior: istantaneo ? 'auto' : 'smooth' });
  }

  // Chiamata a ogni "timeupdate" dell'audio (circa 4 volte al secondo). Restituisce l'indice della frase corrente.
  aggiorna(t) {
    const s = this.segmenti;
    if (!s.length) return -1;
    let i = this.logico;
    // Caso comune: siamo ancora nella stessa frase -> non faccio niente
    if (i >= 0 && t >= s[i].inizio && (i + 1 >= s.length || t < s[i + 1].inizio)) return i;
    // Secondo caso comune: è partita la frase successiva
    if (i >= 0 && i + 1 < s.length && t >= s[i + 1].inizio && (i + 2 >= s.length || t < s[i + 2].inizio)) i = i + 1;
    else i = indiceSegmento(s, t);          // dopo un salto: ricerca binaria
    this.logico = i;
    if (!document.hidden && i !== this.mostrato) this._evidenzia(i, false);
    return i;
  }

  // Riporta subito la pagina alla frase giusta (quando lo schermo si riaccende o torna lo scorrimento automatico)
  riallinea() {
    if (document.hidden || this.logico < 0) return;
    this._evidenzia(this.logico, true);
  }
}
