# Audit: anfaengerfreundliches Code-Refactoring

Stand: `runtime-v1.3.0-rc.2`, Commit `f5e814a663213ef5209448dc4b346c145e17a3d6`

Ziel: Ausfuehrbaren Code leichter lesbar und aenderbar machen, ohne Verhalten,
Vertraege oder wissenschaftliche Ergebnisse zu veraendern. Diese Liste ist die
verbindliche Arbeitsgrundlage fuer `feature/beginner-friendly-code-refactor`.

## Lesbarkeitsregeln

- Produktionsfunktion: hoechstens 60 Zeilen
- Callback und `main()`: hoechstens 40 Zeilen
- hoechstens drei sichtbare Verschachtelungsebenen
- eine Funktion: eine klar benannte Aufgabe
- fruehe Rueckgabe statt tiefer Verschachtelung
- Kommentare und Docstrings: deutsch, kurz, stenoartig
- technische Bezeichner: englisch und konsistent
- JSONata: hoechstens 200 Zeichen, nur kurze Feldabbildungen
- Node-RED: Standard-Nodes vor Function-Nodes
- keine versteckte Fachlogik in Templates oder langen JSONata-Ausdruecken

## Baseline

| Pruefung | Ergebnis vor Refactoring |
|---|---|
| Git | sauberer Branch auf `f5e814a` |
| Python | 167 Tests erfolgreich |
| Node-RED | 5 Testdateien erfolgreich |
| Flowexport | `flows_ai_orchestration.json` aktuell |
| Shell | `run_nodered_orchestration.sh` syntaktisch gueltig |
| Compose | physisch, virtuell und Training gueltig |
| Python-Funktionen | 62 ueber 40 Zeilen, davon 31 ueber 60 und 12 ueber 100; inklusive Tests |
| Produktionsfunktionen | 48 ueber 40 Zeilen, davon 28 ueber 60 und 12 ueber 100 |
| Node-RED-Functions | exakt 4; 12, 23, 31 und 36 Codezeilen |
| JSONata | 426 Ausdruecke; 27 ueber 200 Zeichen; Maximum 3.963 Zeichen |
| Generator | 1.958 Zeilen; groesster Builder 332 Zeilen |

Geschuetzte Ausgangshashes:

| Artefakt | SHA-256 |
|---|---|
| Storage `model.keras` | `6ef3fdb63813fa270ab75c45919e1d9bb9b3158b8ba32eca3a1b8dc768c2f00d` |
| VGR `model.keras` | `654a7c781949fe3b2af27203c32687a73890af52cd3934b6b2678e5fe67c1afa` |
| HBW `model.keras` | `d8559bef03fcb22e3c10b67ef927697a728ef6580ed0df7588f39b0389f02305` |
| Standardtrace | `09a227f14b5b5716cefa9527fd09762a76d7f185340e02ae8af4a2d1fb1d2741` |
| Stationaerer Vollspeichertrace | `66644b6c2dc8ef8311d8d034303d41f5f737f46a12afbc1f86dbd186ece322c7` |
| Prozessartiger Vollspeichertrace | `d7b949389decaa3f569fc632ea7588d0a6cfd89ddf1b7def822e863181eb2a66` |

Funktionale RC.2-Referenz:

- aktueller Modellstand, Standard: 320 vollstaendige Zustaende
- aktueller Modellstand, stationaer: 20/20 VGR und HBW Idle
- aktueller Modellstand, prozessartig: 171/171 VGR und HBW Idle
- historischer Modellstand, Standard: technisch vollstaendig
- historischer Modellstand, stationaer: dokumentierter VGR-Fehler reproduziert
- historischer Modellstand, prozessartig: dokumentierter Vollspeicherfehler reproduziert

Diese sechs Laufresultate werden nach dem Refactoring erneut erzeugt. Modell-
und Trace-Dateien duerfen sich dabei nicht aendern.

## Artefaktklassifikation

