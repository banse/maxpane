# WALLET / SWARM — live Boardroom integration

Date: 2026-10-26. Status: implementation authorized by **“ja so umsetzen”**.
Visual reference: the approved A/B demo at `dc94e8e9`, including one hero row,
mixed widgets and the Agent rack's `▰` / `▱` meters. This PRD supersedes the
demo-only delivery boundary for the production integration; the standalone
demo remains a reference and must never supply fallback live values.

## Purpose and scope

Show the selected public wallet's use of the Swarm: requests, their execution
results, proven payments/refunds, and delivered sites, contracts and tokens.
The owner's decisions remain **“A als Startansicht, B als Artefakt-Detailmodus”**,
**“nur onchain nutzung”**, and exclusion of its agents and trading. The AGENT
view contributes presentation only. No seat work, effort, rank, agent rewards,
portfolio holdings, swaps, prices, P/L or LP/staking analysis belongs here.

This is a nested Python/Textual screen in MaxPane, not a website or a new
top-level dashboard. The generic PM files `ai/memory-bank/site-setup.md` and
`ai/agents/pm.md` are absent. `CLAUDE.md`, the selected visual design and this
document govern implementation. No additional framework is required.

## Entry and interaction

- BOARDROOM `u` opens WALLET / SWARM. While its terminal input has focus, `u`
  remains literal input. The selected seat's owner is never the wallet seed.
- Seed from Boardroom's existing wallet (CLI/environment/saved configuration).
  With no wallet, show an empty identity state and offer the existing wallet
  input. Inside the view, `w` changes wallet and `r` uses the shared refresh
  lifecycle. Cancelling the input leaves the current identity unchanged.
- A is the initial overview. Enter on CREATED opens B at that artifact's stable
  identity. Arrows in B change the selected artifact coherently. Escape returns
  B to A, then A to BOARDROOM. Tab traverses local focusable panes.
- Retain selection and sensible scroll position for the same wallet. A wallet
  change immediately clears old identity data and selection; a late response
  for the previous wallet must not repaint any part of the new view. Reopening
  uses the most recently selected wallet rather than an earlier Boardroom seed.

## Approved presentation

A retains six nine-row heroes: REQUESTS, JOBS, WORKFLOWS, LAUNCHES, ORACLES and
SCHEDULES. Secondary facts appear in scoped footers: sites, contract/token
subset, in-flight requests, payments and follow-ups. All values are derived
from current evidence; fictional counts and fixed timestamps disappear.

Below the cards, show observed request activity as a sparkline, exclusive
request-status bars, contract usage/coverage meters and a payment breakdown.
Use the Agent rack meter renderer. CREATED occupies approximately two thirds
of the next row beside the selected relationship diagram and open follow-ups;
RECORD remains compact beneath it. Follow-up flags are a separate projection,
not an extra additive request-status bucket. Unknown execution state stays
unknown rather than being placed among completed requests.

B retains six heroes (REQUESTS, SITES, CONTRACTS, TOKENS, PAID, ATTENTION), the
artifact list on the left, selected evidence on the right and the payment
widget below the list. Details include identity, request/project links,
deployment/version, rule, observation window, coverage and evidence links.

The target is 149×45 with one complete card row and readable widgets. Narrow
terminals scroll and recover on resize; they must not hide cards or evidence
to satisfy a pin. Read-only real renders are shown before layout hardening.
Measure production geometry; the demo's minimum dimensions are not a pin.

## Data populations and provenance

Orders and their summaries use a visible 30D observation scope. Artifact
inventory is ALL KNOWN outputs attributed to those wallet orders and retained
proven results; it is not a claim to complete lifetime discovery. Utility
signals cover 24H / ALL ACTORS, independently of the paying wallet's actions.
Each source retains its own observed time, chain/block identity and coverage.

| Population | Required identity and interpretation |
|---|---|
| Requests | Public order ID; distinguish new jobs, continuations, workflows, launches, oracle requests and schedule actions. A job serving an oracle/workflow is a linked result, not another paid action. |
| Schedules | Owner-filtered schedules are owned standing orders. Foreign schedule top-ups remain payer actions; they do not transfer ownership. Automatic runs are linked execution context, not direct wallet requests. |
| Sites | Proven project identity; new versions/CIDs do not create another site. Use the recorded canonical URL, never invent a hostname. |
| Contracts | Confirmed `(chain_id, address)` deployments tied through explicit order/job/launch evidence. Name or objective similarity is insufficient. |
| Tokens | Verified token subset of the contracts, counted once in the inventory and contract denominator. A token-shaped name is not classification evidence. |
| Payments | Confirmed payment evidence grouped by chain and asset. Amounts and refunds remain separate; gas and passive rewards are excluded. |

