# Live captures — the states that cannot be recaptured

Everything in the parent directory is from **grace hour 1** (2026-08-16, 21:04–21:14 UTC, plus
the 21:56–22:01 hour-boundary series). The rest of the game — the flat post-grace multiplier,
a judged hour with a live deficit, and the settlement transition itself — happens once and is
then gone. The chain keeps the *history*, but the **view returns at an instant** are not
recoverable after the fact: `isSettled()` flips with no transaction and no log, and
`currentHourTotal()` zeroes with nothing written anywhere.

This directory holds bundles written by `scripts/capture_curator_state.py`. Run it at every
opportunity; a redundant bundle costs a few kilobytes and a missed one costs a fixture that
cannot be recreated.

```bash
python3 scripts/capture_curator_state.py --self-test        # prove the UA is accepted
python3 scripts/capture_curator_state.py --dry-run          # fetch, print, write nothing
python3 scripts/capture_curator_state.py --label post-grace
python3 scripts/capture_curator_state.py --label hour-boundary --no-logs   # fast repeat poll
python3 scripts/capture_curator_state.py --label curve-probe --curve-probe
```

Keyless, read-only, stdlib-only: a bare `python3` from any checkout, no venv, no repo import,
no API key, no signing, ever. Proven by copying the single file into an empty directory and
running it there with macOS's system `/usr/bin/python3` (3.9.6) — it answered 21/21 views and
reported `selector_source: inlined`, its fallback table, because the fixtures were not there.

One thing that is worth knowing before a timed run: on a host with no working IPv6 route, plain
`urllib` waits out the connect timeout on **each** AAAA record these Cloudflare-fronted
endpoints publish. Measured here: 40.08 s for a single `eth_blockNumber`, 3 m 41 s for a whole
bundle, against 0.13 s and 1.3 s once the resolver's answer is reordered IPv4-first. The script
does that reordering itself (`PREFER_IPV4`); if a capture ever feels inexplicably slow, that is
the first thing to check, and `--self-test` will show it.

## What a bundle is

One JSON object per file, self-describing, named for the UTC instant it was taken
(`<YYYYMMDD>T<HHMMSS>Z_<label>.json`; a second run in the same second gets a `-2` counter — a
bundle is never overwritten). Raw payloads go in verbatim: hex strings exactly as the provider
returned them, never reformatted into decimals, so a decoder test can consume the same bytes
the client will see.

| field | what |
|---|---|
| `label`, `captured_at`, `captured_at_utc` | which state this was meant to be, and when it actually was |
| `chain_head` | `eth_blockNumber` at capture, as an int |
| `state` | the 21 parameterless views, keyed by selector: `{"name": "isSettled()", "result": "0x…"}` |
| `balance` | `eth_getBalance(contract)` — nonzero is **always** forced ETH, never deposits (H5) |
| `logs` | one `eth_getLogs` sweep from `logs_from_block`, raw log objects |
| `logs_endpoint` | which of the two logs hosts actually answered |
| `block_timestamps` | `blockNumber → timestamp` for the distinct blocks of the newest 40 logs (H14: Tenderly's logs carry no `blockTimestamp` and Blockscout's carry none either) |
| `blockscout_page_0` | the REST log page, an independent cross-check of the RPC sweep |
| `curve_probe` | present only with `--curve-probe`: `previewPoints(uint256)` over 12 weights, `pointsOf`/`weightOf` over 4 real wallets |
| `errors` | every failure, with stage, URL and message. **A partial bundle is still committed** — three sections beat no bundle at the only instant it could have been taken |

