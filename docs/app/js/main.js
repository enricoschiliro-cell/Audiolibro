// Collega le tre viste (libreria, capitoli, lettore), l'importazione, il lettore audio, il testo sincronizzato e l'aggiornamento dell'app.

import { log, errore, collegaPannello } from './registro.js';
import * as arch from './archivio.js';
import { importaPacchetto, ErroreImportazione } from './importa.js';
import * as lettore from './lettore.js';
import { VistaTesto } from './testo.js';
import { inizializzaLab, aggiornaInfoLab } from './lab.js';
import { mmss, durataLunga, mbLeggibili } from './util.js';
import * as timer from './timer.js';
import * as segnalibri from './segnalibri.js';
import * as statistiche from './statistiche.js';

const $ = (id) => document.getElementById(id);
const viste = { libreria: $('vista-libreria'), capitoli: $('vista-capitoli'), lettore: $('vista-lettore') };
let vistaAttuale = 'libreria';
let libroAperto = null;            // record del libro mostrato nella vista capitoli
let importazioneInCorso = false;
let copertineLibreria = [];        // indirizzi blob: delle copertine da liberare quando ridisegno
let copertinaCapitoli = null;

// ---------- Viste ----------
function mostra(nome) {
  vistaAttuale = nome;
  for (const k of Object.keys(viste)) viste[k].hidden = k !== nome;
  window.scrollTo(0, 0);
  aggiornaMinibarra();
  if (nome === 'lettore') vista.riallinea();
}

function aggiornaMinibarra() {
  const visibile = lettore.haCapitolo() && vistaAttuale !== 'lettore';
  $('minibarra').hidden = !visibile;
  document.body.classList.toggle('con-minibarra', visibile);
}

// ---------- Testo sincronizzato ----------
const vista = new VistaTesto($('testo'), {
  onSalta: (secondi) => lettore.vaiA(secondi),
  onAutoScroll: (acceso) => { $('btn-torna-voce').hidden = acceso; },
});
$('btn-torna-voce').onclick = () => vista.setAutoScroll(true);

// ---------- Collegamento con il lettore audio ----------
let ultimaFrase = -2;
const ui = {
  stato(inRiproduzione) {
    $('btn-play').textContent = inRiproduzione ? '⏸ Pausa' : '▶ Play';
    $('minibarra-stato').textContent = inRiproduzione ? '⏸' : '▶';
  },
  tempo(t, durata) {
    $('let-tempo').textContent = mmss(t) + ' / ' + mmss(durata);
    const i = vista.aggiorna(t);
    if (i !== ultimaFrase) { ultimaFrase = i; $('let-frase').textContent = 'frase ' + (i + 1) + ' di ' + vista.segmenti.length; }
  },
  capitolo(idx, cap, tempi) {
    const titolo = cap.titolo_completo || cap.titolo;
    $('let-titolo').textContent = titolo;
    $('minibarra-titolo').textContent = titolo;
    vista.carica(tempi);
    ultimaFrase = -2;
    $('btn-prec').disabled = idx <= 0;
    $('btn-succ').disabled = idx >= libroAperto.manifest.capitoli.length - 1;
    aggiornaMinibarra();
  },
  caricamento(acceso) {
    $('btn-play').disabled = acceso;
    if (acceso) $('let-frase').textContent = 'Carico il capitolo…';
  },
  messaggio(testo) { $('let-frase').textContent = testo; },
  riallinea() { vista.riallinea(); },
  velocita(v) { $('btn-velocita').textContent = String(v).replace('.', ',') + '×'; },
  timer() { $('btn-timer').textContent = timer.etichetta(); $('btn-timer').classList.toggle('acceso', timer.attivo()); },
};

// ---------- Libreria ----------
function liberaCopertineLibreria() {
  for (const u of copertineLibreria) URL.revokeObjectURL(u);
  copertineLibreria = [];
}

