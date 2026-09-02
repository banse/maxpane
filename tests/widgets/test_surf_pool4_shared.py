"""``widgets/surf/_pool4.py`` -- the primitives all five POOL4 panels share,
and the guards that discover **every** pool4 widget module rather than naming
the three this package happens to own.

Three things are pinned here:

1. **The network-word allowlist and its tripwire** (amendment A13). The word
   is each panel's claim about the provenance of its own numbers, so an
   unrecognised string renders the dash rather than being laundered into a
   title. The objection to an allowlist -- that a third network blanks every
   title the day it is added -- is answered by
   :func:`test_the_network_allowlist_agrees_with_the_frozen_vocabulary`, which
   imports ``surf_models.POOL4_NETWORKS`` and compares **in both directions**.
2. **One implementation.** No pool4 widget module may define a local
   ``network_word`` / ``panel_title``.
3. **The ``$``-token guard**, by discovery. A ``$``-prefixed theme token inside
   markup a widget parses itself with ``rich.text.Text.from_markup`` parses
   cleanly and then raises ``MissingStyle`` at *render* time inside
   ``Static.update`` -- outside the widget's own ``try``, in the message pump,
   which takes the app down. It did exactly that during WP4's build. The check
   globs the pool4 widget modules so a module written later is covered the day
   it lands, rather than the day someone remembers to add it here.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from maxpane_dashboard.data.surf_models import POOL4_NETWORKS
from maxpane_dashboard.widgets.surf import _pool4 as P

_WIDGET_DIR = pathlib.Path(P.__file__).parent

#: Every pool4 widget module, discovered -- not a hand-typed list of three.
#: ``sorted`` so a failure names the same module every run.
POOL4_MODULES = sorted(
    [_WIDGET_DIR / "_pool4.py", *_WIDGET_DIR.glob("pool4_*.py")],
    key=lambda p: p.name,
)

_SOURCES = {path.name: path.read_text() for path in POOL4_MODULES}

#: The two names A13 ruled must have exactly one definition across the body.
#:
#: There was a ``_PENDING_MIGRATION = {"pool4_flow.py"}`` exemption here while
#: A13 step 2 was outstanding, guarded by a test that reddened the day the
#: exemption stopped being needed. It reddened, WP5's swap landed, and the
#: **whole mechanism is gone** rather than left as an empty set: a
#: self-clearing list that has cleared has done its job, and an empty one is
#: an invitation to add the next module to it instead of fixing that module.
#: The sweep below now covers every discovered pool4 module with no
#: exceptions, which is the guard this file was written to be.
_HOISTED = ("network_word", "panel_title")


def test_at_least_the_five_panels_and_the_shared_module_were_discovered():
    """A glob that matched nothing would make every check below vacuous --
    the "test that cannot fail" shape this repo keeps a taxonomy of.
    """
    names = {path.name for path in POOL4_MODULES}
    assert "_pool4.py" in names
    assert len(names) >= 6, names


# ---------------------------------------------------------------------------
# The network word: allowlist, dash, and the tripwire that keeps it honest
# ---------------------------------------------------------------------------


def test_the_network_allowlist_agrees_with_the_frozen_vocabulary():
    """The tripwire A13 leans on.

    ``_pool4.NETWORK_WORDS`` restates ``surf_models.POOL4_NETWORKS`` because a
    widget may not import ``data/`` (contract §0.5), and redundancy plus an
    agreement test is the shape CLAUDE.md mandates -- deriving one from the
    other would make this compare a constant against itself and it could never
    fail again.

    Asserted **in both directions**: a network added to the contract and not to
    the widget reddens here (and would otherwise render as an em dash to every
    reader), and a word invented in the widget with no contract behind it
    reddens here too.
    """
    assert set(P.NETWORK_WORDS) == set(POOL4_NETWORKS)
    assert len(P.NETWORK_WORDS) == len(POOL4_NETWORKS)


@pytest.mark.parametrize("word", POOL4_NETWORKS)
def test_a_known_network_renders_as_itself(word):
    assert P.network_word(word) == word
    assert P.panel_title("PANEL", word) == f"PANEL{P.TITLE_SEP}{word}"


@pytest.mark.parametrize(
    "value",
    [None, "", "BASE", "base", "ETHEREUM", "sepolia-fork", 1, 0, True, object(),
     ["SEPOLIA"], "SEPOLIA MAINNET", "[/x]", "$success"],
)
def test_anything_outside_the_allowlist_renders_the_dash(value):
    """A panel confidently naming a chain this build does not recognise is a
    provenance claim nothing supports -- R4 exactly. The dash says "cannot
    stand behind this label", which is the honest answer.
    """
    assert P.network_word(value) == P.NETWORK_UNKNOWN
    assert P.panel_title("PANEL", value).endswith(P.NETWORK_UNKNOWN)


@pytest.mark.parametrize("sloppy", [" sepolia ", "Sepolia", "MAINNET\n"])
def test_case_and_whitespace_are_normalised_not_rejected(sloppy):
    """``" sepolia "`` is the same claim as ``"SEPOLIA"`` spelled sloppily,
    not an unknown chain. Normalising is not laundering: the result still has
    to be a member.
    """
    assert P.network_word(sloppy) in POOL4_NETWORKS


def test_a_title_never_goes_networkless():
    """The suffix is always present -- the word or the dash, never nothing."""
    for value in (None, "BASE", "SEPOLIA"):
        assert P.TITLE_SEP in P.panel_title("PANEL", value)


# ---------------------------------------------------------------------------
# One implementation of the hoisted names
# ---------------------------------------------------------------------------


def _code_strings(source: str) -> list[str]:
    """Every string literal in *source* **except** its docstrings.

    Scanned through the AST rather than over the raw text for two reasons, and
    both of them bit: comments never enter the AST at all, and a docstring
    that *documents* a hazard is not an instance of it -- the first version of
    the ``$``-token check below failed on ``_pool4.py``'s own explanation of
    the trap, which is precisely a test that fails for a reason that is not
    the one it is named for.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr):
                    docstrings.add(id(first.value))
    out: list[str] = []
    for node in ast.walk(tree):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _module_constant(source: str, name: str):
    """The value of a module-level ``name = "literal"``, or ``None``."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value.value
    return None


def _defines(source: str, name: str) -> bool:
    """True when *source* defines *name* itself, rather than importing it."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
    return False


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_no_pool4_widget_module_defines_its_own_network_word_or_title(name):
    """A13 step 3. Two panels spelling the network word differently is a
    reader-visible defect before it is a test failure: one pool4 body could
    paint ``THE SPLIT · —`` beside ``THE RATCHET · BASE``.
    """
    for hoisted in _HOISTED:
        if name == "_pool4.py":
            assert _defines(_SOURCES[name], hoisted), (
                f"_pool4.py must be where {hoisted} lives"
            )
        else:
            assert not _defines(_SOURCES[name], hoisted), (
                f"{name} defines its own {hoisted}; import it from _pool4"
            )


