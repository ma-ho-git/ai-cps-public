# AI-CPS Public

Portable virtuelle Testumgebung fuer MQTT-basierte neuronale Netze. Mosquitto
vermittelt die Nachrichten, Node-RED bildet Fabrikablauf und Synchronisation
ab, und drei Container stellen Storage-, VGR- und HBW-Inferenz bereit.

Das FlowFuse Dashboard ermoeglicht, Testszenario, Modellprofil, Zufalls-Seed
und simulierte Modulzeiten auszuwaehlen. Status, Vorhersagen, Modulzaehler und
Fehler lassen sich waehrend eines Laufs beobachten.

## Schnellstart

Unterstuetzt werden WSL2/Ubuntu und natives Linux auf `x86_64` mit Docker
Engine oder Docker Desktop im Linux-Container-Modus, Docker Compose und
Python 3.12.

```bash
git clone --depth 1 --branch runtime-v1.3.0 \
  https://github.com/ma-ho-git/ai-cps-public.git AI-CPS
cd AI-CPS
python3 tools/setup_portable_runtime.py init \
  --mode virtual \
  --release runtime-v1.3.0 \
  --compose-project ai-cps-nn-runtime \
  --report-root "$PWD/reports"
./tools/run_nodered_orchestration.sh virtual-hmi --images
```

Dashboard: <http://localhost:1880/dashboard/betrieb>

Das Setup erzeugt `.env`, ein lokales Node-RED-Secret, `.venv`, Reportpfad und
Deployment-Lock. Es laedt die digest-genauen Release-Images und fuehrt den
virtuellen Preflight aus. Die GHCR-Paketnamen beginnen aus
Kompatibilitaetsgruenden weiterhin mit `ai-cps-runtime-`.

## Testszenarien

| Interne ID | Anzeige und Zweck |
|---|---|
| `standard` | Normalbetrieb mit Einlagerungen und Idle-Phasen, 320 Zustaende |
| `full-storage-attempt` | Volles Lager mit 20 wiederholten Einlagerungsversuchen, 157 Zustaende |
| `full-storage-process-guard` | Volles Lager mit 9 Prozesssequenzen und 171 kritischen Zustaenden, insgesamt 308 Zustaende |

Zwei Modellprofile stehen zur Auswahl:

- `deployment-current`: aktueller Modellstand mit Vollspeicherschutz;
- `historical-full-storage-error`: historischer Stand zur reproduzierbaren
  Demonstration des Vollspeicherfehlers.

Erwartungen, Ablauf und Auswertung stehen in der
[Szenarienbeschreibung](docs/VIRTUAL_SCENARIOS.md).

## Direktstart

Ein Szenario kann ohne Dashboard gestartet werden:

```bash
./tools/run_nodered_orchestration.sh virtual-run --images \
  --trace-profile standard \
  --model-profile deployment-current
```

Historischen Vollspeicherfehler reproduzieren:

```bash
./tools/run_nodered_orchestration.sh virtual-run --images \
  --trace-profile full-storage-attempt \
  --model-profile historical-full-storage-error
```

Status und Stopp:

```bash
./tools/run_nodered_orchestration.sh virtual-status
./tools/run_nodered_orchestration.sh virtual-down
```

Der normale Stopp entfernt Container und Docker-Netzwerk, behaelt die
persistenten Node-RED- und Mosquitto-Volumes aber bei. `down -v` ist fuer den
Regelbetrieb nicht vorgesehen.

## Beobachtung Und Reports

Kompakte Zuordnung von NN-Eingang und Vorhersage:

```bash
.venv/bin/python tools/observe_nn_inference.py \
  --host localhost --port 1883
```

Breiter MQTT-Monitor:

```bash
./tools/run_nodered_orchestration.sh monitor
```

Jeder Lauf erzeugt unter `reports/orchestration_simulation/<run_id>/`:

- `events.jsonl`: Ereignisse, Modellprofile und Modell-IDs;
- `summary.csv`: ein Eintrag je vollstaendig korreliertem Zyklus;
- `run_summary.json`: Laufstatus, Konfiguration, Fehler und Modulzaehler.

## Standort Uebertragen

Bei gestopptem Stack kann ein lokaler Teststand uebertragen werden:

```bash
python3 tools/manage_runtime_migration.py export \
  --output ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py inspect \
  ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py import \
  ai-cps-site-backup.tar.gz \
  --target-project ai-cps-restored \
  --target-report-root "$PWD/reports-restored" \
  --force
```

Das Bundle enthaelt `.env`, persistente Volumes und Reports. Es hat Dateimodus
`0600` und enthaelt das lokale Node-RED-Secret im Klartext. In nicht
abgeschotteten Umgebungen muss es vor der Weitergabe verschluesselt werden.

## Dokumentation

- [Testszenarien](docs/VIRTUAL_SCENARIOS.md)
- [Betrieb und Migration](docs/OPERATION_AND_MIGRATION_GUIDE.md)
- [Umgebung einrichten](docs/ENVIRONMENT_SETUP.md)
- [Node-RED-/MQTT-Ablauf](docs/NODERED_MQTT_ORCHESTRATION.md)
- [Portable Bereitstellung](docs/PORTABLE_DEPLOYMENT.md)
- [Troubleshooting](docs/SIMULATION_TROUBLESHOOTING_RUNBOOK.md)

## Lizenz

Dieses Projekt steht unter [AGPL-3.0-only](LICENSE). Rechtlich erforderliche
Hinweise zu uebernommenen Bestandteilen und Drittanbieter-Lizenzen stehen in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
