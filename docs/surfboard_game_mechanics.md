# SURFBOARD hub data research

The new hub is MaxPane dashboard 9. It provides a common entrance to the seven existing
SURFBOARD views and a command-driven IMD monitor. This research fixes the meaning and source
of each headline and meter before implementation. The approved four-row rack remains the layout.

Checked 2026-10-09 CEST, including live GET requests at 22:29–22:31 UTC on 2026-10-08.
Branch: `feature/surfboard-hub-9`, based on `6a22d54b`.

## Evidence and existing code

- [IMD API reference](https://imd.fun/docs/): public network, seat, job and earnings routes.
- [Network snapshot](https://api.imd.fun/swarm): health, counts, seats, owners and recent events.
- [Seat summaries](https://api.imd.fun/seats/records): submitted-work outcomes for the recorded seats.
- [Contributors](https://api.imd.fun/contributors): device effort and broader attempt accounting.
- [Hourly steps](https://api.imd.fun/steps/hourly): 24 accepted-step buckets, oldest first.
- [IMD terminal](https://imd.fun/): frontend source inspected; snapshot polling is 15 seconds.
- `/Library/Vibes/aidude/docs/imd-api-changelog.md`, especially the September 26 account of
  attempt populations and the October 8 earnings additions. Historical notes are leads; current
  responses and headers take precedence.
- `data/surf_swarm.py`: current board groups contributor devices by token and ranks accepted,
  acceptance rate, then token ID. `widgets/surf/swarm_agent_hero.py` currently uses seat totals
  for acceptance and contributor totals for rank: the visible inconsistency to remove.
- `data/surf_client.py::fetch_launchpad`, `LaunchpadState` in `data/surf_models.py`: full
  `swaps_by_coin` is keyed by pool ID; displayed `coins` is capped. Never use the displayed
  slice to calculate a whole-population meter.
- `data/surf_pool4.py::measured_split`: actual inference/burn/reward counter proportions;
  reward is the distributor's entire reward leg, not just stakers.

## Counter populations differ

| Response | Seat 420 attempts | Accepted | Rejected | Failed | Pending |
|---|---:|---:|---:|---:|---:|
| `/seats/records` | 3,392 | 3,253 | 40 | 21 | 78 |
| `/swarm.seats` | 3,392 | 3,253 | 40 | 21 | 78 |
| `/contributors`, device row | 3,442 | 3,222 | 40 | absent | 180 |

Seat summaries count submitted work. Contributor attempts additionally cover other device
activity; its pending bucket includes failures/unscored attempts. Neither pending bucket is a
running-job count. Route caches also differ. Forcing these numbers to match by subtraction,
selecting the greater value, or swapping only one endpoint's numerator would be incorrect.

There is a second defect to defend against: the sampled `/swarm.seats` contained 894 entries,
one with `attempts=0, accepted=1` (seat 1836). The separately sampled `/seats/records` had
890 rows, all satisfying the outcome partition, and seat 1836 had `attempts=1, accepted=1`.
Different population sizes are not proof of missing records: the endpoints have different
membership and cache timing. The hub must not reconcile them by inventing rows.

**Decision:** `/seats/records` is the single authority for submitted-work totals, acceptance
rates and rank in the hub, AGENT and BOARD. The same validated snapshot supplies all of them.
`/contributors` supplies effort, runtime usage and explicitly named receipt statistics only.
`/seats/{id}` supplies identity, history, collaborators and node details; its top-level totals
must not overwrite one selected row of the ranking snapshot.

Observed response headers: `/swarm` `max-age=10`; `/workers`, `/contributors` and
`/steps/hourly` `max-age=30`; `/seats/records` **`max-age=600`**. A successful fetch is not proof
that the record summary was recomputed then. Use “read HH:MM” and disclose the ten-minute
upstream summary cache; record details can be newer. One capped seat-detail request timed out
after 25 seconds while the summary endpoints answered. Hub painting must not await full details.

The observed network snapshot reported 864 online, 9 working, 1,134 completed jobs, 237
completed oracles and 32,621 accepted steps over 24 hours. Those are five distinct counters.
Worker heartbeats reported 863 devices, 9 occupied slots and capacity 1,569 in their own
response. Dividing the snapshot's working number by the worker endpoint's capacity would mix
populations and times.

## Meter evaluation

The rack has room for eight meter cells. A filled bar needs a natural denominator; unbounded
activity is better shown over time. A full bar is not a health or investment recommendation.

| Card | Selected meter | Why it fits | Rejected alternative |
|---|---|---|---|
| ANNOUNCE | **ALERT**, fired detectors / registered detectors | Identifies signal activity without an invented traffic target | Posts / arbitrary maximum; counting unknown detectors as quiet |
| SWARM | **24H**, eight sums of three adjacent hourly accepted-step buckets | Shows workload changes, including quiet periods, from an actual historical endpoint | “BUSY” formed from leases / agents, or from different endpoint snapshots |
| AGENT | **PASS**, selected seat accepted / attempts | Natural 0–100% range; same source as its headline and rank | Accepted / accepted+rejected, which hides failed and pending work |
| BOARD | **PASS**, sum accepted / sum attempts over the same recorded-seat snapshot | Shows fleet acceptance weighted by work, alongside the selected rank | Average of seat percentages; online devices / enrolled seats |
| LAUNCHPAD | **TRADE**, coins traded in 24h / factory coin count | Measures how much of this launchpad is active | New coins / arbitrary daily goal; counts from the top-20 display slice |
| POOL4 | **STAKE**, vault IMD assets / token `totalSupply()` | Existing same-network fields, clear token-unit denominator | “VOL” without a scale; an APR inferred from the dripper's delivery cap |
| PROTOCOL | **BURN**, measured burn counter / sum of inference, burn and reward counters | Reuses the protocol's existing measured split | Quoted policy percentage or queued executor balance presented as burned |

For POOL4, `totalSupply()` means the token contract's current total supply, not a third-party
free-float estimate. The display description is “share of total supply staked.”

ANNOUNCE uses the current eleven `SIGNAL_NAMES`; derive the count from the contract and bind
it to the visible detector list with an agreement test. Only `fired` fills the bar; `watch`
does not. Any unknown detector makes the aggregate meter unavailable, while known fired and
unknown counts remain separately visible in its details.

LAUNCHPAD requires an authoritative full-population getter, a completed historical sweep
that agrees with that population, and a complete rolling-day swap read. Use the uncapped
pool-ID map; matching only the length of a render-capped list is insufficient. Failure or
catch-up gives “indexing”/“unavailable,” not a smaller denominator. Coin tickers never join data.

POOL4 numerator and denominator must describe the same discovered token/network and one
successful protocol snapshot; live token decimals apply. PROTOCOL reuses the existing split
function, including its zero/unknown behavior. Amounts waiting in a burn executor stay queued.

For percentage meters, zero numerator with positive denominator is real 0%. Zero denominator
is “no attempts,” “no coins,” “no supply,” or “no flow,” as appropriate, with no percentage.
Out-of-range values are inconsistent data, never silently clamped into a healthy full meter.
SWARM uses the shared sparkline's linear min–max scale across its eight buckets; the detail
readout states that range in accepted steps per bucket. An all-zero series says “quiet 24h”;
a flat nonzero series shows its constant count. Missing buckets are never filled with zero.
Its total need not equal `/swarm`'s separately cached rolling counter.

SWARM TOKENS, PORTFOLIO and EARNINGS remain planned cards with unlit meters in this release.
No P/L, dollar earnings or fee estimate is inferred from an allocation or a wallet balance.

## Interactive terminal

The website's command parser supports inspection/navigation (`?`, `help`, `status`, `jobs`,
`seat`/`agent`, `find`, `me`, `grep`, `open`, `clear`), plus website-specific sound, screenshot
and animation commands. It does not submit jobs. Native inspection parity is compatible with
MaxPane's read-only/keyless constraints.

The live feed has a bounded snapshot of recent `job`, `node`, `done`, `review`, `site`,
`launch` and `agent` events. Timestamp, role, step, state and objective support the machine
log style. Group adjacent rows by job ID, not by matching objective text. A snapshot is not
a durable event stream: after missed polls, no claim of complete history is possible.

Current `/jobs?limit=3` returned three jobs; defaults return a bounded page. The legacy
“no pagination” claim in the client/rules must be corrected during implementation. The hub
feed does not depend on enumerating job pages; `/swarm.counts` supplies global totals.
