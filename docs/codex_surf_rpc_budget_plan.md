# Codex brief: SURFBOARD and BOARDROOM RPC budget (written 2026-10-22, revised after two reviews)

> **Do not use any superpowers skill.** This brief and the repository's `CLAUDE.md` are the whole process. Where they
> differ, this brief records the owner's decision for this work and names the `CLAUDE.md` step it changes.

## Base and branch

- **Repository:** `/Users/banse/codex/maxpane`.
- **Base:** `feature/surfboard-hub-9` at `adfe652e`.
- **Branch:** new branch `feature/surf-rpc-budget` from that base.
- Never merge, push or tag.
- autopull `main` (`8cef1ab6`) is a separate line with ~610 changed lines in `surf_manager`, `surf_client` and
  `surf_cache`; merging is the owner's later step.

## Scope (owner, 2026-10-22)

**In scope:** only SURFBOARD and BOARDROOM: the surf, pool4, launchpad, launch (Ethereum, Base, Robinhood) and surf NFT
clients and managers, and the BOARDROOM hub cards.

**Parked, not to be touched:**
- TTT, FWA, THE LIST (curator), talismans, cattown, OCM and `curator_nft_holders`;
- any per-chain RPC override;
- changing pool4's accumulator rule after a gap over 24 h (S17 in `docs/surf_pool4_followups.md`: "continuity enforced by
  discarding" stays as it is).

**Shared modules** (`rpc_common.py`, `rpc_classify.py`): may change only so that the parked dashboards behave exactly as
today. Their tests must pass unchanged.

## Process

- Two rounds. Round 1 is the items marked R1; stop after it and report. Round 2 (R2) starts only on the owner's go after
  Claude has verified round 1.
- This counts as a Tier 2 change. This work keeps a short spec and plan per round in `docs/` and waives the per-package
  task reviews and the final whole-branch review: Claude verifies each round independently instead. (Claude's default; the
  owner may veto.)
- "Design in chat" is replaced by this brief.
- Decide, do not ask: record each decision and its reason in the round report. The owner may veto later.
- **Tests:** offline only, with recorded answers; no test may reach the network. Each item gets its own tests and a named
  mutant they kill.
- **Before each commit:** run the set `CLAUDE.md` names: the touched test files and the composing screen or manager file
  whole, via `HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <files>`, plus the fast guard set
  `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`. Add `mounts_app` only when a binding, key or
  registration surface changes.
- **Full suite:** not run by you. Claude runs it as controller in `.venv` (Textual 8.2.8, Python 3.13) and `.venv311`
  (Textual 8.1.1, Python 3.11).
- **Old caches:** caches written by today's code (for example `tests/fixtures/cache/*_53a71d5.json`) must still load. No
  new version keys (the rule in `.claude/rules/data.md`).

## Endpoint facts

You cannot reach the network, so these are recorded for you. They were measured 2026-10-22 from the owner's machine:
- one call per case, in `docs/codex_surf_rpc_budget_captures-2026-10-22.json` (exact status codes and bodies; the one
  wallet in it is a synthetic placeholder);
- earlier probes the same day.

Use the captures as fixtures; do not re-capture.

| Endpoint (as the code uses it) | Serves | Refuses (exact wording in the captures) |
|---|---|---|
| `https://rpc.mevblocker.io` (same with `/fast`) | old logs; old state (`eth_getTransactionCount` at block 25,769,870); a single old block; batches of 5; a wallet-filtered `eth_getLogs` over 1.16M blocks with few logs | "Log response size exceeded. You can make eth_getLogs requests with up to a 10,000 block range and no limit on the response size, or you can request any block range with a cap of 10K logs in the response" (-32602, HTTP 200). 429 / Cloudflare 1015 under bursts. |
| `https://gateway.tenderly.co/public/mainnet` | old logs, old state, 403,200-block windows | 429 under bursts; about 32 back-to-back calls before -32005 (`surf_pool4_client.py` 320-323). |
| `https://ethereum-rpc.publicnode.com` | recent logs (10,000 blocks), a single block at head − 50,400, batches of 5 | HTTP 403 `{"code":-32602,"message":"Archive requests require a personal token…"}` for logs or state more than ~10,000 blocks behind head. Once in 10 parallel calls even for a recent 600-block range. |
| `https://1.rpc.thirdweb.com` | old state, batches of 5, logs up to 1,000 blocks | -32005 "Log response size exceeded. Maximum allowed number of requested blocks is 1000". |
| `https://eth.drpc.org` | recent ranges, old state | HTTP 400 code 35 "ranges over 10000 blocks are not supported on free plan", **also for a 2,000-block old range** (the message is misleading). HTTP 500 "Batch of more than 3 requests are not allowed". |
| `https://eth-pokt.nodies.app` | old state, batches | -32001 "Block range too large: maximum allowed is 50 blocks". |
| `https://base-rpc.publicnode.com` | recent logs | -32602 "query exceeds max results 20000" on a busy 5,000-block range; HTTP 403 archive beyond its line. |
| `https://mainnet.base.org` | — | 429 -32011 "request limit reached" on 3 of 3 calls. |
| `https://base.llamarpc.com` | — | HTTP 525 (down). |
| `https://base.drpc.org` | recent ranges | the same misleading code-35 refusal for old ranges. |

