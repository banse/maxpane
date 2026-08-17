# WP2 — `sybilkit` I/O, CLI, curator preset, benchmark gate, packaging

**Goal:** Make the pure core usable end to end and shippable: keyless failover `sources/`,
the THE-LIST `curator` preset (the sqrt curve, segments, cleaned-list), the `analyze | segments
| export-clean-list` CLI, the labeled-benchmark regression gate, and the standalone
distribution's packaging (own `pyproject.toml`, `py.typed`, README).

**Dependencies:** WP1 (the pure core: `detect`, `Dataset`, `report`, `signals`). Runs in
**wave 2** in parallel with WP4; shares no file with it.

**Owner note — this WP owns and creates:**

- `sybilkit/src/sybilkit/sources/{__init__,logs,txs,blockscout}.py`
- `sybilkit/src/sybilkit/curator.py` (the preset: `curve_points`, `segments`, `clean_list`,
  `CuratorPreset`)
- `sybilkit/src/sybilkit/bench.py`
- `sybilkit/src/sybilkit/cli.py`
- `sybilkit/pyproject.toml` (finalise: deps, extras, entry point, build targets)
- `sybilkit/tests/test_{sources,curator,cli,bench}.py`
- `sybilkit/README.md` (draft; WP6 finalises the maxpane-facing bits)

It **reads** WP1's core and **does not edit it** — a defect in the core is reported, not fixed.
It does **not** touch maxpane at all.

### Ground rules

- **Keyless, always.** No key, no secret, no header carrying one. A banned-host frozenset
  rejects the dead and the newly-keyed at construction (the `curator_client` precedent).
- **Endpoint failover on message text, not code** (research §6, CLAUDE.md): drpc's
  "Can't route your request" wears a code other providers spend on malformed input; a real
  malformed request short-circuits; a provider's *suggested* retry range is **never** adopted
  (one decrements one block per round trip and livelocks a verbatim follower) — halve the window.
