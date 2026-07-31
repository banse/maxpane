"""The shared guarded call, and the guard that keeps it shared (LOW-11).

``_safe_call`` existed eight times -- once per manager -- and drifted into
three incompatible variants. Five of them logged a bare ``fn.__name__``,
so the *exception handler itself* raised ``AttributeError`` for any
callable without that attribute, and the escape propagated into
``fetch_and_compute``: a degraded number became a failed refresh cycle,
which is the precise inversion of the helper's contract.

Two kinds of test live here, and they protect different things:

* the **behaviour** tests pin what the reconciled helper does -- the
  drift is only really resolved once the resolved semantics are written
  down as assertions;
* the **guard** tests pin that there is exactly one of it. Consolidation
  without a guard lasts until the next person needs a wrapper and writes
  one locally, which is how eight copies happened in the first place.
"""

from __future__ import annotations

import ast
import importlib
import logging
from functools import partial
from pathlib import Path

import pytest

from maxpane_dashboard.data import safe_call as safe_call_module
from maxpane_dashboard.data.safe_call import safe_call

# Every dashboard's manager, discovered rather than listed, so dashboard #9
# is covered by the guards below on the day it is added.
SAFE_CALL_PATH = Path(safe_call_module.__file__)
DATA_DIR = SAFE_CALL_PATH.parent
PACKAGE_DIR = DATA_DIR.parent
MANAGER_PATHS = sorted(DATA_DIR.glob("*_manager.py"))
MANAGER_NAMES = [p.stem for p in MANAGER_PATHS]

# Closed-world: every module in the package except the one that owns the
# helper. ``data/manager.py`` (the bakery) does not match the ``*_manager.py``
# convention, and a widget or screen is just as able to paste a wrapper as a
# manager is, so the guard scans everything rather than the eight known sites.
PACKAGE_PATHS = sorted(
    p for p in PACKAGE_DIR.rglob("*.py") if p.resolve() != SAFE_CALL_PATH.resolve()
)


def _manager_module(name: str):
    return importlib.import_module(f"maxpane_dashboard.data.{name}")


# ---------------------------------------------------------------------------
# 1. the duplicates cannot come back
# ---------------------------------------------------------------------------


def test_the_manager_inventory_is_not_empty() -> None:
    """A glob that silently matches nothing makes every guard below vacuous."""
    assert len(MANAGER_PATHS) >= 8, (
        f"expected the eight dashboard managers under {DATA_DIR}, "
        f"found {MANAGER_NAMES}"
    )


def test_no_module_defines_its_own_safe_call() -> None:
    """A pasted helper body must fail this test, not ship quietly.

    Parsed rather than grepped: the module docstrings deliberately discuss
    ``_safe_call`` by name, and prose must stay free to name what code may
    not do. Only real ``def`` statements count -- at any nesting depth, so a
    copy hidden inside a method is caught too. Every offender is reported at
    once, because the failure this guards against arrives eight at a time.
    """
    forked: list[str] = []
    for path in PACKAGE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in {"_safe_call", "safe_call"}
            ):
                forked.append(f"{path.relative_to(PACKAGE_DIR)}:{node.lineno}")
    assert not forked, (
        f"{forked} define a private safe_call instead of importing from "
        "data/safe_call.py -- import it, do not copy it. Eight drifted copies "
        "are what LOW-11 was."
    )


@pytest.mark.parametrize("name", MANAGER_NAMES)
def test_every_manager_uses_the_shared_function(name: str) -> None:
    """Identity, not just absence of a local ``def``.

    The AST scan above is satisfiable by importing something else under the
    same alias; this pins that ``_safe_call`` in each manager *is* the one
    function, so a fix here reaches all eight dashboards.
    """
    module = _manager_module(name)
    assert getattr(module, "_safe_call", None) is safe_call, (
        f"{name} does not use the shared safe_call; a private copy is how the "
        "eight-way fork happened (LOW-11)"
    )


# ---------------------------------------------------------------------------
# 2. the contract: nothing escapes
# ---------------------------------------------------------------------------


def test_a_successful_call_returns_its_value_untouched() -> None:
    assert safe_call(lambda a, b: a + b, 2, 3) == 5


def test_a_falsy_result_is_returned_not_replaced_by_the_default() -> None:
    """``or default`` would be wrong here; several call sites return 0/{}."""
    assert safe_call(lambda: 0, default=99) == 0
    assert safe_call(lambda: {}, default={"x": 1}) == {}


def test_a_raising_function_returns_the_default() -> None:
    def boom() -> None:
        raise ValueError("nope")

    assert safe_call(boom, default={"ok": False}) == {"ok": False}


def test_the_default_default_is_none() -> None:
    def boom() -> None:
        raise ValueError("nope")

    assert safe_call(boom) is None


def test_a_raising_partial_returns_the_default() -> None:
    """``functools.partial`` has no ``__name__``.

    The five older copies read ``fn.__name__`` in the handler, so this case
    raised ``AttributeError`` *out of* the helper and failed the whole
    refresh cycle instead of degrading one number.
    """

    def boom(a: int, b: int) -> None:
        raise ValueError("nope")

    fn = partial(boom, 1)
    assert not hasattr(fn, "__name__")
    assert safe_call(fn, 2, default="fallback") == "fallback"


def test_a_raising_callable_object_returns_the_default() -> None:
    """The other shape of nameless callable, and the one that will arrive.

    Analytics helpers built as configured objects (a threshold carried on
    ``self``) are the realistic future call site.
    """

    class Signal:
        def __call__(self, value: int) -> None:
            raise RuntimeError("nope")

    assert safe_call(Signal(), 1, default="fallback") == "fallback"