`errors: []` is a **claim**, and as of 2026-08-17 it is a true one. A batch answered HTTP 200
with items missing or renumbered used to write `result: null` for every unanswered view and
append nothing, so an archived bundle asserted a clean capture that never happened and its
manifest row read `err = 0` with every decoded column `?`. A 403 was loud; a short batch was
not. Each unanswered id is now an error of its own (`no response for id 7 in the batch`), as is
a `result`-less item, a block header with no timestamp, and an `eth_getLogs` that answers 200
with something other than an array — that last one used to become `logs: []` with the host
named as though it had answered, instead of failing over to the other pool. Read the `err`
column of `MANIFEST.md` before trusting a row's blanks: `?` with `err = 0` means the view
honestly had nothing to say, `?` with `err > 0` means the capture is partial and the bundle
names why.

`selector_source` says whether the 21 selectors came from the committed `batch.json` (the list
that actually answered 21/21 on publicnode) or from the script's inlined fallback copy.

`MANIFEST.md` is the machine-written index: one row per bundle, appended never rewritten,
decoded at write time. The bundle is the authority; the row is the search index.

## One bundle, one instant — why that matters here

The research captures in the parent directory were taken over a ten-minute window while the
game was taking a deposit every few seconds, so **they do not agree with each other, and they
are not supposed to**: `results.json` (21:04) reads `totalContributors() == 143` and
`totalTxCount() == 222`, while `tenderly_logs.json` (21:13) holds **145** `FirstDeposit` and
**231** `Deposited` rows. Both are correct; nine minutes passed.

A test that folds the log sweep and asserts the fold against a *state* read from the other file
is therefore off by two before it starts — worth knowing for H6, whose rule is
"`FirstDeposit.index` maxes at exactly `totalContributors`". Cross-instant assertions belong on
a bundle, where every section was fetched in the same second: in
`20260816T225006Z_grace-late.json` the sweep and the views reconcile exactly, 1282 == 1282 and
794 == 794.

## Labels

| label | the state it is hunting |
|---|---|
| `grace-late` | the decayed end of the early-bird ramp: `10000 < earlyMultiplierBps() < 19491`, `currentHour() > 1`, still in grace |
| `hour-boundary` | `currentHourTotal() == 0` **while** `lastActiveHour()` still names the previous hour — the pair a naive state-poll sparkline renders as a 99.5% crash (H2). Crossings are at `HH:58:47` UTC; retryable hourly, easiest during a quiet hour |
| `post-grace` | `earlyMultiplierBps() == 10000` exactly and `currentHour() >= 24` — grace over, hours are judged |
| `judged-deficit` | a judged hour with `ethNeededThisHour() > 0`; under 900 s left is the red HOUR AT RISK state, over 900 s the yellow one |
| `settlement` | the transition: the last bundle with `isSettled() == false` and the first with `true`. Derived, so it flips with **no transaction and no log** unless someone calls the permissionless `settle()` |
| `curve-probe` | the sqrt curve's onchain witness: `previewPoints`/`pointsOf`/`weightOf`, none of which are in the parameterless round |

## Ledger

Maintained by hand (WP1.7 closes it out). Facts, including negative ones: a bundle showing
`isSettled()` still false at a named instant is evidence, not a failed run.

