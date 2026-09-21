# SURFBOARD — AGENT body on `/seats/{tokenId}`: lifetime seat stats

**Status:** APPROVED by the owner 2026-09-21 — D1–D5 all as recommended. Tier 2 (new endpoint, new contract keys, several AGENT panels).
**Trigger:** the owner compared seat #420 on screen with explorer.imd.fun/agents/420 and the numbers disagreed.

## 1. The defect, measured

Every number below was read live on 2026-09-21 (captures in the session scratchpad; committed as fixtures in WP0).

| seat #420 | explorer = `GET api.imd.fun/seats/420` | AGENT body today |
|---|---|---|
| attempts | **74** | — (NODES `2`) |
| accepted | **12** ("12 of 74 attempts accepted") | ACC **1**, JOBS **2** |
| scored reviews | **72** | **33** scored |

Two causes, each reproducing the screen's number exactly:

1. **A window presented as a total.** `GET /jobs` returns the newest **100** jobs (`count` is the page length,
   not a total; no pagination, parameters ignored). On 2026-09-21 that covered 02:26–05:44 UTC, about 3.3 h.
   The AGENT body folds seat stats out of the details of those jobs plus the jobs-seen map, and prints the
   result as if it were the seat's record. #420 has 2 of its 12 accepted jobs and 33 of its 72 reviews inside
   the window: that is `2 · 2`, ACC `1` and `33 scored`. `docs/imd_swarm_api.md` recorded `/jobs` as "every job"
   (62) on 2026-09-16, so this was true when the body was designed and stopped being true since.
2. **Competitive jobs list only the winner.** An `oracle_assess` job's detail carries one node (the accepted
   seat, e.g. #47 on `80c853bd`) while its review scores twelve seats, #420 among them. So a seat's
   scored-but-not-used attempts reach FEEDBACK and never reach RECORD, NODES or JOBS: the body contradicts itself.

The window fold cannot be fixed by sweeping harder: there is no older page to sweep, and a winner-only detail
does not name the other attempts at all.

## 2. The source: `GET /seats/{tokenId}`

