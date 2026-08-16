# WP6 — `screens/curator.py` (the slot grid, the phases, the measured width)

**Goal:** Compose the seven curator widgets into the approved slot grid with a phase-aware
title bar, `CURATOR_KEYS` dispatch, the `c` swap with a phase-aware default, `RefreshGuard`
scheduling, and a **measured, pinned** full-layout width that does not move
`__main__.FULL_LAYOUT_COLUMNS`.

**Dependencies:** WP0 (`CURATOR_KEYS`, `PHASES`), WP4 (the seven widget classes and their
frozen kwargs), WP5 (`CuratorManager.fetch_and_compute()` / `close()`). Wave 4, alone.

**Owner note.** This WP owns exactly two files:

- `maxpane_dashboard/screens/curator.py`
- `tests/screens/test_curator_screen.py`

It does **not** touch `app.py`, `screens/game_select.py`, `__main__.py` or
`themes/minimal.tcss` — those have one owner, WP7. Two coordination points are called out
below and both are enforced mechanically rather than by comment.

### Interface consumed from WP4 (the widget contract)

WP4's hand-off note is the authority for these; **quote it, do not re-derive it.** The screen
dispatches exactly the PRD §5 key groups, keyword by keyword; WP4 accepts them all, all
optional, all defaulting to `None`, with `**_kwargs` swallowing extras.

| Widget | `update_data(...)` kwargs |
|---|---|
| `CuratorHero` | `phase, current_hour, grace_seconds_left, grace_ends_utc, hour_fed_eth, hour_needed_eth, hour_seconds_left, settled_hour, settled_at_ts, lived_desc, settled_observed_at, early_multiplier_x, points_per_eth_now, survival_streak_hours, closest_call_margin_eth, closest_call_hour, contributors_total, deposits_total, volume_routed_eth, top_points` |
| `CuratorLeaderboard` | `leaderboard_rows` + the screen-supplied `you_address` |
| `CuratorSparklines` | `volume_series, contributors_series` + the screen-supplied `hourly_threshold_eth` |
| `CuratorSignals` | `phase, sig_settled_state, sig_at_risk_state, hour_needed_eth, hour_seconds_left, last_saved_hour, last_saved_wallet, last_saved_age_s, whale_amount_eth, whale_wallet, whale_age_s, clusters_count, flagged_points_share_pct, forced_eth, rescued_total_eth, you_rank, you_points, you_required_next_eth, you_marginal_points` |
| `CuratorActivity` | `activity_rows` |
| `CuratorClosestCalls` | `closest_call_rows, grace_ends_utc` + `first_judged_hour` |
| `CuratorClusters` | `cluster_rows, clusters_count, flagged_points_share_pct` |

Meta keys the screen itself consumes and never dispatches: `as_of`, `as_of_hhmm`, `degraded`,
`settled`, `phase` (dual-consumed — the title bar and the hero and the rail all read it).

Rendered strings this WP asserts against, all owned by WP4: the panel titles `LEADERBOARD`,
`ACTIVITY`, `SIGNALS`, `CLOSEST CALLS`, `CLUSTERS`; the seven detector labels `SETTLED`,
`HOUR AT RISK`, `HOUR SAVED`, `WHALE`, `FARM`, `FORCED ETH`, `YOU`; the hero headlines
`GRACE —`, `HOUR`, `SETTLED AT HOUR`; the copy `routed (all refunded)`; the house marker
`‹ widen`. **If one of these mismatches, report it to WP4 and do not restyle their widget.**

### Layout (PRD §4, the canonical slot grid from `screens/talismans.py:62-84`)

