"""WP4 -- the POOL4 rail panels: THE RATCHET, sIMD VAULT, HATCHES.

Everything here asserts against **composited output**
(``app.screen._compositor.render_strips()``), joining segments **per row**
first and then rows by newline. Joining every ``Segment`` with a newline
splits one painted row into several apparent lines the moment a row carries
two styles -- and every row on these panels carries at least two (a dim label
and an undimmed value), so a test written the naive way would pass while the
user saw something else.

Content width, not terminal width
---------------------------------
Each panel is a ``Vertical`` holding one ``Static`` with ``padding: 0 1``, so
a composited row is ``" " + content`` padded out to the terminal. :func:`
_content_widths` strips exactly that one leading column back off and drops
the title row, because the two width pins each panel exports are *content*
pins: the title cannot shed anything, so it is excluded from the tier
decision and from the pin it feeds.

The width pins are asserted with ``==`` against the widest line the panel
actually paints, which is what makes them fail in **both** directions -- a pin
set one too low and a pin set one too high both redden the same assertion.
The threshold sweeps then pin the *behaviour* on both sides of it.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.data.surf_models import (
    POOL4_DISCOVERY_SOURCES,
    POOL4_HATCH_SCOPES,
    POOL4_REWARD_PATHS,
)
from maxpane_dashboard.widgets.sparkline_common import SPARK_CHARS
from maxpane_dashboard.widgets.surf import _pool4 as P
from maxpane_dashboard.widgets.surf import pool4_hatches as H
from maxpane_dashboard.widgets.surf import pool4_ratchet as R
from maxpane_dashboard.widgets.surf import pool4_vault as V
from maxpane_dashboard.widgets.surf.pool4_hatches import SurfPool4Hatches
from maxpane_dashboard.widgets.surf.pool4_ratchet import SurfPool4Ratchet
from maxpane_dashboard.widgets.surf.pool4_vault import SurfPool4Vault

# ---------------------------------------------------------------------------
# Synthetic payloads, shaped by docs/surf_pool4_contract.md §0.2 / §0.3.
# WP4 depends on WP0 only; these are not fixtures of anything on chain, they
# are the contract's own shapes with plausible Sepolia-scale values in them.
# ---------------------------------------------------------------------------

RATCHET_HEALTHY = dict(
    pool4_network="SEPOLIA",
    pool4_tokens_in_pool=152030338.5414,
    pool4_cap_floor=50000000.0,
    pool4_floor_distance=102030338.5414,
    pool4_floor_distance_pct=204.06,
    pool4_burned_supply_pct=3.24,
    pool4_total_supply=1000000000.0,
    # The ceiling half, live on both chains as of 2026-09-02. The cap sits on
    # the inventory (equal to within 12 wei on mainnet *and* Sepolia), so the
    # fixture keeps them equal: a cap that tracks rather than binds is the
    # normal state, and a fixture where it bound would be the unusual one.
    pool4_inventory_cap=152030338.5414,
    pool4_cap_headroom=0.0,
    pool4_cap_decay_per_day=1000.0,
    pool4_reserve_series=[[float(i), 150000000.0 + i * 1000] for i in range(20)],
    pool4_eth_in_pool=0.0057231,
    pool4_position_liquidity=1.2345e19,
    pool4_current_tick=-34567,
    pool4_ref_tick=-34000,
    pool4_backstop_centred=True,
    pool4_as_of_hhmm="12:34",
)

#: Mainnet at the hour pool4 went live -- every number a live read from
#: ``docs/imd_pool4_mainnet.md``, none of them from the docs site. Kept beside
#: the Sepolia-scale fixture rather than replacing it because both chains are
#: live states the panel must render: mainnet is four orders of magnitude
#: smaller, and it is the one where ``capDecayTokensPerDay()`` returns a rate
#: rather than the no-decay sentinel.
RATCHET_MAINNET = dict(
    RATCHET_HEALTHY,
    pool4_network="MAINNET",
    pool4_tokens_in_pool=5487.3465,
    pool4_inventory_cap=5487.3465,
    pool4_cap_headroom=0.0,
    pool4_cap_floor=1000.0,
    pool4_cap_decay_per_day=1000.0,
    pool4_floor_distance=4487.3465,
    pool4_floor_distance_pct=448.73,
    pool4_eth_in_pool=3.7976,
    pool4_current_tick=72761,
    pool4_ref_tick=72667,
)

VAULT_HEALTHY = dict(
    pool4_network="SEPOLIA",
    pool4_share_price=1.0421,
    pool4_share_price_delta_pct=0.1234,
    pool4_vault_assets=1200000.0,
    pool4_vault_shares=1150000.0,
    pool4_drip_per_day=12500.0,
    pool4_drippable=1200.0,
    pool4_can_drip=True,
    pool4_backlog_imd=250000.0,
    pool4_backlog_days=20.0,
    pool4_implied_apr_pct=4.15,
    pool4_as_of_hhmm="12:34",
)

#: The burn sink only ever appears on a hatch *row*, never in the four-line
#: address block, so it is the marker for "the row's address column is being
#: drawn" that the ladder tests key off.
BURN_SINK = "0x000000000000000000000000000000000000dEaD"

HATCHES_HEALTHY = dict(
    pool4_network="SEPOLIA",
    pool4_discovery_state="not-discovered",
    pool4_discovery_detail="no self-post in the announce channel names a pool4 hook",
    pool4_hook_addr="0xa1B997A9f6bB5F0aD3e02C0Fa2B7cE0Ad2Bd6840",
    pool4_token_addr="0xB37d5488a1e9a4Ff8B4F1D8fC0b0d2d4a6A2Cc82",
    pool4_vault_addr="0x1600E1c4bE0aB0d1f4a0a2f0eFb1c0d2E3f4dc17cc",
    pool4_distributor_addr="0x9046739E1535B40EfBe6AB3f45d0024b690eCA30",
    # Mainnet's shape, and the widest member of POOL4_REWARD_PATHS -- so the
    # compact pin is measured against the widest row the panel can render
    # rather than against whichever word this capture happened to carry.
    pool4_reward_path="via-distributor",
    pool4_dripper_addr="0xe6D3De6daEAf327fCA42745f1998FcD989e00884",
    pool4_hatches=[
        {"scope": "vault", "label": "owner", "state": "renounced",
         "detail": None, "addr": None, "addr_known": False},
        {"scope": "dripper", "label": "rewards", "state": "live",
         "detail": None,
         "addr": "0x4dBE1782b0aC0dE1f2a3B4c5D6e7F8a9B0c188449B",
         "addr_known": True},
        {"scope": "hook", "label": "rebalance", "state": "open",
         "detail": "backstop rebalance enabled", "addr": None,
         "addr_known": False},
        {"scope": "hook", "label": "burn sink", "state": "live",
         "detail": None, "addr": BURN_SINK, "addr_known": True},
        # The distributor's two levers, and they are the reason this scope
        # exists: `rescue` is `emergencyWithdraw` (drain it) and `dripper` is
        # `setDripper` (re-point the entire rewards path at another contract).
        {"scope": "distributor", "label": "rescue", "state": "live",
         "detail": "emergencyWithdraw", "addr": None, "addr_known": False},
        {"scope": "distributor", "label": "dripper", "state": "live",
         "detail": "setDripper re-points rewards", "addr": None,
         "addr_known": False},
        # **Bonding is a RESERVE, not a live product** (D1, and the docs say
        # it three times: "reserves, not live products" §05, "the reserve is
        # live; the bond market isn't" §07).
        #
        # This row has now been wrong in both directions. It said
        # `deployed/unknown · "no contract on either chain"`, which a reader
        # arriving after the launch takes as "bonding does not exist" while 6%
        # of every retired batch accrues to a live reserve inside
        # RewardDistributor. Then it said `live · "40% of rewards"`, which
        # reads as the bond market being open. It is not; it opens at $4.
        #
        # The honest statement is three-part -- the SHARE is live, the RESERVE
        # is live and readable as `heldBonding`, the MARKET is not -- and only
        # the third belongs in a `state` word. `closed` is the vocabulary
        # member that says a market is not open without claiming the thing
        # behind it is absent.
        # 17 cells exactly. The hatch grid's last cell is sized to
        # ``_fmt.long_addr``'s form, and a row with no address gets the same
        # 17 columns for its detail -- so the honest wording has to fit there
        # or it is truncated to "reserve accruing…" and the market's closure
        # never reaches the screen. Reported to WP7 as a constraint on the
        # producer's string rather than worked around by widening the cell,
        # which would take the rail's need past the body's width pin.
        {"scope": "bond", "label": "deployed", "state": "closed",
         "detail": "reserve, opens $4", "addr": None,
         "addr_known": False},
    ],
    pool4_as_of_hhmm="12:34",
)

#: The adopted-mainnet ``pool4_discovery_detail``: WP3's sentence, **verbatim
#: and nothing else**. The ``· tx`` clause that used to be welded onto its tail
#: is gone -- WP0 gave the citation its own key and WP7 stopped merging, which
#: is what closed finding S18 at the source.
_ADOPTED_DETAIL = (
    "adopted 0xa1B997A9861B2b8aC17B4c615089cCC2a5416840 — flags, token and "
    "four getters agree"
)

#: The citation, on its own key. After amendment A27 this is the **only
#: unforgeable** artifact in the whole discovery path: a ``0x2840``-shaped
#: address mines in ~20,000 tries, four of the five getters are liveness
#: checks and ``token()`` is a value the candidate's own contract picks. It is
#: a pointer, not a credential -- the chain stays the authority.
_SOURCE_TX = "0x" + "3f" * 32

#: The text budget ``SurfPool4Hatches`` really gets at the pinned body width,
#: **measured inside ``#surf-pool4-left`` rather than in this harness**: at
#: ``screens/surf.SURF_POOL4_FULL_LAYOUT_COLUMNS = 106`` the panel is 50
#: columns and its child ``Static``'s ``padding: 0 1`` leaves 48.
#:
#: Hand-typed rather than imported, on the same footing as
#: ``test_surf_screen.POOL4_LEFT_NEED``: a widget test that imported the
#: screen's seam would follow it silently wherever it went, and the point of
#: the number here is that S18's evidence must reach the screen at *this*
#: width. If WP8 moves the seam this literal is stale and should be
#: re-measured, not re-derived.
HATCHES_PINNED_PANEL_COLUMNS = 50
HATCHES_PINNED_BUDGET = HATCHES_PINNED_PANEL_COLUMNS - 2

#: Members a panel deliberately fits to the **panel** rather than to its tier,
#: and which therefore cannot be part of a tier pin. HATCHES' discovery detail
#: is elastic by design after S18: it uses whatever columns it is given, so a
#: pin measured with it present would measure the terminal, not the panel.
#: ``test_the_discovery_detail_is_fitted_to_the_panel_not_to_a_constant``
#: covers what the pin no longer can.
_ELASTIC_KEYS = {
    "SurfPool4Hatches": ("pool4_discovery_detail", "pool4_discovery_source_tx"),
}


def _pin_payload(cls, payload):
    """*payload* without the panel's elastic members -- see :data:`_ELASTIC_KEYS`."""
    drop = _ELASTIC_KEYS.get(cls.__name__, ())
    return {k: v for k, v in payload.items() if k not in drop}


