# Decisions and withdrawn statements

Dated one-liners for things `CLAUDE.md` used to say and no longer does, and for choices whose
reasoning would otherwise be re-argued. Newest first. A plan, PRD or work-package file that still
asserts a withdrawn statement is historical — do not review code against it.

- **2026-09-24** — AGENT RUNTIME uses npm latest for Claude Code/Codex and the unique fleet
  plurality for daemon equality; yellow `↑` reserves its own cells and the tooltip names the
  basis. Checks are hourly per package, only in AGENT, with no extra workers request.
  WORK takes contributor turns/hours/output tokens; ACCEPTED combines counts and rate and
  leaves freshness to RECORD; RANK persists the change since the last move per seat.
- **2026-09-24** — AGENT's third card row is removed: ROLES, per-node chain counts/short roles,
  OTHERS and contributor BOARD counts leave the screen; RANK and all payload facts remain.
  COLLAB adds two teammates, NODES replaces TEAMMATES, height falls 33 → 25 at unchanged width 139.
  RECORD moves tok before panel and gains click-only all/not-completed filtering plus a 40..400
  view growing by 20; shared filter-before-window selection drives display and enrichment.
- **2026-09-24** — 5A dropped by the owner: the AGENT ORACLE card gets no panel-agreement or
  open/closed request totals line. RECORD's per-row PANEL column (5B) is the only oracle-outcome
  display. Record popups (ANSWER, SUBMISSION) close on Space or Escape, not Enter, and are not
  opened by keyboard (F-A1 deferred).
- **2026-09-23** — Oracle RECORD replaces the displayed role column with panel and output tokens;
  role remains in the data contract. Compact drops tok; tight retains panel. Bool output uses the
  separately served `agreement.answer`, not figure: the raw corpus includes a nonzero figure
  beside false. The earlier proposed figure-to-bool mapping is withdrawn. Model ids shorten by
  exact cleaned patterns in RECORD/FLEET; no lookup table is used.
- **2026-09-23** — Follow-ups F64–F69 closed. CONTRIBUTORS rounds wall-clock hours, `N min`
  under half an hour. A failed RECORD row paints only a read answer red. A node card never reads
  two different counts as one or the wrong way round (`4.6K of 5K`, never `5.5K of 5K`), and `999,600` reads `1M`. SITES' label column went
  29 → 13, so its tiers moved from 116/108/87 to 100/92/72; the SWARM pin (141, bound by CAPABILITY)
  did not move. An all-hidden `/sites` reads `No current site`, not `live`, because the panel never
  claims reachability. `failure` left `swarm_site_rows`; `superseded_by` stays, for the filter.
- **2026-09-23** — SITES' ens column opens the site: `<label>.site.identitymd.eth` links to
  `https://<label>.site.identitymd.eth.limo/` through a new allowlisted `SITES` explorer (kind
  `site`; the value must be one lower-case LDH label under `site.identitymd.eth`, and only that
  label reaches the URL's host). No copy icon: a name is not an address. SITES now leaves out a
  row replaced by a newer build (`superseded_by`/`superseded`) and a row with no ENS name (the
  feed's two queued builds, 88 attempts, "no static export"); the owner chose both over hiding
  the live `work` row. The failure-in-ens and `label → successor` renderings went with them; the
  label column keeps its 29 cells (F67). BOARDS' first key reads `imd agent` (was a typo).
- **2026-09-22** — AGENT/BOARD/SURFBOARD owner batch. The three node cards are fixed slots
  titled ORACLE, REVIEW and BUILD; a zero or unread value shows `-` on every card including
  OTHERS, which sums only node keys outside the three. SEAT no longer prints "saved". RECORD
  drops launch and sub, writes node as a six-cell word (oracle/review/build), paints a failed
  row's answer red, and loses the blank row under its title -- an exception to the repo-wide
  title margin granted for this body only. Its job id links to `explorer.imd.fun/jobs/<id>`
  through the `IMD` explorer, which accepts canonical lowercase UUIDs and nothing else (a job
  id is not an address and carries no copy icon). RECORD's answer clearance goes 204 -> 165;
  AGENT stays 139x33. LEADERBOARD's table gets one blank cell on the left and a one-cell
  scrollbar on the right. CONTRIBUTORS gains a blank row and devices, accepted-of-attempts,
  rejected/pending, turns/hours and input/output tokens, each unknown as a whole line when a
  contributor row does not serve it; BOARD goes 141x27 -> 141x33, so the owner's 31-row
  terminal now shows `‹ taller` there. The SURFBOARD's IMD SUPPLY hero card becomes BOARDS
  (`'a' - imd agent`, `'b' - leaderboard`, `'s' - swarm`, `'4' - pool4`, left-aligned like THE
  LIST's filter card); `imd_supply` is still read but no longer shown anywhere.
- **2026-09-22** — Swarm polish replaces RECORD's repeated objective with the selected seat's
  own first answer sentence, matched by full submission hash inside a known job. Markdown
  link destinations are discarded and absolute local paths reduced before display; rendering
  still sanitizes text. RECORD retains objective in its data contract for other readers and
  distinguishes queued, failed, absent and empty replies. Actual `usage.model`/duration belong
  to that same submission; worker `premiumModel` is separately labelled **advertised** in
  FLEET and is never treated as a probed or actual-run model. Four unique jobs per seat cycle
  progressively enrich the first 40 rows; the extracted cache is capped at 400 points/48 hours.
  Corrected by polish §7: successful terminal reads and real negatives remain frozen while
  retained, but transport/parse failures retry after the normal answer backoff. The previous
  transient-failure freeze was a spec defect, not an owner decision. A bad persisted point
  is dropped alone; safe stored strings are validated without re-deriving their sentence.
  Meaning-bound colour is shared across SWARM/AGENT heroes and BOARD rows: green healthy/
  working/accepted, red offline/paused/rejected, yellow unavailable or existing pending counts.
  Status words remain present, labels are dim, and rates/scores gain bold without thresholds.
  BOARD rows use dim for offline as explicitly specified for that table. LEADERBOARD sorts
  locally with immutable global rank and token cursor identity; header clicks never save a seat.
  The approved SEAT grouping measures 138×37, above the accepted ≈34; it is skipped under the
  per-item rule and filed as F54, preserving the existing SEAT layout and AGENT 138×32. The
  remaining polish proceeds. F51–F53 record the explicitly deferred API opportunities.
  BOARD measures 141×27, AGENT retains 138×32 and SWARM retains 141×42. CAPABILITY's
  optional inference/record columns appear from 166; RECORD's committed first-40 answer
  clearance moves to 204. Mixed SERVICES clipping remains filed as F55, including the
  increased explicit-word width. No claim that all service combinations fit the body pin.
- **2026-09-22** — BOARD's amended fix wave (§9/§11 of its handover) shortens the status
  hint to `l launchpad · 4 pl4 · s swm · a agt · b brd`; the full `l launchpad` wording stays.
  AGENT removes worker metadata and its separate clock from SEAT while retaining worker state
  in STATUS. Pairing time joins identity, queued feedback joins sent/submitted, and contributor
  facts keep two lines at narrow widths, joining one only where every fact and clock fit.
  `/seats` online no longer competes with worker liveness. Measured AGENT returns to 32 rows,
  closing F46; its column pin comes from its body rather than a wider contributor line.
- **2026-09-22** — The owner approved surf's BOARD as the seventh body on `b`
  (`docs/surf_swarm_board_handover.md`), keeping the existing `s` grid rather than adding a
  fourth row to it. BOARD joins `/contributors` lifetime counters per seat with `/workers`
  state, using separate source markers. The capture's 101 contributor device rows aggregate
  to 99 seats; its 91 workers remain distinct from `/health.connectedDaemons` 92. Enter on
  LEADERBOARD validates and saves the selected seat through the same writer as `i`, then opens
  AGENT. The selected marker follows that saved/current AGENT seat, not the table cursor.
  D2's rejection removal is partially withdrawn: `/contributors` serves rejections and AGENT
  shows them in a separately labelled contributors group. The earlier `/seats` “not served”
  premise is historical too: the new seat #420 capture contains `rejected: 2` and `pending: 12`.
  This implementation leaves the `/seats` fold unchanged and does not reconcile its
  204 attempts / 190 accepted with contributors' 207 / 189. REVISIONS remains absent.
  `tokensPerCompletedJob` is displayed only as served, with that label; runtime-dependent token
  accounting makes inferred totals, costs and token-based rankings inappropriate here.
  AGENT's user-facing WIN RATE/won language becomes ACCEPT RATE/accepted; historical contract
  keys `win_rate` and `last_won_ts` retain their names and documented acceptance meaning.
  Its live status and skills/profiles/platform come only from workers. IN FLIGHT remains
  executing-only and appends the dispatch note, falling back to a failure reason.

- **2026-09-22** (late) — owner: surf's AGENT cards move again. RANK goes up to the hero
  (column 5) and COLLAB down to the seat row; TEAMMATES goes up to the seat row (column 6) and
  BOARD down to the node row. The fourth node card becomes **OTHERS**, which always sums every
  node after the third and reads `0 of 0` when there is none (the swarm serves other node keys --
  `manifest`, `deploy_script`, `build_website`, `build_dapp`, `frontend_for_contract` -- that
  seat #420 has not worked). Node cards shorten `implement`/`review` to `impl`/`rev`; ROLES keeps
  the full names. STATUS says `worked MM-DD HH:MM` when the newest attempt (`submittedAt`) is
  newer than the newest accepted work, and an idle worker reads a green `● online`. OWNER shows
  the owner's forward-verified ENS name (keyless, `data/ens.py` over surf's state pool) in place
  of the address. The AGENT title's `Identity.md AGENT #N` is green and the AGENT title prints
  **no degraded list** ("remove the activity warning"): the groups name the other bodies'
  sources and each AGENT card shows its own unavailable state; the LP-owner warning and the row
  hint stay. The `+N more nodes` statements in the entries below are historical.
- **2026-09-22** (evening) — IMD's `/seats/{id}` changed shape: `work[]` now lists **every**
  attempt with a `status` (`accepted`, `pending`, `rejected`, `failed`) and a `submittedAt`;
  `acceptedAt` is null unless accepted. The node cards counted every work entry as a win and
  showed 110 % (`won / reviewed`); they now read `accepted of attempts` per node, which sums to
  the hero's ACCEPTED (capture `tests/fixtures/surf/swarm/v5/seat_420.json`: 193 of 221 on
  `oracle_assess`). Under the old shape per-node attempts were not served: the card shows the
  accepted count and no rate. RECORD dates each row by `submittedAt` (it printed `??-?? ??:??`
  for every unaccepted attempt) and its `state` shows the attempt's own status (`pending` yellow,
  `rejected`/`failed` red) whenever it was not accepted — 20 of the capture's 28 unaccepted
  attempts sit on a `completed` job and read as a green success before (review I1). Owner, same day: node cards are titled ORACLE / REVIEW / BUILD
  (`NODE_TITLES`; an unknown key keeps its own text), and the AGENT body's title bar reads
  `SURFBOARD · Identity.md AGENT #<token>` in place of IMD price and parity. **Not a defect:**
  ACCEPTED (`/seats`: 195 of 223, six `failed`) and BOARD (`/contributors`: 194 of 226, no failed
  bucket, 29 pending) disagree by definition between the two endpoints, and the committed
  captures carry the same offset.
- **2026-09-22** — owner: surf's AGENT body replaces the SEAT panel and the BY NODE table with
  two rows of hero cards (`widgets/surf/swarm_agent_cards.py`, `swarm_node_cards.py`): OWNER / RUNTIME / FEEDBACK /
  SCORE / BOARD / RANK, then ROLES / four node cards / TEAMMATES. Values row 1 already shows
  (attempts, accepted, accept rate, reviewed, pending) are not repeated; with more than four nodes
  the fourth card sums the rest. The SEAT and BY NODE statements in the entry below are
  historical. Pins moved 138×32 → 135×33 (measurements beside the constants).
- **2026-09-22** — owner, same day: the three AGENT card rows share one column grid (column i has
  one `fr` weight in every row), with a blank row between rows; row 2 reads OWNER / RUNTIME / SCORE
  / FEEDBACK / RANK / BOARD so BOARD sits under STATUS. RECORD's floor went 8 → 6 to pay for the
  blank rows. The STATUS title loses `workers as of HH:MM` and BOARD's title loses `as of HH:MM`:
  a last-good workers or contributors read no longer names its own age on those cards (the
  screen title keeps the body clock; ACCEPTED keeps the seats clock). Accepted by the owner as a
  trade against the "stale presented as live" convention, as on the `4` body. STATUS writes `⚙`
  for "working" in its counts rather than widen its column. Pins 135×33 → 139×33.
- **2026-09-22** — surf's AGENT body uses SEAT beside BY NODE over RECORD
  (`docs/surf_agent_seat_details_handover.md`). ROSTER is retired: its recent job counts looked
  contradictory beside the seat's lifetime accepted count, and its window title understated the
  jobs-seen data it folded. FEEDBACK is retired: the captured reviews all carried value `1`, and a
  passed review does not mean the work won the job. The hero replaces SCORE with WIN RATE
  (`accepted / attempts`); the true score remains in SEAT. BY NODE shows wins against reviewed
  work, its available denominator, and TEAMMATES. STATUS's `won` stamp is the newest accepted
  work; the old feedback `sentAt` stamp said when an oracle transaction reached the chain, not
  when the seat worked. RECORD adds a date, launch kind and an unlinked submission-hash prefix.
  `i` selects the saved seat; the most-active default remains. Enter-on-roster selection and the
  cursor path are removed. The prior AGENT layout and key-retirement statements below are
  historical; `swarm_seat_node_rows` is reintroduced with the seat-detail contract. Pin values and
  their measured binding content live only beside the constants in `screens/surf.py`.
- **2026-09-21** — surf's AGENT body reads the seat's lifetime record from `GET api.imd.fun/seats/{tokenId}`
  (spec `docs/surf_agent_seats_spec.md`, D1–D5): hero SEAT · ACCEPTED `12 of 74` · REVIEWED (total over `N pending`) ·
  SCORE · COLLAB · STATUS; VERDICTS became SEAT RECORD (owner address, runtime, by role); RECORD is lifetime `work[]`,
  FEEDBACK lifetime `reviews[]`; ROSTER stays window-scoped and says so in its title. Seat states: `ok`,
  `unknown_seat` (`never paired`, a real negative), `pending` (`Loading…`), `None` (`unavailable`). Withdrawn with
  it: "`/jobs` returns every job" (it is the newest 100; `count` is the page length); change A's `#N not seen` and
  `unseen_token` (a saved seat off the roster is now shown from `/seats`); `MAXPANE_IMD_SEAT` (the seat is saved by
  `i` to `[seat] token_id` in `config.toml`); the VERDICTS panel with its rejection codes, REJECTED and REVISIONS
  (`/seats` serves neither); RECORD's verifier-detail columns (try, rev, verdict, detail); `swarm_seat_node_rows` and
  `block_number` in feedback rows; `pick_seat` (now `choose_seat`). RECORD's objective column clears from 268 (was
  168, the detail column); the AGENT pins held at 134 × 40.
