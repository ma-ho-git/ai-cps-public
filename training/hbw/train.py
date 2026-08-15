"""Trainiert das aktive PLC-nahe HBW-LSTM.

Der fruehere HBW-Pfad nutzte einen abstrakten 7-Feature-Datensatz. Dieser
Trainingscontainer arbeitet nun mit dem synthetischen PLC-nahen HBW-Datensatz:
`label_HBW` bleibt ein echter Befehlswert, Fenster werden nach `sequence_id`
gruppiert und `empty_storage_0..9` ist die einzige explizite Lagerzustandsinformation.
Die SSC-Lichtschranke am Lager ist als reales Prozesssignal bewusst enthalten;
weitere SSC-/SLD-Signale gehoeren nicht zum aktiven HBW-Vertrag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from typing import Any

import numpy as np
import pandas as pd
import tensorflow as tf

from training import lstm_common


def sha256_file(path: str) -> str:
    """Berechnet den SHA-256-Hash eines Trainings- oder Modellartefakts."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_windows_label_last(
    df_split: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    time_steps: int,
    class_to_index: dict[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kompatibler HBW-Einstieg fuer den gemeinsamen Windowing-Helfer."""
    return lstm_common.make_windows_label_last(
        df_split, feature_cols, label_col, time_steps, class_to_index
    )


def make_windows_label_last_grouped(
    df_split: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    time_steps: int,
    class_to_index: dict[int, int],
    group_col: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Kompatibler HBW-Einstieg fuer gruppiertes Windowing."""
    return lstm_common.make_windows_label_last_grouped(
        df_split, feature_cols, label_col, time_steps, class_to_index, group_col
    )


def train_validation_split_by_group(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    validation_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Kompatibler HBW-Einstieg fuer den gemeinsamen Gruppen-Split."""
    return lstm_common.train_validation_split_by_group(
        X, y, groups, validation_fraction, seed
    )


def validate_input_data(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    class_ids: list[int],
    group_col: str,
) -> None:
    """Prueft den HBW-Datensatz gegen den aktuellen HBW-Featurevertrag."""
    required_cols = ["split", group_col, label_col, *feature_cols]
    validate_required_columns(df, required_cols)
    validate_hbw_feature_names(feature_cols, group_col, label_col)
    validate_hbw_sensor_contract(feature_cols)
    validate_hbw_storage_contract(feature_cols)
    validate_hbw_values(df, required_cols, feature_cols, label_col, class_ids)


def validate_required_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")


def validate_hbw_feature_names(
    feature_cols: list[str], group_col: str, label_col: str
) -> None:
    forbidden_exact = {"split", group_col, label_col, "ts", "ts_ms", "episode_id", "step_idx", "step"}
    overlap = sorted(forbidden_exact.intersection(feature_cols))
    if overlap:
        raise ValueError(f"Feature columns must not include metadata/label columns: {overlap}")
    forbidden_prefix = [col for col in feature_cols if col.startswith("ctx_") or col.startswith("storage_slot_")]
    if forbidden_prefix:
        raise ValueError(
            "HBW feature columns must not include ctx_* or storage_slot_* columns; "
            f"use empty_storage_0..9 as the only explicit storage-state feature: {forbidden_prefix}"
        )


def validate_hbw_sensor_contract(feature_cols: list[str]) -> None:
    start_signal_col = "IX_SSC_LightBarrierStorage_I3"
    if start_signal_col not in feature_cols:
        raise ValueError(f"HBW feature columns must contain {start_signal_col}.")
    forbidden_external_sensor_cols = [
        col
        for col in feature_cols
        if (col.startswith("IX_SSC_") and col != start_signal_col)
        or col.startswith("IW_SSC_")
        or col.startswith("IW_SLD_")
    ]
    if forbidden_external_sensor_cols:
        raise ValueError(
            "HBW only allows the storage light barrier from SSC/SLD-side signals; "
            f"unexpected columns: {forbidden_external_sensor_cols}"
        )


def validate_hbw_storage_contract(feature_cols: list[str]) -> None:
    storage_cols = [f"empty_storage_{idx}" for idx in range(10)]
    missing_storage_cols = [col for col in storage_cols if col not in feature_cols]
    if missing_storage_cols:
        raise ValueError(f"HBW feature columns must contain empty_storage_0..9: {missing_storage_cols}")
    if "empty_storage" in feature_cols:
        raise ValueError("HBW feature columns must not contain numeric empty_storage.")


def validate_hbw_values(
    df: pd.DataFrame,
    required_cols: list[str],
    feature_cols: list[str],
    label_col: str,
    class_ids: list[int],
) -> None:
    na_counts = df[required_cols].isna().sum()
    na_counts = na_counts[na_counts > 0].to_dict()
    if na_counts:
        raise ValueError(f"CSV contains NaN values in model-relevant columns: {na_counts}")

    non_numeric = [col for col in feature_cols if not pd.api.types.is_numeric_dtype(df[col])]
    if non_numeric:
        raise ValueError(f"Feature columns must be numeric: {non_numeric}")

    split_values = set(df["split"].astype(str))
    if split_values != {"train", "test"}:
        raise ValueError(f"Expected split values {{'train', 'test'}}, got {sorted(split_values)}")

    label_values = sorted(df[label_col].astype(int).unique().tolist())
    if label_values != sorted(class_ids):
        raise ValueError(f"Dataset labels {label_values} do not match class_ids {sorted(class_ids)}")


def build_model(
    *,
    time_steps: int,
    n_features: int,
    n_classes: int,
    normalizer: tf.keras.layers.Normalization,
    lstm_units: int,
    dense_units: int,
    dropout: float,
    learning_rate: float,
    l2_value: float,
) -> tf.keras.Model:
    """Baut die kompakte HBW-LSTM-Baseline fuer echte PLC-Befehlslabels."""
    regularizer = tf.keras.regularizers.l2(l2_value) if l2_value else None
    inp = tf.keras.Input(shape=(time_steps, n_features), name="x")
    # Die Normalisierung gehoert ins Modell, damit MQTT spaeter Rohwerte senden kann.
    x = normalizer(inp)
    x = tf.keras.layers.LSTM(
        lstm_units,
        name="temporal_encoder",
        kernel_regularizer=regularizer,
    )(x)
    x = tf.keras.layers.Dropout(dropout, name="temporal_dropout")(x)
    x = tf.keras.layers.Dense(
        dense_units,
        activation="relu",
        kernel_regularizer=regularizer,
        name="command_context",
    )(x)
    out = tf.keras.layers.Dense(n_classes, activation="softmax", name="y_hat")(x)
    model = tf.keras.Model(inp, out)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def label_counts(values: np.ndarray) -> dict[str, int]:
    return lstm_common.label_counts(values)


def evaluate_model(
    model: tf.keras.Model,
    X: np.ndarray,
    y_idx: np.ndarray,
    class_ids: list[int],
) -> dict[str, Any]:
    return lstm_common.evaluate_model(model, X, y_idx, class_ids)


def compute_balanced_class_weight(y: np.ndarray, n_classes: int) -> dict[int, float]:
    return lstm_common.compute_balanced_class_weight(y, n_classes)


def model_param_counts(model: tf.keras.Model) -> dict[str, int]:
    return lstm_common.model_param_counts(model)


def unique_path(path: str) -> str:
    """Findet einen freien Archivpfad fuer alte Registry-Ordner."""
    if not os.path.exists(path):
        return path
    idx = 1
    while os.path.exists(f"{path}_{idx}"):
        idx += 1
    return f"{path}_{idx}"


def safe_replace_dir(src_dir: str, dst_dir: str, rename_existing_to: str | None = None) -> None:
    """Ersetzt `latest` robust, auch wenn alte Docker-Artefakte andere Rechte haben."""
    if os.path.exists(dst_dir):
        try:
            shutil.rmtree(dst_dir)
        except PermissionError:
            if rename_existing_to is None:
                raise
            archive_path = unique_path(rename_existing_to)
            os.rename(dst_dir, archive_path)
            print(f"[WARN] Could not delete {dst_dir}; moved existing directory to {archive_path}", flush=True)
    shutil.copytree(src_dir, dst_dir)


def finalize_model_version(
    ver_dir: str,
    out_base: str,
    timestamp: str,
    publish_latest: bool,
) -> str | None:
    """Publiziert eine Version nur im expliziten Deploymentmodus als `latest`."""
    if not publish_latest:
        return None

    latest_dir = os.path.join(out_base, "latest")
    backup_dir = os.path.join(out_base, "versions", f"{timestamp}_backup_prev_latest")
    safe_replace_dir(ver_dir, latest_dir, rename_existing_to=backup_dir)
    return latest_dir


def load_training_config() -> tuple[str, dict[str, Any]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        return args.config, json.load(handle)


def hbw_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    classes = [int(value) for value in cfg["class_ids"]]
    return {
        "seed": int(cfg.get("seed", 42)),
        "csv_path": cfg["csv_path"],
        "label_col": cfg["label_col"],
        "feature_cols": list(cfg["feature_cols"]),
        "class_ids": classes,
        "class_to_index": {value: index for index, value in enumerate(classes)},
        "time_steps": int(cfg["time_steps"]),
        "group_col": str(cfg.get("group_col", "sequence_id")),
        "domain": cfg["domain"],
        "publish_latest": bool(cfg.get("publish_latest", True)),
        "experiment_name": str(cfg.get("experiment_name", "default")),
        "validation_fraction": float(cfg.get("validation_fraction", 0.2)),
        "epochs": int(cfg.get("epochs", 100)),
        "batch_size": int(cfg.get("batch_size", 16)),
        "patience": int(cfg.get("patience", 10)),
        "use_class_weight": bool(cfg.get("use_class_weight", True)),
    }


def set_random_seed(seed: int) -> None:
    np.random.seed(seed)
    tf.random.set_seed(seed)


def hbw_windows(frame: pd.DataFrame, settings: dict[str, Any]) -> dict[str, Any]:
    train = frame[frame["split"] == "train"].reset_index(drop=True)
    test = frame[frame["split"] == "test"].reset_index(drop=True)
    common = (
        settings["feature_cols"], settings["label_col"], settings["time_steps"],
        settings["class_to_index"], settings["group_col"],
    )
    train_values = make_windows_label_last_grouped(train, *common)
    test_values = make_windows_label_last_grouped(test, *common)
    train_x, train_y, train_ids, train_groups = train_values
    test_x, test_y, test_ids, test_groups = test_values
    if len(train_x) == 0:
        raise ValueError("No training windows created. Check time_steps and sequence lengths.")
    split = train_validation_split_by_group(
        train_x, train_y, train_groups, settings["validation_fraction"], settings["seed"]
    )
    fit_x, val_x, fit_y, val_y, fit_groups, val_groups = split
    if len(fit_x) == 0:
        raise ValueError("No fit windows remain after validation split.")
    return {
        "train_x": train_x, "train_y": train_y, "train_ids": train_ids,
        "train_groups": train_groups, "test_x": test_x, "test_y": test_y,
        "test_ids": test_ids, "test_groups": test_groups, "fit_x": fit_x,
        "fit_y": fit_y, "fit_groups": fit_groups, "val_x": val_x,
        "val_y": val_y, "val_groups": val_groups,
    }


def train_hbw_model(
    cfg: dict[str, Any], settings: dict[str, Any], data: dict[str, Any]
) -> tuple[Any, Any, dict[int, float] | None]:
    normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(data["fit_x"])
    model = build_model(
        time_steps=settings["time_steps"],
        n_features=len(settings["feature_cols"]),
        n_classes=len(settings["class_ids"]),
        normalizer=normalizer,
        lstm_units=int(cfg.get("lstm_units", 32)),
        dense_units=int(cfg.get("dense_units", 32)),
        dropout=float(cfg.get("dropout", 0.2)),
        learning_rate=float(cfg.get("learning_rate", 1e-3)),
        l2_value=float(cfg.get("l2", 1e-4)),
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss" if len(data["val_x"]) else "loss",
            patience=settings["patience"],
            restore_best_weights=True,
        )
    ]
    class_weight = None
    if settings["use_class_weight"]:
        class_weight = compute_balanced_class_weight(data["fit_y"], len(settings["class_ids"]))
    fit_kwargs: dict[str, Any] = {}
    if len(data["val_x"]):
        fit_kwargs["validation_data"] = (data["val_x"], data["val_y"])
    history = model.fit(
        data["fit_x"], data["fit_y"],
        epochs=settings["epochs"], batch_size=settings["batch_size"],
        callbacks=callbacks,
        class_weight=class_weight,
        verbose=2,
        **fit_kwargs,
    )
    return model, history, class_weight


def hbw_activation(
    cfg: dict[str, Any], settings: dict[str, Any], timestamp: str
) -> dict[str, Any]:
    classes = settings["class_ids"]
    features = settings["feature_cols"]
    metadata = {
        "domain": settings["domain"], "time_steps": settings["time_steps"],
        "feature_cols": features, "label_col": settings["label_col"],
        "class_ids": classes, "label_encoding": "dense_class_ids",
        "n_classes": len(classes), "group_col": settings["group_col"],
        "trained_at": timestamp, "dataset_path": settings["csv_path"],
        "input_shape": [settings["time_steps"], len(features)],
    }
    base_path = cfg.get("activation_base_path")
    if not base_path:
        return metadata
    with open(base_path, "r", encoding="utf-8") as handle:
        activation = json.load(handle)
    if "cmd_map" not in activation:
        activation["cmd_map"] = {str(value): f"hbw_command_{value}" for value in classes}
    activation["cmd_map"] = {str(key): value for key, value in activation["cmd_map"].items()}
    activation.update(metadata)
    return activation


def hbw_metrics(
    config_path: str, settings: dict[str, Any], data: dict[str, Any],
    model: Any, model_path: str, history: Any, class_weight: dict[int, float] | None
) -> dict[str, Any]:
    classes = settings["class_ids"]
    evaluations = {
        "train_metrics": evaluate_model(model, data["train_x"], data["train_y"], classes),
        "validation_metrics": evaluate_model(model, data["val_x"], data["val_y"], classes),
        "test_metrics": evaluate_model(model, data["test_x"], data["test_y"], classes),
    }
    return {
        "provenance": {
            "experiment_name": settings["experiment_name"],
            "publish_latest": settings["publish_latest"],
            "config_path": config_path, "config_sha256": sha256_file(config_path),
            "dataset_sha256": sha256_file(settings["csv_path"]),
            "model_sha256": sha256_file(model_path),
        },
        "trained_at": settings["timestamp"], "dataset_path": settings["csv_path"],
        "model": hbw_model_metadata(model, settings),
        "windowing": hbw_window_metadata(settings, data),
        "training": {
            "epochs_ran": int(len(history.history.get("loss", []))),
            "history": {key: [float(value) for value in values] for key, values in history.history.items()},
            "class_weight": {str(key): float(value) for key, value in (class_weight or {}).items()},
        },
        **evaluations,
    }


def hbw_model_metadata(model: Any, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_shape": [None, settings["time_steps"], len(settings["feature_cols"])],
        "output_units": len(settings["class_ids"]),
        "class_ids": settings["class_ids"],
        "parameters": model_param_counts(model),
    }


def hbw_window_metadata(settings: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    groups = lambda values: sorted(set(values.astype(str))) if len(values) else []
    return {
        "mode": "split_group_label_last", "group_col": settings["group_col"],
        "train_windows": int(len(data["train_y"])), "fit_windows": int(len(data["fit_y"])),
        "validation_windows": int(len(data["val_y"])), "test_windows": int(len(data["test_y"])),
        "train_groups": groups(data["train_groups"]), "fit_groups": groups(data["fit_groups"]),
        "validation_groups": groups(data["val_groups"]), "test_groups": groups(data["test_groups"]),
        "train_label_counts": label_counts(data["train_ids"]),
        "test_label_counts": label_counts(data["test_ids"]),
    }


def save_hbw_artifacts(
    config_path: str, cfg: dict[str, Any], settings: dict[str, Any],
    data: dict[str, Any], model: Any, history: Any, class_weight: dict[int, float] | None
) -> tuple[str, str | None, dict[str, Any]]:
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    settings["timestamp"] = ts
    registry_root = cfg.get("model_registry_root", "/model_registry")
    out_base = os.path.join(registry_root, settings["domain"])
    ver_dir = f"{out_base}/versions/{ts}"
    os.makedirs(ver_dir, exist_ok=True)
    model_path = os.path.join(ver_dir, "model.keras")
    model.save(model_path)
    activation = hbw_activation(cfg, settings, ts)
    metrics = hbw_metrics(config_path, settings, data, model, model_path, history, class_weight)
    with open(os.path.join(ver_dir, "activation.json"), "w", encoding="utf-8") as handle:
        json.dump(activation, handle, indent=2)
    with open(os.path.join(ver_dir, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    latest_dir = finalize_model_version(ver_dir, out_base, ts, settings["publish_latest"])
    return ver_dir, latest_dir, metrics


def print_hbw_result(
    version_dir: str, latest_dir: str | None, settings: dict[str, Any],
    data: dict[str, Any], metrics: dict[str, Any]
) -> None:
    test_eval = metrics["test_metrics"]
    print(f"[OK] Saved version: {version_dir}")
    if latest_dir:
        print(f"[OK] Updated latest: {latest_dir}")
    else:
        print("[OK] Candidate mode: latest was not changed")
    print(f"[OK] Input shape: (None, {settings['time_steps']}, {len(settings['feature_cols'])})")
    print(f"[OK] Output units/classes: {len(settings['class_ids'])} / {settings['class_ids']}")
    print(f"[OK] Train windows: {len(data['train_y'])} | Test windows: {len(data['test_y'])}")
    print(f"[OK] Test accuracy: {test_eval.get('accuracy')}")
    print(f"[OK] Test balanced accuracy: {test_eval.get('balanced_accuracy')}")
    print(f"[OK] Test macro F1: {test_eval.get('macro_f1')}")


def main() -> None:
    """Fuehrt Training, Evaluation und Registry-Update fuer HBW aus."""
    config_path, cfg = load_training_config()
    settings = hbw_settings(cfg)
    set_random_seed(settings["seed"])
    frame = pd.read_csv(settings["csv_path"])
    validate_input_data(
        frame, settings["feature_cols"], settings["label_col"],
        settings["class_ids"], settings["group_col"],
    )
    data = hbw_windows(frame, settings)
    model, history, class_weight = train_hbw_model(cfg, settings, data)
    version_dir, latest_dir, metrics = save_hbw_artifacts(
        config_path, cfg, settings, data, model, history, class_weight
    )
    print_hbw_result(version_dir, latest_dir, settings, data, metrics)


if __name__ == "__main__":
    main()
