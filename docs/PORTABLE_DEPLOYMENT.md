# Portable Bereitstellung

## Ziel

Ein zweiter `linux/amd64`-Rechner soll virtuelle und physische Betriebsart aus
einem festen Release starten koennen. Freigegebene, digest-genaue GHCR-Images
sind der Betriebsstandard; lokale Builds bleiben der Entwicklungsweg.

## Uebertragbarer Bestand

- drei NN-Inferenzdienste und `model_registry/*/latest`;
- Node-RED mit FlowFuse Dashboard, Mosquitto, drei Testszenarien und zwei
  festen virtuellen Modellprofilen;
- physische und virtuelle Compose-Datei;
- drei Trainingscontainer und aktive/Regressionstrainingsdaten;
- Preflight, Modellmanager, Beobachter und Reportanalyse;
- kompakte Betriebs- und Architekturdokumentation.

## Online-Schnellstart

Empfohlen:

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

Der Assistent prueft Release-Commit, geschuetzte Dateihashes und Image-Digests,
erzeugt `.env` mit Modus `0600`, ein Node-RED-Secret, `.venv`, Reports und den
lokalen Deployment-Lock. Fuer physisch ist `--mqtt-host` verpflichtend.

## Lokaler Build

Entwickler kopieren `.env.example`, installieren
`.github/requirements-runtime-ci.lock` mit `--require-hashes` und starten ohne
`--images`. Docker baut dann Storage, VGR, HBW und Node-RED aus dem Quellstand.

## Freigegebene Images Und Manifest

Das GitHub-Release enthaelt `runtime-manifest.json` mit Source-Commit,
linux/amd64-Image-Digests, Modell-IDs/-Hashes, Trace-/Flow-Hashes,
Node-RED-Runtimeversion sowie IDs und Hashes der historischen
Demonstrationsmodelle. Der Assistent uebernimmt diese Referenzen in `.env`.
Manuelle `*_IMAGE`-Aenderungen liegen ausserhalb dieses Release-Locks.

Die vier vorhandenen GHCR-Pakete behalten aus Kompatibilitaetsgruenden ihre
Namen `ai-cps-runtime-*-infer` beziehungsweise `ai-cps-runtime-node-red`.
Ihre OCI-Quellreferenz zeigt auf `ma-ho-git/ai-cps-public`.

## Persistenz

Compose verwaltet:

- `nodered_data`
- `mosquitto_data`
- `mosquitto_log`

Reports liegen auf dem Host. Normales `virtual-down` entfernt Container und
Netzwerk, aber keine Volumes. Rolling Windows, offene Requests und laufende
Timer werden bewusst nicht migriert; nach Neustart erfolgt ein neuer Bootstrap.

Node-RED-Flow aktualisieren:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
```

Kein `down -v`, ausser ein vollstaendiger Reset aller lokalen Laufzeitdaten ist
ausdruecklich beabsichtigt.

## Vollstaendiges Standortbundle

Nur bei gestopptem Stack:

```bash
python3 tools/manage_runtime_migration.py export --output ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py inspect ai-cps-site-backup.tar.gz
python3 tools/manage_runtime_migration.py import ai-cps-site-backup.tar.gz \
  --target-project ai-cps-restored \
  --target-report-root "$PWD/reports-restored" \
  --force
```

Enthalten sind `.env`, Node-RED-/Mosquitto-Volumes, der konfigurierte
Reportpfad, ausgewaehlte Kandidaten sowie Auswahlzustand und -historie. Images,
Git-/SSH-/Docker-Zugangsdaten und unbenutzte Modellversionen sind ausgeschlossen.
Der Import prueft alle Hashes, erzeugt bei vorhandenem Zielstand ein
`pre-import-*.tar.gz` und startet den Stack nicht.

Bundle und Pre-Import-Backup erhalten immer Dateimodus `0600`. Der
V1.3.0-RC.3-Importer akzeptiert V1.1.0-, interne V1.1.1-, V1.2.0- sowie
V1.3.0-RC.1- bis RC.3-Bundles.
Vorhandene Zielvolumes
werden nach dem Backup mit dem Zielprojektnamen und den von Compose erwarteten
Labels neu angelegt; ihre Daten stammen anschliessend ausschliesslich aus dem
geprueften Bundle.

`--target-project` und `--target-report-root` ueberschreiben nur den
Docker-Namensraum und den Reportpfad. Alle weiteren Standortwerte und das
Node-RED-Secret bleiben aus dem Bundle erhalten. Damit koennen Quell- und
Wiederherstellungstest ohne gemeinsame Volumes parallel vorbereitet werden.

Das Bundle enthaelt das lokale Node-RED-Secret und die gesamte `.env` im
Klartext. Das ist fuer die abgeschlossene, isolierte Testumgebung akzeptiert.
Sobald echte Kennwoerter hinzukommen, muss das Bundle verschluesselt werden.

## Clean-Clone-Abnahme

1. Release flach klonen und Setup-Assistent ausfuehren.
2. `virtual-preflight` ausfuehren.
3. `virtual-hmi` starten und HTTP 200 fuer `/dashboard/betrieb` pruefen.
4. Standardprofil komplett ausfuehren.
5. Stack neu starten und Node-RED-/Mosquitto-Persistenz pruefen.
6. Modellkandidat testweise waehlen und wieder zurueckrollen.
7. `physical-preflight` gegen einen Testbroker ausfuehren.

Der physische Node-RED-/OPC-UA-/SPS-Aufbau wird nicht migriert; er bleibt eine
externe Black Box. Nur seine MQTT-Grenze muss erreichbar und kompatibel sein.
