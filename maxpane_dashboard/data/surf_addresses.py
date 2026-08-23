"""Vendored address constants for the surf dashboard (surfsurf.eth mission control).

Every address below was read from chain during the 2026-08-08 research sweep and
is EIP-55 checksummed; ``tests/data/test_surf_addresses.py`` recomputes each
checksum with this repo's keccak, so a mistyped nibble cannot ship.

Two hazards this module exists to contain:

* **Address poisoning is live on the ops wallet.** ``frenpet.eth``'s history
  contains 1-gwei sends from ``0x61CCFD5d…F14E`` (imitating :data:`LP_FEE_SINK_B`
  ``0x61CC704c…f14E``) and from ``0xF3083828…0Ee6`` / ``0xF3087598…0eE6``
  (imitating :data:`LP_FEE_SINK_A` ``0xF3084Bc7…0eE6``).  The defence is an
  allowlist, not a blocklist: only addresses in :data:`KNOWN_LABELS` may render
  as a trusted label; everything else renders dimmed and truncated.  Never add a
  spoof here "so it can be flagged" — that inverts the guarantee.
* **Token name/symbol are owner-mutable** (FP → VIBE → IMD, twice already).  The
  dashboard trusts :data:`IMD_TOKEN`, never a name.

Gate hazard (read before wiring signal 3): ``identityAllowed()`` exists on
*both* the IDMD NFT and the working registry.  The NFT's owner is bricked (the
Arachnid CREATE2 factory owns it), so the NFT's flag is permanently ``false``
and reading it would render a gate that can never open.  The live gate is
:data:`IDENTITY_REGISTRY`.
"""

from __future__ import annotations

# --- EOAs -------------------------------------------------------------------
#: Primary dev EOA, ENS surfsurf.eth.  Deploys, mints, bridges, plays FWA.
DEV_WALLET = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"
#: Second dev EOA, ENS frenpet.eth.  Holds the LP position and funds burns.
OPS_WALLET = "0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095"
#: The announcement channel EOA ("the agent").  Emits **no logs** — poll nonces.
ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"

# --- Contracts (Ethereum mainnet) -------------------------------------------
#: ``BridgedFP is OFT`` — LayerZero V2 wrapper around Base FP.  Name is mutable.
IMD_TOKEN = "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"
#: identity.md ERC-721, 2000 supply, fully on-chain SVG.  Ownership bricked.
IDMD_NFT = "0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D"
#: Immutable pure renderer behind ``IDMD_NFT.tokenURI``.
IDENTITY_RENDERER = "0x3F559eF271B245E7e754fEAD7d50cd55aC981423"
#: The *working* identity store; owner = ANNOUNCE.  This is the gate to poll.
IDENTITY_REGISTRY = "0x000008061ccac597a321a75E3470a3E8fAF9dD2d"
#: Uniswap v3 IMD/WETH, 1% fee.  token0 = WETH, token1 = IMD (address order).
POOL_V3 = "0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9"
#: Uniswap v3 NonfungiblePositionManager — holder of LP_POSITION_ID.
NFPM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
#: Superseded burn executor.  Kept: it holds 0.664 IMD of residue and appears
#: in the historical burn ledger.  ``rescueToken`` drained it on 2026-08-20.
BURN_EXECUTOR_V1 = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
#: The live executor.  ``bridgeToBaseBurnReceiver()`` is **permissionless** --
#: the dashboard renders that state and never calls it.
BURN_EXECUTOR_V2 = "0xe29386719C155B6847aD5a4E97C6674f10ffc750"
#: Canonical ERC-8004 Trustless-Agents registry (ANNOUNCE registered here).
ERC8004_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
#: Uniswap v4 PoolManager — ``Initialize`` with hooks != 0x0 IS the launch.
POOL_MANAGER_V4 = "0x000000000004444c5dc75cB358380D2e3dE08A90"
#: Canonical WETH9 — the pool's token0.
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
#: v4 hook behind the IMD launchpad: bonding curves, 0.5% burn + 0.5% creator.
#: It hooks *launchpad coin* pools; the IMD/ETH pool itself is hookless.
LAUNCHPAD_HOOK = "0x51768F5dA32BA2008304cC81674da51aCb802888"
#: ``launch(string,string)`` -- permissionless, unpriced beyond gas.
LAUNCHPAD_FACTORY = "0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42"
#: Uniswap v4 PositionManager -- holds the ops wallet's single LP position.
POSITION_MANAGER_V4 = "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e"
#: Base-side sink the executor bridges to; mainnet supply drops on arrival.
#:
#: KNOWN ANOMALY (flagged 2026-08-23, not corrected): unlike its four
#: siblings above, this literal does not satisfy EIP-55 -- this module's own
#: keccak recomputes a different casing pattern for the same 20 bytes
#: (``0xf9d7CBf5Bef2f5c9ba93a70F31DdCA6457716793``), cross-checked with
#: pycryptodome's independent keccak to rule out a bug in ours. The
#: lowercase digits are identical either way, so this is the same account
#: either way -- only the self-check casing is off. Left byte-for-byte as
#: handed down rather than re-cased, so ``test_every_address_is_checksummed``
#: is the one deliberately red case in the suite; see its docstring.
BASE_BURN_RECEIVER = "0xf9d7cbf5bEF2f5c9bA93a70F31dDCa6457716793"

