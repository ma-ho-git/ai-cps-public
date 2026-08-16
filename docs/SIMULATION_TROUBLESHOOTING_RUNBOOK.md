# Troubleshooting Der Virtuellen Simulation

## Erste Diagnose

```bash
git status -sb
docker info
./tools/run_nodered_orchestration.sh virtual-status
./tools/run_nodered_orchestration.sh virtual-preflight
```

Logs:

```bash
docker compose \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.yml \
  -f scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.virtual.yml \
  logs --tail=200 node_red storage_infer vgr_infer hbw_infer mosquitto
```

## Docker Nicht Erreichbar

Symptom: `failed to connect to the docker API`.

- Docker Engine oder Docker Desktop starten.
- `docker context ls` und `docker info` pruefen.
- Unter WSL nicht Windows- und Linux-Daemon mischen.

## Fehlendes Node-RED-Secret

Das Setup erzeugt das Secret automatisch. Bei manueller Konfiguration in
`.env` setzen:

```env
NODE_RED_CREDENTIAL_SECRET=<langes-zufaelliges-secret>
```

Die `.env` muss nicht mit `source` aktiviert werden.

## Dashboard Liefert 404

Ein persistentes `nodered_data`-Volume kann einen aelteren Flow enthalten:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
./tools/run_nodered_orchestration.sh virtual-hmi --images
```

`virtual-hmi` gilt erst als bereit, wenn `/dashboard/betrieb` HTTP 200 liefert.

## Reportpfad Nicht Schreibbar

```bash
mkdir -p reports
sudo chown -R "$USER:$USER" reports
```

Danach `virtual-preflight` erneut ausfuehren.

## Interner Broker Nicht Erreichbar

- `virtual-status` pruefen.
- Mosquitto- und Node-RED-Logs lesen.
- Belegung von `MQTT_PORT` pruefen.
- Sicherstellen, dass keine zweite Installation denselben Compose-Projektnamen
  oder Hostport verwendet.

## Release Oder Image Passt Nicht

```bash
python3 tools/setup_portable_runtime.py init \
  --mode virtual --release runtime-v1.3.0
```

Der Preflight vergleicht Image-Digests und geschuetzte Dateihashes mit dem
Deployment-Lock. Keine Bestandteile verschiedener Release-Tags mischen.

## NN Offline Oder Contract Fehlt

```bash
./tools/run_nodered_orchestration.sh monitor
```

Pruefen:

- alle drei Inferenzcontainer laufen;
- retained Status und Contract erscheinen fuer Storage, VGR und HBW;
- das im HMI gewaehlte Modellprofil ist laut Contract verfuegbar;
- keine zweite Runtime konsumiert dieselben Request-Topics.

## `fault_latched`

1. Fehlercode, `cycle_id` und betroffenen Dienst im Dashboard oder Report
   sichern.
2. Ursache beheben; keine fehlenden Commands manuell ergaenzen.
3. Reset ausfuehren:

   ```bash
   ./tools/run_nodered_orchestration.sh reset
   ```

Reset verwirft Fenster, offene Zyklen und Timer. Der folgende Lauf beginnt mit
einem neuen Idle-Bootstrap.

## Semaphor Bleibt Blockiert

Im Dashboard oder Fabrikstatus `sent_count` und `accepted_count` je Modul
vergleichen. Typische Ursachen:

- fehlender oder doppelter Command
- Inferenzcontainer beendet
- Publish-Fehler
- Modul-Delay nicht abgeschlossen

Der naechste Tracezustand darf erst nach vier ausgeglichenen Modulen
freigegeben werden.

## Standortbundle Pruefen

```bash
python3 tools/manage_runtime_migration.py inspect \
  ai-cps-site-backup.tar.gz
```

Pruefsummen- oder Releasefehler nicht mit `--force` umgehen. Das beim Import
erzeugte `pre-import-*.tar.gz` ist der Ruecksprungpunkt.

## Sauber Stoppen

```bash
./tools/run_nodered_orchestration.sh virtual-down
```

Kein `down -v` im Normalbetrieb. Persistente Volumes nur nach eigenem Backup
entfernen.
