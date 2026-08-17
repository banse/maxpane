# WP0 — Interface freeze: the `sybilkit` public API and the new curator keys

**Goal:** Lock the standalone distribution's **name**; freeze the `sybilkit` public API
(PRD §3.3) and the new `CURATOR_KEYS` / `CURATOR_ROW_KEYS` (PRD §7) that the whole build codes
against; commit the **worst-case** analysis fixtures so the width sweep and the adapter both
measure the state the data is normally in. After WP0.7 is green, WP1–WP5 can be written
**simultaneously** against one interface, no talking, no invented values.

**Dependencies:** none. **Strictly sequential and first**, exactly like the base-curator WP0.

**Owner note — this WP owns and creates:**

- `sybilkit/src/sybilkit/__init__.py` (API stubs; every public symbol importable, every method
  `raise NotImplementedError` until WP1/WP2)
- `sybilkit/src/sybilkit/model.py`, `.../report.py`, `.../cluster.py` **as stub signatures only**
  (dataclass fields + function signatures; WP1 fills the bodies)
- `sybilkit/tests/sybilkit_fixtures.py` (the shared fixture reader for both distributions)
- `sybilkit/tests/test_public_api.py`
- `sybilkit/README.md` (a stub; WP6 finalises)
- `tests/fixtures/curator/sybil/` (the worst-case slices + a manifest README)
- `tests/curator_sybil_fixtures.py` (the maxpane-side reader for the same slices)
- `tests/data/test_curator_sybil_data.py` (the fact pins over `docs/curator_sybil_data/`)

It **modifies exactly one existing file:** `maxpane_dashboard/data/curator_models.py` (adds the
new keys/rows) and its test `tests/data/test_curator_models.py`. It touches **no** `app.py`,
`__main__.py`, `game_select.py`, `minimal.tcss`, `curator_signals.py`, `curator_manager.py`,
`curator_cache.py`, or any widget/screen. Those belong to later WPs.

### Ground rules

- Run maxpane tests as `.venv/bin/python -m pytest`; the system `python3` lacks the deps.
- Run sybilkit tests from the crate: `cd sybilkit && python -m pytest` (stdlib-only, so the
  system interpreter works, but pin the interpreter in the brief).
- **No I/O in anything WP0 ships.** `curator_models` imports only stdlib (a test already asserts
  it); the sybilkit stubs import only stdlib.
- **A failed read is `None`, never `0`.** Every new optional numeric is `X | None`.
- **The new keys go into `CURATOR_KEYS` ONLY — never into
  `analytics/curator_signals.SIGNAL_OUTPUT_KEYS`.** The manager fills them after `build_signals`
  (the ENS-merge precedent), so `curator_signals.py` stays exactly as shipped and its
  forbidden-word source scan and `flagged=True` tests stay green. WP0.6 pins this with a
  guardrail test.
- Commit after each task, `type(scope): subject`.

---

### Task WP0.1: Lock the name and scaffold the distribution

**Files:** create `sybilkit/pyproject.toml` (skeleton, WP2 finalises deps),
`sybilkit/src/sybilkit/__init__.py`, `sybilkit/src/sybilkit/py.typed`, `sybilkit/README.md`
(stub), `sybilkit/tests/__init__.py`.

**Steps:**

- [ ] **Confirm the name with the user or lock `sybilkit`** (PRD §10). Every path below and
      every import in WP1/WP2/WP3 uses it; a later rename is a sed across two distributions.
      Record the decision in the commit body.
- [ ] Scaffold `sybilkit/` as a sibling of `maxpane/` (the Rust crate) and `maxpane_dashboard/`.
      `pyproject.toml`: `name = "sybilkit"`, `requires-python = ">=3.11"`, `dependencies = []`
      for the core (httpx added in WP2 as an **optional** extra), `[project.scripts] sybilkit =
      "sybilkit.cli:main"` (the entry point WP2 implements), hatchling build backend mirroring
      the root `pyproject.toml`'s shape, `packages = ["src/sybilkit"]`. Ship `py.typed`.
- [ ] Write `sybilkit/src/sybilkit/__init__.py` re-exporting the public names (WP0.4/WP0.5
      define them): `Dataset`, `detect`, `DetectConfig`, `DetectResult`, and from submodules
      `Deposit`, `Tx`, `Funding`, `Cluster`, `Reason`, `WalletVerdict`.
