# SURF NFTs — approved combined design

The owner selected the Collection Explorer layout, IDMD/mint filters and explicit
source details. This document makes that combination concrete for implementation.
Source findings: [surf_nft_game_mechanics.md](surf_nft_game_mechanics.md).

Implemented and reviewed on 2026-10-17. Live coverage, measured layout,
verification and remaining source limits: [delivery evidence](surf_nft_followups.md).

## Purpose and scope

Show which NFT collections the IMD swarm has deployed, what their checked mint
and utility rules establish, and the projects still being built. Connect a
collection to its exact contracts, jobs, published sites and reviewed source.
Adapt aidude's scanner logic into MaxPane; a viewer that only depends on a local
aidude output file does not satisfy the live data requirement.

Python >=3.11, existing Textual/Rich/httpx dependencies, strictly keyless and
read-only. No wallet connection, signing, paid IMD actions, private worker config,
new backend service, or new dependency. Current Surf palette, typography, shared
panels, filters and copy/explorer helpers apply. Target terminal: 149 columns by
45 rows. Pins must be measured after the real render, not copied from the ASCII.

## Screen and BOARDROOM

Dedicated `SurfNftScreen` pushed from the existing SURFBOARD hub, like TOKENS.
There is no tenth game-menu entry. Six native nine-row rack heroes appear first:
COLLECTIONS, IN THE MAKING, MINT OPEN, IDMD FREE, CONDITIONAL, CHAINS.

Below them: a compact filter summary and Launched / In the making stage controls;
a collection table on the left and a scrollable selected-collection detail on
the right. Standard panels are borderless and keep the shared title margin.
At 149x45, identity, chain, mint state, IDMD status and minted/max columns must
remain legible alongside the selected detail. Narrow terminals scroll or expose
honest widen/taller indicators; no required value silently disappears.

Table columns: collection, chain, mint state, IDMD benefit, minted/max. Distinct
contracts with the same name remain separate rows. Names can be shortened in a
table but their full values and identity remain available in selected detail.
Launched is the default stage; in-the-making projects do not become collections
merely because a job completed. Empty filters show a real empty state.

Selected detail contains:

1. Name/symbol, exact chain, standard, contract copy/explorer and deployment facts.
2. Each mint route with its own state, price/currency, window, limits and conditions;
   unknown price is `--`, known zero stays zero. Gas is additional.
3. IDMD benefit and its conditions, with the explicit distinction that personal
   wallet eligibility is not checked. Snapshot/voucher/activity gates remain named.
4. Minted, live supply, maximum and holder estimate independently where available.
5. Utility with deployed/implemented/planned/inferred status, plus related token
   roles and their checked chain/address/metadata. No-code dependencies are not
   shown as usable payment assets.
6. Explicit related Swarm jobs, website/IPFS links, repositories and pinned commits,
   deployment/rule evidence, observed block/time and coverage notes. Long evidence
   scrolls inside the detail area; user-supplied links/text are sanitized.

The BOARDROOM NFT card occupies the current PROTOCOL slot at row 2, column 1,
under ONCHAIN FEED. It uses the existing card renderer and tall numeric style:
headline COLLECTIONS, observed deployed count, supporting in-the-making and mint
open counts. Zero requires a successful discovery result; unread counts use dashes.
Partial coverage is qualified. The card always summarizes the unfiltered catalog.
Keep the rack's six columns, center terminal and other cards in their places.

## Navigation, selection and filters

- Card click/Enter or hub `n` opens NFTs; hub `p` opens the existing PROTOCOL view.
  Keep SURF's `e` protocol binding and the actual protocol data path.
- Printable `n`/`p` remain normal text while terminal/seat inputs are focused.
  Do not use priority shortcuts that steal input.
- `Esc` cancels an open filter editor first, otherwise returns to the retained hub
  with its draft, focus and scroll state. `Tab` traverses controls within NFTs.
- `f` opens the existing `FilterEditorBase` pattern; `/` opens it with search
  focused. Apply/reset/cancel behavior matches the existing local editor.
- Filters: chain (all/Ethereum/Robinhood), stage, mint state/route availability,
  IDMD benefit (all/yes/conditional/no/unknown), utility kind and search.
  Utility matches retain their evidence status; an inferred feature does not
  become verified by appearing in filter results.
- Search covers name/symbol, exact contract and source job/project identity.
  Sort supports newest and name, without ranking unlike payment assets by price.
- Keep selection by immutable identity through refresh/sort/filter when visible;
  otherwise select the first visible row or clear detail when empty.
- Row movement updates detail from the current snapshot. Enter focuses that detail
  for its links and long sources. It does not perform a mint or open an arbitrary
  URL automatically. A→B→A selection cannot display B's late response as A.
- Filtering/sorting/repainting uses `get_snapshot()` and pure projection. It must
  not start network work. Selection marks enrichment priority for the next bounded
  scheduled offer, without awaiting HTTP in event handlers.

Apply chain/search/utility/IDMD/mint filters to the common result set and heroes.
Stage selects the visible table within that set, so the deployed/build hero
counts remain useful when switching stages. Scope is visible in the filter
summary; the hub card remains global. Mint-open means a checked collection-level
mint classification, not a personal successful claim simulation.

