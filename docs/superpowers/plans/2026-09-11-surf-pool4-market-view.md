> **Historical (2026-09-18).** Build-time record; its suite timings ("~11 min") are withdrawn — see `docs/decisions.md`.

# surf `4` POOL4 MARKET view — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth surf body on key `4` — a user-oriented POOL4 market view on the bakery template — without touching the existing `p` auditor body.

**Architecture:** A new hidden body composed at startup and toggled by `_show_mode`, plus a **second hero** swapped with it (curator's existing per-mode hero pattern). Roughly two-thirds of the data is re-presented from the 62 keys `TIER_POOL4` already produces; the delta is four fast-tier reads, one long-tier `Transfer` sweep on its own cache slot, and one pure analytics module for the depth ladder.

**Tech Stack:** Python 3.11, Textual, httpx (data layer only), pytest. No new dependencies.

**Spec:** `docs/surf_pool4_market_PRD.md` — read it before starting. Every task below argues from it and cites sections.

## Global Constraints

Copied verbatim from CLAUDE.md and the spec. **Every task's requirements implicitly include this section.**

- **Strictly read-only.** No signer, no transactor, no nonce manager, no keystore, no calldata for a state change. If a task seems to need one, the task is wrong.
- **Keyless.** Every data source works with no API key of any kind.
- **No test may touch the network.** Assert it structurally — inject a transport that raises on use. Every external payload is a committed fixture under `tests/fixtures/`.
- **Read values live; never hardcode a documented one.** A constant that agrees with the chain today is not evidence for the constant.
- **A failed read is `None`, never `0`.** Never write a sentinel into a history series.
- **Inject the clock.** No module a test needs to control may call `time.time()` internally.
- **Escape every third-party string** before markup or a `DataTable` (`widgets/markup_safety.safe_markup`); a widget rendering third-party text through `Static` hands it a pre-built `rich.text.Text`, never a markup string.
- **Widgets may import pure `analytics/` modules; they may not import `data/`.**
- **Assert against composited output** (`_compositor.render_strips()`), never a content string.
- **Prove a test bites.** Mutate the code, watch the test go red, confirm *which* test reddened, restore.
- **Run only your own test files.** Never the full suite — a neighbour mid-edit reddens it for a reason that is not yours. Use `.venv/bin/python -m pytest`, never system `python3`.
- **Report defects in other agents' files; do not fix them.**
- **Never `git checkout --` a file.** The working tree may hold uncommitted user work.

### Names frozen by WP0 — do not invent variants

| name | meaning |
|---|---|
| `MODE_POOL4_USER` | the new mode word |
| `POOL4_USER_BODY_ID` | `"surf-pool4-user-body"` |
| `POOL4_STAKERS_KEYS` | long-tier key tuple |
| `TIER_POOL4_STAKERS`, `SLOT_POOL4_STAKERS` | the sweep's tier and slot |
| `pool4_reference_pool_tick`, `pool4_venue_gap_pct` | cross-venue keys — **never** `pool4_ref_tick`, which already means the hook's internal lagged tick |
| `pool4_trailing_return_pct` | realised return — **never** reuse `pool4_implied_apr_pct`, the delivery cap |

---

## File Structure

**Created:**

| file | responsibility |
|---|---|
| `maxpane_dashboard/analytics/surf_pool4_depth.py` | pure depth-ladder math; stdlib only |
| `maxpane_dashboard/data/surf_pool4_market.py` | pure folds: venue gap, trailing return, staker concentration |
| `maxpane_dashboard/widgets/surf/pool4u_hero.py` | the three repurposed hero cards |
| `maxpane_dashboard/widgets/surf/pool4u_stakers.py` | STAKERS leaderboard |
| `maxpane_dashboard/widgets/surf/pool4u_burn.py` | BURN & SUPPLY sparkline |
| `maxpane_dashboard/widgets/surf/pool4u_signals.py` | SIGNALS + state summary |
| `maxpane_dashboard/widgets/surf/pool4u_depth.py` | IF IMD FALLS table |

**Modified — one owner each, named in the task:**

| file | owner |
|---|---|
| `maxpane_dashboard/data/surf_models.py` | WP0 only |
| `maxpane_dashboard/data/surf_cache.py` | WP0 only |
| `maxpane_dashboard/data/surf_pool4_client.py` | WP2 only |
| `maxpane_dashboard/data/surf_manager.py` | WP6 only |
| `maxpane_dashboard/screens/surf.py` | WP7 only |
| `maxpane_dashboard/themes/minimal.tcss` | WP7 only |
| `CLAUDE.md`, `README.md`, `.claude/skills/terminal-layout/SKILL.md` | WP10 only |

**Reused unchanged — do not copy, do not edit:** `widgets/surf/pool4_flow.py` (RECENT FLOW), `widgets/sparkline_common.py`, `widgets/markup_safety.py`.

## Expected red — five tripwires, and the trap they set

**Landed by WP0 (`b55ae5f`) and NOT closable until WP7 and WP9.** WP0 grew `SURF_KEYS` by 13 names
whose widgets do not exist yet, and this repo has six completeness tripwires that fire the instant a
payload key exists with no renderer:

| test | closed by |
|---|---|
| `tests/data/test_surf_pool4_models.py::test_every_pool4_key_has_at_least_one_renderer` | WP9 |
| `tests/test_surf_registration.py::test_every_surf_key_is_triaged_for_the_zero_catch` | WP7 |
| `tests/test_surf_registration.py::test_no_surf_key_is_still_waiting_for_a_consumer` | WP7 |
| `tests/screens/test_surf_screen.py::test_surf_keys_covers_the_local_signature_map` | WP7 |
| `tests/screens/test_surf_screen.py::test_screen_dispatches_every_data_key` | WP7 |
| `tests/data/test_surf_models.py::test_surf_keys_is_exactly_the_prd_contract` | WP7 |

**The sixth was missed when this table was first written** (found by WP2+3+4, verified). It differs
from the other five: it is not a "has a renderer" check but a hardcoded `EXPECTED_KEYS` set with a
count in its docstring reading `144 = 82 + 62`. **WP7 must grow both the set and that arithmetic by
13** — the five above close by wiring, this one closes by editing the expectation, and an agent that
only wires will leave it red.

**These six staying red is the tripwire working. Do not "fix" them.** Verified red for exactly this
reason and no other: all six name the same 13 keys.

**The trap, and why it is named here rather than left to be discovered.** The obvious way to quiet
them is to add entries to `POOL4_WIDGET_SIGNATURES`. **That is not available and must not be
attempted**: `tests/screens/test_surf_screen.py:7613` does `cls = _ALL_WIDGET_CLASSES[panel]`, so a
signature naming a widget class that does not exist raises `KeyError`, and `:7567` cross-checks the
name set against the screen's real panels. Parking the keys in `_KEYS_PENDING_CONSUMERS` is refused
too — `tests/test_surf_registration.py:1886-1897` builds `triaged` deliberately *without* that bucket.

If you are an agent on any package other than WP7 or WP9 and one of these five is red, that is the
expected state of the branch. Report it; do not touch it.

## Carry-overs from wave 2 — assigned, not floating

Found by the agents, verified, and each given an owner. None is optional.

**C1 — `pool4_backstop_distance_pct` and `pool4_burn_points` never existed. → WP9 (first) / WP5 done.**
This plan's own self-review said "WP6 owns them". That was the wrong cure: they were never added to
WP0's frozen contract, and `test_surf_widget_contract.py:274` refuses any kwarg not in `SURF_KEYS`, so
WP6 could not have dispatched them whatever it did. WP5 derived both in-widget instead and documented
why. **Do not add the keys now.** Instead WP9 hoists the tick→percent conversion into
`analytics/surf_pool4_depth.py` (which already owns that math) as `band_distance_pct`, and
`pool4u_hero.py` imports it — one source, not two. The burn fold stays in `pool4u_burn.py`: WP5
rejected `supply_series` because it is the surf fast tier's **mainnet** IMD supply while this body can
render Sepolia, and a `· SEPOLIA` title over a mainnet series is the exact defect the network word
exists to prevent. Keep that reasoning in the docstring.

**C2 — the staker row shape is specified two ways. → WP6.**
`surf_pool4_market.staker_rows` emits `address`; `surf_models.py:1394` comments the shape as
`rank/addr/imd/pct`. WP5 reads `address` with an `addr` fallback so the column cannot go blank.
**`address` wins** — it is what the producer actually emits. WP6 fixes the comment and adds the
`SURF_ROW_KEYS` entry; the widget's fallback is then dead and WP9 deletes it.

**C3 — five new widgets escape three shared checks. → WP9.**
`tests/widgets/test_surf_pool4_shared.py:40` globs `pool4_*.py`, which does **not** match
`pool4u_*.py` (verified). The theme-token check, the "no local `network_word`" check and the
`_pool4`-import check therefore do not reach any `4`-body widget. **Widen the glob to `pool4*.py`**
and confirm it then discovers all eight modules. WP5 wrote local equivalents; delete them once the
glob covers them, or the duplication becomes the divergence this repo keeps paying for.

**C4 — `test_surf_widget_contract.py` needs three edits the moment WP7 exports the new classes. → WP7.**
`test_the_derived_widget_lists_are_not_empty_and_agree` holds a hardcoded set, and
`test_no_pool4_widget_needs_a_kwarg_alias` asserts `len(pool4) == 5`. All five new classes are named
`SurfPool4*`, so they land in that bucket. `SurfPool4UserHero` deliberately takes no
`pool4_as_of_hhmm` — a hero has no room for a clock and the title bar carries the fast tier's.

**C5 — the compositing helper is now written twice. → WP10.**
`tests.widgets.surf_compositing` does not exist; this plan cited it as existing. WP5 restated the
private `_lines` helper in both its test files rather than create a shared module while WP9 was
writing in the same tree — the right call under concurrency, and the wrong end state. Hoist it once
the wave has landed.

**C6 — pre-existing defect, `widgets/surf/hero.py:431`. → file only, do not fix.**
`self.update("\n".join(lines))` hands a markup **string** to `Static.update`, which is precisely what
CLAUDE.md's pre-built-`Text` rule forbids: Textual defers the parse into the message pump, so a
malformed third-party string raises *outside* the screen's `try/except` and kills the app. Pre-existing
and outside this branch's scope. **Record it in `docs/surf_pool4_followups.md` (WP10); do not fix it
here** — a fix would ride into this branch unreviewed.

## Wave order

```
WP0  contract freeze                    ── must land first, alone
  ├── WP1  analytics: depth ladder      ─┐
  ├── WP2  data: venue gap + reads       │  parallel
  ├── WP3  data: trailing return         │
  ├── WP4  data: staker sweep + fold     │
  ├── WP5  widgets: hero + stakers + burn│
  └── WP8  oracle fixture               ─┘
WP6  manager wiring        ── after WP2, WP3, WP4
WP9  widgets: signals + depth table ── after WP1
WP7  screen + CSS wiring   ── after WP5, WP9
WP10 layout measurement + docs ── after WP7, LAST
```

---

## Task WP0: Freeze the data contract

**Nothing else may start until this lands.** Every other package builds against these names.

**Files:**
- Modify: `maxpane_dashboard/data/surf_models.py`
- Modify: `maxpane_dashboard/data/surf_cache.py:80-130`
- Test: `tests/data/test_surf_pool4_market_models.py`

**Interfaces:**
- Produces: `POOL4_KEYS` extended by nine names; new `POOL4_STAKERS_KEYS` tuple; `TIER_POOL4_STAKERS`, `SLOT_POOL4_STAKERS`; `POOL4_VENUE_WORDS`, `POOL4_BURNING_STATES`, `POOL4_BACKSTOP_STATES`.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_pool4_market_models.py
from maxpane_dashboard.data import surf_models as m


def test_the_nine_fast_tier_keys_joined_pool4_keys():
    added = (
        "pool4_reference_pool_tick",
        "pool4_venue_gap_pct",
        "pool4_cheaper_venue",
        "pool4_price_usd",
        "pool4_backstop_lower_tick",
        "pool4_backstop_liquidity",
        "pool4_backstop_eth",
        "pool4_backstop_state",
        "pool4_trailing_return_pct",
    )
    for key in added:
        assert key in m.POOL4_KEYS, key
    assert len(m.POOL4_KEYS) == 71


def test_the_cross_venue_key_does_not_borrow_the_internal_ref_tick_name():
    """`pool4_ref_tick` is the hook's own lagged anti-manipulation tick.

    Two things called "ref tick" in one payload is how a wrong number renders
    confidently, so the cross-venue read carries the longer name and both
    survive. PRD 7.1.
    """
    assert "pool4_ref_tick" in m.POOL4_KEYS
    assert "pool4_reference_pool_tick" in m.POOL4_KEYS
    assert m.POOL4_KEYS.count("pool4_ref_tick") == 1


def test_the_trailing_return_is_not_the_delivery_cap_key():
    """`pool4_implied_apr_pct` is the drip *cap* annualised -- a ceiling, not
    a yield. The realised number gets its own key or the vault panel's whole
    refusal to say APR is undone one payload later. PRD 8.1."""
    assert "pool4_implied_apr_pct" in m.POOL4_KEYS
    assert "pool4_trailing_return_pct" in m.POOL4_KEYS


def test_the_staker_sweep_keys_are_their_own_tuple():
    assert m.POOL4_STAKERS_KEYS == (
        "pool4_stakers",
        "pool4_staker_count",
        "pool4_staker_top3_pct",
        "pool4_stakers_as_of_hhmm",
    )
    for key in m.POOL4_STAKERS_KEYS:
        assert key in m.SURF_KEYS


def test_the_three_vocabularies_are_frozen():
    assert m.POOL4_VENUE_WORDS == ("here", "reference")
    assert m.POOL4_BACKSTOP_STATES == ("deployed", "none")
    assert m.POOL4_BURNING_STATES == ("on", "off")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_models.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'POOL4_STAKERS_KEYS'`

- [ ] **Step 3: Add the vocabularies to `surf_models.py`**

Place beside the existing `POOL4_DISCOVERY_SOURCES` block (around line 641):

```python
#: Which venue prices IMD more cheaply for a buyer, or None when the gap is
#: below the two pools' fees summed. A gap smaller than that is not
#: arbitrageable, and telling a reader to switch venues over it is telling
#: them to lose the spread -- so "no word" is a real answer here, not a
#: missing one. PRD 8.3.
POOL4_VENUE_WORDS: tuple[str, ...] = ("here", "reference")

#: THREE states, not two: `deployed` renders the band, `none` means no band
#: exists right now, and `None` means the read failed. Collapsing the middle
#: into either of the others is the curator rail bug verbatim -- a real
#: negative with no representable value reads confident and green through an
#: outage. PRD 5.2.
POOL4_BACKSTOP_STATES: tuple[str, ...] = ("deployed", "none")

#: `off` means headroom > 0 and was READ. `None` means we could not look.
#: Headroom zero is a representable zero and means burning is ON.
POOL4_BURNING_STATES: tuple[str, ...] = ("on", "off")
```

- [ ] **Step 4: Extend `POOL4_KEYS` with the nine fast-tier names**

Append inside the existing `POOL4_KEYS` tuple, as one commented block:

```python
    # ---- the `4` market body: cross-venue price (PRD 5.1, 6.3, 8.3) --------
    # NOT `pool4_ref_tick`, which is three lines up and means the hook's own
    # block-lagged anti-manipulation tick. Different number, different job.
    "pool4_reference_pool_tick",  # int | None — the hookless pool's tick
    "pool4_venue_gap_pct",        # float | None — signed; + = IMD dearer here
    "pool4_cheaper_venue",        # str | None — POOL4_VENUE_WORDS; None = below fees
    "pool4_price_usd",            # float | None — USD per IMD
    # ---- the backstop broken out, for the hero card and the ladder --------
    # Only the derived `pool4_backstop_centred` was exposed before; the ladder
    # needs the band itself.
    "pool4_backstop_lower_tick",  # int | None
    "pool4_backstop_liquidity",   # int | None — raw L, not scaled
    "pool4_backstop_eth",         # float | None — whole ETH in the band
    "pool4_backstop_state",       # str | None — POOL4_BACKSTOP_STATES
    # ---- realised staking return (PRD 8.1) --------------------------------
    # The measured one. `pool4_implied_apr_pct` above is the DELIVERY CAP and
    # stays; these are two different numbers and the panel shows this one.
    "pool4_trailing_return_pct",  # float | None — 7d realised drips / TVL
```

- [ ] **Step 5: Add `POOL4_STAKERS_KEYS` and unpack it into `SURF_KEYS`**

```python
#: The long-tier staker sweep's own payload, on `CURATOR_ANALYSIS_KEYS`'s
#: shape: a separate tuple against a separate slot, where the fixed count is
#: itself the tripwire. PRD 7.2.
POOL4_STAKERS_KEYS: tuple[str, ...] = (
    "pool4_stakers",            # list[dict] | None — rank/addr/imd/pct
    "pool4_staker_count",       # int | None
    "pool4_staker_top3_pct",    # float | None — None on an INCOMPLETE fold
    "pool4_stakers_as_of_hhmm", # str | None — its own, slower clock
)
```

Then, in `SURF_KEYS`, beside the existing `*POOL4_KEYS,` line (around 1463):

```python
    *POOL4_KEYS,
    *POOL4_STAKERS_KEYS,
```

- [ ] **Step 6: Add the tier and slot to `surf_cache.py`**

Beside `TIER_POOL4 = "pool4"` (line 93):

```python
#: The staker sweep's own long tier, on curator's `TIER_ANALYSIS` precedent
#: and for its reason: the fold is a full `Transfer` history walk, far too
#: expensive for the 600 s pool4 tier, and the panel behind it moves slowly.
TIER_POOL4_STAKERS = "pool4_stakers"
```

Add to the tier tuple (line 96), and to both interval tables:

```python
    TIER_POOL4_STAKERS: 1800.0,   # in the normal-interval table (line ~104)
    TIER_POOL4_STAKERS: 300.0,    # in the after-failure table (line ~112)
```

Beside `SLOT_POOL4` (line 127):

```python
SLOT_POOL4_STAKERS = "pool4_stakers"  # the sIMD Transfer fold's last-good
```

Add both names to `__all__` (around line 1073).

- [ ] **Step 7: Run the test and watch it pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_models.py -v`
Expected: 5 passed

- [ ] **Step 8: Prove the count test bites**

Delete one key from the appended block, re-run, confirm `test_the_nine_fast_tier_keys_joined_pool4_keys` reddens **and names the missing key**, then restore. A count assertion that passes with a name missing is a count assertion testing itself.

- [ ] **Step 9: Run the neighbouring suites that consume these tuples**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_models.py tests/data/test_surf_cache_pool4.py -q`
Expected: PASS. If a key-count assertion elsewhere reddens, **that is this task's job to update** — it is the tripwire working.

- [ ] **Step 10: Commit**

```bash
git add maxpane_dashboard/data/surf_models.py maxpane_dashboard/data/surf_cache.py tests/data/test_surf_pool4_market_models.py
git commit -m "feat(surf): freeze the data contract for the pool4 market view"
```

---

## Task WP1: The depth ladder (pure analytics)

**Files:**
- Create: `maxpane_dashboard/analytics/surf_pool4_depth.py`
- Test: `tests/analytics/test_surf_pool4_depth.py`

**Interfaces:**
- Consumes: nothing. **Stdlib only** — no `data/`, no Textual, no clock, no I/O. It joins the `test_surf_widget_contract.py` allowlist in WP9 and its recursive purity walk will check it.
- Produces:
  - `DEPTH_MOVES: tuple[int, ...]`
  - `sqrt_ratio(tick: float) -> float`
  - `eth_between(liquidity: float, tick_lo: int, tick_hi: int) -> float` — whole ETH
  - `tick_for_price_drop(tick_now: int, drop_pct: float) -> int`
  - `depth_rows(*, tick, position_liquidity, band_lower_tick, band_liquidity) -> list[dict] | None`

**Background the implementer needs.** POOL4 is a Uniswap v4 ETH/IMD pool where **ETH is currency0**. Price is IMD per ETH, so **tick up means IMD is cheaper** — a reader selling IMD pushes the tick *up*. The hook holds a full-range position plus a single-sided ETH "backstop" band that starts just above spot in tick terms (below spot in price terms) and runs to the max tick. Constant-liquidity math over a tick range:

```
amount0 (ETH)  = L * (sqrtB - sqrtA) / (sqrtA * sqrtB)
amount1 (IMD)  = L * (sqrtB - sqrtA)
sqrt(price@t)  = 1.0001 ** (t / 2)
```

- [ ] **Step 1: Write the failing test**

```python
# tests/analytics/test_surf_pool4_depth.py
import math
import pytest
from maxpane_dashboard.analytics import surf_pool4_depth as d

L = 1e18


def test_eth_between_matches_a_value_derived_outside_the_formula():
    """Independent oracle, not a restatement of the implementation.

    CORRECTED 2026-09-11 (found by WP1): this sample originally used 13863,
    which is the tick where the price QUADRUPLES -- 1.0001 ** 13863 == 3.9998.
    13863 is the doubling tick of *sqrt(price)*, not of price. The doubling
    tick is log(2)/log(1.0001) == 6931.8 -> 6932.

    1.0001 ** 6932 == 2.0, so over that range the price doubles and sqrt(price)
    goes 1 -> sqrt(2). A full-range position pays out exactly ``1 - 1/sqrt(2)``
    of its notional in currency0 across a doubling. That identity comes from
    the price move, not from the code under test.
    """
    assert d.sqrt_ratio(6932) == pytest.approx(math.sqrt(2.0), rel=1e-4)
    expected = 1.0 - 1.0 / math.sqrt(2.0)          # 0.2928932...
    got = d.eth_between(L, 0, 6932)
    assert got == pytest.approx(expected, rel=1e-4)


def test_eth_between_is_additive_across_a_split_range():
    """A property the formula does not assert about itself: walking a range in
    two hops must pay exactly what walking it in one hop pays."""
    whole = d.eth_between(L, 1000, 9000)
    halves = d.eth_between(L, 1000, 5000) + d.eth_between(L, 5000, 9000)
    assert whole == pytest.approx(halves, rel=1e-12)


def test_eth_between_is_zero_when_the_range_does_not_open():
    assert d.eth_between(L, 5000, 5000) == 0.0
    assert d.eth_between(L, 5000, 4000) == 0.0


def test_a_price_drop_raises_the_tick_because_tick_up_is_imd_cheaper():
    assert d.tick_for_price_drop(68196, 50.0) > 68196
    # halving the price doubles IMD-per-ETH: +6932 ticks, not +13863
    assert d.tick_for_price_drop(0, 50.0) == pytest.approx(6932, abs=2)


def test_more_liquidity_pays_more_and_less_pays_less():
    """Both directions. A one-directional check cannot see a sign error."""
    base = d.depth_rows(
        tick=68196, position_liquidity=6.948e20,
        band_lower_tick=68280, band_liquidity=8.0e20,
    )
    richer = d.depth_rows(
        tick=68196, position_liquidity=2 * 6.948e20,
        band_lower_tick=68280, band_liquidity=8.0e20,
    )
    poorer = d.depth_rows(
        tick=68196, position_liquidity=0.5 * 6.948e20,
        band_lower_tick=68280, band_liquidity=8.0e20,
    )
    for b, r, p in zip(base, richer, poorer):
        assert r["eth_paid"] > b["eth_paid"] > p["eth_paid"]


def test_the_ladder_is_cumulative_and_band_use_never_exceeds_one():
    rows = d.depth_rows(
        tick=68196, position_liquidity=6.948e20,
        band_lower_tick=68280, band_liquidity=8.0e20,
    )
    assert [r["move_pct"] for r in rows] == list(d.DEPTH_MOVES)
    assert all(
        rows[i]["eth_paid"] < rows[i + 1]["eth_paid"] for i in range(len(rows) - 1)
    )
    assert all(0.0 <= r["band_used_pct"] <= 100.0 for r in rows)


def test_a_missing_input_returns_none_and_never_a_zero_ladder():
    """A failed read is None, never 0. A ladder of zeros would render as
    'this pool bids nothing', which is a confident wrong answer."""
    assert d.depth_rows(
        tick=None, position_liquidity=6.9e20,
        band_lower_tick=68280, band_liquidity=8.0e20,
    ) is None
    assert d.depth_rows(
        tick=68196, position_liquidity=None,
        band_lower_tick=68280, band_liquidity=8.0e20,
    ) is None


def test_no_band_still_gives_a_ladder_from_the_full_range_position():
    """No backstop deployed is a real state, not a failure: the full-range
    position still bids. band_used_pct is 0.0, not None."""
    rows = d.depth_rows(
        tick=68196, position_liquidity=6.948e20,
        band_lower_tick=None, band_liquidity=None,
    )
    assert rows is not None
    assert all(r["band_used_pct"] == 0.0 for r in rows)
    assert all(r["eth_paid"] > 0.0 for r in rows)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_pool4_depth.py -v`
Expected: FAIL — `ModuleNotFoundError: maxpane_dashboard.analytics.surf_pool4_depth`

- [ ] **Step 3: Write the implementation**

```python
"""POOL4 depth ladder -- what the hook's own liquidity bids as IMD falls.

PURE. Stdlib only: no I/O, no clock, no Textual, no ``data/``. PRD 6.5, 7.5.

**What this is and is not.** These are quotes from the position as it stands
*right now*. A ``rebalance()`` closes the backstop band and redeploys it from
just above spot, so every number here can move the moment a keeper acts. It is
never a floor, never a guarantee and never protection -- see PRD 8.2 and the
forbidden-word test in ``tests/widgets/test_surf_pool4u_depth.py``.

**Orientation.** ETH is currency0 and price is IMD per ETH, so **tick up means
IMD is cheaper**: a reader selling IMD pushes the tick up, the pool pays out
ETH (currency0) and absorbs IMD (currency1).
"""

from __future__ import annotations

import math

#: v4's max usable tick. The backstop band runs from its lower tick to here,
#: which is what makes its ETH single-sided.
MAX_TICK = 887272

#: log(1.0001), hoisted: this is the hot constant in every conversion.
_LOG_BASE = math.log(1.0001)

#: The ladder's rungs, as percentage falls in IMD's price. Five rows, chosen
#: to fit the panel: -1 is "a normal candle", -50 is "a bad day". The skill's
#: own ladder runs to -90, which is past the point a reader learns anything.
DEPTH_MOVES: tuple[int, ...] = (1, 5, 10, 20, 50)


def sqrt_ratio(tick: float) -> float:
    """sqrt(price) at ``tick``, where price is IMD per ETH."""
    return 1.0001 ** (tick / 2.0)


def eth_between(liquidity: float, tick_lo: int, tick_hi: int) -> float:
    """Whole ETH a position of ``liquidity`` pays as the tick rises lo -> hi.

    Returns 0.0 -- not a negative, not None -- when the range does not open,
    because "the price did not get there" is a representable zero.
    """
    if tick_hi <= tick_lo:
        return 0.0
    a, b = sqrt_ratio(tick_lo), sqrt_ratio(tick_hi)
    return liquidity * (b - a) / (a * b) / 1e18


def tick_for_price_drop(tick_now: int, drop_pct: float) -> int:
    """The tick IMD's price reaches after falling ``drop_pct`` percent.

    A fall in IMD's price is a *rise* in IMD-per-ETH, hence a rise in tick.
    """
    if drop_pct <= 0.0 or drop_pct >= 100.0:
        return tick_now
    ratio = 1.0 / (1.0 - drop_pct / 100.0)
    return tick_now + int(round(math.log(ratio) / _LOG_BASE))


def depth_rows(
    *,
    tick: int | None,
    position_liquidity: float | None,
    band_lower_tick: int | None,
    band_liquidity: float | None,
) -> list[dict] | None:
    """The cumulative ladder, or ``None`` if the position could not be read.

    Keyword-only on ``_pool4_cap_headroom``'s precedent: two tick arguments
    and two liquidity arguments sitting side by side is exactly the signature
    where a positional swap is silent, so make it a ``TypeError``.

    ``None`` for the whole ladder, never a ladder of zeros: a zero ladder
    renders as "this pool bids nothing", which is a confident wrong answer to
    a question we could not answer at all.
    """
    if tick is None or position_liquidity is None:
        return None

    has_band = band_lower_tick is not None and band_liquidity is not None
    band_total = (
        eth_between(band_liquidity, band_lower_tick, MAX_TICK) if has_band else 0.0
    )

    rows: list[dict] = []
    for move in DEPTH_MOVES:
        target = tick_for_price_drop(tick, float(move))
        full = eth_between(position_liquidity, tick, target)
        band = 0.0
        if has_band and target > band_lower_tick:
            band = eth_between(band_liquidity, max(tick, band_lower_tick), target)
        used = (band / band_total * 100.0) if band_total > 0.0 else 0.0
        rows.append(
            {
                "move_pct": move,
                "eth_paid": full + band,
                "band_used_pct": min(used, 100.0),
            }
        )
    return rows
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_pool4_depth.py -v`
Expected: 8 passed

**This formula is already validated against the independent implementation.** Run at the oracle
fixture's inputs (tick 68181, L 6.9047e20, band 68340 / 7.4686e20) it reproduces the skill's whole
sell-side ladder to the penny — 0.28 / 1.01 / 2.24 / 4.82 / 7.57 / 13.73 ETH at -2/-5/-10/-20/-30/-50%
— and `eth_between(band, 68340, MAX_TICK)` returns **24.509**, matching the chain's own
`backstopPrincipal` exactly. The only divergence is -1%, where we compute 0.12 against the oracle's
0.11: a second-decimal rounding difference, inside WP8's 1% tolerance. If your implementation does
not reproduce these, the implementation is wrong — not the fixture.

- [ ] **Step 5: Prove the direction test bites**

Change `tick_for_price_drop` to `tick_now - int(round(...))` — a sign error, and the single most plausible mistake in this module. Re-run. Confirm `test_a_price_drop_raises_the_tick_because_tick_up_is_imd_cheaper` reddens **and** that the ladder monotonicity test reddens with it. Restore.

- [ ] **Step 6: Prove the None guard bites**

Change `return None` to `return []`. Confirm `test_a_missing_input_returns_none_and_never_a_zero_ladder` reddens. Restore.

- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/analytics/surf_pool4_depth.py tests/analytics/test_surf_pool4_depth.py
git commit -m "feat(surf): pure depth-ladder math for the pool4 market view"
```

---

## Task WP2: Cross-venue price — the read and the fold

**Files:**
- Create: `maxpane_dashboard/data/surf_pool4_market.py`
- Modify: `maxpane_dashboard/data/surf_pool4_client.py` (**WP2 owns this file**)
- Test: `tests/data/test_surf_pool4_market_venue.py`

**Interfaces:**
- Consumes: `POOL4_VENUE_WORDS` (WP0).
- Produces:
  - `venue_gap_pct(*, hook_tick, reference_tick) -> float | None`
  - `cheaper_venue(*, gap_pct, hook_fee_bps, reference_fee_bps) -> str | None`
  - `POOL4_REFERENCE_POOL_ID: str` in the client
  - `fetch_reference_slot0(...) -> dict | None` in the client

**The contradiction this task exists to close (PRD 8.3).** The research skill reported the hook **+1.5%** against the reference from `state`, **+0.2%** from `share` twenty-eight blocks later, and 145 ticks (~1.45%) from `depth`. We do not know which is right. This task derives it **one way, from both ticks at the same block**, and writes that derivation into the docstring so the next reader does not have to rediscover the ambiguity.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_pool4_market_venue.py
import pytest
from maxpane_dashboard.data import surf_pool4_market as mk


def test_the_gap_is_derived_from_both_ticks_and_is_signed():
    """Hook at 68196, reference at 68341: the reference tick is HIGHER, so IMD
    is cheaper there, so a buyer pays more here -> positive gap."""
    gap = mk.venue_gap_pct(hook_tick=68196, reference_tick=68341)
    assert gap == pytest.approx(1.46, abs=0.02)
    assert mk.venue_gap_pct(hook_tick=68341, reference_tick=68196) == pytest.approx(
        -1.44, abs=0.02
    )


def test_the_gap_is_none_when_either_tick_is_missing():
    assert mk.venue_gap_pct(hook_tick=None, reference_tick=68341) is None
    assert mk.venue_gap_pct(hook_tick=68196, reference_tick=None) is None


def test_no_venue_is_named_when_the_gap_is_below_the_combined_fees():
    """PRD 8.3. Both pools charge 1%, so a gap under 2% is not arbitrageable
    and switching venues over it loses the spread. Silence is the answer."""
    assert mk.cheaper_venue(
        gap_pct=1.46, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None
    assert mk.cheaper_venue(
        gap_pct=0.2, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None


def test_the_reference_is_named_only_once_the_gap_clears_the_fees():
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=10000, reference_fee_bps=10000
    ) == "reference"
    assert mk.cheaper_venue(
        gap_pct=-3.0, hook_fee_bps=10000, reference_fee_bps=10000
    ) == "here"


def test_an_unreadable_fee_is_not_a_free_pass():
    """A missing fee must not be treated as zero -- that would let every gap
    clear a threshold of nothing and name a venue on noise."""
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=None, reference_fee_bps=10000
    ) is None
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=10000, reference_fee_bps=None
    ) is None
    assert mk.cheaper_venue(
        gap_pct=None, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_venue.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the fold**

```python
"""Pure folds for the POOL4 `4` market body. No I/O, no clock, no Textual.

Imported by the manager, never by a widget.
"""

from __future__ import annotations

import math

_LOG_BASE = math.log(1.0001)


def venue_gap_pct(*, hook_tick: int | None, reference_tick: int | None) -> float | None:
    """How much dearer IMD is on the hook pool than on the hookless one, in %.

    **Derived one way, and this docstring is the authority on which way.** The
    research skill reported this number three ways that did not agree -- +1.5%
    from its ``state`` command, +0.2% from ``share`` twenty-eight blocks later,
    and 145 ticks (~1.45%) implied by ``depth``. We do not inherit any of them.

    The derivation: price is IMD per ETH and equals ``1.0001 ** tick``, so a
    HIGHER tick means more IMD per ETH, means IMD is CHEAPER there. IMD's price
    ratio between the two venues is therefore ``1.0001 ** (reference - hook)``,
    and a positive result means a buyer pays more on the hook pool.

    **Both ticks must come from the same block.** Reading them a block apart is
    how a 1.3% disagreement appears out of nothing in a thin pool -- see
    ``fetch_reference_slot0``, which batches with the hook read for exactly
    this reason.
    """
    if hook_tick is None or reference_tick is None:
        return None
    return (math.exp((reference_tick - hook_tick) * _LOG_BASE) - 1.0) * 100.0


def cheaper_venue(
    *,
    gap_pct: float | None,
    hook_fee_bps: int | None,
    reference_fee_bps: int | None,
) -> str | None:
    """Which venue a buyer should use, or ``None`` when the answer is neither.

    ``None`` is a real answer here and the common one: a gap smaller than the
    two pools' fees summed cannot be arbitraged away, and a reader who moves
    venues to capture it pays more in spread than the gap is worth. PRD 8.3.

    An unreadable fee returns ``None`` rather than defaulting to zero. A zero
    default would make every threshold trivially clear and name a venue on
    noise -- the ``0 in (None, False, ())`` failure this repo has already
    shipped once.
    """
    if gap_pct is None or hook_fee_bps is None or reference_fee_bps is None:
        return None
    threshold = (hook_fee_bps + reference_fee_bps) / 10000.0
    if abs(gap_pct) <= threshold:
        return None
    return "reference" if gap_pct > 0 else "here"
```

- [ ] **Step 4: Add the reference-pool read to the client**

In `maxpane_dashboard/data/surf_pool4_client.py`, beside the existing pool id constants:

```python
#: The hookless ETH/IMD v4 pool, pinned rather than discovered. PRD 2: the
#: research skill warns that discovering a token's reference pool costs several
#: hundred `eth_getLogs` calls over public nodes. Pinning is one `getSlot0`.
#: If IMD's deepest pool ever moves, this constant is wrong and the venue gap
#: silently compares against a shallow pool -- which is why WP8's oracle test
#: cross-checks it against the skill's own `pools` output.
POOL4_REFERENCE_POOL_ID = (
    "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3"
)
```

Add `fetch_reference_slot0` alongside the existing getters, **batched into the same multicall round as the hook's own `getSlot0`** so both ticks come from one block. Follow `fetch_candidate_answers`'s existing batching shape in this file; do not open a second round trip.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_venue.py -v`
Expected: 5 passed

- [ ] **Step 6: Prove the fee-threshold test bites**

Change `if abs(gap_pct) <= threshold:` to `if gap_pct == 0:`. Confirm **both** `test_no_venue_is_named_when_the_gap_is_below_the_combined_fees` cases redden — if only one does, the test is sampling, not covering. Restore.

- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/data/surf_pool4_market.py maxpane_dashboard/data/surf_pool4_client.py tests/data/test_surf_pool4_market_venue.py
git commit -m "feat(surf): derive the pool4 cross-venue price gap one way"
```

---

## Task WP3: The trailing return — realised drips, never the delivery cap

**Files:**
- Modify: `maxpane_dashboard/data/surf_pool4_market.py` (**WP3 appends; WP2 created it — coordinate or land WP2 first**)
- Test: `tests/data/test_surf_pool4_market_return.py`
- Fixture: `tests/fixtures/surf/pool4/dripped_logs_7d.json`

**Interfaces:**
- Produces: `trailing_return_pct(*, dripped_imd, window_seconds, vault_assets) -> float | None`

**Why this exists (PRD 8.1).** `pool4_implied_apr_pct` already exists and is `drip_rate × 365 / TVL` — the **delivery cap** annualised. The vault panel correctly refuses to call it APR. This is the different, real number: IMD actually delivered to the vault over a window, annualised against TVL. The protocol's own docs say the dripper's rate "is only a cap on how fast that reaches the vault".

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_pool4_market_return.py
import pytest
from maxpane_dashboard.data import surf_pool4_market as mk

WEEK = 7 * 24 * 3600


def test_the_return_annualises_what_actually_arrived():
    """1,000 IMD delivered to a 1,000,000 IMD vault in 7 days annualises to
    1000/1000000 * (365/7) * 100 = 5.214%."""
    got = mk.trailing_return_pct(
        dripped_imd=1000.0, window_seconds=WEEK, vault_assets=1_000_000.0
    )
    assert got == pytest.approx(5.214, abs=0.01)


def test_a_quiet_window_is_zero_percent_and_not_none():
    """Nothing dripped is a REAL answer -- the return genuinely was zero. It
    must not render as 'unavailable', which is what None means here."""
    assert mk.trailing_return_pct(
        dripped_imd=0.0, window_seconds=WEEK, vault_assets=1_000_000.0
    ) == 0.0


def test_an_unread_drip_total_is_none_not_zero():
    assert mk.trailing_return_pct(
        dripped_imd=None, window_seconds=WEEK, vault_assets=1_000_000.0
    ) is None


def test_an_empty_vault_is_none_rather_than_a_division_by_zero():
    """An empty vault has no return to report -- and infinity is not a number
    a panel can render."""
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=WEEK, vault_assets=0.0
    ) is None
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=WEEK, vault_assets=None
    ) is None


