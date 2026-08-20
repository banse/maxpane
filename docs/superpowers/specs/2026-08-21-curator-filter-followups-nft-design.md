# Curator Filter Follow-ups And NFT Holders Design

**Date:** 2026-08-21
**Status:** Approved in conversation; pending written-spec review
**Branch:** `feature/curator-list-record-hero`

## 1. Scope

Extend only THE LIST's list-view hero, custom filter editor, and filtered-table
title. Preserve every shared hero and every non-curator view.

The change has four parts:

1. label and reset the existing filter controls;
2. refine the list-only hero formatting;
3. show active criteria beside the filtered-table count; and
4. add keyless Ethereum/Base NFT-holder filtering for four predefined and
   session-added custom collections.

This remains a read-only dashboard. It never signs, sends a transaction,
constructs state-changing calldata, or requires an API key.

## 2. Filter Editor Layout

Every control group has a visible heading above its control rather than relying
on an input placeholder to explain the field.

### Range and option headings

The full-width editor presents these named groups in stable order:

1. `JOIN` - from and to inputs for `first_index`;
2. `HOUR JOINED` - from and to inputs for `first_hour`;
3. `RANK` - raw-rank from and to inputs;
4. `POINTS` - points from and to inputs;
5. `CREDIT` - ETH-credit from and to inputs;
6. `WEIGHT` - ETH-weight from and to inputs;
7. `DEPOSITS` - deposit-count from and to inputs;
8. `ENS` - any, set, or unset;
9. `WINDOW` - any, grace, or judged;
10. `LINK BAND` - any, clean, low, high, or unknown; and
11. `WHALE DEPOSIT` - the existing individual-deposit-at-least-25-ETH toggle.

Compact layouts preserve the same order and wrap complete titled groups rather
than separating a title from its control.

### Linked-pattern headings

`LINKED PATTERNS` remains a section heading. Each selectable evidence family
has its own heading above its checkbox:

- `AMOUNT` - matching amounts;
- `SEQUENCE` - consecutive joins;
- `CADENCE` - cadence;
- `GAS` - gas fingerprint; and
- `FUNDING` - shared funding.

Selected evidence families retain their existing OR semantics. The resulting
family condition combines with every other active filter category using AND.

### Reset and acceptance controls

The editor adds a visible `RESET ALL` command. It clears:

- every range input;
- ENS, window, and band selects back to `any`;
- whale and linked-pattern checkboxes;
- predefined and custom NFT selections;
- the custom collection address input and selected-collection rows; and
- visible validation errors.

Reset modifies the retained editor draft only. It does not change the active
filtered table until the reader presses `f`. Accepting the reset draft produces
the existing no-active-criteria result: an empty filtered list.

The remaining line at the bottom of the editor is centered and reads exactly:

`press 'f' to accept filters`

## 3. Editor-only Hero Note

Only while the custom filter editor is visible, the note below the list hero
changes to exactly:

`set ranges or options below · selected patterns and NFT collections match any`

Raw, cleaned, and filtered table views retain the existing export note:

`press 'e' to export full list as json file - once exported the complete list will be shown below`

The screen owns which note is active. The hero widget still only renders the
primitive note state supplied to it.

## 4. Hero Formatting

### Third card

`THE FILTER` uses the same dim title treatment as `THE LIST`, `THE WALLET`, and
the other list-only hero titles. Its four shortcut lines remain white and
regular weight.

The shortcut lines are padded to one equal visible width before the four-line
block is centered. Consequently the leading `'1'`, `'2'`, `'3'`, and `'f'`
tokens share one vertical column even though the descriptions have different
lengths. Padding is width-aware and must not create a false `‹ widen` state.

### Middle card in Filtered view

The Filtered standing line becomes:

`#<visible index> of <matched total> · filtered`

The rank and total remain bold. The literal `· filtered` suffix is regular
weight and replaces `(filtered)`.

The next three displayed rows - active filter values, wallet identity, and
wallet points - use the success/green color. The existing identity fallback,
filter-summary compaction, and points emphasis remain. Raw and Cleaned middle
card formatting is unchanged.

## 5. Filtered Table Title

The filtered title appends the active criteria after its wallet count, for
example:

`THE FILTERED LIST - 568 wallets · join #1-1,000 · NFT Identity.md`

The base title and count retain their existing bold treatment. The criteria
suffix is regular weight and uses the same dim color as the list-hero titles.

