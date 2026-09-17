"""E2: every address that reaches the screen carries an icon that copies it.

Per case, across all of its views, four questions (PRD §7 E2):

1. **Every icon copies an address the screen was given**, and **the address it
   copies is the one printed right before it**: a whole address must equal it,
   a shortened ``0x<head>…<tail>`` window must share its head and tail. An icon
   behind a label (a name, a symbol) is checked against the payload instead: a
   label the payload carries must sit in a record that also holds the address
   the icon copies, so a row whose icon copies its neighbour's address fails.
2. **Every address printed on screen has its icon**: a whole address, and a
   shortened window whose head and tail match an address the screen was given.
3. **Every seeded address gets an icon in some view**, or a panel dropped one.
4. **Every mounted widget whose module imports the helper produces an icon in
   some view**, unless ``EXEMPT`` names that class with its reason. A panel that
   silently stops rendering its icons, including one that prints its addresses
   in a shape the scans above cannot read, fails here.
5. **An ``EXEMPT`` widget prints no whole or shortened address** in its own
   region, so an exemption cannot hide a widget that renders addresses.

Each case is swept at :data:`SIZE` (170 columns) and again at each view's own
layout pin, plus any ``extra_sizes`` it names (:func:`sizes_for`). Questions 1,
2 and 5 are asked at every size; 3 and 4 only at 170, where every body has room
for every unit it can shed at a pin.

An address-free case gets the opposite: no icon, no whole or shortened address,
and no helper-using widget mounted at all.
"""

from __future__ import annotations

import dataclasses
import re
import types

import pytest
from rich.cells import cell_len

from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.widgets.address import ADDRESS_RE, PROSE_ADDRESS_RE
from tests.address_sweep.case import SweepCase, view_name
from tests.address_sweep.imports import imports_helper
from tests.address_sweep.registry import CASES
from tests.widgets.address_probe import icon_targets

#: The sweep's wide terminal: wide and tall enough for every body to render.
SIZE = (170, 60)


def sizes_for(case: SweepCase, kind: str) -> list[tuple[int, int]]:
    """The terminal each of ``case``'s views is swept at, in ``views`` order.

    ``wide`` is :data:`SIZE` for every view. ``pin`` is each view's own layout
    pin (``case.pins``; ``__main__.FULL_LAYOUT_COLUMNS`` when it names none),
    because 170 columns hides every defect that only exists where a panel is
    tight: an address budgeted below the window floor loses its icon at the
    pin and not at 170. ``extra-N`` is ``case.extra_sizes[N]``.
    """
    count = len(case.views)
    if kind == "wide":
        return [SIZE] * count
    if kind == "pin":
        pins = case.pins or ((FULL_LAYOUT_COLUMNS, None),)
        if len(pins) == 1:
            pins = pins * count
        assert len(pins) == count, (case.name, "one pin per view, or a single pin for all")
        return [(cols, rows or SIZE[1]) for cols, rows in pins]
    index = int(kind.removeprefix("extra-"))
    cols, rows = case.extra_sizes[index]
    return [(cols, rows or SIZE[1])] * count


def _size_params() -> list:
    params = []
    for case in CASES:
        kinds = ["wide", "pin", *(f"extra-{i}" for i in range(len(case.extra_sizes)))]
        params.extend(pytest.param(case, kind, id=f"{case.name}-{kind}") for kind in kinds)
    return params

#: A shortened address window, ``0x<head>…<tail>``.
SHORT_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])0x([0-9a-fA-F]+)…([0-9a-fA-F]+)(?![0-9a-fA-F])")
_WINDOW_RE = re.compile(r"0x([0-9a-fA-F]+)…([0-9a-fA-F]+)")
#: A transaction hash: shortened through ``short_hex`` with no icon, by design.
HASH_RE = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{64}(?![0-9a-fA-F])")
_TOKEN_CHARS = frozenset("0123456789abcdefABCDEFx…")

