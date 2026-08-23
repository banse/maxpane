# Surf feed threading, hero rebuild, launchpad repair — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thread the announce feed, replace two dead hero cards with the launchpad's own
numbers, drop IMD MARKET's legacy v3 line, and repair the launchpad view's layout and data.

**Architecture:** The data contract (`data/surf_models.py`) is frozen in Task 1 so every
later task builds against one interface. Pure analytics (`analytics/surf_feed.py`,
`analytics/surf_launchpad.py`) come before the client that feeds them, which comes before
the manager that caches it, which comes before the widgets that render it. `screens/surf.py`
has exactly one owner (Task 12) and every width sweep happens last (Task 13), after every
string that could move a width is final.

**Tech Stack:** Python 3.11, Textual, pytest, keyless JSON-RPC (publicnode for state,
tenderly/drpc for logs) and Blockscout REST.

**Spec:** `docs/superpowers/specs/2026-08-23-surf-feed-hero-launchpad-design.md`

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include these.

- **Read-only.** No signer, no transactor, no calldata construction for a state change, no
  key or keystore. Nothing in this plan calls a contract that mutates.
- **Keyless.** No new source, no API key, ever.
- **No test touches the network.** Inject a transport that raises on use. Every external
  payload a test needs is a committed fixture under `tests/fixtures/surf/`.
- **A failed read is `None`, never `0`.** A representable zero and an unknown must render
  differently, and the difference must be visible on screen.
- **Escape every third-party string** through `widgets/markup_safety.safe_markup`.
- **Assert against composited output** (`_compositor.render_strips()`), never the content
  string. **Prove a test bites**: mutate the code, watch it go red, restore, and say so in
  the report.
- **Inject the clock.** No new module may call `time.time()` internally; take `now_ts`/`now=`.
- **Do not move `__main__.FULL_LAYOUT_COLUMNS` (143) or `SURF_FULL_LAYOUT_COLUMNS` (143).**
  When a new value would widen a sized cell, shorten the value.
- **The working tree holds ~300 untracked curator fixtures that are the user's own
  uncommitted work.** Never `git add -A`, never `git add .`, never `git checkout --`, never
  `git clean`. Stage named paths only. `docs/superpowers/` is gitignored, so committing a
  doc there needs `git add -f <path>`.
- **Run tests as `.venv/bin/python -m pytest`.** The system `python3` lacks the deps.

### Verified live on 2026-08-23 — use these, do not re-probe

| Fact | Value |
|---|---|
| `LaunchpadFactory.coinCount()` | 146 |
| Earliest `Launched` block | 25_786_048 |
| `LAUNCHPAD_LOG_WINDOW_BLOCKS` today | 33_000 — 702 blocks too short |
| Launches the current window sees | 66 of 146 |
| `CurveSwap` in `head-40_000` | 4,724 (current window sees 2,207) |
| Distinct traders / creators, full history | 673 / 73 |
| `CurveSwap` in 1h / 6h / 24h / 48h | 1 / 18 / 46 / 84 |
| Coins with ≥1 swap in 1h / 24h | 1 / 10 |
| Launches in the last 24h | 0 |
| `Launched` emitter | `LAUNCHPAD_FACTORY` |
| `CurveSwap` / `ImdBurned` emitter | `LAUNCHPAD_HOOK` |
| `TIER_LAUNCHPAD` TTL / backoff | 600 s / 180 s (`data/surf_cache.py`) |

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `maxpane_dashboard/analytics/surf_feed.py` | Pure threading: classified feed items → root/reply/answer tree. No I/O, no Textual. |
| `tests/analytics/test_surf_feed.py` | Table tests for the threading rules, including hostile and degenerate shapes. |
| `tests/fixtures/surf/feed/threaded_channel.json` | A captured channel page containing a post, two inbound replies and two announcement-wallet answers. |
| `tests/fixtures/surf/launchpad/cursor_resume.json` | Two overlapping log pages for the cursor double-count test. |

**Modified**

| File | Change | Owner task |
|---|---|---|
| `data/surf_models.py` | The whole contract: `CHANNEL_KINDS`, `SURF_KEYS`, `SURF_ROW_KEYS`, `LaunchpadCoin`, `LaunchpadState` | 1 |
| `tests/test_surf_registration.py` | Zero-catch triage buckets follow `SURF_KEYS` | 1 (then 2, 9) |
| `data/surf_addresses.py` | `LAUNCHPAD_FIRST_BLOCK` | 5 |
| `data/surf_client.py` | Legacy pair removal (2); launchpad sweep, cursor, 24h aggregates (6) | 2, 6 |
| `analytics/surf_signals.py` | `classify_channel_tx` gains `answer`; `_detect_deploy` stops eating answers | 3 |
| `analytics/surf_launchpad.py` | `rank_coins` ranks on 24h; `HOT_MAX_AGE_S` follows its window | 7 |
| `data/surf_manager.py` | `to_addr` in `_feed_items`, deploy stream (3); slot cursor + payload (8) | 3, 8 |
| `widgets/surf/market.py` | Legacy line removed | 2 |
| `widgets/surf/hero.py` | POOL/LP → LAUNCHPAD/FLOW | 9 |
| `widgets/surf/feed.py` | Threaded, collapsible rendering | 10 |
| `widgets/surf/launchpad.py` | Table columns | 11 |
| `screens/surf.py` | Wiring + the launchpad rail + CSS | 12 |
| `CLAUDE.md`, `README.md` | Docs | 13 |

---

## Task 1: Freeze the data contract

**Files:**
- Modify: `maxpane_dashboard/data/surf_models.py`
- Modify: `tests/test_surf_registration.py:1121-1400` (the three triage buckets)
- Test: `tests/data/test_surf_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: every name below. Later tasks build against these exact spellings.

```python
CHANNEL_KINDS: tuple[str, ...] = ("self", "reply", "answer", "action", "fund")

SURF_ROW_KEYS["feed_items"] = (
    "ts", "kind", "from_addr", "to_addr", "from_label", "text", "tx_hash",
)
SURF_ROW_KEYS["launchpad_coins"] = (
    "ticker", "name", "creator", "creator_known", "age_s", "price_eth",
    "change_24h_pct", "swaps_24h", "swaps_all", "imd_burned",
)

@dataclass(frozen=True, slots=True)
class LaunchpadCoin:
    ticker: str
    name: str
    creator: str
    age_s: float | None
    price_eth: float | None
    change_24h_pct: float | None
    swaps_24h: int
    swaps_all: int
    imd_burned: float | None
```

`LaunchpadState` gains three fields, all `int | None` with a representable zero:
`launch_count`, `new_24h`, `creator_count`. `swaps_by_coin` keeps its name and type
(`dict[str, int] | None`) but its docstring now says **24 h**, not "the hour".

`SURF_KEYS` loses `legacy_pool_liquidity_usd` and gains, in the launchpad block:

```python
    "launchpad_launch_count",       # int | None — Launched events swept, vs coin_count
    "launchpad_new_24h",            # int | None — Launched events in the last 24h
    "launchpad_creator_count",      # int | None — distinct creators, full history
```

- [ ] **Step 1: Write the failing contract tests**

Append to `tests/data/test_surf_models.py`:

```python
def test_channel_kinds_carries_the_authenticated_answer():
    """`answer` is the announcement wallet replying to a reply.

    Per 0xTXT (`0x/packages/protocol/src/surf.ts`) a `surf -> X` zero-value tx
    carrying UTF-8 is a `legacy-reply`, not a contract call. Folding it into
    `action` is what detached the dev's answers from the questions they answer.
    """
    from maxpane_dashboard.data.surf_models import CHANNEL_KINDS

    assert CHANNEL_KINDS == ("self", "reply", "answer", "action", "fund")


def test_feed_rows_carry_the_recipient_threading_needs():
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS

    assert "to_addr" in SURF_ROW_KEYS["feed_items"]


def test_launchpad_rows_rank_on_a_day_and_keep_the_all_time_tiebreak():
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS

    row = SURF_ROW_KEYS["launchpad_coins"]
    assert "swaps_24h" in row and "swaps_all" in row and "change_24h_pct" in row
    assert "swaps_1h" not in row and "change_1h_pct" not in row


def test_the_superseded_v3_liquidity_key_is_gone():
    """Removed with its whole supply chain, not orphaned in the contract.

    A key nothing renders is a key nobody can tell is broken -- the exact
    shape of open follow-ups 4 from the predecessor branch.
    """
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    assert "legacy_pool_liquidity_usd" not in SURF_KEYS


