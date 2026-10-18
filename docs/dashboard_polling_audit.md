# Dashboard loading and polling audit — 2026-10-18

## Scope and behavior

Measure every currently accessible dashboard using public, keyless sources and isolated copies
of the local cache. Distinguish wrapper return, all relevant background reads settling, and
local snapshot projection. A settled cycle may contain failed sources; it does not certify
complete data. Record source errors and time-limited measurements separately.

Keep the existing 30-second polling cadence. A cycle includes the awaited manager fetch and
the relevant detached reads reported by `is_loading(view)`. Discard ticks and manual refresh
requests while that cycle is busy; never queue a replacement or replay overdue ticks. If the
reader thread was blocked across deadlines, advance to the next future deadline before
admitting another poll. A read that completes shortly before the next scheduled tick may be
followed by that tick. This is a cadence, not a 30-second delay after completion.

Opening, reopening and changing dashboard identity still start an immediate bootstrap and
show any cached snapshot. Bootstrap must work even when activation already started a README
read. Preserve cancellation, generation checks, drain barriers, partial/final publications,
source TTLs, request budgets and concurrency inside an accepted cycle. Hidden views do not
poll. No UI/layout, data contract, cache format or endpoint changes.

NFT profiling has measured repeated objective parsing: 981 discovery candidates trigger
97,447 regex calls per publication. Prepare UUID and commit references once per projection,
while preserving the existing directed joins, iteration/overwrite order and evidence gates.
Do not retain derived references across calls: new facts must be visible immediately.

## Work packages and ownership

1. Root owns this specification, `data/reader.py` and `tests/data/test_reader.py`: failing
   concurrency regressions, minimal admission/cadence fix, injected scheduling clock.
2. NFT performance specialist owns `data/surf_nft_rules/catalog.py`,
   `data/surf_nft_discovery.py` and their focused tests: regression first, ephemeral reference
   preparation, before/after profiling and identical-payload comparison. Independent of 1.
3. Dashboard benchmark specialist owns `/tmp/maxpane-poll-audit` measurement scripts/results:
   frozen baseline at `84855401`, live first/warm cycles, request/error counts, accessible
   view coverage and explicit limitations. Independent of 1/2; root incorporates results here.
4. Root integrates packages, measures the changed NFT path, runs touched/composing tests and
   guards, obtains one final whole-change review, records residuals and commits locally.

Estimated production change under 1,000 lines; no per-package reviews. One final review and
one fix wave, with a scoped re-review only if production code changes during that wave.

## Validation

- Held synchronous and detached reads across multiple deadlines: one fetch, passive partial
  and final publication, no catch-up cycle; next future tick can start.
- Reader blocked by CPU work plus a burst of UI requests: no trailing queued fetch.
- Initial activation plus immediate UI fetch: one cycle; setter-started README cannot suppress
  catalogue bootstrap. Existing identity/cancellation/cache-reopen tests remain green.
- Failure and slow projection skip elapsed deadlines without leaving loading stuck.
- NFT joins preserve transitive/cyclic links, identity isolation, source order and unknown
  mint claims; changed objectives on the next call invalidate all derived references.
- Mutation proofs for changed concurrency/decoder behavior. No test network calls. No full
  suite; touched/composing files once, then fast guards.

## Measurements

Manual keyless observations on 2026-10-18; baseline source frozen at `84855401`.
Each first run uses a new process and an isolated copy of the existing public cache, not an
empty cache. Times below are seconds until the wrapper **and relevant background reads**
settled. Immediate warm calls often hit source TTLs; they are not scheduled refresh timings.
Each network phase has one observation, not a percentile or latency guarantee. All nine
current game slots and their accessible native/nested dashboards are accounted for.
These are the listed configurations, not every configured-user startup: the initial
BOARDROOM/Surf probes have no selected seat or hub seats, and FrenPet has no wallet, so own-pet
reads are omitted. Base's `remote_only=True` matches the production app factory exactly.

| Dashboard / body | First cycle (s) | Immediate warm (s) |
|---|---:|---:|
| IMD BOARDROOM | 19.34 | 19.78 |
| Surf / onchain feed | 36.37 | 1.73 |
| Launchpad | 36.22 | 1.48 |
| Pool4 protocol (`e`) | 4.98 | 0.51 |
| Pool4 market (`4`) | 3.96 | 0.51 |
| SWARM / built by swarm | 41.71 | 1.03 |
| AGENT, selected public seat | 20.83 | 0.76 |
| AGENT, no selected seat (control) | 1.46 | 0.54 |
| BOARD / fleet | 1.88 | 0.59 |
| WORK IN PROGRESS | 32.03 | 0.58 |
| ORACLES | 2.25 | 0.57 |
| SWARM TOKENS | 1.01 | 6.76 |
| Token detail | 1.95 | 0.21 |
| NFT Explorer | 26.56 | 0.01 |
| Curator, no wallet | 61.99 | 1.39 |
| Curator, public wallet retained in copied cache | >65.00 | not measured |
| FWA | 9.18 | 0.004 |
| Base Terminal | 0.30 | 0.73 |
| FrenPet, no wallet | 0.66 | 1.04 |
| CatTown | 12.47 | 10.23 |
| Ten Thousand Tokens | 1.38 | 1.03 |
| Talismans | 2.72 | 2.55 |

