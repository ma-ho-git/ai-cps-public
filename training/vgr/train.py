"""Trainiert das aktive VGR-LSTM auf dem PLC-nahen Prozessfeature-Datensatz.

Dieses Skript ist der zentrale Trainingspfad fuer die neue VGR-Migration. Es
bildet Fenster nach `split` und optional nach `sequence_id`, vermeidet damit
Leakage ueber kuenstliche Sequenzgrenzen und speichert den vollstaendigen
Modellvertrag in `activation.json` und `metrics.json`.
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
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, train_test_split
from sklearn.utils.class_weight import compute_class_weight

try:
    import tensorflow as tf
except ModuleNotFoundError:
    tf = None


START_SIGNAL_COL = "IX_SSC_LightBarrierStorage_I3"


def require_tensorflow() -> None:
    """Verlangt TensorFlow nur fuer einen tatsaechlichen Trainingslauf.

    Die Windowing-Hilfen bleiben dadurch in schlanken Runtime-/CI-Umgebungen
    importierbar. Das Training selbst laeuft weiterhin im TensorFlow-Container.
    """
    if tf is None:
        raise RuntimeError(
            "TensorFlow is required for VGR training; use the train_vgr container."
        )


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
    """Baut label-last Fenster aus der vorhandenen Zeilenreihenfolge."""
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
    """Baut Fenster, ohne `sequence_id`- oder andere Gruppengrenzen zu schneiden."""
    X_parts: list[np.ndarray] = []
    y_idx_parts: list[np.ndarray] = []
    y_id_parts: list[np.ndarray] = []
    group_parts: list[np.ndarray] = []

    if group_col not in df_split.columns:
        raise ValueError(f"group_col {group_col!r} is missing from the CSV.")

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


def train_validation_split(
    X: np.ndarray,
    y: np.ndarray,
    validation_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Erzeugt einen klassischen Fenster-Split, falls kein Gruppenmodus genutzt wird."""
    if validation_fraction <= 0 or len(y) < 2:
        return X, np.empty((0,) + X.shape[1:], dtype=X.dtype), y, np.array([], dtype=y.dtype)

    classes, counts = np.unique(y, return_counts=True)
    stratify = y if len(classes) > 1 and counts.min() >= 2 else None

    return train_test_split(
        X,
        y,
        test_size=validation_fraction,
        random_state=seed,
        shuffle=True,
        stratify=stratify,
    )


