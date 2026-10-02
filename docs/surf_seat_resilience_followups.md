# Surf seat resilience — execution notes and follow-ups

Implements `surf_seat_resilience_plan.md` on `feature/surf-seat-resilience`.
The branch starts at `250e4eb`, preserving the runtime and rank fixes already present in the
owner's workspace, rather than reverting to the older base named in the plan.

## Layout refinement

At the unchanged AGENT pin, COLLAB has 14 content columns; `busy · retrying` needs 15.
It uses two existing body lines (`busy ·`, then `retrying`) when needed. The other cards fit
the complete line. No pin or CSS geometry changes are needed.

## Honest loading words

- RECORD answer: valid job UUID and submission hash in its selected window show dim
  `loading…`; an ineligible `not_read` row retains `not read`. The manager normally marks
  malformed answer identities `unavailable` before they reach the widget.
- Panel: only oracle nodes with valid identities show dim `loading…`. Ineligible `not_read`
  rows retain `not read`; non-oracle rows retain `–`.
- SUBMISSION job: only non-joined rows with valid identities and answer state `read` or
  `no_reply` show dim `loading…`; ineligible snapshots retain `not read yet`.

## Verification environment

Use `env -u NO_COLOR .venv/bin/python -m pytest …` for composited color checks. The session
environment sets `NO_COLOR=1`, which removes colors before the tests inspect them. The two
existing screen color failures reproduced on untouched `250e4eb` and passed with that variable
unset. No production or test assertions were changed to accommodate monochrome output.

## Final review

The whole-branch review found one Important issue: a raw HTTP 200 `{"error":"busy"}` body
could compare equal to the normalized busy result. The final fix preserves transport provenance
with the immutable sentinel inside the client and rejects raw busy error bodies from HTTP 200.
Both new HTTP 200 regressions failed before the fix. Scoped re-review: **Approved**, F1
**ADDRESSED**, five focused cases passed. No other findings remain.

## Verification

Commands use `env -u NO_COLOR .venv/bin/python -m pytest`. Counts overlap: each package's
consumer checks are intentional, and the same final guard run covers WP1–WP4.

| Package | Passing checks |
| --- | --- |
| WP0 | 145 model/widget-contract tests on the integrated tree; composing screen has 72 cases and passes in WP1/WP2/WP3; shared guard 199 |
| WP1 | 180 client + composing-screen tests before review; **183 passed** in the expanded run after F1; shared guard 199 |
| WP2 | 356 coercer/cache/manager tests; 494 dependent-data + composing-screen tests; shared guard 199 |
| WP3 | 411 widget/popup + composing-screen tests; 209 AGENT/RECORD layout tests; shared guard 199 |
| WP4 | 234 doc-pinning tests; composing screen shared with WP3; shared guard 199 |

WP0 model/widget files: `tests/data/test_surf_swarm_models.py`,
`tests/widgets/test_surf_widget_contract.py`. WP1 client file:
`tests/data/test_surf_swarm_client.py`. Every composing-screen run includes
`tests/screens/test_surf_swarm_screen.py`.

WP2 core files: `tests/data/test_surf_swarm_seats.py`, `test_surf_cache_swarm.py`,
`test_surf_manager_swarm.py`. Its dependent files are `test_surf_cache.py`,
`test_surf_manager.py`, `test_surf_manager_answers.py`, `test_surf_manager_oracle.py`,
`test_surf_swarm_board.py`, all under `tests/data/`.

WP3 widget files under `tests/widgets/`: `test_surf_swarm_seat_state.py`,
`test_surf_swarm_seat_record.py`, `test_surf_swarm_agent_cards.py`,
`test_surf_swarm_agent_hero.py`; popup files under `tests/screens/`:
`test_submission_detail.py`, `test_oracle_answer.py`. Layout command:
`tests/screens/test_surf_swarm_layout.py -k "agent or record"` (336 deselected).

Doc-pinning files: `tests/test_surf_registration.py`, `tests/test_curator_registration.py`,
`tests/data/test_curator_captures.py`, `tests/data/test_curator_sybil_data.py`,
`tests/data/test_surf_captures.py`. These are the files that read the referenced docs; the wider
grep also finds many comments that merely mention CLAUDE.md. Guard command: `-m guard -q`
(10,595 deselected).

