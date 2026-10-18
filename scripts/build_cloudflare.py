"""Prepare provider and replay snapshots, then build the static Cloudflare assets."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def main() -> int:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        print("npm is required to build the Cloudflare frontend.", file=sys.stderr)
        return 1

    if run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            "backend[api,dev,geo]",
        ]
    ):
        return 1
    if run([npm, "--prefix", "frontend", "ci"]):
        return 1

    with tempfile.TemporaryDirectory(prefix="aether-cloudflare-") as temp_dir:
        context_path = Path(temp_dir) / "live-context.json"
        context_result = run(
            [sys.executable, "scripts/live_context.py", "--output", str(context_path)]
        )
        if context_result:
            print(
                "Public provider refresh failed; publishing its explicit unavailable state.",
                file=sys.stderr,
            )

        env = os.environ.copy()
        env["AETHER_LIVE_CONTEXT"] = str(context_path)
        return run([npm, "run", "build:cloudflare"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
