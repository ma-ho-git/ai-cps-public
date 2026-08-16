# AI Development Handover

Diese Datei ist der anbieterneutrale Einstieg fuer Codex, Claude und andere
KI-Entwicklungswerkzeuge. Sie verweist auf die verbindlichen Fachquellen und
dupliziert deren Details nicht.

## System Scope

- Virtueller Docker-Stack: Mosquitto, Node-RED, FlowFuse Dashboard sowie
  Storage-, VGR- und HBW-Inferenzdienst.
- Drei versionierte Testszenarien und zwei virtuelle Modellprofile.
- Fuenf Node-RED-Funktionstabs fuer Initialisierung, Zustandserfassung,
  virtuelle Module, Jobcounter-Semaphor und NN-Pipeline.
- Reports fuer Ereignisse, korrelierte Zyklen und Gesamtlaufstatus.
- Standortbundle fuer `.env`, persistente Volumes und Reports.

## Sources Of Truth

1. [AGENTS.md](../AGENTS.md): operative Regeln fuer Code-Agenten.
2. [README.md](../README.md): kurzer menschlicher Einstieg.
3. [VIRTUAL_SCENARIOS.md](VIRTUAL_SCENARIOS.md): Szenarien und Erwartungen.
4. [OPERATION_AND_MIGRATION_GUIDE.md](OPERATION_AND_MIGRATION_GUIDE.md):
   verbindliche Bedienungsfolgen.
5. [NODERED_MQTT_ORCHESTRATION.md](NODERED_MQTT_ORCHESTRATION.md):
   Architektur und MQTT-Datenfluss.
6. [PROJECT_KNOWLEDGE.md](PROJECT_KNOWLEDGE.md): dauerhafte Entscheidungen.
7. Code, Konfigurationen und Tests entscheiden bei Widerspruechen ueber den
   implementierten Stand; die Dokumentation wird danach korrigiert.

## Protected Contracts

- Anlagenzustand: `log/logging/state`.
- NN-Requests/-Responses: `ft/nn/<domain>/request` und
  `ft/nn/response/<domain>`.
- Commands: `ai/vgr/cmd*`, `ai/hbw/cmd*`, `ai/mpo/cmd0` und `ai/sld/cmd0`;
  leere Payload, QoS 2, `retain=false`.
- VGR/HBW: Fenster `(10,29)` mit `empty_storage_0..9`.
- Storage: neun Belegungsfeatures und Klassen `0..9`.
- Modellprofile: `deployment-current` und
  `historical-full-storage-error`.
- Jobcounter-Semaphor: Freigabe erst nach Abschluss aller vier Module.
- NN-Responsekorrelation: nur Beobachtung, keine Command-Barriere.

## Readability Contract

- Eine Funktion: eine benannte Aufgabe.
- Produktion: maximal 60 Zeilen; Callback, `main()` und Test: maximal 40.
- Kommentare und Docstrings: deutsch, kurz, Zweck oder Sicherheitsgrund.
- Node-RED: Core-Nodes vor Function-Nodes; Flow nur aus Generator erzeugen.
- Exakt vier Function-Ausnahmen; Hilfe mit Aufgabe, Ein-/Ausgang und Zustand.
- JSONata: maximal 200 Zeichen; keine versteckte Prozesslogik.
- Pflichtcheck: `python tools/check_code_readability.py`.

## Session Start Protocol

1. `AGENTS.md` und diese Datei lesen.
2. `git status -sb`, `git branch --show-current` und `git log -5 --oneline`
   ausfuehren.
3. Aufgabe, bestaetigte Repo-Fakten und Annahmen kurz festhalten.
4. Nur die passenden Fachquellen und Tests lesen.
5. Bei einem schmutzigen Worktree fremde Aenderungen erhalten und integrieren.
6. Vor Laufzeittests Docker, Ports und beabsichtigten MQTT-Broker pruefen.

## Validation Matrix

| Aenderung | Mindestpruefung |
|---|---|
| Dokumentation | Links/Pfade, Dokumentationstests, `git diff --check` |
| Python | `py_compile`, relevante Unit-Tests |
| Lesbarkeit | `python tools/check_code_readability.py` |
| Compose/Umgebung | virtuelle Compose-Konfiguration und Preflight |
| Release/Migration | Manifest-, Setup- und Bundle-Tests |
| Node-RED/HMI | `npm test`, Flowexport, HTTP-Smoke; visuell bei UI-Aenderung |
| MQTT/Commands | Vertrags-, QoS-, Retain- und Fehlerkorrelationstests |
| Modelle/Szenarien | Standardtrace und betroffene Vollspeicherprofile |
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
ohne bestehende Aenderungen oder geschuetzte Runtimevertraege zu
ueberschreiben: <AUFGABE>.
```

Ohne Repositoryzugriff muessen mindestens `AGENTS.md`, diese Datei, die zur
Aufgabe passende Fachquelle und die betroffenen Code-/Konfigurationsdateien
gemeinsam bereitgestellt werden. Ein Browserchat kennt lokale Dateien nicht
automatisch.

## Maintenance Rules

- Fachwissen in der passenden Fachquelle pflegen, nicht in Bot-Adaptern
  duplizieren.
- `CLAUDE.md` bleibt ein duennes Include auf `AGENTS.md` und diese Datei.
- Keine fluechtigen Branch- oder Commitwerte als dauerhaften Systemstand
  festschreiben.
- Neue Pfade oder Vertragsanpassungen aktualisieren Tests und Dokumentation im
  selben Commit.
