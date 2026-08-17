# Wave-3 brief — the client, the analytics and the widgets

Written by the wave-2 gate after WP2, WP3 and WP4 landed and the full suite went green
(4030 passed, 0 failed, 0 skipped — wave 2 added 421 tests). This is what WP5 (cache +
manager) and WP6 (screen) need in order to start **without reading wave 2's source**.
Where this file and an older document disagree, this file wins for names and shapes, and
the source wins over this file.

---

WAVE-3 BRIEF — the exact public surface of everything wave 2 built.
Written so WP5 (cache+manager) and WP6 (screen) can start without opening WP2/WP3/WP4 source.
Where this disagrees with an older doc, this wins; where it disagrees with the source, the source wins.

=====================================================================
0. STATE OF THE TREE
=====================================================================
Suite: 4030 passed / 0 failed / 0 skipped, 223 s. Tree clean.
Wave-2 commits (newest first): dacce86 docs(curator): correct the three hand-off widths that were never measured ·
0481cfb fix(curator): measure every widget width against what its producer emits ·
9707f57 fix(curator): shrink on a result cap and stop truncating the cross-check ·
1ba8370 fix(curator): a dead logs tier leaves the survival streak unknown — on top of wave 1's 21 curator commits.
Curator test counts: client 110 · signals 136 · widgets 175 · models 68 · addresses 139 · captures 34 = 662.
Key arithmetic reconciles exactly: len(CURATOR_KEYS)==49 == 46 SIGNAL_OUTPUT_KEYS + 3 MANAGER_OWNED_KEYS; no key
is produced by nobody and none is produced twice.

=====================================================================
1. maxpane_dashboard/data/curator_client.py  (WP2) — what WP5 calls
=====================================================================
class CuratorClient(OwnedHttpClient)   # close() / __aenter__ / __aexit__ come from the base

__init__(state_rpc: str = STATE_RPC_PRIMARY,
         state_fallbacks: list[str] | None = None,
         log_rpcs: list[str] | None = None,
         blockscout_base: str = BLOCKSCOUT_BASE,
         *, http_client: httpx.AsyncClient | None = None,
         inter_call_delay: float = 0.12,
         backoff_seconds: tuple[float, ...] = (0.5, 1.5),
         now_fn: Callable[[], float] = time.time,
         log_page_blocks: int = LOG_PAGE_BLOCKS) -> None
  * Raises ValueError at construction for a banned host (eth.llamarpc.com, rpc.ankr.com,
    cloudflare-eth.com, api.reservoir.tools, *.alchemy.com, *.infura.io, *.etherscan.io).
  * Inject http_client in every test. The real User-Agent is set per REQUEST, so an injected
    client keeps it.
  * Properties: .state_endpoints -> list[str], .log_endpoints -> list[str] (copies).

