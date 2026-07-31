"""Minimal EVM ABI codec shared by every on-chain client (MEDI-17).

Pure-stdlib hex/ABI encode and decode helpers. No network, no chain
knowledge, no provider knowledge -- which is exactly why these are safe to
share when the transport around them is not (see :mod:`rpc_common` for the
argument, and ``tests/data/test_rpc_shared.py`` for the guard).

Every function here was found by an AST scan to exist as **two or three
byte-identical copies** (modulo docstrings and comments) across
``talismans_client``, ``ttt_client``, ``fwa_client``, ``cattown_client`` and
``ocm_client``. ``fwa_client``'s own module docstring admits the provenance:
"copied verbatim from ``talismans_client``". Solidity's ABI is a fixed,
published encoding; a fix to one copy is a fix every other copy needs, so
the fork has no upside.

Deliberately **not** moved here: helpers that exist in only one client
(``ttt._to_hex``, ``ttt._addr_to_topic``, ``ttt._decode_string_dynamic``,
``fwa._decode_int`` / ``_decode_bool`` / ``_decode_string``). One copy is not
duplication, and hoisting single-use code into a shared module is how shared
modules turn into junk drawers.

Clients import these under their historical private names::

    from .evm_abi import decode_uint as _decode_uint

so every existing call site and every test that reaches for
``ttt_client._decode_uint`` keeps working unchanged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: ``aggregate3(Call3[])`` on Multicall3. Identical in all three clients that
#: batch (talismans, ttt, fwa -- the last via its ``SELECTORS`` table).
SEL_AGGREGATE3 = "0x82ad56cb"

#: The all-zero address, lowercase, ``0x``-prefixed.
ZERO_ADDRESS = "0x" + "0" * 40


# ---------------------------------------------------------------------------
# Hex primitives
# ---------------------------------------------------------------------------


def strip0x(hex_str: str) -> str:
    """Drop a leading ``0x`` if present."""
    return hex_str[2:] if hex_str.startswith("0x") else hex_str


def pad_left(hex_no_0x: str, width: int = 64) -> str:
    """Left-pad a hex string with zeros to *width* characters."""
    return hex_no_0x.lower().rjust(width, "0")


def pad_address(addr: str) -> str:
    """Zero-pad a ``0x``-prefixed address to 32 bytes for ABI encoding.

    Kept distinct from :func:`encode_address` on purpose. It uses ``zfill``
    rather than ``rjust``, and ``zfill`` treats a leading ``+``/``-`` as a
    sign. The two agree on every hex address, but "agree on the inputs we
    happen to pass" is not the same as "are the same function", and this is a
    refactor, not a rewrite.
    """
    return addr[2:].lower().zfill(64)


def addr_from_topic(topic: str) -> str:
    """Convert a 32-byte topic back to a 20-byte address (lowercase ``0x...``)."""
    return "0x" + strip0x(topic).lower()[-40:]


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def decode_uint(hex_data: str, word_idx: int = 0) -> int:
    """Decode an **unsigned** uint256 at word slot *word_idx* of a hex blob."""
    raw = strip0x(hex_data)
    start = word_idx * 64
    chunk = raw[start : start + 64]
    if not chunk:
        return 0
    return int(chunk, 16)


def decode_uint256(hex_str: str) -> int:
    """Decode a single uint256 from a hex string (with or without ``0x``).

    The cattown/ocm spelling of :func:`decode_uint`; kept as its own name
    because those two clients call it that everywhere.
    """
    return decode_uint(hex_str, 0)


def decode_address(hex_data: str, word_idx: int = 0) -> str:
    """Decode an address at word slot *word_idx* (lower 20 bytes)."""
    raw = strip0x(hex_data)
    start = word_idx * 64
    chunk = raw[start : start + 64]
    if not chunk:
        return ZERO_ADDRESS
    return "0x" + chunk[-40:].lower()


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def encode_uint(value: int) -> str:
    """Encode an integer as a 32-byte hex word (no ``0x`` prefix)."""
    if value < 0:
        # Two's complement for int256 (we only need positive here, but be safe)
        value &= (1 << 256) - 1
    return pad_left(hex(value)[2:], 64)


def encode_address(addr: str) -> str:
    """Encode an address as a 32-byte hex word (no ``0x`` prefix)."""
    return pad_left(strip0x(addr).lower(), 64)


def encode_call3(target: str, call_data: str, allow_failure: bool = True) -> str:
    """Encode a single ``Call3`` struct (no ``0x`` prefix).

    ``call_data`` is stripped of its ``0x`` prefix here -- FWA's TRAP 4. A
    Call3 is dynamic because of the ``bytes`` field, so this is only the
    inline representation; the array encoding lives in
    :func:`encode_aggregate3`.
    """
    cd = strip0x(call_data)
    # The dynamic field offset within this tuple is 3 words (target + bool +
    # offset header) -- i.e. 0x60.
    head = (
        encode_address(target)
        + pad_left("01" if allow_failure else "00", 64)
        + pad_left("60", 64)
    )
    # Tail: length-prefixed bytes, padded to a 32-byte boundary.
    cd_len = len(cd) // 2
    cd_padded = cd + "0" * ((64 - (len(cd) % 64)) % 64)
    tail = pad_left(hex(cd_len)[2:], 64) + cd_padded
    return head + tail


def encode_aggregate3(calls: list[tuple[str, str, bool]]) -> str:
    """Build calldata for ``aggregate3(Call3[])``.

    Each input tuple is ``(target_address, callData_hex, allow_failure)``.
    Returns a hex string prefixed with ``0x`` -- and containing ``"0x"``
    exactly once, at index 0 (FWA TRAP 4's assertion).
    """
    body = ""
    body += pad_left("20", 64)  # offset to the dynamic array
    body += pad_left(hex(len(calls))[2:], 64)  # array length

    # Each Call3 is itself dynamic (it contains ``bytes``), so the array body
    # is N offsets followed by the concatenated encoded tuples.
    encoded_tuples = [encode_call3(t, cd, af) for (t, cd, af) in calls]
    n = len(encoded_tuples)
    offsets: list[int] = []
    cursor = n * 32  # in bytes, from the start of the array body
    for tup in encoded_tuples:
        offsets.append(cursor)
        cursor += len(tup) // 2
    body += "".join(pad_left(hex(o)[2:], 64) for o in offsets)
    body += "".join(encoded_tuples)
    return SEL_AGGREGATE3 + body


def decode_aggregate3_result(hex_data: str) -> list[tuple[bool, str]]:
    """Decode ``aggregate3``'s ``Result[] (bool success, bytes returnData)``.

    Returns ``(success, returnData_hex)`` per sub-call, **in request order**.
    A sub-call that reverted under ``allowFailure=true`` comes back as
    ``(False, "0x")`` and keeps its slot -- a decoder that drops failures
    mis-aligns the whole batch.
    """
    raw = strip0x(hex_data)
    if not raw:
        return []
    try:
        # First word: offset to the dynamic array (typically 0x20).
        # Next word: array length. Then N offsets, one per Result tuple.
        array_offset_bytes = int(raw[0:64], 16)
        base = array_offset_bytes * 2  # in chars
        length = int(raw[base : base + 64], 16)
        elements_base = base + 64

        results: list[tuple[bool, str]] = []
        for i in range(length):
            elt_off_bytes = int(
                raw[elements_base + i * 64 : elements_base + (i + 1) * 64],
                16,
            )
            tup_start = elements_base + elt_off_bytes * 2
            success = int(raw[tup_start : tup_start + 64], 16) != 0
            bytes_off = int(raw[tup_start + 64 : tup_start + 128], 16)
            bytes_chars_start = tup_start + bytes_off * 2
            bytes_len = int(raw[bytes_chars_start : bytes_chars_start + 64], 16)
            body = raw[
                bytes_chars_start + 64 : bytes_chars_start + 64 + bytes_len * 2
            ]
            results.append((success, "0x" + body))
        return results
    except (ValueError, IndexError) as exc:
        logger.warning("Failed to decode aggregate3 result: %s", exc)
        return []


__all__ = [
    "SEL_AGGREGATE3",
    "ZERO_ADDRESS",
    "addr_from_topic",
    "decode_address",
    "decode_aggregate3_result",
    "decode_uint",
    "decode_uint256",
    "encode_address",
    "encode_aggregate3",
    "encode_call3",
    "encode_uint",
    "pad_address",
    "pad_left",
    "strip0x",
]
