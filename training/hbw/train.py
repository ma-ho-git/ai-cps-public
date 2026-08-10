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
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.utils.class_weight import compute_class_weight


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
    """Baut label-last Fenster aus einer bereits sortierten Sequenz."""
    if len(df_split) < time_steps:
        return (
            np.empty((0, time_steps, len(feature_cols)), dtype=np.float32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.int32),
        )

    feature_values = df_split[feature_cols].to_numpy(dtype=np.float32)
    label_values = df_split[label_col].astype(int).to_numpy()
    X: list[np.ndarray] = []
    y_idx: list[int] = []
    y_ids: list[int] = []

    for start in range(0, len(df_split) - time_steps + 1):
        end = start + time_steps
        target_id = int(label_values[end - 1])
        X.append(feature_values[start:end])
        y_idx.append(class_to_index[target_id])
        y_ids.append(target_id)

    return (
        np.stack(X).astype(np.float32),
        np.array(y_idx, dtype=np.int32),
        np.array(y_ids, dtype=np.int32),
    )


def make_windows_label_last_grouped(
    df_split: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    time_steps: int,
    class_to_index: dict[int, int],
    group_col: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Baut Fenster ohne Schnitte ueber `sequence_id`-Grenzen."""
    if group_col not in df_split.columns:
        raise ValueError(f"group_col {group_col!r} is missing from the CSV.")

    X_parts: list[np.ndarray] = []
    y_idx_parts: list[np.ndarray] = []
    y_id_parts: list[np.ndarray] = []
    group_parts: list[np.ndarray] = []

    for group_value, group_data in df_split.groupby(group_col, sort=False):
        X_group, y_idx_group, y_ids_group = make_windows_label_last(
            group_data.reset_index(drop=True),
            feature_cols,
            label_col,
            time_steps,
            class_to_index,
        )
        if len(X_group) == 0:
            continue
        X_parts.append(X_group)
        y_idx_parts.append(y_idx_group)
        y_id_parts.append(y_ids_group)
        group_parts.append(np.array([str(group_value)] * len(y_idx_group), dtype=object))

    if not X_parts:
        return (
            np.empty((0, time_steps, len(feature_cols)), dtype=np.float32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.int32),
            np.array([], dtype=object),
        )

    return (
        np.concatenate(X_parts).astype(np.float32),
        np.concatenate(y_idx_parts).astype(np.int32),
        np.concatenate(y_id_parts).astype(np.int32),
        np.concatenate(group_parts),
    )


def train_validation_split_by_group(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    validation_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Trennt komplette Sequenzen in Fit und Validation."""
    if validation_fraction <= 0 or len(y) < 2:
        return (
            X,
            np.empty((0,) + X.shape[1:], dtype=X.dtype),
            y,
            np.array([], dtype=y.dtype),
            groups,
            np.array([], dtype=groups.dtype),
        )

    unique_groups = np.array(sorted(set(groups.astype(str))), dtype=object)
    if len(unique_groups) < 2:
        return (
            X,
            np.empty((0,) + X.shape[1:], dtype=X.dtype),
            y,
            np.array([], dtype=y.dtype),
            groups,
            np.array([], dtype=groups.dtype),
        )

    rng = np.random.default_rng(seed)
    shuffled_groups = unique_groups.copy()
    rng.shuffle(shuffled_groups)
    n_val_groups = max(1, int(round(len(unique_groups) * validation_fraction)))
    n_val_groups = min(n_val_groups, len(unique_groups) - 1)
    val_groups = set(shuffled_groups[:n_val_groups])
    val_mask = np.array([str(group) in val_groups for group in groups], dtype=bool)
    fit_mask = ~val_mask
    return X[fit_mask], X[val_mask], y[fit_mask], y[val_mask], groups[fit_mask], groups[val_mask]


def validate_input_data(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    class_ids: list[int],
    group_col: str,
) -> None:
    """Prueft den HBW-Datensatz gegen den aktuellen HBW-Featurevertrag."""
    required_cols = ["split", group_col, label_col, *feature_cols]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

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

    storage_cols = [f"empty_storage_{idx}" for idx in range(10)]
    missing_storage_cols = [col for col in storage_cols if col not in feature_cols]
    if missing_storage_cols:
        raise ValueError(f"HBW feature columns must contain empty_storage_0..9: {missing_storage_cols}")
    if "empty_storage" in feature_cols:
        raise ValueError("HBW feature columns must not contain numeric empty_storage.")

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
    """Zaehlt Labels JSON-freundlich als String-Keys."""
    if len(values) == 0:
        return {}
    labels, counts = np.unique(values.astype(int), return_counts=True)
    return {str(int(label)): int(count) for label, count in zip(labels, counts)}


def evaluate_model(
    model: tf.keras.Model,
    X: np.ndarray,
    y_idx: np.ndarray,
    class_ids: list[int],
) -> dict[str, Any]:
    """Berechnet Metriken auf echten HBW-Befehlswerten."""
    if len(X) == 0:
        return {
            "accuracy": None,
            "balanced_accuracy": None,
            "macro_f1": None,
            "confusion_matrix": [],
            "classification_report": "",
            "classification_report_dict": {},
        }

    proba = model.predict(X, verbose=0)
    y_pred_idx = proba.argmax(axis=1).astype(np.int32)
    class_ids_arr = np.array(class_ids, dtype=np.int32)
    y_true_ids = class_ids_arr[y_idx]
    y_pred_ids = class_ids_arr[y_pred_idx]

    return {
        "accuracy": float(accuracy_score(y_true_ids, y_pred_ids)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true_ids, y_pred_ids)),
        "macro_f1": float(f1_score(y_true_ids, y_pred_ids, labels=class_ids, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true_ids, y_pred_ids, labels=class_ids).tolist(),
        "classification_report": classification_report(
            y_true_ids,
            y_pred_ids,
            labels=class_ids,
            digits=3,
            zero_division=0,
        ),
        "classification_report_dict": classification_report(
            y_true_ids,
            y_pred_ids,
            labels=class_ids,
            output_dict=True,
            zero_division=0,
        ),
    }


def compute_balanced_class_weight(y: np.ndarray, n_classes: int) -> dict[int, float]:
    """Berechnet Class Weights nur fuer im Fit-Split vorhandene Klassen."""
    if len(y) == 0:
        return {idx: 1.0 for idx in range(n_classes)}
    present_classes = np.unique(y)
    present_weights = compute_class_weight("balanced", classes=present_classes, y=y)
    class_weight = {idx: 1.0 for idx in range(n_classes)}
    class_weight.update({int(idx): float(weight) for idx, weight in zip(present_classes, present_weights)})
    return class_weight


def model_param_counts(model: tf.keras.Model) -> dict[str, int]:
    """Zaehlt Modellparameter fuer Metrikdatei und Thesis-Vergleich."""
    trainable = int(sum(np.prod(v.shape) for v in model.trainable_weights))
    non_trainable = int(sum(np.prod(v.shape) for v in model.non_trainable_weights))
    return {"trainable": trainable, "non_trainable": non_trainable, "total": trainable + non_trainable}


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


def main() -> None:
    """Fuehrt Training, Evaluation und Registry-Update fuer HBW aus."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    seed = int(cfg.get("seed", 42))
    np.random.seed(seed)
    tf.random.set_seed(seed)

    csv_path = cfg["csv_path"]
    label_col = cfg["label_col"]
    feature_cols = list(cfg["feature_cols"])
    class_ids = [int(value) for value in cfg["class_ids"]]
    class_to_index = {class_id: idx for idx, class_id in enumerate(class_ids)}
    time_steps = int(cfg["time_steps"])
    group_col = str(cfg.get("group_col", "sequence_id"))
    domain = cfg["domain"]
    publish_latest = bool(cfg.get("publish_latest", True))
    experiment_name = str(cfg.get("experiment_name", "default"))

    df = pd.read_csv(csv_path)
    validate_input_data(df, feature_cols, label_col, class_ids, group_col)
    df_train = df[df["split"] == "train"].reset_index(drop=True)
    df_test = df[df["split"] == "test"].reset_index(drop=True)

    X_train_all, y_train_all, y_train_ids, train_groups = make_windows_label_last_grouped(
        df_train,
        feature_cols,
        label_col,
        time_steps,
        class_to_index,
        group_col,
    )
    X_test, y_test, y_test_ids, test_groups = make_windows_label_last_grouped(
        df_test,
        feature_cols,
        label_col,
        time_steps,
        class_to_index,
        group_col,
    )
    if len(X_train_all) == 0:
        raise ValueError("No training windows created. Check time_steps and sequence lengths.")

    X_fit, X_val, y_fit, y_val, fit_groups, val_groups = train_validation_split_by_group(
        X_train_all,
        y_train_all,
        train_groups,
        float(cfg.get("validation_fraction", 0.2)),
        seed,
    )
    if len(X_fit) == 0:
        raise ValueError("No fit windows remain after validation split.")

    normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(X_fit)
    model = build_model(
        time_steps=time_steps,
        n_features=len(feature_cols),
        n_classes=len(class_ids),
        normalizer=normalizer,
        lstm_units=int(cfg.get("lstm_units", 32)),
        dense_units=int(cfg.get("dense_units", 32)),
        dropout=float(cfg.get("dropout", 0.2)),
        learning_rate=float(cfg.get("learning_rate", 1e-3)),
        l2_value=float(cfg.get("l2", 1e-4)),
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss" if len(X_val) else "loss",
            patience=int(cfg.get("patience", 10)),
            restore_best_weights=True,
        )
    ]
    class_weight = compute_balanced_class_weight(y_fit, len(class_ids)) if cfg.get("use_class_weight", True) else None
    fit_kwargs: dict[str, Any] = {}
    if len(X_val):
        fit_kwargs["validation_data"] = (X_val, y_val)
    history = model.fit(
        X_fit,
        y_fit,
        epochs=int(cfg.get("epochs", 100)),
        batch_size=int(cfg.get("batch_size", 16)),
        callbacks=callbacks,
        class_weight=class_weight,
        verbose=2,
        **fit_kwargs,
    )

    train_eval = evaluate_model(model, X_train_all, y_train_all, class_ids)
    test_eval = evaluate_model(model, X_test, y_test, class_ids)
    val_eval = evaluate_model(model, X_val, y_val, class_ids)

    ts = time.strftime("%Y-%m-%d_%H%M%S")
    registry_root = cfg.get("model_registry_root", "/model_registry")
    out_base = os.path.join(registry_root, domain)
    ver_dir = f"{out_base}/versions/{ts}"
    os.makedirs(ver_dir, exist_ok=True)
    model_path = os.path.join(ver_dir, "model.keras")
    model.save(model_path)

    act_meta = {
        "domain": domain,
        "time_steps": time_steps,
        "feature_cols": feature_cols,
        "label_col": label_col,
        "class_ids": class_ids,
        "label_encoding": "dense_class_ids",
        "n_classes": len(class_ids),
        "group_col": group_col,
        "trained_at": ts,
        "dataset_path": csv_path,
        "input_shape": [time_steps, len(feature_cols)],
    }
    activation = dict(act_meta)
    base_path = cfg.get("activation_base_path")
    if base_path:
        with open(base_path, "r", encoding="utf-8") as f:
            base = json.load(f)
        if "cmd_map" not in base:
            base["cmd_map"] = {str(class_id): f"hbw_command_{class_id}" for class_id in class_ids}
        base["cmd_map"] = {str(k): v for k, v in base["cmd_map"].items()}
        base.update(act_meta)
        activation = base

    metrics = {
        "provenance": {
            "experiment_name": experiment_name,
            "publish_latest": publish_latest,
            "config_path": args.config,
            "config_sha256": sha256_file(args.config),
            "dataset_sha256": sha256_file(csv_path),
            "model_sha256": sha256_file(model_path),
        },
        "trained_at": ts,
        "dataset_path": csv_path,
        "model": {
            "input_shape": [None, time_steps, len(feature_cols)],
            "output_units": len(class_ids),
            "class_ids": class_ids,
            "parameters": model_param_counts(model),
        },
        "windowing": {
            "mode": "split_group_label_last",
            "group_col": group_col,
            "train_windows": int(len(y_train_all)),
            "fit_windows": int(len(y_fit)),
            "validation_windows": int(len(y_val)),
            "test_windows": int(len(y_test)),
            "train_groups": sorted(set(train_groups.astype(str))),
            "fit_groups": sorted(set(fit_groups.astype(str))),
            "validation_groups": sorted(set(val_groups.astype(str))) if len(val_groups) else [],
            "test_groups": sorted(set(test_groups.astype(str))),
            "train_label_counts": label_counts(y_train_ids),
            "test_label_counts": label_counts(y_test_ids),
        },
        "training": {
            "epochs_ran": int(len(history.history.get("loss", []))),
            "history": {key: [float(value) for value in values] for key, values in history.history.items()},
            "class_weight": {str(k): float(v) for k, v in (class_weight or {}).items()},
        },
        "train_metrics": train_eval,
        "validation_metrics": val_eval,
        "test_metrics": test_eval,
    }

    with open(os.path.join(ver_dir, "activation.json"), "w", encoding="utf-8") as f:
        json.dump(activation, f, indent=2)
    with open(os.path.join(ver_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    latest_dir = finalize_model_version(ver_dir, out_base, ts, publish_latest)

    print(f"[OK] Saved version: {ver_dir}")
    if latest_dir:
        print(f"[OK] Updated latest: {latest_dir}")
    else:
        print("[OK] Candidate mode: latest was not changed")
    print(f"[OK] Input shape: (None, {time_steps}, {len(feature_cols)})")
    print(f"[OK] Output units/classes: {len(class_ids)} / {class_ids}")
    print(f"[OK] Train windows: {len(y_train_all)} | Test windows: {len(y_test)}")
    print(f"[OK] Test accuracy: {test_eval.get('accuracy')}")
    print(f"[OK] Test balanced accuracy: {test_eval.get('balanced_accuracy')}")
    print(f"[OK] Test macro F1: {test_eval.get('macro_f1')}")


if __name__ == "__main__":
    main()
