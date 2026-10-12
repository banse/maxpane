# PROTOCOL / SURFBOARD live hero integration — proposal 1

## Approved scope

The owner approved the proposal 1 Textual mockup and explicitly asked to connect
it. Replace the generic hero only for `MODE_POOL4`, the PROTOCOL dashboard, with
the approved six cards: TOTALS, INVENTORY, REWARD SPLIT, UNSETTLED, DELIVERY and
CHECKS. Keep six equal nine-row cards at **149 columns × 45 rows**, with the
existing native protocol body below. Preserve every other mode and the standalone
fictional mockup.

This is Tier 2, below 1,000 production lines overall, with one final review and
no package reviews. All facts already exist in `_pool4_keys`; reuse the current
pool sweep, source envelope and cache. Add no network call, endpoint, poller,
cache schema, key, credential or configuration write. Superpowers remain disabled.

## Frozen primitive contract

`data/surf_models.py` owns `SURF_PROTOCOL_HERO_FIELDS`,
`SURF_PROTOCOL_HERO_STATES` and `SURF_PROTOCOL_WIDGET_SIGNATURES`.
The normal Surf payload gains one `surf_protocol_hero` dictionary.
`SurfProtocolHero.update_data(*, surf_protocol_hero=None, **kwargs)` consumes it.
The pure assembly function is `project(*, data, sources, now)` in
`data/surf_protocol_hero.py`, with no I/O or clock reads.

```python
SURF_PROTOCOL_HERO_STATES = ("ok", "partial", "stale", "unavailable")
SURF_PROTOCOL_WIDGET_SIGNATURES = {
    "SurfProtocolHero": {"surf_protocol_hero": "surf_protocol_hero"},
}
SURF_PROTOCOL_HERO_FIELDS = {
    "totals": ("state", "read_ts", "burned", "rewarded", "fees"),
    "inventory": ("state", "read_ts", "cap", "reserve", "headroom"),
    "split": ("state", "read_ts", "path", "staking_pct", "nodes_pct", "bonding_pct"),
    "unsettled": ("state", "read_ts", "burn", "rewards"),
    "delivery": ("state", "read_ts", "queued", "ready", "per_day"),
    "checks": ("state", "read_ts", "counters", "drift_bps", "path"),
}
```

All fields and sections are always present. Values are primitives; missing facts
are `None`, not fabricated zero. `read_ts` is the successful observation's UTC
epoch, not display time. Validate finite numeric inputs, reject booleans, preserve
zero, and allow signed `headroom` and `drift_bps`; token amounts are nonnegative.
`path` is exactly `direct`, `via-distributor` or `None`. `counters` is exactly
`reconciled`, `mismatch`, `window-limited`, `unchecked` or `None`.

## Mapping and observation semantics

| Section | Existing flat input keys, in field order |
| --- | --- |
| `totals` | `pool4_total_burned`, `pool4_total_rewarded`, `pool4_total_fee_token` |
| `inventory` | `pool4_inventory_cap`, `pool4_tokens_in_pool`, `pool4_cap_headroom` |
| `split` | `pool4_reward_path`; `pool4_distributor_staking_bps`, `pool4_distributor_nodes_bps`, `pool4_distributor_bonding_bps`, each divided by `pool4_bps_denominator` and multiplied by 100 |
| `unsettled` | `pool4_unsettled_burn`, `pool4_unsettled_stakers` |
| `delivery` | `pool4_backlog_imd`, `pool4_drippable`, `pool4_drip_per_day` |
| `checks` | `pool4_counter_state`, `pool4_split_drift_bps`, `pool4_reward_path` |

Keep `_pool4_keys` as the existing token-unit and protocol-math boundary. Do not
divide whole IMD values again, recompute headroom, derive drift from rounded
totals, or replace the reward total with staking's subdivision.

`sources` needs only its `pool4` envelope. Pass the envelope already captured for
`surf_pool4_hero`, alongside the same flat values at both `_project_hub` and
`_cycle`. In the detached cycle, use metadata captured before offering the sweep;
do not fetch newer cache clocks after capturing older values. A synchronous hub
refresh captures values and metadata together. Preserve the existing no-refresh
path's completed-cycle projection. Neither market nor staker failures degrade
these pool-only cards.

Reuse the current `_pool4_hero_source` rules: confirmed identical successful
reads may advance the observation clock for that captured payload; retry clocks
and failed reads cannot. Timestamps must be finite, positive and no later than
injected `now`. Missing/invalid source provenance invalidates its displayed facts.
Explicitly dated stale values may remain visible. A valid source with some
unread required fields is partial; all required facts unread is unavailable.
Stale source status takes precedence over partial coverage when values survive.

