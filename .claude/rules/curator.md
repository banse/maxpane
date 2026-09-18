---
paths:
  - "maxpane_dashboard/screens/curator.py"
  - "maxpane_dashboard/widgets/curator/**/*"
  - "maxpane_dashboard/data/curator*"
  - "maxpane_dashboard/analytics/curator*"
  - "sybilkit/**/*"
  - "tests/**/*curator*"
  - "tests/fixtures/curator/**/*"
---

# curator — THE LIST dashboard

Key history and withdrawn statements are in `docs/decisions.md`; this file states only what is
true now. Layout pins live beside their constants; the terminal-layout skill names them.

## Keys and views

- `y` swaps the whole body for the reader's own standing — ladder, share, and what passing the
  rank above would cost — hero left in place so the doomsday clock never leaves the screen;
  `esc` backs out, one-way.
- `a` swaps in the linked-wallet analysis body (OPERATORS / SEGMENTS / CLEANED LIST,
  `action_toggle_analysis`) the same way; a second `a` or `esc` backs out. `a` is deliberately
  **not** in `KEY_HINTS`: the owner asked for the binding, not the label, and the hint string is
  pinned at 138 columns.
- `l` opens one full-width record table under its own raw/wallet/cleaned summary hero; `c`
  cycles the list view and remembers the choice (the list title is the sole RAW/CLEANED
  indicator). Each list keeps its own typed header-click sort, a second click reverses it, and
  the fixed YOU row is excluded.
- `f` opens the custom filter editor inside `l`'s record view (`action_toggle_filter`; a no-op
  everywhere else). Digit keys `1`/`2`/`3` are the filter presets.
- `e` exports the active list: the analysis body's own JSON + CSV whenever that body is open
  (`~/.maxpane/curator_clean_list.json` / `.csv`); `l` writes the full uncapped raw or cleaned
  JSON (`curator_raw_list.json` / `curator_cleaned_list.json`); a no-op on dashboard and wallet
  modes. Curator's `e` and surf's `e` are two screens' own bindings, not one shared key; the
  same holds for the two `l`s.
- `w` prompts for the wallet the YOU row is about — `WalletInputScreen` validates and persists
  to `~/.maxpane/config.toml`, app-wide from the next launch. **A runtime wallet switch is more
  than an assignment**: `CuratorManager.set_wallet` also drops the wallet last-good (its payload
  names the *old* address) and expires the fast tier, because a tier with 12 of its 15 seconds
  left is "fresh" and the row would stay dark after a keypress that looked like it worked.
- Status hints read `c view · h history · y you · l lists`; all four labels plus the worst-case
  `4 errors` fit at 138 columns. Each visible panel title already names its state.

## The linked-wallet analysis — the `sybilkit` seam

`data/curator_clusters.py` is the only maxpane module that imports `sybilkit`
(`test_only_curator_clusters_imports_sybilkit` walks every `.py` under `maxpane_dashboard/`).
It is also the *translation boundary*: the library is a general sybil-analysis toolkit and may
say so in its own strings, but `pattern_language()` re-checks every reason, label and detail —
including strings read back from a **persisted** payload, because a hand-edited cache file is
third-party input too — and swaps a forbidden word for the evidence family's own phrase. On
screen the evidence labels speak only patterns: *linked*, *fan-out*, `⚑`/`◌`/`~`/`?`
(high/low/review/unknown), and every evidence panel has its own composited forbidden-word test.
`analytics/curator_signals.py` never mentions or imports the library
(`test_curator_signals_never_imports_sybilkit`); its Tier-A `find_clusters` is unchanged and
`LEADERBOARD_LIMIT = 1_000` caps the `l` record view payload.

The import is guarded (`try/except ImportError` → `SYBILKIT_AVAILABLE`) and that flag is the
packaging story: `sybilkit>=0.1.0` is declared from maxpane v0.8.0, and an older install, a
partial environment or a future name change renders `analysis unavailable` rather than crashing.

