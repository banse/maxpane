# Surf's swarm body (`s`) — design

**Status:** built 2026-09-17 (`c3c1c50`..`cc4a8a3`).

**Research:** `docs/imd_swarm_api.md` — every endpoint, shape, size and timing quoted here was measured there on
2026-09-16.

## 1. What this is

A fifth surf body, opened with `s`, that answers **what the IMD swarm is doing right now**: which agents are
online, what each is working on, what is stuck and why, what shipped, and how fast work is moving. It reads the
swarm's control plane, which is keyless.

It is a body, not a ninth dashboard: `app.py`, `__main__.py` and `GAMES` are untouched, exactly as `l`, `e` and
`4` left them.

### Decisions taken

| Question | Decision |
|---|---|
| Subject | the live swarm first: the field, the queue, what shipped, throughput |
| Placement | a surf body under `s`, not a dashboard, not a panel on the existing body |
| Reads | `/health` on every tier run; the job list only when a counter moved; details for unfinished jobs; a full sweep on a slow tier |
| Hero | its own three cards, toggled with the body (the `4` body's precedent) |
| Degraded groups | none added — the title row is full at eight |
| The explorer's inference headline | omitted: no public route serves it |

## 2. Modules

| File | Responsibility |
|---|---|
| `data/surf_swarm_client.py` | HTTP against the one host, keyless. Nothing else. |
| `data/surf_swarm.py` | pure decode and fold: no network, no clock, no Textual |
| `data/surf_models.py` | row-shape declarations for the new rows (existing file) |
| `data/surf_manager.py` | two tiers, two slots, payload keys (existing file) |
| `data/surf_cache.py` | tier TTLs and backoffs (existing file) |
| `widgets/surf/swarm_hero.py` | AGENTS / IN FLIGHT / ACCEPTED TODAY |
| `widgets/surf/swarm_field.py` | THE FIELD |
| `widgets/surf/swarm_shipped.py` | JUST SHIPPED |
| `widgets/surf/swarm_queue.py` | QUEUE |
| `widgets/surf/swarm_throughput.py` | THROUGHPUT |
| `screens/surf.py` | `MODE_SWARM`, the `s` binding, the body, its pins (existing file) |

The client/fold split is `surf_pool4_client.py` and `surf_pool4_market.py`, so the fold is testable against
committed fixtures with no transport in sight.

## 3. Reads and clocks

**`TIER_SWARM`, TTL 60 s, failure backoff 120 s.**

1. `GET /health` — 567 B, on every tier run, so at most once per 60 s.
2. Compare `connectedDaemons`, `activeEnrollments`, `workingNow`, `acceptedLastDay` and every `pending*` against
   the previous run. Re-read `GET /jobs` (27.5 KB) only if one moved, **or** if 300 s have passed since the last
   list read. The list takes no filter parameters and carries no validators, so this counter check is the only
   smaller read available. It is curator's version-check precedent, one size down.
3. `GET /jobs/{id}` for every job whose state is not terminal (`executing`, `blocked`) — 8 jobs, ~18 KB at
   capture. This is the only source of agent attribution, subtasks and verdicts.

**`TIER_SWARM_SCORES`, TTL 1800 s, failure backoff 300 s.** All 62 details plus `/launches` and `/sites`:
188 KB, 24.9 s measured, spaced so the host is never hit in a burst. Feeds the score and throughput numbers only.

Both tiers are spawned, never awaited: first paint never waits for the swarm, which is how `TIER_LAUNCHPAD` and
`TIER_POOL4` already behave, and `test_the_first_payload_is_not_behind_the_analysis_read` is the shape of the
tripwire that keeps it honest.

**Slots:** `SLOT_SWARM` and `SLOT_SWARM_SCORES`, each with its own last-good and its own `as of HH:MM`.

**Failure classification is by status code**, not message text: a timeout or 5xx degrades the tier and backs off;
a 404 on one detail drops that row and keeps the rest, because a job can vanish between the list and the detail.

## 4. Payload keys

All prefixed `swarm_`: `agents_online`, `agents_enrolled`, `working_now`, `accepted_today`, `jobs_in_flight`,
`jobs_blocked`, `queue_depths`, `services_up`, `field_rows`, `queue_rows`, `blocked_rows`, `shipped_rows`,
`score_rows`, `throughput`, `network`, `as_of_hhmm`, `scores_as_of_hhmm`, `stale`.

Row shapes are declared in `data/surf_models.py` like every other surf row, so widgets and tests share one
contract:

- `field_rows`: `job_id`, `template`, `objective`, `node_key`, `role`, `node_state`, `agent_token`, `agent_id`,
  `revisions`, `dispatch_note`, `moved_ts`, `age_s`.
- `queue_rows`: `state`, `count`. `blocked_rows`: `job_id`, `template`, `reason`, `moved_ts`.
- `shipped_rows`: `kind` (delivery / launch / site), `job_id`, `label`, `commit`, `chain_id`, `address`,
  `tx_hash`, `ens_name`, `cid`, `at_ts`.
- `score_rows`: `agent_id`, `agent_token`, `jobs_scored`, `mean_score`, `last_tx_hash`, `last_chain_id`.
- `throughput`: `accepted_per_day`, `median_delivery_s`, `revision_rate`, `window_days`.

## 5. The body

`s` swaps `#middle-row`, `#separator` and `#bottom-row` for `MODE_SWARM`; `escape` backs out, one way.

**Hero (its own, toggled with the body):** **AGENTS** — online of enrolled, plus whether verifier, publisher and
deployer are up; **IN FLIGHT** — executing now, and how many are blocked; **ACCEPTED TODAY** — accepted in the
last day. `_SURF_HERO_MODES` gains this mode; exactly one hero is ever on screen.

**Panels.** Left column: **THE FIELD** over **JUST SHIPPED**. Rail: **QUEUE** over **THROUGHPUT**.

- **THE FIELD** — one row per unfinished job: agent seat, subtask and role, state, age, revisions, and the
  dispatcher's own note, which is what explains a stall.
- **JUST SHIPPED** — recent deliveries with their commit, launch artifacts with contract addresses, and
  ENS-named sites. Every real address carries the copy icon; a transaction hash is shortened and carries none. An
  ENS-named site carries neither: `data/surf_swarm.py` hardcodes `address: None` for a site row and the upstream
  payload has no address field for a site at all — a site's ENS name resolves a content hash, not a wallet — so
  there is nothing for an icon to copy.
- **QUEUE** — counts by state across all jobs, then every blocked job with its reason.
- **THROUGHPUT** — accepted per day, median created-to-delivered, revision rate, over a named window.

**The chain word** (`· SEPOLIA`, `· MAINNET`, `· —`) is **per row, never in a title** (overruled during
implementation, 2026-09-16, correcting this section as first written below). JUST SHIPPED's own rows mix
chains — launches are mostly Sepolia while the abandoned ones are mainnet — so a single title word would be
confidently wrong for some of the rows beneath it. Each row therefore names its own chain, from that row's own
`chain_id`, in a CHAIN column beside whatever carries an address or a hash; THROUGHPUT's score rows carry the
same per-row word beside their transaction hash, for the identical reason. It is an allowlist over known chain
ids, so an unknown one renders the dash rather than a guess, which is `network_word`'s existing rule — restated
as `widgets/surf/_swarm_chain.chain_word`, shared by both panels.

*As first written, this section said the chain word "goes in the titles of panels that show chain data — JUST
SHIPPED, and any score quoting a transaction — and nowhere else." That was wrong for the reason above and was
never built.*

**Widths.** Its own pins, `SURF_SWARM_FULL_LAYOUT_COLUMNS` and `SURF_SWARM_FULL_LAYOUT_ROWS`, measured in situ
and never derived. Panels shed columns behind `‹ widen`. Every title keeps a blank line under it, and columns
align across panels.

**The status hint** becomes `l launchpad · 4 pool4 · s swarm`, one markup run, and it is measured against the
bar's left-label budget at 143 columns before the wording is fixed. `s swarm` is the half that shortens.

## 6. Honesty contracts

1. **A failed read is `None`, never `0`.** An unread value renders `--`; a real zero renders `0`. "Nothing in
   flight" is a sentence the panel earns only from a successful read.
2. **Last-good behind a marker.** Each slot serves its last good payload with its own `as of HH:MM`. The footer
   says `stale` only when the marker drifts further from the title bar than the two TTLs can explain; the
   threshold is derived from those TTLs, not chosen.
3. **Third-party text is hostile.** Objectives, dispatch notes, verdict details, launch and artifact names are
   user- or agent-written. Each row is a pre-built `rich.text.Text`, fitted on `cell_len`. Addresses inside prose
   get the copy icon through `address_prose`.
4. **One unsigned source, said plainly.** Nothing the host serves is signed. Review scores carry a Sepolia
   transaction hash, so the view shows the hash rather than claiming it verified anything, the way HATCHES marks
   a docs-sourced adoption.
5. **No invented headline.** The explorer's inference total has no public route; it is absent, not estimated.
6. **The clock is injected.** Ages come from a time the tests control.

## 7. Testing

- **Fixtures** captured from the live reads and committed under `tests/fixtures/surf/swarm/`: health, the 62-job
  list, details for an executing job, a blocked job and a completed job carrying a review, a transaction and a
  site, plus launches and sites.
- **No test touches the network**, asserted structurally with a transport that raises on use.
- **The fold is tested pure:** counts, ages against an injected clock, delivery times, revision rate, seat
  attribution.
- **The panels are tested against composited output:** the blank line under each title, column alignment, the
  `‹ widen` tier, a copy icon on every address with a click that copies that row's address, and `--` where a
  zero would look identical.
- **The body:** `s` opens it, `escape` backs out, exactly one hero, the hint fits at 143, and both pins fail in
  both directions.
- **The address sweep** gains this view (`("s",)`) with hand-listed seeded addresses, so the enforcement tests
  refuse an address without its icon here.
- **Degradation:** last-good behind the marker, `stale` only past the threshold, zero versus unread, the
  counter check preventing the list read when nothing moved, and the 300 s ceiling forcing one anyway.
- **Every new test is proven to bite** by mutation.

## 8. Out of scope

- Writing anything to the swarm. MaxPane stays read-only; the host's write surface is authenticated anyway.
- Reading IPFS or opening sites.
- Identifying the ERC-8004 registry contract or verifying score transactions on Sepolia. The hashes are shown;
  chasing them is a later question.
- Per-agent profiles beyond token id and onchain id, which is all the API exposes.
- The explorer's `Find` page.
