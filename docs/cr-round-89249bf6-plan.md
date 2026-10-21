# CR round 89249bf6 — specification and work packages

Batch `89249bf6-6ee4-4eb2-99a1-32730c275f78`, baseline `d28d4fff`; already claimed by the
controller. Nine requests cover several views and shared layout seams: **Tier 2**. This is
the initial implementation plan, not completion evidence. The requests authorize their
implementation; no further general design approval is required.

## Acceptance scope

| Request | Required result |
| --- | --- |
| Work tree | Two separately titled widgets: WORKFLOWS above JOBS. WORKFLOWS receives less vertical space, JOBS more. Keep a usable minimum and independent scrolling; retain current data coverage, search/status filtering, node selection, icon-only disclosure and shared detail behavior. |
| Oracle width | Narrow REQUESTS modestly and give the released width to SELECTED REQUEST. Preserve request columns, selection and detail scrolling; determine the seam from the live composition. |
| BOARDROOM navigation | Move the navigation help into the top header: arrow-key instructions left of centered `IMD BOARDROOM`, Enter instructions right. Use symmetric gaps/regions so unequal hint lengths do not move the title off center. Clear the former help text above the terminal and preserve existing rack/terminal geometry. The submitted `OMD` is treated as the existing `IMD` title. |
| Token loading | Remove generated visible partial notices; retain known counts and hover evidence through a token-specific `TokensHeroCard._footer` override of the existing hook. Use the existing shared dashboard loading indicator during actual pending reads. Keep source coverage, state and successful-read timestamps internally and in available detail/hover. Missing data remains missing, and refresh failures must clear the loading state. |
| Newly launched | Show at most seven newest matching tokens in NEWLY LAUNCHED / 24H. This is a display limit, not a catalogue-fetch limit or a change to new-token totals. |
| Activity replacement | Replace ACTIVITY with TOP TRADED / 24H: the owner clarified **24h volume across tokens of all launch ages**. Reuse the existing selected-pool USD volume; no lifetime-history source is required. |
| Best Plays | Remove the `? unknown` marker and its legend entry. Keep those token rows and their measured returns. Add one blank row above the remaining indicator legend when it exists. Preserve one-sided and withdrawn indicators. |
| POOL4 MARKET (`surf.pool4_user`) | Reality-check all currently displayed data through its source, decoding, projection and rendered meaning; report verified defects and material unavailable/unverifiable facts. |
| PROTOCOL (`surf.pool4`) | Perform the same check for its displayed data, including flow/counter consistency where applicable. Audit first; repair demonstrated defects in a separately claimed scope. |

Work's split is a presentation change over the existing `surf_work` payload. Keep workflow
entries in the upper widget and job/step entries in the lower widget; do not silently introduce
a workflow-selection filter for JOBS. Use stable IDs for restoring focus/selection after refresh.
The implementer confirms treatment of project/context branches before editing. No additional
data reader or duplicate polling follows from adding the second widget.

## Frozen source semantics

The current token contract in `data/swarm_tokens_models.py` contains `volume_24h`, not lifetime
volume. `SwarmTokensMarketClient.fetch_markets` reads DexScreener `volume.h24`; the existing
Gecko candle readers cover a 24-hour window. `analytics/swarm_tokens.py` applies common
chain/query/LP filters and sorts known 24h volume descending. None of those facts establishes
all-time traded volume.

Two meanings were checked with different costs:

1. **Lifetime USD volume:** requires a verified source covering each eligible token's full
   trading lifetime and an explicit pool/universe policy. A truncated trade feed, overlapping
   24h snapshots, recent candles or market cap cannot supply it. The owner did not choose this.
2. **Every launch age, ranked by 24h USD volume:** existing canonical token rows support this
   without new reads. **The owner chose this interpretation.** The title/column discloses 24h.

