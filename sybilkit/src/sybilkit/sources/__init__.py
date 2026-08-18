"""Keyless fetchers — the only part of ``sybilkit`` that ever opens a socket.

**Optional.**  ``pip install sybilkit`` gives the pure core with zero
third-party packages; ``pip install "sybilkit[sources]"`` adds ``httpx`` and
these three modules.  ``import sybilkit.sources`` works either way — the
transport is imported **lazily, inside the call that needs it**, so
``sybilkit --help`` and every core import survive on the pure install and a
real fetch is where the missing extra is named.

Four rules, each of them a bug that shipped somewhere in this repo first.

KEYLESS, AND CHECKED AT CONSTRUCTION
    :class:`SourceConfig` refuses a dead or newly-keyed host in its
    ``__post_init__``.  A keyed endpoint in a keyless tool is a bug, never a
    fallback, and a mistake here should be a ``ValueError`` at wiring time
    rather than a session that quietly renders unavailable.

A REAL ``User-Agent``, ON EVERY REQUEST
    ``ethereum-rpc.publicnode.com`` answers ``403`` to a library-default UA
    and answered the byte-identical batch from ``curl``.  ``eth.blockscout.com``
    stalls python-urllib outright while serving httpx and curl in under a
    second.  The header goes on the **request**, not only on a client this
    module built: every caller may inject their own client (every test does),
    and a constructor-level header would be absent from exactly those requests.

MESSAGE TEXT, NEVER THE CODE
    Providers reuse ``-32602`` and ``-32005`` for unrelated meanings — drpc's
    "Can't route your request" arrives wearing a code other providers spend on
    a genuinely malformed request.  Classify on the message, **in both
    directions**: a short circuit needs the message to match
    :data:`MALFORMED_REQUEST_PATTERNS`, and an unrecognised one rotates.  A
    real malformed request short-circuits the whole chain, because it fails
    identically everywhere and rotating on our own bug triples the request
    count and hides it.  The one place a *code* is still read is an error
    object carrying no message at all — there is nothing else to go on, and
    that exception is documented on ``is_endpoint_limitation`` itself.

A PROVIDER'S SUGGESTED RANGE IS NEVER ADOPTED
    One of them decrements a single block per round trip: ask for 800, be told
    799; ask for 799, be told 798; forever.  We halve **our own** span, at most
    :attr:`SourceConfig.max_shrinks` times, then fail honestly.  This is the
    mandated bite in ``tests/test_sources.py``.

And the outage rule the whole distribution keeps: **a failed read is ``None``,
never ``0`` and never ``[]``.**  An empty list from a fetcher would read as
"this contract has no history", which is the one conclusion an outage must
never reach.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# The optional transport
# ---------------------------------------------------------------------------


class MissingDependency(ImportError):
    """``sybilkit.sources`` was driven without the ``[sources]`` extra."""


def require_httpx():
    """The transport, imported **now** rather than at module load.

    Two things depend on the laziness: the pure install can import this package
    (so ``sybilkit --help`` works, and so the CLI can name the extra instead of
    dying on an ImportError traceback), and the core's stdlib-only gate stays
    meaningful.
    """
    try:
        import httpx  # noqa: PLC0415 — deliberately lazy
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise MissingDependency(
            "sybilkit.sources needs httpx, which ships in the optional extra: "
            'pip install "sybilkit[sources]"'
        ) from exc
    if httpx is None:  # a monkeypatched-out module, and the same answer
        raise MissingDependency(
            "sybilkit.sources needs httpx, which ships in the optional extra: "
            'pip install "sybilkit[sources]"'
        )
    return httpx


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

#: The one identifying string every request carries.  Not a courtesy.
USER_AGENT = "sybilkit (keyless read-only onchain cluster analysis)"

#: Logs pool.  ``publicnode`` is deliberately **absent**: it is the strongest
#: keyless batcher there is for state, and it refuses archive ``eth_getLogs``,
#: so including it spends a round trip and a retry on every sweep before
#: rotating to an endpoint that can answer.
LOG_RPCS: tuple[str, ...] = (
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",
)

#: State pool — plain ``eth_call`` and batched ``eth_getTransactionByHash``.
STATE_RPCS: tuple[str, ...] = (
    "https://ethereum-rpc.publicnode.com",
    "https://gateway.tenderly.co/public/mainnet",
)

BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"

#: Hosts that are dead, newly keyed, or useless.  Verified, not guessed.
BANNED_HOSTS: frozenset[str] = frozenset(
    {
        "eth.llamarpc.com",     # HTTP 521, origin down
        "rpc.ankr.com",         # now requires a key
        "cloudflare-eth.com",   # -32046 on Ethereum
        "api.reservoir.tools",  # sunset, DNS gone
    }
)

#: Whole domains whose every subdomain is keyed.
BANNED_HOST_SUFFIXES: tuple[str, ...] = ("alchemy.com", "infura.io", "etherscan.io")


def assert_keyless(url: str) -> str:
    """*url* back, or ``ValueError`` if its host is dead or keyed."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise ValueError(f"{url!r} has no host")
    if host in BANNED_HOSTS or host.endswith(BANNED_HOST_SUFFIXES):
        raise ValueError(
            f"{url} is a banned host (dead, keyed or useless) — see "
            "sybilkit.sources.BANNED_HOSTS.  sybilkit is keyless; a keyed "
            "endpoint is a bug, not a fallback."
        )
    return url


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Endpoints and budgets, validated at construction.

    ``log_chunk_blocks = 800``
        Measured: the tenderly gateway serves this subject's ``eth_getLogs`` in
        800-block chunks without a split.  The bounded halving below is the net
        for a denser history, not a substitute for a sane starting page.

    ``tx_batch_size = 40``
        publicnode throttles batches much above this; 40 is what was measured
        clean.

    ``blockscout_min_interval = 1/3``
        ~3 requests a second is what ran clean against Blockscout with zero
        ``429``s across 221 lookups.
    """

    log_rpcs: tuple[str, ...] = LOG_RPCS
    state_rpcs: tuple[str, ...] = STATE_RPCS
    blockscout_base: str = BLOCKSCOUT_BASE
    user_agent: str = USER_AGENT
    log_chunk_blocks: int = 800
    min_log_window: int = 50
    max_shrinks: int = 4
    tx_batch_size: int = 40
    max_retries: int = 2
    request_timeout: float = 20.0
    inter_call_delay: float = 0.12
    blockscout_min_interval: float = 1 / 3
    blockscout_max_pages: int = 20
    backoff_seconds: tuple[float, ...] = field(default=(0.5, 1.5))

    def __post_init__(self) -> None:
        if not self.log_rpcs or not self.state_rpcs:
            raise ValueError("an empty endpoint pool can never answer anything")
        for url in (*self.log_rpcs, *self.state_rpcs, self.blockscout_base):
            assert_keyless(url)
        if self.log_chunk_blocks < 1:
            raise ValueError("log_chunk_blocks must be >= 1")
        if self.tx_batch_size < 1:
            raise ValueError("tx_batch_size must be >= 1")

    @property
    def headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": self.user_agent}


DEFAULT_CONFIG = SourceConfig()


# ---------------------------------------------------------------------------
# Error classification — the message, never the code
# ---------------------------------------------------------------------------

#: "This endpoint can't", as opposed to "this request is bad".
ENDPOINT_LIMITATION_PATTERNS: tuple[str, ...] = (
    "limited to", "block range", "range is too large", "ranges over",
    "exceeds", "too large", "too many", "archive", "unauthorized",
    "authenticate", "free plan", "upgrade", "not supported", "unsupported",
    "capacity", "rate limit", "timeout", "try again", "cannot fulfill",
    # drpc, observed live: "Can't route your request. Try again later."
    "can't route", "cannot route", "route your request",
)

#: The shrinkable class only — "you asked for too much in one call".  Providers
#: say that in two units and both are recovered the same way, by halving: a
#: **block-range** cap and a **result-count / response-size** cap.
RANGE_LIMITATION_PATTERNS: tuple[str, ...] = (
    "limited to", "block range", "range is too large", "ranges over",
    "more than", "too many results", "max results", "maximum results",
    "result limit", "query returned", "response size",
)

MALFORMED_REQUEST_CODES = frozenset({-32600, -32601, -32602, -32604, -32700})

#: "This request is bad", in the words providers actually use.  A short circuit
#: needs the **message** to agree: the codes above are reused for unrelated
#: meanings, and a code-only classification bins drpc's routing refusal as our
#: own bug and stops the pool dead.
#:
#: "Method not found" is deliberately **absent**.  The pools here are
#: heterogeneous — ``publicnode`` refuses archive ``eth_getLogs`` outright —
#: so "this endpoint does not have that method" is an endpoint limitation that
#: must rotate, not a request that is ours to fix.
MALFORMED_REQUEST_PATTERNS: tuple[str, ...] = (
    "invalid params", "invalid parameters", "invalid argument",
    "invalid request", "invalid json", "parse error", "unknown block",
    "cannot unmarshal", "hex string", "odd length", "missing value",
    "malformed",
)

#: HTTP statuses that mean "this endpoint is not going to answer" — rotate,
#: do not retry.
DEAD_STATUS_CODES = frozenset({401, 402, 403, 404, 405, 410, 429, 500, 502, 503, 521})


def _message(err: Any) -> str:
    if isinstance(err, dict):
        return str(err.get("message") or "").lower()
    return str(err or "").lower()


def is_range_limitation(err: Any) -> bool:
    """True only for the shrinkable "you asked for too much" class.

    A **string** error body counts: drpc answers some log calls with a bare
    routing string rather than an object, and a classifier that only reads
    dicts bins it as malformed and short-circuits the pool.
    """
    return any(frag in _message(err) for frag in RANGE_LIMITATION_PATTERNS)


def is_endpoint_limitation(err: Any) -> bool:
    """True if *err* reads as "this endpoint can't", not "this request is bad".

    **The message decides, in both directions.**  A non-dict body (drpc's
    routing **string**) is an endpoint problem by construction: a provider that
    could not even shape an error object did not judge our request.  And a
    short circuit — which stops the whole pool — now needs the message to agree
    with :data:`MALFORMED_REQUEST_PATTERNS`, because the codes are reused for
    unrelated meanings and ending on ``code not in MALFORMED_REQUEST_CODES``
    was classification by code, which is exactly what this module's own
    docstring forbids.  An *unrecognised* message therefore rotates: that costs
    a round trip, while short-circuiting on somebody's unfamiliar wording hides
    a working endpoint.

    The single documented use of a code is the one case with no text to
    classify: an error object carrying **no message at all**.
    """
    message = _message(err)
    if any(frag in message for frag in ENDPOINT_LIMITATION_PATTERNS):
        return True
    if not isinstance(err, dict):
        return True
    if not message:
        return err.get("code") not in MALFORMED_REQUEST_CODES
    return not any(frag in message for frag in MALFORMED_REQUEST_PATTERNS)


#: The one dead status that means "later" rather than "never".
RETRY_AFTER_STATUS = 429


def _dead_status_pause(config: SourceConfig, status: int, attempt: int) -> float:
    """Seconds to wait before rotating off *status* — non-zero only for 429.

    ``429`` sat in :data:`DEAD_STATUS_CODES` and broke straight to the next URL
    with no pacing, so a throttled pool was hammered at full speed all the way
    round the rotation.  Every other dead status is "this endpoint is not going
    to answer", and waiting on one buys nothing but latency.
    """
    if status != RETRY_AFTER_STATUS:
        return 0.0
    return config.backoff_seconds[min(attempt, len(config.backoff_seconds) - 1)]


def _slot_of(by_id: dict, raw: Any) -> int | None:
    """The payload slot an answered batch entry belongs to, by ``id``.

    JSON-RPC ids are opaque and a provider is free to echo ``"1"`` for ``1``.
    A strict dict lookup dropped exactly those slots: they stayed ``None``,
    decoded to nothing and landed in ``pending`` — a silent partial that looks
    exactly like a reorg, from an endpoint that answered everything correctly.
    """
    if isinstance(raw, bool):
        return None  # `True` would alias the id `1`
    slot = by_id.get(raw)
    if slot is not None:
        return slot
    if isinstance(raw, str):
        try:
            return by_id.get(int(raw.strip()))
        except ValueError:
            return None
    return None


class RangeTooWide(RuntimeError):
    """``eth_getLogs`` failed because the requested window is too wide."""


class MalformedRequest(RuntimeError):
    """Our own bug: it fails identically everywhere, so it never rotates."""


class AllEndpointsFailed(RuntimeError):
    """Every endpoint in the pool refused or could not be reached."""


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------


def hex_to_int(value: Any) -> int | None:
    """A ``0x`` quantity as an ``int``, or ``None`` — **never** ``0`` on
    failure."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16) if value.lower().startswith("0x") else int(value, 10)
    except ValueError:
        return None


