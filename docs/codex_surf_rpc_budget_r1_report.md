# SURF RPC budget — round 1 implementation report

Date: 2026-10-22. Branch: `feature/surf-rpc-budget`.
Base: `adfe652e559475c39322c12d5f44d6f7e9f516e4`.
Client package: `9e244f06`. Controller/evidence package follows that commit.

## Result and review decisions

Implemented R1-a through R1-e. Stop here for the owner's independent Claude
verification; R2 is not authorized by this report. No merge, push, tag, live
probe, new endpoint pool, shared classifier change or public model key.

- BOARDROOM uses its small POOL4 quote rather than all contract state. Actual
  discovery is revalidated on changed channel data or after 90 seconds; cached
  paths still validate their onchain links. Medium sources use independent
  90-second success and 60-second failure clocks, including forced view entry.
- STAKERS proves an empty historical balance sheet (zero totalSupply/absent code)
  or starts at genesis. A private checkpoint in the existing last-good slot
  holds balances before a 12-block replay tail. Failures do not advance it;
  corrupted/old state rebuilds and unchanged display values keep their timestamp.
- Launchpad cannot publish a count known to disagree with the factory; it retries
  a cold rebuild automatically. The factory witness is pinned to the frozen sweep
  head. Decoy counting uses the full range and deduplicates pools.
- Incomplete history keeps acknowledged pages in bounded process-local buffers,
  independently confirms empty ranges, applies each endpoint's own learned cap,
  and yields after 256 accepted pages per invocation. A stated 50-block cap may
  go below the 300-block blind-halving floor; it still obeys that page budget.
- Known POOL4 state and both venues come from Multicall3 at one block, with the
  dependent share conversion pinned to it. Failed subcalls retry on another
  endpoint. Generic Surf batches preserve successful IDs and cap drpc arrays at 3.

The supplied brief had conflicting outcomes. Correct empty confirmation takes
precedence over “no budget row gets worse.” Two state requests applies to healthy
known paths; discovery, historical anchor proof and failures may need more.
The existing POOL4 accumulator >24h-gap rule remains unchanged.

## Reproduce the budget

Create a separate baseline directory with the exact base commit (the destination
must be new), then run the single committed measurement command:

```sh
mkdir /private/tmp/maxpane-rpc-budget-base-adfe652e
git archive adfe652e559475c39322c12d5f44d6f7e9f516e4 maxpane_dashboard tests pyproject.toml README.md CLAUDE.md | tar -x -C /private/tmp/maxpane-rpc-budget-base-adfe652e
.venv/bin/python scripts/measure_surf_rpc_budget.py --baseline /private/tmp/maxpane-rpc-budget-base-adfe652e --repo . --output /private/tmp/surf-rpc-budget-final.json
```

The baseline directory already exists in this session. The command counts
actual fake-transport HTTP dispatches, JSON-RPC entries and REST GETs, including
retries and empty confirmations. Multicall subcalls are recorded separately.
`codex_surf_rpc_budget_r1_budget.json` commits the counts, projection digests,
import roots and production/fixture hashes. The full regenerated JSON also
contains the compared projections. These are 19 deterministic scenarios.

| Scenario | RPC requests before → after | Entries before → after | REST before → after | Projection equal |
|---|---:|---:|---:|---|
| pool4-known-state | 6 → 2 | 73 → 2 | 0 → 0 | true |
| launchpad/cold | 60 → 101 | 60 → 101 | 0 → 0 | true |
| launchpad/steady | 10 → 16 | 10 → 16 | 0 → 0 | true |
| launchpad/day | 17 → 32 | 18 → 35 | 0 → 0 | true |
| launchpad/week | 88 → 174 | 89 → 177 | 0 → 0 | true |
| decoy/cold | 2 → 2 | 2 → 2 | 0 → 0 | true |
| decoy/steady | 2 → 2 | 2 → 2 | 0 → 0 | true |
| decoy/day | 2 → 2 | 2 → 2 | 0 → 0 | true |
| decoy/week | 2 → 2 | 2 → 2 | 0 → 0 | true |
| stakers/cold | 9 → 16 | 9 → 17 | 0 → 0 | true |
| stakers/steady | 9 → 3 | 9 → 3 | 0 → 0 | true |
| stakers/day | 9 → 9 | 9 → 9 | 0 → 0 | true |
| stakers/week | 9 → 17 | 9 → 17 | 0 → 0 | true |
| stakers/reloaded | 9 → 3 | 9 → 3 | 0 → 0 | true |
| stakers/lifetime-late | 9 → 17 | 9 → 19 | 0 → 0 | false |
| boardroom/cold | 7 → 6 | 57 → 39 | 4 → 3 | true |
| boardroom/steady-minute | 14 → 4 | 114 → 4 | 8 → 0 | true |
| boardroom/revalidation-minute | 14 → 5 | 114 → 5 | 8 → 4 | true |
| boardroom/180s | 42 → 17 | 342 → 50 | 24 → 7 | true |

