# CLAUDE.md

MaxPane: keyless, read-only terminal dashboards for onchain games, NFTs and trading — a Textual
TUI in `maxpane_dashboard/`, published to PyPI as `maxpane`, Python ≥ 3.11. Research, PRDs, plans
and follow-up lists live in `docs/`; withdrawn statements in `docs/decisions.md`; the open
maintenance backlog in `HANDOVER.md`. Per-area detail is in `.claude/rules/*.md` — `data.md`,
`widgets.md`, `dashboard-registry.md`, `curator.md`, `surf.md` — and loads when you read files
they match; layout rules are the `terminal-layout` skill.

<!-- Rewritten 2026-09-18 from 896 lines (git history). Keep under 200 lines: rules and pointers only; per-area detail goes into .claude/rules/. -->

## Hard constraints — read before writing any code

1. **Strictly read-only.** MaxPane never signs, never sends a transaction, never constructs
   state-changing calldata, and never prompts for a private key or keystore password. No signer,
   transactor, nonce manager or keystore exists in this repo and none may be added. If a task
   seems to need one, the task is wrong.
2. **Keyless.** Every data source works with **no API key of any kind** (no Alchemy, Infura,
   keyed Etherscan, OpenSea key, Moralis, NFTPort). A metric with no keyless source is dropped and
   the UI says so — never faked, never silently blank.
3. **No test touches the network.** Inject a transport that raises on use; every external payload
   is a committed fixture under `tests/fixtures/`. No test reaches the real clipboard.
4. **Read values live; never hardcode a documented one.** Docs drift, chains do not.

## Task triage — classify before the first tool call

Say the tier and the one-line reason, then follow only that tier's pipeline. When in doubt pick
the LOWER tier; the ratchet is one-way — the moment a change touches a trigger below, stop, say
so, upgrade. (The superpowers plugin is disabled for this project; if it is ever re-enabled, this
rule overrides its "take the heavier path" and its Bounded path maps to Tier 1.)

- **Tier 0 — hotfix.** ≤ 2 files and ≤ ~30 production lines, or docs-/comment-/test-only.
  Touches none of: a layout pin or its `#:` block, `data/*_models.py` key lists /
  `WIDGET_SIGNATURES`, a shared `widgets/*.py` module, `templates/`, an endpoint pool, a new
  dashboard/body/key. The session implements it itself: no brainstorm doc, dispatch, reviewer,
  ledger or report. One regression test if behaviour changed; mutation proof only where a rule
  already demands it. Run the touched file's tests plus the screen test that composites it (for
  a docs edit: the doc-pinning tests, see Tests); cite the last green suite. Commit. Time box: 30 min.
- **Tier 1 — bounded change.** One dashboard, ≤ 6 files; may move one pin (re-sweep in situ,
  update its `#:` block) or change that dashboard's own data module; no shared widget, no
  `templates/`, no contract key added. Design in chat, owner says yes. One implementer (or the
  session), TDD + mutation proof on the changed behaviour; tests = touched files + composing
  screen test (+ layout test if a pin moved, + address sweep if an address cell changed). ONE
  reviewer pass (mid-tier model, reviewer contract below), at most ONE fix round + scoped
  re-review; residuals go to the followups doc. No ledger or report files — the commit message is
  the evidence. No suite.
- **Tier 2 — architectural.** New dashboard, body, widget or contract key; any change to a shared
  `widgets/*.py`, `templates/`, `data/*_models.py`, an endpoint pool, or > 6 files / > 1
  dashboard. Spec + plan in `docs/`; one implementer per work package; one task review per diff;
  fix rounds capped at 2; final whole-branch review on the most capable model; ONE fix wave; ONE
  scoped re-review; full suite once, by the controller, before merge; followups doc updated; no
  plan workspace left behind.
