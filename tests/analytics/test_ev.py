"""Tests for boost/attack expected value calculations."""

import pytest

from maxpane_dashboard.analytics.ev import (
    BOOST_CATALOG,
    CATALOG_SOURCE_FALLBACK,
    CATALOG_SOURCE_LIVE,
    FALLBACK_CATALOG,
    CatalogEntry,
    EVCatalog,
    build_live_catalog,
    calculate_attack_ev,
    calculate_boost_ev,
    rank_attacks,
    rank_boosts,
)


def _entry(**overrides) -> CatalogEntry:
    defaults = dict(
        id="1",
        name="Test Boost",
        type="boost",
        success_rate=0.5,
        cookie_cost=100.0,
        multiplier_bps=12000,
        duration_seconds=3600,
    )
    defaults.update(overrides)
    return CatalogEntry(**defaults)  # type: ignore[arg-type]


class TestBoostCatalog:
    """Tests for the catalog data structure."""

    def test_catalog_has_eight_entries(self) -> None:
        assert len(BOOST_CATALOG) == 8

    def test_four_boosts_four_attacks(self) -> None:
        boosts = [e for e in BOOST_CATALOG if e[2] == "boost"]
        attacks = [e for e in BOOST_CATALOG if e[2] == "attack"]
        assert len(boosts) == 4
        assert len(attacks) == 4

    def test_ids_are_sequential(self) -> None:
        ids = [e[0] for e in BOOST_CATALOG]
        assert ids == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_success_rates_between_zero_and_one(self) -> None:
        for entry in BOOST_CATALOG:
            assert 0.0 < entry[3] <= 1.0, f"{entry[1]} has invalid success rate"

    def test_catalog_is_importable(self) -> None:
        """BOOST_CATALOG should be importable for use by EV table widget."""
        from maxpane_dashboard.analytics.ev import BOOST_CATALOG as imported

        assert imported is BOOST_CATALOG


class TestCalculateBoostEv:
    """Tests for calculate_boost_ev."""

    def test_ad_campaign_ev(self) -> None:
        # EV = 0.60 * 1000 * (1.25 - 1) * 4 - 120 = 0.60 * 1000 * 0.25 * 4 - 120 = 600 - 120 = 480
        ev = calculate_boost_ev(1, bakery_production_rate=1000.0)
        assert pytest.approx(ev, abs=0.01) == 480.0

    def test_motivational_speech_ev(self) -> None:
        # EV = 0.40 * 1000 * 0.25 * 4 - 80 = 400 - 80 = 320
        ev = calculate_boost_ev(2, bakery_production_rate=1000.0)
        assert pytest.approx(ev, abs=0.01) == 320.0

    def test_secret_recipe_ev(self) -> None:
        # EV = 0.35 * 1000 * 0.5 * 8 - 250 = 1400 - 250 = 1150
        ev = calculate_boost_ev(3, bakery_production_rate=1000.0)
        assert pytest.approx(ev, abs=0.01) == 1150.0

    def test_chefs_help_ev(self) -> None:
        # EV = 0.50 * 1000 * 1.0 * 8 - 450 = 4000 - 450 = 3550
        ev = calculate_boost_ev(4, bakery_production_rate=1000.0)
        assert pytest.approx(ev, abs=0.01) == 3550.0

    def test_zero_production_rate_yields_negative_ev(self) -> None:
        # EV = 0 - cookie_cost
        ev = calculate_boost_ev(1, bakery_production_rate=0.0)
        assert ev == -120.0

    def test_low_production_rate_can_yield_negative_ev(self) -> None:
        # EV = 0.60 * 10 * 0.25 * 4 - 120 = 6 - 120 = -114
        ev = calculate_boost_ev(1, bakery_production_rate=10.0)
        assert pytest.approx(ev, abs=0.01) == -114.0

    def test_raises_on_attack_id(self) -> None:
        with pytest.raises(ValueError, match="attack, not a boost"):
            calculate_boost_ev(5, bakery_production_rate=1000.0)

    def test_raises_on_unknown_id(self) -> None:
        with pytest.raises(KeyError):
            calculate_boost_ev(99, bakery_production_rate=1000.0)


class TestCalculateAttackEv:
    """Tests for calculate_attack_ev."""

    def test_recipe_sabotage(self) -> None:
        # gap_closure = 0.60 * 1000 * 0.25 * 4 = 600
        # ratio = 600 / 120 = 5.0
        ratio = calculate_attack_ev(5, target_production_rate=1000.0)
        assert pytest.approx(ratio, abs=0.01) == 5.0

    def test_fake_partnership(self) -> None:
        # gap_closure = 0.35 * 1000 * 0.25 * 4 = 350
        # ratio = 350 / 60 = 5.833...
        ratio = calculate_attack_ev(6, target_production_rate=1000.0)
        assert pytest.approx(ratio, abs=0.01) == 350.0 / 60.0

    def test_kitchen_fire(self) -> None:
        # gap_closure = 0.20 * 1000 * 1.0 * 2 = 400
        # ratio = 400 / 320 = 1.25
        ratio = calculate_attack_ev(7, target_production_rate=1000.0)
        assert pytest.approx(ratio, abs=0.01) == 1.25

    def test_supplier_strike(self) -> None:
        # gap_closure = 0.30 * 1000 * 0.5 * 4 = 600
        # ratio = 600 / 220 = 2.727...
        ratio = calculate_attack_ev(8, target_production_rate=1000.0)
        assert pytest.approx(ratio, abs=0.01) == 600.0 / 220.0

    def test_zero_target_rate(self) -> None:
        ratio = calculate_attack_ev(5, target_production_rate=0.0)
        assert ratio == 0.0

    def test_raises_on_boost_id(self) -> None:
        with pytest.raises(ValueError, match="boost, not an attack"):
            calculate_attack_ev(1, target_production_rate=1000.0)


