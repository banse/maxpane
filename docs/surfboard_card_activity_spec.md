# Surfboard card activity and footer specification

Date: 2026-10-11. Status: accepted implementation direction. Tier 2: data contract,
persistence, and more than six files. Expected production change: below 1,000 lines.

Activity correction, 2026-10-13: the owner's recent-work requirement supersedes
the observation-only policy below. Existing cached own-work submissions now seed
or advance idle history; unknown age stays a dash. The approved two-stage meter
drains green to orange over 24h, then orange to empty by 72h, with a grey IDLE
label. See [recovery plan](surfboard_activity_recovery_plan.md).

## Problem and constraints

The rack's outer footers currently expose acceptance ratios or empty tracks where the
owner wants recent trading volume, agent activity, and the sIMD exchange rate. Protocol
statistics and zero-news labels also need clearer presentation. Keep the existing card
destinations, rack dimensions, and source boundaries. The owner's terminal is 149×45.
LAUNCHES must retain its title without a widen marker.

Follow KISS and the existing client → cache/manager → plain-data projection → widget
flow. No new service or framework is needed. Sources remain keyless and read-only;
tests use fixtures and injected transports/clocks. Missing or failed reads are never
zero. Existing price-history behavior must remain compatible.

## Evidence and decisions

`data/surfboard.py::cards` projects rack data. `canonical_board` identifies the leader
from canonical records and enriches it with worker presence. `surf_swarm.py` exposes
`last_worked_ts` from submission time and `heartbeat_ts` from worker liveness; neither
is an execution-stop timestamp. `_pool_swarm_board` currently preserves a workers
version clock on unchanged reads and shares scheduling failures with contributors.
Neither clock establishes independently fresh worker observations.

| Decision | Selected approach | Alternative and trade-off |
|---|---|---|
| Launch volume | Reuse keyless market discovery and OHLCV history for combined USD volume | Locally sample rolling 24h totals: cheaper initially, but cannot reconstruct historical buckets on cold start |
| Agent activity | Persist observed busy-to-idle transitions per token | Use submission/heartbeat time: smaller change, but measures a different event and leaves the leader without equivalent history |
| Presentation | Extend the current plain card contract | Add separate footer widgets: more indirection without a useful lifecycle boundary |

The observation approach sacrifices exact upstream stop time: stops are detected on
the existing approximately 120-second worker polling cadence. Detail text must describe
an observed stop, never an exact execution timestamp. Cold idle history stays unknown.

## LAUNCHES outer footer

The user confirmed combined **USD trading volume** for all launched catalogue tokens.
Add separate `swarm_tokens_market.fetch_volume_history` using the same keyless OHLCV
endpoint and rate limiter, with `include_empty=true` and completed-hour candles.
Keep the existing `fetch_history` price request and semantics unchanged. Include every
catalogue deployment, including inactive and retired deployments; unsupported or
ambiguous deployments count against coverage. Deduplicate shared markets by
`(chain, market_pool)`.

The window ends at the latest completed UTC hour, spans the preceding 24 completed
hours, and renders eight consecutive three-hour sums. Validate finite nonnegative USD
volumes and timestamps. A served zero is zero; absent candles, unknown market mappings,
unsupported markets, and failed histories never become zero. Preserve gaps as `None`.
Partial catalogue or market coverage cannot be labelled complete. Detail text states
known/total coverage, USD units, the window end, and the successful observation time.

The footer uses SWARM's existing sparkline style: green `24H` for complete current
coverage, amber `~24H` for partial coverage, and explicit unavailable/stale treatment.
Retained stale history must be identified as stale. Missing points render gaps rather
than invented points. Width changes stretch existing buckets without adding samples.

The manager's `catalogue_summary()['volume']` contract is:

```python
{
    "points": list[float | int | None] | None,  # exactly eight when present
    "state": "ok" | "partial" | "stale" | "unavailable",
    "known": int, "total": int,
    "as_of": float | None, "until": float,
}
```

Coverage counts describe the full catalogue after shared-market deduplication, not
merely active deployments or the currently visible three launch previews. Unsupported,
ambiguous, and unresolved candidates prevent a full-coverage claim. The hub offers
only bounded catalogue, market, and volume work through shared tasks and rate limiting;
it starts neither existing price-history nor trade-history enrichment. Refreshing or
switching between hub and token screen must share applicable work.

