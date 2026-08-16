# WP5 — `data/curator_cache.py` + `data/curator_manager.py`

**Goal:** Tiered fetching, persistence, the settlement evidence latch, the fold that never
touches state, and one `fetch_and_compute()` that returns exactly `CURATOR_KEYS` — always,
under every failure combination, without ever letting an exception escape.

**Dependencies:** WP0 (models, keys), WP2 (`CuratorClient`), WP3 (`build_signals`,
`READING_KEYS`). Wave 3, alone — this WP is the critical path's narrowest point.

**Owner note.** This WP owns and creates:

- `maxpane_dashboard/data/curator_cache.py`
- `maxpane_dashboard/data/curator_manager.py`
- `tests/data/test_curator_cache.py`
- `tests/data/test_curator_manager.py`
- `tests/data/test_curator_degradation.py`

It touches nothing else. `curator_client.py` and `curator_signals.py` are read-only here: a
defect in either is **reported**, not fixed.

### Ground rules

- **`fetch_and_compute()` never raises.** It returns the full `CURATOR_KEYS` dict with `None`
  values and a populated `degraded` list under every failure combination. The screen's
  `try/except` is belt and braces for a mis-wired manager, never the documented outage path.
- **A failed read is `None`, never `0`, and no sentinel ever enters a persisted series.**
- **All loaders take `now=`; the cache takes `clock=`.** No `time.time()` inside anything a
  test drives.
- **Every persisted series loads through `data/series_points.coerce_points`.**
- **Analytics calls go through `data/safe_call.safe_call`** so an analytics bug costs one
  number, not the cycle.
- **Failure never marks a tier fetched.** `mark_failed(tier, retry_after=…)` with a per-tier
  backoff, the `surf_cache` pattern.
- Commit after each task.

---

### Task WP5.1: `CuratorCache` — tiers, slots, clock

**Interfaces:** produces `DEFAULT_CACHE_PATH = ~/.maxpane/curator_cache.json`,
`_SCHEMA_VERSION`, `TIER_FAST/MEDIUM/SLOW/ONCE`, `TIER_TTL_SECONDS = {fast: 15, medium: 60,
slow: 420, once: inf}`, `TIER_FAILURE_BACKOFF_SECONDS`, the slot names
`SLOT_STATE/LOGS/WALLET/CONFIG/BLOCKSCOUT`, and `class CuratorCache` with `is_fresh`,
`is_due`, `tiers_due`, `mark_fetched`, `mark_failed`, `store_last_good`, `get_last_good`,
`as_of_ts`, `age_of`, `newest_as_of` — the `surf_cache` surface.

**Steps:**

- [ ] Failing tests: TTLs drive `tiers_due` off an injected clock with zero sleeping; a failed
      tier is **not** marked fetched and comes due again after its backoff, not its TTL;
      `store_last_good(slot, None)` is **refused** (storing `None` would overwrite a good
      payload and its provenance with an absence); an unknown tier or slot raises `ValueError`
      naming the valid set; the `once` tier never comes due twice after a success.
- [ ] Implement.
- [ ] Commit: `feat(curator): tiered cache with injected clock and failure backoff`

---

### Task WP5.2: Persistence, schema version and `coerce_points`

**Steps:**

- [ ] Failing tests:

```python
def test_a_single_null_in_a_series_does_not_abort_the_load():
    """The bug that once broke startup for EVERY dashboard, not just the one
    owning the file. A corrupt point is dropped and counted, never fatal."""
    _write({"volume_series": [[1, 2], [3, None], "junk", [5, 6]], ...})
    cache.load(now=NOW)
    assert cache.get_series("volume_series") == [[1.0, 2.0], [5.0, 6.0]]


def test_every_persisted_series_goes_through_coerce_points():
    src = inspect.getsource(curator_cache)
    assert "coerce_points" in src
    assert "float(pt[1])" not in src        # the hand-rolled version that broke


def test_a_future_dated_point_is_dropped_and_a_slightly_fast_clock_is_not():
    ...     # CLOCK_SKEW_TOLERANCE_SECONDS


def test_an_unknown_schema_version_loads_nothing_rather_than_guessing():
    ...


def test_save_is_atomic():
    """temp + rename, so a kill mid-write leaves the previous file intact."""
    ...


def test_a_missing_or_unreadable_cache_file_is_silently_an_empty_cache():
    ...
```

