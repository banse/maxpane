# sybilkit

**Keyless EVM sybil / fan-out cluster analysis.** A standalone Python distribution: a
pure-stdlib core you feed your own event data to, optional keyless fetchers, and a CLI. It is
**maxpane-independent** — nothing here imports the dashboard, and the dashboard reaches it
through exactly one adapter. It scores *clusters*, not wallets; it emits *reasons* with a
graduated confidence, never a verdict; and a failed read is `None`, never `0`. No API key of
any kind, ever.

```python
from sybilkit import Dataset, detect, DetectConfig

ds = Dataset.from_events(deposits, first_deposits, txs=None, funding=None)
res = detect(ds, DetectConfig(min_size=5, min_families=2, near_amount_tol=0.10))
res.clusters        # sorted by points_share desc
res.wallet(addr)    # WalletVerdict | None
res.flagged         # set[str], lowercase
```

Status: the public API is **frozen** (WP0); the bodies raise `NotImplementedError` until WP1
(core) and WP2 (sources, CLI, presets, packaging) land.

<!-- TODO(WP6): finalise this README — install, CLI usage, the benchmark gate, the
     keyless-endpoint list, and the separate publish job. -->
