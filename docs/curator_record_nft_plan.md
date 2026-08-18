# THE LIST record NFT — implementation plan (contracts repo)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `ListRecord` — an ownerless ERC-721 that lets any member of THE LIST claim a permanent, fully on-chain record of what their wallet did in the game.

**Architecture:** Three contracts in a standalone Foundry repo at `/Library/Vibes/list-record`. `ListRecord` (ERC-721, no owner, no admin function) gates `claim()` on `LIST.firstHourOf(msg.sender).hasJoined` and reads points/weight/credit/deposits live from the game; `sealRecord(id)` copies the final numbers into the token's own storage once the game has settled. `ListRecordRenderer` (immutable, no setter) assembles a base64 JSON data URI whose SVG image is spliced from one SSTORE2 template blob. Nothing is attested, nothing is snapshotted, and no merkle root gates anything.

**Tech Stack:** Foundry (forge 1.5.1), Solidity 0.8.24 exact-pinned, OpenZeppelin Contracts v5.7.0 (ERC-721 + ERC-4906), forge-std v1.9.7, and a stdlib-only Python 3 generator for the card template. No Node toolchain.

**Spec:** `/Library/Vibes/autopull/docs/curator_record_nft_design.md` — read it alongside this plan. The plan argues from the spec; where a task and the spec disagree, the task says so explicitly.

**Scope:** This plan covers the FIRST deliverable only. `ListAttestations` and the `sybilkit` exporter (spec §7) and the MaxPane read-only line (spec §8.1) are separate later plans and are out of scope here.

## Global Constraints

- **Solidity `0.8.24`, exact pin** (`pragma solidity 0.8.24;`) in every `.sol` file including tests and scripts. OpenZeppelin v5.7.0 declares `^0.8.24` across 133 files, so this is a floor and may not be lowered.
- **`forge fmt` at `line_length = 120`**, tab_width 4, bracket_spacing false. Later tasks quote earlier lines verbatim for exact-string edits; a different width rewraps them and breaks those edits.
- **`remappings.txt` is exactly two lines:** `forge-std/=lib/forge-std/src/` and `@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/`.
- **No test touches the network.** The default suite talks only to `test/mocks/MockList.sol`. The one fork test is gated behind `LIST_FORK_RPC` and skips *loudly*.
- **The collection has no owner.** No `Ownable`, no admin function, no pause, no mint price, no `receive`/`fallback`/`withdraw`, on either `ListRecord` or `ListRecordRenderer`. A grep-based test enforces this on both.
- **Every address literal must be EIP-55 checksummed** (`cast to-check-sum-address`). Two forms in circulation are invalid and solc rejects them: `0xdEaD…bEEF` (correct: `0xDeaD00000000000000000000000000000000BEEf`) and the game address as it appears inside the capture files.
- **No thousands separators in any rendered number.** The same formatted bytes are spliced into both the SVG and the JSON, and `"value":36,924` is not valid JSON. This is a correctness rule, not an aesthetic one.
- **`template/offsets.txt` is ONE line** of comma-separated integers, pairs flattened (`s0,l0,s1,l1,…`). Every consumer parses it with `vm.split(vm.trim(vm.readFile(...)), ",")`.
- **Restoring a mutation:** `git checkout -- <path>` is allowed in this repo (it is fresh and holds no third-party uncommitted work — unlike `/Library/Vibes/autopull`, where it is banned). For anything under `template/` or `test/fixtures/golden_*`, **regenerate** instead, so the blob and its offsets can never drift apart.
- **Prove every guard bites.** Each fix names a mutation; apply it, watch the named test go red, restore, confirm green. A guard without a recorded bite is not done.
- **The repo owner runs every deploy.** No key, keystore or RPC secret enters the repo, and no agent or CI job produces a transaction.

---

### Task 1: Repository scaffold, toolchain, and the two interfaces

You are creating a brand-new Foundry (Solidity) repository from nothing. `forge build` compiles, `forge test` runs tests that are themselves written in Solidity, and dependencies are vendored into `lib/` as git submodules. Nothing here touches another repository, and nothing you write ever sends a transaction or holds a private key.

Background you will not otherwise have: there is an already-deployed, verified, non-upgradeable contract on Ethereum mainnet called `WhitelistCurator` at `0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`. It runs a game called THE LIST. Our contracts only ever *read* it. To read another contract, Solidity needs an `interface`. The EVM does not dispatch on names, it dispatches on a **selector**: the first 4 bytes of `keccak256("name(argtypes)")`. Declare one argument type differently from the deployed contract and the selector changes, the call hits a function that does not exist, and it fails **at runtime**, not at compile time.

The same hazard exists on our own side. `ListRecord` and `ListRecordRenderer` are two separately-deployed contracts; `ListRecord` holds the renderer's address in an immutable and calls it with one struct, `CardData`, ABI-encoded across that boundary. Change the struct's *types* and redeploy only one of the two, and every `tokenURI` reverts. So this task ends by pinning **ten** selectors — the game's nine plus the renderer's one.

**Files**

| action | path |
|---|---|
| create | `/Library/Vibes/list-record/` (whole repo — does not exist yet) |
| create | `/Library/Vibes/list-record/foundry.toml` |
| create | `/Library/Vibes/list-record/remappings.txt` |
| create | `/Library/Vibes/list-record/.gitignore` |
| create | `/Library/Vibes/list-record/README.md` |
| create | `/Library/Vibes/list-record/src/interfaces/IWhitelistCurator.sol` |
| create | `/Library/Vibes/list-record/src/interfaces/IListRecordRenderer.sol` |
| create (submodule) | `/Library/Vibes/list-record/lib/forge-std` |
| create (submodule) | `/Library/Vibes/list-record/lib/openzeppelin-contracts` |
| create (generated) | `/Library/Vibes/list-record/.gitmodules`, `/Library/Vibes/list-record/foundry.lock` |
| test | `/Library/Vibes/list-record/test/Interface.t.sol` |
| read-only reference | `/Library/Vibes/autopull/maxpane_dashboard/abis/curator/whitelist_curator.json` |

**Interfaces**

*Consumes* — nothing. This is the first task in the plan. Its only external input is the vendored ABI of the deployed game, read but never copied into this repo:

```
/Library/Vibes/autopull/maxpane_dashboard/abis/curator/whitelist_curator.json
```

*Produces* — consumed by every later task (canonical map: Task 1 interfaces + scaffold; Task 2 MockList + fixtures; Tasks 3–5 `ListRecord`; Task 6 template generator; Task 7 renderer; Tasks 8–11 wiring, traits, language gate, gas/deploy/fork):

1. `src/interfaces/IWhitelistCurator.sol` — the nine read-only game views, exactly as in the frozen contract.
2. **`src/interfaces/IListRecordRenderer.sol`, created here and nowhere else.** Task 3 imports it in its very first code step and Task 7 implements it; no later task creates it. It declares `CardData` at **file level, outside the interface**, so a consumer can write `import {IListRecordRenderer, CardData} from "…/IListRecordRenderer.sol";` and then use `CardData` unqualified.
3. Two import remappings, and nothing else in `remappings.txt`: `forge-std/=lib/forge-std/src/` and `@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/`. A later task writes `import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";` and it must resolve. **No later task edits, re-writes or re-commits this file.**
4. A compiler pin of **solc 0.8.24, exact, no caret**, with the optimizer on. Verified: OpenZeppelin v5.7.0 declares `pragma solidity ^0.8.24` in 133 files, so 0.8.24 is the *floor* — lowering it breaks the OZ import in a later task. Every `.sol` file in this plan, tests and scripts included, opens `pragma solidity 0.8.24;`.
5. **`[fmt] line_length = 120`**, `tab_width = 4`, `bracket_spacing = false` — matching the Solidity convention already used in `/Library/Vibes/chaincred`. Later tasks quote lines verbatim for exact-string edits, and a narrower setting would rewrap them out from under those edits.
6. `fs_permissions` granting read access to `./test/fixtures` **and** `./template`. Task 2 calls `vm.readFile("test/fixtures/wallets.json")` and Tasks 6–11 call `vm.readFile("template/blob.hex")` and `template/offsets.txt`; both fail with a permissions error without their entry. Neither directory needs to exist yet — Foundry only checks the permission at the moment of a read.

**Steps**

- [ ] **Step 1: Create the Foundry skeleton.** `--no-git` stops it initialising a git repo of its own, so we control the history from the first commit.

```bash
forge init --no-git /Library/Vibes/list-record
```

Expected output ends with `Initialized forge project`. Note that despite `--no-git` it still clones `forge-std` into `lib/forge-std` as a **plain directory, not a submodule** — Step 2 deletes it, because Step 5 re-adds it properly.

- [ ] **Step 2: Strip the template and the non-submodule `lib/`.** If `lib/forge-std` survives into Step 5, `forge install` refuses to add the submodule because the path is already occupied.

```bash
cd /Library/Vibes/list-record
rm -rf lib src/Counter.sol test/Counter.t.sol script/Counter.s.sol README.md .github
```

Verify with `ls -a /Library/Vibes/list-record` — you should see only `.gitignore`, `foundry.toml`, `script`, `src`, `test`, and those three directories should be empty.

- [ ] **Step 3: Write `.gitignore` and `README.md`.** `out/` is compiled artefacts, `cache/` is Foundry's incremental-build cache, `broadcast/` is the transaction log `forge script` writes — none of the three belongs in history.

Write `/Library/Vibes/list-record/.gitignore`:

```gitignore
out/
cache/
broadcast/
.env
.DS_Store
```

Write `/Library/Vibes/list-record/README.md`. Its `## Deploying` section is a stub: **Task 11 replaces this section in place, and it is the only `## Deploying` heading this file ever has.** Do not let a second one appear.

```markdown
# list-record

`ListRecord` — an ERC-721 collection that lets a member of **THE LIST**
(`WhitelistCurator`, `0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`, Ethereum mainnet)
claim a permanent, fully on-chain record of what their wallet did in the game.

* **Claiming is permissionless** and reads the game contract directly. There is no merkle
  root, no allowlist file and no signature — membership is a chain fact.
* **Art and metadata are 100% on chain.** `tokenURI` returns a base64 JSON data URI whose
  image is a percent-encoded SVG assembled inside an immutable renderer contract.
* **The collection has no owner.** No `Ownable`, no admin function, no pause, no mint price,
  no withdraw. It holds no ETH.

## Layout

```
src/           the contracts
test/          Foundry tests; hermetic by default, no network
template/      the card template blob and its slot offsets
tools/         the Python generator that produces template/
script/        deploy scripts (run by a human, see below)
```

## Build and test

```bash
git submodule update --init --recursive   # first checkout only
forge build
forge test
```

`forge test` **never touches the network**. It talks to `test/mocks/MockList.sol`, a local
stand-in for the game contract seeded from committed captures. Integration against the real
deployed game lives in `test/ForkList.t.sol`, which runs only when `LIST_FORK_RPC` is set and
logs a skip line when it is not — so a green run can never quietly mean "integration was
skipped".

## Deploying

**The repo owner runs every deploy, by hand.** No private key, keystore, mnemonic or RPC
secret exists in this repository, none may be added, and no agent or CI job produces a
transaction. `script/Deploy.s.sol` is a script a human executes with their own signer; the
renderer is immutable once deployed, so the deploy is the one irreversible step.

## Dependencies

* `forge-std` v1.9.7 — Foundry's test standard library
* `openzeppelin-contracts` v5.7.0 — ERC-721 and ERC-4906

Both are pinned git submodules and their exact commits are recorded in `foundry.lock`.
Solidity is pinned to **0.8.24**; OpenZeppelin v5.7.0 requires `^0.8.24`, so that pin is a
floor and must not be lowered.
```

- [ ] **Step 4: Start the git history.**

```bash
cd /Library/Vibes/list-record
git init
git add .gitignore README.md foundry.toml
git commit -m "chore: empty foundry skeleton"
```

Expected: one commit containing exactly three files.

- [ ] **Step 5: Install the two dependencies as pinned git submodules.** `forge install` defaults to `git submodule add`, so this only works because Step 4 created a git repo first.

```bash
cd /Library/Vibes/list-record
forge install foundry-rs/forge-std@v1.9.7
forge install OpenZeppelin/openzeppelin-contracts@v5.7.0
```

Expected output contains `Installed forge-std tag=v1.9.7@77041d2ce690e692d6e03cc812b57d1ddaa4d505` and `Installed openzeppelin-contracts tag=v5.7.0@cab19933c33c2ad1d4c7a84864a3601dddfd16f3`. Confirm with `cat .gitmodules` that both paths are listed and with `grep -m1 '"version"' lib/openzeppelin-contracts/package.json` that it prints `"version": "5.7.0",`. Then commit — `foundry.lock` pins the exact commits, so it belongs in history:

```bash
cd /Library/Vibes/list-record
git add .gitmodules foundry.lock lib/forge-std lib/openzeppelin-contracts
git commit -m "chore: pin forge-std v1.9.7 and openzeppelin-contracts v5.7.0"
```

- [ ] **Step 6: Write `foundry.toml` and `remappings.txt`.** Replace the whole of `/Library/Vibes/list-record/foundry.toml` with:

```toml
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
test = "test"
script = "script"

solc_version = "0.8.24"
optimizer = true
optimizer_runs = 200
evm_version = "cancun"
via_ir = false

# Deterministic bytecode: no trailing metadata hash, which keeps a rebuild
# byte-identical and makes source verification reproducible.
bytecode_hash = "none"
cbor_metadata = false

# Hermetic by construction. `ffi = false` means no test can shell out, and there is
# deliberately no [rpc_endpoints] block and no eth_rpc_url: a default `forge test`
# has nowhere to send a request even if someone wrote one. The opt-in fork test in
# Task 11 supplies its own URL from the LIST_FORK_RPC environment variable.
ffi = false

# Tests read committed fixtures and the card template from disk. Read-only, and only
# these two directories. Neither has to exist yet; the permission is checked at the
# moment of a read, not at startup.
fs_permissions = [
    { access = "read", path = "./test/fixtures" },
    { access = "read", path = "./template" },
]

[fmt]
line_length = 120
tab_width = 4
bracket_spacing = false
int_types = "long"
```

Write `/Library/Vibes/list-record/remappings.txt` — exactly these two lines, and no later task touches this file:

```
forge-std/=lib/forge-std/src/
@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
```

Verify the toolchain is wired up:

```bash
cd /Library/Vibes/list-record && forge build
```

Expected output: `Nothing to compile` and exit status 0 (`src/` is still empty). If instead you see a solc download failure or a remapping error, fix it before continuing. Then commit:

```bash
cd /Library/Vibes/list-record
git add foundry.toml remappings.txt
git commit -m "chore: pin solc 0.8.24, optimizer, remappings and fixture read permissions"
```

- [ ] **Step 7: Write the failing selector test.** This is the test-first half of the TDD cycle: neither file it imports exists yet, so it cannot compile. `bytes4(0x…)` is a 4-byte literal; `IWhitelistCurator.pointsOf.selector` is Solidity's compile-time computation of that function's selector. Create `/Library/Vibes/list-record/test/Interface.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {IWhitelistCurator} from "../src/interfaces/IWhitelistCurator.sol";
import {IListRecordRenderer, CardData} from "../src/interfaces/IListRecordRenderer.sol";

/// @dev Pins our read interface against the deployed game
///      (WhitelistCurator, 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91, Ethereum mainnet).
///      The EVM dispatches on the 4-byte selector, so one wrong argument type is a call
///      into nothing. Each constant below was recomputed with `cast sig "<signature>"`
///      against the vendored ABI at
///      maxpane_dashboard/abis/curator/whitelist_curator.json — never copied from prose.
contract InterfaceTest is Test {
    function test_selectors_match_the_deployed_game() public pure {
        assertEq(IWhitelistCurator.pointsOf.selector, bytes4(0xcf6a4403), "pointsOf");
        assertEq(IWhitelistCurator.weightOf.selector, bytes4(0xdd4bc101), "weightOf");
        assertEq(IWhitelistCurator.contributedBy.selector, bytes4(0x64a8e570), "contributedBy");
        assertEq(IWhitelistCurator.txCountOf.selector, bytes4(0x662d7299), "txCountOf");
        assertEq(IWhitelistCurator.firstHourOf.selector, bytes4(0xc5148173), "firstHourOf");
        assertEq(IWhitelistCurator.isSettled.selector, bytes4(0x3270bb5b), "isSettled");
        assertEq(IWhitelistCurator.currentHour.selector, bytes4(0x020e185d), "currentHour");
        assertEq(IWhitelistCurator.gracePeriod.selector, bytes4(0xa06db7dc), "gracePeriod");
        assertEq(IWhitelistCurator.hourDuration.selector, bytes4(0xda25efd9), "hourDuration");
    }

    /// @dev ListRecord and ListRecordRenderer are deployed separately and talk over an ABI
    ///      boundary, so CardData's TYPE LIST is a deployment contract between them: change
    ///      it and redeploy only one side and every tokenURI call reverts. This pins the
    ///      selector (which follows the types) and the encoded width (ten 32-byte words).
    ///      It cannot see a reorder of two same-typed fields — Task 9's golden tokenURI is
    ///      what catches a weight/credit swap.
    function test_the_renderer_call_shape_is_pinned() public pure {
        assertEq(IListRecordRenderer.tokenURI.selector, bytes4(0x4fa1d284), "renderer tokenURI");
        CardData memory d;
        assertEq(abi.encode(d).length, 320, "CardData is ten words");
    }
}
```

- [ ] **Step 8: Run it and watch it fail for the right reason.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Interface.t.sol
```

Expected output — two compile errors naming the two missing files, **not** an assertion failure:

```
Compiler run failed:
Error (6275): Source "src/interfaces/IWhitelistCurator.sol" not found: File not found.
 --> test/Interface.t.sol:5:1:
  |
5 | import {IWhitelistCurator} from "../src/interfaces/IWhitelistCurator.sol";

Error (6275): Source "src/interfaces/IListRecordRenderer.sol" not found: File not found.
 --> test/Interface.t.sol:6:1:
  |
6 | import {IListRecordRenderer, CardData} from "../src/interfaces/IListRecordRenderer.sol";
```

- [ ] **Step 9: Independently verify each game selector against the ABI.** Do not trust the nine constants you just typed. First confirm every signature exists verbatim in the deployed contract's ABI:

```bash
python3 -c "
import json
abi = json.load(open('/Library/Vibes/autopull/maxpane_dashboard/abis/curator/whitelist_curator.json'))
for e in abi:
    if e.get('type') == 'function' and e['name'] in {
        'firstHourOf','pointsOf','weightOf','contributedBy','txCountOf',
        'isSettled','currentHour','gracePeriod','hourDuration'}:
        ins = ','.join(i['type'] for i in e['inputs'])
        outs = ','.join(o['type'] for o in e.get('outputs', []))
        print(f\"{e['name']}({ins}) -> ({outs})\")
"
```

Expected: nine lines, exactly `firstHourOf(address) -> (uint256,bool)`, `pointsOf(address) -> (uint256)`, `weightOf(address) -> (uint256)`, `contributedBy(address) -> (uint256)`, `txCountOf(address) -> (uint256)`, `isSettled() -> (bool)`, `currentHour() -> (uint256)`, `gracePeriod() -> (uint256)`, `hourDuration() -> (uint256)`. Then recompute the selectors from those signatures:

```bash
for s in "pointsOf(address)" "weightOf(address)" "contributedBy(address)" "txCountOf(address)" \
         "firstHourOf(address)" "isSettled()" "currentHour()" "gracePeriod()" "hourDuration()"; do
  printf "%-24s %s\n" "$s" "$(cast sig "$s")"
done
```

Expected, in order: `0xcf6a4403 0xdd4bc101 0x64a8e570 0x662d7299 0xc5148173 0x3270bb5b 0x020e185d 0xa06db7dc 0xda25efd9`. If any line disagrees with Step 7, the ABI is authoritative — fix the test, not the ABI.

- [ ] **Step 10: Write `IWhitelistCurator.sol`.** Create `/Library/Vibes/list-record/src/interfaces/IWhitelistCurator.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Read-only view of the deployed game, `WhitelistCurator` at
///         0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91 on Ethereum mainnet.
///
/// @dev    Only the nine views this collection needs. Deliberately absent:
///         `contributors(address)` (selector 0x1f6d4942), the raw struct getter. Its fourth
///         word is `firstHour + 1`, where 0 means "never deposited" — read naively, every
///         non-member renders as an hour-0 founder, the rarest cohort in the game.
///
///         That getter IS present in the vendored ABI (all 32 functions are), so its absence
///         here is discipline, not an accident of what was available. The thing that keeps
///         the discipline is Task 2's test that a non-member does not read as hour 0, not
///         this comment.
///
///         `deposit()`, `settle()` and `rescue()` are state-changing and are not declared
///         here: this repository never writes to the game.
interface IWhitelistCurator {
    /// @notice Hour index of an address's first deposit. `hasJoined == false` means the
    ///         address never deposited, and `hour` is then a meaningless 0.
    function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined);

    /// @notice Points under the current curve: isqrt(weight) * POINTS_PER_ETH / 1e9.
    function pointsOf(address account) external view returns (uint256);

    /// @notice Sum of (credited delta x early-bird multiplier), in wei-equivalents.
    function weightOf(address account) external view returns (uint256);

    /// @notice The LARGEST SINGLE SEND in wei (`highWater`), uncapped. Not a lifetime sum
    ///         and not the credited amount, which is capped at creditCap. Do not confuse it
    ///         with the `credit_wei` figure in the maxpane sweep, which is the capped one.
    function contributedBy(address account) external view returns (uint256);

    /// @notice Recorded deposits by this address.
    function txCountOf(address account) external view returns (uint256);

    /// @notice True once any completed, judged hour came up short. Monotonic: never false
    ///         again, and once true every per-address view above is frozen for ever.
    function isSettled() external view returns (bool);

    /// @notice Current hour index, counted from launch.
    function currentHour() external view returns (uint256);

    /// @notice Length of the grace period in seconds (86400 on this deployment).
    function gracePeriod() external view returns (uint256);

    /// @notice Length of one hour bucket in seconds (3600 on this deployment).
    function hourDuration() external view returns (uint256);
}
```

- [ ] **Step 11: Write `IListRecordRenderer.sol` and verify its selector.** This is the file Task 3 imports and Task 7 implements. `CardData` is declared at **file level, outside the interface**, so consumers can import the name directly. Create `/Library/Vibes/list-record/src/interfaces/IListRecordRenderer.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Everything the renderer needs to draw one card. `ListRecord` fills it in and
///         passes it by value; the renderer NEVER calls back into `ListRecord`, so the two
///         have no circular constructor dependency and the renderer is deployed first.
///
/// @dev    Declared at file level rather than inside the interface so that consumers can
///         `import {IListRecordRenderer, CardData} from "..."` and use `CardData` unqualified.
///
///         `grace` is `hour < graceHours`, computed by ListRecord from the game's own
///         gracePeriod/hourDuration rather than from a hardcoded 24.
///         `status` is 0 = live, 1 = settled, 2 = sealed.
struct CardData {
    uint256 id;
    address claimant;
    address owner;
    uint256 points;
    uint256 weightWei;
    uint256 creditWei;
    uint256 deposits;
    uint256 hour;
    bool grace;
    uint8 status;
}

interface IListRecordRenderer {
    function tokenURI(CardData calldata d) external view returns (string memory);
}
```

Confirm the pinned selector is the one this struct actually produces:

```bash
cast sig "tokenURI((uint256,address,address,uint256,uint256,uint256,uint256,uint256,bool,uint8))"
```

Expected: `0x4fa1d284`. If it differs, the struct you wrote does not match the frozen contract — fix the struct, not the test.

- [ ] **Step 12: Run the tests and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Interface.t.sol -vv
```

Expected — **2 passing tests, and a bare `forge test` at this point in the plan runs exactly these 2**:

```
Ran 2 tests for test/Interface.t.sol:InterfaceTest
[PASS] test_selectors_match_the_deployed_game() (gas: 10116)
[PASS] test_the_renderer_call_shape_is_pinned() (gas: 5119)
Suite result: ok. 2 passed; 0 failed; 0 skipped
```

Gas figures are printed and vary with the compiler build; they are not part of the expectation. The two `[PASS]` lines and `2 passed; 0 failed` are.

- [ ] **Step 13: Prove the game-selector test bites.** A green test that cannot go red is worse than no test. Introduce the exact bug it exists to catch — a wrong argument type — and watch it fail.

**Restore discipline for this repository, which every mutation step in this plan follows.** `list-record` is a brand-new repository containing nobody else's uncommitted work, so `git checkout -- <path>` is a legitimate way to undo a mutation here, unlike in `/Library/Vibes/autopull` where the blanket ban exists because the working tree routinely holds another person's changes. Two rules qualify it: use `git checkout --` only on a file already committed (before the first commit there is nothing to check out back to, so use the reverse edit shown in each step), and **never** use it on anything under `template/` — those files are generated, and restoring one without the other lets the blob and the offsets drift apart. Regenerate those with `tools/gen_template.py` instead.

`src/interfaces/IWhitelistCurator.sol` is not committed until Step 15, so this mutation is undone with the reverse `sed`:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/function pointsOf(address account)/function pointsOf(uint256 account)/' src/interfaces/IWhitelistCurator.sol
forge test --match-test test_selectors_match_the_deployed_game -vv
```

Expected — the assertion fails, naming the label you gave it (`bytes4` values print right-padded to 32 bytes):

```
[FAIL: pointsOf: 0x8241135800000000000000000000000000000000000000000000000000000000 != 0xcf6a440300000000000000000000000000000000000000000000000000000000] test_selectors_match_the_deployed_game()
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Restore and confirm green:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/function pointsOf(uint256 account)/function pointsOf(address account)/' src/interfaces/IWhitelistCurator.sol
forge test --match-test test_selectors_match_the_deployed_game -vv
```

Expected: `1 passed; 0 failed`.

- [ ] **Step 14: Prove the renderer pin bites.** The mutation is the realistic one: someone widens a struct field. Note that a *reorder* of two `uint256` fields would NOT be caught here, and that is expected — the ABI type list is unchanged. Say so if you are tempted to strengthen this test; Task 9's golden `tokenURI` is where a weight/credit swap is caught.

```bash
cd /Library/Vibes/list-record
sed -i '' 's/    uint8 status;/    uint256 status;/' src/interfaces/IListRecordRenderer.sol
forge test --match-test test_the_renderer_call_shape_is_pinned -vv
```

Expected:

```
[FAIL: renderer tokenURI: 0x9c715c7900000000000000000000000000000000000000000000000000000000 != 0x4fa1d28400000000000000000000000000000000000000000000000000000000] test_the_renderer_call_shape_is_pinned()
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Restore, then confirm the whole file is green and that `forge fmt` agrees with the 120-column setting — if it does not, later tasks quoting these lines verbatim will not match:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/    uint256 status;/    uint8 status;/' src/interfaces/IListRecordRenderer.sol
forge test --match-path test/Interface.t.sol -vv
forge fmt --check
```

Expected: `2 passed; 0 failed`, and `forge fmt --check` prints nothing and exits 0.

- [ ] **Step 15: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/interfaces/IWhitelistCurator.sol src/interfaces/IListRecordRenderer.sol test/Interface.t.sol
git commit -m "feat: IWhitelistCurator and IListRecordRenderer, with all ten selectors pinned"
```

---

### Task 2: MockList and the wallet fixture, seeded from real captures

Every test in this repository has to talk to the game contract, and no test may touch the network — a suite that reaches out to an RPC is slow, flaky, and silently green when the network is down. So we build a **mock**: a small local Solidity contract implementing the same interface as the deployed game, returning whatever we tell it to. Its numbers come from real captures of the live game, committed as a JSON fixture, so the cards the renderer produces later are rendered against values the chain actually held rather than round made-up ones.

**The `firstHour + 1` trap — read this before you write a line.** The deployed game stores each member in a packed struct whose last field is `uint32 firstHour`, and it stores the hour **plus one**, so that the zero value means "this address never deposited":

```solidity
struct Contributor {
    uint96 highWater;
    uint96 weight;
    uint32 txCount;
    uint32 firstHour;   // hour index of first deposit, +1  (0 == never deposited)
}
```

The public getter `contributors(address)` hands that raw word out. The safe accessor `firstHourOf(address)` decodes it:

```solidity
function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined) {
    uint32 stored = contributors[account].firstHour;
    return stored == 0 ? (0, false) : (stored - 1, true);
}
```

Read the raw getter and treat its fourth word as the hour, and **every address that never played renders as an hour-0 founder** — the rarest cohort in the game (96 wallets out of 15 576). It is a silent bug: no revert, no exception, just a permanent NFT that flatters a stranger. That is why the mock stores `firstHour + 1` internally exactly as the real contract does, exposes both the decoded accessor and the raw word, and why the test below is the most valuable test in the suite.

**Files**

| action | path |
|---|---|
| create | `/Library/Vibes/list-record/test/mocks/MockList.sol` |
| create | `/Library/Vibes/list-record/test/fixtures/wallets.json` |
| modify | `/Library/Vibes/list-record/test/Interface.t.sol` |
| read-only reference | `/Library/Vibes/autopull/docs/curator_sybil_data/population.json`, `first_deposits.json.gz`, `deposits.json.gz`, `sweep_meta.json` |
| read-only reference | `/Library/Vibes/autopull/tests/fixtures/curator/captures/live/20260818T195912Z_hour-boundary.json` |
| read-only reference | `/Library/Vibes/autopull/tests/fixtures/curator/captures/source.sol` |

**Interfaces**

*Consumes* — from Task 1, already on disk: `src/interfaces/IWhitelistCurator.sol`; `foundry.toml` with `{ access = "read", path = "./test/fixtures" }`, without which `vm.readFile` reverts; and `remappings.txt` mapping `forge-std/`.

*Produces* — **`MockList`. These setter names are canonical and no other task may rename them. There is no `setGrace`; a draft elsewhere calling `setGrace(uint256,uint256)` means `setHourParams(uint256,uint256)`.**

```solidity
contract MockList is IWhitelistCurator {
    // seeding
    function setMember(
        address account, uint256 hour, uint256 points_,
        uint256 weightWei_, uint256 creditWei_, uint256 deposits_
    ) external;                                  // reverts if hour >= type(uint32).max
    function removeMember(address account) external;

    // per-field mutation, so a later test can make the game LIE after a token is sealed
    function setPoints(address a, uint256 v) external;
    function setWeight(address a, uint256 v) external;
    function setCredit(address a, uint256 v) external;
    function setDeposits(address a, uint256 v) external;
    function setSettled(bool v) external;
    function setCurrentHour(uint256 v) external;
    function setHourParams(uint256 gracePeriod_, uint256 hourDuration_) external;

    // the trap, exposed on purpose: the raw stored word, firstHour + 1
    function rawFirstHour(address account) external view returns (uint32);
}
```

Defaults matter to Task 3: a freshly constructed `MockList` returns `gracePeriod() == 86400` and `hourDuration() == 3600`, so `ListRecord`'s constructor derivation `graceHours = LIST.gracePeriod() / LIST.hourDuration()` yields **24** with no setup call. `isSettled()` starts `false` and `currentHour()` starts `0`. `setHourParams` is how a test proves `graceHours` is *derived* rather than remembered: call it **before** deploying `ListRecord`, since the constructor reads once.

*Produces* — **`test/fixtures/wallets.json`. Task 2 creates it; Tasks 3–11 READ it and none of them creates it.** Its schema, canonical:

- **Rows are TOP-LEVEL keys. There is no `wallets` container.** A consumer reads `.apex.address`, `.ceiling.hour`, `.judged.points`.
- Seven rows: `floor`, `founder`, `apex`, `nonMember` (real) and `judged`, `envelope`, `ceiling` (synthetic, each labelled as such in `_provenance`).
- Every row has the same seven keys: `address`, `points`, `weightWei`, `creditWei`, `deposits`, `hour`, `window`.
- `points`, `deposits`, `hour` are JSON numbers. **`weightWei` and `creditWei` are decimal STRINGS**, because 79 228 162 514 264 337 593 543 950 335 is not representable as a JSON number. Parse them with `vm.parseUint(json.readString(...))`.
- Keys beginning `_` are provenance and are never read by a test.

Which row to reach for:

| need | row | why |
|---|---|---|
| the card's truncated-address slot | `founder` | real, and its hex has no repeated runs, so `0x381f…1744` is a real truncation |
| a golden card in the grace window | `floor`, `founder` or `apex` | real captured members |
| a golden card in the judged window | `judged` | the sweep stops at hour 23, so **no real judged wallet exists to capture** — see `_provenance` |
| downcast / packing at the edges | `ceiling` | the largest value each `SealedRecord` field can hold |
| a plausible worst case | `envelope` | per-field maxima of the real population, on an invented address |
| the non-member negative | `nonMember` | verified absent from all 15 576 contributors |

Later tasks copy this loader verbatim rather than importing it:

```solidity
function _seed(string memory key) internal returns (address who) {
    string memory p = string.concat(".", key);
    who = json.readAddress(string.concat(p, ".address"));
    list.setMember(
        who,
        json.readUint(string.concat(p, ".hour")),
        json.readUint(string.concat(p, ".points")),
        vm.parseUint(json.readString(string.concat(p, ".weightWei"))),
        vm.parseUint(json.readString(string.concat(p, ".creditWei"))),
        json.readUint(string.concat(p, ".deposits"))
    );
}
```

**Steps**

- [ ] **Step 1: Checksum every address the fixture will carry.** Solidity rejects an address literal whose EIP-55 checksum is wrong, and a later task will paste these into `.sol` files. Derive each one rather than retyping it — this is the command to reuse anywhere in the plan an address literal is needed:

```bash
for a in 0xb363a06aefe98c563fafdc18f0cf1847836f319f \
         0x381fe486d87c7f2633c777f1b5be3105a2a51744 \
         0x2fe4093c894749e596f458764c377bf4f1337b58 \
         0xdead00000000000000000000000000000000beef \
         0xe781b28e02ed5fc4b989905cb6848d318f4735fd \
         0x94446fc7b099ac0f2177ae40eb1eb4d11bae6536 \
         0xcb0b0531e86a9ac36fa865ca8e3dbccf047fda91; do
  printf "%s -> %s\n" "$a" "$(cast to-check-sum-address $a)"
done
```

Expected, exactly:

```
0xb363a06aefe98c563fafdc18f0cf1847836f319f -> 0xb363A06aEfE98c563FaFdC18f0cf1847836f319f
0x381fe486d87c7f2633c777f1b5be3105a2a51744 -> 0x381fe486D87C7F2633c777F1b5bE3105A2a51744
0x2fe4093c894749e596f458764c377bf4f1337b58 -> 0x2fE4093c894749e596f458764c377bF4f1337b58
0xdead00000000000000000000000000000000beef -> 0xDeaD00000000000000000000000000000000BEEf
0xe781b28e02ed5fc4b989905cb6848d318f4735fd -> 0xe781B28e02Ed5Fc4b989905cb6848d318F4735Fd
0x94446fc7b099ac0f2177ae40eb1eb4d11bae6536 -> 0x94446Fc7B099aC0f2177ae40eB1EB4D11BaE6536
0xcb0b0531e86a9ac36fa865ca8e3dbccf047fda91 -> 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91
```

Two traps this catches: `0xdEaD…bEEF`, the form everyone types from memory, is **not** valid EIP-55 — the correct form is `0xDeaD00000000000000000000000000000000BEEf`. And the game address as it appears inside the capture files (`0xcB0b0531e86A9aC36fa865ca8e3DbcCF047fDA91`) is also not valid EIP-55; use the form above.

- [ ] **Step 2: Write the fixture.** Create `/Library/Vibes/list-record/test/fixtures/wallets.json`. Three rows are real wallets with the numbers the chain actually held; three are explicitly synthetic, and the file says which is which and why. Attaching population-envelope or structural numbers to a real address would be a lie about that wallet, so those rows get invented addresses whose repeated digits make them unmistakable.