- [ ] `sybilkit/README.md` stub: one paragraph naming the library, "keyless, maxpane-independent,
      stdlib core", and a `# TODO(WP6)` marker.
- [ ] `python -m build sybilkit/` is **not** required here (no deps resolved yet) — but
      `cd sybilkit && python -c "import sybilkit"` must succeed.
- [ ] Commit: `feat(sybilkit): scaffold the standalone distribution and lock the name`

**Done when:** `import sybilkit` works, the package is a sibling distribution, and the name is
recorded.

---

### Task WP0.2: `sybilkit` model stubs (`model.py`)

**Files:** `sybilkit/src/sybilkit/model.py`, `sybilkit/tests/test_public_api.py` (create).

**Interfaces (wei-native dataclasses, no maxpane import ever):**

```python
@dataclass(frozen=True, slots=True)
class Deposit:
    contributor: str        # lowercase 0x address
    hour: int               # the indexed hour topic
    amount_wei: int
    credited_delta_wei: int
    weight_added_wei: int
    new_weight_wei: int
    tx_count: int
    block_number: int
    tx_hash: str
    log_index: int
    ts: float | None = None

@dataclass(frozen=True, slots=True)
class Tx:                    # tier B fingerprint
    tx_hash: str
    nonce: int | None
    max_priority_fee_wei: int | None
    max_fee_wei: int | None
    gas_limit: int | None
    tx_type: int | None

@dataclass(frozen=True, slots=True)
class Funding:              # tier C: first funder of an address
    address: str
    funder: str | None      # None means "we could not resolve a funder", not "no funder"
    hops: int | None

@dataclass(frozen=True, slots=True)
class Dataset:
    deposits: tuple[Deposit, ...]
    first_index: dict[str, int]      # 1-based FirstDeposit index by lowercase address
    txs: dict[str, Tx]               # by tx_hash; may be empty (tier A only)
    funding: dict[str, Funding]      # by lowercase address; may be empty (no tier C yet)

    @classmethod
    def from_events(cls, deposits, first_deposits, *, txs=None, funding=None) -> "Dataset":
        ...    # pure; coerces to wei ints; WP1 fills the body
```

**Steps:**

- [ ] Write `test_public_api.py`: every dataclass constructs from documented kwargs; every wei
      field is `int|None`; `Dataset.from_events` exists and is a classmethod; `model.py` imports
      nothing but the stdlib (source scan for `import httpx`, `maxpane`, `textual`).
- [ ] Write `model.py` with the dataclasses and a `from_events` that **raises
      `NotImplementedError("WP1")`** (this WP freezes the signature, WP1 fills it). The
      dataclass field tuples are the freeze; a `CONSTRUCTOR_KWARGS`-style pin belongs in the
      test so a rename fails.
- [ ] Commit: `feat(sybilkit): freeze the wei-native model dataclasses`

**Done when:** the model vocabulary is frozen and pinned; WP1 has one interface to fill.

---

### Task WP0.3: `sybilkit` report + config + detect stubs (`report.py`, `cluster.py`)

**Files:** `sybilkit/src/sybilkit/report.py`, `sybilkit/src/sybilkit/cluster.py`,
`sybilkit/tests/test_public_api.py` (extend).

**Interfaces:**

```python
# report.py
@dataclass(frozen=True, slots=True)
class Reason:
    family: str              # one of {"amount","sequence","cadence","gas","funding"}
    human_string: str        # pattern-language, e.g. "identical 0.45 ETH send"
    strength: float          # [0,1]

@dataclass(frozen=True, slots=True)
class Cluster:
    cluster_id: int
    members: tuple[str, ...]     # lowercase
    reasons: tuple[Reason, ...]
    confidence: float            # [0,1], multiplicative, graduated
    points: int                  # summed curve points of members (wei-floored)
    points_share: float          # of total_points, [0,1]
    span_blocks: int | None
    size: int

@dataclass(frozen=True, slots=True)
class WalletVerdict:
    in_cluster: bool
    cluster_id: int | None
    reasons: tuple[Reason, ...]
    confidence: float

class DetectResult:              # a small value object, not a dataclass (has methods)
    clusters: list[Cluster]      # sorted by points_share desc
    total_points: int
    flagged_points: int
    clean_points: int
    def wallet(self, addr: str) -> WalletVerdict | None: ...
    @property
    def flagged(self) -> set[str]: ...   # confidence >= threshold, lowercase

# cluster.py
@dataclass(frozen=True, slots=True)
class DetectConfig:
    min_size: int = 5
    min_families: int = 2
    near_amount_tol: float = 0.10
    confidence_threshold: float = 0.5

def detect(ds: Dataset, config: DetectConfig = DetectConfig()) -> DetectResult:
    ...    # raises NotImplementedError("WP1")
```

