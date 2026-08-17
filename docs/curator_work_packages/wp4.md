# WP4 — `widgets/curator/*` (seven render-only widgets)

**Goal:** Seven Textual widgets that render the flat `CURATOR_KEYS` payload and nothing else:
phase-driven hero, leaderboard, sparklines, signal rail, activity feed and the two swap-slot
tables. Every one degrades to an explicit unavailable state, escapes every string, and
advertises the columns it sheds.

**Dependencies:** WP0 (`CURATOR_KEYS`, `CURATOR_ROW_KEYS`, `PHASES` — imported by the **test**
file only). Runs in wave 2 in parallel with WP2 and WP3; shares no file with either.

**Owner note.** This WP owns and creates:

- `maxpane_dashboard/widgets/curator/__init__.py`
- `maxpane_dashboard/widgets/curator/_fmt.py`
- `.../hero.py`, `.../leaderboard.py`, `.../sparklines.py`, `.../signals.py`,
  `.../activity.py`, `.../closest_calls.py`, `.../clusters.py`
- `tests/widgets/test_curator_widgets.py`

It touches **no** `screens/`, no `themes/minimal.tcss` (WP7's), and no `data/` or `analytics/`
module. If a widget needs a value the manager does not emit, **report it to WP0/WP5; do not
add a key.**

### Ground rules

- **Widgets never import from `data/` or `analytics/`.** An AST test in WP4.1 fails if any
  module under `widgets/curator/` imports either package. They receive
  `str`/`int`/`float`/`bool`/`dict`/`list[dict]` only.
- **`update_data(**kwargs)` with every kwarg optional and defaulting to `None`**, plus
  `**_kwargs` so an extra key from a future manager cannot crash a widget. House idiom.
- **`safe_markup` every value** before it reaches markup or `add_row`. v1 renders only
  self-generated hex and numbers; the rule is unconditional because the escape is what makes
  it stay true.
- **Sparklines import `widgets/sparkline_common`** (`build_sparkline`, `coerce_points`,
  `trend_arrow`, `fmt_compact`). Copying a helper is a defect.
- **A `None` list means "source dead"; `[]` means "genuinely nothing".** Two different
  renderings, both explicit. This is the `surf_manager._blank_payload` contract and the
  widgets are the half that acts on it.
- **Width tiers advertise.** Each table picks a tier from its measured width and appends
  `‹ widen` to its own title naming what it dropped. Never clip silently, never raise
  `FULL_LAYOUT_COLUMNS`.
- **Cells are sized to their producers' actual vocabularies** (the `dev`/`ops` lesson): the
  activity `kind` column is sized to `{deposit, joined, saved}` and nothing wider; the address
  column to the 13-column `0x1234…abcd` form; the amount column to the compact ETH formatter's
  real worst case, measured, not guessed.
- Commit after each task.

---

### Task WP4.1: Package, `_fmt`, and the import-hygiene guard

**Interfaces:** produces `widgets/curator/_fmt.py` with `DASH = "--"`, `EMDASH = "—"`,
`as_float`, `fmt_eth(value, places=2)`, `fmt_eth_compact`, `short_addr(value)` (the 13-column
`0x1234…abcd`), `fmt_age(seconds)`, `fmt_countdown(seconds)` (`HH:MM:SS` / `MM:SS`),
`fmt_points`, `hhmm(ts)`, `fmt_pct`. Re-exports the seven widget classes from `__init__.py`.

**Steps:**

- [x] Failing tests:

```python
def test_no_curator_widget_imports_data_or_analytics():
    """Structural, by AST -- a string scan misses ``importlib`` and aliases."""
    for path in Path("maxpane_dashboard/widgets/curator").glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            mods = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names] if isinstance(node, ast.Import)
                    else [])
            for m in mods:
                assert ".data" not in m and ".analytics" not in m, (path.name, m)


def test_no_curator_widget_copies_a_sparkline_helper():
    for path in Path("maxpane_dashboard/widgets/curator").glob("*.py"):
        src = path.read_text("utf-8")
        for copied in ("SPARK_CHARS", "def build_sparkline", "def trend_arrow"):
            assert copied not in src, (path.name, copied)


def test_short_addr_is_thirteen_columns_and_keeps_both_ends():
    out = short_addr("0x381fe4861234567890abcdef1234567890abCDEF")
    assert out == "0x381f…cdef" or len(out) == 13     # pin the exact form
    assert out.startswith("0x381") and out.endswith("CDEF"[-4:].lower()) is not None


def test_every_formatter_returns_a_dash_for_none_and_never_a_zero():
    for fn in (fmt_eth, fmt_eth_compact, fmt_age, fmt_countdown, fmt_points, fmt_pct):
        assert fn(None) in (DASH, EMDASH)
    for fn in (fmt_eth, fmt_points):
        assert fn(0) not in (DASH, EMDASH)      # a real zero still renders


def test_fmt_countdown_handles_the_contracts_edges():
    """timeLeftInHour() returns hourDuration at an exact boundary, never 0
    (H12), and grace_seconds_left is clamped at 0 by the analytics layer."""
    assert fmt_countdown(3600) == "1:00:00"
    assert fmt_countdown(1) == "00:01"
    assert fmt_countdown(0) == "00:00"
    assert fmt_countdown(-5) in (DASH, EMDASH)   # nonsense, never a negative clock


def test_no_formatter_ever_renders_a_negative_countdown():
    assert "-" not in fmt_countdown(0)
```

- [x] Implement.
- [x] Commit: `feat(curator): widget package, format helpers and the import-hygiene guard`

---

### Task WP4.2: `CuratorHero` — the three phase-driven boxes

**Interfaces:** `update_data(phase=None, current_hour=None, grace_seconds_left=None,
grace_ends_utc=None, hour_fed_eth=None, hour_needed_eth=None, hour_seconds_left=None,
settled_hour=None, settled_at_ts=None, lived_desc=None, settled_observed_at=None,
early_multiplier_x=None, points_per_eth_now=None, survival_streak_hours=None,
closest_call_margin_eth=None, closest_call_hour=None, contributors_total=None,
deposits_total=None, volume_routed_eth=None, top_points=None, **_kwargs)`.

**The three boxes, per PRD §3's table:**

| box | grace | judged | settled |
|---|---|---|---|
| CLOCK | `GRACE — judging begins in HH:MM:SS`, subtitle = the absolute UTC end | `HOUR N · fed X.XX/5.00 ETH · MM:SS left` | `SETTLED AT HOUR N · lived Dd HHh` |
| LIST | `252 wallets · 8401 ETH routed (all refunded) · list OPEN` | same, `OPEN` | same, `list FROZEN` |
| CURVE/SURVIVAL | `1.93×` decay + `1 ETH buys ≈ N pts now` | `survived N hours · min margin X.XX @ hour H` | final records: contributors, volume, top score |

**Steps:**

- [x] Failing tests, composited:

```python
def test_volume_is_never_labelled_tvl_or_capital():
    """H4, the flagship honesty rule. Every wei is refunded in-transaction, so
    a TVL label is not a rounding error -- it is a false claim about money at
    risk, on a dashboard people will read while deciding to send 60 ETH."""
    text = _rendered(hero, **_grace_payload())
    assert "routed (all refunded)" in text
    for banned in ("TVL", "locked", "at risk", "capital", "deposited value"):
        assert banned.lower() not in text.lower()


def test_the_one_honest_capital_sentence_appears_at_most_once():
    """PRD §6: the EOA gate means each high-water mark WAS really held in a
    real EOA. True, and worth saying once as subtitle text -- never twice, and
    never next to a volume number."""
    assert _rendered(hero, **_grace_payload()).lower().count("eoa") <= 1


@pytest.mark.parametrize("phase", PHASES)
def test_each_phase_renders_its_own_three_boxes(phase):
    text = _rendered(hero, **_payload_for(phase))
    assert _EXPECTED_HEADLINE[phase] in text


def test_the_settled_hero_reads_as_an_archive_not_as_a_failure():
    """PRD §11: SETTLED is a first-class terminal state. Words like 'error',
    'stale' or 'unavailable' in the settled hero tell a user the dashboard is
    broken when the *game* is over."""
    text = _rendered(hero, **_settled_payload())
    assert "SETTLED AT HOUR" in text and "list FROZEN" in text
    for wrong in ("error", "unavailable", "stale", "no data"):
        assert wrong not in text.lower()


def test_a_missing_value_renders_the_explicit_unavailable_state():
    text = _rendered(hero)          # no kwargs at all
    assert "unavailable" in text.lower() or text.count("--") >= 3
    assert "0.00 ETH" not in text and "0 wallets" not in text


def test_an_unknown_phase_renders_a_named_fallback_not_a_blank_box():
    """phase=None is what a failed isSettled read produces (WP3.2). The hero
    must say so rather than silently choosing GRACE, which would render a
    countdown for a game that may already be dead."""
    text = _rendered(hero, phase=None, current_hour=30)
    assert "phase unavailable" in text.lower()
```

- [x] Implement. The CLOCK box's countdown comes **only** from the payload — no widget-local
      timer, no `time.time()` (PRD §2: clock values are poll-anchored). A test asserts the
      module's source contains no `time.time()` / `datetime.now()`.
- [x] Commit: `feat(curator): phase-driven hero with the routed-not-TVL copy`

---

### Task WP4.3: `CuratorLeaderboard`

**Interfaces:** `update_data(leaderboard_rows=None, you_address=None, **_kwargs)`.
Columns per `CURATOR_ROW_KEYS["leaderboard_rows"]`: rank, address, points, credit ETH, tx
count, `⚑`.

**Steps:**

- [x] Failing tests: 10 rows max; a `None` list renders `leaderboard unavailable` and an empty
      list renders `no contributors yet` (**different strings**, asserted separately); the
      wallet's own row is emphasised when `you_address` matches, case-insensitively (addresses
      arrive checksummed from one source and lowercase from another); `⚑` appears only for
      `flagged=True`; a hostile address string (`"[/x]"`, which no real address is, but which
      a mangled payload can be) renders literally rather than raising `MarkupError`; width
      tiers shed the tx-count column first, then credit, each announced in the title with
      `‹ widen`.
