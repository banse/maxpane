# Surf AGENT hero: REWARDS card (F-S5) — spec and plan

Owner request 2026-10-02 (`docs/surf_seat_resilience_followups.md` F-S5). Tier 2: new contract keys
and a new data read. Shipped on `feature/surf-agent-hero-rewards` together with F-S4 (STATUS
`● working`) and F-S6 (ACCEPTED JOBS before WORK), which are Tier 1 and land first as their own commit.

## What the reader sees

The hero's fourth box (today REVIEWED) becomes **REWARDS**:

```
REWARDS
13.87 IMD          line 1: IMD this seat received
                   line 2: blank
$105.84            line 3: that IMD at the current imd_price_usd
```

The REVIEWED counts leave the hero; the pending count is still in FEEDBACK (`1,711 queued`).

| state | box shows |
|---|---|
| seat read not `ok` (pending / busy / unknown / failed) | the seat state line, like ACCEPTED JOBS (`seat_state_line`) |
| rewards not read yet for this seat | `Loading…` |
| rewards read failed and no last-good for this seat | `unavailable` |
| read ok, nothing received | `0.00 IMD` / `$0.00`: a real zero |
| read ok, price unavailable | line 3 `unavailable`, line 1 unchanged |

## What counts as a reward (owner decisions, 2026-10-02)

1. **A reward is IMD paid to the seat's current owner wallet by a known payer.** Verified on chain
   for seat 420 (`pawai.eth`, `0xe5b1…4f2a`): IMD `0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7`
   (contract name `BridgedFP`, which is why wallets label it "FP") reaches the owner in a
   `disperseToken` call. The transaction is sent by **surfsurf.eth** (`DEV_WALLET`,
   `0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7`) to Disperse
   `0xd15fE25eD0Dba12fE05e7029C88b10C25e8880E3`, and the Transfer log's `from` is Disperse.
   Three payments: 7.6923 (09-23), 3.0521 (09-25) and 3.1218 (09-28) = 13.8662 IMD.
   Disperse is a public contract, so the **transaction sender** decides, not the log.
2. **Since `pairedAt`**: only transfers whose block time is at or after the seat's `pairedAt`
   (from `/seats`). Earlier transfers belong to a previous owner or another era.
