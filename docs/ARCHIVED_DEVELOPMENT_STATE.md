# Archivierter Entwicklungsstand

Der vollstaendige Forschungsstand vor der Runtime-Konsolidierung ist im
**privaten Entwicklungsrepository** dauerhaft gesichert:

- Branch: `archive/full-development-state-2026-08-10`
- Tag: `development-complete-2026-08-10`
- Archivcommit: `87b67dbf0e1ab2f7bcbdb3ecf6d1db1eca1833ad`

Diese Referenzen werden bewusst nicht in das oeffentliche Runtime-Repository
uebertragen. Dort beginnt die Historie mit einem bereinigten Initial-Commit.

Das private Archiv enthaelt insbesondere:

- 28 PLC-/Trainings-/Evaluationsnotebooks;
- Roh-, Zwischen-, Archiv- und Kandidatendatensaetze;
- Lernkurs mit 14 Notebooks;
- historische Python-Orchestratoren und Simulatoren;
- Dataset-/Payload-/UML-/Plot-Builder;
- alte Szenarien, Forschungsplots, TODOs und detaillierte Incident-Evidenz.

Archiv mit Zugriff auf das private Entwicklungsrepository auschecken:

```bash
git fetch origin development-complete-2026-08-10
git switch --detach development-complete-2026-08-10
```

Oder als separaten Arbeitsbaum:

```bash
git worktree add ../AI-CPS-development development-complete-2026-08-10
```

Der Archivbranch wird nicht weiterentwickelt. Neue Runtime- oder
Trainingsaenderungen gehoeren in aktuelle Feature-Branches. Forschungsartefakte
werden nur bei klarer fachlicher Notwendigkeit aus dem Archiv uebernommen.