def test_the_launchpad_population_keys_exist():
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    for key in ("launchpad_launch_count", "launchpad_new_24h",
                "launchpad_creator_count"):
        assert key in SURF_KEYS
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/bin/python -m pytest tests/data/test_surf_models.py -k "channel_kinds or recipient or tiebreak or superseded or population" -v
```

Expected: five failures — `AssertionError` on each.

- [ ] **Step 3: Make the contract changes**

In `maxpane_dashboard/data/surf_models.py`, apply exactly the definitions in the
**Interfaces** block above. Update each docstring the change invalidates:

- `CHANNEL_KINDS` — say what `answer` is and cite `0x/packages/protocol/src/surf.ts`.
- `LaunchpadCoin` — `swaps_24h` is the ranking key; `swaps_all` the tiebreak; both have a
  representable zero (a coin that has never traded really has `0`), while `change_24h_pct`
  is `None` when fewer than two in-window swaps carry a usable price — *"no measurable
  move" is not the claim "a flat day"*.
- `LaunchpadState` — `launch_count` is what the sweep found and `coin_count` is what the
  factory says; when they disagree the panel says so rather than ranking a subset.

- [ ] **Step 4: Re-triage the zero-catch buckets**

`tests/test_surf_registration.py` partitions **every** `SURF_KEYS` entry into
`_NON_NUMERIC_KEYS`, `_NUMERIC_KEYS_EXCLUDED` or `_NUMERIC_ZERO_PROBES`, and
`test_every_surf_key_is_triaged_for_the_zero_catch` derives its check from the live tuple.
So this step is not optional — it is what that test exists to force.

- Delete the `"legacy_pool_liquidity_usd": "legacy: v3 pool $0"` entry from
  `_NUMERIC_ZERO_PROBES` (line ~1383).
- The three new keys have **no consumer until Task 9/11/12**. Do not guess a needle: an
  unverified probe string passes by absence and covers nothing — the exact defect the
  predecessor's fix wave found in four of ten needles. Add them to a new, explicitly
  temporary bucket instead:

```python
#: Keys whose rendering consumer lands in a LATER task of this plan. They are
#: numeric and they WILL need real zero-catch probes -- but a probe string
#: invented before the widget exists passes by absence and proves nothing,
#: which is how four of ten needles went vacuous on the predecessor branch.
#: Task 12 empties this set and moves every entry into `_NUMERIC_ZERO_PROBES`
#: with a needle read off composited output.
_KEYS_PENDING_CONSUMERS = frozenset({
    "launchpad_launch_count",
    "launchpad_new_24h",
    "launchpad_creator_count",
})
```

Include `_KEYS_PENDING_CONSUMERS` in the exhaustiveness union, and add the guard that
makes it self-deleting:

```python
def test_the_pending_consumer_bucket_is_empty_by_the_end_of_this_plan():
    """`_KEYS_PENDING_CONSUMERS` is scaffolding with an expiry date.

    Task 12 wires the last consumer and moves every entry into
    `_NUMERIC_ZERO_PROBES` with a needle verified against composited output.
    This test is what stops the scaffolding from becoming permanent.
    """
    assert _KEYS_PENDING_CONSUMERS == frozenset()
```

Mark that one `@pytest.mark.xfail(strict=False, reason="emptied by Task 12")` **only for
the duration of this plan**, and delete the marker in Task 12. A strict xfail would plant a
red test in a suite required to be green; a non-strict one flips to a pass the moment the
set empties, which is the signal wanted.

- [ ] **Step 5: Run the full contract surface**

```bash
.venv/bin/python -m pytest tests/data/test_surf_models.py tests/test_surf_registration.py -q
```

Expected: green except for failures that name `legacy_pool_liquidity_usd`,
`change_1h_pct`, `swaps_1h` or `to_addr` in code not yet updated — those belong to Tasks 2,
3, 6 and 11. **List them in the report**; do not fix them here and do not silence them.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_models.py tests/data/test_surf_models.py tests/test_surf_registration.py
git commit -m "feat(surf): freeze the feed-threading and launchpad-repair data contract"
```

---

## Task 2: IMD MARKET drops the legacy v3 pool line

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py` (`_pick_legacy_pair` and its call site, and the `legacy_pool_liquidity_usd=` argument at ~:1838)
- Modify: `maxpane_dashboard/data/surf_manager.py:~672` and `~2094`
- Modify: `maxpane_dashboard/widgets/surf/market.py` (the parameter at :559 and :778, `legacy_line` at :589-592, the `_parts` entry at :618, the `left_gap` seam at :694)
- Modify: `maxpane_dashboard/screens/surf.py:~1068` (delete the kwarg — one line)
- Test: `tests/widgets/test_surf_widgets_a.py`, `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: Task 1's `SURF_KEYS` without `legacy_pool_liquidity_usd`.
- Produces: `SurfMarket.update_data()` no longer accepts `legacy_pool_liquidity_usd`;
  `MarketSnapshot` has no such field.

- [ ] **Step 1: Write the failing test**

In `tests/widgets/test_surf_widgets_a.py`:

```python
@pytest.mark.asyncio
async def test_the_market_panel_no_longer_carries_the_superseded_v3_pool():
    """The v3 pool was drained on 2026-08-17 and its position burned.

    Its liquidity is not a second opinion on the live pool's -- it is a
    number about a pool that no longer exists.
    """
    class P(App):
        CSS = "SurfMarket { width: 90; height: 20; }"
        def compose(self) -> ComposeResult:
            yield SurfMarket()

    app = P()
    async with app.run_test(size=(90, 24)) as pilot:
        app.query_one(SurfMarket).update_data(
            imd_price_usd=1.17, imd_change_24h_pct=2.5, imd_vol_24h_usd=244_200.0,
            pool_liquidity_usd=548_700.0, fp_price_usd=1.14, parity_pct=2.5,
        )
        await pilot.pause()
        out = _composited(app)

    assert "legacy" not in out.lower()
    assert "pool $548.7K" in out  # the LIVE pool still renders
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -k superseded -v
```

Expected: PASS on the `legacy` assertion by accident (the payload has no legacy figure, so
the line is blank), FAIL only if `pool $548.7K` does not render. **This test as written does
not bite.** Fix it before proceeding by passing the key explicitly and asserting the
`TypeError`-free removal instead:

```python
        with pytest.raises(TypeError):
            _parts(legacy_pool_liquidity_usd=1.0)   # the private builder, not update_data
```

`update_data` swallows unknown kwargs through `**_kwargs`, so it can never raise — assert
against `market._parts`, which does not. Re-run and confirm it fails with "unexpected
keyword" absent (i.e. `_parts` still accepts it).

- [ ] **Step 3: Remove the chain, top to bottom**

Delete, in this order so the tree never holds a call to something that is gone:

1. `screens/surf.py:~1068` — the `legacy_pool_liquidity_usd=data.get(...)` kwarg.
2. `widgets/surf/market.py` — the `_parts` parameter, the `legacy` / `legacy_line` locals,
   the `"legacy_line"` entry in the returned dict, the `left_gap` assignment at tier `full`
   (replace with `left_gap = ""`), the `update_data` parameter, its `_payload` entry, and
   both docstring paragraphs describing it (the module docstring at :198-215 and the
   `update_data` note at :784).
3. `data/surf_manager.py` — the pass-throughs at `~672` and `~2094`.
4. `data/surf_client.py` — the `legacy_pool_liquidity_usd=self._f(...)` argument at ~:1838,
   then `_pick_legacy_pair` itself and its call site. Confirm with
   `rg -n "legacy" maxpane_dashboard/` that nothing survives except unrelated words.
5. `data/surf_models.py` — the `MarketSnapshot.legacy_pool_liquidity_usd` field at :212 and
   its docstring paragraph at :190.

- [ ] **Step 4: Run the affected suites**

```bash
.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py tests/data/test_surf_client.py tests/data/test_surf_models.py tests/test_surf_registration.py -q
```

Expected: green. Any test still naming `legacy_pool_liquidity_usd` must be **deleted or
re-pointed**, not skipped — the behaviour it covered no longer exists.

- [ ] **Step 5: Prove the removal bites**

Re-add the `left_gap = parts["legacy_line"]` line temporarily and confirm a `KeyError`
reaches a test rather than a user. Restore. Record the mutation in the report.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_client.py maxpane_dashboard/data/surf_manager.py maxpane_dashboard/data/surf_models.py maxpane_dashboard/widgets/surf/market.py maxpane_dashboard/screens/surf.py tests/
git commit -m "refactor(surf): drop the superseded v3 pool line and its whole supply chain"
```

---

## Task 3: `answer` classification, `to_addr`, and NEW DEPLOY's false positive

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py:363-395` (`classify_channel_tx`)
- Modify: `maxpane_dashboard/data/surf_manager.py:1236-1276` (`_feed_items`) and `~1724-1740` (the deploy event stream)
- Test: `tests/analytics/test_surf_signals.py`, `tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: Task 1's `CHANNEL_KINDS` and `SURF_ROW_KEYS["feed_items"]`.
- Produces: `classify_channel_tx(from_addr, to_addr, value_wei, input_hex) -> str` may now
  return `"answer"`; `_feed_items` rows carry `to_addr: str | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/analytics/test_surf_signals.py`:

```python
_ANN = "0x200e710acaa6a93bbc77146026328c40f1d60fb1"
_STRANGER = "0x6eacf11c0000000000000000000000000000dead"
# "Yes the goal is..." -- the real channel nonce 23, abbreviated.
_ANSWER_HEX = "0x" + "Yes the goal is".encode().hex()


def test_the_channel_answering_a_stranger_is_an_answer_not_a_contract_call():
    """0xTXT calls this shape `legacy-reply`: an authenticated Agent Surf answer.

    Classifying it `action` put the dev's replies in the contract-call bucket,
    detached from the question they answer.
    """
    assert classify_channel_tx(_ANN, _STRANGER, 0, _ANSWER_HEX) == "answer"


def test_the_channel_sending_value_with_no_message_is_still_an_action():
    """Channel nonce 16: `surf -> 0xcb0b0531`, 0.05 ETH, empty calldata.

    A payment is not a message. The `value == 0` guard is the reference
    implementation's own `transaction.value === 0n` test.
    """
    assert classify_channel_tx(_ANN, _STRANGER, 50_000_000_000_000_000, "0x") == "action"


def test_the_channel_making_a_real_contract_call_is_still_an_action():
    """The ERC-8004 register() at channel nonce 4 -- calldata that is not UTF-8."""
    assert classify_channel_tx(_ANN, _STRANGER, 0, "0xffffffff") == "action"


def test_a_self_post_is_unaffected():
    assert classify_channel_tx(_ANN, _ANN, 0, _ANSWER_HEX) == "self"