The public paid-by endpoint was probed for the configured wallet on 2026-10-26:
five admitted orders were returned. Its payment objects contain confirmation
status, transaction hash and reason, but no amount, chain or asset. This is a
source-shape observation, not a permanent expected count. A current quote price
must never fill those missing fields. Monetary totals require receipt/event
attribution and a live decimals read; ambiguous or absent evidence stays unknown.
Missing refund coverage is not zero refunds, and prevents a complete net-paid
claim. Different chains/assets are not silently combined into one IMD number.

## Public sources and limits

The [official reference](https://imd.fun/docs/llms.txt) was freshly downloaded
for this task. Public sources are read-only and keyless:

| Source | Use and boundary |
|---|---|
| `/requests/paid-by/:wallet` | Observed paid/attempted orders, newest first, at most 100. No pagination or complete lifetime promise. |
| Job/workflow/launch/oracle detail | Existing `SwarmClient` readers; follow validated explicit result IDs. A launch result first names a job; the job can name its launch. |
| `/schedules?owner=:wallet` | Creation-time pagination. Detail supplies at most 50 recent runs. Preserve cursor/coverage if a bounded refresh stops early. |
| Site/project/publication links | Prove output relationships and versions. Global listings and text matches do not prove payer attribution or a site's configured contract. |
| Receipts, code and reviewed event rules | Confirm deployments, payment evidence and supported non-trading utility on Ethereum, Base and RH. Chain capabilities are measured independently. |

`GET /requests/:id` requires the paid request token and is excluded. No token,
signature, private key, quote, submit, import, transaction or signing surface
is introduced. Runtime ABIs/rules are local reviewed artifacts, not arbitrary
remote instructions. A source URL is not permission to fetch arbitrary hosts.

## Onchain usage rules

A usage rule must bind a reviewed application interpretation to chain,
deployment identity and runtime code/version. Count only successful canonical
application events or equally specific evidence. Deployment, approvals,
generic transfers, holder growth, swaps and HTTP/site traffic are not utility.
Tokens require a proved consumer relationship where utility happens elsewhere.

- Positive verified evidence may show ACTIVE; an incomplete window is a lower
  bound and remains visibly incomplete.
- QUIET requires a supported rule and a complete valid zero-event window.
- Unsupported rules, incomplete zero windows or failed reads remain NO DATA.
- FIRST SEEN, if supported, means first observed since a stated tracking start,
  never first-ever use without complete historical evidence.
- A site's explicit binding may mirror LINKED ACTIVE/QUIET; it adds no event
  or contract to aggregates and cannot prove use through that frontend.
- NO ONCHAIN LINK requires checked absence. Unresolved mapping remains unknown.

BurnTracker is a candidate first application adapter because its public result
names a deployment and Ordered/Updated semantics. Its actual deployed code,
event interpretation and receipt/window evidence must be verified before it is
enabled. Unsupported artifacts remain inspectable with unknown usage; they do
not borrow a generic transfer counter. This integration does not promise a
universal utility decoder or Base/RH archive capability not yet established.

## Loading and implementation boundaries

All overview facts hydrate when the view opens, without visiting B or another
dashboard. Reuse the retained child-manager and `SurfDashboardScreen` lifecycle.
The parent owns child closure; a child must not close borrowed shared clients.
Use per-source freshness/backoff, bounded parallel reads and fair continuation
of unfinished enrichment so older rows are not permanently starved.

Retain last observed values only for the same identity. Failed reads are None,
not zero; never put failure sentinels into activity series. Apply the existing
blank central-readout/card fallback rules and shared loading footer. Coverage
describes what was observed; it is not a generated per-card loading notice.

Use shared address/copy/explorer helpers, with chain-aware links and no guessed
explorer for an unknown chain. Treat every served string and persisted value
as untrusted input. The production renderer must not import fixture generation
or read from the standalone demo.

## Acceptance

The integrated view is reachable from BOARDROOM, reads the configured wallet,
supports identity-safe wallet changes and refresh, preserves A/B navigation,
and reproduces the approved composition with actual evidence. Tests run fully
offline with captured fixtures and raising transports. Live read-only proof
covers initial hydration, both views and source coverage at 149×45. Unknown
usage or amounts are a supported evidence state, not an implementation success
claim for an absent adapter. Root records actual adapter coverage, checks,
layout measurements and remaining source limitations in the implementation plan.
