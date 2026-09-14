"""One ``SweepCase`` per dashboard screen class (PRD §7 E2/E3).

Five dashboards already have a screen harness (surf, curator, FWA, frenpet,
talismans) and TTT has a layout harness; their fake managers and payload
builders are reused, wrapped in a ``CopyRecorder`` so a click on an icon is
recorded instead of reaching a clipboard. The rest (base, cattown, OCM, DOTA,
bakery) get a minimal fake manager here: ``fetch_and_compute``, ``close`` and
``_error_count`` are all any of those screens read.

Every ``*_SEEDED`` tuple is hand-listed after rendering the case with
``icon_targets`` at the sweep's size: each entry names the panel it renders in
and the shape it renders as. Never derive one from the payload.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path

from textual.app import App

import maxpane_dashboard
from maxpane_dashboard.data.models import ActivityEvent, BakerySummary
from maxpane_dashboard.screens.bakery import BakeryScreen
from maxpane_dashboard.screens.base_terminal import BaseTerminalScreen
from maxpane_dashboard.screens.cattown import CatTownScreen
from maxpane_dashboard.screens.curator import CuratorScreen
from maxpane_dashboard.screens.dota import DOTAScreen
from maxpane_dashboard.screens.frenpet import FrenPetScreen
from maxpane_dashboard.screens.frenpet_full import FrenPetFullScreen
from maxpane_dashboard.screens.frenpet_perf import FrenPetPerfScreen
from maxpane_dashboard.screens.frenpet_wallet import FrenPetWalletScreen
from maxpane_dashboard.screens.fwa import FWAScreen
from maxpane_dashboard.screens.ocm import OCMScreen
from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.screens.talismans import TalismansScreen
from maxpane_dashboard.screens.ttt import TTTScreen
from tests.address_sweep.case import SweepCase
from tests.screens import test_curator_screen as _curator
from tests.screens import test_frenpet_screens as _frenpet
from tests.screens import test_fwa_screen as _fwa
from tests.screens import test_surf_screen as _surf
from tests.screens import test_talismans_screen as _talismans
from tests.screens import test_ttt_address_icon_layout as _ttt
from tests.widgets.address_probe import CopyRecorder

_TCSS = Path(maxpane_dashboard.__file__).parent / "themes" / "minimal.tcss"


# -- harnesses ---------------------------------------------------------------


class _SurfCopyHarness(CopyRecorder, _surf._ThemedHarness):
    pass


class _CuratorCopyHarness(CopyRecorder, _curator._ThemedHarness):
    pass


class _FWACopyHarness(CopyRecorder, _fwa._ThemedHarness):
    pass


class _CopyHarness(CopyRecorder, App):
    """Push one screen under the real stylesheet, as the app does."""

    CSS_PATH = _TCSS

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _PayloadManager:
    """A fake manager for the screens without a harness: serves one payload."""

    def __init__(self, payload: dict, **attrs) -> None:
        self._payload = payload
        self._error_count = 0
        for name, value in attrs.items():
            setattr(self, name, value)

    async def fetch_and_compute(self) -> dict:
        return dict(self._payload)

    async def close(self) -> None:
        pass


# -- surf ----------------------------------------------------------------------

#: Seeded into the first announce post's text: an address inside prose.
_SURF_PROSE = "0x5A0b54D5dc17e0AadC383d2db43B0a0D3E029c4c"
#: Seeded into the deploy detector's detail, where surf keeps the WHOLE address
#: inside the sentence (approved deviation: it is persisted and re-quoted).
_SURF_DEPLOY = "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"
#: A launchpad coin creator that appears nowhere else on screen, so the COINS
#: table's CREATOR cell is the only place that can give it an icon.
_SURF_CREATOR = "0xC0ffee254729296a45a3885639AC7E10F9d54979"


def _surf_payload() -> dict:
    payload = copy.deepcopy(_surf._mainnet_pool4_payload())
    feed = payload["feed_items"]
    feed[0] = {**feed[0], "text": f"new router live at {_SURF_PROSE} go look"}
    # FIRED, because an ``ok`` row folds into "N quiet" and paints no detail.
    payload["sig_deploy_state"] = "fired"
    payload["sig_deploy_age_s"] = 60.0
    payload["sig_deploy_detail"] = f"new contract {_SURF_DEPLOY}"
    coins = payload["launchpad_coins"]
    coins[1] = {**coins[1], "creator": _SURF_CREATOR}
    return payload


def _surf_app() -> App:
    manager = _surf._FakeManager(_surf_payload())
    return _SurfCopyHarness(SurfScreen(manager, poll_interval=30, name="surf"))


SURF_SEEDED: tuple[str, ...] = (
    "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E",  # default: ACTIVITY counterparty, shortened
    _SURF_PROSE,                                    # default: FEED announce post, prose
    _SURF_DEPLOY,                                   # default: SIGNALS deploy detail, prose-in-detail
    "0x9D2C9B1F5C3f8b6f7D9C1a5E4b3A2F1D0c9B8A7E",  # l: LAUNCHPAD ACTIVITY wallet, shortened
    _SURF_CREATOR,                                  # l: LAUNCHPAD COINS creator, shortened
    "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",  # l: BURNKEEPERS keeper, shortened
    "0xc6c965bd164c483e87d0b550671798e9a3602840",  # p: THE SPLIT hook, shortened
    "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",  # p: HATCHES owner row, shortened
    "0xf53c0a4E4b0F77D1a3Bc4d8e3F2a1B0c9D8e3364",  # 4: STAKERS rank 1, whole/near-whole
)


# -- curator -------------------------------------------------------------------


def _curator_payload() -> dict:
    return _curator._frozen_payload()


def _curator_app() -> App:
    manager = _curator._FakeManager(payload=_curator_payload())
    screen = CuratorScreen(
        manager,
        poll_interval=30,
        name="curator",
        wallet=_curator._WALLET,
        export_dir=_curator._FIXTURES / "no-local-exports",
    )
    return _CuratorCopyHarness(screen)


CURATOR_SEEDED: tuple[str, ...] = (
    "0x75d51517b90cc5c8873c631ddc177a1bfd96b074",  # list: wallet hero card, full (the reader's wallet)
    "0x5d13fd37e8758030a6a10857c0cb699b2bff7a83",  # list: RAW record table rank 2, full
    "0xf80f4a11eeab430aa02f87d49a6db32c90d00194",  # h: ACTIVITY depositor, shortened
    "0xad468e8336182e2cec7022f3434f91227c33a723",  # h: SIGNALS whale wallet, shortened
)


# -- fwa -----------------------------------------------------------------------

#: A param-drift value that is an address, embedded in ``value_str``
#: (approved deviation for FWA's SIGNALS drift row). Driven through the real
#: analytics builder with an address-typed key (61), the way
#: ``tests/widgets/test_fwa_address_icons.py`` does, so the row is exactly what
#: the manager could hand the screen. ``_fmt_config_value`` lower-cases it.
_FWA_DRIFT = "0x8c8d7c46219d9205f056f28fee5950ad564d7465"


def _fwa_payload() -> dict:
    events = [{"key": 61, "value": int(_FWA_DRIFT, 16), "block_number": 25_600_000}]
    return _fwa._frozen_payload(
        param_drift_signal=_fwa._signals.param_drift_signal(events).model_dump(),
    )


def _fwa_app() -> App:
    return _FWACopyHarness(FWAScreen(_fwa._FakeManager(_fwa_payload()), poll_interval=30, name="fwa"))


FWA_SEEDED: tuple[str, ...] = (
    "0xabababababababababababababababababababab",  # default: HERO crown holder, shortened
    "0x2222222222222222222222222222222222222222",  # default: ODDS BOARD, name-backed (Art Blocks)
    "0x0000000000000000000000000000000000000002",  # default: SETTLEMENT holder, shortened
    _FWA_DRIFT,                                     # default: SIGNALS param drift, prose
    "0x0000000000000000000000000000000000000003",  # c: ACTIVITY purchaser, shortened
)


# -- base ----------------------------------------------------------------------

#: A named token (the symbol stands in for the address) and an unnamed one.
_BASE_NAMED = "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed"
_BASE_UNNAMED = "0x532f27101965dd16442E59d40670FaF5eBB142E4"


def _base_payload() -> dict:
    return {
        "eth_price": "$3,000",
        "gas_price": "0.01 gwei",
        "eth_change_24h": 1.5,
        "total_volume": 1_234_567.0,
        "top_gainer_name": "DEGEN",
        "top_gainer_pct": 12.0,
        "trending_tokens": [
            {"symbol": "DEGEN", "address": _BASE_NAMED, "price_usd": 0.0123,
             "price_change_24h": 12.0, "volume_24h": 1_200_000.0, "market_cap": 45_000_000.0},
            {"symbol": None, "address": _BASE_UNNAMED, "price_usd": 1.5,
             "price_change_24h": -3.0, "volume_24h": 90_000.0, "market_cap": 2_000_000.0},
        ],
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
    }


def _base_app() -> App:
    return _CopyHarness(BaseTerminalScreen(_PayloadManager(_base_payload()), poll_interval=30, name="base"))


BASE_SEEDED: tuple[str, ...] = (
    _BASE_NAMED,    # LEADERBOARD, name-backed (DEGEN)
    _BASE_UNNAMED,  # LEADERBOARD, shortened (no symbol)
)


# -- frenpet (overview, full, wallet, perf) --------------------------------------

_FP_WALLET = "0x030A000000000000000000000000000000004A51"
_FP_OTHER = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"


def _frenpet_payload() -> dict:
    data = _frenpet._sample_data()

    def owned(pet):
        owner = _FP_WALLET if pet.id == 1 else _FP_OTHER
        return pet.model_copy(update={"owner": owner})

    for key in ("top_pets", "managed_pets", "population_pets"):
        data[key] = [owned(p) for p in data[key]]
    data["top_pet"] = data["top_pets"][0]
    data["recent_attacks"] = [
        {"timestamp": int(time.time()), "attacker_id": 1, "defender_id": 2,
         "attacker_won": True, "points_delta": 120},
    ]
    return data


def _frenpet_served() -> dict:
    """The payload plus the one manager attribute the wallet screens print."""
    return {**_frenpet_payload(), "_manager_wallet_address": _FP_WALLET}


def _frenpet_manager() -> _PayloadManager:
    return _PayloadManager(_frenpet_payload(), _wallet_address=_FP_WALLET)


def _frenpet_app() -> App:
    return _CopyHarness(FrenPetScreen(_frenpet_manager(), poll_interval=30, name="frenpet"))


def _frenpet_full_app() -> App:
    return _CopyHarness(FrenPetFullScreen(_frenpet_manager(), poll_interval=30, name="frenpet_full"))


def _frenpet_wallet_app() -> App:
    return _CopyHarness(FrenPetWalletScreen(_frenpet_manager(), poll_interval=30, name="frenpet_wallet"))


def _frenpet_perf_app() -> App:
    return _CopyHarness(FrenPetPerfScreen(_frenpet_manager(), poll_interval=30, name="frenpet_perf"))


FRENPET_FULL_SEEDED: tuple[str, ...] = (
    _FP_WALLET,  # 2: WALLET header, the managed pets' owner, shortened
)
FRENPET_WALLET_SEEDED: tuple[str, ...] = (
    _FP_WALLET,  # title bar, the manager's wallet, shortened
)
FRENPET_PERF_SEEDED: tuple[str, ...] = (
    _FP_WALLET,  # title bar, the manager's wallet, shortened
)


# -- cattown -------------------------------------------------------------------

_CT_NAMED = "0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326"
_CT_UNNAMED = "0x95222290DD7278Aa3Ddd389Cc1E1d165CC4BAfe5"


def _cattown_payload() -> dict:
    now = int(time.time())
    return {
        "competition_state": {"is_active": True, "num_participants": 2},
        "top_fisher": {"address": _CT_NAMED, "display_name": "whiskers", "weight_kg": 12.5},
        "competition_entries": [
            {"rank": 1, "fisher_address": _CT_NAMED, "display_name": "whiskers", "weight_kg": 12.5},
            {"rank": 2, "fisher_address": _CT_UNNAMED, "display_name": "", "weight_kg": 9.0},
        ],
        "recent_catches": [
            {"timestamp": now, "fisher_address": _CT_UNNAMED, "display_name": "",
             "fish_name": "Carp", "weight_kg": 9.0, "rarity": "Common"},
            {"timestamp": now - 60, "fisher_address": _CT_NAMED, "display_name": "whiskers",
             "fish_name": "Pike", "weight_kg": 12.5, "rarity": "Rare"},
        ],
        "recommendation": "",
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
    }


def _cattown_app() -> App:
    return _CopyHarness(CatTownScreen(_PayloadManager(_cattown_payload()), poll_interval=30, name="cattown"))


CATTOWN_SEEDED: tuple[str, ...] = (
    _CT_NAMED,    # HERO leader, LEADERBOARD rank 1 and ACTIVITY: name-backed (whiskers)
    _CT_UNNAMED,  # LEADERBOARD rank 2 and ACTIVITY: shortened
)


# -- ttt -----------------------------------------------------------------------


def _ttt_payload() -> dict:
    return _ttt._sample_data()


def _ttt_app() -> App:
    return _CopyHarness(TTTScreen(_PayloadManager(_ttt_payload()), poll_interval=30, name="ttt"))


TTT_SEEDED: tuple[str, ...] = (
    "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",  # LEADERBOARD rank 1: no symbol, label "--"
    "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2",  # LEADERBOARD rank 2: name-backed (TOKEN2)
    "0xabababababababababababababababababababab",  # ACTIVITY burn actor, shortened
    "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2",  # default: FEES table rank 2, name-backed
)


# -- talismans -----------------------------------------------------------------


def _talismans_payload() -> dict:
    return _talismans._sample_data()


def _talismans_app() -> App:
    return _CopyHarness(
        TalismansScreen(_PayloadManager(_talismans_payload()), poll_interval=30, name="talismans"))


TALISMANS_SEEDED: tuple[str, ...] = (
    "0x0000000000000000000000000000000000000001",  # LEADERBOARD collector rank 1, shortened
)


# -- ocm (hidden) --------------------------------------------------------------

_OCM_ACTOR = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"


def _ocm_payload() -> dict:
    now = int(time.time())
    return {
        "total_supply": 9_000,
        "minted_pct": 90.0,
        "total_staked": 4_000,
        "staking_ratio": 44.4,
        "recent_events": [
            {"tx_hash": "0x" + "cd" * 32, "timestamp": now, "event_type": "mint",
             "actor_address": _OCM_ACTOR, "token_id": 42, "count": 1},
        ],
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 60,
    }


def _ocm_app() -> App:
    return _CopyHarness(OCMScreen(_PayloadManager(_ocm_payload()), poll_interval=60, name="ocm"))


OCM_SEEDED: tuple[str, ...] = (
    _OCM_ACTOR,  # ACTIVITY mint actor, shortened
)


# -- dota (hidden, address-free) -------------------------------------------------


def _dota_payload() -> dict:
    return {
        "game_number": 1,
        "tick": 420,
        "winning_faction": "human",
        "human_base_hp": 900,
        "orc_base_hp": 700,
        "base_max_hp": 1000,
        "top_player_name": "grunt-bot",
        "top_player_wins": 12,
        "top_player_win_rate": 0.6,
        "leaderboard": [
            {"rank": 1, "name": "grunt-bot", "wins": 12, "games": 20,
             "win_rate": 0.6, "player_type": "agent"},
        ],
        "heroes": [
            {"name": "Thrall", "faction": "orc", "hero_class": "warrior", "lane": "mid",
             "hp": 80, "max_hp": 100, "alive": True, "level": 7},
        ],
        "heroes_by_level": [("Thrall", 7)],
        "heroes_by_abilities": [("Thrall", 3)],
        "recommendation": "",
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
    }


def _dota_app() -> App:
    return _CopyHarness(DOTAScreen(_PayloadManager(_dota_payload()), poll_interval=30, name="dota"))


# -- bakery (hidden) -------------------------------------------------------------

_BAKERY_LAUNCHER = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"


def _bakery_payload() -> dict:
    event = ActivityEvent(
        type="simple",
        title="joined the bakery",
        description=None,
        launcher=_BAKERY_LAUNCHER,
        timestamp=str(int(time.time())),
        boost_type_name=None,
        boost_multiplier_bps=None,
        boost_duration=None,
        is_shield=None,
        is_outgoing=True,
        success=True,
        linked_bakery_id=None,
        linked_bakery_name=None,
    )
    # Its creator and leader are addresses no panel prints; the sweep's
    # "no full address without its icon" check guards that they stay unprinted.
    bakery = BakerySummary(
        id=1, name="Rug Co", creator="0x2546BcD3c84621e976D8185a91A922aE77ECEc30",
        leader="0xbDA5747bFD65F08deb54cb465eB87D40e51B197E", top_cook=None,
        member_count=3, active_cook_count=2, season_id=3, created_at="0",
        tx_count="1000000", raw_tx_count="1000000", buffs=0, debuffs=0,
        active_buffs=(), active_debuffs=(),
    )
    return {
        "season_id": 3,
        "prize_pool_eth": 1.0,
        "prize_pool_usd": 3000.0,
        "hours_remaining": 5.0,
        "season_active": True,
        "leader_name": "Rug Co",
        "leader_cookies": 1.0,
        "leader_rate": 1.0,
        "bakeries": [bakery],
        "production_rates": {"Rug Co": 1.0},
        "events": [event],
        "last_updated_seconds_ago": 0,
        "error_count": 0,
        "poll_interval": 30,
    }


def _bakery_app() -> App:
    return _CopyHarness(BakeryScreen(_PayloadManager(_bakery_payload()), poll_interval=30, name="bakery"))


BAKERY_SEEDED: tuple[str, ...] = (
    _BAKERY_LAUNCHER,  # ACTIVITY launcher, shortened
)


# -- the registry ----------------------------------------------------------------

CASES: tuple[SweepCase, ...] = (
    SweepCase(
        name="surf",
        screen_class=SurfScreen,
        build=_surf_app,
        payload=_surf_payload,
        views=((), ("l",), ("p",), ("4",)),
        seeded=SURF_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.surf",),
    ),
    SweepCase(
        name="curator",
        screen_class=CuratorScreen,
        build=_curator_app,
        payload=_curator_payload,
        # The body opens on the record list; ``c`` rotates it, ``h`` is the
        # history dashboard (``c`` swaps its panel there), ``y`` the wallet.
        # No key reaches the analysis body: nothing binds toggle_analysis.
        views=((), ("c",), ("h",), ("h", "c"), ("y",)),
        seeded=CURATOR_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.curator",),
    ),
    SweepCase(
        name="fwa",
        screen_class=FWAScreen,
        build=_fwa_app,
        payload=_fwa_payload,
        views=((), ("c",)),
        seeded=FWA_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.fwa",),
    ),
    SweepCase(
        name="base",
        screen_class=BaseTerminalScreen,
        build=_base_app,
        payload=_base_payload,
        seeded=BASE_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.base",),
    ),
    SweepCase(
        name="frenpet",
        screen_class=FrenPetScreen,
        build=_frenpet_app,
        payload=_frenpet_served,
        address_free=True,
        widget_packages=("maxpane_dashboard.widgets.frenpet",),
    ),
    SweepCase(
        name="frenpet_full",
        screen_class=FrenPetFullScreen,
        build=_frenpet_full_app,
        payload=_frenpet_served,
        views=((), ("2",), ("3",), ("4",)),
        seeded=FRENPET_FULL_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.frenpet",),
    ),
    SweepCase(
        name="frenpet_wallet",
        screen_class=FrenPetWalletScreen,
        build=_frenpet_wallet_app,
        payload=_frenpet_served,
        seeded=FRENPET_WALLET_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.frenpet",),
    ),
    SweepCase(
        name="frenpet_perf",
        screen_class=FrenPetPerfScreen,
        build=_frenpet_perf_app,
        payload=_frenpet_served,
        seeded=FRENPET_PERF_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.frenpet",),
    ),
    SweepCase(
        name="cattown",
        screen_class=CatTownScreen,
        build=_cattown_app,
        payload=_cattown_payload,
        seeded=CATTOWN_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.cattown",),
    ),
    SweepCase(
        name="ttt",
        screen_class=TTTScreen,
        build=_ttt_app,
        payload=_ttt_payload,
        views=((), ("c",)),
        seeded=TTT_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.ttt",),
    ),
    SweepCase(
        name="talismans",
        screen_class=TalismansScreen,
        build=_talismans_app,
        payload=_talismans_payload,
        views=((), ("c",)),
        seeded=TALISMANS_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.talismans",),
    ),
    SweepCase(
        name="ocm",
        screen_class=OCMScreen,
        build=_ocm_app,
        payload=_ocm_payload,
        seeded=OCM_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.ocm",),
    ),
    SweepCase(
        name="dota",
        screen_class=DOTAScreen,
        build=_dota_app,
        payload=_dota_payload,
        address_free=True,
        widget_packages=("maxpane_dashboard.widgets.dota",),
    ),
    SweepCase(
        name="bakery",
        screen_class=BakeryScreen,
        build=_bakery_app,
        payload=_bakery_payload,
        seeded=BAKERY_SEEDED,
        widget_packages=(
            "maxpane_dashboard.widgets.activity_feed",
            "maxpane_dashboard.widgets.leaderboard",
            "maxpane_dashboard.widgets.hero_metrics",
            "maxpane_dashboard.widgets.cookie_chart",
            "maxpane_dashboard.widgets.signals_panel",
            "maxpane_dashboard.widgets.ev_table",
        ),
    ),
)
