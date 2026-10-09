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

Approved with no Critical or Important findings. One Minor test-quality item:
bind `data/swarm_tokens_models.py::WIDGET_SIGNATURES` to actual widget
`update_data` signatures in an agreement test when that test file is next
touched. The existing mounted PANELS agreement covers the screen/widget seam,
but mutating the unused model mapping survived the named contract tests.

Native-style revision review: the compact editor transition after horizontal
scrolling was reproduced and fixed, with a regression covering that route.
The scoped re-review marked the Important finding ADDRESSED.
One Minor UI followup remains: filter-specific footer hints repaint on the
next refresh rather than immediately when the editor opens. Apply/Reset
buttons are visible, and filter shortcuts already work while it is open.
