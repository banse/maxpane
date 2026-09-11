"""The data contract for surf's `4` POOL4 MARKET body (WP0).

Nothing else in that work stream may start until these names exist: five work
packages build against this tuple, and a hand-typed second spelling anywhere
else is the drift the frozen contract exists to make impossible.

The count assertion below is deliberately a hand-typed literal rather than
``len(POOL4_KEYS) == len(POOL4_KEYS)`` in disguise -- it is the tripwire, on
``CURATOR_ANALYSIS_KEYS``'s shape, and it was proven to bite by deleting a key
and watching this file redden naming the missing one.
"""

from maxpane_dashboard.data import surf_models as m


def test_the_nine_fast_tier_keys_joined_pool4_keys():
    added = (
        "pool4_reference_pool_tick",
        "pool4_venue_gap_pct",
        "pool4_cheaper_venue",
        "pool4_price_usd",
        "pool4_backstop_lower_tick",
        "pool4_backstop_liquidity",
        "pool4_backstop_eth",
        "pool4_backstop_state",
        "pool4_trailing_return_pct",
    )
    for key in added:
        assert key in m.POOL4_KEYS, key
    assert len(m.POOL4_KEYS) == 71


def test_the_cross_venue_key_does_not_borrow_the_internal_ref_tick_name():
    """`pool4_ref_tick` is the hook's own lagged anti-manipulation tick.

    Two things called "ref tick" in one payload is how a wrong number renders
    confidently, so the cross-venue read carries the longer name and both
    survive. PRD 7.1.
    """
    assert "pool4_ref_tick" in m.POOL4_KEYS
    assert "pool4_reference_pool_tick" in m.POOL4_KEYS
    assert m.POOL4_KEYS.count("pool4_ref_tick") == 1


def test_the_trailing_return_is_not_the_delivery_cap_key():
    """`pool4_implied_apr_pct` is the drip *cap* annualised -- a ceiling, not
    a yield. The realised number gets its own key or the vault panel's whole
    refusal to say APR is undone one payload later. PRD 8.1."""
    assert "pool4_implied_apr_pct" in m.POOL4_KEYS
    assert "pool4_trailing_return_pct" in m.POOL4_KEYS


def test_the_staker_sweep_keys_are_their_own_tuple():
    assert m.POOL4_STAKERS_KEYS == (
        "pool4_stakers",
        "pool4_staker_count",
        "pool4_staker_top3_pct",
        "pool4_stakers_as_of_hhmm",
    )
    for key in m.POOL4_STAKERS_KEYS:
        assert key in m.SURF_KEYS


def test_the_staker_sweep_gets_its_own_tier_and_slot_on_the_analysis_shape():
    """The plan freezes two names in `surf_cache` and gives them values; the
    test file it ships never looks at either, so this closes that gap.

    The shape is curator's ``TIER_ANALYSIS``: a long TTL with a much shorter
    failure backoff, so a rate-limited endpoint costs minutes rather than the
    full half hour, and its own last-good slot so the fold can serve stale
    behind its own marker.

    The slot is **not** a ninth degraded group -- PRD 7.3: ``SOURCE_POOL4``
    ("p4") is the eighth and last name the title row has columns for.
    """
    from maxpane_dashboard.data import surf_cache as c

    assert c.TIER_POOL4_STAKERS in c.TIERS
    assert c.TIER_POOL4_STAKERS != c.TIER_POOL4
    assert c.TIER_TTL_SECONDS[c.TIER_POOL4_STAKERS] == 1800.0
    assert c.TIER_FAILURE_BACKOFF_SECONDS[c.TIER_POOL4_STAKERS] == 300.0
    assert (
        c.TIER_FAILURE_BACKOFF_SECONDS[c.TIER_POOL4_STAKERS]
        < c.TIER_TTL_SECONDS[c.TIER_POOL4_STAKERS]
    )
    # Slower than the sweep it rides beside, which is the whole reason it is
    # a second tier rather than nine more keys on the first.
    assert (
        c.TIER_TTL_SECONDS[c.TIER_POOL4_STAKERS]
        > c.TIER_TTL_SECONDS[c.TIER_POOL4]
    )

    assert c.SLOT_POOL4_STAKERS in c.SLOTS
    assert c.SLOT_POOL4_STAKERS != c.SLOT_POOL4

    from maxpane_dashboard.data.surf_manager import GROUP_SLOT

    assert c.SLOT_POOL4_STAKERS not in set(GROUP_SLOT.values())


def test_the_three_vocabularies_are_frozen():
    assert m.POOL4_VENUE_WORDS == ("here", "reference")
    assert m.POOL4_BACKSTOP_STATES == ("deployed", "none")
    assert m.POOL4_BURNING_STATES == ("on", "off")
