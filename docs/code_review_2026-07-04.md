# MaxPane — Full Code Review & Reality Check

**Date:** 2026-07-04 · **Branch:** `talismans-dashboard` (incl. uncommitted working-tree changes) · **Version:** 0.4.0

**Method:** 103 review/verification agents — 13 scoped code reviewers (one per dashboard stack + core, widgets, security, async, tests, Rust, architecture), 4 reality checkers (docs-vs-code, packaging, live endpoint probes, headless smoke run), every finding adversarially verified by 1–2 independent agents (criticals/highs verified twice, several reproduced empirically against live chain data or by execution). 78 raw findings → 73 deduped → **70 confirmed, 3 refuted**. Full test suite: **796/796 pass** in 11s.

## Verdict

The codebase is in good shape where it is hardest (ABI decoding, selectors, event topics were independently re-derived and are all correct; async/lifecycle discipline is solid; security posture is clean; packaging/publishing works). The problems cluster in four systemic patterns rather than random bugs:

1. **Silent failure sentinels** — clients convert RPC/transport failures into `0`/empty values, so managers can't distinguish "RPC down" from "value is zero"; zeros get rendered and persisted as real data.
2. **Non-idempotent event pipelines + wrong scan windows** — worst case the TTT `min()`/`max()` inversion that inflates fee numbers ~120× per hour of uptime and persists the corruption.
3. **Copy-paste propagation without backporting** — 8 near-identical stacks; hardening added in newer games (ttt/talismans) never reaches the 6 older copies (e.g. corrupt-cache crash at startup).
4. **Reality drift** — the DOTA game API is deleted (NXDOMAIN), Reservoir is sunset, the Bakery season ended 3 weeks ago but displays as current, README still advertises 6 of 8 dashboards, and CLAUDE.md describes a codebase that doesn't exist.

## Findings by severity

| Severity | Count |
|---|---|
| critical | 1 |
| high | 7 |
| medium | 40 |
| low | 22 |


## Critical (1)

### CRIT-1: `maxpane_dashboard/data/ttt_manager.py:428` — correctness (ttt)

Incremental scan window at ttt_manager.py:428 uses min(last+1, current-5000) instead of max(), so every 30s cycle rescans the last 5000 blocks (~16.7h) and re-applies all Deposited/Launched/Bought events through non-idempotent cache applicators. Fee counters (ETH to holders 24h, per-token FEES 24H/LIFETIME) inflate ~120x after one hour, plateauing near ~2000x as events age out of the window (not strictly unbounded); duplicate rows flood the 200-item activity ring buffer (capping launches_24h inflation at 200 but evicting real history); the inflated buckets are persisted to ~/.maxpane/ttt_cache.json and survive restarts. Fix: max(last + 1, current_block - _INCREMENTAL_LOG_LOOKBACK).

**Failure scenario:** Steady state: last_seen_block['Deposited'] = current_block - 2, so _from returns min(last+1, current-5000) = current-5000. Every deposit in the last 5000 blocks is re-fetched each cycle and TTTCache.apply_deposit unconditionally adds holder_share_wei to the hourly bucket (verified: applying the same event twice yields eth_to_holders_24h_wei = 2e18 for a 1e18 deposit). After 1 hour of 30s polls, 'ETH to holders 24h', per-token FEES 24H/LIFETIME, and launches_24h are ~120x their true values, the activity feed floods with duplicate rows evicting real history from the 200-item ring buffer, and the inflated fees_by_token buckets are persisted to ~/.maxpane/ttt_cache.json so the corruption survives restarts.

**Suggested fix:** Use max(last + 1 - small_reorg_margin, ...) so steady-state scans start at last+1, and/or make apply_* idempotent by deduping on (tx_hash, event_type, token, block_number) before applying.


## High (7)

### HIGH-1: `maxpane_dashboard/analytics/ev.py:7` — correctness (bakery-base)

EVTable rankings are computed exclusively from the stale hardcoded BOOST_CATALOG in ev.py while the live catalog parsed from agent.json into LiveState.active_boost_catalog is never consumed: every success rate, cost, duration, and multiplier is wrong (e.g. Ad Campaign 85%/2800/1500s live vs 60%/120/14400s hardcoded), two displayed items (Motivational Speech, Fake Partnership) no longer exist in the live game, and the live Cleanup Crew boost is missing.

**Failure scenario:** Live agent.json (fetched 2026-07-04) shows 'Ad Campaign' = 85% success (8500 bps), cost 2800 cookies, duration 1500s; the hardcoded entry says 60%, 120 cookies, 14400s (duration off by ~10x, cost by ~23x), and the live catalog has 10 entries vs 8 hardcoded. manager.py:111-112 calls rank_boosts/rank_attacks which read only this hardcoded table, so every EV and ranking shown in the EVTable widget is wrong, despite snapshot.agent_config.live_state.active_boost_catalog containing the correct data.

**Suggested fix:** Build the catalog from agent_config.live_state.active_boost_catalog (successChanceBps, cost, multiplierBps, durationSeconds are all there) and keep the hardcoded table only as a fallback.

### HIGH-2: `maxpane_dashboard/app.py:102` — crash (core)

Startup prefetch worker (app.py:102-166, all game branches) runs manager.fetch_and_compute() with run_worker's default exit_on_error=True and no exception guard, so any launch-time fetch failure (offline, DNS failure, game API 5xx) panics Textual with WorkerFailed and exits the app with return code 1 instead of showing the dashboard with an error status; affects 8 of 11 --game choices including the default 'bakery' (dota/ttt/talismans managers swallow errors internally and are immune).

**Failure scenario:** Launch `maxpane` with no network, DNS failure, or rugpullbakery.com returning 5xx: DataManager.fetch_and_compute (data/manager.py:71-75) deliberately re-raises (FrenPetManager and OCMManager do too), the 'prefetch' worker fails, and Textual panics with WorkerFailed while the splash is showing — app exits with return code 1 and a traceback instead of showing the dashboard with an error status. Confirmed empirically with a headless pilot: app._exception = WorkerFailed(RuntimeError), return_code 1. Every --game choice whose manager re-raises is affected, including the default 'bakery'.

