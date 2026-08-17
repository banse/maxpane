# WP3 — `analytics/curator_signals.py` (pure math, strict TDD)

**Goal:** Every derived number on the screen — the phase machine, the curve, the folds, the
survival record, the cluster heuristic and the YOU quote — as pure functions with the clock
injected, tested against the committed events with integer-exact assertions.

**Dependencies:** WP0 (`curator_models` for `PHASES` and the row/dataclass shapes). Runs in
wave 2 in parallel with WP2 and WP4; shares no file with either.

**Owner note.** This WP owns and creates:

- `maxpane_dashboard/analytics/curator_signals.py`
- `tests/analytics/test_curator_signals.py`
- `tests/fixtures/curator/signals/` (its own slices)

It touches nothing else. **TDD is mandatory here**: the module is pure, deterministic and
fully specified by numbers already in the captures, so tests are written from the captures
*before* the implementation. **`pytest.approx` on a wei value is a review failure.**

### Ground rules

- **No I/O, no Textual, no `data/` client imports.** A test asserts the module's source
  contains no `httpx`/`asyncio`/`textual`/`requests` import and never calls `time.time()`.
  It may import `data/curator_models` for `PHASES` and the dataclasses; that is a stdlib-only
  module.
- **`now_ts` is a parameter, always.** Nothing here reads a clock.
- **Integer in, integer out.** Wei stays `int` through every fold; the manager divides once.
  Floats appear only where the PRD asks for one (`early_multiplier_x`, percentages).
- **Every function is total.** No division by `creditedDelta` (H3), no division by a count
  that can be zero, no `max()`/`min()` over a possibly-empty sequence without a default.
- Commit after each task.

---

### Task WP3.1: Module skeleton, purity, and the frozen output surface

**Interfaces:** produces `SIGNAL_OUTPUT_KEYS: tuple[str, ...]`, `READING_KEYS: tuple[str, ...]`,
and the named constants: `WHALE_MIN_ETH = 25.0`, `WHALE_WINDOW_S = 3600.0`,
`CLUSTER_MIN_SIZE = 3`, `CLUSTER_MAX_BLOCK_SPAN = 32`, `AT_RISK_RED_SECONDS = 900`,
`FIRED_TTL_S`. All PRD §12 "first guesses" are named constants with a comment saying so.

**Steps:**

- [x] Failing tests:

```python
def test_the_module_is_pure():
    src = inspect.getsource(curator_signals)
    for banned in ("import httpx", "import asyncio", "from textual",
                   "import requests", "time.time()", "datetime.now("):
        assert banned not in src, banned


def test_signal_output_keys_are_all_curator_keys():
    """The seam WP0.6 guards from the other side. Asserted here too, so a
    rename in either file fails in the file that made it."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS
    assert set(SIGNAL_OUTPUT_KEYS) <= set(CURATOR_KEYS)


def test_the_tunable_constants_are_named_and_documented_as_guesses():
    """PRD §12: WHALE and cluster thresholds are first guesses to be re-tuned
    against post-grace data. A magic number inline cannot be re-tuned as an
    amendment; it just gets edited."""
    assert WHALE_MIN_ETH == 25.0 and CLUSTER_MIN_SIZE == 3
    assert CLUSTER_MAX_BLOCK_SPAN == 32 and AT_RISK_RED_SECONDS == 900
    src = inspect.getsource(curator_signals)
    assert "first guess" in src.lower()
```

- [x] Implement the skeleton.
- [x] Commit: `feat(curator): analytics skeleton with the frozen signal surface`

---

### Task WP3.2: `derive_phase()` and the clock fields

**Interfaces:** produces
`derive_phase(*, now_ts, launch_time, grace_period, settled, current_hour) -> str` returning
one of `PHASES`, and the clock helpers `grace_seconds_left`, `grace_ends_utc`,
`lived_desc(launch_time, end_ts)`.

**Steps:**

- [x] Failing tests, calibrated on the pinned instants (WP0.7):

