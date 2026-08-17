# WP5 — Per-wallet surfaces: the `y`-view linked line, clean rank, and the graded leaderboard flag

**Goal:** Give the reader their own linkage. On the `y` (YOUR STANDING) view add a `linked` line
and a clean-rank line; upgrade the leaderboard's boolean `⚑` to a confidence-graded marker. All
pattern-language, all `None`-not-`0`, all measured.

**Dependencies:** WP0 (the new keys `you_linked_*`/`you_clean_rank` + the `link_conf` sub-key on
`leaderboard_rows` + the routing table). Runs in **wave 1** in parallel with WP1. Builds against
synthetic payloads (the worst-case fixtures + hand-crafted linkage states); no manager needed.

**Owner note — this WP owns:**

- `maxpane_dashboard/widgets/curator/wallet.py` (adds the `linked` + clean-rank lines to
  `CuratorWalletStanding`)
- `maxpane_dashboard/widgets/curator/leaderboard.py` (grades the flag off the new `link_conf`
  row sub-key)
- additions to `tests/widgets/test_curator_widgets.py`

It **must not edit** `screens/curator.py` (WP4 wires the new kwargs from WP0's routing table and
this WP's hand-off), the manager, the models, or any other widget. If a key it needs is missing,
**report it to WP0/WP3**; do not add one.

### Ground rules

- **Widgets never import `data/` or `analytics/`** — the AST guard covers these edits.
- **`safe_markup` every third-party string** — the linkage reasons and the graded glyph are
  rendered from payload strings; an ENS name in a leaderboard row is the most attacker-controlled
  string on the screen.
- **Pattern-language only** — no `sybil/cheat/fraud/attack/abuse/wash` reaches a composited
  render (the linkage line renders "linked to a 1,995-wallet 0.45Ξ group · same funder", never
  an accusation). The existing `CuratorLeaderboard`/`CuratorSignals` pattern-language tests must
  stay green and the wallet-standing panel gets one of its own.
- **`None` is "we could not tell", never a confident negative** — the single most important
  honesty rule here (a green "clean" off an analysis that never ran is a lie in the reassuring
  direction).
- **Colour is never the sole carrier** — the graded flag has four distinct glyphs.
- Commit after each task.

### Interface consumed (frozen upstream, WP0)

New keys routed to this WP's widgets (WP0.5 routing table):

- `CuratorWalletStanding`: `you_linked_state` (`"clean"|"linked"|None`), `you_linked_reasons`
  (`list[str]`), `you_linked_group_size` (`int|None`), `you_clean_rank` (`int|None`).
- `CuratorLeaderboard`: `leaderboard_rows[*]["link_conf"]` (`"high"|"low"|"clean"|None`).

---

### Task WP5.1: `CuratorWalletStanding` — the `linked` line

**Interfaces:** extend `CuratorWalletStanding.update_data(...)` to accept `you_linked_state`,
`you_linked_reasons`, `you_linked_group_size` (the existing signature already carries the other
standing keys). Render one new line per PRD §6:

- `you_linked_state == "clean"` → `not linked to any group` (the representable negative);
- `you_linked_state == "linked"` → `linked to a 1,995-wallet 0.45Ξ group · same funder`
  (`you_linked_group_size` + the pattern-language `you_linked_reasons`, joined);
- `you_linked_state is None` → `-- unknown` (the B+C sweep has not run — **never** a confident
  "clean").

**Steps:**

- [ ] Failing tests (composited):

```python
async def test_the_linked_line_reads_unknown_before_the_analysis_runs():
    text = await _rendered(CuratorWalletStanding, you_linked_state=None,
                           **_standing_full())
    assert "unknown" in text
    assert "not linked" not in text          # never a confident negative

async def test_a_clean_wallet_says_not_linked():
    text = await _rendered(CuratorWalletStanding, you_linked_state="clean",
                           you_linked_reasons=[], **_standing_full())
    assert "not linked to any group" in text

async def test_a_linked_wallet_shows_pattern_language_reasons():
    text = await _rendered(
        CuratorWalletStanding, you_linked_state="linked",
        you_linked_group_size=1995,
        you_linked_reasons=["identical 0.45Ξ send", "same funder"],
        **_standing_full())
    assert "1,995" in text and "same funder" in text
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in text.lower(), word
```

- [ ] Implement, `safe_markup` on the reasons; the group size formatted with the shared
      `fmt_int`.
- [ ] **Bite (mandated honesty):** render `you_linked_state is None` as `not linked` → the
      confident-negative test reddens. Restore.
- [ ] Commit: `feat(curator): the y-view linked line, unknown before the analysis runs`

---

### Task WP5.2: `CuratorWalletStanding` — the clean-rank line

**Interfaces:** accept `you_clean_rank` and render it beside the raw rank per PRD §6: "you're
#412 raw, #47 with clear farms removed."

**Steps:**

- [ ] Failing tests: `you_clean_rank` set → `#412 raw · #47 clean` (or the measured form) both
      render; `you_clean_rank is None` with a `you_rank` set → the clean rank renders `-- unknown`
      (analysis not run), never equal to the raw rank; a **linked** reader (removed from the
      clean list) renders `clean rank: removed as a linked wallet` (pattern-language) rather than
      a number, because `you_clean_rank` is `None`-for-removed by WP3's contract — assert the
      widget distinguishes "removed" (linked) from "unknown" (not analyzed) using
      `you_linked_state`.
- [ ] Commit: `feat(curator): the y-view clean-rank line beside the raw rank`

---

### Task WP5.3: `CuratorLeaderboard` — the confidence-graded flag

**Interfaces:** grade the flag column off `leaderboard_rows[*]["link_conf"]` (additive; the
existing `flagged` bool stays). Per PRD §6: `⚑` linked-high, `◌` linked-low/one-family, empty
clean, `?` fold-not-run.

**Steps:**

- [ ] Failing tests (composited):

```python
def test_the_flag_has_four_distinct_glyphs():
    """Colour is never the sole carrier; a reader in greyscale must tell the
    four apart (the CuratorSignals precedent)."""
    from maxpane_dashboard.widgets.curator import leaderboard as lb
    glyphs = [lb._LINK_GLYPH[c] for c in ("high", "low", "clean", None)]
    assert len(set(glyphs)) == 4

async def test_link_conf_grades_the_flag():
    rows = [{**_lb_row(), "link_conf": "high"}, {**_lb_row(), "link_conf": "low"},
            {**_lb_row(), "link_conf": "clean"}, {**_lb_row(), "link_conf": None}]
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "⚑" in text and "◌" in text and "?" in text

async def test_the_flag_falls_back_to_the_tier_a_bool_when_link_conf_is_absent():
    """Before the analysis has ever run, link_conf is None on every row but the
    Tier-A `flagged` bool still marks the c-view clusters -- the two must not
    contradict.  `?` means fold-not-run, not clean."""
    rows = [{**_lb_row(), "flagged": True, "link_conf": None}]
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "?" in text            # graded says "not yet analyzed", not "clean"
```

- [ ] Implement `_LINK_GLYPH = {"high": "⚑", "low": "◌", "clean": " ", None: "?"}` and grade the
      cell, `safe_markup`. **The flag column never sheds** in the width tiers (PRD §6) — assert
      it survives the narrowest tier.
- [ ] **Bite:** map `None` → `" "` (clean) → the "fold-not-run is not clean" test reddens.
      Restore.
- [ ] Commit: `feat(curator): confidence-graded leaderboard flag with four distinct glyphs`

---

### Task WP5.4: Width re-pins (widget-level)

**Steps:**

- [ ] Re-measure the widget-level width tiers for `CuratorWalletStanding` (the two new lines add
      rows, possibly a wider value) and `CuratorLeaderboard` (the flag column now carries a glyph
      that never sheds). Pin the new `*_FULL_WIDTH` constants the widgets publish, so WP4's
      screen sweep imports them rather than re-typing a number.
- [ ] Failing tests: the standing panel's new lines shed their **value tails**, never their
      labels (the wallet-panel contract); the leaderboard flag column is present at the narrowest
      tier.
- [ ] Commit: `feat(curator): re-pin the wallet-standing and leaderboard widget widths`

---

### Task WP5.5: Full-widget + suite green, and the WP4 hand-off

**Steps:**

- [ ] Run `tests/widgets/test_curator_widgets.py` and the full suite. The widget totality test
      WP0 may have reddened is green once these widgets accept the new kwargs; nothing else moved.
      (The **screen** totality test stays red until WP4 wires the dispatch — that is WP4's, not
      this WP's, and is expected.)
- [ ] Write the **WP4 hand-off note** — the one artifact WP4 depends on:
      1. `CuratorWalletStanding`'s **exact new `update_data` kwarg tuple** (the existing keys
         plus `you_linked_state`, `you_linked_reasons`, `you_linked_group_size`, `you_clean_rank`)
         — so WP4 extends `WIDGET_SIGNATURES` verbatim;
      2. that `CuratorLeaderboard`'s signature is **unchanged** (`link_conf` is a row sub-key, not
         a top-level kwarg) — so WP4 changes nothing for it;
      3. the published width constants WP4's sweep imports;
      4. every new unavailable-state string WP4's phase tests will assert against.
- [ ] Commit: `test(curator): WP5 sign-off and the WP4 wiring hand-off`

**Done when:** the `y` view carries an honest `linked` and clean-rank line (unknown before the
analysis runs, never a confident negative), the leaderboard flag is confidence-graded with four
distinct glyphs and a column that never sheds, the widths are re-pinned, and WP4 has the exact
kwarg tuples to wire.
