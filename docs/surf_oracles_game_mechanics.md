# ORACLES — sources and mechanics

Research date: 2026-10-13. The owner approved the fictional Textual preview,
including the final 66% request-list / 34% selected-detail split, then asked
to continue with live integration. ORACLES is a new body of the existing
Surf dashboard. It does not add an app dashboard or game registration.

## What the body answers

Which recent oracle requests were loaded, what question each asks, what
outcome the request reports, and how its individual submitted answers relate
to the reported consensus. Agreement, required quorum, target panel size and
the number of returned answers are separate facts.

The answer tree must retain the identity of each submission. A seat can make
multiple submissions, so a seat number, wallet or job alone cannot identify
an answer. The existing AGENT RECORD implementation already resolves exact
submission hashes and interprets typed answers; ORACLES reuses that decoder.

## Verified repository patterns

- `data/surf_swarm_client.py` owns the keyless host pool, pacing and failure
  handling. `fetch_oracle_requests(limit=100)` reads the bounded list;
  `fetch_oracle_request(request_id, submission_hash)` reads one filtered
  member for AGENT and must keep its current contract.
- A separate validated `fetch_oracle_detail(request_id)` will read a request
  with full members. The current detail serves each member's `tokenId`, so
  this body needs no separate submissions-to-seat lookup.
- `data/surf_swarm.py::oracle_point` extracts bounded member facts, validates
  exact request/job/hash identity and uses `agreement.cluster` for membership.
  `enrich_panel_rows` produces the existing `panel_*` / `oracle_*` row fields.
  Each projected member carries the full existing
  `SURF_ROW_KEYS['swarm_seat_work_rows']` RECORD row contract plus `seat`;
  unrelated fields remain None. Do not recalculate cluster membership from
  equal answers or price distance.
- `widgets/surf/_oracle_answer.py` formats existing answer types, consensus
  and panel wording. `screens/oracle_answer.py::OracleAnswerScreen` opens an
  already loaded exact answer and performs no fetch.
- `widgets/surf/news_hero.py` supplies the rack renderer. The approved layout
  and interactions are implemented in `scripts/surf_oracles_demo.py`.
- Surf's WorkReader demonstrates detached active-only polling, cancellation,
  last-good caching and primitive projection through SurfManager. ORACLES
  needs its own cache, independent of AGENT's selected-seat oracle records.

## Current public evidence

The controller captured a keyless read in `/tmp/oracles-live-probe.json` at
2026-10-13 13:31:21 UTC. Its 100 creation-descending request rows contained
66 `attested`, 33 `disagreed` and one `mismatch`, across chain IDs 1 and 4663.
These are observations, not runtime constants or global protocol totals.

List rows carry request id, status, question, chainId, answerType, jobId and
creation/update timestamps. They do not contain the full member answer tree.
The first request's detail contained four members with a target panel size
of five and quorum four. This proves that returned member count cannot stand
in for panel target. Its agreement object carries `agreed`, `answer`, `figure`
and `cluster`; each member carries `ok`, `answer`, `reason`, `wallet`, `tokenId`
and `submissionHash`. The observed answer type is `uint256`.

The old mock's four known statuses are not exhaustive: the live list contains
`mismatch`. Preserve raw normalized status and keep unknown statuses visible;
do not silently relabel them as attested, no quorum or blocked. BLOCKED counts
only `blocked`; all other unknown statuses appear in the visible `other`
coverage count. Validate member `tokenId` with the existing seat parser; no
wallet inference or separate submissions request is necessary. Chain IDs
must be strictly positive integers; zero is unknown, not a network.

## Bounds and failure semantics

Read one newest page of at most 100 requests. This body describes loaded
records and never claims to list every request or all open requests. Load
detail only for the selected request; do not fan out over the list. Keep a
bounded cache of at most eight request details and 64 extracted members per
detail, never raw envelopes or unbounded notes.

List polling is due after 60 seconds; nonterminal detail is due after 120
seconds. A cached terminal detail remains fresh/reusable until the
corresponding list row changes or its 24-hour freshness TTL expires. This
is not a deletion deadline: retain bounded last-good entries across
persistence, marked stale, until successful replacement or eight-entry LRU
eviction. Selecting a request queues
detached work; no screen or
widget event handler awaits a network read. Deactivation and shutdown cancel
owned work, and overlapping triggers cannot create duplicate readers.

A failed read retains last-good values and their original successful clock.
Read clocks identify the beginning of their successful request, not a later
projection/publication. List content is stale after 120 seconds or failure;
nonterminal detail after 120 seconds or failure; terminal detail after list
invalidation, 24 hours or failure. List failures back off for 120 seconds.
No previous read means unavailable, not zero. A successful empty list means
known zero requests; an unread member list is not a known empty panel. List,
selected detail and optional seat resolution can fail independently. A
failed seat lookup must not erase an otherwise valid answer. Show an unknown
seat with a short submission hash instead of inferring identity from wallet.

The PRD freezes the normalized contract, caps and status mapping. The plan
assigns disjoint file ownership and requires a real keyless 149×45 render
before layout pins, geometry documentation or final review.
