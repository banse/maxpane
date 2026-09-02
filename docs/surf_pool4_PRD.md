# PRD — surf `p` POOL4 view

**Status:** proposed 2026-09-01. Source of truth for mechanics:
`docs/imd_pool4_mechanics.md`. Read that first — every claim below leans on it.

**Not a ninth dashboard.** A third body on `SurfScreen`, on the surf `l` / curator `y`/`f`
precedent: `p` swaps the dashboard body for POOL4's own panels, `escape` backs out one-way, and
the hero row stays mounted so LAUNCHPAD/FLOW/BURN/SUPPLY never goes dark. **No six-surface
renumber**: `app.py`, `__main__.py` and `GAMES` are untouched.

---

## 1. Why this view exists

pool4 makes IMD's pool a one-way ratchet: buys drain the reserve, sells burn 89.1% of what
they sell, and 1% of every swap is retained to pay for the protocol's own inference. Three
things follow that no existing surf panel can answer:

1. **How fast is supply actually being destroyed, and how close is the reserve to the floor
   that stops it?** `capFloor` is owner-settable on an unverified contract. This is the single
   most consequential number in the design and nothing displays it today.
2. **Is the split still the split?** 1% / 89.1% / 9.9% held to the basis point across three
   Sepolia launches. It is a *live* ratio, and the view must measure it rather than repeat it.
3. **What is a staker actually being paid, and by what?** sIMD's yield is rate-limited by
   `dripRatePerSecond`, not by pool volume. An APR quoted off fee flow would be wrong by orders
   of magnitude.

## 2. Network — MAINNET vs SEPOLIA

pool4 is not on mainnet yet. The view reads the **live Sepolia launch-3 deployment** until a
mainnet deployment is discovered, and switches automatically when one is.

**Every panel title carries the network word.** `THE RATCHET · SEPOLIA` / `THE RATCHET · MAINNET`.
Not a footnote, not a status-bar mention: a testnet number on an unmarked panel is a stale
number presented as live, and this one would be worse — it would be a *fictional* number
presented as live.

### Address discovery, and why it needs a fingerprint

Mainnet addresses do not exist yet, so they cannot be hardcoded. The dev announces onchain
first and this dashboard already polls the announce channel every tick, so the mainnet hook is
discoverable from the post that announces it.

**The announce channel is attacker-writable by design** — anyone can send it a UTF-8 calldata
tx, and six community replies are already in it. So a `0x…` string scraped from the feed is
**untrusted input**, and adopting one because it looked like an address is how this view would
end up rendering an attacker's contract as the protocol's.

Two gates, both required:

* **Provenance.** Only a *self-post* (`from == to == channel`) is a candidate. Replies and
  inbound txs are never scanned for addresses.
* **Fingerprint.** A candidate is adopted only if the chain agrees it is the hook: the low 14
  bits of the address are `0x2840` (BEFORE_INITIALIZE | BEFORE_ADD_LIQUIDITY | AFTER_SWAP — a v4
  hook cannot lie about this, the PoolManager enforces it at initialize), corroborated by
  `getHookPermissions()` returning the same mask, **and** `rewardShareBps()`,
  `BPS_DENOMINATOR()`, `burnSink()`, `token()` and `poolManager()` all answer, **and** `token()`
  returns the known mainnet IMD address `0xD34a99Bc…`. Anything less stays undiscovered.

Until both gates pass, the view renders SEPOLIA. `rewardsRecipient()` and the vault/dripper are
then read *off the adopted hook*, never scraped — the hook names them itself.

## 3. Layout

`SURF_POOL4_FULL_LAYOUT_COLUMNS` / `_ROWS`, its own constants, measured in situ — not derived
from the launchpad view's 138/31 and not assumed equal to them. The sweep starts away from 138
so it cannot agree with the neighbouring pin by construction. It must land at or under
`__main__.FULL_LAYOUT_COLUMNS` (143).

Body is a `Horizontal`, mirroring `#surf-launchpad-body`: a left column holding the one panel
with unbounded rows over the one summary, and a right rail of three fixed-height summaries.

```
┌ hero (untouched, stays mounted) ─────────────────────────────────────────────┐
│ LAUNCHPAD   │   FLOW    │   BURN    │  SUPPLY                                │
└──────────────────────────────────────────────────────────────────────────────┘
┌ #surf-pool4-left ──────────────────────┐┌ #surf-pool4-rail ──────────────────┐
│ POOL4 FLOW · SEPOLIA                   ││ THE RATCHET · SEPOLIA              │
│  (swap-by-swap: side, size, burned,    ││  reserve · floor · distance · %    │
│   stakers, inference)                  ││  burned · sparkline                │
│                                        │├────────────────────────────────────┤
├────────────────────────────────────────┤│ sIMD VAULT · SEPOLIA               │
│ THE SPLIT · SEPOLIA                    ││  share price · TVL · drip · backlog│
│  measured 1.00 / 89.10 / 9.90          │├────────────────────────────────────┤
│  + cumulative totals                   ││ THE HATCHES · SEPOLIA              │
└────────────────────────────────────────┘└────────────────────────────────────┘
```

