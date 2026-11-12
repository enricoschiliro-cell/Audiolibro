// Importazione di un pacchetto (zip) nell'archivio del telefono.
// Un solo meccanismo per tre casi: libro nuovo, ripresa dopo un'interruzione, aggiornamento di un libro già presente:
// ogni capitolo già salvato con le stesse firme viene saltato, gli altri vengono letti, controllati e salvati uno alla volta.
// Se l'importazione si ferma a metà (app chiusa, iOS la sospende), i capitoli già salvati restano e il libro risulta
// "Importazione incompleta": riscegliendo lo stesso zip si continua da dove si era arrivati.

import { log, errore } from './registro.js';
import { apriZip } from './zip.js';
import { sha256Hex, mbLeggibili } from './util.js';
import * as arch from './archivio.js';

const VERSIONE_CONOSCIUTA = 1;                    // la versione più nuova del formato che questa app sa leggere
const RE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;       // lettere minuscole, numeri e trattini (l'id diventa parte delle chiavi del database)

export class ErroreImportazione extends Error {
  constructor(messaggio) { super(messaggio); this.name = 'ErroreImportazione'; }
}

function controllaManifest(m, zip) {
  if (!m || m.formato !== 'audiolibro-pacchetto') throw new ErroreImportazione('Questo file non è un pacchetto di audiolibro (formato non riconosciuto).');
  if (!Number.isInteger(m.versione) || m.versione < 1) throw new ErroreImportazione('Il pacchetto ha un numero di versione non valido.');
  if (m.versione > VERSIONE_CONOSCIUTA) {
    throw new ErroreImportazione('Questo pacchetto è di una versione più nuova (' + m.versione + ') di quelle che l’app conosce (' + VERSIONE_CONOSCIUTA + '). Aggiorna l’app e riprova.');
  }
  if (!m.libro || typeof m.libro.id !== 'string' || !RE_ID.test(m.libro.id) || m.libro.id.length > 80) {
    throw new ErroreImportazione('L’identificativo del libro nel pacchetto non è valido.');
  }
  if (!Array.isArray(m.capitoli) || m.capitoli.length === 0) throw new ErroreImportazione('Il pacchetto non contiene capitoli.');
  const visti = new Set();
  for (const c of m.capitoli) {
    if (typeof c.id !== 'string' || !RE_ID.test(c.id)) throw new ErroreImportazione('Un capitolo ha un identificativo non valido.');
    if (visti.has(c.id)) throw new ErroreImportazione('Il capitolo ' + c.id + ' compare due volte nel pacchetto.');
    visti.add(c.id);
    for (const [campo, dim] of [['audio', 'byte_audio'], ['tempi', 'byte_tempi']]) {
      const voce = zip.voci.get(c[campo]);
      if (!voce) throw new ErroreImportazione('Nello zip manca il file ' + c[campo] + ' (capitolo ' + c.id + ').');
      if (voce.byteReali !== c[dim]) throw new ErroreImportazione('Il file ' + c[campo] + ' ha una dimensione diversa da quella dichiarata: il pacchetto è danneggiato.');
    }
    if (typeof c.sha256_audio !== 'string' || typeof c.sha256_tempi !== 'string') throw new ErroreImportazione('Mancano le firme del capitolo ' + c.id + '.');
  }
}

