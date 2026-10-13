# AGENT second-row card adjustments

Approved owner request: 2026-10-13. Tier 2: the EARNINGS card replaces FEEDBACK
and introduces a public data source and primitive contract fields. Preserve the
twelve-card rack. Target less than 1,000 changed production lines; one final
review, no package reviews, no full suite. Native owner size: 149×45.

## Required behavior

| Card | Content and frame | Outer footer |
| --- | --- | --- |
| OWNER | Preserve linked/copyable owner address and pairing date. Always neutral frame and border text. | Preserve `OPEN / COPY`. |
| RUNTIME | Remove widen indicator. Orange frame/border text only when software needs an update; neutral otherwise. Omit the inner caption for an unknown update check. | `since` plus last connection time; owner approved connection time because the API exposes no runtime restart timestamp. Hover explains that distinction. |
| MODELS | Always neutral. Put the advertised model and effort on the second inner row, centered with exactly one separating space; effort uses normal weight. | Preserve configuration label. |
| EARNINGS | Replace FEEDBACK. Inner title `TOKENS`; large digits count distinct earned token assets, never token units or value. Inner caption `x worked on` counts distinct assets with accepted work by this selected seat. Green only when such an asset launched within the preceding 24 hours. | `x CLAIMED`, counting distinct assets claimed. |
| COLLAB | Always neutral; preserve existing content. | Preserve existing label. |
| NODES | Always neutral. Three rows: `oracle`, `launches`, `other`, representing accepted work categorized by type without double counting. Inner caption `work by type`. | Preserve history label. |

No visible stale text is reintroduced. Missing data remains distinct from zero;
real pending work paints loading and completed failure paints unavailable.

## Source evidence and counting rules

The requested public reference is
`https://explorer.imd.fun/wallet/0x84F4b7424e1B0464f9C749725C1F34bed9AA8aDA/earned?sort=job-asc`.
The live page was captured on 2026-10-13. Its server-rendered `EarnedTable`
contains all 229 rows, representing 226 distinct valid `(chainId, tokenAddress)`
pairs, six builder rows and eleven rows with `claim.state == "claimed"`. Three
served held rows have a null token address: these are legitimate rows awaiting
an identifiable asset and must not be invented as earned assets or invalidate
the whole table. Counts are
capture observations, not application constants. Counting launch rows would
include the held rows with no token address; identity must come from assets.

Each earned row supplies `launchId`, `chainId`, `tokenAddress`, `cuts`, `jobId`,
`at`, and `claim.state`. The explorer defines the builder cut as accepted work on
the launch's underlying job. A wallet can own multiple seats: intersect builder
rows with the selected seat's accepted work job IDs before counting `worked_on`
or activating the green frame. Wallet earnings and claims are wallet scoped;
the tooltip must say so. Never infer that an owner's every builder row belongs
to the selected seat.

The public explorer `/api/earned?wallet=...` returns claimable IDs and unlocks
only; it cannot establish earned totals or completed claims. Its value endpoint
is unnecessary. A bounded probe found no direct control-plane wallet earnings
route. Read the served table once per owner on a slow clock through an isolated
GET-only source; do not synthesize missing facts from claimable counts.

The smallest source implementation decodes JSON strings from the page's inline
Next flight payload, resolves the dynamic module identifier for `EarnedTable`,
and parses its props with the JSON decoder. Never execute JavaScript. Validate
the matching provider wallet, table shape, row identity and supported claim
state before publishing counts. Locate the export name rather than a fixed
generated module identifier. A served empty table is a real zero; missing,
malformed or truncated table data is unavailable. Bound response bytes and row
count. A future explorer format change must fail closed.

Token identity is `(positive chain ID, lowercased full token address)`, not symbol,
launch ID or job ID. Earned counts include each valid distinct asset once;
claimed counts include it when any matching row is explicitly `claimed`.
Recency uses the row's launch timestamp and injected `now`; future, invalid and
missing timestamps cannot activate green. The same token can have several jobs
or launch rows without being counted twice.