```

In `tests/data/test_surf_manager.py`:

```python
def test_feed_rows_carry_the_recipient(surf_manager):
    """Threading needs to know who an answer was sent to.

    `_feed_items` reads `to_addr` to classify and then dropped it, which is
    why the announcement wallet's answers could not be nested.
    """
    rows = [SimpleNamespace(ts=1.0, nonce=23, from_addr=_ANN, to_addr=_STRANGER,
                            value_wei=0, input_hex=_ANSWER_HEX, tx_hash="0xaa",
                            method=None)]
    items = surf_manager._feed_items(rows)
    assert items[0]["to_addr"] == _STRANGER
    assert items[0]["kind"] == "answer"


def test_an_answer_never_reaches_the_deploy_detector(surf_manager):
    """NEW DEPLOY reads channel items with kind == "action" and labels them
    with the decoded method, falling back to the first four calldata bytes.

    So before this change the answer above entered the deploy stream labelled
    `0x59657320` -- the ASCII for "Yes ". NEW DEPLOY could fire on the dev
    writing a sentence that begins with the right letters.
    """
    items = [{"ts": 1.0, "kind": "answer", "tx_hash": "0xaa", "label": "0x59657320"}]
    events = surf_manager._deploy_events(items, activity_rows=[], activity_read=True)
    assert [e["tx_hash"] for e in events] == []
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k "answer or contract_call or self_post" tests/data/test_surf_manager.py -k "recipient or deploy_detector" -v
```

Expected: `test_the_channel_answering_a_stranger_...` fails with `'action' != 'answer'`;
the `to_addr` test fails with `KeyError`; the deploy test fails or errors on the missing
helper.

- [ ] **Step 3: Add the `answer` branch**

Replace the body of `classify_channel_tx` (`analytics/surf_signals.py:387-395`) with:

```python
    src = _addr(from_addr)
    dst = _addr(to_addr)
    if src == _CHANNEL:
        if dst == _CHANNEL:
            return "self"
        # 0xTXT `legacy-reply`: an authenticated answer from the channel to
        # somebody who wrote to it. Both guards come from the reference
        # implementation (0x/packages/protocol/src/surf.ts): zero value, and
        # calldata that decodes as a message. A 0.05 ETH transfer with empty
        # calldata (channel nonce 16) is a payment, not a message.
        if (_as_int(value_wei) or 0) == 0 and decode_utf8_calldata(input_hex) is not None:
            return "answer"
        return "action"
    if src in _DEV_WALLETS:
        value = _as_int(value_wei) or 0
        if value > 0 or decode_utf8_calldata(input_hex) is None:
            return "fund"
    return "reply"
```

Update the docstring's numbered rule list to match — it currently documents four rules and
this is five.

- [ ] **Step 4: Carry `to_addr`, and stop feeding answers to NEW DEPLOY**

In `data/surf_manager.py::_feed_items`, hoist the recipient out of the inline call and add
it to the emitted dict:

```python
            to_addr = str(_field(row, "to_addr") or "") or None
            kind = _safe_call(
                classify_channel_tx, from_addr, to_addr or "",
                _opt_int(_field(row, "value_wei")) or 0, input_hex, default=None,
            )
            items.append({
                "ts": _opt_float(_field(row, "ts")),
                "kind": kind,
                "from_addr": from_addr,
                "to_addr": to_addr,
                "from_label": KNOWN_LABELS.get(from_addr.lower()),
                ...
            })
```

`to_addr` is `None`, never `""`, for a contract creation — the same three-state rule
`_parse_channel_tx` already documents.

Then extract the deploy-event assembly at `~1724-1740` into a named method so the test above
can reach it, keeping the `kind == "action"` filter exactly as it is. The filter needs no
change: `answer` rows simply no longer match it, which is the fix.

```python
    @staticmethod
    def _deploy_events(feed_items, activity_rows, activity_read: bool):
        """NEW DEPLOY's event stream: dev-wallet deploys plus channel actions.

        The channel branch is gated on `activity_read` as well, and that is
        load-bearing -- `[]` claims "the deploy window was read and held
        nothing" and seeds the baseline, so one source may not make that
        claim on the other's behalf.

        `answer` rows are excluded by the `kind == "action"` filter and that
        exclusion is the point: before `answer` existed, the dev's own text
        replies entered here labelled with the first four bytes of their own
        calldata, so NEW DEPLOY could fire on a sentence.
        """
```

- [ ] **Step 5: Run and prove both bite**

```bash
.venv/bin/python -m pytest tests/analytics/test_surf_signals.py tests/data/test_surf_manager.py -q
```

Then mutate: change `== 0` to `>= 0` in the new branch and confirm the value test goes red;
change the deploy filter to `in ("action", "answer")` and confirm the deploy test goes red.
Restore both. Record both mutations in the report.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/analytics/surf_signals.py maxpane_dashboard/data/surf_manager.py tests/analytics/test_surf_signals.py tests/data/test_surf_manager.py
git commit -m "fix(surf): the channel's own answers are replies, not contract calls"
```

---

## Task 4: `analytics/surf_feed.py` — the threading

**Files:**
- Create: `maxpane_dashboard/analytics/surf_feed.py`
- Create: `tests/analytics/test_surf_feed.py`
- Create: `tests/fixtures/surf/feed/threaded_channel.json`

**Interfaces:**
- Consumes: Task 1's `SURF_ROW_KEYS["feed_items"]`; Task 3's `answer` kind.
- Produces:

```python
def build_threads(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group classified feed items into display rows, newest root first.

    Each returned dict is:
        {"item": <the feed item>, "depth": int, "replies": list[dict]}
    Roots have depth 0 and carry their descendants in `replies`, already
    flattened and depth-tagged (a reply is depth 1, an answer to that reply
    depth 2). Top-level non-message rows (`action`, `fund`) and unthreaded
    replies are returned as roots with an empty `replies` list.
    """
```

Ported from `0x/apps/web/src/model/surfThreads.ts` (`buildSurfTimeline` +
`buildSurfReplyRows`), which is the reference implementation for this exact channel.
**Read that file before writing this one.**

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_surf_feed.py`:

```python
"""Threading rules for the announce channel, ported from 0xTXT.

The channel is permissionless, so every rule here has to survive a hostile
or degenerate input: a reply with no post before it, an answer to nobody, a
malformed timestamp, two items in the same second.
"""
import json
from pathlib import Path

from maxpane_dashboard.analytics.surf_feed import build_threads

_ANN = "0x200e710acaa6a93bbc77146026328c40f1d60fb1"
_ASKER = "0x6eacf11c0000000000000000000000000000dead"
_OTHER = "0xef5212b20000000000000000000000000000beef"


def _item(ts, kind, tx, frm=_ANN, to=_ANN, text="x"):
    return {"ts": ts, "kind": kind, "from_addr": frm, "to_addr": to,
            "from_label": None, "text": text, "tx_hash": tx}


def test_a_reply_nests_under_the_post_that_preceded_it():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "reply", "0xq", frm=_ASKER, to=_ANN),
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xpost"]
    assert [(r["item"]["tx_hash"], r["depth"]) for r in threads[0]["replies"]] == [("0xq", 1)]


def test_an_answer_nests_under_the_reply_from_the_address_it_was_sent_to():
    """The rule that makes this a reply-to-a-reply rather than a second reply.

    0xTXT's `inboundByAuthor`: an answer's parent is the most recent inbound
    reply from the address the answer is addressed to.
    """
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "reply", "0xq1", frm=_OTHER, to=_ANN),
        _item(300, "reply", "0xq2", frm=_ASKER, to=_ANN),
        _item(400, "answer", "0xa", frm=_ANN, to=_ASKER),
    ])
    rows = {r["item"]["tx_hash"]: r for r in threads[0]["replies"]}
    assert rows["0xa"]["depth"] == 2
    assert rows["0xa"]["parent_tx_hash"] == "0xq2"   # _ASKER's, not _OTHER's


def test_an_answer_to_nobody_falls_back_to_the_root_at_depth_one():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(400, "answer", "0xa", frm=_ANN, to=_ASKER),
    ])
    row = threads[0]["replies"][0]
    assert row["depth"] == 1 and row["parent_tx_hash"] == "0xpost"


def test_a_reply_with_no_post_before_it_stays_top_level():
    """The channel has these -- replies that predate the first self-post.

    Dropping them would be silent data loss on a permissionless feed.
    """
    threads = build_threads([_item(50, "reply", "0xorphan", frm=_ASKER, to=_ANN)])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xorphan"]
    assert threads[0]["depth"] == 0 and threads[0]["replies"] == []


def test_actions_and_funds_are_never_threaded():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "action", "0xact", frm=_ANN, to=_OTHER),
        _item(300, "fund", "0xfund", frm=_OTHER, to=_ANN),
    ])
    assert {t["item"]["tx_hash"] for t in threads} == {"0xpost", "0xact", "0xfund"}
    assert threads[0]["replies"] == [] if threads[0]["item"]["tx_hash"] == "0xpost" else True


