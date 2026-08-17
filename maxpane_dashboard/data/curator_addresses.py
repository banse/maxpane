"""Vendored constants for the curator dashboard — THE LIST.

Subject: ``WhitelistCurator`` at :data:`CURATOR` on Ethereum mainnet, deployed
2026-08-16 19:58:47 UTC in block :data:`CREATION_BLOCK`.  Every address below is
EIP-55 checksummed and ``tests/data/test_curator_addresses.py`` recomputes each
checksum with this repo's keccak, so a mistyped nibble cannot ship.

Two hazards this module exists to contain:

* **There is no "the owner changed it" failure mode.**  The contract is
  verified, non-upgradeable, unpaused, and has no mutable parameter: the eight
  config values are ``immutable`` and ``POINTS_PER_ETH`` is a ``constant``.  The
  one privileged function is :func:`rescue`, whose only power is sweeping ETH
  that was *forced* into the contract; it cannot pause, settle, alter a record,
  change a parameter, upgrade anything, or reach a deposit.  So unlike every
  other dashboard in this app, a value that disagrees with the last read is a
  bug in *us*, not a governance action — which is exactly why the immutables are
  still read live off the ``once`` tier rather than hardcoded here.  Docs drift;
  chains do not.
* **The balance of** :data:`CURATOR` **is always forced ETH, never deposits.**
  Every wei sent through ``deposit()`` is refunded inside the same transaction,
  so a nonzero ``eth_getBalance`` means someone ``selfdestruct``-ed or
  coinbase-fed ETH into the address.  It feeds the ``forced_eth`` anomaly signal
  and must never reach a volume, TVL or hero total.  The expected rendering is
  ``—``.

**Read-only, keyless, by hard constraint.**  ``deposit()``, ``settle()`` and
``rescue()`` are read *about*, never called; nothing in this package encodes a
state-changing call and no constant here is an endpoint that wants a key.

**Nothing is imported across dashboard data layers.**  :data:`DEPLOYER` and
:data:`ANNOUNCE` are byte-identical to two constants the surf dashboard also
vendors — both are re-vendored here on purpose (PRD §5).  An import would make
an edit to the surf dashboard, explicitly out of scope for this build, a curator
regression.

This module imports nothing but ``__future__``.
"""

from __future__ import annotations

# --- Addresses (Ethereum mainnet) -------------------------------------------
#: ``WhitelistCurator`` — the whole subject of this dashboard.  Verified source,
#: solc 0.8.28, non-upgradeable.  Its balance is always forced ETH (see above).
#:
#: The checksum below is the one Blockscout returns for
#: ``creation_tx.json → created_contract.hash`` and the one this repo's keccak
#: recomputes.  ``docs/curator_work_packages/wp0.md`` quotes a hand-retyped
#: variant that is not EIP-55; the chain wins.
CURATOR = "0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91"

#: The deploying EOA, ENS ``surfsurf.eth``.  The contract's ``deployer``
#: immutable returns exactly this, and its only power is ``rescue()``.
#: Re-vendored, never imported — see the module docstring.
DEPLOYER = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"

#: The dev's announcement-channel EOA.  Relevant here as a *participant*, not as
#: a feed: it made deposit #1 (0.05 ETH at 19 975 bps, block 25 769 888), which
#: is the one real witness for the weight formula, so it shows up in the
#: leaderboard and the activity feed and deserves a label.  The announce channel
#: itself is surf's subject and is out of scope for this dashboard.
ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# --- Deployment facts (read out of captures/creation_tx.json) ---------------
#: The contract-creation transaction.
CREATION_TX = "0x240bf1a83d08dd10ff28027f4bdd7f9c0fa7f57629a13cfaafdd6e708dcc641f"

#: The block it landed in.  Every log backfill starts here; the ``Launched``
#: event is in this block and no curator log exists below it.
CREATION_BLOCK = 25769870

#: ``launchTime`` — the hour clock's origin, in Unix seconds.  Equal to the
#: creation block's timestamp (2026-08-16 19:58:47 UTC) and to what
#: ``launchTime()`` returned in the captured batch round.
#:
#: This constant is a **pin, not a source**.  The dashboard reads ``launchTime()``
#: live off the ``once`` tier; this value exists so a test can prove the live
#: read agrees, and so the archive still has an origin when every endpoint is
#: down.
LAUNCH_TIME = 1786910327

