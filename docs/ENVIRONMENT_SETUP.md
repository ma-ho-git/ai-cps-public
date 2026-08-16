# Umgebung Einrichten

## Unterstuetzte Systeme

- `linux/amd64`
- Ubuntu 24.04 unter WSL2 oder natives Linux
- Docker Engine oder Docker Desktop im Linux-Container-Modus
- Python 3.12

ARM64, macOS und Windows-Container sind nicht freigegeben.

## Pakete Installieren

```bash
sudo apt update
sudo apt install -y git python3 python3-venv mosquitto-clients curl
docker version
docker compose version
```

Unter WSL2 entweder Docker Desktop mit WSL-Integration oder eine native Docker
Engine in der Distribution verwenden. Nicht beide Daemons in demselben Lauf
mischen.

## Release Klonen

```bash
git clone --depth 1 --branch runtime-v1.3.0 \
  https://github.com/ma-ho-git/ai-cps-public.git AI-CPS
cd AI-CPS
```

Ein flacher Clone enthaelt alles, was fuer die virtuelle Simulation benoetigt
wird, ohne die gesamte Git-Historie zu laden.

## Runtime Vorbereiten

```bash
python3 tools/setup_portable_runtime.py init \
  --mode virtual \
  --release runtime-v1.3.0 \
  --compose-project ai-cps-nn-runtime \
  --report-root "$PWD/reports"
```

Das Setup erzeugt und prueft:

- `.env` mit Modus `0600`
- zufaelliges `NODE_RED_CREDENTIAL_SECRET`
- lokale `.venv` fuer Bedienwerkzeuge
- schreibbaren Reportpfad
- digest-genaue Releaseimages
- `.runtime/deployment-lock.json`

Die `.env` muss nicht mit `source` aktiviert werden. Das Startskript liest sie
selbst; explizite Shellvariablen haben Vorrang.

## Docker Pruefen

```bash
docker info
./tools/run_nodered_orchestration.sh virtual-preflight
```

Bei einem `docker.sock`-Fehler zuerst Docker Engine beziehungsweise Docker
Desktop starten. Projektdateien moeglichst nicht mit `sudo docker compose`
erzeugen.

Verschiedene Installationen auf demselben Rechner brauchen unterschiedliche
Compose-Projektnamen und Reportpfade.

Danach mit [Betrieb und Migration](OPERATION_AND_MIGRATION_GUIDE.md)
fortfahren.
