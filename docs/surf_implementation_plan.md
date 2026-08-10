# SURF Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Each work package is a separate file under
> `docs/surf_work_packages/`; this document is the index, dependency graph and global contract.

**Goal:** Ship `--game surf`, MaxPane dashboard #10 — a keyless, read-only "mission control"
for surfsurf.eth's onchain experiments whose six detectors tell you a new experiment is
happening while it happens.

**Architecture:** House data flow — `surf_client` (keyless fetch, injectable transport) →
`surf_cache` (tiered TTL + persisted baselines/series) → `surf_manager` (`fetch_and_compute()`
→ one flat dict, exactly `SURF_KEYS`) → `SurfScreen` (slot grid, width tiers, no view
swap — every widget is visible at once) →
`widgets/surf/*` (render primitives only). All signal math lives in `analytics/surf_signals.py`
as pure functions.

**Tech Stack:** Python 3.11, Textual, httpx (async, injectable transport), pytest. No web3
dependency — `eth_call` payloads are hand-encoded with vendored selectors, as in
`data/frenpet_client.py`. No new third-party dependencies.

**Spec:** [`surf_PRD.md`](surf_PRD.md) · **Research:** [`surf_game_mechanics.md`](surf_game_mechanics.md)

---

## Global Constraints

Every task's requirements implicitly include these. They are house rules from `CLAUDE.md` plus
the spec's project-wide requirements — violating one is a defect regardless of what a task says.

- **Read-only, keyless.** No signer, no transaction construction, no key/keystore/API-key of any
  kind. Every source is a public endpoint requiring no registration.
- **A failed read is `None`, never `0`.** No sentinel is ever written into a history series.
- **A dead source degrades to an explicit unavailable state** with last-good behind an
  `as of HH:MM` marker — never a crash, blank panel, or stale number presented as live.
- **Escape every third-party string** with `widgets/markup_safety.safe_markup` before it reaches
  markup or a table. Announce messages, token name/symbol, and ENS names are all
  attacker-controlled here.
- **Validate persisted series per point** via `data/series_points.coerce_points`.
- **Inject the clock.** No module a test controls may call `time.time()` internally
  (`now=` / `now_ts` parameters).
- **`SurfScreen` inherits `screens/refresh_guard.RefreshGuard`** — no hand-rolled
  `run_worker(..., exclusive=True)`.
- **Sparklines import `widgets/sparkline_common`** — never copy the helpers.
- **Assert against composited output** (`_compositor.render_strips()`), not content strings.
- **No test may touch the network** — inject a transport that raises on use; every external
  payload is a committed fixture under `tests/fixtures/`.
- **Read values live; never hardcode a documented one.** Parity, bridged share, pool
  composition, burn totals and supply are computed each refresh and never asserted as constants.
- **Widgets never import from `data/` or `analytics/`** — they receive
  `str`/`int`/`float`/`bool`/`dict`/`list[dict]`.
- **One owner per shared file.** `app.py`, `screens/game_select.py`, `__main__.py` and
  `themes/minimal.tcss` belong to WP6 alone. Report defects in another WP's files; do not fix
  them. Never `git checkout --` a file to undo your own edit.
- **Run tests as** `.venv/bin/python -m pytest` — the system `python3` lacks the deps.

## Work packages

| WP | Owns | Tasks | Depends on | File |
|---|---|---|---|---|
| WP0 | `data/surf_addresses.py`, `data/surf_models.py` (+ keccak verification test) | 8 | — | [wp0.md](surf_work_packages/wp0.md) |
| WP1 | `data/surf_client.py` | 10 | WP0 | [wp1.md](surf_work_packages/wp1.md) |
| WP2 | `analytics/surf_signals.py` | 11 | WP0 | [wp2.md](surf_work_packages/wp2.md) |
| WP3 | `widgets/surf/*` (6 widgets) | 8 | WP0 | [wp3.md](surf_work_packages/wp3.md) |
| WP4 | `data/surf_cache.py`, `data/surf_manager.py` | 12 | WP0, WP1, WP2 | [wp4.md](surf_work_packages/wp4.md) |
| WP5 | `screens/surf.py` | 6 | WP3, WP4 | [wp5.md](surf_work_packages/wp5.md) |
| WP6 | shared files + integration | 12 | all | [wp6.md](surf_work_packages/wp6.md) |

**67 tasks, 419 steps.**

