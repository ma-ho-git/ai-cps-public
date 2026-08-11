"""MQTT-Inferenzservice fuer das PLC-nahe HBW-LSTM.

Der Container ersetzt den alten 7-Feature-HBW-Vertrag. Er erwartet ein
vollstaendiges Sequenzfenster mit 10 Zeitschritten. Die konkrete Featurezahl
kommt aus `activation.json`; aktuell sind es 29 Features, darunter die
SSC-Lichtschranke und `empty_storage_0..9`. Die Ausgabe wird ueber
`class_ids` auf echte HBW-Befehlswerte zurueckgemappt.
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
    ResponseCache,
    build_model_contract,
    command_output_contract,
    configure_last_will,
    env_flag,
    load_command_topic_map,
    publish_direct_command,
    publish_contract_and_status,
    response_payload,
)
from model_profiles import (  # noqa: E402
    DEFAULT_MODEL_PROFILE,
    load_profile_specs,
    profile_contract,
    select_profile,
)


SENDER = os.environ.get("SENDER", "testSender")

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_REQ_TOPIC = os.environ.get("MQTT_REQ_TOPIC", "ft/nn/hbw/request")
MQTT_RES_TOPIC = os.environ.get("MQTT_RES_TOPIC", "ft/nn/response/hbw")
MQTT_CONTRACT_TOPIC = os.environ.get("MQTT_CONTRACT_TOPIC", "ft/nn/hbw/contract")
MQTT_STATUS_TOPIC = os.environ.get("MQTT_STATUS_TOPIC", "ft/nn/hbw/status")
MQTT_QOS = int(os.environ.get("MQTT_QOS", "1"))
COMMAND_OUTPUT_ENABLED = env_flag("COMMAND_OUTPUT_ENABLED", False)
COMMAND_TOPICS_PATH = os.environ.get("COMMAND_TOPICS_PATH", "/runtime_config/topics.json")
MODEL_PROFILES_PATH = os.environ.get("MODEL_PROFILES_PATH", "")

MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

BASE = f"/tmp/{SENDER}"
KB_PATH = os.environ.get("KB_PATH", f"{BASE}/knowledgeBase/hbw_lstm.keras")
AB_PATH = os.environ.get("AB_PATH", f"{BASE}/activationBase/activation.json")

MODEL = None
ACTIVATION = None
CONTRACT = None
COMMAND_TOPICS = {}
RESPONSE_CACHE = ResponseCache()
LOADED_PROFILES = {}
ACTIVE_MODEL_PROFILE = DEFAULT_MODEL_PROFILE


def load_json(path: str):
    """Liest die Activation-Datei mit Feature-Reihenfolge und Klassen."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def wait_for_files(paths, timeout_s=180, interval_s=1):
    """Wartet auf Modell und Activation im gemounteten Registry-Pfad."""
    t0 = time.time()
    while True:
        missing = [p for p in paths if not os.path.exists(p)]
        if not missing:
            return
        if time.time() - t0 > timeout_s:
            raise FileNotFoundError(f"Timeout waiting for files: {missing}")
        print(f"[WAIT] missing: {missing} (sleep {interval_s}s)", flush=True)
        time.sleep(interval_s)


def ensure_loaded():
    """Laedt den Deploymentstand und optionale virtuelle Profile einmalig."""
    global MODEL, ACTIVATION, CONTRACT, LOADED_PROFILES, ACTIVE_MODEL_PROFILE
    if LOADED_PROFILES:
        return
    default_profile, specs = load_profile_specs(
        MODEL_PROFILES_PATH or None,
        domain="hbw",
        active_model_path=KB_PATH,
        active_activation_path=AB_PATH,
    )
    for profile_id, spec in specs.items():
        activation = load_json(str(spec["activation_path"]))
        model = tf.keras.models.load_model(str(spec["model_path"]))
        contract = build_model_contract(
            domain="hbw",
            activation=activation,
            model_path=spec["model_path"],
            request_topic=MQTT_REQ_TOPIC,
            response_topic=MQTT_RES_TOPIC,
            command_output=command_output_contract(
                command_topics=COMMAND_TOPICS,
                enabled=COMMAND_OUTPUT_ENABLED,
            ),
        )
        expected_model_id = spec.get("expected_model_id")
        if expected_model_id and expected_model_id != contract["model_id"]:
            raise ValueError(
                f"profile {profile_id!r} model_id mismatch: expected {expected_model_id}, got {contract['model_id']}",
            )
        LOADED_PROFILES[profile_id] = {**spec, "activation": activation, "model": model, "contract": contract}
    ACTIVE_MODEL_PROFILE = default_profile
    MODEL = LOADED_PROFILES[default_profile]["model"]
    ACTIVATION = LOADED_PROFILES[default_profile]["activation"]
    CONTRACT = profile_contract(default_profile, LOADED_PROFILES)


def class_ids_for_output(activation, n_outputs):
    """Sichert ab, dass Modelloutputs auf echte HBW-Befehle gemappt werden."""
    class_ids = activation.get("class_ids")
    if class_ids is None:
        class_ids = list(range(n_outputs))
    class_ids = [int(class_id) for class_id in class_ids]
    if len(class_ids) != n_outputs:
        raise ValueError(
            f"class_ids/output mismatch. class_ids has {len(class_ids)} entries, "
            f"model returned {n_outputs} outputs"
        )
    return class_ids