```
#title-bar     THE LIST · hour N · GRACE/JUDGED/SETTLED · as of HH:MM [· ⚠ state, logs] · vX.Y.Z
#hero-row      CuratorHero (full width, 3 boxes)                        height auto
#middle-row    CuratorLeaderboard (3fr)   | #curator-right-rail (2fr)   1fr
                                          |   CuratorSparklines
                                          |   CuratorSignals
#separator
#bottom-row    CuratorActivity (1fr) | CuratorClosestCalls (1fr)        auto
                                     | CuratorClusters (1fr, hidden)
                                       -- one or the other, toggled with `c`
StatusBar
```

### Ground rules

- **The screen is clock-free.** Every time-derived string (`grace_seconds_left`,
  `hour_seconds_left`, ages) arrives pre-computed in the payload, so a captured instant
  replays forever. A test asserts the module contains no `time.time()` / `datetime.now()`.
- **Per-widget guarded dispatch.** One widget raising must never cost the other six their
  refresh. A *manager* failure touches only the StatusBar.
- **Degradation reaches the title bar** behind the house warning glyph `⚠ `, naming the
  failing groups — the shared `StatusBar` has no `set_degraded()`.
- Every payload value in this file's fixtures is **derived from the WP0 captures or from the
  producer's own vocabulary**. Inventing a plausible-looking number calibrates the width sweep
  against a payload the manager can never emit.
- Commit after each task.

---

### Task WP6.1: Skeleton — compose, bindings, `DEFAULT_CSS`

**Interfaces:** produces `class CuratorScreen(RefreshGuard, Screen)` with
`__init__(self, data_manager, poll_interval: int = 30, name: str = "curator",
wallet: str | None = None, **kwargs)`, `REFRESH_WORKER_NAME = "curator-refresh"`,
`BINDINGS = [r, c]`, `INITIAL_TITLE = "THE LIST · WhitelistCurator · Ethereum Mainnet"`, slot
ids `#title-bar #hero-row #middle-row #curator-right-rail #separator #bottom-row`, and
`CURATOR_FULL_LAYOUT_COLUMNS` (provisional 143 until WP6.6 measures it).

**Steps:**