@pytest.mark.parametrize(
    "name", sorted(set(_SOURCES) - {"_pool4.py"})
)
def test_a_shared_name_a_module_uses_is_a_shared_name_it_imported(name):
    """The general form of A13, now that the sweep above has no exemptions.

    ``network_word`` and ``panel_title`` were the two names the amendment
    ruled on, but the failure they came from -- two modules independently
    writing the same helper with different semantics -- is not specific to
    them. So: **every** ``_pool4`` export a pool4 widget module references has
    to have arrived through ``from ... _pool4 import``, never from a local
    definition and never from a third module that happens to re-export it.

    This is the check that would have caught the original divergence on the
    day the second copy was written rather than at the coordinator's review.
    """
    tree = ast.parse(_SOURCES[name])
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.endswith("_pool4"):
                imported |= {alias.asname or alias.name for alias in node.names}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    borrowed = (used & set(P.__all__)) - imported
    assert not borrowed, (
        f"{name} uses {sorted(borrowed)} without importing them from _pool4"
    )

    # And the other half, which the first version of this test missed: a
    # module that *imports* a shared name and then rebinds it at module level
    # passes the check above -- ``imported`` contains the name, so nothing is
    # "borrowed" -- while the local value is what every call site actually
    # sees. Proven by mutation: adding ``WIDEN_HINT = "< widen"`` under an
    # existing ``from ... _pool4 import WIDEN_HINT`` left this file green
    # until the shadow check below was added.
    shadowed = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shadowed.add(node.name)
        elif isinstance(node, ast.Assign):
            shadowed |= {
                t.id for t in node.targets if isinstance(t, ast.Name)
            }
    collisions = shadowed & set(P.__all__)
    assert not collisions, (
        f"{name} rebinds {sorted(collisions)} over the shared definition"
    )


