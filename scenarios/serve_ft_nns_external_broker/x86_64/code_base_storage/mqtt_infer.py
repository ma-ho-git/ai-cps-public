"""MQTT-Inferenzservice fuer das Storage-NN.

Der Container nimmt neun binare Lagerbelegungssignale entgegen und gibt
`empty_storage` zurueck. Die Ausgabe wird bewusst ueber `class_ids`
gemappt, damit die Softmax-Position nicht mit dem fachlichen Slotwert
verwechselt wird.
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import paho.mqtt.client as mqtt
import tensorflow as tf


COMMON_DIR = Path(__file__).resolve().parents[1] / "code_base_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from mqtt_runtime import (  # noqa: E402
    build_model_contract,
    configure_last_will,
    publish_contract_and_status,
    response_payload,
)


MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_REQ_TOPIC = os.environ.get("MQTT_REQ_TOPIC", "ft/nn/storage/request")
MQTT_RES_TOPIC = os.environ.get("MQTT_RES_TOPIC", "ft/nn/response/storage")
MQTT_CONTRACT_TOPIC = os.environ.get("MQTT_CONTRACT_TOPIC", "ft/nn/storage/contract")
MQTT_STATUS_TOPIC = os.environ.get("MQTT_STATUS_TOPIC", "ft/nn/storage/status")
MQTT_QOS = int(os.environ.get("MQTT_QOS", "1"))

MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

KB_PATH = os.environ.get("KB_PATH", "/model_registry/storage/latest/model.keras")
AB_PATH = os.environ.get("AB_PATH", "/model_registry/storage/latest/activation.json")

MODEL = None
ACTIVATION = None
CONTRACT = None


def load_json(path: str):
    """Liest eine Activation- oder Konfigurationsdatei als JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def wait_for_files(paths: list[str], timeout_s: int = 180, interval_s: int = 1) -> None:
    """Wartet auf Modell- und Activation-Artefakte im gemounteten Registry-Pfad."""
    t0 = time.time()
    while True:
        missing = [path for path in paths if not os.path.exists(path)]
        if not missing:
            return
        if time.time() - t0 > timeout_s:
            raise FileNotFoundError(f"Timeout waiting for files: {missing}")
        print(f"[WAIT] missing: {missing} (sleep {interval_s}s)", flush=True)
        time.sleep(interval_s)


def ensure_loaded() -> None:
    """Laedt Modell und Activation genau einmal in den laufenden Container."""
    global MODEL, ACTIVATION
    if ACTIVATION is None:
        ACTIVATION = load_json(AB_PATH)
    if MODEL is None:
        MODEL = tf.keras.models.load_model(KB_PATH)


def class_ids_for_output(activation: dict, n_outputs: int) -> list[int]:
    """Ordnet Softmax-Ausgaenge den fachlichen `empty_storage`-Klassen zu."""
    class_ids = [int(class_id) for class_id in activation.get("class_ids", list(range(n_outputs)))]
    if len(class_ids) != n_outputs:
        raise ValueError(
            f"class_ids/output mismatch. class_ids has {len(class_ids)} entries, "
            f"model returned {n_outputs} outputs"
        )
    return class_ids


def extract_feature_vector(payload: dict, activation: dict) -> np.ndarray:
    """Extrahiert die neun Storage-Features in exakt der Activation-Reihenfolge."""
    feature_cols = list(activation["feature_cols"])
    raw_features = payload.get("features")

    if isinstance(raw_features, dict):
        missing = [col for col in feature_cols if col not in raw_features]
        if missing:
            raise ValueError(f"Storage features missing keys: {missing}")
        values = [raw_features[col] for col in feature_cols]
    elif isinstance(raw_features, list):
        values = raw_features
    else:
        missing = [col for col in feature_cols if col not in payload]
        if missing:
            raise ValueError(
                "Storage request must contain either a 'features' list/dict or "
                f"top-level feature keys. Missing: {missing}"
            )
        values = [payload[col] for col in feature_cols]

    x = np.asarray(values, dtype=np.float32)
    if x.shape != (len(feature_cols),):
        raise ValueError(f"Storage feature shape mismatch. Expected {(len(feature_cols),)}, got {x.shape}")
    if not np.isin(x, [0, 1]).all():
        # Die Storage-Truth-Table ist binaer; andere Werte waeren kein Sensorrauschen,
        # sondern ein Vertragsfehler im vorgelagerten MQTT-Zustand.
        raise ValueError("Storage features must be binary 0/1 values.")
    return x