function schedaLibro(l) {
  const lib = l.manifest.libro;
  const caps = l.manifest.capitoli;
  const div = document.createElement('div');
  div.className = 'libro';
  if (l.copertina) {
    const img = document.createElement('img');
    img.alt = '';
    const u = URL.createObjectURL(l.copertina);
    copertineLibreria.push(u);
    img.src = u;
    div.appendChild(img);
  } else {
    const vuota = document.createElement('div');
    vuota.className = 'senza-copertina';
    div.appendChild(vuota);
  }
  const dati = document.createElement('div');
  dati.className = 'dati';
  const t = document.createElement('div');
  t.className = 'titolo';
  t.textContent = lib.titolo;
  const a = document.createElement('div');
  a.className = 'piccolo';
  a.textContent = (lib.autore || '') + ' · ' + durataLunga(l.manifest.durata);
  dati.append(t, a);
  const info = document.createElement('div');
  info.className = 'piccolo';
  if (l.stato !== 'pronto') {
    info.className = 'incompleto piccolo';
    const n = Object.keys(l.salvati || {}).length;
    info.textContent = 'Importazione incompleta (' + n + ' di ' + caps.length + ' capitoli). Tocca «Importa libro» e scegli di nuovo lo stesso file per continuare.';
  } else {
    const pos = arch.leggiPosizione(l.id);
    const i = pos ? caps.findIndex((c) => c.id === pos.cap) : -1;
    info.textContent = i >= 0 ? 'Cap. ' + (i + 1) + ' di ' + caps.length : caps.length + ' capitoli';
  }
  dati.appendChild(info);
  const azioni = document.createElement('div');
  azioni.className = 'azioni';
  if (l.stato === 'pronto') {
    const apri = document.createElement('button');
    apri.textContent = 'Apri';
    apri.onclick = () => mostraCapitoli(l);
    azioni.appendChild(apri);
  }
  const elimina = document.createElement('button');
  elimina.className = 'sec';
  elimina.textContent = 'Elimina';
  elimina.onclick = () => eliminaLibro(l);
  azioni.appendChild(elimina);
  dati.appendChild(azioni);
  div.appendChild(dati);
  return div;
}

async function disegnaLibreria() {
  try {
    const libri = await arch.elencoLibri();
    liberaCopertineLibreria();
    const box = $('elenco-libri');
    box.textContent = '';
    if (!libri.length) {
      const p = document.createElement('p');
      p.className = 'piccolo';
      p.textContent = 'Nessun libro. Tocca «Importa libro» e scegli un pacchetto .zip dall’app File.';
      box.appendChild(p);
    }
    for (const l of libri) box.appendChild(schedaLibro(l));
  } catch (e) {
    errore('libreria', e);
    mostraErroreImporta('Non riesco a leggere la libreria: ' + (e && e.message ? e.message : e));
  }
  mostraSpazio();
}

async function mostraSpazio() {
  const sp = await arch.spazio();
  const el = $('stato-spazio');
  if (sp.usato == null) { el.textContent = ''; return; }
  el.textContent = 'Spazio usato: ' + mbLeggibili(sp.usato) + ' su circa ' + (sp.quota / 1e9).toFixed(1).replace('.', ',') + ' GB · dati protetti dalla pulizia automatica: ' + (sp.protetti ? 'sì' : 'no');
}

async function eliminaLibro(l) {
  if (importazioneInCorso) { mostraErroreImporta('Aspetta la fine dell’importazione prima di eliminare un libro.'); return; }
  if (!window.confirm('Eliminare «' + l.manifest.libro.titolo + '» dal telefono? La posizione di ascolto e i segnalibri andranno persi. Potrai reimportarlo dallo zip.')) return;
  try {
    if (lettore.stato().libroId === l.id) lettore.scarica();
    await arch.eliminaLibro(l.id);
    log('libro eliminato: ' + l.id);
  } catch (e) { errore('eliminazione', e); mostraErroreImporta('Non riesco a eliminare il libro: ' + e.message); }
  aggiornaMinibarra();
  await disegnaLibreria();
}

function mostraErroreImporta(testo) {
  const el = $('msg-importa');
  el.textContent = testo;
  el.hidden = false;
}

// ---------- Importazione ----------
$('btn-importa').onclick = () => {
  $('msg-importa').hidden = true;
  // Chiedo subito (con il tocco) di proteggere i dati dalla pulizia automatica; iOS decide, il risultato va nel registro
  arch.chiediPersistenza().then((ok) => log('persist(): ' + (ok ? 'concesso' : 'non concesso')));
  const f = $('file-importa');
  f.value = '';
  f.click();
};
$('file-importa').onchange = (ev) => {
  const file = ev.target.files && ev.target.files[0];
  if (file) eseguiImportazione(file);
};

