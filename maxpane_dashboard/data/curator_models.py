"""Frozen interface for the curator dashboard — THE LIST.

Boundaries only: this module imports nothing but the standard library.  No
client, no cache, no analytics, no Textual.  Every other curator module codes
against what is declared here, and four of them are written in parallel by
agents that never speak to each other — so a field named wrong in this file is
discovered a wave later, at the cost of the wave.

Unit discipline
    **Models are wei-native; the flat dict is the presentation boundary.**
    ``*_wei`` fields are ``int``; ``CuratorManager`` divides exactly once when
    it builds the flat dict, which is why the dict carries ``hour_fed_eth`` /
    ``volume_routed_eth`` while the models carry ``current_hour_total_wei`` /
    ``volume_wei``.  ``test_no_wei_key_leaks_into_the_flat_dict`` and
    ``test_no_eth_denominated_field_reaches_a_model`` pin both directions.

Naming discipline
    **Model fields mirror the chain; flat-dict keys mirror the PRD.**  The
    getter is ``isSettled()`` so the field is ``settled``; the hero key is
    ``phase``.  ``ethNeededThisHour()`` is ``hour_needed_wei`` on the model and
    ``hour_needed_eth`` in the dict.  The mapping table lives in
    ``curator_manager``; nothing here is renamed to match a widget, and
    ``test_no_flat_dict_key_masquerades_as_a_model_field`` forbids the
    confusion.

Raw discipline
    **The client returns what it read; interpretation is pure-function work.**
    :class:`DepositEvent` carries the nine decoded event words and nothing
    derived — ``points``, ``margin`` and cluster membership are all
    ``analytics/curator_signals``'s, which is what gives those functions exactly
    one caller and one test suite each.  :class:`LogSweep` carries raw log rows
    for the same reason.

Outage discipline
    **A failed read is ``None``, never ``0``.**  Every field a read can fail to
    produce is ``… | None``.  Nothing here defaults to ``0``: a zero written
    into a persisted series outlives the outage that produced it, and no
    consumer can tell it from a real measurement afterwards.

The three legitimate zeros
    This contract makes that rule unusually load-bearing, because it has zeros
    that are *answers*:

    * ``currentHourTotal()`` is ``0`` at every hour boundary, for as long as it
      takes the next deposit to land — while ``lastActiveHour()`` still names
      the previous bucket.  A sparkline fed from this view reads the boundary as
      a 99.5% crash (it did: 9987.26 → 51.48 ETH across 2026-08-16 21:58:47 UTC,
      captured in ``hour_boundary_h1_h2.json``).  History is folded from
      ``Deposited`` logs only; the fast tier never writes into a series.
    * ``ethNeededThisHour()`` is ``0`` through the entire grace period and again
      whenever a judged hour is already safe.  A ``None`` here must never light
      the HOUR AT RISK state, and a ``0`` must never be rendered as unknown.
    * ``creditedDelta`` is ``0`` for a deposit above the 1000 ETH cap, which
      still counts *fully* toward hourly survival.  Nothing may divide by it.

Why ``has_joined`` is its own field
    ``contributors(address)`` packs ``firstHour + 1`` into a ``uint32`` so that
    ``0`` can mean "never deposited".  ``firstHourOf(address)`` un-shifts it and
    returns **two** words, ``(hour, hasJoined)``.  ``(0, false)`` is a stranger
    and ``(0, true)`` is someone who deposited in the launch hour; one field
    cannot carry both, and a scalar decode of that view renders every stranger
    as a founder.  ``lastActiveHour()`` is two words for the same reason —
    ``(hour, total)`` — and ``stats()`` is three.

Nothing in this module is read-write.  ``deposit()``, ``settle()`` and
``rescue()`` are read *about*, never called.
"""

from __future__ import annotations

from dataclasses import dataclass

