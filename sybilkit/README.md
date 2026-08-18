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

A frozenset of dead and newly-keyed hosts is refused at `SourceConfig` construction.

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

segments(ds, res, preset)    # Segments: the largest operators, cohorts, multiplier bands
clean_list(ds, res, preset)  # CleanList: the ranking with flagged groups removed
```

`CuratorPreset`'s first two fields have **no defaults** on purpose — they are chain readings
(`POINTS_PER_ETH()`, `minDeposit()`), and 1000 / 0.05 ETH are measurements of one deployment, not
constants. Every remaining field (the gate knobs, the early-cohort size, the grace-hour count, the
"largest operator" line, the multiplier band edges) is an *analysis* choice, so each carries a
documented default and stays a field: a caller who measured something else is never arguing with a
literal.

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