#: Every address this module labels, in declaration order.
LABELED_ADDRESSES: tuple[str, ...] = (
    CURATOR,
    DEPLOYER,
    ANNOUNCE,
    ZERO_ADDRESS,
)

#: Lowercase address -> the label a curator widget may render as trusted.
#:
#: This is an **allowlist**.  Anything absent renders dimmed and truncated and
#: is never styled as known.  Do not add a lookalike here "so it can be
#: flagged": the defence is that unknown addresses fall through.
KNOWN_LABELS: dict[str, str] = {
    CURATOR.lower(): "WhitelistCurator",
    DEPLOYER.lower(): "deployer · surfsurf.eth",
    ANNOUNCE.lower(): "announce channel",
    ZERO_ADDRESS.lower(): "zero address",
}

# --- Event topics -----------------------------------------------------------
# Vendored hashes with their preimages beside them.  The preimages are not
# decoration: ``tests/data/test_curator_addresses.py`` recomputes every value
# from them with this repo's keccak, checks the preimage set against
# ``captures/source.sol``, and checks it a third time against the vendored ABI —
# so a matched pair of typos still fails.
#
# Indexed-ness does not enter a topic0 preimage; the *types* do.  Every one of
# these is a canonical signature with ``indexed`` stripped and no argument names.
#
# Three of the six have never fired on chain as of 2026-08-16 21:14 UTC
# (``HourSaved``, ``Settled``, ``Rescued``).  Their decoders therefore ship
# against synthetic rows whose shape comes from the ABI; the test that asserts
# their absence is the signal that a real fixture has become available.

#: ``Launched`` — emitted once, in the creation block.  The ``once`` tier's
#: config cross-check: it carries all seven constructor-time parameters.
TOPIC_LAUNCHED = (
    "0x1a3476a128c728610b72160c5eb1f2448c3acad2fbc009295ed69ac454493f59"
)
#: ``Deposited`` — the one event the whole archive is folded from.  Nine words;
#: ``contributor`` and ``hour`` are indexed, so the hour comes off topic 2 and
#: no timestamp is needed to bucket it.
TOPIC_DEPOSITED = (
    "0xb83850979ca63333b482bfe84d4d7cf15f9cc15c139b1e48bc44eb5446669cb3"
)
#: ``FirstDeposit`` — one per address, with a **1-based** monotonic ``index``
#: (topic 2) that equals ``totalContributors`` at the time it fired.
TOPIC_FIRST_DEPOSIT = (
    "0xe5a1ae9630942d7510b794ac6b487f13176cf55b27415ad75303dd3109242918"
)
#: ``HourSaved`` — a deposit pushed an at-risk hour over the threshold.  Never
#: fired: it needs a *judged* hour, and the game was still in grace at capture.
#: It may never fire at all, and the signal row must render that explicitly
#: rather than wait for a payload.
TOPIC_HOUR_SAVED = (
    "0xab7cfcae8770eb1969d60d0628eee780b803b3872fc3a2f3a261348cee262209"
)
#: ``Settled`` — the obituary, emitted once ever.  It is **not** the source of
#: truth for the phase: ``settle()`` is permissionless and may lag death
#: indefinitely, so the dashboard polls ``isSettled()`` and treats this log as
#: the detail record that arrives later (PRD §3).
TOPIC_SETTLED = (
    "0x0b88c5bd74fc625a4f651904bf835063c6a449220be319924685261fb7709dd5"
)
#: ``Rescued`` — forced ETH swept out.  If it never fires, nothing was ever
#: forced in, which is the expected case.
TOPIC_RESCUED = (
    "0x8aec0ce3dadffacf4b7a963e0fed1ff2e6151b4c95d4a65acafa9d1299630402"
)