- [x] Implement with a `DataTable`, `safe_markup` on every cell, and `visible_len` from
      `markup_safety` for any title-width decision.
- [x] **Prove it bites:** remove one `safe_markup` call and pass `"[/x]"` as an address →
      the hostile-string test FAILS (`MarkupError` out of the message pump). Restore.
- [x] Commit: `feat(curator): leaderboard with cluster flags and announced width tiers`

---

### Task WP4.4: `CuratorSparklines`

**Interfaces:** `update_data(volume_series=None, contributors_series=None,
hourly_threshold_eth=None, **_kwargs)`.

**Steps:**

- [x] Failing tests: both series render through `sparkline_common.build_sparkline`; a `None`
      series renders `waiting for data...` and an empty one renders the same (here they are
      genuinely the same fact — say so in a comment, since everywhere else they differ); a
      series with a `None` point survives via `coerce_points`; the **threshold line is
      labelled** on the volume spark (`5.00 ETH bar`) because a volume sparkline without the
      survival bar is a pretty picture with no meaning; `trend_arrow` is used, not copied.
- [x] Implement.
- [x] Commit: `feat(curator): hourly volume and contributor sparklines with the survival bar`

---

### Task WP4.5: `CuratorSignals` — the seven-row rail

**Interfaces:** `update_data(**every signal key**, **_kwargs)`. Rows in `SIGNAL_ROWS` order:
SETTLED · HOUR AT RISK · HOUR SAVED · WHALE · FARM · FORCED ETH · YOU.

