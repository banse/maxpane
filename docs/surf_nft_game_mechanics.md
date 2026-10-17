# SURF NFTs — source inspection and design basis

Design research, 2026-10-17. The user requested three ASCII proposals before
implementation: an NFT overview based on aidude's scanner, plus an NFT card
replacing BOARDROOM's PROTOCOL card. PROTOCOL must remain accessible by key.
Approved visual direction: variant 1 (catalog and selected detail), with the
IDMD/mint filters from variant 2 and source details from variant 3. See
[the PRD](surf_nft_PRD.md) for the resulting requirements.
The adaptation is implemented; [delivery evidence](surf_nft_followups.md)
separates the live cold-start observations from the saved source examples below.

## Inspected source and saved evidence

Source checkout: `/Users/banse/codex/aidude`. Entry point: `bin/aid nft-scan`,
implemented by `tools/surf/nft-scan.py`. Its local documentation is
`docs/imd-nft-directory.md`. The generated website at
`data/surf/nft/site/index.html` presents `data/surf/nft/catalog.json`.
The scanner was not run for this inspection.

The inspected catalog was generated on **2026-10-16 at 22:46:23 UTC** by an
offline render. Its discovery snapshot is **21:22:16 UTC**; the displayed chain
observations are around **22:10 UTC**. Render time must not renew observations.
These are saved example values for the proposals, not current live readings:

| Metric | Saved value | Meaning |
|---|---:|---|
| Deployed collections | 20 | 15 Ethereum, 5 Robinhood |
| In the making | 3 | 2 Ethereum, 1 Robinhood; not deployed collections |
| Mint state `open` | 15 | Collection-level classification, not wallet eligibility |
| IDMD benefit `yes` | 3 | Confirmed class-level free route, subject to conditions |
| IDMD benefit `conditional` | 6 | Snapshot, activity, voucher or other conditions |
| Jobs / launches / workflows | 13,699 / 707 / 193 | Public records scanned |
| Publications | 3,978 of reported 3,979 | Coverage incomplete during pagination |

`coverage.complete` is false. Public-history completeness does not prove coverage
of private jobs, nonstandard NFTs or unsupported factories. Three identically
named BMC Illuminati Pass contracts demonstrate why name is not identity.

## Available data and required distinctions

| Data family | Available fields / design use | Source in `tools/surf/` |
|---|---|---|
| Collection | Chain, contract, name, symbol, ERC-721/1155, launch identity | `_nft_catalog.py:602` |
| Mint | Separate routes, states, prices/currency, start/end, limits and conditions; pinned read block/time | `_nft_rules.py:157` |
| IDMD benefit | `yes`, `conditional`, `no`, `unknown`, conditions and evidence | `_nft_rules.py:148` |
| Stats | Optional minted, live supply, maximum supply, holders and collection-specific counters | `_nft_chain.py:144`, `_nft_rules.py:193` |
| Utility | Summary and individual capabilities, with deployed/implemented/planned/inferred evidence status | `_nft_utility.py:72` |
| Related tokens | Payment/burn, reward, staking, eligibility/project roles; exact chain/address and live metadata | `_nft_utility.py:96`, `_nft_tokens.py:113` |
| Links | Explicitly joined jobs, websites, repositories/commits, deployments and source evidence | `_nft_catalog.py:363`, `_nft_links.py:115` |
| Builds | Stage, meaningful activity, accepted implementation and evidence | `_nft_catalog.py:187`, `:612` |
| Coverage | Index completeness, failed checks, references/factories and original observations | `_nft_catalog.py:671` |

Deployment identity is `(chain_id, contract_address)`; pending work uses a
chain/project identity. Only Ethereum mainnet (1) and Robinhood mainnet (4663)
are supported by this scanner. Exact chain, deployed bytecode, NFT interface and
receipt checks are separate from IMD's attribution of an address to a launch.
Factory-created children retain their additional creation evidence.

