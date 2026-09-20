# HANDOVER — open maintenance backlog (written 2026-09-18)

For a fresh Claude Code session started inside this directory. Read `CLAUDE.md` first; it is
now under 200 lines and the per-area detail loads from `.claude/rules/*.md` when you read
matching files. The audit that produced this list is at
`/Library/Vibes/intern/reports/2026-09-18-autopull-audit.md` (evidence, numbers, file:line).

**Already done on 2026-09-18, do not redo:** superpowers plugin disabled for this project
(`.claude/settings.local.json`); `CLAUDE.md` rewritten (old file: `git show 58175bc:CLAUDE.md`)
with per-view specs moved to `.claude/rules/{data,widgets,dashboard-registry,curator,surf}.md`
and withdrawn statements to `docs/decisions.md`; the four doc-pinning tests retargeted
(`tests/test_surf_registration.py`: `_SEAM_NARRATIVE_SURFACES`,
`test_claude_md_counts_the_visible_dashboards`; `tests/test_curator_registration.py`:
`test_claude_md_documents_the_curator_dashboard`, `test_the_docs_record_the_measured_curator_width`);
`autoCompactWindow` set to 300000; `permissions.allow` rewritten from 237 to 52 exact forms
(backups `settings.local.json.bak`, `.bak2`); `!.claude/rules/` added to `.gitignore`; one stale
key in `.claude/skills/terminal-layout/SKILL.md` fixed (`y`/`f` → `y`/`a`). **None of this is
committed.** First task (Tier 0): run `tests/test_surf_registration.py` and
`tests/test_curator_registration.py`, then commit `CLAUDE.md`, `.gitignore`, `.claude/rules/`,
`.claude/skills/terminal-layout/SKILL.md`, `docs/decisions.md`, `HANDOVER.md` and the two test
files. Leave out the pre-existing untracked drafts (7 `docs/netnet_*` / `docs/standardreserve_*`
files, `tests/fixtures/surf/pool4/oracle_25955365.json`) — not part of this work.

Deviations from the audit report, deliberate: `.superpowers/` is archived, not deleted; the
MEDI-38 hardening is its own Tier 1 item (§3.0) rather than folded into the panel refactor; only
the two "~11 min" plan files get a Historical header — other `docs/superpowers/plans/*.md` were
not audited.

Every item below names its triage tier from `CLAUDE.md`. Do them in order; each is its own
commit or branch. Never run the full suite inside an item — run the named files.

---

## 1. Repository hygiene (Tier 0 — mostly untracked state)

1. **Stale worktrees.** `git worktree list` shows nine under `.claude/worktrees/agent-*`, all at
   `6f04827` (commit dated 2026-03-27; worktrees created 2026-03-28..31), plus an orphan dir
   `agent-a660305a` that holds only empty nested `.claude/worktrees/` dirs, and a `.DS_Store`.
   Two checks per worktree, both required: (a) `git log main..worktree-agent-<id> --oneline` is
   empty (verified 2026-09-18 for all nine; all are in `git branch --merged main`); (b)
   `git -C .claude/worktrees/agent-<id> status --porcelain` — every worktree shows a staged edit
   to `.planning/base-terminal-plan.md` and untracked March-2026 drafts under the old
   `dashboard/` package name (e.g. `dashboard/analytics/cattown_conditions.py`,
   `dashboard/widgets/dota/`, `dashboard/abis/`). For each untracked file confirm its
   `maxpane_dashboard/` counterpart on main exists and is the evolved version (`diff`); main's
   `maxpane_dashboard/analytics/cattown_conditions.py` and its test are already longer than the
   worktree drafts. Only then `git worktree remove --force .claude/worktrees/agent-<id>`
   (plain `remove` refuses because of the staged edit). Then `git worktree prune`,
   `git branch -D worktree-agent-<id>` ×9, `rm -r .claude/worktrees/agent-a660305a
   .claude/worktrees/.DS_Store`. Expect ~11 MB freed. Never `--force` before check (b).
