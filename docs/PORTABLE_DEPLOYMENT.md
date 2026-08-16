# Portable Bereitstellung

## Ziel

Ein `linux/amd64`-Rechner soll die virtuelle Simulation reproduzierbar aus
einem festen Release starten koennen. Digest-genaue GHCR-Images sind der
Standard; ein lokaler Quellbuild bleibt fuer Codeaenderungen moeglich.

## Uebertragbarer Bestand

- Mosquitto und Node-RED mit FlowFuse Dashboard
- Storage-, VGR- und HBW-Inferenzdienst
- aktuelle und historische virtuelle Modellprofile
- drei versionierte Testszenarien
- persistente Node-RED-/Mosquitto-Volumes
- Reports und lokale Standortkonfiguration

## Release-Installation

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

Das Release-Manifest bindet Source-Commit, Image-Digests, Modell-IDs,
Modellhashes, Tracehashes und Flowhash. Der Deployment-Lock verhindert, dass
unbemerkt Bestandteile verschiedener Releases gemischt werden.

Die vier GHCR-Pakete behalten aus Kompatibilitaetsgruenden die Namen
`ai-cps-runtime-*-infer` und `ai-cps-runtime-node-red`.

## Persistenz

Compose verwaltet:

- `nodered_data`
- `mosquitto_data`
- `mosquitto_log`

Reports liegen auf dem Host. `virtual-down` entfernt Container und Netzwerk,
aber keine Volumes. Rolling Windows, offene Requests und Timer werden nicht
persistiert; nach einem Neustart beginnt ein kontrollierter Bootstrap.

Vor einem Flowupdate:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
```

## Standortbundle

Nur bei gestopptem Stack:

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

Enthalten sind `.env`, persistente Volumes und Reports. Docker-Images sowie
Git-, SSH-, GitHub- und Docker-Anmeldedaten sind nicht enthalten. Der Import
prueft die Hashes, erstellt vor dem Ersetzen ein Backup und startet den Stack
nicht automatisch.

Bundle und Pre-Import-Backup besitzen Modus `0600`. Da die `.env` und das
Node-RED-Secret im Klartext enthalten sind, ist das Archiv ausserhalb einer
abgeschotteten Testumgebung zu verschluesseln.

## Abnahme Auf Einem Neuen Rechner

1. Release in ein leeres Verzeichnis klonen.
2. Setup mit eigenem Compose-Projektnamen und Reportpfad ausfuehren.
3. `virtual-preflight` erfolgreich abschliessen.
4. Dashboard starten und HTTP 200 fuer `/dashboard/betrieb` pruefen.
5. `standard` mit `deployment-current` vollstaendig ausfuehren.
6. Stack stoppen und erneut starten; persistente Konfiguration pruefen.
7. Bei Bundle-Migration Reports und Volumenamen gegen die Quelle vergleichen.

Die Szenarioerwartungen stehen in [VIRTUAL_SCENARIOS.md](VIRTUAL_SCENARIOS.md).
