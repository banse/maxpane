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
3. No-args and all-``None`` ``update_data`` calls never raise, for every
   exported widget in one sweep, asserted against composited output.
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
from pathlib import Path

import pytest
from rich.errors import MarkupError
from rich.text import Text
from textual.app import App, ComposeResult

from maxpane_dashboard.data.surf_models import SURF_KEYS

# Package root, not submodule paths: this is the surface ``screens/surf.py``
# and its screen test import from (WP5), so the contract sweep exercises it.
import maxpane_dashboard.widgets.surf as surf_widgets
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
    SurfSignals,
)


def _exported_widget_classes() -> tuple[type, ...]:
    """Every widget class the package exports, in ``__all__`` order.

    Derived rather than hand-typed, and that is the fix for a real hole: the
    three launchpad widgets (2026-08-23) were added to the package and to no
    list in this file, so ``widgets/surf/launchpad.py`` was covered by none of
    the four guarantees this module exists to give. Adding
    ``from maxpane_dashboard.data import surf_client`` to it left the whole
    file 22/22 green, and restoring ``[$success]`` into ``_pct_cell`` -- the
    exact crash the theme-token guard was written for -- left it green while
    seven tests in other modules raised ``MarkupError``.

    A derived list covers the next widget the day it is written; a typed one
    covers it the day somebody remembers.
    """
    return tuple(
        obj
        for obj in (getattr(surf_widgets, name) for name in surf_widgets.__all__)
        if isinstance(obj, type)
    )


_ALL_WIDGETS = _exported_widget_classes()

#: The widgets that deliberately do **not** name their ``update_data`` kwargs
#: after ``SURF_KEYS``. The ``l`` view's three panels are primitives-only and
#: reusable, so they take short names (``coins``, ``as_of_hhmm``,
#: ``burned_total``) and the screen maps the ``launchpad_``-prefixed contract
#: keys onto them (``tests/screens/test_surf_screen.py``'s
#: ``SURF_WIDGET_SIGNATURES`` is where that mapping is pinned).
#:
#: An *exception* list rather than an inclusion list, on purpose: a widget
#: added tomorrow lands in the strict kwarg check by default and has to be
#: named here to escape it, which is the opposite of how the launchpad trio
#: escaped every check in this file by simply not being mentioned.
_SHORT_KWARG_WIDGETS = frozenset(
    {SurfLaunchpadCoins, SurfCurveFlow, SurfBurnPipeline}
)

_WIDGETS = tuple(w for w in _ALL_WIDGETS if w not in _SHORT_KWARG_WIDGETS)

#: The one kwarg name that is a contract key with its ``launchpad_`` prefix
#: elided, and the key it stands for.
#:
#: A **kwarg**-level carve-out, deliberately not a widget-level one. The
#: launchpad tier's own slower clock is dispatched to every panel in the
#: ``l`` body, and all five spell it ``as_of_hhmm``; the two panels wired on
#: 2026-08-25 (``SurfLaunchpadActivity``, ``SurfBurnkeepers``) name every
#: *other* kwarg after its ``SURF_KEYS`` key exactly, so putting them in
#: :data:`_SHORT_KWARG_WIDGETS` to excuse this one name would have exempted
#: their whole signature -- the broad waiver that let the first three
#: launchpad panels escape every check in this file. One name is the narrow
#: one.
#:
#: It is not a hole either, because the *mapping* is pinned elsewhere and
#: against the real signature: ``tests/screens/test_surf_screen.py``'s
#: ``SURF_WIDGET_SIGNATURES`` records ``launchpad_as_of_hhmm -> as_of_hhmm``
#: per widget and ``test_screen_dispatches_every_data_key`` compares the
#: recorded dispatch call's kwargs against it, so a panel that takes
#: ``as_of_hhmm`` and is never handed ``launchpad_as_of_hhmm`` still fails
#: there.
_PREFIXED_KWARG_ALIASES = {"as_of_hhmm": "launchpad_as_of_hhmm"}


def test_the_kwarg_alias_stands_for_a_real_contract_key():
    """The carve-out has to keep being a carve-out *from* something.

    An alias whose target left ``SURF_KEYS`` would go on excusing a kwarg
    that answers for nothing, and an alias that was *itself* a contract key
    would be dead weight hiding the next real one. Both are checked here so
    the strict sweep below cannot be widened by accident.
    """
    for alias, key in _PREFIXED_KWARG_ALIASES.items():
        assert key in SURF_KEYS, (
            f"{alias!r} is excused as an elision of {key!r}, which SURF_KEYS "
            "no longer carries"
        )
        assert alias not in SURF_KEYS, (
            f"{alias!r} is a contract key in its own right -- it needs no "
            "alias, and listing it here would absorb the next real offender"
        )


