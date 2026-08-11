# Troubleshooting Runbook

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

- Docker Desktop oder den nativen Docker-Daemon starten.
- `docker context ls` und `docker info` pruefen.
- Unter WSL nicht versehentlich Windows- und Linux-Daemon mischen.

## Preflight Meldet Fehlendes Secret

In `.env` setzen:

```env
NODE_RED_CREDENTIAL_SECRET=<langes-zufaelliges-secret>
```

Die Datei muss nicht mit `source .env` aktiviert werden; das Startskript liest
sie selbst. Bereits gesetzte Shellvariablen haben Vorrang.

## Dashboard Liefert 404

Ein bestehendes `nodered_data`-Volume kann einen alten Flow enthalten:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
./tools/run_nodered_orchestration.sh virtual-hmi
```

`virtual-hmi` gilt erst als erfolgreich, wenn
`/dashboard/betrieb` HTTP 200 liefert.

## Reportpfad Nicht Schreibbar

```bash
mkdir -p reports
sudo chown -R "$USER:$USER" reports
```

Danach Preflight wiederholen. Reports nicht mit Root-Eigentum erzeugen.

## Broker Nicht Erreichbar

- Virtuell: `virtual-status` und Mosquitto-Logs pruefen.
- Physisch: `MQTT_HOST`, Port, Route, Firewall und Credentials pruefen.
- Der physische Preflight erwartet einen erfolgreichen MQTT-CONNACK, sendet
  dabei aber keine fachliche Nachricht.

## Release Oder Image Passt Nicht

```bash
python3 tools/setup_portable_runtime.py init \
  --mode virtual --release runtime-v1.1.1
```

Der Preflight vergleicht digest-genaue Image-Referenzen und geschuetzte
Dateihashes mit `.runtime/deployment-lock.json`. Keine einzelnen Dateien aus
verschiedenen Release-Tags mischen.

## Standortbundle Pruefen

```bash
python3 tools/manage_runtime_migration.py inspect ai-cps-site-backup.tar.gz
```

Bei einem Pruefsummen- oder Releasefehler nicht mit `--force` umgehen. Das beim
Import erzeugte `pre-import-*.tar.gz` ist der Ruecksprungpunkt.

```bash
mosquitto_sub -h <host> -p 1883 -t 'ft/nn/+/status' -v
```

## NN Offline Oder Contract Fehlt

```bash
./tools/run_nodered_orchestration.sh monitor
```

Pruefen:

- `model_registry/<domain>/latest` enthaelt drei Artefakte;
- Modellpfad in `.env` liegt unter `/model_registry`;
- keine zweite Runtime konsumiert dieselben Request-Topics;
- Containerlog zeigt geladenes Modell und retained Online-Status.

## `fault_latched`

1. Fehlercode, `cycle_id` und betroffenen Dienst aus Status/Report sichern.
2. Ursache beheben; keine fehlenden Commands manuell ergaenzen.
3. Danach:

   ```bash
   ./tools/run_nodered_orchestration.sh reset
   ```

Reset verwirft Fenster, offene Zyklen und Timer. Der naechste Zustand startet
mit einem neuen Idle-Bootstrap.

## Semaphor Bleibt Offen

Im Fabrikstatus je Modul `sent_count` und `accepted_count` vergleichen.
Ursachen sind typischerweise fehlender Command, doppelter Command,
Containerabbruch oder Publish-Fehler. Der naechste Zustand darf erst bei vier
ausgeglichenen Modulen erscheinen.

## Modellkandidat Funktioniert Nicht

```bash
python3 tools/manage_model_candidates.py status
python3 tools/manage_model_candidates.py rollback --domain <domain>
```

Danach Stack neu starten. Kein Hot-Swap waehrend eines Zyklus.

## Sauber Stoppen

```bash
./tools/run_nodered_orchestration.sh virtual-down
./tools/run_nodered_orchestration.sh physical-down
```

Kein `down -v` im Normalbetrieb. Persistente Volumes oder lokale Modellversionen
nur nach eigenem Backup entfernen.
