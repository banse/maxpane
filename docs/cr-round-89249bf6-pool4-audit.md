# CR 89249bf6 — POOL4 data reality check

Audited 2026-10-21: every mounted metric group in `surf.pool4_user` (POOL4
MARKET) and `surf.pool4` (PROTOCOL). This checks data provenance, units,
calculations and current public reads; it is not a contract security audit.

## Evidence and clocks

The live application client ran against a temporary copy of the local cache.
Its `eth_call` and head reads were pinned by the audit harness to Ethereum
block **26,240,944**, timestamp **2026-10-21 12:22:23 UTC**. PublicNode supplied
state and headers; Tenderly/MEVBlocker supplied logs. No owner cache was changed.
The completed POOL4 and staker reads took **3.40 seconds**, 33 HTTP RPC requests;
end-to-end including startup/close was 4.78 seconds. The APR fix adds one batch
containing two headers. These are one-run measurements, not latency guarantees.

| Read | Exact scope / observation |
| --- | --- |
| Hook and v4 pool flow | Blocks 26,233,745–26,240,944; display limited to 25 recent rows |
| Dripper delivery | Blocks 26,190,545–26,240,944; boundary timestamps 2026-10-14 11:49:23 and 2026-10-21 12:22:23 UTC; **606,780 seconds** |
| sIMD transfers | Blocks 25,837,745–26,240,944, with eight complete chunks |
| POOL4 observation | 2026-10-21 12:22:27.730 UTC |
| Staker observation | 2026-10-21 12:22:29.771 UTC |
| ETH/USD quote used by price | Separate source clock, 2026-10-21 12:22:02.928 UTC |

An independent RPC calculation at block **26,240,906** read vault supply,
assets, decimals, current burn/reward claims, ETH/USDC price and the delivery
boundary headers. It independently folded the captured share transfers and
delivery events. The explicit-pool `pool4hook-research` helper also agreed with
the state measurements at block 26,240,897; that helper reads `latest`, so it
is corroboration rather than a same-block equality check.

Temporary evidence: `/private/tmp/cr-89249bf6/{capture.json,independent.json,
research-state.json,pool4-slot.json,pool4_stakers-slot.json,live-payload.json}`.
The trimmed real boundary response is committed as
`tests/fixtures/surf/pool4/mainnet_drip_window_boundaries.json`.

## Mounted fields and findings

All token quantities below are whole IMD unless marked otherwise. IMD/ETH
amounts divide raw uint256 values by 1e18. Vault shares instead use the live
`decimals()` result, **24**, and one-share conversion calls use 1e24.

| Surface / fields | Source and calculation | Current evidence / outcome |
| --- | --- | --- |
| MARKET price; venue gap; cheaper venue | Hook current tick gives IMD/ETH; multiply its inverse by separately cached ETH/USD. Comparison uses the two venue ticks from the venue batch and both fee getters. | Price **$5.71670485** at the quote clock above; hook/reference ticks **60,676 / 60,678**, gap **0.020001%**, below combined **2%** fees, hence no venue edge. |
| Generic title price/parity | General Surfboard title selected launchpad sqrt-price before the generic market quote; parity also used FP. POOL4 mode does not refresh the launchpad. | Fixed an unrelated retained **$5.47574317 / −7.5043% / as of —** header above the current POOL4 price: both POOL4 titles now use their own view/source information. |
| MARKET rate; PROTOCOL vault share/delta | Vault `convertToAssets(10**decimals)`; delta compares the session baseline, not a 24-hour return. | **7.976548051 IMD/sIMD**. Fresh-session delta is unknown, correctly not zero. |
| MARKET staking APR | First word of complete `Dripped` logs only, divided by current vault assets, multiplied by 31,536,000 / measured window seconds × 100. Keeper reward is excluded. | **68.153333333 IMD / 1,898,910.588842249 IMD**, over **606,780s**, gives **0.1865339706%**. Fixed missing APR caused by clustered events; see below. |
| MARKET vault; PROTOCOL TVL | Vault `totalAssets`, `totalSupply`, live decimals; holder count from the separate transfer fold. | **1,898,910.588842249 IMD**, **238,061.699958621 sIMD**, **561 holders**. |
| MARKET bid; SIGNALS backstop | Live band liquidity/bounds/current tick; distance from current price to lower bound. Remaining token0 amount is `L × (1/sqrt(max(current,lower)) − 1/sqrt(upper))`, floored at zero. | Bounds **63,840–887,220**, liquidity **829,067,479,182,419,706,067**, **34.071495972 ETH**, **27.12205869% under**. Fixed original-principal overstatement after entering the band. |
| MARKET queue; PROTOCOL delivery/vault next | Dripper balance, `drippable`, `canDrip`, rate; queued / daily rate gives capacity days. | Queued/ready amount **0.259487265 IMD**, cap **1,000 IMD/day**, **canDrip=false**. Capacity days **0.000259487** is not an execution ETA; the minimum drip has not been reached. |
| PROTOCOL vault delivery cap | Annualized daily capacity / current assets. This is distinct from realized delivery APR. | **19.22154746%** theoretical cap; never substitute it for the **0.18653397%** observed staking rate. |
| MARKET BURN & SUPPLY | Hook cumulative burn and token supply; spark/pace from the 25 displayed flow rows and their own timestamps. | Burned **35,109.006202839 IMD**, current Ethereum supply **4,173,855.366511 IMD**, ratio **0.84116490%**. Recent burn chart is a sample, not lifetime or complete-day volume. |
| MARKET SIGNALS burning/backlog | Headroom and backlog from the same POOL4 slot; no extra fetch. | Burning **OFF**, headroom **1,310.291489710 IMD**; positive tiny backlog, not an absent backlog. |
| MARKET IF IMD FALLS | Pure concentrated-liquidity math from current tick, full-range liquidity and band; five scenario rungs. | Inputs checked against live getters. Scenario estimates hold current liquidity fixed; future trades, fees, rebalances and keeper behavior are not predictions. |
| MARKET STAKERS rows/count/top three | Deduplicated sIMD Transfer fold; share amounts converted at current vault rate; rank and concentration from balances. | Independent raw balance sum **238061699958621150789898206531** exactly equals live totalSupply; **561**, top three **17.47219862%**. Completeness limitation below. |
| MARKET RECENT FLOW | v4 Swap/ModifyLiquidity plus hook events joined per transaction; timestamp, side, IMD size, burn/reward and fee legs, settlement. | Correct token orientation/units in sampled rows, e.g. latest sell **17.45 IMD**, fee **0.1745 IMD**. At most 25 rows from the 7,200-block window; zero burn on a trade with headroom is real. |
| PROTOCOL totals / THE SPLIT | Cumulative `totalBurned`, `totalRewarded`, `totalFeeToken`; proportions use their sum. Reward path is read through Distributor, not inferred from address absence. | Burn **35,109.006202839**, rewards **6,195.706976972**, fees **4,085.394997329**. Measured fee/burn/staker shares **9.00062847 / 77.34946580 / 4.09497172%**; drift **0 bps**. |
| PROTOCOL split destinations | Hook reward share 1500/10000; Distributor staking/nft bps; bonding is validated remainder. Earned and held balances come from getters. | Reward leg **30% staking / 30% nodes / 40% bonding**. Earned **1,830.438121522 / 1,830.438121522 / 2,440.584162030 IMD**; node/bond reserves equal their earned amounts in this read. |
| PROTOCOL unsettled/checks/retained | Bounded hook-event reconciliation; current claims independently read; retained ETH and last claim from hook getters. | Current burn/reward claims **0 / 0** independently confirmed; retained ETH **0**; last claim **26,240,619**. Lifetime counter reconciliation remains explicitly **window-limited**. |
| PROTOCOL inventory / THE RATCHET | Hook reserve, cap/floor, decay, liquidity, tick/ref tick; headroom = cap − reserve, floor distance = reserve − floor. | Reserve **7,689.708510290**, cap/floor **9,000**, decay **3,000/day**; floor distance **−1,310.291489710** (**−14.55879433%**) is valid because the floor constrains the cap, not inventory. Full-range ETH **17.819178837**, raw L **370167922903193809364**; band drifted from ref **60,631**. |
| PROTOCOL reserve spark | Retained valid observed reserve samples, not manufactured historical points. | Current read agrees; older cache samples were not independently re-fetched at historical blocks. |
| PROTOCOL HATCHES / addresses/network | Live owner/paused/rebalance getters and resolved reward-path addresses. Capability prose is structural documentation. | MAINNET adopted hook **0xc6c965bd164c483e87d0b550671798e9a3602840**. Vault owner zero/renounced and open; hook/dripper/distributor owner live. Fixed unsupported BOND market closure claim: readable held balance proves reserve, not market deployment. |