#: constant name -> the exact Solidity event signature it hashes.
TOPIC_PREIMAGES: dict[str, str] = {
    "TOPIC_LAUNCHED": (
        "Launched(uint256,uint256,uint256,uint256,uint256,uint256,uint256)"
    ),
    "TOPIC_DEPOSITED": (
        "Deposited(address,uint256,uint256,uint256,uint256,uint256,"
        "uint256,uint256,uint256)"
    ),
    "TOPIC_FIRST_DEPOSIT": "FirstDeposit(address,uint256,uint256)",
    "TOPIC_HOUR_SAVED": "HourSaved(address,uint256,uint256)",
    "TOPIC_SETTLED": "Settled(uint256,uint256,uint256,uint256)",
    "TOPIC_RESCUED": "Rescued(address,uint256)",
}

# --- Function selectors -----------------------------------------------------
# Every literal below was produced with
#   .venv/bin/python -c "from maxpane_dashboard.data.keccak import keccak256_hex; \
#                        print(keccak256_hex(b'<signature>')[:10])"
# and every one is recomputed in-test from the preimage beside it.  The
# preimages themselves are checked against ``captures/source.sol``, and the 21
# parameterless ones are checked against ``captures/batch.json`` — the real
# round publicnode answered on 2026-08-16.  That cross-check is what makes this
# table trustworthy with no network in the suite.
#
# ``isSettled()`` and ``ethNeededThisHour()`` BOTH returned ``0x0`` in that
# round (not settled; grace, so nothing is needed).  Positional reasoning over
# ``results.json`` therefore cannot tell them apart — always key by selector.

# fast tier (8) — one batched eth_call round every 15 s
SEL_IS_SETTLED = "0x3270bb5b"              # isSettled() -> bool
SEL_CURRENT_HOUR = "0x020e185d"            # currentHour()
SEL_CURRENT_HOUR_TOTAL = "0x78f251f3"      # currentHourTotal() -- 0 at every boundary
SEL_ETH_NEEDED_THIS_HOUR = "0xa4586257"    # ethNeededThisHour() -- 0 all through grace
SEL_TIME_LEFT_IN_HOUR = "0x7a7d6632"       # timeLeftInHour() -- hourDuration, never 0
SEL_LAST_ACTIVE_HOUR = "0xa8a036f1"        # lastActiveHour() -> (hour, total)
SEL_EARLY_MULTIPLIER_BPS = "0xd8631b3d"    # earlyMultiplierBps()
SEL_STATS = "0xd80528ae"                   # stats() -> (volume, people, txs)

# once tier (10) — the eight immutables, the constant, and the deployer
SEL_LAUNCH_TIME = "0x790ca413"             # launchTime()
SEL_HOURLY_THRESHOLD = "0x9d99a86d"        # hourlyThreshold()
SEL_GRACE_PERIOD = "0xa06db7dc"            # gracePeriod()
SEL_HOUR_DURATION = "0xda25efd9"           # hourDuration()
SEL_MIN_DEPOSIT = "0x41b3d185"             # minDeposit()
SEL_MIN_ESCALATION = "0x2c379609"          # minEscalation()
SEL_CREDIT_CAP = "0x1ea0466e"              # creditCap()
SEL_FIRST_JUDGED_HOUR = "0x2a9c657f"       # firstJudgedHour()
SEL_POINTS_PER_ETH = "0xc99a340f"          # POINTS_PER_ETH()
SEL_DEPLOYER = "0xd5f39488"                # deployer() -> address

# cross-check (3) — the same three numbers stats() returns, from a *different*
# storage read.  Their agreeing is what makes the slow-tier check meaningful.
# All three are PACKED state variables and their getters return the narrow type,
# not uint256 (see VIEW_RETURN_TYPES); stats() widens the same three on the way
# out.  Every uintN still arrives left-padded in one word, so the decode is the
# same — the width matters only to anyone reasoning about overflow.
SEL_TOTAL_VOLUME = "0x5f81a57c"            # totalVolume()  -> uint128
SEL_TOTAL_CONTRIBUTORS = "0xf251fc8c"      # totalContributors() -> uint64
SEL_TOTAL_TX_COUNT = "0x9b4f50e7"          # totalTxCount() -> uint64