#: Widget classes that import the helper yet never produce an icon, each with
#: the reason. A class, never a module or package.
EXEMPT: dict[str, str] = {
    "maxpane_dashboard.widgets.surf.feed.SurfFeedToggle":
        "a thread's expand/collapse toggle; feed.py imports only is_copy_click for it",
    "maxpane_dashboard.widgets.surf.launchpad.SurfCurveFlow":
        "swap, trader and ETH-owed totals only; no address in its contract",
    "maxpane_dashboard.widgets.surf.launchpad.SurfBurnPipeline":
        "burn pipeline status and amounts only; no address in its contract",
    "maxpane_dashboard.widgets.surf.swarm_throughput.SurfSwarmThroughput":
        "quotes each agent's last score transaction hash through short_hex; a"
        " hash, never an address, so it carries no icon by design",
    "maxpane_dashboard.widgets.surf.swarm_field.SurfSwarmField":
        "a dispatch note's embedded address (address_prose) is the only icon"
        " this panel can ever show, and it lives in the ``note`` column that"
        " only paints at the ``full`` tier (budget >= FULL_WIDTH = 117 cells)."
        " SurfSwarmField is one of two 1fr columns sharing this body's own"
        " width, so reaching that budget needs roughly double the sweep's own"
        " 170-column SIZE (measured: the note column stays hidden through"
        " 240 columns and first paints at 250) -- wider than both the wide"
        " sweep and this body's own layout pin (93), so no render this sweep"
        " produces can ever show one",
    # wallet.py's own contract: "Only this panel's ``wallet`` line ever carries a
    # real address" (CuratorWalletAddress); the rest describe that wallet.
    "maxpane_dashboard.widgets.curator.wallet.CuratorWalletHero":
        "the y view's three boxes about the reader: numbers, never the address",
    "maxpane_dashboard.widgets.curator.wallet.CuratorWalletLadder":
        "the reader's sends (hour, ETH, weight); you_address only keys the rows",
    "maxpane_dashboard.widgets.curator.wallet.CuratorWalletStanding":
        "rank, score, credit, share and join time of the reader's wallet; no address",
    "maxpane_dashboard.widgets.curator.wallet.CuratorWalletNext":
        "what the next legal send must be and buys; amounts only",
    "maxpane_dashboard.widgets.curator.wallet.CuratorWalletTarget":
        "what the place above would cost; amounts only, never that wallet's address",
}


def _rows(app) -> list[str]:
    return ["".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips()]


def _strings_in(value) -> list[str]:
    """Every string ``value`` holds, however it is stored.

    Dicts (keys and values), sequences and sets, dataclasses and objects with a
    ``__dict__`` (pydantic models). Stops at classes, modules and callables, and
    walks with an explicit stack so a deep graph cannot hit the recursion limit.
    """
    out: list[str] = []
    seen: set[int] = set()
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            out.append(v)
            continue
        if v is None or isinstance(v, (bool, int, float, complex, bytes, bytearray)):
            continue
        if isinstance(v, (type, types.ModuleType)) or callable(v):
            continue
        if id(v) in seen:
            continue
        seen.add(id(v))
        if isinstance(v, dict):
            for key, item in v.items():
                stack.append(key)
                stack.append(item)
        elif isinstance(v, (list, tuple, set, frozenset)):
            stack.extend(v)
        elif dataclasses.is_dataclass(v):
            stack.extend(getattr(v, f.name, None) for f in dataclasses.fields(v))
        elif hasattr(v, "__dict__"):
            stack.extend(vars(v).values())
    return out


def _addresses_in(value) -> set[str]:
    """Every address ``value`` holds, lower-cased, whole or inside prose."""
    return {m.group(0).lower() for s in _strings_in(value) for m in PROSE_ADDRESS_RE.finditer(s)}


def _hashes_in(value) -> set[str]:
    return {m.group(0).lower() for s in _strings_in(value) for m in HASH_RE.finditer(s)}


def _records_in(value) -> list[list[str]]:
    """The direct string fields (and keys) of every dict, dataclass and object."""
    records: list[list[str]] = []
    seen: set[int] = set()
    stack = [value]
    while stack:
        v = stack.pop()
        if v is None or isinstance(v, (str, bytes, bytearray, bool, int, float, complex)):
            continue
        if isinstance(v, (type, types.ModuleType)) or callable(v) or id(v) in seen:
            continue
        seen.add(id(v))
        if isinstance(v, dict):
            items = [*v.keys(), *v.values()]
        elif isinstance(v, (list, tuple, set, frozenset)):
            stack.extend(v)
            continue
        elif dataclasses.is_dataclass(v):
            items = [getattr(v, f.name, None) for f in dataclasses.fields(v)]
        elif hasattr(v, "__dict__"):
            items = list(vars(v).values())
        else:
            continue
        records.append([x for x in items if isinstance(x, str)])
        stack.extend(x for x in items if not isinstance(x, str))
    return records


