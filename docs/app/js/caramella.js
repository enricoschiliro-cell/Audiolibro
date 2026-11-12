// Caramella, la mascotte: uno spirito arancione pixel-art 24×24, disegnato dal codice (righe di testo, una lettera per colore).
// Pose e fotogrammi vengono dal componente "Mascotte" del design system Claude Code Retro; la posa "legge" (con il libro) è nuova.
// Regole del design system: scala solo ×2 o ×3 (lo decide il CSS: .caramella e .caramella.x2, con image-rendering: pixelated),
// 11 fotogrammi al secondo, colori presi dai token cc-* (variabili CSS), mai sfumata. Con "movimento ridotto" resta su un fotogramma fermo.

const FPS = 11;
const FRAME_MS = 1000 / FPS;
const riduci = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

// ---------- Colori: letti dai token (variabili CSS), con miscele come nel design system ----------
function cv(nome, riserva) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  return v || riserva;
}
function analizza(h) {
  let m = h.trim().replace('#', '');
  if (m.length === 3) m = m.split('').map((c) => c + c).join('');
  if (!/^[0-9a-fA-F]{6}$/.test(m)) return null;
  return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16));
}
function mescola(a, b, t) {
  const pa = analizza(a), pb = analizza(b);
  if (!pa || !pb) return a;
  return '#' + pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('');
}
let paletta = null;
function leggiPaletta() {
  const arancio = cv('--cc-orange', '#d97757'), arancioChiaro = cv('--cc-orange-hover', '#eb9b7c');
  const verde = cv('--cc-green', '#9db383'), fondo = cv('--cc-bg-deep', '#0f0f0e');
  const blu = cv('--cc-blue', '#8fa8c4'), testo = cv('--cc-text', '#e8e6dc');
  paletta = {
    o: arancio, O: arancioChiaro, h: mescola(arancioChiaro, testo, 0.6),
    q: mescola(arancio, fondo, 0.11), k: mescola(arancio, fondo, 0.22), x: mescola(arancio, fondo, 0.5),
    a: cv('--cc-amber', '#d4a27f'), y: cv('--cc-yellow', '#d8b46a'),
    t: testo, d: fondo, u: blu, U: mescola(blu, fondo, 0.45),
    m: cv('--cc-text-muted', '#8f8b81'), f: cv('--cc-text-faint', '#6b675f'), b: cv('--cc-border-strong', '#4a463f'),
    g: verde, G: mescola(verde, fondo, 0.45), r: cv('--cc-red', '#d4747c'),
  };
  return paletta;
}

// ---------- Sprite: '.' = trasparente ----------
const CORPO = [
  '........................', '........................', '........................',
  '........................', '........................', '........................',
  '..........xxxx..........', '........xxOOOOxx........', '......xxOOOOooooxx......',
  '.....xOOhOoooooooox.....', '....xOOhooooooooooox....', '....xOooooooooooooox....',
  '....xoooooooooooooox....', '....xoooooooooooooox....', '....xooooooooooooqqx....',
  '....xooooooooooqqqqx....', '....xooooooooqqqqqqx....', '....xooooooqqqqqqqkx....',
  '....xooooqqqqqqqkkkx....', '....xooqqqqqqqkkkkkx....',
];
const GONNA = [
  ['....xqqxxqqxxkkxxkkx....', '.....xx..xx..xx..xx.....'],
  ['....xxxqqxxqkxxkkxxx....', '....x..xx..xx..xx..x....'],
];
const GONNA_DY = 20;
const OCCHI = {
  open: { rows: ['d', 'd', 'd'], dxL: 0, dxR: 0, dy: 0 },
  blink: { rows: ['d'], dxL: 0, dxR: 0, dy: 2 },
  happy: { rows: ['.d.', 'd.d'], dxL: -1, dxR: -1, dy: 0 },
  sleep: { rows: ['dd'], dxL: -1, dxR: 0, dy: 2 },
};
const OCCHI_X = { '-1': [8, 11], '0': [10, 13], '1': [12, 15] };
const OCCHI_Y = 12;
const Z_PICCOLA = ['mmm', '..m', '.m.', 'mmm'];
const Z_GRANDE = ['mmmmm', '...m.', '..m..', '.m...', 'mmmmm'];
const BRACCIO_DX = 19, BRACCIO_DY = 9;
const BRACCIO = [
  ['.xx.', 'xoox', 'xoox', 'xoox', 'xoox', 'ooox', '.xxx'],
  ['.....', '.....', '.....', '.xxx.', 'oooox', '.xxx.'],
];
const OMBRA = ['.bbbbbbbbbbbb.'], OMBRA_DX = 5, OMBRA_Y = 23;
const CUORE_GRANDE = ['.r.r.', 'rhrrr', '.rrr.', '..r..'];
const CUORE_PICCOLO = ['r.r', 'rrr', '.r.'];
// Il libro aperto (nuovo): due pagine color testo con le righe di scrittura, bordo scurissimo. Tre fotogrammi: aperto, pagina che si gira, aperto con l'altra pagina.
const LIBRO = [
  ['.dddd.dddd.', 'dttttdttttd', 'dtmmmdtmmmd', 'dttttdttttd', 'dtmmmdtmmmd', '.dddd.dddd.'],
  ['.dddd.dddd.', 'dttttdhttd.', 'dtmmmdhttd.', 'dttttdhttd.', 'dtmmmdhttd.', '.dddd.dddd.'],
  ['.dddd.dddd.', 'dttttdttttd', 'dtmmmdtmmmd', 'dttttdttttd', 'dtmmmdtmmmd', '.dddd.dddd.'],
];
const LIBRO_DX = 6, LIBRO_DY = 16;

