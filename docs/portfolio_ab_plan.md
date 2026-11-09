# Swarm portfolio A/B implementation plan

Tier 2. Owner approved A overview plus B as a native popup on 2026-11-09.
The contract and accepted source trade-off are in `portfolio_ab_spec.md`.
No additional design approval is needed to implement that selected behavior.

## Packages and ownership

| Package | Owner / files | Depends on |
| --- | --- | --- |
| Specification | Planning agent: these two `portfolio_ab_*` documents only | Approved A/B design |
| Data | Data implementer: `data/swarm_portfolio_models.py`, `data/swarm_portfolio_client.py`, `data/swarm_portfolio_manager.py`, `analytics/swarm_portfolio.py`; corresponding data/analytics tests and committed fixture directory | Frozen contract |
| UI | UI implementer: `screens/swarm_portfolio.py`, `widgets/portfolio/overview.py`, `widgets/portfolio/inspector.py`; corresponding widget/screen tests | Frozen contract; data can be stubbed during TDD |
| Integration | Controller: `screens/surfboard.py`, `data/surf_manager.py`, `themes/minimal.tcss`, README, rules, composing/registration/address guards and follow-ups | Data + UI interfaces |

Workers are not alone and must preserve other owners' edits. Changes crossing an
ownership boundary are reported to the controller instead of edited concurrently.
No worker commits or spawns another agent.

The likely production diff is approximately 900–1,200 lines after reuse; this is
an estimate, not a line budget. It includes validation, lifecycle and every A
section, so do not omit behavior to fit under the review threshold. If the frozen
implementation estimate remains above approximately 1,000 lines, follow the
project's package-review plus final-review path. If the controller narrows the
concrete diff below that threshold through actual reuse, record the revised
estimate before implementation and use one final review without package reviews.

## Sequence

1. Freeze the primitive model names from the specification and give both workers
   the same contract. Capture one real public scan result with provenance;
   derive small offline variants for failure and state transitions. Do not start
   additional remote scans merely to create fixtures.
2. Data worker writes failing tests for source wallet validation, malformed/
   conflicting identities, claim readiness, common-token allocations and missing
   values. Add the smallest keyless scan client and normalized decoder. No copy
   of the full aidude scanner, hardcoded values or optional key paths.
3. Implement a retained manager with injected clock/transport, one in-flight
   request, explicit fresh refresh and bounded status polling. Preserve source
   `as_of`; changing wallets clears display state immediately. Prove cancelled
   and delayed A→B→A results cannot publish. Expose the ordinary dashboard seams
   (`wallet`, `set_wallet`, `fetch_and_compute`, `get_snapshot`, `is_loading`,
   active-view/close methods) rather than inventing a second scheduler.
4. Implement pure filtering, canonical token aggregation and monetary metrics.
   Sum upstream allocated values once; utility TVL, NFTs and eligibility remain
   outside total. Ready/locked/pending/unknown reward buckets remain separate.
   Preserve quoted-context caveats when filtering a token's locations.
5. UI worker builds A with existing rack/card helpers, shared `PanelBase` and
   native tables. Reuse common formatters, address helpers, status bar and filter
   patterns. `SwarmPortfolioScreen` inherits `DashboardScreen`, declares `PANELS`
   and uses inherited lifecycle/refresh behavior. New read-only data has no need
   for command buses, repositories, generic adapters or other MVC ceremony.
6. Implement B by subclassing `RecordDetailScreen`, preserving the standard
   border, maximum width, focused scroll body, X and Space/Esc close hint. Include
   the chosen token's location breakdown, valuation context, relationships and
   evidence. Snapshot data once on open; close restores the source table's row.
7. Controller adds retained `SurfManager.swarm_portfolio_manager(wallet)` and
   closes it with the manager. Boardroom `o` opens the new screen with the current
   saved wallet and advertises `o portfolio`. Keep `p` Protocol and legacy
   portfolio classes/tests unchanged. Mirror screen CSS in the production theme.
8. Render against the captured live public result at 149×45 and show overview
   and popup before hardening. Resolve owner-visible layout issues in one batch.
   Then sweep actual content boundaries, add measured `#:` blocks and complete
   the address/explorer sweep. Unknown, empty and long-string cases must remain
   reachable without silently truncated financial values.
9. Run touched behavior while editing. Before commit, run touched files and
   composing integration files whole with isolated cache/home, required fast
   guards, registration mounts for the new binding, and doc pins. Do not run the
   full suite. Compare pre-existing failures against the documented baseline.
10. Conduct the required independent review(s), one fix wave and one scoped
    re-review for production fixes. File Minor/residual findings in the existing
    portfolio follow-ups doc. Controller commits only task-owned files; no push.

## Regression matrix

| Risk | Evidence |
| --- | --- |
| Wrong wallet or delayed response | Invalid identity rejected; A→B→A and suspended-view response cannot publish |
| Shared token double-counting | One token held/staked/rewarded produces one canonical identity and exact allocated sum |
| Claim overstatement | Future unlock locked; stake reward pending; no eligibility evidence unknown; none silently ready |
| Missing valuations | `None` remains unknown; valid 0 remains 0; partial sum labelled and not an exact total |
| Source failure | Running/error/malformed response retains same-wallet timestamp or unread state; fresh flag not repeated |
| Filter disagreement | Cards, allocation, holdings and rewards agree on selected population; utility TVL excluded |
| Popup behavior | Enter opens native modal; Escape/Space/X close; original selection/focus restored; no fetch on open |
| Hostile/long strings | Literal markup stays literal; Unicode and amount columns fit; safe links only |
| Addresses/chains | Copy icon and correct explorer; unsupported chain cannot inherit Ethereum link |
| Geometry | Real 149×45 render; in-situ boundary sweep; no hidden financial content at narrow/short sizes |
| Existing dashboards | Boardroom `p` unchanged; `o` reachable; legacy portfolio contract untouched |

Use `scripts/mutate.py` on decoder/generation/aggregation and measured-pin cases
to prove the named tests fail, then restore byte for byte. Reviewers receive the
verbatim CLAUDE.md contract and run named checks, never whole directories/suites.

## Explicit exclusions

No transaction execution, new contracts, cost basis, P/L, portfolio history,
native-ETH wallet census, guaranteed withdrawal/liquidation claims, full local
scanner port, or changes to aidude. These are not blockers for the approved
snapshot dashboard. The UI must state source limitations accurately instead
of presenting unsupported values or hiding them behind zero fallbacks.
