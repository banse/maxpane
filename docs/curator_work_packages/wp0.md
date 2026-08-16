# WP0 — Interface freeze: addresses, topics, selectors, models, capture facts

**Goal:** Freeze the curator dashboard's constant surface (`data/curator_addresses.py`), its
vendored ABI (`abis/curator/whitelist_curator.json`), its model and flat-dict contract
(`data/curator_models.py`), and pin every fact the later work packages will hardcode to the
committed captures — so WP2, WP3 and WP4 can be written **simultaneously** against one
interface, with no network and no invented values.

**Dependencies:** none. **This WP is strictly sequential and first.** `data/curator_client.py`,
`analytics/curator_signals.py`, `widgets/curator/*`, `data/curator_cache.py` +
`data/curator_manager.py`, `screens/curator.py` and the registration package all import
`curator_addresses` / `curator_models`. Nothing else may start until WP0.8 is green.

**Owner note.** One agent. This WP owns and **creates**:

- `maxpane_dashboard/data/curator_addresses.py`
- `maxpane_dashboard/data/curator_models.py`
- `maxpane_dashboard/abis/curator/whitelist_curator.json`
- `scripts/vendor_curator_abi.py` (one-shot, imported by nothing)
- `tests/curator_fixtures.py`
- `tests/data/test_curator_addresses.py`
- `tests/data/test_curator_models.py`
- `tests/data/test_curator_captures.py`

It **modifies** exactly one existing file: `tests/fixtures/curator/captures/README.md`, and
only to add the "required set" manifest WP0.7 asserts against. It touches **no** `app.py`, no
`__main__.py`, no `game_select.py`, no `minimal.tcss` — those belong to WP7, late.

**WP0 writes no derived fixture files.** That is a decision, not an omission: the surf plan
proved that a WP0 slicing seventeen fixtures nobody downstream consumes is ~1,000 lines of
dead weight. Each consuming WP owns its own slice directory
(`tests/fixtures/curator/client/`, `.../signals/`, `.../screen/`); WP0 owns the captures, the
shared reader, and the **facts**.

| | Owner | Path |
|---|---|---|
| raw captures (the provenance for everything) | WP0 | `tests/fixtures/curator/captures/` (17 files) |
| live/timed captures | **WP1** | `tests/fixtures/curator/captures/live/` |
| the shared capture reader | WP0 | `tests/curator_fixtures.py` |
| the fact pins | WP0 | `tests/data/test_curator_captures.py` |
| client slices | WP2 | `tests/fixtures/curator/client/` |
| signals slices | WP3 | `tests/fixtures/curator/signals/` |
| anything a later WP needs | that WP | `tests/fixtures/curator/<its-own-dir>/` |

### Ground rules for every task below

- Run pytest as `.venv/bin/python -m pytest`. The system `python3` has no `httpx`/`textual`.
- **No test may touch the network.** WP0 ships no I/O code at all, so this is structural:
  `curator_addresses` and `curator_models` import nothing but the stdlib, and a test asserts it.
- **A failed read is `None`, never `0`.** Every optional numeric in `curator_models` is typed
  `X | None`. No model field defaults to `0`. Three legitimate zeros exist on this contract
  (`currentHourTotal` at a boundary, `ethNeededThisHour` in grace, `creditedDelta` above the
  cap) and each must stay distinguishable from a failed read.
- **WP0.5 is the model vocabulary, and it is the only one.** WP2's *Produces* tables and WP5's
  "exact shapes I read" table are restatements of `CONSTRUCTOR_KWARGS`, not independent
  drafts. Three vocabularies for one dataclass does not surface as a merge conflict: the
  producer raises `TypeError`, the consumer's `getattr(..., None)` returns `None` forever, and
  the dashboard renders a dark hero behind a green suite.
- **Recompute, never remember.** Every hash and selector in this WP is derived in-test from
  its Solidity preimage with `maxpane_dashboard/data/keccak.py::keccak256_hex`. Do not
  "correct" one from memory, and do not copy one out of the mechanics doc without recomputing
  it — the doc quotes them abbreviated (`0xb8385097…669cb3`).
- **`source.sol` is the only authority for a signature.** The mechanics doc and the PRD both
  paraphrase; the capture is verified source.
- Commit after each task, `type(scope): subject`.

---

### Task WP0.1: Vendor the ABI

**Files:**
- Create: `maxpane_dashboard/abis/curator/whitelist_curator.json`
- Create: `scripts/vendor_curator_abi.py`
- Test: `tests/data/test_curator_captures.py` (create; WP0.7 appends to it)

**Interfaces:**
- Produces: one ABI JSON array on disk, extracted **offline** from
  `tests/fixtures/curator/captures/contract.json`. Vendored, never fetched at runtime
  (`CLAUDE.md`: "vendored ABI JSON per protocol — never fetched at runtime").
- Consumes: nothing at runtime. `scripts/` is imported by nothing.

**Steps:**

- [ ] Confirm the two ABI captures agree before choosing one:
      `.venv/bin/python -c "import json;a=json.load(open('tests/fixtures/curator/captures/contract.json'));b=json.load(open('tests/fixtures/curator/captures/wc_abi.json'));print(type(a),type(b))"`
      Locate the ABI array inside each (Blockscout's smart-contracts response nests it under
      `abi`). If the two disagree, **stop and report** — two saves of one endpoint diverging
      means one is stale.
- [ ] Write `scripts/vendor_curator_abi.py`: reads the capture, writes the ABI array to
      `maxpane_dashboard/abis/curator/whitelist_curator.json` with `indent=2` and a trailing
      newline. No network, no arguments beyond optional paths. Follow `abis/fwa/`'s layout
      (a per-protocol subdirectory).
- [ ] Run it once. Confirm the output parses and holds every name `source.sol` declares:
      6 events (`Launched`, `Deposited`, `FirstDeposit`, `HourSaved`, `Settled`, `Rescued`),
      10 errors, and the public/external functions incl. `contributors`, `totalVolume`,
      `totalContributors`, `totalTxCount`, `POINTS_PER_ETH` and the eight immutables' getters.
