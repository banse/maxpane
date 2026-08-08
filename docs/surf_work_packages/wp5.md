# WP5 — SurfScreen (screens/surf.py + tests)

**Goal:** Compose the six surf widgets into the approved slot grid with title-bar degradation, SURF_KEYS dispatch, the `c` feed/activity swap, RefreshGuard scheduling, and a measured, pinned full-layout width.

**Work-package ownership (the single source — quote this table, never memory).** Earlier drafts of this plan set carried three mutually inconsistent numberings, so a note saying "confirm with WP4" could route a widget question to the manager owner. The mapping below is the one the other files' own `Owner note` sections declare, and every WP reference in this document has been rewritten against it:

| WP | Owns | What this WP hands to WP5 |
|---|---|---|
| WP0 | `data/surf_addresses.py`, `data/surf_models.py`, `tests/fixtures/surf/**` | `SURF_KEYS`, the seven model dataclasses, the committed captures |
| WP1 | `data/surf_client.py` | (nothing directly — WP5 never imports the client) |
| WP2 | `analytics/surf_signals.py` | (nothing directly — signals reach WP5 through the manager payload) |
| WP3 | `maxpane_dashboard/widgets/surf/**` | the six widget classes, their `update_data` kwargs and their rendered copy |
| WP4 | `data/surf_cache.py`, `data/surf_manager.py` | `SurfManager.fetch_and_compute()` / `close()` |
| **WP5** | **`screens/surf.py`, `tests/screens/test_surf_screen.py`** | — (this document) |
| WP6 | `app.py`, `screens/game_select.py`, `__main__.py`, `themes/minimal.tcss`, `CLAUDE.md`, `README.md`, `pyproject.toml` | registration; consumes WP5's hand-off note |

**Dependencies:** WP0 (`data/surf_models.py` — `SURF_KEYS`), WP3 (`widgets/surf/` — `SurfHero`, `SurfSignals`, `SurfFeed`, `SurfDevActivity`, `SurfMarket`, `SurfNft`), WP4 (`data/surf_manager.py` — `SurfManager.fetch_and_compute()`/`close()`).

**Owner note:** This WP owns exactly two files: `maxpane_dashboard/screens/surf.py` and `tests/screens/test_surf_screen.py`. It does **not** touch `app.py`, `screens/game_select.py`, `__main__.py`, or `themes/minimal.tcss` — those have one owner (WP6). Two coordination points for WP6 are called out below and enforced mechanically where possible:

1. **`themes/minimal.tcss` needs a surf block.** Precedent: FWA required one (`minimal.tcss` line 1771, "── FWA screen ──"), because `DEFAULT_CSS` is a structural fallback only and the registered themes restate it. `SurfScreen.DEFAULT_CSS` (Task WP5.1) keeps the screen correctly proportioned under any theme with no surf block, so WP5's tests pass before WP6 lands; WP6 should copy the `DEFAULT_CSS` block into `minimal.tcss` the way the FWA block does, **without adding vertical padding to the hero row** (the FWA coverage-badge clipping lesson, `tests/screens/test_fwa_screen.py::test_ev_coverage_badge_survives_the_real_stylesheet`).
2. **`__main__.FULL_LAYOUT_COLUMNS` (currently 143) must cover surf.** Task WP5.5 measures the surf layout's real requirement, pins it as `screens/surf.py::SURF_FULL_LAYOUT_COLUMNS`, and adds a test that fails with an explicit WP6 hand-off message if surf needs more than `__main__` documents.

**Interface this WP consumes from WP3 (the widget contract).** The frozen surface pins the six class names but not their `update_data` signatures. This WP dispatches exactly the PRD §5 key groups, keyword-by-keyword; **WP3 — the owner of `widgets/surf/`** — must accept these kwargs (extras rejected, all optional with `None` defaults, house idiom):

| Widget | `update_data(...)` kwargs (exact) |
|---|---|
| `SurfHero` | `hook_status, lp_liquidity, lp_imd, lp_weth, lp_owner_ok, gate_open, identities_written, imd_supply, imd_burned_cum` |
| `SurfSignals` | `sig_post_state, sig_post_detail, sig_post_age_s, sig_lp_state, sig_lp_detail, sig_lp_age_s, sig_gate_state, sig_gate_detail, sig_gate_age_s, sig_deploy_state, sig_deploy_detail, sig_deploy_age_s, sig_bridge_state, sig_bridge_detail, sig_bridge_age_s, sig_burn_state, sig_burn_detail, sig_burn_age_s` |
| `SurfFeed` | `feed_items, feed_nonce, feed_last_post_age_s` |
| `SurfDevActivity` | `dev_activity` |
| `SurfMarket` | `imd_price_usd, imd_change_24h_pct, imd_vol_24h_usd, pool_liquidity_usd, fp_price_usd, parity_pct, supply_series, price_series` |
| `SurfNft` | `nft_holders, nft_transfers_24h, nft_dev_holdings, nft_written, nft_last_sales, nft_floor` |

Meta keys the screen itself consumes (never dispatched): `as_of`, `degraded`, `eth_usd`. Title-bar keys (`imd_price_usd`, `parity_pct`, `feed_nonce`, `feed_last_post_age_s`) are *also* dispatched to their widgets — dual consumption, same as FWA.

Rendered strings this WP asserts against and therefore consumes from WP3, the widget owner (confirm the kwarg list and the copy with WP3 before WP3 freezes its signatures — **not** with WP4, which owns the manager): panel titles `SIGNALS`, `ANNOUNCE FEED`, `DEV ACTIVITY`, `MARKET`, `IDMD NFT`; the six detector row labels `NEW POST`, `LP MIGRATION`, `GATE OPEN`, `NEW DEPLOY`, `BRIDGE STAGE`, `BURN` (PRD §3 names); the hero hook words `NOT LIVE` / `LAUNCHED` (module constants `HOOK_NOT_LIVE` / `HOOK_LAUNCHED`, imported by the test rather than retyped) and the observed-burn line `burned {n:,.0f} observed`; the unknown-counterparty form `0x` + first 8 + `…` + last 6 (`_fmt.long_addr`); the floor line `no keyless source` (PRD §4 pins `n/a — no keyless source`); the house marker `‹ widen`.

**Payload *values*, by contrast, are WP2's and WP4's — not WP3's.** The six `sig_*_detail` strings in this WP's fixture are copied from WP2's detector bodies and `MATRIX` table (`closed · 1 written`, `liquidity holds`, `no new contract`, `mint 114,367 IMD → frenpet.eth`, `supply flat · last: …`, and `LP_POST_DETAIL`'s `#N "…"` form with straight quotes); `hook_status` is spelled the way WP4's `_hook_status()` returns it; `imd_burned_cum` is observation-scoped per WP4.5. Inventing a plausible-looking string or number here calibrates the layout width and the widget rendering against a payload the manager can never emit — the failure mode this table exists to prevent.

**Layout (approved, PRD §4):**

```
#title-bar        SURF · IMD $0.71 · parity -2.7% · feed #14 (23h) [· flags][· degraded: …] · vX.Y.Z
#hero-row         SurfHero (3fr)              | SurfSignals (2fr)          height 10
#middle-row       SurfFeed (3fr)              | SurfMarket (2fr)           1fr
                  SurfDevActivity (3fr, hidden — `c` swaps it with the feed)
#separator
#bottom-row       SurfNft (full width)                                     1fr
StatusBar
```

All sample payloads below are derived from the real captures in
`tests/fixtures/surf/captures/` (values re-verified while writing this plan):
announce channel has 21 txs, latest self-post nonce 13 at `2026-08-07T04:27:11Z`
= epoch `1786076831`, text `"I moved 33 eth to the LP on mainnet https://etherscan.io/tx/0x90a0f8e2…"`
(hash `0xe397869a2ed1299f24618c377112a6e9637395d2c1e21e742ce30e6201440055`);
nonce 12 at epoch `1785903575`; community reply from
`0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159` at epoch `1785795251` containing a
typographic apostrophe (markup-relevant); `dexscreener_imd.json` pair:
priceUsd `0.7074`, h24 change `30.89`, h24 volume `244178`, liquidity usd
`548701.21` / base `388421` IMD / quote `142.7067` WETH; `dexscreener_fp.json`
priceUsd `0.7274` → parity `(0.7074/0.7274 − 1)·100 = −2.7495…%`;
`imd_token.json` total_supply `2376731868679000000000000` (2,376,731.868679 IMD);
`identity_counters.json` holders `667`.

