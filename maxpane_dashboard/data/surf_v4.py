"""Uniswap v4 pool-state maths for the surf dashboard.

v4 has no ``slot0()``.  ``PoolManager`` exposes raw storage through
``extsload(bytes32)``, so reading a pool means computing its slot in the
``_pools`` mapping and unpacking the word by hand::

    base   = keccak256(poolId ‖ uint256(6))
    base+0 = sqrtPriceX96 (0-159) | tick (160-183) | protocolFee (184-207) | lpFee (208-231)
    base+3 = liquidity

Pure: no I/O, no addresses, no Textual.  The mapping slot is passed in from
``surf_addresses`` by the caller rather than imported, so this module stays
testable against any pool.
"""

from __future__ import annotations

from maxpane_dashboard.data.keccak import keccak256

_Q96 = 2 ** 96


def pool_state_slots(pool_id: str, mapping_slot: int = 6) -> tuple[str, str]:
    """Return ``(slot0_key, liquidity_key)`` as 0x-prefixed 32-byte hex."""
    raw = bytes.fromhex(pool_id[2:] if pool_id.startswith("0x") else pool_id)
    if len(raw) != 32:
        raise ValueError(f"pool id must be 32 bytes, got {len(raw)}")
    base = int.from_bytes(keccak256(raw + mapping_slot.to_bytes(32, "big")), "big")
    mask = (1 << 256) - 1
    return (
        "0x" + format(base & mask, "064x"),
        "0x" + format((base + 3) & mask, "064x"),
    )


def decode_slot0(word: str) -> tuple[int, int, int]:
    """Unpack ``(sqrtPriceX96, tick, lpFee)``.  ``tick`` is a signed int24."""
    v = int(word, 16)
    sqrt = v & ((1 << 160) - 1)
    tick = (v >> 160) & ((1 << 24) - 1)
    if tick >= 1 << 23:
        tick -= 1 << 24
    lp_fee = (v >> 208) & ((1 << 24) - 1)
    return sqrt, tick, lp_fee


def decode_liquidity(word: str) -> int:
    return int(word, 16)


def price_eth_per_imd(sqrt_price_x96: int | None) -> float | None:
    """ETH per IMD from the pool's sqrt price.

    currency0 is native ETH and currency1 is IMD, so ``(sqrt/2**96)**2`` is
    IMD per ETH and the price we want is its reciprocal.  A zero or missing
    sqrt price is an unread pool: ``None``, never ``0.0``, which would render
    as a free token.
    """
    if not sqrt_price_x96:
        return None
    imd_per_eth = (sqrt_price_x96 / _Q96) ** 2
    if imd_per_eth <= 0:
        return None
    return 1.0 / imd_per_eth
