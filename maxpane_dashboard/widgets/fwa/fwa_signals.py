"""5-row signals panel for the FWA dashboard.

Renders the five analytical signal rows of PRD §5:

1. **Pool temperature** -- seconds since the last request, and therefore which
   way the surcharge is currently flowing.
2. **Buy gate**         -- ``FWATokenHook.externalBuysEnabled()``; the single
   biggest scheduled event for the token, so it gets a red/green state.
3. **Emissions status** -- normally ``emissions ended`` (the primary case, per
   PRD §8); a live countdown only before 2026-08-04T19:01:23Z.
4. **VRF queue depth**  -- pending randomness requests.
5. **Parameter drift**  -- whether a live-read config parameter moved.

Each signal dict is an ``FWASignal`` dump and carries::

    {"label": str, "value_str": str, "indicator": str, "color": str}

Missing keys collapse to safe defaults; a row never crashes and an all-``None``
payload renders ``--`` on every row.

Two rows get extra rendering rules, because colour alone may not carry meaning
(PRD §11):

* **Pool temperature** must name the direction in words (``→ YOU`` /
  ``→ depositors``). The upstream ``value_str`` normally does; when it does not,
  this module appends an explicit ``direction unknown`` rather than leaving the
  cold→hot colour gradient as the only cue.
* **Emissions** must never render a negative countdown. A ``value_str`` that
  still counts down past the hard stop is rewritten to ``emissions ended``.

Row budget: title + spacer + 5 rows = 7 lines, matching ``tal_signals.py``.

Width behaviour
---------------

The panel measures 78 columns in the 2fr right column at a 200-column terminal
and 54 at 140; the longest realistic row (``COLD 41m · surcharge → YOU (100%)``)
needs 37, so the rows normally fit with room to spare. When a row does not fit,
wrapping is the wrong answer here: the panel is 9 lines tall and already uses 7,
so a wrapped row would silently push the last signal off the bottom. Rows are
therefore ``nowrap`` + ``ellipsis`` and the title grows a ``‹ widen`` marker, so
a clipped row is always announced rather than quietly shortened.

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

import re

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from maxpane_dashboard.widgets.address import (
    ICON_COLS,
    MIN_SHORT_COLS,
    PROSE_ADDRESS_RE,
    address_text,
    short_hex,
)
from maxpane_dashboard.widgets.markup_safety import visible_len as _visible_len
from textual.widgets import Static

_DASH = "--"

#: Marker appended to the title when a row had to be clipped.
WIDEN_HINT = "‹ widen"

#: Strips Textual markup so a row can be measured as the user sees it.
_MARKUP = re.compile(r"\[/?[^\[\]]*\]")

#: Rewritten value for an elapsed emissions window (PRD §8, the primary case).
EMISSIONS_ENDED = "emissions ended"

#: Words that prove the pool-temperature row states its direction in text.
_DIRECTION_WORDS = ("you", "depositor", "purchaser")

#: Words that prove the buy-gate row states its state in text.
# "gated" was missing here, so a correctly-read *closed* gate
# ("GATED — no outside buys ...") matched nothing and got "· state unknown"
# appended — a known state rendered as unknown, and it also pushed the row to
# 79 columns so the SIGNALS panel wore "‹ widen" during healthy operation.
_GATE_WORDS = ("open", "closed", "gated", "enabled", "disabled", "blocked", "live")

#: A signed countdown component, e.g. ``-2d`` / ``−13h`` / ``-41s``.
_NEGATIVE_COUNTDOWN = re.compile(r"[-−]\s*\d")

#: A bytes32-shaped hex run inside a PARAM DRIFT value -- hex boundaries on
#: both sides, the same rule ``widgets/address.py``'s own
#: ``PROSE_ADDRESS_RE`` uses, so a shortened run can never eat into an
#: adjacent, unrelated hex digit. Matched, and shortened, *before* any
#: address windowing runs: once shortened it no longer contains an unbroken
#: 40-hex substring, so it can never be mistaken for an address afterward.
_BYTES32_RE = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{64}(?![0-9a-fA-F])")

#: Cells a shortened bytes32 value gets, and the *default* an address gets
#: too before this row's real width narrows it further -- the anti-poisoning
#: window's own 17-cell form (8 head / 6 tail; PRD §3.2's own worked
#: example).
_DEFAULT_ADDRESS_COLS = 17

#: Cells a shortened bytes32 value gets. Not a layout pin: this row is CSS
#: ``nowrap`` + ``text-overflow: ellipsis`` like every other row in this
#: panel (module docstring, "Width behaviour"), so the shortening exists to
#: keep one 66-character token from dominating the row ahead of that
#: ellipsis, not to satisfy a fixed column. An address gets no such free
#: pass -- see :func:`_fmt_drift`: on the real screen, inside the real rail,
#: a row this long is cropped by the CSS ellipsis *before* the icon at the
#: end of it, at 143, 170 and 200 columns, and the icon only survives at
#: 240 (measured, not estimated --
#: ``tests/screens/test_address_icons_everywhere.py``'s FWA sweep is what
#: caught it). So the address itself is windowed to whatever the row can
#: actually afford, never left to the ellipsis to solve.
_BYTES32_COLS = 17

#: Fallback when the app's own theme is unavailable (not yet mounted, or a
#: bare harness with no theme wired) -- Rich's own colour names, matching
#: ``widgets/curator/signals.py``'s identical ``_TOKEN_FALLBACK`` (the same
#: problem, solved the same way: a required ``Theme`` field resolved to a
#: concrete colour before it reaches ``Text.from_markup``, which -- unlike
#: ``Static.update(str)``'s ``Content.from_markup`` -- does not understand a
#: ``$``-prefixed token and raises instead of degrading).
_TOKEN_FALLBACK = {"success": "green", "warning": "yellow", "error": "red"}


def _resolve_color(color: str, colors: dict[str, str] | None) -> str:
    """A signal ``color`` as a concrete Rich colour.

    ``color`` is one of :data:`~maxpane_dashboard.analytics.fwa_signals.
    SIGNAL_COLORS` -- ``"$success"``/``"$warning"``/``"$error"``/``"dim"``.
    ``"dim"`` passes through unchanged: it is already a Rich keyword, not a
    Textual ``$`` token. Only the three ``$``-prefixed ones need resolving.
    """
    if not color.startswith("$"):
        return color
    name = color[1:]
    if colors and name in colors:
        return colors[name]
    return _TOKEN_FALLBACK.get(name, "white")


def _address_window(available: int, non_address_cols: int, count: int) -> int:
    """How many cells each address in this row gets to show.

    ``available`` is the row's real cell budget (0 means "not laid out
    yet"), ``non_address_cols`` is everything in the value that is *not*
    one of the ``count`` addresses being windowed (the indicator, the
    surrounding prose, and every address's own :data:`ICON_COLS`).
    :data:`_DEFAULT_ADDRESS_COLS` (17) is the ceiling and
    :data:`MIN_SHORT_COLS` (11) is the floor -- narrower only when the rail
    genuinely has less room, never below the floor: a row that still does
    not fit at the floor is left to the panel's own CSS
    ``text-overflow: ellipsis`` to crop, exactly like every other row here
    when its own content overruns.
    """
    if available <= 0 or count <= 0:
        return _DEFAULT_ADDRESS_COLS
    per_address = (available - non_address_cols - ICON_COLS * count) // count
    return max(min(per_address, _DEFAULT_ADDRESS_COLS), MIN_SHORT_COLS)


def _fmt_drift(
    sig: dict | None, colors: dict[str, str] | None, available: int = 0
) -> Text | str:
    """The PARAM DRIFT row, built as ``Text``.

    Unlike the other five rows this one can carry a config value that is a
    genuine 0x address or a bytes32 hash -- ``analytics/fwa_signals.py``'s
    ``_fmt_config_value`` publishes both unshortened (PRD §6), and this is
    the widget that composes them:

    * An **address** (a 40-hex run with hex boundaries on both sides) is
      windowed to :func:`_address_window`'s cells and given the copy icon,
      via :func:`~maxpane_dashboard.widgets.address.address_text` called on
      just the matched substring -- never
      :func:`~maxpane_dashboard.widgets.address.address_prose`, which has no
      ``width`` parameter and always shows the whole address: on the real
      screen that address+icon unit is exactly what a narrow row's CSS
      ellipsis crops first (the icon sits at the very end of it), which is
      the defect this function exists to close. ``address_text``'s own
      ``is_address`` check runs on the *unshortened* match, so the icon
      still copies the real, full address regardless of how narrow the
      displayed window is.
    * A **bytes32** value (64 hex) is shortened first with
      :func:`~maxpane_dashboard.widgets.address.short_hex` and gets **no**
      icon -- it is not a wallet or contract address, the same treatment a
      transaction hash gets everywhere else in this app.

    Built as ``Text`` rather than spliced into a markup string, because the
    copy icon needs its own ``Style`` meta -- the same reason every other
    converted FWA site returns ``Text`` instead of a string. The signal's own
    ``$``-token colour is resolved to a concrete one first (see
    :func:`_resolve_color`), since ``Text.from_markup`` cannot parse it.

    Returns ``""`` (not a bare row) when ``sig`` is absent, matching
    :func:`_fmt_signal`'s existing empty-string convention so the caller's
    ``blank`` fallback still applies.
    """
    if not sig or not isinstance(sig, dict):
        return ""
    value = str(sig.get("value_str") or "").strip() or _DASH
    fg = _resolve_color(sig.get("color") or "dim", colors)
    indicator = sig.get("indicator") or "●"

    # Bytes32 first: once shortened it no longer contains an unbroken
    # 40-hex run, so the address pass below can never mistake it for one.
    shortened = _BYTES32_RE.sub(
        lambda m: short_hex(m.group(0), _BYTES32_COLS), value
    )

    # Same spacing and colour split as `_fmt_signal`'s
    # ``"  [{color}]{indicator}[/] [{color}]{value}[/]"``: the two leading
    # spaces are uncoloured, the indicator and the value each carry `fg`.
    prefix = Text("  ")
    prefix.append(indicator, style=fg)
    prefix.append(" ")

    matches = list(PROSE_ADDRESS_RE.finditer(shortened))
    if not matches:
        line = prefix
        line.append(shortened, style=fg)
        return line

    row_overhead = cell_len(prefix.plain)
    non_address_cols = cell_len(shortened) - sum(
        cell_len(m.group(0)) for m in matches
    )
    address_budget = max(available - row_overhead, 0) if available else 0
    width = _address_window(address_budget, non_address_cols, len(matches))

    line = prefix
    pos = 0
    for match in matches:
        if match.start() > pos:
            line.append(shortened[pos:match.start()], style=fg)
        cell = address_text(match.group(0), width=width, style=fg)
        line.append_text(cell)
        pos = match.end()
    if pos < len(shortened):
        line.append(shortened[pos:], style=fg)
    return line



def _fmt_signal(sig: dict | None) -> str:
    """Render one signal row using Textual markup.

    Returns an empty string when ``sig`` is ``None`` / not a dict; callers pass
    ``{"value_str": "--"}`` instead so all five rows always render.

    The label prefix is dropped, as in ``tal_signals.py``: the value string
    already restates the concept and the row is narrow.
    """
    if not sig or not isinstance(sig, dict):
        return ""
    value = sig.get("value_str") or _DASH
    color = sig.get("color") or "dim"
    indicator = sig.get("indicator") or "●"
    return f"  [{color}]{indicator}[/] [{color}]{value}[/]"


def _with_words(sig: dict | None, words: tuple[str, ...], note: str) -> dict | None:
    """Guarantee the row says something in text, not only in colour.

    When ``value_str`` contains none of ``words``, ``note`` is appended so the
    row still reads correctly in greyscale. Returns a *new* dict; the caller's
    payload is never mutated.
    """
    if not sig or not isinstance(sig, dict):
        return sig
    value = str(sig.get("value_str") or "").strip()
    if not value or value == _DASH:
        return sig
    if any(word in value.lower() for word in words):
        return sig
    out = dict(sig)
    out["value_str"] = f"{value} · {note}"
    return out


def _fmt_pool_temp(sig: dict | None) -> str:
    """Pool temperature: colour gradient *plus* a direction in words."""
    return _fmt_signal(_with_words(sig, _DIRECTION_WORDS, "direction unknown"))


def _fmt_buy_gate(sig: dict | None) -> str:
    """Buy gate: red/green *plus* the state spelled out."""
    return _fmt_signal(_with_words(sig, _GATE_WORDS, "state unknown"))


def _fmt_emissions(sig: dict | None) -> str:
    """Emissions status, never as a negative countdown.

    The 2026-08-04T19:01:23Z hard stop is the primary case: once it passes the
    row must read ``emissions ended``. If an upstream signal still hands us a
    countdown that has gone negative, it is rewritten here rather than shown.
    """
    if not sig or not isinstance(sig, dict):
        return _fmt_signal(sig)
    value = str(sig.get("value_str") or "").strip()
    if value and _NEGATIVE_COUNTDOWN.search(value):
        out = dict(sig)
        out["value_str"] = EMISSIONS_ENDED
        return _fmt_signal(out)
    return _fmt_signal(sig)


class FWASignals(Vertical):
    """Analytical signals panel with five rows."""

    DEFAULT_CSS = """
    FWASignals > .fwa-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWASignals > .fwa-signals-body {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="fwa-signals-title", id="fwa-sig-title")
        # Blank line below the title (doubles as the title spacer).
        yield Static("", classes="fwa-signals-body", id="fwa-sig-spacer")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-pool-temp")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-sellback")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-buy-gate")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-emissions")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-vrf")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-drift")

    def update_data(
        self,
        pool_temp_signal=None,
        sellback_signal=None,
        buy_gate_signal=None,
        emissions_signal=None,
        vrf_queue_signal=None,
        param_drift_signal=None,
        **_kwargs,
    ) -> None:
        """Refresh the five signal rows.

        Every kwarg matches ``FWA_WIDGET_SIGNATURES["FWASignals"]``. No args,
        all-``None`` and a full payload all render without raising.
        """
        self._payload = {
            "pool_temp_signal": pool_temp_signal,
            "sellback_signal": sellback_signal,
            "buy_gate_signal": buy_gate_signal,
            "emissions_signal": emissions_signal,
            "vrf_queue_signal": vrf_queue_signal,
            "param_drift_signal": param_drift_signal,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render on resize so the clipped-row marker tracks the width."""
        self._render_view()

    # -- rendering -----------------------------------------------------

    def _theme_colors(self) -> dict[str, str]:
        """The app's current concrete colours for :data:`_TOKEN_FALLBACK`'s
        three tokens, or ``{}`` when unavailable (not yet mounted, or a bare
        harness with no theme) -- :func:`_resolve_color` falls back to the
        plain colour names in that case. Same pattern as
        ``widgets/curator/signals.py``'s identical method.
        """
        try:
            return self.app.get_css_variables()
        except Exception:
            return {}

    def _render_view(self) -> None:
        payload = self._payload
        blank = _fmt_signal({"value_str": _DASH})
        # Resolved once per refresh, only for the one row that builds a real
        # ``Text`` (PARAM DRIFT, see ``_fmt_drift``): the other five keep
        # handing ``Static`` the plain markup string they always have,
        # parsed by Textual's own ``$``-aware ``Content.from_markup``.
        colors = self._theme_colors()

        # ``padding: 0 1`` on the body rows costs two columns. Computed
        # *before* the rows tuple: PARAM DRIFT windows its own address(es)
        # against this budget rather than relying on the panel's CSS
        # ellipsis to crop the row afterward -- an ellipsis crop lands at
        # the *end* of the row, which is exactly where the copy icon sits,
        # so a row left unwindowed loses its icon on the real screen well
        # before this panel's own "does it fit" marker would ever say so.
        available = max(self.content_size.width - 2, 0)
        clipped = False

        rows = (
            ("#fwa-sig-pool-temp", _fmt_pool_temp(payload.get("pool_temp_signal"))),
            ("#fwa-sig-sellback", _fmt_signal(payload.get("sellback_signal"))),
            ("#fwa-sig-buy-gate", _fmt_buy_gate(payload.get("buy_gate_signal"))),
            ("#fwa-sig-emissions", _fmt_emissions(payload.get("emissions_signal"))),
            ("#fwa-sig-vrf", _fmt_signal(payload.get("vrf_queue_signal"))),
            (
                "#fwa-sig-drift",
                _fmt_drift(payload.get("param_drift_signal"), colors, available),
            ),
        )

        for selector, content in rows:
            text = content if content else blank
            length = (
                cell_len(text.plain) if isinstance(text, Text) else _visible_len(text)
            )
            if available and length > available:
                clipped = True
            try:
                self.query_one(selector, Static).update(text)
            except Exception:  # not composed yet
                return

        try:
            title = self.query_one("#fwa-sig-title", Static)
        except Exception:
            return
        title.update(f"SIGNALS  [yellow]{WIDEN_HINT}[/]" if clipped else "SIGNALS")
