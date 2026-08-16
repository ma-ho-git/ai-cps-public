"""Contract tests for the virtual-simulation documentation."""

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
        self.assertIn("docs/VIRTUAL_SCENARIOS.md", readme)
        self.assertIn("docs/OPERATION_AND_MIGRATION_GUIDE.md", readme)

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
            "VIRTUAL_SCENARIOS.md",
            "OPERATION_AND_MIGRATION_GUIDE.md",
            "NODERED_MQTT_ORCHESTRATION.md",
            "PROJECT_KNOWLEDGE.md",
        ):
            with self.subTest(source=source):
                self.assertIn(source, handover)

    def test_virtual_scenarios_and_model_profiles_are_documented(self) -> None:
        readme = self.read("README.md")
        scenarios = self.read("docs/VIRTUAL_SCENARIOS.md")
        for content in (readme, scenarios):
            for identifier in (
                "standard",
                "full-storage-attempt",
                "full-storage-process-guard",
                "deployment-current",
                "historical-full-storage-error",
            ):
                with self.subTest(identifier=identifier):
                    self.assertIn(identifier, content)

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

    def test_all_local_markdown_links_exist(self) -> None:
        markdown_files = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "CONTRIBUTING.md",
            PROJECT_ROOT / "SECURITY.md",
            PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        ]
        markdown_files.extend(sorted((PROJECT_ROOT / "docs").glob("*.md")))
        for document in markdown_files:
            content = document.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", content):
                path_text = target.split("#", 1)[0]
                if not path_text or "://" in path_text:
                    continue
                resolved = (document.parent / path_text).resolve()
                with self.subTest(document=document.name, target=target):
                    self.assertTrue(resolved.is_file())

    def test_pull_request_template_covers_handover_and_artifact_safety(self) -> None:
        template = self.read(".github/pull_request_template.md")
        for text in (
            "Runtimevertraege",
            "Dokumentation Und Uebergabe",
            "git diff --check",
            "Keine `.env`",
        ):
            self.assertIn(text, template)

    def test_visible_docs_focus_on_virtual_simulation(self) -> None:
        visible_files = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "CONTRIBUTING.md",
            PROJECT_ROOT / "SECURITY.md",
            PROJECT_ROOT / "CITATION.cff",
        ]
        visible_files.extend(sorted((PROJECT_ROOT / "docs").glob("*.md")))
        forbidden = (
            "entwicklungsarchiv",
            "forschungsnotebook",
            "forschungsstand",
            "masterthesis",
            "physischer betrieb",
            "physisches live-system",
            "hybride fischertechnik",
        )

        for document in visible_files:
            content = document.read_text(encoding="utf-8").lower()
            for term in forbidden:
                with self.subTest(document=document.name, term=term):
                    self.assertNotIn(term, content)

    def test_origin_attribution_is_limited_to_legal_notice(self) -> None:
        allowed = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
        documents = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "CITATION.cff"]
        documents.extend(sorted((PROJECT_ROOT / "docs").glob("*.md")))

        for document in documents:
            content = document.read_text(encoding="utf-8")
            with self.subTest(document=document.name):
                self.assertNotRegex(content, r"(?i)Grum|MarcusGrum")

        legal_notice = allowed.read_text(encoding="utf-8")
        self.assertRegex(legal_notice, r"Marcus Grum")
        self.assertIn("https://github.com/MarcusGrum/AI-CPS", legal_notice)


if __name__ == "__main__":
    unittest.main()
