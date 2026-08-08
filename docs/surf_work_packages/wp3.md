# WP3 — Surf Widgets (`widgets/surf/`, six widgets + tests)

**Goal:** Build the six render-only widgets of the surf dashboard (`SurfHero`, `SurfSignals`,
`SurfFeed`, `SurfDevActivity`, `SurfMarket`, `SurfNft`) with headless Textual tests that assert
composited output.

**Dependencies:** WP0 only (`data/surf_models.py` must export `SURF_KEYS`; the contract-conformance
test in WP3.8 imports it — every other task is WP0-independent because widgets consume primitives).

**Owner note:** This WP owns `maxpane_dashboard/widgets/surf/**` and
`tests/widgets/test_surf_widgets_a.py`, `tests/widgets/test_surf_widgets_b.py`,
`tests/widgets/test_surf_widget_contract.py` — nothing else. Do not touch `templates/`,
`screens/`, `data/`, `analytics/`, or any shared file. Before writing code, read
`maxpane_dashboard/templates/signals_template.py`, `templates/activity_feed_template.py`,
`templates/hero_metrics_template.py`, `templates/sparkline_template.py` **and** their FWA
counterparts in `maxpane_dashboard/widgets/fwa/` — the templates are the copy-source and the FWA
widgets carry post-template hardening (`safe_markup`, `visible_len`, `sparkline_common` imports,
the `‹ widen` clip announcement) that the templates may lack. If you find template-vs-widget drift,
**report it in your final summary; do not fix templates** (one owner per shared file).

Two drift facts already measured, so you do not have to re-derive them (still: report, do not fix):

- `templates/signals_template.py` is the **only** row-rendering template with no `safe_markup`
  import (`hero_metrics_template.py`, `activity_feed_template.py`, `leaderboard_template.py` and
  `two_column_table_template.py` all have it). WP3.3 must add escaping to the surf signals panel
  deliberately — copying the template verbatim ships the crash `markup_safety.py` documents.
- No template carries the `‹ widen` clip-announcement machinery (`grep -n widen templates/*.py`
  is empty); it exists only in `widgets/fwa/fwa_signals.py` and `fwa_activity_feed.py`. Copy it
  from there for WP3.3 and WP3.5. `sparkline_template.py` *does* already import
  `sparkline_common`, so WP3.4 inherits the fixed version either way.

House rules that bind every task below (CLAUDE.md Conventions):

- Widgets receive `str`/`int`/`float`/`bool`/`dict`/`list[dict]` only; they import **nothing**
  from `maxpane_dashboard.data` or `maxpane_dashboard.analytics` (WP3.8 pins this with an AST test).
- Every third-party string → `widgets/markup_safety.safe_markup`. Third-party here means: announce
  message text, reply text, counterparty addresses/labels, signal detail strings, ENS names.
  Escape **after** any slicing/padding/uppercasing, never before.
- `None` renders as the widget's explicit unavailable state, never `0`, never blank, never a crash.
- Sparklines import `widgets/sparkline_common` — no copied helpers.
- Sign/state is always carried in **text** (glyph + word), colour is redundant
  (colours are `$success`/`$warning`/`$error`/`dim`, never CSS `green`/`red`).
- Tests assert composited output via `app.screen._compositor.render_strips()` (the
  `_screen_text` helper below, same as `tests/widgets/test_fwa_widgets_a.py::_screen_text`).
- No network anywhere: these are pure-render tests; there is no transport to inject because the
  widgets have no I/O — the AST import test is the structural proof.

All payload numbers in the tests below are **derived from real 2026-08-08 chain state** — the
committed captures in `tests/fixtures/surf/captures/`, or, for the two realized Seaport prices,
WP1's decode of the single purchase transaction (the captures carry no prices at all — see the
last row of the table). Nothing here is invented; the one deliberately hypothetical value, the
`nft_floor = 0.25` used to exercise the v2 escape hatch, is labelled as such at its use site.

