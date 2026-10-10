# PORTFOLIO offline mock implementation plan

Approved: ASCII option 1, Portfolio overview, 149×45, 2026-10-10.
Status: mock complete; the owner approved the rendered design with P/L on
2026-10-10. The next phase is described in `portfolio_live_implementation_plan.md`.
Authority: `CLAUDE.md` Tier 2 and `portfolio_PRD.md`. Target **under 1,000 new
production lines** through reuse (approximately 250 data/analytics, 550 UI and
100 integration). Use one final feature review; no per-package review.

## Frozen primitive contract

Package A publishes key tuples and `WIDGET_SIGNATURES` in
`data/portfolio_models.py`. Existing SWARM TOKENS contracts stay unchanged.

Snapshot: existing `tokens`, `activity`, `as_of`, `is_mock` plus
`wallet: str|None`, `agents: list[dict]|None`. `is_mock` is always true in this
phase. `wallet='sample'` is an explicit standalone preview label, not an address.
Token records retain SWARM TOKENS `TOKEN_KEYS` and these additions:

| Field | Meaning |
|---|---|
| `held_quantity`, `claimable_quantity` | Nonnegative float or `None`; claimable is ready quantity only |
| `claim_state` | `ready`, `locked`, `claimed`, `none`, or `unavailable` |
| `balance_state`, `claim_read_state` | `ok`, `stale`, or `unavailable` |
| `held_cost_usd` | Nonnegative USD basis of the remaining held position, or `None`; synthetic in the mock |
| `locked_quantity`, `claimed_quantity`, `unlock_at`, `claim_reason` | Optional cached detail; nullable quantities/time and explanatory string |

Use optional existing `market_state`, `history_state`, `liquidity_state` and
source clocks to exercise degraded records. Agent records need only `id: str`
and `online: bool|None`; offline does not revoke claims. No fabricated addresses.

```python
demo_snapshot(wallet=None) -> dict  # detached deterministic records
DemoPortfolioManager(wallet=None)
    set_wallet(address) -> bool
    async fetch_and_compute() -> dict
    async close() -> None

project_snapshot(snapshot, *, chain='all', query='', lp_state='all',
                 assets='all', sort='value') -> dict
```

The manager accepts the effective wallet from its caller, never reads config or
uses network/cache clients. `set_wallet` reports whether identity changed.
No wallet means an explicit empty population, not an unavailable source.

The pure projection includes positive holdings OR positive ready claims before
filters, then reuses the SWARM TOKENS projection for market panels and liquidity.
Assets are `all`, `held`, `claimable`; sort is `value`, `claimable`, `symbol`,
`change`, `newest` (existing `volume` may be retained for reuse). Stable identity
breaks ties; missing numeric values sort last. Inputs remain untouched.

Projected tokens add `held_usd`, `claimable_usd`: nullable indicative valuations.
A known zero quantity gives zero without a quote; unknown/stale positive
quantity or price gives `None`. Stale cached quantities stay visibly qualified;
an unverified claim must never look freshly confirmed ready.

Projection keys: `wallet`, `tokens`, `metrics`, `claimable`, `gainers`, `losers`,
`activity`, `agents`, `as_of`, `is_mock`. `claimable` contains positive ready
claim rows from the same filtered IDs. Metrics:

```text
total
held_value held_known held_total
claimable_value claimable_known claimable_total
agents_total agents_online
liquidity_imd liquidity_eth liquidity_partial
pnl_usd pnl_percent
```

`*_known`/`*_total` count priced/current vs positive-quantity token positions,
separately for held and ready claims. Empty known population totals zero;
wholly unavailable valuation is `None`; partial known totals show coverage.
Agent metrics describe the whole selected wallet; `None` association/presence
remains unknown. All other panels derive from identical filtered IDs.
The owner's P/L revision replaces the fourth hero. Unrealized P/L sums current
held values minus remaining-position cost, excluding claims. Missing/stale
held value or missing cost makes both fields unknown. Zero cost leaves the
percentage unknown. Only explicit mock cost bases are supplied in this phase;
live cost-basis reconstruction remains a separate requirement.

Widget signatures: `PortfolioHero(metrics)`, `PortfolioTable(tokens, as_of)`,
`ClaimableTokens(claimable)`, reused `BestPlays(gainers, losers)` and
`TokenActivity(activity, tokens)`. Widgets import no `data/` modules.

## Package A — offline records and projection

Owner: data implementer. Owns only:

- `maxpane_dashboard/data/portfolio_models.py`
- `maxpane_dashboard/data/portfolio_demo.py`
- `maxpane_dashboard/analytics/portfolio.py`
- `tests/data/test_portfolio_demo.py`
- `tests/analytics/test_portfolio.py`

