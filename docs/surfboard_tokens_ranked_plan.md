# Surfboard TOKENS ranking specification and implementation plan

Date: 2026-10-13. Tier 2: the card contract changes. Expected scope is below
1,000 production lines; no package reviews, one final review. This specification
supersedes the behavior in the historical TOKENS/latest-launch plans. Existing
Python/Textual/Rich architecture applies.

## Approved behavior

- Rename the rack card `LAUNCHES` to `TOKENS` and its inset `LATEST` to `LAST 24h`.
- Keep three age/ticker rows. Rank supported token deployments launched within
  the last 24 hours by descending selected-pool 24-hour USD trading volume.
- Replace liquidity markers with green `▲` or red `▼`, comparing consecutive
  successful price reads. First, equal, missing, or incomparable prices show `—`.
- Replace this card's outer volume footer with the newest launch's age and ticker.
  It is independent of the volume ranking and may be older than 24 hours.
  Remove this card's outer `24H` text and sparkline.
- Preserve navigation, card geometry, neighboring cards, and existing launch
  activity behavior. Retain positive `x new` inset text when healthy; partial or
  stale ranking replaces it with an explicit state and dated source marker.

## Evidence and data contract

Root freezes the following contract before independent implementation starts.
Replace `latest_launches` in `SURFBOARD_CARD_FIELDS` with `token_ranking`.
Other cards carry `token_ranking=None`; this card carries exactly six fields:

```text
{rows, newest, state, read_ts, known, total}
rows: None | [] | up to three {id, age_s, symbol, chain, volume_usd, price_direction}
newest: None | {id, age_s, symbol, chain}
price_direction: "up" | "down" | "flat" | None
state: "ok" | "partial" | "stale" | "unavailable"
```

`rows=None` means ranking evidence is unavailable; `[]` means a known empty
eligible population. `known` reports eligible deployments with usable volume;
`total` reports the known eligible population, or is unknown when it cannot be
established. The literal tooltip discloses coverage, state, and successful source
read time. `read_ts` belongs to source evidence, never to repaint or failure.

- Reuse supported production-chain/address validation. Include valid inactive
  deployments; deduplicate aliases by chain/address. Rank only unambiguous
  canonical deployments. Use the earliest known launch record for each so
  relisting cannot reset eligibility. Keep age's existing catalogue-time meaning.
- The window is exactly `0 <= age_s < 86400`, using the injected clock. Exclude
  unknown or invalid launch times. Break volume ties deterministically by launch
  time, then canonical deployment identity; newest selection is deterministic too.
- Reuse existing selected-pool `volume_24h`, `price_usd`, and independent 120-second
  market freshness. Zero volume is valid; missing, negative, boolean, or nonfinite
  volume is unknown and cannot enter a claimed ranking.
- Rank fresh known volumes first. Incomplete catalogue/market coverage must show
  `partial` or `unavailable`, not imply an exhaustive top three. A retained ranking
  may render only with explicit stale qualification and neutral price markers.
- Compare prices only across distinct successful market fetches for the same
  chain/address and expected/selected pool identity. Prices must be valid and
  positive. Pool changes reset comparison; projections never advance it. Failed
  or invalid reads cannot create a zero price or an arrow. Preserve the last valid
  baseline across failures without presenting it as fresh evidence.
- The newest footer uses the full valid canonical launch population, independent
  of volume availability. Distinguish no launches from an unread catalogue and
  disclose partial/stale evidence. Sanitize tickers as third-party text.
- Hub token enrichment offers catalogue and market reads only. Remove its hourly
  volume-history offer, while preserving history, price-history, and trade
  functionality used by the dedicated token dashboard. Add no endpoints or keys.

## Work packages and exclusive ownership

Production paths below are relative to `maxpane_dashboard/`; tests are repo-relative.
All owners preserve concurrent edits and report defects in another owner's files.

| Package | Owner and files | Dependencies |
|---|---|---|
| WP0: contract and projection | Root: `data/surf_models.py`, `data/surfboard.py`, `data/surf_manager.py`, corresponding data/contract tests | Approved specification |
| WP1: ranking evidence | Data worker: `data/swarm_tokens_manager.py`, new focused ranking tests under `tests/data/` | Frozen WP0 contract |
| WP2: card rendering | UI worker: `widgets/surfboard/rack.py`, `tests/widgets/test_surfboard_rack.py`, `tests/surfboard_fixtures.py` | Frozen WP0 contract |
| WP3: integration and completion | Root: composing screen tests, required layout evidence/docs and follow-ups | WP0–WP2 integrated |

WP1 and WP2 run in parallel after contract freeze. No shared file has two owners.
The planner owns only this document; no extra ledgers or child agents are required.

### WP1 — canonical population, ranking, and price comparison

Start at `_tokens`, `_refresh_markets`, `catalogue_summary`, and
`_offer_enrichment`. Write failing offline tests, then the smallest implementation.
Cover inactive deployments, aliases/relisting, ambiguous/duplicate identities,
exact window boundaries, equal-volume ties, newest outside the window, valid zero
volume, missing/malformed values, incomplete coverage, stale evidence, and empty
versus unavailable. Test first/up/down/equal prices, repeated projections, failures,
pool changes, and stale expiry. Assert hub offers no history/trade work and the
dedicated dashboard retains its existing enrichment behavior.

### WP2 — labels, rows, footer, and explicit states

Start at `SLOTS`, `_launch_preview`, `meter_text`, and `render`. Add failing
composited-strip tests for both labels, ordered age/ticker rows, green/red/neutral
markers, newest footer, and absence of this card's volume sparkline/label.
Cover fewer than three rows, partial/stale/unavailable/empty states, dated state
markers, literal tooltip coverage/clock, hostile and wide tickers, clipping hints,
activity styling, and unchanged navigation. Use existing cell-width helpers and
pre-built Rich Text.

### WP0/WP3 — integration, live evidence, and completion

Project the exact envelope through the manager and hub card builder; update
agreement tests and consuming fixtures. Keep projection pure and scheduling in
the existing manager refresh path. Run only touched behavior tests while editing.

Once integrated, show a real keyless live render at **149×45** to the owner before
layout/doc hardening or review. Incorporate corrections, then check existing
minimum dimensions and resize behavior under the terminal-layout skill. Change
pins and their measured `#:` blocks only if observed geometry requires it.

Use focused mutation checks for population/window, ranking freshness, and pool
identity gates. Before completion, run touched test files and composing
screen/manager files once with isolated test home and `-n 4 --dist worksteal`,
then fast `guard and not mounts_app` checks and required documentation pins.
All tests remain offline; no full suite. Dispatch one final review with the
verbatim repository reviewer contract, permit one fix wave and a scoped re-review
only for production fixes, file Minor-only residuals, and commit the scoped work.
