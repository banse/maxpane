"""Tests for the Talismans dashboard manager (WP3b)."""

from __future__ import annotations

import threading

import pytest

from maxpane_dashboard.analytics.talismans_signals import total_cores
from maxpane_dashboard.data import talismans_cache as tc_mod
from maxpane_dashboard.data import talismans_manager as tm_mod
from maxpane_dashboard.data.talismans_cache import TalismansCache
from maxpane_dashboard.data.talismans_manager import TalismansManager


class _FakeClient:
    """Canned-data async client mirroring TalismansClient's surface."""

    def __init__(self):
        self.closed = False

    async def fetch_block_number(self):
        return 1_000_000

    #: post-genesis allocator value; 1538 means exactly one transform id (1537)
    next_transform_id = 1538

    async def fetch_collection_flags(self):
        return {
            "total_supply": 3,
            "genesis_minted": 1536,
            "bond_cleave_enabled": True,
            "cut_merge_enabled": False,
            "next_transform_id": self.next_transform_id,
        }

    async def fetch_operation_logs(self, from_block, to_block):
        ops = [
            {
                "op_type": "bond",
                "token_id_a": 1,
                "token_id_b": 2,
                "result_id": 1537,
                "operator": "0x" + "c" * 40,
                "block_number": 999_990,
                "tx_hash": "0xbond",
                "timestamp": 0,
            }
        ]
        return ops, to_block

    async def fetch_token_states(self, token_ids):
        return {
            1: {"core_count": 1, "material_id": 16, "form": 0, "seed": 1,
                "owner": "0x" + "A" * 40},
            2: {"core_count": 2, "material_id": 3, "form": 1, "seed": 2,
                "owner": "0x" + "B" * 40},
            1537: {"core_count": 2, "material_id": 32, "form": 0, "seed": 3,
                   "owner": "0x" + "A" * 40},
        }

    async def close(self):
        self.closed = True


@pytest.fixture
def manager(tmp_path, monkeypatch):
    cache_file = tmp_path / "talismans_cache.json"
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", cache_file)
    m = TalismansManager(poll_interval=30)
    m.client = _FakeClient()
    return m


_REQUIRED_KEYS = {
    "live_tokens", "genesis_minted", "token_drift", "mythic_count",
    "mythic_pct", "mythics_ever_forged", "total_cores",
    "cores_invariant_intact", "cores_invariant_state",
    "operations_24h", "operations_total",
    "top_collectors", "mythic_history", "operations_history",
    "conservation_signal", "cutmerge_signal", "forge_momentum_signal",
    "mythic_scarcity_signal", "activity_events", "essence_tier_matrix",
    "materials_ledger", "current_block", "last_updated_seconds_ago",
    "error_count", "poll_interval", "active_view", "bond_cleave_enabled",
    "cut_merge_enabled",
}


@pytest.mark.asyncio
async def test_all_contract_keys_present(manager):
    data = await manager.fetch_and_compute()
    missing = _REQUIRED_KEYS - set(data.keys())
    assert not missing, f"missing keys: {missing}"


@pytest.mark.asyncio
async def test_core_counts(manager):
    data = await manager.fetch_and_compute()
    assert data["live_tokens"] == 3
    assert data["genesis_minted"] == 1536
    assert data["token_drift"] == 3 - 1536  # -1533


@pytest.mark.asyncio
async def test_cutmerge_signal_locked(manager):
    data = await manager.fetch_and_compute()
    assert data["cutmerge_signal"]["value_str"] == "LOCKED"


@pytest.mark.asyncio
async def test_mythics_ever_forged(manager):
    data = await manager.fetch_and_compute()
    assert data["mythics_ever_forged"] == 1


@pytest.mark.asyncio
async def test_mythic_count_and_pct(manager):
    data = await manager.fetch_and_compute()
    # token 1537 has material 32 -> Mythic
    assert data["mythic_count"] == 1
    assert data["mythic_pct"] == pytest.approx(1 / 3 * 100)


@pytest.mark.asyncio
async def test_second_cycle_does_not_double_count(manager):
    # the fake client re-returns the same bond op every cycle; dedupe must keep
    # the cumulative counters stable across cycles (no drift on re-scan)
    first = await manager.fetch_and_compute()
    second = await manager.fetch_and_compute()
    assert first["operations_total"] == 1
    assert second["operations_total"] == 1
    assert second["mythics_ever_forged"] == 1
    assert len(second["activity_events"]) == 1