3. **Split evenly per seat**: the wallet's reward total divided by the number of IDMD seats the
   wallet holds now (`balanceOf(owner)` on the seat's collection). pawai.eth holds 1 seat, so 420
   shows the full amount.
4. **USD at today's price**: `imd * imd_price_usd`, recomputed every cycle.

The payer rules live in two constants, so a future payer (pool4, other contracts) is a one-line change:
`REWARD_DISPERSE_CONTRACTS = (DISPERSE,)` with `REWARD_DISPERSERS = (DEV_WALLET,)`: a
transfer **from** a disperse contract counts when its transaction **sender** is a disperser.
`REWARD_DIRECT_PAYERS = ()`: a transfer **from** one of these counts as it is. Empty today.

## Data read (keyless)

`SurfClient.fetch_seat_rewards(owner, since_ts) -> SeatRewards | None` (the manager checks `collection`)

1. Blockscout `GET /addresses/{owner}/token-transfers?type=ERC-20&filter=to&token={IMD}`, newest
   first, following `next_page_params`, stopping at the first row older than `since_ts`. Bound:
   10 pages. **Hitting the bound with a cursor left is a failed read (`None`)**: a partial sum
   understates the reward, and an understated number must never look like a total.
2. Keep rows whose `from` is a direct payer, or a disperse contract (pending the sender check).
   A row with no parseable timestamp, value or hash fails the read; it is never dropped silently.
3. `fetch_tx_senders` (an existing batched `eth_getTransactionByHash`) for the disperse rows.
   A sender we could not read **fails the read**: "unknown sender" must never become "not a reward".
4. One state batch: IMD `decimals()` (a live read, never 18 by assumption) and
   `balanceOf(owner)` on `IDMD_NFT` (`surf_addresses`). The seat's `/seats` `collection` must equal
   `IDMD_NFT` on `chainId == 1`; anything else gives `None` (a seat of another collection is not
   counted against this one). `seats_held == 0` gives `None` (the wallet no
   longer holds the NFT `/seats` says it does).
5. Return `SeatRewards(raw_total, decimals, seats_held, transfers)`: the integer sum, no float.

## Manager and cache

* A per-seat clock, not a new tier (as built): `SWARM_SEAT_REWARDS_TTL_S = 600` per seat,
  `SWARM_SEAT_REWARDS_BACKOFF_S = 120` after a failure, both in `surf_manager`. A global tier
  clock would make a switch to another seat wait out the first seat's TTL; the per-point
  `read_ts` does not, and no `TIERS` entry is added.
* New slot `SLOT_SWARM_SEAT_REWARDS`: per seat `{token: {owner, paired_ts, raw, decimals, seats,
  transfers, read_ts}}`, capped at 6 seats like the seat slot. An entry whose owner or `paired_ts` differ
  from the current seat read is ignored (a sold seat does not inherit the old total).
  Each persisted point is validated (raw ≥ 0 int, 0 ≤ decimals ≤ 36, seats ≥ 1).
* Started from `_pool_swarm_seat` after an `ok` seat read (it needs owner, `pairedAt` and
  collection), inside the existing detached seat task. Never awaited by the cycle.
* Keys (SURF_KEYS 198 → 200):
  * `swarm_seat_rewards`: `{"imd": float, "usd": float | None, "seats": int}` or `None`.
  * `swarm_seat_rewards_state`: `"ok"`, `"pending"` (no read finished for this seat) or `None`
    (read failed, no last-good). Separate from the value so "not read yet" and "could not read"
    stay distinguishable.
* `SurfSwarmAgentHero`'s signature gains both keys.

## Widget

* Box key `reviewed` becomes `rewards`, id `surf-swarm-agent-rewards`, title `REWARDS`, same
  19fr column (CSS in both places). REVIEWED's body and its tests go.
* Line 1 `13.87 IMD` (two decimals; `fmt_compact` from 100,000 up, e.g. `1.2M IMD`), line 2 blank,
  line 3 `$105.84` (`$` with two decimals; compact from 100,000 up). Bold amount, dim unit.
* The AGENT pin (139 × 25) is re-swept with a worst-case rewards payload added to the sweep's
  payloads. The value is shortened, never the pin raised.

## Work packages (run in order by the session; each gets one reviewer)

1. **WP1 data**: constants, `SeatRewards`, `fetch_seat_rewards` with fixtures under
   `tests/fixtures/surf/` (committed Blockscout page for 420, a bound-hit page, an unreadable
   sender); manager tier, slot, coercion and keys; SURF_KEYS count test.
   Tests: `tests/data/test_surf_client*.py`, `test_surf_manager*.py`, `test_surf_swarm_models.py`.
2. **WP2 widget**: REWARDS box, CSS, README/CHANGELOG, sweep payload.
   Tests: hero widget, AGENT screen, AGENT layout sweep, widget contract, `-m guard`.
3. Final whole-branch review on the most capable model, one fix wave, scoped re-review, full
   suite once by the controller. No merge, push or tag: those are the owner's.

## Review fix round (2026-10-02)

* I1: `coerce_rewards_slot` bounds `raw` at `500 * 2**256` (the client's page bound of uint256
  rows); a hand-edited larger value used to overflow the division and blank the whole cycle.
* I2: a row whose `token.address_hash` is not IMD (or carries none) fails the read; the
  `token=` query filter is the server's promise, not ours.
* I3 (convention over spec): REWARDS has no `as of` line, so a point older than
  `SWARM_SEAT_REWARDS_MAX_AGE_S = 3600` is treated as unread (`Loading…`, or `unavailable` after
  a failure), never shown as live.
* M2: a disperse contract listed as a direct payer still takes the sender check.
* Filed, not fixed: M4 (the failure mark is per token, so a seat sold within 120 s of a failed
  read shows `unavailable` rather than `Loading…` until the backoff lapses) and M5
  (`fetch_tx_senders` sends every disperse hash in one batch; a public RPC capping batch size
  fails the read explicitly, as `None`).
