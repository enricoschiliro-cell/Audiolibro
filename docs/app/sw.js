// Service worker dell'app Audiolibro: salva sul telefono il CODICE e l'interfaccia dell'app, così funzionano anche senza internet.
// NON salva mai l'audio dei libri: i libri stanno in IndexedDB (vedi js/archivio.js).
//
// PRIMA DI OGNI PUBBLICAZIONE: se è cambiato un file elencato qui sotto, aumenta VERSIONE.
// Con un numero nuovo il telefono scarica tutti i file insieme e non può mescolare file vecchi e nuovi.
const VERSIONE = 4;
const CACHE = 'app-v' + VERSIONE;   // le cache dell'app cominciano sempre con "app-" (la pagina di prova usa altri nomi)
const FILE = [
  './', 'index.html', 'app.css', 'manifest.webmanifest', 'icona-180.png', 'icona-512.png',
  'js/main.js', 'js/util.js', 'js/registro.js', 'js/zip.js', 'js/archivio.js', 'js/importa.js', 'js/lettore.js', 'js/testo.js', 'js/lab.js',
  'js/timer.js', 'js/statistiche.js', 'js/segnalibri.js', 'js/caramella.js', 'js/aspetto.js'
];

// Installazione: scarico e salvo tutti i file. NIENTE skipWaiting: la versione nuova resta "in attesa"
// finché l'utente tocca "Aggiorna" (così la pagina non si ricarica mentre suona l'audio o c'è un'importazione).
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILE)));
});

// Attivazione: cancello SOLO le cache vecchie dell'app (quelle che cominciano con "app-").
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((chiavi) => Promise.all(chiavi.filter((n) => n.startsWith('app-') && n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// La pagina chiede di attivare subito la versione nuova (tocco su "Aggiorna").
self.addEventListener('message', (e) => {
  if (e.data === 'salta-attesa') self.skipWaiting();
});

// Ogni richiesta dello stesso sito: prima la cache di QUESTA versione, poi la rete.
// Anche la pagina (index.html) viene dalla cache: pagina e moduli sono sempre della stessa versione.
self.addEventListener('fetch', (e) => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const url = new URL(r.url);
  if (url.origin !== self.location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const salvata = await cache.match(r, { ignoreSearch: true });
    if (salvata) return salvata;
    try {
      return await fetch(r);
    } catch (err) {
      // Pagina aperta senza rete con un indirizzo non salvato: ripiego sulla pagina principale
      if (r.mode === 'navigate') {
        const home = await cache.match('index.html');
        if (home) return home;
      }
      return Response.error();
    }
  })());
});
