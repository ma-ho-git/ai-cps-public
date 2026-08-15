"""Trainiert das Storage-NN fuer den ersten freien Lagerplatz.

Das Storage-Modell ist bewusst klein gehalten: Die fachliche Regel ist
deterministisch, das Netz soll diese Regel als pipeline-kompatibler
ANN-Baustein reproduzieren. Die vollstaendige Truth Table bleibt deshalb
der harte Pruefstein, nicht nur eine zufaellige Teststichprobe.
"""

import argparse
import itertools
import json
import os
import random
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


def storage_feature_cols() -> list[str]:
    """Liefert die feste Feature-Reihenfolge fuer die neun Lagerplaetze."""
    return [f"storage_slot_{slot}_occupied" for slot in range(1, 10)]


def first_free_slot(occupancy_values: list[int]) -> int:
    """Bestimmt den ersten freien Slot; 0 steht fuer ein voll belegtes Lager."""
    if len(occupancy_values) != 9:
        raise ValueError(f"Expected 9 occupancy values, got {len(occupancy_values)}")
    for slot, occupied in enumerate(occupancy_values, start=1):
        if int(occupied) not in {0, 1}:
            raise ValueError(f"Occupancy values must be binary 0/1, got {occupied!r}")
        if int(occupied) == 0:
            return slot
    return 0


def build_truth_table(feature_cols: list[str]) -> pd.DataFrame:
    """Erzeugt alle moeglichen Belegungskombinationen als Ground Truth."""
    records: list[dict[str, int]] = []
    for occupancy_values in itertools.product([0, 1], repeat=len(feature_cols)):
        record = dict(zip(feature_cols, [int(value) for value in occupancy_values]))
        record["empty_storage"] = first_free_slot(list(occupancy_values))
        records.append(record)
    return pd.DataFrame.from_records(records)


def validate_storage_data(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    class_ids: list[int],
) -> None:
    """Prueft, ob die CSV wirklich die deterministische Storage-Aufgabe abdeckt."""
    required_cols = [*feature_cols, label_col]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Storage CSV is missing required columns: {missing}")
    if df[required_cols].isna().any().any():
        raise ValueError("Storage CSV contains NaN values in model-relevant columns.")
    if len(feature_cols) != 9:
        raise ValueError(f"Storage-NN expects 9 feature columns, got {len(feature_cols)}")
    for col in feature_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Storage feature must be numeric: {col}")
        invalid_values = sorted(set(df[col].astype(int)) - {0, 1})
        if invalid_values:
            raise ValueError(f"Storage feature {col} must be binary 0/1, got {invalid_values}")
    labels = sorted(df[label_col].astype(int).unique().tolist())
    if labels != class_ids:
        raise ValueError(f"Expected labels {class_ids}, got {labels}")
    if df[feature_cols].drop_duplicates().shape[0] != 512:
        raise ValueError("Storage CSV must contain all 512 unique occupancy combinations.")

    rule_labels = df[feature_cols].apply(lambda row: first_free_slot(row.astype(int).tolist()), axis=1)
    if not (rule_labels.astype(int) == df[label_col].astype(int)).all():
        raise ValueError("Storage labels do not match the deterministic first-free-slot rule.")


