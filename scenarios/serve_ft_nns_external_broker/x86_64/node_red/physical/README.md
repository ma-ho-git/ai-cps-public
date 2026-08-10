# Physisches Live-System Als Black-Box

Der produktive Node-RED-/OPC-UA-/Semaphor-Aufbau und die SPS gehoeren zum
physischen Live-System. Ihr interner Aufbau ist bewusst kein Artefakt dieses
Repositories und wird hier weder exportiert, rekonstruiert noch installiert.

Dieses Softwareprojekt betrachtet ausschliesslich die MQTT-Systemgrenze. Das
physische Live-System muss denselben Vertrag wie die virtuelle Fabrik
erfuellen:

- Anlagenzustand: `log/logging/state`
- Storage: `ft/nn/storage/request` -> `ft/nn/response/storage`
- VGR: `ft/nn/vgr/request` -> `ft/nn/response/vgr`
- HBW: `ft/nn/hbw/request` -> `ft/nn/response/hbw`
- Commands: bestehende `ai/vgr/cmd*`, `ai/hbw/cmd*`, `ai/mpo/cmd0` und
  `ai/sld/cmd0`
- Command-Payload leer, QoS 2, `retain=false`

Der versionierte `flows_ai_orchestration.json` ist eine Referenz fuer die
virtuelle Simulation und den MQTT-Vertragsvergleich. Er ist kein
vollstaendiger Export des physischen Node-RED-Systems.

Die physische Abnahme erfolgt mit
`tools/monitor_physical_mqtt_contract.py` und
`tools/compare_physical_mqtt_contract_captures.py`. Damit werden Topic,
Payloadform, QoS und Retain-Flag verglichen, ohne die Black-Box zu oeffnen.
