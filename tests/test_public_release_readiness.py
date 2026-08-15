"""Tests for the public runtime release gate."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_public_release_readiness as readiness


class PublicReleaseReadinessTests(unittest.TestCase):
    def prepare_root(self, root: Path, *, status: str = "approved") -> None:
        for relative in readiness.REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("public metadata\n", encoding="utf-8")
        config = root / "configs/runtime_release.json"
        config.parent.mkdir(exist_ok=True)
        config.write_text(
            json.dumps({"repository": readiness.EXPECTED_REPOSITORY}),
            encoding="utf-8",
        )
        (root / "configs/publication_rights.json").write_text(
            json.dumps(
                {
                    "entries": [
                        {"id": identifier, "status": status, "scope": "test"}
                        for identifier in readiness.REQUIRED_RIGHTS
                    ]
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def git_files(*files: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "ls-files"],
            returncode=0,
            stdout="\n".join(files) + "\n",
            stderr="",
        )

    def test_approved_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            with mock.patch.object(
                readiness.subprocess, "run", return_value=self.git_files("README.md")
            ):
                errors, warnings = readiness.evaluate(root=root, require_approved=True)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_pending_rights_are_warning_until_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root, status="pending")
            with mock.patch.object(
                readiness.subprocess, "run", return_value=self.git_files("README.md")
            ):
                errors, warnings = readiness.evaluate(root=root, require_approved=False)
                release_errors, _ = readiness.evaluate(root=root, require_approved=True)
        self.assertEqual(errors, [])
        self.assertRegex(warnings[0], "pending")
        self.assertRegex(release_errors[0], "pending")

    def test_prohibited_artifact_and_secret_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            secret = root / "config.txt"
            secret.write_text("token=ghp_" + "a" * 40, encoding="utf-8")
            (root / "research.ipynb").write_text("{}\n", encoding="utf-8")
            with mock.patch.object(
                readiness.subprocess,
                "run",
                return_value=self.git_files("config.txt", "research.ipynb"),
            ):
                errors, _ = readiness.evaluate(root=root, require_approved=True)
        self.assertTrue(any("prohibited" in error for error in errors))
        self.assertTrue(any("possible secret" in error for error in errors))

    def test_exported_tree_without_git_metadata_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            (root / "README.md").write_text("public runtime\n", encoding="utf-8")

            errors, warnings = readiness.evaluate(root=root, require_approved=True)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_env_template_is_allowed_but_runtime_env_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            (root / ".env.example").write_text("MQTT_HOST=localhost\n", encoding="utf-8")
            (root / ".env").write_text("MQTT_HOST=private\n", encoding="utf-8")

            errors, _ = readiness.evaluate(root=root, require_approved=True)

        self.assertTrue(any(error.endswith(".env") for error in errors))
        self.assertFalse(any(error.endswith(".env.example") for error in errors))

    def test_current_release_metadata_is_consistent(self) -> None:
        config = readiness.load_object(readiness.RELEASE_CONFIG)
        rights = readiness.load_object(readiness.RIGHTS_FILE)
        release = str(config["release"])
        version = release.removeprefix("runtime-v")
        self.assertEqual(rights["release"], release)
        self.assertIn(f'version: "{version}"', (readiness.PROJECT_ROOT / "CITATION.cff").read_text())
        for relative in (
            "README.md",
            "docs/ENVIRONMENT_SETUP.md",
            "docs/OPERATION_AND_MIGRATION_GUIDE.md",
            "docs/PORTABLE_DEPLOYMENT.md",
            "docs/SIMULATION_TROUBLESHOOTING_RUNBOOK.md",
            "docs/PUBLIC_RELEASE_PROCEDURE.md",
            "tools/run_nodered_orchestration.sh",
        ):
            with self.subTest(path=relative):
                content = (readiness.PROJECT_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(release, content)

        runtime_version = str(config["node_red_runtime_version"])
        entrypoint = readiness.PROJECT_ROOT / (
            "scenarios/serve_ft_nns_external_broker/x86_64/node_red/entrypoint.sh"
        )
        self.assertIn(runtime_version, entrypoint.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
