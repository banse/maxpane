"""Regression suite for HIGH-1: EV rankings must come from the LIVE catalog.

The bug this file exists to prevent: ``DataManager.fetch_and_compute`` called
``rank_boosts``/``rank_attacks`` with no catalog argument, so every EV shown by
the ``EVTable`` widget was computed from the hardcoded ``BOOST_CATALOG`` even
though ``snapshot.agent_config.live_state.active_boost_catalog`` had already
been fetched and parsed.  Measured against the live game on 2026-07-04 the
hardcoded numbers were off by 10x on duration and 23x on cost, recommended two
boosts that no longer exist, and omitted one that does.

Every assertion below is made against what the manager *returns*, and each
positive assertion ("the live number is used") is paired with a negative one
("the hardcoded number is not"), because a ranking that happens to agree with
the stale table by coincidence is exactly the failure mode that shipped.

Zero network: the client is replaced with a stub before ``DataManager`` is
constructed, and the on-disk history cache is redirected to ``tmp_path``.
"""

from __future__ import annotations

import time

import pytest

from maxpane_dashboard.analytics import ev as ev_module
from maxpane_dashboard.analytics.ev import (
    CATALOG_SOURCE_FALLBACK,
    CATALOG_SOURCE_LIVE,
)
from maxpane_dashboard.data import manager as manager_module
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.models import (
    AgentConfig,
    BakerySummary,
    BoostCatalogItem,
    Contracts,
    GameplayCaps,
    LiveState,
    Network,
    ReferralWeights,
    Season,
)
from maxpane_dashboard.data.snapshot import GameSnapshot

# ---------------------------------------------------------------------------
# Live catalog fixture -- verbatim from https://www.rugpullbakery.com/agent.json
# (fetched 2026-07-27; season 10, isSeasonActive=false).  Shape and values are
# real, including the three non-purchasable ``randomEvent`` entries that the
# hardcoded table has never heard of.
# ---------------------------------------------------------------------------

LIVE_CATALOG_JSON: list[dict] = [
    {
        "id": "1", "name": "Ad Campaign", "type": "boost", "playerPurchasable": True,
        "successChanceBps": 8500, "cost": "2800", "actualCookieCost": "28000000",
        "multiplierBps": 12500, "durationSeconds": "1500", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "3", "name": "Secret Recipe", "type": "boost", "playerPurchasable": True,
        "successChanceBps": 5500, "cost": "7000", "actualCookieCost": "70000000",
        "multiplierBps": 15000, "durationSeconds": "1800", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "4", "name": "Chef's Help", "type": "boost", "playerPurchasable": True,
        "successChanceBps": 3200, "cost": "13500", "actualCookieCost": "135000000",
        "multiplierBps": 20000, "durationSeconds": "1200", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "5", "name": "Recipe Sabotage", "type": "attack", "playerPurchasable": True,
        "successChanceBps": 6500, "cost": "5000", "actualCookieCost": "50000000",
        "multiplierBps": 2000, "durationSeconds": "1200", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "7", "name": "Kitchen Fire", "type": "attack", "playerPurchasable": True,
        "successChanceBps": 2200, "cost": "10500", "actualCookieCost": "105000000",
        "multiplierBps": 6000, "durationSeconds": "720", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "8", "name": "Supplier Strike", "type": "attack", "playerPurchasable": True,
        "successChanceBps": 4000, "cost": "8500", "actualCookieCost": "85000000",
        "multiplierBps": 3500, "durationSeconds": "1500", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": False, "active": True,
    },
    {
        "id": "9", "name": "Cleanup Crew", "type": "boost", "playerPurchasable": True,
        "successChanceBps": 10000, "cost": "6000", "actualCookieCost": "60000000",
        "multiplierBps": 0, "durationSeconds": "0", "isShield": False,
        "isRandomEvent": False, "isCountermeasure": True, "active": True,
    },
    {
        "id": "10", "name": "Rush Order", "type": "randomEvent", "playerPurchasable": False,
        "successChanceBps": 10000, "cost": "0", "actualCookieCost": "0",
        "multiplierBps": 11000, "durationSeconds": "3600", "isShield": False,
        "isRandomEvent": True, "isCountermeasure": False, "active": True,
    },
    {
        "id": "11", "name": "Golden Batch", "type": "randomEvent", "playerPurchasable": False,
        "successChanceBps": 10000, "cost": "0", "actualCookieCost": "0",
        "multiplierBps": 12000, "durationSeconds": "2700", "isShield": False,
        "isRandomEvent": True, "isCountermeasure": False, "active": True,
    },
    {
        "id": "12", "name": "Oven Frenzy", "type": "randomEvent", "playerPurchasable": False,
        "successChanceBps": 10000, "cost": "0", "actualCookieCost": "0",
        "multiplierBps": 13500, "durationSeconds": "1800", "isShield": False,
        "isRandomEvent": True, "isCountermeasure": False, "active": True,
    },
]

