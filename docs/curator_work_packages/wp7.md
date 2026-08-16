# WP7 — Registration and integration (sole owner of every shared file)

**Goal:** Register THE LIST on all six agreeing surfaces at **menu position 2**, add the
stylesheet block, bring the docs to eight dashboards, and prove the whole thing green, live
and keyless.

**Dependencies:** all. Wave 5, alone.

**Owner note.** This WP is the **sole owner** of:

- `maxpane_dashboard/app.py`
- `maxpane_dashboard/__main__.py`
- `maxpane_dashboard/screens/game_select.py`
- `maxpane_dashboard/themes/minimal.tcss`
- `CLAUDE.md`
- `README.md`

plus its own new file `tests/test_curator_registration.py`. No other work package may open any
of them. **The working tree may contain uncommitted user work — never `git checkout --` a file
to undo your own edit.**

### The order is not optional

**`app.py` → `__main__.py` → `GAMES`.** The registration tests derive their expectations from
`GAMES`, so growing that list first turns `tests/test_cli_game_choices.py`,
`tests/test_app_startup.py`, `tests/test_surf_registration.py` and `tests/test_fwa_theme.py`
red until the wiring catches up. `tests/test_surf_registration.py` is the worked example for
the tests; the order above is the worked example for the edits.

### The six surfaces, and what happens to each

| # | surface | change |
|---|---|---|
| 1 | `app.py` — manager import, `self._curator_manager`, screen import, `_prefetch_manager` map, `_launch_game` branch, install branch, close-on-quit, `_GAME_CYCLE` | insert `"curator"` at index **1** (after `"surf"`), hand-typed literal |
| 2 | `app.py` — `MaxPaneApp.__init__`'s `initial_game="surf"` | **untouched**, but verified. This is the surface the 2026-08-10 reorder missed. |
| 3 | `__main__.py` — `--game` `choices` | insert `"curator"` at index **1**; `default="surf"` **untouched** |
| 4 | `screens/game_select.py` — `GAMES` | insert row 2; renumber 3..8 so keys stay contiguous |
| 5 | `CLAUDE.md` | "The **eight** visible dashboards", the table row, every "seven" reference |
| 6 | `README.md` | table, usage examples, width table |

Plus `themes/minimal.tcss`, which is not one of the six but has the same one-owner rule.

**No theme work.** PRD §10: no new theme in v1, so `--theme` choices are **not** touched. THE
LIST must render correctly under all ten registered themes — WP7.9 checks that.

---

### Task WP7.1: `app.py` — manager, screen, cycle, shutdown

**Steps:**

- [ ] Read the current call sites before editing (line numbers drift; the *blocks* do not):
      `rg -n "surf|fwa" maxpane_dashboard/app.py`. Seven insertion points, all patterned on
      the surf/fwa pairs already there.
- [ ] Edit, in this order inside the file:
      1. `from maxpane_dashboard.data.curator_manager import CuratorManager` in the manager
         import block.
      2. `from maxpane_dashboard.screens.curator import CuratorScreen` in the screen import block.
      3. `self._curator_manager = CuratorManager(poll_interval=poll_interval, wallet=wallet)`
         beside `self._surf_manager`.
      4. The `_prefetch_manager` map: `"curator": self._curator_manager`.
      5. The initial-game chain: `elif self._initial_game == "curator":`.
      6. The install chain: `elif game_id == "curator":` mounting `CuratorScreen(...,
         name="curator")` behind the `is_screen_installed` guard.
      7. `_GAME_CYCLE = ["surf", "curator", "fwa", "base", "frenpet", "cattown", "ttt",
         "talismans"]` — a **hand-typed literal**, per the redundancy-plus-agreement-test
         pattern. Do **not** derive it from `GAMES`: deriving would make
         `test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order` compare a
         constant with itself, and it could never fail again.
      8. The shutdown chain: `await self._curator_manager.close()` in its own try/except.
- [ ] Run the app-level suites — they will be **red** until WP7.3 and WP7.4 land, which is the
      expected intermediate state and why the order is fixed:
      `.venv/bin/python -m pytest tests/test_app_startup.py tests/test_surf_registration.py -q`
      Note which failures you expect (`_GAME_CYCLE` vs `GAMES` mismatch) and confirm you got
      exactly those.
- [ ] Commit: `feat(curator): wire the curator manager and screen into the app`

---