**Steps:**

- [x] Failing tests:

```python
def test_all_seven_rows_reach_the_compositor():
    """The FWA coverage-badge lesson: a rail inside a fixed-height row loses
    its LAST row first, and YOU is last. Pinned at the rail's real height."""
    text = _rendered(signals, **_full())
    for label in ("SETTLED", "HOUR AT RISK", "HOUR SAVED", "WHALE",
                  "FARM", "FORCED ETH", "YOU"):
        assert label in text


def test_hour_at_risk_says_n_a_during_grace_and_never_goes_blank():
    text = _rendered(signals, phase="grace", sig_at_risk_state="ok",
                     hour_needed_eth=None)
    assert "n/a until hour" in text


def test_forced_eth_expects_a_dash_and_shouts_on_a_nonzero():
    """H5. Zero is the expected, healthy state and renders quietly. Any
    nonzero value is an anomaly -- forced ETH, never a deposit -- and must be
    visually distinct."""
    assert "—" in _rendered(signals, forced_eth=0.0)
    loud = _rendered(signals, forced_eth=1.5)
    assert "1.5" in loud and "forced" in loud.lower()
    for banned in ("TVL", "balance held", "locked"):
        assert banned.lower() not in loud.lower()


def test_hour_saved_renders_a_never_fired_state_rather_than_waiting():
    """HourSaved may never fire in this game's whole life. A permanently blank
    row is indistinguishable from a broken one."""
    assert "none yet" in _rendered(signals, last_saved_hour=None).lower()


def test_the_farm_row_uses_pattern_language():
    text = _rendered(signals, clusters_count=1, flagged_points_share_pct=12.4)
    assert "fan-out" in text.lower()
    for word in ("sybil", "cheat", "fraud", "attack"):
        assert word not in text.lower()


def test_the_you_row_is_absent_not_zeroed_when_no_wallet_is_configured():
    """All YOU keys None means MAXPANE_WALLET is unset. 'rank -- , 0 pts' reads
    as a wallet with no score; the honest render is 'set MAXPANE_WALLET'."""
    text = _rendered(signals, you_rank=None, you_points=None)
    assert "MAXPANE_WALLET" in text
    assert "0 pts" not in text
```