```python
LAUNCH = 1_786_910_327            # 2026-08-16 19:58:47Z
GRACE_END = LAUNCH + 86_400       # 2026-08-17 19:58:47Z
FIRST_JUDGED_COMPLETE = LAUNCH + 25 * 3600   # 2026-08-17 20:58:47Z


@pytest.mark.parametrize("now,settled,expected", [
    (LAUNCH,                 False, "grace"),
    (GRACE_END - 1,          False, "grace"),
    (GRACE_END,              False, "judged"),   # the boundary belongs to judged
    (GRACE_END + 1,          False, "judged"),
    (FIRST_JUDGED_COMPLETE,  True,  "settled"),
    (LAUNCH + 60,            True,  "settled"),  # settled always wins
])
def test_the_phase_machine(now, settled, expected):
    assert derive_phase(now_ts=now, launch_time=LAUNCH, grace_period=86_400,
                        settled=settled, current_hour=(now - LAUNCH)//3600) == expected


def test_settled_wins_over_every_other_input():
    """SETTLED is terminal and one-way: the contract enforces it. No clock
    value, no missing field and no later reading may take the screen back to a
    live phase."""
    assert derive_phase(now_ts=LAUNCH, launch_time=LAUNCH, grace_period=86_400,
                        settled=True, current_hour=0) == "settled"


def test_an_unknown_settled_flag_does_not_invent_a_phase():
    """settled=None means the read failed. Guessing 'judged' from the clock
    would render a live game on a possibly-dead contract -- the exact hazard
    the PRD names. The answer is None and the hero renders unavailable."""
    assert derive_phase(now_ts=GRACE_END + 60, launch_time=LAUNCH,
                        grace_period=86_400, settled=None,
                        current_hour=24) is None


def test_grace_seconds_left_never_goes_negative():
    assert grace_seconds_left(now_ts=GRACE_END + 5_000, launch_time=LAUNCH,
                              grace_period=86_400) == 0


def test_grace_ends_utc_is_the_absolute_instant_the_hero_prints():
    assert grace_ends_utc(LAUNCH, 86_400) == "2026-08-17 19:58:47 UTC"
```

- [x] Implement.
- [x] **Prove it bites:** make `derive_phase` fall back to `"judged"` when `settled is None` →
      `test_an_unknown_settled_flag_does_not_invent_a_phase` FAILS. Restore.
- [x] Commit: `feat(curator): phase machine with a settled-wins, unknown-is-None contract`

---

### Task WP3.3: The curve — integer sqrt with the contract's exact floor (H7)

**Interfaces:** produces `points_for_weight(weight_wei: int, points_per_eth: int) -> int`.

**The formula, from `source.sol`:**
`_curve(w) = (_sqrt(w) * POINTS_PER_ETH) / 1e9`, i.e.
`points = (isqrt(w) * points_per_eth) // 10**9`. **Multiplication before division** — the
other order loses the low digits of every non-round weight.

**Steps:**

- [x] Write `_contract_sqrt(a)` **in the test file**: a literal transcription of the contract's
      seeded Newton loop, including `result = 1 << (log2(a) >> 1)`, exactly seven iterations,
      and the final `return result if result <= a // result else result - 1`. This is the
      witness. It lives in the test, never in production.
- [x] Failing tests:

```python
def test_the_production_sqrt_matches_the_contract_over_the_edges():
    edges = [0, 1, 2, 3, 4, 8, 10**9 - 1, 10**9, 10**9 + 1, 10**18,
             4 * 10**18, 100 * 10**18, 1000 * 10**18, 2000 * 10**18,
             (1 << 96) - 1, (1 << 96)]
    for w in edges:
        assert math.isqrt(w) == _contract_sqrt(w), w


def test_the_production_sqrt_matches_the_contract_over_a_random_corpus():
    """10 000 draws across the whole reachable weight range (0 .. 2000 ETH,
    the hard ceiling: creditCap 1000 ETH x the 2x maximum multiplier).
    Seeded, so a failure is reproducible."""
    rng = random.Random(20260816)
    for _ in range(10_000):
        w = rng.randrange(0, 2000 * 10**18)
        assert math.isqrt(w) == _contract_sqrt(w), w


def test_the_documented_curve_points():
    """The mechanics doc's table, recomputed rather than trusted."""
    assert points_for_weight(1 * 10**18, 1000) == 1_000
    assert points_for_weight(4 * 10**18, 1000) == 2_000
    assert points_for_weight(100 * 10**18, 1000) == 10_000
    assert points_for_weight(1000 * 10**18, 1000) == 31_622
    assert points_for_weight(2000 * 10**18, 1000) == 44_721
    assert points_for_weight(0, 1000) == 0


def test_the_multiplication_happens_before_the_division():
    """(isqrt(w) * 1000) // 1e9 is not ((isqrt(w) // 1e9) * 1000).

    The wrong order returns 0 for every weight below 1e18 -- i.e. for the 53
    wallets sitting at the 0.05 ETH minimum, which is a third of the list.
    """
    w = 999_999_999 ** 2      # isqrt == 999_999_999, just under 1e9
    assert points_for_weight(w, 1000) == 999
    assert (math.isqrt(w) // 10**9) * 1000 == 0


def test_points_per_eth_is_a_parameter_not_a_literal():
    """CLAUDE.md rule 4: it is a contract constant, read on the `once` tier."""
    assert points_for_weight(10**18, 500) == 500
    assert "1000" not in inspect.getsource(points_for_weight)
```

