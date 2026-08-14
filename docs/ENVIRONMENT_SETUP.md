# Umgebung Einrichten

## Unterstuetzte Systeme

- `linux/amd64`
- Ubuntu 24.04 unter WSL2 oder natives Linux
- native Docker Engine oder Docker Desktop im Linux-Container-Modus
- Python 3.12

ARM64, macOS und Windows-Container sind nicht freigegeben.

## Pakete

```bash
sudo apt update
sudo apt install -y git python3 python3-venv mosquitto-clients curl
docker version
docker compose version
```

Unter WSL2 kann entweder Docker Desktop mit aktivierter WSL-Integration oder
eine native Docker Engine innerhalb der Distribution verwendet werden. Nicht
beide Daemons gleichzeitig fuer denselben Lauf mischen.

## Repository

Fuer einen Betriebsrechner wird wegen der grossen Forschungshistorie ein
flacher Clone empfohlen:

```bash
git clone --depth 1 --branch runtime-v1.3.0-rc.2 \
  https://github.com/ma-ho-git/ai-cps-runtime.git AI-CPS
cd AI-CPS
```

Fuer Forschungsarbeiten mit Historie normal klonen oder den Archivtag
Mit Zugriff auf das private Entwicklungsrepository kann fuer historische
Forschungsartefakte `development-complete-2026-08-10` ausgecheckt werden. Der
Tag ist nicht Bestandteil des oeffentlichen Runtime-Repositorys.

## Python-Werkzeuge

Die Runtime selbst laeuft in Containern. Die lokale Umgebung wird nur fuer
Preflight, Modellverwaltung, Beobachtung und Tests benoetigt.

```bash
python3 tools/setup_portable_runtime.py init \
  --mode virtual --release runtime-v1.3.0-rc.2
```

TensorFlow ist lokal nicht erforderlich, wenn Training und Modellpruefung in
Docker erfolgen.

Der Assistent verwendet die hash-gesperrte Werkzeug-Lockdatei. Fuer einen
manuellen Entwicklungsaufbau:

```bash
cp .env.example .env
chmod 600 .env
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes \
  -r .github/requirements-runtime-ci.lock
```

Mindestens setzen:

```env
NODE_RED_CREDENTIAL_SECRET=<langes-zufaelliges-secret>
```

Fuer den physischen Betrieb:

```env
MQTT_HOST=192.168.0.5
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
```

`.env` wird nie versioniert. Die virtuelle Simulation ueberschreibt den
Broker intern mit dem Compose-Service `mosquitto`.

## Docker-Berechtigungen Und Projektname

```bash
docker info
mkdir -p reports
COMPOSE_PROJECT_NAME=ai-cps-nn-runtime
```

Der Setup-Assistent traegt Host-UID/GID ein; ein einmaliger Compose-Helfer
richtet Node-RED-Volume und Reportpfad ein. Verschiedene Standorte auf einem
Host benoetigen unterschiedliche `COMPOSE_PROJECT_NAME`-Werte.

Bei `docker.sock`-Fehlern zuerst den Docker-Daemon beziehungsweise Docker
Desktop starten. Keine Projektdateien mit `sudo docker compose` erzeugen, wenn
es vermeidbar ist.

## Erstpruefung

```bash
./tools/run_nodered_orchestration.sh virtual-preflight
docker compose -f docker-compose.train.yml config
```

Danach mit `virtual-hmi` oder `virtual-run` fortfahren. Die genaue Reihenfolge
steht in [OPERATION_AND_MIGRATION_GUIDE.md](OPERATION_AND_MIGRATION_GUIDE.md).
