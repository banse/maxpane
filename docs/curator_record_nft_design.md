# THE LIST — onchain record NFT: design

An ERC-721 collection that lets a member of THE LIST claim, on chain, a permanent record of
what their wallet did in the game. Claiming is permissionless and reads the game contract
directly; the token's art and metadata are fully on chain; and the collection has no owner.

**Status: design approved 2026-08-18, nothing implemented.** This document is the specification.
The implementation plan is a separate artifact and does not exist yet. No contract has been
written, compiled or deployed.

**Scope boundary.** The contracts are a **separate Foundry repository**, not part of this one.
MaxPane's first hard constraint is that no signer, transactor or deploy key exists anywhere in
it, and a contracts package brings all three by definition. What this repo gains is (a) an
optional keyless exporter inside `sybilkit`, and (b) optionally, a read-only line in the curator
dashboard showing whether the configured wallet has claimed. Neither signs anything.

---

## 1. What the chain already knows

This is the finding the whole design rests on, so it comes first.

THE LIST (`WhitelistCurator`, `0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`, Ethereum mainnet,
deployed 2026-08-16 19:58:47 UTC in block 25 769 870) is verified, non-upgradeable, unpausable,
and has no mutable parameter. Its eight config values are `immutable` and `POINTS_PER_ETH` is a
`constant`. Its only privileged function sweeps force-fed ETH.

**Points are a real view, not an off-chain derivation.** `weight` is stored per address;
`pointsOf(address)` recomputes the sqrt curve from it at read time. A claim contract can ask the
game what a wallet scored and get the authoritative answer with no attestation of any kind.

| fact | how a contract gets it | selector |
|---|---|---|
| membership + join hour | `firstHourOf(address) → (uint256 hour, bool hasJoined)` | `0xc5148173` |
| points | `pointsOf(address) → uint256` | `0xcf6a4403` |
| weight | `weightOf(address) → uint256` | `0xdd4bc101` |
| credit (high-water) | `contributedBy(address) → uint256` | `0x64a8e570` |
| deposits | `txCountOf(address) → uint256` | `0x662d7299` |
| game finished | `isSettled() → bool` | `0x3270bb5b` |

**`isSettled()` is the design's key lever.** It is derived, not pushed: it returns true the
instant a completed judged hour falls short, whether or not anybody ever calls `settle()` and
whether or not a `Settled` event ever fires. It is monotonic. Once true, every per-address view
above is frozen for ever. A post-settlement live read is therefore functionally a snapshot with
none of a snapshot's trust assumptions.

**What the chain does NOT know**, and cannot be made to know:

- **The join index.** `FirstDeposit` emits a 1-based monotonic index (topic 2) equal to
  `totalContributors` at that instant, and the `Contributor` struct never stores it. It exists
  only in the log. Any "Nth on the list" or early-cohort fact must come from a log sweep.
- **Rank and points-share.** There is no `totalPoints` accumulator and no rank view; `stats()`
  returns volume, people and txs only. These are not merely absent, they are underivable.
- **Linkage.** The cluster analysis needs per-transaction gas fingerprints and first-funder
  lookups over a REST API. No EVM contract can reach either.

### 1.1 The `firstHour + 1` trap

The raw `contributors(address)` getter (`0x1f6d4942`) returns `firstHour + 1`, where `0` means
"never deposited". Reading it and treating word 4 as the hour makes **every non-member render as
an hour-0 founder** — the rarest cohort in the game. This repo deliberately refuses to vendor
that getter for exactly this reason.

**Rule: membership and hour come from `firstHourOf`, both return words, always.** The test that
a non-member cannot claim and does not read as hour 0 is the single most valuable test in the
suite.

---

## 2. Decisions taken

Each was ruled by the user during design. The rationale is recorded because a later reader will
otherwise re-litigate them.

