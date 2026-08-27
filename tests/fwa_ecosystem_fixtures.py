"""Shared deterministic helpers for FWA NETWORK tests.

Every NETWORK work package owns a subdirectory below
``tests/fixtures/fwa/ecosystem``.  This module is the single JSON reader and
provides the common clock and HTTP transport doubles, so no test can silently
fall back to wall time or the public internet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

FWA_ECOSYSTEM_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures" / "fwa" / "ecosystem"
)


def load_fwa_ecosystem_fixture(name: str | Path) -> Any:
    """Load one JSON fixture below :data:`FWA_ECOSYSTEM_FIXTURES`.

    Absolute paths and ``..`` escapes are rejected so a typo cannot make a test
    consume an unrelated developer-local file.
    """

    relative = Path(name)
    if relative.is_absolute():
        raise ValueError("FWA ecosystem fixture path must be relative")
    root = FWA_ECOSYSTEM_FIXTURES.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError("FWA ecosystem fixture path escapes its fixture root")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(slots=True)
class FixedClock:
    """Callable wall-clock double whose time advances only when a test says so."""

    value: float

    def __call__(self) -> float:
        return self.value

    def time(self) -> float:
        """Compatibility alias for collaborators expecting ``clock.time()``."""

        return self.value

    def advance(self, seconds: float) -> float:
        self.value += seconds
        return self.value


class DenyNetworkTransport(httpx.MockTransport):
    """HTTP transport that fails loudly unless a test supplied a handler."""

    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []

        def dispatch(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if handler is None:
                raise AssertionError(
                    "unexpected network request: "
                    f"{request.method} {request.url}"
                )
            return handler(request)

        super().__init__(dispatch)
