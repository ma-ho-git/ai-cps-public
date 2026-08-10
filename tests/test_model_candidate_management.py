"""Tests fuer den rueckrollbaren Modellwechsel in der Deployment-Schicht."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import manage_model_candidates as manager


def write_artifacts(path: Path, *, domain: str, trained_at: str, model: bytes) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.keras").write_bytes(model)
    (path / "activation.json").write_text(
        json.dumps(
            {
                "domain": domain,
                "trained_at": trained_at,
                "feature_cols": ["sensor"],
                "class_ids": [0],
            }
        ),
        encoding="utf-8",
    )
    (path / "metrics.json").write_text('{"accuracy": 1.0}', encoding="utf-8")


def candidate_model_id(domain: str, trained_at: str, model: bytes) -> str:
    digest = hashlib.sha256(model).hexdigest()
    return f"{domain}:{trained_at}:{digest[:12]}"


def write_report(path: Path, *, domain: str, model_id: str, rows: int = 320, faults: int = 0) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "run_summary.json").write_text(
        json.dumps(
            {
                "completed": True,
                "rows_completed": rows,
                "faults": faults,
                "model_ids": {domain: model_id},
                "storage_matches_vgr": rows,
                "vgr_matches": rows,
                "hbw_matches": rows,
            }
        ),
        encoding="utf-8",
    )
    with (path / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["request_id_base", "timeout", "error"])
        writer.writeheader()
        for index in range(rows):
            writer.writerow(
                {"request_id_base": f"r{index:03d}", "timeout": "False", "error": ""}
            )


class ModelCandidateManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.env_file = self.root / ".env"
        self.env_file.write_text(
            "MQTT_HOST=192.168.0.5\nNODE_RED_CREDENTIAL_SECRET=keep-this-secret\n",
            encoding="utf-8",
        )
        for domain in manager.DOMAINS:
            write_artifacts(
                self.root / f"model_registry/{domain}/latest",
                domain=domain,
                trained_at="latest",
                model=f"latest-{domain}".encode(),
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_add_copies_complete_candidate_and_records_identity(self, _validate: mock.Mock) -> None:
        source = self.root / "incoming"
        model = b"candidate-vgr"
        write_artifacts(source, domain="vgr", trained_at="candidate", model=model)

        result = manager.add_candidate(
            domain="vgr",
            name="lstm32",
            source=source,
            target="virtual",
            root=self.root,
        )

        destination = self.root / "model_registry/vgr/candidates/lstm32"
        self.assertTrue(all((destination / name).is_file() for name in manager.ARTIFACTS))
        self.assertTrue((destination / "candidate.json").is_file())
        self.assertEqual(result["model_id"], candidate_model_id("vgr", "candidate", model))

    @mock.patch.object(manager, "ensure_stack_stopped")
    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_select_preserves_env_and_rollback_restores_default(
        self,
        _validate: mock.Mock,
        _stopped: mock.Mock,
    ) -> None:
        candidate = self.root / "model_registry/vgr/candidates/lstm32"
        write_artifacts(candidate, domain="vgr", trained_at="candidate", model=b"candidate")

        manager.select_candidate(
            domain="vgr",
            name="lstm32",
            target="virtual",
            env_file=self.env_file,
            root=self.root,
        )
        selected_env = self.env_file.read_text(encoding="utf-8")
        self.assertIn("VGR_MODEL_DIR=/model_registry/vgr/candidates/lstm32", selected_env)
        self.assertIn("NODE_RED_CREDENTIAL_SECRET=keep-this-secret", selected_env)

        result = manager.rollback_candidate(
            domain="vgr",
            env_file=self.env_file,
            root=self.root,
        )

        rolled_back_env = self.env_file.read_text(encoding="utf-8")
        self.assertNotIn("VGR_MODEL_DIR=", rolled_back_env)
        self.assertIn("NODE_RED_CREDENTIAL_SECRET=keep-this-secret", rolled_back_env)
        self.assertEqual(result["model_dir"], "/model_registry/vgr/latest")

    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_select_is_rejected_when_stack_is_running(self, _validate: mock.Mock) -> None:
        candidate = self.root / "model_registry/vgr/candidates/lstm32"
        write_artifacts(candidate, domain="vgr", trained_at="candidate", model=b"candidate")
        completed = mock.Mock(returncode=0, stdout="vgr_infer\n", stderr="")
        with mock.patch.object(manager.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(manager.CandidateError, "gestopptem Stack"):
                manager.select_candidate(
                    domain="vgr",
                    name="lstm32",
                    target="virtual",
                    env_file=self.env_file,
                    root=self.root,
                )

    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_add_rejects_incomplete_artifact_group(self, _validate: mock.Mock) -> None:
        source = self.root / "incoming"
        source.mkdir()
        (source / "model.keras").write_bytes(b"model")
        with self.assertRaisesRegex(manager.CandidateError, "fehlen"):
            manager.add_candidate(
                domain="vgr",
                name="incomplete",
                source=source,
                target="virtual",
                root=self.root,
            )

    @mock.patch.object(manager, "ensure_stack_stopped")
    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_promote_backs_up_latest_and_resets_selection(
        self,
        _validate: mock.Mock,
        _stopped: mock.Mock,
    ) -> None:
        candidate = self.root / "model_registry/vgr/candidates/lstm32"
        model = b"promoted-model"
        write_artifacts(candidate, domain="vgr", trained_at="candidate", model=model)
        model_id = candidate_model_id("vgr", "candidate", model)
        report = self.root / "report"
        write_report(report, domain="vgr", model_id=model_id)
        self.env_file.write_text(
            self.env_file.read_text(encoding="utf-8")
            + "VGR_MODEL_DIR=/model_registry/vgr/candidates/lstm32\n",
            encoding="utf-8",
        )

        result = manager.promote_candidate(
            domain="vgr",
            name="lstm32",
            report_dir=report,
            env_file=self.env_file,
            root=self.root,
        )

        self.assertEqual(
            (self.root / "model_registry/vgr/latest/model.keras").read_bytes(), model
        )
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertNotIn("VGR_MODEL_DIR=", self.env_file.read_text(encoding="utf-8"))
        self.assertEqual(result["quality"]["quality_matches"], 320)

    @mock.patch.object(manager, "ensure_stack_stopped")
    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_promote_preserves_displaced_latest_when_docker_permissions_block_cleanup(
        self,
        _validate: mock.Mock,
        _stopped: mock.Mock,
    ) -> None:
        candidate = self.root / "model_registry/vgr/candidates/lstm32"
        model = b"promoted-model"
        write_artifacts(candidate, domain="vgr", trained_at="candidate", model=model)
        report = self.root / "report"
        write_report(
            report,
            domain="vgr",
            model_id=candidate_model_id("vgr", "candidate", model),
        )
        real_rmtree = manager.shutil.rmtree

        def fail_for_displaced(path: Path, *args, **kwargs) -> None:
            if Path(path).name.startswith(".latest-previous-"):
                raise PermissionError("Docker-owned artifact")
            real_rmtree(path, *args, **kwargs)

        with mock.patch.object(manager.shutil, "rmtree", side_effect=fail_for_displaced):
            result = manager.promote_candidate(
                domain="vgr",
                name="lstm32",
                report_dir=report,
                env_file=self.env_file,
                root=self.root,
            )

        preserved = Path(result["displaced_backup"])
        self.assertTrue(preserved.is_dir())
        self.assertEqual((preserved / "model.keras").read_bytes(), b"latest-vgr")
        self.assertEqual(
            (self.root / "model_registry/vgr/latest/model.keras").read_bytes(),
            model,
        )

    @mock.patch.object(manager, "ensure_stack_stopped")
    @mock.patch.object(manager, "validate_candidate", return_value=[])
    def test_promote_rejects_report_from_another_model(
        self,
        _validate: mock.Mock,
        _stopped: mock.Mock,
    ) -> None:
        candidate = self.root / "model_registry/vgr/candidates/lstm32"
        write_artifacts(candidate, domain="vgr", trained_at="candidate", model=b"candidate")
        report = self.root / "report"
        write_report(report, domain="vgr", model_id="vgr:other:deadbeef")

        with self.assertRaisesRegex(manager.CandidateError, "Report nutzt"):
            manager.promote_candidate(
                domain="vgr",
                name="lstm32",
                report_dir=report,
                env_file=self.env_file,
                root=self.root,
            )

    def test_status_reports_latest_defaults_and_optional_image(self) -> None:
        self.env_file.write_text(
            self.env_file.read_text(encoding="utf-8") + "VGR_IMAGE=example/vgr:test\n",
            encoding="utf-8",
        )
        value = manager.status(root=self.root, env_file=self.env_file)

        self.assertEqual(value["domains"]["storage"]["model_dir"], "/model_registry/storage/latest")
        self.assertEqual(value["domains"]["vgr"]["image"], "example/vgr:test")
        self.assertTrue(value["domains"]["hbw"]["exists"])

    def test_cli_help_explains_safe_workflow_and_subcommands(self) -> None:
        script = Path(manager.__file__)
        top_level = subprocess.run(
            ["python3", str(script), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(top_level.returncode, 0)
        for text in ("add", "select", "status", "rollback", "promote", "gestopptem Stack"):
            self.assertIn(text, top_level.stdout)

        physical = subprocess.run(
            ["python3", str(script), "add", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        promotion = subprocess.run(
            ["python3", str(script), "promote", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        physical_help = " ".join(physical.stdout.split())
        promotion_help = " ".join(promotion.stdout.split())
        self.assertIn("physical schliesst die virtuelle Pruefung ein", physical_help)
        self.assertIn("320-Zustaende-Lauf", promotion_help)
        self.assertIn("passender model_id", promotion_help)


if __name__ == "__main__":
    unittest.main()