**The analysis is read, not swept** (the `_spawn_crosscheck` precedent, 2026-08-27). THE LIST's
published, immutable linked-wallet analysis — keyless, from `clustermap.vibingco.de`, no
key/token/secret anywhere near it — replaced the locally computed tx-fingerprint/funder sweep:
one version check per tick, and the two bulk reads (~8.3 MB) run only when the compound
`(version_id, content_hash)` has moved. **The hash is the half that earns its keep**: the
publisher rebuilds under one id, so an id-only check would keep serving superseded rows until
the id itself changed; `archive_key` is compound too, and `_is_same_published`'s docstring is
the authority. The export names the population it wants (`q=&link=all&evidence=all&preset=none`)
and the `filters` echo in the answer is read back. The read is spawned, never awaited
(`test_the_first_payload_is_not_behind_the_analysis_read` fails by timing out), on
`TIER_ANALYSIS` (1800 s, 300 s after a failure) with the `SLOT_CLUSTERS` last-good, so the
analysis panels carry an `as of HH:MM` on a slower clock than the title bar's — the marker
advances only when a genuinely new version lands. `analysis_version` names which analysis sits
behind that marker. `content_hash` is publisher-asserted (nothing recomputes it — a trust
boundary, not a defect), but both bulk responses self-identify (`overview["version"]`,
`export["analysis_version"]`) and a pair whose id or hash disagrees with `/versions` is refused.
Superseded exports are archived into `~/.maxpane/archive/<version-id>-<hash12>/`, never deleted;
nothing prunes that directory. A failed read folds into the **`logs`** degraded group only when
there is nothing to serve; otherwise a stale `analysis_as_of_hhmm` is the signal.

**Nothing is persisted as a verdict.** The slot holds revisable rows; groups carry a band *word*
and their families, never a boolean, and a test scans the cache file for one. Banding is
**structural, not numeric**: noisy-OR puts every gated cluster at ≥ 0.77, so `high` means ≥ 3
distinct families or funding present and `low` means exactly two. The library's own 0.5 flag
threshold is likewise structurally inert.

## Record-view filters and the hero contract (2026-08-23)

An empty filter is not an empty result: applying a filter with every field unset returns the raw
list and switches the view back to RAW. In the NFT HOLDERS editor, custom collection controls
and the selected collections share two outer columns; selected collections use a compact
two-column, row-major grid with no blank rows between entries. The three predefined choices are
a hand-typed tuple; custom CryptoPunks-shaped entries are valid.

The three record-list hero cards have a five-line contract. Keep the order stable:

1. The summary card shows `THE LIST`, wallet count, the view's primary total, its context, then
   `list FROZEN`, `list CLEANED`, or `list FILTERED`. The raw primary total is routed ETH;
   cleaned and filtered both use points followed by the routed ETH those wallets deposited,
   without a `deposited` suffix. The cleaned card's ETH comes from
   `CuratorManager.clean_routed_eth()`, which totals the analysis slot's **`clean_ranks`** (every
   clean wallet) and never `clean_list_rows` (capped for display); it is `None` — the dash,
   never a zero — with no analysis or an incomplete fold. It is a screen-supplied hero kwarg,
   not a payload key, so `CURATOR_ANALYSIS_KEYS` stays at fourteen.
2. The wallet card shows the verified ENS name or `YOUR WALLET`; `#rank of total ·
   raw|clean|filtered`; join/hour detail or the active filter summary; `points · credited ETH`;
   and the full wallet address, visible even when ENS exists. Title, standing, points/ETH and
   address use success green; the detail line uses `$success-darken-2`.
3. The filter card shows `THE FILTER`, then `'1' - first 1000 wallets`, `'2' - joined hour 0`,
   `'3' - whale splash`, `'f' - more filters`.

ENS hydration for these lists follows the data rule: the complete raw list is the sole
network-hydration boundary; derived lists reuse its cache; long-running ENS, export and reload
work owns the centered footer message while it runs and clears only its own message.

## Captures

`tests/fixtures/curator/captures/live/` holds hand-captured hour-boundary and grace states that
cannot be recreated. Tests name the ones they use (`CAPTURE_A`, the grace-late bundle) and never
a file count; the ~300 untracked 4-second polls beside them are protected, never staged.