| Value used in tests | Source |
|---|---|
| IMD price `0.7074`, 24h Δ `+30.89%`, vol `244178`, pool liq `548701.21`, sides `388421` IMD / `142.7067` WETH | `dexscreener_imd.json` (`priceUsd`, `priceChange.h24`, `volume.h24`, `liquidity.{usd,base,quote}`) |
| FP price `0.7274` → parity `-2.75%` | `dexscreener_fp.json` (`priceUsd`); `(0.7074/0.7274−1)·100 = −2.7495` |
| IMD supply `2376731.868679` | `imd_token.json` (`total_supply` = `2376731868679000000000000` / 1e18) |
| Observed burn `15745` — the 2026-08-05 event **alone**, deliberately *not* the ~58,849 all-time ledger (see the `imd_burned_cum` note in WP3.2) | `docs/surf_game_mechanics.md` §IMD, announce nonce 12 |
| NFT holders `667`, transfers `7411` total, ~`38`/day | `identity_counters.json`, `identity_token.json` |
| Post nonce 13 text (227 chars, ends `"as always 0 promises."`), ts `1786076831`, hash `0xe397869a…` | `announce_eth_txs.json` `raw_input` hex → UTF-8 |
| Post nonce 8 text (newlines `\n  `, `’`, `—`: `"…for the first few hours—so the risks\n  are clear—…"`), ts `1785284915` | `announce_eth_txs.json` |
| Pasta-sauce reply (`0x1c3A0Ad5…`, ts `1785795251`), begging reply (`0xA5B9737d…`, value 1e13 wei, ts `1785454967`) | `announce_eth_txs.json` |
| Poisoning spoof `0xF3083828702C1989710CECA517412071c2f60Ee6` vs real `0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6` | `ops_eth_txs.json` (live in frenpet.eth's history) |
| Homoglyph token symbol `" UЅDС "` | `ops_eth_token_transfers.json` |
| 08-07 staging: OFT mint `114366.899256` IMD to frenpet.eth ts `1786076495` (tx `0xc7acbcc0…`), LP add ts `1786076603` (tx `0x90a0f8e2…`) | `ops_eth_token_transfers.json` |
| Realized Seaport sales: token `#1751` @ `0.18` ETH and `#354` @ `0.1838989` ETH, both legs of tx `0x5b4d1b44…eadad2` ts `1786163591` | WP1 §"One real Seaport purchase" — decoded from that tx's `OrderFulfilled` logs; the two realized values sum to the tx `value` exactly. **Not** `identity_transfers_page1.json`: WP0.7's `test_no_idmd_transfer_row_carries_a_price` pins that no row of that capture carries a price, so any price attributed to one would be invented |

**Widget `update_data` kwargs are exactly the PRD §5 flat-dict keys** (plus `**_kwargs` so the
screen can splat the whole manager dict at every widget). Unavailability is encoded in the
contract itself: a `None` list means "source dead", an empty list means "genuinely nothing" —
no extra `*_available` keys are invented.

Run all commands from the repo root `/Library/Vibes/autopull`, branch `surf-dashboard`.

---

### Task WP3.1: Package scaffold + shared formatters (`_fmt.py`)

**Files:**
- Create: `maxpane_dashboard/widgets/surf/__init__.py` — **docstring only in this task**; the six
  widget-class re-exports are added in WP3.7, once every submodule it must import actually exists.
  The package root is the import surface WP5 uses (`from maxpane_dashboard.widgets.surf import
  SurfHero, …` in both `screens/surf.py` and its screen test), matching
  `widgets/ttt/__init__.py`, `widgets/talismans/__init__.py` and `screens/fwa.py:94`. WP3 owns this
  file, so the re-exports are WP3's job — do not leave WP5 importing submodule paths.
- Create: `maxpane_dashboard/widgets/surf/_fmt.py`
- Test: `tests/widgets/test_surf_widgets_a.py` (created here, extended by WP3.2–3.4)

**Interfaces:**
- Consumes: `maxpane_dashboard.widgets.markup_safety.safe_markup` (exists).
- Produces (imported by all six widgets):
  - `_fmt.as_float(value) -> float | None`
  - `_fmt.fmt_age(seconds) -> str` (`"45s"`, `"12m"`, `"2h"`, `"3d"`, `"--"` for `None`/negative)
  - `_fmt.fmt_price(value) -> str` (`"$0.7074"` for sub-dollar, `"$1,917.74"` above)
  - `_fmt.fmt_compact(value, unit="") -> str` (re-export of `sparkline_common.fmt_compact`)
  - `_fmt.fmt_liquidity(value) -> str` (`"2.60e+19"` for raw v3 liquidity, compact below 1e12)
  - `_fmt.long_addr(value) -> str` (`0x` + first 8 hex + `…` + last 6 — the anti-poisoning form)
  - `_fmt.hhmm(ts) -> str`, `_fmt.mmdd(ts) -> str` (localtime, `"??:??"`/`"??-??"` fallback)
  - `_fmt.DASH = "--"`, `_fmt.EMDASH = "—"`

- [ ] **Write the failing test.** Create `tests/widgets/test_surf_widgets_a.py`:

```python
"""Headless Textual tests for surf widgets group A (WP3).

Covers the shared formatters, ``SurfHero``, ``SurfSignals`` and ``SurfMarket``.
Group B (feed, dev activity, NFT) lives in ``test_surf_widgets_b.py``.

Every content assertion reads the *composited* screen via
``_compositor.render_strips()`` -- a string that never reaches a pixel must not
pass (house rule).  Zero network: these widgets have no I/O by construction;
``test_surf_widget_contract.py`` proves it structurally with an AST scan.

Payload values are derived from the committed captures under
``tests/fixtures/surf/captures/`` (see the table in docs/plans wp3), so the
representative payloads are the real 2026-08-08 chain state, not invented
numbers.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.surf import _fmt


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _none_payload(widget) -> dict:
    """All-``None`` payload built from the widget's own signature."""
    return {
        name: None
        for name, param in inspect.signature(widget.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }


# ---------------------------------------------------------------------
# _fmt -- pure formatters
# ---------------------------------------------------------------------


def test_fmt_age_buckets():
    assert _fmt.fmt_age(45) == "45s"
    assert _fmt.fmt_age(720) == "12m"
    assert _fmt.fmt_age(7200) == "2h"
    assert _fmt.fmt_age(3 * 86400) == "3d"
    assert _fmt.fmt_age(0) == "0s"


def test_fmt_age_none_and_negative_are_dashes_never_zero():
    """A missing age is unknown, not ``0s`` -- ``None`` never 0-coerces."""
    assert _fmt.fmt_age(None) == "--"
    assert _fmt.fmt_age(-5) == "--"
    assert _fmt.fmt_age("garbage") == "--"
    assert _fmt.fmt_age(float("nan")) == "--"


def test_fmt_price_precision():
    # 0.7074 is the live IMD price in dexscreener_imd.json -- four decimals,
    # not the FWA sub-cent five, and never scientific notation.
    assert _fmt.fmt_price(0.7074) == "$0.7074"
    assert _fmt.fmt_price(1917.74) == "$1,917.74"
    assert _fmt.fmt_price(0.0003686) == "$0.000369"
    assert _fmt.fmt_price(None) == "--"


def test_fmt_liquidity_handles_raw_v3_uint():
    # positions().liquidity is a raw uint128 ~1e19 -- compact K/M/B suffixes
    # are meaningless there, scientific is honest.
    assert _fmt.fmt_liquidity(26010397574917496158) == "2.60e+19"
    assert _fmt.fmt_liquidity(548701.21) == "548.7K"
    assert _fmt.fmt_liquidity(None) == "--"


def test_long_addr_distinguishes_the_live_spoof_pair():
    """0x+8+…+6 must tell the real fee recipient from its live poisoner.

    Both addresses are in frenpet.eth's history right now
    (ops_eth_txs.json): the spoof matches the real address's first 6 and
    last 4 -- the classic short-form collision -- but differs inside the
    first-8 and last-6 windows this format shows.
    """
    real = _fmt.long_addr("0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6")
    spoof = _fmt.long_addr("0xF3083828702C1989710CECA517412071c2f60Ee6")
    assert real == "0xF3084Bc7…D60eE6"
    assert spoof == "0xF3083828…f60Ee6"
    assert real != spoof
    assert _fmt.long_addr(None) == "--"
    assert _fmt.long_addr("") == "--"


def test_hhmm_mmdd_fallbacks():
    assert _fmt.hhmm(None) == "??:??"
    assert _fmt.hhmm("junk") == "??:??"
    assert _fmt.mmdd(None) == "??-??"
    # Real values are localtime-dependent; assert the shape only.
    assert len(_fmt.hhmm(1786076831)) == 5
    assert len(_fmt.mmdd(1786076831)) == 5
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf'` at collection.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/__init__.py` with the
  docstring **and nothing else for now** — the re-export block lands in WP3.7, because importing
  `.hero` here before `hero.py` exists would make every WP3.2–3.6 test collection fail:

```python
"""Widgets for the surf dashboard (surfsurf.eth mission control).

The six widget classes are re-exported from this module in WP3.7, once all
six submodules exist -- see ``widgets/ttt/__init__.py`` for the house shape.
Until then, import the submodule directly (``from .hero import SurfHero``).
"""
```

  Create `maxpane_dashboard/widgets/surf/_fmt.py`:

```python
"""Shared pure formatters for the surf widgets.

These live in one private module because ``fmt_age`` is needed by both the
signals panel (``FIRED 2h ago``) and the feed title (``last 2h ago``), and a
second copy is how the sparkline helpers drifted apart before MEDI-36.
Pure functions, no I/O, no Textual imports, nothing raises.
"""

from __future__ import annotations

import time

from maxpane_dashboard.widgets.sparkline_common import fmt_compact

__all__ = [
    "DASH",
    "EMDASH",
    "as_float",
    "fmt_age",
    "fmt_price",
    "fmt_compact",
    "fmt_liquidity",
    "long_addr",
    "hhmm",
    "mmdd",
]

DASH = "--"
EMDASH = "—"


def as_float(value):
    """Coerce to ``float`` or return ``None`` -- never raise, never 0-coerce."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return out


def fmt_age(seconds) -> str:
    """``45s`` / ``12m`` / ``2h`` / ``3d``; ``--`` for unknown or negative.

    A negative age would mean an event from the future -- that is a corrupt
    input, and rendering it as ``0s`` would claim "right now" about garbage.
    """
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 90:
        return f"{s:.0f}s"
    if s < 90 * 60:
        return f"{s / 60:.0f}m"
    if s < 36 * 3600:
        return f"{s / 3600:.0f}h"
    return f"{s / 86400:.0f}d"


def fmt_price(value) -> str:
    """USD price at IMD-scale precision (a ~$0.71 token, not a sub-cent one)."""
    v = as_float(value)
    if v is None:
        return DASH
    a = abs(v)
    if a >= 1:
        return f"${v:,.2f}"
    if a >= 0.01:
        return f"${v:.4f}"
    if a > 0:
        return f"${v:.6f}"
    return "$0.00"


def fmt_liquidity(value) -> str:
    """Raw v3 liquidity is a uint128 ~1e19; suffixes lie at that magnitude."""
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) >= 1e12:
        return f"{v:.2e}"
    return fmt_compact(v)


def long_addr(value) -> str:
    """``0x`` + first 8 hex + ``…`` + last 6 -- the anti-poisoning form.

    Live spoofs of both fee recipients exist in frenpet.eth's history today;
    they collide with the real addresses on first-6/last-4 (what ``0xAB..CD``
    shorteners show) but not on this window (PRD §4).
    """
    if not value:
        return DASH
    s = str(value).strip()
    if not s:
        return DASH
    if len(s) <= 17:
        return s
    return f"{s[:10]}…{s[-6:]}"


def hhmm(timestamp) -> str:
    """``HH:MM`` local time from unix seconds; ``??:??`` when unusable."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??:??"


def mmdd(timestamp) -> str:
    """``MM-DD`` local time from unix seconds; ``??-??`` when unusable."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??-??"
        t = time.localtime(ts)
        return f"{t.tm_mon:02d}-{t.tm_mday:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??-??"
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
- [ ] **Prove the age test bites** (decoder-shaped boundary logic): in `fmt_age`, temporarily change
  `if s is None or s < 0:` to `if s is None:` — `test_fmt_age_none_and_negative_are_dashes_never_zero`
  must go red (`-5` → `"-5s"`). Restore, re-run green.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/__init__.py maxpane_dashboard/widgets/surf/_fmt.py tests/widgets/test_surf_widgets_a.py && git commit -m "feat(surf): widgets package scaffold + shared pure formatters"`

---

### Task WP3.2: `SurfHero` — experiment status hero row

**Files:**
- Create: `maxpane_dashboard/widgets/surf/hero.py`
- Test: `tests/widgets/test_surf_widgets_a.py` (append)

**Interfaces:**
- Consumes: `_fmt` helpers, `safe_markup`.
- Produces:
  `SurfHero(Horizontal)` with
  `update_data(hook_status=None, lp_liquidity=None, lp_imd=None, lp_weth=None, lp_owner_ok=None, gate_open=None, identities_written=None, imd_supply=None, imd_burned_cum=None, **_kwargs) -> None`
  — kwargs are exactly the PRD §5 `hero` keys. Module constants `HOOK_NOT_LIVE = "NOT LIVE"`
  and `HOOK_LAUNCHED = "LAUNCHED"`.

  `hook_status` vocabulary is **the manager's**, and it is already frozen in two places
  upstream: PRD §4 ("v4 hook NOT LIVE / LAUNCHED") and WP0's `SURF_KEYS` comment
  (`str — "NOT LIVE" until an Initialize with hooks!=0`). WP4's
  `SurfManager._hook_status()` returns exactly `"LAUNCHED"` / `"NOT LIVE"` / `None`, so those
  two literals — **not** lowercase snake forms — are what the widget must branch on. Matching
  is done after whitespace-collapse + upper-case, so `"not live"` also lands on the dedicated
  state. Any other non-empty string renders escaped-uppercased verbatim (the widget must
  survive tomorrow's value); `None` → em-dash.

  > Getting this wrong is silent and expensive: a lowercase-snake branch set makes *every*
  > live payload fall through to the unknown-value arm, so day one renders `NOT LIVE` with
  > the subtitle `unrecognized status`, and launch day renders `LAUNCHED` in plain bold
  > instead of the `$success` styling PRD §4 asks for on the one event the dashboard exists
  > to catch. `test_hero_real_hook_vocabulary_never_hits_the_fallback` pins both values.

  `imd_burned_cum` is **burned since this install's first successful supply read** — not an
  all-time total. WP4.5 builds it as an accumulator over successive `totalSupply` readings
  (`SurfCache.record_supply` / `observed_burn_total`), and WP4's own open issue 4 states the
  limitation: the ~58,849 IMD of PRD §1 was burned across three events (05-16, 07-31, 08-05)
  that all predate any install, the Base burn receiver was never resolved from local data, and
  there is no keyless source for the historical figure. Two consequences bind this widget:

  1. **The label must say `observed`, never `cum`.** `burned 58,848 cum` next to a live supply
     is read as an all-time claim about the token, and the widget cannot produce that number
     honestly. Anything the widget renders here is scoped to what this install watched.
  2. **`0.0` is not `None` and neither is a number to print.** WP4 returns `None` until the
     first successful supply read (`observed_burn_total` → `None` while `last_supply is None`)
     and `0.0` afterwards while nothing has moved — so on a fresh install with a healthy RPC
     the widget *will* be handed `0.0` within one refresh. Rendering that as `burned 0` states
     that zero IMD has ever been burned, which is false. `0.0` gets its own phrasing —
     `no burn observed yet` — and only a positive value is formatted as a quantity.

  > This is why the fixture below carries `15745.0` (one observed event) and not the historical
  > `58848.0`: a test fixture that pins the all-time ledger silently blesses all-time copy.
  > PRD §4's hero wording ("supply + cumulative burned") is honoured in substance — it is
  > cumulative over the observation window — but the *label* diverges from the PRD's phrasing
  > on purpose. Flag it to the plan owner as a PRD copy amendment; do not resolve it by
  > relabelling back to "cumulative".

- [ ] **Write the failing test.** Append to `tests/widgets/test_surf_widgets_a.py`:

```python
# ---------------------------------------------------------------------
# SurfHero
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.hero import (  # noqa: E402
    HOOK_LAUNCHED,
    HOOK_NOT_LIVE,
    SurfHero,
)

#: Live 2026-08-08 chain state: pool sides from dexscreener_imd.json
#: liquidity.base/quote, supply from imd_token.json total_supply/1e18.
#:
#: ``hook_status`` is spelled the way the *manager* spells it (WP4
#: ``_hook_status`` -> "NOT LIVE" / "LAUNCHED" / None, frozen in WP0's
#: SURF_KEYS comment and PRD §4).  A lowercase-snake fixture here would make
#: this whole file green against a widget that mis-renders every live payload.
#:
#: ``imd_burned_cum`` is 15,745 -- the single 2026-08-05 event -- and NOT the
#: 58,848 all-time ledger (12039+31064+15745) of PRD §1.  WP4 accumulates this
#: key from supply readings taken *after* this install started watching, so an
#: all-time fixture here would be pinning a number the data layer can never
#: produce, and would quietly certify all-time copy in the widget.  See the
#: ``imd_burned_cum`` note in WP3.2 and WP4 open issue 4.
_FULL_HERO = {
    "hook_status": HOOK_NOT_LIVE,
    "lp_liquidity": 26010397574917496158,
    "lp_imd": 388421.0,
    "lp_weth": 142.7067,
    "lp_owner_ok": True,
    "gate_open": False,
    "identities_written": 1,
    "imd_supply": 2376731.868679,
    "imd_burned_cum": 15745.0,
}


async def test_hero_full_payload_renders_all_four_boxes_on_screen():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**_FULL_HERO)
        await pilot.pause()
        screen = _screen_text(app)
        # HOOK: the launch state is words, not colour (PRD §3/§11).
        assert "NOT LIVE" in screen
        # LP: both pool sides and the owner sanity flag.
        assert "388.4K IMD" in screen
        assert "142.71 WETH" in screen
        assert "2.60e+19" in screen
        assert "owner ✓ frenpet.eth" in screen
        # GATE: closed, 1/2000 written (identity_counters + research).
        assert "CLOSED" in screen
        assert "1/2000 written" in screen
        # SUPPLY: full-precision supply + the burn this install has observed.
        # The word "observed" is load-bearing: the widget cannot know the
        # all-time total, so it must not imply one (WP4 open issue 4).
        assert "2,376,732 IMD" in screen
        assert "burned 15,745 observed" in screen
        assert "cum" not in screen


async def test_hero_zero_observed_burn_never_claims_none_was_ever_burned():
    """The day-one payload: healthy RPC, one supply read, nothing observed yet.

    WP4's ``observed_burn_total()`` returns ``None`` until the first successful
    supply read and ``0.0`` from then on, so a fresh install with a working RPC
    is handed ``0.0`` within one refresh -- while ~58,849 IMD had in fact been
    burned before the install existed (PRD §1).  Printing ``burned 0`` there is
    a confident false statement about the token, so ``0.0`` gets its own
    phrasing and no quantity is formatted.  ``None`` stays the unavailable dash.
    """
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "imd_burned_cum": 0.0})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no burn observed yet" in screen
        assert "burned 0" not in screen
        # The supply beside it is live and must still render.
        assert "2,376,732 IMD" in screen

        # None is "we have never read a supply", not "zero burned".
        widget.update_data(**{**_FULL_HERO, "imd_burned_cum": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no burn observed yet" not in screen
        assert "burned 0" not in screen
        assert f"burned {_fmt.DASH}" in screen   # _fmt is imported at file top


async def test_hero_launched_and_gate_open_flip_the_words():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "hook_status": HOOK_LAUNCHED, "gate_open": True})
        await pilot.pause()
        screen = _screen_text(app)
        assert "LAUNCHED" in screen
        assert "NOT LIVE" not in screen
        assert "OPEN" in screen
        assert "CLOSED" not in screen


async def test_hero_real_hook_vocabulary_never_hits_the_fallback():
    """The two values the manager actually emits must reach dedicated states.

    Both literals render *something* through the fallback arm too -- it
    uppercases whatever it is handed -- so asserting "NOT LIVE" in the screen
    proves nothing about which branch ran.  The subtitle is the tell: only the
    fallback says "unrecognized status".  This is the regression guard for the
    vocabulary mismatch (widget on ``not_live``/``launched`` vs manager on
    ``NOT LIVE``/``LAUNCHED``), which was silent on day one and would have
    stripped the $success styling from launch day itself.
    """
    assert (HOOK_NOT_LIVE, HOOK_LAUNCHED) == ("NOT LIVE", "LAUNCHED")

    for status, expected_sub in (
        (HOOK_NOT_LIVE, "detectors armed"),
        (HOOK_LAUNCHED, "v4 hook live"),
        # Case/spacing drift from the manager still lands on the real state.
        ("not live", "detectors armed"),
        ("launched", "v4 hook live"),
    ):
        widget = SurfHero()
        app = _Harness(widget)
        async with app.run_test(size=(160, 12)) as pilot:
            widget.update_data(**{**_FULL_HERO, "hook_status": status})
            await pilot.pause()
            screen = _screen_text(app)
            assert expected_sub in screen, status
            assert "unrecognized status" not in screen, status


async def test_hero_owner_changed_is_loud_words_not_colour():
    """lp_owner_ok=False means the LP NFT moved -- the launch precondition."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "lp_owner_ok": False})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" in screen
        assert "owner ✓" not in screen

        # And None is unknown -- neither the checkmark nor the alarm.
        widget.update_data(**{**_FULL_HERO, "lp_owner_ok": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" not in screen
        assert "owner ✓" not in screen
        assert "owner --" in screen


async def test_hero_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        assert "Loading" not in screen
        assert "—" in screen
        # A dead RPC must not render as a zero supply or a zero burn
        # (the false-BURN hazard, game_mechanics §Hazards 5).
        assert "0 IMD" not in screen
        assert "burned 0" not in screen


async def test_hero_unknown_hook_status_is_escaped_not_parsed():
    """The manager owns the vocabulary; a new value must render, not crash."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "hook_status": "[/x] holder-gated"})
        await pilot.pause()  # the crash would happen inside the message pump
        screen = _screen_text(app)
        assert "HOLDER-GATED" in screen
        # This is the arm the two real values must never reach.
        assert "unrecognized status" in screen
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.hero'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/hero.py`
  (seeded from `templates/hero_metrics_template.py` via `widgets/fwa/fwa_hero_metrics.py` —
  keep the FWA box structure and its `padding: 0 2` hazard note: vertical padding must stay 0
  or the fifth line clips):

```python
"""Hero row for the surf dashboard: HOOK · LP · GATE · SUPPLY.

Four boxes answering PRD §4's hero-left slot:

* **HOOK**   -- v4 hook status: NOT LIVE / LAUNCHED, always in words.
* **LP**     -- position #1167726's composition (IMD/WETH sides), raw
  liquidity, and the owner sanity flag.  ``lp_owner_ok=False`` means the
  position NFT moved -- the committed launch precondition -- and renders
  loud; ``None`` renders unknown, never the checkmark.
* **GATE**   -- identityAllowed() state + identities written.  The ``/2000``
  denominator is the IDMD cap: minted out 2026-05-14 on an
  ownership-bricked contract (identity_token.json ``total_supply: 2000``),
  so unlike every live metric it cannot drift.
* **SUPPLY** -- IMD totalSupply + the burn *this install has observed*.
  ``imd_burned_cum`` is an accumulator over successive supply readings
  (WP4.5), so it covers the observation window and nothing before it: the
  ~58,849 IMD burned across 05-16 / 07-31 / 08-05 predates every install and
  has no keyless source (WP4 open issue 4).  The copy therefore says
  ``observed``, never ``cum``, and the three states are distinct: ``None`` ->
  em-dash (no supply read yet, or the read failed), ``0.0`` -> ``no burn
  observed yet`` (we have watched, nothing moved -- printing ``burned 0``
  would assert that no IMD was ever burned, which is false), positive -> the
  quantity.  A ``None`` supply is a failed read and renders an em-dash:
  rendering ``0`` here is the visual twin of the false-BURN bug the data
  layer guards against.

Copied from ``fwa/fwa_hero_metrics.py`` and adapted to the surf data
contract (PRD §5 ``hero`` keys).  Primitives only: this module imports
nothing from the data layer.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_compact,
    fmt_liquidity,
)

#: The hook vocabulary the *manager* emits, spelled exactly as
#: ``SurfManager._hook_status()`` returns it and as WP0's ``SURF_KEYS`` comment
#: and PRD §4 freeze it.  Named constants rather than inline literals because
#: the widget and the manager have to agree on the spelling and nothing else
#: enforces it: a widget branching on ``"not_live"`` still *renders* -- through
#: the unknown-value arm -- so the disagreement is invisible until someone
#: reads the subtitle on launch day.
HOOK_NOT_LIVE = "NOT LIVE"
HOOK_LAUNCHED = "LAUNCHED"


class SurfHeroBox(Static):
    """A single hero box: title, big line, two subtitle lines."""


class SurfHero(Horizontal):
    """Row of four hero boxes: HOOK · LP · GATE · SUPPLY."""

    # Height 7 with zero vertical padding, like FWAHeroMetrics: the boxes
    # carry five content lines and `padding: 1 2` would clip the last one
    # silently (see the WP-10 hazard note in fwa_hero_metrics.py).
    DEFAULT_CSS = """
    SurfHero {
        height: 7;
    }
    SurfHero > SurfHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 2;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        for box_id in ("surf-hero-hook", "surf-hero-lp", "surf-hero-gate", "surf-hero-supply"):
            yield SurfHeroBox("[dim]Loading...[/]", id=box_id, classes="surf-hero-box")

    def update_data(
        self,
        hook_status=None,
        lp_liquidity=None,
        lp_imd=None,
        lp_weth=None,
        lp_owner_ok=None,
        gate_open=None,
        identities_written=None,
        imd_supply=None,
        imd_burned_cum=None,
        **_kwargs,
    ) -> None:
        """Refresh all four boxes from the manager's flat dict (PRD §5 hero)."""
        self._update_hook(hook_status)
        self._update_lp(lp_liquidity, lp_imd, lp_weth, lp_owner_ok)
        self._update_gate(gate_open, identities_written)
        self._update_supply(imd_supply, imd_burned_cum)

    # -- boxes ----------------------------------------------------------

    def _update_hook(self, hook_status) -> None:
        box = self.query_one("#surf-hero-hook", SurfHeroBox)
        status = str(hook_status or "").strip()
        if not status:
            box.update(f"[dim]V4 HOOK[/]\n\n[dim]{EMDASH}[/]\n[dim]status unknown[/]\n[dim] [/]")
            return
        # Canonical form: collapse whitespace, upper-case.  The manager already
        # sends "NOT LIVE"/"LAUNCHED"; this only absorbs case/spacing drift, it
        # does NOT invent a second vocabulary.
        canon = " ".join(status.split()).upper()
        if canon == HOOK_NOT_LIVE:
            big = f"[bold $warning]{HOOK_NOT_LIVE}[/]"
            sub = "detectors armed"
        elif canon == HOOK_LAUNCHED:
            # The flagship event: $success styling is the point (PRD §4).
            big = f"[bold $success]{HOOK_LAUNCHED}[/]"
            sub = "v4 hook live"
        else:
            # Tomorrow's vocabulary: escaped AFTER flattening/slicing/upper-
            # casing so a hostile or merely novel value renders literally
            # (PRD §6.3).  Slicing ``canon`` rather than ``status`` also keeps a
            # newline out of a fixed-height box -- these are 5 content lines in
            # a height-7 frame, so an extra line clips silently.
            big = f"[bold]{safe_markup(canon[:18])}[/]"
            sub = "unrecognized status"
        box.update(f"[dim]V4 HOOK[/]\n\n{big}\n[dim]{sub}[/]\n[dim] [/]")

    def _update_lp(self, lp_liquidity, lp_imd, lp_weth, lp_owner_ok) -> None:
        box = self.query_one("#surf-hero-lp", SurfHeroBox)
        imd = as_float(lp_imd)
        weth = as_float(lp_weth)
        big = f"[bold]{fmt_compact(imd)} IMD[/]" if imd is not None else f"[dim]{EMDASH}[/]"
        weth_str = f"{weth:,.2f} WETH" if weth is not None else f"{DASH} WETH"
        second = f"{weth_str} · L {fmt_liquidity(lp_liquidity)}"
        if lp_owner_ok is True:
            third = "[dim]owner ✓ frenpet.eth[/]"
        elif lp_owner_ok is False:
            # The position NFT moved: the committed launch precondition.
            third = "[bold $error]OWNER CHANGED[/]"
        else:
            third = f"[dim]owner {DASH}[/]"
        box.update(f"[dim]LP #1167726[/]\n\n{big}\n[dim]{second}[/]\n{third}")

    def _update_gate(self, gate_open, identities_written) -> None:
        box = self.query_one("#surf-hero-gate", SurfHeroBox)
        if gate_open is True:
            big = "[bold $success]OPEN[/]"
            sub = "holders can write now"
        elif gate_open is False:
            big = "[bold]CLOSED[/]"
            sub = "since 2026-05-14"
        else:
            big = f"[dim]{EMDASH}[/]"
            sub = "gate unknown"
        try:
            written = f"{int(identities_written)}/2000 written"
        except (TypeError, ValueError):
            written = f"{DASH} written"
        box.update(f"[dim]IDENTITY GATE[/]\n\n{big}\n[dim]{written}[/]\n[dim]{sub}[/]")

    def _update_supply(self, imd_supply, imd_burned_cum) -> None:
        box = self.query_one("#surf-hero-supply", SurfHeroBox)
        supply = as_float(imd_supply)
        burned = as_float(imd_burned_cum)
        # None is a failed read, never 0 -- the false-BURN twin (PRD §6.1).
        big = f"[bold]{supply:,.0f} IMD[/]" if supply is not None else f"[dim]{EMDASH}[/]"
        # Three states, because the key has three meanings (WP4.5):
        #   None -> no successful supply read yet / read failed  -> dash
        #   0.0  -> watched, nothing moved                       -> say so in words
        #   >0   -> the burn observed since we started watching  -> quantity
        # "observed", not "cum": the ~58,849 IMD of PRD §1 was burned before any
        # install existed and this widget can never see it, so a bare
        # "burned 0 cum" on day one would be a confident false statement.
        if burned is None:
            second = f"burned {DASH}"
        elif burned <= 0:
            second = "no burn observed yet"
        else:
            second = f"burned {burned:,.0f} observed"
        box.update(f"[dim]IMD SUPPLY[/]\n\n{big}\n[dim]{second}[/]\n[dim] [/]")
```

  One `"since 2026-05-14"` note: that is the gate-close *date* (an immutable historical fact from
  the research doc, not a live value) — acceptable per the hardcoding rule, which bans live values.
  If the reviewer disagrees, change `sub` for the closed state to `" "` — no test asserts it.

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
- [ ] **Prove the owner-flag test bites:** in `_update_lp`, temporarily change
  `if lp_owner_ok is True:` to `if lp_owner_ok in (True, None):` —
  `test_hero_owner_changed_is_loud_words_not_colour` must go red (the `None` branch renders the
  checkmark). Restore, re-run green.
- [ ] **Prove the hook-vocabulary test bites** (this is the regression that shipped in the first
  draft of this plan): in `_update_hook`, temporarily change the two comparisons to
  `if canon == "NOT_LIVE":` / `elif canon == "LAUNCHED_":` —
  `test_hero_real_hook_vocabulary_never_hits_the_fallback` must go red on the *subtitle*
  (`assert "unrecognized status" not in screen`), while `test_hero_full_payload_...`'s
  `assert "NOT LIVE" in screen` stays **green**, because the fallback uppercases its way to the
  same visible words. That asymmetry is the whole reason the new test asserts the subtitle and
  not the headline. Restore, re-run green.
- [ ] **Prove the observed-burn test bites:** in `_update_supply`, temporarily delete the
  `elif burned <= 0:` arm so `0.0` falls through to the quantity branch —
  `test_hero_zero_observed_burn_never_claims_none_was_ever_burned` must go red on
  `assert "burned 0" not in screen`, while every other hero test stays green (they all pass a
  positive burn, which is exactly how this shipped unnoticed). Restore, re-run green. Then
  restore `f"burned {burned:,.0f} cum"` in the positive arm and confirm
  `test_hero_full_payload_renders_all_four_boxes_on_screen` goes red on `assert "cum" not in
  screen` — the label is a contract, not a preference. Restore, re-run green.
- [ ] **Cross-WP check (report, do not fix):** confirm WP4's `SurfManager._hook_status()` still
  returns exactly `"LAUNCHED"` / `"NOT LIVE"` / `None`. If WP4 has changed the spelling, that is
  a contract change against WP0's `SURF_KEYS` comment and PRD §4 — report it to the plan owner
  rather than adding a third spelling here.
- [ ] **Cross-WP check (report, do not fix):** confirm WP4's `SurfCache.observed_burn_total()`
  still returns `None` before the first successful supply read and `0.0` after it, and that
  `imd_burned_cum` is still observation-scoped rather than seeded with an all-time figure. If
  WP4 ever gains a real all-time source, this widget's copy and the `_FULL_HERO` fixture must
  change together — report to the plan owner, do not seed a number here. Note also that WP0's
  `SURF_KEYS` comment for `imd_burned_cum` reads `cumulative, from the burn ledger`, which
  describes an all-time total the data layer does not produce; that comment is WP0's file —
  report it, do not edit it.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/hero.py tests/widgets/test_surf_widgets_a.py && git commit -m "feat(surf): SurfHero hero row (hook, LP, gate, supply)"`

---

### Task WP3.3: `SurfSignals` — the six detectors, FIRED loud

**Files:**
- Create: `maxpane_dashboard/widgets/surf/signals.py`
- Test: `tests/widgets/test_surf_widgets_a.py` (append)

**Interfaces:**
- Consumes: `_fmt.fmt_age`, `safe_markup`, `visible_len` (from `markup_safety`).
- Produces:
  `SurfSignals(Vertical)` with
  `update_data(sig_post_state=None, sig_post_detail=None, sig_post_age_s=None, sig_lp_state=None, sig_lp_detail=None, sig_lp_age_s=None, sig_gate_state=None, sig_gate_detail=None, sig_gate_age_s=None, sig_deploy_state=None, sig_deploy_detail=None, sig_deploy_age_s=None, sig_bridge_state=None, sig_bridge_detail=None, sig_bridge_age_s=None, sig_burn_state=None, sig_burn_detail=None, sig_burn_age_s=None, **_kwargs) -> None`
  — exactly the 18 PRD §5 `signals` keys. States: `"ok"`/`"watch"`/`"fired"`/`None`
  (case-insensitive on input; anything else renders as the unknown row).
  Module constants `WIDEN_HINT = "‹ widen"`, `SEPARATOR_COLS = 3`, `MIN_DETAIL_COLS = 6` and
  `DETECTOR_LABELS = ("NEW POST", "LP MIGRATION", "GATE OPEN", "NEW DEPLOY", "BRIDGE STAGE", "BURN")`;
  module functions `_head(label, state, age_s) -> str` and
  `_fmt_signal_row(label, state, detail, age_s, available=None) -> str` (both pure, unit-tested).
  `available` is the row's column budget; `None` (the default, and what an unmounted widget
  reports) means "width unknown — do not truncate".

**Row width — the detail shrinks, the head never does (read before writing `_render_view`).**
This panel is the binding width constraint of the whole dashboard if it is written naively, so
the arithmetic is fixed here rather than discovered in WP5.5's measurement:

- `SurfSignals` is the `2fr` of the hero row's `3fr:2fr` split, minus the two padding columns of
  `.surf-signals-body` — `2W/5 − 4` columns of content. At the pinned `W = 143` that is **53**,
  so `available = 51`.
- The **head** is the part that cannot shrink: two leading spaces, the glyph, the full PRD §3
  label and the state word (plus `NNd ago` when fired). The realistic worst case is
  `  ▶ BRIDGE STAGE FIRED 12m ago` = **30 columns** (`LP MIGRATION` ties on label length); the
  absolute worst that `fmt_age` can produce is a four-character age,
  `  ▶ BRIDGE STAGE FIRED 100d ago` = **31**. The shortest head is `  ● BURN OK` = 11.
- With the ` · ` separator (`SEPARATOR_COLS = 3`) that leaves **17–18** columns of detail on the
  worst-case row at the pinned width, and ~37 on the shortest. `_fmt_signal_row` truncates the
  detail to that budget with a visible `…`; it does **not** wrap, and it does not shorten the head.
  Below `MIN_DETAIL_COLS = 6` of remaining budget the detail is dropped entirely rather than
  rendered as a bare `…`, which carries no information.
- Therefore `clipped` — the thing that lights `‹ widen` — is set only when the **head** does not
  fit. A whole-row test would light the marker permanently: WP2 builds details up to
  `DETAIL_LIMIT = 48` and its relaxed-FIRED form
  (`f"nonce 13 · no new post · last: {LP_POST_DETAIL}"`, 87 characters) deliberately exceeds that,
  so real rows run 82–105 columns against a 51-column panel. A marker that is always lit means
  nothing, and chasing it would push `FULL_LAYOUT_COLUMNS` to ~190 — past the ~169 columns a
  laptop gets at the forced 17 pt, i.e. a full layout no one can reach. This is the same trap
  `fwa_signals.py`'s buy-gate footnote records.

**Report to WP2 (do not edit `analytics/surf_signals.py` — one owner per file):** the real display
budget is `available − head − 3`, i.e. **17–18 columns worst case / ~37 best case at W = 143**, not
the "~55 columns" `DETAIL_LIMIT`'s comment assumes. `DETAIL_LIMIT = 48` is still a fine
*producer-side* sanity cap (it bounds what goes into the baseline cache and into the `last: …`
composition), but it is not a display budget and WP2's comment should say so; the widget owns
fitting. Put this in your final summary.

**Label vocabulary — one source, PRD §3 spelling (read before writing the rows).**
The detector labels are a *cross-WP interface string*, not a local styling choice. WP5's screen
test (`test_refresh_renders_title_and_all_panels`) and two WP6 acceptance tests
(`test_all_six_detectors_survive_the_real_stylesheet`,
`test_a_full_outage_renders_explicit_states_not_zeros`) all assert the six PRD §3 names appear in
composited output. So this widget renders the **full** names — `NEW POST`, `LP MIGRATION`,
`GATE OPEN`, `NEW DEPLOY`, `BRIDGE STAGE`, `BURN` — at every width; there is no short-form tier
and no per-width label swap. Do **not** abbreviate them to fit: the label is part of the row
*head*, and the head is what the width budget below protects — the detail tail is truncated in
code (with `text-overflow: ellipsis` as a backstop) so the label always reaches the compositor,
which is exactly what those three tests need.

Export them once as `DETECTOR_LABELS` (order = PRD §3 order = `_ROWS` order) so WP5/WP6 can
`from maxpane_dashboard.widgets.surf import DETECTOR_LABELS` instead of re-typing string
literals; `_ROWS` derives its label column from that tuple. The full names cost ~10 columns more
than a shortened set — but because the *detail* absorbs that cost rather than the panel, they do
**not** raise WP5.5's `SURF_FULL_LAYOUT_COLUMNS`: this widget fits inside the 53 columns it gets
at `W = 143`, and the binding constraint for the measurement is some other panel.

- [ ] **Write the failing test.** Append to `tests/widgets/test_surf_widgets_a.py`:

```python
# ---------------------------------------------------------------------
# SurfSignals
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.markup_safety import visible_len  # noqa: E402
from maxpane_dashboard.widgets.surf.signals import (  # noqa: E402
    DETECTOR_LABELS,
    MIN_DETAIL_COLS,
    SEPARATOR_COLS,
    WIDEN_HINT,
    SurfSignals,
    _fmt_signal_row,
    _head,
)

#: A realistic mixed payload: the 2026-08-07 morning, 12 minutes after the
#: staging mint (ops_eth_token_transfers.json: +114,366.9 IMD OFT-minted to
#: frenpet.eth at 04:21:35) and two hours after the nonce-13 announce post.
_FULL_SIGNALS = {
    "sig_post_state": "fired",
    "sig_post_detail": "#14 · I moved 33 eth to the LP on mainnet",
    "sig_post_age_s": 7200.0,
    "sig_lp_state": "ok",
    "sig_lp_detail": "pos #1167726 liquidity unchanged",
    "sig_lp_age_s": None,
    "sig_gate_state": "ok",
    "sig_gate_detail": "closed · 1/2000 written",
    "sig_gate_age_s": None,
    "sig_deploy_state": "watch",
    "sig_deploy_detail": "frenpet.eth nonce 29→30",
    "sig_deploy_age_s": 900.0,
    "sig_bridge_state": "fired",
    "sig_bridge_detail": "+114,367 IMD minted to frenpet.eth",
    "sig_bridge_age_s": 720.0,
    "sig_burn_state": "ok",
    "sig_burn_detail": "last burn 15,745 IMD",
    "sig_burn_age_s": None,
}


async def test_signals_labels_are_the_prd_names_wp5_and_wp6_assert_on():
    """The label vocabulary is a cross-WP interface, pinned in one place.

    WP5's screen test and WP6's stylesheet/outage acceptance tests assert
    these exact PRD §3 strings against composited output.  If someone
    shortens a label for width, this goes red *here* -- in the widget WP
    that owns the string -- instead of in two WPs that only consume it.
    """
    assert DETECTOR_LABELS == (
        "NEW POST",
        "LP MIGRATION",
        "GATE OPEN",
        "NEW DEPLOY",
        "BRIDGE STAGE",
        "BURN",
    )


async def test_signals_fired_rows_carry_state_and_age_in_words():
    """FIRED must survive greyscale: the word, the age, the glyph -- in text."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "NEW POST FIRED 2h ago" in screen
        assert "BRIDGE STAGE FIRED 12m ago" in screen
        assert "NEW DEPLOY WATCH" in screen
        assert "LP MIGRATION OK" in screen
        assert "GATE OPEN OK" in screen
        assert "BURN OK" in screen
        # Details ride along.
        assert "+114,367 IMD minted to frenpet.eth" in screen
        assert "frenpet.eth nonce 29→30" in screen


async def test_signals_all_six_rows_always_render():
    """None-state rows are dashes -- six rows on screen no matter what."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data()
        await pilot.pause()
        screen = _screen_text(app)
        for label in DETECTOR_LABELS:
            assert f"{label} --" in screen, label
        # No invented state: nothing fired, nothing ok.
        assert "FIRED" not in screen
        assert "OK" not in screen.replace("SIGNALS", "")


async def test_signals_fired_without_age_omits_the_age_not_the_state():
    row = _fmt_signal_row("LP MIGRATION", "fired", "liquidity -37%", None)
    assert "LP MIGRATION FIRED" in row
    assert "ago" not in row
    assert "-- ago" not in row


async def test_signals_unknown_state_renders_as_unknown_not_ok():
    """A state string the widget doesn't know is unknown -- never OK."""
    row = _fmt_signal_row("NEW POST", "exploded", "detail", 5.0)
    assert "NEW POST --" in row
    assert "OK" not in row and "FIRED" not in row


async def test_signals_detail_is_escaped_and_newline_flattened():
    """Detail strings quote announce text -- attacker-writable (PRD §6.4)."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_SIGNALS,
                "sig_post_detail": "[/x] pwn\nsecond line",
            }
        )
        await pilot.pause()  # a MarkupError would raise inside the pump here
        screen = _screen_text(app)
        assert "pwn second line" in screen  # flattened, rendered literally


def test_signals_head_is_never_wider_than_the_panel_it_gets():
    """The unshrinkable part of a row must fit the pinned full-layout width.

    ``SurfSignals`` is the 2fr of a 3fr:2fr hero row, so it gets ``2W/5 - 4``
    content columns -- 53 at the pinned ``W = 143`` -- and ``padding: 0 1``
    on the body rows leaves 51.  The head is glyph + full PRD §3 label +
    state word + age; if *that* stops fitting, the panel genuinely needs a
    wider terminal.  While it fits, the detail is truncated to what is left
    and the marker stays dark -- which is what keeps ``‹ widen`` meaningful.
    """
    available = 2 * 143 // 5 - 4 - 2  # == 51
    worst = max(
        visible_len(_head(label, state, age))
        for label in DETECTOR_LABELS
        for state in ("fired", "watch", "ok", None, "exploded")
        for age in (None, 45.0, 7200.0, 100 * 86400.0)
    )
    # "  ▶ BRIDGE STAGE FIRED 100d ago" -- the widest head this widget can
    # build.  The realistic fired row ("... 12m ago") is 30.
    assert worst == 31, worst
    # Head + separator + a usable detail stub still fits the real panel.
    assert worst + SEPARATOR_COLS + MIN_DETAIL_COLS <= available


async def test_signals_long_detail_is_truncated_and_does_not_light_the_marker():
    """A 100-char detail in a 60-column panel: label intact, tail cut, no widen.

    This is the FWA buy-gate lesson.  WP2 builds details up to
    ``DETAIL_LIMIT = 48`` and its relaxed-FIRED form composes an even longer
    ``... · last: ...`` string, so real rows are 80-105 columns against a
    51-column panel.  If the *whole row* set ``clipped``, ``‹ widen`` would
    be lit during healthy operation and would stop meaning anything.
    """
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(60, 14)) as pilot:
        widget.update_data(**{**_FULL_SIGNALS, "sig_post_detail": "x" * 100})
        await pilot.pause()
        screen = _screen_text(app)
        assert "NEW POST FIRED 2h ago" in screen   # head survives whole
        assert "…" in screen                       # detail was cut, visibly
        assert "x" * 40 not in screen              # and really cut
        assert WIDEN_HINT not in screen            # a fitted head is not clipped


async def test_signals_narrow_width_announces_clipping():
    """``‹ widen`` fires when the *head* cannot fit -- 26 columns is below 30."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(26, 14)) as pilot:
        widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        assert WIDEN_HINT in _screen_text(app)

    app2 = _Harness(SurfSignals())
    async with app2.run_test(size=(120, 14)) as pilot:
        app2._widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        assert WIDEN_HINT not in _screen_text(app2)


def test_signals_row_truncation_is_pure_and_keeps_the_head():
    """``available`` drives the cut; ``None`` means "width unknown, don't cut".

    The long payload is WP2's relaxed-FIRED composition shape -- the one that
    deliberately blows past ``DETAIL_LIMIT`` -- so this is the real input, not
    a stress string.
    """
    long_detail = "nonce 13 · no new post · last: " + "y" * 60
    full = _fmt_signal_row("NEW POST", "ok", long_detail, None)
    assert long_detail in full          # unsized widget: never truncate

    cut = _fmt_signal_row("NEW POST", "ok", long_detail, None, available=40)
    assert "NEW POST OK" in cut         # head intact
    assert "…" in cut                   # tail cut, visibly
    assert visible_len(cut) <= 40

    # Too narrow for a usable detail: the head renders alone, never a bare "…".
    head_only = _fmt_signal_row(
        "BRIDGE STAGE", "fired", long_detail, 7200.0, available=31
    )
    assert "BRIDGE STAGE FIRED 2h ago" in head_only
    assert "…" not in head_only
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.signals'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/signals.py`
  (seeded from `templates/signals_template.py` via `widgets/fwa/fwa_signals.py` — keep the
  clip-announcement machinery, swap the five FWA rows for the six detectors):

```python
"""The six-detector panel for the surf dashboard (PRD §3).

One row per detector: NEW POST · LP MIGRATION · GATE OPEN · NEW DEPLOY ·
BRIDGE STAGE · BURN.  Each row renders ``state · age · one-line detail``
with the state always spelled in words:

* ``fired`` -- ``▶ NEW POST FIRED 2h ago · detail`` in loud bold ``$error``.
  The 24 h FIRED persistence and the baseline math live in
  ``analytics/surf_signals.py``; this widget renders whatever state string
  the manager hands it and adds nothing.
* ``watch`` -- ``◐ NEW DEPLOY WATCH · detail`` in ``$warning``.
* ``ok``    -- ``● LP MIGRATION OK · detail`` dim.
* ``None``/unknown -- ``● LP MIGRATION --`` dim: an unreadable detector is
  unknown, never OK (PRD §6.1's rendering half).

The labels are the PRD §3 names in full, at *every* width -- they are an
interface, asserted against composited output by the screen WP and by two
app-level acceptance tests.  ``DETECTOR_LABELS`` below is the single source;
importers use it instead of retyping the strings.  They are never shortened
to save columns: the label belongs to the row *head*, and the head is what
the width budget below protects.

Detail strings quote announce-channel text, which is attacker-writable by
design, so every detail passes ``safe_markup`` -- after newline flattening
*and after truncation*, so a cut can never bisect an escape sequence
(``feed._item_lines`` does the same, for the same reason).

Width budget -- the detail shrinks, the head never does
-------------------------------------------------------

This panel is the ``2fr`` of the hero row's ``3fr:2fr`` split, so it gets
``2W/5 - 4`` content columns; ``padding: 0 1`` on the body rows costs two
more.  At the pinned full-layout width ``W = 143`` that is 53 columns of
content and **51 usable**::

    head                                    cols
    "  ● BURN OK"                             11   <- shortest
    "  ▶ BRIDGE STAGE FIRED 12m ago"          30   <- realistic worst
    "  ▶ BRIDGE STAGE FIRED 100d ago"         31   <- absolute worst

The head is unshrinkable (glyph + full label + state word + age).  Whatever
is left after it and the ``· `` separator (``SEPARATOR_COLS``) is the detail
budget -- **17-18 columns worst case at the pinned width, ~37 on a short
label** -- and the detail is cut to fit with a visible ``…``.

``clipped``, which lights ``‹ widen`` in the title, is therefore set **only
when the head itself does not fit**.  Testing the whole row would light the
marker permanently: ``analytics/surf_signals`` builds details up to
``DETAIL_LIMIT`` (48) and its relaxed-FIRED form composes
``"... · last: ..."`` on top of that, so real rows run 80-105 columns against
a 51-column panel.  A marker that is always on means nothing, and widening
the layout to clear it would push ``FULL_LAYOUT_COLUMNS`` to ~190 -- past the
~169 columns a laptop gets at the forced 17 pt, i.e. a full layout nobody can
reach.  ``fwa_signals.py`` records the same trap in its ``_GATE_WORDS`` note.

Row budget: title + spacer + 6 rows = 8 lines.

Primitives only -- this module imports nothing from the data layer.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age

#: Marker appended to the title when a *head* could not fit (see the module
#: docstring: a truncated detail is normal operation, not a clipped row).
WIDEN_HINT = "‹ widen"

#: Visible cost of the ``· `` that joins a head to its detail, counting the
#: space in front of it: ``" · "``.
SEPARATOR_COLS = 3

#: Below this many columns of remaining budget the detail is dropped rather
#: than rendered as a stub: two characters and an ellipsis say nothing.
MIN_DETAIL_COLS = 6

#: The state vocabulary this widget knows.  Anything else -- including
#: ``None`` -- is the unknown row, which is never OK (PRD §6.1).
_KNOWN_STATES = ("fired", "watch", "ok")

#: The six detector labels, PRD §3 spelling, PRD §3 order.  **Interface**:
#: the screen tests and the app-level acceptance tests assert these exact
#: strings reach the compositor -- import this tuple, never retype it, and
#: never shorten a label to save columns (see the module docstring).
DETECTOR_LABELS = (
    "NEW POST",
    "LP MIGRATION",
    "GATE OPEN",
    "NEW DEPLOY",
    "BRIDGE STAGE",
    "BURN",
)

#: payload prefix + child id per detector, aligned 1:1 with DETECTOR_LABELS.
_ROW_KEYS = (
    ("post", "#surf-sig-post"),
    ("lp", "#surf-sig-lp"),
    ("gate", "#surf-sig-gate"),
    ("deploy", "#surf-sig-deploy"),
    ("bridge", "#surf-sig-bridge"),
    ("burn", "#surf-sig-burn"),
)

#: (payload prefix, row label, child id) for the six detectors, in PRD order.
_ROWS = tuple(
    (prefix, label, selector)
    for (prefix, selector), label in zip(_ROW_KEYS, DETECTOR_LABELS)
)


def _head(label: str, state, age_s) -> str:
    """The unshrinkable part of a row, as markup.  Pure; unit-tested.

    Measure it with ``visible_len`` -- this is the width that decides whether
    the panel needs widening, and the only width the row cannot give back.
    """
    state_s = str(state or "").strip().lower()
    if state_s == "fired":
        age = fmt_age(age_s)
        body = f"{label} FIRED {age} ago" if age != DASH else f"{label} FIRED"
        return f"  [bold $error]▶ {body}[/]"
    if state_s == "watch":
        return f"  [$warning]◐ {label} WATCH[/]"
    if state_s == "ok":
        return f"  [$success]●[/] [dim]{label} OK[/]"
    # None or an unknown vocabulary word: unknown, never OK.
    return f"  [dim]● {label} {DASH}[/]"


def _fmt_signal_row(label: str, state, detail, age_s, available=None) -> str:
    """Render one detector row, fitting the detail to ``available`` columns.

    ``available`` is the row's column budget.  ``None`` -- the default, and
    what an unmounted widget reports -- means "width unknown, do not
    truncate"; the unit tests rely on that to inspect the full string.

    The head is never shortened.  The detail is cut to whatever is left after
    the head and ``SEPARATOR_COLS``, with a visible ``…``; below
    ``MIN_DETAIL_COLS`` it is dropped entirely.  Escaping happens *after* the
    cut so a slice can never bisect an escape sequence.
    """
    head = _head(label, state, age_s)
    if str(state or "").strip().lower() not in _KNOWN_STATES:
        # An unknown detector has no detail worth quoting.
        return head

    # Newlines flattened first: an announce body is multi-line, a row is not.
    flat = " ".join(str(detail or "").split())
    if not flat:
        return head

    if available:
        budget = int(available) - visible_len(head) - SEPARATOR_COLS
        if budget < MIN_DETAIL_COLS:
            return head
        if len(flat) > budget:
            flat = flat[: budget - 1].rstrip() + "…"

    return f"{head} [dim]· {safe_markup(flat)}[/]"


class SurfSignals(Vertical):
    """Detector panel with six rows."""

    DEFAULT_CSS = """
    SurfSignals > .surf-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfSignals > .surf-signals-body {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="surf-signals-title", id="surf-sig-title")
        yield Static("", classes="surf-signals-body", id="surf-sig-spacer")
        for _, _, selector in _ROWS:
            yield Static("", classes="surf-signals-body", id=selector.lstrip("#"))

    def update_data(
        self,
        sig_post_state=None,
        sig_post_detail=None,
        sig_post_age_s=None,
        sig_lp_state=None,
        sig_lp_detail=None,
        sig_lp_age_s=None,
        sig_gate_state=None,
        sig_gate_detail=None,
        sig_gate_age_s=None,
        sig_deploy_state=None,
        sig_deploy_detail=None,
        sig_deploy_age_s=None,
        sig_bridge_state=None,
        sig_bridge_detail=None,
        sig_bridge_age_s=None,
        sig_burn_state=None,
        sig_burn_detail=None,
        sig_burn_age_s=None,
        **_kwargs,
    ) -> None:
        """Refresh the six rows.  Kwargs are exactly the PRD §5 signal keys."""
        self._payload = {
            "sig_post_state": sig_post_state,
            "sig_post_detail": sig_post_detail,
            "sig_post_age_s": sig_post_age_s,
            "sig_lp_state": sig_lp_state,
            "sig_lp_detail": sig_lp_detail,
            "sig_lp_age_s": sig_lp_age_s,
            "sig_gate_state": sig_gate_state,
            "sig_gate_detail": sig_gate_detail,
            "sig_gate_age_s": sig_gate_age_s,
            "sig_deploy_state": sig_deploy_state,
            "sig_deploy_detail": sig_deploy_detail,
            "sig_deploy_age_s": sig_deploy_age_s,
            "sig_bridge_state": sig_bridge_state,
            "sig_bridge_detail": sig_bridge_detail,
            "sig_bridge_age_s": sig_bridge_age_s,
            "sig_burn_state": sig_burn_state,
            "sig_burn_detail": sig_burn_detail,
            "sig_burn_age_s": sig_burn_age_s,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render on resize so the clipped-row marker tracks the width."""
        self._render_view()

    # -- rendering -----------------------------------------------------

    def _render_view(self) -> None:
        payload = self._payload
        # ``padding: 0 1`` on the body rows costs two columns.  0 means "not
        # laid out yet" -- pass None so rows render untruncated until we know.
        available = max(self.content_size.width - 2, 0) or None
        clipped = False

        for prefix, label, selector in _ROWS:
            state = payload.get(f"sig_{prefix}_state")
            age_s = payload.get(f"sig_{prefix}_age_s")
            markup = _fmt_signal_row(
                label,
                state,
                payload.get(f"sig_{prefix}_detail"),
                age_s,
                available,
            )
            # Only an unfittable *head* is a clipped row: the detail was
            # already shrunk to fit, and flagging that as clipping would keep
            # the marker permanently lit (module docstring).
            if available and visible_len(_head(label, state, age_s)) > available:
                clipped = True
            try:
                self.query_one(selector, Static).update(markup)
            except Exception:  # not composed yet
                return

        try:
            title = self.query_one("#surf-sig-title", Static)
        except Exception:
            return
        title.update(f"SIGNALS  [yellow]{WIDEN_HINT}[/]" if clipped else "SIGNALS")
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
- [ ] **Prove the escape bites** (decoder-shaped): in `_fmt_signal_row`, temporarily replace
  the final `safe_markup(flat)` with a bare `flat` —
  `test_signals_detail_is_escaped_and_newline_flattened` must go red with a `MarkupError`
  raised from inside the message pump (this is exactly the deferred-crash mode
  `markup_safety.py` documents). Restore, re-run green.
- [ ] **Prove the unknown-state test bites:** temporarily change the final `return` in `_head`
  to the ok-row string (`f"  [$success]●[/] [dim]{label} OK[/]"`).
  `test_signals_unknown_state_renders_as_unknown_not_ok` must go red. Restore, re-run green.
- [ ] **Prove the truncation bites, both halves** (this is the finding that made the marker
  useless, so test each half separately):
  1. In `_fmt_signal_row`, temporarily skip the cut (`if False and len(flat) > budget:`) —
     `test_signals_long_detail_is_truncated_and_does_not_light_the_marker` must go red on the
     missing `…`, and `test_signals_row_truncation_is_pure_and_keeps_the_head` on
     `visible_len(cut) <= 40`.
  2. Restore, then in `_render_view` temporarily measure the whole row instead of the head
     (`visible_len(markup) > available`) — the same width test must go red on `WIDEN_HINT not in
     screen`, because every real row is longer than the panel. That red is the production bug in
     miniature: the marker lit on healthy data. Restore, re-run green.
- [ ] **Prove the label guard bites:** temporarily shorten one entry of `DETECTOR_LABELS`
  (`"LP MIGRATION"` → `"LP"`). Both
  `test_signals_labels_are_the_prd_names_wp5_and_wp6_assert_on` and
  `test_signals_fired_rows_carry_state_and_age_in_words` must go red — that pair is what stops a
  width-motivated rename from silently breaking three tests in WP5/WP6. Restore, re-run green.
- [ ] **Confirm the labels still render at every tier** (they must: the truncation eats the tail,
  never the head):
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -k "signals" -v` covers 26, 60
  and 120 columns, and `test_signals_head_is_never_wider_than_the_panel_it_gets` covers the pinned
  51. If a label ever *stops* reaching the compositor at 143 columns, that is a screen-layout
  finding for WP5, not a reason to abbreviate here — report it.
- [ ] **Report the detail budget to WP2** in your final summary: display budget is
  `available − visible_len(head) − 3` = **17–18 columns** worst case at `W = 143`, ~37 on a short
  label — so `analytics/surf_signals.DETAIL_LIMIT = 48` is a producer-side sanity cap, not the
  "~55 columns" display budget its comment claims. Do not edit that file.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/signals.py tests/widgets/test_surf_widgets_a.py && git commit -m "feat(surf): SurfSignals six-detector panel with loud FIRED rows"`

---

### Task WP3.4: `SurfMarket` — price, parity, supply sparkline

**Files:**
- Create: `maxpane_dashboard/widgets/surf/market.py`
- Test: `tests/widgets/test_surf_widgets_a.py` (append)

**Interfaces:**
- Consumes: `sparkline_common.{coerce_points, build_sparkline, SPARK_WIDTH}` (mandatory import,
  never copied), `_fmt` helpers.
- Produces:
  `SurfMarket(Vertical)` with
  `update_data(imd_price_usd=None, imd_change_24h_pct=None, imd_vol_24h_usd=None, pool_liquidity_usd=None, fp_price_usd=None, parity_pct=None, supply_series=None, price_series=None, **_kwargs) -> None`
  — exactly the PRD §5 `market` keys. Series are `list[[ts, value]]`.

- [ ] **Write the failing test.** Append to `tests/widgets/test_surf_widgets_a.py`:

```python
# ---------------------------------------------------------------------
# SurfMarket
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.market import SurfMarket  # noqa: E402

#: dexscreener_imd.json / dexscreener_fp.json, fetched 2026-08-08:
#: IMD $0.7074 +30.89% vol $244,178 pool $548,701.21; FP $0.7274 →
#: parity (0.7074/0.7274 − 1)·100 = −2.75%.  The supply series is the real
#: burn staircase: pre-07-31 supply, the 31,064 burn, the 15,745 burn, then
#: the 08-07 bridge-in mint of 114,366.9 (imd_token.json end state).
_SUPPLY_SERIES = [
    [1784000000, 2309194.0],
    [1785467000, 2278130.0],
    [1785903575, 2262384.97],
    [1786076495, 2376731.868679],
]
_PRICE_SERIES = [[1785900000 + i * 3600, 0.53 + i * 0.004] for i in range(48)]

_FULL_MARKET = {
    "imd_price_usd": 0.7074,
    "imd_change_24h_pct": 30.89,
    "imd_vol_24h_usd": 244178.0,
    "pool_liquidity_usd": 548701.21,
    "fp_price_usd": 0.7274,
    "parity_pct": -2.75,
    "supply_series": _SUPPLY_SERIES,
    "price_series": _PRICE_SERIES,
}


async def test_market_full_payload_renders_all_numbers():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        screen = _screen_text(app)
        assert "$0.7074" in screen
        assert "▲ +30.89%" in screen          # glyph AND sign, not colour alone
        assert "vol 24h $244.2K" in screen
        assert "pool $548.7K" in screen
        assert "FP $0.7274" in screen
        assert "parity ▼ -2.75%" in screen    # negative: IMD below FP


async def test_market_supply_sparkline_shows_the_burn_steps():
    """The supply bar must actually vary -- burns step down, mints step up."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        screen = _screen_text(app)
        supply_line = next(l for l in screen.splitlines() if "supply" in l)
        # More than one distinct block char = the staircase is visible.
        blocks = {c for c in supply_line if c in "▁▂▃▄▅▆▇█"}
        assert len(blocks) >= 2, supply_line
        assert "2.4M" in supply_line          # the live end-state, labelled


async def test_market_short_or_missing_series_say_waiting():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**{**_FULL_MARKET, "supply_series": [], "price_series": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert screen.count("waiting for data") == 2


async def test_market_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        assert "$0.00" not in screen
        assert "+0.00%" not in screen
        assert "--" in screen


async def test_market_malformed_series_points_are_skipped_not_fatal():
    """A single null in a persisted series must not kill the panel."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "supply_series": [None, [1, None], "junk", *_SUPPLY_SERIES],
            }
        )
        await pilot.pause()
        screen = _screen_text(app)
        assert "2.4M" in screen  # the valid points still render
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.market'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/market.py`
  (seeded from `templates/sparkline_template.py` via `widgets/fwa/fwa_sparkline.py`; imports the
  shared helpers, no copies):