The plan went through three adversarial review rounds before landing here: spec-coverage and
interface-consistency checkers found 35 findings, a deeper four-checker round found 63 more
(41 blocker/major), and a final blocker-only gate found 16 — each round repaired one-file-per-agent
so no two fixers collided. The recurring defect class was seam drift (three different field
vocabularies for the same dataclass; a readings dict that did not match the frozen signal
contract), which is why the three seams above are now pinned by tests on both sides.

## Execution waves

```
wave 1:  WP0                          (sequential — freezes the contract everyone builds against)
wave 2:  WP1 ‖ WP2 ‖ WP3              (three agents in parallel; no shared files)
wave 3:  WP4                          (needs the client + the pure signal layer)
wave 4:  WP5                          (needs widgets + manager)
wave 5:  WP6                          (sole owner of every shared file; full-suite + smoke run)
```

WP3 has one task (its `SURF_KEYS` contract test) that imports `data/surf_models.py`; if WP0 has
not landed, park that task rather than stubbing the module — one owner per file.

## The frozen interface

WP0 freezes the module surface in wave 1 and nothing after it may rename a field. The three
seams that broke twice during plan review, and are now pinned by tests on both sides:

1. **Dataclass fields** — `NonceSet`, `ChainState`, `ChannelTx`, `DevTx`, `MarketSnapshot`,
   `LogWindow`, `NftStats` are defined once in WP0. WP1 constructs them, WP4 reads them.
   `CONSTRUCTOR_KWARGS` in WP0 pins the field lists so a mismatch fails at import, not at render.
2. **`READING_KEYS`** — WP4's `_readings()` emits exactly the keys `build_signals` consumes, with
   the outage encoding held constant: `None` means "the read failed", `[]`/`()` means "the read
   succeeded and found nothing". That distinction is what lets BRIDGE STAGE fire at all.
3. **`SURF_KEYS`** — the flat manager dict is PRD §5 verbatim; WP3's widget-contract test asserts
   containment so a widget can never read a key the manager does not emit.

## Where the raw material lives

`tests/fixtures/surf/captures/` holds the real keyless-API payloads captured 2026-08-08
(Blockscout REST v2, GeckoTerminal, DexScreener, ensdata, IPFS) with a `README.md` describing the
trimming applied. Tasks slice committed fixtures out of these captures; nothing in the suite
fetches. Two capture facts that matter for tests: the announcement calldata decodes as UTF-8
*except* the one `register()` call (deliberately non-UTF-8), and `ops_eth_txs.json` carries four
real 1-gwei address-poisoning rows while `ops_eth_token_transfers.json` carries the homoglyph
token spoofs — both shapes must be defended against.

## Known gaps carried into implementation

These are documented in the owning work packages and are not blockers; they are decisions the
implementer confirms against the live chain rather than assumptions the plan hides.

- **`identityAllowed()` target** — the working gate is the IdentityRegistry
  (`0x000008061c…`), not the bricked NFT. WP1 confirms live which address answers before pinning.
- **No hooked v4 pool exists yet**, so the V4 LAUNCH path is tested against a synthetic
  `Initialize` row whose *shape* is real (from the 19 live hookless pools). Re-verify against the
  real log on launch day.
- **NFT floor has no keyless source.** `nft_floor` is `None` by design and renders the explicit
  unavailable state; realized Seaport sale prices are decoded from `OrderFulfilled` logs instead.
- **Blockscout reports two different IMD holder counts** (`tokens`: 1148, `counters`: 1132).
  WP4 picks one source per figure and labels it; averaging would invent a number.
- **`LOG_WINDOW_BLOCKS` (~8 h) is a judgement call**, constructor-injectable. If the app is
  closed longer than the window, a bridge stage that landed meanwhile is missed — acceptable, and
  the shrink path is tested.

## Definition of done

The PRD's success criteria (§11), verified by WP6's integration tasks:

1. A new channel post appears within one refresh interval of the tx landing, with decoded text.
2. Replaying the real 2026-08-07 sequence through the signal layer fires BRIDGE STAGE before
   NEW POST, in order.
3. Under full network outage every detector degrades to an explicit state, no signal fires, and
   no baseline moves.
4. `.venv/bin/python -m pytest` is green; no existing dashboard's tests change except the
   registration tests that derive from `GAMES`.
5. The full layout renders at the pinned column width; narrow tiers advertise `‹ widen`.