def test_the_derived_widget_lists_are_not_empty_and_agree():
    """The derivation has to be able to fail.

    A ``__all__`` that stopped exporting classes, or an exception list that
    grew to swallow everything, would make every parametrised sweep below
    run over nothing and pass. Both ends are pinned, and the
    contract-keyed widgets are named once here -- the only hand-typed list
    left in this file -- so that a widget quietly moving into the short-kwarg
    exception is visible rather than silent.
    """
    assert set(_ALL_WIDGETS) == set(_WIDGETS) | _SHORT_KWARG_WIDGETS
    assert set(_WIDGETS) == {
        SurfHero, SurfSignals, SurfFeed, SurfDevActivity, SurfMarket, SurfNft,
        # Wired into the `l` body 2026-08-25. They land here, in the strict
        # check, rather than in `_SHORT_KWARG_WIDGETS` -- which is what that
        # list's own docstring asks of a new widget. `SurfBurnkeepers` was
        # renamed `burnkeepers=` -> `launchpad_burnkeepers=` to earn it.
        SurfLaunchpadActivity, SurfBurnkeepers,
    }
    assert _SHORT_KWARG_WIDGETS < set(_ALL_WIDGETS)


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
    """Every kwarg is a PRD §5 key -- the screen can splat the flat dict.

    ...or the single documented prefix elision in
    :data:`_PREFIXED_KWARG_ALIASES`, whose target key is re-checked by
    ``test_the_kwarg_alias_stands_for_a_real_contract_key`` above.
    """
    unknown = [
        k
        for k in _kwargs_of(cls)
        if k not in SURF_KEYS
        and _PREFIXED_KWARG_ALIASES.get(k) not in SURF_KEYS
    ]
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
#: re-proves the property the ban was really about, transitively: it follows
#: every ``maxpane_dashboard.analytics.*`` import out of an allowed module and
#: scans that one too, to a fixed point. A depth-1 version of this test was
#: green while ``analytics/surf_feed`` imported ``analytics/surf_signals``,
#: which reaches ``data`` in one further hop -- so the allowance really did
#: open a path to the data layer, and the recursion is what closes it.
_PURE_ANALYTICS_ALLOWED = frozenset({"maxpane_dashboard.analytics.surf_feed"})