_PANELS = (
    (SurfPool4Ratchet, R, RATCHET_HEALTHY),
    (SurfPool4Vault, V, VAULT_HEALTHY),
    (SurfPool4Hatches, H, HATCHES_HEALTHY),
)

_MODULE_DIR = pathlib.Path(R.__file__).parent


# ---------------------------------------------------------------------------
# Composited-output helpers
# ---------------------------------------------------------------------------


async def _render(cls, payload=None, size=(100, 40)):
    """Mount one panel, feed it *payload*, return ``(widget, lines)``.

    ``lines`` are composited **rows**: every ``Segment`` of a strip joined
    first, so a row carrying a dim label and a bright value is one line here
    exactly as it is one line on screen.
    """

    class _A(App):
        def compose(self):
            yield cls()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(cls)
        if payload is not None:
            widget.update_data(**payload)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        lines = ["".join(seg.text for seg in strip).rstrip() for strip in strips]
        return widget, lines


async def _rendered_height(cls, payload, size=(100, 60)) -> int:
    """The panel's real rendered height, measured **while it is mounted**.

    :func:`_render` returns after its app context has closed, so a height read
    from the widget it hands back is stale -- which is why the first version of
    the ``1fr`` floor test never bit. Measured here inside the context, and
    from ``size.height`` rather than from a count of non-blank composited rows,
    because blank rows are exactly what a painted-only count hides and exactly
    what made eleven rendered rows look like ten.
    """

    class _A(App):
        def compose(self):
            yield cls()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(cls)
        widget.update_data(**payload)
        await pilot.pause()
        return widget.size.height


def _painted(lines):
    """Only the rows that carry something."""
    return [line for line in lines if line.strip()]


def _content_widths(lines):
    """Content width of every painted row **below the title**, in cells.

    One leading column is the child ``Static``'s own ``padding: 0 1``; it is
    removed so the number compares against the panel's content pins rather
    than against the terminal. Measured with ``cell_len``, never ``len()``.
    """
    painted = _painted(lines)[1:]
    widths = []
    for line in painted:
        assert line.startswith(" "), f"unexpected left padding: {line!r}"
        widths.append(cell_len(line) - 1)
    return widths


def _body(lines) -> str:
    return "\n".join(_painted(lines))


def _line_starting(lines, label: str) -> str:
    """The one painted row whose content begins with *label*."""
    for line in _painted(lines):
        if line.strip().startswith(label):
            return line.strip()
    raise AssertionError(f"no line starts with {label!r} in:\n{_body(lines)}")


def _ngrams(word: str, n: int = 3) -> set[str]:
    flat = "".join(word.lower().split())
    return {flat[i:i + n] for i in range(max(len(flat) - n + 1, 0))}


def _assert_tristate(yes: str, no: str, unknown: str) -> None:
    """The house tri-state rule: three distinct words, and the ``None`` word
    shares no substring with either confident answer.

    ``ready`` / ``not yet`` / ``unknown`` is the precedent
    (``SurfBurnPipeline._ready_word``); ``READY`` / ``NOT READY`` /
    ``UNKNOWN`` is the bug it exists to prevent, because a row that says
    ``NOT READY`` reads as ``READY`` when it is scanned rather than read.

    The comparison is **pairwise across all three words**, not just the
    ``None`` word against the other two. An earlier version of this helper
    checked only the ``None`` word and was therefore green against
    ``centred`` / ``not centred`` / ``unknown`` -- the exact defect it is
    named for, since the word that swallows the positive answer there is the
    *negative* one. Proven by mutation: swapping ``drifted`` for
    ``not centred`` left the whole file green until this loop was widened.

    The test is a shared three-character run after whitespace is flattened,
    which is what catches the near-misses a substring check alone misses:
    ``off-centre`` fails it against ``centred``, and ``not centred``
    flattens to ``notcentred`` and fails on ``centred`` outright.
    """
    words = (yes, no, unknown)
    assert len(set(words)) == 3
    for a in words:
        for b in words:
            if a is b:
                continue
            assert a not in b, f"{a!r} is a substring of {b!r}"
            shared = _ngrams(a) & _ngrams(b)
            assert not shared, f"{a!r} shares {shared} with {b!r}"


# ---------------------------------------------------------------------------
# Panel titles -- the network word, everywhere, always
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_every_panel_title_ends_with_the_network_word(cls, mod, payload):
    _w, lines = await _render(cls, payload)
    title = _painted(lines)[0].strip()
    assert title.startswith(mod.TITLE)
    assert title.endswith("· SEPOLIA") or "· SEPOLIA" in title


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_a_panel_title_never_goes_networkless(cls, mod, payload):
    """``· —`` when ``pool4_network is None`` -- a title never simply drops
    the suffix, because a Sepolia number under an unmarked title is fictional
    presented as live (plan §5, R4).
    """
    _w, lines = await _render(cls, dict(payload, pool4_network=None))
    title = _painted(lines)[0].strip()
    assert f"· {P.NETWORK_UNKNOWN}" in title
    assert "SEPOLIA" not in title
    assert "MAINNET" not in title


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_network_suffix_survives_a_hostile_network_word(cls, mod, payload):
    """The word is producer-owned but still stripped and escaped: a payload
    carrying markup must not reach the parser as markup.
    """
    _w, lines = await _render(cls, dict(payload, pool4_network="[/x]"))
    title = _painted(lines)[0].strip()
    assert "[/x]" not in title
    assert f"· {P.NETWORK_UNKNOWN}" in title


# ---------------------------------------------------------------------------
# THE RATCHET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_ratchet_labels_the_floor_observed():
    _w, lines = await _render(SurfPool4Ratchet, RATCHET_HEALTHY)
    floor = _line_starting(lines, "floor")
    assert R.FLOOR_WORD in floor
    assert "50.0M" in floor


