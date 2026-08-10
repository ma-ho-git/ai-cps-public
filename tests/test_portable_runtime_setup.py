"""Tests for the release-pinned portable runtime setup assistant."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import setup_portable_runtime as setup


DIGEST = "sha256:" + "b" * 64


class PortableRuntimeSetupTests(unittest.TestCase):
    def test_atomic_env_update_preserves_values_and_restricts_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_file = Path(temp) / ".env"
            env_file.write_text("MQTT_HOST=old\nKEEP=yes\n", encoding="utf-8")
            os.chmod(env_file, 0o644)
            setup.atomic_update_env(env_file, {"MQTT_HOST": "new", "ADDED": "value"})

            content = env_file.read_text(encoding="utf-8")
            self.assertIn("MQTT_HOST=new", content)
            self.assertIn("KEEP=yes", content)
            self.assertIn("ADDED=value", content)
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_manifest_rejects_unpinned_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "platform": "linux/amd64",
                        "images": {key: f"example/{key}:latest" for key in setup.IMAGE_ENV_KEYS},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(setup.SetupError, "pinned"):
                setup.obtain_manifest(
                    release="runtime-v1.1.0",
                    config={"repository": "owner/repo"},
                    manifest_path=manifest,
                )

    def test_manifest_rejects_truncated_image_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "platform": "linux/amd64",
                        "images": {
                            key: f"example/{key}@sha256:short"
                            for key in setup.IMAGE_ENV_KEYS
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(setup.SetupError, "pinned"):
                setup.obtain_manifest(
                    release="runtime-v1.1.0",
                    config={"repository": "owner/repo"},
                    manifest_path=manifest,
                )

    def test_init_creates_release_env_without_overwriting_site_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
            scenario.mkdir(parents=True)
            config = root / "runtime_release.json"
            config.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "repository": "owner/repo",
                        "compose_project": "ai-cps-default",
                    }
                ),
                encoding="utf-8",
            )
            example = root / ".env.example"
            example.write_text(
                "MQTT_HOST=site-broker\nKEEP=site-value\n"
                "NODE_RED_CREDENTIAL_SECRET=replace-with-a-long-random-site-secret\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            images = {
                key: f"ghcr.io/example/{key}@{DIGEST}" for key in setup.IMAGE_ENV_KEYS
            }
            manifest_path.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "platform": "linux/amd64",
                        "source_commit": "1" * 40,
                        "images": images,
                        "protected_files": {"file": "hash"},
                    }
                ),
                encoding="utf-8",
            )
            env_file = root / ".env"
            args = argparse.Namespace(
                release="runtime-v1.1.0",
                manifest=manifest_path,
                mode="virtual",
                env_file=env_file,
                mqtt_host=None,
                mqtt_port=1883,
                mqtt_user="",
                force=False,
                skip_venv=True,
                skip_pull=True,
                skip_preflight=True,
            )
            with (
                mock.patch.object(setup, "RELEASE_CONFIG", config),
                mock.patch.object(setup, "ENV_EXAMPLE", example),
                mock.patch.object(setup, "SCENARIO_ROOT", scenario),
                mock.patch.object(setup, "DEPLOYMENT_LOCK", root / ".runtime/lock.json"),
                mock.patch.object(setup, "verify_source_tree"),
            ):
                setup.init_runtime(args)

            values = setup.load_env(env_file)
            self.assertEqual(values["KEEP"], "site-value")
            self.assertEqual(values["MQTT_HOST"], "site-broker")
            self.assertEqual(values["IMAGE_TAG"], "runtime-v1.1.0")
            self.assertEqual(values["VGR_IMAGE"], images["vgr"])
            self.assertNotIn("replace-with", values["NODE_RED_CREDENTIAL_SECRET"])
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_fresh_env_accepts_release_image_tag_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scenario = root / "scenario"
            scenario.mkdir()
            config = root / "runtime_release.json"
            config.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "repository": "owner/repo",
                        "compose_project": "ai-cps-default",
                    }
                ),
                encoding="utf-8",
            )
            example = root / ".env.example"
            example.write_text(
                "IMAGE_TAG=local\n"
                "REPORT_ROOT_HOST=reports\n"
                "NODE_RED_CREDENTIAL_SECRET=replace-with-a-long-random-site-secret\n",
                encoding="utf-8",
            )
            manifest = {
                "release": "runtime-v1.1.0",
                "platform": "linux/amd64",
                "source_commit": "1" * 40,
                "images": {
                    key: f"ghcr.io/example/{key}@{DIGEST}"
                    for key in setup.IMAGE_ENV_KEYS
                },
                "protected_files": {"file": "hash"},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            args = argparse.Namespace(
                release="runtime-v1.1.0",
                manifest=manifest_path,
                mode="virtual",
                env_file=root / ".env",
                mqtt_host=None,
                mqtt_port=1883,
                mqtt_user="",
                force=False,
                skip_venv=True,
                skip_pull=True,
                skip_preflight=True,
            )
            with (
                mock.patch.object(setup, "RELEASE_CONFIG", config),
                mock.patch.object(setup, "ENV_EXAMPLE", example),
                mock.patch.object(setup, "SCENARIO_ROOT", scenario),
                mock.patch.object(setup, "DEPLOYMENT_LOCK", root / ".runtime/lock.json"),
                mock.patch.object(setup, "verify_source_tree"),
            ):
                setup.init_runtime(args)

            values = setup.load_env(args.env_file)
            self.assertEqual(values["IMAGE_TAG"], "runtime-v1.1.0")

    def test_init_applies_isolated_project_and_report_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scenario = root / "scenario"
            scenario.mkdir()
            config = root / "runtime_release.json"
            config.write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "repository": "owner/repo",
                        "compose_project": "ai-cps-default",
                    }
                ),
                encoding="utf-8",
            )
            example = root / ".env.example"
            example.write_text(
                "COMPOSE_PROJECT_NAME=ai-cps-default\n"
                "REPORT_ROOT_HOST=reports\n"
                "NODE_RED_CREDENTIAL_SECRET=replace-with-a-long-random-site-secret\n",
                encoding="utf-8",
            )
            manifest = {
                "release": "runtime-v1.1.0",
                "platform": "linux/amd64",
                "source_commit": "1" * 40,
                "images": {
                    key: f"ghcr.io/example/{key}@{DIGEST}"
                    for key in setup.IMAGE_ENV_KEYS
                },
                "protected_files": {"file": "hash"},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report_root = root / "isolated-reports"
            args = argparse.Namespace(
                release="runtime-v1.1.0",
                manifest=manifest_path,
                mode="virtual",
                env_file=root / ".env",
                compose_project="ai-cps-v11-clean",
                report_root=report_root,
                mqtt_host=None,
                mqtt_port=1883,
                mqtt_user="",
                force=False,
                skip_venv=True,
                skip_pull=True,
                skip_preflight=True,
            )
            with (
                mock.patch.object(setup, "RELEASE_CONFIG", config),
                mock.patch.object(setup, "ENV_EXAMPLE", example),
                mock.patch.object(setup, "SCENARIO_ROOT", scenario),
                mock.patch.object(setup, "DEPLOYMENT_LOCK", root / ".runtime/lock.json"),
                mock.patch.object(setup, "verify_source_tree"),
            ):
                setup.init_runtime(args)

            values = setup.load_env(args.env_file)
            self.assertEqual(values["COMPOSE_PROJECT_NAME"], "ai-cps-v11-clean")
            self.assertEqual(values["REPORT_ROOT_HOST"], str(report_root.resolve()))
            self.assertTrue(report_root.is_dir())

    def test_compose_project_rejects_unsafe_namespace(self) -> None:
        for value in ("Uppercase", "../shared", "with space", ""):
            with self.subTest(value=value):
                with self.assertRaises(setup.SetupError):
                    setup.validate_compose_project(value)

    def test_physical_setup_requires_explicit_target_broker(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value):
                with self.assertRaisesRegex(setup.SetupError, "--mqtt-host"):
                    setup.require_physical_mqtt_host(value)

    def test_physical_setup_accepts_explicit_historical_broker_address(self) -> None:
        self.assertEqual(
            setup.require_physical_mqtt_host("192.168.0.5"),
            "192.168.0.5",
        )


if __name__ == "__main__":
    unittest.main()