```json
{
  "_schema": "Rows are TOP-LEVEL keys: .floor .founder .apex .nonMember .judged .envelope .ceiling — there is no `wallets` container. Every row has the same seven keys. `points`, `deposits` and `hour` are JSON numbers; `weightWei` and `creditWei` are DECIMAL STRINGS, because 79228162514264337593543950335 is not representable as a JSON number.",
  "_captures": {
    "sweep": "docs/curator_sybil_data/deposits.json.gz + first_deposits.json.gz of the maxpane repo; sweep_meta.json says 2026-08-17 19:44:40 UTC, block 25776962, 15576 contributors, 22319 deposits, is_settled false.",
    "constants": "tests/fixtures/curator/captures/live/20260818T195912Z_hour-boundary.json: gracePeriod 86400, hourDuration 3600, firstJudgedHour 24, minDeposit 50000000000000000, minEscalation 100000000000000000, creditCap 1000000000000000000000, POINTS_PER_ETH 1000, earlyMultiplierBps 10000, currentHour 48, isSettled false.",
    "curve": "pointsOf(a) = isqrt(weightOf(a)) * 1000 / 1e9, from the verified source at tests/fixtures/curator/captures/source.sol.",
    "credit": "contributedBy(a) returns `highWater`, the LARGEST SINGLE SEND, uncapped — not the credited amount and not a lifetime sum. population.json's credit_wei is the credited figure and is capped at creditCap; the two differ and must never be swapped."
  },
  "_provenance": {
    "floor": "REAL. The lowest-points wallet in the sweep; 225 points is the population minimum.",
    "founder": "REAL. The highest-weight wallet of the 96-wallet hour-0 founder cohort. Its hex has no repeated runs, so this is the row to use for the card's truncated-address slot.",
    "apex": "REAL. The highest-points wallet in the sweep, and the population maximum for both points and weight.",
    "nonMember": "REAL NEGATIVE. Verified absent from all 15576 contributors in first_deposits.json.gz.",
    "judged": "SYNTHETIC ADDRESS, STRUCTURAL NUMBERS. The sweep stops at hour 23, entirely inside the grace period, so it contains NO judged-hour wallet at all and none could be captured. The numbers come from contract constants: a first deposit of minDeposit (5e16 wei) in a judged hour, where earlyMultiplierBps is flat 10000, so weight == credit == 5e16 and points = isqrt(5e16)*1000/1e9 = 223. Hour 30 is a real elapsed judged hour: firstJudgedHour is 24 and currentHour was 48 at the 2026-08-18 capture.",
    "envelope": "SYNTHETIC ADDRESS, REAL PER-FIELD MAXIMA. No captured wallet holds all of these at once, which is exactly why the address is invented: points 36924 and weight 1363396200000000000000 are 0x2fE4...7b58's, credit 4040000000000000000000 is 0xe781...35Fd's largest single send, deposits 120 is 0x9444...6536's, hour 0 is the founder cohort's.",
    "ceiling": "SYNTHETIC, TYPE EDGES. Not a wallet and not reachable: the largest value each SealedRecord field can hold. hour is 4294967294 and not 4294967295 because the game stores firstHour + 1 in a uint32, so 4294967295 wraps to 0 and the member would read as a stranger. 2**32-2 is the largest first hour the encoding can represent, in the deployed contract as much as in MockList."
  },
  "_realWalletsNotUsedAsRows": {
    "maxCredit": "0xe781B28e02Ed5Fc4b989905cb6848d318F4735Fd — largest single send 4040000000000000000000 wei, weight 1139900000000000000000, 1 deposit, hour 20, 33762 points.",
    "maxDeposits": "0x94446Fc7B099aC0f2177ae40eB1EB4D11BaE6536 — 120 deposits, largest single send 11950000000000000000 wei, weight 18123945000000000000, hour 11, 4257 points."
  },
  "graceHours": 24,
  "floor": {
    "address": "0xb363A06aEfE98c563FaFdC18f0cf1847836f319f",
    "points": 225,
    "weightWei": "50750000000000000",
    "creditWei": "50000000000000000",
    "deposits": 1,
    "hour": 23,
    "window": "grace"
  },
  "founder": {
    "address": "0x381fe486D87C7F2633c777F1b5bE3105A2a51744",
    "points": 30035,
    "weightWei": "902107370000000000000",
    "creditWei": "461100000000000000000",
    "deposits": 2,
    "hour": 0,
    "window": "grace"
  },
  "apex": {
    "address": "0x2fE4093c894749e596f458764c377bF4f1337b58",
    "points": 36924,
    "weightWei": "1363396200000000000000",
    "creditWei": "786000000000000000000",
    "deposits": 2,
    "hour": 6,
    "window": "grace"
  },
  "nonMember": {
    "address": "0xDeaD00000000000000000000000000000000BEEf",
    "points": 0,
    "weightWei": "0",
    "creditWei": "0",
    "deposits": 0,
    "hour": 0,
    "window": "none"
  },
  "judged": {
    "address": "0x1111111111111111111111111111111111111111",
    "points": 223,
    "weightWei": "50000000000000000",
    "creditWei": "50000000000000000",
    "deposits": 1,
    "hour": 30,
    "window": "judged"
  },
  "envelope": {
    "address": "0x2222222222222222222222222222222222222222",
    "points": 36924,
    "weightWei": "1363396200000000000000",
    "creditWei": "4040000000000000000000",
    "deposits": 120,
    "hour": 0,
    "window": "grace"
  },
  "ceiling": {
    "address": "0x3333333333333333333333333333333333333333",
    "points": 4294967295,
    "weightWei": "79228162514264337593543950335",
    "creditWei": "79228162514264337593543950335",
    "deposits": 4294967295,
    "hour": 4294967294,
    "window": "judged"
  }
}
```

- [ ] **Step 3: Verify every row against the captures before any test depends on it.** This re-derives the three real rows straight from the deposit log, re-checks the non-member's absence, re-checks that the envelope really is the per-field maxima and that no single wallet holds them all, re-derives the judged row from the points curve, and checks the ceiling sits on the type edges. A fixture whose numbers cannot be re-derived is indistinguishable from one somebody invented.

```bash
python3 -c "
import json, gzip, math
FX = '/Library/Vibes/list-record/test/fixtures/wallets.json'
D  = '/Library/Vibes/autopull/docs/curator_sybil_data/'
fx = json.load(open(FX))

dp = json.load(gzip.open(D + 'deposits.json.gz'))
agg = {}
for d in sorted(dp, key=lambda r: (r['block'], r['log_index'])):
    a = agg.setdefault(d['contributor'], {'weightWei': 0, 'creditWei': 0, 'deposits': 0, 'hour': None})
    a['weightWei'] = d['new_weight_wei']
    a['creditWei'] = max(a['creditWei'], d['amount_wei'])
    a['deposits']  = max(a['deposits'], d['tx_count'])
    if a['hour'] is None: a['hour'] = d['hour']
for a in agg.values():
    a['points'] = math.isqrt(a['weightWei']) * 1000 // 10**9

for row in ('floor', 'founder', 'apex'):
    r = fx[row]; live = agg[r['address'].lower()]
    ok = all(str(live[k]) == str(r[k]) for k in ('points','weightWei','creditWei','deposits','hour'))
    print(row, 'REAL', 'MATCH' if ok else 'MISMATCH')

fd = json.load(gzip.open(D + 'first_deposits.json.gz'))
members = {r['contributor'].lower() for r in fd}
print('contributors', len(members), 'nonMember absent', fx['nonMember']['address'].lower() not in members)

e = fx['envelope']
print('envelope maxima',
      e['points'] == max(a['points'] for a in agg.values()),
      int(e['weightWei']) == max(a['weightWei'] for a in agg.values()),
      int(e['creditWei']) == max(a['creditWei'] for a in agg.values()),
      e['deposits'] == max(a['deposits'] for a in agg.values()),
      'no single wallet holds all',
      not any(a['points'] == e['points'] and a['deposits'] == e['deposits'] for a in agg.values()))

j = fx['judged']
print('judged derived', math.isqrt(int(j['weightWei'])) * 1000 // 10**9 == j['points'] == 223,
      int(j['weightWei']) == int(j['creditWei']) == 50000000000000000,
      j['hour'] >= fx['graceHours'])

c = fx['ceiling']
print('ceiling edges', c['points'] == 2**32-1, int(c['weightWei']) == 2**96-1,
      int(c['creditWei']) == 2**96-1, c['deposits'] == 2**32-1, c['hour'] == 2**32-2)
"
```

Expected output, exactly:

```
floor REAL MATCH
founder REAL MATCH
apex REAL MATCH
contributors 15576 nonMember absent True
envelope maxima True True True True no single wallet holds all True
judged derived True True True
ceiling edges True True True True True
```

If a real row prints `MISMATCH`, the capture is authoritative — fix the fixture, never the arithmetic.

- [ ] **Step 4: Write the failing tests.** Replace the whole of `/Library/Vibes/list-record/test/Interface.t.sol` with the version below. It keeps Task 1's two selector tests and adds nine more. It will not compile yet, because `test/mocks/MockList.sol` does not exist.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IWhitelistCurator} from "../src/interfaces/IWhitelistCurator.sol";
import {IListRecordRenderer, CardData} from "../src/interfaces/IListRecordRenderer.sol";
import {MockList} from "./mocks/MockList.sol";

contract InterfaceTest is Test {
    using stdJson for string;

    MockList internal list;
    string internal json;

    function setUp() public {
        list = new MockList();
        json = vm.readFile("test/fixtures/wallets.json");
    }

    /// @dev weightWei and creditWei are decimal STRINGS in the fixture: they exceed what a
    ///      JSON number carries losslessly, so they are parsed with vm.parseUint.
    function _seed(string memory key) internal returns (address who) {
        string memory p = string.concat(".", key);
        who = json.readAddress(string.concat(p, ".address"));
        list.setMember(
            who,
            json.readUint(string.concat(p, ".hour")),
            json.readUint(string.concat(p, ".points")),
            vm.parseUint(json.readString(string.concat(p, ".weightWei"))),
            vm.parseUint(json.readString(string.concat(p, ".creditWei"))),
            json.readUint(string.concat(p, ".deposits"))
        );
    }

    function test_selectors_match_the_deployed_game() public pure {
        assertEq(IWhitelistCurator.pointsOf.selector, bytes4(0xcf6a4403), "pointsOf");
        assertEq(IWhitelistCurator.weightOf.selector, bytes4(0xdd4bc101), "weightOf");
        assertEq(IWhitelistCurator.contributedBy.selector, bytes4(0x64a8e570), "contributedBy");
        assertEq(IWhitelistCurator.txCountOf.selector, bytes4(0x662d7299), "txCountOf");
        assertEq(IWhitelistCurator.firstHourOf.selector, bytes4(0xc5148173), "firstHourOf");
        assertEq(IWhitelistCurator.isSettled.selector, bytes4(0x3270bb5b), "isSettled");
        assertEq(IWhitelistCurator.currentHour.selector, bytes4(0x020e185d), "currentHour");
        assertEq(IWhitelistCurator.gracePeriod.selector, bytes4(0xa06db7dc), "gracePeriod");
        assertEq(IWhitelistCurator.hourDuration.selector, bytes4(0xda25efd9), "hourDuration");
    }

    function test_the_renderer_call_shape_is_pinned() public pure {
        assertEq(IListRecordRenderer.tokenURI.selector, bytes4(0x4fa1d284), "renderer tokenURI");
        CardData memory d;
        assertEq(abi.encode(d).length, 320, "CardData is ten words");
    }

    /// THE trap test. The game stores firstHour + 1, so the raw slot is 1 for an hour-0
    /// founder and 0 for a stranger — but firstHourOf's FIRST return word is 0 for both.
    /// Only the second word tells them apart. Anything that reads the hour without reading
    /// hasJoined mints every stranger as a founder.
    function test_a_non_member_is_not_an_hour_zero_founder() public {
        address founder = _seed("founder"); // real hour-0 member
        address stranger = json.readAddress(".nonMember.address");

        (uint256 fHour, bool fJoined) = list.firstHourOf(founder);
        assertEq(fHour, 0, "founder hour");
        assertTrue(fJoined, "founder joined");

        (uint256 sHour, bool sJoined) = list.firstHourOf(stranger);
        assertEq(sHour, 0, "stranger hour word");
        assertFalse(sJoined, "stranger must not have joined");

        // the two are indistinguishable by hour and distinguishable only by the raw slot
        assertEq(sHour, fHour, "hour word cannot separate them");
        assertEq(list.rawFirstHour(founder), 1, "founder raw slot");
        assertEq(list.rawFirstHour(stranger), 0, "stranger raw slot");
    }

    function test_a_non_member_reads_zero_everywhere() public view {
        address stranger = json.readAddress(".nonMember.address");
        assertEq(list.pointsOf(stranger), 0, "points");
        assertEq(list.weightOf(stranger), 0, "weight");
        assertEq(list.contributedBy(stranger), 0, "credit");
        assertEq(list.txCountOf(stranger), 0, "deposits");
    }

    function test_the_floor_wallet_round_trips() public {
        address floor = _seed("floor");
        (uint256 hour, bool joined) = list.firstHourOf(floor);
        assertEq(hour, 23, "hour");
        assertTrue(joined, "joined");
        assertEq(list.pointsOf(floor), 225, "points");
        assertEq(list.weightOf(floor), 50750000000000000, "weight");
        assertEq(list.contributedBy(floor), 0.05 ether, "credit");
        assertEq(list.txCountOf(floor), 1, "deposits");
    }

    function test_the_apex_wallet_round_trips() public {
        address apex = _seed("apex");
        assertEq(list.pointsOf(apex), 36924, "points");
        assertEq(list.weightOf(apex), 1363396200000000000000, "weight");
        assertEq(list.contributedBy(apex), 786 ether, "credit");
        assertEq(list.txCountOf(apex), 2, "deposits");
        (uint256 hour,) = list.firstHourOf(apex);
        assertEq(hour, 6, "hour");
    }

    /// @dev graceHours is derived, never hardcoded: ListRecord's constructor computes
    ///      gracePeriod() / hourDuration(), and the mock's defaults must make that 24.
    function test_the_mock_defaults_derive_twentyfour_grace_hours() public view {
        assertEq(list.gracePeriod(), 86400, "gracePeriod");
        assertEq(list.hourDuration(), 3600, "hourDuration");
        assertEq(list.gracePeriod() / list.hourDuration(), json.readUint(".graceHours"), "graceHours");
        assertFalse(list.isSettled(), "starts unsettled");
        assertEq(list.currentHour(), 0, "starts at hour 0");
    }

    /// @dev Every member row's `window` must be what the derived boundary actually says, so
    ///      a later card test cannot render `grace` off a row the arithmetic calls judged.
    function test_every_member_row_lands_in_the_window_the_fixture_names() public {
        string[6] memory rows = ["floor", "founder", "apex", "judged", "envelope", "ceiling"];
        uint256 graceHours = list.gracePeriod() / list.hourDuration();
        for (uint256 i = 0; i < rows.length; i++) {
            address who = _seed(rows[i]);
            (uint256 hour, bool joined) = list.firstHourOf(who);
            assertTrue(joined, string.concat(rows[i], ": joined"));
            bool grace = hour < graceHours;
            string memory want = json.readString(string.concat(".", rows[i], ".window"));
            assertEq(grace ? "grace" : "judged", want, string.concat(rows[i], ": window"));
        }
    }

    /// @dev The ceiling row is what Task 4's SealedRecord downcast tests aim at, so its
    ///      values must really be the type edges rather than merely large.
    function test_the_boundary_rows_sit_on_the_type_edges() public {
        address ceiling = _seed("ceiling");
        assertEq(list.pointsOf(ceiling), type(uint32).max, "points at the uint32 edge");
        assertEq(list.weightOf(ceiling), type(uint96).max, "weight at the uint96 edge");
        assertEq(list.contributedBy(ceiling), type(uint96).max, "credit at the uint96 edge");
        assertEq(list.txCountOf(ceiling), type(uint32).max, "deposits at the uint32 edge");
        (uint256 hour,) = list.firstHourOf(ceiling);
        assertEq(hour, uint256(type(uint32).max) - 1, "hour one under the uint32 edge");

        // One higher is unrepresentable: firstHour + 1 wraps a uint32 back to "never
        // deposited", in the deployed contract as much as here, so the mock refuses to
        // create a member who would read as a stranger.
        vm.expectRevert(bytes("MockList: hour would wrap the +1 encoding"));
        list.setMember(address(0xBEEF), uint256(type(uint32).max), 1, 1, 1, 1);
    }

    /// @dev A sealed token must survive the game changing its mind. Later tasks need the
    ///      mock to be able to lie after a seal, so prove every field is mutable and a
    ///      member can be erased entirely.
    function test_the_mock_game_can_lie_after_a_seal() public {
        address apex = _seed("apex");
        list.setSettled(true);
        assertTrue(list.isSettled(), "settled");

        list.setPoints(apex, 1);
        list.setWeight(apex, 0);
        list.setCredit(apex, 0);
        list.setDeposits(apex, 0);
        assertEq(list.pointsOf(apex), 1, "points now lie");
        assertEq(list.weightOf(apex), 0, "weight now lies");
        assertEq(list.contributedBy(apex), 0, "credit now lies");
        assertEq(list.txCountOf(apex), 0, "deposits now lie");

        list.removeMember(apex);
        (, bool joined) = list.firstHourOf(apex);
        assertFalse(joined, "the game may forget a member entirely");
    }

    /// @dev The sweep captured no judged wallet, so the other way to reach the judged side
    ///      with a REAL wallet is to move the boundary. This is the technique a later task
    ///      uses to prove graceHours is read from the game rather than assumed to be 24 —
    ///      call setHourParams BEFORE deploying ListRecord, whose constructor reads once.
    function test_shrinking_the_grace_window_reclassifies_a_real_grace_wallet() public {
        address floor = _seed("floor"); // real, hour 23, inside the default 24-hour grace
        (uint256 hour,) = list.firstHourOf(floor);
        assertTrue(hour < list.gracePeriod() / list.hourDuration(), "grace under the live params");

        list.setHourParams(3600, 3600); // graceHours == 1
        assertEq(list.gracePeriod() / list.hourDuration(), 1, "graceHours now 1");
        assertFalse(hour < list.gracePeriod() / list.hourDuration(), "judged under the new params");
    }
}
```

- [ ] **Step 5: Run it and watch it fail for the right reason.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Interface.t.sol
```

Expected — a compile error naming the missing mock, **not** an assertion failure:

```
Compiler run failed:
Error (6275): Source "test/mocks/MockList.sol" not found: File not found.
 --> test/Interface.t.sol:8:1:
  |
8 | import {MockList} from "./mocks/MockList.sol";
```

- [ ] **Step 6: Write the mock.** Create `/Library/Vibes/list-record/test/mocks/MockList.sol`. One design decision carries the whole task: the internal mapping is named `_firstHourPlusOne` and `setMember` is the **only** way to write it, so no code path can produce a member whose stored slot is 0 or a stranger whose stored slot is non-zero.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IWhitelistCurator} from "../../src/interfaces/IWhitelistCurator.sol";

