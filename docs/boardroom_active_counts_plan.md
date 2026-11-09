# Boardroom active-count implementation plan

Tier 2: one dashboard, several data/presentation/test files. The owner authorized the correction. Expected size is below 1,000 production lines, so use one final review and no package reviews. The session owns implementation and integration; this planning task owns only this plan and the companion specification.

## Packages and dependencies

| Package | Owner and files | Deliverable | Depends on |
| --- | --- | --- | --- |
| A — filtered transport and shipped catalogue | Assigned client implementer: `data/surf_swarm_client.py`, `data/swarm_tokens_manager.py`, their tests | Optional validated Oracle status parameter; `catalogue_summary` adds internal shipped count/state/as_of from existing canonical inactive-inclusive token decoding | Spec |
| B — bounded active observations | Session: `data/surf_card_reader.py`, `tests/data/test_surf_card_current.py`, minimal committed fixtures | Resumable older-job discovery; active-request observation; fresh detail/count guards; waiting facts | A for active requests; job scan can begin independently |
| C — truthful card projection and rendering | Session: `data/surfboard.py`, `widgets/surfboard/rack.py`, their tests | Independent active request count, waiting captions, unknown-preserving Boardroom activity display, canonical SHIPPED token count | A–B |
| D — integration and evidence | Session: composing screen tests, applicable rules/follow-ups | Real-data render, focused mutation evidence, final checks and one review | A–C |

Do not concurrently edit a file owned by another implementer. Coordinate interface names before C begins. Keep native `surf_oracles_reader.py` and shared `CardValues`/`LoadingCard` unchanged unless evidence shows they are necessary; such a change must be explained before implementation.

## Implementation sequence

1. Add failing transport tests for the exact status query, validation without network access, empty-versus-failed responses, and unchanged legacy calls. Implement the smallest optional parameter extension.
2. Add offline reader regressions using the reviewed older job/request shape. The head page omits the active job; the tail or filtered request supplies it. Test bounded continuation, independent clocks, live completion and failed revalidation before implementing the reader changes.
3. Keep newest-page discovery and known-active revalidation every poll. Add one older page only while count coverage is missing. Validate descending cursors and page shape before advancing scan state. Preserve the existing detail limit and cancellation propagation.
4. Maintain the active-request observation independently from native history. Fetch one status-filtered page of at most 500. Validate status, IDs, duplicates and page bounds. Fewer than 500 valid rows proves completeness; a full, malformed or aged page exposes no exhaustive count. Fresh request job IDs can seed current discovery but cannot bypass fresh detail/global-count agreement.
5. Project WIP from the global unfinished count and verified node facts. Show working-node category when present; otherwise show waiting jobs when details are complete. Detail text explains submitted nodes. Use neutral style while waiting.
6. Project RESEARCH from the filtered observation, not counts in the recent-history view. Keep request totals separate from the unknown live-agent roster. Preserve each source's own timestamp and coverage explanation.
7. Apply the unknown-count exception locally in Boardroom. Audit both `_present_data` and the later `count_caption`/loading-caption call sites: preventing zero conversion in only the first path is insufficient. Test unknown after known zero and after positive observations as well as cold unknown.
8. SHIPPED uses the owner's selected launched-token metric. The catalogue owner exposes internal `shipped: {count, state, as_of}` using existing `_tokens(include_inactive=True)` and `_catalogue_source` evidence. Count canonical production deployments, including inactive tokens and excluding testnets, unlaunched rows and aliases. Set the inner unit to TOKENS and the inner footer to the existing rolling-24h new-launch count. Retain the outer 24H accepted-step history with its distinct meaning in hover detail. A partial catalogue cannot supply an exact total.
9. Render keylessly from fresh public data at 149×45 and show the owner before documentation hardening or final review. Preserve exact titles and existing geometry.
10. Update only affected rules/follow-ups. Run touched behavior while editing, then touched test files and composing files once. Run the required fast guards, and documentation pins if rules/docs covered by those checks changed. Compare unrelated known failures against recorded baseline.
11. Run one final independent review of the complete diff, including one check each for source completeness, cancellation and presentation of unknown values. Fix required findings, perform at most the allowed scoped re-review when production changes, then commit only task-owned files.

## Regression matrix

| Risk | Required check |
| --- | --- |
| Old executing job absent from newest page | Discover beyond head over bounded polls; refresh its detail; count waiting rather than working for a submitted node |
| Old assessing request absent from history | Supported filtered query returns it; primary RESEARCH count is independent of recent-history size |
| Real zero versus unread | Complete empty filtered page and complete zero-job evidence produce zero; failure/partial/stale produce unknown |
| Cursor bugs | Identical, increasing, malformed and missing job-history cursor values cannot certify completion; cancellation does not publish a half-complete aggregate |
| Moving active set | Reconcile new job-head identities; refresh known IDs; remove terminal jobs after fresh details; replace active-request observations only with validated filtered reads |
| Budget overflow | Page and cumulative-row limits hold; more than 24 detail candidates never become a complete 24-job count |
| Mixed source times | Old overview, old detail, failed current read and excessive clock skew all prevent current coverage |
| UI fallback | Actual composited footer keeps unknown, including after prior zero/positive data; all numeric and loading-caption paths are covered |
| Oracle semantics | Submitted answers/retained seat fields never become a live-agent count |
| SHIPPED scope | TOKENS unit matches canonical production deployments, including inactive entries; testnets, unlaunched rows and aliases are excluded; partial catalogue is not an exact total |

Prove decoder/concurrency regressions bite using the repository mutation helper: bypass the count/clock guard, drop older-page discovery, or turn unknown activity into numeric zero and demonstrate a focused test failure. Restore by inverse edit and keep unrelated workspace files untouched.

## Existing evidence and exclusions

The preceding title change had 123 passing Boardroom widget/composing tests and 39 failures independently reproduced against the prior code; fast guards had 129 passing checks and the existing SWARM TOKENS CSS failure. These are comparison evidence, not permission to ignore new failures. Do not fix unrelated colour/loading expectations, reroute seats, restart workers, sign, pay, or push as part of this correction.

## Completion evidence

Implemented and independently reviewed on 2026-11-09. The live 149×45 render showed
524 shipped production tokens, one waiting WIP job, and one assessing research
request with unknown agent count. The final review found two paging retry defects;
one fix wave added three failing regressions and corrected both. Scoped re-review:
Approved, both findings addressed. Validation and residual baseline failures are
recorded in `docs/surf_swarm_followups.md` under Boardroom active counts.