# ===========================================================================
# WP0 HAND-OFF — what wave 2 codes against (frozen 2026-08-17)
# ===========================================================================
#
# Frozen names, all importable and all pinned by a test on both sides:
#
#   this module ................ PHASES, SIGNAL_ROWS, CURATOR_KEYS,
#                                CURATOR_ROW_KEYS, CURATOR_SERIES_KEYS,
#                                CURATOR_ACTIVITY_KINDS, CURATOR_SIGNAL_STATES,
#                                CURATOR_DEGRADED_GROUPS, and the
#                                eight dataclasses: CuratorState, CuratorConfig,
#                                WalletState, DepositEvent, LogSweep,
#                                ContributorRow, HourBucket, SettlementRecord
#   tests/data/test_curator_models.py ..... CONSTRUCTOR_KWARGS (import it and
#                                assert the kwargs YOUR code passes)
#   data/curator_addresses.py .. CURATOR / DEPLOYER / ANNOUNCE / ZERO_ADDRESS,
#                                CREATION_TX / CREATION_BLOCK / LAUNCH_TIME,
#                                LABELED_ADDRESSES / KNOWN_LABELS,
#                                the six TOPIC_* + TOPIC_PREIMAGES,
#                                the 28 SEL_* + SELECTOR_PREIMAGES +
#                                VIEW_RETURN_WORDS + VIEW_RETURN_TYPES, and the
#                                four ordered tuples FAST_/ONCE_/CROSS_CHECK_/
#                                WALLET_VIEW_SELECTORS
#   tests/curator_fixtures.py .. CAPTURES / LIVE / capture() / capture_text() /
#                                live_bundles()
#
# Two bite-proofs are DEFERRED and belong to whoever lands the code:
#   1. test_signal_output_keys_are_a_subset_of_curator_keys currently SKIPS.
#      The day analytics/curator_signals.py exists, rename one entry of
#      SIGNAL_OUTPUT_KEYS, run `-k subset -v` -> it must FAIL naming the key;
#      restore -> green, NOT skipped.  If it still skips, importorskip's path is
#      wrong and the guard has been dead the whole time.
#   2. The ordered selector tuples' ORDER is not tested here on purpose —
#      swapping two entries leaves the WP0 suite green.  WP2.4 owns that test,
#      asserted against VIEW_RETURN_WORDS.
#
# ---------------------------------------------------------------------------
# AMENDED 2026-08-17 after review.  Five things moved AFTER the first freeze;
# if you read the briefs before this date, read these five instead:
#
#   1. CURATOR_KEYS GAINED `hourly_threshold_eth` and `first_judged_hour`.
#      Both are chain values two widgets are specified to RENDER, and neither
#      existed on any frozen surface — so wp4.md:412's `_SCREEN_SUPPLIED` was
#      about to make a widget hardcode "5.00" and "24".  wp4/wp6 owners:
#      `_SCREEN_SUPPLIED` is now exactly `{you_address}` (a CLI value, the one
#      legitimate non-chain kwarg); drop the other two from it and dispatch them
#      from the payload like every other key.  The manager divides
#      CuratorConfig.hourly_threshold_wei once; first_judged_hour passes
#      straight through.
#   2. SIGNAL_ROWS's seventh row is `you`, not `rescued`.  PRD §4, wp4.md:231
#      and wp6.md:300 all end the rail in YOU and none of them has a RESCUED
#      row; `rescued_total_eth` renders inside FORCED ETH.
#   3. `you_credit_eth` STAYS in CURATOR_KEYS (PRD §5 names it) but reaches no
#      widget in wp6.md:31's kwarg table, so WP6.1's totality assertion
#      (CURATOR_KEYS − dispatched − META_KEYS is empty) is red as written.
#      Add it to CuratorSignals' row: the honest YOU line is
#      `rank · pts · credit · next ≥`.  Do NOT close the gap by deleting the key.
#   4. VIEW_RETURN_TYPES was wrong for the three cross-check counters:
#      totalVolume is uint128 and totalContributors/totalTxCount are uint64
#      (packed slot), not uint256.  Only 3 of the 28 entries had been pinned;
#      all 28 are now recomputed from source.sol and from the vendored ABI.
#   5. CURATOR_ACTIVITY_KINDS / CURATOR_SIGNAL_STATES / CURATOR_DEGRADED_GROUPS
#      are new.  WP4 sizes the activity feed's `kind` cell from the first one
#      (test-side import) instead of retyping ("deposit", "joined", "saved");
#      WP3/WP5 assert their producers emit only these.
# ---------------------------------------------------------------------------
#
# Three things WP0 found where a doc and the chain disagreed.  The chain won:
#   * CURATOR's EIP-55 checksum is 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91.
#     wp0.md quotes a hand-retyped variant that is not checksummed.
#   * The sweep holds 231 Deposited logs, not 226 (1 + 231 + 145 = 377).
#   * Every captured log carries a block timestamp (RPC: blockTimestamp;
#     Blockscout: block_timestamp), so H14/A4's premise is false.  The
#     eth_getBlockByNumber batch is a fallback, not the only provenance.
#
# Mark every synthetic fixture, from its first commit, with the literal
#   # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
# so `rg "SYNTHETIC — re-point"` is the whole checklist.  Currently synthetic:
# the quiet hour boundary (stale lastActiveHour), any post-grace state
# (earlyBps == 10000), a judged hour with a deficit, the settled state and its
# Settled log, a HourSaved row, a creditedDelta == 0 deposit, and a Rescued row.
#
# LEDGER AMENDMENT (2026-08-17, sybil expansion): the three analysis slices in
# tests/fixtures/curator/sybil/ carry a DIFFERENT marker —
#   SYNTHETIC — calibrated from docs/curator_sybil_data/, re-point at a live
#   analysis bundle
# because what they are re-pointed at is a WP3 analysis bundle rather than a
# capture.  `rg "SYNTHETIC — re-point"` therefore does NOT find them.  The
# grep that finds **both** generations is `rg "SYNTHETIC —"`, and that is the
# one WP6 should close the ledger with.
#
# ---------------------------------------------------------------------------
# SYBIL EXPANSION 2026-08-17 — WP0 of the second curator build.
#
# The linked-wallet / fan-out analysis (docs/curator_sybil_PRD.md,
# docs/curator_sybil_implementation_plan.md) adds TWELVE keys and THREE row
# shapes to the contract above, plus one additive sub-key on
# `leaderboard_rows`.  Wave 1 (WP1 core ∥ WP5 wallet widgets) and wave 2 (WP2
# io/cli ∥ WP4 third view) all code against them without talking.
#
#   new keys ... operator_rows, segment_rows, clean_list_rows,
#                operators_count, clean_points, clean_contributors,
#                points_total, analysis_as_of_hhmm, you_linked_state,
#                you_linked_reasons, you_linked_group_size, you_clean_rank
#                — and they are exported as CURATOR_ANALYSIS_KEYS, because the
#                  analytics suite's output-surface guard needs to name the
#                  third producer of this dict without opening the analytics
#                  module.  Import the tuple; never re-type the twelve.
#
#   R14 (2026-08-18, WP4 fix round 1): `points_total` was ELEVENTH-HOUR-ADDED
#   to this set by controller ruling — the freeze missed the population total,
#   and the CLEANED LIST panel could not render PRD §5.3's "total points vs
#   clean points" from the eleven.  WP3 fills it from the SAME detect result
#   that produces `clean_points` (DetectResult.total_points), so the pair
#   always describes one snapshot; until then the manager's `_blank_payload`
#   emits it as None like every other analysis key.
#   new rows ... operator_rows / segment_rows / clean_list_rows
#   new sub-key  leaderboard_rows["link_conf"]  ("high"|"low"|"clean"|None)
#
# Four things about it that a later agent will otherwise re-litigate:
#
#   1. THE NEW KEYS ARE NOT IN `analytics/curator_signals.SIGNAL_OUTPUT_KEYS`,
#      and must never be added there.  The manager fills them AFTER
#      `build_signals`, exactly the way it merges ENS names — so
#      `curator_signals.py` stays byte-identical to what shipped, its
#      forbidden-word source scan is never touched, and its `flagged=True`
#      tests stay green.  `test_the_new_analysis_keys_are_not_in_the_signal_
#      surface` is the guardrail.
#   2. `flagged_points_share_pct` is REUSED, not duplicated (PRD §7).  It is
#      currently Tier-A's (`find_clusters`, the FARM rail row); the OPERATORS
#      panel wants the library's stronger ≥2-family number.  WHICH ONE WINS IS
#      WP3's decision, not WP0's — the plan (§6 risk 2) recommends the
#      library's once the sweep has last-good, falling back to Tier-A's before
#      that, so FARM and OPERATORS agree.
#   3. `clean_list_export_path` is DELIBERATELY ABSENT (plan §6 risk 1).  The
#      export is an `e` keypress inside the view, the path is screen-supplied
#      like `you_address`, and a manager key for it would couple a read-only
#      data layer to a file write.
#   4. `flagged` (bool) STAYS on `leaderboard_rows`.  PRD §6's "the flag
#      upgrades to confidence-graded" is implemented additively, for reason 1.
#
# Nothing else in this file moved.  The eight dataclasses, PHASES, SIGNAL_ROWS,
# CURATOR_ACTIVITY_KINDS, CURATOR_SIGNAL_STATES, CURATOR_DEGRADED_GROUPS and
# CURATOR_SERIES_KEYS are all exactly as the first freeze left them —
# in particular the analysis sweep folds its failures into the EXISTING `logs`
# degraded group (plan §6 risk 7), so the title bar's frozen group vocabulary
# is untouched.
#
# The routing table (which widget renders which new key) is pinned as
# `ANALYSIS_KEY_ROUTING` in tests/data/test_curator_models.py — in the test,
# not here, because `screens/curator.py` is WP4's file and WP0 may not edit it.
# The worst-case rows WP4/WP5 size against live in
# tests/fixtures/curator/sybil/; the datasets they are calibrated from are
# pinned in tests/data/test_curator_sybil_data.py:
#
#   operator_row_worst.json ... `worst_cluster` + `worst` (the 0.45 operator:
#                               1,995 wallets, 6.81% of points, 44.6x sqrt
#                               subsidy, conf "high", four reasons) + `rows`,
#                               all 16 operators.  `worst` IS its own entry in
#                               `rows`, not a second opinion about it.
#   segment_rows_worst.json ... 12 derived bands + `degraded_row`, the one
#                               carrying `points_share_pct: None`.
#   clean_list_rows_worst.json  top 20 survivors + `totals` + a NAME_COLS(12)
#                               width probe on a synthetic 0xff..ff address.
#   labeled_subset.json ....... 160 members + 60 controls, self-contained
#                               enough to run a detect() offline; byte-
#                               identical to sybilkit/tests/fixtures/.
#
# SIZE THE COLUMNS FROM THESE, and read them through
# `tests/curator_sybil_fixtures.worst_case_envelope()` / `row_payloads()` --
# NOT `worst_case_rows()`, which cannot see `worst` or `degraded_row`.  The
# maxima are over the WHOLE envelope and are pinned by
# `test_the_widest_strings_the_analysis_panels_must_fit`:
#
#   operator reason string ......... 53  ("consecutive join indices
#                                    14,001–14,100 · 1-block span" -- an
#                                    index-run operator in `rows`, NOT the 45
#                                    of `worst`'s own longest phrase)
#   reasons per row ................  4      joined length ............. 150
#   segment label .................. 33
#   segment detail ................. 56  (in `degraded_row`, outside `rows`;
#                                    the widest string in the whole set --
#                                    `rows` alone stops at 44)
#   clean-list name ................ 12  (NAME_COLS)   address ......... 42
#
# And the sybilkit side of the freeze, all importable and signature-pinned by
# sybilkit/tests/test_public_api.py, all raising NotImplementedError("WP1"):
#
#   sybilkit ................... Dataset, detect, DetectConfig, DetectResult,
#                                Deposit, Tx, Funding, Cluster, Reason,
#                                WalletVerdict
#   sybilkit.cluster ........... FAMILIES (the authority for the five family
#                                names), DetectConfig(min_size=5,
#                                min_families=2, near_amount_tol=0.10,
#                                confidence_threshold=0.5), detect(ds, config)
#   sybilkit.curve ............. curve_points(weight_wei, points_per_eth) —
#                                its own module because Cluster.points needs
#                                the curve in wave 1; WP2's curator preset
#                                re-exports THIS one, never a second copy
#   sybilkit.report ............ DEFAULT_CONFIDENCE_THRESHOLD, and
#                                DetectResult(clusters, total_points,
#                                flagged_points, clean_points, *,
#                                confidence_threshold=…)
#   sybilkit/tests/sybilkit_fixtures.py ... load() / slices() / labeled_subset()
#
# ---------------------------------------------------------------------------
# THE EXPECTED RED SET WAVE 1 INHERITS — 5 tests, all deliberate, all UI.
#
# Adding keys to a contract whose consumers assert TOTALITY reddens every
# consumer until it catches up.  That is the mechanism working, not a defect,
# and it is what tells each later WP exactly what to build.  Measured
# 2026-08-18: the whole suite is 4485 passed / 5 failed, and the same five
# curator files were 659/659 green at 4f08e6e, so these five and nothing else
# moved.  DO NOT skip, xfail, or "fix" them from another work package.
#
#  1. tests/screens/test_curator_screen.py::test_curator_keys_covers_the_local_signature_map
#  2. tests/screens/test_curator_screen.py::test_no_contract_key_reaches_no_widget
#     Both name the same 11 orphans (CURATOR_KEYS - dispatched - META_KEYS).
#     ** WP4 closes both ** by wiring WIDGET_SIGNATURES from
#     ANALYSIS_KEY_ROUTING in tests/data/test_curator_models.py.
#
#  3. tests/widgets/test_curator_widgets.py::test_the_leaderboard_columns_are_the_frozen_row_keys
#     The widget's row builder has no `link_conf` column.  ** WP5 closes it. **
#  4. tests/widgets/test_curator_widgets.py::test_the_keys_no_widget_reads_are_named_here_rather_than_forgotten
#     The 11 keys reach no widget in the widgets package.  ** WP4 (the three
#     new panels) and WP5 (the wallet-standing lines) close it together. **
#  5. tests/widgets/test_curator_widgets.py::test_the_full_payload_is_exactly_the_frozen_contract
#     That suite's `_full_payload()` helper needs the 11 new keys.  ** WP4 or
#     WP5, whichever touches the helper first. **
#
# TWO ANALYTICS REDS WERE CLOSED IN WP0 (controller rulings R8/R9, fix round 1)
# and neither of them touched analytics/curator_signals.py, which is still
# byte-identical to what shipped — `git diff main -- .../curator_signals.py` is
# empty, and a test asserts SIGNAL_OUTPUT_KEYS is not derived from CURATOR_KEYS.
#
#   * test_the_output_surface_is_the_flat_contract_minus_the_managers_own_keys
#     now asserts CURATOR_KEYS - SIGNAL_OUTPUT_KEYS ==
#     MANAGER_OWNED_KEYS | CURATOR_ANALYSIS_KEYS, importing the tuple from
#     THIS module.  Three producers, one exact equality, still biting both
#     ways.  That is why CURATOR_ANALYSIS_KEYS exists.
#   * test_the_grace_payload_reproduces_the_bundle now compares build_signals'
#     leaderboard rows against the frozen tuple MINUS `link_conf`, and asserts
#     `link_conf` is still IN the frozen tuple so the subtraction cannot go
#     vacuous.  The precedent it exposes is WP3's to honour: build_signals
#     emits `"name": None` as a PLACEHOLDER (curator_signals.py:1519, :1538)
#     which `_label_with_ens` fills, so `name` is in the tuple even though the
#     manager owns the value.  `link_conf` gets NO placeholder — WP3's adapter
#     merge must seed `row["link_conf"] = None` on every row itself.
#
# ONE PREDICTION IN THE WP0 BRIEF IS WRONG, and WP3 should know why.
# `tests/data/test_curator_manager.py::test_it_returns_exactly_curator_keys_always`
# was expected to redden and DOES NOT.  `CuratorManager._finalise` builds from
# `_blank_payload()`, which is derived from CURATOR_KEYS, so the manager
# already returns all 11 new keys — as `None`, from an analysis that has never
# run.  WP3 therefore inherits no red there, and must write its own test that
# the keys are FILLED rather than merely present: the totality test cannot
# tell the difference and stays green either way.
# ---------------------------------------------------------------------------
# ===========================================================================

