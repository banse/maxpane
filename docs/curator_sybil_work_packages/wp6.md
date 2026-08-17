# WP6 — Registration, docs, packaging, the second publish job, live smoke

**Goal:** Land the feature: footer/help for `f`, README + CLAUDE.md updates, the finalised
`sybilkit` README, the **separate** publish path for the second distribution (noted, not
auto-wired), the memory update, a full green suite across both distributions, and a keyless live
smoke run.

**Dependencies:** all of WP0–WP5. **Wave 4, alone.**

**Owner note — this WP owns:**

- `README.md`, `CLAUDE.md`, `sybilkit/README.md` (final)
- the second-distribution publish path: **either** a documented manual step **or** a new
  `.github/workflows/publish-sybilkit.yml` gated on a distinct tag pattern (see WP6.5)
- the user-memory update (via the memory mechanism, not a repo file)

It **creates no source** and **modifies no shared code file** — a defect in any WP's file is
**reported**, not fixed. It does **not** touch `app.py`, `__main__.py`, `screens/game_select.py`,
`_GAME_CYCLE` or the `--game`/`--theme` choices: **this is an expansion of an existing dashboard,
not a new one — there is no six-surface renumber** (PRD §2). The `f` binding and footer already
landed in WP4's `screens/curator.py`; WP6 documents it, it does not re-add it.

### Ground rules

- Run `.venv/bin/python -m pytest` (maxpane), `cd sybilkit && python -m pytest` (sybilkit),
  `cd maxpane && cargo test` (the Rust crate, must stay untouched and green).
- **Keyless proof** over both distributions: `rg` finds no key/secret/keystore/private-key and
  the word `sybil` never appears in `analytics/curator_signals.py`.
- **Never `git checkout --`** a file; the tree may hold uncommitted user work. Stage explicit
  paths.
- Commit after each task.

---

### Task WP6.1: `README.md`

**Steps:**

- [ ] Add a short "Sybil / fan-out analysis" subsection to the curator (THE LIST) entry: the `f`
      view (OPERATORS / SEGMENTS / CLEANED LIST), the `y`-view `linked` line, the
      confidence-graded flag, the `e` export writing `~/.maxpane/curator_clean_list.json`. State
      it is **read-only analysis, pattern-language, never an accusation**.
- [ ] Add the `sybilkit` standalone tool: install (`pip install sybilkit` / `[sources]`), the
      CLI (`sybilkit analyze|segments|export-clean-list`), and that it is maxpane-independent.
- [ ] If WP4 raised `CURATOR_FULL_LAYOUT_COLUMNS` above 143 (it should not have), update the
      width table per WP4's hand-off — **read `_readme_width_bands()`'s regex in
      `test_surf_registration.py` before touching that table**. Otherwise leave the width table
      alone.
- [ ] Do **not** add a `--game` entry, a menu row, or renumber anything — no new dashboard.
- [ ] Run the doc tests. Commit: `docs: document the sybil analysis view and the sybilkit tool`

---

### Task WP6.2: `CLAUDE.md`

**Steps:**

- [ ] Add to the curator paragraph (the `## The eight visible dashboards` section's prose, and
      the per-dashboard key notes): the `f` analysis view and its keys (`f` linked, `e` export),
      the detached Tier-B+C sweep (the `_spawn_crosscheck` precedent, the long-TTL
      `TIER_ANALYSIS`/`SLOT_CLUSTERS`), and that `data/curator_clusters.py` is the **only**
      module importing `sybilkit` while `analytics/curator_signals.py` stays exactly as shipped
      (the forbidden-word source scan).
- [ ] Add a short architecture note that `sybilkit/` is a **second in-repo Python distribution**
      (sibling to the `maxpane/` Rust crate), keyless and maxpane-independent, built and
      published separately.
- [ ] Add `~/.maxpane/curator_clean_list.json` (+ `.csv`) to the files-on-disk note.
- [ ] If `CURATOR_FULL_LAYOUT_COLUMNS` did **not** move (the expected case), add one sentence to
      the width section recording the analysis view's measured number and that it is under FWA's
      143 — do **not** append to the `198 → 172 → …` record (that tracks the app-wide number,
      which did not move). If it did move, append per WP4's hand-off and the base-build WP7.7
      rule (all four surfaces together).