## LEADERBOARD and AGENT outer footers

LEADERBOARD follows the canonical rank-one token; AGENT follows the selected token.
Both replace `PASS` with `BUSY` in orange or `IDLE` in green. Their meter represents
recent work, independently of acceptance counts:

| Evidence | Label and meter |
|---|---|
| Fresh, any device has positive work | Orange BUSY, full bar |
| Fresh, all devices have known zero work, or the token is confirmed absent | Green IDLE |
| First observed idle, no prior observed stop | IDLE with unknown meter (`—`) |
| Confirmed stop after observed work | IDLE, remaining seconds `max(0, 86400 - (now - stopped_ts))` |
| 12 hours / 24 hours after stop | Half / empty bar |
| Work resumes | BUSY, full bar; next observed stop starts a new window |
| Failed read, evidence older than 300 seconds, or unknown current work | Explicit unknown/stale label and unknown meter; never a fabricated IDLE or BUSY |

Any positive device proves work even if another device's count is unknown. A paused
worker with unknown work count does not prove idle. Repeated idle reads do not reset
the stop clock. Failed and unknown reads preserve history without creating a transition.
Per-token state survives process restart, selected-token changes, and leader changes.

The new pure `data/surfboard_activity.py` module exports:

```python
observe(prior, workers, *, now) -> dict
coerce(payload, *, now) -> dict | None
project(payload, token, *, now) -> dict
# project result:
{"state": "busy" | "idle" | "stale" | "unavailable",
 "remaining": float | None, "as_of": float | None,
 "stopped_ts": float | None}
```

`observe` consumes the normalized workers result; `None` denotes a failed attempt.
The validated persisted payload retains independent successful-read and attempt
metadata plus per-token transition history. A successful unchanged workers response
advances the observation clock. A contributor failure does not stale a successful
worker read. Cache slot: `SLOT_SURFBOARD_ACTIVITY = 'surfboard_activity'`, declared and
exported in `data/surf_cache.py` by the activity implementer, not in `surf_models.py`.
Missing old cache data is a supported cold start; malformed/future persisted values are rejected.
No widget reads the clock or imports data modules.

## Other card changes

- PROTOCOL displays three aligned, left-aligned columns: amount, `IMD`, label; for
  example `33k IMD burned`. Labels remain `burned`, `rewarded`, `fees`. No colons;
  preserve inner padding and unavailable values.
- ONCHAIN NEWS (`announce`) and LAUNCHES (`swarm-tokens`) hide only known zero-new
  inner-footer text. Positive counts remain visible; unknown data stays explicit.
  Keep the underlying count/source semantics intact. Other cards retain their labels.
- POOL4's outer footer is `1 sIMD = x IMD`, reusing `pool4_share_price` from the
  protocol dashboard. Preserve spaces. Fit decimal precision to the current width;
  show six decimals in detail. Missing rates remain unavailable, retained stale rates
  keep their source marker, and no current rate is hardcoded.

## Card contract and boundaries

Append `meter_state` and `share_price` to `SURFBOARD_CARD_FIELDS`; unrelated cards use
`None`. No new widget signature or top-level dashboard key is required. Activity uses
existing numerator/denominator fields (`remaining` / `86400`) and `meter_state`;
volume uses existing `points`, `meter_kind='sparkline'`, and `meter_state`.
`cards(..., activity=None)` receives the validated activity payload for pure projection
at its existing injected `now`. Existing card status/source detail continues to serve
the card's other values; meter health must not silently override unrelated meanings.

## Acceptance and verification

Use test-first behavior changes and committed volume/worker fixtures. Cover aggregation
boundaries, pool deduplication, gaps, zero versus missing, partial/stale sources, retained
price history, independent worker freshness, transition timing, restart, token switching,
and malformed persistence. Assert rendered labels, colors, padding, gaps, and proportional
meters through composited strips. Prove changed decoder/timing behavior with focused
`scripts/mutate.py` runs.

After the behavior works, show a real keyless live render at 149×45 before layout
hardening or review. Check relevant width boundaries and resize behavior, including
LAUNCHES having no widen marker. Run touched and composing test files plus the required
fast guard set once before commit. No full suite; one final whole-change review only.