@pytest.mark.asyncio
async def test_the_ratchet_never_promises_the_floor():
    """R2's copy control. ``capFloor`` binds the swap path on the evidence of
    one wei-exact stop (amendment A7); it is not a guarantee, the hook is
    unverified source, and no "safe until" / "burns stop at" phrasing may be
    added either.
    """
    for payload in (
        RATCHET_HEALTHY,
        dict(RATCHET_HEALTHY, pool4_floor_distance=-1200000.0,
             pool4_floor_distance_pct=-2.4),
        {},
    ):
        _w, lines = await _render(SurfPool4Ratchet, payload)
        body = _body(lines).lower()
        for forbidden in ("guarantee", "guaranteed", "enforced", "safe until",
                          "burns stop"):
            assert forbidden not in body


@pytest.mark.asyncio
async def test_a_reserve_below_its_floor_is_a_number_not_an_error():
    """Amendment A7: launch 1 sits below its own floor today, because a
    backstop rebalance can move the reserve where a swap cannot. The distance
    is signed, never clamped to zero, and carries no warning glyph.
    """
    payload = dict(
        RATCHET_HEALTHY,
        pool4_tokens_in_pool=48800000.0,
        pool4_floor_distance=-1200000.0,
        pool4_floor_distance_pct=-2.4,
    )
    _w, lines = await _render(SurfPool4Ratchet, payload)
    row = _line_starting(lines, "vs floor")
    assert "-1.2M" in row
    assert "-2.4%" in row
    assert "+" not in row              # not clamped to a zero-or-above reading
    assert "⚠" not in _body(lines)
    assert R.UNAVAILABLE_LINE not in _body(lines)


@pytest.mark.asyncio
async def test_the_backstop_tristate_renders_three_distinct_words():
    words = {}
    for value, key in ((True, "yes"), (False, "no"), (None, "unknown")):
        _w, lines = await _render(
            SurfPool4Ratchet, dict(RATCHET_HEALTHY, pool4_backstop_centred=value)
        )
        # The word rides on the `tick` row now -- beside the two ticks it is a
        # statement about -- so it is the last clause of that line.
        words[key] = _line_starting(lines, "tick").split("·")[-1].strip()
    _assert_tristate(words["yes"], words["no"], words["unknown"])
    assert words["yes"] == "centred"
    assert words["unknown"] == "unknown"


@pytest.mark.asyncio
async def test_the_ratchet_never_prints_an_infinity_or_a_nan():
    """``pool4_floor_distance_pct`` is ``None`` when the floor is zero or
    unread; the panel must dash it rather than divide.
    """
    payload = dict(
        RATCHET_HEALTHY, pool4_cap_floor=0.0, pool4_floor_distance_pct=None
    )
    _w, lines = await _render(SurfPool4Ratchet, payload)
    body = _body(lines)
    assert "inf" not in body.lower()
    assert "nan" not in body.lower()
    assert "∞" not in body
    assert "--" in _line_starting(lines, "vs floor")


@pytest.mark.asyncio
async def test_the_reserve_sparkline_is_absent_rather_than_flat_without_history():
    """A flat baseline beside a live reserve claims the reserve has not
    moved. An absent sparkline says "no history yet", which is the true
    statement on a cold cache.
    """
    _w, cold = await _render(
        SurfPool4Ratchet, dict(RATCHET_HEALTHY, pool4_reserve_series=[])
    )
    assert not any(ch in _body(cold) for ch in SPARK_CHARS)
    assert "152.0M" in _body(cold)          # the panel is otherwise healthy

    _w, warm = await _render(SurfPool4Ratchet, RATCHET_HEALTHY)
    assert any(ch in _body(warm) for ch in SPARK_CHARS)


@pytest.mark.asyncio
async def test_a_single_dead_getter_is_one_dash_not_a_dead_ratchet():
    """R1's field-by-field degradation: the hook is unverified source, so one
    reverting getter must be one ``None`` inside an otherwise-healthy panel.
    """
    _w, lines = await _render(
        SurfPool4Ratchet, dict(RATCHET_HEALTHY, pool4_current_tick=None,
                               pool4_ref_tick=None)
    )
    body = _body(lines)
    assert R.UNAVAILABLE_LINE not in body
    assert "152.0M" in body
    assert "--" in _line_starting(lines, "tick")


@pytest.mark.asyncio
async def test_a_wholly_unread_ratchet_says_so():
    _w, lines = await _render(SurfPool4Ratchet, {"pool4_network": "SEPOLIA"})
    assert R.UNAVAILABLE_LINE in _body(lines)


# ---------------------------------------------------------------------------
# THE RATCHET's ceiling half -- inventoryCap and its decay (2026-09-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cap_the_reserve_and_the_floor_read_top_to_bottom():
    """The reserve sits between a decaying cap above and an owner-settable
    floor below. One mechanism, one panel, in mechanism order -- which is the
    arrangement that makes "the cap is sitting on the inventory" (true to
    within 12 wei on both chains today) visible at a glance.
    """
    _w, lines = await _render(SurfPool4Ratchet, RATCHET_MAINNET)
    painted = [line.strip() for line in _painted(lines)]
    order = [
        next(i for i, line in enumerate(painted) if line.startswith(label))
        for label in ("cap", "reserve", "floor", "vs floor")
    ]
    assert order == sorted(order), painted


@pytest.mark.asyncio
async def test_the_no_decay_sentinel_never_prints_as_a_rate_of_zero():
    """The trap, and it is the shape that reaches a reader unnoticed.

    Sepolia's ``capDecayTokensPerDay()`` returns ``2**128 - 1`` -- a sentinel
    meaning *no decay*, which divided into whole IMD is ~3.4e20 per day: a
    confident, absurd number with nothing about it that looks like an error.
    WP7 resolves it to the representable zero ``0.0``; this panel must turn
    that into a **word**. ``0.00 IMD/day`` would assert a decay rate the chain
    never reported, and would read as "the cap decays, just very slowly".
    """
    _w, lines = await _render(
        SurfPool4Ratchet, dict(RATCHET_HEALTHY, pool4_cap_decay_per_day=0.0)
    )
    cap = _line_starting(lines, "cap")
    assert R.NO_DECAY_WORD in cap, cap
    assert "0.00" not in cap
    assert "/day" not in cap
    assert "e+" not in cap.lower()


@pytest.mark.asyncio
async def test_unread_no_decay_and_a_real_rate_all_read_differently():
    """Three states, three renderings, no shared substring between the two
    that a reader might confuse -- the same discipline the tri-states get.
    ``--`` is "we could not look", :data:`NO_DECAY_WORD` is "we looked and it
    does not decay", and a rate is a rate.
    """
    seen = {}
    for label, value in (("unread", None), ("no-decay", 0.0), ("rate", 1000.0)):
        _w, lines = await _render(
            SurfPool4Ratchet,
            dict(RATCHET_HEALTHY, pool4_cap_decay_per_day=value),
        )
        seen[label] = _line_starting(lines, "cap")
    assert len(set(seen.values())) == 3, seen
    assert R.NO_DECAY_WORD not in seen["unread"]
    assert R.NO_DECAY_WORD not in seen["rate"]
    assert "1.0K/day" in seen["rate"]

    # Distinctness alone is too weak, and a mutation proved it: dropping the
    # sentinel branch rendered no-decay as ``0/day``, which is still a third
    # distinct string, so this test stayed green while a neighbouring one
    # caught the defect. What must hold is that the middle state is a **word**
    # -- the cap value's own digits are on the same line, so the assertion is
    # scoped to the cell after the `·` separator.
    cell = seen["no-decay"].split("·")[-1]
    assert not any(ch.isdigit() for ch in cell), cell


@pytest.mark.asyncio
async def test_the_ceiling_half_answers_on_both_chains():
    """**Not** "point it at Sepolia and watch the fields go ``None``."

    That test was written into an earlier draft of the plan and would have
    passed for the wrong reason: both chains answer both getters, only the
    values differ (Sepolia 472,569,750.77 IMD cap and the no-decay sentinel;
    mainnet 5,487.35 and 1,000/day). Absence has to be driven by a getter made
    to revert -- which is what a differently-built future hook looks like --
    so that is what this drives it with.
    """
    for payload in (RATCHET_HEALTHY, RATCHET_MAINNET):
        _w, lines = await _render(SurfPool4Ratchet, payload)
        assert "--" not in _line_starting(lines, "cap")

    _w, lines = await _render(
        SurfPool4Ratchet,
        dict(RATCHET_MAINNET, pool4_inventory_cap=None,
             pool4_cap_decay_per_day=None),
    )
    assert "--" in _line_starting(lines, "cap")
    assert R.UNAVAILABLE_LINE not in _body(lines)      # one dash, not a dead panel


