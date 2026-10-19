# CR round 1a5b8604: BOARDROOM and NFT Explorer

Date: 2026-10-19. Status: implementation authorized; batch already claimed.
Batch: `1a5b8604-198f-4ceb-8748-43a3cbefe333`.

## Scope and decision

Complete these four MaxPane CRs before changing the CR website. This is Tier 2
because BOARDROOM and NFT Explorer are both affected. The expected change is
under 250 production lines and must stay under 1,000: two disjoint implementers,
no package reviews, then one final review. Follow CLAUDE.md and the
terminal-layout skill; the project's superpowers exclusion applies.

Use the existing renderers, projected NFT records and site-link actions.
An alternative would add a new site-resolution service or data-contract key;
that creates another discovery path without adding facts. Keeping the existing
contract limits this change to presentation and avoids additional network reads.

## Accepted behavior

1. `0e10f4f1-089c-4f5f-a38d-0efbe49728a4`: BOARDROOM's NFTS card moves the
   observed `N build · M open` counts from the inner box footer to the outer
   card footer. Counts update with the snapshot; missing values remain dashes,
   known zero stays zero. Keep collection digits and navigation. Do not display
   partial-coverage text on this card.
2. `bdbe90d2-0a83-457e-8830-c6d9dae9ffe1`: move the live `NFT EXPLORER` controls
   line into the unused top header space. Remove its previous one-line slot and
   following blank line so the content panels below it start two rows earlier.
   Preserve stage, chain, filter text, loading state, and resize updates. Reuse
   the top blank space rather than introducing an extra row above the heroes.
3. `2cd1e5cd-5744-47c9-b6aa-d20986cf1035`: omit generated `‹ widen` notices
   everywhere in the NFT view, including the header and collections title.
   Keep fitting, ellipses, scroll access and the existing vertical-overflow
   indication. Do not strip matching words from third-party names or prose.
   This owner exception overrides the skill's usual visible-width-marker rule;
   layout tests must inspect geometry and actual columns directly.
4. `dff7c0c0-8965-4915-8c2a-9f51cfa5617a`: append one clickable site glyph after
   the collection name and its existing copy glyph for rows with a valid linked
   site. Reserve its cells within the existing collection column; retain the
   full contract copy action and chain-correct name link. The site glyph opens
   the linked canonical site and does not select a different row or open the
   NFT detail popup. Missing/invalid sites show no glyph. If multiple eligible
   sites exist, use the first valid site in the existing newest-first order.

## Site evidence and contract

The controller completed a keyless live `nft._cycle` using a temporary cache;
`/tmp/nft-coverage-preview/snapshot.json` contains 23 deployed collections.
Six distinct collections have normalized valid sites, satisfying the requested
greater-than-three condition:

| Collection | Site label |
|---|---|
| IMDenza | `imdenza-the-swarm-set-in-motion` |
| Visual Identity Genesis | `vimd` |
| Courier Companions | `moon` |
| Swarm Cats | `loom` |
| Hive Wars Conqueror | `nectar` |
| Pulse Drone | `pulse` |

The same discovery data contains seven matched workflow IDs for VETERANS,
Visual Identity Genesis, Swarmlers Agents, Courier Companions, Swarm Cats,
Hive Wars Conqueror, and Pulse Drone. This is dated evidence for enabling the
feature, not hardcoded production data or a filter-dependent runtime threshold.

`data/surf_nft_rules/catalog.py:related_records` already follows explicit
`contractsJobId` / `frontendJobId` and publication/job links; it returns sites
ordered newest first. `links.py:normalize_site` already normalizes them. The
existing row `sites` list is the complete interface for this change; no new
models, sources, manager calls, or widget-to-data imports are needed.

Use `widgets/address.py:site_text` and `widgets/explorer.py:SITES` for validated
label/legacy-ENS link metadata. Preserve that metadata on the glyph and reuse
`_CollectionTable._on_click`'s existing `is_explorer_click` dispatch. The widget
rules explicitly prohibit opening raw `site.url`; do not add a second URL path.

## Work packages and ownership

### WP1 — controller: BOARDROOM card

Own only `maxpane_dashboard/widgets/surfboard/rack.py`,
`tests/widgets/test_surfboard_rack.py`, and any necessary focused assertions in
`tests/screens/test_surfboard_screen.py` / `test_surfboard_layout.py`.

