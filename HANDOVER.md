# HANDOVER — current session and open maintenance backlog

## Current session handoff — 2026-10-17

Working directory: `/Users/banse/codex/maxpane`; branch:
`feature/surfboard-hub-9`. The approved mandatory data-loading work is complete;
final scoped re-review approved both integration corrections, with no open
Critical or Important findings. Latest production commit: `f40f6df0`. Changes are
local; no push or merge. Specification, package plan, verification and remaining
measurement limits are in
[the execution follow-ups](docs/surf_data_loading_followups.md).

- Markets validate the exact Ethereum reference pool and token orientation.
  DexScreener remains primary with same-pool GeckoTerminal fallback; ETH/USD has
  an independent persisted observation. Full and passive projections share the
  same source-clock rules. Missing market cap stays unknown, never FDV.
- WORK, RECORD, membership, SITES and Scores share the bounded complete job-detail
  memo. Concurrent same-job reads deduplicate; active WORK confirms details after
  discovery. RECORD uses finite 120/600-second revalidation with existing 4/2
  limits, retained last-good facts and original source observations.
- Conditional scheduler changes, shared Gecko pacing/deadlines and earlier RECORD
  staging were deferred at the approved measurement gate. Five concurrent readers
  sharing one fetch is demonstrated; end-user speedup is not. Actual 149×45 live
  previews were shown, but the bounded run did not complete selected-seat RECORD.
- Final composing evidence before the final corrections: 683 passed and eight
  failures reproduced identically on the untouched base `888a1dd4`. Fast guards:
  125 passed. The final corrections have seven new passing regressions, four
  killed mutations, and 408 affected-file passes with only the known BOARD-key
  baseline failure. No full-suite run or all-green-suite claim. The older layout
  residuals below also remain filed.

Use `.venv/bin/python -m maxpane_dashboard --game surfboard` to start locally.
Preserve the October 16 UI state below and all unrelated untracked user files;
this work changes loading/provenance, not dashboard layout or navigation keys.
There is no pending mandatory implementation. Measurement-gated scheduling work
and the Minor logical-detail instrumentation issue remain filed follow-ups.

---

## Historical session handoff — 2026-10-16

**Resume here.** All requested work is complete. The owner explicitly asked to save
the current state for the next session. Working directory:
`/Users/banse/codex/maxpane`; branch: `feature/surfboard-hub-9`.
Latest implementation commit: **`1bbc08a5`** (`fix(surf): reorder agent accepted
effort runtime and owner cards`). Changes are committed locally; no push or merge
was performed. There is no pending implementation request. Wait for the owner's
next direction; the older handoffs and maintenance instructions below are historical.

### Approved AGENT board order

| Row | Column 1 | Column 2 | Column 3 | Column 4 | Column 5 | Column 6 |
| --- | --- | --- | --- | --- | --- | --- |
| Top | SEAT | STATUS | ACCEPTED | REWARDS | RANK | EFFORT |
| Bottom | RUNTIME | OWNER | MODELS | EARNINGS | COLLAB | NODES |

The last four commits only reordered cards and maintained layout checks:
`2e94d368` STATUS/OWNER, `7214092d` RUNTIME/EFFORT, `4a04c82f` STATUS/ACCEPTED,
then `1bbc08a5` ACCEPTED/RUNTIME and EFFORT/OWNER. Preserve the final table above;
do not replay the intermediate orders. Card values, colors, captions and update
behavior were preserved. Two equal rows of six nine-line cards have one blank row
between them. The AGENT full-layout minimum is **134 columns × 29 rows**;
the owner's terminal is **149×45**. STATUS's full activity subtitle or compact
worker counts bind the width. The latest live preview used seat #1581.

### Earlier completed changes to preserve

- `415f36af`: SEAT inner heading `AGENT`, idle subtitle `ONLINE`, footer
  `ERC-8004 #…`; STATUS uses the current job action when known. OWNER, MODELS and
  NODES have no outer footer. One blank line separates RECORD's title and table.
- `80d61ffd`: EARNINGS counts tokens linked to this selected seat's accepted work,
  not the current owner's entire wallet. Missing work coverage remains unknown.
- `4c9ec0b3`: WIP and ORACLES card captions moved from outer footers to the inner
  bottom border, using its color. Their measured minima are 138×30 and 143×42.