Undocumented, keyless, GET, measured on 8 seats (6–90 KB; seat #0 is the largest at 90 KB, 202 reviews).
It is what the explorer's seat page renders ("12 of 74 attempts accepted", "72 scored" for #420).

| field | meaning (as measured) |
|---|---|
| `tokenId`, `agentId`, `chainId` (1), `collection`, `adapter` | the IDMD seat and its ERC-8004 agent |
| `status` (`active`), `ownership` (`owned`), `owner` (0x…), `pairedAt`, `online` (bool) | the seat's pairing |
| `daemonVersion`, `runtimes[] {id, version}`, `devices` | what runs it |
| `attempts`, `accepted` | lifetime counters; `accepted == len(work)` on all 8 seats |
| `work[] {jobId, objective, jobState, launch, nodeKey, role, submissionHash, acceptedAt}` | every accepted submission, newest first |
| `reviews[] {jobId, nodeKey, role, value, policy, verdict, submissionHash, status, txHash, chainId, sentAt}` | every scored submission, newest first; one per job |
| `collaborators[] {tokenId, agentId, sharedJobs}` | seats it shared jobs with |

Measured facts the design leans on:
- `reviews[].verdict` was `accepted` and `value` was `1` on all 566 reviews read. **Review-accepted ≠
  `accepted`**: 72 of #420's submissions passed review, 12 were the ones the job used. The screen must name
  both and never conflate them.
- `reviews[].status` is `sent` (txHash + sentAt), `submitted` (txHash, **no** sentAt) or `queued` (neither;
  `chainId` null). No `blockNumber` anywhere.
- **Not served:** rejections, revisions, rejection codes, failed checks, verifier detail, "working now".
- `404 {"error":"unknown_seat","detail":"no device has paired with that token"}` for a token never paired —
  a real negative. `400 invalid_request` for a non-decimal id. `/seats` (no id) is 404: there is no seat list.

## 3. What changes on screen

**Rule:** every number on the AGENT body is either the seat's lifetime record from `/seats`, or visibly
labelled as window-scoped. No panel mixes the two without saying so.

- **Hero** (six boxes, same geometry; contents re-swept per the terminal-layout skill):
  SEAT `IDMD #420` / `agent 50939` / how picked · **ACCEPTED** `12 of 74` · **REVIEWED** `72` (+`n pending`
  when submitted/queued exist) · **SCORE** mean of `reviews[].value` with `(72 scored)` · **COLLAB** `24 seats` ·
  **STATUS** `online ●`/`offline ○` + `last HH:MM` (newest of `acceptedAt`/`sentAt`).
  REVISIONS and ACC/REJ leave the hero — `/seats` serves neither (decision D2).
- **VERDICTS → SEAT RECORD panel:** accepted 12 of 74 · reviewed 72 by status (sent / submitted / queued) ·
  score · by role (from `reviews[].role`) · paired `MM-DD HH:MM` · runtime `claude 2.1.278` · owner as an
  address cell (copy icon + Etherscan, `widgets/address.py`, package `EXPLORER`).
- **RECORD:** one row per `work[]` entry, lifetime: when (`acceptedAt`), job, node, role, job state, objective
  (clipped). The verifier-detail columns (try, rev, verdict, detail) go: the source does not serve them for
  lifetime rows (decision D3).
- **FEEDBACK:** one row per `reviews[]` entry, lifetime: when (`sentAt`, else the status word), value, node,
  job, status, chain (`chain_word(chainId)`), tx (`hash_text`, `for_chain_id(chainId)`; none for `queued`).
- **ROSTER:** still the only seat list there is, so still folded from the job window — **and titled as such**:
  `ROSTER · last 100 jobs since HH:MM · as of HH:MM`. Its `acc/rej/rev/score` columns stay window-scoped under
  that title (decision D4).
- **Unknown seat:** a saved seat no longer needs to be on the roster — `/seats` answers for any paired token, so
  the body shows it directly. `unknown_seat` renders `#N never paired` (a real negative); a failed read renders
  `unavailable` behind the tier's `as of HH:MM`. This replaces change A's `#N not seen` fallback (decision D1).

## 4. Data contract (WP0 freezes it in `data/surf_models.py`)

New / changed keys (the roster keys are unchanged):

- `swarm_seat_selected` — `{token_id, agent_id, selected_by}`; `selected_by` gains nothing; `unseen_token` retires.
- `swarm_seat_state` — `"ok" | "unknown_seat" | None` (`None` = read failed or not yet read).
- `swarm_seat_summary` — `{attempts, accepted, reviewed, review_status: {sent, submitted, queued},
  mean_score, scored, roles: [{role, count}], online, owner, paired_ts, last_active_ts, collaborators,
  runtime}`; every field `None` when the source did not carry it.
- `swarm_seat_work_rows` (replaces `swarm_seat_node_rows`) — `job_id, node_key, role, job_state, objective,
  accepted_ts`.
- `swarm_seat_feedback_rows` — `value, verdict, status, node_key, role, job_id, tx_hash, chain_id, sent_ts`
  (`block_number` retires: not served).
- `swarm_seat_as_of_hhmm` — now the **seat tier's** marker.
- `swarm_roster_window` — `{jobs, oldest_ts}` for the ROSTER title.

## 5. Fetching

- `SwarmClient.fetch_seat(token: int)` → `dict | None`, plus an explicit unknown-seat result for the 404
  (`{"error": "unknown_seat"}` body), distinct from `None`. The token is an `int` formatted into the path —
  never caller text. Same two-host pool, same rotation, same pacing.
- A new tier `TIER_SWARM_SEAT` (proposed 120 s, stale after 30 min like its siblings), keyed to the selected
  token: `select_seat` / `set_seat` stay plain attribute writes and **mark the seat tier due**; the refresh
  worker does the read (no network await in a message handler). The cache slot stores the token it was read
  for, so a switch never shows seat A's numbers under seat B's name while B loads — B shows `Loading…` or its
  own last-good.
- One seat per cycle: the selected one. No fan-out across the roster.
- Persisted last-good is third-party input: validated per field on load (`coerce_points` discipline).

## 6. Must honour (CLAUDE.md)

Read-only GET, keyless, no test on the network (committed fixtures from the WP0 capture: #420, #0 (largest),
#1649, #516 (smallest), an `unknown_seat` 404 body, a 400 body). A failed read is `None`, never `0`;
`unknown_seat` is a representable real negative distinct from "could not look". Third-party strings
(objective, node keys, runtime version, roles) through `markup_safety`; the owner address through
`widgets/address.py`; tx hashes through `hash_text` + `for_chain_id`. Pins re-swept in situ.

## 7. Owner decisions (settled 2026-09-21)

- **D1 — seats off the roster: SHOW.** Any paired seat is shown from `/seats`; change A's `unseen_token` /
  `#N not seen` retire in favour of `#N never paired` (`unknown_seat`).
- **D2 — REVISIONS and REJECTED: DROP** from hero and seat panel; `/seats` does not serve them.
- **D3 — RECORD's verifier detail: DROP.** RECORD is the lifetime `work[]`; no window-scoped verdict block.
- **D4 — ROSTER columns: KEEP** `acc/rej/rev/score`, under the window title.
- **D5 — owner address: SHOW** in the seat panel (copy icon + Etherscan).

## 8. Sequence (the plan expands this)

WP0 capture fixtures + freeze the contract · WP1 client `fetch_seat` + pure fold · WP2 manager tier + selection
wiring · WP3 hero + SEAT RECORD panel · WP4 RECORD + FEEDBACK · WP5 ROSTER title, screen dispatch, layout
re-sweep, address sweep case, README · final whole-branch review, one fix wave, full suite once. Update
`docs/imd_swarm_api.md` (the `/jobs` cap and `/seats/{id}`) in WP0.
