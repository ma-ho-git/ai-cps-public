# Project Knowledge

## Systemzweck

AI-CPS Public ist eine portable virtuelle MQTT-/Node-RED-Testumgebung. Drei
Inferenzdienste fuer Storage, VGR und HBW werden in einem simulierten
Fabrikablauf mit vier Modulen ausgefuehrt und beobachtet.

## Laufzeitstruktur

- `runtime-v1.3.0` ist der stabile Referenzstand.
- Mosquitto vermittelt alle virtuellen MQTT-Nachrichten.
- Node-RED bildet Initialisierung, 50-ms-Zustandserfassung, vier Module,
  Jobcounter-Semaphor, NN-Pipeline, Reporting und HMI ab.
- Storage, VGR und HBW laufen als getrennte Inferenzcontainer.
- VGR/HBW-Responses werden fuer Reports korreliert, aber nicht als
  Command-Barriere verwendet.
- Der Semaphor gibt den naechsten Zustand erst frei, wenn fuer VGR, HBW, MPO
  und SLD `sent_count == accepted_count` gilt.

## Node-RED-Lesbarkeit

- Core-Nodes bilden Routing, Validierung, Reporting, Dashboard und Delays ab.
- Die wiederholten Modul-, Windowing- und Responseablaeufe sind Subflows.
- Exakt vier Function-Nodes bleiben fuer Modullaufzeit, atomaren Semaphor,
  dynamischen Modellvertrag und LSTM-Fenster.
- `tools/check_code_readability.py` begrenzt Function-Laenge und JSONata.
- Der Flow wird nur mit `tools/build_modular_nodered_flow.py` erzeugt.

## Modellvertraege

- Storage: neun binaere Lagerbelegungen, Klassen `0..9`.
- VGR/HBW: Fenster `(10,29)` mit `empty_storage_0..9`.
- Bei neuer Quelle: neun interne Idle-Eintraege plus erster realer Zustand.
- Seed-Eintraege erzeugen keine Commands.
- Contracts und Online-Status werden retained publiziert.

Versionierte Standardmodelle:

- Storage: `storage:2026-07-08_085429:6ef3fdb63813`
- VGR: `vgr:2026-08-05_080003:654a7c781949`
- HBW: `hbw:2026-08-05_071254:d8559bef03fc`

## Szenarien Und Profile

- `standard`: 320 Zustaende mit Einlagerungen und Idle-Phasen.
- `full-storage-attempt`: 157 Zustaende, darunter 20 wiederholte kritische
  Einlagerungsversuche.
- `full-storage-process-guard`: 308 Zustaende, darunter 171 kritische
  Zustaende in neun Prozesssequenzen.
- `deployment-current`: aktueller Modellstand mit Vollspeicherschutz.
- `historical-full-storage-error`: festes historisches VGR-/HBW-Paar zur
  Fehlerreproduktion.

Aktuelle Modelle liefern in den Vollspeicherszenarien 20/20 beziehungsweise
171/171 Idle-Ergebnisse fuer VGR und HBW. Das historische Profil reproduziert
den dokumentierten aktiven Command bei vollem Lager.

## Betriebsparameter

- Modulbasiszeit: standardmaessig 100 ms.
- Variation: reproduzierbar minus 50 bis plus 50 Prozent.
- Seed, vier Basiszeiten, Testszenario und Modellprofil sind im HMI waehlbar.
- Ein Profil gilt unveraenderlich fuer den gesamten Lauf.
- Dashboard: `/dashboard/betrieb`.

## Reports

- `events.jsonl`: Ereignisse und Modellinformationen.
- `summary.csv`: vollstaendig korrelierte Zyklen.
- `run_summary.json`: Gesamtlaufstatus, Konfiguration und Modulzaehler.
- Nur der korrelierte finale Fabrikstatus setzt `completed=true`.
- Reset beendet einen offenen Report und erzeugt fuer den naechsten Lauf einen
  neuen Reportordner.

## Portabilitaet

- Freigegeben: WSL2/Ubuntu oder natives Linux auf `x86_64`.
- Releasebetrieb: flacher Tag-Clone, Setup-Assistent und digest-genaue Images.
- `COMPOSE_PROJECT_NAME` trennt Installationen auf demselben Host.
- Standortbundles uebertragen `.env`, persistente Volumes und Reports.
- Bundles sind `0600`, enthalten aber das lokale Secret im Klartext.
- Rolling Windows, offene Zyklen und Docker-Images werden nicht migriert.
- `virtual-down` behaelt persistente Volumes bei.

## Geschuetzte Vertraege

- MQTT-Topics, Payloadformen, QoS und Retain-Flags.
- Feature-Reihenfolgen, Fensterform und Modellklassen.
- Direkte VGR-/HBW-Commands und MPO-/SLD-Idle-Commands.
- Vier-Modul-Semaphor und Reportformate.
- Interne Szenario- und Modellprofil-IDs.