async function eseguiImportazione(file) {
  if (importazioneInCorso) { log('importazione già in corso: ignoro'); return; }
  importazioneInCorso = true;
  mostra('libreria');
  $('msg-importa').hidden = true;
  $('importazione').hidden = false;
  $('imp-barra').value = 0;
  $('btn-importa').disabled = true;
  try {
    await importaPacchetto(file, ({ testo, percentuale }) => {
      $('imp-testo').textContent = testo;
      $('imp-barra').value = percentuale;
    });
    $('imp-testo').textContent = 'Importazione finita.';
    setTimeout(() => { if (!importazioneInCorso) $('importazione').hidden = true; }, 3000);
  } catch (e) {
    errore('importazione', e);
    $('importazione').hidden = true;
    mostraErroreImporta(e instanceof ErroreImportazione ? e.message : 'Errore inatteso durante l’importazione: ' + (e && e.message ? e.message : e));
  } finally {
    importazioneInCorso = false;
    $('btn-importa').disabled = false;
    await disegnaLibreria();
    aggiornaInfoLab();
  }
}
window.addEventListener('beforeunload', (ev) => { if (importazioneInCorso) { ev.preventDefault(); ev.returnValue = ''; } });

// ---------- Capitoli ----------
function mostraCapitoli(l) {
  libroAperto = l;
  lettore.impostaLibro(l);
  const lib = l.manifest.libro;
  const testata = $('cap-intestazione');
  testata.textContent = '';
  if (copertinaCapitoli) { URL.revokeObjectURL(copertinaCapitoli); copertinaCapitoli = null; }
  if (l.copertina) {
    copertinaCapitoli = URL.createObjectURL(l.copertina);
    const img = document.createElement('img');
    img.alt = '';
    img.src = copertinaCapitoli;
    testata.appendChild(img);
  }
  const blocco = document.createElement('div');
  const t = document.createElement('div');
  t.className = 'titolo';
  t.style.color = 'var(--arancio)';
  t.textContent = lib.titolo;
  const a = document.createElement('div');
  a.className = 'piccolo';
  a.textContent = (lib.autore || '') + ' · ' + durataLunga(l.manifest.durata);
  blocco.append(t, a);
  testata.appendChild(blocco);
  aggiornaElencoCapitoli();
  mostra('capitoli');
}

function aggiornaElencoCapitoli() {
  const l = libroAperto;
  if (!l) return;
  const caps = l.manifest.capitoli;
  // Pulsante "Riprendi"
  const btn = $('btn-riprendi');
  const pos = arch.leggiPosizione(l.id);
  const i = pos ? caps.findIndex((c) => c.id === pos.cap) : -1;
  if (i < 0) {
    btn.textContent = 'Inizia dal primo capitolo';
    btn.onclick = () => avviaCapitolo(0);
  } else {
    btn.textContent = 'Riprendi: ' + (caps[i].titolo_completo || caps[i].titolo) + ' · ' + mmss(pos.t);
    btn.onclick = () => avviaCapitolo(i, { riprendiDa: pos.t });
  }
  btn.hidden = false;
  const nSeg = segnalibri.quanti(l.id);
  $('btn-segnalibri').textContent = nSeg ? 'Segnalibri (' + nSeg + ')' : 'Segnalibri';
  $('btn-segnalibri').hidden = false;
  // Elenco
  const ol = $('elenco-capitoli');
  ol.textContent = '';
  const corrente = lettore.stato();
  caps.forEach((c, n) => {
    const li = document.createElement('li');
    const titolo = document.createElement('span');
    titolo.textContent = c.titolo_completo || c.titolo;
    const durata = document.createElement('span');
    durata.className = 'durata';
    durata.textContent = durataLunga(c.durata);
    li.append(titolo, durata);
    if (corrente.libroId === l.id && corrente.idx === n) li.classList.add('attuale');
    li.onclick = () => avviaCapitolo(n);
    ol.appendChild(li);
  });
}

