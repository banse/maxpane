# SWARM production launches: state and follow-ups (2026-10-07)

## Where it stands

**Shipped:** both rounds are on `main` and pushed. Nothing is tagged; the version is still v0.9.3.
- **Round 1 (`c9352030..33563899`)** covers:
  - production launches pinned and highlighted, with ticker, token-first address, site and legitimacy verdict
    (K1 to K4, K6, K7);
  - the `SWARM LAUNCH` detector and title segment;
  - site links on `sites.imd.fun`;
  - chain words BASE and RH.
- **Round 2 (`22af296b..f750b909`)** covers:
  - SITES `site` column and a blank row above the status bar;
  - popup check descriptions;
  - LATEST LAUNCHES in place of THROUGHPUT (parked), with `x` opening the newest launch's popup;
  - the K8 Uniswap v4 liquidity check (popup plus LAUNCHES `liq` column);
  - the pool fee taken from the `Initialize` event.

**Process:** Codex built every round in `/Users/banse/codex/maxpane`. Claude Code (the aidude session) verified each
round independently, with live-data oracles, mutants and width sweeps. Briefs, in order:
- `codex_swarm_launches_plan.md`, then `fix1`–`fix4`;
- `codex_swarm_launches_v2_plan.md`, then `v2_fix1`, `v2_fix2`.

**Final verification (`f750b909`):**
- tests: 2,962 passed;
- the `liq` column stays visible at every width from 91 to 220 columns, on Textual 8.1.1 and 8.2.8;
- live K8 equals an independent PoolManager probe on 34 of 34 pools;
- verdicts: 43 live launches `✓ swarm`, 8 parked launches `✗ K4`.

**Fixtures:** `tests/fixtures/surf/swarm/v8/` (round 1) and `v9/` (round 2). Every live shape the tests rely on is
there, with a MANIFEST.

**Measured background:** aidude keeps the measurements behind this feature, read it before changing the launch
checks:
- `docs/launch-legitimacy-check.md`, the manual checklist; B7 is the liquidity method;
- `docs/imd-api-changelog.md` §3, from 2026-10-05 on;
- `tools/surf/_launch_watch.py`, the macOS launch monitor.

## Facts that were wrong once, so do not reintroduce them

- **`manifest.pool.fee` is not the pool fee.** The `Initialize` event's fee is: 12500 (1.25 %) on custom_token and
  evm_project pools, 3000 on univ4_hook pools.
- **Only `univ4_hook` launches attest their hook.** custom_token and evm_project launches use the shared, never-attested
  `PoolInitializationGuard`. K3 requires the token always, and the hook only for univ4_hook.
- **`/launch/policies` declares a `factory` only on `evm_contracts`.** Hook launches deploy through a second factory,
  `0x12c63b58…`. K2 judges factories per launch kind, and on sender plus receipt otherwise.
- **Liquidity is never "burned"** for swarm launches. Every position is held by an unverified swarm factory
  (`0xff03…`, `0x12c63b58…` on Ethereum; `0x9c9d2fcb…`, `0xa25b02a1…` on Robinhood), with position liquidity equal to
  the deployed L0. The honest word is "locked in factory (unverified)".
- **`createdAt` does not follow `launchNumber`.** Never use a number high-water mark for "new".
- **`imd.fun/launches/<n>/` is a 404,** and `*.site.identitymd.eth.limo` fails TLS. Use
  `explorer.imd.fun/token/<addr>` and `<label>.sites.imd.fun`.

## Open follow-ups (none blocking)

- **`evidence_calls` 64 cap.** `analytics/surf_launch_checks.evidence_calls` caps a batch at 64 artifact addresses.
  The manager is unaffected, because it batches per cycle, but a pure call over all mainnet launches (more than 64
  addresses since 2026-10-06) truncates. Revisit if a caller ever batches everything at once.
- **LATEST LAUNCHES title** at 28 cells or fewer clips the time to `· as of 1…`. Cosmetic.
- **`liq` and `site` at 116–155 columns:** LAUNCHES shows `liq` but not `site` (SITES lists every site). This is
  the controller's decision, which the owner approved in the 150×46 preview. Revisit if `site` matters more there.
- **Copycat detection** (same symbol, other address) was dropped from MaxPane by the owner on 2026-10-06. The manual
  checklist C1 still describes it.
- **Self-deployed swarm-built tokens** (ADAM-style: swarm-built code deployed from the requester's own wallet) are not
  covered in MaxPane. aidude's `launch-watch` detects them; the checklist covers them by hand.
- **The K8 cadence** (300 s, 10 launches per cycle, oldest first) stays inside one cycle up to about 50 pools. More
  than 34 live pools exist today, growing several a day. Watch the first-read latency as the count grows.
