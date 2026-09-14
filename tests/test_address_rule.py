"""E1: one address formatter in the whole app. E5: one clipboard module."""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path("maxpane_dashboard")
HELPER = ROOT / "widgets" / "address.py"
CLIPBOARD = ROOT / "clipboard.py"

FORMATTER_NAME = re.compile(r"_?(short|long|full|fmt|truncate)_?addr(ess)?$", re.I)
SLICE_DIRS = {"widgets", "screens", "data", "analytics"}
#: The largest head or tail a shortening slice keeps; a longer one is not an
#: address window (a 40-hex tail slice is a different operation).
SMALL_BOUND = 12
CLIPBOARD_TOOLS = ("pbcopy", "wl-copy", "xclip", "xsel")
#: ``clip`` is also an ordinary English word ("pad/clip to width"), a CSS value
#: (``text-overflow: clip``) and the name of surf's ``_rowfit.clip`` helper, so
#: it is matched only as a **string literal that is the command itself**
#: (``"clip"``, ``"clip.exe"``, optionally with arguments), the form a
#: subprocess argument list or a shell string takes.
CLIP_WORD = re.compile(r"\s*clip(\.exe)?\b(\s.*)?", re.S)


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        yield path, path.read_text()


# -- E1 slice shapes ---------------------------------------------------------------


def _int_const(node) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant) and type(node.operand.value) is int):
        return -node.operand.value
    return None


def _is_head_slice(s) -> bool:
    """``x[:n]`` or ``x[0:n]`` with a small constant ``n``."""
    if not isinstance(s, ast.Slice) or s.step is not None:
        return False
    lower = None if s.lower is None else _int_const(s.lower)
    if s.lower is not None and lower != 0:
        return False
    upper = _int_const(s.upper) if s.upper is not None else None
    return upper is not None and 0 < upper <= SMALL_BOUND


def _is_tail_slice(s) -> bool:
    """``x[-n:]`` with a small constant ``n``."""
    if not isinstance(s, ast.Slice) or s.step is not None or s.upper is not None:
        return False
    lower = _int_const(s.lower) if s.lower is not None else None
    return lower is not None and -SMALL_BOUND <= lower < 0


def _composes_text(node) -> bool:
    if isinstance(node, (ast.JoinedStr, ast.BinOp)):
        return True
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format")


def slice_shortening_lines(source: str) -> list[int]:
    """Lines where one text-composing expression keeps a head **and** a tail slice.

    That is the private-formatter shape in every spelling: an f-string (any
    separator, markup between the halves, ``[0:6]``), ``+`` concatenation, ``%``
    and ``.format``. A docstring or comment quoting the shape is a string
    constant, not an expression, so it is never flagged.
    """
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not _composes_text(node):
            continue
        slices = [n.slice for n in ast.walk(node) if isinstance(n, ast.Subscript)]
        if any(_is_head_slice(s) for s in slices) and any(_is_tail_slice(s) for s in slices):
            lines.add(node.lineno)
    return sorted(lines)


BANNED_SHAPES = (
    'f"{a[:6]}...{a[-4:]}"',
    'a[:6] + "…" + a[-4:]',
    '"{}…{}".format(a[:6], a[-4:])',
    'f"{a[0:6]}…{a[-4:]}"',
    'f"{a[:6]}[dim]…[/]{a[-4:]}"',
    'f"{a[:6]}…{a[-4:]}"',
    '"%s…%s" % (a[:10], a[-6:])',
)


def test_the_slice_checker_flags_every_banned_spelling():
    for shape in BANNED_SHAPES:
        assert slice_shortening_lines(f"x = {shape}\n") == [1], shape