def make_balanced_training_data(
    X: np.ndarray,
    y: np.ndarray,
    class_ids: list[int],
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Balanciert nur das Fit-Material; bewertet wird weiter auf der Truth Table."""
    rng = np.random.default_rng(seed)
    counts = np.bincount(y.astype(int), minlength=max(class_ids) + 1)
    target_per_class = int(max(counts[class_id] for class_id in class_ids))
    sampled_indices: list[int] = []
    for class_id in class_ids:
        indices = np.where(y.astype(int) == class_id)[0]
        if len(indices) == 0:
            raise ValueError(f"Missing class {class_id} in training data.")
        sampled = rng.choice(indices, size=target_per_class, replace=True)
        sampled_indices.extend(sampled.astype(int).tolist())
    sampled_indices_arr = np.array(sampled_indices, dtype=int)
    rng.shuffle(sampled_indices_arr)
    return X[sampled_indices_arr], y[sampled_indices_arr]


def build_model(
    *,
    n_features: int,
    n_classes: int,
    hidden_units: list[int],
    learning_rate: float,
) -> tf.keras.Model:
    """Baut das kleine MLP fuer die statische Storage-Klassifikation."""
    inp = tf.keras.Input(shape=(n_features,), name="storage_occupancy")
    x = inp
    for idx, units in enumerate(hidden_units, start=1):
        x = tf.keras.layers.Dense(int(units), activation="relu", name=f"hidden_{idx}")(x)
    out = tf.keras.layers.Dense(n_classes, activation="softmax", name="empty_storage_hat")(x)
    model = tf.keras.Model(inp, out, name="empty_storage_mlp")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def evaluate_truth_table(
    model: tf.keras.Model,
    X_truth: np.ndarray,
    y_truth: np.ndarray,
    class_ids: list[int],
) -> dict[str, Any]:
    """Bewertet das Modell auf allen 512 Belegungskombinationen."""
    proba = model.predict(X_truth, verbose=0)
    y_pred_idx = proba.argmax(axis=1)
    class_ids_arr = np.array(class_ids, dtype=np.int32)
    y_pred = class_ids_arr[y_pred_idx]
    return {
        "truth_table_accuracy": float(accuracy_score(y_truth, y_pred)),
        "truth_table_balanced_accuracy": float(balanced_accuracy_score(y_truth, y_pred)),
        "truth_table_macro_f1": float(
            f1_score(y_truth, y_pred, labels=class_ids, average="macro", zero_division=0)
        ),
        "confusion_matrix": confusion_matrix(y_truth, y_pred, labels=class_ids).tolist(),
        "classification_report": classification_report(
            y_truth, y_pred, labels=class_ids, digits=3, zero_division=0
        ),
        "classification_report_dict": classification_report(
            y_truth, y_pred, labels=class_ids, output_dict=True, zero_division=0
        ),
    }


def model_param_counts(model: tf.keras.Model) -> dict[str, int]:
    """Zaehlt Parameter fuer die spaetere wissenschaftliche Einordnung."""
    trainable = int(sum(np.prod(v.shape) for v in model.trainable_weights))
    non_trainable = int(sum(np.prod(v.shape) for v in model.non_trainable_weights))
    return {"trainable": trainable, "non_trainable": non_trainable, "total": trainable + non_trainable}


def unique_path(path: str) -> str:
    """Findet einen freien Archivpfad, ohne vorhandene Modellversionen zu ueberschreiben."""
    if not os.path.exists(path):
        return path
    idx = 1
    while os.path.exists(f"{path}_{idx}"):
        idx += 1
    return f"{path}_{idx}"


def safe_replace_dir(src_dir: str, dst_dir: str, rename_existing_to: str | None = None) -> None:
    """Ersetzt `latest` robust, auch wenn alte Docker-Artefakte Rechteprobleme machen."""
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
    """Publiziert eine Version nur auf ausdruecklichen Wunsch als ``latest``.

    Das Standardtraining arbeitet im Kandidatenmodus. Dadurch bleibt der
    laufende Deploymentstand unveraendert, bis der Kandidat separat getestet
    und mit dem Modellmanager promoviert wurde.
    """
    if not publish_latest:
        return None

    latest_dir = os.path.join(out_base, "latest")
    if os.path.exists(latest_dir):
        backup_dir = os.path.join(out_base, "versions", f"{timestamp}_backup_prev_latest")
        safe_replace_dir(latest_dir, backup_dir)
    stale_latest_dir = os.path.join(
        out_base,
        "versions",
        f"{timestamp}_stale_prev_latest_dir",
    )
    safe_replace_dir(ver_dir, latest_dir, rename_existing_to=stale_latest_dir)
    return latest_dir


def load_training_config() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        return json.load(handle)


def storage_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalisiert alle Trainingsparameter an einer Stelle."""
    return {
        "domain": str(cfg.get("domain", "storage")),
        "csv_path": str(cfg["csv_path"]),
        "label_col": str(cfg.get("label_col", "empty_storage")),
        "feature_cols": list(cfg.get("feature_cols", storage_feature_cols())),
        "class_ids": [int(value) for value in cfg.get("class_ids", list(range(10)))],
        "hidden_units": [int(value) for value in cfg.get("hidden_units", [16, 16])],
        "learning_rate": float(cfg.get("learning_rate", 1e-3)),
        "epochs": int(cfg.get("epochs", 100)),
        "batch_size": int(cfg.get("batch_size", 32)),
        "patience": int(cfg.get("patience", 10)),
        "min_delta": float(cfg.get("min_delta", 1e-6)),
        "publish_latest": bool(cfg.get("publish_latest", True)),
        "experiment_name": str(cfg.get("experiment_name", "default")),
        "seed": int(cfg.get("seed", 42)),
    }


def set_random_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)