| # | decision | why |
|---|---|---|
| D1 | **Claim reads the chain; no merkle root gates it** | Points, hour and membership are all on chain. A root would re-import trust the chain already eliminates, and give someone the power to exclude a member. |
| D2 | **One token, live until sealed** | The renderer reads live from the game; after settlement a holder may `seal()` once, copying the final numbers into the token's own storage. This replaces an earlier burn-and-remint idea (§9.1). |
| D3 | **Transferable, with the claimant recorded** | Tokens trade; the metadata describes the wallet that claimed, not whoever holds it now, and exposes `Held by claimant` so the difference is visible. |
| D4 | **Every member, one token per wallet** | `hasJoined` is the whole gate. Nobody is excluded by a judgement, and no floor is arbitrary except the contract's own. |
| D5 | **No linkage flag; certification is positive-only and optional** | See §7. The collection ships with no attestation and may never gain one. |
| D6 | **OpenSea rarity ranking is not a design goal** | Ruled explicitly. Metadata is honest rather than shaped for a ranker (§9.2). |
| D7 | **KISS; as much on chain as possible; no owner** | Fully on-chain art and metadata, an immutable renderer, no admin function on the collection. |
| D8 | **Metadata carries raw primitives so sub-groups stay computable** | §5.2. |
| D9 | **Collection name `THE LIST`** | Symbol `LIST` unless the user says otherwise — the one detail assumed rather than ruled. |
| D10 | **The description does not mention the optional certification** | Ruled. Nothing in the shipped text refers to a layer that may never exist. |
| D11 | **The user runs the deploy** | No key, no deploy, and no transaction is ever produced from this repo or by an agent. |

---

## 3. Contracts

Three, one of which is optional and may never be published.

### 3.1 `ListRecord` — ERC-721, no owner

Immutables: the game contract address, and the renderer address. **No `Ownable`, no admin
function, no pause, no mint price, no withdraw.** The contract holds no ETH and has nothing to
rug.

```
claim()                     → mints to msg.sender
claimFor(address member)    → mints to member, never to the caller
seal(uint256 tokenId)       → holder-only, post-settlement, once
announceSettled()           → permissionless, once: emits ERC-4906 BatchMetadataUpdate
tokenOf(address) → uint256  → 0 when unclaimed; doubles as the double-claim guard
```

`announceSettled` exists because the collection has **no owner**, and something must still tell
marketplaces to re-read every token when the game freezes. It requires `isSettled()`, may be
called once, and does nothing but emit — so leaving it permissionless costs nothing and depends
on nobody. Without it the ownerless design would have had no way to trigger the one refresh that
matters.

`claim` requires `hasJoined` from `firstHourOf(msg.sender)`. Token ids are sequential from 1, so
**the id is the claim order** — a scarcity dimension that cannot be acquired retroactively.
Double-claim prevention costs no extra storage: `tokenOf` is a mapping worth having as a public
lookup anyway, and its non-zero value is the guard.

`claimFor` always mints to the named member, so a third party can sponsor gas with no way to
redirect the token.

Per token, stored at claim: the **claimant** address (tokens are transferable) and the **game
hour at which it was claimed**.

`seal` copies points, weight, credit, deposits and join hour into the token's own storage —
packed — records the seal timestamp, and emits ERC-4906 `MetadataUpdate`. It is holder-only by
choice: that keeps the ritual and the self-selection, and a token whose wallet is lost simply
stays unsealed, which is honest. **After sealing, the token no longer depends on the game
contract being readable at all.**

### 3.2 `ListRecordRenderer` — pure view, immutable

All `tokenURI` logic. It is a separate contract only because of the 24 576-byte code limit, and
it is an `immutable` constructor argument with **no setter** — there is no upgrade path and no
way for anyone to change anybody's art. It reads: stored values when the token is sealed, live
values from the game when it is not, and attested values from §7 when they exist.

### 3.3 `ListAttestations` — optional, deployed empty

`Ownable2Step`, holding one merkle root and a monotonic epoch, lifted from chaincred's
`ScoreMerkleRoot` including its one-epoch grace window so a proof fetched just before a rotation
does not die in flight.

```
attach(address account, bytes32 traitKey, bytes32 value, bytes32[] proof)   // permissionless
```

Storage is `mapping(address => mapping(bytes32 => bytes32))`. **Deploy it with no root ever
published** — then every attested trait simply does not exist, the renderer's address stays
immutable, and the decision to use it at all can be made later or never. Its owner can only
*add* traits; it can never touch a claim, a seal, or any chain-derived number.

---

## 4. Lifecycle

