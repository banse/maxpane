# SURF Dashboard — PRD

**Project:** surfsurf.eth — the onchain experiments of the FrenPet dev ("Mission Control")
**Target:** MaxPane dashboard #10, `--game surf`, position 7
**Chain:** Ethereum mainnet (chain id 1); Base only as read-only bridge counterpart
**Date:** 2026-08-08 (all live values verified this day)
**Status:** Design approved (lens: dev tracker · job: be early); ready for implementation planning

Source research: [`docs/surf_game_mechanics.md`](surf_game_mechanics.md)

---

## 1. Product summary

Adam (@surfcoderepeat, surfsurf.eth) ships experiments onchain-first: announcements are
UTF-8 calldata self-transactions from EOA `0x200E710a…`, project names get committed to
IPFS months before reveals, and the next launch's precondition (moving the Uniswap v3 LP)
is a single onchain event he has publicly promised to announce in advance.

The dashboard takes the **front-runner's seat**. Its job is to answer one question
continuously:

> **Did something just happen in the surfsurf universe — and how early am I?**

Everything on screen is either one of six detectors or the context to act on one.

### Why this subject earns a dashboard

- The announcement channel **emits no logs** — every event-driven tool (indexers,
  web3alert-style watchers keyed to logs) is structurally blind to it. Nonce polling sees
  a post within one refresh interval. That asymmetry *is* the edge.
- The dev published his own monitoring spec onchain (channel nonce 2, 2026-05-21):
  filter `from==to==channel`, decode calldata as UTF-8, poll ≥1/min. We implement his spec.
- The v4-hook launch has a committed, watchable precondition: liquidity leaving v3
  position #1167726 (owner frenpet.eth). The 33 ETH add on 2026-08-07 followed a
  12-minute onchain choreography (bridge → OFT mint → approve → add → announce) that the
  BRIDGE STAGE detector would have flagged at minute 3.

### Live scale (verified 2026-08-08)

| Metric | Value |
|---|---|
| Channel posts / total channel txs | 14 nonces / 21 txs |
| IMD supply (mainnet) | 2,376,731.87 (= 33.0% of FP supply, bridged 1:1) |
| IMD burned via LP-fee pipeline | ~58,849 IMD across 3 verified events (05-16, 07-31, 08-05) |
| IMD/WETH v3 pool | ~388k IMD + ~142.7 WETH (~$549k), price ≈ $0.71 |
| IDMD NFT | 2000/2000 minted, 667 holders, ~38 transfers/day |
| Identities written | 1/2000 (gate closed since 2026-05-14) |
| v4 hook | **not deployed** — all 19 existing IMD v4 pools are third-party, hookless |

## 2. Scope

**In:** the six detectors; the announcement feed (decoded, classified); dev activity of
both wallets (surfsurf.eth `0x047F606f…` + frenpet.eth `0xE764dA9b…`); IMD market +
FP parity; IDMD NFT stats; supply/burn tracking.

**Out:** FrenPet game data (the `frenpet` dashboard owns it); Vibecoins launchpad
tokens (quiet since Apr; revisit if the hook launches from that codebase); the X feed at
runtime (design-phase source only, per project rule); wallet-scoped personal positions
(`--wallet` integration is a possible v2); Base twin NFT `0x0000C048…` (stalled, unverified
source — mention in hero only if it wakes).

## 3. The flagship: six detectors

Each detector renders `state · age · one-line detail`. States: `OK` (baseline holds),
`WATCH` (precursor movement), `FIRED` (the event happened). Baselines advance immediately
on the successful read that detects an event — so a signal re-fires only on a *new* event —
but the rendered `FIRED` state persists for 24 h with its age (`FIRED 2h ago`), then relaxes
to `OK` with a `last: …` detail. Event timestamps are persisted in the cache so a restart
does not resurrect or lose a FIRED display.

| # | Signal | Poll | FIRED condition | Why it's early |
|---|---|---|---|---|
| 1 | NEW POST | `eth_getTransactionCount(0x200E710a…)` every refresh | nonce > baseline → fetch + decode body | sub-minute on a channel log-watchers can't see |
| 2 | LP MIGRATION | `NFPM.positions(1167726)` every refresh; frenpet.eth nonce | liquidity decrease → FIRED; any frenpet.eth nonce ↑ → WATCH; PoolManager `Initialize` with IMD + `hooks≠0x0` → FIRED "V4 LAUNCH" | he promised to announce before moving the LP; the decrease is the act itself |
| 3 | GATE OPEN | `identityAllowed()` eth_call every refresh | `false→true` flip; `IdentityHashUpdated` log count ↑ → detail | holders can write identities the moment it flips |
| 4 | NEW DEPLOY | both dev nonces every refresh; Blockscout tx page on change | new tx with `created_contract`, or announce-EOA outbound *contract call* | the ERC-8004 registration (nonce 4) was exactly this shape |
| 5 | BRIDGE STAGE | `eth_getLogs` IMD `Transfer(from=0x0, to∈{dev, ops})` recent window | any OFT bridge-in mint to a dev wallet | staging preceded the LP add by 12 min |
| 6 | BURN | BurnExecutor tx seen or verified supply drop | supply(t) < supply(t-1), both reads successful | informational; feeds the supply sparkline |