def prepare_storage_data(settings: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_csv(settings["csv_path"])
    features = settings["feature_cols"]
    label = settings["label_col"]
    classes = settings["class_ids"]
    validate_storage_data(frame, features, label, classes)
    truth_x = frame[features].to_numpy(dtype=np.float32)
    truth_y = frame[label].astype(int).to_numpy(dtype=np.int64)
    train_x, train_y = make_balanced_training_data(
        truth_x, truth_y, classes, settings["seed"]
    )
    return {
        "frame": frame,
        "truth_x": truth_x,
        "truth_y": truth_y,
        "train_x": train_x,
        "train_y": train_y,
    }


def train_storage_model(settings: dict[str, Any], data: dict[str, Any]) -> tuple[Any, Any]:
    model = build_model(
        n_features=len(settings["feature_cols"]),
        n_classes=len(settings["class_ids"]),
        hidden_units=settings["hidden_units"],
        learning_rate=settings["learning_rate"],
    )
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="loss",
            patience=settings["patience"],
            min_delta=settings["min_delta"],
            restore_best_weights=True,
        )
    ]
    history = model.fit(
        data["train_x"],
        data["train_y"],
        epochs=settings["epochs"],
        batch_size=settings["batch_size"],
        callbacks=callbacks,
        verbose=2,
    )
    return model, history


def require_exact_truth_table(metrics: dict[str, Any]) -> None:
    if metrics["truth_table_accuracy"] != 1.0:
        raise RuntimeError("Storage-NN failed to reproduce the complete truth table exactly.")


def version_directory(cfg: dict[str, Any], settings: dict[str, Any], timestamp: str) -> tuple[str, str]:
    registry_root = cfg.get("model_registry_root", "/model_registry")
    output_base = os.path.join(registry_root, settings["domain"])
    version = os.path.join(output_base, "versions", timestamp)
    os.makedirs(version, exist_ok=True)
    return output_base, version


def storage_architecture(model: Any, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_shape": [len(settings["feature_cols"])],
        "hidden_units": settings["hidden_units"],
        "output_units": len(settings["class_ids"]),
        "optimizer": "Adam",
        "learning_rate": settings["learning_rate"],
        "loss": "sparse_categorical_crossentropy",
        "parameter_counts": model_param_counts(model),
    }


def storage_activation(
    cfg: dict[str, Any], settings: dict[str, Any], architecture: dict[str, Any], timestamp: str
) -> dict[str, Any]:
    metadata = {
        "domain": settings["domain"],
        "model_type": "mlp",
        "feature_cols": settings["feature_cols"],
        "label_col": settings["label_col"],
        "class_ids": settings["class_ids"],
        "input_shape": [len(settings["feature_cols"])],
        "n_classes": len(settings["class_ids"]),
        "architecture": architecture,
        "rule_baseline": "first slot with occupied == 0, otherwise 0 for full storage",
        "trained_at": timestamp,
    }
    base_path = cfg.get("activation_base_path")
    if not base_path:
        return metadata
    with open(base_path, "r", encoding="utf-8") as handle:
        activation = json.load(handle)
    activation["cmd_map"] = {str(key): value for key, value in activation.get("cmd_map", {}).items()}
    for class_id in settings["class_ids"]:
        activation["cmd_map"].setdefault(str(class_id), f"empty_storage_{class_id}")
    activation.update(metadata)
    return activation


