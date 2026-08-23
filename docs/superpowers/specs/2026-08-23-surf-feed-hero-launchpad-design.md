# Surf: feed threading, hero rebuild, launchpad repair — design

**Date:** 2026-08-23
**Branch:** `feature/surf-feed-hero-launchpad`
**Predecessor:** `docs/superpowers/specs/2026-08-23-surf-v4-launchpad-design.md` (merged as
`d15e00f`; this spec repairs and extends what that one shipped)

Four independent changes to the `surf` dashboard, requested together:

1. **IMD MARKET** drops its legacy v3 pool line.
2. **The hero row** replaces POOL and LP with LAUNCHPAD and FLOW.
3. **ANNOUNCE FEED** becomes threaded: replies collapse under the post they answer,
   with an expand/collapse control, and the announcement wallet's own answers —
   currently misclassified — nest under the reply they answer.
4. **The `l` LAUNCHPAD view** puts CURVE FLOW and BURN PIPELINE in a right rail beside
   the coins table, and the coins table's data is repaired: it is currently showing
   the twenty oldest never-traded coins out of a population it can only see half of.

Each is separable. They share one screen and two payload surfaces, so they share a
branch, but no task in the plan depends on more than one of the others.

---

## Global constraints

These bind every task. They are the repo's, not this spec's.

- **Read-only.** No signer, no transactor, no calldata construction for a state change,
  no key or keystore. Nothing in this spec calls a contract that mutates.
- **Keyless.** publicnode for state, tenderly/drpc for logs, Blockscout for tx pages,
  DexScreener/GeckoTerminal for prices. No new source, no key, ever.
- **No test touches the network.** Inject a transport that raises. Every payload used by
  a test is a committed fixture under `tests/fixtures/surf/`.
- **A failed read is `None`, never `0`.** A representable zero and an unknown must render
  differently, and the difference must be visible on screen, not merely present in the
  payload.
- **Escape every third-party string** through `widgets/markup_safety.safe_markup` before
  it reaches markup or a table cell. Tickers, coin names and channel messages are all
  attacker-authored.
- **Assert against composited output** (`_compositor.render_strips()`), never the content
  string. **Prove a test bites**: mutate the code, watch it go red, restore.
- **Inject the clock.** No new module may call `time.time()` internally.
- **Do not move `__main__.FULL_LAYOUT_COLUMNS` (143) or `SURF_FULL_LAYOUT_COLUMNS` (143).**
  When a new value would widen a sized cell, shorten the value. Raising a width constant
  is reserved for when no honest short form exists, and this spec has none of those cases —
  §4.1 shows the arithmetic that keeps the launchpad body under 143 with the new rail.
- **The working tree holds ~300 untracked curator fixtures that are the user's own
  uncommitted work.** Never `git add -A`, never `git add .`, never `git checkout --`,
  never `git clean`. Stage named paths only.

### Verified live on 2026-08-23, do not re-derive

Every number below came from a probe against mainnet during design. They are recorded so
implementers do not each re-run them, and so a future reader can tell a measurement from
an assumption.

| Fact | Value |
|---|---|
| `LaunchpadFactory.coinCount()` | **146** |
| `Launched` events within `head-40_000` | **146** — i.e. the whole population |
| Earliest `Launched` block | **25_786_048** (33,702 blocks back from head 25_819_750) |
| `LAUNCHPAD_LOG_WINDOW_BLOCKS` today | 33_000 — **702 blocks too short** |
| Launches the current window sees | **66 of 146** |
| `CurveSwap` in `head-40_000` | **4,724** (the current 33_000 window sees 2,207) |
| Distinct traders, full history | **673** |
| Distinct creators, full history | **73** |
| `CurveSwap` in the last 1h / 6h / 24h / 48h | **1 / 18 / 46 / 84** |
| Coins with ≥1 swap in 1h / 6h / 24h / 48h | **1 / 6 / 10 / 14** |
| Launches in the last 24h | **0** |
| `Launched` emitter | `LAUNCHPAD_FACTORY`, not the hook |
| `CurveSwap` / `ImdBurned` emitter | `LAUNCHPAD_HOOK` |