def test_a_zero_window_is_none_rather_than_infinite():
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=0, vault_assets=1_000_000.0
    ) is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_return.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'trailing_return_pct'`

- [ ] **Step 3: Append the fold to `surf_pool4_market.py`**

```python
#: Seconds in a year, for annualising a window. 365 days, not 365.25: the
#: protocol's own docs annualise on 365 and a panel that disagrees with the
#: protocol's stake page by 0.07% invites a bug report that is not a bug.
_YEAR_SECONDS = 365 * 24 * 3600


def trailing_return_pct(
    *,
    dripped_imd: float | None,
    window_seconds: float | None,
    vault_assets: float | None,
) -> float | None:
    """Realised staking return over a window, annualised. PRD 8.1.

    **This is not ``pool4_implied_apr_pct``.** That key is the dripper's rate
    annualised -- a *ceiling* on how fast rewards can reach the vault, which
    the vault panel deliberately refuses to call APR. This is what actually
    arrived: ``Dripped`` events summed over the window, annualised against TVL.

    **It is lumpy by construction** -- zero through a quiet stretch, spiking
    after a sell-off, because trims only happen when sells exceed headroom.
    That is why the caller renders it with its window in the label
    (``4.0% trailing 7d``) and never as a bare rate.

    Zero is a real answer and returns ``0.0``. ``None`` is reserved for "we
    could not compute it": an unread drip total, an unread or empty vault, or
    a zero-length window.
    """
    if dripped_imd is None or vault_assets is None or window_seconds is None:
        return None
    if vault_assets <= 0.0 or window_seconds <= 0.0:
        return None
    return (dripped_imd / vault_assets) * (_YEAR_SECONDS / window_seconds) * 100.0
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_return.py -v`
Expected: 5 passed

- [ ] **Step 5: Prove the zero-vs-None distinction bites**

Change the zero branch so an empty window returns `0.0` instead of `None`. Confirm `test_an_empty_vault_is_none_rather_than_a_division_by_zero` reddens while `test_a_quiet_window_is_zero_percent_and_not_none` **stays green** — the two must be independently sensitive or they are one test wearing two names. Restore.

- [ ] **Step 6: Capture the Dripped fixture**

Extend `scripts/capture_pool4.py` with a `--dripped` mode that writes 7 days of `Dripped` logs to `tests/fixtures/surf/pool4/dripped_logs_7d.json`. Follow the existing capture modes in that file. **Commit the fixture** — no test may reach the network.

- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/data/surf_pool4_market.py tests/data/test_surf_pool4_market_return.py tests/fixtures/surf/pool4/dripped_logs_7d.json scripts/capture_pool4.py
git commit -m "feat(surf): realised trailing staking return from Dripped events"
```

