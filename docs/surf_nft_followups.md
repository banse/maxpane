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
