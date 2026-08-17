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

---

## The required set (what WP0's guard asserts)

These **18** files — the 17 above plus this README — are the *required set*.
`tests/data/test_curator_captures.py::REQUIRED_CAPTURES` names every one of
them, and the guard is a **named set, never a count**: `captures/live/` belongs
to WP1 and grows at unpredictable moments, so a count-based assertion would go
red for a *successful* capture and teach the next agent to delete evidence.

| directory | owner |
|---|---|
| `tests/fixtures/curator/captures/` (these 18 files) | WP0 |
| `tests/fixtures/curator/captures/live/` | **WP1** — timed bundles, may be empty |
| `tests/fixtures/curator/client/`, `.../signals/`, `.../screen/` … | the consuming work package |

The fixture root holds **directories only** apart from its own markdown; a loose
`*.json` there is a file with no owner and is how one WP's slice lands in
another WP's glob. `test_the_fixtures_root_holds_directories_only` enforces it.

**Every number this directory's prose quotes is pinned in
`tests/data/test_curator_captures.py`.** Three of the pins came out *disagreeing*
with the prose and the chain won:

* **`Deposited` count is 231, not 226.** The table above and the implementation
  plan both say 226. Recounted from the committed bytes: 1 `Launched` + 231
  `Deposited` + 145 `FirstDeposit` = 377. A fold calibrated to 226 would silently
  drop five real deposits.
* **The logs *do* carry block timestamps.** All 377 RPC rows have
  `blockTimestamp` and all 376 Blockscout items have `block_timestamp`, which
  refutes hazard H14 / amendment A4 as written. The `eth_getBlockByNumber` batch
  is a *fallback* for endpoints that omit the field, not the only source; the
  `--:--` rule for a missing stamp still stands.
* **The announce channel did touch the curator.** Its transaction page contains
  exactly one curator item — a `deposit` call of 0.05 ETH, which is the first
  deposit of the game and the witness for the weight formula. It never *posted*
  about it. A blunt "the address is not mentioned" pin is false.

Two shapes to know before slicing: `tenderly_logs.json` is the whole JSON-RPC
envelope (rows are under `result`), and `batch.json`/`results.json` correlate by
`id`, never by list position — two of the 21 views both answered `0x0`.