class _LabelIndex:
    """Which record text goes with which address, for label-backed icons."""

    def __init__(self, served) -> None:
        by_address: dict[str, list[str]] = {}
        everything: list[str] = []
        for record in _records_in(served):
            text = "\n".join(record).lower()
            everything.append(text)
            for address in {m.group(0).lower() for s in record for m in PROSE_ADDRESS_RE.finditer(s)}:
                by_address.setdefault(address, []).append(text)
        self._by_address = {a: "\n".join(t) for a, t in by_address.items()}
        self._everything = "\n".join(everything)

    def contradicts(self, label: str, address: str) -> bool:
        """True when the payload carries ``label``, but never beside ``address``."""
        core = label.lower()
        if len(core) < 3 or not any(ch.isalpha() for ch in core):
            return False
        return core in self._everything and core not in self._by_address.get(address.lower(), "")


_LABEL_SPLIT = re.compile(r"\s{2,}|[│┃|·]")


def _label_before(row: str, icon_x: int) -> str:
    """The label an icon at ``icon_x`` sits behind: its cell, back to a column gap."""
    end = _char_at_cell(row, icon_x - 2)
    if end is None:
        return ""
    return _LABEL_SPLIT.split(row[:end + 1])[-1].strip().rstrip("…").strip()


def _window_matches(head: str, tail: str, value: str) -> bool:
    value = value.lower()
    return value[2:].startswith(head.lower()) and value.endswith(tail.lower())


def _char_at_cell(row: str, cell: int) -> int | None:
    x = 0
    for i, ch in enumerate(row):
        width = cell_len(ch)
        if x <= cell < x + width:
            return i
        x += width
    return None


def _token_ending_at(row: str, cell: int) -> str:
    """The hex/``0x``/``…`` run whose last character covers ``cell``."""
    end = _char_at_cell(row, cell)
    if end is None:
        return ""
    start = end
    while start >= 0 and row[start] in _TOKEN_CHARS:
        start -= 1
    token = row[start + 1:end + 1]
    return token[token.rfind("0x"):] if "0x" in token else token


