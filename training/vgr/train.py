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
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, train_test_split

from training import lstm_common

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
    """Kompatibler VGR-Einstieg fuer den gemeinsamen Windowing-Helfer."""
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
    """Kompatibler VGR-Einstieg fuer gruppiertes Windowing."""
    return lstm_common.make_windows_label_last_grouped(
        df_split, feature_cols, label_col, time_steps, class_to_index, group_col
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
    """Kompatibler VGR-Einstieg fuer den gemeinsamen Gruppen-Split."""
    return lstm_common.train_validation_split_by_group(
        X, y, groups, validation_fraction, seed
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
    return lstm_common.model_param_counts(model)


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
    validate_required_columns(df, required_cols)
    validate_vgr_feature_names(feature_cols, label_col, group_col)
    validate_vgr_storage_contract(feature_cols)
    validate_vgr_values(df, required_cols, feature_cols, group_col)


def validate_required_columns(df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")


def validate_vgr_feature_names(
    feature_cols: list[str], label_col: str, group_col: str | None
) -> None:
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
        raise ValueError(
            "VGR feature columns must not include ctx_*, storage_slot_*, prev_*, "
            "SSC or SLD columns except IX_SSC_LightBarrierStorage_I3 as the "
            "explicit start signal; use empty_storage_0..9 as the only explicit "
            f"storage-state feature: {forbidden_prefix_features}"
        )


def validate_vgr_storage_contract(feature_cols: list[str]) -> None:
    storage_cols = [f"empty_storage_{idx}" for idx in range(10)]
    missing_storage_cols = [col for col in storage_cols if col not in feature_cols]
    if missing_storage_cols:
        raise ValueError(f"VGR feature columns must contain empty_storage_0..9: {missing_storage_cols}")
    if "empty_storage" in feature_cols:
        raise ValueError("VGR feature columns must not contain numeric empty_storage.")


def validate_vgr_values(
    df: pd.DataFrame,
    required_cols: list[str],
    feature_cols: list[str],
    group_col: str | None,
) -> None:
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
    return lstm_common.evaluate_model(model, X, y_idx, class_ids)


def compute_balanced_class_weight(y: np.ndarray, n_classes: int) -> dict[int, float]:
    return lstm_common.compute_balanced_class_weight(y, n_classes)


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


def train_cv_fold(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray, class_ids: list[int],
    train_idx: np.ndarray, val_idx: np.ndarray, fold_idx: int, fold_name: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Trainiert und beschreibt genau einen gruppierten CV-Fold."""
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(settings["seed"] + fold_idx)
    train_x, train_y = X[train_idx], y[train_idx]
    val_x, val_y = X[val_idx], y[val_idx]
    normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(train_x)
    model = build_model(
        time_steps=settings["time_steps"], n_features=settings["n_features"],
        n_classes=len(class_ids), normalizer=normalizer,
        lstm_units=settings["lstm_units"], dense_units=settings["dense_units"],
        dropout=settings["dropout"], learning_rate=settings["learning_rate"],
        l2_value=settings["l2_value"],
    )
    callback = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=settings["patience"], restore_best_weights=True
    )
    class_weight = None
    if settings["use_class_weight"]:
        class_weight = compute_balanced_class_weight(train_y, len(class_ids))
    history = model.fit(
        train_x, train_y, validation_data=(val_x, val_y),
        epochs=settings["epochs"], batch_size=settings["batch_size"],
        callbacks=[callback], class_weight=class_weight, verbose=0,
    )
    class_array = np.array(class_ids, dtype=np.int32)
    return {
        "fold": int(fold_idx), "fold_name": fold_name,
        "train_groups": sorted(set(groups[train_idx].astype(str))),
        "validation_groups": sorted(set(groups[val_idx].astype(str))),
        "train_windows": int(len(train_idx)), "validation_windows": int(len(val_idx)),
        "train_label_counts": label_counts(class_array[train_y]),
        "validation_label_counts": label_counts(class_array[val_y]),
        "epochs_ran": int(len(history.history.get("loss", []))),
        "metrics": evaluate_model(model, val_x, val_y, class_ids),
    }


def summarize_cv(fold_results: list[dict[str, Any]]) -> dict[str, Any]:
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
    return summary


def run_group_cross_validation(
    *, X: np.ndarray, y: np.ndarray, groups: np.ndarray, class_ids: list[int],
    time_steps: int, n_features: int, lstm_units: int, dense_units: int,
    dropout: float, learning_rate: float, l2_value: float, batch_size: int,
    epochs: int, patience: int, use_class_weight: bool, seed: int,
    strategy: str, n_splits: int,
) -> dict[str, Any]:
    """Trainiert Diagnose-Folds, ohne den separaten Test-Holdout anzutasten."""
    settings = {
        "time_steps": time_steps, "n_features": n_features,
        "lstm_units": lstm_units, "dense_units": dense_units,
        "dropout": dropout, "learning_rate": learning_rate,
        "l2_value": l2_value, "batch_size": batch_size, "epochs": epochs,
        "patience": patience, "use_class_weight": use_class_weight, "seed": seed,
    }
    splits = iter_group_cv_splits(groups, strategy, n_splits)
    folds = [
        train_cv_fold(X, y, groups, class_ids, train_idx, val_idx, index, name, settings)
        for index, (train_idx, val_idx, name) in enumerate(splits, start=1)
    ]
    if not folds:
        return {
            "enabled": True, "strategy": strategy, "folds": [], "summary": {},
            "warning": "Not enough groups for grouped cross-validation.",
        }

    return {
        "enabled": True,
        "strategy": strategy,
        "n_splits": int(len(folds)),
        "folds": folds,
        "summary": summarize_cv(folds),
        "interpretation_note": (
            "Grouped CV uses only train sequence_id groups and is a diagnostic "
            "robustness check. The configured test split remains the holdout."
        ),
    }


def label_counts(labels: np.ndarray) -> dict[str, int]:
    return lstm_common.label_counts(labels)


def load_training_config() -> tuple[str, dict[str, Any]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        return args.config, json.load(handle)


def vgr_settings(cfg: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    group_value = cfg.get("group_col")
    group_col = str(group_value) if group_value else None
    labels = sorted(frame[cfg["label_col"]].astype(int).unique())
    classes = [int(value) for value in cfg.get("class_ids", labels)]
    missing_labels = sorted(set(labels) - set(classes))
    if missing_labels:
        raise ValueError(f"class_ids do not cover labels present in CSV: {missing_labels}")
    return {
        "seed": int(cfg.get("seed", 42)), "csv_path": cfg["csv_path"],
        "label_col": cfg["label_col"], "feature_cols": list(cfg["feature_cols"]),
        "time_steps": int(cfg["time_steps"]), "domain": cfg["domain"],
        "group_col": group_col, "class_ids": classes,
        "class_to_index": {value: index for index, value in enumerate(classes)},
        "lstm_units": int(cfg.get("lstm_units", 16)),
        "dense_units": int(cfg.get("dense_units", 16)),
        "dropout": float(cfg.get("dropout", 0.2)), "l2": float(cfg.get("l2", 1e-4)),
        "learning_rate": float(cfg.get("learning_rate", 1e-3)),
        "validation_fraction": float(cfg.get("validation_fraction", 0.2)),
        "validation_mode": str(cfg.get("validation_mode", "group_holdout" if group_col else "random_window")),
        "epochs": int(cfg.get("epochs", 100)), "batch_size": int(cfg.get("batch_size", 16)),
        "patience": int(cfg.get("patience", 10)),
        "use_class_weight": bool(cfg.get("use_class_weight", True)),
        "publish_latest": bool(cfg.get("publish_latest", True)),
        "experiment_name": str(cfg.get("experiment_name", "default")),
    }


def set_random_seed(seed: int) -> None:
    np.random.seed(seed)
    tf.random.set_seed(seed)
    tf.keras.utils.set_random_seed(seed)


def build_vgr_windows(frame: pd.DataFrame, settings: dict[str, Any]) -> dict[str, Any]:
    train = frame[frame["split"] == "train"].copy()
    test = frame[frame["split"] == "test"].copy()
    common = (
        settings["feature_cols"], settings["label_col"], settings["time_steps"],
        settings["class_to_index"],
    )
    if settings["group_col"]:
        train_values = make_windows_label_last_grouped(
            train, *common, group_col=settings["group_col"]
        )
        test_values = make_windows_label_last_grouped(
            test, *common, group_col=settings["group_col"]
        )
        windowing_mode = "split_group_label_last"
    else:
        train_basic = make_windows_label_last(train, *common)
        test_basic = make_windows_label_last(test, *common)
        train_values = (*train_basic, np.array(["train"] * len(train_basic[1]), dtype=object))
        test_values = (*test_basic, np.array(["test"] * len(test_basic[1]), dtype=object))
        windowing_mode = "split_stream_label_last"
    train_x, train_y, train_ids, train_groups = train_values
    test_x, test_y, test_ids, test_groups = test_values
    if len(train_x) == 0:
        raise ValueError("No training windows created. Check time_steps and train split length.")
    return {
        "train_x": train_x, "train_y": train_y, "train_ids": train_ids,
        "train_groups": train_groups, "test_x": test_x, "test_y": test_y,
        "test_ids": test_ids, "test_groups": test_groups, "windowing_mode": windowing_mode,
    }


def add_validation_split(data: dict[str, Any], settings: dict[str, Any]) -> None:
    if settings["validation_mode"] == "group_holdout":
        if not settings["group_col"]:
            raise ValueError("validation_mode='group_holdout' requires group_col.")
        values = train_validation_split_by_group(
            data["train_x"], data["train_y"], data["train_groups"],
            validation_fraction=settings["validation_fraction"], seed=settings["seed"],
        )
    else:
        split = train_validation_split(
            data["train_x"], data["train_y"],
            validation_fraction=settings["validation_fraction"], seed=settings["seed"],
        )
        fit_x, val_x, fit_y, val_y = split
        values = (
            fit_x, val_x, fit_y, val_y,
            np.array(["random_window_fit"] * len(fit_y), dtype=object),
            np.array(["random_window_validation"] * len(val_y), dtype=object),
        )
    keys = ("fit_x", "val_x", "fit_y", "val_y", "fit_groups", "val_groups")
    data.update(dict(zip(keys, values)))


def train_vgr_model(settings: dict[str, Any], data: dict[str, Any]) -> tuple[Any, Any, Any]:
    normalizer = tf.keras.layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(data["fit_x"])
    model = build_model(
        time_steps=settings["time_steps"], n_features=len(settings["feature_cols"]),
        n_classes=len(settings["class_ids"]), normalizer=normalizer,
        lstm_units=settings["lstm_units"], dense_units=settings["dense_units"],
        dropout=settings["dropout"], learning_rate=settings["learning_rate"],
        l2_value=settings["l2"],
    )
    callback = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss" if len(data["val_x"]) else "loss",
        patience=settings["patience"], restore_best_weights=True,
    )
    class_weight = None
    if settings["use_class_weight"]:
        class_weight = compute_balanced_class_weight(data["fit_y"], len(settings["class_ids"]))
    fit_kwargs: dict[str, Any] = {
        "epochs": settings["epochs"], "batch_size": settings["batch_size"],
        "callbacks": [callback], "verbose": 2, "class_weight": class_weight,
    }
    if len(data["val_x"]):
        fit_kwargs["validation_data"] = (data["val_x"], data["val_y"])
    return model, model.fit(data["fit_x"], data["fit_y"], **fit_kwargs), class_weight


def vgr_architecture(model: Any, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_shape": [settings["time_steps"], len(settings["feature_cols"])],
        "normalization": "keras.layers.Normalization(axis=-1), adapted on train-fit windows",
        "lstm_units": settings["lstm_units"], "dense_units": settings["dense_units"],
        "dropout": settings["dropout"], "l2": settings["l2"],
        "output_units": len(settings["class_ids"]), "optimizer": "Adam",
        "learning_rate": settings["learning_rate"], "loss": "sparse_categorical_crossentropy",
        "parameter_counts": model_param_counts(model),
    }


def vgr_activation(
    cfg: dict[str, Any], settings: dict[str, Any], architecture: dict[str, Any], timestamp: str
) -> dict[str, Any]:
    metadata = {
        "domain": settings["domain"], "time_steps": settings["time_steps"],
        "feature_cols": settings["feature_cols"], "label_col": settings["label_col"],
        "group_col": settings["group_col"], "class_ids": settings["class_ids"],
        "label_encoding": "dense_class_ids", "n_classes": len(settings["class_ids"]),
        "architecture": architecture, "trained_at": timestamp,
    }
    base_path = cfg.get("activation_base_path")
    if not base_path:
        return metadata
    with open(base_path, "r", encoding="utf-8") as handle:
        activation = json.load(handle)
    activation["cmd_map"] = {str(key): value for key, value in activation.get("cmd_map", {}).items()}
    for class_id in settings["class_ids"]:
        activation["cmd_map"].setdefault(str(class_id), f"cmd_{class_id}")
    activation.update(metadata)
    return activation


def vgr_cross_validation(
    cfg: dict[str, Any], settings: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    cv_cfg = cfg.get("cross_validation", {})
    if isinstance(cv_cfg, bool):
        cv_cfg = {"enabled": cv_cfg}
    if not bool(cv_cfg.get("enabled", False)):
        return {"enabled": False}
    if not settings["group_col"]:
        raise ValueError("cross_validation.enabled requires group_col.")
    return run_group_cross_validation(
        X=data["train_x"], y=data["train_y"], groups=data["train_groups"],
        class_ids=settings["class_ids"], time_steps=settings["time_steps"],
        n_features=len(settings["feature_cols"]), lstm_units=settings["lstm_units"],
        dense_units=settings["dense_units"], dropout=settings["dropout"],
        learning_rate=settings["learning_rate"], l2_value=settings["l2"],
        batch_size=int(cv_cfg.get("batch_size", settings["batch_size"])),
        epochs=int(cv_cfg.get("epochs", min(settings["epochs"], 50))),
        patience=int(cv_cfg.get("patience", min(settings["patience"], 5))),
        use_class_weight=settings["use_class_weight"], seed=settings["seed"],
        strategy=str(cv_cfg.get("strategy", "leave_one_group_out")),
        n_splits=int(cv_cfg.get("n_splits", 5)),
    )


def vgr_dataset_metadata(frame: pd.DataFrame, settings: dict[str, Any]) -> dict[str, Any]:
    group_col = settings["group_col"]
    group_counts = None
    if group_col:
        group_counts = {
            str(split): int(count)
            for split, count in frame.groupby("split")[group_col].nunique().to_dict().items()
        }
    return {
        "csv_path": settings["csv_path"], "rows": int(len(frame)),
        "feature_count": len(settings["feature_cols"]), "group_col": group_col,
        "row_label_counts": label_counts(frame[settings["label_col"]].astype(int).to_numpy()),
        "split_row_counts": {str(key): int(value) for key, value in frame["split"].value_counts().to_dict().items()},
        "split_group_counts": group_counts,
    }


def vgr_window_metadata(data: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    class_array = np.array(settings["class_ids"], dtype=np.int32)
    return {
        "mode": data["windowing_mode"], "time_steps": settings["time_steps"],
        "group_col": settings["group_col"], "train_windows": int(len(data["train_x"])),
        "train_fit_windows": int(len(data["fit_x"])), "validation_windows": int(len(data["val_x"])),
        "test_windows": int(len(data["test_x"])),
        "train_window_label_counts": label_counts(data["train_ids"]),
        "test_window_label_counts": label_counts(data["test_ids"]),
        "train_window_groups": make_window_metadata(data["train_groups"], data["train_ids"]),
        "fit_window_groups": make_window_metadata(data["fit_groups"], class_array[data["fit_y"]]),
        "validation_window_groups": make_window_metadata(data["val_groups"], class_array[data["val_y"]]),
        "test_window_groups": make_window_metadata(data["test_groups"], data["test_ids"]),
    }


def vgr_metrics(
    config_path: str, frame: pd.DataFrame, settings: dict[str, Any], data: dict[str, Any],
    model: Any, model_path: str, history: Any, class_weight: Any,
    architecture: dict[str, Any], cross_validation: dict[str, Any]
) -> dict[str, Any]:
    classes = settings["class_ids"]
    return {
        "provenance": {
            "experiment_name": settings["experiment_name"], "publish_latest": settings["publish_latest"],
            "config_path": config_path, "config_sha256": sha256_file(config_path),
            "dataset_sha256": sha256_file(settings["csv_path"]), "model_sha256": sha256_file(model_path),
        },
        "dataset": vgr_dataset_metadata(frame, settings),
        "windowing": vgr_window_metadata(data, settings),
        "training": {
            "seed": settings["seed"], "epochs_configured": settings["epochs"],
            "epochs_ran": int(len(history.history.get("loss", []))),
            "batch_size": settings["batch_size"], "validation_fraction": settings["validation_fraction"],
            "validation_mode": settings["validation_mode"],
            "class_weight": {str(key): float(value) for key, value in class_weight.items()} if class_weight else None,
            "history": {key: [float(value) for value in values] for key, values in history.history.items()},
        },
        "architecture": architecture,
        "train_metrics": evaluate_model(model, data["train_x"], data["train_y"], classes),
        "test_metrics": evaluate_model(model, data["test_x"], data["test_y"], classes),
        "cross_validation": cross_validation,
    }


def save_vgr_artifacts(
    config_path: str, cfg: dict[str, Any], frame: pd.DataFrame, settings: dict[str, Any],
    data: dict[str, Any], model: Any, history: Any, class_weight: Any
) -> tuple[str, str | None, dict[str, Any]]:
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    registry_root = cfg.get("model_registry_root", "/model_registry")
    out_base = os.path.join(registry_root, settings["domain"])
    ver_dir = os.path.join(out_base, "versions", ts)
    os.makedirs(ver_dir, exist_ok=True)

    model_path = os.path.join(ver_dir, "model.keras")
    model.save(model_path)
    architecture = vgr_architecture(model, settings)
    activation = vgr_activation(cfg, settings, architecture, ts)
    cross_validation = vgr_cross_validation(cfg, settings, data)
    metrics = vgr_metrics(
        config_path, frame, settings, data, model, model_path, history,
        class_weight, architecture, cross_validation,
    )
    with open(os.path.join(ver_dir, "activation.json"), "w", encoding="utf-8") as handle:
        json.dump(activation, handle, indent=2)
    with open(os.path.join(ver_dir, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    latest_dir = finalize_model_version(ver_dir, out_base, ts, settings["publish_latest"])
    return ver_dir, latest_dir, metrics


def print_vgr_result(
    version_dir: str, latest_dir: str | None, settings: dict[str, Any],
    data: dict[str, Any], metrics: dict[str, Any]
) -> None:
    test_metrics = metrics["test_metrics"]
    cross_validation = metrics["cross_validation"]
    print(f"[OK] Saved version: {version_dir}")
    if latest_dir:
        print(f"[OK] Updated latest: {latest_dir}")
    else:
        print("[OK] Candidate mode: latest was not changed")
    print(f"[OK] Input shape: (None, {settings['time_steps']}, {len(settings['feature_cols'])})")
    print(f"[OK] Output units/classes: {len(settings['class_ids'])} / {settings['class_ids']}")
    print(f"[OK] Train windows: {len(data['train_x'])} | Test windows: {len(data['test_x'])}")
    if settings["group_col"]:
        print(f"[OK] Window groups: {settings['group_col']}")
        groups = sorted(set(data["val_groups"].astype(str))) if len(data["val_groups"]) else []
        print(f"[OK] Validation groups: {groups}")
    if cross_validation.get("enabled"):
        print(f"[OK] Group CV folds: {cross_validation.get('n_splits', 0)}")
    print(f"[OK] Test accuracy: {test_metrics.get('accuracy')}")
    print(f"[OK] Test balanced accuracy: {test_metrics.get('balanced_accuracy')}")
    print(f"[OK] Test macro F1: {test_metrics.get('macro_f1')}")


def main() -> None:
    """Fuehrt den VGR-Trainingslauf aus und schreibt Modell, Activation und Metriken."""
    require_tensorflow()
    config_path, cfg = load_training_config()
    frame = pd.read_csv(cfg["csv_path"])
    settings = vgr_settings(cfg, frame)
    set_random_seed(settings["seed"])
    validate_input_data(
        frame, settings["feature_cols"], settings["label_col"], settings["group_col"]
    )
    data = build_vgr_windows(frame, settings)
    add_validation_split(data, settings)
    model, history, class_weight = train_vgr_model(settings, data)
    version_dir, latest_dir, metrics = save_vgr_artifacts(
        config_path, cfg, frame, settings, data, model, history, class_weight
    )
    print_vgr_result(version_dir, latest_dir, settings, data, metrics)


if __name__ == "__main__":
    main()