/// @notice Local stand-in for the deployed game. Tests never touch the network; this is the
///         only game contract the default suite sees.
///
/// @dev    The storage mirrors the real `Contributor` struct's encoding on purpose:
///         `firstHour` is stored **plus one**, so 0 means "never deposited". Keeping that
///         encoding here is what makes it impossible to seed a member who reads as a
///         non-member, or a non-member who reads as an hour-0 founder. `rawFirstHour`
///         exposes the undecoded word so a test can show the trap rather than describe it.
contract MockList is IWhitelistCurator {
    mapping(address => uint32) private _firstHourPlusOne;
    mapping(address => uint256) private _points;
    mapping(address => uint256) private _weightWei;
    mapping(address => uint256) private _creditWei;
    mapping(address => uint256) private _deposits;

    bool private _settled;
    uint256 private _currentHour;
    // Live values on this deployment, from the capture at 2026-08-18T19:59:12Z:
    // gracePeriod() == 86400 and hourDuration() == 3600, so graceHours derives to 24.
    uint256 private _gracePeriod = 86400;
    uint256 private _hourDuration = 3600;

    /*//////////////////////////////////////////////////////////////
                                SEEDING
    //////////////////////////////////////////////////////////////*/

    /// @notice The only way to make an address a member. `hour` is the real, decoded hour;
    ///         the +1 encoding is applied here and nowhere else.
    function setMember(
        address account,
        uint256 hour,
        uint256 points_,
        uint256 weightWei_,
        uint256 creditWei_,
        uint256 deposits_
    ) external {
        require(hour < type(uint32).max, "MockList: hour would wrap the +1 encoding");
        // casting to uint32 is safe: guarded one line above, and the game stores firstHour
        // in a uint32 slot.
        // forge-lint: disable-next-line(unsafe-typecast)
        _firstHourPlusOne[account] = uint32(hour + 1);
        _points[account] = points_;
        _weightWei[account] = weightWei_;
        _creditWei[account] = creditWei_;
        _deposits[account] = deposits_;
    }

    /// @notice Erase an address back to a non-member.
    function removeMember(address account) external {
        delete _firstHourPlusOne[account];
        delete _points[account];
        delete _weightWei[account];
        delete _creditWei[account];
        delete _deposits[account];
    }

    /*//////////////////////////////////////////////////////////////
                    MUTATION — so the game can LIE
    //////////////////////////////////////////////////////////////*/

    function setPoints(address a, uint256 v) external {
        _points[a] = v;
    }

    function setWeight(address a, uint256 v) external {
        _weightWei[a] = v;
    }

    function setCredit(address a, uint256 v) external {
        _creditWei[a] = v;
    }

    function setDeposits(address a, uint256 v) external {
        _deposits[a] = v;
    }

    function setSettled(bool v) external {
        _settled = v;
    }

    function setCurrentHour(uint256 v) external {
        _currentHour = v;
    }

    /// @notice Move the grace boundary. There is no `setGrace`; this is that function.
    function setHourParams(uint256 gracePeriod_, uint256 hourDuration_) external {
        require(hourDuration_ != 0, "MockList: hourDuration 0 would divide by zero");
        _gracePeriod = gracePeriod_;
        _hourDuration = hourDuration_;
    }

    /*//////////////////////////////////////////////////////////////
                                 VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice The raw stored word, `firstHour + 1` — the shape of the real
    ///         `contributors(address)` getter's fourth word. Reading THIS as the hour is the
    ///         bug; it exists here only so a test can demonstrate it.
    function rawFirstHour(address account) external view returns (uint32) {
        return _firstHourPlusOne[account];
    }

    function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined) {
        uint32 stored = _firstHourPlusOne[account];
        return stored == 0 ? (0, false) : (stored - 1, true);
    }

    function pointsOf(address a) external view returns (uint256) {
        return _points[a];
    }

    function weightOf(address a) external view returns (uint256) {
        return _weightWei[a];
    }

    function contributedBy(address a) external view returns (uint256) {
        return _creditWei[a];
    }

    function txCountOf(address a) external view returns (uint256) {
        return _deposits[a];
    }

    function isSettled() external view returns (bool) {
        return _settled;
    }

    function currentHour() external view returns (uint256) {
        return _currentHour;
    }

    function gracePeriod() external view returns (uint256) {
        return _gracePeriod;
    }

    function hourDuration() external view returns (uint256) {
        return _hourDuration;
    }
}
```

- [ ] **Step 7: Run the tests and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Interface.t.sol -vv
```

Expected — **11 passing tests, and a bare `forge test` at this point in the plan runs exactly these 11**, all in `InterfaceTest` (gas figures are printed too and are not part of the expectation):

```
Ran 11 tests for test/Interface.t.sol:InterfaceTest
[PASS] test_a_non_member_is_not_an_hour_zero_founder()
[PASS] test_a_non_member_reads_zero_everywhere()
[PASS] test_every_member_row_lands_in_the_window_the_fixture_names()
[PASS] test_selectors_match_the_deployed_game()
[PASS] test_shrinking_the_grace_window_reclassifies_a_real_grace_wallet()
[PASS] test_the_apex_wallet_round_trips()
[PASS] test_the_boundary_rows_sit_on_the_type_edges()
[PASS] test_the_floor_wallet_round_trips()
[PASS] test_the_mock_defaults_derive_twentyfour_grace_hours()
[PASS] test_the_mock_game_can_lie_after_a_seal()
[PASS] test_the_renderer_call_shape_is_pinned()
Suite result: ok. 11 passed; 0 failed; 0 skipped
```

`forge test` prints no lint notes. A `forge build` does, and one is expected and correct — reading the committed fixture is the intent:

```
note[unsafe-cheatcode]: usage of unsafe cheatcodes that can perform dangerous operations
  --> test/Interface.t.sol:18:19
   |
18 |         json = vm.readFile("test/fixtures/wallets.json");
```

- [ ] **Step 8: Prove the trap test bites — mutation A, drop the `+ 1`.** This is the bug where the mock stores the raw hour, so an hour-0 founder becomes indistinguishable from a stranger. `test/mocks/MockList.sol` is not committed until Step 11, so the restore is the reverse `sed` (see Task 1 Step 13 for when `git checkout --` is the right tool instead).

```bash
cd /Library/Vibes/list-record
sed -i '' 's/_firstHourPlusOne\[account\] = uint32(hour + 1);/_firstHourPlusOne[account] = uint32(hour);/' test/mocks/MockList.sol
forge test --match-test test_a_non_member_is_not_an_hour_zero_founder -vv
```

Expected:

```
[FAIL: founder joined] test_a_non_member_is_not_an_hour_zero_founder()
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Restore:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/_firstHourPlusOne\[account\] = uint32(hour);/_firstHourPlusOne[account] = uint32(hour + 1);/' test/mocks/MockList.sol
forge test --match-test test_a_non_member_is_not_an_hour_zero_founder -vv
```

Expected: `1 passed; 0 failed`.

- [ ] **Step 9: Prove it bites — mutation B, hand out the raw word.** This is the real-world bug in its exact shape: `firstHourOf` returning the undecoded slot, so every member is off by one hour and every stranger claims hour 0.

```bash
cd /Library/Vibes/list-record
sed -i '' 's/return stored == 0 ? (0, false) : (stored - 1, true);/return (uint256(stored), true);/' test/mocks/MockList.sol
forge test --match-test test_a_non_member_is_not_an_hour_zero_founder -vv
```

Expected:

```
[FAIL: founder hour: 1 != 0] test_a_non_member_is_not_an_hour_zero_founder()
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Restore:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/return (uint256(stored), true);/return stored == 0 ? (0, false) : (stored - 1, true);/' test/mocks/MockList.sol
forge test --match-test test_a_non_member_is_not_an_hour_zero_founder -vv
```

Expected: `1 passed; 0 failed`.

- [ ] **Step 10: Prove the wrap guard bites — mutation C, widen its type.** Without the guard a caller can seed hour `2**32-1`, `hour + 1` wraps a uint32 to 0, and the "member" silently becomes a stranger. Widening the type to `uint64` leaves the guard present but useless, which is how such a bug actually gets written.

```bash
cd /Library/Vibes/list-record
sed -i '' 's/require(hour < type(uint32).max, "MockList: hour would wrap/require(hour < type(uint64).max, "MockList: hour would wrap/' test/mocks/MockList.sol
forge test --match-test test_the_boundary_rows_sit_on_the_type_edges -vv
```

Expected:

```
[FAIL: next call did not revert as expected] test_the_boundary_rows_sit_on_the_type_edges()
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Restore, then confirm the file is green, unmutated and format-clean:

```bash
cd /Library/Vibes/list-record
sed -i '' 's/require(hour < type(uint64).max, "MockList: hour would wrap/require(hour < type(uint32).max, "MockList: hour would wrap/' test/mocks/MockList.sol
forge test --match-path test/Interface.t.sol -vv
forge fmt --check
grep -n "uint32(hour + 1)\|stored == 0 ? (0, false)\|require(hour < type(uint32).max" test/mocks/MockList.sol
```

Expected: `11 passed; 0 failed`; `forge fmt --check` prints nothing and exits 0; and the `grep` prints three lines, one for each restored construct.

- [ ] **Step 11: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/mocks/MockList.sol test/fixtures/wallets.json test/Interface.t.sol
git commit -m "test: MockList and a capture-backed wallet fixture, with the firstHour+1 trap pinned"
```

---

### Task 3: `ListRecord` — constructor, `claim()` and `claimFor()`

THE LIST is a deployed, unowned, non-upgradeable Ethereum game contract (`WhitelistCurator`, `0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`). Wallets deposited ETH into it during a grace window and then during judged hours; the contract stores each wallet's `weight`, its `highWater` credit, its deposit count and the hour of its first deposit. `ListRecord` is a **separate** ERC-721 collection that lets any of those wallets mint a permanent record of what it did — by *asking the game*, with no merkle root, no allowlist and no admin.

You are building the mint half. You need to know only three things about the game:

1. `firstHourOf(address)` returns **two** words — `(hour, hasJoined)`. `hasJoined` is the entire membership test. **Never** derive membership from the hour word: a wallet that never played returns hour `0`, which is also the hour of the rarest, earliest cohort in the game. Reading the hour alone makes every stranger look like a founder. (Spec §1.1. Note that section's 2026-08-18 correction: the raw `contributors` getter *is* vendored in maxpane, so this rule is discipline enforced by a test rather than an absence — which makes Step 23's test more load-bearing, not less.)
2. `currentHour()` returns the game's own hour counter — how far into the game we are *right now*. This is not the same as a member's join hour.
3. `gracePeriod()` and `hourDuration()` are seconds. Their quotient is the number of grace hours (24 on the live deployment). **Read it; never type `24`.** This repo's rule is that documented constants drift and chains do not.

There is no owner, no pause, no price and no withdraw in this contract, and none may be added.

**Restoring a mutation — read once, applies to Tasks 3, 4 and 5.** Every mutation step below is ordered *after* the commit that introduces the code it mutates, and is undone with `git checkout -- <path>`. That is deliberately the opposite of maxpane's blanket ban on `git checkout --`: that ban exists because the maxpane working tree routinely holds another person's uncommitted work. `/Library/Vibes/list-record` is a fresh repository created by Task 1 for this plan alone, with no third-party uncommitted work in it, so the exact-restore property is worth more than the ban. The one exception is anything under `template/` (Task 6's generated blob and offsets) — those are **regenerated with the tool**, never checked out, so the blob and the offsets can never drift apart. Tasks 3–5 touch nothing under `template/`.

**Files**

- Create: `/Library/Vibes/list-record/src/ListRecord.sol`
- Create (test): `/Library/Vibes/list-record/test/Claim.t.sol`
- Read only: `/Library/Vibes/list-record/src/interfaces/IWhitelistCurator.sol`, `/Library/Vibes/list-record/src/interfaces/IListRecordRenderer.sol`, `/Library/Vibes/list-record/test/mocks/MockList.sol`, `/Library/Vibes/list-record/test/fixtures/wallets.json`

This task creates no fixture and no interface. It modifies no file owned by another task.

**Interfaces**

*Consumes — from Task 1 (`src/interfaces/`).* Task 1 creates **both** interface files, `IWhitelistCurator.sol` and `IListRecordRenderer.sol`, before this task runs. No later task creates either one; Task 7 implements `IListRecordRenderer` but does not author the file.

```solidity
interface IWhitelistCurator {
    function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined);
    function pointsOf(address account) external view returns (uint256);
    function weightOf(address account) external view returns (uint256);
    function contributedBy(address account) external view returns (uint256);
    function txCountOf(address account) external view returns (uint256);
    function isSettled() external view returns (bool);
    function currentHour() external view returns (uint256);
    function gracePeriod() external view returns (uint256);
    function hourDuration() external view returns (uint256);
}

struct CardData {
    uint256 id; address claimant; address owner; uint256 points; uint256 weightWei;
    uint256 creditWei; uint256 deposits; uint256 hour; bool grace; uint8 status;
}
interface IListRecordRenderer { function tokenURI(CardData calldata d) external view returns (string memory); }
```

*Consumes — from Task 1 (`foundry.toml`):* `solc = "0.8.24"`, `optimizer_runs = 200`,
`fs_permissions = [{access = "read", path = "./test/fixtures"}, {access = "read", path = "./template"}]`
(the `./template` entry is Task 6's; the `./test/fixtures` entry is what `vm.readFile` needs here), and a top-level `[fmt]` section with `line_length = 120`, `tab_width = 4`, `bracket_spacing = false`.

*Consumes — from Task 1 (`remappings.txt`), exactly two lines:*

```
forge-std/=lib/forge-std/src/
@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
```

so imports read `@openzeppelin/contracts/token/ERC721/ERC721.sol`, against OpenZeppelin v5.x. Do not rewrite or re-commit this file; Task 1 settled it.

*Consumes — from Task 2 (`test/mocks/MockList.sol`), a hermetic stand-in for the game. These are the canonical setter names; there is no `setGrace`:*

```solidity
function setMember(address account, uint256 hour, uint256 points, uint256 weightWei, uint256 creditWei, uint256 deposits) external;
function removeMember(address account) external;
function setSettled(bool v) external;
function setCurrentHour(uint256 h) external;
function setHourParams(uint256 gracePeriod_, uint256 hourDuration_) external;
```

Defaults with no setter called: not settled, `currentHour() == 0`, `gracePeriod() == 86400`, `hourDuration() == 3600` (so `graceHours == 24`), and every unseeded address returns `(0, false)` from `firstHourOf`.

*Consumes — from Task 2 (`test/fixtures/wallets.json`).* Task 2 owns and creates this file. Tasks 3, 4 and 5 only read it, and they read these paths:

- `.graceHours` — number; the real game's grace-hour count, which must equal the mock's default quotient.
- `.wallets.apex.address` / `.hour` / `.points` / `.weightWei` / `.creditWei` / `.deposits` — a **real captured** member. The two wei fields are decimal **strings** (JSON numbers cannot carry 21 digits losslessly) and are parsed with `vm.parseUint`; the rest are JSON numbers.
- `.wallets.second.*` — the same six fields for a second real captured member, so claim-order and batch-range tests have two distinct claimants.
- `.wallets.ceiling.*` — the **synthetic** structural-maximum row Task 4 uses for the downcast test (see Task 4's Interfaces block for the bounds it must satisfy).
- `._provenance` — the block that says which rows are real, which are synthetic, and why.

Nothing in Tasks 3–5 hardcodes a wallet address, a points figure or a wei amount. That is the point: it removes any possibility of a task attaching one wallet's numbers to another wallet's address, and it makes `wallets.json` the single place provenance is stated.

*Produces — for Tasks 4, 5 and 8:*

```solidity
contract ListRecord is ERC721 {                 // name "THE LIST", symbol "LIST"
    IWhitelistCurator public immutable LIST;
    IListRecordRenderer public immutable renderer;
    uint256 public immutable graceHours;        // = LIST.gracePeriod() / LIST.hourDuration()

    uint256 public totalClaimed;                // last minted id
    mapping(address => uint256) public tokenOf;      // 0 = unclaimed; also the double-claim guard
    mapping(uint256 => address) public claimantOf;   // never changes when the token is sold
    mapping(uint256 => uint32)  public claimedAtHour; // the GAME hour at claim, not the join hour

    error NotAMember();
    error AlreadyClaimed();
    event Claimed(address indexed member, uint256 indexed id, uint32 hour);

    constructor(address list_, address renderer_);
    function claim() external returns (uint256 id);
    function claimFor(address member) external returns (uint256 id);
    function _claim(address member) internal returns (uint256 id);
}
```

This task does **not** override `tokenURI`; OZ's inherited one stands until **Task 8** (the renderer-wiring task) replaces it. Task 8 builds `CardData` from `sealedOf` when the token is sealed and from the live game otherwise, with `grace = hour < graceHours` and `status` 0/1/2.

---

- [ ] **Step 1: Write the constructor test.** From `/Library/Vibes/list-record`, create `test/Claim.t.sol`. Everything is seeded from Task 2's fixture, so this file contains no wallet literal. The second `ListRecord`, deployed against a 2-hour-grace mock, is the part that matters: it is what makes a hardcoded `24` fail.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {MockList} from "./mocks/MockList.sol";

contract ClaimTest is Test {
    using stdJson for string;

    MockList internal list;
    ListRecord internal record;

    address internal rank1;
    address internal rank4;
    uint256 internal gameGraceHours;

    address internal constant RENDERER = address(0xBEEF);

    event Claimed(address indexed member, uint256 indexed id, uint32 hour);

    function setUp() public {
        string memory j = vm.readFile("test/fixtures/wallets.json");
        gameGraceHours = j.readUint(".graceHours");
        rank1 = j.readAddress(".wallets.apex.address");
        rank4 = j.readAddress(".wallets.second.address");

        list = new MockList();
        _seed(j, ".wallets.apex", rank1);
        _seed(j, ".wallets.second", rank4);
        record = new ListRecord(address(list), RENDERER);
    }

    function _seed(string memory j, string memory row, address account) internal {
        list.setMember(
            account,
            j.readUint(string.concat(row, ".hour")),
            j.readUint(string.concat(row, ".points")),
            vm.parseUint(j.readString(string.concat(row, ".weightWei"))),
            vm.parseUint(j.readString(string.concat(row, ".creditWei"))),
            j.readUint(string.concat(row, ".deposits"))
        );
    }

    function test_constructor_reads_grace_hours_from_the_game() public {
        assertEq(record.graceHours(), gameGraceHours, "graceHours");
        assertEq(address(record.LIST()), address(list), "LIST");
        assertEq(address(record.renderer()), RENDERER, "renderer");
        assertEq(record.name(), "THE LIST", "name");
        assertEq(record.symbol(), "LIST", "symbol");

        MockList other = new MockList();
        other.setHourParams(7200, 3600);
        assertEq(new ListRecord(address(other), RENDERER).graceHours(), 2, "graceHours is read, not remembered");
    }
}
```

`RENDERER` is `address(0xBEEF)`, not a 40-hex-digit literal, so solc's EIP-55 check does not apply to it and it needs no checksumming. It is never called: `tokenURI` is not overridden until Task 8.

**Address checksums.** No address literal appears in Tasks 3–5, but the fixture's addresses must be EIP-55 correct because Task 7's renderer prints them and later tasks may paste one into a `.sol` file, where solc rejects a bad checksum outright. Produce every one with `cast`, and paste its output verbatim:

```bash
cast to-check-sum-address 0x75d51517b90cc5c8873c631ddc177a1bfd96b074
```

```
0x75D51517b90Cc5C8873C631DDC177a1bfD96b074
```

- [ ] **Step 2: Run it and watch it fail because the contract does not exist yet.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_constructor_reads_grace_hours_from_the_game -vvv
```

Expect a parse failure, not an assertion failure:

```
Compiler run failed:
Error (6275): Source "src/ListRecord.sol" not found: File not found.
 --> test/Claim.t.sol:6:1:
Error: Compilation failed
```

- [ ] **Step 3: Create the contract with nothing but the constructor.** Write `src/ListRecord.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";

import {IWhitelistCurator} from "./interfaces/IWhitelistCurator.sol";
import {IListRecordRenderer} from "./interfaces/IListRecordRenderer.sol";

/// @notice A permanent, permissionless record of one wallet's participation in THE LIST.
/// @dev No owner, no admin function, no pause, no mint price, no withdraw.
contract ListRecord is ERC721 {
    IWhitelistCurator public immutable LIST;
    // forge-lint: disable-next-line(screaming-snake-case-immutable)
    IListRecordRenderer public immutable renderer;
    /// @dev = LIST.gracePeriod() / LIST.hourDuration(), read at construction. Never a remembered 24.
    // forge-lint: disable-next-line(screaming-snake-case-immutable)
    uint256 public immutable graceHours;

    constructor(address list_, address renderer_) ERC721("THE LIST", "LIST") {
        LIST = IWhitelistCurator(list_);
        renderer = IListRecordRenderer(renderer_);
        graceHours = IWhitelistCurator(list_).gracePeriod() / IWhitelistCurator(list_).hourDuration();
    }
}
```

The two `forge-lint` comments are not decoration and they are the only two this contract needs: `renderer` and `graceHours` are `immutable` in lower camel case, which trips forge's `screaming-snake-case-immutable` note. Their names are fixed by the frozen contract, so the note is suppressed exactly where it is raised. Do not add speculative `unsafe-typecast` suppressions elsewhere — forge-lint flags only one cast in the finished contract (Task 4 Step 21) and a dead pragma reads as load-bearing to the next reviewer.

- [ ] **Step 4: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_constructor_reads_grace_hours_from_the_game -vvv
```

```
[PASS] test_constructor_reads_grace_hours_from_the_game()
Suite result: ok. 1 passed; 0 failed; 0 skipped
```

- [ ] **Step 5: Commit — before mutating, so the restore is exact.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "feat(record): ListRecord constructor reads graceHours from the game"
```

- [ ] **Step 6: Prove the test bites.** In `src/ListRecord.sol`, replace the `graceHours = ...` line with `graceHours = 24;` — the mistake this test exists to catch. Re-run Step 4's command:

```
[FAIL: graceHours is read, not remembered: 24 != 2] test_constructor_reads_grace_hours_from_the_game()
```

Restore and confirm green:

```bash
cd /Library/Vibes/list-record && git checkout -- src/ListRecord.sol
forge test --match-test test_constructor_reads_grace_hours_from_the_game
```

- [ ] **Step 7: Write the happy-path claim test.** Append inside `contract ClaimTest` in `test/Claim.t.sol`:

```solidity
    function test_a_member_claims_id_one_and_the_claim_is_recorded() public {
        (uint256 joinHour,) = list.firstHourOf(rank1);
        assertTrue(joinHour != 41, "the two hours must differ or this test proves nothing");
        list.setCurrentHour(41);
        assertEq(record.tokenOf(rank1), 0, "tokenOf before");

        vm.expectEmit(true, true, true, true, address(record));
        emit Claimed(rank1, 1, 41);
        vm.prank(rank1);
        uint256 id = record.claim();

        assertEq(id, 1, "id");
        assertEq(record.totalClaimed(), 1, "totalClaimed");
        assertEq(record.ownerOf(1), rank1, "ownerOf");
        assertEq(record.tokenOf(rank1), 1, "tokenOf after");
        assertEq(record.claimantOf(1), rank1, "claimantOf");
        assertEq(record.claimedAtHour(1), 41, "claimedAtHour");
    }
```

Two hours are in play and they must not be confusable, so the test asserts up front that the fixture's join hour is not 41 before setting the *game* hour to 41. If Task 2 ever seeds an apex row at hour 41 this test says so rather than silently passing for the wrong reason.

- [ ] **Step 8: Run it and watch it fail on the missing surface.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_member_claims_id_one_and_the_claim_is_recorded -vvv
```

```
Error (9582): Member "tokenOf" not found or not visible after argument-dependent lookup in contract ListRecord.
  --> test/Claim.t.sol:62:18
Error: Compilation failed
```

- [ ] **Step 9: Add the storage, the event and the minimal claim path.** In `src/ListRecord.sol`, insert after the `graceHours` declaration (before the `constructor`):

```solidity

    /// @notice Last minted id. Ids are sequential from 1, so an id IS its claim order.
    uint256 public totalClaimed;
    /// @notice 0 while unclaimed. Its non-zero value is also the double-claim guard.
    mapping(address => uint256) public tokenOf;
    /// @notice The wallet that claimed the token. Never changes, even when the token is sold.
    mapping(uint256 => address) public claimantOf;
    /// @notice The GAME hour at which the token was claimed. Not the claimant's join hour.
    mapping(uint256 => uint32) public claimedAtHour;

    event Claimed(address indexed member, uint256 indexed id, uint32 hour);
```

and append after the constructor, inside the contract:

```solidity

    function claim() external returns (uint256 id) {
        return _claim(msg.sender);
    }

    function _claim(address member) internal returns (uint256 id) {
        unchecked {
            id = ++totalClaimed;
        }
        uint32 hour = uint32(LIST.currentHour());

        tokenOf[member] = id;
        claimantOf[id] = member;
        claimedAtHour[id] = hour;

        emit Claimed(member, id, hour);
        _mint(member, id);
    }
```

Two notes. `_mint`, not `_safeMint`: this contract has no owner and no rescue path, so it must never be able to refuse a member. A contract wallet that cannot handle an ERC-721 receive hook would be permanently unable to claim under `_safeMint`, and that failure is unfixable here. State is written *before* the mint regardless, so nothing re-enters into a second claim. And `unchecked` is safe because `totalClaimed` cannot reach 2²⁵⁶ in a mapping-guarded, one-per-wallet mint.

- [ ] **Step 10: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_member_claims_id_one_and_the_claim_is_recorded -vvv
```

```
[PASS] test_a_member_claims_id_one_and_the_claim_is_recorded()
Suite result: ok. 1 passed; 0 failed; 0 skipped
```

- [ ] **Step 11: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "feat(record): claim() mints id 1 and records claimant and claim hour"
```

- [ ] **Step 12: Prove the test bites.** Change `claimedAtHour[id] = hour;` to `claimedAtHour[id] = 0;` and re-run Step 10's command:

```
[FAIL: claimedAtHour: 0 != 41] test_a_member_claims_id_one_and_the_claim_is_recorded()
```

Then `cd /Library/Vibes/list-record && git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 13: Write the claim-order test.** Append inside `contract ClaimTest`:

```solidity
    function test_ids_are_sequential_in_claim_order() public {
        vm.prank(rank1);
        assertEq(record.claim(), 1, "first");
        vm.prank(rank4);
        assertEq(record.claim(), 2, "second");
        assertEq(record.totalClaimed(), 2, "totalClaimed");
    }
```

The token id **is** the claim order — the one scarcity dimension in this collection that cannot be acquired later — so it gets its own pin.

- [ ] **Step 14: Run it — it passes immediately, and that is expected.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_ids_are_sequential_in_claim_order -vvv
```

```
[PASS] test_ids_are_sequential_in_claim_order()
```

Step 9's `++totalClaimed` already gives this behaviour. This test is a regression pin over code that already works, so Step 16 is what establishes that it is worth having.

- [ ] **Step 15: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/Claim.t.sol
git commit -m "test(record): pin token ids to claim order starting at 1"
```

- [ ] **Step 16: Prove the test bites.** Change `id = ++totalClaimed;` to `id = totalClaimed++;` (0-based ids — the classic off-by-one) and re-run Step 14's command:

```
[FAIL: first: 0 != 1] test_ids_are_sequential_in_claim_order()
```

Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 17: Write the double-claim test.** Append inside `contract ClaimTest`:

```solidity
    function test_a_second_claim_from_the_same_wallet_reverts() public {
        vm.prank(rank1);
        record.claim();
        vm.expectRevert(ListRecord.AlreadyClaimed.selector);
        vm.prank(rank1);
        record.claim();
    }
```

- [ ] **Step 18: Run it and watch it fail — the error type does not exist yet, so this is a compile failure, not an assertion.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_second_claim_from_the_same_wallet_reverts -vvv
```

```
Error (9582): Member "AlreadyClaimed" not found or not visible after argument-dependent lookup in type(contract ListRecord).
Error: Compilation failed
```

- [ ] **Step 19: Add the `AlreadyClaimed` guard.** In `src/ListRecord.sol`, add the error above the `event Claimed` line:

```solidity
    error AlreadyClaimed();

```

and add the guard as the first statement of `_claim`, immediately above the `unchecked` block:

```solidity
        if (tokenOf[member] != 0) revert AlreadyClaimed();

```

The guard costs no extra storage: `tokenOf` is a public lookup worth having anyway, and its non-zero value *is* the guard.

- [ ] **Step 20: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_second_claim_from_the_same_wallet_reverts -vvv
```

```
[PASS] test_a_second_claim_from_the_same_wallet_reverts()
```

- [ ] **Step 21: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "feat(record): one token per wallet, guarded by tokenOf"
```

- [ ] **Step 22: Prove the test bites.** Delete the line `if (tokenOf[member] != 0) revert AlreadyClaimed();` and re-run Step 20's command:

```
[FAIL: next call did not revert as expected] test_a_second_claim_from_the_same_wallet_reverts()
```

Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 23: Write the non-member test — the most valuable test in this suite.** Append inside `contract ClaimTest`:

```solidity
    function test_a_non_member_cannot_claim_and_does_not_read_as_hour_zero() public {
        address stranger = makeAddr("stranger");
        (uint256 hour, bool hasJoined) = list.firstHourOf(stranger);
        assertEq(hour, 0, "raw hour word is zero");
        assertFalse(hasJoined, "hasJoined");

        vm.expectRevert(ListRecord.NotAMember.selector);
        vm.prank(stranger);
        record.claim();

        assertEq(record.tokenOf(stranger), 0, "tokenOf");
        assertEq(record.totalClaimed(), 0, "totalClaimed");
    }
```

The first two assertions are the whole point: they establish that a stranger's hour word really is `0`, identical to a founder's, so the only thing separating the two is `hasJoined`. A `claim` that reads the hour instead of the flag would mint founder records to the entire internet.

- [ ] **Step 24: Run it and watch it fail — again a compile failure, because `NotAMember` does not exist.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_non_member_cannot_claim_and_does_not_read_as_hour_zero -vvv
```

```
Error (9582): Member "NotAMember" not found or not visible after argument-dependent lookup in type(contract ListRecord).
Error: Compilation failed
```

- [ ] **Step 25: Add the `NotAMember` guard.** In `src/ListRecord.sol`, add the error above `error AlreadyClaimed();`:

```solidity
    error NotAMember();
```

and make the first two statements of `_claim` read:

```solidity
        (, bool hasJoined) = LIST.firstHourOf(member);
        if (!hasJoined) revert NotAMember();
```

so the full head of `_claim` is now:

```solidity
    function _claim(address member) internal returns (uint256 id) {
        (, bool hasJoined) = LIST.firstHourOf(member);
        if (!hasJoined) revert NotAMember();
        if (tokenOf[member] != 0) revert AlreadyClaimed();
```

Note the discarded first return value. The hour word is deliberately **not** bound to a name here: nothing in `claim` may use it.

- [ ] **Step 26: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_a_non_member_cannot_claim_and_does_not_read_as_hour_zero -vvv
```

```
[PASS] test_a_non_member_cannot_claim_and_does_not_read_as_hour_zero()
```

- [ ] **Step 27: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "feat(record): membership comes from hasJoined, never from the hour word"
```

- [ ] **Step 28: Prove the test bites.** Delete the line `if (!hasJoined) revert NotAMember();` and re-run Step 26's command. solc also warns about the now-unused variable, which is expected and is part of the evidence:

```
Compiler run successful with warnings:
Warning (2072): Unused local variable.
[FAIL: next call did not revert as expected] test_a_non_member_cannot_claim_and_does_not_read_as_hour_zero()
```

Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 29: Write the `claimFor` tests.** Append inside `contract ClaimTest`:

```solidity
    function test_claim_for_mints_to_the_member_never_to_the_caller() public {
        address sponsor = makeAddr("sponsor");
        vm.prank(sponsor);
        uint256 id = record.claimFor(rank1);

        assertEq(record.ownerOf(id), rank1, "ownerOf");
        assertEq(record.claimantOf(id), rank1, "claimantOf");
        assertEq(record.tokenOf(rank1), id, "tokenOf member");
        assertEq(record.tokenOf(sponsor), 0, "tokenOf sponsor");
        assertEq(record.balanceOf(sponsor), 0, "balanceOf sponsor");
    }

    function test_claim_for_a_non_member_reverts() public {
        address stranger = makeAddr("stranger");
        vm.expectRevert(ListRecord.NotAMember.selector);
        record.claimFor(stranger);
    }
```

`claimFor` exists so a third party can pay the gas for a member who cannot. The last two assertions are the security property: the sponsor gets **nothing**, so there is no way to redirect somebody else's record.

- [ ] **Step 30: Run them and watch them fail because `claimFor` does not exist.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_claim_for -vvv
```

```
Error (9582): Member "claimFor" not found or not visible after argument-dependent lookup in contract ListRecord.
Error: Compilation failed
```

- [ ] **Step 31: Add `claimFor`.** In `src/ListRecord.sol`, insert between `claim()` and `_claim(...)`:

```solidity

    function claimFor(address member) external returns (uint256 id) {
        return _claim(member);
    }
```

- [ ] **Step 32: Run them and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_claim_for -vvv
```

```
[PASS] test_claim_for_a_non_member_reverts()
[PASS] test_claim_for_mints_to_the_member_never_to_the_caller()
Suite result: ok. 2 passed; 0 failed; 0 skipped
```

- [ ] **Step 33: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "feat(record): claimFor mints to the named member, never to the caller"
```

- [ ] **Step 34: Prove the redirect test bites.** In `_claim`, change `_mint(member, id);` to `_mint(msg.sender, id);` — the bug where a sponsor keeps the token. Re-run Step 32's command:

```
[FAIL: ownerOf: 0xeB42Ea4654c82B0dd20E908457099A7ed41deDa6 != 0x75D51517b90Cc5C8873C631DDC177a1bfD96b074] test_claim_for_mints_to_the_member_never_to_the_caller()
```

The left address is `makeAddr("sponsor")` and is fixed; the right one is whatever `.wallets.apex.address` holds in Task 2's fixture, so expect that value rather than this exact one if Task 2 chose a different real row. Note that `test_a_member_claims_id_one_and_the_claim_is_recorded` stays green under this mutation, because there `msg.sender == member` — which is exactly why `claimFor` needs its own test. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 35: Run formatting, the linter and the whole suite.**

```bash
cd /Library/Vibes/list-record && forge fmt && forge fmt --check && forge build --force && forge test
```

`forge fmt --check` must print nothing and `forge build` must print `Compiler run successful!`. The suite total is **14 tests**: `test/Interface.t.sol` 7 (Tasks 1–2) + `test/Claim.t.sol` 7 (this task). The last line reads:

```
Ran 2 test suites: 14 tests passed, 0 failed, 0 skipped (14 total tests)
```

Then prove the build is clean where it matters — no warning anywhere, and no lint note located in `src/`:

```bash
cd /Library/Vibes/list-record
forge build --force 2>&1 | grep -E "^warning\[|[[:space:]]+--> src/"; echo "exit=$?"
```

Expect no output and `exit=1`. (The build does print `note[unsafe-cheatcode]` for each `vm.readFile` in the test files and `note[named-struct-fields]` for `MockList`; both are located under `test/`, both are Task 2's or forge-std's business, and neither is yours to silence.) If `forge fmt` rewrote anything, commit it:

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Claim.t.sol
git commit -m "style(record): forge fmt"
```

---

### Task 4: `sealRecord` — freezing the numbers into the token

Until the game settles, a token's metadata is read **live** from the game contract, so a wallet that keeps depositing sees its own record improve. `isSettled()` on the game is derived and monotonic: the instant a completed judged hour comes up short it returns true for ever, and every per-wallet view is frozen by the chain itself from then on.

`sealRecord` is the holder's one-time ritual after that: it copies the final points, weight, credit, deposit count and join hour into the token's **own** storage. After it, the token no longer depends on the game contract being readable at all. It is holder-only by choice — a token whose wallet is lost simply stays unsealed, which is honest.

Two hours are in play and they are different values. `claimedAtHour[id]` (Task 3) is the *game's* hour when the token was minted. `SealedRecord.hour` is the *claimant's join* hour, from `firstHourOf` — the cohort they belong to. Do not cross them.

The mutation-restore rule from Task 3's preamble applies here unchanged: commit first, mutate, then `git checkout -- <path>`.

**Files**

- Modify: `/Library/Vibes/list-record/src/ListRecord.sol`
- Create (test): `/Library/Vibes/list-record/test/Seal.t.sol`
- Read only: `/Library/Vibes/list-record/test/fixtures/wallets.json` (**Task 2 owns and creates it — this task does not write it**), `/Library/Vibes/list-record/test/mocks/MockList.sol`, `/Library/Vibes/list-record/src/interfaces/IWhitelistCurator.sol`

**Interfaces**

*Consumes — from Task 3 (`src/ListRecord.sol`):* `LIST` (an `IWhitelistCurator`), `graceHours`, `totalClaimed`, `tokenOf`, `claimantOf`, `claimedAtHour`, `claim()`, `claimFor(address)`, `_claim(address)`, `error NotAMember()`, `error AlreadyClaimed()`, `event Claimed(address indexed, uint256 indexed, uint32)`. The contract currently declares `contract ListRecord is ERC721` and has no `tokenURI` override.

*Consumes — from Task 1:* `IWhitelistCurator` (full signature list in Task 3's Interfaces block); `fs_permissions` including `{access = "read", path = "./test/fixtures"}` in `foundry.toml`, without which `vm.readFile` reverts.

*Consumes — from Task 2:* `MockList` with `setMember(address,uint256,uint256,uint256,uint256,uint256)`, `setSettled(bool)`, `setCurrentHour(uint256)`, `setHourParams(uint256,uint256)`. There is no `setGrace`.

*Consumes — from Task 2 (`test/fixtures/wallets.json`).* This task reads `.wallets.apex.*` (a real captured member: `address`, `hour`, `points`, `weightWei` and `creditWei` as decimal strings, `deposits`) and `.wallets.ceiling.*` (the synthetic structural-maximum row: `hour`, `points`, `weightWei`, `creditWei`, `deposits` — no address, because inventing one would be dishonest and attaching envelope numbers to a real wallet is forbidden). **The `ceiling` row must satisfy these bounds or Step 33's and Step 34's downcast mutations cannot bite**, and Step 2's first test asserts them so a weak fixture fails loudly:

| path | required |
|---|---|
| `.wallets.ceiling.weightWei` | `> type(uint64).max` (1.8447e19) |
| `.wallets.ceiling.creditWei` | `> type(uint64).max` |
| `.wallets.ceiling.deposits` | `> type(uint16).max` (65 535) |
| `.wallets.ceiling.hour` | `> 0` |
| `.wallets.ceiling.points` | `<= type(uint32).max` |

Note what is *not* required: `points` above `type(uint16).max`. The game's curve tops out at 44 721 points, which needs 16 bits, so `uint32` in `SealedRecord` is deliberate headroom and no narrowing mutation short of `uint8` could bite. Points are proven by value instead (Steps 25 and 29), not by width. This asymmetry is why the ceiling assertion for points is `assertLe`, not `assertGt`.

*Consumes — from OpenZeppelin v5.x:* `ERC721._ownerOf(uint256) internal view returns (address)` — returns `address(0)` for a token that does not exist, and unlike `ownerOf` it does not revert. `IERC4906` at `@openzeppelin/contracts/interfaces/IERC4906.sol`, which declares only two events, `MetadataUpdate(uint256)` and `BatchMetadataUpdate(uint256,uint256)`, and inherits `IERC165` and `IERC721`.

*Produces — for Task 5 and Task 8:*

```solidity
struct SealedRecord {                 // exactly 2 storage slots
    uint32 points; uint96 weightWei; uint96 creditWei;   // slot 0: 32+96+96+32
    uint32 deposits; uint32 hour; uint64 sealedAt;       // slot 1: 32+64; sealedAt == 0 means not sealed
}
mapping(uint256 => SealedRecord) public sealedOf;
function sealRecord(uint256 id) external;
function isSealed(uint256 id) external view returns (bool);
error NotSettled();
error NotHolder();
error AlreadySealed();
error NonexistentToken();
event RecordSealed(uint256 indexed id, uint32 points);
```

plus `contract ListRecord is IERC4906, ERC721`, which is what makes `emit MetadataUpdate(id)` legal and what lets Task 5 write `override(ERC721, IERC165)`.

---

- [ ] **Step 1: Verify Task 2's fixture carries every key this task reads, before writing any Solidity.** This task creates no fixture. Run the shape check:

```bash
cd /Library/Vibes/list-record && python3 - <<'PY'
import json
d = json.load(open("test/fixtures/wallets.json"))
assert "_provenance" in d, "missing _provenance block"
w = d["wallets"]
for k in ["address", "hour", "points", "weightWei", "creditWei", "deposits"]:
    assert k in w["apex"], f"missing wallets.apex.{k}"
for k in ["hour", "points", "weightWei", "creditWei", "deposits"]:
    assert k in w["ceiling"], f"missing wallets.ceiling.{k}"
assert int(w["ceiling"]["weightWei"]) > 2**64 - 1, "ceiling weight cannot bite a uint64 downcast"
assert int(w["ceiling"]["creditWei"]) > 2**64 - 1, "ceiling credit cannot bite a uint64 downcast"
assert int(w["ceiling"]["deposits"]) > 2**16 - 1, "ceiling deposits cannot bite a uint16 downcast"
assert int(w["ceiling"]["hour"]) > 0, "ceiling hour is zero"
assert int(w["ceiling"]["points"]) <= 2**32 - 1, "ceiling points do not fit uint32"
print("wallets.json carries every key Seal.t.sol reads")
PY
```

```
wallets.json carries every key Seal.t.sol reads
```

If it raises, stop and report the exact assertion to whoever owns Task 2 rather than editing their file — that is this repo's rule about other agents' files, and the fixture's provenance block is the reason it must stay one owner's.

- [ ] **Step 2: Write the test file with the fixture-shape, pre-settlement, non-holder and nonexistent-token cases.** Create `test/Seal.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {MockList} from "./mocks/MockList.sol";

contract SealTest is Test {
    using stdJson for string;

    MockList internal list;
    ListRecord internal record;

    address internal apex;
    uint256 internal apexHour;
    uint256 internal apexPoints;
    uint256 internal apexWeightWei;
    uint256 internal apexCreditWei;
    uint256 internal apexDeposits;

    address internal constant RENDERER = address(0xBEEF);

    event RecordSealed(uint256 indexed id, uint32 points);
    event MetadataUpdate(uint256 _tokenId);

    function setUp() public {
        string memory j = vm.readFile("test/fixtures/wallets.json");
        apex = j.readAddress(".wallets.apex.address");
        apexHour = j.readUint(".wallets.apex.hour");
        apexPoints = j.readUint(".wallets.apex.points");
        apexWeightWei = vm.parseUint(j.readString(".wallets.apex.weightWei"));
        apexCreditWei = vm.parseUint(j.readString(".wallets.apex.creditWei"));
        apexDeposits = j.readUint(".wallets.apex.deposits");

        list = new MockList();
        list.setMember(apex, apexHour, apexPoints, apexWeightWei, apexCreditWei, apexDeposits);
        record = new ListRecord(address(list), RENDERER);
        vm.prank(apex);
        record.claim();
    }

    function test_the_fixture_is_shaped_so_that_these_tests_can_bite() public view {
        string memory j = vm.readFile("test/fixtures/wallets.json");
        assertTrue(vm.keyExists(j, "._provenance"), "_provenance block");
        assertTrue(apex != address(0), "apex address");
        assertGt(apexPoints, 0, "apex points");
        assertGt(apexWeightWei, 0, "apex weight");
        assertGt(apexCreditWei, 0, "apex credit");
        assertGt(apexDeposits, 0, "apex deposits");

        assertGt(vm.parseUint(j.readString(".wallets.ceiling.weightWei")), uint256(type(uint64).max), "ceiling weight");
        assertGt(vm.parseUint(j.readString(".wallets.ceiling.creditWei")), uint256(type(uint64).max), "ceiling credit");
        assertGt(j.readUint(".wallets.ceiling.deposits"), uint256(type(uint16).max), "ceiling deposits");
        assertGt(j.readUint(".wallets.ceiling.hour"), 0, "ceiling hour");
        assertLe(j.readUint(".wallets.ceiling.points"), uint256(type(uint32).max), "ceiling points fit uint32");
    }

    function test_seal_reverts_before_settlement() public {
        vm.expectRevert(ListRecord.NotSettled.selector);
        vm.prank(apex);
        record.sealRecord(1);
    }

    function test_seal_reverts_for_a_non_holder() public {
        list.setSettled(true);
        address stranger = makeAddr("stranger");
        vm.expectRevert(ListRecord.NotHolder.selector);
        vm.prank(stranger);
        record.sealRecord(1);
    }

    function test_seal_reverts_for_a_token_that_does_not_exist() public {
        list.setSettled(true);
        vm.expectRevert(ListRecord.NonexistentToken.selector);
        record.sealRecord(99);
    }
}
```

`test_the_fixture_is_shaped_so_that_these_tests_can_bite` is the CI-side twin of Step 1: Step 1 catches a bad fixture before you write code, this test catches one that degrades later.

- [ ] **Step 3: Run them and watch them fail because the errors do not exist.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Seal.t.sol -vvv
```

```
Error (9582): Member "NotSettled" not found or not visible after argument-dependent lookup in type(contract ListRecord).
Error: Compilation failed
```

- [ ] **Step 4: Add the errors, the struct, the mapping and the guard-only `sealRecord`.** In `src/ListRecord.sol`, first add the import under the existing `ERC721` import:

```solidity
import {IERC4906} from "@openzeppelin/contracts/interfaces/IERC4906.sol";
```

change the contract line to:

```solidity
contract ListRecord is IERC4906, ERC721 {
```

add after the `claimedAtHour` mapping:

```solidity
    /// @notice The frozen copy, written once by `sealRecord`. `sealedAt == 0` means not sealed.
    mapping(uint256 => SealedRecord) public sealedOf;
```

add the struct immediately above `error NotAMember();`:

```solidity
    /// @dev Two storage slots: 32+96+96+32 bits, then 32+64.
    struct SealedRecord {
        uint32 points;
        uint96 weightWei;
        uint96 creditWei;
        uint32 deposits;
        uint32 hour;
        uint64 sealedAt;
    }

```

extend the error list so it reads:

```solidity
    error NotAMember();
    error AlreadyClaimed();
    error NotSettled();
    error NotHolder();
    error AlreadySealed();
    error NonexistentToken();
```

and append this function at the end of the contract, after `_claim`:

```solidity

    function sealRecord(uint256 id) external {
        address holder = _ownerOf(id);
        if (holder == address(0)) revert NonexistentToken();
        if (!LIST.isSettled()) revert NotSettled();
        if (msg.sender != holder) revert NotHolder();
        if (sealedOf[id].sealedAt != 0) revert AlreadySealed();
    }
```

Inheriting `IERC4906` alongside `ERC721` compiles without any further override — `ERC721` already implements every function `IERC4906` inherits. The guard order is existence → settled → holder → already-sealed: `NonexistentToken` **must** come first, because `_ownerOf` returning `address(0)` would otherwise fall through to the holder check and report `NotHolder` for a token that never existed. Step 8 proves exactly that.

- [ ] **Step 5: Run them and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Seal.t.sol -vvv
```

```
[PASS] test_seal_reverts_before_settlement()
[PASS] test_seal_reverts_for_a_non_holder()
[PASS] test_seal_reverts_for_a_token_that_does_not_exist()
[PASS] test_the_fixture_is_shaped_so_that_these_tests_can_bite()
Suite result: ok. 4 passed; 0 failed; 0 skipped
```

- [ ] **Step 6: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Seal.t.sol
git commit -m "feat(record): sealRecord guards - settled, holder-only, once, token must exist"
```

- [ ] **Step 7: Prove `test_seal_reverts_before_settlement` bites.** Delete the line `if (!LIST.isSettled()) revert NotSettled();` from `sealRecord` and re-run Step 5's command:

```
[FAIL: next call did not revert as expected] test_seal_reverts_before_settlement()
Suite result: FAILED. 3 passed; 1 failed; 0 skipped
```

Then `cd /Library/Vibes/list-record && git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 8: Prove `test_seal_reverts_for_a_token_that_does_not_exist` bites — and that guard *order* is what makes it work.** Delete only the line `if (holder == address(0)) revert NonexistentToken();`, keeping `address holder = _ownerOf(id);`. Re-run Step 5's command:

```
[FAIL: Error != expected error: NotHolder() != NonexistentToken()] test_seal_reverts_for_a_token_that_does_not_exist()
Suite result: FAILED. 3 passed; 1 failed; 0 skipped
```

That message is the evidence: without the existence check the call still reverts, so a laxer test would have passed while reporting the wrong reason to every caller. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 9: Write the test that the *claimant* cannot seal a token they sold.** This is the case a naive implementation gets wrong, because "the claimant" and "the holder" are the same address right up until the token trades. Append inside `contract SealTest`:

```solidity
    function test_seal_reverts_for_the_claimant_after_they_transferred_it_away() public {
        list.setSettled(true);
        address buyer = makeAddr("buyer");
        vm.prank(apex);
        record.transferFrom(apex, buyer, 1);

        assertEq(record.claimantOf(1), apex, "claimant unchanged");
        assertEq(record.ownerOf(1), buyer, "holder is the buyer");

        vm.expectRevert(ListRecord.NotHolder.selector);
        vm.prank(apex);
        record.sealRecord(1);

        vm.prank(buyer);
        record.sealRecord(1);
        assertTrue(record.isSealed(1), "buyer can seal");
    }
```

- [ ] **Step 10: Run it and watch it fail because `isSealed` does not exist.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_seal_reverts_for_the_claimant_after_they_transferred_it_away -vvv
```

```
Error (9582): Member "isSealed" not found or not visible after argument-dependent lookup in contract ListRecord.
Error: Compilation failed
```

- [ ] **Step 11: Add the `sealedAt` write and `isSealed`.** In `src/ListRecord.sol`, extend `sealRecord` so the guards are followed by a minimal write, and add `isSealed` after it:

```solidity
    function sealRecord(uint256 id) external {
        address holder = _ownerOf(id);
        if (holder == address(0)) revert NonexistentToken();
        if (!LIST.isSettled()) revert NotSettled();
        if (msg.sender != holder) revert NotHolder();
        if (sealedOf[id].sealedAt != 0) revert AlreadySealed();

        sealedOf[id].sealedAt = uint64(block.timestamp);
    }

    function isSealed(uint256 id) external view returns (bool) {
        return sealedOf[id].sealedAt != 0;
    }
```

- [ ] **Step 12: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_seal_reverts_for_the_claimant_after_they_transferred_it_away -vvv
```

```
[PASS] test_seal_reverts_for_the_claimant_after_they_transferred_it_away()
```

- [ ] **Step 13: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Seal.t.sol
git commit -m "feat(record): sealing is holder-only, so a sold token seals for its buyer"
```

- [ ] **Step 14: Prove the test bites.** Change `if (msg.sender != holder) revert NotHolder();` to `if (msg.sender != claimantOf[id]) revert NotHolder();` — holder-only misread as claimant-only. Re-run the whole file:

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Seal.t.sol -vvv
```

```
[PASS] test_seal_reverts_before_settlement()
[PASS] test_seal_reverts_for_a_non_holder()
[FAIL: next call did not revert as expected] test_seal_reverts_for_the_claimant_after_they_transferred_it_away()
```

`test_seal_reverts_for_a_non_holder` stays green under this mutation, which is precisely why the transferred-away case needs its own test. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 15: Write the second-seal test.** Append inside `contract SealTest`:

```solidity
    function test_seal_reverts_the_second_time() public {
        list.setSettled(true);
        vm.prank(apex);
        record.sealRecord(1);
        vm.expectRevert(ListRecord.AlreadySealed.selector);
        vm.prank(apex);
        record.sealRecord(1);
    }
```

- [ ] **Step 16: Run it and watch it pass — the guard from Step 4 and the write from Step 11 already close this.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_seal_reverts_the_second_time -vvv
```

```
[PASS] test_seal_reverts_the_second_time()
```

- [ ] **Step 17: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/Seal.t.sol
git commit -m "test(record): sealing is once and only once"
```

- [ ] **Step 18: Prove the test bites, twice, because two separate lines make it work.** First delete `if (sealedOf[id].sealedAt != 0) revert AlreadySealed();` and re-run Step 16's command:

```
[FAIL: next call did not revert as expected] test_seal_reverts_the_second_time()
```

`git checkout -- src/ListRecord.sol`. Then change `sealedOf[id].sealedAt = uint64(block.timestamp);` to `sealedOf[id].sealedAt = 0;` and re-run:

```
[FAIL: next call did not revert as expected] test_seal_reverts_the_second_time()
```

`sealedAt == 0` means "not sealed", so never writing it is the same bug as never checking it. `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 19: Write the copy-and-emit test.** Append inside `contract SealTest`:

```solidity
    function test_seal_copies_the_values_and_emits() public {
        list.setSettled(true);
        vm.warp(1_760_000_000);

        vm.expectEmit(true, true, true, true, address(record));
        // forge-lint: disable-next-line(unsafe-typecast)
        emit RecordSealed(1, uint32(apexPoints));
        vm.expectEmit(true, true, true, true, address(record));
        emit MetadataUpdate(1);
        vm.prank(apex);
        record.sealRecord(1);

        (uint32 points, uint96 weightWei, uint96 creditWei, uint32 deposits, uint32 hour, uint64 sealedAt) =
            record.sealedOf(1);
        assertEq(uint256(points), apexPoints, "points");
        assertEq(uint256(weightWei), apexWeightWei, "weight");
        assertEq(uint256(creditWei), apexCreditWei, "credit");
        assertEq(uint256(deposits), apexDeposits, "deposits");
        assertEq(uint256(hour), apexHour, "join hour");
        assertEq(uint256(sealedAt), 1_760_000_000, "sealedAt");
        assertTrue(record.isSealed(1), "isSealed");
    }
```

`MetadataUpdate` is the ERC-4906 event: it is how a marketplace learns to re-read a token whose metadata just changed. Without it a sealed card would keep showing its live art on every listing page until something else evicted the cache. The one lint suppression is required — `uint32(apexPoints)` narrows a `uint256` state variable and forge-lint flags exactly that shape.

- [ ] **Step 20: Run it and watch it fail on the missing emit.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_seal_copies_the_values_and_emits -vvv
```

```
[FAIL: log != expected log] test_seal_copies_the_values_and_emits()
```

- [ ] **Step 21: Copy the values.** In `src/ListRecord.sol`, add the event beneath `event Claimed(...)`:

```solidity
    event RecordSealed(uint256 indexed id, uint32 points);
```

then replace the body of `sealRecord` (keeping the four guards exactly as they are) with:

```solidity
    function sealRecord(uint256 id) external {
        address holder = _ownerOf(id);
        if (holder == address(0)) revert NonexistentToken();
        if (!LIST.isSettled()) revert NotSettled();
        if (msg.sender != holder) revert NotHolder();
        if (sealedOf[id].sealedAt != 0) revert AlreadySealed();

        address member = claimantOf[id];
        (uint256 joinHour,) = LIST.firstHourOf(member);

        // Every downcast here is exact, because the game's own storage is already this narrow:
        // `weight` and `highWater` are uint96 in WhitelistCurator, `txCount` and `firstHour` are
        // uint32, and points is sqrt(weight) * 1000 / 1e9, which is <= 281474 for any uint96
        // weight. The frozen error list has no truncation error precisely because none is
        // reachable; `test_the_games_ceiling_values_survive_the_downcast` pins it.
        uint32 points = uint32(LIST.pointsOf(member));
        uint96 weightWei = uint96(LIST.weightOf(member));
        uint96 creditWei = uint96(LIST.contributedBy(member));
        uint32 deposits = uint32(LIST.txCountOf(member));
        // forge-lint: disable-next-line(unsafe-typecast)
        uint32 hour = uint32(joinHour);
        uint64 sealedAt = uint64(block.timestamp);

        sealedOf[id] = SealedRecord({
            points: points,
            weightWei: weightWei,
            creditWei: creditWei,
            deposits: deposits,
            hour: hour,
            sealedAt: sealedAt
        });

        emit RecordSealed(id, points);
        emit MetadataUpdate(id);
    }
```

Note `claimantOf[id]`, not `msg.sender`: the record describes the wallet that **played**, so a token sold to a stranger still seals the claimant's numbers. And `joinHour` here is the claimant's cohort hour from `firstHourOf` — not `claimedAtHour[id]`, which is a different value. Exactly one `unsafe-typecast` suppression is needed and it is on `uint32(joinHour)`: forge-lint flags a narrowing cast of a local variable, not of a call's return value, so the other five casts here raise nothing and must not carry a dead pragma.

- [ ] **Step 22: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_seal_copies_the_values_and_emits -vvv
```

```
[PASS] test_seal_copies_the_values_and_emits()
```

- [ ] **Step 23: Confirm the struct is exactly two slots.** A field-order change that silently costs every sealer an extra `SSTORE` fails no test, so measure it:

```bash
cd /Library/Vibes/list-record && forge inspect --json ListRecord storage | python3 -c "import json,sys; d=json.load(sys.stdin); print([v['numberOfBytes'] for t,v in d['types'].items() if 'SealedRecord' in t and 'mapping' not in t])"
```

```
['64']
```

64 bytes is two 32-byte slots, as designed. Anything above 64 means the packing broke. (Note the flag position: `forge inspect --json ListRecord storage`. `forge inspect ListRecord storage --json` is not accepted by forge 1.5.1 and prints a human table you cannot parse.)

- [ ] **Step 24: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Seal.t.sol
git commit -m "feat(record): sealRecord copies points, weight, credit, deposits and join hour"
```

- [ ] **Step 25: Prove the test bites.** Change `uint32 points = uint32(LIST.pointsOf(member));` to `uint32 points = 0;` and re-run Step 22's command:

```
[FAIL: MetadataUpdate != expected RecordSealed] test_seal_copies_the_values_and_emits()
```

The expected `RecordSealed(1, <apex points>)` no longer matches, so `expectEmit` reports the next log it saw instead. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 26: Write the test that justifies the whole feature — make the game lie, and watch the token not move.** Append inside `contract SealTest`:

```solidity
    function test_sealed_values_do_not_move_when_the_game_lies_afterwards() public {
        list.setSettled(true);
        vm.prank(apex);
        record.sealRecord(1);

        list.setMember(apex, apexHour + 23, 1, 1 ether, 1 ether, 1);

        (uint32 points, uint96 weightWei, uint96 creditWei, uint32 deposits, uint32 hour,) = record.sealedOf(1);
        assertEq(uint256(points), apexPoints, "points frozen");
        assertEq(uint256(weightWei), apexWeightWei, "weight frozen");
        assertEq(uint256(creditWei), apexCreditWei, "credit frozen");
        assertEq(uint256(deposits), apexDeposits, "deposits frozen");
        assertEq(uint256(hour), apexHour, "hour frozen");
    }
```

Every one of the five values changes in the mock after the seal — the join hour moves 23 hours and the points collapse to 1 — and none of them may reach the token. This is the whole promise of the collection: sealed means sealed, even against a game contract that later says something else.

- [ ] **Step 27: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_sealed_values_do_not_move_when_the_game_lies_afterwards -vvv
```

```
[PASS] test_sealed_values_do_not_move_when_the_game_lies_afterwards()
```

- [ ] **Step 28: Commit it on its own, because it is the load-bearing test of this task.**

```bash
cd /Library/Vibes/list-record
git add test/Seal.t.sol
git commit -m "test(record): a sealed token does not move when the game later says otherwise"
```

- [ ] **Step 29: Prove the test bites.** Change `uint32 points = uint32(LIST.pointsOf(member));` to `uint32 points = 0;` again and re-run Step 27's command:

```
[FAIL: points frozen: 0 != 30853] test_sealed_values_do_not_move_when_the_game_lies_afterwards()
```

The right-hand number is `.wallets.apex.points` from Task 2's fixture; expect whatever that row holds. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 30: Write the downcast-fidelity test.** `SealedRecord` narrows five `uint256` reads into `uint32`/`uint96`/`uint32`/`uint32`/`uint64`. Solidity truncates silently, so if any of those widths were wrong the token would carry a plausible, wrong number that nobody would ever notice. Append inside `contract SealTest`:

```solidity
    function test_the_games_ceiling_values_survive_the_downcast() public {
        string memory j = vm.readFile("test/fixtures/wallets.json");
        uint256 cHour = j.readUint(".wallets.ceiling.hour");
        uint256 cPoints = j.readUint(".wallets.ceiling.points");
        uint256 cWeight = vm.parseUint(j.readString(".wallets.ceiling.weightWei"));
        uint256 cCredit = vm.parseUint(j.readString(".wallets.ceiling.creditWei"));
        uint256 cDeposits = j.readUint(".wallets.ceiling.deposits");

        list.setMember(apex, cHour, cPoints, cWeight, cCredit, cDeposits);
        list.setSettled(true);
        vm.prank(apex);
        record.sealRecord(1);

        (uint32 points, uint96 weightWei, uint96 creditWei, uint32 deposits, uint32 hour,) = record.sealedOf(1);
        assertEq(uint256(points), cPoints, "points");
        assertEq(uint256(weightWei), cWeight, "weight");
        assertEq(uint256(creditWei), cCredit, "credit");
        assertEq(uint256(deposits), cDeposits, "deposits");
        assertEq(uint256(hour), cHour, "hour");
    }
```

The `ceiling` row is synthetic and labelled so in the fixture's `_provenance`: it carries the game's structural maxima (weight = 2 × `creditCap`, deposits = `type(uint32).max`), not any wallet's observed numbers, and it deliberately has no address for exactly that reason.

- [ ] **Step 31: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_the_games_ceiling_values_survive_the_downcast -vvv
```

```
[PASS] test_the_games_ceiling_values_survive_the_downcast()
```

- [ ] **Step 32: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/Seal.t.sol
git commit -m "test(record): the game's maximum values survive the SealedRecord downcast"
```

- [ ] **Step 33: Prove the test bites on the weight field.** In the `SealedRecord` struct change `uint96 weightWei;` to `uint64 weightWei;`, and in `sealRecord` change `uint96 weightWei = uint96(LIST.weightOf(member));` to `uint64 weightWei = uint64(LIST.weightOf(member));`. Re-run Step 31's command:

```
[FAIL: weight: 7751640039368425472 != 2000000000000000000000] test_the_games_ceiling_values_survive_the_downcast()
```

That number is exactly what silent truncation looks like: 7.75 ETH where 2 000 ETH belongs, with no revert and no warning. Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 34: Prove it bites on the deposit field too.** In the struct change `uint32 deposits;` to `uint16 deposits;`, and in `sealRecord` change `uint32 deposits = uint32(LIST.txCountOf(member));` to `uint16 deposits = uint16(LIST.txCountOf(member));`. Re-run Step 31's command:

```
[FAIL: deposits: 65535 != 4294967295] test_the_games_ceiling_values_survive_the_downcast()
```

Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 35: Run formatting, the linter and the whole suite.**

```bash
cd /Library/Vibes/list-record && forge fmt && forge fmt --check && forge build --force && forge test
```

`forge fmt --check` prints nothing and `forge build` prints `Compiler run successful!`. The suite total is **23 tests**: `test/Interface.t.sol` 7 (Tasks 1–2) + `test/Claim.t.sol` 7 (Task 3) + `test/Seal.t.sol` 9 (this task). The last line reads:

```
Ran 3 test suites: 23 tests passed, 0 failed, 0 skipped (23 total tests)
```

Then the build-cleanliness check:

```bash
cd /Library/Vibes/list-record
forge build --force 2>&1 | grep -E "^warning\[|[[:space:]]+--> src/"; echo "exit=$?"
```

Expect no output and `exit=1`. Commit any reformatting:

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Seal.t.sol
git commit -m "style(record): forge fmt"
```

---

### Task 5: `announceSettled`, `supportsInterface`, and ERC-4906 on transfer

Three loose ends, all about one problem: **marketplaces cache metadata.** A page showing a token's points is showing whatever it fetched last, which may be hours or weeks old. ERC-4906 is the standard's answer — two events a contract emits to say "re-read this token" (`MetadataUpdate`) or "re-read this range" (`BatchMetadataUpdate`) — and `supportsInterface(0x49064906)` is how an indexer discovers that the contract speaks it at all.

**Why `announceSettled` exists.** The single most important refresh in this collection's life is the moment the game freezes: every live token stops being a moving number and becomes a final one. In an ordinary collection the owner would fire `BatchMetadataUpdate` over the whole supply. **This collection has no owner** — that is a deliberate design decision (spec D7, §9.4), not an omission — so without `announceSettled` nothing could ever trigger that refresh. Making it permissionless costs nothing: it requires `isSettled()` (which the game derives on chain and which is monotonic — once true, true for ever), it runs exactly once, and it does nothing but emit. There is no state anyone could grief and no value anyone could take.

**Why the transfer hook.** One trait — `Held by claimant` — depends on `ownerOf`, so it becomes stale the instant a token is sold. Emitting `MetadataUpdate` from the transfer path keeps that trait honest on a listing page. Mints are deliberately excluded: there is no prior metadata for a marketplace to refresh.

The mutation-restore rule from Task 3's preamble applies here unchanged.

**Files**

- Modify: `/Library/Vibes/list-record/src/ListRecord.sol`
- Create (test): `/Library/Vibes/list-record/test/Announce.t.sol`
- Read only: `/Library/Vibes/list-record/test/fixtures/wallets.json`, `/Library/Vibes/list-record/test/mocks/MockList.sol`

**This task owns `contract AnnounceTest`, the first contract in `test/Announce.t.sol`.** Task 10 appends a second contract to the same file for its metadata-refresh work; it must not modify `AnnounceTest` and must not re-declare `supportsInterface` or `_update` on `ListRecord` — both are implemented here, once, and Task 10 only tests them.

**Interfaces**

*Consumes — from Tasks 3 and 4 (`src/ListRecord.sol`):* `LIST` (an `IWhitelistCurator`, whose `isSettled() external view returns (bool)` is the gate here), `totalClaimed`, `claim()`, `claimFor(address)`, `claimantOf`, `sealedOf`, `sealRecord(uint256)`, `isSealed(uint256)`, `error NotSettled()`, and the declaration `contract ListRecord is IERC4906, ERC721` — which already brings `MetadataUpdate(uint256)` and `BatchMetadataUpdate(uint256,uint256)` into scope, and brings `IERC165` into the inheritance graph (OZ's `IERC4906 is IERC165, IERC721`), which is what makes the `override(ERC721, IERC165)` list below legal.

*Consumes — from Task 2:* `MockList` with `setMember(...)` and `setSettled(bool)`; and `test/fixtures/wallets.json`, from which this task reads `.wallets.apex.*` and `.wallets.second.*` so that two distinct members claim and the announced range `(1, 2)` is a real range rather than a degenerate one.

*Consumes — from OpenZeppelin v5.x:*

```solidity
// ERC721.sol — the single hook every mint, transfer and burn passes through.
// Returns the PREVIOUS owner; address(0) means this was a mint.
function _update(address to, uint256 tokenId, address auth) internal virtual returns (address)

// ERC721.supportsInterface already returns true for
//   0x01ffc9a7 (ERC-165), 0x80ac58cd (ERC-721), 0x5b5e139f (ERC-721 Metadata)
```

*Produces — final public surface of `ListRecord`:*

```solidity
bool public settlementAnnounced;
error AlreadyAnnounced();
function announceSettled() external;                                  // permissionless, once, requires isSettled()
function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, IERC165) returns (bool);
function _update(address to, uint256 tokenId, address auth) internal virtual override returns (address from);
```

---

- [ ] **Step 1: Write the `announceSettled` tests.** Create `test/Announce.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {MockList} from "./mocks/MockList.sol";

contract AnnounceTest is Test {
    using stdJson for string;

    MockList internal list;
    ListRecord internal record;

    address internal rank1;
    address internal rank4;

    address internal constant RENDERER = address(0xBEEF);

    event BatchMetadataUpdate(uint256 _fromTokenId, uint256 _toTokenId);
    event MetadataUpdate(uint256 _tokenId);

    function setUp() public {
        string memory j = vm.readFile("test/fixtures/wallets.json");
        rank1 = j.readAddress(".wallets.apex.address");
        rank4 = j.readAddress(".wallets.second.address");

        list = new MockList();
        _seed(j, ".wallets.apex", rank1);
        _seed(j, ".wallets.second", rank4);
        record = new ListRecord(address(list), RENDERER);

        vm.prank(rank1);
        record.claim();
        vm.prank(rank4);
        record.claim();
    }

    function _seed(string memory j, string memory row, address account) internal {
        list.setMember(
            account,
            j.readUint(string.concat(row, ".hour")),
            j.readUint(string.concat(row, ".points")),
            vm.parseUint(j.readString(string.concat(row, ".weightWei"))),
            vm.parseUint(j.readString(string.concat(row, ".creditWei"))),
            j.readUint(string.concat(row, ".deposits"))
        );
    }

    function test_announce_reverts_before_settlement() public {
        vm.expectRevert(ListRecord.NotSettled.selector);
        record.announceSettled();
        assertFalse(record.settlementAnnounced(), "flag");
    }

    function test_anyone_may_announce_once_the_game_is_settled() public {
        list.setSettled(true);
        address stranger = makeAddr("stranger");

        vm.expectEmit(true, true, true, true, address(record));
        emit BatchMetadataUpdate(1, 2);
        vm.prank(stranger);
        record.announceSettled();

        assertTrue(record.settlementAnnounced(), "flag");
    }

    function test_announce_reverts_the_second_time() public {
        list.setSettled(true);
        record.announceSettled();
        vm.expectRevert(ListRecord.AlreadyAnnounced.selector);
        record.announceSettled();
    }
}
```

The `vm.prank(stranger)` in the middle test is the permissionless property under test, not incidental setup.

- [ ] **Step 2: Run them and watch them fail because `announceSettled` does not exist.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Announce.t.sol -vvv
```

```
Error (9582): Member "announceSettled" not found or not visible after argument-dependent lookup in contract ListRecord.
Error: Compilation failed
```

- [ ] **Step 3: Add the flag, the error and `announceSettled`.** In `src/ListRecord.sol`, add after the `sealedOf` mapping:

```solidity
    /// @notice Set by the one permissionless `announceSettled` call. There is no way to unset it.
    bool public settlementAnnounced;
```

add `error AlreadyAnnounced();` immediately above `error NonexistentToken();`, and append this function after `isSealed`:

```solidity

    /// @notice Tell every marketplace to re-read the whole collection, once, when the game freezes.
    /// @dev    The collection has no owner, so there is nobody who *could* be trusted with this.
    ///         It requires `isSettled()`, runs once, and does nothing but emit -- so leaving it open
    ///         to anyone costs nothing and depends on nobody.
    function announceSettled() external {
        if (settlementAnnounced) revert AlreadyAnnounced();
        if (!LIST.isSettled()) revert NotSettled();
        settlementAnnounced = true;
        emit BatchMetadataUpdate(1, totalClaimed);
    }
```

The `settlementAnnounced` check comes first so a second call reports `AlreadyAnnounced` rather than re-checking the game. Called with nothing claimed it would emit `BatchMetadataUpdate(1, 0)` — an empty range, harmless, and left unguarded on purpose: adding a `totalClaimed > 0` check would burn the one-shot flag on a different condition than the frozen contract describes.

- [ ] **Step 4: Run them and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Announce.t.sol -vvv
```

```
[PASS] test_announce_reverts_before_settlement()
[PASS] test_announce_reverts_the_second_time()
[PASS] test_anyone_may_announce_once_the_game_is_settled()
Suite result: ok. 3 passed; 0 failed; 0 skipped
```

- [ ] **Step 5: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Announce.t.sol
git commit -m "feat(record): permissionless announceSettled, the ownerless collection's one refresh"
```

- [ ] **Step 6: Prove all three tests bite, one mutation each.** Apply each mutation, run the command below, confirm the named failure, then `git checkout -- src/ListRecord.sol` before applying the next.

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Announce.t.sol -vvv
```

1. Delete `if (settlementAnnounced) revert AlreadyAnnounced();` →
   `[FAIL: next call did not revert as expected] test_announce_reverts_the_second_time()`
2. Delete `if (!LIST.isSettled()) revert NotSettled();` →
   `[FAIL: next call did not revert as expected] test_announce_reverts_before_settlement()`
3. Change `emit BatchMetadataUpdate(1, totalClaimed);` to `emit BatchMetadataUpdate(1, 1);` →
   `[FAIL: BatchMetadataUpdate param mismatch at _toTokenId: expected=2, got=1] test_anyone_may_announce_once_the_game_is_settled()`

Mutation 3 is the one that matters most: a hardcoded upper bound would refresh token 1 and silently leave every other token in the collection stale. After restoring, re-run and confirm green.

- [ ] **Step 7: Write the `supportsInterface` test.** Append inside `contract AnnounceTest`:

```solidity
    function test_supports_erc4906_and_the_erc721_ids() public view {
        assertTrue(record.supportsInterface(0x49064906), "ERC-4906");
        assertTrue(record.supportsInterface(0x80ac58cd), "ERC-721");
        assertTrue(record.supportsInterface(0x5b5e139f), "ERC-721 Metadata");
        assertTrue(record.supportsInterface(0x01ffc9a7), "ERC-165");
        assertFalse(record.supportsInterface(0xffffffff), "the ERC-165 sentinel");
        assertFalse(record.supportsInterface(0xdeadbeef), "an unrelated id");
    }
```

The last two are not filler: ERC-165 requires that `0xffffffff` return false, and a `supportsInterface` that returned true for everything would pass the first four assertions.

- [ ] **Step 8: Run it and watch it fail on ERC-4906 only.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_supports_erc4906_and_the_erc721_ids -vvv
```

```
[FAIL: ERC-4906] test_supports_erc4906_and_the_erc721_ids()
```

The three ERC-721 ids already pass — OZ's `ERC721` reports them — so this failure is exactly and only the missing 4906 declaration.

- [ ] **Step 9: Add the constant and the override.** In `src/ListRecord.sol`, add the import beside the other OZ interface import:

```solidity
import {IERC165} from "@openzeppelin/contracts/interfaces/IERC165.sol";
```

add this as the first member of the contract, above `IWhitelistCurator public immutable LIST;`:

```solidity
    /// @dev ERC-4906 defines only events, so it has no conventional interface id. This is the
    ///      constant the standard itself names, and the same one OZ's ERC721URIStorage reports.
    bytes4 private constant ERC4906_INTERFACE_ID = bytes4(0x49064906);

```

and append after `announceSettled`:

```solidity

    /// @inheritdoc IERC165
    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721, IERC165) returns (bool) {
        return interfaceId == ERC4906_INTERFACE_ID || super.supportsInterface(interfaceId);
    }
```

The `override(ERC721, IERC165)` list is mandatory, not stylistic: `ListRecord` reaches `supportsInterface` through both `ERC721` and `IERC4906`'s own `IERC165`, and solc rejects a bare `override` here with `Error (4327): Function needs to specify overridden contracts "ERC721" and "IERC165".` This declaration is final — no later task may add a second one.

Do not reach for `type(IERC4906).interfaceId`: it evaluates to `0x00000000`, because an interface id is the XOR of the function selectors an interface declares and `IERC4906` declares none. The literal is correct and is what OZ itself uses.

- [ ] **Step 10: Run it and watch it pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test test_supports_erc4906_and_the_erc721_ids -vvv
```

```
[PASS] test_supports_erc4906_and_the_erc721_ids()
```

- [ ] **Step 11: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Announce.t.sol
git commit -m "feat(record): declare ERC-4906 support so indexers know to listen"
```

- [ ] **Step 12: Prove the test bites.** Change the return line to `return super.supportsInterface(interfaceId);` and re-run Step 10's command:

```
[FAIL: ERC-4906] test_supports_erc4906_and_the_erc721_ids()
```

Then `git checkout -- src/ListRecord.sol` and re-run to confirm green.

- [ ] **Step 13: Write the transfer-hook tests.** Append inside `contract AnnounceTest`:

```solidity
    function test_a_transfer_emits_metadata_update() public {
        address buyer = makeAddr("buyer");
        vm.expectEmit(true, true, true, true, address(record));
        emit MetadataUpdate(1);
        vm.prank(rank1);
        record.transferFrom(rank1, buyer, 1);
    }

    function test_a_mint_does_not_emit_metadata_update() public {
        address third = makeAddr("third");
        list.setMember(third, 7, 100, 1 ether, 1 ether, 1);

        vm.recordLogs();
        vm.prank(third);
        record.claim();

        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; i++) {
            assertTrue(logs[i].topics[0] != keccak256("MetadataUpdate(uint256)"), "mint emitted MetadataUpdate");
        }
    }
```

The second test is the reason the first is not simply "emit on every `_update`". A mint has no prior metadata to refresh, so a `MetadataUpdate` there is noise every indexer has to process; `vm.recordLogs` is how you assert an event's **absence**, which `vm.expectEmit` cannot do. The `third` wallet is seeded with obviously synthetic numbers because nothing about it is a claim of fact — it exists only to make a third mint happen.

- [ ] **Step 14: Run them and watch the transfer test fail.**

```bash
cd /Library/Vibes/list-record && forge test --match-test "metadata_update" -vvv
```

```
[PASS] test_a_mint_does_not_emit_metadata_update()
[FAIL: Transfer != expected MetadataUpdate] test_a_transfer_emits_metadata_update()
```

The mint test passes trivially right now — nothing emits `MetadataUpdate` yet. Step 18's second mutation is what makes it meaningful.

- [ ] **Step 15: Override the `_update` hook.** Append at the end of the contract in `src/ListRecord.sol`:

```solidity

    /// @dev A sale changes `Held by claimant`, so the metadata really did change. Mints are skipped
    ///      (`from == address(0)`): there is no prior metadata for a marketplace to refresh.
    function _update(address to, uint256 tokenId, address auth) internal virtual override returns (address from) {
        from = super._update(to, tokenId, auth);
        if (from != address(0)) emit MetadataUpdate(tokenId);
    }
```

`_update` is the one hook OZ v5 routes every mint, transfer and burn through, and its return value is the **previous** owner — so `from == address(0)` is precisely "this was a mint". Calling `super._update` first is required: it is what performs the transfer and computes `from`. Like `supportsInterface`, this declaration is final; no later task adds a second one.

- [ ] **Step 16: Run them and watch both pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-test "metadata_update" -vvv
```

```
[PASS] test_a_mint_does_not_emit_metadata_update()
[PASS] test_a_transfer_emits_metadata_update()
Suite result: ok. 2 passed; 0 failed; 0 skipped
```

- [ ] **Step 17: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Announce.t.sol
git commit -m "feat(record): emit ERC-4906 MetadataUpdate on transfer, never on mint"
```

- [ ] **Step 18: Prove both tests bite.** Apply each mutation, run Step 16's command, confirm, then `git checkout -- src/ListRecord.sol`.

1. Delete `if (from != address(0)) emit MetadataUpdate(tokenId);` →
   `[FAIL: Transfer != expected MetadataUpdate] test_a_transfer_emits_metadata_update()`
2. Change that line to the unguarded `emit MetadataUpdate(tokenId);` →
   `[FAIL: mint emitted MetadataUpdate] test_a_mint_does_not_emit_metadata_update()`

After restoring, re-run and confirm both green.

- [ ] **Step 19: Run formatting, the linter and the whole suite one last time.**

```bash
cd /Library/Vibes/list-record && forge fmt && forge fmt --check && forge build --force && forge test
```

`forge fmt --check` prints nothing and `forge build` prints `Compiler run successful!`. The suite total is **29 tests**: `test/Interface.t.sol` 7 (Tasks 1–2) + `test/Claim.t.sol` 7 (Task 3) + `test/Seal.t.sol` 9 (Task 4) + `test/Announce.t.sol` 6 (this task). The last line reads:

```
Ran 4 test suites: 29 tests passed, 0 failed, 0 skipped (29 total tests)
```

Then the build-cleanliness check — no warnings anywhere and no lint note located in `src/`:

```bash
cd /Library/Vibes/list-record
forge build --force 2>&1 | grep -E "^warning\[|[[:space:]]+--> src/"; echo "exit=$?"
```

Expect no output and `exit=1`. To confirm that check is not vacuous, delete the `// forge-lint: disable-next-line(screaming-snake-case-immutable)` line above `uint256 public immutable graceHours;`, re-run it and watch it print `--> src/ListRecord.sol:22:30` with `exit=0`; then `git checkout -- src/ListRecord.sol`. Commit any reformatting:

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Announce.t.sol
git commit -m "style(record): forge fmt"
```

- [ ] **Step 20: Confirm the contract has no admin surface.** The design forbids an owner, a pause, a price and a withdraw (spec D7, §3.1), and the only defence against one being added later is that somebody looks. The contract's own doc comment contains the words "no pause" and "no withdraw", so the scan must skip comment lines or it flags itself:

```bash
cd /Library/Vibes/list-record
for f in src/*.sol; do
  echo "== $f"
  grep -vE '^[[:space:]]*(//|/\*|\*)' "$f" | grep -nE "Ownable|onlyOwner|payable|selfdestruct|delegatecall|receive\(|fallback\(|withdraw|pause"
  echo "exit=$?"
done
```

Expect exactly one file listed and `exit=1`:

```
== src/ListRecord.sol
exit=1
```

Any hit is a design violation, not a style question — stop and report it rather than fixing it silently.

The glob is `src/*.sol` rather than a single filename on purpose: spec §3.2 requires the *renderer* to have no setter either, and the same command covers `src/ListRecordRenderer.sol` automatically from the moment Task 7 creates it. Today it matches one file, so this step proves the claim only for `ListRecord`; Task 11's final audit runs the identical command when there are two. Do not delete this step in favour of that one — this is what keeps the contract clean across the six tasks in between.

---

### Task 6: The card template pipeline — `tools/gen_template.py` and its lock

The card is drawn once, by hand, as an SVG file. A Python script turns that file into two artifacts the contract can use: one flat byte blob and a list of cut points. This task builds the script, generates the artifacts, locks them with a Solidity test, and adds a CI step so the committed artifacts can never drift from the tool that made them.

**Background, in one paragraph.** The renderer stores the whole metadata JSON — envelope, traits and the SVG alike — as one blob of contract code, cut into fixed slices with per-token values spliced between them. So the generator does not merely encode the SVG: it wraps the SVG in the JSON envelope first, then splits the *whole* thing. The SVG carries 13 `{SLOT}` markers; the envelope adds 11 more (the `name` id and ten traits), giving **24 value slots and 25 fixed slices**. That is why `template/card.svg` has 13 markers while `template/offsets.txt` has 25 pairs. The envelope lives inside `tools/gen_template.py` — putting it in Solidity string literals would cost contract bytecode forever and would force a second Base64 pass at runtime.

**Restoring a mutation, stated once for this repo and every task after it.** `git checkout -- <path>` **is allowed here**, which is a deliberate difference from `/Library/Vibes/autopull`, whose blanket ban exists because its working tree routinely holds another agent's uncommitted work. `list-record` is a fresh repository created by Task 1, and every mutation below is applied to a file committed one step earlier, so nothing else can be discarded with it. Two rules qualify it. **Never `git checkout` a generated artifact** — anything under `template/` or `test/fixtures/golden_*` is restored by re-running `python3 tools/gen_template.py`, so the blob and the offsets can never be restored to different generations of each other. And **any restore of a file the generator reads is followed by a regeneration in the same command line**, so the tree is never briefly consistent-looking and actually stale.

#### Files

| | path |
|---|---|
| create | `/Library/Vibes/list-record/template/card.svg` |
| create | `/Library/Vibes/list-record/tools/gen_template.py` |
| create (generated) | `/Library/Vibes/list-record/template/blob.hex` |
| create (generated) | `/Library/Vibes/list-record/template/offsets.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_apex_sealed_json.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_apex_sealed_uri.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_apex_sealed_svg.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_floor_live_json.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_floor_live_uri.txt` |
| create (generated) | `/Library/Vibes/list-record/test/fixtures/golden_floor_live_svg.txt` |
| create | `/Library/Vibes/list-record/.github/workflows/ci.yml` |
| test | `/Library/Vibes/list-record/test/Template.t.sol` |
| read only | `/Library/Vibes/list-record/foundry.toml` — **Task 1 owns it.** This task verifies it and does not edit or commit it. |

#### Interfaces

**Consumes** — no Solidity from any other task. It needs three things Task 1 committed, and `python3` (3.8+, stdlib only — this repo has no Node toolchain):

```
foundry.toml      [profile.default] solc_version = "0.8.24", and
                  fs_permissions = [{access = "read", path = "./template"},
                                    {access = "read", path = "./test/fixtures"}]
                  plus [fmt] line_length = 120, tab_width = 4, bracket_spacing = false
remappings.txt    forge-std/=lib/forge-std/src/
                  @openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
lib/forge-std     submodule
```

**Produces** — three contracts for later tasks:

```
template/blob.hex      one line: "0x" followed by 1996 bytes of hex, no trailing newline.
                       The whole metadata JSON with the 24 per-token values cut out.
template/offsets.txt   ONE line, 50 comma-separated integers, no trailing newline, pairs
                       flattened: s0,l0,s1,l1,...  offsets[2i] = start of fixed slice i in
                       the blob, offsets[2i+1] = its length.  25 pairs.  Slice i is followed
                       by value i for i < 24; slice 24 is the tail.  The renderer's
                       constructor takes exactly this as uint16[50].
                       EVERY consumer parses it with exactly one call:
                         vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",")
                       There are no newlines in this file.  A parser that splits on a
                       newline gets one element and its require() fails in setUp.
test/fixtures/golden_<case>_json.txt   the spliced metadata JSON, before Base64
test/fixtures/golden_<case>_uri.txt    "data:application/json;base64," + base64(that JSON)
test/fixtures/golden_<case>_svg.txt    the percent-decoded SVG a browser sees
                       for case in {apex_sealed, floor_live}
```

The exact `description` string this task freezes into the blob, because Task 10 pins two properties of it (it must contain no case-insensitive match for `certif`, and it must state the caching limitation):

```
A permanent onchain record of what this wallet did in THE LIST. The art and the metadata are stored onchain and read from the game contract, so an unsealed record still moves with the wallet - marketplaces cache metadata and may show an older reading until they refresh.
```

The 24 value slots, in blob order — **the renderer task must emit values in exactly this order**:

```
 0 ID        JSON name                    12 STATUS    card, bottom right
 1 ID        card, top right              13 FRAME     card, sealed frame stroke-width
 2 COLOR     card, points fill            14 POINTS    trait Points
 3 POINTS    card, the mark               15 WEIGHT    trait Weight (ETH)
 4 WEIGHT    card, detail line 1          16 CREDIT    trait Credit (ETH)
 5 CREDIT    card, detail line 1          17 DEPOSITS  trait Deposits
 6 DEPOSITS  card, detail line 2          18 HOUR_J    trait Hour, plain "hour 30"
 7 HOUR      card, encoded "hour%2030"    19 WINDOW    trait Window
 8 WINDOW    card, detail line 2          20 ID        trait Claim Order
 9 ADDR      card, truncated claimant     21 STATUS    trait Status
10 HELD      card, "held%20by%20another"  22 CLAIMANT  trait Claimant, 42 chars
11 COLOR2    card, status fill            23 HELD_YN   trait Held by claimant, yes|no
```

#### Steps

- [ ] **Step 1: verify Task 1's read permissions before writing anything.** `vm.readFile` is refused unless the path is allow-listed, and the refusal message talks about permissions rather than missing files, which sends the engineer hunting the wrong bug. This step only *reads* `foundry.toml` — it belongs to Task 1 and this task neither edits nor commits it.

```
cd /Library/Vibes/list-record && grep -n -A3 "fs_permissions" foundry.toml && grep -n "line_length" foundry.toml
```

Expected: the `fs_permissions` array with **both** entries (`./template` and `./test/fixtures`) and `line_length = 120`. If `./template` is missing, stop here: `foundry.toml` is Task 1's file, every later expected output assumes Task 1's version, and adding the line from this task creates the second owner that split the two clusters in the first place. Go back to Task 1, add it there, re-run Task 1's own green check, then return.

- [ ] **Step 2: create the frozen card.** Write `/Library/Vibes/list-record/template/card.svg`. This is one single line plus a trailing newline. Do not reformat it, do not add indentation, do not change single quotes to double quotes: every SVG attribute uses `'` so that the payload contains no `"` at all and the JSON that wraps it needs no escaping. The middot characters are U+00B7 and are meant to be there — this is an `.svg` file, not a `.sol` file, so non-ASCII is fine *here*.

```svg
<svg xmlns='http://www.w3.org/2000/svg' width='1000' height='1000' viewBox='0 0 1000 1000' font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,DejaVu Sans Mono,monospace'><rect width='1000' height='1000' fill='#1c1c1c'/><g fill='#a4a4a4' font-size='20'><text x='60' y='70'>THE LIST</text><text x='940' y='70' text-anchor='end'>#{ID}</text></g><text x='500' y='500' fill='{COLOR}' font-size='180' text-anchor='middle'>{POINTS}</text><text x='500' y='576' fill='#a4a4a4' font-size='24' text-anchor='middle'>POINTS</text><path stroke='#303030' stroke-width='2' d='M200 626h600'/><text x='500' y='684' fill='#00dd33' font-size='23' text-anchor='middle'>{WEIGHT} ETH weight · {CREDIT} ETH credit</text><text x='500' y='722' fill='#00cc33' font-size='23' text-anchor='middle'>deposits {DEPOSITS} · joined {HOUR} · {WINDOW}</text><g font-size='20'><text x='60' y='944' fill='#a4a4a4'>{ADDR} · {HELD}</text><text x='940' y='944' fill='{COLOR2}' text-anchor='end'>{STATUS}</text></g><rect x='14' y='14' width='972' height='972' fill='none' stroke='#00dd33' stroke-width='{FRAME}'/></svg>
```

- [ ] **Step 3: write the failing test.** Create `/Library/Vibes/list-record/test/Template.t.sol`. It imports nothing from `src/` on purpose — it is a lock on the *files*, so it keeps biting even if the renderer is rewritten. Note the single-line offsets parse: it is the same one every other consumer uses.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";

/// @notice Locks the artifacts that tools/gen_template.py produces.
contract TemplateTest is Test {
    uint256 internal constant SLICES = 25;
    uint256 internal constant SLOTS = 24;
    uint256 internal constant BLOB_LEN = 1996;

    bytes internal blob;
    uint256[] internal offs;

    function setUp() public {
        blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        string[] memory parts = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        for (uint256 i; i < parts.length; ++i) {
            offs.push(vm.parseUint(parts[i]));
        }
    }

    function test_the_blob_is_the_measured_length() public view {
        assertEq(blob.length, BLOB_LEN, "template/blob.hex changed length");
    }

    function test_there_is_one_more_slice_than_there_are_slots() public view {
        assertEq(offs.length, SLICES * 2, "offsets.txt is not 25 start,len pairs");
        assertEq(SLICES, SLOTS + 1, "n slices must be n slots + 1");
    }

    function test_the_slices_tile_the_blob_with_no_gap_and_no_overlap() public view {
        uint256 cursor;
        for (uint256 i; i < SLICES; ++i) {
            assertEq(offs[i * 2], cursor, "slice does not start where the last one ended");
            cursor += offs[i * 2 + 1];
        }
        assertEq(cursor, blob.length, "slices do not cover the whole blob");
    }

    function test_the_blob_is_pure_ascii() public view {
        for (uint256 i; i < blob.length; ++i) {
            assertLt(uint8(blob[i]), 0x80, "template holds a byte a .sol string literal cannot");
        }
    }

    /// @dev The image field is a data: URI nested inside a JSON string.  Inside
    ///      it, a raw # would truncate the SVG at the first hex colour, a raw
    ///      quote would close the JSON string early and a raw space is what a
    ///      strict URI parser rejects.  Outside it - in name and description -
    ///      all three are ordinary characters, so the scan is scoped.
    function test_the_image_field_holds_no_character_that_would_break_it() public view {
        string memory s = string(blob);
        uint256 start = vm.indexOf(s, "data:image/svg+xml,");
        uint256 end = vm.indexOf(s, '","attributes":[');
        assertLt(start, end, "image field not found in the blob");
        for (uint256 i = start; i < end; ++i) {
            bytes1 c = blob[i];
            assertTrue(c != "#", "unencoded # inside the image field");
            assertTrue(c != '"', "unencoded quote inside the image field");
            assertTrue(c != " ", "unencoded space inside the image field");
        }
    }

    function test_resplicing_the_floor_live_values_reproduces_the_golden() public view {
        bytes[SLOTS] memory v = _floorLiveValues();
        bytes memory out;
        for (uint256 i; i < SLICES; ++i) {
            out = abi.encodePacked(out, _slice(i));
            if (i < SLOTS) out = abi.encodePacked(out, v[i]);
        }
        assertEq(string(out), vm.trim(vm.readFile("test/fixtures/golden_floor_live_json.txt")));
    }

    // ---------------------------------------------------------------- helpers

    function _slice(uint256 i) internal view returns (bytes memory s) {
        uint256 start = offs[i * 2];
        uint256 len = offs[i * 2 + 1];
        s = new bytes(len);
        for (uint256 j; j < len; ++j) {
            s[j] = blob[start + j];
        }
    }

    /// @dev The floor case is SYNTHETIC and its address says so - see the
    ///      provenance block in tools/gen_template.py.  0x...0223 is not a
    ///      wallet; it is the structural floor's own points count sitting in an
    ///      otherwise empty address.
    function _floorLiveValues() internal pure returns (bytes[SLOTS] memory v) {
        v[0] = "9182";
        v[1] = "9182";
        v[2] = "%2300ff41";
        v[3] = "223";
        v[4] = "0.0500";
        v[5] = "0.0500";
        v[6] = "1";
        v[7] = "hour%2030";
        v[8] = "judged";
        v[9] = "0x0000%E2%80%A60223";
        v[10] = "held%20by%20claimant";
        v[11] = "%2300ff41";
        v[12] = "live";
        v[13] = "0";
        v[14] = "223";
        v[15] = "0.0500";
        v[16] = "0.0500";
        v[17] = "1";
        v[18] = "hour 30";
        v[19] = "judged";
        v[20] = "9182";
        v[21] = "live";
        v[22] = "0x0000000000000000000000000000000000000223";
        v[23] = "yes";
    }
}
```

- [ ] **Step 4: run it and watch it fail for the right reason.**

```
cd /Library/Vibes/list-record && forge test --match-path test/Template.t.sol -vvv
```

Expected, verbatim apart from the absolute path:

```
[FAIL: vm.readFile: failed to open file "/Library/Vibes/list-record/template/blob.hex": No such file or directory (os error 2)] setUp() (gas: 0)
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

A `setUp` revert collapses the whole suite into one reported failure — that is why the count is `1 failed` and not `6 failed`. If instead you see `the path ... is not allowed to be accessed for read operations`, Step 1 was skipped and `foundry.toml` is missing its `./template` entry.

- [ ] **Step 5: write the generator.** Create `/Library/Vibes/list-record/tools/gen_template.py`. Read the four comment blocks in it — they are the encoding rules, the envelope, the value model and the fixture provenance, and they are the reason the whole scheme works.

```python
#!/usr/bin/env python3
"""Build the on-chain card template and the golden fixtures.

Reads   template/card.svg          the frozen card, with 13 {SLOT} markers
Writes  template/blob.hex          the concatenated fixed slices, 0x-prefixed
        template/offsets.txt       ONE line of comma-separated start,len pairs
        test/fixtures/golden_*.txt the JSON preimage, the tokenURI and the SVG
                                   for two named cases

Stdlib only.  Run from the repository root:  python3 tools/gen_template.py
"""

import base64
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------
# 1. percent-encoding
# --------------------------------------------------------------------------
# The template is stored ALREADY ENCODED so the contract does no encoding at
# runtime.  The set is minimal on purpose - every byte we encode costs two
# extra bytes of contract code forever.
#
#   %   the escape character itself; must go first or decoding is ambiguous
#   #   the URI *fragment* delimiter.  The payload is full of hex colours
#       (#1c1c1c, #00ff41); an unencoded one truncates the image at that point.
#   "   would have to be backslash-escaped inside the JSON string.  Encoding it
#       instead means the JSON needs no escaping at all - which is also why
#       every SVG attribute in card.svg uses single quotes.
#   &   XML entity introducer.
#   space, <, >, ?   the characters a strict data: URI parser may reject.
#   >= 0x80          Solidity string literals are ASCII-only (compile error
#                    8936: "Invalid character in string literal").  The card's
#                    middot U+00B7 is two bytes 0xC2 0xB7; encoded it becomes
#                    %C2%B7, which is plain ASCII and survives the trip through
#                    a .sol file, a hex blob and a JSON string unchanged.
ENCODE = set(b'%#"& <>?') | set(range(0x80, 0x100))


def pct(raw: bytes) -> str:
    out = []
    for b in raw:
        out.append("%%%02X" % b if b in ENCODE else chr(b))
    return "".join(out)


def unpct(s: str) -> bytes:
    out = bytearray()
    i = 0
    raw = s.encode("ascii")
    while i < len(raw):
        if raw[i : i + 1] == b"%":
            out.append(int(raw[i + 1 : i + 3], 16))
            i += 3
        else:
            out.append(raw[i])
            i += 1
    return bytes(out)


# --------------------------------------------------------------------------
# 2. the JSON envelope
# --------------------------------------------------------------------------
# Not percent-encoded: this is the JSON itself.  Only the SVG that lands in
# {IMAGE} is encoded.  The description states the marketplace caching limit and
# deliberately says nothing about any certification layer; both properties are
# asserted by the language-gate task, so this text cannot drift silently.
DESCRIPTION = (
    "A permanent onchain record of what this wallet did in THE LIST. "
    "The art and the metadata are stored onchain and read from the game "
    "contract, so an unsealed record still moves with the wallet - "
    "marketplaces cache metadata and may show an older reading until they "
    "refresh."
)

ENVELOPE = (
    '{"name":"THE LIST #{ID}",'
    '"description":"' + DESCRIPTION + '",'
    '"image":"data:image/svg+xml,{IMAGE}",'
    '"attributes":['
    '{"trait_type":"Points","value":{POINTS}},'
    '{"trait_type":"Weight (ETH)","value":{WEIGHT}},'
    '{"trait_type":"Credit (ETH)","value":{CREDIT}},'
    '{"trait_type":"Deposits","value":{DEPOSITS}},'
    '{"trait_type":"Hour","value":"{HOUR_J}"},'
    '{"trait_type":"Window","value":"{WINDOW}"},'
    '{"trait_type":"Claim Order","value":{ID}},'
    '{"trait_type":"Status","value":"{STATUS}"},'
    '{"trait_type":"Claimant","value":"{CLAIMANT}"},'
    '{"trait_type":"Held by claimant","value":"{HELD_YN}"}]}'
)

SLOT_ORDER = [
    "ID",       # 0  JSON name
    "ID",       # 1  card, top right
    "COLOR",    # 2  card, points fill
    "POINTS",   # 3  card, the mark
    "WEIGHT",   # 4  card, detail line 1
    "CREDIT",   # 5
    "DEPOSITS", # 6  card, detail line 2
    "HOUR",     # 7  percent-encoded: "hour%2041"
    "WINDOW",   # 8
    "ADDR",     # 9  card, truncated claimant
    "HELD",     # 10 percent-encoded: "held%20by%20claimant"
    "COLOR2",   # 11 card, status fill
    "STATUS",   # 12
    "FRAME",    # 13 sealed frame stroke-width
    "POINTS",   # 14 trait Points
    "WEIGHT",   # 15 trait Weight (ETH)
    "CREDIT",   # 16 trait Credit (ETH)
    "DEPOSITS", # 17 trait Deposits
    "HOUR_J",   # 18 trait Hour, plain: "hour 41"
    "WINDOW",   # 19 trait Window
    "ID",       # 20 trait Claim Order
    "STATUS",   # 21 trait Status
    "CLAIMANT", # 22 trait Claimant, full 42 chars
    "HELD_YN",  # 23 trait Held by claimant
]

MARKER = re.compile("[{][A-Z0-9_]+[}]")


# --------------------------------------------------------------------------
# 3. the value model - mirrors src/lib/Str.sol byte for byte
# --------------------------------------------------------------------------
# NO thousands separators.  Points, Weight (ETH), Credit (ETH) and Deposits are
# JSON *number* traits, and a JSON number may not contain a comma: '"value":36,924'
# is not valid JSON.  So a grouped card would have to disagree with its own
# trait list.  Plain digits also let each number be formatted once and spliced
# into both the card and the trait, which is why there are 24 slots and not 28.
def u(v: int) -> str:
    return str(v)


def eth4(wei: int) -> str:
    return "%d.%04d" % (wei // 10**18, (wei % 10**18) // 10**14)


def hex_addr(a: str) -> str:
    return "0x" + a.lower().replace("0x", "").rjust(40, "0")


def short_addr(a: str) -> str:
    h = hex_addr(a)
    return h[:6] + "%E2%80%A6" + h[-4:]


def values(d: dict) -> list:
    sealed = d["status"] == 2
    colour = "%2300dd33" if sealed else "%2300ff41"
    held = d["owner"].lower() == d["claimant"].lower()
    v = {
        "ID": u(d["id"]),
        "COLOR": colour,
        "COLOR2": colour,
        "POINTS": u(d["points"]),
        "WEIGHT": eth4(d["weightWei"]),
        "CREDIT": eth4(d["creditWei"]),
        "DEPOSITS": u(d["deposits"]),
        "HOUR": "hour%20" + u(d["hour"]),
        "HOUR_J": "hour " + u(d["hour"]),
        "WINDOW": "grace" if d["grace"] else "judged",
        "ADDR": short_addr(d["claimant"]),
        "HELD": "held%20by%20claimant" if held else "held%20by%20another",
        "HELD_YN": "yes" if held else "no",
        "STATUS": ("live", "settled", "sealed")[d["status"]],
        "FRAME": "4" if sealed else "0",
        "CLAIMANT": hex_addr(d["claimant"]),
    }
    return [v[name] for name in SLOT_ORDER]


# --------------------------------------------------------------------------
# 4. the two golden cases, and exactly what is observed in each
# --------------------------------------------------------------------------
# APEX_SEALED is a REAL member of THE LIST.  Every wallet fact below is decoded
# from one committed capture - the Deposited logs in maxpane's
# tests/fixtures/curator/captures/tenderly_logs.json (topic0 0xb8385097...69cb3,
# 231 events, 145 contributors, hours 0-1), summed per contributor:
#   claimant  0x381f...1744  the highest-points contributor in that capture,
#                            FirstDeposit index 47
#   hour      0              topic 2 of its first Deposited log  -> grace
#   weightWei 902107370000000000000   the last newWeight word, exact wei
#   creditWei 461100000000000000000   the sum of its creditedDelta words
#   deposits  2              the last txCount word
#   points    30035          _curve(weight) = isqrt(w)*1000/1e9, which also
#                            matches the rank-4 row of the committed screen
#                            fixture curator/screen/settled_payload.json exactly
# id, owner and status are TOKEN facts.  No token exists yet, so they are chosen
# to exercise the sealed / held-by-another branch; they are not claims about the
# wallet.  The owner is another real member of the same capture (index 20).
#
# FLOOR_LIVE is SYNTHETIC and its address says so: 0x...0223 is not a wallet, it
# is the floor's own points count in an otherwise empty address.  The committed
# capture covers hours 0-1 - inside the grace window - so it holds no judged-hour
# member at all, and pinning a judged hour onto a real captured address would be
# inventing a fact about a real person.  The numbers come from the contract's own
# constants instead: minDeposit 0.05 ETH (immutable, captures/results.json id 15)
# and earlyMultiplierBps() == BPS == 10000 once elapsed >= gracePeriod, so
# weightAdded == creditedDelta and _curve(0.05e18) == 223.  That is the
# structural floor of the game, and it is a derivation, not an observation.
APEX_SEALED = dict(
    id=7,
    claimant="0x381fe486d87c7f2633c777f1b5be3105a2a51744",
    owner="0xbb24cda09cb5a838ec93bae56278dc799f34feb4",
    points=30035,
    weightWei=902107370000000000000,
    creditWei=461100000000000000000,
    deposits=2,
    hour=0,
    grace=True,
    status=2,
)
FLOOR_LIVE = dict(
    id=9182,
    claimant="0x0000000000000000000000000000000000000223",
    owner="0x0000000000000000000000000000000000000223",
    points=223,
    weightWei=50000000000000000,
    creditWei=50000000000000000,
    deposits=1,
    hour=30,
    grace=False,
    status=0,
)
CASES = {"apex_sealed": APEX_SEALED, "floor_live": FLOOR_LIVE}


def main() -> int:
    svg = open(os.path.join(ROOT, "template", "card.svg"), "rb").read().rstrip(b"\n")
    full = ENVELOPE.replace("{IMAGE}", pct(svg))

    names = [m[1:-1] for m in MARKER.findall(full)]
    if names != SLOT_ORDER:
        print("slot order changed:\n  got      %s\n  expected %s" % (names, SLOT_ORDER))
        return 1

    parts = MARKER.split(full)          # len(parts) == len(names) + 1
    blob = "".join(parts).encode("ascii")
    offs, start = [], 0
    for p in parts:
        offs.append((start, len(p)))
        start += len(p)

    with open(os.path.join(ROOT, "template", "blob.hex"), "w") as f:
        f.write("0x" + blob.hex())
    with open(os.path.join(ROOT, "template", "offsets.txt"), "w") as f:
        f.write(",".join("%d,%d" % pair for pair in offs))

    for case, data in CASES.items():
        vals = values(data)
        json_text = "".join(
            parts[i] + (vals[i] if i < len(vals) else "") for i in range(len(parts))
        )
        uri = "data:application/json;base64," + base64.b64encode(
            json_text.encode("ascii")
        ).decode("ascii")
        image = json_text.split('"image":"', 1)[1].split('"', 1)[0]
        svg_out = unpct(image[len("data:image/svg+xml,") :])
        d = os.path.join(ROOT, "test", "fixtures")
        open(os.path.join(d, "golden_%s_json.txt" % case), "w").write(json_text)
        open(os.path.join(d, "golden_%s_uri.txt" % case), "w").write(uri)
        open(os.path.join(d, "golden_%s_svg.txt" % case), "wb").write(svg_out)

    print("blob      %d bytes" % len(blob))
    print("slices    %d" % len(parts))
    print("slots     %d" % len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: run the generator.**

```
cd /Library/Vibes/list-record && mkdir -p test/fixtures && python3 tools/gen_template.py
```

Expected output, exactly:

```
blob      1996 bytes
slices    25
slots     24
```

If it prints `slot order changed:` instead, `template/card.svg` was edited — compare the two lists it prints and fix the SVG rather than the `SLOT_ORDER` constant.

- [ ] **Step 7: run the test and watch it pass.**

```
cd /Library/Vibes/list-record && forge test --match-path test/Template.t.sol -vvv
```

Expected: `Suite result: ok. 6 passed; 0 failed; 0 skipped`.

- [ ] **Step 8: commit the pipeline.** `foundry.toml` is deliberately absent from this list: Task 1 owns it and this task only read it.

```
cd /Library/Vibes/list-record
git add template/card.svg tools/gen_template.py template/blob.hex template/offsets.txt test/fixtures/golden_apex_sealed_json.txt test/fixtures/golden_apex_sealed_uri.txt test/fixtures/golden_apex_sealed_svg.txt test/fixtures/golden_floor_live_json.txt test/fixtures/golden_floor_live_uri.txt test/fixtures/golden_floor_live_svg.txt test/Template.t.sol
git commit -m "feat(template): generate the percent-encoded card blob and lock it"
```

- [ ] **Step 9: prove the encoding rule bites.** Edit `tools/gen_template.py` and remove `#` from the encode set so the line reads exactly:

```python
ENCODE = set(b'%"& <>?') | set(range(0x80, 0x100))
```

Then:

```
cd /Library/Vibes/list-record && python3 tools/gen_template.py && forge test --match-path test/Template.t.sol
```

Expected: the generator prints `blob      1978 bytes`, and **two** tests go red:

```
Suite result: FAILED. 4 passed; 2 failed; 0 skipped
[FAIL: template/blob.hex changed length: 1978 != 1996] test_the_blob_is_the_measured_length()
[FAIL: unencoded # inside the image field] test_the_image_field_holds_no_character_that_would_break_it()
```

Note what did **not** go red: `test_resplicing_the_floor_live_values_reproduces_the_golden` still passes, because the generator rewrote the golden in the same run that broke the blob. A golden that its own generator regenerates cannot detect a generator change — that is the gap Step 10 closes, and it is worth seeing once with your own eyes.

Now restore. `tools/gen_template.py` is source, so `git checkout --` is the right move; the artifacts it feeds are generated, so they are restored by re-running it in the same command line:

```
cd /Library/Vibes/list-record && git checkout -- tools/gen_template.py && python3 tools/gen_template.py && forge test --match-path test/Template.t.sol && git status --short
```

Expected: `blob      1996 bytes`, `6 passed; 0 failed`, and no output from `git status --short`.

- [ ] **Step 10: add the CI regeneration guard.** Create `/Library/Vibes/list-record/.github/workflows/ci.yml`. This is the repository's only workflow file; the renderer task and the gas task each append one step to it rather than adding a second workflow.

```yaml
name: ci

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive

      - uses: foundry-rs/foundry-toolchain@v1

      - name: build
        run: forge build --sizes

      # No LIST_FORK_RPC is set here on purpose: the fork test must stay opt-in,
      # so a green CI run is a green *hermetic* run.
      - name: test
        run: forge test -vvv

      # The committed template must be exactly what the tool produces. Without
      # this, blob.hex and the goldens can be hand-edited or left stale and the
      # whole suite stays green against artifacts nothing generates any more.
      - name: the committed template is the one the generator makes
        run: |
          python3 tools/gen_template.py
          git diff --exit-code -- template/blob.hex template/offsets.txt test/fixtures/golden_apex_sealed_json.txt test/fixtures/golden_apex_sealed_uri.txt test/fixtures/golden_apex_sealed_svg.txt test/fixtures/golden_floor_live_json.txt test/fixtures/golden_floor_live_uri.txt test/fixtures/golden_floor_live_svg.txt
```

- [ ] **Step 11: prove the CI guard bites, locally.** First the case that does *not* fire, because knowing which one it is matters. Hand-edit a generated artifact:

```
cd /Library/Vibes/list-record
printf '0xdeadbeef' > template/blob.hex
python3 tools/gen_template.py
git diff --exit-code -- template/blob.hex ; echo "exit=$?"
```

The regeneration overwrites the sabotage, so the diff is clean and `exit=0`. The guard is not a tamper detector for artifacts; it is a drift detector between the tool and the artifacts. Now change the *generator*, which is the case that matters:

```
cd /Library/Vibes/list-record
sed -i '' 's/refresh[.]"/refresh!"/' tools/gen_template.py
python3 tools/gen_template.py
git diff --exit-code -- template/blob.hex ; echo "exit=$?"
```

Expected: a diff is printed and `exit=1`. Restore, source first and artifacts by regeneration:

```
cd /Library/Vibes/list-record && git checkout -- tools/gen_template.py && python3 tools/gen_template.py && git status --short
```

Expected: no output from `git status --short`.

- [ ] **Step 12: commit the guard and check the whole suite.**

```
cd /Library/Vibes/list-record
git add .github/workflows/ci.yml
git commit -m "ci: regenerate the template and fail on any drift from the committed artifacts"
forge test
```

Expected at this point in the sequence: **five suites, 35 tests, 0 failed** —

| suite | owner | tests |
|---|---|---|
| `test/Interface.t.sol` | Task 2 | 7 |
| `test/Claim.t.sol` | Task 3 | 7 |
| `test/Seal.t.sol` | Task 4 | 9 |
| `test/Announce.t.sol` | Task 5 | 6 |
| `test/Template.t.sol` | Task 6 | 6 |

If the total is not 35, the divergence is in an earlier task's suite, not this one: run `forge test --list` and compare against the table before continuing. Do not edit this number to match what you see — a suite that silently stopped being collected is exactly what the count exists to catch.

---

### Task 7: The renderer — SSTORE2, splice, Base64

Turn one `CardData` into a fully on-chain `data:application/json;base64,...` URI. Three new source files, one test file, and one appended CI step. **Task 6 must be done first** — this task reads `template/blob.hex`, `template/offsets.txt` and the golden fixtures it produced.

**How the mechanism works, in one paragraph.** Contract *code* is cheap to read (3 gas per word via `extcodecopy`) and expensive to write once (~200 gas per byte). So the 1 996-byte template is deployed as a contract whose entire body is that blob — the SSTORE2 pattern — behind a leading `STOP` byte so nobody can call it. Rendering allocates one output buffer, then walks slice, value, slice, value, and so on, copying each fixed slice straight out of contract code into the buffer and `mstore`-ing each per-token value in between. Base64 runs once, over the finished JSON. The order matters: Base64 is not byte-aligned to its plaintext, so a pre-encoded blob could not have values spliced into it, and doing it the other way costs a second encode pass — 876 k gas versus 443 k, measured during design (spec section 6.2).

**Decision, already taken, do not re-litigate: numbers carry NO thousands separators.** The prototype card rendered `36,924` and `1,363.3962`. The shipped card renders `30035` and `902.1073`. The decisive reason is **JSON, not bytes**: `Points`, `Weight (ETH)`, `Credit (ETH)` and `Deposits` are JSON *number* traits, and `"value":36,924` is not valid JSON — a grouped card would have to disagree with its own trait list. Two consequences follow: each number is formatted **once** and spliced into both the card and the trait, which is why there are 24 slots and not 28; and a grouping helper would be bytecode in a contract that can never be fixed. It is pinned by `test_numbers_carry_no_thousands_separator_anywhere`.

**Every address literal in this task is EIP-55 checksummed**, because solc rejects a mis-cased one with `Error (9429): This looks like an address but has an invalid checksum.` Re-derive any of them with:

```
cast to-check-sum-address 0x381fe486d87c7f2633c777f1b5be3105a2a51744
```

which prints `0x381fe486D87C7F2633c777F1b5bE3105A2a51744`. The other two: `0xbb24cda09cb5a838ec93bae56278dc799f34feb4` gives `0xbB24CDA09CB5A838Ec93bAe56278dC799f34FEb4`, and `0x0000000000000000000000000000000000000223` is unchanged because it contains no hex letters at all.

#### Files

| | path |
|---|---|
| create | `/Library/Vibes/list-record/src/lib/SSTORE2.sol` |
| create | `/Library/Vibes/list-record/src/lib/Str.sol` |
| create | `/Library/Vibes/list-record/src/ListRecordRenderer.sol` |
| test | `/Library/Vibes/list-record/test/Renderer.t.sol` |
| modify | `/Library/Vibes/list-record/.github/workflows/ci.yml` (append one step) |
| read only | `/Library/Vibes/list-record/src/interfaces/IListRecordRenderer.sol` — **Task 1 created it.** This task verifies and imports it; it does not create it. |
| read only | `/Library/Vibes/list-record/remappings.txt` — **Task 1 created it.** Verified, never rewritten. |

#### Interfaces

**Consumes**

```
src/interfaces/IListRecordRenderer.sol   struct CardData + interface        (Task 1)
template/blob.hex        1996 bytes of hex, "0x"-prefixed, one line          (Task 6)
template/offsets.txt     ONE line, 50 comma-separated ints, 25 (start,len)   (Task 6)
test/fixtures/golden_apex_sealed_{json,uri,svg}.txt                          (Task 6)
test/fixtures/golden_floor_live_{json,uri,svg}.txt                           (Task 6)
@openzeppelin/contracts/utils/Base64.sol -> library Base64 { encode(bytes) -> string }
```

The 24 value slots in blob order are listed in Task 6's Interfaces block; `_values` below implements exactly that order.

**Produces**

```solidity
// src/ListRecordRenderer.sol
contract ListRecordRenderer is IListRecordRenderer {
    address public immutable template;                      // the SSTORE2 pointer
    error BadOffsets();
    constructor(bytes memory blob, uint16[50] memory offs);
    function preimage(CardData calldata d) public view returns (bytes memory);
    function tokenURI(CardData calldata d) external view returns (string memory);
}

// src/lib/SSTORE2.sol   library SSTORE2
    function write(bytes memory data) internal returns (address ptr);
    function readInto(address ptr, uint256 start, uint256 len, bytes memory out, uint256 off) internal view;
    function size(address ptr) internal view returns (uint256);

// src/lib/Str.sol       library Str
    function u(uint256 v) internal pure returns (bytes memory);            // "30035"
    function eth4(uint256 weiAmount) internal pure returns (bytes memory); // "902.1073"
    function hexAddr(address a) internal pure returns (bytes memory);      // 42 chars, lowercase
    function shortAddr(address a) internal pure returns (bytes memory);    // "0x381f%E2%80%A61744"
```

`ListRecord` (Tasks 3-5) is the only production caller: it builds a `CardData` and calls `renderer.tokenURI(d)`. **The renderer never calls back into `ListRecord`** — that is what keeps the two constructors free of a cycle.

Two handles later tasks mutate, named here so their mutation steps are executable verbatim: inside `_values`, the status word is the local `bytes memory status`, and it is consumed twice, as `v[12] = status;` and `v[21] = status;`. Any mutation of the status branch must keep that name or fix both uses.

#### Steps

- [ ] **Step 1: verify Task 1's shared interface file.** Task 1 created `src/interfaces/IListRecordRenderer.sol` beside `IWhitelistCurator.sol`, because Task 3 already imports it. **Do not create it here** — two creators is exactly how the struct definition drifted between clusters.

```
cd /Library/Vibes/list-record && grep -nE "pragma solidity 0.8.24;|struct CardData|uint256 weightWei;|uint256 creditWei;|bool grace;|uint8 status;|function tokenURI" src/interfaces/IListRecordRenderer.sol
```

Expected: eight matching lines — the exact pin, the struct, the two wei fields, the two flag fields, and the interface function. If the file does not exist, stop and finish Task 1; every one of Tasks 3, 4 and 5 fails to compile without it, so it cannot legitimately be missing by the time you are here.

- [ ] **Step 2: verify the OpenZeppelin remapping.** Task 1 wrote `remappings.txt` and this task does not touch it.

```
cd /Library/Vibes/list-record && cat remappings.txt && ls lib/openzeppelin-contracts/contracts/utils/Base64.sol
```

Expected, exactly two lines and then the path:

```
forge-std/=lib/forge-std/src/
@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
lib/openzeppelin-contracts/contracts/utils/Base64.sol
```

That remapping is why every import in this task reads `@openzeppelin/contracts/utils/Base64.sol` and not `@openzeppelin/utils/Base64.sol`.

- [ ] **Step 3: write the failing golden test.** Create `/Library/Vibes/list-record/test/Renderer.t.sol` with the golden half. The two `CardData` cases are the two the generator emitted, so the goldens on disk are the answers.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {CardData} from "../src/interfaces/IListRecordRenderer.sol";
import {Str} from "../src/lib/Str.sol";

contract RendererTest is Test {
    ListRecordRenderer internal renderer;

    // APEX is a real member: the highest-points contributor in the committed
    // capture tests/fixtures/curator/captures/tenderly_logs.json (145
    // contributors, hours 0-1), FirstDeposit index 47.  weightWei is its last
    // observed newWeight word, creditWei the sum of its creditedDelta words,
    // deposits its last txCount word and hour 0 the topic of its first
    // Deposited log.  The game's own curve, isqrt(weight)*1000/1e9, maps that
    // weight to 30035 points, which is also the rank-4 row of the committed
    // screen fixture.  ANOTHER_MEMBER is index 20 of the same capture and only
    // ever appears as a non-claimant holder.
    address internal constant APEX = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;
    address internal constant ANOTHER_MEMBER = 0xbB24CDA09CB5A838Ec93bAe56278dC799f34FEb4;
    // FLOOR is SYNTHETIC and its address says so - the capture holds no
    // judged-hour member, so the judged case is built from contract constants:
    // minDeposit 0.05 ETH with the early multiplier flat at 1x after grace,
    // which the curve maps to exactly 223 points.
    address internal constant FLOOR = 0x0000000000000000000000000000000000000223;

    function setUp() public {
        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        string[] memory parts = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        uint16[50] memory offs;
        for (uint256 i; i < parts.length; ++i) {
            offs[i] = uint16(vm.parseUint(parts[i]));
        }
        renderer = new ListRecordRenderer(blob, offs);
    }

    function _apexSealed() internal pure returns (CardData memory) {
        return CardData({
            id: 7,
            claimant: APEX,
            owner: ANOTHER_MEMBER,
            points: 30035,
            weightWei: 902107370000000000000,
            creditWei: 461100000000000000000,
            deposits: 2,
            hour: 0,
            grace: true,
            status: 2
        });
    }

    function _floorLive() internal pure returns (CardData memory) {
        return CardData({
            id: 9182,
            claimant: FLOOR,
            owner: FLOOR,
            points: 223,
            weightWei: 0.05 ether,
            creditWei: 0.05 ether,
            deposits: 1,
            hour: 30,
            grace: false,
            status: 0
        });
    }

    function test_the_apex_sealed_uri_is_byte_identical_to_the_golden() public view {
        assertEq(renderer.tokenURI(_apexSealed()), vm.trim(vm.readFile("test/fixtures/golden_apex_sealed_uri.txt")));
    }

    function test_the_floor_live_uri_is_byte_identical_to_the_golden() public view {
        assertEq(renderer.tokenURI(_floorLive()), vm.trim(vm.readFile("test/fixtures/golden_floor_live_uri.txt")));
    }

    function test_the_uri_decodes_back_to_the_golden_json_and_svg() public view {
        string memory uri = renderer.tokenURI(_apexSealed());
        string memory b64 = vm.replace(uri, "data:application/json;base64,", "");
        string memory json = string(_b64decode(bytes(b64)));
        assertEq(json, vm.trim(vm.readFile("test/fixtures/golden_apex_sealed_json.txt")), "json");

        string memory image = vm.parseJsonString(json, ".image");
        string memory encoded = vm.replace(image, "data:image/svg+xml,", "");
        string memory svg = string(_pctDecode(bytes(encoded)));
        assertEq(svg, vm.trim(vm.readFile("test/fixtures/golden_apex_sealed_svg.txt")), "svg");
    }

    // ---------------------------------------------------------------- helpers

    function _b64decode(bytes memory data) internal pure returns (bytes memory out) {
        bytes memory alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        bytes memory rev = new bytes(256);
        for (uint256 i; i < 64; ++i) {
            rev[uint8(alphabet[i])] = bytes1(uint8(i));
        }
        uint256 pad;
        if (data[data.length - 1] == "=") ++pad;
        if (data[data.length - 2] == "=") ++pad;
        out = new bytes((data.length / 4) * 3 - pad);
        uint256 o;
        for (uint256 i; i < data.length; i += 4) {
            uint256 n = (uint256(uint8(rev[uint8(data[i])])) << 18) | (uint256(uint8(rev[uint8(data[i + 1])])) << 12)
                | (uint256(uint8(rev[uint8(data[i + 2])])) << 6) | uint256(uint8(rev[uint8(data[i + 3])]));
            if (o < out.length) out[o++] = bytes1(uint8(n >> 16));
            if (o < out.length) out[o++] = bytes1(uint8(n >> 8));
            if (o < out.length) out[o++] = bytes1(uint8(n));
        }
    }

    function _pctDecode(bytes memory s) internal pure returns (bytes memory out) {
        out = new bytes(s.length);
        uint256 o;
        uint256 i;
        while (i < s.length) {
            if (s[i] == "%") {
                out[o++] = bytes1(_nib(s[i + 1]) * 16 + _nib(s[i + 2]));
                i += 3;
            } else {
                out[o++] = s[i];
                ++i;
            }
        }
        assembly {
            mstore(out, o)
        }
    }

    function _nib(bytes1 c) internal pure returns (uint8) {
        uint8 b = uint8(c);
        if (b >= 48 && b <= 57) return b - 48;
        if (b >= 65 && b <= 70) return b - 55;
        return b - 87;
    }
}
```

- [ ] **Step 4: add the property half of the test, still before any implementation.** Insert these six tests into `RendererTest` immediately after `test_the_uri_decodes_back_to_the_golden_json_and_svg`, and append `StrHarness` at the very end of the file, outside the test contract.

```solidity
    function test_numbers_carry_no_thousands_separator_anywhere() public view {
        string memory json = string(renderer.preimage(_apexSealed()));
        assertTrue(vm.contains(json, "30035"), "points lost their digits");
        assertTrue(vm.contains(json, "902.1073"), "weight lost its digits");
        assertFalse(vm.contains(json, "30,035"), "a grouped number reached the card");
        assertFalse(vm.contains(json, "902,1073"), "a grouped number reached the card");
        // A JSON *number* trait may not contain a comma, so a grouped card and
        // an honest trait list cannot both exist.
        assertTrue(vm.contains(json, '"trait_type":"Points","value":30035}'), "Points is not a bare number");
    }

    function test_the_truncated_claimant_is_ascii_and_carries_the_encoded_ellipsis() public view {
        bytes memory json = renderer.preimage(_apexSealed());
        assertTrue(vm.contains(string(json), "0x381f%E2%80%A61744"), "short address changed shape");
        for (uint256 i; i < json.length; ++i) {
            assertLt(uint8(json[i]), 0x80, "a non-ASCII byte reached the output");
        }
    }

    function test_only_the_sealed_card_gains_a_frame_and_the_dimmer_green() public view {
        string memory sealedJson = string(renderer.preimage(_apexSealed()));
        string memory liveJson = string(renderer.preimage(_floorLive()));
        assertTrue(vm.contains(sealedJson, "stroke-width='4'/%3E%3C/svg%3E"), "sealed card lost its frame");
        assertTrue(vm.contains(liveJson, "stroke-width='0'/%3E%3C/svg%3E"), "live card grew a frame");
        assertTrue(vm.contains(sealedJson, "font-size='180'%20text-anchor='middle'%3E30035"), "mark moved");
        assertTrue(vm.contains(sealedJson, "fill='%2300dd33'%20font-size='180'"), "sealed mark is the live green");
        assertTrue(vm.contains(liveJson, "fill='%2300ff41'%20font-size='180'"), "live mark is the sealed green");
    }

    function test_the_status_word_is_one_word_and_matches_the_trait() public view {
        CardData memory d = _floorLive();
        d.status = 1; // game over, token not yet sealed
        string memory json = string(renderer.preimage(d));
        assertTrue(vm.contains(json, "text-anchor='end'%3Esettled%3C/text%3E"), "card status");
        assertTrue(vm.contains(json, '"trait_type":"Status","value":"settled"'), "trait status");
        assertFalse(vm.contains(json, "live%20%C2%B7%20settled"), "the two-word status came back");
    }

    function test_eth4_truncates_and_never_rounds() public {
        StrHarness s = new StrHarness();
        assertEq(s.eth4(1.00005 ether), "1.0000", "rounded up across the 4th decimal");
        assertEq(s.eth4(0.99999 ether), "0.9999", "rounded up across the whole number");
        assertEq(s.eth4(0), "0.0000");
        assertEq(s.eth4(1 wei), "0.0000");
        assertEq(s.eth4(0.0001 ether), "0.0001", "lost a leading zero of the fraction");
        assertEq(s.eth4(0.001 ether), "0.0010", "lost a leading zero of the fraction");
        assertEq(s.eth4(902107370000000000000), "902.1073");
    }

    function test_the_address_helpers_render_lowercase_and_ascii() public {
        StrHarness s = new StrHarness();
        assertEq(s.u(0), "0");
        assertEq(s.u(30035), "30035");
        assertEq(s.hexAddr(APEX), "0x381fe486d87c7f2633c777f1b5be3105a2a51744");
        assertEq(s.shortAddr(APEX), "0x381f%E2%80%A61744");
    }
```

and, after the closing brace of `contract RendererTest`:

```solidity
/// @dev Str is an internal library; this exposes it so the four formats can be
///      pinned directly instead of only through a golden.
contract StrHarness {
    function u(uint256 v) external pure returns (string memory) {
        return string(Str.u(v));
    }

    function eth4(uint256 w) external pure returns (string memory) {
        return string(Str.eth4(w));
    }

    function hexAddr(address a) external pure returns (string memory) {
        return string(Str.hexAddr(a));
    }

    function shortAddr(address a) external pure returns (string memory) {
        return string(Str.shortAddr(a));
    }
}
```

- [ ] **Step 5: run it and watch it fail for the right reason.**

```
cd /Library/Vibes/list-record && forge test --match-contract RendererTest -vvv
```

Expected: `Compiler run failed` with `Error (6275): Source "src/ListRecordRenderer.sol" not found` (and the same for `src/lib/Str.sol`). That is the right failure — the tests cannot run because nothing implements them yet. If instead the error names `src/interfaces/IListRecordRenderer.sol`, Step 1 was skipped.

- [ ] **Step 6: write SSTORE2.** Create `/Library/Vibes/list-record/src/lib/SSTORE2.sol`. This is already `forge fmt`-clean at `line_length = 120`, so a later format pass will not rewrap lines other tasks quote.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Store a byte blob as contract code and read slices of it back.
/// @dev    Contract code is ~200 gas/byte to write once and 3 gas/word to copy,
///         which is why the 1 996-byte card template lives here and not in
///         storage.  The blob is deployed behind a leading STOP (0x00) byte so
///         that a call to the pointer halts instead of executing the template.
library SSTORE2 {
    error DeployFailed();

    /// @dev Runtime of the deployer: PUSH2 <len> then the standard "copy my own
    ///      tail into memory and return it" stub, then STOP, then the payload.
    ///      `len` counts the STOP byte, hence `data.length + 1`.
    function write(bytes memory data) internal returns (address ptr) {
        bytes memory code = abi.encodePacked(hex"61", uint16(data.length + 1), hex"80600a3d393df300", data);
        assembly {
            ptr := create(0, add(code, 0x20), mload(code))
        }
        if (ptr == address(0)) revert DeployFailed();
    }

    /// @notice Copy `len` bytes of the payload starting at payload offset
    ///         `start` into `out` at byte offset `off`.
    /// @dev    `+ 1` skips the STOP byte.  extcodecopy zero-fills past the end
    ///         rather than reverting, so the caller owns the bounds.
    function readInto(address ptr, uint256 start, uint256 len, bytes memory out, uint256 off) internal view {
        assembly {
            extcodecopy(ptr, add(add(out, 0x20), off), add(start, 1), len)
        }
    }

    /// @notice Payload length, excluding the STOP byte.
    function size(address ptr) internal view returns (uint256 s) {
        assembly {
            s := sub(extcodesize(ptr), 1)
        }
    }
}
```

- [ ] **Step 7: write Str.** Create `/Library/Vibes/list-record/src/lib/Str.sol`.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice The only four value formats the card and the metadata use.
/// @dev    Numbers carry NO thousands separators.  `Points`, `Weight (ETH)`,
///         `Credit (ETH)` and `Deposits` are JSON *number* traits, and a JSON
///         number may not contain a comma - so a grouped card would have to
///         disagree with its own trait list, or the contract would have to
///         format every number twice.  Plain digits let each number be
///         formatted once and spliced into both places.
library Str {
    /// @notice Unsigned integer to decimal ASCII.
    function u(uint256 v) internal pure returns (bytes memory) {
        if (v == 0) return "0";
        uint256 n;
        for (uint256 t = v; t != 0; t /= 10) {
            n++;
        }
        bytes memory b = new bytes(n);
        while (v != 0) {
            b[--n] = bytes1(uint8(48 + (v % 10)));
            v /= 10;
        }
        return b;
    }

    /// @notice wei -> "902.1073": four decimals, truncated, never rounded.
    /// @dev    Truncation is deliberate: rounding a value UP across a boundary
    ///         would print a number the chain never held.
    function eth4(uint256 weiAmount) internal pure returns (bytes memory) {
        uint256 whole = weiAmount / 1e18;
        uint256 frac = (weiAmount % 1e18) / 1e14; // 18 - 4 decimals
        bytes memory f = u(frac);
        bytes memory pad = new bytes(4 - f.length);
        for (uint256 i; i < pad.length; ++i) {
            pad[i] = "0";
        }
        return abi.encodePacked(u(whole), ".", pad, f);
    }

    /// @notice Full lowercase 42-character address, for the `Claimant` trait.
    function hexAddr(address a) internal pure returns (bytes memory) {
        bytes memory b = new bytes(42);
        b[0] = "0";
        b[1] = "x";
        uint160 v = uint160(a);
        for (uint256 i = 41; i > 1; --i) {
            uint8 d = uint8(v & 0xf);
            b[i] = bytes1(d < 10 ? 48 + d : 87 + d);
            v >>= 4;
        }
        return b;
    }

    /// @notice `0x381f%E2%80%A61744` - the card's truncated claimant.
    /// @dev    The ellipsis is U+2026, three UTF-8 bytes E2 80 A6.  It is
    ///         emitted ALREADY PERCENT-ENCODED because this string's only
    ///         consumer is the percent-encoded SVG, and because a byte >= 0x80
    ///         cannot appear in a Solidity string literal at all (compile
    ///         error 8936).  The return value is pure ASCII.
    function shortAddr(address a) internal pure returns (bytes memory) {
        bytes memory h = hexAddr(a);
        return abi.encodePacked(h[0], h[1], h[2], h[3], h[4], h[5], "%E2%80%A6", h[38], h[39], h[40], h[41]);
    }
}
```

- [ ] **Step 8: write the renderer.** Create `/Library/Vibes/list-record/src/ListRecordRenderer.sol`.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {CardData, IListRecordRenderer} from "./interfaces/IListRecordRenderer.sol";
import {SSTORE2} from "./lib/SSTORE2.sol";
import {Str} from "./lib/Str.sol";

/// @notice Turns one CardData into a fully on-chain `data:application/json`
///         URI.  Immutable, ownerless, and it never calls back into
///         ListRecord.
/// @dev    The metadata JSON - envelope, traits and the percent-encoded SVG
///         alike - is one blob in contract code (SSTORE2), cut into 25 fixed
///         slices.  Rendering copies slice, value, slice, value ... straight
///         into one output buffer and Base64-encodes it once.  Because the
///         template is stored ALREADY percent-encoded, the contract does no
///         encoding at runtime; and because Base64 is not byte-aligned to its
///         plaintext, encoding once at the end is the only order that lets the
///         per-token values be spliced at all.
contract ListRecordRenderer is IListRecordRenderer {
    /// @notice Number of per-token values spliced into the template.
    uint256 internal constant SLOTS = 24;
    /// @notice Number of fixed slices; always SLOTS + 1.
    uint256 internal constant SLICES = 25;

    /// @notice SSTORE2 pointer holding the whole percent-encoded template.
    address public immutable template;

    /// @dev offsets[2i] = start of slice i in the blob, offsets[2i+1] = length.
    uint16[SLICES * 2] internal offsets;

    error BadOffsets();

    constructor(bytes memory blob, uint16[SLICES * 2] memory offs) {
        uint256 total;
        for (uint256 i; i < SLICES; ++i) {
            if (offs[i * 2] != total) revert BadOffsets();
            total += offs[i * 2 + 1];
        }
        if (total != blob.length) revert BadOffsets();
        template = SSTORE2.write(blob);
        offsets = offs;
    }

    /// @notice The 24 per-token values, in blob order.
    function _values(CardData calldata d) internal pure returns (bytes[SLOTS] memory v) {
        bytes memory id = Str.u(d.id);
        bytes memory points = Str.u(d.points);
        bytes memory weight = Str.eth4(d.weightWei);
        bytes memory credit = Str.eth4(d.creditWei);
        bytes memory deposits = Str.u(d.deposits);
        bytes memory hourN = Str.u(d.hour);
        bytes memory window_ = d.grace ? bytes("grace") : bytes("judged");
        bytes memory status = d.status == 2 ? bytes("sealed") : d.status == 1 ? bytes("settled") : bytes("live");
        // The sealed card is the only one that steps down to #00dd33; the
        // frame, not the hue, is what actually reads at thumbnail size.
        bytes memory colour = d.status == 2 ? bytes("%2300dd33") : bytes("%2300ff41");
        bool own = d.owner == d.claimant;

        v[0] = id; // JSON  name
        v[1] = id; // card  #id
        v[2] = colour; // card  points fill
        v[3] = points; // card  the mark
        v[4] = weight; // card  detail line 1
        v[5] = credit;
        v[6] = deposits; // card  detail line 2
        v[7] = abi.encodePacked("hour%20", hourN);
        v[8] = window_;
        v[9] = Str.shortAddr(d.claimant);
        v[10] = own ? bytes("held%20by%20claimant") : bytes("held%20by%20another");
        v[11] = colour; // card  status fill
        v[12] = status;
        v[13] = d.status == 2 ? bytes("4") : bytes("0"); // sealed frame
        v[14] = points; // trait Points
        v[15] = weight; // trait Weight (ETH)
        v[16] = credit; // trait Credit (ETH)
        v[17] = deposits; // trait Deposits
        v[18] = abi.encodePacked("hour ", hourN); // trait Hour
        v[19] = window_; // trait Window
        v[20] = id; // trait Claim Order
        v[21] = status; // trait Status
        v[22] = Str.hexAddr(d.claimant); // trait Claimant
        v[23] = own ? bytes("yes") : bytes("no"); // trait Held by claimant
    }

    /// @notice The finished metadata JSON, before Base64.  Public so a test can
    ///         diff it against the golden without decoding anything.
    function preimage(CardData calldata d) public view returns (bytes memory out) {
        bytes[SLOTS] memory v = _values(d);
        uint256 total = SSTORE2.size(template);
        for (uint256 i; i < SLOTS; ++i) {
            total += v[i].length;
        }

        out = new bytes(total);
        // Reserve 32 bytes of scratch immediately after `out`.  The splice
        // below copies values a full word at a time, so the last value of the
        // last iteration may overshoot `out`'s end by up to 31 bytes; this
        // makes that overshoot land in memory this call owns.
        assembly {
            mstore(0x40, add(mload(0x40), 0x20))
        }
        address tpl = template;
        uint256 off;
        for (uint256 i; i < SLICES; ++i) {
            uint256 len = offsets[i * 2 + 1];
            SSTORE2.readInto(tpl, offsets[i * 2], len, out, off);
            off += len;
            if (i == SLOTS) break; // the last slice has no value after it
            bytes memory val = v[i];
            uint256 vl = val.length;
            assembly {
                let dst := add(add(out, 0x20), off)
                let src := add(val, 0x20)
                // Word-at-a-time; the overshoot of the final word is always
                // overwritten by the next slice or lies inside the 32-byte
                // slack reserved above, never past it.
                for { let j := 0 } lt(j, vl) { j := add(j, 0x20) } { mstore(add(dst, j), mload(add(src, j))) }
            }
            off += vl;
        }
    }

    /// @inheritdoc IListRecordRenderer
    function tokenURI(CardData calldata d) external view returns (string memory) {
        return string(abi.encodePacked("data:application/json;base64,", Base64.encode(preimage(d))));
    }
}
```

- [ ] **Step 9: run the suite and watch it pass.**

```
cd /Library/Vibes/list-record && forge test --match-contract RendererTest -vvv
```

Expected: `Suite result: ok. 9 passed; 0 failed; 0 skipped`. If the two golden-URI tests fail while the property tests pass, the value order in `_values` does not match Task 6's `SLOT_ORDER` — compare index by index.

- [ ] **Step 10: commit.** Neither the interface nor `remappings.txt` appears here: Task 1 committed both and this task only read them.

```
cd /Library/Vibes/list-record
git add src/lib/SSTORE2.sol src/lib/Str.sol src/ListRecordRenderer.sol test/Renderer.t.sol
git commit -m "feat(renderer): splice the SSTORE2 template into a base64 tokenURI"
```

- [ ] **Step 11: prove the truncation guard bites.** In `src/lib/Str.sol` change the `eth4` fraction line to round instead of truncate:

```solidity
        uint256 frac = ((weiAmount % 1e18) + 5e13) / 1e14; // 18 - 4 decimals
```

Then:

```
cd /Library/Vibes/list-record && forge test --match-test test_eth4_truncates_and_never_rounds -vvv
```

Expected: `[FAIL: rounded up across the 4th decimal: 1.0001 != 1.0000] test_eth4_truncates_and_never_rounds()` and `Suite result: FAILED. 0 passed; 1 failed`.

Note that the golden tests **stay green** under this mutation, because neither golden value has a fifth decimal that rounds — which is exactly why the dedicated `eth4` test exists rather than trusting the goldens. Restore (source file, no generated artifact involved):

```
cd /Library/Vibes/list-record && git checkout -- src/lib/Str.sol && forge test --match-contract RendererTest
```

Expected: `9 passed; 0 failed`.

- [ ] **Step 12: prove the separator guard bites.** In `src/ListRecordRenderer.sol` replace the card's points value with a grouped literal:

```solidity
        v[3] = abi.encodePacked("30,035"); // card  the mark
```

Then:

```
cd /Library/Vibes/list-record && forge test --match-contract RendererTest
```

Expected: `Suite result: FAILED. 4 passed; 5 failed; 0 skipped`, with exactly these five red — `test_numbers_carry_no_thousands_separator_anywhere` (`a grouped number reached the card`), `test_only_the_sealed_card_gains_a_frame_and_the_dimmer_green` (`mark moved`), `test_the_apex_sealed_uri_is_byte_identical_to_the_golden`, `test_the_floor_live_uri_is_byte_identical_to_the_golden` and `test_the_uri_decodes_back_to_the_golden_json_and_svg`. Both goldens go red because slot 3 is shared by both cases. Restore:

```
cd /Library/Vibes/list-record && git checkout -- src/ListRecordRenderer.sol && forge test --match-contract RendererTest
```

Expected: `9 passed; 0 failed`.

- [ ] **Step 13: prove the offsets guard bites.** The constructor rejects an offsets array that does not tile the blob, and that guard is the only thing standing between a mis-generated offsets file and a permanently wrong immutable renderer. Temporarily corrupt the last pair in `setUp` by adding this line just before `renderer = new ListRecordRenderer(blob, offs);`:

```solidity
        offs[49] = offs[49] + 1; // MUTATION: last slice one byte too long
```

Then:

```
cd /Library/Vibes/list-record && forge test --match-contract RendererTest
```

Expected: `[FAIL: BadOffsets()] setUp() (gas: 0)` and `Suite result: FAILED. 0 passed; 1 failed; 0 skipped` — a `setUp` revert is reported as one failure, not nine. Restore:

```
cd /Library/Vibes/list-record && git checkout -- test/Renderer.t.sol && forge test --match-contract RendererTest
```

Expected: `9 passed; 0 failed`.

- [ ] **Step 14: scan the renderer for an admin surface, and put the scan in CI.** Spec section 3.2 requires `ListRecordRenderer` to be pure view and immutable, with no setter, no upgrade path and no way for anyone to change anybody's art. `ListRecord` has its own scan in Task 5; that scan cannot cover this file, because this file did not exist when it ran. Run it now:

```
cd /Library/Vibes/list-record
grep -nE "Ownable|onlyOwner|payable|selfdestruct|delegatecall|receive[(]|fallback[(]|withdraw|pause|upgradeTo|initializ|function[[:space:]]+set[A-Z]" src/ListRecordRenderer.sol src/lib/SSTORE2.sol src/lib/Str.sol ; echo "exit=$?"
```

Expected: no output and `exit=1`. The one piece of mutable state, `offsets`, is written only in the constructor, and this scan is what proves no second writer was ever added. Now prove the scan bites — add a setter just above the `/// @inheritdoc IListRecordRenderer` line in `src/ListRecordRenderer.sol`:

```solidity
    function setTemplate(address t) external {
        offsets[0] = uint16(uint160(t));
    }
```

Re-run the same grep. Expected: `src/ListRecordRenderer.sol:124:    function setTemplate(address t) external {` and `exit=0`. Restore with `git checkout -- src/ListRecordRenderer.sol` and re-run the grep to confirm `exit=1` again.

Then append this step to `/Library/Vibes/list-record/.github/workflows/ci.yml`, at the same indentation as the steps Task 6 wrote, after the template-drift step:

```yaml
      # Spec 3.2: the renderer is immutable, has no setter and no upgrade path.
      # It is the one contract nobody can ever fix, so it gets the same
      # no-admin-surface scan ListRecord gets. Leading "!" inverts the exit code:
      # the step passes only when grep finds nothing.
      - name: the renderer has no admin surface
        run: |
          ! grep -nE "Ownable|onlyOwner|payable|selfdestruct|delegatecall|receive[(]|fallback[(]|withdraw|pause|upgradeTo|initializ|function[[:space:]]+set[A-Z]" src/ListRecordRenderer.sol src/lib/SSTORE2.sol src/lib/Str.sol
```

Commit it:

```
cd /Library/Vibes/list-record
git add .github/workflows/ci.yml
git commit -m "ci: scan the renderer for an admin surface, not just ListRecord"
```

- [ ] **Step 15: record the measured cost for the gas task.** Run the suite with a gas report so the numbers land in the terminal:

```
cd /Library/Vibes/list-record && forge test --match-contract RendererTest --gas-report
```

Measurements taken while validating this task (forge 1.5.1-stable, solc 0.8.24, optimizer on, 200 runs, each state measured in its own transaction so nothing is warm from a previous call):

| quantity | measured | ceiling the gas task pins | headroom |
|---|---|---|---|
| `tokenURI`, sealed card | **274 426 gas**, 2 937 bytes out | 350 000 | 27.5% |
| `tokenURI`, live card | **271 909 gas**, 2 937 bytes out | 350 000 | 28.7% |
| deploy `ListRecordRenderer` incl. the SSTORE2 write of 1 996 B | **1 483 205 gas** | not pinned | — |

Two notes for whoever writes `test/Gas.t.sol`. The `--gas-report` table shows `tokenURI` max 263 552 and a deployment cost of 1 611 964; those are the report's own accounting and are **not** the numbers to pin — pin what a `gasleft()` sandwich measures, which is the table above. And spec section 6.1 quotes **276 275** for the same read, taken through a slightly different harness during design; it is the conservative figure, it is 1 849 gas above what this code measures here, and both sit far under 350 000. A ceiling must never be set below a measured cost, so a ceiling of 275 000 for the sealed state would be red on the day it was written.

- [ ] **Step 16: confirm the tree is clean and the whole suite is green.** Nothing changed on disk in Steps 11 through 15 except the CI file committed in Step 14.

```
cd /Library/Vibes/list-record && git status --short && forge fmt --check && forge test
```

Expected: no output from `git status --short`, no output from `forge fmt --check`, and **six suites, 44 tests, 0 failed** —

| suite | owner | tests |
|---|---|---|
| `test/Interface.t.sol` | Task 2 | 7 |
| `test/Claim.t.sol` | Task 3 | 7 |
| `test/Seal.t.sol` | Task 4 | 9 |
| `test/Announce.t.sol` | Task 5 | 6 |
| `test/Template.t.sol` | Task 6 | 6 |
| `test/Renderer.t.sol` | Task 7 | 9 |

If the total is not 44, run `forge test --list` and reconcile against this table before continuing; a suite that stopped being collected is the failure this count exists to catch. Do not adjust the number to match the output.

---

### Task 8: `ListRecord.tokenURI` — live while unsealed, permanent once sealed

A record NFT is *not* a snapshot taken at mint: while the token is unsealed the renderer asks the
game what the wallet's numbers are **right now**, so a wallet that keeps depositing watches its own
token's points rise. Once the holder calls `sealRecord`, the numbers were copied into the token's
own storage and the token must never consult the game again — not even if the game starts returning
different answers.

`LIST` is the deployed, verified, non-upgradeable `WhitelistCurator`
(`0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`, Ethereum mainnet). Wallets deposit ETH; a sqrt curve
turns deposited weight into points; the game runs in hours; the first 24 are "grace" and every hour
after is "judged". `isSettled()` returns true once the game has finished, after which every
per-wallet view is frozen for ever.

**One trap, and it is the most important fact in this project.** The game also exposes a raw
`contributors(address)` getter (`0x1f6d4942`) returning `firstHour + 1`, with `0` meaning "never
deposited". Reading *that* and treating the value as the hour makes every non-member render as an
hour-0 founder — the rarest cohort in the game. **Membership and the join hour come from
`firstHourOf(address) → (uint256 hour, bool hasJoined)`, always, both return words.** Spec §1.1 was
corrected on 2026-08-18: that getter **is** vendored in maxpane's ABI file, so the guard is
discipline plus a test, not an absence. It is deliberately absent from `IWhitelistCurator`; do not
add it.

#### Restoring a mutation — read once, applies to Tasks 8 through 11

`list-record` is a **fresh repo with no third-party uncommitted work**, so `git checkout -- <path>`
is allowed here. `/Library/Vibes/autopull`'s blanket ban exists because *its* working tree carries
other people's uncommitted changes; that reason does not exist in this repo. Two exceptions hold
throughout Tasks 8–11:

1. **Anything under `template/` is generated.** Undo a template mutation by re-running
   `python3 tools/gen_template.py`, never by `git checkout`, so the blob and its offsets can never
   drift apart. Every template mutation below is therefore either made *in the generator* and
   regenerated, or is **byte-length preserving** so the committed offsets still line up.
2. **When the mutated file also carries this task's own uncommitted implementation**, `git checkout`
   would discard that too. Those restores are hand edits back to the exact text the step quotes.

#### Fixture wallets — one honest provenance, used by Tasks 8, 9, 10 and 11

Three constants appear verbatim in every test contract in Tasks 8–11. They are **not** read from
`test/fixtures/wallets.json` (Task 2's file): coupling six test files and a deploy test to one JSON
shape means a shape change in Task 2 turns four tasks red for no reason. What they must *not* do is
disagree with it, so Step 0 below greps for the real address.

| constant | address | status |
|---|---|---|
| `MEMBER` | `0x381fe486D87C7F2633c777F1b5bE3105A2a51744` | **real**, captured |
| `JUDGED` | `address(0xF100)` | **synthetic**, labelled |
| `CEILING` | `address(0xCE11)` | **synthetic**, labelled |

`MEMBER` provenance, field by field, from the committed captures in `/Library/Vibes/autopull`:

- **points 30 035** — captured. Rank 4 in `tests/fixtures/curator/screen/grace_payload.json`,
  `judged_payload.json` and `settled_payload.json`, and `clean_rank` 8 in
  `tests/fixtures/curator/sybil/clean_list_rows_worst.json`. All four agree.
- **credit 461.1 ETH** — captured, same rows (`credit_eth`).
- **deposits 2** — captured, same rows (`tx_count`).
- **weight 902 101 225 000 000 000 000 wei** — **derived, not observed.** No committed capture
  records a per-wallet weight. `pointsOf` is `sqrt(weight) * 1000 / 1e9`
  (`tests/fixtures/curator/captures/source.sol`), which inverts exactly: the smallest weight whose
  curve is 30 035 is `(30035 * 1e6)² = 902 101 225 × 1e12` wei. Verified: `isqrt` of that is
  `30 035 000 000` exactly, so the curve returns 30 035.
- **hour 1** — **chosen, not observed.** No committed capture records a per-wallet join hour. The
  derived weight-to-credit ratio is 902.101225 / 461.1 = 1.956×, and `earlyMultiplierBps` decays
  linearly from 20 000 to 10 000 over the 86 400-second grace period, so 19 564 bps lands ~3 767 s
  in — hour 1. It is the consistent choice, and it is a choice.

Attaching population-envelope numbers to a real address is dishonest and is forbidden, so the two
boundary rows carry invented addresses that cannot be mistaken for wallets:

- `JUDGED` — the committed sweep stops at hour 23, so **no judged-hour wallet was ever captured**.
  This row is built from the contract's own constants: `minDeposit` 0.05 ETH (`0x41b3d185`, captured
  as `0x4563918244f40000`) in a judged hour, where the early multiplier is flat 1×, so weight equals
  credit and the curve returns exactly **223** points — the structural floor.
- `CEILING` — the widest card the contract's constants permit. `creditCap` is 1000 ETH (`0x1ea0466e`
  → `0x3635c9adc5dea00000`) and the constructor proves max weight is `2 * creditCap`, so 2000 ETH is
  the true weight maximum and `curve(2000e18) == 44 721`. Deposits and hour have no contract bound;
  9 999 and 999 are chosen upper bounds and are labelled as such in the code.

**Every address literal is EIP-55 checksummed** (solc rejects anything else). Re-derive with:

```bash
cast to-check-sum-address 0x381fe486d87c7f2633c777f1b5be3105a2a51744
# 0x381fe486D87C7F2633c777F1b5bE3105A2a51744
cast to-check-sum-address 0xcb0b0531e86a9ac36fa865ca8e3dbccf047fda91
# 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91
```

`address(0xF100)`, `address(0xCE11)` and `address(0xB0B)` are short integer literals cast to
`address`, not 40-digit address literals, so EIP-55 does not apply to them — that is exactly why
they are written that way.

#### Files

- **modify:** `/Library/Vibes/list-record/src/ListRecord.sol`
- **create:** `/Library/Vibes/list-record/test/Traits.t.sol`

`test/Traits.t.sol` is created here and extended by Task 9. Tasks 8 and 9 are its only owners.

#### Interfaces

**Consumes** — all already exist when this task starts; create none of them:

```solidity
// src/interfaces/IWhitelistCurator.sol            (Task 1)
interface IWhitelistCurator {
    function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined);
    function pointsOf(address account) external view returns (uint256);
    function weightOf(address account) external view returns (uint256);
    function contributedBy(address account) external view returns (uint256);
    function txCountOf(address account) external view returns (uint256);
    function isSettled() external view returns (bool);
    function currentHour() external view returns (uint256);
    function gracePeriod() external view returns (uint256);
    function hourDuration() external view returns (uint256);
}

// src/interfaces/IListRecordRenderer.sol          (Task 1) -- CardData is declared at FILE level,
// outside the interface, so both contracts import it by name.
struct CardData {
    uint256 id; address claimant; address owner;
    uint256 points; uint256 weightWei; uint256 creditWei;
    uint256 deposits; uint256 hour;
    bool grace;    // hour < graceHours
    uint8 status;  // 0 = live, 1 = settled, 2 = sealed
}
interface IListRecordRenderer {
    function tokenURI(CardData calldata d) external view returns (string memory);
}

// src/ListRecordRenderer.sol                      (Task 7)
contract ListRecordRenderer is IListRecordRenderer {
    constructor(bytes memory blob, uint16[50] memory offsets);
}

// src/ListRecord.sol                              (Tasks 3, 4 and 5)
contract ListRecord is IERC4906, ERC721 {
    constructor(address list_, address renderer_);   // reads gracePeriod()/hourDuration()
    IWhitelistCurator public immutable LIST;
    IListRecordRenderer public immutable renderer;
    uint256 public immutable graceHours;
    struct SealedRecord {
        uint32 points; uint96 weightWei; uint96 creditWei;
        uint32 deposits; uint32 hour; uint64 sealedAt;   // sealedAt == 0 means not sealed
    }
    mapping(address => uint256) public tokenOf;
    mapping(uint256 => address) public claimantOf;
    mapping(uint256 => SealedRecord) public sealedOf;
    function claim() external returns (uint256 id);
    function sealRecord(uint256 id) external;
    error NonexistentToken();
}

// test/mocks/MockList.sol                         (Task 2) -- the ONLY game contract the default
// suite ever sees.  Setter NAMES are frozen by ruling R4; `setGrace` does not exist.
contract MockList is IWhitelistCurator {
    function setMember(
        address who, uint256 hour_, uint256 points_,
        uint256 weightWei_, uint256 creditWei_, uint256 deposits_
    ) external;
    function setSettled(bool v) external;
    function setHourParams(uint256 gracePeriod_, uint256 hourDuration_) external;
    // constructed with gracePeriod 86400 and hourDuration 3600, so graceHours == 24
}
```

**Produces:** `function tokenURI(uint256 id) public view override returns (string memory);` on
`src/ListRecord.sol`.

---

- [ ] **Step 0: Verify the four things Tasks 1–7 must already have got right.**

```bash
cd /Library/Vibes/list-record
rg -n "fs_permissions" foundry.toml
rg -n "^function setMember" -A3 test/mocks/MockList.sol || rg -n "function setMember" -A4 test/mocks/MockList.sol
head -c 120 template/offsets.txt; echo
rg -in "381fe486d87c7f2633c777f1b5be3105a2a51744" test/fixtures/wallets.json
```

Expected, in order:

1. `fs_permissions` names **both** paths — `{access = "read", path = "./template"}` and
   `{access = "read", path = "./test/fixtures"}`. Every test in Tasks 8–11 and the deploy script
   read `template/blob.hex`; without the first entry they all fail with
   `vm.readFile: the path template/blob.hex is not allowed to be accessed for read operations`.
2. `setMember` takes exactly `(address who, uint256 hour_, uint256 points_, uint256 weightWei_,
   uint256 creditWei_, uint256 deposits_)`, in that order.
3. `offsets.txt` is **one line of comma-separated integers** (`110,7,321,4,…`) with no spaces and no
   newlines.
4. At least one match for the `MEMBER` address.

If any of the four differs, **stop and reconcile with the owning task** — do not adapt the call
sites here. (2) disagreeing means Task 2's Interfaces block and this one contradict each other and
one of them is wrong; (3) disagreeing means a task ignored ruling R1 and every `setUp` in Tasks 8–11
will revert; (4) missing means this plan names a real wallet Task 2's fixture does not, which is the
exact defect the fixture exists to prevent.

- [ ] **Step 1: Write the failing test file.**

Create `/Library/Vibes/list-record/test/Traits.t.sol` with exactly this content.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {MockList} from "./mocks/MockList.sol";

/// @notice The live-versus-permanent contract of the whole design.
contract TokenURISourcing is Test {
    MockList internal list;
    ListRecordRenderer internal renderer;
    ListRecord internal record;

    // REAL, captured.  points 30035 / credit 461.1 ETH / 2 deposits are rank 4 of
    // tests/fixtures/curator/screen/grace_payload.json in the maxpane repo.  The weight is DERIVED
    // by inverting the game's own sqrt curve -- (30035 * 1e6)^2 -- because no committed capture
    // records a per-wallet weight.  The hour is CHOSEN: 902.101225 / 461.1 == 1.956x, which
    // earlyMultiplierBps reaches about one hour into the 24-hour grace window.
    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;
    uint256 internal constant M_POINTS = 30_035;
    uint256 internal constant M_WEIGHT = 902_101_225_000_000_000_000; // 902.101225 ETH
    uint256 internal constant M_CREDIT = 461.1 ether;
    uint256 internal constant M_DEPOSITS = 2;
    uint256 internal constant M_HOUR = 1;

    function setUp() public {
        list = new MockList();
        list.setMember(MEMBER, M_HOUR, M_POINTS, M_WEIGHT, M_CREDIT, M_DEPOSITS);

        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        renderer = new ListRecordRenderer(blob, _offsets());
        record = new ListRecord(address(list), address(renderer));
    }

    /// @dev template/offsets.txt is ONE line of 50 comma-separated integers: flattened (start,len)
    ///      pairs s0,l0,s1,l1,... -- 25 fixed slices with 24 per-token values spliced between them.
    ///      Task 6 owns the file and this is its only format (ruling R1).
    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function test_tokenURI_reverts_for_an_unclaimed_id() public {
        vm.expectRevert(ListRecord.NonexistentToken.selector);
        record.tokenURI(1);
    }

    function test_the_grace_boundary_is_the_games_own_arithmetic() public view {
        // gracePeriod() 86400 / hourDuration() 3600 == 24.  Never hardcode the 24.
        assertEq(record.graceHours(), 24);
    }

    function test_an_unsealed_token_tracks_the_game() public {
        vm.prank(MEMBER);
        uint256 id = record.claim();
        string memory before_ = record.tokenURI(id);
        assertGt(bytes(before_).length, 2_000, "tokenURI must actually render");

        // The wallet escalates.  These numbers satisfy the game's own curve --
        // curve(1000 ETH) == 31622 -- because a fixture that violates it is a lie about what the
        // chain can return, even though the mock does not enforce it.
        list.setMember(MEMBER, M_HOUR, 31_622, 1_000 ether, 520 ether, 3);
        string memory after_ = record.tokenURI(id);

        assertTrue(
            keccak256(bytes(before_)) != keccak256(bytes(after_)),
            "an unsealed token must follow the game"
        );
    }

    function test_a_sealed_token_ignores_the_game() public {
        vm.prank(MEMBER);
        uint256 id = record.claim();
        list.setSettled(true);
        vm.prank(MEMBER);
        record.sealRecord(id);

        string memory frozen = record.tokenURI(id);
        assertGt(bytes(frozen).length, 2_000, "tokenURI must actually render");

        // Now make the game lie: different hour, different everything.
        list.setMember(MEMBER, 7, 1, 1 wei, 1 wei, 999);

        assertEq(record.tokenURI(id), frozen, "a sealed token must not move");
    }
}
```

- [ ] **Step 2: Run it and watch it fail for the right reason.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract TokenURISourcing -vvv
```

`ListRecord` has not overridden `tokenURI` yet, so OpenZeppelin v5's default runs: it calls
`_requireOwned`, then returns `""` because `_baseURI()` is empty. Expect three red and one green:

```
[FAIL: tokenURI must actually render: 0 <= 2000] test_a_sealed_token_ignores_the_game()
[FAIL: tokenURI must actually render: 0 <= 2000] test_an_unsealed_token_tracks_the_game()
[PASS] test_the_grace_boundary_is_the_games_own_arithmetic()
[FAIL: Error != expected error] test_tokenURI_reverts_for_an_unclaimed_id()
```

The fourth fails because the revert data is OpenZeppelin's `ERC721NonexistentToken(1)`, not our
`NonexistentToken()`. What must match is the **set of red names**, not the assertion prose — that
wording varies with the forge-std version. If instead you get a compiler error, fix the compile
error before continuing; a plan step that predicts a red test cannot be satisfied by a build break.

- [ ] **Step 3: Widen the renderer import so `CardData` is in scope.**

```bash
cd /Library/Vibes/list-record && rg -n "IListRecordRenderer.sol" src/ListRecord.sol
```

Expected, from Task 3:

```
import {IListRecordRenderer} from "./interfaces/IListRecordRenderer.sol";
```

Replace that line with:

```solidity
import {CardData, IListRecordRenderer} from "./interfaces/IListRecordRenderer.sol";
```

- [ ] **Step 4: Implement `tokenURI`.**

Add this to `/Library/Vibes/list-record/src/ListRecord.sol`, immediately after `isSealed`.

```solidity
    /// @notice Metadata for one record.
    /// @dev An UNSEALED token reads the game live, so a wallet that keeps depositing sees its own
    ///      token rise rather than go stale.  A SEALED token reads its own storage and never
    ///      touches the game again -- not even if the game starts answering differently.
    ///
    ///      Membership and the join hour ALWAYS come from firstHourOf().  The game's raw
    ///      contributors() getter returns firstHour + 1 with 0 meaning "never deposited", so
    ///      reading that instead renders every non-member as an hour-0 founder.  It is not on
    ///      IWhitelistCurator and must never be added.
    function tokenURI(uint256 id) public view override returns (string memory) {
        address holder = _ownerOf(id);
        if (holder == address(0)) revert NonexistentToken();

        address who = claimantOf[id];
        SealedRecord memory s = sealedOf[id];

        CardData memory d;
        d.id = id;
        d.claimant = who;
        d.owner = holder;

        if (s.sealedAt != 0) {
            d.points = s.points;
            d.weightWei = s.weightWei;
            d.creditWei = s.creditWei;
            d.deposits = s.deposits;
            d.hour = s.hour;
            d.status = 2; // sealed
        } else {
            (uint256 h,) = LIST.firstHourOf(who);
            d.points = LIST.pointsOf(who);
            d.weightWei = LIST.weightOf(who);
            d.creditWei = LIST.contributedBy(who);
            d.deposits = LIST.txCountOf(who);
            d.hour = h;
            d.status = LIST.isSettled() ? 1 : 0; // settled : live
        }

        d.grace = d.hour < graceHours;

        return renderer.tokenURI(d);
    }
```

Two things to understand:

1. `_ownerOf(id)` is OpenZeppelin's internal lookup returning `address(0)` for an unminted token.
   The public `ownerOf(id)` reverts with OZ's own `ERC721NonexistentToken`, so we use the internal
   one and raise ours.
2. `status` is the *token's* status; `grace` is the *wallet's* join window. They are unrelated, and
   a card showing only `grace` on a finished game would never mention the game was over.

- [ ] **Step 5: Run the tests and watch them pass.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract TokenURISourcing -vvv
```

Expected: `Suite result: ok. 4 passed; 0 failed; 0 skipped`.

- [ ] **Step 6: Prove the "unsealed tracks the game" test bites.**

In `src/ListRecord.sol`, change the branch condition:

```solidity
        if (true) {          // MUTATION -- was: if (s.sealedAt != 0)
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TokenURISourcing
```

Every token now reads the all-zero `SealedRecord`, so an unsealed token stops moving. Expect exactly
one failure:

```
[FAIL: an unsealed token must follow the game] test_an_unsealed_token_tracks_the_game()
[PASS] test_a_sealed_token_ignores_the_game()
```

Restore by editing the line back to `if (s.sealedAt != 0) {` — **not** with `git checkout`, because
this file also carries the uncommitted implementation from Step 4. Re-run to confirm 4 passed.

- [ ] **Step 7: Prove the "sealed ignores the game" test bites.**

Same line, the opposite mutation:

```solidity
        if (false) {         // MUTATION -- was: if (s.sealedAt != 0)
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TokenURISourcing
```

Expect exactly one failure, the mirror of the last:

```
[FAIL: a sealed token must not move] test_a_sealed_token_ignores_the_game()
[PASS] test_an_unsealed_token_tracks_the_game()
```

Restore by hand to `if (s.sealedAt != 0) {` and re-run to confirm 4 passed.

- [ ] **Step 8: Run the whole suite.**

```bash
cd /Library/Vibes/list-record && forge test
```

Expected: **48 tests passed, 0 failed**. The arithmetic is
`7 (Interface.t.sol) + 7 (Claim.t.sol) + 9 (Seal.t.sol) + 6 (Announce.t.sol) + 6 (Template.t.sol)
+ 9 (Renderer.t.sol) = 44` from Tasks 1–7, plus 4 from `TokenURISourcing`. The summary line reads
`Ran 7 test suites ...: 48 tests passed, 0 failed, 0 skipped (48 total tests)`. If an addend has
moved because an earlier task changed its count, correct the addend here rather than accepting a
different total — the point of naming them is that a silently uncollected test is visible.

- [ ] **Step 9: Commit.**

```bash
cd /Library/Vibes/list-record
git add src/ListRecord.sol test/Traits.t.sol
git commit -m "feat: tokenURI reads the game live until sealed, then reads the token"
```

---

### Task 9: The ten traits — every one, exactly once, with the right JSON type

`tokenURI` returns a `data:application/json;base64,` URI whose JSON carries an `attributes` array of
exactly ten trait objects. A marketplace renders that array as the filterable list beside the
picture, and it is the only machine-readable description this collection will ever have — the
renderer is immutable, so whatever ships is permanent.

Two rules from the specification, both non-negotiable:

- **A number is unquoted, a string is quoted.** A marketplace uses the JSON type to choose between a
  numeric filter and a categorical one, so the quoting is part of the contract, not formatting.
- **There are exactly ten, and no eleventh.** The design excludes a multiplier band, a rank, a
  points-share and any linkage flag (spec §5.1, §9.2, §9.3). A test that only checked the ten it
  knows about would let an eleventh slip in, so the count is asserted positively.

One Foundry limitation to know first: **`vm.parseJson` cannot ABI-encode a non-integer JSON number.**
Selecting `.attributes[1].value` where the value is `902.1012` fails with
`vm.parseJson: unsupported JSON number: 902.1012`. This is a cheatcode limitation, not a JSON
problem — marketplaces parse it fine. So `Weight (ETH)` and `Credit (ETH)` are pinned on the raw
object text instead, which pins the *absence of the quotes* at the same time and is a stronger
assertion, not a weaker one. Verified on forge 1.5.1-stable.

**No thousands separators, frozen here (ruling R21).** Integers render as plain digits: `44721`,
never `44,721`. The decisive reason is not byte cost — it is that `"value":36,924` **is not valid
JSON at all**, so a separator would need a second helper and a second slot to keep the picture and
the metadata apart. Weight and credit render as wei to exactly four decimal places, truncated, never
rounded, zero-padded: `902.1012`, `461.1000`, `0.0500`.

**Trait order is fixed** and the tests read by index, so order is pinned by construction. For the
`MEMBER` token:

| index | `trait_type` | JSON type | value |
|---|---|---|---|
| 0 | `Points` | number | `30035` |
| 1 | `Weight (ETH)` | number | `902.1012` |
| 2 | `Credit (ETH)` | number | `461.1000` |
| 3 | `Deposits` | number | `2` |
| 4 | `Hour` | string | `"hour 1"` |
| 5 | `Window` | string | `"grace"` |
| 6 | `Claim Order` | number | `1` |
| 7 | `Status` | string | `"live"` |
| 8 | `Claimant` | string | `"0x381fe486d87c7f2633c777f1b5be3105a2a51744"` (42 chars, lowercase) |
| 9 | `Held by claimant` | string | `"yes"` |

#### Files

- **modify:** `/Library/Vibes/list-record/test/Traits.t.sol` (append; Task 8 created it)

No production file changes. The renderer (Task 7) and `tokenURI` (Task 8) already exist; this task
makes their output permanent.

#### Interfaces

**Consumes:** `claim()`, `sealRecord(uint256)`, `tokenURI(uint256)` and ERC-721's
`transferFrom(address,address,uint256)` on `src/ListRecord.sol` (Tasks 3–5 and 8); `setMember(...)`
and `setSettled(bool)` on `test/mocks/MockList.sol` (Task 2); `stdJson.readUint` /
`stdJson.readString` from forge-std.

**Produces**, test-local in `test/Traits.t.sol`: `library B64`, `contract B64SelfTest`,
`contract TraitsTest`.

---

- [ ] **Step 1: Add a base64 decoder to the test file.**

Foundry ships `vm.toBase64` but has no *decode* cheatcode. Append this library to
`/Library/Vibes/list-record/test/Traits.t.sol` directly under the existing `import` lines and above
`contract TokenURISourcing`, and add `import {stdJson} from "forge-std/StdJson.sol";` to the import
block while you are there.

```solidity
/// @dev Test-only base64 decoder.  Foundry has vm.toBase64 but no decode cheatcode, and the whole
///      point of these assertions is to read exactly what a marketplace would read.
library B64 {
    function decode(string memory s) internal pure returns (bytes memory) {
        bytes memory d = bytes(s);
        require(d.length % 4 == 0 && d.length > 0, "b64 length");
        uint256 pad;
        if (d[d.length - 1] == "=") pad++;
        if (d[d.length - 2] == "=") pad++;
        bytes memory out = new bytes((d.length / 4) * 3 - pad);
        uint256 o;
        for (uint256 i; i < d.length; i += 4) {
            uint256 n = (_v(d[i]) << 18) | (_v(d[i + 1]) << 12) | (_v(d[i + 2]) << 6) | _v(d[i + 3]);
            out[o++] = bytes1(uint8(n >> 16));
            if (o < out.length) out[o++] = bytes1(uint8(n >> 8));
            if (o < out.length) out[o++] = bytes1(uint8(n));
        }
        return out;
    }

    function _v(bytes1 c) private pure returns (uint256) {
        uint8 x = uint8(c);
        if (x >= 65 && x <= 90) return x - 65;   // A-Z
        if (x >= 97 && x <= 122) return x - 71;  // a-z
        if (x >= 48 && x <= 57) return x + 4;    // 0-9
        if (x == 43) return 62;                  // +
        if (x == 47) return 63;                  // /
        if (x == 61) return 0;                   // = padding
        revert("b64 char");
    }
}
```

- [ ] **Step 2: Prove the decoder before you trust it.**

Append this contract to the end of the same file:

```solidity
contract B64SelfTest is Test {
    function test_the_decoder_round_trips_including_non_ascii() public pure {
        // the card carries a middle dot (U+00B7) and an ellipsis (U+2026)
        string memory s = unicode'{"a":1,"b":"0x381f…8ef2 · held by claimant"}';
        assertEq(string(B64.decode(vm.toBase64(s))), s);
    }
}
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract B64SelfTest -vvv
```

Expected `[PASS] test_the_decoder_round_trips_including_non_ascii()`. If this fails the decoder is
wrong and every assertion built on it is meaningless — fix it here.

- [ ] **Step 3: Add the traits test contract.**

Append this to the end of `/Library/Vibes/list-record/test/Traits.t.sol`.

```solidity
contract TraitsTest is Test {
    using stdJson for string;

    MockList internal list;
    ListRecordRenderer internal renderer;
    ListRecord internal record;

    // REAL, captured -- see the provenance table in Task 8.
    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;
    // SYNTHETIC and labelled: the widest card the contract's constants permit.  creditCap is
    // 1000 ETH and the constructor proves max weight is 2 * creditCap, so 2000 ETH is the true
    // weight maximum and curve(2000e18) == 44721.  Deposits 9999 and hour 999 have no contract
    // bound and are chosen upper bounds.  The address is invented.
    address internal constant CEILING = address(0xCE11);
    // SYNTHETIC and labelled: the committed sweep stops at hour 23, so no judged-hour wallet was
    // ever captured.  Built from contract constants: minDeposit 0.05 ETH in a judged hour, where
    // the early multiplier is flat 1x, so weight == credit and the curve returns exactly 223.
    address internal constant JUDGED = address(0xF100);
    address internal constant BOB = address(0xB0B);

    function setUp() public {
        list = new MockList();
        list.setMember(MEMBER, 1, 30_035, 902_101_225_000_000_000_000, 461.1 ether, 2);
        list.setMember(CEILING, 999, 44_721, 2_000 ether, 1_000 ether, 9_999);
        list.setMember(JUDGED, 30, 223, 0.05 ether, 0.05 ether, 1);

        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        renderer = new ListRecordRenderer(blob, _offsets());
        record = new ListRecord(address(list), address(renderer));

        vm.prank(MEMBER);
        record.claim(); // token 1
        vm.prank(CEILING);
        record.claim(); // token 2
        vm.prank(JUDGED);
        record.claim(); // token 3
    }

    /// @dev Same parser as TokenURISourcing._offsets, byte for byte -- one line of 50
    ///      comma-separated integers (ruling R1).
    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    /*//////////////////////////////////////////////////////////////
                                 HELPERS
    //////////////////////////////////////////////////////////////*/

    /// @dev tokenURI -> strip `data:application/json;base64,` (29 bytes) -> decode -> JSON text.
    function _json(uint256 id) internal view returns (string memory) {
        bytes memory uri = bytes(record.tokenURI(id));
        bytes memory pre = bytes("data:application/json;base64,");
        require(uri.length > pre.length, "uri too short");
        for (uint256 i; i < pre.length; i++) require(uri[i] == pre[i], "wrong uri prefix");
        bytes memory b64 = new bytes(uri.length - pre.length);
        for (uint256 i; i < b64.length; i++) b64[i] = uri[i + pre.length];
        return string(B64.decode(string(b64)));
    }

    function _contains(string memory hay, string memory nee) internal pure returns (bool) {
        bytes memory h = bytes(hay);
        bytes memory n = bytes(nee);
        if (n.length == 0 || n.length > h.length) return false;
        for (uint256 i; i + n.length <= h.length; i++) {
            bool m = true;
            for (uint256 j; j < n.length; j++) {
                if (h[i + j] != n[j]) { m = false; break; }
            }
            if (m) return true;
        }
        return false;
    }

    function _count(string memory hay, string memory nee) internal pure returns (uint256 c) {
        bytes memory h = bytes(hay);
        bytes memory n = bytes(nee);
        if (n.length == 0 || n.length > h.length) return 0;
        for (uint256 i; i + n.length <= h.length; i++) {
            bool m = true;
            for (uint256 j; j < n.length; j++) {
                if (h[i + j] != n[j]) { m = false; break; }
            }
            if (m) c++;
        }
    }

    /// @dev Asserts trait `i` is EXACTLY {"trait_type":"<name>","value":<raw>}.  `raw` carries its
    ///      own quoting, so this pins the JSON TYPE as well as the value; re-reading trait_type
    ///      through stdJson pins the ORDER.
    function _trait(string memory j, uint256 i, string memory name, string memory raw)
        internal
        pure
    {
        assertEq(
            j.readString(string.concat(".attributes[", vm.toString(i), "].trait_type")),
            name,
            "trait order"
        );
        assertTrue(
            _contains(j, string.concat('{"trait_type":"', name, '","value":', raw, "}")),
            name
        );
    }

    /*//////////////////////////////////////////////////////////////
                              THE TEN TRAITS
    //////////////////////////////////////////////////////////////*/

    function test_the_ten_traits_while_the_game_runs() public view {
        string memory j = _json(1);

        _trait(j, 0, "Points", "30035");
        _trait(j, 1, "Weight (ETH)", "902.1012");
        _trait(j, 2, "Credit (ETH)", "461.1000");
        _trait(j, 3, "Deposits", "2");
        _trait(j, 4, "Hour", '"hour 1"');
        _trait(j, 5, "Window", '"grace"');
        _trait(j, 6, "Claim Order", "1");
        _trait(j, 7, "Status", '"live"');
        _trait(j, 8, "Claimant", '"0x381fe486d87c7f2633c777f1b5be3105a2a51744"');
        _trait(j, 9, "Held by claimant", '"yes"');

        // the integer-valued ones, read back through stdJson rather than matched as text
        assertEq(j.readUint(".attributes[0].value"), 30_035);
        assertEq(j.readUint(".attributes[3].value"), 2);
        assertEq(j.readUint(".attributes[6].value"), 1);
        assertEq(j.readString(".attributes[4].value"), "hour 1");
        assertEq(j.readString(".attributes[5].value"), "grace");
        assertEq(j.readString(".attributes[7].value"), "live");
        assertEq(
            j.readString(".attributes[8].value"), "0x381fe486d87c7f2633c777f1b5be3105a2a51744"
        );
        assertEq(j.readString(".attributes[9].value"), "yes");

        assertEq(j.readString(".name"), "THE LIST #1");
    }

    function test_the_ten_traits_once_the_game_has_settled() public {
        list.setSettled(true);
        string memory j = _json(1);

        // every wallet number is frozen by the chain, so only Status moves
        _trait(j, 0, "Points", "30035");
        _trait(j, 7, "Status", '"settled"');
        assertEq(j.readString(".attributes[7].value"), "settled");
    }

    function test_the_ten_traits_once_the_holder_has_sealed() public {
        list.setSettled(true);
        vm.prank(MEMBER);
        record.sealRecord(1);

        string memory j = _json(1);

        _trait(j, 0, "Points", "30035");
        _trait(j, 1, "Weight (ETH)", "902.1012");
        _trait(j, 2, "Credit (ETH)", "461.1000");
        _trait(j, 3, "Deposits", "2");
        _trait(j, 4, "Hour", '"hour 1"');
        _trait(j, 5, "Window", '"grace"');
        _trait(j, 6, "Claim Order", "1");
        _trait(j, 7, "Status", '"sealed"');
        _trait(j, 8, "Claimant", '"0x381fe486d87c7f2633c777f1b5be3105a2a51744"');
        _trait(j, 9, "Held by claimant", '"yes"');
    }

    /// @dev The Window trait is the WALLET's join window and has nothing to do with Status.  This
    ///      is the synthetic judged row: hour 30, minDeposit 0.05 ETH, 223 points.
    function test_the_window_trait_says_judged_for_a_wallet_that_joined_after_grace() public view {
        string memory j = _json(3);
        _trait(j, 4, "Hour", '"hour 30"');
        _trait(j, 5, "Window", '"judged"');
        _trait(j, 0, "Points", "223");
        _trait(j, 1, "Weight (ETH)", "0.0500");
        _trait(j, 2, "Credit (ETH)", "0.0500");
        assertEq(j.readString(".attributes[5].value"), "judged");
    }

    /*//////////////////////////////////////////////////////////////
                             THE THREE-WAY PIN
    //////////////////////////////////////////////////////////////*/

    /// @dev The honesty case the design exists for: a grace-joined wallet on a FINISHED game with
    ///      an UNSEALED token used to render `grace` and `live` and never mention the game was
    ///      over.  Window is the wallet's join window; Status is the token's.
    function test_status_says_settled_not_live_once_the_game_is_over() public {
        assertEq(_json(1).readString(".attributes[7].value"), "live");

        list.setSettled(true);
        assertEq(_json(1).readString(".attributes[7].value"), "settled");
        // and Window has NOT moved -- a different fact about a different subject
        assertEq(_json(1).readString(".attributes[5].value"), "grace");

        vm.prank(MEMBER);
        record.sealRecord(1);
        assertEq(_json(1).readString(".attributes[7].value"), "sealed");
    }

    function test_held_by_claimant_goes_no_after_a_transfer() public {
        assertEq(_json(1).readString(".attributes[9].value"), "yes");
        vm.prank(MEMBER);
        record.transferFrom(MEMBER, BOB, 1);
        assertEq(_json(1).readString(".attributes[9].value"), "no");
        // Claimant describes the wallet that claimed, not whoever holds it now
        assertEq(
            _json(1).readString(".attributes[8].value"),
            "0x381fe486d87c7f2633c777f1b5be3105a2a51744"
        );
    }

    /*//////////////////////////////////////////////////////////////
                          NO ELEVENTH TRAIT, EVER
    //////////////////////////////////////////////////////////////*/

    /// @dev A positive count, so an added trait fails here rather than passing unnoticed.
    function test_exactly_ten_traits_in_every_state() public {
        assertEq(_count(_json(1), '"trait_type":'), 10, "live");

        list.setSettled(true);
        assertEq(_count(_json(1), '"trait_type":'), 10, "settled");

        vm.prank(MEMBER);
        record.sealRecord(1);
        assertEq(_count(_json(1), '"trait_type":'), 10, "sealed");
    }

    /// @dev Weight and Credit cannot be read through stdJson at all: vm.parseJson rejects a
    ///      non-integer JSON number.  They are pinned on the raw object instead, which pins the
    ///      absence of the quotes with them.
    function test_the_two_eth_traits_are_unquoted_json_numbers() public view {
        string memory j = _json(1);
        assertTrue(_contains(j, '{"trait_type":"Weight (ETH)","value":902.1012}'), "weight");
        assertTrue(_contains(j, '{"trait_type":"Credit (ETH)","value":461.1000}'), "credit");
        assertFalse(_contains(j, '"value":"902.1012"'), "weight must not be a string");
        assertFalse(_contains(j, '"value":"461.1000"'), "credit must not be a string");
    }

    /// @dev No thousands separator anywhere.  A comma inside an unquoted JSON number is not valid
    ///      JSON, and the same bytes are spliced into the picture and the metadata.  Token 2 is
    ///      the ceiling row -- the only one whose numbers are large enough for a separator to be
    ///      possible at all.
    function test_numbers_carry_no_thousands_separator() public view {
        string memory j = _json(2);
        assertFalse(_contains(j, "44,721"), "points");
        assertFalse(_contains(j, "2,000"), "weight");
        assertFalse(_contains(j, "1,000"), "credit");
        assertFalse(_contains(j, "9,999"), "deposits");
        assertTrue(_contains(j, '"value":44721'), "points render as plain digits");
        assertTrue(_contains(j, '"value":2000.0000'), "weight renders as plain digits");
    }
}
```

- [ ] **Step 4: Run them against the current renderer and record what is already green.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest -vvv
```

