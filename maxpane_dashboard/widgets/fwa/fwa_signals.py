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

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_DASH = "--"

#: Rewritten value for an elapsed emissions window (PRD §8, the primary case).
EMISSIONS_ENDED = "emissions ended"

#: Words that prove the pool-temperature row states its direction in text.
_DIRECTION_WORDS = ("you", "depositor", "purchaser")

#: Words that prove the buy-gate row states its state in text.
_GATE_WORDS = ("open", "closed", "enabled", "disabled", "blocked", "live")

#: A signed countdown component, e.g. ``-2d`` / ``−13h`` / ``-41s``.
_NEGATIVE_COUNTDOWN = re.compile(r"[-−]\s*\d")


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
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="fwa-signals-title")
        # Blank line below the title (doubles as the title spacer).
        yield Static("", classes="fwa-signals-body", id="fwa-sig-spacer")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-pool-temp")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-buy-gate")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-emissions")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-vrf")
        yield Static("", classes="fwa-signals-body", id="fwa-sig-drift")

    def update_data(
        self,
        pool_temp_signal=None,
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
        blank = _fmt_signal({"value_str": _DASH})

        rows = (
            ("#fwa-sig-pool-temp", _fmt_pool_temp(pool_temp_signal)),
            ("#fwa-sig-buy-gate", _fmt_buy_gate(buy_gate_signal)),
            ("#fwa-sig-emissions", _fmt_emissions(emissions_signal)),
            ("#fwa-sig-vrf", _fmt_signal(vrf_queue_signal)),
            ("#fwa-sig-drift", _fmt_signal(param_drift_signal)),
        )
        for selector, markup in rows:
            self.query_one(selector, Static).update(markup or blank)