Use the minimal widget contract **`TopTraded(tokens)`**, consuming existing filtered token
rows and ranking independent copies by fresh known `volume_24h` descending; stable token IDs
break ties. A known zero remains eligible, a missing value cannot become zero. Include old
launches; no last-24h launch-age filter. Show seven rows with TOKEN / CHAIN / USD/24H columns.
The panel explicitly says 24H. This requires a widget
signature change, not a new snapshot/projection key or read. Preserve chain/query/LP filters
and existing token-detail navigation. Do not overload `activity` event fields with token rows.
Model declarations and composing screen changes remain root-owned.

The Pool4 audit remains independent of this source decision. The data worker inventories the
actual mounted panels and traces each displayed field to its existing read. Check chain,
contract/pool identity, decimals/units, numerator/denominator, time window, coverage, cache
freshness and missing-versus-zero behavior. Reconcile related totals against independent
available facts where possible; report gaps rather than converting successful HTTP responses
into a correctness claim. No new paid/keyed provider, speculative RPC or history indexer.

## Ownership and sequence

| Package / owner | Files and responsibility | Dependencies |
| --- | --- | --- |
| WP1 — `cr_agent_946` | Only claimed Work/Oracle widget files (`widgets/surf/work.py`, `widgets/surf/oracles.py`) and their widget tests. Split Work widgets and adjust local layout; preserve interactions. | Send the exact shared screen/theme selectors and geometry needs to root. Existing `surf_work` / `surf_oracles` payloads stay unchanged unless an unavoidable seam is reported first. |
| WP2 — root | BOARDROOM widget/screen and token analytics, manager, model, widget/screen files it claims; corresponding tests and CR catalogue labels. | Token contract is frozen as `TopTraded(tokens)` with 24h volume across all launch ages. Root can delegate a disjoint widget/test file explicitly while retaining shared screen/model ownership. |
| WP3 — `cr_data_946`, read-only first | Pool4 source-to-display audit with concrete file/field evidence and focused verification. No production ownership granted by the audit. | Root assigns any demonstrated fixes and tests after findings; root keeps shared manager/models ownership. |
| WP4 — root, integration last | `screens/surf.py`, `data/surf_manager.py`, model declarations, `themes/minimal.tcss`, shared loading/other helpers if needed. | Apply agreed seams once; ensure screen DEFAULT_CSS and theme parity, then live composition. |
| Plan — architect | This file only. | Incorporate factual findings/contract decisions; no production edits or subagents. |

WP1, independent WP2 changes and WP3 may run concurrently in their owned files. Changes to
shared files are sent to root, not patched by several workers. Preserve all other edits.

Initial estimate is **450–850 changed production lines** for the bounded UI/projection work
and small demonstrated Pool4 fixes, reusing existing data and loading machinery. The clarified
ranking requires no new history system. If the Pool4 audit finds a structural defect that
would push the whole round past ~1,000 lines, resize/replan before widening that fix. Within
the current bound, use **one final review only**, no package reviews.

## Focused checks and live gate

- Work: `tests/widgets/test_surf_work.py`, composing `tests/screens/test_surf_work_screen.py`,
  then `tests/screens/test_surf_work_layout.py`. Assert upper WORKFLOWS is smaller than lower
  JOBS at 149×45, both scroll, neither duplicates/discards its population, and selection/filter
  state survives refresh. Regress text selection versus disclosure and keyboard focus transfer.
- Oracle: `tests/widgets/test_surf_oracles.py`, `tests/screens/test_surf_oracles_screen.py`,
  then `tests/screens/test_surf_oracles_layout.py`. Assert the request/detail width transfer
  and that titles, measured columns and selected detail remain usable.
- BOARDROOM: `tests/widgets/test_surfboard_rack.py`, `tests/screens/test_surfboard_screen.py`
  and `tests/screens/test_surfboard_layout.py`. Inspect composited title centering, both hints,
  equal neighboring gaps where space permits, and unchanged card/terminal rectangles.
- Tokens: `tests/analytics/test_swarm_tokens.py`, `tests/widgets/test_swarm_tokens.py`,
  `tests/screens/test_swarm_tokens.py` and relevant manager/market tests. Include eight eligible
  launches (seven displayed, totals still eight), zero/missing volumes, ties/filtering, absent
  unknown marker with rows retained, conditional legend blank row, loading start/end/failure,
  and retained data during background reads. Prove the ranking's stated time window.