```python
"""IMD market panel: price, volume, liquidity, FP parity, two sparklines.

Six rows (title + spacer + four content rows + two sparkline rows):

* price + 24h Δ (glyph carries the sign; colour is redundant, PRD §11)
* volume · pool liquidity
* FP price · parity spread -- the bridge-arbitrage health metric; a live
  value computed upstream each refresh, never a constant (PRD §6.2)
* price sparkline, supply sparkline.  The supply bar is the burn
  staircase: LP-fee burns step it down, OFT bridge-ins step it up.  Series
  come as ``list[[ts, value]]`` and are coerced through
  ``sparkline_common.coerce_points`` -- a single null point degrades to a
  skipped point, never a dead panel.

``None`` anywhere renders ``--``; a missing feed is never a zero price.

Sparkline helpers are imported from ``sparkline_common`` (house rule
MEDI-36 -- import, never copy).  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_WIDTH,
    build_sparkline,
    coerce_points,
)
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_compact,
    fmt_price,
)

_WAITING = "[dim]waiting for data...[/]"


def _fmt_change(value) -> str:
    """Signed 24h change: glyph + sign in text, theme colours only."""
    v = as_float(value)
    if v is None:
        return f"[dim]{DASH} 24h[/]"
    if v > 0:
        return f"[$success]▲ {v:+.2f}%[/] [dim]24h[/]"
    if v < 0:
        return f"[$error]▼ {v:+.2f}%[/] [dim]24h[/]"
    return f"[dim]● {v:+.2f}% 24h[/]"


def _fmt_parity(value) -> str:
    """FP↔IMD parity spread; negative means IMD trades below FP."""
    v = as_float(value)
    if v is None:
        return f"[dim]parity {DASH}[/]"
    if v > 0:
        return f"[dim]parity[/] [$success]▲ {v:+.2f}%[/]"
    if v < 0:
        return f"[dim]parity[/] [$error]▼ {v:+.2f}%[/]"
    return f"[dim]parity ● {v:+.2f}%[/]"


def _spark(series) -> str:
    """A block sparkline from ``[[ts, value]]``, or the waiting message."""
    points = coerce_points(series)
    if len(points) < 2:
        return _WAITING
    values = [v for _, v in points]
    return f"[cyan]{build_sparkline(values, pad=len(values) >= SPARK_WIDTH)}[/]"


class SurfMarket(Vertical):
    """IMD market panel."""

    DEFAULT_CSS = """
    SurfMarket > .surf-market-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfMarket > .surf-market-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("IMD MARKET", classes="surf-market-title")
        yield Static("", classes="surf-market-line", id="surf-mkt-spacer")
        yield Static(_WAITING, classes="surf-market-line", id="surf-mkt-price")
        yield Static("", classes="surf-market-line", id="surf-mkt-vol")
        yield Static("", classes="surf-market-line", id="surf-mkt-parity")
        yield Static("", classes="surf-market-line", id="surf-mkt-price-spark")
        yield Static("", classes="surf-market-line", id="surf-mkt-supply-spark")

    def update_data(
        self,
        imd_price_usd=None,
        imd_change_24h_pct=None,
        imd_vol_24h_usd=None,
        pool_liquidity_usd=None,
        fp_price_usd=None,
        parity_pct=None,
        supply_series=None,
        price_series=None,
        **_kwargs,
    ) -> None:
        """Refresh all rows.  Kwargs are exactly the PRD §5 market keys."""
        price = fmt_price(imd_price_usd)
        big = f"[bold]{price}[/]" if price != DASH else f"[dim]{DASH}[/]"
        self.query_one("#surf-mkt-price", Static).update(
            f"  {big}  {_fmt_change(imd_change_24h_pct)}"
        )

        vol = as_float(imd_vol_24h_usd)
        liq = as_float(pool_liquidity_usd)
        vol_s = f"${fmt_compact(vol)}" if vol is not None else DASH
        liq_s = f"${fmt_compact(liq)}" if liq is not None else DASH
        self.query_one("#surf-mkt-vol", Static).update(
            f"  [dim]vol 24h[/] {vol_s} [dim]·[/] [dim]pool[/] {liq_s}"
        )

        fp = fmt_price(fp_price_usd)
        fp_s = f"[dim]FP[/] {fp}" if fp != DASH else f"[dim]FP {DASH}[/]"
        self.query_one("#surf-mkt-parity", Static).update(
            f"  {fp_s} [dim]·[/] {_fmt_parity(parity_pct)}"
        )

        self.query_one("#surf-mkt-price-spark", Static).update(
            f"  [dim]price [/] {_spark(price_series)}"
        )
        supply_points = coerce_points(supply_series)
        last = f" [dim]{fmt_compact(supply_points[-1][1])}[/]" if supply_points else ""
        self.query_one("#surf-mkt-supply-spark", Static).update(
            f"  [dim]supply[/] {_spark(supply_series)}{last}"
        )
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -v`
- [ ] **Prove the coercion test bites:** temporarily replace `coerce_points(series)` in `_spark`
  with `list(series or [])` — `test_market_malformed_series_points_are_skipped_not_fatal` must go
  red (`TypeError` on the `None` point inside `build_sparkline`… which surfaces as the row not
  rendering / the harness raising). Restore, re-run green.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/market.py tests/widgets/test_surf_widgets_a.py && git commit -m "feat(surf): SurfMarket panel with parity and burn-staircase sparkline"`

---

### Task WP3.5: `SurfFeed` — the announce feed, kind badges, width tiers

**Files:**
- Create: `maxpane_dashboard/widgets/surf/feed.py`
- Test: `tests/widgets/test_surf_widgets_b.py` (create)

**Interfaces:**
- Consumes: `_fmt.{fmt_age, hhmm, mmdd, DASH}`, `safe_markup`.
- Produces:
  `SurfFeed(Vertical)` with
  `update_data(feed_nonce=None, feed_last_post_age_s=None, feed_items=None, **_kwargs) -> None`
  — exactly the PRD §5 `feed` keys. `feed_items` item dicts:
  `{ts, kind, from_addr, from_label, text, tx_hash}`; `kind ∈ {"self","reply","action","fund"}`.
  `feed_items=None` → unavailable state; `[]` → "no posts". Module constants
  `FULL_TEXT_WIDTH = 76`, `WIDEN_HINT = "‹ widen"`, `UNAVAILABLE_LINE = "feed unavailable"`,
  `FEED_TITLE = "ANNOUNCE FEED"`;
  module function `_item_lines(item, width) -> tuple[list[str], bool] | None` (pure).

**Panel title — `ANNOUNCE FEED`, pinned as a constant (read before writing `_set_title`).**
The panel title is a cross-WP interface string exactly like the detector labels: PRD §4 names this
panel `ANNOUNCE FEED`, and WP5 asserts `"ANNOUNCE FEED" in text` four times — once in the
all-panels screen test and once in each of the three legs of the `c`-swap test, where it is also
the *negative* assertion that proves the feed is gone when `DEV ACTIVITY` is showing. A bare
`FEED` is not a substring of `ANNOUNCE FEED`, so shortening it fails the swap test in both
directions. Render `ANNOUNCE FEED` and export it as `FEED_TITLE` so WP5 can import the string
rather than duplicate the literal. The title line is `ANNOUNCE FEED · #14 · last 2h ago`
(+ `· unavailable` / `‹ widen` suffixes) — the constant is the head, the decorations append.