- **2026-09-21** — surf's SWARM body rebuilt (swarm v2, WP7) and the AGENT body bound to `a`; the
  status hint is `l launchpad · 4 pool4 · s swarm · a agent`, and the status bar is asserted whole
  (right label inside the bar, ` poll` composited) from 131 columns — the phrase-only grep it
  replaced could not fail. Withdrawn with it: "THE FIELD beside QUEUE over THROUGHPUT, JUST SHIPPED
  beneath", the hero's "AGENTS / IN FLIGHT / ACCEPTED TODAY", the swarm pin "116 × 28", "reads one
  keyless host" (the client has a two-name pool of one deployment, `SWARM_API_HOSTS`;
  `api.imd.fun` first), the eight v1 keys (`swarm_jobs_in_flight`, `swarm_jobs_blocked`,
  `swarm_queue_depths`, `swarm_field_rows`, `swarm_queue_rows`, `swarm_blocked_rows`,
  `swarm_shipped_rows`, `swarm_score_rows`; `SWARM_KEYS` 32 → 24, `SURF_KEYS` 191 → 183) and the
  2026-09-16 fixtures under `tests/fixtures/surf/swarm/` (the v2 corpus under `v2/` is the only
  one). The score table is gone: THROUGHPUT is a facts panel (`throughput_facts`) and per-agent
  score lives on the AGENT body's VERDICTS; `swarm_throughput` is folded off the live slot because
  its widget shows the live marker.
