# TTT ABI Reconnaissance

Source: verified Solidity source pulled from **Sourcify** (full match) for
`TenThousandTokens.sol`, `TTT.sol`, `Interfaces.sol`; from **Etherscan** verified
source for `TTTHook`. The **FeeSplitter** contract is **NOT verified** on
Etherscan, Sourcify, or Blockscout; its ABI was reconstructed by:

1. Reading the `IFeeSplitter` interface declared in `Interfaces.sol`
2. Querying the deployed bytecode for PUSH4 dispatcher selectors
3. Looking up the three observed event `topic[0]` hashes via the public
   openchain.xyz signature database
4. Calling each candidate selector via `eth_call` and confirming the return
   values match the documented semantics

Confirmation date: 2026-05-22. All view calls were validated against a live
public RPC (`https://ethereum.publicnode.com`).

## Contract addresses (Ethereum mainnet, chain id 1)

| Contract                  | Address                                      | Verified | Source                  |
|---------------------------|----------------------------------------------|----------|-------------------------|
| TenThousandTokens (factory) | `0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e` | yes      | Sourcify (full match)   |
| FeeSplitter               | `0x6e46eaa57e1c7589686e2b0c935e8a8cf907683e` | NO       | bytecode + signature DB |
| TTTHook (Uniswap V4)      | `0xdee7a2ffa963f82facbb12a4e3e8909e4a51a444` | yes      | Etherscan               |
| OnChainRenderer           | `0x60d184419f7ed17ff6ecd2f4277fc21c7ed14615` | unknown  | factory.renderer() read |
| GlobalDistributorHandler  | `0xdf99bd1218e7eb288cffecf9775385167bb09b2d` | unknown  | constructor arg         |
| ClaimSource (S02 Soulbound) | `0xb33d806a94b6770c9d309e0842a75f8e6edcd5a6` | unknown  | constructor arg         |
| Uniswap V4 PoolManager    | `0x000000000004444c5dc75cb358380d2e3de08a90` | yes      | constructor arg         |
| Uniswap V4 PositionManager | `0xbd216513d74c8cf14cf4747e6aaa6420ff64ee9e` | yes      | constructor arg         |
| Permit2                   | `0x000000000022d473030f116ddee9f6b43ac78ba3` | yes      | constructor arg         |
| Multicall3                | `0xca11bde05977b3631167028862be2a173976ca11` | yes      | canonical, all chains   |
| Factory owner             | `0x019817ad02a31b990433542097be29d97613e8cb` | n/a      | EOA (deployer)          |

Per-token ERC20 addresses are discovered dynamically via the factory's
`tokenContract(tokenId) -> address` view OR via the `Launched` event indexed
parameter. As of confirmation date, 109 of 10,000 NFTs have been burned and
launched. Sample launched ERC20s observed during recon:

- tokenId=1 (symbol `ONE`)  -> `0x0edfef9fc4ff3f7911e9332bbb81d824647bca51`
- tokenId=7227             -> `0x3ff47248ce35b84c1d58e3aee7229498e23f741e`
- tokenId=4572             -> `0x5cdb755ad67c85717722da734c45b1919978aec9`
- tokenId=8447             -> `0x2f576fc64cc0e69af04870091dfa74678301d43f`

## Live values read during recon (block 25146444)

| View call (target -> method)            | Returned value                                      |
|-----------------------------------------|-----------------------------------------------------|
| factory.MAX_SUPPLY()                    | `10000`                                             |
| factory.totalMinted()                   | `10000` (fully minted)                              |
| factory.mintStart()                     | `1778775095` (2026-05-14 16:11:35 UTC)              |
| factory.mintEnd()                       | `1779379895` (2026-05-21 16:11:35 UTC)              |
| factory.launchesPaused()                | `false`                                             |
| factory.hook()                          | `0xdee7a2ffa963f82facbb12a4e3e8909e4a51a444`        |
| factory.feeSplitter()                   | `0x6e46eaa57e1c7589686e2b0c935e8a8cf907683e`        |
| factory.renderer()                      | `0x60d184419f7ed17ff6ecd2f4277fc21c7ed14615`        |
| feeSplitter.MAX_SUPPLY()                | `10000`                                             |
| feeSplitter.burnCount()                 | `109`                                               |
| feeSplitter.activeShares()              | `9891` (= MAX_SUPPLY - burnCount)                   |
| feeSplitter.accETHPerShare()            | `314584002055869302935823287727642163483392648`     |
| feeSplitter.SCALE()                     | `1000000000000000000000000000000` (= 1e30)          |
| feeSplitter.nft()                       | `0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e` (factory) |
| feeSplitter.pending(1)                  | `314584002055869` wei (≈ 0.000000315 ETH)           |
| feeSplitter.rewardDebt(1)               | `0`                                                 |