- [ ] **Write the failing test.** Create `tests/widgets/test_surf_widgets_b.py`:

```python
"""Headless Textual tests for surf widgets group B (WP3).

Covers ``SurfFeed``, ``SurfDevActivity`` and ``SurfNft``.  Group A lives in
``test_surf_widgets_a.py``; the cross-widget contract sweep in
``test_surf_widget_contract.py``.

Message fixtures are the *real decoded announce-channel calldata* from
``tests/fixtures/surf/captures/announce_eth_txs.json`` -- including nonce 8's
newlines, typographic apostrophes and em-dashes, because the channel is
attacker-writable by design and those characters are already on chain.
Composited-output assertions throughout; zero network.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.surf.feed import (
    FEED_TITLE,
    FULL_TEXT_WIDTH,
    UNAVAILABLE_LINE,
    WIDEN_HINT,
    SurfFeed,
)


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _none_payload(widget) -> dict:
    return {
        name: None
        for name, param in inspect.signature(widget.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }


# -- real decoded channel calldata (announce_eth_txs.json) --------------

_CHANNEL = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"

#: nonce 13, 2026-08-07T04:27:11Z -- 227 chars, one line on chain.
_POST_13 = (
    "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
    "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
    "Hopefully in the coming days will be able to share more what been "
    "working on, as always 0 promises."
)

#: nonce 8, 2026-07-29T00:28:35Z -- raw newlines, ’ and em-dashes on chain.
_POST_8 = (
    "The hook will be highly experimental. I’ll\n  announce it before "
    "moving the LP. I’m also considering limiting trading to NFT holders "
    "for the first few hours—so the risks\n  are clear—then opening it to "
    "everyone. Thoughts?"
)

_FEED_ITEMS = [
    {
        "ts": 1786076831,
        "kind": "self",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": _POST_13,
        "tx_hash": "0xe397869a2ed1299f24618c377112a6e9637395d2c1e21e742ce30e6201440055",
    },
    {
        "ts": 1785795251,
        "kind": "reply",
        "from_addr": "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159",
        "from_label": None,
        "text": (
            "Bro cooked this so hard it smells like my grandma’s pasta sauce "
            "after marinating overnight. Absolute Michelin alpha."
        ),
        "tx_hash": "0xreply1",
    },
    {
        "ts": 1785284915,
        "kind": "self",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": _POST_8,
        "tx_hash": "0x0b72b4640117ecb1ac6adf1ecd1ea61fff94048c11495334966cd34ab003dc72",
    },
    {
        "ts": 1779817691,
        "kind": "action",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": "contract call: register() → ERC-8004 registry",
        "tx_hash": "0xaction1",
    },
    {
        "ts": 1778823923,
        "kind": "fund",
        "from_addr": "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7",
        "from_label": "surfsurf.eth",
        "text": "funded 0.054 ETH from surfsurf.eth",
        "tx_hash": "0x632f5dc3",
    },
]


# ---------------------------------------------------------------------
# SurfFeed
# ---------------------------------------------------------------------


async def test_feed_title_is_the_prd_name_wp5_asserts_on():
    """``ANNOUNCE FEED``, verbatim -- WP5's c-swap test keys on it.

    The swap test asserts the string is present in the feed view and
    *absent* in the activity view, so a shortened title fails it in both
    directions.  Pinned here, in the WP that owns the string.
    """
    assert FEED_TITLE == "ANNOUNCE FEED"


async def test_feed_title_carries_nonce_and_age():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(
            feed_nonce=14, feed_last_post_age_s=7200.0, feed_items=_FEED_ITEMS
        )
        await pilot.pause()
        assert "ANNOUNCE FEED · #14 · last 2h ago" in _screen_text(app)


async def test_feed_kind_badges_render_and_replies_are_not_dev_styled():
    """All four kinds badge in words; a reply never wears the self badge."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "POST" in screen
        assert "REPLY" in screen
        assert "ACTION" in screen
        assert "FUND" in screen
        # The reply's line carries REPLY, not POST (PRD §6.4).
        reply_line = next(l for l in screen.splitlines() if "pasta sauce" in l or "Bro cooked" in l)
        assert "REPLY" in reply_line
        assert "POST" not in reply_line


async def test_feed_wide_tier_shows_the_full_message():
    """At the wide tier the whole 227-char nonce-13 post is on screen."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        assert 120 - 4 >= FULL_TEXT_WIDTH  # this harness IS the wide tier
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "as always 0 promises." in screen      # the tail survived
        assert WIDEN_HINT not in screen


async def test_feed_narrow_tier_truncates_and_advertises_widen():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(60, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "I moved 33 eth" in screen             # the head renders
        assert "as always 0 promises." not in screen  # the tail is cut...
        assert "…" in screen                          # ...visibly
        assert WIDEN_HINT in screen                   # ...and announced


async def test_feed_onchain_newlines_are_flattened_to_one_logical_row():
    """nonce 8 contains raw '\\n  ' -- it must not smuggle in blank rows."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=[_FEED_ITEMS[2]])
        await pilot.pause()
        screen = _screen_text(app)
        # The wrap re-joins across the on-chain newline: the words on either
        # side of "\n  " appear with a single space between them.
        assert "I’ll announce it before moving the LP." in screen.replace("\n", " ")


async def test_feed_markup_hostile_message_cannot_crash_the_pump():
    """Anyone can post to the channel -- including Textual markup."""
    hostile = [
        {
            "ts": 1786076831,
            "kind": "reply",
            "from_addr": "0x" + "ab" * 20,
            "from_label": None,
            "text": "[/x] [bold red]rug[/]  UЅDС  claim at evil.example",
            "tx_hash": "0xhostile",
        }
    ]
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=hostile)
        await pilot.pause()  # a MarkupError would raise here, inside the pump
        screen = _screen_text(app)
        assert "rug" in screen          # rendered literally...
        assert "UЅDС" in screen         # ...homoglyphs and all


async def test_feed_unavailable_vs_empty_are_different_states():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=None, feed_items=None)
        await pilot.pause()
        screen = _screen_text(app)
        assert UNAVAILABLE_LINE in screen

        widget.update_data(feed_nonce=14, feed_items=[])
        await pilot.pause()
        screen = _screen_text(app)
        assert UNAVAILABLE_LINE not in screen
        assert "no posts in window" in screen


async def test_feed_no_args_and_all_none_do_not_raise():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        assert UNAVAILABLE_LINE in _screen_text(app)
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.feed'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/feed.py`
  (seeded from `templates/activity_feed_template.py` via `widgets/fwa/fwa_activity_feed.py` —
  keep the RichLog structure and the re-render-on-resize pattern):

