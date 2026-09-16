"""Shared chain-id-to-word vocabulary for the swarm body's panels.

**Why this module exists.** THROUGHPUT (Task 8) needed to turn a raw numeric
``last_chain_id`` into a network word and wrote ``_CHAIN_ID_WORDS`` plus a
``_chain_word`` helper to do it, restating ``data/surf_swarm._NETWORKS``
because a widget may not import ``data/`` (contract §0.5). JUST SHIPPED
(Task 9) needs the identical translation for each shipped row's own
``chain_id`` -- the design doc's request to put the chain word in this
panel's title was overruled in favour of one word per row (the rows mix
chains: launches are mostly Sepolia, abandoned ones mainnet, so a single
title word would be confidently wrong for some rows under it), which makes
the *need* for the id-to-word step identical to THROUGHPUT's, not merely
similar. Writing a third copy is exactly the divergence CLAUDE.md's *Reuse
before you build* warns about -- "three copies of one helper means a fix
reaches one of them" -- so this module is the hoist: both panels import
:data:`CHAIN_ID_WORDS` and :func:`chain_word` from here now, and
``swarm_throughput.py`` keeps a module-level ``_CHAIN_ID_WORDS``/
``_chain_word``/``_CHAIN_COLS`` only as *bound names* re-exported from this
module, not as a second definition.

The allowlist, restated
------------------------
:data:`CHAIN_ID_WORDS` mirrors ``data/surf_swarm._NETWORKS`` (``{1:
"MAINNET", 11155111: "SEPOLIA"}``), and the two are kept in agreement by
:func:`test_the_chain_id_allowlist_agrees_with_data_surf_swarm` in
``tests/widgets/test_surf_swarm_chain.py`` -- the same redundancy-plus-
agreement-test shape ``_pool4.NETWORK_WORDS``/``surf_models.POOL4_NETWORKS``
already uses, moved here with the map it protects rather than left behind in
``swarm_throughput.py``'s own test file. Dict equality is symmetric, so one
assertion catches both directions: a chain id added to the fold's map and
not here breaks it (that chain would silently render the em dash on screen
while the data layer already has a name for it), and a chain id invented
here with no contract entry behind it breaks it too.

:func:`chain_word` is an allowlist, not a pass-through, exactly like
``_pool4.network_word`` (which it delegates to for the final validation
step): an id outside :data:`CHAIN_ID_WORDS` -- ``None`` and ``bool``
included -- renders the em dash rather than a guess. ``bool`` is excluded
before the ``int`` check because ``True``/``False`` are ``int`` subclasses
in Python and neither is a chain id.

Purity
------
Stdlib, plus this package's own ``_pool4.network_word``. No ``data/``, no
``analytics/``, no ``textual``, no clock, no I/O.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.surf._pool4 import network_word

__all__ = ["CHAIN_COLS", "CHAIN_ID_WORDS", "chain_word"]

#: Chain id -> the pre-resolved word ``_pool4.network_word`` validates.
#: Restated from ``data/surf_swarm._NETWORKS`` because a widget may not
#: import ``data/``; kept honest by the agreement test named above.
CHAIN_ID_WORDS = {1: "MAINNET", 11155111: "SEPOLIA"}

#: Widest chain word this allowlist can print (``SEPOLIA``/``MAINNET``, 7
#: cells); ``_pool4.NETWORK_UNKNOWN`` (the em dash) is one cell and pads out
#: to the same column. Tied one-to-one to :data:`CHAIN_ID_WORDS` -- both
#: consumers reserve exactly this many cells for a chain word, so it is
#: hoisted alongside the map rather than measured twice.
CHAIN_COLS = 7


def chain_word(chain_id: object) -> str:
    """A raw ``chain_id`` (``last_chain_id`` / a shipped row's own
    ``chain_id``) -> a network word, or :data:`_pool4.NETWORK_UNKNOWN`.

    An allowlist, not a pass-through -- see the module docstring.
    """
    if isinstance(chain_id, int) and not isinstance(chain_id, bool):
        return network_word(CHAIN_ID_WORDS.get(chain_id))
    return network_word(None)