## Method/event name map (whitepaper -> actual)

| Whitepaper / spec term                         | Actual method/event in source                                          | Notes |
|------------------------------------------------|------------------------------------------------------------------------|-------|
| burn count                                      | `FeeSplitter.burnCount()` (NOT on factory)                             | uint256, view. Factory itself has no burn counter; the FeeSplitter tracks it because the factory calls `onBurn(tokenId, owner)` on every burn-and-launch. |
| max supply                                      | `factory.MAX_SUPPLY()` AND `feeSplitter.MAX_SUPPLY()`                  | Both = 10000. Per-ERC20 `MAX_SUPPLY` exists too but is 1e27 (1B tokens with 18 decimals). |
| total minted                                    | `factory.totalMinted()`                                                | uint256, view. Caps at MAX_SUPPLY. |
| holder pool accETHPerShare                     | `FeeSplitter.accETHPerShare()`                                         | uint256, view. **SCALE = 1e30**, not 1e18. per-NFT pending = `(accETHPerShare * 1 - rewardDebt[id]) / SCALE`. |
| holder pool active shares (divisor)             | `FeeSplitter.activeShares()`                                           | uint256, view. Equals `MAX_SUPPLY - burnCount`. |
| BurnAndLaunch event                             | `factory.Launched(uint256 indexed tokenId, address indexed token, address indexed launcher, string imageURI)` | The token-launch event is named **`Launched`**, NOT `BurnAndLaunch`. The hook also emits its own `PoolLaunched(address indexed token, bytes32 indexed poolId, uint256 deploymentBlock)` event in the same tx. |
| TokenDeployed (at mint time)                    | `factory.TokenDeployed(uint256 indexed tokenId, address indexed token, address indexed holder)` | Emitted during initial NFT mint (not burn). |
| FeeSplitter Deposit event                       | `FeeSplitter.Deposited(address indexed token, address indexed sender, uint256 total, uint256 launcherShare, uint256 tokenWorksShare, uint256 punkStrategyShare, uint256 holderShare)` | Name is **`Deposited`** (past tense), with **7 fields** including the four pre-split share amounts. Validated on a real log: shares sum exactly to total; **split is 50/10/10/30** (launcher / tokenWorks / punkStrategy / holder). |
| FeeSplitter Burn observed event                 | `FeeSplitter.Burned(uint256 indexed tokenId, address indexed owner, uint256 paid)` | Emitted by `onBurn()` when a holder calls `burnAndLaunch`. `paid` = any pending holder-pool ETH paid to the holder right before their NFT is removed from the share pool. |
| Holder claim event                              | `FeeSplitter.Claimed(address indexed claimer, uint256 amount, uint256[] tokenIds)` | The claim is multi-tokenId; emits the sum of all claimed amounts plus the list of NFT ids. |
| Buyback event                                   | `TTT.Bought(address indexed caller, uint256 ethSpent, uint256 amountBought, uint256 callerReward)` | Event is named **`Bought`**, NOT `Buyback`. `ethSpent` is the amount used for the swap (already net of the caller's 0.5% bounty). `callerReward` is the bounty. |
| Buyback reservoir read                          | **`address(token).balance`** (no `reservoir()` view)                   | The TTT ERC20 has **no `reservoir()` accessor** — the buyback pool IS the contract's plain ETH balance. Use `eth_getBalance(tttAddr)` (or include a Multicall3.getEthBalance call). |
| Per-NFT pending claim                           | `FeeSplitter.pending(uint256 tokenId) -> uint256`                      | Returns the un-claimed ETH for one NFT. |
| Per-NFT reward debt                             | `FeeSplitter.rewardDebt(uint256 tokenId) -> uint256`                   | Used internally by the MasterChef-style accrual. |
| Holder claim function                           | `FeeSplitter.claim(uint256[] tokenIds)`                                | Multi-id claim only. There is no `claim()` (no-arg). |
| TTTHook launch timestamp / block                | `TTTHook.deploymentBlock(address token) -> uint64`                     | This is the canonical launch block for the decay tax formula. |
| Per-launch swap fee observability               | `TTTHook.HookFee(bytes32 indexed id, address indexed sender, uint128 feeAmount0, uint128 feeAmount1)` + `TTTHook.Trade(bytes32 indexed id, uint160 sqrtPriceX96, int128 ethAmount, int128 tokenAmount)` | Use `Trade` for swap-by-swap volume + spot price; `HookFee` for the fee amount the hook took. `id` is the V4 PoolId. |
| Factory owner                                   | `factory.owner() = 0x019817ad02a31b990433542097be29d97613e8cb`         | EOA. |
| FeeSplitter owner                               | `feeSplitter.owner() = 0x019817ad02a31b990433542097be29d97613e8cb`     | Same EOA. |

## Topic hashes (keccak256 of event signatures)

Computed locally with `Crypto.Hash.keccak(digest_bits=256)` and cross-checked
against on-chain `topic[0]` values observed in the latest 10,000 mainnet
blocks (every hash below has been seen live).

### Factory (`0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e`)
- `Launched(uint256,address,address,string)`
  -> `0xcd0c803f63c8f47c477dceca7e7b639ce5fe037e50d64fe6a845e7abf75a98f6`
- `TokenDeployed(uint256,address,address)`
  -> `0x9334c9b0e49f1735472cc9700c1aac0d7c5ca7e46f77c3a71f0995c81b3a9587`

### FeeSplitter (`0x6e46eaa57e1c7589686e2b0c935e8a8cf907683e`)
- `Deposited(address,address,uint256,uint256,uint256,uint256,uint256)`
  -> `0x354721bce0f1b29ebf3646e2e2c6d15259383d9493f4bb62300f579d2ad57692`
- `Burned(uint256,address,uint256)`
  -> `0x7a6396f9141e42bbd82eddb43e30077ef07aaafcd4ee3dfbd6adb1dca8f2445a`
- `Claimed(address,uint256,uint256[])`
  -> `0xa6836ed9f6b0bfa430c6b744cac7cc781c2a5b5be98f6e7ca42d32fd16bc6af3`

### TTTHook (`0xdee7a2ffa963f82facbb12a4e3e8909e4a51a444`)
- `PoolLaunched(address,bytes32,uint256)`
  -> `0x0e69758f418be98de9ccecf0e2dccfac52647b79b61488d4f531636eafc39699`
- `Trade(bytes32,uint160,int128,int128)`
  -> `0x3e487677d4b5f47ab5353c80a932bc38af2acf8a570ba49a2af4c54057ce7c6d`
- `HookFee(bytes32,address,uint128,uint128)`
  -> `0x444083dce778da1269b63671912c00569a2a58fa85827911902301f91793ffd7`

### TTT ERC20 (per-token, identical bytecode across all 109 launched)
- `Bought(address,uint256,uint256,uint256)`
  -> `0xedba86fd2b22962d534e70ad9b0ff8730de46f636146f2bab6a72cbb1ebbcc53`
- `LauncherSet(address)`
  -> `0x1a5fd50023d8e6487319f2afbf672c5e7b46c48d30a560cb77ab4c328db29f56`
- `MetadataUpdated(string,string,string)`
  -> `0x61b45807b5528344b8b2c26433a3aabead6c9dc6239e146e7ba7c812fded07d0`

## Surprises / deviations from whitepaper

1. **`burnCount()` lives on the FeeSplitter, not the factory.** The factory has
   no burn counter; it relies on `IFeeSplitter.onBurn(tokenId, owner)` being
   invoked on every burn-and-launch and lets the splitter own the bookkeeping.
   Dashboards that want a single multicall should read `burnCount()` from the
   FeeSplitter address.
2. **Event is `Launched`, not `BurnAndLaunch`.** Argument 4 (`imageURI`) is a
   non-indexed string — useful for the activity stream but cannot be used as a
   topic filter.
3. **Two launch events per launch.** `factory.Launched` fires AND
   `TTTHook.PoolLaunched` fires in the same tx. The hook's event includes the
   Uniswap V4 `poolId` (bytes32) and the canonical `deploymentBlock` — that's
   the value the decay-tax formula uses.
4. **`Deposited` carries the four pre-split shares.** The event emits all four
   slice amounts inline (no need to multiply by basis points). Verified
   on-chain: split is exactly **50% launcher / 10% TokenWorks /
   10% PunkStrategy / 30% holder pool** (whitepaper's 50/30/10/10 percentages
   are correct, but the field ORDER in the event puts the 30% holder slot
   LAST, after both 10% slots). The buyback (PunkStrategy slot) is the third
   10% slot, not "30% goes to buyback".
5. **No `reservoir()` view on the ERC20.** The buyback reservoir is just the
   ERC20 contract's plain ETH balance. Use `eth_getBalance` (Multicall3 has a
   helper `getEthBalance` for this, but `aggregate3` + raw eth balance batched
   via custom call also works).