**Steps:**

- [ ] Extend `test_public_api.py`: `DetectConfig` defaults are `min_size=5, min_families=2,
      near_amount_tol=0.10` (PRD §3.1/§3.3); `detect` returns a `DetectResult` (stub raises);
      `Cluster` sorts by `points_share`; `Reason.family` is constrained to the five families
      (a `FAMILIES` tuple lives in `cluster.py` and is the authority).
- [ ] Write the stubs. `detect` raises `NotImplementedError("WP1")`.
- [ ] **Bite:** change one `DetectConfig` default (min_size 5→3) → the defaults test fails.
      Restore.
- [ ] Commit: `feat(sybilkit): freeze the detect/report/config public surface`

**Done when:** the whole PRD §3.3 API imports and is signature-pinned; WP1 fills bodies.

---

### Task WP0.4: The maxpane new keys (`curator_models.py`)

**Files:** modify `maxpane_dashboard/data/curator_models.py`; extend
`tests/data/test_curator_models.py`.

**Interfaces — add to `CURATOR_KEYS` (append; the manager builds all of them):**

```
# analysis view (MODE_ANALYSIS)
operator_rows           # list[dict] — CURATOR_ROW_KEYS["operator_rows"]
segment_rows            # list[dict] — CURATOR_ROW_KEYS["segment_rows"]
clean_list_rows         # list[dict] — CURATOR_ROW_KEYS["clean_list_rows"]
operators_count         # int | None — 0 = analyzed, none linked; None = could not analyze
clean_points            # int | None
clean_contributors      # int | None
analysis_as_of_hhmm     # str | None — the B+C sweep's own freshness marker (long TTL slot)
# per-wallet (y view)
you_linked_state        # str | None — "clean" | "linked" | None
you_linked_reasons      # list[str] — pattern-language phrases; [] = analyzed, not linked
you_linked_group_size   # int | None
you_clean_rank          # int | None
```

**`flagged_points_share_pct` already exists — reused** (see the plan §6 risk 2; the manager
override decision is WP3's, not WP0's). **`clean_list_export_path` is deliberately NOT added**
(plan §6 risk 1 — it is screen-owned).

Add to `CURATOR_ROW_KEYS`:

```python
"operator_rows":   ("size", "reasons", "points", "points_share_pct", "sqrt_subsidy_x", "conf"),
"segment_rows":    ("label", "contributors", "points_share_pct", "detail"),
"clean_list_rows": ("clean_rank", "address", "points", "credit_eth", "name"),
```

Add the **additive** sub-key to the existing `leaderboard_rows` tuple:

```python
"leaderboard_rows": (..., "flagged", "name", "link_conf"),   # link_conf: "high"|"low"|"clean"|None
```

**Steps:**

- [ ] Failing tests in `test_curator_models.py` (extend, do not rewrite — the file already pins
      the shipped keys; re-derive every count assertion rather than hand-bumping a literal):