- **2026-09-21** — swarm v2 layout: `SURF_SWARM_FULL_LAYOUT_COLUMNS` 141 (CAPABILITY binds),
  `_ROWS` 42 with `#surf-swarm-top { min-height: 16 }` — a floor equal to THROUGHPUT's sixteen fixed
  lines, added so the row pin is the body's content (without it a three-way `1fr` split only reached
  sixteen lines at 58 rows); `SURF_AGENT_FULL_LAYOUT_COLUMNS` 134 (ROSTER binds), `_ROWS` 40
  (VERDICTS' thirteen-line floor). The plan's §2 grid (IN FLIGHT | THROUGHPUT over CAPABILITY |
  LAUNCHES) and A1's 2×2 agent grid were not built: 68 + 79 and 59 + 92 tight cells exceed 143.
  IN FLIGHT beside LAUNCHES is a 4fr:5fr row and a named permanent exception (clears at 190 / 205;
  LAUNCHES hides no column from 138); RECORD's detail column is the agent body's (lit to 168 on the
  corpus). LAUNCHES' `parked_reason` clips to its column with a visible `…` rather than wrapping —
  accepted. `SwarmClient` has `follow_redirects=False`: a redirect is a host nobody allowlisted.
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
- **2026-09-26 (pepepane)** — The entries below belong to the `pepepane` fork branch and are
  appended at the end of this file rather than at its top, breaking newest-first once, so that
  `git merge main` from upstream never conflicts here (spec §1 #7; §15 "Shared surfaces" — append-only,
  at the file's end).
- **2026-09-26 — PEPEPANE-CTRL** — MaxPane's read-only charter is relaxed for `pepepane` only: the control
  verbs (restart, drain-restart, stop, start, enable/disable at boot, skills set, kill-orphans, doctor)
  exist as broker verbs behind plan → apply → verify with one audit line per phase; the TUI process
  stays read-only and never gains a write path of its own (spec §11, §16 #1). The charter relaxation
  itself (§16 #1) was approved by the owner on 2026-09-26, the same day the branch and the console
  script were named `pepepane`; the verb list above is the §16 #3 default (and `doctor` the §16 #14
  default), both accepted by the owner on 2026-09-26 together with the other §16 defaults.
- **2026-09-26** — No six-surface registration for PEPEPANE: the lean `pepepane` entrypoint is the product on
  both hosts. `app.py`, `__main__.py`, `screens/game_select.py`, the four `MANAGER_ATTRS` copies and
  `ALL_GAMES` are untouched, so they stay correct by construction (spec §15, §16 #10).
- **2026-09-26** — `subprocess` and `socket` are allowed in `data/seat_tail.py` and
  `data/seat_broker_client.py` only, behind seams with timeouts: every `subprocess.run` passes `timeout=`
  and a list argv, every follower has a documented stop timeout (spec §14 Rules, §15).
- **2026-09-26** — The daemon-log tail is drained on the poll tick inside `SeatManager.fetch_and_compute()`,
  not by a screen timer or a Textual worker, which never starts the tail. Outside `data/seat_manager.py` and its
  tests, `start_tail()` is called only by `seat_cli.py`, and only when not `--once`. Under `--once`,
  the original follower-starting backfill described here is superseded by the 2026-09-27 WP7 correction:
  `SeatManager.backfill()` consumes a bounded source synchronously and never starts a follower, satisfying spec §4.3.
- **2026-09-26** — docker subprocesses on the Mac exist only as one long-lived `docker logs -f --tail 200
  --timestamps` follower and on a 30 s tier with 25 s timeouts on bare docker calls (a wrapped `docker exec` gets
  the host belt of WP6's bullet below) plus a 5-min breaker per verb, overriding
  the blanket ban in the untracked `docs/seat_PRD.md` §3 (spec §4.2, §12.2, §15).
- **2026-09-26** — PEPEPANE's hero row: QUOTA moved to COST, WORK merged into LIVE, GATE and TODAY added — the
  six boxes are `SEAT · LIVE · TODAY · VERDICTS · GATE · UNIT` (spec §8, §15).
- **2026-09-26** — textual pinned to 8.2.8 (with `rich==15.0.0`, `httpx==0.28.1`, `pydantic==2.13.5`) in the
  `seat` optional-dependency group and `deploy/vps/requirements.lock`; `tests/screens/test_surf_swarm_layout.py`
  measured 545/545 on 8.2.8 after the hoist below, and the sweep is re-run on every Textual bump
  (spec §12.1, §15; fill7 §5).
- **2026-09-26** — Seat per-day series live in `seat_ledger.sqlite`'s `days` table (one store for rows and
  rollups); `SeriesCache` is JSON-only and would duplicate the ledger — a recorded exception to
  rules/data.md "Series caches subclass `data/series_cache.SeriesCache`", which stays true for every other
  dashboard (spec §5.6, §15).
- **2026-09-26** — Seat CSS lives only in `SeatScreen.DEFAULT_CSS` (ids `#seat-*`); `SeatApp` loads the shared
  `themes/minimal.tcss` for theme and base-widget rules but nothing seat-specific is appended to that
  sheet — the DEFAULT_CSS/tcss agreement rule assumes one app loading one sheet, which does not describe
  two entrypoints; the agreement test is replaced by `SeatApp.CSS_PATH == app.CSS_PATH` (spec §8, §14, §15).
- **2026-09-26** — Runtime-executing broker children (`imd whoami|status|skills|tools|doctor`,
  `imd skills add|remove`, the session summarisers) run as `systemd-run` transient units
  `imd-dash-<verb>-<seq>` with the worker unit's posture, never inside the broker's cgroup (spec §4.1b, §15).
- **2026-09-26** — `apply` returns when the command exits; verification is the separate `verify` read verb;
  restart success (`shutting down` → `runtimes:` within 30 s → `verified`) and reconnection (`admitted` →
  `connected`) are reported separately, never as one verdict (spec §11, §15).
- **2026-09-26** — No currency anywhere in v1, including Claude Code's list-price estimate: no currency marker in any
  panel, document field, fixture-derived render or code path; `cost-state.totalCostUSD` is never read
  (spec §10, §15, §16 #11).
- **2026-09-26** — Hoist (rules/widgets.md: a helper two packages need is hoisted, never re-declared):
  `widgets/surf/_swarm_table.py` → `widgets/swarm_table.py` (its `DASH` now imported from `widgets/fmt.py`),
  `widgets/surf/_swarm_seat.py` → `widgets/seat_words.py`, and `mmdd_hhmm` / `short_model` from
  `widgets/surf/_fmt.py` into `widgets/fmt.py`; re-export shims stay at all three old paths so no
  `widgets/surf` body or test changed. The three `seat: hoist … (n/3)` commits are the separately
  upstreamable range the spec calls the hoist commit (spec §15 "Hoist commit").
- **2026-09-26 (contract decision)** — The broker runs under `python3 -I`, which keeps the script's own
  directory off `sys.path`; so `imd_dashd/imd_dashd.py`, `gate.py` and `projection.py` begin with
  `import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` and import
  siblings package-qualified (`from imd_dashd import verbs`). The deploy layout is therefore the package
  directory copied verbatim — `BROKER_DIR = /opt/imd-dash/broker/imd_dashd` — and
  `ExecStart=/usr/bin/python3 -I /opt/imd-dash/broker/imd_dashd/imd_dashd.py` supersedes the spec's
  `/opt/imd-dash/broker/imd_dashd.py` spelling (contract §C.11; spec §12.1).
- **2026-09-26 (contract decision)** — Transient children can see the broker scripts:
  `TemporaryFileSystem=/opt:ro` + `BindReadOnlyPaths=/opt/imd-worker` would hide `/opt/imd-dash`, so
  `TRANSIENT_PROPERTIES` adds `-p BindReadOnlyPaths=/opt/imd-dash/broker` (root-owned, read-only,
  MANIFEST-pinned source, no secret); the summarisers stay self-contained regardless so the Mac stdin
  path works (contract §C.11, §C.8; spec §4.1b).
- **2026-09-26 (contract deviation, WP0)** — `tests/fixtures/seat/MANIFEST.json` entries may carry one optional
  key beyond the contract's eight: `allow`, a list drawn from `control_chars` (only for a `synthetic: true`
  fixture — the injection sample `grammar/control_chars.txt`) and `sk` (only for a server-masked fragment
  such as `sk-svcac********`; an unmasked key never passes). Without it the manifest guard would refuse the
  two fixtures spec §14 requires (contract §D).
- **2026-09-27 (Codex build)** — The owner brief replaces the plan's original checkout and
  interpreter setup: build in `/Users/banse/codex/maxpane` from BASE
  `65908e0c0f8e74f5877a39e1619fcbb0dd4cd688`, with the dedicated Python 3.11 venv
  `.venv-pepepane`. The BASE full suite precedes all changes; the two earlier pin-upgrade suite
  runs are replaced by this baseline. The measured hoist neighbourhood is 697 cases and the
  Surf sweep is 545 cases; those counts govern the branch's gates. BASE's two drag-selection
  assertion failures in `tests/test_select_to_copy.py` remain unchanged. Tests unset `NO_COLOR`
  and isolate `HOME`. The owner's latest instruction selects sequential Agency agents without
  Superpowers workflows or worktrees; the branch stays local and checked out when finished.
- **2026-09-27 (execution deviation, WP0)** — The hoists use filesystem moves followed by explicit
  staging because the sandbox permits the approved Git writes but not `git mv`. Editable
  reinstalls use `--no-index --no-deps --no-build-isolation` with the already installed build
  tooling. Surf sweep runs use `-n 4 --dist load` to distribute the one file without changing
  its test scope or assertions; only one pytest invocation runs at a time. The no-currency
  decision above spells out the marker in words to keep shell-symbol prose out of new text.
- **2026-09-27 (owner correction, spec §13)** — The owner confirmed the specific-first redaction
  order: match `sk-ant-` before generic `sk-`, as frozen contract §C.3 and Task 1.2 require.
  Keep the negative lookahead that protects the already redacted `sk-ant-[redacted]` placeholder.
  This corrects the spec's listed generic-first order, which would consume an Anthropic key
  before the specific rule could match. The read-only aidude spec remains unchanged; WP9's
  adapted `docs/pepepane_PRD.md` reflects this correction.


- **2026-09-26 (contract decision, WP2) — a local `task failed:` line appends the pseudo-phase `failed`** to the open ledger
  row and closes it unsubmitted; spec §5.1's `localFailure` row flag is `"failed" in row["phases"]`, so the `tasks` schema
  of contract §C.6 gains no column. The line occurred 0 times in both corpora (13,734 VPS + 15,882 Mac lines), and
  `SeatLedger._load_state` never reopens such a row (spec §5.1; contract §C.6).
- **2026-09-26 (contract decision, WP2) — the seat ledger adds `sessions_skipped_oversize`** to `META_KEYS` (the manager adds
  each summariser call's oversize count there, because the `--since` watermark reports an oversize file once and the COST
  footer needs the total) and three methods beyond contract §C.6: `attach_work_dirs` (spec §5.2 `work-stat` entries set
  `work_dir_abnormal` and the full `node_id`/`job_id` on the row whose accept lies within 300 s of the dir mtime),
  `unattached_sessions` (the doctor/manual/unknown summaries that `seat_cost.summarise(sessions=…)` counts into
  `cost.excluded`, spec §7) and `mark_expired_transcripts` (Claude rows no transcript joined within `cleanupPeriodDays` = 30
  read `tokens_reason = "transcript expired"`, spec §5.4). `today()` reports `p50S`/`longestS`/`verdictLagP50S` in whole
  seconds as spec §7 prints them; `rollup_day`/`days` keep the REAL columns (spec §5.6, §7).


- **2026-09-26 (contract decision, WP4)** — Both session summarisers (`imd_dashd/summarise_codex.py`,
  `summarise_claude.py`) are single self-contained stdlib files fed to `python3 -` on both hosts; they share
  no code, so `iter_bounded_lines` / `iso_ms` exist twice on purpose. Test seams `clock=` and `wall_s=` are
  keyword-only additions to `summarise_file` / `summarise_dir`; `budget_s` defaults to 40 s (Codex, inside
  `RuntimeMaxSec=60`) and 15 s (Claude, inside the in-container `timeout … 20`) (spec §5.4; contract §C.8).
- **2026-09-26 (contract decision, WP4)** — A compressed rollout reports its plain `.jsonl` path and a rollout
  caught mid-compression is reported once: codex renames rollouts to `.jsonl.zst` after 7 days with a fresh
  mtime, and the ledger upserts sessions by path, so a second path would add an attempt's tokens twice
  (spec §5.4; fill8 §4).
- **2026-09-26 (contract decision, WP4)** — Codex turns count `item_completed` items whose type lower-cased
  with `_` removed is `agentmessage` (rollouts say `AgentMessage`, the exec stream `agent_message`); tokens are
  `{0,0,0,0}` for a finished run without a usage report and `None` for a run in flight or cut short by the 5 s
  per-file clock; Codex sessions carry no max-turn figures, Claude sessions no Codex failure flags or quota
  (spec §10; fill3 §2–§3).
- **2026-09-26 (contract decision, WP4)** — `seat_cost.summarise(…, sessions=())` counts doctor / manual /
  unknown summaries into `excluded` (unknown folds into manual); `BUCKET_KEYS` / `QUOTA_KEYS` mirror
  `seat_models` because analytics may not import `data.*`; a day with an unknown figure is omitted from the
  COST series, never drawn as 0 (spec §7, §10).
- **2026-09-26 (contract decision, WP4)** — `TIER_HISTORY` carries 11 rows dated at the six instants of spec
  §10: besides the listed changes it records #7's economy override and wrapper default before 09-22 18:26,
  Claude Code's opus-5/high default before 2.1.280 and the pre-`61d04d62` codex economy constant
  gpt-5.6-terra/low (fill2 §2–§4; memory notes); a seat's own rows beat seat-less rows whatever their date;
  the projection's `inference` block replaces the rows for runs at or after the newest applicable row;
  owner decision §16 #16 confirms the rows (spec §10).
- **2026-09-26 (contract decision, WP4)** — `seat_auth.pause_hint_active` repeats WP7's
  `seat_signals.pausedhint_active` rule (`until` still ahead, hint ≤ 330 s old) because WP4 cannot depend on
  WP7; a lingering `paused until` suffix never degrades auth (header Review Focus 3; fill1 §5).
- **2026-09-26 (contract deviation, WP4)** — Spec §14's "64 MiB+ file stub via a size-only manifest entry" is a
  sparse `truncate()` on `tmp_path` inside the tests (the manifest guard has no size-only entries); the 2 MiB
  oversize line is committed for real. `sessions/rollout_401.jsonl` is a labelled synthetic stand-in in the
  vps §4 reading until the owner-run capture (WP4 Task 4.3 Step 9) replaces it with the real rollout reduced to
  metadata; the tests accept both readings (spec §10, §14).


- **2026-09-27 (execution record, WP4)** — Task 4.3 Step 9 replaced the synthetic 401
  fixture with the captured metadata-only rollout before WP4 completion. Its SHA256 and
  4,148-byte length matched the corpus manifest immediately before copying; fixture bytes
  remain identical. The fixture manifest uses the corpus capture time, 19:32:59Z, correcting
  the reference script's stale 19:31:00Z. The capture records a null final agent message,
  a task-complete error, and null usage. Both defensive failure readings remain supported.
  No live recapture or aidude edit was performed.
- **2026-09-27 (execution departure, WP4)** — Task 4.4 commit 62b31ba followed a failed
  final mutation-restoration check because the inverse edit matched a docstring substring.
  The explicit repair commit 959094d restored the watermark and docstring, with 31 scoped
  tests green before Task 4.5. A later repeat of the watermark mutation failed its named
  regression, and an exact positional inverse restored green. Subsequent commit commands
  are gated on successful verification; history was preserved.
- **2026-09-27 (execution departure, WP4)** — Task 4.5 additionally ran the reference
  plan's existing Homebrew Python 3.14 zstd pytest command with no repository conftest:
  four passed. No dependencies or shared environment were changed. The dedicated Python
  3.11 venv remains authoritative for pytest; later Python 3.14 checks compile source only.
- **2026-09-26 (contract deviation, WP6) — the Mac `seat` projection runs `python3 -`** with `imd_dashd/projection.py`
  piped on stdin, wrapped in the container's `timeout -s TERM -k 5 20`, instead of contract §C.12's `node -e <js>`: the
  container ships `python3` 3.11.2, the session summarisers already travel that way, and one projection script cannot
  drift from a second copy in another language. The whoami match and the canary are unchanged (spec §4.2, §5.2).
- **2026-09-26 (contract deviation, WP6) — `LocalDockerBroker` reuses `imd_dashd`**: `data/seat_broker_client.py` imports
  the gate, the plan store, the verify watch, the drain and the audit from `imd_dashd` behind a guarded import
  (`IMD_DASHD_AVAILABLE`), so both hosts run one implementation of the protocol (rules/widgets.md "hoist, never
  re-declare"). Only the other direction is forbidden: root code imports nothing from `maxpane_dashboard`. The VPS wheel
  never constructs `LocalDockerBroker`; the TUI's enum copies are bound to `imd_dashd/verbs.py` by a test (contract §A.2, §C.12).
- **2026-09-26 (contract deviation, WP6) — every kill goes through the broker's `Runner` seam** as `kill -TERM -- -<pgid>`
  or `kill -TERM <pid>` argv (never `os.kill`), so every process-affecting action passes the one injected seam and the
  timeout guard; the SIGKILL follow-up runs on the serve loop's tick after `KILL_GRACE_S = 10`, not on a timer thread in
  root code (spec §11 kill-orphans row).
- **2026-09-26 (contract deviation, WP6) — the drain-restart loop is polled on the broker's 30 s tick**: each tick reads
  the last minute of journal heartbeats and feeds the drain; fire re-runs the same fresh gate as `apply`. The contract's
  `popen` seam is accepted but unused in v1 — a `journalctl -f` follower would add a second thread to the root process
  for nothing at a 30 s heartbeat cadence (spec §11 drain-restart row).
- **2026-09-26 (contract deviation, WP6) — `FakeBroker` accepts two fixture styles**: a dict carrying `ok` is a whole wire
  response (WP8's CONTROL scripts), and for a read verb any other value is that read's `data` (WP7's dev-mode case files);
  a bare value under a write verb is `bad_response`. Two additive fields follow WP7's reading of the contract: `ping`
  carries `drain` (`None` or the `seat_control_drain` dict) and a partial `DockerUnitReader.read_unit()` carries `reason`
  (contract §C.11, §C.12; spec §14 mutation proof 8).
- **2026-09-26 (contract deviation, WP6) — `LocalDockerBroker` gives each wrapped exec a host-side belt above its in-container limit**
  (`grace + secs + 5`: doctor 135 s, skills-set 40 s, reads 30–35 s) instead of contract §B's 25 s for every docker call,
  so the in-container `timeout` always fires first — killing the `docker exec` client would leave node and the runtime
  running inside the container — and a legitimate 30–90 s doctor smoke run is not cut at 25 s; bare coreutils execs and
  `inspect`/`logs`/`restart`/`stop`/`start` keep 25 s. Its 5-minute breaker is keyed per verb (spec §12.2), so one hung
  `imd status` does not blind the gate's `outbox` read (spec §4.2, §5.3, §11).
- **2026-09-26 (contract deviation, WP6) — read verbs are audited as hourly counts**: `audit.PHASES` gains `"reads"` beside
  contract §C.11's eleven phases, and both brokers write one `reads` line of per-verb counts every
  `READ_COUNT_FLUSH_S = 3600` (the root broker also at exit) — spec §11 "Read verbs (no gating; audited as counts only)";
  never a line per read and never an argument value (spec §13).
- **2026-09-27 (security correction, WP6) — exact process identity authorizes each signal**: the reference
  compared rounded age at TERM and numeric PID/PGID at the delayed KILL. Internal snapshots now bind
  uid, parent, process group, cgroup and exact Linux start ticks. Both phases reread the complete group;
  changed or new members prevent group signals, and individual fallbacks require unchanged identity.
  Worker sub-cgroups are excluded. A complete metadata snapshot also guards the root reader: unreadable
  members cannot silently disappear from a group check, and unavailable verification is false. Fake process
  trees cover identity drift, membership drift, and partial reads. The old exit fixture now removes the fake
  PID directory, as a real exit does, rather than leaving an unreadable stat file. The public row/plan shapes
  remain unchanged. Root focused fix round 2 closed with regression and exact-inverse mutation evidence.
- **2026-09-27 (security correction, WP6) — the Mac kill path uses a complete metadata snapshot**:
  filtered, rounded `ps` output cannot establish exact identity or whole-group membership. The fixed
  `imd_dashd/process_snapshot.py` source travels on stdin to `python3 - --proc-snapshot`, wrapped in
  `timeout -s TERM -k 5 20` with a 30-second host timeout and the existing per-verb breaker. It reads only
  `/proc` stat, status and cgroup metadata for every UID; no command line, environment, credential or task
  body. It checks identity across the read and refuses incomplete or invalid snapshots. Both TERM and KILL
  recheck start ticks, cgroup and membership; uncertain ancestry is refused. Tests inject the Docker runner
  response and use a fake process tree with command files removed. Eleven Mac regressions and the metadata
  reader test passed in focused fix round 1, with three exact-inverse mutations; no live Docker capture ran.
- **2026-09-27 (protocol correction, WP6) — doctor cooldown is checked again at apply** under the write lock
  on both brokers, because two plans created before the first doctor could otherwise bypass the ten-minute
  interval. Refusal still consumes the plan and writes an audit line. A root transient runner `OSError` now
  produces a decided false verification with a sanitized exception class and releases the write lock.
- **2026-09-27 (security correction, WP6) — every audit string is redacted at the write boundary** with the
  existing frozen stdlib redactor before JSON serialization, including arbitrary refused argument names and
  nested fields. Caller allowlists still restrict the schema. Synthetic credential/control-character tests and
  a mutation prove the boundary; visible control glyphs follow the established redactor contract.

- **2026-09-27 (spec correction, WP7)** — `--once` consumes its bounded log backfill synchronously
  through `TailThread.run_once()` without starting a thread, as spec §4.3 requires. A local source wrapper
  enforces the 25-second total and 2-second quiet deadlines, delegates stale Docker backfill handling, and
  closes each source in `finally`. A journald cursor-gap fallback shares the same total deadline. Backfill
  persistence, sticky notes and idempotence remain intact; deterministic idle, continuous, failing, stale
  Docker and journal sources prove the behavior without a live process. This supersedes Task 7.11's
  temporary-thread reference implementation.
- **2026-09-27 (test corrections, WP7)** — The timestamp grammar pin lives in the new signals tests,
  preserving the brief's limit of two edits to the existing model tests. The API-reasons fixture records
  forwarded requests once, preserving exact request counts. The LOG currency guard checks the first,
  nonempty emitted batch because later cycles have already drained it; the prescribed mutation now fails.

- **2026-09-27 (contract refinements, WP7)** — The signals timestamp parser copies WP5's grammar
  verbatim with an equality guard; an empty document has no hero color. WP1's fold-completion and import
  purity tests receive the two approved edits. Gate wording accepts optional drain and in-flight records;
  the manager and signals expose the plan's additive constants, timestamp/build helpers, fixture helpers
  and manager lifecycle/testing seams without changing earlier signatures.
- **2026-09-27 (partial sources and scheduling, WP7)** — Partial unit/host reads land per field with
  `sources.unit.ok = True` and a reason; absent fields remain unknown. WP8 must render that reason even
  when `ok` is true. Paused hints retain `seenUtc` for expiry. Gate, ping and audit reads share the workstat
  tier, with a five-second lifecycle-event bump. A capped API work slice that does not reach yesterday
  leaves divergence unknown. The tasks window retains `backfillDiscardedUtc` for the LEDGER footer.
- **2026-09-27 (fixtures and retained history, WP7)** — The tail-dead and API-down cases inherit the
  healthy case's directories; healthy contains all fourteen broker reads and four API responses. All
  twenty-five new fixture files are explicitly synthetic and registered with byte lengths and digests.
  Unattached sessions contribute to excluded counts, incremental oversize counts persist, transcript
  expiry and work-directory attachment are wired, and sessions/API-work landings roll up the days table.

- **2026-09-27 (contract decision, WP8) — `SeatLog.render_events` appends** the rows whose `seq` it has not seen and
  never `clear()`s on a poll (the batch-per-poll contract of spec §9); the `RichLogFeed` base repaints the whole feed
  whenever anything is new, which on a live log would flicker every 5 s and scroll the reader away. Only a user action
  (`h`) repaints, from the widget's own ring. `SeatLog` restates the grammar's kind words because a widget may not import
  `maxpane_dashboard.data`; `tests/widgets/test_seat_now_log.py::test_seat_log_kind_words_equal_the_grammar_sets` binds
  them (contract §C.15; spec §8 LOG, §14).
- **2026-09-27 (contract deviation, WP8) — the address sweep verifies a seeded job id through its IMD job link**, not
  through a copy icon: PEPEPANE renders no 0x address at all (device key and wallet are truncated to 8 characters at fold time,
  spec §13) and its one link kind is the job link on the LEDGER's node cell, so `tests/screens/test_address_icons_everywhere.py`
  gained a job-seed branch (a seeded value `is_job_id` accepts must be held in the payload and linked on `explorer.imd.fun`
  in some view). Address seeds are unchanged; the other fourteen cases render exactly as before (spec §14 "Widgets/screen").
- **2026-09-27 (contract deviation, WP8) — hero lines are tuples of honest forms**, longest first, and a box paints the
  first that fits its content width; only when the shortest form still does not fit is it clipped with `…` and the box
  raises `‹ widen` in its bottom border. The spec's hero wordings (up to 55 cells) cannot fit six boxes at the
  dashboard width, and `widgets/seat_words._num`'s rule — a shorter honest number, never a cut one — is the repo's
  answer to that. Hero geometry lives in `SeatScreen.DEFAULT_CSS` (the tcss carries no block for it and is not touched);
  CONFIG, COST and MACHINE rows shorten the same way (spec §8 HERO; terminal-layout skill "shorten the value"). The
  hero has no title row (each box's border is region row 0), so `tests/widgets/test_title_blank_row.py` gains six seat
  rows, not the seven contract §A.3 names; the hero's shape is bound by `tests/widgets/test_seat_hero.py`.
- **2026-09-27 (contract deviation, WP8) — LEDGER is the PEPEPANE body's named width exception** (`LEDGER_NEVER_CLEARS_BELOW`,
  measured; the `RECORD_NEVER_CLEARS_BELOW` precedent): its ten-column `full` tier costs 123 cells plus the gutter and
  clears only on a wide terminal, so at the pin it renders `tight` and marks `‹ widen` honestly while the region,
  hidden-column and CSS-clip checks still apply. `seat_cli.py` restates `__main__`'s two argparse validators because
  importing `__main__` imports `app.py` on its second line, which the lean-entrypoint AST guard forbids; behaviour is
  bound by `tests/test_seat_cli.py::test_poll_interval_and_font_size_validators_match_main` (spec §15).

- **2026-09-27 (owner correction, WP8) — pending stays yellow without an invented suffix** when the data supplies
  no authoritative disagreed/awaiting distinction. The owner confirmed this correction to spec §8 on this date;
  the LEDGER never infers that distinction and never paints pending green or running. The actual composited cell
  is tested. WP9's adapted PRD must carry this and the earlier specific-before-generic `sk-ant-` redaction correction.
- **2026-09-27 (spec alignment, WP8) — all seat CSS lives in `SeatScreen.DEFAULT_CSS`**, including hero geometry,
  panel children and CONTROL. This supersedes plan deviation 8's widget-local CSS proposal and follows spec §8/§15
  and the owner brief. Isolated harnesses load this same sheet; the screen's CSS is unscoped so its explicitly
  seat-named selectors also reach pushed modals. `themes/minimal.tcss` is unchanged. Width and height were actually
  measured on healthy and worst payloads; the adjacent pin blocks and terminal-layout skill table own the numbers.
  LOG keeps complete redacted raw lines in horizontal scrollback with a visible scrollbar; a composited regression
  reaches a long line's final text. Both width and height pins have tests that reject too-small and too-large values.
- **2026-09-27 (plan correction, WP8) — CONTROL submissions run in a worker** so a broker apply cannot block Escape.
  An immediate submission guard prevents overlapping writes. A forced local-only plan requires the node8 twice
  (planning and applying) and then an independent typed `local-only` acknowledgement; both values reach the frozen
  broker contract. Focused regressions exposed both reference defects before the correction. The timer already ran
  verification responsively and retains its callback. Unchanged paints are suppressed; modal tests await workers
  and rendered frames with bounded timeouts, not arbitrary wall-clock pauses.
- **2026-09-27 (measurement correction, WP8) — footprint requires a positive sample**. The driver first tries the
  original macOS `footprint` command; after one failed attachment or unusable result it permanently switches to
  read-only `/usr/lib/libproc.dylib` `proc_pid_rusage(pid, RUSAGE_INFO_V4)`. Its 296-byte ctypes structure follows the
  local Apple SDK's `sys/resource.h`; the sample is the greater of current and lifetime peak physical footprint.
  A run with no positive sample exits 1, as does exceeding the unchanged 160 MiB ceiling. Tests fake the fallback
  and no-sample seams and measure the real dedicated `pepepane` launcher with fresh HOME and fixture/offline data.


- **2026-09-26 (WP9)** — `deploy/vps/MANIFEST.sha256` lists repo-relative paths (`imd_dashd/*.py`, every `deploy/vps/*`
  file the installer copies or feeds to pip, the fork wheel under `deploy/vps/wheels/`), so one file verifies the staged
  tree on the VPS before anything is copied and, path-mapped, the installed copies afterwards; wheels are never committed
  (`deploy/vps/.gitignore`), the lock and the MANIFEST are, and `scripts/build_wheels.sh` regenerates both at the commit
  that is deployed (contract §C.18; spec §12.1).
- **2026-09-26 (WP9)** — The fork wheel enters `requirements.lock` as `maxpane==<version> --hash=sha256:…`, so one
  `pip install --no-index --find-links … --only-binary=:all: --require-hashes -r requirements.lock` installs the 20-wheel
  dependency closure and the fork under one hash check; the same hash is in `MANIFEST.sha256` and a guard binds the two (spec §12.1
  install route (a)).
- **2026-09-26 (WP9)** — `install.sh` installs the worker drop-in only with `--worker-dropin` (§16 #4 was approved on 2026-09-26;
  the flag marks the idle moment the owner picks) and never restarts, stops or starts `imd-worker.service` — a guard reads the file for those strings; the
  drop-in takes effect at the next drained restart from CONTROL (spec §12.1 step 7). It gives the root broker its seat
  through a rendered `imd-dashd.service.d/10-seat.conf` (`ExecStart=` reset, then `… imd_dashd.py --seat N`), so the
  MANIFEST-pinned unit keeps the contract's text and the gate's fresh standing read (spec §11 step (b)) has a seat.
- **2026-09-26 (WP9)** — `probe_seat_host.sh` issues `plan restart` and never `apply`; `doctor` is the one write verb it
  applies (one runtime turn, `--skip-doctor` opts out); the §14 drained restart is the owner's, by hand, recorded under
  the probe's last heading (spec §14 "Only on the VPS").
- **2026-09-26 (WP9)** — The no-currency guard over the seat docs
  (`tests/test_seat_deploy_files.py::test_no_dollar_sign_in_docs_seat_files_except_the_no_currency_rule_sentence`) covers
  the six documents written for the fork (`seat_status_schema_v2.md`, `seat_install.md`, `seat_install_probe.md`,
  `seat_followups.md`, `deploy/mac/README.md`, `deploy/vps/VERIFY.md`): prose may carry a currency marker only in the one sentence
  that states the rule, and a currency marker before a digit inside a code block fails. `pepepane_PRD.md` and `pepepane_plan.md`
  are verbatim copies of the spec and the plan, which discuss the rule itself, and are exempt by name (spec §10).
- **2026-09-26 (WP9)** — `docs/seat_PRD.md` and `docs/seat_implementation_plan.md` (untracked on `main`) are committed on
  `pepepane` with the dated overridden banner as line 1 and their bodies unchanged, so the banner guard is
  deterministic on any checkout; `main` never carried them, so `git merge main` cannot conflict on them (spec §15).
- **2026-09-26 (WP9)** — The deploy guard restates `/opt/imd-dash/broker/imd_dashd` and `/usr/bin/python3` as literals
  beside the imported `SOCKET_PATH` / `AUDIT_PATH` / `VERSION` / `CHILD_ENV` / `TRANSIENT_PROPERTIES`, rather than
  importing the broker's `BROKER_DIR`, which resolves to the running package's own directory so the same files import
  under pytest and under `python3 -I` on the VPS; the unit file must name the deployed path, never the checkout's
  (contract §B, §C.11).
- **2026-09-26 (WP9)** — `CHANGELOG.md` gains its `## pepepane (unreleased) — 2026-09-26` section at the end of the file,
  not at the top the contract names: the header rules every shared file append-only at its end, and an upstream
  `## v0.9.4` lands exactly at the top; the section's first sentence says so (spec §1 #7; contract §A.3).


- **2026-09-27 (WP9, build interpreter departure)** — `scripts/build_wheels.sh` honors an explicit interpreter so
  pip download uses this branch's dedicated Python 3.11 venv; the default remains compatible with the reference plan.
  The shell assignment is:
  ```sh
  PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
  ```
  The build produced 20 dependency wheels plus the fork wheel, 21 lock requirements and 21 MANIFEST lines, including
  the added `process_snapshot.py`. The parent performed the sole authorized network build; later manifest/tarball
  regeneration is offline. Wheel files remain ignored. All documented build paths use the Codex clone.
- **2026-09-27 (WP9, probe output correction)** — The reference probe's hex-only scrub could emit journal secret
  fragments, terminal controls and currency markers. Every output code block now passes through the installed broker's
  stdlib redactor, then the same marker suppression used at the manager boundary (bound by an agreement regression),
  retaining the original additional long-hex mask. The root script imports no MaxPane code. Synthetic hostile output
  and currency cases fail before the fix; removal of the redactor fails the named test.
- **2026-09-27 (WP9, probe read deadline correction)** — A fixed 20-second socket deadline was shorter than synchronous
  `status` (30 seconds plus the 15-second subprocess belt). The probe derives a bounded 140-second ceiling from the
  broker's exported maximum runtime and belt plus five seconds. `doctor` apply is asynchronous; its verification is
  polled separately as before. No live probe ran during the build.
- **2026-09-27 (WP9, guard and provenance refinements)** — The installer guard checks the executable hash-required pip
  command, so usage comments cannot mask its removal. The PRD correction guard checks the adaptation header, so the
  historical spec body cannot mask a missing ExecStart correction. SHA256 guards preserve all four copied document
  bodies byte-for-byte; both confirmed owner corrections live only in the PRD header. The lineage docs were copied
  read-only from the two authorized untracked originals. Follow-ups 21–27 transfer the build ledger's remaining owner
  work, BASE failures, unverified review questions and resolved defects after the reference follow-up file was created.
- **2026-09-27 (WP9, measured documentation)** — The install/probe docs distinguish the actual 58.8 MiB lean Mac cold
  peak from the historical 142 MiB full-app peak; the unchanged CI ceiling is 160 MiB. Layout records use WP8's actual
  134-column/50-row body and 210-column LEDGER full tier. VPS measurements are still pending. The changelog reports
  the BASE-measured 545-case Surf sweep, and the adapted plan records 697 hoist tests rather than its historical 672.

- **2026-09-27 (final review R1, transient startup cleanup)** — Both brokers retain apply's cleanup ownership until
  the transient thread has successfully started. Constructor or start failure completes the watch as failed, removes
  the worker entry, clears in-flight state and releases the write lock through the normal error path. No child ran,
  so this failure restores the preceding doctor cooldown rather than charging a new ten-minute interval. Root and Mac
  regressions inject both failures and prove a subsequent legal write succeeds.
- **2026-09-27 (final review R2, bounded socket admission)** — The reference synchronous listener queued concurrent
  applies until the previous write completed. The production listener now admits at most seven connection threads and
  one housekeeping thread, with no task queue. Peer checking and request decoding precede responses; in-flight detail
  captured at accept and checked again before state serialization produces an audited busy refusal during ordinary and
  drain-fired writes. Busy refusals do not consume plans, preserving the existing apply contract. Shared request/tick
  state is serialized independently of admission; audit append and child sequence allocation are synchronized.
  Excess connections close instead of waiting to execute later. Real serve-loop tests hold the command open until both
  concurrent apply and plan refusals arrive, and prove overload is bounded.
- **2026-09-27 (final review R3, summary trust boundaries)** — Both sessions broker return paths and the ledger's
  direct session-ingestion boundary now apply the existing frozen deep redactor to every string, including nested
  mapping keys. The reference implementation sanitized only API-error messages. Actual fixture-derived model metadata,
  nested secret fragments and terminal controls now reach neither socket consumers nor SQLite in raw form; ordinary
  paths, identifiers, joins, numeric token totals and data shapes retain their meanings. The two redactor copies remain
  unchanged and byte-identical.
- **2026-09-27 (final review R4, lifecycle evidence and contract addition; empty-history policy superseded by D1)** — An absent anchored lifecycle record is
  unknown, never terminal. `ERRORS` gains `gate_unknown(lifecycle)` so this required refusal has an explicit wire shape;
  no existing symbol or signature changes. Root queries the latest anchored lifecycle match independently of the
  short heartbeat window, limiting journal output to one matching record with the existing child deadline and no age
  cutoff. Mac uses a bounded 10,000-line older-log read only when its live window lacks lifecycle evidence, and accepts
  it only if its newest daemon timestamp reaches the live window's newest timestamp; stale segments are discarded.
  Missing or truncated history therefore refuses normal restart/stop and re-arms drain. Aged terminal evidence is valid,
  a newer accept supersedes it, and the existing explicit force rules stay separate. The journal test driver now models
  filtering before limiting; no idle evidence is invented. Offline artifacts are rebuilt and rehashed after these fixes.

### 2026-09-27 — PEPEPANE fix 7: stale positive standing

A successful standing read reporting running tasks blocks the gate regardless of age. Only a fresh zero earns `plane+local`; stale positive counts remain visible in `local-only`. This corrects the plan's freshness check without weakening the idle gate.

### 2026-09-27 — PEPEPANE fix 11: executor failures are terminal

The root/Mac lifecycle matcher and TUI terminal-kind set now include local task, question and campaign failures. Research fill1 section 2 and fill6 section 1 establish that executor exceptions emit this final line without a subsequent submission. This corrects the plan's omission.

### 2026-09-27 — PEPEPANE fix 2, owner D1: successful empty history is idle

D1 supersedes the R4 sentences “An absent anchored lifecycle record is unknown, never terminal” and “Missing or truncated history therefore refuses normal restart/stop and re-arms drain.” A successful history read with no lifecycle match now means no open task. Only a failed, timed-out or unreadable read produces `gate_unknown(lifecycle)`. The explicit `lifecycle_read_succeeded` argument to `gate.evaluate` carries that distinction. Root acceptance is corrected by the second-round measured JSON outcome entry below; the no-entries marker is a plain-text form. Mac requires successful live/history reads and retains the stale-segment refusal; an empty older segment cannot corroborate a nonempty live window.

The standing retry remains unchanged: two attempts of up to 8 seconds run inside the root child's 12-second deadline. A slow first attempt can exhaust that outer budget, degrading to `local-only` and requiring its typed acknowledgement. This existing bounded fallback is documented rather than extending the gate deadline.

### 2026-09-27 — PEPEPANE fixes 6 and 12: armed drain and refusal audit

Manual restart/stop plans and applies now refuse an armed drain with `drain_already_armed` and a `cancel-drain` hint, including plans created before the drain. This adds to spec section 11's executing-drain busy rule and prevents a manual action leaving a second restart armed. Malformed apply plan identifiers produce an `unknown_plan` refusal audit without copying the identifier. Verify audit lines remain change-only: polling an unchanged verification state does not repeat the same audit event.

### 2026-09-27 — PEPEPANE fix 1: bounded apply admission

Protocol addition: `apply_late` reports `waited_s` and `plan_spent`. The root broker stamps monotonic time immediately after socket accept, refusing an apply older than 5 seconds before consuming its plan (`plan_spent: false`). It checks the same bound immediately before systemctl, the actual asynchronous transient start, and each initial orphan signal after fresh evidence reads (`plan_spent: true`). Both refusals are audited. A late asynchronous worker completes verification as false with the same error and detail in its reason. The second-round E1 entry below supersedes the original shared 5-second pre-systemctl deadline and its claimed 15-second margin. Broker-owned drain fires have no waiting client and are exempt. Already-started orphan actions retain their specified 10-second SIGKILL completion and identity checks.

Root state locks now protect only short in-memory snapshots/updates. Slow reads have a separate read lock; apply never waits for it, and ping bypasses both. Drain history reads execute outside those locks and discard snapshots if the drain was cancelled or replaced. Existing nonblocking write admission, accept-time busy capture, single-use plans and bounded connection slots remain. Mac ping skips its inline housekeeping tick; other Mac scheduling is unchanged.

### 2026-09-27 — PEPEPANE fix 3: lifecycle journal probe

Spec section 14's owner-run probe list gains a lifecycle journal section after the stale-cursor section (20 sections total). The probe imports the new module-level `lifecycle_journal_argv` from the installed broker and uses the same argv as root history reads, including the LOCAL_FAIL correction. It compares the latest lifecycle against a bounded unfiltered history, reports PCRE2/grep support and captures stdout, stderr and exit status for the same argv with a nonmatching pattern. If the independent 10,000-record baseline contains no lifecycle, the comparison is explicitly inconclusive. This probe remains owner-run; build validation uses shell syntax, list output and an injected synthetic runner only.


## 2026-09-27 — PEPEPANE fix 4: exact projection key allowance

The projection canary permits long hex only at the exact root `deviceKey` path,
then verifies it against `imd whoami`. A nested `inference.deviceKey`, including
one inside an array, is refused and audited without either key. The additive
`allowed_hex64_paths` keyword on `find_secret` and `find_secret_path` enforces
spec §13's "any other" value rule; the existing `allowed_hex64_fields` keyword
keeps its recursive key-name semantics for other callers. Both redactor copies
remain byte-identical. A synthetic eight-key source fixture exercises the real
projection function and both broker canaries.


## 2026-09-27 — PEPEPANE fix 5: long-hex hardening beyond §13

Owner-approved deviation from spec §13's literal lowercase, exactly-64 pattern:
`HEX64_RE` now detects runs of at least 64 hex digits, including uppercase,
optional `0x` prefixes and word-adjacent values. Both canary detection and
redaction use `(?<![0-9A-Fa-f])(?:0x)?[0-9A-Fa-f]{64,}(?![0-9A-Fa-f])`.
The field allowlist remains exactly `submissionHash`, `txHash`, `deviceKey`;
there is no SHA-256 exception. Whoami still supplies the `deviceKey` field.
Both copies remain byte-identical, and 65-digit values are now redacted too.


## 2026-09-27 — PEPEPANE fix 10: fixture content guard

The fixture guard now scans decoded JSON and JSONL keys and strings, plus plain
text, for JWTs, secret field names and the hardened long-hex pattern. JSON
escapes, duplicate keys and numeric-only long hex cannot bypass the scan.
The fixture-only public/hash allowlist is `submissionHash`, `hash`, `txHash`,
`deviceKey`; it never exempts JWTs or secret field names. It does not expand the
production redactor's three-field allowlist.

The new per-entry `allow: ["synthetic_refusal"]` applies only to the six named
synthetic projection/status source and refusal samples, at exact documented
paths with exact synthetic values. It cannot exempt another private-key value,
a nested secret key, JWT, or unrelated hex. Additional hex exceptions are only
complete device lines in three named CLI captures, the bare key in the whoami
capture, `[0].Id`/`[0].Image` in the Docker inspect capture, and the exact
2 MiB A filler at `payload.item.text` in the oversize transcript. Short journald
ids, cursors and 40-digit addresses remain outside the long-hex rule.

No fixture bytes were changed for this guard. The original server-masked
heartbeat and its `redactions: []` entry are preserved. The additive nested-key
fixture from fix 4 is synthetic and carries its own digest and source notes.


## 2026-09-27 — PEPEPANE fixes 8–9: independent liveness facts

CONTROL renders successful verification in green and the separate connected span
in green only for literal `True`; pending, false and not-yet-reported connection
states are yellow. Verification detail and the yellow restart-required note keep
their previous semantics. The status helper accepts a Rich `Text` so those spans
survive composition (spec §11's separate restart and reconnection facts).

A heartbeat reporting running tasks without an attributable `seat_current` now
renders `⚙ N task(s) running` in yellow and contributes amber to the hero. Tail
death, inactive unit, offline and stale-heartbeat warnings retain precedence.
This implements the owner fix brief's explicit missing-current state rather than
claiming green idle from the daemon's alive state. The boundary sweep includes
that state in the worst payload as well as healthy and attributed work. Measured
on Textual 8.2.8: the existing 134-column/50-row pins and 210-column full LEDGER
tier hold; CONFIG still sets the height. No pin, CSS or protected surface changed.


## 2026-09-27 — PEPEPANE owner D2: Textual drag selection

The owner accepts Textual 8.2.8's inclusive end cell. The two drag-copy tests now
expect `LINE[:11]` and `LINE[6:12]` on 8.2.8 or later, and retain `LINE[:10]` and
`LINE[6:11]` on earlier versions. The installed `textual.__version__` is parsed
with the standard library; no dependency or installed environment changes.
Textual 8.1.1 had the exclusive end, but 8.1.2–8.2.7 were not bisected. This is
the explicit owner exception to leaving the two BASE failures untouched, rather
than a change to selection or clipboard behavior.

The install runbook now gives the measured 134×50 minimum before first use,
CONFIG's height floor, the 210-column LEDGER tier and scrolling/widening cues.
The wheel script header correctly counts 20 dependency wheels plus the fork.
The existing standing-read 12-second overall budget and local-only fallback are
retained as recorded with D1. Follow-ups 23 and 28–31 record the resolved version
cause, conservative over-redaction, future authoritative pending suffixes,
privileged-code review and the complete public-push hygiene work. Public hygiene
is deferred as directed by the owner; no captured host identities or historical
plan content were changed in this round.

### 2026-09-27 — PEPEPANE review fixes R1–R3

The lifecycle query now preserves a parse-failure flag: malformed JSON, non-object records and unreadable MESSAGE values fail closed even beside a cursor or readable lifecycle records. Successful empty history still follows owner D1. Ordinary journal consumers continue retaining readable records while skipping unusable ones. The concurrent in-flight helper snapshots its attribute once before testing/copying it, so normal write completion cannot crash accept or dispatch.

Protocol clarification for orphan-control refusals: `partial` distinguishes an error before any signal from one after an already-started subset; `killed` lists that subset's numeric process/group identities, with `plan_spent` and any original error detail preserved. A partial result also carries the apply `audit_seq`. Both deadline and process-snapshot refusals use one finalizer that creates the actual-target verification watch and writes an apply audit with outcome `partial` and the identities in `args.killed`. No further initial signal follows the refusal; existing identity-checked completion applies only to targets already signalled. This adds explicit error detail without changing any verb or weakening the five-second start deadline.


## 2026-09-27 — PEPEPANE fix-round review closure

The independent critical review of the owner fix round found unreadable lifecycle
records accepted behind a cursor, a concurrent in-flight snapshot race, and lost
audit/verification state after a partial orphan action. Commit `5233d4e` fixes all
three. The same reviewer marked R1–R3 ADDRESSED after 34 named checks and inverse
mutation proofs, with exact restoration. The deploy closure is rebuilt once after
this review closure; the seat suite and final full suite validate that final tree.

### 2026-09-27 — PEPEPANE second round fix 1: measured lifecycle outcomes

The VPS systemd 259.5 JSON grep no-match is exit 1 with empty output and stderr. The shared `lifecycle_read_outcome` also accepts marker/cursor-only exit 1, but refuses exit 0 without a valid record and all diagnostics or malformed mixed output. Lifecycle argv now omits the unused cursor and retains stderr diagnostics. The owner-run probe imports this outcome helper, slices its baseline at the grep option, requires a genuinely newer heartbeat for filter-before-limit PASS, and prints JSON record fields only from MESSAGE and __REALTIME_TIMESTAMP. This corrects the first-round D1 marker assumption; no live probe was run.

### 2026-09-27 — PEPEPANE second round fix 2, owner E1: two apply deadlines

Admission remains 5 seconds from accept before plan consumption; transient starts and initial orphan signals retain that same bound. Systemctl execution gets a separate 15-second accept deadline. Apply gate reads run standing, outbox, unit, journal window, lifecycle last, each timeout capped by the remaining monotonic budget (minimum 0.5 seconds). The lifecycle check therefore follows the slow plane read. Restart, stop and start use the shared verb-first `--no-block` argv helper with a 3-second queue-command timeout, leaving 2 seconds within the 20-second client budget. Drain fires use the same helper without a client deadline. `outcome: applied` means systemd accepted the job; a later start failure is detected by verify as no `runtimes:` within 30 seconds. Stop verifies only a raw inactive or failed state, never deactivating.

A pending verify watch is installed immediately when consume succeeds. Every subsequent refusal and nonzero queue-command exit completes it false with code and detail; partial kills retain their real-target watch. The consumed armed-drain refusal audit includes its plan id. Late-apply details identify whether the plan was spent and suggest offline mode for slow plane reads. A successful local-only acknowledgement can now restart after a 12-second standing timeout inside the execution budget. The documented standing retry itself is unchanged.

### 2026-09-27 — PEPEPANE second round fixes 3–4, owner E3: read isolation and reserved admission

This supersedes R2's at-most-seven connection threads: the accept cap is ten, with decoding in each connection thread. Only reads that can spawn a transient child take a separate four-slot admission semaphore and serialized read lock. A full read queue answers busy immediately. Waiters check socket EOF around timed lock acquisition and release both resources on abandonment or error. The EOF check uses select before MSG_PEEK, never changes the five-second socket timeout, and treats seam objects without fileno as alive. UnixSocketBroker never half-closes a request.

Root ping, verify, audit-tail and orphans bypass the slow-read lock. Gate bypasses it when seat identity is already known; install.sh supplies `--seat`. A dynamic gate or seat projection requiring an uncached whoami remains serialized. Worker-uid outbox, work-stat, hints-stat and auth-mtime also bypass it because they spawn no transient unit. Verify cursor updates join the existing short state-lock section; audit-tail relies on append-only single-line writes and skips incomplete lines. Four serialized reads leave six admission slots available to control and independent reads; slow undecoded senders remain bounded by the existing five-second transport deadline. Ten connection threads remain below the unit's TasksMax=64.

### 2026-09-27 — PEPEPANE second round fix 5, owner E2: Mac armed drain

LocalDockerBroker now rejects manual restart and stop while a drain is armed at both plan and apply. The existing `drain_already_armed` error carries the cancel-drain hint; apply refusals include the consumed plan identifier in audit. Container trust and force-disabled rules are unchanged. This ports the root safety addition from the first corrective round.

### 2026-09-27 — PEPEPANE second round fix 6 and lifecycle wording

Empty executor messages and journald-stripped failure lines now share terminal semantics in gate and grammar: task, question or campaign followed by failed and its colon, with an optional space/message. The grammar preserves the optional msg group; synthetic fixture pairs prove both forms close the ledger. Gate/probe wording now distinguishes a failed or unreadable lifecycle history from successful empty history. The stale Mac segment refusal remains; its regression name now describes that condition. The original R4 empty-history claim is visibly marked superseded by D1.

### 2026-09-27 — PEPEPANE second round fix 8: partial signal failures

Initial group and individual orphan signals now route timeout, OS error and nonzero command exits through the partial-action finalizer. Already signalled targets retain their audit, completion watch and identity-checked follow-up; remaining candidates are named as skipped. A failure before any signal is explicitly nonpartial and audited. This adds failure handling to the reference implementation without issuing extra signals.

### 2026-09-27 — PEPEPANE E1 edge: unresolved seat identity

The installer supplies a seat id, and normal plans resolve a missing id through the projection. If identity is still unresolved when a bounded apply starts, its plane read is unavailable/local-only instead of launching an unbounded whoami transient. The existing explicit local-only acknowledgement remains mandatory. Ordinary plan/read identity resolution is preserved, and offline gates avoid identity lookup entirely. This closes the dynamic-identity edge of the root reply budget.

**2026-09-27 (pepepane fix round 2, CONTROL E1 and fixes 7–8).** CONTROL keeps the same plan after a lost apply reply or a command timeout, shows an amber unknown outcome, and checks its verify watch. The uncertainty interval starts before sending apply; transport failures keep polling, while an unknown plan after the 20-second interval ends with an explicit spent-plan message and audit refresh. An admission refusal explicitly marked unspent retains its confirmation prompt; a spent refusal names the offline fallback. Partial orphan actions retain killed and skipped PID lists through pending and final verification, and refresh the audit. Connection wording appears only when the broker supplies a connection value, so stop, doctor and drain arming do not invent a pending connection.

**2026-09-27 (pepepane fix round 2, fix 9 redaction residual).** Chose the brief's permitted documentation option: retain the existing field-based `deviceKey` allowance in `redact` and recursive `redact_tree`. A nested field with that name can therefore retain a long hex value without a whoami match; the general redactor is not by itself a private-key guarantee for arbitrary trees. The projection canary remains stricter: only the root `deviceKey` path matched to whoami is exempt, and nested fields are refused. No canary or redaction test is weakened. Follow-up 33 records the possible future restriction to the two whoami call sites. Follow-up 31 now refers to the real host IPs without reproducing their literals.

**2026-09-27 (pepepane fix round 2, D2 version parser).** The select-to-copy test expectation now accepts a two-part Textual version such as `8.3` as `8.3.0`; missing patch defaults to zero. The measured 8.2.8 inclusive drag boundary and earlier exclusive expectation remain unchanged. Import-level regression cases cover both two-part forms, older releases and a prerelease suffix. Production copy behavior is unchanged.

**2026-09-27 (pepepane fix round 2, fix 9 NOW contract deviation).** Added the existing `seat_daemon_running` field to `SEAT_WIDGET_SIGNATURES["SeatNow"]` and the widget's named arguments because a positive daemon count without a current task must not render idle. `SEAT_KEYS` and the status schema do not change. The task line keeps unavailable-tail and attributed-task precedence, then shows an amber running count matching LIVE; plane details remain on their own line, with plane-assigned waiting wording used when there is no positive local count. An independent signature restatement and compositor tests bind the addition. Healthy, worst-case and unattributed boundary sweeps on Textual 8.2.8 still measure 134 columns and 50 rows, with LEDGER full at 210 columns; no pin, CSS or protected surface changed.


## 2026-09-27 — PEPEPANE second-round review: uncertain queue results and recovered UI effects

The independent review found two integrations missing from E1. A systemctl queue-command timeout is uncertain, so it retains the real verification watch, its cursor, and the command-start time. Both the command handler and the consumed-plan finalizer preserve that watch. A known nonzero exit or a pre-execution refusal still completes verification as failed. This clarifies the preceding consumed-error decision: timeout alone is not evidence that systemd rejected the job.

CONTROL applies successful-plan UI effects once per plan, whether the apply reply arrives normally or verification recovers the outcome. A recovered skills change marks restart required and offers drain-restart; a recovered restart clears the existing next-step note. Failed verification leaves those effects unapplied. Real root-broker tests cover eventual restart success, missing evidence through the deadline, absent cursors, successful and failed skills changes, and repeated verification without duplicate effects. These are corrections to the approved workflow, with no new control verbs or layout changes.

The scoped re-review narrowed the timeout exemption to those actual systemctl-watch kinds. A first orphan-signal timeout has no completed target or resolvable kill watch, so its consume-time placeholder must still complete as failed instead of remaining pending indefinitely. The permanent regression advances housekeeping beyond thirty seconds to check that distinction.

Independent scoped re-review approved R1/R2 at `d57ec81`, with all three original or follow-on reproductions and pertinent permanent tests passing (26 checks). The whole-round review had also passed 85 named integration checks. Two fix waves were used for R1 and one for R2; no Critical or Important finding remains. The final archive is built only after this closure and renamed after the committed hash refresh, as the second fix brief requires.

### 2026-09-28 — PEPEPANE F1: standing freshness at read completion

The standing age now uses its own completion timestamp on both brokers; heartbeat and lifecycle ages still use the later gate evaluation time. The Mac reads standing, outbox, inspect, then tail/history, so a newly accepted task after standing is caught by the final lifecycle read. Plan previews, gate reads and audit preconditions share this value. This implements owner decision F1; the optional `standing_checked_at` argument extends the pure gate evaluator without changing its existing callers' default behavior. The broker harness drives wall and monotonic clocks from one timeline, including the 5.5-second standing regression with subsequent 1.0/1.1-second journal reads and no local-only acknowledgement.

### 2026-09-28 — PEPEPANE lifecycle classification and journal framing

Fix brief 3 requires lifecycle classification on raw text before redaction: stripping a control-only objective erased the accepted event. Both brokers now keep raw journal/tail lines internally, and redact gate replies and plan/apply preconditions at the output boundary; force matching retains the raw node id. The TUI follower and grammar had the same ordering defect: raw classification now precedes redaction of emitted text and every captured field, before queueing or ledger persistence. This supersedes the old redact-before-classify ordering while preserving spec §13's storage/render hygiene. Synthetic regressions verify queue and SQLite output, including a mutation that removes capture redaction and fails.

Journal, Docker tail and backfill records split only at LF, with trailing CR removal. Lifecycle reads reject nonempty results with no classifiable lifecycle record. Invalid UTF-8 remains strict in lifecycle mode and replacement-decoded in the ordinary heartbeat/display window, as the owner correction requires. The lifecycle argv now includes `--all` before `--grep` so long fields remain present in the filtered query and the probe's baseline. The owner must re-run p05 on imd-vps because the earlier live confirmation used the previous argv. Probe byte-array MESSAGEs decode strictly; non-JSON stdout is represented by a fixed omission label. The existing code_block scrub remains unchanged.

F1 display inspection found no UI consumer that recomputes age from planeAsOfUtc: CONTROL's plan block uses the broker's standing_age_s directly, while gate/hero summaries show count and mode. No document-model contract extension is needed.

### 2026-09-28 — PEPEPANE consumed failures and partial Mac signals

A second drain apply is refused before changing the original drain's online/offline mode. Unexpected dispatch exceptions now complete consumed plans as unsuccessful and audit the exception class with the plan id on both brokers. The Mac now creates its pending watch at consume and ports partial kill finalization: completed signals keep their audit, identity snapshots and pending verification even if a later snapshot or signal fails; unsignalled candidates appear as skipped. Root systemctl timeouts remain uncertain and verifiable, and existing root partial-signal handling is preserved.

### 2026-09-28 — PEPEPANE bounded stop verification and useful deadline hints

Root stop plans and watches use the measured TimeoutStopUSec plus ten seconds, capped at 110 seconds; unreadable or infinite values use that cap, safely before watch expiry at 120 seconds. Deactivating remains pending until that deadline, and inactive/failed plus the shutdown line confirms completion. VERIFY_WITHIN_S remains 30 for start and restart. Forced restart retains the explicit existing contract of runtimes within 30 seconds after shutting down: increasing only its initial shutdown wait would not fix a task that emits shutting down before a long teardown, while increasing the post-shutdown interval changes that contract. Brief 3 permits recording this item; follow-up 36 describes the remaining case rather than silently changing restart semantics.

The offline suggestion is now restricted to a consumed execution-deadline refusal for an originally online restart/stop. It is absent from unspent admission, already-offline, start/boot, transient-start and orphan-signal refusals. Enable-boot and disable-boot retain the shared three-second systemctl timeout; timeout replies keep their verification watches so is-enabled can resolve the result, within the unchanged 15 + 3 + 2 ≤ 20 client budget. Admission documentation now states that the six slots outside the serialized read allowance are shared by control requests and all unserialized reads, including worker-uid and gate reads.


### 2026-09-28 — PEPEPANE CONTROL refusal details and bounded recovery

All orphan refusal details carrying killed/skipped lists now use explicit PID formatting. A non-partial refusal says nothing signalled, returns to idle and drops the plan without polling verify; a partial action keeps its PID evidence through verification and shows the sanitized refusal reason and hint. New force and skills prompts clear the previous partial note, while ignored keys during an active operation keep its evidence.

This supersedes the second-round CONTROL entry's spent-plan assumption after a missing apply reply: transport, bad-response, unreachable and unknown-plan verification failures retry only through the client deadline measured from sending apply. After that, CONTROL reports outcome and plan state unknown and directs the operator to LOG and audit before creating a new plan. A missing reply does not prove consume or non-application. A command-timeout reply or an existing verification watch does prove consume, so later uncertainty retains the spent-plan wording without claiming nothing happened. Explicit spent/unspent replies remain authoritative, and no automatic new plan or apply is introduced. The operator install guide now explains queued systemd jobs, separate verification and this recovery flow.

The long-row RichLog test now observes the completion of the deferred automatic scroll before moving horizontally. SeatLog schedules scroll_end after refresh, and Textual defers the actual scroll to another refresh, so a single pilot pause could let that callback reset the test's horizontal position. An additional deferred-frame case exercises this ordering directly; the test waits on completion and composited text, with no sleeps, pin changes or production widget change.


### 2026-09-28 — PEPEPANE review R3.1: probe byte-array output

The independent review demonstrated that p05 emitted numeric MESSAGE arrays unchanged, allowing encoded credentials to pass through text redaction. The probe now strictly decodes valid arrays before its existing output scrub and replaces unreadable MESSAGE values with a fixed omission label. The same small decoder serves lifecycle comparison, which retains unredacted decoded text internally; the original subprocess result stays unchanged. Permanent synthetic tests exercise string and array credentials, invalid UTF-8 and invalid byte types through the actual Python scrub and the final hex-removal pass. This corrects the output boundary without changing broker decoding or probe verdict rules.


### 2026-09-28 — PEPEPANE third-round independent review closure

The critical review of the third corrective round covered standing freshness, lifecycle classification and redaction, consumed-plan finalization, partial actions, CONTROL recovery and stop-watch lifetime. It found one output-boundary defect, R3.1, fixed in `3b7b0a6`. The same reviewer marked it ADDRESSED after the original reproduction and pertinent permanent cases passed (13 checks); bypassing output normalization made three cases fail, and exact inverse restoration returned the four regression cases to green. No Critical or Important finding remains. Follow-ups 35 and 36 retain the owner-run lifecycle probe and the explicitly permitted forced-restart teardown limitation. The archive is rebuilt once after this closure, followed by the seat suite including select-to-copy and the single final full-suite run.

### 2026-09-28 — PEPEPANE G3 accepted heads, Appendix B and contract C.5

Owner G3 adds `accepted_code_head` and `accepted_fuzz_head` after the complete accepted forms, raising the stamped-pattern count from 31 to 33 and expanding ACCEPTED_KINDS to five. Complete code accepts permit empty paths while preserving max_turns. A head is accepted only when its complete tail is absent anywhere after the dash; complete tails followed by extra prose remain unknown. Campaign heads map to campaign/fuzz in the ledger. The root gate, lifecycle query, read sanity check and forced-node match share one accepted-node helper; the Mac gate uses that same classification. This is the approved Appendix B / contract C.5 amendment, not a looser unanchored parser. The lifecycle grep expression has changed, requiring owner-run p05 again.

### 2026-09-28 — PEPEPANE complete journal fields for the ledger follower

The journal fake now filters grep against the full MESSAGE before emitting null for fields at least 4,088 UTF-8 bytes long when all fields were not requested, matching the measured systemd behavior. The TUI follower requests all fields in both cursor and since forms so a long task-failed line closes its ledger row. Removing that option demonstrably leaves the row open; removing it from the root lifecycle query also breaks the long-terminal regression. Broker heartbeat-window and ordinary cursor reads retain their existing options and replacement decoder: the separate strict lifecycle query supplies the gate's authoritative newest task event. This is the explicit brief-4 allowance for those non-lifecycle reads.

### 2026-09-28 — PEPEPANE D5–D7 teardown verification and signal uncertainty

This supersedes the third-round stop/forced-restart entry. Stop uses its extended TimeoutStopUSec-plus-ten deadline, capped at 110 seconds, only while ActiveState is deactivating or after shutting down has appeared; otherwise it keeps the 30-second window. Stop and forced-restart planning re-read the current unit stop timeout and graceful-stop capability. Failed reads clear the previous timeout instead of silently keeping stale configuration, and watches retain their own plan's bound.

For a forced restart only, the plan advertises the maximum of its post-shutdown interval: TimeoutStopUSec plus 30 seconds, capped at 110. Once shutting down arrives, both the success interval and missing-runtimes deadline are additionally capped at 110 seconds minus time already spent since apply began. Thus the watch reaches a verdict before its 120-second purge. The watch is explicitly marked from force_node8; ordinary restart, drain-restart and start keep VERIFY_WITHIN_S at 30. Follow-up 36 is closed under the approved D7 contract.

Mac orphan refusal detail now marks signal outcome unknown only when the actual kill-TERM runner timed out. The transport catch is the narrow point that can distinguish an executed command from an already-open breaker; process-snapshot timeouts and pre-execution breaker refusals do not acquire that marker. The existing apply-kill finalizer preserves the marker alongside partial and PID evidence. All root/Mac drain-already-armed plan and apply refusals now return the same flat drain fields plus the cancel-drain hint.