```python
"""The announce-channel feed: decoded posts, classified, honestly styled.

The panel is titled ``ANNOUNCE FEED`` (PRD §4), exported as ``FEED_TITLE``
because the screen WP asserts it against composited output -- including as
the *negative* half of the ``c``-swap test, where its absence is what proves
the dev-activity panel replaced this one.  Import the constant; do not
retype or shorten the string.

One logical row per channel tx, newest first::

    08-07 04:27  POST    I moved 33 eth to the LP on mainnet https://…

Kinds and their styling (classification happens upstream in
``analytics/surf_signals.classify_channel_tx``; this widget renders the
``kind`` string it is given):

* ``self``   -- ``POST`` in cyan: the dev's own broadcast.
* ``reply``  -- ``REPLY`` dim: the channel is permissionless and replies
  are anyone's text.  A reply is never styled like a dev post and its
  links are never highlighted (PRD §6.4).
* ``action`` -- ``ACTION`` in ``$warning``: an outbound contract call
  (the ERC-8004 register() was exactly this shape -- NEW DEPLOY fuel).
* ``fund``   -- ``FUND`` magenta: dev-wallet funding of the channel.

Width tiers: at ``FULL_TEXT_WIDTH`` columns and above the message renders
*in full*, wrapped with a hanging indent -- the feed is the product here,
and the dev's posts are the payload.  Below that, one truncated line per
post with a visible ``…`` and ``‹ widen`` in the title (house rule: a
clipped row is always announced).

On-chain messages contain raw newlines (nonce 8 does today); they are
flattened to single spaces *before* truncation, and ``safe_markup`` runs
**after** all slicing so an escape sequence can never be cut in half.

``feed_items=None`` means the source is dead (explicit unavailable state);
``[]`` means the window is genuinely empty.  Never a blank panel.

Primitives only -- this module imports nothing from the data layer.
"""

from __future__ import annotations

import textwrap

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age, hhmm, mmdd

#: Panel title, PRD §4 spelling.  **Interface**: the screen tests assert this
#: exact string reaches the compositor, and assert its *absence* when the
#: ``c`` key swaps in the dev-activity panel.  Import it, never retype it.
FEED_TITLE = "ANNOUNCE FEED"

#: Columns at or above which messages render in full (wrapped).
FULL_TEXT_WIDTH = 76

#: Marker appended to the title when a message had to be truncated.
WIDEN_HINT = "‹ widen"

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "feed unavailable"

#: Max feed items rendered per refresh.
_MAX_ROWS = 25

#: ``MM-DD HH:MM`` (11) + 2 spaces + badge column (6) + 1 space.
_PREFIX_WIDTH = 20

#: Minimum text budget: below this we stop shrinking and let CSS clip.
_MIN_TEXT_BUDGET = 10

#: badge text + colour per kind.  Unknown kinds render dim ``?``.
_KIND_STYLES = {
    "self": ("POST", "cyan"),
    "reply": ("REPLY", "dim"),
    "action": ("ACTION", "$warning"),
    "fund": ("FUND", "magenta"),
}


def _item_lines(item, width: int) -> tuple[list[str], bool] | None:
    """Render one feed item at ``width`` columns.

    Returns ``(markup_lines, clipped)`` or ``None`` for malformed input.
    Escaping happens after wrapping/truncation, per token, so a cut can
    never bisect an escape sequence.
    """
    if not isinstance(item, dict):
        return None
    try:
        stamp = f"{mmdd(item.get('ts'))} {hhmm(item.get('ts'))}"
        kind = str(item.get("kind") or "").strip().lower()
        badge, color = _KIND_STYLES.get(kind, ("?", "dim"))
        prefix = f"{stamp}  [{color}]{badge:<6}[/] "
        indent = " " * _PREFIX_WIDTH

        # Flatten on-chain newlines/tabs to single spaces first.
        raw = " ".join(str(item.get("text") or "").split())
        budget = max(width - _PREFIX_WIDTH, _MIN_TEXT_BUDGET)

        if width >= FULL_TEXT_WIDTH:
            wrapped = textwrap.wrap(
                raw, budget, break_long_words=False, break_on_hyphens=False
            ) or [""]
            lines = [prefix + safe_markup(wrapped[0])]
            lines += [indent + safe_markup(chunk) for chunk in wrapped[1:]]
            return lines, False

        if len(raw) > budget:
            return [prefix + safe_markup(raw[: budget - 1] + "…")], True
        return [prefix + safe_markup(raw)], False
    except Exception:
        # A single malformed item must never take down the panel.
        return None


class SurfFeed(Vertical):
    """Announce-channel feed with kind badges and width tiers."""

    DEFAULT_CSS = """
    SurfFeed > .surf-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(FEED_TITLE, classes="surf-feed-title", id="surf-feed-title")
        yield Static(" ", classes="surf-feed-spacer")
        yield RichLog(
            id="surf-feed-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(
        self,
        feed_nonce=None,
        feed_last_post_age_s=None,
        feed_items=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log.  Kwargs are exactly the PRD §5 feed keys."""
        self._payload = {
            "nonce": feed_nonce,
            "age_s": feed_last_post_age_s,
            "items": feed_items,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay out: the tier depends on the width."""
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _set_title(self, nonce, age_s, clipped: bool, unavailable: bool) -> None:
        title = self.query_one("#surf-feed-title", Static)
        parts = [FEED_TITLE]
        try:
            parts.append(f"· #{int(nonce)}")
        except (TypeError, ValueError):
            pass
        age = fmt_age(age_s)
        if age != DASH:
            parts.append(f"· last {age} ago")
        if unavailable:
            parts.append("· [yellow]unavailable[/]")
        text = " ".join(parts)
        if clipped:
            text += f"  [yellow]{WIDEN_HINT}[/]"
        title.update(text)

    def _render_view(self) -> None:
        try:
            log = self.query_one("#surf-feed-log", RichLog)
        except Exception:  # not composed yet
            return

        items = self._payload.get("items")
        nonce = self._payload.get("nonce")
        age_s = self._payload.get("age_s")

        width = log.content_size.width
        if width <= 0:
            width = max(self.content_size.width - 2, 0)

        log.clear()
        log.auto_scroll = False

        if items is None:
            # Source dead: explicit state, never a blank panel (PRD §5 meta).
            self._set_title(nonce, age_s, clipped=False, unavailable=True)
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            item_list = [i for i in list(items)[:_MAX_ROWS] if isinstance(i, dict)]
        except TypeError:
            item_list = []

        clipped_any = False
        lines: list[str] = []
        for item in item_list:
            rendered = _item_lines(item, width)
            if rendered is None:
                continue
            item_markup, clipped = rendered
            clipped_any = clipped_any or clipped
            lines.extend(item_markup)

        self._set_title(nonce, age_s, clipped=clipped_any, unavailable=False)
        if not lines:
            log.write("[dim]  no posts in window[/]")
            return
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
- [ ] **Prove the escape bites** (mandatory for decoder-shaped code): in `_item_lines`,
  temporarily replace every `safe_markup(x)` with `x` —
  `test_feed_markup_hostile_message_cannot_crash_the_pump` must go red with a `MarkupError`
  surfacing from `await pilot.pause()` (the deferred message-pump crash). Restore, re-run green.
- [ ] **Prove the truncation order bites:** temporarily swap escape-then-truncate (apply
  `safe_markup(raw)` *before* the `[: budget - 1]` slice). The hostile-message test at narrow
  width may cut `\[` in half — run
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -k hostile -v` plus the narrow
  test; at least one must go red or render a stray backslash. Restore, re-run green.
- [ ] **Prove the title guard bites:** temporarily set `FEED_TITLE = "FEED"`.
  `test_feed_title_is_the_prd_name_wp5_asserts_on` and `test_feed_title_carries_nonce_and_age`
  must both go red — that pair is what stops the four WP5 `ANNOUNCE FEED` assertions (including
  both directions of the `c`-swap test) from breaking on a title tidy-up. Restore, re-run green.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/feed.py tests/widgets/test_surf_widgets_b.py && git commit -m "feat(surf): SurfFeed announce feed with kind badges and width tiers"`

---

### Task WP3.6: `SurfDevActivity` — labels, dimmed unknowns, dust never rendered

**Files:**
- Create: `maxpane_dashboard/widgets/surf/activity.py`
- Test: `tests/widgets/test_surf_widgets_b.py` (append)

**Interfaces:**
- Consumes: `_fmt.{hhmm, mmdd, long_addr, as_float, DASH}`, `safe_markup`.
- Produces:
  `SurfDevActivity(Vertical)` with
  `update_data(dev_activity=None, **_kwargs) -> None` — exactly the PRD §5 `activity` key.
  Row dicts: `{ts, wallet_label, kind, counterparty, counterparty_known, value_eth, tx_hash}`.
  When `counterparty_known` is truthy, `counterparty` carries a **label** from the vendored
  `KNOWN_LABELS` map (resolved upstream by the manager — the widget must NOT import
  `surf_addresses`); when falsy, it carries a raw address rendered dimmed via `long_addr`.
  Module function `_row_markup(row) -> str | None` (pure; `None` = drop the row).
  Drop rules (defense in depth behind the manager's own filter, PRD §6.5):
  `kind == "dust"` → dropped; `kind == "transfer"` **and** unknown counterparty **and** no value →
  dropped (that triple is the poisoning shape).

- [ ] **Write the failing test.** Append to `tests/widgets/test_surf_widgets_b.py`:

```python
# ---------------------------------------------------------------------
# SurfDevActivity
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    SurfDevActivity,
    _row_markup,
)

