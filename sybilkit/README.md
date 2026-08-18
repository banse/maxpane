# sybilkit

**Keyless EVM sybil / fan-out cluster analysis.** A standalone Python distribution: a
pure-stdlib core you feed your own event data to, optional keyless fetchers, and a CLI. It is
**maxpane-independent** — nothing here imports the dashboard, and the dashboard reaches it
through exactly one adapter. It scores *clusters*, not wallets; it emits *reasons* with a
graduated confidence, never a verdict; and a failed read is `None`, never `0`. No API key of
any kind, ever.

Read-only analysis. Nothing here signs, sends, or constructs calldata for a state change.
Not affiliated with any allowlist, drop, or protocol.

## Install

```bash
pip install sybilkit              # the pure core — zero third-party packages
pip install "sybilkit[sources]"   # adds httpx and the keyless fetchers
```

The core imports with **no** dependencies installed. `sybilkit.sources` imports `httpx` lazily,
inside the call that needs it, so `import sybilkit.sources` and `sybilkit --help` work on the
pure install too — only a live fetch asks for the extra, and it names it.

Python 3.11+. `py.typed` is shipped.

## Use

```python
from sybilkit import Dataset, detect, DetectConfig

ds  = Dataset.from_events(deposits, first_deposits, txs=None, funding=None)
res = detect(ds, DetectConfig(points_per_eth=1000, protocol_min_amount_wei=50_000_000_000_000_000))

res.clusters        # list[Cluster], sorted by points_share desc
res.wallet(addr)    # WalletVerdict | None  — None means "not analyzed", not "clean"
res.flagged         # set[str], lowercase
```

Everything is **wei, and wei are `int`**. There is no `*_eth` field anywhere: a float cannot
hold 1 363 396 200 000 000 000 000 wei, and the points curve floors an integer square root, so
a float upstream moves the last digits of every score.

`points_per_eth` and `protocol_min_amount_wei` have no useful defaults and are not meant to be
remembered — read them off the chain. Without the protocol minimum, every wallet that paid the
protocol's floor is byte-identical to every other one, and identicalness at the minimum
identifies nobody.

### How a cluster forms

A wallet is never scored on its own. Signals emit `Edge`s in five independent **families** —
`amount`, `sequence`, `cadence`, `gas`, `funding` — the combiner unions them, and a component
survives only with **≥ 2 distinct families** and **≥ 5 members**. Confidence is noisy-OR over
the families' best strengths, discounted (never raised) by wallet freshness.

That compound condition is the design, not an optimisation: no per-wallet signal separated
farms from power users in any published study, and false positives are the failure mode rather
than a rounding error.

### What the dataset guarantees

`Dataset.from_events` is order-independent: a shuffled producer and an ordered one build the
same `Dataset`. Two rows sharing a `(tx_hash, log_index)` — a reorg replay, or two sweeps merged
across one — are settled by **content**, not by arrival: the higher `block_number` wins, and
every remaining field of the row breaks the remaining ties, `contributor` and `ts` included, so
no pair is ever decided by which one the producer handed over first. The same rule, character
for character, settles duplicates inside `sources/logs.py`, and a test compares the two sources.

A malformed field drops its row — except `ts`, which degrades to `None`, because `ts` feeds a
label and never a signal (cadence runs off `block_number`, and an hour band is the event's own
`hour` word), and an absent `ts` already degrades that way. A population of ISO-8601 timestamps
is therefore a readable dataset whose only casualty is the CLI's `generated_at` stamp, not an
empty one. A `NaN` or an infinity — what `float()` returns for the JSON literals of those names —
degrades the same way, and it degrades **in the coercer** rather than in the tie-break: an
unorderable `ts` that reached `_replay_rank` would hand a conflicting duplicate straight back to
arrival order, which is the one thing this section promises it never does.

## CLI

```bash
sybilkit analyze           --contract 0x… --from-block N --out clusters.json
sybilkit segments          --contract 0x… --preset curator
sybilkit export-clean-list --contract 0x… --preset curator --out clean_list.json
```

Sweeps `eth_getLogs` in 800-block chunks with endpoint failover, batches
`eth_getTransactionByHash`, and runs a bounded, throttled, resumable Blockscout funding pass —
all keyless. Every document carries a `schema_version`, a provenance header taken **from the
data** (never the wall clock, so re-exporting one archive is byte-identical), and every wei
value as a decimal string (a JSON number is a double to most consumers, and wei are not).

