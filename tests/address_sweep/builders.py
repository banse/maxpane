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
from maxpane_dashboard.screens.curator import CURATOR_FULL_LAYOUT_COLUMNS, CuratorScreen
from maxpane_dashboard.screens.dota import DOTAScreen
from maxpane_dashboard.screens.frenpet import FrenPetScreen
from maxpane_dashboard.screens.frenpet_full import FrenPetFullScreen
from maxpane_dashboard.screens.frenpet_perf import FrenPetPerfScreen
from maxpane_dashboard.screens.frenpet_wallet import FrenPetWalletScreen
from maxpane_dashboard.screens.fwa import FWAScreen
from maxpane_dashboard.screens.ocm import OCMScreen
from maxpane_dashboard.screens.surf import (
    SURF_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_ROWS,
    SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_ROWS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_USER_FULL_LAYOUT_ROWS,
    SURF_AGENT_FULL_LAYOUT_COLUMNS,
    SURF_AGENT_FULL_LAYOUT_ROWS,
    SURF_SWARM_FULL_LAYOUT_COLUMNS,
    SURF_SWARM_FULL_LAYOUT_ROWS,
    SurfScreen,
)
from maxpane_dashboard.screens.talismans import TalismansScreen
from maxpane_dashboard.screens.ttt import TTTScreen
from maxpane_dashboard.widgets.explorer import BASE, ETHEREUM, SEPOLIA
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
#: A swarm launch artifact's contract address (LAUNCHES, ``s``; swarm v2,
#: WP7). The ``artifacts`` column is a fixed-width table column
#: (``swarm_launches.ADDR_COLS`` = 17 at ``full``/``compact``,
#: ``TIGHT_ADDR_COLS`` = 11 at ``tight``, always below a 42-cell address),
#: so this cell renders the anti-poisoning window shape, never the whole
#: address, at every terminal size. Linked per row through
#: ``for_chain_id(chain_id)`` -- the seeded launch is a Sepolia one.
_SWARM_CONTRACT = "0x5b7A2f80cCe8b8f930c60D33c8fb0FA1234abCDe"
#: The selected seat's owner on the AGENT body's SEAT RECORD panel (``a``;
#: ``docs/surf_agent_seats_spec.md`` D5). ``/seats`` serves no chain for the
#: owner, so it links the package ``EXPLORER`` -- mainnet, the case's own
#: ``explorer`` -- rather than a row's ``chain_id``. The panel's
#: ``max-width: 46`` cannot hold 42 characters plus the label, so the cell
#: renders the anti-poisoning window, never the whole address.
_SEAT_OWNER = "0x7A11e2d9C4b3f8E6a5D1c0B9e8F7a6D5c4B3a2E1"


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
    launches = payload["swarm_launch_rows"]
    artifacts = [{**launches[0]["artifacts"][0], "address": _SWARM_CONTRACT}]
    launches[0] = {**launches[0], "artifacts": artifacts, "artifact_count": 1}
    payload["swarm_seat_summary"] = {**payload["swarm_seat_summary"], "owner": _SEAT_OWNER}
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
    _SWARM_CONTRACT,                                # s: LAUNCHES artifact, shortened
    _SEAT_OWNER,                                    # a: SEAT RECORD owner, shortened
)


# -- curator -------------------------------------------------------------------


#: The custom NFT collection the filter-editor view types in: an address the
#: screen is given by the reader, not by the manager.
_CURATOR_NFT = "0x8a90CAb2b38dba80c64b7734e58Ee1dB38B8992e"
#: A second custom collection, added on **Base** through the same controls:
#: a contract address is on one chain, so the editor must link this one to
#: Basescan while the package's wallet explorer stays Etherscan (fix round
#: 1, C1). Not a predefined collection (those are refused as "already
#: available above").
_CURATOR_NFT_BASE = "0x1195Cf65f83B3A5768F3C496D3A05AD6412c64B7"


#: The savior of a judged hour (CLOSEST CALLS, under ``h``): GRACE has judged
#: no hour yet, so its board is empty and a row is seeded.
_CURATOR_SAVIOR = "0x1d0f6bb2d4b4ce7f0d0a4e5c2a4b6f3e8e5c9a71"
#: The first CLEANED row of the committed worst-case analysis slice.
_CURATOR_CLEAN = "0x2fe4093c894749e596f458764c377bf4f1337b58"


