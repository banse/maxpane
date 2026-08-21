from __future__ import annotations

import pytest

from maxpane_dashboard.data.curator_list_filters import (
    FilterContext,
    FilterDataUnavailable,
    FilterSpec,
    FilterValidationError,
    NftCollectionRef,
    PREDEFINED_NFT_COLLECTIONS,
    custom_nft_label,
    empty_filter_values,
    filter_rows,
    filter_summary,
    parse_filter_values,
    parse_nft_collection,
    preset_filter,
)


def _address(number: int) -> str:
    return f"0x{number:040x}"


def _row(
    rank: int,
    *,
    first_index: int | None = None,
    first_hour: int = 0,
    name: str | None = None,
    points: int | None = None,
    credit: float | None = None,
    weight: float | None = None,
    deposits: int | None = None,
    band: str | None = "clean",
) -> dict:
    return {
        "rank": rank,
        "address": _address(rank),
        "first_index": rank if first_index is None else first_index,
        "first_hour": first_hour,
        "name": name,
        "points": rank * 100 if points is None else points,
        "credit_eth": float(rank) if credit is None else credit,
        "weight_eth": float(rank * 2) if weight is None else weight,
        "tx_count": rank if deposits is None else deposits,
        "link_conf": band,
    }


ROWS = [
    _row(1, first_index=1, first_hour=0, name="one.eth", band="high"),
    _row(2, first_index=1_000, first_hour=23, band="low"),
    _row(3, first_index=1_001, first_hour=24, name="three.eth", band=None),
]


def _context() -> FilterContext:
    return FilterContext(
        families_by_address={
            _address(1): frozenset({"amount", "funding"}),
            _address(2): frozenset({"cadence"}),
        },
        whale_addresses=frozenset({_address(3)}),
    )


@pytest.mark.parametrize(
    ("key", "expected"),
    (("1", [1, 2]), ("2", [1]), ("3", [3])),
)
def test_presets_have_the_approved_exact_boundaries(key, expected):
    result = filter_rows(ROWS, preset_filter(key), _context())
    assert [row["rank"] for row in result] == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        ({"join_min": "1000", "join_max": "1000"}, [2]),
        ({"hour_min": "23", "hour_max": "24"}, [2, 3]),
        ({"rank_min": "2", "rank_max": "3"}, [2, 3]),
        ({"points_min": "200", "points_max": "200"}, [2]),
        ({"credit_min": "2", "credit_max": "2"}, [2]),
        ({"weight_min": "6", "weight_max": "6"}, [3]),
        ({"deposits_min": "3", "deposits_max": "3"}, [3]),
        ({"ens": "set"}, [1, 3]),
        ({"ens": "unset"}, [2]),
        ({"window": "grace"}, [1, 2]),
        ({"window": "judged"}, [3]),
        ({"band": "unknown"}, [3]),
        ({"families": frozenset({"cadence", "funding"})}, [1, 2]),
        ({"whale": True}, [3]),
    ),
)
def test_each_custom_field_is_inclusive(values, expected):
    raw = empty_filter_values()
    raw.update(values)
    result = filter_rows(ROWS, parse_filter_values(raw), _context())
    assert [row["rank"] for row in result] == expected


def test_categories_are_and_but_selected_families_are_or():
    values = empty_filter_values()
    values.update(
        hour_max="23",
        ens="any",
        families=frozenset({"cadence", "funding"}),
    )
    result = filter_rows(ROWS, parse_filter_values(values), _context())
    assert [row["rank"] for row in result] == [1, 2]


def test_no_active_filter_is_an_honest_empty_result():
    spec = parse_filter_values(empty_filter_values())
    assert filter_rows(ROWS, spec, _context()) == []


@pytest.mark.parametrize(
    ("values", "field"),
    (
        ({"hour_min": "-1"}, "hour_min"),
        ({"points_min": "1.5"}, "points_min"),
        ({"credit_min": "nan"}, "credit_min"),
        ({"join_min": "10", "join_max": "9"}, "join_min"),
        ({"ens": "sometimes"}, "ens"),
        ({"families": frozenset({"banana"})}, "families"),
    ),
)
def test_invalid_values_name_the_field(values, field):
    raw = empty_filter_values()
    raw.update(values)
    with pytest.raises(FilterValidationError) as caught:
        parse_filter_values(raw)
    assert caught.value.field == field


def test_missing_evidence_is_reported_only_when_that_filter_needs_it():
    family_values = empty_filter_values()
    family_values["families"] = frozenset({"amount"})
    with pytest.raises(FilterDataUnavailable, match="linked analysis unavailable"):
        filter_rows(ROWS, parse_filter_values(family_values), FilterContext())

    whale_values = empty_filter_values()
    whale_values["whale"] = True
    with pytest.raises(FilterDataUnavailable, match="deposit history unavailable"):
        filter_rows(ROWS, parse_filter_values(whale_values), FilterContext())


def test_summaries_are_stable_and_contain_only_active_values():
    values = empty_filter_values()
    values.update(
        hour_min="0",
        hour_max="0",
        credit_min="25",
        ens="set",
        window="grace",
        families=frozenset({"amount", "funding"}),
    )
    assert filter_summary(parse_filter_values(values)) == (
        "joined hour 0",
        "credit >=25 ETH",
        "ENS set",
        "window grace",
        "amount or funding",
    )