## Mutation evidence

Every mutant below made the named test fail; each edit was inverse-restored. Restored checks
passed (three manager cases and two widget cases), as did the package runs above.

| Requirement | Mutation | Test that turned red |
| --- | --- | --- |
| WP1 (M) exact busy error | Remove `error == "busy"` check | `tests/data/test_surf_swarm_client.py::test_fetch_seat_503_with_another_error_is_not_busy` |
| WP2 (M) seat isolation | Serve newest entry instead of selected token | `tests/data/test_surf_manager_swarm.py::test_seat_a_then_b_then_a_busy_keeps_a_record_and_own_timestamp` |
| WP2 (M) own timestamp | Use enclosing slot timestamp instead of entry timestamp | Same A/B/A test; B's 14:03 replaced A's 14:00 |
| WP2 (M) empty busy state | Return None instead of busy | `tests/data/test_surf_manager_swarm.py::test_never_read_seat_busy_is_distinct_from_failed[result0-busy-busy]` |
| WP3 (M) busy title | Remove suffix; separately change yellow to red | `tests/widgets/test_surf_swarm_seat_record.py::test_busy_record_title_is_yellow_and_keeps_its_own_as_of[139]` |
| WP3 (M) loading answer/panel | Change answer to `not read`; separately change panel to `not read` | `tests/widgets/test_surf_swarm_seat_record.py::test_pending_answer_and_panel_loading_only_for_eligible_rows[changes0-words0]` |

## Deferred work

The controller's full-suite run remains required before integration, as specified in the plan.
There is no merge, push or tag in this work package.

## Controller fix wave and follow-ups (2026-09-26)

The controller rebased the branch onto main `b7cb92a`; only `CHANGELOG.md` conflicted. The whole-branch
review (opus) found **C1**: `_spawn_runtime_latest` still read the old single-token slot, so the npm
check never ran and `tests/data/test_surf_manager_runtime.py` failed 3 of 14 (that file was not in
the WP2 dependent set). Fixed: the gate reads only the selected token's own entry, and a new test
covers seat isolation (a mutation that serves any entry turns it red).

Filed, not fixed:
- **F-S1: the loading word is stricter than the manager** (review M1). The widget's
  `valid_identity` accepts only lowercase `[0-9a-f]{64}`; the manager's `_hex64` also accepts
  uppercase. A row with an uppercase hash will be read but shows `not read` instead of `loading…`.
  This errs on the safe side: it never promises a read that does not come.
- **F-S2: the cap evicts by the last change, not the last read** (review M2). An unchanged finished
  read keeps its old `read_ts`, so the slot is not re-stored. As a result the 6-seat cap orders
  seats by when their data last changed, not by when they were last read. The plan said "most
  recently read". Low impact, because only a seventh seat evicts anything.
- **F-S3: job-detail fan-outs ignore a busy host** (observed live 2026-10-02 16:17–16:22, IMD
  outage). While every `/seats/{id}` and `/jobs/{id}` read on both hosts answered
  `503 {"error":"busy"}` (~3.2 s each), `/jobs` itself still answered. So both detail loops kept
  going: `SurfManager._pool_swarm` (`_swarm_executing_ids`) and the scores sweep
  (`_swarm_sweep_ids`) each call `fetch_job` per id in sequence, about one id every 6.4 s (2 hosts × 3.2 s).
  That is ~10 requests a minute to a host that asked us to wait, and the sweep stayed "still in
  flight" for the whole run. Two defects: (a) no back-off. `fetch_job` does not opt into
  `seat_busy`, so a busy answer reads as a failed row (`None`, the same as a 404) and the loop never
  stops. Apply the seat rule: stop the loop at the first all-hosts-busy answer and `mark_failed` the tier.
  (b) a false success. After a busy loop each method still stores `details` (now short or empty)
  as last-good and calls `mark_fetched`. A host that refused to answer then looks like "no
  executing jobs" until the next good read. This breaks the convention that a dead source is
  shown as unavailable, never as a real empty. Keep the prior details when the loop ended busy.
  Tier 1 (surf data module only); proof: a transport that answers busy on `/jobs/{id}` → one
  request per cycle, prior details kept, tier marked failed.

## Owner requests for the AGENT hero (2026-10-02)