---

## Task WP4: The staker sweep and the concentration fold

**Files:**
- Modify: `maxpane_dashboard/data/surf_pool4_market.py` (**appends**)
- Test: `tests/data/test_surf_pool4_market_stakers.py`
- Fixtures: `tests/fixtures/surf/pool4/simd_transfers_full.json`, `tests/fixtures/surf/pool4/simd_transfers_partial.json`

**Interfaces:**
- Produces: `fold_share_transfers(logs, *, complete) -> dict[str, int]`, `staker_rows(balances, *, share_price, limit=20) -> list[dict]`, `top_n_pct(rows, n=3, *, complete) -> float | None`

**Why a sweep (PRD 6.1, 7.2).** Per-holder balances need the sIMD share token's full `Transfer` history folded from the vault's deploy block. Ranking is not the point; **concentration is** — whether three wallets can walk out of this vault is a risk a reader acts on.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_pool4_market_stakers.py
import pytest
from maxpane_dashboard.data import surf_pool4_market as mk

ZERO = "0x" + "00" * 20
A, B, C, D = ("0x" + c * 40 for c in "abcd")


def _xfer(frm, to, value):
    return {"from": frm, "to": to, "value": value}


def test_a_mint_credits_and_a_burn_debits():
    bal = mk.fold_share_transfers(
        [_xfer(ZERO, A, 100), _xfer(ZERO, B, 50), _xfer(A, ZERO, 30)], complete=True
    )
    assert bal == {A: 70, B: 50}


