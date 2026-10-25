# WALLET / SWARM — selected A/B mockup PRD

Date: 2026-10-25. Stage: **isolated Textual DEMO**, before live integration.
The owner selected: **“A als Startansicht, B als Artefakt-Detailmodus.”**
This document fixes the selected preview; proposal C is not implemented.
Revision 2 follows the owner's rendered-preview feedback: **“space should be
used more efficiently, and more widgets, not just cards and tables, only 1 row
of cards.”** Secondary totals move into card footers and compact widgets.

## Goal and authority

Show one wallet's Swarm requests, payments and delivered sites, contracts and
tokens, then inspect the onchain usage of one selected artifact. The owner
explicitly excluded agent details and trading and required **“nur onchain
nutzung.”** The AGENT view supplies visual style only.

Authoritative inputs are `surf_wallet_game_mechanics.md`, the A/B sections of
`surf_wallet_ascii_mockups.md`, the owner's selection and `CLAUDE.md`. The generic
PM files `ai/memory-bank/site-setup.md` and `ai/agents/pm.md` are absent. This is
Python/Textual with Rich, not a website or a Laravel/Livewire implementation.

## Deliverable and boundaries

One standalone `scripts/surf_wallet_demo.py` runs interactively or exports SVG.
All content is deterministic fictional data with fixed timestamps. Both modes
show **DEMO DATA** and state that no API is connected. No real wallet data,
network, configuration/cache persistence, browser launch or clipboard access.

Reuse the existing matrix theme and unchanged `HeroRecord` / `NewsHeroCard`.
Demo-local composition and helpers are allowed. No production screen, registry,
shared widget, theme, source, manager, contract-key or layout-pin changes. No
additional dependencies. A Boardroom entry point is future integration work.

## A — start view

At 149 columns × 45 rows, show **one row of six nine-row rack cards**:
REQUESTS 84, JOBS 42, WORKFLOWS 12, LAUNCHES 8, ORACLES 16 and SCHEDULES 6.
Keep the existing dark inset, neutral frame, green digits and clear units.
There is no second hero row. Its information remains visible in short card
footers and the widgets: 10 sites / 8 linked, 18 contracts including 4 tokens,
5 in flight, paid 62.5 IMD / refunded 1.0 IMD and 4 request follow-ups. A footer
must label its scope clearly; global counts are not outcomes of the card's
request category, and ALL KNOWN artifacts are not restricted to 30D orders.

A compact four-column insights band replaces the second row:

| Widget | Representation and acceptance |
|---|---|
| Request activity | Daily sparkline derived from the 84 orders in the fixed 30D window; visible period, count and a readable scale/context; no invented trend or live history |
| Request status | Labeled proportional bars from mutually exclusive request-state buckets; their counts reconcile to all 84 orders; follow-up flags are not an extra additive bucket |
| Onchain usage | Contract-identity signal and rule/window-coverage bars; count the 18 contracts once, including their 4-token subset; linked sites add no events or extra contracts |
| Payments | Paid and refunded amounts shown separately with a settlement bar for 78 settled / 6 unsettled attempts; amounts remain exact and are not a trading or performance metric |

Below, CREATED takes roughly two thirds of the width. It shows type, artifact
name, chain, compact onchain activity metric and signal. Its remaining third
shows a selected-artifact relationship diagram and the four named open request
follow-ups. The diagram follows the same selected ID as B and distinguishes a
linked site's contract evidence from use through its frontend. Unknown/static
cases explain the missing relationship without inventing a path.

All 28 artifacts remain reachable through internal scrolling. Preserve a compact
recent RECORD below this area. A visible count describes the displayed population
without summing sites, contracts and token subsets. Use the recovered space for
readable information, with no decorative empty panels or duplicate large totals.
Measure the final widget heights and column allocation in the compositor; the
target insights-band height is eight rows, not a production layout pin.

Scopes are explicit: orders 30D, assets ALL KNOWN, usage 24H / ALL ACTORS.
The mock may present these as fixed captions. It must not advertise unimplemented
search, filters, wallet switching, refresh or external-link actions as controls.

## B — artifact detail mode

One row of six nine-row cards: REQUESTS 84, SITES 10, CONTRACTS 18, TOKENS 4,
PAID 62.5 IMD, ATTENTION 4. Below it, the artifact list is on the left and the
selected artifact's details are on the right. The shared compact payments widget
replaces the plain request/payment paragraph beneath the list. The right pane
scrolls internally when needed. B keeps its existing single hero row; it does
not gain another row to accommodate the new overview widgets.

Details show artifact identity/type/chain; its own order and project/launch or
workflow relation; site version or deployed contract; usage rule and consumer
where applicable; unit, count, actor-address count, latest observation, tracking
start and window coverage; signal and evidence placeholders. All external
identifiers are explicit placeholders with DEMO evidence labels. Do not paint
real-looking `0x` addresses, clickable explorer destinations or browser/copy
controls. Evidence remains inline; no external action is part of this preview.

