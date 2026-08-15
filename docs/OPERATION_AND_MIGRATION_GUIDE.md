# Betriebs- Und Migrationsanleitung

Diese Anleitung ist die verbindliche Schrittfolge fuer Installation,
virtuelle Simulation, physischen Test, Beobachtung und Modellwechsel.

## 1. Betriebsart Waehlen

| Modus | Container | Command-Ausgabe |
|---|---|---|
| Virtuelles HMI | Mosquitto, Node-RED, drei NN-Dienste | beim HMI-Start konfiguriert |
| Virtueller Lauf | Mosquitto, Node-RED, drei NN-Dienste | aktiv, ausser `--diagnosis` |
| Physische Diagnose | drei NN-Dienste | aus |
| Physischer Vollbetrieb | drei NN-Dienste | explizit aktiv |

Das physische Node-RED-/OPC-UA-/SPS-System ist eine Black Box. Dieses Projekt
startet oder veraendert es nicht.

## 2. Auf Einen Neuen Computer Migrieren

1. Docker Engine oder Docker Desktop mit Linux-Containern, Compose, Git,
   Python 3.12, `venv`, `curl` und
   Mosquitto-Clients installieren.
2. Repository flach klonen:

   ```bash
   git clone --depth 1 --branch runtime-v1.3.0-rc.3 \
     https://github.com/ma-ho-git/ai-cps-runtime.git AI-CPS
   cd AI-CPS
   ```

3. Runtime automatisch vorbereiten:

   ```bash
   python3 tools/setup_portable_runtime.py init \
     --mode virtual --release runtime-v1.3.0-rc.3 \
     --compose-project ai-cps-nn-runtime \
     --report-root "$PWD/reports"
   ```

   Fuer physisch stattdessen:

   ```bash
   python3 tools/setup_portable_runtime.py init --mode physical \
     --release runtime-v1.3.0-rc.3 --mqtt-host 192.168.0.5
   ```

Das Setup erzeugt Secret, `.venv`, Reportpfad und `.env` mit Modus `0600`,
laedt die freigegebenen Images und fuehrt den Preflight aus. Der physische
MQTT-Test fuehrt nur CONNECT/CONNACK aus und publiziert nichts.

### Bestehenden Standortstand Uebernehmen

Auf dem alten Rechner den Stack stoppen und exportieren; auf dem Zielrechner
den Release zuerst wie oben installieren, dann inspizieren und importieren:

```bash
python3 tools/manage_runtime_migration.py export --output ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py inspect ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py import ai-cps-site-backup.tar.gz \
  --target-project ai-cps-restored \
  --target-report-root "$PWD/reports-restored" \
  --force
```

Der Import stellt `.env`, Volumes, Reports und ausgewaehlte Kandidaten wieder
her, erzeugt zuvor ein Ruecksicherungsbundle und startet nicht automatisch.
Das Bundle ist ein Klartextartefakt der isolierten Testumgebung. Bei spaeteren
echten Credentials vor Weitergabe verschluesseln.

Export und automatisches Ruecksicherungsbundle werden mit Dateimodus `0600`
angelegt. `runtime-v1.3.0-rc.3` importiert Bundles aus V1.1.0, dem internen
V1.1.1-Stand, V1.2.0 sowie V1.3.0-RC.1 bis RC.3.
Mit `--force` werden vorhandene Zielvolumes nach der Ruecksicherung kontrolliert
mit passenden Compose-Labels neu angelegt, damit spaetere Starts keine
Fremdvolume-Warnung erzeugen.

Fuer einen zweiten Teststand immer einen eigenen `--target-project` und
`--target-report-root` verwenden. Dadurch werden weder Docker-Volumes noch
Reports mit der bestehenden Installation geteilt.

## 3. Virtuelle Simulation

### Mit Dashboard

```bash
./tools/run_nodered_orchestration.sh virtual-hmi --images
```

Browser: <http://localhost:1880/dashboard/betrieb>