def train_validation_split_by_group(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    validation_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Trennt Train/Validation so, dass komplette Sequenzen zusammenbleiben."""
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

    return (
        X[fit_mask],
        X[val_mask],
        y[fit_mask],
        y[val_mask],
        groups[fit_mask],
        groups[val_mask],
    )


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
    """Baut die kompakte VGR-LSTM-Baseline mit im Modell gespeicherter Normalisierung."""
    regularizer = tf.keras.regularizers.l2(l2_value) if l2_value else None

    inp = tf.keras.Input(shape=(time_steps, n_features), name="x")
    # Die Normalisierung wird nur auf Trainingsfenstern adaptiert und danach
    # mit dem Modell gespeichert. MQTT-Payloads koennen dadurch Rohwerte senden.
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


def model_param_counts(model: tf.keras.Model) -> dict[str, int]:
    """Zaehlt Modellparameter fuer Metrikdatei und Thesis-Vergleich."""
    trainable = int(sum(np.prod(v.shape) for v in model.trainable_weights))
    non_trainable = int(sum(np.prod(v.shape) for v in model.non_trainable_weights))
    return {
        "trainable": trainable,
        "non_trainable": non_trainable,
        "total": trainable + non_trainable,
    }


def unique_path(path: str) -> str:
    """Findet einen freien Pfad, wenn alte Registry-Ordner archiviert werden."""
    if not os.path.exists(path):
        return path
    idx = 1
    while os.path.exists(f"{path}_{idx}"):
        idx += 1
    return f"{path}_{idx}"


def safe_replace_dir(src_dir: str, dst_dir: str, rename_existing_to: str | None = None) -> None:
    """Ersetzt Registry-Ordner robust, auch bei Docker-Rechteproblemen."""
    if os.path.exists(dst_dir):
        try:
            shutil.rmtree(dst_dir)
        except PermissionError:
            if rename_existing_to is None:
                raise
            archive_path = unique_path(rename_existing_to)
            try:
                os.rename(dst_dir, archive_path)
            except PermissionError as rename_error:
                raise PermissionError(
                    f"Cannot replace {dst_dir}. The existing directory is not writable "
                    "by the current user. Run the training container or fix the "
                    "model_registry ownership before updating latest."
                ) from rename_error
            print(
                f"[WARN] Could not delete {dst_dir}; moved existing directory to {archive_path}",
                flush=True,
            )
    shutil.copytree(src_dir, dst_dir)


def finalize_model_version(
    ver_dir: str,
    out_base: str,
    timestamp: str,
    publish_latest: bool,
) -> str | None:
    """Publiziert eine Version optional als Deployment-Default `latest`.

    Kandidatentrainings setzen ``publish_latest=False``. In diesem Modus darf
    weder der vorhandene Deployment-Default noch dessen Backupstruktur
    veraendert werden.
    """
    if not publish_latest:
        return None

    latest_dir = os.path.join(out_base, "latest")
    if os.path.exists(latest_dir):
        backup_dir = os.path.join(out_base, "versions", f"{timestamp}_backup_prev_latest")
        safe_replace_dir(latest_dir, backup_dir)

    stale_latest_dir = os.path.join(out_base, "versions", f"{timestamp}_stale_prev_latest_dir")
    safe_replace_dir(ver_dir, latest_dir, rename_existing_to=stale_latest_dir)
    return latest_dir


def validate_input_data(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    group_col: str | None = None,
) -> None:
    """Prueft den VGR-Datensatz gegen den aktuellen Prozessfeature-Vertrag."""
    required_cols = ["split", label_col, *feature_cols]
    if group_col:
        required_cols.append(group_col)

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    forbidden_features = {"split", label_col}
    if group_col:
        forbidden_features.add(group_col)

    overlap = sorted(forbidden_features.intersection(feature_cols))
    if overlap:
        raise ValueError(f"Feature columns must not include metadata/label columns: {overlap}")

    forbidden_prefix_features = [
        col
        for col in feature_cols
        if col.startswith("ctx_")
        or col.startswith("storage_slot_")
        or col.startswith("prev_")
        or (col.startswith("IX_SSC_") and col != START_SIGNAL_COL)
        or col.startswith("IW_SSC_")
        or col.startswith("IW_SLD_")
    ]
    if forbidden_prefix_features:
        # Lager- und Kontextzustand sollen nicht doppelt im Modell auftauchen:
        # `empty_storage_0..9` ist die einzige explizite Lagerinformation.
        raise ValueError(
            "VGR feature columns must not include ctx_*, storage_slot_*, prev_*, "
            "SSC or SLD columns except IX_SSC_LightBarrierStorage_I3 as the "
            "explicit start signal; use empty_storage_0..9 as the only explicit "
            f"storage-state feature: {forbidden_prefix_features}"
        )

    storage_cols = [f"empty_storage_{idx}" for idx in range(10)]
    missing_storage_cols = [col for col in storage_cols if col not in feature_cols]
    if missing_storage_cols:
        raise ValueError(f"VGR feature columns must contain empty_storage_0..9: {missing_storage_cols}")
    if "empty_storage" in feature_cols:
        raise ValueError("VGR feature columns must not contain numeric empty_storage.")

    na_counts = df[required_cols].isna().sum()
    na_counts = na_counts[na_counts > 0].to_dict()
    if na_counts:
        raise ValueError(f"CSV contains NaN values in model-relevant columns: {na_counts}")

    non_numeric = [
        col for col in feature_cols if not pd.api.types.is_numeric_dtype(df[col])
    ]
    if non_numeric:
        raise ValueError(f"Feature columns must be numeric: {non_numeric}")

    split_values = set(df["split"].astype(str))
    if split_values != {"train", "test"}:
        raise ValueError(f"Expected split values {{'train', 'test'}}, got {sorted(split_values)}")

    if group_col and df[group_col].isna().any():
        raise ValueError(f"group_col {group_col!r} contains NaN values.")


def evaluate_model(
    model: tf.keras.Model,
    X: np.ndarray,
    y_idx: np.ndarray,
    class_ids: list[int],
) -> dict[str, Any]:
    """Berechnet Standardmetriken auf echten Befehlslabels statt Dense-Indizes."""
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
    present_weights = compute_class_weight(
        class_weight="balanced",
        classes=present_classes,
        y=y,
    )
    class_weight = {idx: 1.0 for idx in range(n_classes)}
    class_weight.update(
        {int(idx): float(weight) for idx, weight in zip(present_classes, present_weights)}
    )
    return class_weight


def make_window_metadata(groups: np.ndarray, y_ids: np.ndarray) -> dict[str, Any]:
    """Verdichtet Fensteranzahl, Gruppen und Labelverteilung fuer `metrics.json`."""
    return {
        "window_count": int(len(y_ids)),
        "group_count": int(len(set(groups.astype(str)))) if len(groups) else 0,
        "groups": sorted(set(groups.astype(str))) if len(groups) else [],
        "label_counts": label_counts(y_ids),
    }


def iter_group_cv_splits(
    groups: np.ndarray,
    strategy: str,
    n_splits: int,
) -> list[tuple[np.ndarray, np.ndarray, str]]:
    """Erzeugt gruppierte CV-Splits fuer eine diagnostische Robustheitspruefung."""
    unique_groups = np.array(sorted(set(groups.astype(str))), dtype=object)
    if len(unique_groups) < 2:
        return []

    if strategy == "group_kfold":
        effective_splits = min(max(2, int(n_splits)), len(unique_groups))
        splitter = GroupKFold(n_splits=effective_splits)
        return [
            (train_idx, val_idx, f"group_kfold_{fold_idx}")
            for fold_idx, (train_idx, val_idx) in enumerate(
                splitter.split(np.zeros(len(groups)), groups=groups),
                start=1,
            )
        ]

    splitter = LeaveOneGroupOut()
    return [
        (train_idx, val_idx, f"leave_one_group_out_{fold_idx}")
        for fold_idx, (train_idx, val_idx) in enumerate(
            splitter.split(np.zeros(len(groups)), groups=groups),
            start=1,
        )
    ]


def run_group_cross_validation(
    *,
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    class_ids: list[int],
    time_steps: int,
    n_features: int,
    lstm_units: int,
    dense_units: int,
    dropout: float,
    learning_rate: float,
    l2_value: float,
    batch_size: int,
    epochs: int,
    patience: int,
    use_class_weight: bool,
    seed: int,
    strategy: str,
    n_splits: int,
) -> dict[str, Any]:
    """Trainiert Diagnose-Folds, ohne den separaten Test-Holdout anzutasten."""
    fold_results = []
    fold_splits = iter_group_cv_splits(groups, strategy, n_splits)

    for fold_idx, (train_idx, val_idx, fold_name) in enumerate(fold_splits, start=1):
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(seed + fold_idx)

        X_fold_train = X[train_idx]
        y_fold_train = y[train_idx]
        X_fold_val = X[val_idx]
        y_fold_val = y[val_idx]

        normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
        normalizer.adapt(X_fold_train)
        model = build_model(
            time_steps=time_steps,
            n_features=n_features,
            n_classes=len(class_ids),
            normalizer=normalizer,
            lstm_units=lstm_units,
            dense_units=dense_units,
            dropout=dropout,
            learning_rate=learning_rate,
            l2_value=l2_value,
        )

        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=patience,
                restore_best_weights=True,
            )
        ]
        class_weight = (
            compute_balanced_class_weight(y_fold_train, len(class_ids))
            if use_class_weight
            else None
        )
        history = model.fit(
            X_fold_train,
            y_fold_train,
            validation_data=(X_fold_val, y_fold_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            class_weight=class_weight,
            verbose=0,
        )
        metrics = evaluate_model(model, X_fold_val, y_fold_val, class_ids)
        fold_results.append(
            {
                "fold": int(fold_idx),
                "fold_name": fold_name,
                "train_groups": sorted(set(groups[train_idx].astype(str))),
                "validation_groups": sorted(set(groups[val_idx].astype(str))),
                "train_windows": int(len(train_idx)),
                "validation_windows": int(len(val_idx)),
                "train_label_counts": label_counts(np.array(class_ids, dtype=np.int32)[y_fold_train]),
                "validation_label_counts": label_counts(np.array(class_ids, dtype=np.int32)[y_fold_val]),
                "epochs_ran": int(len(history.history.get("loss", []))),
                "metrics": metrics,
            }
        )

    if not fold_results:
        return {
            "enabled": True,
            "strategy": strategy,
            "folds": [],
            "summary": {},
            "warning": "Not enough groups for grouped cross-validation.",
        }

    summary: dict[str, Any] = {}
    for metric_name in ["accuracy", "balanced_accuracy", "macro_f1"]:
        values = [
            float(result["metrics"][metric_name])
            for result in fold_results
            if result["metrics"].get(metric_name) is not None
        ]
        summary[metric_name] = {
            "mean": float(np.mean(values)) if values else None,
            "std": float(np.std(values)) if values else None,
            "min": float(np.min(values)) if values else None,
            "max": float(np.max(values)) if values else None,
        }

    return {
        "enabled": True,
        "strategy": strategy,
        "n_splits": int(len(fold_results)),
        "folds": fold_results,
        "summary": summary,
        "interpretation_note": (
            "Grouped CV uses only train sequence_id groups and is a diagnostic "
            "robustness check. The configured test split remains the holdout."
        ),
    }


def label_counts(labels: np.ndarray) -> dict[str, int]:
    """Gibt Labelverteilungen JSON-freundlich mit String-Keys zurueck."""
    values, counts = np.unique(labels, return_counts=True)
    return {str(int(v)): int(c) for v, c in zip(values, counts)}


def main() -> None:
    """Fuehrt den VGR-Trainingslauf aus und schreibt Modell, Activation und Metriken."""
    require_tensorflow()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    seed = int(cfg.get("seed", 42))
    np.random.seed(seed)
    tf.random.set_seed(seed)
    tf.keras.utils.set_random_seed(seed)

    csv_path = cfg["csv_path"]
    label_col = cfg["label_col"]
    feature_cols = list(cfg["feature_cols"])
    time_steps = int(cfg["time_steps"])
    domain = cfg["domain"]
    group_col = cfg.get("group_col")
    group_col = str(group_col) if group_col else None

    lstm_units = int(cfg.get("lstm_units", 16))
    dense_units = int(cfg.get("dense_units", 16))
    dropout = float(cfg.get("dropout", 0.2))
    l2_value = float(cfg.get("l2", 1e-4))
    learning_rate = float(cfg.get("learning_rate", 1e-3))
    validation_fraction = float(cfg.get("validation_fraction", 0.2))
    validation_mode = str(
        cfg.get("validation_mode", "group_holdout" if group_col else "random_window")
    )
    epochs = int(cfg.get("epochs", 100))
    batch_size = int(cfg.get("batch_size", 16))
    patience = int(cfg.get("patience", 10))
    use_class_weight = bool(cfg.get("use_class_weight", True))
    publish_latest = bool(cfg.get("publish_latest", True))
    experiment_name = str(cfg.get("experiment_name", "default"))

    df = pd.read_csv(csv_path)
    validate_input_data(df, feature_cols, label_col, group_col=group_col)

    class_ids = [int(v) for v in cfg.get("class_ids", sorted(df[label_col].astype(int).unique()))]
    missing_labels = sorted(set(df[label_col].astype(int)) - set(class_ids))
    if missing_labels:
        raise ValueError(f"class_ids do not cover labels present in CSV: {missing_labels}")
    # Das Modell lernt dichte Indizes, aber Activation und MQTT muessen spaeter
    # wieder die echten Befehlslabels wie 101 oder 105 zurueckgeben.
    class_to_index = {class_id: idx for idx, class_id in enumerate(class_ids)}

    df_train = df[df["split"] == "train"].copy()
    df_test = df[df["split"] == "test"].copy()

    if group_col:
        # `sequence_id` ist kein Feature, sondern eine harte Fenstergrenze. So
        # entstehen keine LSTM-Fenster ueber kuenstliche Storage-Reset-Grenzen.
        X_train_all, y_train_all, y_train_ids_all, train_window_groups = make_windows_label_last_grouped(
            df_train,
            feature_cols,
            label_col,
            time_steps,
            class_to_index,
            group_col=group_col,
        )
        X_test, y_test, y_test_ids, test_window_groups = make_windows_label_last_grouped(
            df_test,
            feature_cols,
            label_col,
            time_steps,
            class_to_index,
            group_col=group_col,
        )
        windowing_mode = "split_group_label_last"
    else:
        X_train_all, y_train_all, y_train_ids_all = make_windows_label_last(
            df_train, feature_cols, label_col, time_steps, class_to_index
        )
        X_test, y_test, y_test_ids = make_windows_label_last(
            df_test, feature_cols, label_col, time_steps, class_to_index
        )
        train_window_groups = np.array(["train"] * len(y_train_all), dtype=object)
        test_window_groups = np.array(["test"] * len(y_test), dtype=object)
        windowing_mode = "split_stream_label_last"

    if len(X_train_all) == 0:
        raise ValueError("No training windows created. Check time_steps and train split length.")

    if validation_mode == "group_holdout":
        if not group_col:
            raise ValueError("validation_mode='group_holdout' requires group_col.")
        # Validation soll ganze Sequenzen zurueckhalten. Ein zufaelliger
        # Fenstersplit waere bei stark ueberlappenden Fenstern zu optimistisch.
        X_fit, X_val, y_fit, y_val, fit_groups, val_groups = train_validation_split_by_group(
            X_train_all,
            y_train_all,
            train_window_groups,
            validation_fraction=validation_fraction,
            seed=seed,
        )
    else:
        X_fit, X_val, y_fit, y_val = train_validation_split(
            X_train_all,
            y_train_all,
            validation_fraction=validation_fraction,
            seed=seed,
        )
        fit_groups = np.array(["random_window_fit"] * len(y_fit), dtype=object)
        val_groups = np.array(["random_window_validation"] * len(y_val), dtype=object)

    normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(X_fit)

    model = build_model(
        time_steps=time_steps,
        n_features=len(feature_cols),
        n_classes=len(class_ids),
        normalizer=normalizer,
        lstm_units=lstm_units,
        dense_units=dense_units,
        dropout=dropout,
        learning_rate=learning_rate,
        l2_value=l2_value,
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss" if len(X_val) else "loss",
            patience=patience,
            restore_best_weights=True,
        )
    ]

    class_weight = None
    if use_class_weight:
        # Die aktiven VGR-Klassen sind ungleich verteilt; Class Weights halten
        # seltene Start-/Uebergangsklassen im Training sichtbar.
        class_weight = compute_balanced_class_weight(y_fit, len(class_ids))

    fit_kwargs: dict[str, Any] = {
        "epochs": epochs,
        "batch_size": batch_size,
        "callbacks": callbacks,
        "verbose": 2,
        "class_weight": class_weight,
    }
    if len(X_val):
        fit_kwargs["validation_data"] = (X_val, y_val)

    history = model.fit(X_fit, y_fit, **fit_kwargs)

    train_metrics = evaluate_model(model, X_train_all, y_train_all, class_ids)
    test_metrics = evaluate_model(model, X_test, y_test, class_ids)

    ts = time.strftime("%Y-%m-%d_%H%M%S")
    registry_root = cfg.get("model_registry_root", "/model_registry")
    out_base = os.path.join(registry_root, domain)
    ver_dir = os.path.join(out_base, "versions", ts)
    os.makedirs(ver_dir, exist_ok=True)

    model_path = os.path.join(ver_dir, "model.keras")
    model.save(model_path)

    architecture = {
        "input_shape": [time_steps, len(feature_cols)],
        "normalization": "keras.layers.Normalization(axis=-1), adapted on train-fit windows",
        "lstm_units": lstm_units,
        "dense_units": dense_units,
        "dropout": dropout,
        "l2": l2_value,
        "output_units": len(class_ids),
        "optimizer": "Adam",
        "learning_rate": learning_rate,
        "loss": "sparse_categorical_crossentropy",
        "parameter_counts": model_param_counts(model),
    }

    act_meta = {
        "domain": domain,
        "time_steps": time_steps,
        "feature_cols": feature_cols,
        "label_col": label_col,
        "group_col": group_col,
        "class_ids": class_ids,
        "label_encoding": "dense_class_ids",
        "n_classes": len(class_ids),
        "architecture": architecture,
        "trained_at": ts,
    }

    activation = dict(act_meta)
    base_path = cfg.get("activation_base_path")

    if base_path:
        with open(base_path, "r", encoding="utf-8") as f:
            base = json.load(f)

        base["cmd_map"] = {str(k): v for k, v in base.get("cmd_map", {}).items()}
        for class_id in class_ids:
            base["cmd_map"].setdefault(str(class_id), f"cmd_{class_id}")
        # Die Base-Activation liefert stabile Befehlsnamen; der Trainingslauf
        # schreibt den konkret gelernten Feature- und Klassenvertrag dazu.
        base.update(act_meta)
        activation = base

    with open(os.path.join(ver_dir, "activation.json"), "w", encoding="utf-8") as f:
        json.dump(activation, f, indent=2)

    cv_cfg = cfg.get("cross_validation", {})
    if isinstance(cv_cfg, bool):
        cv_cfg = {"enabled": cv_cfg}
    cv_enabled = bool(cv_cfg.get("enabled", False))
    if cv_enabled:
        if not group_col:
            raise ValueError("cross_validation.enabled requires group_col.")
        # CV laeuft nur auf Train-Gruppen. Der Testsplit bleibt der Holdout fuer
        # die abschliessende Bewertung.
        cross_validation = run_group_cross_validation(
            X=X_train_all,
            y=y_train_all,
            groups=train_window_groups,
            class_ids=class_ids,
            time_steps=time_steps,
            n_features=len(feature_cols),
            lstm_units=lstm_units,
            dense_units=dense_units,
            dropout=dropout,
            learning_rate=learning_rate,
            l2_value=l2_value,
            batch_size=int(cv_cfg.get("batch_size", batch_size)),
            epochs=int(cv_cfg.get("epochs", min(epochs, 50))),
            patience=int(cv_cfg.get("patience", min(patience, 5))),
            use_class_weight=use_class_weight,
            seed=seed,
            strategy=str(cv_cfg.get("strategy", "leave_one_group_out")),
            n_splits=int(cv_cfg.get("n_splits", 5)),
        )
    else:
        cross_validation = {"enabled": False}

    metrics = {
        "provenance": {
            "experiment_name": experiment_name,
            "publish_latest": publish_latest,
            "config_path": args.config,
            "config_sha256": sha256_file(args.config),
            "dataset_sha256": sha256_file(csv_path),
            "model_sha256": sha256_file(model_path),
        },
        "dataset": {
            "csv_path": csv_path,
            "rows": int(len(df)),
            "feature_count": len(feature_cols),
            "group_col": group_col,
            "row_label_counts": label_counts(df[label_col].astype(int).to_numpy()),
            "split_row_counts": {str(k): int(v) for k, v in df["split"].value_counts().to_dict().items()},
            "split_group_counts": (
                {
                    str(split): int(count)
                    for split, count in df.groupby("split")[group_col].nunique().to_dict().items()
                }
                if group_col
                else None
            ),
        },
        "windowing": {
            "mode": windowing_mode,
            "time_steps": time_steps,
            "group_col": group_col,
            "train_windows": int(len(X_train_all)),
            "train_fit_windows": int(len(X_fit)),
            "validation_windows": int(len(X_val)),
            "test_windows": int(len(X_test)),
            "train_window_label_counts": label_counts(y_train_ids_all),
            "test_window_label_counts": label_counts(y_test_ids),
            "train_window_groups": make_window_metadata(train_window_groups, y_train_ids_all),
            "fit_window_groups": make_window_metadata(fit_groups, np.array(class_ids, dtype=np.int32)[y_fit]),
            "validation_window_groups": make_window_metadata(val_groups, np.array(class_ids, dtype=np.int32)[y_val]),
            "test_window_groups": make_window_metadata(test_window_groups, y_test_ids),
        },
        "training": {
            "seed": seed,
            "epochs_configured": epochs,
            "epochs_ran": int(len(history.history.get("loss", []))),
            "batch_size": batch_size,
            "validation_fraction": validation_fraction,
            "validation_mode": validation_mode,
            "class_weight": {str(k): float(v) for k, v in class_weight.items()} if class_weight else None,
            "history": {k: [float(v) for v in values] for k, values in history.history.items()},
        },
        "architecture": architecture,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "cross_validation": cross_validation,
    }

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
    print(f"[OK] Train windows: {len(X_train_all)} | Test windows: {len(X_test)}")
    if group_col:
        print(f"[OK] Window groups: {group_col}")
        print(f"[OK] Validation groups: {sorted(set(val_groups.astype(str))) if len(val_groups) else []}")
    if cross_validation.get("enabled"):
        print(f"[OK] Group CV folds: {cross_validation.get('n_splits', 0)}")
    print(f"[OK] Test accuracy: {test_metrics.get('accuracy')}")
    print(f"[OK] Test balanced accuracy: {test_metrics.get('balanced_accuracy')}")
    print(f"[OK] Test macro F1: {test_metrics.get('macro_f1')}")


if __name__ == "__main__":
    main()
