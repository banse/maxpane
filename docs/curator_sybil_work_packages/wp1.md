# WP1 — `sybilkit` core: model, signals, cluster combiner, report, labels (pure)

**Goal:** The pure, stdlib-only heart of the library — every Tier-A/B/C **signal** as a pure
`(Dataset, DetectConfig) -> list[Edge]`, the union-find **cluster** combiner with the ≥2-family
gate and multiplicative confidence, the **report** value objects, and the CEX/infra **labels** —
each written TDD-first against the committed labeled subset, each detector mutation-proven. No
I/O of any kind.

**Dependencies:** WP0 (the frozen public API in `sybilkit/src/sybilkit/{__init__,model,report,
cluster}.py` — signatures only). Runs in **wave 1** in parallel with WP5; shares no file with it.

**Owner note — this WP owns and fills/creates:**

- `sybilkit/src/sybilkit/model.py` (fills `Dataset.from_events`, WP0 froze the fields)
- `sybilkit/src/sybilkit/report.py` (fills `DetectResult`; WP0 froze the dataclasses)
- `sybilkit/src/sybilkit/cluster.py` (fills `detect` + the union-find + `Edge`)
- `sybilkit/src/sybilkit/signals/{amounts,sequence,cadence,split,gas,funding}.py` (creates)
- `sybilkit/src/sybilkit/labels.py` (creates)
- `sybilkit/tests/test_{model,cluster,report,labels}.py` and
  `sybilkit/tests/test_signals_{amounts,sequence,cadence,split,gas,funding}.py`