An empty answer from one endpoint proves nothing (`.claude/rules/data.md:126` records flashbots returning 46 of 1,132 logs).

## Definitions for the budget

- A **request** is one HTTP POST to an RPC host; retries count.
- An **entry** is one JSON-RPC call inside a request; a single call is 1 entry.
- REST GETs (Blockscout, DexScreener, Gecko, CoinGecko) are counted separately.
- The budget table counts these offline with a fake RPC that applies the caps above. Its scenarios:
  - steady state at the default 30 s poll, per view, BOARDROOM included;
  - a cold start;
  - a catch-up after 1 day and after 1 week of downtime, with today's surf log density from the fixtures.

Produce the table by one committed command, before and after each round.

**Global outcome:** on a fixture whose reads are complete, every in-scope manager's flat dict is identical before and after.
Only keys an item names may differ. No row of the table gets worse.

## Round 1

**R1-a · BOARDROOM's POOL4 card.**
- `surf_card_reader.py:33-43` runs `_pool` (165-203) every 30 s, about 57 entries a run and about 114 a minute, for share
  price and tick.
- `_feed` and `_market` (154-163) pass the medium tier unconditionally, so the REST sources are hit every 30 s, the
  regression `surf_manager.py` 1449-1469 says was fixed once.

**Outcome:**
- With only BOARDROOM visible, the POOL4 card costs at most 10 entries a minute in steady state.
- Each REST source is called no more often than its tier TTL.
- The card shows the same values as today on the fixture.

**R1-b · STAKERS stays complete.**
- The stakers fold re-reads 403,200 blocks every 1,800 s (`surf_manager.py` 5283-5345).
- The vault's first sIMD Transfer is block 25,887,017, so at head ≈ 26,290,216 (about 2026-10-28) the window no longer
  reaches it and the fold reports `complete=False` forever.

**Outcome:**
- STAKERS is complete over the vault's whole life at any head, with the same holders and balances as a full fold on the
  fixture.
- After the first full read, the steady state costs at most 1 log request per tier tick.

**R1-c · No surf history skipped or counted complete without being read.**
- The launchpad cursor moves to head after any successful set of pages (`surf_client.py` 2379-2383). An empty page from a
  fallback counts as data (3353-3363). The coinCount vs launch_count mismatch is only logged (2007-2028).
- The decoy-pool count (2486-2513) reads 25,000,000 → head every 600 s through `_get_logs_shrinking`, whose docstring
  (3260-3272) says it is wrong for history. A partial count can be returned as complete: tenderly fails, mevblocker
  range-errors, the window halves, then tenderly answers only the newest half.

**Outcome:**
- No cursor or count moves past blocks that were not read.
- An empty log answer is confirmed by a second endpoint before a cursor or count advances past it, and only then.
- A launchpad count that disagrees with `coinCount()` is never shown as complete, and it heals without a restart.
- The decoy count equals a full read on the fixture.

**R1-d · Sweeps resume instead of restarting.**
- The launchpad cold sweep (`_get_logs_paged`, `surf_client.py` 3304-3365, from 25,786,048 in 2,400-block pages) discards
  everything on one failed page.
- pool4 `_fetch_logs` (`surf_pool4_client.py` 1674-1722) restarts at half width, up to 4 times, on a
  `Pool4LogRangeError` from a later page.