def test_a_holder_who_leaves_entirely_is_dropped_not_kept_at_zero():
    """A zero-balance row would rank an address that holds nothing."""
    bal = mk.fold_share_transfers(
        [_xfer(ZERO, A, 100), _xfer(A, B, 100)], complete=True
    )
    assert A not in bal
    assert bal == {B: 100}


def test_rows_convert_shares_to_imd_and_carry_a_share_of_vault():
    rows = mk.staker_rows({A: 600, B: 400}, share_price=2.0)
    assert rows[0] == {
        "rank": 1, "address": A, "imd": 1200.0, "pct": 60.0,
    }
    assert rows[1]["rank"] == 2 and rows[1]["pct"] == pytest.approx(40.0)


def test_top_three_is_none_on_an_incomplete_fold():
    """PRD 7.4. A partial sweep ranking a subset would understate
    concentration -- the exact direction that makes a risk look smaller than
    it is. None (the dash), never a number computed from part of the data.
    This is `clean_routed_eth`'s guard verbatim.
    """
    rows = mk.staker_rows({A: 600, B: 300, C: 100}, share_price=1.0)
    assert mk.top_n_pct(rows, 3, complete=True) == pytest.approx(100.0)
    assert mk.top_n_pct(rows, 3, complete=False) is None


def test_an_incomplete_fold_is_flagged_rather_than_silently_returned():
    bal = mk.fold_share_transfers([_xfer(ZERO, A, 100)], complete=False)
    assert bal.complete is False
    assert mk.fold_share_transfers([_xfer(ZERO, A, 100)], complete=True).complete is True


