# SWARM TOKENS followups

Live integration now supplies production-chain catalogue identity, quotes,
observed history, recent trades, source freshness and explorer links. The
standalone mock demo remains available for offline design work.

Known limits and future work:

- Provider indexing and history are partial; retain explicit unavailable states.
  A future source may improve coverage, but must not seed fabricated candles.
- New/24h and age use launch-record time. A separate verified deployment-time
  source could refine that meaning without guessing from the first market trade.
- New chain IDs require verified production/network/explorer mappings.
- Detail sources fill progressively in bounded batches; no aggressive full-sweep
  refresh or duplicated launch-evidence collector is introduced.

## Final review

Initial review approved with no Critical or Important findings. The Minor
signature-agreement followup is now addressed in
`tests/widgets/test_swarm_tokens.py::test_model_widget_signatures_match_the_renderers`:
the declared model mapping is checked against actual widget update signatures.

Native-style revision review: the compact editor transition after horizontal
scrolling was reproduced and fixed, with a regression covering that route.
The scoped re-review marked the Important finding ADDRESSED.
One Minor UI followup remains: filter-specific footer hints repaint on the
next refresh rather than immediately when the editor opens. Apply/Reset
buttons are visible, and filter shortcuts already work while it is open.

The later compact-layout request removes LP STATE from the main table and uses
its space for a 20-character sparkline. Liquidity states remain available in
Newly Launched, Best Plays markers, filters and token details. The extra
dashboard heading and selected-token footer are removed; applied context and
overflow hints share ALL TOKENS' heading. The native status bar retains the
mock-data label. Newly Launched and Best Plays share neutral column-header
ink and a blank row before data. The measured layout boundary is now 145×32.

Compact-layout review approved with no findings. Verification passed: 31 focused
tests, 123 fast guards, and all four row/column boundary mutations detected.

## Live verification

Actual keyless data rendered at 149×45 with the approved geometry and partial
quote/trade coverage visible. Catalogue, version joins, source scheduling,
market identity/cap semantics and history gaps have targeted mutation proofs.
The live phase retains the existing filter-footer Minor item above.

The live review found and resolved two provenance issues: catalogue revisions
now clear old detail/pool/position facts and withhold mismatched cached rows;
market caches and in-flight replies are bound to the expected launch pool, with
immediate discovery when that identity changes. Scoped re-review marked both
findings ADDRESSED. All four regression cases and all four associated mutation
checks passed. The earlier market/catalogue/source mutation checks also passed.

Focused integration checks passed across the data, projection, widget and screen
files. The existing rack color tests require NO_COLOR to be unset (55/55 passed
with colors enabled); fast guards passed 123 cases and registration 81 cases.
No full-suite run or push was requested.

## Panel-order and liquidity revision — 2026-10-10

Heroes now precede Activity / Newly Launched / Best Plays, with All Tokens below.
Newly Launched shows paired balances; position states remain in filters, Best
Plays markers and details. The liquidity hero sums current filtered IMD and ETH
balances separately; `≥` marks incomplete known totals and `--` unknown totals.

A real 149×45 render and the boundary sweep preserve the 145×32 pin. Verification:
51 focused tests and 123 fast guards passed. Seven mutants were killed: both
width/height pin directions, mixed currencies, stale balances and unknown-as-zero.
Final scoped review approved with no findings; the additional hero-order
mutation was killed and the CSS agreement check passed.

## TOKENS hub card — 2026-10-10

The hub now uses LAUNCHED digits from the retained production-token catalogue.
Its `x new` footer and green border share the SWARM title's one-hour detected
launch-news window. Catalogue polling from the hub schedules no market reads.
A live 149×45 capture showed 117 launched and 1 new (SPALACE #1210).

Final review approved with no findings. Focused data, widget and composing
screen checks passed, including the 57-case layout file; 123 fast guards passed.
Four mutation checks verified expiry, scheduling, count and digits. Existing
followups above remain; this card introduces no additional review followups.

## Hub title and supply revision — 2026-10-10

The token card is now LAUNCHES with TOKENS above its digits. POOL4 uses IMD PRICE;
PROTOCOL uses IMD BURNED and a percentage of global remaining supply. The live
149×45 capture showed 33,279 burned and 0.47% of supply. Canonical Base FP
totalSupply backs the bridged IMD supply; the existing keyless Base reader fetches
both supply and decimals, with an independent ten-minute source envelope.

Review identified a bounded-ratio defect for cumulative burns exceeding remaining
supply; it is fixed, with a regression and mutation proving percentages above
100% work. Scoped re-review approved. The four initial source/denominator/cache
mutations were also detected. No new unresolved findings.

## SURFBOARD, LEADERBOARD and LAUNCHPAD faces — 2026-10-10

SURFBOARD now previews the latest successful surfsurf.eth announcement across
three lines. Its 24-hour announcement age alone controls green/fresh ink; unique
replies and owner answers from the same window form the footer. Older text
matches empty-slot ink. LEADERBOARD uses the canonical rank-one NFT and accepted
jobs; LAUNCHPAD shows native coin digits and turns green only for new 24h launches.
Narrow footers drop grouping/optional words, and extreme accepted counts use
compact notation with the exact count retained in detail.

The actual 149×45 render showed an older announcement with 7 new replies,
leader #527 with 4,176 accepted jobs, and 208 coins with 0 new. Touched and
composing checks passed 301 cases, the fast guards 123, and six behavior mutants
were detected. Review found a wide-Unicode wrapping defect; original-character
cell measurement fixes it. The regression and reverse mutation cover both
149×45 and 140×36. All 122 affected rendering/address checks passed after the fix;
scoped re-review marked the finding ADDRESSED. No new unresolved findings.

## Card reconciliation and spacing — 2026-11-12

Cards and rankings now include retained observations with their original source
clocks, matching ALL TOKENS. Active token polls refresh missing/stale liquidity
for verified tokens in bounded batches of three, with the existing failure backoff
and catalogue identity guard. Idle summary scrollbars are hidden; ALL TOKENS moves
up one row and keeps one blank row above the footer. See
[tokens-card-consistency-20261112.md](tokens-card-consistency-20261112.md).

Three existing test failures were reproduced on unchanged HEAD `57e7bbc5`:
`test_liquidity_hero_displays_imd_then_eth_and_marks_partial_totals` still expects
`-- ETH` despite the shared card fallback convention; both parametrizations of
`test_actual_pending_token_refresh_animates_shared_footer_then_clears` expect a
private footer timer although the screen owns the shared animation phase.
These test expectations remain follow-ups; this change does not alter shared
card placeholders or loading animation.

Final review approved with no blocking findings or new follow-ups. Verification:
217 targeted tests passed (the three reproduced baseline failures above remain),
131 fast guards, 12 documentation pins and eight independent review checks passed.
The live render and six functional mutation checks are recorded in the plan.
