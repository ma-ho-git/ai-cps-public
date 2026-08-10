# Project Knowledge

## Aktueller Zweck

Das Repository stellt eine portable hybride Testumgebung bereit. Storage-,
VGR- und HBW-Netze sind austauschbare MQTT-Dienste. Virtuell ersetzen
Mosquitto und Node-RED die Fabrik; physisch wird derselbe MQTT-Grenzvertrag
gegen eine externe Node-RED-/OPC-UA-/SPS-Black-Box verwendet.

## Dauerhafte Architekturentscheidungen

- Keine Python-Orchestratorcontainer im aktiven System.
- Node-RED bildet One-hot-Encoding, LSTM-Fenster und Semaphorlogik.
- VGR und HBW publizieren Commands nach erfolgreicher Inferenz direkt und
  unabhaengig; Responsekorrelation dient nur der Beobachtung.
- Der Semaphor synchronisiert Modulabschluesse ueber `sent_count` und
  `accepted_count` fuer VGR, HBW, MPO und SLD.
- Physische Topics, leere Command-Payloads, QoS 2 und `retain=false` bleiben
  eingefroren.
- Der physische Flow und die SPS sind in diesem Softwareprojekt Black Boxes.

## Modellvertraege

- Storage: neun binaere Lagerbelegungen, Klassen `0..9`, statisches MLP.
- VGR/HBW: Sequenz `(10,29)` mit 19 Prozessfeatures und
  `empty_storage_0..9`.
- Vollspeicher ist Modellinput, kein Orchestrator-Kurzschluss.
- LSTM-Bootstrap: neun interne Idle-Zeilen plus erster realer Zustand;
  Seed-Zeilen erzeugen keine Commands.
- Contracts und Online-Status werden retained publiziert.

Deployment-Defaults:

- Storage: `storage:2026-07-08_085429:6ef3fdb63813`
- VGR Guard: `vgr:2026-08-05_080003:654a7c781949`
- HBW Guard: `hbw:2026-08-05_071254:d8559bef03fc`

## Vollspeicherbefund

Die frueheren VGR-/HBW-Daten deckten „Lager voll und Lichtschranke
unterbrochen“ nicht ausreichend ab. Das VGR-Modell konnte nach wiederholtem
Zustand aktiv werden, obwohl Storage korrekt `0` meldete. Guard-Datensaetze
ergaenzten stationaere und prozessartige Gegenbeispiele mit Label `cmd=0`.

Abnahme der promovierten Modelle am 2026-08-10:

- Standard: 320 Zustaende, unveraenderte Vorhersagen und Commands;
- stationaer: 20/20 VGR/HBW Idle;
- prozessartig: 171/171 VGR/HBW Idle;
- keine Faults, Timeouts oder unausgeglichenen Modulcounter.

## Training

- `configs/train_*.json` sind die aktiven, sicheren Kandidatenconfigs.
- VGR nutzt den balancierten Guard-Datensatz, HBW den Guard-Datensatz.
- `publish_latest=false` ist fuer alle drei Domains Standard.
- Originale VGR-/HBW-Datensaetze und `regression_*_original.json` bleiben fuer
  die Rueckwaertskompatibilitaetspruefung erhalten.
- Training schreibt lokale Zeitstempelversionen. Promotion nach `latest`
  erfolgt nur mit Modellmanager und erfolgreichen virtuellen Regressionen.

## Virtuelle Betriebsparameter

- Profile: `standard`, `full-storage-attempt`,
  `full-storage-process-guard`.
- Basiszeit je Modul: Standard 100 ms, Variation fest -50 bis +50 Prozent.
- FlowFuse Dashboard ist lokal unter `/dashboard/betrieb` erreichbar.
- Versionierte Flows werden nicht still in persistente Volumes kopiert;
  Updates erfolgen explizit mit Backup und `flow-update`.

## Portabilitaet

- Freigegeben: WSL2/Ubuntu oder natives Linux auf `x86_64`; native Docker
  Engine und Docker Desktop im Linux-Container-Modus sind zulaessig.
- Betriebsstandard ab V1.1: flacher Clone des festen Release-Tags,
  `setup_portable_runtime.py` und digest-genaue GHCR-Images.
- GHCR publiziert drei NN-Images und das Node-RED-Runtimeimage mit SHA-Tags;
  auf `main` zusaetzlich `latest-validated`.
- Das Release-Manifest bindet Source-Commit, Images, Modelle, Traces und Flows.
- `COMPOSE_PROJECT_NAME` trennt Standortinstallationen auf demselben Host.
- Ein geprueftes Standortbundle uebertraegt die vollstaendige `.env`,
  persistente Volumes, Reports und ausgewaehlte Kandidaten. Es ist ein
  Klartextartefakt der isolierten Testumgebung und enthaelt keine Git-/SSH-/
  GitHub-/Docker-Anmeldedaten.
- Rolling Windows, offene Zyklen und Docker-Images werden nicht migriert.

## Archiv

Der ungekuerzte Forschungsstand ist ausschliesslich im privaten
Entwicklungsrepository unter Branch
`archive/full-development-state-2026-08-10` und Tag
`development-complete-2026-08-10` eingefroren. Dort liegen Notebooks,
Roh-/Zwischendaten, Lernkurs, Builder, alte Orchestratoren und Forschungsplots.

## Oeffentliche Runtime

- Massgebliche oeffentliche Quelle ab V1.1 ist
  `ma-ho-git/ai-cps-runtime` unter `AGPL-3.0-only`.
- Die oeffentliche Historie beginnt mit einem bereinigten Initial-Commit;
  private Entwicklungsbranches und persoenliche Commit-Adressen werden nicht
  uebertragen.
- Herkunft aus Marcus Grums AGPL-lizenziertem AI-CPS wird in
  `THIRD_PARTY_NOTICES.md` dokumentiert.
- Ein Release-Tag ist nur zulaessig, wenn
  `check_public_release_readiness.py --require-approved` erfolgreich ist.
- Runtime, Training, Modelle, Daten und Traces duerfen nur nach dokumentierter
  Rechtefreigabe oeffentlich publiziert werden.