#: The three phases of the settlement state machine, in order.
#:
#: One tuple, imported by the analytics layer (which produces it), the manager
#: (which passes it through), the widgets (which branch on it) and the screen
#: (which picks the swap-slot default from it).  A fourth spelling anywhere is a
#: silent fallback arm.
PHASES: tuple[str, ...] = ("grace", "judged", "settled")

#: The seven signal-rail rows, in render order: PRD §4's
#: ``SETTLED · HOUR AT RISK · HOUR SAVED · WHALE · FARM · FORCED ETH · YOU``.
#: ``sig_settled_state`` and ``sig_at_risk_state`` are the two whose colour is a
#: judgement rather than a number; the rest are observations.
#:
#: **``you`` is last and that is the hazardous position**: a rail inside a
#: fixed-height column loses its last row first (the FWA coverage-badge bug), so
#: the row that carries the reader's own standing is the one that silently
#: disappears.  WP4 pins all seven against the compositor.
#:
#: There is deliberately **no ``rescued`` row**.  This tuple used to end in one,
#: which contradicted every spec the widget author reads and would have shipped
#: an eight-label rail against a seven-label test.  ``rescued_total_eth`` is a
#: real key and it renders **inside the FORCED ETH row** — forced in, swept out,
#: one anomaly with two numbers — rather than spending a row of a rail that is
#: already one row from clipping.
#:
#: Widgets may not import ``data/`` (CLAUDE.md), so this tuple is read by
#: *tests* and by the manager, never by ``widgets/curator/*`` itself.
SIGNAL_ROWS: tuple[str, ...] = (
    "settled",
    "at_risk",
    "hour_saved",
    "whale",
    "clusters",
    "forced_eth",
    "you",
)