---

## 1 · IMD MARKET drops the legacy v3 pool line

### What goes

The dim `legacy: v3 pool $NNN` line in `SurfMarket`, and its entire supply chain:

| Layer | Symbol |
|---|---|
| `data/surf_client.py` | `_pick_legacy_pair` and its call site; the `legacy_pool_liquidity_usd=` argument at ~:1838 |
| `data/surf_models.py` | `MarketSnapshot.legacy_pool_liquidity_usd` field (:212) and its `SURF_KEYS` entry (:445) |
| `data/surf_manager.py` | the payload pass-throughs at ~:672 and ~:2094 |
| `screens/surf.py` | the `legacy_pool_liquidity_usd=` kwarg (~:1068) |
| `widgets/surf/market.py` | the parameter, `legacy_line`, its `_parts` entry, and the `left_gap` seam at tier `full` |

### Why the whole chain and not just the line

Leaving the key in `SURF_KEYS` with no consumer is precisely open follow-up 4 from the
predecessor spec (`identities_written`, `lp_liquidity`), which exists because that
shortcut was taken before. A key nothing renders is a key nobody can tell is broken.

### Consequences to handle

- `SURF_KEYS` shrinks by one. The zero-catch probes in `tests/screens/test_surf_screen.py`
  partition `SURF_KEYS`, so `_NUMERIC_ZERO_PROBES` / `_NUMERIC_KEYS_EXCLUDED` /
  `_NON_NUMERIC_KEYS` must lose the same entry or their partition test fails. This is the
  regression the predecessor's fix wave hit twice (N1); expect it, do not be surprised by it.
- Five test files reference the key: `tests/test_surf_registration.py`,
  `tests/screens/test_surf_screen.py`, `tests/data/test_surf_client.py`,
  `tests/data/test_surf_models.py`, `tests/widgets/test_surf_widgets_a.py`.
- Removing the line **cannot widen** the market panel; confirm the panel's own measured
  width is unchanged or narrower, and leave `SURF_FULL_LAYOUT_COLUMNS` alone either way
  (the announce feed is the other binding panel and is being rewritten in §3, which is
  where the screen-width sweep belongs).

---

## 2 · Hero: `LAUNCHPAD · FLOW · BURN · SUPPLY`

### What goes, and why each

**LP goes because it is a constant.** `lp_state == "gone"` has been true since the
2026-08-17 migration and cannot become anything else: the v3 position was burned, so
`ownerOf(#1167726)` reverts permanently. A box whose only reachable state is
`MIGRATED / v3 position migrated` is decoration.

**POOL goes because every part of it is already on screen elsewhere.** Its USD liquidity
is `pool $548.7K` in IMD MARKET one row down; its decoy count has a seat on the signals
rail as DECOY POOL; its `v4` venue is now permanent.

### What arrives

Both boxes are fed by the **launchpad sweep that already runs** — `_launchpad_logs()`
holds every input in memory today and throws two of them away. **No new request.**

```
┌── LAUNCHPAD ──┐  ┌──── FLOW ─────┐
│               │  │               │
│  146 coins    │  │  4,724 swaps  │
│  0 new · 24h  │  │  673 traders  │
│  73 creators  │  │  0.075 ETH    │
└───────────────┘  └───────────────┘
```

**LAUNCHPAD** — `launchpad_coin_count` (existing, from `coinCount()`), plus two new keys:

- `launchpad_new_24h: int | None` — `Launched` events in the last 24h. Counted from the
  launch list already in hand. **Has a representable zero**: today it is genuinely `0`,
  which must render `0 new · 24h` and never an em-dash.
- `launchpad_creator_count: int | None` — distinct `creator` addresses over the full
  launch history. Also representably zero.

