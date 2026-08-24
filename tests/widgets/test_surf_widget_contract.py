"""Cross-widget contract tests for the surf dashboard (WP3).

Four structural guarantees, one place:

1. Every ``update_data`` kwarg of every surf widget is a key of the frozen
   PRD §5 contract (``data/surf_models.SURF_KEYS``) -- the screen splats
   the manager dict at each widget, so a stray kwarg is a silent no-op and
   a typo'd one never receives data.
2. Widget modules import nothing from ``maxpane_dashboard.data``, and from
   ``maxpane_dashboard.analytics`` only the pure modules named in
   ``_PURE_ANALYTICS_ALLOWED`` -- primitives only, and the structural proof
   that widgets cannot touch the network. The allowance is not a hole in
   that proof: every allowed module is itself scanned, so a widget can only
   reach analytics code that reaches nothing.
3. No-args and all-``None`` ``update_data`` calls never raise, for all six
   widgets in one sweep, asserted against composited output.
4. No Textual theme token (``[$name]``, e.g. ``[$warning]``) reaches a
   Rich-parsed surface (``RichLog.write`` in the activity panel,
   ``Text.from_markup`` in the feed) -- Rich's own markup parser does not
   know Textual's ``$name`` design-token extension and raises
   ``MarkupError`` instead of degrading. This is not hypothetical: the
   identical token crashed every ACTION row of the FWA activity feed until
   a human caught it by eye (``widgets/fwa/fwa_activity_feed.py``,
   ``tests/widgets/test_fwa_accessibility.py``); this guard is the surf
   dashboard's copy of that same regression lock, added proactively rather
   than after a crash.
"""

from __future__ import annotations

import ast
import inspect

import pytest
from rich.errors import MarkupError
from rich.text import Text
from textual.app import App, ComposeResult

from maxpane_dashboard.data.surf_models import SURF_KEYS

# Package root, not submodule paths: this is the surface ``screens/surf.py``
# and its screen test import from (WP5), so the contract sweep exercises it.
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

_WIDGETS = (SurfHero, SurfSignals, SurfFeed, SurfDevActivity, SurfMarket, SurfNft)


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _kwargs_of(cls) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(cls.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    )


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
def test_update_data_kwargs_are_frozen_contract_keys(cls):
    """Every kwarg is a PRD §5 key -- the screen can splat the flat dict."""
    unknown = [k for k in _kwargs_of(cls) if k not in SURF_KEYS]
    assert not unknown, f"{cls.__name__} takes non-contract kwargs: {unknown}"


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
def test_every_widget_accepts_the_whole_flat_dict(cls):
    """``**_kwargs`` is present, so foreign contract keys are ignored."""
    has_var_kw = any(
        p.kind is p.VAR_KEYWORD
        for p in inspect.signature(cls.update_data).parameters.values()
    )
    assert has_var_kw, f"{cls.__name__}.update_data lacks **_kwargs"


#: Analytics modules a surf widget may import, and the reason the list is a
#: list rather than a blanket ban.
#:
#: ``analytics/surf_feed`` is the announce channel's threading rule
#: (``build_threads``): stdlib-only, no I/O, no clock, no Textual. The feed
#: widget renders what it returns, and the alternative -- routing the threads
#: through the manager -- would put a *derived view shape* into the frozen
#: PRD §5 payload, where the widget's own collapse state would have to travel
#: with it. Widgets elsewhere in this repo already import pure analytics
#: helpers (``widgets/base/*`` take their formatters from
#: ``analytics/base_tokens``, ``widgets/frenpet/*`` from
#: ``analytics/frenpet_battle``); this is the surf dashboard's first.
#:
#: The name check alone would be a weaker guard than the blanket ban it
#: replaces, so ``test_the_allowed_analytics_modules_are_themselves_pure``
#: re-proves the property the ban was really about -- transitively, on the
#: allowed module's own source.
_PURE_ANALYTICS_ALLOWED = frozenset({"maxpane_dashboard.analytics.surf_feed"})


def _imported_names(module) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    return imported


def test_the_allowed_analytics_modules_are_themselves_pure():
    """The allowance carries its own proof, rather than trusting a name.

    A widget importing ``analytics.surf_feed`` is only harmless for as long
    as ``analytics.surf_feed`` is: the moment it grows an ``httpx`` import or
    reaches into ``data``, the surf widgets have a transitive path to the
    network and the guard above would still be green. This closes that by
    scanning the allowed module's own source for the same forbidden names.
    """
    import importlib

    assert _PURE_ANALYTICS_ALLOWED, "an empty allowance would make this vacuous"
    for name in sorted(_PURE_ANALYTICS_ALLOWED):
        module = importlib.import_module(name)
        for imported in _imported_names(module):
            assert "maxpane_dashboard.data" not in imported, (name, imported)
            assert "textual" not in imported, (name, imported)
            assert "httpx" not in imported and "aiohttp" not in imported, (
                name,
                imported,
            )