The renderer and `tokenURI` already exist, so this is a **real first run whose result you must
read**, not a formality. Expected: `Suite result: ok. 9 passed; 0 failed; 0 skipped`.

If a value differs, the table at the head of this task is the specification and the divergence is a
real finding — reconcile it with Task 7 before continuing rather than editing the expectation. The
most likely divergences and what they mean:

- `902.1013` instead of `902.1012` → the formatter rounds; the spec says truncate.
- `0.05` instead of `0.0500` → the formatter does not zero-pad the fraction.
- `461.1` read as a *string* → the trait is quoted and the marketplace will offer a categorical
  filter instead of a range slider.

Because all nine pass, "watch it fail" is provided by the seven mutations below, each applied
**before** this task commits anything. Every one is exact and executable as written.

- [ ] **Step 5: Mutation 1 — the eleventh trait.**

The generator builds the metadata envelope as one string concatenation, so there is no "list of
trait objects" to edit. Add this **one line immediately after the `ENVELOPE = (...)` assignment** in
`/Library/Vibes/list-record/tools/gen_template.py` — it is shape-agnostic and works whether the
constant was written as one literal, a parenthesised concatenation or a triple-quoted string:

```python
ENVELOPE = ENVELOPE.replace('{"trait_type":"Held by claimant"', '{"trait_type":"Multiplier Band","value":"steep"},{"trait_type":"Held by claimant"')  # MUTATION
```