## Data contract and correctness

Freeze primitive payload keys in `data/surf_nft_models.py` before parallel work:
`nft_rows`, `nft_build_rows`, `nft_summary`, `nft_selected`, `nft_sources`,
`nft_coverage`, `as_of`, plus each widget's declared signature.
Deployed identities are chain ID plus normalized contract address. Build
identities include chain/project identity. The plan defines exact nested fields.

`SurfNftManager(*, swarm, client=None, cache=None, cache_path=None, clock,
monotonic)` borrows the existing SwarmClient job memo and owns only its NFT
transports/tasks/cache. Its public seams are `fetch_and_compute()`, synchronous
`get_snapshot()`, `select(identity)`, `offer_hub()`, `catalogue_summary()`,
`is_loading(view=None)`, `wait_pending()` and `close()`. SurfManager retains and
closes one instance. The global dashboard registry remains unchanged.

Preserve scanner semantics for all existing reviewed mint/utility adapters,
factory children, constructor evidence, special dependencies and item counters.
Shared source rules/JSON are package resources with recorded source-file hashes;
there is no runtime import from another checkout. Source aidude has no Git HEAD
or scanner license declaration; do not invent either in provenance metadata.

Validate actual chain, bytecode, ERC-165 and matching receipt. Maintain the
distinction between IMD-attributed deployment addresses and independent child
creation evidence. Bind every reviewed rule to exact chain/address/runtime hash;
invalid/missing proof cannot retain a fresh verified rule interpretation.
Unreviewed but verified NFT deployments remain visible with unknown mint terms.
Never promote a referenced external NFT to an IMD deployment by name or mention.

Missing/failed reads are `None`; valid zero is retained. Do not assume token
decimals, convert FDV to market cap, invent floor/volume/APY, or sum holder
estimates into unique holders. No stale data is presented as newly observed.
Continue the current Surf display rule: neutral missing values and source times,
no added stale/failure banners; factual partial coverage and operational states
remain visible.

## Loading and resource limits

Empty-cache operation discovers live data independently of aidude. A saved
catalog may be explicitly imported as initial evidence or used for fixtures;
it is not a mandatory local path or a bundled live dataset. Preserve its scan,
chain and generation clocks separately. Cached data renders before any await.

Use incremental persisted discovery for launches, jobs, workflows and publications;
sites supplement older explicit publication/project relationships. Bounded NFT
searches and full linked job details supplement truncated list previews. Reuse
`read_job_detail` rather than a second job cache. Head refresh and history cursors
are separate, and a failed/non-progressing page cannot advance completeness.

Initial resource guardrails, not measured performance claims:

- At most 24 HTTP-attempt credits and 256 logical RPC calls per offered batch;
  JSON-RPC batches contain at most 32 read-only operations.
- At most four discovery pages and eight shared detail admissions per batch,
  additionally constrained by the total credits; four tasks overall, two per host.
- A shared detail admission reserves the current client's two-host attempt upper
  bound. Cache hits/inflight joins may cost less. Reserved credits and observed
  attempts are distinct counters, never represented as interchangeable.
- Reserve work for selected-collection enrichment independently of history
  backlog. Honor cancellation, provider pacing and 429 cooldown/Retry-After.
- Large scans proceed by saved cursors and pinned-block stages; exhausting a
  budget pauses work, rather than restarting the entire inspection each cycle.
  Factory/item limits start at 256 and are disclosed when coverage is incomplete.
- Start a fresh block context for a new observation, retain its timestamp through
  all resumed stages, and never mix blocks into a verified rule evaluation.
  An unavailable abandoned block restarts that candidate without replacing
  last-good facts with a failed read.

Normal screen polling follows the existing 30-second convention; it only offers
due work. Detailed TTL/backoff/cache limits are frozen in the implementation plan.
No complete CLI scan, synchronous urllib call, website HEAD sweep or all-history
RPC log scan runs on opening the screen. All network paths, including special
factory/item helpers, pass through the owned transport and budget.

## Acceptance

1. Captured fixtures reproduce existing reviewed source behavior and exact
   collection identities; wrong-chain/hash/receipt and unrelated references fail.
2. Independent cold discovery, resumed history, partial failures and cache restart
   work offline under injected transport/clock. Progress under repeated bounded
   batches is proved, including special adapters and shared detail requests.
3. Navigation/filter/selection tests prove no incidental HTTP, retained selection,
   safe shutdown, input typing and correct PROTOCOL return behavior.
4. An actual keyless live 149×45 render is shown before visible-change review and
   layout hardening. Saved fixture renders are not described as live acceptance.
5. Composite layout/address sweeps, decoder/concurrency mutations, affected
   whole-file/composing tests and fast guards run per CLAUDE.md. Registration
   mount checks run for the changed bindings. No full suite without owner request.
6. Task reviews follow ownership boundaries; final whole-change review has one
   final fix wave and one scoped re-review. Existing unrelated baseline failures
   remain explicitly distinguished. No UI speedup is claimed without measurement.
