"""Kleine gemeinsame Helfer fuer VGR- und HBW-LSTM-Training."""

from __future__ import annotations

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
from sklearn.utils.class_weight import compute_class_weight


def make_windows_label_last(
    frame: pd.DataFrame, feature_cols: list[str], label_col: str,
    time_steps: int, class_to_index: dict[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fenster bilden; Label der letzten Zeile verwenden."""
    if len(frame) < time_steps:
        return (
            np.empty((0, time_steps, len(feature_cols)), dtype=np.float32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.int32),
        )
    values = frame[feature_cols].to_numpy(dtype=np.float32)
    labels = frame[label_col].astype(int).to_numpy()
    windows: list[np.ndarray] = []
    dense_labels: list[int] = []
    command_labels: list[int] = []
    for start in range(len(frame) - time_steps + 1):
        end = start + time_steps
        command = int(labels[end - 1])
        windows.append(values[start:end])
        dense_labels.append(class_to_index[command])
        command_labels.append(command)
    return (
        np.stack(windows).astype(np.float32),
        np.array(dense_labels, dtype=np.int32),
        np.array(command_labels, dtype=np.int32),
    )


def make_windows_label_last_grouped(
    frame: pd.DataFrame, feature_cols: list[str], label_col: str,
    time_steps: int, class_to_index: dict[int, int], group_col: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fenster nur innerhalb derselben Sequenz bilden."""
    if group_col not in frame.columns:
        raise ValueError(f"group_col {group_col!r} is missing from the CSV.")
    parts: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for group_value, group in frame.groupby(group_col, sort=False):
        windows, dense, commands = make_windows_label_last(
            group.reset_index(drop=True), feature_cols, label_col,
            time_steps, class_to_index,
        )
        if len(windows):
            groups = np.array([str(group_value)] * len(dense), dtype=object)
            parts.append((windows, dense, commands, groups))
    if not parts:
        return (
            np.empty((0, time_steps, len(feature_cols)), dtype=np.float32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.int32),
            np.array([], dtype=object),
        )
    return tuple(np.concatenate(items) for items in zip(*parts))  # type: ignore[return-value]


def train_validation_split_by_group(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    validation_fraction: float, seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Komplette Sequenzen auf Fit und Validation verteilen."""
    if validation_fraction <= 0 or len(y) < 2:
        return empty_validation_split(X, y, groups)
    unique_groups = np.array(sorted(set(groups.astype(str))), dtype=object)
    if len(unique_groups) < 2:
        return empty_validation_split(X, y, groups)
    rng = np.random.default_rng(seed)
    rng.shuffle(unique_groups)
    count = max(1, int(round(len(unique_groups) * validation_fraction)))
    count = min(count, len(unique_groups) - 1)
    validation_groups = set(unique_groups[:count])
    validation_mask = np.array(
        [str(group) in validation_groups for group in groups], dtype=bool
    )
    fit_mask = ~validation_mask
    return (
        X[fit_mask], X[validation_mask], y[fit_mask], y[validation_mask],
        groups[fit_mask], groups[validation_mask],
    )


def empty_validation_split(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return (
        X, np.empty((0,) + X.shape[1:], dtype=X.dtype),
        y, np.array([], dtype=y.dtype),
        groups, np.array([], dtype=groups.dtype),
    )


def compute_balanced_class_weight(y: np.ndarray, n_classes: int) -> dict[int, float]:
    """Im Fit vorhandene Klassen ausgleichen; fehlende Klassen neutral lassen."""
    if len(y) == 0:
        return {index: 1.0 for index in range(n_classes)}
    classes = np.unique(y)
    weights = compute_class_weight("balanced", classes=classes, y=y)
    result = {index: 1.0 for index in range(n_classes)}
    result.update({int(index): float(weight) for index, weight in zip(classes, weights)})
    return result


def evaluate_model(
    model: Any, X: np.ndarray, y_dense: np.ndarray, class_ids: list[int]
) -> dict[str, Any]:
    """Metriken mit echten Command-IDs statt Dense-Indizes berechnen."""
    if len(X) == 0:
        return {
            "accuracy": None, "balanced_accuracy": None, "macro_f1": None,
            "confusion_matrix": [], "classification_report": "",
            "classification_report_dict": {},
        }
    probabilities = model.predict(X, verbose=0)
    predicted_dense = probabilities.argmax(axis=1).astype(np.int32)
    classes = np.array(class_ids, dtype=np.int32)
    expected = classes[y_dense]
    predicted = classes[predicted_dense]
    return {
        "accuracy": float(accuracy_score(expected, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(expected, predicted)),
        "macro_f1": float(f1_score(expected, predicted, labels=class_ids, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(expected, predicted, labels=class_ids).tolist(),
        "classification_report": classification_report(
            expected, predicted, labels=class_ids, digits=3, zero_division=0
        ),
        "classification_report_dict": classification_report(
            expected, predicted, labels=class_ids, output_dict=True, zero_division=0
        ),
    }


def label_counts(values: np.ndarray) -> dict[str, int]:
    labels, counts = np.unique(values.astype(int), return_counts=True)
    return {str(int(label)): int(count) for label, count in zip(labels, counts)}


def model_param_counts(model: Any) -> dict[str, int]:
    trainable = int(sum(np.prod(value.shape) for value in model.trainable_weights))
    non_trainable = int(sum(np.prod(value.shape) for value in model.non_trainable_weights))
    return {
        "trainable": trainable,
        "non_trainable": non_trainable,
        "total": trainable + non_trainable,
    }