def storage_metrics_payload(
    settings: dict[str, Any], data: dict[str, Any], history: Any,
    architecture: dict[str, Any], metrics: dict[str, Any]
) -> dict[str, Any]:
    frame = data["frame"]
    label_counts = {
        str(key): int(value)
        for key, value in frame[settings["label_col"]].value_counts().sort_index().to_dict().items()
    }
    return {
        "dataset": {
            "csv_path": settings["csv_path"],
            "rows": int(len(frame)),
            "feature_count": len(settings["feature_cols"]),
            "label_counts": label_counts,
        },
        "training": {
            "experiment_name": settings["experiment_name"],
            "publish_latest": settings["publish_latest"],
            "seed": settings["seed"],
            "epochs_configured": settings["epochs"],
            "epochs_ran": int(len(history.history.get("loss", []))),
            "batch_size": settings["batch_size"],
            "early_stopping_patience": settings["patience"],
            "early_stopping_min_delta": settings["min_delta"],
            "balanced_training_rows": int(len(data["train_y"])),
            "history": {key: [float(value) for value in values] for key, values in history.history.items()},
        },
        "architecture": architecture,
        **metrics,
    }


def write_json(path: str, value: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def save_storage_artifacts(
    cfg: dict[str, Any], settings: dict[str, Any], data: dict[str, Any],
    model: Any, history: Any, metrics: dict[str, Any]
) -> tuple[str, str | None]:
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    out_base, ver_dir = version_directory(cfg, settings, ts)
    model.save(os.path.join(ver_dir, "model.keras"))
    architecture = storage_architecture(model, settings)
    activation = storage_activation(cfg, settings, architecture, ts)
    payload = storage_metrics_payload(settings, data, history, architecture, metrics)
    write_json(os.path.join(ver_dir, "activation.json"), activation)
    write_json(os.path.join(ver_dir, "metrics.json"), payload)
    latest_dir = finalize_model_version(ver_dir, out_base, ts, settings["publish_latest"])
    return ver_dir, latest_dir


def print_storage_result(
    version_dir: str, latest_dir: str | None, settings: dict[str, Any], metrics: dict[str, Any]
) -> None:
    print(f"[OK] Saved version: {version_dir}")
    if latest_dir:
        print(f"[OK] Updated latest: {latest_dir}")
    else:
        print("[OK] Candidate mode: latest was not changed")
    print(f"[OK] Input shape: (None, {len(settings['feature_cols'])})")
    print(f"[OK] Output units/classes: {len(settings['class_ids'])} / {settings['class_ids']}")
    print(f"[OK] Truth-table accuracy: {metrics['truth_table_accuracy']}")
    print(f"[OK] Truth-table balanced accuracy: {metrics['truth_table_balanced_accuracy']}")
    print(f"[OK] Truth-table macro F1: {metrics['truth_table_macro_f1']}")


def main() -> None:
    """Fuehrt den Storage-Trainingslauf aus und schreibt Registry-Artefakte."""
    cfg = load_training_config()
    settings = storage_settings(cfg)
    set_random_seed(settings["seed"])
    data = prepare_storage_data(settings)
    model, history = train_storage_model(settings, data)
    metrics = evaluate_truth_table(
        model, data["truth_x"], data["truth_y"], settings["class_ids"]
    )
    require_exact_truth_table(metrics)
    version_dir, latest_dir = save_storage_artifacts(
        cfg, settings, data, model, history, metrics
    )
    print_storage_result(version_dir, latest_dir, settings, metrics)


if __name__ == "__main__":
    main()
