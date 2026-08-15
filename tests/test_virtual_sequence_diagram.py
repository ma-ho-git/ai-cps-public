"""Prueft die drei editierbaren Darstellungen des virtuellen Ablaufs."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UML = ROOT / "docs/assets/uml"


class VirtualSequenceDiagramTests(unittest.TestCase):
    def test_drawio_and_svg_are_valid_xml(self):
        ET.parse(UML / "nodered_mqtt_virtual_sequence.drawio")
        ET.parse(UML / "nodered_mqtt_virtual_sequence.svg")

    def test_all_sources_show_the_modular_virtual_roles(self):
        sources = [
            (UML / "nodered_mqtt_virtual_sequence.drawio").read_text(encoding="utf-8"),
            (UML / "nodered_mqtt_virtual_sequence.svg").read_text(encoding="utf-8"),
            (UML / "nodered_mqtt_virtual_sequence.puml").read_text(encoding="utf-8"),
        ]
        for source in sources:
            with self.subTest(source=source[:20]):
                for label in (
                    "Initialisierung", "Zustands-Flow", "Semaphor-Flow",
                    "KI-Flow", "Modul-Flows", "Storage-NN", "VGR-NN", "HBW-NN",
                ):
                    self.assertIn(label, source)
                self.assertIn("Rohzustand", source)
                self.assertIn("50 ms", source)

    def test_plantuml_keeps_parallel_inference_and_async_messages(self):
        source = (UML / "nodered_mqtt_virtual_sequence.puml").read_text(encoding="utf-8")
        self.assertIn("loop Testszenario", source)
        self.assertIn("par VGR: Inferenz + Command", source)
        self.assertIn("->>", source)
        self.assertIn("4 Jobcounterpaare", source)


if __name__ == "__main__":
    unittest.main()
