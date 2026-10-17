"""FR-SIM-001 leakage guard: planner-side packages must not reach hidden truth."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "aether"
PLANNER_SIDE = ["belief", "planning", "sensors", "orbit", "ingestion", "api"]
FORBIDDEN_IMPORTS = ("aether.simulation", "aether.evaluation")
FORBIDDEN_ATTRS = {"truth", "cloud_truth", "wind_truth"}
CHECKER_FORBIDDEN = ("aether.planning.cpsat", "aether.planning.policies")


def _python_files(sub):
    return sorted((PKG / sub).rglob("*.py"))


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_planner_side_never_imports_truth():
    for sub in PLANNER_SIDE:
        for path in _python_files(sub):
            tree = ast.parse(path.read_text())
            bad = [m for m in _imports(tree) if m.startswith(FORBIDDEN_IMPORTS)]
            assert not bad, f"{path} imports {bad}"
            attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            assert not attrs & FORBIDDEN_ATTRS, f"{path} touches {attrs & FORBIDDEN_ATTRS}"


def test_checker_is_independent_of_solver():
    checker = PKG / "planning" / "checker.py"
    if not checker.exists():
        return
    bad = [m for m in _imports(ast.parse(checker.read_text())) if m.startswith(CHECKER_FORBIDDEN)]
    assert not bad, f"checker imports solver code: {bad}"