#: **Fallback only.**  The live pool id is read from
#: ``LaunchpadHook.imdEthPoolId()`` every chain round.  38 ETH/IMD v4 pools
#: exist and 37 are decoys, so a stale constant is not merely wrong, it points
#: at somebody else's 98%-fee pool.  Used only when the hook read fails.
POOL_V4_ID_FALLBACK = (
    "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3"
)
#: Storage slot of ``PoolManager._pools``; v4 has no ``slot0()`` getter.
V4_POOLS_MAPPING_SLOT = 6

# --- Base chain (read-only bridge counterpart) ------------------------------
#: The original Fren Pet ERC-20 on Base.  IMD mints 1:1 against FP locked here.
FP_TOKEN_BASE = "0xFF0C532FDB8Cd566Ae169C1CB157ff2Bdc83E105"

# --- Secondary label targets (additive; not part of the frozen 14) ----------
#: Seaport 1.6 — 86% of IDMD secondary volume routes through it.
SEAPORT = "0x0000000000000068F116a894984e2DB1123eB395"
UNIVERSAL_ROUTER = "0xd92A36B0000531EF3063dEd4De20A0783308446C"
#: Relay depository — the dev's cross-chain funding route.
RELAY_DEPOSITORY = "0x4cD00E387622C35bDDB9b4c962C136462338BC31"
#: FWA Splitter — already vendored in ``fwa_client``; the dev claims from it.
FWA_SPLITTER = "0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe"
#: Where FWA winnings are swept, ~1 min after each claim.
DEV_SWEEP = "0x58239Ad01D72811F179bAE08983F95Ac30274e55"
#: Unidentified recipients of LP-fee ETH.  Labelled because the poisoners
#: imitate exactly these two strings.
LP_FEE_SINK_A = "0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6"
LP_FEE_SINK_B = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"
#: Arachnid CREATE2 proxy — the accidental owner of IDMD_NFT.
CREATE2_FACTORY = "0x4e59b44847b379578588920cA78FbF26c0B4956C"
#: The dev's *existing* v4 hook (Vibecoins launchpad) — NOT the coming one.
VIBECOINS_HOOK = "0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44"
#: Stalled Base twin of the NFT (unverified source).
IDMD_BASE_TWIN = "0x0000C0484F4626e368dFb909aBa107f7C97b6B1D"
#: CEX hot wallet that funded the 2026-08-07 LP add (33.693 ETH inbound).
KRAKEN_HOT = "0xf70da97812CB96acDF810712Aa562db8dfA3dbEF"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

#: The Uniswap v3 position NFT that holds all IMD liquidity.  Owner = OPS_WALLET;
#: a liquidity decrease here is the LP MIGRATION signal.
LP_POSITION_ID = 1167726