# ---------------------------------------------------------------------------
# sIMD VAULT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_vault_names_the_backlog_as_days_of_runway_at_every_tier():
    """``pool4_backlog_days`` is never a bare number beside a balance. The
    compact tier splits the queue onto two lines rather than shedding the
    phrase -- a raw balance alone is a review failure.
    """
    for container in (100, V.FULL_WIDTH + 1):
        _w, lines = await _render(
            SurfPool4Vault, VAULT_HEALTHY, size=(container, 40)
        )
        body = _body(lines)
        assert V.RUNWAY_WORD in body
        assert "20.0 " + V.RUNWAY_WORD in body
        assert "IMD/day" in body        # the rate is on screen at both tiers


@pytest.mark.asyncio
async def test_the_vault_says_what_the_drip_rate_actually_governs():
    """D2. The drip rate caps **delivery**, not what stakers earn.

    An earlier version of this test asserted the opposite -- that the yield
    itself is rate-limited -- which was a reasonable reading of the mechanism
    and is not what the protocol says the number means (§06: the entitlement
    is the trailing flow set aside for stakers; "the dripper's rate is only a
    cap on how fast that reaches the vault").
    """
    _w, lines = await _render(SurfPool4Vault, VAULT_HEALTHY)
    body = _body(lines)
    assert V.RATE_LIMITED_NOTE in body

    # The forbidden claim, scanned over the whole panel. An earlier version
    # asserted that the words "delivery" and "drip rate" appear -- which they
    # do, on OTHER lines (`DELIVERY_NOT_APR_NOTE` and `DELIVERY_NOTE`), so
    # restoring the old "yield is rate-limited, not flow-limited" sentence
    # left this test green. Proven by mutation. What must hold is that the
    # panel never makes the claim at all.
    lowered = body.lower()
    assert "rate-limited" not in lowered, body
    assert "flow-limited" not in lowered, body


@pytest.mark.asyncio
async def test_our_number_is_never_published_under_the_word_apr():
    """D2's actual defect, and it was a heading rather than a formula.

    ``drip_per_day x 365 / TVL`` is the **delivery cap** annualised. The
    protocol publishes a differently computed APR under that word -- trailing
    seven-day flow against total staked -- and against a deep backlog ours
    understates by a lot (Sepolia's was a year deep) while against an empty one
    it overstates, because nothing can be dripped that has not arrived.

    Two numbers sharing one heading is how a reader concludes one of the two
    sites is lying, so the only place ``APR`` may appear on this panel is in
    the sentence that disclaims it.
    """
    _w, lines = await _render(SurfPool4Vault, VAULT_HEALTHY)
    body = _body(lines)
    assert V.DELIVERY_LABEL in body
    assert V.DELIVERY_NOT_APR_NOTE in body

    # **The heading position specifically.** An earlier version asserted only
    # that every line mentioning "apr" also carried the disclaimer -- which
    # became self-defeating the moment the disclaimer moved onto the number's
    # own line: relabelling the row `apr` produced `apr 4.15% ... not APR`,
    # a line containing both, and the test stayed green. Proven by mutation.
    # What must hold is that no row is *headed* with the word.
    assert V.DELIVERY_LABEL != "apr"
    for line in _painted(lines):
        assert not line.strip().lower().startswith("apr"), line


@pytest.mark.asyncio
async def test_a_suppressed_apr_shows_no_number_and_never_zero_or_infinity():
    """``pool4_implied_apr_pct is None`` means TVL is zero or unread. A ``0%``
    would claim stakers earn nothing; an ``∞`` would claim a division nobody
    performed.
    """
    _w, lines = await _render(
        SurfPool4Vault,
        dict(VAULT_HEALTHY, pool4_vault_assets=0.0, pool4_implied_apr_pct=None),
    )
    apr = _line_starting(lines, V.DELIVERY_LABEL)
    assert V.DELIVERY_SUPPRESSED in apr
    assert not any(ch.isdigit() for ch in apr)
    assert "%" not in apr
    assert "∞" not in apr
    assert "inf" not in _body(lines).lower()


@pytest.mark.asyncio
async def test_a_zero_delivery_rate_is_a_number_and_not_a_missing_read():
    """The zero-needle catch, re-pointed at the row that replaced ``apr``.

    ``pool4_implied_apr_pct == 0.0`` is a real state -- the drip rate is zero,
    so nothing is being delivered -- and it is a different statement from
    "TVL is zero or unread, so this cannot be computed". Retiring the ``apr``
    row took ``tests/test_surf_registration.py``'s ``apr 0.00%`` needle with
    it; the zero is still renderable and the needle text is what went stale.

    Asserted here as well as there, because a zero that cannot be told from a
    missing read is the defect the needle exists for, and this panel should
    not depend on another package's probe table to notice it.
    """
    _w, zero = await _render(
        SurfPool4Vault, dict(VAULT_HEALTHY, pool4_implied_apr_pct=0.0)
    )
    _w, unread = await _render(
        SurfPool4Vault, dict(VAULT_HEALTHY, pool4_implied_apr_pct=None)
    )
    zero_row = _line_starting(zero, V.DELIVERY_LABEL)
    unread_row = _line_starting(unread, V.DELIVERY_LABEL)

    assert "0.00%" in zero_row, zero_row
    assert V.DELIVERY_SUPPRESSED not in zero_row
    assert V.DELIVERY_SUPPRESSED in unread_row
    assert "0.00%" not in unread_row
    assert zero_row != unread_row


@pytest.mark.asyncio
async def test_the_vault_stays_inside_the_rails_one_fr_floor():
    """VAULT carries the rail's ``1fr`` **because** its line count is a
    constant, so ``min-height: 10`` is a ceiling as much as a floor: a ``1fr``
    child cannot overflow, it shrinks, and an eleventh line is dropped with no
    scrollbar, no ``‹ taller`` and no trace while ``virtual_size`` goes on
    reporting ten.

    Nine leaves one row of slack, so the next line added here fails this
    instead of vanishing. Counted over composited output, including the blank
    rows a painted-only count would hide -- which is how eleven looked like
    ten in the first place.
    """
    _VAULT_1FR_MIN_HEIGHT = 10        # screens/surf.py, restated deliberately
    for payload in (VAULT_HEALTHY, {}, dict(VAULT_HEALTHY, pool4_can_drip=None)):
        rendered = await _rendered_height(SurfPool4Vault, payload)
        assert rendered <= _VAULT_1FR_MIN_HEIGHT, (
            f"sIMD VAULT renders {rendered} rows against a 1fr floor of "
            f"{_VAULT_1FR_MIN_HEIGHT}; the overflow is shed in silence"
        )


@pytest.mark.asyncio
async def test_the_drip_tristate_renders_three_distinct_words():
    words = {}
    for value, key in ((True, "yes"), (False, "no"), (None, "unknown")):
        _w, lines = await _render(
            SurfPool4Vault, dict(VAULT_HEALTHY, pool4_can_drip=value)
        )
        cell = _line_starting(lines, "next").split(None, 1)[1]
        words[key] = cell.split("·")[0].strip()
    _assert_tristate(words["yes"], words["no"], words["unknown"])
    assert words["yes"] == "ready"
    assert words["no"] == "not yet"


@pytest.mark.asyncio
async def test_a_missing_share_price_baseline_is_not_a_zero_delta():
    """``None`` means "no second reading yet", which is a different statement
    from ``+0.00%`` and from a failed read.
    """
    _w, lines = await _render(
        SurfPool4Vault, dict(VAULT_HEALTHY, pool4_share_price_delta_pct=None)
    )
    share = _line_starting(lines, "share")
    assert V.NO_BASELINE in share
    assert "0.00%" not in share
    assert "1.042100" in share          # the price itself is unaffected


@pytest.mark.asyncio
async def test_a_wholly_unread_vault_says_so():
    _w, lines = await _render(SurfPool4Vault, {"pool4_network": "SEPOLIA"})
    assert V.UNAVAILABLE_LINE in _body(lines)