Reviewed mint adapters bind chain, address and runtime code hash. A mismatch
removes the verified interpretation. Reported objectives and inferred utility
hints must not acquire the same visual status as checked rules. An open public
route does not establish an open IDMD route; preserve `mint.routes[]`.

Zero mint payment excludes gas. Mandatory platform fees and token burns are not
free. A snapshot claim is not made eligible by acquiring IDMD today. The scanner
does not simulate individual wallets, so the dashboard must not say "you can
claim". Collection-level `IDMD free` counts need that explanation in details.

Ever minted, live supply and ERC-1155 quantities are different metrics. For
example, saved FarmItems has 114 minted, 110 live items and four burned. IMDenza
has five minted out of 3,333, but no known `totalSupply`. Holder counts may be
unavailable and are otherwise an unpinned explorer estimate. Do not sum them
into unique holders or silently substitute minted for live supply.

No reliable floor price, secondary sales volume, wallet NFT portfolio,
personalized eligibility or guaranteed rewards/APY comes from this tool.
Missing prices and statistics remain unknown. Token addresses without deployed
code remain distinct from usable payment assets, even when their symbol matches.

## Proposed MaxPane adaptation

Prefer a dedicated NFT screen reached from the existing SURFBOARD hub, using the
same screen-stack pattern as TOKENS. This can be a new overview without becoming
a tenth global dashboard or changing the game menu. The choice remains part of
the approved visual direction; the implementation plan defines file ownership
and source-reader integration.

- Replace the current PROTOCOL slot at rack row 2, column 1, under ONCHAIN FEED.
  At the known 149×45 terminal it is a 24-column, nine-row card. Preserve the
  six-column rack and center terminal geometry.
- Propose `n` for NFTs and `p` for PROTOCOL from the hub. Both are currently free
  there. Keep the existing SURF `e` protocol binding. Printable keys must keep
  working in the command terminal and seat inputs; shortcuts are non-priority.
- `Esc` returns from the NFT screen to the hub. Selection, sorting and filters
  use the existing cached snapshot; details expose job/site/contract links.
- Reuse the deterministic joins, classifications and reviewed rules. Adapt I/O
  to MaxPane clients, persisted cache, manager lifecycle and shared job memo.
  Do not shell out to a complete history scan on navigation, scrape the HTML,
  or depend on dynamic imports from another local checkout.
- A saved catalog is suitable for explicit initial import and fixture design.
  Runtime discovery and chain enrichment must have independent timestamps,
  bounded requests, incremental history and selected-collection priority.

The scanner is a batch tool: full indexes/searches can traverse up to 1,000
pages; HTTP cache is one hour, workers default six, and up to 64 getter probes
are sequential per candidate. Site checks are also serialized. There is no
total scan request/deadline budget. Those defaults must not become a TUI refresh
policy. A snapshot must render before enrichment finishes.

The proposed default is keyless local rendering and read-only public API/RPC
access, without wallet connection or signing. Accepted infrastructure compromise:
IMD discovery depends on its public service; cached evidence remains readable
during outages, but cannot establish exhaustive new discovery. RPC observations
retain their chain/block provenance. No new hosted service or analytics is needed.
Any copied source/rule tables need a recorded source revision and license check
when the implementation scope is approved.

## Three presentation directions

1. **Catalog and selected detail — recommended.** Six summary cards, searchable
   deployed-collection table, selected mint/utility/token details, and a separate
   in-the-making tab. Hub card leads with 20 deployed collections.
2. **Mint routes and IDMD benefits.** Lead with the three confirmed class-level
   IDMD benefits, separate six conditional benefits, and inspect mint routes and
   their requirements. Hub card leads with three IDMD-benefit collections.
3. **Swarm delivery and provenance.** Lead with the three projects in development,
   their job/source chains and the 20 deployed collections. Hub card leads with
   three projects in development. Deployment and mint availability stay separate.

All three use the existing rack, table, detail and link conventions. ASCII
proposals are schematic; their final layout requires a real 149×45 render and
measured sizing after selection. The partial-coverage note is factual coverage,
not a new visible source-failure banner.