Curator's wallet run still had cross-check work pending at its 65-second cap; it did not
complete in 65 seconds. Curator list/history/analysis share a collector. FWA, TTT and Talismans
display toggles share fetched data. Cached record/pop-up views have no independent read cycle.
Hidden legacy games and the currently unrouted Portfolio demo are excluded. Optional local
Curator export/ENS hydration and filter-specific interactive lookups were not exercised.
The BOARD measurement excludes its separate one-second launch-contribution eligibility offers.

Source errors matter: first+warm probes included HTTP 429s (BOARDROOM 4, Launchpad 1, protocol
3, market 3, Curator 2, CatTown 12); onchain feed/Launchpad each had two read timeouts; CatTown
also had four HTTP 525s, FWA two 404s. The capped Curator wallet probe had three 429s and three
400s. Settling therefore does not imply all fields were fetched successfully. Full request,
wrapper-return and passive-projection timings are retained in the audit artifacts below.

Separate baseline probes exercised the next eligible 30-second grid slot while retaining
the same manager. They skip occupied slots in the measurement harness; actual runtime
admission is covered by the regressions and the production NFT UI probe below.

| Dashboard | Initial cycle (s) | Next start offset (s) | Next cycle (s) | Next-cycle requests |
|---|---:|---:|---:|---:|
| IMD BOARDROOM | 20.17 | 30.002 | 19.76 | 14 (11 HTTP 200, 3 HTTP 429) |
| SWARM | 43.95 | 60.002 | 2.11 | 6 (all HTTP 200) |
| NFT Explorer, before fix | 27.22 | 30.001 | 26.70 | 16 (all HTTP 200) |

The selected AGENT run used the public seat from the user's screenshot and made 85 successful
requests initially, zero on the immediate warm call. Its passive cached projection averaged
0.784 seconds initially and 0.754 seconds after loading (three samples each). This explains
why the no-seat control alone would understate agent loading cost.

### NFT before/after

The old NFT reader returned cached data in 0.009 seconds while remaining busy for 26.56
seconds. A separate baseline scheduled run took 27.22 seconds initially and 26.70 seconds on
the next 30-second slot. Returning from `fetch_and_compute()` was not completion.

Controlled CPU comparison: five paired publications over the same 981 candidates and 19
records took **5.885 seconds before, 0.802 seconds after** (86.4% reduction). Mean 95% Student-t
intervals were [5.443, 6.328] and [0.654, 0.949] seconds. All candidate/catalogue values,
normalized state and serialized JSON order were identical in all five pairs. These intervals
describe this local CPU sample, not internet latency.

Actual production NFT screen plus `ReaderRuntime`, 149×45 Matrix, copied baseline caches:

| Accepted cycle | Start after process entry (s) | Cycle duration (s) |
|---|---:|---:|
| Initial | 0.924 | 6.150 |
| Next scheduled | 31.175 | 6.513 |
| Next scheduled | 61.274 | 5.884 |

Cached rows were visible after 0.970 seconds; the first loading state cleared at 7.114 seconds.
The 72-second run made 73 HTTP requests, all returning 200; maximum concurrent NFT cycles was
**one**. UI selection caused one additional bootstrap wrapper during the initial cycle, but
did not start another acquisition cycle. All later wrappers entered with the manager idle.
The live screen was captured after the third cycle settled. The beginning overlapped a
subsequently interrupted BOARDROOM benchmark and a separate Curator wallet probe; this is a
live observation, not a controlled network A/B or a guarantee of six-second refreshes.

### Polling verification

Before the fix, twenty UI refresh requests submitted during blocked reader CPU work caused
two fetches. After the fix they cause one; a newly submitted request after completion still
works. Deterministic-clock regressions also hold synchronous/detached work over multiple
deadlines and prove the next future slot can run without catch-up. Cached reopening, selected
README bootstrap, cancellation barriers, publication and UI responsiveness remain covered.

190 touched/composing tests passed (9.16 s); 126 fast guards passed (14.01 s). Eight targeted
mutations were killed: four concurrency/cadence/activation mutations and four NFT parsing/join
mutations, with byte-for-byte restoration. No full suite or network test was run.

Final independent review: **Approved, no findings**. The reviewer ran 14 named cases,
independently killed all eight mutations and restored every mutated file byte-for-byte.
UI timer ownership, README/bootstrap admission and generation/cancellation/drain barriers
were checked; no reviewer edits remain.

### Artifacts and reproduction

`/tmp/maxpane-poll-audit/` contains the frozen source, isolated public cache copies,
`measure_views.py`, `timing-matrix.json`, per-target results, test logs and mutation logs.
`nft/comparison.json` records the paired CPU comparison; `nft-runtime/results.json` and
`nft-runtime/nft.svg` record the real reader/UI probe. The user's caches were not modified.

From the repository (manual live probes, not pytest):

```sh
.venv/bin/python /tmp/maxpane-poll-audit/measure_views.py --run-label rerun
.venv/bin/python /tmp/maxpane-poll-audit/measure_views.py --source /Users/banse/codex/maxpane --run-label postfix --scheduled nft
env -u NO_COLOR .venv/bin/python /tmp/maxpane-poll-audit/reader_nft_live.py
```

### Residuals

- Curator's 62-second no-wallet and >65-second wallet reads, SWARM's 42-second read, and the
  32–36-second Surf/Launchpad/WORK reads deserve source-level profiling. The admission fix
  prevents queued polls; it does not shorten those sources' timeout/backfill work.
- NFT enrichment is still resumable across bounded cycles; unknown mint/IDMD semantics and
  partial discovery remain legitimate. This change does not infer unsupported values.
- BOARD's separate contribution offers are guarded by the manager and publish only their
  small result. They are outside the cadence measurement and were not redesigned here.