async function avviaCapitolo(i, opzioni = {}) {
  if (lettore.eCorrente(libroAperto.id, i)) { mostra('lettore'); return; }   // è già caricato: non lo ricarico
  mostra('lettore');
  // Il capitolo si apre FERMO: il Play lo premi tu (iPhone fa partire l'audio solo da un tuo tocco)
  await lettore.apriCapitolo(i, opzioni);
}

$('cap-indietro').onclick = () => { disegnaLibreria(); mostra('libreria'); };
$('let-indietro').onclick = () => { aggiornaElencoCapitoli(); mostra('capitoli'); };
$('minibarra-apri').onclick = () => mostra('lettore');

// ---------- Comandi del lettore ----------
$('btn-play').onclick = () => {
  // play() deve partire subito dal tocco, senza "await" prima
  if (lettore.staSuonando()) lettore.pausa(); else lettore.play();
};
$('btn-meno10').onclick = () => lettore.salta(-10);
$('btn-piu10').onclick = () => lettore.salta(10);
$('btn-prec').onclick = () => { const s = lettore.stato(); lettore.apriCapitolo(s.idx - 1, { riproduci: lettore.staSuonando() }); };
$('btn-succ').onclick = () => { const s = lettore.stato(); lettore.apriCapitolo(s.idx + 1, { riproduci: lettore.staSuonando() }); };

// ---------- Velocità e timer di spegnimento ----------
$('btn-velocita').onclick = () => lettore.prossimaVelocita();
$('btn-timer').onclick = () => {
  const etichetta = timer.ciclo();
  ui.timer();
  log('timer di spegnimento: ' + etichetta);
};

// ---------- Segnalibri ----------
// Piccole funzioni per costruire pezzi di pagina senza HTML scritto a mano (il testo va sempre con textContent)
function crea(tag, classe, testo) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (testo != null) e.textContent = testo;
  return e;
}
function bottone(testo, classe, onclick) {
  const b = crea('button', classe, testo);
  b.onclick = onclick;
  return b;
}
function indiceCapitolo(capId) { return libroAperto ? libroAperto.manifest.capitoli.findIndex((c) => c.id === capId) : -1; }

// La barra sopra i comandi: "Segnalibro salvato" con i tasti Nota e Annulla, sparisce da sola dopo 8 secondi
let timerBarraSeg = null;
function nascondiBarraSegnalibro() {
  clearTimeout(timerBarraSeg);
  $('barra-segnalibro').hidden = true;
}
function mostraBarraSegnalibro(sg, nuovo) {
  const barra = $('barra-segnalibro');
  barra.textContent = '';
  barra.appendChild(crea('span', null, (nuovo ? 'Segnalibro salvato · ' : 'Segnalibro già presente · ') + mmss(sg.t)));
  barra.appendChild(bottone('Nota', 'sec piccolo', () => modificaNotaNellaBarra(sg)));
  if (nuovo) {
    barra.appendChild(bottone('Annulla', 'sec piccolo', () => {
      segnalibri.elimina(libroAperto.id, sg.id);
      log('segnalibro annullato');
      nascondiBarraSegnalibro();
    }));
  }
  barra.hidden = false;
  clearTimeout(timerBarraSeg);
  timerBarraSeg = setTimeout(nascondiBarraSegnalibro, 8000);
}
function modificaNotaNellaBarra(sg) {
  clearTimeout(timerBarraSeg);   // finché scrivi la barra resta aperta
  const barra = $('barra-segnalibro');
  barra.textContent = '';
  const campo = crea('input');
  campo.type = 'text'; campo.maxLength = 300; campo.placeholder = 'Nota (facoltativa)'; campo.value = sg.nota || '';
  const salva = () => {
    segnalibri.impostaNota(libroAperto.id, sg.id, campo.value);
    log('segnalibro: nota salvata');
    nascondiBarraSegnalibro();
  };
  campo.onkeydown = (ev) => { if (ev.key === 'Enter') salva(); };
  barra.append(campo, bottone('OK', 'piccolo', salva));
  campo.focus();
}
$('btn-segna').onclick = () => {
  if (!libroAperto) return;
  const p = lettore.puntoCorrente();
  if (!p) { ui.messaggio('Apri un capitolo per segnare un punto.'); return; }
  const r = segnalibri.aggiungi(libroAperto.id, p);
  if (r.errore) { ui.messaggio('Non riesco a salvare il segnalibro (spazio del telefono).'); log('segnalibro: salvataggio NON riuscito', true); return; }
  log('segnalibro ' + (r.nuovo ? 'salvato' : 'già presente') + ': ' + p.cap + ' a ' + mmss(p.t));
  mostraBarraSegnalibro(r.segnalibro, r.nuovo);
};