def predict(sequence, profile=None):
    """Validiert das Sequenzfenster und berechnet HBW-Befehl plus Top-3."""
    ensure_loaded()
    activation = ACTIVATION if profile is None else profile["activation"]
    model = MODEL if profile is None else profile["model"]
    time_steps = int(activation["time_steps"])
    feature_cols = activation["feature_cols"]
    cmd_map = {int(k): v for k, v in activation["cmd_map"].items()}

    x = np.asarray(sequence, dtype=np.float32)
    if x.shape != (time_steps, len(feature_cols)):
        raise ValueError(f"Sequence shape mismatch. Expected {(time_steps, len(feature_cols))}, got {x.shape}")

    x = x.reshape(1, time_steps, len(feature_cols))
    proba = model.predict(x, verbose=0)[0]
    class_ids = class_ids_for_output(activation, len(proba))
    y_idx = int(np.argmax(proba))
    y_hat = int(class_ids[y_idx])

    top_idx = np.argsort(proba)[-3:][::-1]
    top3 = [
        {
            "cmd": int(class_ids[i]),
            "name": cmd_map.get(int(class_ids[i]), "unknown"),
            "p": float(proba[i]),
        }
        for i in top_idx
    ]
    return y_hat, cmd_map.get(y_hat, "unknown"), top3


def on_connect(client, userdata, connect_flags, reason_code, properties):
    """Publiziert den retained Modellvertrag und abonniert HBW-Requests."""
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
    """Publiziert HBW-Command und korrelierbare JSON-Response unabhaengig."""
    req = {}
    try:
        req = json.loads(msg.payload.decode("utf-8"))
        request_id = str(req.get("request_id", ""))
        if not request_id:
            raise ValueError("request_id is required")

        cached = RESPONSE_CACHE.get(request_id)
        if cached is not None:
            client.publish(MQTT_RES_TOPIC, json.dumps(cached), qos=MQTT_QOS, retain=False)
            print(f"[MQTT] duplicate request_id={request_id} -> response replayed without command", flush=True)
            return
        if LOADED_PROFILES:
            selected_profile_id, selected_profile = select_profile(
                req,
                default_profile=ACTIVE_MODEL_PROFILE,
                loaded_profiles=LOADED_PROFILES,
            )
            selected_contract = selected_profile["contract"]
        else:
            selected_profile_id = str(req.get("model_profile") or DEFAULT_MODEL_PROFILE)
            if selected_profile_id != DEFAULT_MODEL_PROFILE:
                raise ValueError(f"unknown model_profile {selected_profile_id!r}")
            selected_profile = None
            selected_contract = CONTRACT
        sequence = req["sequence"]

        y_hat, y_name, top3 = predict(sequence) if selected_profile is None else predict(sequence, selected_profile)
        command_output = publish_direct_command(
            client,
            domain="hbw",
            command=y_hat,
            command_topics=COMMAND_TOPICS,
            enabled=COMMAND_OUTPUT_ENABLED,
        )
        res = response_payload(
            req,
            model_id=selected_contract["model_id"],
            model_profile=selected_profile_id,
            cmd=y_hat,
            name=y_name,
            top3=top3,
            command_output=command_output,
        )
        RESPONSE_CACHE.remember(request_id, res)
        client.publish(MQTT_RES_TOPIC, json.dumps(res), qos=MQTT_QOS, retain=False)
        print(
            f"[MQTT] request_id={request_id} -> cmd={y_hat} ({y_name}) "
            f"command_output={command_output['reason']}",
            flush=True,
        )

    except Exception as e:
        error_profile_id = str(req.get("model_profile") or DEFAULT_MODEL_PROFILE)
        error_profile = LOADED_PROFILES.get(error_profile_id)
        error_model_id = (
            error_profile["contract"]["model_id"]
            if error_profile is not None
            else CONTRACT["model_id"]
        )
        err = response_payload(
            req,
            model_id=error_model_id,
            model_profile=error_profile_id,
            error=str(e),
        )
        request_id = str(req.get("request_id", ""))
        if request_id and RESPONSE_CACHE.get(request_id) is None:
            RESPONSE_CACHE.remember(request_id, err)
        client.publish(MQTT_RES_TOPIC, json.dumps(err), qos=MQTT_QOS, retain=False)
        print("[ERR]", repr(e), flush=True)


def main():
    """Startet den HBW-Inferenzcontainer als MQTT-Client."""
    global COMMAND_TOPICS
    try:
        print(f"[INIT] waiting for KB={KB_PATH} and AB={AB_PATH}", flush=True)
        wait_for_files([KB_PATH, AB_PATH], timeout_s=180, interval_s=1)
        COMMAND_TOPICS = load_command_topic_map(COMMAND_TOPICS_PATH, "hbw")
        ensure_loaded()
        for profile_id, profile in LOADED_PROFILES.items():
            missing_topics = sorted(
                set(int(value) for value in profile["activation"]["class_ids"]) - set(COMMAND_TOPICS),
            )
            if missing_topics:
                raise ValueError(f"HBW profile {profile_id!r} classes without physical command topics: {missing_topics}")
        print("[INIT] model+activation loaded OK", flush=True)
        print(
            f"[INIT] broker={MQTT_HOST}:{MQTT_PORT} req={MQTT_REQ_TOPIC} "
            f"res={MQTT_RES_TOPIC} direct_commands={COMMAND_OUTPUT_ENABLED} "
            f"profiles={','.join(LOADED_PROFILES)}",
            flush=True,
        )
    except Exception as e:
        # Ohne Modellvertrag waere die Response fachlich nicht interpretierbar.
        print("[FATAL]", repr(e), flush=True)
        raise

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    configure_last_will(client, status_topic=MQTT_STATUS_TOPIC, domain="hbw", qos=MQTT_QOS)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
