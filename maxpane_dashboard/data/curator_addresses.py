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