Criteria follow the pure model's stable category order. NFT criteria come after
the existing categories. The suffix is compacted against the title's actual
rendered width and collapses hidden clauses to a stable `+N`. The existing
sort note and `‹ widen` behavior remain separate and must not overflow the
143-column layout.

## 6. NFT Collection Model

The pure filter model gains an immutable collection reference containing:

- `chain`: `ethereum` or `base`;
- `address`: normalized lower-case 20-byte `0x` address; and
- `label`: predefined display name or a deterministic custom label.

Custom labels use `ETH 0x1234…abcd` or `BASE 0x1234…abcd`; collection metadata
is not required to make the filter truthful.

The four predefined choices are:

| Label | Chain | Contract |
| --- | --- | --- |
| Identity.md | Ethereum | `0x0000ec93127baa929e58e97dd0095a2bfb38ec1d` |
| Fren Pet | Base | `0x5b51cf49cb48617084ef35e7c7d7a21914769ff1` |
| Milady | Ethereum | `0x5af0d9827e0c53e4799bb226655a1de152a425a5` |
| Crypto Punks | Ethereum | `0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb` |

All four addresses were checked against current chain state on 2026-08-21.
Identity.md, Fren Pet, and Milady answer the ERC-721 interface check and
`balanceOf(address)`. CryptoPunks predates ERC-721 interface discovery, but its
contract answers `balanceOf(address)` and is therefore supported explicitly by
the ownership mechanism.

The editor renders the four predefined choices as combinable checkboxes.
Custom collection controls consist of:

1. an explicit Ethereum/Base selector, defaulting to Ethereum;
2. one contract-address input;
3. a compact `+` command, also activated by submitting the address input; and
4. a visible selected-collection list whose rows each have a `×` remove command.

Addresses are syntax-validated before addition, normalized, and deduplicated by
`(chain, address)`. The same predefined collection cannot also appear as a
duplicate custom row. Malformed input stays in the editor with focus and a
field-level error.

The filter specification stores selected collection references. A wallet
passes the NFT category when it currently holds at least one token in any
selected collection. Multiple selected collections therefore combine with OR,
matching LINKED PATTERNS. The NFT category combines with join, score,
contribution, identity, window, band, whale, and linked-pattern categories
using AND.

No selected NFT collection means the NFT category is inactive.

## 7. Keyless Ownership Source

### Why current-state Multicall

NFT ownership is current state, so direct `eth_call` is appropriate. Historical
event scanning is not. Blockscout holder pagination is not the primary source:
it is rate-limited, collection-size-dependent, and the Ethereum endpoint was
observed returning HTTP 429 during design validation.

The implementation uses keyless public Ethereum and Base state RPC pools and
Multicall3 `aggregate3` batches of ERC-721-compatible
`balanceOf(address)` calls. Every subcall allows failure so one incompatible
wallet/collection result cannot abort a batch. CryptoPunks uses the same
working `balanceOf(address)` selector despite lacking ERC-165 support.

The holder reader is a dedicated data component. It reuses the repository's
owned HTTP transport, RPC failover, Multicall3 codec, pacing, and injected-test
patterns. It does not import Textual or filter widgets.

### Bounded scan

The scan universe is exactly the raw source selected by the existing validated
list-source gate:

- the complete raw JSON when its length matches the authoritative contributor
  count; or
- the live first-1,000 fallback otherwise.

For 19,522 wallets and 500 balance calls per Multicall request, one collection
requires 40 or fewer state requests. Selected collections are scanned in a
bounded, paced background task. No NFT collection is prefetched until a filter
selects it.

### Persistent last-good cache

The curator cache gains one additive NFT-holder last-good slot. Each collection
entry records:

- chain and contract;
- normalized holder addresses;
- a deterministic fingerprint of the scanned raw-wallet universe;
- successful/failed subcall coverage;
- observed block number when available; and
- timestamp.

The cache is valid only for the same wallet-universe fingerprint. Successful
ownership entries refresh after 30 minutes. Adding this independent last-good
slot is required by the new cross-chain source; it does not add a polling read
when no NFT filter is active.

An older cache file simply lacks the additive slot. No schema migration or
filter-setting persistence is required.

## 8. Background Lifecycle And Screen State

The manager owns one deduplicated, cancellable NFT-holder task. Requesting a
collection already covered by a fresh matching cache entry does no I/O.
Concurrent requests for the same chain, contract, and wallet fingerprint share
one task.