- [ ] Add the first tests to `tests/data/test_curator_captures.py`:
      - `test_the_vendored_abi_matches_the_capture` — re-runs the extraction in memory and
        compares to the committed file, so a hand-edit fails.
      - `test_the_vendored_abi_declares_every_event_the_source_declares` — parses the event
        names out of `source.sol` with a regex and asserts set equality with the ABI's
        `type == "event"` entries. This is what catches an ABI truncated mid-save.
      - `test_nothing_under_maxpane_dashboard_imports_scripts` — a scan, mirroring the FWA
        guardrail.
- [ ] Run: `.venv/bin/python -m pytest tests/data/test_curator_captures.py -v`
- [ ] Commit:
      `git add maxpane_dashboard/abis/curator scripts/vendor_curator_abi.py tests/data/test_curator_captures.py && git commit -m "feat(curator): vendor the WhitelistCurator ABI from the verified-source capture"`

**Done when:** the ABI is on disk, reproducible from the capture, and proven complete against
`source.sol`.

---

### Task WP0.2: Address and deployment constants

**Files:**
- Create: `maxpane_dashboard/data/curator_addresses.py`
- Test: `tests/data/test_curator_addresses.py`

**Interfaces:**
- Produces: `CURATOR` (the contract), `DEPLOYER`, `ZERO_ADDRESS` — all `str`, EIP-55
  checksummed; `CREATION_TX: str`, `CREATION_BLOCK: int = 25769870`,
  `LAUNCH_TIME: int = 1786910327`, `LABELED_ADDRESSES: tuple[str, ...]`,
  `KNOWN_LABELS: dict[str, str]` (lowercase key → short label).
- Consumes: `maxpane_dashboard.data.keccak.keccak256` (test only, to recompute EIP-55).

**The re-vendoring rule.** `DEPLOYER` is byte-identical to `surf_addresses.DEV_WALLET`. It is
**re-vendored with a comment**, not imported: constants are never imported across dashboard
data layers (PRD §5). An import would make a surf edit a curator regression, and the surf
dashboard is explicitly out of scope for this build.

**Steps:**

- [ ] Write the failing test `tests/data/test_curator_addresses.py` with the surf pattern:
      a local `to_checksum()` built on this repo's keccak (never `hashlib.sha3_256`), a
      parametrised `test_every_address_is_checksummed`, and:

```python
def test_pinned_identities() -> None:
    """The two addresses a typo would silently redirect to someone else."""
    assert A.CURATOR == "0xcB0b0531e86A9aC36fa865ca8e3DbcCF047fDA91"
    assert A.DEPLOYER == "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"


def test_the_deployment_facts_come_from_the_creation_tx() -> None:
    """Not remembered — read out of the committed creation-tx capture."""
    tx = capture("creation_tx.json")
    assert A.CREATION_BLOCK == int(tx["block_number"])
    assert A.CREATION_TX.lower() == str(tx["hash"]).lower()
    # launchTime == the creation timestamp, and the contract's own getter
    # returned it in the batch round.
    assert A.LAUNCH_TIME == 1786910327


def test_the_deployer_is_re_vendored_not_imported() -> None:
    """Constants never cross dashboard data layers (PRD §5).

    The string is identical to surf's DEV_WALLET on purpose. Importing it would
    make an edit to the surf dashboard -- explicitly out of scope for this
    build -- a curator regression.
    """
    import inspect
    source = inspect.getsource(A)
    assert "surf_addresses" not in source
    assert "from maxpane_dashboard.data.surf" not in source


def test_module_imports_nothing_but_stdlib() -> None:
    import inspect
    source = inspect.getsource(A)
    for banned in ("import httpx", "import asyncio", "from textual", "import requests"):
        assert banned not in source
```

- [ ] Run and state the expected failure: `ModuleNotFoundError: No module named
      'maxpane_dashboard.data.curator_addresses'`.
- [ ] Write the module. Its docstring must carry the two hazards this file exists to contain:
      (a) the contract is **verified, non-upgradeable, unpaused, with no mutable parameter** —
      so unlike every other dashboard there is no "the owner changed it" failure mode, and the
      only privileged function is `rescue()`; (b) the balance of this address is **always
      forced ETH**, never deposits, because refunds happen in-transaction.
- [ ] Run to green.
- [ ] Commit:
      `git add maxpane_dashboard/data/curator_addresses.py tests/data/test_curator_addresses.py && git commit -m "feat(curator): vendor the curator address constants with checksum-recomputing tests"`

**Done when:** every constant is checksum-verified in-test and every deployment fact is read
out of `creation_tx.json` rather than typed.

---

### Task WP0.3: Event topics and their Solidity preimages

**Files:**
- Modify: `maxpane_dashboard/data/curator_addresses.py`
- Test: `tests/data/test_curator_addresses.py`

**Interfaces:**
- Produces: `TOPIC_LAUNCHED`, `TOPIC_DEPOSITED`, `TOPIC_FIRST_DEPOSIT`, `TOPIC_HOUR_SAVED`,
  `TOPIC_SETTLED`, `TOPIC_RESCUED` (`str`, `0x` + 64 lowercase hex) and
  `TOPIC_PREIMAGES: dict[str, str]`.

**The six preimages, taken from `source.sol` (indexed-ness does not enter topic0; the *types*
do):**

| constant | preimage |
|---|---|
| `TOPIC_LAUNCHED` | `Launched(uint256,uint256,uint256,uint256,uint256,uint256,uint256)` |
| `TOPIC_DEPOSITED` | `Deposited(address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)` |
| `TOPIC_FIRST_DEPOSIT` | `FirstDeposit(address,uint256,uint256)` |
| `TOPIC_HOUR_SAVED` | `HourSaved(address,uint256,uint256)` |
| `TOPIC_SETTLED` | `Settled(uint256,uint256,uint256,uint256)` |
| `TOPIC_RESCUED` | `Rescued(address,uint256)` |

**Steps:**

- [ ] Append the failing tests:

```python
@pytest.mark.parametrize("name,preimage", sorted(A.TOPIC_PREIMAGES.items()))
def test_topic_matches_its_preimage(name, preimage):
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))


def test_preimage_map_covers_exactly_the_topic_constants():
    """A vendored hash with no preimage is unverifiable; a preimage with no
    constant is dead weight. Both are failures."""
    names = {n for n in dir(A) if n.startswith("TOPIC_") and n != "TOPIC_PREIMAGES"}
    assert set(A.TOPIC_PREIMAGES) == names


def test_the_preimages_match_the_verified_source():
    """The abbreviated hashes in docs/curator_game_mechanics.md are not the
    authority; src/WhitelistCurator.sol is.

    Parsed out of the capture rather than retyped, so an argument-list edit in
    a re-capture fails here instead of shipping a filter that matches nothing.
    """
    sigs = _event_signatures_from_source()   # regex over captures/source.sol
    assert set(A.TOPIC_PREIMAGES.values()) == set(sigs)


def test_every_topic_appears_in_the_captured_log_sweep_or_is_documented_absent():
    """Three of the six have never fired. Say which, in the test."""
    seen = {log["topics"][0] for log in capture("tenderly_logs.json")}
    assert A.TOPIC_LAUNCHED in seen
    assert A.TOPIC_DEPOSITED in seen
    assert A.TOPIC_FIRST_DEPOSIT in seen
    # Never fired as of 2026-08-16 21:14 UTC. Their decoders therefore ship
    # against synthetic rows whose *shape* comes from the ABI (see the plan's
    # "synthetic until captured" table). If one of these starts appearing,
    # this test tells you a real fixture is now available.
    assert A.TOPIC_HOUR_SAVED not in seen
    assert A.TOPIC_SETTLED not in seen
    assert A.TOPIC_RESCUED not in seen
```

- [ ] Run and state the expected failure: `AttributeError: … has no attribute
      'TOPIC_PREIMAGES'`.
- [ ] Append the implementation. Compute each literal with
      `.venv/bin/python -c "from maxpane_dashboard.data.keccak import keccak256_hex; print(keccak256_hex(b'...'))"`
      and paste the result — do **not** copy the abbreviated forms from the mechanics doc.
      Cross-check the leading bytes against that doc's table (`Deposited` starts `0xb8385097`,
      `FirstDeposit` `0xe5a1ae96`, `HourSaved` `0xab7cfcae`, `Settled` `0x0b88c5bd`,
      `Rescued` `0x8aec0ce3`, `Launched` `0x1a3476a1`); a mismatch means a wrong preimage, and
      the *source* wins the argument.
- [ ] Run to green.
- [ ] **Prove the test bites** (decoder-shaped code, house rule): temporarily drop one
      `uint256` from `TOPIC_PREIMAGES["TOPIC_DEPOSITED"]`, run
      `-k preimage` → `test_topic_matches_its_preimage[TOPIC_DEPOSITED-…]` FAILS. Restore.
- [ ] Commit:
      `git add -u && git commit -m "feat(curator): vendor the six event topics, each recomputed from its preimage"`

**Done when:** all six hashes are recomputed in-test from preimages that are themselves
checked against `source.sol`, and the three never-fired events are documented as such.

---

### Task WP0.4: The selector table, cross-checked against the captured batch

**Files:**
- Modify: `maxpane_dashboard/data/curator_addresses.py`
- Test: `tests/data/test_curator_addresses.py`

**Interfaces:**
- Produces: one `SEL_*` constant per view the dashboard calls, plus
  `SELECTOR_PREIMAGES: dict[str, str]`, plus two ordered tuples the client batches with:
  `FAST_VIEW_SELECTORS: tuple[tuple[str, str], ...]` (name, selector) and
  `ONCE_VIEW_SELECTORS`, and `WALLET_VIEW_SELECTORS` for the six argument-taking calls.

**The view surface (all from `source.sol`; return-word counts matter to the decoder):**

| group | preimage | returns |
|---|---|---|
| fast | `isSettled()` | 1 word, **bool** |
| fast | `currentHour()` | 1 |
| fast | `currentHourTotal()` | 1 |
| fast | `ethNeededThisHour()` | 1 |
| fast | `timeLeftInHour()` | 1 |
| fast | `lastActiveHour()` | **2** (`hour`, `total`) |
| fast | `earlyMultiplierBps()` | 1 |
| fast | `stats()` | **3** (`volume`, `people`, `txs`) |
| once | `launchTime()` `hourlyThreshold()` `gracePeriod()` `hourDuration()` `minDeposit()` `minEscalation()` `creditCap()` `firstJudgedHour()` `POINTS_PER_ETH()` `deployer()` | 1 each |
| cross-check | `totalVolume()` `totalContributors()` `totalTxCount()` | 1 each — the same three numbers `stats()` returns, from a different storage read |
| wallet | `pointsOf(address)` `weightOf(address)` `contributedBy(address)` `txCountOf(address)` `requiredNext(address)` | 1 each |
| wallet | `firstHourOf(address)` | **2** (`hour`, `hasJoined` — a bool in the second word) |
| once (amendment) | `previewPoints(uint256)` | 1 — see the plan's spec amendment 2 |

**Steps:**

- [ ] Append the failing tests:

```python
@pytest.mark.parametrize("name,preimage", sorted(A.SELECTOR_PREIMAGES.items()))
def test_selector_matches_its_preimage(name, preimage):
    assert getattr(A, name) == keccak256_hex(preimage.encode("ascii"))[:10]


def test_every_parameterless_selector_appears_in_the_captured_batch():
    """The cross-check that makes the table trustworthy without a network.

    ``captures/batch.json`` is the real 21-call round that publicnode answered.
    Every parameterless selector this module vendors must be one of those 21,
    and all 21 must be accounted for -- an unaccounted selector in the capture
    is a view the research used and this module forgot.
    """
    sent = {c["params"][0]["data"] for c in capture("batch.json")}
    assert len(sent) == 21
    vendored = {
        getattr(A, n) for n, p in A.SELECTOR_PREIMAGES.items() if p.endswith("()")
    }
    assert vendored == sent, (
        f"vendored-not-captured: {sorted(vendored - sent)}; "
        f"captured-not-vendored: {sorted(sent - vendored)}"
    )


def test_the_two_views_that_both_returned_zero_are_told_apart_by_hash():
    """``isSettled()`` and ``ethNeededThisHour()`` both answered 0x0 at capture
    (not settled; grace, so nothing is needed).  Positional reasoning over
    ``results.json`` therefore cannot distinguish them and must not be used --
    the recomputed hash is the only discriminator, and this test is the record
    that the question was asked."""
    assert A.SEL_IS_SETTLED != A.SEL_ETH_NEEDED_THIS_HOUR
    idx = {c["params"][0]["data"]: c["id"] for c in capture("batch.json")}
    results = {r["id"]: r["result"] for r in capture("results.json")}
    assert int(results[idx[A.SEL_IS_SETTLED]], 16) == 0
    assert int(results[idx[A.SEL_ETH_NEEDED_THIS_HOUR]], 16) == 0


def test_the_multi_word_views_are_declared_with_their_word_counts():
    """A 2- or 3-word return decoded as 1 word silently drops fields."""
    assert A.VIEW_RETURN_WORDS["SEL_LAST_ACTIVE_HOUR"] == 2
    assert A.VIEW_RETURN_WORDS["SEL_STATS"] == 3
    assert A.VIEW_RETURN_WORDS["SEL_FIRST_HOUR_OF"] == 2
    assert A.VIEW_RETURN_WORDS["SEL_IS_SETTLED"] == 1
```

- [ ] Run and state the expected failure.
- [ ] Append the implementation: the `SEL_*` literals (each computed with `keccak256_hex`, not
      remembered), `SELECTOR_PREIMAGES`, `VIEW_RETURN_WORDS`, and the three ordered tuples.
      **The ordered tuples are the batch contract**: WP2 sends them in order and decodes
      positionally, so a reorder is a silent field swap — a test in WP2 re-asserts the order
      against `VIEW_RETURN_WORDS`.
- [ ] Run to green. The batch-coverage test is the one that matters; if it reports
      `captured-not-vendored`, recompute the missing preimage from `source.sol` rather than
      deleting the assertion.
- [ ] **Prove it bites:** swap two entries in `FAST_VIEW_SELECTORS`; the WP0 tests stay green
      (order is not their subject) — note this explicitly in the WP2 hand-off so WP2.4 owns
      the order test. Then corrupt one selector literal by a nibble →
      `test_selector_matches_its_preimage` and the batch-coverage test both FAIL. Restore.
- [ ] Commit:
      `git add -u && git commit -m "feat(curator): vendor the view selector table, cross-checked against the captured batch"`

**Done when:** all 21 captured selectors are vendored, each recomputed from a preimage, with
return-word counts declared and the two zero-returning views distinguished by hash.

---

### Task WP0.5: Model dataclasses and `CONSTRUCTOR_KWARGS`

**Files:**
- Create: `maxpane_dashboard/data/curator_models.py`
- Test: `tests/data/test_curator_models.py`

**Interfaces.** This task is the single source of truth for the model vocabulary and it must
land before any WP2 or WP5 code is written. Three rules kept the list honest:

1. **Every field has exactly one named producer.** A field no work package can fill is a field
   WP5 reads as `None` forever while every test stays green.
2. **Models mirror the chain; the flat dict mirrors the PRD.** The getter is `isSettled()` so
   the field is `settled`; the hero key is `phase`. The mapping is table-ised in WP5.
3. **The client returns raw; interpretation is pure-function work.** `DepositEvent` carries the
   decoded event words and nothing derived — `points`, `margin` and cluster membership are all
   WP3's, which is what gives those functions exactly one caller each.

Produced dataclasses (all `@dataclass(frozen=True, slots=True)`, wei-native):

- `CuratorState(settled: bool|None, current_hour: int|None, current_hour_total_wei: int|None,
  hour_needed_wei: int|None, hour_seconds_left: int|None, last_active_hour: int|None,
  last_active_hour_total_wei: int|None, early_bps: int|None, volume_wei: int|None,
  contributors: int|None, tx_count: int|None, forced_balance_wei: int|None,
  block_number: int|None = None)` — producer WP2.4 + WP2.6.
- `CuratorConfig(launch_time: int|None, hourly_threshold_wei: int|None,
  grace_period: int|None, hour_duration: int|None, min_deposit_wei: int|None,
  min_escalation_wei: int|None, credit_cap_wei: int|None, first_judged_hour: int|None,
  points_per_eth: int|None, deployer: str|None)` — producer WP2.4, `once` tier.