- [ ] Read `screens/fwa.py` end to end (the `c` swap's rationale is in its docstring) and skim
      `screens/talismans.py` for the second example and `screens/surf.py` for the rail.
- [ ] Write the failing test module: the `_FakeManager` (never touches the network,
      `raises=True` available as a *defensive* double), `_Harness` and `_ThemedHarness`
      (the latter loads the real `minimal.tcss`, which is valid before WP7 adds a curator
      block — `DEFAULT_CSS` stays in charge and keeps passing after), `_screen_text` via
      `_compositor.render_strips()`, `_frozen_payload(**overrides)` built from
      `{k: sample.get(k) for k in CURATOR_KEYS}`, `_all_none_payload()`, and three phase
      payloads `_grace_payload()` / `_judged_payload()` / `_settled_payload()`.
- [ ] The fixture's captures-derived constants, all from WP0.7's pins:
      `LAUNCH = 1_786_910_327`, `GRACE_END = 1_786_996_727`,
      `FIRST_JUDGED_COMPLETE = 1_787_000_327`, hour-1 volume `730.31…` ETH (from
      `0x27d2c90dce228ae5b0`), `contributors_total = 145`, `deposits_total = 226`,
      `volume_routed_eth` from `0x560119983627C22D4F`, `early_multiplier_x = 1.9491`,
      top wallet `0x381fe486…` at credit 461.1 ETH and ≈30 035 points, and the 9×60Ξ cluster
      at blocks 25 770 115–25 770 143.
- [ ] First tests: `test_bindings_are_refresh_and_the_view_toggle` (`{"r", "c"}`);
      `test_screen_mounts_all_seven_widgets` (hero row 1 child, middle row 2, rail 2,
      bottom row 3 with exactly one of the swap pair displayed);
      `test_curator_keys_covers_the_local_signature_map` (dispatched ⊆ `CURATOR_KEYS`, and
      `CURATOR_KEYS − dispatched − META_KEYS` is empty).
- [ ] Run: expect `ModuleNotFoundError: … screens.curator`.
- [ ] Implement the skeleton. `DEFAULT_CSS` is a **structural fallback only** — WP7 restates it
      in `minimal.tcss`. **No vertical padding on `#hero-row` or `#curator-right-rail`**: the
      rail holds a seven-row signal panel and the FWA coverage-badge clipping bug is exactly
      one `padding: 1 2` away.
- [ ] Run to green. Commit:
      `feat(curator): screen skeleton with the seven-widget slot grid`

---

### Task WP6.2: The title line and the format helpers (pure)

**Interfaces:** produces `_title_line(data) -> str`, `_fmt_age`, `_fmt_eth`, `_fmt_int`,
`_fmt_degraded`, `_phase_word(phase)`, `_num` — all import-safe with no app running.

**Steps:**

- [ ] Failing tests:

```python
def test_the_title_names_the_phase_in_words():
    assert _title_line(_judged_payload()).startswith(
        "THE LIST · hour 24 · JUDGED · as of 20:15")


def test_an_unknown_phase_says_so_rather_than_guessing():
    """phase=None is a failed isSettled read. 'GRACE' would be a guess about
    whether the game is alive."""
    assert "phase —" in _title_line(_frozen_payload(phase=None))


def test_all_none_shows_emdashes_never_zeros():
    line = _title_line(_all_none_payload())
    assert "hour —" in line and "phase —" in line
    assert "0.00" not in line and "hour 0" not in line


def test_degraded_groups_ride_the_house_warning_glyph():
    from maxpane_dashboard.data.curator_manager import SOURCES
    line = _title_line(_frozen_payload(degraded=sorted(SOURCES)))
    assert "⚠ logs, state, wallet" in line


def test_the_settled_title_carries_the_observation_time_not_a_staleness_alarm():
    """Under an outage after settlement the freshness marker moves and the
    phase word does not (PRD §3). The title must make that legible without
    reading as a fault."""
    line = _title_line(_settled_payload(degraded=["state", "logs"]))
    assert "SETTLED" in line and "⚠" in line
    for wrong in ("ERROR", "BROKEN", "no data"):
        assert wrong not in line
```

- [ ] Implement, ordering the line so warnings precede the version tail: `#title-bar` is one
      row high and the tail is what gets clipped.
- [ ] **Prove it bites:** make `_fmt_eth` coerce `None` to `0.0` →
      `test_all_none_shows_emdashes_never_zeros` FAILS. Restore.
- [ ] Commit: `feat(curator): phase-aware title line with the warning-glyph degradation`

---

### Task WP6.3: `_do_refresh` — dispatch, all-`None`, manager failure

**Steps:**

- [ ] Failing tests: `_record_dispatches` wraps every widget's `update_data` and asserts each
      received **exactly** its signature's kwargs (`set(kwargs) == set(signature)`, so an extra
      and a missing both fail by name); nothing in `CURATOR_KEYS` reaches no widget;
      the all-`None` payload renders explicit unavailable states with no `0.00 ETH`,
      no `0 wallets`, no `hour 0`; a raising manager touches only the StatusBar
      (`MANAGER_FAILURE_SECONDS = 999`) and leaves the previous frame standing.
- [ ] State plainly in the test module docstring: **the specified outage path is the all-`None`
      payload, not an exception.** WP5 guarantees `fetch_and_compute` never raises and pins it
      with `test_no_exception_escapes_when_every_call_raises`. The `raises=True` double is belt
      and braces for a mis-wired manager and must never become the documented outage contract.
- [ ] Implement the guarded dispatch (one `try/except` per widget, the `screens/surf.py` shape).
- [ ] **Prove it bites:** delete one kwarg from the `CuratorSignals` dispatch → the dispatch
      test FAILS naming it. Delete the whole `CuratorClusters` block → it FAILS with
      `contract keys reach no widget: [...]`. Restore both.
