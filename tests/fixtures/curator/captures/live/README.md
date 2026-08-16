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
no API key, no signing, ever.

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

`selector_source` says whether the 21 selectors came from the committed `batch.json` (the list
that actually answered 21/21 on publicnode) or from the script's inlined fallback copy.

`MANIFEST.md` is the machine-written index: one row per bundle, appended never rewritten,
decoded at write time. The bundle is the authority; the row is the search index.

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
| `20260816T2258*_hour-boundary.json` … `20260816T2300*` (29 bundles) | 2026-08-16 22:58:23Z → 23:00:22Z | `hour-boundary` | **The hour 2 → 3 crossing at 4-second resolution — and the quiet state was again NOT observed.** The pair that straddles it is `…T225848Z` (hour 2, `currentHourTotal` 2263.8286 ETH, `timeLeftInHour` 12) and `…T225852Z` (hour **3**, `currentHourTotal` **83.4064** ETH, `lastActiveHour` **already 3**, `timeLeftInHour` 3600). Eleven deposits landed inside the first five seconds of the new hour — `totalTxCount` 1341 → 1352, contributors 816 → 826 — so `lastActiveHour()` had rolled before the first poll after the boundary, exactly as it did at 21:58:47. Two facts the series pins anyway: `timeLeftInHour()` reads **3600 at the top of an hour, never 0** (H12), and it steps in 12-second jumps because `eth_call` runs against the latest *block*, so state trails wall clock by up to one block — a boundary poll must keep going for ~30 s past `HH:58:47`. See "Hunting the quiet crossing" below |
| `20260816T225143Z_curve-probe.json` | 2026-08-16 22:51:43Z | `curve-probe` | **The sqrt curve now has an onchain witness.** `previewPoints(uint256)` for twelve weights and `pointsOf`/`weightOf` for four real wallets, all 20 calls answered. Every return equals `(isqrt(weight) * 1000) // 10**9` computed locally: `0`, `1`, `1e9-1` and `1e9` all floor to **0 points** (the floor is real, not a rounding artefact), `1e18 → 1000`, `4e18 → 2000`, `100e18 → 10000`, `1000e18 → 31622`, `2000e18 → 44721`, and the three non-squares land on 1732 / 2645 / 21473. The wallet half cross-checks the *fold* as well: `weightOf` returns 902.10737 / 333.596 / 125.0828 / 117.96 ETH, exactly the `Deposited.newWeight` totals folded out of `../tenderly_logs.json`, and `pointsOf` #1 is 30035, the number the mechanics doc estimated. State-only bundle (`--no-logs --no-blockscout`) — the history is already archived in the `grace-late` bundle one minute earlier |
| `20260816T225006Z_grace-late.json` | 2026-08-16 22:50:06Z | `grace-late` | The rig proven end to end, and a genuinely new state: hour **2**, `earlyMultiplierBps()` decayed to **18812** (0x497c) from the 19491 of the 21:04 round, `isSettled()` false, `ethNeededThisHour()` 0 (grace). Scale has moved a long way past the research capture — **794** contributors, 1282 deposits, **12547.77 ETH** routed, **2077** logs in one sweep against the 377 of `../tenderly_logs.json`. Balance 0, so nothing has been force-fed. 21/21 views, no errors, `block_timestamps` for the newest 40 logs (15 distinct blocks) — the first capture that has them at all |

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

### Still synthetic

Fixtures the build tests against that have no real payload yet, and why:

| fixture | status |
|---|---|
| hour-boundary with a **stale** `lastActiveHour` | waiting on a quiet crossing (the busy one is already captured in `../hour_boundary_h1_h2.json`) |
| post-grace flat multiplier | window opens 2026-08-17 19:58:47 UTC |
| judged hour with a deficit | needs a judged hour that is short with time left on it |
| settled state + the `Settled` log | earliest 2026-08-17 20:58:47 UTC; one-shot, unrepeatable |
| `HourSaved` log row | **may never fire** — it needs a judged hour to cross the threshold from below. If the game dies at hour 24 the event never exists. Do not block on it |
| `Rescued` log row | needs someone to force-feed ETH and the deployer to sweep it; realistically never |
| `creditedDelta == 0` deposit | needs a single send above the 1000 ETH cap; the largest real one is 461.1 ETH. Do not wait for it |
