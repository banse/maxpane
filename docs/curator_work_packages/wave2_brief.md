# Wave-2 brief — the frozen interface

Written by the wave-1 gate agent after WP0 landed and the full suite went green
(3608 passed, 0 failed). This is what a WP2 / WP3 / WP4 agent needs in order to start
**without reading WP0's source**. Where this file and any older document disagree, this
file wins for names and shapes, and `maxpane_dashboard/data/curator_models.py` wins over
this file.

---

WAVE-2 BRIEF — everything you need without reading WP0's source.

IMPORT PATHS
  maxpane_dashboard/data/curator_models.py    — PHASES, SIGNAL_ROWS, CURATOR_KEYS, CURATOR_ROW_KEYS, CURATOR_SERIES_KEYS, CURATOR_ACTIVITY_KINDS, CURATOR_SIGNAL_STATES, CURATOR_DEGRADED_GROUPS, 8 dataclasses. Stdlib-only.
  maxpane_dashboard/data/curator_addresses.py — addresses, deployment pins, 6 TOPIC_*, 28 SEL_*, 4 ordered selector tuples, VIEW_RETURN_WORDS, VIEW_RETURN_TYPES, TOPIC_PREIMAGES, SELECTOR_PREIMAGES.
  maxpane_dashboard/abis/curator/whitelist_curator.json — the vendored ABI.
  tests/curator_fixtures.py — CURATOR_FIXTURES, CAPTURES, LIVE (Paths); capture(name)->Any, capture_text(name)->str, live_bundles()->list[Path] (may be EMPTY; never assert a count).
  tests/data/test_curator_models.py — CONSTRUCTOR_KWARGS: dict[type, tuple[str,...]]. Import it and assert the kwargs YOUR code passes.

PHASES = ("grace", "judged", "settled") — one tuple; a fourth spelling anywhere is a silent fallback arm.
SIGNAL_ROWS = ("settled", "at_risk", "hour_saved", "whale", "clusters", "forced_eth", "you") — 7 rows, render order, ends in `you` (NOT `rescued`; rescued_total_eth renders inside the FORCED ETH row). `you` is last and a fixed-height rail loses its last row first — pin all seven against the compositor.
CURATOR_ACTIVITY_KINDS = ("deposit", "joined", "saved") — size the activity `kind` cell from max(len(k)) via a TEST-SIDE import; widgets may not import data/.
CURATOR_SIGNAL_STATES = ("ok", "watch", "fired") — plus None = unknown, which renders unavailable, never "ok".
CURATOR_DEGRADED_GROUPS = ("state", "logs", "wallet") — the title bar renders these verbatim.
CURATOR_SERIES_KEYS = ("volume_series", "contributors_series") — [ts, value] pairs, through data/series_points.coerce_points.