- `WalletState(address: str, points: int|None, weight_wei: int|None,
  contributed_wei: int|None, tx_count: int|None, first_hour: int|None,
  has_joined: bool|None, required_next_wei: int|None)` — producer WP2.5.
  `first_hour` is **already un-shifted** (`firstHourOf()`'s semantics); `has_joined` is the
  second return word. `first_hour=0, has_joined=False` means "never deposited" and must never
  render as "joined in hour 0".
- `DepositEvent(contributor: str, hour: int, amount_wei: int, credited_delta_wei: int,
  weight_added_wei: int, new_weight_wei: int, tx_count: int, hour_total_wei: int,
  early_bps: int, block_number: int, tx_hash: str, log_index: int, ts: float|None = None)`
  — producer WP2.7; `ts` is filled by WP2.8's block-timestamp batch and is `None` when that
  read failed (renders `--:--`, never `00:00`).
- `ContributorRow(address: str, weight_wei: int, credit_wei: int, tx_count: int,
  first_hour: int|None, first_index: int|None, points: int|None = None)` — producer WP3.6
  (the fold). `points` stays `None` until the curve is applied.
- `HourBucket(hour: int, volume_wei: int, deposits: int, judged: bool,
  saved_by: str|None = None)` — producer WP3.7.
- `SettlementRecord(settled: bool, block_number: int|None, observed_at: float,
  settled_hour: int|None = None, settled_at_ts: int|None = None,
  total_contributors: int|None = None, total_volume_wei: int|None = None)` — producer WP5.4.
  The first three come from the **view** observation (the latch); the last four are filled
  from the `Settled` log when it eventually appears (the obituary).
- `LogSweep(from_block: int|None, to_block: int|None, deposits: tuple[dict, ...] = (),
  first_deposits: tuple[dict, ...] = (), hour_saved: tuple[dict, ...] = (),
  settled: tuple[dict, ...] = (), rescued: tuple[dict, ...] = (),
  launched: tuple[dict, ...] = ())` — producer WP2.7, **raw** log rows with `topics`, `data`,
  `blockNumber`, `transactionHash`, `logIndex` intact. `()` means "read, nothing matched"
  **or** "this one filter failed"; a frozen tuple cannot hold `None`, so the per-group failure
  travels out-of-band in the client's `log_group_failed` dict (the `surf_client` pattern) and
  reaches the user through the manager's `degraded` list. A sweep where **every** group failed
  returns `None` instead of a `LogSweep`.

**Steps:**

- [ ] Write the failing test `tests/data/test_curator_models.py` with the surf structure:
      `test_models_are_frozen_dataclasses`, `CONSTRUCTOR_KWARGS`,
      `test_field_names_are_exactly_the_frozen_vocabulary`,
      `test_every_model_constructs_from_its_documented_kwargs`,
      `test_no_model_field_defaults_to_zero`, `test_wei_fields_are_named_wei`,
      `test_module_has_no_io_imports`, plus these curator-specific ones:

```python
def test_the_three_legitimate_zeros_are_constructible_and_distinct_from_none():
    """This contract has zeros that are answers, not failures.

    ``currentHourTotal`` is 0 at every hour boundary; ``ethNeededThisHour`` is 0
    through the whole grace period and again whenever an hour is safe;
    ``creditedDelta`` is 0 for a deposit above the cap. Each must be storable as
    0 and readable back as 0 -- and each must be storable as None meaning "the
    read failed". A model that cannot hold both has already lost the
    distinction the whole dashboard is built on.
    """
    zeroed = CuratorState(**{**_all_none_state(), "current_hour_total_wei": 0,
                             "hour_needed_wei": 0})
    assert zeroed.current_hour_total_wei == 0
    assert zeroed.hour_needed_wei == 0
    assert CuratorState(**_all_none_state()).current_hour_total_wei is None


def test_first_hour_zero_is_not_the_same_as_never_joined():
    """The packed-struct off-by-one, made unrepresentable.

    ``firstHourOf()`` returns ``(0, false)`` for a stranger and ``(0, true)``
    for someone who deposited in hour 0. One field cannot carry both, which is
    why ``has_joined`` exists as a separate bool.
    """
    stranger = WalletState(address=ADDR, points=None, weight_wei=None,
                           contributed_wei=None, tx_count=None,
                           first_hour=0, has_joined=False, required_next_wei=None)
    founder = dataclasses.replace(stranger, has_joined=True)
    assert stranger.first_hour == founder.first_hour == 0
    assert stranger.has_joined is not founder.has_joined


def test_deposit_event_carries_no_derived_field():
    """Raw discipline: points, margin and cluster membership are WP3's.

    A ``points`` field here would give the curve two callers and two test
    suites, and the one in the client would be the one nobody mutation-tests.
    """
    names = {f.name for f in dataclasses.fields(DepositEvent)}
    for derived in ("points", "margin_wei", "cluster_id", "is_whale", "rank"):
        assert derived not in names


def test_log_sweep_groups_default_to_empty_not_missing():
    sweep = LogSweep(from_block=1, to_block=2, deposits=({"topics": []},))
    assert sweep.first_deposits == () and sweep.settled == ()


def test_no_flat_dict_key_masquerades_as_a_model_field():
    flat_only = {
        "phase", "hour_fed_eth", "hour_needed_eth", "volume_routed_eth",
        "top_points", "forced_eth", "you_rank", "as_of_hhmm", "degraded",
    }
    for model in ALL_MODELS:
        clash = flat_only & {f.name for f in dataclasses.fields(model)}
        assert not clash, f"{model.__name__} carries flat-dict key(s) {clash}"
```

- [ ] Run and state the expected failure: `ModuleNotFoundError`.
- [ ] Write `maxpane_dashboard/data/curator_models.py`. The module docstring carries the unit,
      naming, raw and outage disciplines (copy the four-paragraph shape from
      `data/surf_models.py`), plus the curator-specific paragraph on the three legitimate
      zeros and on why `has_joined` is a separate field.
- [ ] Run to green.
- [ ] Commit:
      `git add maxpane_dashboard/data/curator_models.py tests/data/test_curator_models.py && git commit -m "feat(curator): freeze the curator data models as None-safe frozen dataclasses"`

**Done when:** every model is frozen, wei-native, `None`-safe, and its field tuple is pinned by
`CONSTRUCTOR_KWARGS` so a rename fails at import in three suites at once.

---

### Task WP0.6: `CURATOR_KEYS`, `CURATOR_ROW_KEYS`, `PHASES`

**Files:**
- Modify: `maxpane_dashboard/data/curator_models.py`
- Test: `tests/data/test_curator_models.py`

**Interfaces:**
- Produces: `CURATOR_KEYS: tuple[str, ...]` — the exact key set of
  `CuratorManager.fetch_and_compute()`, PRD §5 made precise;
  `CURATOR_ROW_KEYS: dict[str, tuple[str, ...]]` for the six list payloads;
  `PHASES: tuple[str, ...] = ("grace", "judged", "settled")`;
  `SIGNAL_ROWS: tuple[str, ...]` — the seven rail rows in render order.
- Consumed by: `curator_manager` (builds exactly these), `curator_cache` (persists
  `volume_series` / `contributors_series` through `coerce_points`), `screens/curator.py`
  (dispatches), WP4's widget-contract test (imports `CURATOR_KEYS`; the widget *modules*
  import nothing from `data/`).