- its own fixtures under `sybilkit/tests/fixtures/` (uses WP0's `labeled_subset.json`)

It touches **nothing** under `sybilkit/sources/`, `curator.py`, `cli.py`, `bench.py` — those are
WP2's. If the frozen API in `__init__.py` is wrong, **report it**; do not edit WP2's or a
future file.

### Ground rules

- **stdlib only.** A test asserts every module under `sybilkit/src/sybilkit/` **except**
  `sources/` and `cli.py` contains no `import httpx`/`asyncio`/`requests`/`maxpane`/`textual`.
  The core must be importable with zero third-party deps (PRD §3.5).
- **The word "sybil" is allowed here** — this is the artifact named "sybil", it lives outside
  every maxpane scanned surface (PRD §2, §8). Use it freely in names, docstrings, reasons.
- **Score clusters, not wallets** (PRD §3.1): a wallet is flagged only via a cluster; there is
  no per-wallet threshold.
- **Compound conditions:** a cluster forms only with `≥ min_families` **distinct** edge-families
  and `≥ min_size` members. One family never convicts.
- **Reasons, never verdicts:** `confidence ∈ [0,1]`, multiplicative, graduated. Freshness
  discounts, never convicts.
- **`None` is a failed read; the three legitimate zeros are answers** (mirrors curator).
- **Wei-exact, integer throughout.** The curve floors `isqrt(w) * ppe // 10**9`. `pytest.approx`
  on a wei value is a review failure.
- Commit after each task.

---

### Task WP1.1: `Dataset.from_events` — pure coercion

**Interfaces:** fills WP0's `Dataset.from_events(deposits, first_deposits, *, txs=None,
funding=None) -> Dataset`.

**Steps:**

- [ ] Failing tests (`test_model.py`): builds a `Dataset` from raw dicts and from `Deposit`
      objects; lowercases every address; coerces hex/decimal wei to `int`; de-dupes deposits on
      `(tx_hash, log_index)`; `first_index` is 1-based and keyed by lowercase address; `txs` and
      `funding` default to empty dicts (tier A only); a malformed deposit is **dropped, not
      zeroed** (the `_usable_deposits` discipline from `curator_signals`).
- [ ] Implement, pure. No sort dependence on input order (chain order is
      `(block_number, log_index)`).
- [ ] **Bite:** stop lowercasing an address → the case-insensitive membership test in WP1.5
      would later break; add a `test_addresses_are_normalised_lowercase` here that reddens.
- [ ] Commit: `feat(sybilkit): pure Dataset.from_events`

---

### Task WP1.2: Tier-A amount signals (`signals/amounts.py`, `signals/split.py`)

**Interfaces:** `amount_edges(ds, cfg) -> list[Edge]` (identical + near-identical `±tol`
amount groups among single-deposit wallets); `split_edges(ds, cfg) -> list[Edge]` (the
optimal-split `≈ W/k` weight signature). `Edge` is `(a: str, b: str, family: str,
strength: float, reason: Reason)` or a hyper-edge over a member set — decide in WP1.5's combiner
and keep the signal output a list of pairwise or grouped edges consistently.

**Steps:**

- [ ] Failing tests against `labeled_subset.json`: the 0.45 ETH operator's members are joined by
      an `amount` family edge (byte-identical); the **randomized 0.0989–0.0995** batch (which a
      byte-identical rule misses — research §3) is joined at `near_amount_tol=0.10`; the 0.05 ETH
      **minimum** crowd is NOT one giant amount cluster on its own (amount alone is `NOISY` for a
      round/minimum value — research §5).
- [ ] Amounts group on the **integer wei**, never an ETH float (the `curator_signals`
      discipline). Near-identical uses an integer tolerance derived from `tol` (e.g.
      `abs(a-b) * 1_000 <= tol_bps * max(a,b)`), computed in integers.
- [ ] Commit: `feat(sybilkit): amount and optimal-split edge signals`

---

### Task WP1.3: Tier-A sequence + cadence signals (`signals/sequence.py`, `signals/cadence.py`)

**Interfaces:** `sequence_edges(ds, cfg)` — consecutive `FirstDeposit`-index runs with
near-identical amounts, ≤2-block spacing (research §5.3, the "180 consecutive indices in 7
blocks" pattern); `cadence_edges(ds, cfg)` — per-block burst quantization (exactly 20/30
tx/block) and the metronomic 1-per-N-block drip (research §4/§5.4).

**Steps:**

- [ ] Failing tests: the consecutive-index run over the 0.45 farm is found; the 2.067-ETH
      operator's **two window-separated waves** are linked by the identical odd amount (research
      §3) — this is a `sequence`/`amount` corroboration, so assert the combiner unites them in
      WP1.5, and here assert each signal fires on its own slice; a random scatter of organic
      deposits produces no cadence edge.
- [ ] Commit: `feat(sybilkit): consecutive-index and cadence-quantization signals`

---

### Task WP1.4: Tier-B gas + Tier-C funding signals (`signals/gas.py`, `signals/funding.py`)

**Interfaces:** `gas_edges(ds, cfg)` — priority-fee / max-fee / gas-limit / type **uniformity**
classes over `ds.txs` (the uniformity is the signal, not the value — research §5.2);
`funding_edges(ds, cfg)` — the first-funder graph over `ds.funding`: **funder ∈ same cluster**
(peel chains), the single strongest discriminator (10/10 vs 0/47 — research §5.1).

**Steps:**

- [ ] Failing tests against `tx_fingerprints.json` + `funding.json` slices: the 0.45 and 10.0
      farms collapse to **one** priority fee + **one** gas limit while the 60 controls show 27
      priority fees / 15 gas limits (research §4/§5.2); the funding fold flags the 10/10
      serial-chain members and **not** the 35/47 controls who fund from their own main wallet
      (funder-is-any-contributor is NOISY — research §5.1); a `Funding.funder is None` (Tier-C
      not run) produces **no** funding edge, never a false one.
- [ ] `gas.py`/`funding.py` are still pure — they read `ds.txs`/`ds.funding`, which the adapter
      populates. Empty `ds.txs`/`ds.funding` → no edges (tier A only), which is the normal
      first-cycle state.
- [ ] **Bite (mandated, the funding fold):** make `funding_edges` fire on *any* contributor
      funder rather than funder-∈-cluster → the 35/47-control false-positive test reddens.
      Restore. Record for WP6's audit.
- [ ] Commit: `feat(sybilkit): gas-uniformity and funder-in-cluster signals`

---

### Task WP1.5: The cluster combiner (`cluster.py::detect` + union-find)

**Interfaces:** fills `detect(ds, cfg) -> DetectResult`. Union edges (union-find over the
member set); keep components with `≥ cfg.min_families` **distinct** edge-families and
`≥ cfg.min_size` members; compute per-cluster multiplicative `confidence`, `points`
(via `curve_points`, using `points_per_eth` carried on the `Dataset` or defaulted), and
`points_share`.

**Steps:**

- [ ] Failing tests:

```python
def test_one_family_never_convicts():
    """PRD §3.1.  A component joined only by identical amounts -- with no
    sequence, cadence, gas or funding corroboration -- is below min_families and
    is not a cluster."""
    ds = _amount_only_fixture()   # the 0.05 minimum crowd
    assert detect(ds, DetectConfig(min_families=2)).clusters == []

