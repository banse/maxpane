"""``--version`` must report the build that is actually running.

The flag exists because of a failure that had no symptom.  ``pipx`` and ``uv``
both expose their shims from ``~/.local/bin``, and neither will overwrite a
``maxpane`` it does not own -- the second installer prints a warning and
declines.  So a ``pipx install maxpane`` can succeed, report the new version,
and leave a months-old ``uv`` build still answering to ``maxpane``.  Nothing in
the app said which one you were running: the version was rendered in the status
bar, where you could only see it *after* launching the very binary whose
identity was in question.

Hence the two invariants pinned here: the flag prints the version the running
code would report, and it names the interpreter that is running it.

The parser is driven for real -- ``main()`` with a patched ``sys.argv`` -- for
the same reason ``test_cli_poll_interval`` does it: a test that called
``_version_text()`` directly would pass even if nothing wired it to a flag.

No Textual app is started and no network is touched.
"""

from __future__ import annotations

import importlib
import platform
import sys

import pytest

from maxpane_dashboard import __version__


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, recording what it did."""
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):  # never starts a real TUI
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(
        cli, "_maximize_terminal", lambda *a, **k: captured.update(maximized=True)
    )
    monkeypatch.setattr(
        cli.logging, "basicConfig", lambda **kw: captured.update(logging_configured=True)
    )
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


def _version_output(monkeypatch, capsys, flag: str) -> str:
    """Run the flag, assert it exited cleanly, return what it printed."""
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, [flag])

    assert exc.value.code == 0, (
        f"{flag} is a successful query, not a usage error (got exit "
        f"{exc.value.code})"
    )
    out = capsys.readouterr()
    assert out.out, f"{flag} printed nothing to stdout"
    assert not out.err, (
        f"{flag} must print to stdout so it can be piped; wrote to stderr: "
        f"{out.err!r}"
    )
    return out.out


# ---------------------------------------------------------------------------
# what it prints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_reports_the_running_version(monkeypatch, capsys, flag) -> None:
    """Both spellings print the version the rest of the app would render."""
    first_line = _version_output(monkeypatch, capsys, flag).splitlines()[0]

    assert first_line == f"maxpane {__version__}", (
        "the first line is the machine-readable one -- `--version | head -1` "
        f"must stay exactly 'maxpane <version>', got {first_line!r}"
    )


def test_version_matches_the_packaged_metadata(monkeypatch, capsys) -> None:
    """The printed number is the distribution's, not a second hardcoded copy.

    Guards the obvious wrong fix: a module-level ``VERSION = "0.5.0"`` that
    drifts from ``pyproject.toml`` the first time someone bumps a release.
    """
    from importlib.metadata import version as dist_version

    printed = _version_output(monkeypatch, capsys, "--version").splitlines()[0]

    assert printed == f"maxpane {dist_version('maxpane')}"


def test_version_keeps_its_two_lines(monkeypatch, capsys) -> None:
    """Regression: argparse's own ``action="version"`` reflows the text.

    It hands the string to the help formatter's ``_fill_text`` --
    ``textwrap.fill`` -- which eats the newline and produces
    ``maxpane 0.5.0 Python 3.14.4 (/path/to/python)`` on one line, so
    ``--version | head -1`` returns the interpreter path glued to the version.
    Switching this flag back to ``action="version"`` turns this red.
    """
    lines = _version_output(monkeypatch, capsys, "--version").splitlines()

    assert len(lines) == 2, f"expected version + interpreter lines, got {lines!r}"
    assert lines[0].count(" ") == 1, (
        f"the parseable line must be just 'maxpane <version>', got {lines[0]!r}"
    )
    assert "Python" not in lines[0], (
        "interpreter details leaked onto the machine-readable first line -- "
        "the text was reflowed"
    )


def test_version_names_the_interpreter(monkeypatch, capsys) -> None:
    """The whole point: which install is answering to ``maxpane``.

    Without ``sys.executable`` here, a stale uv shim and a fresh pipx venv are
    indistinguishable from the command line.
    """
    output = _version_output(monkeypatch, capsys, "--version")

    assert sys.executable in output, (
        "the interpreter path is what disambiguates two competing installs; "
        f"missing from: {output!r}"
    )
    assert platform.python_version() in output, (
        "the Python version should be named too"
    )


def test_version_is_a_real_version_not_the_fallback(monkeypatch, capsys) -> None:
    """A published build must never print the not-installed marker.

    ``__init__`` degrades to ``0+unknown`` when there is no distribution
    metadata.  That is correct for a bare source checkout and wrong for
    anything a user installed -- and the tests run against an installed
    package.
    """
    first_line = _version_output(monkeypatch, capsys, "--version").splitlines()[0]
    number = first_line.removeprefix("maxpane ")

    assert number != "0+unknown", (
        "the package under test has no metadata -- reinstall with "
        "`pip install -e .`"
    )
    assert number[:1].isdigit(), f"not a version number: {number!r}"


# ---------------------------------------------------------------------------
# what it must not do
# ---------------------------------------------------------------------------


def test_version_does_not_start_the_app(monkeypatch, capsys) -> None:
    """Asking which build this is must not launch it."""
    captured: dict = {}

    with pytest.raises(SystemExit):
        import maxpane_dashboard.__main__ as cli

        class _Explode:
            def __init__(self, **kwargs):
                raise AssertionError("--version constructed MaxPaneApp")

        monkeypatch.setattr(cli, "MaxPaneApp", _Explode)
        monkeypatch.setattr(cli, "_maximize_terminal", lambda *a, **k: None)
        monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
        monkeypatch.setattr(cli.sys, "argv", ["maxpane", "--version"])
        cli.main()

    assert "ran" not in captured
    capsys.readouterr()


def test_version_does_not_resize_the_terminal(monkeypatch, capsys) -> None:
    """``_maximize_terminal`` fullscreens the window and resets the font size.

    Doing that to someone who typed ``maxpane --version`` would be rude, and
    on Terminal.app it shells out to ``osascript``.  argparse exiting inside
    ``parse_args()`` is what prevents it; this pins that ordering.
    """
    captured: dict = {}

    with pytest.raises(SystemExit):
        import maxpane_dashboard.__main__ as cli

        monkeypatch.setattr(cli, "MaxPaneApp", object)
        monkeypatch.setattr(
            cli, "_maximize_terminal", lambda *a, **k: captured.update(maximized=True)
        )
        monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
        monkeypatch.setattr(cli.sys, "argv", ["maxpane", "--version"])
        cli.main()

    assert "maximized" not in captured
    capsys.readouterr()


def test_version_does_not_truncate_the_log(monkeypatch, capsys) -> None:
    """The sharp edge: ``basicConfig`` opens the log with ``filemode="w"``.

    A ``--version`` handled after logging setup would wipe
    ``~/.maxpane/maxpane.log`` -- destroying the diagnostics of the run the
    user is probably trying to debug -- every single time they checked their
    version.  ``action="version"`` exits during ``parse_args()``, before that
    line is reached.  Move the flag below it and this goes red.
    """
    captured: dict = {}

    with pytest.raises(SystemExit):
        import maxpane_dashboard.__main__ as cli

        monkeypatch.setattr(cli, "MaxPaneApp", object)
        monkeypatch.setattr(cli, "_maximize_terminal", lambda *a, **k: None)
        monkeypatch.setattr(
            cli.logging,
            "basicConfig",
            lambda **kw: captured.update(logging_configured=True),
        )
        monkeypatch.setattr(cli.sys, "argv", ["maxpane", "--version"])
        cli.main()

    assert "logging_configured" not in captured, (
        "--version reached logging.basicConfig, which opens the log file with "
        "filemode='w' and would truncate it"
    )
    capsys.readouterr()


def test_normal_startup_still_configures_logging(monkeypatch) -> None:
    """The counterweight to the test above.

    Proves the previous assertion passes because ``--version`` exits early,
    not because logging setup stopped happening at all.
    """
    captured = _run_cli(monkeypatch, [])

    assert captured.get("logging_configured") is True
    assert captured.get("maximized") is True
    assert captured.get("ran") is True


# ---------------------------------------------------------------------------
# the no-metadata fallback
# ---------------------------------------------------------------------------


def test_missing_metadata_degrades_instead_of_crashing(monkeypatch) -> None:
    """A source checkout with nothing installed must still import.

    ``__init__`` used to call ``version("maxpane")`` unguarded.  Every widget
    module imports the package, so in a fresh clone the failure surfaced as an
    import-time ``PackageNotFoundError`` -- not as anything naming the actual
    problem.
    """
    import importlib.metadata as md

    def _absent(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", _absent)

    import maxpane_dashboard

    reloaded = importlib.reload(maxpane_dashboard)
    try:
        assert reloaded.__version__ == "0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(maxpane_dashboard)

    # and the real version is back, so no other test inherits the stub
    import maxpane_dashboard as restored

    assert restored.__version__ != "0+unknown"
