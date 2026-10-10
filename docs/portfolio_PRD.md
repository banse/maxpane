# PORTFOLIO — approved design

Date: 2026-10-10. The owner selected ASCII option **1: Portfolio overview**,
replaced the LAUNCH LIQUIDITY hero with **P/L**, then approved the completed
149×45 Textual design ("design approved"). The layout and interactions below
are the implementation reference. The offline mock is complete; live integration
is implemented under
`portfolio_live_implementation_plan.md`. Numeric live P/L remains unavailable
without verified cost basis.

Owner revision, 2026-10-10: the table and HELD VALUE use positive wallet
holdings only. The portfolio table sits above the three supporting panels;
claim-only allocations stay in the CLAIMABLE panel and card.

## Requirements and scope

The owner requested a dashboard that lets the user "set a wallet (like in THE
LIST dashboard)" and shows "all tokens that were launched by the swarm and
are held by the set wallet", including "tokens that are claimable for
connected imd agents". Reuse "widgets from the BASE TRADING dashboard" and
"data fetching /enrichment from the SWARM TOKENS dashboard as much as
possible", including "IMD/ETH liquidity" and MaxPane styling.

Stack: existing Python ≥3.11, Textual and Rich; no new dependency. The SURFBOARD
PORTFOLIO card now opens the live dashboard, borrowing its
retained market provider and adding bounded wallet balance/claim readers.
`python -m maxpane_dashboard.demos.portfolio` remains the isolated offline preview.

## Approved layout

```text
HELD VALUE       CLAIMABLE       IMD AGENTS       P/L
known USD        ready USD       linked / online  USD / % unrealized

Wallet: selected wallet · chain / assets / filter context · source state / coverage

PORTFOLIO / matching held-token count
LAUNCH TOKEN CHAIN HELD CLAIMABLE HELD USD PRICE 24H % PAIRED LP PRICE 24H
                       full-width scrollable table
-----------------------------------------------------------------------

MARKET ACTIVITY                 CLAIMABLE                 MOVERS / 24H
held-token market feed         ready token allocations   held-token movers

w wallet · f filters · / search · Enter details · r refresh · Esc hub
```

The four native hero cards are first. Standard panels remain borderless and
use muted headings with their normal blank line, neutral values, green/red
price changes and yellow degraded states. Use existing theme tokens, panel
bases, amount formatters and 20-character price sparklines. Keep all columns
reachable at smaller sizes through scrolling and truthful widen/taller hints.
149×45 is the approved preview target. The completed mock measured a 145×35
minimum for its fixed chrome; smaller terminals retain access through scrolling.

## Data meaning

- A live row represents `(chain_id, token_address)`, never a symbol; launch
  aliases and distinct reward allocations remain separate provenance.
  The offline preview uses synthetic `chain:launch` identities.
  Table rows require a positive held quantity, including unpriced holdings
  and explicitly marked stale balances. Zero/unknown balances and claim-only
  tokens stay out of the table and HELD VALUE population; ready allocations
  still appear in CLAIMABLE and its value card. Synthetic records contain no invented token
  addresses or explorer targets. Live identity is chain + contract.
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
  to preview the design without inventing a wallet address. Only the standalone
  preview retains MOCK DATA, including after entering a real address.
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
- Shared filters select the held and claim populations. Table, HELD VALUE,
  liquidity, movers and market activity use held tokens; CLAIMABLE retains
  ready allocations, including claim-only tokens. Preserve selection identity
  when still visible. Wallet-wide source coverage survives both selections.
- Enter shows cached position and market detail. `r` reloads the same static
  snapshot in the offline preview; the hub refreshes live sources. Escape closes detail/editor first,
  then returns to the hub; standalone Escape exits.

## Acceptance

The approved offline preview and the subsequent keyless live dashboard were
rendered at 149×45 before their layout hardening and final review. No further
design approval is needed.

Verify target and smaller composited layouts, wallet set/cancel/switch, coherent
filters, empty and unavailable states, claim-only and unpriced rows, stale vs
zero, details and navigation. All Portfolio tests block network use. Reuse the
existing SWARM TOKENS projection/feed/movers/filter/detail/screen where sound
and the shared bases used by BASE TRADING; do not copy an entire dashboard.

Out of scope: signing, claim execution or other transactions, wallet history,
unbounded cost-basis acquisition and top-level dashboard registry changes.
Live P/L requires complete verified remaining-position basis and valuation;
otherwise its card explicitly reports unavailable. Source evidence and limits remain in
`portfolio_game_mechanics.md`.
