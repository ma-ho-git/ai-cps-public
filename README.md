# AI-CPS Public

Portables `linux/amd64`-Projekt fuer eine hybride Steuerung der
Fischertechnik-Fabrik. Drei austauschbare neuronale Netze kommunizieren ueber
MQTT. Node-RED orchestriert die Netze, bildet LSTM-Fenster und synchronisiert
in der virtuellen Simulation vier Maschinenmodule.

Enthalten sind:

- virtuelle Simulation mit Mosquitto, Node-RED, FlowFuse Dashboard 2.0 und
  Storage-, VGR- und HBW-Inferenz;
- physischer Betrieb gegen die bestehende MQTT-/OPC-UA-/SPS-Black-Box;
- versionierte Deploymentmodelle und rueckrollbarer Modellwechsel;
- reproduzierbares Kandidatentraining fuer alle drei Netze.

Der vollstaendige Forschungs- und Notebookstand bleibt im privaten
Entwicklungsarchiv und ist nicht Bestandteil dieses portablen Runtime-Repos.

## 1. Release-Schnellstart

Unterstuetzt werden WSL2/Ubuntu und natives Linux auf `x86_64` mit nativer
Docker Engine oder Docker Desktop im Linux-Container-Modus, Compose und
Python 3.12. Betriebsrechner verwenden den freigegebenen Release:

```bash
git clone --depth 1 --branch runtime-v1.3.0 \
  https://github.com/ma-ho-git/ai-cps-public.git AI-CPS
cd AI-CPS
python3 tools/setup_portable_runtime.py init \
  --mode virtual --release runtime-v1.3.0 \
  --compose-project ai-cps-nn-runtime \
  --report-root "$PWD/reports"
./tools/run_nodered_orchestration.sh virtual-hmi --images
```

Das Setup erzeugt `.env`, Secret, `.venv`, Reportpfad und einen lokalen
Release-Lock, laedt digest-genaue Images und fuehrt den Preflight aus.
Physischer Schnellstart:

```bash
python3 tools/setup_portable_runtime.py init --mode physical \
  --release runtime-v1.3.0 --mqtt-host 192.168.0.5
./tools/run_nodered_orchestration.sh physical-up --images
```

Details: [Betriebs- und Migrationsanleitung](docs/OPERATION_AND_MIGRATION_GUIDE.md)
und [Umgebungseinrichtung](docs/ENVIRONMENT_SETUP.md). Der lokale Source-Build
bleibt als Entwicklungsweg erhalten und wird ohne `--images` gestartet.

Die bestehenden GHCR-Paketnamen beginnen aus Kompatibilitaetsgruenden
weiterhin mit `ai-cps-runtime-`. Repository-Name, Quelllinks und OCI-Metadaten
verwenden dagegen die kanonische Bezeichnung `AI-CPS Public`.

## 2. Virtuelle Simulation

Dashboard starten, ohne automatisch einen Lauf auszuloesen:

```bash
./tools/run_nodered_orchestration.sh virtual-hmi
```

Danach: <http://localhost:1880/dashboard/betrieb>

Vollstaendigen Standardlauf direkt starten:

```bash
./tools/run_nodered_orchestration.sh virtual-run
```

Verfuegbare Testszenarien:

```bash
./tools/run_nodered_orchestration.sh virtual-run --trace-profile standard
./tools/run_nodered_orchestration.sh virtual-run --trace-profile full-storage-attempt
./tools/run_nodered_orchestration.sh virtual-run --trace-profile full-storage-process-guard
```

| Interne ID | Bedeutung |
|---|---|
| `standard` | Normalbetrieb mit Einlagerungen und Idle-Phasen (320 Zustaende) |
| `full-storage-attempt` | Vollspeicher mit 20 wiederholten Einlagerungsversuchen (157 Zustaende) |
| `full-storage-process-guard` | Vollspeicher mit 9 vollstaendigen Prozesssequenzen (308 Zustaende) |

Im Dashboard kann pro Lauf zwischen dem aktuellen Deploymentstand und dem
historischen VGR-/HBW-Modellpaar gewaehlt werden. Das historische Profil dient
ausschliesslich dazu, den frueheren Vollspeicherfehler virtuell zu
reproduzieren:

```bash
./tools/run_nodered_orchestration.sh virtual-run \
  --model-profile historical-full-storage-error \
  --trace-profile full-storage-attempt
```

Ohne `--model-profile` wird unveraendert `deployment-current` verwendet. Der
physische Betrieb bietet das historische Profil nicht an.

