"""E1: one address formatter in the whole app. E5: one clipboard module."""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path("maxpane_dashboard")
HELPER = ROOT / "widgets" / "address.py"
CLIPBOARD = ROOT / "clipboard.py"

FORMATTER_NAME = re.compile(r"_?(short|long|full|fmt|truncate)_?addr(ess)?$", re.I)
SLICE_SHAPE = re.compile(r"\[:\s*\d+\s*\]\s*\}\s*(…|\.\.)\s*\{[^}]*\[\s*-\s*\d+\s*:\s*\]")
CLIPBOARD_TOOLS = ("pbcopy", "wl-copy", "xclip", "xsel")


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        yield path, path.read_text()


def test_the_scan_sees_the_app():
    paths = {path for path, _ in _sources()}
    assert HELPER in paths and CLIPBOARD in paths, "run from the repo root"


def test_the_patterns_match_the_shapes_they_ban():
    assert FORMATTER_NAME.fullmatch("_short_addr")
    assert FORMATTER_NAME.fullmatch("long_address")
    assert FORMATTER_NAME.fullmatch("fmt_addr")
    assert not FORMATTER_NAME.fullmatch("short_address_cols")
    assert SLICE_SHAPE.search('f"{a[:6]}…{a[-4:]}"')
    assert SLICE_SHAPE.search('f"{addr[:10]}..{addr[-6:]}"')


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
        if path == HELPER or path.parts[1] not in {"widgets", "screens", "data", "analytics"}:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if SLICE_SHAPE.search(line):
                offenders.append(f"{path}:{i}: {line.strip()}")
    assert not offenders, offenders


def test_only_the_clipboard_module_names_a_clipboard_tool():
    offenders = []
    for path, src in _sources():
        if path == CLIPBOARD:
            continue
        for tool in CLIPBOARD_TOOLS:
            if tool in src:
                offenders.append(f"{path}: {tool}")
    assert not offenders, offenders
