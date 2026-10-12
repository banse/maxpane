# LAUNCHES / SWARM TOKENS live hero integration

## Approved scope

The owner approved proposal 1's Textual mockup and explicitly requested the API
connection. Replace the existing four-card token hero with the six accepted
equipment cards: TOKENS, VOLUME, LIQUIDITY, POOLS, MOMENTUM and TOP VOLUME.
Preserve their order, equal nine-row height and approved 149×45 presentation.

This is Tier 2, under 1,000 production lines overall, with one final review and
no package reviews. Use existing reads, snapshots and source metadata. No new
endpoint, scheduler, polling task, cache format or configuration write. Keep the
native activity, newly launched, movers and token-table panels and filter behavior.
Superpowers remain disabled; favor a small pure projection and renderer adapter.

## Projection and visual contract

Add one `tokens_hero` dictionary to the existing `project_snapshot` result and
declare its exact primitive vocabulary in `data/swarm_tokens_models.py`. Build it
from the **already filtered tokens**, after the same chain, search and LP filters
used by the native body. Sorting changes presentation order, not aggregates or
membership. Never use unfiltered snapshot-level quote/liquidity coverage for a
filtered hero. No data/model objects or Rich/Textual values cross the contract.

The frozen primitive schema is `HERO_FIELDS` in `data/swarm_tokens_models.py`.
Every section has `state` (`ok`, `partial`, `stale`, `unavailable`) and `read_ts`
(successful source observation in epoch seconds, or `None`). Unknown numeric
facts remain `None`; zero means a known value.

| Section | Additional fields |
| --- | --- |
| `tokens` | `tracked`, `new_24h`, `chains` |
| `volume` | `amount` (USD), `known`, `total` |
| `liquidity` | `imd`, `eth`, `known`, `total`, `partial` |
| `pools` | `two_sided`, `one_sided`, `unknown`, `other` |
| `momentum` | `rising`, `falling`, `flat`, `known`, `total` |
| `top_volume` | `rows` of `{symbol, volume_usd}`, `known`, `total` |

`tokens_hero` is the final required projection key, preceding optional `sources`.
`TokensHero.update_data(*, tokens_hero=...)` is its sole dispatch input. Existing
`metrics` and native body projections retain their current behavior.

| Card | Live facts and display |
| --- | --- |
| TOKENS / STATS | Selected token count, launches in the last 24 hours, distinct selected chains; footer `SELECTION` |
| VOLUME / USD scale / 24H | Sum of eligible 24-hour USD volumes, with explicit USD/kUSD/MUSD scale; known/selected coverage; footer `MEASURED` |
| LIQUIDITY / PAIRED | Separate eligible IMD and ETH paired quantities, lower-bound markers when incomplete, known/selected coverage; footer `QUOTE ASSETS` |
| POOLS / STATE | Two-sided, one-sided and unknown LP counts; no inset bottom text in the approved normal state; footer `LIQUIDITY` |
| MOMENTUM / 24H | Rising, falling and flat eligible 24-hour price changes, known/selected coverage; footer `PRICE CHANGE` |
| TOP VOLUME / USD / 24H | Three largest eligible selected-token volumes with symbols and USD amounts; footer `LEADERS` |

Reuse unchanged `NewsHeroCard` and `HeroRecord` from `widgets/surf/news_hero.py`.
Keep grey casings, dark insets, theme accents, aligned labels/values and common
bottom baselines. VOLUME uses an explicit USD/kUSD/MUSD scale: 124,800 USD is
displayed as `124.8` under `kUSD / 24H`. Very small nonzero values retain a
scientific-notation fallback rather than rounding to zero. Paired IMD and ETH are not USD
TVL and must never be added together. All external strings are flattened/escaped
at the renderer boundary. The standalone demo stays explicitly fictional.

## Eligible values and source freshness

Snapshot `as_of` is an evaluation clock only. Catalogue observation comes from
`sources.catalogue.state/as_of`. Other card coverage and observation times must
be folded from the selected tokens' own source fields, using the same rows as the
values. Validate finite numbers and positive, nonfuture source timestamps.

| Fact | Source fields and eligibility |
| --- | --- |
| Token membership / new count / chains | Filtered token rows and catalogue metadata; new means `0 <= as_of-launched_at < 86400` |
| Volume / top volume | Finite nonnegative `volume_24h` with a fresh usable `market_state` and `market_read_at` |
| Momentum | Fresh usable market observation, positive `price_usd`, finite signed `change_24h`; zero change is flat |
| Paired liquidity | Fresh usable `liquidity_state/liquidity_read_at`, finite nonnegative `paired_amount` and recognized paired asset |
| Pool condition | Selected `lp_state` with liquidity observation metadata; combine `one-token` and `one-quote` as one-sided |