def test_the_slice_checker_ignores_quotes_and_unrelated_slices():
    quoted = 'def f(a):\n    """used to return ``f"{a[:6]}…{a[-4:]}"``."""\n    return a\n'
    assert slice_shortening_lines(quoted) == []
    comment = '# f"{a[:6]}…{a[-4:]}"\nx = 1\n'
    assert slice_shortening_lines(comment) == []
    apart = "head = a[:6]\ntail = a[-4:]\n"
    assert slice_shortening_lines(apart) == []
    wide = 'x = f"{a[:40]}…{a[-40:]}"\n'
    assert slice_shortening_lines(wide) == []


# -- E5 clipboard words -------------------------------------------------------------


def _docstring_ids(tree) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    ids.add(id(stmt.value))
    return ids


def _all_export_ids(tree) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                ids.update(id(n) for n in ast.walk(node.value) if isinstance(n, ast.Constant))
    return ids


def clip_literals(source: str) -> list[int]:
    """Lines of string literals naming ``clip`` as a word (not docs, not ``__all__``)."""
    tree = ast.parse(source)
    skip = _docstring_ids(tree) | _all_export_ids(tree)
    return sorted({
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in skip and CLIP_WORD.fullmatch(node.value)
    })


def test_the_clip_checker_flags_a_command_and_ignores_prose():
    assert clip_literals('cmd = ("clip",)\n') == [1]
    assert clip_literals('run(["clip.exe"])\n') == [1]
    assert clip_literals('def f():\n    """pad/clip to width"""\n') == []
    assert clip_literals('__all__ = ["clip", "pad"]\n') == []
    assert clip_literals('x = "clipboard"\n# clip\n') == []
    assert clip_literals('CSS = """\nRow {\n    text-overflow: clip;\n}\n"""\n') == []
    assert clip_literals('run("clip < out.txt", shell=True)\n') == [1]


# -- the scans ----------------------------------------------------------------------


def test_the_scan_sees_the_app():
    paths = {path for path, _ in _sources()}
    assert HELPER in paths and CLIPBOARD in paths, "run from the repo root"


def test_the_formatter_name_pattern_matches_the_names_it_bans():
    assert FORMATTER_NAME.fullmatch("_short_addr")
    assert FORMATTER_NAME.fullmatch("long_address")
    assert FORMATTER_NAME.fullmatch("fmt_addr")
    assert not FORMATTER_NAME.fullmatch("short_address_cols")


def test_no_module_but_the_helper_defines_an_address_formatter():
    offenders = []
    for path, src in _sources():
        if path == HELPER:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and FORMATTER_NAME.fullmatch(node.name):
                offenders.append(f"{path}:{node.lineno} {node.name}")
    assert not offenders, offenders


def test_no_module_but_the_helper_shortens_hex_by_slicing():
    offenders = []
    for path, src in _sources():
        if path == HELPER or path.parts[1] not in SLICE_DIRS:
            continue
        lines = src.splitlines()
        for lineno in slice_shortening_lines(src):
            offenders.append(f"{path}:{lineno}: {lines[lineno - 1].strip()}")
    assert not offenders, offenders


# -- the address floor ----------------------------------------------------------------
#
# ``widgets/address._window`` clamps every width to ``MIN_SHORT_COLS``, so a
# caller that budgets an address below it gets a cell two or more cells wider
# than it asked for, and whatever bounds that cell (a DataTable column, a
# RichLog line, a CSS ellipsis) cuts the end of it: the icon. FWA shipped four
# of those. A literal below the floor is caught here; a module constant below
# it is held to :data:`KNOWN_CONSTANTS_BELOW_FLOOR`, which may only shrink; and
# a computed budget must clamp itself with ``max(MIN_SHORT_COLS, …)``.

_WIDTH_CALLS = {"address_text": "width", "short_address": 1}


def _module_int_constants(tree) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = _int_const(node.value) if node.value is not None else None
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    out[target.id] = value
    return out