def _class_key(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def test_the_payload_walker_finds_addresses_in_every_shape():
    @dataclasses.dataclass
    class Row:
        who: str

    class Model:
        def __init__(self) -> None:
            self.owner = "0x" + "b" * 40
            self.hook = lambda: "0x" + "9" * 40

    deep: list = ["0x" + "7" * 40]
    for _ in range(5000):
        deep = [deep]

    value = {
        "whole": "0x" + "a" * 40,
        "row": Row("0x" + "d" * 40),
        "model": Model(),
        ("0x" + "e" * 40): 1,
        "prose": ["new contract 0x" + "f" * 40 + " · deployer"],
        "tx": "0x" + "c" * 64,
        "cls": Model,
        "module": types,
        "deep": deep,
    }
    assert _addresses_in(value) == {"0x" + c * 40 for c in "abdef7"}
    assert _hashes_in(value) == {"0x" + "c" * 64}


def test_the_token_reader_finds_what_precedes_an_icon():
    row = "  1  0xabcd…ef01 ⧉  DEGEN ⧉  " + "0x" + "a" * 40 + " ⧉"
    assert _token_ending_at(row, row.index("⧉") - 2) == "0xabcd…ef01"
    # a label-backed icon: the cell before the space is a letter, so no token
    assert _token_ending_at(row, row.index("DEGEN") + 4) == ""
    assert _token_ending_at(row, len(row) - 3) == "0x" + "a" * 40
    wide = "名前 0xabcd…ef01 ⧉"
    assert _token_ending_at(wide, cell_len(wide) - 3) == "0xabcd…ef01"


def test_a_label_is_checked_against_the_record_that_holds_the_address():
    a, b = "0x" + "1" * 40, "0x" + "2" * 40
    index = _LabelIndex({"rows": [{"address": a, "name": "whiskers"}, {"address": b, "name": ""}]})
    assert not index.contradicts("whiskers", a)
    assert index.contradicts("whiskers", b)
    assert not index.contradicts("unheard-of", b), "a label the payload never carries is not evidence"
    assert not index.contradicts("--", b)
    row = "  2     Art Blocks ⧉   ♛1   whiske… ⧉"
    assert _label_before(row, row.index("⧉")) == "Art Blocks"
    assert _label_before(row, row.rindex("⧉")) == "whiske"


def test_the_exemptions_name_real_helper_using_classes():
    import importlib

    for key, reason in EXEMPT.items():
        module_name, _, qualname = key.rpartition(".")
        cls = getattr(importlib.import_module(module_name), qualname)
        assert isinstance(cls, type), key
        assert imports_helper(module_name), (key, "does not import the helper; drop the exemption")
        assert reason.strip(), key


async def _enter(view, app, pilot) -> None:
    if callable(view):
        await view(app, pilot)
    else:
        for key in view:
            await pilot.press(key)


def test_every_case_is_swept_at_its_pins():
    from maxpane_dashboard.screens import curator, surf

    by_name = {case.name: case for case in CASES}
    assert sizes_for(by_name["surf"], "pin") == [
        (surf.SURF_FULL_LAYOUT_COLUMNS, SIZE[1]),
        (surf.SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, surf.SURF_LAUNCHPAD_FULL_LAYOUT_ROWS),
        (surf.SURF_POOL4_FULL_LAYOUT_COLUMNS, surf.SURF_POOL4_FULL_LAYOUT_ROWS),
        (surf.SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, surf.SURF_POOL4_USER_FULL_LAYOUT_ROWS),
        (surf.SURF_SWARM_FULL_LAYOUT_COLUMNS, surf.SURF_SWARM_FULL_LAYOUT_ROWS),
    ]
    assert set(sizes_for(by_name["curator"], "pin")) == {(curator.CURATOR_FULL_LAYOUT_COLUMNS, SIZE[1])}
    for case in CASES:
        if case.name not in ("surf", "curator"):
            assert set(sizes_for(case, "pin")) == {(FULL_LAYOUT_COLUMNS, SIZE[1])}, case.name
    ids = {p.id for p in _size_params()}
    assert {f"{c.name}-{k}" for c in CASES for k in ("wide", "pin")} <= ids


def _continues_as_hash_window(head: str, following: str, hashes) -> bool:
    """True when *head* is really the head of a longer windowed hash rather
    than a bare address.

    ``short_hex``'s own window (``widgets/address._window``) caps its *tail*
    at 6 cells but not its *head*: at a wide enough column a 64-hex
    transaction hash can window to a head of exactly 40 cells, which is
    indistinguishable in shape from a real, un-iconized 40-hex address --
    ``THROUGHPUT``'s tx column hits this at the sweep's 170-column width
    (measured: ``last_tx_hash`` windows to a 40-cell head there). A real
    full address is never immediately continued by an ellipsis and more hex;
    when *following* is exactly that, and the whole ``head…tail`` matches a
    hash the screen was actually given, this is that hash's own window, not
    a naked address -- hashes carry no icon by design, the same exclusion
    the shortened-window check below already makes.
    """
    m = re.match(r"…([0-9a-fA-F]+)(?![0-9a-fA-F])", following)
    return bool(m) and any(_window_matches(head, m.group(1), h) for h in hashes)


def _address_tokens_in_region(rows: list[str], region, hashes=frozenset()) -> list[str]:
    """Whole or shortened address tokens printed inside ``region``'s cells.

    ``hashes`` excuses a token that is really the (possibly partial) window
    of a real transaction hash -- see :func:`_continues_as_hash_window`.
    """
    found: list[str] = []
    for y in range(region.y, min(region.y + region.height, len(rows))):
        row = rows[y]
        start, end = _char_at_cell(row, region.x), _char_at_cell(row, region.x + region.width - 1)
        if start is None:
            continue
        cut = row[start:(len(row) if end is None else end + 1)]
        for m in PROSE_ADDRESS_RE.finditer(cut):
            if _continues_as_hash_window(m.group(0)[2:], cut[m.end():], hashes):
                continue
            found.append(m.group(0))
        for m in SHORT_TOKEN_RE.finditer(cut):
            if any(_window_matches(m.group(1), m.group(2), h) for h in hashes):
                continue
            found.append(m.group(0))
    return found


def test_the_region_scan_finds_addresses_only_inside_the_region():
    from textual.geometry import Region

    row = "0x" + "a" * 40 + " ⧉ | 0xabcd…ef01 ⧉"
    rows = [row, "nothing here"]
    split = row.index("|")
    assert _address_tokens_in_region(rows, Region(0, 0, split, 2)) == ["0x" + "a" * 40]
    assert _address_tokens_in_region(rows, Region(split, 0, len(row) - split, 2)) == ["0xabcd…ef01"]
    assert _address_tokens_in_region(rows, Region(0, 1, len(row), 1)) == []


@pytest.mark.parametrize(("case", "kind"), _size_params())
async def test_every_rendered_address_carries_an_icon_that_copies_it(case, kind):
    served = case.payload()
    in_payload = _addresses_in(served)
    hashes = _hashes_in(served)
    labels = _LabelIndex(served)
    seeded = {a.lower() for a in case.seeded}
    problems: list[tuple] = []
    if not seeded <= in_payload:
        problems.append(("a seeded address is not in the payload", sorted(seeded - in_payload)))

    copied_somewhere: set[str] = set()
    mounted: dict[str, str] = {}
    covered: set[str] = set()

    for view, size in zip(case.views, sizes_for(case, kind)):
        label = f"{view_name(view)}@{size[0]}x{size[1]}"
        app = case.build()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await _enter(view, app, pilot)
            await pilot.pause()
            await pilot.pause()
            targets = icon_targets(app)
            rows = _rows(app)
            for widget in app.screen.walk_children(with_self=True):
                key = _class_key(type(widget))
                if imports_helper(type(widget).__module__):
                    mounted.setdefault(key, label)
                if key in EXEMPT:
                    # An exemption says the widget renders no address; hold it to that.
                    for token in _address_tokens_in_region(rows, widget.region, hashes):
                        problems.append((label, key, token, "address rendered inside an EXEMPT widget"))

            if case.address_free:
                if targets:
                    problems.append((label, "icon on an address-free dashboard", targets[:3]))
                for y, row in enumerate(rows):
                    for m in list(PROSE_ADDRESS_RE.finditer(row)) + list(SHORT_TOKEN_RE.finditer(row)):
                        problems.append((label, y, m.group(0), "address on an address-free dashboard"))
                continue

            by_cell = {(x, y): a for x, y, a in targets}
            for x, y, address in targets:
                if address is None or not ADDRESS_RE.fullmatch(address):
                    problems.append((label, x, y, "icon whose action is not a well-formed copy"))
                    continue
                if address.lower() not in in_payload:
                    problems.append((label, x, y, address, "icon copies an address the payload does not hold"))
                token = _token_ending_at(rows[y], x - 2)
                if ADDRESS_RE.fullmatch(token):
                    if token.lower() != address.lower():
                        problems.append((label, x, y, token, address, "icon copies a different address than the one before it"))
                elif (window := _WINDOW_RE.fullmatch(token)) is not None:
                    if not _window_matches(window.group(1), window.group(2), address):
                        problems.append((label, x, y, token, address, "icon copies a different address than the window before it"))
                else:
                    shown = _label_before(rows[y], x)
                    if labels.contradicts(shown, address):
                        problems.append((label, x, y, shown, address, "label-backed icon copies an address whose record does not carry that label"))
                try:
                    widget, _ = app.screen.get_widget_at(x, y)
                except Exception:
                    problems.append((label, x, y, "no widget under an icon"))
                    continue
                for node in widget.ancestors_with_self:
                    covered.add(_class_key(type(node)))
            copied_somewhere.update(a.lower() for _, _, a in targets if a)

            for y, row in enumerate(rows):
                # every whole address printed on screen has its own icon right after it
                for m in PROSE_ADDRESS_RE.finditer(row):
                    icon_x = cell_len(row[:m.end()]) + 1
                    if (by_cell.get((icon_x, y)) or "").lower() == m.group(0).lower():
                        continue
                    if _continues_as_hash_window(m.group(0)[2:], row[m.end():], hashes):
                        continue  # a windowed hash's own head, not a bare address
                    problems.append((label, y, m.group(0), "full address without its icon"))
                # every shortened window of an address the screen was given has one too
                for m in SHORT_TOKEN_RE.finditer(row):
                    head, tail = m.group(1), m.group(2)
                    candidates = {a for a in in_payload if _window_matches(head, tail, a)}
                    if not candidates:
                        continue
                    copied = (by_cell.get((cell_len(row[:m.end()]) + 1, y)) or "").lower()
                    if copied in candidates:
                        continue
                    if not copied and any(_window_matches(head, tail, h) for h in hashes):
                        continue  # the same window is also a transaction hash's; hashes carry no icon
                    problems.append((label, y, m.group(0), "shortened address without its icon"))

    if case.address_free:
        if mounted:
            problems.append(("helper-using widgets mounted on an address-free dashboard", sorted(mounted)))
    elif kind == "wide":
        # Presence is a property of the wide sweep. At a pin a panel may shed a
        # whole window-and-icon unit behind an ellipsis (surf's SIGNALS row
        # reads ``new contract…`` at 143), which is honest; what every size
        # must guarantee is the per-row checks above: nothing printed without
        # its icon, and no icon copying the wrong address.
        missing = seeded - copied_somewhere
        if missing:
            problems.append(("seeded addresses never got an icon in any view", sorted(missing)))
        silent = sorted(k for k in mounted if k not in covered and k not in EXEMPT)
        if silent:
            problems.append(("helper-using widgets mounted but never produced an icon", silent))

    assert not problems, (case.name, problems)
