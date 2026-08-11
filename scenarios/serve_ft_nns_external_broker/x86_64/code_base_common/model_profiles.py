"""Validated model-profile catalog for virtual VGR/HBW experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mqtt_runtime import file_sha256


DEFAULT_MODEL_PROFILE = "deployment-current"


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read model profile catalog {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"model profile catalog {path} must contain a JSON object")
    return value


def _profile_paths(
    domain_config: dict[str, Any],
    *,
    active_model_path: str | Path,
    active_activation_path: str | Path,
    model_registry_root: str | Path,
) -> tuple[Path, Path, Path | None]:
    source = str(domain_config.get("source", ""))
    if source == "active":
        return Path(active_model_path), Path(active_activation_path), None
    if source != "fixed":
        raise ValueError(f"model profile source must be active or fixed, got {source!r}")
    relative_dir = str(domain_config.get("model_dir", ""))
    if not relative_dir:
        raise ValueError("fixed model profile requires model_dir")
    model_dir = Path(model_registry_root) / relative_dir
    return model_dir / "model.keras", model_dir / "activation.json", model_dir / "metrics.json"


def load_profile_specs(
    catalog_path: str | Path | None,
    *,
    domain: str,
    active_model_path: str | Path,
    active_activation_path: str | Path,
    model_registry_root: str | Path = "/model_registry",
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Resolve model paths and verify fixed artifacts without loading TensorFlow."""
    if not catalog_path:
        return DEFAULT_MODEL_PROFILE, {
            DEFAULT_MODEL_PROFILE: {
                "display_name": "Aktueller Modellstand",
                "virtual_only": False,
                "model_path": Path(active_model_path),
                "activation_path": Path(active_activation_path),
                "metrics_path": None,
            },
        }

    catalog = _json_object(Path(catalog_path))
    if catalog.get("schema_version") != "1.0":
        raise ValueError("model profile catalog schema_version must be 1.0")
    default_profile = str(catalog.get("default_model_profile", DEFAULT_MODEL_PROFILE))
    raw_profiles = catalog.get("model_profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ValueError("model profile catalog requires model_profiles")
    if default_profile not in raw_profiles:
        raise ValueError(f"default model profile {default_profile!r} is not defined")

    profiles: dict[str, dict[str, Any]] = {}
    for profile_id, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"model profile {profile_id!r} must be an object")
        domain_config = raw_profile.get("domains", {}).get(domain)
        if not isinstance(domain_config, dict):
            raise ValueError(f"model profile {profile_id!r} has no {domain} configuration")
        model_path, activation_path, metrics_path = _profile_paths(
            domain_config,
            active_model_path=active_model_path,
            active_activation_path=active_activation_path,
            model_registry_root=model_registry_root,
        )
        required = [model_path, activation_path] + ([metrics_path] if metrics_path else [])
        missing = [str(path) for path in required if path is not None and not path.is_file()]
        if missing:
            raise ValueError(f"model profile {profile_id!r} is missing artifacts: {missing}")

        for key, path in (
            ("model_sha256", model_path),
            ("activation_sha256", activation_path),
            ("metrics_sha256", metrics_path),
        ):
            expected = domain_config.get(key)
            if expected and path is not None:
                actual = file_sha256(path)
                if actual != str(expected):
                    raise ValueError(
                        f"model profile {profile_id!r} {key} mismatch: expected {expected}, got {actual}",
                    )

        profiles[str(profile_id)] = {
            "display_name": str(raw_profile.get("display_name", profile_id)),
            "description": str(raw_profile.get("description", "")),
            "virtual_only": bool(raw_profile.get("virtual_only", False)),
            "expected_model_id": domain_config.get("model_id"),
            "model_path": model_path,
            "activation_path": activation_path,
            "metrics_path": metrics_path,
        }
    return default_profile, profiles


def profile_contract(default_profile: str, loaded_profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Expose the active contract plus additive complete contracts per profile."""
    if default_profile not in loaded_profiles:
        raise ValueError(f"default model profile {default_profile!r} was not loaded")
    default_contract = dict(loaded_profiles[default_profile]["contract"])
    default_contract["default_model_profile"] = default_profile
    default_contract["model_profiles"] = {
        profile_id: {
            **dict(values["contract"]),
            "profile_id": profile_id,
            "display_name": values["display_name"],
            "description": values.get("description", ""),
            "virtual_only": bool(values.get("virtual_only", False)),
        }
        for profile_id, values in loaded_profiles.items()
    }
    return default_contract


def select_profile(
    request: dict[str, Any],
    *,
    default_profile: str,
    loaded_profiles: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Select one immutable per-request profile and verify its actual model ID."""
    profile_id = str(request.get("model_profile") or default_profile)
    selected = loaded_profiles.get(profile_id)
    if selected is None:
        raise ValueError(f"unknown model_profile {profile_id!r}")
    requested_model_id = request.get("model_id")
    actual_model_id = selected["contract"]["model_id"]
    if requested_model_id not in (None, "", actual_model_id):
        raise ValueError(
            f"model_id mismatch for profile {profile_id!r}: expected {actual_model_id}, got {requested_model_id}",
        )
    return profile_id, selected