# Names that exist ONLY in the stale hardcoded table -- their appearance in a
# ranking built from live data is proof the live catalog was ignored.
STALE_ONLY_NAMES = {"Motivational Speech", "Fake Partnership"}

_COOKIE_SCALE = 10_000
_RATE = 1000.0  # cookies/hour the fake bakery is driven at


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------


def _season() -> Season:
    return Season(
        id=10,
        start_time="1774535903",
        end_time=str(int(time.time()) + 86_400),
        claim_deadline=None,
        protocol_fee_bps=0,
        seed_amount="1000000",
        results_root=None,
        finalized=False,
        ended=False,
        is_active=True,
        prize_pool="2000000000000000000",
    )


def _bakery(name: str, display_cookies: float, bakery_id: int = 1) -> BakerySummary:
    return BakerySummary(
        id=bakery_id,
        name=name,
        creator="0xaaa",
        leader="0xaaa",
        top_cook=None,
        member_count=10,
        active_cook_count=2,
        season_id=10,
        created_at="1774542117",
        tx_count=str(int(display_cookies * _COOKIE_SCALE)),
        raw_tx_count=str(int(display_cookies * _COOKIE_SCALE)),
        buffs=0,
        debuffs=0,
        active_buffs=(),
        active_debuffs=(),
    )


def _agent_config(catalog: tuple[BoostCatalogItem, ...]) -> AgentConfig:
    return AgentConfig(
        name="Bakery",
        version="1.0",
        generated_at="2026-07-27T21:53:09.621Z",
        network=Network(
            name="Abstract",
            chain_id=2741,
            rpc_http="https://api.mainnet.abs.xyz",
            explorer="https://abscan.org",
            currency="ETH",
            wallet_model="Abstract Global Wallet",
        ),
        contracts=Contracts(
            season_manager="0x1",
            prize_pool="0x2",
            player_registry="0x3",
            clan_registry="0x4",
            boost_manager="0x5",
            bakery="0x6",
        ),
        live_state=LiveState(
            current_season_id=10,
            is_season_active=True,
            buy_in_wei="2000000000000000",
            buy_in_eth="0.002",
            vrf_fee_wei="22006155000000",
            vrf_fee_eth="0.000022006155",
            minimum_required_wei_excluding_gas="2022006155000000",
            minimum_required_eth_excluding_gas="0.002022006155",
            referral_weights=ReferralWeights(
                referred_weight_bps=10500,
                not_referred_weight_bps=10000,
                referral_bonus_bps=500,
            ),
            gameplay_caps=GameplayCaps(
                cookie_scale=_COOKIE_SCALE,
                max_active_boosts=5,
                max_active_debuffs=5,
                leave_penalty_bps=10000,
            ),
            active_boost_catalog=catalog,
        ),
        live_data_status="fresh",
    )


def _snapshot(
    catalog: tuple[BoostCatalogItem, ...],
    *,
    leader_cookies: float,
    fetched_at: float,
) -> GameSnapshot:
    return GameSnapshot(
        season=_season(),
        bakeries=[
            _bakery("Alpha Bakery", leader_cookies, bakery_id=1),
            _bakery("Beta Bakery", leader_cookies / 2, bakery_id=2),
        ],
        activity=[],
        agent_config=_agent_config(catalog),
        eth_price_usd=2500.0,
        fetched_at=fetched_at,
    )


def _live_items() -> tuple[BoostCatalogItem, ...]:
    return tuple(BoostCatalogItem.from_api(entry) for entry in LIVE_CATALOG_JSON)


class _StubClient:
    """Stands in for ``GameDataClient``; serves canned snapshots, no network."""

    def __init__(self, snapshots: list[GameSnapshot]) -> None:
        self._snapshots = snapshots
        self.calls = 0

    async def fetch_all(self) -> GameSnapshot:
        snapshot = self._snapshots[min(self.calls, len(self._snapshots) - 1)]
        self.calls += 1
        return snapshot

    async def close(self) -> None:
        pass


@pytest.fixture
def make_manager(monkeypatch, tmp_path):
    """Build a ``DataManager`` wired to canned snapshots and a tmp cache file."""

    def _factory(snapshots: list[GameSnapshot]) -> DataManager:
        stub = _StubClient(snapshots)
        monkeypatch.setattr(manager_module, "GameDataClient", lambda: stub)
        monkeypatch.setattr(manager_module, "_CACHE_FILE", tmp_path / "history.json")
        return DataManager(poll_interval=30)

    return _factory