| bundle | UTC | label | what it records |
|---|---|---|---|
| `20260817T000322Z_grace-late.json` | 2026-08-17 00:03:22Z | `grace-late` | **The bundle that proves the hour series must come from logs.** One sweep, **5222** logs (2930 `Deposited`, 2291 `FirstDeposit`, one `Launched`) — again reconciling exactly with the views taken in the same second, 2930 == `totalTxCount()` and 2291 == `totalContributors()`. Folding `Deposited.amount` by the event's **indexed hour topic** — no timestamps involved — gives hour 0: 851.89, hour 1: 9987.26, hour 2: 2263.83, hour 3: 2738.92, hour 4 (in progress): 139.25 ETH. The first four are **wei-exact** against three independent state reads taken seconds before each of those hours closed: 9987263970125228654763 (`../hour_boundary_h1_h2.json`, 21:58:35), 2263828567276737794408 (`…T225848Z`), 2738915143506654416570 (`…T235846Z`). That is H2's whole argument as evidence: the fold reproduces `currentHourTotal()` exactly for every *completed* hour, and unlike the state poll it does not collapse to a fresh bucket at the boundary. Scale at capture: 2291 contributors and 15981.15 ETH routed, from 794 and 12547.77 an hour earlier |
| `20260816T235846Z_hour-boundary.json`, `20260816T235850Z_hour-boundary.json` | 2026-08-16 23:58:46Z / 23:58:50Z | `hour-boundary` | The hour 3 → 4 crossing — **busy for the third time**, and the pair kept out of a 32-bundle sweep. Before: hour 3, 2738.9151 ETH, `timeLeftInHour` 12. After, four seconds later: hour 4, `currentHourTotal` **7.0662** ETH with `lastActiveHour` already 4. Two deposits landed inside the first three seconds (`totalTxCount` 2718 → 2720). The fresh-hour reading is the closest to zero yet across the three crossings — 51.48, then 83.41, then 7.07 ETH — which is what "nearly caught it" looks like. The other 30 bundles of that sweep were identical restatements of these two states and were discarded; their manifest rows stay, with a note |
| `20260816T2258*_hour-boundary.json` … `20260816T2300*` (29 bundles) | 2026-08-16 22:58:23Z → 23:00:22Z | `hour-boundary` | **The hour 2 → 3 crossing at 4-second resolution — and the quiet state was again NOT observed.** The pair that straddles it is `…T225848Z` (hour 2, `currentHourTotal` 2263.8286 ETH, `timeLeftInHour` 12) and `…T225852Z` (hour **3**, `currentHourTotal` **83.4064** ETH, `lastActiveHour` **already 3**, `timeLeftInHour` 3600). Eleven deposits landed inside the first five seconds of the new hour — `totalTxCount` 1341 → 1352, contributors 816 → 826 — so `lastActiveHour()` had rolled before the first poll after the boundary, exactly as it did at 21:58:47. Two facts the series pins anyway: `timeLeftInHour()` reads **3600 at the top of an hour, never 0** (H12), and it steps in 12-second jumps because `eth_call` runs against the latest *block*, so state trails wall clock by up to one block — a boundary poll must keep going for ~30 s past `HH:58:47`. See "Hunting the quiet crossing" below |
| `20260816T225143Z_curve-probe.json` | 2026-08-16 22:51:43Z | `curve-probe` | **The sqrt curve now has an onchain witness.** `previewPoints(uint256)` for twelve weights and `pointsOf`/`weightOf` for four real wallets, all 20 calls answered. Every return equals `(isqrt(weight) * 1000) // 10**9` computed locally: `0`, `1`, `1e9-1` and `1e9` all floor to **0 points** (the floor is real, not a rounding artefact), `1e18 → 1000`, `4e18 → 2000`, `100e18 → 10000`, `1000e18 → 31622`, `2000e18 → 44721`, and the three non-squares land on 1732 / 2645 / 21473. The wallet half cross-checks the *fold* as well: `weightOf` returns 902.10737 / 333.596 / 125.0828 / 117.96 ETH, exactly the `Deposited.newWeight` totals folded out of `../tenderly_logs.json`, and `pointsOf` #1 is 30035, the number the mechanics doc estimated. State-only bundle (`--no-logs --no-blockscout`) — the history is already archived in the `grace-late` bundle one minute earlier |
| `20260816T225006Z_grace-late.json` | 2026-08-16 22:50:06Z | `grace-late` | The rig proven end to end, and a genuinely new state: hour **2**, `earlyMultiplierBps()` decayed to **18812** (0x497c) from the 19491 of the 21:04 round, `isSettled()` false, `ethNeededThisHour()` 0 (grace). Scale has moved a long way past the research capture — **794** contributors, 1282 deposits, **12547.77 ETH** routed, **2077** logs in one sweep against the 377 of `../tenderly_logs.json`. Balance 0, so nothing has been force-fed. 21/21 views, no errors, `block_timestamps` for the newest 40 logs (15 distinct blocks) — the first capture that has them at all. **The sweep reconciles exactly against state**: 1282 `Deposited` logs == `totalTxCount()` 1282, 794 `FirstDeposit` logs == `totalContributors()` 794, one `Launched`, and no `HourSaved` / `Settled` / `Rescued` has ever fired. Blocks 25769870 → 25770726, ending on the head the same bundle recorded, so there is no gap to repair |