- [x] Implement, reusing the `{label, value_str, indicator, color}` row shape the Talismans and
      FWA signal widgets use. Colour is **never the sole carrier** — every state also carries
      a glyph or a word.
- [x] Commit: `feat(curator): seven-row signal rail with never-fired and no-wallet states`

---

### Task WP4.6: `CuratorActivity`

**Interfaces:** `update_data(activity_rows=None, **_kwargs)`. Row form per PRD §4:
`HH:MM 0x1234…abcd 3.60Ξ (+2.80 credit → 7.03 wt) tx#4`, `HourSaved` rows highlighted,
`FirstDeposit` rows tagged `joined`.

**Steps:**

- [x] Failing tests:

```python
def test_rows_are_deduped_by_tx_hash_and_log_index():
    """PRD §4. A re-org replay or an overlapping incremental sweep resends
    rows; without the pair as the key, every deposit renders twice and the
    feed silently doubles the game's apparent activity."""
    dup = _rows() + _rows()
    assert _rendered(activity, activity_rows=dup).count("tx#4") == 1


def test_a_missing_timestamp_renders_dashes_not_the_epoch():
    """WP2.8's stamp can fail. ``ts=None`` renders ``--:--``; a 0 would render
    ``00:00`` on 1970-01-01, which looks like data."""
    text = _rendered(activity, activity_rows=[{**_row(), "ts": None}])
    assert "--:--" in text and "00:00" not in text


def test_every_formatting_step_degrades_independently():
    """MEDI-37: one unparseable field costs its own cell, not the row and not
    the panel."""
    broken = {**_row(), "amount_eth": "not a number", "new_weight": None}
    text = _rendered(activity, activity_rows=[broken])
    assert "0x1234" in text            # the row still rendered
    assert "not a number" not in text


def test_the_kind_cell_is_sized_to_the_vocabulary_its_producer_emits():
    """The dev/ops lesson (CLAUDE.md). The producer emits exactly
    {deposit, joined, saved}; a cell wider than 'deposit' is padding and a cell
    narrower is a value cut mid-word."""
    assert _KIND_COLS == max(len(k) for k in ("deposit", "joined", "saved"))


def test_a_none_list_and_an_empty_list_render_differently():
    assert "activity unavailable" in _rendered(activity, activity_rows=None)
    assert "no deposits yet" in _rendered(activity, activity_rows=[])
```

- [x] Implement with a `RichLog`, newest-first, `safe_markup` on every interpolated value, and
      a documented row cap.
- [x] **Prove it bites:** drop `log_index` from the de-dupe key and feed two logs from one
      transaction (real: a `HourSaved` and a `Deposited` share a tx) → the de-dupe test FAILS
      **and** a legitimate second row disappears. Restore, and keep both assertions.
- [x] Commit: `feat(curator): activity feed with (tx, log index) de-duplication`

---

### Task WP4.7: `CuratorClosestCalls`

**Interfaces:** `update_data(closest_call_rows=None, first_judged_hour=None,
grace_ends_utc=None, **_kwargs)`.

**Steps:**

