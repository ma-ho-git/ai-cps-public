# AGENTS.md

## Project Overview

Dieses Repository stellt eine portable virtuelle MQTT-/Node-RED-Simulation
bereit. Mosquitto, Node-RED und drei Inferenzdienste bilden Testszenarien fuer
Storage, VGR und HBW ab. Das FlowFuse Dashboard steuert und beobachtet die
Laeufe.

Vor Aenderungen `docs/AI_DEVELOPMENT_HANDOVER.md` lesen. `README.md` ist der
menschliche Einstieg, `docs/OPERATION_AND_MIGRATION_GUIDE.md` die verbindliche
Bedienungsanleitung und `docs/PROJECT_KNOWLEDGE.md` die technische Wissensbasis.

## Working Rules

- Jede Session mit dem dokumentierten Startprotokoll beginnen.
- Bestehende Aenderungen anderer Personen nicht ueberschreiben.
- Prozesslogik, MQTT-Topics, Payloadformen, QoS, Feature-Reihenfolgen,
  Klassen, Modellprofile und Semaphorverhalten nur nach expliziter Freigabe
  aendern.
- Python-Code klein, testbar und ohne versteckte Seiteneffekte halten:
  Produktion maximal 60 Zeilen, Callback und `main()` maximal 40 Zeilen.
- Node-RED-Flow nur ueber `tools/build_modular_nodered_flow.py` erzeugen.
  Exakt vier dokumentierte Function-Ausnahmen, jeweils maximal 40 Zeilen.
- JSONata maximal 200 Zeichen; Fachentscheidungen mit sichtbaren Core-Nodes.
- Keine `.env`, Credentials, Reports, Docker-Volumes oder lokale
  Modellkandidaten versionieren.

## Runtime Artifacts

- `model_registry/<domain>/latest/` ist der versionierte Standard.
- Das historische virtuelle Modellprofil ist ein fester Demonstrationsstand.
- `versions/`, `candidates/`, Auswahlhistorie und Backups bleiben lokal.
- Die drei Traceprofile sind versionierte Eingaben der virtuellen Simulation.

## Validation

- Dokumentation: lokale Links, Dokumentationsvertraege, `git diff --check`.
- Python: relevante Unit-Tests und `py_compile`.
- Lesbarkeit: `python tools/check_code_readability.py`.
- MQTT/Node-RED: Vertragstests, `npm test`, Flowexport und Compose.
- Runtimeaenderung: Standardlauf und betroffene Vollspeicherszenarien.

## Completion

Zum Abschluss geaenderte Dateien, Wirkung, ausgefuehrte Checks, offene Risiken,
Branch, Commit und naechsten Schritt nach der zentralen Uebergabe nennen.
