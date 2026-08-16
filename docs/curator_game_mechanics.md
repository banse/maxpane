# WhitelistCurator — surfsurf.eth's zero-custody allowlist game

Research for a MaxPane dashboard. All numbers verified onchain 2026-08-16 ~21:13 UTC — the
contract was **~75 minutes old** at capture time, so every "live scale" figure below is a
snapshot of a game that was accelerating while we measured it.

**What it is.** A permissionless onchain whitelist: you send ETH, the same transaction refunds
every wei, and what persists is the record — your high-water single send, a weight, a
square-root points score, and membership in a list any gating contract can read at mint time
(no merkle root, no snapshot). The contract doc names the intended uses: mint whitelists,
airdrop distribution, reputation input. Two rules make it a spectator sport: **escalation**
(only beating your own high-water mark counts) and **settlement** (a doomsday clock — after a
24 h grace period, any completed clock hour that attracts less than 5 ETH freezes the list
forever). Verified source, no proxy, no upgrade path, no pause, no mutable parameter.

## Cast of addresses

| role | address | notes |
|---|---|---|
| WhitelistCurator | `0xcb0b0531e86A9aC36fa865ca8e3DbcCF047fDA91` | Ethereum mainnet, verified (Blockscout, `src/WhitelistCurator.sol`, solc 0.8.28) |
| deployer / surfsurf.eth | `0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7` | surf dashboard's `DEV_WALLET`. Only power: `rescue()` force-fed ETH |
| creation tx | `0x240bf1a83d08dd10ff28027f4bdd7f9c0fa7f57629a13cfaafdd6e708dcc641f` | block 25 769 870, 2026-08-16 19:58:47 UTC; `launchTime` == creation timestamp (1786910327) |
| announce channel | `0x200E710aCAA6A93bbc77146026328C40F1d60fB1` | has **not** mentioned the curator as of 2026-08-16 21:13 UTC (all posts since Aug 1 decoded) |

## Deployed parameters (constructor-set, immutable, cross-checked eth_call vs creation-tx input)

| param | value | meaning |
|---|---|---|
| `hourlyThreshold` | 5 ETH | raw volume a completed judged hour must attract, or the contract settles |
| `gracePeriod` | 86 400 s (24 h) | no judging until it ends **2026-08-17 19:58:47 UTC**; also the early-bird decay window |
| `hourDuration` | 3 600 s | hour index = `(block.timestamp − launchTime) / 3600` |
| `firstJudgedHour` | 24 | derived `gracePeriod / hourDuration`; first judged bucket completes 2026-08-17 20:58:47 UTC — **the earliest possible settlement moment** |
| `minDeposit` | 0.05 ETH | minimum first send per address |
| `minEscalation` | 0.1 ETH | every later send must beat your own high-water by at least this |
| `creditCap` | 1 000 ETH | high-water past this adds zero weight (but full hourly volume) |
| `POINTS_PER_ETH` | 1000 (constant) | scale factor of the sqrt curve |

Read all of these live per the CLAUDE.md rule — but they are immutables, so a `once` cache
tier fits.

## The math (exact, quoted from verified source)

**Escalation gate:** `required = highWater == 0 ? minDeposit : highWater + minEscalation`;
below it the tx reverts `MustEscalate(sent, required)`. Sending 1 ETH a thousand times is
worthless; 1 ETH then 2 ETH nets 2 ETH of credit. Lifetime credit telescopes to
`min(final high-water, creditCap)`.

**Weight:** `creditedDelta = min(amount, cap) − min(oldHighWater, cap)`, then
`weightAdded = creditedDelta × earlyBps / 10_000`.

**Early-bird multiplier:** `earlyBps = 20_000 − elapsed × 10_000 / gracePeriod` while in
grace, flat `10_000` after — 2.0000× at launch decaying linearly *per second* to 1.0000× at
grace end. The only multiplier; hard weight ceiling is therefore 2000 ETH-equivalent.
Verified against live logs: a 0.05 ETH first deposit at `earlyBps` 19 975 produced
`weightAdded` 0.099875 exactly.

**Points (display-only sqrt curve):** `points = floor(sqrt(weight_wei)) × 1000 / 1e9`.
1 ETH weight → 1000 pts, 4 → 2000, 100 → 10 000, 1000 → 31 622; absolute ceiling
(2000 ETH weight) = 44 721. Deliberately concave — the contract's own doc comment says the
curve **actively rewards splitting across wallets** and delegates sybil-clustering to
off-chain analysis of the event data. `weightOf()` is the precise curve-free record;
`pointsOf()` is the display number; `previewPoints(weight)` is a pure quoting function.
Anything recomputing points from weight must floor exactly like the contract's Newton-sqrt.