def _curator_payload() -> dict:
    """GRACE plus the wallet fields and the analysis slot (clean rows included).

    GRACE's leaderboard rows carry no join order, so every join-order filter
    (preset ``1``, first 1000 wallets) would match nothing; each row gets its
    rank as ``first_index`` and hour 0 as ``first_hour``.
    """
    payload = _curator._analysis_payload()
    payload["leaderboard_rows"] = [
        {**row, "first_index": row.get("rank", i), "first_hour": 0}
        for i, row in enumerate(payload["leaderboard_rows"], start=1)
    ]
    payload["closest_call_rows"] = [
        {"hour": 2, "volume_eth": 12.5, "margin_eth": 0.25,
         "savior": _CURATOR_SAVIOR, "savior_name": None},
    ]
    payload["closest_call_margin_eth"] = 0.25
    payload["closest_call_hour"] = 2
    return payload


def _curator_served() -> dict:
    return {
        **_curator_payload(),
        "_typed_nft_collection_address": _CURATOR_NFT,
        "_typed_nft_collection_address_base": _CURATOR_NFT_BASE,
    }


async def curator_filter_editor(app, pilot) -> None:
    """``f`` with two custom NFT collections added through the editor's own
    controls: one on Ethereum, one on Base. The name lookup is an exclusive
    worker, so the second add waits (bounded) for the first to land rather
    than cancelling it."""
    await pilot.press("f")
    await pilot.pause()
    editor = app.screen.query_one(_curator.CuratorListFilterEditor)
    for count, (chain, address) in enumerate(
        (("ethereum", _CURATOR_NFT), ("base", _CURATOR_NFT_BASE)), start=1
    ):
        editor.query_one("#filter-nft-chain", _curator.Select).value = chain
        editor.query_one("#filter-nft-address", _curator.Input).value = address
        await pilot.pause()
        await pilot.click("#filter-nft-add")
        for _ in range(20):
            await pilot.pause()
            if len(editor.values()["nft_collections"]) == count:
                break
        assert len(editor.values()["nft_collections"]) == count, "the collection never landed"


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
    _CURATOR_SAVIOR,                                # h: CLOSEST CALLS savior, shortened
    _CURATOR_CLEAN,                                 # c: CLEANED list / analysis CLEANED LIST, full or shortened
    _CURATOR_NFT,                                   # f: filter editor's selected custom collection (Ethereum)
    _CURATOR_NFT_BASE,                              # f: the second one, on Base -> Basescan (explorer_for)
)


# -- fwa -----------------------------------------------------------------------

#: A param-drift value that is an address, embedded in ``value_str``
#: (approved deviation for FWA's SIGNALS drift row). Driven through the real
#: analytics builder with an address-typed key (61), the way
#: ``tests/widgets/test_fwa_address_icons.py`` does, so the row is exactly what
#: the manager could hand the screen. ``_fmt_config_value`` lower-cases it.
_FWA_DRIFT = "0x8c8d7c46219d9205f056f28fee5950ad564d7465"


#: Unnamed rows: the manager leaves ``collection_name`` / ``purchaser_name``
#: None when no name or ENS is known, so each of these renders as a windowed
#: address rather than a label -- the shape an address budget below
#: ``MIN_SHORT_COLS`` crops the icon off.
_FWA_UNNAMED_COLLECTION = "0x" + "c0" * 20   # CHASE BOARD row 2, no collection name
_FWA_UNNAMED_PURCHASER = "0x" + "d1" * 20    # ACTIVITY row 1 purchaser, no ENS
_FWA_UNNAMED_DRAWN = "0x" + "e2" * 20        # ACTIVITY row 1 collection, no name
_FWA_UNNAMED_HOLDER = "0x" + "f3" * 20       # SETTLEMENT crown rank 1, no ENS


#: A width below FWA's pin where the final review measured an unnamed CHASE
#: BOARD row losing its icon (an address budgeted below ``MIN_SHORT_COLS``):
#: 143 and 170 both hide that defect, so the pin sweep alone cannot see it.
#: A measurement, not a pin.
_FWA_SUB_PIN_COLUMNS = 120


