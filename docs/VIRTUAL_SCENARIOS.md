# Virtuelle Testszenarien

## Zweck

Die drei versionierten Szenarien pruefen denselben MQTT-/Node-RED-Ablauf mit
unterschiedlichen Anlagenzustaenden. Ein Lauf verwendet genau ein Szenario und
ein Modellprofil. Szenario- und Modellwechsel waehrend eines laufenden Zyklus
werden nicht uebernommen.

## Modellprofile

| Profil | Bedeutung |
|---|---|
| `deployment-current` | Aktueller Storage-, VGR- und HBW-Modellstand; Standard |
| `historical-full-storage-error` | Historisches VGR-/HBW-Modellpaar zur reproduzierbaren Fehlerdemonstration; Storage bleibt unveraendert |

Das historische Profil ist kein Sicherheitsvergleich im laufenden Betrieb,
sondern ein bewusst bereitgestellter Testfall. Dashboard und Reports zeigen
Profil-ID sowie die tatsaechlich verwendeten Modell-IDs.

## Normalbetrieb

Interne ID: `standard`

- 320 Anlagenzustaende
- Einlagerungen und Idle-Phasen
- vollstaendiger MQTT-, Inferenz-, Command- und Semaphorablauf
- Referenz fuer technische Vollstaendigkeit und stabile Modellvorhersagen

Erwartung fuer beide Modellprofile:

- 320 Storage-, VGR- und HBW-Ergebnisse
- vier Commands je regularem Zustand plus vier Initialcommands
- keine Timeouts, Faults oder unausgeglichenen Modulzaehler

## Wiederholter Einlagerungsversuch Bei Vollem Lager

Interne ID: `full-storage-attempt`

- 157 Anlagenzustaende insgesamt
- Lager wird einmal vollstaendig belegt
- danach 20 identische Einlagerungsversuche bei vollem Lager
- Lichtschranke bleibt waehrend der kritischen Zustaende ausgeloest

Erwartung mit `deployment-current`:

- 20 von 20 kritischen VGR-Ergebnissen sind Idle (`cmd=0`)
- 20 von 20 kritischen HBW-Ergebnissen sind Idle (`cmd=0`)

Erwartung mit `historical-full-storage-error`:

- erster Versuch bleibt Idle
- ab der zweiten Wiederholung erzeugt VGR den bekannten aktiven Befehl
- 19 von 20 kritischen VGR-Zustaenden reproduzieren den Fehler

Damit laesst sich die Wirkung des Vollspeicherschutzes unmittelbar zwischen
aktuellem und historischem Modellstand vergleichen.

## Prozesssequenzen Bei Vollem Lager

Interne ID: `full-storage-process-guard`

- 308 Anlagenzustaende insgesamt
- neun vollstaendige Prozesssequenzen
- 171 kritische Zustaende bei vollem Lager
- prozessartige Sensormuster statt nur eines wiederholten Einzelzustands

Erwartung mit `deployment-current`:

- 171 von 171 kritischen VGR-Ergebnissen sind Idle
- 171 von 171 kritischen HBW-Ergebnissen sind Idle

Erwartung mit `historical-full-storage-error`:

- mindestens ein aktiver VGR- oder HBW-Befehl bei vollem Lager
- der dokumentierte Modellfehler wird auch im Prozessverlauf sichtbar

## Auswahl Im Dashboard

Unter <http://localhost:1880/dashboard/betrieb> lassen sich vor dem Start
einstellen:

- Testszenario
- Modellprofil
- Zufalls-Seed
- Basiszeit fuer VGR, HBW, MPO und SLD

Die Basiszeit betraegt standardmaessig 100 ms. Je Command wird sie
reproduzierbar um minus 50 bis plus 50 Prozent variiert. Das Dashboard zeigt
Fortschritt, Vorhersagen, Latenzen, Modulzaehler, Semaphorstatus und Fehler.

## Auswertung

Fuer die fachliche Bewertung sind vor allem relevant:

- `model_profile` und `model_id`: tatsaechlich verwendeter Modellstand
- `trace_profile`: stabile interne Szenario-ID
- `predicted_class`: vorhergesagte Klasse
- `command_topic`: daraus resultierender Command
- `sent_count` und `accepted_count`: Semaphorstatus je Modul
- `completed`, `faults` und `timeouts`: technische Laufqualitaet

`run_summary.json.completed=true` gilt erst nach dem finalen, zum Lauf
passenden Fabrikstatus. Ein einzelner abgeschlossener KI-Zyklus beendet den
Gesamtlauf nicht.

Direktstart eines beliebigen Vergleichslaufs:

```bash
./tools/run_nodered_orchestration.sh virtual-run --images \
  --trace-profile <szenario-id> \
  --model-profile <modellprofil-id>
```
