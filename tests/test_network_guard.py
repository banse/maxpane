"""The suite guard must detect attempts even when clients swallow OSError."""

import json
import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]
CONFTEST = Path(__file__).with_name("conftest.py")


def _inner(pytester, monkeypatch, body, *, prefix="", survey=False):
    # Allows a RED run with the actual historical conftest, without editing it.
    source = Path(os.environ.get("MAXPANE_NETWORK_GUARD_TEST_SOURCE", CONFTEST))
    monkeypatch.delenv("MAXPANE_NETWORK_SURVEY_DIR", raising=False)
    if survey:
        monkeypatch.setenv("MAXPANE_NETWORK_SURVEY_DIR", str(pytester.path / "survey"))
    pytester.makeini("[pytest]\nmarkers = host: deliberately exempt host probe\n")
    pytester.makeconftest(prefix + "\n" + source.read_text(encoding="utf-8"))
    pytester.makepyfile(test_inner=body)
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", "-q")


def test_caught_external_connect_still_fails_at_teardown(pytester, monkeypatch):
    result = _inner(pytester, monkeypatch, '''
        import socket
        def test_caught_connect():
            with socket.socket() as client:
                client.settimeout(0.5)
                try:
                    client.connect(("192.0.2.1", 443))
                except OSError:
                    pass
    ''')
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*external network attempt*192.0.2.1*"])


@pytest.mark.parametrize("call, host", [
    ('socket.getaddrinfo("external.invalid", 443)', "external.invalid"),
    ('socket.gethostbyname("external.invalid")', "external.invalid"),
    ('socket.gethostbyname_ex("external.invalid")', "external.invalid"),
    ('socket.gethostbyaddr("192.0.2.1")', "192.0.2.1"),
    ('socket.getnameinfo(("192.0.2.1", 443), 0)', "192.0.2.1"),
])
def test_external_resolution_never_reaches_resolver(pytester, monkeypatch, call, host):
    # This terminal sentinel prevents any DNS traffic even on the unguarded baseline.
    prefix = '''
import socket
def _unexpected_resolution(*args, **kwargs):
    raise AssertionError("unguarded resolver reached")
for _name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
    setattr(socket, _name, _unexpected_resolution)
'''
    result = _inner(pytester, monkeypatch, f'''
        import socket
        def test_caught_resolution():
            try:
                {call}
            except OSError:
                pass
    ''', prefix=prefix)
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines([f"*external network attempt*{host}*"])


@pytest.mark.parametrize("method, family, address", [
    ("connect_ex", "AF_INET", '("192.0.2.1", 443)'),
    ("connect", "AF_INET6", '("2001:db8::1", 443)'),
])
def test_external_connect_paths_are_refused(pytester, monkeypatch, method, family, address):
    prefix = f'''
import socket
def _unexpected_connect(*args, **kwargs):
    raise AssertionError("unguarded connect reached")
socket.socket.{method} = _unexpected_connect
'''
    result = _inner(pytester, monkeypatch, f'''
        import socket
        def test_caught_connect():
            with socket.socket(socket.{family}) as client:
                try:
                    client.{method}({address})
                except OSError:
                    pass
    ''', prefix=prefix)
    result.assert_outcomes(passed=1, errors=1)


def test_local_hosts_delegate_to_socket_functions(pytester, monkeypatch):
    result = _inner(pytester, monkeypatch, '''
        import socket
        import pytest
        @pytest.mark.parametrize("host", [None, "", "localhost", "LOCALHOST", b"localhost", "127.0.0.1", "127.255.255.254", "::1"])
        def test_local_resolution(host):
            assert socket.getaddrinfo(host, 0) == ["delegated"]
        @pytest.mark.parametrize("family, host", [(socket.AF_INET, "localhost"), (socket.AF_INET, "127.255.255.254"), (socket.AF_INET6, "::1")])
        def test_local_connect(family, host):
            with socket.socket(family) as client:
                assert client.connect((host, 0)) == "delegated"
                assert client.connect_ex((host, 0)) == "delegated"
        def test_unix_delegation():
            with socket.socket(socket.AF_UNIX) as client:
                assert client.connect("/tmp/guard-unused") == "delegated"
    ''', prefix='''
import socket
socket.getaddrinfo = lambda *args, **kwargs: ["delegated"]
socket.socket.connect = lambda *args, **kwargs: "delegated"
socket.socket.connect_ex = lambda *args, **kwargs: "delegated"
''')
    result.assert_outcomes(passed=12)