```
   member claims (any time)                    game settles                holder seals
  ─────────────────────────────────────────────────────────────────────────────────────►
   token exists, renderer reads LIVE          values frozen by the      values copied into
   from the game; points may still rise       chain itself             the token; art gains
                                                                       the sealed frame
```

Minting before settlement is safe **because** the renderer is live: a wallet that escalates
after claiming sees its own token update rather than invalidate. That is the whole reason D2
works.

**Marketplace caching is the one honest limitation.** `tokenURI` is truthful whenever it is read
directly, but marketplaces cache, so a live token's points can be stale on a listing page. The
design emits ERC-4906 on transfer (so `Held by claimant` stays honest), on `seal`, and once for
the whole collection via `announceSettled`. It does not, and cannot sensibly, emit on every
points change. The description says so.

---

## 5. Metadata

`tokenURI` returns a base64 JSON data URI. The SVG is embedded inside it as a **plain
URL-encoded** `data:image/svg+xml,` — never base64 inside base64 (§6.2).

### 5.1 Traits

| trait | type | source |
|---|---|---|
| `Points` | number | `pointsOf`, or stored if sealed |
| `Weight (ETH)` | number | `weightOf` |
| `Credit (ETH)` | number | `contributedBy` |
| `Deposits` | number | `txCountOf` |
| `Hour` | string, e.g. `hour 0` | `firstHourOf` |
| `Window` | string, `grace` \| `judged` | hour < 24 |
| `Claim Order` | number | token id |
| `Status` | string, `live` \| `settled` \| `sealed` | token state + `isSettled()` (§6.1) |
| `Claimant` | string, address | stored at claim |
| `Held by claimant` | string, `yes` \| `no` | `ownerOf` vs claimant |

Three further traits — `Join Index`, `Early Cohort`, `Independent` — exist **only** if a root is
ever published, and are **absent** otherwise. Never `"none"`, never `false`. A value nobody
measured must not render as a measured zero; that is this repo's rule and it carries over.

`Hour` is a string because it is a cohort name, not a quantity. There is deliberately **no
multiplier-band trait**: the band edges are a presentation choice in the dashboard's own words,
they are derivable from `Weight ÷ Credit`, and freezing a UI decision into permanent metadata
ages badly.

### 5.2 Sub-groups stay computable

Raw primitives, never pre-baked bands. From the collection's metadata alone anyone can refold:

- **hour cohorts** — group by `Hour`
- **multiplier bands** — `Weight ÷ Credit` *is* the effective multiplier, so whoever folds picks
  their own edges instead of inheriting ours
- **late cohort** — `Hour` relative to the maximum present
- **points, credit and escalation distributions** — sums over the raw numbers

Two folds are not computable from metadata alone and this is stated rather than discovered:
**early cohort** needs the join index (attested, or recovered from `FirstDeposit` logs), and
**linked groups** need the sweep.

**Shares computed over the collection are shares of claimants, not of THE LIST.** Hour 0 was 96
of 15 576 wallets, or 0.62% of the list; its share *of the collection* depends entirely on who
bothers to claim, and there is no reason the two populations should sample alike — an hour-0
holder is likelier to claim than a farm wallet is. Both figures are true and neither substitutes
for the other. Keeping raw numbers rather than baked percentages is what lets a reader normalise
against whichever population they actually mean.

---

## 6. The card

Fully on chain. One SSTORE2 pointer holds the entire fixed template; the renderer slices it with
`extcodecopy` and splices the per-token values between the slices.

**Direction: MARK — the points number is the card.** At 180px, over one rule and two detail
lines: weight and credit, then deposits, join hour and window; the truncated claimant address
bottom-left and the status bottom-right.

The reasoning is not cost. All ten traits already render as a filterable list beside the image,
so a picture that restates them is wasted; the number is the one thing the trait list cannot be.
It is also meaningful without external context, because both ends are contract constants: `223`
is the structural floor (a `minDeposit` of 0.05 ETH in a judged hour, no early-bird multiplier),
and the observed apex `36,924` sits at exactly the 1 000 ETH `creditCap`. At thumbnail size the
glyph count does the work — `223` is 324px wide, `36,924` is 648px.