Rules that apply without restating them: reserve `scrollbar-gutter: stable` on both columns,
give every `1fr` child a `min-height`, fit every hand-built row on `cell_len` not `len()`,
`overflow-y: auto` on the columns, and mirror every screen rule into `themes/minimal.tcss`.

> ### ⚠ AS BUILT, TWO PANELS ARE SWAPPED (WP8, 2026-09-01 — follow-up W3)
>
> The wireframe above and the §4 panel order below are the **specification**, and
> they are left as written. What shipped puts **THE HATCHES** in the left column and
> **THE SPLIT** in the rail:
>
> ```
> ┌ #surf-pool4-left ──────────────────────┐┌ #surf-pool4-rail ──────────────────┐
> │ THE HATCHES · SEPOLIA   (auto)         ││ THE SPLIT · SEPOLIA     (auto)     │
> ├────────────────────────────────────────┤├────────────────────────────────────┤
> │ POOL4 FLOW · SEPOLIA    (1fr, floor 6) ││ THE RATCHET · SEPOLIA   (auto)     │
> │                                        │├────────────────────────────────────┤
> │                                        ││ sIMD VAULT · SEPOLIA    (1fr, 10)  │
> └────────────────────────────────────────┘└────────────────────────────────────┘
> ```
>
> **Why, measured rather than argued.** The columns are split by *what moves*, not by
> what the panels are about: the left column holds the two whose height answers to a
> payload (HATCHES grows one row per lever; the flow log is unbounded), the rail holds
> the three whose line count is a constant. The rail is the taller column and therefore
> sets the body's height pin, so keeping payload-sized panels out of it makes that pin
> the same number under every payload.
>
> Both arrangements were rendered. **The width is identical** — pin 106, `SurfPool4Flow`
> binding at 105, no unadvertised clip at any width, in both. The difference is rows:
>
> | arrangement | width pin | height pin | HATCHES cut with no marker |
> |---|---|---|---|
> | as built | 106 | **44** | never |
> | this §3 wireframe, HATCHES floored at today's 21 rows | 106 | 54 | at 54–55 rows |
> | this §3 wireframe, HATCHES floored at its 23-row cap | 106 | 56 | never |
>
> The built row read 43 until 2026-09-02, when THE SPLIT gained a line (WP5's wrapped
> counter evidence plus W1's reconciliation). The PRD rows are unaffected: THE SPLIT is
> in the *left* column there, where ten rows were already spare.
>
> So the swap was **forced on rows, not on columns** — ten rows, plus a two-row
> window where HATCHES loses content with `‹ taller` dark. It is *not* a width decision
> and must not be written up as one: the rail's 43-column need exists only because
> HATCHES is not in it, so quoting it as the reason HATCHES had to move is circular.
>
> The reasoning and the full sweep live beside the code, in
> `screens/surf.SURF_POOL4_FULL_LAYOUT_ROWS` and `…_COLUMNS`.
>
> §4 below describes each panel's *content*, which the swap does not change; only the
> "(left)" / "(rail)" labels in its subheadings are superseded by the diagram here.

## 4. The panels

### 4.1 POOL4 FLOW (left, unbounded rows)

One row per settled swap, newest first, from `ClaimsSettled` / `FeeCollected` / the buy-side
reserve event. `RichLog(wrap=False)` on `widgets/surf/activity.py`'s `_budget` / `_row_cols`
ladder — **import it, do not copy it**; that helper is already duplicated three times in this
package and the `len()`-vs-`cell_len()` bug it carries has to be fixed three times as a result.

Columns, widest tier first, each dropping out with the panel naming what it shed in its title:

| col | content |
|---|---|
| age | `_fmt_age` |
| side | `BUY` / `SELL` |
| size | IMD in (sell) or IMD out (buy) |
| burned | `ClaimsSettled[0]`, sells only |
| stakers | `ClaimsSettled[1]`, sells only |
| inference | `FeeCollected` leg, in the currency it was taken in |

A buy has no burn and no staker leg. That is a **representable zero, not a dash** — the row
must read as "we looked and this swap burned nothing", never as "we could not look". The
degraded state is a separate, explicit row.

### 4.2 THE SPLIT (left, fixed)

The measured split and the counters behind it:

* `inference / burn / stakers` as percentages **computed from the live counters**
  (`totalFeeToken`, `totalBurned`, `totalRewarded`), never from the 1/89.1/9.9 in the research
  doc. If the measured ratio drifts from `rewardShareBps()`, the panel says so — that drift is
  the single most interesting thing this panel could ever show.
* `totalBurned` · `totalRewarded` · `totalFeeToken` · `retainedEth`, and `lastClaimBlock`.
* Unsettled: what the last accrual event owes that `ClaimsSettled` has not yet paid.

### 4.3 THE RATCHET (rail)

* `tokensInPool()` — the reserve.
* `capFloor()` — the floor, and the **distance to it**, in IMD and as a percentage.
* Burned as a share of `totalSupply()`.
* A reserve sparkline, through `widgets/sparkline_common` (do not copy the helpers).
* `ethInPool()`, `positionLiquidity()`, `currentTick()` vs `refTick()`, and whether the
  backstop is centred.

**The floor binds the swap path and nothing wider, and the panel must not overclaim it.**
`capFloor` is not proven from source — the hook is unverified — but it is now strongly evidenced:
on launch 1 a buy took the reserve from 152,030,338.5414 to **exactly 50,000,000.000000000000000000**,
the wei-exact `capFloor()`. So "distance to floor" is a real, binding number and the panel should
show it as one.

What it must **not** imply is that the floor holds against everything. Launch 1's live
`tokensInPool()` now reads 48,849,555.29 — *below* its own floor — because a backstop rebalance
sits between the clamp and that reading. So a reserve under the floor is a legitimate state, not
a bug and not a degraded read, and the panel renders it as the number it is rather than clamping
it to zero distance or flagging an error.

### 4.4 sIMD VAULT (rail)

* Share price from `convertToAssets(1e18)`, and its change since the view opened.
* `totalAssets()` (TVL in IMD), `totalSupply()` (shares).
* `dripRatePerSecond()` per day, `drippable()`, `canDrip()`, and the **backlog** — the
  dripper's IMD balance — expressed as **days of runway at the current rate**. That framing is
  the panel's whole point: a year-deep backlog against an 86,400/day stream says the yield is
  rate-limited, and a raw balance does not.
* Implied APR **derived from the drip rate and TVL**, never from fee flow, and suppressed
  entirely when TVL is zero rather than rendering an infinity.

### 4.5 THE HATCHES (rail)

The powers that are live and the ones that are gone. Every entry is a live read:

* vault: `owner()`, `paused()` — and that `rescueERC20` can move staked IMD while an owner
  exists. Renounced shows as renounced.
* dripper: `owner()`.
* hook: `owner()`, `marketOpen()`, `rebalanceEnabled()`, `burnSink()`, `rewardsRecipient()`.
* **BOND: not deployed.** The third tab on `imd.fun/pool4/` has no contract on either chain.
  The panel says that in as many words and shows nothing else, because there is nothing else
  to show. When one appears, it appears here.

## 5. Data

* **`data/surf_pool4.py`** — pure: selector constants, the `0x2840` flag check, calldata
  builders, response decoders, the split/backlog/runway maths. No I/O, no clock, no Textual.
  The flag check is `addr_low14 == BEFORE_INITIALIZE | BEFORE_ADD_LIQUIDITY | AFTER_SWAP`
  expressed as named constants, not a magic `0x2840`.
* **v4 pool state** reuses `data/surf_v4.py` (`pool_state_slots`, `decode_slot0`) and
  `data/keccak.py`. Neither is re-implemented.
* **Manager**: a new `TIER_POOL4` slot on `SurfManager` with its own last-good and its own
  `as_of_hhmm`, on the curator `TIER_ANALYSIS` precedent. The marker advances only when new
  data actually lands.
* **The read is spawned, never awaited** — first paint must not be behind it, the same
  contract `test_the_first_payload_is_not_behind_the_analysis_read` pins on curator.
* **Sepolia RPC pool** is separate from the mainnet pools. Per CLAUDE.md, state and logs need
  different endpoints; `ethereum-rpc.publicnode.com` refuses archive `eth_getLogs`, so log
  reads go through the tenderly/drpc pool and the Sepolia equivalent.
* A failed read degrades to an explicit unavailable state behind `as of HH:MM`. A failed read
  is `None`, never `0`, and no sentinel is ever written into the reserve series.

## 6. Wiring

* `p` → `action_toggle_pool4`, `escape` → back to the dashboard, idempotent both ways.
* Status hint becomes `l launchpad · p pool4` — measured, not assumed, against the bar's
  budget at the full layout width.
* Composed once and hidden by `display`, so the first `p` paints a complete frame.

## 7. What this view will not do

* No signing, no calldata for a state change, no keys. `drip()` and `rebalance()` are
  permissionless and pay a keeper reward; this dashboard **displays that they are callable and
  by whom** and never offers to call one.
* No API keys. Sepolia and mainnet RPC plus Blockscout REST, all keyless.
* No hardcoded split, no hardcoded APR, no hardcoded mainnet address.
* No testnet number rendered without the network word beside it.
