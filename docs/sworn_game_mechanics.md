# Sworn dashboard — research and design basis

2026-10-23. Design only; no dashboard implementation approved yet. The owner
requested three ASCII proposals with MaxPane cards before implementation.
This work is independent of the parked C64 and house demonstrations.

## Sources inspected

- Current website: <https://swornbyswarm.sites.imd.fun/>. Inspected in a separate
  headless Playwright session: Home and Catalog, including the rendered hive.
- Repository: <https://github.com/identity-md-launches/launch-2404-renderer-composer-registry>.
- Renderer, HiveData, Registry, Types, Catalog and README at owner-supplied commit
  `c4ff3238390fc51962fb67e86affc20cf418126e`.
- Existing MaxPane deployment evidence: `surf_loading_review_2026_10_23_report.md`.
- Current graphics architecture review: ReaderRuntime, DashboardScreen and the
  installed optional textual-image 0.14.2 implementation. No production edits.

The website footer identifies Ethereum Registry
`0x0da2679000ea5380d1361cc3cca7d4e8c881f766`, Renderer
`0x3039eaf3b979759c77a2a3fc62850f9534162c3b`, and Composer
`0xf564dd76bd081554170c5e0b78144abfb39f7061`.
These match the owner's requested Registry. Before implementation acceptance,
independently read its helper getters and verify source/runtime binding.

The local aidude sworn-site addresses and the repository's DEPLOYMENTS.md still
describe launch 2362. They are historical references, not configuration for this
dashboard. Do not choose a deployment by project name or copy those addresses.

## Card and fact semantics

- ERC-721 cards are transferable. Facts belong to `claimantOf(tokenId)`, not
  `ownerOf(tokenId)`. Show both identities separately when they differ.
- `tokenOf(wallet)` locates the card originally minted by a claimant. It is not
  an inventory of all cards currently held by that wallet.
- `totalSupply` advances at mint; the inspected implementation has no public
  burn route. Confirm that implementation binding before enumerating IDs.
- The catalog has 25 facts across 13 families. A cell shows the highest held
  tier, except PID, which shows the lowest verified ordinal ID.
- Direct facts read live before mint and freeze at mint. Oracle and community
  facts can update later. Absence of an accepted oracle fact is not proof that
  the underlying proposition is false.
- `traitsOf`, `verifiedSpecsOf`, `verified` and `specOf` provide details.
  `hasTrait` establishes an individual fact; the picture is not a credential.
- Read images through the authentic Registry's `tokenURI`. Renderer.tokenURIOf
  accepts an arbitrary registry and must not establish identity by itself.
- Metadata includes only the first 32 community IDs, while its count and
  `verifiedSpecsOf` can cover more. Do not use metadata list length as total.
- The site's home artwork is explicitly synthetic. It is a visual reference,
  not a card owned by a real wallet or a live collection statistic.

## Artwork and terminal fidelity

The renderer emits a static 1000×1000 SVG with 13 flat-topped hexagons, Swarmed
in the center, tier clipping from below, opacity zones, green family colors,
white rarity dots, community rings and an outer progress path. It contains no
visible text, scripts, animations or external artwork. Geometry is in HiveData;
the source is MIT licensed.

Prefer the actual SVG rasterized at the target pane's pixel dimensions. Cache by
SVG content hash and render size. A fallback can derive colored character cells
from the same raster, preserving one artwork source. A separately ported native
renderer is possible but adds equivalence work and can drift.

Kitty graphics is the initial high-fidelity candidate; Ghostty needs an actual
compatibility render. Apple Terminal needs character fallback. Small panes lose
thin details even with graphics. Every proposal therefore allows a fullscreen
card view. Preserve square pixel aspect using actual terminal cell dimensions;
never impose C64 dimensions, palette or text-mode restrictions.

Installed textual-image 0.14.2 requires Python >=3.12, while MaxPane supports
>=3.11. Its synchronous resize/encoding, import-time terminal probing and known
cleanup defect prevent simply importing its widget into production. Choose the
adapter/dependency after the rendering direction is selected.

## MaxPane integration constraints

Reuse ReaderRuntime and DashboardScreen for cached initial paint, reader/UI
separation, 30-second polling while visible, non-overlapping reads and suspension
when leaving. Fetch visible cards and selected detail first; never render every
tokenURI on each poll. Decode and rasterize off the UI thread. Key caches by
chain, Registry and token ID; metadata updates invalidate artwork without
changing token identity. No minting, wallet signing or paid requests in MaxPane.

Use existing hero-card frames, address copy/explorer helpers and centered loading
footer. A wallet or token search must remain usable during reads. Card art stays
readable while supporting details scroll independently. Do not invent market
prices, rankings, rarity scores or collection-wide fact totals.

Pending: choose one of the three proposals and confirm the preferred terminal.
Then write the selected PRD and ask the project-planner agent for work packages.