def test_roots_come_back_newest_first_and_replies_oldest_first():
    threads = build_threads([
        _item(100, "self", "0xold"),
        _item(150, "reply", "0xr1", frm=_ASKER, to=_ANN),
        _item(160, "reply", "0xr2", frm=_OTHER, to=_ANN),
        _item(300, "self", "0xnew"),
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xnew", "0xold"]
    old = [t for t in threads if t["item"]["tx_hash"] == "0xold"][0]
    assert [r["item"]["tx_hash"] for r in old["replies"]] == ["0xr1", "0xr2"]


def test_equal_timestamps_break_on_tx_hash_not_on_input_order():
    """`ts` alone is not a total order and `nonce` is per-sender.

    Two items in the same second must thread identically however the caller
    happened to order them, or the panel reshuffles between refreshes.
    """
    a = _item(100, "self", "0xaaa")
    b = _item(100, "self", "0xbbb")
    assert [t["item"]["tx_hash"] for t in build_threads([a, b])] == \
           [t["item"]["tx_hash"] for t in build_threads([b, a])]


def test_a_malformed_item_is_skipped_and_never_raises():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        {"ts": "not-a-number", "kind": "reply"},
        None,
        "not a dict",
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xpost"]


def test_the_captured_channel_threads_the_way_the_screen_shows_it():
    raw = json.loads(
        (Path(__file__).parent.parent / "fixtures/surf/feed/threaded_channel.json").read_text()
    )
    threads = build_threads(raw["items"])
    assert any(
        r["depth"] == 2 for t in threads for r in t["replies"]
    ), "the capture contains an answer to a reply; threading must find it"
```

- [ ] **Step 2: Build the fixture**

Capture is already available in this repo's shape. Write
`tests/fixtures/surf/feed/threaded_channel.json` by hand from the real channel rows below —
they are the live ones, abbreviated, and the two `answer` rows are the point of the fixture.
**The file must live in a subdirectory**, not at the fixtures root: a pre-existing guard
test forbids loose files there.

```json
{"items": [
 {"ts": 1787281619, "kind": "self",   "from_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "to_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "from_label": "announce", "text": "To help bootstrap the protocol's compute power you'll need an NFT", "tx_hash": "0xpost1"},
 {"ts": 1787329979, "kind": "reply",  "from_addr": "0xef5212b20000000000000000000000000000beef", "to_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "from_label": null, "text": "Should we have one VPS one GPT/Claude sub for every NFT?", "tx_hash": "0xq1"},
 {"ts": 1787331155, "kind": "answer", "from_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "to_addr": "0xef5212b20000000000000000000000000000beef", "from_label": "announce", "text": "you can run multiple per vps on same sub but need one NFT per daemon", "tx_hash": "0xa1"},
 {"ts": 1787380451, "kind": "reply",  "from_addr": "0x6eacf11c0000000000000000000000000000dead", "to_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "from_label": null, "text": "will my IMD NFT generate me $IMD rewards?", "tx_hash": "0xq2"},
 {"ts": 1787435327, "kind": "answer", "from_addr": "0x200e710acaa6a93bbc77146026328c40f1d60fb1", "to_addr": "0x6eacf11c0000000000000000000000000000dead", "from_label": "announce", "text": "Yes the goal is for the protocol to be able to pay users compute", "tx_hash": "0xa2"}
]}
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
.venv/bin/python -m pytest tests/analytics/test_surf_feed.py -v
```

Expected: collection error — `No module named 'maxpane_dashboard.analytics.surf_feed'`.

- [ ] **Step 4: Write the module**

`maxpane_dashboard/analytics/surf_feed.py`. Pure: no I/O, no Textual import, no
`time.time()`. Algorithm, following the reference:

1. Coerce the input: drop anything that is not a `dict`, and anything whose `ts` does not
   coerce to a float. A permissionless feed can hand you anything.
2. Sort **ascending** by `(ts, tx_hash)`. `tx_hash` is the tiebreak because `ts` is not a
   total order and `nonce` is per-sender.
3. Walk once, holding `active_root` and `inbound_by_author: dict[str, dict]`:
   - `self` → open a new root, becomes `active_root`.
   - `reply` → if `active_root` is None, emit as a top-level root with no replies;
     otherwise append at depth 1 with `parent_tx_hash = active_root["tx_hash"]`. Then record
     it in `inbound_by_author[from_addr.lower()]`.
   - `answer` → parent is `inbound_by_author.get((to_addr or "").lower())`; if found, depth
     2 with that parent's hash; else depth 1 under `active_root`; if there is no
     `active_root` either, emit top-level. **Do not** record answers in
     `inbound_by_author` — only inbound replies go there, or the channel would answer
     itself.
   - `action` / `fund` / anything else → top-level root, empty `replies`.
4. Return roots **newest first**; within a root, replies stay ascending.

Every returned row is `{"item": ..., "depth": int, "parent_tx_hash": str | None,
"replies": [...]}`; roots carry their flattened descendants in `replies` and have
`depth == 0`, `parent_tx_hash is None`.

- [ ] **Step 5: Run and prove it bites**

```bash
.venv/bin/python -m pytest tests/analytics/test_surf_feed.py -v
```

All green. Then mutate: make the `answer` branch look up `from_addr` instead of `to_addr`
and confirm `test_an_answer_nests_under_the_reply_from_the_address_it_was_sent_to` goes red.
Restore. Record it.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/analytics/surf_feed.py tests/analytics/test_surf_feed.py tests/fixtures/surf/feed/threaded_channel.json
git commit -m "feat(surf): thread the announce channel, ported from the 0xTXT reference"
```

---

## Task 5: The launchpad's fixed first block

**Files:**
- Modify: `maxpane_dashboard/data/surf_addresses.py`
- Test: `tests/data/test_surf_addresses.py`

**Interfaces:**
- Produces: `surf_addresses.LAUNCHPAD_FIRST_BLOCK: int = 25_786_048`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_launchpad_first_block_is_vendored_not_rolling():
    """A rolling window against a fixed history loses coins every day.

    `LAUNCHPAD_LOG_WINDOW_BLOCKS = 33_000` was 702 blocks short of the first
    `Launched` on 2026-08-23, so 80 of 146 coins were invisible -- including
    the two busiest pools on the launchpad. A deploy block is chain history
    and cannot drift, so it is vendored on the same footing as an address.
    """
    from maxpane_dashboard.data.surf_addresses import LAUNCHPAD_FIRST_BLOCK

    assert LAUNCHPAD_FIRST_BLOCK == 25_786_048
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k first_block -v
```

Expected: `ImportError`.

- [ ] **Step 3: Add the constant**

In `maxpane_dashboard/data/surf_addresses.py`, beside the launchpad addresses:

```python
#: Block of the first ``Launched`` event, i.e. the launchpad's own genesis.
#:
#: Vendored, and that is deliberate. CLAUDE.md's "read values live, never
#: hardcode a documented one" exists because *documented* values drift -- a
#: 5% fee that is 1% on chain, a "4.0x" ratio that measured 3.885x, then
#: 3.49x, then 2.956x on three consecutive days. A block that has already
#: been mined cannot drift; this is chain history, vendored on the same
#: footing as a contract address, and verified the same way -- by what it
#: produces. ``SurfClient._launchpad_logs`` compares the launch count it
#: sweeps against ``LaunchpadFactory.coinCount()`` and the panel renders the
#: disagreement rather than ranking a subset.
#:
#: Verified 2026-08-23 at head 25_819_750: the 146 ``Launched`` events at and
#: after this block are the entire population, and ``coinCount()`` agrees at
#: 146. The 40_000-block chunk below it holds none.
LAUNCHPAD_FIRST_BLOCK = 25_786_048
```

If `surf_addresses.py` carries an `__all__` or a name/selector map that a test walks, add
the constant there too — check with `rg -n "LAUNCHPAD_FACTORY" maxpane_dashboard/data/surf_addresses.py`
and mirror whatever that address does.

- [ ] **Step 4: Run**

```bash
.venv/bin/python -m pytest tests/data/test_surf_addresses.py -q
```

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/data/surf_addresses.py tests/data/test_surf_addresses.py
git commit -m "feat(surf): vendor the launchpad's first block"
```

---

## Task 6: The launchpad sweep — cursor, full population, 24h aggregates

The largest task in this plan. It replaces a rolling window that loses history with an
append-only cursor, and moves every aggregate off the hour and onto the day.

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py:138-152` (constants), `:1184-1342` (`_launchpad_logs`), `:1062-1150` (`fetch_launchpad`)
- Test: `tests/data/test_surf_client.py`
- Create: `tests/fixtures/surf/launchpad/cursor_resume.json`

**Interfaces:**
- Consumes: Task 1's `LaunchpadState`/`LaunchpadCoin`; Task 5's `LAUNCHPAD_FIRST_BLOCK`;
  Task 7's `rank_coins` signature (write against it; Task 7 lands it).
- Produces:

```python
LAUNCHPAD_DAY_BLOCKS = int(86_400 / _LAUNCHPAD_BLOCK_SECONDS)   # 7_200
LAUNCHPAD_RENDER_LIMIT = 20                                     # unchanged

async def fetch_launchpad(self, resume: dict | None = None) -> LaunchpadState:
    """`resume` is the previous sweep's persisted slot state, or None for a
    cold sweep from LAUNCHPAD_FIRST_BLOCK. Returned state carries `cursor`,
    the value to persist and hand back next time."""
```

`LaunchpadState` gains `cursor: dict | None` alongside Task 1's three count fields. The
cursor's shape is:

```python
{"last_block": int,
 "launches": {pool_id: {"ticker","name","creator","block"}},
 "swaps_all": {pool_id: int}}
```

`LAUNCHPAD_LOG_WINDOW_BLOCKS` and `LAUNCHPAD_HOUR_BLOCKS` are **deleted**. Both are named in
`surf_client.__all__` (`:2163-2165`) — remove them there too.

- [ ] **Step 1: Write the failing tests**

In `tests/data/test_surf_client.py`:

```python
def test_the_day_window_is_derived_from_the_block_time_not_typed_twice():
    """A block-time change must move both together, or the window silently
    stops being a day."""
    from maxpane_dashboard.data import surf_client as sc

    assert sc.LAUNCHPAD_DAY_BLOCKS == int(86_400 / sc._LAUNCHPAD_BLOCK_SECONDS)


def test_the_rolling_window_constants_are_gone():
    from maxpane_dashboard.data import surf_client as sc

    assert not hasattr(sc, "LAUNCHPAD_LOG_WINDOW_BLOCKS")
    assert not hasattr(sc, "LAUNCHPAD_HOUR_BLOCKS")


@pytest.mark.asyncio
async def test_a_cold_sweep_starts_at_the_launchpads_first_block():
    client, calls = _client_recording_getlogs()
    await client.fetch_launchpad(resume=None)
    launched = [c for c in calls if c["address"] == A.LAUNCHPAD_FACTORY]
    assert min(int(c["fromBlock"], 16) for c in launched) == A.LAUNCHPAD_FIRST_BLOCK


@pytest.mark.asyncio
async def test_a_warm_sweep_starts_one_block_after_the_cursor():
    """Strictly greater than, so a re-swept boundary block cannot double-count."""
    client, calls = _client_recording_getlogs()
    await client.fetch_launchpad(resume={"last_block": 25_800_000,
                                         "launches": {}, "swaps_all": {}})
    launched = [c for c in calls if c["address"] == A.LAUNCHPAD_FACTORY]
    assert min(int(c["fromBlock"], 16) for c in launched) == 25_800_001


@pytest.mark.asyncio
async def test_resuming_does_not_double_count_a_launch_on_the_boundary_block():
    resume = {"last_block": 25_790_000,
              "launches": {"0xpool": {"ticker": "A", "name": "A", "creator": "0x1",
                                      "block": 25_790_000}},
              "swaps_all": {"0xpool": 5}}
    client = _client_serving("tests/fixtures/surf/launchpad/cursor_resume.json")
    state = await client.fetch_launchpad(resume=resume)
    assert state.launch_count == 1          # the same launch, not two
    assert state.cursor["swaps_all"]["0xpool"] == 5 + 2   # only the 2 new swaps


@pytest.mark.asyncio
async def test_a_failed_sweep_leaves_the_cursor_and_every_counter_untouched():
    """The persisted-accumulator hazard: a failed read must never become a 0
    that outlives the outage, and a partial sweep must not advance the block.
    """
    resume = {"last_block": 25_790_000, "launches": {}, "swaps_all": {"0xpool": 5}}
    client = _client_whose_getlogs_fails()
    state = await client.fetch_launchpad(resume=resume)
    assert state.cursor == resume           # byte-identical, not merely equal-ish
    assert state.swaps_by_coin is None      # honest unknown, never {}


@pytest.mark.asyncio
async def test_the_swap_buffer_is_pruned_to_the_day_it_serves():
    client = _client_serving_swaps_across_three_days()
    state = await client.fetch_launchpad(resume=None)
    assert all(v <= 46 for v in (state.swaps_by_coin or {}).values())
    assert state.swap_count == 4_724        # all-time total is NOT pruned


@pytest.mark.asyncio
async def test_the_population_counts_come_off_the_full_history():
    client = _client_serving("tests/fixtures/surf/launchpad/full_history.json")
    state = await client.fetch_launchpad(resume=None)
    assert state.launch_count == 146
    assert state.creator_count == 73
    assert state.new_24h == 0               # representable zero, never None
```

- [ ] **Step 2: Build the fixtures**

`tests/fixtures/surf/launchpad/cursor_resume.json` holds two `Launched` pages that overlap
on block 25_790_000 plus two `CurveSwap` rows strictly above it.
`full_history.json` holds 146 `Launched` rows across 73 distinct `creator` topics, all
older than 24 h. Generate both with a small script rather than by hand, and commit the
script's output only — not the script.

- [ ] **Step 3: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/data/test_surf_client.py -k launchpad -v
```

- [ ] **Step 4: Rewrite the sweep**

In `data/surf_client.py`:

1. Replace the two window constants with `LAUNCHPAD_DAY_BLOCKS`, derived as shown.
2. `_launchpad_logs(self, resume)` becomes:
   - `head = int(await self._rpc_logs("eth_blockNumber", []), 16)`; on failure return the
     all-`None` shape it already returns, **and the untouched `resume` as the cursor**.
   - `from_block = LAUNCHPAD_FIRST_BLOCK if resume is None else resume["last_block"] + 1`.
   - Sweep `Launched` from `LAUNCHPAD_FACTORY` over `from_block..head`; merge decoded rows
     into `dict(resume["launches"])` keyed by `pool_id`, so a re-seen launch overwrites
     rather than duplicating.
   - Sweep `CurveSwap` and `ImdBurned` from `LAUNCHPAD_HOOK` over the same range. Add each
     swap to `swaps_all[pool_id]`; keep the rows whose block is `>= head -
     LAUNCHPAD_DAY_BLOCKS` in a `day_swaps` list.
   - **If any of the three sweeps returns `None`, do not merge anything.** Return the
     untouched `resume` as the cursor and `None` for every aggregate whose source failed.
     A partial sweep is indistinguishable from an outage and is treated as one.
   - `new_24h` = launches whose block is `>= head - LAUNCHPAD_DAY_BLOCKS`.
   - `creator_count` = distinct `creator` over the *merged* launches, not the new ones.
   - `change_24h_pct` keeps its existing derivation (first vs last in-window swap's
     `ethAmount/coinAmount`), now over `day_swaps`. **`None`, never `0.0`**, when fewer than
     two in-window swaps carry a usable (non-zero `coinAmount`) price.
3. `fetch_launchpad(self, resume=None)` passes `resume` through, calls
   `surf_launchpad.rank_coins(...)` with the Task 7 signature, and builds `LaunchpadCoin`
   rows with `change_24h_pct` / `swaps_24h` / `swaps_all`.
4. Delete both constants from `__all__`.

Cost note for the docstring: a cold sweep is ~34k blocks today, once. Every later sweep is
whatever the 10-minute tier accumulated — a few hundred blocks.

- [ ] **Step 5: Run and prove the two dangerous ones bite**

```bash
.venv/bin/python -m pytest tests/data/test_surf_client.py -q
```

Mutate twice, and record both:
- Change `resume["last_block"] + 1` to `resume["last_block"]` → the boundary test goes red.
- Make the failure path advance `last_block` to `head` → the untouched-cursor test goes red.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_client.py tests/data/test_surf_client.py tests/fixtures/surf/launchpad/
git commit -m "fix(surf): sweep the launchpad from its first block through a cursor"
```

---

## Task 7: `rank_coins` and HOT COIN move to the day

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_launchpad.py`
- Test: `tests/analytics/test_surf_launchpad.py`

**Interfaces:**
- Consumes: nothing.
- Produces:

```python
HOT_MAX_AGE_S = 86400.0   # was 3600.0 -- the window it measures

def rank_coins(launches, day_swaps, swaps_all, now_ts, limit) -> list[dict]:
    """Rank by 24h swaps, tiebreak on all-time swaps, then on age.

    `swaps_all` is {pool_id: cumulative count} from the client's cursor.
    """
```

- [ ] **Step 1: Write the failing tests**

```python
def test_ranking_falls_back_to_all_time_not_to_age_when_the_day_is_quiet():
    """The bug this replaces: 1 swap in an hour across 146 coins sorted every
    coin to 0, the sort fell through to -age_s, and the panel showed the 20
    OLDEST never-traded coins at an identical initial curve price.
    """
    launches = [
        {"pool_id": "0xquiet_old", "ticker": "OLD", "name": "Old", "creator": "0x1", "ts": 0},
        {"pool_id": "0xbusy_new",  "ticker": "BUSY", "name": "Busy", "creator": "0x2", "ts": 900},
    ]
    rows = rank_coins(launches, day_swaps=[], swaps_all={"0xbusy_new": 677},
                      now_ts=1000, limit=10)
    assert [r["ticker"] for r in rows] == ["BUSY", "OLD"]


def test_a_day_swap_outranks_a_bigger_all_time_count():
    launches = [
        {"pool_id": "0xa", "ticker": "A", "name": "A", "creator": "0x1", "ts": 0},
        {"pool_id": "0xb", "ticker": "B", "name": "B", "creator": "0x2", "ts": 0},
    ]
    rows = rank_coins(launches, day_swaps=[{"pool_id": "0xb", "trader": "0x9", "is_buy": True}],
                      swaps_all={"0xa": 999, "0xb": 1}, now_ts=1000, limit=10)
    assert [r["ticker"] for r in rows] == ["B", "A"]


def test_a_never_traded_coin_reports_zero_swaps_not_none():
    """`0` here is a real answer: the coin exists and has never traded."""
    rows = rank_coins([{"pool_id": "0xa", "ticker": "A", "name": "A",
                        "creator": "0x1", "ts": 0}],
                      day_swaps=[], swaps_all={}, now_ts=1000, limit=10)
    assert rows[0]["swaps_24h"] == 0 and rows[0]["swaps_all"] == 0


def test_the_hot_coin_staleness_bound_is_the_window_it_measures():
    """Already in the suite -- it must now pin 24h, not an hour."""
    from maxpane_dashboard.data import surf_client as sc

    assert HOT_MAX_AGE_S == sc.LAUNCHPAD_DAY_BLOCKS * sc._LAUNCHPAD_BLOCK_SECONDS


def test_hot_coin_can_fire_on_a_days_distribution_and_stays_dark_on_an_hours():
    """At an hour the launchpad shows 1 active coin against HOT_MIN_ACTIVE=5,
    so the detector was permanently dark and had never fired. At a day it
    sees 10.
    """
    hour_like = {"0x1": 1}
    day_like = {f"0x{i}": n for i, n in enumerate([18, 14, 6, 2, 1, 1, 1, 1, 1, 1])}
    assert hot_coin_threshold(hour_like) is None
    assert hot_coin_threshold(day_like) == 5      # max(HOT_FLOOR, median 1 * 3)
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/analytics/test_surf_launchpad.py -v
```

- [ ] **Step 3: Implement**

`rank_coins` gains the `swaps_all` parameter, emits `swaps_24h` / `swaps_all` /
`change_24h_pct` per row, and sorts by
`(-r["swaps_24h"], -r["swaps_all"], -(r["age_s"] or 0.0))`. `HOT_MAX_AGE_S` becomes
`86400.0`, and its docstring paragraph about "40 swaps this hour, read yesterday" is
rewritten for the day window — the reasoning is unchanged, only the number moves.

Every `1h` in this module's prose becomes `24h`. Do not leave a docstring describing the
hour: the module's whole argument is that the window is a deliberate choice.

- [ ] **Step 4: Run**

```bash
.venv/bin/python -m pytest tests/analytics/ -q
```

- [ ] **Step 5: Prove it bites**

Change the sort key back to `(-r["swaps_24h"], -(r["age_s"] or 0.0))` and confirm
`test_ranking_falls_back_to_all_time_not_to_age_when_the_day_is_quiet` goes red. Restore.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/analytics/surf_launchpad.py tests/analytics/test_surf_launchpad.py
git commit -m "fix(surf): rank launchpad coins on the day, with an all-time tiebreak"
```

---

## Task 8: The manager caches the cursor and publishes the new keys

**Files:**
- Modify: `maxpane_dashboard/data/surf_manager.py:1370-1490` (`_pool_launchpad`, `_launchpad_payload`, `_launchpad_coin_rows`), `~2090-2110` (the flat payload), `_readings` (~:1600-1700)
- Test: `tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: Task 6's `fetch_launchpad(resume=...)` and `LaunchpadState.cursor`; Task 7's
  `HOT_MAX_AGE_S`.
- Produces: flat keys `launchpad_launch_count`, `launchpad_new_24h`,
  `launchpad_creator_count`; `launchpad_coins` rows in the Task 1 shape.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_the_cursor_round_trips_through_the_launchpad_slot(surf_manager):
    """The slot is what makes the sweep incremental. If the cursor does not
    survive a cache round trip, every sweep is a cold 34k-block sweep.
    """
    await surf_manager._pool_launchpad({TIER_LAUNCHPAD}, now=1000.0)
    payload = surf_manager.cache.get_last_good(SLOT_LAUNCHPAD).payload
    assert payload["cursor"]["last_block"] > 0

    surf_manager.client.fetch_launchpad = _recording_fetch()
    await surf_manager._pool_launchpad({TIER_LAUNCHPAD}, now=2000.0)
    assert surf_manager.client.fetch_launchpad.last_resume == payload["cursor"]


def test_the_flat_payload_publishes_the_population_counts(surf_manager):
    data = surf_manager._flat_from_slots(...)
    for key in ("launchpad_launch_count", "launchpad_new_24h",
                "launchpad_creator_count"):
        assert key in data


def test_hot_coin_reads_the_day_distribution_not_the_rendered_rows(surf_manager):
    """A median over the render-capped top 20 runs several times too high --
    the cap keeps exactly the busiest coins. This is fix round 2's finding
    and it must survive the window change.
    """
    readings = surf_manager._readings(...)
    assert readings["launchpad_swaps_by_coin"] is not None
    assert len(readings["launchpad_swaps_by_coin"]) > LAUNCHPAD_RENDER_LIMIT
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "cursor or population or hot_coin" -v
```

- [ ] **Step 3: Implement**

1. `_pool_launchpad` reads `self.cache.get_last_good(SLOT_LAUNCHPAD).payload.get("cursor")`
   **before** calling the client, and passes it as `resume=`.
2. `_launchpad_payload` caches `"cursor": _field(launchpad_state, "cursor")` alongside the
   existing wei-native fields, plus `launch_count`, `new_24h`, `creator_count`.
3. `_launchpad_coin_rows` emits `change_24h_pct` / `swaps_24h` / `swaps_all` instead of the
   `1h` pair; `creator_known` keeps its existing `KNOWN_LABELS` derivation.
4. `_cycle`'s flat mapping gains the three `launchpad_*` count keys and **drops nothing
   else** — `launchpad_coin_count` (the factory's number) stays, and is now joined by
   `launchpad_launch_count` (what the sweep found). The two are compared at render time,
   not here.
5. `_readings` keeps feeding `launchpad_swaps_by_coin` and `launchpad_coin_tickers`; only
   their window changed, so no wiring moves. **Confirm by reading `_readings`, not by
   assuming** — three detectors on the predecessor branch were permanently dark because
   `_readings` never fed their keys.

- [ ] **Step 4: Run the manager and cache suites**

```bash
.venv/bin/python -m pytest tests/data/ -q
```

- [ ] **Step 5: Prove the round trip bites**

Make `_pool_launchpad` pass `resume=None` unconditionally and confirm the round-trip test
goes red. Restore. This one matters: without it every sweep silently becomes a cold sweep
and the only symptom is slowness.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py
git commit -m "feat(surf): persist the launchpad cursor and publish the population counts"
```

---

## Task 9: Hero — `LAUNCHPAD · FLOW · BURN · SUPPLY`

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/hero.py`
- Modify: `tests/test_surf_registration.py` (move the three keys out of `_KEYS_PENDING_CONSUMERS` **only if** this task's needles are verified against composited output; otherwise leave them for Task 12)
- Test: `tests/widgets/test_surf_widgets_a.py`

**Interfaces:**
- Consumes: Task 8's flat keys.
- Produces: `SurfHero.update_data(launchpad_coin_count=, launchpad_new_24h=,
  launchpad_creator_count=, launchpad_swap_count=, launchpad_trader_count=,
  launchpad_creator_eth_owed=, launchpad_as_of_hhmm=, burn_*=, imd_*=, **_kwargs)`.
  Box ids become `surf-hero-launchpad`, `surf-hero-flow`, `surf-hero-burn`,
  `surf-hero-supply`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_the_hero_leads_with_the_launchpad_and_its_flow():
    app, out = await _render_hero(
        launchpad_coin_count=146, launchpad_new_24h=0, launchpad_creator_count=73,
        launchpad_swap_count=4724, launchpad_trader_count=673,
        launchpad_creator_eth_owed=0.0751, launchpad_as_of_hhmm="20:20",
    )
    assert "LAUNCHPAD" in out and "FLOW" in out
    assert "POOL" not in out and "MIGRATED" not in out
    assert "146 coins" in out and "4,724 swaps" in out


@pytest.mark.asyncio
async def test_zero_new_launches_is_a_number_not_a_dash():
    """Today there genuinely were none. `0 new` and `-- new` are different
    claims and the hero must not collapse them.
    """
    _, out = await _render_hero(launchpad_coin_count=146, launchpad_new_24h=0,
                                launchpad_creator_count=73)
    assert "0 new" in out


@pytest.mark.asyncio
async def test_an_unread_launchpad_slot_shows_no_numbers_at_all():
    _, out = await _render_hero(launchpad_coin_count=None, launchpad_new_24h=None,
                                launchpad_creator_count=None)
    assert "0 coins" not in out and "no read yet" in out


@pytest.mark.asyncio
async def test_the_launchpad_boxes_carry_their_own_slower_clock():
    """The title bar's `as of` is the FAST tier's. The launchpad tier is 600s,
    so these two boxes would otherwise show ten-minute-old numbers under a
    clock claiming seconds -- "a stale number presented as live".
    """
    _, out = await _render_hero(launchpad_coin_count=146, launchpad_as_of_hhmm="20:20")
    assert "20:20" in out
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/widgets/test_surf_widgets_a.py -k hero -v
```

- [ ] **Step 3: Rewrite the two boxes**

Replace `_pool_lines` and `_lp_lines` with `_launchpad_lines` and `_flow_lines`, following
the existing five-line shape `[title, "", big, second, third]`:

```python
def _launchpad_lines(coin_count, new_24h, creator_count, as_of_hhmm, tier) -> list[str]:
    """LAUNCHPAD box: the population, its growth and who is building it.

    Carries the launchpad tier's OWN clock on the title line. The title bar
    above shows the fast tier's `as of`, and these numbers are up to ten
    minutes older than that -- rendering them under the fast clock would be
    exactly the "stale number presented as live" the house rules forbid.
    At `minimal` (13 columns) the clock is dropped; that width is a
    52-column terminal, where nothing else fits either.
    """
    title = "LAUNCHPAD"
    if as_of_hhmm and not _short(tier):
        title = f"LAUNCHPAD · {safe_markup(str(as_of_hhmm))}"
    ...
```

- The big line is `{coin_count:,} coins`, or `[dim]—[/]` when `coin_count is None`.
- The second line is `{new_24h} new · 24h` — **`0` renders as `0`**, and only `None`
  becomes a dash.
- The third is `{creator_count} creators`.
- When *every* input is `None`, the second line becomes `no read yet` and the third blank.
- `_flow_lines(swap_count, trader_count, creator_eth_owed, as_of_hhmm, tier)` follows the
  identical shape: `{swap_count:,} swaps` / `{trader_count:,} traders` /
  `{creator_eth_owed:.4f} ETH`.

Delete `HOOK_NOT_LIVE` and `HOOK_LAUNCHED` and the stale top-level import of them in
`tests/screens/test_surf_screen.py`. Update `compose()`'s box ids and `_render_view`'s
dispatch.

- [ ] **Step 4: Re-derive `MINIMAL_WIDTH`**

`MINIMAL_WIDTH = 13` was anchored by `OWNER CHANGED` (LP's alarm) and SUPPLY's quantity.
**LP is gone, so `OWNER CHANGED` is gone.** Re-derive the anchor from the strings the row
now actually emits — render every state at every tier and measure — and update both the
constant and the module docstring's explanation of what sets it. Do not assume 13 survives.

`test_every_hero_tier_fits_the_width_it_advertises` is the check; extend it to cover the two
new boxes' states, including the unread state and the `as of` title.

- [ ] **Step 5: Run and prove it bites**

```bash
.venv/bin/python -m pytest tests/widgets/ -q
```

Mutate: make `new_24h=0` render a dash and confirm `test_zero_new_launches_is_a_number_not_a_dash`
goes red. Restore. Record it.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/surf/hero.py tests/
git commit -m "feat(surf): the hero leads with the launchpad and its flow"
```

---

## Task 10: The feed renders threads

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/feed.py`
- Test: `tests/widgets/test_surf_widgets_b.py` (where `SurfFeed`'s tests already live) and `tests/widgets/test_surf_widget_contract.py`

**Interfaces:**
- Consumes: Task 4's `build_threads`; Task 3's `answer` kind and `to_addr`.
- Produces: `SurfFeed.update_data(feed_nonce=, feed_last_post_age_s=, feed_items=,
  **_kwargs)` — unchanged signature. New exported names: `ANSWER_BADGE = "ANSWER"`,
  `TOGGLE_COLLAPSED = "▸"`, `TOGGLE_EXPANDED = "▾"`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_replies_are_collapsed_behind_a_count_by_default():
    _, out = await _render_feed(_CAPTURED_ITEMS)
    assert "▸ 2 replies" in out
    assert "will my IMD NFT generate" not in out


@pytest.mark.asyncio
async def test_clicking_the_toggle_expands_and_clicking_again_collapses():
    app = await _mount_feed(_CAPTURED_ITEMS)
    toggle = app.query_one("#surf-feed-toggle-0xpost1")
    await app.pilot.click(toggle)
    assert "will my IMD NFT generate" in _composited(app)
    await app.pilot.click(toggle)
    assert "will my IMD NFT generate" not in _composited(app)


@pytest.mark.asyncio
async def test_the_toggle_answers_the_keyboard_too():
    app = await _mount_feed(_CAPTURED_ITEMS)
    app.query_one("#surf-feed-toggle-0xpost1").focus()
    await app.pilot.press("enter")
    assert "will my IMD NFT generate" in _composited(app)


@pytest.mark.asyncio
async def test_an_answer_is_indented_one_column_past_the_reply_it_answers():
    app = await _expanded_feed(_CAPTURED_ITEMS)
    lines = _composited(app).splitlines()
    reply = next(l for l in lines if "REPLY" in l)
    answer = next(l for l in lines if "ANSWER" in l)
    assert _indent_of(answer) == _indent_of(reply) + 1


@pytest.mark.asyncio
async def test_an_answer_is_never_styled_as_a_contract_call():
    """It is authenticated -- same author as POST -- so it must not wear
    ACTION's colour, which is what made it read as a contract call.
    """
    _, out = await _expanded_feed(_CAPTURED_ITEMS)
    assert "ANSWER" in out and "ACTION" not in out


@pytest.mark.asyncio
async def test_a_post_with_no_replies_shows_no_toggle():
    _, out = await _render_feed([_ITEM_POST_ALONE])
    assert "▸" not in out and "▾" not in out


@pytest.mark.asyncio
async def test_expansion_survives_a_repaint_with_a_new_post_on_top():
    """Keyed by tx hash, not row index: the feed repaints every 30s, and
    collapsing what the reader just opened would make the feature unusable.
    """
    app = await _expanded_feed(_CAPTURED_ITEMS)
    app.query_one(SurfFeed).update_data(feed_items=[_NEWER_POST, *_CAPTURED_ITEMS])
    await app.pilot.pause()
    assert "will my IMD NFT generate" in _composited(app)


@pytest.mark.asyncio
async def test_an_action_with_neither_text_nor_label_renders_its_value():
    """Channel nonce 16: 0.05 ETH, empty calldata. It used to render as
    `ACTION` followed by nothing, which is indistinguishable from a bug.
    """
    _, out = await _render_feed([{"ts": 1.0, "kind": "action", "text": None,
                                 "label": "", "value_eth": 0.05,
                                 "tx_hash": "0xpay", "from_addr": _ANN,
                                 "to_addr": _OTHER, "from_label": "announce"}])
    assert "0.05 ETH" in out


@pytest.mark.asyncio
async def test_a_hostile_name_cannot_kill_the_app_through_deferred_markup():
    """Static defers markup parsing into the message pump, so a malformed
    string raises OUTSIDE the screen's try/except -- the DataTable crash
    CLAUDE.md documents. Rows are handed pre-built Text, never markup.
    """
    _, out = await _render_feed([{**_ITEM_POST_ALONE, "text": "[/x] [bold red]"}])
    assert "[/x]" in out          # rendered as literal text, app still alive
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/widgets/ -k feed -v
```

- [ ] **Step 3: Restructure the widget**

`SurfFeed` keeps its title `Static` and replaces the `RichLog` with a `VerticalScroll`
(`id="surf-feed-body"`). Per render:

1. `threads = build_threads(items)`.
2. For each root: one `SurfFeedRow` (a `Static` subclass) for the post; if it has replies, a
   `SurfFeedToggle` with `id=f"surf-feed-toggle-{tx_hash}"`; then, when expanded, one
   `SurfFeedRow` per reply at its own indent.
3. `SurfFeedToggle` is `can_focus = True`, has `BINDINGS = [Binding("enter", "toggle"),
   Binding("space", "toggle")]` and an `on_click`. Both call the same `action_toggle`, which
   flips `self.feed._expanded[self.tx_hash]` and re-renders.
4. `self._expanded: dict[str, bool]` lives on `SurfFeed` and is **never cleared** by
   `update_data`.

**Rows are handed `rich.text.Text`, not markup strings.** Build them inside `_row_text()`,
which keeps `_item_lines`' existing `try/except → None` contract so one malformed item
still degrades to a skipped row. `safe_markup` still runs on every third-party string;
pre-parsing and escaping are independent guards and neither replaces the other.

`_wrap_no_widow`, `FULL_TEXT_WIDTH`, `_PREFIX_WIDTH`, `WIDEN_HINT`, `UNAVAILABLE_LINE` and
the tier logic are all reused unchanged — they are pure functions over a string and a
budget. The per-row text budget shrinks by the row's `depth`, which is the indentation.

`_KIND_STYLES` gains `"answer": ("ANSWER", "cyan")` — the same colour as `POST`, because it
has the same authenticated author.

- [ ] **Step 4: Run and prove three bite**

```bash
.venv/bin/python -m pytest tests/widgets/ -q
```

Mutate and record:
- Clear `self._expanded` in `update_data` → the repaint test goes red.
- Give `answer` `"yellow"` → the styling test goes red.
- Pass a markup string to `Static.update()` instead of `Text` → the hostile-name test goes
  red (or the app dies, which is the same finding).

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/widgets/surf/feed.py tests/
git commit -m "feat(surf): the announce feed threads its replies behind a toggle"
```

---

## Task 11: The coins table's columns

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/launchpad.py:210-220` (column widths), `:358-365` (columns), the row builder, and `COINS_TITLE`'s note line
- Test: `tests/widgets/test_surf_launchpad_widgets.py` (where the launchpad widgets' tests already live)

**Interfaces:**
- Consumes: Task 1's `SURF_ROW_KEYS["launchpad_coins"]`; Task 8's rows.
- Produces: nine columns at **79 structural columns total**, unchanged from today.

```python
_TICKER_COLS = 8
_NAME_COLS   = 18
_ADDR_COLS   = 11   # was 17 -- pays for the SWAPS ALL column
_AGE_COLS    = 4
_PRICE_COLS  = 10
_PCT_COLS    = 7
_SWAPS_COLS  = 6
_SWAPS_ALL_COLS = 6
_BURNED_COLS = 9
# 8+18+11+4+10+7+6+6+9 = 79
```

- [ ] **Step 1: Write the failing tests**

```python
def test_the_table_still_needs_exactly_seventy_nine_columns():
    """The new column is paid for by shortening CREATOR, not by widening the
    panel. Raising a width constant is reserved for when no honest short
    form exists, and a truncated address is an honest short form.
    """
    from maxpane_dashboard.widgets.surf import launchpad as lp

    assert (lp._TICKER_COLS + lp._NAME_COLS + lp._ADDR_COLS + lp._AGE_COLS
            + lp._PRICE_COLS + lp._PCT_COLS + lp._SWAPS_COLS
            + lp._SWAPS_ALL_COLS + lp._BURNED_COLS) == 79


@pytest.mark.asyncio
async def test_the_table_names_the_day_not_the_hour():
    _, out = await _render_coins(_ROWS)
    assert "24H%" in out and "1H%" not in out


@pytest.mark.asyncio
async def test_the_title_reports_a_population_the_sweep_could_not_reach():
    """146 coins with 66 swept is the bug that produced this whole task.
    Rendering the subset as if it were the population is what hid it.
    """
    _, out = await _render_coins(_ROWS, coin_count=146, launch_count=66)
    assert "146 coins · 66 read" in out


@pytest.mark.asyncio
async def test_an_agreeing_count_says_it_once():
    _, out = await _render_coins(_ROWS, coin_count=146, launch_count=146)
    assert "146 coins" in out and "read" not in out


@pytest.mark.asyncio
async def test_a_hostile_ticker_is_escaped_in_the_table():
    """launch(string,string) is permissionless and unpriced beyond gas."""
    _, out = await _render_coins([{**_ROW, "ticker": "[/x]"}])
    assert "[/x]" in out
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/widgets/ -k coins -v
```

- [ ] **Step 3: Implement**

Column widths as in the Interfaces block. Rename the `1H%` header to `24H%` and the `SWAPS`
header to `SWAPS 24H`; add `SWAPS ALL`. `update_data` gains `launch_count=None` and the
note line reads `{coin_count:,} coins` when the counts agree and
`{coin_count:,} coins · {launch_count:,} read` when they do not. When `launch_count is
None` (the sweep failed), the note keeps today's `as of` behaviour and says nothing about
the population.

The CREATOR cell at 11 columns renders `0x8ca0…e5e8` — six leading characters, ellipsis,
four trailing. Where `creator_known` is true, render the label instead, truncated to 11 with
`safe_markup` applied first.

- [ ] **Step 4: Run**

```bash
.venv/bin/python -m pytest tests/widgets/ -q
```

- [ ] **Step 5: Prove it bites**

Set `_ADDR_COLS = 17` and confirm the 79-column test goes red. Restore. Record it.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/surf/launchpad.py tests/
git commit -m "feat(surf): the coins table ranks on the day and names its population"
```

---

## Task 12: The screen — wiring and the launchpad rail

**Sole owner of `screens/surf.py` for structural changes.** Every earlier task that touched
it made a single-line deletion; this one owns the layout.

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` (`compose`, `DEFAULT_CSS`, the three
  `update_data` dispatches, `LAUNCHPAD_BODY_ID`'s neighbours)
- Modify: `tests/test_surf_registration.py` (empty `_KEYS_PENDING_CONSUMERS`, drop its xfail)
- Test: `tests/screens/test_surf_screen.py`

**Interfaces:**
- Consumes: Tasks 9, 10 and 11's widget signatures.
- Produces: `#surf-launchpad-rail`, a `Vertical` inside a now-`Horizontal`
  `#surf-launchpad-body`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_the_launchpad_summary_panels_sit_beside_the_coins_table():
    app = await _surf_at(140, 50)
    await app.pilot.press("l")
    coins = app.query_one(SurfLaunchpadCoins).region
    flow = app.query_one(SurfCurveFlow).region
    assert flow.x > coins.right - 2, "CURVE FLOW must be to the RIGHT of the table"
    assert flow.y < coins.bottom, "and beside it, not below"


@pytest.mark.asyncio
async def test_the_rail_reserves_its_scrollbar_gutter():
    """Without `scrollbar-gutter: stable` the scrollbar steals a column from
    the binding panel only on short terminals, so the layout's WIDTH
    requirement moves with its HEIGHT -- curator's own bug, one pin true at
    48 rows and one column short at 40.
    """
    app = await _surf_at(140, 50)
    rail = app.query_one("#surf-launchpad-rail")
    assert "stable" in str(rail.styles.scrollbar_gutter)


@pytest.mark.asyncio
async def test_the_hero_survives_the_body_swap():
    """It is outside #surf-launchpad-body, so nothing it tracks goes dark."""
    app = await _surf_at(140, 50)
    await app.pilot.press("l")
    assert "LAUNCHPAD" in _composited(app) and "IMD SUPPLY" in _composited(app)
```

- [ ] **Step 2: Run and watch them fail**

```bash
.venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "beside or gutter or body_swap" -v
```

- [ ] **Step 3: Restructure**

```python
        with Horizontal(id=LAUNCHPAD_BODY_ID):
            yield SurfLaunchpadCoins()
            with Vertical(id="surf-launchpad-rail"):
                yield SurfCurveFlow()
                yield SurfBurnPipeline()
```

CSS, mirroring `#middle-row`/`#surf-right-rail`:

```css
    SurfScreen #surf-launchpad-body { height: 1fr; width: 100%; margin: 1 0 0 0; }
    SurfScreen SurfLaunchpadCoins { width: 7fr; height: 1fr; padding: 0 1; }
    SurfScreen #surf-launchpad-rail {
        width: 6fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfCurveFlow { width: 1fr; height: auto; padding: 0 1; margin: 0 0 1 0; }
    SurfScreen SurfBurnPipeline { width: 1fr; height: 1fr; min-height: 6; padding: 0 1; }
```

**The `7fr:6fr` above is a starting point, not the answer.** Task 13 sweeps it.

Then the wiring: pass Task 9's launchpad kwargs to `SurfHero`, Task 11's `launch_count` to
`SurfLaunchpadCoins`, and confirm every key the three widgets name is actually in the flat
payload. **Read `_readings` and the flat dict rather than assuming** — the predecessor's
whole-branch review found two Criticals that were "green and does nothing", both wiring.

- [ ] **Step 4: Empty the pending-consumer bucket**

Every key in `_KEYS_PENDING_CONSUMERS` now has a rendering consumer. For each, mount the
widget, render it with the key set to `0`, read the composited output, and use **that exact
substring** as the probe needle. Move all three into `_NUMERIC_ZERO_PROBES`, empty the
frozenset, and delete the `xfail` marker from
`test_the_pending_consumer_bucket_is_empty_by_the_end_of_this_plan`.

Do not invent a needle. Four of ten needles on the predecessor branch were wrong, and one
was the rendering of a *non-zero* value, so that probe had never covered anything.

- [ ] **Step 5: Run the screen suite**

```bash
.venv/bin/python -m pytest tests/screens/ tests/test_surf_registration.py -q
```

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/screens/surf.py tests/
git commit -m "feat(surf): the launchpad summary panels move into a right rail"
```

---

## Task 13: Width sweeps, docs, and the full suite

Everything that could move a width is now final. Nothing in this task changes behaviour.

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` (the two width constants and their docstrings)
- Modify: `tests/screens/test_surf_screen.py` (the sweeps)
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Sweep the surf screen's full-layout width**

The feed was rewritten and indentation adds up to 2 columns to the deepest row. Sweep column
by column, **starting away from 143** so the sweep cannot agree with the pin by
construction. Measure against a fixture with the transaction-linking post removed —
`test_a_linked_post_advertises_widen_at_the_full_layout_width` covers that case separately
and its marker is correct.

If the feed now needs more than its share, **shorten `FULL_TEXT_WIDTH` (71)**, do not raise
`SURF_FULL_LAYOUT_COLUMNS`. That lever buys the wrapping with rows, which this panel has to
spare, and it is the one the 2026-08-11 seam work found to be cheap.

- [ ] **Step 2: Sweep the launchpad body's seam**

Sweep seam by seam (`3:2`, `7:6`, `9:7`, `11:9`, `2:1`, `3:1`) and record what each costs in
full-layout columns, then pin the cheapest that clears. Start the width sweep away from both
93 and the new number. Update `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` and rewrite its
docstring: the old text argues from a full-width stacked body that no longer exists.

Re-check `test_the_launchpad_binding_panel_is_the_coins_table`. If the rail has become the
binder, re-point it **with the measurement as evidence**, not by assumption.

- [ ] **Step 3: Assert the app-wide number did not move**

```bash
.venv/bin/python -m pytest tests/test_cli_font_size.py tests/screens/ -q
```

`__main__.FULL_LAYOUT_COLUMNS` must still be **143**. If a sweep says otherwise, stop and
report it rather than editing the constant — that is a design decision, not a measurement.

- [ ] **Step 4: Update the docs**

`CLAUDE.md`:
- The surf row in the dashboard table: the announce feed now threads replies.
- The "Build & run" width paragraphs: surf's own number and the launchpad body's, with what
  binds each — replacing, not appending to, the paragraphs those numbers came from. The
  `198 → 172 → 143 → 176 → 152 → 143` record is appended to **only if
  `__main__.FULL_LAYOUT_COLUMNS` actually moved**, which it must not.
- The Conventions section gains the deferred-markup rule this branch relies on: *a widget
  that renders third-party text through `Static` hands it pre-built `Text`, never a markup
  string — `Static` defers parsing into the message pump, so a malformed string raises
  outside the screen's `try/except`.*
- The test count.

`README.md`: the feed's expand/collapse control and the launchpad view's new layout.

- [ ] **Step 5: Run everything**

```bash
.venv/bin/python -m pytest -q
```

Expected: green, and the count recorded in `CLAUDE.md`. Also run
`.venv/bin/python -m pytest sybilkit -q` to confirm the second distribution is untouched.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/screens/surf.py tests/screens/test_surf_screen.py CLAUDE.md README.md
git commit -m "docs(surf): re-measure both layouts and record what binds them"
```

---

## Self-review

**Spec coverage.** §1 → Task 2. §2 → Tasks 1, 8, 9. §3.1 → Task 3. §3.2 → Tasks 3, 10.
§3.3 → Tasks 3, 4. §3.4–3.6 → Task 10. §3.7 → Task 13. §4.1 → Tasks 12, 13. §4.2 → Tasks 5,
6, 8. §4.3 → Tasks 6, 7, 11. §4.4 → Task 7. §4.5 → Tasks 6, 11. Spec test list items 1–11
map to Tasks 3, 3, 3/10, 4, 4, 10, 10, 6, 11, 7, 7. No gaps.

**Placeholder scan.** No "TBD", no "handle edge cases", no "similar to Task N". Two places
deliberately defer a *measurement* to Task 13 (the launchpad seam, `MINIMAL_WIDTH`) and both
say exactly how to measure it; that is sequencing, not a placeholder.

**Type consistency.** `swaps_24h`/`swaps_all`/`change_24h_pct` are spelled identically in
Tasks 1, 6, 7, 8 and 11. `build_threads` returns the same `{"item", "depth",
"parent_tx_hash", "replies"}` shape in Tasks 4 and 10. `fetch_launchpad(resume=...)` and
`LaunchpadState.cursor` agree between Tasks 6 and 8. `launchpad_launch_count` (flat) and
`LaunchpadState.launch_count` (model) are deliberately different spellings, following the
existing `coin_count`/`launchpad_coin_count` convention that `_launchpad_payload`'s
docstring already documents.

**One known rough edge, called out rather than hidden.** Task 2's Step 2 shows a test that
does *not* bite as first written, and fixes it in the same step. That is intentional: the
naive assertion is the one a careful engineer would reach for first, and `update_data`'s
`**_kwargs` is exactly why it fails to cover anything.
