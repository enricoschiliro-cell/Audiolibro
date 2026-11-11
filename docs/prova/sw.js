// Service worker della pagina di prova: salva i file sul telefono e li serve anche senza internet.
const CACHE = 'prova-v5';
const FILE = ['./', 'index.html', 'manifest.webmanifest', 'icona-180.png', 'icona-512.png', 'prova.wav'];

// Installazione: scarico e salvo tutti i file
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILE)).then(() => self.skipWaiting()));
});

// Attivazione: cancello le versioni vecchie della cache
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((k) => Promise.all(k.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// iPhone chiede l'audio "a pezzi" (richieste Range): devo rispondere con il pezzo giusto,
// altrimenti dalla cache l'audio non parte.
async function rispostaAPezzi(request, response) {
  const range = request.headers.get('range');
  if (!range) return response;
  const blob = await response.blob();
  const tot = blob.size;
  const m = /bytes=(\d*)-(\d*)/.exec(range) || [];
  let inizio, fine;
  if (m[1] === '' && m[2]) { inizio = Math.max(0, tot - parseInt(m[2], 10)); fine = tot - 1; }
  else { inizio = parseInt(m[1] || '0', 10); fine = m[2] ? Math.min(parseInt(m[2], 10), tot - 1) : tot - 1; }
  const pezzo = blob.slice(inizio, fine + 1);
  return new Response(pezzo, {
    status: 206,
    statusText: 'Partial Content',
    headers: {
      'Content-Type': response.headers.get('Content-Type') || 'audio/wav',
      'Content-Range': 'bytes ' + inizio + '-' + fine + '/' + tot,
      'Content-Length': String(pezzo.size),
      'Accept-Ranges': 'bytes'
    }
  });
}

// Ogni richiesta: prima cerco nella cache, se non c'è vado in rete.
// Eccezione: la pagina stessa la chiedo prima alla rete, così le versioni nuove arrivano subito
// (senza rete uso quella salvata).
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  if (e.request.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const nuova = await fetch(e.request);
        const c = await caches.open(CACHE);
        c.put('index.html', nuova.clone());
        return nuova;
      } catch (err) {
        return (await caches.match('index.html')) || Response.error();
      }
    })());
    return;
  }
  e.respondWith((async () => {
    const inCache = await caches.match(e.request.url, { ignoreSearch: true });
    if (inCache) return rispostaAPezzi(e.request, inCache);
    return fetch(e.request);
  })());
});
