# LAUNCHPAD / SURFBOARD live hero integration — proposal 1

## Approved scope

The owner approved the six-card LAUNCHPAD mockup and asked to continue. Connect
COINS, CURVE FLOW, VOLUME, CREATOR FEES, BURN QUEUE and BURNED to existing reads.
Keep six equal nine-row rack cards at **149 columns × 45 rows**, above the native
launchpad body. Preserve its coin/activity tables, flow/burn/burnkeeper panels,
other dashboard modes and the standalone fictional preview.

This is Tier 2, below 1,000 production lines overall, with disjoint data and
widget packages and one final review only. Reuse existing requests, scheduling,
cache entries and conversion helpers. No endpoint, API call, observation map,
persisted cache format, credentials or configuration write is added. Superpowers
remain disabled. Root owns shared files and integration.

## Frozen primitive contract

`data/surf_models.py` owns the following fields/states/signature and adds
`surf_launchpad_hero` to the normal Surf payload. The widget method is
`SurfLaunchpadHero.update_data(*, surf_launchpad_hero=None, **kwargs)`.

```python
SURF_LAUNCHPAD_HERO_STATES = ("ok", "partial", "stale", "unavailable")
SURF_LAUNCHPAD_WIDGET_SIGNATURES = {
    "SurfLaunchpadHero": {"surf_launchpad_hero": "surf_launchpad_hero"},
}
SURF_LAUNCHPAD_HERO_FIELDS = {
    "coins": ("state", "read_ts", "count", "new_24h", "swept"),
    "flow": ("state", "read_ts", "swaps", "traders", "creators"),
    "volume": ("state", "read_ts", "usd", "points", "until", "known", "total",
               "quote", "quote_read_ts", "volume_read_ts"),
    "fees": ("state", "read_ts", "eth"),
    "queue": ("state", "read_ts", "accrued", "staged", "sendable", "ready"),
    "burned": ("state", "read_ts", "imd"),
}
```

The pure assembly seam is `project(*, data, launchpad, sources, now)` in new
`data/surf_launchpad_hero.py`. `data` is the existing whole-unit flat payload;
`launchpad` is its matching captured slot, including `volume_2h`. `sources`
contains independent `launchpad` and `market` envelopes with `state/read_ts`.
All output fields and sections are always present and contain primitives only.
Unknown numbers are `None`, never zero. Counts reject booleans/fractions; amounts
are finite and nonnegative; `ready` is strictly `True`, `False` or `None`.
`points` is eight nonnegative USD values or `None`. All clocks are finite,
positive observation epochs no later than injected capture/projection time.

## Existing source mapping

| Section | Existing input facts |
| --- | --- |
| `coins` | `launchpad_coin_count`, `launchpad_new_24h`, `launchpad_launch_count` |
| `flow` | `launchpad_swap_count`, `launchpad_trader_count`, `launchpad_creator_count` |
| `volume` | Captured `launchpad.volume_2h`, `eth_usd`, launchpad/market source envelopes |
| `fees` | `launchpad_creator_eth_owed` |
| `queue` | `burn_accrued`, `burn_staged`, `burn_bridgeable`, `burn_ready` |
| `burned` | `launchpad_burned_total` |

Factory count and swept launches are separate observations. A mismatch, unknown
count or unknown swept count marks surviving COINS, CURVE FLOW and BURNED facts
partial; preserve both counts for a visible coverage explanation. If all facts
are absent, that section is unavailable. A valid 0/0 population is complete and
can show zero. Do not derive population totals from the capped coin list.

Swaps, distinct trader addresses, creators and burns are cumulative observed
history, not 24-hour counts. New launches use the existing block-based day
approximation; do not claim it has the exact timestamp precision of volume.
History coverage does not degrade independently readable current creator fees
or burn queue getters. A missing individual getter affects its own facts.

Queue readiness is the producer's `previewBridge()` result: positive sendable
amount means ready, zero means waiting, unread means unknown. Do not infer this
from hook accrual, staged balance or minimum bridge settings. Accrued belongs to
the hook; staged is the executor balance; sendable includes bridge limits and
dust. Readiness is a display fact only, with no transaction action. Creator fees
are an outstanding ETH balance, not earned yield. Event burns remain distinct
from observed supply-change burns and the separate PROTOCOL total.

## Shared volume policy

Call existing `surfboard._launchpad_volume(data, launchpad, sources, now)` for
USD points and source status **without copying its conversion or freshness
logic**. Use `surf_launchpad_volume.coerce_snapshot` for validated metadata.
Sum only the returned usable points to derive `usd`, validating the sum remains
finite. Do not build a second definition of launchpad volume for this hero.

The existing snapshot covers eight completed 15-minute buckets over launchpad
token CurveSwap trades, ending at `until`. It is not IMD/ETH-pool volume, not
24-hour volume and not necessarily a rolling window ending at display time.
`known/total` are the snapshot's covered/expected pools. Incomplete coverage
retains its partial state and publishes no points or total; it must not become
a zero chart. A fully covered quiet interval can legitimately total zero.

The ETH amounts are valued at the currently observed ETH/USD quote, not historical
trade quotes. Preserve the helper's requirement for a positive fresh quote with
its own successful-read clock. An unread/stale quote cannot mint a USD value or
borrow the launchpad clock. Stale covered history may retain dated points only
when the existing helper allows them. Retain `quote`, `quote_read_ts`,
`volume_read_ts` and `until` for the tooltip/visible window explanation. The common
volume `read_ts` is the oldest contributing launchpad/snapshot/quote observation.
Invalid launchpad provenance must not make a raw cached snapshot look valid.