### 6.1 Measured, not estimated

A working Solidity renderer was built in a scratchpad, gas measured in-EVM, output rasterised
through librsvg, and the Solidity output proved byte-identical to a Python model.

| quantity | measured |
|---|---|
| template | 1 808 B, one SSTORE2 pointer, 13.6× under the EIP-170 ceiling |
| `tokenURI` output | 2 645 B |
| template deployment | ≈ 443 728 gas (≈ $5 at 3 gwei) |
| `tokenURI` read | 217 083 gas — 0.43% of the 50 M `eth_call` cap |
| fixed vs per-token | ≈ 95% template / 5% variable, across 22 slots |

Every variable slot is a small integer, a fixed-point decimal, a hex address or a closed enum.

Findings that changed the drawing:

- **A colour step alone cannot express `sealed`.** At 200px a sealed card differed from its live
  twin ten times less than two arbitrary wallets differ from each other. The fix is an inset
  frame that appears only when sealed, costing exactly one variable digit, because
  `stroke-width: 0` renders nothing.
- **`Status` folds in the game's phase.** As first specced, a grace-joined wallet on a finished
  game with an unsealed token rendered `grace` and `live` and never mentioned the game was over.
  `isSettled()` is one staticcall, giving three honest states in one slot: **`live`** (game
  running, token unsealed), **`settled`** (game over, token not yet sealed), **`sealed`** (which
  needs no qualifier, since sealing is only possible after settlement). Note this is the
  *token's* status; `Window` remains the *wallet's* join window and is unrelated.
- **Rank and points-share cannot be rendered** (§1). Volume-share is derivable and still must
  not be: the floor wallet is 0.00004% of grace volume, which the house format renders as
  `0.0%` — a real value that reads as zero.
- **Box-drawing characters do not tile.** Their advance is correct but their ink does not span
  it, so a `─` rule renders visibly dashed. Every rule and border is a `<rect>` or `<path>`. The
  other house glyphs (`·`, `Ξ`, `⚑`, `◌`, …) resolve correctly at the monospace advance.
- **The `matrix` palette carries one state colour.** Its `warning` is 4.95 dE from `primary`
  with identical greyscale luminance, and its `error` is a *dark* mark that reads dimmer than a
  healthy number at thumbnail size. State is carried by the word, never the hue.
- **No embedded font.** A 224 kB embed produced a raster byte-identical to the *fallback*,
  because librsvg ignores `@font-face`. The generic `monospace` keyword resolves fixed-advance
  and costs 9 bytes. Give both a matching nominal size and a `viewBox`: the `viewBox` survives a
  requested 3000px raster, the nominal size protects a consumer that requests nothing.

### 6.2 Why URL-encoding, precisely

The byte saving over base64-inside-base64 is only ~5%, and it *inverts* to a 17% loss with a
library-default encoder such as `quote(safe="")`. The real reason is that **base64 is not
byte-aligned to its plaintext**, so a pre-encoded blob cannot have per-token values spliced into
it — which forces two runtime encode passes: **876 k vs 443 k gas, measured**.

So: store the template **already percent-encoded**, over a minimal set (`%`, `#`, `"`, `&`,
space, `<`, `>`, `?`, and every byte ≥ 0x80), and use single quotes for all SVG attributes so
the payload contains no `"` and the JSON needs no escaping at all. The contract then does no
encoding at runtime.

`#` is not optional — it is the URI fragment delimiter and the payload contains hex colours.
Non-ASCII must be pre-encoded before it reaches a `.sol` file, which is ASCII-only.

### 6.3 The language rule becomes a deploy-time check

Because ~95% of the payload is a constant blob and every variable slot is digits, a hex address
or a closed enum, the forbidden-word scan is a **one-time check of a constant at deploy** rather
than the dashboard's runtime `pattern_language()` boundary. That is a stronger position, not a
weaker one.

---

## 7. The optional overlay

**It may never ship.** Nothing in §3.1, §3.2, §4, §5.1 or §6 depends on it.

Its purpose is the two facts the EVM cannot see: the **join index**, and a **positive-only
`Independent` certification** granted to wallets the sweep analysed and found in no linked
cluster. Absence of that trait claims nothing — it reads as "not certified", never as an
accusation — which is the only shape under which a revisable analysis may touch a permanent
artifact.

