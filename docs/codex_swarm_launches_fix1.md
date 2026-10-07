# Codex fix round 1: SWARM production launches (final review of a5f2fe9, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, the original `docs/codex_swarm_launches_plan.md` (c9352030) and
> `CLAUDE.md` are the whole process.

**Branch:** `feature/swarm-launches`; continue from `a5f2fe9`.
**Where the findings come from:** three independent read-only reviews from Claude Code (spec compliance, data layer,
UI and safety), run against `a5f2fe9`, the v8 fixtures, and **live data from 2026-10-06 about 05:45 UTC**:
- 18 production launches, #734 to #773, the first two on Robinhood (#771, #773);
- a new kind, `evm_project` (#761);
- a parked launch (#770).

**What is fine:** spec compliance passes in substance. All B3-named mutants are killed. Markup injection and link
safety hold on Textual 8.1.1 and 8.2.8. There is no false `✗` on any live launch.

**Process confirmations (owner, 2026-10-06):** per-WP reviews were waived by the owner, and the SWARM tight title
form was approved at the live look. **This round:** one commit per item group (F1–F3, F4–F10, F11–F16), each with
its tests and named mutants. Then report for the controller's verification. Never merge, push or tag.

The tests rules are unchanged from the plan's B1. **Record every mutant you run** (name, file:line, killing test) in
the commit body; WP2's and WP3's mutants are not recorded anywhere.

---

## Blockers

**F1 · Site matching blocks the UI loop.**
- **Where:**
  - `analytics/surf_launch_sites.py:16-41` (`match_sites`);
  - called from `data/surf_manager.py:5632` (`_swarm_launch_keys`), which runs at `:6821` and again via
    `_swarm_launch_events` (`:5671`) on every `fetch_and_compute`;
  - `app.py:201` awaits that call on the Textual loop every 30 s.
- **What happens:**
  - for every (site, production launch) pair, the matcher rebuilds `mappings(workflows)` and scans the whole
    workflow history with `any(...)`;
  - measured on the real cache with 100 real sites: **3.97 s per refresh at 150 launches, 19.45 s at the 500 cap**;
  - cProfile puts 15.8 of 16.1 s in `match_sites`.
- **Fix:**
  - Build `{frontendJobId: {contractsJobId,…}}` once per call. Index production launches by each `job_id` and by
    token address, so matching is O(sites + launches).
  - Compute the links **once in the launch-tier task**, store them with the slot, and have the refresh path only read
    them. Recompute only when the slot or the scores slot's workflows change (memoise on their timestamps).
  - `_swarm_launch_events` reuses the rows `_swarm_launch_keys` built, instead of rebuilding them.
- **Test:** a timing guard. `match_sites` at 500 launches × 100 sites × 1,000 workflows takes under 50 ms, and one
  `fetch_and_compute` calls it at most once.

**F2 · SWARM LAUNCH misses a launch that goes live out of number order.**
- **Where:** `analytics/surf_signals.py:1409`, `if seeded and (row["number"] > high or key in pending)`.
- **What happens:**
  - `createdAt` does not follow `launchNumber`, and admitted→live often takes less than one 60 s read;
  - live, #741 came after #745 (53 s to live), #747 after #751 (31 s), and #763 after #767 (173 s);
  - such a launch is never seen `admitted` and its number is ≤ the high-water mark, so it is recorded as seen
    **without firing**;
  - reproduced: seed #751, then a read with #751 and #747 live gives `ok`, fired `[]`.
- **Fix:**
  - Drop the launchNumber high-water gate.
  - Fire when `key not in seen and (number > evicted_floor or key in pending)`, where `swarm_launch_evicted_floor`
    is the highest `launchNumber` ever **evicted** from `swarm_live_seen`. Persist it and sanitise it in
    `surf_cache._sanitise_baselines` (a non-negative int; anything else is a failed read).
  - Remove `swarm_launch_high_water`, or keep it only for display.
- **Tests:**
  - out of order: seed #751, then #747 first seen live fires;
  - the existing 600-launch eviction no-refire test still passes;
  - two out-of-order launches in one read both fire.
- **Mutant:** restore the `> high` gate → the out-of-order test reddens.

**F3 · A corrupt `swarm_live_seen` silently reseeds** (it should be a failed read).
- `_sanitise_baselines` drops an invalid list, so the detector sees the key absent and reseeds silently, swallowing
  every launch in the window.
- **Fix:** keep a sentinel (`None`) so `_swarm_launch_state`'s `corrupt` branch returns DEAD until a valid read
  re-establishes the state. This belongs with F2, since both touch the same state.

## Should-fix: data

**F4 · K3 stays `unknown` forever when an attested contract has no artifact, re-running RPC and a 1.5 s scan every
cycle (live #763).**
- **Where:** `analytics/surf_launch_checks.py:132-148` (name matches no artifact → `unknown`), `:96-101`, and
  `surf_manager.py:5566`, `:5588`.
- **The case:** #763 attests `Strike`, `UnionCard` and `V2TwapSwap`, and `V2TwapSwap` has no artifact. It stays at
  `… 3/4`, re-batches its RPC reads every cycle, and re-scans `Strike` by route (b) every cycle.
  - `Strike`'s creation code starts `61 02a0 80 60 40 52`, so the preamble filter misses.
  - That scan takes 24 hashes of 25 KB, 1.55 s each time.
  - A real mismatch on its 38 KB input would block for **59 s plus 42 s**.
- **Fix:**
  - An attested contract with **no artifact of that name** is `na` for the verdict. Record it in the evidence
    (`"not deployed by this launch"`); it never keeps the launch pending.
  - **Persist K3 per contract.** Never re-run (a) or (b) for a contract that already passed. Re-run only
    `unknown` ones.
  - **Narrow route (b)'s candidates:** an offset `i` is a candidate only if `(i − 4) % 32 == 0` **and** the ABI word
    just before it, `L = int(input[i−32:i])`, satisfies `creationCodeBytes ≤ L ≤ len(input) − i`. That leaves 4–7
    candidates (#763 Strike: 164, 196, 228, 644, 740; UnionCard adds 26980; #747: 164, 196, 228, 740), and the
    real match is always among them.
  - Run `check_launch` via `asyncio.to_thread` so the loop stays responsive. It is pure CPU, and a GIL switch every
    5 ms keeps the UI ticking.
- **Tests:** a #763-shaped launch reaches `✓ swarm` with `V2TwapSwap` as `na`; a passed contract is never rescanned
  (count the keccak calls); the candidate list for the #747 fixture is `[164, 196, 228, 740]`.

**F5 · `/launch/policies` (25 KB) is re-read every cycle in two cases.**
- **Where:** `surf_manager.py:5590`, `checks['K2']['state'] == 'fail' or not known`. It fires every cycle:
  - while a launch with a persisted K2 `fail` stays pending;
  - for any launch whose `policy_version` is missing from `/launch/policies` (or null).
- **Fix:**
  - Record `policies_refreshed_for = {launch_id: policy_version}` in the slot.
  - Force a refresh only when K2 is **newly** judged `fail` this cycle (the previous state was `unknown`), or when
    the version is unknown and not yet recorded.
  - Otherwise keep the 1,800 s cadence.
- **Test:** three cycles with an unknown version give `calls.count('policies') == 1`, and the same holds with a
  persisted K2 fail.

**F6 · K2 never convicts a foreign sender when the deploy tx has `to: null`** (a direct contract creation).
- **Where:** `surf_launch_checks.py:124`, `(not factories or to)`.
- **Fix:** when the tx is present, judge `from` on its own. On a chain that has factories, a present tx with
  `to: null` is a `to` outside the set, so `fail`.
- **Tests:**
  - `from` foreign and `to` null on chain 1 → `✗ K2`;
  - `from` correct and `to` null on a chain without factories → pass.

**F7 · The FIRED entry freezes the ticker and verdict from the first sighting.**
- **Where:** `surf_signals.py:1410`. If the detail read was `503 busy` (seen live on #767), or the RPC lagged, the
  signal shows `$-- #767 … 1/4` for 24 h and the title shows it for 60 min.
- **Fix:** while the launch is still in the reading, refresh `ticker`, `token_address` and `verdict_*` from the
  current event, keeping `ts`.
- **Test:** fire with `partial 1/4`, then the next read with `swarm` shows `✓`.

**F8 · Detail-read starvation.**
- **Where:** `surf_manager.py:5544` spends the 3-read budget on the highest unread numbers. If those fail every
  cycle, the rest are never read. Reproduced: details for #754 and #751 always None, so #737 and #741 stayed without
  facts after 4 cycles.
- **Fix:** record `detail_failed_ts` on a failed or invalid read. Order candidates: never tried, then oldest failure,
  each group by number desc.

**F9 · One route's failure backs off the whole tier** (`surf_manager.py:5531`, `:5599`, `:5622`). A `/sites` or
policies failure applies the 120 s backoff to `/launches` too, which feeds the detector. A2.1 says failures are per
route.
- **Fix:** only a `/launches` failure marks the tier failed. Other routes keep last-good and log.

**F10 · An unguarded site-job shape stops the tier.**
- **Where:** `surf_manager.py:5616` → `site_job_facts`. A job whose `project` is a non-dict raises `AttributeError`
  outside any try, so the tier fails before either slot is stored, and the same job is re-read and fails every cycle.
- **Fix:** guard it like `extract_facts`, and record the job as read (facts `None`).

## Should-fix: widgets

**F11 · LAUNCHES drops every row that is neither production nor Sepolia.**
- **Where:** `widgets/surf/swarm_launches.py:147`, `… and r.get("chain_id") == 11155111`. A null-chain row, an
  unknown chain or an abandoned chain-1 row vanishes. A list made only of such rows paints `No data`, although A0
  says they render as today.
- **Fix:** the second group is **every** non-production row (capped at 12, by number), rendered dim with no `◆` and
  verdict `--`.

**F12 · An admitted token launch shows ticker `--` although the ticker is known** (`swarm_launches.py:200` keys on
a deployed `token` artifact).
- The deploying window is exactly when SWARM LAUNCH says `deploying $ZTO #737`, so the table must agree.
- **Fix:** for a production row with `kind != "evm_contracts"`: `$<ticker>`, else `#<n>`. For `evm_contracts` and
  non-production rows: `--`.

**F13 · Parked production launch verdict** (*controller decision; the owner may veto*).
- #770 is `parked` with the admission check `protected_invariants` failed. It renders `-- pending`, because
  `not_deployed` outranks `failed`, and "pending" is false for a parked launch.
- **Fix:** `not_deployed` applies only while the status is `admitted`. A `parked` launch with a failed admission
  check is `failed` → `✗ K4`; a `parked` launch with no failed check is `-- parked` (dim).
- **Test:** the #770 shape.

**F14 · Signals row hygiene** (SWARM LAUNCH feeds attacker-chosen text into an older path).
- **Unclosed `[` leaks a backslash.** `signals.py:322`: a ticker with an unclosed `[` before a tag paints a stray
  `\`, and the extra cell can cut `#737` to `#73…`. Render the swarm row as
  `Content.from_markup(head) + Content.from_rich_text(Text(" · " + shown, style="dim"))` even when it has no
  address.
- **Wide characters.** `signals.py:348-356` and `_cut_detail` measure `len`; measure with `cell_len`, so a ticker of
  wide characters cannot push the verdict and address off.
- **Test:** ticker `'字'*60` and `Q[31mEVIL[/]R` at the 143 pin: the row fits and `#737` survives.

**F15 · SITES cell.** `swarm_sites.py:228-229`:
- **Label floor:** give the label a floor of 4 cells, and clip the ticker suffix with `rowfit.clip` (which supplies
  `…`); a 40-character ticker currently erases the label.
- **Untrusted links:** keep the label's status colour and dim **only** the ` · $T` suffix.

**F16 · Small things.**
- **LAUNCHES site cell** (`swarm_launches.py:210-211`): `site_text(item.get("site_ens_name") or
  item.get("site_label"), 16, label=item.get("site_label"), …)` whenever either is set, so a null-label site with a
  valid ENS name still shows and links, as the popup already does.
- **Popup** (`screens/swarm_detail.py`):
  - a production launch with no site reads `SITE  none`;
  - Sepolia rows show K1–K7 as `--`, never `unknown`;
  - bold and width-clip `_title` like the other detail screens.
- **Width constants:** `_TICKER_COLS = 11`, `_SITE_COLS = 16` and `_VERDICT_COLS = 10` become constants, each with a
  one-line reason (A3.2).
- **Stale text:**
  - `themes/minimal.tcss` comments above `SurfSwarmLaunches` / `SurfSwarmWorkflows` (`:2605`);
  - `_swarm_table.py:37` ("4 cells");
  - `signals.py` docstrings ("ten rows", "nine rows");
  - `.claude/rules/surf.md:~61` (the scores sweep no longer feeds LAUNCHES / SITES);
  - surf.md "Conflicts remain untrusted" (a conflict gives no link);
  - the name and docstring of `tests/test_explorer_action.py::test_a_click_on_a_site_name_opens_its_eth_limo_page`.

## Test gaps: 8 surviving mutants from the controller's run (add one assertion each)

- (a) K2 `all → any` over several txHashes: a two-artifact row with one bad `from` → `fail`.
- (b) K2 ignoring receipt status: `receipt.status = "0x0"` → `fail`.
- (c, d) the zero address kept in the factory or wallet set: a policy with `owner` or `factory` = `0x0` does not let
  a `0x0` `to` or `from` pass.
- (e) `not_deployed` precedence (after F13): a production `admitted` row with `artifacts: []` → `-- pending`, even
  with K4 failing.
- (f) the site `createdAt` gate at manager level: a site created before the earliest production `createdAt` never
  produces a `('site_job', …)` call. This is B3 #6's adam case.
- (g) conflict, newest wins: two linked sites for one launch → the newer `createdAt`.
- (h) the `/sites` 300 s cadence: two cycles 61 s apart → `calls.count('sites') == 1`.
- Also **B3 #8 at the pin:** at the 143-column default body, the swarm signal sheds its address while `#737`
  survives.
