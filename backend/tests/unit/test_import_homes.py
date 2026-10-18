"""Config types come from aether.config, never aether.contracts (AGENTS.md rule 17).

Two lanes guessed the other way, so this test exists to fail with the exact fix.
"""

import ast
from pathlib import Path

import aether.config as config_module

BACKEND = Path(__file__).resolve().parents[2]
CONFIG_NAMES = {
    name
    for name, obj in vars(config_module).items()
    if isinstance(obj, type) and obj.__module__ == "aether.config"
}


def test_config_types_imported_from_config():
    wrong = []
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            module = getattr(node, "module", None) or ""
            if isinstance(node, ast.ImportFrom) and module.startswith("aether.contracts"):
                bad = sorted(a.name for a in node.names if a.name in CONFIG_NAMES)
                if bad:
                    wrong.append(f"{path.relative_to(BACKEND)}:{node.lineno} imports {bad}")
    assert not wrong, (
        "Config types live in aether.config. Fix with "
        "`from aether.config import <Name>`:\n" + "\n".join(wrong)
    )
