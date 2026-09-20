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
6. **Every address is a link to its chain's explorer** (PRD §7 E7): the last
   cell of the token shown before each icon carries an ``@click`` open action
   **and** an OSC 8 ``link`` for the address the icon copies, on an explorer in
   the case's allowed set (``SweepCase.explorers``), with the URL
   ``address_url`` builds for it; and every link on screen names an address or
   transaction hash the payload holds, on an allowed explorer, with a URL that
   matches its action. A case with no explorer (a chain ``widgets/explorer.py``
   does not allowlist) gets the opposite: no link anywhere.

Each case is swept at :data:`SIZE` (170 columns) and again at each view's own
layout pin, plus any ``extra_sizes`` it names (:func:`sizes_for`). Questions 1,
2 and 5 are asked at every size; 3 and 4 only at 170, where every body has room
for every unit it can shed at a pin.

An address-free case gets the opposite: no icon, no whole or shortened address,
and no helper-using widget mounted at all.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import re
import types

import pytest
from rich.cells import cell_len

from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.widgets.address import ADDRESS_RE, PROSE_ADDRESS_RE
from maxpane_dashboard.widgets.explorer import parse_open_action, url_for
from tests.address_sweep.case import SweepCase, view_name
from tests.address_sweep.imports import HELPER, _is_module, imports_helper, module_imports
from tests.address_sweep.registry import CASES
from tests.widgets.address_probe import icon_targets, link_targets

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
#: A transaction hash: windowed through ``short_hex``/``hash_text`` with no icon, by design.
HASH_RE = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{64}(?![0-9a-fA-F])")
_TOKEN_CHARS = frozenset("0123456789abcdefABCDEFx…")