Baseline rules (correctness-critical): baselines live in the persisted cache and advance
**only on successful reads**. `None` never compares against a number; a failed supply read
must be incapable of producing a BURN or un-FIREing LP MIGRATION. Signal math lives in
`analytics/surf_signals.py` as pure functions taking previous-baseline + current-values +
`now_ts`.

## 4. Widget mapping

Slot grid (title bar → hero row → middle row → bottom row). **No view-swap key: every
widget is on screen at once.** Width tiers advertise dropped columns with `‹ widen`, and
the title bar advertises rows lost off the bottom of the right rail with `‹ taller`:

| Slot | Widget | Content |
|---|---|---|
| title bar | — | `SURF · IMD $x.xx · parity ±x.x% · feed #N (age)` + `‹ taller` + degraded flags + version |
| hero row (full width) | `SurfHero` | experiment status in four boxes: v4 hook NOT LIVE / LAUNCHED; LP position (IMD/WETH sides, owner=frenpet.eth sanity flag); gate CLOSED/OPEN + written x/2000; supply + burns observed since this install began (never an all-time figure — no keyless source; renders "no burn observed yet" until the first one) |
| middle left | `SurfFeed` | announce feed: date · kind (`self` / `reply` / `action` / `fund`) · message. Full text at wide tiers, truncated + `‹ widen` below |
| middle right rail, top | `SurfSignals` | the six detectors, FIRED rows styled loud |
| middle right rail, below | `SurfDevActivity` | recent txs of both dev wallets: date · wallet · label (deploy / LP / burn / bridge / FWA claim / transfer / other) · counterparty |
| bottom left | `SurfMarket` | price, 24h Δ, volume, pool liquidity, FP↔IMD parity spread, price + supply sparklines (burn steps the supply down) |
| bottom right | `SurfNft` | holders, transfers/24h, identities written on one row; dev holdings on their own (`dev holds N identities`); last realized Seaport sales; floor = explicit `n/a — no keyless source`, muted |

Four amendments to this table were made after the dashboard was first built and run:

1. **The hero spans the full width and the signals moved into a right rail.** The original
   grid put `SurfHero` and `SurfSignals` side by side on the hero row, which left the four
   hero boxes sharing half a row — too narrow to render their widest tier on any real
   terminal — and stranded blank rows under the hero and above the status bar. The hero now
   owns its row, the announce feed takes the left of the middle row, and `SurfSignals`
   moved into a right rail — above `SurfMarket` at the time, which amendment 3 supersedes.
   Every row but the middle one is content-sized, so a
   taller terminal hands its extra rows to the feed instead of reserving them blank.
2. **The LP box no longer shows raw liquidity.** It used to render the position's v3 `L`
   beside the WETH side. `L` is a uint128 around 1e19, so it can only be shown as
   `2.16e+18` — K/M/B suffixes lie at that magnitude — and scientific notation of an
   unnamed unit told a reader nothing the WETH side does not, at the highest column cost on
   the row. `lp_liquidity` remains a manager key and still feeds the LP MIGRATION detector;
   it simply has no box. The tier that existed only to hold it was removed with it, rather
   than left as a tier that renders exactly what the next one renders.
3. **The `c` view swap is gone, and the market moved to the bottom row.** The original grid
   put `SurfFeed` and `SurfDevActivity` in one middle-left slot, where the `c` key
   alternated between them — half the dashboard's content was off screen at any moment and the
   shared status bar had to carry a `view:` word to say which half. The activity panel now
   sits under the signals in the right rail, permanently; `SurfMarket` moved down beside
   `SurfNft` on the bottom row, out of a scrolling rail it was shrinking to nothing inside.
   The key, its action, the status-bar indicator and their tests went with the slot they
   served. The cost is columns, not content: the activity panel gets ~`0.4 × terminal`
   instead of a `3fr` slot, so it selects a narrower row tier — and says which fields it
   shed, which is the sanctioned answer to a cramped panel here. That is what moved
   `SURF_FULL_LAYOUT_COLUMNS` from 135 to 176.
