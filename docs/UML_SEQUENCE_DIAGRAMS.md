# UML-Sequenzdiagramme Der MQTT-/Node-RED-Orchestrierung

Stand: 2026-07-27

## Zweck

Die beiden Diagramme dokumentieren den zeitlichen Nachrichtenfluss des
aktuellen Projekts:

- [Virtuelle Simulation](assets/uml/nodered_mqtt_virtual_sequence.svg)
- [PlantUML-Quelle der virtuellen Simulation](assets/uml/nodered_mqtt_virtual_sequence.puml)
- [Editierbare draw.io-Quelle der virtuellen Simulation](assets/uml/nodered_mqtt_virtual_sequence.drawio)
- [Physischer Live-Betrieb](assets/uml/nodered_mqtt_physical_sequence.svg)
- [PlantUML-Quelle des physischen Live-Betriebs](assets/uml/nodered_mqtt_physical_sequence.puml)
- [Editierbare draw.io-Quelle des physischen Live-Betriebs](assets/uml/nodered_mqtt_physical_sequence.drawio)

Sie zeigen denselben KI-Zyklus mit Storage-, VGR- und HBW-Inferenz. Der
Unterschied liegt an der Fabrikgrenze: Im virtuellen Modus emuliert Node-RED
vier Module und deren Laufzeiten; im physischen Modus bleiben der konkrete
Node-RED-/OPC-UA-Flow und die SPS eine Black Box.

## Analyse Der Grum-Vorlage

Als konkrete Darstellungsreferenz wurde Abbildung 9 aus Grum (2024)
ausgewertet. Die zugehoerige lokale Forschungsquelle liegt im archivierten
Entwicklungsstand. Die Abbildung beschreibt den Kommunikationsfluss eines gemeinsam
virtuell und physisch ausgefuehrten Simulationssystems.

Die Vorlage verwendet ein hohes fachliches Abstraktionsniveau:

- Lifelines stehen fuer Systemrollen und CPS-Instanzen, nicht fuer
  Softwareklassen, Container oder Kommunikationsmiddleware.
- Horizontale Klammern ordnen Teilnehmer hierarchisch dem Gesamtsystem sowie
  dem virtuellen und physischen Teilsystem zu.
- Aktivierungsbalken zeigen, wann eine Rolle eine Funktion ausfuehrt oder auf
  ein Ergebnis wartet.
- Nachrichten werden nur beschriftet, wenn ihr fachlicher Informationsgehalt
  fuer das Verstaendnis wichtig ist.
- Die sichtbaren Informationsobjekte sind Steuerungsimpulse,
  Analyseanforderungen, Analyseergebnisse und Systemaktivierungen.
- Broker, Topics, Payloadschemata, IDs, Protokollparameter und interne
  Verarbeitungsschritte bleiben ausserhalb der Abbildung.
- Wiederholung und technische Fehlerbehandlung werden nicht im Detail
  dargestellt; die Abbildung konzentriert sich auf einen repraesentativen
  Kommunikationsdurchlauf.

Die Informationsdichte ist damit niedrig bis mittel: Die Abbildung erklaert
Systemkopplung und Aktivierungsfolge, nicht die Implementierung. Dieses Prinzip
wird fuer die neuen Projektabbildungen uebernommen. Zusaetzlich bleiben
`loop` und `par` erhalten, weil Wiederholung und parallele VGR-/HBW-Inferenz
fachlich zentrale Eigenschaften dieses Projekts sind. Die Unterscheidung
zwischen synchronen und asynchronen Nachrichten wird ebenfalls beibehalten,
obwohl sie in der Grum-Abbildung nicht explizit differenziert wird.

## Wissenschaftliche Einordnung

Die gewaehlte Abstraktion orientiert sich an folgenden Quellen:

- Die UML-2.5.1-Spezifikation definiert Interaktionen ueber Lifelines,
  Nachrichten und kombinierte Fragmente. Dadurch lassen sich Reihenfolge,
  Parallelitaet und Wiederholung getrennt von der Implementierung darstellen
  ([OMG UML 2.5.1](https://www.omg.org/spec/UML/2.5.1/)).
- In einer Virtual-Commissioning-Methodik fuer Fertigungssysteme werden
  Sequenzdiagramme verwendet, um die chronologische Folge ausgetauschter
  Signale, Operationen und beteiligter Akteure vor der physischen Umsetzung
  festzulegen
  ([Bortolini et al., 2021](https://doi.org/10.1007/s11740-021-01037-3)).
- UML-basierte Digital-Twin-Forschung betont ein angemessenes und effizientes
  Abstraktionsniveau fuer komplexe Fertigungssysteme
  ([Azangoo et al., 2020](https://doi.org/10.1109/ETFA46521.2020.9212165)).
- Modulare CPPS-Architekturen behandeln MQTT und OPC UA als standardisierte
  Schnittstellen zwischen lose gekoppelten Systemrollen. Das stuetzt eine
  Darstellung von Rollen und Nachrichten statt einzelner Implementierungsnodes
  ([Goeppert et al., 2023](https://doi.org/10.3389/fmech.2023.1113933)).

MQTT wird als asynchroner Publish-/Subscribe-Austausch modelliert. Dies folgt
dem entkoppelten Client-Server-Publish-/Subscribe-Vertrag der
[OASIS-MQTT-Spezifikation](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html).
OPC-UA-Write-Aufrufe werden als synchrone Request-/Response-Interaktion,
Abschlussmeldungen als asynchrone Notifications dargestellt. Diese Trennung
entspricht den
[OPC-UA-Servicekonzepten](https://reference.opcfoundation.org/specs/OPC-10000-1/5.3.6).

## Gewaehltes Abstraktionsniveau

Die Diagramme zeigen:

- sechs logische Rollen im virtuellen und sieben im physischen Betrieb,
- hierarchische Systemklammern analog zur Grum-Vorlage,
- Aktivierungsbalken fuer Orchestrierung, NN-Inferenz und Fabrikausfuehrung,
- semantische Nachrichten statt konkreter MQTT-Topics,
- die kausale Folge Anlagenzustand -> Storage -> Fensteraufbereitung ->
  VGR/HBW -> direkte Commands -> Modulabschluesse,
- parallele VGR-/HBW-Inferenz mit einem `par`-Fragment,
- den wiederholten Anlagenzyklus mit einem `loop`-Fragment,
- die physische Semaphorgrenze beziehungsweise die virtuelle Vier-Modul-
  Barriere.

Im virtuellen Diagramm bezeichnet `:Startskript` die hostseitige Bedienrolle
von `tools/run_nodered_orchestration.sh`. Sie ist weder ein Container noch
Bestandteil von Node-RED und veröffentlicht nur die einmalige MQTT-
Startnachricht. `:Fabrik-Flow` und `:KI-Flow` sind dagegen als getrennte
Lifelines innerhalb der gemeinsamen Systemgruppe `Node-RED` dargestellt.
Beide Rollen sind eigenständige Flow-Tabs derselben Node-RED-Instanz. Die
Trennung der Lifelines macht ihre unterschiedlichen Verantwortungen und den
MQTT-Austausch sichtbar, ohne einzelne Node-RED-Bausteine abzubilden.

Im physischen Diagramm stehen `:Command-Flows`, `:Semaphor-Flow` und
`:KI-Flow` fuer drei logische Node-RED-Verantwortungen. Die Command-Flows
uebersetzen unabhaengige MQTT-Commands in OPC-UA-Aufrufe. Der Semaphor-Flow
vergleicht gesendete und abgearbeitete Jobcounter und gibt erst danach den
naechsten Zustand frei. Diese Bezeichnungen sind keine bestaetigten Namen
physischer Flow-Tabs. Nur der KI-Flow liegt in diesem Repository als
Referenzartefakt vor; die konkrete physische Node-RED- und SPS-Struktur bleibt
eine Black Box.

Die PlantUML-Dateien sind editierbare, semantisch entsprechende
Begleitquellen fuer den
[offiziellen PlantUML-Editor](https://editor.plantuml.com/uml/). Die finalen
SVGs sind versionierte Darstellungen; die historischen Python-Generatoren
liegen im archivierten Entwicklungsstand.

Die draw.io-Dateien bilden die Sequenzmodelle als unkomprimierte
`mxGraphModel`-Dokumente ab. Teilnehmer, Lifelines, Aktivierungsbalken,
Nachrichten, Fragmente und Legenden sind native, einzeln editierbare
draw.io-Elemente. Sie koennen direkt mit
[draw.io/diagrams.net](https://app.diagrams.net/) geoeffnet werden und
enthalten kein eingebettetes SVG oder Rasterbild.

Der MQTT-Broker wird wie die Message Broker in Grums textlicher
Systembeschreibung als Kommunikationsinfrastruktur behandelt und deshalb
nicht als eigene Lifeline gezeigt. Die Pfeilbeschriftung weist MQTT weiterhin
aus. Bewusst nicht enthalten sind konkrete Topics, QoS/Retain, 28 Rohfelder,
29 Modellfeatures, Request-IDs, Modellstatus, Top-3-Wahrscheinlichkeiten,
Containerstart, Reportdateien und der detaillierte Fehlerpfad. Diese
Informationen stehen in der
[Architekturdokumentation](NODERED_MQTT_ORCHESTRATION.md).

Die semantischen Nachrichten entsprechen weiterhin dem unveraenderten
technischen Vertrag:

| Semantische Nachricht | Technische Schnittstelle |
| --- | --- |
| Anlagenzustand | `log/logging/state` |
| Storage-Anfrage/-Ergebnis | `ft/nn/storage/request` und `ft/nn/response/storage` |
| VGR-Anfrage/-Ergebnis | `ft/nn/vgr/request` und `ft/nn/response/vgr` |
| HBW-Anfrage/-Ergebnis | `ft/nn/hbw/request` und `ft/nn/response/hbw` |
| Direkte VGR-/HBW-Commands | bestehende `ai/vgr/cmd*`- und `ai/hbw/cmd*`-Topics |
| MPO-/SLD-Idle | `ai/mpo/cmd0` und `ai/sld/cmd0` |
| Modulabschluss | physisch OPC UA, virtuell interner Fabrikzustand |

## Notation

| Darstellung | Bedeutung |
| --- | --- |
| Horizontale Klammer | Zugehoerigkeit zu Gesamt- oder Teilsystem |
| Grauer Aktivierungsbalken | Rolle verarbeitet eine Nachricht oder wartet innerhalb eines Zyklus |
| Durchgezogene Linie mit offener Pfeilspitze | asynchrone MQTT-Nachricht oder OPC-UA-Notification |
| Durchgezogene Linie mit gefuellter Pfeilspitze | synchroner lokaler Aufruf oder OPC-UA-Request |
| Gestrichelte Linie mit offener Pfeilspitze | Rueckgabe eines synchronen Aufrufs |
| `par` | VGR- und HBW-Verarbeitung laufen unabhaengig parallel |
| `loop` | Regelkreis bis Trace-Ende beziehungsweise Anlagenstopp |

Die Begriffe Request und Response in MQTT-Topics beschreiben den fachlichen
Zusammenhang. Beide bleiben technisch asynchrone MQTT-Publishes und werden
deshalb mit offenen Pfeilspitzen dargestellt.

## Beschreibung Für Den Thesistext

In Anlehnung an den von Grum (2024) verwendeten Darstellungsansatz
konzentrieren sich die Sequenzdiagramme auf die beteiligten Systemrollen, die
zwischen ihnen ausgetauschten Informationsobjekte und die zeitliche
Koordination des Gesamtsystems. Einzelne Node-RED-Bausteine, der
MQTT-Broker, konkrete Topicnamen und interne Datenstrukturen werden bewusst
nicht als eigene Lifelines dargestellt. Diese Elemente sind für die
technische Realisierung erforderlich, würden jedoch die für die Abbildungen
maßgebliche Sicht auf den Regelkreis überladen. Die offenen Pfeilspitzen
kennzeichnen asynchron übertragene MQTT-Nachrichten beziehungsweise
OPC-UA-Notifications. Gefüllte Pfeilspitzen stehen für synchrone Aufrufe;
gestrichelte Pfeile kennzeichnen deren Rückgaben. Die Fragmente `loop` und
`par` machen zusätzlich die zyklische Ausführung und die parallel
ausgeführten Inferenzschritte sichtbar.

### Virtuelle Simulation

Das Sequenzdiagramm der virtuellen Simulation zeigt die Kommunikation
zwischen dem hostseitigen Startskript, zwei logischen Node-RED-Flows und den
drei NN-Anwendungsdiensten. Das Startskript bereitet den Compose-Stack vor,
wartet auf die Betriebsbereitschaft der KI-Orchestrierung und veröffentlicht
anschließend genau einmal den Startbefehl über MQTT. Es ist kein eigener
Container und greift nach dieser Initialzündung nicht mehr steuernd in den
Regelkreis ein. Der Fabrik-Flow bildet das Verhalten der physischen Anlage
nach, während der KI-Flow die Aufbereitung der Modelleingaben, die
Ausgabe der MPO-/SLD-Idle-Commands, die Reportkorrelation und die
Fehlerverriegelung übernimmt. Storage-NN, VGR-NN und HBW-NN sind als getrennte
Anwendungsdienste dargestellt. Diese Trennung verdeutlicht, dass die Modelle
über MQTT lose gekoppelt sind und ausgetauscht werden können, solange sie
ihren jeweiligen Modell- und Nachrichtenvertrag einhalten.

Auf die einmalige Startnachricht veröffentlicht der Fabrik-Flow zunächst ein
vollständiges Idle-Command-Set für VGR, HBW, MPO und SLD. Dabei handelt es
sich um vier reguläre MQTT-Command-Nachrichten. Der Fabrik-Flow simuliert
deren Modulzeiten und gibt erst nach der Vier-Modul-Semaphorbarriere den
ersten Trace-Zustand frei. Damit lautet die Startfolge:
`Startnachricht -> Idle-Command-Set -> Modulbarriere -> erster
Idle-Trace-Zustand`. Der erste Idle-Zustand ist folglich keine zusätzliche
Startnachricht, sondern die erste reguläre Anlagenzustandsmeldung des
versionierten 320-Zustände-Traces. Alle folgenden Zustände verwenden
denselben Nachrichtentyp und werden ebenfalls erst nach vier
Modulabschlüssen veröffentlicht.

Nach dem Empfang eines Zustands fragt der KI-Flow zunächst das Storage-NN ab.
Dessen Vorhersage bestimmt das freie Lagerfach und wird im KI-Flow in die
One-hot-Darstellung `empty_storage_0..9` überführt. Die Storage-Inferenz ist
den beiden LSTM-Inferenzen vorgeschaltet, weil ihr Ergebnis Bestandteil der
Eingabesequenzen von VGR und HBW ist.

Für eine LSTM-Vorhersage wird ein vollständiges Fenster aus zehn
Zeitschritten benötigt. Beim erstmaligen Auftreten einer Quelle stehen noch
keine historischen Zustände zur Verfügung. Der KI-Flow stellt deshalb neun
versionierte Idle-Einträge voran und fügt den ersten empfangenen Zustand als
zehnten Eintrag hinzu. Dieses Bootstrap-Verfahren ermöglicht bereits für den
ersten real empfangenen Zustand eine VGR- und HBW-Inferenz. Die künstlich
ergänzten Einträge entstehen ausschließlich intern im KI-Flow. Sie sind keine
MQTT-Nachrichten, dienen nur der Initialisierung des Merkmalsfensters und
lösen selbst keine Steuerungsbefehle aus.

Nach der Fensterbildung werden die Anfragen an VGR-NN und HBW-NN
asynchron veröffentlicht. Das `par`-Fragment zeigt, dass beide Modelle
unabhängig voneinander inferieren und ihre vorhergesagten Commands unmittelbar
auf den jeweiligen MQTT-Command-Topics veröffentlichen. VGR und HBW warten
dabei nicht auf das Ergebnis des jeweils anderen Modells. Der KI-Flow
veröffentlicht bereits nach der Storage-Verarbeitung die Idle-Commands für
MPO und SLD. Damit treffen alle vier Modulcommands unabhängig beim
Fabrik-Flow ein.

Zusätzlich publizieren VGR und HBW weiterhin eine JSON-Response mit
Vorhersage, Modellkennung und Korrelationsfeldern. Der KI-Flow ordnet diese
Responses anhand von Zyklus- und Request-ID dem auslösenden Anlagenzustand zu
und erzeugt daraus den gemeinsamen Reportdatensatz. Diese Zusammenführung
erfolgt ausschließlich zur Beobachtung und fachlichen Auswertung. Sie ist
weder eine Command-Barriere noch Bestandteil des Semaphors.

Der Fabrik-Flow ersetzt im virtuellen Betrieb die Ausführung durch SPS und
Anlagenmodule. Jeder eintreffende Command erhöht den `sent_count` seines
Moduls und startet eine reproduzierbare, unabhängig bestimmte
Bearbeitungszeit. Ihre modulbezogene Basiszeit betraegt standardmaessig
0,1 Sekunden und wird pro Command reproduzierbar um -50 bis +50 Prozent
variiert. Nach Ablauf erhöht der
Fabrik-Flow den zugehörigen `accepted_count`. Erst wenn für VGR, HBW, MPO und
SLD jeweils `sent_count == accepted_count` gilt, ist der Semaphor frei und der
nächste Anlagenzustand wird veröffentlicht. Dadurch entsteht aus einer
einzigen Initialnachricht ein selbstständig fortlaufender Regelkreis. Die
virtuelle Umgebung prüft somit nicht nur einzelne Modellvorhersagen, sondern
auch unabhängige Command-Pfade und die nachgelagerte Synchronisation der
vollständigen Steuerungskette.

### Physischer Live-Betrieb

Das Sequenzdiagramm des physischen Live-Betriebs verwendet auf der
KI-Seite denselben Ablauf. Die Rollen `Command-Flows`, `Semaphor-Flow` und
`KI-Flow` bezeichnen logische Verantwortungsbereiche innerhalb der externen
Node-RED-Umgebung. Sie sind keine Aussage über konkrete Namen oder den
internen Aufbau physischer Flow-Tabs. Sowohl die SPS-/Modulseite als auch
deren Node-RED-/OPC-UA-Integration werden im Softwareprojekt weiterhin als
Black Box behandelt. Dokumentiert und geprüft werden der bestehende
MQTT-Grenzvertrag und die fachlich bekannte Jobcounter-Semantik.

Beim Systemstart veröffentlicht der Semaphor-Flow einmalig ein Idle-
Command-Set für alle vier Module. Die Command-Flows erhöhen dadurch die
gesendeten Jobcounter und rufen die zugehörigen SPS-Funktionsblöcke auf.
Nachdem die Module diese Startbefehle abgearbeitet haben, sind gesendete und
abgearbeitete Zähler initial ausgeglichen. Erst dann wird der erste
synchronisierte Anlagenzustand freigegeben.

Zu Beginn jedes regulären Anlagenzyklus veröffentlicht der Semaphor-Flow
einen synchronisierten Anlagenzustand an den KI-Flow. Die
Übertragung erfolgt asynchron über MQTT, auch wenn das Diagramm aus Gründen
der Übersichtlichkeit keine eigene Broker-Lifeline zeigt. Beim Anlagenstart
enthält die erste dieser regulären Zustandsmeldungen einen synchronisierten
Idle-Zustand. Dabei handelt es sich weder um eine zusätzliche Startnachricht
noch um einen eigenen Topic; für den initialen Zustand wird dieselbe
MQTT-Schnittstelle wie für alle Folgezustände verwendet.

Wie in der virtuellen Simulation wird zuerst das Storage-NN abgefragt.
Anschließend bildet der KI-Flow das vollständige Merkmalsfenster und sendet
die VGR- und HBW-Anfragen parallel. Von der ersten MQTT-Zustandsmeldung sind
die neun versionierten Idle-Seeds zu unterscheiden: Sie werden ausschließlich
intern im KI-Flow ergänzt, um das LSTM-Fenster für eine neue Quelle zu
initialisieren, und sind selbst keine MQTT-Nachrichten. VGR- und HBW-Dienst
veröffentlichen ihre vorhergesagten Commands anschließend jeweils direkt und
ohne gegenseitige Wartebedingung. Der KI-Flow ergänzt unabhängig davon die
Idle-Commands für MPO und SLD. Die zusätzlichen JSON-Responses der beiden
Modelle werden nur für Report und Diagnose zusammengeführt.

An der Grenze zur Anlage unterscheidet sich der Ablauf vom virtuellen
Regelkreis. Jeder Command-Flow erhöht beim Eingang eines Commands den
gesendeten Jobcounter des betroffenen Moduls und überträgt den Befehl über
einen synchron dargestellten OPC-UA-Aufruf an die SPS. Die gestrichelte
Rückgabe bestätigt die Annahme dieses Aufrufs, nicht jedoch den Abschluss der
mechanischen Bearbeitung. Die SPS-Funktionsblöcke werden nebenläufig
ausgeführt. Jedes Modul meldet seinen Abschluss unabhängig an Node-RED,
wodurch der jeweilige abgearbeitete Jobcounter erhöht wird.

Der Semaphor-Flow vergleicht anschließend für jedes der vier Module den
gesendeten mit dem abgearbeiteten Zähler. Nur wenn alle Paare übereinstimmen,
wird der nächste Anlagenzustand veröffentlicht. Die Synchronisation erfolgt
somit bewusst nach der unabhängigen Command-Ausgabe und der parallelen
Maschinenausführung. Weder die NN-Dienste noch die Reportkorrelation bilden
diese Barriere.

### Vergleichende Einordnung

Beide Diagramme besitzen bewusst dieselbe KI-seitige Verarbeitungskette:
Anlagenzustand, Storage-Inferenz, Fensterbildung, parallele VGR-/HBW-Inferenz
und unabhängige Ausgabe der vier Modulcommands. Der wesentliche Unterschied
liegt hinter der Fabrikgrenze. Im virtuellen System simuliert der Fabrik-Flow
Laufzeiten, Jobcounter und Modulabschlüsse, während diese Aufgaben im
physischen System von der externen Node-RED-/OPC-UA-/SPS-Black-Box ausgeführt
werden. Die virtuelle Umgebung bildet die physische Zwei-Sekunden-Abfrage
nicht nach, erhält aber die für den KI-Regelkreis maßgebliche Semantik:
Commands erhöhen gesendete Zähler, Abschlüsse erhöhen akzeptierte Zähler und
der nächste Zustand folgt erst bei vollständigem Ausgleich.

Die Übereinstimmung der KI-seitigen Schnittstellen ermöglicht, Modelle und
Orchestrierungsverhalten zunächst reproduzierbar in der virtuellen Umgebung
zu prüfen und anschließend ohne Änderung des Modellvertrags in den
physischen Betrieb zu übertragen. Zugleich verdeutlichen die Diagramme, dass
die zeitliche Ordnung nicht durch synchrone MQTT-Kommunikation entsteht.
MQTT bleibt ein asynchroner Publish-/Subscribe-Mechanismus; die notwendige
Kausalität wird durch Request-Korrelation, Zustandsverwaltung und die
nachgelagerte Jobcounter-Semaphorbarriere hergestellt.

## Abbildungsunterschriften Für Die Thesis

**Virtuelle Simulation:** UML-Sequenzdiagramm des virtuellen
MQTT-Regelkreises. Ein hostseitiges Startskript löst einmalig den Fabrik-Flow
aus; VGR und HBW publizieren ihre Commands direkt, während der Fabrik-Flow
unabhängige Modullaufzeiten und die nachgelagerte Jobcounter-Barriere
simuliert.

**Physischer Live-Betrieb:** UML-Sequenzdiagramm des physischen
MQTT-/OPC-UA-Regelkreises. VGR- und HBW-NN senden ihre Commands unabhängig an
die Command-Flows; erst der Semaphor-Flow synchronisiert die nebenläufigen
Modulabschlüsse über gesendete und abgearbeitete Jobcounter. Die konkrete
steuerungsnahe Umsetzung bleibt Bestandteil des als Black Box dargestellten
physischen Live-Systems.