**PRD §1 background, *not* a payload value:** the all-time burn ledger is
12,039 + 31,064 + 15,745 = 58,848 IMD. `imd_burned_cum` is **not** that number
and can never become it — WP4 derives it from `SurfCache.observed_burn_total()`,
an accumulator over successive `totalSupply` readings that returns `None` before
the first successful read and `0.0` after it (wp4.md, WP4.5 and WP4 open issue 4:
the three historical burns predate any install and have no keyless source). The
fixture below therefore carries the single **observed** 2026-08-05 event,
`15_745.0`; `58_848.0` would pin a number the data layer cannot produce and would
quietly certify all-time copy through WP3.2's `burned {n:,.0f} observed` string.

Likewise the six `sig_*_detail` strings in the fixture are **WP2's output
vocabulary**, copied from `analytics/surf_signals.py`'s detector bodies and the
`MATRIX` table in wp2.md Tasks WP2.4–WP2.8 — not prose invented here. They must be
re-copied whenever a WP2 detector's detail changes.

---

### Task WP5.1: Screen skeleton — compose, bindings, DEFAULT_CSS

**Files:**
- Create: `maxpane_dashboard/screens/surf.py`
- Test: `tests/screens/test_surf_screen.py` (create)

**Interfaces:**
- Consumes: `maxpane_dashboard.screens.refresh_guard.RefreshGuard`; `maxpane_dashboard.widgets.surf.{SurfHero,SurfSignals,SurfFeed,SurfDevActivity,SurfMarket,SurfNft}`; `maxpane_dashboard.widgets.status_bar.StatusBar`; `maxpane_dashboard.data.surf_models.SURF_KEYS`.
- Produces: `class SurfScreen(RefreshGuard, Screen)` with `__init__(self, data_manager, poll_interval: int = 30, name: str = "surf", **kwargs)`, `REFRESH_WORKER_NAME = "surf-refresh"`, `BINDINGS` = `r` + `c`, `INITIAL_TITLE = "SURF · Mission Control · Ethereum Mainnet"`, slot ids `#title-bar #hero-row #middle-row #separator #bottom-row`.

**Steps:**

- [ ] Read `maxpane_dashboard/screens/fwa.py` end-to-end (already summarized above, but the implementer must read it — the module docstring explains *why* every structural choice below is what it is). Also skim `screens/talismans.py` for the second `c`-swap example.

- [ ] Write the failing test. Create `tests/screens/test_surf_screen.py` with the harness, the captures-derived payload, and the mount/bindings tests:

```python
"""Headless Textual tests for the surf dashboard screen (WP5).

A fake manager returns the frozen ``SURF_KEYS`` dict (no network), the screen
is pushed via ``App.run_test()``, and we assert against **composited output**
(``_compositor.render_strips()``), never a widget's content string alone.

Zero network, zero wall clock: every time-derived string
(``feed_last_post_age_s``, signal ages) arrives pre-computed in the payload,
which is why the fetch instant 2026-08-08T04:00:00Z can be replayed forever.
All sample values are lifted from ``tests/fixtures/surf/captures/`` — the real
payloads fetched 2026-08-08 — not invented.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App

from maxpane_dashboard import __version__
from maxpane_dashboard.data.surf_models import SURF_KEYS
from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)
# Imported, never re-spelled: the hook vocabulary is WP4's
# ``SurfManager._hook_status()`` ("LAUNCHED" / "NOT LIVE" / None), frozen in
# WP0's SURF_KEYS comment and PRD §4, and WP3's SurfHero branches on these two
# constants. A lowercase-snake literal here would drive the widget's unknown-
# value arm, so this file would certify a render nobody will ever see.
from maxpane_dashboard.widgets.surf.hero import HOOK_NOT_LIVE

_THEMES = Path(__file__).resolve().parents[2] / "maxpane_dashboard" / "themes"
_TCSS = _THEMES / "minimal.tcss"

_WIDGET_CLASSES = {
    "SurfHero": SurfHero,
    "SurfSignals": SurfSignals,
    "SurfFeed": SurfFeed,
    "SurfDevActivity": SurfDevActivity,
    "SurfMarket": SurfMarket,
    "SurfNft": SurfNft,
}

#: The WP3<->WP5 dispatch contract: exactly the PRD §5 key groups.  Local copy
#: until WP0 exports SURF_WIDGET_SIGNATURES beside SURF_KEYS (open issue) — the
#: mechanical dispatch test below still catches any drift against SURF_KEYS.
SURF_WIDGET_SIGNATURES = {
    "SurfHero": (
        "hook_status", "lp_liquidity", "lp_imd", "lp_weth", "lp_owner_ok",
        "gate_open", "identities_written", "imd_supply", "imd_burned_cum",
    ),
    "SurfSignals": (
        "sig_post_state", "sig_post_detail", "sig_post_age_s",
        "sig_lp_state", "sig_lp_detail", "sig_lp_age_s",
        "sig_gate_state", "sig_gate_detail", "sig_gate_age_s",
        "sig_deploy_state", "sig_deploy_detail", "sig_deploy_age_s",
        "sig_bridge_state", "sig_bridge_detail", "sig_bridge_age_s",
        "sig_burn_state", "sig_burn_detail", "sig_burn_age_s",
    ),
    "SurfFeed": ("feed_items", "feed_nonce", "feed_last_post_age_s"),
    "SurfDevActivity": ("dev_activity",),
    "SurfMarket": (
        "imd_price_usd", "imd_change_24h_pct", "imd_vol_24h_usd",
        "pool_liquidity_usd", "fp_price_usd", "parity_pct",
        "supply_series", "price_series",
    ),
    "SurfNft": (
        "nft_holders", "nft_transfers_24h", "nft_dev_holdings",
        "nft_written", "nft_last_sales", "nft_floor",
    ),
}

#: Keys the screen itself consumes: ``as_of`` (freshness bookkeeping),
#: ``degraded`` (title bar), ``eth_usd`` (context; unrendered in v1).
META_KEYS = frozenset({"as_of", "degraded", "eth_usd"})

# -- fixed instants, all from tests/fixtures/surf/captures/ -------------
_TS_POST_13 = 1_786_076_831   # announce nonce 13, 2026-08-07T04:27:11Z
_TS_POST_12 = 1_785_903_575   # announce nonce 12, 2026-08-05T04:19:35Z
_TS_REPLY = 1_785_795_251     # pasta-sauce reply, 2026-08-03T22:14:11Z
_AS_OF = 1_786_161_600.0      # the fetch instant: 2026-08-08T04:00:00Z
_ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
_REPLIER = "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159"
# Full 42-char addresses, never pre-shortened: WP3's ``long_addr`` returns any
# string of 17 characters or fewer unchanged, so a short-form fixture would
# make the poisoning defence a no-op in this file. Both are live in
# frenpet.eth's history today (ops_eth_txs.json) and are the two WP3 and WP4
# test against.
_REAL_UNKNOWN = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"   # unlabelled LP-fee dest
_SPOOF = "0xF3083828702C1989710CECA517412071c2f60Ee6"          # 1-gwei lookalike


def _sample_data() -> dict:
    """A representative full payload, every value captures-derived."""
    return {
        # -- meta ---------------------------------------------------------
        "as_of": _AS_OF,
        "degraded": [],
        "eth_usd": 1919.2,          # 0.7074 / priceNative 0.0003686
        # -- feed ---------------------------------------------------------
        "feed_nonce": 14,           # eth_getTransactionCount(announce)
        "feed_last_post_age_s": _AS_OF - _TS_POST_13,   # 84769.0 -> "23h"
        "feed_items": [
            {
                "ts": _TS_POST_13,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "from_label": "announce",
                "text": (
                    "I moved 33 eth to the LP on mainnet "
                    "https://etherscan.io/tx/0x90a0f8e2b039e8d86d1b10e33e6"
                    "1e12d13728444e0a9e5ac258051cccb64d669. Hopefully in "
                    "the coming days will be able to share more what been "
                    "working on, as always 0 promises."
                ),
                "tx_hash": "0xe397869a2ed1299f24618c377112a6e9637395d2c1e2"
                           "1e742ce30e6201440055",
            },
            {
                "ts": _TS_POST_12,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "from_label": "announce",
                "text": "@RektSconey created this explorer of the NFTs "
                        "https://idmd-reader.pages.dev. Burned 15745 more "
                        "tokens from the LP fees, made huge progress today "
                        "on the system, will share more when have something "
                        "concrete.",
                "tx_hash": "0xeb2b8272330a0224df369373d177356ca321668f44d5"
                           "2e2e46f08645bcf36fc8",
            },
            {
                # the community reply, typographic apostrophe intact —
                # markup-hostile third-party text (PRD §6.4)
                "ts": _TS_REPLY,
                "kind": "reply",
                "from_addr": _REPLIER,
                "from_label": None,
                "text": "Bro cooked this so hard it smells like my "
                        "grandma’s pasta sauce after marinating "
                        "overnight. Absolute Michelin alpha.",
                "tx_hash": "0xdcb8bf92a26aac481939880c17087e66fc32b036eb84"
                           "3bd7f10fb302ade760c9",
            },
        ],
        # -- signals (states the product can emit: ok/watch/fired/None) ----
        #
        # Every detail string below is **WP2's output vocabulary**, copied
        # verbatim from the detector bodies and the ``MATRIX`` table in
        # wp2.md Tasks WP2.4-WP2.8 -- not paraphrased. ``build_signals``
        # cannot emit anything else, and this screen's composited assertions
        # (and the WP5.5 width measurement) are calibrated on these exact
        # widths. Re-copy them if a WP2 detector's detail changes.
        #
        # Two state/age pairings worth reading twice, both WP2 rules
        # (``FIRED_TTL_S = 86400``):
        #   * post + bridge are ``fired`` because their ages are under 24 h;
        #     a FIRED row keeps the *event's* detail verbatim.
        #   * burn is ``ok`` because its event is 2.99 d old, so WP2 relaxes
        #     it to the composed ``<live detail> · last: <event detail>``
        #     form while keeping the event's age.
        "sig_post_state": "fired",
        # WP2's LP_POST_DETAIL -- the "#N" form with straight quotes and a
        # 48-char body ellipsis, not a "nonce 13 → 14" gloss.
        "sig_post_detail": '#14 "I moved 33 eth to the LP on mainnet https://eth…"',
        "sig_post_age_s": _AS_OF - _TS_POST_13,
        "sig_lp_state": "ok",
        "sig_lp_detail": "liquidity holds",
        "sig_lp_age_s": None,
        "sig_gate_state": "ok",
        # No "/2000": WP2 omits the denominator deliberately (the cap is a
        # documented number, and documented numbers are read live or not
        # shown -- CLAUDE.md rule 4). WP2's `test_no_live_value_is_hardcoded`
        # bans the literal 2000 from that module outright.
        "sig_gate_detail": "closed · 1 written",
        "sig_gate_age_s": None,
        "sig_deploy_state": "ok",
        "sig_deploy_detail": "no new contract",
        "sig_deploy_age_s": None,
        "sig_bridge_state": "fired",
        "sig_bridge_detail": "mint 114,367 IMD → frenpet.eth",
        "sig_bridge_age_s": _AS_OF - (_TS_POST_13 - 720.0),  # staged 12 min pre-add
        "sig_burn_state": "ok",
        "sig_burn_detail": "supply flat · last: burn 15,745 IMD",
        "sig_burn_age_s": _AS_OF - _TS_POST_12,   # 2.99 d -> relaxed past FIRED_TTL_S
        # -- hero -----------------------------------------------------------
        # ``hook_status`` is spelled the way the *producer* spells it: WP4's
        # ``SurfManager._hook_status()`` returns exactly "LAUNCHED" / "NOT
        # LIVE" / None, WP0's SURF_KEYS comment freezes it, and WP3's
        # SurfHero branches on HOOK_NOT_LIVE / HOOK_LAUNCHED. The constant is
        # imported rather than retyped so this fixture cannot drift back to
        # the lowercase-snake form, which canonicalises to "NOT_LIVE", misses
        # both branches and renders the widget's fallback arm ("NOT_LIVE" /
        # "unrecognized status") -- a render no live payload can produce.
        "hook_status": HOOK_NOT_LIVE,
        "lp_liquidity": 2_162_384_733_113_558_190,   # raw uint128, abbreviated by the widget
        "lp_imd": 388_421.0,
        "lp_weth": 142.7067,
        "lp_owner_ok": True,
        "gate_open": False,
        "identities_written": 1,
        "imd_supply": 2_376_731.868679,
        # The observed 2026-08-05 event, NOT the 58,848 all-time ledger of
        # PRD §1: ``imd_burned_cum`` is observation-scoped (WP4.5 --
        # ``SurfCache.observed_burn_total()`` accumulates over successive
        # supply readings; ``None`` before the first successful read, ``0.0``
        # once watched with nothing moved). WP3's SurfHero prints it as
        # ``burned {n:,.0f} observed``, so an all-time value here would make
        # the screen certify an all-time claim that copy exists to avoid.
        "imd_burned_cum": 15_745.0,
        # -- market ---------------------------------------------------------
        "imd_price_usd": 0.7074,
        "imd_change_24h_pct": 30.89,
        "imd_vol_24h_usd": 244_178.0,
        "pool_liquidity_usd": 548_701.21,
        "fp_price_usd": 0.7274,
        "parity_pct": -2.7495188834204012,   # (0.7074/0.7274 - 1) * 100
        "supply_series": [
            [_TS_POST_12 - 86_400, 2_392_476.868679],  # before the 15,745 burn
            [_TS_POST_12, 2_376_731.868679],           # the step down
            [int(_AS_OF), 2_376_731.868679],
        ],
        "price_series": [
            [int(_AS_OF) - (23 - i) * 3600, 0.5404 + i * 0.00726]
            for i in range(24)                          # +30.89% over 24h
        ],
        # -- nft ------------------------------------------------------------
        "nft_holders": 667,
        "nft_transfers_24h": 38,
        "nft_dev_holdings": 3,
        "nft_written": 1,
        "nft_last_sales": [
            {"ts": int(_AS_OF) - 7_200, "token_id": 1204, "eth": 0.219},
            {"ts": int(_AS_OF) - 26_000, "token_id": 421, "eth": 0.2},
        ],
        "nft_floor": None,   # always None in v1 -> "n/a — no keyless source"
        # -- activity --------------------------------------------------------
        # Newest first, the order WP4's ``_activity_rows`` emits and the order
        # WP3's table renders without re-sorting.
        "dev_activity": [
            {
                # Unknown counterparty: the **full 42-char** address, which is
                # what WP4 emits (``_activity_rows`` writes the raw
                # ``counterparty`` string when there is no label;
                # ``test_an_unknown_counterparty_is_never_marked_known`` pins
                # exactly this one). A pre-shortened fixture would sail
                # through WP3's ``long_addr`` untouched -- it returns any
                # string of <=17 chars unchanged -- and the screen test would
                # bless the first-6/last-4 short form the anti-poisoning rule
                # exists to prevent. Renders dimmed as ``0x61CC704c…73f14E``.
                "ts": _TS_POST_13 - 60,
                "wallet_label": "surfsurf.eth",
                "kind": "transfer",
                "counterparty": _REAL_UNKNOWN,
                "counterparty_known": False,
                "value_eth": 0.31,
                "tx_hash": "0x" + "2b" * 32,
            },
            {
                # The live poisoning shape, end to end: a zero-value transfer
                # from an unknown lookalike. WP3's ``_row_markup`` drops the
                # (transfer, value 0, unknown) triple outright, so this row
                # must never reach a pixel -- asserted in WP5.4's
                # ``test_the_activity_view_defends_against_address_poisoning``.
                "ts": _TS_POST_13 - 120,
                "wallet_label": "frenpet.eth",
                "kind": "transfer",
                "counterparty": _SPOOF,
                "counterparty_known": False,
                "value_eth": 0.0,
                "tx_hash": "0x" + "3c" * 32,
            },
            {
                "ts": _TS_POST_13 - 300,
                "wallet_label": "frenpet.eth",
                "kind": "LP",
                "counterparty": "NFPM",
                "counterparty_known": True,
                "value_eth": 33.25,
                "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9"
                           "e5ac258051cccb64d669",
            },
            {
                "ts": _TS_POST_13 - 900,
                "wallet_label": "surfsurf.eth",
                "kind": "bridge",
                "counterparty": "OFT endpoint",
                "counterparty_known": True,
                "value_eth": 0.0,
                "tx_hash": "0x" + "1a" * 32,
            },
        ],
    }


def _frozen_payload(**overrides) -> dict:
    """Exactly ``SURF_KEYS`` — a key added upstream appears here as ``None``."""
    sample = _sample_data()
    payload = {key: sample.get(key) for key in SURF_KEYS}
    payload.update(overrides)
    return payload


def _all_none_payload() -> dict:
    """Every contract key present, every value ``None`` (full outage)."""
    return {key: None for key in SURF_KEYS}


class _FakeManager:
    """Stand-in for SurfManager that never touches the network.

    ``raises=True`` is a *defensive* double, not a model of an outage: the
    real ``SurfManager.fetch_and_compute`` never raises (WP4 guarantees the
    full ``SURF_KEYS`` dict with ``None`` values under every failure
    combination).  Use ``_all_none_payload()`` for an outage; ``raises=True``
    only to prove a mis-wired manager cannot take the screen down.
    """

    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self._payload = payload if payload is not None else _frozen_payload()
        self._raises = raises
        self._error_count = 3
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self._raises:
            raise RuntimeError("all three pools are down")
        return dict(self._payload)

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single SurfScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _ThemedHarness(_Harness):
    """Same, but with the real ``minimal.tcss`` loaded.

    Valid before WP6 adds a surf block: loading the stylesheet without surf
    rules leaves ``SurfScreen.DEFAULT_CSS`` in charge, and keeps passing after
    WP6 restates it.
    """

    CSS_PATH = _TCSS


def _screen_text(app) -> str:
    """Composited screen text — what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _plain(widget) -> str:
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


# -- contract sanity -----------------------------------------------------


def test_surf_keys_covers_the_local_signature_map():
    """Every dispatched kwarg is a contract key, and the map + META is total.

    This is the tripwire for WP0<->WP5 drift (the contract vs. this screen's
    dispatch map) while SURF_WIDGET_SIGNATURES lives locally: a key added to
    SURF_KEYS that no widget receives, or a kwarg here that left the contract,
    both fail loudly.
    """
    dispatched = {k for sig in SURF_WIDGET_SIGNATURES.values() for k in sig}
    assert dispatched <= set(SURF_KEYS), (
        f"dispatch kwargs not in SURF_KEYS: {sorted(dispatched - set(SURF_KEYS))}"
    )
    unconsumed = set(SURF_KEYS) - dispatched - META_KEYS
    assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"


def test_bindings_are_refresh_and_the_view_toggle():
    """``c`` swaps the announce feed and the dev-activity table in one slot."""
    keys = {binding.key for binding in SurfScreen.BINDINGS}
    assert keys == {"r", "c"}


# -- mount ---------------------------------------------------------------


async def test_screen_mounts_all_six_widgets():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()

        for cls in _WIDGET_CLASSES.values():
            screen.query_one(cls)
        # Slot grid: hero row holds two widgets, middle row the swap pair
        # plus the market, bottom row the NFT panel alone.
        assert len(screen.query_one("#hero-row").children) == 2
        assert len(screen.query_one("#middle-row").children) == 3
        assert len(screen.query_one("#bottom-row").children) == 1
        # The dev-activity view starts hidden; the feed starts showing.
        assert screen.query_one(SurfFeed).display is True
        assert screen.query_one(SurfDevActivity).display is False
        assert "Mission Control" in _plain(screen.query_one("#title-bar"))
```