async def _poll_twice(manager: DataManager) -> dict:
    """Run two fetches an hour apart so the production rate is exactly 1000/hr."""
    await manager.fetch_and_compute()
    return await manager.fetch_and_compute()


def _snapshot_pair(catalog: tuple[BoostCatalogItem, ...]) -> list[GameSnapshot]:
    t0 = time.time() - 3600.0
    return [
        _snapshot(catalog, leader_cookies=10_000.0, fetched_at=t0),
        _snapshot(catalog, leader_cookies=11_000.0, fetched_at=t0 + 3600.0),
    ]


# ---------------------------------------------------------------------------
# The regression: rankings must reflect live values, not hardcoded ones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestManagerUsesLiveCatalog:
    async def test_production_rate_is_the_expected_1000_per_hour(
        self, make_manager
    ) -> None:
        """Guard the fixture itself -- every EV assertion below assumes 1000/hr."""
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        assert data["leader_rate"] == pytest.approx(1000.0, rel=1e-6)

    async def test_boost_ev_matches_live_parameters_not_hardcoded(
        self, make_manager
    ) -> None:
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        boosts = dict(data["boost_rankings"])

        # Live: 0.85 * 1000 * (1.25 - 1) * (1500/3600) - 2800 = -2711.4583...
        assert boosts["Ad Campaign"] == pytest.approx(
            0.85 * 1000.0 * 0.25 * (1500 / 3600) - 2800, abs=0.01
        )
        # Hardcoded would have been +480.0 -- 3200 cookies of difference.
        assert boosts["Ad Campaign"] != pytest.approx(480.0, abs=0.01)

        # Live: 0.32 * 1000 * (2.0 - 1) * (1200/3600) - 13500 = -13393.33...
        assert boosts["Chef's Help"] == pytest.approx(
            0.32 * 1000.0 * 1.0 * (1200 / 3600) - 13500, abs=0.01
        )
        assert boosts["Chef's Help"] != pytest.approx(3550.0, abs=0.01)

    async def test_attack_ratio_matches_live_parameters_not_hardcoded(
        self, make_manager
    ) -> None:
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        attacks = dict(data["attack_rankings"])

        # Live: 0.65 * 1000 * 0.20 * (1200/3600) / 5000 = 0.008666...
        assert attacks["Recipe Sabotage"] == pytest.approx(
            0.65 * 1000.0 * 0.20 * (1200 / 3600) / 5000, abs=1e-6
        )
        # Hardcoded would have been 5.0 -- three orders of magnitude out.
        assert attacks["Recipe Sabotage"] != pytest.approx(5.0, abs=0.01)

    async def test_retired_items_are_absent_and_new_item_present(
        self, make_manager
    ) -> None:
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        names = {n for n, _ in data["boost_rankings"]} | {
            n for n, _ in data["attack_rankings"]
        }

        assert not (names & STALE_ONLY_NAMES), (
            "ranking contains boosts that no longer exist in the live game -- "
            "the hardcoded catalog is being used"
        )
        assert "Cleanup Crew" in names, "live-only boost dropped from the ranking"

    async def test_ranking_order_follows_live_numbers(self, make_manager) -> None:
        """Under live parameters the stale table's top pick is now the *worst*."""
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        boost_order = [n for n, _ in data["boost_rankings"]]

        assert boost_order[0] == "Ad Campaign"
        assert boost_order[-1] == "Chef's Help"  # the stale table's #1 pick

    async def test_random_events_are_not_recommended(self, make_manager) -> None:
        """``randomEvent`` items are free (cost 0) -- ranking them would put an
        infinite gap-closure ratio at the top of a list of things you cannot buy."""
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        names = {n for n, _ in data["boost_rankings"]} | {
            n for n, _ in data["attack_rankings"]
        }
        assert names.isdisjoint({"Rush Order", "Golden Batch", "Oven Frenzy"})

    async def test_catalog_source_is_reported_as_live(self, make_manager) -> None:
        data = await _poll_twice(make_manager(_snapshot_pair(_live_items())))
        assert data["ev_catalog_source"] == CATALOG_SOURCE_LIVE