**Leaf encoding**, both sides, OpenZeppelin `StandardMerkleTree` convention:

```
leaf = keccak256(bytes.concat(keccak256(abi.encode(address account, bytes32 traitKey, bytes32 value))))
```

Attested to the **claimant address, not the token id**: it is the natural key, it lets
attestations exist before a member has claimed, and a transferred token keeps them, matching the
rule that metadata describes the claimant.

### 7.1 Two traps, both found by measurement

**The revocation trap.** If the generator emits leaves only for wallets that *qualify*, a grant
made under epoch 1 becomes **unrevokable** — there is no leaf to overwrite it with when epoch 2
withdraws it. **The generator must emit a leaf for every analysed wallet, for every trait,
including the explicit negative value.** Then anyone can permissionlessly correct a stale slot,
using the same property the grant path already relies on.

**One value per `(address, traitKey)` per epoch.** Two differing leaves for one pair both verify
against the same root, and whoever submits picks which lands.

### 7.2 Generator

**Python, inside `sybilkit`, building the OpenZeppelin tree shape by hand — about 40 lines.**
The cross-language boundary buys nothing: no existing export carries the join index, so a
TypeScript generator would still need a new Python emitter plus a schema plus a parser. Python
is four existing, tested calls from a root, with `ds.first_index` already in hand; measured at
3.9 s for a 3 864-leaf tree, using the keccak sybilkit already ships and already checks against
canonical vectors. The repo also has no Node toolchain.

The join index comes only from `FirstDeposit` logs, swept from `CREATION_BLOCK` 25 769 870 to
the settlement head. A missing index must be an **omitted leaf, never a zero leaf** — the index
is 1-based and 0 means "never deposited". The dev cache is not an archive: it holds the join
index uncapped but the deposit history capped.

The manifest carries no reason prose — address, traitKey, value, proof — so no string the
analysis library uses about a cluster can reach a rendered surface.

### 7.3 Copy chaincred's fixture, not its tree

Its tree is layered rather than OZ-shaped, and **the incompatibility is invisible on the
Solidity side**: `MerkleProof.verify` accepts either shape's proofs against its own root, so a
Solidity suite cannot tell which generator built the fixture. It surfaces only when swapping
generators kills every previously-issued proof. Therefore: use the OZ shape, and **size the
fixture table at 7 or 9 leaves, never 8 or 12**, so a shape regression cannot pass by
coincidence.

Chaincred's fixture pattern is otherwise the single most valuable thing to lift: production
exports a pure builder, the fixture script imports that builder rather than reimplementing it,
and the Solidity test loads the root from the fixture and re-verifies every proof through the
real entry point. **Close the one gap it left:** nothing there ever regenerates and diffs the
committed fixture, so it can drift silently. CI regenerates and diffs.

---

## 8. Repo layout, tests, rollout

### 8.1 Layout

- **New Foundry repo** — `ListRecord`, `ListRecordRenderer`, `ListAttestations`, tests, deploy
  scripts, the committed merkle fixture.
- **`sybilkit`** — an `export-attestations` sibling to `export-clean-list`. Keyless, read-only,
  signs nothing. This is also the first concrete reason to want sybilkit on PyPI: `pip install
  sybilkit` is how the contracts repo obtains its generator for the fixture check.
- **MaxPane** — optionally, a read-only line in the `y` view: `record #7 · sealed`, or `not
  claimed`. An expansion of dashboard 2, no six-surface renumber. **Showing "not claimed" is
  read-only; offering a claim button is not, and there is no button.**

### 8.2 Tests

Hermetic by default, on this repo's rule: a `MockList` implements the read interface, seeded
from the real captures already committed here. No fork and no RPC in the default suite; a fork
test exists but is opt-in behind an env var, so a green run never silently skipped integration.

First tests to write, because they catch the failures actually identified:

1. **A non-member cannot claim and does not read as hour 0** (§1.1).
2. **`seal` is holder-only, post-settlement-only, once** — then make the mock game *lie* after
   sealing and assert the token does not move.
3. **`tokenURI` golden file, byte-exact**, decoded base64 → JSON → percent-decode → SVG and
   asserted round-trip identical.
