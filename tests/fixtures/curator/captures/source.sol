// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title  WhitelistCurator
/// @notice Curates a permissionless onchain allowlist of proven wallets — usable as a whitelist for
///         mints and early access, as an airdrop distribution list, or as reputation input. You send
///         ETH, the same transaction sends it straight back — the contract never keeps a wei. What
///         persists is the record.
///
///         Because the list lives onchain, a gating contract can read it directly at mint time:
///         there is no merkle root to publish and no snapshot to maintain.
///
///         Two rules turn it into a game:
///
///         1. ESCALATION. Your recorded contribution is your high-water single send. Every deposit
///            must beat it by at least `minEscalation`, and only the delta is credited. Sending
///            1 ETH a thousand times is worthless; 1 ETH then 2 ETH nets you 2 ETH of credit.
///
///         2. SETTLEMENT. For `gracePeriod` after launch anything goes. After that, every clock
///            hour must pull in `hourlyThreshold` or the contract settles — permanently closed,
///            list frozen forever. A silent hour counts as a failed hour.
///
///         No upgrade path, no pause, no parameter can ever change, and no record can be altered.
///         There is exactly one privileged address — `deployer` — with exactly one power: sweeping
///         ETH that was FORCED into the contract (see `rescue`). It cannot touch deposits, and that
///         is a structural property of the refund, not a promise. Everything else is immutable.
///
/// ─────────────────────────────────────────────────────────────────────────────────────────────
///  FOR BUILDERS CONSUMING THIS LIST
/// ─────────────────────────────────────────────────────────────────────────────────────────────
///
///  This contract does not pretend to solve sybil resistance, and you should not use it as if it
///  did. Nothing onchain can, once the ETH is handed straight back: fanning out across a hundred
///  wallets costs gas and nothing else, and the square-root curve actively rewards doing so.
///  Filter that off-chain. The events carry what you need to cluster it — first-seen hour, the
///  whole escalation ladder, tx counts, hour-by-hour timing — and a farm funded from one source
///  in one afternoon does not look like a hundred strangers.
///
///  What the contract DOES enforce is that the ETH was actually held. Only code-less EOAs may
///  deposit, so no depositor can sit inside a flash-loan callback and compose borrow → deposit →
///  refund → repay atomically. Every high-water mark on this list was real balance at the moment
///  it was recorded. That is the one capital claim you can take at face value.
///
///  What the list does give you is a signal that is expensive to fake and impossible to
///  backfill: addresses that were still showing up on mainnet, paying real gas, hour after hour,
///  in a quiet market after almost everyone else had left. Anyone can buy a token balance or
///  farm a testnet. Nobody can retroactively have been here. That presence is the product; the
///  points are just the scoreboard on top of it.
///
///  Practical consequence for a sybil: the payoff is a bigger share of whatever the list is spent
///  on — a whitelist allocation, an airdrop, a reputation score — and the downside is being
///  clustered and dropped from it entirely. They are wagering gas against total exclusion, which
///  is a deterrent that lives in your indexer, not in this contract.
///
/// ─────────────────────────────────────────────────────────────────────────────────────────────
///
/// @dev    Integrators: a 2300-gas `transfer`/`send` into this contract WILL fail — the deposit
///         path costs far more than the stipend. Use a normal wallet send or `call`.
///         ONLY CODE-LESS EOAs MAY DEPOSIT. Safe, ERC-4337 and EIP-7702 delegated accounts all
///         revert with `OnlyEOA` — 7702 included, since its delegation indicator is real code and
///         is exactly what makes an atomic flash-loaned deposit possible. Say so in your UI before
///         a user burns gas finding out.
contract WhitelistCurator {
    /*//////////////////////////////////////////////////////////////
                                 CONFIG
    //////////////////////////////////////////////////////////////*/

    /// @notice Timestamp the contract went live. The hour clock starts here.
    uint256 public immutable launchTime;
    /// @notice ETH a completed hour must receive to keep the contract open.
    uint256 public immutable hourlyThreshold;
    /// @notice Seconds after launch during which the threshold is not enforced.
    uint256 public immutable gracePeriod;
    /// @notice Length of one hour bucket, in seconds.
    uint256 public immutable hourDuration;
    /// @notice Minimum first deposit.
    uint256 public immutable minDeposit;
    /// @notice Minimum amount each deposit must beat the sender's high-water mark by.
    uint256 public immutable minEscalation;
    /// @notice High-water mark past which no further weight is credited.
    uint256 public immutable creditCap;
    /// @notice First hour index judged against the threshold (= gracePeriod / hourDuration).
    uint256 public immutable firstJudgedHour;

    /// @notice The one privileged address, fixed at deployment. Its ONLY power is `rescue()` —
    ///         sweeping ETH that was forced into the contract. It cannot pause, settle, alter a
    ///         record, change a parameter, or upgrade anything, and it cannot reach deposits.
    address public immutable deployer;

    uint256 private constant BPS = 10_000;
    /// @notice Early-bird multiplier at launch, decaying linearly to 1x at the end of the grace period.
    ///         This is the only multiplier, so 2x is the hard ceiling on weight per unit of credit.
    uint256 private constant EARLY_MAX_BPS = 20_000;
    /// @notice Points awarded for 1 ETH of weight under the default curve.
    uint256 public constant POINTS_PER_ETH = 1000;

    /*//////////////////////////////////////////////////////////////
                                 STORAGE
    //////////////////////////////////////////////////////////////*/

    // ── slot 0: the entire settlement machine ──
    /// @dev Hour index of the most recent recorded deposit.
    uint64 private _lastActiveHour;
    /// @dev Raw wei recorded in that hour.
    uint128 private _lastActiveHourTotal;
    /// @dev Cached settlement flag. Source of truth is `isSettled()`.
    bool private _settled;

    // ── slot 1: reentrancy guard (1 = open, 2 = entered) ──
    uint256 private _lock = 1;

    /// @notice Per-address record. Packs into exactly one slot.
    struct Contributor {
        uint96 highWater; // largest single send == credited net contribution
        uint96 weight; // sum of (credited delta x early-bird multiplier), in wei-equivalents
        uint32 txCount; // recorded deposits (all of which were escalations)
        uint32 firstHour; // hour index of first deposit, +1 (0 == never deposited)
    }

    mapping(address => Contributor) public contributors;

    // ── one slot of global stats ──
    /// @notice Gross wei ever routed through the contract (all of it refunded).
    uint128 public totalVolume;
    /// @notice Unique addresses on the list.
    uint64 public totalContributors;
    /// @notice Recorded deposits across all addresses.
    uint64 public totalTxCount;

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    event Launched(
        uint256 launchTime,
        uint256 hourlyThreshold,
        uint256 gracePeriod,
        uint256 hourDuration,
        uint256 minDeposit,
        uint256 minEscalation,
        uint256 creditCap
    );

    /// @notice Everything an indexer needs to rebuild hourly totals, the leaderboard, and any
    ///         alternative points formula from scratch. `amount` is also the sender's new
    ///         high-water mark, by construction.
    event Deposited(
        address indexed contributor,
        uint256 indexed hour,
        uint256 amount,
        uint256 creditedDelta,
        uint256 weightAdded,
        uint256 newWeight,
        uint256 txCount,
        uint256 hourTotal,
        uint256 earlyBps
    );

    /// @notice Emitted once per address, with a monotonic index so the list can be paged.
    event FirstDeposit(address indexed contributor, uint256 indexed index, uint256 timestamp);

    /// @notice Emitted when a deposit pushes an at-risk hour over the threshold. Carries NO reward —
    ///         it is behavioural data for builders, nothing more. Rescuing an hour is worth exactly
    ///         what the deposit itself is worth.
    event HourSaved(address indexed savior, uint256 indexed hour, uint256 hourTotal);

    /// @notice Emitted once, ever, when the settled flag is persisted.
    event Settled(uint256 indexed hour, uint256 timestamp, uint256 totalContributors, uint256 totalVolume);

    /// @notice Emitted when force-fed ETH is swept out. If this never fires, nothing was ever forced
    ///         in — which is the expected case.
    event Rescued(address indexed to, uint256 amount);

    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/

    error AlreadySettled();
    error NotSettled();
    error OnlyEOA();
    error NotDeployer();
    error NothingToRescue();
    error MustEscalate(uint256 sent, uint256 required);
    error RefundFailed();
    error AmountTooLarge();
    error Reentrancy();
    error InvalidConfig();

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    constructor(
        uint256 _hourlyThreshold,
        uint256 _gracePeriod,
        uint256 _hourDuration,
        uint256 _minDeposit,
        uint256 _minEscalation,
        uint256 _creditCap
    ) {
        if (_hourDuration == 0) revert InvalidConfig();
        if (_hourlyThreshold == 0) revert InvalidConfig();
        if (_minDeposit == 0) revert InvalidConfig();
        if (_minEscalation == 0) revert InvalidConfig();
        if (_gracePeriod % _hourDuration != 0) revert InvalidConfig();
        if (_creditCap < _minDeposit) revert InvalidConfig();
        // Keeps `weight` inside uint96 for any deploy config. Lifetime credit telescopes to at most
        // creditCap, and the early-bird 2x is now the only multiplier, so 2 * creditCap is exact.
        if (_creditCap > uint256(type(uint96).max) / 2) revert InvalidConfig();

        deployer = msg.sender;
        launchTime = block.timestamp;
        hourlyThreshold = _hourlyThreshold;
        gracePeriod = _gracePeriod;
        hourDuration = _hourDuration;
        minDeposit = _minDeposit;
        minEscalation = _minEscalation;
        creditCap = _creditCap;
        firstJudgedHour = _gracePeriod / _hourDuration;

        emit Launched(
            block.timestamp,
            _hourlyThreshold,
            _gracePeriod,
            _hourDuration,
            _minDeposit,
            _minEscalation,
            _creditCap
        );
    }

    /*//////////////////////////////////////////////////////////////
                                DEPOSIT
    //////////////////////////////////////////////////////////////*/

    /// @notice Send ETH here and it comes straight back in the same transaction.
    receive() external payable {
        _deposit();
    }

    /// @notice Explicit entry point. Identical to sending ETH directly.
    function deposit() external payable {
        _deposit();
    }

    function _deposit() private {
        if (_lock != 1) revert Reentrancy();
        _lock = 2;

        // Cheap cached exit once someone has persisted the settlement.
        if (_settled) revert AlreadySettled();

        // Two checks, because either alone is insufficient:
        //
        //   tx.origin == msg.sender   blocks routers, farming wrappers and contract-based sybil
        //                             factories — including a contract calling from its own
        //                             constructor, where code.length is still 0.
        //
        //   code.length == 0          blocks EIP-7702 delegated EOAs, which pass the origin check
        //                             (they ARE tx.origin) while running arbitrary code. Without
        //                             this, a delegate can sit inside a flash-loan callback and
        //                             reach the credit cap with zero capital, since the deposit is
        //                             refunded in the same transaction. A 7702 account carries a
        //                             23-byte delegation indicator (0xef0100 || address); a plain
        //                             EOA carries none.
        //
        // Cost of this policy: Safe, ERC-4337 and EIP-7702 accounts cannot participate at all.
        if (tx.origin != msg.sender) revert OnlyEOA();
        if (msg.sender.code.length != 0) revert OnlyEOA();

        uint256 amount = msg.value;
        if (amount > type(uint96).max) revert AmountTooLarge();

        Contributor memory c = contributors[msg.sender];

        // ── escalation gate: beat your own record or don't play ──
        uint256 required = c.highWater == 0 ? minDeposit : uint256(c.highWater) + minEscalation;
        if (amount < required) revert MustEscalate(amount, required);

        uint256 hour = currentHour();

        // Settlement is derived, never written here: this call reverts, which would undo the write.
        // The predicate is deterministic and monotonic, so every later deposit reaches the same
        // verdict. `settle()` is what persists the flag.
        if (_isShort(hour)) revert AlreadySettled();

        // ── hour bucket: survival always counts the raw amount ──
        uint256 prevHourTotal = (hour == _lastActiveHour) ? _lastActiveHourTotal : 0;
        uint256 newHourTotal = prevHourTotal + amount;

        // Which deposit pushed an at-risk hour over the bar. INFORMATIONAL ONLY — it carries no
        // bonus. A rescue reward cannot be priced here: the ETH needed to save an hour shrinks as
        // the hour fills, so any multiplier on the deposit pays most for the least risk.
        bool savedHour =
            hour >= firstJudgedHour && prevHourTotal < hourlyThreshold && newHourTotal >= hourlyThreshold;

        (uint256 creditedDelta, uint256 weightAdded, uint256 earlyBps) = _credit(c.highWater, amount);

        // ── writes ──
        // casting to 'uint64' is safe because hour <= block.timestamp / hourDuration
        // forge-lint: disable-next-line(unsafe-typecast)
        _lastActiveHour = uint64(hour);
        // casting to 'uint128' is safe because every amount is bounded to uint96 above, so an hour
        // would need 2**32 max-size deposits to overflow
        // forge-lint: disable-next-line(unsafe-typecast)
        _lastActiveHourTotal = uint128(newHourTotal);

        if (c.firstHour == 0) {
            // +1 so 0 keeps meaning "never deposited"
            // casting to 'uint32' is safe because hour <= block.timestamp / hourDuration
            // forge-lint: disable-next-line(unsafe-typecast)
            c.firstHour = uint32(hour + 1);
            unchecked {
                totalContributors += 1;
            }
            emit FirstDeposit(msg.sender, totalContributors, block.timestamp);
        }
        // casting to 'uint96' is safe because of the explicit AmountTooLarge check above
        // forge-lint: disable-next-line(unsafe-typecast)
        c.highWater = uint96(amount);
        // casting to 'uint96' is safe because lifetime credit telescopes to at most creditCap, and
        // the constructor rejects any creditCap above type(uint96).max / 2 (the max multiplier)
        // forge-lint: disable-next-line(unsafe-typecast)
        c.weight += uint96(weightAdded);
        c.txCount += 1;
        contributors[msg.sender] = c;

        // casting to 'uint128' is safe because every amount is bounded to uint96 above
        // forge-lint: disable-next-line(unsafe-typecast)
        totalVolume += uint128(amount);
        unchecked {
            totalTxCount += 1;
        }

        if (savedHour) emit HourSaved(msg.sender, hour, newHourTotal);
        emit Deposited(
            msg.sender, hour, amount, creditedDelta, weightAdded, c.weight, c.txCount, newHourTotal, earlyBps
        );

        // ── effects done, refund last ──
        // Defence in depth: the EOA gate above means msg.sender is always a code-less account, so
        // this transfer cannot fail and the reentrancy guard cannot fire. Both are kept because
        // they are what makes that reasoning safe to change later, not because they are reachable.
        (bool ok,) = msg.sender.call{value: amount}("");
        if (!ok) revert RefundFailed();

        _lock = 1;
    }

    /// @dev Credit for an escalation, cap-aware. Only the part of the new high-water mark that sits
    ///      below `creditCap` and above the sender's previous mark earns anything, so deposits past
    ///      the cap succeed and feed the hourly total while adding zero weight.
    function _credit(uint96 oldHighWater, uint256 amount)
        private
        view
        returns (uint256 creditedDelta, uint256 weightAdded, uint256 earlyBps)
    {
        uint256 cappedNew = amount > creditCap ? creditCap : amount;
        uint256 cappedOld = oldHighWater > creditCap ? creditCap : oldHighWater;
        creditedDelta = cappedNew > cappedOld ? cappedNew - cappedOld : 0;

        earlyBps = earlyMultiplierBps();
        weightAdded = (creditedDelta * earlyBps) / BPS;
    }

    /*//////////////////////////////////////////////////////////////
                               SETTLEMENT
    //////////////////////////////////////////////////////////////*/

    /// @notice Persist the settled flag once the contract has failed an hour. Callable by anyone;
    ///         changes no outcome, it just records the ending and makes later deposits cheaper to
    ///         reject.
    function settle() external {
        if (_settled) revert AlreadySettled();
        uint256 hour = currentHour();
        if (!_isShort(hour)) revert NotSettled();
        _settled = true;
        emit Settled(hour, block.timestamp, totalContributors, totalVolume);
    }

    /// @notice True once any completed, judged hour came up short. Never returns false again.
    function isSettled() public view returns (bool) {
        return _settled || _isShort(currentHour());
    }

    /*//////////////////////////////////////////////////////////////
                                 RESCUE
    //////////////////////////////////////////////////////////////*/

    /// @notice Sweep ETH that was forced into the contract to `deployer`.
    ///
    ///         Deposits are refunded inside the same transaction, so between transactions this
    ///         balance is always exactly zero. The only way it becomes non-zero is if someone
    ///         forces ETH in without calling anything — `selfdestruct` still transfers balance
    ///         post-EIP-6780, and a block builder can name this contract as a fee recipient. That
    ///         ETH would otherwise be stuck forever, since nothing here reads `address(this).balance`.
    ///
    ///         THIS CANNOT REACH A DEPOSIT, structurally rather than by promise:
    ///
    ///           1. A deposit's ETH is only in the contract mid-transaction, and the only external
    ///              call in that window is the refund to a code-less EOA — which by definition runs
    ///              no code and therefore cannot call this function.
    ///           2. Even if it somehow did, the refund sends `msg.value` and would then find the
    ///              balance missing, revert `RefundFailed`, and unwind the whole transaction —
    ///              including the sweep.
    ///
    ///         This is the contract's only privileged function. It cannot pause, settle, alter any
    ///         record, change any parameter, or upgrade anything.
    function rescue() external {
        if (msg.sender != deployer) revert NotDeployer();

        uint256 amount = address(this).balance;
        if (amount == 0) revert NothingToRescue();

        emit Rescued(deployer, amount);

        (bool ok,) = deployer.call{value: amount}("");
        if (!ok) revert RefundFailed();
    }

    /// @dev Did any completed hour in [max(lastActiveHour, firstJudgedHour), hour-1] fall short?
    ///      Every hour after the last active one is provably empty (deposits are the only writer),
    ///      so an empty hour is a failed hour and only the last active hour's total is ever needed.
    function _isShort(uint256 hour) private view returns (bool) {
        if (hour == 0) return false;

        uint256 lastActive = _lastActiveHour;
        uint256 from = lastActive > firstJudgedHour ? lastActive : firstJudgedHour;
        if (from > hour - 1) return false; // nothing completed and judged yet

        if (lastActive >= firstJudgedHour) {
            // The last active hour is complete and judged.
            if (_lastActiveHourTotal < hourlyThreshold) return true;
            // Anything after it is an empty hour.
            return hour - 1 > lastActive;
        }
        // No deposits at or after firstJudgedHour, and [firstJudgedHour, hour-1] is non-empty:
        // those hours are all silent.
        return true;
    }

    /*//////////////////////////////////////////////////////////////
                                 POINTS
    //////////////////////////////////////////////////////////////*/

    /// @notice Points for an address under the current curve.
    /// @dev    `weight` is the precise, curve-free record; points are the display number. Builders
    ///         wanting full resolution should read `weightOf`.
    function pointsOf(address account) external view returns (uint256) {
        return _curve(contributors[account].weight);
    }

    /// @notice Points a given weight would earn. Lets a frontend quote before you send.
    function previewPoints(uint256 weight) external pure returns (uint256) {
        return _curve(weight);
    }

    /// @dev THE CURVE. Square root: concave, so 1000x the capital buys ~31x the points.
    ///      Scaled so 1 ETH of weight == 1000 points.
    function _curve(uint256 weight) private pure returns (uint256) {
        return (_sqrt(weight) * POINTS_PER_ETH) / 1e9; // sqrt(1e18) == 1e9
    }

    /// @dev Integer square root, bit-length seed + 7 Newton iterations (OZ/solady style).
    function _sqrt(uint256 a) private pure returns (uint256) {
        if (a == 0) return 0;
        // Seed with 2**(floor(log2(a)/2)). The lint below targets Yul's shl(bits, value) arg order;
        // this is Solidity's `value << bits`, which is correct as written.
        // forge-lint: disable-next-line(incorrect-shift)
        uint256 result = 1 << (_log2(a) >> 1);
        unchecked {
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            result = (result + a / result) >> 1;
            return result <= a / result ? result : result - 1;
        }
    }

    function _log2(uint256 x) private pure returns (uint256 r) {
        unchecked {
            if (x >> 128 > 0) {
                x >>= 128;
                r += 128;
            }
            if (x >> 64 > 0) {
                x >>= 64;
                r += 64;
            }
            if (x >> 32 > 0) {
                x >>= 32;
                r += 32;
            }
            if (x >> 16 > 0) {
                x >>= 16;
                r += 16;
            }
            if (x >> 8 > 0) {
                x >>= 8;
                r += 8;
            }
            if (x >> 4 > 0) {
                x >>= 4;
                r += 4;
            }
            if (x >> 2 > 0) {
                x >>= 2;
                r += 2;
            }
            if (x >> 1 > 0) r += 1;
        }
    }

    /*//////////////////////////////////////////////////////////////
                                 VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice Current hour index, counted from launch.
    function currentHour() public view returns (uint256) {
        return (block.timestamp - launchTime) / hourDuration;
    }

    /// @notice Early-bird multiplier in bps: 20000 (2x) at launch decaying linearly to 10000 (1x)
    ///         at the end of the grace period, flat thereafter.
    function earlyMultiplierBps() public view returns (uint256) {
        uint256 elapsed = block.timestamp - launchTime;
        if (elapsed >= gracePeriod) return BPS;
        return EARLY_MAX_BPS - (elapsed * BPS) / gracePeriod;
    }

    /// @notice What `account` must send next: their entry minimum, or their record plus a step.
    function requiredNext(address account) external view returns (uint256) {
        uint96 hw = contributors[account].highWater;
        return hw == 0 ? minDeposit : uint256(hw) + minEscalation;
    }

    /// @notice Raw wei recorded in the current hour so far.
    function currentHourTotal() public view returns (uint256) {
        return currentHour() == _lastActiveHour ? _lastActiveHourTotal : 0;
    }

    /// @notice ETH still needed this hour to keep the contract open. Zero during the grace period
    ///         and once the hour is safe.
    function ethNeededThisHour() external view returns (uint256) {
        if (currentHour() < firstJudgedHour) return 0;
        uint256 total = currentHourTotal();
        return total >= hourlyThreshold ? 0 : hourlyThreshold - total;
    }

    /// @notice Seconds left in the current hour bucket.
    function timeLeftInHour() external view returns (uint256) {
        return hourDuration - ((block.timestamp - launchTime) % hourDuration);
    }

    function weightOf(address account) external view returns (uint256) {
        return contributors[account].weight;
    }

    function contributedBy(address account) external view returns (uint256) {
        return contributors[account].highWater;
    }

    function txCountOf(address account) external view returns (uint256) {
        return contributors[account].txCount;
    }

    /// @notice Hour index of an address's first deposit. Reverts nothing; 0 with `hasJoined` false
    ///         simply means they never showed up.
    function firstHourOf(address account) external view returns (uint256 hour, bool hasJoined) {
        uint32 stored = contributors[account].firstHour;
        return stored == 0 ? (0, false) : (stored - 1, true);
    }

    function stats() external view returns (uint256 volume, uint256 people, uint256 txs) {
        return (totalVolume, totalContributors, totalTxCount);
    }

    /// @notice Last hour that recorded a deposit, and how much it took in.
    function lastActiveHour() external view returns (uint256 hour, uint256 total) {
        return (_lastActiveHour, _lastActiveHourTotal);
    }
}
