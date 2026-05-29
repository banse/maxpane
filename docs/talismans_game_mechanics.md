# Talismans — Game / Collection Mechanics

Research notes for the MaxPane **Talismans** dashboard (8th dashboard).

- **Project:** Talismans by tokenfox
- **Site:** https://talismans.tokenfox.art/ · mechanics: https://talismans.tokenfox.art/how-it-works
- **Chain:** Ethereum mainnet
- **Contract:** `0x724d5beffe9a84a87ad1af83713f80600e5f5774` — verified ERC721, name `Talismans`, symbol `TLSM`
- **Marketplaces:** OpenSea, Rarible (secondary only — mint has ended)

## Core idea: conservation, not burn

The defining mechanic is **core conservation**. Every token holds 1–4 *cores*. Operations
only *rearrange* cores between tokens — they never create or destroy them. The total number
of cores in the collection is an **invariant**; only the token count fluctuates.

> "Cores are conserved and the collection is always recoverable."
> "The total number of cores never changes; operations only move cores around."

This is the opposite of a burn-and-mint economy. There is **no fungible token, no price/reward
economy, and no seasons** — the dashboard's story is the living *ecology* of the collection.

## Supply & genesis

- Fixed genesis of **1,536** unique tokens, minted across phases:
  - up to 36 artist proofs
  - 1,500 public (allowlist → open)
  - unsold remainder minted to the artist
- Live token count fluctuates post-mint (operations change it); total cores stay fixed.
- Genesis is pole-balanced: ~768 Lithic and ~768 Lumic at mint.

## Essences (3)

| Essence | Pole | Materials | Minted? |
|---------|------|-----------|---------|
| **Lithic** | matter | 16 | yes (natural mint) |
| **Lumic** | event | 16 | yes (natural mint) |
| **Mythic** | myth synthesis | — | **never minted** — only *forged* when a token's cores span both poles |

## Tiers (cores per token)

Random distribution at mint; average yield ≈ 2 cores.

| Tier | Cores | Probability |
|------|-------|-------------|
| Raw  | 1 | 40% |
| Cut  | 2 | 30% |
| Fine | 3 | 20% |
| Prime| 4 | 10% |

"Eight-core ceiling" exists for Prime Mythic tokens (a Mythic can hold up to 8 because it
spans two 4-core poles). Within a single material the ceiling is 4 cores.

## The four operations (reversible)

All operations conserve cores; they change the token count by ±1.

| Operation | Scope | Effect | Token Δ | Status at launch |
|-----------|-------|--------|---------|------------------|
| **Bond**  | across poles | fuse a matter token + an equal-size event token → one **Mythic** | −1 | **enabled** |
| **Cleave**| across poles | split a Mythic back into its matter pile + event pile | +1 | **enabled** |
| **Cut**   | within material | split a token into two of the same material & form | +1 | **disabled** (rolls out later as "tier mobility") |
| **Merge** | within material | recombine two of the same material & form, up to the 4-core ceiling | −1 | **disabled** (rolls out later) |

So: **Bond ⇄ Cleave** is the cross-pole / Mythic axis; **Cut ⇄ Merge** is the within-material
size axis. Bond/Cleave are live now; Cut/Merge launch disabled and are enabled later — the
dashboard surfaces this as a state signal.

## Onchain surface (verified contract)

Read functions confirmed on Etherscan:

- `coreCount(tokenId)` — number of cores in a token (→ tier)
- `coresOf(tokenId)` — the cores themselves (pole/material encoding — **exact return shape TBD, see abi_recon**)
- `tokenURI(tokenId)` — metadata
- `isRevealed()` · `ownerOf` · `balanceOf` · `royaltyInfo` (ERC2981)
- minting used commit/reveal; transform settings are frozen/immutable

Events confirmed:

- `Bonded` · `Cleaved` · `Cut` · `Merged` — the four operations
- `Transfer` (standard ERC721) · `MetadataUpdate`

These events + `coresOf`/`coreCount` over the ~1,536-token id space (cheap via Multicall3)
are sufficient to reconstruct the full ecology keylessly.

## Open technical question

The **decode of `coresOf()`** — how each core encodes pole/material/tier — is the one unknown.
Resolve in `docs/talismans_abi_recon.md` before implementation. If essence/material is only
available via `tokenURI` JSON (offchain/IPFS) rather than derivable from `coresOf`, the data
layer fetches metadata via a keyless gateway and caches it.

## Dashboard implications

- No market/price data (decision: pure onchain ecology).
- Hero = invariant + ecology state; activity feed = the four operations; signals = conservation
  check + Cut/Merge lock state + forge momentum + Mythic scarcity.
- Small id space (~1,536) → full-collection enumeration each cycle is cheap (unlike TTT's 10k).