```bash
cd /Library/Vibes/list-record && python3 tools/gen_template.py && forge test --match-contract TraitsTest
```

Expected exactly one failure:

```
[FAIL: live: 11 != 10] test_exactly_ten_traits_in_every_state()
```

Delete the mutation line and re-run `python3 tools/gen_template.py`, then re-run the tests to
confirm 9 passed. **Do not `git checkout` `template/`** — regenerating is what keeps the blob and
the offsets consistent with each other.

- [ ] **Step 6: Mutation 2 — the three-way status.**

In `/Library/Vibes/list-record/src/ListRecordRenderer.sol`, find the line that builds the status
word and collapse it to two states, keeping the variable name so `v[12] = status;` and
`v[21] = status;` still compile:

```solidity
        // MUTATION -- was:
        // bytes memory status = d.status == 2 ? bytes("sealed") : d.status == 1 ? bytes("settled") : bytes("live");
        bytes memory status = d.status == 2 ? bytes("sealed") : bytes("live");
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Expected exactly two failures, and nothing else:

```
[FAIL: Status] test_the_ten_traits_once_the_game_has_settled()
[FAIL: assertion failed] test_status_says_settled_not_live_once_the_game_is_over()
```

Restore with `git checkout -- src/ListRecordRenderer.sol` — allowed here because that file is
committed by Task 7 and carries no uncommitted work of ours. Re-run to confirm 9 passed.

- [ ] **Step 7: Mutation 3 — held by claimant.**

In `src/ListRecord.sol`'s `tokenURI`, make the owner always the claimant:

```solidity
        d.owner = who;       // MUTATION -- was: d.owner = holder;
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Expected exactly one failure:

```
[FAIL: assertion failed: yes != no] test_held_by_claimant_goes_no_after_a_transfer()
```

Restore with `git checkout -- src/ListRecord.sol` (committed at the end of Task 8) and re-run.

- [ ] **Step 8: Mutation 4 — the sealed path really reads storage.**

In `src/ListRecord.sol`'s sealed branch:

```solidity
            d.deposits = 0;          // MUTATION -- was: d.deposits = s.deposits;
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Expected exactly one failure:

```
[FAIL: Deposits] test_the_ten_traits_once_the_holder_has_sealed()
```

Restore with `git checkout -- src/ListRecord.sol` and re-run.

- [ ] **Step 9: Mutation 5 — credit really comes from `contributedBy`.**

In `src/ListRecord.sol`'s live branch:

```solidity
            d.creditWei = LIST.weightOf(who);   // MUTATION -- was: LIST.contributedBy(who)
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Credit now renders `902.1012` instead of `461.1000`. Expected exactly two failures:

```
[FAIL: Credit (ETH)] test_the_ten_traits_while_the_game_runs()
[FAIL: credit] test_the_two_eth_traits_are_unquoted_json_numbers()
```

`test_the_ten_traits_once_the_holder_has_sealed` stays green, which is itself informative: the
sealed path never touches the game. Restore with `git checkout -- src/ListRecord.sol`.

