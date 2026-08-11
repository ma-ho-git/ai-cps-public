# AI Development Handover

Diese Datei ist der anbieterneutrale Einstieg fuer Codex, Claude und andere
KI-Entwicklungswerkzeuge. Sie ergaenzt die Fach- und Betriebsdokumentation,
dupliziert sie aber nicht.

## System Scope

- Virtuell: Mosquitto, Node-RED/FlowFuse Dashboard, Storage-, VGR- und
  HBW-Inferenzcontainer, drei versionierte Testszenarien sowie zwei feste
  virtuelle Modellprofile. Das historische Profil dient nur der reproduzierbaren
  Demonstration des bekannten Vollspeicherfehlers.
- Physisch: nur die drei NN-Container; Node-RED, OPC UA und SPS sind eine
  externe Black Box mit eingefrorenem MQTT-Grenzvertrag.
- Training: drei reproduzierbare Trainingscontainer, die lokale Kandidaten
  erzeugen und `latest` nicht automatisch ersetzen.
- Privates Entwicklungsarchiv: Notebooks, Rohdaten, Builder und historische
  Systeme unter `development-complete-2026-08-10`; diese Referenz existiert
  nicht im oeffentlichen Runtime-Repository.

## Sources Of Truth

1. [AGENTS.md](../AGENTS.md): operative Regeln fuer Code-Agenten.
2. [README.md](../README.md): kurzer menschlicher Einstieg.
3. [OPERATION_AND_MIGRATION_GUIDE.md](OPERATION_AND_MIGRATION_GUIDE.md):
   verbindliche Bedienungsfolgen.
4. [NODERED_MQTT_ORCHESTRATION.md](NODERED_MQTT_ORCHESTRATION.md):
   Architektur und MQTT-Vertraege.
5. [TRAINING_AND_MODEL_RELEASE.md](TRAINING_AND_MODEL_RELEASE.md): Training,
   Kandidaten und Promotion.
6. [PROJECT_KNOWLEDGE.md](PROJECT_KNOWLEDGE.md): dauerhafte Entscheidungen.
7. Code, Configs und Tests entscheiden bei Widerspruechen ueber den aktuell
   implementierten Stand; Dokumentation danach korrigieren.

Das oeffentliche Runtime-Repository ist
`https://github.com/ma-ho-git/ai-cps-runtime`. Die private Git-Historie bleibt
eine getrennte Forschungsquelle und darf nicht in oeffentliche Branches
uebernommen werden.

## Protected Contracts

- Live-Eingang: `log/logging/state`.
- NN-Requests/-Responses: `ft/nn/<domain>/request` und
  `ft/nn/response/<domain>`.
- Commands: vorhandene `ai/vgr/cmd*`, `ai/hbw/cmd*`, `ai/mpo/cmd0` und
  `ai/sld/cmd0`; leere Payload, QoS 2, `retain=false`.
- VGR/HBW: Fenster `(10,29)`, darunter `empty_storage_0..9`.
- Storage: neun Belegungsfeatures, Klassen `0..9`.
- `model_registry/<domain>/latest` ist versioniert; lokale `candidates/` und
  `versions/` sind keine Git-Artefakte.
- Node-RED synchronisiert nach den vier Modulabschluessen. Die Korrelation der
  NN-Responses dient der Beobachtung und ist keine Command-Barriere.

## Session Start Protocol

1. `AGENTS.md` und diese Datei lesen.
2. `git status -sb`, `git branch --show-current` und `git log -5 --oneline`
   ausfuehren.
3. Aufgabe, bestaetigte Repo-Fakten und Annahmen kurz festhalten.
4. Nur die passenden Fachquellen und Tests lesen.
5. Bei einem schmutzigen Worktree fremde Aenderungen erhalten und integrieren.
6. Vor Laufzeittests pruefen, ob Docker und der beabsichtigte Broker aktiv sind.

## Validation Matrix

| Aenderung | Mindestpruefung |
|---|---|
| Dokumentation | Links/Pfade, `git diff --check` |
| Python | `py_compile`, relevante Unit-Tests |
| Compose/Umgebung | physische und virtuelle `docker compose config`, Preflight |
| Release/Migration | Manifest-/Setup-/Bundle-Tests, Hashpruefung, Clean-Clone |
| Node-RED/HMI | `npm test`, Flowexport, HTTP-Smoke; visuell bei UI-Aenderung |
| MQTT/Commands | Vertrags-, QoS-, Retain- und Fehlerkorrelationstests |
| Training/Daten | Trainingsvertraege, Kandidatenmodus, unveraendertes `latest` |
| Modelle | Kompatibilitaetscheck, Standardtrace und beide Full-Storage-Profile |
| Runtime | Clean-Start oder begruendeter Wiederverwendungstest, Reports pruefen |

## Session Completion And Handover

Am Ende dokumentieren:

- Branch, letzter Commit und Worktree-Status;
- geaenderte Dateien und fachliche Wirkung;
- ausgefuehrte Tests mit Ergebnis;
- nicht ausgefuehrte Tests mit Grund;
- Annahmen, bekannte Risiken und naechster konkreter Schritt;
- Pfade relevanter Reports, ohne Reports zu versionieren.

## Starter Prompts

Mit Repositoryzugriff:

```text
Lies AGENTS.md und docs/AI_DEVELOPMENT_HANDOVER.md. Fuehre das
Session-Startprotokoll aus. Bearbeite danach folgende Aufgabe minimal-invasiv,
ohne bestehende Aenderungen oder geschuetzte MQTT-/Modellvertraege zu
ueberschreiben: <AUFGABE>.
```

Ohne Repositoryzugriff muessen mindestens `AGENTS.md`, diese Datei, die zur
Aufgabe passende Fachquelle und die betroffenen Code-/Configdateien gemeinsam
bereitgestellt werden. Ein Browserchat kennt lokale Dateien nicht automatisch.

## Maintenance Rules

- Fachwissen wird in der jeweiligen Fachquelle gepflegt, nicht in Bot-Adaptern
  dupliziert.
- `CLAUDE.md` bleibt ein duennes Include auf `AGENTS.md` und diese Datei.
- Keine fluechtigen Branch- oder Commitwerte als dauerhaften Systemstand hier
  festschreiben.
- Entfernte Forschungsartefakte werden im Archiv gepflegt, nicht wieder in den
  portablen Runtime-Branch kopiert.
- Neue Pfade oder Vertragsanpassungen muessen Tests und Dokumentation im selben
  Commit aktualisieren.