## Fixes and remaining boundaries

1. **APR duration:** optional event timestamp spacing could not measure quiet or
   clustered windows, and a prior estimate could survive a failed read. The
   client now reads and validates the two exact boundary headers. Missing or
   mismatched headers leave APR unknown; a complete empty log window with valid
   headers yields a real zero. Failed log chunks still invalidate the sweep.
2. **Backstop amount:** use current price and the actual upper bound rather than
   full original band principal. Missing price/bound data remains unknown.
3. **BOND status:** `heldBonding` no longer turns into a claim that a market is
   closed, absent or opens at a documented dollar price. Deployment stays
   unknown; readable reserve is described as `reserve held`.
4. **Header context:** the controller changed both POOL4 mode headers to their
   own source data, removing the retained launchpad price and unrelated parity.

The two observed RPC reverts are expected reward-path interface probes:
`vault()` on the Distributor and `dripper()` on the Dripper. They do not
represent failed reads for mounted metrics.

Production state batches still use `latest`; one HTTP batch does not guarantee
one block at every provider. The audit pinned calls explicitly. Current prices
also intentionally combine the POOL4 clock with a separate ETH/USD quote clock.
Strict same-block production state snapshots are a follow-up, not a property
claimed by this check.

The bounded staker fold reconciles exactly for this observation. Its existing
generic completeness heuristic cannot prove that older, unmoved balances are
absent outside the eight-week window. A future hardening should reconcile raw
folded balances to same-block vault totalSupply before calling coverage complete.

POOL4 has a **600-second** source TTL and stakers **1,800 seconds**; a UI poll
does not refetch either before it is due. Source read time advances on successful
revalidation, while unchanged-content time can remain older. This audit found
no evidence that an unchanged content clock alone means loading is broken.

## Validation

Focused, offline regression selection: **23 passed** (382 deselected). Covers
exact/missing/wrong/malformed/reversed boundary headers, cold empty and clustered
delivery, failed boundary after success, unrelated delivery topics, below/inside/
above-band and missing-tick amounts, and unsupported BOND deployment inference.
The live fixed payload was rendered at **149×45** for both views by the controller.
Four targeted mutations were killed by the named regression tests: accepting a
wrong boundary block, assuming 12-second blocks, counting original band principal,
and deriving market deployment from reserve presence. The mutation runner restored
both production files byte for byte.
Whole POOL4 data/composing checks: **762 passed**, with five unrelated baseline
screen-test failures reproduced against the prior Surf screen (legacy
launchpad hero/key/body expectations and the staker clipping fixture). The
whole-change review found no POOL4 defects; independent review mutations also
rejected assumed 12-second windows and original-principal backstop amounts.