- [ ] **Step 10: Mutation 6 — points really come from `pointsOf`.**

In `src/ListRecord.sol`'s live branch:

```solidity
            d.points = LIST.txCountOf(who);     // MUTATION -- was: LIST.pointsOf(who)
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Expected exactly two failures — note the second is the separator test's *positive* half, which is
what wires that test to production rather than to itself:

```
[FAIL: Points] test_the_ten_traits_while_the_game_runs()
[FAIL: points render as plain digits] test_numbers_carry_no_thousands_separator()
```

Restore with `git checkout -- src/ListRecord.sol`.

- [ ] **Step 11: Mutation 7 — the grace boundary.**

In `src/ListRecord.sol`:

```solidity
        d.grace = true;      // MUTATION -- was: d.grace = d.hour < graceHours;
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract TraitsTest
```

Expected exactly one failure — the judged row now claims the grace window:

```
[FAIL: Window] test_the_window_trait_says_judged_for_a_wallet_that_joined_after_grace()
```

Restore with `git checkout -- src/ListRecord.sol` and re-run to confirm 9 passed.

- [ ] **Step 12: Run the whole file, then the whole suite.**

```bash
cd /Library/Vibes/list-record && forge test --match-path test/Traits.t.sol && forge test
```

Expected from the file:

```
Suite result: ok. 4 passed; 0 failed; 0 skipped   (TokenURISourcing)
Suite result: ok. 1 passed; 0 failed; 0 skipped   (B64SelfTest)
Suite result: ok. 9 passed; 0 failed; 0 skipped   (TraitsTest)
```

Expected from the suite: **58 tests passed, 0 failed** — 48 after Task 8, plus 1 (`B64SelfTest`) and
9 (`TraitsTest`). Also confirm `git status --short` shows only `test/Traits.t.sol` modified: if
`src/` or `template/` is dirty, a mutation was not restored.

- [ ] **Step 13: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/Traits.t.sol
git commit -m "test: pin all ten traits, their JSON types, and that there is no eleventh"
```

---

### Task 10: The language gate, the description, and one truthfulness test

**The language gate.** The dashboard this collection grew out of has a strict rule about the words
it renders: a cluster analysis is revisable, so nothing that reads as an accusation may reach a
user-visible surface. In the dashboard that rule is enforced at *runtime*, because every string
passes through a translation boundary on the way to the screen. Here the position is much stronger.
About 95% of the metadata payload is a single constant blob compiled into the deploy transaction,
and every variable slot is one of: decimal digits, a lowercase hex address, or a value from a small
closed vocabulary. So **the forbidden-word scan is a one-time check of a constant, not a runtime
screen** (spec §6.3) — there is no string in this system whose content is not already known at build
time. Four tests make that argument checkable rather than merely stated:

1. the blob contains none of the seven words, case-insensitively;
2. the blob's percent-encoding can never *hide* a letter — the template is stored already
   percent-encoded, so `%73ybil` would defeat a naive literal scan;
3. no variable slot can produce one either — the closed vocabularies are scanned;
4. no forbidden word is spellable from the sixteen hex digits, so no address can ever spell one.

**The description (spec §10 item 3, D10, §4).** Two further tests, on the **rendered** JSON rather
than the blob, because that is what a marketplace actually reads: the description must not mention
the certification overlay, and it must state the marketplace-caching limitation. Both are stated
requirements, and an untested requirement is a wish. This task fixes the contract Task 6's
`DESCRIPTION` must satisfy:

- it must **not** contain, case-insensitively, the substring `certif`;
- it must contain the substring `marketplaces cache`.

**What this task does NOT do.** `supportsInterface` and `_update` are implemented **once, in Task
5**, with the OZ v5 signature `function supportsInterface(bytes4 interfaceId) public view virtual
override(ERC721, IERC165) returns (bool)`. OZ 5.6.1's `IERC4906 is IERC165, IERC721`, so any other
form fails to compile with `Error (4327): Function needs to specify overridden contracts "ERC721"
and "IERC165"`. Task 5 also already tests that the interface id is advertised, that a transfer emits
`MetadataUpdate`, and that a mint does not. **Nothing here redeclares either function and nothing
here repeats those three tests.** What is added is the one thing none of them covers: that the
refresh is *truthful* — that the metadata a marketplace re-reads after the event really has changed.

#### Files

- **modify:** `/Library/Vibes/list-record/test/Template.t.sol` — **append** a second contract,
  `LanguageGate`. Task 6 owns the first contract in this file; do not edit it.
- **modify:** `/Library/Vibes/list-record/test/Announce.t.sol` — **append** a second contract,
  `MetadataRefresh`. Task 5 owns the first contract in this file; do not edit it.

No production file is modified by this task.

#### Interfaces

**Consumes:** `claim()`, `tokenURI(uint256)`, `transferFrom(...)` and the inherited ERC-4906
`MetadataUpdate` event on `src/ListRecord.sol` (Tasks 3–5, 8); `ListRecordRenderer` (Task 7);
`MockList.setMember(...)` (Task 2); `template/blob.hex` and `template/offsets.txt` (Task 6);
`library B64` from `test/Traits.t.sol` (Task 9).

---

- [ ] **Step 1: Confirm Task 5's ERC-4906 work is present and green.**

```bash
cd /Library/Vibes/list-record
rg -n "supportsInterface|function _update|IERC4906" src/ListRecord.sol
forge test --match-path test/Announce.t.sol
```

Expected: `supportsInterface` declared exactly once with `override(ERC721, IERC165)`, `_update`
declared exactly once, `IERC4906` imported and inherited — and `6 passed; 0 failed`. If
`supportsInterface` appears twice, or with a bare `override`, that is a build-stopping duplication
from an earlier task; fix it there, not here.

- [ ] **Step 2: Write the language gate.**

Append this to the end of `/Library/Vibes/list-record/test/Template.t.sol`. Add any of these imports
that the file does not already have, at the top:

```solidity
import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {MockList} from "./mocks/MockList.sol";
import {B64} from "./Traits.t.sol";
```

```solidity
/// @notice The forbidden-word scan and the description contract.  Because ~95% of the payload is a
///         constant blob and every variable slot is digits, a hex address or a closed enum, tests
///         1-4 are a ONE-TIME check of a constant rather than a runtime screen -- a stronger
///         position, not a weaker one (spec 6.3).  Tests 5-6 read the RENDERED description,
///         because that is the string a marketplace actually shows.
contract LanguageGate is Test {
    using stdJson for string;

    MockList internal list;
    ListRecordRenderer internal renderer;
    ListRecord internal record;

    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;

    function setUp() public {
        list = new MockList();
        list.setMember(MEMBER, 1, 30_035, 902_101_225_000_000_000_000, 461.1 ether, 2);
        renderer = new ListRecordRenderer(_blob(), _offsets());
        record = new ListRecord(address(list), address(renderer));
        vm.prank(MEMBER);
        record.claim(); // token 1
    }

    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function _blob() internal view returns (bytes memory) {
        return vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
    }

    function _description() internal view returns (string memory) {
        bytes memory uri = bytes(record.tokenURI(1));
        bytes memory pre = bytes("data:application/json;base64,");
        bytes memory b64 = new bytes(uri.length - pre.length);
        for (uint256 i; i < b64.length; i++) b64[i] = uri[i + pre.length];
        return string(B64.decode(string(b64))).readString(".description");
    }

    function _forbidden() internal pure returns (string[7] memory w) {
        w[0] = "sybil";
        w[1] = "cheat";
        w[2] = "fraud";
        w[3] = "attack";
        w[4] = "abuse";
        w[5] = "farmer";
        w[6] = "wash";
    }

    function _lower(bytes memory b) internal pure returns (bytes memory out) {
        out = new bytes(b.length);
        for (uint256 i; i < b.length; i++) {
            uint8 c = uint8(b[i]);
            out[i] = bytes1(c >= 0x41 && c <= 0x5A ? c + 32 : c);
        }
    }

    function _contains(bytes memory h, bytes memory n) internal pure returns (bool) {
        if (n.length == 0 || n.length > h.length) return false;
        for (uint256 i; i + n.length <= h.length; i++) {
            bool m = true;
            for (uint256 j; j < n.length; j++) {
                if (h[i + j] != n[j]) { m = false; break; }
            }
            if (m) return true;
        }
        return false;
    }

    function _nibble(bytes1 c) internal pure returns (uint8) {
        uint8 x = uint8(c);
        if (x >= 48 && x <= 57) return x - 48;   // 0-9
        if (x >= 97 && x <= 102) return x - 87;  // a-f
        if (x >= 65 && x <= 70) return x - 55;   // A-F
        revert("template: `%` not followed by two hex digits");
    }

    /// @dev The whole constant, case-insensitively.
    function test_the_template_speaks_no_forbidden_word() public view {
        bytes memory hay = _lower(_blob());
        string[7] memory w = _forbidden();
        for (uint256 i; i < 7; i++) {
            assertFalse(_contains(hay, bytes(w[i])), w[i]);
        }
    }

    /// @dev The template is stored ALREADY percent-encoded, so a naive scan would miss `%73ybil`.
    ///      The encoding set is `%`, `#`, `"`, `&`, space, `<`, `>`, `?` and every byte >= 0x80 --
    ///      letters are never in it.  Proving that is what makes the literal scan above complete.
    function test_the_percent_encoding_can_never_hide_a_letter() public view {
        bytes memory b = _blob();
        for (uint256 i; i + 2 < b.length; i++) {
            if (b[i] != "%") continue;
            uint8 v = _nibble(b[i + 1]) * 16 + _nibble(b[i + 2]);
            assertFalse(
                (v >= 0x41 && v <= 0x5A) || (v >= 0x61 && v <= 0x7A),
                "template hides a letter behind a percent escape"
            );
        }
    }

    /// @dev The other 5%: every variable slot is decimal digits, a lowercase hex address, or a
    ///      value from one of these closed vocabularies.  Scanning them closes the runtime side.
    function test_no_runtime_value_can_smuggle_a_word_in() public pure {
        string[11] memory closed;
        closed[0] = "grace";
        closed[1] = "judged";
        closed[2] = "live";
        closed[3] = "settled";
        closed[4] = "sealed";
        closed[5] = "hour ";
        closed[6] = "hour%20";
        closed[7] = "held by claimant";
        closed[8] = "held by another";
        closed[9] = "yes";
        closed[10] = "no";

        string[7] memory w = _forbidden();
        for (uint256 i; i < 11; i++) {
            bytes memory hay = _lower(bytes(closed[i]));
            for (uint256 k; k < 7; k++) {
                assertFalse(_contains(hay, bytes(w[k])), closed[i]);
            }
        }
    }

    /// @dev And no address can spell one: none of the seven words is writable using only the
    ///      sixteen hex digits.  If someone ever adds a word that is (`deface`, say), this test
    ///      fails and tells them the address slot now needs a runtime screen after all.
    function test_no_forbidden_word_is_spellable_from_a_hex_address() public pure {
        bytes memory hexset = bytes("0123456789abcdef");
        string[7] memory w = _forbidden();
        for (uint256 i; i < 7; i++) {
            bytes memory word = bytes(w[i]);
            bool allHex = true;
            for (uint256 j; j < word.length; j++) {
                bool inSet;
                for (uint256 k; k < hexset.length; k++) {
                    if (word[j] == hexset[k]) inSet = true;
                }
                if (!inSet) { allHex = false; break; }
            }
            assertFalse(allHex, w[i]);
        }
    }

    /// @dev D10: the shipped text says nothing about a certification layer that may never exist.
    function test_the_rendered_description_names_no_certification() public view {
        assertFalse(_contains(_lower(bytes(_description())), bytes("certif")), "certification");
    }

    /// @dev Spec 4: marketplace caching is the one honest limitation, and the description states
    ///      it rather than letting a holder discover it.
    function test_the_rendered_description_states_the_marketplace_caching_limit() public view {
        assertTrue(
            _contains(bytes(_description()), bytes("marketplaces cache")),
            "the description must state the caching limitation"
        );
    }
}
```

- [ ] **Step 3: Mutation 1 — a forbidden word in the constant.**

The template already exists and is already clean, so mutate it first. This patch is **byte-length
preserving** (`THE%20LIST` → `THE%20wash`, both 10 bytes), so the committed offsets still line up
and only the word changes:

```bash
cd /Library/Vibes/list-record
python3 - <<'PY'
import binascii, pathlib
p = pathlib.Path("template/blob.hex")
b = binascii.unhexlify(p.read_text().strip()[2:])
assert b.count(b"THE%20LIST") == 1, "expected one percent-encoded card title"
p.write_text("0x" + binascii.hexlify(b.replace(b"THE%20LIST", b"THE%20wash", 1)).decode())
PY
forge test --match-contract LanguageGate
```

Expected exactly one failure, naming the word it found:

```
[FAIL: wash] test_the_template_speaks_no_forbidden_word()
[PASS] test_no_forbidden_word_is_spellable_from_a_hex_address()
[PASS] test_no_runtime_value_can_smuggle_a_word_in()
[PASS] test_the_percent_encoding_can_never_hide_a_letter()
[PASS] test_the_rendered_description_names_no_certification()
[PASS] test_the_rendered_description_states_the_marketplace_caching_limit()
```

Restore by regenerating: `python3 tools/gen_template.py`.

- [ ] **Step 4: Mutation 2 — a letter hidden behind a percent escape.**

Also byte-length preserving: `%20` (a space) becomes `%61` (the letter `a`).

```bash
cd /Library/Vibes/list-record
python3 - <<'PY'
import binascii, pathlib
p = pathlib.Path("template/blob.hex")
b = binascii.unhexlify(p.read_text().strip()[2:])
assert b"%20" in b, "expected percent-encoded spaces in the SVG"
p.write_text("0x" + binascii.hexlify(b.replace(b"%20", b"%61", 1)).decode())
PY
forge test --match-contract LanguageGate
```

Expected exactly one failure:

```
[FAIL: template hides a letter behind a percent escape] test_the_percent_encoding_can_never_hide_a_letter()
```

Restore with `python3 tools/gen_template.py`.

- [ ] **Step 5: Mutation 3 — the closed vocabulary.**

The vocabulary *is* the input under test here, so perturb it. In `test/Template.t.sol`, inside
`test_no_runtime_value_can_smuggle_a_word_in`:

```solidity
        closed[1] = "wash trade";   // MUTATION -- was: closed[1] = "judged";
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract LanguageGate
```

Expected exactly one failure:

```
[FAIL: wash trade] test_no_runtime_value_can_smuggle_a_word_in()
```

Restore by editing the line back to `closed[1] = "judged";` — hand edit, because this file carries
this task's own uncommitted work.

- [ ] **Step 6: Mutation 4 — a hex-spellable forbidden word.**

In `_forbidden()`:

```solidity
        w[6] = "deface";   // MUTATION -- was: w[6] = "wash";