# wallet tier (6) — only when MAXPANE_WALLET is set
SEL_POINTS_OF = "0xcf6a4403"               # pointsOf(address)
SEL_WEIGHT_OF = "0xdd4bc101"               # weightOf(address)
SEL_CONTRIBUTED_BY = "0x64a8e570"          # contributedBy(address)
SEL_TX_COUNT_OF = "0x662d7299"             # txCountOf(address)
SEL_REQUIRED_NEXT = "0xa5f88754"           # requiredNext(address)
#: ``firstHourOf(address) -> (hour, hasJoined)``.  **Two words.**  The raw
#: ``contributors(address)`` struct getter carries a ``firstHour + 1`` offset and
#: is deliberately NOT vendored, so no client can reach the un-shifted value:
#: ``(0, false)`` for a stranger must never render as "joined in hour 0".
SEL_FIRST_HOUR_OF = "0xc5148173"           # firstHourOf(address) -> (uint256, bool)

#: ``previewPoints(uint256)`` — plan amendment A2.  The captured 21-call round
#: holds only parameterless views, so the sqrt curve has no onchain witness at
#: all; the ``once`` tier probes this with one encoded argument so the locally
#: recomputed curve can be compared against the contract's own answer.  It is
#: **not** a member of any ordered parameterless tuple: adding it there would
#: shift every positional decode by one.
SEL_PREVIEW_POINTS = "0x27ca8273"          # previewPoints(uint256)

#: constant name -> the exact Solidity function signature it hashes.
SELECTOR_PREIMAGES: dict[str, str] = {
    "SEL_IS_SETTLED": "isSettled()",
    "SEL_CURRENT_HOUR": "currentHour()",
    "SEL_CURRENT_HOUR_TOTAL": "currentHourTotal()",
    "SEL_ETH_NEEDED_THIS_HOUR": "ethNeededThisHour()",
    "SEL_TIME_LEFT_IN_HOUR": "timeLeftInHour()",
    "SEL_LAST_ACTIVE_HOUR": "lastActiveHour()",
    "SEL_EARLY_MULTIPLIER_BPS": "earlyMultiplierBps()",
    "SEL_STATS": "stats()",
    "SEL_LAUNCH_TIME": "launchTime()",
    "SEL_HOURLY_THRESHOLD": "hourlyThreshold()",
    "SEL_GRACE_PERIOD": "gracePeriod()",
    "SEL_HOUR_DURATION": "hourDuration()",
    "SEL_MIN_DEPOSIT": "minDeposit()",
    "SEL_MIN_ESCALATION": "minEscalation()",
    "SEL_CREDIT_CAP": "creditCap()",
    "SEL_FIRST_JUDGED_HOUR": "firstJudgedHour()",
    "SEL_POINTS_PER_ETH": "POINTS_PER_ETH()",
    "SEL_DEPLOYER": "deployer()",
    "SEL_TOTAL_VOLUME": "totalVolume()",
    "SEL_TOTAL_CONTRIBUTORS": "totalContributors()",
    "SEL_TOTAL_TX_COUNT": "totalTxCount()",
    "SEL_POINTS_OF": "pointsOf(address)",
    "SEL_WEIGHT_OF": "weightOf(address)",
    "SEL_CONTRIBUTED_BY": "contributedBy(address)",
    "SEL_TX_COUNT_OF": "txCountOf(address)",
    "SEL_REQUIRED_NEXT": "requiredNext(address)",
    "SEL_FIRST_HOUR_OF": "firstHourOf(address)",
    "SEL_PREVIEW_POINTS": "previewPoints(uint256)",
}

