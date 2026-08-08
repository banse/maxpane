# WP1 — SurfClient: keyless data client for the surf dashboard

**Goal:** Ship `maxpane_dashboard/data/surf_client.py` — every `fetch_*` method of the frozen
surface, fully tested against committed fixtures with a raising transport, no network, no keys.

**Dependencies:** WP0 only — `data/surf_addresses.py` (constants, topics, selectors
**including `SEL_OWNER_OF`**) and `data/surf_models.py` (the dataclasses **and
`CONSTRUCTOR_KWARGS`**). WP2 (signals), WP3 (cache), WP4 (manager), WP5/WP6 (widgets,
screen) build on this client's return models; they do NOT depend on this WP's internals,
and this WP imports nothing from them — `ChannelTx` deliberately carries the raw
`input_hex` so `decode_utf8_calldata` / `classify_channel_tx` keep exactly one caller
(WP4), which is what makes WP1 and WP2 buildable in parallel.

**`ChainState.lp_imd_wei` / `lp_weth_wei` are in `CONSTRUCTOR_KWARGS` and this package is
their producer.** They feed the PRD §5 hero keys `lp_imd` / `lp_weth`, and they are computed
here rather than downstream because the derivation needs `tickLower` / `tickUpper` from the
`positions()` decode — words that exist nowhere else in the frozen surface. WP1.4's freeze
check fails loudly if WP0.4 has not landed them. Do not start WP1.4 with a `getattr`
workaround: a defaulted read is exactly how these keys became permanently `None` before, and
`_field()`-style loudness is the whole reason the vocabulary is now frozen in one place.

