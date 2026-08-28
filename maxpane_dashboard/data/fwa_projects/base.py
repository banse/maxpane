"""Frozen project-manifest boundary and local ABI resource helpers.

This module performs no network I/O.  A project adapter may load a vendored ABI
from the package, but it can never discover or download one at runtime.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from maxpane_dashboard.data.fwa_ecosystem_models import PROJECT_FAMILIES

_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_CODEHASH_RE = re.compile(r"^0x[0-9a-f]{64}$")
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_ABI_ROOT = (_PACKAGE_ROOT / "abis" / "fwa").resolve()

SourceStatus = Literal["verified", "unverified"]
Dependency = tuple[str, str]


class ProjectManifest(BaseModel):
    """Immutable discovery and integrity facts for one deployed surface."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    family: str
    surface: str
    version: str
    role: str
    address: str
    deployment_block: int
    abi_resource: str
    runtime_codehash: str
    source_status: SourceStatus
    is_current: bool
    dependencies: tuple[Dependency, ...] = ()

    @field_validator("surface", "version", "role")
    @classmethod
    def _nonempty_identifier(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("manifest identifiers must be non-empty and trimmed")
        return value

    @field_validator("family")
    @classmethod
    def _known_family(cls, value: str) -> str:
        if value not in PROJECT_FAMILIES:
            raise ValueError(f"unknown project family: {value!r}")
        return value

    @field_validator("address")
    @classmethod
    def _normalized_address(cls, value: str) -> str:
        if not _ADDRESS_RE.fullmatch(value):
            raise ValueError("address must be a lowercase 20-byte hex address")
        return value

    @field_validator("deployment_block")
    @classmethod
    def _positive_block(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("deployment_block must be positive")
        return value

    @field_validator("runtime_codehash")
    @classmethod
    def _normalized_codehash(cls, value: str) -> str:
        if not _CODEHASH_RE.fullmatch(value):
            raise ValueError("runtime_codehash must be a lowercase bytes32 value")
        return value

    @field_validator("abi_resource")
    @classmethod
    def _safe_abi_resource(cls, value: str) -> str:
        if not value.startswith("abis/fwa/") or not value.endswith(".json"):
            raise ValueError("ABI resources must live under abis/fwa and end in .json")
        parts = Path(value).parts
        if ".." in parts or "." in parts:
            raise ValueError("ABI resource traversal is forbidden")
        return value

    @field_validator("dependencies")
    @classmethod
    def _valid_dependencies(
        cls, dependencies: tuple[Dependency, ...]
    ) -> tuple[Dependency, ...]:
        getters: set[str] = set()
        for getter, expected_address in dependencies:
            if not getter or getter.strip() != getter:
                raise ValueError("dependency getter names must be non-empty and trimmed")
            if getter in getters:
                raise ValueError(f"duplicate dependency getter: {getter}")
            if not _ADDRESS_RE.fullmatch(expected_address):
                raise ValueError("dependency addresses must be lowercase 20-byte hex")
            getters.add(getter)
        return dependencies


def resolve_abi_resource(resource: str) -> Path:
    """Resolve one package-relative ABI path without permitting traversal."""

    candidate = (_PACKAGE_ROOT / resource).resolve()
    if candidate.parent != _ABI_ROOT or candidate.suffix != ".json":
        raise ValueError(f"invalid FWA ABI resource: {resource!r}")
    return candidate


def load_abi_resource(resource: str) -> tuple[dict[str, Any], ...]:
    """Load and minimally validate a vendored read/event ABI."""

    path = resolve_abi_resource(resource)
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"ABI resource is not a non-empty array: {resource}")
    if not all(isinstance(entry, dict) for entry in payload):
        raise ValueError(f"ABI resource contains a non-object entry: {resource}")
    return tuple(payload)


def load_manifest_abi(manifest: ProjectManifest) -> tuple[dict[str, Any], ...]:
    """Load the local ABI declared by *manifest*."""

    return load_abi_resource(manifest.abi_resource)


__all__ = [
    "Dependency",
    "ProjectManifest",
    "SourceStatus",
    "load_abi_resource",
    "load_manifest_abi",
    "resolve_abi_resource",
]
