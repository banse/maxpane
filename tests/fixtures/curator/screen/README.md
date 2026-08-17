# `tests/fixtures/curator/screen/` — WP6's slices

Three frozen `CURATOR_KEYS` payloads, one per phase, consumed by
`tests/screens/test_curator_screen.py`. Nothing in them was typed by hand: all
three are the output of the **real producer** — WP5's log decoders
(`data/curator_manager.decode_deposit` / `decode_first_deposit`) and WP3's
`analytics/curator_signals.build_signals` — run offline over a committed
capture. A plausible-looking number invented here would calibrate the screen's
width sweep against a payload the manager can never emit.

| file | phase | status |
|---|---|---|
| `grace_payload.json` | `grace` | **real**, end to end |
| `judged_payload.json` | `judged` | **synthetic** — re-point when capture B lands |
| `settled_payload.json` | `settled` | **synthetic** — re-point when capture C lands |

## Source

`tests/fixtures/curator/captures/live/20260817T000322Z_grace-late.json` — one
WP1 bundle, every section fetched in the same second (`captured_at`
1786925002 = 2026-08-17T00:03:22Z, chain head 25771089), so the contract's own
counters and the folded log history reconcile instead of disagreeing across a
ten-minute research window the way the 2026-08-16 21:04–21:14 captures do by
design.

It holds the 21-view state batch, `eth_getBalance` (`0x0` — the healthy
reading; every wei is refunded in-tx), and 5 222 log rows: 1 `Launched`,
2 291 `FirstDeposit` and 2 930 `Deposited`, each carrying its own
`blockTimestamp`.

Decoded facts the payloads inherit, for orientation: `launchTime` 1786910327,
`gracePeriod` 86400, `hourDuration` 3600, `hourlyThreshold` 5e18,
`firstJudgedHour` 24, `POINTS_PER_ETH` 1000, `creditCap` 1000e18,
`earlyMultiplierBps` 0x477f = **18303 = 1.8303×** at that instant (it decays;
the 21:04 research round reads 19491 = 1.9491×), `stats()` = 15 981.146 ETH
routed / 2 291 contributors / 2 930 txs.

## The `you` wallet

`wallet_state` is built from the fold's own **rank-1** contributor
(`0x75d5…b074`: 30 853 points, 490.9 ETH high-water, 12 deposits, first seen in
hour 1), with `required_next_wei = highWater + minEscalation` — which is
`requiredNext()`'s body verbatim (`source.sol:535-538`), not a guess.

Rank 1 rather than a middle rank on purpose: the YOU row is the signal rail's
widest and its width is a function of the reader's own credit, so the
full-layout sweep is calibrated against the widest **real** wallet the capture
contains. See the test module's docstring.

## The synthetic transformation (judged / settled)

Capture B (a post-grace judged hour) and capture C (the settlement transition)
had not landed when these were written. Both files are therefore the **same
real deposits replayed one grace period later**: every `DepositEvent`'s `hour`
gains 24 and its `ts` gains 86 400, so real grace hours 0–3 become judged hours
24–27 with their real volumes (851.89, 9987.26, 2263.83, 2738.92 ETH — the four
folds WP3 pinned), and `now_ts` moves by the same 86 400.

The in-progress hour 28 keeps only as many of the real hour-4 deposits as fit
under 30 % of the hourly bar, so the fast-tier reads a post-grace contract would
answer are consistent with the fold rather than contradicting it:

* `judged`: `isSettled() == false`, `currentHour() == 28`,
  `earlyMultiplierBps() == 10000` exactly (the flat post-grace multiplier),
  `ethNeededThisHour() == 5e18 − fed` (a live deficit), `timeLeftInHour() == 741`
  — under `AT_RISK_RED_SECONDS`, so HOUR AT RISK is in its red state.
* `settled`: the same, plus the manager's settlement **latch** —
  `SettlementRecord(settled=True, block_number=25795511, observed_at=…,
  settled_hour=28, settled_at_ts=…, total_contributors=…, total_volume_wei=…)` —
  and `now_ts` one hour further on, which is what makes `lived 1 d 4 h` and
  `sig_settled_state == "fired"` (the observation is younger than `FIRED_TTL_S`).

Both loaders in the test module carry the tree-wide marker
`# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`, so
`rg "SYNTHETIC — re-point"` remains the whole checklist (WP7.13 closes it).

## Regenerating