#: The real 2026-08-07 04:2x staging choreography (ops_eth_token_transfers)
#: plus the two poisoning shapes that live in frenpet.eth's history today.
#:
#: ``wallet_label`` is the **producer's** vocabulary, not an ENS name: WP1
#: fills it from ``_DEV_WALLET_LABELS = {DEV_WALLET: "dev", OPS_WALLET:
#: "ops"}``, WP4 passes it straight through and re-checks it against
#: ``DEV_WALLETS = {"dev": ..., "ops": ...}``.  The ENS spellings live in
#: ``KNOWN_LABELS`` ("dev · surfsurf.eth" / "ops · frenpet.eth") and reach
#: the screen through the *hero*, not through this column.  The rows below
#: are all ops-wallet (frenpet.eth) history except the last, which is the
#: dev wallet (surfsurf.eth) -- hence "ops" / "dev".
_SPOOF = "0xF3083828702C1989710CECA517412071c2f60Ee6"   # 1-gwei lookalike
_REAL_UNKNOWN = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"  # LP-fee ETH dest

_DEV_ACTIVITY = [
    {
        "ts": 1786076603,
        "wallet_label": "ops",
        "kind": "LP",
        "counterparty": "NFPM",
        "counterparty_known": True,
        "value_eth": 33.25,
        "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669",
    },
    {
        "ts": 1786076495,
        "wallet_label": "ops",
        "kind": "bridge",
        "counterparty": "OFT endpoint",
        "counterparty_known": True,
        "value_eth": 0.0,
        "tx_hash": "0xc7acbcc0b164",
    },
    {
        "ts": 1783519943,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _REAL_UNKNOWN,
        "counterparty_known": False,
        "value_eth": 8.0,
        "tx_hash": "0x9ea235039668",
    },
    {  # the poisoning row: zero-value, unknown sender lookalike
        "ts": 1783519000,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _SPOOF,
        "counterparty_known": False,
        "value_eth": 0.0,
        "tx_hash": "0xdust1",
    },
    {  # manager-labelled dust: dropped regardless of any other field
        "ts": 1783518000,
        "wallet_label": "dev",
        "kind": "dust",
        "counterparty": _SPOOF,
        "counterparty_known": False,
        "value_eth": 0.0,
        "tx_hash": "0xdust2",
    },
]


async def test_activity_known_labels_and_values_render():
    """The wallet column renders the producer's label, not an ENS name.

    WP1 emits ``"dev"`` / ``"ops"`` in ``wallet_label`` and WP4 re-checks
    exactly those two keys, so a fixture spelled ``"frenpet.eth"`` would
    certify a column that never appears on screen.  The ENS spellings belong
    to ``KNOWN_LABELS`` and reach the user through the hero's ``owner ✓``
    line instead.
    """
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "ops" in screen
        assert "frenpet.eth" not in screen   # not this column's vocabulary
        assert "NFPM" in screen
        assert "33.250 ETH" in screen
        assert "OFT endpoint" in screen   # known zero-value row still renders


