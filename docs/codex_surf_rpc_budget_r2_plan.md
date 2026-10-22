# SURF RPC budget — round 2 spec and plan

Date: 2026-10-22. Continue `feature/surf-rpc-budget` from the completed R1 commits.
The owner authorized R2 and deferred independent review until both rounds are
finished. Keep the brief's other restrictions: offline fixtures only, no full
suite, merge, push or tag. No intermediate agent review. R1 findings, named
exceptions and the four proven baseline screen failures remain documented in
`codex_surf_rpc_budget_r1_report.md` and `codex_surf_rpc_budget_followups.md`.

## Scope and decisions

Implement R2-a–d in the Surf family only. Public flat-dict keys, widget layout,
bindings, old cache versions, separate state/log pools and the POOL4 >24-hour
accumulator gap rule remain unchanged. On complete fixtures, at the same head
and clock, projected values must match. Expected differences are corrected
reorg results and source timestamps that reflect fewer actual observations.
Failed reads never become zero, empty, complete or cached immutable facts.

Choose a small Surf-only scheduler and rolling buffer over modifying the
app-wide RPC policy. This adds explicit injection at a few constructors but
keeps parked dashboards' behavior unchanged. No broker, external cache or new
background polling service is needed.

Three brief assumptions require correction:

1. IMD `name()` and `symbol()` are owner-mutable, documented in
   `surf_addresses.py:286` and `surf_PRD.md`. Keep their live reads. They are not
   candidates for permanent memoization. An unchanged fixture is not proof of
   immutability for `imdEthPoolId()` or any other getter either.
2. Base/Robinhood launch clients currently read state, transactions and receipts;
   they have no historical log pool. Do not invent one to satisfy a numerical
   pool target. Supplied captures prove neither two healthy Base archive hosts
   nor any Robinhood archive host. Preserve existing RH configuration, state the
   evidence gap, and do not claim the two-archive-provider guarantee as verified.
3. One head acquisition per chain means deduplicated explicit head reads within
   a logical refresh. Keep embedded Multicall block witnesses. Failover retries,
   exact-block availability checks and independent retained NFT inspections
   cannot honestly be counted as free or silently rebound to a newer head.

## R2-a: bounded rolling log windows

Add a Surf-only helper layered over R1's complete/resumable history reader.
Identity includes network, address and canonical topics/filter, never a label
alone. Retain a bounded complete window and its covered interval. With old head
H, request from `max(requested_start, H - 11)` through the new target head;
replace the entire overlapping interval, including rows absent from the new
answer, and trim outside the requested window. This rereads the last twelve
old blocks plus new blocks. Do not merge the replay tail additively.

Return the same complete raw-log shape to existing decoders. Deduplicate by
chain log identity, preserve deterministic chain order, reject malformed
positions and remove replaced/removed logs. Failed or unconfirmed empty tails
retain the prior complete buffer and do not advance coverage. Changed filters,
heads behind the retained checkpoint, or a missing older interval require a
safe rebuild; never serve a truncated buffer as complete. Bound retained rows
and keys; eviction means reread, not invented completeness.

Integrate recent Surf filters, the launchpad CurveSwap day, and POOL4 hook,
swap and drip windows. Keep Seaport's existing full OrderFulfilled query and
IDMD post-filter: the NFT item token is not an indexed topic that can simply be
added to the current filter. Its incremental wire window supplies the saving.

Consumer arithmetic matters: launchpad lifetime counters currently accept only
blocks above the committed cursor, and POOL4 has its own accumulator. Replacing
raw recent rows alone does not undo an already-counted orphaned event. Add a
checkpoint/replay boundary where an affected aggregate needs it, or explicitly
report the narrower achieved window guarantee. A 12-block reorg test must check
the projected counts, volumes, traders and burn results as applicable, not only
the helper's row set. Preserve the existing POOL4 gap policy.

## R2-b/d: shared transport and read-cycle head

The controller owns `surf_transport.py`. Default clients share one coordinator
within their reader event loop, held in a weak loop registry. Injected clocks
can use an explicit coordinator. No lock is shared across event loops and no
UI-thread await or hidden-view request is added. Standalone clients participate
in their loop's coordinator or accept an injected fake; parked clients retain
`rpc_common.pace`.

Scheduler contract: one async request admission/dispatch operation around the
client's existing HTTP send, plus host cooldown state. Key by normalized host
so `/fast` and plain URLs cannot bypass pacing. Inject monotonic time, wall
clock and sleep. Recheck cooldown under a host lock immediately before a start;
serialize starts with the strictest configured interval for that host. A 429
records numeric or HTTP-date Retry-After, with a finite fallback for invalid
values. Later requests skip that host while other endpoints continue. Do not
sleep through a long cooldown inside the first endpoint's retry loop. Requests
already dispatched before the 429 response cannot be recalled.