Filed from chat; nothing built. Seat 420 (owner `pawai.eth`, `0xe5b1275fb926613d983da33fbfe1f331b7f64f2a`)
is the worked example. All three touch `widgets/surf/swarm_agent_hero.py`, so do F-S4 and F-S6 in one pass.

- **F-S4: STATUS says `working` while the seat works.** DONE 2026-10-02 (`WORKING_LINE`; the word yields to whole counts when STATUS is too narrow).  Today an idle seat reads
  `● online · ⚙ 0 of 3` (green word, dim counts), but a working seat shows only the counts
  `⚙ 1 of 3` (`_status_body`: `word = counts if live_state == "working"`). Owner wants the same
  shape as idle: `● working · ⚙ 1 of 3`, with the word in green and the counts after it. Keep the
  over-capacity form (`⚙ 9 working` when the oracle jobs push `working` above `maxConcurrency`):
  that becomes `● working · ⚙ 9`, so the word does not appear twice. Line 2 (`accepted MM-DD HH:MM`) is unchanged.
  Check the STATUS cell budget at the AGENT pin (139×33) before choosing the wording. Tier 1.
- **F-S5: REVIEWED becomes REWARDS (the seat's IMD rewards).** DONE 2026-10-02 per `docs/surf_agent_rewards_spec.md` (split per seat, since pairedAt).  Card title `REWARDS`; line 1 the
  IMD received (e.g. `13.87 IMD`), line 2 blank, line 3 its USD value at the current
  `imd_price_usd` (already a SURF key). Today's REVIEWED content (`1,925` / `1,711 pending`) leaves
  the hero; the pending count still shows in FEEDBACK (`1,711 queued`).
  *What counts as a reward, verified on chain 2026-10-02:* IMD (`0xD34a…63B7`, contract name
  `BridgedFP`, which is why wallets label it "FP"; the symbol is IMD) arriving at the seat owner
  in a `disperseToken` call that **surfsurf.eth** (`0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7`, surf's
  `DEV_WALLET`) makes to Disperse `0xd15fE25eD0Dba12fE05e7029C88b10C25e8880E3`.
  For 420 that is 3.1218 (09-28, tx `0x74906756…f41755`), 3.0521 (09-25, `0xdad353cf…efdf62`)
  and 7.6923 (09-23, `0xfc679221…57e55f`) = **13.8662 IMD**. Two 50/25 IMD transfers on 08-21
  came from `hisdudeness.eth`, are not rewards, and are excluded because the sender is not a payer.
  *Source (keyless):* `eth_getLogs` for the IMD `Transfer` event filtered to `to = owner`, keeping
  only transactions whose sender is a known payer. Blockscout `addresses/{owner}/token-transfers`
  is the fallback. The payer list (ops wallet via Disperse today; pool4 and "other contracts"
  later, per owner) must be a single constant, the same idea as `SURF_KEYS`, so adding a payer
  adds no new code path.
  *Open questions for the owner before the PRD:* (1) rewards go to the **owner wallet**, not the
  seat: a wallet holding several seats gets one disperse amount. Split it, or show it per wallet
  and say so? (2) After a seat changes hands, do earlier rewards stay with the old owner?
  (3) USD at today's price (as asked) or at the price when received? Today's price is what was requested.
  New contract keys (`swarm_seat_rewards_imd`, `…_usd`, `…_as_of`) and a new data read make
  this **Tier 2** (spec + plan). A failed read shows `unavailable` and must never show `0 IMD`.
- **F-S6: swap WORK and ACCEPTED, and rename ACCEPTED to `ACCEPTED JOBS`.** DONE 2026-10-02 (content swapped, columns kept aligned with the card row).  The hero row
  becomes `SEAT · ACCEPTED JOBS · WORK · REWARDS · RANK · STATUS`. The cards move whole, title and
  body together (assumed: the request reads "swap the contents" and "rename ACCEPTED", which together
  mean the two boxes trade places). Confirm this with the owner if the wording is ambiguous at
  implementation. `ACCEPTED JOBS` is 13 cells against 8 for `ACCEPTED`; check the title fits
  that box at 139 columns and re-sweep the AGENT pin if it moves. `BOX_IDS` order and the hero
  layout test move with it. Tier 1 (one dashboard; may move one pin).
