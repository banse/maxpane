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


@pytest.fixture(autouse=True)
def _forbid_real_browser(monkeypatch):
    """No test may open the developer's browser (PRD §7 E8).

    Textual's ``App.open_url`` reaches ``webbrowser.open`` even under
    ``run_test`` (``Driver.open_url`` imports ``webbrowser`` lazily, so a
    patch on the module attribute is what it sees). A pilot test that clicks
    a linked address uses ``tests/widgets/address_probe.LinkRecorder``.
    """

    def _refuse(url, *args, **kwargs):
        raise AssertionError(f"a test reached the real browser: {url!r}")

    monkeypatch.setattr("webbrowser.open", _refuse)


@pytest.fixture(autouse=True)
def _no_pepepane_env(monkeypatch):
    """No test inherits a ``PEPEPANE_*`` variable from the developer's shell (spec §14 Rules).

    ``seat_cli`` reads ``PEPEPANE_HOST`` / ``_UNIT`` / ``_CONTAINER`` / ``_BROKER`` /
    ``_SEAT`` / ``_AGENT`` / ``_OFFLINE`` / ``_CONFIG`` as configuration; a suite that saw
    the operator's real broker socket or seat would test the wrong machine. Every CLI
    test also passes ``env={}`` explicitly (contract §E); this fixture is the belt.
    """
    import os  # local: tests/conftest.py is append-only at its end (contract §A.3)

    for name in [key for key in os.environ if key.startswith("PEPEPANE_")]:
        monkeypatch.delenv(name, raising=False)