**FLOW** — three existing keys, none of them new: `launchpad_swap_count`,
`launchpad_trader_count`, `launchpad_creator_eth_owed`.

### The freshness problem, and its fix

The launchpad tier is 1800 s. The title bar's `as of HH:MM` is the **fast** tier's clock.
So without intervention these two boxes would show half-hour-old numbers under a clock
that says they are seconds old — "a stale number presented as live", which the house rules
forbid outright.

**The two launchpad-fed boxes carry the launchpad tier's own clock on their title line:**
`LAUNCHPAD · 20:20`, off the existing `launchpad_as_of_hhmm`. BURN and SUPPLY keep bare
titles — they are fed by the fast tier and the title bar's clock is already theirs.

At the `minimal` tier (13 columns) the clock is dropped from the title; at that width the
box is showing bare numbers and nothing else fits. This is the one place in this spec where
information is shed by width rather than shortened, and it is acceptable only because
`minimal` is unreachable on any terminal that can render this dashboard at all — the hero
row's boxes are a quarter of the screen, so 13 columns means a 52-column terminal.

### States

Per box, in the order a reader meets them:

| Condition | LAUNCHPAD renders | FLOW renders |
|---|---|---|
| Slot never read | `—` big line, dim `no read yet` | `—` big line, dim `no read yet` |
| Read, zero coins/swaps | `0 coins`, `0 new · 24h`, `0 creators` | `0 swaps`, `0 traders`, `— ETH` |
| Read, normal | `146 coins`, `0 new · 24h`, `73 creators` | `4,724 swaps`, `673 traders`, `0.075 ETH` |

An individual `None` inside an otherwise-read payload renders `—` for that line only. The
big line is never `0` when the read failed — the failure the SUPPLY box's docstring already
calls the false-BURN twin.

### Width

The hero's three tiers (`COMPACT_WIDTH` 22 / `TIGHT_WIDTH` 17 / `MINIMAL_WIDTH` 13) stay
as they are. `MINIMAL_WIDTH = 13` is currently anchored by `OWNER CHANGED` (LP's alarm) and
today's `2,730,424 IMD` (SUPPLY's quantity). **LP leaves, so `OWNER CHANGED` leaves with
it** — re-derive the anchor from the strings the row actually emits after this change
rather than assuming 13 still holds, and record the new anchor in the module docstring.
The existing `test_every_hero_tier_fits_the_width_it_advertises` renders every state at
every tier and is the check; extend it to the new boxes' states.

`HOOK_NOT_LIVE` / `HOOK_LAUNCHED` are dead exports kept alive only for a stale top-level
import in `tests/screens/test_surf_screen.py`. Delete both, and the import with them.

---

## 3 · ANNOUNCE FEED: threading

### The defect

`classify_channel_tx` routes **everything** `from == channel && to != channel` to `action`,
the contract-call bucket. But per `0x/packages/protocol/src/surf.ts` — the reference
implementation of this exact channel — that shape is a `legacy-reply`: an *authenticated
answer from the announcement wallet*.

Rendered from live data during design:

```
08-22 23:48  ACTION Yes the goal is for the protocol to be able to pay users compute…
08-22 08:34  REPLY  will my IMD NFT generate me $IMD rewards?
```

The ACTION is the answer to the REPLY below it. It is shown as a contract call, detached
from its question, and above it rather than under it.

**A second, worse consequence.** `surf_manager.py:~1737` feeds channel items with
`kind == "action"` into NEW DEPLOY's event stream, labelled with the decoded method or the
first four calldata bytes. So the answer above enters the deploy detector with the label
`0x59657320` — the ASCII for `"Yes "`. **NEW DEPLOY can fire on the dev writing a sentence
that begins with the right letters.** Reclassifying answers fixes this as a side effect;
the fix must be pinned by its own test, because it is not visible from the feed panel.

### 3.1 Classification