def data_words(row: Any) -> list[str]:
    """A log row's ``data`` field as 32-byte hex words."""
    data = row.get("data") if isinstance(row, dict) else None
    if not isinstance(data, str):
        return []
    body = data[2:] if data.lower().startswith("0x") else data
    return [body[i : i + 64] for i in range(0, len(body) - len(body) % 64, 64)]


def addr_from_topic(topic: Any) -> str | None:
    """The lowercase address packed in an indexed-address topic."""
    if not isinstance(topic, str):
        return None
    body = topic[2:] if topic.lower().startswith("0x") else topic
    if len(body) != 64:
        return None
    return "0x" + body[-40:].lower()


def jsonrpc(request_id: int, method: str, params: list) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def chunks(items: Iterable[Any], size: int) -> list[list[Any]]:
    out: list[list[Any]] = []
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            out.append(batch)
            batch = []
    if batch:
        out.append(batch)
    return out


# ---------------------------------------------------------------------------
# keccak-256 — so that every ABI identifier is COMPUTED
# ---------------------------------------------------------------------------
#
# ~50 lines of pure stdlib rather than a vendored table of hashes, and the
# reason is CLAUDE.md hard constraint 4.  Rulings R10 and R13 require the CLI
# to read ``POINTS_PER_ETH`` and ``minDeposit`` **live**, which means building
# their four-byte selectors; and the log sweep needs ``Deposited``'s topic0.
# Pasted hashes cannot be checked by anything, while a keccak can be checked
# against the canonical empty-string vector and against a deployment's own
# independently-vendored identifiers — which ``tests/test_sources.py`` does.

