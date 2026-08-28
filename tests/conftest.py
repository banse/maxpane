"""Shared test-environment isolation."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ignore_callers_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep compositor colour assertions independent of the caller's shell."""
    monkeypatch.delenv("NO_COLOR", raising=False)
