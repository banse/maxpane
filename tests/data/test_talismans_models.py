import pytest
from maxpane_dashboard.data.talismans_materials import (
    MATERIALS, essence_of, material_name, tier_name,
)
from maxpane_dashboard.data.talismans_models import (
    TalismanToken, TalismanActivityEvent, TalismanSignal, TalismanCollectionState,
)


def test_materials_map_is_total_0_to_47():
    assert set(MATERIALS.keys()) == set(range(48))


def test_essence_lookup_matches_recon():
    assert essence_of(0) == "Lumic"
    assert essence_of(1) == "Lithic"
    assert essence_of(32) == "Mythic"
    assert essence_of(47) == "Mythic"


def test_material_name():
    assert material_name(0) == "Aurora"
    assert material_name(15) == "Diamond"


def test_tier_name_by_core_count():
    assert tier_name(1) == "Raw"
    assert tier_name(2) == "Cut"
    assert tier_name(3) == "Fine"
    assert tier_name(4) == "Prime"
    assert tier_name(5) == "Bonded"
    assert tier_name(8) == "Bonded"
    assert tier_name(0) == "--"


def test_token_is_frozen_and_classifies():
    t = TalismanToken(token_id=1, owner="0xabc", core_count=2, material_id=0,
                      essence="Lumic", form=2, seed=0x26bc, tier="Cut", is_genesis=True)
    assert t.tier == "Cut" and t.essence == "Lumic"
    with pytest.raises(Exception):
        t.core_count = 3


def test_activity_event_optional_fields():
    e = TalismanActivityEvent(tx_hash="0x1", block_number=10, timestamp=100,
                              op_type="bond", token_id_a=262, token_id_b=263, result_id=1537)
    assert e.op_type == "bond" and e.operator is None


def test_signal_color_field():
    s = TalismanSignal(label="CONSERVATION", value_str="INTACT", indicator="●", color="green")
    assert s.color == "green"


def test_collection_state_dicts():
    s = TalismanCollectionState(live_tokens=1448, genesis_minted=1536, total_cores=3000,
                                cores_invariant_baseline=3000, mythic_count=20,
                                essence_counts={"Lithic": 700, "Lumic": 728, "Mythic": 20},
                                tier_counts={"Raw": 500}, current_block=25203610)
    assert s.essence_counts["Mythic"] == 20
