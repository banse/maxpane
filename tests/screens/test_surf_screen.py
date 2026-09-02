"""Headless Textual tests for the surf dashboard screen (WP5).

A fake manager returns the frozen ``SURF_KEYS`` dict (no network), the screen
is pushed via ``App.run_test()``, and we assert against **composited output**
(``_compositor.render_strips()``), never a widget's content string alone.

Zero network, zero wall clock: every time-derived string
(``feed_last_post_age_s``, signal ages) arrives pre-computed in the payload,
which is why the fetch instant 2026-08-08T04:00:00Z can be replayed forever.
All sample values are lifted from ``tests/fixtures/surf/captures/`` -- the real
payloads fetched 2026-08-08 -- not invented.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard import __version__
from maxpane_dashboard.data.surf_models import (
    POOL4_KEYS,
    POOL4_COUNTER_STATES,
    POOL4_DISCOVERY_SOURCES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_SIDES,
    POOL4_HATCH_LABELS,
    POOL4_HATCH_SCOPES,
    POOL4_HATCH_STATES,
    POOL4_NETWORKS,
    POOL4_REWARD_PATHS,
    SURF_KEYS,
)
from maxpane_dashboard.screens.surf import (
    INITIAL_TITLE,
    LAUNCHPAD_BODY_ID,
    LAUNCHPAD_LEFT_ID,
    LAUNCHPAD_RAIL_ID,
    MODE_DASHBOARD,
    MODE_LAUNCHPAD,
    MODE_POOL4,
    POOL4_BODY_ID,
    POOL4_LEFT_ID,
    POOL4_RAIL_ID,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_ROWS,
    SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_ROWS,
    TALLER_HINT,
    SurfScreen,
)
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf.market import (
    PANEL_TITLE,
    POOL_UNVERIFIED_HINT,
    POOL_UNVERIFIED_SHORT,
)
from maxpane_dashboard.widgets.surf import (
    SurfBurnkeepers,
    SurfBurnPipeline,
    SurfCurveFlow,
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfLaunchpadActivity,
    SurfLaunchpadCoins,
    SurfMarket,
    SurfNft,
    SurfPool4Flow,
    SurfPool4Hatches,
    SurfPool4Ratchet,
    SurfPool4Split,
    SurfPool4Vault,
    SurfSignals,
)

_THEMES = Path(__file__).resolve().parents[2] / "maxpane_dashboard" / "themes"
_TCSS = _THEMES / "minimal.tcss"

#: The six dashboard-body widgets: always mounted, always ``display is True``
#: (``test_screen_mounts_all_six_widgets``'s "nothing is hidden" check).  The
#: launchpad trio is a separate mapping (:data:`_LAUNCHPAD_WIDGET_CLASSES`)
#: precisely because it is *not* always visible -- it is composed hidden and
#: only ``l`` shows it, so folding it into this dict would make that same
#: "nothing is hidden" check false the moment it was added.
_WIDGET_CLASSES = {
    "SurfHero": SurfHero,
    "SurfSignals": SurfSignals,
    "SurfFeed": SurfFeed,
    "SurfDevActivity": SurfDevActivity,
    "SurfMarket": SurfMarket,
    "SurfNft": SurfNft,
}

#: The ``l`` LAUNCHPAD body's three widgets (2026-08-23).  Kept apart from
#: :data:`_WIDGET_CLASSES` for the reason documented there; combined with it
#: as :data:`_ALL_WIDGET_CLASSES` for the dispatch-completeness tests, which
#: care whether ``update_data`` was called, not whether the widget is shown.
_LAUNCHPAD_WIDGET_CLASSES = {
    "SurfLaunchpadCoins": SurfLaunchpadCoins,
    "SurfLaunchpadActivity": SurfLaunchpadActivity,
    "SurfCurveFlow": SurfCurveFlow,
    "SurfBurnPipeline": SurfBurnPipeline,
    "SurfBurnkeepers": SurfBurnkeepers,
}

#: The ``p`` POOL4 body's five widgets (2026-09-01).  A **third** role dict
#: rather than five more entries in the launchpad one, for that dict's own
#: reason: these two bodies are composed hidden alongside each other and only
#: one of them can be showing, so "which body is this panel in" is a fact no
#: introspection can recover and every geometry assertion below needs.
#:
#: In left-then-rail, top-to-bottom order, which is also the ``compose`` order.
_POOL4_WIDGET_CLASSES = {
    "SurfPool4Split": SurfPool4Split,
    "SurfPool4Ratchet": SurfPool4Ratchet,
    "SurfPool4Flow": SurfPool4Flow,
    "SurfPool4Hatches": SurfPool4Hatches,
    "SurfPool4Vault": SurfPool4Vault,
}

#: Both halves together -- **derived from the package**, not from the two
#: dicts above.  The two dicts have to stay hand-typed: they encode a *role*
#: ("always mounted and visible" vs "composed hidden until ``l``") that no
#: introspection can see.  Their union is a different claim, and deriving it
#: is what makes a widget added to the package but to neither dict fail here
#: instead of silently escaping every dispatch test below -- which is exactly
#: how the three launchpad widgets escaped the whole of
#: ``tests/widgets/test_surf_widget_contract.py`` for the length of their
#: existence.
def _exported_widget_classes() -> dict[str, type]:
    import maxpane_dashboard.widgets.surf as surf_widgets

    return {
        name: getattr(surf_widgets, name)
        for name in surf_widgets.__all__
        if isinstance(getattr(surf_widgets, name), type)
    }


_ALL_WIDGET_CLASSES = _exported_widget_classes()


def test_the_two_hand_typed_widget_dicts_account_for_every_exported_widget():
    """No role dict may quietly stop naming a widget the package ships.

    The derivation above is what keeps the dispatch sweeps total; this is
    what keeps the *roles* total. A widget in the package and in no dict
    is either an unrendered panel or an untested visibility rule, and both
    read as green today.

    **Three dicts since 2026-09-01, and the pairwise-disjointness check is
    written over the list rather than as one more ``&``.** Spelling it out per
    pair was already the shape that would rot: a fourth body would add three
    more comparisons and the one somebody forgot would be the hole.
    """
    roles = (_WIDGET_CLASSES, _LAUNCHPAD_WIDGET_CLASSES, _POOL4_WIDGET_CLASSES)
    union: set[str] = set()
    for dict_ in roles:
        assert not (union & dict_.keys()), (
            f"a widget is in two role dicts at once: {union & dict_.keys()}"
        )
        union |= dict_.keys()
    assert union == _ALL_WIDGET_CLASSES.keys()
    assert len(_ALL_WIDGET_CLASSES) >= 16

#: The WP3<->WP5 dispatch contract: exactly the PRD §5 key groups.  Local copy
#: until WP0 exports SURF_WIDGET_SIGNATURES beside SURF_KEYS (open issue) --
#: the mechanical dispatch test below still catches any drift against
#: SURF_KEYS.
#:
#: ``{widget name: {SURF_KEYS name: update_data kwarg name}}`` -- a dict of
#: dicts, not the flat ``{widget name: (kwarg, ...)}`` this used to be.  Every
#: widget through Task 8/9/10 happens to name its kwargs identically to the
#: SURF_KEYS field it carries, so a flat tuple of names served for both "what
#: SURF_KEYS key is this" and "what kwarg does the screen pass" at once.  The
#: three Task 11 launchpad widgets break that coincidence on purpose -- they
#: are primitives-only and reusable, so they take their own short names
#: (``coins``, ``as_of_hhmm``, ``burned_total``) rather than the
#: ``launchpad_``-prefixed PRD vocabulary -- so the two questions need two
#: answers per entry now. Keys equal to their values is not redundancy to
#: simplify away: it is the (common) case where the coincidence still holds.
SURF_WIDGET_SIGNATURES: dict[str, dict[str, str]] = {
    # LAUNCHPAD / FLOW / BURN / SUPPLY since 2026-08-24. The POOL and LP boxes
    # this row carried for one day are gone (widgets/surf/hero.py says why),
    # and with them nine kwargs -- see ``META_KEYS`` and
    # ``_KEYS_WITHOUT_A_RENDERER`` below for where each of those keys ended up.
    # The first three names here are the coincidence this map's own comment
    # warns about breaking: the hero takes the ``launchpad_``-prefixed PRD
    # names verbatim, while the ``l`` view's three widgets take short ones.
    "SurfHero": {
        "launchpad_coin_count": "launchpad_coin_count",
        "launchpad_new_24h": "launchpad_new_24h",
        "launchpad_creator_count": "launchpad_creator_count",
        "launchpad_swap_count": "launchpad_swap_count",
        "launchpad_trader_count": "launchpad_trader_count",
        "launchpad_creator_eth_owed": "launchpad_creator_eth_owed",
        "launchpad_as_of_hhmm": "launchpad_as_of_hhmm",
        "burn_accrued": "burn_accrued",
        "burn_staged": "burn_staged",
        "burn_ready": "burn_ready",
        "imd_supply": "imd_supply",
        "imd_burned_cum": "imd_burned_cum",
    },
    "SurfSignals": {
        "sig_post_state": "sig_post_state",
        "sig_post_detail": "sig_post_detail",
        "sig_post_age_s": "sig_post_age_s",
        "sig_thread_state": "sig_thread_state",
        "sig_thread_detail": "sig_thread_detail",
        "sig_thread_age_s": "sig_thread_age_s",
        "sig_lp_state": "sig_lp_state",
        "sig_lp_detail": "sig_lp_detail",
        "sig_lp_age_s": "sig_lp_age_s",
        "sig_gate_state": "sig_gate_state",
        "sig_gate_detail": "sig_gate_detail",
        "sig_gate_age_s": "sig_gate_age_s",
        "sig_deploy_state": "sig_deploy_state",
        "sig_deploy_detail": "sig_deploy_detail",
        "sig_deploy_age_s": "sig_deploy_age_s",
        "sig_bridge_state": "sig_bridge_state",
        "sig_bridge_detail": "sig_bridge_detail",
        "sig_bridge_age_s": "sig_bridge_age_s",
        "sig_burn_state": "sig_burn_state",
        "sig_burn_detail": "sig_burn_detail",
        "sig_burn_age_s": "sig_burn_age_s",
        "sig_decoy_state": "sig_decoy_state",
        "sig_decoy_detail": "sig_decoy_detail",
        "sig_decoy_age_s": "sig_decoy_age_s",
        "sig_burnready_state": "sig_burnready_state",
        "sig_burnready_detail": "sig_burnready_detail",
        "sig_burnready_age_s": "sig_burnready_age_s",
        "sig_hot_state": "sig_hot_state",
        "sig_hot_detail": "sig_hot_detail",
        "sig_hot_age_s": "sig_hot_age_s",
    },
    "SurfFeed": {
        "feed_items": "feed_items",
        "feed_nonce": "feed_nonce",
        "feed_last_post_age_s": "feed_last_post_age_s",
    },
    "SurfDevActivity": {"dev_activity": "dev_activity"},
    "SurfMarket": {
        "imd_price_usd": "imd_price_usd",
        "imd_change_24h_pct": "imd_change_24h_pct",
        "imd_vol_24h_usd": "imd_vol_24h_usd",
        "pool_liquidity_usd": "pool_liquidity_usd",
        "fp_price_usd": "fp_price_usd",
        "parity_pct": "parity_pct",
        "supply_series": "supply_series",
        "price_series": "price_series",
        "price_source_disagreement_pct": "price_source_disagreement_pct",
        # Restored 2026-08-24 (fix round 1). Not a market *row*: it is
        # provenance for the two figures on this panel that come out of the
        # v4 pool, and it renders on the panel title as `· pool id
        # unverified`. It was briefly parked in `_KEYS_WITHOUT_A_RENDERER`
        # below after the hero's POOL box was retired -- correctly, since
        # nothing rendered it, but the parking was the bug rather than the
        # record of one: "we could not verify which pool this is" is a
        # security claim with no other home on the dashboard.
        "pool_id_source": "pool_id_source",
    },
    "SurfNft": {
        "nft_holders": "nft_holders",
        "nft_transfers_24h": "nft_transfers_24h",
        "nft_dev_holdings": "nft_dev_holdings",
        "nft_written": "nft_written",
        "nft_last_sales": "nft_last_sales",
        "nft_floor": "nft_floor",
    },
    # -- the l LAUNCHPAD view's three widgets (2026-08-23) -----------------
    "SurfLaunchpadCoins": {
        "launchpad_coins": "coins",
        "launchpad_coin_count": "coin_count",
        # The sweep's own population count. `SurfLaunchpadCoins.update_data`
        # has named this kwarg since Task 11 and the screen did not pass it,
        # so `_set_note`'s comparison against the factory's `coinCount()`
        # could not run in the real app at all -- the detector for exactly
        # the bug Task 6's review found (a truncating sweep returning 2 of
        # 146 launches as a success) was dark in production while its unit
        # tests passed.
        "launchpad_launch_count": "launch_count",
        "launchpad_as_of_hhmm": "as_of_hhmm",
    },
    "SurfCurveFlow": {
        "launchpad_swap_count": "swap_count",
        "launchpad_trader_count": "trader_count",
        "launchpad_creator_eth_owed": "creator_eth_owed",
        "launchpad_as_of_hhmm": "as_of_hhmm",
    },
    "SurfBurnPipeline": {
        # burn_accrued/burn_staged/burn_ready are also dispatched to SurfHero
        # above -- both widgets render the same live executor state, in two
        # different shapes (a five-line box vs. a full standalone panel), and
        # the manager guarantees the two can never disagree (surf_manager.py
        # builds both from the same read).
        "burn_accrued": "burn_accrued",
        "burn_staged": "burn_staged",
        "burn_ready": "burn_ready",
        "burn_min_bridge": "burn_min_bridge",
        "burn_bridgeable": "burn_bridgeable",
        "launchpad_burned_total": "burned_total",
        "launchpad_as_of_hhmm": "as_of_hhmm",
    },
    # -- the two panels the l body grew on 2026-08-25 ---------------------
    #
    # Note where the coincidence this map's own comment describes comes
    # BACK: both name their payload kwarg after the contract key exactly,
    # which is what puts them in the strict kwarg sweep in
    # ``tests/widgets/test_surf_widget_contract.py`` rather than in its
    # ``_SHORT_KWARG_WIDGETS`` escape list. Only the shared launchpad clock
    # is still spelled short, on all five panels.
    "SurfLaunchpadActivity": {
        "launchpad_activity": "launchpad_activity",
        "launchpad_as_of_hhmm": "as_of_hhmm",
    },
    "SurfBurnkeepers": {
        "launchpad_burnkeepers": "launchpad_burnkeepers",
        "launchpad_as_of_hhmm": "as_of_hhmm",
    },
    # -- the p POOL4 body's five panels (2026-09-01) ----------------------
    #
    # EVERY kwarg is the contract key verbatim, ``pool4_as_of_hhmm``
    # included, and that is a deliberate departure from the launchpad panels
    # one block up rather than an inconsistency. Those five spell the shared
    # clock ``as_of_hhmm`` and are excused by
    # ``tests/widgets/test_surf_widget_contract._PREFIXED_KWARG_ALIASES``,
    # which maps ONE kwarg name onto ONE contract key. A second body whose
    # panels also took ``as_of_hhmm`` would make that one name stand for
    # ``launchpad_as_of_hhmm`` on five widgets and ``pool4_as_of_hhmm`` on
    # five others, at which point the alias proves nothing about either.
    # ``test_no_pool4_widget_needs_a_kwarg_alias`` pins the decision.
    #
    # FOUR keys here reach more than one panel, and the two groups are
    # there for opposite reasons.
    #
    # ``pool4_network`` and ``pool4_as_of_hhmm`` are on all FIVE: every
    # title carries the network word (plan section 5 R4: a testnet number on
    # an unmarked panel is fiction presented as live) and every panel
    # carries the tier's own slower clock.
    #
    # ``pool4_reward_path`` and ``pool4_distributor_addr`` are on exactly
    # TWO -- THE SPLIT and HATCHES -- and that count is pinned, not merely
    # permitted, by ``test_the_reward_topology_reaches_exactly_two_panels``
    # below and by WP0's contract-side
    # ``test_each_scalar_key_has_exactly_one_renderer_apart_from_the_two_
    # shared_ones``. One topology fact, on the two panels that would
    # otherwise disagree about it: SPLIT has to know WHICH leg the measured
    # stakers percentage is (mainnet's 15% reward share against the 4.5%
    # staker share is a 3x error), and HATCHES renders the trust surface the
    # extra Distributor hop adds. A third panel acquiring it would be a
    # second place for the topology to be stated and so a second place for
    # it to disagree with itself.
    #
    # This comment said the two shared keys were "the only two keys here
    # that more than one panel renders" until 2026-09-02, which was true
    # when it was written and stopped being true when mainnet's Distributor
    # split the reward path. Recorded rather than silently corrected: WP4
    # asked whether the topology's two panels collided with an assertion
    # somewhere, and the answer was that no assertion said so -- only this
    # comment did.
    "SurfPool4Hatches": {
        "pool4_hatches": "pool4_hatches",
        "pool4_network": "pool4_network",
        "pool4_discovery_state": "pool4_discovery_state",
        "pool4_discovery_detail": "pool4_discovery_detail",
        # S18: the citation is its own key, never merged into the detail.
        # WP0's `POOL4_WIDGET_SIGNATURES` is the authority; this copy is the
        # redundant one and the agreement test is what makes keeping both
        # worth it -- deriving either would compare a constant with itself.
        "pool4_discovery_source_tx": "pool4_discovery_source_tx",
        # WHICH source the adoption came from -- a disclosure key: the docs
        # site is a weaker provenance than a dev-signed announce post and
        # must identify itself as such.
        "pool4_discovery_source": "pool4_discovery_source",
        # The topology, second of exactly two panels.
        "pool4_reward_path": "pool4_reward_path",
        "pool4_distributor_addr": "pool4_distributor_addr",
        "pool4_hook_addr": "pool4_hook_addr",
        "pool4_token_addr": "pool4_token_addr",
        "pool4_vault_addr": "pool4_vault_addr",
        "pool4_dripper_addr": "pool4_dripper_addr",
        "pool4_as_of_hhmm": "pool4_as_of_hhmm",
    },
    "SurfPool4Flow": {
        "pool4_flow": "pool4_flow",
        "pool4_network": "pool4_network",
        "pool4_as_of_hhmm": "pool4_as_of_hhmm",
    },
    "SurfPool4Split": {
        "pool4_network": "pool4_network",
        "pool4_measured_inference_pct": "pool4_measured_inference_pct",
        "pool4_measured_burn_pct": "pool4_measured_burn_pct",
        "pool4_measured_stakers_pct": "pool4_measured_stakers_pct",
        "pool4_reward_share_bps": "pool4_reward_share_bps",
        "pool4_bps_denominator": "pool4_bps_denominator",
        "pool4_split_drift_bps": "pool4_split_drift_bps",
        "pool4_total_burned": "pool4_total_burned",
        "pool4_total_rewarded": "pool4_total_rewarded",
        "pool4_total_fee_token": "pool4_total_fee_token",
        "pool4_retained_eth": "pool4_retained_eth",
        "pool4_last_claim_block": "pool4_last_claim_block",
        "pool4_unsettled_burn": "pool4_unsettled_burn",
        "pool4_unsettled_stakers": "pool4_unsettled_stakers",
        # The counter reconciliation (W1, 2026-09-02). `None` on the state
        # means the check has NEVER RUN, which is not the same claim as its
        # own `"unchecked"` member -- so it is dispatched rather than
        # defaulted, and this map is what pins that it reaches a widget at
        # all. The contract-side copy lives in
        # `tests/data/test_surf_pool4_models.POOL4_WIDGET_SIGNATURES`; the
        # two are meant to stay redundant and hand-typed, because deriving
        # either from the other would make the agreement test compare a
        # constant against itself.
        "pool4_counter_state": "pool4_counter_state",
        "pool4_counter_detail": "pool4_counter_detail",
        # The mainnet three-way reward split (2026-09-02). `pool4_reward_path`
        # goes to exactly TWO panels -- this one and HATCHES -- and WP0's
        # `POOL4_WIDGET_SIGNATURES` pins that count, so a third panel picking
        # it up shows as a disagreement between the two copies rather than as
        # nothing at all.
        "pool4_reward_path": "pool4_reward_path",
        "pool4_distributor_addr": "pool4_distributor_addr",
        "pool4_distributor_staking_bps": "pool4_distributor_staking_bps",
        "pool4_distributor_nodes_bps": "pool4_distributor_nodes_bps",
        # The REMAINDER, not a getter: 10000 - staking - nodes. Named here
        # because a fixture that hardcodes 4000 asserts a number the chain
        # never returned.
        "pool4_distributor_bonding_bps": "pool4_distributor_bonding_bps",
        "pool4_distributor_staking_earned": "pool4_distributor_staking_earned",
        "pool4_distributor_nodes_earned": "pool4_distributor_nodes_earned",
        "pool4_distributor_bonding_earned": "pool4_distributor_bonding_earned",
        "pool4_distributor_held_nodes": "pool4_distributor_held_nodes",
        "pool4_distributor_held_bonding": "pool4_distributor_held_bonding",
        "pool4_as_of_hhmm": "pool4_as_of_hhmm",
    },
    "SurfPool4Ratchet": {
        "pool4_network": "pool4_network",
        "pool4_tokens_in_pool": "pool4_tokens_in_pool",
        "pool4_cap_floor": "pool4_cap_floor",
        # The inventory ceiling. ⚠ `pool4_cap_headroom` is cap − reserve
        # where `pool4_floor_distance` is reserve − floor: the operand order
        # flips so both read positive when healthy, and reversing it renders
        # a binding cap as slack.
        "pool4_inventory_cap": "pool4_inventory_cap",
        "pool4_cap_headroom": "pool4_cap_headroom",
        "pool4_cap_decay_per_day": "pool4_cap_decay_per_day",
        "pool4_floor_distance": "pool4_floor_distance",
        "pool4_floor_distance_pct": "pool4_floor_distance_pct",
        "pool4_burned_supply_pct": "pool4_burned_supply_pct",
        "pool4_total_supply": "pool4_total_supply",
        "pool4_reserve_series": "pool4_reserve_series",
        "pool4_eth_in_pool": "pool4_eth_in_pool",
        "pool4_position_liquidity": "pool4_position_liquidity",
        "pool4_current_tick": "pool4_current_tick",
        "pool4_ref_tick": "pool4_ref_tick",
        "pool4_backstop_centred": "pool4_backstop_centred",
        "pool4_as_of_hhmm": "pool4_as_of_hhmm",
    },
    "SurfPool4Vault": {
        "pool4_network": "pool4_network",
        "pool4_share_price": "pool4_share_price",
        "pool4_share_price_delta_pct": "pool4_share_price_delta_pct",
        "pool4_vault_assets": "pool4_vault_assets",
        "pool4_vault_shares": "pool4_vault_shares",
        "pool4_drip_per_day": "pool4_drip_per_day",
        "pool4_drippable": "pool4_drippable",
        "pool4_can_drip": "pool4_can_drip",
        "pool4_backlog_imd": "pool4_backlog_imd",
        "pool4_backlog_days": "pool4_backlog_days",
        "pool4_implied_apr_pct": "pool4_implied_apr_pct",
        "pool4_as_of_hhmm": "pool4_as_of_hhmm",
    },
}

#: Keys the screen itself consumes without a 1:1 widget kwarg.
#:
#: ``as_of`` (freshness bookkeeping), ``degraded`` (title bar), ``eth_usd``
#: (context; unrendered in v1) are the original three.
#:
#: Task 12 added three more: ``gate_open``, ``identities_written``,
#: ``lp_liquidity`` still do real work even though the hero's 2026-08-23
#: POOL/LP/BURN/SUPPLY rebuild dropped their direct kwargs --
#: ``surf_manager._readings`` reads them straight off this same flat dict to
#: build the GATE/LP detectors (``sig_gate_*``/``sig_lp_*``), which *are*
#: dispatched, to SurfSignals, above. Their information still reaches the
#: screen -- through the detector text, not as raw values -- so "no widget
#: kwarg" is not "no consumer downstream of this dict", just no *direct* one.
#:
#: ``hook_status``, ``pool_liquidity_raw`` and ``lp_position_count`` USED to
#: sit here too, parked rather than removed: Task 12 found nothing downstream
#: read any of the three but did not own ``data/surf_models.py``/
#: ``data/surf_manager.py`` to remove them from ``SURF_KEYS`` itself, and
#: flagged the cleanup in task-12-report.md. Task 6 fix round 12a did that
#: cleanup -- all three are gone from ``SURF_KEYS`` now, not merely
#: unconsumed, so they no longer belong in this set either.
#:
#: 2026-08-24 added two more of the same shape, both from the hero's
#: LAUNCHPAD/FLOW rebuild:
#:
#: * ``decoy_pool_count`` -- ``surf_manager._readings`` reads it straight off
#:   this flat dict to feed ``_detect_decoy``, so it reaches the screen as
#:   ``sig_decoy_*``, dispatched to SurfSignals. Identical in kind to
#:   ``gate_open`` above, and the hero's own module docstring names DECOY POOL
#:   on the signals rail as where the retired POOL box's decoy count went.
#: * ``lp_owner_ok`` -- ``_title_line`` in this very screen turns a ``False``
#:   into ``⚠ LP owner changed`` on the title bar, which is the whole of what
#:   the retired LP box's ``owner ✓`` line was saying. The screen consuming a
#:   key directly is the original meaning of this set.
META_KEYS = frozenset({
    "as_of", "degraded", "eth_usd",
    "gate_open", "identities_written", "lp_liquidity",
    "decoy_pool_count", "lp_owner_ok",
})

#: Contract keys the manager still publishes that now reach **nothing** --
#: not a widget, not a detector, not this screen. Distinct from
#: :data:`META_KEYS`, which asserts the screen consumes them: folding these in
#: there would make that set's own docstring false, and "consumed somewhere"
#: is precisely the claim nobody can check once the two are mixed.
#:
#: All five are the hero's retired POOL and LP boxes' fields, orphaned by the
#: 2026-08-24 rebuild (``widgets/surf/hero.py`` argues each retirement). Their
#: information either moved (``pool_liquidity_usd`` to SurfMarket,
#: ``decoy_pool_count`` and ``lp_owner_ok`` to the two entries just added to
#: ``META_KEYS``) or simply ran out: ``lp_state``, ``lp_imd`` and ``lp_weth``
#: have read ``None`` since the ops wallet burned the v3 position on
#: 2026-08-17 and ``ownerOf`` began reverting, ``pool_venue`` has read ``"v4"``
#: with no path back ever since, and ``pool_fee_bps`` is a static 1%. Each of
#: those is an accepted loss, reviewed and confirmed as such.
#:
#: **``pool_id_source`` was in this set for one commit and should not have
#: been.** It is the flag saying the live-pool lookup fell back to a vendored
#: constant -- i.e. that the liquidity and price on screen may belong to one
#: of the 37 third-party decoy pools rather than to IMD's own. Nothing else
#: on the dashboard carries that claim (DECOY POOL on the signals rail counts
#: decoys, which is not the same fact), so parking it was a silent regression
#: rather than a record of one. It now renders on the IMD MARKET panel's
#: title and is a ``SurfMarket`` kwarg above. The lesson this set is annotated
#: with: "no widget reads it" is a fact, but "and that is fine" is a
#: *judgement*, and the two have to be made separately for every entry.
#:
#: **Parked, not blessed.** The real fix is to remove them from ``SURF_KEYS``,
#: which lives in ``data/surf_models.py`` -- a file the task that orphaned
#: them does not own. That is exactly how ``hook_status``,
#: ``pool_liquidity_raw`` and ``lp_position_count`` were handled one wave
#: earlier (see ``META_KEYS``'s own note on them): parked here, flagged in the
#: task report, and removed from the contract by the module's owner in the
#: following round, at which point this set shrinks. It is scaffolding with
#: the same expiry date ``_KEYS_PENDING_CONSUMERS`` had.
#:
#: ``test_the_unrendered_keys_are_named_by_no_widget_signature`` is what stops
#: an entry rotting here after somebody re-wires it: re-add ``lp_imd=`` to a
#: widget's ``update_data`` and this list is what goes red.
_KEYS_WITHOUT_A_RENDERER = frozenset({
    "pool_venue", "pool_fee_bps",
    "lp_state", "lp_imd", "lp_weth",
})

#: **Empty, for the second time.** Task 12 of the v3->v4/launchpad plan
#: emptied it once (27 keys that plan's Task 1 froze before their consumers
#: existed); the surf-launchpad-panels plan's Task 1 then reused the same
#: precedent to freeze ``launchpad_activity``/``launchpad_burnkeepers`` ahead
#: of the widgets, and this task -- that plan's own wiring task -- is where
#: those two consumers arrive, so the carve-out expires here rather than
#: rotting into a claim that nothing renders them.
#:
#: Every key ``SURF_KEYS`` carries now reaches either a widget kwarg
#: (:data:`SURF_WIDGET_SIGNATURES`), :data:`META_KEYS`, or the
#: explicitly-parked :data:`_KEYS_WITHOUT_A_RENDERER`. Empty is not the same
#: as absent: the subtraction stays in both tests below so the *next* plan
#: can name its own pre-frozen keys here, and so an entry regressing into it
#: is visible as a diff rather than as a new mechanism. A key sitting here
#: past its plan's wiring task is a bug, not a waiver.
_KEYS_PENDING_CONSUMERS: frozenset[str] = frozenset()

# -- fixed instants, all from tests/fixtures/surf/captures/ -------------
_TS_POST_13 = 1_786_076_831   # announce nonce 13, 2026-08-07T04:27:11Z
_TS_POST_12 = 1_785_903_575   # announce nonce 12, 2026-08-05T04:19:35Z
_TS_REPLY = 1_785_795_251     # pasta-sauce reply, 2026-08-03T22:14:11Z
_AS_OF = 1_786_161_600.0      # the fetch instant: 2026-08-08T04:00:00Z
#: ``_AS_OF`` as the title bar renders it (final fix wave, I4). Computed, not
#: typed: ``_fmt_hhmm`` renders **local** time, so a literal would pin these
#: tests to whichever timezone they were written in and go red on a laptop
#: that travels.
_AS_OF_HHMM = time.strftime("%H:%M", time.localtime(_AS_OF))
_ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
_REPLIER = "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159"
# Full 42-char addresses, never pre-shortened: WP3's ``long_addr`` returns any
# string of 17 characters or fewer unchanged, so a short-form fixture would
# make the poisoning defence a no-op in this file. Both are live in
# frenpet.eth's history today (ops_eth_txs.json) and are the two WP3 and WP4
# test against.
_REAL_UNKNOWN = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"   # unlabelled LP-fee dest
_SPOOF = "0xF3083828702C1989710CECA517412071c2f60Ee6"          # 1-gwei lookalike


def _sample_data() -> dict:
    """A representative full payload, every value captures-derived."""
    return {
        # -- meta ---------------------------------------------------------
        "as_of": _AS_OF,
        "degraded": [],
        "eth_usd": 1919.2,          # 0.7074 / priceNative 0.0003686
        # -- feed ---------------------------------------------------------
        "feed_nonce": 14,           # eth_getTransactionCount(announce)
        "feed_last_post_age_s": _AS_OF - _TS_POST_13,   # 84769.0 -> "23h"
        # Every row carries the whole frozen ``SURF_ROW_KEYS["feed_items"]``
        # shape, ``to_addr``/``label``/``value_eth`` included -- pinned by
        # ``test_every_list_row_in_the_fixture_matches_the_frozen_row_shape``.
        # Those three were absent until 2026-08-24, the same drift the
        # launchpad rows had: harmless on screen while every row here carries
        # ``text`` (``feed.py`` only falls back to ``label`` and then
        # ``value_eth`` when it does not), but a fixture that is missing a
        # contract field cannot be what a screen test measures the contract
        # against.
        #
        # All three values are the producer's own, not invented.
        # ``to_addr`` is the channel for all three rows: a ``self`` post is
        # ``from == to == channel`` by definition (``classify_channel_tx``),
        # and a ``reply`` is a stranger writing *to* the channel.
        # ``label`` is what ``surf_manager._feed_items`` emits for a row with
        # no decoded ``method``: the first four calldata bytes as hex, which
        # for a text post is the first four characters of the message
        # ("I mo", "@Rek", "Bro ").  ``value_eth`` is ``0.0`` -- a real,
        # measured zero, which is the normal shape on this channel (a post is
        # calldata, not a payment) and honestly distinct from the ``None``
        # the manager writes when ``value_wei`` will not read.
        "feed_items": [
            {
                "ts": _TS_POST_13,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "to_addr": _ANNOUNCE.lower(),
                "from_label": "announce",
                "label": "0x49206d6f",
                "value_eth": 0.0,
                "text": (
                    "I moved 33 eth to the LP on mainnet "
                    "https://etherscan.io/tx/0x90a0f8e2b039e8d86d1b10e33e6"
                    "1e12d13728444e0a9e5ac258051cccb64d669. Hopefully in "
                    "the coming days will be able to share more what been "
                    "working on, as always 0 promises."
                ),
                "tx_hash": "0xe397869a2ed1299f24618c377112a6e9637395d2c1e2"
                           "1e742ce30e6201440055",
            },
            {
                "ts": _TS_POST_12,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "to_addr": _ANNOUNCE.lower(),
                "from_label": "announce",
                "label": "0x4052656b",
                "value_eth": 0.0,
                "text": "@RektSconey created this explorer of the NFTs "
                        "https://idmd-reader.pages.dev. Burned 15745 more "
                        "tokens from the LP fees, made huge progress today "
                        "on the system, will share more when have something "
                        "concrete.",
                "tx_hash": "0xeb2b8272330a0224df369373d177356ca321668f44d5"
                           "2e2e46f08645bcf36fc8",
            },
            {
                # the community reply, typographic apostrophe intact --
                # markup-hostile third-party text (PRD §6.4)
                "ts": _TS_REPLY,
                "kind": "reply",
                "from_addr": _REPLIER,
                "to_addr": _ANNOUNCE.lower(),
                "from_label": None,
                "label": "0x42726f20",
                "value_eth": 0.0,
                "text": "Bro cooked this so hard it smells like my "
                        "grandma’s pasta sauce after marinating "
                        "overnight. Absolute Michelin alpha.",
                "tx_hash": "0xdcb8bf92a26aac481939880c17087e66fc32b036eb84"
                           "3bd7f10fb302ade760c9",
            },
        ],
        # -- signals (states the product can emit: ok/watch/fired/None) ----
        #
        # Every detail string below is **WP2's output vocabulary**, copied
        # verbatim from the detector bodies and the ``MATRIX`` table in
        # wp2.md Tasks WP2.4-WP2.8 -- not paraphrased. ``build_signals``
        # cannot emit anything else, and this screen's composited assertions
        # (and the WP5.5 width measurement) are calibrated on these exact
        # widths. Re-copy them if a WP2 detector's detail changes.
        #
        # Two state/age pairings worth reading twice, both WP2 rules
        # (``FIRED_TTL_S = 86400``):
        #   * post + bridge are ``fired`` because their ages are under 24 h;
        #     a FIRED row keeps the *event's* detail verbatim.
        #   * burn is ``ok`` because its event is 2.99 d old, so WP2 relaxes
        #     it to the composed ``<live detail> · last: <event detail>``
        #     form while keeping the event's age.
        "sig_post_state": "fired",
        # WP2's LP_POST_DETAIL -- the "#N" form with straight quotes and a
        # 48-char body ellipsis, not a "nonce 13 -> 14" gloss.
        "sig_post_detail": '#14 "I moved 33 eth to the LP on mainnet https://eth…"',
        "sig_post_age_s": _AS_OF - _TS_POST_13,
        # NEW REPLY quiet: this fixture's channel has no unreported reply on
        # it, which is the ordinary state and keeps the row in the quiet fold.
        "sig_thread_state": "ok",
        "sig_thread_detail": "no new replies",
        "sig_thread_age_s": None,
        "sig_lp_state": "ok",
        "sig_lp_detail": "liquidity holds",
        "sig_lp_age_s": None,
        "sig_gate_state": "ok",
        # No "/2000": WP2 omits the denominator deliberately (the cap is a
        # documented number, and documented numbers are read live or not
        # shown -- CLAUDE.md rule 4). WP2's `test_no_live_value_is_hardcoded`
        # bans the literal 2000 from that module outright.
        "sig_gate_detail": "closed · 1 written",
        "sig_gate_age_s": None,
        "sig_deploy_state": "ok",
        "sig_deploy_detail": "no new contract",
        "sig_deploy_age_s": None,
        "sig_bridge_state": "fired",
        "sig_bridge_detail": "mint 114,367 IMD → frenpet.eth",
        "sig_bridge_age_s": _AS_OF - (_TS_POST_13 - 720.0),  # staged 12 min pre-add
        "sig_burn_state": "ok",
        "sig_burn_detail": "supply flat · last: burn 15,745 IMD",
        "sig_burn_age_s": _AS_OF - _TS_POST_12,   # 2.99 d -> relaxed past FIRED_TTL_S
        # -- hero (POOL / LP / BURN / SUPPLY, rebuilt 2026-08-23) ------------
        # This fixture's own instant (2026-08-08) predates the v3->v4
        # migration (2026-08-17) and the launchpad's public launch, so the
        # LP position that was still live *then* is what is exercised here
        # (``lp_state="live"``, ``pool_venue="v3"``) -- the pre-migration
        # shape a Task 8 review minor flagged as untested at integration
        # level anywhere in the suite ("FLAG PROMINENTLY TO THE FINAL
        # REVIEW"), closed here as a side effect of using real captured
        # values instead of a synthetic post-migration snapshot.
        # ``gate_open``/``identities_written``/``lp_liquidity`` are kept
        # (unlike ``hook_status``, dropped below) even though none reaches a
        # widget kwarg any more: they still feed the GATE/LP detectors
        # inside the real manager (see ``META_KEYS`` above), and their
        # values here are the same real 2026-08-08 capture the sig_gate/
        # sig_lp detail strings above were transcribed from -- keeping them
        # documents that link even though nothing in *this* fixture computes
        # one from the other.
        "lp_liquidity": 2_162_384_733_113_558_190,   # raw uint128; pool_liquidity_raw's sibling, neither reaches a widget
        "gate_open": False,
        "identities_written": 1,
        # -- pool (v3 -> v4 migration): the *live* pool this instant, v3 --
        "pool_venue": "v3",
        "pool_fee_bps": 10_000,                     # 1%, Uniswap fee units (fee / 1e6)
        "pool_id_source": "hook",
        "decoy_pool_count": 37,                     # 38 ETH/IMD v4 pools seen; 1 real
        "lp_state": "live",
        "lp_imd": 388_421.0,
        "lp_weth": 142.7067,
        "lp_owner_ok": True,
        # -- burn executor (v1 -> v2): the permissionless bridge-and-burn --
        "burn_accrued": 1_234.56,
        "burn_staged": 45.0,
        "burn_ready": True,
        "burn_min_bridge": 500.0,
        # previewBridge(): what a burn would actually send right now.
        "burn_bridgeable": 620.0,
        "imd_supply": 2_376_731.868679,
        # The observed 2026-08-05 event, NOT the 58,848 all-time ledger of
        # PRD §1: ``imd_burned_cum`` is observation-scoped (WP4.5 --
        # ``SurfCache.observed_burn_total()`` accumulates over successive
        # supply readings; ``None`` before the first successful read, ``0.0``
        # once watched with nothing moved). WP3's SurfHero prints it as
        # ``burned {n:,.0f} observed``, so an all-time value here would make
        # the screen certify an all-time claim that copy exists to avoid.
        "imd_burned_cum": 15_745.0,
        # -- market ---------------------------------------------------------
        "imd_price_usd": 0.7074,
        "imd_change_24h_pct": 30.89,
        "imd_vol_24h_usd": 244_178.0,
        "pool_liquidity_usd": 548_701.21,
        # ``price_source_disagreement_pct`` is always computable (it compares
        # the two live sources against each other), so it carries a small,
        # healthy value here rather than ``None``.
        "price_source_disagreement_pct": 0.4,
        "fp_price_usd": 0.7274,
        "parity_pct": -2.7495188834204012,   # (0.7074/0.7274 - 1) * 100
        "supply_series": [
            [_TS_POST_12 - 86_400, 2_392_476.868679],  # before the 15,745 burn
            [_TS_POST_12, 2_376_731.868679],           # the step down
            [int(_AS_OF), 2_376_731.868679],
        ],
        "price_series": [
            [int(_AS_OF) - (23 - i) * 3600, 0.5404 + i * 0.00726]
            for i in range(24)                          # +30.89% over 24h
        ],
        # -- nft ------------------------------------------------------------
        "nft_holders": 667,
        "nft_transfers_24h": 38,
        "nft_dev_holdings": 3,
        "nft_written": 1,
        "nft_last_sales": [
            {"ts": int(_AS_OF) - 7_200, "token_id": 1204, "eth": 0.219},
            {"ts": int(_AS_OF) - 26_000, "token_id": 421, "eth": 0.2},
        ],
        "nft_floor": None,   # always None in v1 -> "n/a -- no keyless source"
        # -- activity --------------------------------------------------------
        # Newest first, the order WP4's ``_activity_rows`` emits and the order
        # WP3's table renders without re-sorting.
        #
        # ``wallet_label`` is ``"dev"``/``"ops"`` -- the *producer's* whole
        # vocabulary (``surf_client._DEV_WALLET_LABELS``, passed through by
        # ``surf_manager._activity_rows``), pinned against it by
        # ``test_the_activity_fixture_speaks_the_producers_wallet_vocabulary``.
        # It read ``"surfsurf.eth"``/``"frenpet.eth"`` until 2026-08-10, which
        # the pipeline never emits: those are the ``KNOWN_LABELS`` spellings
        # and they reach the user through the hero's ``owner ✓`` line instead.
        # Two things hid it. The activity cell was 12 columns wide, exactly
        # enough for ``surfsurf.eth``, so nothing looked wrong; and the
        # manager's defence-in-depth sender re-check keys on ``DEV_WALLETS``,
        # whose keys are ``dev``/``ops``, so an ENS-spelled label matched no
        # entry and skipped the check entirely. Narrowing the cell to the real
        # vocabulary rendered ``sur``/``fre`` and exposed both.
        "dev_activity": [
            {
                # Unknown counterparty: the **full 42-char** address, which is
                # what WP4 emits (``_activity_rows`` writes the raw
                # ``counterparty`` string when there is no label;
                # ``test_an_unknown_counterparty_is_never_marked_known`` pins
                # exactly this one). A pre-shortened fixture would sail
                # through WP3's ``long_addr`` untouched -- it returns any
                # string of <=17 chars unchanged -- and the screen test would
                # bless the first-6/last-4 short form the anti-poisoning rule
                # exists to prevent. Renders dimmed as ``0x61CC704c…73f14E``.
                "ts": _TS_POST_13 - 60,
                "wallet_label": "dev",
                "kind": "transfer",
                "counterparty": _REAL_UNKNOWN,
                "counterparty_known": False,
                "value_eth": 0.31,
                "tx_hash": "0x" + "2b" * 32,
                "imd_burned": None,
            },
            {
                # The live poisoning shape, end to end: a zero-value transfer
                # from an unknown lookalike. WP3's ``_row_markup`` drops the
                # (transfer, value 0, unknown) triple outright, so this row
                # must never reach a pixel -- asserted in WP5.4's
                # ``test_the_activity_view_defends_against_address_poisoning``.
                "ts": _TS_POST_13 - 120,
                "wallet_label": "ops",
                "kind": "transfer",
                "counterparty": _SPOOF,
                "counterparty_known": False,
                "value_eth": 0.0,
                "tx_hash": "0x" + "3c" * 32,
                "imd_burned": None,
            },
            {
                "ts": _TS_POST_13 - 300,
                "wallet_label": "ops",
                "kind": "lp",
                "counterparty": "NFPM",
                "counterparty_known": True,
                "value_eth": 33.25,
                "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9"
                           "e5ac258051cccb64d669",
                "imd_burned": None,
            },
            {
                "ts": _TS_POST_13 - 900,
                "wallet_label": "dev",
                "kind": "bridge",
                "counterparty": "OFT endpoint",
                "counterparty_known": True,
                "value_eth": 0.0,
                "tx_hash": "0x" + "1a" * 32,
                "imd_burned": None,
            },
        ],
        # -- launchpad (detached sweep, its own slower "as of") -------------
        # The magnitudes CLAUDE.md records for the real 2026-08-19 launchpad
        # state four days in (146 coins, 73 creators, 4,683 swaps, 673
        # traders, 3,299 IMD burned) -- not invented, and ``launchpad_burned_
        # total`` matches the same figure ``tests/widgets/
        # test_surf_launchpad_widgets.py`` already uses for SurfBurnPipeline.
        # Deliberately left unset (``None`` via ``_frozen_payload``'s
        # ``.get()``): sig_decoy_state/sig_burnready_state/sig_hot_state.
        # Setting any of the three to a real "ok" here would fold that
        # detector into the quiet-collapse summary (widgets/surf/signals.py)
        # and change the visible-row/quiet-count shape every width sweep in
        # this file below keys off ``_widen_sweep_payload`` (built from this
        # same fixture) -- leaving them unknown keeps every one of those
        # sweeps' pre-existing counts correct, and "the sweep never ran"
        # is exactly the state a v1 install reaching this tier for the first
        # time is really in.
        "launchpad_coin_count": 146,
        # The sweep's own population, agreeing with the factory's claim above
        # -- the healthy state, in which `SurfLaunchpadCoins._set_note` says
        # nothing extra. A disagreement is the abnormal one and belongs in the
        # widget's own tests, not in the fixture every width sweep in this file
        # measures against.
        "launchpad_launch_count": 146,
        # 146 launches over the four days to 2026-08-19 is a mean of 36 a day.
        # Set rather than left `None` because the hero's LAUNCHPAD box renders
        # an unread field as a dash, and a width measured against a dash is a
        # width measured against a state the data is not normally in
        # (CLAUDE.md's IMD/FP peg lesson). It happens to cost nothing here --
        # `36 new · 24h` and `-- new · 24h` are the same twelve columns -- but
        # that is a measurement, not a reason to have left it out.
        "launchpad_new_24h": 36,
        "launchpad_creator_count": 73,
        "launchpad_swap_count": 4_683,
        "launchpad_trader_count": 673,
        "launchpad_burned_total": 3_299.0,
        "launchpad_creator_eth_owed": 2.4187,
        # ``change_24h_pct``/``swaps_24h``/``swaps_all`` -- Task 1's frozen
        # ``SURF_ROW_KEYS["launchpad_coins"]``, pinned field-for-field by
        # ``test_every_list_row_in_the_fixture_matches_the_frozen_row_shape``
        # below. These rows carried the pre-branch ``change_1h_pct``/
        # ``swaps_1h`` and no ``swaps_all`` until 2026-08-24, which meant
        # ``24H%``, ``SW 24H`` and ``SW ALL`` rendered ``--`` in every screen
        # test in this file: the whole Task 1/7/11 rename could be reverted
        # with the suite green.
        #
        # The two swap counts are deliberately different per row -- a fixture
        # where ``swaps_24h == swaps_all`` would pass just as happily against
        # a widget that rendered one field into both cells.
        "launchpad_coins": [
            {
                "ticker": "PANE", "name": "MaxPane Coin",
                "creator": "0x9D2C9B1F5C3f8b6f7D9C1a5E4b3A2F1D0c9B8A7E",
                "creator_known": False, "age_s": 3_600.0,
                "price_eth": 0.0071,
                # Not computed yet -- Task 1 only freezes the two mcap
                # fields; a later work package derives mcap_eth from
                # price_eth and mcap_usd from the market tier at assembly
                # (spec 2.5/2.6). An honest None here is not a fake mcap.
                "mcap_eth": None, "mcap_usd": None,
                "change_24h_pct": 34.0,
                "swaps_24h": 12, "swaps_all": 31, "imd_burned": 88.4,
            },
            {
                # The three-state row: fewer than two priced swaps in the
                # day-long window, so ``change_24h_pct`` is ``None`` (a dash,
                # never ``0%``) and ``swaps_24h`` is a real, representable
                # zero -- while ``swaps_all`` is 3, the coin having traded
                # before today. That combination is exactly what the widened
                # window (Task 7) exists to show and what the hour-long one
                # could not say at all.
                "ticker": "SURF", "name": "Surf Launch",
                "creator": "0x4E1c3A0Ad54418Fe843953C71dF23637DE732Cee",
                "creator_known": False, "age_s": 7_200.0,
                "price_eth": 0.00021, "mcap_eth": None, "mcap_usd": None,
                "change_24h_pct": None,
                "swaps_24h": 0, "swaps_all": 3, "imd_burned": 0.0,
            },
        ],
        # Frozen by Task 1 of the surf-launchpad-panels plan, parked in
        # ``_KEYS_PENDING_CONSUMERS`` below until a later task in that plan
        # wires up the widgets that will render them -- exercised here only
        # so ``test_every_list_row_in_the_fixture_matches_the_frozen_row_shape``
        # measures every row shape ``SURF_ROW_KEYS`` declares, this one
        # included.
        "launchpad_activity": [
            {
                "kind": "buy", "ticker": "PANE",
                "wallet": "0x9D2C9B1F5C3f8b6f7D9C1a5E4b3A2F1D0c9B8A7E",
                "wallet_known": False, "eth": 0.012, "age_s": 45.0,
            },
            {
                # A launch has no swap size: eth is None, never 0.0 -- a zero
                # would read and rank as a free trade.
                "kind": "launch", "ticker": "SURF",
                "wallet": "0x4E1c3A0Ad54418Fe843953C71dF23637DE732Cee",
                "wallet_known": False, "eth": None, "age_s": 7_200.0,
            },
        ],
        "launchpad_burnkeepers": [
            {
                "wallet": "0x" + "bb" * 20, "wallet_known": False,
                "imd_burned": 42.0, "eth_paid": 0.0031, "burns": 3,
            },
        ],
        "launchpad_as_of_hhmm": "01:14",
        # -- pool4 (`p` view, its own detached tier and its own slower clock)
        #
        # The **undiscovered Sepolia** state, which plan section 5 R4 calls
        # the primary path rather than the edge case: there is no pool4 hook
        # on mainnet, so what actually executes on the day this ships is
        # discovery finding nothing, `pool4_network == "SEPOLIA"`, and five
        # panel titles saying so over testnet numbers. Every screen test in
        # this file therefore measures that state by default, and the
        # adopted-mainnet one is an override where a test needs it.
        #
        # Values are the Sepolia launch-3 deployment's own shapes (the hook,
        # token, vault and dripper addresses are `surf_manager`'s vendored
        # constants and the dripper's own read), at magnitudes the mechanics
        # doc records. `pool4_split_drift_bps` is `0.0` -- the *healthy*
        # value, and a representable zero rather than a dash, which is the
        # single most likely thing for this panel to get wrong.
        "pool4_network": "SEPOLIA",
        "pool4_as_of_hhmm": "14:32",
        "pool4_discovery_state": "not-discovered",
        "pool4_discovery_detail":
            "no self-post in the announce channel names a pool4 hook",
        # Deliberately absent, and deliberately NOT filled to close the
        # value-check blind spot the counter keys above were filled to close:
        # on the undiscovered path there is no adoption, so there is no
        # transaction to cite, and `None` is the honest state rather than a
        # missing read. Inventing a hash here to make one more mutation bite
        # would trade a true fixture for a test convenience. The key's own
        # dispatch is covered on the adopted path instead, by
        # `test_the_adopted_discovery_detail_does_not_move_the_pool4_pin`.
        "pool4_discovery_source_tx": None,
        "pool4_hook_addr": "0xa1B997A9861B2b8aC17B4c615089cCC2a5416840",
        "pool4_token_addr": "0xB37d54bC1F1d9271fc57D7E03192976baA39Cc82",
        "pool4_vault_addr": "0x1600E1c4bE0aB0d1f4a0a2f0eFb1c0d2E3f417cc",
        "pool4_dripper_addr": "0x4dBE1782b0aC0dE1f2a3B4c5D6e7F8a9B0c1449B",
        "pool4_measured_inference_pct": 1.004,
        "pool4_measured_burn_pct": 89.102,
        "pool4_measured_stakers_pct": 9.894,
        "pool4_reward_share_bps": 990,
        "pool4_bps_denominator": 10_000,
        "pool4_split_drift_bps": 0.0,
        "pool4_total_burned": 102_030_338.5414,
        "pool4_total_rewarded": 1_234_567.25,
        "pool4_total_fee_token": 1_122_334.5,
        # A real, measured zero: the owner has withdrawn everything ever
        # collected, which amendment A9 records as correct behaviour rather
        # than a mismatch. A dash here would report an outage.
        "pool4_retained_eth": 0.0,
        "pool4_last_claim_block": 8_123_456,
        # The outstanding legs the corpus actually carries (amendment A20:
        # round to two decimals, NOT round to the wei).
        "pool4_unsettled_burn": 267_300.0,
        "pool4_unsettled_stakers": 29_700.0,
        "pool4_tokens_in_pool": 152_030_338.5414,
        "pool4_cap_floor": 50_000_000.0,
        "pool4_floor_distance": 102_030_338.5414,
        "pool4_floor_distance_pct": 204.06,
        "pool4_burned_supply_pct": 3.24,
        "pool4_total_supply": 1_000_000_000.0,
        "pool4_reserve_series": [
            [float(i), 150_000_000.0 + i * 1000] for i in range(20)
        ],
        "pool4_eth_in_pool": 0.0057231,
        "pool4_position_liquidity": 1.2345e19,
        "pool4_current_tick": -34_567,
        "pool4_ref_tick": -34_000,
        "pool4_backstop_centred": True,
        # A14: the vault reports 24 decimals, so the share price is
        # `convertToAssets(10 ** decimals) / 1e18` and the share count is
        # `raw / 10 ** decimals`. Both of the WRONG forms render as entirely
        # plausible numbers (0.0000013 IMD/share; 21 billion sIMD), so the
        # magnitudes here are the corrected ones and the cross-check holds:
        # 27,377.00 / 21,010.98 = 1.302986.
        "pool4_share_price": 1.302986,
        "pool4_share_price_delta_pct": 0.1234,
        "pool4_vault_assets": 27_377.0,
        "pool4_vault_shares": 21_010.98,
        "pool4_drip_per_day": 12_500.0,
        "pool4_drippable": 1_200.0,
        "pool4_can_drip": True,
        "pool4_backlog_imd": 250_000.0,
        "pool4_backlog_days": 20.0,
        "pool4_implied_apr_pct": 4.15,
        # W1's counter reconciliation. Set to the HEALTHY state, and set at
        # all for two reasons.
        #
        # It is right on the merits: the check runs against the Sepolia
        # counters whatever discovery is doing, so a fixture on the day-one
        # undiscovered path still has a real answer here, and `None` would
        # mean "the check has never run" -- a different and rarer state than
        # the one this fixture is meant to be.
        #
        # And it closes a measured blind spot. `test_screen_dispatches_
        # every_data_key` compares each kwarg's value against the payload's
        # value for the key it answers for, which can only catch a mis-wire
        # between two keys the fixture DISTINGUISHES. While both of these
        # were `None`, swapping the dispatch to read
        # `pool4_counter_state=data.get("pool4_counter_detail")` stayed
        # green -- proven by mutation, not supposed.
        #
        # The wording is the producer's own (`surf_pool4.reconcile_counters`,
        # pinned by `tests/data/test_surf_pool4.py`), not a paraphrase.
        "pool4_counter_state": "reconciled",
        "pool4_counter_detail": "all 5 identities hold to the wei",
        # -- the mainnet topology and ceiling (2026-09-02) -----------------
        #
        # This fixture stays the SEPOLIA / undiscovered day-one state that
        # plan section 5 R4 calls the primary path, so `rewardsRecipient()`
        # reaches the Dripper with nothing in between -- `direct` -- and the
        # distributor fields are absent. `None` on those is "there is no
        # Distributor on this deployment", which is the honest state rather
        # than a failed read. `_mainnet_pool4_payload` below is the
        # `via-distributor` counterpart, and the two are swept side by side.
        #
        # ⚠ THIS SAID `"two-way"` UNTIL 2026-09-02, and `POOL4_REWARD_PATHS`
        # has no such member. The word describes the SPLIT's shape, not the
        # TOPOLOGY the key carries, and the comment above it said "the reward
        # path is the two-way one" -- which is exactly how the slip happened
        # and why it read as correct on every re-read. Cost: `SurfPool4Split`
        # treats an unrecognised path as unknown and annotates nothing, by
        # design, because guessing either way is the 3x error. So the fixture
        # silently exercised the unknown branch while claiming to be the
        # Sepolia one. Pinned now by
        # `test_every_closed_vocabulary_fixture_value_is_a_member`.
        "pool4_reward_path": "direct",
        "pool4_distributor_addr": None,
        "pool4_distributor_staking_bps": None,
        "pool4_distributor_nodes_bps": None,
        "pool4_distributor_bonding_bps": None,
        "pool4_distributor_staking_earned": None,
        "pool4_distributor_nodes_earned": None,
        "pool4_distributor_bonding_earned": None,
        "pool4_distributor_held_nodes": None,
        "pool4_distributor_held_bonding": None,
        "pool4_discovery_source": None,
        # The inventory ceiling. Sepolia's decay rate is the no-decay
        # sentinel, so the cap sits exactly ON the inventory and the headroom
        # is a real, representable **0.0** -- not a dash, and not a number to
        # "fix" into something non-zero. `pool4_cap_decay_per_day` is `None`
        # rather than 2**128-1: the producer resolves the sentinel, and a
        # panel must never print ~3.4e20 IMD/day.
        "pool4_inventory_cap": 472_569_750.774434,
        "pool4_cap_headroom": 0.0,
        "pool4_cap_decay_per_day": None,
        # Newest first, capped by the manager at POOL4_FLOW_LIMIT. Three rows
        # and three different meanings of a zero leg, which is the whole
        # subject of this panel:
        #   * the SELL settled and both legs are real numbers;
        #   * the BUY has no burn leg and no staker leg, and those are
        #     `0.0` -- a fact about the mechanism, never `None`;
        #   * the accrued SELL's legs are `0.0` for a different reason
        #     (`ClaimsSettled` has not fired), which is why it carries
        #     `settled: False` and the panel flags it.
        "pool4_flow": [
            {
                "ts": 1_756_000_000.0, "age_s": 120.0, "side": "sell",
                "size_imd": 1234.5, "burned_imd": 111.42,
                "stakers_imd": 12.38, "fee_imd": None, "fee_eth": 0.0057,
                "settled": True, "tx_hash": "0x" + "ab" * 32,
            },
            {
                "ts": 1_755_999_000.0, "age_s": 420.0, "side": "buy",
                "size_imd": 987.65, "burned_imd": 0.0, "stakers_imd": 0.0,
                "fee_imd": 12.38, "fee_eth": None,
                "settled": True, "tx_hash": "0x" + "cd" * 32,
            },
            {
                "ts": 1_755_998_000.0, "age_s": 840.0, "side": "sell",
                "size_imd": 4500.0, "burned_imd": 0.0, "stakers_imd": 0.0,
                "fee_imd": None, "fee_eth": 0.0031,
                "settled": False, "tx_hash": "0x" + "ef" * 32,
            },
        ],
        # The ten levers `surf_manager._pool4_hatch_rows` really emits, in its
        # own order -- not a sample of them. The count is load-bearing for
        # this body's height (`SURF_POOL4_FULL_LAYOUT_ROWS`), so a fixture
        # carrying five would measure a panel eight rows shorter than the one
        # a user sees.
        "pool4_hatches": [
            {"scope": "vault", "label": "owner", "state": "renounced",
             "detail": None, "addr": None, "addr_known": False},
            {"scope": "vault", "label": "paused", "state": "live",
             "detail": None, "addr": None, "addr_known": False},
            {"scope": "vault", "label": "rescue", "state": "open",
             "detail": "owner may sweep stray tokens", "addr": None,
             "addr_known": False},
            {"scope": "dripper", "label": "owner", "state": "live",
             "detail": None,
             "addr": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
             "addr_known": True},
            {"scope": "dripper", "label": "rewards", "state": "live",
             "detail": None,
             "addr": "0x4dBE1782b0aC0dE1f2a3B4c5D6e7F8a9B0c1449B",
             "addr_known": True},
            {"scope": "hook", "label": "owner", "state": "live",
             "detail": None,
             "addr": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
             "addr_known": True},
            {"scope": "hook", "label": "market", "state": "open",
             "detail": None, "addr": None, "addr_known": False},
            {"scope": "hook", "label": "rebalance", "state": "open",
             "detail": "backstop rebalance enabled", "addr": None,
             "addr_known": False},
            {"scope": "hook", "label": "burn sink", "state": "live",
             "detail": None,
             "addr": "0x000000000000000000000000000000000000dEaD",
             "addr_known": True},
            {"scope": "bond", "label": "deployed", "state": "unknown",
             "detail": None, "addr": None, "addr_known": False},
        ],
    }


#: The MAINNET deployment, from ``docs/imd_pool4_mainnet.md`` -- every number
#: a live read on the day pool4 went live, not a figure from the project's
#: own docs page.
#:
#: It exists because four of this body's behaviours differ by deployment and
#: three of them are invisible on Sepolia: the reward split is three-way
#: rather than two-way, ``rewardShareBps`` is 1500 rather than 1000,
#: ``capFloor`` is 1,000 IMD rather than 250M, and the inventory cap actually
#: *decays* rather than tracking the inventory. A body swept only against
#: Sepolia is a body measured against the state the data is no longer in.
#:
#: ⚠ ``pool4_cap_headroom`` IS ``cap − reserve``: 5,331.227804 − 5,236.544041
#: = **+94.683763**. Its sibling ``pool4_floor_distance`` is ``reserve −
#: floor``. The operand order flips so both read positive when healthy, and
#: writing this one by analogy with the other gives −94.68 -- a binding cap
#: rendered as slack. ``test_the_cap_headroom_keeps_its_operand_order`` pins
#: the sign against the two operands rather than against a literal, so a
#: fixture edit cannot quietly reverse it.
def _mainnet_pool4_payload(**overrides) -> dict:
    reserve = 5_236.544041
    cap = 5_331.227804
    floor = 1_000.0
    payload = _frozen_payload(
        pool4_network="MAINNET",
        pool4_discovery_state="adopted",
        pool4_discovery_detail=_ADOPTED_DISCOVERY_DETAIL,
        pool4_discovery_source_tx=_ADOPTED_SOURCE_TX,
        # The disclosure: this adoption came from the docs page, which is a
        # weaker provenance than a dev-signed announce post.
        pool4_discovery_source="docs",
        pool4_hook_addr="0xc6c965bd164c483e87d0b550671798e9a3602840",
        pool4_vault_addr="0x9efa934d9fad4ae28c998a40195646b965a97247",
        pool4_dripper_addr="0xe6D3De6daEAf327fCA42745f1998FcD989e00884",
        # -- the three-way split, inside the Distributor -------------------
        #
        # `via-distributor`, NOT "three-way": the key carries the TOPOLOGY
        # (is there a Distributor between the hook and the Dripper), not the
        # number of legs the split has. Both fixtures named the split shape
        # here until 2026-09-02 -- see the note in `_frozen_payload` above.
        pool4_reward_path="via-distributor",
        pool4_distributor_addr="0x9046739E1535B40EfBe6AB3f45d0024b690eCA30",
        pool4_distributor_staking_bps=3000,
        pool4_distributor_nodes_bps=3000,
        # THE REMAINDER, and written as the derivation rather than as 4000 so
        # this fixture cannot assert a number the chain never returned.
        pool4_distributor_bonding_bps=10_000 - 3000 - 3000,
        pool4_distributor_staking_earned=3.1490,
        pool4_distributor_nodes_earned=3.1490,
        pool4_distributor_bonding_earned=4.1986,
        pool4_distributor_held_nodes=3.1490,
        pool4_distributor_held_bonding=4.1986,
        # -- the ceiling, which on mainnet genuinely binds -----------------
        pool4_tokens_in_pool=reserve,
        pool4_inventory_cap=cap,
        pool4_cap_headroom=cap - reserve,          # +94.683763. NOT reserve - cap.
        pool4_cap_decay_per_day=1_000.0,
        pool4_cap_floor=floor,
        pool4_floor_distance=reserve - floor,      # the sibling, other way round
        # -- the rest of the live state ------------------------------------
        pool4_reward_share_bps=1500,
        pool4_eth_in_pool=3.7976,
        pool4_total_burned=59.4807,
        pool4_total_rewarded=10.4966,
        pool4_total_fee_token=0.8437,
        pool4_retained_eth=0.0479,
        pool4_current_tick=72_761,
        pool4_ref_tick=72_667,
        pool4_share_price=7.902919,
        pool4_vault_assets=1_293.31,
        pool4_drip_per_day=86.4,
        pool4_drippable=0.0,
        pool4_can_drip=False,
    )
    payload.update(overrides)
    return payload


def _frozen_payload(**overrides) -> dict:
    """Exactly ``SURF_KEYS`` -- a key added upstream appears here as ``None``."""
    sample = _sample_data()
    payload = {key: sample.get(key) for key in SURF_KEYS}
    payload.update(overrides)
    return payload


def _all_none_payload() -> dict:
    """Every contract key present, every value ``None`` (full outage)."""
    return {key: None for key in SURF_KEYS}


class _FakeManager:
    """Stand-in for SurfManager that never touches the network.

    ``raises=True`` is a *defensive* double, not a model of an outage: the
    real ``SurfManager.fetch_and_compute`` never raises (WP4 guarantees the
    full ``SURF_KEYS`` dict with ``None`` values under every failure
    combination).  Use ``_all_none_payload()`` for an outage; ``raises=True``
    only to prove a mis-wired manager cannot take the screen down.
    """

    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self._payload = payload if payload is not None else _frozen_payload()
        self._raises = raises
        self._error_count = 3
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self._raises:
            raise RuntimeError("all three pools are down")
        return dict(self._payload)

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single SurfScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _ThemedHarness(_Harness):
    """Same, but with the real ``minimal.tcss`` loaded.

    Valid before WP6 adds a surf block: loading the stylesheet without surf
    rules leaves ``SurfScreen.DEFAULT_CSS`` in charge, and keeps passing after
    WP6 restates it.
    """

    CSS_PATH = _TCSS


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _plain(widget) -> str:
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


# -- contract sanity -----------------------------------------------------


def test_surf_keys_covers_the_local_signature_map():
    """Every dispatched kwarg is a contract key, and the map + META is total.

    This is the tripwire for WP0<->WP5 drift (the contract vs. this screen's
    dispatch map) while SURF_WIDGET_SIGNATURES lives locally: a key added to
    SURF_KEYS that no widget receives, or a kwarg here that left the contract,
    both fail loudly. ``_KEYS_PENDING_CONSUMERS`` is a named, enumerated
    carve-out for the v4/launchpad keys Tasks 8-12 have not wired yet -- a
    key regressing outside that list still fails here.
    """
    dispatched = {k for sig in SURF_WIDGET_SIGNATURES.values() for k in sig}
    assert dispatched <= set(SURF_KEYS), (
        f"dispatch kwargs not in SURF_KEYS: {sorted(dispatched - set(SURF_KEYS))}"
    )
    unconsumed = (
        set(SURF_KEYS)
        - dispatched
        - META_KEYS
        - _KEYS_WITHOUT_A_RENDERER
        - _KEYS_PENDING_CONSUMERS
    )
    assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"
    # The carve-outs are carve-outs from something. A key that left SURF_KEYS
    # but stayed listed here is a waiver nobody is using any more, and it
    # would hide the next real orphan by absorbing its name.
    stale = (META_KEYS | _KEYS_WITHOUT_A_RENDERER) - set(SURF_KEYS)
    assert not stale, f"a carve-out names a key SURF_KEYS no longer has: {sorted(stale)}"
    assert not (META_KEYS & _KEYS_WITHOUT_A_RENDERER), (
        "a key claims both to be consumed by the screen and to reach nothing"
    )
    assert not (dispatched & _KEYS_WITHOUT_A_RENDERER), (
        "a key is parked as unrendered while a widget is dispatched it: "
        f"{sorted(dispatched & _KEYS_WITHOUT_A_RENDERER)}"
    )


def test_the_unrendered_keys_are_named_by_no_widget_signature():
    """``_KEYS_WITHOUT_A_RENDERER`` has to keep being *true*, not just listed.

    Every surf widget's ``update_data`` ends in ``**_kwargs``, so re-wiring
    one of these keys raises nothing and changes no test on its own -- the
    parked list would simply go on claiming the key reaches nothing while a
    box rendered it. Reading the real signatures is what turns that into a
    failure: name ``lp_imd=`` in an ``update_data`` again and this goes red,
    with the instruction to move it back into ``SURF_WIDGET_SIGNATURES``.
    """
    import inspect

    named: dict[str, set[str]] = {}
    for name, cls in _ALL_WIDGET_CLASSES.items():
        params = inspect.signature(cls.update_data).parameters
        for param in params.values():
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                continue
            named.setdefault(param.name, set()).add(name)

    still_named = {
        key: sorted(named[key]) for key in _KEYS_WITHOUT_A_RENDERER if key in named
    }
    assert not still_named, (
        "these keys are parked as reaching no renderer, but a widget names "
        f"them in its update_data signature: {still_named} -- move them back "
        "into SURF_WIDGET_SIGNATURES"
    )


# The binding set is asserted in the POOL4 section at the end of this file
# (``test_the_bindings_are_refresh_and_the_two_view_toggles``), which replaced
# the launchpad-only version that lived here. Two tests pinning different
# exact contents of one ``BINDINGS`` set cannot both pass, so it moved rather
# than gaining a sibling.


# -- the l LAUNCHPAD view (2026-08-23) ------------------------------------


def _surf_app(payload: dict | None = None) -> App:
    """A themed harness around a fresh SurfScreen, for the mode-toggle tests.

    Themed (the real ``minimal.tcss`` loaded), so the launchpad body's CSS
    block is exercised the same way a live app renders it, not just
    ``SurfScreen.DEFAULT_CSS`` in isolation.
    """
    manager = _FakeManager(payload)
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    return _ThemedHarness(screen)


async def test_l_swaps_the_body_and_keeps_the_hero() -> None:
    """Body swap on curator's y/f precedent: the hero never leaves."""
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is True
        assert pilot.app.screen.query_one(SurfHero).display is True
        assert pilot.app.screen.query_one("#middle-row").display is False


async def test_escape_backs_out_one_way() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("escape")
        assert pilot.app.screen.query_one("#middle-row").display is True


async def test_l_is_idempotent_and_toggles_back() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("l")
        assert pilot.app.screen.query_one("#middle-row").display is True


async def test_the_status_hint_names_the_new_view() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for s in strips for seg in s)
        assert "l launchpad" in text


async def test_l_also_hides_the_separator_and_bottom_row() -> None:
    """The brief's own test only names ``#middle-row``; the other two rows
    of the dashboard body must not be left showing under the launchpad
    body, or the screen would render both stacked on top of each other."""
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        assert pilot.app.screen.query_one("#separator").display is False
        assert pilot.app.screen.query_one("#bottom-row").display is False


async def test_the_launchpad_widgets_are_dispatched_hidden_before_l_is_pressed() -> None:
    """Composed-once-shown-by-display: the first ``l`` paints a complete
    frame, not a blank one that fills in a beat later (curator's own reason
    for dispatching its `f`/`l` bodies whether or not they are showing)."""
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        coins = pilot.app.screen.query_one(SurfLaunchpadCoins)
        # The widget's own ``.display`` is untouched by ``_show_mode`` --
        # only the container's is set, and it is what actually hides
        # everything inside it -- so this checks the container, not the
        # child.
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is False
        # Dispatched: the population note has moved off its "Loading"
        # placeholder even though nothing has displayed it yet. It rides on
        # the panel's own title row since Task 11 -- `#surf-lpc-note` is
        # gone, and a widget whose whole job was a blank line was renamed
        # `#surf-lpc-gap` rather than left carrying a name it had stopped
        # earning. ``_plain`` reads the widget's own visual directly, unlike
        # ``_screen_text`` -- a hidden widget reaches no compositor row at
        # all.
        title = coins.query_one("#surf-lpc-title")
        assert "146 coins" in _plain(title)


# -- the launchpad body's right rail (2026-08-24) -------------------------


async def test_the_launchpad_summary_panels_sit_beside_the_coins_table() -> None:
    """CURVE FLOW and BURN PIPELINE moved out from under the coin table.

    Stacked, the two summary panels took eleven rows off the one panel in
    this body whose row count is real data -- their own ten lines are
    label/value text that never grows. Beside the table they cost columns
    instead, which is the currency a fixed-column ``DataTable`` was already
    spending a constant amount of.

    ``_surf_app`` is the **themed** harness, and that is load-bearing here:
    the app stylesheet outranks ``SurfScreen.DEFAULT_CSS``, so a rail written
    into ``DEFAULT_CSS`` alone would leave ``minimal.tcss``'s own
    ``SurfLaunchpadCoins { width: 100% }`` in charge and put the rail back
    under the table with nothing raising. This test is what notices.
    """
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen

        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        coins = screen.query_one(SurfLaunchpadCoins)
        flow = screen.query_one(SurfCurveFlow)
        pipeline = screen.query_one(SurfBurnPipeline)

        assert [type(c).__name__ for c in rail.children] == [
            "SurfCurveFlow", "SurfBurnPipeline", "SurfBurnkeepers",
        ]
        # To the RIGHT of the table, and beside it rather than below.
        assert coins.region.right <= rail.region.x
        assert flow.region.x >= rail.region.x
        assert flow.region.y < coins.region.bottom
        # Stacked inside the rail, flow above the pipeline, same column.
        assert flow.region.x == pipeline.region.x
        assert flow.region.bottom <= pipeline.region.y
        # Composited, not merely laid out: both titles reach a pixel while
        # the table is on screen, and the table keeps the screen's spare rows.
        rail_text = _region_text(pilot.app, rail)
        assert "CURVE FLOW" in rail_text and "BURN PIPELINE" in rail_text
        # The spare rows CHANGED HANDS on 2026-08-25 and this is where that
        # is visible. It used to read ``coins.region.height >
        # flow.region.height``, on the grounds that the table was the one
        # panel here whose row count was real data. The table is capped at
        # ten rows now, so it sizes to its content like the summary panels
        # do, and the two panels that grow are the ones with unbounded
        # content: LAUNCHPAD ACTIVITY in the left column, BURNKEEPERS in the
        # rail. Left as it was, this line would assert the old regime and
        # go red for the right reason -- so it is restated, not deleted.
        activity = screen.query_one(SurfLaunchpadActivity)
        keepers = screen.query_one(SurfBurnkeepers)
        assert activity.region.height > flow.region.height
        assert keepers.region.height > flow.region.height


# -- the l body's two columns and five panels (2026-08-25) ----------------


async def test_the_launchpad_body_holds_five_panels_in_two_columns() -> None:
    """Two columns, five panels, and the order within each is the layout.

    ``#surf-launchpad-left`` is new: the coin table is capped at ten rows, so
    it has no use for the body's spare rows and LAUNCHPAD ACTIVITY -- a feed,
    whose content is unbounded -- takes them. Asserted on the *children* of
    each container rather than on a screen-wide query, because a panel
    mounted into the wrong column still answers ``query_one`` from the
    screen and would leave this green.
    """
    async with _surf_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        assert [type(w) for w in left.children] == [
            SurfLaunchpadCoins, SurfLaunchpadActivity,
        ]
        assert [type(w) for w in rail.children] == [
            SurfCurveFlow, SurfBurnPipeline, SurfBurnkeepers,
        ]
        # ...and the two columns really are side by side, not stacked: the
        # child lists above are identical either way.
        assert left.region.right <= rail.region.x
        assert left.region.y == rail.region.y


async def test_both_new_panels_are_dispatched_on_every_refresh() -> None:
    """Dispatched whether or not ``l`` is showing, so the first keypress
    paints a complete frame instead of a blank one -- the contract the other
    three launchpad panels already keep.
    """
    async with _surf_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        # Still in MODE_DASHBOARD: neither panel has been displayed once.
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is False
        assert pilot.app.screen.query_one(SurfLaunchpadActivity)._payload
        assert pilot.app.screen.query_one(SurfBurnkeepers)._payload
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "LAUNCHPAD ACTIVITY" in text and "BURNKEEPERS" in text
    # The payload, not just the titles -- a dispatched panel that rendered
    # its empty state would satisfy the two title checks above.
    assert "PANE" in text and "0xbbbb…bbbb" in text


async def test_a_dead_launchpad_sweep_leaves_both_new_panels_explicit() -> None:
    """No blank panel, no stale number presented as live."""
    from maxpane_dashboard.widgets.surf.burnkeepers import UNAVAILABLE_LINE as BK
    from maxpane_dashboard.widgets.surf.launchpad_activity import (
        UNAVAILABLE_LINE as ACT,
    )
    payload = _frozen_payload(
        launchpad_activity=None, launchpad_burnkeepers=None
    )
    async with _surf_app(payload).run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert ACT in text and BK in text


async def test_the_rows_the_capped_coin_table_gave_up_go_to_the_feed() -> None:
    """The whole reason the left half became a column.

    ``SurfLaunchpadCoins`` is ``height: auto`` and so is the ``DataTable``
    inside it -- and the second half is the one that actually does the work.
    The ``1fr`` this body used to hand the panel lives on that table
    (``widgets/surf/launchpad.py``'s own ``DEFAULT_CSS``); take it off the
    panel alone and the table goes on claiming the column's spare rows from
    inside an auto-sized parent, the cap buys the feed nothing, and every
    structural test above still passes.

    Measured at two terminal heights, because "the table is short" is not
    the claim -- "the table does not grow, and the feed does" is, and one
    height cannot tell them apart.
    """
    heights: dict[int, tuple[int, int]] = {}
    for rows in (30, 50):
        async with _surf_app().run_test(size=(150, rows)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.press("l")
            await pilot.pause()
            screen = pilot.app.screen
            heights[rows] = (
                screen.query_one(SurfLaunchpadCoins).region.height,
                screen.query_one(SurfLaunchpadActivity).region.height,
            )

    (coins_30, feed_30), (coins_50, feed_50) = heights[30], heights[50]
    assert coins_30 == coins_50, (
        f"the coin table grew {coins_30} -> {coins_50} rows with the "
        "terminal: it is still claiming the column's spare rows"
    )
    assert feed_50 > feed_30, (
        f"the feed did not take the 20 rows the terminal grew by "
        f"({feed_30} -> {feed_50})"
    )
    assert feed_50 - feed_30 == 20, (heights, "the spare rows went elsewhere")


async def test_the_floored_panels_never_thin_out_below_their_floor() -> None:
    """``min-height`` on a ``1fr`` child is load-bearing, not decoration.

    A ``1fr`` child cannot overflow its container -- it SHRINKS -- so without
    a floor each of these two panels sheds one line per terminal row down to
    a bare title, with no scrollbar, no ``‹ widen`` and no other trace
    anywhere on screen. The floor is what turns that into an overflow the
    containing column's ``overflow-y: auto`` can show, and the title bar's
    ``‹ taller`` is what advertises it.

    **Asserted on the laid-out height AND on the marker, not on composited
    cells, and the difference matters both ways.** A floored panel that the
    column has scrolled past composites *zero* rows -- correctly: it is
    below the fold, reachable by scrolling, and ``‹ taller`` says so. So a
    composited-cell assertion here would fail on a layout that is behaving
    exactly as designed. What the earlier version of this test was missing
    is the other half: it proved the panels keep their rows without proving
    anything on screen tells the reader those rows are off the fold. Both
    are asserted now, at a height short enough that the body genuinely
    cannot fit them.
    """
    async with _surf_app().run_test(size=(150, 20)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        activity = screen.query_one(SurfLaunchpadActivity)
        keepers = screen.query_one(SurfBurnkeepers)
        assert activity.region.height >= 6, activity.region.height
        assert keepers.region.height >= 5, keepers.region.height
        # The floors are only honest if the overflow they create is visible
        # somewhere. It is not the panels' own job -- they have no marker --
        # so it has to be the title bar's, on the row that cannot be pushed
        # off. Without this the assertions above are green in a state where
        # BURNKEEPERS reaches the screen as nothing at all.
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]
        assert (
            screen.query_one(f"#{LAUNCHPAD_LEFT_ID}").show_vertical_scrollbar
            or screen.query_one(f"#{LAUNCHPAD_RAIL_ID}").show_vertical_scrollbar
        ), "neither column is scrolling, so the floors are not being tested"


#: The two heights the gutter proof is measured at, and neither is arbitrary.
#:
#: The launchpad rail first overflows at **22** rows (measured: 23 shows no
#: scrollbar, 22 does), so 46 is comfortably on the roomy side and 22 is the
#: first row count where the scrollbar actually exists. A pair of heights that
#: both sit above the crossover cannot fail -- fix round 1 shipped exactly
#: that mistake with (46, 24), and the reviewer caught it by deleting the
#: property and watching the "proof" stay green.
_RAIL_ROOMY_ROWS = 46
_RAIL_OVERFLOWING_ROWS = 22


async def _launchpad_rail_widths(height: int, width: int = 150) -> dict:
    """Rail geometry in the ``l`` body at *height* rows -- the widths the
    gutter is actually about, plus whether the scrollbar is really there."""
    async with _surf_app().run_test(size=(width, height)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        return {
            "flow": screen.query_one(SurfCurveFlow).region.width,
            "pipeline": screen.query_one(SurfBurnPipeline).region.width,
            "coins": screen.query_one(SurfLaunchpadCoins).region.width,
            "overflowing": rail.show_vertical_scrollbar,
        }


async def test_the_launchpad_rail_reserves_its_scrollbar_gutter() -> None:
    """Curator's ``#curator-right-rail`` bug, pre-empted -- and *proved*.

    Without ``scrollbar-gutter: stable`` the rail's scrollbar takes a column
    away the moment the rail overflows, so the layout's WIDTH requirement
    moves with its HEIGHT: the width Task 13 pins at one terminal height is a
    column short at another. Curator shipped exactly that -- one pin true at
    48 rows and one column short at 40.

    **The column belongs to the rail's own children, not to the table beside
    it.** That is the whole subject of this test and fix round 1 got it
    wrong: it compared ``SurfLaunchpadCoins.region.width``, which a ``7fr``
    seam fixes at 80 regardless of the rail's scrollbar, at two heights that
    were *both* above the overflow crossover. Two independent reasons it
    could never fail. Measured with the property deleted from both
    stylesheets:

    * ``coins`` -- 80 at 46 rows and 80 at 22. Unchanged by the mutation.
      The wrong subject.
    * ``flow``/``pipeline`` -- 70 at 46 rows, 69 at 22. **That** is the
      column the gutter reserves, and reserving it is what makes the two
      heights agree.

    So the assertion is: the rail's children are the same width whether or
    not the rail is tall enough to need a scrollbar. It is checked against
    laid-out regions rather than ``styles.scrollbar_gutter`` because a style
    read cannot see a one-copy CSS deletion (the app stylesheet and
    ``DEFAULT_CSS`` cover for each other) -- that half is guarded by
    ``test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet``
    instead, which compares the property between the two copies.
    """
    roomy = await _launchpad_rail_widths(_RAIL_ROOMY_ROWS)
    cramped = await _launchpad_rail_widths(_RAIL_OVERFLOWING_ROWS)

    # The premise: the two heights straddle the overflow crossover. Without
    # this the comparison below is trivially true and tests nothing -- which
    # is precisely how the first version of this test passed.
    assert not roomy["overflowing"], (
        f"the rail already overflows at {_RAIL_ROOMY_ROWS} rows -- both "
        "sample heights are on the same side of the crossover"
    )
    assert cramped["overflowing"], (
        f"the rail does not overflow at {_RAIL_OVERFLOWING_ROWS} rows -- the "
        "condition this test exists to measure never occurs"
    )

    for panel in ("flow", "pipeline"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at {_RAIL_ROOMY_ROWS} rows "
            f"and {cramped[panel]} at {_RAIL_OVERFLOWING_ROWS}: the "
            "scrollbar took a column instead of using its reserved gutter, "
            "so this layout's width requirement now moves with its height"
        )

    # The declaration itself, so a rail that happened to agree for some other
    # reason still names the property it is relying on.
    async with _surf_app().run_test(size=(150, _RAIL_ROOMY_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        rail = pilot.app.screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        assert "stable" in str(rail.styles.scrollbar_gutter)


async def test_the_hero_survives_the_launchpad_body_swap() -> None:
    """The hero is outside ``#surf-launchpad-body``, so nothing it tracks
    goes dark when ``l`` swaps the body underneath it.

    Asserted against the hero's **own region**, not the whole screen: three
    of its four box titles are words the launchpad panels also composite
    (``LAUNCHPAD COINS``, ``CURVE FLOW``'s numbers, ``BURN PIPELINE``), so a
    whole-screen substring check would pass with the hero unmounted entirely.
    """
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is True

        hero = _region_text(pilot.app, screen.query_one(SurfHero))
        for title in ("LAUNCHPAD", "FLOW", "BURN", "IMD SUPPLY"):
            assert title in hero, f"the hero lost its {title} box under `l`"
        # The live numbers, not just the frame: BURN and SUPPLY read the fast
        # tier and are the pair that would go dark if the hero were swapped.
        assert "2,376,732 IMD" in hero
        assert "READY" in hero


# -- the launchpad body's CSS, in agreement (Task 12 addendum) ------------
#
# In the shape of curator's
# ``test_selected_nft_geometry_matches_widget_and_screen_fallback_css``: an
# automated structural comparator, not a sentence promising the two copies
# match. That exact class of drift shipped as recently as v0.8.2 (a widget's
# own ``DEFAULT_CSS`` gained a property the screen's fallback copy did not),
# and ``tests/test_surf_registration.py::
# test_the_stylesheet_block_and_default_css_describe_one_layout`` already
# guards the *whole* surf screen's two CSS copies the same way -- this is a
# second, narrower guard scoped to just the launchpad-body selectors this
# task adds, living in this task's own test file rather than depending on a
# file this task does not own to keep catching drift in the code it owns.

#: ``overflow-y``, ``scrollbar-gutter`` and ``scrollbar-size`` joined the
#: geometry in 2026-08-24, with the rail. They are not decoration here: the gutter is what stops the
#: rail's scrollbar from taking a column out of the coin table beside it on
#: short terminals only, and a property declared in one copy and not the other
#: is *invisible* rather than conflicting -- Textual falls back to DEFAULT_CSS
#: for a property the app stylesheet never mentions, so the layout would be
#: right under both stylesheets today and wrong under one of them the moment
#: either copy's value changed. This is the only guard the pair has: the
#: ``scrollbar-size`` is here for the identical reason and was left out of
#: the first pass, one property over from the hole it was closing: the
#: Textual default is two cells wide, so a copy that drops the ``1 1`` gives
#: the rail's children a column *less* than the other copy does -- the same
#: height-dependent width drift, arrived at from the other direction.
_LAUNCHPAD_CSS_STRUCTURAL = (
    "width", "min-width", "max-width", "height", "min-height", "padding",
    "margin", "overflow-y", "scrollbar-gutter", "scrollbar-size",
)
#: Shorthand properties whose absence means "the CSS default" -- so one copy
#: spelling ``padding: 0 0`` and the other omitting it is agreement, not
#: drift. Mirrors ``tests/test_surf_registration.py``'s own constant.
_LAUNCHPAD_CSS_SHORTHAND_DEFAULTS = {"padding": "0", "margin": "0"}

_LAUNCHPAD_CSS_SELECTORS = (
    f"#{LAUNCHPAD_BODY_ID}", f"#{LAUNCHPAD_LEFT_ID}", f"#{LAUNCHPAD_RAIL_ID}",
    "SurfLaunchpadCoins",
    # The `1fr` the coin table used to carry really lives on its DataTable
    # (`widgets/surf/launchpad.py`'s own DEFAULT_CSS), so the override that
    # takes it to `auto` is geometry like any other and has to agree across
    # both copies -- this is the selector that would silently disagree
    # otherwise, and the panel above it would look identical in both files
    # while rendering differently.
    "SurfLaunchpadCoins > DataTable",
    "SurfLaunchpadActivity",
    "SurfCurveFlow", "SurfBurnPipeline", "SurfBurnkeepers",
)


def _expand_css_box(value: str) -> tuple[str, ...]:
    """CSS box shorthand -> four values, so ``0 0`` == ``0`` == ``0 0 0 0``."""
    parts = value.split()
    if len(parts) == 1:
        return tuple(parts * 4)
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    return tuple(parts[:4])


def _css_rules(css: str) -> dict[str, dict[str, str]]:
    """``{selector: {property: value}}`` for the structural properties.

    A leading ``SurfScreen `` is stripped: ``DEFAULT_CSS`` scopes every rule
    to the screen, while the stylesheet block scopes only the ids (the
    shared ``#middle-row``/``#bottom-row`` rules elsewhere in the file are
    law for ten other screens) and leaves the ``Surf*`` types unscoped,
    since those types exist nowhere else. The two spellings mean the same
    thing here -- the same reasoning ``tests/test_surf_registration.py``
    already applies to the rest of this screen's CSS.
    """
    import re

    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[str, dict[str, str]] = {}
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        head, body = chunk.split("{", 1)
        props: dict[str, str] = {}
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            name, _, value = decl.partition(":")
            name = name.strip()
            if name in _LAUNCHPAD_CSS_STRUCTURAL:
                props[name] = " ".join(value.split())
        if not props:
            continue
        for selector in head.split(","):
            selector = " ".join(selector.split())
            if selector.startswith("SurfScreen "):
                selector = selector[len("SurfScreen "):]
            out.setdefault(selector, {}).update(props)
    return out


def _surf_stylesheet_block() -> str:
    """The surf section of the shared stylesheet, or ``''`` if absent."""
    text = _TCSS.read_text(encoding="utf-8")
    marker = "/* ── Surf screen"
    if marker not in text:
        return ""
    start = text.index(marker)
    nxt = text.find("/* ── ", start + len(marker))
    return text[start:] if nxt == -1 else text[start:nxt]


def test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet() -> None:
    """``SurfScreen.DEFAULT_CSS`` and the surf block in ``minimal.tcss`` must
    describe the launchpad body's geometry identically -- edit both or
    neither. The app stylesheet is what actually renders (it outranks
    ``DEFAULT_CSS``); ``DEFAULT_CSS`` is what keeps the screen correctly
    proportioned when it is reviewed or mounted without the app stylesheet.
    """
    fallback = _css_rules(SurfScreen.DEFAULT_CSS)
    block = _css_rules(_surf_stylesheet_block())

    for selector in _LAUNCHPAD_CSS_SELECTORS:
        assert selector in fallback, (
            f"{selector} is not styled in SurfScreen.DEFAULT_CSS"
        )
        assert selector in block, (
            f"{selector} is not styled in the surf block of minimal.tcss"
        )
        for prop in _LAUNCHPAD_CSS_STRUCTURAL:
            default = _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS:
                assert _expand_css_box(left) == _expand_css_box(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


# -- the l body's own measured width (Task 13; re-swept 2026-08-25) -------
#
# ``SURF_FULL_LAYOUT_COLUMNS`` (this screen) and ``__main__.FULL_LAYOUT_
# COLUMNS`` (the app) are FWA's 143 and this task moves neither -- the
# measurement, the binding panel, the per-seam table and why the CLAUDE.md
# width record is not appended to are all in
# ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``'s own docstring in
# ``screens/surf.py``.
#
# The sweep below runs 128..150: comfortably below *and* above the measured
# 138, and never starting at it, so it could not agree with the pin by
# construction.
#
# It ran 80..105 until 2026-08-24 and 120..145 until 2026-08-25. Each range
# was right for the body it was written against -- three stacked full-width
# panels binding at 93, then a 12:5 rail binding at 135 -- and each had to
# move when the pin did. Re-centre the range whenever the pin moves.


def _title_text(pilot) -> str:
    """Composited screen text, named for this task's own sweep pseudocode.

    Not just row 0: the marker this task adds lives on the binding panel's
    *own* title (``SurfLaunchpadCoins``, the ``SurfMarket``/curator
    ``CuratorOperators`` idiom), not a screen-wide banner the way
    ``TALLER_HINT`` is -- curator's own ``_analysis_view_text`` returns the
    whole composited screen for the identical reason.
    """
    return _screen_text(pilot.app)


def _clipped_launchpad_lines(app, screen) -> list[str]:
    """Every composited line in the ``l`` body that ends in a truncation.

    **Asked of the five panels, never of their two containers**, and that is
    a correctness fix rather than a tidy-up. ``_region_text`` slices the
    compositor to a widget's rectangle, and a *container*'s rectangle
    includes the column reserved by ``scrollbar-gutter: stable`` -- so on any
    row where the scrollbar glyph is painted, a genuinely clipped line no
    longer *ends* in ``…`` and the check goes quiet exactly when the layout
    is under most pressure. Each panel's own rectangle excludes that gutter.

    It asks whether a line ENDS in ``…``, not whether one contains one.
    ``text-overflow: ellipsis`` puts its ellipsis at the truncation point,
    which is the end of the rendered line, so this catches every clip a bare
    ``in`` would. What it stops catching is a false positive that arrived
    with BURNKEEPERS (2026-08-25): its wallet cell is a deliberate
    anti-poisoning *window*, ``0xbbbb…bbbb``, whose ellipsis is a glyph in
    the middle of a line that fits perfectly well. Left as ``in``, the sweep
    below failed at every width from the pin up while nothing was clipped
    anywhere -- a red test that would have been "fixed" by moving a pin.
    """
    out = []
    for cls in _LAUNCHPAD_WIDGET_CLASSES.values():
        for line in _region_text(app, screen.query_one(cls)).split("\n"):
            if line.rstrip().endswith("…"):
                out.append(line)
    return out


@pytest.mark.parametrize(
    "payload", [None, "ordinary"], ids=["committed-capture", "ordinary-burn-line"]
)
@pytest.mark.parametrize("width", range(128, 151))
async def test_the_launchpad_body_is_whole_from_its_pinned_width(width, payload) -> None:
    """Start the sweep away from the pin: a sweep that began at the constant
    would agree with it by construction.

    **Swept against both payload magnitudes**, because the rail's need is
    data-dependent (see :func:`_ordinary_burn_payload`) and this pin's whole
    claim is that it is *not*. A capture-only sweep pins the pin from below
    for the small case only; running the same widths against an ordinary
    burn line is what makes "138 either way" an assertion rather than a
    sentence in a docstring.

    The dashboard body's own widen marker (the announce feed's linked-tx
    post, deliberately excluded from ``_widen_sweep_payload`` -- see that
    fixture's own docstring) cannot contaminate this sweep: ``#middle-row``
    is hidden in ``MODE_LAUNCHPAD``, so nothing it composites reaches the
    screen while ``l`` is showing.

    **Whole means the whole body, not merely the panels that can say so.**
    Three of the five panels here advertise ``‹ widen`` and two --
    ``SurfCurveFlow`` and ``SurfBurnPipeline`` -- are plain label/value
    ``Static``s that ellipsise and go quiet. Asserting only on the marker
    would therefore accept a seam whose *rail* binds, and that is not a
    hypothetical: it is what the ``12fr:5fr`` seam this body shipped with
    actually did: as shipped it clipped ``accrued 1.2K IMD · staged 45.00
    I…`` at 129..132 (131..132 once the left column reserved its own
    scrollbar gutter) with no ``‹ widen`` anywhere on screen, which is why
    **no value of the constant could make this sweep green** and the fix
    was a re-seam rather than a re-typed number. The clip check below is what makes that a
    failure instead of a green sweep.
    """
    pl = _ordinary_burn_payload() if payload == "ordinary" else None
    async with _surf_app(pl).run_test(size=(width, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        title = _title_text(pilot)
        clipped = _clipped_launchpad_lines(pilot.app, pilot.app.screen)
        if width >= SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS:
            assert "‹ widen" not in title, width
            assert not clipped, (
                f"at {width} the l body is clipping a line and nothing on "
                f"screen says so: {clipped}"
            )
        else:
            assert "‹ widen" in title, width


#: The burn pipeline in the state the data is normally in.
#:
#: The committed capture is the **small** case for this rail:
#: ``accrued 1.2K IMD · staged 45.00 IMD`` is 35 cells, and the rail needs
#: 40 screen columns for it. ``_fmt.fmt_imd`` renders 100.00..999.99 at six
#: columns and compacts only above 1000, so an ordinary launchpad -- one
#: whose 500 IMD minimum bridge has been met and whose hook is refilling --
#: prints ``accrued 620.00 IMD · staged 500.00 IMD``, 38 cells and 43
#: columns, which is also the widest that line can ever be.
#:
#: That three-column difference is the whole subject of the seam sweep in
#: ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``: four of the seams that look
#: cheapest against the capture stop qualifying against this payload,
#: because the rail becomes the binding panel and the rail is two plain
#: ``Static``s with no ``‹ widen`` between them. CLAUDE.md's standing rule
#: is to measure a data-dependent width against the state the data is
#: normally in; this is that state.
def _ordinary_burn_payload() -> dict:
    return _frozen_payload(burn_accrued=620.0, burn_staged=500.0)


@pytest.mark.parametrize(
    "payload", [None, "ordinary"], ids=["committed-capture", "ordinary-burn-line"]
)
@pytest.mark.parametrize("width", range(112, SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS))
async def test_nothing_below_the_pin_clips_without_saying_so(width, payload) -> None:
    """The seam's *disqualifying* property, asserted rather than asserted-in-
    prose.

    CLAUDE.md's rule is that below the pin the only panel allowed to clip is
    one that advertises the loss. Two of this body's five cannot: the rail's
    ``SurfCurveFlow`` and ``SurfBurnPipeline`` are plain ``Static``s. So a
    seam that hands the rail less than it needs while the marked coin table
    is already clean renders a truncated line with nothing on screen asking
    to be widened -- exactly what ``5:2`` was rejected for in the 2026-08-24
    sweep, and exactly what ``12fr:5fr`` did once MCAP took four columns off
    the table.

    The sibling sweep above only checks the marker below the pin, which is
    green in that state. This is the half that bites, and it needs **both**
    payloads to bite at every seam worth rejecting: mutate the seam in both
    stylesheets to ``12fr:5fr`` and the committed-capture half reddens at
    131..132; mutate it to ``23fr:10fr`` or ``16fr:7fr`` -- the seams that
    look cheapest by arithmetic -- and only the ordinary-burn-line half
    does. A single-payload version of this test greens one of those two
    mistakes.

    **The range starts at 112, not at the pin's neighbourhood**, because on
    the seam that is actually pinned nothing clips anywhere in 128..137 --
    the whole point of choosing it -- so a sweep confined to those widths
    executes its ``if`` body zero times and is a guard with no positive
    behind it. At 2:1 the rail falls under ``SurfBurnPipeline``'s need from
    117 down against the capture and from 126 down against an ordinary burn
    line, so the lower widths are where this test does its real work: they
    are widths at which the body *is* clipping, and the assertion is that
    ``SurfLaunchpadCoins`` is lit through all of them.
    """
    pl = _ordinary_burn_payload() if payload == "ordinary" else None
    async with _surf_app(pl).run_test(size=(width, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        clipped = _clipped_launchpad_lines(pilot.app, pilot.app.screen)
        if clipped:
            assert "‹ widen" in _title_text(pilot), (
                f"at {width} the l body clips {clipped} and no panel on "
                "screen advertises the loss"
            )


async def test_the_launchpad_binding_panel_is_the_coins_table() -> None:
    """Pinned by a test, not by a sentence in CLAUDE.md (curator's own
    ``test_the_analysis_binding_panel_is_the_operators_table`` precedent):
    ``SurfLaunchpadCoins`` -- its ``DataTable``'s nine fixed columns -- is
    the ``l`` body's binder, and it is the binder **by construction of the
    seam** rather than by luck.

    Re-checked against the ``2fr:1fr`` seam (2026-08-25) rather than
    assumed. The left column needs 92 screen columns and cannot give one
    back; the rail needs 40 against the committed capture and 43 against any
    ordinary one, and 2:1 hands it **46** at the pin. So one column below
    the pin the coin table is the only panel with anything to say, and it
    stays the only one under every payload this pipeline can produce --
    which is the property that chose this seam over ``13:6``, which collects
    135 with *zero* margin on a rail whose own binding panel cannot mark
    (``SurfBurnkeepers`` has a ``‹ widen`` but clears at 37, well under the
    rail's 40..43, so it is never the panel asking for columns). See
    ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``."""
    async with _surf_app().run_test(
        size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS - 1, 46)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        marked = {
            name
            for name, cls in _LAUNCHPAD_WIDGET_CLASSES.items()
            if "‹ widen" in _region_text(pilot.app, screen.query_one(cls))
        }
    assert marked == {"SurfLaunchpadCoins"}, marked


# -- the l body's own measured height (2026-08-25) ------------------------
#
# New with the five-panel body: three panels never came close to running out
# of rows, five do. Curator's ``f``/``y`` precedent -- the body is whole from
# ``SURF_LAUNCHPAD_FULL_LAYOUT_ROWS``, and below it the body scrolls and the
# title bar says ``‹ taller``. Note where each marker lives: ``‹ taller`` is
# screen-wide and rides row 0, the one row a short terminal can never push
# off; ``‹ widen`` rides the binding panel's own title.
#
# The sweep runs 24..45 -- seven rows below the measured 31 and fourteen
# above, never starting at it.


#: The coin table at the ten rows it is capped at.
#:
#: ``_sample_data``'s ``launchpad_coins`` has **two** rows, so in every other
#: test in this file ``SurfLaunchpadCoins`` is five rows tall (title, blank,
#: header, two coins) and the left column contributes 11 rows to the body.
#: The pin's own derivation is written against the ten-row cap -- 13 rows of
#: table plus ``SurfLaunchpadActivity``'s floor of 6 = **19** -- and none of
#: that was exercised anywhere: ``coins.size.height`` was 5 at every terminal
#: height in the committed suite, so the left column never scrolled and the
#: stated arithmetic could have been wrong by eight rows without a red test.
#:
#: Measured with this payload the left column really is 19 and the rail 20,
#: so the pin holds at 31 with **one row of margin** -- and, unlike the
#: capture, this payload actually exercises the left column's own overflow
#: branch (it scrolls from 29 down). It is the height sweep's counterpart to
#: :func:`_ordinary_burn_payload` on the width side, and it exists for the
#: same reason: the committed capture is the small case, and a pin measured
#: only against the small case is a pin nobody has tested.
#:
#: The tickers are rewritten per row so the ten are distinguishable on
#: screen; every other field is the fixture's own, so no row shape is
#: invented here (``test_every_list_row_in_the_fixture_matches_the_frozen_
#: row_shape`` still owns that claim for the fixture itself).
def _ten_coin_payload() -> dict:
    payload = _frozen_payload()
    rows = payload["launchpad_coins"]
    payload["launchpad_coins"] = [
        {**rows[i % len(rows)], "ticker": f"C{i:02d}"} for i in range(10)
    ]
    return payload


@pytest.mark.parametrize(
    "payload", [None, "ten-coins"], ids=["committed-capture", "ten-coin-table"]
)
@pytest.mark.parametrize("rows", range(24, 46))
async def test_the_launchpad_body_is_whole_from_its_pinned_height(
    rows, payload
) -> None:
    """Curator's ``f``/``y`` precedent, applied to surf's own second body.

    Started away from the pin, like every other sweep in this module. 150
    columns is comfortably past ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``, so
    nothing here is measuring a width.

    **Swept against a ten-coin table as well as the capture**, for the reason
    :func:`_ten_coin_payload` records: the pin's derivation is written about
    a 13-row table and a 19-row left column, and the committed capture makes
    that table 5 rows and that column 11. Under the capture alone the left
    column never scrolls at any height in this range, so half of what the pin
    is about was unexercised -- the rail could have been the binder by
    accident rather than by measurement.
    """
    pl = _ten_coin_payload() if payload == "ten-coins" else None
    async with _surf_app(pl).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
        if rows >= SURF_LAUNCHPAD_FULL_LAYOUT_ROWS:
            assert TALLER_HINT not in text, rows
        else:
            assert TALLER_HINT in text, rows


async def test_the_height_pin_is_measured_against_the_column_it_describes() -> None:
    """The pin's *derivation*, asserted -- not just its threshold.

    ``SURF_LAUNCHPAD_FULL_LAYOUT_ROWS``' docstring says the rail binds at 20
    rows and the left column asks for 19 with a full ten-coin table. The
    sweep above can only ever see the resulting threshold, so it stays green
    if those two numbers swap, drift, or were never true -- which is exactly
    the state the committed capture left them in, its two-row table making
    the left column 11.

    This is the row-wise counterpart of the width side's in-situ half-
    measurements. It is also the guard that would catch the coin table's cap
    changing: raise it past ten and the left column becomes the binder, at
    which point the pin moves and this test names the reason.

    **Measured below the pin, not at it**, and that is the whole trick.
    ``SurfLaunchpadActivity`` and ``SurfBurnkeepers`` are ``1fr``: on a
    terminal with rows to spare they grow, so at the pin itself both columns
    report the body's own height (20) and the 19 the docstring derives is
    nowhere on screen. At 28 rows the body is 17, both ``1fr`` children are
    on their ``min-height`` floors, and each column's ``virtual_size`` is its
    real content: 19 and 20. The floors are therefore part of what is being
    asserted here, not a separate subject.
    """
    async with _surf_app(_ten_coin_payload()).run_test(size=(150, 28)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        assert column.size.height < 19, (
            "28 rows no longer squeezes the body below its content, so both "
            "columns are reporting the terminal's height and this test is "
            "measuring nothing"
        )
        assert screen.query_one(SurfLaunchpadCoins).size.height == 13, (
            "the coin table is not the 13 rows the pin is derived from -- "
            "title, blank, header and the ten rows it is capped at"
        )
        assert column.virtual_size.height == 19, column.virtual_size.height
        assert rail.virtual_size.height == 20, rail.virtual_size.height
        assert rail.virtual_size.height > column.virtual_size.height, (
            "the rail is no longer the taller column, so it is no longer the "
            "panel this pin is measured against -- re-derive it"
        )
        # ...and the pin is that content plus the body's own chrome: the
        # title bar, the hero row and its top margin, this body's top margin
        # and the StatusBar. Derived from the laid-out screen rather than
        # retyped, so a hero that grew a row moves this rather than silently
        # disagreeing with the constant.
        chrome = pilot.app.size.height - column.size.height
        assert rail.virtual_size.height + chrome == SURF_LAUNCHPAD_FULL_LAYOUT_ROWS


async def test_the_row_marker_answers_for_the_body_that_is_showing() -> None:
    """``_rail_is_cut`` used to ask one fixed container and got it wrong.

    It read ``#surf-right-rail`` unconditionally. In ``MODE_LAUNCHPAD`` that
    container sits inside a ``display: none`` ``#middle-row``, is never laid
    out, and reports ``show_vertical_scrollbar is False`` at *every* terminal
    height -- so the one advertisement this screen has for a row gone off the
    bottom was dark across the whole of the ``l`` view while the launchpad
    rail was visibly scrolling.

    The two bodies have different thresholds (36 rows and 31), and both
    heights where they *disagree* and where they *agree* are exercised here,
    because only the pair together says what the marker is answering for:

    * **33 rows** -- short for the dashboard body, whole for the launchpad
      one. A marker still wired to the dashboard rail stays lit after ``l``
      and fails this half.
    * **28 rows** -- short for both. The marker must be lit in *both* modes,
      which is what stops the fix being "make it dark in MODE_LAUNCHPAD".
      That mutation passes the 33-row half on its own.
    """
    for rows, launchpad_marker in ((33, False), (28, True)):
        async with _surf_app().run_test(size=(150, rows)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            screen = pilot.app.screen
            assert TALLER_HINT in _screen_text(pilot.app), (
                f"{rows} rows is meant to be short for the dashboard body -- "
                "if it is not, this test's premise is gone and it can no "
                "longer fail"
            )
            assert screen.query_one("#surf-right-rail").display is True, (
                "the premise of the bug: the dashboard rail's own `display` "
                "stays True inside the hidden #middle-row"
            )
            await pilot.press("l")
            await pilot.pause()
            lit = TALLER_HINT in _screen_text(pilot.app)
            assert lit is launchpad_marker, (
                f"at {rows} rows the launchpad body's marker is "
                f"{'lit' if lit else 'dark'} and should be "
                f"{'lit' if launchpad_marker else 'dark'} -- the marker is "
                "not answering for the body that is showing"
            )


async def test_the_launchpad_left_column_scrolls_rather_than_clipping() -> None:
    """The regression test for the column's own arrival defect.

    ``#surf-launchpad-left`` shipped (2026-08-25) with ``height: 1fr`` and no
    ``overflow-y``. A ``Vertical`` defaults to ``overflow: hidden hidden``,
    so on a short terminal LAUNCHPAD ACTIVITY's rows were clipped straight
    out of the column -- no scrollbar, no ``‹ widen`` (the panel is not the
    one binding on width), and no ``‹ taller`` either, because
    ``_rail_is_cut`` was still asking the *dashboard* body's rail. Every row
    below the fold was unreachable and nothing on screen said a row existed.

    Both halves of the fix are asserted, because either alone is a different
    bug: the column must **scroll** (the affordance -- nothing is dropped,
    it is all still reachable) and the title bar must **say so** (the
    advertisement, on row 0, which no short terminal can push off).
    ``min-height`` on the ``1fr`` child is what turns "the column is short"
    into an overflow at all, so this is also that floor's proof.
    """
    async with _surf_app().run_test(size=(150, 20)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        assert column.virtual_size.height > column.size.height, (
            "the left column holds no more than it shows at 20 rows -- this "
            "test's premise is gone and it can no longer fail"
        )
        assert column.show_vertical_scrollbar, (
            "the left column holds more than it shows and is not scrolling: "
            "those rows are clipped, not merely off the fold"
        )
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]


async def test_the_launchpad_left_column_reserves_its_scrollbar_gutter() -> None:
    """``#surf-launchpad-rail``'s own gutter test, for the column that did
    not have one.

    ``#surf-launchpad-left`` arrived (2026-08-25) with ``height: 1fr`` and no
    ``overflow-y`` at all, and a ``Vertical`` defaults to ``overflow: hidden
    hidden`` -- so the activity feed was clipped straight out of the column
    below 22 rows with no scrollbar and no other trace. Giving it
    ``overflow-y: auto`` without ``scrollbar-gutter: stable`` would have
    traded that for the bug curator shipped instead: the scrollbar taking a
    column out of the coin table on short terminals only, so this layout's
    WIDTH pin becomes a function of its HEIGHT.

    Measured across the column's own overflow crossover, which is **21**
    rows with the committed capture (22 shows no scrollbar, 21 does). A pair
    of heights on the same side of it could not fail.

    **There is deliberately no ``styles.scrollbar_gutter`` assertion here.**
    Reading the declaration back is CSS compared against CSS: it cannot fail
    for a layout reason, and it cannot even see a one-copy deletion, because
    the app stylesheet and ``DEFAULT_CSS`` cover for each other. The
    width-equality assertions below are the ones that bite (measured with
    the property deleted: ``coins`` 100 columns at 46 rows and 99 at 20),
    and the two-copy agreement is
    ``test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet``'s
    job.
    """
    async def widths(height: int) -> dict:
        async with _surf_app().run_test(size=(150, height)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            screen = pilot.app.screen
            column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
            return {
                "coins": screen.query_one(SurfLaunchpadCoins).region.width,
                "activity": screen.query_one(SurfLaunchpadActivity).region.width,
                "overflowing": column.show_vertical_scrollbar,
            }

    roomy = await widths(46)
    cramped = await widths(20)

    assert not roomy["overflowing"], (
        "the left column already overflows at 46 rows -- both sample "
        "heights are on the same side of the crossover"
    )
    assert cramped["overflowing"], (
        "the left column does not overflow at 20 rows -- the condition this "
        "test exists to measure never occurs"
    )
    for panel in ("coins", "activity"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at 46 rows and "
            f"{cramped[panel]} at 20: the scrollbar took a column instead of "
            "using its reserved gutter, so this layout's width requirement "
            "now moves with its height"
        )


async def test_every_coin_column_header_reaches_the_screen_whole_and_distinct() -> None:
    """No two columns may render the same header, and none may be cut.

    ``DataTable`` truncates a header to its column width with **no ellipsis
    and no other trace** -- so a label longer than its column is lost in
    silence, and two labels that share a prefix longer than their columns
    become the *same word on screen*. Both happened here: ``SWAPS 24H`` and
    ``SWAPS ALL`` are 9 characters in 6-column cells, so the table rendered
    ``SWAPS   SWAPS`` at every width including the full layout, with 41 and
    977 underneath. A reader could not tell the day count from the all-time
    one, which defeats the column Task 11 added.

    The assertion is deliberately **not** "some expected substring is
    present" -- that shape passes while the screen shows nothing of the
    kind. It reads the labels off the table itself (never retyped here, so
    a renamed column cannot leave a stale literal behind), then requires
    three things of the *composited* header row at the pinned width:

    1. every label appears in it **verbatim** -- a truncated header does
       not, which is the truncation half;
    2. the labels are pairwise distinct -- which is the collision half, and
       the half a presence check cannot make;
    3. they appear **in declaration order and without overlapping** -- so
       "found" means "found in its own column", not matched inside a
       neighbour's text.
    """
    from textual.widgets import DataTable

    async with _surf_app().run_test(
        size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one("#surf-lpc-table", DataTable)
        labels = [str(column.label) for column in table.columns.values()]
        panel = _region_text(pilot.app, screen.query_one(SurfLaunchpadCoins))

    assert len(labels) == 9, labels
    assert len(set(labels)) == len(labels), (
        f"two coin columns declare the same header, so the screen shows one "
        f"word over two different numbers: {labels}"
    )

    header = next((line for line in panel.split("\n") if labels[0] in line), None)
    assert header is not None, f"no header row composited:\n{panel}"

    cursor = 0
    for label in labels:
        found = header.find(label, cursor)
        assert found >= 0, (
            f"the {label!r} header does not reach the screen whole at "
            f"{SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS} columns -- DataTable cut it "
            f"and said nothing:\n{header!r}"
        )
        cursor = found + len(label)


async def test_the_default_view_still_clears_at_the_app_wide_width() -> None:
    """Nothing in this change may move ``FULL_LAYOUT_COLUMNS``.

    ``_widen_sweep_payload()``, not the raw sample: the dashboard body
    (unlike the launchpad body above) stays on screen here, and the sample
    fixture's first announce post glues a URL to a raw tx hash -- a real,
    deliberate marker (``test_a_linked_post_advertises_widen_at_the_full_
    layout_width``) that is not the one this test is about.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert FULL_LAYOUT_COLUMNS == 143
    async with _surf_app(_widen_sweep_payload()).run_test(
        size=(FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        assert "‹ widen" not in _screen_text(pilot.app)


def test_the_initial_title_names_the_dashboard_the_menu_names():
    """The title bar is the only place the name is read *inside* the app.

    Derived from ``GAMES``, never a second literal: the menu row and the
    screen's own title must not be able to drift apart again. They did --
    the rename reached the menu, the README and CLAUDE.md and stopped at
    ``INITIAL_TITLE``, so pressing the menu key opened a screen still
    titled with the old name for the whole first fetch, and permanently on
    the degraded path (``_title_line`` is what replaces it, and a manager
    that raises never reaches it).

    **Case-insensitively** since 2026-08-12: the title bar shouts its
    board's name (``SURFBOARD``, like FWA's ``FWA``) where the menu prints
    it as a word. Only the case is allowed to differ -- the letters are
    still the menu's, derived from ``GAMES`` and never re-typed.
    """
    from maxpane_dashboard.screens.game_select import GAMES

    name = next(row[2] for row in GAMES if row[1] == "surf")
    assert name.lower() in INITIAL_TITLE.lower(), (
        f"the menu calls this dashboard {name!r}; its own title bar says "
        f"{INITIAL_TITLE!r}"
    )


# -- mount ---------------------------------------------------------------


async def test_screen_mounts_all_six_widgets():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()

        for cls in _WIDGET_CLASSES.values():
            screen.query_one(cls)
        # Slot grid: the hero owns the top row alone; the middle row is the
        # feed beside a rail of SIGNALS over DEV ACTIVITY; the bottom row is
        # the market beside the NFT panel.
        assert len(screen.query_one("#hero-row").children) == 1
        assert len(screen.query_one("#middle-row").children) == 2
        assert len(screen.query_one("#surf-right-rail").children) == 2
        assert len(screen.query_one("#bottom-row").children) == 2
        # Nothing is hidden -- that is the whole point of the three-row grid.
        for cls in _WIDGET_CLASSES.values():
            assert screen.query_one(cls).display is True, f"{cls.__name__} is hidden"
        # The launchpad trio (2026-08-23) is the one deliberate exception:
        # composed once, mounted, and hidden until `l` shows it.
        for cls in _LAUNCHPAD_WIDGET_CLASSES.values():
            screen.query_one(cls)  # mounted...
        assert screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is False, (
            "the launchpad body is visible before l is pressed"
        )
        # WP5.3 wires ``_title_line`` into ``_do_refresh``, and RefreshGuard
        # fires that refresh on screen resume, so by the time ``pilot.pause()``
        # returns the placeholder ``INITIAL_TITLE`` has already been replaced
        # by the fetched payload's title -- this is no longer the pre-refresh
        # state the old assertion checked. Asserted against **composited
        # output**, not the widget's content string (house rule): a title
        # that never reaches the compositor would still pass a ``_plain()``
        # check while being invisible to a real user.
        assert (
            f"SURFBOARD · IMD $0.71 · parity -2.7% · as of {_AS_OF_HHMM}"
            in _screen_text(app)
        )


# -- title line (pure) ---------------------------------------------------

from maxpane_dashboard.screens import surf as surf_mod


def test_title_line_composes_the_mandated_format():
    line = surf_mod._title_line(_frozen_payload())
    # PRD §4: SURFBOARD · IMD $x.xx · parity ±x.x% · as of HH:MM + flags.
    # `feed #N (age)` was the fourth field until the final fix wave (I4); it
    # is rendered verbatim by the ANNOUNCE panel's own title one row down
    # (`ANNOUNCE · #14 · last 23h ago`), and its seventeen columns bought the
    # freshness marker this screen had nowhere at all.
    head = f"SURFBOARD · IMD $0.71 · parity -2.7% · as of {_AS_OF_HHMM}"
    assert line.startswith(head)
    # Nothing follows the healthy figures: no flags in this sample, and the
    # version tail went in 2026-08-12 (the StatusBar already carries it).
    assert line == head
    assert "⚠" not in line                 # nothing degraded in the sample


def test_title_line_all_none_shows_emdashes_never_zeros():
    line = surf_mod._title_line(_all_none_payload())
    assert "IMD —" in line
    assert "parity —" in line
    # The marker never disappears: "we have never read anything" is a state
    # this row must be able to say, not one it may go quiet about.
    assert "as of —" in line
    assert "$0.00" not in line and "0.0%" not in line   # None is never 0-coerced


def test_title_line_renders_degraded_and_lp_owner_warning():
    line = surf_mod._title_line(
        _frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    assert "· ⚠ logs, market" in line
    assert "⚠ LP owner changed" in line    # position #1167726 left frenpet.eth


# -- the title bar's own copy (2026-08-12) -------------------------------
#
# Three edits to one row: the board is named in full, the version tail is
# gone (the StatusBar three rows down already carries it), and the degraded
# list wears this codebase's warning glyph instead of spelling the word.
# All three buy columns back on the one row of this screen that cannot
# ellipsise -- everything past its first line reaches no pixel at all.


def test_the_title_line_shouts_the_board_and_leaves_the_version_alone():
    """``SURFBOARD``, and nothing that looks like a version anywhere on it."""
    import re

    line = surf_mod._title_line(_frozen_payload())
    assert line.startswith("SURFBOARD · IMD ")
    assert f"v{__version__}" not in line, (
        "the version is duplicated: the StatusBar already carries it"
    )
    assert not re.search(r"v\d+\.\d+", line), line


async def test_the_status_bar_still_carries_the_version_to_a_pixel():
    """The other half of dropping the title's version tail, on the screen.

    The argument for taking ``· v0.6.0`` off the title bar was "the StatusBar
    three rows down already renders it" -- and *nothing asserted that*. The
    test above only pins the version's absence from the title line, so
    deleting the label from ``widgets/status_bar.py`` left the whole suite
    green with the version reaching no pixel anywhere in the TUI (the only
    other reference, ``tests/test_cli_version.py``, is ``--version`` on
    stdout, a different surface entirely).

    Composited, both halves at once: present on the screen, absent from the
    row that gave it up. A version rendered into a widget nobody composites
    would satisfy the first assertion of a content-string test and none of
    a user's.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 46) as (app, _screen, _p):
        text = _screen_text(app)
        assert f"maxpane v{__version__}" in text, (
            "the version reaches no pixel on this screen -- the title bar "
            "gave its tail up to the StatusBar and the StatusBar dropped it"
        )
        assert f"v{__version__}" not in text.split("\n")[0], (
            "the version came back to the title bar, which is the row that "
            "cannot ellipsise"
        )


def test_the_initial_title_is_the_confirmed_wording():
    """Spelled out, not derived: ``SURF · Surfboard`` said the name twice.

    A test asserting ``"SURFBOARD" in INITIAL_TITLE`` would pass on the old
    three-segment wording too, so the whole string is the assertion.
    """
    assert INITIAL_TITLE == "SURFBOARD · Ethereum Mainnet"


def test_degraded_sources_ride_the_house_warning_glyph_not_the_word():
    """``⚠ activity`` -- the glyph ``⚠ feed unavailable`` already uses.

    The source names themselves are untouched: they are the manager's own
    ``SOURCES`` vocabulary, and the eight are spelled out here against a
    ``sorted(SOURCES)`` derived from the manager so a rename reddens this
    rather than quietly re-wording the most prominent row on the screen.

    ``"pad"`` (not ``"launchpad"``) was the seventh: Task 6 fix round 1
    (controller finding 2) renders it terse because the worst-case title bar
    (see ``WORST_CASE_TITLE_COLUMNS`` below) is width-bound -- widening the
    layout to fit the long form was rejected in favour of shortening the
    label, this repo's standing rule.

    ``"p4"`` (not ``"pool4"``) is the **eighth**, spelled short for exactly
    that reason and measured rather than assumed: those four columns (``,
    p4``) took the worst-case row from 139 to 143, which is
    ``SURF_FULL_LAYOUT_COLUMNS`` to the column. The long form would have taken
    it to 146 and the tail of this row does not clip, it *disappears*.
    """
    from maxpane_dashboard.data.surf_manager import SOURCES

    assert surf_mod._fmt_degraded(["activity"]) == " · ⚠ activity"
    assert surf_mod._fmt_degraded(sorted(SOURCES)) == (
        " · ⚠ activity, chain, channel, logs, market, nft, p4, pad"
    )
    assert sorted(SOURCES) == [
        "activity", "chain", "channel", "logs", "market", "nft", "p4", "pad"
    ], "a source group was renamed -- the title bar's vocabulary follows it"
    assert "degraded" not in surf_mod._fmt_degraded(sorted(SOURCES))


def test_fmt_age_tiers():
    assert surf_mod._fmt_age(None) == "—"
    assert surf_mod._fmt_age(42.0) == "42s"
    assert surf_mod._fmt_age(84_769.0) == "23h"     # the sample's real age
    assert surf_mod._fmt_age(5_400.0) == "90m"      # 90 min is the m/h boundary
    assert surf_mod._fmt_age(3 * 86_400.0) == "3d"  # 36 h is the h/d boundary
    assert surf_mod._fmt_age(-5.0) == "—"           # a negative age is nonsense


# -- degraded formatting (pure) -- review round 1 -----------------------
#
# _fmt_degraded's job is to make anything short of "nothing is degraded"
# ((None)/[]) visibly wrong. A bare ``except TypeError: return ""`` used to
# turn a malformed ``degraded`` value into the *healthy* line -- the exact
# failure this project exists to prevent, on the most prominent line of the
# screen.


def test_fmt_degraded_healthy_inputs_render_empty():
    assert surf_mod._fmt_degraded(None) == ""
    assert surf_mod._fmt_degraded([]) == ""


def test_fmt_degraded_bare_string_is_one_group_not_characters():
    # A string is iterable character-by-character; treat it as a single
    # group name instead of exploding "logs" into "l, o, g, s".
    assert surf_mod._fmt_degraded("logs") == " · ⚠ logs"


def test_fmt_degraded_list_with_a_non_string_element_still_renders():
    assert surf_mod._fmt_degraded(["logs", 42]) == " · ⚠ logs, 42"


def test_fmt_degraded_unexpected_shapes_never_render_the_healthy_line():
    # None of these mean "nothing is degraded" -- an int cannot be iterated
    # and a dict is not a list of names -- so none may collapse to "", which
    # the title line renders identically to a genuinely healthy state.
    assert surf_mod._fmt_degraded(42) != ""
    assert surf_mod._fmt_degraded({"logs": True}) != ""
    assert "⚠" in surf_mod._fmt_degraded(42)
    assert "⚠" in surf_mod._fmt_degraded({"logs": True})


def test_title_line_with_a_malformed_degraded_value_never_reads_healthy():
    healthy = surf_mod._title_line(_frozen_payload(degraded=[]))
    assert "⚠" not in healthy
    for bad in (42, {"logs": True}, ["logs", 42]):
        line = surf_mod._title_line(_frozen_payload(degraded=bad))
        assert line != healthy
        assert "⚠" in line


# -- refresh dispatch ----------------------------------------------------


def _record_dispatches(screen) -> dict[str, list[dict]]:
    """Wrap every widget's ``update_data`` so we can see what it was handed.

    ``_ALL_WIDGET_CLASSES``, not ``_WIDGET_CLASSES``: this records dispatch
    calls, which the launchpad trio receives every refresh whether or not
    ``l`` is showing it (see ``_do_refresh``) -- unlike the "nothing is
    hidden" mount test, visibility is not what this helper is checking.
    """
    calls: dict[str, list[dict]] = {name: [] for name in _ALL_WIDGET_CLASSES}

    def _wrap(name: str, original):
        def recorder(**kwargs):
            calls[name].append(kwargs)
            return original(**kwargs)

        return recorder

    for name, cls in _ALL_WIDGET_CLASSES.items():
        widget = screen.query_one(cls)
        widget.update_data = _wrap(name, widget.update_data)

    return calls


async def test_screen_dispatches_every_data_key():
    """Every ``SURF_KEYS`` group reaches the widget that owns it.

    ``signature`` is now ``{SURF_KEYS name: update_data kwarg name}``, not a
    flat tuple of kwarg names (see the module comment on
    ``SURF_WIDGET_SIGNATURES``): the launchpad trio's kwargs are not spelled
    like their SURF_KEYS names, so the two questions -- "what did the
    dispatch call actually pass" and "what contract key does that answer
    for" -- need their own comparisons instead of one set equality.
    """
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1

        payload = _frozen_payload()
        dispatched: set[str] = set()
        checked_values = 0
        for name, signature in SURF_WIDGET_SIGNATURES.items():
            assert calls[name], f"{name}.update_data was never called"
            kwargs = calls[name][-1]
            expected_kwargs = set(signature.values())
            assert set(kwargs) == expected_kwargs, (
                f"{name} got {sorted(set(kwargs) ^ expected_kwargs)} "
                "off-contract"
            )
            # ...and each kwarg carries the value of the key it answers for.
            #
            # THE NAME CHECK ABOVE IS NOT ENOUGH, and a mutation proved it:
            # rewriting one dispatch line to
            # `pool4_discovery_source_tx=data.get("pool4_discovery_detail")`
            # -- the right kwarg, the wrong payload key -- left this test
            # green. That is the copy-paste error a block of forty-seven
            # near-identical `key=data.get("key")` lines actually invites,
            # and it puts one key's value under another key's name on screen
            # with nothing anywhere disagreeing.
            for contract_key, kwarg in signature.items():
                assert kwargs[kwarg] == payload[contract_key], (
                    f"{name}.{kwarg} was handed "
                    f"{kwargs[kwarg]!r}, which is not the payload's "
                    f"{contract_key!r} ({payload[contract_key]!r}) -- the "
                    "dispatch is reading the wrong key"
                )
                if payload[contract_key] is not None:
                    checked_values += 1
            dispatched |= set(signature)   # SURF_KEYS names, not kwarg names

        # The value check can only bite where the fixture distinguishes two
        # keys, so a pair that are both `None` in `_sample_data` would swap
        # invisibly. Counting the comparisons that had something to compare
        # keeps that a known limit rather than a silent one, and stops the
        # loop above going vacuous if the fixture ever thinned out.
        #
        # THE PAIRS THAT ARE CURRENTLY BLIND, found by mutation rather than
        # by reading, so the limit is measured rather than asserted:
        #
        #   * `pool4_discovery_source` / `pool4_discovery_source_tx`
        #   * `pool4_distributor_staking_bps` / `_nodes_bps`
        #
        # All four are `None` on the day-one Sepolia payload this test runs
        # against, for the right reason -- there is no adoption to cite and
        # no Distributor on that deployment -- so swapping either pair leaves
        # this green. Filling them to close the gap would mean writing a
        # Sepolia fixture that asserts a mainnet shape, which is the trade
        # this file refuses everywhere else.
        #
        # The two `*_bps` keys stay blind even on mainnet: the chain really
        # does return 3000 for both, so no honest fixture distinguishes them.
        # That one is a property of the deployment, not of the test.
        assert checked_values >= 92, (
            f"only {checked_values} dispatched values were non-None -- the "
            "fixture no longer distinguishes enough keys for the value "
            "check to mean much"
        )

        # Nothing in the contract goes unrendered by accident: it is either a
        # widget kwarg, a meta key the screen itself consumes, or one of the
        # six keys explicitly parked in `_KEYS_WITHOUT_A_RENDERER` as having
        # been orphaned by the hero rebuild and awaiting removal from
        # SURF_KEYS by that module's owner.
        unconsumed = (
            set(SURF_KEYS)
            - dispatched
            - META_KEYS
            - _KEYS_WITHOUT_A_RENDERER
            - _KEYS_PENDING_CONSUMERS
        )
        assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"


async def test_refresh_renders_title_and_all_panels():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert f"SURFBOARD · IMD $0.71 · parity -2.7% · as of {_AS_OF_HHMM}" in title

        text = _screen_text(app)
        # Panel titles (the WP3 widget-interface strings).
        assert "SIGNALS" in text
        assert "ANNOUNCE FEED" in text
        assert "MARKET" in text
        assert "IDENTITY.MD" in text
        # The hero's own titles reach the compositor -- POOL/LP/BURN/SUPPLY,
        # rebuilt 2026-08-23 for the v4 migration (widgets/surf/hero.py).
        assert "POOL" in text
        assert "IMD SUPPLY" in text
        # The observed burn reached the hero, and PRD §1's all-time ledger is
        # nowhere on screen — the manager cannot produce it. At 150 columns
        # the hero owns the full row (unlike the pre-2026-08-09 layout this
        # comment used to measure, which shared it 3fr:2fr with the signals
        # panel): swept, a hero box has content columns comfortably past
        # ``COMPACT_WIDTH`` (22) here, so this renders the *compact* copy,
        # ``burned 15,745 observed`` -- the quantity whole either way. This
        # used to assert the prefix ``"burned 15,7"`` because the full copy
        # was ellipsised here to ``burned 15,74…`` — a number cut mid-digits,
        # with nothing marking the cut. That was final-review I-2; the shed
        # field (at narrower widths) replaced it.
        assert "burned 15,745 observed" in text
        assert "burned 15,74…" not in text
        assert "58,848" not in text
        # The clipping trap: every detector row that keeps its own line
        # reaches the compositor. SurfSignals now carries ten detectors
        # with quiet-collapse (Task 9): this fixture's lp/gate/deploy/burn
        # and thread are all `ok` and fold into one dim "5 quiet" line (the labels
        # themselves are therefore *not* on screen for those four -- folding
        # is what quiet-collapse means), so the quiet line is what a CSS
        # regression would eat first, the role BURN's own row used to play
        # when there were only six and nothing folded.
        for label in ("NEW POST", "BRIDGE STAGE", "DECOY POOL",
                      "BURN READY", "HOT COIN"):
            assert label in text, f"detector row {label!r} clipped or missing"
        assert "5 quiet" in text
        # The floor is explicitly unavailable, never faked (PRD §4).
        assert "no keyless source" in text


async def test_screen_survives_manager_exception():
    """Belt and braces: the screen stands; only the StatusBar is marked.

    This is **not** the specified outage path — WP4's manager never raises,
    it returns all-``None`` (see ``test_screen_survives_all_none_payload``,
    which is the real-outage test).  A raising manager models a mis-wired or
    non-manager object, i.e. a programming error, and this test exists so
    that error degrades instead of killing the app.
    """
    manager = _FakeManager(raises=True)
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        status = screen.query_one(StatusBar).query_one("#status-left")
        rendered = _plain(status)
        # Not "updated 999s ago" any more: surf opted into the status bar's
        # key-hints label (2026-08-23, ``SurfScreen.KEY_HINTS``) so ``l
        # launchpad`` could be named there, and ``StatusBar._ordinary_status``
        # trades the freshness segment for the hints segment when a screen
        # sets one -- the same tradeoff curator already made for its own
        # hints. The error count is unaffected; it is appended either way.
        assert "l launchpad" in rendered
        assert "updated" not in rendered
        assert "3 errors" in rendered   # manager's _error_count is surfaced

        # The title bar was not half-overwritten with a broken frame -- and
        # it still names the dashboard the menu names. This is the *only*
        # path on which ``INITIAL_TITLE`` is what the user reads for good
        # (``_title_line`` never runs), so the name has to be right here.
        # Composited, not the content string: the title bar is centred and
        # one row high, and a name that never reaches a pixel is not a name.
        text = _screen_text(app)
        assert INITIAL_TITLE in text.split("\n")[0]
        assert "Mission Control" not in text
        # Every widget is still mounted and rendering.
        assert "SIGNALS" in text
        assert "IDENTITY.MD" in text


async def test_screen_survives_all_none_payload():
    """A full outage renders explicit unavailable states, never zeros."""
    manager = _FakeManager(payload=_all_none_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert "SURFBOARD · IMD — · parity — · as of —" in title
        text = _screen_text(app)
        assert "$0.00" not in text     # a None price is never a zero price
        assert "no keyless source" in text


async def test_degraded_sources_reach_the_title_bar():
    manager = _FakeManager(
        payload=_frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        text = _screen_text(app)
        assert "⚠ logs, market" in text
        assert "LP owner changed" in text


# -- everything on screen at once ---------------------------------------
#
# The `c` swap is gone with the slot it swapped. These are what replaced its
# three tests: the panels it used to alternate between are now both permanently
# composited, side by side with the rail, and no key can take either away.


async def test_the_feed_and_the_activity_panel_are_both_on_screen_at_once():
    """The instruction, stated as an assertion: nothing is hidden.

    Composited, not `display`: a panel mounted at zero height satisfies a
    visibility flag while showing the user nothing.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        for title in ("ANNOUNCE FEED", "SIGNALS", "DEV ACTIVITY",
                      "IMD MARKET", "IDENTITY.MD", "POOL"):
            assert title in text, f"{title} is not on screen"


async def test_no_key_can_hide_a_panel():
    """`c` was the only key that could, and it is gone.

    Pressing it now must be inert -- not "swap something else", not crash.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        before = _screen_text(app)

        await pilot.press("c")
        await pilot.pause()

        assert _screen_text(app) == before, "`c` still changes the screen"
        assert "DEV ACTIVITY" in before and "ANNOUNCE FEED" in before


async def test_the_status_bar_never_advertises_a_view():
    """No slot has two views any more, so `view: …` would name nothing.

    Asserted on the composited status bar, because the string is built inside
    ``StatusBar._update_right`` -- a screen that kept calling
    ``set_active_view`` would put a stale word on a bar this dashboard shares
    with nine others.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "view:" not in text
        assert "surf" in text.split("\n")[-1]   # the bar is otherwise intact


async def test_the_activity_panel_defends_against_address_poisoning():
    """The anti-poisoning form survives all the way to the compositor.

    Two live shapes from frenpet.eth's history are in the payload: an
    unlabelled but genuine LP-fee destination, and a 1-gwei lookalike that
    collides with a real fee recipient on first-6/last-4. WP3 renders unknown
    counterparties as ``0x`` + first 8 + ``…`` + last 6 and drops the
    (transfer, zero value, unknown) triple outright -- this asserts both
    through the real screen rather than trusting the widget's own unit test,
    because a short-form *fixture* would make either defence a silent no-op.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "DEV ACTIVITY" in text
        # The genuine unknown renders in the wide, poisoning-resistant window…
        assert "0x61CC704c…73f14E" in text
        # …and never in the classic short form the lookalike collides with.
        assert "0x61CC…f14E" not in text
        # The dust row reaches no pixel at all -- not the address, not the tail.
        assert "F3083828" not in text
        assert "f60Ee6" not in text


# -- the three-row layout -----------------------------------------------
#
# The hero spans the full width on a row of its own; the middle row is the
# announce feed beside a rail stacking SIGNALS over DEV ACTIVITY; the bottom
# row is IMD MARKET beside IDENTITY.MD, on the same column seam as the row
# above it. Every assertion below is geometric or composited -- the
# arrangement is what the user asked for, so "the widget is mounted" is not
# enough: it has to land where they put it.

#: The rail id, spelled once. Scoped to ``SurfScreen`` in both stylesheets.
_RAIL = "#surf-right-rail"


class _screen_at:
    """``async with _screen_at(w, h) as (app, screen, pilot):`` -- refreshed."""

    def __init__(self, width: int = 150, height: int = 46, payload=None) -> None:
        self._size = (width, height)
        self._payload = payload
        self._ctx = None

    async def __aenter__(self):
        manager = _FakeManager(
            payload=self._payload if self._payload is not None
            else _widen_sweep_payload()
        )
        self._screen = SurfScreen(manager, poll_interval=30, name="surf")
        self._app = _ThemedHarness(self._screen)
        self._ctx = self._app.run_test(size=self._size)
        pilot = await self._ctx.__aenter__()
        await pilot.pause()
        await self._screen._do_refresh()
        await pilot.pause()
        return self._app, self._screen, pilot

    async def __aexit__(self, *exc):
        return await self._ctx.__aexit__(*exc)


async def test_the_hero_owns_a_full_width_row_of_its_own():
    """The hero is the whole top row -- nothing shares it."""
    async with _screen_at(150, 46) as (app, screen, _pilot):
        hero_row = screen.query_one("#hero-row")
        hero = screen.query_one(SurfHero)

        assert len(hero_row.children) == 1, (
            "something else is still sharing the hero row: "
            f"{[type(c).__name__ for c in hero_row.children]}"
        )
        assert hero.region.width == hero_row.region.width == 150
        # All four boxes are laid out inside that full width, in order.
        xs = [box.region.x for box in hero.children]
        assert len(xs) == 4 and xs == sorted(xs)
        assert xs[-1] + hero.children[-1].region.width <= 150


async def test_the_right_rail_stacks_the_signals_above_the_dev_activity():
    """SIGNALS sits on top of DEV ACTIVITY, both in the middle row's rail."""
    async with _screen_at(150, 46) as (app, screen, _pilot):
        rail = screen.query_one(_RAIL)
        signals = screen.query_one(SurfSignals)
        activity = screen.query_one(SurfDevActivity)
        feed = screen.query_one(SurfFeed)

        assert [type(c).__name__ for c in rail.children] == [
            "SurfSignals", "SurfDevActivity",
        ]
        # Stacked, not side by side: same column, signals strictly above.
        assert signals.region.x == activity.region.x == rail.region.x
        assert signals.region.y + signals.region.height <= activity.region.y
        # ...and the whole rail is to the right of the feed, in one row.
        assert feed.region.x + feed.region.width <= rail.region.x
        assert feed.region.y == rail.region.y

        # Composited, not just geometric: both titles reach a pixel, in order.
        text = _screen_text(app)
        assert text.index("SIGNALS") < text.index("DEV ACTIVITY")


async def test_the_bottom_row_puts_the_market_left_of_the_nft_panel():
    """The third row, and it shares the middle row's column seam.

    The seam is the point: two rows split 3:2 read as one grid, and a market
    panel that started one column off from the feed above it would read as a
    mistake even though every panel was present.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        row = screen.query_one("#bottom-row")
        market = screen.query_one(SurfMarket)
        nft = screen.query_one(SurfNft)
        feed = screen.query_one(SurfFeed)
        rail = screen.query_one(_RAIL)

        assert [type(c).__name__ for c in row.children] == ["SurfMarket", "SurfNft"]
        # Side by side, market first, in one row, below the middle row.
        assert market.region.y == nft.region.y
        assert market.region.x + market.region.width <= nft.region.x
        assert row.region.y >= rail.region.y + rail.region.height
        # The seam: the market/NFT boundary is the feed/rail boundary.
        assert market.region.width == feed.region.width
        assert nft.region.x == rail.region.x

        text = _screen_text(app)
        assert text.index("IMD MARKET") < text.index("IDENTITY.MD")
        # ...and both are below the rail's two panels.
        assert text.index("DEV ACTIVITY") < text.index("IMD MARKET")


async def test_the_hero_row_is_no_taller_than_the_hero():
    """The dead space above the feed: the row used to reserve 10 rows for 7.

    Sized to its content instead. Composited, because the failure is *blank
    rows* -- a region height alone would not show them.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        hero_row = screen.query_one("#hero-row")
        hero = screen.query_one(SurfHero)
        assert hero_row.region.height == hero.region.height

        lines = _screen_text(app).split("\n")
        top, bottom = hero_row.region.y, hero_row.region.y + hero_row.region.height
        assert lines[bottom - 1].strip(), (
            "the hero row's last line is blank -- it is still taller than its content"
        )
        # The row directly under the hero belongs to the middle row's margin,
        # and there is exactly one of them.
        assert not lines[bottom].strip()
        assert lines[bottom + 1].strip(), "more than one blank row under the hero"
        assert top == 2


async def test_the_bottom_row_sizes_to_the_nft_panel_and_strands_no_rows():
    """The other half of the complaint: ~a fifth of the screen was empty.

    The NFT panel is the last thing on screen above the status bar, so any row
    the bottom row reserves beyond the panel's own content is dead. Asserted
    against composited output: the last non-blank row before the status bar
    must be the panel's last line, not eight rows above it.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        bottom = screen.query_one("#bottom-row")
        nft = screen.query_one(SurfNft)
        assert bottom.region.height == nft.region.height

        lines = _screen_text(app).split("\n")
        status_row = len(lines) - 1
        assert "q quit" in lines[status_row]
        last_content = max(i for i in range(status_row) if lines[i].strip())
        # One margin row between the panel and the status bar, no more.
        assert status_row - last_content <= 2, (
            f"{status_row - last_content - 1} dead rows above the status bar"
        )
        assert "0.200 ETH" in lines[last_content], (
            "the last NFT sale is not the last thing on screen"
        )


async def test_a_taller_terminal_hands_every_new_row_to_the_feed():
    """Slack goes to the feed, never back into the fixed rows.

    Fourteen more terminal rows must arrive as fourteen more feed rows -- if
    the hero or the NFT panel takes a share of them the dead space is back.
    """
    async with _screen_at(150, 46) as (_app, screen, _pilot):
        short = {
            "feed": screen.query_one(SurfFeed).region.height,
            "hero": screen.query_one(SurfHero).region.height,
            "nft": screen.query_one(SurfNft).region.height,
        }
    async with _screen_at(150, 60) as (_app, screen, _pilot):
        tall = {
            "feed": screen.query_one(SurfFeed).region.height,
            "hero": screen.query_one(SurfHero).region.height,
            "nft": screen.query_one(SurfNft).region.height,
        }

    assert tall["feed"] - short["feed"] == 14, (
        f"the feed absorbed {tall['feed'] - short['feed']} of 14 new rows"
    )
    assert tall["hero"] == short["hero"]
    assert tall["nft"] == short["nft"]


async def test_a_terminal_too_short_for_nine_detectors_says_so():
    """Rows are the columns problem again: the loss must be advertised.

    Renamed from "...six_detectors..." (Task 9 grew the rail to nine, with
    quiet-collapse folding ``ok`` rows into one dim summary line); the
    behaviour this asserts is unchanged.

    Sizing every row to its content is what removed the dead space, and the
    price is that the rail is only as tall as the middle row -- where the old
    layout gave the signals a fixed ten-row band that survived down to a
    ~16-row terminal. ``overflow-y: auto`` on the rail is the row-wise
    ``‹ widen``: nothing is drawn while everything fits, and the scrollbar
    appears exactly when something is missing.

    **The sentinel changed, the mechanism did not (Task 8/12 addendum).**
    ``BURN`` used to be this test's sentinel for "the rail scrolled away",
    because it was the rail's own last detector. It cannot be any more: the
    2026-08-23 hero rebuild put a card titled ``BURN`` on the hero row too,
    and the hero row never scrolls -- so ``"BURN" not in text`` could never
    go true again regardless of what the rail lost. ``HOT COIN`` is the
    rail-only replacement: it is the last of the ten detector labels
    (PRD §3 order) and, with this fixture's lp/gate/deploy/burn/thread all
    quiet-collapsed into "5 quiet" already, the last row the rail draws before
    that summary line -- swept at the same two heights the old test used
    (46, 28), it is present at 46 and gone at 28, same as ``BURN`` used to
    be. Neither detector label was renamed: CLAUDE.md holds them as an
    interface two app-level acceptance tests also assert, and lengthening
    one would cost the rail's unshrinkable head width it does not have to
    spend.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        text = _screen_text(app)
        for label in ("NEW POST", "BRIDGE STAGE", "DECOY POOL",
                      "BURN READY", "HOT COIN"):
            assert label in text, f"{label} is missing at a normal height"
        assert "5 quiet" in text, (
            "lp/gate/deploy/burn/thread are all `ok` in this fixture and "
            "should fold into one summary line"
        )
        assert screen.query_one(_RAIL).show_vertical_scrollbar is False, (
            "the rail scrolls even when everything fits -- a marker that is "
            "always on says nothing"
        )

    async with _screen_at(150, 28) as (app, screen, _pilot):
        assert "HOT COIN" not in _screen_text(app), (
            "28 rows fits every detector after all -- re-measure"
        )
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True, (
            "a detector row was dropped with nothing on screen to say so"
        )


#: What the market panel exists to show, as composited fragments.  Matched
#: inside the panel's own rectangle and nowhere else: "parity" is also in the
#: title bar and "supply" in the hero, so a whole-screen match would keep
#: reading the market as present long after it had gone.
_MARKET_FIELDS = ("$0.7074", "vol 24h", "parity", "price ", "supply")

#: The panel now carries nine detectors, but this fixture's fixed *rendered*
#: row count is still six: post/bridge are `fired` and decoy/burnready/hot
#: are unknown (this fixture never sets them), so all five keep their own
#: line, while lp/gate/deploy/burn and thread are all `ok` and fold into one
#: dim "N quiet" line (widgets/surf/signals.py's Quiet-collapse section). The
#: quiet line renders last, after every detector slot, and so is always the
#: first thing scrolled off -- the role BURN's own row used to play.
_DETECTORS = ("NEW POST", "BRIDGE STAGE", "DECOY POOL", "BURN READY",
              "HOT COIN", "5 quiet")

#: The activity rows the sweep payload produces, once the dust row is dropped.
#: Composited fragments, unique to that panel.
_ACTIVITY_ROWS = ("0x61CC704c…73f14E", "NFPM", "OFT endpoint")

#: The height at and above which the whole rail fits: ``SurfSignals`` is 8 rows
#: (title, spacer, six body rows -- see ``_DETECTORS``) plus the one-row
#: margin that separates it from the activity panel, and ``SurfDevActivity``
#: is floored at
#: ``ACTIVITY_MIN_HEIGHT``, so the rail's content is a constant 16 and the
#: other rows of the screen cost a fixed 21. Measured, not derived -- the
#: arithmetic is here to explain the number, the sweep below is what pins it.
#:
#: **36 -> 37 on 2026-08-10**, the one row the rail separator costs. The
#: ``‹ taller`` marker therefore lights at 36 where it used to light at 35,
#: and the first genuinely-lost activity row moved 33 -> 34 with it: the
#: marker still leads the loss by exactly two rows, which is the property
#: that matters and which ``test_the_marker_lights_before_the_first_line_is_
#: actually_lost`` pins at both ends.
#:
#: **37 -> 38 later the same day**, and only the market paid: a second blank
#: row went in under ``IMD MARKET``'s title, while ``IDENTITY.MD`` broke even
#: on its own new blank by dropping ``_MAX_SALES`` 4 -> 3. The bottom row is
#: as tall as its taller child, so a row added to the shorter panel would
#: have cost nothing -- it was the market's, and the market was the taller
#: one. Re-measured, not adjusted: the marker is dark from 38 and lit at 37.
#:
#: **Unmoved on 2026-08-24**, through two changes that each looked like they
#: should move it, and the reasons are worth more than the number.
#:
#: NEW REPLY is a *tenth* detector, and it cost the rail nothing: it is ``ok``
#: on a quiet channel, and an ``ok`` row folds into the ``· N quiet`` line
#: rather than taking one -- which is the whole point of quiet-collapse. Only
#: the count changed, 4 -> 5. Measured first against a fixture that left the
#: new keys *unset*, this read 39, because an unset key is the ``None``
#: state, unknown rows never fold, and the row took a line it will never take
#: in production. That is CLAUDE.md's "measure a data-dependent number against
#: the state the data is normally in", on rows instead of columns: set the
#: fixture to the state the channel is actually in and the row costs nothing.
#:
#: ``IMD MARKET`` lost a blank row in the same change and the screen did not
#: notice either -- which inverts the paragraph above. Measured here,
#: ``SurfMarket`` is **7** rows and ``SurfNft`` is **9**: IDENTITY.MD is the
#: taller child of the bottom row now, and has been since it grew back past
#: the market. A row taken off the market buys this screen nothing until the
#: two are level again.
FIRST_WHOLE_HEIGHT = 38


def _visible_panel(app, widget, clip) -> str:
    """Composited text of *widget*'s rectangle, intersected with *clip*'s.

    Two things ``_region_text`` below does not do, both of which these sweeps
    need.  It assumes the whole region is on-screen, and at these heights a
    panel's region can start *below* the last composited row -- which is the
    failure being measured, so it has to clip rather than raise.  And a widget
    inside a scroll container keeps its full region even when the container
    paints only part of it, so without intersecting the container's rectangle
    this would read whatever is painted underneath and call it the panel.
    """
    lines = _screen_text(app).split("\n")
    region = widget.region.intersection(clip.region)
    return "\n".join(
        lines[y][region.x : region.x + region.width]
        for y in range(region.y, min(region.y + region.height, len(lines)))
    )


def _missing_at(app, screen) -> list[str]:
    """Everything the three-row layout promises that is not composited.

    Deliberately not "every row of every panel": the feed and the activity log
    are scrolling ``RichLog``s that legitimately show fewer posts on a shorter
    terminal, exactly as they do on a taller one with more posts. What is
    promised is the *fixed* content -- the six detectors, the market's five
    figures -- plus the activity panel's declared floor, which is what
    ``ACTIVITY_MIN_HEIGHT`` exists to make measurable.
    """
    text = _screen_text(app)
    market = _visible_panel(
        app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
    )
    missing = [d for d in _DETECTORS if d not in text]
    missing += [f"market {f}" for f in _MARKET_FIELDS if f not in market]
    if "DEV ACTIVITY" not in text:
        missing.append("DEV ACTIVITY")
    missing += [f"activity {r}" for r in _ACTIVITY_ROWS if r not in text]
    return missing


async def test_every_panel_is_whole_on_a_terminal_that_fits_them():
    """The positive half, at the height the rail first fits and well above it.

    Without this the sweep below is satisfied by a marker welded permanently
    to the title bar -- the failure mode this codebase keeps recording.
    """
    for height in (FIRST_WHOLE_HEIGHT, 46, 60):
        async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, height) as (app, screen, _p):
            assert _missing_at(app, screen) == [], (
                f"at {SURF_FULL_LAYOUT_COLUMNS}x{height} the layout is short of "
                f"{_missing_at(app, screen)}"
            )
            assert TALLER_HINT not in _screen_text(app), (
                f"the row marker is lit at {SURF_FULL_LAYOUT_COLUMNS}x{height}, "
                "where everything fits"
            )
            assert screen.query_one(_RAIL).show_vertical_scrollbar is False


async def test_no_height_drops_content_without_saying_so():
    """The row-wise half of the ``‹ widen`` contract, swept height by height.

    The contract is not "everything always fits" -- at 28 rows it cannot. It
    is that a height which costs the screen a promised line must light the row
    marker on the **title bar**: row 0, the one row a short terminal can never
    push off, unlike the panel titles themselves.

    The sweep runs to 16 rows because the failure it guards moved. In the
    two-row layout the market lived in the rail, shrank silently and was gone
    by 31; here it sits in an ``auto`` bottom row and survives to 20, below
    which the screen itself scrolls and the bottom row goes off the end. Both
    ends of that range have to stay advertised.
    """
    for height in range(40, 15, -1):
        async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, height) as (app, screen, _p):
            missing = _missing_at(app, screen)
            lit = TALLER_HINT in _screen_text(app).split("\n")[0]
            if missing:
                assert lit, (
                    f"at {SURF_FULL_LAYOUT_COLUMNS}x{height} the screen lost "
                    f"{missing} with nothing on screen to say so"
                )


async def test_the_marker_lights_before_the_first_line_is_actually_lost():
    """It leads the loss by two rows, and that is the floor doing its job.

    ``SurfDevActivity`` is ``1fr`` in a scroll container, so it shrinks rather
    than overflowing; ``min-height: ACTIVITY_MIN_HEIGHT`` is what converts
    "the rail is one row short" into an overflow the screen can see. The two
    rows of slack are the blank tail of that floor: at 36 and 35 the rail is
    genuinely painting less than it holds, and by 34 a real activity row has
    gone. A marker that lit at 34 instead would have let two heights of
    silent shrinkage through, which is precisely how the market disappeared
    from this rail before.

    Both numbers moved up one on 2026-08-10 (35/33 -> 36/34) when the rail
    gained its one-row separator. The *lead* is what this test is about, and
    it is unchanged -- which is the point: the separator cost a row of rail,
    not a row of warning.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, FIRST_WHOLE_HEIGHT - 1) as (
        app, screen, _p
    ):
        assert TALLER_HINT in _screen_text(app).split("\n")[0]
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True
        assert _missing_at(app, screen) == [], (
            "the marker no longer leads the loss -- re-measure both numbers"
        )

    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, FIRST_WHOLE_HEIGHT - 3) as (
        app, screen, _p
    ):
        assert _missing_at(app, screen), (
            f"{FIRST_WHOLE_HEIGHT - 3} rows fits everything after all -- the "
            "marker leads the loss by more than two rows now"
        )


async def test_the_market_keeps_its_figures_far_below_the_rail():
    """143x30: the height at which the old layout showed a blank rail.

    Moving the market out of the scrolling rail and into the ``auto`` bottom
    row is what bought this: every figure is still composited ten rows below
    the height the rail stops fitting, and the panel is still its full height
    rather than a title over nothing.

    Seven rows: eight from 2026-08-11, when a second blank row went in under
    the title, and seven again from 2026-08-24, when it came back out -- on
    screen the pair read as a gap rather than as the title standing off its
    figures. The number is asserted rather than derived from the widget so
    that a row appearing or vanishing has to be a deliberate edit here --
    counting ``compose``'s yields would agree with itself through any change
    at all.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 30) as (app, screen, _p):
        panel = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
        assert all(field in panel for field in _MARKET_FIELDS), (
            f"the market lost {[f for f in _MARKET_FIELDS if f not in panel]}"
        )
        assert screen.query_one(SurfMarket).region.height == 7
        # ...and the rail's own loss is still advertised, in words.
        assert TALLER_HINT in _screen_text(app).split("\n")[0]
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True


async def test_the_market_panel_is_not_clipped_at_the_pinned_layout_width():
    """Nothing is cut here at the width the layout is measured at.

    Pairing the sparklines with their figures and adding the bridge block
    took the panel's widest row from ~33 rendered columns to 71 against the
    captured spread -- and to **73** against a tight one, because the row's
    width moves with ``fmt_price``'s precision band and moves the wrong way:
    a gap under $0.01 renders ``$0.007100`` where the capture's $0.0200
    renders ``$0.0200``, so a *healthier* peg is a *wider* row. That is what
    took this layout 142 -> 143; the margin the 71 suggested was never there.

    The panel grew its own tiers on 2026-08-11 (``widgets/surf/market.py``:
    five of them, measured off the rows it actually paints), so a narrower
    terminal now sheds a named field and says so rather than ellipsising in
    silence. That is the *narrow* half and it is pinned in the widget tests.
    This is the wide half, and it stays here because the two are different
    claims: a tiered panel that sheds a field it did not have to would pass
    every test over there and be wrong on every terminal anyone owns.
    """
    for width in (SURF_FULL_LAYOUT_COLUMNS, 143, 160):
        async with _screen_at(width, 46) as (app, screen, _p):
            panel = _visible_panel(
                app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
            )
            assert "…" not in panel, (
                f"at {width} columns the market is cut with nothing to say so:\n"
                f"{panel}"
            )
            # The bridge block is the part that is newly wide, and the two
            # ends of it are the two that must survive: what IMD is, and
            # that the spread is gross.
            assert "IMD is FP bridged 1:1 from Base" in panel
            assert "gross of fees" in panel
            # ...and it says so, too: a panel shedding a field it has room
            # for would satisfy every assertion above.
            assert "‹ widen" not in panel, (
                f"at {width} columns the market sheds a field it has room "
                f"for:\n{panel}"
            )


#: This module imports ``SURF_FULL_LAYOUT_COLUMNS`` further down, beside the
#: width-sweep section it belongs to, so it is not a name this helper can
#: take as a default argument -- defaults bind at ``def`` time. Resolved in
#: the body instead, which runs long after the module has finished loading.
async def _market_title(pool_id_source, width: int | None = None) -> str:
    """The IMD MARKET panel's composited title row at *width*, region-scoped.

    ``_region_text``, not ``_screen_text``: ``pool`` and ``unverified`` are
    ordinary words and a whole-screen substring check would be satisfied by
    another panel one day. The claim is about this panel's own title row.
    """
    payload = _frozen_payload(pool_id_source=pool_id_source)
    async with _screen_at(
        SURF_FULL_LAYOUT_COLUMNS if width is None else width, 48, payload
    ) as (app, screen, _pilot):
        return _region_text(app, screen.query_one(SurfMarket)).splitlines()[0]


async def test_only_a_fallback_pool_id_warns_on_the_market_title():
    """The pool-identity warning, restored 2026-08-24 (fix round 1).

    38 ETH/IMD v4 pools exist on mainnet and 37 are third-party decoys, some
    at fee tiers up to 98%. ``pool_id_source == "fallback"`` means
    ``LaunchpadHook.imdEthPoolId()`` did not answer and a vendored constant
    was used instead -- so the liquidity and the on-chain price leg on THIS
    panel may belong to somebody else's pool. Retiring the hero's POOL box
    left that claim with no home anywhere on the dashboard for one commit;
    DECOY POOL on the signals rail carries the decoy *count*, which does not
    answer "did we pick the right one out of the 38".

    Three states, three different claims, asserted against composited output:

    * ``"fallback"`` -- we looked and could not verify. Warn.
    * ``"hook"``     -- we looked and it checks out. Silent.
    * ``None``       -- the launchpad sweep has not run. Also silent: warning
      here would collapse "unverified" into "unread", the same
      two-claims-one-string bug ``burn_ready``'s tri-state exists to avoid,
      and the panel's own rows already say they have no data.
    """
    warned = await _market_title("fallback")
    assert POOL_UNVERIFIED_HINT in warned, warned
    assert warned.strip().startswith(PANEL_TITLE), (
        "the marker replaced the panel title instead of being appended to it"
    )

    for quiet_source in ("hook", None):
        quiet = await _market_title(quiet_source)
        assert PANEL_TITLE in quiet
        for marker in (POOL_UNVERIFIED_HINT, POOL_UNVERIFIED_SHORT, "pool id"):
            assert marker not in quiet, (
                f"pool_id_source={quiet_source!r} warned: {quiet!r} -- only a "
                "verified-and-failed lookup may claim the pool is unverified"
            )


async def test_the_pool_warning_outranks_the_widen_hint_and_never_wraps():
    """Two markers share one title row, and the priority is not arbitrary.

    A shed column is a nuisance the reader fixes by widening; a pool nobody
    verified means the figures below may not be IMD's at all, which the
    reader cannot fix and cannot learn any other way. So the warning takes
    the columns first and the widen hint degrades around it -- at 55 columns
    the panel carries ``· pool ?`` and no hint at all, where the same panel
    with a verified pool carries ``‹ widen``.

    **And neither may wrap.** ``#surf-mkt-title`` has no ``text-overflow``
    and the row is ``auto``-height, so a title one column too long takes a
    second row out of a panel whose eighth row is the bridge block. The
    height is asserted identical across all three states at every width --
    that is the property that would break silently, in a panel that still
    looks fine, if the budget arithmetic were wrong.
    """
    # Priority: at this width the warning fits and the descriptive hint does
    # not, so the hint is what gives way.
    narrow = await _market_title("fallback", 55)
    assert POOL_UNVERIFIED_SHORT in narrow, narrow
    assert "‹ widen" not in narrow, narrow
    assert "‹ widen" in await _market_title("hook", 55)

    # Both fit together once there is room for both.
    roomy = await _market_title("fallback", 90)
    assert POOL_UNVERIFIED_HINT in roomy and "‹ widen" in roomy, roomy

    # Too narrow for even the short form: silent rather than wrapped, the
    # rule this panel's own `_set_title` already applies to its widen hint.
    assert POOL_UNVERIFIED_SHORT not in await _market_title("fallback", 40)

    # ...and the title never costs the panel a row, in any state, at any of
    # the widths above.
    for width in (40, 55, 62, 90, 120, 143):
        heights = {}
        for source in ("fallback", "hook", None):
            payload = _frozen_payload(pool_id_source=source)
            async with _screen_at(width, 48, payload) as (_app, screen, _pilot):
                heights[source] = screen.query_one(SurfMarket).region.height
        assert len(set(heights.values())) == 1, (
            f"the pool marker changed the panel's height at {width}: {heights}"
        )


async def test_the_market_advertises_its_own_shedding_on_the_real_screen():
    """The narrow half, on the composited screen rather than in a harness.

    The widget tests drive ``SurfMarket`` in a bare harness where its content
    box is the whole app; here it is ``7fr`` of a 13-column seam inside a
    padded row, which is the geometry that actually decides how many columns
    it gets -- and the geometry a widget test cannot see. **142 is the first
    terminal width that costs the market a field**, so the two halves of the
    contract are pinned at both ends and one column apart:

    * at 143 the panel is whole and unmarked;
    * at 142 a field is gone, the marker names it, and no row is cut.

    Deliberately *not* derived from ``SURF_FULL_LAYOUT_COLUMNS``, even now
    that the two agree: an independent literal is what makes a widget that
    grows a column fail *here*, with the number in hand, instead of moving
    both sides of the comparison together and pinning nothing.

    **The market is the panel that sets the layout width now**, against a
    tight peg -- it is the last one asking for a column, one above the
    announce feed. The guard below says so rather than letting the two drift.
    """
    market_first_full_terminal = 143
    assert market_first_full_terminal == MEASURED_FULL_LAYOUT_COLUMNS, (
        "the market is no longer the panel that sets the full-layout width -- "
        "re-measure it and correct every surface that names the market"
    )

    async with _screen_at(market_first_full_terminal, 46) as (app, screen, _p):
        whole = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
    assert "‹ widen" not in whole and "…" not in whole, whole
    assert "vol 24h" in whole and "gap narrows" in whole

    async with _screen_at(market_first_full_terminal - 1, 46) as (app, screen, _p):
        shed = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
    assert "…" not in shed, f"a row is cut where a tier should have fitted:\n{shed}"
    assert "vol 24h" not in shed, f"nothing was shed one column down:\n{shed}"
    # The marker is on this panel's own rectangle, and it names the field.
    assert "‹ widen" in shed.split("\n")[0], shed
    assert "24h volume" in shed.split("\n")[0], shed


async def test_the_row_marker_follows_a_live_resize_in_both_directions():
    """Dragging the window is the common case, and it refetches nothing.

    The title bar is composed from the last payload, so without a resize
    hook the marker only corrects itself on the next 30-second poll: half a
    minute of a lit marker on a terminal that now fits, or -- worse -- of a
    dark one on a terminal that no longer does.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 46) as (app, _screen, pilot):
        assert TALLER_HINT not in _screen_text(app).split("\n")[0]

        await pilot.resize_terminal(SURF_FULL_LAYOUT_COLUMNS, 30)
        await pilot.pause()
        assert TALLER_HINT in _screen_text(app).split("\n")[0], (
            "the terminal shrank past the rail and the marker stayed dark"
        )

        await pilot.resize_terminal(SURF_FULL_LAYOUT_COLUMNS, 46)
        await pilot.pause()
        assert TALLER_HINT not in _screen_text(app).split("\n")[0], (
            "the terminal grew back and the marker stayed lit"
        )


#: A payload with every flag the title bar can carry lit at once: the LP owner
#: warning and **every** degraded group. Not a hypothetical -- the manager's
#: outermost guard writes ``payload["degraded"] = list(SOURCES)`` on a failed
#: cycle (``data/surf_manager.py``), so all six at once is the state this row
#: is *most* likely to be in when it matters, and the LP flag is independent
#: of it.
#:
#: The list is taken from ``SOURCES`` rather than typed out: it was three
#: names for one commit, which made ``WORST_CASE_TITLE_COLUMNS`` measure a
#: case the manager never emits and left the one concrete mutation this
#: fixture exists to catch -- *a longer degraded list* -- green. Sorted, so
#: the payload is stable if the declaration order moves; the width does not
#: depend on the order but the diff should not either.
def _worst_case_title_payload() -> dict:
    from maxpane_dashboard.data.surf_manager import SOURCES

    return _frozen_payload(
        feed_items=_representative_feed_items(),
        degraded=sorted(SOURCES),
        lp_owner_ok=False,
    )


async def test_the_row_marker_survives_a_title_bar_full_of_warnings():
    """The one loss signal on the screen must not be the first thing lost.

    ``#title-bar`` is one row high and the ``Static`` *wraps*: everything past
    the first line reaches no pixel at all -- no ``…``, no scrollbar, nothing.
    With every degraded group and the LP warning the line runs 133 columns, so
    at 100 the wrap falls inside the degraded list and used to take
    ``‹ taller`` (and the version tail) with it. The rail was scrolling,
    DEV ACTIVITY's rows
    were off screen, and the screen said so nowhere -- and only when a source
    was *also* down, which is precisely when a reader needs both.

    So the marker rides in front of the warnings. It is the only advertisement
    on this screen with no second home: the LP flag is also the hero's
    ``OWNER CHANGED`` box, and a degraded group is also its own panel's
    unavailable state, but nothing else anywhere says a row went off the
    bottom.
    """
    payload = _worst_case_title_payload()
    # 100 is the narrowest terminal this project treats as real; 120 and 130
    # are inside the band where the *tail* is being cut (see
    # ``WORST_CASE_TITLE_COLUMNS``), which is exactly where the ordering has
    # to hold. ``SURF_FULL_LAYOUT_COLUMNS`` is not spelled as 143 beside
    # itself: two entries with the same value swept one width twice.
    for width in (100, 120, 130, SURF_FULL_LAYOUT_COLUMNS):
        async with _screen_at(width, 30, payload=payload) as (app, screen, _p):
            assert screen.query_one(_RAIL).show_vertical_scrollbar is True, (
                f"{width}x30 fits the rail after all -- pick a shorter height"
            )
            row0 = _screen_text(app).split("\n")[0]
            assert TALLER_HINT in row0, (
                f"at {width}x30 the rail is scrolling and row 0 says nothing:\n"
                f"{row0!r}"
            )
            # The warning it now precedes is still on the same row -- the fix
            # is an ordering, not a trade of one advertisement for another.
            assert "⚠ LP owner changed" in row0, row0

    # ...and it stays dark on a terminal that fits, warnings or no warnings:
    # this must not become a marker that is simply always on.
    async with _screen_at(100, 46, payload=payload) as (app, screen, _p):
        assert screen.query_one(_RAIL).show_vertical_scrollbar is False
        assert TALLER_HINT not in _screen_text(app)


async def test_the_freshness_marker_survives_the_launchpad_swap():
    """I4: the one tier with a DETACHED sweep must not be the one whose
    staleness the default view cannot show.

    ``l`` swaps the whole dashboard body, so the launchpad's own ``as of
    HH:MM`` (inside ``SurfBurnPipeline``/``SurfLaunchpadCoins``) is invisible
    from the dashboard and every panel that could carry one is invisible from
    the launchpad. ``#title-bar`` is outside both bodies and is the only place
    a reader can see, in either mode, that the numbers stopped moving --
    which is exactly why opting into the StatusBar's key hints (and giving up
    its ``updated Ns ago``) is defensible here at all.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 48) as (app, screen, pilot):
        assert f"as of {_AS_OF_HHMM}" in _screen_text(app).split("\n")[0]
        await pilot.press("l")
        await pilot.pause()
        assert screen._mode == MODE_LAUNCHPAD
        assert f"as of {_AS_OF_HHMM}" in _screen_text(app).split("\n")[0], (
            "the freshness marker went away with the dashboard body"
        )


async def test_a_cold_cache_still_says_as_of_rather_than_going_quiet():
    """A marker that disappears when there is nothing to be fresh about reads
    identically to a healthy one -- the FARM/HOUR SAVED bug, on the row that
    covers the whole screen."""
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 48, payload=_all_none_payload()) as (
        app, _screen, _p
    ):
        row0 = _screen_text(app).split("\n")[0]
        assert "as of —" in row0, row0


#: The narrowest terminal on which the **whole** worst-case title bar reaches
#: a pixel: the board's name, every figure, the ``as of`` marker,
#: ``‹ taller``, the LP warning and **all eight** degraded groups, all on the
#: one row of this screen that cannot ellipsise. Swept over the real screen rather than counted -- ``⚠``
#: is not a one-column glyph on every width table, so the arithmetic is not
#: the test.
#:
#: **139** (final fix wave, I4; was 142, and 137 before that across six
#: source groups). The row gained ``as of HH:MM`` -- this screen had no
#: freshness signal anywhere, which stopped being survivable once the
#: launchpad arrived as a **detached** sweep -- and paid for it by dropping
#: ``feed #N (age)``, which the ANNOUNCE panel's own title renders verbatim
#: one row down (``ANNOUNCE · #14 · last 23h ago``). Adding the marker alone
#: measured **156**, past ``SURF_FULL_LAYOUT_COLUMNS`` (143), where this
#: row's tail is *gone* rather than clipped; the seventeen columns the
#: duplicate segment was spending bought it with three to spare. Shorten the
#: copy, do not widen the layout -- the same rule that turned
#: ``SOURCE_LAUNCHPAD`` into ``"pad"`` rather than raising this pin when the
#: seventh source group arrived (the long form measured past 143 on its own,
#: and even at three characters the name still cost five columns, ``, pad``,
#: taking the pin 137 -> 142). Measured by sweeping the real render 130-149,
#: not computed. It read **111** for one commit,
#: measured against a fixture carrying three degraded groups -- but
#: ``SurfManager``'s outermost guard emits ``list(SOURCES)``, every group,
#: and a full outage is precisely when this row is read. The fixture derives
#: its list from ``SOURCES`` (:func:`_worst_case_title_payload`), so the
#: number moves with the vocabulary instead of behind it -- which is exactly
#: the mutation that moved this constant this time.
#:
#: **139 -> 143 on 2026-09-01, and the margin is now zero.** ``SOURCE_POOL4``
#: is the **eighth** degraded group (``surf_manager.SOURCES``), and this row
#: prints every member verbatim, so ``, p4`` cost it exactly four columns --
#: measured, not computed, by sweeping the real render 128..159 with the
#: outage payload: ``pad``, the last name the row prints, first survives at
#: **143** and is cut at 142.
#:
#: 143 is ``SURF_FULL_LAYOUT_COLUMNS`` exactly, which is the outcome the pool4
#: plan's own risk register predicted to the column ("that is 143 exactly --
#: zero margin"). The standing rule is to shorten the copy rather than widen
#: the layout, and it does not fire here: the row *fits* the documented width,
#: it merely no longer clears it. What zero margin actually means is worth
#: stating, because it is a fact about the **next** change rather than this
#: one: a ninth source group, or one more word anywhere on this line, puts the
#: worst case past 143 and the tail is *gone* -- no ``…``, no scrollbar, no
#: trace, on the one row of this screen that exists to say something is down.
#: The assertion at the end of the companion test below is what turns that
#: into a red suite instead of a silent loss, and it now has no slack left to
#: absorb an edit. Shorten this row before adding to it.
#:
#: It read 139 with seven groups and 142 with six-plus-``pad``; the history is
#: in the paragraphs above.
WORST_CASE_TITLE_COLUMNS = 143


async def test_the_worst_case_title_bar_keeps_its_whole_tail_from_here():
    """Both directions, so the number is tight rather than merely generous.

    A wrapping ``height: 1`` ``Static`` loses its tail with no ``…`` and no
    scrollbar, so "where does it start losing it" is a real measurement and
    not a detail -- and it moves whenever this row's copy *or the source
    vocabulary* moves. The sentinel is the last name the row prints, read
    from ``SOURCES``: hard-coding ``"nft"`` would keep passing if a seventh
    group were appended after it, which is the mutation this measurement
    exists to catch.
    """
    from maxpane_dashboard.data.surf_manager import SOURCES

    last_name = sorted(SOURCES)[-1]
    payload = _worst_case_title_payload()
    async with _screen_at(WORST_CASE_TITLE_COLUMNS, 30, payload=payload) as (
        app, _screen, _p
    ):
        assert last_name in _screen_text(app).split("\n")[0], (
            f"the tail is already gone at {WORST_CASE_TITLE_COLUMNS} columns"
        )
    async with _screen_at(WORST_CASE_TITLE_COLUMNS - 1, 30, payload=payload) as (
        app, _screen, _p
    ):
        assert last_name not in _screen_text(app).split("\n")[0], (
            f"the whole line already fits at {WORST_CASE_TITLE_COLUMNS - 1} -- "
            "the copy got shorter, re-measure this"
        )

    # The claim the number is *for*: at the width the whole dashboard is
    # measured to need, a total outage still prints every group it names.
    # Two independently swept constants, not one compared with itself.
    assert WORST_CASE_TITLE_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS, (
        f"the worst-case title bar needs {WORST_CASE_TITLE_COLUMNS} columns "
        f"but the surf layout is measured at {SURF_FULL_LAYOUT_COLUMNS}: at "
        "the full layout a full outage would silently lose group names"
    )


#: A width where ``SurfDevActivity`` is genuinely below its widest tier, for
#: the resize test below.  It must **not** be ``SURF_FULL_LAYOUT_COLUMNS``:
#: that constant is by definition the width at which nothing is shed, so using
#: it here made the "before" assertion vacuous the moment the constant was
#: re-measured from 135 to 176 -- the panel already showed the amount column,
#: and the test could no longer see a re-tier happen at all.  It was 143 while
#: the full row needed 66 columns of rail; the row needs 58 now, so 143 is
#: inside the *clean* band and re-tiers from nothing.  120 is a real terminal
#: width, is inside the marked band pinned above, and leaves the panel a
#: genuine tier below its widest.
_NARROW_FOR_RE_TIER = 120


async def test_the_activity_panel_re_tiers_when_the_terminal_is_resized():
    """``SurfDevActivity.on_resize`` outlived the ``c`` swap that motivated it.

    It was written because the panel was composed hidden and therefore first
    rendered at zero width, where ``_tier_for`` optimistically picks ``full``.
    That is gone, but the path is not: ``RichLog`` rows are formatted at write
    time against the width they were written at, so a widened terminal shows
    yesterday's tier -- padded, shrunken and marked -- until something
    re-renders them. Nothing else does.
    """
    async with _screen_at(_NARROW_FOR_RE_TIER, 46) as (app, screen, pilot):
        activity = screen.query_one(SurfDevActivity)
        assert "0.310 ETH" not in _region_text(app, activity)

        await pilot.resize_terminal(200, 46)
        await pilot.pause()

        panel = _region_text(app, screen.query_one(SurfDevActivity))
        assert "0.310 ETH" in panel, (
            "the rows kept the narrow terminal's tier after it was widened"
        )
        assert "‹ widen" not in panel


# -- the pinned full-layout width ---------------------------------------

from maxpane_dashboard.__main__ import _DEFAULT_FONT_SIZE  # noqa: E402
from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS


def _representative_feed_items() -> list[dict]:
    """The captured feed items minus the one carrying an unbreakable token.

    The nonce-13 post's tx-link (a URL glued to a 66-char hex hash by the
    raw text's own punctuation, no space) is 91 columns wide and cannot be
    wrapped -- ``SurfFeed`` correctly truncates it and lights its own
    ``‹ widen`` no matter how wide the panel gets, because the *next* real
    post linking a transaction will do the same thing again. That belongs to
    a fixture that documents it as permanent
    (``test_a_linked_post_advertises_widen_at_full_layout_width_forever``
    below), not to the fixture the full-layout width is measured against --
    a fixture containing an inherently-unbreakable token has no finite width
    that clears it, so it cannot be what "full layout" is measured from.
    This is the same real captures (nonce 12's short link, the reply) minus
    that one post, nothing invented.
    """
    return [
        item
        for item in _sample_data()["feed_items"]
        if item["ts"] != _TS_POST_13
    ]


#: An FP price putting the IMD/FP gap inside ``fmt_price``'s six-decimal band
#: while leaving IMD at its captured price.  Derived, not invented: any gap
#: under $0.01 renders ``$0.007100`` where the capture's $0.0200 renders
#: ``$0.0200``, and the market panel's binding row is two columns **wider**
#: for it.  At IMD's $0.7074 that band is every parity inside ±1.41%, i.e.
#: the normal state of a 1:1 bridge -- the capture's 2.75% is the outlier.
_TIGHT_PEG_FP_PRICE = 0.7145


def _tight_peg(payload: dict) -> dict:
    """*payload* with the IMD/FP pair at a sub-cent gap, parity recomputed."""
    imd = payload["imd_price_usd"]
    return {
        **payload,
        "fp_price_usd": _TIGHT_PEG_FP_PRICE,
        "parity_pct": (imd / _TIGHT_PEG_FP_PRICE - 1) * 100,
    }


def _widen_sweep_payload() -> dict:
    """The payload the full-layout-width measurement sweeps against.

    Carries a **tight** peg, because ``SurfMarket``'s widest row is a
    function of the spread and gets wider as the spread narrows: the dollar
    gap is the one cell whose precision band moves, and the capture's
    unusually wide 2.75% renders it two columns short of what a healthy 1:1
    bridge renders. A width measured against the capture alone is a width the
    panel exceeds in its ordinary state -- which is what
    ``test_the_full_layout_width_covers_a_tight_peg_not_only_the_capture``
    holds, and why this is not the raw capture.
    """
    return _tight_peg(_frozen_payload(feed_items=_representative_feed_items()))


async def _widen_markers(width: int, payload: dict | None = None) -> int:
    """Composited ``‹ widen`` count at *width*, whole screen.

    Defaults to the representative (no-unbreakable-token) payload; pass
    ``payload=`` to measure against something else, e.g. the full sample with
    the tx-linked post.  There is no ``view`` argument any more: every panel
    is composited at once, so one render measures the whole dashboard.
    """
    manager = _FakeManager(
        payload=payload if payload is not None else _widen_sweep_payload()
    )
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _screen_text(app).count("‹ widen")


async def _panels_asking_for_width(width: int) -> set[str]:
    """Which panels composite a ``‹ widen`` at *width*, by their own titles.

    A count alone cannot say *whose* marker is the last one standing, and
    that is the claim the sweep constants below are written around -- it has
    changed hands three times (activity, feed, market) and was restated in
    prose each time without a test that could contradict it.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        panels = (SurfHero, SurfFeed, SurfSignals, SurfDevActivity,
                  SurfMarket, SurfNft)
        marked = {
            cls.__name__
            for cls in panels
            if "‹ widen" in _region_text(app, screen.query_one(cls))
        }
        # No panel outside that tuple may hide a marker from this helper.
        assert len(marked) == _screen_text(app).count("‹ widen"), marked
        return marked


async def _markers_outside_the_activity_panel(width: int) -> int:
    """The same count, minus the ones inside ``SurfDevActivity``'s rectangle.

    The activity panel is the one widget the three-row layout genuinely
    narrowed -- it swapped a ``3fr`` slot of its own for a share of the right
    rail -- so it is the last panel to come clean as the terminal widens.
    Subtracting it is how the tests below still say something about *the
    other five*, and it is how the seam's balance is measured: the two
    numbers are now adjacent where they were 41 columns apart.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        whole = _screen_text(app).count("‹ widen")
        panel = _region_text(app, screen.query_one(SurfDevActivity))
        return whole - panel.count("‹ widen")


# -- the seam, and the width it buys ------------------------------------
#
# Both lower rows split on one seam, and *where* that seam sits is the whole
# full-layout width. It is a measurement, not a taste call: the left column's
# binding panel is ``SurfFeed`` (the columns it needs before it breaks a post)
# and the right column's is ``SurfDevActivity`` (the rail it needs before it
# sheds a field), so the narrowest terminal serving both is their sum -- and
# only a seam near their ratio collects it.
#
# **The two needs, and the sweep, are both dated. Re-measure before quoting.**
#
# *At the 3:2 -> 7:6 re-seam*, the needs were 81 and 71 (sum 152). 3:2 handed
# the feed 0.60 W against the 0.538 it needed, so the rail reached 71 only at
# 176: 24 columns wider than the layout required, and past the ~169 a laptop
# gets at the 17 pt MaxPane forces on launch. Swept over the real screen then:
#
#     5:3 187 · 13:8 184 · 8:5 183 · 3:2 176 · 7:5 169 · 11:8 167 · 4:3 164
#     1:1 162 · 9:7 161 · 5:4 158 · 11:9 156 · 12:11 156 · 6:5 155 · 10:9 154
#     19:17 154 · 9:8 153 · 13:11 153 · 17:15 153 · 7:6 152 · 8:7 152
#     23:20 152 · 81:71 152
#
# *Today the needs are 76 and 63* -- ``feed.FULL_TEXT_WIDTH`` came down 76 ->
# 71 (feed's need 81 -> 76) and the activity row's cells were sized to their
# producer's vocabularies (rail's need 71 -> 63). Sum 139. Re-swept the same
# way, patching both copies of the seam (``DEFAULT_CSS`` *and* the
# ``minimal.tcss`` block, which outranks it -- patching one alone measures
# nothing):
#
#     5:3 166 · 13:8 163 · 8:5 162 · 3:2 156 · 1:1 152 · 7:5 149 · 11:8 148
#     12:11 146 · 4:3 145 · 10:9 145 · 17:15 144 · 8:7 143 · 9:7 142 · 7:6 142
#     13:11 141 · 5:4 140 · 6:5 140 · 11:9 139 · 23:19 139 · 76:63 139
#
# So the floor moved 152 -> 139 and the seam that collects it moved with it:
# ~1.21 now (76:63), not ~1.14-1.19. **7:6 costs 142, three columns above the
# floor**, and the layout keeps it: ``__main__.FULL_LAYOUT_COLUMNS`` is FWA's
# 143 again, so a surf screen that cleared at 139 instead of 142 would not
# move one number a user sees. Re-seaming is what you do when one of the two
# needs moves; recording the three columns is what you do meanwhile.
#
# These constants used to be ``FIRST_CLEAN_WIDTH`` (an alias for
# ``SURF_FULL_LAYOUT_COLUMNS``) and ``FIRST_CLEAN_WIDTH_WITHOUT_THE_ACTIVITY_
# PANEL = 135``, describing the 3:2 seam with 41 columns of daylight between
# them. Both moved with the seam.

#: Column-points a maximized laptop terminal has to spend: columns times font
#: size, which is very nearly constant because the window is already as wide as
#: the display. Measured 169 columns at 17 pt, and the README's other quoted
#: pair falls out of the same number -- 2873 / 14 == 205.2, i.e. the "about 205
#: at 14 pt" it prints two lines later.
LAPTOP_COLUMN_POINTS = 2873

#: Columns a laptop gets at the font size ``__main__`` forces on launch. The
#: whole point of the seam re-measurement: at 3:2 the full layout needed 176 and
#: was therefore unreachable here without ``--font-size``.
#:
#: **Derived from ``_DEFAULT_FONT_SIZE``, not written down.** It was the bare
#: literal ``169`` until final review I-3, which left the premise of
#: ``test_the_full_layout_is_reachable_at_the_forced_font_size`` unpinned:
#: raising the forced size to 24 pt would have dropped a real laptop to 119
#: columns while the test happily went on rendering at 169 and passing, with
#: the claim in its own name false. Now the same edit moves this number and
#: the test measures the width the app actually produces.
LAPTOP_COLUMNS_AT_THE_FORCED_FONT = LAPTOP_COLUMN_POINTS // _DEFAULT_FONT_SIZE

#: The narrowest width at which **no** surf panel composites a ``‹ widen``,
#: swept one column at a time over the real screen and pinned in both
#: directions by ``test_the_measured_full_layout_width_is_exactly_the_tight_one``.
#:
#: Deliberately kept as an **independent literal** rather than an alias for
#: ``SURF_FULL_LAYOUT_COLUMNS``, even now that the two agree. The source
#: constant is quoted by ``__main__.FULL_LAYOUT_COLUMNS``, the ``--font-size``
#: help text, the README width table and CLAUDE.md; this number is what the
#: screen actually measures. Aliasing them would turn every cross-check below
#: into a constant compared against itself, which pins nothing -- the whole
#: point is that a widget growing a column moves *this* one and the mismatch
#: is what goes red.
#:
#: They have been apart twice, both times for one commit, both times because
#: a re-measurement lands before the five surfaces that quote it: 24 apart
#: when the 3:2 -> 7:6 re-seam brought the measurement 176 -> 152, and 10
#: apart when sizing the activity row's wallet and kind cells to the
#: producer's real vocabularies (``{"dev", "ops"}`` and ``DEV_TX_KINDS``)
#: took ``activity.FULL_WIDTH`` 66 -> 58 and this measurement 152 -> 142.
#: ``test_the_documented_width_still_covers_the_measured_one`` held the
#: direction meanwhile (generous is safe; short clips). Both reconciliations
#: landed; both constants read **143**.
#:
#: **142 -> 143 on 2026-08-12, and the binding panel changed hands again.**
#: The number was measured against the capture's 2.75% IMD/FP spread, which
#: renders the *narrow* case of ``SurfMarket``'s binding row: ``fmt_price``
#: switches to six decimals below $0.01, so a **tighter** peg -- every parity
#: inside ±1.41% at IMD's $0.7074, i.e. the ordinary state of a 1:1 bridge --
#: renders ``$0.007100`` for ``$0.0200`` and needs two columns more. The sweep
#: payload carries a tight peg for exactly that reason (``_widen_sweep_
#: payload``), and the market is now the last panel asking for a column: the
#: announce feed clears at 142, the market at 143. The activity panel has
#: cleared from 135 since its row was resized; every claim of the form "the
#: activity panel is the one still buying width" belongs to the 176 and 152
#: eras, and "the feed is the last one" to the 142 era.
MEASURED_FULL_LAYOUT_COLUMNS = 143

#: The narrowest width at which every panel *except* the activity is clean --
#: i.e. the width the widest of the feed and the market asks for. It was 41
#: below the number above at the 3:2 seam (that gap *was* the defect), one
#: below it at 7:6, and 10 below it after ``feed.FULL_TEXT_WIDTH`` dropped
#: 76 -> 71 so the feed would wrap in a narrower column. It is now **equal**
#: to it, and stays equal for a second reason: the panel that sets it is the
#: market, which is not in the activity's rectangle either.
MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL = 143

#: How far the *activity* column may drift above the feed's before the seam is
#: worth re-cutting. Not a tolerance to widen when a measurement disappoints:
#: it is width the rail is buying that the feed has stopped using. Lower it
#: when a re-seam banks some; never raise it to make a number pass.
#:
#: **Zero**, and it stays zero: the activity panel clears seven columns below
#: the feed, so it is buying nothing. A ratchet above 0 would let that gap
#: re-open in silence.
#:
#: Read what it measures, though, and not more. This number is deliberately
#: one-sided -- it subtracts the activity panel and nothing else -- so it goes
#: blind exactly when the *feed* is the panel above the seam's balance point,
#: which is the regime the screen is in now. The recoverable width today is
#: **3 columns** (7:6 collects the layout at 142; a 76:63-shaped seam collects
#: it at the 139 the two panels actually sum to), measured in the seam table
#: above and not visible here at all. Those three columns are unspent on
#: purpose: ``__main__.FULL_LAYOUT_COLUMNS`` is FWA's 143, so surf clearing at
#: 139 rather than 142 would change nothing anyone sees. If the feed's or the
#: rail's need moves again, re-sweep the table before re-seaming -- do not
#: raise this constant to describe it.
RECOVERABLE_SEAM_SLACK = 0

#: Readable alias at the one site that wants to say "the width at which this
#: panel has everything it needs".
FIRST_CLEAN_WIDTH = MEASURED_FULL_LAYOUT_COLUMNS


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    """Well below the threshold every drop is announced, never silent."""
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 20) > 0


# -- the seam's measured consequences (the sweep is documented above) ----


async def test_the_measured_full_layout_width_is_exactly_the_tight_one():
    """Both directions, both sides a render of the real screen.

    Too high and the app would document a terminal wider than any panel
    needs; too low and it documents one that clips. The ``-1`` assertion is
    what keeps a widget that quietly grows a column failing *here*, with the
    number in hand.
    """
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS) == 0, (
        f"a marker survives at {MEASURED_FULL_LAYOUT_COLUMNS} -- the measured "
        "width clips, re-measure it"
    )
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1) > 0, (
        f"the screen is already clean at {MEASURED_FULL_LAYOUT_COLUMNS - 1} -- "
        "the measured width is padded, re-measure it"
    )


async def test_the_full_layout_width_covers_a_tight_peg_not_only_the_capture():
    """The market's binding row is wider when the *peg is healthier*.

    ``fmt_price`` renders a gap of $0.0200 at four decimals and a gap under
    $0.01 at six, so ``IMD $0.007100 under FP`` is two columns wider than the
    capture's ``IMD $0.0200 under FP`` -- and at IMD's $0.7074 that band is
    every parity inside ±1.41%, i.e. what a 1:1 bridge looks like when it is
    working. Measured against the capture alone this screen looks clean a
    column early, which is what it did read (142) until 2026-08-12.

    Both payloads are asserted, in opposite directions, so the constant
    cannot be re-measured from the friendlier one by accident.
    """
    capture = _frozen_payload(feed_items=_representative_feed_items())
    tight = _tight_peg(capture)

    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1, payload=capture) == 0, (
        "the capture no longer clears a column early -- if the market's row "
        "stopped moving with the spread, simplify the sweep payload"
    )
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1, payload=tight) > 0, (
        "a tight peg is clean below the measured width -- re-measure it"
    )
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS, payload=tight) == 0


async def test_the_full_layout_is_reachable_at_the_forced_font_size():
    """The prize. ``__main__`` forces 17 pt, which is ~169 columns on a laptop.

    At the 3:2 seam this was one marker short of clean -- the dev-activity
    panel one tier down, permanently, on the font size the app itself picks.
    A "full layout" no user reaches without passing ``--font-size 12`` is not
    a full layout, it is a footnote.

    The width is *derived* from ``_DEFAULT_FONT_SIZE`` (see
    ``LAPTOP_COLUMNS_AT_THE_FORCED_FONT``), so changing what the app forces
    moves what this renders at instead of leaving the claim in the name
    quietly false.
    """
    assert await _widen_markers(LAPTOP_COLUMNS_AT_THE_FORCED_FONT) == 0, (
        f"a panel is still shedding fields at {LAPTOP_COLUMNS_AT_THE_FORCED_FONT} "
        "columns, the width the forced font size actually gives"
    )


async def test_the_two_columns_now_clear_at_the_same_width():
    """No panel is buying width above the rest any more.

    At 3:2 the other five panels were clean from 135 and the activity panel
    only at 176: 41 columns bought for one widget, every one of them wasted
    on a feed that had already stopped needing them. The 7:6 seam closed that
    to one column; the feed's ``FULL_TEXT_WIDTH`` dropping 76 -> 71 re-opened
    it to 10, deliberately, as width a future seam re-cut could spend.

    It is **zero** now, and from the other direction: sizing the activity
    row's wallet and kind cells to the producer's real vocabularies took
    ``activity.FULL_WIDTH`` 66 -> 58, and that panel now clears from 135 --
    eight columns *below* the last one asking for width.

    That last one is ``SurfMarket`` as of 2026-08-12, not ``SurfFeed``: the
    market's binding row is two columns wider against a tight peg than
    against the captured spread, so it clears at 143 where the feed clears at
    142. Pinned **by name** at the bottom, because a count cannot tell the
    two apart and this claim has now been wrong twice in prose.

    The gap may shrink freely; it may not grow, because a growing gap means
    one column is again buying width the other stopped using.

    What this does **not** say: that the seam is optimal. It is one-sided by
    construction -- it subtracts the activity panel, so it can only see the
    rail overshooting the feed, never the feed overshooting the rail, which is
    the direction the screen overshoots in today. The seam table above has
    that number (3 columns, deliberately unspent); see
    ``RECOVERABLE_SEAM_SLACK``.
    """
    assert await _markers_outside_the_activity_panel(
        MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL
    ) == 0
    assert await _markers_outside_the_activity_panel(
        MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL - 1
    ) > 0, "those panels are clean below the measured width -- re-measure it"
    assert (
        MEASURED_FULL_LAYOUT_COLUMNS - MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL
    ) <= RECOVERABLE_SEAM_SLACK, (
        "the gap between the two columns grew: one is buying width the other "
        "has already stopped using. Re-cut the seam for the feed's current "
        f"FULL_TEXT_WIDTH, or lower {RECOVERABLE_SEAM_SLACK} deliberately"
    )
    # ...and the last marker standing is the *market's*, by name -- outside
    # the activity panel, which by then has been clean for eight columns.
    assert await _panels_asking_for_width(MEASURED_FULL_LAYOUT_COLUMNS - 1) == {
        "SurfMarket"
    }, "the panel that sets the full-layout width changed hands -- re-measure"
    assert await _panels_asking_for_width(MEASURED_FULL_LAYOUT_COLUMNS) == set()
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1) == 1
    assert await _markers_outside_the_activity_panel(
        MEASURED_FULL_LAYOUT_COLUMNS - 1
    ) == 1, (
        "the activity panel is the last one asking for width again -- it "
        f"should be clean from {ACTIVITY_FIRST_FULL_TERMINAL}, well below this"
    )
    # Said directly too, on that panel's own rectangle: the arithmetic above
    # implies it, but only as long as both counts stay right.
    assert "‹ widen" not in await _activity_panel(
        MEASURED_FULL_LAYOUT_COLUMNS - 1
    )


def _threaded_sweep_payload() -> dict:
    """``_widen_sweep_payload()``, restaged so its reply actually threads.

    The committed capture cannot exercise threading at all: its one
    ``kind="reply"`` is *older* than the post it follows, so
    ``build_threads`` sorts it first, finds no active root and returns it as
    a root of its own. Nothing is ever indented, and a width sweep against
    that fixture measures the flat list the feed rendered before it grew
    threads -- while quietly reading as though it had covered them.

    Same two real messages, nothing invented: only the reply's ``ts`` moves,
    to ten minutes *after* the post, which is what a reply normally is.
    """
    items = [dict(item) for item in _representative_feed_items()]
    post = next(item for item in items if item["kind"] == "self")
    reply = next(item for item in items if item["kind"] == "reply")
    reply["ts"] = post["ts"] + 600
    return _tight_peg(_frozen_payload(feed_items=[post, reply]))


async def _markers_with_threads_open(width: int, expand: bool) -> int:
    """Whole-screen ``‹ widen`` count at *width*, threads open or shut.

    Expansion is set on the panel's own ``_expanded`` map rather than by
    pressing ``enter``: the keyboard route needs the toggle focused, and a
    sweep that silently failed to focus it would report the collapsed
    number for both halves of the comparison -- which is precisely the
    false green this test exists to rule out. The assertion below that a
    thread really was opened is what keeps that honest.
    """
    from maxpane_dashboard.analytics.surf_feed import build_threads

    payload = _threaded_sweep_payload()
    manager = _FakeManager(payload=payload)
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        feed = screen.query_one(SurfFeed)
        opened = 0
        if expand:
            for root in build_threads(payload["feed_items"]):
                tx = str(root["item"].get("tx_hash") or "")
                if tx and root.get("replies"):
                    feed._expanded[tx] = True
                    opened += 1
            assert opened, (
                "nothing threaded -- the fixture no longer nests a reply and "
                "this sweep would compare the collapsed layout against itself"
            )
            feed._render_view()
            await pilot.pause()
            await pilot.pause()
        return _screen_text(app).count("‹ widen")


@pytest.mark.parametrize("depth", (0, 1, 2, 3))
def test_a_nested_row_is_never_wider_than_the_panel(depth):
    """The claim the full-layout width rests on, asserted where it is decided.

    ``_item_lines`` pays ``depth`` out of the row's own *text budget*
    (``width - _PREFIX_WIDTH - depth``) instead of adding it to the line, so
    a nested row comes out one column narrower than its parent rather than
    one column wider than the panel. That is the whole reason opening a
    thread costs the screen no columns.

    It is asserted on the function rather than on the screen because the
    screen **cannot see the failure**: pay the indent out of the line and
    the row overflows by ``depth`` columns, but ``_cell_fit`` measured the
    chunk against the budget it was given, reports no truncation, and
    ``text-wrap: nowrap`` then has the compositor clip the overflow with no
    ``‹ widen`` and no ``…`` anywhere. A whole-screen marker count is
    identical before and after -- the defect is invisible to exactly the
    kind of test this file is otherwise made of, which is why this one
    measures cells.

    Widths start at 40: below ``30 + depth`` the ``_MIN_TEXT_BUDGET`` floor
    deliberately stops shrinking and lets CSS clip, so the invariant does
    not hold there and is not claimed to.
    """
    from rich.text import Text

    from maxpane_dashboard.widgets.surf.feed import _item_lines

    item = next(
        it for it in _representative_feed_items() if it["kind"] == "reply"
    )
    for width in range(40, 121):
        rendered = _item_lines(item, width, depth)
        assert rendered is not None, (width, depth)
        lines, _clipped = rendered
        widest = max(Text.from_markup(line).cell_len for line in lines)
        assert widest <= width, (
            f"depth {depth} at {width} columns renders a {widest}-cell row -- "
            f"the indent is being added to the line instead of taken out of "
            f"the text budget, and nothing on screen can say so"
        )


@pytest.mark.parametrize("width", (134, 135, 141, 142, MEASURED_FULL_LAYOUT_COLUMNS))
async def test_an_open_thread_costs_the_screen_no_columns(width):
    """The composited half of the same claim, on the real screen.

    The widths straddle the pin and both marker hand-overs below it (142
    market-only, 135 the activity panel dropping out), so a regime that
    moved by even one column on either side of the boundary shows up here.
    Paired with ``test_a_nested_row_is_never_wider_than_the_panel`` above,
    which carries the assertion this one is structurally unable to make.
    """
    assert await _markers_with_threads_open(width, expand=True) == (
        await _markers_with_threads_open(width, expand=False)
    ), width


async def test_the_documented_width_still_covers_the_measured_one():
    """``SURF_FULL_LAYOUT_COLUMNS`` may be generous; it may never be short.

    It read 176 against a measured 152 for one commit, then 152 against a
    measured 142 for another, because reconciling it reaches ``__main__``, the
    README and CLAUDE.md and belongs to a commit of its own each time; both
    now read 142. The direction is what this pins either way: a
    documented width *below* the measured one is a width that clips, which is
    the failure this whole marker system exists to prevent. Kept as an
    inequality on purpose -- it must survive the next re-measurement landing
    one commit ahead of the surfaces that quote it.
    """
    assert SURF_FULL_LAYOUT_COLUMNS >= MEASURED_FULL_LAYOUT_COLUMNS
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS) == 0


async def test_both_lower_rows_split_on_the_same_seam():
    """The columns line up down the screen -- a real, visible property.

    The middle row's seam and the bottom row's are one line, so SIGNALS/DEV
    ACTIVITY sit directly above IDENTITY.MD rather than beside a ragged edge.
    Swept across the seam's own rounding: ``fr`` shares land on different
    integers at different widths, and the two rows must round *together*.
    """
    for width in (MEASURED_FULL_LAYOUT_COLUMNS, 158, 163,
                  LAPTOP_COLUMNS_AT_THE_FORCED_FONT, 176, 201):
        async with _screen_at(width, 48) as (_app, screen, _p):
            feed = screen.query_one(SurfFeed).region
            rail = screen.query_one(_RAIL).region
            market = screen.query_one(SurfMarket).region
            nft = screen.query_one(SurfNft).region
            assert feed.right == rail.x, f"middle row has a gap at {width}"
            assert market.right == nft.x, f"bottom row has a gap at {width}"
            assert feed.right == market.right, (
                f"at {width} the middle row's seam is at {feed.right} and the "
                f"bottom row's at {market.right} -- the columns do not line up"
            )


# -- the blank row between the rail's two panels ------------------------


async def test_a_blank_row_separates_the_signals_from_the_dev_activity():
    """The two rail panels read as one block without it.

    Asserted three ways, because each alone is satisfied by a bug: the
    geometry (one row of gap), the *composited* content of that row (blank
    across the rail's full width -- a gap with something painted in it is not
    a separator), and that the rows on either side are **not** blank, which is
    what stops a panel that merely grew a trailing empty line from passing.
    """
    async with _screen_at(MEASURED_FULL_LAYOUT_COLUMNS, 48) as (app, screen, _p):
        signals = screen.query_one(SurfSignals).region
        activity = screen.query_one(SurfDevActivity).region
        rail = screen.query_one(_RAIL).region

        assert activity.y - signals.bottom == 1, (
            f"the rail's two panels are {activity.y - signals.bottom} rows "
            "apart, expected exactly one blank row between them"
        )

        lines = _screen_text(app).split("\n")

        def _rail_slice(y: int) -> str:
            return lines[y][rail.x : rail.x + rail.width]

        assert _rail_slice(signals.bottom).strip() == "", (
            "the separating row is not blank: "
            f"{_rail_slice(signals.bottom)!r}"
        )
        assert _rail_slice(signals.bottom - 1).strip() != "", (
            "the signals panel already ended in a blank row -- this test is "
            "measuring padding that was there before, not the separator"
        )
        assert _rail_slice(activity.y).strip() != "", (
            "the activity panel starts on a blank row -- the gap is two rows "
            "wide, not one"
        )
        # The separator must not have cost either panel a line.
        assert "BURN" in _screen_text(app)
        assert "DEV ACTIVITY" in _rail_slice(activity.y)


async def test_a_linked_post_advertises_widen_at_the_full_layout_width():
    """A tx-linked post's ``‹ widen`` at the full-layout width is correct,
    not a bug -- do not "fix" this by raising ``SURF_FULL_LAYOUT_COLUMNS``.

    The nonce-13 capture's tx-link token (a URL glued to a 66-char hex hash
    by the post's own punctuation) is 91 columns and cannot be wrapped, so
    ``SurfFeed`` truncates it visibly and says so. The house rule is "never
    clip silently"; this is that rule working.

    The *reason* not to chase it, corrected: this token is 91 columns and
    therefore finite, and the marker does clear -- at 216, pinned below.
    (The earlier wording claimed "no finite width fixes it", which was
    measurably false and would send the next reader to the wrong conclusion.)
    The conclusion is unchanged and rests on different ground: 216 is far past
    the ~169 columns a laptop gets at the forced 17 pt, and the *next* post
    linking a transaction brings its own token of its own length, so no pinned
    width settles the general case.

    It was 194 while the seam was 3:2. Narrowing the feed's share to buy the
    layout 24 columns overall moved it out to 216 -- the one thing the new
    seam costs, and it is a width nobody reaches under either seam.
    """
    assert (
        await _widen_markers(
            MEASURED_FULL_LAYOUT_COLUMNS, payload=_frozen_payload()
        )
        > 0
    )
    assert (
        await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, payload=_frozen_payload())
        > 0
    )
    # Where it actually clears -- measured, not asserted from the comment.
    assert await _widen_markers(215, payload=_frozen_payload()) > 0
    assert await _widen_markers(216, payload=_frozen_payload()) == 0


# -- the hero's own width tiers (final-review I-2) -----------------------

from maxpane_dashboard.widgets.surf.hero import (  # noqa: E402
    WIDEN_HINT as HERO_WIDEN_HINT,
)


def _region_text(app, widget) -> str:
    """Composited text of just *widget*'s rectangle on the screen.

    ``_screen_text`` is the whole screen, which is useless for "nothing in
    the hero is truncated": the feed below it legitimately renders ``…`` on
    an over-long token. Slicing the compositor's strips to the widget's own
    region keeps the claim about the widget it is made about.
    """
    strips = app.screen._compositor.render_strips()
    region = widget.region
    # Rows of the region that are actually ON the composited screen.
    #
    # A widget's region can extend past the last strip -- a body taller than
    # its terminal, a panel a column has scrolled below the fold -- and this
    # used to index ``strips[y]`` unguarded and raise ``IndexError``. That is
    # the wrong failure for a helper whose whole job is "what does the user
    # see here": the answer for an off-screen row is *nothing*, and a caller
    # asking whether a line is clipped should get an empty answer rather than
    # a traceback. Found by a height sweep at 34 rows, where the mainnet
    # payload pushes the rail's lower panels off the end.
    return "\n".join(
        "".join(seg.text for seg in strips[y])[region.x : region.x + region.width]
        for y in range(region.y, min(region.y + region.height, len(strips)))
        if y >= 0
    )


async def _hero_text(width: int) -> str:
    """Composited text of the hero row alone at *width* columns."""
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfHero))


def _hero_fields(text: str) -> set[str]:
    """The hero's content words, free of box drawing and padding.

    Two renders at different widths differ in border length and padding even
    when they show the same fields, so a raw string compare would always
    differ. This reduces a render to what it actually *says*.
    """
    box_drawing = "─│┌┐└┘┬┴├┤┼"
    scrubbed = "".join(" " if ch in box_drawing else ch for ch in text)
    return set(scrubbed.split())


async def test_the_hero_cuts_neither_a_number_nor_a_title_at_the_pinned_width():
    """I-2, re-measured against LAUNCHPAD/FLOW/BURN/SUPPLY (2026-08-24).

    A truncated *word* is a shortened word; a truncated *number* still reads
    as a number, and a truncated panel title reads as a different panel. The
    hero sheds whole fields instead, so at the pinned width every title and
    every quantity arrives intact. The list below is what the real screen
    renders at ``SURF_FULL_LAYOUT_COLUMNS`` today, swept after Task 12 wired
    the ``launchpad_*`` keys through -- it is NOT carried over from the
    POOL/LP-era assertions this test used to make, which were measured
    against a row whose first two boxes still read ``no read yet``.
    """
    hero = await _hero_text(SURF_FULL_LAYOUT_COLUMNS)

    for whole in (
        # The titles. LAUNCHPAD and FLOW carry the launchpad tier's own
        # slower clock; BURN and SUPPLY read the fast tier and carry none,
        # which is the distinction the clock exists to make visible.
        "LAUNCHPAD · 01:14", "FLOW · 01:14", "BURN", "IMD SUPPLY",
        # The numbers, whole and comma-grouped.
        "146 coins", "73 creators", "4,683 swaps", "673 traders",
        "2.4187 ETH", "2,376,732 IMD", "READY",
        # This width reaches the *widest* tier, so the fields the narrow
        # tiers compress are all here in full, with the words that scope
        # them ("24h", "acc"/"stg", "observed") intact.
        "36 new · 24h", "acc 1.2K · stg 45.0", "burned 15,745 observed",
    ):
        assert whole in hero, f"{whole!r} did not survive the hero row whole"

    # The retired POOL and LP boxes are gone from the row at every width,
    # this one included. Their fields were dropped, not moved into a narrower
    # tier of the surviving boxes, so none of them may reappear here: the pool
    # figure lives in the IMD MARKET panel, the decoy count on the signals
    # rail, and the owner check on the title bar.
    for retired in ("owner ✓", "of 38", "WETH", "$548.7K", "· L "):
        assert retired not in hero, (
            f"{retired!r} is back in the hero -- POOL/LP were retired, and "
            "their information belongs to the market panel, the signals rail "
            "and the title bar now"
        )

    # The general statement the list above is a sample of: at the pinned
    # width the hero truncates nothing at all.
    assert "…" not in hero, f"something in the hero is still ellipsised:\n{hero}"


async def test_the_hero_spends_new_columns_in_the_documented_order():
    """Widening restores the compressed fields at each tier boundary.

    Re-measured against LAUNCHPAD/FLOW/BURN/SUPPLY once Task 12 wired the
    ``launchpad_*`` keys through: swept width by width (76-100 and 91-127,
    see task-12-report.md), the short<->long boundary the old test pinned at
    91/99 vs. 119/127 **did not move** -- 118 is still the last short-form
    width and 119 the first long one, so those four widths are kept rather
    than re-chosen.

    What *did* move is the relationship between ``minimal`` and ``tight``.
    They rendered identical text while the row was POOL/LP/BURN/SUPPLY, and
    the old version of this test asserted exactly that. They no longer do:
    LAUNCHPAD and FLOW carry the launchpad tier's own clock, and the
    2026-08-24 fix round narrowed it with the tier instead of dropping it
    (``LAUNCHPAD · 01:14`` -> ``LAUNCHPAD 01:14`` -> ``LAUNCHPAD slow``), so
    the two narrow tiers now differ by precisely one field -- and that field
    is the one that stops a ten-minute-old number from sitting under a
    this-second clock. It is asserted here rather than left to the widget's
    own tests because this is where the *screen* proves the marker survives
    down to the narrowest row anybody can render.

    A fourth tier used to sit above these three, holding the retired LP box's
    raw ``· L <liquidity>``. It went with the box. ``wide`` below is therefore
    not a distinct tier -- it is kept in the sweep precisely to assert that
    extra columns now buy *nothing*, which is the claim that would quietly go
    untested if the width were simply deleted.
    """
    narrow = await _hero_text(91)     # minimal tier
    tight = await _hero_text(99)      # tight tier
    mid = await _hero_text(119)       # compact tier
    wide = await _hero_text(127)      # still compact: there is nothing wider

    # The retired boxes' fields are absent at every width, the widest
    # included -- there is no tier that brings either box back.
    for text in (narrow, tight, mid, wide):
        assert "· L " not in text
        assert "owner ✓" not in text
        assert "e+" not in text, "a raw uint128 is rendering somewhere in the hero"

    # The slow clock narrows with the tier and never disappears: it is what
    # tells a ten-minute-old LAUNCHPAD/FLOW number from a this-second
    # BURN/SUPPLY one, and dropping it at the narrow tiers was the bug the
    # 2026-08-24 fix round closed.
    assert "LAUNCHPAD slow" in narrow and "FLOW slow" in narrow
    assert "01:14" not in narrow, "the narrowest tier has no room for a stamp"
    assert "LAUNCHPAD 01:14" in tight and "FLOW 01:14" in tight
    assert "· 01:14" not in tight, "tight drops the separator, not the stamp"
    assert "LAUNCHPAD · 01:14" in mid and "FLOW · 01:14" in mid

    # ...and that clock is the *only* thing separating the two narrow tiers
    # for this payload: nothing else in the four boxes branches on `tight`
    # vs `minimal` beyond the shared `_short()` check. Asserted rather than
    # assumed, so a body that starts differentiating them turns this into a
    # real two-tier check instead of a silently weakened one.
    assert _hero_fields(narrow) - {"slow"} == _hero_fields(tight) - {"01:14"}

    # Past `compact`, extra columns buy nothing: the two widest renders agree
    # field for field. Without this the collapsed ladder would be untested.
    assert _hero_fields(mid) == _hero_fields(wide)

    # The observed burn: a whole short form, never cut digits.
    assert "burn 15,745" in narrow
    assert "burn 15,745" in tight
    assert "burned 15,745 observed" in mid
    for text in (narrow, tight, mid):
        assert "burned 15,74…" not in text

    # LAUNCHPAD's 24h window and BURN's accrued/staged pair are the same
    # shape: a compressed form below `compact`, the full connective words
    # (`24h`, `acc`, `·`, `stg`) at and above it.
    assert "36 new" in narrow and "24h" not in narrow
    assert "36 new" in tight and "24h" not in tight
    assert "36 new · 24h" in mid
    assert "1.2K/45.0" in narrow and "stg" not in narrow
    assert "acc 1.2K · stg 45.0" in mid

    # Nothing is truncated at any of the four widths.
    for text in (narrow, tight, mid, wide):
        assert "…" not in text


async def test_the_hero_marker_is_dark_on_every_terminal_anyone_owns():
    """The marker fires only when the *narrowest* tier cannot fit.

    Bolting a bare ``‹ widen`` onto the hero would leave it permanently lit
    -- back when the row was shared, the full copy needed ~220 columns,
    past the ~169 a laptop gets at the forced 17 pt. A marker that is on
    everywhere means nothing (the trap ``widgets/surf/signals.py``
    documents). Tying it to the narrowest tier keeps it dark, and the
    full-width row lowers the floor a long way below any terminal this
    dashboard is usable in at all.

    **87 columns since 2026-08-24**, seven above the 80 measured for
    POOL/LP/BURN/SUPPLY, and the move is Task 12's own doing rather than a
    copy edit: until the screen dispatched the ``launchpad_*`` keys, the
    LAUNCHPAD and FLOW boxes had nothing to render and sat at ``no read
    yet`` under a bare title, so the width they were measured at was the
    width of an unwired row. Wired, the binding line is LAUNCHPAD's own
    ``minimal``-tier title ``LAUNCHPAD slow`` (14 columns, the narrow-tier
    stand-in for its clock), which needs the box 14 wide and gets it at 87.
    Swept 76-100 rather than probed at the boundary: 76-86 light exactly one
    or two markers, 87-100 none.
    """
    assert HERO_WIDEN_HINT == "‹ widen"

    for width in (87, 100, SURF_FULL_LAYOUT_COLUMNS, 143, 169, 200, 240):
        assert HERO_WIDEN_HINT not in await _hero_text(width), (
            f"the hero advertises a loss at {width} columns"
        )

    # ...and it is not merely unreachable: one column narrower the LAUNCHPAD
    # box can no longer fit its own title at any tier, and says so.
    assert HERO_WIDEN_HINT in await _hero_text(86)


# -- the activity panel's own width tiers (final-review I-1) -------------

from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    FULL_WIDTH as ACTIVITY_FULL_WIDTH,
)
from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    _tier_for as _activity_tier_for,
)
from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    WIDEN_HINTS as ACTIVITY_WIDEN_HINTS,
)

#: The unknown-counterparty window as ``_fmt.long_addr`` renders the real
#: unlabelled LP-fee destination. Spelled once here: every assertion below is
#: about *this exact string* surviving whole, because the classic
#: first-6/last-4 short form collides with a live spoof (see the module
#: docstring of ``widgets/surf/activity.py``).
_ADDR_WINDOW = "0x61CC704c…73f14E"

#: The hints, as **test-local literals**. Asserting
#: ``ACTIVITY_WIDEN_HINTS[tier] in text`` instead would be satisfied by an
#: empty hint -- i.e. by a widget that sheds the column in exactly the
#: silence these tests exist to catch. Proven: emptying the widget's table
#: left every assertion green until this literal was introduced.
_ACTIVITY_HINTS = {
    "compact": "‹ widen for amounts",
    "minimal": "‹ widen: time, kind, ETH",
}


def test_the_activity_hints_are_the_strings_this_file_asserts_on():
    """Pin the literals above to the widget's own table, both directions."""
    assert {
        tier: ACTIVITY_WIDEN_HINTS[tier] for tier in _ACTIVITY_HINTS
    } == _ACTIVITY_HINTS
    # The widest layout sheds nothing, so it advertises nothing.
    assert ACTIVITY_WIDEN_HINTS["full"] == ""
    assert set(ACTIVITY_WIDEN_HINTS) == set(_ACTIVITY_HINTS) | {"full"}


async def _activity_panel(width: int) -> str:
    """Composited text of the activity panel's own rectangle at *width*.

    The panel's rectangle, not the whole screen: the NFT panel one row below
    it renders ``38 transfers/24h``, so a whole-screen ``"transfer" in text``
    -- which is what this file used to assert for "the kind column is
    present" -- was true at every width, including the ones where the kind
    column had been shed. Both panels are always composited now, so the
    contamination is permanent and the fix is to stop reading the screen when
    the claim is about one panel.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfDevActivity))


#: The two quantities the captured signal details carry, spelled here because
#: every partial form of them below is derived from these strings rather than
#: typed out. ``_sample_data`` builds the details that contain them.
_SIGNAL_QUANTITIES = ("114,367", "15,745")


async def _signals_panel(width: int) -> str:
    """Composited text of the signals panel's own rectangle at *width*."""
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfSignals))


async def test_a_signal_detail_is_never_cut_through_a_number():
    """``mint 114,…`` is the defect; ``mint …`` is the fix (final review I-3).

    A detector detail is free text quoted from the announce channel, so it is
    truncated with a visible ``…`` at every width -- that part is deliberate
    and documented, and it is why this panel's ``‹ widen`` deliberately does
    *not* light for it. What is not allowed is where the cut lands: at 100
    columns it fell inside the bridge row's ``114,367`` and the burn row's
    ``15,745``, putting ``mint 114,…`` and ``burn 15,…`` on screen. A reader
    cannot tell 114 thousand from 114 million there, and nothing marks it.

    The house rule is to shed a whole field instead, which is exactly the fix
    the hero took for ``burned 15,74…``. Swept across every width where the
    panel is narrow enough to cut, so it pins the *rule* and not one width.

    Positively bound too: the details are still rendered and still truncated
    here, so a widget that stopped showing details at all would not pass.
    """
    import re

    # 92 is the narrowest width where the bridge row still has a detail budget
    # at all (below it the head renders alone, which is the panel's own
    # documented floor and not a cut).
    for width in range(92, 130):
        panel = await _signals_panel(width)
        assert "…" in panel, f"nothing is truncated at {width} -- widen the sweep"
        assert re.search(r"BRIDGE STAGE FIRED .* · \S", panel), (
            f"the bridge row lost its detail entirely at {width} columns"
        )
        for quantity in _SIGNAL_QUANTITIES:
            for cut in range(2, len(quantity)):
                partial = f"{quantity[:cut]}…"
                assert partial not in panel, (
                    f"{partial!r} at {width} columns: the detail was cut "
                    f"through {quantity}, which reads as a different number"
                )


async def test_a_whole_quantity_still_survives_where_it_fits():
    """The other half: backing the cut off must not swallow an intact number.

    Without this, dropping every trailing digit run unconditionally would
    pass the test above and quietly cost the reader a figure that fitted.

    ``burn`` is ``ok`` in this fixture, so quiet-collapse folds it away and
    its ``15,745`` detail never reaches a pixel at all -- that is the panel
    working as designed (``widgets/surf/signals.py``'s Quiet-collapse
    section), not the truncation this test guards against. ``bridge`` is
    ``fired`` and never folds, so its ``114,367`` is the quantity that stays
    on its own line at every width; the full width is where it must survive
    whole.
    """
    wide = await _signals_panel(MEASURED_FULL_LAYOUT_COLUMNS)
    assert "114,367" in wide, (
        "the bridge row's quantity no longer survives whole at the full width"
    )


async def _activity_usable_columns(width: int) -> int:
    """Columns the activity log really has to spend, from a real render.

    This is the number ``_tier_for`` selects on -- ``RichLog``'s scrollable
    content region, i.e. the rail minus the panel's padding, the log's padding
    and the log's permanent scrollbar gutter -- not the panel's region width.
    """
    from textual.widgets import RichLog

    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        panel = screen.query_one(SurfDevActivity)
        return panel._log_width(panel.query_one("#surf-activity-log", RichLog))


#: The narrowest terminal at which the activity row fits whole -- i.e. at
#: which the ETH amount column survives. Derived below from the rail formula
#: and the widget's own ``FULL_WIDTH``, then pinned against a real render, so
#: it is not a third literal to keep in step by hand.
ACTIVITY_FIRST_FULL_TERMINAL = 135


def test_every_list_row_in_the_fixture_matches_the_frozen_row_shape():
    """Every list-of-dict row here carries exactly ``SURF_ROW_KEYS``.

    The root cause of the 2026-08-23 branch's one Critical finding: this
    file named ``SURF_ROW_KEYS`` nowhere at all, so nothing compared its
    fixture rows against the contract they claim to be instances of. The
    launchpad rows still carried the pre-branch ``change_1h_pct``/
    ``swaps_1h`` and had no ``swaps_all`` -- so ``24H%``, ``SW 24H`` and
    ``SW ALL`` rendered ``--`` in *every* screen test in this module, and
    the whole Task 1/7/11 rename could be reverted with the suite green.
    The feed rows had the same drift in the other direction, missing
    ``to_addr``, ``label`` and ``value_eth``.

    Cross-layer for the same reason
    ``test_the_activity_fixture_speaks_the_producers_vocabularies`` below
    is, and modelled on it: this file may import ``data/`` (the widgets may
    not), and without that import the fixture is free to invent a row shape
    the pipeline never emits -- which is exactly what it did.

    Both directions, and mechanically over *every* list key rather than a
    hand-typed three: a missing field renders as a dash and a stray one is
    simply never read, and both read as a passing test. Walking
    ``_sample_data()`` rather than naming keys is what makes a fourth
    list-of-dict payload covered the day it is written -- the same reason
    ``_ALL_WIDGET_CLASSES`` above is derived rather than typed out.
    """
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS

    sample = _sample_data()
    rows_seen = 0
    for key, value in sample.items():
        if not isinstance(value, list):
            continue
        if not value or not all(isinstance(row, dict) for row in value):
            continue
        assert key in SURF_ROW_KEYS, (
            f"the fixture carries a list-of-dict payload {key!r} that "
            "SURF_ROW_KEYS does not declare a row shape for"
        )
        declared = set(SURF_ROW_KEYS[key])
        for index, row in enumerate(value):
            assert set(row) == declared, (
                f"{key}[{index}] is missing "
                f"{sorted(declared - set(row))} and carries stray "
                f"{sorted(set(row) - declared)} -- the screen tests are "
                "measuring a row shape the pipeline never emits"
            )
            rows_seen += 1

    # The walk itself has to be able to fail: a fixture that stopped
    # carrying list payloads (or a filter that stopped matching them) would
    # loop zero times and pass.  Every declared row shape must be exercised.
    assert set(SURF_ROW_KEYS) <= {
        key for key, value in sample.items() if isinstance(value, list)
    }, (
        f"declared row shapes {sorted(set(SURF_ROW_KEYS))} are not all "
        "present in the fixture -- one of them is unmeasured here"
    )
    assert rows_seen >= len(SURF_ROW_KEYS)


def test_the_activity_fixture_speaks_the_producers_vocabularies():
    """The payload every width sweep above renders must be a real payload.

    Cross-layer on purpose: this file may import ``data/`` (the widget may
    not), and without that import the fixture is free to invent labels the
    pipeline never emits -- which is exactly what it did. ``surfsurf.eth`` and
    ``frenpet.eth`` sat here from WP5 until 2026-08-10, so every width
    conclusion drawn from this payload was drawn against a 12-column label
    where production sends three, and the manager's own sender re-check
    (``surf_manager.DEV_WALLETS``, keyed ``dev``/``ops``) silently matched
    nothing and skipped.

    Both directions: the fixture may only use labels the producer emits, and
    it must exercise *every* one of them, so a vocabulary that grows a third
    wallet cannot go unrendered by the sweeps.

    The ``kind`` column is the same claim one cell to the right, and it had
    the same defect: the LP row was spelled ``"LP"`` where the producer emits
    ``"lp"``. Harmless on width (two columns either way) but every sweep in
    this file was rendering a kind the pipeline never emits -- and the
    widget's only kind branches are ``"dust"`` and ``"transfer"``, both
    lower-case, so a case-folding change would have gone uncaught here.
    One direction only: ``DEV_TX_KINDS`` has seven members and this payload
    exists to measure widths, not to enumerate them -- ``tests/widgets/
    test_surf_widgets_b.py::test_activity_cells_are_sized_from_the_producers
    _own_vocabularies`` renders every one of them.
    """
    from maxpane_dashboard.data.surf_client import (
        DEV_TX_KINDS,
        _DEV_WALLET_LABELS,
    )
    from maxpane_dashboard.data.surf_manager import DEV_WALLETS

    kinds = {row["kind"] for row in _widen_sweep_payload()["dev_activity"]}
    assert kinds <= set(DEV_TX_KINDS), (
        f"the fixture sends kinds {sorted(kinds - set(DEV_TX_KINDS))}, which "
        "the client never emits"
    )

    produced = set(_DEV_WALLET_LABELS.values())
    used = {row["wallet_label"] for row in _widen_sweep_payload()["dev_activity"]}
    assert used <= produced, (
        f"the fixture sends wallet labels {sorted(used - produced)}, which "
        "the client never emits -- the width sweeps are measuring a payload "
        "production does not produce"
    )
    assert used == produced, (
        f"the fixture never renders {sorted(produced - used)}: a label the "
        "producer emits is missing from every width sweep in this file"
    )
    # ...and the manager's defence-in-depth re-check really does key on these
    # same names, which is the half an ENS-spelled label quietly bypassed.
    assert set(DEV_WALLETS) == produced


async def test_the_activity_rail_reaches_full_width_well_below_the_pinned_width():
    """Where the rail hits ``FULL_WIDTH`` -- 135 now, and 152 once.

    The rail is ``6fr`` of the 7:6 seam, so it gets the columns the feed's
    ``floor(7W/13)`` leaves -- ``ceil(6W/13)`` -- and the log spends five of
    them on two paddings and a permanent scrollbar gutter. That makes
    ``ceil(6W/13) - 5`` usable columns. The formula is the stable part and is
    swept first; only where it crosses ``FULL_WIDTH`` moved.

    It used to cross at exactly 152 (``ceil(912/13) - 5 == 66 ==
    ACTIVITY_FULL_WIDTH``), and that identity was the app's whole documented
    floor. Sizing the wallet cell to the producer's two-member vocabulary and
    the kind cell to its widest member took the row 66 -> 58, so the crossing
    moved down to 135 and this panel stopped being what sets the floor. Both
    ends are pinned: a row that quietly grows a column again moves the
    crossing back up and reddens here with the number in hand.

    ``widgets/surf/activity.py`` documented the slope as ``0.46 * terminal -
    4``, i.e. 62/67/74 at 143/152/169 against the real 61/66/73 -- an
    off-by-one that also hid the identity (final review I-2). The arithmetic
    below is written out independently of the widget so a widget that starts
    lying agrees with nothing.
    """
    from math import ceil

    for terminal in (120, ACTIVITY_FIRST_FULL_TERMINAL, 143, 150,
                     MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL,
                     MEASURED_FULL_LAYOUT_COLUMNS, 160,
                     LAPTOP_COLUMNS_AT_THE_FORCED_FONT, 200):
        assert await _activity_usable_columns(terminal) == ceil(6 * terminal / 13) - 5, (
            f"the rail's usable width at {terminal} columns is not "
            "ceil(6W/13) - 5 any more -- re-derive the note in "
            "widgets/surf/activity.py::_tier_for before trusting it"
        )

    # Where it crosses, both directions, against the widget's own constant.
    assert await _activity_usable_columns(ACTIVITY_FIRST_FULL_TERMINAL) == (
        ACTIVITY_FULL_WIDTH
    ), "the rail no longer hands the panel exactly its full row at 135"
    assert await _activity_usable_columns(ACTIVITY_FIRST_FULL_TERMINAL - 1) == (
        ACTIVITY_FULL_WIDTH - 1
    ), "the width below no longer falls one column short -- re-measure"
    # ...and 135 really is the *first* such width, not merely one of them.
    assert ACTIVITY_FIRST_FULL_TERMINAL == min(
        w for w in range(60, 260) if ceil(6 * w / 13) - 5 >= ACTIVITY_FULL_WIDTH
    )
    # The panel is therefore clean well before the screen as a whole is, which
    # is the shape this change produced and the reason the floor is now the
    # feed's to set.
    assert ACTIVITY_FIRST_FULL_TERMINAL < MEASURED_FULL_LAYOUT_COLUMNS

    # ...and the note a reader lands on quotes the widths that were measured.
    # Derived from the renders above, so re-deriving the formula wrong a second
    # time reddens this instead of shipping.
    doc = " ".join(_activity_tier_for.__doc__.split())
    assert "0.46 * terminal - 4" not in doc, (
        "the rail's usable width is ceil(6W/13) - 5; 0.46W - 4 is the "
        "approximation that put 67 where the measured 66 was"
    )
    for terminal in (ACTIVITY_FIRST_FULL_TERMINAL, 143,
                     MEASURED_FULL_LAYOUT_COLUMNS,
                     LAPTOP_COLUMNS_AT_THE_FORCED_FONT):
        usable = await _activity_usable_columns(terminal)
        assert f"{usable} at {terminal}" in doc, (
            f"_tier_for's note does not say the rail has {usable} columns at "
            f"{terminal}, which is what the screen renders"
        )


async def test_the_activity_panel_shows_every_column_at_its_own_clean_width():
    """The positive half: at ``FIRST_CLEAN_WIDTH`` nothing is shed and nothing
    is advertised. Without this, the tests below could be satisfied by a
    widget that simply always renders its narrowest tier."""
    panel = await _activity_panel(FIRST_CLEAN_WIDTH)
    assert _ADDR_WINDOW in panel
    assert "0.310 ETH" in panel          # the amount column is present...
    assert "transfer" in panel           # ...and so is the kind column
    # ...and the HH:MM half of the stamp, which the minimal tier sheds. The
    # hour itself is local (``_fmt.hhmm``), so the shape is what is asserted.
    import re

    assert re.search(r"\d\d-\d\d \d\d:\d\d", panel), (
        "the stamp lost its HH:MM half at the panel's own clean width"
    )
    assert "‹ widen" not in panel        # ...so there is nothing to advertise


async def test_the_activity_panel_never_drops_the_amount_column_in_silence():
    """One column below the crossing the amount goes -- and is advertised.

    Measured on the real screen: at ``ACTIVITY_FIRST_FULL_TERMINAL - 1`` the
    rail is one column short of the full row, the ``0.310 ETH`` amount cannot
    fit, and ``RichLog(wrap=False)`` shrinks the line at write time with no
    ``…`` and nothing in the title. Shedding the column is correct; shedding
    it in silence is the defect -- a user comparing a 180-column window with a
    narrow one otherwise sees two different truths about one tx.

    This was asserted at 150 while the full row needed 66 columns of rail.
    The row needs 58 now, so 150 is comfortably inside the *clean* band and
    the boundary that means anything is the crossing itself.
    """
    panel = await _activity_panel(ACTIVITY_FIRST_FULL_TERMINAL - 1)
    assert "0.310 ETH" not in panel, (
        f"the amount fits after all at {ACTIVITY_FIRST_FULL_TERMINAL - 1} "
        "columns -- re-measure FULL_WIDTH"
    )
    # ...and one column wider it does, which is what makes this a boundary
    # rather than a width that happens to sit inside a wide marked band.
    assert "0.310 ETH" in await _activity_panel(ACTIVITY_FIRST_FULL_TERMINAL)
    assert _ACTIVITY_HINTS["compact"] in panel, (
        "the amount column vanished without the title saying so"
    )
    # The columns that were *not* shed are still there, whole.
    assert _ADDR_WINDOW in panel
    assert "transfer" in panel


async def test_the_activity_panel_names_the_columns_the_rail_costs_it():
    """120 columns is the minimal tier: address only, and the title says so.

    The rail is the panel's whole width budget, so a narrow terminal takes
    the time and kind columns as well as the amount. What is not negotiable
    is that the title names which fields went.

    This used to be asserted at **143**, then at **120**, and each move was
    a real widening of the row's reach. At the 3:2 seam a 143-column terminal
    put the panel in its *minimal* tier; 7:6 took that to compact. Sizing the
    wallet and kind cells to the producer's vocabularies took the compact row
    46 -> and the minimal band down again, so the tier only appears at 108.
    Both ends are pinned so the band cannot silently widen back.
    """
    panel = await _activity_panel(108)
    assert _ACTIVITY_HINTS["minimal"] in panel
    assert "0.310 ETH" not in panel and "transfer" not in panel
    assert _ADDR_WINDOW in panel

    # The tier the narrower cells bought back: 109 is no longer minimal, and
    # neither is 120, which the old row spent entirely on padding.
    for wider_width in (109, 120):
        wider = await _activity_panel(wider_width)
        assert _ACTIVITY_HINTS["minimal"] not in wider, (
            f"{wider_width} columns is back in the minimal tier"
        )
        assert _ACTIVITY_HINTS["compact"] in wider
        assert "transfer" in wider


async def test_the_narrow_activity_panel_never_cuts_the_poisoning_window():
    """80 columns leaves the log 27 usable -- and the window must survive.

    This is the correctness half of I-1, not a cosmetic one. Cut to its first
    six characters both live spoof addresses render ``0xF308``, which is the
    exact collision the wide ``0x``+8+``…``+6 window exists to prevent. The
    panel must shed whole fields -- time, kind, amount, and here the wallet
    label as well -- before it touches a single hex digit, and say so.

    At this width the panel is 30 columns and cannot fit the 24-column
    descriptive hint beside its title, so it falls back to the bare marker
    (``activity.SHORT_HINT``). That fallback exists because of this layout:
    the panel's old ``3fr`` slot never got this narrow.
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    panel = await _activity_panel(80)
    assert _ADDR_WINDOW in panel, "the anti-poisoning window was cut to fit"
    assert SHORT_HINT in panel, "three columns went with nothing said"
    # The fields that were shed to pay for it, and nothing half-rendered.
    assert "0.310 ETH" not in panel


async def test_the_poisoning_window_survives_every_terminal_the_rail_allows():
    """80 is not the bottom. Swept to a terminal narrower than the window.

    The rail hands this panel ``ceil(6W/13) - 5`` columns, so the test above
    measured one comfortable point of a curve that keeps falling. Below 61
    the row -- ``MM-DD`` + gap + window, 24 columns, the wallet cell already
    gone -- no longer fits the 23 the rail gives at W=59-60, and
    ``RichLog(wrap=False)`` narrowed it at write time with no ``…``, no
    marker and nothing in the title:

    * **60 columns** rendered ``0x61CC704c…73f14`` -- one hex digit short;
    * **50** rendered ``0x61CC704c…7``;
    * **40** rendered ``0x61CC7``, the ``…`` gone too, so a truncated
      address no longer looked truncated at all.

    At a log width of 13 the live spoof pair both render ``0xF308`` -- the
    single collision this panel's wide window exists to prevent, arrived at
    by the panel itself.

    The assertion is on every hex run in the panel's own rectangle rather
    than on the window as a literal, because a *prefix* is the defect and
    ``_ADDR_WINDOW not in panel`` cannot see one.
    """
    import re

    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    # ``*`` and not ``+``: the narrowest clip left a bare ``0x`` behind,
    # which a ``+`` quantifier does not match at all.
    hex_run = re.compile(r"0x[0-9A-Fa-f…]*")
    withheld = 0
    for width in range(34, 82):
        panel = await _activity_panel(width)
        for run in hex_run.findall(panel):
            assert run == _ADDR_WINDOW, (
                f"{run!r} at {width} columns: the anti-poisoning window was "
                "cut to make the row fit"
            )
        assert "no recent activity" not in panel, (
            f"{width} columns reports the dev wallets quiet; they are not"
        )
        if _ADDR_WINDOW not in panel:
            withheld += 1
            assert SHORT_HINT in panel, (
                f"the rows went at {width} columns with nothing said at all"
            )
    # Both branches really are exercised: the sweep straddles the width where
    # the window stops fitting, so neither assertion above is vacuous.
    assert 0 < withheld < 48, (
        f"{withheld} of 48 widths withheld their rows -- re-derive the sweep"
    )


async def test_the_activity_panel_is_never_silent_about_a_shed_column():
    """A shed column is announced at *every* width, not merely most of them.

    The marker normally goes beside the title, and ``_set_title`` drops it
    when the title bar itself is too narrow to hold it -- a Static with no
    ``text-overflow`` wraps instead, pushing a row out of the log. That was
    accepted while the band was unreachable; in the right rail it is not.
    At 46 and 50 columns the rail leaves the log 17 and 19, narrow enough
    that the ``MM-DD`` date goes, and the title bar (19 and 21 columns) can
    hold neither the descriptive hint nor the 7-column bare one. Three
    columns of date vanished with nothing said anywhere on the panel.

    The fallback is the one the withheld-rows branch already uses: say it in
    the log instead. Swept against the amount column, which is the last
    thing to go, so the two branches are "everything is here, and nothing is
    claimed" and "something went, and it is claimed".
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    # From 24: the rail leaves the log ``ceil(6W/13) - 5`` columns, which is
    # exactly ``len(SHORT_HINT)`` there and less below it -- a terminal that
    # cannot render the seven columns of the marker itself is past the point
    # where any wording helps, and the rows are already withheld there
    # (``test_the_poisoning_window_survives_every_terminal_the_rail_allows``).
    clean = 0
    for width in sorted(set(range(24, 146, 5)) | {46, 50, 55, 80, 108, 134,
                                                  135, 143}):
        panel = await _activity_panel(width)
        if "0.310 ETH" in panel:
            clean += 1
            assert SHORT_HINT not in panel, (
                f"{width} columns shows every column and still advertises a "
                "loss -- a marker that is on everywhere means nothing"
            )
        else:
            assert SHORT_HINT in panel, (
                f"a column went at {width} columns with nothing said on the "
                f"panel at all:\n{panel}"
            )
    assert clean, "the sweep never reaches a width where nothing is shed"


# -- the NFT panel's own width tiers -------------------------------------
#
# ``SurfNft`` was the one surf widget with no marker machinery at all. It did
# not need any while it was the sole child of ``#bottom-row`` at ``1fr``; the
# three-row restructure put it beside the market at ``2fr`` of a 3:2 split, so
# it sees ~``0.4 * W - 4`` columns against the 46 its stats row needed and
# started silently ellipsising ``dev holds 3`` -- and, further down, cutting
# ``38 transfers/24h`` into ``38 transfers/24…``, a number with a different
# unit. ``text-overflow: ellipsis`` renders the ``…``; nothing put a word in
# the title, which is the half of the contract that names what went.
#
# **The rows were then rearranged, and every number below moved with them.**
# The written count folded into the stats row and the dev holdings
# took a row of their own (``dev holds 3 identities``), so the stats row is
# 49 columns rather than 46 and the ladder sheds ``1/2000 written`` first,
# ``transfers/24h`` second. Two consequences these tests pin: the panel's own
# clean width went 107 -> 113 (three more columns on its widest row, at ~0.46
# panel columns per terminal column), and ``dev holds`` is now present at
# *every* width -- an assertion that it is absent no longer says anything
# about a tier.

from maxpane_dashboard.widgets.surf.nft import (  # noqa: E402
    SHORT_HINT as NFT_SHORT_HINT,
    WIDEN_HINTS as NFT_WIDEN_HINTS,
)

#: The NFT hints as **test-local literals**, for the reason ``_ACTIVITY_HINTS``
#: is one: ``NFT_WIDEN_HINTS[tier] in panel`` is satisfied by an *empty* hint,
#: i.e. by exactly the silent shed these tests exist to catch. ``SHORT_HINT``
#: is additionally a **prefix** of both, so ``SHORT_HINT in panel`` cannot tell
#: the descriptive hint from the bare fallback -- every assertion below names
#: the whole string it means, and the two are asserted against each other.
_NFT_HINTS = {
    "compact": "‹ widen for /2000 written",
    "minimal": "‹ widen: 24h /2000",
}


def test_the_nft_hints_are_the_strings_this_file_asserts_on():
    """Pin the literals above to the widget's own table, both directions."""
    assert {tier: NFT_WIDEN_HINTS[tier] for tier in _NFT_HINTS} == _NFT_HINTS
    assert NFT_WIDEN_HINTS["full"] == "", "the widest tier sheds nothing"
    assert set(NFT_WIDEN_HINTS) == set(_NFT_HINTS) | {"full"}
    assert NFT_SHORT_HINT == "‹ widen"
    # The prefix relationship this file has to work around, stated once.
    for hint in _NFT_HINTS.values():
        assert hint.startswith(NFT_SHORT_HINT)


async def _nft_panel(width: int) -> str:
    """Composited text of the NFT panel's own rectangle at *width*.

    The panel's rectangle, not the whole screen: ``38 transfers/24h`` also
    appears nowhere else, but ``‹ widen`` appears in up to three other titles,
    so a whole-screen assertion about *this* panel's marker would be satisfied
    by the activity panel's.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfNft))


async def test_the_nft_panel_shows_every_figure_at_its_own_clean_width():
    """The positive half: nothing shed, nothing cut, nothing advertised.

    113 is the measured boundary -- one column narrower the stats row no
    longer fits -- so this also pins that the panel is clean at every width
    the dashboard is actually meant to run at, the pinned one (143 today,
    read from the constant rather than retyped) included.
    Without it the sweep below is satisfied by a panel welded to its
    narrowest tier, which is the failure this codebase keeps recording.

    It was 123 at the 3:2 seam and 107 after the re-seam: the NFT panel is on
    the *right* of the seam, so widening the right column to 6:13 handed it 16
    columns it did not have. It is 113 since the rows were rearranged, the one
    time this boundary has moved *up*: the stats row gained the written count
    (46 -> 49 columns) and gave up the dev holdings to a row of its own.
    """
    for width in (113, 143, 169, MEASURED_FULL_LAYOUT_COLUMNS,
                  SURF_FULL_LAYOUT_COLUMNS):
        panel = await _nft_panel(width)
        assert "667 holders" in panel, width
        assert "38 transfers/24h" in panel, width
        assert "1/2000 written" in panel, width
        assert "dev holds 3 identities" in panel, width
        assert "…" not in panel, f"the NFT panel truncates at {width}:\n{panel}"
        assert NFT_SHORT_HINT not in panel, (
            f"a marker is lit at {width} where nothing was shed"
        )


async def test_the_nft_panel_sheds_the_written_count_rather_than_cutting_it():
    """112 columns: one short of the whole row, which is where it breaks.

    The field that goes first is the written count, and it goes *whole*: the
    alternative the ellipsis gives you is ``1/2000 writt…``, a labelled figure
    with its label gone. Shedding is correct; shedding in silence is the
    defect. (It was ``dev holds`` that went first, at 106, until the dev
    holdings moved to a row of their own -- the ladder was re-derived rather
    than re-pointed, because a hint naming a field the panel now always shows
    would be a marker that lies.)
    """
    panel = await _nft_panel(112)
    assert "1/2000 written" not in panel, "the truncated written count survives"
    # The fields that stayed, whole -- including the dev row, which is not the
    # stats row's to trade any more.
    assert "667 holders" in panel
    assert "38 transfers/24h" in panel
    assert "dev holds 3 identities" in panel
    assert _NFT_HINTS["compact"] in panel, "the field went with nothing said"


async def test_the_nft_panel_never_cuts_a_number_off_its_unit():
    """100 and 90 columns: ``… transfers/24h · …`` and ``38 transfers/24…``.

    A truncated word is a shortened word; a truncated *number* still reads as
    a number, and ``24…`` is a different quantity from ``24h``. The hero
    carries the same rule (``burned 15,74…``), and the NFT panel now sheds
    whole fields to keep it.
    """
    for width in (90, 100):
        panel = await _nft_panel(width)
        assert "38 transfers/24h" in panel, f"the unit was cut off at {width}"
        assert "1/2000 written" not in panel, width
    # Both hint branches are reachable, and which one shows is a width fact:
    # ``IDENTITY.MD`` + 2 + the 25-column hint needs 38 usable columns, which
    # the panel first has at a terminal width of 89 (87 while the hint was 24
    # columns, 101 at the 3:2 seam).
    assert _NFT_HINTS["compact"] in await _nft_panel(89)
    narrow = await _nft_panel(88)
    assert _NFT_HINTS["compact"] not in narrow, (
        "the descriptive hint fits after all at 88 columns -- re-measure"
    )
    # ...and the fallback is the *bare* marker, not the hint belonging to the
    # narrower tier. That one is 18 columns and does fit here, so a fallback
    # chain routed through it would render a marker naming ``24h`` -- a field
    # this tier still shows -- and every ``SHORT_HINT in panel`` assertion
    # would stay green, ``SHORT_HINT`` being a prefix of it.
    assert _NFT_HINTS["minimal"] not in narrow, (
        "the panel fell back to a hint for a tier it is not in"
    )
    assert NFT_SHORT_HINT in narrow, "a field went with nothing said at all"


async def test_the_nft_panel_names_the_fields_it_sheds_at_its_narrowest_tier():
    """74 columns leaves 31 usable, which fits ``667 holders`` and no more.

    The hint is terse because it has to be: an 11-column title plus two
    columns of gap leaves exactly 18 for a marker that only appears when the
    panel is 31 wide, and 31 is where the tier starts -- the descriptive
    wording spends the whole budget and lives in a two-terminal-column band
    (74-75). Below it the panel falls back to the bare marker. (87 and 80 at
    the 3:2 seam -- the panel is wider now, so it takes a narrower terminal to
    drive it this far down.)
    """
    panel = await _nft_panel(74)
    assert "667 holders" in panel
    assert "transfers/24h" not in panel and "1/2000 written" not in panel
    # The dev holdings are on their own row and survive the narrowest tier --
    # the stats ladder has nothing to do with them any more.
    assert "dev holds 3 identities" in panel
    assert _NFT_HINTS["minimal"] in panel

    bare = await _nft_panel(71)
    assert _NFT_HINTS["minimal"] not in bare, (
        "the descriptive hint fits after all at 71 columns -- re-measure"
    )
    assert NFT_SHORT_HINT in bare


async def test_no_width_lets_the_nft_panel_cut_a_line_in_silence():
    """The sweep: whatever gets cut, the title says so -- at every width.

    Two claims, both against composited output. Anything ellipsised is
    advertised, and no *number* is ever the thing ellipsised: the tiers shed
    whole labelled fields, so a figure is either whole or absent.
    """
    import re

    widths = sorted(
        set(range(80, SURF_FULL_LAYOUT_COLUMNS + 1, 6))
        | {86, 87, 88, 90, 100, 101, 122, 123, SURF_FULL_LAYOUT_COLUMNS}
    )
    for width in widths:
        panel = await _nft_panel(width)
        if "…" in panel:
            assert NFT_SHORT_HINT in panel, (
                f"the NFT panel cut a line at {width} in silence:\n{panel}"
            )
        assert re.search(r"\d…", panel) is None, (
            f"a number was cut off its tail at {width}:\n{panel}"
        )


def test_surf_fits_inside_the_documented_app_width():
    """WP6 coordination tripwire — mechanical, not a comment.

    ``__main__.FULL_LAYOUT_COLUMNS`` (owned by WP6/one owner) documents the
    width the *widest* dashboard needs. If surf measures wider than it, the
    app-level constant and its help text become lies; this failure message is
    the hand-off.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"surf needs {SURF_FULL_LAYOUT_COLUMNS} columns but "
        f"__main__.FULL_LAYOUT_COLUMNS documents {FULL_LAYOUT_COLUMNS}. "
        "Do NOT edit __main__.py from WP5 — report to WP6, which owns it, "
        "and land this test together with WP6's raise."
    )


# -- refresh guard: skip, never queue ------------------------------------


def test_surf_screen_opts_into_the_refresh_guard():
    """Structural: the mixin comes first and the worker name is surf's own.

    The generic suite (tests/screens/test_refresh_guard.py) auto-discovers
    every polling screen; this pins the two things it cannot: MRO order and
    the name.
    """
    mro = SurfScreen.__mro__
    from textual.screen import Screen as _Screen

    from maxpane_dashboard.screens.refresh_guard import RefreshGuard

    assert mro.index(RefreshGuard) < mro.index(_Screen)
    assert SurfScreen.REFRESH_WORKER_NAME == "surf-refresh"


class _BlockingManager:
    """Parks inside ``fetch_and_compute`` until the test releases it."""

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return _frozen_payload()

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


async def test_overrun_tick_is_skipped_never_queued_or_cancelled():
    """A tick landing mid-refresh is dropped; the refresh completes once."""
    manager = _BlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        # on_screen_resume started the initial refresh; wait until it is
        # provably parked inside fetch_and_compute.
        await asyncio.wait_for(manager.entered.wait(), timeout=2)

        skipped_before = screen._refresh_skipped
        assert screen.start_refresh() is None          # the overrunning tick
        assert screen.start_refresh() is None          # and another
        assert screen._refresh_skipped == skipped_before + 2
        assert manager.calls == 1                      # nothing queued

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()

        assert manager.calls == 1                      # nothing ran after
        assert screen._refresh_in_flight is False      # flag lowered
        # ...and the completed refresh actually rendered.
        assert f"as of {_AS_OF_HHMM}" in _plain(screen.query_one("#title-bar"))


async def test_manual_refresh_and_interval_tick_share_one_guard():
    """The ``r`` binding and the interval callback fund into one guard.

    Both are inherited unchanged from ``RefreshGuard`` (pinned structurally
    by ``test_every_polling_screen_uses_the_guard``); this drives the actual
    named entry points -- ``action_refresh`` (the ``r`` key) and
    ``_schedule_refresh`` (the interval timer) -- through a real SurfScreen
    to prove neither can double-run against the other nor deadlock waiting
    for the other to finish.
    """
    manager = _BlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 1

        # A manual "r" press and an interval tick both land while the
        # initial refresh is still in flight -- neither may start a second
        # fetch, and neither blocks waiting on the other.
        screen.action_refresh()
        screen._schedule_refresh()
        for _ in range(20):
            await asyncio.sleep(0)
        assert manager.calls == 1, "a manual or interval tick started a second fetch"

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert manager.calls == 1
        assert screen._refresh_in_flight is False

        # Once idle, a manual refresh runs cleanly to completion...
        manager.entered.clear()
        manager.release.clear()
        screen.action_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 2
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False

        # ...and so does an interval tick straight after it: no deadlock
        # either way round.
        manager.entered.clear()
        manager.release.clear()
        screen._schedule_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 3
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False


class _TrackingBlockingManager:
    """``_BlockingManager`` plus concurrency/failure observables.

    ``_BlockingManager`` above is kept exactly as the brief specifies it;
    this sibling adds the extra bookkeeping the prefetch-join and
    raise-recovery proofs below need (concurrency high-water mark, a
    one-shot failure) without touching that frozen class.
    """

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.concurrent = 0
        self.max_concurrent = 0
        self.fail_next = False

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.entered.set()
        try:
            await self.release.wait()
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("simulated RPC failure")
            return _frozen_payload()
        finally:
            self.concurrent -= 1

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


class _PrefetchHarness(App):
    """Reproduces ``MaxPaneApp.on_mount``'s startup prefetch closely enough
    to prove SurfScreen's own first refresh joins it (MEDI-35). Same worker
    name, same node (the app), same ``exclusive=True`` as the real app and
    as ``tests/screens/test_refresh_guard.py``'s generic harness -- this
    drives the identical race through a real ``SurfScreen`` so WP5's own
    sign-off does not rest solely on another screen's test file.
    """

    def __init__(self, manager: _TrackingBlockingManager) -> None:
        super().__init__()
        self._manager = manager

    def on_mount(self) -> None:
        from maxpane_dashboard.screens.refresh_guard import PREFETCH_WORKER_NAME

        self.run_worker(
            self._prefetch(),
            exclusive=True,
            name=PREFETCH_WORKER_NAME,
            exit_on_error=False,
        )

    async def _prefetch(self) -> None:
        try:
            await self._manager.fetch_and_compute()
        except Exception:
            pass


async def test_surf_first_refresh_joins_the_startup_prefetch():
    """SurfScreen's initial refresh does not race the app-node prefetch.

    The join behaviour (``_await_startup_prefetch``) is inherited unchanged
    from ``RefreshGuard`` and already covered generically (other screens) in
    ``tests/screens/test_refresh_guard.py``; this repeats the exact race
    through a real ``SurfScreen`` instance so the first paint is proven, not
    assumed, not to be a race between the placeholder title and real data.
    """
    manager = _TrackingBlockingManager()
    app = _PrefetchHarness(manager)
    screen = SurfScreen(manager, poll_interval=30, name="surf")

    async with app.run_test():
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 1

        # The dashboard screen appears while the prefetch is still running --
        # this is the ordering the real app produces (prefetch starts at
        # on_mount, the dashboard screen only appears after splash + game
        # select).
        app.push_screen(screen)
        for _ in range(50):
            await asyncio.sleep(0)

        # Joined, not raced: only the prefetch's fetch is in flight, and the
        # screen's own has not started yet.
        assert manager.max_concurrent == 1
        assert manager.calls == 1

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)

        # The prefetch finished, then the screen's own fetch ran -- serially,
        # never concurrently -- and it produced the real first paint.
        assert manager.calls == 2
        assert manager.max_concurrent == 1
        assert f"as of {_AS_OF_HHMM}" in _plain(screen.query_one("#title-bar"))


async def test_a_raising_refresh_lowers_the_guard_flag_and_the_next_tick_still_runs():
    """The *guard* recovers from a raising manager, not just ``_do_refresh``.

    ``test_screen_survives_manager_exception`` already proves SurfScreen's
    own try/except around ``fetch_and_compute()`` degrades cleanly when
    ``_do_refresh()`` is called directly. This test drives the same failure
    through ``start_refresh()`` -- the real scheduling entry point used by
    the ``r`` binding and the interval timer -- to prove
    ``RefreshGuard._guarded_refresh``'s ``finally`` also lowers
    ``_refresh_in_flight`` and that the next scheduled tick still runs, so a
    raising manager cannot wedge the screen on placeholders for the rest of
    the session.
    """
    manager = _TrackingBlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        manager.fail_next = True
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()

        assert manager.calls == 1
        assert screen._refresh_in_flight is False, "a raising refresh wedged the guard"

        manager.entered.clear()
        manager.release.clear()
        screen._schedule_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 2, "the guard did not schedule the next tick"
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False
        assert f"as of {_AS_OF_HHMM}" in _plain(screen.query_one("#title-bar"))


# =========================================================================
# The ``p`` POOL4 view (2026-09-01) -- the third body on this screen
# =========================================================================
#
# The `l` body's tests two thousand lines up are the template and most of
# this section is that template applied to a second swap. Three things are
# genuinely new and are worth reading rather than skimming:
#
# 1.  A `…` at the end of a pool4 line is NOT necessarily a clip. Four of the
#     five panels fit their own third-party strings to their own tier width,
#     so HATCHES paints `no self-post in the announce chann…` at 47 cells
#     inside a 99-cell panel and means it. `_clipped_pool4_lines` compares
#     against the panel's own edge instead, and the launchpad's bare
#     `endswith("…")` would have reported this whole body as permanently
#     clipped at every width including 200.
# 2.  The height pin is a CONSTANT under every payload, and that is a design
#     property this section asserts directly rather than inferring from one
#     sweep -- see `test_the_pool4_height_pin_does_not_move_with_the_hatch_
#     count`.
# 3.  `_SCROLL_COLUMNS` gaining a MODE_POOL4 entry is the 2026-08-25 defect's
#     own regression lock, and it is guarded twice: once for the marker
#     really lighting on this body, once for the mapping being total over
#     every mode the screen has.


def _pool4_app(payload: dict | None = None) -> App:
    """The themed harness, so the real ``minimal.tcss`` pool4 block renders.

    Load-bearing, not tidiness: an app stylesheet outranks ``DEFAULT_CSS``,
    so a seam written into ``DEFAULT_CSS`` alone would leave whatever
    ``minimal.tcss`` says in charge and every width number below would be
    measuring the wrong file.
    """
    return _surf_app(payload)


#: The two column widths the width pin is assembled from, measured in situ.
#: Restated here as independent literals rather than imported from
#: ``screens/surf.py``'s docstring prose (which is prose, and cannot be
#: imported anyway), so ``test_the_pool4_pin_is_the_sum_of_the_needs_it_
#: claims`` compares two things rather than one thing with itself.
#:
#: **Neither number may be quoted as a reason for the panel arrangement**, and
#: :data:`POOL4_RAIL_NEED` especially not -- a warning that survived the
#: mainnet rebalance by changing sides. It used to read "the rail needs 43
#: *because* ``SurfPool4Hatches`` is in the other column". HATCHES is now in
#: the rail, the rail needs 50 *because* it is, and quoting that 50 as
#: evidence the swap was right is the identical circle mirrored. Rendered
#: instead, in both directions: the pin is **106 either way**, with
#: ``SurfPool4Flow`` binding at 105 either way under the pinned seam. The
#: arrangement was chosen on rows, not columns --
#: ``screens/surf.SURF_POOL4_FULL_LAYOUT_ROWS`` carries that measurement.
#:
#: Both were re-measured on 2026-09-02 against the layout the screen now
#: builds, across all three payload magnitudes, and the rail's moved:
#: left = max(FLOW 53, RATCHET 45, SPLIT 36); rail = max(HATCHES 50,
#: VAULT 44).
POOL4_LEFT_NEED = 53        # SurfPool4Flow's, plus the column's own gutter
POOL4_RAIL_NEED = 50        # SurfPool4Hatches', plus the column's own gutter

#: An independent literal for the same reason ``MEASURED_FULL_LAYOUT_COLUMNS``
#: is one: a test that aliased the screen's constant would compare a number
#: against itself and pin nothing.
MEASURED_POOL4_COLUMNS = 106
MEASURED_POOL4_ROWS = 44


def _pool4_payload(**overrides) -> dict:
    return _frozen_payload(**overrides)


def _pool4_hatch_payload(rows: int) -> dict:
    """The fixture's hatch list re-cut to *rows* levers.

    The producer emits ten and the widget caps at twelve, so the interesting
    magnitudes are 0, 10 and 12 -- and the height pin's whole claim is that
    none of them moves it.
    """
    base = _sample_data()["pool4_hatches"]
    labels = ("owner", "paused", "rescue", "market", "rebalance",
              "burn sink", "rewards", "deployed")
    return _frozen_payload(pool4_hatches=[
        {**base[i % len(base)], "label": labels[i % len(labels)]}
        for i in range(rows)
    ])


#: The pool4 flow in the state the data is normally in, on
#: :func:`_ordinary_burn_payload`'s exact reasoning. ``_fmt.fmt_imd`` renders
#: 100.00..999.99 at **six** columns and compacts everything above 1000, so
#: the committed magnitudes (``1.2K``, ``4.5K``) are this panel's *narrow*
#: case and a three-digit-and-two-decimals row is its widest. The ETH fee leg
#: is four decimals, so ``0.9999 ETH`` is the widest that cell can be.
#: A pin measured only against the compact numbers is a pin nobody has tested.
def _ordinary_pool4_payload() -> dict:
    rows = []
    for index, side in enumerate(("sell", "buy", "sell")):
        rows.append({
            "ts": 1_756_000_000.0 - index,
            "age_s": 120.0 + index * 86_400 * 40,   # forces the widest fmt_age
            "side": side,
            "size_imd": 987.65,
            "burned_imd": 888.88 if side == "sell" else 0.0,
            "stakers_imd": 999.99 if side == "sell" else 0.0,
            "fee_imd": 999.99 if side == "buy" else None,
            "fee_eth": None if side == "buy" else 0.9999,
            "settled": index != 2,
            "tx_hash": "0x" + "ab" * 32,
        })
    return _frozen_payload(
        pool4_flow=rows * 8,
        # The vault line that actually sets the rail's 42: `fmt_imd`'s
        # six-column band on both halves of `queue … · … days of runway`.
        pool4_backlog_imd=999.99,
        pool4_backlog_days=999.9,
    )


def _clipped_pool4_lines(app, screen) -> list[str]:
    """Every composited line in the ``p`` body that **CSS** truncated.

    Asked of the five panels, never of their two containers, for
    ``_clipped_launchpad_lines``' reason: a container's rectangle includes
    the cell reserved by ``scrollbar-gutter: stable``, so on any row where
    the scrollbar glyph is painted a genuinely clipped line no longer *ends*
    in ``…`` and the check goes quiet exactly when the layout is under most
    pressure.

    **And it compares against the panel's own edge, which the launchpad's
    version does not have to.** Four of this body's five panels fit their own
    third-party strings to their own tier width with ``_fmt.fit_cell``, so a
    trailing ``…`` is routinely the panel saying "this detail is longer than
    the column I gave it" rather than CSS saying "this line is longer than
    the panel". HATCHES paints exactly that at 47 cells inside a 99-cell
    panel, and a bare ``endswith("…")`` reports this body as clipped at every
    width including 200 -- a permanently red sweep that would have been
    "fixed" by moving a pin. ``text-overflow: ellipsis`` can only cut at the
    panel's content edge, so that is what the length is compared against.
    """
    out = []
    for cls in _POOL4_WIDGET_CLASSES.values():
        widget = screen.query_one(cls)
        edge = widget.region.width - 1
        for line in _region_text(app, widget).split("\n"):
            body = line.rstrip()
            if body.endswith("…") and len(body) >= edge:
                out.append(body)
    return out


def _pool4_marked(app, screen) -> set[str]:
    """Which pool4 panels have a ``‹`` marker lit, by class name.

    ``‹`` rather than ``‹ widen``: this body's rail panels fall back to a bare
    glyph when the title plus its network word plus the words no longer fit
    (``widgets/surf/_pool4.GLYPH_HINT``), and a check written against the
    long spelling alone would call a marked panel unmarked at exactly the
    widths where it is under most pressure.
    """
    return {
        name
        for name, cls in _POOL4_WIDGET_CLASSES.items()
        if "‹" in _region_text(app, screen.query_one(cls))
    }


# -- the swap itself ------------------------------------------------------


def test_the_bindings_are_refresh_and_the_two_view_toggles():
    """``c`` is still gone; ``l``, ``p`` and ``escape`` are not a return of it.

    ``c`` existed only because the announce feed and the dev-activity panel
    shared one slot, and a key that hides half a screen still has nothing to
    offer this layout. ``l`` and ``p`` are a different shape of key: each
    swaps the *whole* dashboard body for an unrelated second view (curator's
    ``y``/``f`` precedent) and leaves the hero mounted above it.

    This replaces ``test_the_bindings_are_refresh_and_the_launchpad_toggle``
    rather than sitting beside it: two tests asserting different exact
    contents of one ``BINDINGS`` set cannot both pass, and the older one's
    ``keys == {"r", "l", "escape"}`` is the assertion this task changes.
    """
    keys = {binding.key for binding in SurfScreen.BINDINGS}
    assert keys == {"r", "l", "p", "escape"}
    assert not hasattr(SurfScreen, "action_toggle_view"), (
        "the old c-swap action outlived its binding -- an action with no key "
        "is a surface nobody can reach and nobody maintains"
    )
    for action in ("action_toggle_launchpad", "action_toggle_pool4",
                   "action_show_dashboard"):
        assert hasattr(SurfScreen, action), action


async def test_p_swaps_the_body_and_keeps_the_hero() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("p")
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is True
        assert screen.query_one(SurfHero).display is True
        assert screen.query_one("#middle-row").display is False
        assert screen.query_one("#separator").display is False
        assert screen.query_one("#bottom-row").display is False


async def test_escape_backs_out_of_the_pool4_body_too() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("p")
        await pilot.press("escape")
        assert pilot.app.screen.query_one("#middle-row").display is True
        assert pilot.app.screen.query_one(f"#{POOL4_BODY_ID}").display is False


async def test_p_is_idempotent_and_toggles_back() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("p")
        await pilot.press("p")
        assert pilot.app.screen.query_one("#middle-row").display is True
        assert pilot.app.screen.query_one(f"#{POOL4_BODY_ID}").display is False


async def test_the_three_bodies_are_never_showing_at_once() -> None:
    """Exactly one body at a time, through every transition between them.

    This is the test for the edit ``_show_mode`` was most likely to receive:
    keeping the old ``launchpad = self._mode == MODE_LAUNCHPAD`` boolean and
    adding a second one beside it leaves the dashboard rows reading ``not
    launchpad``, which is **true** in MODE_POOL4 -- so ``p`` would paint the
    pool4 body on top of a dashboard body that never went away. Every
    assertion below passes under that mutation except the ones about
    ``#middle-row``, which is why the dashboard rows are checked on every
    hop rather than only on the way home.
    """
    bodies = ("#middle-row", f"#{LAUNCHPAD_BODY_ID}", f"#{POOL4_BODY_ID}")
    async with _pool4_app().run_test() as pilot:
        screen = pilot.app.screen
        for keys, expected in (
            ((), "#middle-row"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("p",), f"#{POOL4_BODY_ID}"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("escape",), "#middle-row"),
            (("p",), f"#{POOL4_BODY_ID}"),
            (("escape",), "#middle-row"),
        ):
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (keys, showing)
            # ...and the hero is never part of any of it.
            assert screen.query_one(SurfHero).display is True


async def test_the_status_hint_names_both_views() -> None:
    """The phrase reaches a pixel, and reaches it as ONE ``Segment``.

    Two assertions, and the second one is the whole point. ``_screen_text``
    joins a strip's segments with ``""``, which is the right instrument for
    every other composited assertion in this file and is **blind to exactly
    the defect this test exists to catch**: a per-letter ``[dim]`` tag splits
    the hint into ``l`` / `` launchpad · `` / ``p`` / `` pool4`` and the
    row-joined text is byte-identical either way.

    Proven, not assumed. Mutating ``KEY_HINTS`` to
    ``"[dim]l[/] launchpad · [dim]p[/] pool4"`` left the row-join version of
    this test green; it is the segment check below that reddens.

    Why the segment boundary is the subject at all: the app-level acceptance
    grep in ``tests/test_surf_registration.py`` and the launchpad hint test
    above both join **every segment with a newline**, which is the join
    CLAUDE.md warns against for ordinary layout assertions precisely because
    it splits a styled row into several apparent lines. Here that is the
    measurement rather than the mistake -- the claim being made is "this
    phrase is one styled run", and a split is what makes those greps fail
    while the status bar looks perfectly correct on screen.
    """
    phrase = "l launchpad · p pool4"
    async with _pool4_app().run_test() as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = _screen_text(pilot.app)
        segments = [seg.text for strip in strips for seg in strip]

    assert phrase in text, (
        "the hint did not reach a pixel -- check the StatusBar had room for "
        "it at this width"
    )
    assert any(phrase in segment for segment in segments), (
        "the hint reaches the screen but is split across Segments: "
        "KEY_HINTS must be ONE markup run, not per-letter tags, or the "
        "app-level acceptance greps for the contiguous phrase fail while "
        "the bar itself looks right"
    )


async def test_the_pool4_key_hint_fits_the_status_bar_at_the_full_layout() -> None:
    """Measured against the bar's own budget, never counted.

    This hint is nine columns longer than the one that shipped, and the
    StatusBar's left label is the segment that loses characters when the bar
    runs out. Asserted at ``SURF_FULL_LAYOUT_COLUMNS`` -- the width the whole
    dashboard is documented to need -- and, one column at a time, over the
    band below it, so the test says *where* it stops fitting rather than only
    that it fits somewhere.

    Both halves of the phrase are checked. ``l launchpad`` alone survives
    several columns further than the whole hint does, so a test that only
    looked for the new half would call the row healthy while the old half
    had been cut off the other end.
    """
    async with _pool4_app().run_test(
        size=(SURF_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "l launchpad · p pool4" in text

    # The band below it: find where the whole phrase stops reaching a pixel,
    # and assert that width is under the documented layout rather than over.
    lost_at = None
    for width in range(SURF_FULL_LAYOUT_COLUMNS, 79, -1):
        async with _pool4_app().run_test(size=(width, 46)) as pilot:
            await pilot.pause()
            if "l launchpad · p pool4" not in _screen_text(pilot.app):
                lost_at = width
                break
    assert lost_at is None or lost_at < SURF_FULL_LAYOUT_COLUMNS, (
        f"the key hint is already cut at {lost_at} columns, which is at or "
        f"above the documented {SURF_FULL_LAYOUT_COLUMNS} -- shorten the hint"
    )


# -- the body's shape and its dispatch ------------------------------------


async def test_the_pool4_body_holds_five_panels_in_two_columns() -> None:
    """Asserted on each container's own children, never on a screen-wide
    query: a panel mounted into the wrong column still answers ``query_one``
    from the screen and would leave this green.

    The order is the layout and both halves of it are deliberate. HATCHES
    leads the RAIL: plan section 5 R4's day-one state is *undiscovered*, and
    HATCHES is the panel that says so, so it sits at the top of its column
    rather than under a summary of numbers the view has not earned yet. The
    left column stacks THE SPLIT and THE RATCHET above the flow log, and the
    two columns then carry 33 rows each at the worst payload, which is what
    ``SURF_POOL4_FULL_LAYOUT_ROWS`` is measured from.

    This docstring said "the rail stacks the three panels whose line count is
    a constant, which is what makes the pin the same number under every
    payload" until 2026-09-02. That property was real and is gone: mainnet's
    three-way split made THE SPLIT payload-sized as well, and no two-column
    cut of these five panels can keep both variable panels out of the binder.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        rail = screen.query_one(f"#{POOL4_RAIL_ID}")
        assert [type(w) for w in left.children] == [
            SurfPool4Split, SurfPool4Ratchet, SurfPool4Flow,
        ]
        assert [type(w) for w in rail.children] == [
            SurfPool4Hatches, SurfPool4Vault,
        ]
        # ...and the two columns really are side by side, not stacked: the
        # child lists above are identical either way.
        assert left.region.right <= rail.region.x
        assert left.region.y == rail.region.y


#: How the two column ``#:`` blocks spell each panel, so the agreement test
#: below can compare prose against ``compose``.
#:
#: Hand-typed rather than derived from the class names: deriving it would
#: make the test reconstruct the very sentence it is checking, and it could
#: never fail. The prose names are the ones a reader sees on screen, which is
#: why the blocks use them.
_POOL4_PANEL_PROSE = {
    "THE SPLIT": SurfPool4Split,
    "THE RATCHET": SurfPool4Ratchet,
    "POOL4 FLOW": SurfPool4Flow,
    "HATCHES": SurfPool4Hatches,
    "sIMD VAULT": SurfPool4Vault,
}


def _pool4_column_block(constant: str) -> str:
    """The ``#:`` block immediately above *constant* in ``screens/surf.py``,
    as one whitespace-normalised string."""
    import re

    from maxpane_dashboard.screens import surf as surf_module

    source = Path(surf_module.__file__).read_text()
    lines = source.splitlines()
    index = next(
        i for i, line in enumerate(lines) if line.startswith(f"{constant} = ")
    )
    block: list[str] = []
    i = index - 1
    while i >= 0 and lines[i].startswith("#:"):
        block.append(lines[i][2:].strip())
        i -= 1
    return re.sub(r"\s+", " ", " ".join(reversed(block)))


@pytest.mark.parametrize(
    "constant,container_id",
    [("POOL4_LEFT_ID", POOL4_LEFT_ID), ("POOL4_RAIL_ID", POOL4_RAIL_ID)],
    ids=["left", "rail"],
)
async def test_the_pool4_column_blocks_name_the_panels_compose_builds(
    constant, container_id,
) -> None:
    """⚠ The recurring defect on this branch, turned into a red suite.

    ``POOL4_LEFT_ID`` and ``POOL4_RAIL_ID`` do not carry labels, they carry
    **reasoned blocks that argue why an arrangement is correct** -- and a
    persuasive wrong explanation is what the next reader trusts. CLAUDE.md's
    convention is that the ``#:`` block beside the code is the authority
    *because* it sits beside the code and cannot drift the way a copy in
    another file can. When the authority is the copy that drifted, a reader
    has no way to tell which half of the file to believe, and this file has
    a correct ``SURF_POOL4_FULL_LAYOUT_ROWS`` block three hundred lines away
    that would then be saying something incompatible.

    **It has drifted twice and been suspected a third time.** Once before the
    W3 follow-up, once when the mainnet rebalance recut the body, and once
    more as a false alarm from a reader working off a pre-edit copy -- which
    cost a round trip to refute and is its own argument for a check that
    answers in a second. Every one of those was a human noticing; none of
    them was a test.

    So the block's opening arrangement sentence is parsed and compared
    against what ``compose`` actually builds, per column, in order. The
    convention it pins is small and worth stating: **each column block leads
    with a bold run naming its panels top to bottom, joined by "over"**. A
    future rebalance that moves a panel and not the sentence fails here on
    the same commit rather than in someone's reading months later.

    What this does NOT check, said plainly so nobody mistakes its scope: the
    blocks' claims about which child carries the ``1fr``. That is guarded one
    layer down by
    ``test_exactly_one_pool4_child_per_column_carries_the_fr``, which reads
    ``minimal.tcss`` -- the copy that actually renders. Asserting the prose
    version here as well was tried and dropped: every phrasing that survived
    a paragraph reflow also passed for a sentence naming the wrong panel,
    which is the tests-that-cannot-fail shape this repo keeps a taxonomy of.
    """
    import re

    block = _pool4_column_block(constant)
    bold = re.search(r"\*\*(.+?)\*\*", block)
    assert bold, (
        f"{constant}'s block has no bold arrangement sentence -- the "
        "convention this test pins is that it leads with one"
    )
    named = [part.strip(" .`") for part in bold.group(1).split(" over ")]
    unknown = [n for n in named if n not in _POOL4_PANEL_PROSE]
    assert not unknown, (
        f"{constant}'s block names {unknown}, which is not a panel on this "
        f"body -- known names are {sorted(_POOL4_PANEL_PROSE)}"
    )

    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        built = [
            type(w) for w in pilot.app.screen.query_one(f"#{container_id}").children
        ]

    assert [_POOL4_PANEL_PROSE[n] for n in named] == built, (
        f"{constant}'s block says the column is {named}, but compose builds "
        f"{[c.__name__ for c in built]}. The block is not a label, it is the "
        "argument for the layout -- correct it in the same change that moved "
        "the panel, and record the drift rather than overwriting it"
    )


#: Every pool4 payload key whose contract is a CLOSED vocabulary, mapped to
#: the tuple it must draw from -- scalars first, then the fields on row
#: payloads.
#:
#: Hand-typed, on this file's standing rule: deriving the map from the
#: contract would make the sweep below compare the vocabulary against itself.
#: The names are imported, so a RENAMED vocabulary fails at import; only the
#: key-to-vocabulary pairing is restated.
_POOL4_CLOSED_VOCABULARIES = {
    "pool4_network": POOL4_NETWORKS,
    "pool4_discovery_state": POOL4_DISCOVERY_STATES,
    "pool4_discovery_source": POOL4_DISCOVERY_SOURCES,
    "pool4_counter_state": POOL4_COUNTER_STATES,
    "pool4_reward_path": POOL4_REWARD_PATHS,
}
_POOL4_ROW_VOCABULARIES = {
    "pool4_flow": {"side": POOL4_FLOW_SIDES},
    "pool4_hatches": {
        "scope": POOL4_HATCH_SCOPES,
        "label": POOL4_HATCH_LABELS,
        "state": POOL4_HATCH_STATES,
    },
}


def _all_pool4_fixtures() -> dict[str, dict]:
    """Every pool4 payload this module hands to a real screen."""
    return {
        "_pool4_payload": _pool4_payload(),
        "_mainnet_pool4_payload": _mainnet_pool4_payload(),
        "_ordinary_pool4_payload": _ordinary_pool4_payload(),
        "_pool4_hatch_payload(0)": _pool4_hatch_payload(0),
        "_pool4_hatch_payload(10)": _pool4_hatch_payload(10),
        "_pool4_hatch_payload(12)": _pool4_hatch_payload(12),
        **{
            f"_POOL4_HEIGHT_PAYLOADS[{name!r}]": build()
            for name, build in _POOL4_HEIGHT_PAYLOADS.items()
            if build() is not None
        },
    }


def test_every_closed_vocabulary_fixture_value_is_a_member() -> None:
    """⚠ A fixture may not invent a word, and nothing checked that until now.

    WP0's agreement tests pin that each closed vocabulary and its renderers
    agree. **Neither direction looks at a fixture**, so a payload built here
    with a word that is in no vocabulary satisfied every existing guard: the
    key is present, correctly named, dispatched, and declared by its panel,
    so the kwarg sweep, the renderer-count sweep and the swallow check are
    all green. Only a vocabulary check or a rendered-output diff can see that
    the value means nothing.

    That is S21's lesson reaching a new layer. S21 was a key that reached no
    *renderer*; this is a key that reaches its renderer carrying a word the
    renderer cannot interpret, which is worse, because the panel then
    exercises its own unknown branch while the fixture's name says otherwise.

    **It had two live instances, and this test was written because of them.**
    ``_pool4_payload`` carried ``"two-way"`` and ``_mainnet_pool4_payload``
    carried ``"three-way"``; ``POOL4_REWARD_PATHS`` is
    ``("direct", "via-distributor")``. Both words describe the SPLIT's shape
    rather than the TOPOLOGY the key carries, and the comment beside the
    first one said "the reward path is the two-way one", which is why it read
    as correct on every re-read. ``SurfPool4Split`` treats an unrecognised
    path as unknown and annotates nothing -- deliberately, because guessing
    either way is the 3x error between the 4.5% staker leg and the 15% reward
    share -- so the mainnet fixture rendered
    ``measured stakers 9.89%`` where it should have rendered
    ``measured stakers 9.89% (staking leg)``, on the one line whose whole job
    is to say which leg the reader is looking at.

    ``None`` is skipped rather than rejected: it is the honest "not read" or
    "no such thing" on several of these keys, and the vocabularies
    deliberately exclude it.
    """
    offenders: list[str] = []
    for name, payload in _all_pool4_fixtures().items():
        for key, vocabulary in _POOL4_CLOSED_VOCABULARIES.items():
            value = payload.get(key)
            if value is not None and value not in vocabulary:
                offenders.append(
                    f"{name}[{key!r}] = {value!r}, not one of {vocabulary}"
                )
        for key, fields in _POOL4_ROW_VOCABULARIES.items():
            for index, row in enumerate(payload.get(key) or ()):
                for field, vocabulary in fields.items():
                    value = row.get(field)
                    if value is not None and value not in vocabulary:
                        offenders.append(
                            f"{name}[{key!r}][{index}][{field!r}] = {value!r}, "
                            f"not one of {vocabulary}"
                        )

    assert not offenders, (
        "fixture values outside their closed vocabulary -- the panel will "
        "render its unknown branch while this fixture's name claims "
        "otherwise:\n  " + "\n  ".join(offenders)
    )


def test_the_two_pool4_fixtures_disagree_about_the_reward_path() -> None:
    """The premise the sweep above cannot supply, and without it the fix is
    only half checked.

    Both fixtures could be corrected to the *same* member and stay green
    there -- but the Sepolia fixture exists to be the ``direct`` deployment
    and the mainnet one to be the ``via-distributor`` deployment, which is
    the whole reason the pair is swept side by side. A fix that collapsed
    them onto one word would lose the case the key exists for.
    """
    assert _pool4_payload()["pool4_reward_path"] == "direct"
    assert _mainnet_pool4_payload()["pool4_reward_path"] == "via-distributor"
    # ...and the topology really is the thing that differs, not just a string:
    assert _pool4_payload()["pool4_distributor_addr"] is None
    assert _mainnet_pool4_payload()["pool4_distributor_addr"] is not None


async def test_every_pool4_panel_is_dispatched_before_p_is_pressed() -> None:
    """Composed-once-shown-by-``display``: the first ``p`` paints a complete
    frame, not a blank one that fills in a beat later.

    Checked on the widgets' own stored payloads while the body is still
    hidden -- a hidden widget reaches no compositor row at all, so there is
    nothing to read off the screen -- and then on composited output once
    ``p`` has been pressed, because a panel that stored a payload and
    rendered nothing would satisfy the first half alone.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is False
        for name, cls in _POOL4_WIDGET_CLASSES.items():
            assert screen.query_one(cls)._payload, (
                f"{name} was not dispatched while the body was hidden -- the "
                "first `p` will paint it blank"
            )
        await pilot.press("p")
        await pilot.pause()
        text = _screen_text(pilot.app)

    for title in ("HATCHES", "POOL4 FLOW", "THE SPLIT", "THE RATCHET",
                  "sIMD VAULT"):
        assert title in text, title
    # The payload, not just the titles -- a dispatched panel rendering its
    # empty state would satisfy the five checks above.
    assert "SELL" in text and "89.10%" in text and "1.302986" in text


async def test_every_pool4_panel_titles_the_network_it_is_showing() -> None:
    """Plan section 5 R4, and it is a hard failure rather than a cosmetic one.

    There is no pool4 hook on mainnet, so what runs on day one is discovery
    finding nothing and five panels rendering **Sepolia** numbers. A testnet
    number on an unmarked panel is not merely stale, it is fiction presented
    as live -- so the network word rides every panel's own title, not a
    footnote and not a status-bar mention, and all five have to agree.

    Asserted per panel region rather than on the whole screen: ``SEPOLIA``
    appearing five times anywhere would pass a screen-wide count while four
    panels went networkless.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        for name, cls in _POOL4_WIDGET_CLASSES.items():
            region = _region_text(pilot.app, screen.query_one(cls))
            assert "SEPOLIA" in region, (
                f"{name} does not name the network its numbers came from"
            )
            assert "MAINNET" not in region, name


async def test_a_dead_pool4_sweep_leaves_every_panel_explicit() -> None:
    """No blank panel, no stale number presented as live.

    The whole-payload outage: every pool4 key ``None``, which is what a tier
    that has never landed looks like. Each panel must say so in its own
    words, and the network word falls back to the em dash rather than
    guessing a chain.
    """
    from maxpane_dashboard.widgets.surf.pool4_flow import (
        UNAVAILABLE_LINE as FLOW_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_hatches import (
        UNAVAILABLE_LINE as HATCHES_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_ratchet import (
        UNAVAILABLE_LINE as RATCHET_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_vault import (
        UNAVAILABLE_LINE as VAULT_UNAVAILABLE,
    )

    payload = _frozen_payload(**{key: None for key in POOL4_KEYS})
    async with _pool4_app(payload).run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        text = _screen_text(pilot.app)
    for line in (FLOW_UNAVAILABLE, HATCHES_UNAVAILABLE, RATCHET_UNAVAILABLE,
                 VAULT_UNAVAILABLE):
        assert line in text, line
    # The network word is the em dash, not a guessed chain.
    assert "SEPOLIA" not in text and "MAINNET" not in text


async def test_a_quiet_pool4_sweep_is_not_a_dead_one() -> None:
    """``[]`` and ``None`` must not composite to the same sentence.

    This is CLAUDE.md's FARM/HOUR-SAVED rule at the screen level: a swept-
    and-quiet window and a read that failed are different facts, and a panel
    that renders them identically reads confident and green through an
    outage. The widget's own tests pin the two strings; this pins that the
    *screen* hands the widget the distinction rather than flattening it on
    the way (``data.get`` returns ``None`` for a missing key and ``[]`` for
    an empty one, and only one of those is an outage).
    """
    from maxpane_dashboard.widgets.surf.pool4_flow import (
        EMPTY_LINE, UNAVAILABLE_LINE,
    )

    async with _pool4_app(_frozen_payload(pool4_flow=[])).run_test(
        size=(150, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        quiet = _screen_text(pilot.app)
    async with _pool4_app(_frozen_payload(pool4_flow=None)).run_test(
        size=(150, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("p")
        await pilot.pause()
        dead = _screen_text(pilot.app)

    assert EMPTY_LINE in quiet and UNAVAILABLE_LINE not in quiet
    assert UNAVAILABLE_LINE in dead and EMPTY_LINE not in dead


# -- the p body's own measured width (2026-09-01) -------------------------
#
# ``SURF_FULL_LAYOUT_COLUMNS`` (this screen, 143),
# ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` (the ``l`` body, 138) and
# ``__main__.FULL_LAYOUT_COLUMNS`` (the app, 143) are all untouched by this
# task -- the measurement, the binding panel, the per-seam table and why the
# CLAUDE.md width record is not appended to are in
# ``SURF_POOL4_FULL_LAYOUT_COLUMNS``' own docstring in ``screens/surf.py``.
#
# The sweep runs **96..152**: ten columns below the measured 106 and
# forty-six above it, never starting at it, and crossing BOTH neighbouring
# pins (138 and 143) so agreeing with either would have to show up as a sweep
# result. The brief asked for 118..152; that is a subset of this range and
# every width in it is above the pin, so on its own the below-the-pin branch
# would have run zero times. The range was widened downward rather than the
# pin pushed up to meet it.


@pytest.mark.parametrize(
    "payload", [None, "ordinary"],
    ids=["committed-capture", "ordinary-magnitudes"],
)
@pytest.mark.parametrize("width", range(96, 153))
async def test_the_pool4_body_is_whole_from_its_pinned_width(
    width, payload
) -> None:
    """Start the sweep away from the pin: one that began at the constant
    would agree with it by construction.

    **Whole means the whole body, not merely the panels that can say so.**
    Both halves are asserted at and above the pin -- no marker anywhere *and*
    no CSS-clipped line anywhere -- because a seam whose binder went quiet
    would satisfy the marker half alone. Below the pin the claim is the
    marker's: something must be asking for the columns.

    **Swept against two payload magnitudes**, on
    ``_ordinary_burn_payload``'s reasoning next door. It does not move a
    single number here, and *that* is the result worth having: this panel's
    columns are floored at their own header labels, so the widest data cell
    never exceeds them. A capture-only sweep could not have told the
    difference between "the width does not move with the data" and "we only
    ever measured one payload".

    The dashboard body's own markers cannot contaminate this: ``#middle-row``
    is hidden in MODE_POOL4, so nothing it composites reaches the screen.
    """
    pl = _ordinary_pool4_payload() if payload == "ordinary" else None
    async with _pool4_app(pl).run_test(size=(width, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        marked = _pool4_marked(pilot.app, screen)
        clipped = _clipped_pool4_lines(pilot.app, screen)
        if width >= SURF_POOL4_FULL_LAYOUT_COLUMNS:
            assert not marked, (width, marked)
            assert not clipped, (
                f"at {width} the p body is clipping a line and nothing on "
                f"screen says so: {clipped}"
            )
        else:
            assert marked, width


@pytest.mark.parametrize("width", range(80, SURF_POOL4_FULL_LAYOUT_COLUMNS))
async def test_nothing_below_the_pool4_pin_clips_without_saying_so(
    width,
) -> None:
    """Below the pin the only panel allowed to lose anything is one that
    advertises the loss.

    The sibling sweep above only checks that *something* is marked below the
    pin, which stays green even if the marked panel and the clipping panel
    are different widgets. This is the half that would catch that, and it is
    also the half that would catch a future rail panel losing its marker: it
    asks, per width, whether every CSS-clipped line has a marker somewhere on
    the body to account for it.

    **The range starts at 80, well under the pin's neighbourhood**, because
    on the pinned seam nothing clips anywhere between 96 and 105 -- the whole
    point of choosing it -- so a sweep confined to those widths would execute
    its ``if`` body zero times and be a guard with no positive behind it.
    """
    async with _pool4_app().run_test(size=(width, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        clipped = _clipped_pool4_lines(pilot.app, screen)
        if clipped:
            assert _pool4_marked(pilot.app, screen), (
                f"at {width} the p body clips {clipped} and no panel on "
                "screen advertises the loss"
            )


async def test_the_pool4_binding_panel_is_the_flow_log() -> None:
    """Pinned by a test, not by a sentence.

    ``SurfPool4Flow`` is this body's binder, and it is the binder **by
    construction of the seam** rather than by luck: the left column needs 53
    screen columns and the rail 43, and 1:1 hands the rail 53 at the pin, so
    one column below the pin the flow log is the only panel with anything to
    say and stays the only one under every payload this pipeline produces.

    That is the property the seam was chosen for. ``3:2`` collects the very
    same 106 with the *rail* binding, and ``5:4`` collects the arithmetic
    floor of 96 with FLOW binding but zero margin on both halves -- so
    neither the pin alone nor the binder alone identifies the layout, and
    this test is what pins the half the constant cannot.
    """
    async with _pool4_app().run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS - 1, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        marked = _pool4_marked(pilot.app, pilot.app.screen)
    assert marked == {"SurfPool4Flow"}, marked


async def test_the_pool4_pin_is_the_sum_of_the_needs_it_claims() -> None:
    """The pin's *derivation*, not just its threshold.

    The sweep above can only see the resulting number, so it stays green if
    the two column needs the docstring names swapped, drifted, or were never
    true. Measured at the width where each column is exactly on its stated
    need -- the pin itself, where 1:1 gives the left column 53 -- and the
    rail's three columns of margin are asserted as margin rather than
    assumed.

    ``POOL4_LEFT_NEED``/``POOL4_RAIL_NEED`` are hand-typed literals here
    rather than imported from the screen: deriving them from the constant
    they explain would make this compare a number with itself.
    """
    async with _pool4_app().run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}").region.width
        rail = screen.query_one(f"#{POOL4_RAIL_ID}").region.width

    assert left == POOL4_LEFT_NEED, (
        f"the left column gets {left} columns at the pin, not the "
        f"{POOL4_LEFT_NEED} the constant is built from -- re-derive it"
    )
    assert rail >= POOL4_RAIL_NEED
    assert rail - POOL4_RAIL_NEED == 3, (
        f"the rail's margin is {rail - POOL4_RAIL_NEED}, not the three "
        "columns the seam was chosen to buy. It was ten before the mainnet "
        "rebalance put HATCHES (50) in the rail in place of VAULT (44), and "
        "the two-column-cheaper 20:19 seam was declined precisely because it "
        "leaves one"
    )
    # ...and the pin really is what those two needs add up to under this
    # seam, which is the arithmetic the docstring's per-seam table rests on.
    assert left + rail == SURF_POOL4_FULL_LAYOUT_COLUMNS
    assert MEASURED_POOL4_COLUMNS == SURF_POOL4_FULL_LAYOUT_COLUMNS


def test_the_pool4_body_fits_inside_the_documented_app_width() -> None:
    """The standing rule, asserted rather than assumed: a body measured wider
    than ``__main__.FULL_LAYOUT_COLUMNS`` means shortening a value, never
    raising the app's number.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_POOL4_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_POOL4_FULL_LAYOUT_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS
    # Three bodies, three independently measured pins. They are allowed to
    # be equal -- but if two of them ever ARE equal it should be because
    # somebody measured it, so the constants are kept separate and this is
    # the note that says so rather than a test forbidding the coincidence.
    assert SURF_POOL4_FULL_LAYOUT_COLUMNS != SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS


# -- the p body's own measured height (2026-09-01, re-swept 2026-09-02) ---
#
# The sweep runs 34..52 -- ten rows below the measured 44 and eight above,
# never starting at it. It has been re-centred twice as the pin moved
# (43 -> 46 -> 44); the rule is that the range straddles the pin generously
# and never begins on it, not that the endpoints are fixed.


#: The payloads the height sweep runs, and the last one is the pin's own.
#:
#: **The network dimension is not decoration.** Every Sepolia body here fits
#: in 43 or less -- the twelve-lever one needs exactly 43 -- so a sweep of
#: Sepolia payloads alone can say nothing about a pin of 44 from underneath,
#: and the first version of this test after the mainnet re-sweep made its
#: below-the-pin claim against ``_pool4_hatch_payload(12)`` for exactly that
#: reason and passed at 43 with the pin one row above it. THE SPLIT is three
#: rows taller on mainnet, so ``mainnet-capped`` is the body the pin actually
#: describes and is the only payload the below-the-pin branch may assert on.
_POOL4_HEIGHT_PAYLOADS = {
    "ten-levers": lambda: None,
    "no-levers": lambda: _pool4_hatch_payload(0),
    "capped-levers": lambda: _pool4_hatch_payload(12),
    "mainnet-capped": lambda: _mainnet_pool4_payload(
        pool4_hatches=_pool4_hatch_payload(12)["pool4_hatches"]
    ),
}


@pytest.mark.parametrize("payload_name", sorted(_POOL4_HEIGHT_PAYLOADS))
@pytest.mark.parametrize("rows", range(34, 53))
async def test_the_pool4_body_is_whole_from_its_pinned_height(
    rows, payload_name
) -> None:
    """150 columns is comfortably past the width pin, so nothing here is
    measuring a width.

    **The two halves are not symmetric, and that asymmetry is the pin's
    definition rather than a weakness in the test.** At and above the pin
    EVERY payload must fit -- that is what "the body is whole from here"
    claims, and it is checked for all three. Below the pin only the payload
    the pin was measured against need overflow: a body with no levers at all
    is fourteen rows shorter and legitimately fits at 42, so asserting the
    marker lit below the pin for every payload would be asserting that a
    small payload must pretend not to fit.

    That is exactly what the first version of this test did after the
    mainnet re-sweep, and it failed on six parametrisations for the right
    reason -- the pin had become a worst case over payloads where it used to
    be a constant, and the sweep had not been told.

    So the below-the-pin claim is made against ``mainnet-capped``, which is
    the worst case the widgets can render and therefore the payload the pin
    actually describes. It was made against the *Sepolia* capped-lever list
    until 2026-09-02, and that was a second version of the same mistake one
    dimension over: a twelve-lever Sepolia body needs 43, so it fits one row
    below a 44 pin and the "the pin is tight" half of this test was asserting
    something false about the right layout.
    """
    payload = _POOL4_HEIGHT_PAYLOADS[payload_name]()
    async with _pool4_app(payload).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        await pilot.pause()
        text = _screen_text(pilot.app)

    if rows >= SURF_POOL4_FULL_LAYOUT_ROWS:
        assert TALLER_HINT not in text, (rows, payload_name)
    elif payload_name == "mainnet-capped":
        assert TALLER_HINT in text, (rows, payload_name)


async def test_the_pool4_height_pin_is_measured_against_the_column_it_describes() -> None:
    """The pin's *derivation*, not just its threshold.

    **Measured below the pin, not at it.** Both columns' ``1fr`` children
    grow on a terminal with rows to spare, so at the pin itself each column
    reports the body's own height and the content the docstring derives is
    nowhere on screen. At 34 rows both sit on their floors and each column's
    ``virtual_size`` is its real content.

    The binder now SWITCHES with the payload, which is the property this
    body lost when mainnet made two panels payload-sized: the left column
    (THE SPLIT + THE RATCHET + the flow log's floor) binds on mainnet and on
    a short lever list, and the rail (HATCHES + sIMD VAULT) binds once the
    hatch list is long. So the assertion is on the *worst case over
    payloads*, which is what the pin actually is, rather than on one column
    being permanently taller.
    """
    worst = 0
    for label, payload in (
        ("sepolia-12-levers", _pool4_hatch_payload(12)),
        ("mainnet", _mainnet_pool4_payload()),
    ):
        async with _pool4_app(payload).run_test(size=(150, 34)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            await pilot.pause()
            screen = pilot.app.screen
            left = screen.query_one(f"#{POOL4_LEFT_ID}")
            rail = screen.query_one(f"#{POOL4_RAIL_ID}")
            assert left.size.height < left.virtual_size.height or \
                rail.size.height < rail.virtual_size.height, (
                    f"{label}: 34 rows no longer squeezes the body, so both "
                    "columns report the terminal's height and this test is "
                    "measuring nothing"
                )
            worst = max(worst, left.virtual_size.height,
                        rail.virtual_size.height)
            chrome = pilot.app.size.height - left.size.height

    assert worst == 33, (
        f"the body's worst-case content is {worst} rows, not the 33 the pin "
        "is derived from -- re-sweep it"
    )
    assert worst + chrome == SURF_POOL4_FULL_LAYOUT_ROWS
    assert MEASURED_POOL4_ROWS == SURF_POOL4_FULL_LAYOUT_ROWS


async def test_the_pool4_height_pin_covers_every_payload_the_widgets_render() -> None:
    """The property that REPLACED "the pin does not move with the payload".

    That claim was true while every panel whose line count answered to the
    data was kept out of the binding column. Mainnet ended it: THE SPLIT is
    12 rows on Sepolia and 15 on mainnet, HATCHES is 13 to 24 rows depending
    on the lever list, and any two-column arrangement of these five panels
    puts one of them in the binder. Asserting the old property now would be
    asserting something the layout cannot deliver, and quietly dropping it
    would leave the pin covering whichever payload somebody happened to
    sweep.

    So the claim is the honest one: the pin covers the WORST case over every
    payload the widgets can render -- including the twelve-lever list at
    ``pool4_hatches.MAX_ROWS``, which is above what the producer emits today
    and is exactly the case a pin measured against "the state the data is in"
    would have missed.
    """
    from maxpane_dashboard.widgets.surf.pool4_hatches import MAX_ROWS

    heights: dict[str, int] = {}
    for label, payload in (
        ("no-levers", _pool4_hatch_payload(0)),
        ("ten-levers", _pool4_hatch_payload(10)),
        ("capped-levers", _pool4_hatch_payload(MAX_ROWS)),
        ("mainnet", _mainnet_pool4_payload()),
        # The worst case, and the one the tightness probe below uses -- the
        # two halves have to be about the same body or "fits at the pin, not
        # one row under it" is a claim about two different layouts.
        ("mainnet-capped", _mainnet_pool4_payload(
            pool4_hatches=_pool4_hatch_payload(MAX_ROWS)["pool4_hatches"]
        )),
    ):
        async with _pool4_app(payload).run_test(
            size=(150, SURF_POOL4_FULL_LAYOUT_ROWS)
        ) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            await pilot.pause()
            text = _screen_text(pilot.app)
            assert TALLER_HINT not in text, (
                f"{label}: the body does not fit at its own pinned height"
            )
            heights[label] = pilot.app.screen.query_one(
                SurfPool4Hatches
            ).region.height

    # The premise: the hatch count really is changing the panel, or the four
    # cases above are one case measured four times.
    assert heights["no-levers"] < heights["ten-levers"] < \
        heights["capped-levers"], heights
    # ...and one row below the pin, the worst of them does NOT fit -- so the
    # pin is tight rather than merely generous.
    #
    # THE WORST PAYLOAD IS MAINNET'S, not the capped Sepolia list this used
    # to probe: THE SPLIT is 15 rows on mainnet against 12 on Sepolia, which
    # is three of the four rows separating a Sepolia body that fits in 43
    # from a mainnet one that needs 44. Probing the Sepolia list here asked
    # whether a body the pin does not describe fits one row under it, and
    # the honest answer was yes.
    worst_payload = _mainnet_pool4_payload(
        pool4_hatches=_pool4_hatch_payload(MAX_ROWS)["pool4_hatches"]
    )
    async with _pool4_app(worst_payload).run_test(
        size=(150, SURF_POOL4_FULL_LAYOUT_ROWS - 1)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT in _screen_text(pilot.app), (
            "the body still fits one row below the pin -- the pin is loose"
        )


async def test_the_pool4_floors_never_thin_a_panel_below_its_content() -> None:
    """``min-height`` on a ``1fr`` child is load-bearing, not decoration --
    and the two columns pick their ``1fr`` child by different rules.

    A ``1fr`` child cannot overflow a scroll container, it SHRINKS, so one
    given fewer rows than its content loses them with no scrollbar, no
    ``‹ widen`` and no other trace **unless it scrolls inside itself**. Only
    ``SurfPool4Flow`` does. So:

    * FLOW may be squeezed to its floor of 6 -- its rows go behind its own
      ``RichLog`` scrollbar, which is a place the reader can still reach;
    * ``sIMD VAULT`` carries the rail's ``1fr`` **because its line count is a
      constant**, so ``min-height: 10`` is both floor and ceiling and it can
      never be cut. Asserted against its content, not against the constant:
      a panel that grew an eleventh line would fail here rather than lose it;
    * HATCHES is ``auto`` and is therefore never shrunk at all, at any
      height, under any lever count -- which is the assertion that would have
      caught the arrangement this one replaced, where HATCHES carried the
      rail's ``1fr`` and silently lost two rows of a twelve-lever payload in
      the narrow window before the column began to scroll.

    Asserted on laid-out heights and on the marker, never on composited
    cells: a floored panel the column has scrolled past composites *zero*
    rows, correctly, and ``‹ taller`` is what says so.
    """
    async with _pool4_app(_pool4_hatch_payload(12)).run_test(
        size=(150, 24)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        flow = screen.query_one(SurfPool4Flow)
        vault = screen.query_one(SurfPool4Vault)
        hatches = screen.query_one(SurfPool4Hatches)

        assert flow.region.height >= 6, flow.region.height
        assert vault.region.height >= vault.virtual_size.height, (
            f"sIMD VAULT is {vault.region.height} rows against "
            f"{vault.virtual_size.height} of content -- the panel chosen for "
            "the rail's 1fr because it cannot be cut is being cut"
        )
        assert hatches.region.height == hatches.virtual_size.height, (
            f"HATCHES is {hatches.region.height} rows against "
            f"{hatches.virtual_size.height} of content: it is being shrunk, "
            "so it is no longer `height: auto` and its rows are being lost "
            "with nothing on screen saying so"
        )
        # The floors are only honest if the overflow they create is visible.
        # Without this the assertions above are green in a state where half
        # the body reaches the screen as nothing at all.
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]
        assert (
            screen.query_one(f"#{POOL4_LEFT_ID}").show_vertical_scrollbar
            or screen.query_one(f"#{POOL4_RAIL_ID}").show_vertical_scrollbar
        ), "neither column is scrolling, so the floors are not being tested"


# -- the row marker on the third body, and the mapping that feeds it ------


async def test_the_taller_marker_lights_on_the_pool4_body() -> None:
    """The 2026-08-25 defect's regression lock, applied to the third body.

    ``_rail_is_cut`` reads ``_SCROLL_COLUMNS[self._mode]`` and falls back to
    ``()`` for a mode that is not in it. A ``MODE_POOL4`` body added without
    its entry therefore reports "nothing is cut" at **every** terminal height
    while both its columns visibly scroll -- which is exactly what
    ``MODE_LAUNCHPAD`` did, for the whole of that view's existence, because
    the method read one hardcoded container id.

    Three heights, and the trio is what makes this bite rather than any one
    of them:

    * **50 rows** -- whole for the pool4 body (43) and whole for the
      dashboard body (36). The marker must be dark in both, or the test
      below cannot tell a wired marker from a stuck-on one.
    * **40 rows** -- short for pool4, whole for the dashboard. This is the
      half a missing ``_SCROLL_COLUMNS`` entry fails: the marker is dark
      before ``p`` and must be **lit** after it.
    * **28 rows** -- short for both. The marker must stay lit through the
      swap, which is what stops the fix being "light it whenever the mode is
      MODE_POOL4"; that mutation passes the 40-row half on its own.
    """
    for rows, before, after in ((50, False, False), (40, False, True),
                                (28, True, True)):
        async with _pool4_app().run_test(size=(150, rows)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            assert (TALLER_HINT in _screen_text(pilot.app)) is before, (
                f"{rows} rows: the DASHBOARD body's marker is not in the "
                "state this test's premise needs"
            )
            await pilot.press("p")
            await pilot.pause()
            assert (TALLER_HINT in _screen_text(pilot.app)) is after, (
                f"{rows} rows: the pool4 body's marker should be "
                f"{'lit' if after else 'dark'}"
            )


def test_every_mode_names_its_scrolling_columns() -> None:
    """``_SCROLL_COLUMNS`` must be **total** over the modes that exist.

    The test above proves this body's marker works. This proves the *next*
    body cannot be added without one, which is the half that would actually
    have caught the 2026-08-25 defect before it shipped: a mode missing from
    this mapping does not raise, it silently answers ``()``.

    The mode list is discovered from the module rather than typed, so a
    fourth ``MODE_*`` constant lands here the day it is written.
    """
    import maxpane_dashboard.screens.surf as surf

    modes = {
        getattr(surf, name)
        for name in dir(surf)
        if name.startswith("MODE_") and isinstance(getattr(surf, name), str)
    }
    assert modes == {MODE_DASHBOARD, MODE_LAUNCHPAD, MODE_POOL4}, (
        f"a mode was added or removed: {modes}"
    )
    assert set(SurfScreen._SCROLL_COLUMNS) == modes, (
        "a body has no _SCROLL_COLUMNS entry -- `‹ taller` will be dark "
        "across the whole of it at every terminal height: "
        f"{modes - set(SurfScreen._SCROLL_COLUMNS)}"
    )
    for mode, selectors in SurfScreen._SCROLL_COLUMNS.items():
        assert selectors, f"{mode} names no scrolling column"
        assert all(s.startswith("#") for s in selectors), (mode, selectors)


#: The two heights the pool4 gutter proof is measured at, and neither is
#: arbitrary. On the committed capture the columns first overflow at 40 rows
#: (measured, 2026-09-02: 41 shows no scrollbar, 40 does), so 50 is
#: comfortably on the roomy side and 40 is the first row count where the
#: scrollbar actually exists. A pair of heights both above the crossover
#: cannot fail -- the ``l`` body's own version of this test shipped exactly
#: that mistake once, and this one nearly repeated it: the crossover was 42
#: until WP4 shortened HATCHES, and the stale 42 left the premise assertion
#: failing rather than the comparison silently passing, which is the whole
#: reason the premise is asserted.
#:
#: Note this is the CAPTURE's crossover, not the pin's. The pin (44) is the
#: worst case over every payload; the committed capture is a Sepolia body
#: that legitimately fits in 41. Two different questions, two different
#: numbers.
_POOL4_ROOMY_ROWS = 50
_POOL4_OVERFLOWING_ROWS = 40


async def _pool4_column_widths(height: int, width: int = 150) -> dict:
    async with _pool4_app().run_test(size=(width, height)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        return {
            "split": screen.query_one(SurfPool4Split).region.width,
            "vault": screen.query_one(SurfPool4Vault).region.width,
            "flow": screen.query_one(SurfPool4Flow).region.width,
            "left_overflowing": screen.query_one(
                f"#{POOL4_LEFT_ID}"
            ).show_vertical_scrollbar,
            "rail_overflowing": screen.query_one(
                f"#{POOL4_RAIL_ID}"
            ).show_vertical_scrollbar,
        }


async def test_the_pool4_columns_reserve_their_scrollbar_gutters() -> None:
    """Without ``scrollbar-gutter: stable`` a column's scrollbar takes a
    column away the moment it overflows, so this layout's WIDTH requirement
    would move with its HEIGHT and the pin measured at 50 rows would be one
    column short at 42. Curator shipped exactly that.

    **The column belongs to the column's own children, not to the panels
    beside them**, so the widths compared are the panels' -- and the premise
    that the two heights straddle the overflow crossover is asserted first,
    because without it the comparison is trivially true and tests nothing.

    Checked against laid-out regions rather than ``styles.scrollbar_gutter``,
    because a style read cannot see a one-copy CSS deletion (the app
    stylesheet and ``DEFAULT_CSS`` cover for each other); that half is guarded
    by the property-by-property agreement test below.
    """
    roomy = await _pool4_column_widths(_POOL4_ROOMY_ROWS)
    cramped = await _pool4_column_widths(_POOL4_OVERFLOWING_ROWS)

    assert not roomy["rail_overflowing"], (
        f"the rail already overflows at {_POOL4_ROOMY_ROWS} rows -- both "
        "sample heights are on the same side of the crossover"
    )
    assert cramped["rail_overflowing"], (
        f"the rail does not overflow at {_POOL4_OVERFLOWING_ROWS} rows -- "
        "the condition this test exists to measure never occurs"
    )

    for panel in ("split", "vault", "flow"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at {_POOL4_ROOMY_ROWS} rows "
            f"and {cramped[panel]} at {_POOL4_OVERFLOWING_ROWS}: a scrollbar "
            "took a column instead of using its reserved gutter, so this "
            "layout's width requirement now moves with its height"
        )

    async with _pool4_app().run_test(size=(150, _POOL4_ROOMY_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        for column in (POOL4_LEFT_ID, POOL4_RAIL_ID):
            gutter = pilot.app.screen.query_one(f"#{column}").styles.scrollbar_gutter
            assert "stable" in str(gutter), column


async def test_the_hero_survives_the_pool4_body_swap() -> None:
    """The hero is outside ``#surf-pool4-body``, so nothing it tracks goes
    dark when ``p`` swaps the body underneath it.

    Asserted against the hero's **own region**, not the whole screen: the
    pool4 panels composite the words ``BURN``, ``FLOW`` and ``SUPPLY``
    themselves, so a whole-screen substring check would pass with the hero
    unmounted entirely.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is True
        hero = _region_text(pilot.app, screen.query_one(SurfHero))
        for title in ("LAUNCHPAD", "FLOW", "BURN", "IMD SUPPLY"):
            assert title in hero, f"the hero lost its {title} box under `p`"
        assert "2,376,732 IMD" in hero
        assert "READY" in hero


# -- the p body's CSS, in agreement ---------------------------------------

_POOL4_CSS_SELECTORS = (
    f"#{POOL4_BODY_ID}", f"#{POOL4_LEFT_ID}", f"#{POOL4_RAIL_ID}",
    "SurfPool4Hatches", "SurfPool4Flow",
    "SurfPool4Split", "SurfPool4Ratchet", "SurfPool4Vault",
)


def test_the_pool4_body_css_agrees_between_default_css_and_the_stylesheet() -> None:
    """``SurfScreen.DEFAULT_CSS`` and the surf block in ``minimal.tcss`` must
    describe the pool4 body's geometry identically -- edit both or neither.

    The app stylesheet is what actually renders (it outranks
    ``DEFAULT_CSS``); ``DEFAULT_CSS`` is what keeps the screen correctly
    proportioned when it is reviewed or mounted without it. A property
    declared in one copy and not the other is *invisible* rather than
    conflicting: Textual falls back to ``DEFAULT_CSS`` for anything the app
    stylesheet never mentions, so the layout is right under both copies today
    and wrong under one of them the moment either value changes.

    Reuses the ``l`` body's own comparator and property list, which already
    covers ``overflow-y``, ``scrollbar-gutter`` and ``scrollbar-size`` -- all
    three load-bearing here for the same reasons they are next door.
    """
    fallback = _css_rules(SurfScreen.DEFAULT_CSS)
    block = _css_rules(_surf_stylesheet_block())

    for selector in _POOL4_CSS_SELECTORS:
        assert selector in fallback, (
            f"{selector} is not styled in SurfScreen.DEFAULT_CSS"
        )
        assert selector in block, (
            f"{selector} is not styled in the surf block of minimal.tcss"
        )
        for prop in _LAUNCHPAD_CSS_STRUCTURAL:
            default = _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS:
                assert _expand_css_box(left) == _expand_css_box(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


def test_exactly_one_pool4_child_per_column_carries_the_fr() -> None:
    """The rule the body is built on, read off the CSS rather than the code.

    Two ``1fr`` children in one column split its slack and neither reaches
    the floor the layout was measured with; none at all strands the column's
    spare rows above the fold. Both are silent, and both are the kind of
    thing an edit to the stylesheet makes without touching a line of Python
    -- which is why this is asserted against ``minimal.tcss``, the copy that
    actually renders, and not against ``compose``.
    """
    block = _css_rules(_surf_stylesheet_block())
    columns = {
        POOL4_LEFT_ID: ("SurfPool4Split", "SurfPool4Ratchet", "SurfPool4Flow"),
        POOL4_RAIL_ID: ("SurfPool4Hatches", "SurfPool4Vault"),
    }
    for column, panels in columns.items():
        growing = [p for p in panels if block[p].get("height") == "1fr"]
        assert len(growing) == 1, (
            f"#{column} has {len(growing)} children at `height: 1fr` "
            f"({growing}); exactly one may grow"
        )
        assert block[growing[0]].get("min-height"), (
            f"{growing[0]} carries a `1fr` with no `min-height`: a `1fr` "
            "child cannot overflow a scroll container, it shrinks, so "
            "without a floor it sheds a line per terminal row down to a bare "
            "title with no scrollbar and no trace"
        )
        assert block[f"#{column}"].get("overflow-y") == "auto", column
        assert block[f"#{column}"].get("scrollbar-gutter") == "stable", column


#: The adopted-mainnet ``pool4_discovery_detail``: WP3's sentence, and
#: **nothing else**.
#:
#: It carried ``· tx <66-char hash>`` glued on the end until S18, because
#: ``surf_manager._pool4_cited_detail`` composed it that way. That function is
#: deleted and the citation is its own contract key, so a fixture still
#: merging them asserts a shape the producer cannot emit -- a test passing
#: against a world that does not exist, which is worse than a failing one
#: because nothing ever goes red to say so.
#:
#: Still the long case this test is named for: it renders on HATCHES, which
#: is in the *binding* column, so it is the shape that could move the width
#: pin.
_ADOPTED_DISCOVERY_DETAIL = (
    "adopted 0xa1B997A9861B2b8aC17B4c615089cCC2a5416840: flags, token and "
    "five getters agree"
)

#: The citation, now its own key. Dispatched beside the detail and rendered
#: on its own line, never merged into it.
_ADOPTED_SOURCE_TX = "0x" + "3f" * 32


async def test_the_adopted_discovery_detail_does_not_move_the_pool4_pin() -> None:
    """D8: the day-one payload is the *short* discovery detail, so the pin
    was first measured against the narrow case.

    CLAUDE.md's rule is to measure a data-dependent width against the state
    the data is normally in, and "normally" for this key changes the moment a
    mainnet hook is adopted: the detail goes from one clause to a sentence
    plus a 66-character transaction hash. On the binding column. That is the
    shape that moves pins, so it is measured rather than assumed.

    It does not move this one, and the second half of this test is what
    explains why -- but the property it asserts **changed with S18 and the
    old one was the defect**. It used to assert *constancy*: that the block
    rendered identically at every width. That was true, and it was true
    because ``_discovery_markup`` windowed the detail to its tier's own
    width, a fixed 35 cells, leaving 115 spare columns unused beside an
    ellipsis at 150. The correct property is **monotonicity** -- a wider
    panel renders more and never less -- transcribed from WP4's own
    ``test_the_discovery_block_is_fitted_to_the_panel_not_to_a_constant``.

    A test asserting the old property would now fail *for the right reason*
    and be "fixed" by reverting a real improvement, which is the second-worst
    outcome available; asserting nothing at all would leave the pin half
    green if the widget ever went back to a constant. So the property is
    restated rather than dropped.
    """
    payload = _frozen_payload(
        pool4_network="MAINNET",
        pool4_discovery_state="adopted",
        pool4_discovery_detail=_ADOPTED_DISCOVERY_DETAIL,
        pool4_discovery_source_tx=_ADOPTED_SOURCE_TX,
    )
    assert len(_ADOPTED_DISCOVERY_DETAIL) > 80, (
        "the fixture stopped being the long-detail case it is named for"
    )
    assert "· tx" not in _ADOPTED_DISCOVERY_DETAIL, (
        "the fixture merged the citation back into the detail -- the "
        "producer has not composed it that way since S18"
    )

    widths: dict[int, int] = {}
    for width in (SURF_POOL4_FULL_LAYOUT_COLUMNS, 120, 152, 200):
        async with _pool4_app(payload).run_test(size=(width, 60)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            screen = pilot.app.screen
            hatches = screen.query_one(SurfPool4Hatches)
            body = _region_text(pilot.app, hatches)
            widths[width] = max(
                (len(line.rstrip()) for line in body.split("\n")), default=0
            )
            if width == SURF_POOL4_FULL_LAYOUT_COLUMNS:
                # THE PIN HALF, unchanged: at the pin nothing is marked and
                # nothing is CSS-clipped, on the adopted path.
                assert not _pool4_marked(pilot.app, screen), (
                    "the adopted detail lights a marker at the pin -- the "
                    "pin was measured against the short detail only"
                )
                assert not _clipped_pool4_lines(pilot.app, screen)

    # THE MONOTONICITY HALF, replacing the constancy one.
    ordered = [widths[w] for w in sorted(widths)]
    assert ordered == sorted(ordered), (
        f"HATCHES renders LESS on a wider panel: {widths}"
    )
    assert len(set(ordered)) > 1, (
        f"HATCHES renders identically at every width: {widths} -- the "
        "discovery block is being fitted to a constant again, so the spare "
        "columns of a wide terminal are going unused beside an ellipsis"
    )
    # ...and the citation, which is the part a reader can actually rely on,
    # survives in full at the pin rather than being the thing that got cut.
    async with _pool4_app(payload).run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        hatch_text = _region_text(
            pilot.app, pilot.app.screen.query_one(SurfPool4Hatches)
        )
    assert _ADOPTED_SOURCE_TX[:10] in hatch_text, (
        "the citation does not reach the screen at the pinned width"
    )


# =========================================================================
# The mainnet deployment (2026-09-02): three-way split, inventory ceiling
# =========================================================================


def test_the_cap_headroom_keeps_its_operand_order() -> None:
    """⚠ The sign trap, pinned against its OPERANDS rather than a literal.

    ``pool4_floor_distance`` is ``reserve − floor``. ``pool4_cap_headroom``
    is ``cap − reserve``. The operand order flips between the two so that
    both read positive when healthy -- which is what makes them legible side
    by side, and is also exactly why writing the ceiling half "by analogy"
    with the floor half is such an easy mistake: ``reserve − cap`` gives
    −94.68 on the live mainnet numbers and renders a **binding cap as
    slack**, which is the one reading this key exists to prevent.

    Asserted against the two operands, never against ``+94.683763``. A
    literal would pass just as happily if the fixture and the constant were
    reversed together, which is the shape a mistake here actually takes: the
    author flips the subtraction and updates the expected number to match.
    """
    payload = _mainnet_pool4_payload()
    reserve = payload["pool4_tokens_in_pool"]
    cap = payload["pool4_inventory_cap"]
    floor = payload["pool4_cap_floor"]

    # The premise: on mainnet the cap really is above the reserve and really
    # does bind. Without this the sign assertions below are about a fixture
    # where either order happens to be positive.
    assert cap > reserve > floor, (reserve, cap, floor)

    assert payload["pool4_cap_headroom"] == cap - reserve, (
        "pool4_cap_headroom is not cap − reserve -- if it was written as "
        "reserve − cap it now reports a binding cap as slack"
    )
    assert payload["pool4_cap_headroom"] > 0
    assert payload["pool4_floor_distance"] == reserve - floor, (
        "pool4_floor_distance is not reserve − floor"
    )
    assert payload["pool4_floor_distance"] > 0
    # ...and the two really are opposite orders, which is the whole claim.
    assert payload["pool4_cap_headroom"] != reserve - cap


def test_the_reward_topology_reaches_exactly_two_panels() -> None:
    """WP0 pins the count; this pins that our copy agrees with it.

    ``pool4_reward_path`` says whether a Distributor is in the path and the
    staker leg is split again. It belongs on THE SPLIT (which renders the
    legs) and on HATCHES (which renders the trust surface the extra hop
    adds), and nowhere else -- a third panel acquiring it would be a second
    place for the topology to be stated and therefore a second place for it
    to disagree with itself.
    """
    from tests.data.test_surf_pool4_models import POOL4_WIDGET_SIGNATURES

    mine = {n for n, sig in SURF_WIDGET_SIGNATURES.items()
            if "pool4_reward_path" in sig}
    theirs = {n for n, sig in POOL4_WIDGET_SIGNATURES.items()
              if "pool4_reward_path" in sig}
    assert mine == theirs == {"SurfPool4Split", "SurfPool4Hatches"}, (mine, theirs)
    # The distributor address rides with it on both.
    for panel in mine:
        assert "pool4_distributor_addr" in SURF_WIDGET_SIGNATURES[panel], panel


def test_every_contract_key_is_a_real_parameter_of_its_panel() -> None:
    """A panel must DECLARE the keys the contract says it renders.

    ``**_kwargs`` is mandatory on all five ``update_data`` methods so the
    screen can splat the whole payload and a future key cannot raise. Its
    cost is that a key the widget forgot to declare is swallowed in silence
    -- the dispatch is correct, the kwarg-name check passes, the value
    reaches nothing, and no test anywhere disagrees. Every guard that
    predates this one stayed green through two live instances of exactly
    that, because ``**_kwargs`` accepts everything and therefore cannot tell
    **rendered** from **accepted and dropped** (follow-up S21).

    So the contract is compared against the real signatures, with **no
    exemptions**.

    There was a ``_KEYS_THE_WIDGET_SWALLOWS`` mapping here while the two
    known instances were open -- ``pool4_cap_headroom`` on
    ``SurfPool4Ratchet`` and ``pool4_reward_path`` on ``SurfPool4Hatches``,
    each verified twice (the word appeared nowhere in the widget's source,
    and zeroing the key through the real screen produced no new composited
    line where every other numeric key produced one). It was guarded so that
    a THIRD entry or a FIX of either reddened this test, and the fix is what
    happened: both landed in ``widgets/surf/`` and the handshake fired here.

    The **whole mechanism is gone** rather than left as an empty dict, on
    ``tests/widgets/test_surf_pool4_shared.py``'s ``_PENDING_MIGRATION``
    precedent -- a self-clearing list that has cleared has done its job, and
    an empty one is an invitation to add the next panel to it instead of
    fixing that panel. What the list was protecting is kept as the rule it
    always was: a dispatched key reaching no pixel is a defect, named here
    on the day it is written.
    """
    import inspect

    from tests.data.test_surf_pool4_models import POOL4_WIDGET_SIGNATURES

    swallowed = {}
    for panel, keys in POOL4_WIDGET_SIGNATURES.items():
        cls = _ALL_WIDGET_CLASSES[panel]
        declared = {
            name
            for name, param in inspect.signature(cls.update_data).parameters.items()
            if param.kind is not param.VAR_KEYWORD and name != "self"
        }
        for key in keys:
            if key not in declared:
                swallowed[key] = panel

    assert not swallowed, (
        f"contract keys dispatched to a panel that does not declare them, so "
        f"`**_kwargs` swallows them and they reach no pixel: {swallowed}. "
        "Declare the parameter on that panel's `update_data` and render it "
        "-- do not park it in an exemption list here."
    )


#: Payload/height pairs the row-marker property is swept over.
#:
#: The heights are a band, not a guess, and the PAYLOADS are the part that
#: matters: the one-row boundary this test exists to catch moves with the
#: body's content, so a sweep pinned to one payload catches it only where
#: that payload happens to sit. Measured with the fix disabled, the
#: disagreement appears on the **no-lever** body at 41 rows and nowhere else
#: in 36..53 -- so a lock written against the mainnet payload alone (which
#: is what the first version of this test did) passes with the fix removed
#: and locks nothing. Four payloads, eighteen heights.
_ROW_MARKER_SWEEP = [
    (name, rows)
    for name in ("no-levers", "ten-levers", "capped-levers", "mainnet")
    for rows in range(36, 54)
]


@pytest.mark.parametrize(
    "payload_name,rows", _ROW_MARKER_SWEEP,
    ids=[f"{n}-{r}" for n, r in _ROW_MARKER_SWEEP],
)
async def test_the_row_marker_agrees_with_the_scrollbar_at_every_height(
    payload_name, rows,
) -> None:
    """``‹ taller`` must be lit exactly when a column is actually scrolling.

    The regression lock for a defect that shipped and was measured rather
    than reasoned about (2026-09-02). ``_show_mode`` and ``on_resize`` defer
    ``_render_title`` through ``call_after_refresh`` because the newly-shown
    body has not been laid out when they return -- correct, and at the
    **one-row** boundary still one pass short. A column whose content
    exceeds its height by exactly one row acquires its scrollbar on a later
    pass, so the title was composed while ``_rail_is_cut()`` still said
    ``False`` and nothing recomposed it.

    The result was the marker DARK on a body that was scrolling, at exactly
    the height where a reader most needs it: one row from fitting. WP5 saw
    this shape, could not separate it from its own dispatch injection, and
    reported it as unverified rather than dressing it up -- which was the
    right call, and it is real.

    Note what this asserts and what it does not: it compares the marker
    against the columns' **own** ``show_vertical_scrollbar``, not against a
    height threshold. A literal would go stale the next time a panel gains a
    line; the property cannot. ``_rail_is_cut`` was never wrong -- it
    returned ``True`` throughout -- so a test of that method alone would
    have stayed green. Only what reached a pixel was wrong, so that is what
    is measured.
    """
    payload = {
        "no-levers": lambda: _pool4_hatch_payload(0),
        "ten-levers": lambda: _pool4_hatch_payload(10),
        "capped-levers": lambda: _pool4_hatch_payload(12),
        "mainnet": _mainnet_pool4_payload,
    }[payload_name]()
    async with _pool4_app(payload).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        rail = screen.query_one(f"#{POOL4_RAIL_ID}")
        scrolling = (
            left.show_vertical_scrollbar or rail.show_vertical_scrollbar
        )
        lit = TALLER_HINT in _screen_text(pilot.app).split("\n")[0]

    assert lit is scrolling, (
        f"{payload_name} at {rows} rows: a column is "
        f"{'scrolling' if scrolling else 'not scrolling'} but the marker is "
        f"{'lit' if lit else 'dark'} -- the title was composed before the "
        "layout settled and nothing recomposed it"
    )