#: Widget classes that import the helper yet never produce an icon, each with
#: the reason. A class, never a module or package.
EXEMPT: dict[str, str] = {
    "maxpane_dashboard.widgets.surf.feed.SurfFeedToggle":
        "a thread's expand/collapse toggle; feed.py imports only is_copy_click /"
        " is_explorer_click for it",
    "maxpane_dashboard.widgets.surf.launchpad.SurfCurveFlow":
        "swap, trader and ETH-owed totals only; no address in its contract",
    "maxpane_dashboard.widgets.surf.launchpad.SurfBurnPipeline":
        "burn pipeline status and amounts only; no address in its contract",
    "maxpane_dashboard.widgets.surf.swarm_throughput.SurfSwarmThroughput":
        "quotes each agent's last score transaction hash through hash_text (a"
        " short_hex window, linked to its row's chain); a hash, never an"
        " address, so it carries no icon by design",
    "maxpane_dashboard.widgets.surf.swarm_field.SurfSwarmField":
        "a dispatch note's embedded address (address_prose) is the only icon"
        " this panel can ever show, and it lives in the ``note`` column that"
        " only paints at the ``full`` tier (budget >= FULL_WIDTH = 117 cells)."
        " Re-measured 2026-09-17 (swarm column-balance change, QUEUE/"
        " THROUGHPUT capped at a fixed max-width rather than sharing an"
        " unbounded 1fr with FIELD/SHIPPED): FIELD is now the ONLY unbounded"
        " 1fr in its row, so it gets column-for-column growth above QUEUE's"
        " own cap instead of half of it, and the full tier's own threshold"
        " (measured, not derived) fell from 250 to exactly 170 -- the wide"
        " sweep's own SIZE, not past it. This panel's exemption therefore no"
        " longer rests on the note column being unreachable inside the"
        " sweep: at SIZE=(170, 60) FIELD genuinely reaches ``full`` and would"
        " paint an icon if the seeded payload put an address in a dispatch"
        " note. It does not (the swarm fixture's own two notes are"
        " ``\"waiting on review\"`` and ``None``, guarded by its own test:"
        " test_the_swarm_field_exemption_s_own_assumption_is_still_true_of_"
        " the_fixture), so the exemption still holds on the facts, not on"
        " unreachability -- and this comment says so rather than repeating"
        " the now-false claim that no swept render could ever show one."
        " This body's own layout pin (116, re-swept 2026-09-17 fix round 1"
        " on a silent overflow the column-balance change's own 95 had been"
        " certifying) is still well under 170, so FIELD stays out of"
        " ``full`` tier there regardless.",
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


def _link_at(app, x: int, y: int) -> tuple[tuple | None, str | None]:
    """``(parsed open action, OSC 8 url)`` at cell ``(x, y)``, read the way
    :func:`icon_targets` reads an icon: off ``screen.get_style_at``, the style
    a click would hit -- one reader for the icon and the token before it."""
    style = app.screen.get_style_at(x, y)
    meta = style.meta or {}
    return parse_open_action(meta.get("@click")), style.link or None


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


def test_the_swarm_field_exemption_s_own_assumption_is_still_true_of_the_fixture():
    """``SurfSwarmField``'s own ``EXEMPT`` entry no longer rests on the note
    column being unreachable (fix round 1, 2026-09-17, on the column-balance
    change's own re-sweep: THE FIELD's own ``full``-tier threshold, 170, sits
    *inside* this file's own 170-column ``SIZE`` sweep now, not past it) --
    it rests on a narrower, checkable fact instead: the seeded swarm fixture
    puts no address in any ``dispatch_note``. That fact was true when the
    comment was written and had **no test of its own** -- a future fixture
    edit (a new seeded row, a note rewritten to include an example address)
    could make the comment's own claim false while this file keeps reporting
    green, exactly the "an EXEMPT widget prints no address" guarantee E5
    exists to protect elsewhere in this file, here left to a sentence in a
    docstring instead of an assertion.

    This is that assertion: every ``dispatch_note`` in the fixture the sweep
    actually mounts (``tests.address_sweep.builders._surf_payload``) is
    checked against both address patterns this file already uses
    (:data:`ADDRESS_RE`, whole; :data:`PROSE_ADDRESS_RE`, embedded). If this
    ever reddens, the fix is not to weaken this test -- it is to move
    ``SurfSwarmField`` off ``EXEMPT`` and let E4 require it to actually
    produce an icon, because the premise that panel's exemption depends on
    stopped holding.
    """
    from tests.address_sweep.builders import _surf_payload

    payload = _surf_payload()
    rows = payload.get("swarm_field_rows") or []
    assert rows, "the swarm fixture seeded no field rows -- this test has nothing to check"
    for row in rows:
        note = row.get("dispatch_note")
        if not isinstance(note, str):
            continue
        assert not ADDRESS_RE.search(note), (
            row.get("job_id"), note,
            "a whole address is now seeded into a dispatch note -- "
            "SurfSwarmField's own EXEMPT reason no longer holds",
        )
        assert not PROSE_ADDRESS_RE.search(note), (
            row.get("job_id"), note,
            "an embedded address is now seeded into a dispatch note -- "
            "SurfSwarmField's own EXEMPT reason no longer holds",
        )


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
    """True when *head*'s digits and *following*'s continuation match some
    hash's own window -- shape and value only, **not sufficient on its own**
    to excuse anything (see :func:`_hash_only_module`, which supplies the
    other half).

    ``short_hex``'s own window (``widgets/address._window``) caps its *tail*
    at 6 cells but not its *head*: at a wide enough column a 64-hex
    transaction hash can window to a head of exactly 40 cells, which is
    indistinguishable in shape from a real, un-iconized 40-hex address.
    ``THROUGHPUT`` used to hit this at wide enough terminals (measured at
    the sweep's own 170-column width before 2026-09-17) -- it no longer can,
    now that ``swarm_throughput._MAX_TX_COLS`` caps the width it ever hands
    ``short_hex`` at 12 cells (a 5-cell head at most, per ``_window``'s own
    arithmetic), so this specific collision is retired -- see
    :func:`test_the_former_throughput_hash_collision_is_now_structurally_impossible`.
    The general point this docstring makes stands regardless: ``_window``
    itself still carries no head cap, so a *future* widget that hands it an
    uncapped width can still reproduce the shape this function exists to
    catch, and the provenance check below is what closes it when one does.

    Fix round 1 (task-13-review.md, Finding 1, High): this predicate alone
    matches **any** hash anywhere in the whole served payload, with no check
    on which widget painted the candidate text. The review's own adversarial
    construction proves that is not enough: a real hash and a hypothetical
    bare, un-iconized address can share every digit (``"0x" + "2"*64`` and
    ``"0x" + "2"*40``), so the printed text is byte-identical either way --
    no amount of value-matching, however width-aware, can tell them apart
    from the string alone. Both call sites below therefore require this
    predicate to be true **and** :func:`_hash_only_module` to be true of the
    widget that actually painted the position -- provenance, not value,
    closes the hole; this function keeps doing only the shape/value half of
    the job its name always claimed.
    """
    m = re.match(r"…([0-9a-fA-F]+)(?![0-9a-fA-F])", following)
    return bool(m) and any(_window_matches(head, m.group(1), h) for h in hashes)


#: The two entry points in ``widgets/address`` that ever attach a copy icon
#: (``address_text``/``address_prose`` -- see that module's own docstring).
#: A module reaching either one, directly or transitively, is capable of
#: printing a real, icon-bearing address; a module reaching neither is not.
_ICON_PRODUCING_HELPERS = frozenset({f"{HELPER}.address_text", f"{HELPER}.address_prose"})


def _reaches_icon_machinery(module_name: str) -> bool:
    """True when *module_name* can reach ``address_text``/``address_prose``
    through **any chain** of imports, followed to a fixed point.

    Fix round 2 (task-13-review.md carry-over): a depth-1 check (only
    *module_name*'s own imports) is exactly the mistake
    ``tests/widgets/test_surf_widget_contract.py::test_the_allowed_
    analytics_modules_are_themselves_pure`` already exists to catch one
    layer over, for the identical reason -- that test's own docstring: "a
    depth-1 version of this test was green while ``analytics/surf_feed``
    imported ``analytics/surf_signals``, which reaches ``data`` in one
    further hop." Here the one-hop-removed case is real, not hypothetical:
    ``widgets/surf/feed.py`` and ``widgets/surf/signals.py`` never import
    ``address_text``/``address_prose`` directly -- they import
    ``widgets/surf/_icons.py`` (``mark_addresses``/``link_prose``/
    ``link_in_order``), and *that* module imports ``address_text`` on its
    own line. Both widgets genuinely paint iconized addresses; a depth-1
    version of :func:`_hash_only_module` classified both as hash-only.

    The walk follows this repo's own precedent's exact shape (a
    ``queue``/``seen`` fixed-point BFS over ``module_imports``, the same
    AST-resolved import reader ``imports_helper`` itself uses), restricted
    to ``maxpane_dashboard.*`` names -- the icon machinery cannot hide in
    ``rich``/``textual``/stdlib, and a name is only followed once
    :func:`tests.address_sweep.imports._is_module` (the same guard
    ``widget_modules_of`` already uses for the identical "not every ``X.Y``
    is a module" reason) confirms it resolves to one.

    **A package root is never followed** (checked here, not inside
    ``_is_module``, because ``widget_modules_of`` deliberately *does* walk
    into a package for its own, different question). ``from
    maxpane_dashboard.widgets.surf import <sibling>`` -- the ordinary
    sibling-import shape half this package's modules used until Branch 3
    moved the row-fit machinery to ``widgets.rowfit`` -- resolves to *two*
    names: the specific submodule (the real edge) and the bare package
    ``...surf`` itself (an artifact of the AST shape, not a real one).
    ``widgets/surf/__init__.py`` re-exports this package's
    entire public widget surface by design (its own docstring: "the
    package root is the import surface the screen and its tests use"), so
    following that second name made *every* surf widget that imports any
    sibling by this common pattern reach *every* icon-producing widget
    anywhere in the package -- caught here because it flipped
    ``swarm_throughput`` (imports only ``short_hex``, and only reaches
    ``rowfit``/``_fmt``/``_pool4``/``_swarm_chain``, none of which import
    the icon machinery either) to "not hash-only" the moment the walk went
    through the package init instead of stopping at the plain modules the
    import actually names.
    """
    seen: set[str] = set()
    queue = [module_name]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        names = module_imports(name)
        if names & _ICON_PRODUCING_HELPERS:
            return True
        for candidate in names:
            if candidate in seen or not candidate.startswith("maxpane_dashboard."):
                continue
            if not _is_module(candidate):
                continue
            spec = importlib.util.find_spec(candidate)
            if spec is not None and spec.submodule_search_locations is not None:
                continue  # a package root, not a real call-graph edge -- see above
            queue.append(candidate)
    return False


def _hash_only_module(module_name: str | None) -> bool:
    """True when *module_name* can only ever print a hash's own window --
    never a real, icon-bearing address -- and so is safe provenance for
    :func:`_continues_as_hash_window`'s excuse.

    It must import the address helper at all (``imports_helper``, the same
    AST-resolved check ``EXEMPT``'s own agreement test uses) **and** never
    reach ``address_text``/``address_prose`` through any chain of imports
    (:func:`_reaches_icon_machinery`, transitive -- fix round 2; a direct-
    import-only version of this check missed ``feed.py``/``signals.py``,
    which reach the icon machinery through ``widgets/surf/_icons.py``). A
    module in this shape cannot construct a copy icon at all: every
    ``0x``-shaped run it paints is provably the output of
    ``short_hex``/``short_address`` windowing some value it was handed, not
    a bare address. A module that never touches the helper at all is not
    "hash only" either -- there is nothing here to excuse in the first
    place, only widgets already in the icon business get the benefit of the
    doubt.
    """
    if not module_name or not imports_helper(module_name):
        return False
    return not _reaches_icon_machinery(module_name)


def _shortened_window_hash_excuse(head: str, tail: str, hashes, painter: str | None) -> bool:
    """True when a shortened window with no matching copy icon is excused as
    a transaction hash's own window -- **provenance and value**, the
    shortened-window counterpart of the whole-address branch's
    :func:`_continues_as_hash_window` + :func:`_hash_only_module` pairing.

    F3: before this function existed, the main sweep's shortened-window
    branch excused on value alone -- ``any(_window_matches(head, tail, h) for
    h in hashes)``, with no check on which widget painted the token at all.
    A real, un-iconized address whose digits happened to match some
    unrelated hash's own window *anywhere in the served payload* -- not
    necessarily the same widget, not necessarily related -- was silently
    excused, exactly the defect class the whole-address branch and the
    region scanner (``_address_tokens_in_region``) both had before their own
    fix. Requiring :func:`_hash_only_module` of the *painting* widget closes
    it the same way: a widget that can never construct a real, icon-bearing
    address gets the benefit of the doubt; one that can, never does, no
    matter what its digits happen to match elsewhere in the payload.
    """
    return _hash_only_module(painter) and any(_window_matches(head, tail, h) for h in hashes)


def _widget_module_at(app, x: int, y: int) -> str | None:
    """The module of the widget actually responsible for cell (*x*, *y*)
    under the address-icon rules, or ``None`` when there is none or it
    cannot be resolved.

    ``get_widget_at`` (the same lookup the icon-coverage check above already
    uses) returns the innermost leaf -- a plain Textual ``Static`` or
    ``DataTable`` cell whose own module is Textual's, never this
    application's, so checking it directly would make :func:`_hash_only_module`
    return ``False`` (not hash-only) for *every* position on screen, since
    Textual's own widgets never import the address helper at all. Walking
    ``ancestors_with_self`` to the first ancestor that imports the helper at
    all names the widget that is actually part of the address-icon system
    (``SurfSwarmThroughput``, ``SurfSwarmShipped``, ...); further ancestors
    are container chrome (``Vertical``, ``Horizontal``, the screen itself)
    that would falsely read as address-incapable for the same reason.
    """
    try:
        widget, _ = app.screen.get_widget_at(x, y)
    except Exception:
        return None
    for node in widget.ancestors_with_self:
        module = type(node).__module__
        if imports_helper(module):
            return module
    return None


def _address_tokens_in_region(
    rows: list[str], region, hashes=frozenset(), *, hash_only: bool = False,
) -> list[str]:
    """Whole or shortened address tokens printed inside ``region``'s cells.

    ``hash_only`` (the *region*'s own widget, per :func:`_hash_only_module`)
    gates whether ``hashes`` may excuse a token at all: a region belonging
    to any widget capable of printing a real address gets no excuse, no
    matter what its digits happen to match elsewhere in the payload (Finding
    1, task-13-review.md -- narrowed from a bare ``hashes`` check in fix
    round 1).
    """
    found: list[str] = []
    for y in range(region.y, min(region.y + region.height, len(rows))):
        row = rows[y]
        start, end = _char_at_cell(row, region.x), _char_at_cell(row, region.x + region.width - 1)
        if start is None:
            continue
        cut = row[start:(len(row) if end is None else end + 1)]
        for m in PROSE_ADDRESS_RE.finditer(cut):
            if hash_only and _continues_as_hash_window(m.group(0)[2:], cut[m.end():], hashes):
                continue
            found.append(m.group(0))
        for m in SHORT_TOKEN_RE.finditer(cut):
            if hash_only and any(_window_matches(m.group(1), m.group(2), h) for h in hashes):
                continue
            found.append(m.group(0))
    return found


def test_a_hash_only_module_is_recognized_by_which_icon_helpers_it_imports():
    """Fix round 1 (task-13-review.md, Finding 1, High): the provenance half
    of the fix. A widget class's own module either can or cannot construct a
    copy icon, decided from its imports alone -- see :func:`_hash_only_module`
    (added in this fix round; this assertion fails against 855d5d6, which has
    no such function).
    """
    # Only imports short_hex/MIN_SHORT_COLS: structurally cannot ever print
    # a real, icon-bearing address -- the legitimate case the exclusion
    # exists for.
    assert _hash_only_module("maxpane_dashboard.widgets.surf.swarm_throughput")
    # Imports address_text (and short_hex): capable of the real bug this
    # finding is about, so never excused regardless of what its own printed
    # digits happen to match elsewhere in the payload.
    assert not _hash_only_module("maxpane_dashboard.widgets.surf.swarm_shipped")
    # Imports address_prose, the other icon-producing entry point: also not
    # hash-only, proving the check is not just checking for address_text.
    assert not _hash_only_module("maxpane_dashboard.widgets.surf.swarm_field")
    # Never touches the address helper at all: nothing to excuse here either.
    assert not _hash_only_module("maxpane_dashboard.widgets.surf.swarm_queue")
    assert not _hash_only_module(None)


def test_a_module_reaching_icons_through_an_indirection_is_not_hash_only():
    """Fix round 2 (coordinator carry-over on task-13-review.md Finding 1):
    real modules, not the synthetic swarm names above.

    ``widgets/surf/feed.py`` and ``widgets/surf/signals.py`` never import
    ``address_text``/``address_prose`` directly -- both reach them through
    ``widgets/surf/_icons.py`` (``mark_addresses``/``link_prose``/
    ``link_in_order``), which imports ``address_text`` on its own line --
    and both genuinely paint iconized addresses (``SurfFeed``'s announce
    posts, ``SurfSignals``' deploy detail). A depth-1 check of direct
    imports alone classified both as hash-only, which would excuse a real,
    un-iconized address/hash collision attributed to either widget's own
    text. This assertion fails against fix round 1 (`1c279ea`), where
    ``_hash_only_module`` checked only direct imports.
    """
    # Reach the icon machinery one hop further out, through _icons.py:
    # never hash-only, no matter how few names they import directly.
    assert not _hash_only_module("maxpane_dashboard.widgets.surf.feed")
    assert not _hash_only_module("maxpane_dashboard.widgets.surf.signals")
    # The indirection itself: _icons.py imports address_text directly, so
    # it is not hash-only even at depth 0.
    assert not _hash_only_module("maxpane_dashboard.widgets.surf._icons")
    # The genuinely hash-only case must still hold once the walk is
    # transitive -- the fix must not trade a false negative for a false
    # positive.
    assert _hash_only_module("maxpane_dashboard.widgets.surf.swarm_throughput")


def test_the_region_scan_only_excuses_a_hash_window_for_a_hash_only_widget():
    """Finding 1 (task-13-review.md, High), reproduced with the review's own
    adversarial construction and closed: a real hash and a hypothetical bare
    address can share every digit (``"0x" + "2"*64`` / ``"0x" + "2"*40``), so
    the printed text ``0x<head>…<tail>`` is byte-identical whichever one
    produced it -- no value-only check can tell them apart. Only knowing
    which widget painted it can: with ``hash_only=True`` (a widget that can
    only ever window a hash) the run is excused; with ``hash_only=False``
    (the correct answer for any widget capable of a real address) it is
    reported, exactly as an un-iconized address must be.

    Fails against 855d5d6: ``_address_tokens_in_region`` there takes no
    ``hash_only`` keyword at all -- ``hashes`` alone decided it, so this
    exact adversarial row was excused unconditionally (Finding 1's whole
    point). This call raises ``TypeError`` until fix round 1 adds the
    parameter.
    """
    from textual.geometry import Region

    head = "2" * 40
    row = f"0x{head}…222222 padding"
    rows = [row]
    hashes = {"0x" + "2" * 64}
    region = Region(0, 0, len(row), 1)

    assert _address_tokens_in_region(rows, region, hashes, hash_only=True) == []
    assert _address_tokens_in_region(rows, region, hashes, hash_only=False) == [
        f"0x{head}", f"0x{head}…222222",
    ]


async def test_the_former_throughput_hash_collision_is_now_structurally_impossible():
    """RETIRED as a live-collision reproduction, 2026-09-17 (swarm
    column-balance change) -- reported rather than silently dropped, per
    the task that made the change: the swarm body's owner asked to cap
    THROUGHPUT's tx-hash column at 12 cells
    (``swarm_throughput._MAX_TX_COLS``), and that cap is a *ceiling* on the
    width :func:`swarm_throughput._agent_lines` ever hands ``short_hex``,
    not merely a floor beside :data:`swarm_throughput._MIN_TX_COLS`. A
    12-cell window's own arithmetic (``widgets/address._window``: ``budget
    = width - 3``, ``tail = min(6, budget // 2)``, ``head = budget - tail``)
    tops out at a 5-cell head (``budget=9, tail=4, head=5``) -- nowhere near
    the 40-cell head a bare address's own shape needs to collide with. The
    test this replaced (``test_the_full_address_scan_resolves_the_real_
    collision_to_its_widget``) re-measured the one outer width that
    produced a 40-cell head three times across two days (170 -> 166 -> 153
    -> 166) as the swarm body's own layout changed around it; this fourth
    change does not move that number, it deletes the head budget the
    collision needed to exist at any width, which is why this test proves
    a structural bound rather than re-sweeping for a fourth number.

    Proven two ways, not asserted from the constant alone:

    1. **Structurally.** :func:`_window`'s own head formula is monotonic in
       ``width``, so the widest head any call this panel makes can ever
       produce is bounded by its widest legal argument
       (:data:`swarm_throughput._MAX_TX_COLS`). A 5-cell head can never
       equal a 40-character run, so the collision the retired test
       reproduced cannot exist at *any* terminal width, not merely the ones
       swept below.
    2. **Empirically**, across a band that comfortably straddles both this
       file's own 170-column ``SIZE`` and every width the retired test ever
       measured (150-190): the collision regex never matches, at any width
       in that band, on the same live-rendered swarm body the retired test
       used.

    The provenance machinery this test used to exercise live
    (:func:`_widget_module_at`, :func:`_hash_only_module`) is unaffected by
    the cap and stays covered by the synthetic constructions above
    (``test_a_hash_only_module_is_recognized_by_which_icon_helpers_it_
    imports``, ``test_a_module_reaching_icons_through_an_indirection_is_
    not_hash_only``, ``test_the_region_scan_only_excuses_a_hash_window_
    for_a_hash_only_widget``) -- none of those construct their collision by
    rendering THROUGHPUT at a specific width, so none of them lost their
    subject when this one did.
    """
    from maxpane_dashboard.widgets.address import _window
    from maxpane_dashboard.widgets.surf import swarm_throughput as T
    from tests.address_sweep.builders import _surf_app

    # 1. Structural bound: the widest head this panel's own cap can ever
    # produce, independent of any render.
    widest_window = _window("0x" + "2" * 64, T._MAX_TX_COLS)
    head = widest_window[2:widest_window.index("…")]
    assert len(head) < 40, (
        "the tx-hash window's own head reached 40 cells at the panel's own "
        "MAX_TX_COLS ceiling -- the structural argument this test makes no "
        "longer holds and the collision may be reachable again"
    )

    # 2. Empirical confirmation on the live body, across the band the
    # retired test's own three re-sweeps all fell inside. A fresh app per
    # width, on every other sweep's own precedent in this file
    # (``tests/screens/test_surf_swarm_layout.py``'s ``_render``) -- an
    # ``App`` is not re-run once its own ``run_test`` context has exited.
    collision = re.compile(r"0x2{40}…2{6}")
    for width in range(150, 191, 5):
        app = _surf_app()
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            await pilot.pause()
            rows = _rows(app)
            hits = [m for row in rows for m in collision.finditer(row)]
            assert not hits, (
                width, "the retired collision rendered again -- the 12-cell "
                "cap no longer bounds THROUGHPUT's hash window as this test "
                "assumes"
            )


def test_the_shortened_window_hash_excuse_requires_a_hash_only_painter():
    """F3 (docs/surf_swarm_followups.md): the main sweep's shortened-window
    branch excused a missing icon on value alone -- ``any(_window_matches(
    head, tail, h) for h in hashes)``, with no check on which widget painted
    the token. :func:`_shortened_window_hash_excuse` is the fix, and this
    sweeps every head/tail split :func:`_window` can produce for a 40-hex
    address (widths 11..41; below 11 nothing truncates, at 42 the address no
    longer truncates at all) rather than checking one lucky split, per the
    review note that a values-agree-with-themselves test at a single width
    can hide a shape that only breaks at another.

    Fails against the pre-fix shape: temporarily replacing this function's
    body with ``return any(_window_matches(head, tail, h) for h in hashes)``
    (ignoring ``painter`` entirely, the exact code this replaced) turns every
    assertion in the adversarial group red, at every width in the sweep --
    the value-only check excuses the real-address painter exactly as
    readily as the hash-only one. Restoring the body turns it green again.
    """
    from maxpane_dashboard.widgets.address import MIN_SHORT_COLS, _window

    address = "0x" + "5" * 40
    hashes = {"0x" + "5" * 64}  # shares every digit with `address`'s own window, at any split
    non_hash_only = "maxpane_dashboard.widgets.surf.swarm_shipped"
    hash_only = "maxpane_dashboard.widgets.surf.swarm_throughput"
    # the anchors this test leans on -- pinned again so a change to either
    # widget's own imports reddens here, not silently inside the sweep below
    assert not _hash_only_module(non_hash_only)
    assert _hash_only_module(hash_only)

    for width in range(MIN_SHORT_COLS, 42):
        window = _window(address, width)
        m = _WINDOW_RE.fullmatch(window)
        assert m, (width, window, "expected a truncated window at this width")
        head, tail = m.group(1), m.group(2)
        # legitimate: a hash-only widget's own hash window, sharing every
        # digit with an address elsewhere -- still excused, or the sweep
        # starts crying wolf on every real hash render.
        assert _shortened_window_hash_excuse(head, tail, hashes, hash_only), width
        # adversarial: a widget capable of a real, icon-bearing address --
        # never excused, no matter how many digits its shortened window
        # happens to share with a hash elsewhere in the payload.
        assert not _shortened_window_hash_excuse(head, tail, hashes, non_hash_only), width
        # no painter resolved at all (e.g. no widget found at that
        # coordinate): nothing here to give the benefit of the doubt to.
        assert not _shortened_window_hash_excuse(head, tail, hashes, None), width


async def test_the_main_sweep_catches_a_shortened_address_the_old_value_only_excuse_missed():
    """F3, end to end and adversarial, reproducing the exact hole named in
    docs/surf_swarm_followups.md: a real, un-iconized address, painted by a
    widget whose own module *can* build a real, icon-bearing address
    (``tests/screens/_f3_address_probe.BareShortenedAddress`` imports
    ``address_text`` directly, the same provenance a real production widget
    such as ``SurfSwarmShipped`` has), shortened to a window that shares
    every digit with an unrelated hash sitting elsewhere in the served
    payload -- never rendered anywhere on screen at all, exactly "elsewhere
    in the payload" rather than "elsewhere on screen".

    This reproduces the main sweep loop's own shortened-window scan
    (``SHORT_TOKEN_RE`` over each rendered row, the same candidate/copied
    check, the same ``_widget_module_at`` + :func:`_shortened_window_hash_excuse`
    pairing at the same call shape) against a real, running app -- so it
    also proves the *wiring* (``_widget_module_at`` resolving the real
    painter at the real token position), not merely the predicate in
    isolation the test above already covers.

    Fails against the pre-fix shape (see the mutation note on
    :func:`_shortened_window_hash_excuse` above): with ``painter`` ignored,
    the loop below finds the window excused by value alone and reports no
    problem, so the final ``assert problems`` here goes red. Passes once the
    provenance check is restored.
    """
    from textual.app import App

    from maxpane_dashboard.widgets.address import MIN_SHORT_COLS, _window
    from tests.screens._f3_address_probe import BareShortenedAddress

    address = "0x" + "5" * 40
    collide_hash = "0x" + "5" * 64  # shares every digit with `address`'s own window
    shown = _window(address, MIN_SHORT_COLS)
    served = {"address": address, "unrelated_hash": collide_hash}

    class _Harness(App):
        def compose(self):
            yield BareShortenedAddress(shown)

    app = _Harness()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        rows = _rows(app)
        in_payload = _addresses_in(served)
        hashes = _hashes_in(served)
        by_cell = {(x, y): a for x, y, a in icon_targets(app)}

        problems: list[tuple] = []
        for y, row in enumerate(rows):
            for m in SHORT_TOKEN_RE.finditer(row):
                head, tail = m.group(1), m.group(2)
                candidates = {a for a in in_payload if _window_matches(head, tail, a)}
                if not candidates:
                    continue
                copied = (by_cell.get((cell_len(row[:m.end()]) + 1, y)) or "").lower()
                if copied in candidates:
                    continue
                token_x = cell_len(row[:m.start()])
                painter = _widget_module_at(app, token_x, y)
                if not copied and _shortened_window_hash_excuse(head, tail, hashes, painter):
                    continue
                problems.append((y, m.group(0)))

        assert problems, (
            "the shortened-window branch excused a real, un-iconized address "
            "painted by a widget capable of building one, because its digits "
            "matched an unrelated hash elsewhere in the payload -- this is "
            "exactly the value-only hole F3 describes"
        )


def test_the_region_scan_finds_addresses_only_inside_the_region():
    from textual.geometry import Region

    row = "0x" + "a" * 40 + " ⧉ | 0xabcd…ef01 ⧉"
    rows = [row, "nothing here"]
    split = row.index("|")
    assert _address_tokens_in_region(rows, Region(0, 0, split, 2)) == ["0x" + "a" * 40]
    assert _address_tokens_in_region(rows, Region(split, 0, len(row) - split, 2)) == ["0xabcd…ef01"]
    assert _address_tokens_in_region(rows, Region(0, 1, len(row), 1)) == []


@pytest.mark.parametrize(("case", "kind"), _size_params())
async def test_every_rendered_address_carries_an_icon_that_copies_it_and_a_link_that_opens_it(case, kind):
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
            links = link_targets(app)
            rows = _rows(app)
            allowed = {e.name: e for e in case.explorers}
            for widget in app.screen.walk_children(with_self=True):
                key = _class_key(type(widget))
                if imports_helper(type(widget).__module__):
                    mounted.setdefault(key, label)
                if key in EXEMPT:
                    # An exemption says the widget renders no address; hold it to that.
                    for token in _address_tokens_in_region(
                        rows, widget.region, hashes,
                        hash_only=_hash_only_module(type(widget).__module__),
                    ):
                        problems.append((label, key, token, "address rendered inside an EXEMPT widget"))

            if case.address_free:
                if targets:
                    problems.append((label, "icon on an address-free dashboard", targets[:3]))
                if links:
                    problems.append((label, "link on an address-free dashboard", links[:3]))
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
                # E7: the last cell of the shown token (right before the
                # separating space) links to the same address, on an allowed explorer.
                parsed, url = _link_at(app, x - 2, y)
                if not allowed:
                    if parsed is not None or url is not None:
                        problems.append((label, x, y, address, "link on a dashboard with no explorer"))
                elif parsed is None or url is None:
                    problems.append((label, x, y, address, "address without a link"))
                else:
                    explorer, kind, value = parsed
                    if kind != "address" or value.lower() != address.lower():
                        problems.append((label, x, y, value, address, "link opens a different value than the icon copies"))
                    elif explorer.name not in allowed:
                        problems.append((label, x, y, explorer.name, "link on the wrong explorer"))
                    elif url != url_for(explorer, kind, value):
                        problems.append((label, x, y, url, "link url does not name the linked address"))
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

            # E7: every link on screen names an address or a transaction hash
            # the payload holds, on an allowed explorer, and its URL is the one
            # its action rebuilds -- never a link to anything else.
            seen_links: set[tuple] = set()
            for x, y, name, kind, value, url in links:
                if name is None or kind is None or value is None:
                    problems.append((label, x, y, url, "link without a well-formed open action"))
                    continue
                if (name, kind, value, url) in seen_links:
                    continue  # one report per span, not per cell
                seen_links.add((name, kind, value, url))
                held = hashes if kind == "tx" else in_payload
                if value.lower() not in held:
                    problems.append((label, x, y, kind, value, "link to a value the payload does not hold"))
                if name not in allowed:
                    problems.append((label, x, y, name, "link on the wrong explorer"))
                elif url != url_for(allowed[name], kind, value):
                    problems.append((label, x, y, url, "link url does not match its action"))

            for y, row in enumerate(rows):
                # every whole address printed on screen has its own icon right after it
                for m in PROSE_ADDRESS_RE.finditer(row):
                    icon_x = cell_len(row[:m.end()]) + 1
                    if (by_cell.get((icon_x, y)) or "").lower() == m.group(0).lower():
                        continue
                    token_x = cell_len(row[:m.start()])
                    painter = _widget_module_at(app, token_x, y)
                    if _hash_only_module(painter) and _continues_as_hash_window(
                        m.group(0)[2:], row[m.end():], hashes
                    ):
                        continue  # a windowed hash's own head, painted by a widget
                        # that can never construct an icon -- not a bare address
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
                    token_x = cell_len(row[:m.start()])
                    painter = _widget_module_at(app, token_x, y)
                    if not copied and _shortened_window_hash_excuse(head, tail, hashes, painter):
                        continue  # the same window is also a transaction hash's, painted by
                        # a widget that can never construct an icon -- not a bare address
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