```

`deface` is writable with only the sixteen hex digits, so an address could spell it. Expected
exactly one failure — the other five stay green, which is the point: the blob does not contain
`deface` and neither does any closed vocabulary, so only the spellability test moves.

```bash
cd /Library/Vibes/list-record && forge test --match-contract LanguageGate
```

```
[FAIL: deface] test_no_forbidden_word_is_spellable_from_a_hex_address()
```

Restore by hand to `w[6] = "wash";`.

- [ ] **Step 7: Mutation 5 — a certification sentence in the description.**

Add this **one line immediately after the `DESCRIPTION = ...` assignment** in
`/Library/Vibes/list-record/tools/gen_template.py`. It is shape-agnostic: it works whatever form the
constant was written in.

```python
DESCRIPTION = DESCRIPTION + " Certified independent by the curator."  # MUTATION
```

```bash
cd /Library/Vibes/list-record && python3 tools/gen_template.py && forge test --match-contract LanguageGate
```

Expected exactly one failure:

```
[FAIL: certification] test_the_rendered_description_names_no_certification()
```

Delete the line, re-run `python3 tools/gen_template.py`.

- [ ] **Step 8: Mutation 6 — the caching limitation removed.**

Same place, same technique:

```python
DESCRIPTION = DESCRIPTION.replace("marketplaces cache", "listings update")  # MUTATION
```

```bash
cd /Library/Vibes/list-record && python3 tools/gen_template.py && forge test --match-contract LanguageGate
```

Expected exactly one failure:

```
[FAIL: the description must state the caching limitation] test_the_rendered_description_states_the_marketplace_caching_limit()
```

Delete the line and regenerate. If instead this mutation makes **no** test fail, `DESCRIPTION` never
contained the phrase: add the mandated sentence to it in `tools/gen_template.py` — *"Values are read
from the game contract at read time; marketplaces cache metadata, so a listing page may lag a live
token's numbers."* — regenerate, and re-run.

- [ ] **Step 9: Run the gate green.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract LanguageGate
```

Expected: `Suite result: ok. 6 passed; 0 failed; 0 skipped`.

- [ ] **Step 10: Scan BOTH contracts for an admin surface.**

Spec §3.1 says `ListRecord` has no owner and no admin function; §3.2 says `ListRecordRenderer` is
immutable with **no setter** — "no upgrade path and no way for anyone to change anybody's art". The
renderer is the contract the spec calls irreversible, so it is scanned too. It could not be scanned
by Task 5, which runs before Task 7 creates it; this is where the renderer half lands.

```bash
cd /Library/Vibes/list-record
rg -nE "Ownable|onlyOwner|payable|selfdestruct|delegatecall|receive\s*\(|fallback\s*\(|withdraw|pause|function set[A-Z]" src/ListRecord.sol src/ListRecordRenderer.sol ; echo "exit=$?"
```

Expected: no output and `exit=1` (ripgrep exits 1 when it matches nothing).

Now prove the scan bites. Add this to `src/ListRecordRenderer.sol`, inside the contract:

```solidity
    function setTemplate(address p) external { }   // MUTATION
```

Re-run the same command. Expected: one match, `exit=0`. Restore with
`git checkout -- src/ListRecordRenderer.sol`, re-run, and confirm `exit=1` again.

- [ ] **Step 11: Write the truthfulness test.**

Append this to the end of `/Library/Vibes/list-record/test/Announce.t.sol`, adding to the top of the
file any of these imports it does not already have:

```solidity
import {stdJson} from "forge-std/StdJson.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {B64} from "./Traits.t.sol";
```

```solidity
/// @notice ERC-4906 is how an OWNERLESS collection tells a marketplace to re-read a token.  Task 5
///         owns `supportsInterface` and `_update` and already tests that the interface id is
///         advertised, that a transfer emits, and that a mint does not.  This contract tests the
///         one thing none of those covers: that the refresh is TRUTHFUL -- that the metadata a
///         marketplace re-reads after the event really has changed.  Nothing here redeclares
///         either function.
contract MetadataRefresh is Test {
    using stdJson for string;

    event MetadataUpdate(uint256 _tokenId);

    MockList internal list;
    ListRecordRenderer internal renderer;
    ListRecord internal record;

    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;
    address internal constant BOB = address(0xB0B);

    function setUp() public {
        list = new MockList();
        list.setMember(MEMBER, 1, 30_035, 902_101_225_000_000_000_000, 461.1 ether, 2);
        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        renderer = new ListRecordRenderer(blob, _offsets());
        record = new ListRecord(address(list), address(renderer));
    }

    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function _heldByClaimant(uint256 id) internal view returns (string memory) {
        bytes memory uri = bytes(record.tokenURI(id));
        bytes memory pre = bytes("data:application/json;base64,");
        bytes memory b64 = new bytes(uri.length - pre.length);
        for (uint256 i; i < b64.length; i++) b64[i] = uri[i + pre.length];
        return string(B64.decode(string(b64))).readString(".attributes[9].value");
    }

    /// @dev The event and the change it announces, asserted together.  Either half alone can be
    ///      green while the pair is a lie: an event that fires when nothing moved is noise, and a
    ///      trait that moves with no event is a stale listing for ever.
    function test_the_transfer_refresh_is_truthful() public {
        vm.prank(MEMBER);
        uint256 id = record.claim();
        assertEq(_heldByClaimant(id), "yes", "before the transfer");

        vm.expectEmit(true, true, true, true, address(record));
        emit MetadataUpdate(id);

        vm.prank(MEMBER);
        record.transferFrom(MEMBER, BOB, id);

        assertEq(_heldByClaimant(id), "no", "after the transfer");
    }
}
```

- [ ] **Step 12: Run it, then prove each half bites.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract MetadataRefresh -vvv
```

Expected `Suite result: ok. 1 passed` — both halves are already implemented (Task 5 emits, Tasks 7
and 8 render). Now the two mutations.

**Half one, the event.** In `src/ListRecord.sol`, in Task 5's `_update`:

```solidity
        if (false) emit MetadataUpdate(tokenId);   // MUTATION -- was: if (from != address(0))
```

Re-run. Expected `[FAIL: log != expected log] test_the_transfer_refresh_is_truthful()`. Restore with
`git checkout -- src/ListRecord.sol`.

**Half two, the change.** In `src/ListRecord.sol`'s `tokenURI`:

```solidity
        d.owner = who;       // MUTATION -- was: d.owner = holder;
```

Re-run. Expected `[FAIL: after the transfer: yes != no] test_the_transfer_refresh_is_truthful()` —
the event still fires, and the test still catches it, which is exactly the pairing this test exists
for. Restore with `git checkout -- src/ListRecord.sol` and re-run to confirm 1 passed.

- [ ] **Step 13: Run the whole suite.**

```bash
cd /Library/Vibes/list-record && forge test && git status --short
```

Expected: **65 tests passed, 0 failed** — 58 after Task 9, plus 6 (`LanguageGate`) and 1
(`MetadataRefresh`). And `git status --short` must list only `test/Template.t.sol` and
`test/Announce.t.sol`; anything under `src/` or `template/` means a mutation was not restored.

- [ ] **Step 14: Commit.**

```bash
cd /Library/Vibes/list-record
git add test/Template.t.sol test/Announce.t.sol
git commit -m "test: gate the template's language, pin the description, prove the refresh is truthful"
```

---

### Task 11: Gas ceilings, the deploy script and its test, the fork test, and the rehearsal

Four deliverables and one written checklist.

**Why a gas ceiling on a view function.** `tokenURI` is never called in a transaction — a
marketplace reads it with `eth_call`, which is capped (50 M on most public nodes, far lower on
some). The whole card is assembled in memory on every read: a template sliced out of an SSTORE2
pointer with `extcodecopy`, twenty-four per-token values spliced between the slices, and one base64
pass over the finished JSON.

**The numbers to hold this to are the shipped ones, not the prototype's.** Spec §6.1 now carries
both columns and marks the right-hand one as the regression target: the prototype measured 1 808 B
of template and 217 083 gas for an SVG-only card, but the shipped design puts the whole JSON
envelope in the blob, which is **1 996 B** and **276 275 gas for a 2 937-byte `tokenURI`**. Quoting
the prototype's figure as a target would fail a correct implementation.

| quantity | shipped measurement | ceiling here | headroom |
|---|---|---|---|
| `tokenURI` (renderer alone) | 276 275 gas | — | — |
| `tokenURI` live (through `ListRecord`) | measured in Step 2 | 350 000 | ~19% over the renderer alone |
| `tokenURI` sealed | measured in Step 2 | 350 000 | ~24% |
| `claim` | measured in Step 2 | measurement + 25% | 25% by construction |

The live path adds one `ownerOf` SLOAD, two mapping SLOADs and six cold staticcalls into the game
(~15 600 gas); the sealed path adds two SLOADs and no external call at all, so sealed **must** be
cheaper than live. A ceiling is never set below a measured cost.

**Why a snapshot as well.** The ceilings are deliberately loose — a tight one fails on every
harmless change. `.gas-snapshot` is the tight instrument: it records each test's gas to the unit, so
a regression shows up as a **diff in a committed file** during review. The ceiling catches a
disaster; the snapshot catches a drift.

#### Files

- **create:** `/Library/Vibes/list-record/test/Gas.t.sol`
- **create:** `/Library/Vibes/list-record/test/ForkList.t.sol` *(mandated by ruling R11 and spec
  §8.2; not in the original frozen file list)*
- **create:** `/Library/Vibes/list-record/script/Deploy.s.sol`
- **create:** `/Library/Vibes/list-record/test/Deploy.t.sol` *(mandated by ruling R20; not in the
  original frozen file list)*
- **create:** `/Library/Vibes/list-record/.gas-snapshot` (generated, committed)
- **modify:** `/Library/Vibes/list-record/README.md` — **replace** its existing `## Deploying`
  section written by Task 1. There must be exactly one section with that heading when you are done.

#### Interfaces

**Consumes:** `ListRecord(address,address)`, `claim()`, `sealRecord(uint256)`, `tokenURI(uint256)`,
`LIST()`, `renderer()`, `graceHours()`; `ListRecordRenderer(bytes,uint16[50])`;
`IWhitelistCurator` (Task 1); `MockList.setMember(...)` / `.setSettled(bool)` (Task 2);
`template/blob.hex` and `template/offsets.txt` (Task 6).

**Produces:** `script/Deploy.s.sol` exposing
`function offsets() public view returns (uint16[50] memory)`,
`function deployWith(address game) public returns (ListRecordRenderer, ListRecord)` and
`function run() external`.

---

- [ ] **Step 1: Write the gas test.**

Create `/Library/Vibes/list-record/test/Gas.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {MockList} from "./mocks/MockList.sol";

/// @notice Ceilings, not targets.  `tokenURI` is read with eth_call, so its cost is a budget
///         against a node's call cap rather than a fee anybody pays.  The SHIPPED measurement
///         (spec 6.1) is 276 275 gas for a 2 937-byte tokenURI from the renderer alone;
///         ListRecord adds one ownerOf SLOAD, two mapping SLOADs and six cold staticcalls into
///         the game (~15 600) on the live path, and two SLOADs and no external call on the
///         sealed one.  350 000 therefore carries roughly 19% headroom over the live path and
///         24% over the sealed one.  `.gas-snapshot` is the tight instrument; this is the
///         disaster alarm.
contract GasTest is Test {
    uint256 internal constant LIVE_CEILING = 350_000;
    uint256 internal constant SEALED_CEILING = 350_000;
    // CLAIM_CEILING is added in Step 3 from the first measured run plus 25% (ruling R10).

    MockList internal list;
    ListRecordRenderer internal renderer;
    ListRecord internal record;

    // SYNTHETIC ceiling row, labelled: the widest card the contract's constants permit.  creditCap
    // is 1000 ETH and the constructor proves max weight is 2 * creditCap, so 2000 ETH is the true
    // weight maximum and curve(2000e18) == 44721.  Deposits 9999 and hour 999 have no contract
    // bound and are chosen upper bounds.  Widest values means longest strings, which is the worst
    // case for the base64 pass.  The address is invented.
    address internal constant CEILING = address(0xCE11);

    function setUp() public {
        list = new MockList();
        list.setMember(CEILING, 999, 44_721, 2_000 ether, 1_000 ether, 9_999);

        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        renderer = new ListRecordRenderer(blob, _offsets());
        record = new ListRecord(address(list), address(renderer));
    }

    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function test_gas_claim() public {
        uint256 g0 = gasleft();
        vm.prank(CEILING);
        record.claim();
        uint256 used = g0 - gasleft();
        console2.log("claim gas", used);
    }

    /// @dev Measured COLD -- the first read in the transaction -- because that is what an eth_call
    ///      from a marketplace actually is.
    function test_gas_tokenURI_live() public {
        vm.prank(CEILING);
        uint256 id = record.claim();

        uint256 g0 = gasleft();
        string memory uri = record.tokenURI(id);
        uint256 used = g0 - gasleft();

        console2.log("tokenURI live gas", used);
        console2.log("tokenURI bytes", bytes(uri).length);
        assertGt(bytes(uri).length, 2_000, "tokenURI must actually render");
        assertLt(used, LIVE_CEILING, "tokenURI live");
    }

    /// @dev A sealed token makes no external call at all, so it must be cheaper than live.
    function test_gas_tokenURI_sealed() public {
        vm.prank(CEILING);
        uint256 id = record.claim();
        list.setSettled(true);
        vm.prank(CEILING);
        record.sealRecord(id);

        uint256 g0 = gasleft();
        string memory uri = record.tokenURI(id);
        uint256 used = g0 - gasleft();

        console2.log("tokenURI sealed gas", used);
        assertGt(bytes(uri).length, 2_000, "tokenURI must actually render");
        assertLt(used, SEALED_CEILING, "tokenURI sealed");
    }
}
```

- [ ] **Step 2: Run it and record the real numbers.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract GasTest -vv
```

Expected: three passes with three `console2` figures — `claim gas`, `tokenURI live gas` (with
`tokenURI bytes` around 2 937) and `tokenURI sealed gas`. **Write all three down; Step 3 and Step 17
need them.**

Three checks on what you just read:

- **sealed < live.** If not, something is wrong: the sealed path makes no external calls.
- **live below 350 000.** If it is above, do not raise the ceiling — 350 000 already carries ~27%
  over the shipped 276 275, so a live path above it means `ListRecord`'s own reads cost far more
  than the ~20 000 predicted. Find out what before touching the constant.
- **`tokenURI bytes` near 2 937.** A much smaller number means the template or the offsets are not
  what Task 6 produced.

- [ ] **Step 3: Set the claim ceiling from the measurement, plus 25%.**

Compute it — substitute the number `claim gas` printed:

```bash
python3 -c "import math,sys; m=int(sys.argv[1]); print(f'CLAIM_CEILING = {math.ceil(m*1.25/1000)*1000:_}')" 143217
```

Add the constant beside the other two in `test/Gas.t.sol`, replacing the placeholder comment, and
add the assertion to `test_gas_claim` after the `console2.log`:

```solidity
    uint256 internal constant CLAIM_CEILING = 179_000;   // first measured run + 25%, ruling R10
```

```solidity
        assertLt(used, CLAIM_CEILING, "claim");
```

(`179_000` is what the command above prints for a measurement of 143 217 — use whatever it prints
for yours. The rule is exact: measured × 1.25, rounded up to the next whole thousand.)

```bash
cd /Library/Vibes/list-record && forge test --match-contract GasTest -vv
```

Expected: `Suite result: ok. 3 passed`. Write the measured/ceiling pairs down side by side; they go
in the commit message so the headroom is visible in the history and not only in a generated file.

- [ ] **Step 4: Prove the ceiling bites.**

A ceiling nobody has seen fail is not evidence of anything. Drop the live ceiling below the number
you recorded:

```solidity
    uint256 internal constant LIVE_CEILING = 100_000;   // MUTATION -- was: 350_000
```

```bash
cd /Library/Vibes/list-record && forge test --match-test test_gas_tokenURI_live -vv
```

Expected:

```
[FAIL: tokenURI live: 2xxxxx >= 100000] test_gas_tokenURI_live()
```

Restore `LIVE_CEILING = 350_000;` by hand — this file is not committed yet, so `git checkout` would
delete it — and re-run to confirm it passes.

- [ ] **Step 5: Write the fork test.**

Spec §8.2 requires it: hermetic by default, but a green run must never silently have skipped
integration. Create `/Library/Vibes/list-record/test/ForkList.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {IWhitelistCurator} from "../src/interfaces/IWhitelistCurator.sol";

/// @notice The ONLY test in this repository that may touch a network, and it does so only when
///         LIST_FORK_RPC is set.  A default `forge test` never leaves the machine.  It skips
///         LOUDLY: the gate is in the test's own name, so the default run prints it, and the body
///         logs a line as well.  A silent skip is the failure mode this design exists to avoid.
contract ForkListTest is Test {
    address internal constant LIST_MAINNET = 0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91;
    // REAL, captured -- rank 4 of the committed curator payloads.  Points, credit and deposits can
    // only grow, so every assertion below is a floor rather than an equality.
    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;

    function test_the_deployed_game_answers_all_nine_views_when_LIST_FORK_RPC_is_set() public {
        string memory rpc = vm.envOr("LIST_FORK_RPC", string(""));
        if (bytes(rpc).length == 0) {
            console2.log("SKIPPED: set LIST_FORK_RPC=<mainnet rpc> to run the integration check");
            return;
        }
        vm.createSelectFork(rpc);
        assertGt(LIST_MAINNET.code.length, 0, "no code at the game address");

        IWhitelistCurator g = IWhitelistCurator(LIST_MAINNET);

        (uint256 hour, bool joined) = g.firstHourOf(MEMBER);          // 1
        assertTrue(joined, "the captured member must be a member on chain");
        assertLt(hour, 24, "captured during the grace window");

        assertGe(g.pointsOf(MEMBER), 30_035, "points only grow");     // 2
        assertGe(g.weightOf(MEMBER), 902_101_225_000_000_000_000, "weight only grows"); // 3
        assertGe(g.contributedBy(MEMBER), 461.1 ether, "credit only grows");            // 4
        assertGe(g.txCountOf(MEMBER), 2, "deposits only grow");       // 5

        g.isSettled();                                                // 6 -- either answer is fine
        assertGt(g.currentHour(), 0);                                 // 7
        assertEq(g.gracePeriod(), 86_400);                            // 8
        assertEq(g.hourDuration(), 3_600);                            // 9
        assertEq(g.gracePeriod() / g.hourDuration(), 24, "graceHours");

        // and the trap, on the real chain: a wallet that never deposited is not an hour-0 founder
        (uint256 h0, bool never) = g.firstHourOf(address(0xDEAD));
        assertFalse(never, "a wallet that never deposited must not read as a member");
        assertEq(h0, 0);
    }
}
```

- [ ] **Step 6: Run it with the env var unset and confirm the skip is loud.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract ForkListTest -vv
```

Expected — a pass whose name states the gate, plus the log line:

```
[PASS] test_the_deployed_game_answers_all_nine_views_when_LIST_FORK_RPC_is_set()
Logs:
  SKIPPED: set LIST_FORK_RPC=<mainnet rpc> to run the integration check
```

To actually run it (optional, and the only network call in this plan):
`LIST_FORK_RPC=https://ethereum-rpc.publicnode.com forge test --match-contract ForkListTest -vv`.

- [ ] **Step 7: Write the deploy script's test, before the script.**

Create `/Library/Vibes/list-record/test/Deploy.t.sol`. The script is the one irreversible artifact
in the project and its offsets parser is the same code path the renderer depends on, so `forge test`
exercises it against the committed template.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {Deploy} from "../script/Deploy.s.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";
import {MockList} from "./mocks/MockList.sol";

/// @notice Hermetic tests for the deploy script.  `deployWith` is separated from `run()` exactly
///         so this file can exercise it with no broadcast, no env var and no network.
contract DeployTest is Test {
    Deploy internal deployScript;
    MockList internal list;

    address internal constant MEMBER = 0x381fe486D87C7F2633c777F1b5bE3105A2a51744;

    function setUp() public {
        deployScript = new Deploy();
        list = new MockList();
        list.setMember(MEMBER, 1, 30_035, 902_101_225_000_000_000_000, 461.1 ether, 2);
    }

    function _offsets() internal view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function test_the_script_deploys_a_pair_that_renders_from_the_committed_template() public {
        (ListRecordRenderer renderer, ListRecord record) = deployScript.deployWith(address(list));

        assertEq(address(record.LIST()), address(list), "game");
        assertEq(address(record.renderer()), address(renderer), "renderer");
        assertEq(record.graceHours(), 24, "graceHours read from the game, not hardcoded");

        vm.prank(MEMBER);
        uint256 id = record.claim();
        assertGt(bytes(record.tokenURI(id)).length, 2_000, "the deployed pair must render");
    }

    /// @dev The script's parser and the suite's parser must agree, because only one of them is
    ///      exercised by the deploy that actually happens.
    function test_the_script_and_the_suite_parse_the_same_offsets() public view {
        uint16[50] memory mine = _offsets();
        uint16[50] memory theirs = deployScript.offsets();
        for (uint256 i; i < 50; i++) {
            assertEq(theirs[i], mine[i], "offsets diverge");
        }
    }

    function test_the_script_refuses_a_zero_game_address() public {
        vm.expectRevert(bytes("set LIST_ADDRESS"));
        deployScript.deployWith(address(0));
    }

    function test_the_script_refuses_an_address_with_no_code() public {
        vm.expectRevert(bytes("LIST_ADDRESS has no code on this chain"));
        deployScript.deployWith(makeAddr("an EOA on the wrong chain"));
    }
}
```

- [ ] **Step 8: Write the script — deliberately without its two guards.**

Create `/Library/Vibes/list-record/script/Deploy.s.sol`. The two `require`s are added in Step 10, so
the guard tests have something to be red about first.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {ListRecord} from "../src/ListRecord.sol";
import {ListRecordRenderer} from "../src/ListRecordRenderer.sol";

/// @notice Deploys the renderer, then the collection pointed at it.
///
///         THERE IS NO PRIVATE KEY IN THIS REPOSITORY AND NONE MAY BE ADDED.  forge supplies the
///         signer at the command line -- `--ledger`, `--trezor` or `--interactive` -- and the
///         repository owner runs every deploy personally.  This script never reads a key, never
///         reads a keystore password, and never writes one anywhere.
///
///         Order matters: ListRecord takes the renderer as an IMMUTABLE constructor argument and
///         there is no setter, so the renderer must exist first.  The renderer never calls back
///         into ListRecord, which is why there is no circular dependency to break.
///
///         `deployWith` is split out of `run()` so test/Deploy.t.sol can exercise the real code
///         path hermetically -- no broadcast, no env var, no network.
contract Deploy is Script {
    /// @dev template/offsets.txt is ONE line of 50 comma-separated integers: flattened (start,len)
    ///      pairs, 25 fixed slices with 24 per-token values spliced between them.
    function offsets() public view returns (uint16[50] memory o) {
        string[] memory p = vm.split(vm.trim(vm.readFile("template/offsets.txt")), ",");
        require(p.length == 50, "offsets: expected 50 integers (25 start,len pairs)");
        for (uint256 i; i < 50; i++) {
            o[i] = uint16(vm.parseUint(vm.trim(p[i])));
        }
    }

    function deployWith(address game)
        public
        returns (ListRecordRenderer renderer, ListRecord record)
    {
        bytes memory blob = vm.parseBytes(vm.trim(vm.readFile("template/blob.hex")));
        require(blob.length > 1_000, "template/blob.hex looks truncated");

        renderer = new ListRecordRenderer(blob, offsets());
        record = new ListRecord(game, address(renderer));
    }

    function run() external {
        address game = vm.envAddress("LIST_ADDRESS");

        vm.startBroadcast();
        (ListRecordRenderer renderer, ListRecord record) = deployWith(game);
        vm.stopBroadcast();

        console2.log("game      ", game);
        console2.log("renderer  ", address(renderer));
        console2.log("record    ", address(record));
        console2.log("graceHours", record.graceHours());
    }
}
```

- [ ] **Step 9: Run the deploy tests and watch the guards fail.**

```bash
cd /Library/Vibes/list-record && forge test --match-contract DeployTest -vvv
```

Expected — the two happy-path tests pass because that behaviour is genuinely already there, and the
two guard tests are red because the guards do not exist yet:

```
[PASS] test_the_script_and_the_suite_parse_the_same_offsets()
[PASS] test_the_script_deploys_a_pair_that_renders_from_the_committed_template()
[FAIL: call did not revert as expected] test_the_script_refuses_a_zero_game_address()
[FAIL: call did not revert as expected] test_the_script_refuses_an_address_with_no_code()
```

- [ ] **Step 10: Add the two guards.**

At the top of `deployWith` in `script/Deploy.s.sol`, before the `vm.parseBytes` line:

```solidity
        require(game != address(0), "set LIST_ADDRESS");
        require(game.code.length > 0, "LIST_ADDRESS has no code on this chain");
```

```bash
cd /Library/Vibes/list-record && forge test --match-contract DeployTest -vvv
```

Expected: `Suite result: ok. 4 passed; 0 failed; 0 skipped`.

- [ ] **Step 11: Dry-run `run()` hermetically and watch the guard fire end to end.**

`forge script` with no `--rpc-url` runs against a fresh in-memory EVM, broadcasts nothing and
touches no network. On that empty chain nothing has code, so the zero address is the honest probe:

```bash
cd /Library/Vibes/list-record
LIST_ADDRESS=0x0000000000000000000000000000000000000000 \
  forge script script/Deploy.s.sol --sig "run()" 2>&1 | tail -5
```

Expected: the script reverts with `set LIST_ADDRESS`, which is the guard doing its job through the
real entry point rather than through `deployWith`. A deploy against an address that *does* have code
belongs on a real chain and is step 3 of the Sepolia rehearsal in Step 15 — do not try to fake one
here.

- [ ] **Step 12: Generate the gas snapshot.**

`ForkListTest` is excluded: its cost depends on whether `LIST_FORK_RPC` is set, so including it
would make the check pass or fail on an environment variable. Both commands must carry the same
filter.

```bash
cd /Library/Vibes/list-record
forge snapshot --no-match-contract ForkListTest
head -20 .gas-snapshot
```

Confirm `GasTest:test_gas_tokenURI_live()` and `GasTest:test_gas_tokenURI_sealed()` are both there.
Then confirm the check mode, which is how a regression will actually be caught:

```bash
cd /Library/Vibes/list-record
forge snapshot --check --no-match-contract ForkListTest --tolerance 1 ; echo "exit=$?"
```

Expected: no diff and `exit=0`. (`--tolerance 1` allows a 1% wobble so a solc patch bump does not
fail the build; a real regression is far larger.) Then make sure the file is committable:

```bash
cd /Library/Vibes/list-record && git check-ignore -v .gas-snapshot ; echo "exit=$?"
```

Expected `exit=1`, meaning nothing ignores it. If a rule matches, remove that rule from
`.gitignore` — a snapshot that is not committed cannot produce a diff and is worthless.

- [ ] **Step 13: Prove the snapshot bites.**

Step 12 only proved the file agrees with itself. Change a cost. Add this line to
`test_gas_tokenURI_live` in `test/Gas.t.sol`, **after** the `assertLt` so it falls outside the
measured window — the ceiling is unaffected and only the recorded total moves:

```solidity
        record.tokenURI(id);   // MUTATION -- a second render, outside the measured window
```

```bash
cd /Library/Vibes/list-record
forge snapshot --check --no-match-contract ForkListTest --tolerance 1 ; echo "exit=$?"
```

Expected: a printed diff for `GasTest:test_gas_tokenURI_live()` — roughly +276 000 gas, far outside
1% — and `exit=1`. Delete the mutation line (hand edit; `test/Gas.t.sol` is not committed yet) and
re-run to confirm `exit=0`.

- [ ] **Step 14: Replace the README's `## Deploying` section.**

Task 1 wrote a stub with this heading. **Replace it; do not append a second one.**

```bash
cd /Library/Vibes/list-record
python3 - <<'PY'
import pathlib
p = pathlib.Path("README.md")
t = p.read_text()
i = t.index("## Deploying")
j = t.find("\n## ", i + 1)
tail = t[j + 1:] if j != -1 else ""
new = """## Deploying

**The repository owner runs every deploy. There is no private key in this repository, there never
will be, and no agent produces a transaction.** `forge` takes the signer at the command line:
`--ledger`, `--trezor`, or `--interactive` (which prompts and keeps the key out of your shell
history). Do not add a `.env` with a key, do not add a keystore, do not add a `PRIVATE_KEY`
variable to any script.

**The renderer is immutable and the collection has no owner.** No setter, no upgrade path, no admin
function, no pause, no withdraw. A mainnet deploy cannot be revised. If the art is wrong the only
remedy is a second collection, which splits the floor and leaves the first one as a husk. That is
why the rehearsal below is not optional.

### Sepolia rehearsal

Do all of this on Sepolia, in order, before thinking about mainnet.

1. **Deploy a `MockList` to Sepolia.** The real game is a mainnet contract, so the testnet needs a
   stand-in answering the same nine view functions. `test/mocks/MockList.sol:MockList` is exactly
   that and `forge create` will deploy it from the test path.

2. **Seed the mock with two members whose numbers are far apart.** One at the structural floor
   (223 points, 0.05 ETH weight and credit, one deposit, a judged hour) and one near the ceiling
   (44 721 points, 2000 ETH weight, 1000 ETH credit, a grace hour). The card is a single 180px
   number and the whole design rests on the glyph count doing the work at thumbnail size; two
   similar wallets will not show you whether that is true.

3. **Deploy against it.** `LIST_ADDRESS=<mock address> forge script script/Deploy.s.sol --sig
   "run()" --rpc-url <sepolia> --broadcast --verify`. Record the renderer and record addresses the
   script prints. Verify both on Sepolia Etherscan: the "no owner, no admin function" claim is only
   checkable if the source is verified.

4. **Claim from two different wallets.** One `claim()` from each. Confirm the ids are 1 and 2 in the
   order the transactions landed: **the id is the claim order**, and it is the one scarcity
   dimension nobody can acquire retroactively.

5. **Confirm a non-member cannot claim.** Send `claim()` from a third wallet the mock does not know.
   It must revert with `NotAMember()`. It must *not* mint an hour-0 token: an hour-0 founder is the
   rarest cohort in the game and a wallet that never deposited must never render as one.

6. **Look at the item on a real marketplace.** OpenSea's or Rarible's testnet site, whichever is up.
   This is the step the whole rehearsal exists for. Confirm with your eyes:
   - the SVG renders as a picture, not a broken-image icon;
   - the big points number is legible in the collection grid at thumbnail size, not only on the
     item page;
   - all ten traits appear in the properties panel;
   - `Points`, `Weight (ETH)`, `Credit (ETH)`, `Deposits` and `Claim Order` show as **numbers** (a
     range slider) and the other five as **strings** (a value list). If a number shows up as a
     category, the quoting in the template is wrong;
   - **no rarity rank is shown.** Expected, not a bug: a single numeric attribute disqualifies a
     whole collection from OpenSea's ranker, and `Claimant` is unique per token anyway. The design
     ruled explicitly against shaping metadata for a ranker.

7. **Transfer one token** to the other wallet. Refresh the item's metadata and confirm
   `Held by claimant` flipped from `yes` to `no` -- that is the ERC-4906 `MetadataUpdate` the
   transfer emitted, doing its job through a real marketplace's cache.

8. **Settle the mock, then seal.** Flip the mock to settled, confirm the item says `settled` rather
   than `live`, then call `sealRecord(id)` from the holder. Confirm the item gains the inset frame
   and says `sealed`. Then change the mock's numbers and confirm the sealed token **does not move**
   while the unsealed one does. This is the live-versus-permanent contract, checked through the
   same pipeline a buyer would see.

9. **Call `announceSettled()` once** from any wallet and confirm the marketplace re-reads the
   collection. It is permissionless because the collection has no owner: without it there would be
   no way to trigger the one refresh that matters.

10. **Only then, mainnet.** `LIST_ADDRESS=0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`, the real
    `WhitelistCurator` on Ethereum mainnet. Re-read step 3's verification step and do it again.
    Claiming opens immediately, in the live era: a wallet that claims early and keeps depositing
    watches its own token rise, which is exactly what the design intends.

### Integration check

`test/ForkList.t.sol` asks the deployed mainnet game all nine interface questions. It is skipped
unless `LIST_FORK_RPC` is set, and it says so out loud when it skips:

    LIST_FORK_RPC=https://ethereum-rpc.publicnode.com forge test --match-contract ForkListTest -vv

A default `forge test` never touches a network.

### Gas regressions

`.gas-snapshot` is committed. Before any commit that touches `src/`:

    forge snapshot --check --no-match-contract ForkListTest --tolerance 1

If it fails, regenerate with `forge snapshot --no-match-contract ForkListTest` and **read the
diff** -- a `tokenURI` that got more expensive is a real finding, not a file to re-bless. The
ceilings in `test/Gas.t.sol` are the disaster alarm; this file is the drift detector.

"""
p.write_text(t[:i] + new + tail)
PY
grep -c "^## Deploying" README.md
```

Expected: `1`. If it prints `2`, the replacement appended instead of replacing and the file now
makes overlapping claims under two identical headings.

- [ ] **Step 15: Verify the README says what you meant.**

```bash
cd /Library/Vibes/list-record
rg -n "no private key|immutable and the collection has no owner|no rarity rank|LIST_FORK_RPC" README.md
```

Expected: four matches, one per claim. These are the sentences a future reader most needs and most
easily loses in an edit.

- [ ] **Step 16: Run the whole suite and re-snapshot.**

```bash
cd /Library/Vibes/list-record
forge test
forge snapshot --no-match-contract ForkListTest
git diff --stat .gas-snapshot
```

Expected: **73 tests passed, 0 failed** — 65 after Task 10, plus 3 (`GasTest`), 4 (`DeployTest`) and
1 (`ForkListTest`). If `.gas-snapshot` changed since Step 12, understand *why* before committing it;
that is the entire purpose of the file.

- [ ] **Step 17: Commit, with the measured numbers in the message.**

The three figures go into history rather than only into a generated file. Capture them from a fresh
run so the message cannot drift from the code:

```bash
cd /Library/Vibes/list-record
forge test --match-contract GasTest -vv | grep -E "claim gas|tokenURI live gas|tokenURI sealed gas" > /tmp/list-record-gas.txt
cat /tmp/list-record-gas.txt
git add test/Gas.t.sol test/ForkList.t.sol script/Deploy.s.sol test/Deploy.t.sol .gas-snapshot README.md
git commit -F - <<EOF
feat: gas ceilings + snapshot, deploy script and its test, fork test, rehearsal checklist

Measured:
$(cat /tmp/list-record-gas.txt)
Ceilings: tokenURI 350000 live and sealed (shipped renderer measurement is 276275 for a
2937-byte tokenURI, spec 6.1); claim ceiling is the first measured run + 25%.
.gas-snapshot is the tight regression detector, excluding ForkListTest because its cost
depends on whether LIST_FORK_RPC is set.
EOF
```

Confirm the commit body carries three real numbers and no placeholder before moving on.

---
