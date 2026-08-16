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
| `20260816T225006Z_grace-late.json` | 2026-08-16 22:50:06Z | `grace-late` | The rig proven end to end, and a genuinely new state: hour **2**, `earlyMultiplierBps()` decayed to **18812** (0x497c) from the 19491 of the 21:04 round, `isSettled()` false, `ethNeededThisHour()` 0 (grace). Scale has moved a long way past the research capture — **794** contributors, 1282 deposits, **12547.77 ETH** routed, **2077** logs in one sweep against the 377 of `../tenderly_logs.json`. Balance 0, so nothing has been force-fed. 21/21 views, no errors, `block_timestamps` for the newest 40 logs (15 distinct blocks) — the first capture that has them at all |

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
