# Betrieb Und Migration

Diese Anleitung beschreibt Installation, Bedienung, Beobachtung und
Uebertragung der virtuellen Simulation.

## 1. Neuen Computer Vorbereiten

Voraussetzungen:

- `linux/amd64`
- Ubuntu 24.04 unter WSL2 oder natives Linux
- Docker Engine oder Docker Desktop im Linux-Container-Modus
- Docker Compose
- Git, Python 3.12, `venv`, `curl` und Mosquitto-Clients

Release installieren:

```bash
git clone --depth 1 --branch runtime-v1.3.0 \
  https://github.com/ma-ho-git/ai-cps-public.git AI-CPS
cd AI-CPS
python3 tools/setup_portable_runtime.py init \
  --mode virtual \
  --release runtime-v1.3.0 \
  --compose-project ai-cps-nn-runtime \
  --report-root "$PWD/reports"
```

Der Assistent erzeugt `.env` mit Modus `0600`, ein Node-RED-Secret, `.venv`,
Reportverzeichnis und Deployment-Lock. Danach prueft er Docker, Images,
Modelle, Traces, Ports und Schreibrechte.

## 2. Dashboard Starten

```bash
./tools/run_nodered_orchestration.sh virtual-hmi --images
```

Dashboard: <http://localhost:1880/dashboard/betrieb>

Der Stack besteht aus Mosquitto, Node-RED sowie Storage-, VGR- und
HBW-Inferenzdienst. Ein Lauf startet erst nach der Bedienaktion im Dashboard.

Vor dem Start auswaehlen:

- Testszenario
- aktuelles oder historisches Modellprofil
- Zufalls-Seed
- Basiszeit fuer VGR, HBW, MPO und SLD

Die drei Szenarien und ihre erwarteten Ergebnisse beschreibt
[VIRTUAL_SCENARIOS.md](VIRTUAL_SCENARIOS.md).

## 3. Lauf Direkt Starten

```bash
./tools/run_nodered_orchestration.sh virtual-run --images \
  --trace-profile standard \
  --model-profile deployment-current
```

Wichtige Optionen:

| Option | Wirkung |
|---|---|
| `--trace-profile <id>` | eines der drei Testszenarien |
| `--model-profile <id>` | aktueller oder historischer Modellstand |
| `--diagnosis` | Ablauf ohne Maschinencommands |
| `--images` | digest-genaue GHCR-Releaseimages |
| `--no-build` | vorhandene lokale Images verwenden |
| `--env-file <pfad>` | abweichende Standortkonfiguration |
| `--skip-preflight` | Preflight nur fuer gezielte Fehlersuche auslassen |

Umgebungswerte wie `FACTORY_SEED`, `FACTORY_*_BASE_RUNTIME_MS`, `MQTT_PORT`,
`NODE_RED_PORT`, `READY_TIMEOUT_S` und `REPORT_ROOT_HOST` koennen in `.env`
gesetzt werden. Bereits gesetzte Shellvariablen haben Vorrang.

## 4. Betrieb Beobachten

Containerstatus:

```bash
./tools/run_nodered_orchestration.sh virtual-status
```

Kompakte NN-Eingaenge und Vorhersagen:

```bash
.venv/bin/python tools/observe_nn_inference.py \
  --host localhost --port 1883
```

Alle wichtigen MQTT-Nachrichten:

```bash
./tools/run_nodered_orchestration.sh monitor
```

Containerlogs:

```bash
docker compose \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.yml \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.virtual.yml \
  logs -f node_red storage_infer vgr_infer hbw_infer mosquitto
```

Der Beobachter und der Monitor publizieren keine fachlichen Nachrichten.

## 5. Reports Auswerten

Pro Lauf entsteht ein eigener Ordner:

```text
reports/orchestration_simulation/<run_id>/events.jsonl
reports/orchestration_simulation/<run_id>/summary.csv
reports/orchestration_simulation/<run_id>/run_summary.json
```

- `events.jsonl`: detaillierte Ereignisse und Modellinformationen
- `summary.csv`: korrelierte Zyklusergebnisse
- `run_summary.json`: Gesamtergebnis, Konfiguration und Modulzaehler

Ein Lauf ist erst abgeschlossen, wenn `completed=true` und die Zaehler aller
vier Module ausgeglichen sind.

## 6. Stoppen Und Aktualisieren

```bash
./tools/run_nodered_orchestration.sh virtual-down
```

Der Befehl entfernt Container und Netzwerk, aber keine persistenten Volumes.
Vor einem Flowupdate:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
```

`down -v` nur verwenden, wenn alle lokalen Laufzeitdaten bewusst verworfen
werden sollen.

## 7. Teststand Uebertragen

Quelle und Ziel muessen gestoppt sein.

Export und Kontrolle:

```bash
python3 tools/manage_runtime_migration.py export \
  --output ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py inspect \
  ai-cps-site-backup.tar.gz
```

Import in eine getrennte Installation:

```bash
python3 tools/manage_runtime_migration.py import \
  ai-cps-site-backup.tar.gz \
  --target-project ai-cps-restored \
  --target-report-root "$PWD/reports-restored" \
  --force
```

Der Import prueft Hashes, legt vor dem Ersetzen ein Ruecksicherungsbundle an,
stellt `.env`, Volumes und Reports wieder her und startet keine Container.
Mit eigenem Projektnamen und Reportpfad bleiben mehrere Installationen
voneinander getrennt.

Bundle und Ruecksicherungsbundle erhalten Dateimodus `0600`. Sie enthalten
das lokale Node-RED-Secret im Klartext und muessen ausserhalb einer
abgeschotteten Testumgebung verschluesselt werden.

## 8. Fehler Beheben

Bei `fault_latched` zuerst Fehlercode und Zyklus im Dashboard oder Report
pruefen. Nach Beseitigung der Ursache:

```bash
./tools/run_nodered_orchestration.sh reset
```

Weitere Diagnosehilfen stehen im
[Troubleshooting-Runbook](SIMULATION_TROUBLESHOOTING_RUNBOOK.md).