Keep NFT's budgets, deadline, response-size and chain-identity validation. Its
per-host semaphore is not a substitute for sharing admission with other Surf
clients. Consume HTTP budget only for actual dispatch. Cancellation releases
locks and stops owned work; a cancelled waiter must not leave a phantom slot or
permanently pending shared head.

Head seam agreed with the controller: `@read_cycle` creates a task-local context
only when none exists; child tasks inherit it. `await transport.head(chain,
loader)` single-flights an explicit head read and returns a validated positive
hex height. Failures are not memoized. A new refresh gets a fresh context; a
long-running old task must retain its own context. Count recovery attempts.
Multicall's own block number remains the provenance of that EVM execution.

A shared head is not proof a fallback node has reached it. Before accepting
logs at a target height, require evidence that the answering URL serves that
exact block, coalesced within the same read cycle. A validated exact-height
header is the simplest witness; check its number and known hash, and reject a
missing/mismatched answer. Count these extra calls. Do not claim this guarantee
until the real log path and corresponding lagging-node fixture exercise it.

## R2-c/d: pools, immutable facts and NFT work

Ethereum Surf/POOL4 log pools already use Tenderly and Mevblocker, without
llama/drpc/nodies/publicnode. Preserve that split and update stale cap comments;
do not remove useful state hosts merely because they reject archive logs.
Where dead endpoints remain in Surf-owned paths, remove them using the supplied
record. A temporary 429 justifies cooldown, not a permanent ban without a
verified replacement. No fresh endpoint is labelled verified without evidence.

Memoize only successful, validated immutable facts, scoped by chain, address
and relevant implementation/deployment identity. Read decimals first; never
substitute 18. Suppress a getter only after explicit deterministic EVM-revert
evidence, not a timeout, empty return, missing code, unsupported historical
block or rate limit. Use bounded revalidation where immutability/implementation
stability is unproven. Failed initial reads remain retryable.

BOARDROOM retains already proven NFT deployments instead of re-proving each
every 120 seconds. New/changed candidate identity and proof revisions remain
eligible, and factory discovery continues. The detailed NFT view still updates
mutable supply/mint/source facts on its existing cadence. Retaining proof must
not refresh its timestamp or promote partial evidence to verified.

Batch independent NFT inspection operations at the same pinned block using the
existing `rpc_batch` API where host support permits; keep dependency boundaries
and per-field failures. Robinhood's existing single-call fallback is not
silently replaced with an unverified array assumption. Existing progress limits
and invalidation on changed proof inputs/runtime remain in force.

## Disjoint work packages

| Owner/package | Files and responsibility | Dependency |
|---|---|---|
| Plan | This file only | Brief, R1 report and focused source reads |
| Controller | New Surf transport/head helper; `surf_manager.py`, `surf_card_reader.py`, launch Base/RH adapters, budget command, final evidence/docs | Freeze transport API before client wiring; integrate rolling/cycle seams |
| Surf client worker | `surf_client.py` and its dedicated tests | Transport/head interface and rolling helper API |
| POOL4 client worker | `surf_pool4_client.py` and its dedicated tests | Same APIs; preserve R1 bundle and retry semantics |
| Rolling helper worker | New shared Surf rolling module and focused tests; R1 history helper only by explicit ownership agreement | Complete-read callback contract; no other owner edits this file concurrently |
| NFT worker | `surf_nft_client.py`, `surf_nft_chain.py`, `surf_nft_manager.py` and dedicated tests | Shared transport contract; starts when a concurrency slot is free |

Execute independent ownership packages in parallel within available slots.
Root integrates shared manager files after APIs settle. No worker spawns agents
or edits another package; transfer ownership before crossing a file seam.

## Acceptance and finish

Use failing offline tests followed by minimal implementation. Required named
mutants cover additive replay, missing last replay block, bypassed shared lock,
ignored Retry-After, stale cross-cycle head, lagging log node acceptance,
memoized failure and redundant proven-NFT work. Prove changed collector behavior
through manager projections and unchanged complete fixture values.

Run the same committed budget command against R1 and R2 with identical fixtures;
retain the original-base comparison where useful. Include actual POSTs, entries,
REST calls, block witnesses and confirmation/retry premiums. Add cross-client
same-host concurrency and cooldown scenarios with injected time. State gaps in
NFT/Base/RH workload evidence instead of claiming a whole-app proof.

Before each commit run touched and composing files whole with isolated HOME and
four worksteal workers, fast guards and changed docpins. No full suite or live
capture. Update the round report, follow-ups, decisions, CHANGELOG and relevant
endpoint/probe documentation with actual outcomes and deviations. Independent
review occurs only at the owner's requested final stage.