**EOA-only:** both `tx.origin != msg.sender` and `msg.sender.code.length != 0` revert
`OnlyEOA` (the latter also catches EIP-7702 delegated accounts). No flash-loan can compose
borrow→deposit→refund→repay: **every high-water mark was real balance in a real EOA at that
moment** — the only capital claim the numbers support (see hazards).

## Settlement (the doomsday clock)

- Hours 0–23 (grace) are never judged. From hour 24 on, **every completed hour** must have
  received ≥ 5 ETH raw deposit volume. The in-progress hour is never judged — an hour can be
  saved at its last second. A silent hour is a failed hour.
- **Settlement is lazy and derived, not pushed.** Every deposit self-checks `_isShort` and
  reverts `AlreadySettled` after a failed hour even if nobody ever calls `settle()`.
  `isSettled()` returns `_settled || _isShort(currentHour())` — true the second failure
  becomes final, never flips back. `settle()` is **permissionless**, only persists the flag,
  and emits `Settled(hour, timestamp, totalContributors, totalVolume)` — it may lag actual
  death indefinitely.
- Only one hour bucket exists in state (`_lastActiveHour` + its total); every hour after it
  is provably empty because deposits are the only writer.
- On settlement everything freezes: no more deposits, all records/weights/points immutable,
  all views readable forever. Deposits inside the hour that fails lose nothing (already
  refunded in their own tx; records stand).