# ---------------------------------------------------------------------------
# HATCHES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discovery_not_run_and_not_discovered_say_different_things():
    """"Discovery has not run" and "discovery ran and found nothing" are two
    states, and rendering one word for both is the FARM/HOUR-SAVED defect.
    """
    _w, unrun = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_discovery_state=None,
                               pool4_discovery_detail=None)
    )
    _w, swept = await _render(SurfPool4Hatches, HATCHES_HEALTHY)
    unrun_line = _line_starting(unrun, "discovery")
    swept_line = _line_starting(swept, "discovery")
    assert unrun_line != swept_line
    assert H.DISCOVERY_UNKNOWN in unrun_line
    assert "not-discovered" not in unrun_line
    assert "not-discovered" in swept_line


# ---------------------------------------------------------------------------
# S18 -- the adoption's evidence has to reach the screen, and the state/
# citation pair has to stay readable as a pair
# ---------------------------------------------------------------------------


def _discovery_block(lines) -> list[str]:
    """The ``discovery`` label row's own indented continuation rows."""
    painted = _painted(lines)
    start = next(
        i for i, line in enumerate(painted) if line.strip().startswith("discovery")
    )
    out = []
    for line in painted[start + 1:]:
        if not line.startswith(" " * (H._DISCOVERY_LABEL_COLS + H._GAP + 1)):
            break
        out.append(line.strip())
    return out


def _verdict_line(lines) -> str:
    """Just the ``discovery <state> · <provenance>`` row.

    The provenance clause rides on this row, and the row below it can carry
    the *citation's* own warning -- two different disclosures with the same
    glyph. A test that asserted over the whole block therefore caught the
    wrong ``⚠``; scoping to the verdict row is what makes the assertion about
    provenance rather than about whichever warning happened to be nearby.
    """
    return next(
        line.strip() for line in _painted(lines)
        if line.strip().startswith("discovery")
    )


def _discovery_pair(lines) -> str:
    """The verdict word **and** its block, which is the unit the semantics
    table is about.

    ``_discovery_block`` alone excludes the label row, and the label row is
    where the state word lives -- so comparing blocks made ``rejected`` + hash
    and ``adopted`` + hash look identical when the detail was held constant.
    The panel distinguishes them perfectly well; the extraction did not.
    """
    painted = _painted(lines)
    start = next(
        i for i, line in enumerate(painted) if line.strip().startswith("discovery")
    )
    return "\n".join([painted[start].strip(), *_discovery_block(lines)])


async def _hatches(state, detail, source_tx, panel=None):
    return await _render(
        SurfPool4Hatches,
        dict(HATCHES_HEALTHY, pool4_discovery_state=state,
             pool4_discovery_detail=detail,
             pool4_discovery_source_tx=source_tx),
        size=(panel or HATCHES_PINNED_PANEL_COLUMNS, 60),
    )


@pytest.mark.asyncio
async def test_the_citation_renders_on_its_own_line_at_the_pinned_width():
    """S18's fix, at the width that matters.

    The citation used to arrive welded to the tail of a ~94-character sentence
    and was therefore the first thing any fitting pass dropped -- so what
    reached the screen was the address the reader could already see four lines
    below, and none of the evidence. It now has its own line and its own
    width, and cannot be crowded out.
    """
    _w, lines = await _hatches("adopted", _ADOPTED_DETAIL, _SOURCE_TX)
    block = _discovery_block(lines)
    cite = [line for line in block if line.startswith(H.CITATION_LABEL + " ")]
    assert len(cite) == 1, block
    assert _SOURCE_TX[:34] in cite[0], cite[0]


@pytest.mark.asyncio
async def test_the_citation_keeps_its_prefix_when_it_is_truncated():
    """A hash is a pointer, and the prefix is the half an explorer searches on,
    so it is truncated head-first with a trailing ``…`` -- never middle-elided
    into a form that finds nothing.
    """
    _w, lines = await _hatches("adopted", _ADOPTED_DETAIL, _SOURCE_TX)
    cite = next(
        line for line in _discovery_block(lines)
        if line.startswith(H.CITATION_LABEL + " ")
    )
    shown = cite[len(H.CITATION_LABEL) + 1:]
    assert shown.startswith("0x3f3f3f3f")
    assert shown.endswith("…")
    assert _SOURCE_TX.startswith(shown[:-1])      # a real prefix, not a window

    # Wide enough, and the whole hash is there with nothing elided.
    _w, wide = await _hatches("adopted", _ADOPTED_DETAIL, _SOURCE_TX, panel=140)
    assert any(_SOURCE_TX in line for line in _discovery_block(wide))


@pytest.mark.asyncio
async def test_the_citation_is_never_crowded_out_by_the_detail():
    """The property the two-key split buys, stated so it cannot regress.

    However long the producer's sentence gets, it competes for its **own**
    line, not for the citation's. This is the invariant a merged string could
    not offer at any width.
    """
    _w, lines = await _hatches(
        "adopted", "adopted " + "x" * 400, _SOURCE_TX
    )
    block = _discovery_block(lines)
    assert any(line.startswith(H.CITATION_LABEL + " ") for line in block), block
    assert _SOURCE_TX[:20] in " ".join(block)


@pytest.mark.asyncio
async def test_the_four_state_and_citation_combinations_read_differently():
    """``surf_models.Pool4Discovery``'s table, rendered.

    Each row is a distinct statement and the panel must not collapse any two
    of them -- above all the two ``None``-citation rows, which are an expected
    absence and an unauditable adoption respectively.
    """
    rendered = {}
    for label, state, tx in (
        ("not-discovered/none", "not-discovered", None),
        ("rejected/hash", "rejected", _SOURCE_TX),
        ("adopted/hash", "adopted", _SOURCE_TX),
        ("adopted/none", "adopted", None),
    ):
        _w, lines = await _hatches(state, _ADOPTED_DETAIL, tx)
        rendered[label] = _discovery_pair(lines)
    assert len(set(rendered.values())) == 4, rendered


@pytest.mark.asyncio
async def test_an_adoption_with_no_citation_does_not_look_like_an_expected_absence():
    """The row worth surfacing, and the reason the citation is a separate key.

    ``not-discovered`` + ``None`` is the day-one path and says nothing; it
    would be noise to print "nothing to cite" on every launch, and printing it
    is how a reader learns to skip the row that matters. ``adopted`` + ``None``
    is an adoption nothing can audit, and it gets a warning line **in the
    position the citation would have occupied** -- so the absence is what the
    reader sees, not an empty space.
    """
    _w, expected = await _hatches("not-discovered", _ADOPTED_DETAIL, None)
    _w, unauditable = await _hatches("adopted", _ADOPTED_DETAIL, None)

    assert H.UNAUDITABLE_LINE not in "\n".join(_discovery_block(expected))
    assert H.UNAUDITABLE_LINE in "\n".join(_discovery_block(unauditable))
    assert "⚠" in "\n".join(_discovery_block(unauditable))

    # And an adoption that *can* be audited says nothing of the kind.
    _w, healthy = await _hatches("adopted", _ADOPTED_DETAIL, _SOURCE_TX)
    assert H.UNAUDITABLE_LINE not in "\n".join(_discovery_block(healthy))


@pytest.mark.asyncio
async def test_the_discovery_block_is_fitted_to_the_panel_not_to_a_constant():
    """The original S18 defect, kept pinned after the simplification.

    The block used to be windowed to its **tier's** width -- a constant 35
    cells -- so it rendered identically at 106 columns and at 260, with 115
    spare columns going unused beside an ellipsis. A wider panel must render
    more, and never less.
    """
    widths = {}
    for panel in (HATCHES_PINNED_PANEL_COLUMNS, 70, 100, 140):
        _w, lines = await _hatches(
            "adopted", _ADOPTED_DETAIL, _SOURCE_TX, panel=panel
        )
        widths[panel] = max(cell_len(line) for line in _discovery_block(lines))
    assert len(set(widths.values())) > 1, widths
    assert sorted(widths) == sorted(widths, key=widths.get), widths


@pytest.mark.asyncio
async def test_a_truncated_detail_does_not_light_the_marker():
    """``‹ widen`` means a whole column of the hatch grid was shed.

    The discovery detail is a one-line elastic **summary** whose truncation
    announces itself in its own ``…``, and after A27 every clause in it
    describes a forgeable gate -- so more columns buy a reader nothing they
    could have relied on. The citation, which they could, is on its own line
    and is never dropped. Marking here would light the marker at the pinned
    width on every adopted payload, which is how a marker stops meaning
    anything.
    """
    widget, lines = await _hatches("adopted", "adopted " + "x" * 400, _SOURCE_TX)
    block = _discovery_block(lines)
    assert any(line.endswith("…") for line in block), block
    assert widget._widen is False
    assert H.WIDEN_HINT not in _body(lines)