- **A real `User-Agent` on every request** — publicnode 403s python-urllib's default.
- **No network in tests.** `httpx.MockTransport` doubles + a structural AST scan that the test
  files inject a transport that raises on real use (both distributions' rule).
- **`httpx` is optional.** The core imports with zero deps; `sources/` and the CLI import
  `httpx` lazily and the pyproject declares it under an extra so `pip install sybilkit` gives the
  pure core and `pip install "sybilkit[sources]"` adds the fetchers (PRD §3.5).
- **Wei-exact curve, floored like the contract.**
- Commit after each task.

---

### Task WP2.1: `curator.py` preset — the curve, floored exactly

**Interfaces:** `curve_points(weight_wei: int, points_per_eth: int) -> int` =
`isqrt(weight_wei) * points_per_eth // 10**9`; `CuratorPreset` holding THE LIST's constants
(from the contract, not hardcoded documentation — the preset takes them as inputs where the
adapter reads them live).

**Steps:**

- [ ] Failing tests (mirror `analytics/test_curator_signals.py`'s curve tests): the documented
      points (`1e18→1000`, `4e18→2000`, `100e18→10000`, `1000e18→31622`, `2000e18→44721`,
      `0→0`); **multiplication before division** (a weight just under 1e9 floors to a real
      value, not 0); `points_per_eth` is a parameter, not a literal (source scan for `1000`).
- [ ] Implement with `math.isqrt`.
- [ ] **Bite (mandated, the curve floor — three variants, mirroring the base build's WP3.3):**
      `//`→`round`; `math.isqrt`→`int(math.sqrt(...))`; operand order swapped. Each reddens a
      different named test. Restore each. Record for WP6's audit.
- [ ] Commit: `feat(sybilkit): the curator sqrt curve, floored exactly like the contract`

---

### Task WP2.2: `curator.py` preset — segments and clean_list

**Interfaces:** `segments(ds, res) -> Segments`, `clean_list(ds, res) -> CleanList`.

- `Segments`: whale **operators** (combined credit, since a single 800 ETH send is only 2
  wallets / 0.25% of points — research §5, Adam's ask), per-hour join/points bands, per-multiplier
  bands, the index-1000 "early" cohort (7.6% of points — research §5). Pattern-language labels
  ("largest operators", "early cohort"), never "whale sybil".
- `CleanList`: ranked survivors (farm-flagged members removed) + `clean_rank(addr)` — the
  reader's rank in the de-sybilled list.

**Steps:**

- [ ] Failing tests against the labeled subset + `whales_segments.json`: the whale segment is
      defined on the **operator**, not the single send (research §5 — only 2 wallets qualify at
      800 ETH+); the index-1000 cohort is 7.61% of points; `clean_points == total - flagged`;
      `clean_rank` of a flagged member is `None` (removed) and of a survivor is dense; the
      segment labels carry **no** accusatory word (the library may use "sybil" internally, but
      the segment `label` strings are what a preset consumer might render, so keep them
      pattern-language to make the adapter's job trivial).
- [ ] Implement, pure.
- [ ] Commit: `feat(sybilkit): whale-operator/segment bands and the cleaned list`

---

### Task WP2.3: `sources/` — keyless failover fetchers

**Interfaces:** `sources/logs.py` (`fetch_deposits(contract, from_block, *, transport=None)` —
`eth_getLogs`, 800-block chunks, tenderly primary / drpc fallback); `sources/txs.py`
(`fetch_tx_fingerprints(tx_hashes, *, transport=None)` — batched `getTransactionByHash` on
publicnode, `User-Agent` set); `sources/blockscout.py` (`fetch_funding(addresses, *,
transport=None)` — Blockscout REST, keyset pagination, ~3 req/s, resumable). Each returns the
WP0 model objects or `None` on failure.

**Steps:**

- [ ] Failing tests with `httpx.MockTransport`:
  - a first sweep pulls the whole history in chunks; a chunk failure fails over to drpc on
    **message text**;
  - `fetch_tx_fingerprints` batches and sets a real `User-Agent`; a 403 without it is asserted
    against a transport that returns 403 for the default UA;
  - `fetch_funding` paginates by keyset, throttles, and is resumable (a second call continues
    from a cursor);
  - a provider's suggested retry range is **not** adopted — the window halves;
  - **structural:** every test injects a transport; a real socket is never opened (AST scan for
    a bare `httpx.AsyncClient()` in the tests, mirroring `test_curator_client.py`).
- [ ] Implement lazily-imported `httpx`; the banned-host frozenset; message-text classification.
- [ ] **Bite (mandated, the livelock):** make `fetch_deposits` follow a provider's suggested
      range verbatim → the livelock test reddens (the window never shrinks). Restore.
- [ ] Commit: `feat(sybilkit): keyless failover sources for logs, txs and funding`

---

### Task WP2.4: `bench.py` — the labeled-benchmark regression gate

**Interfaces:** `run_benchmark(labeled_subset) -> BenchResult` with `precision`, `median_gap`,
and a `passes(floor, ceiling)`.

**Steps:**

- [ ] Failing tests (the ChainCred pattern — research §7): the gate computes precision over the
      16 audited operators + controls; a **precision floor** and a **median-gap ceiling** are
      asserted so a heuristic tuned to zero recall fails; a `todo`-marked assertion pins the
      **cluster-level** target the wallet-level baseline can't meet, flipped to a real assertion
      when detection reaches it (PRD §3.5).
- [ ] The gate reads `labeled_subset.json` (WP0's fixture), never the network.
- [ ] Commit: `feat(sybilkit): labeled-benchmark regression gate with a precision floor`

---

### Task WP2.5: `cli.py` — `analyze | segments | export-clean-list`

**Interfaces:** `main(argv=None) -> int`; subcommands per PRD §3.4:

```
sybilkit analyze --contract 0x… --from-block N --preset curator --out clusters.json
sybilkit segments --contract 0x… --preset curator
sybilkit export-clean-list --contract 0x… --preset curator --out clean_list.json
```

**Steps:**

- [ ] Failing tests: `analyze` on a **fixture-backed** dataset (no network — inject a transport
      or a pre-built `Dataset`) prints/writes `reasons`-shaped JSON; `--out` writes the file and
      names the path; a missing `--contract` exits non-zero with a message; `export-clean-list`
      writes the survivors + each reader's clean rank. JSON is `reasons`-shaped
      (`{clusters:[{members,reasons,confidence,points_share}], flagged, ...}`).
- [ ] The CLI imports `httpx` lazily (via `sources/`), so `sybilkit --help` works on the pure
      install; a live fetch prints a clear "install sybilkit[sources]" message if httpx is
      absent.
- [ ] Commit: `feat(sybilkit): analyze/segments/export-clean-list CLI with JSON output`

---

### Task WP2.6: Packaging — `pyproject.toml`, `py.typed`, build

**Steps:**

- [ ] Finalise `sybilkit/pyproject.toml`: `name = "sybilkit"` (or the locked name),
      `dependencies = []`, `[project.optional-dependencies] sources = ["httpx>=0.27"]`,
      `[project.scripts] sybilkit = "sybilkit.cli:main"`, hatchling backend,
      `packages = ["src/sybilkit"]`, `py.typed` shipped. Python 3.11.
- [ ] `python -m build sybilkit/` produces an sdist and a wheel; `pip install
      dist/sybilkit-*.whl` in a scratch venv imports the core with **no** httpx, and
      `pip install "dist/sybilkit-*.whl[sources]"` adds the fetchers. Record both in the commit
      body.
- [ ] Draft `sybilkit/README.md`: install (`pip install sybilkit` / `[sources]`), a
      three-line usage example (`Dataset.from_events` → `detect` → `res.flagged`), the CLI
      commands, and a "keyless, read-only analysis; not affiliated with any allowlist" note.
      Mark the maxpane-facing "THE LIST preset" section `# TODO(WP6)`.
- [ ] Add the **packaging note for WP6** in the commit body: the root
      `.github/workflows/publish.yml` runs `python -m build` at the repo root and builds
      **only maxpane** (`pyproject.toml` packages `maxpane_dashboard`), so publishing
      `sybilkit` is a **separate** job/tag — not auto-wired. WP6 decides between a manual step
      and a distinct `publish-sybilkit.yml` gated on a `sybilkit-v*` tag (plan §6 risk 8).
- [ ] Commit: `build(sybilkit): finalise pyproject, py.typed and the standalone build`

---

### Task WP2.7: No-network gate and sign-off

**Steps:**

- [ ] `cd sybilkit && python -m pytest -q` green.
- [ ] The structural no-network assertion covers `sources/` and `cli.py`: no test opens a real
      socket; every fetch test injects a transport that raises on a live request.
- [ ] Write the WP3 hand-off note: the `sources/` signatures (contract, from_block, transport),
      the `curator` preset's `segments`/`clean_list`/`curve_points` shapes, and the exact JSON
      the CLI writes — so the adapter (WP3) drives the same functions and matches the same
      output.
- [ ] Commit: `test(sybilkit): no-network gate and WP2 sign-off`

**Done when:** the library is installable and usable **without maxpane**, the CLI runs against a
fixture, the benchmark gate has a precision floor + median-gap ceiling + a cluster-level `todo`,
the three curve mutations were each watched go red, and `python -m build sybilkit/` builds a
wheel whose core imports with zero third-party packages.