#: constant name -> how many 32-byte words the return data holds.
#:
#: **Three of these are not 1 and a scalar decode of any of them is a silent
#: bug**: ``stats()`` is three words, ``lastActiveHour()`` and
#: ``firstHourOf()`` are two.  Reading only the first word of ``firstHourOf()``
#: throws away ``hasJoined``, which is the one thing that separates "deposited
#: in hour 0" from "never deposited".
VIEW_RETURN_WORDS: dict[str, int] = {
    "SEL_IS_SETTLED": 1,
    "SEL_CURRENT_HOUR": 1,
    "SEL_CURRENT_HOUR_TOTAL": 1,
    "SEL_ETH_NEEDED_THIS_HOUR": 1,
    "SEL_TIME_LEFT_IN_HOUR": 1,
    "SEL_LAST_ACTIVE_HOUR": 2,
    "SEL_EARLY_MULTIPLIER_BPS": 1,
    "SEL_STATS": 3,
    "SEL_LAUNCH_TIME": 1,
    "SEL_HOURLY_THRESHOLD": 1,
    "SEL_GRACE_PERIOD": 1,
    "SEL_HOUR_DURATION": 1,
    "SEL_MIN_DEPOSIT": 1,
    "SEL_MIN_ESCALATION": 1,
    "SEL_CREDIT_CAP": 1,
    "SEL_FIRST_JUDGED_HOUR": 1,
    "SEL_POINTS_PER_ETH": 1,
    "SEL_DEPLOYER": 1,
    "SEL_TOTAL_VOLUME": 1,
    "SEL_TOTAL_CONTRIBUTORS": 1,
    "SEL_TOTAL_TX_COUNT": 1,
    "SEL_POINTS_OF": 1,
    "SEL_WEIGHT_OF": 1,
    "SEL_CONTRIBUTED_BY": 1,
    "SEL_TX_COUNT_OF": 1,
    "SEL_REQUIRED_NEXT": 1,
    "SEL_FIRST_HOUR_OF": 2,
    "SEL_PREVIEW_POINTS": 1,
}

#: constant name -> the Solidity return types, in order.  **A decode-instruction
#: table**, and every one of the 28 entries is recomputed from ``source.sol`` by
#: ``test_the_return_types_are_recomputed_from_the_verified_source`` and again
#: from the vendored ABI — pinning three of them by hand left the other 25 free
#: to be wrong, and three of them *were*.
#:
#: Only two spellings need special handling at the seam.  ``bool``:
#: ``isSettled()`` and ``firstHourOf()``'s second word — the model field is
#: ``bool | None`` and ``False`` must never be confused with ``None``.
#: ``address``: ``deployer()`` — ``decode_address``, not ``decode_uint``.
#: **Every remaining type is some ``uintN`` and they all decode identically**,
#: left-padded into one 32-byte word, so a decoder branches on the two names
#: above and treats the rest as one case (asserted by
#: ``test_every_declared_return_type_is_bool_address_or_a_uint``).
#:
#: The three counters are **not** ``uint256`` and this file used to say they
#: were: ``totalVolume`` is a ``uint128`` and ``totalContributors`` /
#: ``totalTxCount`` are ``uint64`` (``source.sol`` lines 124-128), packed into
#: one storage slot.  ``stats()`` widens all three to ``uint256`` on the way out,
#: which is why the cross-check group and ``stats()`` disagree here while
#: agreeing on every value.
VIEW_RETURN_TYPES: dict[str, tuple[str, ...]] = {
    "SEL_IS_SETTLED": ("bool",),
    "SEL_CURRENT_HOUR": ("uint256",),
    "SEL_CURRENT_HOUR_TOTAL": ("uint256",),
    "SEL_ETH_NEEDED_THIS_HOUR": ("uint256",),
    "SEL_TIME_LEFT_IN_HOUR": ("uint256",),
    "SEL_LAST_ACTIVE_HOUR": ("uint256", "uint256"),
    "SEL_EARLY_MULTIPLIER_BPS": ("uint256",),
    "SEL_STATS": ("uint256", "uint256", "uint256"),
    "SEL_LAUNCH_TIME": ("uint256",),
    "SEL_HOURLY_THRESHOLD": ("uint256",),
    "SEL_GRACE_PERIOD": ("uint256",),
    "SEL_HOUR_DURATION": ("uint256",),
    "SEL_MIN_DEPOSIT": ("uint256",),
    "SEL_MIN_ESCALATION": ("uint256",),
    "SEL_CREDIT_CAP": ("uint256",),
    "SEL_FIRST_JUDGED_HOUR": ("uint256",),
    "SEL_POINTS_PER_ETH": ("uint256",),
    "SEL_DEPLOYER": ("address",),
    # Packed counters — narrower than stats()'s widened uint256s.  See above.
    "SEL_TOTAL_VOLUME": ("uint128",),
    "SEL_TOTAL_CONTRIBUTORS": ("uint64",),
    "SEL_TOTAL_TX_COUNT": ("uint64",),
    "SEL_POINTS_OF": ("uint256",),
    "SEL_WEIGHT_OF": ("uint256",),
    "SEL_CONTRIBUTED_BY": ("uint256",),
    "SEL_TX_COUNT_OF": ("uint256",),
    "SEL_REQUIRED_NEXT": ("uint256",),
    "SEL_FIRST_HOUR_OF": ("uint256", "bool"),
    "SEL_PREVIEW_POINTS": ("uint256",),
}