def test_an_unread_share_price_gives_no_rows_rather_than_raw_shares():
    """Rendering share counts where IMD is promised is a unit error a reader
    cannot see -- 21 billion 'shares' against 21,010 real ones is the
    decimals-offset trap one layer up."""
    assert mk.staker_rows({A: 600}, share_price=None) is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_stakers.py -v`
Expected: FAIL — `AttributeError: ... 'fold_share_transfers'`

- [ ] **Step 3: Implement the fold**

Append to `surf_pool4_market.py`. `fold_share_transfers` returns a `dict` subclass carrying a `.complete` flag so completeness travels with the data instead of in a parallel variable that a caller can forget to check:

```python
class ShareBalances(dict):
    """Folded sIMD balances, carrying whether the sweep actually finished.

    A plain dict would let an incomplete fold be ranked as though it were the
    whole vault, which understates concentration -- the direction that makes a
    risk look smaller than it is. The flag rides with the data.
    """

    complete: bool = False


def fold_share_transfers(logs, *, complete: bool) -> ShareBalances:
    """Fold sIMD ``Transfer`` logs into per-holder balances.

    Mints arrive from the zero address and burns go to it; both are ordinary
    transfers in ERC-20 and neither is a holder. A holder whose balance
    reaches zero is dropped rather than kept, so nothing ranks an address that
    holds nothing.
    """
    out = ShareBalances()
    out.complete = complete
    for log in logs:
        frm, to, value = log["from"], log["to"], int(log["value"])
        if frm != ZERO_ADDRESS:
            out[frm] = out.get(frm, 0) - value
            if out[frm] <= 0:
                out.pop(frm, None)
        if to != ZERO_ADDRESS:
            out[to] = out.get(to, 0) + value
    return out


def staker_rows(balances, *, share_price: float | None, limit: int = 20):
    """Ranked rows in IMD, or ``None`` if shares cannot be converted.

    ``share_price`` is IMD per share and is a LIVE read: the vault is a Solady
    ERC-4626 reporting ``decimals()`` of 24, so a hardcoded divisor renders a
    plausible wrong number rather than an error. CLAUDE.md's decimals rule.
    """
    if share_price is None or not balances:
        return None
    total = sum(balances.values())
    if total <= 0:
        return None
    ranked = sorted(balances.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {
            "rank": i + 1,
            "address": addr,
            "imd": shares * share_price,
            "pct": shares / total * 100.0,
        }
        for i, (addr, shares) in enumerate(ranked)
    ]


def top_n_pct(rows, n: int = 3, *, complete: bool) -> float | None:
    """Share of the vault the top ``n`` hold, or ``None`` on a partial fold."""
    if not complete or not rows:
        return None
    return sum(r["pct"] for r in rows[:n])
```

Define `ZERO_ADDRESS = "0x" + "00" * 20` at module scope.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_pool4_market_stakers.py -v`
Expected: 6 passed

- [ ] **Step 5: Prove the completeness guard bites**

Change `top_n_pct` to ignore `complete`. Confirm `test_top_three_is_none_on_an_incomplete_fold` reddens. Restore. Then delete the `if out[frm] <= 0` branch and confirm `test_a_holder_who_leaves_entirely_is_dropped_not_kept_at_zero` reddens. Restore.

- [ ] **Step 6: Fix the stale `share_price` comment — you own this one line**

`maxpane_dashboard/data/surf_models.py:1347` reads:

```python
    "pool4_share_price",           # float | None — convertToAssets(1e18) / 1e18
```

**That comment is wrong and it is the exact trap CLAUDE.md's decimals rule exists for.** The vault is a
Solady ERC-4626 reporting `decimals()` of **24**, so one whole share is `1e24`; `surf_pool4.py:1487` is
the authority and says `convertToAssets(10 ** decimals())`. The *value* in the payload is correct — only
the comment is wrong, which is worse, because it sits where a consumer of this key naturally looks and
it documents the wrong-argument call the decoder refuses. Both wrong divisors render as plausible
numbers: one reads as a dead vault, the other as an emissions farm.

Fix the comment to `convertToAssets(10 ** decimals()) / 1e18 — one WHOLE share; decimals() is 24`.
**WP0 is finished and committed, so this one line is yours** — found by WP0 and filed rather than fixed,
per the review rule. Change nothing else in that file.

- [ ] **Step 7: Capture both fixtures**

Add `--transfers` to `scripts/capture_pool4.py`. Capture the **full** history to `simd_transfers_full.json`, and a **deliberately truncated** slice to `simd_transfers_partial.json` — the partial fixture exists solely to drive the `None` concentration guard and must be committed with a comment saying so.

- [ ] **Step 8: Commit**

```bash
git add maxpane_dashboard/data/surf_pool4_market.py maxpane_dashboard/data/surf_models.py tests/data/test_surf_pool4_market_stakers.py tests/fixtures/surf/pool4/simd_transfers_*.json scripts/capture_pool4.py
git commit -m "feat(surf): fold sIMD transfers into staker concentration"
```

---

## Task WP5: The repurposed hero, STAKERS and BURN & SUPPLY

**Files:**
- Create: `maxpane_dashboard/widgets/surf/pool4u_hero.py`, `pool4u_stakers.py`, `pool4u_burn.py`
- Test: `tests/widgets/test_surf_pool4u_hero.py`, `test_surf_pool4u_left.py`

**Interfaces:**
- Consumes: `POOL4_BACKSTOP_STATES`, `POOL4_VENUE_WORDS`, `POOL4_STAKERS_KEYS` (WP0).
- Produces: `SurfPool4UserHero`, `SurfPool4UStakers`, `SurfPool4UBurn`, each with `update_data(payload: dict) -> None`.

**Patterns to follow, not reinvent.** `widgets/surf/pool4_hatches.py` for the panel title and `‹ widen` marker (import from `widgets/surf/_pool4.py`, do not restate). `templates/hero_metrics_template.py` for the three-box hero. `widgets/sparkline_common.py` for the burn sparkline — **import the helpers, never paste them**; three dashboards once carried byte-identical copies and a fix reached none of the others. Row fitting comes from `widgets/surf/_rowfit.py` and is `cell_len`-based.

- [ ] **Step 1: Write the failing hero test — the three-state card first**