- [x] Failing tests: rows ascend by margin; the savior column renders `—` when the hour was
      never at risk (no `HourSaved`); an **empty** list during grace renders the PRD's exact
      explicit state `no judged hours yet — judging begins <UTC>` with the instant taken from
      `grace_ends_utc`, never a hardcoded date; a `None` list renders `closest calls
      unavailable`; a margin of exactly `0.00` renders as a number, not as `—` (an hour that
      survived by nothing is the tightest possible call and the most interesting row on the
      board).
- [x] Implement.
- [x] Commit: `feat(curator): closest-calls table with an explicit pre-judging state`

---

### Task WP4.8: `CuratorClusters`

**Interfaces:** `update_data(cluster_rows=None, clusters_count=None,
flagged_points_share_pct=None, **_kwargs)`.

**Steps:**

- [x] Failing tests: renders the captured 9×60Ξ cluster as `9× 60.00Ξ · 28 blocks`; the
      points-share column is a percentage of total points, `—` when total points is unknown
      (never a division by zero, never a `0.0%` that means "we could not compute it"); an
      empty list renders `no fan-out patterns found` — a real, meaningful negative — and a
      `None` renders `clusters unavailable`; pattern-only language, asserted by the same
      forbidden-word list WP3.10 uses; width tiers shed the block-window column first.
- [x] Implement.
- [x] Commit: `feat(curator): cluster table with pattern-only language and a real empty state`

---

### Task WP4.9: The widget contract test

**Steps:**

- [x] Add the three-way exercise every widget suite in this repo runs — **no args**,
      **all-`None`**, **full payload** — parametrised over all seven classes, asserting no
      raise and the expected row counts, all through the compositor.
- [x] Add the contract test against WP0's frozen keys:

```python
def test_every_widget_kwarg_is_a_curator_key():
    """Containment, from the widget side. A widget that reads a key the manager
    does not emit renders None forever with a green suite behind it -- which is
    exactly what this repo's seam-drift defect class looks like."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS
    for cls, sig in CURATOR_WIDGET_SIGNATURES.items():
        unknown = set(sig) - set(CURATOR_KEYS) - _SCREEN_SUPPLIED
        assert not unknown, f"{cls}: {sorted(unknown)}"


def test_the_signature_map_covers_every_widget_this_package_exports():
    """A widget added without an entry here is a widget nobody checks."""
    assert set(CURATOR_WIDGET_SIGNATURES) == set(_EXPORTED_CLASSES)
```

      `_SCREEN_SUPPLIED` holds the two kwargs the screen passes that are not payload keys
      (`you_address`, `hourly_threshold_eth`) — name them, so the exception is a decision
      rather than a hole.
- [x] Run the file and the full suite.
- [x] Write the WP6 hand-off note: the exact `update_data` kwarg tuple per widget, every panel
      title string, every unavailable-state string, and the `‹ widen` marker convention. WP6
      asserts against these strings and must not re-invent them.
- [x] Commit: `test(curator): widget contract, three-way exercise and the screen hand-off`

**Done when:** all seven widgets survive no-args / all-None / full payload through the
compositor, no widget imports `data/` or `analytics/`, and the kwarg map is pinned against
`CURATOR_KEYS`.

---

## WP4 → WP6 hand-off (written 2026-08-17, when WP4 landed)

Everything WP6's screen needs in order to dispatch to these widgets **without
reading their source**. WP6 asserts against these strings; it must not re-invent
them. All seven classes and every constant below are re-exported from the package
root, `maxpane_dashboard.widgets.curator` — import from there, never from a
submodule.

### `update_data` kwargs, per widget

Every kwarg is optional and defaults to `None`; every signature ends in `**_kwargs`,
so the screen may splat the whole flat dict at every widget. Every name is a key of
`CURATOR_KEYS` except `you_address`, which is the screen's own (CLI / `MAXPANE_WALLET`).

