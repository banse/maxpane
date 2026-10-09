# SWARM TOKENS followups

This delivery is the approved version-1 offline mock dashboard. Live API
integration is a later phase; none of these values are live market data.

- Replace mock IDs with chain plus token contract identity, enumerate all
  production-chain launches, and establish pagination/completeness per source.
- Validate market-cap versus FDV, paired balances, LP position sidedness and
  token price-history coverage with keyless sources. Preserve missing values
  and source timestamps independently; never infer liquidity state from USD
  totals alone.
- Connect real contract/pool detail links through the shared explorer/copy
  helpers once verified addresses are available.
- Add live source freshness and refresh behavior after the data contract is
  backed by real endpoints. The current demo intentionally reloads a fixed
  snapshot and makes no market-data requests.

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
