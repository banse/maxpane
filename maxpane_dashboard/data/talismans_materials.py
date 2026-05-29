"""Material ID → (name, essence) map for the Talismans NFT collection.

Essences:
  "Lithic"  — matter essence (earth/stone/crystal)
  "Lumic"   — event essence (light/energy/phenomenon)
  "Mythic"  — synthesis essence (rare combinatoric materials)

The integer keys are the ``materialId`` values stored on-chain in the
Talismans contract.  IDs 0–31 cover Lumic and Lithic materials; IDs 32–47
are all Mythic.
"""

from __future__ import annotations

MATERIALS: dict[int, tuple[str, str]] = {
    0: ("Aurora", "Lumic"), 1: ("Foxfire", "Lithic"), 2: ("Pulsarlike", "Lumic"), 3: ("Amethyst", "Lithic"),
    4: ("Citrine", "Lithic"), 5: ("Fire Obsidian", "Lithic"), 6: ("Duskhollow", "Lumic"), 7: ("Sakura", "Lumic"),
    8: ("Rainforest", "Lumic"), 9: ("Embermade", "Lithic"), 10: ("Abyss", "Lumic"), 11: ("Bloodmoon", "Lumic"),
    12: ("Sugilite", "Lithic"), 13: ("Bored Ruby", "Lithic"), 14: ("Dawnstone", "Lithic"), 15: ("Diamond", "Lithic"),
    16: ("Rock", "Lithic"), 17: ("Daystar", "Lumic"), 18: ("Tsavorite", "Lithic"), 19: ("Rhodochrosite", "Lithic"),
    20: ("Copper", "Lithic"), 21: ("Foxglow", "Lumic"), 22: ("Sealume", "Lumic"), 23: ("Aquamarine", "Lithic"),
    24: ("Blazar", "Lumic"), 25: ("Sproutsong", "Lumic"), 26: ("Heartfern", "Lumic"), 27: ("Moss", "Lumic"),
    28: ("Cobalt", "Lithic"), 29: ("Emerald", "Lithic"), 30: ("Wisp", "Lumic"), 31: ("Twilight", "Lumic"),
    32: ("Corona", "Mythic"), 33: ("Strobeflora", "Mythic"), 34: ("Sigil", "Mythic"), 35: ("Smokeblossom", "Mythic"),
    36: ("Saint Spectrum", "Mythic"), 37: ("Cypher", "Mythic"), 38: ("Aether", "Mythic"), 39: ("Deadform", "Mythic"),
    40: ("Nullbloom", "Mythic"), 41: ("Reliquary", "Mythic"), 42: ("Duskcode", "Mythic"), 43: ("Phosphor", "Mythic"),
    44: ("Celestial", "Mythic"), 45: ("Corposant", "Mythic"), 46: ("Wraithseal", "Mythic"), 47: ("Wraithseal+", "Mythic"),
}

_TIER_BY_CORES = {1: "Raw", 2: "Cut", 3: "Fine", 4: "Prime"}


def essence_of(material_id: int) -> str:
    """Return the essence string for a material ID, or ``"--"`` if unknown."""
    return MATERIALS.get(material_id, ("?", "--"))[1]


def material_name(material_id: int) -> str:
    """Return the display name for a material ID, or ``"Unknown"`` if unknown."""
    return MATERIALS.get(material_id, ("Unknown", "--"))[0]


def tier_name(core_count: int) -> str:
    """Map a talisman's core count to its tier label.

    * 1 core  → Raw
    * 2 cores → Cut
    * 3 cores → Fine
    * 4 cores → Prime
    * 5–8     → Bonded
    * other   → "--"
    """
    if core_count in _TIER_BY_CORES:
        return _TIER_BY_CORES[core_count]
    if 5 <= core_count <= 8:
        return "Bonded"
    return "--"