ASYNC METHODS — signature, return shape, failure encoding

  await fetch_state() -> CuratorState | None
    One JSON-RPC batch array: the 8 FAST_VIEW_SELECTORS plus eth_blockNumber as the LAST entry of the
    SAME array (state and height therefore describe the same block).
    None only when no endpoint served the array at all. Otherwise every field degrades on its own:
    one reverted entry is that field's None, never the round's.
    forced_balance_wei is ALWAYS None here — it is fetch_balance()'s, and WP5 folds it in with
    dataclasses.replace. That separation is deliberate (the balance is forced ETH, never a volume).
    block_number comes from the trailing eth_blockNumber.

  await fetch_config() -> CuratorConfig | None
    The 10 ONCE_VIEW_SELECTORS in one batch. Same degradation contract. Nothing on this contract can
    change these, so WP5 may cache the result forever. It NEVER falls back to curator_addresses' pins.

  await fetch_wallet(address: str) -> WalletState | None
    The 6 WALLET_VIEW_SELECTORS, each selector + encode_address(wallet), in one batch.
    An address that cannot be one (length/hex check) costs ZERO requests and returns None with
    wallet_failed=True. first_hour/has_joined come from firstHourOf()'s two words: (0, False) is a
    stranger, (0, True) is a launch-hour founder.

  await fetch_balance() -> int | None
    eth_getBalance(CURATOR). A bare int on purpose so nothing can reach it off a state object.
    0 is the HEALTHY answer (every wei is refunded in-tx); None is "could not read". Feeds forced_eth
    alone — never a volume, TVL or hero total.

  await fetch_logs(from_block: int, to_block: int | str = "latest") -> LogSweep | None
    LOGS POOL ONLY. One address-scoped filter with a topic0 OR-array is the cheap path; six per-topic
    filters are the fallback for an endpoint that refuses the array. Paged at LOG_PAGE_BLOCKS=2000 with
    bounded halving (max 3 shrinks, floor 300 blocks) that narrows the window's RIGHT edge — never
    raises fromBlock, which would walk past history nothing re-asks for.
    Returns a LogSweep whose six groups hold RAW LOG DICTS, verbatim (topics / data / blockNumber /
    transactionHash / logIndex / blockTimestamp all intact), de-duplicated on (transactionHash, logIndex)
    and filtered to rows whose address is the curator.
    None ONLY when every group failed. Otherwise read client.log_group_failed to tell "()" apart from
    "this filter died" — a dead settled filter otherwise reads as "the game is alive".
    to_block="latest" resolves the head on the LOGS pool; if that fails, every group is marked failed
    and the call returns None having attempted no filter.

  await fetch_block_timestamps(block_numbers: Iterable[int]) -> dict[int, int]
    A FALLBACK, not the provenance — every captured row already carries its own stamp. Distinct blocks
    only, sorted, bounded to the NEWEST MAX_TIMESTAMP_BLOCKS=40. An empty input makes NO request and
    returns {}. A block that could not be read is ABSENT from the dict, never mapped to 0. Returns {}
    (never None) on total failure.

  await fetch_blockscout_logs(max_pages: int = MAX_BLOCKSCOUT_PAGES) -> list[dict] | None
    The RPC sweep's independent cross-check, following next_page_params verbatim.
    None = could not read COMPLETELY — any page failing, AND exhausting max_pages with a cursor still
    open. [] = read fine, nothing there. A truncated list is never handed out, because these rows exist
    to be diffed and half of them diff into phantom gaps.
    client.blockscout_truncated separates the two Nones: True means "the history outgrew the pager's
    budget" (a configuration problem), False means "the source is down".

DEGRADATION SURFACE — six attributes, each reset at the START of the call it describes, so a recovered
endpoint clears it with nobody remembering to:
  .state_failed: bool        fetch_state() failed in whole OR in part
  .config_failed: bool       fetch_config(), same contract (separate because the once tier is on its own
                             schedule; WP5 folds both into the "state" degraded group)
  .logs_failed: bool         fetch_logs() could not read a single group
  .wallet_failed: bool       fetch_wallet() failed in whole or in part
  .blockscout_truncated: bool see above
  .log_group_failed: dict[str, bool] keyed by LOG_GROUPS =
      ("deposits","first_deposits","hour_saved","settled","rescued","launched")
Map these onto CURATOR_DEGRADED_GROUPS ("state","logs","wallet"): state|config -> "state",
logs|log_group_failed -> "logs", wallet -> "wallet".

MODULE-LEVEL (all exported): STATE_RPC_PRIMARY="https://ethereum-rpc.publicnode.com",
STATE_RPC_FALLBACKS=[tenderly, rpc.mevblocker.io], LOG_RPCS=[tenderly, eth.drpc.org],
BLOCKSCOUT_BASE="https://eth.blockscout.com/api/v2", USER_AGENT, LOG_PAGE_BLOCKS=2000,
LOG_GROUPS, MAX_TIMESTAMP_BLOCKS=40, MAX_BLOCKSCOUT_PAGES=400,
decode_view(sel_name: str, raw: Any) -> tuple[Any, ...] | None  (drives off VIEW_RETURN_TYPES; returns
None for a missing, non-string or SHORT payload — a reverted call comes back "0x" and decoding that as
zeros would manufacture a reading out of a failure).

