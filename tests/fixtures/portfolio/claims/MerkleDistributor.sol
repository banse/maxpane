// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {LaunchFees} from "./LaunchFees.sol";

/// @title Contributor allocations for one launch
/// @notice Funded inside the launch transaction with the contributor pool, and claimed rather than
/// pushed. On mainnet that is the difference between one transaction per launch and one per
/// contributor; it also means a dead or wrong address costs nothing, and unclaimed value is
/// recoverable rather than burnt.
///
/// @dev Rounds rather than a single root, so a remediation job can be paid later without deploying a
/// second contract. Each round has its own root and its own funding; a leaf is `(account, amount)`
/// and carries no index, because OpenZeppelin's `StandardMerkleTree` double-hashes and sorts pairs,
/// so a leaf is identified by its content. One fewer thing for the two sides to agree on, on the
/// path where disagreeing means a contributor cannot be paid.
///
/// Nobody owns it. The factory that made it opens its first round in the launch transaction and
/// can open no other; later rounds are the treasury's, and the treasury is whatever the chain's
/// `LaunchFees` names when it is asked, so moving it there moves it here. Unclaimed value goes to
/// that treasury once a round's sweep delay is up, and anyone may send it: it can go nowhere else.
contract MerkleDistributor is ReentrancyGuard {
    using SafeERC20 for IERC20;

    error NotOpener();
    error AlreadyClaimed();
    error InvalidProof();
    error NoSuchRound();
    error StillLocked(uint64 unlocksAt);
    error SweepTooEarly(uint64 sweepableAt);
    error EmptyRoot();
    error RoundClosed();
    error InsufficientFunding();
    error InsufficientRoundBalance();

    event RoundOpened(uint256 indexed round, bytes32 root, uint256 funded, uint64 unlocksAt);
    event Claimed(uint256 indexed round, address indexed account, uint256 amount);
    event Swept(address indexed to, uint256 amount);

    struct Round {
        bytes32 root;
        uint256 funded;
        uint256 claimed;
        /// @dev Contributor allocations vest as a cliff. A fresh launch whose worker allocations are
        /// instantly liquid prices itself down at birth, which costs the contributors it was meant
        /// to pay.
        uint64 unlocksAt;
    }

    IERC20 public immutable token;
    /// @notice The factory that made it: it may open the first round, and nothing after.
    address public immutable opener;
    /// @notice The chain's fee settings, which name the treasury.
    LaunchFees public immutable fees;
    /// @notice How long after a round opens before what is left may be swept. Never before the round
    /// unlocks, whatever this says: see `sweep`.
    uint64 public immutable sweepDelay;

    Round[] private _rounds;
    mapping(uint256 round => mapping(address account => bool)) public claimed;
    mapping(uint256 round => uint64) public openedAt;
    mapping(uint256 round => bool) public swept;
    /// @notice Tokens still owed by all open rounds. A new round must have its own funding.
    uint256 public reserved;

    constructor(IERC20 token_, address opener_, LaunchFees fees_, uint64 sweepDelay_) {
        token = token_;
        opener = opener_;
        fees = fees_;
        sweepDelay = sweepDelay_;
    }

    /// @notice Where unclaimed value goes, and who may open a later round: the chain's treasury now.
    function treasury() public view returns (address) {
        return fees.treasury();
    }

    /// @notice Opens a round against tokens this contract already holds.
    /// @dev Funding is checked rather than pulled: the launch transaction transfers the contributor
    /// pool in and opens the round in the same call, and a distributor that could pull would need an
    /// allowance from something that has one.
    function openRound(bytes32 root, uint256 funded, uint64 lockSeconds)
        external
        nonReentrant
        returns (uint256 round)
    {
        if (msg.sender != treasury() && (msg.sender != opener || _rounds.length != 0)) revert NotOpener();
        if (root == bytes32(0)) revert EmptyRoot();
        if (token.balanceOf(address(this)) < reserved + funded) revert InsufficientFunding();
        reserved += funded;

        round = _rounds.length;
        _rounds.push(
            Round({
                root: root,
                funded: funded,
                claimed: 0,
                unlocksAt: uint64(block.timestamp) + lockSeconds
            })
        );
        openedAt[round] = uint64(block.timestamp);

        emit RoundOpened(round, root, funded, _rounds[round].unlocksAt);
    }

    /// @notice Claims one allocation.
    /// @dev Anyone may submit the proof, but the tokens only ever go to the account in the leaf. That
    /// lets us pay the gas for a contributor who has none without being able to redirect what they
    /// are owed.
    function claim(uint256 round, address account, uint256 amount, bytes32[] calldata proof) external nonReentrant {
        if (round >= _rounds.length) revert NoSuchRound();
        Round storage current = _rounds[round];

        if (swept[round]) revert RoundClosed();
        if (block.timestamp < current.unlocksAt) revert StillLocked(current.unlocksAt);
        if (claimed[round][account]) revert AlreadyClaimed();

        // Double hashing is what makes a leaf unforgeable as an internal node — the shape
        // OpenZeppelin's StandardMerkleTree produces, and what our off-chain tree builds.
        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(account, amount))));
        if (!MerkleProof.verifyCalldata(proof, current.root, leaf)) revert InvalidProof();
        if (amount > current.funded - current.claimed) revert InsufficientRoundBalance();

        claimed[round][account] = true;
        current.claimed += amount;
        reserved -= amount;

        token.safeTransfer(account, amount);
        if (token.balanceOf(address(this)) < reserved) revert InsufficientFunding();
        emit Claimed(round, account, amount);
    }

    /// @notice Sends what a round's claimants never took to the treasury. Anyone may call it once the
    /// round's delay is up: the tokens can go only to the treasury `LaunchFees` names at that moment.
    /// @dev `block.timestamp` is compared here and in `claim`, which the linter flags. It is the
    /// right clock for both: a validator can move it by seconds, and these windows are a six-month
    /// lock and a one-year sweep delay. Block numbers would be worse — they drift against wall time,
    /// and a lock a contributor was told lasts six months should last six months.
    /// @dev Deliberately late and deliberately to one address, the network's treasury. Unclaimed value that can never be
    /// recovered is a slow leak; unclaimed value that can be recovered early is a reason not to
    /// trust the distributor at all.
    /// @dev Never before the round unlocks, whichever of the two clocks runs later. The delay counts
    /// from the round opening and is one number the deployer sets for every launch; the lock is
    /// another, set per launch by policy; nothing checks one against the other, and a lock longer
    /// than the delay would otherwise let the treasury empty a round no contributor could yet touch.
    /// Waited out here rather than refused in `openRound`: a long lock is a legitimate choice and
    /// not a mistake, and refusing it would revert the whole launch over a constant somebody has to
    /// go and change, when the only correct answer to it is to wait.
    function sweep(uint256 round) external nonReentrant returns (uint256 amount) {
        if (round >= _rounds.length) revert NoSuchRound();
        if (swept[round]) revert RoundClosed();
        Round storage current = _rounds[round];

        uint64 sweepableAt = openedAt[round] + sweepDelay;
        uint64 unlocksAt = current.unlocksAt;
        if (unlocksAt > sweepableAt) sweepableAt = unlocksAt;
        if (block.timestamp < sweepableAt) revert SweepTooEarly(sweepableAt);

        // Close the old proofs before paying out, and leave every other round's tokens in place.
        amount = current.funded - current.claimed;
        swept[round] = true;
        reserved -= amount;
        address to = treasury();
        if (amount > 0) token.safeTransfer(to, amount);
        if (token.balanceOf(address(this)) < reserved) revert InsufficientFunding();
        emit Swept(to, amount);
    }

    function roundCount() external view returns (uint256) {
        return _rounds.length;
    }

    function roundOf(uint256 round) external view returns (Round memory) {
        if (round >= _rounds.length) revert NoSuchRound();
        return _rounds[round];
    }
}
