"""Suite-wide guards. Every test runs under these."""

import pytest


@pytest.fixture(autouse=True)
def _forbid_real_clipboard(monkeypatch):
    """No test may spawn pbcopy / xclip / wl-copy / xsel / clip.

    A headless suite that overwrote the developer's clipboard would be the
    MANAGER_ATTRS cache-overwrite hazard in a new place (PRD §7 E5).
    """

    async def _refuse(cmd, data):
        raise AssertionError(f"a test reached the real clipboard: {cmd!r}")

    monkeypatch.setattr("maxpane_dashboard.clipboard._run", _refuse)
