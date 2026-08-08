# WP0 — Data contract, addresses, captures

**Goal:** Freeze the surf dashboard's constant surface (`data/surf_addresses.py`) and its
flat-dict and model contract (`data/surf_models.py`), and commit the real 2026-08-08 captures
as the single source material every later work package slices from — with every number those
packages hardcode pinned to its capture in exactly one place, so they can be written in
parallel against one interface with no network and no invented values.

**Dependencies:** none. **This WP is strictly sequential and first** — `data/surf_client.py`,
`analytics/surf_signals.py`, `widgets/surf/*`, `data/surf_cache.py` + `data/surf_manager.py`,
`screens/surf.py` and the registration package all import `surf_addresses` / `surf_models`, and
each of them cuts its own test data out of `tests/fixtures/surf/captures/`. Nothing else may
start until WP0.8 is green.

**Owner note:** one agent, one branch (`surf-dashboard`, already checked out). This WP owns and
creates `maxpane_dashboard/data/surf_addresses.py`, `maxpane_dashboard/data/surf_models.py`,
`tests/surf_fixtures.py`, `tests/data/test_surf_addresses.py`, `tests/data/test_surf_models.py`,
`tests/data/test_surf_captures.py` and `tests/fixtures/surf/captures/`. It touches **no**
existing file except adding new ones (no `app.py`, no `__main__.py`, no `game_select.py` —
those belong to the registration WP, late).

**WP0 writes no fixture files.** That is a decision taken before the WP starts, not an
omission — see *Fixture ownership* below. It removed nine tasks and ~1,000 lines from an
earlier revision of this plan.

### Ground rules that apply to every task below

- Run pytest as `.venv/bin/python -m pytest` (system `python3` has no `pydantic`/`httpx`).
- No test may touch the network. WP0 ships no I/O code at all, so this is structural here:
  `surf_addresses` and `surf_models` import nothing but the stdlib, and a test asserts it.
- **A failed read is `None`, never `0`.** Every optional numeric in `surf_models` is typed
  `X | None` and defaults to `None` where a default exists. No model field defaults to `0`.
- **WP0.4 is the model vocabulary, and it is the only one.** WP1's *Consumes* tables and
  WP4's "Exact shapes WP4 reads" table are restatements of `CONSTRUCTOR_KWARGS`, not
  independent drafts — build WP0.4 first, then have both restate from the module. Three
  vocabularies for one dataclass is not a merge conflict that surfaces: the producer raises
  `TypeError` and the consumer's `getattr(..., None)` returns `None` forever, so the
  dashboard renders a dark hero with a green suite behind it.
- Every value in this plan (checksums, topic hashes, selectors, supply figures, tx hashes,
  burn totals) was computed or read during planning from `maxpane_dashboard/data/keccak.py` and
  the captures in `tests/fixtures/surf/captures/`. Do not "correct" one from memory — recompute.
- Commit after each task. Messages use the repo's `type(scope): subject` form.

---

### Fixture ownership — decided before WP0 starts

*(Work packages are named by the module they own in this section. The numbering used in the
older prose elsewhere in this file does not match the numbering the other plan documents use,
so a WP number here would be ambiguous; a path is not.)*

An earlier revision of this plan had WP0 carve **17 fixture files** out of the captures, ship
`scripts/slice_surf_fixtures.py` and a `tests/surf_fixtures.load_fixture`, and guard the lot
with a reproducibility test. **Nothing downstream consumed any of it** — every one of the 17
filenames, plus `FIXTURES` / `load_fixture` / `payload` / `announce_rows` and the slicer, was
grepped against the other six plan documents and appears in none of them. Instead:

- `data/surf_client.py`'s WP re-slices the same captures into `tests/fixtures/surf/client/`
  under different names (`announce_txs_page1.json` vs WP0's `announce_txs.json`,
  `idmd_token.json` vs `blockscout_idmd_token.json`, …) behind its own private `load_fixture`.
- `analytics/surf_signals.py`'s WP cuts a third slice into `tests/fixtures/surf/signals/`.
- The widget, cache/manager and screen WPs use no fixture file at all — they inline the values
  they need.

That is three copies of the same 2026-08-08 payloads under three provenance conventions, with
one reproducibility check covering only the copy nobody reads.

It is also **not** fixable by pointing the consumers at WP0's copies: they need shapes WP0's
slices deliberately do not have. The client's tests need the **full untrimmed pages wrapped as
Blockscout serves them** (`{"items": [21 | 30 | 50 rows], "next_page_params": null}`) because
pagination and the poisoning filter are exactly what they exercise; WP0's slices were 8/7/11
rows with fields dropped by `trim_tx`. The signals WP needs a decoded-message list, not a tx
list. Retrofitting either onto WP0's shapes would rewrite suites those WPs have already
specified in full — the signals plan states its 135 tests were executed end to end against its
own slice.

**Decision: WP0 owns the captures and pins their facts; each consuming work package owns its
own slices.**

| | Owner | Path |
|---|---|---|
| raw captures (the provenance for everything) | WP0 | `tests/fixtures/surf/captures/` |
| the shared capture reader | WP0 | `tests/surf_fixtures.py` |
| the fact pins | WP0 | `tests/data/test_surf_captures.py` |
| client slices | `data/surf_client.py`'s WP | `tests/fixtures/surf/client/` |
| signals slice | `analytics/surf_signals.py`'s WP | `tests/fixtures/surf/signals/` |
| anything a later WP needs | that WP | `tests/fixtures/surf/<its-own-dir>/` |

Two rules make that hold:

1. **The root of `tests/fixtures/surf/` holds directories only** — no loose `*.json`. WP0.6
   asserts it. This is what stops one WP's file landing in another WP's glob — the failure the
   signals WP already writes down as a hard rule, and that the client WP already follows by
   putting its slices in `client/`.
2. **The facts live in one place.** Every number a later work package hardcodes — the burn
   total, the four poisoning rows, the 1148-vs-1132 holder disagreement, the parity spread,
   the nonce ladder — is asserted against the capture in `tests/data/test_surf_captures.py`
   (WP0.7). A re-capture that moves one of them fails once, in the file that owns it, instead
   of once per copy or (the current state) nowhere.

What went away with the 17 fixtures, and where each case now lives:

| dropped fixture | why it existed | where the case lives now |
|---|---|---|
| `announce_txs.json`, `dev_wallet_txs_page1.json`, `ops_wallet_txs.json`, `ops_token_transfers.json`, `idmd_transfers_page1.json` | trimmed tx/transfer slices | the consuming WP's own slice; the *facts* they asserted are WP0.7 |
| the four `market_*.json` and five `blockscout_*.json` | verbatim capture copies | read the capture — a verbatim copy of a committed file is not a fixture |
| `announce_txs_hostile.json` | synthetic Textual-markup calldata | the signals and widget WPs each build hostile input inline in the test that needs it. No real capture contains a `[`, and WP0.7 asserts that, so the synthetic-ness stays documented |
| `dev_wallet_deploy_tx.json` | synthetic contract creation | the manager WP builds `created_contract=` rows inline. WP0.7 pins both that no capture holds a creation *and* the only real deploy evidence (`imd_info.json`) |
| `rpc_state_batch.json` | derived `eth_call` words | the client WP owns `encode_positions_return()` / `encode_slot0_return()`. WP0.7 pins the pool price those encoders must derive from — see open issue 12 |

If a later WP does want a shared slice reader, it is added to `tests/surf_fixtures.py` next to
`capture()` — not copied into a test module, and not pre-built here: a helper with no caller is
the defect this decision removed.

---

### Task WP0.1: Address constants module

**Files:**
- Create: `maxpane_dashboard/data/surf_addresses.py`
- Test: `tests/data/test_surf_addresses.py`

**Interfaces:**
- Produces: `DEV_WALLET`, `OPS_WALLET`, `ANNOUNCE`, `IMD_TOKEN`, `IDMD_NFT`,
  `IDENTITY_RENDERER`, `IDENTITY_REGISTRY`, `POOL_V3`, `NFPM`, `BURN_EXECUTOR`,
  `FP_TOKEN_BASE`, `ERC8004_REGISTRY`, `POOL_MANAGER_V4`, `WETH` — all `str`, EIP-55
  checksummed; `LP_POSITION_ID: int = 1167726`. Additive secondary constants
  `SEAPORT`, `UNIVERSAL_ROUTER`, `RELAY_DEPOSITORY`, `FWA_SPLITTER`, `DEV_SWEEP`,
  `LP_FEE_SINK_A`, `LP_FEE_SINK_B`, `CREATE2_FACTORY`, `VIBECOINS_HOOK`, `IDMD_BASE_TWIN`,
  `KRAKEN_HOT`, `ZERO_ADDRESS`, and `LABELED_ADDRESSES: tuple[str, ...]`.
- Consumes: `maxpane_dashboard.data.keccak.keccak256` (test only, to recompute EIP-55).

**Steps:**

- [ ] Write the failing test `tests/data/test_surf_addresses.py`:

```python
"""Frozen address surface for the surf dashboard.

Every constant here is re-derived in-test: the checksum is recomputed with the
repo's own keccak, so a transposed nibble pasted from a research doc fails here
instead of silently reading a different contract on mainnet.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.keccak import keccak256

# The 14 names the module contract froze, plus the additive label targets.
PRIMARY = (
    "DEV_WALLET",
    "OPS_WALLET",
    "ANNOUNCE",
    "IMD_TOKEN",
    "IDMD_NFT",
    "IDENTITY_RENDERER",
    "IDENTITY_REGISTRY",
    "POOL_V3",
    "NFPM",
    "BURN_EXECUTOR",
    "FP_TOKEN_BASE",
    "ERC8004_REGISTRY",
    "POOL_MANAGER_V4",
    "WETH",
)
SECONDARY = (
    "SEAPORT",
    "UNIVERSAL_ROUTER",
    "RELAY_DEPOSITORY",
    "FWA_SPLITTER",
    "DEV_SWEEP",
    "LP_FEE_SINK_A",
    "LP_FEE_SINK_B",
    "CREATE2_FACTORY",
    "VIBECOINS_HOOK",
    "IDMD_BASE_TWIN",
    "KRAKEN_HOT",
    "ZERO_ADDRESS",
)


def to_checksum(addr: str) -> str:
    """EIP-55, recomputed with the repo's keccak (not hashlib.sha3_256)."""
    body = addr.lower().removeprefix("0x")
    digest = keccak256(body.encode("ascii")).hex()
    return "0x" + "".join(
        ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch
        for i, ch in enumerate(body)
    )


@pytest.mark.parametrize("name", PRIMARY + SECONDARY)
def test_every_address_is_checksummed(name: str) -> None:
    value = getattr(A, name)
    assert isinstance(value, str), name
    assert len(value) == 42 and value.startswith("0x"), name
    assert value == to_checksum(value), f"{name} is not EIP-55 checksummed"


def test_pinned_identities() -> None:
    """The four addresses a typo would silently redirect to someone else."""
    assert A.ANNOUNCE == "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
    assert A.IMD_TOKEN == "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
    assert A.IDMD_NFT == "0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D"
    assert A.POOL_V3 == "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"


def test_lp_position_id() -> None:
    assert A.LP_POSITION_ID == 1167726
    assert isinstance(A.LP_POSITION_ID, int)


def test_addresses_are_distinct() -> None:
    values = [getattr(A, n).lower() for n in PRIMARY + SECONDARY]
    assert len(set(values)) == len(values), "duplicate address constant"


def test_labeled_addresses_is_the_union() -> None:
    assert set(A.LABELED_ADDRESSES) == {
        getattr(A, n) for n in PRIMARY + SECONDARY
    }


def test_module_imports_nothing_but_stdlib() -> None:
    """Constants must be importable from a widget test with no I/O stack."""
    import inspect

    source = inspect.getsource(A)
    for banned in ("import httpx", "import asyncio", "from textual", "import requests"):
        assert banned not in source, f"surf_addresses must not {banned}"
```

- [ ] Run it and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
      → collection error `ModuleNotFoundError: No module named
      'maxpane_dashboard.data.surf_addresses'` (all 27 parametrised cases error).

- [ ] Write the minimal implementation `maxpane_dashboard/data/surf_addresses.py`:

```python
"""Vendored address constants for the surf dashboard (surfsurf.eth mission control).

Every address below was read from chain during the 2026-08-08 research sweep and
is EIP-55 checksummed; ``tests/data/test_surf_addresses.py`` recomputes each
checksum with this repo's keccak, so a mistyped nibble cannot ship.

Two hazards this module exists to contain:

* **Address poisoning is live on the ops wallet.** ``frenpet.eth``'s history
  contains 1-gwei sends from ``0x61CCFD5d…F14E`` (imitating :data:`LP_FEE_SINK_B`
  ``0x61CC704c…f14E``) and from ``0xF3083828…0Ee6`` / ``0xF3087598…0eE6``
  (imitating :data:`LP_FEE_SINK_A` ``0xF3084Bc7…0eE6``).  The defence is an
  allowlist, not a blocklist: only addresses in :data:`KNOWN_LABELS` may render
  as a trusted label; everything else renders dimmed and truncated.  Never add a
  spoof here "so it can be flagged" — that inverts the guarantee.
* **Token name/symbol are owner-mutable** (FP → VIBE → IMD, twice already).  The
  dashboard trusts :data:`IMD_TOKEN`, never a name.

Gate hazard (read before wiring signal 3): ``identityAllowed()`` exists on
*both* the IDMD NFT and the working registry.  The NFT's owner is bricked (the
Arachnid CREATE2 factory owns it), so the NFT's flag is permanently ``false``
and reading it would render a gate that can never open.  The live gate is
:data:`IDENTITY_REGISTRY`.
"""

from __future__ import annotations

# --- EOAs -------------------------------------------------------------------
#: Primary dev EOA, ENS surfsurf.eth.  Deploys, mints, bridges, plays FWA.
DEV_WALLET = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"
#: Second dev EOA, ENS frenpet.eth.  Holds the LP position and funds burns.
OPS_WALLET = "0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095"
#: The announcement channel EOA ("the agent").  Emits **no logs** — poll nonces.
ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"

# --- Contracts (Ethereum mainnet) -------------------------------------------
#: ``BridgedFP is OFT`` — LayerZero V2 wrapper around Base FP.  Name is mutable.
IMD_TOKEN = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
#: identity.md ERC-721, 2000 supply, fully on-chain SVG.  Ownership bricked.
IDMD_NFT = "0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D"
#: Immutable pure renderer behind ``IDMD_NFT.tokenURI``.
IDENTITY_RENDERER = "0x3F559eF271B245E7e754fEAD7d50cd55aC981423"
#: The *working* identity store; owner = ANNOUNCE.  This is the gate to poll.
IDENTITY_REGISTRY = "0x000008061ccac597a321a75E3470a3E8fAF9dD2d"
#: Uniswap v3 IMD/WETH, 1% fee.  token0 = WETH, token1 = IMD (address order).
POOL_V3 = "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"
#: Uniswap v3 NonfungiblePositionManager — holder of LP_POSITION_ID.
NFPM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
#: ``bridgeToBaseBurnReceiver()`` — LP-fee IMD leaves mainnet supply here.
BURN_EXECUTOR = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
#: Canonical ERC-8004 Trustless-Agents registry (ANNOUNCE registered here).
ERC8004_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
#: Uniswap v4 PoolManager — ``Initialize`` with hooks != 0x0 IS the launch.
POOL_MANAGER_V4 = "0x000000000004444c5dc75cB358380D2e3dE08A90"
#: Canonical WETH9 — the pool's token0.
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

# --- Base chain (read-only bridge counterpart) ------------------------------
#: The original Fren Pet ERC-20 on Base.  IMD mints 1:1 against FP locked here.
FP_TOKEN_BASE = "0xFF0C532FDB8Cd566Ae169C1CB157ff2Bdc83E105"

# --- Secondary label targets (additive; not part of the frozen 14) ----------
#: Seaport 1.6 — 86% of IDMD secondary volume routes through it.
SEAPORT = "0x0000000000000068F116a894984e2DB1123eB395"
UNIVERSAL_ROUTER = "0xd92A36B0000531EF3063dEd4De20A0783308446C"
#: Relay depository — the dev's cross-chain funding route.
RELAY_DEPOSITORY = "0x4cD00E387622C35bDDB9b4c962C136462338BC31"
#: FWA Splitter — already vendored in ``fwa_client``; the dev claims from it.
FWA_SPLITTER = "0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe"
#: Where FWA winnings are swept, ~1 min after each claim.
DEV_SWEEP = "0x58239Ad01D72811F179bAE08983F95Ac30274e55"
#: Unidentified recipients of LP-fee ETH.  Labelled because the poisoners
#: imitate exactly these two strings.
LP_FEE_SINK_A = "0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6"
LP_FEE_SINK_B = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"
#: Arachnid CREATE2 proxy — the accidental owner of IDMD_NFT.
CREATE2_FACTORY = "0x4e59b44847b379578588920cA78FbF26c0B4956C"
#: The dev's *existing* v4 hook (Vibecoins launchpad) — NOT the coming one.
VIBECOINS_HOOK = "0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44"
#: Stalled Base twin of the NFT (unverified source).
IDMD_BASE_TWIN = "0x0000C0484F4626e368dFb909aBa107f7C97b6B1D"
#: CEX hot wallet that funded the 2026-08-07 LP add (33.693 ETH inbound).
KRAKEN_HOT = "0xf70da97812CB96acDF810712Aa562db8dfA3dbEF"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

#: The Uniswap v3 position NFT that holds all IMD liquidity.  Owner = OPS_WALLET;
#: a liquidity decrease here is the LP MIGRATION signal.
LP_POSITION_ID = 1167726

#: Every address this module labels, in declaration order.
LABELED_ADDRESSES: tuple[str, ...] = (
    DEV_WALLET,
    OPS_WALLET,
    ANNOUNCE,
    IMD_TOKEN,
    IDMD_NFT,
    IDENTITY_RENDERER,
    IDENTITY_REGISTRY,
    POOL_V3,
    NFPM,
    BURN_EXECUTOR,
    ERC8004_REGISTRY,
    POOL_MANAGER_V4,
    WETH,
    FP_TOKEN_BASE,
    SEAPORT,
    UNIVERSAL_ROUTER,
    RELAY_DEPOSITORY,
    FWA_SPLITTER,
    DEV_SWEEP,
    LP_FEE_SINK_A,
    LP_FEE_SINK_B,
    CREATE2_FACTORY,
    VIBECOINS_HOOK,
    IDMD_BASE_TWIN,
    KRAKEN_HOT,
    ZERO_ADDRESS,
)
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
      (31 passed).
- [ ] Commit:
      `git add maxpane_dashboard/data/surf_addresses.py tests/data/test_surf_addresses.py && git commit -m "feat(surf): vendor the surf address constants with checksum-recomputing tests"`

---

### Task WP0.2: Topics, preimages and selectors

**Files:**
- Modify: `maxpane_dashboard/data/surf_addresses.py`
- Test: `tests/data/test_surf_addresses.py`

**Interfaces:**
- Produces: `TOPIC_TRANSFER`, `TOPIC_IDENTITY_HASH_UPDATED`, `TOPIC_V4_INITIALIZE`,
  `TOPIC_SEAPORT_ORDER_FULFILLED` (`str`, `0x` + 64 lowercase hex);
  `TOPIC_PREIMAGES: dict[str, str]`; `SEL_POSITIONS`, `SEL_IDENTITY_ALLOWED`,
  `SEL_TOTAL_SUPPLY`, `SEL_SLOT0`, `SEL_NAME`, `SEL_SYMBOL`, `SEL_OWNER_OF`
  (`str`, `0x` + 8 hex); additive `SELECTOR_PREIMAGES: dict[str, str]`.
  `SEL_OWNER_OF` exists because the PRD hero key `lp_owner_ok` needs
  `NFPM.ownerOf(LP_POSITION_ID)`; without it `ChainState.lp_owner` would be a field no
  work package can populate. The parametrised preimage test recomputes it like the rest,
  so the literal is self-verifying.
- Consumes: `keccak256_hex` (test only).

**Steps:**

- [ ] Append the failing tests to `tests/data/test_surf_addresses.py`:

```python
# ---------------------------------------------------------------------------
# topics + selectors, recomputed from their preimages
# ---------------------------------------------------------------------------

from maxpane_dashboard.data.keccak import keccak256_hex  # noqa: E402


@pytest.mark.parametrize("name,preimage", sorted(A.TOPIC_PREIMAGES.items()))
def test_topic_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))


@pytest.mark.parametrize("name,preimage", sorted(A.SELECTOR_PREIMAGES.items()))
def test_selector_matches_its_preimage(name: str, preimage: str) -> None:
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))[:10]


def test_preimage_maps_cover_exactly_the_constants() -> None:
    """A vendored hash with no preimage is unverifiable; a preimage with no
    constant is dead weight.  Both are failures."""
    topic_names = {n for n in dir(A) if n.startswith("TOPIC_") and n != "TOPIC_PREIMAGES"}
    sel_names = {n for n in dir(A) if n.startswith("SEL_")}
    assert set(A.TOPIC_PREIMAGES) == topic_names
    assert set(A.SELECTOR_PREIMAGES) == sel_names


def test_pinned_topic_values() -> None:
    """Pinned literals, so a *matching pair* of typos (preimage + hash) fails.

    These four hexes were computed during planning with this repo's keccak and
    cross-checked against docs/surf_PRD.md §5.
    """
    assert A.TOPIC_TRANSFER == (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )
    assert A.TOPIC_IDENTITY_HASH_UPDATED == (
        "0x57c85cf86ae80c7b372281c7dd1b0f8b99de39e76d757725a32b6bd88f7ff1b6"
    )
    assert A.TOPIC_V4_INITIALIZE == (
        "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
    )
    assert A.TOPIC_SEAPORT_ORDER_FULFILLED == (
        "0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31"
    )


def test_pinned_selector_values() -> None:
    assert A.SEL_POSITIONS == "0x99fbab88"
    assert A.SEL_IDENTITY_ALLOWED == "0xac8f3de6"
    assert A.SEL_TOTAL_SUPPLY == "0x18160ddd"
    assert A.SEL_SLOT0 == "0x3850c7bd"
    assert A.SEL_NAME == "0x06fdde03"
    assert A.SEL_SYMBOL == "0x95d89b41"


def test_hash_strings_are_lowercase_and_sized() -> None:
    for name in A.TOPIC_PREIMAGES:
        value = getattr(A, name)
        assert len(value) == 66 and value == value.lower()
    for name in A.SELECTOR_PREIMAGES:
        value = getattr(A, name)
        assert len(value) == 10 and value == value.lower()
```

- [ ] Run and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
      → `AttributeError: module 'maxpane_dashboard.data.surf_addresses' has no attribute
      'TOPIC_PREIMAGES'` at collection of the two parametrised tests.

- [ ] Append the implementation to `maxpane_dashboard/data/surf_addresses.py`:

```python
# --- Event topics -----------------------------------------------------------
# Vendored hashes with their preimages beside them; the preimages are not
# decoration — tests/data/test_surf_addresses.py recomputes every value from
# them, and pins the literals too, so a matched pair of typos still fails.
#
# ``IdentityHashUpdated`` was taken from the verified IdentityMD source
# (captures/identity_contract.json): ``event IdentityHashUpdated(uint256
# indexed id, string ipfsHash, bool permanent)``.  Indexed-ness does not enter
# the topic0 preimage; the *types* do.

TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TOPIC_IDENTITY_HASH_UPDATED = (
    "0x57c85cf86ae80c7b372281c7dd1b0f8b99de39e76d757725a32b6bd88f7ff1b6"
)
TOPIC_V4_INITIALIZE = (
    "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
)
TOPIC_SEAPORT_ORDER_FULFILLED = (
    "0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31"
)

#: constant name -> the exact Solidity event signature it hashes.
TOPIC_PREIMAGES: dict[str, str] = {
    "TOPIC_TRANSFER": "Transfer(address,address,uint256)",
    "TOPIC_IDENTITY_HASH_UPDATED": "IdentityHashUpdated(uint256,string,bool)",
    "TOPIC_V4_INITIALIZE": (
        "Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)"
    ),
    "TOPIC_SEAPORT_ORDER_FULFILLED": (
        "OrderFulfilled(bytes32,address,address,address,"
        "(uint8,address,uint256,uint256)[],"
        "(uint8,address,uint256,uint256,address)[])"
    ),
}

# --- Function selectors -----------------------------------------------------
SEL_POSITIONS = "0x99fbab88"        # NFPM.positions(uint256)
SEL_IDENTITY_ALLOWED = "0xac8f3de6"  # IdentityRegistry.identityAllowed()
SEL_TOTAL_SUPPLY = "0x18160ddd"      # ERC-20/721 totalSupply()
SEL_SLOT0 = "0x3850c7bd"             # UniswapV3Pool.slot0()
SEL_NAME = "0x06fdde03"              # ERC-20 name()  — mutable, display only
SEL_SYMBOL = "0x95d89b41"            # ERC-20 symbol() — mutable, display only
SEL_OWNER_OF = "0x6352211e"          # ERC-721 ownerOf(uint256) — NFPM position

#: constant name -> the exact Solidity function signature it hashes.
SELECTOR_PREIMAGES: dict[str, str] = {
    "SEL_POSITIONS": "positions(uint256)",
    "SEL_IDENTITY_ALLOWED": "identityAllowed()",
    "SEL_TOTAL_SUPPLY": "totalSupply()",
    "SEL_SLOT0": "slot0()",
    "SEL_NAME": "name()",
    "SEL_SYMBOL": "symbol()",
    "SEL_OWNER_OF": "ownerOf(uint256)",
}
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
      (11 new cases from the two parametrised tests — 4 topics + 7 selectors — plus the
      4 assertion tests).
- [ ] Prove the test bites (decoder-shaped code, house rule): temporarily change
      `TOPIC_PREIMAGES["TOPIC_V4_INITIALIZE"]` to drop the trailing `int24`, run
      `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k preimage -v`
      → `test_topic_matches_its_preimage[TOPIC_V4_INITIALIZE-...]` FAILS. Restore.
- [ ] Commit:
      `git add maxpane_dashboard/data/surf_addresses.py tests/data/test_surf_addresses.py && git commit -m "feat(surf): vendor topics and selectors, each recomputed from its preimage in test"`

---

### Task WP0.3: KNOWN_LABELS and the poisoning allowlist

**Files:**
- Modify: `maxpane_dashboard/data/surf_addresses.py`
- Test: `tests/data/test_surf_addresses.py`

