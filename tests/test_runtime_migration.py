"""Tests for checksummed AI-CPS site bundles."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import manage_runtime_migration as migration


class RuntimeMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scenario = self.root / "scenarios/serve_ft_nns_external_broker/x86_64"
        self.scenario.mkdir(parents=True)
        self.config = self.root / "configs/runtime_release.json"
        self.config.parent.mkdir()
        self.config.write_text(
            json.dumps({"release": "runtime-v1.1.0", "platform": "linux/amd64"}),
            encoding="utf-8",
        )
        self.env_file = self.root / ".env"
        self.env_file.write_text(
            "COMPOSE_PROJECT_NAME=custom-site\n"
            "REPORT_ROOT_HOST=../../../reports\n"
            "NODE_RED_CREDENTIAL_SECRET=test-secret\n"
            "VGR_MODEL_DIR=/model_registry/vgr/candidates/selected-vgr\n",
            encoding="utf-8",
        )
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "report.txt").write_text("site-report", encoding="utf-8")
        for domain in migration.MODEL_DOMAINS:
            model_dir = self.root / "model_registry" / domain / "latest"
            if domain == "vgr":
                model_dir = self.root / "model_registry/vgr/candidates/selected-vgr"
            model_dir.mkdir(parents=True)
            (model_dir / "model.keras").write_bytes(domain.encode())
            (model_dir / "activation.json").write_text(
                json.dumps({"trained_at": "test"}), encoding="utf-8"
            )
            (model_dir / "metrics.json").write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def patches(self):
        return (
            mock.patch.object(migration, "PROJECT_ROOT", self.root),
            mock.patch.object(migration, "SCENARIO_ROOT", self.scenario),
            mock.patch.object(migration, "RELEASE_CONFIG", self.config),
            mock.patch.object(migration, "DEPLOYMENT_LOCK", self.root / ".runtime/lock.json"),
            mock.patch.object(migration, "ensure_stack_stopped"),
            mock.patch.object(migration, "git_head", return_value="1" * 40),
        )

    @staticmethod
    def fake_volume(_volume: str, destination: Path, *, allow_missing: bool) -> bool:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"volume-archive")
        return True

    def create_bundle(self) -> Path:
        output = self.root / "site.tar.gz"
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], mock.patch.object(
            migration, "backup_volume", side_effect=self.fake_volume
        ):
            migration.export_bundle(output=output, env_file=self.env_file)
        return output

    def test_export_contains_full_env_custom_project_and_selected_candidate(self) -> None:
        bundle = self.create_bundle()
        manifest = migration.inspect_bundle(bundle)

        self.assertEqual(manifest["compose_project"], "custom-site")
        self.assertTrue(manifest["contains_plaintext_env"])
        self.assertEqual(
            manifest["selected_candidates"],
            ["model_registry/vgr/candidates/selected-vgr"],
        )
        self.assertEqual(set(manifest["included_volumes"]), set(migration.VOLUMES))
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o600)

    def test_checksum_damage_is_rejected(self) -> None:
        bundle = self.create_bundle()
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            with migration.tarfile.open(bundle, "r:gz") as archive:
                migration._safe_extract(archive, stage)
            (stage / ".env").write_text("tampered=true\n", encoding="utf-8")
            damaged = self.root / "damaged.tar.gz"
            with migration.tarfile.open(damaged, "w:gz") as archive:
                for child in stage.iterdir():
                    archive.add(child, arcname=child.name)
        with self.assertRaisesRegex(migration.MigrationError, "checksum mismatch"):
            migration.inspect_bundle(damaged)

    def test_import_creates_backup_and_restores_without_starting(self) -> None:
        bundle = self.create_bundle()
        self.env_file.write_text(
            "COMPOSE_PROJECT_NAME=target-site\nREPORT_ROOT_HOST=../../../reports\n",
            encoding="utf-8",
        )
        restore_calls: list[tuple[str, str, str]] = []
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], mock.patch.object(
            migration, "export_bundle"
        ) as backup, mock.patch.object(
            migration,
            "restore_volume",
            side_effect=lambda project, logical, archive: restore_calls.append(
                (project, logical, archive.name)
            ),
        ):
            backup.return_value = {}
            backup_path = migration.import_bundle(
                bundle=bundle, env_file=self.env_file, force=True
            )

        backup.assert_called_once()
        self.assertTrue(backup_path.name.startswith("pre-import-"))
        restored = migration.load_env(self.env_file)
        self.assertEqual(restored["COMPOSE_PROJECT_NAME"], "custom-site")
        self.assertEqual(restored["NODE_RED_CREDENTIAL_SECRET"], "test-secret")
        self.assertEqual(len(restore_calls), 3)

    def test_import_creates_private_pre_import_backup(self) -> None:
        bundle = self.create_bundle()
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], mock.patch.object(
            migration, "backup_volume", side_effect=self.fake_volume
        ), mock.patch.object(migration, "restore_volume"):
            backup_path = migration.import_bundle(
                bundle=bundle,
                env_file=self.env_file,
                force=True,
            )

        self.assertTrue(backup_path.is_file())
        self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)

    def test_import_can_restore_into_isolated_project_and_report_root(self) -> None:
        bundle = self.create_bundle()
        target_reports = self.root / "isolated-reports"
        restore_calls: list[tuple[str, str, str]] = []
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], mock.patch.object(
            migration,
            "restore_volume",
            side_effect=lambda project, logical, archive: restore_calls.append(
                (project, logical, archive.name)
            ),
        ):
            migration.import_bundle(
                bundle=bundle,
                env_file=self.root / "isolated.env",
                force=True,
                target_project="ai-cps-v11-restore",
                target_report_root=target_reports,
            )

        restored = migration.load_env(self.root / "isolated.env")
        self.assertEqual(restored["COMPOSE_PROJECT_NAME"], "ai-cps-v11-restore")
        self.assertEqual(restored["REPORT_ROOT_HOST"], str(target_reports.resolve()))
        self.assertEqual(restored["NODE_RED_CREDENTIAL_SECRET"], "test-secret")
        self.assertEqual(
            {(project, logical) for project, logical, _archive in restore_calls},
            {
                ("ai-cps-v11-restore", "nodered_data"),
                ("ai-cps-v11-restore", "mosquitto_data"),
                ("ai-cps-v11-restore", "mosquitto_log"),
            },
        )
        self.assertEqual(
            (target_reports / "report.txt").read_text(encoding="utf-8"),
            "site-report",
        )

    def test_target_project_rejects_unsafe_namespace(self) -> None:
        for value in ("Uppercase", "../shared", "with space", ""):
            with self.subTest(value=value):
                with self.assertRaises(migration.MigrationError):
                    migration.validate_compose_project(value)

    def test_compatibility_rejects_unsafe_candidate_path(self) -> None:
        manifest = {
            "release": "runtime-v1.1.0",
            "platform": "linux/amd64",
            "included_volumes": list(migration.VOLUMES),
            "selected_candidates": ["model_registry/vgr/candidates/../../outside"],
        }
        with mock.patch.object(migration, "RELEASE_CONFIG", self.config):
            with self.assertRaisesRegex(migration.MigrationError, "unsafe candidate"):
                migration.validate_compatibility(manifest)

    def test_compatibility_rejects_unknown_volume(self) -> None:
        manifest = {
            "release": "runtime-v1.1.0",
            "platform": "linux/amd64",
            "included_volumes": ["nodered_data", "unknown"],
            "selected_candidates": [],
        }
        with mock.patch.object(migration, "RELEASE_CONFIG", self.config):
            with self.assertRaisesRegex(migration.MigrationError, "volume list"):
                migration.validate_compatibility(manifest)

    def test_v13_rc_accepts_supported_site_bundles(self) -> None:
        self.config.write_text(
            json.dumps(
                {
                    "release": "runtime-v1.3.0-rc.1",
                    "platform": "linux/amd64",
                    "compatible_site_bundle_releases": [
                        "runtime-v1.1.0",
                        "runtime-v1.1.1",
                        "runtime-v1.2.0",
                        "runtime-v1.3.0-rc.1",
                    ],
                }
            ),
            encoding="utf-8",
        )
        for release in (
            "runtime-v1.1.0", "runtime-v1.1.1", "runtime-v1.2.0",
            "runtime-v1.3.0-rc.1",
        ):
            with self.subTest(release=release):
                manifest = {
                    "release": release,
                    "platform": "linux/amd64",
                    "included_volumes": list(migration.VOLUMES),
                    "selected_candidates": [],
                }
                with mock.patch.object(migration, "RELEASE_CONFIG", self.config):
                    migration.validate_compatibility(manifest)

    def test_patch_release_rejects_unlisted_site_bundle(self) -> None:
        self.config.write_text(
            json.dumps(
                {
                    "release": "runtime-v1.2.0",
                    "platform": "linux/amd64",
                    "compatible_site_bundle_releases": [
                        "runtime-v1.1.0",
                        "runtime-v1.1.1",
                        "runtime-v1.2.0",
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest = {
            "release": "runtime-v1.0.0",
            "platform": "linux/amd64",
            "included_volumes": list(migration.VOLUMES),
            "selected_candidates": [],
        }
        with mock.patch.object(migration, "RELEASE_CONFIG", self.config):
            with self.assertRaisesRegex(migration.MigrationError, "not compatible"):
                migration.validate_compatibility(manifest)

    def test_restore_volume_recreates_unlabelled_volume_with_compose_labels(self) -> None:
        archive = self.root / "volume.tar.gz"
        archive.write_bytes(b"archive")
        inspect = mock.Mock(returncode=0, stdout="null\n", stderr="")
        with mock.patch.object(migration.subprocess, "run", return_value=inspect), mock.patch.object(
            migration, "run_checked"
        ) as run_checked:
            migration.restore_volume("target-project", "nodered_data", archive)

        commands = [call.args[0] for call in run_checked.call_args_list]
        self.assertIn(
            ["docker", "volume", "rm", "target-project_nodered_data"],
            commands,
        )
        self.assertIn(
            [
                "docker",
                "volume",
                "create",
                "--label",
                "com.docker.compose.project=target-project",
                "--label",
                "com.docker.compose.volume=nodered_data",
                "target-project_nodered_data",
            ],
            commands,
        )

    def test_restore_volume_keeps_correctly_labelled_volume(self) -> None:
        archive = self.root / "volume.tar.gz"
        archive.write_bytes(b"archive")
        labels = {
            "com.docker.compose.project": "target-project",
            "com.docker.compose.volume": "nodered_data",
        }
        inspect = mock.Mock(returncode=0, stdout=json.dumps(labels), stderr="")
        with mock.patch.object(migration.subprocess, "run", return_value=inspect), mock.patch.object(
            migration, "run_checked"
        ) as run_checked:
            migration.restore_volume("target-project", "nodered_data", archive)

        commands = [call.args[0] for call in run_checked.call_args_list]
        self.assertNotIn(
            ["docker", "volume", "rm", "target-project_nodered_data"],
            commands,
        )


if __name__ == "__main__":
    unittest.main()