*** THE ONE GAP WP5 MUST OWN, AND wp5.md DOES NOT MENTION IT ***
The client hands back RAW log dicts. Nothing in the tree turns them into the DepositEvent objects that
READING_KEYS["deposits"] demands, nor into the first_deposits / hour_saved dicts, nor into
rescued_total_wei. curator_signals only CONSUMES DepositEvent; curator_client only groups raw rows;
wp5.md tasks WP5.1-WP5.13 never name a decoder. WP5 owns it. The vendored ABI
(maxpane_dashboard/abis/curator/whitelist_curator.json) gives the layout:
  Deposited(contributor address INDEXED, hour uint256 INDEXED, then DATA words in order:
      amount, creditedDelta, weightAdded, newWeight, txCount, hourTotal, earlyBps)
      -> topics[1]=contributor, topics[2]=hour; 7 data words. DepositEvent takes raw words only,
         nothing derived; ts comes from the row's own blockTimestamp; ts=None renders "--:--", never 00:00.
  FirstDeposit(contributor address INDEXED, index uint256 INDEXED, timestamp uint256 DATA)
      -> {"contributor","index","ts"}; index is 1-based and maxes at exactly totalContributors.
  HourSaved(savior address INDEXED, hour uint256 INDEXED, hourTotal uint256 DATA)
      -> {"hour","wallet","ts"}. Never fired on chain.
  Settled(hour uint256 INDEXED, timestamp/totalContributors/totalVolume DATA) -> fills SettlementRecord's
      last four fields if it ever appears. isSettled() is DERIVED, so it can flip with no log at all —
      the latch must not wait for this event.
  Rescued(to address INDEXED, amount uint256 DATA) -> sum the amounts into rescued_total_wei. Never fired.
  Launched(launchTime, hourlyThreshold, gracePeriod, hourDuration, minDeposit, minEscalation, creditCap —
      all DATA, no indexed fields).
Decode with data/evm_abi's decode_uint / decode_address / strip0x, the same helpers the client uses.

=====================================================================
2. maxpane_dashboard/analytics/curator_signals.py  (WP3) — the seam
=====================================================================
THE INPUT SEAM. READING_KEYS is a 22-tuple and it IS defined here (wave 1 correctly flagged that neither
READING_KEYS nor SIGNAL_OUTPUT_KEYS existed at freeze time; both now do, hand-typed rather than derived).
Uniform outage encoding across every entry: None = the read failed. [] / () = the read succeeded and found
nothing. 0 is a measurement. A MISSING key is treated exactly like None, so a caller that has not
implemented a tier yet degrades one row instead of raising.
  fast tier:   settled (bool|None), current_hour, hour_needed_wei (0 is REAL), hour_seconds_left (never 0),
               early_bps, volume_wei, contributors, tx_count, forced_balance_wei
  once tier:   launch_time, grace_period, hour_duration, hourly_threshold_wei, first_judged_hour,
               points_per_eth, credit_cap_wei
  logs tier:   deposits (list[DepositEvent]|None), first_deposits (list[dict]|None),
               hour_saved (list[dict]|None), rescued_total_wei (int|None, 0 is REAL)
  manager-held: settlement_record (SettlementRecord|None — the latch, not a read),
                wallet_state (WalletState|None — None when no wallet is configured)
NOTE the fast tier deliberately has NO current_hour_total_wei and NO last_active_hour: hour totals are
folded from the logs alone (H2). Do not add a state read into the fold path.

MANAGER_OWNED_KEYS = ("degraded", "as_of_hhmm", "as_of") — the three flat-dict keys build_signals does NOT
produce. WP5 adds exactly these and nothing else.
SIGNAL_OUTPUT_KEYS — 46 keys, always all of them, every call.