2. **Finished plan workspaces.** `.superpowers/` holds `sdd/` (9 plan dirs, 453 files, 14 MB)
   and `brainstorm/` (16 files). Only `sdd/cr_01_plan/progress.md` closes with "Plan status:
   complete"; `sdd/2026-08-21-curator-cr-01/` has no ledger and four ledgers stop mid-narrative
   — but every commit they cite is on main (`git merge-base --is-ancestor <hash> main`) and
   every `feature/*` branch is merged. Move all of `.superpowers/` to
   `~/Archive/autopull-superpowers-2026-09-18/` (outside the repo) rather than deleting; the
   `deferred*.md` / `carried-findings.md` files inside are the only record of deferred Minor
   rulings. Two files are tracked despite `.gitignore` (`git ls-files .superpowers` →
   `sdd/curator_sybil_implementation_plan/wp3-report.md`, `wp6-report.md`): `git rm --cached`
   them in the same commit. Also archive `.planning/` (19 files, 2026-03-27) and
   `.mind/MEMORY.md` (2026-08-20 handoff, superseded — see `docs/decisions.md`), and move the 14
   root `Greenshot *.png` into `docs/screenshots/` (gitignored; tidiness for `ls`).
3. **Untracked capture polls.** `git status` lists exactly 300 untracked 4-second polls under
   `tests/fixtures/curator/captures/live/` (22.7 KB of noise per call). They are protected
   evidence: add their glob to `.git/info/exclude` (the local mechanism already used for
   `.mind/` on line 18 and `**/.claude/worktrees/` on line 11), never to `.gitignore`, and never
   delete them. After that, `git clean -X` / `-x` would remove them as ignored files — never run
   those here. Verify with `git status --porcelain | wc -l`.
4. **Doc drift (Tier 0 docs fixes, one commit).** README:168 and README:517 state the swarm pin
   as 93×42; the code pin is 116×28 (`screens/surf.py:1973`, `:2113`) — replace both with the
   constant names (README should not carry numbers; the `#:` blocks do). README:225-226 and
   :406-407 say `c` switches RAW/CLEANED in the `l` view; it cycles raw → cleaned → filtered
   (`screens/curator.py:297`, `:1924`). README:224-225 names the `l` hero's cards THE LIST /
   wallet / THE CLEANED LIST; they are THE LIST / YOUR WALLET (or ENS) / THE FILTER
   (`widgets/curator/list_hero.py`). `docs/address_copy_PRD.md:248` (§7 E2) still lists `p` on
   surf and omits `e` and `s` (`f` on curator is still real — the filter editor); point E2 at the
   `views` tuples in `tests/address_sweep/builders.py:593` and `:614-615`.
   `docs/surf_pool4_implementation_plan.md:789` and
   `docs/superpowers/plans/2026-09-11-surf-pool4-market-view.md:1788` still say the suite takes
   "~11 min"; add a one-line "Historical — see docs/decisions.md" header to each rather than
   editing their bodies. Run `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/` and the
   files it names before committing.

## 2. Test suite: parallelism, tiers, sweeps (Tier 1 — test/config only, one reviewer)

Facts: 8,551 cases in `tests/` (data 3,658, widgets 1,778, screens 1,528, analytics 1,225, root
362) + 445 in `sybilkit/tests`; `tests/screens` is ~85% of the ~30 minutes (≈1,530 whole-screen
compositor cases at 0.3–1.3 s each; 937 of them are integer width/height sweeps); no
`pytest-xdist`, no markers, no durations file, no CI test run.

