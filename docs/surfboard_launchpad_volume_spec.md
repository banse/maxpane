# Surfboard launchpad volume and reduced chrome

Date: 2026-10-11. Tier 2: client/model/manager and screen/widget changes across
more than six files. Expected production change below 1,000 lines; one final
review only. This specification supersedes the focused-detail presentation in
`surfboard_status_layout_spec.md`; its card positions and activity states remain.

## Requested result

- PROTOCOL has three left-aligned columns: label, amount, IMD. For example,
  `burned 33k IMD`, without a colon. Align corresponding columns across rows,
  retain spacing between columns and padding at both ends, and leave its inset
  bottom border without footer text.
- LAUNCHES keeps its existing 24-hour volume history. Its sparkline glyphs use
  the same green as SWARM, including when coverage is partial. Preserve the
  amber `~24H` label for partial or stale data.
- Remove focused-card dynamic detail from the screen entirely. Return the
  terminal to its direct central grid slot and its full available dimensions.
  Keep card focus, keyboard navigation, activation, and terminal behavior.
- LAUNCHPAD uses the same eight-point sparkline format for the latest two
  completed hours of trading across all launchpad tokens. The label is `2H` for
  complete fresh data and amber `~2H` for partial or stale data; chart glyphs are
  green. Missing data remains visibly unknown.

Combined USD volume follows the convention already accepted for LAUNCHES. The
LAUNCHPAD calculation values its ETH quote amounts with the valid cached ETH/USD
quote; it does not claim to reconstruct historical USD execution prices.

## Existing source and chosen calculation

`data/surf_client.py::_launchpad_logs` receives the complete uncapped
`day_swaps` sweep before `_launchpad_feed_from_logs` produces a shortened feed.
The merged `launches` population and `LaunchpadState.cursor` retain all known
pool identities, including tokens outside the rendered coin ranking. The cursor
contains lifetime counters, but no historical swap amounts or timestamps; the
chart therefore cannot be reconstructed from the cursor alone.

`_decode_curve_swap_log` decodes the CurveSwap event's native ETH quote amount
from ABI word 1. Sum that quote leg once per buy or sell for every pool in the
complete launchpad population. Identify pools by their stable pool ID, not by
ticker. Do not sum both sides of a trade, add fee legs, use the capped `activity`
or `coins` lists, or substitute the per-coin swap counts for volume.

Use eight closed UTC 15-minute intervals with half-open boundaries `[start,end)`;
their common end is the last completed UTC quarter-hour at the observed head.
Exclude the still-open interval. Retain that end with the snapshot; repainting
or an unrelated successful getter must not advance it. A valid native ETH amount
uses the event-defined wei scale of 10^18, independent of each launched token's
ERC20 decimals. Any implementation that instead uses token units must read and
validate the actual token decimals.

Fetch exact block-header timestamps through the existing keyless state RPC pool.
The feed's block-distance-times-12 estimate is unsuitable for exact binning.
Reuse the existing full log sweep and client transport; do not add a per-token
market-price fanout or an endpoint pool. Read at most 256 distinct swap-block
headers in batches of 32, newest first, stopping when remaining blocks precede
the window. One separate head/scan-start header batch proves range coverage.
Reuse headers for repeated blocks and bound timestamp hydration to 20 seconds.
Exhausted budget, timeout, missing/mismatched headers, or insufficient time
coverage produces an unavailable observation, never invented zero buckets.

## Data seam and truthfulness

Add only the optional internal `LaunchpadState.volume_2h` snapshot needed to pass
the uncapped calculation from client to manager. Persist it in the existing
launchpad slot via `_launchpad_payload` and pass it through the existing
`launchpad=` card input. The snapshot carries eight validated native-quote
buckets, coverage state, its own read/head timestamps, and the covered window end.
No public `SURF_KEYS`, card keys, widget signatures, or new cache slot are needed.
Use existing card `points`, `meter_kind='sparkline'`, and `meter_state`.

The manager/card projection converts valid buckets to USD only with a finite,
positive ETH/USD quote whose market-family source clock is fresh. Volume has an
independent 600-second TTL, checked against both read and head timestamps. The
projection validates persisted data again before use. Clocks are injected,
including expiry and window boundaries.

- A successfully covered interval with no trades is a real zero. Failed log
  reads, missing block timestamps, malformed amounts, incomplete population,
  unknown pool identities, and missing USD conversion are not zero-volume proof.
- Never publish a sum of the successfully decoded subset as a complete total.
  Affected buckets remain missing; when the affected interval cannot be located,
  degrade the whole observation conservatively. Complete coverage also requires
  the factory coin count to match the full known launch population; a mismatch
  is partial with no complete aggregate chart. Malformed/conflicting event IDs
  make the observation unavailable rather than double-counting uncertain logs.
- Reject booleans, negative/nonfinite amounts, invalid ABI integers, malformed
  timestamps, impossible future clocks, and invalid persisted bucket shapes.
  Validate integer amounts before conversion to a display number.
- A failed refresh or expired snapshot cannot become live through a new slot
  timestamp. Retained history keeps its original source clocks and window end, with
  stale state. A missing/expired USD quote cannot yield a fresh USD chart.
- Cold or malformed caches remain unavailable; old caches without `volume_2h`
  load normally. Preserve existing launchpad totals, cursor, ranking, feed, and
  their failure behavior.

With focused detail removed, the visible footer must itself preserve the
partial/stale distinction from complete data. Internal detail strings may remain
for existing contracts, but cannot be the only disclosure of degraded volume.

## Layout and retained behavior

Remove `#surfboard-detail`, its updates and detail-only state, and the center
wrapper introduced solely for terminal/detail stacking. Put the existing
terminal directly in its four-column, three-row central slot. Synchronize
screen CSS and `themes/minimal.tcss`; retain genuine outer scroll hints.

Keep AGENT at row 2 column 0, PORTFOLIO at row 1 column 5, and empty BAY 10/11/12.
Keep OFF red with hollow cells, BUSY orange with a full green bar, and IDLE with
the existing green-to-orange 24-hour decay. LAUNCHES never widens its title.
Retain protocol source calculations and other card data; only its inset footer
presentation and column order change.

## Decision and acceptance

The chosen full-log/header path adds bounded header reads but has complete
population coverage and exact interval membership. Reusing the capped feed would
be shorter but omit trades and use approximate ages. Fetching market histories
per launchpad coin adds transports, identity joins, and unavailable-market cases;
the existing protocol event quote amounts avoid that complexity.

Acceptance requires source tests for full population and interval boundaries,
decoding/clock/failure tests, composited color/column/geometry tests, and a real
keyless 149×45 render shown before any pin hardening. Measure layout boundaries
after that render; preserve readable protocol spacing and truthful overflow.
Run only affected and composing tests plus required guards/docpins, then one
final review of the complete change. No full-suite run or extra approval step.