`CHANNEL_KINDS` grows from four to five: `("self", "reply", "answer", "action", "fund")`.
It is frozen in `data/surf_models.py` and re-exported from `analytics/surf_signals.py` —
`tests/analytics/test_surf_signals.py:2086` asserts the tuple is *not* redefined in the
analytics module, so it must stay a re-export.

`classify_channel_tx` gains one branch, in this order:

1. `from == to == channel` → `self`
2. `from == channel`:
   - `value == 0` **and** `decode_utf8_calldata(input) is not None` → **`answer`**
   - otherwise → `action`
3. `from` in dev wallets **and** (`value > 0` or the calldata is not a message) → `fund`
4. otherwise → `reply`

The `value == 0` guard is load-bearing and comes from the reference implementation's own
`transaction.value === 0n` test. Channel nonce 16 is `surf → 0xcb0b0531` carrying 0.05 ETH
and no text: it is a payment, not a message, and it stays `action`.

### 3.2 Empty action rows

That same nonce-16 row currently renders as `ACTION` followed by nothing — its calldata is
`0x`, so there is no text and no selector to label it with. An `action` row with neither
text nor label renders **its value** instead: `sent 0.05 ETH`. A row that renders nothing
is indistinguishable from a rendering bug.

### 3.3 Threading

A new pure module, `analytics/surf_feed.py`. No I/O, no Textual, `now_ts` injected. It
ports `buildSurfTimeline` + `buildSurfReplyRows` from
`0x/apps/web/src/model/surfThreads.ts`, which is the same channel's reference threading.

```python
def build_threads(items: Sequence[Mapping], ...) -> list[dict]
```

Rules, applied over items sorted **ascending** by `(ts, tx_hash)` — `ts` alone is not a
total order and `nonce` is per-sender, so the tx hash is the tiebreak:

- **`self` is a root.** Every root carries `replies: list[dict]`.
- **`reply` attaches to the newest root at or before its own timestamp.** A reply with no
  root before it is unthreaded and stays a top-level row (the reference calls these
  `unthreadedReplies`; the channel has some, from before the first self-post).
- **`answer` attaches to the most recent `reply` *from the address it was sent to***, via
  an `{address: newest inbound reply}` map walked in ascending order — the reference's
  `inboundByAuthor`. Depth 2. If no such reply exists, it attaches to the active root at
  depth 1.
- **`action` and `fund` are never threaded.** They are not messages; they stay top-level.

Output is ordered **newest root first** for display, replies **oldest first** within a
thread — the reference's ordering, and the one that reads as a conversation.

`_feed_items` in `surf_manager.py` must start carrying **`to_addr`**. It reads the field
today to classify and then discards it; threading cannot work without it.

### 3.4 Rendering

Collapsed by default. One toggle per root, revealing every descendant:

```
08-21 05:06  POST   To help bootstrap the protocol's compute power you'll need
                    an NFT, a codex or claude subscription…
             ▸ 2 replies
```

expanded — each depth exactly **one column** right of its parent:

```
             ▾ 2 replies
              REPLY  Should we have one VPS one GPT/Claude sub for every NFT…
               ANSWER you can run multiple per vps on same sub but need one NFT…
```

A root with no replies shows no toggle line at all. `answer` gets its own badge and colour,
distinct from both `REPLY` (dim) and `ACTION` (yellow): **`ANSWER`, cyan** — the same colour
as `POST`, because it has the same authenticated author, which is the whole point of
separating it from `ACTION`.

### 3.5 Two structural consequences

**`RichLog` cannot host a click target.** It renders through Rich markup, which has no
`@click`. `SurfFeed` becomes a `VerticalScroll` of per-row widgets, with the toggle a
focusable `Static` subclass carrying its root's `tx_hash`. Mouse click and
`enter`/`space`-while-focused both toggle. `_wrap_no_widow` and the width tiers survive
unchanged — they are pure functions over a string and a budget.