const POSA_BASE = { bob: 0, dx: 0, recoil: 0, skirt: 0, eyes: 'open', look: 1, lookY: 0, zzz: -1, arm: 0, shadow: false, fx: 'none', fxPhase: 0, book: 0 };

function disegnaRighe(ctx, righe, dx, dy) {
  const pal = paletta || leggiPaletta();
  for (let y = 0; y < righe.length; y++) {
    for (let x = 0; x < righe[y].length; x++) {
      const ch = righe[y][x];
      if (ch === '.' || ch === ' ' || !pal[ch]) continue;
      ctx.fillStyle = pal[ch];
      ctx.fillRect(dx + x, dy + y, 1, 1);
    }
  }
}

// Strati dal fondo: ombra, corpo, gonna, braccio, libro, occhi, effetti
function componi(p) {
  const L = [];
  const ox = p.dx - p.recoil * (p.look >= 0 ? 1 : -1);
  if (p.shadow && p.bob <= 1) L.push([OMBRA, OMBRA_DX + ox, OMBRA_Y]);
  L.push([CORPO, ox, p.bob]);
  L.push([GONNA[p.skirt], ox, GONNA_DY + p.bob]);
  if (p.arm > 0) L.push([BRACCIO[p.arm - 1], BRACCIO_DX + ox, BRACCIO_DY + p.bob]);
  if (p.book > 0) L.push([LIBRO[p.book - 1], LIBRO_DX + ox, LIBRO_DY + p.bob]);
  const e = OCCHI[p.eyes], xs = OCCHI_X[p.look], ey = OCCHI_Y + p.lookY + p.bob + e.dy;
  L.push([e.rows, xs[0] + e.dxL + ox, ey]);
  L.push([e.rows, xs[1] + e.dxR + ox, ey]);
  const z = p.zzz;
  if (z >= 0 && z <= 5) L.push([Z_PICCOLA, 16, 4 - Math.floor(z / 2)]);
  if (z >= 4 && z <= 11) L.push([Z_GRANDE, 18, 2 - Math.floor((z - 4) / 3)]);
  const f = p.fxPhase;
  if (p.fx === 'hearts') {
    if (f <= 5) L.push([CUORE_GRANDE, 10, 2 - Math.floor(f / 3)]);
    if (f >= 3 && f <= 9) L.push([CUORE_PICCOLO, 16, 3 - Math.floor((f - 3) / 3)]);
  }
  return L;
}

// ---------- Animazioni (11 fotogrammi al secondo) ----------
const serie = (n, fn) => Array.from({ length: n }, (_, i) => fn(i));
const alt = (i, ogni) => Math.floor(i / ogni) % 2;
const BOB_LENTO = [0, 0, -1, -1, -1, -1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0];
const BOB_VELOCE = [0, -1, -1, 0, 0, 1, 1, 0];
const fermo = { loop: true, fermo: 0, frames: serie(16, (i) => ({ bob: BOB_LENTO[i], skirt: Math.floor(i / 4) % 2 })) };
const palpebre = { loop: true, fermo: 0, frames: fermo.frames.map((f, i) => (i === 7 || i === 8 ? { ...f, eyes: 'blink' } : f)) };
const fluttua = { loop: true, fermo: 1, frames: serie(8, (i) => ({ bob: BOB_VELOCE[i], skirt: Math.floor(i / 2) % 2 })) };
const SEQ_SGUARDI = [[0, 0, 5], [1, 0, 8], [0, 0, 3], [-1, 0, 8], [0, 0, 3], [0, -1, 5]];
const intorno = {
  loop: true, fermo: 10,
  frames: [].concat(...SEQ_SGUARDI.map(([look, lookY, n]) => serie(n, () => ({ look, lookY }))))
    .map((f, i) => ({ ...f, bob: BOB_LENTO[i % 16], skirt: Math.floor(i / 4) % 2 })),
};
const SALTO = [0, 1, 1, -1, -3, -4, -5, -5, -5, -4, -3, -1, 0, 1, 0, 0];
const saltello = {
  loop: false, fermo: 7,
  frames: SALTO.map((bob, i) => ({ bob, skirt: i >= 3 && i <= 11 ? 1 : 0, eyes: i >= 5 && i <= 9 ? 'happy' : 'open', lookY: i >= 3 && i <= 6 ? -1 : 0 })),
};
const dorme = { loop: true, fermo: 14, frames: serie(24, (i) => ({ bob: i < 12 ? 1 : 2, skirt: 0, eyes: 'sleep', look: 0, shadow: true, zzz: Math.floor(i / 2) })) };
const BRACCIO_SALUTO = [0, 0, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 1, 2, 0, 0, 0, 0, 0];
const saluta = {
  loop: false, fermo: 6,
  frames: BRACCIO_SALUTO.map((arm, i) => ({ arm, look: 0, lookY: 0, eyes: i >= 3 && i <= 20 ? 'happy' : 'open', bob: i >= 2 && i <= 20 && i % 4 < 2 ? -1 : 0, skirt: alt(i, 3) })),
};
const coccole = {
  loop: false, fermo: 8,
  frames: serie(24, (i) => ({ eyes: i >= 2 && i <= 21 ? 'happy' : 'open', bob: i >= 1 && i <= 20 && i % 6 < 3 ? -1 : 0, skirt: alt(i, 3), fx: 'hearts', fxPhase: Math.floor(i / 2) })),
};
// Legge un libro (nuova): guarda in basso, ogni tanto gira la pagina e sbatte le palpebre
const legge = {
  loop: true, fermo: 4,
  frames: serie(32, (i) => ({
    bob: BOB_LENTO[i % 16], skirt: Math.floor(i / 4) % 2,
    look: 0, lookY: 1, eyes: i === 26 || i === 27 ? 'blink' : 'open',
    book: i >= 18 && i <= 20 ? 2 : (i > 20 ? 3 : 1),
  })),
};
const ANIMAZIONI = { fermo, palpebre, 'si guarda intorno': intorno, fluttua, saltello, dorme, saluta, coccole, legge };

