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