4. **`SurfNft`'s rows were regrouped and its floor line was muted.** The written count
   folded into the stats row (`667 holders · 38 transfers/24h · 1/2000 written`) and the dev
   holdings took a row of their own, phrased as the sentence they are: `dev holds 3
   identities`. (Figures as of the 2026-08-08 capture, matching §2 and
   `surf_game_mechanics.md` §IDMD; they are read live and will have moved. This amendment
   first quoted `666 holders · 7 transfers/24h` and `dev holds 4`, which matched neither.)
   The old arrangement put the one figure about a *person* at the end of a row of figures
   about the *collection*, and spent a whole row on a single fraction. **The
   floor line did not move and its claim is unchanged** — it is still the explicit
   `n/a — no keyless source`, still never faked and never blank; only its colour changed,
   from `[yellow]` to the `[dim]` the panel's own labels use. Warning vocabulary was wrong
   for it: there is no keyless floor source for this collection *at all*, so the line states
   a permanent condition rather than flagging something wrong right now, and a colour that
   shouts on a standing fact trains the eye to skip it. Muted is not hidden — it composites
   at 4.65:1 or better against the background in all ten themes, pinned per theme. A *real*
   floor, if a keyless source ever exists, still renders bold. The regrouping also forced
   the width ladder to be re-derived rather than re-pointed: the row now sheds
   `1/2000 written` first (the only one of its three figures that is also on screen in the
   hero's IDENTITY GATE box), then `transfers/24h`, with the holder count last standing.
   The panel's own clean width went 107 → 113; `SURF_FULL_LAYOUT_COLUMNS` did not move,
   because the market still binds at 143.

Counterparty rendering in `SurfDevActivity` (address-poisoning defense — live spoofs of
both fee recipients exist in frenpet.eth's history today): known addresses render as
labels from a vendored map (dev / ops / announce / NFPM / BurnExecutor / OFT endpoint /
Relay solver / Seaport / Kraken…); unknown addresses render dimmed as
`0x` + first 8 + `…` + last 6 and are never styled as trusted. Zero-value dust transfers
*to* the wallets from unknown senders are dropped from the feed entirely (that is the
poisoning vector).

All third-party strings — messages, token name/symbol (owner-mutable, renamed twice
already), ENS names, NFT metadata — pass through `widgets/markup_safety.safe_markup`.

## 5. Data layer

### Endpoints (all keyless, all validated in research)

| Pool | Endpoints | Used for |
|---|---|---|
| state RPC | `ethereum-rpc.publicnode.com` (batches; no archive getLogs) | eth_call getters, nonces |
| logs RPC | `gateway.tenderly.co/public/mainnet`, `eth.drpc.org` | recent-window getLogs (IMD mints, IdentityHashUpdated, Initialize, OrderFulfilled) |
| Blockscout REST | `eth.blockscout.com/api/v2` (GET) | channel bodies, dev-wallet tx pages, token counters/holders |
| market REST | GeckoTerminal + DexScreener | IMD + FP price/volume/liquidity (cross-check; GeckoTerminal serves stale token names — display the onchain name) |
| price | CoinGecko via existing `data/price.py` | ETH/USD |

Base RPC (`mainnet.base.org`) only for the FP-side parity price if DexScreener lacks it.
Blockscout v1 `eth_call` is broken (HTTP 400) — never use it; REST v2 GETs only.

### Addresses (vendored constants module `data/surf_addresses.py`)

The full cast table from `surf_game_mechanics.md` §Cast, including the known-label map
for `SurfDevActivity`. Topics vendored with their preimages and keccak-verified by a test
(`IdentityHashUpdated` = `0x57c85cf8…`, v4 `Initialize` = `0xdd466e67…`, ERC-20 `Transfer`).

### Refresh tiers

| Tier | Cadence | Contents |
|---|---|---|
| fast | every refresh | 3 nonces, positions(), identityAllowed(), totalSupply(), slot0 (one batched RPC round) |
| medium | 60–120 s | getLogs windows, GeckoTerminal/DexScreener, channel bodies on nonce change |
| slow | 5–10 min | Blockscout counters/holders, dev tx pages, reply enumeration |

### Manager data contract (frozen — the parallel-agent interface)

`SurfManager.fetch_and_compute()` returns a flat dict; widgets receive primitives only.

| Key group | Keys |
|---|---|
| meta | `as_of`, `degraded` (list[str] of source-group names), `eth_usd` |
| feed | `feed_nonce`, `feed_last_post_age_s`, `feed_items` (list[dict]: `ts, kind, from_addr, from_label, text, tx_hash`) |
| signals | per signal `sig_{post,lp,gate,deploy,bridge,burn}_state` (`"ok"/"watch"/"fired"/None`), `…_detail` (str), `…_age_s` (float\|None) |
| hero | `hook_status`, `lp_liquidity`, `lp_imd`, `lp_weth`, `lp_owner_ok`, `gate_open`, `identities_written`, `imd_supply`, `imd_burned_cum` |
| market | `imd_price_usd`, `imd_change_24h_pct`, `imd_vol_24h_usd`, `pool_liquidity_usd`, `fp_price_usd`, `parity_pct`, `supply_series`, `price_series` |
| nft | `nft_holders`, `nft_transfers_24h`, `nft_dev_holdings`, `nft_written`, `nft_last_sales` (list[dict]: `ts, token_id, eth`), `nft_floor` (always `None` in v1 — renders the explicit unavailable state) |
| activity | `dev_activity` (list[dict]: `ts, wallet_label, kind, counterparty, counterparty_known, value_eth, tx_hash`) |

Every numeric key is `float|int|None`; `None` renders as the widget's unavailable state,
never as 0.

## 6. Correctness rules

1. **Baselines advance only on successful reads** (§3). The false-BURN case
   (supply `None` → 0) gets a dedicated regression test.
2. **No hardcoded live values**: parity, bridged share (33.0%), pool composition, burn
   totals are computed each refresh. The repo has measured a documented "constant" drift
   three days running; same rule here.
3. **Token identity is mutable**: name/symbol read live, `safe_markup`-escaped, and the
   dashboard trusts the *address*, never the name. Indexer names (GeckoTerminal "VIBE")
   are display-only fallbacks, flagged stale.
4. **The channel is permissionless**: anyone can post replies, including spam/scams
   (a begging tx and a pasta-sauce reply already exist). Replies render distinctly from
   self-posts; links in replies are never highlighted as the dev's.
5. **Poisoning defense** per §4 — and the `dev_activity` builder must key on tx sender ==
   dev wallet, never on "appears in the wallet's transfer list".
6. **State vs logs RPC pools stay separate**; RPC errors classified on message text.

## 7. Time-sensitive context (true on 2026-08-08, will change)

- The v4 hook is **not deployed**; hero shows NOT LIVE. Design assumes the launch shape
  is: staging mints → LP decrease → Initialize with hooks≠0x0 → announce post. Any one
  alone fires its own signal; the dashboard needs no code change on launch day.
- Gate is closed with 1/2000 written; if "the agent" reopens it, GATE OPEN fires and the
  hero flips — also no code change.
- The channel has 21 txs; one Blockscout page. Pagination code must still handle growth.
- The dev's FWA play (20 splitter claims) is labeled FWA income in `dev_activity` — it is
  not IMD economics.

## 8. Testing

- Fixtures are committed slices of the real payloads fetched 2026-08-08: channel txs
  (incl. the non-UTF-8 `register()` calldata and markup-hostile message text with
  newlines/em-dashes), positions/slot0 hex, Blockscout pages incl. poisoning rows,
  GeckoTerminal/DexScreener/CoinGecko JSON.
- A transport that raises on use is injected everywhere; no test touches the network
  (structural assertion, house rule).
- `analytics/surf_signals.py`: table-driven tests per signal × (ok/watch/fired/outage);
  the two poisoned-baseline cases (false BURN, un-FIRE on outage) mutation-checked.
- UTF-8 decoder: valid, invalid (selector-prefixed), empty, markup-hostile inputs.
- Topic constants: recompute keccak in-test from preimages.
- Screen: composited-strip assertions at the pinned full-layout width and one narrow tier;
  that no key can hide a panel (there is no view swap); degraded-flag rendering; the
  `‹ taller` row marker, including on a title bar already carrying every warning it can.
- Game-select contiguity and `--game` choices tests extend via `GAMES` derivation
  (no hardcoded ids).

## 9. Registration checklist (the five agreeing surfaces)

`GAMES` in `screens/game_select.py` (key 7) · `_GAME_CYCLE` in `app.py` · `--game`
choices in `__main__.py` (default stays `fwa`) · CLAUDE.md dashboard table · README.
Plus: screen registered in `app.py`, cache file `~/.maxpane/surf_cache.json`, theme
registered if a dedicated one ships.

## 10. Theme

Reuse an existing theme by default (`--theme` already mixes freely). Optional dedicated
`surf` theme (deep-water blues, signal-orange FIRED accents) only if a work package has
slack; not on the critical path.

## 11. Success criteria

1. A new channel post is visible on the dashboard within one refresh interval of the tx
   landing, with decoded text.
2. Replaying the 2026-08-07 LP-add sequence against fixtures fires BRIDGE STAGE before
   the add and NEW POST after it, in order.
3. All six detectors degrade to explicit states under full network outage; no signal
   fires and no baseline moves.
4. `pytest` green including the new suite; no existing dashboard's tests affected except
   the auto-extending registration tests.
5. Full layout renders at the pinned column width; narrow tiers advertise `‹ widen`.

## 12. Open questions (not blockers)

- v2: `--wallet` personal-position overlay (own IMD/IDMD vs pool)?
- v2: Seaport realized-price *series* (floor proxy) vs the v1 last-sales list?
- If the hook launches NFT-holder-gated, does a seventh "GATE TRADE" signal earn a slot,
  or does LP MIGRATION's detail line carry it?