Applying an NFT filter never waits for network I/O:

1. the screen stores the accepted filter specification and closes the editor;
2. the manager returns cached holders when available;
3. missing entries queue the detached scan and return an explicit pending
   state;
4. the filtered table renders `NFT holder data loading` rather than a false
   empty result; and
5. the next normal dashboard refresh recomputes the active filter from the new
   last-good ownership data while preserving table sort and receipts.

The task is cancelled and awaited during manager close before the HTTP client
closes. It never delays first paint or an unrelated dashboard refresh.

## 9. Failure And Export Semantics

Synchronous editor validation failures keep the editor open. Ownership-source
states are distinct:

- **fresh success:** filter and export normally;
- **stale success while refreshing:** keep using the last-good holder set and
  show `as of HH:MM`;
- **pending without last-good:** show `NFT holder data loading`, do not render a
  false empty match set, and do not export;
- **failure without last-good:** show `NFT holder data unavailable`, do not
  render a false empty match set, and do not export; and
- **valid zero holders among the raw universe:** render a real empty filtered
  list and allow export of `[]`.

A custom address with no code or no usable `balanceOf(address)` is unavailable,
not a collection with zero holders. A failed scan never overwrites a previous
successful holder set or a previously exported filtered JSON file.

The filtered export remains a plain JSON array in current table sort with
sequential `index`. NFT criteria appear only in the visible filter summary and
title; no new envelope is added to the export.

## 10. MVC Boundaries

- **Model:** immutable NFT collection references, parsing, validation,
  summaries, OR-within-NFT matching, and AND-across-category filtering.
- **Data client/cache/manager:** keyless chain reads, background task,
  last-good ownership cache, completeness, and degradation state.
- **Screen/controller:** retained editor draft, reset/apply flow, active note,
  scan requests, refresh recomputation, receipts, and export gating.
- **Widgets:** titled controls, custom collection add/remove presentation,
  reset command event, hero markup, and title rendering from supplied
  primitives.

Widgets do not read chain state, inspect the manager, or filter rows directly.
The manager does not import Textual.

## 11. Verification

All tests remain keyless and offline. Network-capable components use injected
transports that fail if an unexpected request occurs.

Required coverage includes:

1. exact predefined chain/address constants and custom normalization;
2. malformed address, chain, duplicate, and predefined/custom collision cases;
3. NFT OR semantics and AND composition with every existing category;
4. no selected NFT condition and valid zero-match behavior;
5. Ethereum/Base Multicall encoding, 500-call chunking, response alignment,
   individual failure, total failure, and endpoint failover;
6. CryptoPunks-compatible `balanceOf` behavior without requiring ERC-165;
7. wallet-universe fingerprinting, 30-minute freshness, stale last-good,
   pending, failure, retry, and persistence round trips;
8. no NFT network activity until an NFT filter is selected;
9. detached-task deduplication, non-blocking first paint, refresh publication,
   and clean cancellation;
10. editor headings, responsive grouping, predefined selection, custom add,
    submit-to-add, remove, deduplication, reset, error focus, and retained draft;
11. exact centered footer and editor-only hero note;
12. dim `THE FILTER`, aligned shortcut tokens, filtered standing markup, and
    green active-filter/identity/points rows;
13. filtered-title suffix style, stable order, NFT labels, width compaction,
    sort coexistence, and `+N` overflow behavior;
14. pending/unavailable export protection and valid-empty `[]` export;
15. 143-column raw, cleaned, filtered, and editor composites with no incoherent
    overlap or horizontal scrollbar; and
16. the complete curator suite plus comparison with the repository's 13 known
    unrelated FWA/Surf accessibility failures.

Every production guard is introduced through TDD with a named mutation that
proves its test fails for the intended reason. Commits stage explicit paths and
never include the pre-existing live curator captures.

## 12. Out Of Scope

- ERC-1155 collection-wide ownership, because it requires token IDs and has no
  collection-level `balanceOf(address)` view;
- historical ownership at the game's launch or settlement block;
- OpenSea, Alchemy, Moralis, keyed explorer APIs, or any API key;
- persistent custom-filter settings;
- NFT metadata, images, floor prices, or token lists;
- changes to shared hero cards or non-curator views; and
- exposing the hidden Linked Analysis binding again.