async def test_activity_unknown_addresses_render_long_form_never_shortform():
    """0x+8+…+6 -- the form that distinguishes the live spoof pair."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "0x61CC704c…73f14E" in screen
        # Never the classic first-6/last-4 shortener the spoof collides with.
        assert "0x61CC…f14E" not in screen


async def test_activity_dust_rows_are_never_rendered():
    """The poisoning vector: nothing from either dust row reaches a pixel."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "F3083828" not in screen           # long form absent
        assert "f60Ee6" not in screen             # tail absent too
        assert "dust" not in screen               # not even the kind


def test_activity_row_markup_drop_rules_are_exact():
    """Pure-function check: exactly the poisoning triple is dropped."""
    base = dict(_DEV_ACTIVITY[3])  # zero-value unknown transfer -> dropped
    assert _row_markup(base) is None
    assert _row_markup({**base, "kind": "dust", "value_eth": 5.0}) is None
    # Any leg of the triple broken -> the row renders.
    assert _row_markup({**base, "value_eth": 0.001}) is not None
    assert _row_markup({**base, "counterparty_known": True}) is not None
    assert _row_markup({**base, "kind": "burn"}) is not None
    # Malformed input degrades to a dropped row, never a raise.
    assert _row_markup(None) is None
    assert _row_markup("junk") is None
    assert _row_markup({}) is not None  # renders a dash row, doesn't raise


async def test_activity_markup_hostile_label_cannot_crash_the_pump():
    """Counterparty text is third-party even when 'known' upstream."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(
            dev_activity=[
                {
                    "ts": 1786076603,
                    "wallet_label": "[/x] evil",
                    "kind": "transfer",
                    "counterparty": "[bold]Kraken[/bold]",
                    "counterparty_known": True,
                    "value_eth": 1.0,
                    "tx_hash": "0x1",
                }
            ]
        )
        await pilot.pause()  # MarkupError would surface here
        assert "Kraken" in _screen_text(app)


async def test_activity_unavailable_vs_empty_vs_none_args():
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=None)
        await pilot.pause()
        assert "activity unavailable" in _screen_text(app)

        widget.update_data(dev_activity=[])
        await pilot.pause()
        screen = _screen_text(app)
        assert "no recent activity" in screen
        assert "activity unavailable" not in screen

        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        assert "activity unavailable" in _screen_text(app)
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.activity'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/activity.py`:

```python
"""Recent transactions of both dev wallets, poisoning-defended.

One line per tx, newest first::

    08-07 04:23  ops           lp        NFPM  33.250 ETH
    08-07 04:21  ops           bridge    OFT endpoint
    07-17 04:12  ops           transfer  0x61CC704c…73f14E  8.000 ETH

``wallet_label`` is the producer's two-value vocabulary -- ``"dev"`` /
``"ops"``, from ``surf_client._DEV_WALLET_LABELS``, re-checked by the
manager against the address each label names.  It is deliberately *not* an
ENS name: the ENS spellings live in ``KNOWN_LABELS`` ("dev · surfsurf.eth"
/ "ops · frenpet.eth") and reach the user through the hero's ``owner ✓``
line.  This widget renders whatever string it is handed, so if the labels
should ever read as ENS names that is a change to the producer, not here.

Rendering rules (PRD §4, address-poisoning defense -- live spoofs of both
fee recipients exist in frenpet.eth's history today):

* ``counterparty_known`` truthy -> ``counterparty`` is a label from the
  vendored ``KNOWN_LABELS`` map, resolved upstream; rendered cyan.  The
  map itself lives in ``data/surf_addresses.py`` and is deliberately NOT
  imported here -- widgets receive primitives only.
* unknown -> dimmed ``0x`` + first 8 + ``…`` + last 6, never styled as
  trusted.  The window is wide enough to distinguish the live spoof pair
  (``0xF3084Bc7…D60eE6`` vs ``0xF3083828…f60Ee6``), which the classic
  first-6/last-4 short form is not.
* dust never renders: ``kind == "dust"`` rows are dropped outright, and a
  zero-value ``transfer`` from an unknown counterparty -- exactly the
  poisoning shape -- is dropped even if the manager's own filter missed
  it.  Defense in depth; the manager keys on tx sender (PRD §6.5), this
  widget keys on the rendered row.

``dev_activity=None`` -> explicit unavailable state; ``[]`` -> genuinely
quiet wallets.  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    hhmm,
    long_addr,
    mmdd,
)

#: Max rows rendered per refresh.
_MAX_ROWS = 25

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "activity unavailable"


def _row_markup(row) -> str | None:
    """Format one activity row; ``None`` drops it (malformed or poisonous)."""
    if not isinstance(row, dict):
        return None
    try:
        kind = str(row.get("kind") or "").strip().lower()
        if kind == "dust":
            return None
        known = bool(row.get("counterparty_known"))
        value = as_float(row.get("value_eth"))
        if kind == "transfer" and not known and not value:
            # Zero-value transfer from an unknown counterparty: the
            # address-poisoning shape.  Never rendered (PRD §4).
            return None

        stamp = f"{mmdd(row.get('ts'))} {hhmm(row.get('ts'))}"
        # Pad raw, escape after -- padding an escaped string misaligns it.
        wallet = safe_markup(f"{str(row.get('wallet_label') or DASH)[:12]:<12}")
        kind_cell = safe_markup(f"{(kind or DASH)[:8]:<8}")
        if known:
            who = f"[cyan]{safe_markup(str(row.get('counterparty') or DASH))}[/]"
        else:
            who = f"[dim]{safe_markup(long_addr(row.get('counterparty')))}[/]"
        amount = f"  {value:,.3f} ETH" if value else ""
        return f"{stamp}  [bold]{wallet}[/]  [dim]{kind_cell}[/]  {who}{amount}"
    except Exception:
        # A single malformed row must never take down the panel.
        return None


class SurfDevActivity(Vertical):
    """Feed of both dev wallets' recent transactions."""

    DEFAULT_CSS = """
    SurfDevActivity > .surf-activity-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfDevActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("DEV ACTIVITY", classes="surf-activity-title", id="surf-act-title")
        yield Static(" ", classes="surf-activity-spacer")
        yield RichLog(
            id="surf-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(self, dev_activity=None, **_kwargs) -> None:
        """Rewrite the log.  ``dev_activity`` is the PRD §5 activity key."""
        try:
            log = self.query_one("#surf-activity-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        if dev_activity is None:
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            rows = list(dev_activity)[:_MAX_ROWS]
        except TypeError:
            rows = []

        lines = [m for m in (_row_markup(row) for row in rows) if m is not None]
        if not lines:
            log.write("[dim]  no recent activity[/]")
            return
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
- [ ] **Prove the dust filter bites** (mandatory — this is the security-shaped code): comment out
  the `if kind == "dust": return None` line **and** the poisoning-triple `return None` in
  `_row_markup` — `test_activity_dust_rows_are_never_rendered` and
  `test_activity_row_markup_drop_rules_are_exact` must both go red. Restore each separately,
  confirming each test catches its own condition, then re-run green.
- [ ] **Report the `wallet_label` vocabulary to WP5** in your final summary (do not edit their
  file): WP5's `_sample_data()` `dev_activity` rows still spell `wallet_label` as
  `"frenpet.eth"` / `"surfsurf.eth"`, but the producer emits `"dev"` / `"ops"`
  (`surf_client._DEV_WALLET_LABELS`, re-checked by `SurfManager` against `DEV_WALLETS`). Their
  screen fixture should move to `"dev"` / `"ops"` so it renders what the live dashboard renders.
  If the *product* decision is that this column should show ENS names, that is a change to WP1's
  `_DEV_WALLET_LABELS`, not a fixture edit here — raise it, do not encode the disagreement.
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/activity.py tests/widgets/test_surf_widgets_b.py && git commit -m "feat(surf): SurfDevActivity with label allowlist and dust-row defense"`

---

### Task WP3.7: `SurfNft` — IDMD stats, honest floor, last sales, package re-exports

**Files:**
- Create: `maxpane_dashboard/widgets/surf/nft.py`
- Edit: `maxpane_dashboard/widgets/surf/__init__.py` (the re-export block deferred from WP3.1 —
  `nft.py` is the last of the six submodules, so this is the first task where it can be written)
- Test: `tests/widgets/test_surf_widgets_b.py` (append)

**Interfaces:**
- Consumes: `_fmt.{mmdd, as_float, DASH}`, `safe_markup`.
- Produces:
  `SurfNft(Vertical)` with
  `update_data(nft_holders=None, nft_transfers_24h=None, nft_dev_holdings=None, nft_written=None, nft_last_sales=None, nft_floor=None, **_kwargs) -> None`
  — exactly the PRD §5 `nft` keys. `nft_last_sales` item dicts: `{ts, token_id, eth}`.
  Module constant `FLOOR_UNAVAILABLE = "n/a — no keyless source"` (tested verbatim; PRD §5
  pins `nft_floor` to `None` in v1 and this string is the required rendering).

- [ ] **Write the failing test.** Append to `tests/widgets/test_surf_widgets_b.py`:

```python
# ---------------------------------------------------------------------
# SurfNft
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.nft import (  # noqa: E402
    FLOOR_UNAVAILABLE,
    SurfNft,
)

#: identity_counters.json (667 holders), research (38 transfers/day, dev
#: holds 3, 1/2000 written).
#:
#: The sales are the **only** realized IDMD prices anyone has decoded: both
#: legs of the dev wallet's Seaport purchase ``0x5b4d1b44...eadad2`` at ts
#: 1786163591 -- token 1751 at 0.18 ETH and token 354 at 0.1838989 ETH,
#: whose realized values sum to the transaction's own ``value`` exactly
#: (WP1 §"One real Seaport purchase").  They are decoded from that tx's
#: ``OrderFulfilled`` logs, *not* from ``identity_transfers_page1.json``:
#: WP0.7's ``test_no_idmd_transfer_row_carries_a_price`` pins that no row of
#: that capture carries a price at all, so a price attributed to one would
#: be invented -- which is what the header of this file promises not to do.
_FULL_NFT = {
    "nft_holders": 667,
    "nft_transfers_24h": 38,
    "nft_dev_holdings": 3,
    "nft_written": 1,
    "nft_last_sales": [
        {"ts": 1786163591, "token_id": 1751, "eth": 0.18},
        {"ts": 1786163591, "token_id": 354, "eth": 0.1838989},
    ],
    "nft_floor": None,  # pinned None in v1 (PRD §5)
}


async def test_nft_full_payload_renders_stats_and_sales():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)
        assert "667" in screen and "holders" in screen
        assert "38" in screen and "transfers/24h" in screen
        assert "dev holds 3" in screen
        assert "1/2000 written" in screen
        # Both legs of the one real Seaport fill, at three decimals.
        assert "#1751" in screen and "0.180 ETH" in screen
        assert "#354" in screen and "0.184 ETH" in screen


async def test_nft_floor_is_the_explicit_unavailable_state_never_a_number():
    """No keyless floor source exists; the UI says so (PRD §5 nft_floor)."""
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)
        assert FLOOR_UNAVAILABLE in screen
        assert "floor 0" not in screen           # never faked as zero

        # v2 escape hatch: if a float ever arrives, render it -- with units.
        # 0.25 is a *hypothetical* v2 value, deliberately not one of the two
        # realized prices above, so this assertion cannot be satisfied by a
        # sale line; there is no keyless floor source to take a real one from.
        widget.update_data(**{**_FULL_NFT, "nft_floor": 0.25})
        await pilot.pause()
        screen = _screen_text(app)
        assert "0.250 ETH" in screen
        assert FLOOR_UNAVAILABLE not in screen


async def test_nft_sales_unavailable_vs_empty():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**{**_FULL_NFT, "nft_last_sales": None})
        await pilot.pause()
        assert "sales unavailable" in _screen_text(app)

        widget.update_data(**{**_FULL_NFT, "nft_last_sales": []})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no sales in window" in screen
        assert "sales unavailable" not in screen


async def test_nft_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        # A dead Blockscout is not a collection with zero holders.
        assert "0 holders" not in screen
        assert f"{FLOOR_UNAVAILABLE}" in screen
        assert "--" in screen


async def test_nft_malformed_sale_rows_are_skipped():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(
            **{
                **_FULL_NFT,
                "nft_last_sales": [
                    None,
                    "junk",
                    {"ts": None, "token_id": None, "eth": None},
                    {"ts": 1786163591, "token_id": 1751, "eth": 0.18},
                ],
            }
        )
        await pilot.pause()
        assert "#1751" in _screen_text(app)
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
  Expected: `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.surf.nft'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/widgets/surf/nft.py`:

```python
"""IDMD NFT panel: holders, velocity, identities, honest floor, last sales.

Rows: title · stats · written · floor · last-sales block.

**The floor line is the honesty flagship.**  There is no keyless floor
source for IDMD (OpenSea is keyed/Cloudflare-gated -- game_mechanics
§recipes), so PRD §5 pins ``nft_floor`` to ``None`` in v1 and this widget
renders the explicit ``n/a — no keyless source`` state.  It is never
faked, never ``0``, never silently blank.  If a future version ships a
real source and hands us a float, it renders with units -- the escape
hatch costs nothing today.

Realized Seaport sales (``nft_last_sales``) are the closest keyless proxy
and get their own block: ``MM-DD  #token  x.xxx ETH``.  Those prices come
from decoded ``OrderFulfilled`` logs, not from the ERC-721 transfer list --
a transfer row carries a token id and nothing about money, which is why
``nft_last_sales[].eth`` is the manager's job and not a field this widget
can synthesise when it is missing.  A sale row without a usable ``eth`` is
skipped, never rendered at ``0.000``.

``None`` scalars render ``--``; a dead Blockscout is not a collection
with zero holders.  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, mmdd

#: The explicit floor state.  Tested verbatim (PRD §5 nft group).
FLOOR_UNAVAILABLE = "n/a — no keyless source"

#: Sales lines rendered at most.
_MAX_SALES = 4