- [x] Implement with `math.isqrt`.
- [x] **Mandated prove-it-bites #3 (PRD §8, the curve floor):**
      1. Change the production body's `//` to `round(... / ...)` →
         `test_the_documented_curve_points` FAILS at `1000 * 10**18` (31622 → 31623). Restore.
      2. Change `math.isqrt(w)` to `int(math.sqrt(w))` → the randomized differential FAILS
         (float64 has 53 bits of mantissa; weights above ~9e15 wei land on the wrong side of
         an integer boundary often enough that 10 000 draws find it). Restore.
      3. Swap the operand order to `(math.isqrt(w) // 10**9) * points_per_eth` →
         `test_the_multiplication_happens_before_the_division` FAILS. Restore.
      Record all three in the WP3 sign-off note; WP7.12 audits them.
- [x] **When WP1.6's curve probe lands**, add `test_the_curve_matches_previewPoints_on_chain`
      against the captured returns and mark it as the onchain witness. Until then, this task's
      commit message must say "validated by transcription", not "validated against chain".
      Mark the placeholder `# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`.
- [x] Commit: `feat(curator): integer sqrt curve floored exactly like the contract`

---

### Task WP3.4: The weight formula (H8)

**Interfaces:** produces `weight_added(credited_delta_wei: int, early_bps: int) -> int`
= `credited_delta_wei * early_bps // 10_000`.

**Steps:**

- [x] Failing tests:

```python
def test_the_captured_first_deposit_to_the_wei():
    """0.05 ETH at 19 975 bps -> 0.099875 ETH of weight. `==`, never approx."""
    assert weight_added(5 * 10**16, 19_975) == 99_875_000_000_000_000


def test_every_captured_deposit_satisfies_the_identity():
    """All 226 rows from tenderly_logs.json. This is the differential that
    makes the formula a fact rather than a reading of the source."""
    for ev in _captured_deposits():
        assert weight_added(ev.credited_delta_wei, ev.early_bps) == ev.weight_added_wei


def test_the_division_floors():
    assert weight_added(1, 19_999) == 1          # 1.9999 -> 1
    assert weight_added(1, 9_999) == 0           # 0.9999 -> 0, a real zero
    assert weight_added(3, 10_001) == 3          # 3.0003 -> 3


def test_a_zero_credited_delta_yields_zero_weight_and_does_not_raise():
    """H3: legal, and common once anyone crosses the cap."""
    assert weight_added(0, 20_000) == 0
```

