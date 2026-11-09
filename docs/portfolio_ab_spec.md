# Swarm portfolio: overview A and popup B

Approved by the owner on 2026-11-09: design A is the dashboard; design B opens
as a popup in the same style as existing MaxPane popups. Target: 149 columns
by 45 rows. The ASCII figures were illustrative, not expected live values.

## Outcome and composition

The selected wallet can inspect its Swarm holdings, deposits, rewards, NFTs,
eligibility and token utilities across Ethereum, Base and Robinhood. This is
the discovered Swarm portfolio, not a census of every asset in the wallet.

The overview follows the approved A hierarchy:

1. Six rack cards: TOTAL VALUE, WALLET, STAKED, UNCLAIMED, NFTS and SEATS.
   The first four show estimated USD value. NFTs show collection/item counts;
   seats show actual identified IDMD seats, not a count of eligibility fields.
2. A current allocation bar for wallet, staked and unclaimed value; chain,
   search, value sort and show-no-sale controls.
3. Holdings beside unclaimed rewards; stakes/deposits beside token utilities.
4. NFT inventory, seats/eligibility and scan evidence below.

Holdings show token, chain, wallet amount, allocated value and token-sale
status. Rewards distinguish ready, locked, stake-pending and unknown readiness.
Stakes show principal value, separate pending rewards, estimated APR and its
method. Utility balances belong to the contract, not the user. Unbounded lists
scroll inside panels; smaller terminals keep all content reachable.

Selecting a token opens B as a `RecordDetailScreen` subclass: centered native
accent border, title, top-right X, scrollable content and pinned Space/Esc close
hint. A compact token inventory sits beside the selected token's detail, so B
retains its list/detail workspace inside the modal. It shows token identity,
its combined estimated value, wallet/staked/reward
amounts, sale coverage, pool evidence, connected contracts and source metadata.
Opening the popup takes a cached immutable snapshot and does not start network
reads. Closing restores overview focus and selection. Use the shared address,
copy and chain-explorer helpers throughout. Claims only link to their existing
explorer/project destinations; no signing, transactions or claim execution.

Navigation is Boardroom `o`, advertised as `o portfolio`. Existing `p` remains
Protocol. No Boardroom card replacement or top-level dashboard renumbering.
The overview uses `w` for the existing wallet prompt, `/` search, `f` filters,
Tab/pointer panel selection, Enter details, `r` refresh and Esc Boardroom.

## Source and valuation decision

Use the keyless public scan interface behind `imd.vibingco.de/portfolio`.
The source implementation is `/Library/Vibes/aidude/tools/portfolio/`.
`GET /portfolio/api/scan?wallet=<address>` reports running/done/error; a done
response contains a scan snapshot. `fresh=1` is an explicit refresh request,
not a flag repeated on every status poll. The hosted service controls its own
cache and scan limits. Retain the source's scan timestamp and per-chain block
heads; never replace an old observation time with the local poll time.

| Choice | Benefit | Cost |
| --- | --- | --- |
| Adapt the reference scan API — selected | Reuses its broad discovery, pooled valuation, stakes, NFTs and utility logic | Depends on the reference service; estimates inherit its evidence limits |
| Port the entire scanner into MaxPane | Independent transport and future source control | Large new scanner, RPC workload and maintenance surface; outside this change |

Keep the legacy `PortfolioScreen`, `PortfolioManager`, market-price models and
demo intact. Their held-price/P&L contracts differ from this exit-value view.
Use additive `SwarmPortfolio*` modules and a retained manager owned by SurfManager.

The source groups wallet, stake and reward amounts by `(chain_id, token_address)`,
quotes the aggregate token exposure and apportions proceeds across its lines.
Preserve those allocations; selecting/filtering a subset does not create a new
independently executable quote. Do not regroup by symbol or merge chains.
Total value is wallet + stake principal + unclaimed rewards. Pending stake
rewards appear once in unclaimed, never in both principal and rewards.

These are estimates, not net guaranteed liquidation proceeds. Source exceptions
include direct ETH/dollar conversions and reserve-valued LP positions. The
token-sale percentage describes the first token leg, not necessarily the entire
route. No portfolio-history chart or P/L is available from this snapshot source.

## Primitive data contract

The new models module owns field tuples. All payloads contain primitives only.
Amounts are whole-token quantities; monetary fields are USD. Numeric values
must be finite and nonnegative. Unknown is `None`; observed zero is zero.

**Snapshot:** `wallet`, `state`, `as_of`, `assets`, `positions`, `rewards`, `nfts`,
`standings`, `utilities`, `chains`, `coverage`, `error`, `seats`, `seats_as_of`,
`seats_state`. State is one of empty,
loading, ok, partial, stale or unavailable. Each unread row collection is `None`;
a successfully empty collection is `[]`.