@pytest.mark.asyncio
async def test_a_hostile_detail_and_address_do_not_raise():
    """``detail`` and ``addr`` are third-party strings. A markup string handed
    to ``Static.update()`` defers its parse into the message pump and raises
    outside the screen's ``try/except``; parsed here it can only skip a line.

    ``[$warning]`` is the second half of the trap: a ``$``-prefixed theme
    token is resolvable by Textual's own renderer but **not** by
    ``rich.text.Text.from_markup``, which these panels use on purpose -- it
    raises at *render* time, inside ``Static.update``, if it survives to a
    style.
    """
    rows = [
        {"scope": "hook", "label": "[/x]", "state": "[bold]live",
         "detail": "[$warning]pwn[/]", "addr": None, "addr_known": False},
        {"scope": "[/x]", "label": "owner", "state": "live",
         "detail": None, "addr": "0x[$warning]dead", "addr_known": True},
        "not a dict",
        None,
    ]
    _w, lines = await _render(
        SurfPool4Hatches,
        dict(HATCHES_HEALTHY, pool4_hatches=rows,
             pool4_discovery_detail="[/x][bold]$warning",
             pool4_hook_addr="0x[/x]"),
    )
    body = _body(lines)
    assert "[/x]" not in body
    assert "[$warning]" not in body
    assert H.TITLE in body


@pytest.mark.asyncio
async def test_the_address_block_dashes_an_unread_address():
    """A blank would read as "there is no such contract"."""
    _w, lines = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_vault_addr=None)
    )
    assert "--" in _line_starting(lines, "vault ")


@pytest.mark.asyncio
async def test_unread_levers_and_an_empty_lever_list_say_different_things():
    _w, unread = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_hatches=None)
    )
    _w, empty = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_hatches=[])
    )
    assert H.UNAVAILABLE_LINE in _body(unread)
    assert H.UNAVAILABLE_LINE not in _body(empty)
    assert "no levers reported" in _body(empty)


@pytest.mark.asyncio
async def test_a_wholly_unread_hatches_panel_says_so():
    _w, lines = await _render(SurfPool4Hatches, {"pool4_network": "SEPOLIA"})
    assert H.UNAVAILABLE_LINE in _body(lines)


@pytest.mark.asyncio
async def test_the_lever_list_is_capped():
    rows = [
        dict(HATCHES_HEALTHY["pool4_hatches"][0], label=f"lever{i}")
        for i in range(H.MAX_ROWS + 5)
    ]
    _w, lines = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_hatches=rows),
        size=(100, 60),
    )
    body = _body(lines)
    assert "lever0" in body
    assert f"lever{H.MAX_ROWS}" not in body


@pytest.mark.asyncio
async def test_the_headroom_renders_between_both_of_its_operands():
    """WP0 requires the subtraction be checkable against the numbers shown.

    ``cap`` is the row above and ``reserve`` the row below, so a reader can
    verify ``cap - reserve`` without leaving the block.
    """
    _w, lines = await _render(SurfPool4Ratchet, RATCHET_MAINNET)
    painted = [line.strip() for line in _painted(lines)]
    idx = {
        label: next(i for i, line in enumerate(painted) if line.startswith(label))
        for label in ("cap", "headroom", "reserve")
    }
    assert idx["cap"] < idx["headroom"] < idx["reserve"], painted


@pytest.mark.asyncio
async def test_the_headroom_is_cap_minus_reserve_and_not_the_other_way_round():
    """**The sign trap, verified.**

    ``pool4_floor_distance`` is ``reserve - floor``; ``pool4_cap_headroom`` is
    ``cap - reserve`` -- the operand order flips. Both read positive when
    healthy, which is exactly why copying the sibling's shape inverts the
    meaning without announcing it: mainnet's measured gap renders ``+94.68``
    one way and ``-94.68`` the other, and the wrong one draws a **binding cap
    as slack**.

    Driven with a cap genuinely above the reserve, so the two orders disagree
    in sign rather than merely in magnitude.
    """
    _w, lines = await _render(
        SurfPool4Ratchet,
        dict(RATCHET_MAINNET, pool4_inventory_cap=5582.03,
             pool4_tokens_in_pool=5487.35, pool4_cap_headroom=94.68),
    )
    headroom = _line_starting(lines, "headroom")
    assert "+94.7" in headroom, headroom
    assert "-94.7" not in headroom


@pytest.mark.asyncio
async def test_an_inventory_above_its_cap_renders_negative_and_is_not_clamped():
    """A negative headroom is a real state -- the inventory is above the cap --
    and clamping it would report a binding cap as merely exhausted slack.
    Same rule the floor half already follows in the other direction.
    """
    _w, lines = await _render(
        SurfPool4Ratchet, dict(RATCHET_MAINNET, pool4_cap_headroom=-94.68)
    )
    headroom = _line_starting(lines, "headroom")
    assert "-94.7" in headroom, headroom
    assert "+" not in headroom
    assert "⚠" not in _body(lines)
    assert R.UNAVAILABLE_LINE not in _body(lines)


@pytest.mark.asyncio
async def test_the_headroom_reaches_the_compositor_at_all():
    """The hole this closed: a key can be declared by WP0, dispatched by WP8
    and silently absorbed by ``**_kwargs`` with every existing guard green,
    because the contract sweep cannot see a swallowed keyword. So this is
    verified the way WP8 found it -- by **rendering**: moving the value must
    move the composited output.
    """
    _w, a = await _render(
        SurfPool4Ratchet, dict(RATCHET_MAINNET, pool4_cap_headroom=1234.5)
    )
    _w, b = await _render(
        SurfPool4Ratchet, dict(RATCHET_MAINNET, pool4_cap_headroom=None)
    )
    assert _body(a) != _body(b)
    assert "1.2K" in _body(a)


# ---------------------------------------------------------------------------
# HATCHES -- mainnet's new trust surfaces, and the provenance disclosure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_distributor_is_named_in_the_address_block():
    """Mainnet routes ``rewardsRecipient()`` to a Reward Distributor that has
    no Sepolia counterpart, making the vault three hops away instead of two.
    It is listed in path order between the vault and the dripper.
    """
    _w, lines = await _render(SurfPool4Hatches, HATCHES_HEALTHY)
    row = _line_starting(lines, "dist ")
    assert "0x9046739E" in row, row


@pytest.mark.asyncio
async def test_the_distributor_hatches_disclose_both_of_its_powers():
    """The reason the scope exists. Its owner can ``emergencyWithdraw`` (drain
    it) and ``setDripper`` (re-point the entire rewards path at another
    contract) -- a trust surface that did not exist two days ago.
    """
    _w, lines = await _render(SurfPool4Hatches, HATCHES_HEALTHY, size=(120, 60))
    body = _body(lines)
    assert "rescue" in body
    assert "dripper" in body
    assert body.count("dist ") >= 3       # the address row plus two levers


def test_every_hatch_scope_fits_its_column():
    """The property, not the abbreviation.

    ``distributor`` is eleven characters against a seven-column grid cell.
    Widening the cell would take this panel 45 -> 49 content columns, its
    column need 49 -> 53, and the body pin 106 -> 107 -- and the standing rule
    is shorten the value, not raise the pin. So it is abbreviated; what is
    asserted is that **every** member of the closed vocabulary renders inside
    the column, which a sixth scope would redden rather than be clipped by.
    """
    from rich.cells import cell_len as _cl
    for scope in POOL4_HATCH_SCOPES:
        shown = H._SCOPE_SHORT.get(scope, scope)
        assert _cl(shown) <= H._SCOPE_COLS, f"{scope!r} renders as {shown!r}"
    # And the map does not carry entries for words that never needed one.
    for key in H._SCOPE_SHORT:
        assert key in POOL4_HATCH_SCOPES, key
        assert _cl(key) > H._SCOPE_COLS, f"{key!r} did not need shortening"


def test_the_source_vocabulary_agrees_with_the_contract():
    """Both directions. A fourth source added to ``POOL4_DISCOVERY_SOURCES``
    must redden here rather than fall through to the unattributed branch and
    quietly look like one of these three; and a word invented in the widget
    with no contract behind it reddens too.
    """
    assert set(H.SOURCE_WORDS) == set(POOL4_DISCOVERY_SOURCES)