_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)

_MASK64 = (1 << 64) - 1
_KECCAK_RATE = 136  # (1600 - 2*256) / 8, in bytes


def _rotl64(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64 if shift else value


def _keccak_f(lanes: list[list[int]]) -> None:
    for rnd in range(24):
        c = [lanes[x][0] ^ lanes[x][1] ^ lanes[x][2] ^ lanes[x][3] ^ lanes[x][4]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                lanes[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rotl64(lanes[x][y], _KECCAK_ROT[x][y])
        for x in range(5):
            for y in range(5):
                lanes[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y] & _MASK64)
        lanes[0][0] ^= _KECCAK_RC[rnd]


def keccak256(data: bytes) -> bytes:
    """Keccak-256 (Ethereum's, with the original ``0x01`` padding — **not**
    SHA3-256's ``0x06``)."""
    lanes = [[0] * 5 for _ in range(5)]
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _KECCAK_RATE:
        padded.append(0x00)
    padded[-1] |= 0x80
    for offset in range(0, len(padded), _KECCAK_RATE):
        block = padded[offset : offset + _KECCAK_RATE]
        for i in range(_KECCAK_RATE // 8):
            lane = int.from_bytes(block[i * 8 : i * 8 + 8], "little")
            lanes[i % 5][i // 5] ^= lane
        _keccak_f(lanes)
    out = bytearray()
    for i in range(4):  # 32 bytes = 4 lanes off the rate
        out += lanes[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out)


def keccak256_hex(data: bytes) -> str:
    return "0x" + keccak256(data).hex()


def event_topic(signature: str) -> str:
    """``topic0`` for a canonical event signature (no argument names, no
    ``indexed`` — indexedness does not enter the preimage; the *types* do)."""
    return keccak256_hex(signature.encode("ascii"))


def selector(signature: str) -> str:
    """The four-byte function selector for a canonical function signature."""
    return keccak256_hex(signature.encode("ascii"))[:10]


# ---------------------------------------------------------------------------
# The shared HTTP plumbing
# ---------------------------------------------------------------------------


def open_client(config: SourceConfig = DEFAULT_CONFIG, *, transport: Any = None):
    """A client this package owns, or one wrapping *transport* for a test.

    The single construction site in the package: every fetcher takes
    ``client=`` or ``transport=``, so injecting a transport in a test really
    does cover every request the code can make.
    """
    httpx = require_httpx()
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(config.request_timeout),
        "follow_redirects": True,
        "headers": dict(config.headers),
    }
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.AsyncClient(**kwargs)


class _Session:
    """One client plus the pacing state, and who is responsible for closing it.

    Constructed by every fetcher from the ``client=``/``transport=`` pair, so
    the three modules share exactly one answer to "whose client is this".
    """

    __slots__ = ("client", "config", "_owned", "_sleep", "_last_at", "_id")

    def __init__(
        self,
        config: SourceConfig,
        *,
        client: Any = None,
        transport: Any = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self._owned = client is None
        self.client = client if client is not None else open_client(
            config, transport=transport
        )
        if sleep is None:
            import asyncio  # noqa: PLC0415 — only the I/O path needs a loop

            sleep = asyncio.sleep
        self._sleep = sleep
        self._last_at = 0.0
        self._id = 0

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owned:
            await self.client.aclose()

    def next_id(self) -> int:
        self._id += 1
        return self._id

    async def pace(self, seconds: float) -> None:
        if seconds > 0:
            await self._sleep(seconds)

    async def post(self, url: str, payload: Any):
        await self.pace(self.config.inter_call_delay)
        return await self.client.post(
            url, json=payload, headers=dict(self.config.headers)
        )

    async def get(self, url: str, params: Any = None, *, delay: float | None = None):
        await self.pace(
            self.config.inter_call_delay if delay is None else delay
        )
        return await self.client.get(
            url, params=params, headers=dict(self.config.headers)
        )


async def rpc_call(
    session: _Session, urls: tuple[str, ...], method: str, params: list
) -> Any:
    """One JSON-RPC call across a pool, classified on the message.

    Raises :class:`RangeTooWide` for the shrinkable class (the caller halves
    its own window), :class:`MalformedRequest` without rotating for our own
    bug, and :class:`AllEndpointsFailed` when the pool is exhausted.

    **A 200 body that is not a JSON-RPC object rotates.**  A single answer is
    an object by spec; an HTML error page or a bare array is an endpoint that
    did not answer, not an answer of ``None`` and not a page of zero rows.
    """
    payload = jsonrpc(session.next_id(), method, params)
    httpx = require_httpx()
    last: BaseException | None = None
    for url in urls:
        for attempt in range(session.config.max_retries):
            try:
                resp = await session.post(url, payload)
                if resp.status_code in DEAD_STATUS_CODES:
                    last = RuntimeError(f"{url} -> HTTP {resp.status_code}")
                    await session.pace(
                        _dead_status_pause(session.config, resp.status_code, attempt)
                    )
                    break
                body: Any = None
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    # A 200 we cannot read is NOT an answer.  A ``text/html``
                    # error page used to come back as ``None`` with **no
                    # rotation**, and a bare ``[]`` came back verbatim — which
                    # ``_page`` accepted as a page of zero logs, so a sweep
                    # completed *empty* during an outage.  A single JSON-RPC
                    # answer is an object by spec, even when its ``result`` is a
                    # list; anything else is an endpoint that did not answer.
                    # Rotate, exactly as ``rpc_batch`` does for a non-list body.
                    last = RuntimeError(
                        f"{url}: answered {type(body).__name__}, not a JSON-RPC object"
                    )
                    break
                if body.get("error"):
                    err = body["error"]
                    if is_range_limitation(err):
                        raise RangeTooWide(str(err))
                    if is_endpoint_limitation(err):
                        last = RuntimeError(f"{url}: {err}")
                        break
                    raise MalformedRequest(f"{url}: {err}")
                resp.raise_for_status()
                return body.get("result")
            except (RangeTooWide, MalformedRequest):
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if attempt < session.config.max_retries - 1:
                    await session.pace(
                        session.config.backoff_seconds[
                            min(attempt, len(session.config.backoff_seconds) - 1)
                        ]
                    )
    raise AllEndpointsFailed(f"{method}: {last}")


async def rpc_batch(
    session: _Session, urls: tuple[str, ...], calls: list[tuple[str, list]]
) -> list[Any]:
    """A JSON-RPC **array**, re-aligned by ``id`` rather than by position.

    Positional alignment is the trap: providers are allowed to answer a batch
    out of order, and one that does hands every fingerprint to the wrong
    transaction — a defect that looks exactly like a detector calibration
    problem.
    """
    payload = [jsonrpc(session.next_id(), m, p) for m, p in calls]
    by_id = {entry["id"]: i for i, entry in enumerate(payload)}
    httpx = require_httpx()
    last: BaseException | None = None
    for url in urls:
        for attempt in range(session.config.max_retries):
            try:
                resp = await session.post(url, payload)
                if resp.status_code in DEAD_STATUS_CODES:
                    last = RuntimeError(f"{url} -> HTTP {resp.status_code}")
                    await session.pace(
                        _dead_status_pause(session.config, resp.status_code, attempt)
                    )
                    break
                body = resp.json()
                if not isinstance(body, list):
                    last = RuntimeError(f"{url}: batch answered {type(body).__name__}")
                    break
                out: list[Any] = [None] * len(payload)
                endpoint_problem: Any = None
                for entry in body:
                    if not isinstance(entry, dict):
                        continue
                    slot = _slot_of(by_id, entry.get("id"))
                    if slot is None:
                        continue
                    err = entry.get("error")
                    if err:
                        # Same discipline as `rpc_call`, and it was missing
                        # here: drpc's "Can't route your request" arrives on
                        # every entry wearing -32602, and a batch path that
                        # only skipped errored entries returned an empty
                        # result set from a live endpoint that had refused the
                        # whole call.  Classify on the MESSAGE.
                        if is_endpoint_limitation(err):
                            endpoint_problem = err
                            break
                        raise MalformedRequest(f"{url}: {err}")
                    out[slot] = entry.get("result")
                if endpoint_problem is not None:
                    last = RuntimeError(f"{url}: {endpoint_problem}")
                    break  # rotate the WHOLE batch: this endpoint refused it
                return out
            except (MalformedRequest, AllEndpointsFailed):
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if attempt < session.config.max_retries - 1:
                    await session.pace(
                        session.config.backoff_seconds[
                            min(attempt, len(session.config.backoff_seconds) - 1)
                        ]
                    )
    raise AllEndpointsFailed(f"batch of {len(calls)}: {last}")


async def fetch_uint_view(
    contract: str,
    signature: str,
    *,
    config: SourceConfig = DEFAULT_CONFIG,
    client: Any = None,
    transport: Any = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> int | None:
    """One zero-argument ``uint256`` view, read **live**.

    This is how rulings R10 and R13 are honoured end to end: the CLI calls it
    for ``POINTS_PER_ETH()`` and ``minDeposit()`` and hands the answers to
    :class:`sybilkit.curator.CuratorPreset`, which has no default for either.
    ``None`` on failure — never a remembered value dressed up as a reading.
    """
    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        try:
            raw = await rpc_call(
                s,
                config.state_rpcs,
                "eth_call",
                [{"to": contract, "data": selector(signature)}, "latest"],
            )
        except (AllEndpointsFailed, MalformedRequest, RangeTooWide):
            return None
    if not isinstance(raw, str):
        return None
    return hex_to_int(raw)


__all__ = [
    "AllEndpointsFailed",
    "BANNED_HOSTS",
    "BANNED_HOST_SUFFIXES",
    "BLOCKSCOUT_BASE",
    "DEFAULT_CONFIG",
    "LOG_RPCS",
    "MalformedRequest",
    "MissingDependency",
    "RangeTooWide",
    "STATE_RPCS",
    "SourceConfig",
    "USER_AGENT",
    "addr_from_topic",
    "assert_keyless",
    "data_words",
    "event_topic",
    "fetch_uint_view",
    "hex_to_int",
    "is_endpoint_limitation",
    "is_range_limitation",
    "keccak256",
    "keccak256_hex",
    "open_client",
    "require_httpx",
    "selector",
]