@pytest.mark.asyncio
async def test_collections_well_formed(manager):
    data = await manager.fetch_and_compute()
    tc = data["top_collectors"]
    assert isinstance(tc, list) and tc
    assert {"rank", "address", "tokens", "cores", "mythics"} <= set(tc[0].keys())

    ml = data["materials_ledger"]
    assert isinstance(ml, list) and ml
    assert {"rank", "material", "essence", "tokens", "cores"} <= set(ml[0].keys())

    etm = data["essence_tier_matrix"]
    assert "rows" in etm and "totals" in etm
    assert len(etm["rows"]) == 3


@pytest.mark.asyncio
async def test_invariant_intact_first_scan(manager):
    data = await manager.fetch_and_compute()
    assert data["cores_invariant_intact"] is True
    assert data["total_cores"] == 1 + 2 + 2  # 5


@pytest.mark.asyncio
async def test_result_ids_registered(manager):
    await manager.fetch_and_compute()
    assert 1537 in manager.cache.known_ids


@pytest.mark.asyncio
async def test_close_saves_and_closes(manager):
    await manager.fetch_and_compute()
    await manager.close()
    assert manager.client.closed is True


# ---------------------------------------------------------------------------
# HIGH-4: enumeration must not depend on the log lookback
# ---------------------------------------------------------------------------


class _NoLogsClient(_FakeClient):
    """A fresh install whose log scan finds nothing.

    This is the real-world case, not a contrived one: no keyless endpoint
    serves eth_getLogs back to the deploy block, so post-genesis ids created
    before the lookback window are invisible to the log scan forever.
    """

    #: 1537..1755 allocated; the fixture below makes 1537 and 1600 live.
    next_transform_id = 1756

    async def fetch_operation_logs(self, from_block, to_block):
        return [], to_block

    async def fetch_token_states(self, token_ids):
        ids = set(token_ids)
        out = {}
        for tid, mat in ((1, 16), (2, 3), (1537, 32), (1600, 32)):
            if tid in ids:
                out[tid] = {
                    "core_count": 6 if mat == 32 else 1,
                    "material_id": mat,
                    "form": 0,
                    "seed": tid,
                    "owner": "0x" + "a" * 40,
                }
        return out

    async def fetch_collection_flags(self):
        flags = await super().fetch_collection_flags()
        flags["total_supply"] = 4  # what the contract reports
        return flags


@pytest.fixture
def nolog_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)
    m.client = _NoLogsClient()
    return m


@pytest.mark.asyncio
async def test_transform_ids_seeded_without_any_logs(nolog_manager):
    """The whole of HIGH-4: ids come from nextTransformId, not from logs."""
    await nolog_manager.fetch_and_compute()
    known = nolog_manager.cache.known_ids
    assert 1537 in known and 1755 in known
    assert 1756 not in known, "nextTransformId itself is not yet allocated"
    assert 1536 in known, "genesis seeding still applies"


@pytest.mark.asyncio
async def test_enumeration_completes_and_sets_conservation_baseline(nolog_manager):
    """Fresh install: CONSERVATION must reach INTACT, not stick on SYNCING.

    Before the fix the sweep only ever saw genesis ids, so len(tokens) never
    reached totalSupply, the baseline was never set, and the hero cores box
    rendered a permanent false yellow DRIFT.
    """
    data = await nolog_manager.fetch_and_compute()
    assert len(nolog_manager.cache.tokens) == data["live_tokens"] == 4
    assert nolog_manager.cache.cores_invariant_baseline == data["total_cores"]
    assert data["cores_invariant_intact"] is True
    assert data["conservation_signal"]["value_str"] != "SYNCING"


@pytest.mark.asyncio
async def test_post_genesis_mythics_are_counted(nolog_manager):
    """Mythics live almost entirely in the post-genesis id range."""
    data = await nolog_manager.fetch_and_compute()
    assert data["mythic_count"] == 2


@pytest.mark.asyncio
async def test_seed_transform_ids_ignores_unusable_values(nolog_manager):
    """A failed read (0) must not be mistaken for 'no tokens'."""
    before = set(nolog_manager.cache.known_ids)
    nolog_manager._seed_transform_ids(0)
    nolog_manager._seed_transform_ids(1536)
    nolog_manager._seed_transform_ids(1537)  # allocator at the first id => none minted
    assert nolog_manager.cache.known_ids == before