#: Every address this module labels, in declaration order.
LABELED_ADDRESSES: tuple[str, ...] = (
    DEV_WALLET,
    OPS_WALLET,
    ANNOUNCE,
    IMD_TOKEN,
    IDMD_NFT,
    IDENTITY_RENDERER,
    IDENTITY_REGISTRY,
    POOL_V3,
    NFPM,
    BURN_EXECUTOR_V1,
    ERC8004_REGISTRY,
    POOL_MANAGER_V4,
    WETH,
    FP_TOKEN_BASE,
    SEAPORT,
    UNIVERSAL_ROUTER,
    RELAY_DEPOSITORY,
    FWA_SPLITTER,
    DEV_SWEEP,
    LP_FEE_SINK_A,
    LP_FEE_SINK_B,
    CREATE2_FACTORY,
    VIBECOINS_HOOK,
    IDMD_BASE_TWIN,
    KRAKEN_HOT,
    ZERO_ADDRESS,
    BURN_EXECUTOR_V2,
    LAUNCHPAD_HOOK,
    LAUNCHPAD_FACTORY,
    POSITION_MANAGER_V4,
    BASE_BURN_RECEIVER,
)

# --- Event topics -----------------------------------------------------------
# Vendored hashes with their preimages beside them; the preimages are not
# decoration — tests/data/test_surf_addresses.py recomputes every value from
# them, and pins the literals too, so a matched pair of typos still fails.
#
# ``IdentityHashUpdated`` was taken from the verified IdentityMD source
# (captures/identity_contract.json): ``event IdentityHashUpdated(uint256
# indexed id, string ipfsHash, bool permanent)``.  Indexed-ness does not enter
# the topic0 preimage; the *types* do.

TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TOPIC_IDENTITY_HASH_UPDATED = (
    "0x57c85cf86ae80c7b372281c7dd1b0f8b99de39e76d757725a32b6bd88f7ff1b6"
)
TOPIC_V4_INITIALIZE = (
    "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
)
TOPIC_SEAPORT_ORDER_FULFILLED = (
    "0x9d9af8e38d66c62e2c12f0225249fd9d721c54b83f48d9352c97c6cacdcb6f31"
)
#: v4 PoolManager -- liquidity add/remove against the IMD/ETH pool.
TOPIC_MODIFY_LIQUIDITY = (
    "0xf208f4912782fd25c7f114ca3723a2d5dd6f3bcc3ac8db5af63baa85f711d5ec"
)
#: LaunchpadFactory -- one per ``launch(string,string)`` call.
TOPIC_LAUNCHED = (
    "0xedc96a45101454b126fdf99206bee0947b2cc3ce06933cb22a2b9434bb4eaa9e"
)
#: LaunchpadHook -- one per bonding-curve trade against a launched coin.
TOPIC_CURVE_SWAP = (
    "0x4e041a3c3c349dd253ff446bef131680ef40e9d33b823aedaa99e0893bee4dcf"
)
#: BurnExecutor -- fires when staged IMD is actually burned.
TOPIC_IMD_BURNED = (
    "0xb95f82a5dcec67b396bc59a79ad4a1757d5ea6d29690b8c6bcd88d720adee5d6"
)
#: LaunchpadHook -- the 0.5% creator-fee half of every curve swap.
TOPIC_CREATOR_FEE_ACCRUED = (
    "0xb26ec14e06ac4ca6c33b6f1eb87160c44cd1a6237e0f884c947a89e61f98b4c6"
)

