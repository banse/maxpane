---
paths:
  - "maxpane_dashboard/data/**/*"
  - "maxpane_dashboard/analytics/**/*"
  - "tests/data/**/*"
  - "tests/analytics/**/*"
  - "tests/fixtures/**/*"
  - "sybilkit/**/*"
  - "tests/widgets/test_*_contract.py"
---

# Data and analytics layer — the full rules

Every rule here is a bug that shipped, was found, and was fixed repo-wide. The headlines are in
`CLAUDE.md` "Conventions"; this file carries the reasoning and the tests that enforce them.

## Purity

`analytics/` is PURE: no I/O, no clock, no Textual imports. Widgets may import pure, stdlib-only
helpers from `analytics/`; they may not import `data/` (a layer that imports `httpx`). Measured
2026-08-24: 22 widget modules already import `analytics/` and 10 still import `data/`
(`base/*` ×8 for `data.base_models`, `leaderboard`/`activity_feed` for `data.models`). Those ten
are legacy debt, not licence. State the rule as purity and prove it:
`tests/widgets/test_surf_widget_contract.py` is the worked example — an allowlist of analytics
modules a surf widget may import, plus `test_the_allowed_analytics_modules_are_themselves_pure`,
which AST-walks each allowed module's own imports to a fixed point and asserts none reaches
`data`, `textual`, `httpx` or `aiohttp`. The recursion is what bites: a depth-1 version was green
while `analytics/surf_feed` imported `analytics/surf_signals`, which reaches `data` in one hop.

## A failed read is `None`, never `0`

Clients that turn an outage into `0`/empty make a manager unable to distinguish "RPC down" from
"the value is zero" — and the zero then gets *persisted*, so the corruption outlives the outage.
Never write a sentinel into a history series.

## A dead source degrades to an explicit unavailable state

Never a crash, never a blank panel, never a stale number presented as live. Serve last-good
behind an `as of HH:MM` marker. Check the widget can *tell*: a row whose real negative has no
representable value ("no whale in the last hour", "it has never fired") renders `None`
identically for "we looked and there was nothing" and "we could not look", so it reads confident
and green through an outage. Curator's rail shipped that way: FARM said `-- unknown` off
`clusters_count is None` while HOUR SAVED and WHALE, folded from the same dead group, said
`none yet`. Either give the value a representable zero or hand the widget the `degraded` list.

A *false* degradation is the same defect pointing the other way: naming a whole group degraded
on the evidence of one slow tier tells a reader eight panels are unreliable when seven are live
(`tests/data/test_surf_manager_pool4_market.py::test_a_sweep_with_nothing_to_serve_names_no_group_at_all`).

## ENS names are third-party strings, and the widest kind

Reverse resolution lives in `data/ens.py` and is keyless; use it through a client's own multicall
so it inherits that dashboard's pool. Two rules it exists to keep: the **forward check** is not
optional (a reverse record needs nobody's permission, so an unverified lookup lets any address
claim `vitalik.eth`), and a **miss is not an empty name** — most wallets have no record, and
without recording the misses every one of them is re-resolved on every tick forever.
`ens.NameStore` holds both TTLs.

For record lists, the **complete raw list is the sole ENS network-hydration boundary**. Cleaned
and filtered lists reuse the raw-list ENS cache; changing filters must never start hydration
again. When hydration finishes, repaint whichever derived list is visible.

## A token's `decimals()` is a live read, never 18 by assumption

pool4's sIMD vault is a Solady ERC4626 reporting *asset decimals + `_decimalsOffset()`* — 18 + 6 —
so `decimals()` answers **24** and one whole share is `1e24`. Both wrong divisors render as
plausible numbers: `convertToAssets(1e18)/1e18` reads `0.0000013 IMD/share` (looks like a dead
vault) and `totalSupply/1e18` reads 21 *billion* shares (looks like an emissions farm), against a
true share price of `1.302986` and 21,010.98 shares. The decoder **refuses** a capture that asked
`convertToAssets(1e18)` rather than mapping a wrong-argument answer onto a right-looking field —
the fix belongs in the capture. A test refuses a `POOL4_VAULT_DECIMALS`-shaped constant. A
constant that happens to agree with the chain today is not evidence for the constant; it is the
reason nobody would notice when it stops agreeing (see `docs/decisions.md`, 2026-09-02).

## Read values live; never hardcode a documented one

Docs drift, chains do not. One protocol documents a 5% fee that is 1% on chain; a "4.0×" ratio
quoted in research measured 3.885×, 3.49× and 2.956× on three consecutive days. Mainnet pool4
shipped a different protocol from testnet and almost all of it self-adapted because nothing was a
constant; the one thing that did not was *structure* (an extra hop), which a live read cannot
absorb.

## Validate persisted series per point

Use `data/series_points.coerce_points`. A single `null` in a cache file used to abort startup for
*every* dashboard. A hand-edited cache file is third-party input too: strings read back from a
persisted payload get the same checks as strings fetched live.

## Series caches subclass `data/series_cache.SeriesCache`