**`Static.update()` defers markup parsing into the message pump.** That is the failure
CLAUDE.md documents for `DataTable`: a malformed string raises *outside* the screen's
`try/except` and kills the app. `RichLog.write` parses synchronously at call time, which is
why the current widget is safe. So rows are handed **pre-built `rich.text.Text` objects**,
never markup strings — built inside the widget's own `try`, where a malformed item still
degrades to a skipped row exactly as `_item_lines` does today.

`safe_markup` remains mandatory on every third-party string regardless. Escaping and
pre-parsing are two independent guards and neither replaces the other.

### 3.6 State that must survive a refresh

Expansion state is a `dict[tx_hash, bool]` on the widget. The feed repaints on every poll
(30 s); collapsing what the reader just opened, every 30 seconds, would make the feature
unusable. Keyed by tx hash, not by row index, so a new post arriving at the top does not
shift what is open.

### 3.7 Width

The feed is one of the two panels binding `SURF_FULL_LAYOUT_COLUMNS = 143` (the other is
the dev-activity rail, at 63 against the feed's 76). Indentation adds up to **2 columns** to
the deepest row. Re-sweep the surf screen's full-layout width after this change, starting
away from 143 so the sweep cannot agree with the pin by construction.

**If the feed's need grows past its share, shorten `FULL_TEXT_WIDTH` (currently 71) rather
than raise the constant** — that is exactly the lever the 2026-08-11 seam work found to be
the cheap one, and it buys the wrapping with rows, which this panel has to spare.

`‹ widen` behaviour is unchanged: a clipped row is always announced.

---

## 4 · LAUNCHPAD view: layout and data repair

### 4.1 Layout

`#surf-launchpad-body` becomes a `Horizontal`, mirroring `#middle-row`:

```
#surf-launchpad-body   SurfLaunchpadCoins  |  #surf-launchpad-rail
                                           |    SurfCurveFlow
                                           |    SurfBurnPipeline
```

The rail gets `overflow-y: auto` and **`scrollbar-gutter: stable`**. That last property is
not cosmetic: curator's right rail needed it because without it the scrollbar stole a
column from the binding panel *only on terminals under 42 rows*, making the layout's width
requirement depend on its height and leaving one pin true at 48 rows and one column short
at 40.

**The arithmetic that keeps this under 143.** The coins table's eight columns are fixed and
do not shrink: `8+18+17+4+10+7+6+9 = 79` structural columns. §4.3 adds a ninth column, and
pays for it by shrinking CREATOR `17 → 11`, so the table stays at **79** exactly. The two
rail panels are label/value lines measured clear down to 60 columns; their widest line is
`owed 0.0751 ETH to creators` at 27. So a rail of ~34 and a table of 79 sum to ~117 with
padding — comfortably under FWA's 143, and the app-wide constant does not move.

**Sweep the seam, do not assume it.** The predecessor's own history is the argument: a 3:2
seam was replaced by 7:6 for a 24-column saving, and 7:6 is *today* three columns off
optimum because the panels' needs moved underneath it. Sweep seam by seam in
`tests/screens/test_surf_screen.py` and pick the cheapest that clears; pin
`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` to the measurement, starting the sweep away from both
93 and whatever the new number turns out to be.

`test_the_launchpad_binding_panel_is_the_coins_table` must still pass, or be re-pointed with
evidence if the rail genuinely becomes the binder.

### 4.2 The window bug

`LAUNCHPAD_LOG_WINDOW_BLOCKS = 33_000` is a **rolling** window measured back from head. The
launch history is **fixed at its start**. The earliest `Launched` is 702 blocks older than
the window, so:

- **80 of 146 coins are invisible**, including the two busiest pools on the launchpad
  (677 and 660 swaps). Those two have no ticker, no name and no creator, and can never
  reach the table however it is sorted.
- It loses roughly 7,200 more blocks of launch history **every day**. This is not a
  threshold that was set slightly wrong; it is a shape that is wrong.
- It also halves the swap history: 2,207 of 4,724.

**Fix.** Sweep `Launched` from a vendored first block:

```python
#: Block of the first `Launched` event. A deploy block is immutable — this is
#: not a documented value that can drift, it is chain history.
#: Verified 2026-08-23: the 146 events at and after this block are the entire
#: population, and `LaunchpadFactory.coinCount()` agrees at 146.
LAUNCHPAD_FIRST_BLOCK = 25_786_048
```

This does not contradict the "read values live, never hardcode a documented one" rule. That
rule exists because *documented* values drift — a 5% fee that is 1% on chain, a "4.0×" ratio
that measured 3.885×, then 3.49×, then 2.956×. A block number that has already been mined
cannot drift. It is vendored on the same footing as a contract address, and like an address
it is verified by what it produces: **if the sweep's launch count disagrees with
`coinCount()`, the panel says so** rather than quietly ranking a subset.

**Cursor, so the sweep does not grow without bound.** A fixed-start sweep re-fetches the
same history every 30 minutes and grows ~7,200 blocks a day. Both log streams are
append-only, so the launchpad slot persists a cursor and each sweep fetches only
`last_block + 1 .. head`. Curator's `SLOT_CLUSTERS` resumable cursor is the precedent.
Strictly-greater-than, so a re-swept boundary block cannot double-count.

The slot carries:

| Field | Meaning | Growth |
|---|---|---|
| `last_block` | highest block swept | — |
| `launches` | one row per coin, keyed by `pool_id` | bounded by `coinCount()` |
| `swaps_all` | `{pool_id: cumulative count}` | bounded by coin count |
| `swaps_recent` | swap rows newer than `head - LAUNCHPAD_DAY_BLOCKS`, pruned each sweep | bounded by a day's volume |

`swaps_recent` is what `swaps_24h` and `change_24h_pct` are computed from, and pruning it
every sweep is what bounds it. The 30-minute tier refreshes far more often than the 7,200
-block day it retains, so the buffer can never develop a hole.

On a cold cache the first sweep is the whole history — 34k blocks today, once. That is the
only unbounded read here, and it is the one that cannot be avoided.

**A cursor makes `swaps_all` a persisted accumulator, which is the shape the house rules
warn about**: never write a sentinel into a history series, and never let a failed read
become a `0` that outlives the outage. So a failed sweep **leaves the cursor and every
counter untouched** — it does not advance `last_block`, does not zero a counter, and does
not write a partial merge. The next sweep resumes from the same place. A partial sweep is
indistinguishable from an outage here and is treated as one.

### 4.3 The ranking bug

The table ranks by `swaps_1h`. In the hour measured during design, **1 swap occurred across
all 146 coins**. So every coin ranked 0, the sort fell through to `-age_s`, and the panel
showed the twenty oldest never-traded coins — identical initial curve price
(`3.20e-09` for all twenty), `--` change, `0` swaps. That is the screenshot.

**Fix:**

| Before | After |
|---|---|
| rank by `swaps_1h`, tiebreak `-age_s` | rank by `swaps_24h`, tiebreak `swaps_all`, then `-age_s` |
| `change_1h_pct` | `change_24h_pct` |
| column `SWAPS` (1h) | columns `SWAPS 24H` and `SWAPS ALL` |
| `CREATOR` 17 cols | `CREATOR` 11 cols — pays for the new column, table stays 79 |
| title `1H%` | title `24H%` |

`LAUNCHPAD_HOUR_BLOCKS = 300` is replaced by `LAUNCHPAD_DAY_BLOCKS = 7_200` (24 h at the
12 s block time already vendored as `_LAUNCHPAD_BLOCK_SECONDS`). Derive it from that
constant rather than writing 7_200 as a literal, so a block-time change moves both together.

24h is the shortest window with enough data to rank: 46 swaps across 10 active coins,
against 1 across 1 at an hour. It is also the shortest window that repairs HOT COIN (below).

`change_24h_pct` keeps the existing derivation — first vs last in-window swap's effective
price, `ethAmount/coinAmount`, `None` when fewer than two swaps carry a usable price.
**`None`, never `0.0`**: "no measurable move" is not the claim "a flat day".

### 4.4 HOT COIN

The detector needs `HOT_MIN_ACTIVE = 5` active coins to have a median at all. At an hour it
sees 1 and is permanently dark — it has never fired and cannot. At 24h it sees 10.

`swaps_by_coin` becomes the 24h distribution. `HOT_MAX_AGE_S` is pinned by
`test_the_hot_coin_staleness_bound_is_the_window_it_measures` to *the window it measures*,
so it moves 3600 → 86400 with it, and that test is what keeps the two honest.

`HOT_MULTIPLE = 3` and `HOT_FLOOR = 5` are unchanged. Against today's 24h distribution the
bar lands at `max(5, median×3)`; with 10 active coins and a median of 1, that is 5 — so IMD
(18 swaps) and FREN PET (14) clear it and nothing else does. A detector that fires on 2 of
146 coins is behaving.

### 4.5 The count disagreement is itself a signal

Once launches are swept from a fixed start, `len(launches)` should equal `coinCount()`. When
it does not, the panel's title says so — `146 coins · 66 read` — rather than rendering a
subset as if it were the population. That is the check that would have caught this bug on
the day it appeared, and it costs one comparison of two numbers already in hand.

---

## Testing

Every task lands with tests before code. Beyond the per-task cases the plan will enumerate:

**Structural / anti-regression:**

- No test opens a socket. The injected transport raises on use.
- `SURF_KEYS` and the zero-catch probe partition agree after §1's removal and §2's additions.
- `CHANNEL_KINDS` is defined once, in `data/surf_models.py`, and re-exported.

**Behavioural, one per defect this spec fixes** — each must be shown to bite:

1. An `answer`-shaped tx is classified `answer`, not `action`.
2. An `answer`-shaped tx does **not** enter NEW DEPLOY's event stream (the `0x59657320`
   false positive).