### Hunting the quiet crossing

The state capture **A** still needs — `currentHourTotal() == 0` while `lastActiveHour()` still
names the previous hour — has now been missed twice, at 21:58:47 and at 22:58:47, for the same
reason both times: during grace the game takes a deposit within seconds of every boundary, so
the new hour's bucket is already nonzero before the first poll lands. Nothing is wrong with the
rig; the state simply does not exist during a busy hour.

It is retryable at **every** `HH:58:47` UTC until settlement, and it gets easier as the game
quietens — after grace ends the whole point of the game is hours that nearly go empty, so an
hour whose first minutes are silent is the *normal* post-grace case rather than a rarity.

```bash
# Sweep one crossing: 25 s before to ~100 s after, every 4 s, state only.
python3 scripts/capture_curator_state.py --label hour-boundary \
        --no-logs --no-blockscout --start-at HH:58:22 --every 4 --repeat 30
```

Keep polling for at least 30 s past the boundary: `eth_call` runs against the latest *block*,
so `currentHour()` flips up to a block late and `timeLeftInHour()` steps in 12-second jumps.

### `--start-at`, and what happens when you are late

Three forms, all UTC: `HH:MM:SS`, `@<epoch>`, and `boundary` (the next `launchTime + N*3600`,
i.e. the next `HH:58:47` — derived from `launchTime`, not from the wall clock).

**Being late never costs a window.** An `HH:MM:SS` that has already gone by up to six hours
means *start now*: the script prints `start instant 20:57:00Z passed 30 s ago — capturing now`
and fires immediately, then spaces the remaining `--repeat` captures by `--every` from that
real start. Only a time more than six hours behind is read as tomorrow's, and a time that went
by as midnight passed is read as yesterday's rather than as a wait of nearly a day.

That is a fix, not a description of how it always behaved: until 2026-08-17 a start instant
one second in the past resolved to *the same time tomorrow*, printed one line of stderr and
blocked for ~86 400 s. Firing the settlement command a few seconds late would have lost
capture C forever — the transition is one-shot, and it flips with no transaction and no log.
Pinned by `test_a_start_instant_that_has_just_gone_means_now_not_tomorrow` and
`test_a_sweep_fired_late_captures_now_and_still_takes_every_capture`.

If you are already inside the window and want no arithmetic at all, drop `--start-at`
altogether: the sweep starts at once and `--every`/`--repeat` still hold the grid.

### The two windows on 2026-08-17 — a runbook

Both are on the clock and neither can be retried in the form it happens. Read this, run the
self-test first, and do not improvise at 20:58.

