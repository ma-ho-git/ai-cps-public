# Training Und Modellfreigabe

## Trainingsbestand

| Domain | Aktiver Datensatz | Modell |
|---|---|---|
| Storage | vollstaendige 512-Zeilen-Truth-Table | MLP |
| VGR | balancierter Full-Storage-Guard-Datensatz | LSTM `(10,29)` |
| HBW | Full-Storage-Guard-Datensatz | LSTM `(10,29)` |

Die Original-VGR-/HBW-Datensaetze bleiben fuer Regressionstests erhalten.
Configs liegen unter `configs/`; Images unter `training/<domain>/`.

## Sicheres Kandidatentraining

```bash
docker compose -f docker-compose.train.yml build train_storage train_vgr train_hbw
docker compose -f docker-compose.train.yml run --rm train_storage
docker compose -f docker-compose.train.yml run --rm train_vgr
docker compose -f docker-compose.train.yml run --rm train_hbw
```

Alle aktiven Configs setzen `publish_latest=false`. Ein Lauf schreibt nur nach
`model_registry/<domain>/versions/<timestamp>/`. Der versionierte
Deployment-Default bleibt unveraendert.

## Artefaktvertrag

Jeder Kandidat besteht aus:

- `model.keras`
- `activation.json`
- `metrics.json`

`activation.json` definiert Domain, Feature-Reihenfolge, Inputform, Klassen und
Command-Mapping. Die drei Dateien werden immer gemeinsam getestet und bewegt.

## Pruefung

```bash
python3 tools/check_model_compatibility.py \
  --domain vgr --candidate-dir model_registry/vgr/versions/<timestamp> \
  --mode virtual
```

Original- und Guard-Daten auswerten:

```bash
python3 tools/evaluate_full_storage_guard_models.py \
  --domain vgr \
  --baseline-dir model_registry/vgr/latest \
  --candidate-dir model_registry/vgr/versions/<timestamp>
```

Danach Kandidat ueber `manage_model_candidates.py add/select` aktivieren und
drei virtuelle Laeufe durchfuehren:

1. `standard`: exakt gleiche Klassen und Command-Topics wie Baseline;
2. `full-storage-attempt`: alle 20 Versuche VGR/HBW `cmd=0`;
3. `full-storage-process-guard`: alle 171 Guard-Zustaende VGR/HBW `cmd=0`.

Zusaetzlich: keine Faults, Timeouts oder unausgeglichenen Modulcounter.

## Promotion Und Rollback

```bash
python3 tools/manage_model_candidates.py promote \
  --domain vgr --report-dir reports/orchestration_simulation/<run>
```

Promotion verlangt einen abgeschlossenen 320-Zustaende-Report mit passender
Modell-ID. Danach werden die drei neuen `latest`-Artefakte bewusst versioniert.

Vor Promotion oder bei Fehler:

```bash
python3 tools/manage_model_candidates.py rollback --domain vgr
```

Alternative Frameworks duerfen als MQTT-kompatibles Inferenzimage eingebunden
werden. Request-, Response-, Contract-, Status- und Command-Vertraege bleiben
dabei unveraendert.