```python
# tests/widgets/test_surf_pool4u_hero.py
from maxpane_dashboard.widgets.surf.pool4u_hero import SurfPool4UserHero
# compositing helper used by every other surf widget test in this directory
from tests.widgets.surf_compositing import composite  # existing helper


async def test_the_backstop_card_tells_no_band_apart_from_no_read():
    """Three states, not two. PRD 5.2.

    `none deployed` and `unavailable` are DIFFERENT answers: one says we
    looked and there is no band, the other says we could not look. Rendering
    them identically is the curator rail bug -- a real negative with no
    representable value reads confident and green straight through an outage.
    """
    deployed = await composite(
        SurfPool4UserHero,
        {"pool4_backstop_state": "deployed", "pool4_backstop_eth": 24.419,
         "pool4_backstop_distance_pct": 0.84},
    )
    assert "24.4" in deployed and "0.84" in deployed

    absent = await composite(SurfPool4UserHero, {"pool4_backstop_state": "none"})
    assert "none deployed" in absent
    assert "unavailable" not in absent

    unread = await composite(SurfPool4UserHero, {"pool4_backstop_state": None})
    assert "unavailable" in unread
    assert "none deployed" not in unread


async def test_every_card_shows_unavailable_rather_than_going_blank():
    """MEDI-38. A card skipped when its value is missing keeps whatever it last
    showed -- or 'Loading...' forever if the first poll was the one that
    failed -- and a reader cannot tell stale from live."""
    out = await composite(SurfPool4UserHero, {})
    assert out.count("unavailable") == 3


async def test_the_staking_card_never_says_bare_apr():
    """PRD 8.1. The window is part of the number: this figure is lumpy by
    construction and a bare rate over-promises it."""
    out = await composite(
        SurfPool4UserHero,
        {"pool4_trailing_return_pct": 4.01, "pool4_vault_assets": 1_359_676.0,
         "pool4_staker_count": 66},
    )
    assert "trailing" in out and "7d" in out
    assert "APR" not in out


async def test_the_price_card_says_nothing_about_venues_below_the_fee_floor():
    """cheaper_venue is None when the gap cannot be arbitraged. The card must
    stay silent, not fall through to naming a venue anyway."""
    out = await composite(
        SurfPool4UserHero,
        {"pool4_price_usd": 2.845, "pool4_venue_gap_pct": 1.46,
         "pool4_cheaper_venue": None},
    )
    assert "2.845" in out
    assert "reference" not in out.lower()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_pool4u_hero.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `pool4u_hero.py`**

Three `Static` boxes in a `Horizontal`, on `templates/hero_metrics_template.py`'s shape. Three rules that are not optional:

1. **`_UNAVAILABLE` is rendered, never skipped** — the box always emits, so a failed poll cannot leave a stale value on screen.
2. **The backstop card branches on `pool4_backstop_state` three ways**, never on `pool4_backstop_eth is None`.
3. **Every value reaches `Static` as a pre-built `rich.text.Text`**, parsed synchronously inside the widget's own `try` — `Static.update("…[/x]…")` defers the parse into the message pump, where the failure raises outside the screen's `try/except` and kills the app.

- [ ] **Step 4: Write `pool4u_stakers.py`**

`DataTable` on `templates/leaderboard_template.py`'s shape: rank, address, IMD, % of vault, with a footer `Static` in the form `top 3 = NN% of vault`. Three rules:

1. **The footer renders `--` when `pool4_staker_top3_pct` is `None`**, and never a computed fallback.
2. Addresses are shortened with the template's `_short_addr` and **escaped** — they are chain-sourced strings.
3. The panel carries its **own** `as of HH:MM` from `pool4_stakers_as_of_hhmm`, not the body's, because it rides a slower tier (PRD 7.2).

- [ ] **Step 5: Write `pool4u_burn.py`**

Sparkline over `pool4_burn_points` plus pace, total retired, and share of supply. **Imports `build_sparkline_from_points` from `widgets/sparkline_common`.** A `None` sample degrades to a gap in the line, never to a zero — a zero in a burn series reads as "burning stopped", which is a different and wrong claim.

- [ ] **Step 6: Run all the widget tests**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_pool4u_hero.py tests/widgets/test_surf_pool4u_left.py -v`
Expected: PASS

- [ ] **Step 7: Prove the three-state test bites**

Collapse the backstop card's `none` branch into the unavailable branch. Confirm `test_the_backstop_card_tells_no_band_apart_from_no_read` reddens **on the `absent` assertions specifically** — not on the `unread` ones, which would mean the test is checking the wrong half. Restore.

- [ ] **Step 8: Commit**

```bash
git add maxpane_dashboard/widgets/surf/pool4u_hero.py maxpane_dashboard/widgets/surf/pool4u_stakers.py maxpane_dashboard/widgets/surf/pool4u_burn.py tests/widgets/test_surf_pool4u_hero.py tests/widgets/test_surf_pool4u_left.py
git commit -m "feat(surf): pool4 market hero, stakers and burn panels"
```

---

## Task WP9: SIGNALS and IF IMD FALLS

**Depends on WP1.**

**Files:**
- Create: `maxpane_dashboard/widgets/surf/pool4u_signals.py`, `pool4u_depth.py`
- Modify: `tests/widgets/test_surf_widget_contract.py` (add both to the analytics allowlist)
- Test: `tests/widgets/test_surf_pool4u_signals.py`, `test_surf_pool4u_depth.py`

**Interfaces:**
- Consumes: `analytics.surf_pool4_depth.depth_rows` output via the payload key `pool4_depth_rows`.
- Produces: `SurfPool4USignals`, `SurfPool4UDepth`.

- [ ] **Step 1: Write the failing tests — the two contracts that matter**

```python
# tests/widgets/test_surf_pool4u_signals.py

async def test_burning_tells_all_three_states_apart():
    """on / off / unknown. A checker that compares only the None word is a
    logged defect in this repo -- assert all three or this test is sampling."""
    on = await composite(SurfPool4USignals, {"pool4_burning": "on",
                                             "pool4_cap_headroom": 0.0})
    assert "ON" in on and "headroom 0" in on

    off = await composite(SurfPool4USignals, {"pool4_burning": "off",
                                              "pool4_cap_headroom": 1240.0})
    assert "OFF" in off and "1,240" in off

    unknown = await composite(SurfPool4USignals, {"pool4_burning": None})
    assert "ON" not in unknown and "OFF" not in unknown
    assert "unknown" in unknown


async def test_the_summary_line_never_gives_advice():
    """PRD 8.4. Bakery's template ends with a recommendation. That is fine for
    a cookie game and is something else on a financial market: this repo ships
    a strictly read-only tool. Grep the COMPOSITED body, not the source -- a
    bare-word source grep is a known-fake shape here.
    """
    out = await composite(
        SurfPool4USignals,
        {"pool4_burning": "on", "pool4_cheaper_venue": "reference",
         "pool4_venue_gap_pct": 3.1, "pool4_backstop_distance_pct": 0.84},
    )
    for forbidden in ("buy", "sell", "should", "recommend"):
        assert forbidden not in out.lower(), forbidden
    assert "burning on" in out.lower()
```

```python
# tests/widgets/test_surf_pool4u_depth.py

async def test_the_ladder_never_promises_protection():
    """PRD 8.2. These are quotes from the position as it stands; a rebalance
    relocates the band. THE RATCHET's `observed`-not-`guaranteed` rule, one
    panel over."""
    out = await composite(
        SurfPool4UDepth,
        {"pool4_depth_rows": [
            {"move_pct": 1, "eth_paid": 0.14, "band_used_pct": 5.0},
            {"move_pct": 50, "eth_paid": 13.81, "band_used_pct": 29.0},
        ]},
    )
    for forbidden in ("guaranteed", "protected", "safe", "floor"):
        assert forbidden not in out.lower(), forbidden
    assert "now" in out.lower()          # the title says what it is a quote of


async def test_an_unreadable_position_says_so_instead_of_showing_an_empty_table():
    out = await composite(SurfPool4UDepth, {"pool4_depth_rows": None})
    assert "unavailable" in out
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_pool4u_signals.py tests/widgets/test_surf_pool4u_depth.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `pool4u_signals.py`**

Four rows on `templates/signals_template.py`'s shape, plus a **state summary** replacing the template's recommendation line. The summary is **composed in the widget from the typed payload parts** — never shipped as a prose payload key, which would let the sentence drift from the rows above it.

Row contract: `burning` branches three ways on `pool4_burning`; `cheaper pool` renders nothing when `pool4_cheaper_venue` is `None`; `drip backlog` reads `pool4_backlog_days` and exists only to tell the reader whether the trailing return understates.

- [ ] **Step 4: Write `pool4u_depth.py`**

Table of `move_pct` / `eth_paid` / `band_used_pct` from `pool4_depth_rows`. Title carries the network word and the `‹ widen` marker from `widgets/surf/_pool4.py` — **import them; do not restate.** Two packages once wrote `network_word` twice with different behaviour on unknown input, which is how one body could paint `THE SPLIT · —` beside `THE RATCHET · BASE`.

- [ ] **Step 5: Add both widgets to the analytics allowlist**

In `tests/widgets/test_surf_widget_contract.py`, add `maxpane_dashboard.analytics.surf_pool4_depth` to the allowed-modules list. The suite's `test_the_allowed_analytics_modules_are_themselves_pure` will then AST-walk it **recursively** — a depth-1 version of that check was once green while an analytics module reached `data` one hop further on.

- [ ] **Step 6: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_pool4u_signals.py tests/widgets/test_surf_pool4u_depth.py tests/widgets/test_surf_widget_contract.py -v`
Expected: PASS

- [ ] **Step 7: Prove the forbidden-word tests bite**

Add the word `protected` to the depth panel's title. Confirm `test_the_ladder_never_promises_protection` reddens. Restore. Then add `should buy` to the signals summary; confirm the advice test reddens. Restore. **Confirm the composited assertion is what caught it** — if only a source grep would have, the test is the fake shape.

- [ ] **Step 8: Commit**

```bash
git add maxpane_dashboard/widgets/surf/pool4u_signals.py maxpane_dashboard/widgets/surf/pool4u_depth.py tests/widgets/test_surf_pool4u_signals.py tests/widgets/test_surf_pool4u_depth.py tests/widgets/test_surf_widget_contract.py
git commit -m "feat(surf): pool4 market signals and depth ladder panels"
```

---

## Task WP6: Manager wiring

**Depends on WP2, WP3, WP4. WP6 is the sole owner of `surf_manager.py`.**

**Files:**
- Modify: `maxpane_dashboard/data/surf_manager.py`
- Test: `tests/data/test_surf_manager_pool4_market.py`

**Interfaces:**
- Consumes: everything WP2–WP4 produced.
- Produces: the nine new fast keys inside `_pool4_keys`'s payload, and `POOL4_STAKERS_KEYS` from a detached sweep.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_surf_manager_pool4_market.py

async def test_the_first_payload_is_not_behind_the_staker_sweep():
    """The sweep is a full Transfer history walk. If first paint waits on it
    the dashboard is blank for minutes. Spawned, never awaited --
    `_spawn_pool4`'s contract (surf_manager.py:2594).

    This test fails by TIMING OUT, which is the point: there is no assertion
    that can observe 'did not block' after the fact.
    """
    mgr = _manager_with(stakers_transport=_never_returns())
    payload = await asyncio.wait_for(mgr.fetch_and_compute(), timeout=2.0)
    assert payload["pool4_current_tick"] is not None
    assert payload["pool4_stakers"] is None


async def test_the_stakers_marker_does_not_advance_on_a_tick_that_found_nothing():
    """A fresh time beside days-old data is a stale number presented as live.
    Curator's analysis marker rule, PRD 7.2."""
    mgr = _manager_with(stakers_transport=_returns_same_fold_twice())
    first = await mgr.fetch_and_compute()
    await _advance(mgr, seconds=1800)
    second = await mgr.fetch_and_compute()
    assert second["pool4_stakers_as_of_hhmm"] == first["pool4_stakers_as_of_hhmm"]


async def test_a_failed_sweep_serves_last_good_and_adds_no_ninth_degraded_group():
    """PRD 7.3. `p4` is the EIGHTH group and CLAUDE.md records that the eighth
    name is what took the worst-case title row to exactly the pinned width.
    There is no room for a ninth."""
    mgr = _manager_with(stakers_transport=_raises())
    payload = await mgr.fetch_and_compute()
    assert len(set(payload["degraded"])) <= 8
    assert "pool4_stakers" not in payload["degraded"]