1. **Parallel runner.** `.venv/bin/pip install pytest-xdist pytest-timeout`. Before enabling,
   confirm no shared on-disk state: `rules/dashboard-registry.md` documents tests that overwrite
   `~/.maxpane/<game>_cache.json` when a manager copy is un-mocked, and the fixtures dir holds
   live captures. Run the suite once with `HOME=$(mktemp -d)` under `-n 4 --dist loadfile` and
   compare pass/fail with the last serial run (`docs/decisions.md`: 29:46 for 7,580 tests,
   3 failed, on 2026-09-11; today's collection is 8,551 — re-measure serially first). Expected
   30 → ~9–11 min. Do not add `-n` to `addopts`; document the command in CLAUDE.md "Tests".
2. **Markers and tiers.** In `pyproject.toml` add `markers = ["screen: composites a whole
   dashboard", "sweep: integer size sweep", "guard: reads repo source or docs"]`; add
   `tests/screens/conftest.py` with `pytest_collection_modifyitems` tagging everything under
   `tests/screens` as `screen` and functions named `*_is_whole_from_*` / `*_at_every_height*` /
   `*clips_without_saying_so*` / `*scrolls_at_or_above_the_pin*` / `*loses_a_row*` as `sweep`.
   Replace the one-line tier note in CLAUDE.md "Tests" with three commands: fast (`tests/data
   tests/analytics tests/test_*.py` + sybilkit, ~2 min), widgets (+ `tests/widgets`, ~6 min),
   full. Fix the two-`tests`-packages collision (`pytest tests sybilkit/tests` raises
   `ImportPathMismatchError`; both have `__init__.py`): either `--import-mode=importlib` in
   `[tool.pytest.ini_options]` or rename `sybilkit/tests` → `sybilkit/sybilkit_tests`; the fast
   tier must be one command.
3. **Collapse the integer sweeps to boundary sets** (the only item here that needs the
   reviewer). Sites: `tests/screens/test_surf_swarm_layout.py:875-878` (`range(60,160)` + three
   `range(101,131)`) and `:1211` (`_HEIGHT_SWEEP` 20..61);
   `tests/screens/test_surf_pool4_market_layout.py:698-700`, `:1014-1015` and `:1287` (height
   sweeps); `tests/screens/test_surf_screen.py:2423`, `:2496`, `:2632`, `:7420`
   (`range(86,153)`), `:7463`, `:7621`, `:8762` (`_ROW_MARKER_SWEEP`);
   `tests/screens/test_ttt_address_icon_layout.py:271` (`range(120,151)`). Replace each range
   with `{min, pin-1, pin, pin+1, each declared tier boundary ±1, each _OWN_WHOLE_FROM threshold
   ±1, max}` (8–12 cases). **Keep every geometry invariant unchanged** — region overflow, hidden
   `DataTable` columns, clipped lines, wrap-shed flags — those are what caught `7df2e8c` and
   `f51a528`, not the enumeration. Prove each collapsed test still bites by re-applying the
   mutation its `#:` block or docstring names. Expect ~800 fewer cases, ~8 min saved. Note in
   the terminal-layout skill that a pin is certified by the boundary set.
4. **Mutation testing instead of the manual ritual (optional).** `pip install mutmut`; for a
   Tier 2 branch run it diff-scoped (`--paths-to-mutate $(git diff --name-only main --
   maxpane_dashboard | tr '\n' ',')`) against the fast tier plus the owning widget file, and
   record surviving mutants in the PR instead of hand-written mutation sections.
5. Update the counts in CLAUDE.md "Tests" from `pytest --collect-only -q | tail -1`.

## 3. Code refactors (in this order — so the next repo-wide rule lands once)

Measured duplication: activity feeds 16 files / 4,121 lines, hero rows 17 / 4,382, signals
17 / 3,902, sparklines 17 / 2,108, leaderboards 12 / 1,748; `_tier_for` ×15, `_fmt_eth` ×12,
`_build_sparkline` ×10, `_SPARK_CHARS` ×13, `as_float` AST-identical ×5; 7 JSON-RPC rotation
loops, 4 `_multicall`, 5 `_ENDPOINT_LIMITATION_PATTERNS` tables plus three range/cap-marker
variants; 9 `save_to_file` / `load_from_file` pairs; 151 `update_data(` dispatch sites across 14
screens. Estimated 7,500–8,500 lines removable. Each Tier 2 step: spec in chat, one implementer
per package, reviewer contract, full suite once before merge.

0. **(Tier 1, do first) Apply the MEDI-38 unavailable state** from
   `templates/hero_metrics_template.py` to `widgets/ocm/ocm_hero_metrics.py` (`:54` renders
   "Loading…" forever when `total_supply <= 0`, collapsing a real 0 into "loading"),
   `ct_hero_metrics.py`, `dota_hero_metrics.py`, and to `ocm_signals.py`, `ct_signals.py`,
   `dota_signals.py`, `tal_signals.py` (0 `unavailable`, 0 `try:` in each). Seven files, no
   shared module; the widgets' own test files plus the composing screen tests.
1. **Delete dead `widgets/base` code** (2,465 of 3,247 lines; near-zero risk). `widgets/base/
   overview.py` is shadowed by the `overview/` package and byte-identical to
   `overview/_legacy_overview.py` (md5 `d765cc8e…`); `overview/bt_leaderboard.py` calls itself a
   dead-code duplicate; 17 top-level widgets exported by `widgets/base/__init__.py:3-19`
   (fee_claims, fee_leaderboard, fee_stats, gecko_pools, graduated, launch_feed, launch_stats,
   pool_info, price_sparklines, token_chart, token_price, token_signals, top_movers, trade_feed,
   trending_table, volume_bars, volume_sparklines, plus the `OverviewPanel` re-export at `:18`)
   have zero references outside `widgets/base` — `screens/base_terminal.py` imports only the six
   `BT*` classes from `overview/`. Delete them, prune `__init__.py`, and clean the tests: drop
   the eight base entries at `tests/test_address_rule.py:237-242,244-245` (keep `:243`
   `bt_overview_leaderboard`; the set-equality assert at `:308` fails on any stale entry);
   delete the tests for removed modules in `tests/widgets/test_base_address_icons.py` (`:163`
   MODULES list, `:197-244` fee_claims, `:270-297` shadowed-overview tests, `:352`
   bt_leaderboard import; keep `:311`/`:332`); re-point `tests/widgets/test_markup_safety.py:282`
   at `bt_overview_leaderboard`; shrink the "older copies" list in `widgets/sparkline_common.py`.
   Tests: `tests/widgets/test_base_*`, `tests/widgets/test_markup_safety.py`,
   `tests/widgets/test_title_blank_row.py`, `tests/screens/test_base_*`,
   `tests/test_address_rule.py`, `tests/test_address_sweep_registry.py`.
2. **Hoist the sanitiser** into `widgets/markup_safety.py`: `TAG_LIKE`, `flatten()`,
   `strip_tags()`, `sanitize_cell(value, width)` (flatten → strip → clip with `cell_len` →
   escape). Four copies: `widgets/surf/launchpad.py:119-170` (its `_clip` at `:142` still uses
   `len()`), `launchpad_activity.py:210-232`, `burnkeepers.py:115-128`, `_pool4.py:215-235`;
   plus fwa's duplicate `_MARKUP` regex at `fwa_settlement_table.py:60` and `fwa_signals.py:71`
   (same pattern as `markup_safety.py:31 _MARKUP_TAG`). There are no talismans/ttt copies;
   base's `_strip_non_ascii` is a different function. Keep the module docstrings' rationale as
   the docstring of `sanitize_cell`.
3. **`widgets/fmt.py` and `widgets/rowfit.py`.** Move `widgets/surf/_rowfit.py` to
   `widgets/rowfit.py` (leave a re-export shim), add `has_marker()`, `title_with_hint()` and a
   `Ladder(...)` helper so `FULL_WIDTH`/`COMPACT_WIDTH`/`WIDEN_HINTS`/`SHORT_HINT` stop being
   re-declared; convert the 15 `_tier_for` sites (`rg -n 'def _tier_for' maxpane_dashboard/widgets`).
   Create `widgets/fmt.py` with `DASH`, `EMDASH`, `as_float`, `fmt_age`, `fmt_countdown`, `hhmm`,
   `mmdd`, `fmt_eth(value, places, unit)`, `fmt_pct`, `fmt_points`; make `curator/_fmt.py` and
   `surf/_fmt.py` thin re-exports plus their dashboard-specific formatters; convert the three
   fwa `_as_float` (`fwa_settlement_table`, `fwa_hero_metrics`, `fwa_odds_board`) and the 12
   `_fmt_eth` definitions.
4. **Subclassable panels replace the copy templates.** `widgets/panels.py`: `PanelBase`
   (title + margin, empty/unavailable/degraded rendering), `RichLogFeed` (the `_seen_keys` /
   clear / rewrite / `scroll_home` contract from `templates/activity_feed_template.py:144-199`
   plus one `format_row(event) -> Text | None` hook), `TableLeaderboard`, `HeroRow`,
   `SignalsPanel`, `SparklinePanel`. Migrate the five small dashboards first — ocm (603 lines),
   cattown (685), dota (588), talismans (911), ttt (1,299) — then the six `BT*` widgets and the
   four Bakery-only top-level widgets (`hero_metrics.py`, `leaderboard.py`, `activity_feed.py`,
   `signals_panel.py`). Then delete `templates/{activity_feed,leaderboard,hero_metrics,signals,
   sparkline,two_column_table,status_bar,screen}_template.py` and update `rules/widgets.md`
   step 3 to point at `panels.py`. Leave surf/curator/fwa panels alone in this step (tiered row
   layouts are a different shape). Keep the per-dashboard composited tests; add one test module
   for `panels.py`.
5. **`screens/dashboard_screen.py`.** `DashboardScreen(RefreshGuard, Screen)` with `GAME_NAME`,
   `REFRESH_WORKER_NAME`, `PANELS: tuple[tuple[type[Widget], Callable[[dict], dict]], ...]`;
   owns `__init__(manager, poll_interval)`, `on_screen_resume`/`on_screen_suspend` (timer +
   `StatusBar` wiring) and the `_do_refresh` dispatch loop with the per-panel `try/except` +
   `logger.warning`. Migrate bakery, base_terminal, cattown, dota, frenpet, frenpet_perf,
   frenpet_wallet, ocm, talismans, ttt (each becomes `compose()` + `PANELS` + `GAME_NAME`);
   fwa, frenpet_full, surf, curator keep custom `_do_refresh` but inherit the lifecycle.
   ~1,100 lines removed. Address-sweep and screen tests are the acceptance suite.
6. **`data/rpc_classify.py` and `data/series_cache.py`.** `SeriesCache` — **done, Branch 9 (2026-09-20):**
   `data/series_cache.py`, subclassed by bakery, cattown, dota, ocm, frenpet and base (talismans/ttt are
   event caches, follow-up #41); `data/manager_base.py` (`_error_count` / `last_success` / `as_of_hhmm` /
   last-good fold) is in no branch (follow-up #44). **RPC — done as option B, Branch 10 (2026-09-20):** the
   error TABLES are hoisted into `data/rpc_classify.py` (two endpoint tables, Ethereum and Base; two range
   families, span and result-count; `MALFORMED_REQUEST_CODES`; predicates that take the table as a
   parameter and `requested_span` wherever the request had one) and bound by ttt, curator, surf, surf_pool4
   and cattown; the nine per-client error POLICIES (`_rpc*` loops, pagers, shrinkers) stay where their
   tests are; `fwa_logs` uses `rpc_common`'s transport atoms; seven managers take `client=` / `cache=` /
   `cache_path=` and three clients read their env var at construction so the data layer works as an
   importable library. The full `RpcPool(state_urls, log_urls, *, http, classify)` with one union
   `ENDPOINT_LIMITATION_PATTERNS` tuple that this item first described was **declined 2026-09-20** (owner):
   the survey found seven fragments whose meaning flips between clients, nine individually tested policies
   and ~1,050 tests in the blast radius, and the "~700 lines" was reachable only by deleting pinned policy.
   Two corrections to the original text: `fwa_logs` has no `_RANGE_CAP_MARKERS` (it inlines the check), and
   there are nine error policies, not five. Kind-classifiers `talismans_client._classify_rpc_error` and
   `fwa_logs._classify_rpc_error` keep their local marker tables (follow-up #65). Endpoint behaviour rules
   in `rules/data.md` are the spec; `tests/fixtures/surf/pool4/rpc_error_states.json`,
   `log_range_messages.json` and `tests/fixtures/fwa/rpc_errors.json` are the classifier's evidence.
7. Afterwards, rewrite "Reuse before you build" in `rules/widgets.md` as the new-dashboard
   checklist: models keys → `OwnedHttpClient` + bound `rpc_classify` tables + endpoint pools →
   `SeriesCache` subclass →
   manager → `DashboardScreen` subclass with `PANELS` → panel subclasses → `SweepCase` in
   `tests/address_sweep/builders.py` → six-surface registration. A new dashboard should be
   ~600 lines of configuration plus hooks instead of ~4,200.

## 4. Outside this repo (for the maintenance workspace, `/Library/Vibes/intern`)

- Scope the user-level `freelance-cockpit` MCP server to its own project
  (`claude mcp remove freelance-cockpit --scope user`, re-add with `--scope local` there).
- Disable `bankr-agent-dev` for this project only if its skills are never used here
  (`enabledPlugins` in `.claude/settings.local.json`, same shape as the superpowers line).
- Consider archiving `~/.claude/agents/testing/testing-reality-checker.md` and
  `testing-evidence-collector.md` (fail-by-default review personas; never dispatch them here).
- `~/.codex/AGENTS.md` (global Codex rules) mandates TDD-first and always-dispatch
  orchestration; either exempt this repo or align it with CLAUDE.md's triage block so a Codex
  session here does not re-introduce the dispatch-everything habit.

## 5. How to verify the 2026-09-18 restructuring itself

- Start a session here and run `/context`: `CLAUDE.md` must be listed under Memory files and
  the five `.claude/rules/*.md` must appear only after you read a matching file (open
  `maxpane_dashboard/screens/surf.py` and check `surf.md` loads).
- `claude plugin list` from this directory shows `superpowers … disabled`; no superpowers
  skills appear in the session's skill list.
- `jq . .claude/settings.local.json` parses; `autoCompactWindow` is `300000`;
  `permissions.allow` has no bare interpreter, shell, `curl`, `sqlite3`, `git push`,
  `git reset` or `git *` entry — the only interpreter-prefixed forms are
  `.venv/bin/python -m pytest`, `.venv/bin/python -m maxpane_dashboard --version` and
  `python3.11 -m venv .venv`.
- `git diff --stat 58175bc -- CLAUDE.md .gitignore .claude/skills tests` and
  `git status --short .claude/rules docs/decisions.md HANDOVER.md` show exactly the files named
  in "Already done" above.
