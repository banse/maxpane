"""``tests/screens/_sweeps.boundary_set`` -- the set every collapsed layout
sweep runs over (HANDOVER.md §2.3, terminal-layout skill).

Lives outside ``tests/screens`` on purpose: it composites nothing and must
not carry the ``screen`` marker.
"""

from __future__ import annotations

import pytest

from tests.screens._sweeps import boundary_set


def test_both_ends_the_pin_and_each_threshold_with_their_neighbours():
    assert boundary_set(116, 60, 159, 129) == [60, 115, 116, 117, 128, 129, 130, 159]


def test_hi_is_inclusive_and_duplicates_collapse():
    # The pin is also a threshold; pin+1 is hi. Nothing is listed twice.
    assert boundary_set(45, 36, 46, 45) == [36, 44, 45, 46]


def test_neighbours_outside_the_band_are_clipped_not_added():
    # A pin one under the band's floor: only its +1 survives (as lo).
    assert boundary_set(111, 112, 120) == [112, 120]


def test_a_pin_far_outside_the_band_leaves_just_the_ends():
    assert boundary_set(5, 10, 20) == [10, 20]


def test_an_empty_band_is_refused():
    with pytest.raises(ValueError):
        boundary_set(10, 20, 10)


def test_the_result_is_sorted_ascending():
    s = boundary_set(99, 86, 152, 143, 138)
    assert s == sorted(s)
