// Lettore minimo di file ZIP, scritto per questa app (nessuna libreria).
// Legge solo i pezzi che servono (File.slice), quindi uno zip da 100 MB non viene mai caricato tutto in memoria.
// Supporta solo ciò che usa il nostro pacchetto: metodo 0 (STORED, senza compressione) e 8 (DEFLATED), niente cifratura, niente zip64.
//
// Come è fatto uno zip (in breve): in fondo al file c'è una "fine dell'indice" (EOCD) che dice dove sta l'indice (directory centrale);
// l'indice elenca ogni file con nome, metodo, dimensioni e posizione della sua intestazione locale, seguita dai dati.

const FIRMA_FINE = 0x06054b50;
const FIRMA_INDICE = 0x02014b50;
const FIRMA_LOCALE = 0x04034b50;

export async function apriZip(file) {
  const dim = file.size;
  if (dim < 22) throw new Error('il file è troppo piccolo per essere uno zip');

  // 1) Ultimi byte del file: la "fine dell'indice" sta lì (può esserci un commento lungo al massimo 65535 byte)
  const lunghezzaCoda = Math.min(dim, 22 + 65535);
  const coda = new DataView(await file.slice(dim - lunghezzaCoda, dim).arrayBuffer());
  let posFine = -1;
  for (let i = lunghezzaCoda - 22; i >= 0; i--) {
    if (coda.getUint32(i, true) === FIRMA_FINE) { posFine = i; break; }
  }
  if (posFine < 0) throw new Error('manca la fine dell’indice: non sembra un file zip');
  const quanteVoci = coda.getUint16(posFine + 10, true);
  const dimIndice = coda.getUint32(posFine + 12, true);
  const posIndice = coda.getUint32(posFine + 16, true);
  if (quanteVoci === 0xFFFF || dimIndice === 0xFFFFFFFF || posIndice === 0xFFFFFFFF) throw new Error('zip64 non supportato');
  if (posIndice + dimIndice > dim) throw new Error('indice dello zip fuori dal file (file incompleto?)');

  // 2) L'indice: nome, metodo e dimensioni di ogni file
  const indice = new DataView(await file.slice(posIndice, posIndice + dimIndice).arrayBuffer());
  const decodificaNome = new TextDecoder('utf-8');
  const voci = new Map();
  let o = 0;
  for (let n = 0; n < quanteVoci; n++) {
    if (o + 46 > indice.byteLength || indice.getUint32(o, true) !== FIRMA_INDICE) throw new Error('indice dello zip danneggiato');
    const flag = indice.getUint16(o + 8, true);
    const metodo = indice.getUint16(o + 10, true);
    const byteCompressi = indice.getUint32(o + 20, true);
    const byteReali = indice.getUint32(o + 24, true);
    const lenNome = indice.getUint16(o + 28, true);
    const lenExtra = indice.getUint16(o + 30, true);
    const lenCommento = indice.getUint16(o + 32, true);
    const posLocale = indice.getUint32(o + 42, true);
    const nome = decodificaNome.decode(new Uint8Array(indice.buffer, indice.byteOffset + o + 46, lenNome));
    if (flag & 1) throw new Error('file cifrato non supportato: ' + nome);
    if (metodo !== 0 && metodo !== 8) throw new Error('metodo di compressione ' + metodo + ' non supportato: ' + nome);
    if (posLocale >= dim) throw new Error('posizione non valida per ' + nome);
    voci.set(nome, { nome, metodo, byteCompressi, byteReali, posLocale });
    o += 46 + lenNome + lenExtra + lenCommento;
  }

  // 3) Lettura di un file dello zip, già decompresso (come blocco di byte)
  async function leggi(nome) {
    const v = voci.get(nome);
    if (!v) throw new Error('nello zip manca ' + nome);
    const intestazione = new DataView(await file.slice(v.posLocale, v.posLocale + 30).arrayBuffer());
    if (intestazione.byteLength < 30 || intestazione.getUint32(0, true) !== FIRMA_LOCALE) throw new Error('intestazione danneggiata per ' + nome);
    const inizioDati = v.posLocale + 30 + intestazione.getUint16(26, true) + intestazione.getUint16(28, true);
    if (inizioDati + v.byteCompressi > dim) throw new Error('dati fuori dal file per ' + nome + ' (file incompleto?)');
    const pezzo = file.slice(inizioDati, inizioDati + v.byteCompressi);
    let byte;
    if (v.metodo === 0) {
      byte = new Uint8Array(await pezzo.arrayBuffer());
    } else {
      // "deflate-raw" è il formato di compressione dentro lo zip; il browser lo sa già decomprimere
      const flusso = pezzo.stream().pipeThrough(new DecompressionStream('deflate-raw'));
      byte = new Uint8Array(await new Response(flusso).arrayBuffer());
    }
    if (byte.byteLength !== v.byteReali) throw new Error('dimensione inattesa per ' + nome + ' (' + byte.byteLength + ' invece di ' + v.byteReali + ')');
    return byte;
  }

  return { voci, leggi, ha: (nome) => voci.has(nome) };
}
