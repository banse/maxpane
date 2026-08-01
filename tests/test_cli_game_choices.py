"""MEDI-5: ``--game`` may only offer dashboards that can actually be reached.

``--game`` used to accept ``frenpet_full``, ``frenpet_wallet`` and
``frenpet_perf``.  None of them could be displayed:

* they are commented out of ``screens/game_select.py``'s ``GAMES``, so the
  selection menu never lists them;
* they are absent from ``MaxPaneApp._GAME_CYCLE``, so tab-cycling skips
  them;
* ``GameSelectScreen.on_key`` always dismisses with a concrete visible game
  id, so ``app.py``'s ``if game_id is None: game_id = self._initial_game``
  fallback never fires.

The flag's only remaining effect for those three was a startup prefetch --
including on-chain reward calls when a wallet is configured -- whose
results nothing could render.

The parser is driven for real rather than re-declaring the choice list: the
failure this guards is a mismatch between the CLI and the menu, and a test
that compared two copies of the same list would pass in exactly that case.
No Textual app is started and no network is touched -- ``MaxPaneApp`` is
stubbed and ``logging.basicConfig`` neutered so a run never truncates the
user's ``~/.maxpane/maxpane.log``.
"""

from __future__ import annotations

import pytest

#: Choices removed by MEDI-5; re-add them when the views are re-enabled.
UNREACHABLE_GAMES = ["frenpet_full", "frenpet_wallet", "frenpet_perf"]


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, returning the app's kwargs."""
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):  # never starts a real TUI
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli, "_maximize_terminal", lambda *a, **k: None)
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


@pytest.mark.parametrize("game", UNREACHABLE_GAMES)
def test_unreachable_games_are_rejected(monkeypatch, game) -> None:
    """A flag that cannot do what its help says must not be accepted."""
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--game", game])


def test_every_game_choice_is_offered_by_the_menu(monkeypatch) -> None:
    """The CLI and the selection menu must agree on what exists.

    This is the assertion that keeps MEDI-5 closed: comment a game out of
    ``GAMES`` without touching the CLI and this fails, instead of shipping
    a flag that silently prefetches a dashboard nobody can open.
    """
    from maxpane_dashboard.screens.game_select import GAMES

    visible = {game_id for _key, game_id, _name, _desc in GAMES}

    captured = _run_cli(monkeypatch, [])
    assert captured["initial_game"] in visible

    # Every accepted choice must resolve to a menu entry.
    for game in visible:
        result = _run_cli(monkeypatch, ["--game", game])
        assert result["initial_game"] == game

    for game in UNREACHABLE_GAMES:
        assert game not in visible, (
            f"{game} is selectable again -- re-add it to the --game choices "
            "in __main__.py"
        )


def test_reachable_games_still_work(monkeypatch) -> None:
    """The removal did not take any live dashboard with it."""
    for game in ("bakery", "frenpet", "ttt", "talismans", "fwa"):
        captured = _run_cli(monkeypatch, ["--game", game])
        assert captured["initial_game"] == game
        assert captured.get("ran") is True


def test_game_help_does_not_promise_to_skip_the_menu() -> None:
    """The help text must describe what the flag does.

    It read "Which game dashboard to show first", but the selection menu
    appears for every value -- ``GameSelectScreen`` is pushed
    unconditionally after the splash and always dismisses with the id the
    user picked. The flag preloads; it does not select.
    """
    import argparse
    from unittest.mock import patch

    import maxpane_dashboard.__main__ as cli

    help_texts: dict[str, str] = {}
    real_add_argument = argparse.ArgumentParser.add_argument

    def spy(self, *args, **kwargs):
        if args and isinstance(args[0], str) and args[0].startswith("--"):
            help_texts[args[0]] = kwargs.get("help", "")
        return real_add_argument(self, *args, **kwargs)

    with patch.object(argparse.ArgumentParser, "add_argument", spy):
        with patch.object(cli, "MaxPaneApp", lambda **kw: type("A", (), {"run": lambda s: None})()):
            with patch.object(cli, "_maximize_terminal", lambda *a, **k: None):
                with patch.object(cli.logging, "basicConfig", lambda **kw: None):
                    with patch.object(cli.sys, "argv", ["maxpane"]):
                        cli.main()

    game_help = help_texts["--game"]
    assert "show first" not in game_help, (
        "the help still claims --game selects the dashboard; it only "
        f"preloads one: {game_help!r}"
    )
    assert "menu" in game_help.lower(), (
        "the help should say the selection menu still appears: "
        f"{game_help!r}"
    )