**Asset:** `id`, `chain_id`, `token_address`, `symbol`, `name`,
`wallet_quantity`, `wallet_usd`, `staked_quantity`, `staked_usd`,
`ready_quantity`, `ready_usd`, `locked_quantity`, `locked_usd`,
`pending_quantity`, `pending_usd`, `unknown_reward_quantity`,
`unknown_reward_usd`, `total_usd`, `sell_state`, `sellable_pct`, `pool`,
`connections`, `source`. The ID is `chain:lowercase-address`. `source` preserves
available location/provenance facts; source presence must not be inferred from
a numeric fallback. Sale state: full, partial, none, no_pool or unknown.

**Position:** `id`, `asset_id`, `chain_id`, `contract_address`, `name`,
`quantity`, `value_usd`, `pending_usd`, `apr`, `apr_method`, `site_url`, `rewards`.
The final field contains normalized reward IDs, not a second valued inventory.

**Reward:** `id`, `asset_id`, `chain_id`, `token_address`, `symbol`, `quantity`,
`value_usd`, `status`, `unlock_at`, `source_name`, `source_address`, `site_url`,
`kind`. Status: ready, locked, pending or unknown. A future usable unlock means
locked; stake accrual means pending. Ready requires usable eligibility evidence;
an unclassified source claim or missing unlock is not proof of readiness.

**NFT:** `id`, `chain_id`, `contract_address`, `name`, `symbol`, `count`,
`token_ids`, `site_url`.

**Standing:** `id`, `chain_id`, `contract_address`, `name`, `fields`, `sites`.
Fields are `{name, value}`; sites are `{label, url}`. Contract eligibility is
preserved as its own named observation, not a synthesized safety/agent score.

**Utility:** `id`, `asset_id`, `chain_id`, `contract_address`, `name`, `kind`,
`role`, `joined`, `tvl_quantity`, `tvl_usd`, `apr`, `apr_method`, `site_url`.

**Chain:** `chain_id`, `block`. These are block observations from the same scan,
not invented separate observation timestamps or a cross-chain atomic snapshot.

**Coverage:** `claims_complete`, `malformed_rows`, `contracts_scanned`,
`hidden_count`. Completeness is asserted only where the source supplies evidence;
contract counts alone do not prove an exhaustive portfolio.

**Seats:** a separate keyless `/pair/wallet` read supplies owned IDMD tokens,
including unpaired tokens. Seat ownership has its own observation time and
60-second refresh cadence; NFT discovery alone does not prove the full seat set.

The pure `project(snapshot, chain='all', query='', show_no_sale=False,
sort='value')` function adds overview `metrics`, filtered `holdings` and popup
data while retaining canonical assets. Metrics include total/wallet/staked/
unclaimed USD, ready/locked/pending/unknown-reward USD, NFT collection/item counts,
seat count and partial state. Filtering uses the same selected population for
all associated amounts; identity and source coverage survive filtering.

## Failure and safety behavior

- Validate source wallet identity before publishing. A→B→A switches require a
  generation guard; obsolete results cannot repaint the selected wallet.
- Poll only while active, retain one pending request, bound responses and lists,
  and cancel/drain owned reads on wallet change, view suspension and close.
- Keep valid same-wallet observations on transient failure with their original
  timestamp. Unknown totals remain unknown or explicitly partial; no fake zero.
- Apply the existing owner display override: retain source errors/states
  internally and in hover evidence; do not add fixed failure banners. The SEATS
  card uses its own ownership timestamp/state, independently of scan age.
- Distinguish no pool, no quoted proceeds and unread data. The reference can
  collapse a failed quote to zero, so zero alone cannot support a stronger
  claim that buyers do not exist.
- Keep unknown holdings visible. The no-sale toggle hides confirmed no-sale
  source rows only; it does not hide malformed/unread values as worthless.
- Reject conflicting duplicate identities instead of adding them twice.
  Invalid rows reduce coverage and cannot silently produce an exact total.
- Escape all third-party text. Accept safe HTTPS project links only; address
  explorer selection follows the normalized chain, never arbitrary source HTML.
- No API keys, imported signer code, source execution or runtime dependency on
  the aidude checkout. Tests use committed public captures and deny network.

## Acceptance

All approved A sections receive real source data and handle empty/error states.
B opens as the existing native modal style and has no independent polling loop.
The overview, popup, filters and wallet switch work at 149×45 and in smaller
scrollable terminals. Show a live keyless render before layout hardening/review;
then certify content-driven pins in situ. Validate double-counting, readiness,
unknown states, stale snapshots and wallet races with focused offline tests.