- Pool4: worker names the test per demonstrated finding. Existing composing owners are
  `tests/screens/test_surf_pool4_screen.py` and `test_surf_pool4_market_screen.py`, with relevant
  `tests/data/test_surf_pool4*.py`, `test_surf_manager_pool4*.py` and depth/hero tests selected
  by the touched calculation. Use committed fixtures/injected clocks and transports; no test
  network or clipboard access.

Root shows **real keyless live renders at the owner's 149×45 terminal before hardening**.
Apply owner corrections before pin sweeps, `#:` changes, completion documentation or review.
Potentially affected pins are `SURF_WORK_FULL_LAYOUT_{COLUMNS,ROWS}`,
`SURF_ORACLES_FULL_LAYOUT_{COLUMNS,ROWS}`, `SURFBOARD_FULL_LAYOUT_{COLUMNS,ROWS}` and
`SWARM_TOKENS_FULL_LAYOUT_{COLUMNS,ROWS}`. Pool4 pins change only if a demonstrated fix changes
painted geometry. Measure affected boundaries in situ under both CSS variants; never derive
one pin from another. Use required mutation proof for changed pins/decoding/concurrency.

Use failing focused tests before implementation. Root runs touched and composing files once
precommit, fast non-mounting guards and required doc pins; no full suite. One final review,
one integrated fix wave and a scoped re-review only if production fixes require it. Record
minor residuals in the existing follow-up mechanism. Close the batch only after verification
and a real commit, with audit limitations honestly included in the validation evidence.

## Implementation record

Actual delegation after the frozen plan: `cr_plan` implemented the Token widgets,
screen, WIDGET_SIGNATURES addition and the isolated token stylesheet selectors;
Portfolio keeps its inherited presentation through two explicit overrides.
`cr_data_946` owned the POOL4 client/manager and associated data tests after the
audit established defects. Root retained the shared Surf screen, BOARDROOM,
composing layout tests, CR target labels and integration.

Live 149×45 renders were shown for BOARDROOM, WORK, ORACLES, SWARM TOKENS,
POOL4 MARKET and PROTOCOL before hardening/review. Boundary measurements retain
BOARDROOM 143×37, WORK 138×30, ORACLES 143×42; the Token boundary tests retain
146×34. No new data source, signing path or background worker was introduced.
POOL4 adds one bounded batch of two public block-header reads per due source
refresh. Detailed source verification is in `cr-round-89249bf6-pool4-audit.md`.

The UI/composing run finished with 368 passed and nine existing Portfolio
failures. All nine reproduce with the baseline Portfolio module: its unchanged
PortfolioHero calls a removed render_box method. The Token/Portfolio formatting
compatibility regression passes. This separate defect is recorded in follow-ups.
The POOL4 data/composing run finished with 762 passed and five existing failures:
older launchpad hero/binding/body expectations and the staker clipping fixture.
All five reproduce with the baseline Surf screen; no data regression failed.

Final review found two WORK interaction defects: a visible job could bypass its
blocked workflow's filter, and returning by mouse to the other tree's unchanged
cursor left the previous detail selected. Both have failing-before regression
tests and one focused fix wave. The shared ClickSelectTree is unchanged; WORK
explicitly re-highlights a repeated label click and respects blocked workflow
status before linked-job visibility. Scoped re-review marked both findings
ADDRESSED and approved the change; three regression cases passed and both fix
mutations were independently killed and restored.

Final WORK widget/composing/layout and BOARDROOM rack run: **144 passed**.
Fast guards: **128 passed**; documentation pins: **12 passed**. Across development,
16 implementation mutations and five independent review mutations were killed
and restored. The earlier broad UI/POOL4 runs retain the 14 proven baseline
failures described above. No full repository suite ran. No remaining review
findings; the data audit's limits remain explicit follow-ups. IMDB capture
recorded `none`: no new swarm-protocol lesson was established by these UI and
calculation repairs.
