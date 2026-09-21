"""The saved IDMD seat: ``config.get_seat``/``save_seat``, ``parse_seat``, and
the path from ``~/.maxpane/config.toml`` through ``__main__`` and
``MaxPaneApp`` into ``SurfManager(seat=)``.

Every test points ``config`` at a temporary file: a suite that rewrites the
developer's own config is the failure the wallet prompt's tests guard too.
"""

from __future__ import annotations

import sys

import pytest

from maxpane_dashboard import config
from maxpane_dashboard.screens.seat_input import parse_seat


@pytest.fixture()
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_FILE", path)
    return path


def test_no_file_means_no_seat(config_file):
    assert config.get_seat() is None


def test_save_then_get_round_trips_and_keeps_the_wallet(config_file):
    config.save_wallet("0x" + "ab" * 20)
    config.save_seat(1548)
    assert config.get_seat() == 1548
    assert config.get_wallet() == "0x" + "ab" * 20
    config.save_seat(0)
    assert config.get_seat() == 0, "token 0 is a real seat, not 'unset'"
    assert "[seat]\ntoken_id = 0" in config_file.read_text()


@pytest.mark.parametrize("line", [
    'token_id = "1548"', "token_id = -1", "token_id = true", "token_id = 1.5",
])
def test_a_hand_edited_seat_that_is_not_a_token_id_is_no_seat(config_file, line):
    config_file.write_text(f"[seat]\n{line}\n")
    assert config.get_seat() is None


@pytest.mark.parametrize("text", ["seat = 5\n", 'seat = "1548"\n', "seat = [1]\n"])
def test_a_seat_that_is_not_a_table_is_no_seat_not_a_crash(config_file, text):
    """``main()`` reads this on every launch: a hand-edited file in the
    wrong shape must mean "no seat saved", never an ``AttributeError``."""
    config_file.write_text(text)
    assert config.get_seat() is None
    config.save_seat(7)
    assert config.get_seat() == 7, "the prompt can repair the file it could not read"


def test_a_wallet_that_is_not_a_table_is_no_wallet_not_a_crash(config_file, monkeypatch):
    monkeypatch.delenv("MAXPANE_WALLET", raising=False)
    config_file.write_text('wallet = "0xabc"\n')
    assert config.get_wallet() == ""


def test_the_retired_env_var_is_not_a_seat(config_file, monkeypatch):
    monkeypatch.setenv("MAXPANE_IMD_SEAT", "1548")
    assert config.get_seat() is None


@pytest.mark.parametrize("text, token", [
    ("1548", 1548), ("#1548", 1548), ("  #0 ", 0), ("0012", 12),
    ("", None), ("#", None), ("12a", None), ("-5", None), ("1 548", None),
    ("١٥٤٨", None), ("##1", None), ("12345678901", None),
])
def test_parse_seat(text, token):
    assert parse_seat(text) == token


# -- start-up wiring -----------------------------------------------------------


def test_the_app_hands_the_seat_to_the_surf_manager():
    from maxpane_dashboard.app import MaxPaneApp
    assert MaxPaneApp(seat=1548)._surf_manager._seat_saved == 1548
    assert MaxPaneApp()._surf_manager._seat_saved is None


def test_main_reads_the_saved_seat_into_the_app(config_file, monkeypatch):
    import maxpane_dashboard.__main__ as entry

    config.save_seat(463)
    built: dict = {}

    class _App:
        def __init__(self, **kwargs):
            built.update(kwargs)

        def run(self):
            built["ran"] = True

    monkeypatch.setattr(entry, "MaxPaneApp", _App)
    monkeypatch.setattr(entry, "_maximize_terminal", lambda *_a, **_k: None)
    monkeypatch.setattr(entry.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(entry.os, "makedirs", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["maxpane", "--font-size", "0"])
    entry.main()
    assert built["seat"] == 463 and built["ran"] is True