Im HMI koennen Testszenario, Modellprofil, Seed und Basiszeit fuer VGR, HBW,
MPO und SLD gewaehlt werden. Jede Basiszeit wird reproduzierbar um -50 bis
+50 Prozent variiert. Standard sind 100 ms. Das historische Modellprofil ist
deutlich als virtuelle Reproduktion des bekannten Vollspeicherfehlers
gekennzeichnet.

### Direktstart

```bash
./tools/run_nodered_orchestration.sh virtual-run --images
```

Optionen:

| Option | Wirkung |
|---|---|
| `--trace-profile standard` | Normalbetrieb: Einlagerungen und Idle-Phasen (320 Zustaende) |
| `--trace-profile full-storage-attempt` | Vollspeicher: 20 wiederholte Einlagerungsversuche (157 Zustaende) |
| `--trace-profile full-storage-process-guard` | Vollspeicher: 9 vollstaendige Prozesssequenzen (308 Zustaende) |
| `--model-profile deployment-current` | aktuell ausgewaehlter Deploymentstand, Standard |
| `--model-profile historical-full-storage-error` | historische VGR-/HBW-Modelle zur virtuellen Fehlerreproduktion |
| `--diagnosis` | keine Maschinencommands |
| `--no-build` | vorhandene Images verwenden |
| `--images` | freigegebene GHCR-Runtimeimages verwenden |
| `--env-file PATH` | andere Standortkonfiguration |
| `--skip-preflight` | nur fuer gezielte Diagnose |

Startparameter koennen auch in `.env` stehen: `FACTORY_SEED`, vier
`FACTORY_*_BASE_RUNTIME_MS`, `TRACE_PROFILE`, `MODEL_PROFILE`, `MQTT_PORT`,
`NODE_RED_PORT`, `READY_TIMEOUT_S` und `REPORT_ROOT_HOST`.

Das Modellprofil wird vor dem ersten Zustand festgelegt und gilt fuer den
vollstaendigen Lauf. Ein Wechsel waehrend eines offenen Laufs wird nicht
uebernommen. Nach Reset beginnt ein anderes Profil mit einem neuen
Neun-Zeilen-Bootstrap. Das historische Profil ist nur im virtuellen Stack
verfuegbar; der physische Stack verwendet weiterhin ausschliesslich die in
`.env` ausgewaehlten Deploymentmodelle.

### Status, Logs Und Stopp

```bash
./tools/run_nodered_orchestration.sh virtual-status
docker compose \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.yml \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.virtual.yml \
  logs -f node_red storage_infer vgr_infer hbw_infer
./tools/run_nodered_orchestration.sh virtual-down
```

Volumes bleiben erhalten. Bei einem neuen versionierten Flow zuerst Backup,
dann `flow-update` ausfuehren.

## 4. Physisches Live-System

### Einstellungen

```env
MQTT_HOST=192.168.0.5
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
COMMAND_OUTPUT_ENABLED=false
```

### Diagnose

```bash
./tools/run_nodered_orchestration.sh physical-preflight
./tools/run_nodered_orchestration.sh physical-up
```

Jetzt NN-Status, Requests und Responses beobachten. Es werden noch keine
VGR-/HBW-Commands erzeugt.

### Kontrollierte Freigabe

Nur wenn Broker, physische Black Box, Safety und Topics geprueft sind:

```bash
./tools/run_nodered_orchestration.sh physical-down
./tools/run_nodered_orchestration.sh physical-up --command-output-enabled
```

Die physischen Grenzschnittstellen bleiben unveraendert: Live-Zustand auf
`log/logging/state`, leere Command-Payloads, QoS 2 und `retain=false`.

```bash
./tools/run_nodered_orchestration.sh physical-status
./tools/run_nodered_orchestration.sh physical-down
```

## 5. Prozess Beobachten

Eine kompakte Zeile je NN-Eingang und Vorhersage:

```bash
.venv/bin/python tools/observe_nn_inference.py \
  --host <broker> --port 1883
```