async def test_both_ticks_come_from_the_same_block():
    """The whole reason the venue gap is derivable at all. PRD 8.3."""
    transport = _recording_transport()
    mgr = _manager_with(transport=transport)
    await mgr.fetch_and_compute()
    calls = transport.batched_calls()
    assert "getSlot0(hook)" in calls[0] and "getSlot0(reference)" in calls[0]
```

- [ ] **Step 2: Run and watch fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager_pool4_market.py -v`
Expected: FAIL

- [ ] **Step 3: Extend `_pool4_keys` with the nine fast keys**

Fold in `venue_gap_pct`, `cheaper_venue`, `trailing_return_pct` and the broken-out band. The backstop state is derived **three ways**, never two:

```python
if band is None:                       # the read failed
    state, lower, liq, eth = None, None, None, None
elif band.liquidity == 0:              # we looked; there is no band
    state, lower, liq, eth = "none", None, None, None
else:
    state = "deployed"
    ...
```

- [ ] **Step 4: Add `_spawn_pool4_stakers`**

Copy `_spawn_pool4`'s shape (`surf_manager.py:2594`) exactly: guard on `TIER_POOL4_STAKERS not in tiers`, one sweep at a time, `store_last_good(SLOT_POOL4_STAKERS, ...)`, `mark_failed` on error. **Never `await` it from `fetch_and_compute`.**

- [ ] **Step 5: Run the tests and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager_pool4_market.py -v`
Expected: PASS

- [ ] **Step 6: Prove the detachment test bites**

Change the spawn to `await self._pool4_stakers_detached(...)`. Confirm `test_the_first_payload_is_not_behind_the_staker_sweep` **times out** rather than failing on an assertion. Restore.

- [ ] **Step 7: Run the existing pool4 manager suite**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager_pool4.py tests/data/test_surf_cache_pool4.py -q`
Expected: PASS — the `p` body must be untouched by all of this.

- [ ] **Step 8: Commit**

```bash
git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager_pool4_market.py
git commit -m "feat(surf): wire the pool4 market keys and the staker sweep"
```

---

## Task WP7: Screen and CSS wiring

**Depends on WP5, WP9. WP7 is the sole owner of `screens/surf.py` and `themes/minimal.tcss`.**

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py`
- Modify: `maxpane_dashboard/themes/minimal.tcss`
- Test: `tests/screens/test_surf_pool4_market_screen.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_four_opens_the_market_body_and_escape_backs_out():
    async with app.run_test() as pilot:
        await pilot.press("4")
        assert screen._mode == MODE_POOL4_USER
        await pilot.press("escape")
        assert screen._mode == MODE_DASHBOARD


async def test_pressing_four_twice_returns_to_the_dashboard():
    """`action_toggle_launchpad`'s contract: the key is also its own way back."""


async def test_exactly_one_hero_shows_in_every_mode():
    """The repurposed hero is a SECOND widget toggled with the body -- curator's
    per-mode hero pattern. Two heroes showing at once, or none, are both
    reachable if the visibilities are derived separately rather than from one
    comparison against `self._mode`."""
    for mode, key in ((MODE_DASHBOARD, "escape"), (MODE_POOL4_USER, "4"),
                      (MODE_POOL4, "p"), (MODE_LAUNCHPAD, "l")):
        await pilot.press(key)
        shown = [h for h in screen.query(".surf-hero") if h.display]
        assert len(shown) == 1, mode


async def test_the_market_body_dispatches_every_key_it_declares():
    """A `**_kwargs` widget can absorb a dispatched key with every signature
    guard green (open finding S23). Render, then diff: each key must reach a
    widget that actually renders it."""
```

- [ ] **Step 2: Run and watch fail**

- [ ] **Step 3: Add the mode, the binding and the body**

```python
MODE_POOL4_USER = "pool4_user"
POOL4_USER_BODY_ID = "surf-pool4-user-body"
```

```python
Binding("4", "toggle_pool4_user", "Pool4 market", show=False),
```

`action_toggle_pool4_user` mirrors `action_toggle_pool4` (line 1956) including its idempotence.

- [ ] **Step 4: Extend `_show_mode` — and fix the two docstrings it makes false**

`_show_mode` (line 1908) currently derives four visibilities from one comparison against `self._mode`. Add the new body **and both heroes** to that same derivation — never a separate boolean, for the reason its own docstring gives: the obvious edit when the third body arrived would have left the pool4 body painting on top of a dashboard body that was still showing.

**Two docstrings become false and must be updated in this step, not later:**
- `_show_mode`'s own: *"this screen has exactly one hero and it is not part of any body … this method never touches its `display`, so it is on in every mode."* It now mounts two and toggles both, on curator's pattern — which that same docstring already names.
- The module docstring at `surf.py:40`: *"`#hero-row` is never touched by either swap and stays on screen in all"*.

A docstring that asserts the opposite of what the code does is worse than none: it is the thing the next reader trusts instead of reading.

- [ ] **Step 5: Extend `KEY_HINTS` — and measure it**

```python
KEY_HINTS = "[dim]l launchpad · p pool4 · 4 market[/]"
```

One markup run, not per-letter tags: adjacent differently-styled runs never share a composited line, and the acceptance test greps for the contiguous phrase. Then **measure it** — see WP10 Step 1. If it does not fit, `4 market` shortens; `l launchpad` does not.

- [ ] **Step 6: Add the CSS to both places**

Every screen rule appears identically in `SurfScreen.DEFAULT_CSS` **and** in `themes/minimal.tcss`; a test compares them property by property. Give every `1fr` child a `min-height` — a `1fr` child cannot overflow a scroll container, it *shrinks*, shedding a line per terminal row down to a bare title with no scrollbar and no trace. Any `Vertical` holding a growing panel needs `overflow-y: auto` **and** `scrollbar-gutter: stable`.