def test_the_widen_vocabulary_means_one_thing_across_the_repo():
    """``SHORT_HINT`` already means ``"‹ widen"`` in ``activity.py``,
    ``launchpad_activity.py`` and ``pool4_flow.py``. The rail panels' narrower
    glyph tier is real -- a pool4 title carries the network word too, so
    ``THE RATCHET · SEPOLIA  ‹ widen`` does not fit a narrow rail -- but it
    gets its own name rather than redefining an established one.
    """
    from maxpane_dashboard.widgets.surf import activity, launchpad_activity
    from maxpane_dashboard.widgets.surf import pool4_flow

    assert P.WIDEN_HINT == "‹ widen"
    for established in (activity, launchpad_activity, pool4_flow):
        assert established.SHORT_HINT == P.WIDEN_HINT, established.__name__
    assert P.GLYPH_HINT != P.WIDEN_HINT
    assert P.GLYPH_HINT in P.WIDEN_HINT          # a tier below, not a rival

    # And no pool4 module may re-point `SHORT_HINT` at the narrower glyph --
    # the collision this test exists to have already fixed, in the one shape
    # that could reintroduce it.
    for name, source in _SOURCES.items():
        value = _module_constant(source, "SHORT_HINT")
        assert value in (None, P.WIDEN_HINT), (
            f"{name} redefines SHORT_HINT as {value!r}; it means "
            f"{P.WIDEN_HINT!r} everywhere else -- use GLYPH_HINT"
        )


# ---------------------------------------------------------------------------
# Discovery-based structural guards over every pool4 widget module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_no_pool4_widget_puts_a_theme_token_inside_its_own_markup(name):
    """The defect that took the app down during WP4's build.

    These modules parse their own markup with ``rich.text.Text.from_markup``
    -- CLAUDE.md's "hand ``Static`` a pre-built ``Text``, never a markup
    string" rule -- and Rich cannot resolve Textual's ``$``-prefixed theme
    variables. ``[bold $success]`` parses fine and raises ``MissingStyle`` at
    **render** time, inside ``Static.update``, i.e. in the message pump and
    outside the widget's own ``try``. It is the same hazard the terminal-layout
    skill records for ``DataTable.default_cell_formatter``, reached from the
    other direction.

    Rich colour names (``green``, ``cyan``, ``yellow``, ``dim``) are the fix.
    This is checked by discovery so a pool4 module written after WP4 is
    covered the day it lands.
    """
    for literal in _code_strings(_SOURCES[name]):
        assert "[$" not in literal, f"{name}: {literal!r}"
        for token in ("$success", "$warning", "$error", "$accent", "$primary"):
            assert f"[bold {token}" not in literal, f"{name}: {literal!r}"
            assert f"[dim {token}" not in literal, f"{name}: {literal!r}"


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_a_pool4_widget_module_stays_pure(name):
    """Contract §0.5's module boundary, asserted as *purity* rather than as a
    banned name (CLAUDE.md: "state it that way and prove it").

    An AST walk, so a lazy import inside a function is caught too. ``data/``
    and ``analytics/`` are out because they are the layers that reach the
    network; ``httpx``/``aiohttp`` are out directly; a clock is out because
    every age reaching a pool4 widget is precomputed by the manager, which is
    the only reason a committed capture replays forever.
    """
    tree = ast.parse(_SOURCES[name])
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    for module in modules:
        top = module.split(".")
        assert "data" not in top, f"{name} imports {module}"
        assert "analytics" not in top, f"{name} imports {module}"
        assert top[0] not in ("httpx", "aiohttp", "time", "datetime"), (
            f"{name} imports {module}"
        )


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_a_pool4_widget_module_never_copies_the_sparkline_helpers(name):
    """MEDI-36: ``sparkline_common`` is the single definition, and three
    byte-identical copies of ``_coerce_points`` are what it cost to learn it.
    """
    source = _SOURCES[name]
    assert "▁▂▃" not in source
    assert "SPARK_CHARS =" not in source
