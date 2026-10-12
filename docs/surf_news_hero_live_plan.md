# ONCHAIN NEWS / SURFBOARD live hero integration

## Approved scope

The owner selected the six-card proposal, reviewed the standalone Textual mockup,
and requested “connect the api”. Integrate that design into the native default
ONCHAIN NEWS / SURFBOARD body (`SurfScreen.MODE_DASHBOARD`) using existing reads and
cache entries. Preserve the approved ANNOUNCEMENT, LATEST REPLY, SIGNALS, DEV
ACTIVITY, IMD MARKET and NFT BOARDS ordering and nine-row equipment-card design.
The owner target remains 149 columns × 45 rows.

This is Tier 2 because the change adds a production widget and payload contract.
Target fewer than 1,000 production lines overall, with one final review and no
package reviews; aim for roughly 400 lines for the widget and pure projection.
KISS applies: one projected dictionary, one new mode-specific hero, existing
clients/caches and normal screen dispatch. No endpoints, credentials, additional
API calls, user configuration writes or dashboard registration changes.

Only the default news hero changes. `SurfHero` continues serving LAUNCHPAD and the
protocol mode. Keep the existing body panels, routing and other heroes intact.
The standalone demo remains explicitly fictional and reuses the production visual
implementation rather than maintaining a second renderer.

## Frozen primitive contract

Add one key, `surf_news_hero`, to `SURF_KEYS`. Its value is a dictionary containing
exactly six sections below. Declare the field vocabulary in `surf_models.py` and
register `SurfNewsHero.update_data(*, surf_news_hero=None)` in the widget contract.
No model, cache object, datetime, Rich object or Textual object crosses this seam.

Every section includes `state: "ok" | "stale" | "unavailable"` and
`read_ts: float | None` (UTC epoch seconds of the successful source observation).
An absent top-level payload renders all six sections unavailable.

| Section | Additional fields |
| --- | --- |
| `announcement` | `text: str | None`, `age_s: float | None` |
| `reply` | `text: str | None`, `age_s: float | None` |
| `signals` | `fired`, `watch`, `quiet`, `known`, `total`: integers |
| `activity` | `rows: list[dict] | None`, `wallet_count: int | None` |
| `market` | `price_usd: float | None`, `change_24h_pct: float | None`, `points: list[float] | None` |
| `boards` | `holders`, `written`, `moves_24h`: finite nonnegative numbers or `None` |

Activity rows contain only `age_s: float | None`, `wallet_label: str` and
`kind: str`, newest first, at most three. `wallet_count` is the configured tracked
dev/ops wallet scope, not the distinct labels represented by the latest rows.

The announcement is the latest valid nonempty `kind="self"` message from the full
cached channel. COMMUNITY is strictly `kind="reply"`; official answers never
replace it. Select text and timestamp from the same row, reject invalid/future
timestamps, and use a stable transaction-hash tie-break for equal timestamps.
Compute ages from an injected `now`. Do not read the capped 25-row public feed for
these selections or pair its text with `feed_last_post_age_s` from another record.

Healthy, empty channel selections display “No posts in cache” or “No replies in
cache”; bounded history cannot prove that none ever existed. An unread channel
displays unavailable. Activity distinguishes `None` from a successful empty list.

Signal counts use the existing eleven detector names: `fired`, `watch` and `ok`
map to the three displayed rows; known counts only those recognized states.
Unknown states do not become quiet. With no known detectors, show unknown counts
and `KNOWN 0/11`. FIRED is a count of detector types currently fired, not events.
Its existing 24-hour persistence does not make this a 24-hour event total.

Market values reuse the existing selected-price rule; zero is a real value and
must not become unavailable. Retain validated price-series values for the footer
sparkline without inventing points, interpolating missing reads or claiming a
new time window. NFT `moves_24h` maps only to the actual `nft_transfers_24h` value,
never the lifetime written count. Strings remain raw until safe widget rendering.

## Source clocks and freshness

Use the same captured cache version for a value and its clock. Read-only projection
must not refresh an observation timestamp. Reuse existing degradation/failure and
truncation evidence; a failed refresh with last-good data is stale, not zero.
An absent valid source observation is unavailable. Age expiry uses the existing
tier TTLs below, imported from the cache definitions rather than duplicated.

| Hero section | Existing source | Freshness basis |
| --- | --- | --- |
| Announcement / reply | Full `SLOT_CHANNEL.payload.items` | Channel entry timestamp, medium tier (90 s), `SOURCE_CHANNEL` failure/truncation evidence |
| Activity | `SLOT_ACTIVITY.payload.rows` | Activity entry timestamp, slow tier (420 s), `SOURCE_ACTIVITY` failure/truncation evidence |
| Boards | `SLOT_NFT` holder/written/transfer fields | NFT entry timestamp, slow tier (420 s), `SOURCE_NFT` failure evidence |
| Signals | Existing `sig_*` snapshot | `_last_full_read_ts`, poll interval and the source states required by known detectors; never projection time or unrelated global degradation |
| Market fallback | `SLOT_MARKET` aggregator price/change/history | Market entry timestamp, medium tier (90 s), `SOURCE_MARKET` failure evidence |
| Market chain price | Captured launchpad square-root price × market ETH/USD | Both launchpad (600 s) and market (90 s) states; worst required state and oldest required observation |

