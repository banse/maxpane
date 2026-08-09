"""SurfScreen -- surfsurf.eth Mission Control as a Textual Screen.

Layout (the house pattern; the hero owns the top row outright and the
signals ride a right-hand rail above the market)::

    #title-bar         SURF · IMD $x.xx · parity ±x.x% · feed #N (age)
    #hero-row          SurfHero (full width, four boxes)
    #middle-row        SurfFeed (3fr)          | #surf-right-rail (2fr)
                       SurfDevActivity (3fr)   |   SurfSignals (auto)
                         -- one or the other,  |   SurfMarket  (1fr)
                            toggled with `c`   |
    #separator
    #bottom-row        SurfNft (full width)
    StatusBar

The hero was half a row wide until 2026-08-09 and shared it with the
signals panel. Two things were wrong with that. Its four boxes had to
share a ``3fr`` half, which left each of them 13 content columns on a
139-column terminal -- narrow enough that the box copy had to shed whole
fields to fit (see ``widgets/surf/hero.py``), and the ``full`` tier was
unreachable below ~220 columns, i.e. on no terminal anybody owns. And the
row was pinned at ``height: 10`` for a ``height: 7`` widget, so three rows
under the boxes were reserved and blank on every launch. Full width buys
each box ~26 columns at the same 139, which reaches the ``full`` tier, and
the row now sizes to its content.

**Every row but the middle one sizes to its content**, and the middle row
alone carries ``1fr``. That is what makes a tall terminal grow the feed
instead of stranding whitespace: previously ``#bottom-row`` also carried
``1fr`` and took half the slack for a panel with eight lines in it, which
left roughly a fifth of the screen empty above the status bar.

Deliberate choices, in the FWA screen's terms (see screens/fwa.py, whose
docstring carries the full rationale):

1. **``c`` toggles the announce feed and the dev-activity table** in the
   middle-left slot. Both stay mounted and both are dispatched to on every
   refresh, so toggling is a visibility flip with no refetch and no blank
   first frame. The rail to their right is outside the swap, so it never
   flickers.
2. **Every widget update is individually guarded** -- one widget raising must
   never cost the other five their refresh. A *manager* failure touches only
   the StatusBar and leaves the previous frame standing.
3. **Degradation reaches the title bar** (``· degraded: …``), because the
   shared StatusBar API has no ``set_degraded()``.

The screen is clock-free: every time-derived string (``feed_last_post_age_s``,
per-signal ages) arrives pre-computed in the payload. Nothing here consults
the wall clock, so any captured instant replays forever in tests.

Written against the frozen ``SURF_KEYS`` contract, not against
``SurfManager``'s internals -- any object with an awaitable
``fetch_and_compute()`` returning that dict drives it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard import __version__
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.surf_manager import SurfManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "SURF · Mission Control · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: Measured against composited output (both ``c`` views), not estimated --
#: see tests. The width at which ordinary (non-token) feed content, and
#: every other widget, show zero ``‹ widen`` markers in both views.
#:
#: 135 is set by ``SurfFeed``. Swept one column at a time over the real
#: screen in both ``c`` views (125..145, then 150/169/200/240): the feed
#: lights exactly one marker at every width through 134, both views are
#: clean from 135 up, and nothing relights above it.
#:
#: It was 139 before the 2026-08-09 restructure, and 139 was set by
#: ``SurfHero``: four boxes across a ``3fr`` half of the row got 12 content
#: columns at 135 and 13 -- ``hero.MINIMAL_WIDTH`` -- at 139, so a longer
#: unrecognised ``hook_status`` could light a box marker at 137-138. A
#: full-width hero row ends that whole class of sensitivity: each box now
#: gets ~26 content columns at 135, which is the ``full`` tier (24) with
#: headroom, and the hero's own marker is unreachable above 81 columns. The
#: activity panel clears its full tier at 119 and the rail's two panels
#: clear theirs inside a ``2fr`` share well below this, so the feed alone
#: decides the number now.
#:
#: This number deliberately EXCLUDES posts carrying an inherently
#: unbreakable token (a URL glued to a raw tx hash, e.g. by a trailing
#: period with no space -- the real nonce-13 capture's link is 91 columns).
#: SurfFeed correctly truncates such a token and lights its own ``‹ widen``;
#: *this particular capture* clears at 194, and the next real post linking a
#: transaction reproduces the shape at whatever width its own token needs.
#: A fixture containing one therefore cannot be what "full layout" is
#: measured against -- see
#: ``test_a_linked_post_advertises_widen_at_the_full_layout_width``. Do not
#: raise this toward 194 to silence a linked post's marker: that marker is
#: correct, and 194 is past the ~169 columns a laptop gets at the forced
#: 17 pt, i.e. a "full layout" nobody could reach.
SURF_FULL_LAYOUT_COLUMNS = 135


# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` — never raise."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _fmt_usd(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"${out:,.2f}"


def _fmt_signed_pct(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"{out:+.1f}%"


def _fmt_age(value) -> str:
    """``42s`` / ``17m`` / ``23h`` / ``3d`` — or an em-dash for ``None``.

    90 is the seconds/minutes boundary and 90 min the minutes/hours boundary
    (``5400.0`` renders ``90m``); 36 h is the hours/days boundary — the same
    tiers the sparkline axis uses.
    """
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if seconds != seconds or seconds < 0:
        return _EMDASH
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds <= 90 * 60:
        return f"{int(seconds // 60)}m"
    if seconds < 36 * 3600:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _fmt_degraded(sources) -> str:
    """``· degraded: logs, market`` — or an empty string when all is well.

    Only ``None``/``[]`` (or anything else falsy) genuinely mean "nothing is
    degraded" and may render empty. Every other input must render
    *something* visibly wrong, even if it is a shape the manager should
    never actually produce: a bare ``except: return ""`` here would let a
    malformed ``degraded`` value collapse the title bar to the healthy line
    on the single most prominent row of the screen, which is the exact
    failure this whole project exists to prevent.
    """
    if not sources:
        return ""

    # A bare string is one group name, not a sequence of one-letter groups
    # (``"logs"`` iterates to ``"l", "o", "g", "s"`` otherwise).
    if isinstance(sources, (str, bytes)):
        sources = [sources]

    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        # Truthy but not iterable (an int, a float, ...) -- an unexpected
        # shape the manager never emits today, but "unreachable today" is
        # not a reason to fail toward looking healthy.
        return " · degraded: ?"

    if not names:
        return " · degraded: ?"
    return " · degraded: " + ", ".join(names)


def _title_line(data: dict) -> str:
    """Compose the meta row (PRD §4).

    Ordered by what must survive a narrow terminal: warnings before the
    version tail, because ``#title-bar`` is one row high and the tail is what
    gets clipped. Parity renders with the em-dash fallback rather than a
    zero: a dead market source must never read as perfect parity.
    """
    feed_age = _fmt_age(data.get("feed_last_post_age_s"))
    line = (
        f"SURF · IMD {_fmt_usd(data.get('imd_price_usd'))} · "
        f"parity {_fmt_signed_pct(data.get('parity_pct'))} · "
        f"feed #{_fmt_int(data.get('feed_nonce'))} ({feed_age})"
    )

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    line += _fmt_degraded(data.get("degraded"))
    # Plain, unmarked version tail: the StatusBar already carries the dim
    # version, and markup here would only complicate every assertion on the
    # end of this string.
    line += f" · v{__version__}"
    return line


class SurfScreen(RefreshGuard, Screen):
    """surfsurf.eth Mission Control dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Feed/Activity", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "surf-refresh"

    # Structural fallback only. WP6 restates these in themes/minimal.tcss
    # (one owner) the way the FWA block does, app-stylesheet rules then beat
    # DEFAULT_CSS. They live here so the screen is reviewable and correctly
    # proportioned on its own, under any theme that has no surf block. The
    # two copies must stay in agreement -- edit both or neither.
    #
    # `#hero-row` is `height: auto` and carries NO vertical padding. SurfHero
    # is a height-7 widget whose boxes hold five content lines inside a
    # height-7 frame; one row of vertical padding here clips the bottom
    # border off the screen, which is the FWA hero-clipping bug. `auto` also
    # replaces the old `height: 10`, whose three spare rows were the dead
    # space above the feed.
    #
    # `#middle-row` is the ONLY `1fr` row on the screen, so every row a
    # taller terminal adds lands in the feed. `#bottom-row` is `auto`: the
    # NFT panel has eight lines and used to be handed half the slack.
    #
    # SurfSignals is `auto` inside the rail (a title plus six detector rows);
    # SurfMarket takes the rail's remainder. Giving *signals* the remainder
    # instead would push the market off the bottom of a short terminal, and
    # any vertical padding on either costs the sixth detector row -- BURN --
    # while the panel still looks complete. tests/test_surf_registration.py
    # asserts all six reach the compositor.
    #
    # The rail scrolls (`overflow-y: auto`) purely as the short-terminal
    # guard: sizing the rows to their content means the rail is only as tall
    # as the middle row, so below ~29 terminal rows BURN no longer fits. No
    # scrollbar is drawn at any normal height; when one is, it is what makes
    # that loss visible instead of silent.
    DEFAULT_CSS = """
    SurfScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    SurfScreen #hero-row {
        height: auto;
        margin: 1 0 0 0;
    }
    SurfScreen SurfHero {
        width: 1fr;
        padding: 0 1;
    }
    SurfScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    SurfScreen SurfFeed {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfDevActivity {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen #surf-right-rail {
        width: 2fr;
        height: 1fr;
        overflow-y: auto;
    }
    SurfScreen SurfSignals {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    SurfScreen SurfMarket {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    SurfScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    SurfScreen #bottom-row {
        height: auto;
        margin: 0 0 1 0;
    }
    SurfScreen SurfNft {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "SurfManager",
        poll_interval: int = 30,
        name: str = "surf",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Which widget owns the middle-left slot: "feed" or "activity".
        self._active_view: str = "feed"

    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def action_toggle_view(self) -> None:
        """Swap the announce feed and the dev-activity table in one slot.

        Both widgets stay mounted and both keep being updated on every
        refresh, so toggling is a pure visibility flip -- no refetch, no
        repopulate, no empty frame.
        """
        self._active_view = "activity" if self._active_view == "feed" else "feed"
        showing_feed = self._active_view == "feed"
        try:
            self.query_one(SurfFeed).display = showing_feed
            self.query_one(SurfDevActivity).display = not showing_feed
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("surf view toggle failed: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield SurfHero()

        with Horizontal(id="middle-row"):
            # Two views of one slot, toggled with ``c``. The activity table
            # is created hidden rather than on demand so it keeps receiving
            # every refresh and is already populated when toggled to.
            yield SurfFeed()
            activity = SurfDevActivity()
            activity.display = False
            yield activity
            # The right rail: signals on top, market underneath. Sibling of
            # the two swapped views rather than a child of either, so ``c``
            # cannot take it with it.
            with Vertical(id="surf-right-rail"):
                yield SurfSignals()
                yield SurfMarket()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield SurfNft()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("surf")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            # Belt and braces: WP4's SurfManager.fetch_and_compute() never
            # raises -- it guarantees the full SURF_KEYS dict with None
            # values under every failure combination. This branch covers a
            # mis-wired manager or a future manager edit that breaks that
            # guarantee, not the specified outage path (see
            # test_screen_survives_all_none_payload for the real one).
            logger.debug("surf refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=MANAGER_FAILURE_SECONDS,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        if not isinstance(data, dict):  # defensive: a broken manager contract
            logger.debug("surf refresh returned %r, not a dict", type(data))
            return

        # Title bar
        try:
            self.query_one("#title-bar", Static).update(_title_line(data))
        except Exception as exc:
            logger.debug("Failed to update title bar: %s", exc)

        # Hero (the full-width top row)
        try:
            self.query_one(SurfHero).update_data(
                hook_status=data.get("hook_status"),
                lp_liquidity=data.get("lp_liquidity"),
                lp_imd=data.get("lp_imd"),
                lp_weth=data.get("lp_weth"),
                lp_owner_ok=data.get("lp_owner_ok"),
                gate_open=data.get("gate_open"),
                identities_written=data.get("identities_written"),
                imd_supply=data.get("imd_supply"),
                imd_burned_cum=data.get("imd_burned_cum"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfHero: %s", exc)

        # Signals (right rail, top) -- the six detectors
        try:
            self.query_one(SurfSignals).update_data(
                sig_post_state=data.get("sig_post_state"),
                sig_post_detail=data.get("sig_post_detail"),
                sig_post_age_s=data.get("sig_post_age_s"),
                sig_lp_state=data.get("sig_lp_state"),
                sig_lp_detail=data.get("sig_lp_detail"),
                sig_lp_age_s=data.get("sig_lp_age_s"),
                sig_gate_state=data.get("sig_gate_state"),
                sig_gate_detail=data.get("sig_gate_detail"),
                sig_gate_age_s=data.get("sig_gate_age_s"),
                sig_deploy_state=data.get("sig_deploy_state"),
                sig_deploy_detail=data.get("sig_deploy_detail"),
                sig_deploy_age_s=data.get("sig_deploy_age_s"),
                sig_bridge_state=data.get("sig_bridge_state"),
                sig_bridge_detail=data.get("sig_bridge_detail"),
                sig_bridge_age_s=data.get("sig_bridge_age_s"),
                sig_burn_state=data.get("sig_burn_state"),
                sig_burn_detail=data.get("sig_burn_detail"),
                sig_burn_age_s=data.get("sig_burn_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfSignals: %s", exc)

        # Announce feed (middle-row left slot, view A)
        try:
            self.query_one(SurfFeed).update_data(
                feed_items=data.get("feed_items"),
                feed_nonce=data.get("feed_nonce"),
                feed_last_post_age_s=data.get("feed_last_post_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfFeed: %s", exc)

        # Dev activity (middle-row left slot, view B -- hidden, still updated)
        try:
            self.query_one(SurfDevActivity).update_data(
                dev_activity=data.get("dev_activity"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfDevActivity: %s", exc)

        # Market (right rail, bottom)
        try:
            self.query_one(SurfMarket).update_data(
                imd_price_usd=data.get("imd_price_usd"),
                imd_change_24h_pct=data.get("imd_change_24h_pct"),
                imd_vol_24h_usd=data.get("imd_vol_24h_usd"),
                pool_liquidity_usd=data.get("pool_liquidity_usd"),
                fp_price_usd=data.get("fp_price_usd"),
                parity_pct=data.get("parity_pct"),
                supply_series=data.get("supply_series"),
                price_series=data.get("price_series"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfMarket: %s", exc)

        # NFT (bottom row)
        try:
            self.query_one(SurfNft).update_data(
                nft_holders=data.get("nft_holders"),
                nft_transfers_24h=data.get("nft_transfers_24h"),
                nft_dev_holdings=data.get("nft_dev_holdings"),
                nft_written=data.get("nft_written"),
                nft_last_sales=data.get("nft_last_sales"),
                nft_floor=data.get("nft_floor"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfNft: %s", exc)

        # Status bar. A refresh that reaches this line just fetched, so the
        # staleness is honestly 0 without consulting any clock; ``as_of`` is
        # the *payload's* fetch instant and stays inside the widgets' strings.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=0.0,
                error_count=int(_num(getattr(self._data_manager, "_error_count", 0))),
                poll_interval=self._poll_interval,
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