- **Also owned here:** the `SIGNAL_OUTPUT_KEYS ⊆ CURATOR_KEYS` containment assertion, guarded
  by `pytest.importorskip` so WP0 stays green before `analytics/curator_signals.py` exists.
  Nothing else in the repo compares those two surfaces, and the widget package cannot host the
  check because its import-hygiene test forbids widgets from importing `analytics/` at all.

**The key set** (PRD §5, with the four additions this plan makes explicit — marked ★):

```
phase machine   phase · settled · settled_hour · settled_at_ts · lived_desc
                settled_observed_at ★   (the evidence record's stamp; drives the
                                         "SETTLED as of HH:MM" framing under outage)
clock           current_hour · hour_fed_eth · hour_needed_eth · hour_seconds_left ·
                grace_seconds_left · grace_ends_utc
curve           early_multiplier_x · points_per_eth_now · survival_streak_hours ·
                closest_call_margin_eth · closest_call_hour
list            contributors_total · deposits_total · volume_routed_eth · top_points
signals         last_saved_hour · last_saved_wallet · last_saved_age_s ·
                whale_amount_eth · whale_wallet · whale_age_s · clusters_count ·
                flagged_points_share_pct · forced_eth · rescued_total_eth
                sig_settled_state ★ · sig_at_risk_state ★   (the two rail rows whose
                                         colour is a judgement, not a number)
YOU             you_rank · you_points · you_credit_eth · you_required_next_eth ·
                you_marginal_points
rows            leaderboard_rows · activity_rows · closest_call_rows · cluster_rows ·
                volume_series · contributors_series
health          degraded · as_of_hhmm · as_of ★   (epoch, for the screen's own bookkeeping;
                                         as_of_hhmm is the rendered marker)
```

**Steps:**

- [ ] Append the failing tests:

```python
def test_curator_keys_is_exactly_the_prd_contract():
    assert set(CURATOR_KEYS) == EXPECTED_KEYS
    assert len(CURATOR_KEYS) == len(set(CURATOR_KEYS))


def test_phases_are_the_three_the_prd_names():
    assert PHASES == ("grace", "judged", "settled")


def test_no_wei_key_leaks_into_the_flat_dict():
    assert not [k for k in CURATOR_KEYS if k.endswith("_wei")]


def test_row_key_sets_match_the_prd():
    assert CURATOR_ROW_KEYS["leaderboard_rows"] == (
        "rank", "address", "points", "credit_eth", "tx_count", "flagged",
    )
    assert CURATOR_ROW_KEYS["activity_rows"] == (
        "ts", "address", "amount_eth", "credited_eth", "new_weight",
        "tx_count", "hour", "kind", "tx_hash", "log_index",
    )
    assert CURATOR_ROW_KEYS["closest_call_rows"] == (
        "hour", "volume_eth", "margin_eth", "savior",
    )
    assert CURATOR_ROW_KEYS["cluster_rows"] == (
        "size", "amount_eth", "first_block", "last_block", "points",
        "points_share_pct",
    )
    assert set(CURATOR_ROW_KEYS) <= set(CURATOR_KEYS)


def test_activity_rows_carry_the_dedupe_key():
    """PRD §4: de-dupe by (tx, log index). Both must be in the row shape or the
    widget cannot do it, and a re-org replay renders every deposit twice."""
    assert {"tx_hash", "log_index"} <= set(CURATOR_ROW_KEYS["activity_rows"])


def test_signal_output_keys_are_a_subset_of_curator_keys():
    """The only place the two frozen key surfaces are compared.

    Skips until analytics/curator_signals.py lands; a skip here is the intended
    state, not an outstanding failure. WP0.8 records the deferred bite-proof.
    """
    sig = pytest.importorskip("maxpane_dashboard.analytics.curator_signals")
    missing = sorted(set(sig.SIGNAL_OUTPUT_KEYS) - set(CURATOR_KEYS))
    assert not missing, f"signal keys absent from CURATOR_KEYS: {missing}"
```

- [ ] Run: expect `ImportError: cannot import name 'CURATOR_KEYS'`, and the containment test
      reported **SKIPPED** (confirm with `-rs`).
- [ ] Append the implementation, with a one-line comment per key naming its type and its
      unavailable rendering (the `SURF_KEYS` style). Every numeric is `float|int|None` and
      `None` renders the widget's unavailable state, never a 0.
- [ ] Run to green (one skip).
- [ ] Commit:
      `git add -u && git commit -m "feat(curator): freeze CURATOR_KEYS, the row shapes and the phase vocabulary"`
- [ ] **Deferred bite-proof, recorded on the WP0.8 checklist** — the day
      `analytics/curator_signals.py` lands: rename one entry of `SIGNAL_OUTPUT_KEYS`, run
      `-k subset -v` → FAILS naming the key; restore → green (**not** skipped). If it still
      skips, the `importorskip` path is wrong and the guard has been dead the whole time.

**Done when:** the flat contract is importable, exact, and pinned against both the PRD and
(deferred) the analytics layer.

---

### Task WP0.7: The shared capture reader and the fact pins

**Files:**
- Create: `tests/curator_fixtures.py`
- Modify: `tests/data/test_curator_captures.py`
- Modify: `tests/fixtures/curator/captures/README.md` (add the required-set manifest)

**Interfaces:**
- Produces: `tests.curator_fixtures.CURATOR_FIXTURES: Path`, `CAPTURES: Path`,
  `LIVE: Path`, `capture(name) -> Any`, `live_bundles() -> list[Path]`. That is the whole
  module — no envelope helper, because WP0 commits no derived fixture for one to open.
- Consumes: nothing. `json` and `pathlib`; reads files, opens no socket.

**Why the pins matter.** Every number a later work package hardcodes is asserted here, against
the capture, in one place. A re-capture that moves one of them fails once, in the file that
owns it, instead of drifting through six work packages.

**Steps:**

- [ ] Write `tests/curator_fixtures.py` (model it on `tests/surf_fixtures.py`). `LIVE` points
      at `captures/live/` and `live_bundles()` returns a **sorted, possibly empty** list —
      empty is the normal state before WP1's first timed run, and no test may fail on it.
