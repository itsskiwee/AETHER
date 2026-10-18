"""Hash-verified loader for immutable, local plume datasets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aether.contracts.models import PlumeObservation


class PinnedDatasetError(ValueError):
    """A pinned dataset is missing, malformed, or differs from its manifest."""


@dataclass(frozen=True)
class PinnedPlumeDataset:
    dataset_id: str
    manifest_path: str
    manifest_sha256: str
    normalized_sha256: str
    raw_file_count: int
    plumes: tuple[PlumeObservation, ...]


def load_pinned_plume_dataset(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    repo_root: str | Path,
    verify_raw: bool = True,
) -> PinnedPlumeDataset:
    """Load only the normalized records and raw files listed by a repository manifest.

    All paths are repository-relative. The expected manifest digest is checked before trusting
    any path in it; file paths are then constrained to the resolved repository root. The loader
    never accesses the network or scans the raw dataset directory.
    """
    root = Path(repo_root).resolve()
    manifest_value = Path(manifest_path)
    if manifest_value.is_absolute():
        manifest_file = manifest_value.resolve()
        try:
            manifest_rel = manifest_file.relative_to(root).as_posix()
        except ValueError as exc:
            raise PinnedDatasetError("manifest_path must stay inside repo_root") from exc
    else:
        manifest_rel = _repo_relative(manifest_path, "manifest_path")
        manifest_file = _resolve_under_root(root, manifest_rel, "manifest")
    manifest_bytes = _read_bytes(manifest_file, "manifest")
    actual_manifest_sha256 = _digest(manifest_bytes)
    _require_sha(expected_manifest_sha256, actual_manifest_sha256, "manifest")

    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinnedDatasetError(f"manifest is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PinnedDatasetError("manifest root must be an object")
    if manifest.get("schema_version") != 1:
        raise PinnedDatasetError("unsupported manifest schema_version")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise PinnedDatasetError("manifest dataset_id must be a non-empty string")

    raw_files = manifest.get("raw_files")
    if not isinstance(raw_files, list):
        raise PinnedDatasetError("manifest raw_files must be an array")
    provider = _required_text(manifest.get("provider"), "manifest provider")
    dataset = _required_text(manifest.get("dataset"), "manifest dataset")
    version = _required_text(manifest.get("version"), "manifest version")
    seen_paths: set[str] = set()
    raw_roles_by_id: dict[str, set[str]] = {}
    metadata_sha256_by_id: dict[str, str] = {}
    for index, record in enumerate(raw_files):
        if not isinstance(record, dict):
            raise PinnedDatasetError(f"raw_files[{index}] must be an object")
        rel = _repo_relative(record.get("path"), f"raw_files[{index}].path")
        if rel in seen_paths:
            raise PinnedDatasetError(f"duplicate raw file path {rel!r}")
        seen_paths.add(rel)
        role = record.get("role")
        if role not in {"metadata", "raster"}:
            raise PinnedDatasetError(f"raw_files[{index}].role must be metadata or raster")
        native_id = _required_text(record.get("native_id"), f"raw_files[{index}].native_id")
        roles = raw_roles_by_id.setdefault(native_id, set())
        if role in roles:
            raise PinnedDatasetError(
                f"duplicate {role} raw file for native_id {native_id!r} in manifest"
            )
        roles.add(role)
        expected_sha256 = record.get("sha256")
        if (
            not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise PinnedDatasetError(f"raw_files[{index}].sha256 must be a lowercase SHA-256")
        expected_size = record.get("size_bytes")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise PinnedDatasetError(f"raw_files[{index}].size_bytes must be a nonnegative integer")
        if role == "metadata":
            metadata_sha256_by_id[native_id] = expected_sha256
        if verify_raw:
            file_path = _resolve_under_root(root, rel, f"raw_files[{index}]")
            actual_size = file_path.stat().st_size
            if actual_size != expected_size:
                raise PinnedDatasetError(f"raw file size mismatch for {rel!r}")
            actual_sha256 = _file_digest(file_path)
            _require_sha(expected_sha256, actual_sha256, f"raw file {rel!r}")
    incomplete_raw_pairs = sorted(
        native_id for native_id, roles in raw_roles_by_id.items() if roles != {"metadata", "raster"}
    )
    if incomplete_raw_pairs:
        raise PinnedDatasetError(
            "raw_files must contain exactly one metadata and raster per native_id; "
            f"incomplete entries: {incomplete_raw_pairs!r}"
        )

    normalized = manifest.get("normalized")
    if not isinstance(normalized, dict):
        raise PinnedDatasetError("manifest normalized must be an object")
    normalized_rel = _repo_relative(normalized.get("path"), "normalized.path")
    normalized_file = _resolve_under_root(root, normalized_rel, "normalized input")
    normalized_bytes = _read_bytes(normalized_file, "normalized input")
    actual_normalized_sha256 = _digest(normalized_bytes)
    _require_sha(normalized.get("sha256"), actual_normalized_sha256, "normalized input")
    expected_normalized_size = normalized.get("size_bytes")
    if expected_normalized_size is not None and (
        isinstance(expected_normalized_size, bool)
        or not isinstance(expected_normalized_size, int)
        or expected_normalized_size != len(normalized_bytes)
    ):
        raise PinnedDatasetError("normalized input size mismatch")
    try:
        records = json.loads(normalized_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinnedDatasetError(f"normalized input is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(records, list):
        raise PinnedDatasetError("normalized input root must be an array")
    expected_count = normalized.get("record_count")
    if (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count != len(records)
    ):
        raise PinnedDatasetError("normalized record_count differs from manifest")

    plumes = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        try:
            plume = PlumeObservation.model_validate(record)
        except Exception as exc:
            raise PinnedDatasetError(
                f"normalized record {index} fails PlumeObservation validation: {exc}"
            ) from exc
        if plume.id in seen_ids:
            raise PinnedDatasetError(f"duplicate normalized plume id {plume.id!r}")
        seen_ids.add(plume.id)
        if plume.native_id not in raw_roles_by_id:
            raise PinnedDatasetError(
                f"normalized native ID {plume.native_id!r} has no raw files in manifest"
            )
        if metadata_sha256_by_id.get(plume.native_id) != plume.source.sha256:
            raise PinnedDatasetError(
                f"normalized source hash for {plume.native_id!r} does not match its metadata file"
            )
        if (
            plume.provider != provider
            or plume.source.provider != provider
            or plume.source.dataset != dataset
            or plume.source.version != version
            or plume.dataset_version != version
        ):
            raise PinnedDatasetError(
                f"normalized source identity for {plume.native_id!r} differs from manifest"
            )
        plumes.append(plume)

    sorted_plumes = sorted(plumes, key=lambda plume: plume.id)
    if [plume.id for plume in plumes] != [plume.id for plume in sorted_plumes]:
        raise PinnedDatasetError("normalized records must be sorted by id")
    if set(metadata_sha256_by_id) != {plume.native_id for plume in plumes}:
        raise PinnedDatasetError("metadata native IDs differ from normalized plume records")

    return PinnedPlumeDataset(
        dataset_id=dataset_id,
        manifest_path=manifest_rel,
        manifest_sha256=actual_manifest_sha256,
        normalized_sha256=actual_normalized_sha256,
        raw_file_count=len(raw_files),
        plumes=tuple(plumes),
    )


def _repo_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PinnedDatasetError(f"{label} must be a non-empty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PinnedDatasetError(f"{label} must stay inside the repository")
    return path.as_posix()


def _resolve_under_root(root: Path, relative: str, label: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PinnedDatasetError(f"{label} path escapes the repository") from exc
    if not candidate.is_file():
        raise PinnedDatasetError(f"{label} file is missing: {relative}")
    return candidate


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PinnedDatasetError(f"cannot read {label}: {exc}") from exc


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PinnedDatasetError(f"cannot hash file {path}: {exc}") from exc
    return digest.hexdigest()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_sha(expected: Any, actual: str, label: str) -> None:
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise PinnedDatasetError(f"{label} SHA-256 must be 64 lowercase hexadecimal characters")
    if actual != expected:
        raise PinnedDatasetError(f"{label} SHA-256 mismatch")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PinnedDatasetError(f"{label} must be a non-empty string")
    return value
