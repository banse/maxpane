"""Tests for Talismans NFT signal analytics.

Covers the pure functions in ``maxpane_dashboard.analytics.talismans_signals``:

* total_cores
* mythic_count
* mythic_scarcity_pct
* essence_tier_matrix
* materials_ledger
* top_collectors
* count_operations
* conservation_signal
* cutmerge_signal
* forge_momentum_signal
* mythic_scarcity_signal

All inputs are constructed directly from ``TalismanToken`` / ``TalismanActivityEvent``
Pydantic models -- no mocking framework needed.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.analytics.talismans_signals import (
    conservation_signal,
    count_operations,
    cutmerge_signal,
    essence_tier_matrix,
    forge_momentum_signal,
    materials_ledger,
    mythic_count,
    mythic_scarcity_pct,
    mythic_scarcity_signal,
    top_collectors,
    total_cores,
)
from maxpane_dashboard.data.talismans_models import (
    TalismanActivityEvent,
    TalismanToken,
)

VALID_COLORS = {"green", "yellow", "red", "dim"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tok(
    token_id: int = 1,
    owner: str = "0x000000000000000000000000000000000000aaaa",
    core_count: int = 2,
    material_id: int = 0,   # Aurora → Lumic
    essence: str = "Lumic",
    form: int = 0,
    seed: int = 0,
    tier: str = "Cut",
    is_genesis: bool = False,
    **overrides,
) -> TalismanToken:
    """Build a minimal valid TalismanToken with sensible defaults."""
    defaults = dict(
        token_id=token_id,
        owner=owner,
        core_count=core_count,
        material_id=material_id,
        essence=essence,
        form=form,
        seed=seed,
        tier=tier,
        is_genesis=is_genesis,
    )
    defaults.update(overrides)
    return TalismanToken(**defaults)


def _evt(
    tx_hash: str = "0xabc",
    block_number: int = 100,
    timestamp: int = 1_000_000,
    op_type: str = "cut",
    token_id_a: int | None = None,
    token_id_b: int | None = None,
    result_id: int | None = None,
    operator: str | None = None,
    essence: str | None = None,
    tier: str | None = None,
) -> TalismanActivityEvent:
    """Build a minimal valid TalismanActivityEvent with sensible defaults."""
    return TalismanActivityEvent(
        tx_hash=tx_hash,
        block_number=block_number,
        timestamp=timestamp,
        op_type=op_type,
        token_id_a=token_id_a,
        token_id_b=token_id_b,
        result_id=result_id,
        operator=operator,
        essence=essence,
        tier=tier,
    )


def _signal_fields(sig) -> dict:
    """Return all four signal fields as a dict."""
    return {f: getattr(sig, f) for f in ("label", "value_str", "indicator", "color")}


# ---------------------------------------------------------------------------
# total_cores
# ---------------------------------------------------------------------------

class TestTotalCores:
    def test_empty(self) -> None:
        assert total_cores([]) == 0

    def test_sum(self) -> None:
        tokens = [_tok(core_count=1), _tok(core_count=3), _tok(core_count=5)]
        assert total_cores(tokens) == 9

    def test_single(self) -> None:
        assert total_cores([_tok(core_count=4)]) == 4


# ---------------------------------------------------------------------------
# mythic_count
# ---------------------------------------------------------------------------

class TestMythicCount:
    def test_empty(self) -> None:
        assert mythic_count([]) == 0

    def test_none_mythic(self) -> None:
        tokens = [_tok(essence="Lithic"), _tok(essence="Lumic")]
        assert mythic_count(tokens) == 0

    def test_mixed(self) -> None:
        tokens = [
            _tok(essence="Mythic"),
            _tok(essence="Lumic"),
            _tok(essence="Mythic"),
            _tok(essence="Lithic"),
        ]
        assert mythic_count(tokens) == 2

    def test_all_mythic(self) -> None:
        tokens = [_tok(essence="Mythic") for _ in range(5)]
        assert mythic_count(tokens) == 5


# ---------------------------------------------------------------------------
# mythic_scarcity_pct
# ---------------------------------------------------------------------------

class TestMythicScarcityPct:
    def test_zero_live_returns_zero(self) -> None:
        assert mythic_scarcity_pct(0, 0) == 0.0

    def test_zero_mythic(self) -> None:
        assert mythic_scarcity_pct(0, 100) == pytest.approx(0.0)

    def test_all_mythic(self) -> None:
        assert mythic_scarcity_pct(50, 50) == pytest.approx(100.0)

    def test_half(self) -> None:
        assert mythic_scarcity_pct(25, 100) == pytest.approx(25.0)

    def test_negative_live_treated_as_zero(self) -> None:
        # live <= 0 → 0.0
        assert mythic_scarcity_pct(5, -1) == 0.0


# ---------------------------------------------------------------------------
# essence_tier_matrix
# ---------------------------------------------------------------------------

class TestEssenceTierMatrix:
    def test_empty_tokens_three_zeroed_rows(self) -> None:
        result = essence_tier_matrix([])
        rows = result["rows"]
        assert len(rows) == 3
        essences = [r["essence"] for r in rows]
        assert essences == ["Lithic", "Lumic", "Mythic"]
        for row in rows:
            assert row["raw"] == 0
            assert row["cut"] == 0
            assert row["fine"] == 0
            assert row["prime"] == 0
            assert row["bonded"] == 0
            assert row["total"] == 0

    def test_empty_tokens_zero_totals(self) -> None:
        result = essence_tier_matrix([])
        totals = result["totals"]
        for key in ("raw", "cut", "fine", "prime", "bonded", "total"):
            assert totals[key] == 0

    def test_counts_by_essence_and_tier(self) -> None:
        tokens = [
            _tok(essence="Lithic", tier="Raw"),
            _tok(essence="Lithic", tier="Cut"),
            _tok(essence="Lithic", tier="Cut"),
            _tok(essence="Lumic", tier="Fine"),
            _tok(essence="Mythic", tier="Bonded"),
        ]
        result = essence_tier_matrix(tokens)
        rows = {r["essence"]: r for r in result["rows"]}
        assert rows["Lithic"]["raw"] == 1
        assert rows["Lithic"]["cut"] == 2
        assert rows["Lithic"]["fine"] == 0
        assert rows["Lithic"]["total"] == 3
        assert rows["Lumic"]["fine"] == 1
        assert rows["Lumic"]["total"] == 1
        assert rows["Mythic"]["bonded"] == 1
        assert rows["Mythic"]["total"] == 1

    def test_unknown_tier_counts_only_in_total(self) -> None:
        # tier="--" is unknown; should appear in total but not a tier bucket
        tokens = [
            _tok(essence="Lumic", tier="--"),
            _tok(essence="Lumic", tier="Cut"),
        ]
        result = essence_tier_matrix(tokens)
        rows = {r["essence"]: r for r in result["rows"]}
        assert rows["Lumic"]["total"] == 2
        assert rows["Lumic"]["cut"] == 1
        assert rows["Lumic"]["raw"] == 0

    def test_unknown_essence_is_ignored(self) -> None:
        # defensive: a malformed essence must not raise and must not land in any row
        tokens = [_tok(essence="Weird", tier="Raw"), _tok(essence="Lithic", tier="Raw")]
        result = essence_tier_matrix(tokens)
        rows = {r["essence"]: r for r in result["rows"]}
        assert set(rows) == {"Lithic", "Lumic", "Mythic"}
        assert rows["Lithic"]["total"] == 1
        # the "Weird" token is dropped from per-essence rows
        assert sum(r["total"] for r in result["rows"]) == 1

    def test_totals_sum_across_rows(self) -> None:
        tokens = [
            _tok(essence="Lithic", tier="Raw"),
            _tok(essence="Lumic", tier="Cut"),
            _tok(essence="Mythic", tier="Bonded"),
        ]
        result = essence_tier_matrix(tokens)
        totals = result["totals"]
        assert totals["raw"] == 1
        assert totals["cut"] == 1
        assert totals["bonded"] == 1
        assert totals["total"] == 3

    def test_row_order_is_lithic_lumic_mythic(self) -> None:
        result = essence_tier_matrix([])
        assert [r["essence"] for r in result["rows"]] == ["Lithic", "Lumic", "Mythic"]


# ---------------------------------------------------------------------------
# materials_ledger
# ---------------------------------------------------------------------------

class TestMaterialsLedger:
    def test_empty_returns_empty(self) -> None:
        assert materials_ledger([]) == []

    def test_single_material(self) -> None:
        tokens = [_tok(material_id=0, core_count=2), _tok(material_id=0, core_count=3)]
        rows = materials_ledger(tokens)
        assert len(rows) == 1
        row = rows[0]
        assert row["rank"] == 1
        assert row["tokens"] == 2
        assert row["cores"] == 5
        assert row["essence"] == "Lumic"  # material 0 = Aurora = Lumic

    def test_ranked_by_tokens_desc(self) -> None:
        # material 0 (Aurora, Lumic): 3 tokens, material 1 (Foxfire, Lithic): 1 token
        tokens = [
            _tok(material_id=0), _tok(material_id=0), _tok(material_id=0),
            _tok(material_id=1, essence="Lithic"),
        ]
        rows = materials_ledger(tokens)
        assert rows[0]["rank"] == 1
        assert rows[0]["tokens"] == 3
        assert rows[1]["rank"] == 2
        assert rows[1]["tokens"] == 1

    def test_tie_break_by_cores_desc(self) -> None:
        # Both materials have 2 tokens; material 1 has more cores total
        tokens = [
            _tok(token_id=1, material_id=0, core_count=1),  # Aurora, total cores=1
            _tok(token_id=2, material_id=0, core_count=1),
            _tok(token_id=3, material_id=1, core_count=3, essence="Lithic"),  # Foxfire, total cores=6
            _tok(token_id=4, material_id=1, core_count=3, essence="Lithic"),
        ]
        rows = materials_ledger(tokens)
        assert rows[0]["material"] == "Foxfire"  # 6 cores > 2 cores
        assert rows[1]["material"] == "Aurora"

    def test_top_n_truncates(self) -> None:
        # Create 5 different materials, ask for top_n=3
        tokens = [
            _tok(token_id=i, material_id=i % 5, essence="Lumic") for i in range(15)
        ]
        rows = materials_ledger(tokens, top_n=3)
        assert len(rows) == 3

    def test_ranks_are_sequential(self) -> None:
        tokens = [
            _tok(token_id=1, material_id=0),
            _tok(token_id=2, material_id=1, essence="Lithic"),
            _tok(token_id=3, material_id=2, essence="Lumic"),
        ]
        rows = materials_ledger(tokens, top_n=32)
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))

    def test_each_row_has_required_keys(self) -> None:
        tokens = [_tok(material_id=0)]
        rows = materials_ledger(tokens)
        assert set(rows[0].keys()) == {"rank", "material", "essence", "tokens", "cores"}


# ---------------------------------------------------------------------------
# top_collectors
# ---------------------------------------------------------------------------

class TestTopCollectors:
    def test_empty_returns_empty(self) -> None:
        assert top_collectors([]) == []

    def test_single_owner(self) -> None:
        tokens = [_tok(owner="0xAAA", core_count=3), _tok(owner="0xAAA", core_count=2)]
        rows = top_collectors(tokens)
        assert len(rows) == 1
        row = rows[0]
        assert row["rank"] == 1
        assert row["address"] == "0xAAA"
        assert row["tokens"] == 2
        assert row["cores"] == 5
        assert row["mythics"] == 0

    def test_mythics_counted_correctly(self) -> None:
        tokens = [
            _tok(owner="0xBBB", essence="Mythic", core_count=5, tier="Bonded"),
            _tok(owner="0xBBB", essence="Lumic", core_count=2),
            _tok(owner="0xBBB", essence="Mythic", core_count=6, tier="Bonded"),
        ]
        rows = top_collectors(tokens)
        assert rows[0]["mythics"] == 2

    def test_ranked_by_cores_desc(self) -> None:
        # 0xAAA has fewer tokens but more cores
        tokens = [
            _tok(token_id=1, owner="0xAAA", core_count=8, tier="Bonded"),
            _tok(token_id=2, owner="0xBBB", core_count=1, tier="Raw"),
            _tok(token_id=3, owner="0xBBB", core_count=1, tier="Raw"),
        ]
        rows = top_collectors(tokens)
        assert rows[0]["address"] == "0xAAA"  # 8 cores > 2 cores
        assert rows[1]["address"] == "0xBBB"

    def test_tie_break_cores_equal_by_tokens_desc(self) -> None:
        # Same cores, different token counts
        tokens = [
            _tok(token_id=1, owner="0xAAA", core_count=2),
            _tok(token_id=2, owner="0xAAA", core_count=2),  # 4 cores, 2 tokens
            _tok(token_id=3, owner="0xBBB", core_count=4, tier="Prime"),  # 4 cores, 1 token
        ]
        rows = top_collectors(tokens)
        assert rows[0]["address"] == "0xAAA"  # same cores, more tokens

    def test_top_n_truncates(self) -> None:
        tokens = [_tok(token_id=i, owner=f"0x{i:040x}") for i in range(20)]
        rows = top_collectors(tokens, top_n=5)
        assert len(rows) == 5

    def test_ranks_are_sequential(self) -> None:
        tokens = [
            _tok(token_id=i, owner=f"0x{i:040x}", core_count=i + 1)
            for i in range(5)
        ]
        rows = top_collectors(tokens)
        assert [r["rank"] for r in rows] == list(range(1, 6))

    def test_each_row_has_required_keys(self) -> None:
        tokens = [_tok(owner="0xXXX")]
        rows = top_collectors(tokens)
        assert set(rows[0].keys()) == {"rank", "address", "tokens", "cores", "mythics"}


# ---------------------------------------------------------------------------
# count_operations
# ---------------------------------------------------------------------------

class TestCountOperations:
    def test_empty_events(self) -> None:
        assert count_operations([]) == 0

    def test_all_within_window_explicit_now(self) -> None:
        now = 1_000_000
        events = [
            _evt(timestamp=now - 100),
            _evt(timestamp=now - 200),
            _evt(timestamp=now - 300),
        ]
        assert count_operations(events, window_sec=86400, now_ts=now) == 3

    def test_some_outside_window(self) -> None:
        now = 1_000_000
        events = [
            _evt(timestamp=now - 100),       # inside
            _evt(timestamp=now - 86399),     # inside (boundary)
            _evt(timestamp=now - 86400),     # inside (exactly at cutoff)
            _evt(timestamp=now - 86401),     # outside
            _evt(timestamp=now - 200_000),   # outside
        ]
        assert count_operations(events, window_sec=86400, now_ts=now) == 3

    def test_none_now_anchors_to_max_timestamp(self) -> None:
        # Anchor = 1_000_000, window = 3600 → cutoff = 996_400
        # Only events at timestamps >= cutoff counted
        anchor = 1_000_000
        events = [
            _evt(timestamp=anchor),              # anchor itself, inside
            _evt(timestamp=anchor - 3600),       # exactly at cutoff, inside
            _evt(timestamp=anchor - 3601),       # just outside
        ]
        assert count_operations(events, window_sec=3600, now_ts=None) == 2

    def test_all_outside_window(self) -> None:
        now = 1_000_000
        events = [_evt(timestamp=now - 999_999)]
        assert count_operations(events, window_sec=60, now_ts=now) == 0


# ---------------------------------------------------------------------------
# conservation_signal
# ---------------------------------------------------------------------------

class TestConservationSignal:
    def test_intact(self) -> None:
        sig = conservation_signal(100, 100)
        fields = _signal_fields(sig)
        assert fields["label"] == "CONSERVATION"
        assert fields["value_str"] == "INTACT"
        assert fields["indicator"] == "●"
        assert fields["color"] == "green"

    def test_drift_positive(self) -> None:
        sig = conservation_signal(105, 100)
        fields = _signal_fields(sig)
        assert "DRIFT" in fields["value_str"]
        assert fields["color"] == "red"

    def test_drift_negative(self) -> None:
        sig = conservation_signal(95, 100)
        fields = _signal_fields(sig)
        assert "DRIFT" in fields["value_str"]
        assert fields["color"] == "red"

    def test_drift_shows_delta(self) -> None:
        sig = conservation_signal(110, 100)
        assert "+10" in sig.value_str

    def test_drift_negative_delta(self) -> None:
        sig = conservation_signal(90, 100)
        assert "-10" in sig.value_str

    def test_unset_baseline_is_syncing(self) -> None:
        # baseline not yet established -> neutral, not a false drift
        sig = conservation_signal(3114, 0)
        fields = _signal_fields(sig)
        assert fields["value_str"] == "SYNCING"
        assert fields["color"] == "dim"

    def test_incomplete_scan_is_syncing(self) -> None:
        # a partial enumeration must not claim drift against the baseline
        sig = conservation_signal(2000, 3114, complete=False)
        fields = _signal_fields(sig)
        assert fields["value_str"] == "SYNCING"
        assert fields["color"] == "dim"

    def test_valid_color(self) -> None:
        for total, baseline in [(100, 100), (105, 100), (95, 100)]:
            sig = conservation_signal(total, baseline)
            assert sig.color in VALID_COLORS

    def test_all_fields_present(self) -> None:
        sig = conservation_signal(100, 100)
        for field in ("label", "value_str", "indicator", "color"):
            assert getattr(sig, field) is not None


# ---------------------------------------------------------------------------
# cutmerge_signal
# ---------------------------------------------------------------------------

class TestCutmergeSignal:
    def test_live(self) -> None:
        sig = cutmerge_signal(cut_merge=True)
        assert sig.label == "CUT/MERGE"
        assert sig.value_str == "LIVE"
        assert sig.color == "green"
        assert sig.indicator == "●"

    def test_locked(self) -> None:
        sig = cutmerge_signal(cut_merge=False)
        assert sig.value_str == "LOCKED"
        assert sig.color == "yellow"
        assert sig.indicator == "●"

    def test_valid_color_live(self) -> None:
        assert cutmerge_signal(True).color in VALID_COLORS

    def test_valid_color_locked(self) -> None:
        assert cutmerge_signal(False).color in VALID_COLORS

    def test_all_fields_present(self) -> None:
        sig = cutmerge_signal(False)
        for field in ("label", "value_str", "indicator", "color"):
            assert getattr(sig, field) is not None


# ---------------------------------------------------------------------------
# forge_momentum_signal
# ---------------------------------------------------------------------------

class TestForgeMomentumSignal:
    def test_fewer_than_two_points_stable(self) -> None:
        sig = forge_momentum_signal([])
        assert sig.label == "FORGE MOMENTUM"
        assert sig.value_str == "STABLE"
        assert sig.color == "dim"
        assert sig.indicator == "●"

    def test_one_point_stable(self) -> None:
        sig = forge_momentum_signal([(0.0, 100.0)])
        assert sig.value_str == "STABLE"
        assert sig.color == "dim"

    def test_consolidating(self) -> None:
        # latest < earliest → net fusing → CONSOLIDATING ▼ green
        history = [(0.0, 100.0), (1.0, 80.0), (2.0, 70.0)]
        sig = forge_momentum_signal(history)
        assert "CONSOLIDATING" in sig.value_str
        assert "▼" in sig.value_str
        assert sig.color == "green"

    def test_splitting(self) -> None:
        # latest > earliest → SPLITTING ▲ yellow
        history = [(0.0, 50.0), (1.0, 60.0), (2.0, 75.0)]
        sig = forge_momentum_signal(history)
        assert "SPLITTING" in sig.value_str
        assert "▲" in sig.value_str
        assert sig.color == "yellow"

    def test_equal_stable(self) -> None:
        history = [(0.0, 100.0), (1.0, 100.0)]
        sig = forge_momentum_signal(history)
        assert sig.value_str == "STABLE"
        assert sig.color == "dim"

    def test_valid_color_all_cases(self) -> None:
        cases = [
            [],
            [(0.0, 100.0)],
            [(0.0, 100.0), (1.0, 80.0)],
            [(0.0, 50.0), (1.0, 75.0)],
            [(0.0, 100.0), (1.0, 100.0)],
        ]
        for history in cases:
            sig = forge_momentum_signal(history)
            assert sig.color in VALID_COLORS

    def test_all_fields_present(self) -> None:
        sig = forge_momentum_signal([])
        for field in ("label", "value_str", "indicator", "color"):
            assert getattr(sig, field) is not None


# ---------------------------------------------------------------------------
# mythic_scarcity_signal
# ---------------------------------------------------------------------------

class TestMythicScarcitySignal:
    def test_label(self) -> None:
        sig = mythic_scarcity_signal(10, 100)
        assert sig.label == "MYTHIC SCARCITY"

    def test_value_str_contains_mythic_count(self) -> None:
        sig = mythic_scarcity_signal(10, 100)
        assert "10" in sig.value_str

    def test_value_str_contains_pct(self) -> None:
        sig = mythic_scarcity_signal(10, 100)
        assert "10.0%" in sig.value_str

    def test_color_is_dim(self) -> None:
        sig = mythic_scarcity_signal(10, 100)
        assert sig.color == "dim"

    def test_indicator_is_dot(self) -> None:
        sig = mythic_scarcity_signal(10, 100)
        assert sig.indicator == "●"

    def test_zero_live(self) -> None:
        sig = mythic_scarcity_signal(0, 0)
        assert "0.0%" in sig.value_str
        assert sig.color == "dim"

    def test_valid_color(self) -> None:
        assert mythic_scarcity_signal(5, 200).color in VALID_COLORS

    def test_all_fields_present(self) -> None:
        sig = mythic_scarcity_signal(5, 200)
        for field in ("label", "value_str", "indicator", "color"):
            assert getattr(sig, field) is not None