def test_local_tcp_unix_and_socketpair_stay_usable(pytester, monkeypatch):
    result = _inner(pytester, monkeypatch, '''
        import socket
        import pytest
        @pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
        def test_loopback(host):
            with socket.socket() as server, socket.socket() as client:
                try:
                    server.bind(("127.0.0.1" if host == "localhost" else host, 0))
                except PermissionError:
                    pytest.skip("sandbox forbids local listener; verified separately outside sandbox")
                server.listen()
                client.settimeout(0.5)
                client.connect((host, server.getsockname()[1]))
                peer, _ = server.accept()
                with peer:
                    client.sendall(b"local")
                    assert peer.recv(5) == b"local"
        def test_other_loopback_address():
            # macOS does not configure every 127/8 address, but the guard permits it.
            with socket.socket() as client:
                client.settimeout(0.5)
                try:
                    client.connect(("127.0.0.2", 0))
                except PermissionError:
                    pytest.skip("sandbox forbids local listener; verified separately outside sandbox")
                except OSError:
                    pass
        def test_ipv6_loopback():
            with socket.socket(socket.AF_INET6) as server, socket.socket(socket.AF_INET6) as client:
                try:
                    server.bind(("::1", 0))
                except OSError:
                    pytest.skip("IPv6 loopback unavailable")
                server.listen()
                client.settimeout(0.5)
                assert client.connect_ex(server.getsockname()) == 0
                peer, _ = server.accept()
                peer.close()
        def test_unix(tmp_path):
            with socket.socket(socket.AF_UNIX) as server, socket.socket(socket.AF_UNIX) as client:
                # tmp_path may exceed macOS's 104-byte Unix socket path limit.
                import tempfile
                with tempfile.TemporaryDirectory(dir="/tmp", prefix="guard-") as directory:
                    path = directory + "/s"
                    try:
                        server.bind(path)
                    except PermissionError:
                        pytest.skip("sandbox forbids local listener; verified separately outside sandbox")
                    server.listen()
                    client.connect(path)
                    peer, _ = server.accept()
                    peer.close()
        def test_socketpair():
            a, b = socket.socketpair()
            with a, b:
                a.sendall(b"pair")
                assert b.recv(4) == b"pair"
        @pytest.mark.parametrize("host", [None, ""])
        def test_unspecified_resolution(host):
            assert socket.getaddrinfo(host, 0)
    ''')
    outcomes = result.parseoutcomes()
    assert outcomes.get("failed", 0) == outcomes.get("errors", 0) == 0
    assert outcomes.get("passed", 0) + outcomes.get("skipped", 0) == 8
    if outcomes.get("skipped", 0):
        pytest.skip("local listener unavailable here; run this control outside sandbox")


def test_proxy_settings_cannot_route_tests_to_external_proxy(pytester, monkeypatch):
    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://external.invalid:8080")
    result = _inner(pytester, monkeypatch, '''
        import os
        import urllib.request
        def test_proxy_environment():
            for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
                assert name not in os.environ
            assert os.environ["NO_PROXY"] == os.environ["no_proxy"] == "*"
            assert urllib.request.getproxies() == {"no": "*"}
            assert urllib.request.proxy_bypass("external.invalid")
    ''')
    result.assert_outcomes(passed=1)


def test_host_marker_is_exempt_without_external_traffic(pytester, monkeypatch):
    result = _inner(pytester, monkeypatch, '''
        import socket
        import pytest
        @pytest.mark.host
        def test_host_exemption():
            assert socket.gethostbyname("external.invalid") == "192.0.2.1"
    ''', prefix='''
import socket
socket.gethostbyname = lambda host: "192.0.2.1"
''')
    result.assert_outcomes(passed=1)


def test_survey_still_refuses_and_durably_records_nodeid(pytester, monkeypatch):
    result = _inner(pytester, monkeypatch, '''
        import socket
        import pytest
        def test_survey_attempt():
            with socket.socket() as client:
                client.settimeout(0.5)
                with pytest.raises(OSError):
                    client.connect(("192.0.2.1", 443))
    ''', survey=True)
    result.assert_outcomes(passed=1)
    rows = [json.loads(line) for path in (pytester.path / "survey").glob("*.jsonl")
            for line in path.read_text().splitlines()]
    assert rows == [{"nodeid": "test_inner.py::test_survey_attempt", "host": "192.0.2.1"}]
