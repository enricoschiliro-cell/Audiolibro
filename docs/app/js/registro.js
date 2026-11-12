// Registro degli eventi: un "diario" salvato sul telefono, così lo ritrovi dopo aver bloccato lo schermo
// e puoi copiarlo o condividerlo per capire cosa è successo senza un computer collegato.
// Tutte le chiavi di salvataggio locale di questa app cominciano con "al." (la pagina di prova usa nomi diversi).

const CHIAVE = 'al.registro';
const MASSIMO_RIGHE = 300;

let righe = [];   // { t: testo, err: true/false }
try { righe = JSON.parse(localStorage.getItem(CHIAVE) || '[]'); } catch (e) { righe = []; }
let elRighe = null;

function salva() {
  try { localStorage.setItem(CHIAVE, JSON.stringify(righe)); } catch (e) { /* senza salvataggio il registro vale solo finché l'app è aperta */ }
}

function disegna() {
  if (!elRighe) return;
  elRighe.textContent = '';
  for (const r of righe.slice().reverse()) {      // la più recente in alto
    const d = document.createElement('div');
    d.textContent = r.t;                           // textContent: nessun testo viene scambiato per HTML
    if (r.err) d.className = 'err';
    elRighe.appendChild(d);
  }
}

export function log(testo, err = false) {
  const ora = new Date().toLocaleTimeString('it-IT');
  righe.push({ t: ora + '  ' + testo, err });
  if (righe.length > MASSIMO_RIGHE) righe = righe.slice(-MASSIMO_RIGHE);
  salva();
  disegna();
}

export function errore(contesto, e) {
  const nome = e && e.name ? e.name : 'Errore';
  const msg = e && e.message ? e.message : String(e);
  log('ERRORE ' + contesto + ': ' + nome + ': ' + msg, true);
}

export function testoCompleto() {
  return righe.map((r) => r.t).join('\n');
}

async function copiaTesto(testo) {
  try {
    await navigator.clipboard.writeText(testo);
    return true;
  } catch (e) {
    // Ripiego per i browser senza permesso sugli appunti
    const ta = document.createElement('textarea');
    ta.value = testo;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
    ta.remove();
    return ok;
  }
}

// Collega il pannello della pagina: elenco delle righe e tasti Copia / Condividi / Pulisci
export function collegaPannello({ righe: elencoRighe, copia, condividi, pulisci }) {
  elRighe = elencoRighe;
  disegna();
  copia.onclick = async () => {
    const ok = await copiaTesto(testoCompleto());
    copia.textContent = ok ? 'Copiato ✓' : 'Non riuscito';
    setTimeout(() => { copia.textContent = 'Copia'; }, 2000);
  };
  condividi.onclick = async () => {
    const testo = testoCompleto();
    if (navigator.share) {
      try { await navigator.share({ title: 'Registro Audiolibro', text: testo }); return; } catch (e) { if (e && e.name === 'AbortError') return; }
    }
    await copiaTesto(testo);
    condividi.textContent = 'Copiato ✓';
    setTimeout(() => { condividi.textContent = 'Condividi'; }, 2000);
  };
  pulisci.onclick = () => { righe = []; salva(); disegna(); };
}

// Errori che nessuno ha intercettato: finiscono comunque nel registro
window.addEventListener('error', (ev) => log('ERRORE non gestito: ' + ev.message + (ev.filename ? ' (' + ev.filename.split('/').pop() + ':' + ev.lineno + ')' : ''), true));
window.addEventListener('unhandledrejection', (ev) => errore('promessa non gestita', ev.reason));