# ---------------------------------------------------------------------------
# HIGH-5: the watermark follows the scan, not the head block
# ---------------------------------------------------------------------------


class _PartialScanClient(_FakeClient):
    """Client whose log scan only ever completes part of the requested range."""

    def __init__(self, scanned_to):
        super().__init__()
        self._scanned_to = scanned_to
        self.requested: list[tuple[int, int]] = []

    async def fetch_operation_logs(self, from_block, to_block):
        self.requested.append((from_block, to_block))
        return [], self._scanned_to


@pytest.mark.asyncio
async def test_watermark_stops_at_last_complete_block(tmp_path, monkeypatch):
    """A dropped page must be re-scanned next cycle, not skipped forever."""
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)
    m.client = _PartialScanClient(scanned_to=999_500)

    await m.fetch_and_compute()
    assert m.cache.last_seen_block["ops"] == 999_500
    assert m.cache.last_seen_block["ops"] != 1_000_000, "must not jump to head"

    # Next cycle resumes immediately after the last completed block.
    await m.fetch_and_compute()
    assert m.client.requested[-1][0] == 999_501


@pytest.mark.asyncio
async def test_watermark_held_when_no_page_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)
    m.cache.last_seen_block["ops"] = 900_000
    # from_block will be 900_001; a scanned_to below that means "no progress".
    m.client = _PartialScanClient(scanned_to=900_000)

    await m.fetch_and_compute()
    assert m.cache.last_seen_block["ops"] == 900_000
    assert m._error_count >= 1, "an incomplete scan must be visible, not silent"

    await m.fetch_and_compute()
    # The same range is retried rather than abandoned.
    assert m.client.requested[0] == m.client.requested[1] == (900_001, 1_000_000)


@pytest.mark.asyncio
async def test_full_scan_advances_watermark_to_head(manager):
    await manager.fetch_and_compute()
    assert manager.cache.last_seen_block["ops"] == 1_000_000


@pytest.mark.asyncio
async def test_raising_client_leaves_watermark_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)

    class _Boom(_FakeClient):
        async def fetch_operation_logs(self, from_block, to_block):
            raise RuntimeError("all endpoints down")

    m.client = _Boom()
    m.cache.last_seen_block["ops"] = 777
    await m.fetch_and_compute()
    assert m.cache.last_seen_block["ops"] == 777


@pytest.mark.asyncio
async def test_caught_up_scan_is_not_counted_as_a_failure(tmp_path, monkeypatch):
    """No new blocks since the last cycle is success, not an incomplete scan.

    from_block would be head+1, which _get_logs answers with an empty list and
    to_block — a value below from_block that must not read as 'no progress'.
    """
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)
    m.client = _FakeClient()
    m.cache.last_seen_block["ops"] = 1_000_000  # already at head

    await m.fetch_and_compute()
    assert m._error_count == 0
    assert m.cache.last_seen_block["ops"] == 1_000_000


# ---------------------------------------------------------------------------
# MEDI-27 / MEDI-28: an RPC outage must not be rendered as an empty collection
# ---------------------------------------------------------------------------


def _manager_on(tmp_path, monkeypatch, client) -> TalismansManager:
    monkeypatch.setattr(tm_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tm_mod, "_CACHE_FILE", tmp_path / "c.json")
    m = TalismansManager(poll_interval=30)
    m.client = client
    return m


class _NoTokenStates(_FakeClient):
    async def fetch_token_states(self, token_ids):
        raise RuntimeError("multicall endpoint down")


class _NoFlags(_FakeClient):
    async def fetch_collection_flags(self):
        raise RuntimeError("multicall endpoint down")


@pytest.mark.asyncio
async def test_a_failed_sweep_keeps_the_previous_token_registry(
    tmp_path, monkeypatch
):
    """MEDI-27: ``set_token_states`` replaces the registry wholesale.

    Writing a truncated (or empty) sweep into it empties the title bar, the
    leaderboard and the matrix — and looks exactly like a collection that
    really has gone to zero.
    """
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())
    good = await m.fetch_and_compute()
    assert good["total_cores"] > 0
    registry = dict(m.cache.tokens)

    m.client = _NoTokenStates()
    degraded = await m.fetch_and_compute()

    assert m.cache.tokens == registry, "the live registry was thrown away"
    assert total_cores(list(m.cache.tokens.values())) == good["total_cores"]
    assert degraded["mythic_count"] == good["mythic_count"]
    assert degraded["error_count"] >= 1, "the outage must be visible"
    # The registry survived, but the sweep did not finish, so the emitted core
    # total is the syncing placeholder rather than a number the hero box would
    # have to label DRIFT (LOW-12).
    assert degraded["cores_invariant_state"] == "syncing"
    assert degraded["total_cores"] is None


