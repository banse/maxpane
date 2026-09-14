"""POOL4 FLOW's zero legs on a mainnet sell into headroom, against a real receipt.

The owner read ``0.00`` in BURNED and STAKERS on every row, sells included,
and asked whether more digits would show something. The committed receipt
(``mainnet_sell_into_headroom_receipt.json``, captured 2026-09-15 read-only
and keyless) is the evidence that settles it. The sell paid a 1% LP fee and
nothing else, so the zeros are true zeros. These tests pin that reading at
three layers: the receipt itself, the decoder and the manager's row builder.
The widget's rendering of the same rows is pinned in
``tests/widgets/test_surf_pool4_left.py``.

No test here touches the network: every byte is the committed fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data.surf_manager import SurfManager

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "surf" / "pool4" / "mainnet_sell_into_headroom_receipt.json"
)

POOL_MANAGER = "0x000000000004444c5dc75cb358380d2e3de08a90"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
WEI = 10**18


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


def _split(fx: dict) -> tuple[list[dict], list[dict]]:
    """The receipt's logs as the client's two sweeps would return them.

    ``swaps``: PoolManager ``Swap`` logs filtered on the hook pool's id, the
    same ``[TOPIC_SWAP, pool_id]`` filter the client issues. ``hook``: every
    log the hook contract emitted.
    """
    logs = fx["receipt"]["logs"]
    swaps = [
        l for l in logs
        if l["address"].lower() == POOL_MANAGER
        and l["topics"][0] == P.TOPIC_SWAP
        and l["topics"][1].lower() == fx["pool_id"].lower()
    ]
    hook = [l for l in logs if l["address"].lower() == fx["hook"].lower()]
    return swaps, hook


def _word(hex_topic: str) -> str:
    return "0x" + hex_topic[-40:].lower()


def test_the_receipt_is_the_sell_it_claims_to_be() -> None:
    """The fixture's own premise, checked before anything is read off it."""
    fx = _load()
    assert fx["receipt"]["status"] == "0x1"
    swaps, hook = _split(fx)
    assert len(swaps) == 1, "exactly one swap in this receipt goes through the hook pool"
    topics0 = [l["topics"][0] for l in hook]
    assert topics0.count(P.TOPIC_FEE_COLLECTED) == 1


def test_the_sell_paid_no_burn_and_no_stakers_on_chain() -> None:
    """The chain-side half of the finding, asserted on the receipt's own logs.

    The hook emitted no accrual and no settlement. No IMD moved to the burn
    sink, the distributor, the dripper or the vault. ``totalBurned`` and
    ``totalRewarded`` read the same at the block before and at the head after.
    ``tokensInPool`` sat under ``inventoryCap``, which is why the hook did not
    trim.
    """
    fx = _load()
    _swaps, hook = _split(fx)
    topics0 = {l["topics"][0] for l in hook}
    assert P.TOPIC_ACCRUAL not in topics0
    assert P.TOPIC_CLAIMS_SETTLED not in topics0

    payees = {
        fx[k].lower() for k in ("burn_sink", "distributor", "dripper", "vault")
    }
    imd_out = [
        l for l in fx["receipt"]["logs"]
        if l["address"].lower() == fx["token"].lower()
        and l["topics"][0] == TRANSFER
        and _word(l["topics"][2]) in payees
    ]
    assert imd_out == [], imd_out

    results = fx["state_calls"]["results"]
    before, after = hex(fx["state_calls"]["block_before"]), "latest"
    for name in ("totalBurned", "totalRewarded"):
        assert results[f"{before}:{name}"] == results[f"{after}:{name}"], name
    block_of = hex(fx["state_calls"]["block_of"])
    in_pool = int(results[f"{block_of}:tokensInPool"], 16)
    cap = int(results[f"{block_of}:inventoryCap"], 16)
    assert in_pool < cap

    census = fx["hook_log_census"]["counts"]
    assert census.get(P.TOPIC_ACCRUAL, 0) == 0
    assert census.get(P.TOPIC_CLAIMS_SETTLED, 0) == 0
    assert census[P.TOPIC_FEE_COLLECTED] > 0


def test_the_decoder_reads_the_sell_as_a_fee_with_zero_legs() -> None:
    fx = _load()
    swaps, hook = _split(fx)
    events = P.decode_flow_events(swaps=swaps, hook_logs=hook)
    assert events is not None and len(events) == 1
    ev = events[0]
    assert ev.side == "sell"
    assert ev.tx_hash == fx["tx_hash"]
    assert ev.size_wei == 337_834_800_000_000_000_000
    assert ev.burned_wei == 0
    assert ev.stakers_wei == 0
    assert ev.fee_token_wei == 3_378_347_999_999_999_999
    assert ev.fee_eth_wei is None
    assert ev.settled is True


def test_the_manager_publishes_true_zeros_not_unread_legs() -> None:
    """``0.0``, not ``None``: this is a read that succeeded and found nothing."""
    fx = _load()
    swaps, hook = _split(fx)
    rows = SurfManager._pool4_flow_rows(swaps, hook)
    assert rows is not None and len(rows) == 1
    row = rows[0]
    assert row["side"] == "sell"
    assert row["burned_imd"] == 0.0 and row["burned_imd"] is not None
    assert row["stakers_imd"] == 0.0 and row["stakers_imd"] is not None
    assert abs(row["size_imd"] - 337.8348) < 1e-9
    assert abs(row["fee_imd"] - 3.378348) < 1e-9
    assert row["fee_eth"] is None
