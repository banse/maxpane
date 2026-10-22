# SURF RPC budget — round 1 spec and implementation plan

Date: 2026-10-22. Base: `adfe652e`, `feature/surfboard-hub-9`.
Implementation branch: `feature/surf-rpc-budget`.

## Scope and evidence

Implement R1-a through R1-e from `codex_surf_rpc_budget_plan.md`, then stop for
the owner's independent Claude verification. Tier 2; the brief replaces design
approval and explicitly waives package/final reviews. No live recapture, full
suite, merge, push or tag. R2 rate coordination, endpoint-pool cleanup, general
rolling windows and static-getter suppression remain parked. The existing
POOL4 accumulator gap policy remains unchanged.

The supplied capture is a dated diagnostic sample, not a complete log dataset:
successful bodies are truncated to 600 characters. Use its complete error bodies
and observed batch behavior to constrain fake transports; use existing complete
repository log/getter fixtures for numerical equivalence. In particular,
Mevblocker's response describes a result-count limit as well as a block-range
alternative. Do not reinterpret every such response as a universal 10,000-block
cap. Existing message-based classification remains authoritative.

## Contract and accepted trade-offs

No new dashboard, widget, binding, model key or public flat-dict contract.
On complete fixtures at the same head and injected clock, numerical values,
addresses, rows/order and representable zeros remain equal. Keep each reader's
existing failure shape (`None`, or its existing failed state object); never
publish partial history as a completed empty result. Keep old cache files
loadable without a new version key. New private cursor state is optional,
validated independently and ignored when invalid; old last-good UI payloads
remain usable while a cursor is rebuilt.

Explicitly permitted differences are the corrections named by R1: previously
truncated launch/decoy counts and staker populations, recovered failed state
entries, incomplete-history source state, source observation times reflecting
the actual tier cadence, and corrected block provenance. Getter-derived fees
and queue values must not disappear merely because log coverage failed.

Two choices were considered: preserve existing request counts by trusting a
single response, or spend bounded extra reads to prove an empty range and retry
failed entries. Choose the latter. Integrity takes priority over the brief's
unconditional "no row gets worse" statement. Quantify the exceptions instead
of excluding their HTTP POSTs from the report:

- A genuine empty page requires at least two independent endpoint answers,
  versus one today. A quiet staker tick therefore cannot simultaneously promise
  confirmation and at most one log request. One request is the healthy,
  nonempty incremental case; confirmed empty costs two, before failures.
- At most two state requests per chain applies to healthy known-address POOL4
  reads. Cold path discovery, historical anchor proof and endpoint failures may
  cost more. If 500 arbitrary RPC entries reach a host capped at three, raw
  batching needs at least 167 requests; packing compatible `eth_call` entries
  into Multicall3 reduces that cost without miscounting entries.
- A proven lifetime staker anchor can cost extra on first use. A moving
  eight-week window cannot prove a vault's lifetime at arbitrary future heads.
- Budget rows for unchanged NFT/Base/Robinhood paths must remain unchanged;
  report workload coverage honestly if a fake cannot exercise a complete view.

## Design

### R1-a: card-only work and tier clocks

`SurfCardReader.offer`, `_pool`, `_feed` and `_market` currently offer every
source at 30 seconds and inject `TIER_MEDIUM` unconditionally. Respect each
source's tier TTL and failure backoff, including empty caches and forced view
entry. Coordinate the medium card reads so one source cannot mark the entire
tier successful while another failed. A BOARDROOM visit must not populate or
offer hidden detail collectors.

Use a small POOL4 card read for share price and pool tick, reusing discovered
network/address identity and live vault decimals. Do not run all hook/dripper/
distributor getters to paint two values. The steady-state target is at most
10 outer RPC entries per minute, including any discovery revalidation needed
in that fixture. Address changes invalidate dependent memoized paths.

### R1-b: staker history with an explicit anchor

Replace the head-relative window as the sole completeness criterion. Existing
`_pool4_sweep_is_complete` explicitly admits that omitted, never-moved mints
can pass its checks. It remains a diagnostic, not lifetime proof.

Establish an empty-balance starting point once per network/vault: a verified
deployment receipt if one is already available, or historical `totalSupply`
equal to zero / verified absent code immediately before the proposed floor.
A failed call or bare `eth_call` result `0x` is not that proof. If the current
403,200-block candidate floor cannot be proven, expand backwards or resume a
genesis-based scan; keep the result incomplete meanwhile. Never hardcode the
first-transfer block from the brief as a deployment fact.

Retain the complete balance map and a validated cursor scoped to network and
vault. A small replay tail permits replacement of recently observed transfers
instead of applying them twice; a checkpoint before that tail plus an exact
range replay is preferable to persisting all lifetime raw logs. A new cursor
must not introduce silent reorg loss: cover a 12-block replay horizon, and
invalidate/rebuild rather than retreat a committed checkpoint if the head
falls behind it. This protects the new fold, not the parked R2 rolling readers.
Commit balances/cursor only after the requested range completes. Use explicit
block/log identity, sort in chain order and reject malformed Transfer records
rather than silently dropping them from a purported complete fold.

