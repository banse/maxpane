# WhitelistCurator raw captures — 2026-08-16

Real payloads captured during the research session for the `curator` dashboard (THE LIST),
all between 21:04 and 21:14 UTC on 2026-08-16, when the contract was ~75 minutes old
(hour 1 of the game, 145 contributors, grace period). Source of truth for building the
curated fixtures under `tests/fixtures/curator/` — tests should consume derived fixtures,
not these bulk files, but every derived fixture must trace back to one of these.

| file | what | source |
|---|---|---|
| `source.sol` | full verified source, solc 0.8.28 | `eth.blockscout.com/api/v2/smart-contracts/0xcb0b0531…` |
| `contract.json` / `wc_abi.json` | the smart-contracts API response incl. ABI (two agents' saves of the same endpoint) | same |
| `creation_tx.json` | creation tx `0x240bf1a8…`, block 25769870, 2026-08-16 19:58:47 UTC | Blockscout `/transactions/…` |
| `tenderly_logs.json` | single-sweep `eth_getLogs` from deploy block, 226 `Deposited` + others (377 logs) | `gateway.tenderly.co/public/mainnet` (keyless) |
| `bs_page_0..7.json` | the same history via Blockscout `/addresses/…/logs` pagination (376 logs; reconciled with the sweep — the 1 extra tenderly log landed between pulls) | Blockscout |
| `ann_page_0.json` | announce channel `0x200E710a…` transactions page (no curator mention as of capture) | Blockscout |
| `batch.json` / `results.json` | batched `eth_call` round of all 21 parameterless views + decoded results | `ethereum-rpc.publicnode.com` |
| `hour_boundary_h1_h2.json` | the same batch re-sent every ~20 s across the hour 1 → hour 2 boundary (2026-08-16 21:56:15 → 22:01:21 UTC, 16 samples), with a `views` table mapping each request id to its selector and Solidity signature | same |

**The hour-boundary capture is the hazard in its real form.** `currentHourTotal()` falls
**9987.26 → 51.48 ETH** across 21:58:47 UTC while `stats()` keeps climbing (516 → 524
contributors, 10839 → 10891 ETH) — a sparkline fed from the state poll reads that as a 99.5%
crash. Feed history from `Deposited` logs only.

What this capture does **not** contain: the game was busy enough that a deposit landed within
11 s of the boundary, so `lastActiveHour()` had already rolled to hour 2 in the first
post-boundary sample. The distinct `lastActiveHour() < currentHour()` state — a boundary with
no deposit yet, which post-grace is also the at-risk state — still has to be recorded when a
quiet hour happens.

Two view shapes worth pinning before the models are frozen: `lastActiveHour()` returns
**(hour, total)** and `firstHourOf(address)` returns **(hour, hasJoined)** — both two-word
returns, not scalars.

Hazard notes that came out of capturing these: publicnode returned HTTP 403 to a
python-urllib default User-Agent but accepted the same batch via curl — set a real UA in the
client; `eth.drpc.org` failed once with routing-message text ("Can't route your request…") —
classify by message text and fail over to tenderly.