4. **The forbidden-word scan over the template constant**, once, at deploy.
5. **The merkle fixture at 7 or 9 leaves**, with tamper negatives and the revocation case —
   epoch 2 overwriting an epoch-1 grant with the explicit negative value.
6. **Gas snapshots**, so a `tokenURI` cost regression is a diff rather than a surprise.

### 8.3 Rollout

1. Contracts, renderer, hermetic tests. No attestation.
2. **Sepolia rehearsal against a mock game**, and look at the card on a real marketplace listing.
   The deploy is the one irreversible step — the renderer is immutable by design.
3. Mainnet. Claiming opens immediately, in the live era.
4. Settlement; holders seal.
5. The overlay, whenever or never.

**The user runs every deploy.** No key exists in either repo and no agent produces a transaction.

**Plan scope.** This design covers three deliverables that should not share one implementation
plan. The *first* plan covers only the contracts repo — `ListRecord`, `ListRecordRenderer`,
their tests, and rollout steps 1–3 — which is a self-contained, shippable collection. The
`sybilkit` exporter and `ListAttestations` (§7) are a second plan, written only if the overlay
is ever wanted. The MaxPane read-only line (§8.1) is a third, and the smallest.

---

## 9. Deliberately not done

### 9.1 Burn-and-remint

Considered and rejected in favour of `seal()`. The chain already freezes the values at
settlement, so a burn buys ceremony rather than finality — and it collides with
transferability: the burner is whoever *holds* the token, so either a non-member mints a record
of someone else's participation, or a token bought by a non-member becomes permanently
unredeemable. Both are bad and there is no third answer. Two collections would also split the
floor and leave whichever nobody converts as a husk.

### 9.2 Shaping metadata for OpenSea's rarity ranker

Ruled out by the user, and worth recording so it is not reintroduced as a "fix". Had it been a
goal, three measured constraints would have applied: a single numeric attribute disqualifies the
**entire collection** from ranking; ERC-1155 is excluded outright; and the primary sort key is
the count of 1-of-1 traits, so any near-unique value (an exact points figure, an address)
promotes those tokens above everything. Frequency rarity is also U-shaped, so round-number
points buckets would have made the *lowest*-points wallets rare alongside the highest.

Consequence of the ruling: because `Points` is a numeric trait and `Claimant` is unique per
token, **OpenSea will not display rarity ranks for this collection.** That is the accepted
trade, not an oversight.

### 9.3 A linkage flag in the metadata

Rejected on the author's own prior evidence. In chaincred, shipped code scored named real people
as probable sybils (`gakonst.eth` at 88/1000, inside its own red "high sybil risk" band), its
appeals path granted relief on the website and **never reached the merkle root that went on
chain**, and no sybil judgement was ever made permanent on any surface. This repo's own doctrine
says the same thing: nothing is persisted as a verdict, and a later sweep may re-admit a wallet
to the clean list, which is the point.

A frozen flag would also have been coverage-dependent rather than a property of the wallet: the
sweep is budgeted and resumable, and the same 220 wallets went from 10 flagged to 99 as tier-B
data arrived.

### 9.4 An upgradeable renderer, and an owner

An earlier draft had a swappable renderer so a live-reading mode could be added later. Once live
reading became the default, its only remaining purpose was art revision — which is a rug vector
in exchange for nothing. Immutable, and the collection has no owner at all.

---

## 10. Open items

1. **Symbol.** `LIST` assumed; the only detail not explicitly ruled.
2. **Whether the overlay ever ships.** Deliberately deferred; deploying `ListAttestations` with
   no root costs nothing and keeps it possible.
3. **Description text.** Must not mention the certification (D10). Should state the marketplace
   caching limitation (§4) rather than let a holder discover it.
4. **Population is still moving.** 15 576 contributors at the last full sweep, 18 317 on chain
   the next day, and the game is unsettled at hour 41. Every distribution figure here is a
   snapshot; re-measure before quoting one, and read live values rather than these.
5. **Rasteriser evidence is librsvg 2.62.0 only.** resvg and browser pipelines differ, notably
   on `@font-face`. The conclusions are the same either way, but the claim is one data point.
