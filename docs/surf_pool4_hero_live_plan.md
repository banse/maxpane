# POOL4 / SURFBOARD live hero integration — proposal 1

## Approved scope

The owner approved the six-card Textual mockup and asked to continue. Connect that
design to existing live POOL4 data. The rack destination is `MODE_POOL4_USER`, the
market dashboard; the separate `MODE_POOL4` protocol body keeps its existing hero.
Preserve six equal nine-row cards at **149 columns × 45 rows**, in this order:
IMD PRICE, sIMD RATE, STAKING, VAULT, DOWNSIDE BID and DRIP QUEUE.

This is Tier 2, below 1,000 production lines overall, with one final review and
no package reviews. Reuse existing client reads, snapshots, cache entries and
scheduling. Add no endpoint, poller, cache format, credential or configuration
write. Superpowers remain disabled. Keep native POOL4 FLOW, BURN & SUPPLY, SIGNALS,
STAKERS and IF IMD FALLS panels and all other dashboard heroes intact.

## Frozen primitive contract

`data/surf_models.py` owns `SURF_POOL4_HERO_FIELDS`, `SURF_POOL4_HERO_STATES` and
`SURF_POOL4_WIDGET_SIGNATURES`. Add one `surf_pool4_hero` dictionary to the normal
Surf payload. `SurfPool4RackHero.update_data(*, surf_pool4_hero=None)` consumes it.
The pure assembly seam is `project(*, data, sources, now)` in
`data/surf_pool4_hero.py`; it performs no I/O or clock reads.

Every section has `state: ok | partial | stale | unavailable` and
`read_ts: float | None`, the successful observation's UTC epoch. The exact fields
beyond those common two are:

| Section | Fields | Approved display |
| --- | --- | --- |
| `price` | `usd`, `venue`, `gap_pct` | IMD PRICE / USD; numeric USD price, venue subtitle; footer POOL4 |
| `rate` | `imd` | sIMD RATE / IMD; conversion per 1 sIMD; footer EXCHANGE |
| `staking` | `apr` | STAKING / APR %; `trailing 7d`; footer REALISED |
| `vault` | `imd`, `simd`, `holders`, `holders_state`, `holders_read_ts`, `holders_partial` | VAULT / STATS; IMD, sIMD and addresses; footer STAKED |
| `bid` | `status`, `eth`, `distance_pct` | DOWNSIDE BID / ETH; distance under spot; status footer |
| `queue` | `imd`, `per_day`, `days` | DRIP QUEUE / DELIVERY; queued IMD, cap IMD/d and queue days; footer RATE LIMITED |

`holders_state` uses the same state vocabulary and retains its independent
`holders_read_ts`; the boolean `holders_partial` preserves incomplete coverage
independently, including when the source is stale. All values are primitives; no cache/model objects, Rich values
or Textual objects cross the seam. Validate finite numbers, reject booleans as
numeric values, and preserve `None` as unknown rather than inventing zero.

## Source mapping and capture rules

`sources` contains `pool4`, `market` and `stakers`, each with independent
`state/read_ts`. Root constructs these envelopes from the same cache versions as
the flat values. Capture pool and staker payloads plus metadata **before detached
work is offered**; capture market metadata after its own awaited read alongside
the selected market payload. Do not re-read newer cache clocks after projection
values have already been captured.

| Card facts | Existing flat source fields | Observation dependency |
| --- | --- | --- |
| Price and venue | `pool4_price_usd`, `pool4_cheaper_venue`, `pool4_venue_gap_pct` | USD price combines pool tick and market ETH/USD; use the oldest contributing pool/market clock. Venue comparison comes from the same pool sweep |
| Share conversion | `pool4_share_price` | Pool sweep |
| Realised staking APR | `pool4_trailing_return_pct` | Pool sweep, including that sweep's drip delivery window |
| Vault balances | `pool4_vault_assets`, `pool4_vault_shares` | Pool sweep |
| Holder count | `pool4_staker_count` | Separate staker fold and its own state/clock |
| Downside bid | `pool4_backstop_state`, `pool4_backstop_eth`, current/lower ticks | Pool sweep; reuse existing `band_distance_pct` math |
| Delivery queue | `pool4_backlog_imd`, `pool4_drip_per_day`, `pool4_backlog_days` | Pool sweep |

Use entry timestamps plus matching successful-read clocks only when a confirmed
unchanged read describes that captured payload. A retry/attempt clock, evaluation
time, event timestamp or another source's success cannot refresh a card. Preserve
failure evidence and existing source TTLs. Source timestamps must be finite,
positive and no later than injected `now`.