**Interfaces:**
- Produces: `KNOWN_LABELS: dict[str, str]` — **lowercase** address → short display label.
- Consumed by: `data/surf_client.py` (its dev-activity task does the lookup and fills
  `DevTx.counterparty_label`, where the row's provenance still exists) and
  `data/surf_manager.py` (derives `dev_activity[].counterparty_known` =
  `counterparty_label is not None`). **The widgets never import it**: `widgets/surf/activity.py`
  receives the resolved `counterparty` string plus the `counterparty_known` boolean, and the
  widget package ships an AST test that fails if any surf widget module imports
  `surf_addresses` at all.

**Steps:**

- [ ] Append the failing tests:

```python
# ---------------------------------------------------------------------------
# KNOWN_LABELS — the allowlist that defeats address poisoning
# ---------------------------------------------------------------------------

# Live spoofs found in frenpet.eth's history on 2026-08-08.  Each sent exactly
# 1 gwei so it would appear in the wallet's tx list next to the real recipient.
LIVE_SPOOFS = (
    "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",  # imitates LP_FEE_SINK_B
    "0xf3083828702c1989710ceca517412071c2f60ee6",  # imitates LP_FEE_SINK_A
    "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",  # imitates LP_FEE_SINK_A
)


def test_known_labels_keys_are_lowercase_addresses() -> None:
    for key in A.KNOWN_LABELS:
        assert key == key.lower(), key
        assert len(key) == 42 and key.startswith("0x"), key


def test_known_labels_covers_every_labeled_address() -> None:
    assert set(A.KNOWN_LABELS) == {a.lower() for a in A.LABELED_ADDRESSES}


def test_labels_are_short_enough_for_a_narrow_column() -> None:
    for key, label in A.KNOWN_LABELS.items():
        assert label.strip() == label and label, key
        assert len(label) <= 22, f"{label!r} will blow up the activity column"


def test_no_spoof_is_ever_labeled() -> None:
    """The defence is an allowlist.  A poisoned lookalike must fall through to
    the dimmed unknown rendering, never to a label."""
    for spoof in LIVE_SPOOFS:
        assert spoof not in A.KNOWN_LABELS


def test_the_real_fee_sinks_are_labeled_and_differ_from_their_spoofs() -> None:
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_A.lower()]
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_B.lower()]
    assert A.LP_FEE_SINK_A.lower() not in LIVE_SPOOFS
    assert A.LP_FEE_SINK_B.lower() not in LIVE_SPOOFS
    # They differ only in the middle — first 6 and last 4 chars collide.
    assert A.LP_FEE_SINK_B.lower()[:6] == LIVE_SPOOFS[0][:6]
    assert A.LP_FEE_SINK_B.lower()[-4:] == LIVE_SPOOFS[0][-4:]
```

- [ ] Run and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k labels -v`
      → `AttributeError: … has no attribute 'KNOWN_LABELS'` in all five tests.

- [ ] Append the implementation:

```python
#: Lowercase address -> the label ``SurfDevActivity`` may render as trusted.
#:
#: This is an **allowlist**.  Anything absent renders dimmed as
#: ``0x`` + first 8 + ``…`` + last 6 and is never styled as known.  Do not add
#: spoof addresses here; the poisoning defence is that they fall through.
KNOWN_LABELS: dict[str, str] = {
    DEV_WALLET.lower(): "dev · surfsurf.eth",
    OPS_WALLET.lower(): "ops · frenpet.eth",
    ANNOUNCE.lower(): "announce channel",
    IMD_TOKEN.lower(): "IMD token",
    IDMD_NFT.lower(): "IDMD NFT",
    IDENTITY_RENDERER.lower(): "IdentityRenderer",
    IDENTITY_REGISTRY.lower(): "IdentityRegistry",
    POOL_V3.lower(): "IMD/WETH v3 pool",
    NFPM.lower(): "Uniswap v3 NFPM",
    BURN_EXECUTOR.lower(): "BurnExecutor",
    ERC8004_REGISTRY.lower(): "ERC-8004 registry",
    POOL_MANAGER_V4.lower(): "v4 PoolManager",
    WETH.lower(): "WETH",
    FP_TOKEN_BASE.lower(): "FP token · Base",
    SEAPORT.lower(): "Seaport",
    UNIVERSAL_ROUTER.lower(): "UniversalRouter",
    RELAY_DEPOSITORY.lower(): "Relay depository",
    FWA_SPLITTER.lower(): "FWA Splitter",
    DEV_SWEEP.lower(): "dev sweep wallet",
    LP_FEE_SINK_A.lower(): "LP-fee sink A",
    LP_FEE_SINK_B.lower(): "LP-fee sink B",
    CREATE2_FACTORY.lower(): "CREATE2 factory",
    VIBECOINS_HOOK.lower(): "Vibecoins v4 hook",
    IDMD_BASE_TWIN.lower(): "IDMD twin · Base",
    KRAKEN_HOT.lower(): "Kraken hot wallet",
    ZERO_ADDRESS.lower(): "0x0 mint/burn",
}
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
- [ ] Prove the test bites: temporarily add
      `"0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e": "LP-fee sink B"` to `KNOWN_LABELS`,
      run `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k spoof -v`
      → `test_no_spoof_is_ever_labeled` FAILS (and
      `test_known_labels_covers_every_labeled_address` too). Remove the line.
- [ ] Commit:
      `git add maxpane_dashboard/data/surf_addresses.py tests/data/test_surf_addresses.py && git commit -m "feat(surf): add KNOWN_LABELS allowlist with live-spoof exclusion tests"`

---

### Task WP0.4: Model dataclasses

**Files:**
- Create: `maxpane_dashboard/data/surf_models.py`
- Test: `tests/data/test_surf_models.py`

**Interfaces:**

> **This task is the single source of truth for the model vocabulary, and it must land
> before any WP1 or WP4 code is written.** The field lists below are not a sketch: WP1
> constructs these dataclasses with exactly these keyword names and WP4 reads exactly these
> attribute names. Three rules kept the list honest, and each one deleted a field that an
> earlier draft carried:
>
> 1. **Every field has exactly one named producer.** A field no work package can fill is a
>    field WP4 reads as `None` forever while every test stays green. `lp_owner` survived
>    because WP0.2 now vendors `SEL_OWNER_OF`; `identities_written` did *not* survive on
>    `ChainState` — the verified IdentityMD source exposes `totalSupply` and
>    `identityAllowed` and **no written-hash counter**, so that fact lives on
>    `NftStats.written`, whose producer is named and implemented: WP1.8's
>    `_count_identities_written()`.
> 2. **Models mirror the chain, the flat dict mirrors the PRD.** The getter is
>    `identityAllowed()`, so the field is `identity_allowed`; the hero key is `gate_open`.
>    Same for `imd_supply_wei` → `imd_supply`, `value_wei` → `value_eth`. A model field and
>    its flat key are *allowed* to differ and the mapping is written down in WP4 — what is
>    not allowed is WP4 reading the flat name off the model, which is how the first draft
>    ended up with `state.lp_imd`.
> 3. **The client returns raw; interpretation is pure-function work — except where the frozen
>    model leaves no choice.** PRD §6 rule 4. So `ChannelTx` carries `input_hex` and *not*
>    `kind`/`text`: WP4 derives both through the pure layer (`classify_channel_tx`,
>    `decode_utf8_calldata`), which is what gives those functions exactly one caller each.
>    `DevTx` is the deliberate exception — it arrives **pre-labelled** from WP1.6, because
>    `counterparty`, `counterparty_label` and `kind` are declared below **without defaults**
>    and a constructor cannot leave a non-default field unset. That no-default declaration is
>    the artifact WP1's *Decode ownership* table and WP4's ownership section both cite when
>    they assign the sender filter, the `KNOWN_LABELS` lookup and the `kind` vocabulary to
>    WP1.6, so it is load-bearing in two other plans: **do not delete the three fields.** The
>    manager derives exactly one thing from them, `counterparty_known`
>    (= `counterparty_label is not None`).
>
> `lp_imd_wei` / `lp_weth_wei` are the one pair here that no single `eth_call` returns:
> `positions()` gives liquidity `L` and the tick bounds, `slot0()` gives the current
> `sqrtPriceX96`, and the token amounts are the standard v3 closed form over the three.
> They live on `ChainState` rather than being derived downstream because the derivation
> needs `tickLower`/`tickUpper`, which exist **only** inside WP1.4's `positions()` decode.
> A manager holding just `lp_liquidity` and `sqrt_price_x96` could only compute them under
> a full-range assumption — true today, wrong the day the LP is re-added concentrated, and
> that day is signal 2's entire subject. `MarketSnapshot.pool_imd`/`pool_weth` are a
> *different* number (DexScreener's whole-pool reserves, all positions) and are kept for
> the market panel's cross-check, not for the hero.

- Produces (exact signatures — WP1 constructs these, WP4 consumes them; the *producer*
  column is binding, and a field with no producer is a defect to report, not to stub):

  - `NonceSet(announce: int|None, dev: int|None, ops: int|None, block_number: int|None = None)`
    — producer WP1.3.
  - `ChainState(lp_liquidity: int|None, lp_token0: str|None, lp_token1: str|None,
    lp_fee: int|None, lp_tokens_owed0_wei: int|None, lp_tokens_owed1_wei: int|None,
    lp_imd_wei: int|None, lp_weth_wei: int|None, lp_owner: str|None,
    identity_allowed: bool|None, imd_supply_wei: int|None, sqrt_price_x96: int|None,
    pool_tick: int|None, imd_name: str|None, imd_symbol: str|None,
    block_number: int|None = None)`
    — producer WP1.4, one `aggregate3` over seven sub-calls, plus a pure derivation.
  - `ChannelTx(tx_hash: str, ts: float, nonce: int|None, from_addr: str, to_addr: str|None,
    value_wei: int, input_hex: str, method: str|None = None)`
    — producer WP1.5. Raw: no `kind`, no `text`.
  - `DevTx(tx_hash: str, ts: float, wallet_label: str, from_addr: str, to_addr: str|None,
    counterparty: str, counterparty_label: str|None, value_wei: int, method: str|None,
    kind: str, created_contract: str|None = None)`
    — producer WP1.6, which owns the address-poisoning filter *and* the label lookup. This is
    the one model that arrives pre-labelled, and the reason is in WP1's *Decode ownership*
    table: the sender==dev-wallet check only works where the row's provenance (whose page it
    came from) is still known, which is inside the client. A row that reaches the manager
    already exists, and filtering it there is one step too late.
  - `MarketSnapshot(imd_price_usd: float|None, imd_price_usd_gecko: float|None,
    imd_change_24h_pct: float|None, imd_vol_24h_usd: float|None,
    pool_liquidity_usd: float|None, pool_imd: float|None, pool_weth: float|None,
    fp_price_usd: float|None, fdv_usd: float|None, eth_usd: float|None,
    indexer_name: str|None, indexer_symbol: str|None, sources_agree: bool|None = None)`
    — producer WP1.7. `indexer_name`/`indexer_symbol` are **DexScreener's** (current);
    no GeckoTerminal string ever enters the snapshot, which is why there is no
    `indexer_name_stale` flag to carry. The onchain name/symbol live on `ChainState`.
  - `LogWindow(from_block: int|None, to_block: int|None, bridge_mints: tuple[dict, ...] = (),
    identity_updates: tuple[dict, ...] = (), v4_initializes: tuple[dict, ...] = (),
    seaport_sales: tuple[dict, ...] = ())`
    — producer WP1.9, which fills the four groups with the **raw** log rows the endpoint
    returned (`topics`, `data`, `blockNumber`, `blockTimestamp`, `transactionHash`, intact);
    WP1.9b is the hand-over guard that proves nothing was normalised away, and the decoders
    are WP4's. `seaport_sales` (not `seaport_orders`). `()` means the group was read and held
    nothing **or** that one filter failed — a frozen tuple cannot hold `None`, so WP1 keeps
    the per-group failure set privately and surfaces it through the manager's `degraded`
    list. Only a sweep where every group failed is a `None` *instead of* a `LogWindow`.
  - `NftStats(holders: int|None, total_supply: int|None, transfers_total: int|None,
    dev_holdings: int|None, transfers_24h: float|None = None, written: int|None = None,
    floor_eth: None = None)`
    — producer WP1.8, all four numbers. `transfers_total` is Blockscout's lifetime counter
    (7,411 on 2026-08-08); `transfers_24h` is the *rate* the PRD asks for, derived by
    WP1.8's `_count_transfers_24h()` — the two are separate fields precisely so a lifetime
    count can never be rendered as a daily one. `written` is the lifetime "x of 2000",
    produced by WP1.8's `_count_identities_written()` over distinct `topics[1]` on
    `/addresses/{IDENTITY_REGISTRY}/logs`. Both degrade to `None` when their page bound is
    hit inside the window, because a lower bound rendered as a total is a wrong number.
    `floor_eth` is the one deferred field; see the open issues. There is no `last_sales`
    field: realized sales are decoded from
    `LogWindow.seaport_sales` (medium tier, logs pool), not from Blockscout counters
    (slow tier, REST), and one owner beats two half-filled ones.
- Consumes: nothing (stdlib `dataclasses` only).

**Steps:**

- [ ] Write the failing test `tests/data/test_surf_models.py`:

```python
"""Interface freeze for the surf data layer.

These are cheap structural tests whose only job is to stop the contract
drifting while later work packages code against it in parallel.
"""

from __future__ import annotations

import dataclasses

import pytest

from maxpane_dashboard.data.surf_models import (
    ChainState,
    ChannelTx,
    DevTx,
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
)

ALL_MODELS = (
    NonceSet,
    ChainState,
    ChannelTx,
    DevTx,
    MarketSnapshot,
    LogWindow,
    NftStats,
)


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_are_frozen_dataclasses(model) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True


def test_nonce_set_accepts_partial_failure() -> None:
    """A batched read where one call failed is None for that leg, not 0."""
    ns = NonceSet(announce=14, dev=None, ops=38)
    assert ns.announce == 14
    assert ns.dev is None
    assert ns.ops == 38
    assert ns.block_number is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        ns.dev = 0  # type: ignore[misc]


#: The exact keyword names each producer passes.  This is the interface freeze that
#: matters: a rename anywhere now fails at *collection* in this file, in WP1's client
#: suite and in WP4's manager suite, instead of silently becoming a ``None`` hero.
#: WP1 and WP4 each import CONSTRUCTOR_KWARGS and assert the same thing against the
#: kwargs their own code passes — see WP1.2 and WP4.7.
CONSTRUCTOR_KWARGS: dict[type, tuple[str, ...]] = {
    NonceSet: ("announce", "dev", "ops", "block_number"),
    ChainState: (
        "lp_liquidity", "lp_token0", "lp_token1", "lp_fee",
        "lp_tokens_owed0_wei", "lp_tokens_owed1_wei", "lp_imd_wei",
        "lp_weth_wei", "lp_owner", "identity_allowed", "imd_supply_wei",
        "sqrt_price_x96", "pool_tick", "imd_name", "imd_symbol",
        "block_number",
    ),
    ChannelTx: (
        "tx_hash", "ts", "nonce", "from_addr", "to_addr", "value_wei",
        "input_hex", "method",
    ),
    DevTx: (
        "tx_hash", "ts", "wallet_label", "from_addr", "to_addr", "counterparty",
        "counterparty_label", "value_wei", "method", "kind", "created_contract",
    ),
    MarketSnapshot: (
        "imd_price_usd", "imd_price_usd_gecko", "imd_change_24h_pct",
        "imd_vol_24h_usd", "pool_liquidity_usd", "pool_imd", "pool_weth",
        "fp_price_usd", "fdv_usd", "eth_usd", "indexer_name", "indexer_symbol",
        "sources_agree",
    ),
    LogWindow: (
        "from_block", "to_block", "bridge_mints", "identity_updates",
        "v4_initializes", "seaport_sales",
    ),
    NftStats: (
        "holders", "total_supply", "transfers_total", "dev_holdings",
        "transfers_24h", "written", "floor_eth",
    ),
}


@pytest.mark.parametrize("model", ALL_MODELS)
def test_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    """The whole point of WP0.4.

    Three work packages code against these names in parallel.  An earlier draft of
    this plan had ChainState spelled three different ways across WP0/WP1/WP4 — the
    constructor calls would have raised TypeError and the reads would have returned
    None for the entire hero.  This test is what makes that a collection error.
    """
    assert tuple(f.name for f in dataclasses.fields(model)) == CONSTRUCTOR_KWARGS[model]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_model_constructs_from_its_documented_kwargs(model) -> None:
    """Constructing by keyword — the way every producer does — must not TypeError."""
    assert model(**{name: None for name in CONSTRUCTOR_KWARGS[model]}) is not None


def test_chain_state_all_none_is_constructible() -> None:
    """Total outage must produce a well-formed all-None state, never zeros."""
    cs = ChainState(
        lp_liquidity=None,
        lp_token0=None,
        lp_token1=None,
        lp_fee=None,
        lp_tokens_owed0_wei=None,
        lp_tokens_owed1_wei=None,
        lp_imd_wei=None,
        lp_weth_wei=None,
        lp_owner=None,
        identity_allowed=None,
        imd_supply_wei=None,
        sqrt_price_x96=None,
        pool_tick=None,
        imd_name=None,
        imd_symbol=None,
    )
    assert all(getattr(cs, f.name) is None for f in dataclasses.fields(cs))


def test_no_flat_dict_key_masquerades_as_a_model_field() -> None:
    """The reverse of the drift that produced this test.

    ``lp_imd``/``imd_supply``/``gate_open``/``value_eth``/``block`` are *flat-dict*
    keys.  WP4 must map to them from the wei-native model fields, and a getattr for
    the flat name would quietly yield the default forever.
    """
    flat_only = {
        "lp_imd", "lp_weth", "imd_supply", "gate_open", "value_eth", "block",
        "counterparty_known", "identity_writes", "floor",
    }
    for model in ALL_MODELS:
        clash = flat_only & {f.name for f in dataclasses.fields(model)}
        assert not clash, f"{model.__name__} carries flat-dict key(s) {clash}"


def test_no_model_field_defaults_to_zero() -> None:
    """The house rule, stated structurally: a default of 0 is a sentinel that
    would outlive the outage that produced it."""
    for model in ALL_MODELS:
        for field in dataclasses.fields(model):
            if field.default is not dataclasses.MISSING:
                assert field.default in (None, False, ()), (
                    f"{model.__name__}.{field.name} defaults to {field.default!r}"
                )


def test_wei_fields_are_named_wei() -> None:
    """Unit discipline, mirrored from fwa_models: models are wei-native and the
    flat dict is the presentation boundary."""
    for name in ("imd_supply_wei", "lp_imd_wei", "lp_weth_wei",
                 "lp_tokens_owed0_wei", "lp_tokens_owed1_wei"):
        assert name in {f.name for f in dataclasses.fields(ChainState)}
    assert "value_wei" in {f.name for f in dataclasses.fields(ChannelTx)}
    assert "value_wei" in {f.name for f in dataclasses.fields(DevTx)}


def test_nft_floor_is_pinned_to_none() -> None:
    """v1 has no keyless floor source.  The field exists so the widget can
    render the explicit unavailable state; it must not become a number."""
    stats = NftStats(
        holders=667,
        total_supply=2000,
        transfers_total=7411,
        dev_holdings=3,
    )
    assert stats.floor_eth is None
    assert stats.transfers_24h is None   # the rate, not the lifetime counter
    assert stats.written is None         # WP1.8 fills it; the default is the
                                         # degraded state, not "no producer"


def test_nft_lifetime_and_daily_transfers_are_separate_fields() -> None:
    """Blockscout serves a lifetime counter; the PRD asks for a daily rate.

    Holding both on one field is how 7,411 gets rendered as "7,411/day".  The
    derivation is WP1.8's ``_count_transfers_24h()``; when it cannot reach the
    24 h edge inside its page budget it answers ``None`` and the widget renders
    the unavailable state rather than a lower bound.
    """
    names = {f.name for f in dataclasses.fields(NftStats)}
    assert {"transfers_total", "transfers_24h"} <= names


def test_log_window_groups_default_to_empty_not_missing() -> None:
    """``()`` is the only empty a group can carry.

    It means the window was read and nothing happened in it, *or* that this one
    filter failed — the tuple cannot hold ``None``, so the failure travels in
    the manager's ``degraded`` list instead.  A window where *every* group
    failed is a ``None`` returned instead of a ``LogWindow``: the client never
    hands back a half-real window.
    """
    window = LogWindow(from_block=1, to_block=2, bridge_mints=({"ts": 1.0},))
    assert window.bridge_mints == ({"ts": 1.0},)
    assert window.identity_updates == ()
    assert window.v4_initializes == ()
    assert window.seaport_sales == ()


def test_channel_tx_kinds_are_the_four_frozen_strings() -> None:
    """CHANNEL_KINDS is the vocabulary ``classify_channel_tx`` returns — it is
    deliberately *not* a ChannelTx field: the client returns raw rows and the
    pure layer classifies them (PRD §6 rule 4)."""
    from maxpane_dashboard.data.surf_models import CHANNEL_KINDS

    assert CHANNEL_KINDS == ("self", "reply", "action", "fund")
    assert "kind" not in {f.name for f in dataclasses.fields(ChannelTx)}
    assert "text" not in {f.name for f in dataclasses.fields(ChannelTx)}


def test_module_has_no_io_imports() -> None:
    import inspect

    from maxpane_dashboard.data import surf_models

    source = inspect.getsource(surf_models)
    for banned in ("import httpx", "import asyncio", "from textual", "import requests"):
        assert banned not in source
```

- [ ] Run and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_models.py -v`
      → collection error `ModuleNotFoundError: No module named
      'maxpane_dashboard.data.surf_models'`.

- [ ] Write `maxpane_dashboard/data/surf_models.py`:

```python
"""Frozen interface for the surf ("mission control") dashboard.

Boundaries only: this module imports nothing but the standard library.  No
client, no cache, no analytics, no Textual.  Every other surf module codes
against what is declared here.

Unit discipline (copied deliberately from ``fwa_models``): **models are
wei-native, the flat dict is the presentation boundary.**  ``*_wei`` fields are
``int``; the manager divides exactly once when it builds the flat dict, which is
why the dict carries ``imd_supply`` / ``value_eth`` while the models carry
``imd_supply_wei`` / ``value_wei``.

Naming discipline: **model fields mirror the chain, flat-dict keys mirror the
PRD.**  The getter is ``identityAllowed()`` so the field is ``identity_allowed``;
the hero key is ``gate_open``.  The full mapping is table-ised in
``surf_manager``; nothing here is renamed to match a widget.

Raw discipline: the client returns what it read.  ``ChannelTx`` has no ``kind``
and no ``text`` — the manager derives both through ``analytics/surf_signals``,
so the classifier and the UTF-8 decoder each have exactly one caller and one
test suite against hostile input (PRD §6 rule 4).  ``LogWindow`` carries raw log
rows for the same reason; the decoders live in ``surf_manager``.

``DevTx`` is the one deliberate exception, and the reason is right below it:
``counterparty``, ``counterparty_label`` and ``kind`` are declared **without
defaults**, so only the constructor site can fill them — and that site is the
client, which is the last place a row's provenance (whose page it came from)
still exists, and therefore the only place the address-poisoning sender filter
can run.  The manager derives ``counterparty_known`` from ``counterparty_label``
and nothing else.

Outage discipline: every field a read can fail to produce is ``… | None`` and
defaults to ``None``.  Nothing here defaults to ``0`` — a zero written into a
persisted supply series outlives the outage that produced it and fires a false
BURN signal (docs/surf_PRD.md §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The four announcement-channel classifications (analytics/surf_signals.py
#: ``classify_channel_tx`` returns exactly one of these).
CHANNEL_KINDS: tuple[str, ...] = ("self", "reply", "action", "fund")

#: Signal states rendered by ``SurfSignals``.  ``None`` means "not evaluated".
SIGNAL_STATES: tuple[str, ...] = ("ok", "watch", "fired")


@dataclass(frozen=True, slots=True)
class NonceSet:
    """The three transaction counts read every refresh, in one batch.

    A leg that failed is ``None``; a leg that succeeded and is genuinely 0 is
    ``0``.  Signal code must never conflate the two.
    """

    announce: int | None
    dev: int | None
    ops: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class ChainState:
    """One batched round of ``eth_call`` getters — the PRD fast tier.

    Seven ``aggregate3`` sub-calls: ``positions()``, ``ownerOf()``,
    ``identityAllowed()``, ``totalSupply()``, ``slot0()``, ``name()``,
    ``symbol()``.  Every sub-call is ``allowFailure=True``, so one reverted view
    degrades one field to ``None`` rather than the round.

    ``lp_owner`` is the raw address from ``NFPM.ownerOf(LP_POSITION_ID)``; the
    manager compares it to ``OPS_WALLET`` to produce ``lp_owner_ok`` — the model
    does not editorialise, and "unread" must stay distinguishable from "someone
    else holds it".

    ``lp_imd_wei``/``lp_weth_wei`` are **derived, not returned**: the standard
    Uniswap v3 closed form over ``liquidity``, ``sqrtPriceX96`` and the position's
    ``tickLower``/``tickUpper``.  WP1.4 computes them because it is the only place
    the tick bounds exist — see the note above.  A ``0`` in either is a *real*
    zero (the price left that side of the range); ``None`` is a failed read.

    There is no ``identities_written``: the verified IdentityMD source has
    ``totalSupply`` and ``identityAllowed`` and no written-hash counter, so that
    number is ``NftStats.written``'s problem, not a getter's.
    """

    lp_liquidity: int | None
    lp_token0: str | None
    lp_token1: str | None
    lp_fee: int | None
    lp_tokens_owed0_wei: int | None
    lp_tokens_owed1_wei: int | None
    lp_imd_wei: int | None
    lp_weth_wei: int | None
    lp_owner: str | None
    identity_allowed: bool | None
    imd_supply_wei: int | None
    sqrt_price_x96: int | None
    pool_tick: int | None
    imd_name: str | None
    imd_symbol: str | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class ChannelTx:
    """One announcement-channel transaction, **raw**.

    No ``kind`` and no ``text``: the channel is permissionless and
    attacker-writable, so classification and UTF-8 decoding are pure functions in
    ``analytics/surf_signals`` where they are table-tested against hostile input.
    ``input_hex`` is what makes that possible and is never dropped — the manager
    calls ``classify_channel_tx(from_addr, to_addr, value_wei, input_hex)`` and
    ``decode_utf8_calldata(input_hex)``.

    ``method`` is Blockscout's decoded method name when it has one, else
    ``None`` — a hint for the feed, never the classification.
    """

    tx_hash: str
    ts: float
    nonce: int | None
    from_addr: str
    to_addr: str | None
    value_wei: int
    input_hex: str
    method: str | None = None


@dataclass(frozen=True, slots=True)
class DevTx:
    """One dev-wallet transaction for the activity feed, filtered and labelled.

    ``counterparty_label`` is ``None`` for anything outside
    ``surf_addresses.KNOWN_LABELS`` — an allowlist, never a heuristic, so a
    lookalike cannot inherit its target's label no matter how many leading hex
    characters it matches.  The widget renders those dimmed and truncated.

    Rows are only ever built where the *sender* is a dev wallet, so a poisoning
    dust transfer can never manufacture one (PRD §6.5).  That is a
    **construction invariant**, not a downstream filter: ``wallet_label`` records
    whose page the row came from, and that provenance only exists inside the
    client, which is why WP1.6 owns the check.

    The manager still derives ``counterparty_known`` (= ``counterparty_label is
    not None``) and scales ``value_wei`` to ETH for display.
    """

    tx_hash: str
    ts: float
    wallet_label: str
    from_addr: str
    to_addr: str | None
    counterparty: str
    counterparty_label: str | None
    value_wei: int
    method: str | None
    kind: str
    created_contract: str | None = None


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Cross-checked market view.  DexScreener displays, GeckoTerminal checks.

    ``indexer_name``/``indexer_symbol`` are **DexScreener's**, which are current.
    GeckoTerminal still serves "Vibe Coins" (two renames behind) — its numbers
    are welcome and its strings are barred at the client, which is why no
    ``*_stale`` flag needs to exist here.  The onchain name/symbol the dashboard
    actually renders are ``ChainState.imd_name``/``imd_symbol``.

    ``sources_agree`` is ``None`` unless *both* sources answered: two prices that
    were never compared are not two prices that disagreed.
    """

    imd_price_usd: float | None
    imd_price_usd_gecko: float | None
    imd_change_24h_pct: float | None
    imd_vol_24h_usd: float | None
    pool_liquidity_usd: float | None
    pool_imd: float | None
    pool_weth: float | None
    fp_price_usd: float | None
    fdv_usd: float | None
    eth_usd: float | None
    indexer_name: str | None
    indexer_symbol: str | None
    sources_agree: bool | None = None


@dataclass(frozen=True, slots=True)
class LogWindow:
    """A recent-window ``eth_getLogs`` sweep across the logs RPC pool.

    Per group, ``()`` means the group was read and held nothing **or** that this
    one filter failed: these fields are frozen tuples and cannot hold ``None``,
    so a single failed group degrades to ``()`` and the failure is reported
    through the manager's ``degraded`` list — never through the tuple.  Do not
    write ``if window.bridge_mints is None``; no input can reach that branch.
    Only a sweep where *every* group failed returns ``None`` instead of a
    ``LogWindow``, because collapsing a dead logs pool into a quiet chain would
    hide exactly the state the launch signals are watching for.

    Groups carry the **raw** log rows the endpoint returned — ``topics`` (full
    list, order intact), ``data`` (untruncated), ``blockNumber``,
    ``blockTimestamp`` when the endpoint sends it, and ``transactionHash`` — all
    preserved, never normalised, pruned or re-keyed.  The decoders that turn
    those into ``ts`` / ``hooks`` / ``amount`` / ``token_id`` live in
    ``surf_manager`` (WP4); WP1.9b is the hand-over guard that fails if the
    client drops any of the fields those decoders index.
    """

    from_block: int | None
    to_block: int | None
    bridge_mints: tuple[dict, ...] = ()
    identity_updates: tuple[dict, ...] = ()
    v4_initializes: tuple[dict, ...] = ()
    seaport_sales: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class NftStats:
    """IDMD collection stats from Blockscout counters + one ``balanceOf``.

    ``transfers_total`` is the lifetime counter Blockscout serves (7,411 on
    2026-08-08).  ``transfers_24h`` is the *rate* the PRD hero asks for; it is a
    separate field so the lifetime number can never be rendered as a daily one,
    and WP1.8's ``_count_transfers_24h()`` derives it by walking
    ``/tokens/{IDMD}/transfers`` newest-first until a row falls outside the
    window.  ``written`` (identities with a hash set — 1 of 2000) is WP1.8's
    ``_count_identities_written()``: distinct ``topics[1]`` over
    ``/addresses/{IDENTITY_REGISTRY}/logs``, lifetime, keyless.  Both answer
    ``None`` when their page budget runs out before the answer is complete — a
    lower bound printed as a rate or a total is a wrong number.

    ``floor_eth`` is the one deferred field, and it is pinned to ``None`` for
    good: OpenSea is keyed and Cloudflare-gated and no other keyless source
    exists, so the widget renders ``n/a — no keyless source``.  Never populate
    any of the three from an indexer guess — and specifically, never populate
    ``written`` from ``len(LogWindow.identity_updates)``, which counts an
    eight-hour window and not the collection (see open issue 9).

    Realized sales are **not** here: they are decoded from
    ``LogWindow.seaport_sales`` on the medium tier.
    """

    holders: int | None
    total_supply: int | None
    transfers_total: int | None
    dev_holdings: int | None
    transfers_24h: float | None = None
    written: int | None = None
    floor_eth: None = None
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_models.py -v`
- [ ] Commit:
      `git add maxpane_dashboard/data/surf_models.py tests/data/test_surf_models.py && git commit -m "feat(surf): freeze the surf data models as None-safe frozen dataclasses"`

---

### Task WP0.5: SURF_KEYS and SURF_ROW_KEYS

**Files:**
- Modify: `maxpane_dashboard/data/surf_models.py`
- Test: `tests/data/test_surf_models.py`

**Interfaces:**
- Produces: `SURF_KEYS: tuple[str, ...]` — the exact 48 keys of
  `SurfManager.fetch_and_compute()`; additive `SURF_ROW_KEYS: dict[str, tuple[str, ...]]`
  for the three list-of-dict payloads.
- Consumed by (named by module — the WP numbering differs between plan documents):
  `data/surf_manager.py` builds exactly these keys; `data/surf_cache.py` persists
  `supply_series` / `price_series` through `coerce_points`; `screens/surf.py` dispatches the
  flat dict; the widget package's contract test imports `SURF_KEYS` (the widget *modules*
  import nothing from `data/`).
- **Also owned here: the `SIGNAL_OUTPUT_KEYS ⊆ SURF_KEYS` containment assertion.**
  `analytics/surf_signals.py` freezes the 18 `sig_*` names it emits; this module freezes the
  48 the dashboard renders. Nothing else in the repo compares the two surfaces —
  `analytics/surf_signals.py`'s own `test_signal_output_keys_match_the_prd_naming` checks the
  *shape* of its names, and the widget package cannot host the check because its
  import-hygiene test forbids the widget layer from importing `analytics/` at all. So a
  rename on either side would ship as a widget silently rendering `None` for a detector
  nobody notices is missing. The test below closes that, guarded by `importorskip` so WP0
  stays green before the signals module exists. (This settles the "one file, not both"
  choice the signals plan asks the WP0 editor to record: it lives **here**, not in
  `tests/data/test_surf_manager.py`.)

**Steps:**

- [ ] Append the failing test to `tests/data/test_surf_models.py`:

```python
# ---------------------------------------------------------------------------
# the flat-dict contract (docs/surf_PRD.md §5)
# ---------------------------------------------------------------------------

EXPECTED_KEYS = {
    # meta
    "as_of",
    "degraded",
    "eth_usd",
    # feed
    "feed_nonce",
    "feed_last_post_age_s",
    "feed_items",
    # signals — six detectors x (state, detail, age)
    "sig_post_state",
    "sig_post_detail",
    "sig_post_age_s",
    "sig_lp_state",
    "sig_lp_detail",
    "sig_lp_age_s",
    "sig_gate_state",
    "sig_gate_detail",
    "sig_gate_age_s",
    "sig_deploy_state",
    "sig_deploy_detail",
    "sig_deploy_age_s",
    "sig_bridge_state",
    "sig_bridge_detail",
    "sig_bridge_age_s",
    "sig_burn_state",
    "sig_burn_detail",
    "sig_burn_age_s",
    # hero
    "hook_status",
    "lp_liquidity",
    "lp_imd",
    "lp_weth",
    "lp_owner_ok",
    "gate_open",
    "identities_written",
    "imd_supply",
    "imd_burned_cum",
    # market
    "imd_price_usd",
    "imd_change_24h_pct",
    "imd_vol_24h_usd",
    "pool_liquidity_usd",
    "fp_price_usd",
    "parity_pct",
    "supply_series",
    "price_series",
    # nft
    "nft_holders",
    "nft_transfers_24h",
    "nft_dev_holdings",
    "nft_written",
    "nft_last_sales",
    "nft_floor",
    # activity
    "dev_activity",
}


def test_surf_keys_is_exactly_the_prd_contract() -> None:
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    assert set(SURF_KEYS) == EXPECTED_KEYS
    assert len(SURF_KEYS) == len(set(SURF_KEYS)) == 48


def test_every_signal_has_all_three_facets() -> None:
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    for base in ("post", "lp", "gate", "deploy", "bridge", "burn"):
        for suffix in ("state", "detail", "age_s"):
            assert f"sig_{base}_{suffix}" in SURF_KEYS


def test_signal_output_keys_are_a_subset_of_surf_keys() -> None:
    """SIGNAL_OUTPUT_KEYS (the signals module) must all exist in SURF_KEYS.

    Skips until ``analytics/surf_signals.py`` lands; from then on this is the
    only test in the repo that compares the two frozen key surfaces, so a
    rename on either side fails here — instead of surfacing as a widget that
    quietly renders ``None`` for a signal nobody notices is missing.
    """
    surf_signals = pytest.importorskip("maxpane_dashboard.analytics.surf_signals")
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    missing = sorted(set(surf_signals.SIGNAL_OUTPUT_KEYS) - set(SURF_KEYS))
    assert not missing, f"signal keys absent from SURF_KEYS: {missing}"


def test_row_key_sets_match_the_prd() -> None:
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS

    assert SURF_ROW_KEYS["feed_items"] == (
        "ts",
        "kind",
        "from_addr",
        "from_label",
        "text",
        "tx_hash",
    )
    assert SURF_ROW_KEYS["nft_last_sales"] == ("ts", "token_id", "eth")
    assert SURF_ROW_KEYS["dev_activity"] == (
        "ts",
        "wallet_label",
        "kind",
        "counterparty",
        "counterparty_known",
        "value_eth",
        "tx_hash",
    )
    assert set(SURF_ROW_KEYS) <= set(
        __import__(
            "maxpane_dashboard.data.surf_models", fromlist=["SURF_KEYS"]
        ).SURF_KEYS
    )


def test_no_wei_key_leaks_into_the_flat_dict() -> None:
    """The dict is the presentation boundary: ETH/float only."""
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    assert not [k for k in SURF_KEYS if k.endswith("_wei")]
```

- [ ] Run and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_models.py -k keys -v`
      → `ImportError: cannot import name 'SURF_KEYS' from
      'maxpane_dashboard.data.surf_models'`.
      `test_signal_output_keys_are_a_subset_of_surf_keys` reports **SKIPPED**, not failed —
      `analytics/surf_signals.py` does not exist yet and `importorskip` is what keeps WP0
      green ahead of it. A skip here is the intended state, not an outstanding failure.

- [ ] Append the implementation:

```python
#: Every key ``SurfManager.fetch_and_compute()`` returns — the parallel-agent
#: interface, frozen by docs/surf_PRD.md §5.  Every numeric is ``float|int|None``
#: and ``None`` renders as the widget's unavailable state, never as 0.
SURF_KEYS: tuple[str, ...] = (
    # ---- meta ---------------------------------------------------------------
    "as_of",                 # float — epoch of the sweep that produced this dict
    "degraded",              # list[str] — source-group names currently failing
    "eth_usd",               # float | None — CoinGecko via data/price.py
    # ---- feed ---------------------------------------------------------------
    "feed_nonce",            # int | None — eth_getTransactionCount(ANNOUNCE)
    "feed_last_post_age_s",  # float | None
    "feed_items",            # list[dict] — SURF_ROW_KEYS["feed_items"]
    # ---- signals: six detectors, state/detail/age each ----------------------
    "sig_post_state",        # "ok" | "watch" | "fired" | None
    "sig_post_detail",       # str
    "sig_post_age_s",        # float | None
    "sig_lp_state",
    "sig_lp_detail",
    "sig_lp_age_s",
    "sig_gate_state",
    "sig_gate_detail",
    "sig_gate_age_s",
    "sig_deploy_state",
    "sig_deploy_detail",
    "sig_deploy_age_s",
    "sig_bridge_state",
    "sig_bridge_detail",
    "sig_bridge_age_s",
    "sig_burn_state",
    "sig_burn_detail",
    "sig_burn_age_s",
    # ---- hero ---------------------------------------------------------------
    "hook_status",           # str — "NOT LIVE" until an Initialize with hooks!=0
    "lp_liquidity",          # float | None — raw v3 L, rendered abbreviated
    "lp_imd",                # float | None — IMD side, whole tokens
    "lp_weth",               # float | None — WETH side, whole tokens
    "lp_owner_ok",           # bool | None — ownerOf(1167726) == OPS_WALLET
    "gate_open",             # bool | None — IdentityRegistry.identityAllowed()
    "identities_written",    # int | None — 1 of 2000 on 2026-08-08
    "imd_supply",            # float | None — whole IMD, never 0 on failure
    "imd_burned_cum",        # float | None — cumulative, from the burn ledger
    # ---- market -------------------------------------------------------------
    "imd_price_usd",
    "imd_change_24h_pct",
    "imd_vol_24h_usd",
    "pool_liquidity_usd",
    "fp_price_usd",
    "parity_pct",            # float | None — (imd/fp - 1) * 100, computed live
    "supply_series",         # list[[ts, supply]] — burns step it down
    "price_series",          # list[[ts, price_usd]]
    # ---- nft ----------------------------------------------------------------
    "nft_holders",
    "nft_transfers_24h",
    "nft_dev_holdings",
    "nft_written",
    "nft_last_sales",        # list[dict] — SURF_ROW_KEYS["nft_last_sales"]
    "nft_floor",             # always None in v1 — explicit unavailable state
    # ---- activity -----------------------------------------------------------
    "dev_activity",          # list[dict] — SURF_ROW_KEYS["dev_activity"]
)

#: Row shapes for the three list-of-dict payloads.  Widgets index these keys
#: directly, so adding one is a contract change, not an implementation detail.
SURF_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "feed_items": ("ts", "kind", "from_addr", "from_label", "text", "tx_hash"),
    "nft_last_sales": ("ts", "token_id", "eth"),
    "dev_activity": (
        "ts",
        "wallet_label",
        "kind",
        "counterparty",
        "counterparty_known",
        "value_eth",
        "tx_hash",
    ),
}
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_models.py -v`
      → all pass except `test_signal_output_keys_are_a_subset_of_surf_keys`, which is
      `1 skipped` until the signals module lands. Confirm it is a skip and not an error:
      `.venv/bin/python -m pytest tests/data/test_surf_models.py -k subset -rs` prints
      `SKIPPED … could not import 'maxpane_dashboard.analytics.surf_signals'`.
- [ ] Commit:
      `git add maxpane_dashboard/data/surf_models.py tests/data/test_surf_models.py && git commit -m "feat(surf): freeze SURF_KEYS (48) and the three row-key shapes"`
- [ ] **Deferred — prove the containment test bites, the day `analytics/surf_signals.py`
      lands.** It cannot be proven earlier: with the module absent the test skips, and a skip
      proves nothing. Record it on the WP0 sign-off checklist (WP0.8) as an open follow-up,
      and run it as the first thing after the signals module is merged:
      1. In `maxpane_dashboard/analytics/surf_signals.py`, rename one entry of
         `SIGNAL_OUTPUT_KEYS` — `sig_burn_state` → `sig_burns_state`.
      2. `.venv/bin/python -m pytest tests/data/test_surf_models.py -k subset -v`
         → FAILS with `signal keys absent from SURF_KEYS: ['sig_burns_state']`.
      3. Restore the name; re-run → green (not skipped).
      If it still skips at step 2, the import path in `importorskip` is wrong and the guard
      has been dead the whole time — that is the one failure mode this test has.

---

### Task WP0.6: Commit the captures and the shared capture reader

**Files:**
- Commit (currently untracked): `tests/fixtures/surf/captures/` — 31 files, 1.6 MB
  (29 `*.json` + `README.md` + `agent_card_ipfs.txt`)
- Create: `tests/surf_fixtures.py`
- Test: `tests/data/test_surf_captures.py`

**Interfaces:**
- Produces: `tests.surf_fixtures.SURF_FIXTURES: Path`, `CAPTURES: Path`, `capture(name) -> Any`.
  That is the whole module. There is deliberately no `load_fixture` / `payload` /
  `announce_rows` envelope helper: WP0 commits no fixture file for one to open, and the WPs
  that do commit slices already read them their own way. The module is the *shared home* for
  such a helper when a second reader appears — see *Fixture ownership*.
- Consumed by: WP0.7, and any later WP that wants a raw capture rather than its own slice.
- Consumes: nothing. `json` and `pathlib`; reads files, opens no socket.

**Steps:**

- [ ] Confirm the captures are untracked, then commit them **first** — they are the provenance
      for every slice any WP will cut, and WP0.7 reads them directly:
      `git status --porcelain tests/fixtures/surf` → `?? tests/fixtures/surf/`.
      `git add tests/fixtures/surf/captures && git commit -m "test(surf): commit the 2026-08-08 keyless capture set as fixture provenance"`
      (`pyproject.toml` ships `include = ["maxpane_dashboard/"]` in the sdist and
      `packages = ["maxpane_dashboard"]` in the wheel, so these 1.6 MB never reach PyPI.)

- [ ] Write the failing test `tests/data/test_surf_captures.py` — the module header plus the
      WP0.6 guards; WP0.7 appends the fact pins to the same file:

```python
"""The surf capture set — the one source material, and the facts it pins.

Every surf work package derives its test data from ``tests/fixtures/surf/captures/``:
real keyless payloads (Blockscout REST v2, GeckoTerminal, DexScreener) fetched on
2026-08-08.  Two things are asserted here and nowhere else:

1.  The captures are committed, readable, keyless and read-only.
2.  Every number a later work package hardcodes is recomputed *from the capture* —
    the burn total, the poisoning rows, the holder disagreement, the parity spread,
    the nonce ladder.  A re-capture that moves one of them fails here, once.

WP0 commits no fixture file.  Each consuming work package owns a subdirectory of
``tests/fixtures/surf/`` (``client/``, ``signals/``, …); the root-directory guard
below is what keeps those from colliding with each other's globs.

No network: this module reads files only.
"""

from __future__ import annotations

import json

from tests.surf_fixtures import CAPTURES, SURF_FIXTURES


def test_captures_are_committed_and_readable() -> None:
    names = {p.name for p in CAPTURES.iterdir()}
    assert "README.md" in names, "the capture set must document its own provenance"
    json_files = sorted(CAPTURES.glob("*.json"))
    assert len(json_files) == 29
    for path in json_files:
        assert json.loads(path.read_text(encoding="utf-8")) is not None, path.name


def test_the_fixtures_root_holds_directories_only() -> None:
    """Ownership rule: WP0 owns ``captures/`` and every other work package owns its
    own subdirectory.  A loose ``*.json`` at the root is a file with no owner, and
    it is how one WP's slice lands in another WP's glob and turns its suite red in
    a file it may not edit."""
    loose = sorted(p.name for p in SURF_FIXTURES.iterdir() if p.is_file())
    assert loose == [], f"put these in a per-work-package subdirectory: {loose}"


def test_no_capture_carries_an_api_key() -> None:
    """Hard constraint: every source is keyless.  A captured URL with a key in it
    would mean the payload cannot be re-fetched by someone who installed the app."""
    for path in sorted(CAPTURES.iterdir()):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"
```

- [ ] Run and state the expected failure:
      `.venv/bin/python -m pytest tests/data/test_surf_captures.py -v`
      → collection error `ModuleNotFoundError: No module named 'tests.surf_fixtures'`.

- [ ] Write the reader `tests/surf_fixtures.py`:

```python
"""Shared access to the surf capture set.

``tests/fixtures/surf/captures/`` holds the real keyless payloads captured on
2026-08-08; every surf work package slices its own test data out of them.  This
module is the one reader of the captures, so four test suites (``tests/data``,
``tests/analytics``, ``tests/widgets``, ``tests/screens``) do not hand-roll four.

It exposes **only** the raw-capture reader.  There is no envelope helper here
because WP0 commits no fixture file for one to open, and a helper with no caller
is exactly the defect that deleted nine tasks from this plan.  A work package that
commits slices under ``tests/fixtures/surf/<its-dir>/`` and wants a shared reader
adds it *here*, next to ``capture()`` — never by copying this file.

The captures are **read-only**.  Nothing regenerates them; a test that rewrote one
would turn the provenance into whatever made the suite green that afternoon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: ``tests/fixtures/surf`` — the root each work package takes a subdirectory of.
SURF_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surf"

#: The committed 2026-08-08 payloads.
CAPTURES = SURF_FIXTURES / "captures"


def capture(name: str) -> Any:
    """One raw capture body, exactly as the keyless API served it."""
    with open(CAPTURES / name, encoding="utf-8") as fh:
        return json.load(fh)
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/data/test_surf_captures.py -v`
      (3 passed).
- [ ] Prove the ownership guard bites: `touch tests/fixtures/surf/stray.json`, run
      `.venv/bin/python -m pytest tests/data/test_surf_captures.py -k root -v`
      → `test_the_fixtures_root_holds_directories_only` FAILS with
      `put these in a per-work-package subdirectory: ['stray.json']`. Delete the file.
- [ ] Commit:
      `git add tests/surf_fixtures.py tests/data/test_surf_captures.py && git commit -m "test(surf): add the shared capture reader and the fixture-root ownership guard"`

---

### Task WP0.7: Pin the capture facts every other work package quotes

**Files:**
- Modify: `tests/data/test_surf_captures.py`
- Test: itself

**Interfaces:**
- Produces: one assertion per number the other plan documents hardcode. Nothing importable —
  this task's output is a *guard*, and its value is that a re-capture, a corrected figure or a
  copy-paste transposition fails in one named place instead of drifting silently through six
  work packages.
- Consumes: `tests.surf_fixtures.capture`, `surf_addresses.KNOWN_LABELS` (one test).

**Why this is the replacement for nine fixture tasks.** The deleted tasks asserted these same
facts against WP0's private copies of the captures. Asserting them against the captures is
strictly stronger: it is the same evidence with one fewer indirection, it covers the data the
other WPs actually slice, and it cannot go stale relative to a copy nobody reads.

**Steps:**

- [ ] Append the failing tests (they fail at collection until WP0.1's `KNOWN_LABELS` exists;
      everything else is data that is already committed, so run them *after* WP0.3):

```python
# ---------------------------------------------------------------------------
# the announcement channel — calldata IS the message
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

from tests.surf_fixtures import capture  # noqa: E402

#: The three Blockscout address transaction pages.
TX_CAPTURES = (
    "announce_eth_txs.json",
    "wallet_eth_txs_page1.json",
    "ops_eth_txs.json",
)

ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
DEV = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"
OPS = "0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095"
NFPM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
BURN_EXECUTOR = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
IMD = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
ZERO = "0x0000000000000000000000000000000000000000"


def body(row: dict) -> str:
    """The message a channel transaction carries, or ``UnicodeDecodeError``."""
    return bytes.fromhex(row["raw_input"][2:]).decode("utf-8")


def one(rows: list[dict], prefix: str, key: str = "hash") -> dict:
    """Exactly one row whose ``key`` starts with ``prefix``.

    Not a dict index: a dict would silently keep the last match, so a hash that
    stopped being unique after a re-capture would pick a different row than the
    comment above it claims.
    """
    matches = [r for r in rows if r[key].startswith(prefix)]
    assert len(matches) == 1, f"{prefix} matched {len(matches)} rows"
    return matches[0]


def rows_of(name: str) -> list[dict]:
    """Blockscout serves some captures bare and some wrapped in ``items``."""
    payload = capture(name)
    return payload["items"] if isinstance(payload, dict) else payload


def test_the_nonce_ladder() -> None:
    """The live counters every fast-tier read is compared against are the highest
    committed nonce + 1: announce 13 -> 14, dev 2349 -> 2350, ops 37 -> 38.  Any
    WP that fakes an ``eth_getTransactionCount`` response derives it from here."""
    channel = capture("announce_eth_txs.json")
    assert len(channel) == 21
    assert max(r["nonce"] for r in channel if r["from"]["hash"] == ANNOUNCE) == 13
    dev_rows = capture("wallet_eth_txs_page1.json")
    assert len(dev_rows) == 30
    assert max(r["nonce"] for r in dev_rows if r["from"]["hash"] == DEV) == 2349
    ops_rows = capture("ops_eth_txs.json")
    assert len(ops_rows) == 50
    assert max(r["nonce"] for r in ops_rows if r["from"]["hash"] == OPS) == 37


def test_the_register_call_is_the_only_non_utf8_body() -> None:
    """Signal 4 (NEW DEPLOY) keys on this shape: an outbound *contract call* from
    the channel whose calldata is ABI, not text.  Every other body decodes, which
    is what makes ``decode_utf8_calldata``'s failure path meaningful."""
    channel = capture("announce_eth_txs.json")
    undecodable = []
    for row in channel:
        try:
            body(row)
        except UnicodeDecodeError:
            undecodable.append(row["hash"])
    assert len(undecodable) == 1
    reg = one(channel, "0xa4ce159e5100")
    assert reg["hash"] == undecodable[0]
    assert reg["to"]["hash"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
    assert reg["raw_input"].startswith("0xf2c298be")  # register(string)


def test_the_funding_tx_and_the_paid_reply() -> None:
    """The permissionless-channel hazard, as data: the dev's own funding tx and a
    stranger's 1e13-wei begging tx sit in the same list as the posts."""
    channel = capture("announce_eth_txs.json")
    funding = one(channel, "0x632f5dc3e5aa")
    assert funding["from"]["hash"] == DEV and funding["to"]["hash"] == ANNOUNCE
    assert funding["raw_input"] == "0x" and funding["value"] == "54000000000000000"
    reply = one(channel, "0xd52c857d4df0")
    assert reply["from"]["hash"] != ANNOUNCE
    assert reply["value"] == "10000000000000"


def test_message_bodies_carry_the_typography_that_breaks_layout() -> None:
    channel = capture("announce_eth_txs.json")
    hook = body(one(channel, "0x0b72b4640117"))
    assert len(hook) == 219
    assert "\n" in hook and "—" in hook and "’" in hook
    spec = body(one(channel, "0xc189351772cb"))
    assert len(spec) == 952  # the long body the feed must truncate at narrow tiers


def test_no_captured_message_contains_a_markup_bracket() -> None:
    """Why every markup-hostile test vector in this plan set is synthetic and built
    inline by the WP that needs it: the channel is permissionless, but nobody has
    used it to post Textual markup *yet*.  If this ever fails, a real vector
    exists — slice it into that WP's directory and say so in its provenance."""
    for row in capture("announce_eth_txs.json"):
        try:
            text = body(row)
        except UnicodeDecodeError:
            continue
        assert "[" not in text, row["hash"]


# ---------------------------------------------------------------------------
# dev wallet — the activity feed's raw material
# ---------------------------------------------------------------------------


def test_dev_wallet_page_landmarks() -> None:
    rows = {r["hash"][:14]: r for r in capture("wallet_eth_txs_page1.json")}
    seaport = rows["0x5b4d1b4416bb"]        # the dev buying his own collection
    assert seaport["to"]["name"] == "Seaport"
    assert seaport["value"] == "363898900000000000"
    assert rows["0xcfb8f6e2c733"]["method"] == "bridgeToBaseBurnReceiver"
    claim = rows["0x139d860ed62f"]          # FWA income, NOT IMD economics
    assert claim["to"]["name"] == "Splitter" and claim["method"] == "claim"
    assert rows["0xdbfc446490ec"]["to"]["hash"] == (
        "0x58239Ad01D72811F179bAE08983F95Ac30274e55"   # swept ~1 minute later
    )
    stamps = [r["timestamp"] for r in rows.values()]
    assert min(stamps).startswith("2026-07-27") and max(stamps).startswith("2026-08-08")


def test_no_captured_transaction_creates_a_contract() -> None:
    """Documents why every NEW DEPLOY vector is synthetic and inline: none of the
    101 captured transactions carries ``created_contract``."""
    total = 0
    for name in TX_CAPTURES:
        rows = capture(name)
        total += len(rows)
        assert all(r.get("created_contract") is None for r in rows), name
    assert total == 101


def test_the_only_real_deploy_evidence_is_the_token_info_capture() -> None:
    """Whatever a later WP builds its flagged-synthetic deploy row from, these two
    values are the real ones and must be reused rather than invented."""
    info = capture("imd_info.json")
    assert info["creation_transaction_hash"] == (
        "0xb2e2587f18b440f2c492d911566cb979d4ec477dd69824d9ac17bdae2608704b"
    )
    assert info["creator_address_hash"] == DEV


# ---------------------------------------------------------------------------
# ops wallet — the LP choreography and the live poisoning rows
# ---------------------------------------------------------------------------


def test_the_lp_add_choreography_is_present_and_ordered() -> None:
    """PRD §11.2: bridge-in -> approve -> add, inside eight minutes on 2026-08-07."""
    rows = {r["hash"][:14]: r for r in capture("ops_eth_txs.json")}
    inbound = rows["0xd37239cfdbc1"]   # 33.693 ETH from a CEX hot wallet, 04:15:47
    approve = rows["0x0031c5c8cee0"]   # approve(IMD) to the NFPM,          04:22:23
    add = rows["0x90a0f8e2b039"]       # multicall into position 1167726,   04:23:23
    assert inbound["timestamp"] < approve["timestamp"] < add["timestamp"]
    assert inbound["to"]["hash"] == OPS
    assert inbound["value"] == "33693247247435751553"
    assert approve["method"] == "approve" and approve["to"]["hash"] == IMD
    assert add["to"]["hash"] == NFPM
    assert add["value"] == "33252659725872729307"
    assert add["method"] == "multicall"


def test_the_two_real_fee_sinks_received_real_eth() -> None:
    rows = {r["hash"][:14]: r for r in capture("ops_eth_txs.json")}
    assert rows["0x4628e535ea91"]["to"]["hash"] == (
        "0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6"
    )
    assert rows["0x4628e535ea91"]["value"] == "1428629183776324443"
    assert rows["0xed46d5f37715"]["to"]["hash"] == (
        "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"
    )
    assert rows["0xed46d5f37715"]["value"] == "300000000000000000"


def test_the_four_poisoning_rows_are_one_gwei_inbound_from_lookalikes() -> None:
    """Live address poisoning, as captured.  Every WP that renders a counterparty
    must drop these: inbound dust from senders that are not the dev wallets."""
    from maxpane_dashboard.data.surf_addresses import KNOWN_LABELS

    poison = [r for r in capture("ops_eth_txs.json") if r["value"] == "1000000000"]
    assert len(poison) == 4
    senders = {r["from"]["hash"].lower() for r in poison}
    assert senders == {
        "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",
        "0xf3083828702c1989710ceca517412071c2f60ee6",
        "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",
    }
    assert all(r["to"]["hash"] == OPS for r in poison)
    assert not senders & set(KNOWN_LABELS)


def test_each_spoof_shares_a_prefix_and_suffix_with_its_target() -> None:
    """This is why a truncated address must never be styled as trusted."""
    real_b = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E".lower()
    spoof_b = "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e"
    assert real_b[:6] == spoof_b[:6] and real_b[-4:] == spoof_b[-4:]
    real_a = "0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6".lower()
    for spoof_a in (
        "0xf3083828702c1989710ceca517412071c2f60ee6",
        "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",
    ):
        assert real_a[:6] == spoof_a[:6] and real_a[-4:] == spoof_a[-4:]


# ---------------------------------------------------------------------------
# the IMD transfer ledger — burns, OFT mints, homoglyph tokens
# ---------------------------------------------------------------------------


def test_burn_ledger_sums_to_the_researched_total() -> None:
    """PRD §1's "~58,849 IMD".  ``imd_burned_cum`` is computed from this ledger,
    never typed in: 12039.394018716332754656 (2026-05-16) + 31064 (07-31) +
    15745 (08-05)."""
    burns = [
        r
        for r in rows_of("ops_eth_token_transfers.json")
        if (r.get("to") or {}).get("hash") == BURN_EXECUTOR
    ]
    assert len(burns) == 3
    total = sum(int(r["total"]["value"]) for r in burns)
    assert total == 58_848_394_018_716_332_754_656
    assert total / 10**18 == pytest.approx(58_848.394_018_716_33, rel=1e-12)


def test_bridge_in_mints_come_from_the_zero_address() -> None:
    """Signal 5 (BRIDGE STAGE): OFT mints to a dev wallet, minutes before the add.

    The token filter is load-bearing — a spoof token also mints from ``0x0`` in
    this same capture, so a filter on ``from == 0x0`` alone counts three.
    """
    rows = rows_of("ops_eth_token_transfers.json")
    from_zero = [r for r in rows if (r.get("from") or {}).get("hash") == ZERO]
    assert len(from_zero) == 3
    mints = [r for r in from_zero if r["token"]["address_hash"] == IMD]
    assert len(mints) == 2
    assert {int(r["total"]["value"]) for r in mints} == {
        114_366_899_256_000_000_000_000,
        10_000_000_000_000_000_000_000,
    }
    assert all(r["timestamp"].startswith("2026-08-07T04:") for r in mints)
    # LayerZero OFT sharedDecimals is 6, so every bridged amount is a multiple of
    # 1e12 wei.  A decoder that loses precision breaks this immediately.
    assert all(int(r["total"]["value"]) % 10**12 == 0 for r in mints)


def test_homoglyph_token_symbols_live_in_this_wallets_real_history() -> None:
    """These strings are why ``safe_markup`` runs on token symbols too — and why a
    symbol renderer must survive ``None``."""
    symbols = {r["token"]["symbol"] for r in rows_of("ops_eth_token_transfers.json")}
    # Escapes, not glyphs: an editor that normalises these on save would make the
    # assertion pass against a different string than the one on chain.
    assert "\u0116T\u1e28" in symbols                    # ĖTḨ
    assert "\u200aU\u0405D\u0421\u200a" in symbols     # hair spaces, Cyrillic Ѕ/С
    assert "USD\u0421" in symbols                        # Cyrillic С, unpadded
    assert None in symbols                                # a row with no symbol at all


# ---------------------------------------------------------------------------
# market — DexScreener displays, GeckoTerminal cross-checks
# ---------------------------------------------------------------------------


def test_dexscreener_imd_pair_values() -> None:
    pair = capture("dexscreener_imd.json")["pairs"][0]
    assert pair["baseToken"]["address"] == IMD
    assert pair["pairAddress"] == "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"
    assert pair["labels"] == ["v3"]
    assert pair["priceUsd"] == "0.7074"
    assert pair["priceChange"]["h24"] == 30.89
    assert pair["volume"]["h24"] == 244178
    assert pair["liquidity"] == {"usd": 548701.21, "base": 388421, "quote": 142.7067}


def test_geckoterminal_serves_a_two_renames_stale_name() -> None:
    """PRD §6.3: indexer names are display fallbacks.  DexScreener's are current;
    GeckoTerminal's are two renames behind, so its strings are barred at the
    client and only its numbers are used."""
    attrs = capture("geckoterminal_imd.json")["data"]["attributes"]
    assert attrs["name"] == "Vibe Coins"
    assert attrs["symbol"] == "VIBE"
    assert attrs["price_usd"] == "0.7127337345"
    base = capture("dexscreener_imd.json")["pairs"][0]["baseToken"]
    assert base["name"] == "Identity.md" and base["symbol"] == "IMD"


def test_parity_is_computable_from_the_two_market_captures() -> None:
    imd = float(capture("dexscreener_imd.json")["pairs"][0]["priceUsd"])
    fp = float(capture("dexscreener_fp.json")["pairs"][0]["priceUsd"])
    assert imd == 0.7074 and fp == 0.7274
    assert (imd / fp - 1.0) * 100.0 == pytest.approx(-2.749518834204012, rel=1e-12)


def test_the_two_indexers_disagree_by_under_one_percent() -> None:
    """Cross-check discipline: they are close, so a wild divergence later means one
    source is broken, not that the market moved."""
    dex = float(capture("dexscreener_imd.json")["pairs"][0]["priceUsd"])
    gecko = float(capture("geckoterminal_imd.json")["data"]["attributes"]["price_usd"])
    assert abs(dex - gecko) / dex < 0.01


def test_the_pool_price_is_derivable_from_the_capture() -> None:
    """Any synthetic ``slot0`` a later WP encodes derives its sqrtPriceX96 from
    this number, not from a remembered one (open issue 12).

    token0 = WETH (0xC02a…) < token1 = IMD (0xD34a…) by address order, so the pool
    price is IMD per WETH — the inverse of DexScreener's ``priceNative``.  Getting
    that direction backwards is the classic v3 decoding bug.
    """
    pair = capture("dexscreener_imd.json")["pairs"][0]
    assert pair["priceNative"] == "0.0003686"          # WETH per IMD
    assert 1 / float(pair["priceNative"]) == pytest.approx(
        2712.9679869777538, rel=1e-12
    )


# ---------------------------------------------------------------------------
# Blockscout token + counters
# ---------------------------------------------------------------------------


def test_imd_supply_and_the_two_disagreeing_holder_counts() -> None:
    """Documented, not smoothed over: ``/tokens`` says 1148, ``/counters`` says
    1132.  Both are Blockscout; the hero renders one and says which."""
    token = capture("imd_token.json")
    assert token["address_hash"] == IMD
    assert token["total_supply"] == "2376731868679000000000000"
    assert int(token["total_supply"]) / 10**18 == pytest.approx(2_376_731.868679)
    assert token["symbol"] == "IMD" and token["name"] == "Identity.md"
    assert token["holders_count"] == "1148"
    assert capture("imd_counters.json")["token_holders_count"] == "1132"
    assert capture("imd_counters.json")["transfers_count"] == "30441"
    # sharedDecimals = 6, so mainnet supply is always a multiple of 1e12 wei.
    assert int(token["total_supply"]) % 10**12 == 0


def test_bridged_share_is_computable_and_matches_the_research() -> None:
    imd = int(capture("imd_token.json")["total_supply"])
    fp = int(capture("fp_base_token.json")["total_supply"])
    assert fp == 7_195_584_582_643_610_841_108_662
    assert imd / fp * 100 == pytest.approx(33.030420827960086, rel=1e-12)


def test_idmd_collection_counters() -> None:
    token = capture("identity_token.json")
    assert token["total_supply"] == "2000"
    assert token["type"] == "ERC-721"
    assert token["holders_count"] == "667"
    counters = capture("identity_counters.json")
    assert counters["token_holders_count"] == "667"
    assert counters["transfers_count"] == "7411"


# ---------------------------------------------------------------------------
# IDMD transfers — the page that is not a day
# ---------------------------------------------------------------------------


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_the_idmd_transfer_page_is_not_a_day() -> None:
    """Guards against counting *one page* as transfers/24h: the captured page spans
    2026-08-07T23:05:35 .. 2026-08-08T09:51:59 — under eleven hours.

    WP1.8's ``_count_transfers_24h()`` is what makes that safe: live, the endpoint
    paginates, and the count follows cursors until it sees a row older than
    ``now - 86400`` — answering ``None`` if the page budget runs out first, because
    a lower bound rendered as a daily rate is a wrong number.  Not a ``/counters``
    delta across refreshes: that measures the gap between two observations, so it
    is either a 60-second sample scaled up or a number that does not exist until
    the dashboard has run for a day."""
    stamps = sorted(r["timestamp"] for r in rows_of("identity_transfers_page1.json"))
    assert len(stamps) == 25
    assert (_ts(stamps[-1]) - _ts(stamps[0])).total_seconds() < 11 * 3600


def test_no_idmd_transfer_row_carries_a_price() -> None:
    """Realized prices live in Seaport ``OrderFulfilled`` logs, not here — which is
    why ``nft_last_sales[].eth`` has no source in this capture set (open issue 2)."""
    rows = rows_of("identity_transfers_page1.json")
    assert all(r["token"]["symbol"] == "IDMD" for r in rows)
    assert all(r["token_type"] == "ERC-721" for r in rows)
    assert all(set(r["total"]) == {"token_id", "token_instance"} for r in rows)
    assert all("value" not in r for r in rows)
    seaport = [r for r in rows if (r["method"] or "").startswith(("fulfill", "match"))]
    assert len(seaport) == 24
```

- [ ] Run and state the expected failure — run it *before* WP0.3 lands. The `KNOWN_LABELS`
      import is function-local, so this is a test failure and not a collection error, and it
      is the only one:
      `.venv/bin/python -m pytest tests/data/test_surf_captures.py -k poisoning -v`
      → `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_addresses'` inside
      `test_the_four_poisoning_rows_are_one_gwei_inbound_from_lookalikes`.
      Every other test in this task passes immediately: the data is already committed, which
      is the point — these tests document the captures, they do not drive new code. That is
      also why this task may be done at any point after WP0.3 without blocking anything.
- [ ] Run to green (after WP0.3):
      `.venv/bin/python -m pytest tests/data/test_surf_captures.py -v` (28 passed —
      3 from WP0.6 and 25 here).
- [ ] Prove a test bites (decoder-shaped selection, house rule): in
      `test_bridge_in_mints_come_from_the_zero_address`, drop the
      `r["token"]["address_hash"] == IMD` filter so `mints` is `from_zero`, run
      `.venv/bin/python -m pytest tests/data/test_surf_captures.py -k bridge_in -v`
      → FAILS on `len(mints) == 2` (it is 3 — a spoof token mints from `0x0` too). Restore.
- [ ] Commit:
      `git add tests/data/test_surf_captures.py && git commit -m "test(surf): pin every capture fact the other work packages hardcode"`

---

### Task WP0.8: Suite guards and WP0 sign-off

**Files:**
- Modify: `tests/data/test_surf_captures.py`
- Test: the whole suite

**Interfaces:**
- Produces: the guarantee later WPs rely on — the capture set is complete, immutable and
  unreachable from shipped code, and the fixtures root is free for each WP's own subdirectory.
- Consumes: everything above.

**Steps:**

- [ ] Append the final guards:

```python
# ---------------------------------------------------------------------------
# suite-wide guards
# ---------------------------------------------------------------------------


def test_the_capture_inventory_is_complete() -> None:
    """29 JSON captures + the README + the agent card.  A later work package
    deleting one, or quietly re-capturing under a new name, fails loudly here."""
    assert {p.name for p in CAPTURES.iterdir()} == {
        "README.md",
        "agent_card_ipfs.txt",
        "announce_eth_info.json",
        "announce_eth_txs.json",
        "dexscreener_fp.json",
        "dexscreener_imd.json",
        "ens_surfsurf.json",
        "eth_search_frenpet.json",
        "fp_base_token.json",
        "geckoterminal_fp.json",
        "geckoterminal_imd.json",
        "identity_contract.json",
        "identity_counters.json",
        "identity_holders_page1.json",
        "identity_info.json",
        "identity_instances_sample.json",
        "identity_token.json",
        "identity_transfers_page1.json",
        "imd_contract.json",
        "imd_counters.json",
        "imd_holders.json",
        "imd_info.json",
        "imd_token.json",
        "ops_eth_info.json",
        "ops_eth_token_transfers.json",
        "ops_eth_txs.json",
        "reg_contract.json",
        "reg_info.json",
        "wallet_eth_info.json",
        "wallet_eth_token_transfers_page1.json",
        "wallet_eth_txs_page1.json",
    }


def test_the_capture_set_stays_small() -> None:
    """Provenance, not an archive.  1.6 MB on 2026-08-08; the captures were already
    trimmed at capture time (paginated lists cut to one page, strings over 4000
    chars end in ``...TRUNCATED``).  A re-capture that forgets that trimming shows
    up here before it shows up in a clone."""
    total = sum(p.stat().st_size for p in CAPTURES.rglob("*") if p.is_file())
    assert total < 4_000_000, f"capture set has grown to {total} bytes"


def test_nothing_shipped_reads_the_captures() -> None:
    """``tests/fixtures/`` is test-only material and is not in the wheel, so a
    runtime read would be a ``FileNotFoundError`` on every installed copy."""
    package = SURF_FIXTURES.parents[2] / "maxpane_dashboard"
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "fixtures/surf" not in source, path
        assert "surf_fixtures" not in source, path
```

- [ ] Prove the inventory guard bites:
      `mv tests/fixtures/surf/captures/imd_token.json /tmp/ && .venv/bin/python -m pytest tests/data/test_surf_captures.py -k inventory -v`
      → `test_the_capture_inventory_is_complete` FAILS. Move it back.
- [ ] Run the new suite green:
      `.venv/bin/python -m pytest tests/data/test_surf_addresses.py tests/data/test_surf_models.py tests/data/test_surf_captures.py -v`
- [ ] Confirm WP0 shipped no fixture file — the decision, checked rather than remembered:
      `ls tests/fixtures/surf` → `captures` and nothing else;
      `git ls-files tests/fixtures/surf | grep -v '^tests/fixtures/surf/captures/'` → empty.
- [ ] Run the whole suite and confirm nothing else moved:
      `.venv/bin/python -m pytest -q` → previous count + the WP0 tests, **1 skipped**, 0
      failures. The skip is `test_signal_output_keys_are_a_subset_of_surf_keys` (WP0.5) and
      it is expected until `analytics/surf_signals.py` exists; confirm it is the only one
      with `.venv/bin/python -m pytest -q -rs | grep surf`.
- [ ] Record the one WP0 obligation that outlives this sign-off: the containment test's
      prove-it-bites step is **deferred to the day `analytics/surf_signals.py` merges**,
      because a skipped test proves nothing. The procedure is written out in WP0.5's last
      step (rename `sig_burn_state` → `sig_burns_state` in `SIGNAL_OUTPUT_KEYS`, watch it go
      red naming that key, restore). Hand it to whoever merges the signals module.
- [ ] Commit:
      `git add tests/data/test_surf_captures.py && git commit -m "test(surf): add the capture inventory, size and no-runtime-read guards"`

---

## What WP0 hands to the other work packages

Consumers are named by the module they own — the WP numbering differs between the plan
documents, and a path cannot be misread.

| Consumer | Imports from WP0 |
|---|---|
| `data/surf_client.py` | every constant in `surf_addresses` (including `SEL_OWNER_OF`); all seven models **and** `CONSTRUCTOR_KWARGS` |
| `analytics/surf_signals.py` | `ANNOUNCE`, `DEV_WALLET`, `OPS_WALLET`; `CHANNEL_KINDS`, `SIGNAL_STATES`, the `sig_*` names in `SURF_KEYS` |
| `data/surf_cache.py` | `SURF_KEYS` (which series it persists) — plus `data/series_points.coerce_points`, which already exists |
| `data/surf_manager.py` | `SURF_KEYS`, `SURF_ROW_KEYS`, all seven models, `KNOWN_LABELS` |
| `widgets/surf/*` | `SURF_KEYS` — **in the contract test only.** The widget modules themselves import nothing from WP0: their package ships an AST import-hygiene test asserting no surf widget module imports `maxpane_dashboard.data`, `analytics` or `surf_addresses`. Row shapes reach them as literal keys (they must match `SURF_ROW_KEYS`, but the widgets do not import it), and `KNOWN_LABELS` reaches them **pre-resolved** — as the `counterparty` string the client looked up plus the `counterparty_known` boolean `surf_manager._activity_rows` derives from it. |
| `screens/surf.py` | `SURF_KEYS` (the flat dict it dispatches) |
| **all of them** | `tests/fixtures/surf/captures/` as the only source material, and `tests.surf_fixtures.capture()` to read it. **WP0 hands over no fixture file** — each WP slices what it needs into its own `tests/fixtures/surf/<dir>/`, and the facts those slices must preserve are pinned in `tests/data/test_surf_captures.py` (WP0.7). |

## Open issues WP0 records but does not resolve

1. **`identityAllowed()` target.** The selector is verified against the IdentityMD source, but
   the *registry*'s own source is not in the capture set. The client WP must confirm live that
   `IDENTITY_REGISTRY` answers it (the NFT's copy is bricked-false forever). If the registry
   uses a different getter, `SEL_IDENTITY_ALLOWED` and its preimage change together.
2. **No Seaport `OrderFulfilled` log capture**, so `nft_last_sales[].eth` has no source. Either
   the client WP captures a real log window, or `nft_last_sales` ships empty with the explicit
   unavailable state. Do not synthesize prices. WP0.7's
   `test_no_idmd_transfer_row_carries_a_price` is what keeps this honest: the transfer page
   looks like it should carry a price and does not.
3. **No `nft_dev_holdings` capture.** The dev is not in the top-60 holders page; the figure
   needs `balanceOf(DEV_WALLET)` or the address token-balance endpoint. The client WP picks one.
4. **No contract-creation row exists in any capture**, so the NEW DEPLOY detector has no real
   vector. WP0.7 pins both the absence
   (`test_no_captured_transaction_creates_a_contract`, across all 101 captured txs) and the
   only real deploy evidence (`imd_info.json`'s `creation_transaction_hash` +
   `creator_address_hash`). The WP that tests the detector builds its own flagged-synthetic
   row and reuses those two real values rather than inventing a hash.
5. **The ISO→epoch parser is not in the frozen surface.** Blockscout serves
   `"2026-08-07T04:27:11.000000Z"`; models carry `ts: float`. The client WP owns the helper
   (`surf_client._parse_ts`) and must be the only place it exists.
6. **Two Blockscout holder counts disagree** (IMD 1148 vs 1132). The manager picks one source
   per figure and the hero says which; do not average them. Pinned by WP0.7.
7. **`KNOWN_LABELS` has no entry for `0xA4aD5765…`** (the correspondent who received IDMD #0
   and #946): the research note truncates the address and no capture contains it in full.
   It renders dimmed until someone reads the full address off chain.
8. **Task instruction vs capture reality:** the 1-gwei lookalike rows live in
   `captures/ops_eth_txs.json` (native ETH sends), not `ops_eth_token_transfers.json` — that
   file holds the *homoglyph token* spoofs (`ĖTḨ`, ` UЅDС `, `USDС`, `ETHG`, and one row whose
   symbol is `null`). WP0.7 pins both shapes; the widget WP must defend against both.
9. **CLOSED — `NftStats.written` has a producer: WP1.8's `_count_identities_written()`.**
   *(Was: "no producer yet, so `identities_written` / `nft_written` are `None` in v1", on the
   premise that the only keyless route needed a vendored deploy block no capture contains.
   That premise was wrong — the route taken is a REST log view, not an archive `eth_getLogs`
   sweep, so no deploy block is required.)* The IdentityMD source in the captures
   (`src/IdentityMD.sol`) does expose `totalSupply` and `identityAllowed` and *no*
   written-hash counter, so the "1 of 2000" figure still cannot be read with an `eth_call`.
   The client instead counts **distinct `topics[1]`** over Blockscout's
   `/addresses/{IDENTITY_REGISTRY}/logs`, filtered on `TOPIC_IDENTITY_HASH_UPDATED` — keyless,
   lifetime, page-bounded, `None` when the bound is hit before the last page (a lower bound is
   not a count). Distinct ids, not rows: re-writing one token's hash is one identity written,
   not two. `NftStats.written` is the **single** producer for both flat keys —
   `ChainState` has no `identities_written` field — so the manager reads `stats.written` for
   the hero and the NFT panel alike.
   Two constraints survive and are the whole reason this issue stays on the page:
   **(a) never back-fill `written` from `len(LogWindow.identity_updates)`** — that is a
   *recent-window* count, and presenting it as an all-time total would read "1 of 2000" today
   and "0 of 2000" the moment the window slid past the only write (the write happened
   2026-05-14, months outside any window this client opens); the windowed count is a *signal
   detail* ("n writes since the gate opened"), never the hero number. **(b)** the log view is
   the one WP1.8 endpoint no capture proves — WP1.8's first step curls it. If this Blockscout
   build lacks it, `written` degrades to `None`, the widget renders `— / 2000`, and the
   fallback is *not* a windowed count and *not* an archive backfill on a keyless pool.
10. **CLOSED — `NftStats.transfers_24h` has a producer: WP1.8's `_count_transfers_24h()`.**
    *(Was: "likewise starts `None` … until it derives the rate".)* Blockscout serves the
    lifetime `transfers_count` (7,411) on `/counters`; the PRD hero wants a daily rate, and
    the two stay separate fields so the lifetime number can never be rendered as a daily one.
    The rate is counted off `/tokens/{IDMD}/transfers`, newest-first, following cursors until
    a row older than `now - 86400` appears (or the server stops offering one) — with the
    injected clock, never `time.time()`. WP0.7's `test_the_idmd_transfer_page_is_not_a_day`
    is why the page bound matters rather than why the derivation is impossible: the captured
    page spans under eleven hours, so **hitting the page budget while still inside the window
    returns `None`, not the partial count**. The live constraint that remains:
    **never render `transfers_total` as a rate**, and never substitute one field for the
    other when the other is `None`.
11. **The model vocabulary is frozen by WP0.4 and by nothing else.** The client and manager WPs
    must restate their *Consumes* tables from the built module (`CONSTRUCTOR_KWARGS`), not from
    their own drafts. An earlier revision of this plan carried three different spellings of
    `ChainState`; the constructor calls would have raised `TypeError` and the
    `getattr(state, ..., None)` reads would have returned `None` for the entire hero with every
    test green. WP0.4 must therefore be merged before either writes code.
12. **Two different synthetic pool prices are in flight, and WP0 does not own either.** WP0.7
    pins the capture-derived figure: `dexscreener_imd.json` quotes `priceNative
    "0.0003686"` WETH per IMD, i.e. **2712.9679869777538** IMD per WETH (token0 = WETH <
    token1 = IMD, so the pool price is the inverse). The client WP's plan currently encodes its
    synthetic `slot0` from `2749.578620645` / tick `79188`. Both are synthetic test vectors, so
    neither is wrong on chain — but any assertion that cross-checks a decoded price against a
    market capture must use the capture-derived number, or it will fail for the right reason
    and be "fixed" by loosening the tolerance. Flag this to the client WP before it writes
    `encode_slot0_return()`.
13. **The fixture-ownership decision is load-bearing for three WPs and is recorded in exactly
    one place** (*Fixture ownership*, above). If a second work package ever needs a slice that
    already exists in another's directory, the answer is a shared reader added to
    `tests/surf_fixtures.py` — not a fourth copy of the same 2026-08-08 payload. The root
    guard in WP0.6 catches a stray file; nothing catches a duplicate in a sibling directory
    except this note and review.