For REWARD SPLIT, a `via-distributor` path requires a readable positive
denominator and bounded shares; unavailable fractions remain `None`. Preserve
the producer's derived bonding value and its visible qualification. An explicit
`direct` path is a valid observation of no distributor subdivision: retain that
path, leave all three distributor percentages `None`, and render the direct
staking route rather than three invented zero shares. Unknown path cannot be
inferred from an address or from missing legs; do not publish a distributor split
under an unknown route. Preserve readable path evidence when percentages fail.

## Rendering behavior

Reuse `HeroRecord` and `LocalSourceHeroCard` unchanged. New widget-local behavior
may style CHECKS alarms without changing the shared renderer or importing data
modules. Preserve the rack's casing, inset, green healthy frame, list alignment,
equal height and footer baseline.

- TOTALS / IMD: burned, rewarded, fees; footer `CUMULATIVE`.
- INVENTORY / IMD: cap, reserve, headroom; footer `RATCHET`. Keep the sign of
  negative headroom and do not clamp it to zero.
- REWARD SPLIT / REWARD %: staking, nodes, bonding with a visible derived marker
  and explanation. The percentages divide the reward leg, not gross sells.
  Direct and unknown routes must remain visibly distinct from a distributor.
- UNSETTLED / IMD: burn and rewards; footer `PENDING`.
- DELIVERY / IMD: queued, ready and cap per day; footer `RATE LIMITED`. Ready
  is the existing drippable amount; the rate is a cap, not earned yield or a
  promised delivery time.
- CHECKS / STATUS: reconciliation verdict, signed drift in bps, reward path;
  footer `ACCOUNTING` when healthy. Match the native SPLIT semantics:
  `mismatch` is the foremost alarm; nonzero drift is also an alarm. Neither
  may render as green success. `window-limited`, `unchecked` and unknown mean
  `not established`, with neutral styling, not a passing verdict or an alarm.
  `direct` must not print `distributor`; unknown path stays explicitly unknown.

Source freshness and accounting verdict are different: a fresh mismatch still
has fresh source metadata and a visible accounting alarm. Stale/partial footers
use the existing local-clock treatment; show real read times, never refresh time.
Keep known values when neighbors are unread, and show every card on every update.
Use safe literal text, adaptive compact formatting and sufficient precision so
small nonzero amounts or drift do not falsely read as zero. Keep the full native
body's evidence available beneath the summary.

## Work packages and dependencies

1. **Planning agent:** only `docs/surf_protocol_hero_live_plan.md`; freeze this
   contract before data and widget implementation. No code or subagents.
2. **Data worker:** new `data/surf_protocol_hero.py`, focused projection tests,
   `data/surf_models.py`, `data/surf_manager.py` integration, and their relevant
   manager/model contract tests. Own matching observation capture and both
   assembly entry points. Existing protocol reads and math stay unchanged.
3. **Widget worker:** new `widgets/surf/protocol_hero.py` and
   `tests/widgets/test_surf_protocol_hero.py`. Consume only the frozen primitives,
   render the six cards, and handle route/verdict/unknown/freshness differences.
4. **Root:** exports, `screens/surf.py`, theme CSS, composing screen/layout tests,
   live capture, measured pin changes if needed and integration/follow-up docs.
   Mount the new hero once, show it only for `MODE_POOL4`, and stop showing the
   generic `SurfHero` only in that mode. All other mode visibility is preserved.

Production paths are relative to `maxpane_dashboard/`; tests remain under `tests/`.
Data and widget packages can run in parallel after freeze; root integration
depends on both. Root assigns individual contract-test files before concurrent
edits; no shared test file has two owners. Preserve others' work and report
cross-owner defects rather than editing another package. No task reviews.

## Verification and delivery

- Start with focused failing tests. During edits run only cases covering the
  change; no tests touch the network or real clipboard.
- Cover zero, unknown and partial facts; signed negative headroom/drift; invalid
  numbers/denominators/clocks; source staleness/failure; direct versus distributor
  versus unknown routes; all counter verdicts; and model/widget agreement.
- Prove both manager paths preserve the pool snapshot's own timestamp even when
  detached work completes later. Unrelated market/staker degradation must not
  blank or stale the protocol facts.
- Assert actual composited content and styling: no false green mismatch/drift,
  no guessed distributor route, no rounded-to-zero nonzero measurements, derived
  bonding disclosure, all six cards and their common nine-row geometry.
- Check mode switches, resize/scroll recovery and coherence with the native
  protocol body, while preserving other heroes.
- Show a keyless **live production render at 149×45 before** pin remeasurement,
  hardening docs or final review. Temporary artifacts stay outside Git; failed
  facts remain visibly unavailable. This planning document precedes that gate.
- Then measure the actual in-situ protocol layout, update pins and their `#:`
  records only as evidence requires, and prove important clock/geometry tests
  bite using reversible targeted mutations.
- Before commit, run affected and composing files once with isolated HOME and
  `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
  docpins. No full suite without an owner request.
- One final independent review, one fix wave, and one scoped re-review only
  when production fixes require it. File Minor-only residuals; root commits the
  reviewed result before advancing to the next dashboard's proposal phase.