#: constant name -> the exact Solidity event signature it hashes.
TOPIC_PREIMAGES: dict[str, str] = {
    "TOPIC_TRANSFER": "Transfer(address,address,uint256)",
    "TOPIC_IDENTITY_HASH_UPDATED": "IdentityHashUpdated(uint256,string,bool)",
    "TOPIC_V4_INITIALIZE": (
        "Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)"
    ),
    "TOPIC_SEAPORT_ORDER_FULFILLED": (
        "OrderFulfilled(bytes32,address,address,address,"
        "(uint8,address,uint256,uint256)[],"
        "(uint8,address,uint256,uint256,address)[])"
    ),
    "TOPIC_MODIFY_LIQUIDITY": (
        "ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)"
    ),
    "TOPIC_LAUNCHED": (
        "Launched(bytes32,address,address,string,string,uint256,uint256)"
    ),
    "TOPIC_CURVE_SWAP": (
        "CurveSwap(bytes32,address,address,bool,uint256,uint256,uint256,"
        "uint256,uint256)"
    ),
    "TOPIC_IMD_BURNED": "ImdBurned(uint256)",
    "TOPIC_CREATOR_FEE_ACCRUED": "CreatorFeeAccrued(address,uint256)",
}

# --- Function selectors -----------------------------------------------------
SEL_POSITIONS = "0x99fbab88"        # NFPM.positions(uint256)
SEL_IDENTITY_ALLOWED = "0xac8f3de6"  # IdentityRegistry.identityAllowed()
SEL_TOTAL_SUPPLY = "0x18160ddd"      # ERC-20/721 totalSupply()
SEL_SLOT0 = "0x3850c7bd"             # UniswapV3Pool.slot0()
SEL_NAME = "0x06fdde03"              # name()  — shared by ERC-20 and ERC-721
SEL_SYMBOL = "0x95d89b41"            # symbol() — shared by ERC-20 and ERC-721
#: Both selectors are called against IMD_TOKEN only, where name()/symbol() are
#: mutable, display-only owner-set strings (FP -> VIBE -> IMD, twice already —
#: see the module docstring).  IDMD_NFT's name()/symbol() are hardcoded `pure`
#: returns in the verified source and are not read through these selectors.
SEL_OWNER_OF = "0x6352211e"          # ERC-721 ownerOf(uint256) — NFPM position

# --- v4 / launchpad selectors -------------------------------------------
SEL_EXTSLOAD = "0x1e2eaeaf"          # PoolManager.extsload(bytes32)
SEL_COIN_COUNT = "0x678fd289"        # LaunchpadFactory.coinCount()
SEL_ALL_COINS = "0x13560cac"         # LaunchpadFactory.allCoins(uint256)
SEL_POOL_ID_OF = "0x30040054"        # LaunchpadFactory.poolIdOf(address)
SEL_IMD_ETH_POOL_ID = "0x45e9a4a4"   # LaunchpadHook.imdEthPoolId()
SEL_IMD_TO_BURN = "0x8feff8aa"       # LaunchpadHook.imdToBurn()
SEL_TOTAL_REAL_IMD = "0x7cadd0a2"    # LaunchpadHook.totalRealImd()
SEL_BURN_FEE_BPS = "0xa5189810"      # LaunchpadHook.burnFeeBps()
SEL_CREATOR_FEE_BPS = "0x17773ebb"   # LaunchpadHook.creatorFeeBps()
SEL_TOTAL_CREATOR_ETH_OWED = "0x8e0ff96e"    # LaunchpadHook.totalCreatorEthOwed()
SEL_SPOT_PRICE_ETH_PER_COIN = "0x39c051d9"   # LaunchpadHook.spotPriceEthPerCoin(bytes32)
SEL_GET_CURVE = "0x8c7171b5"         # LaunchpadHook.getCurve(bytes32)
SEL_TOKEN_BALANCE = "0x9e1a4d19"     # BurnExecutor.tokenBalance()
SEL_MIN_BRIDGE_AMOUNT = "0xc3c22475"  # BurnExecutor.minBridgeAmount()
SEL_PREVIEW_BRIDGE = "0xe102463d"    # BurnExecutor.previewBridge()
SEL_BALANCE_OF = "0x70a08231"        # ERC-20 balanceOf(address) — IMD @ BurnExecutor