def _imported_names(module) -> list[str]:
    """Every dotted name a module's own source imports.

    ``from X import Y`` yields **both** ``X`` and ``X.Y``. Yielding only ``X``
    is what made the recursion below blind: ``from maxpane_dashboard.analytics
    import surf_signals`` reads as an import of the *package*, and walking the
    package's ``__init__`` finds nothing, so a widget could reach
    ``analytics.surf_signals`` -- which imports ``data.surf_addresses`` and
    ``data.surf_models`` -- through an allowed module with the suite green.
    ``X.Y`` is not always a module (it is often a function); the caller tries
    to import it and ignores the ones that are not.
    """
    tree = ast.parse(inspect.getsource(module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported += [f"{base}.{a.name}" if base else a.name for a in node.names]
    return imported


def test_the_allowed_analytics_modules_are_themselves_pure():
    """The allowance carries its own proof, rather than trusting a name.

    A widget importing ``analytics.surf_feed`` is only harmless for as long
    as ``analytics.surf_feed`` is: the moment it grows an ``httpx`` import or
    reaches into ``data``, the surf widgets have a transitive path to the
    network and the guard above would still be green.

    **Transitively**, and that word is load-bearing. Scanning only the named
    modules leaves the path open one hop further out: adding ``from
    maxpane_dashboard.analytics import surf_signals`` to
    ``analytics/surf_feed`` -- a module that itself imports
    ``data.surf_addresses`` and ``data.surf_models`` -- left a depth-1
    version of this test green. The walk below follows every
    ``maxpane_dashboard.analytics.*`` name it finds, to a fixed point.
    """
    import importlib

    assert _PURE_ANALYTICS_ALLOWED, "an empty allowance would make this vacuous"
    seen: set[str] = set()
    queue = sorted(_PURE_ANALYTICS_ALLOWED)
    scanned = 0
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            module = importlib.import_module(name)
        except ImportError:
            # ``X.Y`` where Y is a function, not a module. Its module ``X``
            # was queued alongside it, so nothing goes unscanned.
            continue
        scanned += 1
        for imported in _imported_names(module):
            assert "maxpane_dashboard.data" not in imported, (name, imported)
            assert "textual" not in imported, (name, imported)
            assert "httpx" not in imported and "aiohttp" not in imported, (
                name,
                imported,
            )
            if imported.startswith("maxpane_dashboard.analytics"):
                queue.append(imported)
    assert scanned >= len(_PURE_ANALYTICS_ALLOWED), (
        "fewer modules were actually scanned than are allowed -- the walk "
        "imported nothing and proved nothing"
    )


def _surf_widget_modules() -> tuple:
    """Every module under ``maxpane_dashboard/widgets/surf/``, imported.

    Walked off disk rather than hand-typed. The typed version of this list
    named seven modules and ``widgets/surf/launchpad.py`` was not one of
    them, so the three ``l``-view widgets were exempt from the purity proof
    for the whole of their existence: adding ``from maxpane_dashboard.data
    import surf_client`` to that module left this file green, while the same
    mutation in an already-listed module correctly reddened -- which is how
    the transitive half of the guard was shown to work and the coverage half
    shown not to.

    ``__init__`` is included deliberately: it is the import surface the
    screen uses, so a data-layer import placed there would reach every
    consumer of the package.
    """
    import importlib

    package = Path(surf_widgets.__file__).parent
    names = sorted(
        path.stem if path.stem != "__init__" else ""
        for path in package.glob("*.py")
    )
    modules = tuple(
        importlib.import_module(
            f"{surf_widgets.__name__}.{stem}" if stem else surf_widgets.__name__
        )
        for stem in names
    )
    assert len(modules) >= 8, (
        f"only {len(modules)} surf widget modules found -- the walk is not "
        "seeing the package and would prove nothing"
    )
    return modules


def test_the_module_walk_sees_every_file_in_the_package():
    """The walk has to be able to fail.

    A glob that matched nothing, or an import that silently dropped a
    module, would leave every assertion in the purity scan running over an
    empty (or partial) list. Compared against the directory listing rather
    than against a count, so a module added tomorrow is covered without this
    test being edited -- and against the *file names*, which is the thing the
    old hand-typed import block got wrong.
    """
    package = Path(surf_widgets.__file__).parent
    on_disk = {path.stem for path in package.glob("*.py")}
    walked = {
        module.__name__.rsplit(".", 1)[-1] if module is not surf_widgets
        else "__init__"
        for module in _surf_widget_modules()
    }
    assert walked == on_disk
    assert "launchpad" in walked, (
        "the l-view widgets are back outside the purity proof"
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
    for module in _surf_widget_modules():
        for name in _imported_names(module):
            assert "maxpane_dashboard.data" not in name, (module.__name__, name)
            if "analytics" in name:
                # Prefix match: ``_imported_names`` yields ``X`` and ``X.Y``
                # for a ``from X import Y``, and the allowlist names modules.
                assert any(
                    name == allowed or name.startswith(f"{allowed}.")
                    for allowed in _PURE_ANALYTICS_ALLOWED
                ), (module.__name__, name)
            assert "surf_addresses" not in name, (module.__name__, name)
            assert "surf_client" not in name, (module.__name__, name)
            assert "httpx" not in name and "aiohttp" not in name, (module.__name__, name)


# ``_ALL_WIDGETS``, not ``_WIDGETS``: this sweep asks whether a widget
# survives an empty payload, which has nothing to do with what its kwargs are
# named, so the short-kwarg exception that keeps the launchpad trio out of the
# two contract-key checks above has no bearing here. Those three rendered a
# full outage untested until 2026-08-24.
@pytest.mark.parametrize("cls", _ALL_WIDGETS, ids=lambda c: c.__name__)
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

#: ``launchpad.py`` is Rich-parsed too, but only in part -- so it gets a
#: *scope* rather than a whole-module scan.
#:
#: Its coin table is a ``DataTable``, and a ``str`` cell is parsed by Rich:
#: ``[$success]`` in a cell raises ``MarkupError`` out of the message pump
#: exactly as it does in the feed (demonstrated in
#: ``test_rich_rejects_a_theme_token_in_a_data_table_cell`` below, not
#: asserted from memory). ``_pct_cell`` originally read ``[$success]``/
#: ``[$error]`` and crashed the very first render -- and restoring that after
#: the fact left this whole file green, because the module was in no list here
#: at all.
#:
#: The rest of the module is *not* Rich-parsed and legitimately uses tokens:
#: the panel's own note goes to ``Static.update()`` as a string, which is
#: Textual Content markup, where ``[$warning]`` is correct and shipping. A
#: whole-module scan would forbid that, and would also trip over the
#: docstrings that explain this very rule.
#:
#: So the scope is derived from the code rather than typed: start at
#: ``_coin_row`` -- the one function whose return value becomes table cells --
#: and follow its calls to a fixed point within the module. A cell helper
#: renamed or a new one added is covered without editing this file.
_RICH_PARSED_ROOTS = {"maxpane_dashboard.widgets.surf.launchpad": "_coin_row"}


def _rich_parsed_modules():
    import maxpane_dashboard.widgets.surf.activity as act_mod
    import maxpane_dashboard.widgets.surf.feed as feed_mod

    modules = (feed_mod, act_mod)
    assert tuple(m.__name__ for m in modules) == _RICH_PARSED_MODULE_NAMES
    return modules


def _call_closure(module, root: str) -> list[ast.FunctionDef]:
    """*root* and every function in *module* it reaches, transitively.

    Purely syntactic: it matches call targets by bare name against the
    module's own top-level ``def``s, which is all the cell helpers are. A
    call it cannot resolve (a method, an import) is simply not a function of
    this module and is out of scope by definition.
    """
    tree = ast.parse(inspect.getsource(module))
    defs = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert root in defs, f"{module.__name__} has no {root}() any more"

    reached: dict[str, ast.FunctionDef] = {}
    queue = [root]
    while queue:
        name = queue.pop()
        if name in reached:
            continue
        reached[name] = defs[name]
        for node in ast.walk(defs[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in defs:
                    queue.append(node.func.id)
    return list(reached.values())


def _string_literals(nodes) -> list[str]:
    """Every string literal under *nodes*, **docstrings excluded**.

    The prose explaining this rule has to quote the tokens it forbids -- and
    ``launchpad._pct_cell``'s docstring does exactly that, recording the
    ``[$success]`` crash it was written to prevent. A docstring never reaches
    a renderer, so excluding it removes a false positive without weakening
    anything: the guard is about what is *handed to a parser*.

    Structural, not a heuristic on content: a docstring is the first
    statement of a module, class or function body when that statement is a
    bare string, and only those are dropped.
    """
    docstrings: set[int] = set()
    literals: list[str] = []
    for parent in nodes:
        for node in ast.walk(parent):
            body = getattr(node, "body", None)
            if (
                isinstance(node, (ast.Module, ast.ClassDef,
                                  ast.FunctionDef, ast.AsyncFunctionDef))
                and isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    for parent in nodes:
        for node in ast.walk(parent):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                literals.append(node.value)
    return literals


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

    Only string literals are inspected, docstrings excluded: the prose
    explaining this rule necessarily quotes the tokens it forbids, so
    scanning raw source text would self-trip on this docstring and comments,
    and scanning docstrings would trip on ``launchpad._pct_cell``'s own
    record of the crash it was written to prevent.

    Two scopes, for two reasons (see :data:`_RICH_PARSED_ROOTS`): the feed
    and activity modules are Rich-parsed end to end, while the launchpad
    module is Rich-parsed only along the path that builds ``DataTable``
    cells -- everything else in it renders through ``Static.update()``,
    where a ``$``-token is correct and currently shipping.
    """
    import importlib

    scopes = [(module, [ast.parse(inspect.getsource(module))])
              for module in _rich_parsed_modules()]
    for name, root in _RICH_PARSED_ROOTS.items():
        module = importlib.import_module(name)
        nodes = _call_closure(module, root)
        assert len(nodes) >= 2, (
            f"{name}: the call closure from {root}() collapsed to "
            f"{len(nodes)} function(s) -- it would prove nothing"
        )
        scopes.append((module, nodes))

    for module, nodes in scopes:
        literals = _string_literals(nodes)
        assert literals, f"{module.__name__}: nothing was scanned"
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


@pytest.mark.asyncio
async def test_rich_rejects_a_theme_token_in_a_data_table_cell():
    """The launchpad half of the rule, demonstrated rather than assumed.

    ``SurfLaunchpadCoins`` is the first surf widget whose text reaches a
    ``DataTable`` rather than a ``Static`` or a ``RichLog``, and it is not
    obvious from the call site which markup dialect that is. It is Rich's:
    a ``[$name]`` token in a cell raises ``MarkupError`` out of the message
    pump, which is why ``_coin_row``'s call closure is scanned above.
    """
    from maxpane_dashboard.widgets.surf import launchpad as lp

    original = lp._pct_cell
    lp._pct_cell = lambda value: "[$success]+34.0%[/]"
    try:
        widget = lp.SurfLaunchpadCoins()
        app = _Harness(widget)
        with pytest.raises(MarkupError):
            async with app.run_test(size=(100, 24)) as pilot:
                widget.update_data(coins=[{
                    "ticker": "ICE", "name": "Ice", "creator": "0x8ca0",
                    "creator_known": False, "age_s": 7_200.0,
                    "price_eth": 0.0071, "change_24h_pct": 34.0,
                    "swaps_24h": 41, "swaps_all": 97, "imd_burned": 250.0,
                }], coin_count=1, as_of_hhmm="01:14")
                await pilot.pause()
    finally:
        lp._pct_cell = original