All three NFT fields selected for this hero come from `_nft_payload(stats)` and
the NFT slot. Only sales use the separate logs clock; sales are not in this hero.
Activity’s configured wallet count describes tracked scope, not successful reads
of every wallet or a claim that both appear in the latest three actions.

Signal source dependencies are post: chain/channel; thread: channel; LP and gate:
chain/logs; deploy: channel/activity; bridge: logs; burn: chain/activity; decoy,
burn-ready and hot: launchpad; swarm: the swarm-launch slot. Only known detectors
contribute dependency failures to the summary. NFT, market, protocol or unrelated
unknown detector failures cannot falsely stale the known channel detectors.

The market headline currently prefers `price_eth_per_imd(sqrt_price_x96) * eth_usd`
and falls back to the market price when that calculation is unavailable. Preserve
that rule. The 24-hour change and historical points remain market-backed. Do not
label a chain-derived price fresh just because the market conversion refreshed.
`_cycle` captures the launchpad slot before detached work; `_project_hub` may see
a newer slot. Either carry the original source version through or recompute the
hero price synchronously from one captured pair of entries and its matching clocks.

Render normal approved footers when healthy. Replace a stale footer with a concise
`stale HH:MM` indication; make the actual source observation available in a tooltip.
Unavailable cells stay explicit. Last-good data may remain visible behind its stale
marker; no fake fresh green state or false quiet state. No per-card network fetches.

## Work packages and file ownership

1. **Planning agent:** owns only `docs/surf_news_hero_live_plan.md`. Freeze this
   contract and communicate it to both implementers. No production edits.
2. **Data owner:** owns `data/surf_models.py`, `data/surf_manager.py`, a small pure
   `data/surf_news_hero.py` projection, and the corresponding new projection /
   manager tests. Paths are under `maxpane_dashboard/` and `tests/` respectively.
   Add the contract first, project the six records without new I/O, and test the
   full-channel selection, source versions, partial knowledge, stale/empty states,
   real zeros and tracked-wallet scope. Manager injection must cover cached and
   normal refresh paths without changing existing flat-field semantics.
3. **Widget owner:** owns `widgets/surf/news_hero.py`, its package `__init__.py`,
   `scripts/surf_news_hero_demo.py`, the demo tests and new widget tests. Implement
   the accepted renderer against the frozen dictionary; the mock demo supplies a
   fictional dictionary using the same widget. Preserve native digits, aligned
   lists, wrapped previews, footer sparkline and safe third-party text handling.
   The widget owner also owns the preview-helper hoist into
   `widgets/surf/_icons.py` and its compatibility alias in
   `widgets/surfboard/rack.py`, so both heroes reuse the same wrapping helper.
4. **Root:** owns `screens/surf.py`, `themes/minimal.tcss`, composing screen tests,
   registration/widget-contract tests and any required measured layout records.
   Compose the new hero once, show it only in default NEWS mode, and dispatch its
   one contract key. Root coordinates live preview, verification, review and commit.

Data and widget packages can run in parallel after this contract is frozen; their
file ownership is disjoint. Root integration depends on both. Agents must preserve
other work and report cross-owner issues rather than editing another package.
There are no per-package review gates.

## Verification and delivery order

- Use focused failing tests before implementation. During editing run only cases
  for the changed behavior. Every automated test is network-free and clipboard-free.
- Assert composited output and actual geometry at 149×45, all six nine-row cards,
  expected values/footers, safe long text, and stale/unavailable states. Verify
  default NEWS uses the new hero while LAUNCHPAD/protocol retain the old hero.
- Include manager cases with the newest valid self-post beyond the public-feed
  cap, a newer official answer than the latest reply, mixed source clocks, a
  skipped tier retaining last-good data, and a failed source retaining its age.
- Once production paints correctly, load existing keyless APIs and show the real
  149×45 render to the owner **before** pin sweeps, layout documentation or review.
  Use temporary preview artifacts; report any unavailable data honestly.
- After the live corrections settle, measure the actual NEWS compositor in situ.
  Change a layout pin or its record only if measured evidence requires it. Prove
  geometry and source/decoder assertions bite with targeted reversible mutations.
- Before commit, run affected complete test files and composing files once with
  isolated HOME and `-n 4 --dist worksteal`; run fast `guard and not mounts_app`
  checks and applicable docpins. No full suite without an owner request.
- Perform one independent final review of the scoped diff, one fix wave, and one
  scoped re-review only when the fixes alter production code. File Minor-only
  residuals using the repository process. Root commits exact owned task files.

Finish this dashboard’s live-data confirmation before beginning the next dashboard
in the owner’s ASCII → Textual mockup → API workflow. Other dashboard hero designs
remain deferred to their individual selection stages.