- [ ] Commit: `feat(curator): dispatch CURATOR_KEYS to widgets with per-widget guards`

---

### Task WP6.4: The `c` swap with a phase-aware default

**The rule (PRD §4):** the bottom-right slot shows **CLUSTERS** until the first judged hour
completes, then **CLOSEST CALLS**; `c` toggles either way at any time.

**Steps:**

- [ ] Failing tests:

```python
def test_the_default_view_follows_the_phase():
    """Clusters are the interesting table during grace -- there is nothing to
    survive yet, so a CLOSEST CALLS panel would open on an empty state for the
    dashboard's whole first day."""
    assert _default_view("grace") == "clusters"
    assert _default_view("judged") == "closest"
    assert _default_view("settled") == "closest"
    assert _default_view(None) == "clusters"     # unknown -> the never-empty one


def test_the_default_flips_once_and_does_not_fight_the_user():
    """The phase-aware default applies until the user presses `c`. After that
    the choice is theirs, even across a phase change -- a panel that snaps back
    while you are reading it is worse than a suboptimal default."""
    screen = ...
    await _refresh(screen, _grace_payload())
    assert screen._active_view == "clusters"
    await pilot.press("c")
    assert screen._active_view == "closest"
    await _refresh(screen, _judged_payload())    # phase changed under them
    assert screen._active_view == "closest"      # unchanged: user chose
    await _refresh(screen, _settled_payload())
    assert screen._active_view == "closest"


def test_the_hidden_view_still_receives_updates():
    """Both stay mounted and both are dispatched to, so toggling is a
    visibility flip with no refetch and no blank first frame."""
    ...


def test_both_views_occupy_the_identical_slot():
    """Give either a different width and the layout jumps on every `c`."""
    assert (clusters.size.width, clusters.size.height) == (closest.size.width,
                                                           closest.size.height)


def test_the_toggle_survives_a_missing_widget():
    screen.query_one(CuratorClusters).remove()
    screen.action_toggle_view()          # must not raise


def test_the_status_bar_names_the_active_view():
    ...
```

- [ ] Implement `action_toggle_view()` plus `_user_chose_view: bool` (set by the action, never
      by a refresh) and `_apply_phase_default(phase)` called from `_do_refresh` only while
      `_user_chose_view` is false.
- [ ] **Prove it bites:** let `_apply_phase_default` run unconditionally → the
      "does not fight the user" test FAILS. Restore.
- [ ] Commit: `feat(curator): c swaps clusters and closest calls with a phase-aware default`

---

### Task WP6.5: The three phases, rendered

**Steps:**

- [ ] Three composited tests, one per phase, at the pinned size:

```python
async def test_the_grace_screen_renders_the_countdown_and_the_curve():
    text = await _render(_grace_payload())
    assert "GRACE —" in text and "judging begins in" in text
    assert "2026-08-17 19:58:47 UTC" in text
    assert "1.95×" in text or "1.9491" in text      # WP4 owns the exact form
    assert "n/a until hour 24" in text              # HOUR AT RISK during grace
    assert "no judged hours yet" in text            # the closest-calls state
    assert "routed (all refunded)" in text


async def test_the_judged_screen_renders_the_hour_clock_and_the_risk_state():
    text = await _render(_judged_payload())
    assert "HOUR 24" in text and "/5.00 ETH" in text
    assert "1.00×" in text                          # the flat multiplier
    assert "HOUR AT RISK" in text


async def test_the_settled_screen_renders_an_archive_not_a_fault():
    """PRD §11: a settled contract renders an archive, not an error state."""
    text = await _render(_settled_payload())
    assert "SETTLED AT HOUR" in text and "list FROZEN" in text
    for wrong in ("unavailable", "stale", "error", "no data", "⚠"):
        assert wrong not in text.lower() if wrong != "⚠" else wrong not in text


async def test_the_settled_screen_under_a_total_outage_keeps_the_phase():
    """The flagship. The freshness marker moves; the verdict does not."""
    text = await _render(_settled_payload(degraded=["logs", "state", "wallet"]))
    assert "SETTLED" in text
    assert "⚠ logs, state, wallet" in text
    assert "as of" in text


async def test_all_seven_detector_rows_reach_the_compositor_in_every_phase():
    """The rail is inside a fixed-height column; YOU is last and goes first."""
    for payload in (_grace_payload(), _judged_payload(), _settled_payload()):
        text = await _render(payload)
        for label in ("SETTLED", "HOUR AT RISK", "HOUR SAVED", "WHALE",
                      "FARM", "FORCED ETH", "YOU"):
            assert label in text, (label, payload["phase"])
```

