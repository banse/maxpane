# surfsurf.eth — the onchain experiments of the FrenPet dev

Research for the `surf` dashboard, compiled 2026-08-08. Sources: full Blockscout dumps of all
involved addresses (ETH + Base), verified contract source for every contract that has it, the
complete 21-tx announcement channel decoded, the dev's X feed (327 tweets, design-phase input
only — X is **not** a runtime source), and live keyless RPC reads. Raw data and the eleven
research reports live in the session scratchpad; every load-bearing claim below carries a tx
hash or a live-read citation.

**Subject:** Adam, @surfcoderepeat (GitHub: surfer77), co-creator of FrenPet on Base.
Bio: "Freedom. / currently onchain." He ships onchain-first by explicit policy: since
2026-05-14 all substantive communication happens as onchain messages; X gets terse
after-the-fact pointers.

---

## Cast of addresses

| Label | Address | Chain | What it is |
|---|---|---|---|
| dev wallet (surfsurf.eth) | `0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7` | ETH + Base | Primary EOA. Deploys, mints, bridges. ETH nonce ~2350, Base ~1490, ~120 contracts deployed on Base |
| ops wallet (frenpet.eth) | `0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095` | ETH | Second dev EOA: holds the LP position, collects fees, funds burns. 29 txs total |
| announce channel | `0x200E710aCAA6A93bbc77146026328C40F1d60fB1` | ETH | EOA broadcast feed ("the agent"). Owns the IdentityRegistry, holds IDMD #0, registered on ERC-8004 |
| IMD token | `0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7` | ETH | `BridgedFP is OFT` — LayerZero V2 OFT wrapping Base FP. Name/symbol **mutable** (FP→VIBE→IMD) |
| IDMD NFT | `0x0000eC93127BAA929E58E97dd0095A2BFb38ec1D` | ETH | "identity.md" ERC-721, 2000 supply, free mint, fully onchain SVG metadata. Ownership bricked at birth |
| IdentityRenderer | `0x3F559eF271B245E7e754fEAD7d50cd55aC981423` | ETH | Immutable pure renderer; traits derive from `keccak256("identity.md"‖id)` — computable offline |
| IdentityRegistry | `0x000008061ccac597a321a75E3470a3E8fAF9dD2d` | ETH | The *working* identity store. Owner = announce EOA. Gate currently **closed**; 1/2000 written |
| IMD/WETH v3 pool | `0xD6A822D028bbf7b6EDfA1533e110Ee40c08551d9` | ETH | Uniswap v3, 1% fee, the only real IMD market. LP = position NFT #1167726 owned by frenpet.eth |
| BurnExecutor | `0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B` | ETH | `bridgeToBaseBurnReceiver()` — OFT-sends LP-fee IMD to a Base burn receiver (mainnet supply drops) |
| FP token | `0xFF0C532FDB8Cd566Ae169C1CB157ff2Bdc83E105` | Base | The original Fren Pet ERC-20 (7.196M supply, ~22k holders) |
| FrenPet game | `0x0e22b5f3e11944578b37ed04f5312dfc246f443c` | Base | EIP-2535 Diamond — covered by the existing `frenpet` dashboard |
| ERC-8004 IdentityRegistry | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` | ETH | Canonical Trustless-Agents registry. The announce EOA registered `identitymd-agent` here |
| Vibecoins hook | `0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44` | ETH | Dev's *existing* v4 hook (launchpad, live since 2026-01-06) — not the upcoming experiment |
| IDMD Base twin | `0x0000C0484F4626e368dFb909aBa107f7C97b6B1D` | Base | 698 minted, unverified source, equally ownership-bricked. Stalled |

Unidentified but recurring: `0x58239Ad…` (receives the dev's swept FWA winnings),
`0xF3084Bc7…0eE6` and `0x61CC704c…f14E` (received LP-fee ETH), `0xA4aD5765…` (correspondent,
received gifted IDMD #0 and #946).

## The announcement channel (the spine of everything)

The dev posts by sending **value-0 self-transactions whose calldata is plain UTF-8** from
`0x200E710a…`. Anyone can "reply" by sending the address a tx with UTF-8 calldata. 21 txs
total as of today: 13 self-posts, 1 ERC-8004 `register()` call, 1 funding tx from the dev
wallet (0.054 ETH, tx `0x632f5dc3…`, proves ownership), 6 community replies.

Key posts (all decoded from calldata):

| Date | Nonce | Message (condensed) |
|---|---|---|
| 2026-05-16 | 0 | "soon" |
| 2026-05-21 | 2 | A complete machine-readable monitoring spec: filter `from==to==channel`, decode input as UTF-8, poll ≥1/min, keep seen-hashes — *the dev published the dashboard's own polling contract* |
| 2026-05-22 | 3 | "A P2P decentralized harness" |
| 2026-05-22 | 4 | ERC-8004 `register("ipfs://QmYj9brp…")` → agent card `identitymd-agent` (inactive stub). The project name was committed onchain **two months before** the public reveal |
| 2026-07-27 | 7 | Reveal: OpenSea `identitymd` + IMD token address |
| 2026-07-29 | 8 | The v4 hook: "highly experimental", **"I'll announce it before moving the LP"**, floats NFT-holder-only trading for the first hours |
| 2026-07-31 | 10 | Pool is 1% fee tier; 30,784 IMD accrued fees, to be burned periodically |
| 2026-08-03 | 11 | Thesis: "IDM has pristine distribution that can't be recreated… everyone will communicate onchain too" |
| 2026-08-05 | 12 | Community explorer idmd-reader.pages.dev; "Burned 15745 more tokens" |
| 2026-08-07 | 13 | "I moved 33 eth to the LP" citing tx `0x90a0f8e2…` — executed by frenpet.eth, first-person: both wallets share the operator |

Cadence: a May burst, a 52-day silence, and since Jul 26 a steady ~1.65-day rhythm. Replies
arrive within 1–3 h of provocative posts.

**Detection recipe (critical):** these txs emit **no logs** (`has_logs:false`) —
`eth_getLogs` and every event indexer are structurally blind to this channel. The cheap
detector is `eth_getTransactionCount(channel)` (currently 14) on any public RPC each refresh;
on increase, fetch bodies via Blockscout REST `/api/v2/addresses/{addr}/transactions`
(keyless, all 21 fit one page). Inbound replies need the same enumeration on a slower timer.
Classification: `from==to==channel` → self-post · `from==channel, to≠channel` → onchain
action (decode by selector) · `from==dev wallet` → funding · else community reply.

**Hazard:** the feed is attacker-writable by design (anyone can post) and already contains
newlines, typographic quotes and em-dashes. Every message must pass `safe_markup`.

## IMD — the wrapped, bridged FP

`BridgedFP is OFT` (LayerZero V2, verified source, solc 0.8.26, ~90 lines). No mint function:
supply exists only via `lzReceive` from owner-set peers — Base (the FP OFTAdapter
`0xAB152dB8…`) and Arbitrum. FP locks on Base, IMD mints 1:1 on mainnet
(sharedDecimals=6 — totalSupply is always a multiple of 1e12 wei). Confirmed by the dev's own
site vibecoins.ai: the token "originally launched as the Frenpet token on Base, now bridged to
Ethereum mainnet… arbitrage via layerzero bridging back and forth".

- Supply 2,376,731.87 IMD = **33.0%** of FP's 7,195,584.58; 1,148 holders; ~30,441 transfers.
- Renamed onchain twice via owner-only `updateNameAndSymbol`: "Fren Pet"/"FP" →
  "Vibe Coins"/"VIBE" (2026-01-07) → "Identity.md"/"IDM", typo-fixed to "IMD" (2026-05-15).
  **Treat name/symbol as mutable and attacker-adjacent**; GeckoTerminal still serves the stale
  VIBE name, DexScreener the current one.
- Governance: owner (dev) can `setPeer` to anything — i.e. can mint arbitrarily. A trust
  caveat, not a bug.
- Market: the v3 pool holds ~388k IMD + ~142.7 WETH (~$549k) after the 33.25 ETH add;
  price ≈ $0.71, 24h volume ≈ $244k, FDV ≈ $1.6M. FP on Base trades at near-parity with
  correlated moves — the parity spread is a real arbitrage/health metric.
- **Burn pipeline:** LP fees (IMD side) → BurnExecutor → OFT-send to a Base burn receiver →
  mainnet totalSupply decreases. Verified ledger from frenpet.eth: 12,039 IMD (05-16),
  31,064 (07-31), 15,745 (08-05) — the last two match announce posts to the minute. The ETH
  side of fees is *not* burned (16.1 ETH currently parked in frenpet.eth).

## IDMD — identity.md NFT

Solady ERC-721, verified source. `mint(uint256 id)`: free, ungated, caller picks the id
(0–1999), one per wallet, cap 2000. Minted out on launch day 2026-05-14 (the dev was buying
secondary 47 minutes after deploy). 667 holders; top-10 hold 17.1%, dev holds 3 (bought two
on OpenSea on 2026-08-08 — he is *buying his own collection*). ~38 transfers/day this week,
86% via Seaport. OpenSea floor was 0.219 ETH (public HTML, not a dependable keyless source).

Metadata is **100% onchain**: `tokenURI` → immutable renderer → base64 JSON embedding a
900×900 generative SVG. Traits (Archetype/Face/Palette/Halo/Signal Density) derive purely
from `keccak256("identity.md"‖id)` — a dashboard can compute any token's traits offline.

**The twist:** the NFT contract's ownership is **bricked at birth** — deployed through the
Arachnid CREATE2 proxy, `_initializeOwner(msg.sender)` made the *factory* the owner
(live-read confirmed: `owner()` = `0x4e59b448…`). Every `onlyOwner` setter (including
`setIdentityAllowed`, `setUniv4Hook`, `setUniv4Pool`) is permanently uncallable, so the
NFT's own identity feature is dead and its `Memory State` trait will read "Unwritten" forever.
The dev noticed same-day and deployed the separate **IdentityRegistry** with his address
hardcoded as owner, wrote token #0's identity in a single open-gate block
(`setIdentityAllowed(true)` → `setIdentityHash(0, bafkrei…, permanent=false)` →
`setIdentityAllowed(false)`), then transferred registry ownership to the announce EOA.
State today: gate **closed**, 1/2000 written, 0 permanent. IDMD #0 — the only written
identity — now belongs to the announce EOA itself. When "the agent" reopens the gate, any
IDMD holder can attach an IPFS identity file to their token. **Gate reopening is a headline
event** and is watchable via one `eth_call` (`identityAllowed()`) plus
`IdentityHashUpdated` logs (topic0 `0x57c85cf8…`).

## The upcoming Uniswap v4 hook (the "be early" event)

What it is (from X + announce channel + onchain): a **single-pool redesign of the Sato
mechanism** — SATO runs token issuance through a v4 hook with an exponential bonding curve
(mint into pool on demand, buy back and burn on sells) but needs two pools; Adam is
"trying to improve its weaknesses (mostly to not need 2 pools)". Status: **not deployed**.
All 19 existing IMD v4 pools are third-party hookless noise (every `Initialize` log has
`hooks=0x0`), including the $17.7k "VIBE/ETH 1%" pool — created by an unrelated EOA at fee
10002 (1.0002%). Neither dev wallet has ever touched the v4 PositionManager.

The dev *does* run one live v4 hook already: the Vibecoins launchpad hook (since 2026-01-06,
10 token launches). Its permission bits lack `beforeSwap`, so *that* code cannot gate
trading by NFT ownership — holder-gating exists only as a floated idea.

**Launch early-warning recipe (all keyless):** he committed onchain to announcing before
moving the LP. Watch, in escalating order: (1) announce-channel nonce; (2) v3 position
#1167726 liquidity (`NFPM.positions(1167726)` eth_call — a `DecreaseLiquidity` is the
smoking gun); (3) frenpet.eth nonce (29 lifetime txs, any activity is signal);
(4) PoolManager `Initialize` logs where currency is IMD **and hooks ≠ 0x0** — that log *is*
the launch; (5) OFT bridge-in mints to dev wallets (staging, as before the 33 ETH add:
bridge → mint → approve → add → announce inside 12 minutes).

## The agent / "P2P decentralized harness"

Registered on the canonical ERC-8004 IdentityRegistry (`0x8004A169…`, Draft ERC, live since
2026-01-29, 22k+ agents) as `identitymd-agent` — card is a stub (`active:false`). The
"P2P decentralized harness" teased 2026-05-22 is unnamed in public; on X: agent-built
projects (the OpenClaw evm-wallet skill, deprecated), Hermes bots watching the chain, and on
2026-08-08: "my agent thing just worked by itself for the first time… it's alive". Expect
the next experiment to surface here: watch the announce EOA's *outbound contract calls*
(like the register call, nonce 4) and the ERC-8004 registry for card updates
(`active:true` flip / services appearing).

## Cross-links to existing MaxPane dashboards

- The dev is an **active FWA player**: 20 Splitter claims since 2026-07-23 (the FWA splitter
  `0x1c175b9f…` is already in `fwa_client.py`), winnings swept to `0x58239Ad…` within ~1 min.
  Fun cross-over stat, but label it FWA income — it is *not* IMD economics.
- FrenPet on Base keeps running; the `frenpet` dashboard covers game state. The `surf`
  dashboard should show FP only as the bridge counterpart (parity, bridged share) — not
  duplicate game data.

## Keyless data-source recipes (all validated in this research)

| Need | Source | Notes |
|---|---|---|
| Channel new-post detect | `eth_getTransactionCount` on public RPC | ~free, every refresh |
| Channel bodies + replies | Blockscout REST `/api/v2/addresses/{a}/transactions` | GET, keyless, decodes calldata for us |
| Token/NFT supply, holders | Blockscout REST `/api/v2/tokens/{a}` + `/counters` | IMD totalSupply drop = burn |
| Pool price/liquidity live | `eth_call` slot0/liquidity/positions (publicnode) | hand-encoded, no web3 dep — pattern exists in `frenpet_client.py` |
| Market price/volume/24h | GeckoTerminal + DexScreener REST | GeckoTerminal serves stale token names — display onchain name |
| Logs (Initialize, IdentityHashUpdated, Seaport) | `eth_getLogs` via tenderly-public / drpc | publicnode refuses archive getLogs; state vs logs pools differ (CLAUDE.md) |
| ETH/USD | CoinGecko simple/price | already in `data/price.py` |
| NFT floor | — none keyless | OpenSea is keyed/Cloudflare-gated. Either parse Seaport `OrderFulfilled` logs for realized prices, or show explicit unavailable state. Never fake it |

## Hazards for implementation

1. **Attacker-controlled text everywhere**: announce messages (anyone can write), token
   name/symbol (owner-mutable, already changed twice), ENS names. `safe_markup` on all of it.
2. **Address poisoning is live on frenpet.eth**: 1-gwei lookalike senders
   (`0xF3083828…0Ee6` vs real `0xF3084Bc7…0eE6`) and homoglyph tokens (`ĖTḨ`, `UЅDС`) are in
   its transfer history *right now*. Any tx-feed widget must not render spoofed counterparties
   as trusted; prefer full addresses or verified-label allowlists.
3. **The channel emits no logs** — poll nonces, don't wait for events.
4. **Blockscout v1 `eth_call` is broken (HTTP 400)**; use the normal RPC POST stack for live
   reads. Blockscout REST v2 GETs are solid.
5. **A failed read is `None`, never `0`** — especially for totalSupply (a burn detector that
   turns an outage into a 2.37M→0 supply drop would fire a false BURN signal).
6. **The 33% bridged share and price parity are live values** — read, never hardcode (repo
   rule; the FP/IMD ratio moves with every bridge tx).

## Open questions (not blockers)

- Is the NFT-contract ownership brick intentional performance art or an accident the
  IdentityRegistry papered over? (Unknowable; doesn't change the design.)
- The EOE1 encrypted envelope tweeted 2026-07-27 (A256GCM/PBKDF2 format) — purpose unknown;
  no onchain counterpart found yet.
- Where the LP-fee ETH ultimately goes (`0xF3084Bc7…`, `0x61CC704c…` unidentified).
- The exact Base burn receiver address (burns verified by supply decrease + announce
  cross-match; receiver not resolved from local data).
