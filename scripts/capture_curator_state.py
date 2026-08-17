#!/usr/bin/env python3
"""One-shot, keyless capture of WhitelistCurator's live state -> a JSON bundle.

THE LIST (`--game curator`, MaxPane dashboard #11) watches a contract whose
interesting states are **one-shot**: the hour boundary where
``currentHourTotal()`` zeroes while ``lastActiveHour()`` still names the hour
before it, the first post-grace judged hour with a live deficit, and the
settlement transition itself, which happens with no transaction and no log.
Miss one and it cannot be recreated -- the chain keeps the history, but not the
*view returns* at that instant.

So this script exists to be run in a hurry, by someone who has read nothing
else, from any checkout::

    python3 scripts/capture_curator_state.py --self-test      # prove the UA works
    python3 scripts/capture_curator_state.py --dry-run        # fetch, print, write nothing
    python3 scripts/capture_curator_state.py --label post-grace
    python3 scripts/capture_curator_state.py --curve-probe --label curve-probe

    # A whole timed window, unattended -- one command, no stopwatch.  Crossings
    # are at launchTime + N*3600, i.e. HH:58:47 UTC:
    python3 scripts/capture_curator_state.py --label hour-boundary \\
            --no-logs --no-blockscout --start-at boundary --every 4 --repeat 30

Deliberate properties, each of them a constraint rather than a preference:

* **Stdlib only.**  No ``httpx``, no repo import, no venv.  ``python3`` is
  enough.  It is imported by nothing and imports nothing of ``maxpane_dashboard``.
  Verified end to end on macOS's system ``/usr/bin/python3`` (3.9.6) from a
  directory holding nothing but this file, as well as on 3.14 -- if the
  fixtures are missing it falls back to its inlined selector table and says so
  in the bundle's ``selector_source``.
* **Read-only and keyless.**  ``eth_call`` / ``eth_getBalance`` /
  ``eth_blockNumber`` / ``eth_getLogs`` / ``eth_getBlockByNumber`` and one
  Blockscout GET.  It never builds calldata for a state change, never signs,
  never asks for a key.  ``deposit()``, ``settle()`` and ``rescue()`` are read
  *about*, never called.
* **A real ``User-Agent``.**  publicnode answers HTTP 403 to python-urllib's
  default UA and accepts the identical batch from curl.  That is the single
  most likely way a capture run dies at 20:58 UTC, so ``--self-test`` checks it
  first and it is the first thing to run before a timed window.
* **Never overwrites a bundle.**  The filename carries the UTC instant; a
  second run inside the same second gets a ``-2`` counter.
* **Never aborts on a partial failure.**  A bundle holding three of four
  sections is worth infinitely more than no bundle at all at the only moment it
  could have been taken.  Every failure lands in the bundle's ``errors`` list
  with its URL and message.
* **Records what was seen, not what was expected.**  ``isSettled()`` still
  false at 21:30 is evidence; commit that bundle and say so in the ledger.

The fetch layer takes an injectable *opener* so the tests can drive it with a
canned transport and never touch the network
(``tests/test_capture_curator_state.py``).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Constants -- the chain facts, all verified 2026-08-16.
# --------------------------------------------------------------------------

CONTRACT = "0xcB0b0531e86A9aC36fa865ca8e3DbcCF047fDA91"
DEPLOY_BLOCK = 25769870
LAUNCH_TIME = 1786910327  # creation-tx timestamp == launchTime(), 19:58:47 UTC

STATE_URL = "https://ethereum-rpc.publicnode.com"
LOGS_URL = "https://gateway.tenderly.co/public/mainnet"
LOGS_FALLBACK_URL = "https://eth.drpc.org"
BLOCKSCOUT_URL = "https://eth.blockscout.com/api/v2"

USER_AGENT = "maxpane-capture/1.0 (+https://pypi.org/project/maxpane)"

TIMEOUT_SECONDS = 20
RETRY_BACKOFF_SECONDS = (1.0, 3.0)  # two retries, in this order

#: How far a wall-clock ``--start-at`` may sit in the past and still mean
#: "start now" rather than "the same time tomorrow".  Typing
#: ``--start-at 20:57:00`` at 20:57:30 is the *normal* way a timed window gets
#: run, and reading those thirty seconds as an 86 370-second wait is how the
#: settlement capture would be lost -- silently, behind one line of stderr.
#: Six hours is far wider than any lateness a runbook produces and far narrower
#: than a genuine "tomorrow at this time".
PAST_START_GRACE_SECONDS = 6 * 3600

#: How many of the newest logs get their block timestamp resolved.  Tenderly's
#: ``eth_getLogs`` carries no ``blockTimestamp`` and Blockscout's log items do
#: not either, so the activity feed's HH:MM has to come from a bounded
#: ``eth_getBlockByNumber`` batch on the state pool.
BLOCK_TIMESTAMP_WINDOW = 40

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "curator", "captures")
LIVE_DIR = os.path.join(CAPTURES_DIR, "live")
MANIFEST_PATH = os.path.join(LIVE_DIR, "MANIFEST.md")
BATCH_FIXTURE = os.path.join(CAPTURES_DIR, "batch.json")

#: The 21 parameterless views, in the order of the captured research batch.
#: This table is the *fallback*: when ``captures/batch.json`` is present the
#: selectors are read out of it at run time, because that file is the
#: known-good list actually sent to publicnode.  The signatures come from the
#: ``views`` table of ``captures/hour_boundary_h1_h2.json``.
VIEWS: tuple[tuple[str, str], ...] = (
    ("0xc99a340f", "POINTS_PER_ETH()"),
    ("0x1ea0466e", "creditCap()"),
    ("0x020e185d", "currentHour()"),
    ("0x78f251f3", "currentHourTotal()"),
    ("0xd5f39488", "deployer()"),
    ("0xd8631b3d", "earlyMultiplierBps()"),
    ("0xa4586257", "ethNeededThisHour()"),
    ("0x2a9c657f", "firstJudgedHour()"),
    ("0xa06db7dc", "gracePeriod()"),
    ("0xda25efd9", "hourDuration()"),
    ("0x9d99a86d", "hourlyThreshold()"),
    ("0x3270bb5b", "isSettled()"),
    ("0xa8a036f1", "lastActiveHour()"),
    ("0x790ca413", "launchTime()"),
    ("0x41b3d185", "minDeposit()"),
    ("0x2c379609", "minEscalation()"),
    ("0xd80528ae", "stats()"),
    ("0x7a7d6632", "timeLeftInHour()"),
    ("0xf251fc8c", "totalContributors()"),
    ("0x9b4f50e7", "totalTxCount()"),
    ("0x5f81a57c", "totalVolume()"),
)

SELECTOR_NAMES = dict(VIEWS)

# Selectors used by name in the summary/manifest.
SEL_CURRENT_HOUR = "0x020e185d"
SEL_CURRENT_HOUR_TOTAL = "0x78f251f3"
SEL_EARLY_BPS = "0xd8631b3d"
SEL_ETH_NEEDED = "0xa4586257"
SEL_IS_SETTLED = "0x3270bb5b"
SEL_LAST_ACTIVE_HOUR = "0xa8a036f1"
SEL_STATS = "0xd80528ae"
SEL_TIME_LEFT = "0x7a7d6632"
SEL_TOTAL_CONTRIBUTORS = "0xf251fc8c"
SEL_TOTAL_VOLUME = "0x5f81a57c"

#: The curve probe (WP1.6): the committed 21-call round holds only
#: parameterless views, so the sqrt curve has no onchain witness at all.  These
#: weights straddle the 1e9-wei floor, the exact squares, and three
#: non-squares including the largest real deposit (461.1 ETH).
CURVE_WEIGHTS: tuple[int, ...] = (
    0,
    1,
    10**9 - 1,
    10**9,
    10**18,               # -> 1000 points
    3 * 10**18,           # non-square
    4 * 10**18,           # -> 2000
    7 * 10**18 + 1,       # non-square
    100 * 10**18,         # -> 10000
    461_100_000_000_000_000_000,  # the largest real single send
    1000 * 10**18,        # -> 31622
    2000 * 10**18,        # the ceiling, -> 44721
)

#: Four real wallets, read out of ``captures/tenderly_logs.json``: the top three
#: of the leaderboard by folded ``newWeight`` and one of the nine 60-ETH fan-out
#: farm wallets.
CURVE_WALLETS: tuple[tuple[str, str], ...] = (
    ("0x381fe486d87c7f2633c777f1b5be3105a2a51744", "leaderboard #1 (1.1 + 461.1 ETH)"),
    ("0xbb24cda09cb5a838ec93bae56278dc799f34feb4", "leaderboard #2 (25 + 45 + 170 ETH)"),
    ("0x4ac4a33101abb2aa21167de2b881429b915818a3", "leaderboard #3 (1 + 63.5 ETH)"),
    ("0xbc87ca75ee832c4d6894790958ba8c9d3b48beb6", "60 ETH farm wallet (rank 4)"),
)

CURVE_UINT_FUNCTIONS = ("previewPoints(uint256)",)
CURVE_ADDRESS_FUNCTIONS = ("pointsOf(address)", "weightOf(address)")

#: A vendored selector whose preimage is known, used to prove the inlined
#: keccak is really Keccak-256 and not ``hashlib.sha3_256`` before any computed
#: selector is sent.
KECCAK_CHECK = ("isSettled()", "0x3270bb5b")


# --------------------------------------------------------------------------
# Keccak-256 -- copied, not imported.
# --------------------------------------------------------------------------
# ``maxpane_dashboard/data/keccak.py`` holds the same function, but this script
# must run from a checkout with no venv and must not import the package, so the
# permutation lives here too.  ``hashlib.sha3_256`` is NOT this function: NIST
# changed the domain padding byte from 0x01 to 0x06, so it would produce
# plausible-looking selectors that call nothing.  ``_selector`` checks itself
# against a vendored selector before use.

_KECCAK_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_KECCAK_ROTATIONS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)

_MASK64 = (1 << 64) - 1
_RATE_BYTES = 136


def _rotl64(value: int, shift: int) -> int:
    shift %= 64
    if shift == 0:
        return value & _MASK64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(lanes: list[list[int]]) -> None:
    for round_constant in _KECCAK_ROUND_CONSTANTS:
        parity = [
            lanes[x][0] ^ lanes[x][1] ^ lanes[x][2] ^ lanes[x][3] ^ lanes[x][4]
            for x in range(5)
        ]
        theta = [
            parity[(x - 1) % 5] ^ _rotl64(parity[(x + 1) % 5], 1) for x in range(5)
        ]
        for x in range(5):
            for y in range(5):
                lanes[x][y] ^= theta[x]

        rotated = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                rotated[y][(2 * x + 3 * y) % 5] = _rotl64(
                    lanes[x][y], _KECCAK_ROTATIONS[x][y]
                )

        for x in range(5):
            for y in range(5):
                lanes[x][y] = rotated[x][y] ^ (
                    (~rotated[(x + 1) % 5][y] & _MASK64) & rotated[(x + 2) % 5][y]
                )

        lanes[0][0] ^= round_constant


def keccak256(data: bytes) -> bytes:
    """Keccak-256 digest (32 bytes) -- Ethereum's hash, not SHA-3."""
    message = bytes(data)
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
    while len(out) < 32:
        for i in range(_RATE_BYTES // 8):
            if len(out) >= 32:
                break
            x, y = i % 5, i // 5
            out += lanes[x][y].to_bytes(8, "little")
        else:
            _keccak_f1600(lanes)
    return bytes(out[:32])


def selector(signature: str) -> str:
    """First four bytes of ``keccak256(signature)``, ``0x``-prefixed."""
    return "0x" + keccak256(signature.encode("utf-8"))[:4].hex()


def keccak_self_check() -> bool:
    """True when the inlined keccak reproduces a vendored selector."""
    signature, expected = KECCAK_CHECK
    return selector(signature) == expected


# --------------------------------------------------------------------------
# Tiny ABI helpers (hand-encoded, exactly as the app's clients do).
# --------------------------------------------------------------------------


def encode_uint(value: int) -> str:
    """A uint256 as 64 hex chars, no ``0x`` -- for concatenation into data."""
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    return f"{value:064x}"


def encode_address(address: str) -> str:
    """An address left-padded to 32 bytes, no ``0x``."""
    clean = address.lower().removeprefix("0x")
    if len(clean) != 40:
        raise ValueError(f"not an address: {address!r}")
    return clean.rjust(64, "0")


def hex_to_int(quantity: str | None) -> int | None:
    """An RPC *quantity* (``0x189378e``) as an int, or None if unreadable.

    Not the same shape as an ABI word: quantities are minimal-length, so this
    must not be ``decode_uint``, which insists on a full 32-byte word and would
    read every block number as a failed read.
    """
    if not isinstance(quantity, str):
        return None
    try:
        return int(quantity, 16)
    except ValueError:
        return None


def decode_uint(word: str | None, index: int = 0) -> int | None:
    """Word *index* of a return value as an int, or None if unreadable.

    A failed read is ``None``, never ``0`` -- this contract has three
    legitimate zeros (``currentHourTotal()`` at a boundary,
    ``ethNeededThisHour()`` during grace, ``creditedDelta`` above the cap) and
    they must stay distinguishable from an outage.
    """
    if not isinstance(word, str):
        return None
    clean = word.removeprefix("0x")
    start, end = index * 64, (index + 1) * 64
    if len(clean) < end:
        return None
    try:
        return int(clean[start:end], 16)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Transport.
# --------------------------------------------------------------------------


class CaptureError(Exception):
    """A stage failed.  Carries the URL so the bundle can name it."""

    def __init__(self, message: str, url: str = "", status: int | None = None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.status = status


#: Try IPv4 addresses before IPv6 ones.  Measured on the capture machine:
#: every endpoint here is behind Cloudflare, which answers with two AAAA
#: records; a host with no working IPv6 route waits out the connect timeout on
#: **each** of them before falling back, so one ``eth_blockNumber`` took 40.08 s
#: through urllib and 0.13 s through curl.  A full bundle took 3 m 41 s.  That
#: is the difference between catching an hour boundary and missing it, so the
#: default opener reorders the resolver's answer.  Nothing is filtered out: a
#: v6-only host is still reached, just second.
PREFER_IPV4 = True


def _ipv4_first(getaddrinfo):
    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        infos = getaddrinfo(host, port, family, type, proto, flags)
        return sorted(infos, key=lambda info: 0 if info[0] == socket.AF_INET else 1)

    return resolve


def urllib_opener(url: str, body: bytes | None, headers: dict, timeout: float):
    """The default opener: ``(status, body_bytes)``, never raising on HTTP status.

    Signature is the whole injection seam -- the tests pass a callable with
    this shape and the script never reaches the network.
    """
    request = urllib.request.Request(
        url, data=body, headers=headers, method="POST" if body else "GET"
    )
    original_getaddrinfo = socket.getaddrinfo
    if PREFER_IPV4:
        socket.getaddrinfo = _ipv4_first(original_getaddrinfo)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), response.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a body
        return exc.code, exc.read()
    except Exception as exc:  # URLError, socket timeout, TLS, DNS
        raise CaptureError(f"{type(exc).__name__}: {exc}", url=url) from exc
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _headers(json_body: bool) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def http_json(
    url: str,
    payload=None,
    *,
    opener=urllib_opener,
    timeout: float = TIMEOUT_SECONDS,
    retries: int = 2,
    sleeper=time.sleep,
):
    """POST *payload* (or GET when it is None) and parse JSON.

    Retries twice with 1 s / 3 s backoff.  Raises ``CaptureError`` on a
    non-200, on unparseable JSON, or after the last retry.
    """
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    last: CaptureError | None = None
    for attempt in range(retries + 1):
        try:
            status, raw = opener(url, body, _headers(body is not None), timeout)
            if status != 200:
                snippet = raw[:200].decode("utf-8", "replace") if raw else ""
                raise CaptureError(f"HTTP {status}: {snippet}", url=url, status=status)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise CaptureError(f"unparseable JSON: {exc}", url=url) from exc
        except CaptureError as exc:
            last = exc
            if attempt < retries:
                sleeper(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
    assert last is not None
    raise last


def rpc_batch(url: str, calls: list, **kw):
    """Send a JSON-RPC batch and return the responses sorted by id."""
    response = http_json(url, calls, **kw)
    if isinstance(response, dict):  # a batch may still come back as one error
        raise CaptureError(_rpc_error_text(response) or "batch returned an object", url=url)
    if not isinstance(response, list):
        raise CaptureError(f"batch returned {type(response).__name__}", url=url)
    return sorted(response, key=lambda item: item.get("id", 0))


def rpc_call(url: str, method: str, params: list, **kw):
    """Send one JSON-RPC call and return its ``result``."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    response = http_json(url, payload, **kw)
    if not isinstance(response, dict):
        raise CaptureError(f"expected an object, got {type(response).__name__}", url=url)
    error = _rpc_error_text(response)
    if error:
        raise CaptureError(error, url=url)
    return response.get("result")


def _rpc_error_text(response) -> str:
    if not isinstance(response, dict):
        return ""
    error = response.get("error")
    if not error:
        return ""
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message") or json.dumps(error)
        return f"[{code}] {message}"
    return str(error)


# --------------------------------------------------------------------------
# Error classification -- on message TEXT, never on code.
# --------------------------------------------------------------------------
# Providers reuse -32602 and -32005 for unrelated meanings, so the code says
# nothing.  drpc's routing failure and tenderly's range limit both arrive as
# -32602 in practice; one means "try another host", the other means "ask for
# less".  Classify the words.

_ENDPOINT_LIMITATION_PATTERNS = (
    "can't route",
    "cannot route",
    "no backend",
    "unsupported method",
    "method not found",
    "method not supported",
    "not available on",
    "archive",
    "upgrade",
    "capacity",
    "rate limit",
    "too many requests",
    "forbidden",
    "unauthorized",
    "api key",
)

_RANGE_LIMITATION_PATTERNS = (
    "block range",
    "range is too large",
    "too many blocks",
    "query returned more than",
    "more than 10000 results",
    "response size",
    "too large",
    "limit exceeded",
    "exceed maximum",
    "query timeout",
    "took too long",
)


def looks_like_endpoint_limitation(text: str) -> bool:
    """This host will never answer this question -- try the next host."""
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _ENDPOINT_LIMITATION_PATTERNS)


def is_range_limitation(text: str) -> bool:
    """This host wants a smaller window -- halve it.

    Never parse a provider's *suggested* range: one of them decrements its
    suggestion by a single block per round trip and livelocks anything that
    follows it verbatim.
    """
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _RANGE_LIMITATION_PATTERNS)


# --------------------------------------------------------------------------
# Stages.  Each returns its section and appends to *errors*; none aborts.
# --------------------------------------------------------------------------


def load_selectors(batch_path: str = BATCH_FIXTURE):
    """The 21 parameterless selectors, preferring the committed batch payload.

    The captured ``batch.json`` is the list that actually answered 21/21 on
    publicnode, so it beats anything retyped here.  When it is missing (a bare
    checkout, a copied script), the inlined ``VIEWS`` table stands in.
    """
    try:
        with open(batch_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        found = []
        for call in payload:
            data = call["params"][0]["data"]
            if isinstance(data, str) and len(data) == 10:
                found.append(data.lower())
        if found:
            return found, "batch.json"
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    return [sel for sel, _ in VIEWS], "inlined"


def _batch_entry(by_id: dict, call_id: int, *, url: str, errors: list, stage: str):
    """The response for *call_id*, or ``(None, message)`` with the miss recorded.

    A batch answered HTTP 200 with **fewer items than calls**, or with the ids
    renumbered, is the one shape that can otherwise write ``result: None`` for
    every view while ``errors`` stays empty -- an archived bundle asserting a
    clean capture that never happened.  A 403 is loud; a short batch was
    silent.  An unanswered id is a failure like any other, and so is a
    ``{"jsonrpc": "2.0", "id": 3}`` carrying neither ``result`` nor ``error``.
    """
    item = by_id.get(call_id)
    if item is None:
        message = f"no response for id {call_id} in the batch"
    else:
        message = _rpc_error_text(item)
        if not message and "result" not in item:
            message = f"no result for id {call_id} in the batch"
        if not message:
            return item, ""
    errors.append({"stage": stage, "url": url, "message": message})
    return None, message


def fetch_state(selectors, *, url: str = STATE_URL, errors: list, **kw):
    """One batched ``eth_call`` round over the parameterless views."""
    calls = [
        {
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "eth_call",
            "params": [{"to": CONTRACT.lower(), "data": sel}, "latest"],
        }
        for index, sel in enumerate(selectors)
    ]
    state: dict = {}
    try:
        responses = rpc_batch(url, calls, **kw)
    except CaptureError as exc:
        errors.append({"stage": "state", "url": exc.url or url, "message": exc.message})
        return state
    by_id = {item.get("id"): item for item in responses}
    for index, sel in enumerate(selectors):
        entry = {"name": SELECTOR_NAMES.get(sel, "unknown()")}
        item, error = _batch_entry(
            by_id, index + 1, url=url, errors=errors, stage=f"state {sel}"
        )
        if error:
            entry["error"] = error
        else:
            entry["result"] = item.get("result")
        state[sel] = entry
    return state


def fetch_balance(*, url: str = STATE_URL, errors: list, **kw):
    try:
        return rpc_call(url, "eth_getBalance", [CONTRACT.lower(), "latest"], **kw)
    except CaptureError as exc:
        errors.append({"stage": "balance", "url": exc.url or url, "message": exc.message})
        return None


def fetch_head(*, url: str = STATE_URL, errors: list | None = None, **kw):
    try:
        head = rpc_call(url, "eth_blockNumber", [], **kw)
    except CaptureError as exc:
        if errors is None:
            raise
        errors.append({"stage": "head", "url": exc.url or url, "message": exc.message})
        return None
    return hex_to_int(head) if isinstance(head, str) else None


def fetch_logs(
    from_block: int,
    *,
    to_block: str | int = "latest",
    urls=(LOGS_URL, LOGS_FALLBACK_URL),
    errors: list,
    head: int | None = None,
    **kw,
):
    """Full ``eth_getLogs`` sweep, failing over by message text and halving on range.

    State and logs need different endpoint pools: publicnode batches happily
    but refuses archive ``eth_getLogs``, so it is not in this list at all.
    """
    resolved_to = to_block
    if to_block == "latest" and head is not None:
        resolved_to = head
    for url in urls:
        try:
            logs = _sweep(url, from_block, resolved_to, errors=errors, **kw)
        except CaptureError as exc:
            errors.append({"stage": "logs", "url": exc.url or url, "message": exc.message})
            continue
        return logs, url
    return [], None


def _sweep(url: str, from_block: int, to_block, *, errors: list, depth: int = 0, **kw):
    """One window, halving on a range complaint; raises on anything else."""
    params = {
        "address": CONTRACT.lower(),
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block) if isinstance(to_block, int) else to_block,
    }
    try:
        result = rpc_call(url, "eth_getLogs", [params], **kw)
    except CaptureError as exc:
        if (
            is_range_limitation(exc.message)
            and not looks_like_endpoint_limitation(exc.message)
            and isinstance(to_block, int)
            and to_block > from_block
            and depth < 12
        ):
            middle = from_block + (to_block - from_block) // 2
            errors.append(
                {
                    "stage": "logs range halved",
                    "url": url,
                    "message": f"{exc.message} -> split at {middle}",
                }
            )
            first = _sweep(url, from_block, middle, errors=errors, depth=depth + 1, **kw)
            second = _sweep(url, middle + 1, to_block, errors=errors, depth=depth + 1, **kw)
            return first + second
        raise
    if not isinstance(result, list):
        # Same silence as a short batch: a 200 with no ``result`` array used to
        # become ``logs: []`` with an empty ``errors`` list and an endpoint
        # named as though it had answered.  An empty sweep is a real state --
        # an unreadable one is not, and the other host may still know.
        raise CaptureError(
            f"eth_getLogs answered 200 with {type(result).__name__}, not a list", url=url
        )
    return result


def fetch_block_timestamps(logs, *, url: str = STATE_URL, errors: list,
                           window: int = BLOCK_TIMESTAMP_WINDOW, **kw):
    """``eth_getBlockByNumber`` over the distinct blocks of the newest *window* logs.

    Tenderly's ``eth_getLogs`` returns no ``blockTimestamp`` and Blockscout's
    log items carry none either, so the activity feed's HH:MM has no other
    keyless provenance.  A missing stamp must render ``--:--``, never
    ``00:00`` -- which is why the map is sparse rather than zero-filled.
    """
    stamps: dict = {}
    blocks: list[str] = []
    for log in logs[-window:] if window else logs:
        number = log.get("blockNumber")
        if isinstance(number, str) and number not in blocks:
            blocks.append(number)
    if not blocks:
        return stamps
    calls = [
        {
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "eth_getBlockByNumber",
            "params": [number, False],
        }
        for index, number in enumerate(blocks)
    ]
    try:
        responses = rpc_batch(url, calls, **kw)
    except CaptureError as exc:
        errors.append({"stage": "block timestamps", "url": exc.url or url,
                       "message": exc.message})
        return stamps
    by_id = {item.get("id"): item for item in responses}
    for index, number in enumerate(blocks):
        item, error = _batch_entry(
            by_id, index + 1, url=url, errors=errors, stage=f"block {number}"
        )
        if error:
            continue
        block = item.get("result")
        if isinstance(block, dict) and isinstance(block.get("timestamp"), str):
            stamps[number] = block["timestamp"]
        else:
            # The map stays sparse -- a missing stamp renders ``--:--`` and a
            # zero would render 00:00 -- but the gap is stated, not implied by
            # a key that is simply absent.
            errors.append({"stage": f"block {number}", "url": url,
                           "message": f"no timestamp in the header for block {number}"})
    return stamps


def fetch_blockscout(*, base: str = BLOCKSCOUT_URL, errors: list, **kw):
    """Page 0 of the REST log history, as an independent cross-check."""
    url = f"{base}/addresses/{CONTRACT}/logs"
    try:
        return http_json(url, None, **kw)
    except CaptureError as exc:
        errors.append({"stage": "blockscout", "url": exc.url or url, "message": exc.message})
        return None


def fetch_curve_probe(*, url: str = STATE_URL, errors: list,
                      weights=CURVE_WEIGHTS, wallets=CURVE_WALLETS, **kw):
    """``previewPoints(uint256)`` over a spread of weights + per-wallet views.

    The selectors are computed from their literal signatures so the script
    needs no vendored table -- guarded by ``keccak_self_check()``, because
    ``sha3_256`` would produce four plausible bytes that call nothing.
    """
    probe: dict = {"weights": [], "wallets": []}
    if not keccak_self_check():
        message = "keccak self-check failed: computed selector != vendored isSettled()"
        errors.append({"stage": "curve probe", "url": url, "message": message})
        return probe

    calls = []
    plan = []
    next_id = 1
    for signature in CURVE_UINT_FUNCTIONS:
        sel = selector(signature)
        for weight in weights:
            calls.append({
                "jsonrpc": "2.0", "id": next_id, "method": "eth_call",
                "params": [{"to": CONTRACT.lower(), "data": sel + encode_uint(weight)},
                           "latest"],
            })
            plan.append(("weights", next_id, signature, sel, str(weight), None))
            next_id += 1
    for signature in CURVE_ADDRESS_FUNCTIONS:
        sel = selector(signature)
        for address, note in wallets:
            calls.append({
                "jsonrpc": "2.0", "id": next_id, "method": "eth_call",
                "params": [{"to": CONTRACT.lower(), "data": sel + encode_address(address)},
                           "latest"],
            })
            plan.append(("wallets", next_id, signature, sel, address, note))
            next_id += 1

    try:
        responses = rpc_batch(url, calls, **kw)
    except CaptureError as exc:
        errors.append({"stage": "curve probe", "url": exc.url or url, "message": exc.message})
        return probe
    by_id = {item.get("id"): item for item in responses}
    for bucket, call_id, signature, sel, argument, note in plan:
        entry = {"name": signature, "selector": sel, "argument": argument}
        if note:
            entry["note"] = note
        item, error = _batch_entry(
            by_id, call_id, url=url, errors=errors,
            stage=f"curve {signature}({argument})",
        )
        if error:
            entry["error"] = error
        else:
            entry["result"] = item.get("result")
        probe[bucket].append(entry)
    return probe


# --------------------------------------------------------------------------
# Bundle assembly.
# --------------------------------------------------------------------------


def utc_stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def file_stamp(epoch: float) -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(epoch))


def capture(
    *,
    label: str,
    logs_from: int = DEPLOY_BLOCK,
    curve_probe: bool = False,
    skip_logs: bool = False,
    skip_blockscout: bool = False,
    opener=urllib_opener,
    now=None,
    sleeper=time.sleep,
    state_url: str = STATE_URL,
    logs_urls=(LOGS_URL, LOGS_FALLBACK_URL),
    blockscout: str = BLOCKSCOUT_URL,
):
    """Fetch everything and return the bundle dict.  Never raises on a partial failure."""
    kw = {"opener": opener, "sleeper": sleeper}
    captured_at = int(time.time() if now is None else now)
    errors: list = []

    selectors, selector_source = load_selectors()
    head = fetch_head(url=state_url, errors=errors, **kw)
    state = fetch_state(selectors, url=state_url, errors=errors, **kw)
    balance = fetch_balance(url=state_url, errors=errors, **kw)

    logs: list = []
    logs_endpoint = None
    if not skip_logs:
        logs, logs_endpoint = fetch_logs(
            logs_from, urls=logs_urls, errors=errors, head=head, **kw
        )
    block_timestamps = fetch_block_timestamps(logs, url=state_url, errors=errors, **kw)
    blockscout_page = None
    if not skip_blockscout:
        blockscout_page = fetch_blockscout(base=blockscout, errors=errors, **kw)

    bundle = {
        "label": label,
        "captured_at": captured_at,
        "captured_at_utc": utc_stamp(captured_at),
        "contract": CONTRACT,
        "chain_head": head,
        "selector_source": selector_source,
        "state": state,
        "balance": balance,
        "logs": logs,
        "logs_from_block": hex(logs_from),
        "logs_endpoint": logs_endpoint,
        "block_timestamps": block_timestamps,
        "blockscout_page_0": blockscout_page,
        "endpoints": {
            "state": state_url,
            "logs": list(logs_urls),
            "blockscout": blockscout,
        },
        "errors": errors,
    }
    if curve_probe:
        bundle["curve_probe"] = fetch_curve_probe(url=state_url, errors=errors, **kw)
    return bundle


def summarise(bundle) -> dict:
    """The decoded handful the ledger and the terminal line need."""
    state = bundle.get("state") or {}

    def view(sel, index=0):
        entry = state.get(sel) or {}
        return decode_uint(entry.get("result"), index)

    answered = sum(1 for entry in state.values() if entry.get("result") is not None)
    settled = view(SEL_IS_SETTLED)
    volume = view(SEL_TOTAL_VOLUME)
    balance = bundle.get("balance")
    return {
        "views_answered": answered,
        "views_total": len(state),
        "log_count": len(bundle.get("logs") or []),
        "balance_wei": hex_to_int(balance) if isinstance(balance, str) else None,
        "current_hour": view(SEL_CURRENT_HOUR),
        "current_hour_total_wei": view(SEL_CURRENT_HOUR_TOTAL),
        "early_bps": view(SEL_EARLY_BPS),
        "eth_needed_wei": view(SEL_ETH_NEEDED),
        "time_left_s": view(SEL_TIME_LEFT),
        "last_active_hour": view(SEL_LAST_ACTIVE_HOUR, 0),
        "last_active_total_wei": view(SEL_LAST_ACTIVE_HOUR, 1),
        "settled": None if settled is None else bool(settled),
        "contributors": view(SEL_TOTAL_CONTRIBUTORS),
        "total_volume_wei": volume,
        "stats_volume_wei": view(SEL_STATS, 0),
        "errors": len(bundle.get("errors") or []),
    }


def _eth(wei):
    return None if wei is None else wei / 1e18


def summary_line(bundle) -> str:
    s = summarise(bundle)
    settled = "?" if s["settled"] is None else str(s["settled"]).lower()
    balance = "?" if s["balance_wei"] is None else f"{_eth(s['balance_wei']):.6g}"
    parts = [
        f"{s['views_answered']}/{s['views_total']} views",
        f"{s['log_count']} logs",
        f"balance {balance}",
        f"isSettled={settled}",
        f"hour={s['current_hour']}",
        f"earlyBps={s['early_bps']}",
        f"lastActiveHour={s['last_active_hour']}",
        f"contributors={s['contributors']}",
    ]
    if s["errors"]:
        parts.append(f"{s['errors']} error(s)")
    return " · ".join(parts)


def bundle_path(label: str, epoch: float, directory: str = LIVE_DIR) -> str:
    """A path that never collides -- a second run in the same second gets ``-2``."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label) or "capture"
    base = f"{file_stamp(epoch)}_{safe}"
    candidate = os.path.join(directory, base + ".json")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}-{counter}.json")
        counter += 1
    return candidate


MANIFEST_HEADER = (
    "# Live capture manifest\n"
    "\n"
    "One row per bundle written by `scripts/capture_curator_state.py`, appended\n"
    "never rewritten. Decoded from the bundle at write time; the bundle itself is\n"
    "the authority. `hourTotal` and `needed` are ETH, `lastActive` is\n"
    "`hour/total`.\n"
    "\n"
    "| bundle | captured (UTC) | label | hour | hourTotal | lastActive | earlyBps |"
    " needed | timeLeft | settled | contributors | volume | logs | err |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def manifest_row(filename: str, bundle) -> str:
    s = summarise(bundle)

    def num(value, digits=4):
        return "?" if value is None else f"{value:,.{digits}f}"

    def integer(value):
        return "?" if value is None else f"{value:,}"

    last_active = "?"
    if s["last_active_hour"] is not None:
        last_active = f"{s['last_active_hour']}/{num(_eth(s['last_active_total_wei']), 2)}"
    settled = "?" if s["settled"] is None else ("**true**" if s["settled"] else "false")
    return (
        f"| `{filename}` | {bundle.get('captured_at_utc')} | {bundle.get('label')} "
        f"| {integer(s['current_hour'])} | {num(_eth(s['current_hour_total_wei']), 2)} "
        f"| {last_active} | {integer(s['early_bps'])} "
        f"| {num(_eth(s['eth_needed_wei']), 4)} | {integer(s['time_left_s'])} "
        f"| {settled} | {integer(s['contributors'])} "
        f"| {num(_eth(s['total_volume_wei']), 2)} | {s['log_count']} | {s['errors']} |\n"
    )


def write_bundle(bundle, *, directory: str = LIVE_DIR, manifest: str | None = None) -> str:
    """Write the bundle and append its manifest row.  Returns the bundle path."""
    os.makedirs(directory, exist_ok=True)
    path = bundle_path(bundle["label"], bundle["captured_at"], directory)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=1, sort_keys=False)
        handle.write("\n")

    manifest_path = manifest or os.path.join(directory, "MANIFEST.md")
    exists = os.path.exists(manifest_path)
    with open(manifest_path, "a", encoding="utf-8") as handle:
        if not exists:
            handle.write(MANIFEST_HEADER)
        handle.write(manifest_row(os.path.basename(path), bundle))
    return path


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def self_test(*, url: str = STATE_URL, opener=urllib_opener, sleeper=time.sleep) -> int:
    """One ``eth_blockNumber``, printing ``OK <head>`` or the failure verbatim.

    Run this at 20:50 UTC.  It proves the User-Agent is accepted before the
    window that cannot be retried opens.
    """
    try:
        head = fetch_head(url=url, opener=opener, sleeper=sleeper, retries=1)
    except CaptureError as exc:
        print(f"FAIL {url}: {exc.message}", file=sys.stderr)
        return 1
    if head is None:
        print(f"FAIL {url}: no block number in the response", file=sys.stderr)
        return 1
    print(f"OK {head}")
    return 0


def next_hour_boundary(now: float, launch: int = LAUNCH_TIME, hour: int = 3600) -> int:
    """The next ``launchTime + N*hour`` instant strictly after *now*.

    In wall-clock terms every crossing is at **58 minutes 47 seconds past the
    hour, UTC**, but deriving it from ``launchTime`` is what keeps the script
    right if the contract's own hour is ever read differently.
    """
    elapsed = int(now) - launch
    return launch + (elapsed // hour + 1) * hour


def parse_start_at(value: str, now: float) -> int:
    """``HH:MM:SS`` (UTC), ``@EPOCH``, or ``boundary`` -> an epoch second.

    ``HH:MM:SS`` resolves to the instant with that wall-clock time inside the
    window ``[now - PAST_START_GRACE_SECONDS, now + 24 h - grace)`` -- the next
    such instant, **except** that one which has only just gone stays in the
    past, and the caller then starts immediately (``wait_until`` returns at
    once for a target behind it).

    This is not a nicety.  The rule it replaces was "today if still ahead,
    tomorrow otherwise", which turned a command fired one second late into a
    ~24-hour wait: ``parse_start_at("20:57:00", 20:57:30Z)`` resolved to
    *tomorrow's* 20:57:00, printed one line of stderr and blocked for 86 370
    seconds.  The settlement transition happens once, at 20:58:47 UTC, with no
    transaction and no log; an operator eight seconds late must still capture
    it.  Only a time more than six hours behind is read as tomorrow's, and the
    mirror case -- a time that has just gone as midnight passed, so today's
    copy of it is nearly a day ahead -- is pulled back to yesterday's for the
    same reason.
    """
    text = value.strip()
    if text == "boundary":
        return next_hour_boundary(now)
    if text.startswith("@"):
        return int(text[1:])
    parts = text.split(":")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        raise ValueError(f"not a UTC time, @epoch or 'boundary': {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    midnight = int(now) - int(now) % 86400
    target = midnight + hour * 3600 + minute * 60 + second
    earliest = int(now) - PAST_START_GRACE_SECONDS
    while target < earliest:
        target += 86400
    while target - 86400 >= earliest:
        target -= 86400
    return target


def wait_until(target: float, *, now=time.time, sleeper=time.sleep, tick: float = 1.0) -> None:
    """Block until *target*, in small steps so a Ctrl-C lands promptly."""
    while True:
        remaining = target - now()
        if remaining <= 0:
            return
        sleeper(min(tick, remaining))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_curator_state.py",
        description="Capture WhitelistCurator's live state into a timestamped JSON bundle.",
        epilog="Keyless and read-only. No API key, no signing, no transaction, ever.",
    )
    parser.add_argument(
        "--label", default="capture",
        help="bundle label: grace-late, hour-boundary, post-grace, judged-deficit, "
             "settlement, curve-probe",
    )
    parser.add_argument(
        "--logs-from", type=int, default=DEPLOY_BLOCK, metavar="BLOCK",
        help=f"first block of the eth_getLogs sweep (default the deploy block {DEPLOY_BLOCK})",
    )
    parser.add_argument("--no-logs", action="store_true",
                        help="skip the log sweep (fast repeated polling across a boundary)")
    parser.add_argument("--no-blockscout", action="store_true",
                        help="skip the Blockscout cross-check (keeps a poll series small)")
    parser.add_argument("--curve-probe", action="store_true",
                        help="also batch previewPoints/pointsOf/weightOf (WP1.6)")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and print the summary, write nothing")
    parser.add_argument("--self-test", action="store_true",
                        help="one eth_blockNumber; prints OK <head> or the failure")
    parser.add_argument("--out-dir", default=LIVE_DIR,
                        help="where bundles and MANIFEST.md are written")
    parser.add_argument("--start-at", metavar="HH:MM:SS",
                        help="wait for this UTC instant before the first capture; also "
                             "accepts @EPOCH, or 'boundary' for the next launchTime+N*3600. "
                             "An instant that has already gone (by up to 6 h) captures "
                             "immediately and says so — being late never costs a window")
    parser.add_argument("--every", type=float, default=0.0, metavar="SECONDS",
                        help="seconds between captures when --repeat is above 1")
    parser.add_argument("--repeat", type=int, default=1, metavar="N",
                        help="take N captures (a window sweep: one command, unattended)")
    return parser


def run_series(args, *, opener=urllib_opener, now=time.time, sleeper=time.sleep,
               out=None, err=None) -> int:
    """One capture, or a whole window sweep -- the timed part of the rig.

    A window like the settlement boundary is one command rather than a person
    with a stopwatch: ``--start-at 20:58:20 --every 5 --repeat 30``.  Slots are
    computed from the start instant, not from the previous capture, so a slow
    round trip does not walk the schedule off the boundary.

    A start instant that has **already gone** never waits: it says so on
    stderr and captures immediately, re-anchoring the grid to the real start so
    that a late operator still gets every capture asked for rather than
    spending the first few slots on time that is already behind them.
    """
    # Resolved per call, not bound at import: pytest's capture swaps the
    # streams after this module is loaded.
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err

    start = now()
    if args.start_at:
        target = parse_start_at(args.start_at, start)
        late = start - target
        if late > 0:
            print(
                f"start instant {utc_stamp(target)} passed {int(late)} s ago "
                f"— capturing now",
                file=err,
            )
        else:
            print(f"waiting until {utc_stamp(target)} ({int(target - start)} s)", file=err)
            wait_until(target, now=now, sleeper=sleeper)
            start = target

    for index in range(max(1, args.repeat)):
        if index:
            wait_until(start + index * args.every, now=now, sleeper=sleeper)
        bundle = capture(
            label=args.label,
            logs_from=args.logs_from,
            curve_probe=args.curve_probe,
            skip_logs=args.no_logs,
            skip_blockscout=args.no_blockscout,
            opener=opener,
            now=now(),
            sleeper=sleeper,
        )
        line = summary_line(bundle)
        if args.dry_run:
            print(f"[dry-run] {line}", file=out)
        else:
            path = write_bundle(bundle, directory=args.out_dir)
            print(f"{os.path.relpath(path, REPO_ROOT)} — {line}", file=out)
        for error in bundle["errors"]:
            print(f"  ! {error['stage']}: {error['message']}", file=err)
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return self_test()

    return run_series(args)


if __name__ == "__main__":
    raise SystemExit(main())