@pytest.mark.asyncio
async def test_a_failed_sweep_does_not_persist_a_sample(tmp_path, monkeypatch):
    """The hourly buckets are overwrite-by-hour and get written to disk.

    A sample taken during an outage therefore outlives the outage: it stays in
    the 7-day sparkline unless a good cycle happens to land in the same hour.
    """
    m = _manager_on(tmp_path, monkeypatch, _NoTokenStates())
    await m.fetch_and_compute()
    assert list(m.cache.mythic_hourly) == []
    assert list(m.cache.tokencount_hourly) == []


@pytest.mark.asyncio
async def test_a_flags_outage_falls_back_to_cached_counts(tmp_path, monkeypatch):
    """MEDI-28: the fallback branch was unreachable while the client swallowed.

    With ``fetch_collection_flags`` answering zeros, the dashboard reported
    ``live_tokens=0`` and sampled a 0 into ``tokencount_hourly``, which
    ``forge_momentum_signal`` then read as a bullish green "CONSOLIDATING ▼" —
    a signal manufactured entirely by a network error.
    """
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())
    await m.fetch_and_compute()
    cached_live = len(m.cache.tokens)
    samples = list(m.cache.tokencount_hourly)

    m.client = _NoFlags()
    out = await m.fetch_and_compute()

    assert out["live_tokens"] == cached_live != 0
    assert out["error_count"] >= 1
    assert list(m.cache.tokencount_hourly) == samples, "a zero was persisted"


@pytest.mark.asyncio
async def test_a_degraded_cycle_never_locks_in_a_conservation_baseline(
    tmp_path, monkeypatch
):
    """A stale registry and a cached supply can agree by coincidence.

    The baseline is the collection's core-conservation invariant and is set
    once, permanently; it must only ever come from a cycle that actually read
    both halves of the comparison from chain.
    """
    m = _manager_on(tmp_path, monkeypatch, _NoFlags())
    out = await m.fetch_and_compute()
    assert m.cache.cores_invariant_baseline == 0
    # No baseline means the invariant is unknown, not broken (LOW-12): a
    # failed read is None, never False.
    assert out["cores_invariant_state"] == "syncing"
    assert out["cores_invariant_intact"] is None


# ---------------------------------------------------------------------------
# LOW-12: core conservation is a tri-state, not a bool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_syncing_is_not_reported_as_drift(tmp_path, monkeypatch):
    """An unfinished count must never raise the DRIFT alarm.

    The hero box renders ``cores_invariant_intact`` as a bool -- truthy is a
    green "conserved", anything falsy is a yellow "DRIFT". Collapsing the
    tri-state into that bool meant every cold cache and every partial sweep
    accused the collection of breaking its central invariant, while the
    Signals panel simultaneously and correctly showed CONSERVATION=SYNCING.
    """
    m = _manager_on(tmp_path, monkeypatch, _NoTokenStates())
    out = await m.fetch_and_compute()

    assert out["cores_invariant_state"] == "syncing"
    # Neither of the two legacy keys may assert anything: None makes the hero
    # box fall through to its dim "--" placeholder.
    assert out["cores_invariant_intact"] is None
    assert out["total_cores"] is None
    # ...and the signal layer agrees, in the same frame.
    assert out["conservation_signal"]["value_str"] == "SYNCING"


@pytest.mark.asyncio
async def test_complete_sweep_reports_intact(manager):
    """A full, successful sweep still locks in and reports the invariant."""
    out = await manager.fetch_and_compute()
    assert out["cores_invariant_state"] == "intact"
    assert out["cores_invariant_intact"] is True
    assert out["total_cores"] == 5
    assert out["conservation_signal"]["value_str"] == "INTACT"


