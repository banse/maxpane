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
