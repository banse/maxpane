# SWARM TOKENS mock dashboard

## Approved requirements

The owner requested a dashboard combining BASE TRADING, SURFBOARD launchpad and
the swarm LAUNCHES table, with "a NEWLY LAUNCHED widget and best plays and activity"
and a main table containing "liquidty info(especially if its one-sided or not)
and a sparkline for each token together will all other important info."
The owner selected version **1**, Market overview, and **all production chains,
with a chain filter**. This delivery is the mock Textual demo, before live APIs.

Stack: existing Python ≥3.11/Textual/Rich application. Use current SURFBOARD
dark theme tokens, shared panel bases and sparkline helpers. No new dependencies.
Target: 149×45. The top-level dashboard registry and CLI game list stay unchanged.

## Layout

The owner subsequently requested native MaxPane styling: standard panels have
no surrounding borders, and no title or filter controls appear above the hero
cards. This revises the initial boxed mock while retaining version 1's hierarchy.

```text
+ TOKENS --------+ + NEW / 24H -----+ + VOLUME / 24H --+ + LIQUIDITY ----+
| deployed count| | count / 24h    | | known USD sum  | | position mix  |
+---------------+ +----------------+ +----------------+ +---------------+
MOCK DATA / chain: All / LP: All / search: none / sort: volume

ALL TOKENS / filtered count
launch token chain age price 24h% mcap volume buys/sells paired LP
       LP state   per-token 24h sparkline   launch verdict
                         scrollable token rows

NEWLY LAUNCHED            BEST PLAYS                 ACTIVITY
age / token / chain      gainers and losers          time / kind
liquidity state          change / liquidity          token / amount

selected token summary / help                           MOCK DATA
```

The ASCII above groups the table fields for readability; actual tokens use one
table row each, as approved in the full version-1 preview. The main table owns
most available height. Supporting widgets remain visible at the target size.
Narrow/short terminals expose scrolling and `widen`/`taller` hints instead of
silently discarding required columns or changing to a different design.
Use native `HeroRow`/`HeroBoxBase` framing for the four top metrics. Standard
table and supporting panels use the existing unbordered `TableLeaderboard`,
`RichLogFeed` and `PanelBase` appearance. Place the mock notice, compact applied
filter summary and any overflow hints below the hero row.

Filter editing follows THE LIST and the SURFBOARD AGENT record editor: a
dashboard-owned `FilterEditorBase` subclass shows compact, titled controls in
the body, using its four-column layout and two-column compact form. Reuse the
local shared base, which matches `/Library/Vibes/autopull`'s original primitive;
do not import another checkout at runtime or create a competing control style.

## Content and interactions

- Four top metrics: deployed count, launches in 24h, known
  24h USD volume with coverage, and liquidity-state counts.
- Main table: launch ID, symbol, chain, age, USD price, 24h change, market cap,
  24h volume, buys/sells, paired asset amount/unit, LP state, per-token price
  sparkline, verdict. Unknowns are visibly distinct from zero.
- NEWLY LAUNCHED: newest matching launches from the last 24h, showing chain and
  liquidity state. Empty filters show an explicit empty state.
- BEST PLAYS: gainers and losers by known 24h change, with liquidity context.
  Exclude missing prices/changes; keep one-sided positions eligible and visible.
  The title is descriptive; no buy/sell recommendations or safety guarantees.
- ACTIVITY: matching synthetic trades, launches and LP events, newest first.
- Chain filter defaults to All, with Ethereum, Base and Robinhood choices.
  Search and LP-state filters apply consistently across table, metrics and
  supporting widgets. Sort allows volume and newest (additional numeric sorts
  may reuse the same small implementation).
- `f` opens the filter editor; `/` opens it with search focused. The existing
  chain, search, LP-state and sort fields are the complete filter set. Edits are
  drafts until **APPLY FILTER**; **RESET ALL** restores their default values.
  Escape cancels the draft and closes the editor without changing the applied
  result. Existing `c`/`o` chain/sort shortcuts operate only while the editor is
  closed, so typing in controls cannot accidentally change the dashboard.
- Preserve selected token identity through sorting and filter updates when it
  remains visible. Otherwise choose the first visible token; handle zero rows.
- Enter exposes selected-token detail within the demo. Unknown contract/pool
  links say not connected in mock; no fabricated explorer targets or inert copy icons.
- Escape returns to the existing hub when pushed from its SWARM TOKENS card;
  standalone Escape exits. An open filter editor consumes Escape first to
  cancel its draft; token details retain their own close-before-back behavior.
- The hub card clearly says demo/mock; future Portfolio and Earnings cards stay
  planned. No live polling label or fake refresh activity on this static demo.

## Offline launch and acceptance

Provide `python -m maxpane_dashboard.demos.swarm_tokens`, isolated from the
production startup manager and network prefetch. Opening from the hub must not
initiate a SWARM TOKENS network source. Refresh reloads the deterministic mock
snapshot rather than mutating prices or simulating live trading.

Acceptance requires an actual running mock-screen render at 149×45 before
layout hardening. This explicit mock-first request supersedes the usual live
render step for this phase. Then verify composited layout and interactions at
target size and smaller scrolling sizes, with no network or real clipboard use.
All screenshots and sample counters remain visibly marked MOCK DATA.