Site details qualify usage with LINKED and explain that activity of the linked
contract does not establish use through that frontend. Token details show utility
actions at a demonstrated consumer, not swaps, price, holder growth or generic
transfers. No seat, worker, contribution, effort, reward or ranking detail.

## Navigation and selection

- Start in A. Up/down selects by stable artifact ID, not by presentation index.
- Enter on CREATED opens B on that same artifact. B up/down selects another
  artifact and updates all details coherently.
- Escape from B returns to A with the current artifact selected. Restore the
  saved overview scroll where possible; if B moved outside that viewport, only
  scroll enough to reveal the selection. Do not jump to the first row.
- Escape from A or `q` exits the standalone demo. Tab follows a useful focus
  order between scrollable sections. The footer lists only working bindings.
- At 100×30, outer scrolling makes all cards and panels reachable; restore the
  full geometry and identity when resized back to 149×45. Do not shrink or drop
  hero cards to conceal overflow.

## Deterministic fixture contract

Use demo-local immutable records or plain primitives, with stable identities.
No production data-model module is needed. Summary values must derive from the
fixture population or a documented fixture fact, not from the visible row slice.

The implementation interface is `SurfWalletDemo(view='overview',
selected_id='site-atlas')`, `mock_snapshot()` returning a dict with full `orders`
and `artifacts`, `hero_records(snapshot, view)`, `usage_signal(artifact, by_id)`,
`usage_text(...)` and `export_demo(path, size, view, selected_id)`. All data types
remain local to the script. Mounted A/B grids use distinct widget ID prefixes
while sharing the selected artifact ID.

| Population | Required DEMO facts |
|---|---|
| Requests | 84 distinct orders: 32 job opens, 10 continuations, 12 workflows, 8 launches, 16 oracles, 2 schedule creates and 4 topups |
| Payments | 78 settled / 6 unsettled attempts; settled amounts total 62.5 IMD; separate linked refunds total 1.0 IMD |
| Outcomes | 10 delivered workflows, 6 deployed launch outcomes, 14 attested oracle answers; 5 in flight: 2 jobs, 1 workflow, 1 launch, 1 oracle |
| Attention | 4 distinct open request follow-ups: 2 blocked work items, 1 failed delivery, 1 paused owned schedule |
| Artifacts | 10 distinct site projects and 18 distinct contract identities, of which 4 are tokens: 28 list entries if each contract appears once under its most specific type |
| Linkage | 8 sites with proved mock contract bindings; include one explicitly static site and one unresolved mapping |
| Usage coverage | 6 contract identities have a mock verified rule, including 2 of 4 tokens; 4 of those 6 windows are complete |

Orders cover 2026-09-25 12:00 through 2026-10-25 12:00 UTC. Usage covers the
last 24 hours ending at the same fixed instant. Chain block boundaries are
explicit fictional evidence, not a claim that real blocks were read. Amounts
must retain exact arithmetic. Requests, artifacts and usage are separate units.

Required named cases:

| Artifact | Display and detail expectation |
|---|---|
| Atlas portal / Base | LINKED ACTIVE from Atlas Registry; same underlying evidence, not extra activity |
| Harbor portal / Ethereum | LINKED QUIET from Harbor Vault's complete zero-deposit window |
| Atlas Registry / Base | ACTIVE; 27 registrations / 9 actor addresses in 24h |
| Harbor Vault / Ethereum | QUIET; zero deposits from a complete valid-rule window |
| Harbor Credits / Base | FIRST SEEN; 4 redemptions / 3 actor addresses; first observed since tracking began 10-24 12:00, not first-ever use |
| Signal Access / RH | NO DATA; no verified usage rule, count stays unknown |
| Static site | NO ONCHAIN LINK after completed mapping review, no claim of nonuse |
| Incomplete history | NO DATA when no positive evidence exists; never synthesize zero or QUIET |

Include an incomplete positive case to preserve the ACTIVE lower-bound rule if
it can be represented without expanding scope. Do not invent a universal active-
user total; actor addresses are not humans and repeated site/contract evidence
does not create additional actions.

## CLI and exports

Support `--export PATH.svg`, `--size 149x45`, `--view overview|detail` and
`--select STABLE_ARTIFACT_ID`. Default view is overview. Reject invalid view,
size or selection clearly without falling back to another artifact. The selected
artifact must be visible in the requested export. With no export argument, run
the standalone app directly; no server or background process is needed.

## Acceptance boundary

The preview succeeds when A and B render coherently at 149×45 with only one
hero row each and no outer overflow, all named cases
are inspectable, navigation retains identity, narrow layouts remain reachable,
demo totals and visual distributions agree, and no external side effect occurs.
The new plots, bars, relationship diagram and follow-up list must be composited
and readable alongside CREATED and RECORD. Export and inspect both
views and the unknown/static-site cases. This certifies a fictional preview,
not live data completeness, production layout pins or deployment readiness.

Live API/RPC discovery, receipts, onchain signal adapters, Boardroom registration,
real wallet input, caching and refresh lifecycles are a later implementation
phase after feedback on this preview.