- [ ] Implement with the `surf_cache` `_jsonable` sanitiser and temp+rename save.
- [ ] Commit: `feat(curator): atomic persistence with per-point series validation`

---

### Task WP5.3: The series — fed from logs only (H2, mandated mutation #2)

**Interfaces:** produces `record_hour_buckets(buckets, *, now=None)`,
`record_contributor_count(total, *, ts, now=None)`, `get_series(name)`,
`SERIES_NAMES = ("volume_series", "contributors_series")`.

**Steps:**

- [ ] Failing tests:

```python
def test_the_series_writer_takes_folded_buckets_not_a_state_reading():
    """H2, structural. ``currentHourTotal()`` legitimately drops to 0 at every
    hour boundary while ``lastActiveHour()`` still names the previous bucket. A
    state-poll sparkline reads that as a crash -- and the zero gets PERSISTED,
    so the corruption outlives the boundary that produced it."""
    params = set(inspect.signature(CuratorCache.record_hour_buckets).parameters)
    assert params == {"self", "buckets", "now"}
    src = inspect.getsource(curator_cache)
    for banned in ("current_hour_total", "currentHourTotal"):
        assert banned not in src


def test_the_fast_tier_payload_cannot_reach_the_series():
    """The other half of the same guarantee, from the manager's side: the keys
    the fast tier produces and the keys the series writer consumes are
    disjoint sets, asserted rather than reasoned about."""
    assert not (set(FAST_TIER_PAYLOAD_KEYS) & set(SERIES_INPUT_KEYS))


def test_the_boundary_fixture_writes_no_zero():
    """The behavioural half. Replay: hour 1 with 730 ETH, then the boundary
    state where currentHourTotal is 0 and lastActiveHour still says hour 1.
    The series must still read [.., 730] -- the boundary is invisible to it.

    # SYNTHETIC -- re-point at tests/fixtures/curator/captures/live/<bundle>
    # (WP1.3 capture A). The synthetic is captures/results.json with two words
    # changed; the real pair is the same two words changed by the chain.
    """
    cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))
    cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))  # boundary tick
    assert 0.0 not in [v for _ts, v in cache.get_series("volume_series")[:-1]]


def test_a_genuinely_silent_hour_does_write_a_zero():
    """The mirror image, and the reason the rule is 'from logs only' rather
    than 'never write a zero'. A judged hour that took in nothing IS a zero,
    and it is the most important point on the chart."""
    ...
```

- [ ] Implement.
- [ ] **Mandated prove-it-bites #2 (PRD §8, the hour-boundary rule):** add a
      `current_hour_total_wei` parameter to `record_hour_buckets` and let it overwrite the last
      bucket; run the boundary fixture → `test_the_boundary_fixture_writes_no_zero` FAILS with
      a `0.0` in the series, and `test_the_series_writer_takes_folded_buckets_not_a_state_reading`
      FAILS on the signature. Restore. **Record the evidence for WP7.12.**
- [ ] Commit: `feat(curator): hourly series fed exclusively from folded Deposited logs`

---

### Task WP5.4: The settlement evidence latch (H1, mandated mutation #1)

**Interfaces:** produces `observe_settlement(settled, *, block_number, now=None) ->
SettlementRecord | None`, `settlement_record() -> SettlementRecord | None`,
`record_settled_event(hour, ts, contributors, volume_wei)`.

**The rule (PRD §3).** `isSettled()` is the truth; the `Settled` event is the obituary. The
moment a fetch observes `True`, persist `{value, block_number, observed_at}`. From then on the
dashboard renders SETTLED **through RPC outages** — an outage degrades the freshness marker,
never the phase. This latch cannot be griefed: it reads a one-way predicate the contract
itself enforces, not attacker-emittable logs.

**Steps:**

- [ ] Failing tests:

```python
def test_the_first_true_observation_is_persisted_with_its_evidence():
    rec = cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    assert rec.settled is True and rec.block_number == 25_776_000
    assert rec.observed_at == NOW


def test_a_false_observation_never_clears_a_true_one():
    """One-way by construction, and the contract agrees: isSettled() is
    ``_settled || _isShort(currentHour())`` and never returns false again. A
    later false can only be a bad read, a wrong endpoint, or a fork."""
    cache.observe_settlement(True, block_number=1, now=NOW)
    cache.observe_settlement(False, block_number=2, now=NOW + 15)
    assert cache.settlement_record().settled is True


def test_a_none_observation_never_clears_a_true_one():
    """The outage case, which is the whole point."""
    cache.observe_settlement(True, block_number=1, now=NOW)
    cache.observe_settlement(None, block_number=None, now=NOW + 15)
    assert cache.settlement_record().settled is True


def test_the_latch_survives_a_save_load_round_trip():
    ...


def test_a_persisted_record_is_re_validated_not_trusted():
    """The surf hook_status lesson: never trust the boolean a file happened to
    contain. A record missing block_number or observed_at, or carrying a
    non-bool, is discarded rather than believed."""
    for junk in ({"settled": True}, {"settled": "yes", "block_number": 1,
                 "observed_at": NOW}, {"settled": True, "block_number": "x",
                 "observed_at": NOW}):
        _write({"settlement": junk, ...})
        cache.load(now=NOW)
        assert cache.settlement_record() is None


def test_the_settled_event_fills_the_obituary_without_creating_the_latch():
    """A Settled log with no prior view observation must NOT set the latch:
    the event is evidence about the past, the view is evidence about now. (In
    practice they agree -- but a log-only latch is the exact hazard the PRD
    names, one level down.)"""
    cache.record_settled_event(hour=24, ts=1_787_000_400, contributors=300,
                               volume_wei=9 * 10**21)
    assert cache.settlement_record() is None
    cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    rec = cache.settlement_record()
    assert rec.settled_hour == 24 and rec.total_contributors == 300
```

- [ ] Implement.
- [ ] **Mandated prove-it-bites #1 (PRD §8, the settlement latch):** change
      `settlement_record()` to re-read the live value instead of the persisted record (i.e.
      make the latch transparent) → `test_a_none_observation_never_clears_a_true_one` FAILS,
      and WP5.13's end-to-end "outage after settlement still renders SETTLED" FAILS. Restore.
      **Record the evidence for WP7.12.**
- [ ] Commit: `feat(curator): settlement evidence latch, re-validated and outage-proof`

---

### Task WP5.5: The folded contributor table and the block watermark

**Interfaces:** produces `store_fold(rows, *, last_block, now=None)`, `fold_rows()`,
`last_seen_block()`, `MAX_PERSISTED_EVENTS` with a documented drop count.

**Steps:**

- [ ] Failing tests: the watermark advances only on a **successful** sweep (a failed sweep must
      not skip a block range forever — the gap-repair tier exists because that once happened);
      a watermark of `None`/absent means "backfill from `CREATION_BLOCK`", never "start from
      now"; a persisted row with a missing field is dropped and counted, not fatal; the row cap
      drops **oldest** events and logs the count.
- [ ] Implement.
- [ ] **Prove it bites:** advance the watermark before the sweep succeeds → the failed-sweep
      test FAILS with a permanent gap. Restore.
- [ ] Commit: `feat(curator): persisted fold, block watermark and bounded event history`

---

### Task WP5.6: Cluster state persistence

**Steps:**

- [ ] Failing tests: clusters persist and reload; a reloaded cluster whose block window is
      outside the retained history is dropped rather than rendered; the flagged-points share
      is recomputed on load, never restored from disk (it is a ratio against a total that
      changes every hour).
- [ ] Implement.
- [ ] Commit: `feat(curator): persist cluster state with a recomputed points share`

---

### Task WP5.7: `CuratorManager` skeleton, sources and `degraded`