```python
def test_curator_keys_gained_exactly_the_analysis_surface():
    """The new keys are present, and no shipped key was removed."""
    new = {
        "operator_rows", "segment_rows", "clean_list_rows", "operators_count",
        "clean_points", "clean_contributors", "analysis_as_of_hhmm",
        "you_linked_state", "you_linked_reasons", "you_linked_group_size",
        "you_clean_rank",
    }
    assert new <= set(CURATOR_KEYS)
    assert "clean_list_export_path" not in CURATOR_KEYS   # screen-owned (plan §6.1)
    assert len(CURATOR_KEYS) == len(set(CURATOR_KEYS))    # still no duplicate


def test_the_new_analysis_keys_are_not_in_the_signal_surface():
    """They are manager-adapter-produced (the ENS-merge precedent), NOT emitted
    by build_signals -- so analytics/curator_signals.py stays exactly as shipped
    and its forbidden-word source scan is never touched.  Guarded with
    importorskip so WP0 is green before the analytics module is read."""
    sig = pytest.importorskip("maxpane_dashboard.analytics.curator_signals")
    analysis = {
        "operator_rows", "segment_rows", "clean_list_rows", "operators_count",
        "clean_points", "clean_contributors", "analysis_as_of_hhmm",
        "you_linked_state", "you_linked_reasons", "you_linked_group_size",
        "you_clean_rank",
    }
    assert analysis.isdisjoint(set(sig.SIGNAL_OUTPUT_KEYS))


def test_the_new_row_shapes_are_frozen():
    assert CURATOR_ROW_KEYS["operator_rows"] == (
        "size", "reasons", "points", "points_share_pct", "sqrt_subsidy_x", "conf")
    assert CURATOR_ROW_KEYS["segment_rows"] == (
        "label", "contributors", "points_share_pct", "detail")
    assert CURATOR_ROW_KEYS["clean_list_rows"] == (
        "clean_rank", "address", "points", "credit_eth", "name")
    assert set(CURATOR_ROW_KEYS) <= set(CURATOR_KEYS)


def test_the_leaderboard_gained_a_confidence_grade_without_dropping_the_bool():
    """PRD §6: the flag upgrades to graded.  `flagged` (Tier-A bool) STAYS so
    curator_signals.py is untouched; `link_conf` is the additive graded grade."""
    lb = CURATOR_ROW_KEYS["leaderboard_rows"]
    assert "flagged" in lb and "link_conf" in lb
```

- [ ] Run: expect the four to fail (`link_conf`/new keys absent).
- [ ] Add the keys and row shapes to `curator_models.py`, each with a one-line comment naming
      its type and its unavailable rendering (the existing `CURATOR_KEYS` house style). Update
      the module's `CURATOR_ROW_KEYS` docstring paragraph. Extend the WP0-hand-off comment block
      at the top with a short "sybil expansion 2026-08-17" note.
- [ ] Run to green.
- [ ] **Bite:** rename `sqrt_subsidy_x` → `sqrt_x` in `CURATOR_ROW_KEYS` →
      `test_the_new_row_shapes_are_frozen` fails naming it. Restore.
- [ ] Commit: `feat(curator): add the sybil-analysis keys and row shapes to the frozen contract`

**Done when:** the new flat contract is importable, exact, disjoint from the signal surface, and
the leaderboard grade is additive.

---

### Task WP0.5: The routing table pin (screen dispatch contract)