Das Werkzeug ist rein passiv und publiziert nichts. Fuer alle wichtigen Topics:

```bash
./tools/run_nodered_orchestration.sh monitor
```

Reports:

- `events.jsonl`: Ereignisse und Modellinformationen;
- `summary.csv`: ein Datensatz pro vollstaendig korreliertem Zyklus;
- `run_summary.json`: Gesamtstatus, Counts, Fehler und Konfiguration. Das Feld
  `completed` wird erst durch den korrelierten finalen Fabrikstatus gesetzt;
  abgeschlossene einzelne KI-Zyklen markieren den Gesamtlauf nicht als fertig.

## 6. Modell Mit Gleichem Featurevertrag Testen

1. Stack stoppen.
2. Zusammengehoerige Artefakte bereitstellen: `model.keras`,
   `activation.json`, `metrics.json`.
3. Kompatibilitaet pruefen:

   ```bash
   python3 tools/check_model_compatibility.py \
     --domain vgr --candidate-dir /pfad/kandidat --mode virtual
   ```

4. Kandidat aufnehmen und auswaehlen:

   ```bash
   python3 tools/manage_model_candidates.py add \
     --domain vgr --name kandidat --source /pfad/kandidat --target virtual
   python3 tools/manage_model_candidates.py select \
     --domain vgr --name kandidat --target virtual
   ```

5. Standardtrace und beide Guard-Profile ausfuehren.
6. Reports vergleichen:

   ```bash
   python3 tools/compare_model_runs.py \
     --domain vgr --baseline <baseline-report> --candidate <kandidaten-report>
   ```

7. Rueckrollen oder nach pruefbarem 320-Zustaende-Lauf promovieren:

   ```bash
   python3 tools/manage_model_candidates.py rollback --domain vgr
   python3 tools/manage_model_candidates.py promote \
     --domain vgr --report-dir <kandidaten-report>
   ```

## 7. Modell Mit Geaendertem Featurevertrag

Ein anderes Modell darf Features entfernen oder umordnen, wenn der Vertrag
und die Inputform konsistent sind. Neue Features sind nur kompatibel, wenn:

- sie in allen virtuellen Payloads und im physischen 28-Feld-Vertrag liegen;
- sie in den neun Idle-Seeds vorhanden sind;
- `empty_storage_0..9` fuer VGR/HBW erhalten bleibt;
- alle Ausgabeklassen einem vorhandenen Command-Topic zugeordnet sind.

`check_model_compatibility.py` blockiert fehlende Features, ungueltige Formen,
unbekannte Klassen und unzureichende Seeds. Neue abgeleitete Features oder
neue physische Rohfelder sind keine einfache Modellablage, sondern eine
separate Schnittstellenmigration.

Alternative Frameworks werden als eigenes `*_IMAGE` eingebunden. Der Container
muss unveraendert Request-, Response-, Contract- und Status-Topics bedienen.

## 8. Training

```bash
docker compose -f docker-compose.train.yml build
docker compose -f docker-compose.train.yml run --rm train_storage
docker compose -f docker-compose.train.yml run --rm train_vgr
docker compose -f docker-compose.train.yml run --rm train_hbw
```

Alle aktiven Configs setzen `publish_latest=false`. Details und Freigabegates:
[TRAINING_AND_MODEL_RELEASE.md](TRAINING_AND_MODEL_RELEASE.md).

## 9. Fehler Und Wiederherstellung

- `fault_latched`: Ursache in Status/Reports beheben, danach `reset`.
- Dashboard 404 bei altem Volume: Backup und `flow-update`.
- Docker-API nicht erreichbar: Docker-Daemon starten.
- Broker nicht erreichbar: `.env`, Route und Port pruefen.
- Nie automatisch fehlende Commands durch aktives Verhalten ersetzen.
- Kein `down -v` im normalen Betrieb.

Ausfuehrliche Diagnose: [SIMULATION_TROUBLESHOOTING_RUNBOOK.md](SIMULATION_TROUBLESHOOTING_RUNBOOK.md).
