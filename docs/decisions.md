# Decisions and withdrawn statements

Dated one-liners for things `CLAUDE.md` used to say and no longer does, and for choices whose
reasoning would otherwise be re-argued. Newest first. A plan, PRD or work-package file that still
asserts a withdrawn statement is historical — do not review code against it.

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