@pytest.mark.asyncio
async def test_real_drift_is_still_reported(manager):
    """A genuine invariant break must survive the tri-state (no false calm)."""
    await manager.fetch_and_compute()
    assert manager.cache.cores_invariant_baseline == 5

    # Move the baseline: the next complete sweep now disagrees with it.
    manager.cache.cores_invariant_baseline = 9
    out = await manager.fetch_and_compute()

    assert out["cores_invariant_state"] == "drift"
    assert out["cores_invariant_intact"] is False
    assert out["total_cores"] == 5
    assert out["conservation_signal"]["value_str"].startswith("DRIFT")


# ---------------------------------------------------------------------------
# LOW-13: the cache save must not block the event loop every cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_does_not_serialize_the_cache_on_the_event_loop(
    tmp_path, monkeypatch
):
    """The per-cycle save was a ~12 ms CPU stall on the Textual event loop.

    A blocked loop stops answering keypresses, not just data refreshes, so
    this pins that ``fetch_and_compute`` never calls the blocking serializer
    directly -- it must go through a worker thread.
    """
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())

    loop_thread = threading.get_ident()
    save_threads: list[int] = []
    real_save = m.cache.save_to_file

    def _tracking_save(path):
        save_threads.append(threading.get_ident())
        return real_save(path)

    monkeypatch.setattr(m.cache, "save_to_file", _tracking_save)

    await m.fetch_and_compute()

    assert save_threads, "the first cycle should still persist"
    assert loop_thread not in save_threads, "cache serialized on the event loop"


@pytest.mark.asyncio
async def test_cache_save_is_throttled_across_cycles(tmp_path, monkeypatch):
    """Rewriting hundreds of KB every 30 s buys nothing; a crash only ever
    loses the counters accumulated since the last save."""
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())

    saves = []
    monkeypatch.setattr(m.cache, "save_to_file", lambda path: saves.append(path))

    await m.fetch_and_compute()
    assert len(saves) == 1, "the first cycle must persist"

    for _ in range(5):
        await m.fetch_and_compute()
    assert len(saves) == 1, "every cycle re-serialized the whole cache"

    # Once the interval has elapsed, the next cycle saves again.
    m._last_save_ts -= tm_mod._SAVE_INTERVAL_SECONDS + 1
    await m.fetch_and_compute()
    assert len(saves) == 2


@pytest.mark.asyncio
async def test_close_still_persists_synchronously(tmp_path, monkeypatch):
    """Throttling must not cost the last cycle's state on quit."""
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())
    await m.fetch_and_compute()

    saves = []
    monkeypatch.setattr(m.cache, "save_to_file", lambda path: saves.append(path))
    await m.close()
    assert len(saves) == 1


@pytest.mark.asyncio
async def test_a_failed_save_does_not_break_the_refresh(tmp_path, monkeypatch):
    """Persistence is a side effect; it must never fail a fetch cycle."""
    m = _manager_on(tmp_path, monkeypatch, _FakeClient())

    def _boom(path):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(m.cache, "save_to_file", _boom)
    out = await m.fetch_and_compute()
    assert out["live_tokens"] == 3


def test_seen_tx_ops_is_bounded():
    """The dedupe window is persisted and reloaded -- unbounded growth made
    every save slower forever, across sessions."""
    c = TalismansCache()
    for i in range(tc_mod._SEEN_TX_OPS_MAX + 500):
        c._remember_tx_op(f"key-{i}")

    assert len(c.seen_tx_ops) == tc_mod._SEEN_TX_OPS_MAX
    # FIFO: the oldest keys go, the newest are still deduped.
    assert "key-0" not in c.seen_tx_ops
    assert f"key-{tc_mod._SEEN_TX_OPS_MAX + 499}" in c.seen_tx_ops


def test_loading_an_oversized_dedupe_window_truncates(tmp_path):
    """An over-cap file written by an older build must not survive reload."""
    path = tmp_path / "c.json"
    c = TalismansCache()
    c.seen_tx_ops = {f"key-{i}": None for i in range(tc_mod._SEEN_TX_OPS_MAX + 300)}
    c.save_to_file(str(path))

    c2 = TalismansCache()
    c2.load_from_file(str(path))
    assert len(c2.seen_tx_ops) == tc_mod._SEEN_TX_OPS_MAX
    assert "key-0" not in c2.seen_tx_ops, "oldest keys should be dropped"
    assert f"key-{tc_mod._SEEN_TX_OPS_MAX + 299}" in c2.seen_tx_ops