def _fmt_count(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return DASH


def _sale_line(sale) -> str | None:
    """``08-08  #1821  0.219 ETH`` or ``None`` for a malformed row."""
    if not isinstance(sale, dict):
        return None
    try:
        token = int(sale["token_id"])
        eth = float(sale["eth"])
    except (KeyError, TypeError, ValueError):
        return None
    return f"  [dim]{mmdd(sale.get('ts'))}[/]  #{token}  [bold]{eth:.3f} ETH[/]"


class SurfNft(Vertical):
    """IDMD collection panel."""

    DEFAULT_CSS = """
    SurfNft > .surf-nft-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfNft > .surf-nft-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("IDMD NFT", classes="surf-nft-title")
        yield Static("", classes="surf-nft-line", id="surf-nft-spacer")
        yield Static("", classes="surf-nft-line", id="surf-nft-stats")
        yield Static("", classes="surf-nft-line", id="surf-nft-written")
        yield Static("", classes="surf-nft-line", id="surf-nft-floor")
        yield Static("", classes="surf-nft-line", id="surf-nft-sales-head")
        yield Static("", classes="surf-nft-line", id="surf-nft-sales")

    def update_data(
        self,
        nft_holders=None,
        nft_transfers_24h=None,
        nft_dev_holdings=None,
        nft_written=None,
        nft_last_sales=None,
        nft_floor=None,
        **_kwargs,
    ) -> None:
        """Refresh all rows.  Kwargs are exactly the PRD §5 nft keys."""
        self.query_one("#surf-nft-stats", Static).update(
            f"  [bold]{_fmt_count(nft_holders)}[/] [dim]holders ·[/] "
            f"[bold]{_fmt_count(nft_transfers_24h)}[/] [dim]transfers/24h ·[/] "
            f"[dim]dev holds[/] [bold]{_fmt_count(nft_dev_holdings)}[/]"
        )

        written = _fmt_count(nft_written)
        self.query_one("#surf-nft-written", Static).update(
            f"  [dim]identities[/] [bold]{written}[/][dim]/2000 written[/]"
            if written != DASH
            else f"  [dim]identities {DASH}/2000 written[/]"
        )

        floor = as_float(nft_floor)
        if floor is None:
            floor_markup = f"  [dim]floor[/] [yellow]{FLOOR_UNAVAILABLE}[/]"
        else:
            floor_markup = f"  [dim]floor[/] [bold]{floor:.3f} ETH[/]"
        self.query_one("#surf-nft-floor", Static).update(floor_markup)

        sales_head = self.query_one("#surf-nft-sales-head", Static)
        sales_body = self.query_one("#surf-nft-sales", Static)
        if nft_last_sales is None:
            sales_head.update("  [dim]last sales[/]")
            sales_body.update("  [yellow]⚠ sales unavailable[/]")
            return
        try:
            rows = list(nft_last_sales)[:_MAX_SALES]
        except TypeError:
            rows = []
        lines = [l for l in (_sale_line(s) for s in rows) if l is not None]
        sales_head.update("  [dim]last sales (Seaport)[/]")
        sales_body.update("\n".join(lines) if lines else "  [dim]no sales in window[/]")
```

  Note the `/2000` denominator: same justification as `SurfHero` — the IDMD cap is minted out on
  an ownership-bricked contract (`identity_token.json` `total_supply: 2000`), immutable, so it is
  not a "documented live value".

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
- [ ] **Prove the floor test bites:** temporarily change the `if floor is None:` branch to render
  `f"  [dim]floor[/] [bold]0.000 ETH[/]"` —
  `test_nft_floor_is_the_explicit_unavailable_state_never_a_number` must go red. Restore,
  re-run green.

- [ ] **Write the failing re-export test.** All six submodules now exist, so the package root can
  finally become the import surface. Append to `tests/widgets/test_surf_widgets_b.py`:

```python
# ---------------------------------------------------------------------
# Package surface
# ---------------------------------------------------------------------


def test_package_root_reexports_the_six_widget_classes():
    """``from maxpane_dashboard.widgets.surf import SurfHero`` must work.

    This is the house pattern (``widgets/ttt/__init__.py``,
    ``widgets/talismans/__init__.py``, and ``screens/fwa.py`` importing from
    ``maxpane_dashboard.widgets.fwa``), and it is the surface the screen WP
    imports from -- both ``screens/surf.py`` and its screen test spell
    ``from maxpane_dashboard.widgets.surf import (SurfDevActivity, SurfFeed,
    SurfHero, SurfMarket, SurfNft, SurfSignals)``.  A bare-docstring
    ``__init__.py`` turns both of those into ``ImportError``, and this file
    owns ``__init__.py``, so the guard belongs here.
    """
    import maxpane_dashboard.widgets.surf as pkg

    from maxpane_dashboard.widgets.surf import (
        DETECTOR_LABELS,
        FEED_TITLE,
        FLOOR_UNAVAILABLE,
        SurfDevActivity,
        SurfFeed,
        SurfHero,
        SurfMarket,
        SurfNft,
        SurfSignals,
    )

    classes = (SurfHero, SurfSignals, SurfFeed, SurfDevActivity, SurfMarket, SurfNft)
    for cls in classes:
        assert cls.__name__ in pkg.__all__, cls.__name__
        assert getattr(pkg, cls.__name__) is cls
    # The three rendered interface strings ride along, so consumers never
    # retype them (see the deliverable summary).
    assert DETECTOR_LABELS[0] == "NEW POST"
    assert FEED_TITLE == "ANNOUNCE FEED"
    assert FLOOR_UNAVAILABLE.startswith("n/a")
```

- [ ] **Run it and state the expected failure.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -k reexports -v`
  Expected: `ImportError: cannot import name 'SurfHero' from 'maxpane_dashboard.widgets.surf'`.

- [ ] **Minimal implementation.** Replace `maxpane_dashboard/widgets/surf/__init__.py` (created
  docstring-only in WP3.1) with the full re-export block, shaped exactly like
  `maxpane_dashboard/widgets/ttt/__init__.py`:

```python
"""Widgets for the surf dashboard (surfsurf.eth mission control).

Six render-only widgets, one per PRD §5 panel group:

======================  ===================================================
Widget                  Slot in ``screens/surf.SurfScreen``
======================  ===================================================
``SurfHero``            hero row, left (3fr) -- experiment status
``SurfSignals``         hero row, right (2fr) -- the six detectors
``SurfFeed``            middle row -- announce channel (``c`` swaps it out)
``SurfDevActivity``     middle row -- dev wallets (``c`` swaps it in)
``SurfMarket``          bottom row, left -- price, parity, supply
``SurfNft``             bottom row, right -- IDMD collection
======================  ===================================================

The classes are re-exported here because the package root is the import
surface the screen and its tests use, exactly as ``widgets/ttt`` and
``widgets/talismans`` do it and as ``screens/fwa.py`` consumes
``maxpane_dashboard.widgets.fwa``.

``DETECTOR_LABELS``, ``FEED_TITLE`` and ``FLOOR_UNAVAILABLE`` ride along:
they are *rendered interface strings* asserted against composited output by
the screen WP and by the app-level acceptance tests, so consumers import
them instead of retyping the literals.

These widgets take primitives only and import nothing from ``data/`` or
``analytics/``, so this package is safe to import with no manager, no cache
and no network present (pinned by ``tests/widgets/test_surf_widget_contract.py``).
"""

from .activity import SurfDevActivity
from .feed import FEED_TITLE, SurfFeed
from .hero import SurfHero
from .market import SurfMarket
from .nft import FLOOR_UNAVAILABLE, SurfNft
from .signals import DETECTOR_LABELS, SurfSignals

__all__ = [
    "DETECTOR_LABELS",
    "FEED_TITLE",
    "FLOOR_UNAVAILABLE",
    "SurfDevActivity",
    "SurfFeed",
    "SurfHero",
    "SurfMarket",
    "SurfNft",
    "SurfSignals",
]
```

- [ ] **Run to green:** `.venv/bin/python -m pytest tests/widgets/test_surf_widgets_b.py -v`
- [ ] **Prove there is no import cycle:** `.venv/bin/python -c "import maxpane_dashboard.widgets.surf as p; print(sorted(p.__all__))"`
  must print the nine names without raising. (`__init__` imports `.hero`, which imports
  `maxpane_dashboard.widgets.surf._fmt` by absolute path while the package is still
  initialising — legal, because the partially-built package module is already in `sys.modules`,
  but worth one command to prove rather than assume.)
- [ ] **Commit:**
  `git add maxpane_dashboard/widgets/surf/nft.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_widgets_b.py && git commit -m "feat(surf): SurfNft panel with honest no-keyless-floor state + package re-exports"`

---

### Task WP3.8: Cross-widget contract sweep — SURF_KEYS conformance, import hygiene, full suite

**Files:**
- Create: `tests/widgets/test_surf_widget_contract.py`
- Test: same file.

**Interfaces:**
- Consumes: `data.surf_models.SURF_KEYS` (WP0 — the only WP3 test that touches another WP's
  module; it runs the parallel-agent interface check), all six widget classes.
- Produces: nothing new — this task pins the contract.

- [ ] **Write the failing-or-green test.** Create `tests/widgets/test_surf_widget_contract.py`:

```python
"""Cross-widget contract tests for the surf dashboard (WP3).

Three structural guarantees, one place:

1. Every ``update_data`` kwarg of every surf widget is a key of the frozen
   PRD §5 contract (``data/surf_models.SURF_KEYS``) -- the screen splats
   the manager dict at each widget, so a stray kwarg is a silent no-op and
   a typo'd one never receives data.
2. Widget modules import nothing from ``maxpane_dashboard.data`` or
   ``maxpane_dashboard.analytics`` -- primitives only, and the structural
   proof that widgets cannot touch the network.
3. No-args and all-``None`` ``update_data`` calls never raise, for all six
   widgets in one sweep, asserted against composited output.
"""

from __future__ import annotations

import ast
import inspect

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.data.surf_models import SURF_KEYS

# Package root, not submodule paths: this is the surface ``screens/surf.py``
# and its screen test import from (WP5), so the contract sweep exercises it.
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

_WIDGETS = (SurfHero, SurfSignals, SurfFeed, SurfDevActivity, SurfMarket, SurfNft)


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _kwargs_of(cls) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(cls.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    )


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
def test_update_data_kwargs_are_frozen_contract_keys(cls):
    """Every kwarg is a PRD §5 key -- the screen can splat the flat dict."""
    unknown = [k for k in _kwargs_of(cls) if k not in SURF_KEYS]
    assert not unknown, f"{cls.__name__} takes non-contract kwargs: {unknown}"


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
def test_every_widget_accepts_the_whole_flat_dict(cls):
    """``**_kwargs`` is present, so foreign contract keys are ignored."""
    has_var_kw = any(
        p.kind is p.VAR_KEYWORD
        for p in inspect.signature(cls.update_data).parameters.values()
    )
    assert has_var_kw, f"{cls.__name__}.update_data lacks **_kwargs"


def test_widget_modules_import_no_data_layer_and_no_analytics():
    """Primitives only -- also the structural no-network proof."""
    import maxpane_dashboard.widgets.surf._fmt as fmt_mod
    import maxpane_dashboard.widgets.surf.activity as act_mod
    import maxpane_dashboard.widgets.surf.feed as feed_mod
    import maxpane_dashboard.widgets.surf.hero as hero_mod
    import maxpane_dashboard.widgets.surf.market as mkt_mod
    import maxpane_dashboard.widgets.surf.nft as nft_mod
    import maxpane_dashboard.widgets.surf.signals as sig_mod

    for module in (fmt_mod, hero_mod, sig_mod, feed_mod, act_mod, mkt_mod, nft_mod):
        tree = ast.parse(inspect.getsource(module))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for name in imported:
            assert "maxpane_dashboard.data" not in name, (module.__name__, name)
            assert "analytics" not in name, (module.__name__, name)
            assert "surf_addresses" not in name, (module.__name__, name)
            assert "surf_client" not in name, (module.__name__, name)
            assert "httpx" not in name and "aiohttp" not in name, (module.__name__, name)


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
async def test_no_args_and_all_none_render_without_raising(cls):
    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=(120, 20)) as pilot:
        widget.update_data()
        widget.update_data(
            **{
                name: None
                for name, param in inspect.signature(widget.update_data).parameters.items()
                if param.kind is not param.VAR_KEYWORD and name != "self"
            }
        )
        # Pump the message loop: deferred MarkupErrors surface here or never.
        await pilot.pause()
        screen = _screen_text(app)
        assert screen.strip(), f"{cls.__name__} rendered an empty screen"
        assert "Loading" not in screen
```

- [ ] **Run it and state the expected outcome.**
  `.venv/bin/python -m pytest tests/widgets/test_surf_widget_contract.py -v`
  Expected: **green if WP0 has landed** (all six widgets exist by now and their kwargs were chosen
  from PRD §5). If it fails on `from maxpane_dashboard.data.surf_models import SURF_KEYS` with
  `ModuleNotFoundError`, WP0 has not merged yet — this is the one legitimate wait-state in WP3;
  park this task, do not stub `surf_models` yourself (one owner per file). If it fails on a
  kwarg mismatch, the widget is wrong, not the contract — fix the widget.
- [ ] **Prove the kwarg test bites:** temporarily rename `SurfMarket.update_data`'s
  `imd_price_usd` kwarg to `imd_price` —
  `test_update_data_kwargs_are_frozen_contract_keys[SurfMarket]` must go red. Restore, re-run.
- [ ] **Run the whole widget suite plus the full suite:**
  `.venv/bin/python -m pytest tests/widgets/ -v` then `.venv/bin/python -m pytest`
  Both must be green (the full run proves no existing dashboard's tests were disturbed —
  WP3 touched no shared file, so any red here is a finding to report, not to fix).
- [ ] **Commit:**
  `git add tests/widgets/test_surf_widget_contract.py && git commit -m "test(surf): widget contract sweep - SURF_KEYS conformance, import hygiene, None-safety"`

---

## Deliverable summary for the integrating WPs

The screen WP (owner of `screens/surf.py`) composes and dispatches with:

```python
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

# dispatch: every widget accepts the whole manager dict
for widget in (...):
    widget.update_data(**payload)
```

**Import from the package root, not from the submodules.** WP3.7 re-exports all six classes (and
`DETECTOR_LABELS`, `FEED_TITLE`, `FLOOR_UNAVAILABLE`) from `widgets/surf/__init__.py`, the same
shape `widgets/ttt/__init__.py` and `widgets/talismans/__init__.py` use and the same surface
`screens/fwa.py:94` consumes. Submodule paths still work and remain correct for the two names that
are deliberately *not* re-exported — `hero.HOOK_NOT_LIVE` / `hero.HOOK_LAUNCHED`,
`feed.FULL_TEXT_WIDTH`, `feed.UNAVAILABLE_LINE`, `activity.UNAVAILABLE_LINE`, the two
`WIDEN_HINT`s — because those are panel-local constants, not the shared widget surface.

All six `update_data` signatures consume PRD §5 keys only (pinned by
`test_surf_widget_contract.py`); unavailability contracts: `feed_items=None` /
`dev_activity=None` / `nft_last_sales=None` → explicit unavailable states, `[]` → explicit
empty states, `None` scalars → dashes. Constants other WPs may reference:
`feed.FULL_TEXT_WIDTH = 76`, `feed.WIDEN_HINT` / `signals.WIDEN_HINT = "‹ widen"`,
`feed.UNAVAILABLE_LINE = "feed unavailable"`, `activity.UNAVAILABLE_LINE = "activity unavailable"`,
`nft.FLOOR_UNAVAILABLE = "n/a — no keyless source"`.

**Rendered interface strings — import these, do not retype them.** Two of them are asserted
against composited output by the screen WP and by the app-level acceptance tests, so they are
frozen here rather than in the consumers:

```python
from maxpane_dashboard.widgets.surf import DETECTOR_LABELS, FEED_TITLE, FLOOR_UNAVAILABLE

DETECTOR_LABELS   # ("NEW POST", "LP MIGRATION", "GATE OPEN",
                  #  "NEW DEPLOY", "BRIDGE STAGE", "BURN")  -- PRD §3 order
FEED_TITLE        # "ANNOUNCE FEED"     -- PRD §4
FLOOR_UNAVAILABLE # "n/a — no keyless source"  -- PRD §5 nft_floor
```

- The detector labels are **never abbreviated for width**. They render in full at every width;
  because the label leads its row, an over-long row loses its detail tail to `text-overflow:
  ellipsis` and the label still reaches the compositor. The extra columns land in the screen WP's
  `SURF_FULL_LAYOUT_COLUMNS` measurement, which is the right place for them.
- `FEED_TITLE` is the *head* of the panel title; `#nonce`, `last Nh ago`, `· unavailable` and
  `‹ widen` are appended after it, so `FEED_TITLE in title` holds in every state — including the
  negative assertion in the `c`-swap test (feed shown ⇒ present, activity shown ⇒ absent).
- Panel titles for the other four widgets, for the same substring assertions: `SIGNALS`,
  `DEV ACTIVITY`, `IMD MARKET`, `IDMD NFT`. (The market panel is titled `IMD MARKET`; a screen
  test asserting the bare substring `MARKET` still passes. `SIGNALS` gains a `‹ widen` suffix
  when a detector row is clipped, so assert it as a substring, not as an equality.)

One contract note for the screen WP: `imd_burned_cum` is **observation-scoped** — the burn this
install has seen since its first successful supply read, not an all-time total (WP4.5; WP4 open
issue 4). `SurfHero` renders it as `burned {n:,.0f} observed`, `no burn observed yet` for `0.0`,
and a dash for `None`. Screen-level fixtures must therefore carry a plausible *observed* value
(e.g. `15_745.0`, the single 2026-08-05 event) — **not** the historical `58_848.0` of PRD §1,
which the manager cannot produce and which pins copy the widget deliberately does not print.