- [ ] Add the ownership and hygiene guards to `tests/data/test_curator_captures.py`:

```python
#: The captures committed with the research session. Named, never counted:
#: WP1 lands more files under ``captures/live/`` at unpredictable moments, and a
#: count-based guard would turn this suite red for a *successful* capture.
REQUIRED_CAPTURES = (
    "source.sol", "contract.json", "wc_abi.json", "creation_tx.json",
    "tenderly_logs.json", "batch.json", "results.json", "ann_page_0.json",
    *(f"bs_page_{i}.json" for i in range(8)),
    "README.md",
)


def test_the_required_captures_are_committed_and_readable():
    names = {p.name for p in CAPTURES.iterdir()}
    missing = [n for n in REQUIRED_CAPTURES if n not in names]
    assert not missing, missing
    for name in REQUIRED_CAPTURES:
        if name.endswith(".json"):
            assert json.loads((CAPTURES / name).read_text("utf-8")) is not None, name


def test_the_fixtures_root_holds_directories_only():
    """WP0 owns captures/, WP1 owns captures/live/, every other WP owns its own
    subdirectory. A loose *.json at the root is a file with no owner, and it is
    how one WP's slice lands in another WP's glob."""
    loose = sorted(p.name for p in CURATOR_FIXTURES.iterdir() if p.is_file())
    assert loose == [], f"put these in a per-work-package subdirectory: {loose}"


def test_no_capture_carries_an_api_key():
    for path in sorted(CAPTURES.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text("utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"


def test_no_live_bundle_breaks_the_reader():
    """Zero bundles is the normal pre-WP1 state and must stay green."""
    for path in live_bundles():
        assert json.loads(path.read_text("utf-8")) is not None, path.name
```

- [ ] Append the **fact pins** — every number a later WP will quote:

```python
def test_the_batch_round_decodes_to_the_documented_state():
    """The 21 views, at 2026-08-16 ~21:12 UTC, hour 1 of the game.

    Keyed by *selector*, never by list position: two of the 21 returned 0x0 and
    positional reasoning cannot tell them apart (WP0.4).
    """
    v = _decoded_batch()          # {selector: int|tuple, from batch.json+results.json}
    assert v[A.SEL_POINTS_PER_ETH] == 1000
    assert v[A.SEL_CREDIT_CAP] == 1000 * 10**18
    assert v[A.SEL_HOURLY_THRESHOLD] == 5 * 10**18
    assert v[A.SEL_GRACE_PERIOD] == 86_400
    assert v[A.SEL_HOUR_DURATION] == 3_600
    assert v[A.SEL_MIN_DEPOSIT] == 5 * 10**16          # 0.05 ETH
    assert v[A.SEL_MIN_ESCALATION] == 10**17           # 0.1 ETH
    assert v[A.SEL_FIRST_JUDGED_HOUR] == 24
    assert v[A.SEL_LAUNCH_TIME] == 1_786_910_327
    assert v[A.SEL_CURRENT_HOUR] == 1
    assert v[A.SEL_IS_SETTLED] == 0
    assert v[A.SEL_ETH_NEEDED_THIS_HOUR] == 0
    assert v[A.SEL_TIME_LEFT_IN_HOUR] == 2_796
    # 19491 bps == 1.9491x. NOT ~1.99x -- a fixture calibrated to 1.99 would
    # miscompute every weight derived from it.
    assert v[A.SEL_EARLY_MULTIPLIER_BPS] == 19_491
    assert v[A.SEL_STATS] == (0x560119983627C22D4F, 143, 222)
    # stats() and the three public counters are different storage reads of the
    # same numbers; they agreeing is what makes the slow-tier cross-check
    # meaningful.
    assert v[A.SEL_TOTAL_VOLUME] == v[A.SEL_STATS][0]
    assert v[A.SEL_TOTAL_CONTRIBUTORS] == v[A.SEL_STATS][1]
    assert v[A.SEL_TOTAL_TX_COUNT] == v[A.SEL_STATS][2]
    # The hour-boundary hazard is INVISIBLE in this capture: the current hour
    # IS the last active hour, so both agree. That is precisely why WP1 capture
    # A exists.
    assert v[A.SEL_LAST_ACTIVE_HOUR] == (1, v[A.SEL_CURRENT_HOUR_TOTAL])


def test_the_derived_config_is_self_consistent():
    v = _decoded_batch()
    assert v[A.SEL_FIRST_JUDGED_HOUR] == v[A.SEL_GRACE_PERIOD] // v[A.SEL_HOUR_DURATION]
    # The doomsday deadlines every phase test is calibrated on.
    assert v[A.SEL_LAUNCH_TIME] + v[A.SEL_GRACE_PERIOD] == 1_786_996_727   # 08-17 19:58:47Z
    assert v[A.SEL_LAUNCH_TIME] + 25 * 3600 == 1_787_000_327               # 08-17 20:58:47Z


def test_the_log_sweep_holds_the_history_the_folds_are_tested_against():
    logs = capture("tenderly_logs.json")
    assert len(logs) == 377
    by_topic = Counter(l["topics"][0] for l in logs)
    assert by_topic[A.TOPIC_DEPOSITED] == 226
    assert by_topic[A.TOPIC_LAUNCHED] == 1
    # FirstDeposit.index is 1-based and monotonic == totalContributors.
    idx = sorted(int(l["topics"][2], 16)
                 for l in logs if l["topics"][0] == A.TOPIC_FIRST_DEPOSIT)
    assert idx == list(range(1, len(idx) + 1))
    assert max(idx) == 145      # the sweep caught two more than the batch's 143


def test_the_weight_formula_cross_check_event_is_present_and_exact():
    """The one real witness for ``weightAdded = creditedDelta * earlyBps // 1e4``.

    0.05 ETH at 19975 bps -> 0.099875 ETH of weight, to the wei. WP3.4 asserts
    this with ``==``; here we prove the event it asserts against exists.
    """
    ev = _first_deposit_with(early_bps=19_975, amount_wei=5 * 10**16)
    assert ev["credited_delta_wei"] == 5 * 10**16
    assert ev["weight_added_wei"] == 99_875_000_000_000_00   # 0.099875e18
    assert ev["weight_added_wei"] == 5 * 10**16 * 19_975 // 10_000


def test_every_captured_deposit_satisfies_the_weight_identity():
    """226 rows, no exceptions. This is the differential WP3.4 re-runs."""
    for ev in _deposits():
        assert ev["weight_added_wei"] == (
            ev["credited_delta_wei"] * ev["early_bps"] // 10_000
        )


def test_the_fan_out_cluster_is_in_the_data():
    """The cluster heuristic's real positive: 9 wallets, exactly 60 ETH each,
    inside a ~32-block window (25 770 115-25 770 143)."""
    sixty = [e for e in _deposits() if e["amount_wei"] == 60 * 10**18]
    assert len(sixty) == 9
    blocks = sorted(e["block_number"] for e in sixty)
    assert blocks[0] == 25_770_115 and blocks[-1] == 25_770_143
    assert len({e["contributor"].lower() for e in sixty}) == 9


def test_no_capture_carries_a_credited_delta_of_zero():
    """The cap case has no real instance: the largest single send is 461.1 ETH
    against a 1000 ETH cap. WP3.5's fixture is therefore SYNTHETIC by necessity,
    and this assertion is what keeps that documented rather than forgotten."""
    assert all(e["credited_delta_wei"] > 0 for e in _deposits())
    assert max(e["amount_wei"] for e in _deposits()) < 1000 * 10**18


def test_no_capture_carries_a_block_timestamp():
    """Tenderly's eth_getLogs returns none, and Blockscout's log items carry
    only ``block_number`` (the ``timestamp`` field in bs_page_* is
    FirstDeposit's own *data* field). This is why WP2.8 exists."""
    assert all("blockTimestamp" not in l for l in capture("tenderly_logs.json"))


def test_the_blockscout_pages_reconcile_with_the_rpc_sweep():
    """376 vs 377: the one extra tenderly log landed between the two pulls.
    Pinned as an exact relationship so a re-capture that silently loses a page
    fails here."""
    bs = [i for p in range(8) for i in capture(f"bs_page_{p}.json")["items"]]
    assert len(bs) == 376
    rpc_keys = {(l["transactionHash"], int(l["logIndex"], 16))
                for l in capture("tenderly_logs.json")}
    bs_keys = {(i["transaction_hash"], i["index"]) for i in bs}
    assert bs_keys <= rpc_keys
    assert len(rpc_keys - bs_keys) == 1


def test_the_announce_channel_never_mentioned_the_curator():
    """PRD §7 and §12: the launch was unannounced. Pinned so a later 'surely
    they posted about it' assumption has to argue with the capture.
    Surf is OUT OF SCOPE -- this is a fact pin, not a feature."""
    page = capture("ann_page_0.json")
    blob = json.dumps(page).lower()
    assert A.CURATOR.lower() not in blob
```

