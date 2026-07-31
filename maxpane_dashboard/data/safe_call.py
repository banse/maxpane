"""The one guarded call behind every dashboard's analytics layer.

Every manager computes its signals by handing a pure analytics function
to a small wrapper: if that function raises, one number on the screen
degrades to a fallback and the refresh cycle carries on.  The contract is
"an analytics bug must cost one number, not the whole cycle".

That wrapper existed eight times -- once per manager -- and the copies
drifted into three incompatible variants.  The worst of the drift was in
the exception handler itself: five copies logged a bare ``fn.__name__``,
which raises ``AttributeError`` for any callable that has no such
attribute (a ``functools.partial``, a callable object).  That
``AttributeError`` escapes *the very helper whose job is to let nothing
escape*, turning a should-be-degraded analytics failure into a failed
refresh cycle -- the exact inversion of the contract (LOW-11).  Reading a
call site told you nothing about which variant you had: the fixed and the
broken forms are identical from the outside.

Three reconciliation decisions are baked in here, deliberately:

``**kwargs`` are forwarded.
    Seven copies took positional arguments only; ``fwa_manager``'s took
    ``**kwargs`` and seven of its call sites depend on it (they build
    signal dicts by keyword).  Accepting them is the superset, so no
    existing call site changes meaning.  ``default`` follows ``*args``
    and is therefore keyword-only, so it can never be swallowed by a
    positional argument; a *misspelled* ``default=`` is forwarded to
    ``fn`` instead, which raises ``TypeError`` inside the ``try`` and is
    logged -- visibly, see below -- rather than passing silently.

The callable's name is read defensively.
    ``getattr(fn, "__name__", fn)`` is the whole point of the finding.
    A callable without a ``__name__`` falls back to its ``repr``, which
    is what you wanted in the log anyway.

Failures log at ``warning``, not ``debug``.
    Six of the eight copies used ``debug`` -- but MaxPane's default log
    level is ``WARNING`` (``__main__.py``), so under the shipped
    configuration those six logged precisely nothing: a persistent
    analytics failure was invisible, and the user saw a fallback number
    with no way to learn it was a fallback.  The usual argument against
    ``warning`` -- log flooding -- does not apply here, because nothing
    routed through this helper does network I/O (the clients own that,
    and their own retry logging); these are pure functions over
    already-fetched data.  Output also goes to ``~/.maxpane/maxpane.log``,
    truncated per run, never to the TUI.  Anyone who does want silence
    can set the level on this one logger, which is a thing you could not
    do while the helper lived in eight modules.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_call(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """Call ``fn(*args, **kwargs)``, returning *default* on any exception.

    Never raises -- including out of its own exception handler.  Logs at
    ``warning`` so a degraded number is discoverable at MaxPane's default
    log level.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- absorbing everything is the point
        logger.warning(
            "Analytics call %s failed: %s", getattr(fn, "__name__", fn), exc
        )
        return default


__all__ = ["safe_call"]
