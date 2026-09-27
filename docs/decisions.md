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
  `SeatManager.backfill()` calls it itself: it starts the follower, drains after `BACKFILL_QUIET_S` of quiet
  (cap `BACKFILL_MAX_S`) and stops it before returning, so `--once` leaves no follower. This deviates from
  spec §4.3 "(no thread)" (header owner note 7) (spec §4.3, §9, §15).
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
- **2026-09-27 (final review R4, lifecycle evidence and contract addition)** — An absent anchored lifecycle record is
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
