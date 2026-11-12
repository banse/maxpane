# Neutral value ink — 2026-11-12

Tier 2 because this spans POOL4 and SWARM; expected under 100 production lines.
Use white for neutral right-hand values in POOL4 BURN & SUPPLY/SIGNALS and SWARM
FLEET/RECEIPTS, matching COLLECTION DETAIL. Keep gray labels and headings, all
colored status/count accents, exact text, data, spacing and navigation unchanged.

Independent packages: the POOL4 implementer owns pool4u_burn.py,
pool4u_signals.py and its focused style tests; root owns swarm_fleet.py and its
style tests. No shared base or data changes. Root integrates and verifies live
149x45 renders from public observations, followed by touched/composing checks,
fast guards, documentation pins and one final scoped review. No pin changes or
layout sweep is needed for style-only changes with identical text and dimensions.
Commit the verified result locally; capture no new IMD protocol lesson.

Implementation uses `not dim` and the inherited normal `$text` color, matching
COLLECTION DETAIL. ANSI `white` was rejected during visual inspection because
the terminal palette tints it cream. Full and compact values preserve their text;
the compact ETH supply label is explicitly dim while its amount uses normal ink.

Acceptance: keyless public reads with copied operator caches, rendered at 149x45
for POOL4 MARKET and the SWARM board. Both previews showed normal white values,
gray labels/headings and unchanged colored counts/statuses. No data logic,
geometry, pin, navigation or shared renderer was changed.

Verification: 297 touched/composing cases passed; all 16 failures reproduced on
unchanged HEAD 9811749c with an identical failure-node set. These cover two older
paused-color expectations, two LAUNCHPAD composition expectations and twelve
AGENT/record harness cases. Fast guards: 131 passed. Documentation pins: 12 passed.
The compact-label fix then passed 21 focused burn/neutral-value cases.

Final review found one Important compact-label color issue; fixed in one wave.
Scoped re-review: ADDRESSED. Both theme cases pass and reverting the label color
kills both. No new review follow-ups remain. Existing baseline test failures
remain outside this visual change. IMDb capture recorded `none`.