Raw `/workers` supplies `connectedAt`; it is not a restart receipt. Use the latest
valid matching-seat device connection timestamp, preserve the independent worker
source clock and explain the scope on hover. Do not substitute read time.
Raw seat `work[].launch` is a launch **kind**, not proof of an actual completed
launch; NODES must join accepted work with canonical launch evidence before
assigning it to the launches category. Oracle takes precedence over launches.

## Contract and ownership

Freeze these primitive seams before implementation:

- RUNTIME adds `connected_ts`, `connected_state`, `connected_read_ts` and retains existing update-state facts.
- Replace the `feedback` hero section with `earnings`: `state`, `read_ts`,
  `earned`, `worked_on`, `claimed`, `worked_recent`, `owner`.
- NODES retains its original `rows` for hover and adds nullable `oracle`, `launches`,
  `other`, `known_jobs`, `total_jobs`, `launch_state`, `launch_read_ts`. Counts
  represent accepted work entries; coverage counts distinct non-oracle jobs.
  The launch fact is a validated live launch ID and positive chain ID from the
  exact job read, including testnets to match the explorer's scope. Requested,
  blocked or unread launches cannot become launched work.

One owner per file; controller may reassign a whole package before work starts.

1. **Research/planning owner:** this plan and temporary public captures only.
   Determine the earnings source and freeze counting semantics. No production
   changes or subagents.
2. **Controller/data owner:** `surf_models.py`, `surf_manager.py`,
   `surf_agent_hero.py`, cache/source integration, corresponding contract,
   projection and manager tests. Own any selected-seat or launch normalization
   changes, or delegate complete disjoint files explicitly. Earnings needs an
   owner-keyed retained cache, a bounded slow TTL and failure backoff, actual
   in-flight status, and no blocking network await in a widget/screen handler.
   Existing seat switching must not paint the prior owner's counts.
3. **Earnings source implementer:** own
   `maxpane_dashboard/data/surf_agent_earnings.py`, its source fixtures and
   direct tests only. This module owns the pure decoder, strict cached-point
   coercion, earnings summary and `OwnedHttpClient` subclass. One public
   GET; injected HTTP transport; no key, signer, calldata or claim action.
   Depends on the source and primitive contract decisions above. This package
   may run in parallel with the UI package and controller integration.
4. **UI owner:** `widgets/surf/agent_rack_hero.py`, its widget tests and native
   hero composing tests. Preserve
   card shape, address handling and click actions while changing the specified
   content and colors. Do not edit data files. Depends on frozen primitives.
   **Independent work-membership owner:** `surf_agent_work.py`, its focused tests
   and three exact job fixtures. Controller owns `surf_agent_card_sources.py`
   to join these facts with owner earnings and manage the independent clocks.
5. **Controller:** integrate, run targeted composing tests, render live keyless
   data at 149×45 and show the owner before pin hardening/docs/final review.
   Then measure layout through the native harness, update only necessary pins,
   run touched/composing files once, fast guards and docpins, and request the
   single final review. Commit locally; do not push.

## Verification

Test source decoding and distinct-asset counts with recorded fixtures, including
duplicate launch rows, explicit empty table, malformed/truncated payload,
unsupported claim state, wallet mismatch and response bounds. Mutation proof
must kill at least the duplicate-count and claimed-state mistakes.

Test selected-seat accepted builder attribution separately from same-wallet
other seats, the 24-hour boundary, no false green on missing dates, retained
cache failures, actual pending state and seat switches. NODES needs an oracle
that also links to a launch, a launch intent that never deployed, multiple
accepted work entries and genuine zero categories. Keep full detail rows
independent of the visible record window.

Composited widget checks must inspect actual border color, centered model row,
normal-weight effort, hidden unknown runtime caption, no widen hint, EARNINGS
digits/captions and all three NODES rows. Recheck OWNER copy/explorer behavior
without real clipboard access. No tests use the network.

Temporary source captures: `/tmp/agent_earned_page.html`,
`/tmp/agent_earned_flight.txt`, `/tmp/agent_earned_rows.json`,
`/tmp/agent_earned_api.json`, `/tmp/agent_probe_seats_3.json`,
`/tmp/agent_probe_workers.json`. Promote only the smallest relevant exact capture
or documented structural fixture into `tests/fixtures/` during implementation.
