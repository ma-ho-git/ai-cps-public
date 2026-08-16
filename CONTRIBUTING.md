# Contributing

Beitraege sind ueber Issues und Pull Requests in `ma-ho-git/ai-cps-public`
willkommen.

## Vor Einer Aenderung

1. `AGENTS.md` und `docs/AI_DEVELOPMENT_HANDOVER.md` lesen.
2. MQTT-Topics, Payloads, QoS, Feature-Reihenfolge, Modellklassen,
   Modellprofile und Semaphorverhalten nur mit ausdruecklicher
   Vertragsmigration aendern.
3. Keine `.env`, Credentials, Reports, Docker-Volumes oder lokalen
   Modellkandidaten committen.
4. Passende Tests und die massgebliche Dokumentation aktualisieren.

## Lizenz Und Fremdmaterial

Mit einem Beitrag wird bestaetigt, dass er unter `AGPL-3.0-only` verteilt
werden darf. Bestehende Copyright-, Lizenz- und Attributionshinweise bleiben
erhalten. Kopiertes oder angepasstes Fremdmaterial muss im Pull Request
benannt und vor dem Merge korrekt gekennzeichnet werden.

Commits sollen einen Developer-Certificate-of-Origin-Sign-off enthalten:

```bash
git commit --signoff
```

Der Sign-off bestaetigt den Developer Certificate of Origin 1.1:
<https://developercertificate.org/>.

## Mindestpruefung

- Python: relevante Unit-Tests und `py_compile`
- Node-RED/MQTT: JavaScript-Tests, Flowexport und Compose-Validierung
- Lesbarkeit: `python tools/check_code_readability.py`
- Runtime: Standardtrace und betroffene Vollspeicherszenarien
- Dokumentation: lokale Links und `git diff --check`

Produktionsfunktionen bleiben auf 60 Zeilen begrenzt; Callbacks, `main()` und
Tests auf 40 Zeilen. Node-RED-Prozessentscheidungen sollen mit sichtbaren
Core-Nodes umgesetzt werden. Die vier dokumentierten Function-Ausnahmen und
JSONata-Ausdruecke bis 200 Zeichen werden automatisch geprueft.