- [ ] Mark the judged and settled payloads
      `# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>` (WP1.4 / WP1.5).
- [ ] Commit: `test(curator): all three phases rendered through the compositor`

---

### Task WP6.6: Measure and pin the full-layout width

**Width is measured, never reasoned.** Target ≤ **143** so `__main__.FULL_LAYOUT_COLUMNS` does
not move — FWA's 143 stays the binder. If a table cannot clear it, the table **sheds a column
with `‹ widen`**; the constant does not rise.

**Steps:**

- [ ] Add the helpers the surf suite proved worth having:
      `_widen_markers(width, payload=None) -> int` (composited count over the whole screen) and
      `_panels_asking_for_width(width) -> set[str]` (which panel's rectangle each marker is in,
      with `assert len(marked) == text.count("‹ widen")` so no panel can hide one).
- [ ] Write the tests **against the constant**, so a wrong pin turns them red rather than
      documenting fiction:

```python
async def test_the_measured_width_clears_every_marker():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS) == 0


async def test_the_measured_width_is_tight_not_padded():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS - 1) > 0


async def test_both_c_views_clear_at_the_same_width():
    """The swap must not change the requirement; otherwise the documented
    number is true for one keypress and false for the other."""
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS, view="clusters") == 0
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS, view="closest") == 0


async def test_the_widest_phase_is_the_one_measured():
    """A data-dependent width must be measured against the state the data is
    normally in (CLAUDE.md, the IMD/FP peg lesson). Three phases print
    different worst cases: SETTLED prints the longest hero line
    ('SETTLED AT HOUR 24 · lived 1d 01h'), JUDGED prints the longest clock line
    ('HOUR 24 · fed 4.87/5.00 ETH · 12:03 left'), and GRACE prints the longest
    absolute timestamp. The pinned number is the MAX over all three, asserted
    here rather than assumed from whichever fixture was handy."""
    per_phase = {p: await _first_clean_width(_payload_for(p)) for p in PHASES}
    assert CURATOR_FULL_LAYOUT_COLUMNS == max(per_phase.values()), per_phase


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    assert await _widen_markers(CURATOR_FULL_LAYOUT_COLUMNS - 20) > 0


def test_curator_fits_inside_the_documented_app_width():
    """WP7 coordination tripwire -- mechanical, not a comment."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
    assert CURATOR_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"curator needs {CURATOR_FULL_LAYOUT_COLUMNS} columns but the app "
        f"documents {FULL_LAYOUT_COLUMNS}. Do NOT edit __main__.py from WP6 -- "
        "report to WP7, which owns it."
    )
```

- [ ] **Run the sweep.** Column by column, over the real screen, in all three phases and both
      `c` views (throwaway; do not commit it):

```bash
cd /Library/Vibes/autopull && .venv/bin/python - <<'EOF'
import asyncio, importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "_curator_harness", Path("tests/screens/test_curator_screen.py"))
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)

for w in range(110, 181):
    total = 0
    for phase in ("grace", "judged", "settled"):
        for view in ("clusters", "closest"):
            total += asyncio.run(
                h._widen_markers(w, payload=h._payload_for(phase), view=view))
    print(w, total, sorted(asyncio.run(h._panels_asking_for_width(w))))
    if total == 0:
        print("=> CURATOR_FULL_LAYOUT_COLUMNS =", w); break
EOF
```