The APR history is not an independently refreshed cache: `_pool4_drip_read` writes
the delivered amount and measured window into the same pool snapshot. A failed
window read yields `None`; it does not retain a prior delivered amount. Only the
measured block-time estimate may carry forward to determine a quiet window's
span. An unread APR therefore makes STAKING unavailable without degrading valid
share, bid or queue fields from the same sweep.

VAULT retains readable balances when holders are missing and marks the card
partial. Valid but old holders make the combined card stale, retaining their real
clock; `holders_state/holders_read_ts` remain independently available. Do not stamp
holders with the newer pool clock. Source completeness and network must describe
the fold actually used; incomplete or mismatched provenance cannot claim a fresh
complete holder count.

## Rendering semantics

Reuse unchanged `NewsHeroCard` and `HeroRecord`. A local card subclass may handle
the `partial` footer, preserving the existing shared renderer. Healthy footers
retain the approved labels; stale/partial markers and tooltips expose their real
observation clocks. Render every card on every update, including unavailable data.
Keep known fields visible when a different field is missing and distinguish this
from a wholly unavailable card. Preserve numeric zero where it is a real reading.

Price is USD per IMD; share conversion is IMD per whole sIMD. Show a cheaper venue
only when the existing producer's fee gate names one. A readable gap with no
eligible venue says `no venue edge`; an unread gap is explicitly unavailable.
Flatten and escape external strings at the widget boundary.

STAKING must retain `APR %` and `trailing 7d`: this is annualised realised delivery
over that window, not the raw seven-day gain or the delivery-rate ceiling. VAULT
shows holder addresses, not unique people. `bid.status == none` means a successful
read found no deployed band; do not present it as an outage or fabricate zero ETH
and a zero-distance band. A deployed but partly unread bid keeps that distinction.
Queue rate is a delivery cap, with queued IMD and days separate; a zero/unread rate
must not produce an invented duration or infinity. No new charts/history are needed.

## Work packages and ownership

1. **Planning agent:** only `docs/surf_pool4_hero_live_plan.md`; record the approved
   contract, source rules, dependencies and checks. No production edits.
2. **Data owner (`launches_hero_data`):** new `data/surf_pool4_hero.py` and focused
   projection tests. Assemble the frozen dictionary from supplied values and
   envelopes, preserving independent states, clocks and unknown/zero semantics.
3. **Widget owner (`news_hero_widget`):** new `widgets/surf/pool4_hero.py` and focused
   widget tests. Adapt the contract to the approved rack design without importing
   data modules or changing the shared renderer.
4. **Root:** `data/surf_models.py`, manager assembly/dispatch, `screens/surf.py`,
   theme CSS, exports, composing/contract tests, live capture, measured layout
   records and follow-up documentation. Mount the hero once and show it only with
   `MODE_POOL4_USER`; integrate the matched source metadata and coordinate commit.

Production paths are relative to `maxpane_dashboard/`; tests live under `tests/`.
Data and widget work may proceed independently after contract freeze. Integration
depends on both. Preserve other work and report cross-owner issues rather than
editing another owner's files. No separate package reviews.

## Verification and delivery

- Begin with focused failing tests; while editing run only changed cases. Tests
  prohibit network and real clipboard access.
- Cover healthy zero, absent values, partial cards, retained stale reads, invalid
  clocks/numbers, mixed pool/market ages, independent holder age, and no-band versus
  unread-band states. Prove detached completions cannot relabel captured old values.
- Assert composited values, units, all titles/subtitles/footers and six equal
  nine-row geometries at 149×45. Exercise narrow resize, recovery and mode switching;
  the native body and other heroes must remain coherent.
- Show the owner a keyless **live production render at 149×45 before** pin
  measurement/hardening, layout-record updates or final review. Temporary capture
  artifacts stay outside Git; source failures remain visible in the UI.
- After live corrections settle, measure actual in-situ geometry. Change pins only
  when measured evidence requires it. Use targeted reversible mutations to prove
  important source-clock and geometry assertions detect regressions.
- Once before commit, run whole affected and composing test files with isolated
  HOME and `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and
  applicable docpins. No full suite without the owner's request.
- One independent final review, one fix wave, and a scoped re-review only if fixes
  touch production code. File Minor-only residuals through the existing process.

Complete POOL4 live confirmation before presenting the next dashboard's three
ASCII proposals in the owner's repeated mockup → API workflow.