All measured projections match except the intentional lifetime-history fix.
At `firstTransfer + 403200`, the baseline claims complete coverage with 347
holders; the full corpus and the new code have 348. The old missing holder also
changes concentration. Healthy state/card values are unchanged.

BOARDROOM's steady minute is two polls. Its 180-second row is six polls in a
half-open interval; the channel slot starts fresh, so it needs one rather than
two GETs in that interval. The POOL4-state row excludes history/discovery.

## Evidence and limitations

- The user-supplied capture was taken on 2026-10-22; no new network reads occurred.
  Its successful bodies are truncated to 600 characters. Complete existing
  getter/1,116-Transfer fixtures supply values; complete captured errors constrain
  provider behavior. Launchpad/decoy corpora are pre-existing generated fixtures.
- Catch-up advances the fixture head at 7,200 blocks/day without inventing new
  events. It measures quiet catch-up, not today's live log density or latency.
- The announcement, historical zero-supply oracle and ETH/USD quote used by the
  harness are explicitly synthetic. Actual discovery logic still runs.
- No current IP throttling or cross-reader rate coordinator is simulated. RPC
  error, partial-response, cap-change and cancellation cases have separate tests.
- This command covers the changed POOL4/card/launchpad/staker projections. It does
  not prove equality of every all-view manager flat dict or measure complete NFT,
  Base, Robinhood or work/current-swarm workloads. Their collectors are unchanged.

## Acceptance outcomes that are deliberately not claimed

- The one-log-request quiet STAKERS target is missed: quiet pages need two
  independent answers (plus one head request). A nonempty incremental page uses
  one log request. Catch-up may span more pages.
- “No budget row gets worse” and cheaper launchpad cold/week reads are not met:
  the table includes the integrity premium rather than hiding it.
- Same-block two-request state is verified for healthy known metadata. Failed
  identity/decimals/subcalls can require retries; cold address discovery costs more.
- A 12-block tail handles bounded recent replacements, not arbitrary deep reorgs.
  Pending page buffers survive retries/cancellation in-process, not process exits.
  The completed staker checkpoint does survive disk save/reload.

## Validation

- Final affected data/client/manager/cache/shared set: **1,258 passed**, isolated
  HOME, four worksteal workers, 7.21 seconds. Includes old cache fixture loaders,
  saved staker checkpoint reload and unchanged shared-RPC guard tests.
- Earlier combined run including three whole composing screen files: **1,607
  passed, 6 failed**. Two in-scope test fixtures were corrected and pass in the
  final data run (a 13-launch slice had a 146 count; the blind-halving test used
  an explicit 50-block cap). The other four are baseline failures listed below.
- Fast guards: **128 passed**. Docpins: **12 passed**. `git diff --check` passed.
- Before the controller/evidence commit, its whole touched/composing set was
  rerun: **471 passed** in 7.45 seconds; **128 guards** and **12 docpins** passed again.
- **14 named mutants killed**, with byte-for-byte restoration. Definitions are
  committed in `tests/fixtures/surf/rpc_budget_mutants.json`: 6 history/batch/count
  mutants, 4 POOL4 state/progress mutants, 3 card/staker controller mutants and
  1 wire-counter mutant. Each R1 item has a named regression proof.
- No full suite or Python 3.11/Textual 8.1.1 run; these remain the independent
  verification assigned to Claude by the brief. No registration surface changed.

The four unchanged screen failures were independently rerun at the exact base
commit, **4 failed in 4.27 seconds**, with the same assertions:

1. `test_surf_pool4_screen.py::test_the_bindings_are_refresh_and_the_two_view_toggles`
2. `test_surf_pool4_screen.py::test_the_three_bodies_are_never_showing_at_once`
3. `test_surf_pool4_market_screen.py::test_exactly_one_hero_shows_in_every_mode[launchpad]`
4. `test_surf_pool4_market_screen.py::test_exactly_one_hero_survives_every_transition_between_bodies`

They expect old bindings and `SurfHero` instead of the existing
`SurfLaunchpadHero`. No screen implementation or test was changed in this round.
Follow-ups and remaining gates are in `codex_surf_rpc_budget_followups.md`.
IMDB capture recorded `none`: these changes supplied no new protocol observation.