### R1-c/d: lossless resumable history

Use one owner for each client file. A sweep records chain, address/topics,
start, target head, first unread block and validated accumulated rows. Keep
successful pages across retries/cancellation; freeze or extend the incomplete
target rather than discarding progress when a poll sees a newer head. Do not
reuse a checkpoint for a different filter or chain. Successful sibling event
sweeps stay available until the enclosing launchpad sweep commits.

Keep public failure shapes unchanged while internal progress survives. Cursor
advance is exclusive of the last fully read block, never a requested head.
Confirm an empty range with a distinct endpoint; an unavailable confirmation
keeps it unread. Retry the same missing interval when a host narrows its own
page capacity. A cap learned from one host must not constrain another host;
try other eligible hosts at their own size before narrowing. Keep page/attempt
budgets and partial-is-unknown behavior. Do not follow suggested left edges.

`fetch_decoy_pool_count` must use the history reader instead of the shrinking
recent-window reader. Do not replace its one sparse wide read with blindly fixed
2,400-block pages: at captured head 26,250,043, the 25,000,000 floor would create
521 pages before retries. Try a wide sparse read on a capable host and adapt only
when that host's actual answer requires it. Launchpad compares the completed swept population with
`coinCount()`. A mismatch cannot be treated as complete and must schedule a
rebuild from `LAUNCHPAD_FIRST_BLOCK` without restart, retaining prior good
display data and independent getters until repair succeeds.

### R1-e: coherent state reads

A JSON-RPC array of independent `latest` calls is not a same-block snapshot.
Replace compatible getter rounds with Multicall3, including its block-number
getter inside the aggregate. Retry failed subcalls at that exact block on a
different endpoint; a missing block identity must not produce a purported
coherent result. Preserve successful values when one subcall still fails.

For known addresses, the manager uses a bundled POOL4 read covering hook,
dripper, vault, distributor and both pool venues. Discovery/dependent calls on
cold paths may need extra rounds; pin dependent reads to the established block.
Live vault decimals determine `convertToAssets(10 ** decimals)` exactly as now.
Do not treat a revert as zero or cache an outage as an immutable negative.

For methods that cannot be combined in Multicall3, chunk arrays by the receiving
host's known limit (drpc: three), correlate by request ID and retry only unresolved
entries elsewhere. Distinguish malformed local requests from endpoint failures.
Reuse shared ABI helpers; do not change parked dashboard transport semantics.

## Ownership and dependencies

| Work package | Exclusive files/responsibility | Dependencies |
|---|---|---|
| Plan | `docs/codex_surf_rpc_budget_r1_plan.md` | Brief, captures and named callsites |
| Surf client | `surf_client.py`; its focused history/state batch tests and fixtures | Agreed complete-page/confirmation policy |
| POOL4 client | `surf_pool4_client.py`; its focused state/log tests and fixtures | Agree card and full-state bundle APIs with controller before integration |
| Controller integration | `surf_card_reader.py`, `surf_manager.py`, any optional cursor persistence/coercion, composing tests | Client APIs; sole owner of shared integration files |
| Controller evidence | One committed offline budget command, round report, data rules, decisions, CHANGELOG and probe-date/docpin updates | Same harness run against base and finished tree |

The two client packages run in parallel because ownership is disjoint. Changes
to shared RPC helpers require explicit ownership transfer first; prefer no
change when surf-local adaptation suffices. No worker edits another owner's
tests or files, commits shared changes, or spawns another agent.

## Verification and completion

Write failing focused tests first, then minimal implementation. Each R1 item
has a named killed mutant: bypass TTL, skip the old mint/checkpoint, trust an
unconfirmed empty or advance a failed page, discard successful pages on retry,
and unpin/drop failed state entries. Include changing caps, mixed per-entry
errors, short/malformed replies, cancellation and corrupted/old cursor input.

Use one offline counting command against both base and final code, injected
clocks and committed complete fixtures. Count every HTTP POST, JSON-RPC entry
and REST call. Cover 30-second steady state, cold start, one-day and one-week
catch-up, plus named failure/empty scenarios. Compare complete projections,
not only client outputs. Report correctness premiums and unsupported scenarios
explicitly; no estimates presented as captured request counts.

Before each implementation commit run touched files and composing manager or
screen files whole, with isolated HOME and four worksteal workers, plus fast
guards. Run docpins for changed evidence/docs; registration checks only if that
surface changes. Never run the full suite in this round. Commit one item or a
tight dependency group with evidence/mutants in its body. Record the before/
after table, actual test counts, decisions and any unmet outcome in the round
report. Stop after round 1 for Claude verification; no implied R2 approval.
