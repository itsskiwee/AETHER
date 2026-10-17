"""Every PR-* parameter ID cited in configs or code must exist in Parameter_Register.md.

lessons.md 1.1: a config comment citing a parameter that has no register row is a dangling claim.
Ranges in the register ("PR-V10..V13", "PR-A10-12", "PR-W05/06") count for every ID inside them.
"""

import re

ID = re.compile(r"PR-([A-Z])(\d{2})")
RANGE = re.compile(r"PR-([A-Z])(\d{2})\s*(?:\.\.|\u2013|-|/)\s*(?:PR-)?\1?(\d{2})")


def _register_ids(text):
    ids = {f"PR-{p}{n}" for p, n in ID.findall(text)}
    for prefix, lo, hi in RANGE.findall(text):
        ids |= {f"PR-{prefix}{i:02d}" for i in range(int(lo), int(hi) + 1)}
    return ids


def test_no_dangling_parameter_ids(repo_root):
    register = _register_ids((repo_root / "Implementation" / "Parameter_Register.md").read_text())
    cited = {}
    for folder in ("configs", "backend/aether", "experiments", "scripts"):
        for path in (repo_root / folder).rglob("*"):
            if path.suffix in {".yaml", ".py", ".md"} and path.is_file():
                text = path.read_text()
                for p, lo, hi in RANGE.findall(text):
                    for i in range(int(lo), int(hi) + 1):
                        cited.setdefault(f"PR-{p}{i:02d}", path)
                for p, n in ID.findall(text):
                    cited.setdefault(f"PR-{p}{n}", path)
    dangling = {k: str(v.relative_to(repo_root)) for k, v in cited.items() if k not in register}
    assert not dangling, f"IDs missing from Parameter_Register.md: {dangling}"