def _fwa_payload() -> dict:
    events = [{"key": 61, "value": int(_FWA_DRIFT, 16), "block_number": 25_600_000}]
    payload = _fwa._frozen_payload(
        param_drift_signal=_fwa._signals.param_drift_signal(events).model_dump(),
    )
    chase = copy.deepcopy(payload["chase_positions"])
    chase[1] = {**chase[1], "collection": _FWA_UNNAMED_COLLECTION, "collection_name": None}
    draws = copy.deepcopy(payload["draw_events"])
    draws[0] = {**draws[0], "purchaser": _FWA_UNNAMED_PURCHASER, "purchaser_name": None,
                "collection": _FWA_UNNAMED_DRAWN, "collection_name": None}
    crowns = copy.deepcopy(payload["crown_history"])
    crowns[0] = {**crowns[0], "holder": _FWA_UNNAMED_HOLDER, "holder_name": None}
    payload.update(chase_positions=chase, draw_events=draws, crown_history=crowns)
    return payload


def _fwa_app() -> App:
    return _FWACopyHarness(FWAScreen(_fwa._FakeManager(_fwa_payload()), poll_interval=30, name="fwa"))


FWA_SEEDED: tuple[str, ...] = (
    "0xabababababababababababababababababababab",  # default: HERO crown holder, shortened
    "0x2222222222222222222222222222222222222222",  # default: ODDS BOARD, name-backed (Art Blocks)
    "0x0000000000000000000000000000000000000002",  # default: SETTLEMENT holder, shortened
    _FWA_DRIFT,                                     # default: SIGNALS param drift, prose
    "0x0000000000000000000000000000000000000003",  # c: ACTIVITY purchaser, shortened
    _FWA_UNNAMED_COLLECTION,                        # default: CHASE BOARD, unnamed, shortened
    _FWA_UNNAMED_PURCHASER,                         # c: ACTIVITY purchaser, unnamed, shortened
    _FWA_UNNAMED_DRAWN,                             # c: ACTIVITY collection, unnamed, shortened
    _FWA_UNNAMED_HOLDER,                            # default: SETTLEMENT crown rank 1, unnamed, shortened
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
        # Mainnet by default (``widgets/surf/_fmt.EXPLORER``); the pool4 panels link
        # by ``pool4_network`` and the swarm rows by their own ``chain_id`` (the
        # fixture's launch and feedback rows are mostly Sepolia), so all three
        # are allowed. The ``a`` AGENT body renders one address: SEAT RECORD's
        # owner, seeded as ``_SEAT_OWNER`` and linked on the package
        # ``EXPLORER`` (mainnet, this case's ``explorer``). Its other panels
        # render hashes only (RECORD none, FEEDBACK through ``hash_text``).
        explorer=ETHEREUM,
        explorers=(ETHEREUM, SEPOLIA, BASE),
        rows_pick_explorer=True,
        screen_class=SurfScreen,
        build=_surf_app,
        payload=_surf_payload,
        views=((), ("l",), ("e",), ("4",), ("s",), ("a",)),
        seeded=SURF_SEEDED,
        pins=(
            (SURF_FULL_LAYOUT_COLUMNS, None),
            (SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, SURF_LAUNCHPAD_FULL_LAYOUT_ROWS),
            (SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS),
            (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_POOL4_USER_FULL_LAYOUT_ROWS),
            (SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS),
            (SURF_AGENT_FULL_LAYOUT_COLUMNS, SURF_AGENT_FULL_LAYOUT_ROWS),
        ),
    ),
    SweepCase(
        name="curator",
        explorer=ETHEREUM,  # widgets/curator/_fmt.EXPLORER -- every wallet address
        # A custom collection's contract links to its own chain
        # (widgets/curator/list_filter.NFT_CHAIN_EXPLORERS); the Base one the
        # editor view adds must link on Basescan and nowhere else.
        explorers=(ETHEREUM, BASE),
        explorer_for={_CURATOR_NFT_BASE: BASE},
        screen_class=CuratorScreen,
        build=_curator_app,
        payload=_curator_served,
        # The body opens on the RAW record list; ``c`` rotates it to CLEANED,
        # preset ``1`` applies a filter (FILTERED), ``h`` is the history
        # dashboard (``c`` swaps its panel there), ``y`` the wallet, ``a``
        # the linked-wallet analysis body (bound 2026-09-15). A view
        # coroutine still types a collection into ``f``'s editor -- the
        # callable-view mechanism stays for that one.
        views=((), ("c",), ("1",), ("h",), ("h", "c"), ("y",), ("a",),
               curator_filter_editor),
        seeded=CURATOR_SEEDED,
        pins=((CURATOR_FULL_LAYOUT_COLUMNS, None),),
    ),
    SweepCase(
        name="fwa",
        explorer=ETHEREUM,  # widgets/fwa/_chain.EXPLORER
        screen_class=FWAScreen,
        build=_fwa_app,
        payload=_fwa_payload,
        views=((), ("c",)),
        seeded=FWA_SEEDED,
        extra_sizes=((_FWA_SUB_PIN_COLUMNS, None),),
    ),
    SweepCase(
        name="base",
        explorer=BASE,  # widgets/base/_chain.EXPLORER
        screen_class=BaseTerminalScreen,
        build=_base_app,
        payload=_base_payload,
        seeded=BASE_SEEDED,
    ),
    SweepCase(
        name="frenpet",
        explorer=None,  # address-free
        screen_class=FrenPetScreen,
        build=_frenpet_app,
        payload=_frenpet_served,
        address_free=True,
    ),
    SweepCase(
        name="frenpet_full",
        explorer=BASE,  # widgets/frenpet/_chain.EXPLORER (the hidden bodies' sites)
        screen_class=FrenPetFullScreen,
        build=_frenpet_full_app,
        payload=_frenpet_served,
        views=((), ("2",), ("3",), ("4",)),
        seeded=FRENPET_FULL_SEEDED,
    ),
    SweepCase(
        name="frenpet_wallet",
        explorer=BASE,  # widgets/frenpet/_chain.EXPLORER (the hidden bodies' sites)
        screen_class=FrenPetWalletScreen,
        build=_frenpet_wallet_app,
        payload=_frenpet_served,
        seeded=FRENPET_WALLET_SEEDED,
    ),
    SweepCase(
        name="frenpet_perf",
        explorer=BASE,  # widgets/frenpet/_chain.EXPLORER (the hidden bodies' sites)
        screen_class=FrenPetPerfScreen,
        build=_frenpet_perf_app,
        payload=_frenpet_served,
        seeded=FRENPET_PERF_SEEDED,
    ),
    SweepCase(
        name="cattown",
        explorer=BASE,  # widgets/cattown/_chain.EXPLORER
        screen_class=CatTownScreen,
        build=_cattown_app,
        payload=_cattown_payload,
        seeded=CATTOWN_SEEDED,
    ),
    SweepCase(
        name="ttt",
        explorer=ETHEREUM,  # widgets/ttt/_chain.EXPLORER
        screen_class=TTTScreen,
        build=_ttt_app,
        payload=_ttt_payload,
        views=((), ("c",)),
        seeded=TTT_SEEDED,
    ),
    SweepCase(
        name="talismans",
        explorer=ETHEREUM,  # widgets/talismans/_chain.EXPLORER
        screen_class=TalismansScreen,
        build=_talismans_app,
        payload=_talismans_payload,
        views=((), ("c",)),
        seeded=TALISMANS_SEEDED,
    ),
    SweepCase(
        name="ocm",
        explorer=ETHEREUM,  # widgets/ocm/_chain.EXPLORER
        screen_class=OCMScreen,
        build=_ocm_app,
        payload=_ocm_payload,
        seeded=OCM_SEEDED,
    ),
    SweepCase(
        name="dota",
        explorer=None,  # address-free
        screen_class=DOTAScreen,
        build=_dota_app,
        payload=_dota_payload,
        address_free=True,
    ),
    SweepCase(
        name="bakery",
        # Abstract (``tests/data/test_client.py`` pins ``agent.json``'s ``chainId``
        # 2741, explorer ``abscan.org``), which ``widgets/explorer.py`` does not
        # allowlist: no explorer, so E7 asserts that no address on it links.
        explorer=None,
        screen_class=BakeryScreen,
        build=_bakery_app,
        payload=_bakery_payload,
        seeded=BAKERY_SEEDED,
    ),
)
