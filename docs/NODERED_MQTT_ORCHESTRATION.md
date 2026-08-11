# Node-RED-/MQTT-Orchestrierung

## Zielarchitektur

Die drei NN-Container sind zustandslose MQTT-Inferenzdienste. Node-RED
uebernimmt im virtuellen System Featureaufbereitung, Storage-One-hot-Encoding,
LSTM-Windowing, Reporting und Semaphorlogik. Im physischen System bleibt die
Node-RED-/OPC-UA-/SPS-Implementierung eine externe Black Box.

Aktive Container virtuell:

- `mosquitto`
- `node_red`
- `storage_infer`
- `vgr_infer`
- `hbw_infer`

Physisch laufen aus diesem Repository nur die drei NN-Dienste.

## MQTT-Vertraege

| Zweck | Topic |
|---|---|
| Anlagenzustand | `log/logging/state` |
| Storage Request/Response | `ft/nn/storage/request`, `ft/nn/response/storage` |
| VGR Request/Response | `ft/nn/vgr/request`, `ft/nn/response/vgr` |
| HBW Request/Response | `ft/nn/hbw/request`, `ft/nn/response/hbw` |
| Contracts | `ft/nn/<domain>/contract` |
| Status | `ft/nn/<domain>/status` |
| Orchestrierungsstatus | `ft/ai/orchestration/status` |
| Zyklusergebnis | `ft/ai/orchestration/cycle_result` |
| Fabriksteuerung | `ft/sim/factory/control` |
| Fabrikstatus | `ft/sim/factory/status` |

VGR und HBW publizieren bei freigegebenem Command-Output ihre leeren
Maschinencommands direkt auf den bestehenden `ai/<domain>/cmd<code>`-Topics.
MPO und SLD erhalten Idle-Commands vom KI-Flow. Commands verwenden QoS 2 und
`retain=false`.

## Zyklus

1. Der KI-Flow validiert den 28-Feld-Rohzustand.
2. Storage wird einmal abgefragt und liefert `empty_storage=0..9`.
3. Node-RED erzeugt `empty_storage_0..9` und aktualisiert beide Rolling Windows.
4. Bei neuer `source_id` werden neun versionierte Idle-Zeilen vorangestellt.
5. VGR- und HBW-Requests werden parallel gesendet.
6. VGR/HBW publizieren ihre Commands unabhaengig; der KI-Flow publiziert MPO/SLD.
7. Die vier Module laufen unabhaengig.
8. Erst wenn je Modul `sent_count == accepted_count` gilt, wird der naechste
   Anlagenzustand freigegeben.
9. VGR-/HBW-Responses werden fuer Reports korreliert. Diese Korrelation ist
   keine Command-Barriere.

Bei vollem Lager bleibt `empty_storage_0=1` ein normaler LSTM-Eingang. Die
aktuellen Guard-Modelle liefern in den beiden versionierten Vollspeicherprofilen
durchgehend `cmd=0`.

## Virtuelle Fabrik

Der Fabrik-Flow laedt eines von drei Profilen:

- `standard`: 320 Zustaende;
- `full-storage-attempt`: stationaere Ueberfuellversuche;
- `full-storage-process-guard`: prozessartige Ueberfuellversuche.

Jedes Modul besitzt eine Basiszeit. Pro Command wird daraus mit dem durch
`FACTORY_SEED` reproduzierbaren Faktor `0,5..1,5` eine Laufzeit erzeugt.
Standard sind 100 ms pro Modul.

## FlowFuse Dashboard

Das Dashboard liegt unter `/dashboard/betrieb` und steuert ausschliesslich den
virtuellen Fabrik-Control-Topic. Es zeigt Betriebszustand, Fortschritt,
Vorhersagen, Konfidenzen, Modulcounter und Fehler. Einstellbar sind Trace,
Seed und vier Modulbasiszeiten. Broker, Modelle und physische Freigabe bleiben
bewusst ausserhalb des HMI.

Das Paket `@flowfuse/node-red-dashboard` ist exakt gepinnt und image-lokal
installiert. `settings.js` registriert das explizite `nodesDir`, sodass ein
persistentes `/data`-Volume das Paket nicht verdeckt.

## Flowstruktur

Die Flows verwenden Core-Nodes fuer MQTT, `change`, `switch`, `split`, JSON
und Dateien. Drei begrenzte Function-Nodes bleiben als Adapter erhalten:

- Orchestrierungsereignis an `lib/orchestration.js` uebergeben;
- konsistenten Reportzustand mit `lib/reporting.js` erzeugen;
- Fabrikereignis an `lib/virtual_factory.js` uebergeben.

Zustandsautomaten, PRNG, Requestkorrelation und Vier-Modul-Barriere bleiben
zusammenhaengend in getesteten JS-Modulen. Eine Zerlegung auf unverbundene
`delay`-/`join`-Nodes wuerde Reset und Reproduzierbarkeit veraendern.

## Fehlerverhalten

Ungueltiger Payload, Timeout, Modellfehler, unbekannte Klasse oder
Publish-Fehler fuehren zu `fault_latched`. Fehlende Commands werden nicht durch
Idle ersetzt. Weitere Zustaende bleiben bis zum manuellen Reset blockiert.

## Persistenz Und Reports

Flows, Settings, Topics, Seeds und Traces sind versioniert. Docker-Volumes
persistieren Node-RED- und Mosquitto-Daten. Rolling Windows, offene Requests
und Timer werden nach Neustart bewusst neu initialisiert.

Reports:

```text
reports/orchestration_simulation/<run_id>/events.jsonl
reports/orchestration_simulation/<run_id>/summary.csv
reports/orchestration_simulation/<run_id>/run_summary.json
```

Ein einzelner KI-Zyklus aktualisiert die Run-Summary mit `completed=false`.
Erst der retained Fabrikstatus `completed` mit passender `simulation_run_id`
schliesst den Gesamtlauf ab und ergaenzt die finalen Modulzaehler. Ein Reset
schliesst einen offenen Report als gestoppt und trennt den folgenden Lauf in
einen neuen Reportordner.

Flowupdates erfolgen kontrolliert:

```bash
./tools/manage_nodered_runtime_backup.sh backup ./backup
./tools/run_nodered_orchestration.sh flow-update
```

Die importierbare KI-Referenz wird mit
`python3 tools/export_nodered_ai_flow.py --check` gegen den Gesamtflow geprueft.