# ---------------------------------------------------------------------------
# Chain state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CuratorState:
    """One batched ``eth_call`` round — the PRD fast tier — plus the balance.

    Eight views in one batch: ``isSettled``, ``currentHour``,
    ``currentHourTotal``, ``ethNeededThisHour``, ``timeLeftInHour``,
    ``lastActiveHour`` (2 words), ``earlyMultiplierBps``, ``stats`` (3 words);
    ``forced_balance_wei`` comes from a separate ``eth_getBalance``.

    Every field is independently failable: one sub-call that reverted or was
    dropped degrades *that* field to ``None``, not the round.

    ``settled`` is a ``bool | None`` and the three states are all distinct:
    ``True`` (the game is over), ``False`` (it is running) and ``None`` (we do
    not know).  Only the first may render SETTLED.

    ``current_hour`` and ``last_active_hour`` disagreeing is **normal**, not an
    error: at an hour boundary the clock has moved and no deposit has landed in
    the new bucket yet.  Post-grace that same shape is the at-risk state.

    ``forced_balance_wei`` is **always forced ETH**, never deposits — every wei
    of a deposit is refunded in the same transaction.  It feeds the ``forced_eth``
    anomaly row and must never reach a volume, TVL or hero total; the expected
    rendering is ``—``.
    """

    settled: bool | None
    current_hour: int | None
    current_hour_total_wei: int | None
    hour_needed_wei: int | None
    hour_seconds_left: int | None
    last_active_hour: int | None
    last_active_hour_total_wei: int | None
    early_bps: int | None
    volume_wei: int | None
    contributors: int | None
    tx_count: int | None
    forced_balance_wei: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class CuratorConfig:
    """The ``once`` tier: eight immutables, one constant, one address.

    Read **live**, never hardcoded (CLAUDE.md).  ``curator_addresses`` pins the
    same numbers so a test can prove the live read agrees, but the dashboard
    always renders what the chain answered.  Nothing on this contract can change
    them — there is no owner power that reaches a parameter — so ``once`` is a
    genuine forever cache rather than a long TTL.

    ``deployer`` is an address string, not a number: decode it with
    ``decode_address``.
    """

    launch_time: int | None
    hourly_threshold_wei: int | None
    grace_period: int | None
    hour_duration: int | None
    min_deposit_wei: int | None
    min_escalation_wei: int | None
    credit_cap_wei: int | None
    first_judged_hour: int | None
    points_per_eth: int | None
    deployer: str | None


