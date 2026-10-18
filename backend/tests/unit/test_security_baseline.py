"""INT-09 security baseline (Parameter_2 Part D, P0 subset).

- SEC-IN-007: YAML is only ever loaded with a safe loader.
- SEC-IN-010: no pickle-family deserialization anywhere.
- SEC-IN-011: only allowlisted packages import network libraries; URLs pass the allowlist.
- SEC-SPACE-001: no spacecraft command, uplink or ground-segment code or dependencies.
- SEC-SEC-001: local credential files are git-ignored.

Each AST rule also runs against known-bad snippets, so a rule can't pass vacuously.
"""

from __future__ import annotations

import ast
import re
import socket
import tomllib
from pathlib import Path

import pytest

from aether import netpolicy
from aether.netpolicy import DisallowedURLError, assert_public_address, require_allowed_url

REPO = Path(__file__).resolve().parents[3]
SCANNED_DIRS = ("backend/aether", "backend/tests", "scripts")

UNSAFE_YAML_CALLS = {
    "load",
    "load_all",
    "full_load",
    "full_load_all",
    "unsafe_load",
    "unsafe_load_all",
}
UNSAFE_YAML_LOADERS = {"Loader", "FullLoader", "UnsafeLoader"}
PICKLE_MODULES = {
    "pickle",
    "cPickle",
    "_pickle",
    "joblib",
    "dill",
    "cloudpickle",
    "marshal",
    "shelve",
}
PICKLE_ATTRS = {"read_pickle", "to_pickle"}
NETWORK_MODULES = {
    "requests",
    "httpx",
    "urllib3",
    "aiohttp",
    "socket",
    "http",
    "ftplib",
    "smtplib",
    "earthaccess",
    "cdsapi",
    "paramiko",
}
NETWORK_SUBMODULES = {"urllib.request"}
COMMAND_MODULES = {
    "spacepackets",
    "ccsds",
    "pyccsds",
    "yamcs",
    "openc3",
    "cosmos",
    "fprime",
    "fprime_gds",
    "cfs",
    "cfe",
    "satnogs",
    "gnuradio",
    "serial",
    "can",
    "pymavlink",
    "dronekit",
}
COMMAND_NAME = re.compile(
    r"(telecommand|uplink|tc_frame|command_(spacecraft|satellite)|send_command|tasking_request)",
    re.IGNORECASE,
)


# --- rule implementations --------------------------------------------------------------------


def _root(name: str) -> str:
    return name.split(".")[0]


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            names += [f"{node.module}.{a.name}" for a in node.names]
    return names


def yaml_violations(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "yaml" and node.attr in UNSAFE_YAML_CALLS | UNSAFE_YAML_LOADERS:
                out.append(f"yaml.{node.attr} (use yaml.safe_load)")
        if isinstance(node, ast.ImportFrom) and node.module == "yaml":
            for alias in node.names:
                if alias.name in UNSAFE_YAML_CALLS | UNSAFE_YAML_LOADERS:
                    out.append(f"from yaml import {alias.name}")
    return out


def pickle_violations(tree: ast.AST) -> list[str]:
    out = [f"import {m}" for m in _imported_modules(tree) if _root(m) in PICKLE_MODULES]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in PICKLE_ATTRS:
            out.append(f".{node.attr}")
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "allow_pickle" and not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                ):
                    out.append("allow_pickle enabled")
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "load"
                and isinstance(func.value, ast.Name)
                and func.value.id == "torch"
            ):
                out.append("torch.load")
    return out


def network_imports(tree: ast.AST) -> list[str]:
    return [
        m for m in _imported_modules(tree) if _root(m) in NETWORK_MODULES or m in NETWORK_SUBMODULES
    ]


def command_violations(tree: ast.AST) -> list[str]:
    out = [f"import {m}" for m in _imported_modules(tree) if _root(m) in COMMAND_MODULES]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if COMMAND_NAME.search(node.name):
                out.append(f"definition {node.name!r}")
    return out


# --- repository scans ------------------------------------------------------------------------


def _python_files():
    for folder in SCANNED_DIRS:
        for path in sorted((REPO / folder).rglob("*.py")):
            yield path.relative_to(REPO).as_posix(), ast.parse(path.read_text(), str(path))


@pytest.mark.parametrize(
    "rule", [yaml_violations, pickle_violations, command_violations], ids=lambda f: f.__name__
)
def test_repository_has_no_violations(rule):
    found = {rel: v for rel, tree in _python_files() if (v := rule(tree))}
    assert not found, f"{rule.__name__}: {found}"