Die virtuelle Fabrik bildet den physischen Ablauf in fuenf getrennten
Node-RED-Tabs nach: Initialisierung, 50-ms-Zustandserfassung, vier unabhaengige
Module, Jobcounter-Semaphor und NN-Pipeline. Das interne Topic
`ft/sim/factory/raw_state` ist ausschliesslich virtuell; der freigegebene
Anlagenzustand bleibt unveraendert auf `log/logging/state`.

Status und Stopp:

```bash
./tools/run_nodered_orchestration.sh virtual-status
./tools/run_nodered_orchestration.sh virtual-down
```

Persistente Docker-Volumes bleiben beim normalen Stopp erhalten. Kein
`down -v` im Regelbetrieb verwenden.

## 3. Physischer Betrieb

Das physische Node-RED-/OPC-UA-/SPS-System ist eine Black Box. Dieses
Repository nutzt nur den eingefrorenen MQTT-Grenzvertrag.

```bash
./tools/run_nodered_orchestration.sh physical-preflight
./tools/run_nodered_orchestration.sh physical-up
```

`physical-up` startet nur die drei NN-Container und sendet standardmaessig
keine Maschinenbefehle. Erst nach kontrollierter Diagnose freigeben:

```bash
./tools/run_nodered_orchestration.sh physical-up --command-output-enabled
```

```bash
./tools/run_nodered_orchestration.sh physical-status
./tools/run_nodered_orchestration.sh physical-down
```

## 4. Training Und Modellwechsel

Die drei Trainingsdienste erzeugen ausschliesslich lokale Kandidaten unter
`model_registry/<domain>/versions/`; `latest` wird nicht automatisch ersetzt.

```bash
docker compose -f docker-compose.train.yml build train_storage train_vgr train_hbw
docker compose -f docker-compose.train.yml run --rm train_vgr
```

Kandidaten pruefen, auswaehlen und rueckrollen:

```bash
python3 tools/check_model_compatibility.py --domain vgr --candidate-dir /pfad/zum/modell --mode virtual
python3 tools/manage_model_candidates.py add --domain vgr --name kandidat --source /pfad/zum/modell --target virtual
python3 tools/manage_model_candidates.py select --domain vgr --name kandidat --target virtual
python3 tools/manage_model_candidates.py rollback --domain vgr
```

Details: [Training und Modellfreigabe](docs/TRAINING_AND_MODEL_RELEASE.md).

## Beobachtung

Kompakte Zuordnung von NN-Eingang und Vorhersage:

```bash
.venv/bin/python tools/observe_nn_inference.py --host localhost --port 1883
```

Breiter MQTT-Monitor:

```bash
./tools/run_nodered_orchestration.sh monitor
```

Reports liegen unter `reports/orchestration_simulation/<run_id>/` und werden
nicht versioniert.

## Standort Uebertragen

Bei gestopptem Stack kann der vollstaendige lokale Teststand uebertragen
werden:

```bash
python3 tools/manage_runtime_migration.py export --output ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py inspect ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py import ai-cps-site-backup.tar.gz \
  --target-project ai-cps-restored \
  --target-report-root "$PWD/reports-restored" \
  --force
```

Das Bundle enthaelt die vollstaendige `.env` einschliesslich des lokalen
Node-RED-Secrets im Klartext. Es ist fuer die isolierte Testumgebung gedacht;
bei spaeteren echten Zugangsdaten muss es vor Weitergabe verschluesselt werden.

## Dokumentation

- [Betrieb und Migration](docs/OPERATION_AND_MIGRATION_GUIDE.md)
- [Portable Bereitstellung](docs/PORTABLE_DEPLOYMENT.md)
- [Node-RED-/MQTT-Architektur](docs/NODERED_MQTT_ORCHESTRATION.md)
- [Training und Modellfreigabe](docs/TRAINING_AND_MODEL_RELEASE.md)
- [Troubleshooting](docs/SIMULATION_TROUBLESHOOTING_RUNBOOK.md)
- [Oeffentliche Release-Prozedur](docs/PUBLIC_RELEASE_PROCEDURE.md)
- [Rechtepruefung](docs/PUBLICATION_RIGHTS_REVIEW.md)
- [KI-Entwicklungsuebergabe](docs/AI_DEVELOPMENT_HANDOVER.md)

## Lizenz Und Herkunft

Dieses Projekt steht unter [AGPL-3.0-only](LICENSE). Es entwickelt Konzepte
und fruehe Deploymentstrukturen aus
[Marcus Grums AI-CPS](https://github.com/MarcusGrum/AI-CPS) fuer die hybride
fischertechnik-Fabrik weiter. Details und Drittanbieter-Lizenzen stehen in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Die Software ist eine
Forschungs- und Testumgebung und keine zertifizierte Sicherheitssteuerung.