@dataclass(frozen=True, slots=True)
class WalletState:
    """The six argument-taking views, for the YOU row.  Only when a wallet is set.

    ``first_hour`` is **already un-shifted** — it is ``firstHourOf()``'s first
    word, not the packed struct's ``firstHour + 1``.  ``has_joined`` is the
    second word, and it exists because ``first_hour == 0`` is ambiguous without
    it: ``(0, False)`` means "never deposited" and must never render as "joined
    in hour 0".

    ``required_next_wei`` is what the *next* deposit from this address must
    exceed (high-water mark + ``minEscalation``); it is a live number that grows
    every time the wallet deposits.
    """

    address: str
    points: int | None
    weight_wei: int | None
    contributed_wei: int | None
    tx_count: int | None
    first_hour: int | None
    has_joined: bool | None
    required_next_wei: int | None


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DepositEvent:
    """One decoded ``Deposited`` log.  Raw words only — nothing derived.

    ``contributor`` and ``hour`` are the two **indexed** topics, which is why
    hour bucketing needs no timestamp at all: the hour is in the log, and its
    wall clock is ``launchTime + hour * hourDuration``, exact by construction.

    ``credited_delta_wei`` may legitimately be ``0`` (a deposit above the credit
    cap) and ``weight_added_wei`` with it.  Both are still real measurements;
    neither is a failed read, and nothing may divide by either.

    ``weight_added_wei == credited_delta_wei * early_bps // 10_000``, floored —
    an identity that holds for all 231 captured rows and is re-asserted wei-exact
    by the analytics suite.

    ``ts`` is the block's wall clock, filled by the bounded
    ``eth_getBlockByNumber`` batch, and is ``None`` when that read failed.  A
    ``None`` renders ``--:--``, never ``00:00``.  ``(tx_hash, log_index)`` is the
    de-dupe key: without it a re-org replay renders every deposit twice.
    """

    contributor: str
    hour: int
    amount_wei: int
    credited_delta_wei: int
    weight_added_wei: int
    new_weight_wei: int
    tx_count: int
    hour_total_wei: int
    early_bps: int
    block_number: int
    tx_hash: str
    log_index: int
    ts: float | None = None


@dataclass(frozen=True, slots=True)
class LogSweep:
    """One ``eth_getLogs`` window, grouped by event, rows still raw.

    Each group holds the log dicts as the endpoint served them, with ``topics``,
    ``data``, ``blockNumber``, ``transactionHash`` and ``logIndex`` intact — the
    decoders live downstream so they have exactly one caller and one hostile-input
    suite.

    ``()`` means "read, nothing matched" **or** "this one filter failed".  A
    frozen tuple cannot hold ``None``, so the per-group failure travels
    out-of-band in the client's ``log_group_failed`` dict and reaches the user
    through the manager's ``degraded`` list.  A sweep where **every** group
    failed returns ``None`` instead of a :class:`LogSweep`.
    """

    from_block: int | None
    to_block: int | None
    deposits: tuple[dict, ...] = ()
    first_deposits: tuple[dict, ...] = ()
    hour_saved: tuple[dict, ...] = ()
    settled: tuple[dict, ...] = ()
    rescued: tuple[dict, ...] = ()
    launched: tuple[dict, ...] = ()


# ---------------------------------------------------------------------------
# Folds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContributorRow:
    """One folded leaderboard row.  Produced by the fold, not by the client.

    ``credit_wei`` is the address's high-water mark — its credited net
    contribution — not the gross it routed; ``weight_wei`` is the sum of
    ``creditedDelta × earlyBps``, which is what the curve turns into points.
    The two diverge for anyone who deposited late, and calling either "volume"
    is wrong.

    ``points`` stays ``None`` until the curve is applied.  A ``0`` there would
    render a real entry as having scored nothing.

    ``first_index`` is ``FirstDeposit``'s **1-based** index; it maxes at exactly
    ``totalContributors``.
    """

    address: str
    weight_wei: int
    credit_wei: int
    tx_count: int
    first_hour: int | None
    first_index: int | None
    points: int | None = None


@dataclass(frozen=True, slots=True)
class HourBucket:
    """One hour of the game, folded from ``Deposited`` logs only.

    Never from ``currentHourTotal()`` — that view zeroes at every boundary and a
    series fed from it renders the boundary as a crash.

    ``judged`` is false for the in-progress hour and for every hour before
    ``firstJudgedHour``: the contract's own ``_isShort`` returns false while
    ``lastActive == hour``, so the hour you are living in is never judged.

    ``saved_by`` is the address of a ``HourSaved`` savior and is ``None`` for
    every hour that event never fired in — which, as of the captures, is all of
    them.  It may never fire at all; the row renders its explicit never-fired
    state rather than waiting for a payload.
    """

    hour: int
    volume_wei: int
    deposits: int
    judged: bool
    saved_by: str | None = None


@dataclass(frozen=True, slots=True)
class SettlementRecord:
    """The settlement evidence record — the latch, and later the obituary.

    ``settle()`` is permissionless and may lag death indefinitely, so
    ``isSettled()`` is polled and the *view* is the source of truth.  The first
    three fields are that observation: on the first ``True``, the manager writes
    ``{value, block_number, observed_at}`` and **never re-reads through it**.
    A later outage degrades the freshness marker, never the phase.

    The last four are filled from the ``Settled`` log when it eventually
    appears, and stay ``None`` until then — possibly forever.  ``settled_hour``
    is the hour that failed; ``settled_at_ts`` is the log's own timestamp word,
    not the observation time.
    """

    settled: bool
    block_number: int | None
    observed_at: float
    settled_hour: int | None = None
    settled_at_ts: int | None = None
    total_contributors: int | None = None
    total_volume_wei: int | None = None


# ---------------------------------------------------------------------------
# The flat manager contract
# ---------------------------------------------------------------------------