- [ ] Run it and confirm the expected failure: `ModuleNotFoundError: No module named 'maxpane_dashboard.screens.surf'` (or `ImportError` on `SurfScreen`).

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -v
```

- [ ] Minimal implementation. Create `maxpane_dashboard/screens/surf.py`:

```python
"""SurfScreen — surfsurf.eth Mission Control as a Textual Screen.

Layout (the house pattern; structurally the FWA screen with the hero split
into two side-by-side widgets)::

    #title-bar      SURF · IMD $x.xx · parity ±x.x% · feed #N (age)
    #hero-row       SurfHero (3fr)   | SurfSignals (2fr)
    #middle-row     SurfFeed (3fr)     | SurfMarket (2fr)
                    SurfDevActivity (3fr)
                      -- one or the other, toggled with `c`
    #separator
    #bottom-row     SurfNft (full width)
    StatusBar

Deliberate choices, in the FWA screen's terms (see screens/fwa.py, whose
docstring carries the full rationale):

1. **``c`` toggles the announce feed and the dev-activity table** in the
   middle-left slot. Both stay mounted and both are dispatched to on every
   refresh, so toggling is a visibility flip with no refetch and no blank
   first frame.
2. **Every widget update is individually guarded** — one widget raising must
   never cost the other five their refresh. A *manager* failure touches only
   the StatusBar and leaves the previous frame standing.
3. **Degradation reaches the title bar** (``· degraded: …``), because the
   shared StatusBar API has no ``set_degraded()``.

The screen is clock-free: every time-derived string (``feed_last_post_age_s``,
per-signal ages) arrives pre-computed in the payload. Nothing here consults
the wall clock, so any captured instant replays forever in tests.

Written against the frozen ``SURF_KEYS`` contract, not against
``SurfManager``'s internals — any object with an awaitable
``fetch_and_compute()`` returning that dict drives it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard import __version__
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.surf_manager import SurfManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "SURF · Mission Control · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: Measured in Task WP5.5 (provisional: the FWA number until then).
SURF_FULL_LAYOUT_COLUMNS = 143


class SurfScreen(RefreshGuard, Screen):
    """surfsurf.eth Mission Control dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Feed/Activity", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "surf-refresh"

    # Structural fallback only. WP6 restates these in themes/minimal.tcss
    # (one owner) the way the FWA block does; app-stylesheet rules then beat
    # DEFAULT_CSS. They live here so the screen is reviewable and correctly
    # proportioned on its own, under any theme that has no surf block.
    #
    # #hero-row is height 10: SurfSignals renders six detector rows plus a
    # title inside a border. Any theme rule that adds vertical padding here
    # drops the sixth row — the BURN detector — which is exactly the FWA
    # coverage-badge clipping bug. The compositor test pins all six rows.
    DEFAULT_CSS = """
    SurfScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    SurfScreen #hero-row {
        height: 10;
        margin: 1 0 0 0;
    }
    SurfScreen SurfHero {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfSignals {
        width: 2fr;
        padding: 0 1;
    }
    SurfScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    SurfScreen SurfFeed {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfDevActivity {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfMarket {
        width: 2fr;
        padding: 0 1;
    }
    SurfScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    SurfScreen #bottom-row {
        height: 1fr;
        margin: 0 0 1 0;
    }
    SurfScreen SurfNft {
        width: 1fr;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "SurfManager",
        poll_interval: int = 30,
        name: str = "surf",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Which widget owns the middle-left slot: "feed" or "activity".
        self._active_view: str = "feed"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield SurfHero()
            yield SurfSignals()

        with Horizontal(id="middle-row"):
            # Two views of one slot, toggled with ``c``. The activity table
            # is created hidden rather than on demand so it keeps receiving
            # every refresh and is already populated when toggled to.
            yield SurfFeed()
            activity = SurfDevActivity()
            activity.display = False
            yield activity
            yield SurfMarket()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield SurfNft()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("surf")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    # ------------------------------------------------------------------
    # Refresh flow (Task WP5.3 fills this in)
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        await self._data_manager.fetch_and_compute()
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -v
```

Expected: 3 passed (`test_surf_keys_covers_the_local_signature_map`, `test_bindings_are_refresh_and_the_view_toggle`, `test_screen_mounts_all_six_widgets`).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py && git commit -m "feat(surf): screen skeleton with the six-widget slot grid"
```

---

### Task WP5.2: Title line and format helpers (pure functions)

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py`
- Test: `tests/screens/test_surf_screen.py` (append)

**Interfaces:**
- Consumes: payload keys `imd_price_usd`, `parity_pct`, `feed_nonce`, `feed_last_post_age_s`, `lp_owner_ok`, `degraded`; `maxpane_dashboard.__version__`.
- Produces: `surf._title_line(data: dict) -> str`, `surf._fmt_age(value) -> str`, `surf._fmt_usd(value) -> str`, `surf._fmt_signed_pct(value) -> str`, `surf._fmt_int(value) -> str`, `surf._fmt_degraded(sources) -> str`, `surf._num(value, default=0.0) -> float` — all import-safe without an app running (WP6's title assertions may reuse them).

**Steps:**

- [ ] Write the failing tests (append to `tests/screens/test_surf_screen.py`). These are synchronous unit tests — the title line is a pure function, so the degradation matrix is tested here cheaply and the composited tests stay few:

```python
# -- title line (pure) ---------------------------------------------------

from maxpane_dashboard.screens import surf as surf_mod


def test_title_line_composes_the_mandated_format():
    line = surf_mod._title_line(_frozen_payload())
    # PRD §4: SURF · IMD $x.xx · parity ±x.x% · feed #N (age) + flags + version
    assert line.startswith("SURF · IMD $0.71 · parity -2.7% · feed #14 (23h)")
    assert line.endswith(f"v{__version__}")
    assert "degraded" not in line          # nothing degraded in the sample


def test_title_line_all_none_shows_emdashes_never_zeros():
    line = surf_mod._title_line(_all_none_payload())
    assert "IMD —" in line
    assert "parity —" in line
    assert "feed #— (—)" in line
    assert "$0.00" not in line and "0.0%" not in line   # None is never 0-coerced


def test_title_line_renders_degraded_and_lp_owner_warning():
    line = surf_mod._title_line(
        _frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    assert "· degraded: logs, market" in line
    assert "⚠ LP owner changed" in line    # position #1167726 left frenpet.eth


def test_fmt_age_tiers():
    assert surf_mod._fmt_age(None) == "—"
    assert surf_mod._fmt_age(42.0) == "42s"
    assert surf_mod._fmt_age(84_769.0) == "23h"     # the sample's real age
    assert surf_mod._fmt_age(5_400.0) == "90m"      # 90 min is the m/h boundary
    assert surf_mod._fmt_age(3 * 86_400.0) == "3d"  # 36 h is the h/d boundary
    assert surf_mod._fmt_age(-5.0) == "—"           # a negative age is nonsense
```

- [ ] Run and confirm the expected failure: `AttributeError: module 'maxpane_dashboard.screens.surf' has no attribute '_title_line'`.

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k title_line -v
```

- [ ] Minimal implementation — add to `screens/surf.py` below the constants (mirrors `screens/fwa.py`'s helper block; `_num`, `_fmt_int`, `_fmt_degraded` are the FWA implementations with the surf key name):

```python
# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` — never raise."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _fmt_usd(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"${out:,.2f}"


def _fmt_signed_pct(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"{out:+.1f}%"


def _fmt_age(value) -> str:
    """``42s`` / ``17m`` / ``23h`` / ``3d`` — or an em-dash for ``None``.

    90 is the seconds/minutes boundary and 90 min the minutes/hours boundary
    (``5400.0`` renders ``90m``); 36 h is the hours/days boundary — the same
    tiers the sparkline axis uses.
    """
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if seconds != seconds or seconds < 0:
        return _EMDASH
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds <= 90 * 60:
        return f"{int(seconds // 60)}m"
    if seconds < 36 * 3600:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _fmt_degraded(sources) -> str:
    """``· degraded: logs, market`` — or an empty string when all is well."""
    if not sources:
        return ""
    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        return ""
    if not names:
        return ""
    return " · degraded: " + ", ".join(names)


def _title_line(data: dict) -> str:
    """Compose the meta row (PRD §4).

    Ordered by what must survive a narrow terminal: warnings before the
    version tail, because ``#title-bar`` is one row high and the tail is what
    gets clipped. Parity renders with the em-dash fallback rather than a
    zero: a dead market source must never read as perfect parity.
    """
    feed_age = _fmt_age(data.get("feed_last_post_age_s"))
    line = (
        f"SURF · IMD {_fmt_usd(data.get('imd_price_usd'))} · "
        f"parity {_fmt_signed_pct(data.get('parity_pct'))} · "
        f"feed #{_fmt_int(data.get('feed_nonce'))} ({feed_age})"
    )

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    line += _fmt_degraded(data.get("degraded"))
    # Plain, unmarked version tail: the StatusBar already carries the dim
    # version, and markup here would only complicate every assertion on the
    # end of this string.
    line += f" · v{__version__}"
    return line
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "title_line or fmt_age" -v
```

Expected: 4 passed.

- [ ] Prove the em-dash test bites: temporarily change `_fmt_signed_pct` to return `f"{_num(value):+.1f}%"` (the 0-coercion bug) — `test_title_line_all_none_shows_emdashes_never_zeros` must go red on `"0.0%" not in line` (it renders `+0.0%`; the assertion catches the `0.0%` substring). Restore.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py && git commit -m "feat(surf): title line with parity, feed age and degraded flags"
```

---

### Task WP5.3: `_do_refresh` — dispatch, manager failure, all-None payload

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py`
- Test: `tests/screens/test_surf_screen.py` (append)

**Interfaces:**
- Consumes: `SurfManager.fetch_and_compute() -> dict` (awaitable; **never raises** — WP4 guarantees it returns the full `SURF_KEYS` key set with `None` values and a populated `degraded` list on total failure), `SurfManager._error_count` (optional attr, default 0), `StatusBar.update_data(last_updated_seconds_ago=, error_count=, poll_interval=)`, the six WP3 `update_data` signatures from the header table.
- Produces: `SurfScreen._do_refresh()` — per-widget guarded dispatch of exactly the header-table kwargs; a manager exception (belt-and-braces path, see below) touches only the StatusBar (`MANAGER_FAILURE_SECONDS = 999`).

**The specified outage path is the all-`None` payload, not an exception.** WP4's `surf_manager.py` docstring guarantees `fetch_and_compute` returns **exactly** `SURF_KEYS` "always, under every failure combination, and without ever letting an exception escape", and pins it with `test_no_exception_escapes_when_every_call_raises`. So `test_screen_survives_all_none_payload` — not `test_screen_survives_manager_exception` — is the test that models a real RPC outage, and it is the one to trust when the two disagree about what a user sees.

The `try`/`except` around the fetch and the `_FakeManager(raises=True)` double are kept anyway, deliberately, as **belt and braces**: they cover a manager that is mis-wired at construction, a future manager edit that breaks WP4's guarantee, and any `AttributeError` from an object that is not a manager at all. They must never become the *documented* outage contract — `MANAGER_FAILURE_SECONDS = 999` is a programming-error indicator, and a plan or review that reads it as "this is what an outage looks like" has the contract backwards.

**Steps:**

- [ ] Write the failing tests (append):

```python
# -- refresh dispatch ----------------------------------------------------


def _record_dispatches(screen) -> dict[str, list[dict]]:
    """Wrap every widget's ``update_data`` so we can see what it was handed."""
    calls: dict[str, list[dict]] = {name: [] for name in _WIDGET_CLASSES}

    def _wrap(name: str, original):
        def recorder(**kwargs):
            calls[name].append(kwargs)
            return original(**kwargs)

        return recorder

    for name, cls in _WIDGET_CLASSES.items():
        widget = screen.query_one(cls)
        widget.update_data = _wrap(name, widget.update_data)

    return calls