### Task WP7.2: Verify the sixth surface

**Steps:**

- [ ] Confirm `MaxPaneApp.__init__`'s signature default is still `initial_game: str = "surf"`
      and that the comment above it still explains why it is hand-typed. **Change nothing.**
- [ ] Run the pin:
      `.venv/bin/python -m pytest tests/test_app_startup.py -k bare_app_prefetches -v`
      It compares `MaxPaneApp()._initial_game` against `GAMES[0][1]`; both are still `"surf"`,
      so it must stay green through the whole of WP7. If it goes red at any point, an edit
      moved surf out of position 1 — stop and revert that edit, not this test.
- [ ] Record in the commit body that surface 2 was verified and deliberately not edited. The
      2026-08-10 reorder was missed precisely because nobody wrote that down.
- [ ] Commit: `chore(curator): verify the bare-app prefetch default is untouched`

---

### Task WP7.3: `__main__.py` — the `--game` choice

**Steps:**

- [ ] Insert `"curator"` at index 1 of the `--game` `choices` list. **Leave `default="surf"`
      alone** and leave the help text alone (it already says the flag preloads rather than
      selects, which `test_game_help_does_not_promise_to_skip_the_menu` asserts).
- [ ] Do **not** touch `--theme` (no new theme in v1) or `FULL_LAYOUT_COLUMNS` (WP7.7 decides).
- [ ] Run: `.venv/bin/python -m pytest tests/test_cli_game_choices.py -q` — still red on the
      GAMES↔choices comparison until WP7.4. Expected.
- [ ] Commit: `feat(curator): accept --game curator`

---

### Task WP7.4: `GAMES` — the menu row and the renumber

**Steps:**

- [ ] Insert after the surf row and renumber everything below it:

```python
GAMES = [
    ("1", "surf", "Surfboard", "The onchain adventures of surfsurf.eth"),
    ("2", "curator", "THE LIST", "Zero-custody allowlist game w/ an hourly doomsday clock on Ethereum"),
    ("3", "fwa", "Fake World Assets", "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum"),
    ("4", "base", "Base Trading", "Trending tokens, volume, signals on Base"),
    ("5", "frenpet", "FrenPet", "Pet battles, leaderboard, activity on Base"),
    ("6", "cattown", "Cat Town", "Fishing competition, KIBBLE economy on Base"),
    ("7", "ttt", "Ten Thousand Tokens", "NFT collection w/ UniV4 burn-to-launch on Ethereum"),
    ("8", "talismans", "Talismans", "Core-conservation NFT collection on Ethereum"),
]
```

      Leave every commented-out hidden row (`frenpet_full`, `frenpet_wallet`, `frenpet_perf`,
      `dota`, `bakery`, `ocm`) exactly where it is, comments intact — those comments are the
      restore instructions.
- [ ] Check the description's rendered width: the menu row is `[N] Name — description` and a
      long description wraps or clips on a narrow terminal. Measure it against the other seven
      rather than guessing; shorten if it is the longest by more than a few columns.
- [ ] Run the three surfaces' tests together — they should now all agree:

```bash
.venv/bin/python -m pytest tests/test_cli_game_choices.py tests/test_app_startup.py \
  tests/test_surf_registration.py tests/test_fwa_theme.py -q
```

      Specifically confirm: `test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order`,
      `test_the_cli_choices_are_exactly_the_menu`,
      `test_every_game_choice_is_offered_by_the_menu`, `test_reachable_games_still_work`,
      `test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on`,
      `test_the_default_game_is_the_first_menu_entry`, and — the contiguity assertion PRD §9.4
      refers to — `tests/test_fwa_theme.py::…` asserting
      `keys == [str(i) for i in range(1, len(GAMES) + 1)]`.
      `test_claude_md_counts_the_visible_dashboards` will be red until WP7.8: expected.
- [ ] Also confirm `tests/test_surf_registration.py::test_surf_is_menu_entry_one` is still
      green — `SURF_ROW` is pinned verbatim at key `"1"`, and inserting at position 2 must not
      disturb it.
- [ ] Commit: `feat(curator): register THE LIST at menu position 2 and renumber the keys`

---

### Task WP7.5: `themes/minimal.tcss` — the curator block

**Steps:**