#: The exact key set of ``CuratorManager.fetch_and_compute()``.  PRD §5, made
#: precise.
#:
#: Every numeric is ``float | int | None`` and ``None`` renders the widget's
#: **unavailable** state, never a 0.  Every list defaults to ``[]`` meaning
#: "read, nothing to show" -- a failed read reaches the user through
#: ``degraded``, never through an empty table pretending to be an empty game.
#:
#: The manager builds exactly these keys, always all of them: a total failure
#: returns the full contract with every value ``None``/``[]``, because a screen
#: that has to guess whether a key exists is a screen with a silent fallback arm.
CURATOR_KEYS: tuple[str, ...] = (
    # ---- phase machine ------------------------------------------------------
    "phase",                    # "grace" | "judged" | "settled" — one of PHASES
    "settled",                  # bool | None — isSettled(); None is "unknown"
    "settled_hour",             # int | None — from the Settled log, not the view
    "settled_at_ts",            # int | None — the Settled log's own timestamp
    "settled_observed_at",      # float | None — when the latch first saw True
    "lived_desc",               # str | None — "lived 3 h 12 m" / "alive 4 h"
    # ---- clock --------------------------------------------------------------
    "current_hour",             # int | None — hour index since launch
    "hour_fed_eth",             # float | None — folded from Deposited logs only
    "hour_needed_eth",          # float | None — 0.0 in grace is REAL, not unknown
    "hour_seconds_left",        # int | None — hourDuration at a boundary, never 0
    "grace_seconds_left",       # int | None — 0 once grace is over
    "grace_ends_utc",           # str | None — "2026-08-17 19:58:47Z"
    # ---- config, read live off the `once` tier ------------------------------
    # Two chain constants the widgets have to RENDER, not merely branch on.
    # Neither is recoverable from any other key, and CLAUDE.md forbids a widget
    # hardcoding the documented value:
    "hourly_threshold_eth",     # float | None ★ — the "/5.00 ETH" denominator
                                #   of the hero clock and the sparkline's
                                #   survival bar.  NOT derivable from
                                #   hour_fed_eth + hour_needed_eth:
                                #   ethNeededThisHour() returns 0 all through
                                #   grace AND whenever a judged hour is already
                                #   safe (source.sol:547), so the sum equals the
                                #   threshold only while an hour is short.
    "first_judged_hour",        # int | None ★ — hourlyThreshold's first bite.
                                #   The literal 24 in "n/a until hour 24"
                                #   (HOUR AT RISK during grace) and in
                                #   "no judged hours yet".  gracePeriod //
                                #   hourDuration on this deployment, but neither
                                #   operand is in the flat dict either.
    # ---- curve --------------------------------------------------------------
    "early_multiplier_x",       # float | None — earlyBps / 10 000, e.g. 1.9491
    "points_per_eth_now",       # float | None — the effective rate right now
    "survival_streak_hours",    # int | None — judged hours survived in a row
    "closest_call_margin_eth",  # float | None — thinnest judged-hour margin
    "closest_call_hour",        # int | None — the hour that margin belongs to
    # ---- the list -----------------------------------------------------------
    "contributors_total",       # int | None
    "deposits_total",           # int | None
    "volume_routed_eth",        # float | None — ROUTED, all of it refunded
    "top_points",               # int | None — rank 1's score
    # ---- signals ------------------------------------------------------------
    "last_saved_hour",          # int | None — None means HourSaved never fired
    "last_saved_wallet",
    "last_saved_ens",           # str | None — verified name for last_saved_wallet        # str | None
    "last_saved_age_s",         # float | None
    "whale_amount_eth",         # float | None
    "whale_wallet",
    "whale_ens",                # str | None — verified name for whale_wallet             # str | None
    "whale_age_s",              # float | None
    "clusters_count",           # int | None — 0 is a real answer
    "flagged_points_share_pct", # float | None
    "forced_eth",               # float | None — ALWAYS forced ETH, never deposits
    "rescued_total_eth",        # float | None — Rescued has never fired
    "sig_settled_state",        # "ok" | "watch" | "fired" | None
    "sig_at_risk_state",        # "ok" | "watch" | "fired" | None
    # ---- YOU (all None when no wallet is configured) ------------------------
    "you_rank",                 # int | None
    "you_points",               # int | None
    "you_credit_eth",           # float | None — the high-water mark, not gross.
                                #   PRD §5 names it; PRD §4's rail line
                                #   ("rank · pts · next ≥ X.XX ETH") forgot it.
                                #   The key stays — the honest YOU row is
                                #   rank · pts · credit · next ≥ — and the rail's
                                #   kwarg row in wp4/wp6 is what needs the fix.
    "you_required_next_eth",    # float | None — what the next deposit must beat
    "you_marginal_points",      # int | None — points requiredNext would buy
    # ---- YOU, the dedicated view (`y`) --------------------------------------
    # Everything below is folded from data the fast tier and the log sweep
    # already fetched; the view adds no request of its own.
    "you_weight_eth",           # float | None — the curve's input, not the score
    "you_tx_count",             # int | None — sends that counted, not attempts
    "you_first_hour",           # int | None — 0 is a real hour (the launch one)
    "you_joined_utc",           # str | None — launchTime + first_hour * 3600
    "you_weight_share_pct",     # float | None — share of ALL weight, not of the
                                #   top ten. The sqrt curve rewards splitting
                                #   across wallets, so this is what one key
                                #   holds, never what a person holds.
    "you_ladder_rows",          # list[dict] — CURATOR_ROW_KEYS["you_ladder_rows"]
    "you_next_rank",            # int | None — the rank above; None at rank 1
    "you_ens",                  # str | None — verified reverse ENS, or None
    "you_next_send_passes",     # bool | None — does the MINIMUM legal send
                                #   already pass the rank above?  None is "we
                                #   could not tell", never "no".
    "you_next_rank_needs_eth",  # float | None — one send that would pass it.
                                #   None at the credit cap: no send buys weight
                                #   there, and a number would be a promise the
                                #   contract will not keep.
    # ---- rows ---------------------------------------------------------------
    "leaderboard_rows",         # list[dict] — CURATOR_ROW_KEYS["leaderboard_rows"]
    "activity_rows",            # list[dict] — CURATOR_ROW_KEYS["activity_rows"]
    "closest_call_rows",        # list[dict] — CURATOR_ROW_KEYS["closest_call_rows"]
    "cluster_rows",             # list[dict] — CURATOR_ROW_KEYS["cluster_rows"]
    "volume_series",            # list[[ts, value]] — through coerce_points
    "contributors_series",      # list[[ts, value]] — through coerce_points
    # ---- linked-wallet analysis (MODE_ANALYSIS, the `f` view) ---------------
    # Produced by the manager's adapter AFTER build_signals, from the detached
    # B+C sweep's last-good — never by analytics/curator_signals (see the note
    # under CURATOR_ROW_KEYS).  Every one of them is `None` until that sweep
    # has published once, and `None` here is "could not analyze", which the
    # three panels render as their own unavailable state.
    "operator_rows",            # list[dict] — CURATOR_ROW_KEYS["operator_rows"]
    "segment_rows",             # list[dict] — CURATOR_ROW_KEYS["segment_rows"]
    "clean_list_rows",          # list[dict] — CURATOR_ROW_KEYS["clean_list_rows"]
    "operators_count",          # int | None ★ — 0 is "analyzed, none linked",
                                #   a real answer; None is "could not analyze".
                                #   The FARM-row defect is exactly this pair
                                #   collapsing, so both must be representable.
    "clean_points",             # int | None — total points with the linked
                                #   groups removed.  0 would mean the whole
                                #   list is linked, which is an answer too.
    "clean_contributors",       # int | None — survivor count
    "points_total",             # int | None — the population's total curve
                                #   points at the ANALYSIS snapshot (R14,
                                #   2026-08-18: the freeze missed it, and
                                #   without it the CLEANED LIST cannot render
                                #   PRD §5.3's "total vs clean").  Taken from
                                #   the same detect result as `clean_points`
                                #   so the two always describe one snapshot;
                                #   None is "analysis not run", never 0.
    "analysis_as_of_hhmm",      # str | None — the B+C sweep's OWN freshness
                                #   marker.  Separate from `as_of_hhmm`
                                #   because the sweep is detached and long-TTL:
                                #   one marker for both tiers would present an
                                #   hours-old analysis as live.
    # ---- YOU, linkage (all None when no wallet is configured) ---------------
    "you_linked_state",         # str | None — "clean" | "linked".  None is
                                #   "the sweep has not run", and must render
                                #   `-- unknown`, NEVER a confident "clean".
    "you_linked_reasons",       # list[str] — pattern-language phrases;
                                #   [] is "analyzed, not linked"
    "you_linked_group_size",    # int | None — size of the group, when linked
    "you_clean_rank",           # int | None — rank in the de-sybilled list.
                                #   Rendered beside `you_rank`, never instead
                                #   of it: "#412 raw, #47 with clear farms
                                #   removed" is the whole point.
    "you_list_row",             # dict | None — complete fixed row under the
                                #   raw/clean list, including JOIN # even when
                                #   the wallet ranks below the display cap.
    # ---- health -------------------------------------------------------------
    "degraded",                 # list[str] — group names ⊆ {state, logs, wallet}
    "as_of_hhmm",               # str — the rendered freshness marker
    "as_of",                    # float — epoch, for the screen's own bookkeeping
)