DATACLASSES (all frozen, slots=True; field tuple == CONSTRUCTOR_KWARGS entry, in this order):
  CuratorState(settled, current_hour, current_hour_total_wei, hour_needed_wei, hour_seconds_left, last_active_hour, last_active_hour_total_wei, early_bps, volume_wei, contributors, tx_count, forced_balance_wei, block_number=None) — every field independently failable to None; `settled` is bool|None and True/False/None are three distinct states, only True may render SETTLED.
  CuratorConfig(launch_time, hourly_threshold_wei, grace_period, hour_duration, min_deposit_wei, min_escalation_wei, credit_cap_wei, first_judged_hour, points_per_eth, deployer) — deployer is a str address (decode_address).
  WalletState(address, points, weight_wei, contributed_wei, tx_count, first_hour, has_joined, required_next_wei) — first_hour is ALREADY un-shifted (firstHourOf()'s word 0); has_joined is word 1.
  DepositEvent(contributor, hour, amount_wei, credited_delta_wei, weight_added_wei, new_weight_wei, tx_count, hour_total_wei, early_bps, block_number, tx_hash, log_index, ts=None) — raw words only, nothing derived; (tx_hash, log_index) is the de-dupe key; ts=None renders "--:--", never "00:00".
  LogSweep(from_block, to_block, deposits=(), first_deposits=(), hour_saved=(), settled=(), rescued=(), launched=()) — groups hold RAW log dicts (topics/data/blockNumber/transactionHash/logIndex intact); () means "read, nothing matched" OR "this one filter failed" (per-group failure travels out-of-band in the client's `log_group_failed` dict); a sweep where EVERY group failed returns None instead of a LogSweep.
  ContributorRow(address, weight_wei, credit_wei, tx_count, first_hour, first_index, points=None) — points stays None until the curve is applied; credit_wei is the high-water mark, not gross; first_index is FirstDeposit's 1-based index and maxes at exactly totalContributors.
  HourBucket(hour, volume_wei, deposits, judged, saved_by=None) — judged is False for the in-progress hour and for every hour before firstJudgedHour.
  SettlementRecord(settled, block_number, observed_at, settled_hour=None, settled_at_ts=None, total_contributors=None, total_volume_wei=None) — first three are the latch observation; last four are filled from the Settled log if it ever appears.

CURATOR_KEYS — 49 keys, exactly:
  phase, settled, settled_hour, settled_at_ts, settled_observed_at, lived_desc,
  current_hour, hour_fed_eth, hour_needed_eth, hour_seconds_left, grace_seconds_left, grace_ends_utc,
  hourly_threshold_eth, first_judged_hour,
  early_multiplier_x, points_per_eth_now, survival_streak_hours, closest_call_margin_eth, closest_call_hour,
  contributors_total, deposits_total, volume_routed_eth, top_points,
  last_saved_hour, last_saved_wallet, last_saved_age_s, whale_amount_eth, whale_wallet, whale_age_s,
  clusters_count, flagged_points_share_pct, forced_eth, rescued_total_eth, sig_settled_state, sig_at_risk_state,
  you_rank, you_points, you_credit_eth, you_required_next_eth, you_marginal_points,
  leaderboard_rows, activity_rows, closest_call_rows, cluster_rows, volume_series, contributors_series,
  degraded, as_of_hhmm, as_of
The manager always emits ALL of them; a total failure returns the full contract with every value None/[]. Models are wei-native; the flat dict is the presentation boundary (ETH floats), and the manager divides exactly once.

CURATOR_ROW_KEYS (widgets index these directly; every amount is already ETH):
  leaderboard_rows: (rank, address, points, credit_eth, tx_count, flagged)
  activity_rows:    (ts, address, amount_eth, credited_eth, new_weight, tx_count, hour, kind, tx_hash, log_index)
  closest_call_rows:(hour, volume_eth, margin_eth, savior)
  cluster_rows:     (size, amount_eth, first_block, last_block, points, points_share_pct)

TWO-WORD (and three-word) RETURN SHAPES — a scalar decode of any of these is a silent bug:
  SEL_LAST_ACTIVE_HOUR -> 2 words (uint256 hour, uint256 total)
  SEL_FIRST_HOUR_OF    -> 2 words (uint256 hour, bool hasJoined)  <-- (0, False) is a stranger; (0, True) is a launch-hour founder. Reading only word 0 renders every stranger as a founder.
  SEL_STATS            -> 3 words (uint256 volume, uint256 people, uint256 txs)
  every other selector -> 1 word. VIEW_RETURN_WORDS is the machine-readable table; VIEW_RETURN_TYPES is the decode-instruction table (all 28 entries recomputed from source.sol and the ABI).
  Only two type spellings need special handling: `bool` (isSettled, firstHourOf word 1 — False must never be confused with None) and `address` (deployer -> decode_address). Every remaining type is some uintN, all left-padded into one word, all decoded identically.

SELECTOR TABLE — accessor names by tier. Each tuple is (CONSTANT_NAME, selector_hex); ORDER IS THE CONTRACT and WP2 decodes positionally:
  FAST_VIEW_SELECTORS (8, one batched eth_call every 15 s): SEL_IS_SETTLED 0x3270bb5b, SEL_CURRENT_HOUR 0x020e185d, SEL_CURRENT_HOUR_TOTAL 0x78f251f3, SEL_ETH_NEEDED_THIS_HOUR 0xa4586257, SEL_TIME_LEFT_IN_HOUR 0x7a7d6632, SEL_LAST_ACTIVE_HOUR 0xa8a036f1, SEL_EARLY_MULTIPLIER_BPS 0xd8631b3d, SEL_STATS 0xd80528ae
  ONCE_VIEW_SELECTORS (10, cached forever — nothing on this contract can change them): SEL_LAUNCH_TIME 0x790ca413, SEL_HOURLY_THRESHOLD 0x9d99a86d, SEL_GRACE_PERIOD 0xa06db7dc, SEL_HOUR_DURATION 0xda25efd9, SEL_MIN_DEPOSIT 0x41b3d185, SEL_MIN_ESCALATION 0x2c379609, SEL_CREDIT_CAP 0x1ea0466e, SEL_FIRST_JUDGED_HOUR 0x2a9c657f, SEL_POINTS_PER_ETH 0xc99a340f, SEL_DEPLOYER 0xd5f39488
  CROSS_CHECK_VIEW_SELECTORS (3): SEL_TOTAL_VOLUME 0x5f81a57c (uint128), SEL_TOTAL_CONTRIBUTORS 0xf251fc8c (uint64), SEL_TOTAL_TX_COUNT 0x9b4f50e7 (uint64) — packed slot; stats() widens the same three to uint256, which is why the type tables disagree while the values agree.
  WALLET_VIEW_SELECTORS (6, only when a wallet is set; each is selector + encode_address(wallet)): SEL_POINTS_OF 0xcf6a4403, SEL_WEIGHT_OF 0xdd4bc101, SEL_CONTRIBUTED_BY 0x64a8e570, SEL_TX_COUNT_OF 0x662d7299, SEL_REQUIRED_NEXT 0xa5f88754, SEL_FIRST_HOUR_OF 0xc5148173
  NOT a member of any ordered tuple (adding it would shift every positional decode): SEL_PREVIEW_POINTS 0x27ca8273 = previewPoints(uint256).
  DELIBERATELY NOT VENDORED: the raw contributors(address) struct getter — it carries the firstHour+1 offset. Use firstHourOf().
  fast + once + cross-check == the 21 parameterless calls of captures/batch.json.

TOPICS (topic0; preimages in TOPIC_PREIMAGES): TOPIC_LAUNCHED 0x1a3476a1..., TOPIC_DEPOSITED 0xb8385097..., TOPIC_FIRST_DEPOSIT 0xe5a1ae96..., TOPIC_HOUR_SAVED 0xab7cfcae..., TOPIC_SETTLED 0x0b88c5bd..., TOPIC_RESCUED 0x8aec0ce3....
  Deposited's indexed topics are (contributor, hour) — the hour comes off topic 2, so hour bucketing needs NO timestamp; its wall clock is launchTime + hour*hourDuration, exact by construction.

ADDRESSES / PINS:
  CURATOR = 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91 (the EIP-55 checksum the chain returns; wp0.md quotes a non-checksummed hand-retype — the chain wins)
  DEPLOYER = 0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7 (surfsurf.eth), ANNOUNCE = 0x200E710aCAA6A93bbc77146026328C40F1d60fB1, ZERO_ADDRESS.
  KNOWN_LABELS is an ALLOWLIST keyed by lowercase address; anything absent renders dimmed and truncated, never styled as known.
  CREATION_TX = 0x240bf1a8..., CREATION_BLOCK = 25769870, LAUNCH_TIME = 1786910327 (2026-08-16 19:58:47 UTC). These are PINS, not sources — read the immutables live off the `once` tier.

CHAIN VALUES pinned by tests/data/test_curator_captures.py (do not hardcode in production; calibrate fixtures to them):
  POINTS_PER_ETH 1000 · creditCap 1000e18 · hourlyThreshold 5e18 · gracePeriod 86400 · hourDuration 3600 · minDeposit 0.05e18 · minEscalation 0.1e18 · firstJudgedHour 24 (== gracePeriod//hourDuration).
  earlyMultiplierBps at capture = 19491 = 1.9491x, NOT ~1.99x. A fixture calibrated to 1.99 silently miscomputes every derived weight.
  Grace ends launchTime+86400 = 1786996727 = 2026-08-17 19:58:47Z; earliest settlement launchTime+25*3600 = 1787000327 = 2026-08-17 20:58:47Z.
  weightAdded == creditedDelta * earlyBps // 10_000, floored — holds for all 231 captured Deposited rows; witness 0.05 ETH at 19975 bps -> 0.099875 ETH. Assert wei-exact `==`; pytest.approx on a wei value is a review failure.
  points == (isqrt(weight) * 1000) // 10**9 — multiplication before division, floored.

FIVE POST-FREEZE AMENDMENTS (2026-08-17) that OVERRIDE the WP briefs if you read them before that date:
  1. CURATOR_KEYS GAINED hourly_threshold_eth and first_judged_hour. wp4.md:412's `_SCREEN_SUPPLIED` is now exactly {you_address} — drop the other two from it and dispatch them from the payload like every other key. Neither is derivable: ethNeededThisHour() returns 0 through ALL of grace AND whenever a judged hour is already safe (source.sol:547), so hour_fed_eth + hour_needed_eth does NOT reconstruct the threshold (the capture shows 734.61 ETH fed against a 5 ETH bar with the view answering 0).
  2. SIGNAL_ROWS's seventh row is `you`, not `rescued`.
  3. you_credit_eth STAYS a key and must reach CuratorSignals — the honest YOU line is `rank · pts · credit · next >=`. wp6.md:31's kwarg table omits it, so WP6.1's totality assertion is red as written. Do NOT close that gap by deleting the key.
  4. VIEW_RETURN_TYPES was wrong for the three cross-check counters (uint128/uint64/uint64, not uint256); all 28 entries are now recomputed from source.sol and the vendored ABI.
  5. CURATOR_ACTIVITY_KINDS / CURATOR_SIGNAL_STATES / CURATOR_DEGRADED_GROUPS are new — use them instead of retyping vocabularies (the dev/ops cell-sizing defect).

THREE PLACES A DOC AND THE CHAIN DISAGREED (chain won):
  - CURATOR's checksum (above).
  - The sweep holds 231 Deposited logs, not 226 (1 Launched + 231 Deposited + 145 FirstDeposit = 377).
  - H14/A4's premise is FALSE: every captured log DOES carry a block timestamp (RPC `blockTimestamp`, Blockscout `block_timestamp`). The eth_getBlockByNumber batch is a FALLBACK, not the only provenance. A missing stamp still renders "--:--", never "00:00".

CAPTURES
  Root tests/fixtures/curator/ holds DIRECTORIES ONLY (a test enforces it). WP0 owns captures/ (18-file named required set — never a count). WP1 owns captures/live/ and it GROWS while you build; never assert a count there. Put your own slices under tests/fixtures/curator/client/ | signals/ | screen/.
  Read them with tests.curator_fixtures.capture()/capture_text(). Shapes that trip people: tenderly_logs.json is the FULL JSON-RPC envelope (rows are ["result"]); batch.json/results.json are bare 21-item lists correlated BY `id`, never by position (isSettled() and ethNeededThisHour() BOTH returned 0x0, so positional reasoning cannot tell them apart); bs_page_*.json are {"items","next_page_params"}; hour_boundary_h1_h2.json is {"meta","views","samples"}.
  The 2026-08-16 research captures span 21:04-21:14 UTC and DISAGREE WITH EACH OTHER BY DESIGN (results.json: 143 contributors / 222 txs; tenderly_logs.json: 145 FirstDeposit / 231 Deposited). Cross-instant assertions belong on a live BUNDLE, where every section was fetched in the same second — e.g. 20260816T225006Z_grace-late.json reconciles 1282==1282 and 794==794.
  WP3, GOOD NEWS that changes wp3.md as written: the sqrt curve now HAS an onchain witness. tests/fixtures/curator/captures/live/20260816T225143Z_curve-probe.json holds previewPoints(uint256) over 12 weights plus pointsOf/weightOf over 4 real wallets, all 20 calls answered, every return equal to (isqrt(w)*1000)//10**9 (0, 1, 1e9-1 and 1e9 all floor to 0 points; 1e18->1000; 1000e18->31622). Assert against it IN ADDITION TO the Newton transcription; the transcription differential stays.
  WP2/WP3, H2's evidence: 20260817T000322Z_grace-late.json folds Deposited by the indexed hour topic to hour 0: 851.89, hour 1: 9987.26, hour 2: 2263.83, hour 3: 2738.92 ETH — wei-exact against three independent state reads taken seconds before each hour closed. The fold reproduces currentHourTotal() for every COMPLETED hour and does not collapse at a boundary.

HOUSE RULES THAT BITE HARDEST HERE
  A failed read is None, never 0 — and this contract has THREE legitimate zeros: currentHourTotal() at a boundary, ethNeededThisHour() during grace or a safe judged hour, creditedDelta above the 1000 ETH cap (which still counts FULLY toward hourly survival; nothing may divide by it).
  timeLeftInHour() returns hourDuration, never 0, at an exact boundary (observed 3600 at the top of an hour). It steps in ~12 s jumps because eth_call runs against the latest block, so state trails wall clock by up to one block.
  The in-progress hour is NEVER judged (_isShort returns false while lastActive == hour).
  The contract's balance is ALWAYS forced ETH, never deposits — every wei is refunded in-tx. It feeds forced_eth only and must never reach a volume, TVL or hero total; expected rendering is an em dash. Volume is gas-priced: the honest copy is "routed (all refunded)"; the strings TVL / locked / at risk / capital next to a volume field are scanned for and forbidden.
  Two endpoint pools, never crossed: ethereum-rpc.publicnode.com for state (it batches but REFUSES archive eth_getLogs); gateway.tenderly.co/public/mainnet and eth.drpc.org for logs. Banned hosts: eth.llamarpc.com, rpc.ankr.com, cloudflare-eth.com, api.reservoir.tools, *.alchemy.com, infura.io, any etherscan.io. Set a real User-Agent — publicnode 403s python-urllib's default. Classify RPC errors on MESSAGE TEXT, not code (-32602/-32005 are reused); never follow a provider's suggested range — halve the window.
  Inject the clock (now= / now_ts / clock=). No network in any test — inject a transport that raises. Widgets never import data/ or analytics/ (AST-checked). Sparklines import widgets/sparkline_common. Escape with widgets/markup_safety.safe_markup. Assert against _compositor.render_strips(). Prove your test bites.

OWNERSHIP: WP2 owns data/curator_client.py + tests/data/test_curator_client.py + tests/fixtures/curator/client/. WP3 owns analytics/curator_signals.py + tests/analytics/test_curator_signals.py + tests/fixtures/curator/signals/. WP4 owns widgets/curator/* + tests/widgets/test_curator_widgets.py. curator_addresses.py and curator_models.py are READ-ONLY to all three — if a selector or field is missing, report it with the preimage, do not add it. app.py, __main__.py, game_select.py, minimal.tcss, README.md and CLAUDE.md are WP7's alone. Stage explicit paths only; never `git add -A`, never `git checkout --`.

---

## Still open from wave 1

- Capture A (quiet hour crossing: currentHourTotal()==0 while lastActiveHour() still names the previous hour) is STILL MISSING. Hunted three times — 21:58:47, 22:58:47 and 23:58:47 UTC on 2026-08-16 — and missed all three because during grace a deposit lands within seconds of every boundary (fresh-hour readings were 51.48, 83.41 and 7.07 ETH). Retryable at every HH:58:47 UTC and it gets EASIER post-grace, when a near-empty hour is the normal case. Until it lands, the stale-lastActiveHour decode path ships against a synthetic (results.json with two words changed). The volume-drop half of H2 IS real and captured (hour_boundary_h1_h2.json plus the ...T225848Z/...T225852Z and ...T235846Z/...T235850Z pairs).
- Capture B (post-grace / judged hour with a live deficit) is MISSING; its window is TODAY, 2026-08-17 19:58:47 UTC. Until it lands, the JUDGED phase, the flat earlyBps==10000 branch and the yellow/red HOUR AT RISK states are all fixture-less — WP3 and WP4 build them against synthetics that MUST carry the literal comment '# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>'.
- Capture C (the settlement transition) is MISSING; earliest window is TODAY, 2026-08-17 20:58:47 UTC, and it is one-shot and unrepeatable forever — isSettled() is derived, so it flips with no transaction and no log. Both halves are needed (last bundle reading 0x0, first reading 0x1) or WP5's latch test cannot be exercised. Runbook: tests/fixtures/curator/captures/live/README.md, section 'The two windows on 2026-08-17'.
- HourSaved and Rescued have never fired on chain and may never. Their rows must render an explicit never-fired state; do not block on a payload.
- WP1.3's two commit/ledger checkboxes in docs/curator_work_packages/wp1.md (lines 192-193) are unticked although the commits exist (dec4b69, 338faf2) — stale bookkeeping only, no code impact. WP1.7 (the `rg "SYNTHETIC — re-point"` close-out) is open by design; WP7.13 closes it.
- MINOR, and wave 2 must know: READING_KEYS and SIGNAL_OUTPUT_KEYS are NOT frozen by WP0, despite docs/curator_implementation_plan.md's 'The frozen interface' item 2 saying READING_KEYS is pinned on both sides. Neither name exists anywhere in the tree. WP3 owns and must define both in analytics/curator_signals.py, and WP3.12's hand-off note (READING_KEYS verbatim, with each key's outage encoding: None = the read failed, []/() = read succeeded and found nothing) is a hard prerequisite for WP5 in wave 3, which asserts set(manager._readings(...)) == set(READING_KEYS).
- MINOR: the ORDER of FAST_/ONCE_/CROSS_CHECK_/WALLET_VIEW_SELECTORS is deliberately NOT tested by WP0 — swapping two entries leaves the WP0 suite green, and that was verified. WP2.4 owns that test and must assert it against VIEW_RETURN_WORDS. Until WP2.4 lands, a positional decode swap is undetectable.
- MINOR: WP3 must NOT edit tests/data/test_curator_models.py (WP0's file). When curator_signals.py lands, run `-k subset -v -rs` and confirm that test flips SKIPPED -> PASSED, then perform the deferred bite-proof: rename one SIGNAL_OUTPUT_KEYS entry, watch it FAIL naming the key, restore. If it still SKIPS, importorskip's path is wrong and the guard has been dead the whole time.