// L'elenco dei segnalibri del libro aperto
function disegnaSegnalibri() {
  const l = libroAperto;
  if (!l) return;
  $('seg-titolo').textContent = 'Segnalibri · ' + l.manifest.libro.titolo;
  const box = $('seg-elenco');
  box.textContent = '';
  const lista = segnalibri.elenco(l.id).slice().sort((a, b) => (indiceCapitolo(a.cap) - indiceCapitolo(b.cap)) || (a.t - b.t));
  if (!lista.length) {
    box.appendChild(crea('p', 'piccolo', 'Nessun segnalibro. Nel lettore tocca «🔖 Segna» per segnare la frase che stai ascoltando.'));
    return;
  }
  for (const s of lista) box.appendChild(schedaSegnalibro(l, s));
}

function schedaSegnalibro(l, s) {
  const i = indiceCapitolo(s.cap);
  const cap = i >= 0 ? l.manifest.capitoli[i] : null;
  const div = crea('div', 'segnalibro');
  div.appendChild(crea('div', 'titolo', (cap ? (cap.titolo_completo || cap.titolo) : s.cap) + ' · ' + mmss(s.t)));
  if (s.testo) div.appendChild(crea('div', 'frase-seg', '«' + s.testo + '»'));
  if (s.nota) div.appendChild(crea('div', 'nota', s.nota));
  const azioni = crea('div', 'azioni');
  const vai = bottone('Vai', null, () => vaiAlSegnalibro(s));
  vai.disabled = i < 0;
  azioni.appendChild(vai);
  azioni.appendChild(bottone(s.nota ? 'Cambia nota' : 'Nota', 'sec', () => modificaNotaNellElenco(div, azioni, s)));
  const elimina = bottone('Elimina', 'sec', () => {
    if (!elimina.dataset.sicuro) {   // due tocchi: il primo chiede conferma, il secondo elimina (senza finestre del browser)
      elimina.dataset.sicuro = '1';
      elimina.textContent = 'Sicuro?';
      setTimeout(() => { delete elimina.dataset.sicuro; elimina.textContent = 'Elimina'; }, 3000);
      return;
    }
    segnalibri.elimina(l.id, s.id);
    log('segnalibro eliminato');
    disegnaSegnalibri();
    aggiornaElencoCapitoli();
  });
  azioni.appendChild(elimina);
  div.appendChild(azioni);
  return div;
}

function modificaNotaNellElenco(div, azioni, s) {
  const campo = crea('input');
  campo.type = 'text'; campo.maxLength = 300; campo.placeholder = 'Nota (facoltativa)'; campo.value = s.nota || '';
  const salva = () => {
    segnalibri.impostaNota(libroAperto.id, s.id, campo.value);
    log('segnalibro: nota salvata');
    disegnaSegnalibri();
  };
  campo.onkeydown = (ev) => { if (ev.key === 'Enter') salva(); };
  azioni.textContent = '';
  azioni.append(bottone('Salva', null, salva), bottone('Annulla', 'sec', () => disegnaSegnalibri()));
  div.insertBefore(campo, azioni);
  campo.focus();
}

// "Vai": apre il capitolo del segnalibro FERMO, all'inizio di quella frase (il Play lo premi tu, come per "Riprendi")
function vaiAlSegnalibro(s) {
  const l = libroAperto;
  const i = indiceCapitolo(s.cap);
  if (!l || i < 0) return;
  $('pannello-segnalibri').hidden = true;
  if (lettore.eCorrente(l.id, i)) { lettore.vaiA(s.t); mostra('lettore'); return; }   // già caricato: basta spostarsi
  avviaCapitolo(i, { da: s.t });
}