```python
# .venv/bin/python, from the repo root.  Writes the three files above.
import dataclasses, json
from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data.curator_manager import decode_deposit, decode_first_deposit
from maxpane_dashboard.data.curator_models import SettlementRecord, WalletState, CURATOR_KEYS
from maxpane_dashboard.analytics.curator_signals import READING_KEYS, build_signals, fold_deposits

BUNDLE = 'tests/fixtures/curator/captures/live/20260817T000322Z_grace-late.json'
B = json.load(open(BUNDLE))
st = {k: v['result'] for k, v in B['state'].items()}
u = lambda h: int(h, 16)
words = lambda h: [h[2:][i * 64:(i + 1) * 64] for i in range(len(h[2:]) // 64)]
stats = words(st[A.SEL_STATS])
NOW = float(B['captured_at'])
GRACE = u(st[A.SEL_GRACE_PERIOD])
MIN_ESC = u(st[A.SEL_MIN_ESCALATION])
THRESH = u(st[A.SEL_HOURLY_THRESHOLD])

base = {k: None for k in READING_KEYS}
base.update(
    settled=bool(u(st[A.SEL_IS_SETTLED])), current_hour=u(st[A.SEL_CURRENT_HOUR]),
    hour_needed_wei=u(st[A.SEL_ETH_NEEDED_THIS_HOUR]),
    hour_seconds_left=u(st[A.SEL_TIME_LEFT_IN_HOUR]),
    early_bps=u(st[A.SEL_EARLY_MULTIPLIER_BPS]), volume_wei=int(stats[0], 16),
    contributors=int(stats[1], 16), tx_count=int(stats[2], 16),
    forced_balance_wei=u(B['balance']), launch_time=u(st[A.SEL_LAUNCH_TIME]),
    grace_period=GRACE, hour_duration=u(st[A.SEL_HOUR_DURATION]),
    hourly_threshold_wei=THRESH, first_judged_hour=u(st[A.SEL_FIRST_JUDGED_HOUR]),
    points_per_eth=u(st[A.SEL_POINTS_PER_ETH]), credit_cap_wei=u(st[A.SEL_CREDIT_CAP]))

by = {}
for r in B['logs']:
    by.setdefault((r.get('topics') or [''])[0].lower(), []).append(r)
dep = [d for d in (decode_deposit(r) for r in by.get(A.TOPIC_DEPOSITED.lower(), [])) if d]
fd = [d for d in (decode_first_deposit(r) for r in by.get(A.TOPIC_FIRST_DEPOSIT.lower(), [])) if d]
base.update(deposits=dep, first_deposits=fd, hour_saved=[], rescued_total_wei=0)

top = fold_deposits(dep, fd, points_per_eth=base['points_per_eth'])[0]
base['wallet_state'] = WalletState(
    address=top.address, points=top.points, weight_wei=top.weight_wei,
    contributed_wei=top.credit_wei, tx_count=top.tx_count, first_hour=top.first_hour,
    has_joined=True, required_next_wei=top.credit_wei + MIN_ESC)

SH = 24                                    # one grace period, in hours
shift = [dataclasses.replace(d, hour=d.hour + SH,
                             ts=None if d.ts is None else d.ts + SH * 3600) for d in dep]
keep = [d for d in shift if d.hour < 4 + SH]
partial = sorted([d for d in shift if d.hour == 4 + SH],
                 key=lambda d: (d.block_number, d.log_index))
run, total, target = [], 0, THRESH * 3 // 10
for d in partial:
    if total + d.amount_wei > target:
        continue
    run.append(d); total += d.amount_wei
jd = keep + run

jr = dict(base)
jr.update(deposits=jd, settled=False, current_hour=4 + SH, early_bps=10000,
          hour_needed_wei=THRESH - total, hour_seconds_left=741,
          volume_wei=sum(d.amount_wei for d in jd), tx_count=len(jd))
JNOW, SNOW = NOW + SH * 3600, NOW + (SH + 1) * 3600
sr = dict(jr)
sr.update(settled=True, hour_needed_wei=THRESH - total, hour_seconds_left=3600,
          settlement_record=SettlementRecord(
              settled=True, block_number=25795511, observed_at=SNOW - 1804,
              settled_hour=4 + SH, settled_at_ts=int(SNOW - 1810),
              total_contributors=jr['contributors'], total_volume_wei=jr['volume_wei']))

for name, readings, now, hhmm in (('grace', base, NOW, '00:03'),
                                  ('judged', jr, JNOW, '20:15'),
                                  ('settled', sr, SNOW, '21:15')):
    payload = build_signals(readings, now_ts=now)
    payload['degraded'] = []
    payload['as_of'] = float(now)
    payload['as_of_hhmm'] = hhmm
    assert set(payload) == set(CURATOR_KEYS)
    with open(f'tests/fixtures/curator/screen/{name}_payload.json', 'w') as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write('\n')
```

`as_of_hhmm` is a rendered local-time string the manager produces with
`time.localtime`, so it is set explicitly rather than derived: deriving it here
would make the frozen payload depend on the machine's timezone, and the screen
renders it verbatim.