def test_a_nameless_callable_is_still_identified_in_the_log(caplog) -> None:
    """Degrading silently is only half the contract; it must be discoverable."""

    def boom(a: int, b: int) -> None:
        raise ValueError("nope")

    with caplog.at_level(logging.WARNING):
        safe_call(partial(boom, 1), 2, default=None)
    assert "nope" in caplog.text
    assert "boom" in caplog.text, (
        "the repr fallback should still name the wrapped function"
    )


def test_keyboardinterrupt_is_not_swallowed() -> None:
    """``except Exception``, deliberately, not ``except BaseException``.

    Absorbing Ctrl-C would make a hung refresh cycle uninterruptible -- the
    helper degrades analytics, it does not defeat the user.
    """

    def boom() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        safe_call(boom, default="fallback")


# ---------------------------------------------------------------------------
# 3. the reconciled signature
# ---------------------------------------------------------------------------


def test_keyword_arguments_are_forwarded() -> None:
    """The ``fwa_manager`` variant took ``**kwargs``; seven call sites need it.

    Accepting them is the superset -- no pre-existing positional call site
    changes meaning -- and building a signal dict by keyword is unreadable
    any other way.
    """

    def build(a: int, *, b: int, c: int) -> dict[str, int]:
        return {"a": a, "b": b, "c": c}

    assert safe_call(build, 1, b=2, c=3) == {"a": 1, "b": 2, "c": 3}


def test_a_raising_call_with_keywords_still_returns_the_default() -> None:
    def build(*, b: int) -> None:
        raise ValueError("nope")

    assert safe_call(build, b=2, default={}) == {}


def test_default_is_keyword_only_and_is_not_forwarded() -> None:
    """``default`` follows ``*args``, so it can never be eaten positionally.

    It is also consumed by the wrapper rather than passed on, which matters
    because analytics functions of the form ``f(values, default=...)`` are
    plausible -- and ``fwa_manager`` already passes ``default`` alongside
    eight domain keywords in one call.
    """
    seen: dict[str, object] = {}

    def record(**kwargs: object) -> str:
        seen.update(kwargs)
        return "called"

    assert safe_call(record, default="unused", x=1) == "called"
    assert seen == {"x": 1}, "default must not reach the wrapped callable"


def test_a_misspelled_default_is_loud_not_silent() -> None:
    """The one cost of ``**kwargs``, and why the log level matters.

    ``defualt=`` is forwarded to a callable that does not accept it, so the
    ``TypeError`` lands inside the ``try`` and the real default (``None``)
    is returned instead of the intended fallback. That is a typo the type
    checker cannot see, so the record it leaves must be visible at
    MaxPane's default log level -- WARNING.
    """

    def analytics(value: int) -> int:
        return value * 2

    with _capture() as records:
        result = safe_call(analytics, 1, defualt=[])

    assert result is None
    assert any("analytics" in r.getMessage() for r in records)


class _capture:
    """Collect records from the shared helper's own logger.

    The logger is opened to ``level`` (DEBUG by default) so that a record at
    *any* level is captured -- otherwise a test asserting "this is a WARNING"
    would pass just as happily against silence.
    """

    def __init__(self, level: int = logging.DEBUG) -> None:
        self.level = level
        self.records: list[logging.LogRecord] = []

    def __enter__(self) -> list[logging.LogRecord]:
        self.handler = logging.Handler(logging.NOTSET)
        self.handler.emit = self.records.append  # type: ignore[method-assign]
        self.logger = logging.getLogger(safe_call_module.__name__)
        self.logger.addHandler(self.handler)
        self.previous = self.logger.level
        self.logger.setLevel(self.level)
        return self.records

    def __exit__(self, *exc: object) -> None:
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.previous)


# ---------------------------------------------------------------------------
# 4. the log level decision
# ---------------------------------------------------------------------------


def test_failures_log_at_warning_not_debug() -> None:
    """Six of the eight copies used ``debug``; under the shipped config that
    means they logged nothing at all.

    ``__main__.py`` calls ``basicConfig(level=WARNING)`` by default, so a
    persistent analytics failure in those six was invisible: the user saw a
    fallback number with no way to learn it was one. Nothing routed through
    this helper does network I/O, so the usual objection to WARNING -- flooding
    on a flaky public RPC -- does not apply.
    """

    def boom() -> None:
        raise ValueError("nope")

    with _capture() as records:
        safe_call(boom)

    assert [r.levelno for r in records] == [logging.WARNING], (
        "one record, at WARNING -- DEBUG would be dropped by the default "
        "basicConfig(level=WARNING) in __main__.py"
    )


def test_the_shared_logger_is_silenceable_in_one_place() -> None:
    """The compensation for choosing the louder level.

    Eight module loggers could not be turned down together; one can. Anyone
    who finds a persistently failing analytics call too noisy has a single
    lever, which was not true while the helper lived in eight modules.
    """
    with _capture(logging.CRITICAL) as records:
        assert safe_call(lambda: 1 / 0, default="fallback") == "fallback"

    assert records == []


# ---------------------------------------------------------------------------
# 5. the module stays a leaf
# ---------------------------------------------------------------------------


def test_safe_call_imports_nothing_from_the_package() -> None:
    """A helper every manager imports must not import any of them back.

    ``data/series_points.py`` set this precedent: stdlib and typing only, so
    the shared leaf cannot introduce a cycle or drag a dashboard's
    dependencies into the other seven.
    """
    tree = ast.parse(Path(safe_call_module.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [m for m in imported if m.startswith("maxpane_dashboard")], (
        f"data/safe_call.py must stay a leaf; it imports {imported}"
    )