- [ ] Pin the printed number and replace the `provisional` comment with
      `#: Measured against composited output (three phases x two c views), not estimated.`
      Record in the module docstring **which panel was the last one asking for a column** —
      that fact has changed hands three times on the surf screen and was restated in prose
      each time with no test that could contradict it. Here it is pinned by
      `_panels_asking_for_width`.
- [ ] **If the number exceeds 143**, do not raise anything: go back to the widest panel and
      shed a column with `‹ widen`, then re-sweep. Only if that is genuinely impossible does
      `test_curator_fits_inside_the_documented_app_width` stay red **by design**, with the
      number recorded in the WP7 hand-off for WP7.7 to raise `FULL_LAYOUT_COLUMNS`, the README
      width table and the `--font-size` help text together.
- [ ] Commit: `feat(curator): pin the measured full-layout width across phases and views`

---

### Task WP6.7: The worst-case title bar

**Steps:**

- [ ] Measure `WORST_CASE_TITLE_COLUMNS`: the longest title the manager can actually emit —
      the **settled** phase (longest phase word plus the hour), all three `SOURCES` degraded
      (built from the real tuple, not typed out), the `as of HH:MM` marker and the version
      tail. `#title-bar` is a `height: 1` `Static` that **wraps out of existence** rather than
      ellipsising, so a lost tail is silent.
- [ ] Pin it in both directions (whole tail present at N, absent at N−1) and assert
      `WORST_CASE_TITLE_COLUMNS <= CURATOR_FULL_LAYOUT_COLUMNS` — two independently swept
      constants, never one compared with itself.
- [ ] Commit: `test(curator): measure the worst-case title bar and prove it fits`

---

### Task WP6.8: `RefreshGuard` integration

**Steps:**

- [ ] Structural test: `RefreshGuard` precedes `Screen` in the MRO;
      `REFRESH_WORKER_NAME == "curator-refresh"`.
- [ ] Event-driven overrun test with a `_BlockingManager` (no sleeps beyond bare
      `asyncio.sleep(0)` yields): a tick landing mid-refresh is **skipped**, `_refresh_skipped`
      increments, `manager.calls` stays 1, `_refresh_in_flight` lowers, and the completed
      refresh actually rendered.
- [ ] **Prove it bites:** comment out the `if self._refresh_in_flight:` early return in
      `screens/refresh_guard.py`, watch the overrun test go red, and **restore the file
      exactly** — this WP does not own it; `git diff` must be empty for that path afterwards.
- [ ] Run the generic suite too and confirm its auto-discovery picks `CuratorScreen` up:
      `.venv/bin/python -m pytest tests/screens/test_refresh_guard.py tests/screens/test_curator_screen.py -v`
- [ ] Run `.venv/bin/python -m pytest tests/screens/ -q` — nothing outside curator may move.
- [ ] Write the WP7 hand-off note:
      1. copy `CuratorScreen.DEFAULT_CSS` into `minimal.tcss` as a
         `/* ── Curator screen ── */` block, FWA-style, **with no vertical padding on
         `#hero-row` or `#curator-right-rail`**;
      2. the measured `CURATOR_FULL_LAYOUT_COLUMNS` and whether it needs a
         `FULL_LAYOUT_COLUMNS` raise;
      3. `tests/screens/test_curator_screen.py::_FakeManager` is import-safe and reusable by
         the registration tests;
      4. WP7's offline-launch acceptance criterion should use an **all-`None` payload**, not a
         raising manager — the latter models a programming error, not an outage.
- [ ] Commit: `test(curator): prove skip-not-queue refresh scheduling on the curator screen`

**Done when:** all three phases render through the compositor, the width is swept and pinned
with the binding panel named, and the screen drops overrun ticks instead of queueing them.
