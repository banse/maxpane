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
#: ``bridgeToBaseBurnReceiver()`` — LP-fee IMD leaves mainnet supply here.
BURN_EXECUTOR = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
#: Canonical ERC-8004 Trustless-Agents registry (ANNOUNCE registered here).
ERC8004_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
#: Uniswap v4 PoolManager — ``Initialize`` with hooks != 0x0 IS the launch.
POOL_MANAGER_V4 = "0x000000000004444c5dc75cB358380D2e3dE08A90"
#: Canonical WETH9 — the pool's token0.
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

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
    BURN_EXECUTOR,
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
)
