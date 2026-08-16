# Publication Rights Review

Dieses interne Wartungsdokument beschreibt die Rechtefreigabe fuer
`ma-ho-git/ai-cps-public`. Der maschinenlesbare Status steht in
`configs/publication_rights.json`.

## Freigabepunkte

- [x] Rechtlich erforderliche Herkunftshinweise stehen in
  `THIRD_PARTY_NOTICES.md`.
- [x] Projektbeitraege duerfen unter `AGPL-3.0-only` veroeffentlicht werden.
- [x] Versionierte Daten und Modellartefakte duerfen weitergegeben werden.
- [x] Die drei virtuellen Traces enthalten keine vertraulichen Daten.
- [x] Der getrackte Baum enthaelt keine `.env`, Reports, Credentials oder
  lokalen Laufzeitartefakte.

Die Freigaben wurden am 10.08.2026 bestaetigt. Vertrauliche oder
personenbezogene Nachweise werden ausserhalb von Git aufbewahrt; dieses
Dokument enthaelt nur die nicht vertrauliche Entscheidung.

## Release-Gate

Vor einem Release ausfuehren:

```bash
python3 tools/check_public_release_readiness.py --require-approved
```

Ein Release ist unzulaessig, solange der maschinenlesbare Status einen
ausstehenden oder abgelehnten Freigabepunkt meldet.