| Klasse | Artefakte | Begruendung |
|---|---|---|
| `refactor` | `tools/nodered_low_code_flow.py`, `tools/build_modular_nodered_flow.py` | Generator zu gross; Verantwortungen vermischt |
| `refactor` | `training/*/train.py` | grosse Ablauf-, Daten- und Auswertungsfunktionen |
| `refactor` | `scenarios/.../code_base_*/mqtt_infer.py` | Callbacks erledigen mehrere Aufgaben |
| `refactor` | `scenarios/.../code_base_common/*.py` | Profil- und MQTT-Helfer teilweise zu breit |
| `refactor` | `tools/*.py` | mehrere grosse Analyse-, Deployment- und Migrationseinheiten |
| `refactor` | `tools/run_nodered_orchestration.sh` | Parser, Pruefungen und Modi deutlicher trennen |
| `refactor` | `tests/*.py`, aktueller Node-RED-Flowtest | lange Tests ueber Fixture-Helfer lesbarer machen |
| `remove` | `node_red/lib/{bootstrap,hmi,orchestration,reporting,virtual_factory}.js` | vom aktuellen Runtimeflow nicht geladen |
| `remove` | alte Node-RED-Tests fuer diese Referenzkerne | testen nicht den aktiven Implementierungspfad |
| `keep` | kleine Analyse-, Export-, Monitor- und SBOM-Helfer | bereits begrenzt und eindeutig |
| `generated` | `node_red/flows.json`, `node_red/flows_ai_orchestration.json` | nur ueber Generator und Exportwerkzeug aendern |
| `generated` | `package-lock.json`, Release-Manifeste und SBOM-Ausgaben | nicht manuell refaktorieren |
| `configuration` | JSON-Configs, Compose, Dockerfiles, CI und `settings.js` | lesbar pruefen; Verhalten und Werte schuetzen |
| `configuration` | Modelle, CSVs und Trace-Payloads | unveraenderliche Datenartefakte; nicht refaktorieren |

`scenarios/...` steht fuer
`scenarios/serve_ft_nns_external_broker/x86_64/`.

## Aufgabenliste

Statuswerte: `pending`, `in_progress`, `completed`, `kept`.