- `HourSaved(savior, hour, hourTotal)` fires when a deposit pushes a judged at-risk hour from
  below to ≥ threshold. Explicitly informational — **no reward** ("a rescue bonus would pay
  most for the least risk").

## Events (topic0 verified)

| event | topic0 | notes |
|---|---|---|
| `Launched(...)` 7×uint256 | `0x1a3476a1…493f59` | once, constructor |
| `Deposited(address indexed contributor, uint256 indexed hour, amount, creditedDelta, weightAdded, newWeight, txCount, hourTotal, earlyBps)` | `0xb8385097…669cb3` | every recorded deposit; carries running totals — leaderboard and hourly history rebuild from this event alone |
| `FirstDeposit(address indexed contributor, uint256 indexed index, timestamp)` | `0xe5a1ae96…242918` | index is 1-based and monotonic == totalContributors; the only enumeration of the list |
| `HourSaved(address indexed savior, uint256 indexed hour, hourTotal)` | `0xab7cfcae…262209` | judged hours only |
| `Settled(uint256 indexed hour, timestamp, totalContributors, totalVolume)` | `0x0b88c5bd…709dd5` | the archival record of death, not the live signal |
| `Rescued(address indexed to, amount)` | `0x8aec0ce3…630402` | deployer sweeping force-fed ETH; never fired = nothing was ever forced |

## View surface for a keyless dashboard

**One batched eth_call round (fast tier, state RPC) covers the whole doomsday widget:**
`isSettled()`, `currentHour()`, `currentHourTotal()`, `ethNeededThisHour()`,
`timeLeftInHour()`, `lastActiveHour()`, `earlyMultiplierBps()`, `stats()`
(= volume/people/txs), plus the immutables. Per-wallet detail for a *known* address
(`MAXPANE_WALLET`): `pointsOf`, `weightOf`, `contributedBy`, `txCountOf`, `firstHourOf`,
`requiredNext` (the exact wei the wallet must send next — quote it before someone burns gas
on `MustEscalate`).

**Needs `eth_getLogs` history (logs RPC pool):** the contributor list itself (no onchain
enumeration — page `FirstDeposit` by index), the leaderboard (fold `Deposited.newWeight`
per contributor — the event carries running totals, no re-derivation), hour-by-hour volume
and closest-call history (only the last active hour lives in state), escalation ladders,
`HourSaved` heroes, `Settled`, `Rescued`.

**Validated endpoints (this research, live):** state — `ethereum-rpc.publicnode.com`
(all 21 parameterless views returned, zero failures); logs —
`gateway.tenderly.co/public/mainnet` (226 `Deposited` from deploy block `0x189360e` in one
sweep); `eth.drpc.org` failed once with routing-message text ("Can't route your request…") —
classify by message text and fail over. Blockscout REST
(`eth.blockscout.com/api/v2/addresses/<addr>/logs`, 8 pages) reconciled with the RPC sweep
exactly. Etherscan page fetch returned 403 — do not depend on it.

## Live scale (verified 2026-08-16 21:13 UTC, hour 1 of the game)

- 145 contributors, 231 deposits, **1630 ETH gross routed and refunded** in 75 minutes.
- Ramp: quiet first 20 min → violent 20:38–21:08 peak (≈500 ETH per 10-min bucket at max).
- Leaderboard: #1 `0x381fe486…` credit 461.1 ETH (ladder 1.1 → 461.1, two txs), weight
  902.1, ≈30 035 pts. #2 170 ETH (25→45→170). #3 63.5 ETH (1→63.5).
- **A textbook fan-out farm is already in the data:** 9 wallets each sent exactly 60 ETH once,
  in consecutive blocks 25 770 115–25 770 143 (~6 min window), taking ranks 4–12 — precisely
  the split the sqrt curve rewards and the doc comment predicts.
- A grinder (`0xba7610…`) is at 13 deposits, +0.1 ETH minimum escalations every block or two.
- Median credit 0.25 ETH; 53 wallets at the 0.05 minimum; largest single send 461.1 ETH.
- Not settled (structurally cannot be before 2026-08-17 20:58:47 UTC). `HourSaved`,
  `Settled`, `Rescued`: never fired.

## Cross-links to existing MaxPane dashboards

- The deployer is surf's `DEV_WALLET`; the curator address appears **nowhere** in the repo.
  Surf's dev-activity widget would render the deploy as an unknown dimmed counterparty; its
  announce feed would surface a post about it only if the channel ever posts one (it hasn't).
- Launched **unannounced**: nothing on the announce channel, X, Farcaster, Dune, or Mirror as
  of capture — seven distinct web queries came up empty. 1630 ETH found it onchain anyway.
- The channel's last self-post (Aug 16 04:50 UTC, ~15 h before deploy) talks about moving all
  LP to Uniswap v4 and burning more IMD — the curator may be part of that arc ("initial
  compute event"?), but that is inference, not evidence.

## Hazards for implementation

- **Every demand number is gas-priced, not capital-priced.** All ETH is refunded in-tx, so
  hourly volume, total volume, contributor count and `HourSaved` are all fakeable for the
  price of gas (the doc comment says so itself). Never render volume as TVL or capital at
  risk. The one honest capital claim: each high-water mark was really held by a real EOA at
  that moment (EOA gate blocks atomic flash-loan composition).
- **`isSettled()` is the truth; the `Settled` event is the obituary.** A dashboard keying
  GAME OVER off the event shows a live game on a dead contract indefinitely. Poll the view.
  Unlike surf's `hook_status` trap, this latch is safe: derived from contract state by the
  contract itself, one-way by construction — but keep the evidence-record pattern anyway.
- **`currentHourTotal()` drops to 0 at every hour boundary** while `lastActiveHour()` still
  shows the previous bucket. A naive state-poll sparkline reads that as a crash. History
  comes from `Deposited` logs only.
- **`creditedDelta` can legitimately be 0** (deposit above `creditCap`, which still counts
  fully toward hourly survival). Never divide by it; weight ∝ volume does not hold.
- **Nonzero contract balance always means forced ETH** (selfdestruct / fee-recipient), never
  deposits. Render as anomaly, not TVL. `rescue()` structurally cannot touch deposits — the
  refund happens before the balance ever rests.
- **Packed-struct off-by-one:** raw `contributors(addr)` returns `firstHour` with a +1 offset
  (0 = never); `firstHourOf()` un-shifts it. `FirstDeposit.index` is 1-based.
- Deposits after death revert `AlreadySettled` (gas lost, principal returned by revert);
  sends below `requiredNext` revert `MustEscalate`; 2300-gas `.transfer` sends can never
  succeed; contracts/Safes/4337/7702 accounts revert `OnlyEOA`.
- Rounding: `weightAdded` floors, `earlyBps` decay floors ≤ 1 bp in the depositor's favor,
  `_curve` floors the integer sqrt. Negligible, but recompute-and-compare tests must floor
  identically.

## Open questions (not blockers)

- **What does the list gate?** Unknown. No announcement anywhere. Candidate arcs: the IMD/
  IDMD "initial compute event", a FrenPet-adjacent mint, or something new. The gating
  contract, when it appears, will read this list directly.
- Will the announce channel post about it (retro-announcement)? Re-check each refresh via
  the surf feed.
- How long does the community keep feeding the 5 ETH/hour clock once the 2× early-bird decays
  to 1×? The first judged hour completes 2026-08-17 20:58:47 UTC; the dashboard may launch
  into a settled game and must be equally good as an archive.
