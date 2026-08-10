# AGENTS.md

## Project Overview

Dieses Repository ist das portable Runtime- und Kerntrainingsprojekt einer
Masterthesis. Es enthaelt drei MQTT-Inferenzdienste fuer Storage, VGR und HBW,
eine virtuelle Node-RED-/Mosquitto-Umgebung und den physischen MQTT-Grenzpfad.

Vor Aenderungen `docs/AI_DEVELOPMENT_HANDOVER.md` lesen. `README.md` ist der
menschliche Einstieg, `docs/OPERATION_AND_MIGRATION_GUIDE.md` die verbindliche
Bedienungsanleitung und `docs/PROJECT_KNOWLEDGE.md` die dauerhafte Wissensbasis.

## Working Rules

- Jede Session mit dem dokumentierten Startprotokoll beginnen.
- Bestehende Aenderungen anderer Personen nicht ueberschreiben.
- Prozesslogik, MQTT-Topics, Payloadformen, QoS, Feature-Reihenfolgen,
  Klassen und Semaphorverhalten nur nach expliziter Freigabe aendern.
- Wissenschaftliche Aenderungen an Daten, Splits, Training oder Modellen in
  `docs/PROJECT_KNOWLEDGE.md` begruenden.
- Python-Code klein, testbar und ohne versteckte Seiteneffekte halten.
- Node-RED-Function-Nodes bleiben schmale Adapter zu getesteten JS-Kernen.
- Keine `.env`, Credentials, Reports, Docker-Volumes oder lokale
  Modellkandidaten versionieren.

## Data And Models

- `data/plc/` enthaelt nur die aktiven Trainings- und Regressionstabellen.
- `model_registry/<domain>/latest/` ist der versionierte Deployment-Default.
- `versions/`, `candidates/`, Auswahlhistorie und Backups bleiben lokal.
- Training laeuft standardmaessig mit `publish_latest=false`; Promotion erst
  nach virtueller Regression ueber den Kandidatenmanager.
- Forschungsnotebooks, Rohdaten und historische Artefakte liegen nur im
  privaten Entwicklungsarchiv unter `development-complete-2026-08-10`, nicht
  im oeffentlichen Runtime-Repository.

## Validation

- Markdown: mindestens `git diff --check`.
- Python: relevante Unit-Tests und `py_compile`.
- MQTT/Node-RED: Python-Vertragstests, `npm test`, Flowexport und Compose.
- Training: Config-/Datensatzvertrag, Kandidatenmodus und unveraendertes
  `latest` pruefen.
- Runtimeaenderung: virtuellen Standardlauf und betroffene Guard-Profile.

## Completion

Zum Abschluss geaenderte Dateien, Wirkung, ausgefuehrte Checks, offene Risiken,
Branch, Commit und naechsten Schritt nach der zentralen Uebergabe nennen.