A per-poll history cache declares its series once — `SERIES = (SeriesSpec("prize_pool_history"), …)` —
and inherits the atomic write, the open/decode and dict guards, the injected clock
(`load_from_file(path, *, now=None, max_age=None)`), the per-point `coerce_points` loop with a
per-series `max_age`, clear-before-extend and the `"Skipped %d …"` warning. `record(name, ts, value)`
drops `None`: a failed read never becomes a `0` in a series, and the manager passes `None`, not a
default (`cattown_manager`, `frenpet_manager`). Hooks: `update()` (per cache), `extra_payload` /
`restore_extra` (keyed dicts, scalars), `before_load` (version branches), `history_size` (key-count
for the keyed caches, point-count otherwise), `SeriesSpec.key` when the JSON key differs from the
attribute. **Never add a version key to a cache file that has none and never rename one:** ocm's
`"version": 2` and frenpet's `"schema_version": 2` are what every live `~/.maxpane/*.json` carries;
a rename reads as v1 and empties users' burn or population series. Acceptance for any change here
is the fixture set `tests/fixtures/cache/*_53a71d5.json` — six files written by the pre-refactor code
plus two v1 files derived from them (`tests/scripts/make_cache_fixtures.py`) — loading point-for-point
and re-saving to the same parsed JSON, key order included, with only `saved_at` excused
(`tests/data/test_series_cache.py`).
`talismans_cache` and `ttt_cache` are event caches, not series caches, and do not subclass it.

## Inject the clock

No module a test needs to control may call `time.time()` internally. Cache loaders take `now=`;
signal builders take `now_ts`.

## `eth_call` to an address with no code returns `"0x"` and no error

"The call did not fail" is not "the getter answered". `surf_pool4.answered` is the one place that
distinction lives. Absence cases in tests must be driven by a getter made to revert, not by
pointing at a chain where the getter exists with a different value.

## RPC endpoints

**Verified dead, do not reintroduce:** `eth.llamarpc.com` (521), `rpc.ankr.com/eth` (now keyed),
`cloudflare-eth.com` (`-32046` on Ethereum), `api.reservoir.tools` (DNS gone, API sunset),
`rpc.sepolia.org` (404), `omniatech` (521), `ethereum.blockpi.network` (non-JSON),
`eth.merkle.io` (`-32601` for `eth_getLogs`).

**Never add to a log pool:** `rpc.flashbots.net` — answered a 75,000-block `eth_getLogs` with 46
logs where the truth was 1,132, no error, no warning. A wrong answer that looks right defeats
every degradation path in this repo.

**Working keyless Ethereum mainnet:** `ethereum-rpc.publicnode.com` for state (batches, but
**refuses archive `eth_getLogs`**); `gateway.tenderly.co/public/mainnet` and `rpc.mevblocker.io`
for logs (`mevblocker` names a real cap truthfully — `range 75000 exceeds limit of 10000` — so a
client can chunk against it; measured 1,132 logs in 8 chunks, agreeing with tenderly to the log).
**State and logs need different endpoint pools.**

**`eth.drpc.org`** is in FWA's and curator's pools (recent logs, where it works) and out of
surf's mainnet log pool since 2026-09-12: its free plan's limit is **archive depth, about 64
blocks**, not page width, and it answers anything older with `code 35 "ranges over 10000 blocks
are not supported"` *whatever span you asked for*. A client that shrinks on that message halves
its window forever. **A provider's error message is only evidence about the request it was
actually reading**: if the limit it names is one you already meet, rotate, do not shrink.

**Sepolia does not inherit mainnet's story.** `ethereum-sepolia-rpc.publicnode.com` batches
`eth_call` *and* serves archive `eth_getLogs`. `sepolia.drpc.org` answers every method with
`code 35 "chain is not available on free plan"` — a keyed endpoint wearing a keyless URL — so ban
it **by hostname**, never by `drpc.org`. `1rpc.io` serves one 30-call batch then 429s and caps
logs at 50 blocks: state fallback only. Tenderly's Sepolia gateway answers a 3-call batch and
rate-limits the 30-call round the client actually issues — **probe with the batch you ship**.

**Classify RPC errors on message text, not code.** Providers reuse `-32602` and `-32005` for
unrelated meanings; one provider's "suggested retry range" decrements one block per round trip
and livelocks anything that follows it verbatim. Evidence:
`tests/fixtures/surf/pool4/rpc_error_states.json`.

**The DOTA game API is NXDOMAIN.** The Bakery season ended 2026-06-12; its API still serves.

## Tiers and clocks

Long reads (`TIER_ANALYSIS`, `TIER_LAUNCHPAD`, `TIER_POOL4`, `TIER_POOL4_STAKERS`, the swarm
tiers) are spawned and never awaited, so first paint never waits on them
(`test_the_first_payload_is_not_behind_the_analysis_read` fails by timing out). Each carries its
own last-good slot and its own `as of HH:MM`, which advances only when a genuinely new version
lands. `SOURCES` in `data/surf_manager.py` stays at **eight** degraded groups — `SOURCE_POOL4`
(`p4`) is the last name the worst-case title row has room for (terminal-layout skill); newer
tiers serve last-good behind their own marker plus a conditional `stale` word derived from the
two tiers' TTLs, and never name a group.

## `sybilkit/` is a second Python distribution

A sibling of the `maxpane/` Rust crate, not a package inside `maxpane_dashboard/`: own
`pyproject.toml`, own `sybilkit_tests/` (not `tests/`: two packages of that name cannot be collected together), own version, own PyPI name (`0.1.0` since 2026-08-19). It is
maxpane-independent (stdlib core; `httpx` is the optional `[sources]` extra, imported lazily).
Build with `python -m build sybilkit/`; the root build must not build it. Only
`data/curator_clusters.py` imports it (`test_only_curator_clusters_imports_sybilkit`), through a
guarded `try/except ImportError` → `SYBILKIT_AVAILABLE` that **stays**: an older or partial
install renders `analysis unavailable` instead of crashing. Its fetcher tests need the
`[sources]` extra; run them with `.venv/bin/python -m pytest sybilkit`, because an interpreter
without `httpx` *skips* them and reports green.