**Suggested fix:** Wrap the prefetch coroutine in a try/except that logs the error (mirroring the screens' _do_refresh), or pass exit_on_error=False to run_worker for the prefetch workers.

### HIGH-3: `maxpane_dashboard/data/ocm_manager.py:127` — correctness (ocm-dota)

Burn Rate signal is computed from the cached totalSupply sparkline series instead of a cumulative-burn series: OCM burns (transfers to 0xdead) never reduce totalSupply, so any mint inside the ~2h cache window is displayed as burn pressure (a single mint renders "~84/week" red "high") while real burns are never counted; the intended burn plumbing (OCMCache.update_burned_count/cumulative_burned and _scan_recent_activity's burn tally) is dead code.

**Failure scenario:** compute_burn_rate() (ocm_signals.py:107) documents its input as '(timestamp, cumulative_burned) pairs', but the manager passes supply_history (totalSupply over time). OCM burns are transfers to 0xdead and never decrease totalSupply, so the supply series only grows with mints. With the default 120-sample/60s window (~2h), a single mint yields delta=1 over elapsed_weeks=0.0119 -> burn_rate ~84/week -> the Burn Rate widget shows '~84/week' with red 'high' pressure, purely from mint activity, while real burns are never counted. The plumbing that was meant to feed this (OCMCache.update_burned_count/cumulative_burned, and the burned_count returned by _scan_recent_activity) is never called anywhere.

**Suggested fix:** Track a (timestamp, burned_count) series in OCMCache from snapshot.collection.burned_count (balanceOf(0xdead) is already fetched every poll) and pass that series to compute_burn_rate; delete or wire up the dead update_burned_count plumbing.

### HIGH-4: `maxpane_dashboard/data/talismans_manager.py:240` — correctness (talismans)

Fresh installs permanently miss live post-genesis tokens created before the 250k-block log lookback (currently 92 of 182, incl. 50 of 93 Mythics): known_ids is only grown from operation logs within the lookback and the scan watermark then advances past the gap, so enumeration_complete never becomes true, the conservation baseline is never set, CONSERVATION stays SYNCING forever, the TOTAL CORES hero box permanently shows a false yellow DRIFT, Mythics are undercounted ~46%, and collectors/matrix/ledger are incomplete. (Contrary to the original claim, recent ops DO exist in the window — the '0 events' observation was a silently-swallowed RPC failure in _get_logs, a related robustness gap — so ops/activity metrics work; the defect is the undiscoverable pre-window tokens and the misleading DRIFT rendering of incomplete enumeration.)

**Failure scenario:** Verified live at block 25458767: eth_getLogs over the 250k lookback returns 0 Bonded/Cleaved/Cut/Merged events, so known_ids stays at genesis 1..1536. nextTransformId()=1756 and 182 post-genesis tokens (ids 1537-1755, 908 cores, including 6-core Mythics like #1537) are live, so a fresh install sees 1172 tokens vs totalSupply=1354. enumeration_complete is False forever, the conservation baseline is never set, CONSERVATION stays 'SYNCING', the TOTAL CORES hero box permanently shows a false yellow 'DRIFT' (tal_hero_metrics.py:143 renders intact=False as DRIFT), MYTHICS undercounts, mythics_ever_forged=0, operations_total=0, activity feed is empty, and top_collectors omits every Mythic holder. Only the developer's machine with a cache built during development shows correct data; every new user gets permanently wrong headline metrics.

**Suggested fix:** Seed known_ids from the contract's transform counter instead of relying on log lookback: read nextTransformId() (selector 0x98e1870d, verified live) each cycle and add 1537..next-1 to known_ids; the existing tokenData/ownerOf multicall sweep already filters dead ids. Alternatively scan operation logs from the contract deploy block on first run.

### HIGH-5: `maxpane_dashboard/data/talismans_manager.py:270` — correctness (talismans)

_get_logs silently drops failed eth_getLogs pages (talismans_client.py:536-543) yet _scan_operations unconditionally advances and persists last_seen_block["ops"] to current_block (talismans_manager.py:270), so any dropped chunk permanently loses Bonded/Cleaved/Cut/Merged events and their result token ids — the only id-discovery mechanism besides genesis seeding — leaving enumeration incomplete forever (conservation stuck SYNCING, hero cores box stuck on yellow DRIFT) and operations_total/mythics_ever_forged undercounted; a fallback RPC answering the 50k-block range with error -32602 even short-circuits the remaining endpoints (talismans_client.py:485-504), making the drop easier than an all-endpoint outage.

**Failure scenario:** TalismansClient._get_logs (talismans_client.py:538-543) catches per-chunk exceptions, logs at debug, and skips to the next chunk, so fetch_operation_logs never raises and the manager's try/except at line 243-248 is dead code. If one 50k-block page fails on all four endpoints (e.g. publicnode timeout plus rate-limited fallbacks during the 5-page initial backfill), _scan_operations still sets last_seen_block['ops']=current_block and persists it to ~/.maxpane/talismans_cache.json. The Bonded/Cleaved events in that range are never re-scanned: their result ids never enter known_ids, so the live token set can never match totalSupply again, conservation is stuck SYNCING, the hero shows false DRIFT, and operations_total/mythics_ever_forged are permanently undercounted.

**Suggested fix:** Make _get_logs raise (or return a (logs, last_complete_block) pair) when a chunk fails after all retries, and have _scan_operations advance the watermark only to the last fully-scanned block.

### HIGH-6: `maxpane_dashboard/data/ttt_client.py:265` — test-coverage (tests)

The TTT data layer is untested: ttt_client.py (1034 lines — the largest client, with hand-rolled _encode_aggregate3 / _decode_aggregate3_result / _decode_string_dynamic dynamic-ABI decoding and four event-log decoders), ttt_manager.py (573) and ttt_cache.py (534, JSON persistence with corruption handling) have zero tests; only the pure functions in ttt_signals are covered (35 tests).

**Failure scenario:** This is exactly the class of code that already produced the talismans dynamic-tuple decode bug (fixed in commit 3139636 with tests). An off-by-one word offset in _decode_aggregate3_result would return wrong reservoir_wei for every launched token, so buybacks-ready counts and claim math shown on the TTT screen are wrong for all users, and no test fails.

**Suggested fix:** Port the tests/data/test_talismans_client.py approach: hand-built aggregate3 return blobs (a helper already exists there), truncated/reverted returnData cases, and event-log decoder fixtures; add a ttt_cache save/load/corrupt-file round-trip like tests/data/test_cache.py.

### HIGH-7: `maxpane_dashboard/widgets/leaderboard.py:77` — crash (widgets)

Unescaped player-controlled bakery names (leader row f"[bold]{bakery.name}[/]" at leaderboard.py:71 and raw names at :75) are passed to DataTable.add_row (:77); textual 8.1.1 defers Text.from_markup to the DataTable's _on_idle -> _update_dimensions -> default_cell_formatter, so a name containing invalid Rich markup (e.g. "[/x] Bakers") raises MarkupError inside the message pump, bypassing BakeryScreen._do_refresh's try/except and crashing the entire app — persistently, on every refresh, on the app's default screen. Reproduced experimentally in the project venv. Fix: rich.markup.escape() the name (or pass Text objects). templates/leaderboard_template.py:92/95 has the same pattern but is not runtime-reachable (copy-paste template only); fix it too so new dashboards do not inherit the bug.

**Failure scenario:** getTopBakeries returns a bakery whose player-chosen name contains a mismatched Rich closing tag, e.g. '[/x] Bakers'. Leaderboard.update_data calls table.add_row(bakery.name, ...) which succeeds, but textual 8.1.1's DataTable defers Text.from_markup to _on_idle -> _update_dimensions -> default_cell_formatter (verified experimentally in the project venv: add_row succeeds, then rich.errors.MarkupError is raised inside the message pump). Because it happens outside BakeryScreen._do_refresh's try/except blocks, the unhandled exception crashes the whole app. Same pattern also on line 71 (f"[bold]{bakery.name}[/]") and in templates/leaderboard_template.py line 95.

**Suggested fix:** Wrap all API-sourced strings with rich.markup.escape() before interpolating into markup or passing to add_row: from rich.markup import escape; name = escape(bakery.name).


## Medium (40)

### MEDI-1: `CLAUDE.md:22` — architecture (architecture)

Working-tree CLAUDE.md documents a nonexistent backend/+frontend transaction-bot repo: all build/run/test commands (lines 73, 83, 91) reference paths absent from the repo (no backend/, no frontend/, no requirements.txt anywhere, no tests/strategy/), the env-var block (lines 98–107) lists ten variables none of which appear in code (including MAXPANE_KEYSTORE_PASSWORD), and line 7 asserts — above the line-13 staleness disclaimer, so unhedged — reuse of executor/transactor/keystore/nonce-management infrastructure that grep confirms exists nowhere in the tree, misdirecting agents toward key handling in a deliberately keyless read-only Textual TUI whose real entry point is `python -m maxpane_dashboard`.

**Failure scenario:** Any developer or coding agent following the checked-in instructions fails immediately: `pip install -r backend/requirements.txt` (line 73), `python -m backend.main` (line 83), and `pytest tests/strategy/` (line 91) all reference paths that don't exist (repo root contains maxpane_dashboard/, maxpane/, tests/{analytics,data,screens,widgets}). More dangerously, the doc instructs setting MAXPANE_KEYSTORE_PASSWORD (line 98+) and describes transaction-sending 'strategy' behavior (bake/boost/attack), inviting an agent to re-introduce key handling and transaction code into a project whose hard constraints are keyless and read-only. The 'Everything below this line may be outdated' disclaimer at line 13 does not cover line 7's claim of reused 'executor, transactor, keystore, nonce management' infrastructure, which is equally false.

**Suggested fix:** Rewrite CLAUDE.md to describe the actual package layout (maxpane_dashboard/{data,screens,widgets,analytics,templates,themes}), the real run/test commands, and state the keyless/read-only constraints explicitly.

### MEDI-2: `maxpane/src/intro/prompt.rs:276` — crash-tiny-terminal (rust)

PromptState::render (maxpane/src/intro/prompt.rs:276, 298, 317, 331) builds Rects sized to text length without clamping to the frame area; on terminals narrower than 33 columns the 33-char question Rect overflows the buffer and ratatui 0.29.0's Paragraph rendering hard-panics ('index outside of buffer') on the prompt's first frame, and on terminals shorter than 5 rows the response line at start_y+4 panics once an answer is shown (heights <=2 panic immediately) — aborting the app; reproduced at 25x10 and 40x4. The stored LayoutMode (Minimal exists for small terminals) is never used in render, unlike the typewriter/logo/splash screens which clamp.

**Failure scenario:** Run the intro in a terminal/pane 25 cols wide (or resize below 33 cols during the prompt): q_rect is Rect::new(0, y, 33, 1) on a 25-wide buffer; ratatui 0.29 Paragraph::render_text does raw buf[(x,y)] indexing and panics. Confirmed by probe: 'index outside of buffer: the area is 25x10 but index is (25, 3)'. Same for ShowingResponse on a 4-row terminal: resp_y = start_y+4 -> panic at (13, 4). The panic hook restores the terminal, but the app aborts. detect_layout has a Minimal mode for small terminals, yet PromptState ignores its layout field entirely — the intro does NOT handle tiny terminal sizes on this screen (logo.rs/splash.rs/typewriter.rs all clamp correctly).

**Suggested fix:** Clamp all prompt Rects like logo.rs does: width = text_width.min(area.width), skip rendering when y >= area.height (q_rect line 276, input rect line 298, frozen-input rect line 317, resp_rect line 331).

### MEDI-3: `maxpane/src/intro/prompt.rs:298` — crash-unbounded-input (rust)

Unbounded prompt input buffer plus unclamped Rect width (prompt.rs:296-298, also :317/:331 in the response branch) causes a guaranteed ratatui out-of-bounds panic — in debug and release — once the input line exceeds the terminal width (71+ buffered chars on 80 cols); no catch_unwind exists, so the intro binary crashes instead of completing, though the trigger is self-typed overlong input and a relaunch recovers.

**Failure scenario:** On a standard 80x24 terminal, type 72+ characters at the '> [Y/N]: ' prompt (e.g. holding a key for ~2 seconds): display = prefix(9) + buffer + cursor exceeds 80, x saturates to 0, Rect::new(0, y, 90, 1) is rendered and ratatui panics writing at column 80. Confirmed by probe: 'index outside of buffer: the area is 80x24 but index is (80, 12)'. Intro aborts with a panic message instead of reaching the dashboard.

**Suggested fix:** Cap input_buffer length in handle_input (e.g. 40 chars — longest easter egg is 8) and/or clamp the rendered Rect width to area.width.

### MEDI-4: `maxpane/src/theme.rs:74` — config-parse-panic (rust)

parse_hex_color (maxpane/src/theme.rs:74) validates only byte length (hex.len() == 6) before slicing at fixed byte offsets, so a 6-byte multi-byte-UTF-8 color value like "#€€" in [intro.colors] with color_scheme = "custom" panics at a char boundary ("byte index 2 is not a char boundary") during unconditional startup theme resolution in main.rs, crashing the app instead of returning None and falling back to the phosphor default as documented.

**Failure scenario:** User puts text = "#€€" ("#€€", 6 bytes after '#') under [intro.colors] in ~/.maxpane/config.toml with color_scheme = "custom": maxpane panics at startup with 'byte index 2 is not a char boundary' (confirmed by probe). The function exists specifically to validate untrusted config input and returns Option, but crashes instead of falling back to the phosphor default.

**Suggested fix:** Add `if !hex.is_ascii() { return None; }` after the length check, or use hex.as_bytes() with from_str_radix on str::from_utf8-checked slices.

### MEDI-5: `maxpane_dashboard/__main__.py:56` — cli-validation (core)

--game accepts frenpet_full/frenpet_wallet/frenpet_perf but those dashboards are unreachable at runtime: they are commented out of GameSelectScreen's menu, excluded from _GAME_CYCLE tab cycling, and the initial_game fallback at app.py:177 is dead code because Textual invokes the result callback only via Screen.dismiss(result) and the menu always dismisses with a concrete visible game id. For every --game value the app still shows the selection menu (help text 'show first' is wrong for all games), and for the frenpet variants the flag's only effect is a useless prefetch -- including extra on-chain reward calls from the new fetch_rewards=True wallet manager when a wallet address is configured -- whose results can never be displayed.

**Failure scenario:** User runs `maxpane --game frenpet_wallet` expecting the wallet dashboard (help text: 'Which game dashboard to show first'). After the splash, GameSelectScreen only offers the 8 visible games and its on_key always dismisses with a concrete game id, so app.py:177 `if game_id is None` never fires; the wallet dashboard cannot be displayed at all. Meanwhile on_mount still prefetches via _frenpet_wallet_manager (with the new fetch_rewards=True doing extra on-chain reward calls) whose results are never shown. The same applies to all --game values: none is actually 'shown first', the menu always requires manual selection.

**Suggested fix:** Either auto-launch args.game after the splash (skipping the menu when --game is given), or remove the hidden frenpet variants from the CLI choices until the views are re-enabled.

### MEDI-6: `maxpane_dashboard/analytics/cattown_conditions.py:212` — correctness (cattown)

get_competition_timing (cattown_conditions.py:210-222) uses datetime.replace(day=now.day±offset) instead of timedelta arithmetic and raises ValueError('day is out of range for month') on ~3 month-boundary days per month (75 days in 2026-2027, reproduced incl. Sat 2026-10-31 and Sun 2026-11-01). The sole caller (cattown_manager.py:127) swallows it via _safe_call at DEBUG level and substitutes is_active=False/0s, so on those dates the RPC-independent weekday countdown fallback (lines 136-137) is silently lost: when chain/API competition data is unavailable or end_time==0, the hero widget shows "Starts in 0m"/"LIVE 0m" and the recommendation says "Competition starts in 0m" instead of real countdowns. Note the LIVE/inactive status itself comes from chain data (comp.is_active), so the bug zeroes countdowns but does not flip an otherwise-reported live competition to inactive.

**Failure scenario:** Reproduced with mocked dates: Mon 2026-06-29 (day 29+5=34), Sat 2026-10-31 (sunday_end day 31+1=32, line 220), and Sun 2026-11-01 (day 1-1=0, line 217) all raise ValueError. The manager's _safe_call swallows it and substitutes {'is_active': False, seconds 0}, so whenever the chain/API competition data is unavailable on such dates the RPC-independent countdown fallback is lost and the hero widget / recommendation wrongly report no competition — notably ON a live competition Saturday like 2026-10-31. This recurs several days every month.

**Suggested fix:** Compute saturday_start = midnight(now) - timedelta(days=weekday) + timedelta(days=5) (minus 7 days when weekday==6) and sunday_end = saturday_start + timedelta(days=2) - timedelta(seconds=1); timedelta handles month/year rollover.

### MEDI-7: `maxpane_dashboard/analytics/frenpet_perf_signals.py:22` — unit-error (frenpet)

FrenPet Performance screen labels points-per-day velocities as '/hr' (fpp_pets, fpp_velocity, fpp_signals), a 24x unit misstatement inconsistent with the '/day' labels on wallet/full screens and with the genuinely per-hour trends sparkline on the same screen; the hardcoded '+' prefix also renders negative velocity as '+-N/hr'.

**Failure scenario:** calculate_velocity (frenpet_signals.py:23-54) regresses over days and returns points/day; the wallet and pet views correctly label it '/day' (pet_card.py:112, pet_signals.py:143). The perf stack treats the same values as pts/hr: compute_total_velocity docstring says 'pts/hr' and the perf widgets render f'+{velocity}/hr' (fpp_pets.py:123, fpp_velocity.py:130-132, fpp_signals.py:66-68). A pet gaining 2,400 pts/day shows '+2.4K/hr' on the Performance screen but '+2400/day' on the Wallet screen for identical data. The perf widgets also hardcode a '+' prefix, so negative velocity renders as '+-500/hr'.

**Suggested fix:** Relabel the perf widgets to '/day' (and fix the sign prefix), or divide by 24 before display; align color thresholds accordingly.

### MEDI-8: `maxpane_dashboard/analytics/signals.py:23` — correctness (bakery-base)

calculate_late_join_ev (signals.py:23) overstates the displayed Late-Join EV by multiplying top-3 probability by the FULL prize pool — ignoring the confirmed 70/20/10 split and never using its member_count parameter to divide the payout among the winning bakery's members (~90x inflation for a 30-member leader) — and DataManager computes it without season_active gating; however, the SignalsPanel only renders the ev_usd figure (the "consider joining" recommendation string is never displayed anywhere), and the claimed positive-EV-for-ended-season scenario does not reproduce live because a finalized season's pool is drained (actual output: ev_usd=-2.95, negative recommendation), so the misleading positive display only occurs during active seasons.

**Failure scenario:** Verified against the live API: with season 10 already finalized/ended, fetch_and_compute() returned late_join_ev = {'ev_usd': 9749.3, 'recommendation': 'Positive EV -- consider joining'}. The leader bakery has 30 members and payouts are 70/20/10, so a realistic per-member EV is roughly two orders of magnitude smaller — and joining a finished season has EV of exactly -buy_in. The SignalsPanel displays a 'consider joining' recommendation for a season that cannot be joined.

**Suggested fix:** Apply the 70/20/10 split weights, divide the bakery share by member_count, and have manager.py (lines 118-128) short-circuit to a 'season over' recommendation when season_active is False.

### MEDI-9: `maxpane_dashboard/app.py:51` — correctness (core)

App-level Binding("tab", "switch_game") (app.py:51) is permanently shadowed by textual 8.1.1's built-in Screen.BINDINGS entry tab->app.focus_next (screen.py:269), which sits earlier in the non-priority binding chain (focused widget -> screen -> app); Tab therefore only moves focus and never cycles games, leaving action_switch_game/_GAME_CYCLE dead code despite "tab" being advertised in the game-select hint and dashboard status bars ('m' menu remains the only working switch path).

**Failure scenario:** User opens any game dashboard and presses Tab (as promised by the game-select hint 'tab to cycle later'): focus_next runs instead, action_switch_game never executes, _current_game and the screen stack are unchanged. Confirmed empirically with a headless pilot on the bakery screen (textual 8.1.1): current_game stayed 'bakery' after Tab. _GAME_CYCLE and action_switch_game are dead code; the only way to change games is the 'm' menu.

**Suggested fix:** Use Binding("tab", "switch_game", priority=True) on the App (and consider shift+tab for reverse), or move the binding to each game screen so it precedes Screen's default, or pick a different key and fix the hint text.

### MEDI-10: `maxpane_dashboard/app.py:365` — stale-cache (core)

On quit, the three never-polled FrenPetManager instances (_frenpet_full/_wallet/_perf, closed after _frenpet_manager in action_quit at app.py:361-375) each unconditionally full-overwrite ~/.maxpane/frenpet_cache.json with their construction-time cache state (empty on first run), so the last writer (_frenpet_perf_manager) always discards all score history accumulated during the session and the cache file can never grow across sessions.

**Failure scenario:** User watches the FrenPet dashboard for an hour (only _frenpet_manager.cache accumulates score-history points), then presses q on that screen. action_quit closes managers in order: _frenpet_manager.close() persists the fresh history (frenpet_manager.py:503-511), then _frenpet_full_manager, _frenpet_wallet_manager, and _frenpet_perf_manager each call save_cache() on the same _CACHE_FILE — FrenPetCache.save_to_file (frenpet_cache.py:134-163) is a full overwrite, so the final file contains only the data loaded at construction. On the next launch the sparkline/history persistence is back to pre-session state; the cache file can never grow across sessions.

**Suggested fix:** Only persist the cache from the manager whose screen actually fetched data (e.g. track a dirty flag / last_updated and skip save when the cache was never updated), or give each manager variant its own cache file, or share a single FrenPetCache instance across the four managers.

### MEDI-11: `maxpane_dashboard/app.py:373` — architecture (architecture)

All four FrenPetManager instances (app.py:68-84) load and save the same ~/.maxpane/frenpet_cache.json; FrenPetCache.save_to_file fully overwrites the file with in-memory state and is only invoked from close(). On quit, action_quit closes the managers in fixed order, so the three never-polling managers (frenpet_full/wallet/perf — hidden from game select and Tab cycling) each rewrite the file with their startup snapshot after the active frenpet manager saved fresh history; _frenpet_perf_manager (app.py:373) wins as last writer. Starting from no cache file the idle managers save empty histories, so cross-session persistence of pet-score sparkline history never accumulates.

**Failure scenario:** User runs the frenpet main screen for an hour (screens poll only while active — on_screen_resume starts the timer, so the other 3 managers keep their startup-loaded, stale histories). On quit, action_quit closes managers in sequence: frenpet (line 361) saves fresh history, then frenpet_full (365), frenpet_wallet (369), and frenpet_perf (373) each rewrite the file with the stale startup snapshot. Last writer wins: the hour of accumulated pet-score time-series is lost, and after restart the sparklines show no history — persistence effectively never works for the frenpet dashboards.

**Suggested fix:** Share a single FrenPetCache instance (and single client) across the four FrenPetManager instances, or give each view its own cache file, or only save from the manager whose screen was last active.

### MEDI-12: `maxpane_dashboard/data/base_manager.py:258` — stale-cache (bakery-base)

record_overview_point (base_manager.py:258 → base_cache.py:126-128) unconditionally persists failure sentinels — ETH price 0.0 from get_eth_price and total_volume/trade_count 0.0 from an empty trending fetch — into the overview time series saved to ~/.maxpane/base_cache.json; the next successful cycle then reports a false "Rising" volume signal (compute_volume_trend with prev<=0), the ETH sparkline scale is transiently crushed while the zero is in the last 20 rendered points, and after restart the volume trend compares against an arbitrarily stale persisted point (gaps up to ~41 days observed in the actual cache, which also contains a real 0.0 sentinel).

**Failure scenario:** get_eth_price() returns (0.0, 0.0) and get_dexscreener_trending() returns [] on any failure (e.g. a GeckoTerminal/DexScreener 429 or timeout). fetch_and_compute still succeeds, so _compute_overview appends (ts, 0.0) to eth_price_history/volume_history, which are persisted to ~/.maxpane/base_cache.json. The ETH sparkline's scale is crushed by the zero dip, and on the next successful cycle compute_volume_trend(current, prev=0.0) reports 'Rising' regardless of reality. Additionally, prev_volume is taken from the persisted history, so after a restart the trend compares against a point that can be weeks old (observed: 96 stale points loaded from a month-old cache).

**Suggested fix:** Skip recording points when the fetch failed (eth_price <= 0 / empty token list), and ignore prev_volume points older than a few poll intervals when computing the trend.

### MEDI-13: `maxpane_dashboard/data/base_manager.py:1` — test-coverage (tests)

cattown_manager.py (317 lines) and the bakery manager.py (219 lines) have zero manager-layer tests, and BaseManager.fetch_and_compute/_compute_overview — the poll-cycle dict every Base terminal widget reads via data.get() — is untested (though BaseManager's token-detail path IS tested in tests/data/test_token_detail.py). A key rename or None-propagation bug in that dict would silently blank Base screen widgets (per-widget try/except and .get() defaults prevent crashes but hide the regression behind warning logs); nothing in the 796 tests, and no base screen test, exercises that contract.

**Failure scenario:** A key rename or None-propagation bug in base_manager's fetch_and_compute dict (the contract every Base terminal widget reads) blanks out or crashes widgets on the Base screen; nothing in the 796 tests exercises that dict, so the regression only surfaces when a user opens the dashboard.

**Suggested fix:** Clone the tests/data/test_frenpet_manager.py / test_talismans_manager.py pattern (fake client + EXPECTED_KEYS contract set + fetch-failure error-count test) for base, cattown, and bakery managers.

### MEDI-14: `maxpane_dashboard/data/cache.py:164` — crash-path (bakery-base)

load_from_file in DataCache (cache.py:164) and BaseTokenCache (base_cache.py:218) — and the same pattern in all six other cache classes — only catches OSError/JSONDecodeError; a syntactically valid cache JSON containing non-numeric point values (e.g. null) raises uncaught TypeError/ValueError during MaxPaneApp.__init__ (app.py:67/85, via manager.py:57 / base_manager.py:78), preventing the TUI from launching for all dashboards until the offending ~/.maxpane cache file is deleted, contradicting the 'silently does nothing if corrupted' docstring. Requires an externally corrupted/hand-edited file, since the app itself only persists floats via atomic writes.

**Failure scenario:** Reproduced: a cache file containing {"histories": {"Abyss": [[null, 1.0]]}} makes float(None) raise TypeError ('float() argument must be a string or a real number'). DataManager() is created in app.py:67 inside App.__init__, so a corrupt ~/.maxpane/history_cache.json or base_cache.json prevents the TUI from launching for all 8 dashboards until the user manually deletes the file — contradicting the docstring's 'silently does nothing if corrupted'.

**Suggested fix:** Wrap the per-point float() conversion (or the whole load) in try/except (TypeError, ValueError) and skip bad points, in both cache.py and base_cache.py.

### MEDI-15: `maxpane_dashboard/data/cattown_cache.py:172` — corrupt-cache-crash (cattown)

CatTownCache.load_from_file (cattown_cache.py:172) crashes the whole app at startup with an uncaught TypeError/ValueError if ~/.maxpane/cattown_cache.json contains valid JSON with non-numeric point elements (e.g. null), contradicting its docstring; however the app itself only ever writes floats atomically, so the trigger requires external file modification or cross-version format drift — real but low-probability, hence medium severity.

**Failure scenario:** ~/.maxpane/cattown_cache.json contains valid JSON with a bad point, e.g. {"prize_pool_history": [[null, 5.0]]} (external edit, another tool, or cross-version drift). float(None) raises TypeError (reproduced: 'float() argument must be a string or a real number'). load_from_file is called from CatTownManager.__init__ (cattown_manager.py:56), which MaxPaneApp.__init__ calls unconditionally (app.py:86) — so MaxPane crashes at launch even when the user starts a different game. The docstring explicitly claims 'Silently does nothing if the file is missing or corrupted', which is false for type corruption.

**Suggested fix:** Wrap the per-point conversion in try/except (TypeError, ValueError) and skip bad points, or wrap the whole restore loop and treat any exception as 'corrupt file, start empty' (optionally deleting the file).

### MEDI-16: `maxpane_dashboard/data/cattown_client.py:720` — efficiency-freeze (cattown)

get_recent_catches re-fetches every unique block timestamp serially via eth_getBlockByNumber on each 30s refresh with no memoization (block_ts is function-local, cattown_client.py:719-724); under rate limiting each failing block costs up to ~48s (3x15s timeout + 1s/2s backoff), so a refresh can exceed the 30s poll interval and the exclusive worker (screens/cattown.py:82) cancels it forever; additionally, per-block failures — including non-retried JSON-RPC error bodies — fall back to timestamp=block number (line 724), which the activity feed renders as a bogus 1971-era HH:MM.

**Failure scenario:** Measured live: 144 FishCaught logs across 26 unique blocks in the current 5000-block window (plus TreasureFound blocks); every 30s poll re-fetches all of these timestamps serially against rate-limited mainnet.base.org. Under 429s each failing call costs up to ~10s (3 retries + 1s/2s backoff, 15s timeout), so one refresh can exceed the 30s poll interval; since every refresh runs via run_worker(exclusive=True) in the same group (screens/cattown.py:82), the next tick cancels the in-flight one and the dashboard never completes a refresh while hammering the RPC. Independently, the per-block failure fallback `block_ts[bn] = bn` (line 724) makes FishCatch.timestamp = block number (~48,186,994), which _format_event_time renders as a 1971-era HH:MM — wrong time shown to the user.

**Suggested fix:** Memoize block->timestamp on the client across refreshes (blocks are immutable), cap the number of timestamp lookups per refresh, and on failure reuse the previous poll's value or omit the time instead of storing the block number.

### MEDI-17: `maxpane_dashboard/data/cattown_client.py:236` — architecture (architecture)

The JSON-RPC transport exists in 3 divergent generations (cattown: no throttle, single hardcoded endpoint; ocm: 0.5s throttle, single endpoint; ttt/talismans: multi-endpoint failover + dead-endpoint codes + error classification) with no backporting. On a 429 burst or endpoint outage, Cat Town's unpaced sequential eth_calls (including one eth_getBlockByNumber per event block in get_recent_catches) do NOT raise or bump error_count — the _safe_* wrappers swallow every failure, so the dashboard silently renders zeroed kibble/catches/staking data as fresh (error_count=0, last_updated≈0) and pollutes the persisted sparkline cache with zeros; only the REST-API-backed competition widgets survive. OCM degrades the same way (zero-fill via _safe_read_uint) but at least has an env-var endpoint override, which cattown lacks.

**Failure scenario:** Cat Town's fetch_snapshot fires many sequential eth_calls with zero pacing at the single public Base RPC; a rate-limit burst returns 429 on all 3 retries of _post_with_retry (cattown_client.py:196) and the snapshot raises — error_count climbs and the dashboard shows stale data. Worse, if that one endpoint goes down or geo-blocks (the exact 403/521-class failures ttt_client.py enumerates as _ENDPOINT_DEAD_CODES), the cattown and ocm dashboards are bricked for the whole session while ttt/talismans transparently fail over to their fallback RPC lists.

**Suggested fix:** Extract the hardened ttt/talismans _rpc (throttle + fallback rotation + error classification) into one shared rpc module and have all 5 RPC-based clients use it.

### MEDI-18: `maxpane_dashboard/data/frenpet_cache.py:205` — architecture (architecture)

Six older cache copies (frenpet_cache.py:205, cache.py:164, cattown_cache.py:172, dota_cache.py:170, ocm_cache.py:202, base_cache.py:218/232) parse persisted history points with unguarded float() calls; a valid-JSON cache file containing non-numeric values (e.g. null) raises TypeError that propagates unguarded through the manager __init__ (e.g. frenpet_manager.py:88) into MaxPaneApp.__init__ (app.py:67-90, which eagerly constructs every game's manager) and out of __main__.py:93 before Textual's error handling starts, bricking startup of the entire multi-game app on every launch until the file is manually deleted — contradicting the load_from_file docstring, while the newer ttt_cache.py/talismans_cache.py copies guard the same parsing with try/except. Mitigating factor vs. the original claim: the app's own atomic, float-coerced write path cannot produce such a file, so the trigger requires external modification or cross-version schema skew rather than organic corruption (truncated files are invalid JSON and are handled gracefully).

**Failure scenario:** Reproduced with the project venv: ~/.maxpane/frenpet_cache.json containing {"histories": {"7": [[1710000000.0, null]]}} (valid JSON, dict-shaped, so it passes both guards) raises TypeError at frenpet_cache.py:205 `dq.append((float(pt[0]), float(pt[1])))`. load_from_file is called unguarded from FrenPetManager.__init__ (frenpet_manager.py:88), which runs inside MaxPaneApp.__init__ (app.py:68), so the TUI aborts with a traceback before mounting and stays broken on every launch until the user deletes the file — despite the docstring promising 'Silently does nothing if the file is missing or corrupted'. Identical unguarded lines exist in cache.py:164, cattown_cache.py:172, dota_cache.py:170, ocm_cache.py:202, base_cache.py:218 — a corrupt cache file for ANY of these 6 games bricks startup of the whole multi-game app, while the ttt and talismans copies (ttt_cache.py:486-503, talismans_cache.py:287-295) degrade gracefully.

**Suggested fix:** Extract one shared TimeSeriesCache persistence mixin using the hardened ttt/talismans pattern (per-block try/except, skip bad points), or at minimum wrap the whole post-json.load body of the 6 older load_from_file copies in try/except Exception.

### MEDI-19: `maxpane_dashboard/data/frenpet_manager.py:156` — correctness (frenpet)

Global battle rate in frenpet_manager.py:156-159 assumes newest-first epoch-second attack entries, but the RPC-log fallback (_get_attacks_rpc) returns ascending-block-order entries with timestamp=block_number; when the Ponder attacks query fails, the negative span clamps to 0.001h yielding absurd rates (e.g. ~50,000/hr shown as 'high' in FPGameSignals), which are also appended to and persisted in battle_rate_history (~/.maxpane/frenpet_cache.json), while block-number timestamps render as bogus 1971-epoch HH:MM in the battle activity feeds.

**Failure scenario:** When the Ponder 'attacks' GraphQL entity errors, get_recent_attacks falls back to _get_attacks_rpc (frenpet_client.py:361-414), which returns eth_getLogs results in ascending block order and sets timestamp=block_number. In the manager, last_ts - first_ts is then negative, span_hours clamps to 0.001, and global_battle_rate becomes len/0.001 (e.g. 50,000/hr), shown in FPGameSignals as '~50000/hr · high' and appended to battle_rate_history, poisoning the sparkline. The block-number timestamps also render as bogus 1971-era HH:MM in the activity feeds.

**Suggested fix:** In _get_attacks_rpc, fetch block timestamps (or at least reverse to newest-first and convert block deltas to seconds using ~2s Base block time); alternatively compute span from min/max timestamp in the manager.

### MEDI-20: `maxpane_dashboard/data/frenpet_manager.py:39` — stale-cache-clobber (frenpet)

All four FrenPetManager instances share ~/.maxpane/frenpet_cache.json with load-once-at-construction and full-overwrite (no merge) save-on-close; action_quit closes them sequentially so _frenpet_perf_manager — which in the default flow never fetches (frenpet variants are hidden from _GAME_CYCLE) — saves last and reverts the file to its startup snapshot, silently discarding all history accumulated during the session by the active manager.

**Failure scenario:** App start constructs 4 FrenPetManagers (app.py:68-84), each loading the same cache file. User watches the FrenPet overview for an hour; only _frenpet_manager appends new score-history points. On quit, action_quit closes managers sequentially (app.py:361-375) and each close() calls save_cache() to the same path — frenpet_perf saves last with the histories it loaded at startup, silently reverting the file. Next launch, sparklines are missing the previous session's data, defeating the persistence feature.

**Suggested fix:** Use per-view cache files, share one cache/manager instance, or only save from managers whose cache was actually updated (track a dirty flag).

### MEDI-21: `maxpane_dashboard/data/frenpet_manager.py:505` — stale-cache (async)

All four FrenPetManager instances share ~/.maxpane/frenpet_cache.json; on quit each close() does a full-file overwrite in sequence, so the last-closed manager (frenpet_perf, stale unless its screen was active) clobbers the active manager's freshly accumulated per-pet score history — defeating sparkline persistence for the frenpet/frenpet_full/frenpet_wallet screens. (Note: population-level battle-rate/total-score histories are never persisted by save_to_file at all, independent of this bug.)

**Failure scenario:** User runs the frenpet dashboard for an hour (score/battle-rate history accumulates in _frenpet_manager.cache), presses q: action_quit closes frenpet (saves fresh history), then frenpet_full, frenpet_wallet, and frenpet_perf each save the same file - the perf manager still holds only the data loaded at construction, so the hour of history is clobbered. Sparkline history therefore never survives restarts; the persistence feature is effectively defeated whenever more than one FrenPet manager exists (always, since app.__init__ builds all four).

**Suggested fix:** Use per-variant cache files, share one FrenPetCache instance across the four managers, or only save from the manager whose cache was updated most recently.

### MEDI-22: `maxpane_dashboard/data/manager.py:106` — stale-cache (bakery-base)

DataCache.load_from_file restores persisted history with no age filtering and histories are keyed by bakery name with no season awareness, so for up to ~60 minutes after a restart (until the 120-point deque evicts stale samples) production rates are regressed over mixed stale/current data: a long idle gap yields the long-run average rate instead of the current rate, and a season rollover yields a negative slope clamped to 0, making leader_rate=0, all boost EVs negative, and gap_analysis report gap_rate 0 with wrong 'catchable' verdicts.

**Failure scenario:** DataCache.load_from_file restores all points regardless of the file's saved_at, and history is keyed by bakery name only. Restart the app a day into a gap: regression over [old cluster, 24h gap, new cluster] yields the 24h-average rate, not the current rate. Worse, when a new season starts and cookie counts reset to ~0 while the cache holds last season's multi-million values for the same bakery name, the slope is negative and clamped to 0 — leader_rate=0 then makes every boost EV negative and gap_analysis reports gap_rate 0 / wrong 'catchable' verdicts.

**Suggested fix:** On load, drop points older than the sparkline window (e.g. max_history * poll_interval) and clear a bakery's history when its cookie count decreases (season reset).

### MEDI-23: `maxpane_dashboard/data/models.py:309` — decode-error (bakery-base)

ActivityEvent.launcher (models.py:309) is typed non-optional str, but live random events (isRandomEvent=true, e.g. 'Rush Order' boosts) have launcher=null; the list comprehension in client.py:262 then aborts the whole per-bakery feed, and get_activity_feed_global's return_exceptions handling silently drops all of that bakery's events, leaving the ActivityFeed widget incomplete with only a log warning (reproduced live: 80 of 100 events returned, bakery 1568 dropped).

**Failure scenario:** Confirmed live: running fetch_and_compute() logged 'Failed to fetch activity for a bakery: 1 validation error for ActivityEvent / launcher / Input should be a valid string [input_value=None]'. client.py:262 builds the feed with a list comprehension, so a single null-launcher event discards every event for that bakery; get_activity_feed_global then silently omits that bakery, leaving the ActivityFeed widget incomplete with no visible error.

**Suggested fix:** Make launcher (and defensively title/description) `str | None` with a default, or skip individual malformed events instead of failing the whole list.

### MEDI-24: `maxpane_dashboard/data/ocm_cache.py:202` — crash-path (ocm-dota)

load_from_file's unguarded float() coercion crashes on corrupt-but-valid-JSON cache points (e.g. null values), and because every game's manager loads its cache in __init__ and MaxPaneApp.__init__ constructs all managers unconditionally before app.run(), one bad value in any of the 8 ~/.maxpane/*_cache.json files (same pattern in ocm, dota, base, bakery, cattown, frenpet, talismans, ttt caches) aborts MaxPane startup for all dashboards with a raw traceback, contradicting the docstring's 'silently does nothing if corrupted' contract.

**Failure scenario:** Reproduced: a cache file containing {"supply_history": [[1751600000.0, null]], ...} raises TypeError ('float() argument must be a string or a real number, not NoneType') at float(pt[1]); only OSError/JSONDecodeError are caught, contradicting the docstring's 'silently does nothing if ... corrupted'. OCMManager.__init__ calls load_from_file (ocm_manager.py:53) and is constructed in MaxPaneApp.__init__ (maxpane_dashboard/app.py:87), so one bad value in ~/.maxpane/ocm_cache.json prevents MaxPane from launching for ALL 8 dashboards until the user manually deletes the file. dota_cache.py:170 has the identical bug (DOTAManager constructed at app.py:88).

**Suggested fix:** Wrap the per-point conversion (or the whole load loop) in try/except (TypeError, ValueError) and skip bad points; apply the same fix to DOTACache.load_from_file.

### MEDI-25: `maxpane_dashboard/data/ocm_client.py:389` — correctness (ocm-dota)

_safe_read_uint's 0-on-failure sentinel is consumed as real data by fetch_snapshot (which never raises on RPC failure), so sustained public-RPC failures yield a 'successful' all-zero snapshot with error_count=0, possible negative net_supply, and a (ts, 0.0) point appended to supply_history and persisted across restarts; if that point is the oldest in history, the next good poll produces an absurd mint velocity and time_to_next_tier. Impact is bounded: the poisoned point rolls off the 120-sample deque (~2h of good polls) and the display self-heals.

**Failure scenario:** Public-RPC 429s/timeouts that exhaust the 3 retries make _safe_read_uint return 0. If only totalSupply() fails while balanceOf(0xdead) succeeds, net_supply = 0 - burned goes negative and total_supply/minted_pct display as 0. Worse, OCMManager.fetch_and_compute() then appends (ts, 0.0) to supply_history via cache.update() and persists it to ~/.maxpane/ocm_cache.json, so on the next good poll compute_mint_velocity sees 0 -> ~10,000 in minutes and shows an absurd mint velocity ('active' green) plus a bogus time_to_next_tier -- and the poisoned point survives restarts. Since fetch_snapshot never raises even when every RPC call fails, error_count stays 0 and the status bar reports a fresh, error-free update while all widgets show zeros.

**Suggested fix:** Distinguish failure from zero (return None from _safe_read_uint, or raise when core reads like totalSupply fail); skip cache.update()/history append for failed reads and increment error_count so the status bar reflects the outage.

### MEDI-26: `maxpane_dashboard/data/ocm_client.py:102` — test-coverage (tests)

The OCM dashboard is the only one of 8 dashboards with zero test coverage: ocm_client.py (538 lines of hand-rolled JSON-RPC/ABI decoding), ocm_manager.py (248), ocm_cache.py (215), and analytics/ocm_signals.py (121) have no tests, so a decode or unit-conversion regression would ship undetected while all 796 tests stay green. Runtime impact is bounded, not a crash: the specific int(topics[3],16) IndexError is already guarded (len(topics)<4 check at ocm_client.py:427 plus except IndexError at :467), and screens/ocm.py wraps all refresh/widget updates in try/except — the realistic untested failure mode is silently wrong or missing data on the OCM screen.

**Failure scenario:** A regression in the OCM decode path (e.g. a log with fewer than 4 topics reaching int(topics[3],16) -> IndexError, or a wei-vs-ETH slip in ocm_signals) crashes or silently corrupts the OCM screen for every user, while all 796 tests stay green. OCM memory notes already record rate-limit lessons, so this client has known-tricky RPC behavior with no regression net.

**Suggested fix:** Add a tests/data/test_ocm_client.py mirroring the talismans-client pattern (canned _rpc responses, malformed-log and reverted-call cases) plus a tests/analytics/test_ocm_signals.py; the existing talismans/cattown test files are direct templates.

### MEDI-27: `maxpane_dashboard/data/talismans_manager.py:304` — error-handling (talismans)

A transient multicall failure never raises (TalismansClient._multicall returns all-False results), making _refresh_token_states' except-branch dead for RPC failures; set_token_states then replaces the live token registry with an empty or chunk-truncated dict, zeroing the title bar, leaderboard, and matrix for that cycle, and persisting a mythic_hourly=0 sample that leaves a sparkline dip if no successful refresh lands in the same hour bucket (it self-heals within the hour otherwise; the conservation baseline and known_ids are unaffected).

**Failure scenario:** TalismansClient._multicall catches all exceptions and returns [(False, '0x')]*len (talismans_client.py:562-564), so on an RPC blip fetch_token_states returns {} (or is missing whole 150-id chunks) instead of raising. set_token_states then replaces cache.tokens with the empty/partial dict: the title bar drops to '0 mythic · cores 0', the leaderboard empties, and sample_distribution persists mythic_count=0 into the 7-day mythic_hourly sparkline in the on-disk cache, leaving a permanent dip artifact even after the next successful refresh.

**Suggested fix:** Have fetch_token_states/_multicall distinguish transport failure from per-call revert (e.g. raise on multicall transport failure, or return None), and keep the previous registry when the sweep did not fully succeed; skip sample_distribution for incomplete cycles.

### MEDI-28: `maxpane_dashboard/data/talismans_manager.py:114` — error-handling (talismans)

The cached-flags fallback at talismans_manager.py:115-123 is unreachable on any network-failure path because fetch_collection_flags swallows RPC errors via _multicall and returns zeros (only an exotic malformed 200-with-null-result response can reach it); during an outage the dashboard shows live_tokens=0, persists a zero sample into tokencount_hourly, and forge_momentum_signal reports a false green "CONSOLIDATING ▼".

**Failure scenario:** fetch_collection_flags swallows all failures via _multicall and _u() and returns {'total_supply': 0, 'genesis_minted': 0, ...}, so the except branch at lines 115-123 (which would substitute cached counts) can never execute. During an outage the hero and title bar show 0 live tokens, and sample_distribution(now_ts, mcount, 0) appends token_count=0 to tokencount_hourly (persisted to cache); forge_momentum_signal then sees latest(0) < earliest and reports 'CONSOLIDATING ▼' in green — a bullish-looking signal manufactured entirely by a network error.

**Suggested fix:** Make fetch_collection_flags raise (or return None) when the underlying multicall transport call failed, so the existing fallback to cached values actually runs, and do not sample distribution buckets on a failed cycle.

### MEDI-29: `maxpane_dashboard/data/ttt_client.py:593` — correctness (ttt)

_get_logs (ttt_client.py:587-594) swallows per-chunk eth_getLogs failures and returns a partial list with no error indication, defeating the manager's watermark guard in _scan_events (ttt_manager.py:431-446): last_seen_block is advanced to current_block and persisted, so events in the failed chunk older than the 5,000-block incremental lookback are permanently lost for the cache's lifetime. Missed Launched tokens never enter cache.tokens (register_token is only reachable via apply_launch), permanently excluding them from the leaderboard, top-fee-engines table, metadata/reservoir refresh, and buyback scans; their later fee deposits still show in the activity feed but unlabeled. The same silent loss applies to Deposited and Bought scans.

**Failure scenario:** First run scans 150,000 blocks in 15 chunks of 10k; a chunk hits 'query returned too many results' / range-limit errors on all four public endpoints (server-defined JSON-RPC codes break to the next endpoint, then RuntimeError) -> the exception is caught here, cursor advances, fetch_launched_events returns the partial list without any error indication -> _scan_events sets cache.last_seen_block['Launched'] = current_block and persists it. Launches in that chunk are never re-scanned (only a 5,000-block lookback thereafter): those tokens never appear in the leaderboard, fees table, or activity feed for the life of the cache.

**Suggested fix:** Propagate chunk failures (or return a partial-success flag) and only advance the watermark past ranges that were actually fetched.

### MEDI-30: `maxpane_dashboard/data/ttt_client.py:512` — error-handling (ttt)

resp.json() at ttt_client.py:512 raises json.JSONDecodeError (a ValueError, caught by neither the (httpx.HTTPError, httpx.StreamError) arm nor the RuntimeError arm) on a 200 non-JSON response, escaping _rpc from the first endpoint's first attempt and bypassing the entire retry-and-fallback chain; ttt_manager's per-source except Exception then zeroes factory state, events, and reservoirs until the primary RPC recovers.

**Failure scenario:** cloudflare-eth.com returns HTTP 200 with an HTML challenge/error page (or a proxy injects a non-JSON body) -> json.JSONDecodeError propagates straight out of _rpc without trying eth.drpc.org / ankr / llamarpc -> every call fails at the first endpoint even though 3 healthy fallbacks exist; the dashboard degrades to all-zero factory state, no new events, and zeroed reservoirs (compounding the burn_count=0 finding) until the primary recovers.

**Suggested fix:** Add ValueError/json.JSONDecodeError to the per-attempt except clause so malformed bodies count as endpoint failures and trigger fallback.

### MEDI-31: `maxpane_dashboard/data/ttt_manager.py:186` — error-handling (ttt)

TTTClient._multicall swallows total-RPC-outage exceptions and returns [(False,'0x')]*5, so fetch_factory_state returns burn_count=0/active_shares=0 instead of raising; TTTManager's except branch and _error_count never fire (contradicting fetch_and_compute's documented contract and leaving its fallback dict dead code), the dashboard silently renders plausible-false data (title '0/10,000', unburned=10,000, burned 0.0%, concentration 1/10,000) with no error indication, and a false (hour, 0) point is written into burns_hourly and persisted to ttt_cache.json on shutdown if not re-sampled within the same hour. Display self-heals next successful cycle and the dashboard is read-only, so impact is bounded: one cycle of false UI plus one potentially permanent bad sparkline point.

**Failure scenario:** All 4 public RPC endpoints time out for one cycle -> TTTClient._multicall returns [(False,'0x')]*5 -> fetch_factory_state returns burn_count=0/active_shares=0 without raising -> manager's except branch (and _error_count increment) never fires -> title bar shows '0/10,000', hero shows unburned=10,000 / burned 0.0%, concentration signal computes 1/10,000, and sample_burns_and_floor writes (hour, 0) into the 7-day sparkline history; if the app closes before a successful re-sample in the same hour, the false 0 point is saved in ttt_cache.json permanently.

**Suggested fix:** Have fetch_factory_state signal failure (raise or return None) when the multicall itself failed, and skip sampling/rendering factory-derived metrics for that cycle.

### MEDI-32: `maxpane_dashboard/screens/frenpet_full.py:606` — dead-data-key (frenpet)

Pet view (frenpet_full.py:606-607) reads data['all_scores'] and data['population_pets'], keys never produced anywhere in the repo, so PetSignals always renders 'Rank #0 of 0' (despite correct ranks being available in data['pet_ranks']) and SniperQueue always shows the 'No viable targets' placeholder, on every refresh of the CLI-only frenpet_full screen.

**Failure scenario:** Launch with --game frenpet_full and a wallet that owns pets: fetch_and_compute() (frenpet_manager.py:381-427) returns pet_ranks and population_stats but no 'all_scores'/'population_pets'. update_pet_view then takes the else branch at line 689 (rank_info = zeros) — even though correct per-pet ranks exist in data['pet_ranks'] — and passes an empty list to SniperQueue.update_data, so PetSignals renders 'Rank #0 of 0' and the sniper table never lists a candidate regardless of live data.

**Suggested fix:** Use data['pet_ranks'][pet.id] for rank_info and have the manager expose the population pet list (e.g. snapshot.population.pets) for the sniper queue.

### MEDI-33: `maxpane_dashboard/screens/frenpet_wallet.py:152` — unit-error (frenpet)

FrenPet wallet hero renders raw 18-decimal uint256 values (total_fp_in_pool, user_shares) through _fmt_fp, which never divides by 1e18, so the POOL SHARE and APR boxes' subtitle lines show garbage like 'of 37325669265659.0B FP pool' (verified live: totalFpInPool ≈ 3.73e22 raw = ~37,326 FP); headline metrics in the same boxes remain correct and the view is CLI-only (hidden from the game-select menu), making this a display-only defect.

**Failure scenario:** FrenPetClient.get_total_fp_in_pool()/get_user_shares() return int(hex,16) with no 1e18 scaling (verified live on Base: totalFpInPool = 0x7e76db7c53edaf45157 ≈ 3.7e22, i.e. ~37,300 FP). The screen passes these raw to FPWalletHero.update_data, whose _fmt_fp() caps at a /1e9 'B' suffix, so the POOL SHARE box shows 'of 37300000000000.0B FP pool' and the APR box 'on <similar garbage> FP staked'. Contrast: the same screen correctly divides total_fp_per_second by 1e18 at line 241, and get_fp_reward_pool() divides by 1e18 in the client.

**Suggested fix:** Divide total_fp_in_pool and user_shares by 1e18 before passing to FPWalletHero (or scale inside _fetch_wallet_rewards so all consumers get display units).

### MEDI-34: `maxpane_dashboard/screens/talismans.py:124` — concurrency (async)

Every screen pairs set_interval(poll_interval) with run_worker(exclusive=True) in the same node/group, so any refresh cycle exceeding the 30s poll interval is cancelled by the next timer tick and restarted from scratch. Normal cycles measure ~1.5s steady-state / ~5s cold-start (20x margin), so this does not trigger routinely; but under sustained RPC degradation — canonically a hanging primary endpoint, where each of ~15 sequential calls burns ~20.5s in timeouts before falling back (no cross-call endpoint demotion) — every cycle exceeds 30s and the dashboard livelocks: no refresh ever completes, widgets stay on placeholders, RPC traffic continues, and the multi-endpoint fallback resilience is nullified. Fix by guarding against overrun (skip tick if a refresh worker is running, or restart the interval on completion).

**Failure scenario:** Talismans steady-state cycle re-reads tokenData+ownerOf for all ~1,536+ known ids every cycle (~11 Multicall3 batches of 300 sub-calls each, plus log scans and a first-run 250k-block scan = 5 paged eth_getLogs) against free public RPCs with 0.5s+1.5s retry backoffs; this routinely exceeds the default 30s poll interval. When it does, the interval timer's _schedule_refresh starts a new exclusive worker which cancels the in-flight one (worker_manager.cancel_group matches same node+group), fetch_token_states restarts from chunk 0 with no incremental progress, and the cycle repeats: widgets show placeholders forever while RPC traffic continues. Same pattern in all 11 screens; TTT (sequential event scans + metadata + reservoirs + market data) and the FrenPet wallet screen (now with fetch_rewards=True: 3 serialized RPCs + 0.3s of sleeps per pet per cycle) are also at risk. Cancellation additionally orphans ttt_manager's create_task() side tasks (floor/eth_usd) mid-cycle.

**Suggested fix:** Skip scheduling a new refresh while one is running (check the worker's state or an in-progress flag) instead of cancelling it, or set the interval timer only after a refresh completes.

### MEDI-35: `maxpane_dashboard/screens/ttt.py:121` — race-condition (async)

App-node prefetch worker and screen-node initial refresh run fetch_and_compute() concurrently on the same TTTManager (Textual's exclusive=True only cancels within the same DOM node); with no lock and a post-await watermark update, both first-run scans read last_seen_block=0 and double-apply all Launched/Deposited/Bought events, doubling event-derived metrics (launches_24h, holder-pool 24h ETH, per-token fee columns) and duplicating activity-feed rows, persisted to ~/.maxpane/ttt_cache.json — chain-read values (burn_count, unburned, holder_pool_eth_total) are unaffected; the same pattern applies to every game manager, including the default bakery startup path.

**Failure scenario:** Start with `--game ttt`: on_mount launches the prefetch (first-run scan of 150k blocks takes well over the few seconds the user spends on splash + game select); when TTTScreen resumes, _do_initial_refresh starts a second fetch_and_compute on the same TTTManager. Both scans read last_seen_block=0 and both apply every Deposited/Launched event (TTTCache has no dedup) -> fees and launch counts double from the very first snapshot and are persisted. For bakery the same overlap appends two near-identical history points per bakery; for talismans two full token-state sweeps race through set_token_states and sample_distribution. Textual's cancel_group filters on worker.node == node (worker_manager.py:149-152), so the screen's exclusive worker cannot cancel the app-node prefetch.

**Suggested fix:** Have the screen's initial refresh await/join the prefetch worker result, or serialize fetch_and_compute per manager with an asyncio.Lock.

### MEDI-36: `maxpane_dashboard/templates/sparkline_template.py:1` — architecture (architecture)

templates/ (8 modules) is a documented copy-and-adapt seed, not an import library, but it is bypassed and stale: no code imports it, new dashboards copy from the previous dashboard (tal from ttt, ttt from ocm), _coerce_points/_build_sparkline are byte-identical duplicates in ttt/tal while ocm/cattown/dota and sparkline_template.py itself lack the None-tolerant _coerce_points hardening (None entry -> TypeError in _build_sparkline), so fixes fork per-dashboard, never reach the template (untouched since 2026-04-03), and the dead templates subpackage still ships in the PyPI wheel.

**Failure scenario:** Because propagation is dashboard-to-dashboard copy instead of a shared import, every fix forks: _coerce_points and _build_sparkline are byte-identical duplicates in ttt_sparkline.py and tal_sparkline.py, while the older ocm/cattown/dota sparkline copies lack the None-tolerant _coerce_points hardening entirely; a bug fixed in sparkline_template.py reaches nothing. This is the exact mechanism that produced the proven startup-crash divergence in the cache loaders (finding 1): the 9th dashboard will be seeded from talismans, inheriting whatever bugs it has at copy time, and dead template code ships in the PyPI package.

**Suggested fix:** Either make templates real shared code that game widgets import (parameterized by id-prefix/labels), or delete the package and document the copy-source; extract the byte-identical helpers (_coerce_points, _build_sparkline, _safe_call, cache persistence) into shared modules.

### MEDI-37: `maxpane_dashboard/widgets/activity_feed.py:107` — error-handling (widgets)

ActivityFeed writes unescaped API strings (event.title, event.description, linked_bakery_name) to a markup=True RichLog; one bad event raises MarkupError after log.clear(), leaving the feed blank or truncated on every refresh.

**Failure scenario:** getActivityFeed returns an event whose title/description or linked bakery name contains a mismatched close tag (e.g. bakery named '[/b]team' appearing as linked_bakery_name in _event_to_markup line 44). update_data executes log.clear() (line 104) then log.write raises MarkupError synchronously (verified: RichLog.write with markup=True raises immediately). BakeryScreen catches it and only logs a warning, so the panel stays empty/partial for as long as the bad event remains in the feed window, with no user-visible error.

**Suggested fix:** Apply rich.markup.escape() to ts/who/title/description/target inside _event_to_markup before embedding them in markup strings.

### MEDI-38: `maxpane_dashboard/widgets/hero_metrics.py:98` — error-handling (widgets)

leader_name (player-chosen bakery name from the tRPC API, never escaped) is interpolated into Static markup at hero_metrics.py:98-102; invalid markup like '[/x]' makes Static.update raise MarkupError synchronously (textual 8.1.1), which BakeryScreen catches and logs each poll — prize-pool and countdown boxes keep updating, but the LEADER box stays frozen at 'Loading...'/stale data for as long as that bakery leads. Same unescaped-name pattern in cookie_chart.py:107-112 freezes the affected sparkline row and all rows after it.

**Failure scenario:** The #1 bakery's name contains e.g. '[/x]'. leader_box.update(f"[dim]{leader_name} ...") raises MarkupError synchronously (verified with Static.update in textual 8.1.1). BakeryScreen logs a warning and continues, but because the prize-pool and countdown boxes are updated in the same update_data call that dies at the leader box... actually the prize/countdown boxes update first, while the leader box permanently shows 'Loading...' or stale data as long as that bakery leads. Identical unescaped-name pattern in widgets/cookie_chart.py lines 107-112 freezes the corresponding sparkline row.

**Suggested fix:** Escape leader_name (and bakery names in cookie_chart.py) with rich.markup.escape() before formatting.

### MEDI-39: `tests/data/test_cattown_client.py:299` — test-correctness (tests)

test_fetch_snapshot_assembles_all silently validates only the RPC fallback: under AsyncMock(spec=httpx.AsyncClient), _get_competition_from_api raises AttributeError("'coroutine' object has no attribute 'get'") (resp.json() returns an unawaited coroutine), which get_competition_state's broad except at cattown_client.py:382 swallows; this is the source of the suite's only two 'coroutine never awaited' RuntimeWarnings, and the cat.town API-success parse (the primary production path via cattown_manager.py:94) has zero coverage anywhere in tests/. Correction to the original scenario: tightening the broad except would not make this test fail — _safe_competition_state's own except Exception (line 815) would still return a default CompetitionState, so the masking is two layers deep.

**Failure scenario:** If the cat.town API changes its leaderboard JSON (e.g. prizePool becomes a float, or 'size' stops being a stringified int, breaking int(comp.get('prizePool','0')) or int(item.get('size','0')) in _get_competition_from_api), every real user silently falls back to RPC or sees a wrong prize pool, and the suite stays green because no test ever executes the API-success parse. Conversely, if someone tightens the broad except in get_competition_state, this test starts failing for a reason unrelated to what it claims to test.

**Suggested fix:** Configure mock_http.get to return a real httpx.Response (or a stub with sync raise_for_status/json) carrying a canned cat.town leaderboard payload; add one test for API-success parsing and keep a separate explicit test for the RPC fallback (mock get to raise).

### MEDI-40: `tests/data/test_frenpet_manager.py:75` — test-coverage (tests)

The uncommitted fetch_rewards feature (frenpet_manager.py diff on this branch) is completely untested: no test passes fetch_rewards=True, no test touches _fetch_wallet_rewards (an on-chain RPC decode path with rate-limit sleeps), and the manager's output key 'wallet_rewards' (frenpet_manager.py:422) is absent from the EXPECTED_KEYS contract set, so the suite also failed to notice that the default behavior flipped (wallet rewards were previously fetched whenever wallet_address was set, now off by default).

**Failure scenario:** A decode or rate-limit regression in _fetch_wallet_rewards ships unnoticed and the FrenPet wallet dashboard silently shows no rewards data (the except at frenpet_manager.py:283 swallows the error); equally, if app.py's fetch_rewards=True wiring is dropped in a refactor, no test fails and the feature silently disappears.

**Suggested fix:** Add wallet_rewards to EXPECTED_KEYS; add two tests: fetch_rewards=True with a mocked _fetch_wallet_rewards asserting the payload lands in the result, and fetch_rewards=False (with wallet set) asserting wallet_rewards is None.


## Low (22)

### LOW-1: `maxpane/src/intro/mod.rs:130` — ctrl-c-swallowed (rust)

No code checks KeyModifiers::CONTROL, so with raw mode enabled Ctrl+C is never treated as an interrupt: at the Y/N prompt it is inserted into the input buffer as a literal 'c'; with skip_key="none" it is ignored on every screen; and with the default skip_key="any" it triggers Skip (marking the intro seen and taking the dashboard path) instead of aborting. Impact is bounded — every screen auto-advances or offers Esc/N recovery, and the current binary exits right after the intro anyway — so this is a TUI-convention/UX defect rather than a trap.

**Failure scenario:** Raw mode suppresses SIGINT, so Ctrl+C arrives as KeyEvent{Char('c'), CONTROL}. At the Y/N prompt (needs_input=true) it falls through to PromptState::handle_input's Char(c) catch-all and types 'c' into the buffer; with skip_key="none" configured, Ctrl+C is dead on every screen. A user expecting the universal terminal interrupt cannot abort the intro — they must know to press Esc or answer N. With the default skip_key="any", Ctrl+C on the typewriter/rain screens 'skips' into the dashboard rather than exiting, the opposite of the user's intent.

**Suggested fix:** In IntroSequence::handle_input (or the main event loop), check key.modifiers.contains(CONTROL) && key.code == Char('c') first and return IntroAction::Exit.

### LOW-2: `maxpane/src/main.rs:88` — key-release-not-filtered (rust)

Key events are processed without filtering kind == KeyEventKind::Press, so on Windows (where crossterm delivers both Press and Release events) every keystroke registers twice.

**Failure scenario:** On Windows: typing 'n' then Enter at the prompt buffers "nn" (press + release), which is not recognized as No — the user gets 'There is no spoon. Try again.' retry instead of Exit; easter eggs like 'gm' become 'ggmm' and never match; with skip_key="any", the Release of the Enter key that launched the binary from the shell can instantly skip the whole intro. Unix/macOS is unaffected because only Press events are emitted there.

**Suggested fix:** Guard the event loop with `if key.kind == crossterm::event::KeyEventKind::Press` before calling seq.handle_input(key).

### LOW-3: `maxpane_dashboard/__main__.py:44` — cli-validation (core)

--poll-interval accepts 0 and negative values with no bounds check: 0 kills every screen's refresh timer via ZeroDivisionError in Textual's Timer skip path (refresh silently stops after the initial fetch, and the stored exception also crashes the app with a traceback on exit via Timer._stop_all); negative values drive an await-free busy loop in the same skip branch that starves the asyncio event loop and freezes the entire TUI. Both reproduced against Textual 8.1.1 in the project venv.

**Failure scenario:** `maxpane --poll-interval 0`: each screen's on_screen_resume calls set_interval(0, ...); in textual/timer.py Timer._run, skip=True and next_timer < now leads to `count = int((now - start) / _interval + 1)` -> ZeroDivisionError, the timer task dies unobserved, and the dashboard silently stops auto-refreshing after the initial fetch. `--poll-interval -5`: the same skip branch recomputes count to the same value and `continue`s forever without an await, starving the asyncio event loop and freezing the whole UI.

**Suggested fix:** Validate the argument (e.g. argparse type function enforcing a minimum of 5 seconds) or clamp poll_interval in MaxPaneApp.__init__.

### LOW-4: `maxpane_dashboard/analytics/ocm_signals.py:10` — correctness (ocm-dota)

generate_staking_signal and generate_recommendation (ocm_signals.py:10, :73) 100x-rescale the already-percentage staking_ratio whenever it is <= 1.0, so any genuine sub-1% (or exactly 1%) staking ratio would display as inverted healthy double/triple-digit staking and suppress the low-staking warning; latent today since live data shows ~11.6% staked, which takes the correct branch.

**Failure scenario:** OCMManager passes snapshot.staking.staking_ratio, which is already a percentage (total_staked / net_supply * 100, ocm_client.py:347-349). With 80 of 10,000 NFTs staked, staking_ratio = 0.8 -> the heuristic 'pct = staking_ratio * 100 if staking_ratio <= 1.0' turns it into 80 -> the Signals widget shows '80% staked' green 'healthy' instead of '1% staked' red 'low', and generate_recommendation suppresses the correct 'Low staking activity' message. Exactly 1.0% staked displays as '100% staked'.

**Suggested fix:** Remove the unit-guessing heuristic; both functions should take a percentage and use it directly (the caller contract is already percent).

### LOW-5: `maxpane_dashboard/analytics/ttt_signals.py:114` — correctness (ttt)

count_decay_window (ttt_signals.py:114) counts negative block deltas as inside the 98-block decay window; when fetch_block_number returns 0 on total RPC failure, TTTManager passes current_block=0 unguarded to decay_window_signal, so every cached token is reported in-decay (yellow) and _age_str shows "0b" for all leaderboard rows until the next successful poll.

**Failure scenario:** fetch_block_number returns 0 (all endpoints down for that one call) while the cache holds e.g. 340 launched tokens -> (0 - launch_block) < 98 is True for all -> Signals panel shows '340 tokens in decay window (>1% buy tax)' in yellow; _age_str simultaneously shows '0b' age for every leaderboard row. A guard for current_block <= 0 (skip or keep previous signal) avoids the false alarm.

**Suggested fix:** Only count tokens with 0 <= current_block - launch_block < DECAY_BLOCKS, and have the manager skip block-anchored signals when current_block is 0.

### LOW-6: `maxpane_dashboard/data/base_cache.py:64` — unbounded-growth (security)

BaseTokenCache._price_histories has no entry-count cap or eviction: every never-seen token address from the uncapped GeckoTerminal trending response gets a new 120-point deque (base_cache.py:64-65), the whole dict is persisted to ~/.maxpane/base_cache.json on shutdown, and it is reloaded uncapped on every MaxPane startup for any dashboard (BaseManager is constructed unconditionally in app.py:85), so memory and the cache file grow without bound across sessions.

**Failure scenario:** Every poll, update() creates a new 120-point deque for each never-seen token address taken straight from the API response. get_dexscreener_trending (base_client.py:739) iterates data['data'] with no cap on pool count, so a compromised/hostile GeckoTerminal response containing e.g. 500k pool entries creates 500k deques in one cycle, which save_to_file() then serialises to disk and load_from_file() restores on every startup (also uncapped). Even organically, trending tokens churn daily and old addresses are never evicted, so the cache file grows forever across sessions.

**Suggested fix:** Cap the number of tracked addresses (e.g. LRU-evict beyond ~500 tokens), truncate the pools list from the API to a sane maximum (e.g. 50), and apply the same cap when loading histories from disk.

### LOW-7: `maxpane_dashboard/data/base_client.py:113` — keyless-constraint (security)

Shipped package carries a dead keyed Bankr integration: BaseChainClient.__init__ (base_client.py:113-114) silently reads BANKR_API_KEY/ALCHEMY_API_KEY from the environment at every app launch (app.py:85 constructs BaseManager eagerly), and base_manager.py:20-23 performs an opt-in import-time load_dotenv of a file named by MAXPANE_BASEBOARD_ENV (override=False). The key-transmitting path (x-api-key to api.bankr.bot) is unreachable — get_trending_tokens_bankr has zero callers anywhere, including tests, and _alchemy_api_key is never used — so this violates the project's internal keyless constraint and leaves latent keyed code, but leaks nothing today.

**Failure scenario:** The shipped PyPI package reads BANKR_API_KEY and ALCHEMY_API_KEY from the user's environment into every BaseChainClient instance, and base_manager.py imports arbitrary env vars from a file pointed to by MAXPANE_BASEBOARD_ENV at module import time. The path is currently dead in the app (app.py:85 constructs BaseManager(remote_only=True) and nothing calls get_trending_tokens_bankr), but any future caller of get_trending_tokens_bankr() re-enables a keyed, non-public endpoint — and a user who happens to have BANKR_API_KEY set for another project has that secret silently captured into a long-lived client object of a tool advertised as keyless.

**Suggested fix:** Delete the Bankr code path (_bankr_submit_prompt, _bankr_poll_job, get_trending_tokens_bankr), the BANKR_API_KEY/ALCHEMY_API_KEY env reads, and the MAXPANE_BASEBOARD_ENV load_dotenv block; the app already runs exclusively on the keyless DexScreener/GeckoTerminal path.

### LOW-8: `maxpane_dashboard/data/base_manager.py:22` — architecture (architecture)

base_manager.py:19-23 performs an undocumented, silent import-time load_dotenv of a foreign 'baseboard' .env (opt-in via MAXPANE_BASEBOARD_ENV, override=False so it only adds unset vars), and base_client.py carries dead keyed infrastructure — BANKR_API_KEY/ALCHEMY_API_KEY reads (113-114, alchemy key never used at all), a "BANKR_API_KEY not configured" raise (221) reachable only via get_trending_tokens_bankr which has zero callers — all unreachable from the shipped app since app.py:85 only constructs BaseManager(remote_only=True); python-dotenv is a shipped PyPI dependency existing solely for this dead hook, contradicting the project's keyless constraint. (Note: GeckoTerminal/Clanker are keyless, not keyed, though that flow is equally unreachable.)

**Failure scenario:** Importing maxpane_dashboard.data.base_manager (which app.py always does) silently loads environment variables from an unrelated project's .env file if MAXPANE_BASEBOARD_ENV points at one — an import-time side effect that can change behavior of anything else reading those env vars in-process. The keyed Bankr/GeckoTerminal/Clanker paths are unreachable from the shipped app but remain maintained-looking, misleading contributors into thinking keyed operation is supported and contradicting the documented keyless guarantee of the public PyPI package.

**Suggested fix:** Strip the bankr/alchemy key plumbing and the baseboard .env loader from base_manager/base_client, keeping only the remote_only DexScreener path the app actually uses.

### LOW-9: `maxpane_dashboard/data/cattown_client.py:315` — dead-fallback-unit-mismatch (cattown)

get_kibble_price's oracle fallback (cattown_client.py:313-326) is dead code — the contract at KIBBLE_ORACLE is not a Chainlink aggregator and reverts on latestRoundData()/decimals() (verified live), so any DEX getReserves failure silently yields price 0.0; additionally, the working DEX path returns an ETH-denominated price (~4e-7, reserve0 WETH / reserve1 KIBBLE, verified live) that is stored in KibbleEconomy.price_usd and exported as the documented hero metric "kibble_price_usd" (cattown_manager.py:267), while cattown_signals.py:178 formats the same field as ETH. Latent only: no current widget renders the value and generate_kibble_signal is never called, but any consumer of the documented key gets an ETH value labeled USD.

**Failure scenario:** Verified via live eth_call on Base: 0xE97B7ab0...FB7 returns 'execution reverted' for both 0xfeaf968c and 0x313ce567, so whenever the DEX getReserves call fails (rate limit), the fallback always raises too and the price silently becomes 0.0 — the fallback is dead code. Additionally, the DEX path returns reserve0/reserve1 = KIBBLE price in ETH (~2e-7), but it is stored in KibbleEconomy.price_usd and exported as 'kibble_price_usd' (cattown_manager.py:267), the manager docstring lists it as a hero metric, and the units even disagree with the (never-working) oracle branch which would return USD. Not currently rendered by any Cat Town widget, but any consumer of the documented key will show an ETH value labeled as USD.

**Suggested fix:** Rename the field/key to price_eth (or convert to USD via an ETH/USD source), and either remove the dead oracle fallback or fix/verify the oracle interface; validate_cattown_abis.py already documents that this oracle reverts on the Chainlink interface.

### LOW-10: `maxpane_dashboard/data/dota_client.py:223` — test-coverage (tests)

The DOTA data layer (dota_client.py, 321 lines; dota_manager.py, 338 lines) has zero tests — only the pure signal functions are covered (47 tests in test_dota_signals.py). The claimed crash paths do not exist: malformed leaderboard entries are skipped by a per-entry try/except (dota_client.py:219-230) and fetch_token_price catches all exceptions and returns (None, None, None), with DOTAManager.fetch_and_compute adding a further try/except around every client call. The gap's real cost is that this graceful-degradation behavior is unpinned, so a regression (e.g., removing a guard or reshaping the parse) would not be caught by any test.

**Failure scenario:** The DOTA API already moved hosts once (memory: 'API moved to DigitalOcean'); if it returns games_won: null or a non-numeric priceUsd, int(None)/float(None) raises TypeError inside fetch_leaderboard/fetch_token_price and the DOTA screen enters an error loop — no test would catch either the crash or a graceful-degradation regression.

**Suggested fix:** Add tests/data/test_dota_client.py with MockTransport fixtures for the leaderboard/game-state/DexScreener endpoints, including null/missing-field variants of the real payload shapes.

### LOW-11: `maxpane_dashboard/data/frenpet_manager.py:535` — architecture (architecture)

_safe_call is duplicated 7 times across managers in 3 drifted variants: the frenpet/base variant logs fn.__name__ at warning level, cattown/dota/ocm at debug, and only ttt/talismans use getattr(fn, '__name__', fn) — in the 5 older copies the exception handler itself can raise, defeating the helper's 'never crash the dashboard' contract.

**Failure scenario:** If any of the 5 older managers ever passes a callable without __name__ (functools.partial, a callable object) to _safe_call and that callable raises, the handler's `fn.__name__` raises AttributeError which escapes _safe_call and propagates into fetch_and_compute, turning a should-be-degraded analytics failure into a failed refresh cycle. Latent today (current call sites pass plain functions), but the trap is invisible because the fixed and broken variants look identical at the call site.

**Suggested fix:** Move the ttt/talismans variant into one shared util (e.g. data/_util.py) and delete the 6 duplicates.

### LOW-12: `maxpane_dashboard/data/talismans_manager.py:182` — correctness (talismans)

cores_invariant_intact (talismans_manager.py:182) collapses the syncing/intact/drift tri-state into a bool, so on any incomplete enumeration sweep (failed or partial token-state fetch, flags failure, or ids minted outside the log lookback on a cold cache) the TOTAL CORES hero box renders a false yellow 'DRIFT' (tal_hero_metrics.py:143-146) while the Signals panel simultaneously shows CONSERVATION=SYNCING; note a fully successful first sweep is unaffected since the baseline is locked in the same cycle.

**Failure scenario:** On the first refresh cycles before the baseline is set, or during any partially-failed sweep, enumeration_complete is False so cores_invariant_intact=False; tal_hero_metrics.py:143-145 renders that as '[yellow]DRIFT[/]' while the Signals panel simultaneously and correctly shows CONSERVATION=SYNCING. The user sees a contradictory false alarm about the dashboard's central invariant.

**Suggested fix:** Pass the same tri-state the signal layer uses (e.g. 'syncing'/'intact'/'drift') to the hero widget and render syncing as a dim placeholder instead of DRIFT.

### LOW-13: `maxpane_dashboard/data/talismans_manager.py:217` — blocking-io (async)

TalismansManager.fetch_and_compute (talismans_manager.py:217) synchronously saves the full cache (~420 KB JSON: ~1,536 pydantic tokens, 200 events, never-pruned seen_tx_ops) on the Textual event loop every 30 s poll cycle — measured ~12 ms per save (growing with seen_tx_ops, ~36 ms at 50k keys), dominated by model_dump/json CPU rather than disk; all other managers persist only in close(). At most a one-frame UI hiccup per cycle; fix by saving in close()/periodically or via asyncio.to_thread.

**Failure scenario:** Every 30 seconds the event loop blocks for the model_dump + JSON serialization + file write of the full cache (hundreds of KB); on slower disks or as seen_tx_ops grows without bound (it is never pruned, and is persisted and reloaded), this causes a periodic UI stutter in the TUI. All other managers persist only on quit; only Talismans does it per-cycle.

**Suggested fix:** Persist on close() like the other managers, or offload the dump to a thread (asyncio.to_thread) and prune seen_tx_ops to a bounded window.

### LOW-14: `maxpane_dashboard/data/ttt_cache.py:408` — correctness (ttt)

fees_eth_lifetime is recomputed every refresh from fee buckets that prune_old (called at ttt_manager.py:213, immediately before per_token_fees at :218) truncates to 25h, and update_token_fees overwrites rather than accumulates the value; with pruned buckets also being what gets persisted, the fees table's LIFETIME column (ttt_fees_table.py:88/112) can never show more than ~25h of fee history, contradicting both its header and the per_token_fees docstring's "since the cache started" claim.

**Failure scenario:** A token earns 5 ETH of holder-share fees over a week while the dashboard runs; prune_old (line 368) drops all buckets older than 25h each cycle, so sum_total only covers the last 25h (say 0.3 ETH) -> widgets/ttt/ttt_fees_table.py shows 'LIFETIME 0.3' -- understated by ~94% and nearly identical to the 24H column, making the column meaningless and misleading.

**Suggested fix:** Either keep a separate monotonically-increasing lifetime counter per token that prune_old does not touch, or rename the column to a 24h-scoped label.

### LOW-15: `maxpane_dashboard/data/ttt_client.py:788` — stale-cache (ttt)

_multicall swallows total-RPC-failure exceptions and returns all-False, so fetch_token_reservoirs (ttt_client.py:788) reports 0 wei for every address instead of raising; this bypasses the manager's except-continue cache-fallback guard (ttt_manager.py:517-522) and update_token_reservoir overwrites cached reservoir balances with zeros, transiently flipping the "Buybacks ready" signal to "0 buybacks ready" for that cycle. Fix: have fetch_token_reservoirs omit failed entries (like fetch_token_metadata) or raise when the whole batch fails.

**Failure scenario:** One transient RPC outage during the reservoir refresh -> _multicall returns [(False,'0x')]*N -> every address is reported as 0 -> update_token_reservoir overwrites last-known balances with 0 -> buybacks_ready_signal drops from 'N buybacks ready (Σ x Ξ bounty)' to '0 buybacks ready' for that cycle even though nothing changed on-chain, contradicting the module's own 'caller falls back to cache' contract.

**Suggested fix:** Omit failed addresses from the result dict (like fetch_token_metadata does) so cached values are preserved.

### LOW-16: `maxpane_dashboard/data/ttt_manager.py:474` — correctness (ttt)

The Bought (buyback) event scan in ttt_manager.py:474 caps the eth_getLogs address filter to known[:200] — the 200 oldest launches, since cache.tokens is insertion-ordered by launch and never re-sorted — so once more than 200 tokens have launched (currently 121 of 10,000 on-chain), buyback events for newer tokens are silently and permanently omitted from the activity feed (the watermark at line 489 still advances, so missed events cannot be back-filled). The buybacks-ready/bounty signal is unaffected because reservoirs are fetched for all tokens without a cap.

**Failure scenario:** The collection reaches 500 launched tokens; cache.tokens preserves registration (launch) order, so known[:200] is the 200 oldest launches. A buyback fires on token #350 -> no Bought log is ever requested for it -> the activity feed and bounty context omit exactly the newest, most actively traded tokens with no error or indication anywhere.

**Suggested fix:** Select the 200 most relevant tokens (e.g. newest launch_block or highest reservoir_wei) instead of the oldest, or rotate through the address list across cycles.

### LOW-17: `maxpane_dashboard/screens/base_terminal.py:92` — correctness (bakery-base)

On refresh failure, BaseTerminalScreen's except-branch (base_terminal.py:92) hardcodes error_count=0 to the StatusBar even though BaseManager has just incremented _error_count, suppressing (and potentially resetting) the error indicator during active failures; all sibling screens pass the manager's real _error_count in the same branch.

**Failure scenario:** fetch_and_compute raises (e.g. network down); BaseManager increments _error_count, but the except-branch calls StatusBar.update_data(error_count=0), so the status bar reports zero errors while the dashboard is actually failing — unlike bakery.py:106 which passes the manager's real _error_count.

**Suggested fix:** Pass self._manager._error_count (or expose a public property) in the error path, matching BakeryScreen.

### LOW-18: `maxpane_dashboard/screens/frenpet.py:107` — dead-data-key (frenpet)

FrenPet overview title bar reads population_stats['total_pets']/['active_pets'] (frenpet.py:107-108) but both calculate_population_stats and the _safe_call fallback in frenpet_manager.py produce keys 'total'/'active', so total is always 0 and the 'X/Y active' header silently never displays.

**Failure scenario:** calculate_population_stats (frenpet_population.py:87-96) returns keys 'total' and 'active'. data.get('population_stats').get('total_pets', 0) is always 0, so the truthiness check at line 109 always fails and the title permanently shows plain 'FrenPet · Overview' even with a fully loaded population — the active/total counts are silently never displayed.

**Suggested fix:** Change the lookups to population_stats.get('total') and .get('active').

### LOW-19: `maxpane_dashboard/screens/game_select.py:86` — resource-leak (core)

Pressing 'q' on the game-select menu calls self.app.exit() directly, bypassing MaxPaneApp.action_quit, so no manager close() runs: httpx clients are never closed and caches are never persisted.

**Failure scenario:** User views a dashboard, presses 'm' to return to the menu, then 'q' to quit: app exits immediately without awaiting any manager.close() (confirmed with a headless pilot — monkeypatched close() hooks were never called), so save_cache() for bakery/frenpet history never runs (session history lost) and all 11 managers' httpx.AsyncClient instances are abandoned at event-loop teardown. Quitting from a game screen goes through action_quit and behaves correctly, making the two quit paths inconsistent.

**Suggested fix:** Replace self.app.exit() with self.app.run_action("quit") (or simply remove the on_key branch and let the app-level 'q' binding handle it) so the graceful shutdown path always runs.

### LOW-20: `maxpane_dashboard/widgets/activity_feed.py:93` — correctness (widgets)

When the activity feed is empty, 'No activity yet' is appended to the RichLog on every poll cycle, accumulating duplicate lines indefinitely.

**Failure scenario:** getActivityFeed returns [] on every refresh (new season, quiet game). update_data hits `if not events: if not self._seen_keys: log.write(...)` each poll; _seen_keys stays empty, so a new '  No activity yet' line is appended every poll_interval seconds (30s default -> 120 duplicate lines after an hour, and the log scrolls). Same bug copied into templates/activity_feed_template.py line 90.

**Suggested fix:** Track a _placeholder_written flag (or write the placeholder once in on_mount) instead of keying off _seen_keys.

### LOW-21: `scripts/extract_cattown_abis.py:18` — stale-path (cattown)

scripts/extract_cattown_abis.py (and validate_cattown_abis.py) still write/read the pre-rename dashboard/abis/cattown path, so an ABI refresh silently lands in a dead untracked directory and the canonical reference ABIs in maxpane_dashboard/abis/cattown/ go stale — but these JSONs are dev reference artifacts only; the app decodes via hardcoded selectors in cattown_client.py and never loads them at runtime.

**Failure scenario:** Run `python scripts/extract_cattown_abis.py` after a cat.town contract upgrade: the script silently creates a fresh /Library/Vibes/autopull/dashboard/abis/cattown/ (ABI_DIR.mkdir(parents=True) on line 19), saves the newly extracted ABIs there, and reports success — while the app keeps decoding against the stale ABIs in maxpane_dashboard/abis/cattown/. The refresh appears to have worked but changes nothing.

**Suggested fix:** Change ABI_DIR to ROOT / 'maxpane_dashboard' / 'abis' / 'cattown', and move the mkdir out of module import into main().

### LOW-22: `scripts/validate_cattown_abis.py:17` — stale-path (cattown)

scripts/validate_cattown_abis.py line 17 still points ABI_DIR at the pre-rename dashboard/abis/cattown path, so the standalone dev validation script deterministically reports 0/6 PASS ("ABI file not found") and exits 1; the actual ABIs live in maxpane_dashboard/abis/cattown/ and shipped dashboards are unaffected.

**Failure scenario:** Run `python scripts/validate_cattown_abis.py`: /Library/Vibes/autopull/dashboard does not exist (verified), so abi_path.exists() is False for all 6 contracts, validate_contract returns False for each, and the validator reports 0/6 PASS regardless of the actual (correct) ABIs living in maxpane_dashboard/abis/cattown/. The ABI-validation tool is completely non-functional.

**Suggested fix:** Change ABI_DIR to ROOT / 'maxpane_dashboard' / 'abis' / 'cattown'.


## Refuted findings (for the record)

- `maxpane_dashboard/data/client.py:179` — get_active_season lacks an empty-list guard at client.py:179, but the between-seasons state cited as the trigger verifiably returns a non-empty inactive-season list handled by the existing fallback; the missing guard is a defensive-coding nit, not a reachable dashboard-killing failure.

- `maxpane_dashboard/templates/leaderboard_template.py:80` — GameLeaderboard.update_data crashes on plausible entry shapes: float(score) raises on None or non-numeric strings, and _short_addr(entry.get('address', '?')) raises TypeError when 'address' is present but None.

- `tests/widgets/test_talismans_widgets.py:1` — UI-layer tests exist only for the newest dashboard: talismans has 7 headless widget tests and 2 screen tests, but the other 7 dashboards' widget packages (widgets/base, cattown, dota, frenpet, ocm, ttt) plus the shared widgets (cookie_chart, ev_table, leaderboard, signals_panel, hero_metrics, activi


## Reality check


### External data-source liveness

Probed all 20 external data sources in maxpane_dashboard/data/ (5 game APIs, 8 market/price APIs + 1 site scrape, 7 RPC endpoints). Three real reality-check findings: (1) The DOTA game API at wc2-agentic-dev-3o6un.ondigitalocean.app is GONE — NXDOMAIN, app deleted — so the DOTA dashboard's game-state and leaderboard widgets are permanently dead (only the DexScreener price widget survives, showing a near-dead token); the game appears dead. (2) api.reservoir.tools no longer resolves (Reservoir sunset its API), so TTT's NFT floor widget can never populate — gracefully tolerated but dead code plus wasted retries. (3) RugPull Bakery's tRPC API is alive with intact shapes, but there has been no active season for ~3 weeks (season 10 finalized 2026-06-12, top bakery has 0 active cooks); get_active_season silently falls back to displaying the finalized season, so the dashboard shows a finished game as current. RPC hygiene: cloudflare-eth.com (TTT primary) is degraded (refuses eth_blockNumber with -32046 — the code explicitly anticipates this and falls over), rpc.ankr.com/eth now requires an API key (dead for this keyless project), and eth.llamarpc.com returns 521 (origin down) — all handled by the fallover logic but worth pruning; publicnode, drpc, and mainnet.base.org are healthy. Everything else is fully alive and shape-compatible: Cat Town (active competition running), FrenPet Ponder GraphQL, DexScreener (both endpoint styles), GeckoTerminal, Clanker, CoinGecko, and the tenthousandtokens.net SSR scrape (regex still matches 130 tokens). Bankr is unverifiable keyless but inert by design without BANKR_API_KEY.


**Wrong / outdated:**

- **[wrong]** DOTA data source https://wc2-agentic-dev-3o6un.ondigitalocean.app (game state + leaderboard) works as the code expects
  - The DigitalOcean app's hostname no longer resolves (NXDOMAIN) — the app has been deleted, not just down. fetch_game_state and fetch_leaderboard can never succeed; the DOTA dashboard's live-game widgets are permanently dead and every poll burns 3 retries with 2/4/8s backoff per endpoint. Only the DexScreener token-price widget still has data (token trades at ~$0.000001344 with 0 recent txns — the token itself is near-dead too). This looks like a dead game; the DOTA dashboard needs a new API base or retirement.

- **[wrong]** TTT data source https://api.reservoir.tools/collections/v7 (NFT floor + 24h sales) works as the code expects
  - api.reservoir.tools no longer resolves — Reservoir sunset its NFT API after the Relay pivot, so the 'keyless tier' the code targets is gone entirely. fetch_nft_floor tolerates this (returns None after 3 retries with backoff), so the dashboard doesn't crash, but the floor/sales widget can never populate and each poll wastes ~7s of retry backoff. The code path should be removed or replaced (e.g. an onchain or marketplace-free source).

- **[outdated]** RugPull Bakery data source https://www.rugpullbakery.com/api/trpc works as the code expects
  - Endpoint alive and response shapes still match the models (tRPC envelope, season fields, paginated bakery items). But there has been NO active season for ~3 weeks: the only season returned is finalized (ended 2026-06-12), the top bakery shows activeCookCount 0, and get_active_season silently falls back to returning that finalized season. The dashboard renders, but it renders a completed season as if it were current — the game is dormant or wound down between seasons. Worth a 'season ended' state in the UI or a health check on isActive.

- **[outdated]** TTT data source https://cloudflare-eth.com (primary Ethereum RPC) works as the code expects
  - Cloudflare's public gateway is degraded: it answers eth_chainId but refuses eth_blockNumber with -32046. The client code literally has a comment anticipating -32046 from this host and falls over to eth.drpc.org (verified working), so TTT data still flows — but the 'primary' RPC fails the very first call of most poll cycles, adding a wasted request + fallover hop every time. Consider promoting eth.drpc.org or publicnode to primary.

- **[outdated]** TTT/Talismans fallback RPC https://rpc.ankr.com/eth works as the code expects (keyless)
  - Ankr ended its keyless public endpoint — it now requires an API key, which violates this project's keyless-only rule. The fallover logic treats the -32000 error as endpoint failure and moves on, so nothing breaks, but this entry is dead weight in both fallback chains and should be replaced (e.g. with ethereum-rpc.publicnode.com, already proven working).

- **[wrong]** TTT fallback RPC https://eth.llamarpc.com works as the code expects
  - eth.llamarpc.com returns Cloudflare 521 on every request — the origin is down. The client's _ENDPOINT_DEAD_CODES set includes 521 so it skips immediately without retries, but as the last fallback it provides zero redundancy and should be swapped out.


**Verified accurate:** 13 claims — Cat Town data source https://api.cat.town/v1/fishing/competition/leaderboard wor; Cat Town data source https://api.cat.town/v1/tickets/leaderboard (raffle) works ; FrenPet data source https://api.pet.game (Ponder GraphQL) works as the code expe; DexScreener data source https://api.dexscreener.com/latest/dex/tokens/{addr} (DO; TTT data source https://api.dexscreener.com/tokens/v1/ethereum/{addresses} (batc; Base dashboard data source https://api.geckoterminal.com/api/v2 (trending_pools ; Base dashboard data source https://www.clanker.world/api/tokens works as the cod; CoinGecko data source https://api.coingecko.com/api/v3/simple/price (ETH/USD) wo …


### Docs vs. code

Audited README.md, both CLAUDE.md versions (committed + working tree), docs/*.md plans, and repo media against the actual code. Headline findings: (1) README is the most user-visible offender — it claims "6 onchain games" and lists 6 dashboards, but the code ships 8 (TTT and Talismans missing from the table, the --game flag list, and the themes list, which omits the 9th theme `talismans`); everything else in README checks out (install commands, PyPI package maxpane 0.4.0, Python 3.11+, repo URL github.com/banse/maxpane, Rust intro build path/binary, keyboard shortcuts m/tab/r/t/q — though the `c` view-toggle on TTT/Talismans and menu number keys are undocumented). (2) CLAUDE.md: the working-tree rewrite fixes only the overview; it still falsely claims AutoPet infrastructure reuse (no executor/transactor/keystore/nonce code exists), and everything below — backend/frontend architecture tree, backend/requirements.txt, npm frontend build, python -m backend.main, tests/strategy/ paths, and all 10 listed MAXPANE_* env vars — is dead; real env vars are MAXPANE_WALLET, MAXPANE_ETH_RPC_URL, MAXPANE_BASEBOARD_ENV, MAXPANE_INDEXER_DB. Real test tree: tests/{analytics,data,screens,widgets}, 796 tests. (3) Docs: the Rust-intro plan and talismans ABI recon match the built code; MAXPANE_PRD.md's "Pane Protocol" was never built; cattown/ocm plans use the stale dashboard/ package prefix and several planned tests were never written — OCM has zero tests. (4) Media: all Greenshot pngs/screenshots/.mov are gitignored and untracked (pack is 793 KiB — no repo bloat), but ~85 MB of untracked media plus a 1.3 GB Rust target/ clutter the working tree and can be deleted without any git loss.


**Wrong / outdated:**

- **[wrong]** README: "Track leaderboards, signals, trends, and analytics for 6 onchain games"
  - There are 8 dashboards. app.py _GAME_CYCLE = ["base", "frenpet", "cattown", "dota", "bakery", "ocm", "ttt", "talismans"] and game_select.py lists 8 entries including Ten Thousand Tokens and Talismans.

- **[outdated]** README Dashboards table lists 6 games (Base Trading, FrenPet, Cat Town, DOTA, Rugpull Bakery, OCM)
  - Missing two rows: Ten Thousand Tokens (Ethereum, "NFT collection w/ UniV4 burn-to-launch") and Talismans (Ethereum, "Core-conservation NFT collection"). Both are fully wired (screens/ttt.py, screens/talismans.py, TTTManager, TalismansManager).

- **[outdated]** README: "Terminal dashboard for blockchain games on Base, Abstract, and Ethereum"
  - Chain list is still accurate (Base, Abstract, Ethereum), but "blockchain games" undersells scope: Base Trading is a trading dashboard and TTT/Talismans are NFT-collection dashboards. The working-tree CLAUDE.md itself says the project "expanded to NFT and trading dashboards".

- **[outdated]** README usage lists --game frenpet/base/cattown/dota/ocm as the game flags
  - Real choices are bakery, frenpet, frenpet_full, frenpet_wallet, frenpet_perf, base, cattown, ocm, dota, ttt, talismans. README omits `--game ttt` and `--game talismans` (public dashboards) and the three hidden FrenPet variants. Also undocumented: --wallet and --log-level flags.

- **[outdated]** README available themes: matrix minimal bloomberg htop retro bakery frenpet base (8 themes)
  - There are 9 themes; `talismans` (antique gold + violet) is missing from the README. __main__.py --theme choices and themes/__init__.py both include it.

- **[outdated]** Committed CLAUDE.md (HEAD): "MaxPane is an automation service for the RugPull Bakery game on Abstract" plus contract addresses, boost/attack tables, tRPC endpoints, bootstrap endpoints
  - Entirely superseded. The product is a read-only multi-dashboard Textual TUI (maxpane_dashboard/). No automation, no transaction signing, no game API client for bot actions. The uncommitted working-tree CLAUDE.md (git diff CLAUDE.md) replaces this overview with the correct "CLI app for onchain dashboards" description, but only the overview section was rewritten.

- **[wrong]** Working-tree CLAUDE.md: "MaxPane reuses AutoPet's proven infrastructure (executor, transactor, event bus, scheduler, API/dashboard, keystore, nonce management, spending guard)"
  - None of that code exists in this repo. grep for executor/transactor/nonce/keystore/spending across maxpane_dashboard/*.py returns zero files. The codebase is data clients + caches + analytics + Textual widgets/screens only. This sentence survived the rewrite but describes a project that was never built here.

- **[outdated]** Working-tree CLAUDE.md: "The details for all added games can be found in the docs subdirectory"
  - Mostly true — docs/ has game-mechanics files for bakery, cattown, dota, ocm, talismans, and tenthousandtokens — but there is no FrenPet doc and no Base Trading doc, so "all added games" overclaims.

- **[wrong]** CLAUDE.md Architecture section: maxpane/ contains backend/ (core, scheduler, strategy, executor, api, abis, main.py, service_loop.py) and frontend/ (React + Vite), Dockerfile, docker-compose.yml
  - No backend/ or frontend/ directory exists anywhere in the repo (ls: No such file or directory), no Dockerfile, no docker-compose.yml. Actual layout: maxpane_dashboard/ (Python Textual TUI: data/, analytics/, widgets/, screens/, themes/, templates/, abis/), maxpane/ (Rust intro binary), tests/, scripts/, docs/. The section does carry a self-disclaimer ("may be outdated") but every path in it is dead.

- **[wrong]** CLAUDE.md Build & Run: `python3.11 -m venv .venv` + `pip install -r backend/requirements.txt`; frontend: `cd frontend && npm install && npm run build`
  - backend/requirements.txt does not exist (no requirements.txt anywhere in the repo) and there is no frontend/. Actual install: `pip install -e .` (hatchling) or `pipx install maxpane`. scripts/start.sh even prints an error referencing the nonexistent requirements.txt.

- **[outdated]** CLAUDE.md Run: `python -m backend.main` or `./scripts/start.sh`
  - `python -m backend.main` cannot work (no backend package). Actual entry points: `maxpane` console script or `python -m maxpane_dashboard`. `./scripts/start.sh` does exist and works — it builds/runs the Rust intro then execs `python -m maxpane_dashboard`, so half the claim survives.

- **[outdated]** CLAUDE.md Tests: `pytest`, `pytest tests/strategy/`, `pytest tests/strategy/test_boost.py::test_ev_calculation`, `pytest -x`
  - `pytest` works (796 tests collected) and `-x` is fine, but tests/strategy/ does not exist — subdirectories are tests/analytics, tests/data, tests/screens, tests/widgets. There is no test_boost.py; the closest EV tests live in tests/analytics/test_ev.py.

- **[wrong]** CLAUDE.md Environment Variables: MAXPANE_KEYSTORE_PATH, MAXPANE_KEYSTORE_PASSWORD, MAXPANE_RPC_URL, MAXPANE_BACKUP_RPC_URL, MAXPANE_BAKERY_ID, MAXPANE_DAILY_GAS_LIMIT_ETH, MAXPANE_DRY_RUN, MAXPANE_LOG_LEVEL, MAXPANE_API_PORT, MAXPANE_API_TOKEN
  - None of these are read anywhere in the code. Actual env vars consumed: MAXPANE_WALLET (config.py:51), MAXPANE_ETH_RPC_URL (data/ocm_client.py:43), MAXPANE_BASEBOARD_ENV (data/base_manager.py:20), MAXPANE_INDEXER_DB (data/frenpet_client.py:76), plus MAXPANE_INTRO_SHOWN exported by scripts/start.sh.

- **[outdated]** CLAUDE.md Strategy Considerations: "The bot's primary value is in strategic decision-making... automate baking, boost timing, attack timing, cookie budget"
  - There is no bot. The product is a read-only dashboard; nothing signs or submits transactions. Fragments survive as display analytics only (analytics/ev.py EV table, analytics/leaderboard.py, widgets/ev_table.py), so the EV/leaderboard concepts became visualizations, not automation.

- **[outdated]** CLAUDE.md "Key Differences from AutoPet" table (chains, VRF vs commit-reveal, reward models, strategy focus)
  - Describes the abandoned bakery-bot framing. The game facts (Abstract 2741, VRF, season prize pool) are still true of the game itself, but as a description of this project's design it is obsolete — the table compares two automation bots, and MaxPane is neither.

- **[outdated]** docs/MAXPANE_PRD.md: MAXPANE is "an open-source terminal framework and the Pane Protocol — an open standard that lets any dApp describe its terminal-based frontend as a JSON schema", with Phase 2 transaction signing and Phase 3 multiplayer
  - Aspirational pre-MVP vision (dated 2026-03-27) that was never built. No Pane Protocol, no JSON schema renderer, no community panes, no tx signing, no shared sessions exist. The shipped product is a fixed set of hand-built game/NFT/trading dashboards.

- **[outdated]** docs/cattown_implementation_plan.md: new files under dashboard/data/, dashboard/analytics/, dashboard/widgets/cattown/, dashboard/screens/cattown.py plus tests test_cattown_client/cache/manager/conditions/economy/signals
  - All runtime files were built, but under maxpane_dashboard/ — the plan's dashboard/ package prefix is stale (package renamed for PyPI). Test gaps: tests/data/test_cattown_client.py and the three analytics test files exist, but planned tests/data/test_cattown_cache.py and tests/data/test_cattown_manager.py were never created.

- **[outdated]** docs/ocm_implementation_plan.md: 13 new files including 6 widgets (ocm_hero_metrics, ocm_staking_overview, ocm_sparklines, ocm_signals, ocm_activity_feed, ocm_supply_breakdown), manager, screen, plus tests/analytics/test_ocm_signals.py; visual test via `python -m dashboard --game ocm`
  - All runtime files exist with exactly the planned names (under maxpane_dashboard/, not dashboard/). But the planned tests/analytics/test_ocm_signals.py was never written — there are zero OCM tests in the whole test suite (grep 'ocm' in tests/ returns nothing). The launch command is now `python -m maxpane_dashboard --game ocm`.


**Verified accurate:** 11 claims — README install: pipx install maxpane / uv tool install maxpane / pip install max; README: "Requires Python 3.11+"; README: git clone https://github.com/banse/maxpane.git; README: Rust intro built via `cd maxpane && cargo build --release`, binary at ./; README usage: `maxpane` launches with default game bakery; --theme minimal; --po; README keyboard shortcuts: m = menu, tab = next game, r = refresh, t = cycle the; Working-tree CLAUDE.md: "MaxPane is a CLI app for onchain dashboards... expanded; docs/IMPLEMENTATION_PLAN.md + docs/MAXPANE_Intro_PRD.md: standalone Rust TUI int …


### Packaging & release pipeline

Release pipeline is fundamentally sound: pyproject (0.4.0), tag v0.4.0, and PyPI (0.4.0 live, confirmed via pip index) all agree; the freshly built wheel contains every data file (10 abis/*.json + themes/minimal.tcss, though only the .tcss is loaded at runtime — ABIs are reference-only); publish.yml triggers on v* tag push and uses PyPI trusted publishing (id-token: write, no token); and the name 'maxpane' is consistent across dist name, console script, and README install commands (import name is maxpane_dashboard by design). Two real discrepancies: (1) there is no --version CLI flag — `maxpane --version` errors — despite __version__ existing in maxpane_dashboard/__init__.py, and (2) the dev venv's editable install has stale metadata so __version__ reports 0.3.2 at runtime until `pip install -e .` is re-run; local dist/ likewise holds only stale 0.3.2 artifacts from April. Minor: the Rust helper crate is unsynced at 0.1.0.


**Wrong / outdated:**

- **[outdated]** maxpane_dashboard.__version__ agrees with pyproject's 0.4.0
  - The mechanism is correct-by-construction for end users (it reads installed dist metadata, so PyPI installs always match). But the dev venv's editable install has stale metadata from when pyproject said 0.3.2, so __version__ currently reports 0.3.2 at runtime, not 0.4.0. A `pip install -e .` re-run refreshes it. Not a packaging bug, but locally inconsistent right now.

- **[wrong]** The CLI exposes a --version flag
  - No --version flag exists anywhere in the package. There is no way to check the installed version from the CLI; a `parser.add_argument("--version", action="version", version=__version__)` would be a one-line fix. (Side note: the bundled Rust crate maxpane/Cargo.toml is at version 0.1.0, unsynced with the Python dist.)


**Verified accurate:** 5 claims — pyproject.toml declares version 0.4.0 and it matches the latest git tag; The built wheel contains the non-Python data files the app needs at runtime (abi; .github/workflows/publish.yml triggers on version tags and publishes via trusted; PyPI package name 'maxpane' is consistent with the import name and README instal; The last actually built/published version matches pyproject's 0.4.0


### Smoke run

Reality check passes: a fresh user can run every advertised dashboard without a crash. (1) Clean import. (2) CLI --help works and lists all 8 games (bakery, frenpet, base, cattown, dota, ocm, ttt, talismans) plus 3 hidden frenpet variants. (3) 24/24 headless Textual runs succeeded — all 8 screens mounted via App.run_test() and survived both injected fetch failures and real (partially blocked) network, and the full app flow (splash → game select via keys 1-8 → dashboard) worked for every game; screens catch fetch errors in _do_refresh so network failure degrades gracefully. (4) Scripts have no path bit-rot (venv, data/, Rust intro binary all exist), but three warts: launch.sh and launch-maximized.sh crash with 'TERM_PROGRAM: unbound variable' when that env var is unset (set -u + unguarded expansion — reproduced; fix is ${TERM_PROGRAM:-}); start.sh/dashboard.sh's venv-missing hint references a nonexistent requirements.txt; usage comments omit dota/ttt/talismans. One live-data wart: Cat Town's ActivityEvent pydantic model rejects launcher=None now returned by the API (logged and swallowed, rows dropped, no crash). Tested on branch talismans-dashboard working tree, which includes uncommitted edits to maxpane_dashboard/app.py and data/frenpet_manager.py.


**Wrong / outdated:**

- **[wrong]** scripts/launch.sh and scripts/launch-maximized.sh run in any terminal
  - These two launchers crash immediately in any environment that does not set TERM_PROGRAM (ssh sessions, plain xterm, CI, non-macOS terminals). One-character fix: use ${TERM_PROGRAM:-} as the other scripts do.

- **[outdated]** start.sh / dashboard.sh venv-missing hint ('pip install -r requirements.txt') points at a real file
  - A fresh user without a venv would be told to install from a nonexistent file; correct instruction is `pip install -e .` (or pipx/uv per the PyPI packaging setup). Cosmetic but misleading for exactly the fresh-user scenario.

- **[outdated]** Script usage comments document the available --game values
  - Purely cosmetic doc rot in header comments; args are passed through via "$@" so all 8 games actually work through every script.

- **[wrong]** Cat Town manager parses live API activity data cleanly
  - The live Cat Town API now returns launcher=None for some activity events, which the pydantic ActivityEvent model rejects; the widget silently loses those rows. Non-fatal (does not crash), but the model should make `launcher` Optional to match current API reality.


**Verified accurate:** 5 claims — The package imports cleanly (python -c "import maxpane_dashboard; import maxpane; python -m maxpane_dashboard --help works and lists all 8 games as --game choices; Every one of the 8 game screens mounts headlessly without crashing, including wh; The full app flow (MaxPaneApp -> splash -> game select -> dashboard) works headl; scripts/*.sh reference paths that exist (no path bit-rot)


## Reviewer scope notes (overall assessment per area)


### talismans
The Talismans data layer is well-built where it was hardest: I verified the custom dynamic-tuple tokenData decode, the aggregate3 encode/decode (offsets, bounds, string slicing), burned-id handling (ownerOf revert -> skipped), and the event decoders (including Cut's two-word data layout) live against Ethereum mainnet — all exactly correct and matching the recon doc; the materials/essence table matches the verified source, division-by-zero and None paths in the signals are guarded, dedupe/watermark cache persistence is atomic and corruption-tolerant, the httpx client and manager are properly closed on app shutdown, and all 106 talismans tests pass. No unrevealed (owned but coreCount==0) tokens currently exist, so the core_count==0 skip is presently safe. The systemic weakness is failure signaling and id discovery: the client converts every transport failure into zero/empty sentinels so the manager cannot distinguish 'RPC down' from 'value is zero' (findings 2-4), and — live-confirmed today — a fresh install discovers none of the 182 live post-genesis tokens because id discovery relies solely on a 250k-block log lookback that all transformation activity now predates (finding 1), leaving every headline metric (mythics, total cores, conservation, leaderboard, activity) permanently wrong for new users. fetch_transfer_logs is currently dead code. RPC pacing (50ms inter-call delay, ~15 requests per 30s cycle, retry + 4-endpoint fallback) is reasonable for keyless public endpoints.


### ttt
The TTT data layer is generally well-built: I independently verified every hardcoded function selector and event topic hash via keccak256 against the ABI JSONs (all correct, including the tricky Launched-vs-BurnAndLaunch and 7-field Deposited signatures), hand-checked the stdlib-only aggregate3 encode/decode against the ABI spec (correct, including nested dynamic-tuple offsets), and confirmed the SCALE=1e30 and holderShare-direct-read semantics are honored; the screen layer is defensively wrapped and cannot crash the TUI, and httpx clients are closed via the app's shutdown path. The serious problem is the refresh cycle's event pipeline: the incremental scan window bug (min instead of max) combined with non-idempotent cache applicators means fee/launch/activity data double-counts on every 30-second poll and persists inflated to disk -- this is the single defect that makes the dashboard's headline holder-pool and fee numbers wrong within minutes of running, verified by direct simulation against the real cache code. The remaining findings are error-handling gaps where transient public-RPC failures are masked as legitimate zeros (factory state, reservoirs) or cause silent permanent event loss (swallowed getLogs chunks under an advancing watermark), plus two smaller display-correctness issues (25h-truncated "LIFETIME" fees, oldest-200 buyback cap).


### core
The app core is generally well built: graceful shutdown closes all 11 managers with per-manager exception guards, every game screen uses on_screen_resume/on_screen_suspend to start/stop its poll timer (so suspended screens do not poll — no poller leak on game switches), wallet-address validation in wallet_input.py is correct, theme registration/cycling works (verified headlessly), and the uncommitted diff is sound — fetch_rewards=True is correctly scoped to _frenpet_wallet_manager, the only consumer of wallet_rewards. I also probed several suspected screen-stack crash paths ('m'/tab on splash and menu, ScreenStackError on pop) with a headless pilot and they all self-heal, so they are not reported. The real defects found: an unguarded startup prefetch worker that crashes the app when the first fetch fails (confirmed, hits the default launch path offline or on a flaky API), the Tab game-cycling binding being permanently shadowed by Textual Screen's built-in focus_next binding (confirmed dead, contradicting the on-screen hint), quit-time clobbering of the shared frenpet history cache by the three idle FrenPetManager instances, plus smaller CLI/quit-path gaps (--game frenpet_* choices unreachable, menu 'q' bypassing graceful shutdown, unvalidated --poll-interval).


### frenpet
The FrenPet stack is defensively written overall (retry/backoff in the client, _safe_call around analytics, per-widget try/except in screens, owned httpx clients closed on quit, atomic cache writes), and the uncommitted fetch_rewards change is correct: only _frenpet_wallet_manager gets fetch_rewards=True, FrenPetWalletScreen is the only screen that renders wallet_rewards, and neither FrenPetPerfScreen nor FrenPetFullScreen's wallet view touches that key — so the gating removes ~8 serialized RPC calls per refresh from the other three managers with no rendering regression (tests pass 29/29). The real defects cluster in data-contract drift between the manager's output dict and the screens/widgets: keys read that are never produced ('apr', 'all_scores', 'population_pets', 'total_pets'), raw 1e18 on-chain values rendered unscaled on the wallet hero (verified against live Base RPC), a per-day velocity mislabeled '/hr' on the Performance view, plus a broken RPC-log fallback for battle rate and a shared cache file that the last-closed manager clobbers on quit.


### cattown
The Cat Town stack is fundamentally sound: I recomputed every function selector and event topic hash (all correct), traced the ABI-encoding decode paths for getCurrentCompetition, the tuple[50] leaderboard structs, and the FishCaught/TreasureFound event data layouts against the checked-in ABI JSONs (all slot offsets correct), and live-verified on Base that token0 of the Sushi pair is WETH so the reserve-ratio price math is right. Wei-to-token conversions consistently use 1e18, the 70/10/10/7.5/2.5 revenue-split constants match between client and economy module, division-by-zero guards are present throughout the analytics, and the manager/_safe_call + per-widget try/except layering means most single-source failures degrade gracefully rather than crashing the TUI. The real defects are in the edge paths: corrupt-cache handling that can crash the whole app at startup, month-boundary date math in the competition-timing fallback (reproduced ValueError), an unmemoized serial per-block timestamp fan-out that both re-hammers the rate-limited public RPC every 30s and substitutes block numbers for timestamps on failure, both ABI maintenance scripts still pointing at the pre-rename dashboard/ directory (making the validator always fail and the extractor write to a dead location), and a provably dead oracle fallback plus an ETH-priced value exported under a *_usd name. Minor non-findings noted: the unused _COMP_CATCH_TOPIC constant holds a wrong hash (real competition FishCaught topic is 0x0460e7a9...), StakingState.weekly_revenue is populated from cumulative accRewardPerShare (bogus proxy, but staking data is never rendered), and the treasure sell-value stored in FishCatch.weight_kg is handled correctly by the activity feed which omits weight for treasures.


### bakery-base
The two oldest stacks are structurally solid — owned httpx clients are closed properly, cache writes are atomic (tmp+rename), DexScreener/GeckoTerminal calls are spaced with min-delay throttles, and both screens wrap every widget update in try/except so no verified path crashes the running TUI. The real problems are in what the dashboards display: I ran both stacks against the live APIs and confirmed that the bakery EV table is built from a hardcoded boost catalog that has drifted badly from the live agent.json (costs/success/durations all wrong), the late-join EV shows 'Positive EV $9,749 — consider joining' for a season that is already finalized (winner-take-all math ignoring the confirmed 70/20/10 split and the unused member_count parameter), and the activity feed silently drops whole bakeries because the live API returns null launcher fields the model rejects. Season-over handling mostly works today (the API still returns the finalized season) but an empty season list is an unguarded IndexError. On the Base side, response-shape drift is handled defensively via _safe_float helpers, but failure sentinels (0.0 ETH price, empty token lists) are recorded into the persisted overview time series, and rate-limit 429s are retried like any error without honoring Retry-After. A corrupt cache file with non-numeric points crashes the whole app at launch since both managers load caches in App.__init__ (reproduced). Bankr/Alchemy key plumbing still exists in base_client.py but is dormant in the remote_only path actually used, so the keyless constraint holds in practice.


### ocm-dota
The OCM and DOTA stacks are structurally solid: RPC calls are serialized with a 0.5s inter-call throttle plus 3-attempt exponential backoff on 429/5xx (directly addressing the historical public-RPC rate-limit pain), httpx clients are owned and closed via manager.close(), cache writes are atomic (tmp + os.replace), all function selectors verified correct against keccak256, and both screens wrap every widget update in try/except so a bad payload cannot freeze the TUI. The DOTA stack handles its DigitalOcean API being down or moved gracefully -- game state, leaderboard, and DexScreener fetches are each individually guarded, leaderboard parsing is permissive with per-entry error isolation, and failures degrade to stale/empty data with error_count incremented rather than crashing. The real defects are concentrated in OCM analytics wiring: the Burn Rate signal is fed the wrong time series (mints displayed as burns), RPC-failure zeros are silently treated as real data and persisted into the sparkline history, and a unit-guessing heuristic corrupts sub-1% staking ratios; additionally, both caches' load_from_file crashes on corrupt-but-valid-JSON contents, which (reproduced) aborts the whole app at startup since managers are constructed in App.__init__.


### widgets
The shared widgets and templates are generally well-hardened against the numeric edge cases this scope worried about: sparklines handle <2 points, empty series, and span==0 (both cookie_chart.py and sparkline_template.py), leaderboards handle empty lists with a 'No data' row, dominance handles inf, format_* helpers guard negatives and zero, and the signals dict keys (ev_usd/gap_rate) match what analytics/signals.py actually returns; screen_template.py is byte-identical to screens/bakery.py so there is no template/screen drift, and screen-side try/except wrapping contains most widget failures. The one systemic defect is the complete absence of Rich-markup escaping for remote, player-controlled strings (bakery names, event titles/descriptions): I verified in the project venv (textual 8.1.1) that a name containing a mismatched close tag like '[/x]' crashes Static.update and RichLog.write synchronously (degrading panels silently) and — worst — is deferred by DataTable to its _on_idle formatter, where the MarkupError escapes every try/except and crashes the entire app. EVTable and StatusBar only render trusted static/config strings and are clean.


### security
Security posture is strong for a read-only keyless TUI: no committed secrets (pattern scan over all tracked files clean, .env/data/keystore gitignored), all runtime endpoints public and keyless except a dead Bankr code path (finding 2), no eval/exec/pickle/shell-injection on external data (only json.loads and safe regexes; the sole subprocess call uses fixed osascript args; shell scripts quote arguments properly), cache persistence uses fixed filenames under ~/.maxpane with atomic temp+rename writes and fail-soft corrupt-file handling (no path traversal from API data), wallet addresses are hex-validated before persisting and never logged, and publish.yml uses PyPI trusted publishing triggered only by same-repo tag pushes so forks cannot publish. Residual hardening nits, not defects: GitHub Actions are pinned to mutable tags (checkout@v4, gh-action-pypi-publish@release/v1) rather than SHAs and the publish job has no protected environment; httpx clients set no max response size, so a compromised endpoint streaming a multi-GB body would OOM the process; dependencies are floor-pinned only (textual>=0.80 etc.), so a breaking major release of textual could break fresh installs. The two reported findings are low severity: unbounded token-history growth in the Base cache (the one concrete hostile-API disk/memory growth vector) and the keyless-constraint-violating Bankr/env-key remnants.


### async
Overall the async architecture is disciplined and consistent: each manager owns exactly one httpx.AsyncClient created in its constructor and closed via action_quit (no per-call clients, no cross-event-loop sharing since httpx binds lazily), every screen wraps its whole refresh in try/except so polling loops survive network failures instead of dying silently, timers are correctly stopped in on_screen_suspend and screens are installed once per game so Tab-cycling does not leak managers, timers, or workers. The serious problems cluster in three places: (1) the TTT incremental-scan window is inverted (min instead of max) against a cache with no event dedup, which I reproduced - user-facing fee/launch numbers inflate linearly with uptime and the corruption is persisted; (2) the app-level prefetch workers run raising managers with Textual's default exit_on_error=True, turning a startup network failure into a full app crash; and (3) the universal set_interval + exclusive-worker pattern cancels any refresh slower than poll_interval, which for the RPC-heavy Talismans/TTT cycles on free public endpoints can starve a dashboard into never updating. Secondary issues: the prefetch and the screen's first refresh can run fetch_and_compute concurrently on the same manager (cross-node workers are not mutually exclusive), the four FrenPet managers clobber one shared cache file on quit, and Talismans advances its scan watermark past silently-dropped getLogs chunks, permanently wedging the conservation-invariant signal.


### tests
The tests that exist are high quality, not smoke tests: talismans client tests use exact live-chain ABI hex fixtures (including the dynamic-tuple offset regression from commit 3139636), bakery/base/frenpet client tests use httpx.MockTransport with realistic tRPC/GeckoTerminal/DexScreener payloads, analytics tests probe exact thresholds on both sides, cache tests cover TTL/persistence/corrupt-file paths, and managers (where tested) get contract-key, dedupe-across-rescan, and error-count tests. The whole 796-test suite runs offline in ~11s with no skipped/xfailed tests and no live network. The problem is skew, not quality. Per-dashboard picture: Talismans (this branch) is best-rounded (~124 tests: client/models/manager/cache/signals plus the only widget+screen tests); FrenPet is deepest (~254, though the branch's new fetch_rewards/wallet_rewards path is untested); Base trading ~154 (client+token-detail+3 analytics modules, but the 406-line base_manager and base_cache untested); Bakery ~132 (client/cache/4 analytics, manager untested); Cat Town ~59 (client decode + 3 analytics, but the REST-API-primary competition path is never exercised — the one snapshot test silently validates only the RPC fallback via a broken AsyncMock, the source of the suite's two RuntimeWarnings); DOTA 47 (signal functions only — client/manager/cache dark); TTT 35 (signal functions only — the 1034-line hand-rolled ABI client, 573-line manager, and 534-line cache all dark); OCM zero tests of any kind. Minor non-finding observations: a few tests assert private attributes (manager._error_count, screen._active_view) and base_client tests stub the private _request_with_retry seam — acceptable coupling, and the EXPECTED_KEYS contract-set pattern actually aids refactoring. Net: the newest dashboard sets an excellent template; the three least-recently-touched data layers (OCM, TTT, DOTA) carry essentially all of the untested crash/decode risk.


### rust
The Rust intro binary is in good shape overall: cargo check and all 186 tests pass; terminal state restoration is handled correctly (panic hook installed before raw mode entry, chained to the original hook, restore_terminal runs before result handling, and no unwrap() on terminal operations in the runtime path); config parsing degrades gracefully to defaults on missing/broken files; and the rain, logo, splash, and typewriter renderers all clamp their draw rects to the frame area. The weak spot is the Prompt screen (prompt.rs), which builds Paragraph rects from raw text lengths without any clamping — combined with ratatui 0.29's panicking buffer indexing this yields three confirmed-by-execution crash paths (terminal < 33 cols, terminal < 5 rows during a response, and a user typing ~72+ chars on any terminal). The prompt is also the screen where Ctrl+C gets swallowed as literal input since raw mode suppresses SIGINT and no CONTROL-modifier check exists. One additional confirmed panic lives in theme.rs hex parsing on multi-byte config values. All crashes are at least followed by proper terminal restoration via the panic hook, so no raw/hidden-cursor terminal is left behind — but the intro aborts instead of degrading. Fixes are small and localized (rect clamping, input length cap, an is_ascii() check, a Ctrl+C branch, and a KeyEventKind::Press filter).


### architecture
The architecture is 8 near-identical copy-paste stacks, not a framework: maxpane_dashboard/data/ is ~12,550 lines across 37 files where the per-game cache files are 63-71% line-identical (difflib: cattown vs dota 0.71, cattown vs ocm 0.63, frenpet vs bakery 0.66), _safe_call exists 7 times in 3 drifted variants, load_from_file/save_to_file exist 8 times each, _build_sparkline 6 times, and the JSON-RPC transport 5 times in 3 robustness generations. The propagation model is the core problem and it is documented in the code itself ("Copied from ttt_sparkline.py", "Inspired by ocm_sparklines.py"): each new dashboard is seeded by copying the previous one, so hardening ratchets forward (ttt/talismans have safe cache loaders, RPC fallback rotation, throttling) but is never backported — I proved the killer case by execution: a corrupt-but-valid-JSON cache file for any of the 6 older games raises TypeError out of load_from_file, through the unguarded manager __init__, and aborts MaxPaneApp construction entirely, while the identical ttt/talismans code degrades gracefully. The templates/ package that was supposed to prevent exactly this has zero imports anywhere (package, tests, scripts) — it is dead code shipped to PyPI. CLAUDE.md compounds the problem by describing a nonexistent backend/frontend transaction-bot repo with failing commands and key-handling instructions that contradict the keyless/read-only constraints. Maintainability verdict: adding dashboard 9 is cheap (copy talismans), but any cross-cutting fix now requires 6-8 coordinated edits and history shows those edits don't happen; extracting the cache persistence, _rpc transport, _safe_call, and sparkline helpers into shared modules would remove roughly a third of the data layer and convert the divergent-copy bug class into single-point fixes.