def test_the_four_predefined_nft_collections_are_exact():
    assert [
        (item.label, item.chain, item.address)
        for item in PREDEFINED_NFT_COLLECTIONS
    ] == [
        (
            "Identity.md",
            "ethereum",
            "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d",
        ),
        (
            "Fren Pet",
            "base",
            "0x5b51cf49cb48617084ef35e7c7d7a21914769ff1",
        ),
        (
            "Milady",
            "ethereum",
            "0x5af0d9827e0c53e4799bb226655a1de152a425a5",
        ),
        (
            "Crypto Punks",
            "ethereum",
            "0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb",
        ),
    ]


def test_custom_nft_collections_validate_normalise_and_deduplicate():
    address = "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD"
    spec = parse_filter_values(
        {
            "nft_collections": (
                {"chain": "base", "address": address},
                {"chain": "base", "address": address.lower()},
            )
        }
    )
    assert spec.nft_collections == (
        NftCollectionRef(
            chain="base",
            address=address.lower(),
            label="BASE 0xabcd…abcd",
        ),
    )
    assert custom_nft_label("ethereum", address.lower()) == "ETH 0xabcd…abcd"


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ({"chain": "arbitrum", "address": "0x" + "1" * 40}, "nft_collections"),
        ({"chain": "ethereum", "address": "0x1234"}, "nft_collections"),
        ({"chain": "ethereum", "address": "0x" + "z" * 40}, "nft_collections"),
    ],
)
def test_invalid_custom_nft_collections_name_the_editor_field(value, field):
    with pytest.raises(FilterValidationError) as caught:
        parse_filter_values({"nft_collections": (value,)})
    assert caught.value.field == field


def test_selected_nft_collections_are_or_with_each_other_and_and_with_points():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    rows = [
        {"address": "0x" + "1" * 40, "points": 10},
        {"address": "0x" + "2" * 40, "points": 20},
        {"address": "0x" + "3" * 40, "points": 30},
    ]
    context = FilterContext(
        nft_holders_by_collection={
            identity.key: frozenset({rows[0]["address"]}),
            frenpet.key: frozenset({rows[1]["address"]}),
        }
    )
    spec = FilterSpec(
        points_min=15,
        nft_collections=(identity, frenpet),
    )
    assert [row["address"] for row in filter_rows(rows, spec, context)] == [
        rows[1]["address"]
    ]


@pytest.mark.parametrize(
    ("spec_values", "first_values", "second_values"),
    (
        ({"join_min": 2}, {"first_index": 2}, {"first_index": 1}),
        ({"hour_min": 2}, {"first_hour": 2}, {"first_hour": 1}),
        ({"rank_min": 2}, {"rank": 2}, {"rank": 1}),
        ({"points_min": 2}, {"points": 2}, {"points": 1}),
        ({"credit_min": 2}, {"credit_eth": 2}, {"credit_eth": 1}),
        ({"weight_min": 2}, {"weight_eth": 2}, {"weight_eth": 1}),
        ({"deposits_min": 2}, {"tx_count": 2}, {"tx_count": 1}),
        ({"ens": "set"}, {"name": "one.eth"}, {"name": None}),
        ({"window": "judged"}, {"first_hour": 24}, {"first_hour": 0}),
        ({"band": "high"}, {"link_conf": "high"}, {"link_conf": "clean"}),
    ),
)
def test_nft_category_ands_with_each_row_backed_category(
    spec_values, first_values, second_values
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    first = {"address": "0x" + "1" * 40, **first_values}
    second = {"address": "0x" + "2" * 40, **second_values}
    context = FilterContext(nft_holders_by_collection={
        collection.key: frozenset({first["address"], second["address"]})
    })
    spec = FilterSpec(nft_collections=(collection,), **spec_values)
    assert filter_rows([first, second], spec, context) == [first]


def test_nft_category_ands_with_linked_family_and_whale_evidence():
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    first = "0x" + "1" * 40
    second = "0x" + "2" * 40
    rows = [{"address": first}, {"address": second}]
    holders = {collection.key: frozenset({first, second})}
    family_context = FilterContext(
        families_by_address={
            first: frozenset({"amount"}),
            second: frozenset({"funding"}),
        },
        nft_holders_by_collection=holders,
    )
    assert filter_rows(
        rows,
        FilterSpec(
            families=frozenset({"amount"}),
            nft_collections=(collection,),
        ),
        family_context,
    ) == [rows[0]]
    whale_context = FilterContext(
        whale_addresses=frozenset({first}),
        nft_holders_by_collection=holders,
    )
    assert filter_rows(
        rows,
        FilterSpec(whale=True, nft_collections=(collection,)),
        whale_context,
    ) == [rows[0]]


def test_every_selected_nft_collection_must_have_truthful_holder_data():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    with pytest.raises(FilterDataUnavailable, match="NFT holder data"):
        filter_rows(
            [{"address": "0x" + "1" * 40}],
            FilterSpec(nft_collections=(identity, frenpet)),
            FilterContext(
                nft_holders_by_collection={identity.key: frozenset()}
            ),
        )


def test_nft_filter_summary_is_stable_and_last():
    identity, frenpet = PREDEFINED_NFT_COLLECTIONS[:2]
    assert filter_summary(
        FilterSpec(
            join_min=1,
            join_max=100,
            nft_collections=(identity, frenpet),
        )
    ) == (
        "join #1-100",
        "NFT Identity.md or Fren Pet",
    )


def test_integer_bounds_remain_exact_above_binary_float_precision():
    exact = 2**53 + 1
    spec = parse_filter_values({"points_max": str(exact - 1)})
    assert filter_rows(
        [{"address": "0x" + "1" * 40, "points": exact}],
        spec,
        FilterContext(),
    ) == []