- [ ] Commit: `docs: bring CLAUDE.md up to the sybil-analysis expansion`

---

### Task WP6.3: `sybilkit/README.md` (final)

**Steps:**

- [ ] Finalise the standalone README: what it is (a general keyless EVM sybil-cluster toolkit;
      THE LIST is one preset), install matrix, the three-line API example, the CLI, the design
      rules (score clusters not wallets; ≥2 families; min-size ≥5; reasons not verdicts;
      keyless; `None`-is-a-failed-read), the benchmark gate, and a clear "not affiliated with any
      allowlist; read-only analysis" disclaimer.
- [ ] Resolve the `# TODO(WP6)` markers WP0/WP2 left.
- [ ] Commit: `docs(sybilkit): finalise the standalone README`

---

### Task WP6.4: The keyless / no-verdict / single-import audit

**Steps:**

- [ ] `rg -n "api_key|apikey|x-api-key|Authorization|keystore|private_key|MAXPANE_KEYSTORE"
      sybilkit/ maxpane_dashboard/data/curator_clusters.py` returns nothing.
- [ ] `rg -n "sybil|cheat|fraud|attack|abuse|farmer" maxpane_dashboard/analytics/curator_signals.py`
      returns nothing (the source-scan surface stays clean).
- [ ] `rg -n "import sybilkit|from sybilkit" maxpane_dashboard/` returns exactly one file:
      `data/curator_clusters.py`.
- [ ] Re-run WP1/WP2/WP3's mandated prove-it-bites as an independent audit (the base-build WP7.12
      pattern): the cluster combiner's family gate, the funding fold, the three curve-floor
      variants, and the "first paint not blocked" spawn. For each: the file, the line, the test
      that reddened, `git diff` empty afterwards. Record in the commit body.
- [ ] Commit: `test: audit the sybil build's keyless, no-verdict and mutation guarantees`

---

### Task WP6.5: The second publish path (noted, not auto-wired)

**The fact (plan §6 risk 8):** `.github/workflows/publish.yml` triggers on `v*` and runs
`python -m build` at the repo root, which builds **only maxpane** (`pyproject.toml` packages
`maxpane_dashboard`). Publishing `sybilkit` needs its own `python -m build sybilkit/` and upload.

**Steps:**

- [ ] Confirm a maxpane `v*` tag does **not** build or publish `sybilkit` (read the root
      workflow; it does not `cd sybilkit`). Document this in `sybilkit/README.md` and CLAUDE.md.
- [ ] Add the second publish path as a **noted task**, chosen with the user:
      - **Option A (recommended, safest):** a manual release step documented in
        `sybilkit/README.md` — `python -m build sybilkit/ && twine upload sybilkit/dist/*` — so a
        maxpane tag never accidentally ships an unversioned sybilkit.
      - **Option B:** a **separate** `.github/workflows/publish-sybilkit.yml` gated on a distinct
        tag pattern (`sybilkit-v*`), mirroring the root workflow but `cd sybilkit`. If added, it
        must **not** trigger on `v*`.
      Do not wire sybilkit into the maxpane release. Record the choice in the commit body.
- [ ] `python -m build` (root) still builds only maxpane; `python -m build sybilkit/` builds the
      wheel whose core imports with zero third-party packages. Record both.
- [ ] Commit: `build: document (and optionally add) the separate sybilkit publish path`

---

### Task WP6.6: Full-suite green, both distributions and the Rust crate

**Steps:**

- [ ] `.venv/bin/python -m pytest -q` (maxpane) green; the manager, screen and widget totality
      tests WP0 reddened are all green.
- [ ] `cd sybilkit && python -m pytest -q` green, including the benchmark gate.
- [ ] `cd maxpane && cargo test` green and **untouched** (this build changed no Rust).
- [ ] `git diff main --stat`: the only modified pre-existing files are `curator_models.py`
      (WP0), `curator_manager.py`/`curator_cache.py` (WP3), `screens/curator.py`/`minimal.tcss`
      (WP4), `widgets/curator/wallet.py`/`leaderboard.py` (WP5), the test files, README/CLAUDE
      (WP6) — plus the new `sybilkit/`, `data/curator_clusters.py`, the new widgets and fixtures.
      **Anything else is another WP's stray edit — report it, do not fix or revert it** (it may
      be uncommitted user work).
