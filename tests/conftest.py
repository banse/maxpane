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


@pytest.fixture(autouse=True)
def _forbid_external_network(request, monkeypatch):
    """Refuse external I/O and fail even when a client catches the refusal.

    MAXPANE_NETWORK_SURVEY_DIR explicitly selects a blocking, record-only survey.
    Each process writes its own JSONL file, including the owning test's nodeid.
    This in-process fixture cannot cover subprocesses or tests outside tests/.
    """
    import ipaddress
    import json
    import os
    from pathlib import Path
    import socket

    if request.node.get_closest_marker("host"):
        yield
        return

    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    refused = set()
    survey_dir = os.environ.get("MAXPANE_NETWORK_SURVEY_DIR")

    class ExternalNetworkRefused(OSError):
        pass

    def is_local(host):
        if host is None or host == "" or host == b"":
            return True
        if isinstance(host, bytes):
            host = host.decode("ascii", errors="replace")
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(host):
        if is_local(host):
            return
        host = host.decode("ascii", errors="replace") if isinstance(host, bytes) else str(host)
        refused.add(host)
        if survey_dir:
            directory = Path(survey_dir)
            directory.mkdir(parents=True, exist_ok=True)
            worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
            with (directory / f"{worker}-{os.getpid()}.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps({"nodeid": request.node.nodeid, "host": host}) + "\n")
                output.flush()
                os.fsync(output.fileno())
        raise ExternalNetworkRefused(f"external network attempt refused: {host}")

    def guarded_connect(original):
        def connect(client, address):
            if client.family in (socket.AF_INET, socket.AF_INET6):
                check(address[0])
            return original(client, address)
        return connect

    def guarded_resolver(original, *, sockaddr=False):
        def resolve(host, *args, **kwargs):
            check(host[0] if sockaddr else host)
            return original(host, *args, **kwargs)
        return resolve

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, guarded_connect(getattr(socket.socket, name)))
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
        monkeypatch.setattr(socket, name, guarded_resolver(getattr(socket, name), sockaddr=name == "getnameinfo"))
    yield
    if refused and not survey_dir:
        pytest.fail("external network attempt(s): " + ", ".join(sorted(refused)), pytrace=False)