- **Follow-ups.** A test-quality refinement ("coverage could be broader", derived threshold,
  single payload) is Minor: file it, do it as Tier 0 when its file is next touched, never its own
  branch or dispatch. A follow-ups branch is Tier 0 per item unless the item names a pin, a
  contract key or a shared widget. A perf item enters a branch only with a measured number.

**New dashboard (Tier 2):** research the project into `docs/<game>_game_mechanics.md` (existing
files are the pattern); brainstorm with the owner in chat; write `docs/<game>_PRD.md` on the
template widgets unless told otherwise; on approval the project-planner agent writes the
work-package plan. Packages run one at a time unless they own disjoint files, which the plan lists.

## Architecture

```
maxpane_dashboard/   __main__.py (CLI) · app.py (MaxPaneApp, _GAME_CYCLE) · config.py
  abis/              vendored ABI JSON — never fetched at runtime
  analytics/         PURE functions: signals, EV math. No I/O, no clock, no Textual
  data/              per-dashboard client / cache / manager / models
  screens/           one Screen per dashboard + splash, game_select, wallet_input, refresh_guard,
                     dashboard_screen.py (DashboardScreen: lifecycle + PANELS dispatch)
  templates/         copy-sources for new dashboards; a copy never propagates a fix
  widgets/           shared: panels, sparkline_common, markup_safety, address, status_bar · one pkg per dashboard
maxpane/             Rust intro crate · sybilkit/  SECOND Python distribution, maxpane-independent
tests/               analytics/ data/ screens/ widgets/ address_sweep/ fixtures/ · scripts/ one-shot tooling
```

**Data flow:** `client` (fetch, keyless) → `cache` (tiered TTL, persisted to `~/.maxpane/`) →
`manager` (`fetch_and_compute()` → flat dict) → `screen` (dispatch) → `widgets` (render only:
`str`/`int`/`float`/`bool`/`dict`/`list[dict]`; may import pure `analytics/` helpers, never
`data/`). Dashboards (`--game`): `surf` (default, prefetched), `curator`, `fwa`, `base`,
`frenpet`, `cattown`, `ttt`, `talismans`; hidden but intact: `bakery`, `ocm`, `dota`,
`frenpet_full/_wallet/_perf`. Adding, hiding or reordering one touches six surfaces
(`rules/dashboard-registry.md`).

## Build & run

```bash
python3.11 -m venv .venv && source .venv/bin/activate && pip install -e .
python -m maxpane_dashboard [--game surf --theme fwa]   # splash → game select, or straight in
python -m maxpane_dashboard --version                     # trust this over memory
```

`__version__` is read from installed metadata, written once by the editable install: re-run
`pip install -e .` after a version bump. Keys: README "Keyboard shortcuts" is the owner;
`BINDINGS` in `screens/*.py` are the truth. **Layout is a function of terminal columns and its
rules live in `.claude/skills/terminal-layout/SKILL.md`** — read it before changing anything that
affects how a dashboard is sized. Numbers live only in the `#:` block beside each pin constant;
the app-wide pin is `__main__.FULL_LAYOUT_COLUMNS`. Logs: `~/.maxpane/maxpane.log`; caches:
`~/.maxpane/*.json`. **Env vars** (all optional, none a key or secret): `MAXPANE_ETH_RPC_URL`,
`MAXPANE_BASE_RPC_URL`, `MAXPANE_WALLET`, `MAXPANE_INDEXER_DB`, `MAXPANE_BASEBOARD_ENV`,
`MAXPANE_FONT_SIZE` (0 = leave the terminal alone).

## Tests

