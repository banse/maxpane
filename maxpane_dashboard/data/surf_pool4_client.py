"""pool4 — the chain client.  Four endpoint pools, keyless, read-only.

This is WP6 of ``docs/surf_pool4_implementation_plan.md``.  It is the only
module on the pool4 path that touches a socket.  Everything it decodes is
:mod:`maxpane_dashboard.data.surf_pool4`'s (WP3); nothing here re-implements a
selector, a topic, a gate or a formula.

Deliberately **not** an extension of ``surf_client.py``
------------------------------------------------------

``surf_client`` is a 3,200-line shared file with its own owner and its own
mainnet endpoint pools.  Co-owning it across this build is how a merge conflict
becomes a silent endpoint change, so the mainnet URLs and the error-message
tables below are **re-declared here rather than imported**, on the repo's
redundancy-plus-an-agreement-test pattern (``_GAME_CYCLE``, the ``--game``
choices, ``NETWORK_WORDS``).  ``test_the_mainnet_pools_agree_with_surf_client``
and ``test_the_error_pattern_tables_agree_with_surf_client`` are the tripwires;
deriving either from ``surf_client`` would make them compare a constant against
itself and they could never fail again.

Four pools, and the Sepolia halves are MEASURED
-----------------------------------------------

The plan's §3 said "publicnode is BANNED from ``SEPOLIA_LOG_RPCS``", reasoning
by analogy from mainnet.  That is wrong, and amendment A11 closed R8 by
measuring it.  Re-measured by this package on 2026-09-01 against the launch-3
hook, one 400-block archive window and the 30-call getter round this client
actually issues:

===========================================  =======  ==========  =============
host                                         30-call  archive     verdict
                                             batch    getLogs
===========================================  =======  ==========  =============
``ethereum-sepolia-rpc.publicnode.com``      200 ×2   200, 90     BOTH pools
                                                      logs
``gateway.tenderly.co/public/sepolia``       **429**  200, 90     LOGS only
                                             -32005   logs
``1rpc.io/sepolia``                          200 then **-32602**  STATE fallback
                                             429      "limited to  only
                                             -32029   0 - 50
                                                      blocks"
``sepolia.drpc.org``                         400      400         BANNED
                                             code 35  code 35
``rpc.sepolia.org``                          404      404         BANNED
``endpoints.omniatech.io/v1/eth/sepolia``    521      521         BANNED
===========================================  =======  ==========  =============

Three things in that table are load-bearing and are the reason it is written
here rather than left in a commit message:

* **Sepolia publicnode serves archive ``eth_getLogs``, unlike its mainnet
  sibling.**  It is the primary of *both* Sepolia pools.  The mainnet split is
  a fact about mainnet publicnode, not a property of the vendor.
* **Tenderly Sepolia's 429 only appears at the size we actually send.**  A
  3-call probe passes; the 30-call hook round is rejected with
  ``-32005 rate limit exceeded``, cold, on the first attempt.  A11 recorded the
  429 and this package reproduced it — measuring with a toy batch would have
  put a host in the state pool that cannot serve one real round.
* **``sepolia.drpc.org`` is not "400s on ``eth_blockNumber``"** — it answers
  *every* method with ``code 35 "chain is not available on free plan, please
  upgrade to paid plan"``.  It is a keyed endpoint wearing a keyless URL, which
  is a ban, not a fallback.  (Its mainnet sibling ``eth.drpc.org`` is a
  different hostname and stays in ``MAINNET_LOG_RPCS``, where it works.)

``1rpc.io/sepolia`` is a **state fallback only**: it serves one 30-call batch
and 429s on the next one in a burst, asking for an OnFinality key.  A fallback
is only reached when the primary is already failing, so it is never part of a
burst behind a healthy primary — but it must never be a primary, and its
50-block ``eth_getLogs`` cap keeps it out of the log pool entirely.

Failure semantics (CLAUDE.md, non-negotiable)
---------------------------------------------

**A failed read is ``None``, never ``0``.**  Every public ``fetch_*`` returns
its WP0 dataclass with per-field ``None`` for individually failed reads, and
``None`` overall only when the whole round failed.  No public method raises
into the refresh loop.

**An ``eth_call`` that did not error is not a getter that answered** (A10).  A
call to an address with no code returns ``"0x"`` with no error, so every
decoded field goes through WP3's :func:`~surf_pool4.answered` — including the
two places this module decodes a word itself, where ``evm_abi.decode_uint``
would otherwise return ``0`` for an empty payload and write a sentinel.

**Errors are classified on message text, not code.**  ``-32602`` means
"``eth_getLogs`` is limited to 0 - 50 blocks" on one provider and "Invalid
params" on another (``rpc_error_states.json``), and ``-32005`` is Tenderly's
rate limit here and something else elsewhere.  A provider's *suggested* retry
range is **never** followed: one decrements a single block per round trip and
livelocks anything that obeys it.  This client halves its own window, bounded.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data import surf_v4
from maxpane_dashboard.data.evm_abi import decode_uint, strip0x
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)
from maxpane_dashboard.data.surf_models import (
    POOL4_DISCOVERY_STATES,
    POOL4_NETWORKS,
    Pool4Discovery,
    Pool4DripperState,
    Pool4FlowEvent,
    Pool4HookState,
    Pool4VaultState,
    PoolV4State,
)

logger = logging.getLogger(__name__)

#: The closed vocabularies are unpacked from the contract, never retyped (A5).
NETWORK_SEPOLIA, NETWORK_MAINNET = POOL4_NETWORKS
_STATE_ADOPTED = POOL4_DISCOVERY_STATES[1]


# ---------------------------------------------------------------------------
# Endpoints — FOUR pools, not two
# ---------------------------------------------------------------------------

#: Sepolia state pool.  publicnode primary: it served the 30-call getter round
#: twice back to back.  1rpc is a fallback only — one round, then 429.
SEPOLIA_STATE_RPCS = [
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://1rpc.io/sepolia",
]

#: Sepolia logs pool.  **publicnode is present on purpose** — it serves archive
#: ``eth_getLogs`` on Sepolia, unlike its mainnet sibling (A11, re-measured).
#: 1rpc is deliberately absent: it caps ``eth_getLogs`` at 50 blocks.
SEPOLIA_LOG_RPCS = [
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://gateway.tenderly.co/public/sepolia",
]

#: Mainnet state pool — the values of ``surf_client.STATE_RPC_PRIMARY`` and
#: ``surf_client.STATE_RPC_FALLBACKS``, transcribed, not imported.
MAINNET_STATE_RPCS = [
    "https://ethereum-rpc.publicnode.com",
    "https://gateway.tenderly.co/public/mainnet",
    "https://rpc.mevblocker.io",
]

#: Mainnet logs pool — the values of ``surf_client.LOG_RPCS``, transcribed.
#: publicnode is absent here and present in ``SEPOLIA_LOG_RPCS``, and that
#: asymmetry is the measurement, not an oversight.
MAINNET_LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",
]

#: ``surf_client._BANNED_RPC_HOSTS`` transcribed, plus the three Sepolia hosts
#: this package measured dead.  Each carries its symptom: a ban with no symptom
#: beside it is a ban nobody can ever re-test.
_BANNED_RPC_HOSTS = frozenset(
    {
        # --- transcribed from surf_client._BANNED_RPC_HOSTS ---
        "eth.llamarpc.com",         # HTTP 521, origin down
        "rpc.ankr.com",             # now requires an API key
        "eth-mainnet.g.alchemy.com",
        "mainnet.infura.io",
        "api.opensea.io",
        "api.reservoir.tools",      # sunset, DNS gone
        "cloudflare-eth.com",       # -32603 / -32046 on every call
        # --- measured by WP6 on Sepolia, 2026-09-01 ---
        "sepolia.drpc.org",         # every method: 400, code 35, "free plan"
        "rpc.sepolia.org",          # HTTP 404 (Apache), no JSON-RPC at all
        "endpoints.omniatech.io",   # HTTP 521, origin down
    }
)


#: The two mainnet-only hook getters, named here **only** so this module can
#: assert that WP3's table carries them.  The selectors themselves are WP3's —
#: ``surf_pool4.HOOK_SELECTORS`` grew ``capDecayTokensPerDay`` and
#: ``inventoryCap`` on 2026-09-02 and derives both from their signature strings
#: — so the hook round picks them up for free and there is no second copy of a
#: selector table here.
#:
#: This module briefly *did* carry a second copy, and a mutation is what caught
#: it: dropping the local block changed nothing, because the round was already
#: getting both from ``HOOK_SELECTORS``.  Two tables for one set of selectors is
#: the divergence CLAUDE.md's "reuse before you build" exists to prevent, so the
#: copy went and ``test_wp3s_hook_table_carries_the_two_mainnet_getters`` is the
#: agreement test that replaces it.
#:
#: **Both answer on Sepolia too, measured** — the "mainnet-only" premise is
#: false, and the degradation test is therefore built on a getter made to
#: revert rather than on pointing at Sepolia, which would have passed for the
#: wrong reason.  See the test for the numbers.
MAINNET_HOOK_GETTERS: tuple[str, ...] = ("capDecayTokensPerDay", "inventoryCap")

#: The Reward Distributor's recovered interface (mainnet only, 2,334 bytes).
#: Read-only members only: ``distribute()``, ``setDripper(address)`` and
#: ``emergencyWithdraw(address)`` are state-changing and this repo has no
#: signer, so they are deliberately absent rather than merely unused.
#:
#: **There is no ``bondingBps()`` and none is invented here.**  Bonding is the
#: remainder, ``10000 - stakingBps - nftBps``, and that derivation is named
#: downstream rather than hardcoded at its measured 4000.
DISTRIBUTOR_SIGNATURES: dict[str, str] = {
    "dripper": "dripper()",
    "asset": "asset()",
    "owner": "owner()",
    "stakingBps": "stakingBps()",
    "nftBps": "nftBps()",
    "stakingEarned": "stakingEarned()",
    "bondingEarned": "bondingEarned()",
    "nftEarned": "nftEarned()",
    "heldBonding": "heldBonding()",
    "heldNft": "heldNft()",
}

#: ``vault()`` and ``dripper()``, the two questions the walk asks at each hop.
SEL_VAULT = "vault()"
SEL_DRIPPER = "dripper()"

#: How far the vault walk may follow ``dripper()`` before giving up.
#:
#: Measured need is **one** hop on Sepolia (recipient IS the dripper) and
#: **two** on mainnet (recipient is the Distributor, which names the dripper).
#: Four leaves headroom for one more link being inserted without a release,
#: which is precisely what happened between Sepolia and mainnet — and stops
#: well short of letting an unbounded chain run. Each hop is one batched round
#: trip, so the whole walk costs at most four and normally one or two.
_MAX_VAULT_HOPS = 4

#: How many flag-passing candidates may be adjudicated in one sweep.
#:
#: The flag gate is arithmetic, so in practice this is 0 or 1 — but both
#: candidate sources are attacker-writable, and a ``0x2840``-shaped address
#: mines in ~20,000 tries, so 500 of them is seconds of work. Without a cap a
#: single edited page turns one refresh into 500 getter rounds: an RPC
#: amplifier built out of the very filter that was supposed to prevent one.
_MAX_CANDIDATE_ROUNDS = 8

#: The docs page, and it is NOT one of the four RPC pools — see
#: :meth:`Pool4Client.fetch_docs_page`.
DOCS_URL = "https://pool4.imd.fun/docs"
#: Only this host may be fetched as a docs source. The operator widened the
#: trust surface to one page; an allowlist is what keeps it one page.
_DOCS_HOSTS = frozenset({"pool4.imd.fun"})
#: Hard byte cap on the docs response. The page is a few tens of KB; this is
#: room to grow and a bound on a hostile or broken server.
_DOCS_MAX_BYTES = 2 * 1024 * 1024
_DOCS_TIMEOUT = 10.0

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
#: publicnode 429s under bursts; measured in fwa_client, transcribed here.
_INTER_CALL_DELAY = 0.12

#: Recent-window size for ``eth_getLogs`` (~8 h at 12 s blocks, on Sepolia as
#: on mainnet).  Halved — never "suggested-range"-followed — on a range error,
#: at most ``_LOG_MAX_SHRINKS`` times.  Transcribed from ``surf_client``.
LOG_WINDOW_BLOCKS = 2400
_LOG_MIN_WINDOW = 300
_LOG_MAX_SHRINKS = 3


# ---------------------------------------------------------------------------
# Error classification — message text first
# ---------------------------------------------------------------------------
#
# Transcribed from ``surf_client``, which transcribed it from ``ttt_client``.
# ``rpc_common``'s docstring explains at length why this policy is NOT shared:
# five clients implement five different error policies, each encoding a fact
# about a specific provider, and a shared one would be a five-way switch with
# every client's behaviour reachable from every other client's bug.

_ENDPOINT_LIMITATION_PATTERNS = (
    "limited to", "block range", "range is too large", "ranges over",
    "exceeds", "too large", "too many", "archive", "api key", "unauthorized",
    "authenticate", "free plan", "upgrade", "not supported", "unsupported",
    "capacity", "rate limit", "timeout", "try again", "cannot fulfill",
)

_RANGE_LIMITATION_PATTERNS = (
    "limited to", "block range", "range is too large", "ranges over",
)

_MALFORMED_REQUEST_CODES = {-32600, -32601, -32602, -32604, -32700}


def _looks_like_endpoint_limitation(err: Any) -> bool:
    """True if *err* reads as "this endpoint can't", not "this request is bad".

    The message is read **first** and the code only as a fallback, and both
    live probes in ``rpc_error_states.json`` are why: ``-32602`` carries
    "eth_getLogs is limited to 0 - 50 blocks range" on 1rpc and "Invalid
    params" on publicnode.  Code-first classification would treat the
    recoverable one as our own bug and stop rotating.
    """
    if not isinstance(err, dict):
        return True
    message = str(err.get("message") or "").lower()
    if any(frag in message for frag in _ENDPOINT_LIMITATION_PATTERNS):
        return True
    return err.get("code") not in _MALFORMED_REQUEST_CODES


def _is_range_limitation(err: Any) -> bool:
    """True only for "your block range is too wide" — the shrinkable class."""
    if not isinstance(err, dict):
        return False
    message = str(err.get("message") or "").lower()
    return any(frag in message for frag in _RANGE_LIMITATION_PATTERNS)


class Pool4LogRangeError(RuntimeError):
    """``eth_getLogs`` failed because the requested window is too wide.

    Carries no suggested range **on purpose**.  Providers volunteer one, and
    one of them decrements a single block per round trip; a client that
    plumbed the suggestion through would have somewhere to put it, and
    somewhere to put it is how it eventually gets used.  The caller halves its
    own window instead.
    """


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


class Pool4Client(OwnedHttpClient):
    """Async, keyless, read-only client for the pool4 contracts.

    Addresses are **parameters, never imports**: the Sepolia hook/vault/dripper
    are vendored by the caller and the mainnet hook is *discovered*, so a
    module-level constant here would be either a testnet address shipped to
    mainnet readers or a mainnet address nobody verified.  WP3 made the same
    call for the announce address and the expected token, for the same reason.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        sepolia_state_rpcs: Sequence[str] | None = None,
        sepolia_log_rpcs: Sequence[str] | None = None,
        mainnet_state_rpcs: Sequence[str] | None = None,
        mainnet_log_rpcs: Sequence[str] | None = None,
        inter_call_delay: float = _INTER_CALL_DELAY,
        backoff_seconds: tuple[float, ...] = _BACKOFF_SECONDS,
        log_window_blocks: int = LOG_WINDOW_BLOCKS,
    ) -> None:
        self._pools: dict[tuple[str, str], list[str]] = {
            (NETWORK_SEPOLIA, "state"): list(
                sepolia_state_rpcs or SEPOLIA_STATE_RPCS
            ),
            (NETWORK_SEPOLIA, "logs"): list(sepolia_log_rpcs or SEPOLIA_LOG_RPCS),
            (NETWORK_MAINNET, "state"): list(
                mainnet_state_rpcs or MAINNET_STATE_RPCS
            ),
            (NETWORK_MAINNET, "logs"): list(mainnet_log_rpcs or MAINNET_LOG_RPCS),
        }
        for urls in self._pools.values():
            for url in urls:
                host = (urlparse(url).hostname or "").lower()
                if host in _BANNED_RPC_HOSTS:
                    raise ValueError(
                        f"{url} is a banned RPC host (dead, keyed or capped) — "
                        "see surf_pool4_client._BANNED_RPC_HOSTS"
                    )
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._inter_call_delay = inter_call_delay
        self._backoff_seconds = backoff_seconds
        self._log_window_blocks = log_window_blocks
        self._request_id = 0
        self._last_rpc_at: float = 0.0

    # Lifecycle (close / __aenter__ / __aexit__) comes from OwnedHttpClient.

    # ------------------------------------------------------------------
    # Pools
    # ------------------------------------------------------------------

    def state_endpoints(self, network: str) -> list[str]:
        return list(self._pool(network, "state"))

    def log_endpoints(self, network: str) -> list[str]:
        return list(self._pool(network, "logs"))

    def _pool(self, network: Any, kind: str) -> list[str]:
        """The endpoint list for one (network, kind), or ``ValueError``.

        ``POOL4_NETWORKS`` is a closed vocabulary (A5), so a word outside it is
        a producer bug rather than a new chain.  It raises here and every
        public method turns that into ``None`` — a Sepolia read must never be
        able to fall back onto a mainnet URL by accident, which is exactly what
        a permissive default would allow.
        """
        try:
            return self._pools[(network, kind)]
        except (KeyError, TypeError):
            raise ValueError(
                f"unknown pool4 network {network!r} — expected one of "
                f"{POOL4_NETWORKS}"
            ) from None

    # ------------------------------------------------------------------
    # RPC plumbing
    # ------------------------------------------------------------------

    async def _post_rpc(self, url: str, payload: Any) -> httpx.Response:
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)
        return await self._client.post(url, json=payload)

    async def _rpc_state_batch(
        self, network: str, calls: Sequence[tuple[str, list]]
    ) -> list[Any] | None:
        """One JSON-RPC *batch array* POST on this network's state pool.

        Returns per-entry results aligned with *calls*; an entry that came back
        as an error is ``None`` (**never** ``0`` — a zeroed counter persists
        and outlives the outage that produced it).  Returns ``None`` only when
        every endpoint failed to serve the batch at all.
        """
        payloads = []
        for method, params in calls:
            self._request_id += 1
            payloads.append(jsonrpc_payload(self._request_id, method, params))
        id_to_idx = {p["id"]: i for i, p in enumerate(payloads)}
        last_err: BaseException | None = None
        for url in self._pool(network, "state"):
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payloads)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break  # rotate, do not retry a dead host
                    body: Any = None
                    try:
                        body = resp.json()
                    except ValueError:
                        pass
                    # Tenderly Sepolia answers an over-large batch with a
                    # single -32005 object and HTTP 429, so the JSON error body
                    # is classified BEFORE raise_for_status — drpc taught
                    # talismans_client the same lesson with an HTTP 400.
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break  # rotate
                        raise RuntimeError(f"malformed request: {err}")
                    resp.raise_for_status()
                    if not isinstance(body, list):
                        # An endpoint that answers a batch with a scalar is not
                        # speaking the protocol; rotate rather than guess.
                        last_err = RuntimeError(f"{url}: non-batch reply")
                        break
                    results: list[Any] = [None] * len(payloads)
                    for entry in body:
                        if not isinstance(entry, Mapping):
                            continue
                        idx = id_to_idx.get(entry.get("id"))
                        if idx is None:
                            continue
                        if entry.get("error"):
                            logger.warning(
                                "pool4 batch entry %s failed: %s",
                                calls[idx][0], entry["error"],
                            )
                            continue  # stays None — never 0
                        results[idx] = entry.get("result")
                    return results
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        logger.warning(
            "pool4 %s state batch failed on every endpoint: %s", network, last_err
        )
        return None

    async def _rpc_logs(self, network: str, method: str, params: list) -> Any:
        """One JSON-RPC call on this network's LOGS pool.

        Raises :class:`Pool4LogRangeError` when the message says the window is
        too wide; the caller halves its **own** window.  A provider's suggested
        range is never read, never stored and never followed.
        """
        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self._pool(network, "logs"):
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payload)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break
                    body: Any = None
                    try:
                        body = resp.json()
                    except ValueError:
                        pass
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _is_range_limitation(err):
                            raise Pool4LogRangeError(str(err.get("message") or err))
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break
                        raise RuntimeError(f"malformed request: {err}")
                    resp.raise_for_status()
                    return body.get("result") if isinstance(body, dict) else None
                except Pool4LogRangeError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all {network} log endpoints failed: {last_err}")

    # ------------------------------------------------------------------
    # One getter round
    # ------------------------------------------------------------------

    async def _getter_round(
        self,
        network: str,
        calls: Sequence[tuple[str, str, str]],
        block_tag: str = "latest",
        with_block_number: bool = True,
    ) -> tuple[dict[str, Any], int | None] | None:
        """``({name: raw_return_or_None}, block_number)`` for one batch.

        *calls* are ``(name, to, calldata)``.  ``eth_blockNumber`` rides the
        **same batch array** rather than a second round trip: a height fetched
        separately can describe a different block from the getters, which is
        ``surf_client.fetch_nonces``'s reasoning and this module's too.

        ``None`` only when the whole batch failed everywhere.  A single dead
        getter is one ``None`` inside an otherwise-healthy answer map.
        """
        entries: list[tuple[str, list]] = [
            ("eth_call", [{"to": to, "data": data}, block_tag])
            for (_name, to, data) in calls
        ]
        if with_block_number:
            entries.append(("eth_blockNumber", []))
        results = await self._rpc_state_batch(network, entries)
        if results is None:
            return None
        answers = {
            name: results[idx] for idx, (name, _to, _data) in enumerate(calls)
        }
        block_number = _hex_int(results[-1]) if with_block_number else None
        return answers, block_number

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_block_number(self, *, network: str) -> int | None:
        """The head block, or ``None``.  Never ``0`` — 0 would read as genesis."""
        try:
            results = await self._rpc_state_batch(
                network, [("eth_blockNumber", [])]
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_block_number: %s", exc)
            return None
        if not results:
            return None
        return _hex_int(results[0])

    async def fetch_transaction(
        self,
        tx_hash: str,
        *,
        network: str,
    ) -> dict | None:
        """One transaction by hash, as the node returned it, or ``None``.

        **This is the fetch that re-establishes provenance** (S15).  A27 made
        an announce-wallet self-post the only gate an attacker cannot satisfy,
        but provenance is re-derived each cycle from a 25-row channel window,
        and at the channel's measured 2.55 days/post that window turns over in
        roughly **64 days** — so a genuine mainnet adoption would lapse back to
        Sepolia two months after it was announced.  The cure is to remember the
        self-post's *transaction hash* and re-read that transaction.  **The
        cache says where to look; the chain stays the authority** — which is
        the precise difference between this and the persisted-adoption defence
        A27 retired, where the cache was believed rather than merely consulted.

        Returns the node's own transaction object, unmodified and undecoded.
        Raw for :meth:`fetch_flow_logs`'s reason: WP3 owns the provenance
        predicate and I do not know which fields it will read, so inventing a
        normalised shape here would be a guess at another package's contract.
        ``from``, ``to``, ``input``, ``hash`` and ``blockNumber`` are all
        present exactly as ``eth_getTransactionByHash`` spells them.

        **Two values that look like failures and are not**, both passed through
        deliberately:

        * ``to`` is ``null`` on a contract creation.  That is a real fact about
          a real transaction and it makes the transaction *not a self-post* —
          a provenance answer, which is WP3's to give, not mine.
        * ``blockNumber`` is ``null`` while a transaction is pending.  Passed
          through for the same reason, and **named in WP6's report** so the
          question of whether an unmined self-post establishes provenance
          lands on somebody rather than between us.  WP6's recommendation is
          that it must not.

        **Every other unreadable outcome is ``None``, and never a provenance
        verdict.**  A null result — an unknown hash — is a *failed read*, not
        "no such transaction": a node that is behind, pruned, or answering for
        the wrong chain returns exactly the same ``null`` as a hash that was
        never mined, and one endpoint cannot tell those apart.  Reporting it as
        a failed provenance check would make an RPC outage look like an attack
        and would drop an adoption that is still perfectly good.

        ``tx_hash`` is validated **before it can reach a URL or a JSON-RPC
        body**.  It is third-party input by exactly the argument that makes a
        hand-edited cache third-party input: it comes back out of
        ``~/.maxpane/``.
        """
        body = _tx_hash_body(tx_hash)
        if body is None:
            logger.warning(
                "fetch_transaction: %r is not a 32-byte transaction hash", tx_hash
            )
            return None
        wanted = "0x" + body

        try:
            results = await self._rpc_state_batch(
                network, [("eth_getTransactionByHash", [wanted])]
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_transaction: %s", exc)
            return None
        if not results:
            return None
        tx = results[0]
        if not isinstance(tx, dict) or not tx:
            # A27's sibling of A10: "the call did not fail" is not "the
            # transaction exists". ``null`` is the answer for an unknown hash
            # AND for a node that simply does not have it.
            logger.warning("fetch_transaction: %s returned no transaction", wanted)
            return None

        # --- the identity check, and it lives HERE on purpose --------------
        #
        # A client that returns the wrong transaction must not be believed, and
        # this is the only layer that can say so. Two reasons it is WP6's and
        # not WP3's, both structural rather than stylistic:
        #
        # 1. **Only this layer knows the question.** The pure predicate is
        #    handed an answer; it has no idea which hash was asked for unless
        #    the caller passes the expectation in alongside — at which point
        #    the caller is shipping its own question across the boundary so
        #    somebody else can compare it, which is longer and no safer.
        # 2. **Only this layer can return the right answer.** A hash mismatch
        #    is a fact about the *endpoint* — confused, stale, or hostile — and
        #    its correct outcome is ``None``, "we could not read". A pure
        #    provenance predicate returns a provenance verdict, so the loudest
        #    thing it could say is "not a self-post", which is the exact
        #    conflation of an outage with an attack this method exists to
        #    avoid. The check must live where ``None`` is expressible.
        returned = _tx_hash_body(tx.get("hash"))
        if returned is None:
            logger.warning("fetch_transaction: %s answered with no hash", wanted)
            return None
        if returned != body:
            logger.warning(
                "fetch_transaction: asked for %s, got 0x%s — refusing it",
                wanted, returned,
            )
            return None
        return tx

    async def verify_hook(
        self,
        addr: str,
        *,
        network: str,
        expected_token: str,
    ) -> Pool4Discovery | None:
        """Adjudicate one candidate hook against the chain.

        **The second gate, and a forgeable one.  It narrows; it does not
        authorise** (amendment A27).  The fingerprint is forgeable *by
        construction* and two packages measured it independently: a
        ``0x2840``-shaped address was mined in ~16,000 tries by the security
        pass and 20,141 by WP3, in under a second.  Four of the five getters
        are pure liveness checks any deployed contract passes, and ``token()``
        is a value the candidate's own contract chooses — so a contract that
        answers real mainnet IMD to ``token()`` and zero words to the rest is
        *adopted* by this method.

        **Provenance is the unforgeable gate and it lives upstream**, in
        :func:`~surf_pool4.candidate_addresses`, which reads announce-wallet
        self-posts only: a transaction signed by the announce wallet is the one
        thing an attacker cannot mint.  This method never sees a transaction
        and has no parameter for one, which is exactly why the persisted path —
        the one path that reached a fingerprint without passing provenance —
        was removed rather than hardened.  **Do not add an address source that
        skips it.**

        What the method does do is cheap and worth doing: its arithmetic half
        runs *before the network*.  ``has_pool4_flags`` is pure arithmetic on a
        string the caller already has, so a flag-failing candidate is rejected
        without a single ``eth_call`` and a self-post naming twenty decoys costs
        zero round trips rather than twenty.  A flag-passing candidate costs
        exactly one getter round, whose answers go to WP3's
        :func:`~surf_pool4.fingerprint_verdict` — which owns the verdict.
        Nothing here re-derives ``0x2840``, re-orders the gates or second-
        guesses a rejection.

        ``None`` is returned only when the round could not be read at all.
        "We could not look" is not a verdict: holding ``rejected`` from an
        outage would make a transient RPC failure look like a settled fact
        about the protocol, and the caller would drop an adoption it had
        already established.

        ``getHookPermissions`` is included in the answer map **only when it
        actually answered**, and that is a decision worth stating.  The v4
        permission field is the address's own low fourteen bits, and the
        PoolManager enforces *those*; ``getHookPermissions()`` is the
        contract's self-declaration and is corroboration, not the source of
        truth.  Requiring it would reject a mainnet hook built without that
        member — A8's own catastrophic direction, where pool4 is never
        discovered on any chain.  Requiring it to **agree** when it speaks
        costs nothing and catches a contract lying about itself, so a present
        but malformed or disagreeing answer is a rejection and an absent one
        falls through to the ``token()`` identity gate.
        """
        if not P.has_pool4_flags(addr):
            # Arithmetic on a string the caller already has. A self-post naming
            # twenty decoys must cost zero round trips, not twenty: a discovery
            # path that verifies first and filters second turns an
            # attacker-writable channel into an RPC amplifier.
            state, detail = P.fingerprint_verdict(addr, {}, expected_token)
            return Pool4Discovery(
                network=network, state=state, detail=detail,
                hook_addr=None, token_addr=None, source_tx_hash=None,
            )

        answers = await self._fingerprint_answers(addr, network=network)
        if answers is None:
            return None
        state, detail = P.fingerprint_verdict(addr, answers, expected_token)
        if state != _STATE_ADOPTED:
            return Pool4Discovery(
                network=network, state=state, detail=detail,
                hook_addr=None, token_addr=None, source_tx_hash=None,
            )
        return Pool4Discovery(
            network=network,
            state=state,
            detail=detail,
            hook_addr=P.checksum_address(addr),
            token_addr=P.checksum_address(expected_token),
            source_tx_hash=None,
        )

    #: The getters a fingerprint needs, in gate order. ONE list, because
    #: :meth:`verify_hook` and :meth:`fetch_candidate_answers` must fetch
    #: exactly the same evidence or the two paths can disagree about the same
    #: address — which is the divergence this whole branch has been removing.
    _FINGERPRINT_GETTERS = (
        "getHookPermissions", "token", "rewardShareBps",
        "BPS_DENOMINATOR", "burnSink", "poolManager",
    )

    async def _fingerprint_answers(
        self, addr: str, *, network: str
    ) -> dict[str, Any] | None:
        """One getter round for one candidate, shaped for ``fingerprint_verdict``."""
        try:
            round_ = await self._getter_round(
                network,
                [(name, addr, P.encode_getter(P.HOOK_SELECTORS[name]))
                 for name in self._FINGERPRINT_GETTERS],
                with_block_number=False,
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fingerprint round: %s", exc)
            return None
        if round_ is None:
            return None
        answers = round_[0]
        # An unanswered ``getHookPermissions`` is OMITTED, not passed as None.
        # ``fingerprint_verdict`` treats the key's presence as "the contract
        # spoke", so passing an unanswered one would reject every hook built
        # without that member — A8's catastrophic direction. Present-but-
        # disagreeing is still a rejection; absent falls through to ``token()``.
        # This lives here so both public callers get the identical rule.
        if not P.answered(answers.get("getHookPermissions")):
            answers.pop("getHookPermissions", None)
        return answers

    async def fetch_candidate_answers(
        self,
        addrs: Sequence[str] | None,
        *,
        network: str,
    ) -> dict[str, dict[str, Any]] | None:
        """``{address: {getter: raw}}`` for the candidates worth asking about.

        **Evidence, never a verdict.**  This is the ``answers_by_addr`` input
        WP3's :func:`~surf_pool4.ranked_discovery` and
        :func:`~surf_pool4.fingerprint_verdict` declare, and it exists so that
        adjudication happens **once**, in the layer that owns it.  A consumer
        that could not get these bytes had to re-derive ranking for itself, and
        two copies of a ranking rule is exactly the divergence this branch has
        spent its time removing.

        Nothing in this map is an adoption.  Four of the five getters are pure
        liveness checks any deployed contract passes, and ``token()`` is a value
        the candidate's own contract chooses — so a map entry means "this
        address answered", which is not evidence of anything on its own (A27).
        The verdict comes from ``fingerprint_verdict``, and the *authority*
        behind it comes from provenance, upstream.

        **Why this does not weaken ``verify_hook``'s pinned property.**  That
        property is that ``verify_hook`` cannot tell where an address came from,
        which is why provenance has to gate *which addresses are asked at all*.
        This method is equally origin-blind: it takes bare address strings, adds
        no provenance source, and lets nothing skip a gate that could not
        already be skipped by calling the batch primitive directly.  Withholding
        fetched bytes was never the control.  ``verify_hook``'s signature is
        untouched and its tripwire still stands.

        Two bounds, both inherited rather than invented:

        * **The flag gate runs first, before the network.**  A candidate whose
          low fourteen bits are not :data:`~surf_pool4.POOL4_REQUIRED_FLAGS`
          gets no round trip and **no entry in the map**, so this map cannot be
          used to adjudicate an address that failed the arithmetic gate.
        * :data:`_MAX_CANDIDATE_ROUNDS` caps the sweep.  Both candidate sources
          are attacker-writable and a correctly-flagged address mines in
          seconds, so an uncapped sweep is an RPC amplifier.

        ``None`` when nothing could be read at all; ``{}`` when there was
        nothing worth asking.  Different answers, as everywhere else here.
        """
        flagged = [a for a in (addrs or ()) if P.has_pool4_flags(a)]
        if not flagged:
            return {}
        if len(flagged) > _MAX_CANDIDATE_ROUNDS:
            logger.warning(
                "fetch_candidate_answers: %s flag-passing candidates, "
                "adjudicating the first %s",
                len(flagged), _MAX_CANDIDATE_ROUNDS,
            )
            flagged = flagged[:_MAX_CANDIDATE_ROUNDS]

        out: dict[str, dict[str, Any]] = {}
        for addr in flagged:
            answers = await self._fingerprint_answers(addr, network=network)
            if answers is None:
                continue
            key = P.checksum_address(addr) or addr
            out[key] = answers
        if not out:
            return None
        return out

    async def fetch_hook_state(
        self,
        hook_addr: str,
        *,
        network: str,
        token_addr: str | None = None,
    ) -> Pool4HookState | None:
        """One batched round over the hook's recovered getter set.

        The hook is **unverified source**, so a getter that answers on Sepolia
        may revert on mainnet.  That is an ordinary outcome: the round is never
        dropped, the reverted getter is one ``None``, and the panel above it
        renders every field that did answer (plan R1 control (a)).

        ``totalSupply()`` is read off ``token_addr``'s own contract in the same
        batch — it is not a hook getter and must not look like one.  Omitting
        ``token_addr`` leaves ``total_supply_wei`` ``None`` and costs nothing
        else.

        There is deliberately **no** ``vault()`` call: the hook has no vault
        getter (A3), and the path is ``rewardsRecipient()`` -> RewardDripper ->
        ``dripper.vault()``.  Looking for one here would be the first step
        towards filling the field by scraping the announce channel, which is
        the one way this address must never be obtained.
        """
        calls = [
            (name, hook_addr, P.encode_getter(sel))
            for name, sel in P.HOOK_SELECTORS.items()
        ]
        # ``capDecayTokensPerDay`` and ``inventoryCap`` need no special case:
        # they are members of ``HOOK_SELECTORS`` and ride the same batch as
        # everything else. A hook that does not implement them reverts those
        # two entries and every other field in the round still reads — the same
        # per-field degradation the unverified-source getters already get
        # (plan R1 control (a)).
        supply_key = "__token_total_supply"
        if token_addr:
            calls.append(
                (supply_key, token_addr,
                 P.encode_getter(P.ERC20_SELECTORS["totalSupply"]))
            )
        try:
            round_ = await self._getter_round(network, calls)
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_hook_state: %s", exc)
            return None
        if round_ is None:
            return None
        answers, block_number = round_
        supply_raw = answers.pop(supply_key, None)
        return P.decode_hook_state(
            answers,
            total_supply_wei=_uint_or_none(supply_raw),
            block_number=block_number,
        )

    async def resolve_vault_path(
        self,
        rewards_recipient: str,
        *,
        network: str,
    ) -> dict | None:
        """Walk from ``rewardsRecipient()`` to the vault.  **Hop count DISCOVERED.**

        A3 said the path was two hops and forbade looking for ``vault()`` on
        the hook.  The prohibition still stands — the vault must be reached by
        *following the chain*, never scraped — but on 2026-09-02 the chain grew
        a link::

            Sepolia   hook.rewardsRecipient() -> Dripper     -> dripper.vault()
            Mainnet   hook.rewardsRecipient() -> Distributor -> distributor.dripper()
                                                             -> Dripper -> dripper.vault()

        Both shapes are live **simultaneously**: the Distributor exists on
        mainnet and has no Sepolia counterpart, so neither is "the" path and a
        hardcoded three would break Sepolia exactly as the hardcoded two broke
        mainnet.  So nothing here counts hops.  At each node it asks the node
        what it is — ``vault()`` and ``dripper()``, both in one batch — and
        follows whatever the chain answers.

        **How the walk terminates.**  Three independent bounds, because each
        stops a different runaway:

        1. :data:`_MAX_VAULT_HOPS` — a hard cap.  Measured need is one hop on
           Sepolia and two on mainnet; four leaves room for one more link being
           inserted without a release, which is exactly what just happened.
        2. **A visited set.**  A contract whose ``dripper()`` returns itself, or
           an A→B→A pair, stops immediately instead of burning the whole hop
           budget on every refresh.  Not redundant with the cap: the cap bounds
           the damage, the cycle check makes a loop cost one extra call rather
           than four.
        3. **The zero address is not a hop.**  ``dripper()`` answering
           ``0x000…0`` means "not set", and following it would ``eth_call`` an
           address with no code — which returns ``"0x"`` and tells us nothing
           (A10).  A wasted round trip and a misleading one.

        Returns ``{"path": [...], "dripper": addr|None, "vault": addr|None}``
        — a plain dict, because WP0 owns the models and inventing a shape for
        another package's contract is a guess.  ``path`` is every address
        actually visited, in order, so a caller can *say* how the vault was
        reached rather than assert it.

        ``None`` only when the very first hop could not be read.  A walk that
        ran and found no vault returns its dict with ``vault: None`` — "we
        looked and the chain does not lead there" is a different answer from
        "we could not look", and this is one of the few places in this module
        where both are expressible.
        """
        start = P.checksum_address(rewards_recipient)
        if start is None:
            logger.warning(
                "resolve_vault_path: %r is not an address", rewards_recipient
            )
            return None

        path: list[str] = []
        seen: set[str] = set()
        node: str | None = start
        dripper: str | None = None
        vault: str | None = None
        read_anything = False

        for _hop in range(_MAX_VAULT_HOPS):
            if node is None or node.lower() in seen:
                break
            seen.add(node.lower())
            path.append(node)
            try:
                round_ = await self._getter_round(
                    network,
                    [(SEL_VAULT, node, P.encode_getter(P.selector(SEL_VAULT))),
                     (SEL_DRIPPER, node, P.encode_getter(P.selector(SEL_DRIPPER)))],
                    with_block_number=False,
                )
            except (RuntimeError, ValueError) as exc:
                logger.warning("resolve_vault_path: %s", exc)
                break
            if round_ is None:
                break
            read_anything = True
            answers = round_[0]

            found = _addr_or_none(answers.get(SEL_VAULT))
            if found is not None:
                vault = found
                # The node that named the vault IS the dripper: ``vault()``
                # lives on the RewardDripper and nowhere else (A3).
                dripper = node
                break
            node = _addr_or_none(answers.get(SEL_DRIPPER))

        if not read_anything:
            return None
        return {"path": path, "dripper": dripper, "vault": vault}

    async def fetch_distributor_state(
        self,
        distributor_addr: str,
        *,
        network: str,
    ) -> dict | None:
        """The Reward Distributor's recovered getters.  Mainnet only, today.

        A plain dict of decoded values keyed by getter name, ``None`` per field
        that did not answer, because WP0 owns the models and this contract has
        none yet.  Same per-field degradation as every other round here.

        **``bondingBps`` is absent and is not invented.**  The contract has no
        such getter: bonding is the remainder, ``10000 - stakingBps - nftBps``,
        measured at 4000.  Deriving it is a decision about the payload and
        belongs downstream; returning it from here would make a computed number
        indistinguishable from a read one, which is the whole habit this repo's
        "read values live" rule exists to break.

        ``distribute()``, ``setDripper()`` and ``emergencyWithdraw()`` are in
        the recovered interface and are **deliberately not here**: they change
        state, and this repo has no signer and never will.
        """
        calls = [
            (name, distributor_addr, P.encode_getter(P.selector(sig)))
            for name, sig in DISTRIBUTOR_SIGNATURES.items()
        ]
        try:
            round_ = await self._getter_round(network, calls)
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_distributor_state: %s", exc)
            return None
        if round_ is None:
            return None
        answers, block_number = round_
        out: dict[str, Any] = {"block_number": block_number}
        for name in DISTRIBUTOR_SIGNATURES:
            raw = answers.get(name)
            if name in ("dripper", "asset", "owner"):
                out[name] = _addr_or_none(raw)
            else:
                out[name] = _uint_or_none(raw)
        return out

    async def fetch_vault_state(
        self,
        vault_addr: str,
        *,
        network: str,
    ) -> Pool4VaultState | None:
        """``StakedIMD``'s getters -> the model, in **two** rounds.

        ``decimals()`` is read first, in its own round, and the share-price
        argument is built from it: ``convertToAssets(10 ** decimals)``, keyed
        ``convertToAssets`` because that is the key WP3's
        ``SHARE_PRICE_CALL`` reads (A22).

        This is not ceremony.  The vault is a Solady ``ERC4626`` whose
        ``_decimalsOffset()`` is 6, so ``decimals()`` is **24** on Sepolia and
        one whole share is ``1e24`` units.  Asking ``convertToAssets(1e18)``
        asks the price of a *millionth* of a share and gets a real number back
        that renders as ``0.0000013 IMD/share`` — a dead-looking vault, with no
        error anywhere.  Both wrong forms are plausible on screen, which is why
        the argument is computed from a live read and **24 is never hardcoded**:
        the mainnet vault does not exist and nothing binds its offset to
        Sepolia's, so a constant would reproduce the 10⁶ defect at the
        switchover, silently.

        When ``decimals()`` does not answer, ``convertToAssets`` is **not
        asked at all** and ``share_price_wei`` is ``None``.  Asking it with a
        guessed argument would launder a wrong-argument answer into a
        right-looking field; a dark row is recoverable and a plausible wrong
        number is not.  Every other vault field still reads.

        The second round is pinned to the first round's block, so ``decimals``
        and the share price describe one state rather than two adjacent ones.
        """
        try:
            first = await self._getter_round(
                network,
                [("decimals", vault_addr,
                  P.encode_getter(P.VAULT_SELECTORS["decimals"]))],
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_vault_state: %s", exc)
            return None
        if first is None:
            return None
        decimals_raw, block_number = first[0].get("decimals"), first[1]
        decimals = _uint_or_none(decimals_raw)
        whole_share = P.whole_share_units(decimals)

        block_tag = "latest" if block_number is None else hex(block_number)
        calls = [
            (name, vault_addr, P.encode_getter(sel))
            for name, sel in P.VAULT_SELECTORS.items()
            if name != P.SHARE_PRICE_CALL
        ]
        if whole_share is not None:
            calls.append(
                (P.SHARE_PRICE_CALL, vault_addr,
                 P.encode_convert_to_assets(whole_share))
            )
        try:
            second = await self._getter_round(
                network, calls, block_tag=block_tag, with_block_number=False
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_vault_state: %s", exc)
            second = None
        if second is None:
            # The decimals round landed and the rest did not: still a model,
            # with the one field we read and the rest ``None``. All-or-nothing
            # here would throw away a good read.
            return P.decode_vault_state(
                {"decimals": decimals_raw}, block_number=block_number
            )
        answers = dict(second[0])
        answers["decimals"] = decimals_raw
        return P.decode_vault_state(answers, block_number=block_number)

    async def fetch_dripper_state(
        self,
        dripper_addr: str,
        *,
        network: str,
        token_addr: str | None = None,
    ) -> Pool4DripperState | None:
        """``RewardDripper``'s getters -> the model.

        The **backlog** is ``balanceOf(dripper)`` on the token, not a dripper
        getter, so it rides the same batch against a different contract and is
        passed to WP3's decoder as a parameter.  Omitting ``token_addr`` leaves
        ``balance_wei`` ``None``; it never becomes ``0``, which would render as
        "the backlog is empty" — a very different claim from "we did not read
        it".
        """
        calls = [
            (name, dripper_addr, P.encode_getter(sel))
            for name, sel in P.DRIPPER_SELECTORS.items()
        ]
        balance_key = "__token_balance_of_dripper"
        if token_addr:
            calls.append(
                (balance_key, token_addr, P.encode_balance_of(dripper_addr))
            )
        try:
            round_ = await self._getter_round(network, calls)
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_dripper_state: %s", exc)
            return None
        if round_ is None:
            return None
        answers, block_number = round_
        balance_raw = answers.pop(balance_key, None)
        return P.decode_dripper_state(
            answers,
            balance_wei=_uint_or_none(balance_raw),
            block_number=block_number,
        )

    async def fetch_pool_slot0(
        self,
        pool_id: str,
        *,
        network: str,
        pool_manager: str,
    ) -> PoolV4State | None:
        """The v4 pool's ``slot0`` and ``liquidity`` via ``extsload``.

        v4 has no ``slot0()``; state is raw storage under ``PoolManager._pools``
        and the slot derivation is ``surf_v4.pool_state_slots``, reached through
        WP3's :func:`~surf_pool4.pool_state_calls`.  Neither the keccak nor the
        derivation is re-implemented here.

        ``pool_id_source`` is always ``"hook"``: pool4's pool id comes from
        ``hook.poolId()`` and there is no vendored fallback to confuse it with,
        unlike the launchpad's 38 decoy pools.
        """
        try:
            slot0_data, liquidity_data = P.pool_state_calls(pool_id)
        except (ValueError, TypeError) as exc:
            logger.warning("fetch_pool_slot0: %s", exc)
            return None
        try:
            round_ = await self._getter_round(
                network,
                [("slot0", pool_manager, slot0_data),
                 ("liquidity", pool_manager, liquidity_data)],
                with_block_number=False,
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning("fetch_pool_slot0: %s", exc)
            return None
        if round_ is None:
            return None
        answers, _block = round_
        sqrt_price = tick = lp_fee = None
        slot0_raw = answers.get("slot0")
        if P.answered(slot0_raw):
            sqrt_price, tick, lp_fee = surf_v4.decode_slot0(slot0_raw)
        liquidity_raw = answers.get("liquidity")
        liquidity = (
            surf_v4.decode_liquidity(liquidity_raw)
            if P.answered(liquidity_raw) else None
        )
        return PoolV4State(
            pool_id=pool_id,
            sqrt_price_x96=sqrt_price,
            tick=tick,
            lp_fee=lp_fee,
            liquidity=liquidity,
            pool_id_source="hook",
        )

    async def fetch_docs_page(self, url: str = DOCS_URL) -> str | None:
        """The docs page, RAW.  A **candidate** source and nothing more.

        **Why this is beside the four pools and not in them.**  The pools are
        JSON-RPC endpoint rotations keyed by ``(network, kind)``: they carry
        batch semantics, JSON-RPC error classification, and a banned-host list
        that is entirely about RPC providers.  None of that applies to an HTML
        ``GET``.  Two more reasons that matter more than the plumbing:

        * **It is not chain-scoped.**  One page describes the deployment
          whatever network the view is showing.  Filing it under a network
          would imply a Sepolia docs page exists, and none does.
        * **It does not have the pools' standing.**  An RPC answers with
          consensus data; this is one operator's mutable HTML.  Shelving them
          together reads as equal authority, and the entire mitigation for
          this source is that its weakness stays *visible*.

        **This supplies candidates only.**  The full chain fingerprint still
        runs afterwards and nothing about A27 relaxes: the announce channel
        remains the stronger path and overrides this one when a self-post
        lands.  The cost is stated plainly and not relitigated — anyone who can
        edit that page can nominate a hook, and the fingerprint will not stop
        them, because a ``0x2840`` address mines in ~20,000 tries and
        ``token()`` is the candidate's own choice.  The mitigation is
        disclosure: the panel names which source an adoption came from.

        **The text comes back raw (S16).**  No stripping, no case folding, no
        HTML unescaping, no Unicode normalisation.  ``ADDRESS_RE`` must see the
        bytes the server sent, because every normalisation upstream of
        extraction re-arms the bidi case: ``0x`` + U+202E + 40 hex digits
        renders as one thing and *is* another, and the regex's leading-anchor
        guard is what refuses it.  Normalising here would quietly disarm a
        control that lives two modules away.  Bytes are decoded UTF-8 with
        ``errors="replace"`` rather than by the server's declared charset — an
        attacker-chosen charset is not a fact — and replacement can only
        destroy a would-be address, never mint one, since U+FFFD is not a hex
        digit and the regex requires a literal ``0x``.

        Third-party attacker-mutable input, so it is bounded three ways: the
        host must be on :data:`_DOCS_HOSTS`, redirects are **not followed at
        all**, and the body is capped at :data:`_DOCS_MAX_BYTES`.

        ``None`` is "we could not read", never "no candidate".
        """
        host = (urlparse(url).hostname or "").lower()
        if host not in _DOCS_HOSTS:
            logger.warning(
                "fetch_docs_page: %s is not an allowed docs host %s",
                url, sorted(_DOCS_HOSTS),
            )
            return None

        for attempt in range(_MAX_RETRIES):
            try:
                self._last_rpc_at = await pace(
                    self._last_rpc_at, self._inter_call_delay
                )
                resp = await self._client.get(
                    url,
                    # Not followed at ALL, rather than "not followed to another
                    # host". A same-host redirect would be defensible, but the
                    # page is served directly today, so refusing is one fewer
                    # moving part on a source whose whole justification is that
                    # its trust surface stays small and visible.
                    follow_redirects=False,
                    timeout=httpx.Timeout(_DOCS_TIMEOUT),
                    headers={"Accept": "text/html"},
                )
                if resp.status_code in ENDPOINT_DEAD_CODES:
                    logger.warning("fetch_docs_page: %s -> %s", url, resp.status_code)
                    return None
                if resp.is_redirect:
                    logger.warning(
                        "fetch_docs_page: %s redirected to %r — not followed",
                        url, resp.headers.get("location"),
                    )
                    return None
                resp.raise_for_status()

                declared = resp.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > _DOCS_MAX_BYTES:
                            logger.warning(
                                "fetch_docs_page: declares %s bytes, cap is %s",
                                declared, _DOCS_MAX_BYTES,
                            )
                            return None
                    except ValueError:
                        pass  # a malformed header decides nothing
                raw = resp.content
                # The header is advisory — a server that lies about its length
                # is exactly the server this cap exists for. The byte count is
                # the real gate.
                if len(raw) > _DOCS_MAX_BYTES:
                    logger.warning(
                        "fetch_docs_page: %s bytes exceeds the %s cap",
                        len(raw), _DOCS_MAX_BYTES,
                    )
                    return None
                if not raw:
                    logger.warning("fetch_docs_page: %s served an empty body", url)
                    return None
                return raw.decode("utf-8", errors="replace")
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(self._backoff_seconds[attempt])
                else:
                    logger.warning("fetch_docs_page: %s failed: %s", url, exc)
        return None

    async def fetch_flow_logs(
        self,
        hook_addr: str,
        from_block: int,
        to_block: int,
        *,
        network: str,
    ) -> list[dict] | None:
        """The hook's raw logs over ``[from_block, to_block]``, or ``None``.

        Raw logs rather than decoded rows, because **two** WP3 decoders read
        this same window — :func:`~surf_pool4.decode_flow_events` and
        :func:`~surf_pool4.reserve_series` — and a client that decoded and
        discarded would force a second sweep of the chain for bytes it already
        had.  :meth:`fetch_flow_events` is the decoded convenience over this.

        ``[]`` means swept and genuinely quiet; ``None`` means the read failed.
        A **partial** sweep is reported as ``None`` too, and that is deliberate:
        the counter reconciliation downstream sums these logs, so a window
        missing its middle produces a burn total that is simply wrong rather
        than merely absent.  Per-field degradation is right for getters, where
        each field stands alone; it is wrong for a sum.

        A "your range is too wide" error halves this client's own window and
        pages, at most ``_LOG_MAX_SHRINKS`` times.  The provider's suggested
        range is never read: one of them decrements a single block per round
        trip, so a client that follows it verbatim livelocks.
        """
        if to_block < from_block:
            return []
        window = min(to_block - from_block + 1, self._log_window_blocks)
        window = max(window, 1)
        for _shrink in range(_LOG_MAX_SHRINKS + 1):
            try:
                return await self._sweep(
                    network, hook_addr, from_block, to_block, window
                )
            except Pool4LogRangeError as exc:
                narrower = max(_LOG_MIN_WINDOW, window // 2)
                if narrower >= window:
                    logger.warning(
                        "fetch_flow_logs: window %s is already minimal: %s",
                        window, exc,
                    )
                    return None
                logger.info(
                    "fetch_flow_logs: halving window %s -> %s (%s)",
                    window, narrower, exc,
                )
                window = narrower
            except RuntimeError as exc:
                logger.warning("fetch_flow_logs: %s", exc)
                return None
            except ValueError as exc:  # unknown network
                logger.warning("fetch_flow_logs: %s", exc)
                return None
        logger.warning("fetch_flow_logs: gave up after %s shrinks", _LOG_MAX_SHRINKS)
        return None

    async def _sweep(
        self,
        network: str,
        hook_addr: str,
        from_block: int,
        to_block: int,
        window: int,
    ) -> list[dict]:
        """Page ``[from_block, to_block]`` in *window*-sized chunks.

        Raises :class:`Pool4LogRangeError` straight up so the caller can halve
        and start over; a half-collected page set is thrown away rather than
        returned, for the reason :meth:`fetch_flow_logs` gives.
        """
        out: list[dict] = []
        start = from_block
        while start <= to_block:
            end = min(start + window - 1, to_block)
            result = await self._rpc_logs(
                network,
                "eth_getLogs",
                [{
                    "address": hook_addr,
                    "fromBlock": hex(start),
                    "toBlock": hex(end),
                }],
            )
            if result is None:
                raise RuntimeError("eth_getLogs returned no result")
            if not isinstance(result, list):
                raise RuntimeError(f"eth_getLogs returned {type(result).__name__}")
            out.extend(r for r in result if isinstance(r, dict))
            start = end + 1
        return out

    async def fetch_flow_events(
        self,
        hook_addr: str,
        from_block: int,
        to_block: int,
        *,
        network: str,
    ) -> list[Pool4FlowEvent] | None:
        """:meth:`fetch_flow_logs` through WP3's decoder.

        ``None`` propagates as ``None`` — decoding a failed read into ``[]``
        would turn "the log endpoints are down" into "nothing traded", which is
        the FARM/HOUR-SAVED defect this repo has already shipped once.
        """
        logs = await self.fetch_flow_logs(
            hook_addr, from_block, to_block, network=network
        )
        if logs is None:
            return None
        return P.decode_flow_events(logs)


# ---------------------------------------------------------------------------
# Small decode helpers — both guarded by ``answered``
# ---------------------------------------------------------------------------


#: The only characters a transaction-hash body may contain.
#:
#: ``isascii()`` plus set membership, **never** ``int(body, 16)``, and that is
#: a transcribed bug rather than a style choice.  WP3's ``_hex_body`` records
#: it: Python's ``int`` accepts every Unicode decimal digit that ``ascii``
#: refuses, so sixty-four FULLWIDTH DIGIT characters parse as a hex number and
#: would have gone into a URL and a JSON-RPC body wearing a valid shape.
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

#: A transaction hash is 32 bytes.  Equality, not a minimum: a longer string
#: that merely *starts* with a real hash is a different string, and truncating
#: it to fit would be this module inventing a hash nobody asked for.
_TX_HASH_NIBBLES = 64


def _tx_hash_body(tx_hash: Any) -> str | None:
    """The lowercase 64-nibble body of a transaction hash, or ``None``.

    Total over third-party input, because that is what this is: the hash comes
    back out of ``~/.maxpane/``, so it is a hand-editable string by exactly the
    argument that makes a hand-edited discovery payload third-party input.
    ``None``, a non-string, the wrong length, a non-ASCII digit and a non-hex
    character all return ``None`` rather than raising or, worse, reaching a
    socket.

    This deliberately duplicates the shape of ``surf_pool4._hex_body`` rather
    than importing it: that helper is private to WP3 and is free to be renamed
    or re-scoped without telling anyone, and reaching across a package boundary
    into a ``_`` name is a dependency neither side agreed to. Redundancy plus
    an agreement test is the repo's answer when a rule must not diverge and
    cannot be shared —
    ``test_the_hash_validator_refuses_what_wp3s_address_validator_refuses``
    is that test, and it pins the Unicode-digit class both helpers exist for.
    """
    if not isinstance(tx_hash, str):
        return None
    body = strip0x(tx_hash.strip())
    if len(body) != _TX_HASH_NIBBLES:
        return None
    if not body.isascii() or not set(body) <= _HEX_DIGITS:
        return None
    return body.lower()


def _addr_or_none(raw: Any) -> str | None:
    """A checksummed address from a getter return, or ``None``.

    ``None`` for an unanswered getter (A10) **and** for the zero address: a
    getter that answers ``0x000…0`` is telling us the slot is unset, which is
    not an address to follow or to render. ``evm_abi.decode_address`` returns
    ``ZERO_ADDRESS`` for an empty payload, so the guard has to be here.
    """
    if not P.answered(raw):
        return None
    body = strip0x(str(raw).strip())[-40:]
    if int(body, 16) == 0:
        return None
    return P.checksum_address(body)


def _hex_int(raw: Any) -> int | None:
    """``0x…`` -> ``int``, or ``None``.  Never ``0`` on a failed parse."""
    if not isinstance(raw, str):
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


def _uint_or_none(raw: Any) -> int | None:
    """A uint256 return value, or ``None`` if the getter did not answer.

    ``evm_abi.decode_uint`` returns ``0`` for an empty payload, and ``"0x"`` is
    exactly what an ``eth_call`` to an address with no code returns (A10).
    Calling it unguarded would write a sentinel — a supply of zero, a backlog
    of zero — that persists and outlives the outage.  ``P.answered`` is the one
    place that distinction lives and this is the only door into ``decode_uint``
    in this module.
    """
    if not P.answered(raw):
        return None
    try:
        return decode_uint(strip0x(str(raw).strip()))
    except ValueError:
        return None


__all__ = [
    "DISTRIBUTOR_SIGNATURES",
    "DOCS_URL",
    "MAINNET_HOOK_GETTERS",
    "MAINNET_LOG_RPCS",
    "MAINNET_STATE_RPCS",
    "SEPOLIA_LOG_RPCS",
    "SEPOLIA_STATE_RPCS",
    "LOG_WINDOW_BLOCKS",
    "Pool4Client",
    "Pool4LogRangeError",
]