async def test_screen_dispatches_every_data_key():
    """Every ``SURF_KEYS`` group reaches the widget that owns it."""
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1

        dispatched: set[str] = set()
        for name, signature in SURF_WIDGET_SIGNATURES.items():
            assert calls[name], f"{name}.update_data was never called"
            kwargs = calls[name][-1]
            assert set(kwargs) == set(signature), (
                f"{name} got {sorted(set(kwargs) ^ set(signature))} "
                "off-contract"
            )
            dispatched |= set(kwargs)

        # Nothing in the contract goes unrendered: it is either a widget
        # kwarg or a meta key the screen itself consumes.
        unconsumed = set(SURF_KEYS) - dispatched - META_KEYS
        assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"


async def test_refresh_renders_title_and_all_panels():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert "SURF · IMD $0.71 · parity -2.7% · feed #14 (23h)" in title

        text = _screen_text(app)
        # Panel titles (the WP3 widget-interface strings).
        assert "SIGNALS" in text
        assert "ANNOUNCE FEED" in text
        assert "MARKET" in text
        assert "IDMD NFT" in text
        # The hook vocabulary the manager actually emits reaches the hero in
        # words. ``NOT_LIVE`` (underscore) is WP3's *fallback* headline for an
        # unrecognised value, so asserting its absence is the tripwire against
        # this fixture drifting back to the lowercase-snake spelling — both
        # forms are 8 characters, so both survive the hero box's
        # ``text-overflow: ellipsis`` here and the two stay separable.
        assert "NOT LIVE" in text
        assert "NOT_LIVE" not in text
        # The observed burn reached the hero, and PRD §1's all-time ledger is
        # nowhere on screen — the manager cannot produce it. Only the prefix is
        # asserted: at 150 columns a hero box has 14 content columns
        # (150·3/5 = 90, −2 screen padding = 88, ÷4 boxes = 22, −2 margin
        # −2 border −4 padding), so WP3.2's full ``burned 15,745 observed``
        # copy is ellipsised. The exact string is WP3's to pin at box width.
        assert "burned 15,7" in text
        assert "58,848" not in text
        # The clipping trap: all six detector rows reach the compositor.
        # SurfSignals is six rows + title inside #hero-row's fixed height —
        # if a theme or CSS change costs it a row, BURN (the last) goes first.
        for label in ("NEW POST", "LP MIGRATION", "GATE OPEN",
                      "NEW DEPLOY", "BRIDGE STAGE", "BURN"):
            assert label in text, f"detector row {label!r} clipped or missing"
        # The floor is explicitly unavailable, never faked (PRD §4).
        assert "no keyless source" in text