#: constant name -> the exact Solidity function signature it hashes.
SELECTOR_PREIMAGES: dict[str, str] = {
    "SEL_POSITIONS": "positions(uint256)",
    "SEL_IDENTITY_ALLOWED": "identityAllowed()",
    "SEL_TOTAL_SUPPLY": "totalSupply()",
    "SEL_SLOT0": "slot0()",
    "SEL_NAME": "name()",
    "SEL_SYMBOL": "symbol()",
    "SEL_OWNER_OF": "ownerOf(uint256)",
    "SEL_EXTSLOAD": "extsload(bytes32)",
    "SEL_COIN_COUNT": "coinCount()",
    "SEL_ALL_COINS": "allCoins(uint256)",
    "SEL_POOL_ID_OF": "poolIdOf(address)",
    "SEL_IMD_ETH_POOL_ID": "imdEthPoolId()",
    "SEL_IMD_TO_BURN": "imdToBurn()",
    "SEL_TOTAL_REAL_IMD": "totalRealImd()",
    "SEL_BURN_FEE_BPS": "burnFeeBps()",
    "SEL_CREATOR_FEE_BPS": "creatorFeeBps()",
    "SEL_TOTAL_CREATOR_ETH_OWED": "totalCreatorEthOwed()",
    "SEL_SPOT_PRICE_ETH_PER_COIN": "spotPriceEthPerCoin(bytes32)",
    "SEL_GET_CURVE": "getCurve(bytes32)",
    "SEL_TOKEN_BALANCE": "tokenBalance()",
    "SEL_MIN_BRIDGE_AMOUNT": "minBridgeAmount()",
    "SEL_PREVIEW_BRIDGE": "previewBridge()",
    "SEL_BALANCE_OF": "balanceOf(address)",
}

#: Lowercase address -> the label ``SurfDevActivity`` may render as trusted.
#:
#: This is an **allowlist**.  Anything absent renders dimmed as
#: ``0x`` + first 8 + ``…`` + last 6 and is never styled as known.  Do not add
#: spoof addresses here; the poisoning defence is that they fall through.
KNOWN_LABELS: dict[str, str] = {
    DEV_WALLET.lower(): "dev · surfsurf.eth",
    OPS_WALLET.lower(): "ops · frenpet.eth",
    ANNOUNCE.lower(): "announce channel",
    IMD_TOKEN.lower(): "IMD token",
    IDMD_NFT.lower(): "IDMD NFT",
    IDENTITY_RENDERER.lower(): "IdentityRenderer",
    IDENTITY_REGISTRY.lower(): "IdentityRegistry",
    POOL_V3.lower(): "IMD/WETH v3 pool",
    NFPM.lower(): "Uniswap v3 NFPM",
    ERC8004_REGISTRY.lower(): "ERC-8004 registry",
    POOL_MANAGER_V4.lower(): "v4 PoolManager",
    WETH.lower(): "WETH",
    FP_TOKEN_BASE.lower(): "FP token · Base",
    SEAPORT.lower(): "Seaport",
    UNIVERSAL_ROUTER.lower(): "UniversalRouter",
    RELAY_DEPOSITORY.lower(): "Relay depository",
    FWA_SPLITTER.lower(): "FWA Splitter",
    DEV_SWEEP.lower(): "dev sweep wallet",
    LP_FEE_SINK_A.lower(): "LP-fee sink A",
    LP_FEE_SINK_B.lower(): "LP-fee sink B",
    CREATE2_FACTORY.lower(): "CREATE2 factory",
    VIBECOINS_HOOK.lower(): "Vibecoins v4 hook",
    IDMD_BASE_TWIN.lower(): "IDMD twin · Base",
    KRAKEN_HOT.lower(): "Kraken hot wallet",
    ZERO_ADDRESS.lower(): "0x0 mint/burn",
    BURN_EXECUTOR_V2.lower(): "BurnExecutor",
    BURN_EXECUTOR_V1.lower(): "BurnExecutor v1",
    LAUNCHPAD_HOOK.lower(): "LaunchpadHook",
    LAUNCHPAD_FACTORY.lower(): "LaunchpadFactory",
    POSITION_MANAGER_V4.lower(): "v4 PositionManager",
    BASE_BURN_RECEIVER.lower(): "Base burn sink",
}