export function nomiAnimazioni() { return Object.keys(ANIMAZIONI); }
export function numeroFotogrammi(nome) { return ANIMAZIONI[nome] ? ANIMAZIONI[nome].frames.length : 0; }

// Disegna un fotogramma su un canvas 24×24 (serve anche per fare le immagini di prova e la copertina)
export function disegnaFotogramma(canvas, nome, indice) {
  const clip = ANIMAZIONI[nome];
  if (!clip) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 24, 24);
  const posa = { ...POSA_BASE, ...clip.frames[indice % clip.frames.length] };
  for (const [righe, dx, dy] of componi(posa)) disegnaRighe(ctx, righe, dx, dy);
}

// ---------- Il motore: un solo orologio per tutte le Caramelle visibili ----------
const istanze = new Set();
let acceso = false, ultimo = 0, accumulo = 0;
function tic(adesso) {
  if (!acceso) return;
  accumulo = Math.min(accumulo + (adesso - ultimo), 500);
  ultimo = adesso;
  while (accumulo >= FRAME_MS) {
    accumulo -= FRAME_MS;
    for (const c of istanze) if (c.visibile()) c.passo();
  }
  requestAnimationFrame(tic);
}
function avvia() {
  if (acceso || riduci || document.hidden) return;
  acceso = true; ultimo = performance.now(); accumulo = 0;
  requestAnimationFrame(tic);
}
document.addEventListener('visibilitychange', () => { if (document.hidden) acceso = false; else avvia(); });

export class Caramella {
  constructor(canvas) {
    this.canvas = canvas;
    this.base = 'fermo';
    this.nome = 'fermo';
    this.indice = 0;
    this.unaVolta = false;
    this.attesa = null;
    istanze.add(this);
    this.disegna(riduci ? ANIMAZIONI.fermo.fermo : 0);
    avvia();
  }
  visibile() { return this.canvas.offsetParent !== null; }
  disegna(i) { disegnaFotogramma(this.canvas, this.nome, i); }
  cambia(nome) {
    this.nome = nome;
    this.indice = 0;
    this.disegna(riduci ? ANIMAZIONI[nome].fermo : 0);
  }
  // L'animazione di fondo, che si ripete (fermo, palpebre, si guarda intorno, fluttua, dorme, legge)
  imposta(nome) {
    if (!ANIMAZIONI[nome]) return;
    this.base = nome;
    if (!this.unaVolta && this.nome !== nome) this.cambia(nome);
  }
  // Un'animazione che si fa una volta sola (saluta, coccole, saltello) e poi si torna a quella di fondo
  gioca(nome) {
    if (!ANIMAZIONI[nome]) return;
    this.unaVolta = true;
    this.cambia(nome);
    if (riduci) {   // niente movimento: un fotogramma fermo per un attimo
      clearTimeout(this.attesa);
      this.attesa = setTimeout(() => { this.unaVolta = false; this.cambia(this.base); }, 1500);
    }
  }
  passo() {
    const clip = ANIMAZIONI[this.nome];
    const n = clip.frames.length;
    if (clip.loop) this.indice = (this.indice + 1) % n;
    else if (this.indice < n - 1) this.indice++;
    else { this.unaVolta = false; this.cambia(this.base); return; }
    this.disegna(this.indice);
  }
}