@pytest.mark.asyncio
async def test_a_docs_adoption_and_a_signed_adoption_do_not_look_the_same():
    """**The disclosure the operator's decision was conditioned on.**

    The announce channel has not named the mainnet hook, so ``pool4.imd.fun/
    docs`` was accepted as a candidate source. That widens the trust surface
    and the chain fingerprint does not close it -- a ``0x2840``-shaped address
    mines in ~20,000 tries, four of the five getters are pure liveness checks,
    and ``token()`` is the candidate's own choice. Prevention was not
    available; disclosure was, and it is delivered here. A dev-signed adoption
    and a docs-sourced one looking alike would silently undo it.
    """
    rendered = {}
    for source in ("self-post", "docs"):
        _w, lines = await _render(
            SurfPool4Hatches,
            dict(HATCHES_HEALTHY, pool4_discovery_state="adopted",
                 pool4_discovery_source_tx=_SOURCE_TX,
                 pool4_discovery_source=source),
        )
        rendered[source] = _verdict_line(lines)

    assert rendered["self-post"] != rendered["docs"]
    assert "⚠" in rendered["docs"], rendered["docs"]
    assert "⚠" not in rendered["self-post"], rendered["self-post"]
    assert "docs" in rendered["docs"]
    assert "self-post" in rendered["self-post"]


@pytest.mark.asyncio
async def test_a_missing_or_unknown_source_reads_at_least_as_weakly_as_docs():
    """``None`` is where a producer bug comes to rest, and a renderer treating
    it as "nothing to say" would draw a docs adoption identically to a signed
    one -- undoing the disclosure by omission. So an unrecorded source, an
    explicitly ``unattributed`` one, and a word this build has never heard of
    are all warned about, and none of them may render as ``self-post``.
    """
    weak = {}
    for label, source in (
        ("none", None), ("unattributed", "unattributed"), ("bogus", "BASE-post"),
    ):
        _w, lines = await _render(
            SurfPool4Hatches,
            dict(HATCHES_HEALTHY, pool4_discovery_state="adopted",
                 pool4_discovery_source_tx=_SOURCE_TX,
                 pool4_discovery_source=source),
        )
        weak[label] = _verdict_line(lines)
        assert "⚠" in weak[label], (label, weak[label])
        assert "self-post" not in weak[label], (label, weak[label])

    # An unrecorded source stays distinguishable from a declared one, so a
    # producer bug does not hide inside the vocabulary member.
    assert weak["none"] != weak["unattributed"]
    assert H.UNSOURCED_WORD.strip("⚠ ") in weak["none"]


@pytest.mark.asyncio
async def test_provenance_is_stated_only_where_there_is_an_adoption():
    """``not-discovered`` and ``rejected`` have nothing adopted to attribute,
    and a provenance note on the day-one path every launch is how a reader
    learns to skip the clause that matters. Same asymmetry as the citation.
    """
    for state in ("not-discovered", "rejected"):
        _w, lines = await _render(
            SurfPool4Hatches,
            dict(HATCHES_HEALTHY, pool4_discovery_state=state,
                 pool4_discovery_source="docs"),
        )
        assert "via" not in _verdict_line(lines)


@pytest.mark.asyncio
async def test_a_bond_reserve_never_renders_as_an_open_market():
    """D1, and this panel has now been wrong in both directions.

    "No bond contract is named by the hook" is literally true of the *hook*
    and reads as "bonding does not exist" -- while 6% of every retired batch
    accrues to a live reserve inside ``RewardDistributor``. Its replacement,
    "live at 40% of the reward share", reads as *the bond market is open*. It
    is not: it opens at $4 per IMD, and until then nothing is sold and the
    reserve only grows.

    Three states a single word flattens -- the same discipline the four-state
    citation work applies one panel over. What this pins is the half the
    widget owns: given the honest row, the panel must render the reserve and
    the market's closure distinguishably, and must not paint the bond row with
    the word it paints a live owner key with.
    """
    _w, lines = await _render(SurfPool4Hatches, HATCHES_HEALTHY, size=(120, 60))
    bond = next(
        line.strip() for line in _painted(lines) if line.strip().startswith("bond")
    )
    assert "closed" in bond, bond
    assert "reserve" in bond, bond
    assert "opens" in bond, bond
    # The reserve is not the market: the row must not carry the liveness word
    # that the vault's and hook's owner rows carry.
    assert "live" not in bond, bond
    # And it must not read as absence either -- the other half of D1.
    assert "no bond" not in bond
    assert "absent" not in bond


@pytest.mark.asyncio
async def test_the_reward_path_disambiguates_the_distributors_dash():
    """**The reason this key exists**, and it is not cosmetic.

    ``pool4_distributor_addr`` is ``None`` both when there is no Distributor
    (Sepolia's shape) and when the getter that would have named one failed --
    and the hook's views are batched with ``allowFailure=True``, so the second
    is a routine payload. Those two readings are three times apart on the
    headline percentage: 15% of gross reaches stakers under ``direct``, 4.5%
    under ``via-distributor``. A bare ``--`` cannot tell them apart; the word
    beside it can.
    """
    seen = {}
    for label, path in (
        ("direct", "direct"), ("via", "via-distributor"), ("unread", None),
    ):
        _w, lines = await _render(
            SurfPool4Hatches,
            dict(HATCHES_HEALTHY, pool4_distributor_addr=None,
                 pool4_reward_path=path),
        )
        seen[label] = _line_starting(lines, "dist ")
    assert len(set(seen.values())) == 3, seen
    assert "direct" in seen["direct"]
    assert "via-distributor" in seen["via"]
    assert H.UNKNOWN_PATH_WORD in seen["unread"]
    assert all("--" in line for line in seen.values()), seen


@pytest.mark.asyncio
async def test_an_unknown_reward_path_never_guesses_a_shape():
    """``None`` and a word this build has never heard of both read as unread.
    Guessing a leg is the error the key exists to prevent, and "unread" is not
    a guess.
    """
    for path in (None, "sideways", ""):
        _w, lines = await _render(
            SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_reward_path=path)
        )
        row = _line_starting(lines, "dist ")
        assert H.UNKNOWN_PATH_WORD in row, (path, row)
        assert "direct" not in row
        assert "via-distributor" not in row


def test_the_reward_path_vocabulary_agrees_with_the_contract():
    """Both directions, so a third path member reddens here rather than
    falling through to the unread branch and quietly looking like an outage.
    """
    assert set(H.REWARD_PATH_WORDS) == set(POOL4_REWARD_PATHS)


@pytest.mark.asyncio
async def test_the_reward_path_reaches_the_compositor_at_all():
    """Verified by rendering, not by reading the signature -- a keyword
    swallowed by ``**_kwargs`` is invisible to every signature-shaped guard.
    """
    _w, a = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_reward_path="direct")
    )
    _w, b = await _render(
        SurfPool4Hatches, dict(HATCHES_HEALTHY, pool4_reward_path="via-distributor")
    )
    assert _body(a) != _body(b)


@pytest.mark.asyncio
async def test_every_lever_the_producer_emits_survives_the_row_cap():
    """The two rows WP8 needed came out of **whitespace, not levers.**

    The producer emits exactly twelve, and the two a cap of ten would have
    dropped are the two that changed most recently: the hook's burn sink
    (mainnet moved it from ``0x…dEaD`` to the BurnExecutor) and bonding's
    deployed row. Hiding a trust surface to save a row inverts what this panel
    is for.
    """
    assert H.MAX_ROWS >= 12
    rows = HATCHES_HEALTHY["pool4_hatches"]
    _w, lines = await _render(SurfPool4Hatches, HATCHES_HEALTHY, size=(120, 60))
    body = _body(lines)
    for row in rows:
        assert row["label"] in body, row


