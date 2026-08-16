# Node-RED-/MQTT-Ablauf

## Container

Der virtuelle Stack besteht aus:

- `mosquitto`: interner MQTT-Broker
- `node_red`: Fabrikablauf, Semaphor, NN-Pipeline, Reporting und Dashboard
- `storage_infer`: Vorhersage des freien Lagerfachs
- `vgr_infer`: VGR-Command aus LSTM-Fenster
- `hbw_infer`: HBW-Command aus LSTM-Fenster

Die Inferenzdienste bleiben zustandslos. Node-RED verwaltet den Zustand eines
Simulationslaufs.

## MQTT-Topics

| Zweck | Topic |
|---|---|
| Virtueller Rohzustand | `ft/sim/factory/raw_state` |
| Freigegebener Anlagenzustand | `log/logging/state` |
| Storage Request/Response | `ft/nn/storage/request`, `ft/nn/response/storage` |
| VGR Request/Response | `ft/nn/vgr/request`, `ft/nn/response/vgr` |
| HBW Request/Response | `ft/nn/hbw/request`, `ft/nn/response/hbw` |
| Modellvertraege | `ft/nn/<domain>/contract` |
| Dienststatus | `ft/nn/<domain>/status` |
| Orchestrierungsstatus | `ft/ai/orchestration/status` |
| Zyklusergebnis | `ft/ai/orchestration/cycle_result` |
| Fabriksteuerung | `ft/sim/factory/control` |
| Fabrikstatus | `ft/sim/factory/status` |

VGR und HBW publizieren ihre leeren Commands direkt auf
`ai/<domain>/cmd<code>`. Der KI-Flow publiziert die MPO-/SLD-Idle-Commands.
Commands verwenden QoS 2 und `retain=false`.

## Flow-Tabs

### `00 Initialisierung`

- Startkonfiguration validieren
- gewaehlten Trace laden
- Run-ID, Traceposition, Fault-Latch und Jobcounter initialisieren
- je ein Idle-Command fuer VGR, HBW, MPO und SLD publizieren
- Reset an alle zustandsbehafteten Pfade verteilen

### `10 Zustandserfassung`

- aktuellen Tracezustand alle 50 ms publizieren
- internes Topic `ft/sim/factory/raw_state`
- Traceindex nicht durch den Tick veraendern

Dadurch kann derselbe Rohzustand mehrfach erscheinen, waehrend Module noch
arbeiten.

### `20 Virtuelle Module`

Vier getrennte Gruppen verarbeiten VGR-, HBW-, MPO- und SLD-Commands:

1. Command pruefen und `sent_count` erhoehen.
2. Reproduzierbare Laufzeit aus Seed, Modul, Jobnummer und Basiszeit bilden.
3. Teilprozess mit Core-`delay` simulieren.
4. `accepted_count` erhoehen und Modul freigeben.

Standardbasiszeit sind 100 ms. Je Command gilt ein reproduzierbarer Faktor von
0,5 bis 1,5.

### `30 Semaphor`

Ein Zustand wird genau einmal auf `log/logging/state` freigegeben, wenn:

- jedes Modul einen neuen Command erhalten hat;
- fuer alle Module `sent_count == accepted_count` gilt;
- kein Fault aktiv ist;
- der aktuelle Tracezustand noch nicht freigegeben wurde.

Erst die Freigabe erhoeht den Traceindex. Nach dem letzten Zustand wartet der
Semaphor auf dessen vollstaendiges Command-Set und publiziert dann
`state=completed`.

### `40 NN-Pipeline`

1. Modellvertraege, Profil, Features, Klassen und Command-Mappings pruefen.
2. Storage-Request publizieren.
3. Storage-Klasse in `empty_storage_0..9` codieren.
4. VGR- und HBW-Fenster mit Laenge 10 aktualisieren.
5. Bei neuer Quelle neun interne Idle-Eintraege ergaenzen.
6. VGR- und HBW-Requests parallel publizieren.
7. Responses nur fuer Beobachtung und Reports korrelieren.

Die Korrelation ist keine Command-Barriere.

## Modellprofile

- `deployment-current`: aktueller Modellstand
- `historical-full-storage-error`: historisches VGR-/HBW-Paar fuer die
  Vollspeicherfehler-Demonstration

Das Profil wird beim Start festgelegt, an jeden VGR-/HBW-Request weitergegeben
und in Status und Reports gespeichert. Nach einem Profilwechsel beginnt das
Windowing mit neuem Bootstrap.

## Low-Code-Struktur

Routing, Validierung, Serialisierung, Reporting, HMI und Verzoegerungen
verwenden Node-RED-Core-Nodes. Wiederholte Ablaeufe sind als Subflows sichtbar.

Exakt vier begrenzte Function-Nodes bleiben:

- deterministische Modullaufzeit berechnen
- Semaphorentscheidung und Traceindex atomar aktualisieren
- dynamischen Modellvertrag pruefen
- LSTM-Fenster quell- und modellbezogen fortschreiben

Jede Function besitzt im Editor Hilfe zu Aufgabe, Eingang, Zustand, Ausgang
und Begruendung. JSONata bleibt auf kurze Feldabbildungen begrenzt.

## Dashboard Und Fehler

Das Dashboard unter `/dashboard/betrieb` zeigt Laufstatus, Fortschritt,
Vorhersagen, Konfidenzen, Modulcounter, Semaphorstatus und Fehler. Einstellbar
sind Szenario, Modellprofil, Seed und vier Modulbasiszeiten.

Gezielte `catch`- und MQTT-`status`-Pfade behandeln unter anderem:

- ungueltige Startkonfiguration
- fehlenden oder inkompatiblen Modellvertrag
- ungueltigen Payload
- Inferenz- oder Command-Timeout
- doppelten Command
- blockierten Semaphor
- MQTT- oder Reportfehler

Ein kritischer Fehler setzt `fault_latched`. Weitere Zustaende bleiben bis zum
Reset blockiert. Debug-Nodes zeigen nur IDs, Topic, Klasse, Laufzeit und
Counter, keine vollstaendigen Rohpayloads oder LSTM-Fenster.

## Persistenz Und Reports

Docker-Volumes persistieren Node-RED- und Mosquitto-Daten. Rolling Windows,
offene Requests und Timer werden nach Neustart bewusst neu initialisiert.

Reports:

```text
reports/orchestration_simulation/<run_id>/events.jsonl
reports/orchestration_simulation/<run_id>/summary.csv
reports/orchestration_simulation/<run_id>/run_summary.json
```

Erst der finale Fabrikstatus mit passender `simulation_run_id` setzt
`completed=true`. Ein Reset schliesst einen offenen Report mit
`stop_reason=reset` und beginnt den naechsten Lauf in einem neuen Ordner.

Flowupdate:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
```
