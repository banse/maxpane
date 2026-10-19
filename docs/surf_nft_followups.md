# NFT Explorer delivery evidence and follow-ups

Implementation: 2026-10-17, approved combination of proposal 1's collection/detail
layout, proposal 2's IDMD/mint filters and proposal 3's explicit sources.

## Detail popup and README summary — 2026-10-17

The right column now stacks collection basics and `SUMMARY (github README.md)`.
Every catalogue row ends in `»`; that action and Enter open all former sections
from MINT ROUTES onward in the shared RECORD popup frame. Closing with Space,
Escape or X preserves the table cursor. Read-only source links and independent
address-copy actions work in the popup and summary.

README acquisition is selected-only, keyless and independent of the chain cycle.
The 32-entry repository/ref cache survives dashboard revisits in this process;
successful/missing reads have a 600-second TTL, failures back off 120 seconds,
and one request has a six-second budget. Retained text survives failed refreshes.
Only a canonical linked repository and optional valid commit may supply root
README.md. The 1,600-character excerpt excludes code, badges and navigation-only
links; it does not assert mint availability or wallet eligibility.

A fresh public capture at 149×45 reached Sinopia plus its pinned README excerpt
in 6.4 seconds from empty temporary caches (24 NFT-client requests). Both the main
view and popup were shown before hardening. Capture files are under
`/tmp/maxpane-nft-popup-live/`; this is a bounded cold-start observation, not a
claim of full catalogue completion. The navigation-only line found in that live
README was then removed from the excerpt parser with a fixture regression.

The measured screen boundary remains 146×33. The `»` uses the existing final
table column's budget. Collection basics are capped at half the right column,
so long holder/project facts scroll without pushing the summary below it.
Popup and summary use their own scroll regions.

Verification: 238 affected/composing tests passed, plus 126 fast guards,
12 documentation pins and both NFT address-sweep sizes. Width and height pin
mutations in both directions, a hidden-summary overflow mutation, decoder and
cancellation mutations all failed the intended regressions and were restored.
Final review found one Important issue: an invalid first repository suppressed
a later valid GitHub source. The fix selects the first valid entry in source
order without downgrading an invalid pin; both regressions failed before the fix,
the manager file passed all 30 tests afterward, and scoped review marked it
ADDRESSED. The actual Sinopia navigation mixes anchor and relative-file links;
that shape now has a failing-before/passing-after fixture regression, and all
33 README/client cases passed after its correction. No new residual findings.

## Delivered behavior

BOARDROOM's NFTS card replaces PROTOCOL in the existing rack. `n` or card
activation opens the nested Explorer; `p` opens the retained native PROTOCOL
body. Input fields keep their typed letters. Filters (`f`), search (`/`), stage
(`b`), chain (`c`), sort (`o`), selection and reopen reuse retained observations.
The Explorer has no global game-menu slot and no scanner subprocess or sibling
checkout dependency.

Sources are public Swarm indices/details, the shared job memo, public Ethereum
and Robinhood RPCs, and narrowly validated explorer/pinned-source reads. The
adapted rules retain all 22 reviewed contract identities and the utility,
factory-child, constructor-reference and related-token families. File hashes
and provenance are in `data/surf_nft_rules/SOURCE_MANIFEST.json`; the inspected
source checkout had no Git HEAD or scanner license declaration, so neither was
invented. Packaged JSON resources are checked in the built wheel.

## Measured live evidence

Live captures use an empty isolated HOME, actual managers/HTTP clients and the
production stylesheet at 149×45. They run at most four bounded cycles, then stop
acquisition before rendering. Other BOARDROOM readers are held passive during
this NFT-specific capture, explaining their neutral placeholders.

The first public-network capture made 46 physical requests in 58.6 seconds. It
found 180 launches and 408 candidate contract identities, but published no
collection: job backfill consumed the deadline before background chain work.
This was shown before layout hardening. A named regression reproduced starvation;
chain proof now receives an early budget slice even without a selected row.

The fix-specific cold capture made 77 physical requests over four cycles in
50.8 seconds. Per-cycle owned attempts/reserved shared credits were 12/2, 18/6,
18/6 and 18/6; logical RPC operations were 7, 14, 14 and 11. It published one
independently confirmed Robinhood collection, Sinopia, while mint/IDMD facts
remained unknown. The Explorer and NFTS card both displayed partial coverage.
These are bounded first-start observations, **not a full-catalog performance
claim or current guaranteed collection counts**. Public endpoint failures can
leave details incomplete; subsequent admitted cycles resume work.

