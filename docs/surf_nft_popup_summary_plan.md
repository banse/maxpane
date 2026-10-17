# NFT popup and README summary implementation plan

Implements [the approved spec](surf_nft_popup_summary_spec.md), 2026-10-17.
Tier 2, expected under 1,000 production lines. One final review; no task reviews.
All owners share the checkout and must preserve other owners' changes.

## Package A — data and selected README lifecycle

Owner: data implementer. Parallel with B after the payload above is frozen.

Own `data/surf_nft_models.py`, `data/surf_nft_manager.py`,
`data/surf_nft_client.py`, `analytics/surf_nft.py`, an optional narrowly scoped
`analytics/surf_nft_readme.py`/`data/surf_nft_readme.py` helper, and corresponding
data/analytics tests and new README fixtures. Do not edit UI files or the persisted
NFT evidence cache.

1. Add the exact `nft_readme` payload/signature and projection identity guard.
2. Add validated keyless GitHub README acquisition and deterministic excerpt
   extraction. Reuse bounded transport rather than another HTTP client.
3. Add selected-repository cache and separate owned task to `SurfNftManager`.
   Preserve `select(identity)` and expose `get_readme()` as a cheap passive getter.
   Include work in loading/cancel/drain/close without making `_offer()` block
   catalogue polling simply because a README is busy.
4. Cover repository/ref normalization, malformed/oversized responses, hostile
   prose, missing/no repo, cache reuse, identity guarding, independent completion,
   cancellation/late completion and zero hidden/BOARDROOM fetches. Inject transport
   and clocks; demonstrate concurrency/decoder test sensitivity with targeted
   mutation checks.

## Package B — selected panels, table action and popup

Owner: UI implementer. Parallel with A; use the frozen primitive payload with
offline fixture data while A is in flight.

Own `screens/surf_nft.py`, new `screens/nft_detail.py`,
`widgets/surf_nft/{detail,table,summary,__init__}.py`, and
`tests/widgets/test_surf_nft.py`, `tests/screens/test_surf_nft.py` plus a new modal
test if useful. Also owns only the NFT CSS block in `themes/minimal.tcss`; do not
change other theme sections. Do not edit data/models/analytics, shared popup/base
widgets or other boards. Parent owns cross-cutting registration/address-sweep tests
if changes prove necessary.

1. Split current detail formatting without duplicating evidence logic; retain
   basics in COLLECTION DETAIL and render all following sections in a
   `RecordDetailScreen` subclass with copied selected row/source/coverage context.
2. Add a trailing `»` action for every real launched/build row. Keep address/copy
   interactions independent. Enter and icon open the correct record snapshot;
   closing restores selected table focus. Empty rows have no action.
3. Stack `NftSummary` below the basic detail, add its PANELS adapter and render
   source-labelled excerpt using safe text/address helpers.
4. On highlight/select: set manager selection, show cached summary immediately,
   and use the existing loading tick plus `get_readme()` to repaint promptly when
   its payload changes. Never perform I/O in the message handler or widget.
5. Offline tests assert composited basics-only right pane, full popup sections,
   clickable icon/keyboard/close behavior, address-copy isolation, cached summary
   and correct filtered selection. Measure the added icon's actual column budget;
   avoid silently adding horizontal overflow.

## Package C — integration, live view and hardening

Owner: parent/controller; depends on A and B. Own the two plan/spec documents after
planning handoff, any `tests/address_sweep/builders.py` / address coverage changes,
and `docs/surf_nft_followups.md`. Coordinate screen pin edits with B after handoff.

1. Integrate and run focused changed-behavior tests. Capture fresh public live NFT
   view and popup at 149×45 with isolated temporary caches; show owner before
   final layout documentation or review.
2. Measure relevant width/height boundaries and edit pin/comment evidence only if
   required by actual render. Check whole columns/icons, basic panel and summary
   headings, popup scroll/focus, address links and no outer clipping.
3. Run touched and composing test files once with isolated HOME, four workers and
   worksteal. Also fast guards; docpins for updated docs; registration mount checks
   if bindings/key surface changes; affected address sweep when address cells move.
   No full suite. Include targeted mutation proof for new decoding/concurrency and
   changed pins; leave production restored after each mutation.
4. Final whole-change review under CLAUDE.md's reviewer contract, followed by one
   coordinated fix wave and a scoped re-review only for production fixes. File
   Minor-only residuals in existing NFT followups.
5. Commit only intended files locally; no push. Report actual tests and any known
   baseline failures separately. Do not create a plan workspace or unrelated docs.