3. A `surf → X` tx carrying value and no text is still `action`, and renders its value.
4. An answer nests under the reply from the address it was sent to, at depth 2 — not under
   the root.
5. A reply with no preceding root stays top-level rather than vanishing.
6. Expansion state survives a repaint with a new item at the top.
7. A malformed feed item degrades to a skipped row and does not blank the panel — the
   deferred-parse crash path, asserted against composited output.
8. A launch at exactly `LAUNCHPAD_FIRST_BLOCK` is included (boundary), and a cursor resume
   at block `N` does not double-count a launch at `N`.
8b. A **failed** sweep leaves `last_block` and every `swaps_all` counter exactly as they
   were — no advance, no zero, no partial merge — and the next sweep resumes from the same
   block. This is the persisted-accumulator hazard and it gets a mutation check.
9. `len(launches) != coinCount()` renders the disagreement in the title.
10. With a fixture where the last hour is empty but the last day is not, the coins table
    ranks by 24h volume rather than falling through to age.
11. HOT COIN fires against a 24h fixture with 10 active coins and stays dark at 4.

**Width, measured not asserted from memory:** re-sweep the surf screen and the launchpad
body, each starting away from its pin. `__main__.FULL_LAYOUT_COLUMNS` must still be 143 at
the end, and the plan's last task verifies it.

---

## Explicitly out of scope

- The NFT-as-daemon-licence reframing. Parked at the user's request on 2026-08-23 and still
  parked.
- Any change to the `y` or `c` bindings, or to any other dashboard.
- `imd.fun` as a data source.
- The predecessor's open follow-ups 1 (`fp_best_plays.py` escaping — a live FrenPet defect
  that deserves its own branch), 2 (the dead `v4_initializes` sweep), 3
  (`price_source_disagreement_pct` rendering `0` and `None` alike) and 4
  (`identities_written` / `lp_liquidity` having no consumers). §1 removes a *third*
  consumerless key rather than adding one; it does not clear the existing two.
