# PRD — ORACLES

Status: mock preview and the final 66% requests / 34% detail split approved
by the owner on 2026-10-13; live integration authorized by the subsequent
request to continue. Tier 2: one native Surf body and its data contract.

## 1. Approved composition

Reuse the six equal nine-row rack cards from the mock and existing
`NewsHeroCard` / `HeroRecord` renderer. Preserve their shared baselines,
gray casing, dark readout and meaningful green/yellow/red status treatment.

| Outer title | Inner title | Value | Scope |
| --- | --- | --- | --- |
| REQUESTS | LOADED | Unique loaded requests | Newest bounded page |
| ASSESSING | OPEN | Status exactly `assessing` | Loaded requests |
| ATTESTED | CLOSED | Status exactly `attested` | Loaded requests |
| NO QUORUM | CLOSED | Status exactly `disagreed` | Loaded requests |
| BLOCKED | ATTENTION | Status exactly `blocked` | Loaded requests |
| NETWORKS | CHAINS | Distinct known chain IDs | Loaded requests |

Cards use the unfiltered list. A list never successfully read produces
unknown counts; a successful empty list produces zero. If any loaded row's
chain is unknown, NETWORKS is unknown. Unknown statuses remain in REQUESTS
and are visibly counted as `N other` in the coverage line. In particular,
the observed `mismatch` status is not counted as blocked or no quorum.

The left request table occupies approximately 66% of the body; the selected
request summary and expandable answer tree occupy the remaining 34%.
Questions use the available table width, with visible ellipsis when clipped.
The right summary separates result, agreement, quorum and panel target.
The table and tree scroll independently and use the available body height.

The owner's terminal is 149×45. Render the production body with live keyless
data at that size before hardening layout pins or dispatching review. Pins
are measured in the real Surf containers; the mock's geometry is a design
reference, not a production certification.

## 2. Navigation and interaction

- `Ctrl+o` opens/toggles `MODE_ORACLES = "oracles"` in Surf. The boardroom's
  `Ctrl+o` opens the same body through the existing return-context route.
  Plain `o` retains the existing board sorting behavior.
- No new app dashboard, number, `--game` value or game-select entry.
- Compose `SurfOraclesHero` and `SurfOraclesBody` once. Both accept only the
  `surf_oracles` contract keyword, plus ignored foreign dispatch keys.
- Clicking or selecting a request updates its summary and queues its detail.
  Selecting a new request immediately removes a different request's old
  answers; a pending read never leaves mismatched detail beside the new row.
- Preserve selection, local filters and tree expansion through refresh where
  identities remain present. Default to the newest visible request when the
  selection disappears or the filter excludes it. No matching rows has its
  own empty message and no unrelated selected detail.
- `/` opens local find for question, request/job identity and chain text.
  `f` cycles all, assessing, attested, no quorum, blocked and other;
  `c` cycles all and the loaded chains. These operations filter locally and
  never alter hero totals. Input typing must not trigger letter shortcuts.
- Tree branches expand/collapse by keyboard and mouse. An answer leaf uses
  the exact selected member record to open `OracleAnswerScreen`; closing
  returns to the same request and tree. A branch toggle is not an answer open.
- `r` follows guarded refresh. Escape closes local find first, then follows
  the existing Surf/back/boardroom return behavior. Preserve other modes'
  bindings, especially AGENT's `f` and boardroom's plain `o`.

Body messages are `RequestSelected(request_id)` and `AnswerSelected(row)`.
The screen routes selection into `manager.set_oracle_request(id)` without a
network await, and opens the existing modal only from a loaded answer row.
No API or data-module imports belong in widgets.

## 3. Frozen primitive payload

Export `surf_oracles` in `SURF_KEYS`, with both widget signatures exactly
`("surf_oracles",)`. Export the row-key tuples from `data/surf_models.py`;
widget-side literal copies require the existing agreement test pattern.

```text
surf_oracles = {
  state: "ok" | "stale" | "unavailable",
  read_ts: float | None,
  now_ts: float,
  partial: bool,
  rows: list[Request] | None,
  selected_id: str | None,
  detail: Detail | None,
  detail_state: "loading" | "ok" | "stale" | "unavailable" | "partial",
  detail_read_ts: float | None
}
Request = {
  id, job_id, status, chain_id, question, created_ts, updated_ts
}
Detail = {
  id, job_id, status, chain_id, question,
  panel_answer_type, panel_answer_bool, panel_figure,
  agreed, quorum, panel_size,
  member_count, members: list[Member] | None, truncated: bool
}
Member = every field in SURF_ROW_KEYS['swarm_seat_work_rows'], plus seat
```

Members use the full existing primitive RECORD row contract. Project the
relevant identity, panel and oracle fields from canonical extracted points;
leave unrelated RECORD fields None. Do not narrow members to a second
oracle-only row shape or persist duplicate enriched RECORD rows.

Request/detail IDs and job IDs are validated UUID strings. Hashes are exact
validated submission hashes; `node_key` is `oracle_assess`. Optional text is
a bounded string or None; timestamps are finite valid numeric values or
None, with future timestamps rejected according to the existing clock rule.
Counts are strict nonnegative integers or None, never bools. Chain IDs are
strictly positive integers or None; zero is unknown. Seats follow the
existing seat parser. Boolean answer and member-success fields are strict
bools or None.
Figures and typed answers remain validated strings without float conversion.
`now_ts` is injected by the manager; widgets do not read a clock.