function apriSegnalibri() { disegnaSegnalibri(); $('pannello-segnalibri').hidden = false; }
$('btn-segnalibri').onclick = apriSegnalibri;
$('btn-elenco-seg').onclick = apriSegnalibri;
$('seg-chiudi').onclick = () => { $('pannello-segnalibri').hidden = true; aggiornaElencoCapitoli(); };

// ---------- Statistiche ----------
function durataBreve(s) {
  if (s < 1) return '0 min';
  if (s < 60) return 'meno di 1 min';
  return durataLunga(s);
}
function giornoCorto(chiave) { const p = chiave.split('-'); return p[2] + '/' + p[1]; }   // "2026-11-12" -> "12/11"

function apriStatistiche() {
  statistiche.salva();   // include anche l'ascolto di adesso
  const r = statistiche.riepilogo();
  const corpo = $('stat-corpo');
  corpo.textContent = '';
  const riga = (a, b) => { const d = crea('div', 'stat-riga'); d.append(crea('span', null, a), crea('span', null, b)); return d; };
  corpo.append(riga('Oggi', durataBreve(r.oggi)), riga('Ultimi 7 giorni', durataBreve(r.settimana)), riga('Totale', durataBreve(r.totale)));
  corpo.appendChild(crea('div', 'stat-titolo', 'Per libro'));
  if (!r.perLibro.length) corpo.appendChild(crea('p', 'piccolo', 'Ancora niente: le statistiche partono dal primo ascolto.'));
  for (const x of r.perLibro) corpo.appendChild(riga(x.titolo, durataBreve(x.secondi)));
  corpo.appendChild(crea('div', 'stat-titolo', 'Ultimi 14 giorni'));
  const massimo = Math.max(60, ...r.giorni.map((g) => g.secondi));
  for (const g of r.giorni) {
    const d = crea('div', 'stat-giorno');
    const barra = crea('div', 'stat-barra');
    const pieno = crea('div');
    pieno.style.width = Math.round((g.secondi / massimo) * 100) + '%';
    barra.appendChild(pieno);
    const testo = g.secondi >= 60 ? Math.round(g.secondi / 60) + ' min' : (g.secondi > 0 ? '<1 min' : '–');
    d.append(crea('span', null, giornoCorto(g.data)), barra, crea('span', null, testo));
    corpo.appendChild(d);
  }
  corpo.appendChild(crea('p', 'piccolo', 'Si conta il tempo in cui l’audio suona davvero, a qualsiasi velocità. Il conteggio parte da questa versione dell’app.'));
  $('pannello-stat').hidden = false;
}
$('btn-stat').onclick = apriStatistiche;
$('stat-chiudi').onclick = () => { $('pannello-stat').hidden = true; };

// ---------- Registro ----------
collegaPannello({ righe: $('reg-righe'), copia: $('reg-copia'), condividi: $('reg-condividi'), pulisci: $('reg-pulisci') });
$('btn-registro').onclick = () => { $('pannello-registro').hidden = false; aggiornaInfoLab(); };
$('reg-chiudi').onclick = () => { $('pannello-registro').hidden = true; };

// ---------- Controllo delle funzioni del telefono ----------
function controllaFunzioni() {
  const mancano = [];
  if (!('indexedDB' in window)) mancano.push('IndexedDB (database del browser)');
  if (!(window.crypto && crypto.subtle)) mancano.push('crypto.subtle (serve una connessione sicura https)');
  if (typeof DecompressionStream === 'undefined') mancano.push('DecompressionStream (serve iOS 16.4 o più recente)');
  else { try { new DecompressionStream('deflate-raw'); } catch (e) { mancano.push('decompressione deflate-raw (serve iOS 16.4 o più recente)'); } }
  if (!('serviceWorker' in navigator)) log('service worker non supportato: l’app non funzionerà offline');
  if (mancano.length) {
    const el = $('msg-funzioni');
    el.textContent = 'Questo browser non ha tutto ciò che serve: ' + mancano.join('; ') + '. L’importazione dei libri non funzionerà.';
    el.hidden = false;
    $('btn-importa').disabled = true;
    log('funzioni mancanti: ' + mancano.join('; '), true);
  }
  return mancano.length === 0;
}

