"""Status enums for the Fake World Assets (FWA) protocol.

Provenance
----------
These are the REAL member names, not guesses. Both enums were read from the
Etherscan-verified source of the FWA core contract
``0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c`` -- file ``src/FWA.sol``,
lines 82-103 -- retrieved keylessly on 2026-07-27 by
``scripts/vendor_fwa_abis.py --fetch``.

They are transcribed here rather than parsed at import time because member
names do not survive ABI encoding: both enums appear in the ABI as a bare
``uint8``, and the ABI is all the runtime has. Re-running the vendoring script
with ``--fetch`` re-prints both definitions, so drift against a redeployed
contract is visible without hand-diffing Solidity.

``docs/fwa_technical_findings.md`` §6.6 and §12.2 item 4 list these enums as
unresolved -- "status == 1 = Active empirically; values 2, 3, 4 seen but
undefined". That question is now closed, and the empirical reading holds:
``ListingStatus(1) == Active``. The three other observed values, 2/3/4, are
``Allocated`` / ``Withdrawn`` / ``Settled``. Nothing had to be inferred.

This module is deliberately inert: standard library only, no network, no I/O,
no dependency on ``scripts/``.
"""

from __future__ import annotations

__all__ = [
    "LISTING_STATUS",
    "ACQUISITION_STATUS",
    "LISTING_STATUS_ACTIVE",
    "listing_status_label",
    "acquisition_status_label",
]


# ---------------------------------------------------------------------------
# enum ListingStatus  --  src/FWA.sol L82-92
#
# The trailing source comment on `Staged` is worth keeping: it is a deposit
# made while an acquisition is unresolved -- escrowed but NOT yet in the
# selection pool. A later request may reserve it before asking VRF; otherwise
# it activates once the sequencer is idle. It was appended last specifically so
# the pre-existing numeric listing states stayed stable, which is why a
# position in the staging line reads 5 and not something in the middle.
# ---------------------------------------------------------------------------
LISTING_STATUS: dict[int, str] = {
    0: "None",
    1: "Active",
    2: "Allocated",
    3: "Withdrawn",
    4: "Settled",
    5: "Staged",
}

# ---------------------------------------------------------------------------
# enum AcquisitionStatus  --  src/FWA.sol L94-103
#
# Source comments, verbatim in intent:
#   Pending    waiting for an on-time VRF word
#   Expired    skipped in sequence after its word deadline; escrowed fee
#              credited for withdrawal
#   Refunded   no listing / slippage refund; escrowed fee credited for
#              withdrawal
#   Ready      an on-time word is cached and must be settled in request order
#   TimedOut   a callback arrived after its deadline; the request is skipped
#              when it reaches the head
#
# Note that Expired and TimedOut are NOT synonyms: Expired means no word
# arrived in time, TimedOut means one arrived too late to be usable. Both leave
# the request skippable, but only Expired credits at the deadline.
# ---------------------------------------------------------------------------
ACQUISITION_STATUS: dict[int, str] = {
    0: "None",
    1: "Pending",
    2: "Fulfilled",
    3: "Expired",
    4: "Refunded",
    5: "Ready",
    6: "TimedOut",
}

# The one value the enumerator filters on. Named so call sites do not sprinkle
# bare `== 1` around (findings §6: every live position reads 1).
LISTING_STATUS_ACTIVE = 1


def listing_status_label(n: int) -> str:
    """Human label for a ``ListingStatus`` value.

    Returns ``"status {n}"`` for any value not in the recovered enum. An
    unrecognised value means the contract was redeployed with a longer enum, so
    the honest fallback is the raw number -- never a plausible-looking guess.
    """
    return LISTING_STATUS.get(n, f"status {n}")


def acquisition_status_label(n: int) -> str:
    """Human label for an ``AcquisitionStatus`` value.

    Same contract as :func:`listing_status_label`: unknown values render as
    ``"status {n}"`` rather than being coerced into a neighbouring name.
    """
    return ACQUISITION_STATUS.get(n, f"status {n}")