#: Row shapes for the eight list-of-dict payloads.  Widgets index these keys
#: directly, so adding one is a contract change, not an implementation detail.
#:
#: Every amount here is already ETH: the manager divided once, at the boundary.
#: Nothing is called TVL, locked, at risk or capital — every wei this contract
#: ever saw was refunded inside the same transaction, so the only honest word
#: for the number is *routed*.
#:
#: Nothing here is called a sybil, a cheat or a farm either, and that is a
#: schema rule rather than a copy rule: a column name reaches the screen as a
#: ``DataTable`` header long before any widget author gets a say.  The linked
#: groups are ``operator_rows``; the 44.6× number is ``sqrt_subsidy_x``, which
#: names a property of the curve (it pays ``sqrt(k)`` for splitting one
#: bankroll across ``k`` wallets) rather than an accusation about a person.
CURATOR_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "leaderboard_rows": (
        "rank", "address", "points", "credit_eth", "tx_count", "flagged",
        # Verified reverse ENS for `address`, or None.  Rendered in the
        # address cell's own width, so a name never widens the table.
        "name",
        # Record traits already present in the contributor fold. ETH values
        # are projected here; raw wei never crosses the flat-dict boundary.
        "weight_eth", "first_hour", "first_index",
        # "high" | "low" | "clean" | None  ->  ⚑ / ◌ / (empty) / ?
        #
        # ADDITIVE, and appended rather than folded into `flagged`.  PRD §6
        # calls this "the flag upgrades to confidence-graded", which reads like
        # a type change on `flagged` -- but `flagged` is filled by
        # analytics/curator_signals.py, and that module must stay EXACTLY as
        # shipped (PRD §2; its source is forbidden-word-scanned).  So the bool
        # stays, the grade is a new sub-key merged in by the manager the way
        # `name` is merged by `_label_with_ens`, and the widget grades off
        # `link_conf` when it is present and off `flagged` when it is not.
        #
        # None is "the analysis sweep has not run", rendered `?` -- never an
        # empty cell, which is the *clean* rendering and would be a confident
        # negative drawn from a missing read.
        "link_conf",
    ),
    # ``ts`` is None when the block-timestamp batch failed -> renders "--:--".
    # ``tx_hash`` + ``log_index`` are the de-dupe key (PRD §4).
    "activity_rows": (
        "ts", "address", "amount_eth", "credited_eth", "new_weight",
        "tx_count", "hour", "kind", "tx_hash", "log_index", "name",
    ),
    "closest_call_rows": (
        "hour", "volume_eth", "margin_eth", "savior", "savior_name",
    ),
    # One row per send the reader made.  ``capped`` marks a deposit that
    # credited nothing because it was above the 1000 ETH cap -- it still counted
    # in full toward that hour's survival, so the 0 is a fact about the cap.
    "you_ladder_rows": (
        "hour", "amount_eth", "credited_eth", "weight_eth", "early_x", "capped",
        # The running score after that rung, off the event's own new_weight.
        "points",
        # The place this wallet stood in right after it -- None when the event
        # history has dropped rows, where the number would flatter the reader.
        "rank",
        "ts",
    ),
    "cluster_rows": (
        "size", "amount_eth", "first_block", "last_block", "points",
        "points_share_pct",
    ),
    # ---- the analysis view's three panels ---------------------------------
    # One row per linked-wallet group, widest first.  `reasons` is a
    # list[str] of pattern-language phrases ("identical 0.45Ξ send ×1,995",
    # "shared funder chain") -- already escaped copy, not a code, because the
    # panel renders them verbatim and the reader is meant to judge the shape
    # rather than trust a score.
    #
    # `conf` is "high" | "low" | None and renders as a filled/hollow marker,
    # never a raw number: 0.87 on a screen reads as a verdict with a decimal
    # point.  `sqrt_subsidy_x` is the curve's own multiple (44.6× for the
    # widest real operator), and `points_share_pct` is already a percentage --
    # the library reports a share in [0,1] and the manager multiplies once.
    "operator_rows": (
        "size", "reasons", "points", "points_share_pct", "sqrt_subsidy_x",
        "conf",
    ),
    # Adam's segments: whale *operators* by combined credit, the index-1000
    # early cohort, per-hour join bands, per-multiplier bands.  `detail` is a
    # free pattern-language string the panel prints after the numbers.
    #
    # `points_share_pct` is `float | None` here and the None is load-bearing:
    # some bands (a per-hour join band, say) have a contributor count but no
    # attributable points share, and a 0.0 there would read as "this hour
    # scored nothing".
    "segment_rows": ("label", "contributors", "points_share_pct", "detail"),
    # The de-sybilled list.  `clean_rank` is the survivor rank, which is NOT
    # `rank` -- the two are rendered side by side ("#412 raw, #47 clean") and
    # one name for both would make that line impossible to write.
    "clean_list_rows": (
        "clean_rank", "address", "points", "credit_eth", "name",
        "weight_eth", "tx_count", "first_hour", "first_index",
    ),
}

