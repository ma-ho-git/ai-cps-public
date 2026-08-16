# Security Policy

## Unterstuetzte Version

Unterstuetzt wird der neueste Tag der Reihe `runtime-v1.*`.

## Schwachstelle Melden

GitHubs private Vulnerability-Reporting-Funktion oder ein privates Security
Advisory in `ma-ho-git/ai-cps-public` verwenden. Zugangsdaten, interne
Adressen oder ausnutzbare Details nicht in einem oeffentlichen Issue nennen.

## Einsatzgrenze

Die Software ist eine virtuelle Testumgebung und keine zertifizierte
Sicherheitssteuerung. Node-RED und Mosquitto nur in einem lokalen oder
vertrauenswuerdigen Netz bereitstellen. Eine oeffentliche Freigabe des
Dashboards oder MQTT-Ports benoetigt Authentifizierung, Transportverschluesselung
und eine eigene Sicherheitspruefung.

Standortbundles enthalten `.env` und das lokale Node-RED-Secret im Klartext.
Sie besitzen Dateimodus `0600`, muessen aber vor einer Weitergabe ausserhalb
der abgeschotteten Testumgebung zusaetzlich verschluesselt werden.