**Owner note:** WP1 owns exactly three surfaces: `maxpane_dashboard/data/surf_client.py`,
`tests/data/test_surf_client.py`, and `tests/fixtures/surf/client/*` (test-sized slices of the
captures — the captures README mandates slicing over wholesale loading). Do not touch
`surf_addresses.py` / `surf_models.py`; if a constant or model field is missing, **report it to
the orchestrator, do not add it** (house rule: report defects in other agents' files).

**Read before coding** (in this order — the client is a style mirror, not an invention):

1. `maxpane_dashboard/data/fwa_client.py` — endpoint bans at construction, `_rpc` retry +
   rotation, Multicall3 aggregate3 batching, per-view `None`-not-`0` decode, `OwnedHttpClient`.
2. `maxpane_dashboard/data/ttt_client.py` — the two-pool (state vs logs) split,
   `_looks_like_endpoint_limitation` message-text classification, `_MALFORMED_REQUEST_CODES`.
3. `maxpane_dashboard/data/frenpet_client.py` — `_get_with_retry` REST pattern.
4. `maxpane_dashboard/data/fwa_market.py` — DexScreener/GeckoTerminal degradation discipline.
5. `tests/data/test_fwa_client.py` lines 60–305 — `_no_network`, `RecordingTransport`,
   `decode_aggregate3_calldata`, `encode_aggregate3_result`. Reuse these idioms verbatim.

**Design decisions frozen by this WP** (WP2–WP5 may rely on them):

- The client does **no signal math**, **no UTF-8 message decoding** and **no channel
  classification** — those are `analytics/surf_signals.py` (WP2), called by WP4.
- It is otherwise **raw with two named exceptions**: `fetch_dev_activity` filters and labels
  (WP0.4 forces it — see the ownership table below), and nothing else does. "Raw" is also an
  *obligation*, not just an absence: log rows must reach WP4 carrying every field its decoders
  index into. A previous draft dropped that half, and dropping it silently disabled four
  features.
- Failure semantics: every `fetch_*` returns its model (or list) on any partial success and
  `None` when **every** source for that method failed. Inside a model, an individually failed
  field is `None`. `0`, `[]`, `""` are real values, never failure encodings.
- Pools: state RPC (`ethereum-rpc.publicnode.com` + fallbacks) for `eth_call` /
  `eth_getTransactionCount`; logs RPC (`gateway.tenderly.co/public/mainnet`, `eth.drpc.org`)
  for `eth_getLogs`. The string `"eth_getLogs"` appears only in the logs section of the
  module; a structural test pins it. `eth_blockNumber` is asked of **both** pools and that is
  deliberate: the logs pool answers it to bound a `getLogs` window (WP1.9), and the state pool
  answers it as the fourth leg of the nonce batch (WP1.3) so `NonceSet.block_number` describes
  the same round as the counts. The two heights are not interchangeable and neither is ever
  substituted for the other.
- **Every field WP0.4 declares on a model this WP produces is passed by this WP** — including
  the two `block_number` fields, which carry a default and so cannot fail loudly on their own.
  `NonceSet.block_number` comes from WP1.3's fourth batch leg and `ChainState.block_number`
  from WP1.4's eighth `aggregate3` sub-call; both are read by WP4's `_pool_chain`. WP1.2's
  `declared - passed` assertion is what keeps this true as WP0 evolves.
- All addresses compared/stored **lowercase**; the checksummed constants from
  `surf_addresses.py` are lowered once at module import.

**Ownership and the hand-over contract (read this before WP1.6 and WP1.9):**

Two steps were previously delegated into a gap where WP1 and WP4 each pointed at the other, so
neither implemented them. That left signals 2/3/5 dead, `hook_status` pinned to `NOT LIVE`
forever, `nft_last_sales` permanently empty and the address-poisoning defense entirely absent.
They are settled here, and **each half is assigned by the frozen artifact rather than by
preference** — WP0.4 is the one input neither WP1 nor WP4 may edit, so an owner derived from it
survives a re-read by either package. A split decided on taste does not: this question has
already been "settled" in both directions once.

| Step | Owner | The artifact that decides it |
|---|---|---|
| `DevTx` sender filter, `KNOWN_LABELS` lookup, `kind` vocabulary | **WP1**, Task WP1.6 | WP0.4 declares `DevTx.counterparty`, `.counterparty_label` and `.kind` **without defaults**. A constructor cannot leave them unset, so the only place they can be filled is where `DevTx` is built. WP0.4's own docstring makes it an invariant: *"Rows are only ever built where the sender is a dev wallet."* |
| `eth_getLogs` rows → `hooks` / `token_id` / `amount` / `ts` | **WP4**, `_hex_int` / `_word_addr` / `_log_ts` / `_v4_launch_rows` | Nothing freezes the *contents* of `LogWindow`'s four groups — WP0.4 froze them as bare `tuple[dict, ...]`. With no artifact forcing the split, it goes where it is already implemented, and WP1's obligation is to hand the rows over intact (below). |

Two consequences to carry into WP4, for the plan owner rather than for this file: `_activity_rows`
must **read** `counterparty` / `counterparty_label` / `kind` instead of deriving them (keeping
its sender re-check as defence in depth is fine — that is an assertion about a rule, not a
second copy of one), and the note that `seaport_sales` arrives "decoded by WP1.9b" is wrong —
it arrives raw like the other three groups and needs the same `_word_addr` treatment.

WP1's remaining obligation for logs is real and has its own tests: a raw row must reach the
manager with everything the manager needs to decode it. WP1 must not normalise, prune or
re-key these payloads.

| WP1 must preserve | Because WP4 reads | Would silently break |
|---|---|---|
| `topics` (full list, order intact) on every log row | `topics[1..3]` — token id, currencies, mint recipient | GATE OPEN detail, BRIDGE STAGE |
| `data` (full hex, not truncated) on every log row | `hooks` = data word 2; Seaport offer/consideration; mint amount | V4 LAUNCH — the one event this dashboard exists for |
| `blockNumber` **and** `blockTimestamp` when the endpoint sends it | `_log_ts(log, now)` prefers a real stamp and falls back to first-seen | FIRED ages read "just now" for older events |
| `transactionHash` | WP2's detectors key on it so a re-observed row cannot re-fire | duplicate FIRED on every refresh |
| `DevTx.from_addr`, `.to_addr`, `.value_wei`, `.method`, `.created_contract` | WP4's defence-in-depth sender re-check, and the `value_eth` scaling | a re-check with nothing to check |

(Dev-activity rows are the *other* direction: WP1 filters and labels them before WP4 ever sees
them — see the ownership table above.)

**Fixture inventory this WP creates** (Task WP1.2 step 1; all sliced from
`tests/fixtures/surf/captures/`, real payloads captured 2026-08-08):

| fixture | sliced from | used by |
|---|---|---|
| `tests/fixtures/surf/client/announce_txs_page1.json` | `announce_eth_txs.json` (21 rows, wrapped in `{"items":…,"next_page_params":null}`) | WP1.5 |
| `tests/fixtures/surf/client/dev_txs_page1.json` | `wallet_eth_txs_page1.json` (30 rows, wrapped) | WP1.6 |
| `tests/fixtures/surf/client/ops_txs_page1.json` | `ops_eth_txs.json` (50 rows, wrapped) | WP1.6 |
| `tests/fixtures/surf/client/geckoterminal_imd.json` | verbatim copy | WP1.7 |
| `tests/fixtures/surf/client/dexscreener_imd.json` | verbatim copy | WP1.7 |
| `tests/fixtures/surf/client/dexscreener_fp.json` | verbatim copy | WP1.7 |
| `tests/fixtures/surf/client/idmd_token.json` | `identity_token.json` verbatim | WP1.8 |
| `tests/fixtures/surf/client/idmd_counters.json` | `identity_counters.json` verbatim | WP1.8 |
| `tests/fixtures/surf/client/idmd_transfers_page1.json` | `identity_transfers_page1.json` (25 rows, **projected** to the five fields the client reads — the capture carries a base64 SVG per row) | WP1.8 |

No `eth_getLogs` fixture exists, and none is needed here: the captures hold no raw log payloads
(Blockscout's REST views are already decoded), WP1.9's tests drive synthetic rows through
`_fake_log`, and WP4 builds its own log doubles for the decoders it owns. If WP4 ever wants
real encoded rows, the reference values below are the derivation source.

Ground-truth values derived from the captures (verified by running the derivation commands in
the tasks below — do not re-type from memory):

- announce channel: 21 txs on one page; newest self-post nonce **13**, ts
  `2026-08-07T04:27:11Z` = epoch **1786076831.0**, hash `0xe397869a…440055`.
  Live account nonce therefore **14** (`0xe`).
- register() action row: hash `0xa4ce159e…d1c1c2`, `to` = ERC-8004 registry
  `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`, `method` = `"register"`, input starts
  `0xf2c298be`, and its body is **not** valid UTF-8 (`0xf2 0xc2` fails a strict decode).
- funding row: hash `0x632f5dc3…5e402a`, from dev wallet, `value` = `54000000000000000`,
  `raw_input` = `"0x"`.
- dev wallet page: 30 rows, newest nonce **2349** → account nonce **2350** (`0x92e`).
- ops wallet page: 50 rows, 37 sent by ops, newest sent nonce **37** → account nonce **38**
  (`0x26`). The 33-ETH LP add: hash `0x90a0f8e2…`, nonce 37, `method` = `"multicall"`,
  `to` = NFPM `0xC36442b4a4522E871399CD717aBDD847Ab11FE88`,
  `value` = `33252659725872729307` wei, ts `2026-08-07T04:23:23Z` = epoch **1786076603.0**.
- market: DexScreener IMD price **0.7074** USD, 24h Δ **30.89**, vol **244178**, liquidity
  **548701.21** USD / **388421** IMD / **142.7067** WETH, fdv **1647147**, baseToken name
  `"Identity.md"` / `"IMD"`; GeckoTerminal price **0.7127337345** (name `"Vibe Coins"` —
  STALE, display-only-never); cross-check diff **0.751 %** → agree. DexScreener FP (Base):
  3 pairs, max-liquidity pair (424308.81 USD) price **0.7274**.
- IDMD: holders **667**, total_supply `"2000"`, `/counters` transfers **7411** — that is the
  **lifetime** count, not a daily rate; the PRD's "~38 transfers/day" is a *different* number
  and WP1.8 derives it from timestamps (see the next bullet).
- IDMD transfer page (`identity_transfers_page1.json`): **25 rows, newest first**, newest
  `2026-08-08T09:51:59Z` = epoch **1786182719.0**, oldest **1786143935.0** — a **10.77 h**
  span, so all 25 fall inside a 24 h window anchored at the newest row, and **16** remain
  inside one anchored **18 h** later (its cutoff is `newest − 6 h` = 1786161119, which falls
  between row 15 at 5.907 h old and row 16 at 8.197 h old). Those two numbers are what WP1.8's
  window tests assert. **The clock offset and the window length are different quantities** —
  the page is shorter than the window, so an offset at or below **13.23 h** still counts all
  25, and 16 is the answer only for an offset in **(15.81 h, 18.09 h]** (above that the two
  rows sharing ts 1786161455.0 leave together and the count drops straight to 14).
- Identities written: **1 of 2000** (IDMD #0, 2026-05-14, gate closed since) — a lifetime
  count, months outside any log window this client opens.
- IMD Blockscout total_supply `"2376731868679000000000000"` (= 2,376,731.868679 IMD).
- LP position #1167726 is **full range** (`tickLower`/`tickUpper` = ∓887200 at spacing 200)
  and in range, which is why `L·√P / 2⁹⁶` and `L·2⁹⁶/√P` reproduce DexScreener's reserves
  (388,421 IMD / 142.7067 WETH) to within 1 %. That agreement is a *property of this
  position today*, not a formula — WP1.4 implements the general one.

**Ground truth for WP1.6's filter and for WP4's log decoders**, derived by reading the capture
files — never re-typed from memory. WP1 owns the captures and the fixture slices, so this is
the one place these can be re-derived when a capture is refreshed; the log-side values are
recorded here for WP4's tests to assert against rather than inventing numbers.

- **Event layouts**, read off the *verified* sources in the captures, not from memory:
  `IdentityHashUpdated(uint256 indexed id, string ipfsHash, bool permanent)`
  (`identity_contract.json` → `source_code_head`; so the token id is **topics[1]**, and the
  data is a dynamic `(string,bool)` nobody needs to decode);
  `Initialize(bytes32 indexed id, address indexed currency0, address indexed currency1,
  uint24 fee, int24 tickSpacing, address hooks, uint160 sqrtPriceX96, int24 tick)`
  (so `hooks` is **data word 2**, not a topic — this is the field the whole V4 LAUNCH branch
  turns on); `OrderFulfilled(bytes32 orderHash, address indexed offerer, address indexed zone,
  address recipient, SpentItem[] offer, ReceivedItem[] consideration)` where `SpentItem` is 4
  words `(uint8 itemType, address token, uint256 identifier, uint256 amount)` and
  `ReceivedItem` is 5 words (same + `address recipient`).
- **IMD is 18 decimals**, and this is *captured*, not assumed:
  `ops_eth_token_transfers.json` → `token.decimals == "18"`. (There is no `SEL_DECIMALS` in
  WP0's frozen surface — see open issue 7.)
- **Two real bridge-stage mints** (IMD `Transfer` from `0x0` → ops wallet), the exact shape
  signal 5 watches for, 4½ and 2 minutes before the 33-ETH LP add at ts 1786076603.0:

  | ts | block | tx | amount |
  |---|---|---|---|
  | 1786076339.0 | 25700653 | `0x17084b1b…cea85c` | `10000000000000000000000` wei = 10,000 IMD |
  | 1786076495.0 | 25700666 | `0xc7acbcc0…1d0a01` | `114366899256000000000000` wei = 114,366.899256 IMD |

- **One real Seaport purchase**, dev wallet, tx `0x5b4d1b44…eadad2`, ts **1786163591.0**,
  block **25707884**, `fulfillAvailableAdvancedOrders`, two orders in one transaction —
  the exact `nft_last_sales` shape:

  | token_id | seller proceeds | OpenSea fee | realized ETH |
  |---|---|---|---|
  | 1751 | `178200000000000000` | `1800000000000000` | **0.18** |
  | 354 | `182059911000000000` | `1838989000000000` | **0.1838989** |

  The two realized totals sum to `363898900000000000` wei = the transaction's `value` exactly.
  That identity is the cheapest available proof that a Seaport decoder is correct: get the
  offer/consideration walk wrong and the sum stops matching the transaction value.
- **The poisoning rows are live and on both wallets.** 17 of the 80 captured rows are inbound;
  six of those are ≤ 1 gwei dust from lookalike senders:

  | spoof sender | imitates | page |
  |---|---|---|
  | `0x61ccfd5d…10df14e` (×2) | `LP_FEE_SINK_B` `0x61cc704c…6373f14e` | ops |
  | `0xf3083828…c2f60ee6` | `LP_FEE_SINK_A` `0xf3084bc7…424d60ee6` | ops |
  | `0xf3087598…d80b70ee6` | `LP_FEE_SINK_A` | ops |
  | `0x5823d93a…27d84e55` | `DEV_SWEEP` `0x58239ad0…30274e55` | dev |
  | `0xa4ad23e7…7867d5717` | (no match in the cast — still dust, still dropped) | dev |

  Each shares its target's first 4 and last 4 hex characters — exactly what a truncated
  `0x…` rendering collapses into. WP0 already pins three of them in `LIVE_SPOOFS`.
- **After the sender==dev-wallet filter: 63 rows survive** (26 dev + 37 ops out of 80), with
  the PRD §4 `kind` vocabulary distributing as `other` 33 · `fwa claim` 12 · `transfer` 8 ·
  `lp` 5 · `burn` 3 · `bridge` 2 under the address-keyed rules (`to == NFPM` → lp,
  `to == BURN_EXECUTOR` → burn, `to == RELAY_DEPOSITORY` → bridge, `to == FWA_SPLITTER` and
  `method == "claim"` → fwa claim, `method is None` and `raw_input == "0x"` → transfer, else
  other). Zero rows carry `created_contract` on these two pages, so `deploy` has no live
  example — WP1.6 covers it with a synthetic row and says so.

---

### Task WP1.1: Module skeleton — pools, banned hosts, RPC plumbing, error classification

**Files:**
- Create: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `rpc_common.OwnedHttpClient / ENDPOINT_DEAD_CODES / jsonrpc_payload / pace`;
  `surf_addresses` constants (import only, no values re-typed).
- Produces:
  `STATE_RPC_PRIMARY: str`, `STATE_RPC_FALLBACKS: list[str]`, `LOG_RPCS: list[str]`,
  `BLOCKSCOUT_BASE: str = "https://eth.blockscout.com/api/v2"`,
  `DEXSCREENER_TOKENS_API: str`, `GECKO_TOKEN_API: str`,
  **`COINGECKO_ETH_URL: str`** (WP1.7's fourth market leg — declared here so it is not
  invented three tasks later),
  `LOG_WINDOW_BLOCKS: int = 2400`, `MAX_CHANNEL_PAGES: int = 3`, `MAX_ACTIVITY_PAGES: int = 2`,
  `MAX_NFT_TRANSFER_PAGES: int = 4`, `MAX_REGISTRY_LOG_PAGES: int = 4`,
  `_DAY_SECONDS: float = 86400.0`, `PRICE_AGREE_TOLERANCE_PCT: float = 5.0`,
  `_looks_like_endpoint_limitation(err) -> bool`, `_is_range_limitation(err) -> bool`,
  `class SurfClient(OwnedHttpClient)` with
  `__init__(state_rpc=STATE_RPC_PRIMARY, state_fallbacks=None, log_rpcs=None,
  blockscout_base=BLOCKSCOUT_BASE, *, http_client=None, inter_call_delay=0.12,
  backoff_seconds=(0.5, 1.5), now_fn=time.time, log_window_blocks=LOG_WINDOW_BLOCKS)`,
  `.state_endpoints` / `.log_endpoints` properties, `async _rpc_state(method, params)`,
  `async _rpc_state_batch(calls: list[tuple[str, list]]) -> list | None`,
  `async _rpc_logs(method, params)`, `async _get_json(url, params=None)`, `close()` (inherited).

- [ ] **Write the failing tests.** Create `tests/data/test_surf_client.py`:

```python
"""Tests for maxpane_dashboard.data.surf_client.

**Zero network.** Every test drives the client through an ``httpx.MockTransport``.
There are TWO offline doubles and they are not interchangeable:

* ``_raising_client`` raises ``AssertionError`` on any request, so it proves a
  code path performed **no I/O at all**. It may only be used where nothing is
  fetched — ``MockTransport`` does not wrap handler exceptions, so that
  ``AssertionError`` propagates verbatim through httpx and is caught by none of
  the client's ``except (httpx.HTTPError, ValueError)`` / ``except RuntimeError``
  handlers.
* ``_offline_client`` raises ``httpx.ConnectError`` — a real transport failure
  the client already classifies — so it models a **total outage** and every
  ``fetch_*`` degrades to ``None`` through its normal retry/rotation path. Every
  ``*_outage_returns_none`` test uses this one.

``RecordingTransport`` captures every request so pool separation is asserted
structurally, not assumed. Fixtures are committed slices of real payloads
captured 2026-08-08 (see ``tests/fixtures/surf/client/``); expected values below
were derived by decoding those files, never typed from memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import surf_client
from maxpane_dashboard.data.surf_client import SurfClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "client"


def load_fixture(name: str) -> Any:
    with open(FIXTURES / name) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles (mirrors tests/data/test_fwa_client.py)
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _raising_client(**kw: Any) -> SurfClient:
    """A client that must not be asked for anything — proves zero I/O.

    Use ONLY where the code path under test issues no request. An
    ``AssertionError`` raised inside a ``MockTransport`` handler is re-raised
    verbatim by httpx (verified against the installed 0.28.1: the transport does
    not wrap handler exceptions), and ``AssertionError`` is not an
    ``httpx.HTTPError``, a ``ValueError`` or a ``RuntimeError`` — so it sails
    straight through every ``except`` clause in ``SurfClient`` and out of the
    fetcher. For "the whole internet is down, return None", use
    ``_offline_client`` below.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _offline(request: httpx.Request) -> httpx.Response:
    """Fail at the socket, the way a real outage does."""
    raise httpx.ConnectError(
        f"test attempted real network access: {request.method} {request.url}",
        request=request,
    )


def _offline_client(**kw: Any) -> SurfClient:
    """A client whose every request fails at the transport layer.

    ``httpx.ConnectError`` IS an ``httpx.HTTPError``, so ``_rpc_state``,
    ``_rpc_state_batch``, ``_rpc_logs`` and ``_get_json`` all classify it,
    exhaust their retries, rotate through every endpoint and give up — which is
    exactly the total-outage path each ``fetch_*`` must degrade to ``None``
    through. This is the double for every ``*_outage_returns_none`` test.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_offline)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, method, payload_or_None)``."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[tuple[str, str, Any]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                try:
                    payload = json.loads(request.content)
                except ValueError:
                    payload = None
            self.requests.append((str(request.url), request.method, payload))
            return handler(request)

        super().__init__(_wrapped)

    def urls(self) -> list[str]:
        return [u for (u, _m, _p) in self.requests]


def _client_on(transport: httpx.MockTransport, **kw: Any) -> SurfClient:
    return SurfClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _rpc_ok(payload: dict, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}


# ---------------------------------------------------------------------------
# WP1.1 — configuration and classification
# ---------------------------------------------------------------------------


def test_state_and_log_pools_are_disjoint_roles():
    client = _raising_client()
    assert client.state_endpoints[0] == "https://ethereum-rpc.publicnode.com"
    # publicnode refuses archive eth_getLogs (CLAUDE.md dead-endpoint table):
    # it must never appear in the logs pool.
    assert all("publicnode" not in u for u in client.log_endpoints)
    assert "https://gateway.tenderly.co/public/mainnet" in client.log_endpoints
    assert "https://eth.drpc.org" in client.log_endpoints


@pytest.mark.parametrize(
    "url",
    [
        "https://eth.llamarpc.com",       # HTTP 521, origin down
        "https://rpc.ankr.com/eth",       # now keyed
        "https://cloudflare-eth.com",     # -32046 on every call
        "https://api.reservoir.tools",    # sunset
        "https://mainnet.infura.io/v3/x", # keyed
    ],
)
def test_banned_host_rejected_at_construction(url):
    with pytest.raises(ValueError):
        SurfClient(state_rpc=url, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))
    with pytest.raises(ValueError):
        SurfClient(log_rpcs=[url], http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        # 1rpc ships its 50-block log cap under -32602 — the *malformed* code.
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "query exceeds max block range"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, True),
        ({"code": -32046, "message": "Cannot fulfill request"}, True),
        # A genuinely malformed request must NOT rotate — it fails the same way
        # on every endpoint and would burn the whole pool.
        ({"code": -32602, "message": "invalid argument 0: json: cannot unmarshal"}, False),
        ({"code": -32601, "message": "the method does not exist"}, False),
        # A non-dict error is unclassifiable: err toward rotation.
        ("boom", True),
    ],
)
def test_endpoint_limitation_classification_is_message_first(err, expected):
    assert surf_client._looks_like_endpoint_limitation(err) is expected


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "block range is too large, try 25700000-25700001"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, False),
        ({"code": -32602, "message": "invalid argument"}, False),
    ],
)
def test_range_limitation_is_a_narrower_class(err, expected):
    assert surf_client._is_range_limitation(err) is expected


@pytest.mark.asyncio
async def test_rpc_state_rotates_on_dead_status_and_error_body():
    """publicnode answers HTTP 403 → rotate; tenderly answers an error body →
    rotate; the third endpoint answers — the caller sees its result."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        payload = json.loads(request.content)
        if "publicnode" in url:
            return httpx.Response(403, json={})
        if "tenderly" in url:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32000, "message": "capacity exceeded, upgrade plan"},
            })
        return httpx.Response(200, json=_rpc_ok(payload, "0x92e"))

    async with _client_on(RecordingTransport(handler)) as client:
        result = await client._rpc_state("eth_getTransactionCount",
                                         ["0x" + "11" * 20, "latest"])
    assert result == "0x92e"
    assert len({u.split("/")[2] for u in seen}) == 3  # three distinct hosts tried


@pytest.mark.asyncio
async def test_rpc_state_gives_up_after_all_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, json={})

    async with _client_on(RecordingTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            await client._rpc_state("eth_blockNumber", [])


@pytest.mark.asyncio
async def test_close_does_not_close_injected_client():
    http = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    client = SurfClient(http_client=http)
    await client.close()
    assert not http.is_closed  # injected clients belong to the caller
    await http.aclose()
```

- [ ] Add `pytest.ini`/existing config already enables `pytest-asyncio` (it does — every
  `test_*_client.py` uses bare `@pytest.mark.asyncio`). Run:
  `.venv/bin/python -m pytest tests/data/test_surf_client.py -v` —
  **expected failure:** `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_client'`.
- [ ] **Minimal implementation.** Create `maxpane_dashboard/data/surf_client.py`:

```python
"""Keyless multi-source client for the surf dashboard (surfsurf.eth tracker).

Four source groups, all keyless (PRD docs/surf_PRD.md §5):

=================  =========================================================
state RPC          eth_call getters + the three nonces. publicnode primary —
                   the strongest keyless batcher, but it REFUSES archive
                   ``eth_getLogs``, which is why the pools are separate.
logs RPC           recent-window ``eth_getLogs`` only (bridge mints,
                   IdentityHashUpdated, v4 Initialize, Seaport OrderFulfilled).
Blockscout REST    v2 GETs only: channel bodies, dev tx pages, token counters.
                   v1 ``eth_call`` is broken (HTTP 400) — never used.
market REST        GeckoTerminal + DexScreener, cross-checked. GeckoTerminal
                   serves a STALE token name ("Vibe Coins") — display names
                   come from DexScreener/onchain, never from GeckoTerminal.
=================  =========================================================

Failure semantics (CLAUDE.md, non-negotiable): a failed read is ``None``,
never ``0``. Every public ``fetch_*`` returns its model with per-field
``None`` for individually failed reads, and ``None`` overall only when every
source for that method failed. No public method ever raises into the refresh
loop.

RPC errors are classified on MESSAGE TEXT, not code: providers reuse -32602
and -32005 for unrelated meanings, and one provider's "suggested retry range"
decrements one block per round trip — following it verbatim livelocks. This
client never follows a suggested range; it halves its own window (bounded).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoints — two pools, structurally separate (CLAUDE.md hazard table)
# ---------------------------------------------------------------------------

STATE_RPC_PRIMARY = "https://ethereum-rpc.publicnode.com"
STATE_RPC_FALLBACKS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://rpc.mevblocker.io",
]
#: Logs pool. publicnode is deliberately absent: it 403s archive eth_getLogs.
LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",  # hard 10k-block page cap; fine at our window
]

_BANNED_RPC_HOSTS = frozenset(
    {
        "eth.llamarpc.com",       # HTTP 521, origin down
        "rpc.ankr.com",           # now requires an API key
        "eth-mainnet.g.alchemy.com",
        "mainnet.infura.io",
        "api.opensea.io",
        "api.reservoir.tools",    # sunset, DNS gone
        "cloudflare-eth.com",     # -32603 / -32046 on every call
    }
)

BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"
DEXSCREENER_TOKENS_API = "https://api.dexscreener.com/latest/dex/tokens"
GECKO_TOKEN_API = (
    "https://api.geckoterminal.com/api/v2/networks/eth/tokens/{address}"
)
#: ETH/USD, keyless. The URL is copied verbatim from
#: ``maxpane_dashboard/data/price.py::_COINGECKO_URL``, which is module-private
#: there — this is a copied *string*, not a copied client. WP1.7 explains why
#: ``PriceClient`` itself must not be instantiated here (it builds its own
#: ``httpx.AsyncClient`` and would bypass the injected transport) and why its
#: ``0.0``-on-failure sentinel must not be copied with it.
COINGECKO_ETH_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=ethereum&vs_currencies=usd"
)

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
_INTER_CALL_DELAY = 0.12  # publicnode 429s under bursts; measured in fwa_client

#: Recent-window size for eth_getLogs (~8 h at 12 s blocks). Constructor-
#: injectable; halved (never "suggested-range"-followed) on range errors.
LOG_WINDOW_BLOCKS = 2400
_LOG_MIN_WINDOW = 300
_LOG_MAX_SHRINKS = 3

MAX_CHANNEL_PAGES = 3   # 21 txs fit one page today; growth must not break us
MAX_ACTIVITY_PAGES = 2  # per wallet
#: ~38 IDMD transfers/day at 50 rows/page: four pages is ~5x headroom, and
#: hitting the bound means "unknown", never a partial count (WP1.8).
MAX_NFT_TRANSFER_PAGES = 4
#: Identity writes are 1 of 2000 today; the same bound-means-unknown rule.
MAX_REGISTRY_LOG_PAGES = 4

_DAY_SECONDS = 86400.0

PRICE_AGREE_TOLERANCE_PCT = 5.0

# ---------------------------------------------------------------------------
# Error classification — message text first (mirrors ttt_client; policy is
# deliberately NOT shared via rpc_common, see that module's docstring)
# ---------------------------------------------------------------------------

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
    """True if *err* reads as "this endpoint can't", not "this request is bad"."""
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


class _LogRangeError(RuntimeError):
    """eth_getLogs failed because the requested window is too wide."""


class SurfClient(OwnedHttpClient):
    """Async, keyless, read-only client for every surf data source."""

    def __init__(
        self,
        state_rpc: str = STATE_RPC_PRIMARY,
        state_fallbacks: list[str] | None = None,
        log_rpcs: list[str] | None = None,
        blockscout_base: str = BLOCKSCOUT_BASE,
        *,
        http_client: httpx.AsyncClient | None = None,
        inter_call_delay: float = _INTER_CALL_DELAY,
        backoff_seconds: tuple[float, ...] = _BACKOFF_SECONDS,
        now_fn: Callable[[], float] = time.time,
        log_window_blocks: int = LOG_WINDOW_BLOCKS,
    ) -> None:
        self._state_rpcs = [state_rpc, *(state_fallbacks or STATE_RPC_FALLBACKS)]
        self._log_rpcs = list(log_rpcs or LOG_RPCS)
        for url in (*self._state_rpcs, *self._log_rpcs):
            host = (urlparse(url).hostname or "").lower()
            if host in _BANNED_RPC_HOSTS:
                raise ValueError(
                    f"{url} is a banned RPC host (dead, keyed or useless) — "
                    "see surf_client._BANNED_RPC_HOSTS"
                )
        self._blockscout = blockscout_base.rstrip("/")
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._inter_call_delay = inter_call_delay
        self._backoff_seconds = backoff_seconds
        self._now_fn = now_fn
        self._log_window_blocks = log_window_blocks
        self._request_id = 0
        self._last_rpc_at: float = 0.0

    # Lifecycle (close / __aenter__ / __aexit__) comes from OwnedHttpClient.

    @property
    def state_endpoints(self) -> list[str]:
        return list(self._state_rpcs)

    @property
    def log_endpoints(self) -> list[str]:
        return list(self._log_rpcs)

    # ------------------------------------------------------------------
    # RPC plumbing
    # ------------------------------------------------------------------

    async def _post_rpc(self, url: str, payload: Any) -> httpx.Response:
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)
        return await self._client.post(url, json=payload)

    async def _rpc_state(self, method: str, params: list) -> Any:
        """One JSON-RPC call on the state pool, retry + rotation.

        Rotation policy mirrors ``fwa_client``: this pool issues only plain
        getters, so the cheapest recovery from any *endpoint* problem is the
        next endpoint. A malformed-request error, however, is OUR bug: it
        fails identically everywhere, so it short-circuits the chain.
        """
        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self._state_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payload)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break  # rotate, do not retry a dead host
                    resp.raise_for_status()
                    body = resp.json()
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break  # rotate
                        raise RuntimeError(f"malformed request: {err}")
                    return body.get("result")
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all state endpoints failed: {last_err}")

    async def _rpc_state_batch(
        self, calls: list[tuple[str, list]]
    ) -> list[Any] | None:
        """One JSON-RPC *batch array* POST on the state pool.

        Returns per-entry results aligned with *calls*; an entry that came
        back as an error is ``None`` (NEVER 0). Returns ``None`` only when
        every endpoint failed to serve the batch at all.
        """
        payloads = []
        for method, params in calls:
            self._request_id += 1
            payloads.append(jsonrpc_payload(self._request_id, method, params))
        id_to_idx = {p["id"]: i for i, p in enumerate(payloads)}
        last_err: BaseException | None = None
        for url in self._state_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payloads)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break
                    resp.raise_for_status()
                    body = resp.json()
                    if not isinstance(body, list):
                        # An endpoint that answers a batch with a scalar is
                        # not speaking the protocol; rotate.
                        last_err = RuntimeError(f"{url}: non-batch reply")
                        break
                    results: list[Any] = [None] * len(payloads)
                    for entry in body:
                        idx = id_to_idx.get(entry.get("id"))
                        if idx is None:
                            continue
                        if entry.get("error"):
                            logger.warning(
                                "batch entry %s failed: %s",
                                calls[idx][0], entry["error"],
                            )
                            continue  # stays None — never 0
                        results[idx] = entry.get("result")
                    return results
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        logger.warning("state batch failed on every endpoint: %s", last_err)
        return None

    async def _rpc_logs(self, method: str, params: list) -> Any:
        """One JSON-RPC call on the LOGS pool.

        Raises ``_LogRangeError`` when the message says the window is too
        wide (the caller halves its own window — a provider's "suggested
        range" is NEVER followed: one of them decrements a block per round
        trip and livelocks verbatim followers). Other endpoint limitations
        rotate; malformed requests raise.
        """
        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self._log_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payload)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break
                    # drpc wraps its shrinkable range cap in an HTTP 400 —
                    # classify the JSON error body BEFORE raise_for_status
                    # (talismans_client learned this live).
                    body: Any = None
                    try:
                        body = resp.json()
                    except ValueError:
                        pass
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _is_range_limitation(err):
                            raise _LogRangeError(str(err))
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break
                        raise RuntimeError(f"malformed request: {err}")
                    resp.raise_for_status()
                    return body.get("result") if isinstance(body, dict) else None
                except _LogRangeError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all log endpoints failed: {last_err}")

    # ------------------------------------------------------------------
    # REST plumbing (Blockscout v2 / DexScreener / GeckoTerminal)
    # ------------------------------------------------------------------

    async def _get_json(self, url: str, params: dict | None = None) -> Any:
        """GET with retries. Returns parsed JSON, or ``None`` on any failure."""
        for attempt in range(_MAX_RETRIES):
            try:
                self._last_rpc_at = await pace(
                    self._last_rpc_at, self._inter_call_delay
                )
                resp = await self._client.get(url, params=params)
                if resp.status_code in ENDPOINT_DEAD_CODES:
                    logger.warning("GET %s -> %s", url, resp.status_code)
                    return None
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(self._backoff_seconds[attempt])
                else:
                    logger.warning("GET %s failed: %s", url, exc)
        return None
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`
  (7 test functions, 20 collected cases after parametrisation; the async tests exercise
  rotation with zero sleeps).
- [ ] **Prove the classifier test bites:** in `_looks_like_endpoint_limitation`, change the
  final line to `return True`, rerun — the two malformed-code cases go red
  (`invalid argument…unmarshal` and `method does not exist`). Restore, rerun green.
- [ ] Commit:
  `git add maxpane_dashboard/data/surf_client.py tests/data/test_surf_client.py && git commit -m "feat(surf): WP1.1 client skeleton — dual RPC pools, banned hosts, message-text error classification"`

---

### Task WP1.2: Commit the client fixture slices

**Files:**
- Create: `tests/fixtures/surf/client/` (8 files, table in the header)
- Test: extend `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `tests/fixtures/surf/captures/*.json` (read-only source material).
- Produces: the 8 fixture files — the only test payloads WP1 uses.

- [ ] Generate the slices (one command, deterministic, review the diff before committing):

```bash
cd /Library/Vibes/autopull && .venv/bin/python - <<'EOF'
import json, pathlib
src = pathlib.Path("tests/fixtures/surf/captures")
dst = pathlib.Path("tests/fixtures/surf/client")
dst.mkdir(parents=True, exist_ok=True)

def w(name, obj):
    (dst / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")

# Blockscout /addresses/{a}/transactions returns {"items": [...], "next_page_params": ...};
# the captures were trimmed to the bare items list, so re-wrap them.
w("announce_txs_page1.json",
  {"items": json.load(open(src / "announce_eth_txs.json")), "next_page_params": None})
w("dev_txs_page1.json",
  {"items": json.load(open(src / "wallet_eth_txs_page1.json")), "next_page_params": None})
w("ops_txs_page1.json",
  {"items": json.load(open(src / "ops_eth_txs.json")), "next_page_params": None})
for a, b in [
    ("geckoterminal_imd.json", "geckoterminal_imd.json"),
    ("dexscreener_imd.json", "dexscreener_imd.json"),
    ("dexscreener_fp.json", "dexscreener_fp.json"),
    ("identity_token.json", "idmd_token.json"),
    ("identity_counters.json", "idmd_counters.json"),
]:
    w(b, json.load(open(src / a)))

# /tokens/{IDMD}/transfers — the 24 h rate's source.  The capture is 392 KB of
# base64 SVG per row (`token_instance`); the client reads five scalar fields,
# so project the rows down before committing.  Slicing here is the captures
# README's rule, and it keeps a 392 KB blob out of the suite.
KEEP = ("timestamp", "transaction_hash", "block_number", "log_index", "method")
rows = []
for r in json.load(open(src / "identity_transfers_page1.json")):
    row = {k: r[k] for k in KEEP if k in r}
    row["from"] = {"hash": (r.get("from") or {}).get("hash")}
    row["to"] = {"hash": (r.get("to") or {}).get("hash")}
    row["total"] = {"token_id": ((r.get("total") or {}).get("token_id"))}
    rows.append(row)
w("idmd_transfers_page1.json", {"items": rows, "next_page_params": None})
print("wrote", sorted(p.name for p in dst.iterdir()))
EOF
```

- [ ] **Write the failing test** (guards the slices themselves, so a future re-capture that
  breaks an assumption fails here, not three tasks later):

```python
# ---------------------------------------------------------------------------
# WP1.2 — fixture integrity
# ---------------------------------------------------------------------------


def test_client_fixtures_are_committed_and_shaped():
    announce = load_fixture("announce_txs_page1.json")
    assert set(announce) == {"items", "next_page_params"}
    assert len(announce["items"]) == 21          # the full channel, one page
    assert announce["next_page_params"] is None
    assert len(load_fixture("dev_txs_page1.json")["items"]) == 30
    assert len(load_fixture("ops_txs_page1.json")["items"]) == 50
    # The register() row is the one non-UTF-8 body — keep it in the slice.
    reg = [t for t in announce["items"]
           if t["hash"].startswith("0xa4ce159e")]
    assert len(reg) == 1 and reg[0]["raw_input"].startswith("0xf2c298be")
    # Markup-hostile message text survived the slice (em-dash post, nonce 8).
    hostile = [t for t in announce["items"] if t["nonce"] == 8
               and t["from"]["hash"] == t["to"]["hash"]]
    assert len(hostile) == 1


def test_the_transfer_slice_can_answer_a_24h_question():
    """The rate fixture must keep timestamps, and must stay small.

    Two independent failure modes: a projection that drops `timestamp` makes
    every row uncountable (the client would report 0 transfers/day, which
    looks like a quiet collection rather than a broken slice), and a slice
    that keeps `token_instance` drags 392 KB of base64 SVG per row into the
    suite.
    """
    page = load_fixture("idmd_transfers_page1.json")
    assert set(page) == {"items", "next_page_params"}
    rows = page["items"]
    assert len(rows) == 25 and all(r.get("timestamp") for r in rows)
    assert page["next_page_params"] is None
    assert all("token_instance" not in json.dumps(r) for r in rows)
    # Newest first, and the whole slice spans well under a day (10.8 h) — so
    # every row counts toward a 24 h window anchored just after the newest.
    stamps = [r["timestamp"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)


# ---------------------------------------------------------------------------
# WP1.2 — the model vocabulary this WP constructs against
# ---------------------------------------------------------------------------


#: Fields WP1 deliberately leaves at their WP0.4 default, with the reason.
#: Anything NOT listed here must actually be passed by this WP — see the
#: `declared - passed` assertion below.
WP1_LEAVES_DEFAULTED: dict[str, set[str]] = {
    # No keyless floor source exists for IDMD in v1 (WP0 open issue 2). The
    # field is pinned to None by WP0.4's own test so the widget can render the
    # explicit unavailable state; filling it would require a keyed API.
    "NftStats": {"floor_eth"},
}


def test_this_wp_constructs_against_wp0s_frozen_field_names():
    """A rename in WP0.4 must fail here, at collection, not at a live refresh.

    Every `fetch_*` below builds its model **by keyword**, so a field WP0 renames
    is a `TypeError` the first time that method runs — which in a client suite
    means the first time a transport double answers, and in production means the
    first refresh after deploy. This test drags that failure forward to import
    time and names the culprit, by asserting the kwargs this WP passes are
    exactly WP0.4's declared fields.

    It is deliberately assertive in **both** directions:

    * `passed - declared` catches WP1 inventing a field WP0 does not have (a
      `TypeError` at the first live refresh).
    * `required - passed` catches WP0 adding a mandatory field WP1 never fills
      (also a `TypeError`).
    * `declared - passed` catches the third and quietest case: WP0 declares a
      field **with a default** and names WP1 as its producer, and WP1 never
      passes it. Nothing raises, every suite stays green, and WP4 reads `None`
      forever. `ChainState.block_number` and `NonceSet.block_number` were
      exactly this — both are `int | None = None`, both are read by WP4's
      `_pool_chain`, and neither was in a constructor call. WP0's rule 1 says a
      field with no producer is a defect to *report*; this assertion is what
      makes it impossible to ship one by accident instead.

    The literal dicts below are deliberately duplicated from the `Consumes` lines
    rather than derived from the dataclasses: deriving them would make the test
    agree with any rename, which is the one thing it must not do.
    """
    import dataclasses

    from maxpane_dashboard.data import surf_models as m

    kwargs_this_wp_passes = {
        m.NonceSet: {"announce", "dev", "ops", "block_number"},
        m.ChainState: {
            "lp_liquidity", "lp_token0", "lp_token1", "lp_fee",
            "lp_tokens_owed0_wei", "lp_tokens_owed1_wei", "lp_owner",
            "lp_imd_wei", "lp_weth_wei",
            "identity_allowed", "imd_supply_wei", "sqrt_price_x96", "pool_tick",
            "imd_name", "imd_symbol", "block_number",
        },
        m.ChannelTx: {
            "tx_hash", "ts", "nonce", "from_addr", "to_addr", "value_wei",
            "input_hex", "method",
        },
        m.DevTx: {
            "tx_hash", "ts", "wallet_label", "from_addr", "to_addr",
            "counterparty", "counterparty_label", "value_wei", "method", "kind",
            "created_contract",
        },
        m.MarketSnapshot: {
            "imd_price_usd", "imd_price_usd_gecko", "imd_change_24h_pct",
            "imd_vol_24h_usd", "pool_liquidity_usd", "pool_imd", "pool_weth",
            "fp_price_usd", "fdv_usd", "eth_usd", "indexer_name",
            "indexer_symbol", "sources_agree",
        },
        m.LogWindow: {
            "from_block", "to_block", "bridge_mints", "identity_updates",
            "v4_initializes", "seaport_sales",
        },
        m.NftStats: {
            "holders", "total_supply", "transfers_total", "transfers_24h",
            "dev_holdings", "written",
        },
    }
    for model, passed in kwargs_this_wp_passes.items():
        declared = {f.name for f in dataclasses.fields(model)}
        unknown = passed - declared
        assert not unknown, f"{model.__name__}: WP1 passes {unknown}, WP0 has {declared}"
        required = {
            f.name for f in dataclasses.fields(model)
            if f.default is dataclasses.MISSING
        }
        assert not required - passed, (
            f"{model.__name__}: WP0 requires {required - passed}, WP1 never passes it"
        )
        unproduced = declared - passed - WP1_LEAVES_DEFAULTED.get(
            model.__name__, set()
        )
        assert not unproduced, (
            f"{model.__name__}: WP0 declares {unproduced} and names WP1 as the "
            "producer, but WP1 never passes it — it would be None forever with "
            "a green suite. Fill it, or ask WP0 to drop it and add it to "
            "WP1_LEAVES_DEFAULTED with the reason."
        )
```

- [ ] Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -k "fixtures_are_committed or frozen_field_names" -v`
  — **expected failure before the generation step, green after** (if you ran generation first,
  temporarily `mv` the directory to see it fail — the test must be provably load-bearing).
- [ ] **Prove the `declared - passed` assertion bites** (it is new, and it is the only guard
  against a silently unproduced field): drop `"block_number"` from
  `kwargs_this_wp_passes[m.ChainState]` and rerun `-k frozen_field_names` →
  `test_this_wp_constructs_against_wp0s_frozen_field_names` FAILS naming
  `ChainState: {'block_number'}`. Restore, green. Note that the *other* two assertions stay
  green through that mutation — that is the hole this one closes.
- [ ] Commit:
  `git add tests/fixtures/surf/client tests/data/test_surf_client.py && git commit -m "test(surf): WP1.2 commit client fixture slices and assert every declared field has a producer"`

---

### Task WP1.3: `fetch_nonces()` — the cheapest detector primitive

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `surf_addresses.ANNOUNCE / DEV_WALLET / OPS_WALLET`;
  `surf_models.NonceSet` — restated from WP0.4's `CONSTRUCTOR_KWARGS[NonceSet]`:
  `announce: int | None`, `dev: int | None`, `ops: int | None`,
  `block_number: int | None = None`. **All four are produced here.** WP0.4 names WP1.3 as
  the producer of *every* `NonceSet` field, and `block_number` is not decoration: WP4 reads it
  (its field table lists it, and `_pool_chain` stores it as the chain slot's `block`). Leaving
  it at its default is the exact defect WP0's rule 1 names — "a field with no producer is a
  defect to report, not to stub" — and it is invisible to WP1.2's old check, because a field
  with a default is never in `required`. WP1.2's `declared - passed` assertion now closes that
  hole.
- Produces: `async fetch_nonces() -> NonceSet | None` — one JSON-RPC batch POST of **four**
  legs on the state pool: three `eth_getTransactionCount(addr, "latest")` plus one
  `eth_blockNumber`. The height rides the same batch array rather than a second round trip, so
  the three counts and the block they were read at can never be a refresh apart — which is the
  only reason a `block_number` on this model is worth anything to a nonce-diff detector.

- [ ] **Write the failing tests.** Expected values are the live 2026-08-08 account nonces
  (announce newest tx nonce 13 → count 14; dev 2349 → 2350; ops 37 → 38) and the newest block
  any 2026-08-08 capture names (25,707,884 — the Seaport purchase's block, from this file's
  ground-truth table):

```python
# ---------------------------------------------------------------------------
# WP1.3 — fetch_nonces
# ---------------------------------------------------------------------------

from maxpane_dashboard.data import surf_addresses as A

#: The newest block any 2026-08-08 capture names (the Seaport purchase's block —
#: see the ground-truth table in this plan's header).  Used as the head the STATE
#: pool reports, so every expected value in this suite stays capture-derived.
#: WP1.9's logs pool has its own, deliberately different head (``LOG_HEAD_BLOCK``);
#: the two are never interchangeable and must never share a name — module globals
#: resolve at call time, so a second ``HEAD_BLOCK = …`` further down this file
#: would silently retune every assertion above it.
HEAD_BLOCK = 25_707_884
#: Derived, never pinned separately: two literals that must agree are two
#: literals that can disagree.
HEAD_BLOCK_HEX = hex(HEAD_BLOCK)  # "0x188456c"


def _nonce_handler(
    values: dict[str, str], block: str | None = HEAD_BLOCK_HEX
) -> Callable[[httpx.Request], httpx.Response]:
    """values maps lowercase address -> hex nonce; answers a JSON-RPC batch.

    ``block`` answers the fourth leg (``eth_blockNumber``); passing ``None``
    makes that one leg error while the three counts still succeed.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        assert isinstance(batch, list), "fetch_nonces must POST one batch array"
        out = []
        for entry in batch:
            if entry["method"] == "eth_blockNumber":
                assert entry["params"] == []
                if block is None:
                    out.append({"jsonrpc": "2.0", "id": entry["id"],
                                "error": {"code": -32005, "message": "rate limit"}})
                else:
                    out.append({"jsonrpc": "2.0", "id": entry["id"],
                                "result": block})
                continue
            assert entry["method"] == "eth_getTransactionCount"
            addr = entry["params"][0].lower()
            out.append({"jsonrpc": "2.0", "id": entry["id"],
                        "result": values[addr]})
        return httpx.Response(200, json=out)

    return handler


LIVE_NONCES = {
    A.ANNOUNCE.lower(): "0xe",     # 14 — channel account nonce 2026-08-08
    A.DEV_WALLET.lower(): "0x92e", # 2350
    A.OPS_WALLET.lower(): "0x26",  # 38
}


@pytest.mark.asyncio
async def test_fetch_nonces_one_batched_post_real_values():
    transport = RecordingTransport(_nonce_handler(dict(LIVE_NONCES)))
    async with _client_on(transport) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert nonces.announce == 14
    assert nonces.dev == 2350
    assert nonces.ops == 38
    # The height the three counts were read at — WP0.4's fourth NonceSet field,
    # which WP4's `_pool_chain` stores as the chain slot's `block`.  It rides
    # the SAME batch array, so it can never describe a different block from the
    # counts beside it.
    assert nonces.block_number == HEAD_BLOCK
    assert len(transport.requests) == 1  # ONE round trip for the fast tier


@pytest.mark.asyncio
async def test_fetch_nonces_partial_batch_error_is_field_none_never_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        out = []
        for entry in batch:
            if entry["method"] == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "result": HEAD_BLOCK_HEX})
                continue
            addr = entry["params"][0].lower()
            if addr == A.DEV_WALLET.lower():
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "error": {"code": -32005, "message": "rate limit"}})
            else:
                out.append({"jsonrpc": "2.0", "id": entry["id"], "result": "0xe"})
        return httpx.Response(200, json=out)

    async with _client_on(RecordingTransport(handler)) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert nonces.announce == 14
    assert nonces.dev is None      # failed read: None. 0 here would mean a
    assert nonces.dev != 0         # fresh EOA and reset every baseline.
    assert nonces.ops == 14
    assert nonces.block_number == HEAD_BLOCK  # the height leg is independent


@pytest.mark.asyncio
async def test_fetch_nonces_block_leg_failure_is_none_never_zero():
    """The height leg fails alone; the three counts still arrive.

    ``block_number`` has a default, so it is the one field on this model that a
    constructor can silently omit with every test green — which is exactly what
    happened before this test existed.  Two things are asserted: it is genuinely
    produced (the test above), and a *failed* read of it is ``None``.  ``0``
    would be genesis, and WP4 would render block 0 beside three live nonces.
    """
    handler = _nonce_handler(dict(LIVE_NONCES), block=None)
    async with _client_on(RecordingTransport(handler)) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert (nonces.announce, nonces.dev, nonces.ops) == (14, 2350, 38)
    assert nonces.block_number is None
    assert nonces.block_number != 0


@pytest.mark.asyncio
async def test_fetch_nonces_total_outage_returns_none():
    # _offline_client, not _raising_client: this path DOES issue a request, and
    # the outage has to arrive as a transport error the client classifies.
    async with _offline_client() as client:
        assert await client.fetch_nonces() is None
```

- [ ] Run — **expected failure:** `AttributeError: 'SurfClient' object has no attribute
  'fetch_nonces'`.
- [ ] **Minimal implementation** (append to the class; import `NonceSet` at module top from
  `maxpane_dashboard.data.surf_models`):

```python
    # ------------------------------------------------------------------
    # Public API — fast tier
    # ------------------------------------------------------------------

    async def fetch_nonces(self) -> NonceSet | None:
        """The three account nonces **and the height they were read at**, one
        batched POST (PRD §3 signals 1/2/4).

        The announce channel emits NO logs — this poll IS the new-post
        detector. A failed leg is ``None``: turning it into 0 would read as
        "fresh EOA" and un-fire / re-fire every nonce-derived signal, and a
        ``block_number`` of 0 would read as genesis.

        ``eth_blockNumber`` is the fourth entry of the same batch array, not a
        second round trip: a height fetched separately can describe a different
        block from the counts, which is worse than no height at all for a
        detector that diffs nonces between refreshes. It is also why the fast
        tier is still ONE request.
        """
        addrs = [A.ANNOUNCE, A.DEV_WALLET, A.OPS_WALLET]
        try:
            results = await self._rpc_state_batch(
                [("eth_getTransactionCount", [a, "latest"]) for a in addrs]
                + [("eth_blockNumber", [])]
            )
        except RuntimeError as exc:  # malformed-request short-circuit
            logger.warning("fetch_nonces: %s", exc)
            return None
        if results is None:
            return None

        def to_int(hex_or_none: Any) -> int | None:
            if not isinstance(hex_or_none, str):
                return None
            try:
                return int(hex_or_none, 16)
            except ValueError:
                return None

        return NonceSet(
            announce=to_int(results[0]),
            dev=to_int(results[1]),
            ops=to_int(results[2]),
            block_number=to_int(results[3]),
        )
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the None-not-zero test bites:** change `continue  # stays None` in
  `_rpc_state_batch` to `results[idx] = "0x0"`, rerun —
  `test_fetch_nonces_partial_batch_error_is_field_none_never_zero` goes red, and so does
  `test_fetch_nonces_block_leg_failure_is_none_never_zero` (block 0). Restore, green.
- [ ] **Prove the `block_number` producer test bites:** drop `block_number=to_int(results[3])`
  from the `NonceSet(...)` call — this is the *only* mutation in this WP that leaves the type
  checker, the constructor and WP1.2's `required - passed` check all happy, because the field
  has a default. `test_fetch_nonces_one_batched_post_real_values` must go red on
  `None != 25707884`. Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.3 fetch_nonces — four-leg batch with the read height, failed leg is None never 0"`

---

### Task WP1.4: `fetch_chain_state()` — the aggregate3 fast-state round

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `evm_abi.encode_aggregate3 / decode_aggregate3_result / decode_uint /
  decode_address / decode_string / encode_uint / strip0x / pad_left`;
  `surf_addresses.NFPM / IDENTITY_REGISTRY / IMD_TOKEN / POOL_V3 / LP_POSITION_ID /
  OPS_WALLET / SEL_POSITIONS / SEL_OWNER_OF / SEL_IDENTITY_ALLOWED / SEL_TOTAL_SUPPLY /
  SEL_SLOT0 / SEL_NAME / SEL_SYMBOL / WETH`; `surf_models.ChainState` — **restated from
  WP0.4's `CONSTRUCTOR_KWARGS[ChainState]`, not drafted here**: `lp_liquidity, lp_token0,
  lp_token1, lp_fee, lp_tokens_owed0_wei, lp_tokens_owed1_wei, lp_owner, identity_allowed,
  imd_supply_wei, sqrt_price_x96, pool_tick, imd_name, imd_symbol` (each `| None`) plus
  `lp_imd_wei, lp_weth_wei` (see the freeze check below) and
  `block_number: int | None = None` — **produced here too, by an eighth `aggregate3`
  sub-call**, not left at its default. WP0.4 names WP1.4 as the producer of every `ChainState`
  field and WP4's `_pool_chain` stores `block_number` as the chain slot's `block`; a
  constructor that omits it makes that key `None` forever with a green suite, which is WP0's
  rule 1 verbatim ("a field with no producer is a defect to report, not to stub"). It is
  filled from the round itself so the state and the height agree by construction.
- Produces: `async fetch_chain_state() -> ChainState | None`; module helpers
  `_decode_positions(raw_hex) -> dict | None`, `_decode_slot0(raw_hex) -> dict | None`,
  `_sqrt_ratio_at_tick(tick) -> int`, `_position_amounts_wei(liquidity, sqrt_price_x96,
  tick_lower, tick_upper) -> tuple[int | None, int | None]` (all exported for WP4's tests);
  `MULTICALL3` constant `"0xcA11bde05977b3631167028862bE2a173976CA11"` and the module-private
  `_SEL_GET_BLOCK_NUMBER = "0x42cbb15c"` (`getBlockNumber()`, recomputed during planning with
  `maxpane_dashboard/data/keccak.py`). It lives here rather than in `surf_addresses` because
  WP0's frozen selector surface has no entry for it and WP1 may not edit that file — the same
  arrangement as the local `_SEAPORT`; see open issue 3 and open issue 14.

**Freeze check — run this first; if it fails, stop and report, do not work around it:**

```bash
cd /Library/Vibes/autopull && .venv/bin/python -c "
from maxpane_dashboard.data.surf_addresses import SEL_OWNER_OF
from maxpane_dashboard.data.surf_models import ChainState
import dataclasses
names = {f.name for f in dataclasses.fields(ChainState)}
missing = {'lp_imd_wei', 'lp_weth_wei', 'lp_owner', 'block_number'} - names
assert not missing, f'WP0 must land these ChainState fields first: {missing}'
print('ok')
"
```

  `lp_imd_wei` / `lp_weth_wei` are the producers for the PRD §5 hero keys `lp_imd` / `lp_weth`
  (WP4 already reads exactly those two model names). They are **derived here, not downstream**,
  because the derivation needs `tickLower`/`tickUpper` from `positions()`, and those two words
  exist nowhere else in the frozen surface — a manager holding only `lp_liquidity` and
  `sqrt_price_x96` can compute the amounts *only* under the full-range assumption, which is
  wrong the day the LP is re-added concentrated. That day is signal 2's entire subject. Open
  issue 8 carries the two-line WP0 diff.

  Note the field names that are **not** what an eye-of-the-beholder draft would pick, and why
  (all three cost a rename in an earlier revision of this plan): the getter is
  `identityAllowed()` so the field is `identity_allowed` and the *flat-dict* key is
  `gate_open`; `imd_supply_wei` (not `imd_total_supply_wei`) pairs with the flat key
  `imd_supply`; `pool_tick` (not `tick`) because `positions()` already gave us `tickLower`
  and `tickUpper` and an unqualified `tick` reads as one of those. The two `tokensOwed`
  fields carry the `_wei` suffix because they are raw token amounts and WP0.4's
  `test_wei_fields_are_named_wei` pins it.

- [ ] **Write the failing tests.** The harness re-uses the FWA test codecs; the sub-call
  returns are built to the documented ABI layouts (`positions(uint256)` = flat 12-word tuple:
  nonce, operator, token0, token1, fee, tickLower, tickUpper, liquidity, feeGrowth0, feeGrowth1,
  owed0, owed1; `slot0()` = 7 words with a **signed int24 tick**; `getBlockNumber()` = one
  word, answered by Multicall3 itself, which is why its sub-call target is `MULTICALL3` and
  not one of the surf addresses):

```python
# ---------------------------------------------------------------------------
# WP1.4 — fetch_chain_state
# ---------------------------------------------------------------------------

from maxpane_dashboard.data.evm_abi import (
    encode_uint as _encode_uint,
    strip0x as _strip0x,
)

# Copied idioms from tests/data/test_fwa_client.py (they are test-local there
# too; the shared codec is evm_abi, the harness helpers are per-suite).


def decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    raw = _strip0x(data)
    assert raw[:8] == "82ad56cb", f"not an aggregate3 payload: {raw[:8]}"
    body = raw[8:]
    arr_off = int(body[0:64], 16) * 2
    n = int(body[arr_off:arr_off + 64], 16)
    base = arr_off + 64
    out: list[tuple[str, bool, str]] = []
    for i in range(n):
        off = int(body[base + i * 64: base + (i + 1) * 64], 16) * 2
        s = base + off
        target = "0x" + body[s + 24: s + 64]
        allow = int(body[s + 64: s + 128], 16) != 0
        cd_off = int(body[s + 128: s + 192], 16) * 2
        cs = s + cd_off
        cd_len = int(body[cs: cs + 64], 16)
        out.append((target, allow, "0x" + body[cs + 64: cs + 64 + cd_len * 2]))
    return out


def encode_aggregate3_result(results: list[tuple[bool, str]]) -> str:
    tuples = []
    for success, data in results:
        raw = _strip0x(data)
        n_bytes = len(raw) // 2
        padded = raw + "0" * ((64 - (len(raw) % 64)) % 64)
        tuples.append(
            _encode_uint(1 if success else 0)
            + _encode_uint(0x40)
            + _encode_uint(n_bytes)
            + padded
        )
    offsets, cursor = [], len(tuples) * 32
    for t in tuples:
        offsets.append(cursor)
        cursor += len(t) // 2
    return ("0x" + _encode_uint(0x20) + _encode_uint(len(tuples))
            + "".join(_encode_uint(o) for o in offsets) + "".join(tuples))


def _word_addr(a: str) -> str:
    return _strip0x(a).lower().rjust(64, "0")


def _word_int(v: int) -> str:
    # evm_abi.encode_uint already two's-complements a negative into a full
    # word (evm_abi.py:183), which is exactly how a node returns int24 ticks.
    return _encode_uint(v)


LP_LIQUIDITY = 2_351_337_420_000_000_000_000   # realistic uint128 for the test
POOL_TICK = 79188                              # ≈ ln(2749.58)/ln(1.0001)
SQRT_PRICE_X96 = int((2749.578620645) ** 0.5 * 2**96)


def encode_positions_return(
    *,
    liquidity: int = LP_LIQUIDITY,
    tick_lower: int = -887200,
    tick_upper: int = 887200,
) -> str:
    """Flat 12-word positions(uint256) return; token0=WETH < token1=IMD.

    Defaults are the live position: full range at spacing 200, so the side
    amounts collapse to the closed form the first LP test asserts against.
    """
    words = [
        _word_int(0),                        # nonce
        _word_addr("0x" + "00" * 20),        # operator
        _word_addr(A.WETH),                  # token0
        _word_addr(A.IMD_TOKEN),             # token1
        _word_int(10000),                    # fee — the 1% tier
        _word_int(tick_lower),               # tickLower (signed int24)
        _word_int(tick_upper),               # tickUpper
        _word_int(liquidity),                # liquidity
        _word_int(0), _word_int(0),          # feeGrowthInside{0,1}
        _word_int(7_345_000_000_000_000_000),      # tokensOwed0
        _word_int(30_784_000_000_000_000_000_000), # tokensOwed1
    ]
    return "0x" + "".join(words)


def encode_slot0_return(*, tick: int = POOL_TICK) -> str:
    words = [
        _word_int(SQRT_PRICE_X96), _word_int(tick),
        _word_int(0), _word_int(1), _word_int(1), _word_int(0), _word_int(1),
    ]
    return "0x" + "".join(words)


def encode_string_return(s: str) -> str:
    b = s.encode()
    padded = b.hex() + "0" * ((64 - (len(b.hex()) % 64)) % 64)
    return "0x" + _encode_uint(0x20) + _encode_uint(len(b)) + padded


IMD_SUPPLY_WEI = 2376731868679000000000000  # imd_token.json total_supply


def _chain_state_subcall(target: str, calldata: str) -> tuple[bool, str]:
    sel = "0x" + _strip0x(calldata)[:8]
    t = target.lower()
    if t == A.NFPM.lower() and sel == A.SEL_POSITIONS:
        arg = int(_strip0x(calldata)[8:72], 16)
        assert arg == A.LP_POSITION_ID  # 1167726 — the watched position
        return True, encode_positions_return()
    if t == A.NFPM.lower() and sel == A.SEL_OWNER_OF:
        arg = int(_strip0x(calldata)[8:72], 16)
        assert arg == A.LP_POSITION_ID
        return True, "0x" + _word_addr(A.OPS_WALLET)   # frenpet.eth holds it
    if t == A.IDENTITY_REGISTRY.lower() and sel == A.SEL_IDENTITY_ALLOWED:
        return True, "0x" + _encode_uint(0)  # gate CLOSED on 2026-08-08
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_TOTAL_SUPPLY:
        return True, "0x" + _encode_uint(IMD_SUPPLY_WEI)
    if t == A.POOL_V3.lower() and sel == A.SEL_SLOT0:
        return True, encode_slot0_return()
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_NAME:
        return True, encode_string_return("Identity.md")
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_SYMBOL:
        return True, encode_string_return("IMD")
    if t == surf_client.MULTICALL3.lower() and sel == surf_client._SEL_GET_BLOCK_NUMBER:
        # Multicall3 answering about itself — the eighth leg, so the state and
        # the height it was read at are the same round trip.
        return True, "0x" + _encode_uint(HEAD_BLOCK)
    return False, "0x"


def _chain_state_handler(
    subcall=_chain_state_subcall,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == surf_client.MULTICALL3.lower()
        inner = decode_aggregate3_calldata(call["data"])
        result = encode_aggregate3_result(
            [subcall(t, cd) for (t, _allow, cd) in inner]
        )
        return httpx.Response(200, json=_rpc_ok(payload, result))

    return handler


@pytest.mark.asyncio
async def test_fetch_chain_state_one_multicall_real_values():
    transport = RecordingTransport(_chain_state_handler())
    async with _client_on(transport) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.lp_liquidity == LP_LIQUIDITY
    assert state.lp_token0 == A.WETH.lower()
    assert state.lp_token1 == A.IMD_TOKEN.lower()
    assert state.lp_fee == 10000
    assert state.lp_tokens_owed0_wei == 7_345_000_000_000_000_000
    assert state.lp_tokens_owed1_wei == 30_784_000_000_000_000_000_000
    assert state.lp_owner == A.OPS_WALLET.lower()
    assert state.identity_allowed is False        # closed, NOT None
    assert state.imd_supply_wei == IMD_SUPPLY_WEI
    assert state.sqrt_price_x96 == SQRT_PRICE_X96
    assert state.pool_tick == POOL_TICK
    assert state.imd_name == "Identity.md"
    assert state.imd_symbol == "IMD"
    assert state.block_number == HEAD_BLOCK       # the eighth sub-call
    assert len(transport.requests) == 1           # ONE eth_call round


@pytest.mark.asyncio
async def test_fetch_chain_state_derives_both_lp_side_amounts():
    """PRD §5 hero keys `lp_imd` / `lp_weth` — this is their only producer.

    The captured position is full range (tickLower/Upper = ∓887200), where the
    general v3 formula collapses to L/√P and L·√P; asserting against that
    closed form proves the general implementation is right *here* while the
    concentrated case below proves it is not a hardcoded shortcut.  Sides are
    mapped by ADDRESS (token0 == WETH), never by index: this pool happens to
    order WETH first, and the next one need not.
    """
    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()

    q96 = 1 << 96
    assert state.lp_weth_wei == pytest.approx(LP_LIQUIDITY * q96 / SQRT_PRICE_X96, rel=1e-9)
    assert state.lp_imd_wei == pytest.approx(LP_LIQUIDITY * SQRT_PRICE_X96 / q96, rel=1e-9)
    # And they are wei ints, not floats: the models are wei-native and WP4
    # divides exactly once (WP0.4 test_wei_fields_are_named_wei).
    assert isinstance(state.lp_imd_wei, int) and isinstance(state.lp_weth_wei, int)


@pytest.mark.asyncio
async def test_lp_side_amounts_use_the_real_range_not_the_full_range_shortcut():
    """The day signal 2 fires, the LP is re-added — very likely concentrated.

    A narrower range holds strictly less of both tokens for the same L, and a
    range entirely below spot is 100 % token1.  A full-range shortcut
    (L/√P, L·√P) passes the test above and fails both of these, which is why
    `_decode_positions` must keep `tick_lower` / `tick_upper`.
    """
    def narrow(target, calldata, *, lo, hi):
        sel = "0x" + _strip0x(calldata)[:8]
        if target.lower() == A.NFPM.lower() and sel == A.SEL_POSITIONS:
            return True, encode_positions_return(tick_lower=lo, tick_upper=hi)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(
        lambda t, cd: narrow(t, cd, lo=78000, hi=80000)
    ))) as client:
        inside = await client.fetch_chain_state()

    q96 = 1 << 96
    assert 0 < inside.lp_weth_wei < LP_LIQUIDITY * q96 / SQRT_PRICE_X96
    assert 0 < inside.lp_imd_wei < LP_LIQUIDITY * SQRT_PRICE_X96 / q96

    # Range entirely BELOW spot (tick 79188): the position is all token1 = IMD.
    async with _client_on(RecordingTransport(_chain_state_handler(
        lambda t, cd: narrow(t, cd, lo=60000, hi=70000)
    ))) as client:
        below = await client.fetch_chain_state()
    assert below.lp_weth_wei == 0     # a REAL zero — the side holds nothing.
    assert below.lp_imd_wei > 0       # (None here would mean "read failed".)


@pytest.mark.asyncio
async def test_lp_side_amounts_are_none_when_any_input_is_missing():
    """No half-derivation.  With slot0 dead we have L but no √P, and an amount
    computed from a missing price is a number nobody can distinguish from a
    real one — the exact shape of the false-BURN bug in PRD §6 rule 1."""
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_SLOT0:
            return False, "0x"
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state.lp_liquidity == LP_LIQUIDITY   # the leg that worked
    assert state.sqrt_price_x96 is None
    assert state.lp_imd_wei is None and state.lp_weth_wei is None


@pytest.mark.asyncio
async def test_fetch_chain_state_uses_exactly_the_frozen_kwargs():
    """The contract freeze, asserted where it can actually bite.

    ``ChainState`` is constructed by keyword in one place; WP0.4 owns the names.
    Comparing against ``CONSTRUCTOR_KWARGS`` here turns a rename in either
    direction into a red test rather than a TypeError at the first live refresh
    — and, worse, a WP4 ``getattr(state, "lp_imd", None)`` that never raises.
    """
    import dataclasses

    from maxpane_dashboard.data.surf_models import ChainState as _CS
    from tests.data.test_surf_models import CONSTRUCTOR_KWARGS

    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()
    assert tuple(f.name for f in dataclasses.fields(_CS)) == CONSTRUCTOR_KWARGS[_CS]
    assert isinstance(state, _CS)


@pytest.mark.asyncio
async def test_fetch_chain_state_decodes_negative_tick_as_signed():
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_SLOT0:
            return True, encode_slot0_return(tick=-79188)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state.pool_tick == -79188  # unsigned decode would give 2**256-79188


@pytest.mark.asyncio
async def test_fetch_chain_state_failed_subcall_is_field_none():
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_TOTAL_SUPPLY:
            return False, "0x"  # allowFailure miss — e.g. a reverted call
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.imd_supply_wei is None       # a 0 here is a 2.37M-token
    assert state.lp_liquidity == LP_LIQUIDITY  # false-BURN — PRD §6 rule 1
    # identityAllowed's real value IS false — prove failure did not leak in:
    assert state.identity_allowed is False


@pytest.mark.asyncio
async def test_fetch_chain_state_block_number_leg_is_none_when_it_fails():
    """`block_number` is the one ChainState field with a default, which is the
    only reason it needs a test of its own.

    A constructor that simply omits it type-checks, constructs, and passes
    WP1.2's `required - passed` check — and hands WP4's `_pool_chain` a chain
    slot whose `block` is `None` on every refresh forever. Here the eighth
    sub-call reverts, so the field is `None` **because the read failed**, and
    the other seven legs still land.
    """
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == surf_client._SEL_GET_BLOCK_NUMBER:
            return False, "0x"
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.block_number is None
    assert state.block_number != 0             # 0 would render as genesis
    assert state.lp_liquidity == LP_LIQUIDITY  # the round survived


@pytest.mark.asyncio
async def test_fetch_chain_state_total_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_chain_state() is None
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_chain_state'`
  (plus `MULTICALL3` and `_SEL_GET_BLOCK_NUMBER` missing).
- [ ] **Minimal implementation.** Add to the module (imports at top:
  `from maxpane_dashboard.data.evm_abi import (decode_address, decode_string, decode_uint,
  encode_aggregate3, encode_call3, strip0x)`; `from maxpane_dashboard.data.surf_models import
  ChainState, …`):

```python
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

#: ``getBlockNumber()`` on Multicall3 itself — recomputed during planning with
#: this repo's keccak, not remembered.  Module-private and defined HERE because
#: WP0's frozen selector surface has no entry for it and WP1 may not edit
#: ``surf_addresses`` (open issue 14 offers WP0 the one-line promotion).
_SEL_GET_BLOCK_NUMBER = "0x42cbb15c"

_POSITIONS_RETURN_WORDS = 12
_SLOT0_RETURN_WORDS = 7


def _decode_int24(word: int) -> int:
    """Two's-complement for the int24 tick returned as a full word."""
    return word - (1 << 256) if word >= 1 << 255 else word


def _decode_positions(raw_hex: str) -> dict | None:
    """positions(uint256) flat 12-word tuple; short return = revert = None."""
    raw = strip0x(raw_hex or "")
    if len(raw) < _POSITIONS_RETURN_WORDS * 64:
        return None
    return {
        "token0": decode_address(raw, 2),
        "token1": decode_address(raw, 3),
        "fee": decode_uint(raw, 4),
        "tick_lower": _decode_int24(decode_uint(raw, 5)),
        "tick_upper": _decode_int24(decode_uint(raw, 6)),
        "liquidity": decode_uint(raw, 7),
        "tokens_owed0": decode_uint(raw, 10),
        "tokens_owed1": decode_uint(raw, 11),
    }


def _decode_slot0(raw_hex: str) -> dict | None:
    raw = strip0x(raw_hex or "")
    if len(raw) < _SLOT0_RETURN_WORDS * 64:
        return None
    return {
        "sqrt_price_x96": decode_uint(raw, 0),
        "tick": _decode_int24(decode_uint(raw, 1)),
    }


_Q96 = 1 << 96
_MAX_TICK = 887272


def _sqrt_ratio_at_tick(tick: int) -> int:
    """``sqrt(1.0001**tick) * 2**96`` — the range edge in Q64.96.

    Deliberately NOT Uniswap's 256-bit bit-shift ladder: that exists so a
    *contract* can be exact in integer arithmetic, and porting it is a
    well-known source of transcription bugs. A float pow is accurate to about
    1e-12 relative, which is roughly a millionth of the last digit this
    dashboard ever prints (four decimals of a 388,421-token side). Read-only,
    display-only, and the exactness that matters — ``liquidity`` and
    ``sqrtPriceX96`` — comes off the chain untouched.
    """
    tick = max(-_MAX_TICK, min(_MAX_TICK, int(tick)))
    return int(math.exp(tick * math.log(1.0001) / 2) * _Q96)


def _position_amounts_wei(
    liquidity: int | None,
    sqrt_price_x96: int | None,
    tick_lower: int | None,
    tick_upper: int | None,
) -> tuple[int | None, int | None]:
    """``(amount0_wei, amount1_wei)`` currently held by an v3 position.

    Any missing input yields ``(None, None)``: an amount derived from a failed
    price read is indistinguishable from a real one on screen, and this pair
    feeds the LP MIGRATION hero row.

    The general formula — the full-range shortcut ``L/√P`` / ``L·√P`` is only
    its limit case, and the LP is expected to be re-added concentrated:

        √P clamped into [√a, √b]
        amount0 = L · 2**96 · (√b − √P) / (√P · √b)
        amount1 = L · (√P − √a) / 2**96

    An in-range side that genuinely holds nothing is ``0``; that is a value,
    not a failure (a position parked entirely below spot is 100 % token1).
    """
    if None in (liquidity, sqrt_price_x96, tick_lower, tick_upper):
        return None, None
    if sqrt_price_x96 <= 0 or tick_lower >= tick_upper:
        return None, None
    sa = _sqrt_ratio_at_tick(tick_lower)
    sb = _sqrt_ratio_at_tick(tick_upper)
    sp = max(sa, min(sb, sqrt_price_x96))
    amount0 = (liquidity * _Q96 * (sb - sp)) // (sp * sb) if sp * sb else 0
    amount1 = (liquidity * (sp - sa)) // _Q96
    return amount0, amount1
```

  `math` joins the module imports. Two traps worth stating once: the clamp of `√P` into the
  range is what makes an out-of-range position single-sided (drop it and a position parked
  below spot reports a negative WETH side), and `tick_lower >= tick_upper` is a decode failure,
  not a zero-width position — `positions()` never returns one.

  and the method (inside `SurfClient`):

```python
    async def fetch_chain_state(self) -> ChainState | None:
        """The fast-tier eth_call round: one aggregate3 over eight views.

        Sub-call order is positional and mirrored in the decode below.
        Every sub-call is ``allowFailure=True``: a single reverted view
        degrades one field to ``None``, never the round.

        The eighth sub-call is Multicall3's own ``getBlockNumber()``, which is
        how ``ChainState.block_number`` gets a producer without a second round
        trip. Reading the height inside the same ``eth_call`` also makes it
        *the* height of this state: fetch it separately and a reorg or a
        rotated endpoint can hand back a block the other seven never saw.
        """
        calls = [
            (A.NFPM, A.SEL_POSITIONS + encode_uint(A.LP_POSITION_ID)),
            (A.NFPM, A.SEL_OWNER_OF + encode_uint(A.LP_POSITION_ID)),
            (A.IDENTITY_REGISTRY, A.SEL_IDENTITY_ALLOWED),
            (A.IMD_TOKEN, A.SEL_TOTAL_SUPPLY),
            (A.POOL_V3, A.SEL_SLOT0),
            (A.IMD_TOKEN, A.SEL_NAME),
            (A.IMD_TOKEN, A.SEL_SYMBOL),
            (MULTICALL3, _SEL_GET_BLOCK_NUMBER),
        ]
        # NOTE the tuple order evm_abi.encode_aggregate3 actually takes:
        # (target, callData, allowFailure) -- NOT (target, allow, data).
        data = encode_aggregate3(
            [(target, calldata, True) for target, calldata in calls]
        )
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": data}, "latest"]
            )
        except RuntimeError as exc:
            logger.warning("fetch_chain_state: %s", exc)
            return None
        results = decode_aggregate3_result(raw or "0x")
        if len(results) != len(calls):
            logger.warning("fetch_chain_state: short aggregate3 reply")
            return None

        def ok(i: int) -> str | None:
            success, ret = results[i]
            return ret if success and strip0x(ret) else None

        pos = _decode_positions(ok(0)) if ok(0) else None
        owner_raw = ok(1)
        gate_raw = ok(2)
        supply_raw = ok(3)
        slot0 = _decode_slot0(ok(4)) if ok(4) else None
        name_raw, sym_raw = ok(5), ok(6)
        block_raw = ok(7)

        # The two LP side amounts (PRD §5 `lp_imd` / `lp_weth`).  Mapped by
        # ADDRESS: this pool orders WETH as token0, but trusting the index
        # instead of the address is how a dashboard prints 142 IMD and 388k
        # WETH the first time a pool is deployed the other way round.
        amount0, amount1 = _position_amounts_wei(
            pos["liquidity"] if pos else None,
            slot0["sqrt_price_x96"] if slot0 else None,
            pos["tick_lower"] if pos else None,
            pos["tick_upper"] if pos else None,
        )
        weth_wei = imd_wei = None
        if pos and (pos["token0"] or "").lower() == A.WETH.lower():
            weth_wei, imd_wei = amount0, amount1
        elif pos and (pos["token1"] or "").lower() == A.WETH.lower():
            imd_wei, weth_wei = amount0, amount1
        else:
            logger.warning(
                "fetch_chain_state: position %s is not a WETH pair (%s/%s) — "
                "LP sides unavailable",
                A.LP_POSITION_ID,
                pos and pos["token0"], pos and pos["token1"],
            )

        # Keyword names are WP0.4's CONSTRUCTOR_KWARGS[ChainState], verbatim.
        return ChainState(
            lp_imd_wei=imd_wei,
            lp_weth_wei=weth_wei,
            lp_liquidity=pos["liquidity"] if pos else None,
            lp_token0=pos["token0"] if pos else None,
            lp_token1=pos["token1"] if pos else None,
            lp_fee=pos["fee"] if pos else None,
            lp_tokens_owed0_wei=pos["tokens_owed0"] if pos else None,
            lp_tokens_owed1_wei=pos["tokens_owed1"] if pos else None,
            lp_owner=decode_address(owner_raw) if owner_raw else None,
            identity_allowed=(
                None if gate_raw is None else decode_uint(gate_raw, 0) != 0
            ),
            imd_supply_wei=(
                None if supply_raw is None else decode_uint(supply_raw, 0)
            ),
            sqrt_price_x96=slot0["sqrt_price_x96"] if slot0 else None,
            pool_tick=slot0["tick"] if slot0 else None,
            imd_name=decode_string(name_raw) if name_raw else None,
            imd_symbol=decode_string(sym_raw) if sym_raw else None,
            block_number=(
                None if block_raw is None else decode_uint(block_raw, 0)
            ),
        )
```

  Two `evm_abi` signatures that are easy to get backwards and *will* produce a node-side
  "cannot unmarshal" rather than a Python error: `encode_aggregate3` takes
  `(target, callData, allowFailure)` tuples (verified in
  `maxpane_dashboard/data/evm_abi.py:217`), and `encode_uint(value) -> str` returns an
  **unprefixed 64-hex word**, so `SEL + encode_uint(id)` is the whole calldata. Also
  `decode_string` is typed `-> str | None`; the `ChainState` name/symbol fields absorb that
  `None` unchanged (a token whose name fails to decode is unnamed, not `""`).
- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the signed-tick test bites:** in `_decode_int24`, change the body to
  `return word` — `test_fetch_chain_state_decodes_negative_tick_as_signed` goes red with the
  astronomically wrong `2**256 - 79188`. Restore, green.
- [ ] **Prove the LP-side tests bite** (decoder-shaped code, house rule — two mutations,
  because the two failure modes are different):
  1. Replace the body of `_position_amounts_wei` with the full-range shortcut
     `return liquidity * _Q96 // sqrt_price_x96, liquidity * sqrt_price_x96 // _Q96` —
     `test_fetch_chain_state_derives_both_lp_side_amounts` still passes (that is the point of
     having two tests) while
     `test_lp_side_amounts_use_the_real_range_not_the_full_range_shortcut` goes red on the
     below-spot case. Restore.
  2. Swap the side mapping to positional (`weth_wei, imd_wei = amount0, amount1`
     unconditionally) and flip the fixture so `token0` is `A.IMD_TOKEN` — the first LP test
     goes red with the two sides transposed. Restore, green.
- [ ] **Prove the `block_number` producer bites:** delete the `block_number=` line from the
  `ChainState(...)` call and the eighth entry from `calls`. Nothing raises — the field has a
  default — and WP1.2's freeze test stays green, which is precisely why this mutation is
  listed. `test_fetch_chain_state_one_multicall_real_values` must go red on
  `None != 25707884`. Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.4 fetch_chain_state — aggregate3 round, owner, signed tick, LP side amounts, read height"`

---

### Task WP1.5: `fetch_channel_txs()` — the announcement feed bodies

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py` (uses `announce_txs_page1.json`)

**Interfaces:**
- Consumes: `surf_models.ChannelTx` — restated from WP0.4's
  `CONSTRUCTOR_KWARGS[ChannelTx]`, in order: `tx_hash: str`, `ts: float`,
  `nonce: int | None`, `from_addr: str`, `to_addr: str | None`, `value_wei: int`,
  `input_hex: str`, `method: str | None = None`. Addresses lowercase, `ts` epoch seconds UTC.
  **`ChannelTx` carries no `kind` and no `text`**, because classification and UTF-8 decoding
  are WP2's pure functions called by WP4 (see *Design decisions* above: the client does no
  signal math and no message decoding). The rule that decides this — and that decides
  `DevTx` the other way — is in the header's ownership table: a derived field is filled where
  **WP0.4's constructor forces it to be**. `ChannelTx` has no `kind`/`text` field at all, so
  nothing is forced and WP4 derives; `DevTx` declares three such fields without defaults, so
  WP1.6 must fill them. The channel body is already sitting in `input_hex`, so the manager
  hands it straight to `decode_utf8_calldata`, which is what gives that decoder's
  hostile-input table exactly one caller to test.
- Produces: `async fetch_channel_txs() -> list[ChannelTx] | None`; helpers
  `_parse_iso_ts(ts: str) -> float | None` and `_lenient_int(value: Any) -> int | None`.

  `_lenient_int` exists for one field and one reason. WP0.4 types `ChannelTx.nonce`
  `int | None`, and **`0` is a real nonce on this channel** — it is the genesis "soon" post.
  So a row where Blockscout omits or nulls `nonce` must become `None`, never `0`: an
  `int(row.get("nonce") or 0)` makes every unreadable row impersonate the first post the
  channel ever made, and the impersonation is silent because 0 is a value the feed genuinely
  expects to see. This is the repo-wide "a failed read is `None`, never `0`" rule at the one
  place a sibling test in this very suite already enforces it
  (`test_fetch_nonces_partial_batch_error_is_field_none_never_zero`), and it is the same rule
  `_parse_dev_tx` already follows for `to_addr` / `created_contract` with `… or None`.

- [ ] **Write the failing tests** (every expected value read out of the fixture — 21 rows,
  epoch values derived via `datetime.fromisoformat`):

```python
# ---------------------------------------------------------------------------
# WP1.5 — fetch_channel_txs
# ---------------------------------------------------------------------------


def _blockscout_handler(
    pages: dict[str, list[dict]],
) -> Callable[[httpx.Request], httpx.Response]:
    """Maps '/addresses/{addr}/transactions' path fragments to page lists.

    Each page list is served in order: first GET gets pages[addr][0], the
    second (with next_page_params echoed as query args) pages[addr][1], etc.
    """
    served: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for addr, plist in pages.items():
            if f"/addresses/{addr}" in path and path.endswith("/transactions"):
                i = served.get(addr, 0)
                served[addr] = i + 1
                return httpx.Response(200, json=plist[min(i, len(plist) - 1)])
        raise AssertionError(f"unexpected Blockscout path: {path}")

    return handler


@pytest.mark.asyncio
async def test_fetch_channel_txs_parses_the_full_page():
    fixture = load_fixture("announce_txs_page1.json")
    handler = _blockscout_handler({A.ANNOUNCE: [fixture]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()
    assert txs is not None and len(txs) == 21

    # Newest self-post: nonce 13, the 33-ETH LP announcement (2026-08-07).
    head = txs[0]
    assert head.nonce == 13
    assert head.from_addr == A.ANNOUNCE.lower()
    assert head.to_addr == A.ANNOUNCE.lower()
    assert head.ts == 1786076831.0  # 2026-08-07T04:27:11Z
    assert head.tx_hash.startswith("0xe397869a")
    assert head.input_hex.startswith("0x49206d6f766564")  # "I moved" — raw,
    # undecoded: UTF-8 decoding is analytics/surf_signals.py's job (WP2).

    # The register() action: to = ERC-8004 registry, method preserved.
    reg = [t for t in txs if t.tx_hash.startswith("0xa4ce159e")][0]
    assert reg.from_addr == A.ANNOUNCE.lower()
    assert reg.to_addr == A.ERC8004_REGISTRY.lower()
    assert reg.method == "register"
    assert reg.input_hex.startswith("0xf2c298be")

    # The funding tx: from the dev wallet, 0.054 ETH, empty calldata.
    fund = [t for t in txs if t.tx_hash.startswith("0x632f5dc3")][0]
    assert fund.from_addr == A.DEV_WALLET.lower()
    assert fund.value_wei == 54_000_000_000_000_000
    assert fund.input_hex == "0x"

    # A community reply keeps its own sender (permissionless channel).
    pasta = [t for t in txs if t.tx_hash.startswith("0xdcb8bf92")][0]
    assert pasta.from_addr == "0x1c3a0ad54418fe843953c71df23637de732ce159"
    assert pasta.to_addr == A.ANNOUNCE.lower()


@pytest.mark.asyncio
async def test_fetch_channel_txs_follows_next_page_params_once_per_page():
    fixture = load_fixture("announce_txs_page1.json")
    nxt = {"block_number": 25108773, "index": 224, "items_count": 50}
    page1 = {"items": fixture["items"][:11], "next_page_params": nxt}
    page2 = {"items": fixture["items"][11:], "next_page_params": None}
    transport = RecordingTransport(_blockscout_handler({A.ANNOUNCE: [page1, page2]}))
    async with _client_on(transport) as client:
        txs = await client.fetch_channel_txs()
    assert len(txs) == 21
    assert len(transport.requests) == 2
    # The second GET must carry the server's cursor verbatim as query params.
    second_url = transport.urls()[1]
    assert "block_number=25108773" in second_url and "index=224" in second_url


@pytest.mark.asyncio
async def test_fetch_channel_txs_page_growth_is_bounded():
    """A server that always hands back a cursor must not be followed forever."""
    fixture = load_fixture("announce_txs_page1.json")
    endless = {"items": fixture["items"][:7],
               "next_page_params": {"block_number": 1, "index": 1}}
    transport = RecordingTransport(_blockscout_handler({A.ANNOUNCE: [endless]}))
    async with _client_on(transport) as client:
        txs = await client.fetch_channel_txs()
    assert txs is not None
    assert len(transport.requests) == surf_client.MAX_CHANNEL_PAGES


@pytest.mark.asyncio
async def test_channel_tx_unreadable_nonce_is_none_never_the_genesis_post():
    """`0` is a real nonce here — the channel's first post, the "soon" tx.

    So a row whose `nonce` Blockscout omits or nulls may not be coerced to 0:
    it would silently impersonate that post, and every consumer that keys on
    nonce (the feed's ordering, WP2's new-post detector's baseline) would see
    two rows claiming to be the same tx. `None` says "unread", which is what it
    is. `_parse_dev_tx` already does exactly this for its own optional fields.
    """
    fixture = load_fixture("announce_txs_page1.json")
    rows = [dict(r) for r in fixture["items"][:3]]
    rows[0]["nonce"] = None            # Blockscout nulls it
    rows[1].pop("nonce", None)         # …or omits it entirely
    rows[2]["nonce"] = 0               # …and a genuine 0 must survive as 0
    page = {"items": rows, "next_page_params": None}

    handler = _blockscout_handler({A.ANNOUNCE: [page]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()

    assert len(txs) == 3
    assert txs[0].nonce is None and txs[0].nonce != 0
    assert txs[1].nonce is None
    assert txs[2].nonce == 0          # a read that worked and said zero


@pytest.mark.asyncio
async def test_channel_tx_contract_creation_has_to_addr_none_not_empty_string():
    """WP0.4 types `to_addr` `str | None`; a creation has no `to`.

    `""` is a third state nobody declared: it is falsy like `None` but is a
    `str`, so `str(to_addr or "")` in WP4 and `_addr("")` in WP2 both keep
    working while `to_addr is None` — the check WP2's classifier documents for
    "``to = None`` (a deployment)" — quietly stops matching.
    """
    fixture = load_fixture("announce_txs_page1.json")
    row = dict(fixture["items"][0])
    row["to"] = None
    page = {"items": [row], "next_page_params": None}

    handler = _blockscout_handler({A.ANNOUNCE: [page]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()
    assert len(txs) == 1
    assert txs[0].to_addr is None
    assert txs[0].to_addr != ""


@pytest.mark.asyncio
async def test_fetch_channel_txs_outage_returns_none_not_empty_list():
    async with _offline_client() as client:
        result = await client.fetch_channel_txs()
    assert result is None  # [] would mean "the channel is empty" — a lie
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_channel_txs'`.
- [ ] **Minimal implementation:**

```python
def _parse_iso_ts(ts: str | None) -> float | None:
    """Blockscout ISO-8601 ('2026-08-07T04:27:11.000000Z') -> epoch seconds."""
    if not ts:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _lenient_int(value: Any) -> int | None:
    """A Blockscout scalar that may be ``int``, ``str``, missing or ``null``.

    ``None`` for anything unreadable — **never** ``0``. The field this exists
    for is ``ChannelTx.nonce``, where ``0`` is a real value (the channel's
    genesis "soon" post), so ``int(row.get("nonce") or 0)`` would make every
    unreadable row impersonate it. ``bool`` is rejected for the same reason
    WP2's ``_as_int`` rejects it: ``True`` is never a nonce, and reading it as
    ``1`` turns a broken payload into a plausible number.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 10)
        except ValueError:
            return None
    return None
```

  (put the `datetime` import at module top, shown inline here for locality) and in the class:

```python
    async def _blockscout_tx_pages(
        self, address: str, max_pages: int
    ) -> list[dict] | None:
        """All tx rows for *address*, following next_page_params, bounded."""
        url = f"{self._blockscout}/addresses/{address}/transactions"
        rows: list[dict] = []
        params: dict | None = None
        for _page in range(max_pages):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return rows or None  # partial > nothing; None only if empty
            rows.extend(body["items"])
            nxt = body.get("next_page_params")
            if not nxt:
                break
            params = nxt  # the server cursor, verbatim, as query params
        return rows

    @staticmethod
    def _parse_channel_tx(row: dict) -> ChannelTx | None:
        ts = _parse_iso_ts(row.get("timestamp"))
        tx_hash = row.get("hash")
        from_addr = ((row.get("from") or {}).get("hash") or "").lower()
        # `or None`, exactly as _parse_dev_tx does it: WP0.4 types this field
        # `str | None`, and a contract creation has no `to`.  "" would be a
        # third state nobody declared — falsy like None, but a str, so a
        # downstream `to_addr is None` check stops matching in silence.
        to_addr = ((row.get("to") or {}).get("hash") or "").lower() or None
        if ts is None or not tx_hash or not from_addr:
            return None  # a malformed row is dropped, never zero-filled
        try:
            value_wei = int(row.get("value") or "0")
        except (TypeError, ValueError):
            return None
        return ChannelTx(
            ts=ts,
            # NOT `int(... or 0)`: nonce 0 is the channel's genesis "soon" post,
            # so a missing nonce coerced to 0 impersonates a real tx.
            nonce=_lenient_int(row.get("nonce")),
            from_addr=from_addr,
            to_addr=to_addr,
            value_wei=value_wei,
            input_hex=row.get("raw_input") or "0x",
            tx_hash=tx_hash,
            method=row.get("method"),
        )

    async def fetch_channel_txs(self) -> list[ChannelTx] | None:
        """Every tx touching the announce channel, newest first, RAW.

        No decoding, no classification here: the channel is permissionless
        and attacker-writable; interpretation is pure-function work in
        analytics/surf_signals.py where it is table-tested (PRD §6 rule 4).
        """
        rows = await self._blockscout_tx_pages(A.ANNOUNCE, MAX_CHANNEL_PAGES)
        if rows is None:
            return None
        parsed = [self._parse_channel_tx(r) for r in rows]
        return [p for p in parsed if p is not None]
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the pagination test bites:** in `_blockscout_tx_pages`, replace `params = nxt`
  with `params = None` — `test_fetch_channel_txs_follows_next_page_params_once_per_page` goes
  red on the query-param assertion. Restore, green.
- [ ] **Prove the nonce test bites** (decoder-shaped, and the failure it prevents is silent):
  change `nonce=_lenient_int(row.get("nonce"))` back to `nonce=int(row.get("nonce") or 0)` —
  `test_channel_tx_unreadable_nonce_is_none_never_the_genesis_post` goes red twice, on
  `0 is not None` for both the nulled and the omitted row, while every other test in the file
  stays green. Restore, green.
- [ ] **Prove the `to_addr` test bites:** drop the trailing `or None` —
  `test_channel_tx_contract_creation_has_to_addr_none_not_empty_string` goes red on `'' != None`.
  Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.5 fetch_channel_txs — Blockscout pages, bounded cursor follow, raw rows, None-not-zero nonce"`

---

### Task WP1.6: `fetch_dev_activity()` — the poisoning filter, the label lookup, the kind vocabulary

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py` (uses `dev_txs_page1.json`, `ops_txs_page1.json`)

**This task owns the address-poisoning defense** (PRD §4 counterparty rendering, §6 rule 5),
because WP0.4's `DevTx` declares `counterparty`, `counterparty_label` and `kind` without
defaults — they can only be filled where the row is constructed. Downstream re-checks are
defence in depth, not the rule: if this task ships without the filter, the six live dust spoofs
render as ordinary activity rows. See the ownership table in the header.

**Interfaces:**
- Consumes: `surf_models.DevTx` — WP0.4's frozen field list, in order: `tx_hash: str`,
  `ts: float`, `wallet_label: str`, `from_addr: str`, `to_addr: str | None`,
  `counterparty: str`, `counterparty_label: str | None`, `value_wei: int`,
  `method: str | None`, `kind: str`, `created_contract: str | None = None`;
  `surf_addresses.DEV_WALLET / OPS_WALLET / KNOWN_LABELS / NFPM / BURN_EXECUTOR /
  FWA_SPLITTER / RELAY_DEPOSITORY`; `_blockscout_tx_pages` from WP1.5.
- Produces: `async fetch_dev_activity() -> list[DevTx] | None` — merged rows of both wallets,
  newest first, **already filtered and labelled**; module constants
  `DEV_TX_KINDS: frozenset[str]`, `_DEV_WALLET_LABELS: dict[str, str]`,
  `_DUST_WEI: int = 10**9`; helpers
  `_classify_dev_kind(row, to_addr, created) -> str` and `_label_for(addr) -> str | None`.

**The three rules, and why they are one mechanism:**

1. **Sender keying (primary).** A row is built only when `from == the wallet whose page it
   came from`. PRD §6.5 is explicit that the builder keys on the sender and never on "appears
   in the wallet's transfer list", because appearing in that list is precisely what an attacker
   can buy for 1 gwei. This drops all 17 inbound rows across the two captured pages.
2. **Dust drop (PRD §4).** Inbound transfers ≤ `_DUST_WEI` from unknown senders are dropped.
   Rule 1 strictly subsumes rule 2 — every dust row is inbound — so implement **rule 1 only**
   and do not add a dust branch that can never execute. A branch no input can reach is dead
   code that reads like a defense; the test below asserts the six dust rows are gone *and* the
   mutation check proves rule 1 is what removed them. `_DUST_WEI` stays as the documented
   threshold for whoever later wants to surface inbound rows deliberately.
3. **Allowlist labels.** `counterparty_label` is `KNOWN_LABELS.get(counterparty)` — an
   allowlist, never a heuristic. Unknown stays `None`, and WP5 renders it dimmed and
   truncated. A lookalike therefore cannot inherit its target's label no matter how many
   leading hex characters it matches.

`counterparty` is the *other* side of the tx: `to_addr` for a normal call, and
`created_contract` for a deployment (where `to` is null). An earlier draft of this task
invented `DevTx(wallet=…, nonce=…)`, which are not WP0.4 names and would not construct at all.

- [ ] **Write the failing tests:**

```python
# ---------------------------------------------------------------------------
# WP1.6 — fetch_dev_activity
# ---------------------------------------------------------------------------


# The six live ≤1-gwei dust senders on the two captured pages.  Each shares
# its target's first four and last four hex characters — which is exactly what
# a truncated `0x1234…abcdef` rendering shows.  WP0 pins three of them in
# LIVE_SPOOFS; these are all six, across both wallets.
LIVE_DUST_SENDERS = {
    "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",  # ~ LP_FEE_SINK_B
    "0xf3083828702c1989710ceca517412071c2f60ee6",  # ~ LP_FEE_SINK_A
    "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",  # ~ LP_FEE_SINK_A
    "0x5823d93a369b0aebd798e4557196f23927d84e55",  # ~ DEV_SWEEP
    "0xa4ad23e725bb527dd5cae35b6aa985e7867d5717",  # no cast match, still dust
}


@pytest.mark.asyncio
async def test_fetch_dev_activity_merges_both_wallets_real_rows():
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
    # 80 captured rows; 17 are inbound and never become DevTx rows.
    assert rows is not None and len(rows) == 63

    # The 2026-08-07 33-ETH LP add (ops wallet, multicall to NFPM).
    lp = [r for r in rows if r.tx_hash.startswith("0x90a0f8e2")][0]
    assert lp.wallet_label == "ops"
    assert lp.from_addr == A.OPS_WALLET.lower()
    assert lp.to_addr == A.NFPM.lower()
    assert lp.method == "multicall"
    assert lp.kind == "lp"
    assert lp.value_wei == 33_252_659_725_872_729_307
    assert lp.ts == 1786076603.0  # 2026-08-07T04:23:23Z
    # Labelled from the allowlist, not from any string in the payload.
    assert lp.counterparty == A.NFPM.lower()
    assert lp.counterparty_label == A.KNOWN_LABELS[A.NFPM.lower()]

    # The dev-wallet FWA splitter claims — 12 of them on this page.
    claims = [r for r in rows if r.kind == "fwa claim"]
    assert len(claims) == 12
    assert all(r.counterparty == A.FWA_SPLITTER.lower() for r in claims)
    assert all(r.counterparty_label == "FWA Splitter" for r in claims)

    # Newest-first across the merge.
    assert all(rows[i].ts >= rows[i + 1].ts for i in range(len(rows) - 1))


@pytest.mark.asyncio
async def test_the_kind_vocabulary_matches_the_captured_pages():
    """PRD §4: deploy / LP / burn / bridge / FWA claim / transfer / other.

    Counts are derived from the two capture files, not chosen.  Re-derive them
    from `tests/fixtures/surf/captures/` if a fixture is ever re-sliced.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    counts = Counter(r.kind for r in rows)
    assert counts == Counter({
        "other": 33, "fwa claim": 12, "transfer": 8,
        "lp": 5, "burn": 3, "bridge": 2,
    })
    # Every kind is from the closed vocabulary — a Blockscout `method` string
    # never reaches the widget's label column.  It is attacker-influenced
    # (anyone can deploy a contract with a chosen function name) and unbounded
    # in width.
    assert set(counts) <= surf_client.DEV_TX_KINDS


@pytest.mark.asyncio
async def test_a_deploy_row_is_labelled_from_created_contract():
    """No page in the captures holds a deployment, so this row is synthetic.

    It is the shape PRD §3 signal 4 fires on (the ERC-8004 registration was
    exactly this), and `to` is null on a real deploy — the counterparty has to
    come from `created_contract` or the row renders blank.
    """
    page = load_fixture("dev_txs_page1.json")
    row = dict(page["items"][0])
    row |= {
        "hash": "0x" + "de" * 32,
        "to": None,
        "method": None,
        "created_contract": {"hash": "0x" + "c0" * 20},
    }
    handler = _blockscout_handler(
        {A.DEV_WALLET: [{"items": [row], "next_page_params": None}]}
    )
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    assert len(rows) == 1
    assert rows[0].kind == "deploy"
    assert rows[0].counterparty == "0x" + "c0" * 20
    assert rows[0].counterparty_label is None      # a fresh deploy is unknown


@pytest.mark.asyncio
async def test_poisoning_dust_never_becomes_an_activity_row():
    """PRD §4 + §6.5 — the whole point of the sender keying.

    Six live ≤1-gwei transfers from lookalike addresses sit in these two
    captures today.  Every one of them is inbound, so keying on the sender
    removes all six; none may appear as a row, and none may borrow the label
    of the address it imitates.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    senders = {r.from_addr for r in rows}
    assert senders == {A.DEV_WALLET.lower(), A.OPS_WALLET.lower()}
    assert not (senders & LIVE_DUST_SENDERS)
    # …and the spoofs did not sneak in on the counterparty side either.
    assert not ({r.counterparty for r in rows} & LIVE_DUST_SENDERS)

    # The real fee sinks the spoofs imitate ARE labelled — proving the test
    # discriminates by address and not by "anything that looks like a sink".
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_A.lower()] == "LP-fee sink A"
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_B.lower()] == "LP-fee sink B"


@pytest.mark.asyncio
async def test_an_unknown_counterparty_is_never_labelled():
    """The allowlist has no fallback.  USDT is a real, frequent counterparty
    on the ops page and is deliberately not in the cast: it must stay None so
    WP5 renders it dimmed rather than as a trusted name."""
    handler = _blockscout_handler(
        {A.OPS_WALLET: [load_fixture("ops_txs_page1.json")]}
    )
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    usdt = [r for r in rows
            if r.counterparty == "0xdac17f958d2ee523a2206206994597c13d831ec7"]
    assert usdt, "the ops page holds USDT transfers"
    assert all(r.counterparty_label is None for r in usdt)
    assert all(
        r.counterparty_label is None
        for r in rows if r.counterparty not in A.KNOWN_LABELS
    )


@pytest.mark.asyncio
async def test_fetch_dev_activity_one_wallet_down_is_partial_not_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if A.OPS_WALLET.lower() in str(request.url).lower():
            return httpx.Response(521, json={})
        return _blockscout_handler(
            {A.DEV_WALLET: [load_fixture("dev_txs_page1.json")]}
        )(request)

    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
    # 30 captured dev rows, 4 of them inbound → 26 survive the sender keying.
    assert rows is not None and len(rows) == 26


@pytest.mark.asyncio
async def test_fetch_dev_activity_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_dev_activity() is None
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_dev_activity'`.
- [ ] **Minimal implementation:**

```python
#: The closed label vocabulary for the activity column (PRD §4).
DEV_TX_KINDS = frozenset(
    {"deploy", "lp", "burn", "bridge", "fwa claim", "transfer", "other"}
)

_DEV_WALLET_LABELS: dict[str, str] = {
    A.DEV_WALLET.lower(): "dev",
    A.OPS_WALLET.lower(): "ops",
}

#: Inbound value at or below this is poisoning bait, not a payment.  Not used
#: by the filter — sender keying already removes every inbound row — and kept
#: as the documented PRD §4 threshold for whoever later surfaces inbound rows
#: deliberately.  See rule 2 in this task.
_DUST_WEI = 10**9


def _label_for(addr: str | None) -> str | None:
    """Allowlist lookup.  No fallback, no fuzzy match, no prefix match."""
    if not addr:
        return None
    return A.KNOWN_LABELS.get(addr.lower())
```

  and in the class:

```python
    @staticmethod
    def _classify_dev_kind(row: dict, to_addr: str | None,
                           created: str | None) -> str:
        """Map one tx onto the closed PRD §4 vocabulary.

        Keyed on the *destination address* wherever possible, because the
        address is what the dashboard trusts (CLAUDE.md: trust the address,
        never the name).  `method` only ever narrows a decision the address
        has already made.
        """
        if created:
            return "deploy"
        if to_addr == A.NFPM.lower():
            return "lp"
        if to_addr == A.BURN_EXECUTOR.lower():
            # bridgeToBaseBurnReceiver(): it bridges in order to burn, and the
            # burn is what signal 6 and the supply sparkline care about.
            return "burn"
        if to_addr == A.RELAY_DEPOSITORY.lower():
            return "bridge"
        if to_addr == A.FWA_SPLITTER.lower() and row.get("method") == "claim":
            return "fwa claim"
        if row.get("method") is None and (row.get("raw_input") or "0x") == "0x":
            return "transfer"
        return "other"

    @classmethod
    def _parse_dev_tx(cls, row: dict, wallet_addr: str) -> DevTx | None:
        """Build one DevTx, or None if this row is not this wallet's own tx.

        The sender check is the address-poisoning defense (PRD §6.5) and it
        lives HERE, at construction, so that no later stage can be handed a
        row that should not exist.  A 1-gwei transfer from a lookalike address
        returns None and never becomes a widget row.
        """
        from_addr = ((row.get("from") or {}).get("hash") or "").lower()
        if from_addr != wallet_addr:
            return None                      # ← the whole poisoning defense

        ts = _parse_iso_ts(row.get("timestamp"))
        tx_hash = row.get("hash")
        if ts is None or not tx_hash:
            return None
        try:
            value_wei = int(row.get("value") or "0")
        except (TypeError, ValueError):
            return None

        to_addr = ((row.get("to") or {}).get("hash") or "").lower() or None
        created = row.get("created_contract") or None
        if isinstance(created, dict):
            created = (created.get("hash") or "").lower() or None
        elif isinstance(created, str):
            created = created.lower() or None

        counterparty = to_addr or created or ""
        return DevTx(
            tx_hash=tx_hash,
            ts=ts,
            wallet_label=_DEV_WALLET_LABELS[wallet_addr],
            from_addr=from_addr,
            to_addr=to_addr,
            counterparty=counterparty,
            counterparty_label=_label_for(counterparty),
            value_wei=value_wei,
            method=row.get("method"),
            kind=cls._classify_dev_kind(row, to_addr, created),
            created_contract=created,
        )

    async def fetch_dev_activity(self) -> list[DevTx] | None:
        """Recent txs of both dev wallets, merged newest-first, filtered and
        labelled.

        Inbound rows — including the six live address-poisoning dust transfers
        sitting in these two wallets' histories today — are dropped here, at
        the only place that still knows *whose page* a row came from.
        """
        dev_rows, ops_rows = await asyncio.gather(
            self._blockscout_tx_pages(A.DEV_WALLET, MAX_ACTIVITY_PAGES),
            self._blockscout_tx_pages(A.OPS_WALLET, MAX_ACTIVITY_PAGES),
        )
        if dev_rows is None and ops_rows is None:
            return None
        out: list[DevTx] = []
        for rows, wallet_addr in (
            (dev_rows, A.DEV_WALLET.lower()),
            (ops_rows, A.OPS_WALLET.lower()),
        ):
            for row in rows or []:
                parsed = self._parse_dev_tx(row, wallet_addr)
                if parsed is not None:
                    out.append(parsed)
        out.sort(key=lambda r: r.ts, reverse=True)
        return out
```

Add `from collections import Counter` to the test module imports.

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the poisoning filter bites** (mandatory — this is the one test standing between
  a spoof and the screen). In `_parse_dev_tx`, relax the sender check to the "appears in the
  wallet's list" rule PRD §6.5 forbids:

```python
        to_addr_probe = ((row.get("to") or {}).get("hash") or "").lower()
        if wallet_addr not in (from_addr, to_addr_probe):
            return None
```

  Run `.venv/bin/python -m pytest tests/data/test_surf_client.py -k "poisoning or merges" -v`
  → `test_poisoning_dust_never_becomes_an_activity_row` FAILS on the sender set (the five
  spoof addresses are back) and `test_fetch_dev_activity_merges_both_wallets_real_rows` FAILS
  on `80 != 63`. Restore, green.
- [ ] **Prove the allowlist bites.** Change `_label_for` to fall back to a prefix match
  (`next((v for k, v in A.KNOWN_LABELS.items() if k[:6] == addr[:6]), None)`) — the shape a
  well-meaning "make more addresses readable" change would take. Run
  `-k "unknown_counterparty"` → FAILS, because those shared prefixes are the whole attack.
  Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.6 fetch_dev_activity — sender-keyed poisoning filter, allowlist labels, closed kind vocabulary"`

---

### Task WP1.7: `fetch_market()` — GeckoTerminal + DexScreener with cross-check

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py` (uses the three market fixtures)

**Interfaces:**
- Consumes: `surf_models.MarketSnapshot` — restated from WP0.4's
  `CONSTRUCTOR_KWARGS[MarketSnapshot]`, in order: `imd_price_usd, imd_price_usd_gecko,
  imd_change_24h_pct, imd_vol_24h_usd, pool_liquidity_usd, pool_imd, pool_weth, fp_price_usd,
  fdv_usd, eth_usd: float | None`; `indexer_name, indexer_symbol: str | None`;
  `sources_agree: bool | None = None`); `surf_addresses.IMD_TOKEN / FP_TOKEN_BASE / POOL_V3`;
  `surf_client.COINGECKO_ETH_URL` — the module constant **defined in WP1.1**, whose URL string
  is copied verbatim from `data/price.py::_COINGECKO_URL` (private there, so it is copied
  rather than imported).
- Produces: `async fetch_market() -> MarketSnapshot | None`. Policy frozen here:
  DexScreener is the display source (its names are current); GeckoTerminal is the
  cross-check; `sources_agree` is `None` unless both answered; FP price = the
  max-liquidity Base pair; **no GeckoTerminal name ever enters the snapshot**.

  **`eth_usd` is filled here**, which settles the question WP4 raised: the flat key `eth_usd`
  is read off `MarketSnapshot`, so this method is what puts it there. Fetch it as a fourth leg
  of the same `asyncio.gather` through **this client's** `_get_json`, not by instantiating
  `data/price.PriceClient` — `PriceClient` builds its own `httpx.AsyncClient`, which would open
  a real socket straight through the injected transport and break
  `test_client_never_opens_a_real_socket`. Note also that `PriceClient.get_eth_usd()`
  **returns `0.0` on failure**; that sentinel must not be copied here. A dead CoinGecko is
  `eth_usd=None`, and every ETH-denominated figure downstream renders unavailable rather than
  free.

- [ ] **Write the failing tests** (values verified against the fixtures in the header table):

```python
# ---------------------------------------------------------------------------
# WP1.7 — fetch_market
# ---------------------------------------------------------------------------


#: ETH/USD as CoinGecko answered on 2026-08-08.  There is no committed capture
#: for this leg (the capture set predates `eth_usd` being a MarketSnapshot
#: field), so it is an inline literal and labelled as one rather than dressed up
#: as fixture-derived.
COINGECKO_ETH_USD = 1917.74


def _market_handler(
    *, dex_imd=True, gecko=True, dex_fp=True, eth=True,
) -> Callable[[httpx.Request], httpx.Response]:
    """Routes ALL FOUR legs `fetch_market` gathers.

    The fourth (CoinGecko) is easy to forget, and forgetting it does not
    degrade anything — ``_get_json`` catches only ``(httpx.HTTPError,
    ValueError)``, so the fallthrough ``AssertionError`` below would escape
    through ``asyncio.gather`` and error every market test instead of failing
    one assertion.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.dexscreener.com" in url and A.IMD_TOKEN.lower() in url.lower():
            if not dex_imd:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("dexscreener_imd.json"))
        if "api.dexscreener.com" in url and A.FP_TOKEN_BASE.lower() in url.lower():
            if not dex_fp:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("dexscreener_fp.json"))
        if "api.geckoterminal.com" in url:
            if not gecko:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("geckoterminal_imd.json"))
        if "coingecko" in url:
            if not eth:
                return httpx.Response(500, json={})
            return httpx.Response(
                200, json={"ethereum": {"usd": COINGECKO_ETH_USD}}
            )
        raise AssertionError(f"unexpected market URL: {url}")

    return handler


@pytest.mark.asyncio
async def test_fetch_market_cross_checked_real_values():
    async with _client_on(RecordingTransport(_market_handler())) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7074)          # DexScreener
    assert snap.imd_price_usd_gecko == pytest.approx(0.7127337345)
    assert snap.sources_agree is True    # 0.751 % diff < 5 % tolerance
    assert snap.imd_change_24h_pct == pytest.approx(30.89)
    assert snap.imd_vol_24h_usd == pytest.approx(244178.0)
    assert snap.pool_liquidity_usd == pytest.approx(548701.21)
    assert snap.pool_imd == pytest.approx(388421.0)
    assert snap.pool_weth == pytest.approx(142.7067)
    assert snap.fdv_usd == pytest.approx(1647147.0)
    # FP parity leg: the MAX-LIQUIDITY Base pair (424,308.81 USD), not the
    # first pair DexScreener happens to order.
    assert snap.fp_price_usd == pytest.approx(0.7274)
    # The fourth leg: eth_usd is a MarketSnapshot field and THIS method fills it
    # (WP4 reads the flat key off the snapshot).  A missing leg here is
    # invisible — the field just stays None forever.
    assert snap.eth_usd == pytest.approx(COINGECKO_ETH_USD)
    # Identity is mutable and GeckoTerminal is STALE ("Vibe Coins"): the
    # snapshot must carry DexScreener's current name and never Gecko's.
    assert snap.indexer_name == "Identity.md"
    assert snap.indexer_symbol == "IMD"


@pytest.mark.asyncio
async def test_fetch_market_gecko_down_degrades_cross_check_not_price():
    async with _client_on(
        RecordingTransport(_market_handler(gecko=False))
    ) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7074)
    assert snap.imd_price_usd_gecko is None
    assert snap.sources_agree is None  # unknown, NOT False and NOT True


@pytest.mark.asyncio
async def test_fetch_market_dexscreener_down_falls_back_to_gecko_price():
    async with _client_on(
        RecordingTransport(_market_handler(dex_imd=False, dex_fp=False))
    ) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7127337345)  # fallback leg
    assert snap.sources_agree is None
    assert snap.fp_price_usd is None
    assert snap.indexer_name is None  # Gecko's stale name must NOT leak in


@pytest.mark.asyncio
async def test_fetch_market_disagreement_is_flagged_not_averaged():
    fixture = load_fixture("dexscreener_imd.json")
    fixture["pairs"][0]["priceUsd"] = "0.90"  # ~23 % off Gecko's 0.7127

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "dexscreener" in url and A.IMD_TOKEN.lower() in url.lower():
            return httpx.Response(200, json=fixture)
        return _market_handler()(request)

    async with _client_on(RecordingTransport(handler)) as client:
        snap = await client.fetch_market()
    assert snap.sources_agree is False
    assert snap.imd_price_usd == pytest.approx(0.90)  # still reported raw


@pytest.mark.asyncio
async def test_fetch_market_coingecko_down_is_none_never_zero():
    """`PriceClient.get_eth_usd()` returns 0.0 on failure. That sentinel must
    not be copied here: an ETH price of 0 makes every ETH-denominated figure
    downstream render as free rather than as unavailable."""
    async with _client_on(RecordingTransport(_market_handler(eth=False))) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.eth_usd is None
    assert snap.eth_usd != 0.0
    assert snap.imd_price_usd == pytest.approx(0.7074)  # the IMD legs survive


@pytest.mark.asyncio
async def test_fetch_market_total_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_market() is None
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_market'`.
- [ ] **Minimal implementation:**

```python
    @staticmethod
    def _pick_imd_pair(body: Any) -> dict | None:
        """The canonical v3 pool's pair, else the deepest pair, else None."""
        pairs = (body or {}).get("pairs") or []
        for p in pairs:
            if str(p.get("pairAddress", "")).lower() == A.POOL_V3.lower():
                return p
        return max(
            pairs,
            key=lambda p: ((p.get("liquidity") or {}).get("usd") or 0.0),
            default=None,
        )

    @staticmethod
    def _f(value: Any) -> float | None:
        """Lenient float parse: None/absent/garbage stays None, never 0."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def fetch_market(self) -> MarketSnapshot | None:
        """IMD + FP market data, DexScreener primary, GeckoTerminal check.

        GeckoTerminal serves a STALE token name for IMD ("Vibe Coins") — its
        numbers are welcome, its strings are not (PRD §6 rule 3).
        """
        dex_body, gecko_body, fp_body, eth_body = await asyncio.gather(
            self._get_json(f"{DEXSCREENER_TOKENS_API}/{A.IMD_TOKEN}"),
            self._get_json(GECKO_TOKEN_API.format(address=A.IMD_TOKEN.lower()),
                           params={"include": "top_pools"}),
            self._get_json(f"{DEXSCREENER_TOKENS_API}/{A.FP_TOKEN_BASE}"),
            self._get_json(COINGECKO_ETH_URL),
        )
        eth_usd = self._f(((eth_body or {}).get("ethereum") or {}).get("usd"))

        pair = self._pick_imd_pair(dex_body)
        gecko_price = None
        gecko_pool = None
        if isinstance(gecko_body, dict):
            attrs = ((gecko_body.get("data") or {}).get("attributes") or {})
            gecko_price = self._f(attrs.get("price_usd"))
            included = gecko_body.get("included") or []
            gecko_pool = (included[0].get("attributes") or {}) if included else None
        if pair is None and gecko_price is None:
            return None  # both IMD sources dead — no snapshot, no zeros

        price_dex = self._f((pair or {}).get("priceUsd"))
        price = price_dex if price_dex is not None else gecko_price
        agree: bool | None = None
        if price_dex is not None and gecko_price is not None:
            mid = (price_dex + gecko_price) / 2
            agree = (
                abs(price_dex - gecko_price) / mid * 100
                <= PRICE_AGREE_TOLERANCE_PCT
                if mid > 0 else False
            )

        fp_pair = None
        if isinstance(fp_body, dict):
            fp_pair = max(
                fp_body.get("pairs") or [],
                key=lambda p: ((p.get("liquidity") or {}).get("usd") or 0.0),
                default=None,
            )

        liq = (pair or {}).get("liquidity") or {}
        change = (pair or {}).get("priceChange") or {}
        vol = (pair or {}).get("volume") or {}
        return MarketSnapshot(
            imd_price_usd=price,
            imd_price_usd_gecko=gecko_price,
            imd_change_24h_pct=(
                self._f(change.get("h24"))
                if pair is not None
                else self._f((gecko_pool or {}).get(
                    "price_change_percentage", {}).get("h24"))
            ),
            imd_vol_24h_usd=(
                self._f(vol.get("h24"))
                if pair is not None
                else self._f(((gecko_pool or {}).get("volume_usd") or {}).get("h24"))
            ),
            pool_liquidity_usd=(
                self._f(liq.get("usd"))
                if pair is not None
                else self._f((gecko_pool or {}).get("reserve_in_usd"))
            ),
            pool_imd=self._f(liq.get("base")),
            pool_weth=self._f(liq.get("quote")),
            fp_price_usd=self._f((fp_pair or {}).get("priceUsd")),
            fdv_usd=self._f((pair or {}).get("fdv")),
            # 0.0 would be a sentinel, and an ETH price of zero is not a number
            # anyone should see rendered as one.
            eth_usd=(eth_usd if (eth_usd or 0) > 0 else None),
            indexer_name=((pair or {}).get("baseToken") or {}).get("name"),
            indexer_symbol=((pair or {}).get("baseToken") or {}).get("symbol"),
            sources_agree=agree,
        )
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the stale-name test bites:** in `fetch_market`, change `indexer_name=…` to pull
  from the Gecko attrs (`attrs.get("name")` fallback) —
  `test_fetch_market_dexscreener_down_falls_back_to_gecko_price` goes red on
  `indexer_name is None` (it would show "Vibe Coins"). Restore, green.
- [ ] **Prove the ETH sentinel guard bites:** change `eth_usd=(eth_usd if (eth_usd or 0) > 0
  else None)` to `eth_usd=(eth_usd or 0.0)` — the `PriceClient` behaviour this method exists
  not to copy — and `test_fetch_market_coingecko_down_is_none_never_zero` goes red on
  `0.0 is not None`. Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.7 fetch_market — DexScreener primary, Gecko cross-check, stale names barred"`

---

### Task WP1.8: `fetch_nft_stats()` — counters, balanceOf, the 24 h rate and the written count

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py` (uses `idmd_token.json`, `idmd_counters.json`,
  `idmd_transfers_page1.json`)

**Interfaces:**
- Consumes: `surf_models.NftStats` — restated from WP0.4's `CONSTRUCTOR_KWARGS[NftStats]`:
  `holders: int | None`, `total_supply: int | None`, `transfers_total: int | None`,
  `dev_holdings: int | None`, `transfers_24h: float | None = None`,
  `written: int | None = None`, `floor_eth: None = None`;
  `surf_addresses.IDMD_NFT / DEV_WALLET / IDENTITY_REGISTRY / TOPIC_IDENTITY_HASH_UPDATED`.
- Produces: `async fetch_nft_stats() -> NftStats | None`; helpers
  `async _count_transfers_24h() -> float | None` and
  `async _count_identities_written() -> int | None`; module constants
  `_SEL_BALANCE_OF = "0x70a08231"` (ERC-721 `balanceOf(address)` — client-local, like
  `ttt_client`'s selectors), `_DAY_SECONDS = 86400.0`,
  `MAX_NFT_TRANSFER_PAGES = 4`, `MAX_REGISTRY_LOG_PAGES = 4`. Floor price is **not** fetched
  by design: no keyless source exists (PRD §5 — `nft_floor` is always `None` at the manager).

**This task owns four numbers, and three of them are traps:**

1. **`transfers_total` and `transfers_24h` are two fields on purpose.** Blockscout's
   `/counters` serves a *lifetime* `transfers_count` (7,411 on 2026-08-08); PRD §4 asks the
   NFT panel for **transfers/day** (~38). Assigning the counter to the rate is a
   one-character mistake that renders "7,411/day" with total confidence, so the rate is
   derived separately, from `/tokens/{IDMD}/transfers` — the exact endpoint the capture
   `identity_transfers_page1.json` came from — by counting rows newer than
   `now_fn() - 86400`. The clock is the **injected** one (house rule), never `time.time()`.
2. **A truncated count is not a count.** Rows come newest-first; the count is complete only
   once a row *older* than the cutoff is seen, or the server stops offering a cursor. If the
   page bound is hit while still inside the window the answer is `None`, not the partial
   number — a lower bound printed as a rate is a wrong number, and PRD §5 says `None` renders
   the unavailable state rather than a lie.
3. **`written` is a lifetime count and must not be derived from a log window.** The hero's
   "written x/2000" (PRD §4, flat keys `identities_written` *and* `nft_written`) is 1 today,
   written on 2026-05-14 — months outside any `eth_getLogs` window this client opens, so
   counting `LogWindow.identity_updates` would render a confident **0/2000**. The registry
   exposes no written-hash getter (verified against the captured sources), so the source is
   Blockscout's address-log view, filtered on `IdentityHashUpdated` and counted over
   **distinct** `topics[1]` — re-writing one token's hash is one identity written, not two.
4. `written` is therefore the **single producer** for both flat keys. `ChainState` carries no
   `identities_written` field (WP0.4), so WP4 must read `stats.written` for the hero as well
   as the NFT panel; the distinct-id count over the recent `identity_updates` window is a
   *signal detail* ("n writes since the gate opened"), never the hero number. Open issue 9.

**Endpoint check before implementing** (one is proven by a capture, one is not):

```bash
curl -s "https://eth.blockscout.com/api/v2/tokens/0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D/transfers" | head -c 200
curl -s "https://eth.blockscout.com/api/v2/addresses/0x000008061ccac597a321a75E3470a3E8fAF9dD2d/logs" | head -c 200
```

  Both must answer `{"items": [...]`. If `/logs` does not exist on this Blockscout build,
  **stop and report** — `written` stays `None` and the widget renders `— / 2000`; do not
  substitute a window count, and do not backfill months of `eth_getLogs` on a keyless pool.

- [ ] **Write the failing tests:**

```python
# ---------------------------------------------------------------------------
# WP1.8 — fetch_nft_stats
# ---------------------------------------------------------------------------


# The capture's newest IDMD transfer, 2026-08-08T09:51:59Z.  Every clock in
# these tests is expressed relative to it, so the expected counts are a
# property of the fixture rather than of the day the suite runs.
IDMD_NEWEST_TRANSFER_TS = 1786182719.0

# One IdentityHashUpdated log: token id 0, the only identity ever written
# (2026-05-14).  Blockscout's /addresses/{h}/logs shape, trimmed to the three
# fields the client reads.
def _registry_log(token_id: int, topic0: str = A.TOPIC_IDENTITY_HASH_UPDATED) -> dict:
    return {
        "address": {"hash": A.IDENTITY_REGISTRY},
        "topics": [topic0, "0x" + _encode_uint(token_id)],
        "data": "0x",
        "block_number": 25_004_000,
    }


REGISTRY_LOGS_PAGE = {
    "items": [
        _registry_log(0),
        # A second write to the SAME id — still one identity written.
        _registry_log(0),
        # An unrelated event from the same contract (ownership transfer):
        # topic0 filtering, not "every log this address emitted", is the rule.
        _registry_log(7, topic0="0x" + "ab" * 32),
    ],
    "next_page_params": None,
}


def _nft_handler(
    *, rest_up=True, rpc_up=True, dev_balance=3,
    transfers_page=None, registry_page=None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "blockscout" in url:
            if not rest_up:
                return httpx.Response(521, json={})
            path = request.url.path.rstrip("/")
            if path.endswith("/counters"):
                return httpx.Response(200, json=load_fixture("idmd_counters.json"))
            if path.endswith("/transfers"):
                return httpx.Response(200, json=(
                    transfers_page
                    if transfers_page is not None
                    else load_fixture("idmd_transfers_page1.json")
                ))
            if path.endswith("/logs"):
                assert A.IDENTITY_REGISTRY.lower() in path.lower()
                return httpx.Response(200, json=(
                    registry_page if registry_page is not None
                    else REGISTRY_LOGS_PAGE
                ))
            return httpx.Response(200, json=load_fixture("idmd_token.json"))
        payload = json.loads(request.content)
        if not rpc_up:
            return httpx.Response(521, json={})
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == A.IDMD_NFT.lower()
        assert call["data"].startswith(surf_client._SEL_BALANCE_OF)
        assert A.DEV_WALLET.lower()[2:] in call["data"].lower()
        return httpx.Response(
            200, json=_rpc_ok(payload, "0x" + _encode_uint(dev_balance))
        )

    return handler


def _nft_client(transport, *, now: float = IDMD_NEWEST_TRANSFER_TS + 60.0):
    """A client whose clock sits just after the capture's newest transfer."""
    return _client_on(transport, now_fn=lambda: now)


@pytest.mark.asyncio
async def test_fetch_nft_stats_real_values():
    async with _nft_client(RecordingTransport(_nft_handler())) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.holders == 667          # idmd_token.json holders_count
    assert stats.total_supply == 2000    # minted out on launch day
    assert stats.transfers_total == 7411 # idmd_counters.json — LIFETIME
    assert stats.dev_holdings == 3       # balanceOf(dev) — he buys his own
    # The whole 25-row slice sits inside the 24 h window (it spans 10.8 h),
    # so the rate is the page count — NOT the lifetime counter beside it.
    assert stats.transfers_24h == 25.0
    assert stats.transfers_24h != stats.transfers_total
    assert stats.written == 1            # IDMD #0, the only identity written
    assert stats.floor_eth is None       # no keyless source, pinned


@pytest.mark.asyncio
async def test_transfers_24h_is_a_window_not_a_page_count():
    """Move the clock forward and rows fall out of the window.

    The derivation must be "rows newer than now-24h", not "rows on the page".
    The clock has to move far enough to actually cross the window's trailing
    edge, and the page only spans 10.77 h: at +6 h the cutoff is still
    ``newest - 18 h``, older than every row on it, so the count would be 25 and
    this test would be byte-identical to ``test_fetch_nft_stats_real_values``.
    At **+18 h** the cutoff is ``newest - 6 h`` = 1786161119, which lands
    between row 15 (5.907 h old, inside) and row 16 (8.197 h old, outside) —
    16 rows. Any anchor in (newest + 15.81 h, newest + 18.09 h] gives 16;
    18 h sits comfortably inside that and states the cutoff in round hours.
    """
    async with _nft_client(
        RecordingTransport(_nft_handler()),
        now=IDMD_NEWEST_TRANSFER_TS + 18 * 3600.0,
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.transfers_24h == 16.0
    # NOT 25: that is the answer for a cutoff older than the whole page, and
    # "change the expectation to 25" is the repair that makes this test vacuous.
    assert stats.transfers_24h != 25.0


@pytest.mark.asyncio
async def test_transfers_24h_is_none_when_the_window_outruns_the_page_bound():
    """A lower bound is not a rate.

    A server that keeps handing back a cursor while every row is still inside
    the window means the client never saw the edge of the day. `None` renders
    the unavailable state; the partial count would render as fact.
    """
    fixture = load_fixture("idmd_transfers_page1.json")
    endless = {"items": fixture["items"], "next_page_params": {"index": 1}}
    transport = RecordingTransport(_nft_handler(transfers_page=endless))
    async with _nft_client(transport) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.transfers_24h is None
    assert stats.transfers_total == 7411   # the lifetime leg still answered
    transfer_gets = [u for u in transport.urls() if u.endswith("/transfers")
                     or "/transfers?" in u]
    assert len(transfer_gets) == surf_client.MAX_NFT_TRANSFER_PAGES


@pytest.mark.asyncio
async def test_written_counts_distinct_ids_and_only_the_right_topic():
    """1/2000 — and it stays 1 when the same token is re-written."""
    async with _nft_client(RecordingTransport(_nft_handler())) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 1

    two = {"items": [_registry_log(0), _registry_log(1337)],
           "next_page_params": None}
    async with _nft_client(
        RecordingTransport(_nft_handler(registry_page=two))
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 2

    # A registry that emitted nothing yet is 0 written — a real value, and
    # the one case where 0 must NOT become None.
    empty = {"items": [], "next_page_params": None}
    async with _nft_client(
        RecordingTransport(_nft_handler(registry_page=empty))
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 0


@pytest.mark.asyncio
async def test_fetch_nft_stats_rest_down_still_reports_dev_holdings():
    async with _nft_client(RecordingTransport(_nft_handler(rest_up=False))) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.holders is None and stats.transfers_total is None
    assert stats.transfers_24h is None and stats.written is None
    assert stats.dev_holdings == 3


@pytest.mark.asyncio
async def test_fetch_nft_stats_everything_down_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_nft_stats() is None
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_nft_stats'`.
- [ ] **Minimal implementation** (module level: `_SEL_BALANCE_OF = "0x70a08231"`; and note
  `encode_uint`/`pad_left` come from `evm_abi`):

```python
    async def _count_transfers_24h(self) -> float | None:
        """IDMD transfers in the last 24 h — a RATE, never the lifetime count.

        Rows arrive newest-first, so the first row older than the cutoff ends
        the count: everything after it is outside the window. Two endings are
        complete answers — that older row, or a page the server did not
        continue. Running out of page budget while still inside the window is
        NOT: that answer is a lower bound, and a lower bound rendered as
        "transfers/day" is a wrong number, so it degrades to ``None``.
        """
        cutoff = self._now_fn() - _DAY_SECONDS
        url = f"{self._blockscout}/tokens/{A.IDMD_NFT}/transfers"
        params: dict | None = None
        count = 0
        for _page in range(MAX_NFT_TRANSFER_PAGES):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return None
            for row in body["items"]:
                ts = _parse_iso_ts(row.get("timestamp"))
                if ts is None:
                    continue          # undated row: skip it, never count it
                if ts < cutoff:
                    return float(count)          # crossed the window edge
                count += 1
            nxt = body.get("next_page_params")
            if not nxt:
                return float(count)              # no older rows exist
            params = nxt
        logger.warning(
            "transfers_24h: %s pages did not reach the 24 h edge — reporting "
            "unavailable rather than a lower bound", MAX_NFT_TRANSFER_PAGES,
        )
        return None

    async def _count_identities_written(self) -> int | None:
        """Distinct IDMD ids that ever received an identity hash (x of 2000).

        LIFETIME, not windowed. The only write today happened 2026-05-14,
        months before any ``eth_getLogs`` window this client opens, so a
        window count would render a confident 0/2000. Blockscout's address-log
        view is the keyless lifetime source; the registry exposes no
        written-hash getter.

        Counted over DISTINCT ``topics[1]``: ``IdentityHashUpdated`` fires
        again when a holder replaces their hash, and that is one identity
        written, not two. Topic0 is filtered explicitly — the registry emits
        other events, and "every log this contract ever emitted" is a
        different, larger number.
        """
        url = f"{self._blockscout}/addresses/{A.IDENTITY_REGISTRY}/logs"
        params: dict | None = None
        ids: set[str] = set()
        for _page in range(MAX_REGISTRY_LOG_PAGES):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return None
            for row in body["items"]:
                topics = row.get("topics") or []
                if not topics or str(topics[0] or "").lower() != \
                        A.TOPIC_IDENTITY_HASH_UPDATED.lower():
                    continue
                if len(topics) > 1 and topics[1]:
                    ids.add(str(topics[1]).lower())
            if not body.get("next_page_params"):
                return len(ids)       # 0 is a real answer: nobody has written
            params = body["next_page_params"]
        logger.warning("identities written: page bound hit, count truncated")
        return None                   # a lower bound is not a count

    async def fetch_nft_stats(self) -> NftStats | None:
        """IDMD collection stats. Floor is deliberately absent: no keyless
        source (OpenSea keyed/Cloudflare-gated) — the manager renders the
        explicit unavailable state, never a faked number.
        """
        token_body, counters_body, transfers_24h, written = await asyncio.gather(
            self._get_json(f"{self._blockscout}/tokens/{A.IDMD_NFT}"),
            self._get_json(f"{self._blockscout}/tokens/{A.IDMD_NFT}/counters"),
            self._count_transfers_24h(),
            self._count_identities_written(),
        )
        dev_holdings: int | None = None
        try:
            calldata = _SEL_BALANCE_OF + pad_left(strip0x(A.DEV_WALLET).lower(), 64)
            raw = await self._rpc_state(
                "eth_call", [{"to": A.IDMD_NFT, "data": calldata}, "latest"]
            )
            if raw and strip0x(raw):
                dev_holdings = decode_uint(raw, 0)
        except RuntimeError as exc:
            logger.warning("fetch_nft_stats balanceOf: %s", exc)

        def to_int(v: Any) -> int | None:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        holders = to_int((token_body or {}).get("holders_count"))
        supply = to_int((token_body or {}).get("total_supply"))
        transfers = to_int((counters_body or {}).get("transfers_count"))
        if all(v is None for v in (holders, supply, transfers, dev_holdings,
                                   transfers_24h, written)):
            return None
        return NftStats(
            holders=holders,
            total_supply=supply,
            transfers_total=transfers,     # lifetime, 7,411
            transfers_24h=transfers_24h,   # the rate — a different number
            dev_holdings=dev_holdings,
            written=written,               # feeds BOTH hero and NFT panel
            # floor_eth stays at its pinned None: no keyless source exists.
        )
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the rate is not the counter.** In `fetch_nft_stats`, pass
  `transfers_24h=float(transfers)` (the lifetime value — the mistake this field split exists
  to prevent). `test_fetch_nft_stats_real_values` goes red on `25.0 != 7411.0`. Restore, green.
- [ ] **Prove the window is a window.** In `_count_transfers_24h`, drop the
  `if ts < cutoff: return float(count)` branch so every row on the page is counted —
  `test_transfers_24h_is_a_window_not_a_page_count` goes red with `25.0 != 16.0`, while
  `test_fetch_nft_stats_real_values` stays green (its clock leaves all 25 inside the window).
  That asymmetry is the point of having both tests. Restore, green.
- [ ] **Prove the truncation guard bites.** In `_count_transfers_24h`, replace the final
  `return None` with `return float(count)` —
  `test_transfers_24h_is_none_when_the_window_outruns_the_page_bound` goes red with a
  plausible-looking 100. Restore, green.
- [ ] **Prove the distinct-id count bites.** In `_count_identities_written`, count rows
  instead of ids (`ids.add(f"{len(ids)}")` or a plain counter) —
  `test_written_counts_distinct_ids_and_only_the_right_topic` goes red with `2 != 1` on the
  re-written token. Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.8 fetch_nft_stats — counters, balanceOf, 24h rate and lifetime written count"`

---

### Task WP1.9: `fetch_recent_logs()` — the logs pool, four filters, shrink-not-follow

> **This task fetches; WP4 decodes.** The four groups carry raw log dicts, and WP4's
> `_hex_int` / `_word_addr` / `_log_ts` helpers turn them into `hooks`, token ids, amounts and
> timestamps. That split only works if the rows arrive *intact* — see *The hand-over contract*
> in the header, and Task WP1.9b, which pins it. Truncating `data`, re-keying `topics` or
> dropping `blockTimestamp` here silently disables V4 LAUNCH, GATE OPEN's detail and
> BRIDGE STAGE, with no error anywhere.

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `surf_addresses.IMD_TOKEN / IDENTITY_REGISTRY / POOL_MANAGER_V4 / DEV_WALLET /
  OPS_WALLET / IDMD_NFT / TOPIC_TRANSFER / TOPIC_IDENTITY_HASH_UPDATED / TOPIC_V4_INITIALIZE /
  TOPIC_SEAPORT_ORDER_FULFILLED / KNOWN_LABELS`; `evm_abi.pad_left / strip0x`;
  `surf_models.LogWindow` — WP0's frozen names, all four groups
  `tuple[dict, ...]` (`bridge_mints`, `identity_updates`, `v4_initializes`, `seaport_sales`),
  plus `from_block: int | None`, `to_block: int | None`. **`seaport_sales`, not
  `seaport_orders`** — an earlier draft of this task used the wrong name and WP4 codes against
  the frozen one.
- Produces: `async fetch_recent_logs() -> LogWindow | None`; module constants
  `_SEAPORT = "0x0000000000000068f116a894984e2db1123eb395"` (Seaport 1.6; asserted present in
  `KNOWN_LABELS` by a test), `_ZERO_TOPIC = "0x" + "0" * 64`; helper
  `_addr_topic(addr) -> str`.

- [ ] **Write the failing tests:**

```python
# ---------------------------------------------------------------------------
# WP1.9 — fetch_recent_logs
# ---------------------------------------------------------------------------

#: The head the LOGS pool reports — deliberately NOT ``HEAD_BLOCK`` (WP1.3's
#: state-pool head, 25,707,884).  The two pools answer ``eth_blockNumber``
#: independently and this suite must not pretend otherwise, so they get
#: different names as well as different values.  Reusing the name would be worse
#: than confusing: module globals resolve at call time, so the later definition
#: would win for the WHOLE file and quietly break WP1.3's assertions.
LOG_HEAD_BLOCK = 25_709_000


def _addr_topic(addr: str) -> str:
    return "0x" + _strip0x(addr).lower().rjust(64, "0")


def _fake_log(topic0: str, address: str, **extra: Any) -> dict:
    return {
        "address": address.lower(),
        "topics": [topic0, *extra.pop("topics", [])],
        "data": extra.pop("data", "0x"),
        "blockNumber": hex(extra.pop("block", LOG_HEAD_BLOCK - 5)),
        "transactionHash": extra.pop("tx", "0x" + "ab" * 32),
        "logIndex": "0x0",
    }


def _topics_match(log_topics: list, flt_topics: list) -> bool:
    """Real ``eth_getLogs`` topic semantics: positional, ``None`` = wildcard,
    a list = OR at that position.

    The double MUST honour positions. ``fetch_recent_logs`` asks for
    ``Initialize`` twice — IMD as ``currency0`` (topic 2), then as ``currency1``
    (topic 3) — and merges the two answers without deduping, because on a real
    chain IMD is only ever one of the two. A position-blind handler serves the
    same row to both queries and the merged group holds a phantom duplicate,
    which is a defect in the DOUBLE, not in the client.
    """
    for i, want in enumerate(flt_topics):
        if want is None:
            continue
        if i >= len(log_topics):
            return False
        got = str(log_topics[i]).lower()
        if isinstance(want, (list, tuple)):
            if got not in {str(w).lower() for w in want}:
                return False
        elif got != str(want).lower():
            return False
    return True


def _logs_handler(
    logs_by_topic0: dict[str, list[dict]],
    *, range_errors_before_success: int = 0,
) -> Callable[[httpx.Request], httpx.Response]:
    state = {"range_errors_left": range_errors_before_success,
             "windows_seen": []}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(LOG_HEAD_BLOCK)))
        assert payload["method"] == "eth_getLogs", payload["method"]
        flt = payload["params"][0]
        window = int(flt["toBlock"], 16) - int(flt["fromBlock"], 16)
        state["windows_seen"].append(window)
        if state["range_errors_left"] > 0:
            state["range_errors_left"] -= 1
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32005,
                          # a DECREMENTING suggested range — following it
                          # verbatim livelocks (CLAUDE.md hazard).
                          "message": "block range is too large, try "
                                     f"{LOG_HEAD_BLOCK - 1}-{LOG_HEAD_BLOCK}"},
            })
        topic0 = flt["topics"][0]
        rows = [
            log for log in logs_by_topic0.get(topic0, [])
            if _topics_match(log["topics"], flt["topics"])
        ]
        return httpx.Response(200, json=_rpc_ok(payload, rows))

    handler.state = state  # type: ignore[attr-defined]
    return handler


def _standard_logs() -> dict[str, list[dict]]:
    idmd_word = _strip0x(A.IDMD_NFT).lower().rjust(64, "0")
    return {
        A.TOPIC_TRANSFER: [
            _fake_log(A.TOPIC_TRANSFER, A.IMD_TOKEN, topics=[
                "0x" + "0" * 64, _addr_topic(A.OPS_WALLET)]),
        ],
        A.TOPIC_IDENTITY_HASH_UPDATED: [],
        # topics = [Initialize, poolId, currency0, currency1] — IMD sits at
        # topic 2, i.e. it is currency0 here.  A pool can only ever have IMD on
        # ONE side, which is why `_topics_match` must answer exactly one of the
        # client's two Initialize queries.
        A.TOPIC_V4_INITIALIZE: [
            _fake_log(A.TOPIC_V4_INITIALIZE, A.POOL_MANAGER_V4, topics=[
                "0x" + "11" * 32, _addr_topic(A.IMD_TOKEN),
                _addr_topic("0x" + "c0" * 20)]),
        ],
        A.TOPIC_SEAPORT_ORDER_FULFILLED: [
            _fake_log(A.TOPIC_SEAPORT_ORDER_FULFILLED, surf_client._SEAPORT,
                      topics=["0x" + "22" * 32, "0x" + "33" * 32],
                      data="0x" + "00" * 31 + "01" + idmd_word),
            # An OrderFulfilled for some OTHER collection — must be dropped
            # by the IDMD pre-filter.
            _fake_log(A.TOPIC_SEAPORT_ORDER_FULFILLED, surf_client._SEAPORT,
                      topics=["0x" + "44" * 32, "0x" + "55" * 32],
                      data="0x" + "ee" * 96),
        ],
    }


@pytest.mark.asyncio
async def test_fetch_recent_logs_filters_and_pools():
    handler = _logs_handler(_standard_logs())
    transport = RecordingTransport(handler)
    async with _client_on(transport) as client:
        window = await client.fetch_recent_logs()
    assert window is not None
    assert window.to_block == LOG_HEAD_BLOCK
    assert window.from_block == LOG_HEAD_BLOCK - surf_client.LOG_WINDOW_BLOCKS
    assert len(window.bridge_mints) == 1
    assert window.identity_updates == ()          # empty is DATA, not failure
    # ONE Initialize row, from TWO queries: the fixture log carries IMD at
    # topic 2 (currency0), so the currency0 query matches it and the currency1
    # query answers []. `_topics_match` is what makes the double behave like a
    # real node here — a position-blind one would hand the same row to both
    # queries and the un-deduped merge below would hold it twice.
    assert len(window.v4_initializes) == 1
    assert len(window.seaport_sales) == 1         # the non-IDMD row was dropped

    # Every request in this method went to the LOGS pool — never publicnode.
    assert transport.urls(), "no requests recorded"
    for url in transport.urls():
        assert "publicnode" not in url

    # The bridge-mint filter is exact: Transfer, from == 0x0, to ∈ {dev, ops}.
    getlogs = [p for (_u, _m, p) in transport.requests
               if p and p.get("method") == "eth_getLogs"]
    mint = [p for p in getlogs
            if p["params"][0]["topics"][0] == A.TOPIC_TRANSFER][0]
    flt = mint["params"][0]
    assert flt["address"].lower() == A.IMD_TOKEN.lower()
    assert flt["topics"][1] == "0x" + "0" * 64
    assert sorted(t.lower() for t in flt["topics"][2]) == sorted(
        [_addr_topic(A.DEV_WALLET), _addr_topic(A.OPS_WALLET)])

    # The v4 Initialize filter matches IMD as EITHER currency (two topics-OR
    # calls or one per position — assert both positions were queried).
    init_calls = [p for p in getlogs
                  if p["params"][0]["topics"][0] == A.TOPIC_V4_INITIALIZE]
    assert len(init_calls) == 2
    positions = set()
    for p in init_calls:
        topics = p["params"][0]["topics"]
        for i in (2, 3):
            if len(topics) > i and topics[i] == _addr_topic(A.IMD_TOKEN):
                positions.add(i)
    assert positions == {2, 3}


@pytest.mark.asyncio
async def test_fetch_recent_logs_halves_window_never_follows_suggestion():
    handler = _logs_handler(_standard_logs(), range_errors_before_success=1)
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()
    assert window is not None
    seen = handler.state["windows_seen"]
    assert seen[0] == surf_client.LOG_WINDOW_BLOCKS
    assert seen[1] == surf_client.LOG_WINDOW_BLOCKS // 2  # halved…
    assert 1 not in seen  # …and the endpoint's 1-block suggestion was IGNORED


@pytest.mark.asyncio
async def test_fetch_recent_logs_shrink_is_bounded_then_none():
    handler = _logs_handler(_standard_logs(), range_errors_before_success=99)
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()
    assert window is None  # bounded retries, then honest failure — no livelock
    assert len(handler.state["windows_seen"]) <= (
        (surf_client._LOG_MAX_SHRINKS + 1) * 5 * 2  # filters x endpoints cap
    )


@pytest.mark.asyncio
async def test_fetch_recent_logs_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_recent_logs() is None


def test_seaport_address_is_labeled():
    assert surf_client._SEAPORT in A.KNOWN_LABELS  # one cast list, no drift
```

- [ ] Run — **expected failure:** `AttributeError: … no attribute 'fetch_recent_logs'`.
- [ ] **Minimal implementation:**

```python
_SEAPORT = "0x0000000000000068f116a894984e2db1123eb395"  # Seaport 1.6
_ZERO_TOPIC = "0x" + "0" * 64


def _addr_topic(addr: str) -> str:
    return "0x" + pad_left(strip0x(addr).lower(), 64)
```

  and in the class:

```python
    async def _get_logs_shrinking(
        self, base_filter: dict, from_block: int, to_block: int
    ) -> list[dict] | None:
        """eth_getLogs with bounded window-halving on range errors.

        A provider's suggested range is NEVER adopted: one of them decrements
        a single block per round trip, which livelocks a verbatim follower.
        Halving our own window converges in <= _LOG_MAX_SHRINKS steps or
        fails honestly.
        """
        window = to_block - from_block
        for _shrink in range(_LOG_MAX_SHRINKS + 1):
            flt = dict(base_filter)
            flt["fromBlock"] = hex(to_block - window)
            flt["toBlock"] = hex(to_block)
            try:
                result = await self._rpc_logs("eth_getLogs", [flt])
                return result if isinstance(result, list) else None
            except _LogRangeError:
                window = max(window // 2, _LOG_MIN_WINDOW)
                if window == _LOG_MIN_WINDOW and _shrink >= 1:
                    break
            except RuntimeError as exc:
                logger.warning("getLogs failed: %s", exc)
                return None
        return None

    async def fetch_recent_logs(self) -> LogWindow | None:
        """The recent-window log sweep for signals 2/3/5 and NFT sales.

        LOGS POOL ONLY. Four filter groups; an *empty* group is data (nothing
        happened); a *failed* group is ``None``; a dead head-read is a dead
        window. Raw log dicts pass through — decoding is downstream.
        """
        try:
            head_hex = await self._rpc_logs("eth_blockNumber", [])
            head = int(head_hex, 16)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.warning("fetch_recent_logs head: %s", exc)
            return None
        from_block = head - self._log_window_blocks

        bridge = await self._get_logs_shrinking(
            {
                "address": A.IMD_TOKEN,
                "topics": [
                    A.TOPIC_TRANSFER,
                    _ZERO_TOPIC,
                    [_addr_topic(A.DEV_WALLET), _addr_topic(A.OPS_WALLET)],
                ],
            },
            from_block, head,
        )
        identity = await self._get_logs_shrinking(
            {"address": A.IDENTITY_REGISTRY,
             "topics": [A.TOPIC_IDENTITY_HASH_UPDATED]},
            from_block, head,
        )
        # v4 Initialize: IMD may be currency0 (topic2) or currency1 (topic3).
        init0 = await self._get_logs_shrinking(
            {"address": A.POOL_MANAGER_V4,
             "topics": [A.TOPIC_V4_INITIALIZE, None, _addr_topic(A.IMD_TOKEN)]},
            from_block, head,
        )
        init1 = await self._get_logs_shrinking(
            {"address": A.POOL_MANAGER_V4,
             "topics": [A.TOPIC_V4_INITIALIZE, None, None,
                        _addr_topic(A.IMD_TOKEN)]},
            from_block, head,
        )
        v4_inits: list[dict] | None
        if init0 is None and init1 is None:
            v4_inits = None
        else:
            v4_inits = [*(init0 or []), *(init1 or [])]
        seaport_raw = await self._get_logs_shrinking(
            {"address": _SEAPORT,
             "topics": [A.TOPIC_SEAPORT_ORDER_FULFILLED]},
            from_block, head,
        )
        seaport: list[dict] | None = None
        if seaport_raw is not None:
            # Cheap pre-filter: keep only fulfillments whose payload mentions
            # the IDMD contract. Exact consideration decoding is downstream.
            idmd_word = strip0x(A.IDMD_NFT).lower()
            seaport = [
                log for log in seaport_raw
                if idmd_word in str(log.get("data", "")).lower()
            ]

        if bridge is None and identity is None and v4_inits is None \
                and seaport is None:
            return None
        # Raw rows, verbatim from the endpoint.  WP4 decodes them; this module
        # must not normalise, prune or re-key them.
        return LogWindow(
            from_block=from_block,
            to_block=head,
            bridge_mints=tuple(bridge or ()),
            identity_updates=tuple(identity or ()),
            v4_initializes=tuple(v4_inits or ()),
            seaport_sales=tuple(seaport or ()),
        )
```

  A group that *failed* must stay distinguishable from a group that was *empty*, and a frozen
  tuple field cannot hold `None`. The all-four-failed case is already handled above by
  returning `None` for the whole window; a single failed group degrades to `()` and is
  reported through the manager's `degraded` list, not through the tuple.

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v`.
- [ ] **Prove the shrink test bites:** in `_get_logs_shrinking`, change
  `window = max(window // 2, _LOG_MIN_WINDOW)` to parse and adopt the suggested range from the
  error message (`try 25708999-25709000` → window 1) —
  `test_fetch_recent_logs_halves_window_never_follows_suggestion` goes red on `1 not in seen`.
  Restore, green.
- [ ] **Prove the double is position-aware** (this one guards the *test harness*, and a
  position-blind harness is how `v4_initializes` came to hold a duplicate that cannot exist on
  chain): in `_topics_match`, `return True` unconditionally —
  `test_fetch_recent_logs_filters_and_pools` goes red on `2 != 1` for `v4_initializes`.
  Restore, green.
- [ ] Commit:
  `git add -u && git commit -m "feat(surf): WP1.9 fetch_recent_logs — logs pool only, four filters, shrink-not-follow"`

---

### Task WP1.9b: The hand-over guard — raw rows reach WP4 intact

**Files:**
- Modify: `tests/data/test_surf_client.py` (tests only — no production edits expected)

**Why this task exists.** WP4 decodes the log rows (`_hex_int` / `_word_addr` / `_log_ts`,
`_v4_launch_rows`). Every field it reads is a field WP1 has to have carried through untouched,
and every way of losing one is silent — the decode returns an empty string or a zero and the
feature simply never fires. There is no exception, no log line and no failing test unless one
is written here. The four failure modes, all of which a plausible "tidy up the payload" edit
would produce:

| If WP1 loses… | WP4 computes | What the user sees |
|---|---|---|
| `data` beyond the first word | `hooks == ""` | `hook_status` stuck on `NOT LIVE` — through launch day |
| `topics[1]` | token id `0` | GATE OPEN's written count stuck at 0 |
| `blockTimestamp` | `_log_ts` falls back to `now` | every FIRED age reads "just now" |
| `transactionHash` | detectors lose their dedupe key | the same event re-fires every refresh |

**Interfaces:**
- Consumes: `fetch_recent_logs` from WP1.9.
- Produces: no production code. The guarantee WP4's decoders are written against.

- [ ] **Write the tests** (append to the WP1.9 section):

```python
# ---------------------------------------------------------------------------
# WP1.9b — the hand-over contract
# ---------------------------------------------------------------------------

# Field-for-field, what WP4's decoders index into.  Keep in sync with the
# hand-over table in the WP1 header; a failure here is a WP1 defect, and a
# change here needs WP4's agreement.
_REQUIRED_LOG_FIELDS = {"topics", "data", "blockNumber", "transactionHash"}


def _rich_log(topic0: str, address: str, **extra: Any) -> dict:
    """A log with every field a real endpoint sends, including the optional
    ``blockTimestamp`` that tenderly returns and drpc does not."""
    return {
        **_fake_log(topic0, address, **extra),
        "blockTimestamp": hex(1_786_076_339),
        "logIndex": "0x2c",
        "removed": False,
    }


@pytest.mark.asyncio
async def test_every_log_row_reaches_the_manager_with_its_decodable_fields():
    """The contract WP4's decoders are written against."""
    handler = _logs_handler(_standard_logs())
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()

    groups = (window.bridge_mints, window.identity_updates,
              window.v4_initializes, window.seaport_sales)
    rows = [r for group in groups for r in group]
    assert rows, "fixture must produce rows in at least one group"
    for row in rows:
        assert _REQUIRED_LOG_FIELDS <= set(row), row
        assert isinstance(row["topics"], list) and row["topics"]
        assert str(row["data"]).startswith("0x")
        assert row["transactionHash"]


@pytest.mark.asyncio
async def test_the_full_data_word_run_survives_untruncated():
    """`hooks` is data word 2 of a v4 Initialize — five words in.

    A client that kept only the first word would leave WP4 reading "" for
    hooks, which is falsy, which reads as hookless, which pins the hero to
    NOT LIVE forever.  This is the single highest-consequence field in the
    dashboard, so it gets its own test.
    """
    hooks_word = _strip0x(A.VIBECOINS_HOOK).lower().rjust(64, "0")
    data = "0x" + "".join([
        "0" * 60 + "2710",          # fee = 10000
        "0" * 60 + "00c8",          # tickSpacing = 200
        hooks_word,                 # word 2 — hooks
        "0" * 63 + "1",             # sqrtPriceX96
        "0" * 64,                   # tick
    ])
    logs = _standard_logs()
    logs[A.TOPIC_V4_INITIALIZE] = [
        _fake_log(A.TOPIC_V4_INITIALIZE, A.POOL_MANAGER_V4,
                  topics=["0x" + "11" * 32, _addr_topic(A.IMD_TOKEN),
                          _addr_topic(A.WETH)],
                  data=data),
    ]

    async with _client_on(RecordingTransport(_logs_handler(logs))) as client:
        window = await client.fetch_recent_logs()

    row = window.v4_initializes[0]
    assert row["data"] == data                       # byte-for-byte
    assert len(_strip0x(row["data"])) == 64 * 5      # all five words
    # Decoded the way WP4 will decode it, as a cross-check of the contract.
    assert "0x" + _strip0x(row["data"])[64 * 2 + 24:64 * 3] == \
        A.VIBECOINS_HOOK.lower()
    assert len(row["topics"]) == 4                   # id + both currencies


@pytest.mark.asyncio
async def test_block_timestamp_is_passed_through_when_the_endpoint_sends_it():
    """Optional upstream field, and the difference between a true FIRED age
    and "just now" for every event (WP4's `_log_ts` prefers it)."""
    logs = {
        A.TOPIC_TRANSFER: [
            _rich_log(A.TOPIC_TRANSFER, A.IMD_TOKEN,
                      topics=["0x" + "0" * 64, _addr_topic(A.OPS_WALLET)],
                      data="0x" + f"{10**22:064x}"),
        ],
        A.TOPIC_IDENTITY_HASH_UPDATED: [],
        A.TOPIC_V4_INITIALIZE: [],
        A.TOPIC_SEAPORT_ORDER_FULFILLED: [],
    }
    async with _client_on(RecordingTransport(_logs_handler(logs))) as client:
        window = await client.fetch_recent_logs()

    row = window.bridge_mints[0]
    assert row["blockTimestamp"] == hex(1_786_076_339)
    # The amount word is intact too — 10,000 IMD at 18 decimals.
    assert int(row["data"], 16) == 10**22


def test_the_client_never_decodes_a_log_itself():
    """One owner for the log decoders, and it is WP4.

    A second copy here would drift from the manager's and the two would
    disagree about launch day.  Matching on WP4's helper names rather than on
    words like "hooks" keeps this from firing on an explanatory comment.
    """
    source = Path(_mod.__file__).read_text()
    for banned in ("_word_addr", "_log_ts", "_v4_launch_rows"):
        assert banned not in source, (
            f"{banned} is WP4's; surf_client must hand over raw rows"
        )
    # The dev-activity labelling IS this module's (WP0.4 forces it), so the
    # allowlist lookup is expected here and only here.
    assert "_label_for" in source
```

- [ ] Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -k "hand_over or data_word or block_timestamp or never_decodes" -v`
      — all green against the WP1.9 implementation, which already passes rows through verbatim.
      These tests are a **ratchet**, not a driver: they exist so a later "clean up the log
      payload" edit fails loudly instead of silently disabling four features.
- [ ] **Prove they bite.** In `fetch_recent_logs`, add the plausible tidy-up — replace the
      returned rows with a projection that keeps only what *this module* uses:

```python
        def _slim(group):
            return tuple({"topics": r["topics"][:1], "data": r["data"][:66],
                          "blockNumber": r["blockNumber"],
                          "transactionHash": r["transactionHash"]}
                         for r in (group or []))
```

      and wrap each group in it. Re-run → `test_the_full_data_word_run_survives_untruncated`
      FAILS on the byte-for-byte `data` comparison and on `len(topics) == 4`;
      `test_block_timestamp_is_passed_through…` FAILS on the missing key. Restore, green.
- [ ] Commit:
      `git add -u && git commit -m "test(surf): WP1.9b pin the raw log hand-over WP4's decoders depend on"`

---

### Task WP1.10: Structural guards — pool separation, full-outage sweep, suite gate

**Files:**
- Modify: `tests/data/test_surf_client.py` (tests only — no production edits expected)

**Interfaces:**
- Consumes: everything above.
- Produces: the WP1 completion guarantee WP4 builds on — *every* `fetch_*` degrades to `None`
  under total outage, and the state pool can never be asked for logs.

- [ ] **Write the tests** (append):

```python
# ---------------------------------------------------------------------------
# WP1.10 — structural guards
# ---------------------------------------------------------------------------

import inspect
import re

from maxpane_dashboard.data import surf_client as _mod


def _code_only(source: str) -> str:
    """Source with docstrings and comments stripped (WP2 uses the same idiom).

    The guards below assert on what the code *does*. Prose has to be free to
    NAME the thing it forbids: the module docstring explains that publicnode
    "REFUSES archive ``eth_getLogs``" — which is the entire reason the pools are
    separate — and the ``LOG_RPCS`` comment says the same again. A raw
    substring check would fail against the very implementation WP1.1 specifies.
    """
    return re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", source))


FETCHERS = [
    "fetch_nonces", "fetch_chain_state", "fetch_channel_txs",
    "fetch_dev_activity", "fetch_market", "fetch_recent_logs",
    "fetch_nft_stats",
]


def test_frozen_surface_is_complete():
    for name in FETCHERS:
        fn = getattr(SurfClient, name)
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", FETCHERS)
async def test_every_fetcher_survives_total_outage_as_none(name):
    """PRD success criterion 3: full outage → explicit degraded state.

    Every request fails at the transport layer, so this proves each method
    survives its retries, its endpoint rotation and its ``asyncio.gather``
    without letting an exception escape into the refresh loop.

    ``_offline_client``, not ``_raising_client``: these methods all DO issue
    requests, and an ``AssertionError`` from a ``MockTransport`` handler is not
    an ``httpx.HTTPError`` — it would propagate out of the fetcher and error
    all seven cases instead of asserting anything.
    """
    async with _offline_client() as client:
        result = await getattr(client, name)()
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", FETCHERS)
async def test_no_fetcher_turns_outage_into_zero(name):
    """A failed read is None, never 0 / [] / {} (CLAUDE.md convention)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, json={})

    async with _client_on(RecordingTransport(handler)) as client:
        result = await getattr(client, name)()
    assert result is None
    assert result != 0 and result != [] and result != {}


def test_state_pool_is_structurally_logless():
    """No state-pool CODE may spell eth_getLogs.

    A capability probe is the failure mode: publicnode answers a narrow
    recent range and 403s the backfill, so the safe rule is that no state-
    pool helper can even name the method (mirrors
    test_no_eth_getlogs_in_this_module in the FWA suite).

    Run on ``_code_only``, not on the raw source: the module docstring names
    ``eth_getLogs`` twice and the ``LOG_RPCS`` comment once, all three to
    explain why the pools are separate at all. Deleting that prose to satisfy a
    substring check would remove the explanation and keep the hazard.
    """
    code = _code_only(Path(_mod.__file__).read_text())
    state_section = code.split("async def _rpc_logs")[0]
    assert "eth_getLogs" not in state_section


def test_client_module_never_reads_the_wall_clock_directly():
    """time.time() is injected as now_fn; time.monotonic (pacing) is fine."""
    source = Path(_mod.__file__).read_text()
    assert "time.time()" not in source


@pytest.mark.asyncio
async def test_no_fetcher_invents_a_zero_timestamp():
    """The sweep for the sentinel that would disable BRIDGE STAGE.

    0.0 is the one value that is both falsy AND a valid float: it survives
    every `if ts:` guard downstream while meaning 1970, i.e. an event that can
    never be recent enough to fire.  No parsed `ts` may be 0.0 — a row whose
    timestamp could not be parsed is dropped, never zero-stamped.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
        channel = await client.fetch_channel_txs()

    for row in [*rows, *(channel or [])]:
        assert row.ts > 1_600_000_000.0, row


def test_every_log_group_is_a_tuple_never_none():
    """WP0 froze the four groups as tuple[dict, ...]; WP4 iterates them.

    This pins only the container — a `None` reaching a `for` loop in the
    manager is the failure it prevents.  The *contents* are pinned by
    WP1.9b's hand-over tests.
    """
    from maxpane_dashboard.data.surf_models import LogWindow as _LW

    window = _LW(from_block=1, to_block=2)
    for name in ("bridge_mints", "identity_updates",
                 "v4_initializes", "seaport_sales"):
        assert getattr(window, name) == ()
```

- [ ] Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -v` — all green. If
  `test_state_pool_is_structurally_logless` fails, read the failure literally: **executable
  code above `async def _rpc_logs` mentions `eth_getLogs`.** Prose does not trip it (the
  assertion runs on `_code_only`, which strips docstrings and `#` comments), so the fix is
  never to delete an explanatory sentence. Either a `getLogs` call site drifted up into the
  state plumbing — move it below `_rpc_logs`, where `_get_logs_shrinking` and
  `fetch_recent_logs` already live — or `_rpc_state` / `_rpc_state_batch` grew a logs branch,
  which is the defect the guard exists to catch and must be removed, not relocated.
- [ ] **Prove this guard bites:** add `# eth_getLogs` … no — a comment is stripped by design.
  Add a real statement above `_rpc_logs`, e.g. `_PROBE = "eth_getLogs"` next to
  `STATE_RPC_PRIMARY`, rerun → `test_state_pool_is_structurally_logless` FAILS. Delete it,
  green. (Doing it with a comment instead and watching the test stay green is the second half
  of the proof: the guard pins code, not prose.)
- [ ] Full-suite gate (must be green, ~2100 existing tests unaffected — this WP adds files
  only): `.venv/bin/python -m pytest`
- [ ] Commit:
  `git add -u && git commit -m "test(surf): WP1.10 structural guards — outage sweep, pool separation, clock injection"`

---

## Open issues for the orchestrator (not blockers inside WP1)

1. **CLOSED — the model vocabulary is frozen in WP0.4 and imported, not restated.** Every
   *Consumes* line in this file is a quotation of WP0.4's `CONSTRUCTOR_KWARGS`, and Task
   WP1.2's `test_this_wp_constructs_against_wp0s_frozen_field_names` asserts the kwargs this
   WP passes are exactly the declared fields — so a rename is a collection error here rather
   than a `TypeError` on the first live refresh. **WP0.4 must be merged before any WP1 code
   is written.**

   What this closed, for the record: WP0, WP1 and WP4 each carried a different spelling of
   the same seven dataclasses. `ChainState` alone appeared as
   `gate_open`/`imd_supply_wei`/`lp_imd_wei` (WP0), `identity_allowed`/
   `imd_total_supply_wei`/`lp_tokens_owed0` (this file) and `identity_allowed`/`imd_supply`/
   `lp_imd` (WP4 — which was reading *flat-dict* keys off a model). `ChannelTx` required a
   `kind`/`text` the client refuses to compute; `DevTx` was `wallet`+`nonce` here and
   `wallet_label`+`counterparty*`+`kind` there; `NftStats` was passed a `transfers_total`
   that did not exist, while WP4 read a `transfers_24h`/`written`/`last_sales` nobody set;
   `MarketSnapshot` was passed four fields that did not exist and omitted `eth_usd`, which
   did; `LogWindow` was `seaport_orders` here, `seaport_sales` in WP0 and
   `identity_writes: int` in WP4. Every constructor call in this file would have raised, and
   WP4's `getattr(…, None)` reads would have returned `None` for the entire hero with a green
   suite behind them.

   Where each contested name landed:

   | model | resolution |
   |---|---|
   | `ChainState` | mirrors the getters — `identity_allowed` (flat key `gate_open`), `pool_tick`, `imd_name`/`imd_symbol`; `imd_supply_wei` pairs with flat `imd_supply`; **gains** `lp_owner` (WP0.2's new `SEL_OWNER_OF`) and `lp_imd_wei`/`lp_weth_wei` (derived in WP1.4 — issue 10's diff, now landed); **loses** `identities_written`, for which no getter exists |
   | `ChannelTx` | raw: no `kind`, no `text`; `method` optional |
   | `DevTx` | keeps `counterparty`/`counterparty_label`/`kind` and WP1.6 fills them — see 1b |
   | `MarketSnapshot` | this file's shape, plus `eth_usd`, which WP1.7 now fetches |
   | `LogWindow` | `seaport_sales`; four tuple groups; `()` means empty, not failed |
   | `NftStats` | `transfers_total` **and** `transfers_24h` as separate fields, both filled by WP1.8 (lifetime counter vs derived rate); no `last_sales` (sales come off `LogWindow.seaport_sales`); `written` filled by WP1.8 from the registry's lifetime log view — see issue 11 |

1b. **Ownership of the poisoning filter — settled, and worth stating loudly because it was
   settled twice in opposite directions.** WP1.6 owns the sender filter, the `KNOWN_LABELS`
   lookup and the `kind` vocabulary; WP4's `_activity_rows` reads those fields and keeps a
   sender re-check as defence in depth. The tie-break is **WP0.4**, not preference: `DevTx`
   declares `counterparty`, `counterparty_label` and `kind` without defaults, so only the
   constructor can fill them, and WP0.4's docstring already states the invariant ("Rows are
   only ever built where the sender is a dev wallet"). Anchoring to the one file neither
   package may edit is what stops this flipping a third time. **If the orchestrator prefers
   WP4 to own it instead, the same WP0.4 edit is required first** — give the three fields
   defaults or drop them from the client-facing model — and WP1.6's filter/label/kind code
   comes out in the same change. Do not do both halves in different packages.
2. **`SEL_POSITIONS` arg encoding.** WP1 assumes `evm_abi.encode_uint(LP_POSITION_ID)`
   appended to the selector; confirm `evm_abi.encode_uint` returns an unprefixed 64-hex word
   (it does today — `fwa_client` relies on it).
3. **Seaport address.** The frozen `surf_addresses` surface has `TOPIC_SEAPORT_ORDER_FULFILLED`
   but no Seaport address constant; WP1 defines `_SEAPORT` locally and pins agreement via
   `test_seaport_address_is_labeled` (it must be a `KNOWN_LABELS` key). If WP0 prefers to own
   the address, promote it and delete the local constant — one-line change.
4. **CLOSED — `lp_owner_ok`.** WP0.2 vendors `SEL_OWNER_OF = "0x6352211e"` with its
   `ownerOf(uint256)` preimage (recomputed in-test like every other selector), and WP1.4 has
   the seventh `aggregate3` sub-call that fills `ChainState.lp_owner`. WP4 compares it to
   `OPS_WALLET`. Deriving it from NFPM transfer history was dropped: that answers "who
   received it last inside the window we happened to read", which is not the same fact as
   "who holds it", and the hero would have stated the wrong one confidently.
5. **Blockscout page sizes.** The live `/transactions` page held all 21 channel txs and 50 ops
   txs on 2026-08-08; `MAX_CHANNEL_PAGES=3` / `MAX_ACTIVITY_PAGES=2` bound growth. WP4 should
   surface "feed may be truncated" if the last fetched page still carried `next_page_params`.
6. **pytest-asyncio strict mode.** The suite already runs `asyncio_mode = auto`-style markers
   in every `test_*_client.py`; WP1 copies the same `@pytest.mark.asyncio` idiom. Nothing to
   configure.
7. **No `SEL_DECIMALS` in the frozen surface.** WP4 scales bridge-mint amounts by 18 decimals.
   That value is *captured*, not remembered (`ops_eth_token_transfers.json` →
   `token.decimals == "18"`), but it is still a constant in a repo whose first rule is to read
   values live. Cheap fix if WP0 wants it: add `SEL_DECIMALS` (`0x313ce567`) and let
   `fetch_chain_state` return it. Not a blocker — the raw wei value is exact either way and no
   signal depends on the scaled float.
8. **Block timestamps are approximate by design, and that is WP4's call.** WP4's `_log_ts`
   prefers the endpoint's `blockTimestamp` and falls back to *first-seen* (`now`), rather than
   resolving a block header per event. Consequence to accept knowingly: on the first sweep
   after a restart, an event that landed minutes earlier renders as `FIRED just now`. It is
   bounded (WP2's detectors key on `tx_hash`, so nothing re-fires) and it costs zero round
   trips. **WP1's obligation is only to pass `blockTimestamp` through when the endpoint sends
   it** (tenderly does, drpc does not) — pinned by WP1.9b. If the approximation later proves
   too coarse for BRIDGE STAGE, the exact fix belongs in WP1, not WP4: add
   `_resolve_block_times(blocks) -> dict[int, float]` calling `eth_getBlockByNumber` on the
   **logs** pool (the manager owns no transport and must never open one), cap it at ~40
   distinct blocks per sweep, and return `None` — never `0.0` — for anything unresolved.
9. **Distinct-id counting applies to both counts, and they are different counts.** A holder
   may rewrite the same identity twice, so every count over `IdentityHashUpdated` is over
   distinct token ids, never `len(rows)`. But there are two such counts and only one of them
   is the hero's: WP4's count over `LogWindow.identity_updates` is *"writes seen in the recent
   window"* — signal 3's detail line — while the hero's "written x/2000" is a **lifetime**
   number that WP1.8 produces (issue 11). Reading the window count into the hero renders
   `0/2000` on a chain whose real answer is `1/2000`, because the only write so far happened
   on 2026-05-14.
10. **BLOCKING — WP0 must add two `ChainState` fields before WP1.4 is written.** The PRD §5
   hero keys `lp_imd` / `lp_weth` have no producer without them, and WP4 already reads exactly
   these two model names. Two lines in `surf_models.py` plus two entries in
   `CONSTRUCTOR_KWARGS[ChainState]`:

   ```python
       lp_imd_wei: int | None
       lp_weth_wei: int | None
   ```

   They are **derived in WP1.4**, not in the manager, because the derivation needs
   `tickLower`/`tickUpper` from `positions()` — words that exist nowhere else in the frozen
   surface. A manager holding only `lp_liquidity` and `sqrt_price_x96` can compute the sides
   *only* under the full-range assumption, which is exactly true today and exactly wrong the
   day the LP is re-added concentrated — the day signal 2 exists for. WP1.4's freeze check
   fails loudly until this lands; do not paper over it with `getattr(state, "lp_imd", None)`,
   which is how these keys became permanently `None` in the first place.
11. **The hero's `identities_written` and the NFT panel's `nft_written` are one number with
   one producer: `NftStats.written` (WP1.8).** `ChainState` carries no `identities_written`
   field (WP0.4 dropped it — no getter exists), so WP4 must read `stats.written` for both flat
   keys. Source: Blockscout's `/addresses/{IDENTITY_REGISTRY}/logs`, filtered on
   `IdentityHashUpdated`, counted over distinct `topics[1]`, lifetime, bounded pages, `None`
   when truncated. If WP0 would rather the hero read it off `ChainState`, that needs a getter
   this registry does not have — the alternative is passing the same client-derived number
   into two models, which is the duplication this issue exists to prevent.
12. **`transfers_24h`: WP1.8 counts a window; WP0 says the number comes from a `/counters`
   delta across refreshes. One of the two has to go, and WP1 argues for the window — the
   orchestrator has to pick.** WP0's position is stated in two places: its open issue 10
   ("the client fills `transfers_total` and leaves `transfers_24h` `None` until it derives the
   rate", with counting one page ruled out) and the docstring of WP0.7's
   `test_the_idmd_transfer_page_is_not_a_day`, which asserts the captured page spans under
   eleven hours and concludes that `nft_transfers_24h` should come from the `/counters` delta.

   WP0 is right about the premise and, WP1 argues, wrong about the conclusion. *One captured
   page* spans 10.8 h, not a day — but that is a property of the capture, not of the endpoint:
   live, `/tokens/{IDMD}/transfers` paginates, and WP1.8 follows cursors until it sees a row
   older than `now-24h`, answering `None` if the page budget runs out first (its
   `test_transfers_24h_is_none_when_the_window_outruns_the_page_bound` pins exactly that).
   WP1.8 therefore never counts "one page" — the very thing WP0.7 forbids — and it is exact on
   the *first* refresh. The counters delta cannot be: it measures transfers between two
   *observations*, so it is either a 60-second sample scaled up (noise printed as a day) or a
   genuine 24 h delta that does not exist until the dashboard has been running for 24 h. It
   would also have to live in WP3/WP4, which means `NftStats.transfers_24h` would have no
   producer in the client that owns the field — the defect class WP0's rule 1 names.

   **Decision needed.** If the orchestrator prefers the delta, say so explicitly: WP1.8 then
   returns `None` for the field, WP0.7's docstring stands as written, and WP3/WP4 gain the
   derivation — rather than both packages half-filling one field. If the orchestrator prefers
   the window, WP0.7's docstring needs its last sentence amended (WP0's file, WP0's edit).
   There is no fixture question attached either way: WP0 ships **no** fixture file at all
   (its *Fixture ownership* section, and a root-level `tests/fixtures/surf/idmd_transfers_page1.json`
   would fail WP0.6's `test_the_fixtures_root_holds_directories_only`), so
   `tests/fixtures/surf/client/idmd_transfers_page1.json` from WP1.2 is the only slice of this
   capture that exists.
13. **WP1.8 depends on two Blockscout v2 paths; one is capture-proven and one is not.**
   `/tokens/{IDMD}/transfers` is where `identity_transfers_page1.json` came from.
   `/addresses/{IDENTITY_REGISTRY}/logs` is *not* in the capture set — WP1.8's first step
   curls both. If the log view is missing on this Blockscout build, `written` degrades to
   `None` (the widget renders `— / 2000`) and the orchestrator gets told; the fallback is
   **not** a windowed `eth_getLogs` count (see issue 9) and **not** a months-long archive
   backfill on a keyless pool.
14. **The two `block_number` fields now have producers, and WP0.4's prose needs one word
   changed to match.** Reported, not fixed — `surf_models.py` is WP0's file. WP0.4 names WP1.3
   and WP1.4 as the producer of *every* field on `NonceSet` and `ChainState`, but its
   `ChainState` docstring and its *Produces* line both say "**seven** `aggregate3` sub-calls".
   Filling `block_number` from the same round takes it to **eight**: the added leg is
   `MULTICALL3.getBlockNumber()` (selector `0x42cbb15c`, recomputed with this repo's keccak
   during planning), and `NonceSet.block_number` comes from a fourth `eth_blockNumber` leg in
   WP1.3's batch. Neither costs a round trip; both were previously `None` forever, invisibly,
   because a defaulted field is not "required" (see WP1.2's new `declared - passed`
   assertion). Two consequences for WP0 to accept or reject:
   - change "seven" to "eight" in `ChainState`'s docstring and in WP0.4's *Produces* line;
   - optionally promote the selector to `surf_addresses` as `SEL_GET_BLOCK_NUMBER` with its
     `getBlockNumber()` preimage, which WP0.2's parametrised preimage test then recomputes for
     free. Until then it lives as the module-private `surf_client._SEL_GET_BLOCK_NUMBER`, the
     same arrangement as `_SEAPORT` (issue 3). WP1 will not edit `surf_addresses`.

   **If WP0 would rather drop both fields than have them filled**, that is a coherent answer
   too — `NonceSet` and `ChainState` lose `block_number`, WP4's field table and `_pool_chain`'s
   `"block"` key lose their source, and the hero says so. What is not acceptable is the state
   this issue closes: declared, read downstream, and produced by nobody.