**19:50 UTC — arm.** `python3 scripts/capture_curator_state.py --self-test` must print
`OK <block>`. If it prints a 403 the User-Agent is the suspect (publicnode rejects
python-urllib's default); nothing else about the run matters until this passes.

**19:58:47 UTC — grace ends (capture B).**

```bash
python3 scripts/capture_curator_state.py --label post-grace --start-at 19:58:52
```

Check by hand that `earlyMultiplierBps()` decodes to exactly `0x2710` (10000). If it is still
above, either the clock is off or `launchTime` is not 1786910327 — stop and report rather than
relabelling the bundle. Then hunt the deficit, which is the perishable half:

```bash
python3 scripts/capture_curator_state.py --label judged-deficit \
        --no-logs --no-blockscout --start-at 20:00:00 --every 300 --repeat 12
```

Keep the bundle with the smallest `timeLeftInHour()` that still has `ethNeededThisHour() > 0`;
under 900 seconds is the red HOUR AT RISK fixture. If the hour simply fills, keep a bundle with
`ethNeededThisHour() == 0` and `currentHour() >= 24` — "judged and safe" is also a state that
has never been captured — and write in the ledger that no deficit was observed in that hour.

**20:58:47 UTC — earliest possible settlement (capture C).** The transition is one-shot and
unrepeatable; `isSettled()` is *derived*, so it flips with **no transaction and no log** unless
somebody calls the permissionless `settle()`.

```bash
python3 scripts/capture_curator_state.py --label settlement \
        --no-logs --no-blockscout --start-at 20:57:00 --every 60 --repeat 8
```

State-only on purpose: a full sweep is ~2 MB and settlement writes **nothing** to the log —
the view is the whole event. The history sweep comes once, at the end.

Keep both halves: the **last** bundle reading `isSettled() == 0x0` and the **first** reading
`0x1`. The manager's latch test needs "not settled", then "settled", then an outage — one half
alone does not exercise it. Then keep polling every ~30 minutes for a few hours in case someone
calls `settle()`, so the `Settled` log lands in a bundle's `logs` array.

If 20:58:47 passes and `isSettled()` is still false, the first judged hour survived. That is not
a failed run — it is the game. Record it in the ledger and repeat at each following `HH:58:47`.

**Once it is settled**, take one full-history sweep: it never changes again and it is the most
valuable single artefact here.

```bash
python3 scripts/capture_curator_state.py --label settlement --logs-from 25769870
```

Budget for its size before you run it. The sweep was 377 logs at 21:13 (research), 2077 at
22:50, and **5222** at 00:03 — a 4.7 MB bundle five hours after launch, and the game was still
accelerating. A settlement-day archive could be tens of megabytes; take it anyway (it is the
one artefact that cannot be retaken), but expect to discuss whether it lands in git raw,
gzipped, or trimmed to the event types the tests fold.

### Re-pointing the synthetic fixtures

`rg "SYNTHETIC — re-point" tests/` is the whole checklist. It returned nothing on
2026-08-16 23:05 UTC only because the suites that place the markers had not been written yet;
~~as of that timestamp there is nothing to re-point~~ — **as of 2026-08-17 it returns 33
matches**, and the inventory below (WP7.13) says what each one is waiting for. Each marker
names the bundle it needs, and the convention is exact so the grep stays the whole checklist:
do not reword it, and do not delete one to tidy the output.

Two rules for whoever closes it out:

- **Run the test before changing any expected value.** If it passes unchanged against the real
  bundle, the synthetic was faithful and the evidence just got upgraded for free. If it fails,
  read *why* first — a synthetic that disagrees with the chain is a finding, and it belongs in
  this ledger.
- **Do not delete a marker to tidy the grep.** Some of them are permanently synthetic (below);
  those stay, with the reason written down.

### Still synthetic

Fixtures the build tests against that have no real payload yet, and why:

| fixture | status |
|---|---|
| hour-boundary with a **stale** `lastActiveHour` | waiting on a quiet crossing (the busy one is already captured in `../hour_boundary_h1_h2.json`). Missed three times — 21:58:47, 22:58:47, 23:58:47 — all busy |
| post-grace flat multiplier | window opens 2026-08-17 19:58:47 UTC — **still ahead** |
| judged hour with a deficit | needs a judged hour that is short with time left on it; earliest 2026-08-17 20:58:47 UTC |
| settled state + the `Settled` log | earliest 2026-08-17 20:58:47 UTC; one-shot, unrepeatable — **still ahead** |
| `HourSaved` log row | **PERMANENT-SYNTHETIC unless it fires.** It needs a judged hour to cross the threshold from below; if the game dies at hour 24 the event never exists. Do not block on it |
| `Rescued` log row | **PERMANENT-SYNTHETIC.** Needs someone to force-feed ETH *and* the deployer to sweep it; realistically never |
| `creditedDelta == 0` deposit | **PERMANENT-SYNTHETIC in practice.** Needs a single send above the 1000 ETH cap; the largest real one is 461.1 ETH. Do not wait for it |
| judged hours generally (streak, closest call) | **structurally synthetic until 20:58:47 UTC** — no hour on this contract has ever been judged, so every `HourBucket(judged=True)` in the suite is hand-built |

### The marker inventory — WP7.13, 2026-08-17

That grep returns **33** matches. Nothing was re-pointed, because
**no bundle for capture A, B or C exists**: the newest bundle here is `20260817T000322Z`, both
of the 2026-08-17 windows (19:58:47 and 20:58:47 UTC) were still ahead when this was written,
and the quiet crossing has been missed at three consecutive boundaries. Every marker therefore
stays exactly as its owning work package wrote it — the convention is what makes the grep the
whole checklist, and a marker deleted to tidy the output is a fixture that silently stops being
tracked.

What each one is waiting for, so the next agent does not have to re-derive it:

| waiting on | markers | where |
|---|---:|---|
| **A** — quiet crossing (`currentHourTotal == 0` with a stale `lastActiveHour`) | 3 | `data/test_curator_cache.py:425` `test_the_boundary_fixture_writes_no_zero`; `data/test_curator_manager.py:375` `test_a_quiet_crossing_cannot_overwrite_a_folded_bucket`; `data/test_curator_manager.py:1220` `test_a_silent_hour_reaches_the_series_as_a_zero_rather_than_a_hole` |
| **B** — post-grace / judged hour with a deficit | 15 | `analytics/test_curator_signals.py:668, 1236, 1434, 1448, 2062, 2121, 2142`; `widgets/test_curator_widgets.py:278, 458, 814, 1497, 1907`; `screens/test_curator_screen.py:194, 215`; `fixtures/curator/signals/readings_judged_deficit.json` |
| **C** — settlement transition + the `Settled` log | 6 | `analytics/test_curator_signals.py:1483`; `widgets/test_curator_widgets.py:303`; `screens/test_curator_screen.py:196, 222`; `data/test_curator_manager.py:926`; `fixtures/curator/signals/readings_settled.json` |
| **permanent-synthetic** — the event may never fire, or the deposit may never land | 3 | `data/test_curator_manager.py:614` `test_the_settled_and_hour_saved_decoders_read_their_synthetic_rows` (`HourSaved`); `data/test_curator_client.py:1299` `test_the_endgame_rows_group_correctly_when_they_finally_fire` + `fixtures/curator/client/logs_settled_row.json` (`HourSaved`/`Settled`/`Rescued` shapes, taken from the ABI); `widgets/test_curator_widgets.py:1352` `test_a_zero_credit_is_a_real_reading_and_not_an_unknown_one` (a deposit above the 1000 ETH cap) |
| **prose** — the convention documented, not a fixture | 6 | this file; `fixtures/curator/screen/README.md:74-75`; `fixtures/curator/signals/README.md:17,19`; `analytics/test_curator_signals.py:2142`'s own assertion that the marker is present in the fixture |

The permanent-synthetic four already carry their reason where they live — `logs_settled_row.json`'s
`_comment` states plainly that `HourSaved`, `Settled` and `Rescued` have never fired and that the
rows carry the ABI's *shape* only, and the widget test's follow-up comment names the 461.1 ETH
largest real deposit. They keep their markers on purpose: the marker is what proves the fixture is
still being watched, and `HourSaved` would be re-pointable the day one finally fires.

**One gap closed since the plan was written:** `previewPoints`/`pointsOf` were captured
(`20260816T225143Z_curve-probe.json`, 20 of 20 calls matching `(isqrt(w) * rate) // 1e9`), so the
sqrt curve is validated **against chain**, not by transcription. No marker was waiting on it, which
is why the count did not fall.
