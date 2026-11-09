# Boardroom active-count correction

Status: implementation authorized by the owner on 2026-11-09. The owner selected launched tokens for SHIPPED.

## Problem and evidence

At commit `29028809`, Boardroom displays global unfinished-job totals beside counts derived from only the latest 100 jobs or requests. Older active identities fall outside those history pages. Unknown node counts become zero through numeric and caption fallback paths.

The 2026-11-09 public capture found one executing job, `31a2cf4d-24f7-4fe8-8a31-f9437c520182`, created November 5. Its sole node was submitted, with no live assignment. Request `2f058f1e-ffd6-4b68-a779-fcf0a775b035` remained assessing. Neither identity appeared in the newest 100 history rows; the supported `status=assessing` request query returned the request. Replaying that capture yielded `node_counts=None`, followed by a painted `0 working` caption. These dated values are regression evidence, not constants for production.

## Required behavior

| Card | Primary metric | Supporting activity |
| --- | --- | --- |
| WIP | Unfinished jobs from the fresh global executing count | Verified working-node category when present; `N waiting` for unfinished jobs with complete details and no working node; otherwise an explicit unknown caption |
| RESEARCH | Distinct currently assessing requests from an independently verified filtered read | Agent count only where existing complete live-panel evidence supports it; otherwise unknown |
| SHIPPED | Canonical production token deployments, including inactive deployments | Inner unit `TOKENS`; inner footer is the existing rolling-24h new-launch count; online agents cannot stand in for shipped work |
| SWARM | Existing fleet statistics | No metric change required |

Keep the owner-approved outer titles SHIPPED, WIP, RESEARCH and SWARM. An unfinished job is not proof of active execution. Waiting work uses neutral activity styling; positive working-node evidence can activate the WIP frame. Unknown activity stays unknown after a failed read and after a previous known zero. Preserve real observed zero.

The WIP waiting count describes jobs without a working node, not agents. Hover detail explains submitted/awaiting-processing state separately from working nodes. Do not infer live Oracle competitors from submitted members, retained seats, or request count. SHIPPED deduplicates aliases and excludes testnets and unlaunched entries through the existing canonical token catalogue. Its outer 24H accepted-step history is retained, with the distinct unit stated in hover detail.

## Decisions and trade-offs

| Approach | Benefit | Cost / reason |
| --- | --- | --- |
| Increase the newest-history page only | Small change and finds this incident | Merely moves the omission boundary; rejected as the completeness strategy |
| Refresh all historical details | Straightforward exhaustive reasoning | Unbounded I/O, rate pressure and hidden-dashboard work; rejected |
| Filter active requests; resume bounded job discovery and refresh known active identities | Finds old active work while retaining current budgets | A cold start can remain unknown across polls; selected |

Use the existing API client, Boardroom reader, pure card projection and local card presentation. No new service, generic state framework, global numeric fallback change, layout pin, or persisted top-level model key is required. The native ORACLES history view keeps its existing list/cache semantics; Boardroom's active-request observation is separate.

## Coverage and freshness contract

1. Refresh the newest job page and known active identities. When verified executing coverage is missing, resume at most one older page per poll with a strictly descending creation cursor. Candidate IDs alone cannot suppress discovery: their details may be terminal. Retain the cursor across successful incomplete polls, committing advancement only after detail validation succeeds; failed or cancelled detail reads retry the same page. Bounded reads are not a full-history refresh loop.
2. Seed candidate job IDs from validated active Oracle requests. Deduplicate by canonical job ID. Preserve the existing 24-detail ceiling; exceeding it is incomplete coverage rather than permission to claim zero.
3. A complete node summary still requires successful fresh detail reads, valid node facts, a fresh overview, compatible observation clocks, and exact agreement between freshly executing details and the overview count. Finding the expected number of IDs alone is insufficient.
4. Read assessing requests through the supported status filter, one page of at most 500 per poll. Only a valid page shorter than 500 proves a complete count. A full page, duplicate/conflicting identity, wrong status or malformed row leaves the count unknown. Fresh validated request job IDs can seed job discovery without certifying its coverage.
5. Failed, malformed, oversized, conflicting, nonadvancing or cancelled reads cannot advance coverage to complete. A checkpoint cannot survive a changed scan identity/filter. Newest-head failure cannot be repaired by a successful old tail page.
6. Apply freshness independently to job nodes and active requests. Request job IDs may seed discovery only while their source is less than 60 seconds old. Do not replace unknown current activity with stale retained numeric presentation.
7. Zero is valid only with complete, fresh evidence. Unknown or incomplete counts remain `None` internally and render as a blank or dash caption on the affected Boardroom cards.

Internal reader observations may add waiting/research facts passed through `current_work`; they must not widen `SURFBOARD_CARD_FIELDS`, widget signatures or persisted overview schemas. Card models retain their existing `primary`, `secondary`, `status`, `detail` and source-clock fields.

## Acceptance evidence

- The old active job/request capture produces WIP `1`, a waiting caption, and RESEARCH `1`, with unknown agent count preserved.
- New active work, completion, failure, stale reads, cancellation and cold starts do not fabricate zero or resurrect removed work as current.
- Work outside the first history page is found over bounded polls. Missing or malformed coverage remains unknown.
- SHIPPED uses the complete canonical production-token catalogue and the TOKENS unit. Its count never falls back to online agents or a partial recent launch list.
- Composited tests and a keyless production-data render at 149×45 confirm full labels and captions without moving layout pins.
- One final branch review follows implementation and the real render. The change is expected to remain below 1,000 production lines; no package review is required.