| ID | Bereich und Fundstelle | Problem / Messwert | Zielmassnahme | Absicherung | Status |
|---|---|---|---|---|---|
| AR-001 | `tools/nodered_low_code_flow.py` | 1.958 Zeilen; vier Builder ueber 170 Zeilen | Module je Flowtab; kleine Node-Fabriken | Flowexport und Strukturtests | completed |
| AR-002 | `build_pipeline_nodes()` | 332 Zeilen | Storage, Windowing, Requests und Responses trennen | MQTT-/Flowvertragstests | completed |
| AR-003 | `update_low_code_hmi()` | 260 Zeilen | HMI-Bereiche und Widgets trennen | HMI-Struktur- und Browsertest | completed |
| AR-004 | `build_subflows()` | 240 Zeilen | Modul- und Window-Subflow separat bauen | vier Function-Ausnahmen pruefen | completed |
| AR-005 | `build_init_nodes()` | 221 Zeilen | Start, Reset, Trace und Idle-Zweige trennen | Start-/Resettests | completed |
| AR-006 | `build_reporting_nodes()` | 171 Zeilen | Zyklus, Summary und Dateien trennen | Reportvertragstests | completed |
| AR-007 | Generator-JSONata | 27 Ausdruecke ueber 200 Zeichen; max. 3.963 | Standard-Nodes und kurze Feldabbildungen | neuer JSONata-Grenztest | completed |
| AR-008 | vier Node-RED-Functions | 12-36 Zeilen | beibehalten; eine Aufgabe; Steno-Hilfe | Zeilen-/Hilfetexttest | completed |
| AR-009 | `node_red/lib/*.js` | fuenf nicht geladene Referenzkerne | Schutztests uebertragen; Dateien entfernen | aktuelle Flow-/Dockerregression | completed |
| AR-010 | alte Node-RED-Tests | binden nur tote Referenzkerne | aktive Flowvertraege direkt testen | `npm test` | completed |
| AR-011 | `training/vgr/train.py:main()` | 316 Zeilen | Config, Daten, Training, CV, Evaluation, Artefakte trennen | Trainingsvertrag und Smoke | pending |
| AR-012 | `training/vgr/run_group_cross_validation()` | 120 Zeilen | Fold-Aufbau, Fit und Ergebnis trennen | CV-Ergebnistest | pending |
| AR-013 | `training/vgr/validate_input_data()` | 67 Zeilen | Schema- und Inhaltspruefung trennen | Datensatzvertrag | pending |
| AR-014 | `training/hbw/train.py:main()` | 189 Zeilen | Ablauf in benannte Schritte zerlegen | Trainingsvertrag und Smoke | pending |
| AR-015 | `training/hbw/validate_input_data()` | 64 Zeilen | Schema- und Inhaltspruefung trennen | Datensatzvertrag | pending |
| AR-016 | `training/storage/train.py:main()` | 152 Zeilen | Daten, Fit, Evaluation und Ablage trennen | Truth-Table-Test | pending |
| AR-017 | VGR/HBW `mqtt_infer.py:on_message()` | je 73 Zeilen | Lesen, Profil, Inferenz, Command und Response trennen | MQTT- und Direct-Command-Tests | completed |
| AR-018 | `model_profiles.load_profile_specs()` | 71 Zeilen | Kataloglesen und Profilvalidierung trennen | Profilvertragstest | completed |
| AR-019 | `check_model_compatibility.analyze_model()` | 144 Zeilen | Artefakt-, Form-, Feature- und Mappingchecks trennen | Kompatibilitaetstests | completed |
| AR-020 | `compare_model_runs.compare_runs()` | 117 Zeilen | Reports lesen, vergleichen und Ergebnis bauen trennen | Vergleichstests | completed |
| AR-021 | `evaluate_full_storage_guard_models.evaluate_domain()` | 113 Zeilen | Modellladen, Fenster, Metriken und Ausgabe trennen | Guard-Evaluationstest | completed |
| AR-022 | `manage_model_candidates.py` | Promotion 90; Parser 84; Auswahl 57 | Teilpruefungen und Command-Parser trennen | Kandidatenmanager-Suite | completed |
| AR-023 | `setup_portable_runtime.init_runtime()` | 88 Zeilen | Pfade, Environment, Images und Preflight trennen | Setup-Suite | completed |
| AR-024 | `manage_runtime_migration.py` | Import 62; Export 52 | Archivpruefung, Backup und Restore trennen | Migration-Suite | completed |
| AR-025 | `check_deployment_readiness.py` | mehrere Funktionen 42-78 Zeilen | einzelne Checks und Sammler vereinfachen | Preflight-Suite | completed |
| AR-026 | Vollspeicher-Analysewerkzeuge | Analysen 72 und 87 Zeilen | Laden, Filtern, Befund und Ausgabe trennen | Analyse-Suiten | completed |
| AR-027 | `observe_nn_inference.main()` | 44 Zeilen | Parser, Client und Lauf trennen | Beobachtertests | completed |
| AR-028 | `run_nodered_orchestration.sh` | grosser Modus-Dispatcher und Optionspfad | Parser-, Check- und Modusfunktionen | Shell- und CLI-Vertragstests | pending |
| AR-029 | lange Python-Tests | 14 Tests ueber 40 Zeilen | eindeutige Fixture-Helfer; ein Verhalten je Test | vollstaendige Suite | pending |
| AR-030 | Docker, Compose, CI | korrekt, aber Querverweise auf tote Libs moeglich | Namen/Phasen klaeren; tote Erwartungen entfernen | drei Compose-Ausgaben und CI | pending |
| AR-031 | automatische Lesbarkeitspruefung | bisher nicht vorhanden | AST-, Function-, JSONata- und Totpfadcheck | CI und Unit-Test | pending |
| AR-032 | Dokumentation | Regeln und Status noch nicht dauerhaft verankert | Audit fortschreiben; Wissen/Beitragshinweise | Doku-Test und `diff --check` | pending |

## Nicht Zu Aendernde Vertraege

- MQTT-Topics, Payloadformen, QoS und Retain-Flags
- Feature-Reihenfolgen, Klassen und Command-Mappings
- Modelle, Trainingsdaten und Trace-Payloads
- Semaphor-, Bootstrap-, Timeout- und Fault-Latch-Verhalten
- HMI-Bedienumfang und sichtbare Simulationsergebnisse
- Reportdateien und CLI-Kompatibilitaet
- physischer MQTT-Grenzvertrag

## Abschlussvergleich

Dieser Abschnitt wird nach Phase 2 ausgefuellt.

| Messwert | Vorher | Nachher |
|---|---:|---:|
| Produktionsfunktionen ueber 60 Zeilen | 28 | pending |
| Callbacks / `main()` ueber 40 Zeilen | 4 | pending |
| Node-RED-Function-Nodes | 4 | 4 |
| Function-Codezeilen, Maximum | 36 | 36 |
| JSONata ueber 200 Zeichen | 27 | 0 |
| Nicht geladene JavaScript-Kerne | 5 | 0 |
| Python-Tests | 167 erfolgreich | pending |
| Node-RED-Testdateien | 5 erfolgreich | 2 erfolgreich; aktive Pfade |