## Manager capture and freshness

Root hoists the existing flat launchpad assembly into
`_launchpad_keys(slot, entry, eth_usd)` and reuses it in `_cycle` and `_project_hub`.
This is necessary because the hub currently refreshes counts while retaining
burn/fee amounts from an older full payload. One assembly boundary must supply
the native panels and new hero from the same slot and perform wei conversion
exactly once. Preserve the existing whole-unit values and readiness logic.

Capture the launchpad entry, values and source envelope **before** offering its
detached sweep. Capture market values and metadata together after that source's
awaited read. Reuse the existing `_pool4_hero_source` helper for tier/source
metadata rather than introducing a new tracker. Launchpad uses its 600-second
tier; the market quote retains the existing 90-second policy. Failed reads retain
the last-good clock and explicit stale state; partial subfields do not fabricate
fresh values for unread facts.

Use the current injected clock at each synchronous capture/projection boundary,
not the full cycle's start timestamp after intervening awaits. A source that
finishes later than cycle start is not a future observation. Conversely, never
read a newer cache timestamp to label values captured before detached completion.
Preserve already matched projections when the no-refresh path reuses a completed
cycle. No additional network work or altered scheduling is needed.

## Rendering contract

Reuse existing `HeroRecord` and `Pool4HeroCard`/`LocalSourceHeroCard` presentation.
Keep the approved casing, inset, frame, list alignment and card/footer heights.

| Card | Inner presentation | Healthy footer |
| --- | --- | --- |
| COINS | COINS; count digits; new launches `/24h` | FACTORY |
| CURVE FLOW | HISTORY; swaps, traders, creators | OBSERVED |
| VOLUME | kUSD; total digits; `2h to HH:MM` | 2H plus existing sparkline |
| CREATOR FEES | ETH; precise balance digits; `owed` | UNCLAIMED |
| BURN QUEUE | IMD; accrued, staged, sendable | READY / WAITING / UNKNOWN |
| BURNED | kIMD; amount digits; `cumulative` | EVENT TOTAL |

Only display a green healthy frame when the source and required facts support
it. Keep known values beside unread neighbors. Source partial/stale markers and
local read clocks remain visible; coverage and readiness qualifications must not
disappear when the normal footer is replaced. Every update paints every card.
Unknown volume has no fabricated sparkline; complete zero volume stays distinct.
Adaptive precision must retain small positive ETH/IMD/volume values rather than
rounding them to zero, and must not clip large digits. Widgets construct no
managers/endpoints, perform no I/O and import no data modules.

## Ownership and dependencies

1. **Planning agent:** only this new plan; freeze the approved contract before
   implementation. No code, commits or subagents.
2. **Data agent:** new `data/surf_launchpad_hero.py` and
   `tests/data/test_surf_launchpad_hero.py`. Implement the pure projection using
   existing volume logic; do not alter shared files without root coordination.
3. **Widget agent:** new `widgets/surf/launchpad_hero.py` and
   `tests/widgets/test_surf_launchpad_hero.py`. Consume the frozen primitive dict
   and implement the approved six-card presentation and states.
4. **Root:** `surf_models.py`, manager and shared projection seams, screen/theme,
   exports, contract/manager/composing/layout tests, live capture and follow-up
   documentation. Mount `SurfLaunchpadHero` once and show it only in
   `MODE_LAUNCHPAD`, replacing the generic hero there while preserving other modes.

Data and widget packages run independently after contract freeze. Root integration
depends on both and is the sole owner of shared files. Preserve other agents'
work; report cross-owner defects instead of editing another package.

## Verification and delivery

- Start with focused failing tests. Tests use no network or real clipboard.
  Cover contract agreement; genuine zeros versus unknown; factory/sweep mismatch;
  coverage-independent queue/fees; readiness tri-state; small/large amounts;
  partial fields, failed source, stale retained readings and invalid clocks.
- Exercise complete and incomplete volume, eight buckets and sum agreement,
  stale/failed quote, stale/end-of-window history, zero quiet interval and no
  substitution from capped tables or the unrelated IMD pool.
- Prove manager hub/full paths agree on slot-derived burn/fee amounts, capture
  clocks after intervening awaits, and resist detached completion relabeling.
  Mutation-prove important source-clock and conversion claims with named tests.
- Assert composited output at 149×45, six equal nine-row cards, native body
  coherence, mode switching, narrow scrolling and resize recovery. Preserve
  readable units and all source/coverage/readiness qualifications.
- Show the **live production render at 149×45 before** layout remeasurement,
  pin evidence/hardening docs or final review. This planning document precedes
  that gate. Keep temporary captures outside Git.
- After the live preview, use the existing launchpad in-situ sweep, alter pins
  only when measurement requires it and mutation-prove changed geometry checks.
- Before commit run affected/composing files once under isolated HOME with
  `-n 4 --dist worksteal`, fast `guard and not mounts_app` and applicable docpins.
  No full suite without an owner request.
- One final independent review, one fix wave and scoped re-review only for
  production fixes. File Minor-only residuals; root commits the verified result
  before continuing the dashboard proposal loop.