# --- The batch contract -----------------------------------------------------
# THESE TUPLES ARE ORDERED AND THE ORDER IS THE CONTRACT.  WP2 sends them in
# order and decodes positionally, so swapping two entries is a silent field
# swap that no WP0 test can see (WP0's subject is the hashes, not the order).
# WP2.4 owns the order test, re-asserted against VIEW_RETURN_WORDS.
#
# fast + once + cross-check == the 21 parameterless calls of captures/batch.json.

#: The 15 s round: eight views, one batched ``eth_call``.
FAST_VIEW_SELECTORS: tuple[tuple[str, str], ...] = (
    ("SEL_IS_SETTLED", SEL_IS_SETTLED),
    ("SEL_CURRENT_HOUR", SEL_CURRENT_HOUR),
    ("SEL_CURRENT_HOUR_TOTAL", SEL_CURRENT_HOUR_TOTAL),
    ("SEL_ETH_NEEDED_THIS_HOUR", SEL_ETH_NEEDED_THIS_HOUR),
    ("SEL_TIME_LEFT_IN_HOUR", SEL_TIME_LEFT_IN_HOUR),
    ("SEL_LAST_ACTIVE_HOUR", SEL_LAST_ACTIVE_HOUR),
    ("SEL_EARLY_MULTIPLIER_BPS", SEL_EARLY_MULTIPLIER_BPS),
    ("SEL_STATS", SEL_STATS),
)

#: Read once and cached forever: nothing on this contract can change them.
ONCE_VIEW_SELECTORS: tuple[tuple[str, str], ...] = (
    ("SEL_LAUNCH_TIME", SEL_LAUNCH_TIME),
    ("SEL_HOURLY_THRESHOLD", SEL_HOURLY_THRESHOLD),
    ("SEL_GRACE_PERIOD", SEL_GRACE_PERIOD),
    ("SEL_HOUR_DURATION", SEL_HOUR_DURATION),
    ("SEL_MIN_DEPOSIT", SEL_MIN_DEPOSIT),
    ("SEL_MIN_ESCALATION", SEL_MIN_ESCALATION),
    ("SEL_CREDIT_CAP", SEL_CREDIT_CAP),
    ("SEL_FIRST_JUDGED_HOUR", SEL_FIRST_JUDGED_HOUR),
    ("SEL_POINTS_PER_ETH", SEL_POINTS_PER_ETH),
    ("SEL_DEPLOYER", SEL_DEPLOYER),
)

#: The slow tier's independent read of ``stats()``'s three numbers.
CROSS_CHECK_VIEW_SELECTORS: tuple[tuple[str, str], ...] = (
    ("SEL_TOTAL_VOLUME", SEL_TOTAL_VOLUME),
    ("SEL_TOTAL_CONTRIBUTORS", SEL_TOTAL_CONTRIBUTORS),
    ("SEL_TOTAL_TX_COUNT", SEL_TOTAL_TX_COUNT),
)

#: The six argument-taking calls, sent only when a wallet is configured.  Each
#: is ``selector + encode_address(wallet)``.
WALLET_VIEW_SELECTORS: tuple[tuple[str, str], ...] = (
    ("SEL_POINTS_OF", SEL_POINTS_OF),
    ("SEL_WEIGHT_OF", SEL_WEIGHT_OF),
    ("SEL_CONTRIBUTED_BY", SEL_CONTRIBUTED_BY),
    ("SEL_TX_COUNT_OF", SEL_TX_COUNT_OF),
    ("SEL_REQUIRED_NEXT", SEL_REQUIRED_NEXT),
    ("SEL_FIRST_HOUR_OF", SEL_FIRST_HOUR_OF),
)