def test_widget_modules_import_no_data_layer_and_no_analytics():
    """Primitives only -- also the structural no-network proof.

    Note: this scans the AST of each surf module's own source for import
    statements. It deliberately does NOT inspect ``sys.modules`` after
    import -- merely importing ``maxpane_dashboard.widgets`` (the package,
    to reach any dashboard) eagerly loads legacy widgets that pull
    ``data.*``/``analytics.*`` into ``sys.modules`` as a side effect, which
    is reproducible from a bare ``import maxpane_dashboard.widgets`` with no
    surf involvement whatsoever. That is a pre-existing quirk of the shared
    package, not a surf defect, and a ``sys.modules``-based check would
    misattribute it to these modules.
    """
    import maxpane_dashboard.widgets.surf._fmt as fmt_mod
    import maxpane_dashboard.widgets.surf.activity as act_mod
    import maxpane_dashboard.widgets.surf.feed as feed_mod
    import maxpane_dashboard.widgets.surf.hero as hero_mod
    import maxpane_dashboard.widgets.surf.market as mkt_mod
    import maxpane_dashboard.widgets.surf.nft as nft_mod
    import maxpane_dashboard.widgets.surf.signals as sig_mod

    for module in (fmt_mod, hero_mod, sig_mod, feed_mod, act_mod, mkt_mod, nft_mod):
        for name in _imported_names(module):
            assert "maxpane_dashboard.data" not in name, (module.__name__, name)
            if "analytics" in name:
                assert name in _PURE_ANALYTICS_ALLOWED, (module.__name__, name)
            assert "surf_addresses" not in name, (module.__name__, name)
            assert "surf_client" not in name, (module.__name__, name)
            assert "httpx" not in name and "aiohttp" not in name, (module.__name__, name)


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
async def test_no_args_and_all_none_render_without_raising(cls):
    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=(120, 20)) as pilot:
        widget.update_data()
        widget.update_data(
            **{
                name: None
                for name, param in inspect.signature(widget.update_data).parameters.items()
                if param.kind is not param.VAR_KEYWORD and name != "self"
            }
        )
        # Pump the message loop: deferred MarkupErrors surface here or never.
        await pilot.pause()
        screen = _screen_text(app)
        assert screen.strip(), f"{cls.__name__} rendered an empty screen"
        assert "Loading" not in screen


# ---------------------------------------------------------------------------
# Theme-token guard: no ``[$name]`` Textual design token may reach a
# Rich-parsed surface. Added beyond the brief (WP3.8 addendum) -- the FWA
# widgets already carry this guard (test_fwa_accessibility.py) and its
# absence in surf is exactly the gap that let ``[$warning]`` ship into a
# brief's own reference feed code and crash every ACTION row.
# ---------------------------------------------------------------------------

#: The two surf modules whose lines are parsed by *Rich*'s own
#: ``Text.from_markup``: the activity panel writes them into a ``RichLog``
#: (``markup=True``), and the feed calls ``Text.from_markup`` itself and hands
#: the resulting ``Text`` to a ``Static`` -- the same parser either way, and
#: the same reason ``$``-tokens are illegal in both. ``SurfHero``,
#: ``SurfSignals``, ``SurfMarket`` and ``SurfNft`` pass *strings* to
#: ``Static.update`` -- Textual Content markup -- and legitimately use
#: ``$success``/``$warning``/``$error`` design tokens there, so they are
#: correctly excluded from this scan.
_RICH_PARSED_MODULE_NAMES = (
    "maxpane_dashboard.widgets.surf.feed",
    "maxpane_dashboard.widgets.surf.activity",
)


def _rich_parsed_modules():
    import maxpane_dashboard.widgets.surf.activity as act_mod
    import maxpane_dashboard.widgets.surf.feed as feed_mod

    modules = (feed_mod, act_mod)
    assert tuple(m.__name__ for m in modules) == _RICH_PARSED_MODULE_NAMES
    return modules


def test_no_theme_token_reaches_a_rich_parsing_surface():
    """``$``-tokens are Textual *Content* markup only.

    ``SurfDevActivity`` writes every line through ``RichLog.write``
    (``markup=True``) and ``SurfFeed`` calls ``Text.from_markup`` directly;
    both are Rich's own parser -- the one ``rich.markup.escape``/
    ``safe_markup`` is built against, not Textual's
    ``Content.from_markup``/``$token`` extension that ``Static.update()``
    understands when it is handed a *string*. ``[$warning]`` is not valid
    Rich markup and raises ``MarkupError`` at parse time instead of
    degrading.

    Only string literals are inspected: the prose explaining this rule
    necessarily quotes the tokens it forbids, so scanning raw source text
    would self-trip on this docstring and comments.
    """
    for module in _rich_parsed_modules():
        tree = ast.parse(inspect.getsource(module))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        # f-strings decompose into Constant parts, so `[$warning]` survives
        # as its own literal segment and is still caught.
        for text in literals:
            for token in ("[$success]", "[$error]", "[$warning]", "[$"):
                assert token not in text, (
                    f"{module.__name__} hands {token!r} to a Rich-parsed surface"
                )


def test_rich_rejects_theme_tokens_but_accepts_what_surf_feed_sends():
    """The rule above, demonstrated rather than asserted from memory."""
    from maxpane_dashboard.widgets.surf.activity import (
        UNAVAILABLE_LINE as ACTIVITY_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.feed import (
        UNAVAILABLE_LINE as FEED_UNAVAILABLE,
    )

    with pytest.raises(MarkupError):
        Text.from_markup("[$warning]x[/]")

    for unavailable in (FEED_UNAVAILABLE, ACTIVITY_UNAVAILABLE):
        rendered = Text.from_markup(f"[yellow]⚠ {unavailable}[/]")
        assert unavailable in rendered.plain
        assert "⚠" in rendered.plain
