# Decisions and withdrawn statements

Dated one-liners for things `CLAUDE.md` used to say and no longer does, and for choices whose
reasoning would otherwise be re-argued. Newest first. A plan, PRD or work-package file that still
asserts a withdrawn statement is historical — do not review code against it.

- **2026-09-18** — `CLAUDE.md` rewritten to a core file plus path-scoped `.claude/rules/*.md`
  (`data`, `widgets`, `dashboard-registry`, `curator`, `surf`); per-view specs moved out of the
  always-loaded file. The superpowers plugin is disabled for this project
  (`.claude/settings.local.json`); the triage tiers and the reviewer contract in `CLAUDE.md`
  replace its subagent-driven-development loop. `.mind/MEMORY.md` (a 2026-08-20 curator handoff)
  is historical: it names the `f` analysis key, `THE WALLET` / `THE CLEANED LIST` card titles and
  a 13-failure full-suite baseline, all withdrawn below. Withdrawn with the rewrite:
  `hero_metrics`/`leaderboard`/`activity_feed`/`signals_panel` were listed as shared widget modules
  — they are Bakery-only; the shared set is `sparkline_common`, `markup_safety`, `address`,
  `status_bar`. `LEADERBOARD_LIMIT = 100` — it has been `1_000` since `2e5d0cb`. Changed, not
  withdrawn: agents run one work package at a time unless the plan lists disjoint files (was:
  parallel by default); a mutation proof is required for decoder-/concurrency-shaped changes, pin
  moves and Tier 1/2 changed behaviour (was: universal).
- **2026-09-16** — surf's SWARM body bound to `s`; status hint is `l launchpad · 4 pool4 · s swarm`.
- **2026-09-15** — surf's POOL4 protocol body (MODE_POOL4) moved from `p` to `e` (experimental)
  and left off the status bar; `p` is unbound. Older text calling it "the `p` body" means this
  body. Curator's linked-wallet analysis bound to `a` (`action_toggle_analysis` had been
  unreachable since `f` moved to the filter editor on 2026-08-20, `9c5eb2d`); `a` is not in
  `KEY_HINTS` by request.
- **2026-09-14** — POOL4 FLOW removed from surf's `e` body (duplicate of the `4` body's RECENT
  FLOW); `SurfPool4Flow` has one mount. `widgets/status_bar.py` colours are theme variables, not
  CSS colour names (`green` is `#008000`, WCAG-failing); the template copy was not updated.
- **2026-09-12** — Withdrawn: "the staker sweep folds into `p4` only when it has nothing at all
  to serve." It reads its `vault_addr` from `SLOT_POOL4`'s last-good, so it cannot be empty
  unless pool4 is already cold — the clause named eight panels degraded on the evidence of one
  slow tier. It names no group (`test_a_sweep_with_nothing_to_serve_names_no_group_at_all`).
  Withdrawn: `eth.drpc.org` "has a hard 10k-block page cap" — its free-plan limit is archive
  depth (~64 blocks) and it answers any older request with the 10,000-block sentence; it left
  surf's mainnet log pool. The `4` body's panels dropped their `as of` markers (STAKERS keeps a
  conditional `stale` word instead); STAKERS prints whole addresses and the body's pins moved.
- **2026-09-11** — The full suite measured 29:46 (7,580 tests, 3 failed), not the "~11 min" this file
  claimed for four months; the "13-failure baseline" no longer exists (3 failures, filed).
- **2026-09-02** — Withdrawn: "the `bond` tab on imd.fun/pool4 has no contract on either chain."
  Bonding is live inside mainnet's Reward Distributor (40% of the reward share). What stays true:
  no *separate* bond contract is named by anything the dashboard reads, so HATCHES says `unknown`,
  not `absent`. Same day: the argument "the mainnet vault does not exist yet, nothing binds its
  decimals offset to testnet's" was refuted — mainnet's vault also reports `decimals() == 24` —
  and the guard against a `POOL4_VAULT_DECIMALS`-shaped constant stays.
- **2026-09-01** — surf's status hint gained `· p pool4` (removed again 2026-09-15, above); the
  hint is read back off composited output against `StatusBar`'s left-label budget, and `l launchpad` must never shorten
  (the app-level acceptance test greps for it). The persisted-adoption "defence" for pool4 hook
  discovery was deleted, not documented (A27): a hand-edited cache file returned *adopted*
  against a real attempt.
- **2026-08-27** — Curator's cleaned hero card lost the static note `after linked removal`
  (a restatement of the `list CLEANED` label) in favour of the routed ETH the clean wallets
  deposited. Curator's status hint lost the redundant `view: closest` / `view: clusters` tail.
  The `l` hero's cards are THE LIST / YOUR WALLET (or ENS) / THE FILTER; `THE WALLET` and
  `THE CLEANED LIST` are table titles, not hero cards.
- **2026-08-26** — Rule adopted: a review never fixes what it finds (`c6dc14b`).
- **2026-08-24** — Withdrawn: "widgets never import from `data/` or `analytics/`." Measured: 22
  widget modules import `analytics/`, 10 still import `data/` (legacy debt). The rule is purity,
  proven by `tests/widgets/test_surf_widget_contract.py`, not a banned name. Plan and
  work-package files that still quote the old sentence (`docs/curator_implementation_plan.md`,
  `docs/surf_implementation_plan.md`, `docs/curator_work_packages/wp4.md`, others) are historical.
- **2026-08-10** — Withdrawn: "hiding a dashboard touches five surfaces." It is six; the sixth
  (`MaxPaneApp.__init__`'s `initial_game=`) was missed by that day's reorder because the list said
  five. Pinned by `tests/test_app_startup.py::test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on`.
- **Before 2026-08** — An earlier `CLAUDE.md` described MaxPane as a transaction-signing bot for
  RugPull Bakery with a `MAXPANE_KEYSTORE_PASSWORD` env var and an executor/transactor/nonce
  manager. None of that ever existed here; it was inherited from a different project. Any
  instruction pointing at key handling in this repo is wrong.
- **Standing** — `__version__` comes from installed distribution metadata; an editable install
  writes it once, so re-run `pip install -e .` after a version bump. This venv reported `0.3.2`
  for three months and four releases before that was understood.