#: The thirteen keys the **manager's analysis adapter** produces, and the only
#: keys in ``CURATOR_KEYS`` that ``build_signals`` does not emit besides
#: ``curator_signals.MANAGER_OWNED_KEYS`` (``degraded``, ``as_of_hhmm``,
#: ``as_of``).  Eleven at the freeze; ``points_total`` added the population
#: comparison and ``you_list_row`` added the uncapped fixed wallet record.
#:
#: It exists so the analytics suite's output-surface guard can stay an exact
#: equality —
#: ``CURATOR_KEYS − SIGNAL_OUTPUT_KEYS == MANAGER_OWNED_KEYS | CURATOR_ANALYSIS_KEYS``
#: — **without** ``analytics/curator_signals.py`` being edited.  That module
#: must stay byte-identical to what shipped (PRD §2): its source is
#: forbidden-word-scanned, and its Tier-A behaviour is explicitly out of scope
#: for this build.  Putting the names *here*, in the contract module both sides
#: already import, is what lets the guard keep biting on both directions of
#: drift while the analytics module is never opened.
#:
#: Hand-typed rather than filtered out of ``CURATOR_KEYS``: a derivation would
#: make ``test_the_analysis_keys_are_exactly_the_thirteen_the_adapter_fills``
#: compare a constant against itself, and the same redundancy rule already
#: applies to ``SIGNAL_OUTPUT_KEYS`` one module over.
CURATOR_ANALYSIS_KEYS: tuple[str, ...] = (
    "operator_rows",
    "segment_rows",
    "clean_list_rows",
    "operators_count",
    "clean_points",
    "clean_contributors",
    "points_total",
    "analysis_as_of_hhmm",
    "you_linked_state",
    "you_linked_reasons",
    "you_linked_group_size",
    "you_clean_rank",
    "you_list_row",
)

#: The exact ``kind`` values the activity-row producer emits — the vocabulary,
#: not just the column name.
#:
#: ``CURATOR_ROW_KEYS`` freezes that a row *has* a ``kind``; without this tuple
#: nothing freezes what goes in it, and the two sides are written a wave apart:
#: the widget sizes a fixed-width cell in wave 2, the producer fills it in wave
#: 3.  That is exactly the ``dev``/``ops`` defect CLAUDE.md records — a cell
#: sized to a remembered vocabulary is simultaneously padded and cutting a value
#: mid-word, and both suites stay green while it happens.
#:
#: The consumer sizes from ``max(len(k) for k in CURATOR_ACTIVITY_KINDS)`` (a
#: **test-side** import; widgets may not import ``data/``) and the producer
#: asserts membership.  Adding a value is a contract change that costs columns.
CURATOR_ACTIVITY_KINDS: tuple[str, ...] = ("deposit", "joined", "saved")

#: The only three values ``sig_settled_state`` / ``sig_at_risk_state`` may hold,
#: besides ``None`` (= unknown, which renders the unavailable state, never
#: "ok").  A colour vocabulary is as size- and branch-sensitive as the kinds
#: above: a fourth spelling from the analytics layer is a silent fallback arm.
CURATOR_SIGNAL_STATES: tuple[str, ...] = ("ok", "watch", "fired")

#: The only group names that may appear in ``degraded``.  The title bar renders
#: them verbatim ("⚠ logs, state, wallet"), so an unlisted spelling reaches the
#: user as-is.
CURATOR_DEGRADED_GROUPS: tuple[str, ...] = ("state", "logs", "wallet")

#: The two ``[timestamp, value]`` payloads.  They are **not** lists of dicts, so
#: they get a name of their own rather than a column tuple that would tell a
#: widget to index a 2-tuple by key.  Both load through
#: ``data/series_points.coerce_points``, and both are fed **only** from folded
#: ``Deposited`` logs — never from ``currentHourTotal()``, which zeroes at every
#: hour boundary and would write that zero into the history for good.
CURATOR_SERIES_KEYS: tuple[str, ...] = ("volume_series", "contributors_series")


__all__ = [
    "PHASES",
    "SIGNAL_ROWS",
    "CURATOR_KEYS",
    "CURATOR_ROW_KEYS",
    "CURATOR_ANALYSIS_KEYS",
    "CURATOR_SERIES_KEYS",
    "CURATOR_ACTIVITY_KINDS",
    "CURATOR_SIGNAL_STATES",
    "CURATOR_DEGRADED_GROUPS",
    "CuratorState",
    "CuratorConfig",
    "WalletState",
    "DepositEvent",
    "LogSweep",
    "ContributorRow",
    "HourBucket",
    "SettlementRecord",
]