`--dataset FILE` runs the same analysis over a committed JSON bundle and sweeps nothing. Since
such a run cannot read the chain, it must be told what the chain says:
`--points-per-eth` and `--min-deposit-wei` are required there and have no defaults.

**Every refusal is a named message and a non-zero exit, never a traceback.** That covers the
arguments (`--max-txs 0` fetches nothing and says where it stopped, a negative
`--funding-budget` is rejected outright, `--from-block` past the head is an error rather than an
inverted `block_range`) and the chain readings a run cannot proceed on (a deployment answering
zero points per ETH is named, not divided by).

## Endpoints (all keyless, all verified)

| use | endpoint |
|---|---|
| logs | `gateway.tenderly.co/public/mainnet`, then `eth.drpc.org` |
| state / tx fingerprints | `ethereum-rpc.publicnode.com`, then the tenderly gateway |
| per-address history | `eth.blockscout.com/api/v2` |

Four things measured the hard way and encoded in `sources/`: publicnode **403s** a
library-default `User-Agent` and refuses archive `eth_getLogs`; Blockscout stalls
python-urllib while answering httpx and curl in under a second; drpc answers some log calls
with a routing-error **string** wearing a code other providers spend on malformed input, so
failover classifies on **message text, never the code**; and a provider's *suggested* retry
range is never adopted — one of them decrements a single block per round trip and livelocks a
verbatim follower, so the window halves instead.

Two more rules the same failover carries: a **200 whose body is not a JSON-RPC answer** — an
HTML error page, a bare array — is a failure that rotates to the next endpoint, never a read
that counts; and a **429 backs off before it rotates**, so a throttled pool is not walked at
full speed until it is exhausted.

A frozenset of dead and newly-keyed hosts is refused at `SourceConfig` construction.

### What a sweep returns, and what it means

Every fetcher answers `None` for **"nothing was read"** and a sweep object for "something was".
The distinction is load-bearing — the whole point of `None` is that a consumer can tell an outage
from a real emptiness — so each one states its own extent rather than implying it:

| fetcher | `None` means | a returned sweep means |
|---|---|---|
| `fetch_deposits` | the head could not be read, or not one chunk could | the chunks between `from_block` and **`to_block`** were read; `to_block` is the coverage *and* the resume cursor, so a run that lost its endpoint pool part-way returns the partial rather than discarding it |
| `fetch_tx_fingerprints` | zero batches were read | the fingerprints in `fingerprints` were read; every hash not in them is in `pending`, including everything after a malformed batch |
| `fetch_funding` | not one attempted address answered — and a deferral does not soften that, since a budgeted pass whose two requests both died is exactly as dead as an unbudgeted one | `funding` holds only walks that **finished**; `pending` holds the rest, with `pending_reasons` naming why, and `page_cursors` says where each bounded walk stopped |

A funding walk finishes only when it has read the address's incoming history to the end. Two
histories count: `/transactions?filter=to`, and — **only when that one found no incoming
transfer at all** — `/internal-transactions?filter=to`, because a wallet funded by a
`disperse`-style multisend receives its ETH as an internal transfer and appears nowhere on the
first endpoint. That is the exact pattern the `funding` family exists to catch, so it is not
optional; making it conditional keeps the cost off the common case. A direct internal transfer
is still `hops=1`.

`funder=None` on a row in `funding` is therefore a **measurement** — both histories were walked
and nobody funded this wallet. Anything we could not read (an unparseable page, a `from` that is
not an address, a page bound) leaves the address in `pending` instead, and never becomes a row.
A resolved row is the one thing a caller may cache forever; a hole must not be cacheable as one.

`fetch_funding(..., cursors=…)` takes back the `page_cursors` of a previous sweep, so an address
whose history is longer than `blockscout_max_pages` resumes mid-history next pass instead of
re-walking from page 1 forever. The mapping is tolerant on read — an absent or unreadable entry
simply starts at page 1 — so a consumer's payload written before cursors existed still works.

## The benchmark gate

`sybilkit.bench.run_benchmark(labeled_subset)` scores the detector against a labeled list and
returns a `BenchResult` with `precision`, `median_gap` and `passes(floor, ceiling)`. Two bars,
because either alone is gameable: a precision floor is met perfectly by a detector that
convicts nobody, and a gap ceiling by one that convicts everybody. It reads the fixture its
caller hands it and never the network.

## Tests