# ---------------------------------------------------------------------------
# Fallback: allowed to be stale, never allowed to be silent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestManagerFallback:
    async def test_empty_live_catalog_falls_back_and_says_so(
        self, make_manager
    ) -> None:
        data = await _poll_twice(make_manager(_snapshot_pair(())))

        assert data["ev_catalog_source"] == CATALOG_SOURCE_FALLBACK
        # The stale numbers are still shown (better than a blank panel) ...
        assert dict(data["boost_rankings"])["Ad Campaign"] == pytest.approx(
            480.0, abs=0.01
        )
        # ... but the source is flagged so the UI can label them.
        assert data["ev_catalog_source"] != CATALOG_SOURCE_LIVE

    async def test_catalog_of_only_unrankable_items_falls_back(
        self, make_manager
    ) -> None:
        """A catalog of nothing but random events is not a usable ranking."""
        random_only = tuple(
            BoostCatalogItem.from_api(entry)
            for entry in LIVE_CATALOG_JSON
            if entry["type"] == "randomEvent"
        )
        data = await _poll_twice(make_manager(_snapshot_pair(random_only)))
        assert data["ev_catalog_source"] == CATALOG_SOURCE_FALLBACK

    async def test_fallback_and_live_disagree_on_every_shared_boost(
        self, make_manager
    ) -> None:
        """Belt and braces: if these ever coincide, the tests above go blind."""
        live = dict(
            (await _poll_twice(make_manager(_snapshot_pair(_live_items()))))[
                "boost_rankings"
            ]
        )
        stale = dict(
            (await _poll_twice(make_manager(_snapshot_pair(()))))["boost_rankings"]
        )
        shared = set(live) & set(stale)
        assert shared, "fixtures no longer share any boost names"
        for name in shared:
            assert live[name] != pytest.approx(stale[name], abs=0.01), name


# ---------------------------------------------------------------------------
# Unknown entries must not crash the ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnknownEntriesAreSurvivable:
    async def test_unknown_type_and_id_do_not_crash_or_vanish_silently(
        self, make_manager
    ) -> None:
        exotic = [
            *LIVE_CATALOG_JSON,
            {  # a type nobody has ever seen
                "id": "99", "name": "Quantum Oven", "type": "hyperBoost",
                "playerPurchasable": True, "successChanceBps": 5000, "cost": "1",
                "actualCookieCost": "10000", "multiplierBps": 30000,
                "durationSeconds": "600", "isShield": False, "isRandomEvent": False,
                "isCountermeasure": False, "active": True,
            },
            {  # a known type with an id the code has never heard of
                "id": "77", "name": "Night Shift", "type": "boost",
                "playerPurchasable": True, "successChanceBps": 4000, "cost": "900",
                "actualCookieCost": "9000000", "multiplierBps": 13000,
                "durationSeconds": "3600", "isShield": False, "isRandomEvent": False,
                "isCountermeasure": False, "active": True,
            },
        ]
        catalog = tuple(BoostCatalogItem.from_api(e) for e in exotic)
        data = await _poll_twice(make_manager(_snapshot_pair(catalog)))

        boosts = dict(data["boost_rankings"])
        # The unheard-of *id* is ranked on its own numbers, not looked up in a table.
        assert boosts["Night Shift"] == pytest.approx(
            0.40 * 1000.0 * 0.30 * 1.0 - 900, abs=0.01
        )
        # The unheard-of *type* is excluded rather than guessed at.
        assert "Quantum Oven" not in boosts
        assert data["ev_catalog_source"] == CATALOG_SOURCE_LIVE

    async def test_inactive_entry_is_excluded(self, make_manager) -> None:
        retired = []
        for entry in LIVE_CATALOG_JSON:
            entry = dict(entry)
            if entry["name"] == "Ad Campaign":
                entry["active"] = False
            retired.append(entry)
        catalog = tuple(BoostCatalogItem.from_api(e) for e in retired)
        data = await _poll_twice(make_manager(_snapshot_pair(catalog)))

        assert "Ad Campaign" not in dict(data["boost_rankings"])
        assert "Secret Recipe" in dict(data["boost_rankings"])


class TestSkippedEntriesAreRecorded:
    """``EVCatalog.skipped`` is the audit trail behind the exclusions above."""

    def test_every_excluded_item_is_named_with_a_reason(self) -> None:
        catalog = ev_module.build_live_catalog(_live_items())
        skipped = dict(catalog.skipped)

        assert set(skipped) == {"Rush Order", "Golden Batch", "Oven Frenzy"}
        for reason in skipped.values():
            assert reason  # non-empty explanation, not a bare drop

    def test_malformed_numbers_are_skipped_not_raised(self) -> None:
        class _Broken:
            id = "42"
            name = "Broken Boost"
            type = "boost"
            active = True
            player_purchasable = True
            success_chance_bps = 5000
            cost = "not-a-number"
            multiplier_bps = 12000
            duration_seconds = "600"

        catalog = ev_module.build_live_catalog([_Broken()])
        assert catalog.entries == ()
        assert dict(catalog.skipped)["Broken Boost"].startswith("unparsable")

    def test_resolve_catalog_of_none_is_the_fallback(self) -> None:
        assert ev_module.resolve_catalog(None).source == CATALOG_SOURCE_FALLBACK
        assert ev_module.resolve_catalog([]).source == CATALOG_SOURCE_FALLBACK
