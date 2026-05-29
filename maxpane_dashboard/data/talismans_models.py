"""Pydantic models for the Talismans NFT dashboard data.

These are the internal data shapes the Talismans dashboard manipulates between
the data layer (WP3) and the widgets/screen (WP4/WP5).  All models are frozen
so they can be safely shared across the snapshot pipeline.

Naming notes (see ``docs/talismans_abi_recon.md``):

* ``core_count`` is the number of cores in a talisman (1 = Raw, 2 = Cut,
  3 = Fine, 4 = Prime, 5–8 = Bonded).
* ``materialId`` is the on-chain integer mapped to (name, essence) via
  ``talismans_materials.MATERIALS``.
* ``form`` is the on-chain shape index (0–N), purely cosmetic.
* ``seed`` is the on-chain randomness seed used for visual generation.
* Genesis talismans (``is_genesis=True``) are the 1 536 original mints;
  all subsequent tokens are produced via transformation operations.
* ``cores_invariant_baseline`` in ``TalismanCollectionState`` captures the
  total core count at a reference snapshot — used to verify the conservation
  invariant: operations only *rearrange* cores between tokens, so the total
  core count never changes (only the token count fluctuates).

``essence`` and ``tier`` on ``TalismanToken`` are denormalized for display
(matching the TTT model pattern).  The data layer (WP3) is the single populator
and derives them via ``talismans_materials.essence_of`` / ``tier_name``, so they
are consistent with ``material_id`` / ``core_count`` by construction; the model
does not re-validate them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "TalismanToken",
    "TalismanActivityEvent",
    "TalismanSignal",
    "TalismanCollectionState",
]


class TalismanToken(BaseModel):
    """One Talisman NFT token with its on-chain attributes."""

    model_config = ConfigDict(frozen=True)

    token_id: int
    owner: str                        # checksummed or lowercased 0x address
    core_count: int                   # number of fused cores (1–8)
    material_id: int                  # on-chain materialId (0–47)
    essence: str                      # "Lithic" | "Lumic" | "Mythic"
    form: int                         # cosmetic shape index
    seed: int                         # on-chain RNG seed
    tier: str                         # "Raw" | "Cut" | "Fine" | "Prime" | "Bonded"
    is_genesis: bool                  # True for the 1 536 original mint tokens


class TalismanActivityEvent(BaseModel):
    """Single event for the Talismans activity feed.

    ``op_type`` is one of (see ``docs/talismans_abi_recon.md``):
    * ``"bond"``   — fuse a matter + event token into a Mythic (−1 token)
    * ``"cleave"`` — split a Mythic back into a Lithic + a Lumic (+1 token)
    * ``"cut"``    — split a token into two of the same material (+1 token)
    * ``"merge"``  — recombine two same-material tokens into one (−1 token)

    ``token_id_a`` / ``token_id_b`` are the input token IDs (b is None for
    single-input ops).  ``result_id`` is the surviving or newly minted token.
    """

    model_config = ConfigDict(frozen=True)

    tx_hash: str
    block_number: int
    timestamp: int                    # unix seconds
    op_type: str                      # "bond" | "cleave" | "cut" | "merge"
    token_id_a: int | None = None
    token_id_b: int | None = None
    result_id: int | None = None
    operator: str | None = None       # msg.sender address
    essence: str | None = None        # resulting talisman's essence after op
    tier: str | None = None           # resulting talisman's tier after op


class TalismanSignal(BaseModel):
    """One row of the Signals panel."""

    model_config = ConfigDict(frozen=True)

    label: str
    value_str: str
    indicator: str                    # colored dot or symbol (e.g. "●", "►")
    color: str                        # "green" | "yellow" | "red" | "dim"


class TalismanCollectionState(BaseModel):
    """Collection-wide aggregate state for one poll cycle."""

    model_config = ConfigDict(frozen=True)

    live_tokens: int                  # current total supply (non-burned)
    genesis_minted: int               # original mint count (≤ 1 536)
    total_cores: int                  # sum of core_count across all live tokens
    cores_invariant_baseline: int     # reference snapshot for conservation check
    mythic_count: int                 # tokens whose essence == "Mythic"
    essence_counts: dict[str, int]    # {"Lithic": n, "Lumic": n, "Mythic": n}
    tier_counts: dict[str, int]       # {"Raw": n, "Cut": n, "Fine": n, "Prime": n, "Bonded": n}
    current_block: int