```bash
cd sybilkit && python -m pytest
```

No test opens a socket. Every external payload is a committed fixture; every fetch test injects
an `httpx.MockTransport`, and an AST scan enforces it.

## The THE LIST preset

`sybilkit.curator` is **one preset**, not the subject of the library. It holds the constants and
the cuts one particular allowlist game needs, and it is the worked example for writing another.

```python
from sybilkit import Dataset, detect, DetectConfig
from sybilkit.curator import CuratorPreset, clean_list, segments

preset = CuratorPreset(points_per_eth=..., min_deposit_wei=...)   # both read off the chain
res    = detect(ds, DetectConfig(points_per_eth=preset.points_per_eth,
                                 protocol_min_amount_wei=preset.min_deposit_wei))

segments(ds, res, preset)    # Segments: the linked groups, cohorts, multiplier bands
clean_list(ds, res, preset)  # CleanList: the ranking with flagged groups removed
```

`CuratorPreset`'s first two fields have **no defaults** on purpose — they are chain readings
(`POINTS_PER_ETH()`, `minDeposit()`), and 1000 / 0.05 ETH are measurements of one deployment, not
constants. Every remaining field (the gate knobs, the early-cohort size, the grace-hour count, the
"largest operator" line, the multiplier band edges) is an *analysis* choice, so each carries a
documented default and stays a field: a caller who measured something else is never arguing with a
literal.

`Segments.bands` keys on a closed vocabulary: **`linked_groups`** (every linked cluster,
aggregated), `early_cohort`, `late_cohort`, `hour_<h>`, `multiplier_<edge_bps>` and
`multiplier_unknown`. `linked_groups` is deliberately *not* the `largest_operator_credit_wei`
slice — that is `Segments.largest_operators`, a property, and it is never a band. The aggregate
carried the credit line's name while applying none of it; the fix was to correct the name,
because the number itself was right and it is the most useful one on the panel.

`clean_list` never speaks for a wallet nobody analyzed. Survivors come from `res.analyzed`
alone, so a result that analyzed nobody has no survivors and `CleanList.standing(addr)` answers
`"unknown"` — the three words `clean` / `removed` / `unknown` mean what they say on every
result, including a hand-built one.

`segments`, `clean_list` and the signal functions all take their shared folds by **keyword with
a default** (`weights=`, `credits=`, `firsts=`, `windows=`, `singles=`, `groups=`) so one caller
can walk a population once and hand the same answer to both. Every one of those parameters is additive: a
caller who does not care keeps the call it always had, and the cross-distribution imports
(`signals.first_rows`, `signals.tier_a_components`, `curator.segments`, `curator.clean_list`,
`CuratorPreset`, `sources.blockscout`, `sources.txs`) only ever grow.

### The adapter boundary

The MaxPane dashboard consumes this library through exactly one module,
`maxpane_dashboard/data/curator_clusters.py`, and that seam is deliberate in both directions:

- **Nothing here imports maxpane.** The dependency is one-way; this distribution is installable
  and usable on its own, and its test suite never imports the dashboard.
- **Nothing this library says reaches a screen unfiltered.** The adapter re-phrases every reason,
  label and detail — including strings read back out of a persisted cache file — into pattern
  language before rendering. This library is free to call a cluster what it is; a dashboard
  looking at real people's wallets is not.
- The adapter's import of this library is **guarded**, so the dashboard runs, and degrades to an
  explicit "analysis unavailable", when `sybilkit` is not installed.

## Releasing

**`sybilkit` is published by hand, and on purpose.** The repository's
`.github/workflows/publish.yml` fires on a `v*` tag and runs `python -m build` at the *repository
root*, which builds only `maxpane` (the root `pyproject.toml` packages `maxpane_dashboard`). It
never changes directory into `sybilkit/`, so **a maxpane release cannot ship this distribution** —
which is the safe default: an automatic build here would publish whatever version string happened
to be sitting in this `pyproject.toml` at the time of somebody else's release.

To cut a release, bump `version` in `sybilkit/pyproject.toml` and then, from the repository root:

```bash
python -m build sybilkit/          # -> sybilkit/dist/*.whl and *.tar.gz
twine upload sybilkit/dist/*
```

Check the wheel before uploading: its core must import with **zero** third-party packages
installed (`python -c "from sybilkit import detect"` in a venv with no `httpx`), and
`pip install "sybilkit[sources]"` must be the only thing that brings `httpx` in.