- [ ] Commit: `chore: full suite green across both distributions with the sybil expansion`

---

### Task WP6.7: The live smoke run

**Steps:**

- [ ] `pip install -e .` first — `__version__` comes from installed distribution metadata written
      once at install time; without this the status bar and `--version` report a stale version.
- [ ] `python -m maxpane_dashboard --game curator` on a real terminal at ≥ the measured width.
      Check against the live chain:
      - `f` opens the analysis view with the doomsday clock still on screen; `esc` backs out;
      - OPERATORS shows the linked groups widest-first with pattern-language reasons and a
        verdict-free confidence marker;
      - SEGMENTS shows the largest operators / early cohort / per-hour bands;
      - CLEANED LIST shows total vs clean points and, with `MAXPANE_WALLET` set, your clean rank;
      - `e` writes `~/.maxpane/curator_clean_list.json` (+ `.csv`) and the panel names the path;
      - the `y` view's `linked` line reads `-- unknown` until the background sweep lands, then a
        pattern-language linkage or `not linked`;
      - the leaderboard flag is graded (`⚑`/`◌`/empty/`?`);
      - the analysis panels stamp `as of HH:MM` on their own schedule (long TTL);
      - `m`, `tab`, `r`, `t`, `q`, `c`, `w`, `y` all still behave; `tab` visits curator once/lap.
- [ ] **First-paint check:** the SIGNALS rail (the doomsday clock) fills in under a second; the
      analysis panels fill on the **next** cycle, not the first — the detached sweep must not
      block first paint (the `_spawn_crosscheck` guarantee).
- [ ] **Fresh-install backfill:** `mv ~/.maxpane/curator_cache.json /tmp/` and relaunch; the
      history backfills and the analysis catches up in the background; no key is ever requested.
- [ ] **Offline launch:** disable networking; every panel renders an explicit unavailable state,
      the analysis panels read `analysis unavailable`, nothing is `0`, the app does not exit.
- [ ] **`sybilkit` standalone smoke:** in a scratch venv, `pip install "sybilkit[sources]"` (from
      the built wheel), run `sybilkit analyze --contract 0x… --preset curator --out /tmp/c.json`
      keyless, and confirm the JSON is `reasons`-shaped. Then `pip install sybilkit` (core only)
      and confirm `python -c "from sybilkit import detect"` works with no httpx.
- [ ] Record every observation (including disagreements) in the commit body.
- [ ] Commit: `chore: live smoke run — analysis view and sybilkit CLI, keyless`

---

### Task WP6.8: Memory update and synthetic-fixture close-out

**Steps:**

- [ ] `rg -n "SYNTHETIC — re-point|SYNTHETIC — calibrated" tests/ sybilkit/tests/` and reconcile:
      each remaining marker is either re-pointed at a live analysis bundle (if one was captured)
      or marked **permanent-synthetic** with its reason (the worst-case operator row calibrated
      from `docs/curator_sybil_data/` may stay synthetic — the live population is the calibration
      source, per the CLAUDE.md live-read rule).
- [ ] Update the user memory: a new "Curator Sybil / fan-out analysis" entry (the `f` view, the
      `sybilkit` distribution, the detached B+C sweep, the pattern-language-on-screen /
      sybil-in-the-library split), and bump the milestones entry (a second in-repo distribution;
      the curator dashboard's third view).
- [ ] Final read-through of `docs/curator_sybil_implementation_plan.md`: every risk in §6 is now
      either resolved-and-recorded or struck. If the `flagged_points_share_pct` reuse, the
      `clean_list_export_path` ownership or the degraded-group decision landed differently from
      the recommendation, update the plan's §6 to match what shipped.
- [ ] Commit: `docs: close the sybil-analysis ledger and update memory`

**Done when:** both distributions and `cargo test` are green, `f`/`e`/`y` behave live and degrade
cleanly offline, the analysis is keyless end to end, `sybilkit` installs and runs standalone, the
second publish path is documented (and never fires on a maxpane tag), and the plan's risks are
each resolved on the record.