**A1 — fixtures and lifecycle adapter (30–60 minutes).** Test first, then reuse
the SWARM TOKENS synthetic market builder with wallet quantities/claims and
agent association. The default four-token example matches the approved ASCII
values. Test variants cover locked/claimed exclusions, unpriced holdings,
stale/unknown/zero and 44 rows to exercise scrolling. Acceptance: deterministic detached data, no fabricated addresses,
no network, no-wallet state, wallet switching and static refresh.

**A2 — pure projection (30–60 minutes).** Reuse market selection/aggregation,
adding only portfolio membership, valuations and asset/value filters.
Acceptance: deduplicated membership, offline-agent entitlement retained, no
locked/claimed ready value, no quantity/price failure converted to zero,
coherent filtered populations and coverage, deterministic sorting and no input
mutation. Supply named tests and the frozen keys to Package B.

## Package B — widgets, screen and integration

Owner: root/session. May start against the frozen contract in parallel with A;
integration depends on A. Owns all UI/shared changes, including:

- `maxpane_dashboard/widgets/portfolio/` (renderers, filter/detail adapters)
- `maxpane_dashboard/screens/portfolio.py`
- `maxpane_dashboard/demos/portfolio.py`
- `maxpane_dashboard/screens/surfboard.py`
- `maxpane_dashboard/widgets/surfboard/rack.py`
- `maxpane_dashboard/themes/minimal.tcss` (exact scoped CSS mirror)
- Portfolio widget/screen tests and relevant composing hub tests
- Required dashboard-screen/address/refresh guard registries and narrowly
  necessary shared helper hoists; no second owner of these files

**B1 — native view (30–60 minutes).** Use small subclasses/adapters around
SWARM TOKENS screen/table/filter/detail, its feed and movers, and the panel bases
used by BASE TRADING. Add four portfolio heroes, wallet/filter context and
claim rows in the approved order. Acceptance: actual 149×45 render, all ten
table fields, 20-character price chart, clear MOCK DATA, native colors and no
invented portfolio history or duplicated shared renderer implementations.

**B2 — wallet and interaction (30–60 minutes).** Reuse wallet prompt persistence,
shared address actions and draft filter controls. Keep source wallet identity
with every snapshot; clear old rows on change and reject mismatched results.
Acceptance: wallet set/cancel/switch (including startup environment override),
shared copy/explorer actions, filter apply/reset/cancel, stable selection,
cached details, static refresh and close-before-back Escape behavior.

**B3 — hub/demo integration (30–60 minutes).** Activate existing PORTFOLIO hub
card as a mock destination. Standalone uses a sample label or empty wallet and
must never instantiate production startup managers. Acceptance: module entry
opens offline, hub return works, saved wallet is injected, no new top-level
game number and no Portfolio network access. Guard registrations reflect only
the new nested screen; do not weaken existing guards.

## Render, verification and final review

Root shows the running offline mock at 149×45 before measuring layout pins,
writing their evidence or dispatching review. This phase's explicit mock-first
requirement replaces the usual live render. Do not ask for another design gate.

Then verify composited output at 149×45 and smaller scrolling sizes, measured
boundary hints and address actions. Add mutation proof only where the repository
requires it (for example, a new measured pin). Use meaningful behavior tests;
avoid tests that merely repeat implementation. Tests block network and real
clipboard/browser calls. No live data acquisition is needed.

While editing, run focused affected cases. Once integrated, root runs touched
test files and composing files, the fast non-mounting guard set, and relevant
registration/address checks. Do not run the full suite. Root coordinates one
final scoped whole-feature review, one fix wave and a scoped re-review only
for production fixes; Minor-only findings go into followups.

No subagent commits or child-agent dispatch. Every owner leaves unrelated
working-tree changes untouched. This plan is complete when the approved mock,
actual render and named verification are delivered; live Portfolio is separate.

## Verification evidence

The actual 149×45 Textual render was shown before hardening. Widths 138–150
and heights 28–38 measured a 145×35 minimum for the fixed chrome; the boundary
tests still pass with the revised P/L hero. All fields remain reachable below
the minimum, and a 44-token fixture scrolls inside the table.

Five mutation checks were killed: width and height pins changed by one in
either direction, and disabled wallet-generation protection. Mutations were
restored byte for byte. The P/L tests first failed without the metric, then
passed for gains, losses, filtered positions, unknown/stale values and zero
cost. No test used live wallet data. Live follow-ups are in
`portfolio_followups.md`.

Final validation: 185 touched/composing cases passed across the original run
and the color-enabled rerun of the two color-sensitive files; 124 fast guards,
81 app registration checks, 12 doc pins and three Portfolio address/dispatch/
refresh checks passed. No full suite was run. The one final review approved
the mock without findings; its additional claims-exclusion mutation was killed.