#: Address widths that are a module constant below the floor, found when this
#: check was written (2026-09-14) in packages outside that fix wave. Each is a
#: symbol-backed token cell whose unnamed fallback is an address; whether the
#: column around it absorbs the clamp is unmeasured. Reported, not fixed: the
#: list may only shrink. ``(path, constant)``.
KNOWN_CONSTANTS_BELOW_FLOOR = frozenset({
    ("maxpane_dashboard/widgets/base/graduated.py", "_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/launch_feed.py", "_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/overview.py", "_MOVERS_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/overview.py", "_VOL_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/overview/_legacy_overview.py", "_MOVERS_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/overview/_legacy_overview.py", "_VOL_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/overview/bt_overview_leaderboard.py", "_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/top_movers.py", "_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/base/trending_table.py", "_TOKEN_COLS"),
    ("maxpane_dashboard/widgets/ttt/ttt_fees_table.py", "_SYM_WIDTH"),
    ("maxpane_dashboard/widgets/ttt/ttt_leaderboard.py", "_SYM_WIDTH"),
})


def address_widths_below_floor(source: str, floor: int) -> list[tuple[int, str | None, str]]:
    """``(line, constant, call)`` for every address width that is a known int below ``floor``.

    A width is known when it is an int literal (``constant`` is ``None``) or a
    module-level name bound to one; ``None`` and computed widths are not judged.
    """
    tree = ast.parse(source)
    constants = _module_int_constants(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        where = _WIDTH_CALLS.get(name)
        if where is None:
            continue
        arg = None
        for keyword in node.keywords:
            if keyword.arg == "width":
                arg = keyword.value
        if arg is None and isinstance(where, int) and len(node.args) > where:
            arg = node.args[where]
        if arg is None:
            continue
        value, constant = _int_const(arg), None
        if value is None and isinstance(arg, ast.Name):
            value, constant = constants.get(arg.id), arg.id
        if value is not None and value < floor:
            found.append((node.lineno, constant, ast.unparse(node)))
    return found


def test_the_floor_checker_flags_literals_and_constants_below_the_floor():
    assert address_widths_below_floor("address_text(a, width=10)\n", 11) == [(1, None, "address_text(a, width=10)")]
    assert address_widths_below_floor("A.short_address(a, 4)\n", 11) == [(1, None, "A.short_address(a, 4)")]
    assert address_widths_below_floor("W = 9\naddress_text(a, label=n, width=W)\n", 11)[0][1] == "W"
    assert address_widths_below_floor("address_text(a, width=-1)\n", 11)
    assert address_widths_below_floor("address_text(a, width=11)\nshort_address(a, 17)\n", 11) == []
    assert address_widths_below_floor("address_text(a, width=None)\naddress_text(a)\n", 11) == []
    assert address_widths_below_floor("address_text(a, width=max(11, w - 2))\n", 11) == []
    assert address_widths_below_floor("short_hex(tx, 4)\n", 11) == [], "a hash is not an address"


def test_no_address_is_budgeted_below_the_window_floor():
    from maxpane_dashboard.widgets.address import MIN_SHORT_COLS

    offenders, known = [], set()
    for path, src in _sources():
        if path == HELPER:
            continue
        for line, constant, call in address_widths_below_floor(src, MIN_SHORT_COLS):
            if constant is not None and (str(path), constant) in KNOWN_CONSTANTS_BELOW_FLOOR:
                known.add((str(path), constant))
                continue
            offenders.append(f"{path}:{line}: {call}")
    assert not offenders, offenders
    assert known == KNOWN_CONSTANTS_BELOW_FLOOR, (
        "a known constant was fixed or renamed; drop it from the list",
        sorted(KNOWN_CONSTANTS_BELOW_FLOOR - known),
    )


def test_only_the_clipboard_module_names_a_clipboard_tool():
    offenders = []
    for path, src in _sources():
        if path == CLIPBOARD:
            continue
        for tool in CLIPBOARD_TOOLS:
            if tool in src:
                offenders.append(f"{path}: {tool}")
        offenders.extend(f"{path}:{line}: clip" for line in clip_literals(src))
    assert not offenders, offenders
