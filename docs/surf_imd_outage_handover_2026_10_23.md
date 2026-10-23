# SURF during an imd.fun outage — handover for Codex (small round)

Owner request 2026-10-23, from a live render of the Codex build (`feature/surf-rpc-budget` at `f65236ea`). Read `CLAUDE.md`
and `.claude/rules/surf.md` / `data.md` first. Precedence: CLAUDE.md > this document > your own judgement. This document
says what is wrong and what must be true afterwards; how is yours.

## What happened (measured 2026-10-23, Claude)

- Since **05:45 UTC** the registrar holds `imd.fun` (`client hold`). Every name under it answers NXDOMAIN: `api.imd.fun`,
  `pool4.imd.fun`, `explorer.imd.fun`, `*.sites.imd.fun`. The plane itself is up at
  `https://identitymdcontrol-plane-production.up.railway.app` (same deployment, `/version` `3dc93dc1`).
- `SwarmClient`'s two-host pool (`SWARM_API_HOSTS`) worked as designed: version, health and workers read through the
  Railway host in under 0.5 s.
- **POOL4 MARKET renders as SEPOLIA.** `~/.maxpane/maxpane.log` repeats every cycle:
  `fetch_docs_page: https://pool4.imd.fun/docs failed: [Errno 8] nodename nor servname provided, or not known`.
  `~/.maxpane/surf_cache.json` `last_good.pool4.payload`: `network SEPOLIA`, `discovery_state not-discovered`,
  `discovery_detail "no hook-shaped address in 6 self-post addresses"`, `discovery_source_tx None`, `discovery_source None`,
  `hook_addr 0xa1B9…6840` (the vendored Sepolia hook). The mainnet adoption had come from the docs page; the hook's
  self-post has left the 25-row channel window, and no source transaction was remembered for a docs adoption.
- **The STAKERS table is mainnet under a SEPOLIA heading.** `last_good.pool4_stakers.payload.network` is `MAINNET`
  (554 addresses), while the section reads "STAKERS · SEPOLIA" with the rest of the screen.
- **`maxpane_dashboard/data/surf_nft_rules/catalog.py:10`** declares `API = "https://api.imd.fun"`, outside the pool, so
  its reads fail for the whole outage.

## What must be true afterwards

1. **POOL4 stays on mainnet through an imd.fun outage.** With every `imd.fun` name failing to resolve and the plane
   reachable at its Railway host, the market card adopts the mainnet hook. The adoption still has to be proven from an
   authoritative source in the cycle it is used (A27, S15: a cache says where to look, it is never believed); choose the
   source, and state in the report why it meets the same gates as the channel and the docs page.
2. **A fallback is never silent.** When no source adopts, the screen says so and why (for example "mainnet hook not
   proven: docs unreachable"), instead of presenting the vendored Sepolia deployment as the market.
3. **Every section's network label comes from the data it shows.** No screen shows mainnet rows under a Sepolia label,
   or the reverse.
4. **Every dashboard read of the plane goes through `SWARM_API_HOSTS`**, `surf_nft_rules/catalog.py` included. A grep
   for `api.imd.fun` under `maxpane_dashboard/` finds only the pool's declaration and display strings.
5. **Tests cover the outage offline:** a transport on which every `imd.fun` name fails as a resolution error, and the
   Railway host answers from fixtures, for points 1 to 4. No test touches the network (CLAUDE.md rule 3).

## Constraints

- Branch `feature/surf-rpc-budget`, on top of the current head; one writer; explicit paths per commit; this document in
  the first commit. No push, merge, tag or version bump. Use `.venv311` and `env -u NO_COLOR HOME=$(mktemp -d)`.
- Keyless and read-only as before; no new service, provider or key; no layout change beyond labels and the fallback note.
- Do not touch untracked files you did not create.
- Out of scope, recorded only: PEPEPANE's broker reads `https://api.imd.fun/seats/{seat}/standing` without the pool
  (`imd_dashd/imd_dashd.py:54`, branch `pepepane`); that is a separate branch and deployment.

## Deliverable

- Commits with their tests, each naming the mutant its test kills.
- `docs/surf_imd_outage_report_2026_10_23.md`: what changed per point 1 to 5, the adoption source chosen and why, test
  counts before and after, every deviation with its reason, anything not reached.

## Not included (each needs the owner's yes)

- A live render check against the real hosts while the outage lasts: 1 agent × 1 run (Claude), plus the owner's look.
- Claude's verification of the round: 1 agent × 1 run plus the full suite once (~17 min).
