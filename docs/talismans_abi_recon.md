# Talismans (TLSM) ABI Reconnaissance

Source: **verified Solidity source pulled from Sourcify (EXACT match)** for the
single contract `src/Talismans.sol` plus its libraries (`TalismanCore`,
`TalismanMaterials`, `TalismanTransformationLib`, `TalismanForms`,
`TalismanStructs`). All view/log probes validated live against the public
keyless RPC `https://ethereum.publicnode.com` (Cloudflare was flaky during
recon; publicnode is the reliable keyless endpoint and is the only tried RPC
that exposes `web3_sha3`).

Confirmation date: **2026-05-29**, at mainnet block **25203610**.

Full verified ABI saved to: `/Library/Vibes/autopull/docs/talismans_abi.json`
(149 entries: 79 functions, 22 events, plus errors + constructor).

## Address / checksum gotcha (read this first)

The address handed to recon, `0x724d5beffe9a84a87ad1af83713f80600e5f5774`, has
a **broken EIP-55 checksum** when mixed-case variants are tried. The Sourcify v2
API rejects a bad checksum with HTTP 400 `Invalid address`. The **correct
checksum** is:

```
0x724D5bEffe9A84a87AD1Af83713F80600E5f5774
```

(note `724D5b...`, not `724d5b...`). Lowercase works for `eth_call`/`eth_getLogs`
(RPCs don't checksum), but Sourcify needs the checksummed form. Computed via
`web3_sha3` of the ASCII address bytes -> EIP-55.

The legacy Sourcify repo path (`repo.sourcify.dev/contracts/full_match/...`) now
**307-redirects** to `sourcify.dev/server/...` and the old path is dead. Use the
**v2 API** instead:

```
https://sourcify.dev/server/v2/contract/1/0x724D5bEffe9A84a87AD1Af83713F80600E5f5774?fields=abi,metadata,sources
```

Etherscan's keyless V1 `getabi` endpoint is **dead** ("deprecated V1 endpoint,
switch to V2") — V2 requires a key. Sourcify is the keyless winner here.

## Contract addresses (Ethereum mainnet, chain id 1)

| Contract                    | Address                                      | Verified | Source                       |
|-----------------------------|----------------------------------------------|----------|------------------------------|
| Talismans (ERC721, TLSM)    | `0x724d5beffe9a84a87ad1af83713f80600e5f5774` | yes      | Sourcify (EXACT match)       |
| TalismanMaterials (table)   | `0xf106ec35734457581566b53db0f71252bbce2f33` | unknown  | `Talismans.materials()` read |
| Renderer (on-chain art)     | `0xe0d5d29507ba2672d1af8eafab9796a181167778` | unknown  | `Talismans.renderer()` read  |
| Multicall3                  | `0xca11bde05977b3631167028862be2a173976ca11` | yes      | canonical, code present      |

`materials()` and `renderer()` are external contracts the NFT delegates to.
**The materials table contract is needed for the per-core essence lookup**
(`elementOf(uint8)`) if you decode cores yourself; the renderer is only needed
for art (tokenURI already proxies to it).

## Live values read during recon (block 25203610)

| View call (selector)                | Returned value                                  |
|-------------------------------------|-------------------------------------------------|
| `name()` 0x06fdde03                 | `"Talismans"`                                   |
| `symbol()` 0x95d89b41               | `"TLSM"`                                         |
| `totalSupply()` 0x18160ddd          | `0x5a8` = **1448** (live token count)           |
| `genesisMinted()` 0x153de143        | `0x600` = **1536** (all genesis minted)         |
| `MAX_GENESIS_SUPPLY()` 0x738e7218   | `0x600` = **1536**                              |
| `MAX_CORES_PER_TOKEN()` 0xd7a711a5  | **8** (NOT 4 — see surprises)                   |
| `materials()` 0xb6b7ae59            | `0xf106ec35734457581566b53db0f71252bbce2f33`    |
| `renderer()` 0x8ada6b0f             | `0xe0d5d29507ba2672d1af8eafab9796a181167778`    |
| `bondAndCleaveEnabled()` 0xd11543fd | `true`                                          |
| `cutAndMergeEnabled()` 0xdafa0f1a   | `false` (currently disabled)                    |
| `coreCount(1)` 0xf22a6113           | `2`                                             |
| `isRevealed(1)` 0x5055fbc3          | `true`                                          |
| `isGenesis(1)` 0xf1e25ea8           | `true`                                          |

**totalSupply (1448) < genesisMinted (1536)**: net 88 tokens have been removed
by bond/merge operations (each Bond/Merge is `-1` token). The live id space is
sparse and ids exceed 1536 (new Cut/Cleave/mint ids count up from 1537+).

## Core encoding — THE key finding: how to read pole / material / tier

`coresOf(uint256) -> uint256[]` returns the token's array of **packed `uint256`
cores**. Each core's bit layout (from `TalismanCore.sol`, LSB = bit 0):

| Bits   | Width | Field        | Accessor                  |
|--------|-------|--------------|---------------------------|
| 0..5   | 6     | `materialId` | `core & 0x3f`             |
| 6..9   | 4     | `shapeForm`  | `(core >> 6) & 0xf`       |
| 10..25 | 16    | `seed`       | `(core >> 10) & 0xffff`   |
| 26..255| 230   | reserved     | mask only what you own    |

There is **NO pole bit and NO tier bit inside a core.** Derive them:

- **Tier = `coreCount(tokenId)` = `coresOf(tokenId).length`.**
  1 -> `Raw`, 2 -> `Cut`, 3 -> `Fine`, 4 -> `Prime`. (Confirmed by source
  comment and by tokenURI: token #1, 2 cores, Tier="Cut".) NOTE the contract
  allows up to **8 cores** (`MAX_CORES_PER_TOKEN`), so tiers >4 exist for
  heavily-bonded Mythics; names for 5..8 are decided by the (unverified)
  renderer — read them from `tokenURI` rather than hardcoding.

- **Pole / Essence is a property of the MATERIAL, looked up per core.**
  Call `TalismanMaterials.elementOf(uint8 materialId) -> (Essence essence,
  uint8 bitmask)` on the materials contract. `Essence` enum:
  `0=Lithic, 1=Lumic, 2=Mythic`.

- **Token-level material/form/seed are DERIVED (folded), not just core[0]:**
  - `coreMaterialId(tokenId)` -> `deriveMaterialId`: scans all cores, sets
    `hasLithic/hasLumic/hasMythic`, XOR-folds element bitmasks, then output
    essence = Mythic if (any Mythic core) OR (has both Lithic and Lumic);
    else Lithic if any Lithic; else Lumic. Final id =
    `materialsFromSignature(outEssence, foldedBitmask)`. This is the
    cross-pole synthesis rule (Lithic + Lumic -> Mythic).
  - `coreShapeForm(tokenId)` -> `deriveShapeForm`: most-common form across
    cores wins (tie -> higher-index core).
  - `coreSeed(tokenId)` -> `deriveSeed`: XOR of distinct per-core seeds.

  So the per-token `coreMaterialId/coreShapeForm/coreSeed` accessors return a
  FOLDED value that does NOT equal `coresOf[0]`'s fields. Verified: token #1
  `coresOf` = `[0xce1880, 0x54e880]` (both materialId=0, form=2, seeds 13190 &
  5434), but `coreSeed(1)` = `0x26bc` (9916 = 13190 XOR 5434), while
  `coreMaterialId(1)`=0 and `coreShapeForm(1)`=2. Use the **accessors** for
  token-level traits; use **raw `coresOf`** only when you need per-core detail.

### Material id -> essence table (from verified `getMaterial` switch)

Essence is **NOT contiguous by id range.** Ids 0..31 are interleaved 16 Lithic
+ 16 Lumic; ids 32..47 are all Mythic. There are **48 materials**
(`MATERIAL_COUNT=48`), `NON_MYTHIC_MATERIAL_COUNT=32`. You MUST look up essence
per id; do not assume `id<16 = Lithic`. Names by id:

```
0 Aurora=Lumic   1 Foxfire=Lithic   2 Pulsarlike=Lumic   3 Amethyst=Lithic
4 Citrine=Lithic 5 Fire Obsidian=Lithic 6 Duskhollow=Lumic 7 Sakura=Lumic
8 Rainforest=Lumic 9 Embermade=Lithic 10 Abyss=Lumic 11 Bloodmoon=Lumic
12 Sugilite=Lithic 13 Bored Ruby=Lithic 14 Dawnstone=Lithic 15 Diamond=Lithic
16 Rock=Lithic 17 Daystar=Lumic 18 Tsavorite=Lithic 19 Rhodochrosite=Lithic
20 Copper=Lithic 21 Foxglow=Lumic 22 Sealume=Lumic 23 Aquamarine=Lithic
24 Blazar=Lumic 25 Sproutsong=Lumic 26 Heartfern=Lumic 27 Moss=Lumic
28 Cobalt=Lithic 29 Emerald=Lithic 30 Wisp=Lumic 31 Twilight=Lumic
32 Corona  33 Strobeflora 34 Sigil 35 Smokeblossom 36 Saint Spectrum
37 Cypher 38 Aether 39 Deadform 40 Nullbloom 41 Reliquary 42 Duskcode
43 Phosphor 44 Celestial 45 Corposant 46 Wraithseal 47 (else branch) = all Mythic
```

Distribution over 0..31: **16 Lithic, 16 Lumic**. Over 32..47: **16 Mythic**.
Easiest robust path: read each material's name + essence directly from
`materialName(id)` / `essenceName(...)` / `elementOf(id)` on the materials
contract, or just read the rendered traits from `tokenURI`.

## Metadata: FULLY ON-CHAIN (data: URI, base64 SVG + HTML)

`tokenURI(uint256) -> string` returns an on-chain
`data:application/json;base64,...` blob (token #1 was 27,013 bytes). Decoded
JSON for token #1:

```json
{
  "name": "Talisman #1",
  "image": "data:image/svg+xml;base64,...",
  "animation_url": "data:text/html;base64,...",
  "attributes": [
    {"trait_type":"Material","value":"Aurora"},
    {"trait_type":"Chroma","value":"Variegated"},
    {"trait_type":"Essence","value":"Lumic"},
    {"trait_type":"Form","value":"Pendant"},
    {"trait_type":"Tier","value":"Cut"},
    {"trait_type":"Cores","value":2},
    {"trait_type":"Seed","value":"0x26bc"},
    {"trait_type":"Genesis","value":true}
  ]
}
```

**No IPFS, no HTTPS — everything is on-chain.** Essence, Material, Tier, Form,
Chroma, Cores, Seed, Genesis are all present in the tokenURI attributes, so a
dashboard can get every trait from `tokenURI` alone (no separate materials-table
calls) — but tokenURI is heavy (~27 KB each). For bulk enumeration, prefer the
cheap reads `coresOf` + `coreCount` + `coreMaterialId` + per-id essence lookup,
and reserve `tokenURI` for single-token detail views.

There are also lighter art surfaces: `tokenImage(id)->string` (SVG only),
`tokenView(id)->string`, `tokenShape(id)->bytes`.

## Events — full arg layouts + computed topic0 (all validated live)

topic0 = keccak256 of the canonical signature, computed via `web3_sha3` on
publicnode and cross-checked against live `topic[0]` in blocks
25153611-25203610.

### Transformation events

| Event | Canonical sig | topic0 |
|-------|---------------|--------|
| `Bonded` | `Bonded(uint256,uint256,uint256,address)` | `0xf4d7559aa146406a2a7769decb3cc99cb5c91d0c4b37c8c48ef43b5df27dac8d` |
| `Cleaved` | `Cleaved(uint256,uint256,uint256,address)` | `0x46ba0b66389416f9b9efdb0acff2fa246aeca62e3a0b23cf1f2503daef255209` |
| `Cut` | `Cut(uint256,uint256,uint256,uint256,address)` | `0x8a931aa6e7978064180abf7fe0fad5724567980368d0620b07f12c150063455a` |
| `Merged` | `Merged(uint256,uint256,uint256,address)` | `0x16c20a9d07670de1acd6a4887d37d0bd6e908958838c007bdab074541130d1e0` |

Arg layouts (indexed = goes in topics):

- **`Bonded(uint256 indexed tokenIdA, uint256 indexed tokenIdB, uint256 indexed bondedId, address operator)`**
  topics = [topic0, tokenIdA, tokenIdB, bondedId]; data = `operator` (32-byte
  padded address). Bond fuses A + B (opposite poles, equal core counts) into a
  Mythic `bondedId`, **−1 token**. Live sample (block 25188761):
  topics `[..., 0x106, 0x107, 0x601]`, data
  `0x...b9bb10d46ef46068b876f0ffa27016eca5dee8ab` -> tokenIdA=262,
  tokenIdB=263, bondedId=1537, operator=0xb9bb...e8ab. (bondedId 1537 > 1536
  confirms output ids count up beyond genesis.) **106 Bonded events** in the
  recon window.

- **`Cleaved(uint256 indexed tokenId, uint256 indexed lithicId, uint256 indexed lumicId, address operator)`**
  topics = [topic0, tokenId, lithicId, lumicId]; data = operator. Splits a
  Mythic back into a Lithic + a Lumic, **+1 token**. **18 events** in window.

- **`Cut(uint256 indexed tokenId, uint256 indexed headId, uint256 indexed tailId, uint256 index, address operator)`**
  topics = [topic0, tokenId, headId, tailId]; **data = `(uint256 index,
  address operator)`** (TWO non-indexed fields, 64 bytes). `index` is the core
  split point. Splits one token into two, **+1 token**. **0 events** in window
  (cut/merge currently disabled).

- **`Merged(uint256 indexed tokenIdA, uint256 indexed tokenIdB, uint256 indexed mergedId, address operator)`**
  topics = [topic0, tokenIdA, tokenIdB, mergedId]; data = operator. Recombines
  two same-material tokens into one, **−1 token**. **0 events** in window.

### Other useful events

| Event | Canonical sig | topic0 |
|-------|---------------|--------|
| `Transfer` | `Transfer(address,address,uint256)` | `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` |
| `MetadataUpdate` (ERC-4906) | `MetadataUpdate(uint256)` | `0xf8e1a15aba9398e019f0b49df1a4fde98ee17ae345cb5f6b5e2c27f5033e8ce7` |

Also present in ABI (not topic-hashed here, mostly admin): `Approval`,
`ApprovalForAll`, `TransformationApprovalForAll`, `BatchMetadataUpdate`,
`MaterialsUpdated`, `MaterialsFrozen`, `RendererUpdated`, `RendererFrozen`,
`MinterUpdated`, `RoyaltyUpdated`, `RoyaltyEnforcementDisabledForever`,
`TransformationSettingsUpdated`, `TransformationSettingsFrozen`,
`OwnershipTransferStarted`, `OwnershipTransferred`, `TransferValidatorUpdated`.

`MetadataUpdate(tokenId)` fires whenever a token's cores change (the on-chain
art is re-derived) — a useful "something happened to this token" signal in
addition to the four transformation events.

## Exact read-function signatures (the ones a dashboard needs)

```
coresOf(uint256 tokenId)        -> uint256[]   (raw packed cores; see bit layout)  [0xfb8a4957]
coreCount(uint256 tokenId)      -> uint256      (= cores.length = tier)            [0xf22a6113]
coreMaterialId(uint256 tokenId) -> uint8        (FOLDED token-level material id)   [0xea67f790]
coreShapeForm(uint256 tokenId)  -> uint8        (enum TalismanForms.ShapeForm)     [0xb4a1984f]
coreSeed(uint256 tokenId)       -> uint16       (FOLDED token-level seed)          [0xea0e2d0d]
tokenData(uint256 tokenId)      -> (uint256[] cores, uint8 materialId, uint8 form, uint8 coreCount, uint16 seed)  [0xb4b5b48f]
isRevealed(uint256 tokenId)     -> bool         (cores.length > 0)                 [0x5055fbc3]
isCleavable(uint256 tokenId)    -> bool         (revealed Mythic spanning both poles)
isGenesis(uint256 tokenId)      -> bool  (pure)                                    [0xf1e25ea8]
tokenURI(uint256 tokenId)       -> string       (on-chain data: URI JSON)          [0xc87b56dd]
tokenImage(uint256 tokenId)     -> string       (on-chain SVG)
ownerOf(uint256 tokenId)        -> address
balanceOf(address owner)        -> uint256
tokensOfOwner(address owner)    -> uint256[]     (enumerate a wallet, no log replay)[0x8462151c]
totalSupply()                   -> uint256                                          [0x18160ddd]
genesisMinted()                 -> uint256                                          [0x153de143]
royaltyInfo(uint256,uint256)    -> (address receiver, uint256 amount)
coreRarityWeights()             -> uint256[]  (pure; [40,30,20,10] -> Raw/Cut/Fine/Prime mint weights)
```

`tokenData` is the **single best per-token read**: one call returns cores +
folded materialId + form + coreCount + seed. Layout decoded live for token #1:
`cores=[0xce1880,0x54e880], materialId=0, form=2, coreCount=2, seed=0x26bc`.

**ABI-encoding gotcha (load-bearing for the decoder):** because the returned
tuple contains a dynamic `uint256[]`, the *whole tuple is dynamic*, so the
return is wrapped behind a **leading head offset word** (`0x20`). The real
on-chain bytes for `tokenData(1)` are:
`word0=0x20` (tuple offset) · `word1=0xa0` (cores[] offset, relative to the
tuple start at word1) · `word2=materialId` · `word3=form` · `word4=coreCount`
· `word5=seed` · `word6=cores length` · `word7..=cores`. A decoder MUST
dereference word0 first and read the tuple head starting at word1 — reading
materialId/coreCount from words 1-4 directly (skipping the wrapper) yields
garbage (materialId=0xa0, inflated coreCount).

`ShapeForm` enum (index -> name): `0 Brilliant, 1 Cushion, 2 Pendant, 3 Block,
4 Dome, 5 Shard, 6 Jagged, 7 Orb, 8 Dagger, 9 Teardrop, 10 Cluster, 11 Geode,
...` (enum continues; first 12 confirmed from source).

## Token enumeration strategy

There is **NO ERC721Enumerable `tokenByIndex`** (not in ABI). Strategy:

1. The live id space is **sparse and unbounded above 1536** (Bond/Cut/Cleave
   mint fresh ids; Merge/Bond burn ids). `totalSupply()` (1448) is a count, not
   a max id. You cannot just iterate `1..totalSupply`.
2. **Genesis ids are `1..1536`** (`isGenesis` is pure; genesis range fixed by
   `MAX_GENESIS_SUPPLY`). Transformation-output ids start at 1537 and climb;
   read the running counter via `nextTransformId()` to know the current upper
   bound, then probe `1..nextTransformId()`.
3. **Multicall3 (`0xca11bde05977b3631167028862be2a173976ca11`, code present /
   callable)** is the enumeration tool: batch `aggregate3` calls of
   `coreCount(id)` + `coresOf(id)` + `ownerOf(id)` across the id range.
   `ownerOf` reverts for nonexistent/burned ids, so use `aggregate3`
   (per-call `allowFailure=true`) and treat reverts as "id not live."
   `coreCount==0` also flags burned/never-existent ids.
4. For **per-wallet** views, `tokensOfOwner(address)` returns all live ids for
   an owner in one call — no log replay needed.
5. For an **activity feed**, replay the four transformation event topic0s +
   `Transfer` via `eth_getLogs`. **publicnode caps `eth_getLogs` at 50,000
   blocks per request** (error `-32701 exceed maximum block range: 50000`), so
   page in <=50k-block chunks.

## Surprises / corrections vs the background brief

1. **MAX_CORES_PER_TOKEN = 8, not 4.** The brief said tokens hold 1–4 cores.
   On-chain max is **8**. Tiers Raw/Cut/Fine/Prime map to 1/2/3/4 cores, but a
   bonded Mythic can exceed 4 cores; tier names for 5..8 live in the
   (unverified) renderer — read them from `tokenURI`, don't hardcode.

2. **Cores encode only materialId + shapeForm + seed.** No pole bit, no tier
   bit. **Pole/essence is looked up from the material** via
   `TalismanMaterials.elementOf(id)`; **tier is the core count.** This is the
   single most load-bearing correction for any decoder.

3. **Essence is NOT a contiguous id range.** Ids 0..31 interleave 16 Lithic +
   16 Lumic; 32..47 are Mythic. Always look up essence per material id.

4. **Event names are exactly `Bonded/Cleaved/Cut/Merged`** (match brief), but
   each carries a trailing **non-indexed `address operator`**, and **`Cut` has
   an extra non-indexed `uint256 index`** (5 args, 2 non-indexed data fields).
   Don't assume all four have identical layouts.

5. **`cutAndMergeEnabled()` is currently `false`** (bond/cleave enabled). Zero
   Cut/Merged logs exist in recent history — the dashboard should treat
   cut/merge as a (currently-disabled) toggleable feature, gated by
   `cutAndMergeEnabled()` / `bondAndCleaveEnabled()`, both of which can be
   frozen via `transformationSettingsFrozen()`.

6. **Metadata is 100% on-chain** (data: URI base64 SVG + HTML animation_url).
   No IPFS/HTTPS. tokenURI is large (~27 KB); use cheap accessors for bulk.

7. **Token-level material/form/seed accessors return FOLDED values**, not
   `coresOf[0]`. `coreSeed` = XOR of distinct core seeds; `coreShapeForm` =
   modal form; `coreMaterialId` = synthesised essence+bitmask. Confirmed live.

8. **Address checksum + Sourcify path matter.** Use checksummed
   `0x724D5bEffe9A84a87AD1Af83713F80600E5f5774` and the v2 API
   (`sourcify.dev/server/v2/...`); the old `repo.sourcify.dev` path 307s away
   and Etherscan keyless V1 `getabi` is dead.

9. **No `tokenByIndex`/Enumerable.** Enumerate via Multicall3 over
   `1..nextTransformId()` with `allowFailure`, or `tokensOfOwner` per wallet.

## Things I could NOT determine

- **Renderer + TalismanMaterials verification status:** their source is not on
  Sourcify (only the main NFT is). Their ABIs can be reconstructed from the
  interfaces (`ITalismanRenderer`, the `TalismanMaterials` source is bundled in
  the NFT's verified source set so its full ABI IS known) — `elementOf`,
  `materialName`, `materialColors`, `essenceName`, `materialIdFromSignature`
  etc. are all in the bundled `src/TalismanMaterials.sol`.
- **Tier names for core counts 5–8** (renderer-defined; read from tokenURI).
- **`nextTransformId()` current value** was not probed live (selector exists in
  ABI; recommend reading it to bound enumeration). Genesis range `1..1536` is
  confirmed.
- A live **`Cut`/`Merged` data layout** could not be sampled (none in last
  ~600k blocks since cut/merge is disabled); layouts above are from the
  authoritative verified ABI, not an observed log.

## Files this recon produced

- `docs/talismans_abi.json` — full verified ABI (149 entries) from Sourcify
- `docs/talismans_abi_recon.md` — this document