THE ENTRY POINT
  build_signals(readings: Any, *, now_ts: float) -> dict
    Emits exactly SIGNAL_OUTPUT_KEYS. Total over hostile input: a non-dict `readings` is treated as {},
    every internal call is guarded, and the six list keys (leaderboard_rows, activity_rows,
    closest_call_rows, cluster_rows, volume_series, contributors_series) default to [] while every scalar
    defaults to None. THIS IS THE PRESENTATION BOUNDARY: wei becomes ETH here, once. Nothing downstream
    divides again.
    Behaviour WP5 depends on:
      * The settlement LATCH beats the live read: if readings["settlement_record"].settled is True, out
        ["settled"] is True regardless of the live isSettled(), and settled_hour / settled_at_ts /
        settled_observed_at are filled from the record.
      * sig_settled_state: "fired" while the observation is younger than FIRED_TTL_S (86400 s), then
        "watch"; "ok" when settled is False; None when settled is None.
      * has_logs = isinstance(readings["deposits"], (list, tuple)). When False, survival is NOT computed
        (survival_streak_hours stays None rather than 0) and clusters_count stays None. This is the
        1ba8370 fix — state and logs sit on different endpoint pools, so live-state/dead-logs is the
        expected outage, not a corner.
      * Totals prefer the contract's own counters (contributors / tx_count / volume_wei) and fall back to
        the fold only when the counter is None AND has_logs.

