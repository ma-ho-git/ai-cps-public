# Oeffentliche Release-Prozedur

Diese Prozedur veroeffentlicht einen geprueften Stand im bestehenden
Repository `ma-ho-git/ai-cps-public`. Private Entwicklungshistorie,
Standortkonfiguration und Laufzeitartefakte gehoeren nicht in den Release.

## 1. Release Vorbereiten

1. Releasekennung in `configs/runtime_release.json`, HMI, Dokumentation und
   `CITATION.cff` angleichen.
2. Modell-, Datensatz- und Trace-Hashes vor der Abnahme erfassen.
3. Vollstaendige Tests und die betroffenen Runtime-Szenarien ausfuehren.
4. Den oeffentlichen Baum hart pruefen:

   ```bash
   python3 tools/check_public_release_readiness.py --require-approved
   python3 tools/check_code_readability.py
   git diff --check
   ```

5. Sicherstellen, dass `.env`, Reports, Volumes, Kandidaten und temporaere
   Dateien nicht versioniert sind.

## 2. Pull Request Nach Main

1. Feature-Branch zu `origin` pushen und Pull Request gegen `main` oeffnen.
2. Runtime-CI, vier Image-Builds und erforderliche Review abwarten.
3. Nur einen konfliktfreien, vollstaendig geprueften Stand mergen.
4. Main-CI vollstaendig abwarten. Die vier `latest-validated`-Images werden
   aus dem neuen Main-Commit erzeugt.

Bei fehlgeschlagener CI erfolgt kein Tag. Korrekturen werden als neuer Commit
ueber einen Pull Request eingespielt; kein Force-Push nach `main`.

## 3. Unveraenderlichen Tag Veroeffentlichen

Erst nach erfolgreicher Main-CI:

```bash
git switch main
git pull --ff-only origin main
git tag -a runtime-v1.3.0 -m "AI-CPS Public V1.3.0"
git push origin runtime-v1.3.0
```

Der Tag wird niemals verschoben oder ueberschrieben. Der Tag-Workflow erzeugt:

- vier `linux/amd64`-Images mit Release- und SHA-Tag;
- `runtime-manifest.json` mit Image-, Modell-, Trace- und Flowhashes;
- Source-SBOM und `SHA256SUMS`;
- Lizenzhinweise und `CITATION.cff`.

## 4. Release Abnehmen

1. Release-Artefakte und Images ohne GitHub-Anmeldung abrufen.
2. Tag mit `--depth 1` in ein leeres Verzeichnis klonen.
3. Setup, Preflight, Dashboard und einen vollstaendigen Standardlauf pruefen.
4. Modell-IDs, Commands, Reportabschluss und Modulcounter kontrollieren.
5. Stack ohne `down -v` stoppen und Testergebnis dokumentieren.

Fruehere Release-Tags bleiben als unveraenderliche Rueckfallstaende erhalten.