NFT geometry measured at 146×33; BOARDROOM remains 143×37. Width/height boundary
tests and five UI mutations cover both understated and overstated pins, plus
accidental refresh from cached filtering. Actual populated captures and request
logs are retained outside the temporary plan workspace under
`/tmp/maxpane-nft-live-20261017-fixed/`.

## Verification and review

Task reviews cover N0–N5 separately. N4/N5 approved without findings. Source
review found malformed job-template handling, corrupted history cursors, cache
byte retention, incomplete chain refresh replacing confirmed evidence, archive
error propagation and constructor-child provenance on refresh. Each has an
owner fix and a named regression; all six findings are ADDRESSED in their
scoped re-reviews.

Source fix mutations prove malformed-template isolation, cursor recovery,
byte-cap persistence and last-good proof retention. Definitive negative chain
observations remain able to remove a collection; missing reads cannot do so.

The full touched/composing run (isolated HOME, NO_COLOR unset, four workers)
finished with **822 passed + 43 subtests** in 47.20 seconds. Its nine failures
are existing Portfolio behavior, reproduced on both the current tree and an
untouched `9e2894d8` archive with the same nine named nodes run serially
(3.60/3.49 seconds). The NFT address sweep passed both cases. Fast guards passed
125 cases; the added CSS block initially broke the Portfolio EOF agreement,
then all four affected NFT/Portfolio/token CSS guards passed after moving the
block unchanged. The final fast-guard rerun passed **126 tests** in 14.14 seconds;
final documentation pins passed **12 tests** in 16.05 seconds. Required app registration:
79 passed, one separately reproduced baseline failure below. The wheel builds
offline and contains the NFT screen and all three rule JSON resources. Feature
Python files also parse under the Python 3.11 grammar.

The final whole-feature review found two additional retention combinations:
changed runtime plus unavailable receipt, and deferred factory rediscovery
overwriting a child's good proof. The single final fix wave covers evidence
and record-only cache states, invalidates contradicted runtime interpretations,
and preserves pending children's prior observations and enrichment eligibility.
Both final findings are **ADDRESSED**. All 12 scoped regressions passed; both
final mutants were killed and restored. The final affected manager/cache/Surf
integration/NFT-screen files passed **151 tests in 7.87 seconds**. The wheel was
rebuilt after these fixes and its packaged manager verified byte-for-byte.

Review reports, mutation definitions/logs, composing results and layout
measurements are archived in `/tmp/maxpane-nft-review-20261017/`. The temporary
implementation workspace is removed at delivery. No push or release is made.

## Remaining limitations / follow-ups

1. **Partial cold discovery:** four bounded cycles observed one deployment with
   incomplete mint details. Before changing scheduling/budgets again, measure
   longer empty-cache runs and compare physical requests, confirmed counts and
   completed routes. Navigation itself remains cache-only.
2. **Unreviewed dependency runtimes:** StarterClaim, HiveWars and GameRegistry
   do not have reviewed dependency runtime hashes in the inspected rules. Their
   getter observations may be retained, but stronger dependent mint claims stay
   unknown. A future rule update needs independently checked deployed code and
   fixtures; no documented or guessed hash is a substitute.
3. **Coverage limits:** public-history termination does not establish private-job,
   unsupported-factory or nonstandard-NFT completeness. Factory/event scans and
   byte/count retention caps continue to qualify coverage explicitly.
4. **Previous unrelated baseline failures:** see
   [surf_data_loading_followups.md](surf_data_loading_followups.md). Replacing
   the PROTOCOL card removes its obsolete card assertions; it does not claim to
   repair unrelated native protocol calculations.
5. **Existing outage-banner test:** the required app-registration checks report
   79 passes and one failure in
   `tests/test_surf_registration.py::test_a_full_outage_renders_explicit_states_not_zeros`.
   It still expects the warning banner removed by the prior Surf display override.
   The same assertion fails on an untouched `9e2894d8` archive (2.08 seconds).
   Update that test when its existing source-display contract is next maintained;
   this feature does not restore the removed banner.