PURE FUNCTIONS WP5 MAY CALL DIRECTLY (all in __all__, all total over None):
  derive_phase(*, now_ts, launch_time, grace_period, settled, current_hour) -> str|None
      One of PHASES ("grace","judged","settled"). settled is True -> "settled" even with everything else
      missing. settled is None -> None, never a guess. hour 0 is never judged. The grace boundary itself
      belongs to "judged".
  grace_seconds_left(*, now_ts, launch_time, grace_period) -> int|None   (0 = grace finished; never negative)
  grace_ends_utc(launch_time, grace_period) -> str|None                  ("YYYY-MM-DD HH:MM:SS UTC")
  lived_desc(launch_time, end_ts, *, settled=False) -> str|None          ("alive 4 h" / "lived 3 h 12 m")
  points_for_weight(weight_wei, points_per_eth) -> int|None              (isqrt(w)*rate//1e9, MULTIPLY FIRST)
  weight_added(credited_delta_wei, early_bps) -> int|None                (delta*bps//10000, floored)
  credited_delta(amount_wei, old_high_water_wei, credit_cap_wei) -> int|None
                                                                         (min(a,cap)-min(old,cap), >=0)
  fold_deposits(deposits, first_deposits, *, points_per_eth) -> list[ContributorRow]
      Sorted by points desc, weight desc, first_index asc, address — total and deterministic.
  bucket_start_ts(hour, launch_time, hour_duration) -> int|None
  hourly_buckets(deposits, *, launch_time, hour_duration, first_judged_hour, hourly_threshold_wei)
      -> list[HourBucket]. DENSE (a silent hour is present at volume_wei=0). There is deliberately NO
      parameter through which a state read could enter.
  survival(buckets, *, current_hour, hourly_threshold_wei, first_judged_hour=None) -> dict with keys
      {"streak_hours", "closest_call_hour", "closest_call_margin_wei", "closest_calls"} where
      closest_calls is a list of (hour, volume_wei, margin_wei, savior) ascending by margin, ties by hour.
      The judged window is [first_judged_hour, current_hour-1]; the in-progress hour is NEVER judged.
  at_risk_state(*, phase, needed_wei, seconds_left, first_judged_hour) -> tuple[str|None, str]
      (state, detail). detail is ALWAYS a non-empty string. None NEVER lights an alarm.
      Red below AT_RISK_RED_SECONDS=900. A deficit with an unreadable clock is "watch", not "fired".
  find_clusters(deposits, contributors, *, min_size=3, max_block_span=32) -> list[dict] with keys
      {"size","amount_eth","first_block","last_block","points","points_share_pct"}
  cluster_members(deposits, *, min_size=3, max_block_span=32) -> set[str]  (lowercase addresses)
  newest_whale(deposits, *, now_ts, min_eth=25.0, window_s=3600.0) -> dict|None with keys
      {"amount_wei","wallet","age_s","block_number","tx_hash"}. A deposit whose ts could not be read is
      EXCLUDED, never treated as now.
  you_quote(wallet_state, rows, *, points_per_eth, early_bps, credit_cap_wei)
      -> (rank, points, credit_eth, required_next_eth, marginal_points). has_joined is False -> rank,
      points and credit are None (a stranger is not a wallet scoring zero) while required_next and its
      marginal points are still reported.
  Tunables: WHALE_MIN_ETH, WHALE_WINDOW_S, CLUSTER_MIN_SIZE, CLUSTER_MAX_BLOCK_SPAN, AT_RISK_RED_SECONDS,
  FIRED_TTL_S, LEADERBOARD_LIMIT=10, ACTIVITY_LIMIT=40, CLOSEST_CALL_LIMIT=10, CLUSTER_LIMIT=10.
  States: STATE_OK="ok", STATE_WATCH="watch", STATE_FIRED="fired". PHASES is RE-EXPORTED from
  curator_models (the same tuple object, not a copy) so a consumer has one import site.

WP5's WP5.11 assertion `set(manager._readings(...)) == set(READING_KEYS)` will pass against the tuple above.
The deferred bite-proof wave 1 asked for is DONE and green: WP0's
tests/data/test_curator_models.py::test_signal_output_keys_are_a_subset_of_curator_keys now RUNS
(no longer skipped) and passes.

=====================================================================
3. maxpane_dashboard/widgets/curator/  (WP4) — what WP6 composes
=====================================================================
Import surface is the package root: `from maxpane_dashboard.widgets.curator import ...`.
Seven widgets, all `Vertical` subclasses, all render-only, all taking primitives.
Each `update_data(...)` ends in `**_kwargs`, so THE SCREEN MAY SPLAT THE WHOLE FLAT DICT AT EVERY WIDGET:
`widget.update_data(**payload)` is the intended call. Every widget also has `on_resize`; three have
`on_mount`. Nothing needs an id from the screen except CSS placement.

  CuratorHero — hero row, full width, height 8 (inner #curator-hero-boxes is 7). Three boxes with ids
    curator-hero-clock / curator-hero-list / curator-hero-curve, each 1fr.
    update_data(phase, current_hour, grace_seconds_left, grace_ends_utc, hour_fed_eth, hour_needed_eth,
      hour_seconds_left, hourly_threshold_eth, settled_hour, settled_at_ts, settled_observed_at,
      lived_desc, early_multiplier_x, points_per_eth_now, survival_streak_hours,
      closest_call_margin_eth, closest_call_hour, contributors_total, deposits_total,
      volume_routed_eth, top_points)
    Tier widths PER BOX: full 26 / compact 21 / minimal 18 (TIER_WIDTHS). Exports PHASE_UNAVAILABLE.
  CuratorLeaderboard — middle left. update_data(leaderboard_rows, you_address).
    Tiers full 48 / compact 42 / minimal 32. Exports LEADERBOARD_TITLE "TOP OF THE LIST",
    LEADERBOARD_EMPTY "no contributors yet", LEADERBOARD_UNAVAILABLE "leaderboard unavailable".
  CuratorSparklines — rail top. update_data(volume_series, contributors_series, hourly_threshold_eth).
    Exports SPARKLINES_TITLE "TRENDS", WAITING "waiting for data...".
  CuratorSignals — rail bottom, SEVEN rows + title. update_data(phase, settled, settled_hour,
      sig_settled_state, sig_at_risk_state, first_judged_hour, hour_needed_eth, hour_seconds_left,
      last_saved_hour, last_saved_wallet, last_saved_age_s, whale_amount_eth, whale_wallet, whale_age_s,
      clusters_count, flagged_points_share_pct, forced_eth, rescued_total_eth, you_rank, you_points,
      you_credit_eth, you_required_next_eth, you_marginal_points).
    SIGNAL_KEYS = ("settled","at_risk","hour_saved","whale","clusters","forced_eth","you") and
    SIGNAL_LABELS = ("SETTLED","HOUR AT RISK","HOUR SAVED","WHALE","FARM","FORCED ETH","YOU"), 1:1, render
    order, `you` LAST. There is no `rescued` row — rescued_total_eth renders INSIDE FORCED ETH.
    SIGNALS_FULL_WIDTH = 82 (this is the corrected number; the wp4 hand-off published 76, at which the
    rail silently dropped "next >= 4.10 ETH (+120 pts)"). Exports UNKNOWN_GLYPH (hollow circle, distinct
    from ok's filled one), NEVER_SAVED "none yet", NO_WALLET "set MAXPANE_WALLET", SIGNALS_TITLE.
    A fixed-height rail loses its LAST row first, so give it room for all seven.
  CuratorActivity — bottom left. update_data(activity_rows).
    Widths FULL 74 / COMPACT 64 / NARROW 44 / MINIMAL 36 / FLOOR 27. Exports ACTIVITY_TITLE "ACTIVITY",
    ACTIVITY_EMPTY "no deposits yet", ACTIVITY_UNAVAILABLE "activity unavailable".
  CuratorClosestCalls — bottom right, `c` swap slot A.
    update_data(closest_call_rows, first_judged_hour, grace_ends_utc). Tiers 42 / 31 / 18.
    Exports CLOSEST_CALLS_TITLE "CLOSEST CALLS", NO_JUDGED_HOURS "no judged hours yet",
    CLOSEST_CALLS_UNAVAILABLE.
  CuratorClusters — bottom right, `c` swap slot B.
    update_data(cluster_rows, clusters_count, flagged_points_share_pct). Tiers 45 / 33 / 23.
    Exports CLUSTERS_TITLE "FAN-OUT PATTERNS", CLUSTERS_EMPTY "no fan-out patterns found",
    CLUSTERS_UNAVAILABLE. Pattern-only language: nothing here accuses anyone.
  Shared from ._fmt (re-exported at the package root): ADDR_COLS=11, DASH="--", EMDASH, NO_STAMP="--:--".

KEY COVERAGE, verified programmatically: the union of the seven update_data kwarg sets covers 46 of the 49
CURATOR_KEYS. The three it never consumes are exactly the manager-owned health keys — degraded,
as_of_hhmm, as_of — which the SCREEN renders in the title bar (CURATOR_DEGRADED_GROUPS renders verbatim).
The only kwarg not in CURATOR_KEYS is `you_address` on CuratorLeaderboard. This confirms wave-1
amendment 1: _SCREEN_SUPPLIED is exactly {you_address}; hourly_threshold_eth and first_judged_hour are
dispatched from the payload like every other key, and neither is derivable (ethNeededThisHour() returns 0
through ALL of grace and on any already-safe judged hour, so hour_fed + hour_needed does not reconstruct
the threshold).

WP6 also inherits the house rules that bit hardest here: escape third-party strings with
widgets/markup_safety.safe_markup, assert against _compositor.render_strips() not the content string,
inherit screens/refresh_guard.RefreshGuard rather than hand-rolling run_worker(exclusive=True), and
remember that the widget widths above are MEASUREMENTS against the state the data is normally in — the
app-wide FULL_LAYOUT_COLUMNS is currently FWA's 143 and any curator number must be measured, not assumed.

=====================================================================
4. HOUSE RULES THAT ARE ALREADY ENCODED — do not undo them
=====================================================================
* A failed read is None, never 0. This contract has THREE legitimate zeros that must survive untouched:
  currentHourTotal() at a boundary, ethNeededThisHour() during grace or on a safe hour, and creditedDelta
  above the 1000 ETH cap (which still counts FULLY toward hourly survival — nothing may divide by it).
* Wei is an integer. Assert wei with ==; pytest.approx belongs only on the ETH floats build_signals emits.
* The balance is always forced ETH. It must never reach a volume, TVL or hero total; expected rendering is
  an em dash, and volume copy is "routed (all refunded)" — the strings TVL / locked / at risk / capital
  next to a volume field are scanned for and forbidden.
* Two endpoint pools, never crossed. Classify RPC errors on MESSAGE TEXT, not code. Never adopt a
  provider's suggested retry range — halve the window.
* Inject the clock everywhere (now= / now_ts / clock= / now_fn=). No test may open a socket.

