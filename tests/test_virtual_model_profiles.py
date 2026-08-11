import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/code_base_common"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import sys
sys.path.insert(0, str(COMMON))
profiles = load_module("model_profiles", COMMON / "model_profiles.py")


class VirtualModelProfileTests(unittest.TestCase):
    def test_no_catalog_preserves_single_active_profile(self):
        default, specs = profiles.load_profile_specs(
            None,
            domain="vgr",
            active_model_path=ROOT / "model_registry/vgr/latest/model.keras",
            active_activation_path=ROOT / "model_registry/vgr/latest/activation.json",
            model_registry_root=ROOT / "model_registry",
        )
        self.assertEqual(default, "deployment-current")
        self.assertEqual(list(specs), ["deployment-current"])

    def test_versioned_catalog_resolves_and_verifies_both_profiles(self):
        catalog = ROOT / (
            "scenarios/serve_ft_nns_external_broker/x86_64/"
            "node_red/config/virtual_experiment_catalog.json"
        )
        default, specs = profiles.load_profile_specs(
            catalog,
            domain="vgr",
            active_model_path=ROOT / "model_registry/vgr/latest/model.keras",
            active_activation_path=ROOT / "model_registry/vgr/latest/activation.json",
            model_registry_root=ROOT / "model_registry",
        )
        self.assertEqual(default, "deployment-current")
        self.assertEqual(set(specs), {"deployment-current", "historical-full-storage-error"})
        self.assertTrue(specs["historical-full-storage-error"]["virtual_only"])

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "model"
            model_dir.mkdir()
            for name in ("model.keras", "activation.json", "metrics.json"):
                (model_dir / name).write_text("x", encoding="utf-8")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({
                "schema_version": "1.0",
                "default_model_profile": "deployment-current",
                "model_profiles": {
                    "deployment-current": {
                        "domains": {"vgr": {"source": "active"}},
                    },
                    "bad": {
                        "domains": {"vgr": {
                            "source": "fixed",
                            "model_dir": "model",
                            "model_sha256": "0" * 64,
                        }},
                    },
                },
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "model_sha256 mismatch"):
                profiles.load_profile_specs(
                    catalog,
                    domain="vgr",
                    active_model_path=model_dir / "model.keras",
                    active_activation_path=model_dir / "activation.json",
                    model_registry_root=root,
                )

    def test_selection_defaults_and_rejects_wrong_model_id(self):
        loaded = {
            "deployment-current": {"contract": {"model_id": "vgr:current"}},
            "historical": {"contract": {"model_id": "vgr:old"}},
        }
        profile_id, selected = profiles.select_profile(
            {}, default_profile="deployment-current", loaded_profiles=loaded,
        )
        self.assertEqual(profile_id, "deployment-current")
        self.assertEqual(selected["contract"]["model_id"], "vgr:current")
        with self.assertRaisesRegex(ValueError, "model_id mismatch"):
            profiles.select_profile(
                {"model_profile": "historical", "model_id": "vgr:current"},
                default_profile="deployment-current",
                loaded_profiles=loaded,
            )


if __name__ == "__main__":
    unittest.main()
