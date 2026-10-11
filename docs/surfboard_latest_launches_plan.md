# LAUNCHES card: latest tokens

## Approved specification

The owner's request replaces the LAUNCHES inset title "TOKENS" with "LATEST",
removes the digits, and shows three rows with launch age, ticker, and chain.
Row text uses the same white as the previous digits. Each row starts with green
`✔` when verified ETH/IMD liquidity is two-sided, or orange `⚠` for single-sided
liquidity, using the SWARM TOKENS dashboard's classification.

Only this inset changes. Keep the `N new` inset footer, outer `TOKENS` meter,
route, activity border colors, card dimensions, and all other cards unchanged.

- Select the three newest supported live swarm token deployments from the same
  deduplicated population as SWARM TOKENS; deterministic ordering uses launch
  timestamp and deployment identity. Never duplicate a deployment through aliases.
- Reuse `SwarmTokensManager._tokens()` for exact launch identity, ticker, chain,
  liquidity freshness, and `lp_state`; do not reproduce liquidity predicates.
- Green requires fresh verified `two-sided` ETH/IMD liquidity. Fresh `one-token`
  or `one-quote` is orange. Unknown, stale, withdrawn, or unverified liquidity
  gets neutral `—`; cached catalogue freshness cannot certify a liquidity read.
- Preserve unknown ages/symbols as `—`. A failed catalogue read is explicitly
  unavailable; a known empty catalogue says no launches. Fewer than three known
  tokens produces only their real rows, with unused space blank.
- Retained/partial catalogue state and observation time remain disclosed in
  card detail. Untrusted ticker text is flattened safely and rendered as Rich
  `Text`; clipping must retain age, chain, marker, and the existing widen hint.

## Scope and ownership

Tier 2 because the card payload contract gains `latest_launches`. Expected change
is under 1,000 production lines, so there are no package reviews; one final review
covers the complete diff. The root session owns all implementation and tests.
This planner owns this document only. Packages run sequentially because their
files and data contract overlap. Python/Textual/Rich remain the existing stack.
No new endpoints, keys, signing, dependencies, or unrelated dashboard work.

## Implementation packages

### 1. Freeze the contract and project cached evidence

Files: `data/surf_models.py`, `data/swarm_tokens_manager.py`,
`data/surf_manager.py`, `data/surfboard.py`, and their focused data tests under
`tests/data/` (`test_swarm_tokens_live.py`, `test_surfboard.py`,
`test_surf_manager_surfboard.py`).

Add `latest_launches` to `SURFBOARD_CARD_FIELDS`: `None` means unknown; a list
contains at most three primitive row dictionaries (`age_s`, `symbol`, `chain`,
`lp_state`, `liquidity_state`, and `paired_symbol`).
Other cards retain the field as `None`. Derive ages with the injected clock.

Add optional `source` to pure `catalogue_summary()` and pass the cached
`data['swarm_launch_rows']` from `_project_hub()` explicitly. Reuse
`_tokens(source or {}, now)` and the existing newest-token selector. Catalogue
identity selection and the existing count/state/as-of fields stay intact. Keep
catalogue and bounded launch-evidence refresh offers in the existing hub refresh
path; never hide scheduling inside `_project_hub()` or `catalogue_summary()`.
This card must not start market/history/trade reads. Feed summary rows into
`hub.cards()` and retain the count in card data/detail, without rendering digits.

Acceptance: offline tests cover latest ordering, deduplication, supported/live
filtering, matching versus mismatched launch evidence, TTL boundary/stale/withdrawn
states, empty versus unavailable, and no market enrichment offered from the hub.

### 2. Render the three-row inset

Depends on package 1. Files: `widgets/surfboard/rack.py`,
`tests/widgets/test_surfboard_rack.py`, `tests/surfboard_fixtures.py`, and
`tests/screens/test_surfboard_layout.py` as required for the composing fixture.

Replace only the LAUNCHES numeric branch with `LATEST` and three aligned row
slots. Use cell-width-aware formatting: marker, age, flexible ticker, chain.
Keep ordinary row text white and color only the liquidity marker. Fit the
existing inset at the owner size and minimum width; long symbols use the
existing explicit clipping indication. Update fixture payloads to exercise rows.

Acceptance: composited-strip tests prove all three rows, order, white text,
green/orange/neutral markers, safe hostile/wide tickers, fewer rows, unavailable
and empty states, preserved footers, and unchanged neighboring cards/navigation.

### 3. Verify and finish

Depends on packages 1–2. Show a fresh keyless live render at 149×45 before layout
hardening or review. Check the existing 140×36 boundary and resizing in situ;
only re-pin and update the measured `#:` block if evidence requires it. Do not
raise the pin merely to accommodate an unusually long ticker.

While editing, run only affected behavior tests. Prove liquidity/order tests
bite using `scripts/mutate.py`, then run touched test files plus their composing
screen/manager files once with isolated HOME and `-n 4 --dist worksteal`, followed
by `guard and not mounts_app`. No network or clipboard access in tests; no full
suite. Dispatch one final review with the repository's verbatim reviewer
contract. Resolve the permitted fix wave and scoped re-review if required,
record residual follow-ups, and commit only this task's changes.

## Live check

The 2026-10-11 public/keyless 149×45 capture showed TEST with an orange warning,
SFPT with a green check, and the RH launch with neutral unknown liquidity.
Long names retain the existing clipping hint; the 140×36 layout pin is unchanged.
Launch age keeps the catalogue's `createdAt` meaning, as in SWARM TOKENS; it is
not a separately verified deployment-block timestamp.
