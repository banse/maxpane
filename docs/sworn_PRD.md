# Sworn Card Explorer PRD

Approved direction, 2026-10-23. Owner: “yes 1 with 3, maybe 3 in popup then”.
This selects proposal 1 as the main dashboard and proposal 3 as its large
detail popup. It supersedes the pending-selection wording in the earlier
[proposals](sworn_dashboard_proposals.md) and [research](sworn_game_mechanics.md).

## Purpose and scope

Display actual Sworn cards as faithfully as the terminal permits, with readable
facts and evidence beside them. This is an independent MaxPane dashboard,
`--game sworn`, appended after the existing nine choices. Existing defaults
stay unchanged. C64 and house demonstrations remain parked.

The dashboard is keyless and strictly read-only. No wallet connection, mint,
signature, transaction, trait request, or paid operation is included. Synthetic
website art is never used as a live card. There are no invented prices, rarity
scores, rankings, or collection-wide fact totals.

## Main view: Card Explorer

- Four shared MaxPane hero cards: COLLECTION / MINTED; FAMILIES / SELECTED;
  FACTS / SELECTED; COMMUNITY / SELECTED. Only collection supply is global.
  Selected family and catalog-fact denominators are 13 and 25 for the verified
  source version; counts come from accepted data, never artwork interpretation.
- A bounded card list at left, selected square artwork in the center,
  and selected-card facts at right. Rows provide a trailing `»` detail action
  following existing MaxPane record tables. Keyboard selection updates the
  artwork without blocking input.
- Search accepts a token ID or claimant address. `tokenOf(address)` is an
  original-claimant lookup, not the current holder's complete NFT inventory.
  Invalid input and a confirmed unminted claimant have distinct readable
  outcomes; neither gets a fabricated issued card.
- Card rows may show already-known family counts; an unread row must not show
  zero. Browse IDs cheaply and load selected detail first. Do not fetch every
  tokenURI merely to populate list statistics.
- Show original Claimant and current Holder separately. Every visible address
  uses shared copy/explorer helpers. A source/metadata action and the row action
  open the detail popup. Shared footer keeps the loading indicator centered.

The conceptual proposal's `f filter` did not define a filter dataset or query.
Do not add an unbounded collection scan to implement it. Token/claimant lookup
and a page around the selection are the initial navigation contract; richer filtering is
a follow-up requiring defined coverage.

## Detail popup: Wallet and Facts

Use the existing MaxPane large-popup treatment. The left pane gives the same
card artwork more room. The right pane lists wallet facts and community facts,
with selected-fact explanation and available accepted evidence identifiers or
block window. Scroll details independently; preserve the artwork's square
aspect. Closing returns to the same list selection and cached main view.

Facts belong to the original claimant even after transfer. Direct facts freeze
at mint; oracle/community facts can change afterward. A missing accepted fact
is not a claim that the proposition is false. Community count uses the reported
count or complete accepted-ID source, never a metadata list length truncated to
32. Fetch complete accepted IDs for complete detail, or label a bounded list as
partial. Evidence may be absent
for direct facts; do not invent an oracle proof or apply one quorum to all kinds.

## Acquisition and identity

Use Ethereum chain 1 and the owner's Registry
`0x0da2679000ea5380d1361cc3cca7d4e8c881f766`. Check the current website manifest
and independently read Registry helper bindings. A mismatched manifest must not
silently switch to an older or unrelated Registry. Record source commit and
observation block/time with snapshots. Use pinned, vendored read-only ABIs.

Acquire artwork from the authentic Registry's `tokenURI`, decode its metadata
and SVG, and use one raster source for both terminal graphics and character
fallback. Bound decoded sizes and reject unsupported external SVG resources.
Metadata and artwork conversion happen on the reader side, never during paint.

Reuse ReaderRuntime and DashboardScreen. Cache by chain, Registry and token ID.
On entry, display cache immediately and refresh; poll at 30 seconds while the
dashboard is visible. Skip overlap and elapsed ticks. Leaving stops acquisition.
Retain observation times on failed refreshes; missing data is `None`, never a
fabricated zero. The shared loading footer represents reads. Selection changes
must not let a slower previous response replace the newly selected card.

## Rendering and compatibility

Use shared hero frames, neutral labels, MaxPane background and the SVG's actual
colors. Preserve pixel aspect; no C64 palette, resolution or cropped framing.
Prefer prepared terminal graphics where supported. Always provide a character
fallback derived from the same raster, and report its fidelity honestly.
Python 3.11 remains supported. Capability probing must not occur while Textual
owns input. Do not import a probing image library from widget modules.

## Acceptance

1. `--game sworn`, menu selection and dashboard cycling open the same view.
2. Live keyless selected-card reads bind to the expected deployment; a transfer
   fixture proves holder and claimant remain separate.
3. Actual SVG colors/geometry survive raster conversion; main and popup images
   use the same source. No placeholder artwork masquerades as a minted card.
4. Cache-first reopen, visible-only polling, selection races and failed reads
   have deterministic tests without network, clipboard or wall-clock sleeps.
5. Show the live main view and popup at the owner's 149×45 terminal size before
   layout hardening and final review. Inspect resize, dismissal and fallback.
6. Run touched/composing tests, registration/doc guards and required mutation
   proofs. One final whole-change review; a local commit records actual evidence.