// avanza({ testo, percentuale }) viene chiamata a ogni passo, per la barra di avanzamento
export async function importaPacchetto(file, avanza = () => {}) {
  const t0 = performance.now();
  log('importazione: ' + file.name + ' (' + mbLeggibili(file.size) + ')');
  avanza({ testo: 'Apro il file…', percentuale: 0 });

  // 1) Apertura dello zip e lettura del manifest
  let zip;
  try { zip = await apriZip(file); } catch (e) { throw new ErroreImportazione('Non riesco ad aprire il file come zip: ' + e.message + '.'); }
  if (!zip.ha('manifest.json')) throw new ErroreImportazione('Nello zip manca manifest.json: non è un pacchetto di audiolibro.');
  let manifest;
  try { manifest = JSON.parse(new TextDecoder().decode(await zip.leggi('manifest.json'))); } catch (e) { throw new ErroreImportazione('Il manifest del pacchetto è illeggibile: ' + e.message + '.'); }
  controllaManifest(manifest, zip);
  const id = manifest.libro.id;
  const totaleByte = manifest.capitoli.reduce((s, c) => s + c.byte_audio + c.byte_tempi, 0);
  log('manifest ok: «' + manifest.libro.titolo + '», ' + manifest.capitoli.length + ' capitoli, ' + mbLeggibili(totaleByte) + ' da salvare');

  // 2) Libro già presente? Riprendo da dove ero (i capitoli con le stesse firme si saltano)
  const esistente = await arch.leggiLibro(id);
  const salvati = Object.assign({}, esistente && esistente.salvati);
  let giaSalvati = 0;
  let byteGiaSalvati = 0;
  for (const c of manifest.capitoli) {
    const s = salvati[c.id];
    if (s && s.a === c.sha256_audio && s.t === c.sha256_tempi) { giaSalvati++; byteGiaSalvati += c.byte_audio + c.byte_tempi; }
  }
  if (esistente) log('libro già presente (' + esistente.stato + '): ' + giaSalvati + ' capitoli già a posto, li salto');

  // 3) Spazio: avviso (non blocca: la stima del telefono può essere prudente; se manca davvero lo spazio lo scopriamo salvando)
  const sp = await arch.spazio();
  const daSalvare = totaleByte - byteGiaSalvati;
  if (sp.quota != null && sp.usato != null && (sp.quota - sp.usato) < daSalvare * 1.2) {
    log('ATTENZIONE: spazio libero stimato ' + mbLeggibili(sp.quota - sp.usato) + ', servono circa ' + mbLeggibili(daSalvare), true);
    avanza({ testo: 'Attenzione: lo spazio libero potrebbe non bastare.', percentuale: 0, avviso: true });
  }

  // 4) Copertina (piccola) e record del libro. Il record NON viene scritto adesso: viene scritto insieme al primo capitolo
  //    che si salva davvero (come "importazione", così se si interrompe si vede). In questo modo un pacchetto difettoso
  //    (per esempio con una firma sbagliata) non rovina un libro già importato correttamente.
  let copertina = (esistente && esistente.copertina) || null;
  if (manifest.copertina && zip.ha(manifest.copertina)) {
    try {
      const bytes = await zip.leggi(manifest.copertina);
      if (bytes.byteLength < 5e6) copertina = new Blob([bytes], { type: 'image/jpeg' });
    } catch (e) { log('copertina non letta: ' + e.message); }
  }
  const record = {
    id, manifest, stato: 'importazione', salvati, copertina,
    importatoIl: (esistente && esistente.importatoIl) || Date.now(),
  };

  // 5) Un capitolo alla volta: leggo, controllo le firme, e solo dopo salvo (in una transazione sola)
  let fatti = byteGiaSalvati;
  for (let n = 0; n < manifest.capitoli.length; n++) {
    const c = manifest.capitoli[n];
    const etichetta = 'Capitolo ' + (n + 1) + ' di ' + manifest.capitoli.length;
    const s = salvati[c.id];
    if (s && s.a === c.sha256_audio && s.t === c.sha256_tempi) {
      log(c.id + ': già salvato, salto');
      continue;
    }
    const tc = performance.now();
    avanza({ testo: etichetta + ': leggo e controllo…', percentuale: Math.round((fatti / totaleByte) * 100) });
    let byteAudio, byteTempi, tempi;
    try {
      byteAudio = await zip.leggi(c.audio);
      if ((await sha256Hex(byteAudio)) !== c.sha256_audio.toLowerCase()) {
        throw new ErroreImportazione('La firma dell’audio del capitolo «' + (c.titolo_completo || c.id) + '» non coincide: il file è danneggiato (copia o download incompleto). Rifai la copia del pacchetto e riprova.');
      }
      byteTempi = await zip.leggi(c.tempi);
      if ((await sha256Hex(byteTempi)) !== c.sha256_tempi.toLowerCase()) {
        throw new ErroreImportazione('La firma dei tempi del capitolo «' + (c.titolo_completo || c.id) + '» non coincide: il file è danneggiato.');
      }
      tempi = JSON.parse(new TextDecoder().decode(byteTempi));
      if (!tempi || !Array.isArray(tempi.segmenti) || tempi.segmenti.length === 0) throw new ErroreImportazione('I tempi del capitolo ' + c.id + ' non sono validi.');
    } catch (e) {
      if (e instanceof ErroreImportazione) throw e;
      throw new ErroreImportazione('Errore leggendo il capitolo ' + c.id + ': ' + e.message);
    }
    avanza({ testo: etichetta + ': salvo sul telefono…', percentuale: Math.round((fatti / totaleByte) * 100) });
    salvati[c.id] = { a: c.sha256_audio, t: c.sha256_tempi };
    try {
      await arch.salvaCapitolo(id, c.id, byteAudio, tempi, record);
    } catch (e) {
      delete salvati[c.id];
      if (e && e.name === 'QuotaExceededError') {
        throw new ErroreImportazione('Spazio esaurito sul telefono. Libera spazio e riprova: i capitoli già importati restano, riscegli lo stesso file per continuare.');
      }
      errore('salvataggio capitolo ' + c.id, e);
      throw new ErroreImportazione('Non riesco a salvare il capitolo ' + c.id + ': ' + (e && e.message ? e.message : e));
    }
    fatti += c.byte_audio + c.byte_tempi;
    log(c.id + ': salvato in ' + Math.round(performance.now() - tc) + ' ms (' + mbLeggibili(c.byte_audio) + ')');
  }

  // 6) Chiusura: tolgo i capitoli che non sono più nel pacchetto e segno il libro "pronto"
  const attuali = new Set(manifest.capitoli.map((c) => c.id));
  const daTogliere = Object.keys(salvati).filter((k) => !attuali.has(k));
  await arch.eliminaCapitoli(id, daTogliere);
  for (const k of daTogliere) delete salvati[k];
  record.stato = 'pronto';
  await arch.salvaLibro(record);
  avanza({ testo: 'Fatto.', percentuale: 100 });
  log('importazione finita in ' + ((performance.now() - t0) / 1000).toFixed(1) + ' s' + (daTogliere.length ? ' (tolti ' + daTogliere.length + ' capitoli non più presenti)' : ''));
  return record;
}