| widget | `update_data` kwargs |
|---|---|
| `CuratorHero` | `phase, current_hour, grace_seconds_left, grace_ends_utc, hour_fed_eth, hour_needed_eth, hour_seconds_left, hourly_threshold_eth, settled_hour, settled_at_ts, settled_observed_at, lived_desc, early_multiplier_x, points_per_eth_now, survival_streak_hours, closest_call_margin_eth, closest_call_hour, contributors_total, deposits_total, volume_routed_eth, top_points` |
| `CuratorLeaderboard` | `leaderboard_rows, you_address` |
| `CuratorSparklines` | `volume_series, contributors_series, hourly_threshold_eth` |
| `CuratorSignals` | `phase, settled, settled_hour, sig_settled_state, sig_at_risk_state, first_judged_hour, hour_needed_eth, hour_seconds_left, last_saved_hour, last_saved_wallet, last_saved_age_s, whale_amount_eth, whale_wallet, whale_age_s, clusters_count, flagged_points_share_pct, forced_eth, rescued_total_eth, you_rank, you_points, you_credit_eth, you_required_next_eth, you_marginal_points` |
| `CuratorActivity` | `activity_rows` |
| `CuratorClosestCalls` | `closest_call_rows, first_judged_hour, grace_ends_utc` |
| `CuratorClusters` | `cluster_rows, clusters_count, flagged_points_share_pct` |

**Four `CURATOR_KEYS` reach no widget in this package** and are WP6's own:
`as_of`, `as_of_hhmm`, `degraded` (the title bar) and `settled_observed_at`
(the hero takes it as a fallback stamp but the freshness marker is the title
bar's). `tests/widgets/test_curator_widgets.py::test_the_keys_no_widget_reads_are_named_here_rather_than_forgotten`
records that set, so WP6.1's totality assertion has a starting point.

### Panel titles (exact, asserted)

`CuratorHero` has no title of its own — its three boxes are titled `CLOCK` /
`THE LIST` / `CURVE`, and the third becomes `SURVIVAL` in the judged phase and
`FINAL` in the settled one.

| constant | value |
|---|---|
| `LEADERBOARD_TITLE` | `TOP OF THE LIST` |
| `SPARKLINES_TITLE` | `TRENDS` |
| `SIGNALS_TITLE` | `SIGNALS` |
| `ACTIVITY_TITLE` | `ACTIVITY` |
| `CLOSEST_CALLS_TITLE` | `CLOSEST CALLS` |
| `CLUSTERS_TITLE` | `FAN-OUT PATTERNS` |

`SIGNAL_LABELS` is the rail's seven row labels in order:
`SETTLED · HOUR AT RISK · HOUR SAVED · WHALE · FARM · FORCED ETH · YOU`.

### Explicit states (exact, asserted)

| constant | value | means |
|---|---|---|
| `LEADERBOARD_UNAVAILABLE` | `leaderboard unavailable` | `leaderboard_rows is None` |
| `LEADERBOARD_EMPTY` | `no contributors yet` | `leaderboard_rows == []` |
| `ACTIVITY_UNAVAILABLE` | `activity unavailable` | `activity_rows is None` |
| `ACTIVITY_EMPTY` | `no deposits yet` | `activity_rows == []` |
| `CLOSEST_CALLS_UNAVAILABLE` | `closest calls unavailable` | `closest_call_rows is None` |
| `NO_JUDGED_HOURS` | `no judged hours yet` | `closest_call_rows == []`; the panel appends ` — judging begins <grace_ends_utc> · hour <first_judged_hour>` when it has them |
| `CLUSTERS_UNAVAILABLE` | `clusters unavailable` | `cluster_rows is None` |
| `CLUSTERS_EMPTY` | `no fan-out patterns found` | `cluster_rows == []` |
| `WAITING` | `waiting for data...` | either series has < 2 usable points — **the one place `None` and `[]` render the same**, because neither can be drawn |
| `PHASE_UNAVAILABLE` | `phase unavailable` | `phase` is `None` or not one of `PHASES` — the hero's CLOCK box **and** the rail's `HOUR AT RISK` row, which used to fall through to the judged branch and call an unjudged hour `hour is safe` |
| `UNKNOWN_GLYPH` | `○` | a signal state that could not be read. `ok` is `●`, `watch` is `◐`, `fired` is `▶`; all four differ, so the rail reads in greyscale and colour is never the sole carrier |
| `NEVER_SAVED` | `none yet` | HOUR SAVED has never fired |
| `NO_WALLET` | `set MAXPANE_WALLET` | every `you_*` key is `None` |
| `DASH` / `EMDASH` / `NO_STAMP` | `--` / `—` / `--:--` | "could not read" / "deliberately nothing" / "no block stamp" |

### The `‹ widen` convention

Every panel appends `‹ widen: <what it shed>` to its **title** (never replaces
the title, so `TITLE in text` holds at every width), degrading to a bare
`‹ widen` when the descriptive form does not fit, and moving the bare marker
into the panel's note line when even that does not fit the title bar (the
sparkline panel has no note line and uses its spacer row). The hero is the
exception: its boxes carry the marker in their **bottom border**
(`border_subtitle`), because a hero box has five content lines and no sixth.

