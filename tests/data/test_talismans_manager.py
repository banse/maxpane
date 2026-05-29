"""Tests for the Talismans dashboard manager (WP3b)."""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import talismans_manager as tm_mod
from maxpane_dashboard.data.talismans_manager import TalismansManager


class _FakeClient:
    """Canned-data async client mirroring TalismansClient's surface."""

    def __init__(self):
        self.closed = False

    async def fetch_block_number(self):
        return 1_000_000

    async def fetch_collection_flags(self):
        return {
            "total_supply": 3,
            "genesis_minted": 1536,
            "bond_cleave_enabled": True,
            "cut_merge_enabled": False,
        }

    async def fetch_operation_logs(self, from_block, to_block):
        return [
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
    "cores_invariant_intact", "operations_24h", "operations_total",
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