def predict(payload: dict) -> tuple[int, list[dict]]:
    """Berechnet den ersten freien Slot und die Top-3-Diagnosewerte."""
    ensure_loaded()
    x = extract_feature_vector(payload, ACTIVATION)
    proba = MODEL.predict(x.reshape(1, -1), verbose=0)[0]
    class_ids = class_ids_for_output(ACTIVATION, len(proba))
    y_idx = int(np.argmax(proba))
    y_hat = int(class_ids[y_idx])

    top_idx = np.argsort(proba)[-3:][::-1]
    top3 = [
        {
            "empty_storage": int(class_ids[idx]),
            "name": ACTIVATION.get("cmd_map", {}).get(str(class_ids[idx]), f"empty_storage_{class_ids[idx]}"),
            "p": float(proba[idx]),
        }
        for idx in top_idx
    ]
    return y_hat, top3


def on_connect(client, userdata, connect_flags, reason_code, properties):
    """Publiziert den retained Modellvertrag und abonniert Storage-Requests."""
    print(f"[MQTT] connected reason={reason_code}, subscribing to {MQTT_REQ_TOPIC}", flush=True)
    publish_contract_and_status(
        client,
        contract_topic=MQTT_CONTRACT_TOPIC,
        status_topic=MQTT_STATUS_TOPIC,
        contract=CONTRACT,
        qos=MQTT_QOS,
    )
    client.subscribe(MQTT_REQ_TOPIC, qos=MQTT_QOS)


def on_message(client, userdata, msg):
    """Verarbeitet genau eine Storage-Anfrage und publiziert Ergebnis oder Fehler."""
    req = {}
    try:
        req = json.loads(msg.payload.decode("utf-8"))
        empty_storage, top3 = predict(req)
        res = response_payload(
            req,
            model_id=CONTRACT["model_id"],
            empty_storage=empty_storage,
            top3=top3,
        )
        client.publish(MQTT_RES_TOPIC, json.dumps(res), qos=MQTT_QOS, retain=False)
        print(f"[MQTT] request_id={req.get('request_id', '')} -> empty_storage={empty_storage}", flush=True)
    except Exception as exc:
        err = response_payload(req, model_id=CONTRACT["model_id"], error=str(exc))
        client.publish(MQTT_RES_TOPIC, json.dumps(err), qos=MQTT_QOS, retain=False)
        print("[ERR]", repr(exc), flush=True)


def main() -> None:
    """Startet den Storage-Inferenzcontainer als dauerhaften MQTT-Client."""
    global CONTRACT
    print(f"[INIT] waiting for KB={KB_PATH} and AB={AB_PATH}", flush=True)
    wait_for_files([KB_PATH, AB_PATH], timeout_s=180, interval_s=1)
    ensure_loaded()
    CONTRACT = build_model_contract(
        domain="storage",
        activation=ACTIVATION,
        model_path=KB_PATH,
        request_topic=MQTT_REQ_TOPIC,
        response_topic=MQTT_RES_TOPIC,
    )
    print("[INIT] storage model+activation loaded OK", flush=True)
    print(f"[INIT] broker={MQTT_HOST}:{MQTT_PORT} req={MQTT_REQ_TOPIC} res={MQTT_RES_TOPIC}", flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    configure_last_will(client, status_topic=MQTT_STATUS_TOPIC, domain="storage", qos=MQTT_QOS)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
