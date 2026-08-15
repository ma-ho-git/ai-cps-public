#!/usr/bin/env python3
"""Verbindliche Lesbarkeitsgrenzen fuer Runtime und Tests pruefen."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = Path("scenarios/serve_ft_nns_external_broker/x86_64")
FLOW_FILE = SCENARIO / "node_red/flows.json"
SHELL_FILE = Path("tools/run_nodered_orchestration.sh")
PYTHON_ROOTS = (Path("tools"), Path("training"), SCENARIO, Path("tests"))
DEAD_JS_FILES = (
    "bootstrap.js", "hmi.js", "orchestration.js", "reporting.js", "virtual_factory.js",
)
INFO_SECTIONS = (
    "### Aufgabe", "### Eingang", "### Zustand", "### Ausgang",
    "### Warum Function-Node?",
)
TYPED_VALUE_KEYS = {"tot": "to", "fromt": "from", "pt": "p", "vt": "v"}


@dataclass(frozen=True)
class Issue:
    """Ein lesbarer Pruefbefund."""

    location: str
    detail: str

    def __str__(self) -> str:
        return f"{self.location}: {self.detail}"


def iter_python_files(root: Path) -> list[Path]:
    """Python-Dateien im festgelegten Scope sammeln."""
    files: set[Path] = set()
    for relative in PYTHON_ROOTS:
        base = root / relative
        if base.exists():
            files.update(base.rglob("*.py"))
    return sorted(path for path in files if "__pycache__" not in path.parts)


def function_limit(path: Path, name: str) -> int:
    """Grenze fuer Produktion, Callback oder Test bestimmen."""
    if path.parts[0] == "tests" and name.startswith("test_"):
        return 40
    if name == "main" or name.startswith("on_"):
        return 40
    return 60


def scan_python_file(root: Path, path: Path) -> list[Issue]:
    """Funktionslaengen einer Python-Datei pruefen."""
    relative = path.relative_to(root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
    except SyntaxError as error:
        return [Issue(str(relative), f"ungueltiges Python: {error.msg}")]
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        size = (node.end_lineno or node.lineno) - node.lineno + 1
        limit = function_limit(relative, node.name)
        if size > limit:
            location = f"{relative}:{node.lineno} {node.name}()"
            issues.append(Issue(location, f"{size} Zeilen; erlaubt {limit}"))
    return issues


def scan_python(root: Path) -> list[Issue]:
    """Alle Python-Fundstellen zusammenfassen."""
    issues: list[Issue] = []
    for path in iter_python_files(root):
        issues.extend(scan_python_file(root, path))
    return issues


def shell_function_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """Top-Level-Shellfunktionen ueber ihre Startzeilen abgrenzen."""
    starts: list[tuple[int, str]] = []
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\) \{")
    for index, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if match:
            starts.append((index, match.group(1)))
    spans: list[tuple[str, int, int]] = []
    for index, (start, name) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else len(lines) + 1
        spans.append((name, start, next_start - start))
    return spans


def scan_shell(root: Path) -> list[Issue]:
    """Shellfunktionen gegen die Produktionsgrenze pruefen."""
    path = root / SHELL_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: list[Issue] = []
    for name, start, size in shell_function_spans(lines):
        limit = 40 if name == "main" else 60
        if size > limit:
            issues.append(Issue(f"{SHELL_FILE}:{start} {name}()", f"{size} Zeilen; erlaubt {limit}"))
    return issues


def iter_jsonata(value: object) -> list[str]:
    """Typed-Input-JSONata aus verschachtelten Flowobjekten lesen."""
    expressions: list[str] = []
    if isinstance(value, list):
        for item in value:
            expressions.extend(iter_jsonata(item))
        return expressions
    if not isinstance(value, dict):
        return expressions
    for key, item in value.items():
        expression_key = TYPED_VALUE_KEYS.get(key)
        if expression_key is None and key.endswith("Type"):
            expression_key = key[:-4]
        if item == "jsonata" and isinstance(value.get(expression_key), str):
            expressions.append(value[expression_key])
        expressions.extend(iter_jsonata(item))
    return expressions


def scan_function_node(node: dict) -> list[Issue]:
    """Eine Function-Ausnahme auf Groesse und Hilfe pruefen."""
    issues: list[Issue] = []
    node_id = node.get("id", "<ohne-id>")
    size = len(node.get("func", "").splitlines())
    if size > 40:
        issues.append(Issue(node_id, f"Function-Node hat {size} Codezeilen; erlaubt 40"))
    info = node.get("info", "")
    missing = [section for section in INFO_SECTIONS if section not in info]
    if missing:
        issues.append(Issue(node_id, "Hilfetext fehlt: " + ", ".join(missing)))
    return issues


def scan_flow(root: Path) -> list[Issue]:
    """Function-Ausnahmen und JSONata-Grenze pruefen."""
    flow_path = root / FLOW_FILE
    flows = json.loads(flow_path.read_text(encoding="utf-8"))
    functions = [node for node in flows if node.get("type") == "function"]
    issues: list[Issue] = []
    if len(functions) != 4:
        issues.append(Issue(str(FLOW_FILE), f"{len(functions)} Function-Nodes; erwartet 4"))
    for node in functions:
        issues.extend(scan_function_node(node))
    for index, expression in enumerate(iter_jsonata(flows), start=1):
        if len(expression) > 200:
            issues.append(Issue(f"{FLOW_FILE} JSONata #{index}", f"{len(expression)} Zeichen; erlaubt 200"))
    return issues


def scan_dead_paths(root: Path) -> list[Issue]:
    """Entfernte Referenzkerne duerfen nicht wiederkehren."""
    base = root / SCENARIO / "node_red/lib"
    return [
        Issue(str(path.relative_to(root)), "entfernter Referenzkern wieder vorhanden")
        for name in DEAD_JS_FILES
        if (path := base / name).exists()
    ]


def check_repository(root: Path = ROOT) -> list[Issue]:
    """Alle automatischen Lesbarkeitschecks ausfuehren."""
    issues = scan_python(root)
    issues.extend(scan_shell(root))
    issues.extend(scan_flow(root))
    issues.extend(scan_dead_paths(root))
    return issues


def main() -> int:
    """Befunde kompakt fuer lokale Nutzung und CI ausgeben."""
    issues = check_repository()
    if issues:
        print("Lesbarkeitspruefung fehlgeschlagen:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Lesbarkeitspruefung erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
