# Oeffentliche Release-Prozedur

Dieses interne Wartungsdokument beschreibt die Veroeffentlichung eines
geprueften Stands in `ma-ho-git/ai-cps-public`.

## 1. Vorbereiten

1. Releasekennung in `configs/runtime_release.json`, Dashboard,
   Dokumentation und `CITATION.cff` angleichen.
2. Modell-, Trace- und Flowhashes erfassen.
3. Vollstaendige Tests und betroffene virtuelle Szenarien ausfuehren.
4. Releasebaum pruefen:

   ```bash
   python3 tools/check_public_release_readiness.py --require-approved
   python3 tools/check_code_readability.py
   git diff --check
   ```

5. Sicherstellen, dass `.env`, Reports, Volumes, Kandidaten und temporaere
   Dateien nicht versioniert sind.

## 2. Pull Request Nach Main

1. Feature-Branch pushen und Pull Request gegen `main` oeffnen.
2. Runtime-CI, Image-Builds und erforderliche Review abwarten.
3. Nur einen konfliktfreien, vollstaendig geprueften Stand mergen.
4. Main-CI vollstaendig abwarten.

Bei fehlgeschlagener CI erfolgt kein Tag. Korrekturen werden ueber einen neuen
Commit und Pull Request eingespielt; kein Force-Push nach `main`.

## 3. Tag Veroeffentlichen

Erst nach erfolgreicher Main-CI:

```bash
git switch main
git pull --ff-only origin main
git tag -a runtime-v1.3.0 -m "AI-CPS Public V1.3.0"
git push origin runtime-v1.3.0
```

Ein Release-Tag wird niemals verschoben. Der Tag-Workflow erzeugt Images,
`runtime-manifest.json`, Source-SBOM, `SHA256SUMS`, Lizenzhinweise und
`CITATION.cff`.

## 4. Release Abnehmen

1. Release-Artefakte und Images ohne Anmeldung abrufen.
2. Tag mit `--depth 1` in ein leeres Verzeichnis klonen.
3. Setup, Preflight und Dashboard pruefen.
4. Vollstaendigen `standard`-Lauf mit `deployment-current` ausfuehren.
5. Modell-IDs, Commands, Reportabschluss und Modulcounter kontrollieren.
6. Stack ohne `down -v` stoppen.

Fruehere Release-Tags bleiben als unveraenderliche Rueckfallstaende erhalten.
