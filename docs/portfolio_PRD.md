# PORTFOLIO — approved offline mockup

Date: 2026-10-10. The owner selected ASCII option **1: Portfolio overview**.
This approves the Textual mockup at **149×45**, not live wallet integration.
Owner revision: replace the LAUNCH LIQUIDITY hero with **P/L**.

## Requirements and scope

The owner requested a dashboard that lets the user "set a wallet (like in THE
LIST dashboard)" and shows "all tokens that were launched by the swarm and
are held by the set wallet", including "tokens that are claimable for
connected imd agents". Reuse "widgets from the BASE TRADING dashboard" and
"data fetching /enrichment from the SWARM TOKENS dashboard as much as
possible", including "IMD/ETH liquidity" and MaxPane styling.

Stack: existing Python ≥3.11, Textual and Rich; no new dependency. The immediate
deliverable is a deterministic, offline preview opened from the existing
SURFBOARD PORTFOLIO card or `python -m maxpane_dashboard.demos.portfolio`.
The hub itself retains its existing sources; opening Portfolio adds no network
requests. Live catalogue/balance/claim readers are a later phase.

## Approved layout

```text
HELD VALUE       CLAIMABLE       IMD AGENTS       P/L
known USD        ready USD       linked / online  USD / % unrealized

Wallet: selected wallet · chain / assets / filter context · MOCK DATA

MARKET ACTIVITY                 CLAIMABLE                 MOVERS / 24H
matching token market feed     ready token allocations   gainers / losers

-----------------------------------------------------------------------
PORTFOLIO / matching token count
LAUNCH TOKEN CHAIN HELD CLAIMABLE HELD USD PRICE 24H % PAIRED LP PRICE 24H
                       full-width scrollable table

w wallet · f filters · / search · Enter details · r refresh · Esc hub
```

The four native hero cards are first. Standard panels remain borderless and
use muted headings with their normal blank line, neutral values, green/red
price changes and yellow degraded states. Use existing theme tokens, panel
bases, amount formatters and 20-character price sparklines. Keep all columns
reachable at smaller sizes through scrolling and truthful widen/taller hints.
149×45 is the preview target; no layout minimum is claimed before measurement.

## Data meaning

- A row represents one synthetic `chain:launch` identity, never a symbol.
  Include a positive held quantity **or** a positive ready claim, including
  claim-only and unpriced tokens. Synthetic records contain no invented token
  addresses or explorer targets. Live identity will require chain + contract.
- HELD VALUE and CLAIMABLE show separate indicative USD sums. Missing/stale
  quantity or price does not enter the known sum; show coverage and partial
  state. Zero is a successful zero, `None` is unknown, and cached stale values
  must be visibly stale. Neither valuation is a liquidation quote or P/L.
- P/L is unrealized gain/loss on the filtered held positions: current held USD
  minus their remaining-position USD cost basis, with percentage over that
  basis. Ready claims and realized gains are excluded. Any missing/stale held
  valuation or missing cost basis makes P/L unavailable; a zero basis has no
  percentage. Positive is green, negative red, zero neutral. The offline sample
  has an explicitly synthetic $3,300 basis and $3,500 value: +$200 / +6.1%.
- Claims reflect wallet entitlement. An agent going offline does not remove
  that entitlement. Locked/claimed amounts remain in cached detail and never
  enter ready totals. Current agent association and online counts are explicitly
  wallet-wide, independent of token filters; no invented per-agent allocation.
- PAIRED LP and token detail describe launch positions, separate from holdings.
  Count each mock token's single position once in the filtered population;
  reuse SWARM TOKENS' IMD/ETH aggregation, partial markers and LP formatting.
  Details retain one-sided/withdrawn state. Never combine IMD and ETH units.
- MARKET ACTIVITY reuses matching token market events; it is not wallet history.
  MOVERS / 24H reuses known current market changes. Charts are token price
  history, never fabricated historical portfolio values.

## Wallet and controls

- The hub uses the existing saved/environment wallet or shows "Set a wallet to
  view your portfolio." Standalone may start with the explicit label "sample"
  to preview the design without inventing a wallet address. Every view retains
  MOCK DATA, including after entering a real address.
- `w` reuses `WalletInputScreen`, validation and persistence. Its accepted
  callback address becomes the current screen/manager wallet immediately,
  overriding startup environment precedence for this session. Cancel preserves
  the previous wallet. Switching clears previous wallet rows before rendering
  the next snapshot; a mismatched snapshot cannot repaint the new wallet.
- Every displayed entered address uses shared address/copy/explorer helpers.
  The sample label carries no fake link or copy action. Tests never invoke the
  real clipboard or browser.
- `f` opens the shared draft filter editor; `/` focuses search. Chain, assets
  (all/held/claimable), LP state, search and sort apply together. Default is all
  chains, held-or-ready-claim assets and held-value descending. Unknown numeric
  values sort last. APPLY commits, RESET resets the draft, Escape cancels.
- One filtered token set drives the table, valuations, liquidity, claims,
  movers and market activity. Preserve selection identity when still visible.
- Enter shows cached position and market detail. `r` reloads the same static
  snapshot without simulated market changes. Escape closes detail/editor first,
  then returns to the hub; standalone Escape exits.

## Acceptance

Show an actual running offline Textual render at 149×45 before layout hardening
and final review. The owner's explicit mock-first workflow substitutes this
for the normal live render in this phase; no further design approval is needed.

Verify target and smaller composited layouts, wallet set/cancel/switch, coherent
filters, empty and unavailable states, claim-only and unpriced rows, stale vs
zero, details and navigation. All Portfolio tests block network use. Reuse the
existing SWARM TOKENS projection/feed/movers/filter/detail/screen where sound
and the shared bases used by BASE TRADING; do not copy an entire dashboard.

Out of scope: live reads, new polling/cache stacks, signing, claiming or other
transactions, wallet history, live cost-basis/PnL acquisition and top-level dashboard registry
changes. Source research and live-integration caveats remain in
`portfolio_game_mechanics.md`.
