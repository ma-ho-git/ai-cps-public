"""Contract tests for the AI-assisted development handover documents."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HANDOVER = PROJECT_ROOT / "docs" / "AI_DEVELOPMENT_HANDOVER.md"


class AiDevelopmentDocsTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def test_required_entrypoints_exist(self) -> None:
        for relative_path in (
            "AGENTS.md",
            "CLAUDE.md",
            "docs/AI_DEVELOPMENT_HANDOVER.md",
            ".github/pull_request_template.md",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((PROJECT_ROOT / relative_path).is_file())

    def test_bot_entrypoints_reference_the_canonical_handover(self) -> None:
        agents = self.read("AGENTS.md")
        claude = self.read("CLAUDE.md")
        readme = self.read("README.md")

        self.assertIn("docs/AI_DEVELOPMENT_HANDOVER.md", agents)
        self.assertIn("@AGENTS.md", claude)
        self.assertIn("@docs/AI_DEVELOPMENT_HANDOVER.md", claude)
        self.assertIn("docs/AI_DEVELOPMENT_HANDOVER.md", readme)

    def test_handover_contains_required_protocols_and_sources(self) -> None:
        handover = HANDOVER.read_text(encoding="utf-8")
        for heading in (
            "## Sources Of Truth",
            "## Protected Contracts",
            "## Session Start Protocol",
            "## Validation Matrix",
            "## Session Completion And Handover",
            "## Starter Prompts",
            "## Maintenance Rules",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, handover)

        for source in (
            "AGENTS.md",
            "OPERATION_AND_MIGRATION_GUIDE.md",
            "NODERED_MQTT_ORCHESTRATION.md",
            "PROJECT_KNOWLEDGE.md",
        ):
            with self.subTest(source=source):
                self.assertIn(source, handover)

    def test_versioned_latest_and_local_candidates_are_distinguished(self) -> None:
        agents = self.read("AGENTS.md")
        handover = HANDOVER.read_text(encoding="utf-8")
        for content in (agents, handover):
            self.assertIn("model_registry/<domain>/latest", content)
            self.assertIn("versioniert", content)
            self.assertIn("candidates/", content)

    def test_local_markdown_links_in_handover_exist(self) -> None:
        handover = HANDOVER.read_text(encoding="utf-8")
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", handover)
        self.assertTrue(links)

        for target in links:
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text:
                continue
            resolved = (HANDOVER.parent / path_text).resolve()
            with self.subTest(target=target):
                self.assertTrue(resolved.is_file())

    def test_pull_request_template_covers_handover_and_artifact_safety(self) -> None:
        template = self.read(".github/pull_request_template.md")
        for text in (
            "Wissenschaftliche Und Vertragliche Auswirkungen",
            "Dokumentation Und Uebergabe",
            "git diff --check",
            "Keine `.env`",
        ):
            self.assertIn(text, template)


if __name__ == "__main__":
    unittest.main()