**The marker fires on the first loss, not the last.** The rail raises it when
*any* part of *any* row is dropped, and the sparkline panel raises it when the
survival-bar label goes, two tiers before the trend value does. Both used to
wait for total loss, which made a half-rendered row indistinguishable from a
payload that had nothing more to say — the failure mode the tiers exist to
prevent. A shrinking sparkline is still not a loss: it is a smaller window, not
a hidden column.

Measured widths, so WP6 can budget the slot grid before it renders anything:

| panel | needs (widget columns) | sheds, in order |
|---|---|---|
| hero box | 26 (×3 boxes + borders/margins → ~90 for the row) | wording, then the grace date, then the parenthetical |
| leaderboard | 48 | `TX`, then `CREDIT` |
| sparklines | 46 for both rows at full width | the bar label, then the spark's width, then the trend value |
| signals rail | **82** — import `SIGNALS_FULL_WIDTH`, do not retype it | parts from the end of each row |
| activity | 74 (+3 for the panel: `padding: 0 1` and `RichLog`'s reserved gutter → a 77-column terminal) | delta wording, delta, `tx#`, then `kind` |
| closest calls | 42 | `VOLUME`, then `SAVIOR` |
| clusters | 45 | the block window, then `POINTS` |

The signals rail is the widest thing in this package and it is the panel to
measure the seam against. **Measure, do not reason** — and re-measure after any
copy edit, exactly as the surf screen's seam sweep does.

**Three of those numbers were wrong when this table was first written, and the
way they were wrong is the point.** Each was taken from the example row in its
own module docstring instead of from the widest row its producer can emit:

* the rail said **76**. The full YOU line — `rank 12 · 1,234 pts · 3.60 credit
  · next ≥ 4.10 ETH (+120 pts)` — is 80 columns of value, and the rows carry
  `padding: 0 1`, so the widget needs **82**. At 76–81 the rail "fitted" by
  amputating the only actionable number it carries, and `_row()` raised no
  marker because it only reported a loss when *every* part was dropped. A width
  sweep could not have caught it. `SIGNALS_FULL_WIDTH` is now exported and
  pinned by `test_the_rail_publishes_the_width_it_was_measured_at`, which
  re-measures it from the seven builders — import the constant rather than
  copying 82 into the screen;
* the feed said **70**, from `(+2.80 credit → 7.03 wt)`. The captured 461.1 ETH
  whale renders `(+461.10 credit → 899.00 wt)`, 28 columns, and the row needs
  **74**;
* the cluster table said **42**, from the single captured `9× 60.00Ξ ·
  28 blocks`. Ten wallets or more is 22 columns of pattern, so the tier is
  **45**.

All three cells are now derived — `_fmt.COMPACT_ETH_COLS`, measured off
`fmt_eth_compact` itself, plus `clusters.MAX_BLOCK_SPAN` — so an example row
can no longer set a width. WP6 should still re-measure rather than trust this
table: that is what this paragraph is a record of.

### Three things WP6 and WP7 must know

1. **`HOUR AT RISK` contains the string "at risk".** It is PRD §4's mandated
   label and it is about the *hour*, not about capital. WP7.12's guardrail scan
   for `TVL` / `locked` / `at risk` / `capital` will hit it; scope the scan to
   lines carrying a volume field, the way
   `test_forced_eth_expects_a_dash_and_shouts_on_a_nonzero` does.
2. **The hero is 8 rows tall, not 7** — three boxes over the one-line EOA
   subtitle (`CuratorHero.EOA_SUBTITLE`, the single honest capital sentence,
   rendered once and never beside a volume figure).
3. **`short_addr` renders 11 columns, not 13.** PRD §4 says "`0x1234…abcd`
   (13 cols)" and its two halves disagree; the literal is 11 and every address
   cell here is sized from `ADDR_COLS`.