`rows=None` means unread/unavailable, while `[]` means a successfully read
empty list. `members=None` means unread, while `[]` is a known empty panel.
`member_count` is the returned member-list length before extraction/capping;
the loaded leaf count is the number of unique accepted hashes. A source
count or panel target is never replaced by the number of displayed leaves.
Identical duplicate hashes are deduplicated; conflicting duplicates are
unavailable evidence and make detail partial. Caps or discarded malformed
members set `truncated` and detail partial. The UI states loaded/returned
coverage instead of implying completeness. A blocked request with null
members follows the existing decoder's known-empty blocked semantics.

`partial` qualifies a full 100-row page or discarded malformed/duplicate
list entries. It does not claim that a short page is a global request count.
Unknown statuses are valid rows and are not discarded. A nonempty raw page
with no valid rows is unavailable, not a successful empty list.

## 4. Reads, identity and cache

Use the existing SwarmClient and host pool. Read one newest list page with
`fetch_oracle_requests(limit=100)`. Add validated
`fetch_oracle_detail(request_id)` for the full-member detail route. Leave
AGENT's filtered `fetch_oracle_request(request_id, submission_hash)` unchanged.
Read only the selected request's detail; there is no 100-request fan-out.

The live member already supplies `tokenId`. Parse that field with the
existing seat parser and show a seat only if it is valid. No submissions
lookup is needed. Invalid/missing seat becomes `unknown seat` plus a short
submission hash; a wallet never establishes seat identity. Duplicate attempts
retain their individual hashes even when the seat is the same.

Reuse `surf_swarm.oracle_point` for each accepted exact member hash and
`enrich_panel_rows` for the widget projection. Preserve typed answers,
unknown versus false/zero/empty, unsuccessful-member reason, question and
bounded notes. Use `agreement.cluster`; do not recompute agreement. A detail
must match both the requested request ID and its expected job ID.

The ORACLES reader/cache is independent of AGENT's selected-seat oracle
cache. Retain at most eight detail entries in least-recently-used order,
each with at most 64 members. Persist bounded canonical extracted points
once per member, request metadata and seat identity, never full API/member
envelopes, unbounded notes or a second copy of enriched member rows. Reuse
the existing 6,000-byte oracle-point cap and text limits; validate persisted
entries as untrusted input and prune malformed entries independently.
TTL expiry does not delete valid last-good entries, including on cache
reload. Retain those bounded entries as stale until a successful read
replaces them or the eight-entry LRU evicts them.

- List TTL: 60 seconds. Failed list retries back off 120 seconds.
- Nonterminal detail TTL: 120 seconds. Failed detail retries back off
  120 seconds for the same selection.
- Recognized terminal detail remains reusable until its corresponding list
  row's status or updated timestamp changes or its 24-hour freshness/reuse
  TTL expires. This TTL is not a hard data-deletion limit. Unknown statuses
  do not earn indefinite terminal freshness.
- Activating ORACLES may offer one detached reader; overlapping triggers
  coalesce. Deactivation cancels its task; shutdown awaits cancellation.
- `set_oracles_active(bool)` and `set_oracle_request(id)` set state and queue
  bounded work without awaiting a network read. `get_oracles_snapshot()`
  returns the cached projection. `project_hub()` includes `surf_oracles`.
- While ORACLES is visible, the screen projects cached state once per second
  so a completed detail appears promptly. That projection is local and never
  starts extra parallel readers; ordinary mode lifecycle controls fetching.

Selection changes during an in-flight request cannot publish its result as
the current request's detail. A completed old result may populate its own
bounded cache entry only; the latest valid selection is serviced next.

## 5. Freshness and safe rendering

Successful list and detail reads have separate clocks, each captured at the
beginning of its successful request. Publish the matching normalized value
and read clock together only after successful validation. Projection time
and cache publication time never replace a source read clock. A failed refresh
retains last-good values and their old successful clock, marks them stale
and never rewrites failure as empty success. Without last-good, show explicit
unavailable or loading states. A pending detail uses the selected list row's
question/status as context and says its answers are loading/unavailable.

List content becomes stale at 120 seconds of age or a failed latest attempt.
Nonterminal detail becomes stale at 120 seconds or failure; recognized
terminal detail becomes stale when its list status/update changes, at 24
hours of age, or on failure. These ages use each source's successful read
clock, even when a new attempt is pending. Detail caps/decoding loss say
partial; when a retained partial detail is stale, stale takes precedence and
its `truncated`/member coverage remains visible. Display local `as of HH:MM`
markers for list and detail; do not extend the constrained global degraded
source title. Expired terminal detail is re-read with stale previous content.

Third-party text uses `Text` and the existing sanitizers. Address-bearing
questions, answers and notes use existing copy/explorer helpers; unknown
chains get no guessed explorer. The modal remains read-only and keyless.
No signing, wallet prompts, writes or secrets are introduced.

## 6. Acceptance

The live body preserves the approved six-card 66/34 composition, meaningful
request and answer selection, filters and exact modal identity. Tests cover
unknown/empty/false/zero separately; source failure and stale clocks; mismatch
status; full-panel versus loaded leaves; duplicate/conflicting hashes;
missing seat; typed answers; cache bounds; active-only cancellation and rapid
selection changes. All tests are offline using committed or synthetic data.

The controller shows a real keyless 149×45 production render before measured
pins, geometry documentation and final review. Verification is scoped to
touched and composing tests, relevant guards and registration/doc checks;
the full suite is outside this task.
