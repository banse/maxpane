"""``_swarm_chain`` -- the swarm body's shared chain-id-to-word vocabulary.

Task 9's hoist: THROUGHPUT (Task 8) and JUST SHIPPED (Task 9) both need to
turn a raw numeric chain id into a network word (a known id's word, or the
em dash for anything else), so the map and helper now live in one module
(``maxpane_dashboard.widgets.surf._swarm_chain``) instead of being copied a
second and then a third time. This file is the redundancy-plus-agreement-
test half of that hoist, moved here verbatim from
``tests/widgets/test_surf_swarm_rail.py`` alongside the map it protects.
"""

from maxpane_dashboard.data.surf_swarm import _NETWORKS as _SWARM_CHAIN_NETWORKS
from maxpane_dashboard.widgets.surf._pool4 import NETWORK_UNKNOWN
from maxpane_dashboard.widgets.surf._swarm_chain import CHAIN_ID_WORDS, chain_word


def test_the_chain_id_allowlist_agrees_with_data_surf_swarm():
    """``_swarm_chain.CHAIN_ID_WORDS`` restates ``data/surf_swarm._NETWORKS``
    because a widget may not import ``data/`` (contract §0.5) -- the same
    reason ``_pool4.NETWORK_WORDS`` restates ``surf_models.POOL4_NETWORKS``.
    Dict equality is symmetric by construction, so this one assertion
    catches both directions the ruling named: a chain id added to the
    fold's map and not the widget's breaks it (that chain would silently
    render the em dash on screen while the data layer already has a name
    for it), and a chain id invented in the widget with no contract entry
    behind it breaks it too.
    """
    assert CHAIN_ID_WORDS == _SWARM_CHAIN_NETWORKS


def test_a_known_chain_id_resolves_its_word():
    assert chain_word(1) == "MAINNET"
    assert chain_word(11155111) == "SEPOLIA"


def test_an_unknown_or_missing_chain_id_renders_the_dash():
    """An allowlist, not a pass-through: ``None``, an unrecognised id and a
    ``bool`` (an ``int`` subclass, but never a chain id) all fall to the em
    dash rather than a guess.
    """
    assert chain_word(None) == NETWORK_UNKNOWN
    assert chain_word(999999999) == NETWORK_UNKNOWN
    assert chain_word(True) == NETWORK_UNKNOWN
    assert chain_word(False) == NETWORK_UNKNOWN