Stale market values remain present in manager rows but must not enter fresh totals,
momentum counts or leader rankings. A valid zero volume or paired quantity is data;
missing/invalid/unread values are not zero. Preserve the distinction between an
empty successful selection and an unavailable catalogue. Lower-bound paired sums
retain `>=` when selected coverage is incomplete. Do not invent a zero for an
unobserved asset merely because another asset was observed.

Retain real source clocks when reads fail; never replace them with projection time
or a different token's newer read. A card's source age must describe its contributing
observations. Partial catalogue or measurement coverage remains explicit through
the contract's coverage/state indicators and visible subtitle/footer treatment.
Fresh but incomplete data is not falsely labelled stale. Fresh measurements with
a stale or partial catalogue have `partial` state and the oldest contributing
measurement clock; TOKENS retains the catalogue state and catalogue clock.
All-stale measurements have `stale` state and their actual old clock, with unknown
numeric facts rather than a stale sum. An empty fresh selection has known zeros
at the catalogue clock; an unavailable catalogue makes all hero facts unknown.

The unchanged shared renderer directly supports `ok`, `stale` and `unavailable`.
The token-card subclass formats degraded footers as orange `partial HH:MM`,
`stale HH:MM` or `unavailable`, using the native dashboard's local clock. Its
tooltip labels the same local observation time; the shared renderer stays intact.
Known coverage stays visible in the inset subtitle, and the source read clock
remains available in the tooltip. No shared renderer change is needed.

Rank TOP VOLUME descending by eligible USD volume with a deterministic token-id
tie-break. Missing leaders render honestly rather than fabricated rows. Preserve
actual LP vocabulary: withdrawn/other states are not silently recast as two-sided,
one-sided or unknown. Any necessary out-of-three-state indication must be explicit
without changing the approved normal-state empty inset footer.

## Work packages and ownership

1. **Planning agent:** only `docs/surf_launches_hero_live_plan.md`. Record scope,
   primitive contract, source semantics and verification; no production edits.
2. **Root:** `data/swarm_tokens_models.py`, `screens/swarm_tokens.py`, associated
   CSS, `widgets/swarm_tokens/__init__.py` exports, composing/contract tests, and
   any measured layout records/documentation.
   Freeze `tokens_hero`, integrate the new widget through existing panel dispatch,
   preserve filter/navigation behavior and coordinate live preview and commit.
3. **Data owner:** the pure `analytics/swarm_tokens.py` projection and its tests,
   with an additional small pure helper module only if needed and agreed. Fold
   the hero after selection without changing manager reads or native body values.
   Test eligibility, clocks, coverage, zero/unknown states and deterministic leaders.
4. **Widget owner:** new `widgets/swarm_tokens/hero.py` and widget
   tests. Adapt primitives into the unchanged shared rack renderer, preserve the
   approved visual contract and explicitly render partial/stale/empty states.

Production paths above are relative to `maxpane_dashboard/`; tests live under
`tests/`. Root coordinates any demo adapter changes. Data and widget owners may
work in parallel after contract freeze; root integration depends on both. Files
are disjoint. Preserve others' work and report cross-owner issues rather than
editing another package. No per-package reviews.

## Verification and delivery order

- Write focused failing tests before implementation; while editing run only changed
  cases. All automated tests refuse network and real clipboard access.
- Cover chain/search/LP filters, selected denominators, known zero, unavailable
  catalogue, empty selection, partial catalogue, stale/unsupported quotes, missing
  source clocks, mixed assets and top-volume ties. Retain existing body projections.
- Assert composited content and actual geometry at 149×45: six equal nine-row
  cards, complete titles/footers, scaled USD value, separate paired units, native
  body panels and no unwanted overflow. Exercise narrow resize and filter controls.
- When the production view works, show a keyless live 149×45 render before pin
  hardening, layout records or final review. Use temporary artifacts and keep
  partial/stale/unavailable readings honest in the visible design.
- After live corrections settle, measure the actual compositor in situ. Change
  pins only if evidence requires it. Prove important projection/clock and geometry
  assertions bite using targeted reversible mutations.
- Once before commit, run complete affected and composing test files with isolated
  HOME and `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and
  applicable docpins. Do not run the full suite without the owner's request.
- One independent final review, one fix wave, and one scoped re-review only when
  fixes touch production code. File Minor-only residuals through the existing
  follow-up process. Root commits exact task files and reports the last green checks.

Complete LAUNCHES live-data confirmation before starting the next dashboard's
three ASCII proposals in the owner's repeated mockup → API workflow.