async def test_screen_survives_manager_exception():
    """Belt and braces: the screen stands; only the StatusBar is marked.

    This is **not** the specified outage path — WP4's manager never raises,
    it returns all-``None`` (see ``test_screen_survives_all_none_payload``,
    which is the real-outage test).  A raising manager models a mis-wired or
    non-manager object, i.e. a programming error, and this test exists so
    that error degrades instead of killing the app.
    """
    manager = _FakeManager(raises=True)
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        status = screen.query_one(StatusBar).query_one("#status-left")
        rendered = _plain(status)
        assert "updated 999s ago" in rendered
        assert "3 errors" in rendered   # manager's _error_count is surfaced

        # The title bar was not half-overwritten with a broken frame.
        assert "Mission Control" in _plain(screen.query_one("#title-bar"))
        # Every widget is still mounted and rendering.
        text = _screen_text(app)
        assert "SIGNALS" in text
        assert "IDMD NFT" in text


async def test_screen_survives_all_none_payload():
    """A full outage renders explicit unavailable states, never zeros."""
    manager = _FakeManager(payload=_all_none_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert "SURF · IMD — · parity — · feed #— (—)" in title
        text = _screen_text(app)
        assert "$0.00" not in text     # a None price is never a zero price
        assert "no keyless source" in text


async def test_degraded_sources_reach_the_title_bar():
    manager = _FakeManager(
        payload=_frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        text = _screen_text(app)
        assert "degraded: logs, market" in text
        assert "LP owner changed" in text
```

- [ ] Run and confirm the expected failure: `test_screen_dispatches_every_data_key` fails with `SurfHero.update_data was never called` (the Task WP5.1 stub `_do_refresh` fetches and discards).

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "dispatches or renders_title or survives or degraded_sources" -v
```

- [ ] Minimal implementation — replace the stub `_do_refresh` in `screens/surf.py`:

```python
    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("surf refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=MANAGER_FAILURE_SECONDS,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        if not isinstance(data, dict):  # defensive: a broken manager contract
            logger.debug("surf refresh returned %r, not a dict", type(data))
            return

        # Title bar
        try:
            self.query_one("#title-bar", Static).update(_title_line(data))
        except Exception as exc:
            logger.debug("Failed to update title bar: %s", exc)

        # Hero (hero-row left)
        try:
            self.query_one(SurfHero).update_data(
                hook_status=data.get("hook_status"),
                lp_liquidity=data.get("lp_liquidity"),
                lp_imd=data.get("lp_imd"),
                lp_weth=data.get("lp_weth"),
                lp_owner_ok=data.get("lp_owner_ok"),
                gate_open=data.get("gate_open"),
                identities_written=data.get("identities_written"),
                imd_supply=data.get("imd_supply"),
                imd_burned_cum=data.get("imd_burned_cum"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfHero: %s", exc)

        # Signals (hero-row right) — the six detectors
        try:
            self.query_one(SurfSignals).update_data(
                sig_post_state=data.get("sig_post_state"),
                sig_post_detail=data.get("sig_post_detail"),
                sig_post_age_s=data.get("sig_post_age_s"),
                sig_lp_state=data.get("sig_lp_state"),
                sig_lp_detail=data.get("sig_lp_detail"),
                sig_lp_age_s=data.get("sig_lp_age_s"),
                sig_gate_state=data.get("sig_gate_state"),
                sig_gate_detail=data.get("sig_gate_detail"),
                sig_gate_age_s=data.get("sig_gate_age_s"),
                sig_deploy_state=data.get("sig_deploy_state"),
                sig_deploy_detail=data.get("sig_deploy_detail"),
                sig_deploy_age_s=data.get("sig_deploy_age_s"),
                sig_bridge_state=data.get("sig_bridge_state"),
                sig_bridge_detail=data.get("sig_bridge_detail"),
                sig_bridge_age_s=data.get("sig_bridge_age_s"),
                sig_burn_state=data.get("sig_burn_state"),
                sig_burn_detail=data.get("sig_burn_detail"),
                sig_burn_age_s=data.get("sig_burn_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfSignals: %s", exc)

        # Announce feed (middle-row left, view A)
        try:
            self.query_one(SurfFeed).update_data(
                feed_items=data.get("feed_items"),
                feed_nonce=data.get("feed_nonce"),
                feed_last_post_age_s=data.get("feed_last_post_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfFeed: %s", exc)

        # Dev activity (middle-row left, view B — hidden, still updated)
        try:
            self.query_one(SurfDevActivity).update_data(
                dev_activity=data.get("dev_activity"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfDevActivity: %s", exc)

        # Market (middle-row right)
        try:
            self.query_one(SurfMarket).update_data(
                imd_price_usd=data.get("imd_price_usd"),
                imd_change_24h_pct=data.get("imd_change_24h_pct"),
                imd_vol_24h_usd=data.get("imd_vol_24h_usd"),
                pool_liquidity_usd=data.get("pool_liquidity_usd"),
                fp_price_usd=data.get("fp_price_usd"),
                parity_pct=data.get("parity_pct"),
                supply_series=data.get("supply_series"),
                price_series=data.get("price_series"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfMarket: %s", exc)

        # NFT (bottom row)
        try:
            self.query_one(SurfNft).update_data(
                nft_holders=data.get("nft_holders"),
                nft_transfers_24h=data.get("nft_transfers_24h"),
                nft_dev_holdings=data.get("nft_dev_holdings"),
                nft_written=data.get("nft_written"),
                nft_last_sales=data.get("nft_last_sales"),
                nft_floor=data.get("nft_floor"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfNft: %s", exc)

        # Status bar. A refresh that reaches this line just fetched, so the
        # staleness is honestly 0 without consulting any clock; ``as_of`` is
        # the *payload's* fetch instant and stays inside the widgets' strings.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=0.0,
                error_count=int(_num(getattr(self._data_manager, "_error_count", 0))),
                poll_interval=self._poll_interval,
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -v
```

Expected: all tests so far pass. If a panel-title assertion fails, the string mismatches WP3's actual copy — **report it to WP3, the widget owner, and do not restyle their widget** (house rule: report defects in other agents' files); if WP3's copy is the better one, update the assertion here and record the agreed string in the WP3↔WP5 interface table in this document's header.

- [ ] Prove the mechanical test bites: delete the `sig_burn_age_s=` line from the `SurfSignals` dispatch — `test_screen_dispatches_every_data_key` must go red with `SurfSignals got ['sig_burn_age_s'] off-contract`. Restore. Then delete the whole `SurfNft` dispatch block — the same test must go red with `contract keys reach no widget: ['nft_dev_holdings', …]`. Restore.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py && git commit -m "feat(surf): dispatch the SURF_KEYS payload to widgets with per-widget guards"
```

---

### Task WP5.4: The `c` swap — announce feed ↔ dev activity

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py`
- Test: `tests/screens/test_surf_screen.py` (append)

**Interfaces:**
- Consumes: `StatusBar.set_active_view(view: str)`; WP3 panel titles `ANNOUNCE FEED` / `DEV ACTIVITY`; WP3's `widgets/surf/_fmt.long_addr` rendering (`0x` + first 8 + `…` + last 6) and `activity._row_markup`'s drop rule for the (transfer, zero value, unknown) triple — both asserted through the compositor, never re-implemented here.
- Produces: `SurfScreen.action_toggle_view()`; `SurfScreen._active_view` ∈ `{"feed", "activity"}` (initial `"feed"`).

**Steps:**

- [ ] Write the failing tests (append):

```python
# -- the feed / activity toggle -----------------------------------------


async def test_c_swaps_the_feed_and_the_activity_table():
    """One slot, two views, mutually exclusive at every step."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "ANNOUNCE FEED" in text and "DEV ACTIVITY" not in text
        assert screen._active_view == "feed"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "DEV ACTIVITY" in text and "ANNOUNCE FEED" not in text
        assert screen._active_view == "activity"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "ANNOUNCE FEED" in text and "DEV ACTIVITY" not in text
        assert screen._active_view == "feed"


async def test_the_market_and_nft_panels_are_unaffected_by_the_toggle():
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        for _ in range(3):
            text = _screen_text(app)
            assert "MARKET" in text
            assert "IDMD NFT" in text
            await pilot.press("c")
            await pilot.pause()


async def test_the_hidden_view_still_receives_updates():
    """Both widgets stay mounted and dispatched to, whichever is showing.

    Creating the activity table on demand would leave it empty for a beat
    after the first toggle, which reads as a bug. This asserts it has
    content *before* it is ever shown.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

        assert calls["SurfDevActivity"], "the hidden activity table was never updated"
        assert calls["SurfFeed"]

        # and it renders immediately on the very first toggle
        await pilot.press("c")
        await pilot.pause()
        assert "DEV ACTIVITY" in _screen_text(app)


async def test_the_activity_view_defends_against_address_poisoning():
    """The anti-poisoning form survives all the way to the compositor.

    Two live shapes from frenpet.eth's history are in the payload: an
    unlabelled but genuine LP-fee destination, and a 1-gwei lookalike that
    collides with a real fee recipient on first-6/last-4. WP3 renders unknown
    counterparties as ``0x`` + first 8 + ``…`` + last 6 and drops the
    (transfer, zero value, unknown) triple outright — this asserts both
    through the real screen rather than trusting the widget's own unit test,
    because a short-form *fixture* would make either defence a silent no-op.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("c")          # the activity table owns the slot
        await pilot.pause()

        text = _screen_text(app)
        assert "DEV ACTIVITY" in text
        # The genuine unknown renders in the wide, poisoning-resistant window…
        assert "0x61CC704c…73f14E" in text
        # …and never in the classic short form the lookalike collides with.
        assert "0x61CC…f14E" not in text
        # The dust row reaches no pixel at all — not the address, not the tail.
        assert "F3083828" not in text
        assert "f60Ee6" not in text


async def test_the_toggle_survives_a_missing_widget():
    """A toggle must never take the screen down (it runs outside the
    refresh path's per-widget try/except)."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        screen.query_one(SurfFeed).remove()
        await pilot.pause()

        screen.action_toggle_view()  # must not raise
        await pilot.pause()

        assert screen._active_view == "activity"


async def test_the_status_bar_names_the_active_view():
    """Same affordance FWA, Talismans and TTT use, so `c` is discoverable."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        seen = []
        bar = screen.query_one(StatusBar)
        original = bar.set_active_view
        bar.set_active_view = lambda v: (seen.append(v), original(v))[1]

        screen.action_toggle_view()
        await pilot.pause()

        assert seen == ["activity"]


async def test_both_views_get_the_identical_slot():
    """The toggle must not resize the panel underneath it.

    Both views carry ``width: 3fr`` against SurfMarket's ``2fr``; give either
    a different width and the layout jumps on every ``c`` press. Measured
    under the real stylesheet rather than trusting the numbers to stay equal
    (and it keeps holding after WP6 restates the block in minimal.tcss).
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        feed_size = screen.query_one(SurfFeed).size

        await pilot.press("c")
        await pilot.pause()
        act_size = screen.query_one(SurfDevActivity).size

        assert (act_size.width, act_size.height) == (feed_size.width, feed_size.height), (
            f"activity occupies {act_size} where the feed occupied "
            f"{feed_size} — the panel resizes on every toggle"
        )
        assert act_size.height > 1, "the activity table collapsed instead of filling the row"
```

- [ ] Run and confirm the expected failure: `test_c_swaps_the_feed_and_the_activity_table` fails — pressing `c` raises no action (`action_toggle_view` missing), `_active_view` stays `"feed"` and `DEV ACTIVITY` never appears.

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "toggle or swaps or identical_slot or hidden_view or unaffected or poisoning" -v
```

- [ ] Minimal implementation — add to `SurfScreen` (between `compose` and the lifecycle methods):

```python
    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def action_toggle_view(self) -> None:
        """Swap the announce feed and the dev-activity table in one slot.

        Both widgets stay mounted and both keep being updated on every
        refresh, so toggling is a pure visibility flip — no refetch, no
        repopulate, no empty frame.
        """
        self._active_view = "activity" if self._active_view == "feed" else "feed"
        showing_feed = self._active_view == "feed"
        try:
            self.query_one(SurfFeed).display = showing_feed
            self.query_one(SurfDevActivity).display = not showing_feed
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("surf view toggle failed: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -v
```

- [ ] Prove the guard bites (concurrency/teardown-shaped code): remove the inner `try/except` around the two `display` assignments — `test_the_toggle_survives_a_missing_widget` must go red with `NoMatches`. Restore.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py && git commit -m "feat(surf): c swaps the announce feed and dev activity in one slot"
```

---

### Task WP5.5: Measure and pin the full-layout width; narrow tier advertises

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` (pin `SURF_FULL_LAYOUT_COLUMNS`)
- Test: `tests/screens/test_surf_screen.py` (append)

**Interfaces:**
- Consumes: the house `‹ widen` marker convention (every WP3 widget advertises dropped columns in its title); `maxpane_dashboard.__main__.FULL_LAYOUT_COLUMNS` (read-only — owned by WP6).
- Produces: `screens/surf.py::SURF_FULL_LAYOUT_COLUMNS: int` — the measured minimum width at which the composited surf screen shows zero `‹ widen` markers in **both** `c` views. WP6 consumes this constant for the app-level width documentation.

**Steps:**

- [ ] Write the failing tests (append). They are written against the constant, so pinning a wrong number turns them red rather than silently documenting fiction — the FWA pattern from `tests/test_cli_font_size.py::test_the_documented_width_matches_the_layout`:

```python
# -- the pinned full-layout width ---------------------------------------

from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS


async def _widen_markers(width: int, view: str = "feed") -> int:
    """Composited ``‹ widen`` count at *width*, in the requested ``c`` view."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view == "activity":
            await pilot.press("c")
            await pilot.pause()
        return _screen_text(app).count("‹ widen")


async def test_the_pinned_width_clears_every_widen_marker():
    """At ``SURF_FULL_LAYOUT_COLUMNS``, both views are marker-free."""
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, "feed") == 0
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, "activity") == 0


async def test_the_pinned_width_is_tight_not_padded():
    """Four columns narrower, at least one widget advertises the loss."""
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 4, "feed") > 0 or (
        await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 4, "activity") > 0
    ), "the documented width is higher than it needs to be"


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    """Well below the threshold every drop is announced, never silent."""
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 20, "feed") > 0


def test_surf_fits_inside_the_documented_app_width():
    """WP6 coordination tripwire — mechanical, not a comment.

    ``__main__.FULL_LAYOUT_COLUMNS`` (owned by WP6/one owner) documents the
    width the *widest* dashboard needs. If surf measures wider than it, the
    app-level constant and its help text become lies; this failure message is
    the hand-off.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"surf needs {SURF_FULL_LAYOUT_COLUMNS} columns but "
        f"__main__.FULL_LAYOUT_COLUMNS documents {FULL_LAYOUT_COLUMNS}. "
        "Do NOT edit __main__.py from WP5 — report to WP6, which owns it, "
        "and land this test together with WP6's raise."
    )
```

- [ ] Run and observe. Expected outcome with the provisional constant (143): `test_the_pinned_width_clears_every_widen_marker` **fails** if surf's real requirement differs from FWA's, or `test_the_pinned_width_is_tight_not_padded` fails if 143 is padded. Either failure is the measurement prompt; both passing at 143 first try would mean surf's requirement is exactly FWA's — verify with the sweep below anyway before trusting a coincidence.

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "pinned_width or narrow_tier or fits_inside" -v
```

- [ ] Measure. Run this sweep (from the repo root; throwaway — do not commit it):

```bash
cd /Library/Vibes/autopull && .venv/bin/python - <<'EOF'
import asyncio, importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "_surf_harness", Path("tests/screens/test_surf_screen.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

async def markers(width, view):
    screen = harness.SurfScreen(harness._FakeManager(), poll_interval=30, name="surf")
    app = harness._ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view == "activity":
            await pilot.press("c")
            await pilot.pause()
        return harness._screen_text(app).count("‹ widen")

for w in range(120, 201):
    n = asyncio.run(markers(w, "feed")) + asyncio.run(markers(w, "activity"))
    print(w, n)
    if n == 0:
        print("=> SURF_FULL_LAYOUT_COLUMNS =", w)
        break
EOF
```

- [ ] Pin the printed number: edit `SURF_FULL_LAYOUT_COLUMNS` in `screens/surf.py` to the measured value and replace the `provisional` comment with `#: Measured against composited output (both c views), not estimated — see tests.` If the number exceeds 143, `test_surf_fits_inside_the_documented_app_width` stays red **by design**: leave it red, record the number in the WP6 hand-off note, and let WP6's `__main__.py` change turn it green (do not touch `__main__.py` here).

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "pinned_width or narrow_tier or fits_inside" -v
```

Expected: 4 passed (or 3 passed + the documented WP6-blocked failure, called out in the final report).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py && git commit -m "feat(surf): pin the measured full-layout width in both c views"
```

---

### Task WP5.6: RefreshGuard integration — skip-not-queue, proven live

**Files:**
- Modify: none (behavior landed with WP5.1's class declaration)
- Test: `tests/screens/test_surf_screen.py` (append); run `tests/screens/test_refresh_guard.py` (read-only — its auto-discovery must pick SurfScreen up)

**Interfaces:**
- Consumes: `RefreshGuard.start_refresh()` / `_refresh_in_flight` / `_refresh_skipped`; `refresh_guard.PREFETCH_WORKER_NAME` (join-the-prefetch is inherited, and covered generically by `tests/screens/test_refresh_guard.py`).
- Produces: surf-specific proof that an overrunning refresh drops ticks instead of queueing or cancelling.

**Steps:**

- [ ] Write the failing-capable tests (append). Event-driven, zero sleeps except bare `sleep(0)` yields — the interleaving is chosen by the test, not the clock (the `test_refresh_guard.py` house style):

```python
# -- refresh guard: skip, never queue ------------------------------------


def test_surf_screen_opts_into_the_refresh_guard():
    """Structural: the mixin comes first and the worker name is surf's own.

    The generic suite (tests/screens/test_refresh_guard.py) auto-discovers
    every polling screen; this pins the two things it cannot: MRO order and
    the name.
    """
    mro = SurfScreen.__mro__
    from textual.screen import Screen as _Screen

    from maxpane_dashboard.screens.refresh_guard import RefreshGuard

    assert mro.index(RefreshGuard) < mro.index(_Screen)
    assert SurfScreen.REFRESH_WORKER_NAME == "surf-refresh"


class _BlockingManager:
    """Parks inside ``fetch_and_compute`` until the test releases it."""

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return _frozen_payload()

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


async def test_overrun_tick_is_skipped_never_queued_or_cancelled():
    """A tick landing mid-refresh is dropped; the refresh completes once."""
    manager = _BlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        # on_screen_resume started the initial refresh; wait until it is
        # provably parked inside fetch_and_compute.
        await asyncio.wait_for(manager.entered.wait(), timeout=2)

        skipped_before = screen._refresh_skipped
        assert screen.start_refresh() is None          # the overrunning tick
        assert screen.start_refresh() is None          # and another
        assert screen._refresh_skipped == skipped_before + 2
        assert manager.calls == 1                      # nothing queued

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()

        assert manager.calls == 1                      # nothing ran after
        assert screen._refresh_in_flight is False      # flag lowered
        # ...and the completed refresh actually rendered.
        assert "feed #14" in _plain(screen.query_one("#title-bar"))
```

- [ ] Run and confirm both pass immediately (the guard came free with the WP5.1 class declaration — these tests exist to keep it that way):

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "refresh_guard or overrun" -v
```

- [ ] Prove the overrun test bites (mandatory for concurrency-shaped code). In `maxpane_dashboard/screens/refresh_guard.py`, comment out the `if self._refresh_in_flight:` early-return block in `start_refresh` — `test_overrun_tick_is_skipped_never_queued_or_cancelled` must go red (`start_refresh()` returns a Worker, `manager.calls` climbs). **Restore the file exactly** (this WP does not own `refresh_guard.py`; the mutation is a local, uncommitted proof — `git diff` must be empty for that file afterwards).

- [ ] Run the generic guard suite and the whole surf file; confirm the auto-discovery tests (`test_every_polling_screen_uses_the_guard`, `test_no_screen_schedules_a_bare_refresh_worker`) now cover SurfScreen and stay green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_refresh_guard.py tests/screens/test_surf_screen.py -v
```

- [ ] Full-suite sanity (nothing outside surf may move — registration is WP6's):

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/ -q
```

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add tests/screens/test_surf_screen.py && git commit -m "test(surf): prove skip-not-queue refresh scheduling on the surf screen"
```

---

## WP6 hand-off summary (do not act on these from WP5)

1. Add the surf structural block to `themes/minimal.tcss` (copy `SurfScreen.DEFAULT_CSS`, FWA-block style; **no vertical padding on `#hero-row`** — the six-detector compositor test is the tripwire).
2. If `SURF_FULL_LAYOUT_COLUMNS` measured > 143, raise `__main__.FULL_LAYOUT_COLUMNS` (and its help text) — `test_surf_fits_inside_the_documented_app_width` is red until then, by design.
3. Registration (`GAMES` key 7, `_GAME_CYCLE`, `--game` choices, CLAUDE.md table, README) reuses `tests/screens/test_surf_screen.py::_FakeManager` for its screen-install test if needed — it is import-safe.
4. **Cross-WP items routed here as *report, do not fix* are now applied — WP4 open issue 6's first bullet is closed.** WP5's screen fixture no longer carries `imd_burned_cum: 58_848.0`; it carries the observed `15_745.0` WP4.5 specifies, and `hook_status` is now the manager's `"NOT LIVE"` (imported as `HOOK_NOT_LIVE`) rather than the lowercase-snake spelling WP3's hero fixture comment warns about. WP4 and WP3 own those notes and cannot be edited from here, so the close-out is recorded in this hand-off: whoever reconciles the open-issue lists can strike that bullet against this file.

5. **WP6's `BoomManager` acceptance test models a programming error, not the specified outage path.** The real `SurfManager.fetch_and_compute` never raises — WP4 guarantees the full `SURF_KEYS` dict with `None` values and a populated `degraded` list under every failure combination (`test_no_exception_escapes_when_every_call_raises`). A raising manager is therefore a shape the app only sees if the manager is mis-wired at construction or a future edit breaks WP4's guarantee. Keep the test — it proves that error degrades rather than killing the app — but label it as such, and use an all-`None` payload (not `BoomManager`) for WP6's "launches and degrades cleanly offline" acceptance criterion, since that is what an actual offline launch produces.