```bash
.venv/bin/python -m pytest tests/analytics/        # pure math, seconds
# Three tiers, each ONE command; single-process times measured 2026-09-19 on this machine.
.venv/bin/python -m pytest tests/data tests/analytics tests/test_*.py sybilkit/sybilkit_tests  # fast: ~5,700 tests, ~3 min
.venv/bin/python -m pytest -m 'not screen' sybilkit/sybilkit_tests tests   # + widgets, no composites: ~7,500 tests, ~6 min
.venv/bin/python -m pytest sybilkit/sybilkit_tests tests                   # full: ~8,330 tests (7,885 + 445 sybilkit), ~30 min
HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist loadfile sybilkit/sybilkit_tests tests   # full, parallel: ~12.5 min
cargo test                                          # the Rust crate, from maxpane/
```

Markers (`pyproject.toml`): `screen` = everything under `tests/screens` (836 whole-dashboard
composites, 0.3–1.3 s a case, ~85 % of the serial half hour); `sweep` = the layout-pin certifications
inside it (boundary sets since 2026-09-19, terminal-layout skill); `guard` = a file that reads repo
source or docs rather than exercising code. `-n` is deliberately **not** in `addopts`: some tests
write `~/.maxpane/<game>_cache.json` through an un-mocked manager, so a parallel run isolates `HOME`
as above (serial and `-n 4` passed the identical 8,551-test set on 2026-09-19: 29:46 vs 12:29). Both
distributions collect in one command since `sybilkit/tests` became `sybilkit/sybilkit_tests` — two
packages both named `tests` raised `ImportPathMismatchError`.

**Run the tests that could see the change:** the touched module's test file plus the
screen/manager test that consumes it. The full suite runs once, before merge or push, by the
controller — never by an implementer or reviewer, never after every task; cite the last green run.
A docs-only edit still needs the tests that pin the doc: `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`
and run every file it names. Use `.venv/bin/python -m pytest`: the system `python3` lacks the deps,
and an interpreter without `httpx` *skips* sybilkit's fetcher tests and reports green.

## Conventions — each one is a bug that shipped; the reasoning is in `.claude/rules/`

- **A failed read is `None`, never `0`**; never write a sentinel into a history series.
- **A dead source degrades to an explicit unavailable state** behind an `as of HH:MM` marker —
  never a crash, a blank panel, a stale number presented as live, or a *false* degradation.
  A real negative needs a representable value distinct from "could not look".
- **Escape every third-party string** before markup or a `DataTable`: `markup_safety.safe_markup`.
  Token symbols are attacker-controlled. A `Static` gets a pre-built `rich.text.Text`, never a
  markup string.
- **Every displayed 0x address carries a copy icon and links to its chain's explorer** (click
  the text, or Cmd+click the OSC 8 hyperlink) via `widgets/address.py` and `widgets/explorer.py`
  only; each dashboard package declares its `EXPLORER` once and an unknown chain gets no link,
  never a guessed one. Enforced by `tests/test_address_rule.py` and the E2/E7 sweep
  `tests/screens/test_address_icons_everywhere.py`.
- **ENS** (`data/ens.py`): forward-check every reverse record; record misses; the raw list is
  the sole hydration boundary. **`decimals()` is a live read**, never 18 by assumption.
- **Validate persisted series per point** (`data/series_points.coerce_points`); a hand-edited
  cache file is third-party input. **Inject the clock** (`now=` / `now_ts`).
- **Screens inherit `screens/dashboard_screen.DashboardScreen`** (lifecycle + `PANELS` dispatch;
  `RefreshGuard` underneath); never hand-roll exclusive workers; no network await in a message
  handler.
- **Reuse before you build**: shared module (`widgets/fmt.py`, `rowfit.py`, `markup_safety.py`, `address.py`, …) →
  dashboard sibling / its `_fmt.py` (dashboard-specific formatters only) → template. A helper two modules need is hoisted in the same change, never re-declared. The one
  legitimate copy is a hand-typed literal bound by an agreement test (`_GAME_CYCLE`, `--game`
  choices, `initial_game`, `MANAGER_ATTRS`, a widget restating a `data/` tuple). Sparklines
  import `widgets/sparkline_common`.