def test_network_imports_only_in_allowed_packages():
    this_file = Path(__file__).relative_to(REPO).as_posix()
    found = {}
    for rel, tree in _python_files():
        if rel == this_file or rel.startswith(netpolicy.NETWORK_MODULE_PREFIXES):
            continue
        if bad := network_imports(tree):
            found[rel] = bad
    assert not found, f"network libraries imported outside allowed packages: {found}"


def test_no_command_dependencies_declared():
    project = tomllib.loads((REPO / "backend" / "pyproject.toml").read_text())["project"]
    deps = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        deps += extra
    names = {re.split(r"[<>=!~\[; ]", d, maxsplit=1)[0].lower().replace("-", "_") for d in deps}
    assert not names & COMMAND_MODULES, f"ground-segment dependency: {names & COMMAND_MODULES}"
    assert not names & PICKLE_MODULES, f"pickle-family dependency: {names & PICKLE_MODULES}"


def test_credential_files_are_gitignored():
    ignored = set((REPO / ".gitignore").read_text().split())
    assert {".env", ".env.*", ".netrc", "!.env.example"} <= ignored
    assert (REPO / ".env.example").exists()


def test_env_example_has_no_values_for_secrets():
    for line in (REPO / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if any(word in key for word in ("TOKEN", "KEY", "PASSWORD", "SECRET", "DATABASE_URL")):
                assert value.strip() == "", f"{key} must be blank in .env.example"


# --- the rules catch known-bad code ----------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "snippet"),
    [
        (yaml_violations, "import yaml\nyaml.load(open('x'))"),
        (yaml_violations, "import yaml\nyaml.load(s, Loader=yaml.FullLoader)"),
        (yaml_violations, "from yaml import unsafe_load"),
        (pickle_violations, "import pickle"),
        (pickle_violations, "from joblib import load"),
        (pickle_violations, "import numpy as np\nnp.load('a.npy', allow_pickle=True)"),
        (pickle_violations, "import pandas as pd\npd.read_pickle('x')"),
        (pickle_violations, "import torch\ntorch.load('m.pt')"),
        (network_imports, "import requests"),
        (network_imports, "from urllib.request import urlopen"),
        (network_imports, "import http.client"),
        (command_violations, "import spacepackets"),
        (command_violations, "from yamcs.client import YamcsClient"),
        (command_violations, "def build_tc_frame(x):\n    pass"),
        (command_violations, "class UplinkQueue:\n    pass"),
    ],
)
def test_rules_catch_bad_code(rule, snippet):
    assert rule(ast.parse(snippet))


@pytest.mark.parametrize(
    ("rule", "snippet"),
    [
        (yaml_violations, "import yaml\nyaml.safe_load(open('x'))"),
        (pickle_violations, "import numpy as np\nnp.load('a.npy', allow_pickle=False)"),
        (network_imports, "from urllib.parse import urlsplit"),
        (command_violations, "def plan_virtual_acquisitions():\n    pass"),
    ],
)
def test_rules_allow_safe_code(rule, snippet):
    assert not rule(ast.parse(snippet))


# --- outbound URL policy ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=EMITL2BCH4PLM",
        "https://api.carbonmapper.org/api/v1/catalog/plumes",
        "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=json",
        "https://CMR.EARTHDATA.NASA.GOV./search",
    ],
)
def test_allowed_urls(url):
    assert require_allowed_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://cmr.earthdata.nasa.gov/search",  # not https
        "https://user:pw@cmr.earthdata.nasa.gov/",  # embedded credentials
        "https://cmr.earthdata.nasa.gov:8443/",  # non-default port
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata IP literal
        "https://[::1]/",  # IPv6 loopback literal
        "https://evil.celestrak.org/",  # subdomain of an allowed host
        "https://celestrak.org.evil.example/",  # suffix trick
        "https://example.com/",  # not allowlisted
        "file:///etc/passwd",
    ],
)
def test_disallowed_urls(url):
    with pytest.raises(DisallowedURLError):
        require_allowed_url(url)


def _fake_resolver(addresses):
    def fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]

    return fake


def test_public_resolution_passes(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolver(["8.8.8.8"]))
    assert assert_public_address("celestrak.org") == ["8.8.8.8"]


@pytest.mark.parametrize("addr", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1"])
def test_private_resolution_is_rejected(monkeypatch, addr):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolver(["8.8.8.8", addr]))
    with pytest.raises(DisallowedURLError):
        assert_public_address("celestrak.org")