6. **Existing Portfolio failures:** five behavior nodes in
   `tests/screens/test_portfolio.py` fail on the clean baseline as well:
   `test_holdings_table_precedes_supporting_panels_and_claims_stay_separate`,
   `test_live_claim_only_wallet_has_zero_held_value_and_empty_portfolio`,
   `test_no_wallet_prompt_persists_and_repaints_selected_address`,
   `test_live_coverage_sources_and_details_never_show_demo_values`, and
   `test_wallet_change_discards_late_snapshot_and_refreshes_new_identity`.
   Four live width/height parameters of
   `test_measured_portfolio_boundary_preserves_columns_and_advertises_scroll`
   also fail. Existing PortfolioHero updates report a missing `render_box`.
   The feature does not alter Portfolio behavior; its CSS block agreement passes.

No floor price, secondary volume, wallet portfolio, personal claim simulation,
signing or paid job flow is included.

## NFT refresh fairness — 2026-10-18

The retained live catalogue had 18 deployed collections, 15 with deployment-only
proof and no getter readings, competing with 981 candidate addresses. Static
selected/reviewed/unseen ordering repeatedly displaced unfinished enrichment;
its ten-minute pinned context could expire before completion.

The NFT manager now retains one background inspection until completion, with
unfinished known collections ahead of routine refreshes. A separate resumable
proof allocation continues discovering new collections. Selection gets a bounded
eight-request/three-second slice; discovery and probes also have time slices.
All slices retain the same cycle counters and original 24-HTTP/256-RPC/fifteen-
second network admission budget. Stuck/restarting work yields with backoff;
full stage-cache admission cannot spin. Proof-only evidence without a retained
stage is immediately eligible for enrichment. Existing reader ownership,
30-second polling, cancellation, cache retention and proof-only BOARDROOM reads
remain in place. No model keys, endpoints, mint rules or screen layout changed.

Live verification used a temporary copy of the public NFT cache and real keyless
reads. Over eleven consecutive bounded cycles (296.58 seconds, without adding
30-second waits), the scheduler completed ArtifactsPiece, refreshed IMDenza and
upgraded BMC Illuminati Pass from proof-only to 38 getter readings: mint `open`,
IDMD `no`, supply `0/500`. It then advanced VisualIdentityEdition2. These are
observations, not a latency guarantee or a complete catalogue refresh. The
149×45 real-data render was shown before review. The user's cache was untouched.
Artifacts: `/tmp/maxpane-nft-loading-fixed/` and
`/tmp/maxpane-nft-loading-fixed.log`.

Verification: 231 touched/composing data, reader, analytics, widget and screen
tests passed; 126 fast guards passed. Four rollback mutations were killed and
restored byte-for-byte: sticky completion, failed-stage backoff, stage-cap
admission and time slicing. No full suite was run. Logs:
`/tmp/maxpane-nft-loading-tests.log`, `/tmp/maxpane-nft-loading-guards.log`,
`/tmp/maxpane-nft-loading-mutations.log`.

Measured follow-up (resolved by the polling audit below): `_publish()` took 6.026 seconds for this retained catalogue;
cache preparation took 0.139 seconds and snapshot projection 0.007 seconds.
Profile the repeated catalogue joins before optimizing them. The network
admission deadline does not bound synchronous projection/persistence time.
Mint/IDMD values without reviewed deployed semantics correctly remain unknown.

Final independent review: **Approved, no findings**. Seven targeted regressions
passed; the reviewer independently killed all four named mutations and restored
the files byte-for-byte. The inspection/cancellation seam and the BOARDROOM
proof-only boundary were checked. No reviewer changes remain.

## NFT CPU work and shared poll admission — 2026-10-18

The [dashboard polling audit](dashboard_polling_audit.md) resolves the repeated-join
performance follow-up. UUID/commit references are now prepared once per projection.
Five identical-input comparisons reduced publication CPU work from 5.885 to 0.802
seconds, with identical catalogue/state values and JSON order. Three real reader/UI
cycles took 6.150, 6.513 and 5.884 seconds; only one cycle ran at a time.

Shared reader admission now includes manager-owned background work, coalesces busy
UI refresh requests before they cross threads, and discards elapsed 30-second ticks.
Opening/reopening still bootstraps immediately, including when README work starts
in the activation setter. Partial/final snapshots and retained cached navigation
remain available. Source TTLs, budgets and enrichment fairness are unchanged.