- **Classify RPC errors on message text, not code**; state and logs need different endpoint
  pools; a provider's error is evidence only about the request it read — rotate, do not shrink.
- **Tests:** assert against composited output (`render_strips()`), not the content string; prove
  a test bites where the change is decoder- or concurrency-shaped or moves a pin; no wall-clock
  waits in pilot tests — await an observable state.

## Known hazards

- **Dead endpoints, do not reintroduce:** `eth.llamarpc.com`, `rpc.ankr.com/eth` (keyed),
  `cloudflare-eth.com`, `api.reservoir.tools`, `rpc.sepolia.org`, `sepolia.drpc.org` (keyed,
  ban by hostname), `omniatech`, `ethereum.blockpi.network`, `eth.merkle.io`. **Never in a log
  pool:** `rpc.flashbots.net` (silently truncates). `ethereum-rpc.publicnode.com` refuses archive
  `eth_getLogs` on mainnet only. Working pools: `rules/data.md`.
- `templates/` is how bugs propagate: a defect there reaches every dashboard not yet written,
  and a fix there reaches no existing copy. The DOTA API is NXDOMAIN; Bakery's season ended.

## Working with agents

- **Precedence for every seat:** this file's conventions > approved spec > plan/brief >
  implementer report. A finding that contradicts a lower authority is upheld; one that
  contradicts a higher authority is filed as a spec/plan defect, never silently overruled.
- **Freeze the data contract first** (a models module exporting keys and widget signatures).
  **One owner per shared file** (`app.py`, `screens/game_select.py`, `__main__.py`,
  `themes/minimal.tcss`), late in the sequence; seams are for files, not functions — an
  append-only hoist into a shared module needs no owner.
- **Report defects in other agents' files; do not fix them. A review never fixes what it
  finds**; findings are filed and sized by the Follow-ups rule. An owner-driven interactive pass
  that edits code is a fix session, not a review.
- **Verifying is not fixing.** A reviewer *should* mutate the tree to test a claim and restore it
  **by inverse edit only** — `git checkout`, `git stash`, `git reset`, `git restore`, `git clean`,
  `git add` are forbidden in a review — ending with `git status` clean. **The working tree may
  contain uncommitted user work**: never `git checkout --` a file to undo your own edit.
  Subagents never spawn subagents; one reviewer per diff, never two.

## Reviewer contract

Hand this to every reviewer, every tier, verbatim. Never dispatch a persona agent (Reality
Checker, Evidence Collector, `feature-dev:code-reviewer` — it has no shell) as a code reviewer.

1. **Scope:** the diff you were handed plus one focused check per named risk outside it; do not
   crawl the codebase. "Hard constraints" and "Conventions" above are the rules you review against.
2. **Findings** need file:line, what breaks, and how you know. Critical = wrong number on screen,
   crash, any network/key/signing path, a weakened security gate. Important = a convention above
   broken, a missing requirement, a test that cannot fail. Minor = everything else, including
   test-rigor-only findings. No target count: zero findings is a valid report.
3. **Verification is expected:** mutate files in place to test a claim and run the *named* test;
   restore by inverse edit only — `git checkout`, `git stash`, `git reset`, `git restore`,
   `git clean`, `git add` are forbidden — and finish with `git status` clean. Never commit, fix,
   or widen the diff; no directory or suite runs. No shell → say so in line 1 and mark every
   mutation claim unverified.
4. **Mandated redundancy is not duplication:** a hand-typed copy an agreement test binds is
   correct; flag a copy only when no agreement test names it. **Precedence:** CLAUDE.md
   conventions > approved spec > plan/brief > implementer report; a finding that contradicts a
   higher authority is filed as a spec/plan defect, never silently overruled.
5. **Verdict:** `Approved`, or `Needs fixes: <n Critical, n Important>`. A re-review verdicts only
   the findings it was sent (ADDRESSED / NOT ADDRESSED) and files the rest. No subagents, no
   strengths section, no praise.