- Start at `meter_text` (NFT currently returns empty `Text`),
  `SurfboardCard.render` (currently builds the inner `secondary` counts), and
  `test_nft_card_preserves_collection_digits_and_build_mint_counts`.
- Write the failing composited-output regression: dynamic counts occur on the
  outer border only; the inset footer is empty; digits and no-partial behavior
  survive. Include known zero, missing count, update, and narrow card sizes.
- Move the existing formatting to the outer footer with the smallest change;
  fit count text without introducing invented values or moving the hub pin.
- Run the touched tests while editing. Check the existing BOARDROOM boundary
  and resize cases once the implementation is ready.

### WP2 — NFT implementer: header, width notices and site glyph

Own only `maxpane_dashboard/screens/surf_nft.py`,
`maxpane_dashboard/widgets/surf_nft/table.py`,
`tests/screens/test_surf_nft.py`, and `tests/widgets/test_surf_nft.py`.
Also own the NFT-specific block in `maxpane_dashboard/themes/minimal.tcss` to
keep production CSS consistent with the screen's `DEFAULT_CSS`; reserve that
shared file to this implementer during WP2 and leave other theme blocks alone.
No edits to WP1 files, shared address/explorer modules, or data modules.
Report a defect outside this ownership to the controller instead of fixing it.

- Start at the screen's `DEFAULT_CSS`, `compose`, `_chrome`; the table's
  `build_row`, `refresh_title`, and `_CollectionTable._on_click`.
- Write failing tests for top-header placement, the two-row content movement,
  and absence of generated width notices under long/CJK filter captions and
  narrow windows. Keep direct viewport/frame/column checks in existing sweeps.
- Write a composited glyph-order test and click test with a mocked browser
  opener: collection/name link, copy glyph, then site glyph. Cover long/CJK
  names, unknown chain, no site, invalid label, multiple sites, and resorting.
  The copy target must remain the full collection contract. No real clipboard
  or network access in any test.
- Implement with existing row fields and helpers. Do not gate glyphs on how
  many rows survive the current search/filter; the live prerequisite is met.
- Keep header behavior when filtering and resizing; inspect all mounted NFT
  widgets for inherited generated width notices without altering shared bases.
- Run focused tests while editing. Leave final pin measurement and its `#:`
  documentation until after the controller shows the real live render.

WP1 and WP2 may run in parallel because their files are disjoint. Both workers
must preserve existing user changes and each other's work.

### WP3 — controller: integration and completion

Depends on WP1 and WP2. Own this plan, follow-up records, any needed NFT sweep
fixture extension in `tests/address_sweep/builders.py`, and final measurement
updates after the NFT implementer hands back its files.

- Render keyless live BOARDROOM and NFT Explorer at the established owner size
  149×45 and show the output before hardening or reviewer dispatch.
- Sweep actual NFT geometry on both sides of measured width/height boundaries;
  do not infer a new row pin merely by subtracting two. Update the local pin
  and adjacent `#:` block only if the measurement changes it. Prove a changed
  pin test fails for both too-small and too-large mutations with `scripts/mutate.py`.
- Run the complete touched widget/screen test files, the NFT address sweep
  (`tests/screens/test_address_icons_everywhere.py -k surf_nft`), and
  `.venv/bin/python -m pytest -m 'guard and not mounts_app' tests`.
  Run relevant data-link fixture tests only if investigation changes data code;
  no full suite and no registration-mount suite unless scope reaches those surfaces.
- Request one final review using CLAUDE.md's reviewer contract. Address Critical
  and Important findings in one fix wave; scoped re-review only if production
  changed. File Minor residuals in the relevant existing follow-ups document.
- Complete the claimed batch only when all four CRs are resolved, recording the
  implementation summary, exact verification evidence, and the real commit hash
  via `--commit`. Code changes must be committed before batch completion.

## Deferred next stage: CR website

Only after MaxPane completion, implement the separately authorized website
changes: save multiple notes before batch submission, and sidebar navigation
that preserves unsaved text without reloads. Keep the button label exactly
`Codex Queue`. This plan neither implements that work nor allows it to delay
or replace any of the four current MaxPane CRs.
