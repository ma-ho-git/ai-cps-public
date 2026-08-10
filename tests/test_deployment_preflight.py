"""Unit-Tests fuer den portablen Deployment-Preflight."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_deployment_readiness as preflight


class DeploymentPreflightTests(unittest.TestCase):
    def test_virtual_port_owned_by_current_runtime_is_accepted(self):
        class BusySocket:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def bind(self, _address):
                raise OSError("busy")

        def docker_holders(args, **_kwargs):
            service = "mosquitto" if "publish=1883" in args else "node_red"
            return mock.Mock(
                returncode=0,
                stdout=f"test-site|{service}\n",
                stderr="",
            )

        with (
            mock.patch.object(preflight.socket, "socket", return_value=BusySocket()),
            mock.patch.object(preflight.shutil, "which", return_value="/usr/bin/docker"),
            mock.patch.object(preflight, "run_command", side_effect=docker_holders),
        ):
            checks = preflight.check_virtual_ports(
                {"COMPOSE_PROJECT_NAME": "test-site"}
            )

        self.assertTrue(all(check.ok for check in checks))
        self.assertTrue(all("owned by test-site" in check.detail for check in checks))

    def test_virtual_port_owned_by_another_project_is_rejected(self):
        class BusySocket:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def bind(self, _address):
                raise OSError("busy")

        with (
            mock.patch.object(preflight.socket, "socket", return_value=BusySocket()),
            mock.patch.object(preflight.shutil, "which", return_value="/usr/bin/docker"),
            mock.patch.object(
                preflight,
                "run_command",
                return_value=mock.Mock(
                    returncode=0,
                    stdout="other-site|node_red\n",
                    stderr="",
                ),
            ),
        ):
            checks = preflight.check_virtual_ports(
                {"COMPOSE_PROJECT_NAME": "test-site"}
            )

        self.assertTrue(all(not check.ok for check in checks))

    def test_env_file_is_read_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("MQTT_HOST=192.168.0.5\nMQTT_PASS='secret value'\n", encoding="utf-8")
            values = preflight.load_env_file(path)

        self.assertEqual(values["MQTT_HOST"], "192.168.0.5")
        self.assertEqual(values["MQTT_PASS"], "secret value")

    def test_process_environment_has_precedence(self):
        settings = preflight.merged_settings(
            {"MQTT_HOST": "from-file", "MQTT_PORT": "1883"},
            {"MQTT_HOST": "from-process"},
        )
        self.assertEqual(settings["MQTT_HOST"], "from-process")
        self.assertEqual(settings["MQTT_PORT"], "1883")

    def test_physical_mode_treats_live_system_as_mqtt_black_box(self):
        ok = preflight.CheckResult("stub", True, "ok")
        with (
            mock.patch.object(preflight, "check_architecture", return_value=ok),
            mock.patch.object(preflight, "check_docker", return_value=[]),
            mock.patch.object(preflight, "check_compose_configs", return_value=[]),
            mock.patch.object(preflight, "check_model_artifacts", return_value=[]),
            mock.patch.object(preflight, "check_dependency_pins", return_value=[]),
            mock.patch.object(preflight, "check_nodered_assets", return_value=ok),
            mock.patch.object(preflight, "check_report_directory", return_value=ok),
            mock.patch.object(preflight, "check_mqtt_credentials", return_value=ok),
            mock.patch.object(preflight, "check_nodered_credential_secret", return_value=ok),
            mock.patch.object(preflight, "check_conflicting_consumers", return_value=ok),
            mock.patch.object(
                preflight,
                "check_broker",
                return_value=preflight.CheckResult("mqtt-broker", True, "reachable"),
            ),
        ):
            checks = preflight.collect_checks(
                mode="physical",
                settings={"MQTT_HOST": "192.168.0.5", "MQTT_PORT": "1883"},
                use_images=False,
            )

        names = {check.name for check in checks}
        self.assertIn("mqtt-broker", names)
        self.assertNotIn("nodered-assets", names)
        self.assertNotIn("report-directory", names)
        self.assertNotIn("nodered-credential-secret", names)
        self.assertFalse(any(name.startswith("factory-base-runtime:") for name in names))

    def test_virtual_mode_requires_nodered_assets_reports_and_secret(self):
        ok = preflight.CheckResult("stub", True, "ok")
        with (
            mock.patch.object(preflight, "check_architecture", return_value=ok),
            mock.patch.object(preflight, "check_docker", return_value=[]),
            mock.patch.object(preflight, "check_compose_configs", return_value=[]),
            mock.patch.object(preflight, "check_model_artifacts", return_value=[]),
            mock.patch.object(preflight, "check_dependency_pins", return_value=[]),
            mock.patch.object(
                preflight,
                "check_nodered_assets",
                return_value=preflight.CheckResult("nodered-assets", True, "ok"),
            ),
            mock.patch.object(
                preflight,
                "check_report_directory",
                return_value=preflight.CheckResult("report-directory", True, "ok"),
            ),
            mock.patch.object(
                preflight,
                "check_mqtt_credentials",
                return_value=preflight.CheckResult("mqtt-credentials", True, "ok"),
            ),
            mock.patch.object(
                preflight,
                "check_nodered_credential_secret",
                return_value=preflight.CheckResult("nodered-credential-secret", True, "ok"),
            ),
            mock.patch.object(preflight, "check_conflicting_consumers", return_value=ok),
        ):
            checks = preflight.collect_checks(mode="virtual", settings={}, use_images=False)

        names = {check.name for check in checks}
        self.assertIn("nodered-assets", names)
        self.assertIn("report-directory", names)
        self.assertIn("nodered-credential-secret", names)
        self.assertIn("factory-base-runtime:vgr", names)
        self.assertIn("factory-base-runtime:hbw", names)
        self.assertIn("factory-base-runtime:mpo", names)
        self.assertIn("factory-base-runtime:sld", names)
        self.assertNotIn("mqtt-broker", names)

    def test_virtual_factory_base_runtimes_default_to_100_ms(self):
        checks = preflight.check_factory_base_runtimes({})

        self.assertTrue(all(check.ok for check in checks))
        self.assertTrue(all("=100 ms" in check.detail for check in checks))

    def test_virtual_factory_base_runtimes_are_checked_per_module(self):
        checks = preflight.check_factory_base_runtimes(
            {
                "FACTORY_VGR_BASE_RUNTIME_MS": "50",
                "FACTORY_HBW_BASE_RUNTIME_MS": "200",
                "FACTORY_MPO_BASE_RUNTIME_MS": "0",
                "FACTORY_SLD_BASE_RUNTIME_MS": "100.5",
            }
        )
        by_name = {check.name: check for check in checks}

        self.assertTrue(by_name["factory-base-runtime:vgr"].ok)
        self.assertTrue(by_name["factory-base-runtime:hbw"].ok)
        self.assertFalse(by_name["factory-base-runtime:mpo"].ok)
        self.assertFalse(by_name["factory-base-runtime:sld"].ok)

    def test_virtual_factory_base_runtimes_reject_negative_and_nonfinite_values(self):
        for invalid in ("-1", "nan", "inf", "", "9007199254740992"):
            with self.subTest(invalid=invalid):
                checks = preflight.check_factory_base_runtimes(
                    {"FACTORY_VGR_BASE_RUNTIME_MS": invalid}
                )
                self.assertFalse(checks[0].ok)

    def test_virtual_assets_include_all_versioned_trace_profiles(self):
        relative_paths = {
            path.relative_to(preflight.PROJECT_ROOT).as_posix()
            for path in preflight.required_nodered_assets()
        }

        self.assertIn(
            "scenarios/serve_ft_nns_external_broker/x86_64/"
            "test_payloads/live_plc_trace/payloads.jsonl",
            relative_paths,
        )
        self.assertIn(
            "scenarios/serve_ft_nns_external_broker/x86_64/"
            "test_payloads/live_plc_full_storage_attempt/payloads.jsonl",
            relative_paths,
        )
        self.assertIn(
            "scenarios/serve_ft_nns_external_broker/x86_64/"
            "test_payloads/live_plc_full_storage_attempt/manifest.csv",
            relative_paths,
        )

    def test_only_x86_64_is_released(self):
        self.assertTrue(preflight.check_architecture("x86_64").ok)
        self.assertTrue(preflight.check_architecture("amd64").ok)
        self.assertFalse(preflight.check_architecture("aarch64").ok)

    def test_model_check_requires_all_three_latest_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for domain in preflight.MODEL_DOMAINS:
                latest = root / "model_registry" / domain / "latest"
                latest.mkdir(parents=True)
                (latest / "model.keras").write_bytes(b"model")
                (latest / "activation.json").write_text("{}", encoding="utf-8")
                (latest / "metrics.json").write_text("{}", encoding="utf-8")

            checks = preflight.check_model_artifacts(root)
            self.assertTrue(all(check.ok for check in checks))

            (root / "model_registry/hbw/latest/model.keras").unlink()
            checks = preflight.check_model_artifacts(root)
            self.assertFalse(next(check for check in checks if check.name == "model:hbw").ok)

    def test_model_check_uses_selected_candidate_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for domain in preflight.MODEL_DOMAINS:
                model_dir = root / "model_registry" / domain / "latest"
                if domain == "vgr":
                    model_dir = root / "model_registry/vgr/candidates/lstm32"
                model_dir.mkdir(parents=True)
                (model_dir / "model.keras").write_bytes(b"model")
                (model_dir / "activation.json").write_text("{}", encoding="utf-8")
                (model_dir / "metrics.json").write_text("{}", encoding="utf-8")

            checks = preflight.check_model_artifacts(
                root,
                {"VGR_MODEL_DIR": "/model_registry/vgr/candidates/lstm32"},
            )

        self.assertTrue(all(check.ok for check in checks))

    def test_model_check_rejects_path_outside_registry_mount(self):
        checks = preflight.check_model_artifacts(
            Path("/tmp/project"),
            {"VGR_MODEL_DIR": "/tmp/model"},
        )
        self.assertFalse(next(check for check in checks if check.name == "model:vgr").ok)

    def test_prebuilt_images_require_ghcr_repositories(self):
        checks = preflight.check_image_settings(
            {
                "IMAGE_TAG": "sha-1234",
                "STORAGE_IMAGE_REPOSITORY": "ghcr.io/example/storage",
                "VGR_IMAGE_REPOSITORY": "ghcr.io/example/vgr",
                "HBW_IMAGE_REPOSITORY": "local-hbw",
            }
        )
        self.assertFalse(next(check for check in checks if check.name == "image-repository:hbw").ok)

    def test_complete_image_reference_is_accepted(self):
        digest = "a" * 64
        checks = preflight.check_image_settings(
            {
                "IMAGE_TAG": "local",
                "STORAGE_IMAGE": f"registry.example/storage@sha256:{digest}",
                "VGR_IMAGE": f"registry.example/vgr@sha256:{digest}",
                "HBW_IMAGE": f"registry.example/hbw@sha256:{digest}",
            }
        )
        self.assertTrue(all(check.ok for check in checks))

    def test_virtual_prebuilt_images_include_node_red(self):
        checks = preflight.check_image_settings(
            {
                "IMAGE_TAG": "sha-1234",
                "STORAGE_IMAGE_REPOSITORY": "ghcr.io/example/storage",
                "VGR_IMAGE_REPOSITORY": "ghcr.io/example/vgr",
                "HBW_IMAGE_REPOSITORY": "ghcr.io/example/hbw",
                "NODE_RED_IMAGE_REPOSITORY": "local-node-red",
            },
            include_node_red=True,
        )
        self.assertFalse(
            next(check for check in checks if check.name == "image-repository:node_red").ok
        )

    def test_runtime_requirements_must_be_pinned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scenario = root / "scenarios/serve_ft_nns_external_broker/x86_64"
            for domain in preflight.MODEL_DOMAINS:
                code_dir = scenario / f"code_base_{domain}"
                code_dir.mkdir(parents=True)
                (code_dir / "requirements.txt").write_text(
                    "numpy==1.26.4\npaho-mqtt==2.1.0\n",
                    encoding="utf-8",
                )
            common = scenario / "code_base_common"
            common.mkdir(parents=True)
            (common / "requirements-runtime.lock").write_text(
                "tensorflow==2.16.1 \\\n    --hash=sha256:" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            for domain in preflight.MODEL_DOMAINS:
                training = root / "training" / domain
                training.mkdir(parents=True)
                (training / "requirements-training.lock").write_text(
                    "tensorflow==2.16.1 \\\n    --hash=sha256:" + "a" * 64 + "\n",
                    encoding="utf-8",
                )
            checks = preflight.check_dependency_pins(root)
            self.assertTrue(all(check.ok for check in checks))

            (scenario / "code_base_vgr/requirements.txt").write_text("numpy\n", encoding="utf-8")
            checks = preflight.check_dependency_pins(root)
            self.assertFalse(next(check for check in checks if check.name == "dependency-pins:vgr").ok)

    def test_compose_validation_receives_env_file_settings(self):
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(preflight, "run_command", return_value=completed) as run_command:
            checks = preflight.check_compose_configs(
                Path("/tmp/project"),
                {"NODE_RED_CREDENTIAL_SECRET": "site-specific-secret"},
            )

        self.assertTrue(all(check.ok for check in checks))
        for call in run_command.call_args_list:
            self.assertEqual(call.kwargs["env"]["NODE_RED_CREDENTIAL_SECRET"], "site-specific-secret")

    def test_physical_compose_validation_skips_virtual_overlay(self):
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(preflight, "run_command", return_value=completed) as run_command:
            checks = preflight.check_compose_configs(
                Path("/tmp/project"),
                {},
                mode="physical",
            )

        self.assertEqual([check.name for check in checks], ["compose-physical"])
        self.assertEqual(run_command.call_count, 1)

    def test_nodered_secret_is_separate_from_mqtt_credentials(self):
        mqtt_check = preflight.check_mqtt_credentials({"MQTT_USER": "user", "MQTT_PASS": "pw"})
        secret_check = preflight.check_nodered_credential_secret({})

        self.assertTrue(mqtt_check.ok)
        self.assertFalse(secret_check.ok)

    def test_missing_docker_cli_reports_failure_without_running_compose(self):
        failed = preflight.CheckResult("docker", False, "docker CLI not found")
        ok = preflight.CheckResult("stub", True, "ok")
        with (
            mock.patch.object(preflight.shutil, "which", return_value=None),
            mock.patch.object(preflight, "check_architecture", return_value=ok),
            mock.patch.object(preflight, "check_docker", return_value=[failed]),
            mock.patch.object(preflight, "check_compose_configs") as compose_check,
            mock.patch.object(preflight, "check_model_artifacts", return_value=[]),
            mock.patch.object(preflight, "check_dependency_pins", return_value=[]),
            mock.patch.object(preflight, "check_mqtt_credentials", return_value=ok),
            mock.patch.object(preflight, "check_nodered_assets", return_value=ok),
            mock.patch.object(preflight, "check_report_directory", return_value=ok),
            mock.patch.object(preflight, "check_nodered_credential_secret", return_value=ok),
        ):
            checks = preflight.collect_checks(mode="virtual", settings={}, use_images=False)

        self.assertIn(failed, checks)
        compose_check.assert_not_called()

    def test_detects_legacy_and_duplicate_nn_consumers(self):
        conflicts = preflight.parse_conflicting_consumers(
            [
                "current-storage|ai-cps-nn-runtime|storage_infer",
                "old-pipeline|x86_64|pipeline_orchestrator",
                "other-vgr|old-project|vgr_infer",
            ]
        )
        self.assertEqual(
            conflicts,
            [
                "old-pipeline (x86_64/pipeline_orchestrator)",
                "other-vgr (old-project/vgr_infer)",
            ],
        )

    def test_dynamic_project_name_is_not_reported_as_duplicate(self):
        conflicts = preflight.parse_conflicting_consumers(
            [
                "current-vgr|thesis-site|vgr_infer",
                "other-vgr|other-site|vgr_infer",
            ],
            "thesis-site",
        )
        self.assertEqual(conflicts, ["other-vgr (other-site/vgr_infer)"])

    def test_env_file_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            env_file = Path(temp) / ".env"
            env_file.write_text("COMPOSE_PROJECT_NAME=test-site\n", encoding="utf-8")
            env_file.chmod(0o644)
            checks = preflight.check_env_file(env_file, {"COMPOSE_PROJECT_NAME": "test-site"})
            self.assertFalse(checks[0].ok)
            env_file.chmod(0o600)
            checks = preflight.check_env_file(env_file, {"COMPOSE_PROJECT_NAME": "test-site"})
            self.assertTrue(all(check.ok for check in checks))

    def test_docker_desktop_linux_engine_is_supported(self):
        responses = [
            mock.Mock(returncode=0, stdout='{"Os":"linux","Arch":"amd64"}', stderr=""),
            mock.Mock(returncode=0, stdout="Docker Desktop 4.x\n", stderr=""),
            mock.Mock(returncode=0, stdout="Docker Compose version v2\n", stderr=""),
            mock.Mock(returncode=0, stdout="desktop-linux\n", stderr=""),
        ]
        with (
            mock.patch.object(preflight.shutil, "which", return_value="/usr/bin/docker"),
            mock.patch.object(preflight, "run_command", side_effect=responses),
        ):
            checks = preflight.check_docker()
        self.assertTrue(all(check.ok for check in checks))
        self.assertIn("Docker Desktop", next(c.detail for c in checks if c.name == "docker-runtime"))


if __name__ == "__main__":
    unittest.main()