- [ ] **Step 7: Run the screen tests**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_pool4_market_screen.py tests/screens/test_surf_screen.py -v`
Expected: PASS

- [ ] **Step 8: Prove the hero test bites**

Give both heroes `display = True` unconditionally. Confirm `test_exactly_one_hero_shows_in_every_mode` reddens in **more than one** mode — if it reddens in only one, it is checking one branch and passing the rest by luck. Restore.

- [ ] **Step 8b: Close the four tests only WP7 can close**

All four verified red, none closable by any earlier package.

1. **`tests/screens/test_surf_screen.py::test_every_list_row_in_the_fixture_matches_the_frozen_row_shape`**
   — a **seventh** tripwire, caused by C2 declaring `SURF_ROW_KEYS["pool4_stakers"]`. Add
   `pool4_stakers` rows (`rank`/`address`/`imd`/`pct`) to `_sample_data()`. You have to do this anyway
   for `test_screen_dispatches_every_data_key`.

2. **`tests/data/test_surf_pool4_models.py::test_a_healthy_sweep_publishes_every_pool4_key`** — its
   hardcoded `missing` list names none of WP0's nine keys. Red since `b55ae5f`, not caused by WP6.

3. **`tests/data/test_surf_manager_pool4.py::test_the_backstop_publishes_one_tri_state_and_no_tick_bounds`**
   — **retire this test's premise, do not patch it into silence.** It asserts no backstop tick bound
   exists in `POOL4_KEYS`, which was A19's deliberate choice for the `p` body's rail. **The `4` body
   reverses A19 on purpose**: the depth ladder needs the band itself, so `pool4_backstop_lower_tick`
   and `pool4_backstop_liquidity` are published by design. Rewrite it to assert what is now true —
   the rail still renders one tri-state and does not render the bounds — and say in its docstring that
   A19 was narrowed rather than broken. A test whose premise a later decision retired must be
   rewritten with that decision named, never deleted and never quietly relaxed.

4. **`tests/data/test_surf_manager_pool4.py::test_the_log_window_is_the_trailing_span_from_the_head_block`**
   — genuinely new. It does `(start, end), = client.log_windows`, which assumed the pool4 sweep makes
   exactly one log read; WP6 added the dripper's delivery window, so there are two. Its claim is still
   true — select the hook's window rather than assume it is the only one.

Also worth doing while you are in that file: `FakePool4Client` has no `fetch_reference_slot0`, so that
suite logs a `WARNING ... has no attribute` per sweep. Harmless — `_guard` turns it into the honest
`None` — but it is noise that will train a reader to ignore warnings.

- [ ] **Step 9: Commit**

```bash
git add maxpane_dashboard/screens/surf.py maxpane_dashboard/themes/minimal.tcss tests/screens/test_surf_pool4_market_screen.py
git commit -m "feat(surf): the 4 key opens the pool4 market body"
```

---

## Task WP8: The independent oracle

**Runs in parallel from the start; its assertions land once WP2–WP4 exist.**

**Files:**
- Create: `tests/fixtures/surf/pool4/oracle_<block>.json`, `tests/data/test_surf_pool4_oracle.py`

**Why (PRD 9).** The `pool4hook-research` skill is a second, independent implementation of this protocol's math, written by its own author. Agreement between two independent implementations is a far stronger check than any self-consistency test — and it is exactly how the `0x840` / `0x2840` flag error would have been caught on day one instead of mid-build.

- [x] **Step 1: Capture the oracle at a pinned block — DONE, fixture committed**

`tests/fixtures/surf/pool4/oracle_25955365.json` already exists. **Do not regenerate it**: it is
evidence, and a fixture refreshed to make a test pass proves nothing.

**A trap that cost a rewrite of this step: `depth --json` carries only the *inputs*** (`spotTick`,
`fullRangeLiquidity`, `backstop.lower/liquidity`, `reference`) — **not the ladder rows.** The rows
exist only in the skill's text table and were parsed out of it. The committed fixture already holds
both, under `sell_side` with `full_range_eth` / `backstop_eth` / `band_used_pct` / `hook_total_eth`.

Still to capture if the staker cross-check is wanted: `node pool4hook.ts stakers --hours 168 --json`.

- [ ] **Step 2: Write the cross-check test**

```python
def test_our_depth_ladder_agrees_with_the_independent_reader():
    """Two implementations, one protocol. Tolerance is 1% because the oracle
    rounds for display; a disagreement wider than that is a real defect in one
    of them and this test does not care which."""
    CORRECTED 2026-09-11 (found by WP1): this originally used
    ``zip(ours, oracle["sell_side"])``. The oracle ladder has NINE rungs
    (1/2/5/10/20/30/50/75/90) and ``DEPTH_MOVES`` has five (1/5/10/20/50), so a
    positional zip compared our -5% against the oracle's -2% and our -10%
    against its -5%: a test that passes or fails for a reason that is not the
    claim. Match on ``move_pct``, and count the comparisons so a future rung
    with no oracle row cannot be skipped in silence.
    """
    oracle = _load_oracle()
    ours = depth_rows(
        tick=oracle["tick"],
        position_liquidity=oracle["position_liquidity"],
        band_lower_tick=oracle["backstop_lower"],
        band_liquidity=oracle["backstop_liquidity"],
    )
    by_move = {r["move_pct"]: r for r in oracle["sell_side"]}
    compared = 0
    for row in ours:
        ref = by_move[row["move_pct"]]          # KeyError, never a silent skip
        assert row["eth_paid"] == pytest.approx(ref["hook_total_eth"], rel=0.05)
        compared += 1
    assert compared == len(ours)


def test_our_pinned_reference_pool_is_the_one_the_oracle_calls_deepest():
    """If IMD's deepest pool ever moves, POOL4_REFERENCE_POOL_ID is wrong and
    the venue gap silently compares against a shallow pool. This is the test
    that notices."""
    assert _load_oracle()["reference_pool_id"] == POOL4_REFERENCE_POOL_ID
```

- [ ] **Step 3: Run and watch it fail, then pass once WP1/WP2 land**

- [ ] **Step 4: Record the venue-gap resolution**

Compute our `venue_gap_pct` from the oracle's two ticks and compare to each of the three figures the skill reported (+1.5%, +0.2%, ~1.45%). **Write the finding into `docs/surf_pool4_followups.md`** whichever way it lands — including "still unexplained". PRD 10.1 stays open until this step closes it.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/surf/pool4/oracle_*.json tests/data/test_surf_pool4_oracle.py docs/surf_pool4_followups.md
git commit -m "test(surf): cross-check pool4 math against an independent reader"
```

---

## Task WP11: The ladder must tell an unread band from an absent one

**Blocking. Runs before WP10.** Found by WP7, verified through the real screen.

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_pool4_depth.py`
- Modify: `maxpane_dashboard/widgets/surf/pool4u_depth.py`
- Test: `tests/analytics/test_surf_pool4_depth.py`, `tests/widgets/test_surf_pool4u_depth.py`

**The defect, measured.** `depth_rows` derives `has_band = band_lower_tick is not None and
band_liquidity is not None`, so an unread band and an undeployed one both produce
`band_used_pct == 0.0` on every rung. `depth_rows(..., band_liquidity=0)` and
`depth_rows(..., band_liquidity=None)` return equal lists, and the rendered column is byte-identical.

**Why it is not cosmetic.** This panel exists to answer *how much is bidding under me*. Reporting
`band used 0.0%` during an outage is a confident wrong answer to that question, and it is the exact
shape CLAUDE.md names: "a row whose real negative has no representable value renders `None` identically
for 'we looked and there was nothing' and 'we could not look', so it reads confident and green through
an outage."

**The fix.** `pool4_backstop_state` already carries the distinction (`"deployed"` / `"none"` / `None`)
and the ladder never consults it. Thread it through:

- `depth_rows` takes `band_state: str | None` as a keyword-only argument.
- `band_state is None` → each row's `band_used_pct` is **`None`**, not `0.0`. The full-range leg is
  still real and still renders: the position is readable even when the band is not, and a reader is
  better served by "the position bids this much, the band is unknown" than by either silence or a
  confident zero.
- `band_state == "none"` → `0.0`, which is the true value: there is no band, so none of it is used.
- `band_state == "deployed"` → today's behaviour.

The widget renders the `None` case visibly differently — not a dash that could read as zero.

- [ ] **Step 1: Write the failing test that pins the distinction**

```python
def test_an_unread_band_does_not_render_as_an_unused_one():
    """The defect this task exists for. Measured before the fix: these two
    returned equal lists and the rendered column was byte-identical."""
    common = dict(tick=68181, position_liquidity=6.9047e20, band_lower_tick=68340)
    unread = depth_rows(**common, band_liquidity=None, band_state=None)
    absent = depth_rows(**common, band_liquidity=0, band_state="none")

    assert [r["band_used_pct"] for r in unread] == [None] * len(unread)
    assert [r["band_used_pct"] for r in absent] == [0.0] * len(absent)
    assert unread != absent

    # the full-range leg survives an unread band -- the position is still readable
    assert all(r["eth_paid"] > 0.0 for r in unread)
```

- [ ] **Step 2: Run it, watch it fail on the equality**
- [ ] **Step 3: Add `band_state` and the three branches**
- [ ] **Step 4: Thread `pool4_backstop_state` through the widget; render the unread state distinctly**
- [ ] **Step 5: Add the composited widget test** — the two states must not produce the same painted column. Assert against `render_strips()`, not the row dicts.
- [ ] **Step 6: Prove it bites** — collapse `band_state is None` back into the `"none"` branch and confirm **both** the analytics test and the composited widget test redden. If only the analytics one does, the widget is not actually rendering the distinction.
- [ ] **Step 7: Remove the `_NUMERIC_KEYS_EXCLUDED` entry** WP7 added for `pool4_backstop_liquidity`, whose comment says it goes away when this defect does. Confirm `tests/test_surf_registration.py` stays green without it.
- [ ] **Step 8: Commit**

```bash
git add maxpane_dashboard/analytics/surf_pool4_depth.py maxpane_dashboard/widgets/surf/pool4u_depth.py tests/analytics/test_surf_pool4_depth.py tests/widgets/test_surf_pool4u_depth.py tests/test_surf_registration.py
git commit -m "fix(surf): the depth ladder tells an unread band from an absent one"
```

---

## Task WP10: Layout measurement and docs

**LAST. Depends on WP7. Sole owner of `CLAUDE.md`, `README.md` and the terminal-layout skill.**

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` (the two new pins only — coordinate with WP7)
- Modify: `CLAUDE.md`, `README.md`, `.claude/skills/terminal-layout/SKILL.md`
- Test: `tests/screens/test_surf_pool4_market_layout.py`

- [ ] **Step 1: Read the terminal-layout skill before touching a number**

`.claude/skills/terminal-layout/SKILL.md`. **Measure, never derive** — arithmetic over column constants has been wrong twice here, because a `DataTable` buys a cell gutter per column. **Measure in situ**, inside the real container, or the number is short by whatever padding the bare harness did not pay.

- [ ] **Step 2: Sweep for the column pin**

Render the body across a width range that **does not start at the pin** — a sweep starting there agrees with the constant by construction. Find the width at which the binding panel first clips, and confirm that panel can actually *mark* (`‹ widen`): a seam whose binding panel clips in silence is disqualified.

- [ ] **Step 3: Sweep for the row pin**

Same method vertically. **Record the result against W7**: the `p` body needs 44 rows, the tallest in the repo, and nobody has ever checked it against a real laptop. If this body lands nearer the launchpad's 31, say so in the `#:` block — it is the first evidence either way.

- [ ] **Step 4: Write both constants with their own `#:` blocks**

`SURF_POOL4_USER_FULL_LAYOUT_COLUMNS` and `..._ROWS`, each carrying its measurement method and which panel binds it. No second copy of either number anywhere, including in `CLAUDE.md` — a copy drifts and a docstring cannot be tested.

- [ ] **Step 5: Write the width test, both directions**

```python
def test_the_column_pin_is_measured_against_the_panel_that_binds_it():
    """Both directions: set it too low and too high, confirm each reddens.
    A one-directional test missed the defect that shipped here before."""
```

Assert the **property** (whenever a row would clip, the marker is lit), not the literal (the marker lights below 35). The literal goes stale silently; the property cannot.

- [ ] **Step 6: Measure the status hint**

Read `l launchpad · p pool4 · 4 market` back off **composited output** at `SURF_FULL_LAYOUT_COLUMNS`, following `test_the_pool4_key_hint_fits_the_status_bar_at_the_full_layout`. Do not count characters. If it does not fit, shorten `4 market` and re-measure.

- [ ] **Step 7: Run the mutation harness with a per-mutation pyc cache**

Both-directions pin tests are the most collision-prone mutation shape in this repo (open finding S22). The harness **must** use a `PYTHONPYCACHEPREFIX` directory **unique per mutation** — one shared prefix reproduces the bug where two same-size mutations in the same second run the first's bytecode (A31). After each mutation, confirm **which** test reddened, not merely that something did: `pytest ::nonexistent_test` exits 4, and a harness reading non-zero as "failed" scores that as a bite (A36).

- [ ] **Step 8: Update the docs**

- **CLAUDE.md** — add the `4` body to the surf section and the keys list, on the POOL4 section's shape. State the hero break explicitly: this is the first surf body that swaps the hero, and it follows curator's per-mode hero rather than inventing a pattern.
- **README.md** — the keys line.
- **terminal-layout SKILL.md** — add both pins to the pins table.

- [ ] **Step 9: Run the full suite — this is the merge gate**

Run: `.venv/bin/python -m pytest`
Expected: green, ~11 min. This is one of the few moments CLAUDE.md sanctions a full run: the end of a multi-task branch.

- [ ] **Step 10: Commit**

```bash
git add maxpane_dashboard/screens/surf.py CLAUDE.md README.md .claude/skills/terminal-layout/SKILL.md tests/screens/test_surf_pool4_market_layout.py
git commit -m "feat(surf): measure and document the pool4 market body's layout"
```

---

## Self-review

**Spec coverage.** Every PRD section maps to a task: §3 frame → WP7 + WP10; §4 layout → WP7, WP10; §5 hero → WP0 (states), WP5; §6.1–6.2 → WP5; §6.3 → WP9; §6.4 → reused unchanged, asserted in WP7 Step 1; §6.5 → WP1 + WP9; §7 data → WP0, WP2, WP3, WP4, WP6; §8 honesty → WP2 (8.3), WP3 (8.1), WP9 (8.2, 8.4); §9 testing → every task's bite step, plus WP8; §10 open items → WP8 Step 4 (venue gap), WP10 Step 3 (W7), WP10 Step 6 (hint width); §11 → enforced by Global Constraints.

**Type consistency.** `depth_rows` returns `list[dict]` with keys `move_pct` / `eth_paid` / `band_used_pct` in WP1, and WP9 reads exactly those three. `staker_rows` returns `rank` / `address` / `imd` / `pct` in WP4, and WP5 reads exactly those four. `cheaper_venue` returns `POOL4_VENUE_WORDS` or `None`; WP5 and WP9 both treat `None` as "render nothing".

**Known gap, deliberate.** `pool4_burn_points` (WP5's sparkline) and `pool4_backstop_distance_pct` are consumed by widgets but produced by WP6's manager fold without a task of their own — both are mechanical derivations from keys that already exist (`pool4_total_burned` bucketed by day; tick delta to `pool4_backstop_lower_tick`). **WP6 owns them.** They are called out here rather than left to be discovered, because a key consumed by a widget and produced by nobody is exactly the S23 shape this plan is otherwise trying to catch.