- [x] Implement.
- [x] **Mandated prove-it-bites (PRD §8's third mutation, correctly aimed — see the index
      plan's amendment 3):** change `//` to `round(a * b / 10_000)` →
      `test_the_division_floors` FAILS at `weight_added(1, 19_999)` and the 226-row
      differential FAILS on the first non-exact row. Restore.
- [x] Commit: `feat(curator): weight formula, floored, differential-tested on 226 events`

---

### Task WP3.5: `credited_delta()` and the cap case (H3)

**Interfaces:** produces
`credited_delta(amount_wei: int, old_high_water_wei: int, credit_cap_wei: int) -> int`.

**Steps:**

- [x] Failing tests: the source's exact semantics —
      `min(amount, cap) - min(old, cap)`, floored at 0; a first deposit credits its whole
      amount; an escalation credits only the increment; **an amount above the cap credits
      zero when the old high-water is already at the cap**; the telescoping identity (a ladder
      of escalations sums to `min(final, cap)`), asserted over the real 13-deposit grinder
      ladder in the captures.
- [x] The cap fixture is **synthetic by necessity** — the largest real send is 461.1 ETH
      against a 1000 ETH cap (WP0.7 pins that). Mark it
      `# SYNTHETIC — permanent: no >1000 ETH deposit exists on chain` and give it its own test
      asserting the *pair* of consequences: zero weight **and** full hourly volume credit.
- [x] Add the guardrail:

```python
def test_nothing_in_this_module_divides_by_credited_delta():
    """H3. ``weight is proportional to volume`` is false on this contract, and
    the tempting normalisation is a ZeroDivisionError waiting for the first
    whale."""
    src = inspect.getsource(curator_signals)
    assert "/ credited" not in src and "// credited" not in src
    assert "/ delta" not in src and "// delta" not in src
```

- [x] Commit: `feat(curator): cap-aware credited delta with the zero-delta case`

---

### Task WP3.6: `fold_deposits()` — the contributor table

**Interfaces:** produces
`fold_deposits(deposits, first_deposits, *, points_per_eth) -> list[ContributorRow]`, sorted
by points descending, ties broken by weight then by first-deposit index (deterministic).

**Steps:**

- [x] Failing tests:

```python
def test_the_fold_uses_the_events_running_totals_not_a_re_derivation():
    """``Deposited`` carries ``newWeight`` and ``txCount`` -- the contract's own
    running totals. Summing ``weightAdded`` instead would drift the moment one
    log is missed, and a missed log is what the gap-repair tier exists for."""
    rows = fold_deposits(_captured_deposits(), _captured_first_deposits(),
                         points_per_eth=1000)
    for row in rows:
        last = _last_event_for(row.address)
        assert row.weight_wei == last.new_weight_wei
        assert row.tx_count == last.tx_count


def test_credit_telescopes_to_the_final_high_water():
    """PRD/mechanics: lifetime credit == min(final high-water, cap), and
    ``amount`` IS the new high-water by construction."""
    for row in rows:
        assert row.credit_wei == _last_event_for(row.address).amount_wei


def test_the_fold_reproduces_the_captured_leaderboard():
    """Rank 1: 0x381fe486..., credit 461.1 ETH, weight 902.1, ~30 035 points.
    Recomputed from the events, then compared to the research's reading."""
    assert rows[0].credit_wei == 461_100_000_000_000_000_000
    assert 30_000 <= rows[0].points <= 30_100


def test_the_fold_matches_the_contracts_own_counters():
    """143 contributors and 222 txs in the batch round; the sweep caught 145
    and 226, because it was pulled two minutes later. The fold must equal the
    SWEEP, and the difference from the batch must be exactly the extra rows --
    not hand-waved."""
    assert len(rows) == 145
    assert sum(r.tx_count for r in rows) == 226


def test_first_index_is_one_based_and_dense():
    assert sorted(r.first_index for r in rows) == list(range(1, 146))


def test_the_fold_is_deterministic_under_input_reordering():
    shuffled = random.Random(7).sample(_captured_deposits(), k=226)
    assert fold_deposits(shuffled, ..., points_per_eth=1000) == rows


def test_an_empty_history_folds_to_an_empty_list_not_a_crash():
    assert fold_deposits([], [], points_per_eth=1000) == []
```

- [x] Implement.
- [x] Commit: `feat(curator): fold the contributor table from the events' running totals`

---

### Task WP3.7: `hourly_buckets()` — the series that never touches state (H2)

**Interfaces:** produces `hourly_buckets(deposits, *, launch_time, hour_duration,
first_judged_hour, hourly_threshold_wei) -> list[HourBucket]`, dense from hour 0 to the
highest observed hour (**silent hours are present with `volume_wei=0`** — a missing hour and a
silent hour are different facts, and a silent judged hour is what kills the game), and
`bucket_start_ts(hour, launch_time, hour_duration) -> int`.

**Steps:**

- [x] Failing tests:

```python
def test_the_hour_comes_from_the_indexed_topic_not_from_a_timestamp():
    """No deposit event carries a timestamp and tenderly returns no
    blockTimestamp (WP0.7 pins both). The hour is topics[2]; the wall-clock is
    launch_time + hour*hour_duration, exact by construction."""
    buckets = hourly_buckets(_captured_deposits(), launch_time=LAUNCH,
                             hour_duration=3600, first_judged_hour=24,
                             hourly_threshold_wei=5 * 10**18)
    assert bucket_start_ts(1, LAUNCH, 3600) == LAUNCH + 3600
    assert {b.hour for b in buckets} == {0, 1}


def test_the_function_signature_admits_no_state_reading():
    """H2, made structural. ``currentHourTotal`` cannot enter this fold because
    there is no parameter for it to enter through, and the source names none."""
    params = set(inspect.signature(hourly_buckets).parameters)
    assert params == {"deposits", "launch_time", "hour_duration",
                      "first_judged_hour", "hourly_threshold_wei"}
    src = inspect.getsource(hourly_buckets)
    for banned in ("current_hour_total", "currentHourTotal", "last_active_hour"):
        assert banned not in src


def test_silent_hours_are_present_with_a_zero_not_absent():
    """A gap in the series renders as a join between two peaks; a zero renders
    as the silence that kills the game."""
    sparse = [_dep(hour=0, wei=10**18), _dep(hour=3, wei=10**18)]
    hours = [b.hour for b in hourly_buckets(sparse, ...)]
    assert hours == [0, 1, 2, 3]
    assert [b.volume_wei for b in hourly_buckets(sparse, ...)] == [10**18, 0, 0, 10**18]


def test_only_hours_at_or_after_first_judged_hour_are_marked_judged():
    assert all(b.judged is False for b in buckets if b.hour < 24)


def test_the_captured_hours_reproduce_the_research_reading():
    """Hour 0 quiet then violent; hour 1 the peak. Recomputed, not quoted."""
    assert buckets[1].volume_wei == 0x27D2C90DCE228AE5B0
    assert sum(b.volume_wei for b in buckets) == 0x560119983627C22D4F  # == totalVolume
```

- [x] Implement.
- [x] **Mandated prove-it-bites #2 (PRD §8, the hour-boundary rule) — part one.** The
      structural half lives here: add a `current_hour_total_wei` parameter and let the last
      bucket take it → `test_the_function_signature_admits_no_state_reading` FAILS. Restore.
      The behavioural half (a boundary fixture writing a zero into the persisted series) is
      WP5.3's, because the writing happens in the cache.
- [x] Commit: `feat(curator): hourly buckets folded from the indexed hour topic alone`

---

### Task WP3.8: Survival — judged hours, streak, closest call (H13)

**Interfaces:** produces
`survival(buckets, *, current_hour, hourly_threshold_wei) -> dict` with
`streak_hours`, `closest_call_hour`, `closest_call_margin_wei`, `closest_calls`
(list of `(hour, volume_wei, margin_wei, savior)` ascending by margin).

**Steps:**

- [x] Failing tests:

```python
def test_the_in_progress_hour_is_never_judged():
    """H13, straight from _isShort: `from > hour - 1` returns false, so the
    hour you are living in cannot kill you. Judging it would settle the game
    every single hour, three seconds after the boundary."""
    s = survival(buckets_through(hour=30, last_is_empty=True),
                 current_hour=30, hourly_threshold_wei=5 * 10**18)
    assert 30 not in [h for h, *_ in s["closest_calls"]]


def test_the_hour_that_just_completed_becomes_judgeable_at_the_boundary():
    before = survival(b, current_hour=29, hourly_threshold_wei=T)
    after = survival(b, current_hour=30, hourly_threshold_wei=T)
    assert 29 not in _hours(before) and 29 in _hours(after)


def test_no_judged_hours_yet_is_an_explicit_state_not_an_empty_number():
    """During grace there is nothing to survive. The margin is None, not 0 --
    a 0 margin reads as 'we scraped through by nothing', which is a lie in the
    most alarming possible direction."""
    s = survival(_captured_buckets(), current_hour=1, hourly_threshold_wei=T)
    assert s["streak_hours"] == 0
    assert s["closest_call_hour"] is None
    assert s["closest_call_margin_wei"] is None
    assert s["closest_calls"] == []


def test_the_margin_is_volume_minus_threshold_and_can_be_exactly_zero():
    """A judged hour that took in exactly 5 ETH survived by exactly nothing.
    That is the tightest possible real call and must render as 0.00, not None."""
    ...


def test_the_streak_counts_consecutive_survived_judged_hours():
    ...
```

- [x] Implement.
- [x] Commit: `feat(curator): survival streak and closest-call fold over judged hours`

---

### Task WP3.9: HOUR AT RISK

**Interfaces:** produces
`at_risk_state(*, phase, needed_wei, seconds_left, first_judged_hour) -> tuple[str, str]`
returning `(state, detail)` where state ∈ `{"ok", "watch", "fired", None}`.

**Steps:**

- [x] Failing tests: in `grace`, always `("ok", "n/a until hour 24")` — never blank, and the
      hour number comes from `first_judged_hour`, never a literal 24; in `judged` with
      `needed_wei == 0` → `ok`; `needed_wei > 0` and `seconds_left >= 900` → `watch`
      ("hour needs X ETH"); `needed_wei > 0` and `seconds_left < 900` → `fired`;
      `needed_wei is None` → `(None, …)` and **never** `watch` — a failed read must not light
      an alarm; in `settled` → an explicit terminal state, not `ok`.
- [x] Implement.
- [x] **Prove it bites:** treat `needed_wei is None` as `> 0` →
      the failed-read test FAILS. Restore. (This is the "a dead RPC screams that the game is
      dying" bug.)
- [x] Commit: `feat(curator): HOUR AT RISK with a None-never-alarms contract`

---

### Task WP3.10: The cluster heuristic v1

**Interfaces:** produces `find_clusters(deposits, contributors, *, min_size=CLUSTER_MIN_SIZE,
max_block_span=CLUSTER_MAX_BLOCK_SPAN) -> list[dict]` matching `CURATOR_ROW_KEYS["cluster_rows"]`.

**Rule (PRD §5):** among **single-deposit** wallets, groups of ≥ 3 with **byte-identical**
amounts whose blocks span ≤ 32. Rendered as `⚑` "fan-out pattern" — **pattern language only,
never accusation.**

**Steps:**

- [x] Failing tests:

```python
def test_the_real_fan_out_is_found():
    """9 wallets, exactly 60 ETH each, blocks 25 770 115-25 770 143 (span 28).
    The contract's own doc comment predicts this shape; this is it in the data."""
    clusters = find_clusters(_captured_deposits(), _captured_contributors())
    sixty = [c for c in clusters if c["amount_eth"] == 60.0]
    assert len(sixty) == 1 and sixty[0]["size"] == 9
    assert sixty[0]["first_block"] == 25_770_115
    assert sixty[0]["last_block"] == 25_770_143


def test_the_grinder_is_not_a_cluster():
    """0xba7610... has 13 deposits. Multi-deposit wallets are excluded by
    construction: escalating against yourself is the opposite of fanning out."""
    assert not any("0xba7610" in a.lower()
                   for c in clusters for a in c.get("addresses", []))


def test_the_53_minimum_deposits_are_not_one_giant_cluster():
    """53 wallets sat at the 0.05 ETH minimum. They are identical in amount and
    would form a 53-wallet 'cluster' without the block-span bound -- which
    would flag a third of the list and mean nothing."""
    minimums = [c for c in clusters if c["amount_eth"] == 0.05]
    assert all(c["size"] < 20 for c in minimums)
    assert all(c["last_block"] - c["first_block"] <= 32 for c in clusters)


def test_amounts_are_compared_in_wei_not_in_eth_floats():
    """Two deposits of 0.1 + 0.2 ETH-as-float are 'equal' after rounding and
    are not equal on chain. The grouping key is the integer."""
    src = inspect.getsource(find_clusters)
    assert "amount_eth" not in src.split("return")[0]


def test_the_output_carries_no_accusatory_vocabulary():
    """PRD §5: pattern language only. The contract's own docs delegate sybil
    analysis to consumers; calling a wallet a sybil is a claim this data
    cannot support."""
    blob = json.dumps(clusters).lower() + inspect.getsource(curator_signals).lower()
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "farmer"):
        assert word not in blob


def test_a_cluster_of_exactly_three_is_found_and_of_two_is_not():
    ...
```

- [x] Implement. Group on `(amount_wei,)` over single-deposit wallets, then split each group
      into maximal runs whose block span is ≤ 32.
- [x] Commit: `feat(curator): fan-out cluster heuristic with pattern-only language`

---

### Task WP3.11: WHALE and the YOU quote

**Interfaces:** produces `newest_whale(deposits, *, now_ts, min_eth, window_s)` and
`you_quote(wallet_state, rows, *, points_per_eth, early_bps, credit_cap_wei)` returning
`(rank, points, credit_eth, required_next_eth, marginal_points)`.

**Steps:**

- [x] Failing tests:
      - whale: the largest single deposit inside the window and ≥ 25 ETH; nothing when the
        window is empty (`None`, not 0); a deposit with `ts is None` (WP2.8's failed stamp) is
        **excluded from the window** rather than treated as now — a missing timestamp must not
        promote an old deposit into the last hour;
      - YOU rank: derived from the folded rows; an address not on the list gets `rank=None`
        and `points=0`? **No** — `points=None` and an explicit "not on the list yet" detail.
        Assert that: a stranger's row must not render as "rank —, 0 pts", which reads like a
        wallet with zero score rather than one that has never played;
      - `marginal_points`: `points_for_weight(weight + weight_added(credited_delta(required_next,
        high_water, cap), early_bps)) - points`, i.e. what the *next legal send* buys. Asserted
        against a hand-computed case and against a wallet already at the cap (marginal = 0,
        legitimately);
      - every YOU field is `None` when `MAXPANE_WALLET` is unset — the manager passes
        `wallet_state=None` and the function must not raise.
- [x] Implement.
- [x] Commit: `feat(curator): whale detection and the YOU marginal-points quote`

---

### Task WP3.12: `build_signals()` and the `READING_KEYS` seam

**Interfaces:** produces `build_signals(readings: dict, *, now_ts: float) -> dict` emitting
**exactly** `SIGNAL_OUTPUT_KEYS`.

**Steps:**

- [x] Failing tests:

```python
def test_build_signals_emits_exactly_the_frozen_surface():
    out = build_signals(_full_readings(), now_ts=NOW)
    assert set(out) == set(SIGNAL_OUTPUT_KEYS)


def test_build_signals_accepts_exactly_the_frozen_readings():
    """The seam WP5 produces. Both directions, so neither side can drift:
    a reading WP5 stops sending, and a reading this module stops reading."""
    assert set(_full_readings()) == set(READING_KEYS)


def test_none_and_empty_mean_different_things_and_both_are_handled():
    """None == the read failed; [] / () == the read succeeded and found
    nothing. HOUR AT RISK and SETTLED both hinge on it: an empty judged-hour
    list means 'nothing judged yet' and a None means 'we could not look'."""
    empty = build_signals({**_full_readings(), "judged_buckets": []}, now_ts=NOW)
    failed = build_signals({**_full_readings(), "judged_buckets": None}, now_ts=NOW)
    assert empty["sig_at_risk_state"] == "ok"
    assert failed["sig_at_risk_state"] is None


def test_an_all_none_readings_dict_produces_the_full_surface_of_nones():
    out = build_signals({k: None for k in READING_KEYS}, now_ts=NOW)
    assert set(out) == set(SIGNAL_OUTPUT_KEYS)
    assert all(v is None or v == [] for v in out.values())


def test_build_signals_never_raises_on_hostile_input():
    for bad in ({}, {k: object() for k in READING_KEYS},
                {**_full_readings(), "current_hour": -1}):
        assert set(build_signals(bad, now_ts=NOW)) == set(SIGNAL_OUTPUT_KEYS)
```

- [x] Implement, routing each sub-fold through its own small helper so a failure in one
      degrades one key (the manager wraps the whole call in `data/safe_call.safe_call`, but
      losing seven rows because the cluster fold hiccuped is still wrong).
- [x] Run the whole file and the full suite.
- [x] Write the WP5 hand-off note: `READING_KEYS` verbatim, with each key's outage encoding.
- [x] Commit: `feat(curator): build_signals over the frozen readings seam`

**Done when:** every fold is tested against the 226 captured events with `==`, the three
mutations in WP3.3/WP3.4/WP3.7 were each watched go red, and `READING_KEYS` is pinned on this
side of the seam.


---

## Sign-off — WP3 landed 2026-08-17

All twelve tasks, strict TDD, tests written from the committed captures before
the implementation. **132 tests** in `tests/analytics/test_curator_signals.py`;
the full suite is green (3978 passed at the time of the WP3.12 commit).

### The mandated prove-it-bites (WP7.12 audits these)

| # | mutation | what went red |
|---|---|---|
| WP3.2 | `derive_phase` falls back to `"judged"` when `settled is None` | `test_an_unknown_settled_flag_does_not_invent_a_phase` **and** `test_every_phase_it_can_return_is_one_of_the_three_frozen_spellings` |
| WP3.3 #1 | curve `//` → `round(... / ...)` | `test_the_documented_curve_points` (31 622 → 31 623), the onchain `previewPoints` witness, and `test_the_multiplication_happens_before_the_division` |
| WP3.3 #2 | `math.isqrt` → `int(math.sqrt(...))` | `test_the_production_curve_survives_weights_a_float_sqrt_would_round_wrong` |
| WP3.3 #3 | operand order → `(isqrt(w) // 1e9) * ppe` | `test_the_multiplication_happens_before_the_division` + both onchain witnesses |
| WP3.4 | weight `//` → `round(a * b / 10_000)` | `test_the_division_floors` and the 3161-row differential |
| WP3.6 | drop the `(block_number, log_index)` sort | `test_the_fold_is_deterministic_under_input_reordering` |
| WP3.7 | add a `current_hour_total_wei` parameter and let the last bucket take it | `test_the_function_signature_admits_no_state_reading` |
| WP3.9 | treat `needed_wei is None` as a deficit | `test_a_failed_read_is_unknown_and_never_lights_an_alarm` |
| WP0 deferred | rename one `SIGNAL_OUTPUT_KEYS` entry (`top_points` → `top_pointz`) | `tests/data/test_curator_models.py::test_signal_output_keys_are_a_subset_of_curator_keys` — it flipped SKIPPED → PASSED when the module landed, and FAILS naming the key. The guard is live. |

**WP3.3 #2 did not bite as written and had to be re-aimed.** The task's
randomized differential compares `math.isqrt` to the test's transcription — two
things that are both outside the module under test — so a float `sqrt` in
production sailed straight past it. Worse, the WP's premise is wrong: over
0..2000 ETH the float mismatch rate is **under 1 in 200 000**, and the curve's
`// 1e9` absorbs almost every mismatch that does occur (a ±1 wei error in the
root only moves a point when the root is a multiple of 10^6). The differential
now runs *through* `points_for_weight`, and four chosen witnesses are pinned by
value — `(k * 10**6)**2 - 1` for k = 224, 10 000, 31 622, 44 721, one per decade
of the reachable range.

### Numbers that came from the captures, not from this file

`wp3.md`'s hex literals for the hourly fold (`0x27D2C90DCE228AE5B0`,
`0x560119983627C22D4F`) and its `226` / `len(rows) == 145, sum == 226` counters
belong to an earlier, 226-row reading of the sweep. Recomputed from the
committed bytes: **231** deposits, 145 contributors, hour 0 =
851.887546893889652639 ETH, hour 1 = 778.611705271950173616 ETH, total
1630.499252165839826255 ETH. The bundle
`captures/live/20260817T000322Z_grace-late.json` reconciles wei-exact against
the contract's own counters in a single instant (2291 contributors, 2930
deposits, 15 981.146536110048548095 ETH, and the fold reproduces
`currentHourTotal()` for the in-progress hour).

The curve now has its onchain witness: `previewPoints()` over 12 weights and
`pointsOf`/`weightOf` over 4 real wallets, all 20 answered, all equal to
`(isqrt(w) * 1000) // 10**9` — and the fold's weight for those 4 wallets equals
`weightOf()` to the wei.

### Deviations from this file, and why

1. **`survival()` takes an optional `first_judged_hour=`.** Without it the fold
   cannot tell a silent judged hour from an hour outside the judged window, and
   the silent hours past the last deposit are exactly the ones that kill the
   contract. The signature in this file still works; the keyword is additive.
2. **`find_clusters` does not expose member addresses** (this file's
   `test_the_grinder_is_not_a_cluster` reads `c["addresses"]`). `cluster_rows`
   is a frozen row shape and adding a column is a contract change. Membership is
   its own function, `cluster_members()`, and both read one grouping
   (`_cluster_runs`) so the leaderboard's `flagged` column and the cluster table
   can never disagree on screen.
3. **WP3.12's `judged_buckets` reading does not exist.** `sig_at_risk_state`
   hinges on `hour_needed_wei`, not on a bucket list, so the None-vs-empty test
   is written against the reading that actually decides it — plus a second test
   pinning None-vs-empty on `deposits`.
4. **The H12 countdown formatter lives in WP4, not here.** No flat-dict key
   carries a countdown *string*, and widgets may not import `analytics/`, so a
   formatter here would be dead code. This module passes `hour_seconds_left`
   through untouched and `at_risk_state` is tested at 3600, 900, 899 and 1.
   **WP4 owns the format and must render 3600 as `60:00`, never `00:00`.**
5. **`at_risk_state`'s `detail` does not cross the flat-dict boundary** — there
   is no `sig_at_risk_detail` key. The state does; WP4 composes the row text
   from `hour_needed_eth` / `hour_seconds_left` / `first_judged_hour`.

### Still synthetic (`rg "SYNTHETIC — re-point"`)

`tests/fixtures/curator/signals/readings_judged_deficit.json` (capture B) and
`readings_settled.json` (capture C), plus the marked comments in the test file
for the flat post-grace multiplier, the deficit states and the settled state.
The cap-exceeding deposit is marked **permanently** synthetic: the largest real
send is 461.1 ETH against a 1000 ETH cap.