# ---------------------------------------------------------------------------
# Width ladders -- each pin asserted with ``==`` (fails both directions), then
# the threshold swept on both sides of it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_full_width_pin_is_the_widest_full_tier_line(cls, mod, payload):
    """``==``, not ``<=``: a pin set one column too low and a pin set one
    column too high both redden this. Measured in situ, inside the real
    container, so the child ``Static``'s own padding is paid for.
    """
    widget, lines = await _render(cls, _pin_payload(cls, payload), size=(100, 40))
    assert widget._widen is False
    assert max(_content_widths(lines)) == mod.FULL_WIDTH


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_compact_width_pin_is_the_widest_compact_tier_line(
    cls, mod, payload
):
    """Rendered one column below the full pin: narrow enough to force the
    compact tier, wide enough that nothing is clipped, so the number measured
    is the tier's own width and not CSS's.
    """
    widget, lines = await _render(
        cls, _pin_payload(cls, payload), size=(mod.FULL_WIDTH + 1, 40)
    )
    assert widget._widen is True
    assert max(_content_widths(lines)) == mod.COMPACT_WIDTH


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_widen_marker_lights_exactly_at_the_pin(cls, mod, payload):
    """Both directions of the threshold. The budget is the container width
    minus the child ``Static``'s two padding columns, so the full tier
    survives at ``FULL_WIDTH + 2`` and is shed at ``FULL_WIDTH + 1``.
    """
    widget, lines = await _render(cls, payload, size=(mod.FULL_WIDTH + 2, 40))
    assert widget._widen is False
    assert mod.WIDEN_HINT not in _body(lines)

    widget, lines = await _render(cls, payload, size=(mod.FULL_WIDTH + 1, 40))
    assert widget._widen is True
    assert mod.WIDEN_HINT in _body(lines)


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_marker_shortens_rather_than_letting_css_eat_it(cls, mod, payload):
    """A panel that can bind must be able to *mark*.

    A pool4 title carries the network word as well as the panel name, so
    ``THE RATCHET · SEPOLIA  ‹ widen`` genuinely does not fit a narrow rail
    where a bare ``LAUNCHPAD ACTIVITY  ‹ widen`` would. ``_pool4.title_text``
    therefore places the longest hint that fits -- ``WIDEN_HINT``, then
    ``GLYPH_HINT`` -- and places none at all when neither does, because a
    marker CSS eats is a marker the reader never sees.
    """
    base = len(mod.TITLE) + len(" · SEPOLIA")

    wide, lines = await _render(cls, payload, size=(mod.FULL_WIDTH + 1, 40))
    assert wide._widen is True
    assert mod.WIDEN_HINT in _body(lines)

    # Just too narrow for `‹ widen`, wide enough for `‹`.
    narrow = base + len(mod.WIDEN_HINT) + 2 + 2 - 1
    widget, lines = await _render(cls, payload, size=(narrow, 40))
    title = _painted(lines)[0].rstrip()
    assert widget._widen is True
    # `…` is the assertion that bites here. ``GLYPH_HINT in title`` alone
    # cannot tell a *placed* glyph from a ``‹ widen`` that CSS clipped down to
    # ``‹ wid…`` -- the glyph is a substring of the phrase -- so a fitter that
    # never shortened passed this test until the ellipsis check was added.
    assert "…" not in title, title
    assert title.endswith(f"  {mod.GLYPH_HINT}"), title
    assert not title.endswith(mod.WIDEN_HINT), title

    # And directly against the fitter, where CSS cannot flatter it: three
    # tiers, and the narrowest places no marker at all.
    full_room = base + 2 + len(mod.WIDEN_HINT)
    assert P.title_text(mod.TITLE, "SEPOLIA", True, full_room).endswith(
        f"  {mod.WIDEN_HINT}"
    )
    assert P.title_text(mod.TITLE, "SEPOLIA", True, full_room - 1).endswith(
        f"  {mod.GLYPH_HINT}"
    )
    assert (
        P.title_text(mod.TITLE, "SEPOLIA", True, base + 2)
        == f"{mod.TITLE} · SEPOLIA"
    )


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_marker_and_the_shed_content_never_disagree(cls, mod, payload):
    """The property, not the literal: at every width in the ladder's band,
    the full-tier-only content is on screen **iff** the marker is dark.

    A marker that lights while its panel is still drawing everything, or a
    panel that sheds a column with the marker dark, are the two halves of the
    silent-clipping failure this repo's layout rules exist to prevent.
    """
    marker_of = {
        SurfPool4Ratchet: lambda body: any(ch in body for ch in SPARK_CHARS),
        SurfPool4Vault: lambda body: V.RATE_LIMITED_NOTE in body,
        SurfPool4Hatches: lambda body: "…00dEaD" in body,
    }[cls]
    for width in range(mod.FULL_WIDTH - 6, mod.FULL_WIDTH + 7):
        widget, lines = await _render(cls, payload, size=(width, 60))
        body = _body(lines)
        full_tier_drawn = marker_of(body)
        assert full_tier_drawn is (widget._widen is False), (
            f"{cls.__name__} at container width {width}: "
            f"widen={widget._widen} full_tier_drawn={full_tier_drawn}"
        )
        # The glyph, not the phrase: inside this band a narrow panel falls
        # back from `‹ widen` to `‹` rather than letting CSS eat the marker.
        assert (mod.GLYPH_HINT in body) is widget._widen


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_the_title_keeps_its_name_and_its_network_at_every_width(
    cls, mod, payload
):
    """``‹ widen`` is **appended**, never substituted, so the panel's name and
    its network word both survive the marker.
    """
    for width in (mod.FULL_WIDTH + 20, mod.FULL_WIDTH + 1):
        _w, lines = await _render(cls, payload, size=(width, 40))
        title = _painted(lines)[0].strip()
        assert mod.TITLE in title
        assert "SEPOLIA" in title


# ---------------------------------------------------------------------------
# Contract-shaped sweeps over all three panels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_a_bare_update_data_renders_the_unavailable_state(cls, mod, payload):
    """No required constructor argument, no required keyword: the screen
    composes these bare and the contract sweep instantiates and calls them
    with nothing at all.
    """
    widget, lines = await _render(cls, {})
    body = _body(lines)
    assert mod.UNAVAILABLE_LINE in body
    assert f"· {P.NETWORK_UNKNOWN}" in _painted(lines)[0]
    assert widget._widen is False


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_an_unknown_future_key_is_swallowed(cls, mod, payload):
    """``**_kwargs`` is mandatory: the screen splats the whole payload and a
    key added to the contract later must not raise here.
    """
    _w, lines = await _render(
        cls, dict(payload, pool4_something_new=1, feed_items=[], as_of_hhmm="09:09")
    )
    assert mod.TITLE in _body(lines)


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_a_panel_paints_its_title_before_any_payload(cls, mod, payload):
    _w, lines = await _render(cls, payload=None)
    assert mod.TITLE in _body(lines)


@pytest.mark.parametrize("cls,mod,payload", _PANELS)
@pytest.mark.asyncio
async def test_a_resize_re_lays_the_panel_out(cls, mod, payload):
    """The panels hold the raw payload, not formatted lines, so a terminal
    resize picks a new tier rather than repainting the old one.
    """

    class _A(App):
        def compose(self):
            yield cls()

    async with _A().run_test(size=(100, 40)) as pilot:
        widget = pilot.app.query_one(cls)
        widget.update_data(**payload)
        await pilot.pause()
        assert widget._widen is False
        await pilot.resize_terminal(mod.FULL_WIDTH + 1, 40)
        await pilot.pause()
        assert widget._widen is True


# ---------------------------------------------------------------------------
# Structural
#
# The purity walk, the "no copied sparkline" check and the ``$``-theme-token
# guard used to live here over a hand-typed list of three modules. They moved
# to ``tests/widgets/test_surf_pool4_shared.py``, which **discovers** the
# pool4 widget modules instead, so WP5's two panels and any pool4 module
# written later are covered the day they land rather than the day someone
# remembers to extend a list. What stays here is the one thing that is about
# these three panels specifically.
# ---------------------------------------------------------------------------

_SOURCES = {
    name: (_MODULE_DIR / name).read_text()
    for name in ("pool4_ratchet.py", "pool4_vault.py", "pool4_hatches.py")
}


def test_the_rail_panels_import_the_shared_title_rather_than_building_one():
    """Amendment A13: one ``network_word``, one ``panel_title``, in
    ``_pool4.py``. These three must **call** the shared fitter and must not
    declare a title, a separator or a hint vocabulary of their own -- two
    panels spelling the network word differently is a reader-visible defect
    (``THE SPLIT · —`` beside ``THE RATCHET · BASE``) before it is a test
    failure.

    ``test_surf_pool4_shared`` asserts the same thing across *every* pool4
    module by discovery; this is the narrower, more legible statement about
    the three panels this package owns.
    """
    for name, source in _SOURCES.items():
        assert "from maxpane_dashboard.widgets.surf._pool4 import" in source, name
        assert "title_text(" in source, name
        assert "def network_word" not in source, name
        assert "def panel_title" not in source, name
        assert "WIDEN_HINT = " not in source, name
        assert "GLYPH_HINT = " not in source, name
        assert "TITLE_SEP = " not in source, name

    # The three modules and the shared one agree on the marker vocabulary by
    # identity, not by two equal strings that could drift apart.
    assert R.WIDEN_HINT is V.WIDEN_HINT is H.WIDEN_HINT is P.WIDEN_HINT
    assert R.GLYPH_HINT is V.GLYPH_HINT is H.GLYPH_HINT is P.GLYPH_HINT
