"""Keccak-256 (the pre-standard variant Ethereum uses), in pure Python.

Why this file exists at all: every selector and event topic in this repo is
precomputed and vendored under ``abis/``, so nothing needed a runtime hash
until ENS.  ENS ``namehash`` is defined recursively over the *labels of a name*
-- and for reverse resolution the name is ``<address>.addr.reverse``, built
from addresses that are only known at runtime.  There is nothing to vendor.

The three alternatives were worse:

* ``hashlib.sha3_256`` is **not** this function.  NIST changed the domain
  padding byte from ``0x01`` to ``0x06`` between Keccak and the final SHA-3
  standard, so the two give completely different digests for the same input.
  Reaching for ``sha3_256`` here is the classic way to get a namehash that is
  self-consistent, plausible-looking, and resolves nothing.
* ``web3_sha3`` over RPC costs a round trip per hash and is disabled on
  several of the keyless endpoints this app depends on.
* ``eth-hash``/``pycryptodome`` would add a compiled wheel to a dependency set
  that is deliberately three pure-Python packages, for one function.

Correctness is pinned in ``tests/data/test_keccak.py`` against the official
empty-string and "abc" vectors, several known Ethereum selectors, and the
published namehash of ``eth``/``vitalik.eth`` -- values that would all diverge
immediately under the SHA-3 padding mistake above.
"""

from __future__ import annotations

_ROUND_CONSTANTS: tuple[int, ...] = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

#: Rotation offsets, indexed ``[x][y]`` over the 5x5 lane grid.
_ROTATION_OFFSETS: tuple[tuple[int, ...], ...] = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)

_MASK64 = (1 << 64) - 1

#: 1600-bit state, 256-bit output -> rate = 1600 - 2*256 = 1088 bits = 136 bytes.
_RATE_BYTES = 136
_OUTPUT_BYTES = 32


def _rotl64(value: int, shift: int) -> int:
    """Rotate a 64-bit lane left by *shift*."""
    shift %= 64
    if shift == 0:
        return value & _MASK64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(lanes: list[list[int]]) -> None:
    """The permutation, applied in place to a 5x5 grid of 64-bit lanes."""
    for round_constant in _ROUND_CONSTANTS:
        # theta
        column_parity = [
            lanes[x][0] ^ lanes[x][1] ^ lanes[x][2] ^ lanes[x][3] ^ lanes[x][4]
            for x in range(5)
        ]
        theta = [
            column_parity[(x - 1) % 5] ^ _rotl64(column_parity[(x + 1) % 5], 1)
            for x in range(5)
        ]
        for x in range(5):
            for y in range(5):
                lanes[x][y] ^= theta[x]

        # rho + pi
        rotated = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                rotated[y][(2 * x + 3 * y) % 5] = _rotl64(
                    lanes[x][y], _ROTATION_OFFSETS[x][y]
                )

        # chi
        for x in range(5):
            for y in range(5):
                lanes[x][y] = rotated[x][y] ^ (
                    (~rotated[(x + 1) % 5][y] & _MASK64) & rotated[(x + 2) % 5][y]
                )

        # iota
        lanes[0][0] ^= round_constant


def keccak256(data: bytes) -> bytes:
    """Keccak-256 digest of *data* (32 bytes).

    This is Ethereum's hash, **not** ``hashlib.sha3_256`` -- the domain
    padding differs (``0x01`` here, ``0x06`` in the NIST standard).
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"keccak256 needs bytes, got {type(data).__name__}")
    message = bytes(data)

    # Pad10*1 with Keccak's original 0x01 domain byte.
    pad_len = _RATE_BYTES - (len(message) % _RATE_BYTES)
    padded = bytearray(message) + bytearray(pad_len)
    padded[len(message)] |= 0x01
    padded[-1] |= 0x80

    lanes = [[0] * 5 for _ in range(5)]
    for offset in range(0, len(padded), _RATE_BYTES):
        block = padded[offset : offset + _RATE_BYTES]
        for i in range(_RATE_BYTES // 8):
            x, y = i % 5, i // 5
            lanes[x][y] ^= int.from_bytes(block[i * 8 : i * 8 + 8], "little")
        _keccak_f1600(lanes)

    out = bytearray()
    while len(out) < _OUTPUT_BYTES:
        for i in range(_RATE_BYTES // 8):
            if len(out) >= _OUTPUT_BYTES:
                break
            x, y = i % 5, i // 5
            out += lanes[x][y].to_bytes(8, "little")
        else:
            _keccak_f1600(lanes)
    return bytes(out[:_OUTPUT_BYTES])


def keccak256_hex(data: bytes) -> str:
    """Keccak-256 digest as a ``0x``-prefixed lowercase hex string."""
    return "0x" + keccak256(data).hex()


def keccak256_text(text: str) -> bytes:
    """Keccak-256 of *text* encoded as UTF-8."""
    return keccak256(text.encode("utf-8"))


__all__ = ["keccak256", "keccak256_hex", "keccak256_text"]
