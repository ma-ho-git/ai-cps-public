# Public Runtime Release Procedure

Diese Prozedur veroeffentlicht Runtime V1.2 ohne die private
Entwicklungshistorie. Das Zielrepository ist
`https://github.com/ma-ho-git/ai-cps-runtime`.

## 1. Freigabe

1. Alle Nachweise aus `PUBLICATION_RIGHTS_REVIEW.md` einholen.
2. Die zugehoerigen Eintraege in `configs/publication_rights.json` auf
   `approved` setzen.
3. Den harten Release-Check ausfuehren:

   ```bash
   python3 tools/check_public_release_readiness.py --require-approved
   ```

Ohne erfolgreichen Check werden weder das oeffentliche Repository noch ein
Release-Tag erzeugt.

## 2. Privaten Quellstand Einfrieren

1. Vollstaendige Tests und Runtime-Abnahmen ausfuehren.
2. Den freigegebenen Stand im privaten Repository als
   `checkpoint/portable-runtime-v1.2.0-ready-2026-08-11` sichern.
3. Den exakten Commit notieren. Der Worktree muss sauber sein.

## 3. Bereinigten Quellbaum Exportieren

```bash
mkdir -p /tmp/ai-cps-runtime-public
git archive --format=tar <FREIGEGEBENER_COMMIT> | \
  tar -xf - -C /tmp/ai-cps-runtime-public
python3 /tmp/ai-cps-runtime-public/tools/check_public_release_readiness.py \
  --require-approved
```

Der Export darf keine `.git`-Historie, `.env`, Reports, Volumes,
Modellkandidaten, Notebooks oder vollstaendige fremde Publikationen enthalten.

## 4. Oeffentliches Repository Erzeugen

Im Export wird eine neue Historie mit einer datenschutzfreundlichen
GitHub-Noreply-Adresse begonnen:

```bash
cd /tmp/ai-cps-runtime-public
git init -b main
git config user.name "ma-ho-git"
git config user.email "118806301+ma-ho-git@users.noreply.github.com"
git add .
git commit -m "Initial public runtime release"
```

Vor dem Push ist zu pruefen, dass genau ein Commit vorhanden ist. Danach wird
das neue **oeffentliche** GitHub-Repository angelegt, als `origin` eingetragen
und `main` gepusht. Branchschutz verlangt die Runtime-CI fuer weitere
Aenderungen.

## 5. Images Und Release

1. CI fuer `main` vollstaendig abwarten.
2. Alle vier GHCR-Packages auf `public` stellen und anonymen Pull pruefen.
3. Den zur Releasekonfiguration passenden unveraenderlichen Runtime-Tag
   erzeugen und pushen, fuer diesen Release `runtime-v1.2.0`.
4. Release-Manifest, `SHA256SUMS`, Source-SBOM, Notices, Citation und
   Image-Digests pruefen.
5. Clean-Install und Standort-Restore mit getrennten Compose-Projekten und
   Reportpfaden abnehmen.

Das private Entwicklungsrepository bleibt erhalten, ist aber nicht die
oeffentliche Runtime-Quelle.