class TestRankBoosts:
    """Tests for rank_boosts."""

    def test_returns_four_boosts(self) -> None:
        ranked = rank_boosts(bakery_production_rate=1000.0)
        assert len(ranked) == 4

    def test_sorted_by_ev_descending(self) -> None:
        ranked = rank_boosts(bakery_production_rate=1000.0)
        evs = [ev for _, ev in ranked]
        assert evs == sorted(evs, reverse=True)

    def test_best_boost_at_high_rate(self) -> None:
        ranked = rank_boosts(bakery_production_rate=1000.0)
        # Chef's Help has highest EV at 1000/hr: 3550
        assert ranked[0][0] == "Chef's Help"

    def test_returns_names_and_evs(self) -> None:
        ranked = rank_boosts(bakery_production_rate=1000.0)
        for name, ev in ranked:
            assert isinstance(name, str)
            assert isinstance(ev, float)

    def test_zero_production_all_negative(self) -> None:
        ranked = rank_boosts(bakery_production_rate=0.0)
        for _, ev in ranked:
            assert ev < 0


class TestRankAttacks:
    """Tests for rank_attacks."""

    def test_returns_four_attacks(self) -> None:
        ranked = rank_attacks(target_production_rate=1000.0)
        assert len(ranked) == 4

    def test_sorted_by_ratio_descending(self) -> None:
        ranked = rank_attacks(target_production_rate=1000.0)
        ratios = [r for _, r in ranked]
        assert ratios == sorted(ratios, reverse=True)

    def test_best_attack_at_standard_rate(self) -> None:
        ranked = rank_attacks(target_production_rate=1000.0)
        # Fake Partnership: 350/60 = 5.83 -- best ratio
        assert ranked[0][0] == "Fake Partnership"

    def test_zero_target_rate_all_zero(self) -> None:
        ranked = rank_attacks(target_production_rate=0.0)
        for _, ratio in ranked:
            assert ratio == 0.0


class TestCatalogPrimitives:
    """The catalog type is what makes provenance visible -- test it directly."""

    def test_hardcoded_table_is_tagged_as_fallback(self) -> None:
        assert FALLBACK_CATALOG.source == CATALOG_SOURCE_FALLBACK
        assert FALLBACK_CATALOG.is_live is False

    def test_default_argument_is_the_fallback_catalog(self) -> None:
        """Ranking without an explicit catalog must never claim to be live."""
        assert rank_boosts(1000.0) == rank_boosts(1000.0, catalog=FALLBACK_CATALOG)

    def test_lookup_accepts_int_and_str_ids(self) -> None:
        assert FALLBACK_CATALOG.get(1).name == FALLBACK_CATALOG.get("1").name

    def test_lookup_of_unknown_id_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="Unknown boost/attack ID"):
            FALLBACK_CATALOG.get("nope")

    def test_zero_multiplier_means_no_production_effect_not_minus_100pct(self) -> None:
        """Live 'Cleanup Crew' has multiplierBps=0: a countermeasure, not a
        production halving. Its EV is exactly its cost, never a huge negative."""
        catalog = EVCatalog(
            entries=(_entry(id="9", name="Cleanup Crew", multiplier_bps=0,
                            duration_seconds=7200, cookie_cost=6000.0),),
            source=CATALOG_SOURCE_LIVE,
        )
        assert calculate_boost_ev("9", 1000.0, catalog) == pytest.approx(-6000.0)

    def test_live_catalog_is_tagged_live(self) -> None:
        class _Item:
            id = "1"
            name = "Ad Campaign"
            type = "boost"
            active = True
            player_purchasable = True
            success_chance_bps = 8500
            cost = "2800"
            multiplier_bps = 12500
            duration_seconds = "1500"

        catalog = build_live_catalog([_Item()])
        assert catalog.source == CATALOG_SOURCE_LIVE
        assert catalog.is_live is True
        assert catalog.get("1").cookie_cost == 2800.0
        # and it disagrees with the hardcoded entry of the same id
        assert catalog.get("1").cookie_cost != FALLBACK_CATALOG.get("1").cookie_cost

    def test_build_live_catalog_of_nothing_is_empty_not_fallback(self) -> None:
        """``build_live_catalog`` never substitutes stale data on its own --
        that decision belongs to ``resolve_catalog``."""
        catalog = build_live_catalog([])
        assert catalog.entries == ()
        assert catalog.source == CATALOG_SOURCE_LIVE