6. **Buyback event is named `Bought`**, with 4 fields including the caller's
   bounty in a dedicated `callerReward` field. The fee math is: caller gets
   `slice * 50bps / 10000`; the rest is swapped to TTT-<n> and held forever on
   the ERC20 contract itself.
7. **FeeSplitter `SCALE` is 1e30, not 1e18.** With 9891 active shares and
   sub-ETH deposits, 1e18 would lose precision; 1e30 keeps full precision on a
   per-share basis. Implementations MUST read `SCALE()` once and use it in
   pending-calculations (do NOT hardcode 1e18).
8. **`claim` is multi-id only.** `FeeSplitter.claim(uint256[] tokenIds)` is the
   only claim entrypoint. There's no no-arg or single-id claim.
9. **FeeSplitter is unverified.** Source code is NOT published on Etherscan or
   Sourcify. ABI for this dashboard was reconstructed from:
   - `IFeeSplitter` interface in `Interfaces.sol` (gives `depositETH(address)`
     and `onBurn(uint256, address)` signatures)
   - PUSH4 selector scan of deployed bytecode (matches: `accETHPerShare`,
     `SCALE`, `activeShares`, `burnCount`, `MAX_SUPPLY`, `nft`, `pending`,
     `rewardDebt`, `claim(uint256[])`, `owner`, plus solady Ownable handover
     functions)
   - openchain.xyz signature database lookup for the three observed event
     `topic[0]` hashes
   - Live `eth_call` confirmation that each candidate returns the expected
     semantic value
   If TokenWorks ever verifies this contract on Etherscan, cross-check the
   exact parameter names against the recon above.
10. **Mint window closed** (mintEnd was 2026-05-21 16:11:35 UTC). The dashboard
    should treat mint phase as historical context, not a live counter.
11. **GlobalDistributorHandler & OnChainRenderer & ClaimSource are not
    verified.** None of these are needed for the dashboard's data plane —
    they are mentioned in the recon table for completeness only.

## Files this recon produced

- `maxpane_dashboard/abis/ttt_factory.json` — 11 entries (9 views + 2 events)
- `maxpane_dashboard/abis/ttt_fee_splitter.json` — 11 entries (8 views + 3 events)
- `maxpane_dashboard/abis/ttt_erc20.json` — 13 entries (10 views + 3 events)
- `maxpane_dashboard/abis/multicall3.json` — 1 entry (`aggregate3` only)
- `docs/tenthousandtokens_abi_recon.md` — this document