**Outcome:**
- After a failure, the next attempt starts at the first unread page.
- Kept progress is never reported as complete.
- One endpoint's cap never narrows another endpoint's pages.
- A cap that changes (as mevblocker's did) costs no code change and loses no page.
- A cold start and a 1-week catch-up each cost no more requests than today.

**R1-e · pool4 state reads.**
- pool4 sends JSON-RPC arrays: hook 34 entries, dripper 12, distributor 11, vault 2 then 9, plus 2 per vault hop, slot0 2,
  reference 5. The call lists are at 1026-1044, 1178-1184, 1249-1262 and 1294-1303; the plumbing is at 506-664.
- An entry that errors inside an HTTP 200 array becomes `None` with no retry elsewhere (`surf_pool4_client.py` 506-572;
  same in `surf_client.py` 1468-1515).
- `_rpc_state_batch` never chunks; `fetch_seat_rewards` (3157-3181) can send ~500 entries.

**Outcome:**
- Each tier read of known addresses comes from one block, in at most 2 requests per chain. The vault walk on a cold start
  may take more.
- No request exceeds the receiving host's batch cap (drpc 3).
- A failed entry is retried on another endpoint before it becomes `None`.
- The one-block guarantee of `surf_pool4_client.py` 1379-1391 holds.

## Round 2 (after round 1 is verified and the owner says go)

**R2-a · Steady-state windows.** These re-read their whole window on every tick:
- `fetch_recent_logs` (`surf_client.py` 3367-3466): 2,400 blocks every 90 s. Its Seaport `OrderFulfilled` filter pulls every
  OpenSea fill and keeps the IDMD ones.
- The launchpad CurveSwap day: 7,200 blocks every 600 s.
- The pool4 hook, swap and drip logs: 3 + 3 + 8 pages every 600 s (`surf_manager.py` 358, 366).

**Outcome:**
- The per-tick cost grows with new blocks only.
- A reorg of up to 12 blocks is never lost or counted twice.
- Sales are the same set as today on the fixture.

**R2-b · Rate limits for the surf clients.**
- After a 429 the next call starts at the same host again, and `Retry-After` is ignored.
- `pace()` (`rpc_common.py` 124-143) holds no lock, so `gather` bursts (`surf_manager.py` 1406, 2431, 3345, 3363, 3513)
  leave together.
- Each client paces on its own clock.
- `SurfNftClient._request` (`surf_nft_client.py` 197-245) already does this well.

**Outcome:**
- No host gets surf requests faster than its configured interval, across all surf clients.
- After a 429, a host gets none until its `Retry-After` (or a set pause) has passed, while reads continue elsewhere.

**R2-c · Surf endpoint pools.**
- Remove endpoints that cannot serve what they are asked, per the table: `eth.llamarpc.com`; `base.llamarpc.com` where surf
  uses it; drpc and nodies in any pool that reads old logs.
- Every surf pool that reads history keeps at least two endpoints able to serve it. The launch clients for Base and
  Robinhood are included.
- publicnode never serves surf log reads older than ~10,000 blocks.

**R2-d · Duplicate and static reads.**
- `eth_blockNumber` is read at `surf_client.py` 1609, 2169, 2502 and 3388, `surf_pool4_client.py` 654 (every getter round)
  and 672, and `surf_nft_chain.py:117`. That is twice per launchpad tick (2169, 2502).
- The 30 s bundle re-reads name and symbol (`fetch_chain_state` 1673ff).
- `imdEthPoolId()` (1795-1830) is re-read.
- 105 known pool4 getter reverts are asked again (`~/.maxpane/maxpane.log` since 10-21).
- IMD decimals are re-read (:3189).
- The NFT hub re-proves proven collections every 120 s (`surf_nft_manager.py` 29, 245).
- The NFT inspector sends one request per read (`surf_nft_chain.py` 84-240).

**Outcome:**
- Each chain's head is read at most once per tick, and no log window claims blocks the answering node may not have yet.
- Values that never change, and getters known to revert, are not re-read.

## Keep

These are deliberate and must survive:

- only the visible view polls;
- separate state and log pools;
- publicnode is kept out of surf mainnet log pools;
- error classification on message text, with range complaints the request already meets rotating instead of shrinking
  (`rpc_classify.py`);
- `_get_logs_paged` fails rather than skipping blocks;
- Multicall3 with the block number inside where it is used today;
- the pool4 page budget, checked against the contract's own counters (its 50,400-block stakers pages need an endpoint that
  serves them; only tenderly does by block range);
- memoized immutables;
- tier TTLs with failure backoff.

## Deliverable and report (per round)

- **Commits:** on `feature/surf-rpc-budget`, one item or a tight group per commit, each with its tests and named mutant in
  the body.
- **Round report:** `docs/codex_surf_rpc_budget_r<n>_report.md`, containing:
  - the budget table before and after;
  - the before-commit test counts;
  - every decision and deviation, with its reason;
  - every outcome not reached, and why.
- **Docs updated in the same round:**
  - `.claude/rules/data.md` (surf endpoints and caps);
  - `decisions.md` for each reversed or new design;
  - CHANGELOG;
  - `ENDPOINTS_VERIFIED_ON` / `_ENDPOINT_PROBE` with their docpin tests.

## Not included (each needs the owner's yes; cost per round)

- **Live request-count run** against the real free RPCs (`docs/dashboard_data_lifecycle_spec.md` asks for one before
  review): 1 agent × 1 run plus machine time. It can rate-limit the owner's IP for a while.
- **Adversarial review of the diff:** 1 agent × 1 run, plus at most 1 scoped re-review (`CLAUDE.md`: one reviewer per diff).
- **Codex fix rounds** if verification finds defects: 1 Codex run each, plus Claude's re-verification (1 agent).
- **Claude's verification of each round:** 1 agent × 1 run plus the full suite twice (~2 × 17 min). This is the proposed
  replacement for the waived Tier 2 reviews.
- **The owner's look at a live render** where a screen's paint changes.
