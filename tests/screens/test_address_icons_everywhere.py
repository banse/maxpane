"""E2: every address that reaches the screen carries an icon that copies it.

Two different sets, each asking a different question (PRD §7 E2). **Every
icon** must copy an address the payload actually holds, or it is a
wrong-address icon. **Every seeded address** must get an icon in some view, or
a panel dropped one. A single set cannot answer both.
"""

from __future__ import annotations

import dataclasses

import pytest
from rich.cells import cell_len

from maxpane_dashboard.widgets.address import PROSE_ADDRESS_RE, is_address
from tests.address_sweep.registry import CASES
from tests.widgets.address_probe import icon_targets

#: The sweep's terminal: wide and tall enough for every body to render.
SIZE = (170, 60)


def _rows(app) -> list[str]:
    return ["".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips()]


def _addresses_in(value) -> set[str]:
    """Every address ``value`` holds, however it is stored, lower-cased.

    Payloads carry dicts and lists, but also dataclass and pydantic model
    instances (FWA signals, bakery/frenpet models), and addresses embedded in
    longer strings (surf's deploy detail, FWA's drift ``value_str``, a post's
    prose). Missing any of those would make a correct icon read as "copies an
    address the payload does not hold". Searching strings with the prose
    pattern keeps a 64-hex transaction hash out: it is not an address.
    """
    found: set[str] = set()
    seen: set[int] = set()

    def walk(v) -> None:
        if isinstance(v, str):
            found.update(m.group(0).lower() for m in PROSE_ADDRESS_RE.finditer(v))
            return
        if v is None or isinstance(v, (bool, int, float, bytes)):
            return
        if id(v) in seen:
            return
        seen.add(id(v))
        if isinstance(v, dict):
            for key, item in v.items():
                walk(key)
                walk(item)
        elif isinstance(v, (list, tuple, set, frozenset)):
            for item in v:
                walk(item)
        elif dataclasses.is_dataclass(v) and not isinstance(v, type):
            for field in dataclasses.fields(v):
                walk(getattr(v, field.name, None))
        elif hasattr(v, "__dict__"):
            for item in vars(v).values():
                walk(item)

    walk(value)
    return found


def test_the_payload_walker_finds_addresses_in_every_shape():
    @dataclasses.dataclass
    class Row:
        who: str

    class Model:
        def __init__(self) -> None:
            self.owner = "0x" + "b" * 40

    tx = "0x" + "c" * 64
    value = {
        "whole": "0x" + "a" * 40,
        "row": Row("0x" + "d" * 40),
        "model": Model(),
        ("0x" + "e" * 40): 1,
        "prose": ["new contract 0x" + "f" * 40 + " · deployer"],
        "tx": tx,
    }
    assert _addresses_in(value) == {"0x" + c * 40 for c in "abdef"}


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_every_rendered_address_carries_an_icon_that_copies_it(case):
    in_payload = _addresses_in(case.payload())
    seeded = {a.lower() for a in case.seeded}
    assert seeded <= in_payload, (case.name, "a seeded address is not in the payload", seeded - in_payload)
    copied_somewhere: set[str] = set()

    for keys in case.views:
        app = case.build()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            await pilot.pause()
            targets = icon_targets(app)
            rows = _rows(app)

            if case.address_free:
                assert not targets, (case.name, keys, "icon on an address-free dashboard")
                assert not any(PROSE_ADDRESS_RE.search(r) for r in rows), (case.name, keys)
                continue

            for x, y, address in targets:
                assert address is not None and is_address(address), (case.name, keys, x, y)
                assert address.lower() in in_payload, (
                    case.name, keys, address, "icon copies an address the payload does not hold")
            copied_somewhere.update(a.lower() for _, _, a in targets if a)

            # every full address printed on screen has its own icon right after it
            by_cell = {(x, y): a for x, y, a in targets}
            for y, row in enumerate(rows):
                for m in PROSE_ADDRESS_RE.finditer(row):
                    icon_x = cell_len(row[:m.end()]) + 1
                    assert (by_cell.get((icon_x, y)) or "").lower() == m.group(0).lower(), (
                        case.name, keys, y, m.group(0), "full address without its icon")

    if not case.address_free:
        missing = seeded - copied_somewhere
        assert not missing, (case.name, "seeded addresses never got an icon in any view", missing)