- `43ae60f4`: WIP reentry restarts reads that were being cancelled. This is already
  implemented; do not reopen it without evidence of a new problem.
- Earlier BOARDROOM/SURFBOARD layout, palette, source-display and token-dashboard
  changes are already in the current code. The October 10 design below is
  superseded and must not be used to restore old card positions or colors.

### Verification and known residuals

- Latest swaps were shown with fresh public data at 149×45. The capture and stress
  layout measurements still fit from 134 columns. Both swap reversals were caught
  independently by the card-order regression. Scoped review approved without findings.
- Final widget/live integration files: **100 passed**. Fast guards: **125 passed**.
  The broader touched/composing/address run had 617 passes and three failures;
  one obsolete bare-harness width expectation was then corrected and covered by
  the final 100-pass run. No production fix was needed: the real screen at 149 columns
  renders RUNTIME's `update available` caption fully; the bare harness needs 151.
- Two pre-existing failures remain in `tests/screens/test_surf_swarm_layout.py`:
  `test_busy_agent_cards_keep_independent_records_at_the_pin` and
  `test_the_status_bar_edge_is_where_it_was_measured`. They are filed as F-R4/F-R5
  in `docs/surf_agent_record_view_followups.md` and were reproduced against
  pre-swap production code. Do not describe the whole test suite as green.
  F-R2/F-R3 in that document and the Minor caption-test finding in
  `docs/surf_work_followups.md` are separate recorded follow-ups, not pending orders.
- No full suite was run. Use `.venv/bin/python`; unset `NO_COLOR` for color previews
  and isolate HOME for parallel tests. `CLAUDE.md` triage applies; Superpowers is
  disabled. The terminal-layout skill and `scripts/measure_layout.py` own sizing.

### Files and workspace

Card order/rendering: `maxpane_dashboard/widgets/surf/agent_rack_hero.py`.
Screen and AGENT size constants: `maxpane_dashboard/screens/surf.py`.
Tests: `tests/widgets/test_surf_agent_rack_hero.py`,
`tests/screens/test_surf_agent_hero_live.py`, and
`tests/screens/test_surf_swarm_layout.py`. OWNER's compact-address boundary is now
129/130 in its bare-harness test; its copy, explorer link and padding checks remain.
The layout's current `#:` block records the measured evidence.

Tracked implementation files were clean after `1bbc08a5`. Existing untracked
`.codex/`, `.venv311/`, `.worktrees/` and
`docs/codex_swarm_launches_{fix1,fix2,fix3,fix4,v2_fix1,v2_fix2,v2_plan}.md`
are unrelated material: do not delete, revert or stage them. Temporary live-preview
tools and SVG/PNG captures under `/private/tmp/` and `/tmp/` may not survive restart.

---

## Historical session handoff — 2026-10-10 (superseded)

The following describes the October 10 state only; the October 17 handoff above
is authoritative for resuming work.

**Resume here.** The owner ended the session with all requested work completed.
Working directory: `/Users/banse/codex/maxpane`; branch: `feature/surfboard-hub-9`.
Latest implementation commit: `71d011d0` (`fix(surfboard): restore orange borders
and white inner titles`). Changes are committed locally; no push or merge was
performed. There is no pending implementation request: wait for the owner's next
direction. The older maintenance narrative below is historical; do not treat its
"first task" or uncommitted-state claims as current session instructions.

### Approved SURFBOARD hub state

- Top row, left to right: **SURFBOARD, SWARM, LAUNCHES, POOL4, PROTOCOL,
  LEADERBOARD**. Second-row side cards: LAUNCHPAD left, AGENT right. Portfolio,
  earnings and empty bays remain underneath; the central terminal polls every 30s.
- Inner backgrounds are dark, outer populated card backgrounds lighter (original
  scheme). Inner titles are **white like the digits, regular weight**, independent
  of border color. Outer titles stay muted. The final change restored **orange
  inactive borders**; green active states, red offline/error states and the yellow
  ready-to-burn state remain. Do not reapply the reverted gray-border or muted-inner-
  title experiments. Footer colors still follow the card state.
- Native three-line digits retain thousands separators and decimal punctuation.
  SURFBOARD alone uses a three-line latest-post preview, with ellipsis when clipped.