- [ ] Append a `/* ── Curator screen ── */` block at EOF, copying
      `CuratorScreen.DEFAULT_CSS` in the style of the surf and FWA blocks. Scope the ids
      (`CuratorScreen #hero-row`, `#middle-row`, `#curator-right-rail`, `#bottom-row`) and
      leave the `Curator*` widget types unscoped — those types exist nowhere else.
      **No vertical padding on `#hero-row` or `#curator-right-rail`.**
- [ ] Do **not** restate `#title-bar` or `#separator`: the shared stylesheet already styles
      those two ids for every screen, and restating them gives a shared rule a second owner
      (the surf block's documented asymmetry).
- [ ] Add to `tests/test_curator_registration.py` (WP7.6) the two-copies-agree test, ported
      from `test_surf_registration.py`: parse both copies' structural properties
      (`width`, `height`, `min-height`, `padding`, `margin`), expand box shorthands, and assert
      the shared selectors carry identical geometry — with the `_DEFAULT_CSS_ONLY` /
      `_BLOCK_ONLY` sets pinned **as sets, not counted**. A count is the vacuity hole: renaming
      a widget in one copy silently drops it from the comparison.
- [ ] Render under every registered theme and confirm nothing clips:
      `for t in matrix minimal bloomberg htop retro bakery frenpet base talismans fwa; do …`
      — or, better, a parametrised headless test over `themes.THEME_NAMES` asserting the seven
      detector rows and the three hero headlines reach the compositor under each.
- [ ] Commit: `style(curator): add the curator block to the shared stylesheet`

---

### Task WP7.6: `tests/test_curator_registration.py`

**Steps:**

- [ ] Write it, mirroring `tests/test_surf_registration.py`, with **every assertion derived
      from `GAMES`** wherever it can be — a later hide, show or reorder must *move* these
      tests, not break them. Cover:
      - every manager attribute exists on a fresh app (add `_curator_manager` to
        `MANAGER_ATTRS`; that list is hardcoded on purpose — the failure it guards is a manager
        that was never built, which a derived list cannot see);
      - `_prefetch_manager("curator") is app._curator_manager`;
      - `q` closes `CuratorManager` exactly once, through the menu quit path;
      - `_launch_game("curator")` reaches a `CuratorScreen`, not the `else: return`;
      - launching twice reuses one installed screen;
      - `"curator"` appears in `_GAME_CYCLE` exactly once and `tab` from the previous entry
        reaches it (the previous entry is read from the cycle, never named);
      - the menu row is pinned **verbatim** as `CURATOR_ROW` — the copy is what must not drift;
      - pressing the key `GAMES` gives it opens `CuratorScreen`;
      - the row reaches the compositor on **one line** carrying both `[2]` and `THE LIST`
        (the loose version searches the whole screen and stays green with the key on another
        dashboard's row);
      - the stylesheet block exists and agrees with `DEFAULT_CSS` (WP7.5);
      - `FULL_LAYOUT_COLUMNS >= CURATOR_FULL_LAYOUT_COLUMNS`;
      - the docs surfaces (WP7.8/7.9) — derived from `GAMES`, so they cover dashboard eight
        without being touched.
- [ ] **Do not duplicate the contiguity assertion**; it lives in `tests/test_fwa_theme.py` and
      already derives from `len(GAMES)`. Reference it in a comment so the next reader finds it.
- [ ] Commit: `test(curator): registration tests derived from GAMES`

---

### Task WP7.7: The full-layout width decision

**Steps:**

- [ ] Read WP6's hand-off number. Three cases:
      - **≤ 143** (the target): change **nothing**. `FULL_LAYOUT_COLUMNS` stays 143, the README
        width table's `≥ 143` stays, and the CLAUDE.md record
        (`198 → 172 → 143 → 176 → 152 → 143`) is **not** appended to — the app-wide number did
        not move. Add one sentence to CLAUDE.md's width section stating curator's measured
        number and that it is under FWA's, the same way surf's is recorded.
      - **exactly 143**: same, plus note that curator is now *level with* FWA, and that which
        dashboard binds is itself a measurement — do not assert one from an older paragraph.
      - **> 143**: go back to WP6 first. Only if a column genuinely cannot be shed do you
        raise the constant, and then all four surfaces move together —
        `__main__.FULL_LAYOUT_COLUMNS`, its `--font-size` help text, the README width table
        (`test_the_readme_quotes_the_documented_width` asserts `≥ N` appears), and the
        CLAUDE.md record, which is **appended to, never rewritten**.
- [ ] Run `.venv/bin/python -m pytest tests/test_cli_font_size.py tests/test_surf_registration.py -q`
      — the surf width tests read `FULL_LAYOUT_COLUMNS` and will notice any move.
- [ ] Commit: `docs(curator): record the measured full-layout width`

---

### Task WP7.8: `CLAUDE.md`

**Steps:**

- [ ] Heading: `## The seven visible dashboards` → `## The eight visible dashboards`
      (`test_claude_md_counts_the_visible_dashboards` derives the word from `len(GAMES)`).
- [ ] Table: insert row 2 and renumber 3..8:
      `| 2 | \`curator\` | Ethereum | THE LIST: zero-custody allowlist game, hourly doomsday clock |`
- [ ] Fix **every** "seven" reference in the prose, not just the heading:
      `rg -n "seven|The seven" CLAUDE.md` and read each hit. The sentence about `surf` being
      position 1 and the `--game` default stays true and stays.
- [ ] Add curator to the registration-surfaces paragraph's worked example list: it currently
      names `tests/test_surf_registration.py`; add `tests/test_curator_registration.py` as the
      second worked example, and note that curator was the **position-2 insert**, which is a
      different shape from surf's append — every key below it shifted.
- [ ] Add the curator paragraph to the width section per WP7.7.
- [ ] Add `~/.maxpane/curator_cache.json` to the caches sentence if that sentence enumerates.
- [ ] Run: `.venv/bin/python -m pytest tests/test_surf_registration.py -k "documented or counts" -q`
- [ ] Commit: `docs(curator): bring CLAUDE.md to eight visible dashboards`

---

### Task WP7.9: `README.md`

**Steps:**

- [ ] Dashboard table: insert THE LIST at position 2, renumber.
- [ ] Usage block: add `maxpane --game curator` — `test_every_visible_dashboard_is_documented`
      asserts the literal `--game curator` appears **and** that the display name `THE LIST`
      appears.
- [ ] Width table: add curator's row if its measured number introduces a new band, and check
      the existing `≥ 143` line still parses — `_readme_width_bands()` in
      `test_surf_registration.py` parses that table with a regex and will fail loudly if its
      shape changes. **Read that parser before editing the table.**
- [ ] Do not touch the surf-specific caveats (`links a transaction`, the seam narrative
      naming 142) — three tests assert those strings are present and one asserts a closed band
      is absent.
- [ ] Run the doc tests. Commit: `docs(curator): add THE LIST to the README`

---

### Task WP7.10: Full-suite green

**Steps:**

- [ ] `.venv/bin/python -m pytest -q` — everything green.
- [ ] `cd maxpane && cargo test` — untouched and green (this WP changed no Rust).
- [ ] Diff review: `git diff main --stat`. Confirm the **only** modified pre-existing files are
      the six this WP owns. Anything else is another WP's stray edit — **report it, do not fix
      it**, and do not revert it (it may be uncommitted user work).
- [ ] Confirm the suite grew by the expected order of magnitude and that no existing test
      changed except the registration tests that derive from `GAMES`:
      `git diff main --stat -- tests/ | grep -v curator`
- [ ] Commit: `chore(curator): full suite green with THE LIST registered`

---

### Task WP7.11: The live smoke run

**Steps:**

- [ ] `pip install -e .` first — `__version__` comes from installed distribution metadata and
      an editable install writes it **once, at install time**. Without this the status bar and
      `--version` report a stale version, and this repo has already shipped three months of
      dev runs showing an April release.
- [ ] `python -m maxpane_dashboard --game curator` on a real terminal at ≥ the measured width.
      Check, against the live chain:
      - the phase word matches reality (grace / judged / settled) and the countdown moves
        between polls;
      - the leaderboard's top row matches a block explorer's reading of the same wallet;
      - `contributors_total` / `deposits_total` match `stats()`;
      - FORCED ETH reads `—`;
      - `c` swaps clusters ⇄ closest calls, and the default matched the phase on open;
      - `m`, `tab`, `r`, `t`, `q` all behave; `tab` visits curator exactly once per lap.
- [ ] **Fresh-install backfill:** `mv ~/.maxpane/curator_cache.json /tmp/` and relaunch. The
      full history backfills from block 25769870 in one sweep, the screen fills, and no key is
      ever requested. Time it and record the number.
- [ ] **Offline launch:** disable networking and launch. Every panel renders an explicit
      unavailable state, the title bar names all three degraded groups, nothing is `0`, and the
      app does not exit. Use this rather than a raising manager as the acceptance criterion —
      it is what an actual offline launch produces.
- [ ] **Keyless proof:** `rg -n "api_key|apikey|x-api-key|Authorization|keystore|private_key"
      maxpane_dashboard/` returns nothing under the curator modules, and the client's banned-host
      frozenset is in force.
- [ ] Record every observation (including the ones that disagreed with expectation) in the
      commit body.
- [ ] Commit: `chore(curator): live smoke run against Ethereum mainnet`

---

### Task WP7.12: The prove-it-bites audit

PRD §8 mandates three mutations. Each was performed inside its owning task; this task is the
independent re-run and the written record, because "it was proven once, somewhere" is exactly
how a mutation proof rots.

**Steps:**

- [ ] **Settlement latch** (WP5.4): make `settlement_record()` re-read the live value instead
      of the persisted record. Run
      `.venv/bin/python -m pytest tests/data/test_curator_cache.py tests/data/test_curator_degradation.py -q`
      → red on `test_a_none_observation_never_clears_a_true_one` **and**
      `test_settlement_survives_a_total_outage`. Restore. `git diff` empty.
- [ ] **Hour-boundary fold** (WP5.3): add a `current_hour_total_wei` parameter to
      `record_hour_buckets` and let it overwrite the last bucket. Run
      `.venv/bin/python -m pytest tests/data/test_curator_cache.py -q` → red on both the
      signature test and the boundary-fixture test. Restore. `git diff` empty.
- [ ] **Curve floor** (WP3.3, three variants): `//` → `round`; `math.isqrt` →
      `int(math.sqrt(...))`; operand order swapped. Each must redden a *different* named test.
      Restore after each. `git diff` empty.
- [ ] Re-run the fourth, the one PRD §8 does not name but the index plan's amendment 3 splits
      out: **the weight floor** (WP3.4), `//` → `round`, → red on `test_the_division_floors`
      and on the 226-row differential. Restore.
- [ ] Add the static guardrails as a permanent test file section (they are cheap and they
      never rot):

```python
def test_no_curator_module_divides_by_credited_delta():           # H3
def test_no_curator_surface_labels_volume_as_tvl_or_capital():    # H4
def test_no_curator_module_contains_a_hardcoded_contract_parameter():  # CLAUDE.md rule 4
def test_no_curator_module_imports_a_signer_or_a_keystore():
def test_no_curator_module_names_a_banned_rpc_host():
```

- [ ] Write the audit record into the commit body: for each mutation, the file, the line, the
      test that reddened, and the confirmation that `git diff` was empty afterwards.
- [ ] Commit: `test(curator): audit the four mandated mutation proofs`

---

### Task WP7.13: Close out the synthetic-fixture ledger

**Steps:**

- [ ] `rg -n "SYNTHETIC — re-point" tests/` and reconcile with WP1's ledger at
      `tests/fixtures/curator/captures/live/README.md`.
- [ ] For each remaining marker, one of exactly two outcomes:
      - a real bundle exists → hand it to WP1.7 (or do the re-point yourself if WP1 has
        finished), run the test **before** editing any expectation, and record any disagreement
        between synthetic and chain as a finding;
      - no bundle and none expected (`HourSaved` that never fired, `Rescued`, the >1000 ETH
        deposit) → mark it **permanent-synthetic** with the reason, in the test and in the
        ledger.
- [ ] Update the index plan's "synthetic until captured" table so its status column matches the
      ledger exactly, and update the "Known gaps carried into implementation" section: if
      WP1.6's curve probe landed, the sqrt curve is now validated **against chain** and the
      gap paragraph must say so instead of "by transcription".
- [ ] Final read-through of `docs/curator_implementation_plan.md`: every claim in it should now
      be either true or struck. A plan that outlives its own accuracy is the artefact
      CLAUDE.md's width section keeps apologising for.
- [ ] Run `.venv/bin/python -m pytest -q` one last time.
- [ ] Commit: `docs(curator): close the synthetic-fixture ledger and reconcile the plan`

**Done when:** all six surfaces agree, the suite and `cargo test` are green, `--game curator`
launches and degrades cleanly offline, the four mutation proofs are recorded, and every
synthetic fixture is either re-pointed or documented as permanent.