- [ ] Add the required-set manifest to `tests/fixtures/curator/captures/README.md`: a short
      section stating that the sixteen JSON/sol files plus this README are the *required set*,
      that `live/` is WP1's and grows, and that the pins live in
      `tests/data/test_curator_captures.py`.
- [ ] Run: `.venv/bin/python -m pytest tests/data/test_curator_captures.py -v`
- [ ] **Prove the ownership guard bites:** `touch tests/fixtures/curator/stray.json`, run
      `-k root` → FAILS naming the file. Delete it.
- [ ] **Prove a fact pin bites:** temporarily change the expected `early_bps` to `19_900` →
      `test_the_batch_round_decodes_to_the_documented_state` FAILS. Restore.
- [ ] Commit:
      `git add tests/curator_fixtures.py tests/data/test_curator_captures.py tests/fixtures/curator/captures/README.md && git commit -m "test(curator): add the shared capture reader and pin every fact the plan quotes"`

**Done when:** every number this plan and the later WPs quote is asserted against a committed
payload, and the fixture root has one owner per directory.

---

### Task WP0.8: Freeze sign-off

**Files:** none created. This task is a gate.

**Steps:**

- [ ] Run the whole WP0 surface:
      `.venv/bin/python -m pytest tests/data/test_curator_addresses.py tests/data/test_curator_models.py tests/data/test_curator_captures.py -v`
      Expect green with exactly **one skip** (`test_signal_output_keys_are_a_subset_of_curator_keys`).
- [ ] Run the full suite to prove WP0 disturbed nothing:
      `.venv/bin/python -m pytest -q` — the pre-existing ~2100 tests stay green. WP0 adds
      files only; if anything else moved, find out why before signing off.
- [ ] Confirm the structural no-network property:
      `.venv/bin/python -c "import maxpane_dashboard.data.curator_addresses, maxpane_dashboard.data.curator_models"`
      runs with no `httpx`/`textual` import (verify with `-X importtime` or by inspecting the
      module sources — the tests already assert it, this is the human check).
- [ ] Write the **hand-off note** into the WP0 commit message body or a short comment at the
      top of `curator_models.py`, listing for the parallel wave:
      1. the frozen names (`CURATOR_KEYS`, `CURATOR_ROW_KEYS`, `PHASES`, `SIGNAL_ROWS`,
         `CONSTRUCTOR_KWARGS`, the `SEL_*`/`TOPIC_*` tables and the three ordered selector
         tuples);
      2. the two deferred bite-proofs (WP0.6's containment test; WP0.4's selector-order test,
         which is WP2.4's to own);
      3. the synthetic-fixture list from the index plan, so WP2/WP3/WP5 mark their synthetic
         fixtures with `# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`
         from the first commit rather than retrofitting the comment later.
- [ ] Commit: `git commit --allow-empty -m "chore(curator): WP0 interface freeze signed off"`

**Done when:** the three suites are green with one documented skip, the full suite is
unchanged, and the hand-off note exists. **Wave 2 may now start.**
