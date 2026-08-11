"""Compose-Vertrag fuer unveraenderte Defaults und optionale Modellwechsel."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.yml"
VIRTUAL_COMPOSE = ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/docker-compose.virtual.yml"


@unittest.skipUnless(shutil.which("docker"), "docker CLI is required for Compose rendering")
class ModelSelectionComposeTests(unittest.TestCase):
    def render(self, **values: str) -> dict:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as env_file:
            for key, value in values.items():
                env_file.write(f"{key}={value}\n")
            env_file.flush()
            process = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    env_file.name,
                    "-f",
                    str(COMPOSE),
                    "config",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")},
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def render_virtual(self, **values: str) -> dict:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as env_file:
            env_file.write("NODE_RED_CREDENTIAL_SECRET=test-only-secret\n")
            for key, value in values.items():
                env_file.write(f"{key}={value}\n")
            env_file.flush()
            process = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    env_file.name,
                    "-f",
                    str(COMPOSE),
                    "-f",
                    str(VIRTUAL_COMPOSE),
                    "config",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")},
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_defaults_keep_current_images_and_latest_paths(self) -> None:
        config = self.render()
        expected_images = {
            "storage_infer": "ft_cb_storage:local",
            "vgr_infer": "ft_cb_vgr:local",
            "hbw_infer": "ft_cb_hbw:local",
        }
        for service, image in expected_images.items():
            domain = service.removesuffix("_infer")
            values = config["services"][service]
            self.assertEqual(values["image"], image)
            self.assertEqual(
                values["environment"]["KB_PATH"],
                f"/model_registry/{domain}/latest/model.keras",
            )

    def test_candidate_path_and_complete_image_can_be_overridden(self) -> None:
        config = self.render(
            VGR_MODEL_DIR="/model_registry/vgr/candidates/lstm32",
            VGR_IMAGE="registry.example/vgr@sha256:abc",
        )
        vgr = config["services"]["vgr_infer"]
        self.assertEqual(vgr["image"], "registry.example/vgr@sha256:abc")
        self.assertEqual(
            vgr["environment"]["KB_PATH"],
            "/model_registry/vgr/candidates/lstm32/model.keras",
        )
        self.assertEqual(
            vgr["environment"]["AB_PATH"],
            "/model_registry/vgr/candidates/lstm32/activation.json",
        )

    def test_virtual_node_red_image_can_be_overridden(self) -> None:
        config = self.render_virtual(
            NODE_RED_IMAGE="ghcr.io/example/ai-cps-node-red@sha256:abc"
        )
        self.assertEqual(
            config["services"]["node_red"]["image"],
            "ghcr.io/example/ai-cps-node-red@sha256:abc",
        )

    def test_historical_profile_catalog_is_virtual_only(self) -> None:
        physical = self.render()
        virtual = self.render_virtual()
        for domain in ("vgr", "hbw"):
            service = f"{domain}_infer"
            self.assertNotIn("MODEL_PROFILES_PATH", physical["services"][service]["environment"])
            self.assertEqual(
                virtual["services"][service]["environment"]["MODEL_PROFILES_PATH"],
                "/runtime_config/virtual_experiment_catalog.json",
            )

    def test_compose_project_and_runtime_identity_are_configurable(self) -> None:
        config = self.render_virtual(
            COMPOSE_PROJECT_NAME="portable-site",
            AI_CPS_UID="1234",
            AI_CPS_GID="2345",
        )
        self.assertEqual(config["name"], "portable-site")
        self.assertEqual(config["services"]["node_red"]["user"], "1234:2345")
        self.assertEqual(config["services"]["runtime_permissions"]["user"], "0:0")


if __name__ == "__main__":
    unittest.main()