**Interfaces:** produces `SOURCES = ("state", "logs", "wallet")` (PRD §5's exact vocabulary),
`GROUP_SLOT`, `class CuratorManager(client=None, cache=None, poll_interval=30,
wallet=None, clock=time.time)`, `_guard(coro, name)`, `_note(group, ok)`, `_degraded()`,
`save_cache()`, `async close()`.

**Steps:**

- [ ] Failing tests: `degraded` is a sorted list drawn **only** from `SOURCES` (a manager that
      invents `"rpc"` would light a banner the screen's formatter has never seen);
      `_guard` swallows and notes; `close()` awaits the client's `close()` and saves the cache
      **in that order** (a client closed first cannot corrupt a save); `close()` still saves if
      the client's close raises.
- [ ] Implement.
- [ ] Commit: `feat(curator): manager skeleton with the three-source degradation surface`

---

### Task WP5.8: `_pool_state` — the fast tier

**Steps:**

- [ ] Failing tests: one `fetch_state()` + one `fetch_balance()` per fast tick, no more;
      `settled` feeds `observe_settlement`, and **only** that — the fast tier writes no series
      (WP5.3's disjointness test covers it structurally, this covers it behaviourally);
      `forced_balance_wei` reaches `forced_eth` and reaches **nothing else** —
      `test_a_nonzero_balance_never_reaches_a_volume_field` asserts that with a 1.5 ETH
      balance and checks `volume_routed_eth` and `hour_fed_eth` are untouched (H5);
      a failed state read notes `"state"` degraded and leaves the previous last-good standing.
- [ ] Implement.
- [ ] Commit: `feat(curator): fast tier with the settlement observation and forced-ETH anomaly`

---

### Task WP5.9: `_pool_logs` — backfill, incremental, gap repair

**Steps:**

- [ ] Failing tests:

```python
def test_a_first_run_backfills_from_the_creation_block():
    """Validated as one sweep in the research; 377 logs from 25 769 870."""
    assert _recorded_from_block() == A.CREATION_BLOCK


def test_a_later_run_starts_at_the_watermark_plus_one():
    ...


def test_a_failed_sweep_does_not_advance_the_watermark():
    """Otherwise the missed range is missed forever and the leaderboard is
    permanently wrong with no symptom."""
    ...


def test_the_slow_tier_repairs_a_gap_the_fold_missed():
    """PRD §5: cross-check stats() against the folded totals; a mismatch
    triggers a re-sweep of the suspect range rather than a silent wrong number.
    Driven with a fold that is deliberately short by one event."""
    ...


def test_a_stats_mismatch_marks_the_fold_stale_rather_than_publishing():
    ...


def test_one_failed_log_group_degrades_only_its_own_keys():
    """LogSweep's () is ambiguous; log_group_failed resolves it. A dead
    ``settled`` filter must not make the leaderboard look empty, and an empty
    ``hour_saved`` must not read as a failure."""
    ...
```

- [ ] Implement, reading the client's `log_group_failed` dict rather than inferring from `()`.
- [ ] Commit: `feat(curator): log backfill, incremental sweep and stats-cross-check repair`

---

### Task WP5.10: `_pool_wallet` — the YOU tier

**Steps:**

- [ ] Failing tests: with no `MAXPANE_WALLET`, **zero** wallet calls are made and every `you_*`
      key is `None`; with a wallet set, the six calls run on the fast tier; an invalid address
      string is rejected before any call and notes `"wallet"` degraded rather than sending
      garbage to the node; a wallet not on the list yields `you_rank=None` with
      `you_required_next_eth` still populated (the contract answers `minDeposit` for a
      stranger, which is exactly the number that wallet needs — and the most useful thing on
      the row).
- [ ] Implement, reading the wallet from the constructor (the app passes `--wallet` /
      `MAXPANE_WALLET`), never from the environment inside the manager.
- [ ] Commit: `feat(curator): wallet tier, silent and complete when no wallet is configured`

---

### Task WP5.11: `_readings()` — the WP3 seam

**Steps:**

- [ ] Failing tests:

```python
def test_readings_emits_exactly_the_frozen_reading_keys():
    from maxpane_dashboard.analytics.curator_signals import READING_KEYS
    assert set(manager._readings(...)) == set(READING_KEYS)


def test_the_outage_encoding_is_held_constant():
    """None == the read failed. [] == the read succeeded and found nothing.
    Collapsing them makes a dead logs pool indistinguishable from a quiet
    chain -- and 'quiet' is the state that kills this contract."""
    dead = manager._readings(logs=None, ...)
    quiet = manager._readings(logs=LogSweep(from_block=1, to_block=2), ...)
    assert dead["deposits"] is None
    assert quiet["deposits"] == []
```

- [ ] Implement, routing `build_signals` through `safe_call` with a full-`None` default.
- [ ] Commit: `feat(curator): the readings seam with a constant outage encoding`

---

### Task WP5.12: `fetch_and_compute()` — the flat contract

**Steps:**

- [ ] Failing tests:

```python
def test_it_returns_exactly_curator_keys_always():
    for scenario in _EVERY_FAILURE_COMBINATION:
        out = asyncio.run(_manager(scenario).fetch_and_compute())
        assert set(out) == set(CURATOR_KEYS)


def test_no_exception_escapes_when_every_call_raises():
    out = asyncio.run(_manager_all_raising().fetch_and_compute())
    assert set(out) == set(CURATOR_KEYS)
    assert out["degraded"] == sorted(SOURCES)


def test_the_manager_divides_to_eth_exactly_once():
    """Models are wei-native; the dict is the presentation boundary. Two
    divisions is how a number becomes 1e-18 of itself, silently."""
    src = inspect.getsource(curator_manager)
    assert src.count("/ WEI") + src.count("/ 10**18") == _EXPECTED_DIVISION_SITES


def test_a_key_the_manager_invents_is_dropped_and_logged():
    """_finalise returns exactly CURATOR_KEYS -- the surf pattern."""
    ...


def test_the_blank_payload_distinguishes_dead_sources_from_empty_ones():
    """A None list means 'source dead'; [] means 'genuinely nothing'. On a
    blank payload the ROW keys stay None (we did not look) while the SERIES
    keys are [] (an empty history is a fact about this install, not about the
    network)."""
    blank = manager._blank_payload()
    for key in ("leaderboard_rows", "activity_rows", "closest_call_rows", "cluster_rows"):
        assert blank[key] is None
    for key in ("volume_series", "contributors_series"):
        assert blank[key] == []
    assert blank["degraded"] == []
```

- [ ] Implement.
- [ ] **Prove it bites:** seed `leaderboard_rows=[]` in `_blank_payload` → the last test FAILS
      (a dead Blockscout would assert the list is empty). Restore.
- [ ] Commit: `feat(curator): fetch_and_compute returns exactly CURATOR_KEYS, never raises`

---

### Task WP5.13: The degradation matrix

**Files:** `tests/data/test_curator_degradation.py`

Each row is a required test, driven end to end through a fake client.

| failure | dies | keeps working | rendered state |
|---|---|---|---|
| state pool down (all three endpoints) | phase truth, clock, `earlyBps`, forced ETH, YOU | leaderboard, series, activity, clusters, closest calls (all log-derived) | hero boxes `unavailable`; **if settlement was already observed the phase stays SETTLED** behind `as of HH:MM`; `degraded=["state"]` |
| logs pool down (tenderly + drpc) | leaderboard, series, activity, clusters, closest calls, `HourSaved` | the whole clock, phase, at-risk, forced ETH, YOU | last-good fold behind `as of HH:MM`, or the explicit unavailable state if never fetched; `degraded=["logs"]` |
| everything down | everything | nothing | full `CURATOR_KEYS` of `None`, `degraded=["logs","state","wallet"]`, no crash, no zero anywhere |
| **outage after settlement observed** | freshness | **the phase** | SETTLED, with the staleness marker moving and the phase word not |
| wallet read fails, chain healthy | YOU only | everything else | YOU row `unavailable`; `degraded=["wallet"]` |
| grace → judged crossing | nothing | everything | phase flips on the injected clock alone, with no refetch |
| settled with a `Settled` log absent | nothing | everything | SETTLED from the view; obituary fields `None`, not `0` |

**Steps:**

- [ ] Write all seven, driving the injected clock and the fake client — no sleeping.
- [ ] The fourth row is the flagship:

```python
def test_settlement_survives_a_total_outage():
    """PRD §11.3. Observe settled once, then kill every endpoint forever."""
    m = _manager(_client_settled_at(block=25_776_000), clock=_clock)
    first = asyncio.run(m.fetch_and_compute())
    assert first["phase"] == "settled"

    m._client = _client_all_dead()
    for tick in range(1, 6):
        _clock.advance(60)
        out = asyncio.run(m.fetch_and_compute())
        assert out["phase"] == "settled", f"phase lost on tick {tick}"
        assert out["settled"] is True
        assert "state" in out["degraded"]
        assert out["as_of_hhmm"] == first["as_of_hhmm"]   # freshness froze
    # ...and the freshness marker is what moved, not the verdict.
    assert out["settled_observed_at"] == first["settled_observed_at"]
```

- [ ] Run the whole WP, then the full suite.
- [ ] Write the WP6 hand-off note: `fetch_and_compute()`/`close()` signatures, the exact
      `SOURCES` strings the title bar will render, and the confirmation that the manager never
      raises — so WP6's `raises=True` double is labelled belt-and-braces, not the outage path.
- [ ] Commit: `test(curator): the seven-row degradation matrix, settlement latch included`

**Done when:** the flat contract holds under every failure combination, the two mandated
mutations in WP5.3 and WP5.4 were each watched go red and restored, and a settled contract
still reads SETTLED with every endpoint dead.