| Outer card | Inner title | Main content | Footer / state behavior |
| --- | --- | --- | --- |
| SURFBOARD | LATEST POST | Latest successful surfsurf.eth announcement | `x new` counts unique replies and owner answers in 24h. Green/fresh text only for a new announcement within 24h; replies alone do not turn it green. Old post text matches empty-slot ink. |
| SWARM | AGENTS | Online agent count | `x working`; green when at least one agent is working. |
| LAUNCHES | TOKENS | Production-chain token catalogue count | `x new`; uses the SWARM header's one-hour detected launch-news window, green while a launch signal is current. |
| POOL4 | IMD PRICE | IMD USD price | `USD`; green for positive 24h price change, orange otherwise. |
| PROTOCOL | IMD BURNED | Cumulative IMD burned | Percentage of global remaining supply, e.g. `0.47%` (no `of supply`). Green for a recent burn signal; yellow when ready to burn. |
| LEADERBOARD | TOP AGENT | Rank-one agent NFT number | `x jobs` using accepted jobs (no `accepted` in the footer). |
| LAUNCHPAD | COINS | Coins launched | `x new` in 24h; green only when new launches exceed zero. |
| AGENT | SEAT | Agent NFT/seat number | `x of y` working slots; green for working slots, orange for idle, red with `offline` footer when offline. |

### Approved SWARM TOKENS dashboard

Real keyless data is connected for all supported production chains, with a chain
filter. Heroes come first, followed by **ACTIVITY / NEWLY LAUNCHED / BEST PLAYS**,
then **ALL TOKENS** below. Standard panels are borderless and filtering follows the
existing native filter editor. There is no extra dashboard heading above the heroes
or selected-token footer. ALL TOKENS has paired liquidity and a widened sparkline,
with no LP STATE column. NEWLY LAUNCHED also shows PAIRED LP instead of LP STATE.
NEWLY LAUNCHED and BEST PLAYS have matching neutral column headings and a blank
line before content. The LIQUIDITY hero sums filtered paired balances separately
as IMD and ETH; incomplete known totals use `≥`, unknown totals use `--`.

Source coverage/history/trades can be partial; never fabricate missing values or
candles. `docs/swarm_tokens_followups.md` records the reviewed limitations and
remaining Minor filter-footer hint refresh issue. The mock demo is retained for
offline design work. No new unresolved findings came from the latest hub changes.

### Where to continue and verification

- Hub rendering: `maxpane_dashboard/widgets/surfboard/rack.py`; terminal renderer
  beside it; composing screen: `maxpane_dashboard/screens/surfboard.py`.
- Hub values: `maxpane_dashboard/data/surfboard.py` and
  `maxpane_dashboard/analytics/surfboard.py`. Token dashboard:
  `maxpane_dashboard/screens/swarm_tokens.py`, `widgets/swarm_tokens/`, and
  `data/swarm_tokens_*.py`. Prior specs/plans and review outcomes are in `docs/`.
- Final color change verified with live keyless render at **149×45**, 49 rack
  tests, 71 composing screen/layout tests, and 123 fast guards, all passing.
  No full-suite run. Use `.venv/bin/python` and unset `NO_COLOR` for color checks;
  isolate HOME for parallel tests. Latest temporary capture tooling/artifacts are
  under `/tmp/hub-card-faces/` and may not survive a restart.
- Follow `CLAUDE.md` triage; Superpowers is disabled here. Small styling hotfixes
  stay in the main session without agent dispatch. Read the terminal-layout skill
  before sizing changes. Show a real live render before layout hardening/review.
- Tracked working tree was clean after the implementation commit. Existing
  untracked `.codex/`, `.venv311/`, `.worktrees/` and
  `docs/codex_swarm_launches_{fix1,fix2,fix3,fix4,v2_fix1,v2_fix2,v2_plan}.md`
  are unrelated material: do not delete, revert or stage them.

---

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
7. **Done, Branch 11 (2026-09-20):** "Reuse before you build" in `rules/widgets.md` is the
   new-dashboard checklist — models keys → `OwnedHttpClient` + bound `rpc_classify` tables +
   endpoint pools → `SeriesCache` subclass → manager with seams → `DashboardScreen` subclass with
   `PANELS` → panel subclasses + `_chain.py` `EXPLORER` → `SweepCase` in
   `tests/address_sweep/builders.py` → six-surface registration. The "~600 lines" was an estimate;
   the checklist states the measured floor instead (dota ~1,550 lines after the programme, ocm
   ~1,830, of which the client, its fixtures and the models are the per-dashboard part).

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
