# `sybilkit/tests/fixtures/`

Committed, read-only, keyless. **No test in this distribution opens a socket**;
every external payload is one of these files. Read them through
`tests/sybilkit_fixtures.py`, never by a hand-rolled path.

| file | what it is |
|---|---|
| `labeled_subset.json` | the benchmark subset: 160 sampled members of the 16 audited operators + 60 controls, each with its deposit rows, 1-based join index, transaction fingerprint and funder |
| `deposits.json.gz` | the full population — 22 319 `Deposited` rows |
| `first_deposits.json.gz` | the full population — 15 576 `FirstDeposit` rows |

All three come from the 2026-08-17 19:44:40 UTC sweep of a live Ethereum
mainnet contract (latest block 25 776 962). They are measured data, not
synthesised.

## Wheels do not ship this directory

`pyproject.toml`'s `[tool.hatch.build.targets.wheel] packages = ["src/sybilkit"]`
and the sdist's `include = ["src/sybilkit/"]` both exclude `tests/`, so the ~3 MB
of population data stays out of what a user installs. It is here so the segment
statistics and the precision floor can be asserted against the **real
distribution** rather than against a sample of it — a benchmark gate measured on
a convenient subset is a gate that passes for the wrong reason.

Both archives stay **gzipped** and are decompressed in memory by
`sybilkit_fixtures.load()`. There is deliberately no uncompressed copy in the
tree: `deposits.json` unpacks to ~12 MB, and an untracked 12 MB file beside the
archive reads as a change nobody made on the next `git status`.

## `labeled_subset.json` — the shape

```
meta      { sweep_utc, latest_block, population_*, n_clusters/members/controls, labels }
clusters  [ { cluster, kind, amount_eth, wallets, eth_in, points, share_pct,
              points_if_one_wallet, sqrt_subsidy_x, sampled } × 16 ]
members   [ { address, cluster, is_member: true, first_index, first_deposit_block,
              first_deposit_ts, deposits[…], tx{…}|null, funding{…}|null } × 160 ]
controls  [ … × 60, with cluster: null and is_member: false ]
```

`funding.funder_in_cluster` is `true` when the funder is a member of that
address's **own** cluster (checked against the full membership, not just the
sampled ten); for a control it is `true` when the funder belongs to **any**
audited cluster; and it is **`null`** when the funder could not be resolved.
`null` is not `false` — the whole library runs on that distinction, and this is
the file where it starts.

The measured result the gate exists to keep: on every fully-resolved farm sample
the funder is a fellow cluster member **10 of 10** times; across the controls it
is **0 of 47**. That is the strongest single discriminator on this population,
and it is the reason tier C is worth a background Blockscout sweep at all.

## The mirror

`labeled_subset.json` is **byte-identical** to
`tests/fixtures/curator/sybil/labeled_subset.json` in the maxpane repo. PRD §8
requires both distributions to gate on the same evidence, and a test on the
maxpane side asserts the two copies agree — otherwise they drift into two
convenient subsets and neither gate means anything.