## NFT catalogue discovery admission — 2026-10-18

Fresh Swarm pages were reaching the cache, but 985 contract candidates competed
without NFT/new-launch priority. Five live baseline cycles left the deployed
count at 18 and job details at 86. Launch-detail reads repeatedly spent the
remaining allowance before linked jobs could reserve their two-host reads.
Reviewed factories also entered the proof-only path: their negative NFT interface
result returned before their child-discovery adapters could run.

The manager now orders probes by reported NFT intent and launch number, without
using that text as deployment evidence. Existing reviewed factories receive full
inspection and the collection refresh TTL; retained factory work keeps priority
after reopening. Newly discovered child placeholders enter full inspection
without waiting for the ten-minute negative-probe TTL; completed negatives still
back off. Background inspection leaves four HTTP slots and two seconds
for discovery, with one linked job offered before more page/launch reads. Total
limits remain 24 HTTP attempts, 256 RPC calls and fifteen seconds of network
admission per cycle. Existing proof gates, endpoint pools, source rules, UI layout
and single-flight polling are unchanged.

Real keyless reads against an isolated copy of the user's cache increased the
deployed count from 18 to 20: NightFrogs and imd/place seasons. Job details advanced
from 86 to 99; previously unfilled Veterans and Keel Notes details also populated.
The final twelve-cycle sample took 6.92–9.23 seconds per cycle. These diagnostic
cycles ran consecutively without thirty-second waits; this is not a complete
catalogue latency guarantee. A 149×45 Matrix render with NightFrogs selected was
shown before review. The user's active cache was not modified.

Swarm Cats was discovered in the reviewed Loom factory registry but remained
excluded because its creation-receipt proof failed in normal sliced scans.
Subsequent direct reads and an isolated full factory inspection succeeded; the
normal-cycle recovery was not verified. Follow up by capturing the receipt
observation across sliced replay before attributing this to the provider. Its
unverified row stays excluded. No source or origin gate was weakened.
Mint/IDMD fields still require their own reviewed evidence and may remain unknown.

Verification: 161 touched/composing tests and 126 fast guards passed. Eight restored
mutations were killed: discovery priority, factory full-inspection admission,
retained-factory rank, linked-job reservation, linked-job time allowance and
factory refresh TTL, plus child initial admission and full inspection. No full
suite was run. Live captures, render and test/mutation logs are under
`/tmp/maxpane-nft-discovery-audit/`.

Independent review approved the original diff. The scoped correction for initial
child admission, negative backoff and preserved proof gates was marked ADDRESSED;
the reviewer independently killed its two mutations. Minor test follow-up:
`test_discovered_child_is_inspected_before_waiting_for_negative_probe_ttl` disables
`_publish`, so its final empty-row assertion does not itself exercise projection.
Use a real projection when that test is next maintained; the chain origin gates
were checked separately and remain unchanged.

## NFT card coverage footers — 2026-10-19

Approved scope: remove coverage notices from the outer footer of Boardroom's NFT
card and all six NFT dashboard cards in every source state. Keep the existing
active-loading indicator. Preserve counts, inner headings, data states and
coverage/provenance in the dashboard header, popup and tooltips.
No data, pin or layout change. Keep shared `LocalSourceHeroCard` unchanged;
an NFT-only subclass clears its footer while retaining its local-time tooltip.

Single controller-owned package: `widgets/surfboard/rack.py`,
`widgets/surf_nft/hero.py`, `tests/widgets/test_surfboard_rack.py` and
`tests/widgets/test_surf_nft.py`, plus the composing assertions in
`tests/screens/test_surfboard_layout.py`. Under 30 production lines; one final review.
Verify composed blank borders through updates, resize and source-state changes,
with existing counts/provenance and other card footers preserved.

Actual-source 149×45 previews were shown before hardening at
`/tmp/nft-coverage-preview/{nft,boardroom}.png`; an isolated cache copy and a real
NFT cycle supplied 23 collections. All 235 affected/composing cases passed
(75 unchanged cases, then 160 after updating the three obsolete footer
expectations); the 128 fast guards passed. Final review: Approved, no findings.
Both rollback mutations were killed by the named NFT hero and Boardroom tests;
the reviewer restored production files byte-for-byte. Missing versus zero counts,
pending/unavailable blank footers at 132 and 149 columns, and other cards' partial
notices passed focused checks.