def test_min_size_keeps_one_human_few_wallets_out():
    assert all(c.size >= 5 for c in detect(_labeled(), DetectConfig()).clusters)

def test_the_16_audited_operators_are_each_found():
    res = detect(_labeled(), DetectConfig())
    found = {_shape(c) for c in res.clusters}
    for shape in ("0.45", "14.0", "10.0", "1.2", "2.067"):
        assert shape in found

def test_no_control_is_flagged():
    res = detect(_labeled(), DetectConfig())
    assert res.flagged.isdisjoint(_control_addresses())

def test_confidence_is_graduated_not_binary():
    res = detect(_labeled(), DetectConfig())
    confs = sorted({round(c.confidence, 2) for c in res.clusters})
    assert len(confs) >= 2 and all(0.0 <= c <= 1.0 for c in confs)

def test_freshness_discounts_never_convicts():
    """A fresh-nonce-only signal cannot lift a one-family component to a
    cluster (research §5: 55% of controls are nonce-0)."""
    ...
```

- [ ] Implement union-find; a component's `reasons` are the distinct-family reasons that built
      it; `confidence` is a multiplicative product of family strengths, clamped to [0,1].
- [ ] **Bite (mandated, the cluster combiner):** drop the distinct-family count gate (accept
      `≥1` family) → `test_one_family_never_convicts` and `test_no_control_is_flagged` redden.
      Restore. Record for WP6's audit.
- [ ] Commit: `feat(sybilkit): union-find cluster combiner with the two-family gate`

---

### Task WP1.6: `DetectResult` + `report.py` (points, shares, wallet lookup)

**Steps:**

- [ ] Failing tests: `res.wallet(addr)` returns a `WalletVerdict` for a member and `None` for a
      stranger (never a zero-confidence verdict — a stranger is not a wallet scored clean);
      `res.flagged` is exactly the members with `confidence >= threshold`, lowercase;
      `total_points == flagged_points + clean_points`; `curve_points(1e18, 1000) == 1000`,
      `curve_points(1000e18, 1000) == 31_622`, `curve_points(0, 1000) == 0` — floored exactly
      like `analytics/curator_signals.points_for_weight`.
- [ ] **Bite (mandated, the curve floor):** change `//` to `round(... / ...)` in `curve_points`
      (note: `curve_points` lives in WP2's `curator.py` preset — so this specific bite belongs
      to WP2; here assert the report's `points` sums match member curve points and mutate the
      **summation** instead). Coordinate: the curve itself is WP2's; `report.py` consumes it.
- [ ] Commit: `feat(sybilkit): DetectResult with wallet verdicts and point shares`

---

### Task WP1.7: `labels.py` (CEX + infra exclusion)

**Interfaces:** `CEX_HOT_WALLETS: frozenset[str]` (the 12 from ChainCred, research §7),
`is_infra_funder(addr) -> bool`, and an exclusion hook the funding signal calls so a shared CEX
funder does not fabricate a cluster (the recurring false-positive class — research §7).

**Steps:**

- [ ] Failing tests: the 12 CEX addresses are lowercase and checksummed-decoded consistently;
      a cluster whose only funding link is a shared CEX hot wallet is **not** formed (the
      disperse.app / CEX false-positive class); the constant is a `frozenset`, not a list.
- [ ] Vendor the 12 addresses **with a comment citing `chaincred`
      `packages/common/src/constants/selectors.ts`** (re-vendored, not imported — the two
      repos are separate).
- [ ] Commit: `feat(sybilkit): CEX hot-wallet labels and infra-funder exclusion`

---

### Task WP1.8: Purity + no-I/O gate and sign-off

**Steps:**

- [ ] `test_the_core_imports_no_io`: AST-scan every `sybilkit/src/sybilkit/*.py` and
      `signals/*.py` (not `sources/`, not `cli.py`) for `httpx`/`asyncio`/`requests`/`maxpane`/
      `textual`. None present.
- [ ] `cd sybilkit && python -m pytest -q` green, and `python -c "import sybilkit; from
      sybilkit import detect, Dataset, DetectConfig"` runs with **zero** third-party packages
      installed (a genuine stdlib-only check).
- [ ] Write the WP2/WP3 hand-off note: the exact `Edge`/`FAMILIES` shapes, the `detect`
      contract, and which fixtures the benchmark gate should reuse.
- [ ] Commit: `test(sybilkit): core purity gate and WP1 sign-off`

**Done when:** every detector is tested against the labeled subset, the combiner's two-family
gate and the funding fold were each watched go red and restored, and the core imports zero
third-party packages.