// ---------- Aggiornamento dell'app (service worker) ----------
// La versione nuova resta "in attesa": la attivo solo quando tocchi "Aggiorna", mai mentre suona l'audio o c'è un'importazione.
let approvaRicarica = false;
async function registraServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  if (location.search.indexOf('nosw') >= 0) {      // modalità di sviluppo: nessun service worker (?nosw)
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const r of regs) await r.unregister();
    log('service worker disattivato (?nosw)');
    return;
  }
  try {
    const reg = await navigator.serviceWorker.register('sw.js');
    diagnosiServiceWorker(reg);   // scrive nel Registro se il service worker sta davvero lavorando
    // Al primissimo avvio il service worker si sta ancora installando: scrivo una seconda riga appena è attivo
    if (!reg.active) navigator.serviceWorker.ready.then(() => diagnosiServiceWorker(reg)).catch(() => {});
    const controllaAttesa = () => { if (reg.waiting && navigator.serviceWorker.controller) mostraAvvisoAggiornamento(reg.waiting); };
    controllaAttesa();
    reg.addEventListener('updatefound', () => {
      const n = reg.installing;
      if (!n) return;
      n.addEventListener('statechange', () => { if (n.state === 'installed') controllaAttesa(); });
    });
    navigator.serviceWorker.addEventListener('controllerchange', () => { if (approvaRicarica) location.reload(); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) reg.update().catch(() => {}); });
  } catch (e) { errore('service worker', e); }
}

// Diagnosi: UNA riga nel Registro che dice se il service worker (la parte che fa funzionare l'app senza internet)
// è attivo, se controlla questa pagina, quali cache dell'app ci sono e se il browser pensa di avere la rete.
// "controlla questa pagina: NO" è normale solo al primissimo avvio dopo l'installazione; dal secondo avvio deve essere SÌ.
async function diagnosiServiceWorker(reg) {
  try {
    const stati = [];
    if (reg.active) stati.push('attivo');
    if (reg.waiting) stati.push('versione nuova in attesa');
    if (reg.installing) stati.push('in installazione');
    const controlla = !!navigator.serviceWorker.controller;
    const dettaglio = [];
    if (window.caches) {
      for (const nome of await caches.keys()) {
        if (!nome.startsWith('app-')) continue;
        const c = await caches.open(nome);
        dettaglio.push(nome + ' (' + (await c.keys()).length + ' file)');
      }
    }
    log('service worker: ' + (stati.join(', ') || 'nessuno') +
        ' · controlla questa pagina: ' + (controlla ? 'SÌ' : 'NO (normale solo al primissimo avvio)') +
        ' · cache: ' + (dettaglio.join(', ') || 'nessuna') +
        ' · rete secondo il browser: ' + (navigator.onLine ? 'presente' : 'ASSENTE'));
  } catch (e) {
    log('service worker: diagnosi non riuscita (' + (e && e.message ? e.message : e) + ')', true);
  }
}

function mostraAvvisoAggiornamento(worker) {
  log('versione nuova dell’app pronta (in attesa)');
  const barra = $('avviso-aggiornamento');
  barra.hidden = false;
  $('btn-aggiorna').onclick = () => {
    if (lettore.staSuonando() || importazioneInCorso) {
      $('avviso-aggiornamento-testo').textContent = 'Metti in pausa (o aspetta la fine dell’importazione), poi tocca Aggiorna.';
      return;
    }
    approvaRicarica = true;
    worker.postMessage('salta-attesa');
  };
}

// ---------- Avvio ----------
async function avvia() {
  log('app avviata · ' + (window.navigator.standalone === true || matchMedia('(display-mode: standalone)').matches ? 'aperta dall’icona' : 'aperta dal browser'));
  controllaFunzioni();
  lettore.init({ audio: $('audio'), audio2: $('audio2'), ui });
  ui.stato(false);
  $('btn-prec').disabled = true;
  $('btn-succ').disabled = true;
  inizializzaLab({ importaFile: eseguiImportazione });
  await disegnaLibreria();
  registraServiceWorker();
}
avvia().catch((e) => errore('avvio', e));