**Files:** extend `tests/data/test_curator_models.py` (a documentation-shaped pin; the screen
itself is WP4's).

**Interfaces:** the routing table (plan §3.3) as data a later test can check. Because
`screens/curator.py` is WP4's file, WP0 cannot edit `WIDGET_SIGNATURES`. Instead WP0 pins the
**intended routing** as a module-level constant in the test so WP4 and WP5 wire against the same
map without talking.

**Steps:**

- [ ] Add a `ANALYSIS_KEY_ROUTING: dict[str, str]` **in the test file** (not production) mapping
      each new key to the widget class name that must render it (plan §3.3), and:

```python
def test_every_new_key_has_a_home_widget():
    """Totality: the screen's dispatch test will require CURATOR_KEYS - dispatched
    - META_KEYS == {}.  Each new top-level key must therefore reach a widget.
    analysis_as_of_hhmm reaches all three analysis panels."""
    homed = set(ANALYSIS_KEY_ROUTING)
    new = {k for k in CURATOR_KEYS if k in {
        "operator_rows","segment_rows","clean_list_rows","operators_count",
        "clean_points","clean_contributors","analysis_as_of_hhmm",
        "you_linked_state","you_linked_reasons","you_linked_group_size","you_clean_rank"}}
    assert new <= homed
```

- [ ] Commit: `test(curator): pin the analysis-key → widget routing for WP4/WP5`

**Done when:** WP4 and WP5 have one authoritative routing map to code against.

---

### Task WP0.6: Worst-case analysis fixtures + the data pins

**Files:** create `tests/fixtures/curator/sybil/` (slices), `tests/curator_sybil_fixtures.py`
(maxpane reader), `sybilkit/tests/sybilkit_fixtures.py` (sybilkit reader),
`tests/data/test_curator_sybil_data.py` (pins over `docs/curator_sybil_data/`).

**Why the worst-case matters.** WP4 pins its width against these rows before WP3 exists, so a
toy row would calibrate the layout to a state the data is never in (CLAUDE.md's IMD/FP-peg
lesson). Freeze the **widest real** operator row.

**Steps:**

- [ ] Pin the raw dataset facts (read from `docs/curator_sybil_data/`, never retyped):

```python
def test_the_operator_economics_are_the_research_numbers():
    econ = load("cluster_economics.json")   # docs/curator_sybil_data/
    # The 0.45 ETH operator: 1,995 wallets, 6.81% of points, 44.6x sqrt subsidy.
    top = _by_shape(econ, "0.45")
    assert top["wallets"] == 1995
    assert round(top["share_pct"], 2) == 6.81
    assert round(top["sqrt_subsidy_x"], 1) == 44.6

def test_the_conservative_floor_is_16_operators():
    econ = load("cluster_economics.json")
    assert _audited_count(econ) == 16          # 6,303 wallets, 43.3% of points

def test_the_funding_signal_is_10_of_10_on_farms_and_0_of_47_on_controls():
    f = load("funding.json")
    assert _farm_funder_in_cluster(f) == (10, 10)
    assert _control_funder_in_cluster(f) == (0, 47)
```

- [ ] Slice the **worst-case operator row** into `tests/fixtures/curator/sybil/operator_row_worst.json`
      (the 1,995-wallet 0.45 ETH operator: its full reasons list in pattern-language, its
      `points`, `points_share_pct = 6.81`, `sqrt_subsidy_x = 44.6`, `conf = "high"`) and a
      `segment_rows_worst.json` (the whale-operators + index-1000 early cohort + per-hour bands)
      and a `clean_list_rows_worst.json` (top survivors). Mark each
      `# SYNTHETIC — calibrated from docs/curator_sybil_data/, re-point at a live analysis bundle`.
      These are the payloads WP4/WP5 measure against.
- [ ] Slice a small **labeled subset** for the benchmark gate (the 16 audited operators'
      sampled members from `suspects.json` + the 60 controls) into
      `sybilkit/tests/fixtures/labeled_subset.json` **and** mirror it under
      `tests/fixtures/curator/sybil/` (PRD §8: both repos). Both readers open the same shape.
- [ ] Write both fixture readers (`load(name)`, `slices()`), modelled on
      `tests/curator_fixtures.py`. Neither opens a socket.
- [ ] Add the fixture-hygiene guards (mirroring `test_curator_captures.py`): no fixture carries
      an API key; the sybil fixtures live under one directory; the readers return sorted lists.
- [ ] **Bite:** change the expected `share_pct` to `6.90` → the economics pin fails. Restore.
- [ ] Commit: `test(curator): pin the sybil datasets and commit the worst-case analysis rows`

**Done when:** every number the later WPs quote is pinned against `docs/curator_sybil_data/`, and
WP4/WP5 have worst-case rows to size against.

---

### Task WP0.7: Freeze sign-off

**Steps:**

- [ ] Run the full new WP0 surface: the sybilkit stubs' tests + the extended
      `test_curator_models.py` + `test_curator_sybil_data.py`. Green, with the one guarded skip
      (`test_the_new_analysis_keys_are_not_in_the_signal_surface` while `curator_signals` is
      importable it should PASS, not skip — confirm).
- [ ] Run the whole maxpane suite (`~4300+` tests) to prove WP0 disturbed nothing: it adds keys
      to `CURATOR_KEYS`, so the manager's `test_it_returns_exactly_curator_keys_always` will go
      **red** (the manager does not yet emit the new keys) — that is the **one expected
      failure**, and it is exactly what tells WP3 what to build. Confirm no *other* test moved.
      If any widget/screen totality test also reddens, that is also expected (WP4/WP5 wire the
      keys); note which, so the parallel wave knows its starting red set.
- [ ] Write the **hand-off note** (commit body or a comment block in `curator_models.py`):
      1. the frozen sybilkit names and the locked distribution name;
      2. the new `CURATOR_KEYS`, the three new row shapes, the `link_conf` sub-key, the routing
         table, and the two deliberate omissions (`clean_list_export_path` screen-owned,
         new keys absent from `SIGNAL_OUTPUT_KEYS`);
      3. the worst-case fixture paths WP4/WP5 measure against;
      4. the expected red set the parallel wave inherits (the manager's totality test + any
         screen/widget totality test), so a wave-1 agent is not alarmed by it.
- [ ] Commit: `chore(sybil): WP0 interface freeze signed off`

**Done when:** both interfaces are importable and pinned, the only reds are the documented
manager/screen totality tests the later WPs close, and the hand-off exists. **Wave 1 may start.**
