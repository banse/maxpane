"""Headless Textual tests for the Talismans dashboard screen.

A fake manager returns a representative full data-contract dict (no network),
the screen is pushed via ``App.run_test()``, and we assert:

* the screen mounts and composes all widgets,
* ``_do_refresh`` dispatches the dict to every widget without raising,
* ``action_toggle_view`` flips ``_active_view`` and the table ``.display`` flags.
"""

from __future__ import annotations

import time

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.screens.talismans import TalismansScreen


def _sample_data() -> dict:
    now = int(time.time())
    return {
        "live_tokens": 1490,
        "genesis_minted": 1536,
        "token_drift": -46,
        "mythic_count": 12,
        "mythic_pct": 0.8,
        "mythics_ever_forged": 15,
        "total_cores": 1536,
        "cores_invariant_intact": True,
        "operations_24h": 34,
        "operations_total": 2891,
        "top_collectors": [
            {
                "rank": i,
                "address": f"0x{i:040x}",
                "tokens": 100 - i,
                "cores": 50 - i,
                "mythics": i,
            }
            for i in range(1, 6)
        ],
        "mythic_history": [[1000 + i * 86400, i] for i in range(10)],
        "operations_history": [[1000 + i * 86400, 30 - i] for i in range(10)],
        "conservation_signal": {
            "label": "Conservation",
            "value_str": "cores conserved",
            "indicator": "●",
            "color": "green",
        },
        "cutmerge_signal": {
            "label": "Cut/Merge",
            "value_str": "net +3 cuts",
            "indicator": "▲",
            "color": "yellow",
        },
        "forge_momentum_signal": {
            "label": "Forge",
            "value_str": "2 mythics 24h",
            "indicator": "●",
            "color": "green",
        },
        "mythic_scarcity_signal": {
            "label": "Scarcity",
            "value_str": "0.8% mythic",
            "indicator": "●",
            "color": "red",
        },
        "activity_events": [
            {
                "tx_hash": "0xaaa",
                "block_number": 100,
                "timestamp": now,
                "op_type": "bond",
                "token_id_a": 12,
                "token_id_b": 34,
                "result_id": 99,
                "operator": "0xabc",
            },
        ],
        "essence_tier_matrix": {
            "rows": [
                {
                    "essence": "Lithic",
                    "raw": 500,
                    "cut": 200,
                    "fine": 100,
                    "prime": 50,
                    "bonded": 0,
                    "total": 850,
                },
            ],
            "totals": {
                "raw": 500,
                "cut": 200,
                "fine": 100,
                "prime": 50,
                "bonded": 0,
                "total": 850,
            },
        },
        "materials_ledger": [
            {
                "rank": i,
                "material": f"Material {i}",
                "essence": "Lithic",
                "tokens": 100 - i,
                "cores": 50 - i,
            }
            for i in range(1, 7)
        ],
        "current_block": 19_000_000,
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
        "active_view": "matrix",
        "bond_cleave_enabled": True,
        "cut_merge_enabled": True,
    }


class _FakeManager:
    """Stand-in for TalismansManager that never touches the network."""

    def __init__(self) -> None:
        self._error_count = 0
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        return _sample_data()

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single TalismansScreen for testing."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


@pytest.mark.asyncio
async def test_screen_mounts_and_refreshes():
    manager = _FakeManager()
    screen = TalismansScreen(manager, poll_interval=30, name="talismans")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Screen mounted with the default view.
        assert screen._active_view == "matrix"
        # Dispatch the full data contract without raising.
        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1


@pytest.mark.asyncio
async def test_toggle_view_flips_display():
    manager = _FakeManager()
    screen = TalismansScreen(manager, poll_interval=30, name="talismans")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        matrix = screen.query_one("#tal-matrix-table")
        materials = screen.query_one("#tal-materials-table")

        # Initial: matrix shown, materials hidden.
        assert screen._active_view == "matrix"
        assert matrix.display is True
        assert materials.display is False

        # Toggle to materials.
        screen.action_toggle_view()
        await pilot.pause()
        assert screen._active_view == "materials"
        assert matrix.display is False
        assert materials.display is True

        # Toggle back to matrix.
        screen.action_toggle_view()
        await pilot.pause()
        assert screen._active_view == "matrix"
        assert matrix.display is True
        assert materials.display is False
