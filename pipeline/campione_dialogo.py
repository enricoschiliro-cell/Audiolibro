"""Campione PROVVISORIO con dialoghi (Ivanhoe, Capitolo primo: Gurth e Wamba nel bosco) per scegliere il narratore.
Le frasi sono scritte a mano qui sotto, con i trattini dei dialoghi gia' tolti (in Ivanhoe le battute iniziano con
'-' lungo e gli incisi sono chiusi da '-' corto). Il riconoscimento automatico di chi parla verra' dopo.
Crea output/ivanhoe/frasi/01-prova-dialogo.json  (testo: Liber Liber, traduzione di Sergio Ortolani, 1928)."""
import json
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent

blocchi = [
    ["Essi parlavano in lingua anglosassone che era, come già dicemmo, quella delle classi inferiori eccettuati "
     "i soldati normanni e le genti al servizio diretto della nobiltà feudale."],
    ["La maledizione di San Withold cade su questa mandra di bestiacce!",
     "Disse Gurth dopo aver dato di fiato più volte al corno per raccogliere i maiali sparsi per il bosco."],
    ["La maledizione di Dio cada su loro e su me! Se il lupo a due gambe non ne afferra qualcuno questa sera "
     "io non sono più Gurth. Quà Fangs, quà!",
     "Gridò ad un grosso cane dal pelo ruvido, mezzo mastino e mezzo levriere, che correva in ogni direzione "
     "come per aiutare il padrone a raccogliere la mandra."],
    ["Il diavolo gli faccia cadere i denti!",
     "Continuò Gurth.",
     "E che l'artefice del male confonda il guardiacaccia che strappa le unghie dalle zampe dei nostri cani "
     "rendendoli incapaci così a compiere il loro dovere. Wamba, alzati e, se sei un uomo, aiutami."],
    ["Davvero!",
     "Rispose Wamba, senza muoversi.",
     "Ho consultato in proposito le mie gambe ed esse pensano che profanare i miei meravigliosi abiti colle "
     "pilacchere di questi pantani sarebbe un atto indegno della mia sovranità e del mio guardaroba reale."],
    ["I miei porci cambiati in Normanni!",
     "Disse Gurth.",
     "Spiegami questo enigma. Io non ho né il cervello sì fine né il cuore sì lieto per indovinarlo."],
]

dati = {
    "capitolo": 1, "titolo": "Capitolo primo", "annuncio": "Capitolo uno.",
    "blocchi": [{"tipo": "paragrafo", "frasi": b} for b in blocchi],
}
uscita = RADICE / "output" / "ivanhoe" / "frasi"
uscita.mkdir(parents=True, exist_ok=True)
(uscita / "01-prova-dialogo.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
print(sum(len(f.split()) for b in blocchi for f in b), "parole in", len(blocchi), "blocchi")
