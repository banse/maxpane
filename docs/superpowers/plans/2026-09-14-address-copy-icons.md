# Copy icon beside every 0x address — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 0x wallet or contract address that any MaxPane dashboard or view renders gets a clickable `⧉` beside it that copies the full address to the user's clipboard, and tests make that rule bind every future dashboard.

**Architecture:** One pure helper module (`widgets/address.py`) renders every address, shortened address, name-backed address and address-in-prose as a `rich.text.Text` whose icon carries a Textual `@click` action. One app-level mixin runs that action through a write-only clipboard module (native tool first, OSC 52 second) and reports the honest outcome in the status bar. Seven dashboard packages convert their call sites in parallel, and then a composited sweep plus source and registration tests enforce the rule.

**Tech Stack:** Python 3.11, Textual 8.1.1, Rich, pytest + pytest-asyncio (`asyncio_mode = "auto"`). No new dependencies.

**Spec:** `docs/address_copy_PRD.md`, including its two AMENDED blocks in §3. Read it first; every task argues from it.

## Global Constraints

- **Strictly read-only.** The only new capability is a local clipboard **write**. No signing, no transactions, no network, and the clipboard is **never read**.
- **Keyless.** Nothing added needs any key.
- **No test may touch the network, and no test may touch the real clipboard.** The clipboard runner is replaced for the whole suite by `tests/conftest.py` (Task 1).
- **Validation uses `fullmatch`**, never `^…$`. `$` matches before a trailing newline (PRD §3.1 AMENDED).
- **Only a validated address is interpolated into an action string.** Invalid values render plain, with no icon and no action anywhere in their spans.
- **The window rule** (PRD §3.2 AMENDED): `budget = width − 3`, `tail = min(6, budget // 2)`, `head = budget − tail`, width clamped to ≥ 11. At 17 cells that is 8/6, the anti-poisoning form. Case is preserved; curator lower-cases before calling.
- **`ICON_COLS = 2`** (a space plus a one-cell `⧉`). **No layout pin is raised for the icon.** A panel grows where it has slack and shortens its displayed address where it has none (PRD §5).
- **Fit on `rich.cells.cell_len`, never `len()`.** Names are attacker-chosen and can be CJK or emoji.
- **Theme tokens (`$success`, `$warning`, …) are not Rich styles.** Never pass one to `Text(style=…)` or `Style(...)`: Rich cannot parse them, and `tests/widgets/test_fwa_accessibility.py` forbids handing one to a Rich parsing surface. Where a line's colour is a theme token, keep that colour on the widget's CSS class or resolve the token to a concrete colour first, and prove it with a composited colour assertion.
- **Widgets may import `widgets/address.py`** (rich-only, Textual-free). They may not import `data/`.
- **Assert against composited output.** Read icons with `tests/widgets/address_probe.icon_targets` (Task 1); never with a content string.
- **Prove every test bites.** Mutate, watch the **named** test go red, restore. Use a `PYTHONPYCACHEPREFIX` unique per mutation. `pytest ::nonexistent_test` exits 4, so a non-zero exit is not evidence.
- `.venv/bin/python -m pytest`, never system `python3`. **Run your own files, never the full suite**, except in Task 10. Never background a test command; never use `timeout` (absent on macOS).
- **Never `git checkout --` any file.** The tree holds the owner's unrelated uncommitted work. Restore mutations from your own copies.
- **Report defects in other packages' files; do not fix them.** Do not merge, push, tag or branch.

### Names frozen by Tasks 0 and 1 — do not invent variants

| Name | Where | Signature |
|---|---|---|
| `is_address` | `widgets/address.py` | `(value: object) -> bool` |
| `short_address` | `widgets/address.py` | `(address: str, width: int) -> str` |
| `short_hex` | `widgets/address.py` | `(value: str, width: int) -> str` |
| `copy_action` | `widgets/address.py` | `(address: str) -> str` → `"app.copy_address('0x…')"` |
| `address_text` | `widgets/address.py` | `(address, *, label=None, width=None, style="") -> Text` |
| `address_prose` | `widgets/address.py` | `(text: str, *, style="") -> Text` |
| `is_copy_click` | `widgets/address.py` | `(event: object) -> bool` |
| `COPY_GLYPH`, `ICON_COLS`, `MIN_SHORT_COLS` | `widgets/address.py` | `"⧉"`, `2`, `11` |
| `copy_text` | `maxpane_dashboard/clipboard.py` | `async (text, *, osc52, runner=None, which=shutil.which, platform=sys.platform) -> str` |
| `copy_message` | `maxpane_dashboard/clipboard.py` | `(outcome: str, address: str \| None) -> str` |
| `COPIED`, `UNCONFIRMED`, `UNAVAILABLE` | `maxpane_dashboard/clipboard.py` | outcome words |
| `CopyAddressMixin` | `maxpane_dashboard/copy_action.py` | `action_copy_address(self, address: str)`, `COPY_MESSAGE_S = 3.0` |
| `StatusBar.message` | `widgets/status_bar.py` | read-only property, `""` when none |
| `icon_targets` | `tests/widgets/address_probe.py` | `(app) -> list[tuple[int, int, str \| None]]` |
| `CopyRecorder` | `tests/widgets/address_probe.py` | mixin; `self.copied: list[str]` |

---

## The conversion recipe — every Wave 1 task follows it

1. **Confirm each candidate module** in your task renders an address. A module that only slices strings for another purpose is a false positive; name it in your report and leave it alone.
2. **Replace the private formatter and its call sites** with the helper, then **delete the private formatter**. Do not re-export it under another name.

```python
from maxpane_dashboard.widgets.address import address_text, address_prose, short_hex, is_copy_click

# a DataTable cell — Text cells are accepted, and the icon's click works inside them
table.add_row(address_text(row.get("address"), width=ADDR_COLS), ...)

# a Static line composed of parts — build Text, never a markup string
line = Text()
line.append("owner ", style="dim")
line.append_text(address_text(owner, width=17))
self.query_one("#owner", Static).update(line)

# a RichLog line
log.write(address_text(holder, width=17))

# a name standing in for an address: the name is shown, the icon copies the address
address_text(entry.get("address"), label=entry.get("name") or None, width=NAME_COLS)

# third-party prose that may contain addresses (a transaction hash never gets an icon)
body = address_prose(post_text)

# a transaction hash (outside the rule): shortened, no icon
short_hex(tx_hash, 17)
```

3. **A widget with its own `on_click`** puts the guard first, before `event.stop()`, so the copy still fires and a click elsewhere still runs the widget's behaviour:

```python
def on_click(self, event) -> None:
    if is_copy_click(event):
        return
    event.stop()
    self.action_toggle()
```

4. **Markup-string sites that embed an address** (for example `f"[{colour}]{address}[/]"`) become `Text` composition. Where the colour is a theme token, see Global Constraints.
5. **Data or analytics that shorten an address before the widget** publish the **full address as its own field**, and the widget composes label plus `address_text`. Grow the row-shape declaration (`*_ROW_KEYS` / the models module) and close the tripwires that guard it.
6. **Width, per panel** (PRD §5):
   1. Note the address cell's current display width `W` and every pin the panel touches.
   2. **Grow first:** keep the display at `W` and add `ICON_COLS`. Re-sweep those pins in situ, starting below the pin (terminal-layout skill).
   3. **If a pin moved, shorten instead:** display width `W − ICON_COLS`, clamped to `MIN_SHORT_COLS`. Re-sweep and confirm the pin holds.
   4. **Record every shortening** in the `#:` block of the pin it protects: the panel, `W`, the new width, and the anti-poisoning window before and after.
   5. **Never raise a pin.** If a cell cannot give up two cells honestly, stop and report.
7. **Test the package** against composited output with `icon_targets`, click one icon through `CopyRecorder`, and run the package's existing screen, widget, layout and registration tests. A widget-level test constructs each widget the way its screen does, including any constructor arguments; `widget_cls()` in the task code is the shape, not a promise that every widget takes none.
8. **Mutations**, at minimum: (a) drop the icon from one converted site, and the named test goes red; (b) make one site copy a different address, and the named test goes red.

---

## File Structure

**Created**

| File | Responsibility | Task |
|---|---|---|
| `maxpane_dashboard/widgets/address.py` | validate, window, render address/name/prose + icon, click guard | 0 |
| `maxpane_dashboard/clipboard.py` | write-only clipboard: native tools then OSC 52; outcome words and messages | 1 |
| `maxpane_dashboard/copy_action.py` | `CopyAddressMixin`: the app action and its self-clearing status message | 1 |
| `tests/conftest.py` | autouse guard: no test reaches the real clipboard | 1 |
| `tests/widgets/address_probe.py` | `icon_targets`, `CopyRecorder` | 1 |
| `tests/widgets/test_address.py`, `tests/test_clipboard.py`, `tests/test_copy_action.py` | Wave 0 tests | 0, 1 |
| `tests/address_sweep/__init__.py`, `case.py`, `registry.py`, `builders.py` | the sweep's case type, its cases, and the six missing builders | 9 |
| `tests/test_address_rule.py` | E1 (source) and E5 (tool names) | 9 |
| `tests/screens/test_address_icons_everywhere.py` | E2 (composited sweep) | 9 |
| `tests/test_address_sweep_registry.py` | E3 (registration and agreement) | 9 |

**Modified — one owner each**

| File | Owner |
|---|---|
| `maxpane_dashboard/app.py`, `widgets/status_bar.py` | Task 1 |
| `screens/surf.py`, `data/surf_models.py`, `analytics/surf_signals.py`, `widgets/surf/*` | Task 2 |
| `screens/curator.py`, `data/curator_list_filters.py`, `widgets/curator/*` | Task 3 |
| `__main__.py`, `data/fwa_manager.py`, `analytics/fwa_signals.py`, `widgets/fwa/*` | Task 4 |
| `widgets/base/*` | Task 5 |
| `widgets/cattown/*`, `widgets/talismans/*` | Task 6 |
| `widgets/ttt/*` | Task 7 |
| `widgets/ocm/*`, `widgets/frenpet/*`, `screens/frenpet_{full,perf,wallet}.py`, `widgets/activity_feed.py`, `widgets/leaderboard.py`, `templates/activity_feed_template.py`, `templates/leaderboard_template.py` | Task 8 |
| `themes/minimal.tcss` | **nobody in Wave 1.** A package that needs a CSS change reports it; the orchestrator serialises it |
| `CLAUDE.md`, `README.md`, `.claude/skills/terminal-layout/SKILL.md`, `docs/address_copy_PRD.md` | Task 10 |

## Wave order

```
Wave 0   Task 0 → Task 1                          one agent, sequential, lands alone
Wave 1   Tasks 2–8                                parallel; no shared files
Wave 2   Task 9                                   after all of Wave 1 (E2 can only pass once icons exist)
Wave 3   Task 10                                  last; the full suite
```

---

## Task 0: The address helper

**Files:**
- Create: `maxpane_dashboard/widgets/address.py`
- Test: `tests/widgets/test_address.py`

**Interfaces:**
- Consumes: nothing. **Rich only**: no Textual, no `data/`, no I/O, no clock.
- Produces: every `widgets/address.py` name in the frozen table above.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_address.py
import ast
import pathlib

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets import address as A

ADDR = "0x" + "abcdef0123" * 4          # 40 hex
TX = "0x" + "ab" * 32                   # 64 hex


def _actions(text: Text) -> list[tuple[str, str]]:
    """(covered text, @click action) for every span that carries an action."""
    out = []
    for span in text.spans:
        if isinstance(span.style, Style) and span.style.meta.get("@click"):
            out.append((text.plain[span.start:span.end], span.style.meta["@click"]))
    return out


def test_the_window_reproduces_both_formatters_it_replaces():
    """PRD §3.2 AMENDED: one rule, and it is exactly the two it replaces."""
    assert A.short_address(ADDR, 17) == "0x" + ADDR[2:10] + "…" + ADDR[-6:]   # surf long_addr, 8/6
    assert A.short_address(ADDR, 11) == "0x" + ADDR[2:6] + "…" + ADDR[-4:]    # curator short_addr, 4/4
    assert cell_len(A.short_address(ADDR, 40)) == 40
    assert A.short_address(ADDR, 42) == ADDR
    assert A.short_address(ADDR, 5) == A.short_address(ADDR, 11)             # clamped


def test_the_window_keeps_the_address_case():
    mixed = "0x" + "AbCdEf0123" * 4
    assert A.short_address(mixed, 17) == "0x" + mixed[2:10] + "…" + mixed[-6:]


def test_validation_uses_fullmatch_and_rejects_every_injection_shape():
    assert A.is_address(ADDR)
    assert A.is_address(ADDR.upper().replace("0X", "0x"))
    for bad in (ADDR + "\n", ADDR[:-1] + "'", ADDR[:-1] + ")", ADDR + "0", ADDR[:-1], None, 12, "", "vitalik.eth"):
        assert not A.is_address(bad), repr(bad)


def test_the_icon_copies_the_exact_address_and_only_the_glyph_is_clickable():
    t = A.address_text(ADDR, width=17)
    assert t.plain == A.short_address(ADDR, 17) + " " + A.COPY_GLYPH
    assert _actions(t) == [(A.COPY_GLYPH, f"app.copy_address('{ADDR}')")]
    assert A.copy_action(ADDR) == f"app.copy_address('{ADDR}')"


def test_width_none_shows_the_whole_address():
    assert A.address_text(ADDR).plain == ADDR + " " + A.COPY_GLYPH


def test_an_invalid_value_renders_plain_with_no_action_anywhere():
    for bad in (ADDR + "\n", "0xdead')", "", None, "vitalik.eth"):
        t = A.address_text(bad)
        assert A.COPY_GLYPH not in t.plain, repr(bad)
        assert _actions(t) == [], repr(bad)


def test_a_name_is_shown_and_the_icon_copies_the_address_behind_it():
    t = A.address_text(ADDR, label="vitalik.eth")
    assert t.plain == "vitalik.eth " + A.COPY_GLYPH
    assert _actions(t) == [(A.COPY_GLYPH, A.copy_action(ADDR))]


def test_a_wide_name_is_fitted_on_cells_not_characters():
    t = A.address_text(ADDR, label="名前名前名前名前", width=7)
    assert cell_len(t.plain) == 7 + A.ICON_COLS
    assert t.plain.endswith("… " + A.COPY_GLYPH)


def test_prose_icons_follow_addresses_and_never_a_transaction_hash():
    t = A.address_prose(f"sent to {ADDR}, tx {TX}.")
    assert t.plain == f"sent to {ADDR} {A.COPY_GLYPH}, tx {TX}."
    assert _actions(t) == [(A.COPY_GLYPH, A.copy_action(ADDR))]


def test_prose_finds_addresses_at_both_ends_and_inside_punctuation():
    t = A.address_prose(f"{ADDR} and ({ADDR})")
    assert len(_actions(t)) == 2


def test_short_hex_windows_a_hash_without_an_icon():
    assert A.short_hex(TX, 17) == "0x" + TX[2:10] + "…" + TX[-6:]
    assert A.short_hex("not hex", 17) == "not hex"


class _Evt:
    def __init__(self, meta):
        self.style = Style(meta=meta)


def test_is_copy_click_only_for_copy_icons():
    assert A.is_copy_click(_Evt({"@click": A.copy_action(ADDR)}))
    assert not A.is_copy_click(_Evt({"@click": "app.toggle()"}))
    assert not A.is_copy_click(_Evt({}))
    assert not A.is_copy_click(object())


def test_the_helper_stays_pure():
    tree = ast.parse(pathlib.Path(A.__file__).read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    roots = {m.split(".")[0] for m in modules}
    assert not roots & {"textual", "httpx", "aiohttp", "asyncio", "subprocess"}, roots
    assert not [m for m in modules if m.startswith("maxpane_dashboard.data")]
```

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_address.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'maxpane_dashboard.widgets.address'`

- [ ] **Step 3: Write the helper**

```python
"""Every 0x address a widget renders, with the copy icon beside it.

PRD: ``docs/address_copy_PRD.md``. One module owns every address on screen,
so the rule "a displayed address carries a ``⧉`` that copies it" lives in one
place and the 21 private formatters it replaced cannot drift apart again.

Pure: Rich only. No Textual, no I/O, no clock, no ``data/``. The copy itself
happens in ``maxpane_dashboard/clipboard.py`` via ``copy_action.CopyAddressMixin``;
this module only renders the icon and names the action it triggers.
"""

from __future__ import annotations

import re

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text

__all__ = [
    "ADDRESS_RE", "COPY_GLYPH", "ICON_COLS", "MIN_SHORT_COLS", "PROSE_ADDRESS_RE",
    "address_prose", "address_text", "copy_action", "is_address", "is_copy_click",
    "short_address", "short_hex",
]

#: An address, matched with ``fullmatch`` and **never** with ``^…$``: Python's
#: ``$`` also matches before a trailing newline, so an anchored pattern accepts
#: ``"0x…\n"``, which is exactly the value this check exists to keep out of an
#: action string (PRD §3.1 AMENDED).
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")

#: An address inside prose. Hex boundaries on both sides: a 64-hex transaction
#: hash starts with a 40-hex run, and without the lookahead every hash in a
#: post would get an icon that copies a truncated, meaningless value.
PROSE_ADDRESS_RE = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])")

_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")

#: U+29C9 TWO JOINED SQUARES, one cell wide; chosen by the owner after seeing
#: it render cleanly in their terminal. ``📋`` is two cells and inconsistent.
COPY_GLYPH = "⧉"

#: What one icon costs a layout: a separating space and the one-cell glyph.
ICON_COLS = 2

#: The narrowest window: ``0x`` + 4 + ``…`` + 4, curator's former form.
MIN_SHORT_COLS = 11

_ELLIPSIS = "…"
_TAIL_MAX = 6
_ACTION_PREFIX = "app.copy_address("


def is_address(value: object) -> bool:
    """True only for a whole, well-formed 0x address."""
    return isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None


def _window(value: str, width: int) -> str:
    """The anti-poisoning window (PRD §3.2 AMENDED).

    ``budget = width - 3`` for ``0x`` and ``…``; ``tail = min(6, budget // 2)``;
    ``head = budget - tail``. At 17 cells that is 8/6 (surf's ``long_addr``,
    which exists because live spoofs collide with real addresses on 6/4), at
    11 it is 4/4 (curator's ``short_addr``). Case is preserved.
    """
    width = max(width, MIN_SHORT_COLS)
    if cell_len(value) <= width:
        return value
    budget = width - 3
    tail = min(_TAIL_MAX, budget // 2)
    head = budget - tail
    return f"0x{value[2:2 + head]}{_ELLIPSIS}{value[-tail:]}"


def short_address(address: str, width: int) -> str:
    """``address`` windowed to ``width`` cells; a non-address passes through."""
    return _window(address, width) if is_address(address) else address


def short_hex(value: str, width: int) -> str:
    """Any other 0x hex (a transaction hash) windowed the same way. No icon."""
    if isinstance(value, str) and _HEX_RE.fullmatch(value):
        return _window(value, width)
    return value


def copy_action(address: str) -> str:
    """The action string for a **validated** address. Never call it otherwise."""
    return f"{_ACTION_PREFIX}{address!r})"


def _fit(text: str, width: int | None) -> str:
    """``text`` fitted to ``width`` cells with a trailing ellipsis."""
    if width is None or cell_len(text) <= width:
        return text
    out = ""
    for ch in text:
        if cell_len(out) + cell_len(ch) > width - 1:
            break
        out += ch
    return out + _ELLIPSIS


def _icon(address: str) -> tuple[str, Style]:
    return COPY_GLYPH, Style(meta={"@click": copy_action(address)})


def address_text(
    address: str | None,
    *,
    label: str | None = None,
    width: int | None = None,
    style: str | Style = "",
) -> Text:
    """Display text plus ``" ⧉"``, the click action on the glyph only.

    ``label`` is shown instead of the address (an ENS or player name); the icon
    still copies ``address``. ``width`` is the budget for the displayed part and
    **excludes** :data:`ICON_COLS`; ``None`` shows the whole address. A value
    that is not a valid address renders plain, with no icon and no action.
    ``style`` must be a Rich style, never a ``$theme`` token.
    """
    valid = is_address(address)
    if label:
        shown = _fit(label, width)
    elif valid:
        shown = address if width is None else short_address(address, width)
    else:
        shown = _fit(str(address) if address else "--", width)
    out = Text(shown, style=style)
    if valid:
        out.append(" ")
        out.append(*_icon(address))
    return out


def address_prose(text: str, *, style: str | Style = "") -> Text:
    """``text`` with ``" ⧉"`` inserted after every valid address in it."""
    out = Text(style=style)
    pos = 0
    for match in PROSE_ADDRESS_RE.finditer(text):
        out.append(text[pos:match.end()])
        out.append(" ")
        out.append(*_icon(match.group(0)))
        pos = match.end()
    out.append(text[pos:])
    return out


def is_copy_click(event: object) -> bool:
    """True when a click landed on a copy icon.

    A widget with its own ``on_click`` returns early when this is true, so the
    icon's copy fires and the widget's own behaviour does not (PRD §3.4).
    """
    meta = getattr(getattr(event, "style", None), "meta", None) or {}
    action = meta.get("@click")
    return isinstance(action, str) and action.startswith(_ACTION_PREFIX)
```

- [ ] **Step 4: Run and watch it pass**

Run: `.venv/bin/python -m pytest tests/widgets/test_address.py -v`
Expected: 13 passed

- [ ] **Step 5: Prove the tests bite** (unique `PYTHONPYCACHEPREFIX` each; restore from a copy)

| Mutation | Must turn red |
|---|---|
| `ADDRESS_RE.fullmatch` → `re.match(r"^0x[0-9a-fA-F]{40}$", value)` | `test_validation_uses_fullmatch_and_rejects_every_injection_shape` (the `"\n"` case) |
| `tail = min(_TAIL_MAX, …)` → `tail = 4` | `test_the_window_reproduces_both_formatters_it_replaces` |
| drop the lookahead from `PROSE_ADDRESS_RE` | `test_prose_icons_follow_addresses_and_never_a_transaction_hash` |
| in `_fit`, `cell_len(out) + cell_len(ch)` → `len(out) + 1` | `test_a_wide_name_is_fitted_on_cells_not_characters` |
| `if valid:` → `if True:` in `address_text` | `test_an_invalid_value_renders_plain_with_no_action_anywhere` |

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/address.py tests/widgets/test_address.py
git commit -m "feat: one address helper that renders a copy icon beside every address"
```

---

## Task 1: The clipboard, the app action, and the test harness

**Files:**
- Create: `maxpane_dashboard/clipboard.py`, `maxpane_dashboard/copy_action.py`, `tests/conftest.py`, `tests/widgets/address_probe.py`
- Modify: `maxpane_dashboard/widgets/status_bar.py` (add the `message` property), `maxpane_dashboard/app.py:48` (class bases)
- Test: `tests/test_clipboard.py`, `tests/test_copy_action.py`, `tests/widgets/test_address_probe.py`

**Interfaces:**
- Consumes: `is_address`, `short_address`, `copy_action`, `COPY_GLYPH` (Task 0).
- Produces: `clipboard.copy_text`, `clipboard.copy_message`, the three outcome words, `CopyAddressMixin`, `StatusBar.message`, `icon_targets`, `CopyRecorder`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_clipboard.py
import asyncio

import pytest

from maxpane_dashboard import clipboard as C
from maxpane_dashboard.widgets.address import short_address

ADDR = "0x" + "abcdef0123" * 4


async def test_a_native_tool_that_succeeds_is_copied_and_osc52_is_untouched():
    calls, osc = [], []

    async def runner(cmd, data):
        calls.append((cmd, data))
        return 0

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: f"/usr/bin/{name}", platform="darwin")
    assert out == C.COPIED
    assert calls == [(("pbcopy",), ADDR.encode())]
    assert osc == []


async def test_no_native_tool_falls_back_to_osc52_and_says_unconfirmed():
    osc = []

    async def runner(cmd, data):  # pragma: no cover - must not be reached
        raise AssertionError("no tool exists, so none may run")

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: None, platform="darwin")
    assert out == C.UNCONFIRMED
    assert osc == [ADDR]


async def test_linux_tries_each_tool_in_order_then_osc52():
    tried, osc = [], []

    async def runner(cmd, data):
        tried.append(cmd[0])
        if cmd[0] == "xclip":
            raise OSError("broken")
        if cmd[0] == "xsel":
            raise asyncio.TimeoutError
        return 1

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: f"/usr/bin/{name}", platform="linux")
    assert tried == ["wl-copy", "xclip", "xsel"]
    assert out == C.UNCONFIRMED and osc == [ADDR]


async def test_osc52_failing_too_is_unavailable():
    def osc52(text):
        raise RuntimeError("no driver")

    out = await C.copy_text(ADDR, osc52=osc52, which=lambda name: None, platform="darwin")
    assert out == C.UNAVAILABLE


async def test_the_default_runner_is_looked_up_at_call_time(monkeypatch):
    """A default bound at definition time would let tests escape the conftest guard."""
    seen = []

    async def fake(cmd, data):
        seen.append(cmd)
        return 0

    monkeypatch.setattr(C, "_run", fake)
    out = await C.copy_text(ADDR, osc52=lambda t: None,
                            which=lambda name: "/x", platform="darwin")
    assert out == C.COPIED and seen == [("pbcopy",)]


async def test_the_suite_cannot_reach_the_real_clipboard():
    with pytest.raises(AssertionError, match="real clipboard"):
        await C._run(("pbcopy",), b"x")


def test_the_messages_are_honest_and_contain_no_markup():
    messages = {
        C.COPIED: C.copy_message(C.COPIED, ADDR),
        C.UNCONFIRMED: C.copy_message(C.UNCONFIRMED, ADDR),
        C.UNAVAILABLE: C.copy_message(C.UNAVAILABLE, None),
    }
    assert messages[C.COPIED] == f"copied {short_address(ADDR, 17)}"
    assert messages[C.UNCONFIRMED] == "sent to terminal clipboard (unconfirmed)"
    assert messages[C.UNAVAILABLE] == "copy unavailable"
    for text in messages.values():
        assert "[" not in text and "]" not in text   # StatusBar.set_message wraps in markup
```

```python
# tests/test_copy_action.py
from textual.app import App

from maxpane_dashboard import clipboard as C
from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.widgets.status_bar import StatusBar

ADDR = "0x" + "abcdef0123" * 4


class _App(CopyAddressMixin, App):
    COPY_MESSAGE_S = 0.05

    def compose(self):
        yield StatusBar()


class _BareApp(CopyAddressMixin, App):
    COPY_MESSAGE_S = 0.05


async def test_a_copy_posts_the_outcome_and_clears_it(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test() as pilot:
        await app.run_action(f"copy_address('{ADDR}')")
        bar = app.screen.query_one(StatusBar)
        assert bar.message == C.copy_message(C.COPIED, ADDR)
        await pilot.pause(0.2)
        assert bar.message == ""


async def test_the_clear_never_erases_a_newer_message(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test() as pilot:
        await app.run_action(f"copy_address('{ADDR}')")
        bar = app.screen.query_one(StatusBar)
        bar.set_message("fetching ENS …")
        await pilot.pause(0.2)
        assert bar.message == "fetching ENS …"


async def test_an_invalid_address_never_reaches_the_clipboard(monkeypatch):
    called = []

    async def fake_copy(text, **kw):  # pragma: no cover - must not run
        called.append(text)
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test():
        await app.action_copy_address(ADDR + "\n")
        assert called == []
        assert app.screen.query_one(StatusBar).message == "copy unavailable"


async def test_a_screen_without_a_status_bar_does_not_raise(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _BareApp()
    async with app.run_test():
        await app.action_copy_address(ADDR)


def test_the_real_app_carries_the_action():
    assert issubclass(MaxPaneApp, CopyAddressMixin)
```

```python
# tests/widgets/test_address_probe.py
from rich.text import Text
from textual.app import App
from textual.widgets import Static

from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text
from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4


class _App(CopyRecorder, App):
    def compose(self):
        line = Text("名前 ")                         # 5 cells, 3 characters
        line.append_text(address_text(ADDR, width=17))
        yield Static(line)


async def test_icon_targets_reads_cell_positions_and_the_copied_address():
    app = _App()
    async with app.run_test(size=(60, 4)) as pilot:
        await pilot.pause()
        [(x, y, target)] = icon_targets(app)
        assert target == ADDR
        assert x == 5 + 17 + 1                       # cells, not characters
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/test_clipboard.py tests/test_copy_action.py tests/widgets/test_address_probe.py -v`
Expected: FAIL — `ModuleNotFoundError` for `maxpane_dashboard.clipboard`

- [ ] **Step 3: Write `maxpane_dashboard/clipboard.py`**

```python
"""Write-only local clipboard for the copy icon (PRD §4).

Never reads the clipboard. Native tools first: ``App.copy_to_clipboard`` writes
OSC 52, which Apple Terminal ignores, so on the owner's machine the native path
is the one that actually works. OSC 52 is the fallback (SSH), and because it
cannot confirm anything, its outcome is reported as unconfirmed.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Awaitable, Callable

from maxpane_dashboard.widgets.address import short_address

__all__ = ["COPIED", "UNCONFIRMED", "UNAVAILABLE", "OUTCOMES", "NATIVE_TIMEOUT_S",
           "copy_message", "copy_text", "native_commands"]

COPIED = "copied"
UNCONFIRMED = "unconfirmed"
UNAVAILABLE = "unavailable"
OUTCOMES = (COPIED, UNCONFIRMED, UNAVAILABLE)

#: A native tool that has not finished in this long is abandoned for the next.
NATIVE_TIMEOUT_S = 2.0

Runner = Callable[[tuple[str, ...], bytes], Awaitable[int]]


def native_commands(platform: str = sys.platform) -> tuple[tuple[str, ...], ...]:
    if platform == "darwin":
        return (("pbcopy",),)
    if platform.startswith("win"):
        return (("clip",),)
    return (("wl-copy",), ("xclip", "-selection", "clipboard"), ("xsel", "--clipboard", "--input"))


async def _run(cmd: tuple[str, ...], data: bytes) -> int:
    """Run one tool with ``data`` on stdin. No shell; an argument list only."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.communicate(data), NATIVE_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode if proc.returncode is not None else 1


async def copy_text(
    text: str,
    *,
    osc52: Callable[[str], None],
    runner: Runner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    platform: str = sys.platform,
) -> str:
    """Copy ``text``; return one of :data:`OUTCOMES`.

    ``runner`` defaults to ``_run`` **looked up at call time**, never bound as a
    default argument, so the suite-wide guard in ``tests/conftest.py`` cannot be
    escaped by a default captured before it was installed.
    """
    run = runner if runner is not None else _run
    data = text.encode()
    for cmd in native_commands(platform):
        if which(cmd[0]) is None:
            continue
        try:
            if await run(cmd, data) == 0:
                return COPIED
        except (OSError, asyncio.TimeoutError):
            continue
    try:
        osc52(text)
    except Exception:  # noqa: BLE001 — any driver failure is "could not copy"
        return UNAVAILABLE
    return UNCONFIRMED


def copy_message(outcome: str, address: str | None) -> str:
    """The status-bar sentence for an outcome. Plain words and validated hex only.

    ``StatusBar.set_message`` wraps its argument in markup, so nothing
    third-party may ever reach it; an address here has already passed
    ``is_address``.
    """
    if outcome == COPIED and address:
        return f"copied {short_address(address, 17)}"
    if outcome == UNCONFIRMED:
        return "sent to terminal clipboard (unconfirmed)"
    return "copy unavailable"
```

- [ ] **Step 4: Write `maxpane_dashboard/copy_action.py`**

```python
"""The one app-level action every copy icon calls (PRD §4)."""

from __future__ import annotations

from maxpane_dashboard import clipboard
from maxpane_dashboard.widgets.address import is_address
from maxpane_dashboard.widgets.status_bar import StatusBar


class CopyAddressMixin:
    """Mixed into ``MaxPaneApp`` ahead of ``App``."""

    #: How long the outcome stays in the status bar.
    COPY_MESSAGE_S: float = 3.0

    async def action_copy_address(self, address: str) -> None:
        # Validated again here: the icon's meta is not the only way to invoke
        # an action, and an unvalidated value must never reach a subprocess.
        if not is_address(address):
            self._post_copy_message(clipboard.UNAVAILABLE, None)
            return
        outcome = await clipboard.copy_text(address, osc52=self.copy_to_clipboard)
        self._post_copy_message(outcome, address)

    def _post_copy_message(self, outcome: str, address: str | None) -> None:
        bars = self.screen.query(StatusBar)
        if not bars:
            return  # splash, game select and the wallet prompt have no status bar
        bar = bars.first()
        message = clipboard.copy_message(outcome, address)
        token = object()
        self._copy_message_token = token
        bar.set_message(message)

        def _clear() -> None:
            # Only our own, and only if still on display: an ENS fetch or an
            # export that posted since keeps its message (CLAUDE.md ownership).
            if getattr(self, "_copy_message_token", None) is token and bar.message == message:
                bar.set_message("")

        self.set_timer(self.COPY_MESSAGE_S, _clear)
```

- [ ] **Step 5: Add `StatusBar.message`**

In `maxpane_dashboard/widgets/status_bar.py`, directly above `def set_message`:

```python
    @property
    def message(self) -> str:
        """The centred operation message currently on display (``""`` when none)."""
        return getattr(self, "_message", "")
```

- [ ] **Step 6: Mix the action into the app**

In `maxpane_dashboard/app.py`, add the import beside the other `maxpane_dashboard` imports:

```python
from maxpane_dashboard.copy_action import CopyAddressMixin
```

and change `class MaxPaneApp(App):` (line 48) to:

```python
class MaxPaneApp(CopyAddressMixin, App):
```

- [ ] **Step 7: Write the suite-wide guard and the probe**

```python
# tests/conftest.py
"""Suite-wide guards. Every test runs under these."""

import pytest


@pytest.fixture(autouse=True)
def _forbid_real_clipboard(monkeypatch):
    """No test may spawn pbcopy / xclip / wl-copy / xsel / clip.

    A headless suite that overwrote the developer's clipboard would be the
    MANAGER_ATTRS cache-overwrite hazard in a new place (PRD §7 E5).
    """

    async def _refuse(cmd, data):
        raise AssertionError(f"a test reached the real clipboard: {cmd!r}")

    monkeypatch.setattr("maxpane_dashboard.clipboard._run", _refuse)
```

```python
# tests/widgets/address_probe.py
"""Read copy icons off composited output: where each is and what it copies."""

from __future__ import annotations

import re

from rich.cells import cell_len

from maxpane_dashboard.widgets.address import COPY_GLYPH

_ACTION = re.compile(r"app\.copy_address\('(0x[0-9a-fA-F]{40})'\)")


def icon_targets(app) -> list[tuple[int, int, str | None]]:
    """Every ``⧉`` on screen as ``(x, y, copied address)``.

    ``x`` is a **cell** column, accumulated with ``cell_len``: a CJK name
    before the icon would put a character index on the wrong cell. The
    address comes from the compositor's style at that cell, which is the
    click target a user would hit; ``None`` means an icon whose action is not
    a well-formed copy.
    """
    out: list[tuple[int, int, str | None]] = []
    for y, strip in enumerate(app.screen._compositor.render_strips()):
        x = 0
        for segment in strip:
            for ch in segment.text:
                if ch == COPY_GLYPH:
                    meta = app.screen.get_style_at(x, y).meta or {}
                    match = _ACTION.fullmatch(str(meta.get("@click", "")))
                    out.append((x, y, match.group(1) if match else None))
                x += cell_len(ch)
    return out


class CopyRecorder:
    """Mix into a harness ``App`` ahead of ``App``: records copies, touches no clipboard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.copied: list[str] = []

    async def action_copy_address(self, address: str) -> None:
        self.copied.append(address)
```

- [ ] **Step 8: Run and watch them pass**

Run: `.venv/bin/python -m pytest tests/test_clipboard.py tests/test_copy_action.py tests/widgets/test_address_probe.py tests/widgets/test_address.py -v`
Expected: all pass

Run the tests that construct the real app, which must stay green: `.venv/bin/python -m pytest tests/test_app_startup.py tests/test_game_select_quit.py -q`

- [ ] **Step 9: Prove the tests bite**

| Mutation | Must turn red |
|---|---|
| `run = runner if runner is not None else _run` → a default argument `runner: Runner = _run` | `test_the_default_runner_is_looked_up_at_call_time` |
| `return UNCONFIRMED` → `return COPIED` | `test_no_native_tool_falls_back_to_osc52_and_says_unconfirmed` |
| delete `and bar.message == message` | `test_the_clear_never_erases_a_newer_message` |
| delete the `is_address` check in `action_copy_address` | `test_an_invalid_address_never_reaches_the_clipboard` |
| delete the autouse fixture body | `test_the_suite_cannot_reach_the_real_clipboard` |
| in `icon_targets`, `x += cell_len(ch)` → `x += 1` | `test_icon_targets_reads_cell_positions_and_the_copied_address` |

- [ ] **Step 10: Commit**

```bash
git add maxpane_dashboard/clipboard.py maxpane_dashboard/copy_action.py maxpane_dashboard/app.py maxpane_dashboard/widgets/status_bar.py tests/conftest.py tests/widgets/address_probe.py tests/test_clipboard.py tests/test_copy_action.py tests/widgets/test_address_probe.py
git commit -m "feat: copy_address app action with a native clipboard and an honest status message"
```

---

## Task 2: surf

**Files:**
- Modify: `widgets/surf/_fmt.py` (delete `long_addr`, `full_addr` once no caller remains), `widgets/surf/activity.py`, `burnkeepers.py`, `launchpad.py`, `launchpad_activity.py`, `pool4_hatches.py`, `pool4u_stakers.py`, `feed.py`; `analytics/surf_signals.py:542` and `:1004`, plus the widget that renders those signal rows; `data/surf_models.py` (row-shape keys, only if a signal row gains an `address` field); `screens/surf.py` (**pins and their `#:` blocks only**)
- Confirm, and do not change if it is a false positive: `widgets/surf/_rowfit.py`
- Test: `tests/widgets/test_surf_address_icons.py`

**Interfaces:**
- Consumes: `address_text`, `address_prose`, `short_hex`, `is_copy_click`, `ICON_COLS` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific to surf:**
- **`long_addr` is the anti-poisoning 17-cell window** (8/6). Its callers (HATCHES, the dashboard activity feed) keep `width=17` unless a pin forces shortening, and any shortening records the anti-poisoning cost in the pin's `#:` block.
- **STAKERS** (`pool4u_stakers.py`) shows whole 42-character addresses and binds `SURF_POOL4_USER_FULL_LAYOUT_COLUMNS = 119`. Tier: whole address plus icon when the column's budget is at least `42 + ICON_COLS`; otherwise `width=40`, the PRD §5 trade that holds 119. Record it in that constant's `#:` block.
- **`feed.py`:** announce post bodies are third-party prose, so use `address_prose`. The row's `on_click` is `event.stop(); self.action_toggle()`; add the `is_copy_click` guard first (recipe step 3). The terminal-layout skill's caveat applies: a linked post already lights `‹ widen` at 143, and that marker is correct, so do not raise `SURF_FULL_LAYOUT_COLUMNS` for prose icons.
- **HATCHES' discovery detail** (`adopted 0x… — flags,…`) is prose: use `address_prose`. The citation `tx 0x…` is a transaction hash: use `short_hex`, with no icon.
- **`analytics/surf_signals.py`:** `:542` returns `f"{text[:10]}…{text[-6:]}"` and `:1004` builds `f"new contract {_short_addr(label)}"`. Publish the full address as its own field on that signal row, delete `_short_addr` there, and have the rendering widget compose the label with `address_text(address, width=17)`. If that grows a row shape in `data/surf_models.py`, close the tripwires it trips (`tests/test_surf_registration.py`, `tests/screens/test_surf_screen.py` signature maps).
- **`tests/widgets/test_surf_widget_contract.py`** allowlists what surf widgets may import. `widgets.address` is Textual-free and rich-only; add it wherever that allowlist requires.
- **Pins this task re-sweeps:** `SURF_FULL_LAYOUT_COLUMNS = 143`, `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS/ROWS = 138/31`, `widgets/surf/launchpad._TABLE_FULL_WIDTH = 89`, `SURF_POOL4_FULL_LAYOUT_COLUMNS/ROWS = 99/45`, `SURF_POOL4_USER_FULL_LAYOUT_COLUMNS/ROWS = 119/35`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_surf_address_icons.py
from tests.screens.test_surf_screen import (
    _ThemedHarness, _FakeManager, _frozen_payload, _mainnet_pool4_payload,
)
from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.screens.surf import SurfScreen


class _CopyHarness(CopyRecorder, _ThemedHarness):
    pass


def _app(payload):
    return _CopyHarness(SurfScreen(_FakeManager(payload), poll_interval=30, name="surf"))


def _addresses_in(payload) -> set[str]:
    from maxpane_dashboard.widgets.address import is_address
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


async def _targets(payload, keys=(), size=(160, 60)):
    app = _app(payload)
    async with app.run_test(size=size) as pilot:
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
        return icon_targets(app), app


async def test_every_surf_body_renders_icons_and_every_icon_copies_a_payload_address():
    for payload, keys in ((_frozen_payload(), ()), (_frozen_payload(), ("l",)),
                          (_mainnet_pool4_payload(), ("p",)), (_mainnet_pool4_payload(), ("4",))):
        targets, _ = await _targets(payload, keys)
        assert targets, f"no copy icon on the surf body after {keys}"
        known = _addresses_in(payload)
        for x, y, address in targets:
            assert address in known, (keys, x, y, address)


async def test_clicking_a_stakers_icon_copies_that_row_address():
    payload = _mainnet_pool4_payload()
    app = _app(payload)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        targets = icon_targets(app)
        assert targets
        x, y, address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


async def test_a_feed_icon_click_copies_and_does_not_toggle_the_thread():
    payload = _frozen_payload()
    app = _app(payload)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        before = app.screen.query_one("#surf-feed-body").virtual_size
        feed_targets = [t for t in icon_targets(app)
                        if app.screen.query_one("#surf-feed-body").region.contains(t[0], t[1])]
        assert feed_targets, (
            "no copy icon inside the feed: seed a post body carrying a full address "
            "into this test's payload, or the test proves nothing")
        x, y, address = feed_targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]
        assert app.screen.query_one("#surf-feed-body").virtual_size == before
```

> **Seed a post body containing a full address** into the payload this test uses, before Step 2. The frozen payload may not carry one, and the assertion is written to fail rather than pass vacuously when it does not. Say which field you seeded in your report.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_address_icons.py -v`
Expected: FAIL — `assert targets` (no copy icon on the surf body)

- [ ] **Step 3: Convert every surf site** per the recipe and the specifics above. Delete `_fmt.long_addr`, `_fmt.full_addr` and the three private `_short_addr`s once nothing imports them.

- [ ] **Step 4: Re-sweep the surf pins** per recipe step 6 and record every shortening in its `#:` block.

- [ ] **Step 5: Run the surf suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_address_icons.py tests/screens/test_surf_screen.py tests/screens/test_surf_pool4_market_screen.py tests/screens/test_surf_pool4_market_layout.py tests/test_surf_registration.py tests/widgets/test_surf_widget_contract.py -q`
Expected: all pass

- [ ] **Step 6: Prove the tests bite:** recipe step 8, plus: remove the `is_copy_click` guard from `feed.py`, and `test_a_feed_icon_click_copies_and_does_not_toggle_the_thread` must turn red.

- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/widgets/surf maxpane_dashboard/analytics/surf_signals.py maxpane_dashboard/data/surf_models.py maxpane_dashboard/screens/surf.py tests/widgets/test_surf_address_icons.py tests/screens tests/test_surf_registration.py tests/widgets/test_surf_widget_contract.py
git commit -m "feat(surf): copy icon beside every address, name and prose address"
```

---

## Task 3: curator

**Files:**
- Modify: `widgets/curator/_fmt.py` (delete `short_addr` once unused), `activity.py`, `closest_calls.py`, `leaderboard.py`, `list_hero.py`, `signals.py`; `data/curator_list_filters.py:67`; `screens/curator.py` (**pin and `#:` block only**)
- Leave alone: `widgets/curator/list_filter.py:201` (`f"{chain}:{address.casefold()}"` is a key, not a display)
- Test: `tests/widgets/test_curator_address_icons.py`

**Interfaces:**
- Consumes: `address_text`, `ICON_COLS`, `MIN_SHORT_COLS` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific to curator:**
- **Lower-casing is deliberate** (`_fmt.short_addr` docstring: two sources spell one wallet two ways, and "this row is you" must not depend on which panel you read). Call `address_text(address.lower(), width=ADDR_COLS)` and keep that reason in the widget's own comment. The icon then copies the lower-case form, which is equally valid.
- **`activity.py:253`** builds `f"[{colour}]{address}[/]"` and **`list_hero.py:170`** builds `f"[$success]{_wallet_address(data)}[/]"`. Both become `Text` composition. `$success` is a theme token: per Global Constraints it must not go into a Rich style. Keep that colour on the widget's CSS class, or resolve it to a concrete colour, and prove the address still renders in success green with a composited colour assertion. CLAUDE.md's record-list hero contract names that colour.
- **ENS names are shown beside the address** on the wallet card. The icon goes on the address, and the name stays as it is.
- **`data/curator_list_filters.py:67`** returns `f"{prefix} {address[:6]}…{address[-4:]}"` for the filter summary. Publish the full address as its own field and compose in the widget.
- **The list view's header-click sort** (`lists.py:548`) is the repo's only `DataTable` selection handler, and icons never sit in a header. A click on an icon moves the list cursor to that row (PRD §11, accepted).
- **Pin:** `CURATOR_FULL_LAYOUT_COLUMNS = 138`. CLAUDE.md records that the status hint and the worst-case `4 errors` fit at 138 only after deliberate trimming. Re-sweep, do not assume.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_curator_address_icons.py
import re

from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.widgets.address import is_address

# Use the curator screen test's existing harness and payload builders.
from tests.screens import test_curator_screen as T


def _harness_class():
    """The App subclass test_curator_screen builds its screens with."""
    for name in dir(T):
        obj = getattr(T, name)
        if isinstance(obj, type) and name.endswith("Harness"):
            return obj
    raise AssertionError("test_curator_screen defines no *Harness App; name the one it uses")


def _addresses_in(payload) -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v.lower())
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


async def test_curator_views_render_icons_that_copy_payload_addresses():
    Harness = _harness_class()

    class _CopyHarness(CopyRecorder, Harness):
        pass

    for payload_fn, keys in ((T._frozen_payload, ()), (T._wallet_payload, ("y",)),
                             (T._analysis_payload, ("f",)), (T._list_payload, ("l",))):
        payload = payload_fn()
        app = _CopyHarness(T.CuratorScreen(T._FakeManager(payload), poll_interval=30))
        async with app.run_test(size=(150, 55)) as pilot:
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            targets = icon_targets(app)
            assert targets, f"no copy icon on curator after {keys}"
            known = _addresses_in(payload)
            for x, y, address in targets:
                assert address.lower() in known, (keys, address)
```

> If `test_curator_screen` builds its app differently (a named fake manager, a different harness), adapt `_harness_class` and the constructor call to that module's real names **before** Step 2, and say what you adapted. The assertions are the contract; the lookup is not.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_curator_address_icons.py -v`
Expected: FAIL — `assert targets`

- [ ] **Step 3: Convert every curator site** per the recipe and the specifics above.
- [ ] **Step 4: Re-sweep `CURATOR_FULL_LAYOUT_COLUMNS`** per recipe step 6.
- [ ] **Step 5: Run the curator suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_curator_address_icons.py tests/screens/test_curator_screen.py tests/widgets/test_curator_widgets.py tests/test_curator_registration.py -q`
Expected: all pass

- [ ] **Step 6: Prove the tests bite:** recipe step 8, plus: pass `address` instead of `address.lower()` in one leaderboard site, and a "this row is you" test must turn red. Name it.
- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/widgets/curator maxpane_dashboard/data/curator_list_filters.py maxpane_dashboard/screens/curator.py tests/widgets/test_curator_address_icons.py tests/screens/test_curator_screen.py tests/test_curator_registration.py
git commit -m "feat(curator): copy icon beside every address, lower-case spelling kept"
```

---

## Task 4: FWA

**Files:**
- Modify: `widgets/fwa/fwa_activity_feed.py`, `fwa_chase_board.py`, `fwa_hero_metrics.py`, `fwa_odds_board.py`, `fwa_settlement_table.py`; `data/fwa_manager.py:422`; `analytics/fwa_signals.py:374` and `:377`; `__main__.py` (**`FULL_LAYOUT_COLUMNS` and its `#:` block only**)
- Test: `tests/widgets/test_fwa_address_icons.py`

**Interfaces:**
- Consumes: `address_text`, `ICON_COLS` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific to FWA:**
- **Names stand in for addresses** in two places: `fwa_hero_metrics.py:454` (`safe_markup(name[:20]) if name else _short_addr(holder)`) and `fwa_odds_board.py:256` (`r.get("name") or r.get("address")`). Both become `address_text(holder, label=name or None, width=…)`. `name[:20]` counted characters; the helper fits on cells.
- **`data/fwa_manager.py:422`** returns `f"{addr[:6]}…{addr[-4:]}"`. That is the 6/4 form surf's anti-poisoning note warns about. Publish the full address and let the widget window it through the helper (8/6 at 17 cells).
- **`analytics/fwa_signals.py:374/377`** returns `f"0x{text[:4]}..{text[-4:]}"`. Same treatment: full field, widget composes.
- **FWA's accessibility test** (`tests/widgets/test_fwa_accessibility.py::test_no_theme_variable_is_handed_to_a_rich_parsing_surface`) forbids handing a theme variable to Rich. No `style="$…"` on `address_text`.
- **Pin:** `__main__.FULL_LAYOUT_COLUMNS = 143` is FWA's, and `tests/test_cli_font_size.py` pins it in both directions (`_fwa_markers(143) == 0` and `_fwa_markers(142) > 0`). Re-sweep; it must hold.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_fwa_address_icons.py
from tests.screens import test_fwa_screen as T
from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.widgets.address import is_address


def _addresses_in(payload) -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


async def test_fwa_renders_icons_and_every_icon_copies_a_payload_address():
    payload = T._sample_data()
    harness = next(getattr(T, n) for n in dir(T)
                   if isinstance(getattr(T, n), type) and n.endswith("Harness"))

    class _CopyHarness(CopyRecorder, harness):
        pass

    app = _CopyHarness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert targets, "no copy icon on the FWA dashboard"
        known = _addresses_in(payload)
        for x, y, address in targets:
            assert address in known, address
        x, y, address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


def test_a_named_holder_shows_its_name_and_copies_its_address():
    from maxpane_dashboard.widgets.address import address_text, COPY_GLYPH
    holder = "0x" + "12ab34cd56" * 4
    t = address_text(holder, label="whale.eth", width=20)
    assert t.plain == "whale.eth " + COPY_GLYPH
```

> Adapt the harness lookup and the fake-manager name to `tests/screens/test_fwa_screen.py`'s real ones **before** Step 2, and say what you adapted.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_fwa_address_icons.py -v`
Expected: FAIL — `assert targets`

- [ ] **Step 3: Convert every FWA site** per the recipe and the specifics above.
- [ ] **Step 4: Re-sweep `FULL_LAYOUT_COLUMNS = 143`** per recipe step 6.
- [ ] **Step 5: Run the FWA suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_fwa_address_icons.py tests/screens/test_fwa_screen.py tests/widgets/test_fwa_accessibility.py tests/test_fwa_theme.py tests/test_cli_font_size.py tests/data/test_fwa_degradation.py -q`
Expected: all pass

- [ ] **Step 6: Prove the tests bite:** recipe step 8.
- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/widgets/fwa maxpane_dashboard/data/fwa_manager.py maxpane_dashboard/analytics/fwa_signals.py maxpane_dashboard/__main__.py tests/widgets/test_fwa_address_icons.py tests/screens/test_fwa_screen.py
git commit -m "feat(fwa): copy icon beside every address and named holder"
```

---

## Task 5: base

**Files:**
- Modify: `widgets/base/fee_claims.py`, `fee_leaderboard.py`, `graduated.py`, `launch_feed.py`, `overview.py`, `top_movers.py`, `trending_table.py`, `overview/_legacy_overview.py`, `overview/bt_leaderboard.py`, `overview/bt_overview_leaderboard.py`
- Test: `tests/widgets/test_base_address_icons.py`

**Interfaces:**
- Consumes: `address_text`, `short_hex` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific to base:**
- **Token contract addresses** (trending, top movers, launches, graduated) are contract addresses and are in scope.
- **`fee_claims.py` also displays transaction hashes.** Those go through `short_hex`, with no icon.
- **Eight base widgets import `data.base_models`**, legacy debt CLAUDE.md records. Do not touch that; it is not this task.
- **No layout pin exists for base.** Recipe step 6 still applies to each panel's own column budget: a clipped header with no marker is still a defect.

- [ ] **Step 1: Write the failing tests** (widget level; Task 9 adds the screen-level case)

```python
# tests/widgets/test_base_address_icons.py
import importlib
import inspect

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
MODULES = [
    "fee_claims", "fee_leaderboard", "graduated", "launch_feed", "overview",
    "top_movers", "trending_table",
]


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, f"{mod.__name__} defines no widget with update_data"
    return classes[0]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget = widget
        self._payload = payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


@pytest.mark.parametrize("name", MODULES)
async def test_each_base_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.base.{name}")
    widget_cls = _widget_class(mod)
    payload = SEEDED[name]
    app = _WidgetApp(widget_cls(), payload)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert (ADDR in {t[2] for t in icon_targets(app)}), name


#: One payload per widget carrying ADDR where that widget renders an address.
#: Build each from the widget's own existing test in tests/widgets/ (the keys
#: its update_data takes), with ADDR substituted into the address field.
SEEDED: dict[str, dict] = {}
```

> **Fill `SEEDED` before Step 2**, one entry per module, from each widget's real `update_data` keys (its existing tests show the shape). A module you confirm renders no address comes **out** of `MODULES`, and your report says why. An empty `SEEDED` fails with a `KeyError`, which is the point.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_base_address_icons.py -v`
Expected: FAIL — no icon with `ADDR` on each widget

- [ ] **Step 3: Convert every base site** per the recipe; transaction hashes through `short_hex`.
- [ ] **Step 4: Run the base suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_base_address_icons.py tests/widgets -q -k base`
Expected: all pass

- [ ] **Step 5: Prove the tests bite:** recipe step 8, plus: in `fee_claims.py`, route a transaction hash through `address_text`, and a test must show a hash with no icon. Add that test if none exists.
- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/base tests/widgets/test_base_address_icons.py
git commit -m "feat(base): copy icon beside every wallet and token address"
```

---

## Task 6: cattown and talismans

**Files:**
- Modify: `widgets/cattown/ct_activity_feed.py`, `ct_hero_metrics.py`, `ct_leaderboard.py`; `widgets/talismans/tal_leaderboard.py`
- Test: `tests/widgets/test_cattown_talismans_address_icons.py`

**Interfaces:**
- Consumes: `address_text` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific here:**
- **Names stand in for addresses** in all three cattown sites:
  - `ct_activity_feed.py:43`: `display_name if display_name else _short_addr(catch.get("fisher_address", ""))`
  - `ct_leaderboard.py:72`: the same shape on `fisher_address`
  - `ct_hero_metrics.py:149`: `display_name if display_name else addr`, where the address was shown whole
  - Each becomes `address_text(address, label=display_name or None, width=…)`.
- `tal_leaderboard.py` has its own `_short_addr(addr)`; delete it.
- **No layout pin exists** for either dashboard; recipe step 6 applies to the panel budgets.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_cattown_talismans_address_icons.py
import importlib
import inspect

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["cattown.ct_activity_feed", "cattown.ct_hero_metrics", "cattown.ct_leaderboard",
         "talismans.tal_leaderboard"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, mod.__name__
    return classes[0]


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("with_name", [False, True], ids=["address", "named"])
async def test_the_icon_appears_with_or_without_a_display_name(name, with_name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.{name}")
    payload = SEEDED[name](with_name)
    app = _WidgetApp(_widget_class(mod)(), payload)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}, (name, with_name)


#: name -> callable(with_name) -> update_data kwargs, with ADDR as the address
#: and, when with_name is True, "whiskers" as the display name. Build each from
#: that widget's existing tests.
SEEDED: dict = {}
```

> **Fill `SEEDED` before Step 2** from each widget's real `update_data` keys. The `named` case is the owner's decision in PRD §1: a name shown instead of an address still gets the icon.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_cattown_talismans_address_icons.py -v`
Expected: FAIL

- [ ] **Step 3: Convert every site** per the recipe.
- [ ] **Step 4: Run the suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_cattown_talismans_address_icons.py tests/screens/test_talismans_screen.py tests/widgets -q -k "cattown or ct_ or talismans or tal_"`
Expected: all pass

- [ ] **Step 5: Prove the tests bite:** recipe step 8, plus: restore `display_name if display_name else …` without an icon in one cattown site, and the `named` case for that site must turn red.
- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/cattown maxpane_dashboard/widgets/talismans tests/widgets/test_cattown_talismans_address_icons.py
git commit -m "feat(cattown, talismans): copy icon beside every address and named fisher"
```

---

## Task 7: TTT

**Files:**
- Modify: `widgets/ttt/ttt_activity_feed.py`, `ttt_claims_table.py`, `ttt_fees_table.py`, `ttt_leaderboard.py`
- Test: `tests/widgets/test_ttt_address_icons.py`

**Interfaces:**
- Consumes: `address_text`, `short_hex` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: nothing other tasks consume.

**What is specific to TTT:** a claims table and a fees table are `DataTable`s, so icons live in cells. No layout pin exists; recipe step 6 applies to the table column budgets. A table header that loses characters has no ellipsis, which the terminal-layout skill warns about, so measure the header with the icon's two cells added.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_ttt_address_icons.py
import importlib
import inspect

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["ttt_activity_feed", "ttt_claims_table", "ttt_fees_table", "ttt_leaderboard"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, mod.__name__
    return classes[0]


@pytest.mark.parametrize("name", CASES)
async def test_each_ttt_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.ttt.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}, name
        x, y, _ = next(t for t in targets if t[2] == ADDR)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]


#: name -> update_data kwargs carrying ADDR, built from that widget's existing tests.
SEEDED: dict[str, dict] = {}
```

> **Fill `SEEDED` before Step 2.**

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_ttt_address_icons.py -v`
Expected: FAIL

- [ ] **Step 3: Convert every TTT site** per the recipe.
- [ ] **Step 4: Run the suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_ttt_address_icons.py tests/widgets -q -k ttt`
Expected: all pass

- [ ] **Step 5: Prove the tests bite:** recipe step 8.
- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/ttt tests/widgets/test_ttt_address_icons.py
git commit -m "feat(ttt): copy icon beside every address"
```

---

## Task 8: hidden dashboards, shared widgets, and the templates

**Files:**
- Modify: `widgets/ocm/ocm_activity_feed.py`; `widgets/frenpet/overview/fp_overview_leaderboard.py`, `sniper_queue.py`, `top_leaderboard.py`; `screens/frenpet_full.py`, `screens/frenpet_perf.py`, `screens/frenpet_wallet.py` (each defines `_short_addr`); `widgets/activity_feed.py`, `widgets/leaderboard.py` (shared, used by bakery); `templates/activity_feed_template.py`, `templates/leaderboard_template.py`
- Confirm: DOTA has no address sites (`widgets/dota/*`, `screens/dota.py`). If it has any, convert them and say so.
- Test: `tests/widgets/test_hidden_shared_address_icons.py`

**Interfaces:**
- Consumes: `address_text` (Task 0); `icon_targets`, `CopyRecorder` (Task 1).
- Produces: templates that every future dashboard is copied from.

**What is specific here:**
- **The two templates are copy-sources.** Each imports the helper, drops its `_short_addr`, uses `address_text(address, label=name or None, width=…)` where it shows `name or _short_addr(address)` (`leaderboard_template.py:89`, `activity_feed_template.py:92`), and says in its docstring:

```
Every displayed 0x address -- and every name that stands in for one -- goes
through ``widgets/address.py`` and carries the copy icon. That is a repo rule,
not a style: tests/test_address_rule.py fails on a private address formatter
and tests/screens/test_address_icons_everywhere.py fails on an address that
reaches the screen without its icon. Copy this, keep the import.
```

- **Templates are imported by nothing but tests** (`test_markup_safety`, `test_sparkline_common`, `test_refresh_guard`). Run those three.
- **The shared `widgets/activity_feed.py` and `widgets/leaderboard.py`** render bakery's panels; bakery is hidden but in scope.

- [ ] **Step 1: Write the failing tests**

```python
# tests/widgets/test_hidden_shared_address_icons.py
import ast
import importlib
import inspect
import pathlib

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["ocm.ocm_activity_feed", "frenpet.overview.fp_overview_leaderboard",
         "frenpet.sniper_queue", "frenpet.top_leaderboard", "activity_feed", "leaderboard"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, mod.__name__
    return classes[0]


@pytest.mark.parametrize("name", CASES)
async def test_each_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}, name


@pytest.mark.parametrize("template", ["activity_feed_template", "leaderboard_template"])
def test_each_template_uses_the_helper_and_defines_no_formatter(template):
    path = pathlib.Path(f"maxpane_dashboard/templates/{template}.py")
    tree = ast.parse(path.read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "maxpane_dashboard.widgets.address" in imports, template
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert not {n for n in names if "addr" in n.lower()}, (template, names)
    assert "carries the copy icon" in (ast.get_docstring(tree) or ""), template


#: name -> update_data kwargs carrying ADDR, built from that widget's existing tests.
SEEDED: dict[str, dict] = {}
```

> **Fill `SEEDED` before Step 2.** The frenpet **screens'** `_short_addr` sites are covered by Task 9's sweep; convert them here all the same.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/widgets/test_hidden_shared_address_icons.py -v`
Expected: FAIL

- [ ] **Step 3: Convert every site and both templates** per the recipe.
- [ ] **Step 4: Run the suites**

Run: `.venv/bin/python -m pytest tests/widgets/test_hidden_shared_address_icons.py tests/screens/test_frenpet_screens.py tests/test_markup_safety.py tests/test_sparkline_common.py tests/test_refresh_guard.py -q`
Expected: all pass (locate those three template consumers with `rg -l "templates" tests/` if their paths differ)

- [ ] **Step 5: Prove the tests bite:** recipe step 8, plus: put `_short_addr` back into `leaderboard_template.py`, and `test_each_template_uses_the_helper_and_defines_no_formatter[leaderboard_template]` must turn red.
- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/ocm maxpane_dashboard/widgets/frenpet maxpane_dashboard/screens/frenpet_full.py maxpane_dashboard/screens/frenpet_perf.py maxpane_dashboard/screens/frenpet_wallet.py maxpane_dashboard/widgets/activity_feed.py maxpane_dashboard/widgets/leaderboard.py maxpane_dashboard/templates tests/widgets/test_hidden_shared_address_icons.py
git commit -m "feat: copy icon in hidden dashboards, shared panels and both templates"
```

---

## Task 9: Enforcement — the sweep, the registry, the rule

**Runs after all of Wave 1.** Tests only.

**Files:**
- Create: `tests/address_sweep/__init__.py`, `tests/address_sweep/case.py`, `tests/address_sweep/registry.py`, `tests/address_sweep/builders.py`, `tests/test_address_rule.py`, `tests/screens/test_address_icons_everywhere.py`, `tests/test_address_sweep_registry.py`

**Interfaces:**
- Consumes: every name in the frozen table; the fourteen dashboard screen classes (`screens/{bakery,base_terminal,cattown,curator,dota,frenpet,frenpet_full,frenpet_perf,frenpet_wallet,fwa,ocm,surf,talismans,ttt}.py`). Each takes `(manager, poll_interval, **kwargs)`; always pass `poll_interval=` by keyword, because four of them require it.
- Produces: the enforcement a future dashboard cannot pass without the icon.

- [ ] **Step 1: Write the case type and the registry**

These are two modules, so that importing either one first cannot hit a half-initialised circular
import. A single `registry.py` that defined `SweepCase` and also imported the builders, which import
`SweepCase` back, would only work when the registry happened to be imported first.

```python
# tests/address_sweep/case.py
"""One screen the address sweep renders (PRD §7 E2/E3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.app import App


@dataclass(frozen=True)
class SweepCase:
    #: The screen's name: a GAMES id, or the hidden screen's install name.
    name: str
    #: The screen class this case renders; E3 checks all fourteen are here.
    screen_class: type
    #: Builds a CopyRecorder harness around the real screen with a fake manager.
    build: Callable[[], App]
    #: The payload that harness serves. E2 reads it to tell a wrong-address icon
    #: (one copying an address that appears nowhere in the payload) from a right one.
    payload: Callable[[], dict]
    #: Key sequences that reach each view; () is the default body.
    views: tuple[tuple[str, ...], ...] = ((),)
    #: True when the dashboard shows no address at all (PRD §7 E3).
    address_free: bool = False
    #: Addresses deliberately placed where this dashboard renders them, in every
    #: shape it uses. HAND-LISTED, never derived from the payload: a payload
    #: carries addresses no panel shows (a pool manager, an internal sink), and a
    #: derived list would fail E2 on addresses that were never meant to render.
    seeded: tuple[str, ...] = ()
    #: Widget packages the screen renders from, for the E3 agreement test.
    widget_packages: tuple[str, ...] = ()
```

```python
# tests/address_sweep/registry.py
"""The sweep's cases, in one tuple."""

from tests.address_sweep.builders import CASES

__all__ = ["CASES"]
```

- [ ] **Step 2: Write the builders**

In `tests/address_sweep/builders.py`, build one `SweepCase` per screen class:
- **For the five dashboards with screen test harnesses** (surf, curator, FWA, frenpet, talismans),
  reuse their existing fake manager and payload builder from `tests/screens/test_<dash>_screen.py`,
  wrapped in a `CopyRecorder` harness.
- **For the six without** (base, cattown, TTT, OCM, DOTA, bakery), write a minimal fake manager
  exposing `fetch_and_compute` (returning the payload), `close` and `_error_count`, plus whatever else
  that screen reads on mount. Surf's `_FakeManager` shows the first three are the minimum.
- **For every address-rendering case**, render it once with `icon_targets`, confirm which addresses
  actually reach the screen, and list at least one per shape that dashboard uses (full, shortened,
  name-backed, prose) in its `*_SEEDED` tuple, with the panel it renders in as a comment. Seed an
  address into the payload wherever a shape the dashboard uses has none.

The surf case, as the worked example:

```python
# tests/address_sweep/builders.py
from __future__ import annotations

from textual.app import App

from maxpane_dashboard.screens.surf import SurfScreen
from tests.address_sweep.case import SweepCase
from tests.screens.test_surf_screen import _FakeManager, _ThemedHarness, _mainnet_pool4_payload
from tests.widgets.address_probe import CopyRecorder


class _CopyHarness(CopyRecorder, _ThemedHarness):
    pass


def _surf() -> App:
    return _CopyHarness(SurfScreen(_FakeManager(_mainnet_pool4_payload()), poll_interval=30, name="surf"))


#: Addresses surf is confirmed to render, at least one per shape it uses, each
#: confirmed with icon_targets and commented with its panel. Empty fails E3.
SURF_SEEDED: tuple[str, ...] = ()


CASES = (
    SweepCase(
        name="surf",
        screen_class=SurfScreen,
        build=_surf,
        payload=_mainnet_pool4_payload,
        views=((), ("l",), ("p",), ("4",)),
        seeded=SURF_SEEDED,
        widget_packages=("maxpane_dashboard.widgets.surf",),
    ),
    # curator, fwa, frenpet, frenpet_full, frenpet_perf, frenpet_wallet, talismans,
    # base_terminal, cattown, ttt, ocm, dota, bakery: one SweepCase each, same fields.
)
```

> **Write all fourteen cases, and fill every `*_SEEDED` tuple, before Step 3.** An empty seed tuple on
> an address-rendering case fails E3's `test_an_address_rendering_case_seeds_at_least_one_address`.
> That is the point: a case cannot pass the sweep by seeding nothing. DOTA is expected to be
> `address_free=True`; confirm it.

- [ ] **Step 3: Write E2, the composited sweep**

Two different sets, each asking a different question. **Every icon** must copy an address the
payload actually holds, or it is a wrong-address icon. **Every seeded address** must get an icon in
some view, or a panel dropped one. A single set cannot answer both: all payload addresses would fail
on addresses no panel shows, and the seeds alone would miss a wrong-address icon on an unseeded row.

```python
# tests/screens/test_address_icons_everywhere.py
"""E2: every address that reaches the screen carries an icon that copies it."""

import pytest
from rich.cells import cell_len

from maxpane_dashboard.widgets.address import PROSE_ADDRESS_RE, is_address
from tests.address_sweep.registry import CASES
from tests.widgets.address_probe import icon_targets


def _rows(app) -> list[str]:
    return ["".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips()]


def _addresses_in(value) -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v.lower())
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    return found


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_every_rendered_address_carries_an_icon_that_copies_it(case):
    in_payload = _addresses_in(case.payload())
    seeded = {a.lower() for a in case.seeded}
    assert seeded <= in_payload, (case.name, "a seeded address is not in the payload", seeded - in_payload)
    copied_somewhere: set[str] = set()

    for keys in case.views:
        app = case.build()
        async with app.run_test(size=(170, 60)) as pilot:
            for key in keys:
                await pilot.press(key)
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
```

- [ ] **Step 4: Write E1 and the E5 source check**

```python
# tests/test_address_rule.py
"""E1: one address formatter in the whole app. E5: one clipboard module."""

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
        if path == HELPER or not path.parts[1] in {"widgets", "screens", "data", "analytics"}:
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
```

- [ ] **Step 5: Write E3**

```python
# tests/test_address_sweep_registry.py
"""E3: nothing can hide from the sweep."""

import ast
import importlib
import pathlib
import pkgutil

from maxpane_dashboard.screens.game_select import GAMES
from tests.address_sweep.registry import CASES

SCREENS = pathlib.Path("maxpane_dashboard/screens")


def _status_bar_screen_classes() -> set[str]:
    """Screen classes whose module composes a StatusBar: the dashboards and hidden ones."""
    names = set()
    for path in SCREENS.glob("*.py"):
        src = path.read_text()
        if "yield StatusBar" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Screen"):
                names.add(node.name)
    return names


def test_every_dashboard_screen_has_a_sweep_case():
    registered = {c.screen_class.__name__ for c in CASES}
    assert registered == _status_bar_screen_classes(), (
        "a screen composes a StatusBar with no SweepCase, or a case names a screen that is gone")


def test_every_games_entry_is_covered():
    names = {c.name for c in CASES}
    missing = [g for g in GAMES if (g if isinstance(g, str) else getattr(g, "id", str(g))) not in names]
    assert not missing, missing


def test_an_address_rendering_case_seeds_at_least_one_address():
    empty = [c.name for c in CASES if not c.address_free and not c.seeded]
    assert not empty, empty


def test_a_dashboard_whose_widgets_use_the_helper_cannot_be_address_free():
    wrong = []
    for case in CASES:
        if not case.address_free:
            continue
        for package in case.widget_packages:
            pkg = importlib.import_module(package)
            for mod in pkgutil.walk_packages(pkg.__path__, prefix=package + "."):
                src = pathlib.Path(importlib.import_module(mod.name).__file__).read_text()
                if "maxpane_dashboard.widgets.address" in src:
                    wrong.append((case.name, mod.name))
    assert not wrong, wrong
```

> `GAMES` entries may be tuples or objects rather than strings. Read `screens/game_select.py` and make `test_every_games_entry_is_covered` extract the real id **before** Step 6; the assertion is the contract. Likewise, if a status-bar screen module defines a helper class whose name also ends in `Screen`, narrow `_status_bar_screen_classes` to the class that actually composes the `StatusBar`, rather than listing the helper as a dashboard.

- [ ] **Step 6: Run and watch them pass**

Run: `.venv/bin/python -m pytest tests/screens/test_address_icons_everywhere.py tests/test_address_rule.py tests/test_address_sweep_registry.py -v`
Expected: all pass. If E2 finds an address without its icon in a dashboard, **report it against that Wave 1 package and do not fix it here.**

- [ ] **Step 7: Prove the tests bite**

| Mutation | Must turn red |
|---|---|
| re-add `def _short_addr(a): return a[:6]` to `widgets/ttt/ttt_leaderboard.py` | `test_no_module_but_the_helper_defines_an_address_formatter` |
| in one surf widget, `address_text(...)` → `Text(address)` | `test_every_rendered_address_carries_an_icon_that_copies_it[surf]` |
| make one icon copy `ADDR[::-1]`-shaped wrong address | `test_every_rendered_address_carries_an_icon_that_copies_it` for that case |
| delete the DOTA case from `builders.py` | `test_every_dashboard_screen_has_a_sweep_case` |
| mark surf `address_free=True` | `test_a_dashboard_whose_widgets_use_the_helper_cannot_be_address_free` |
| add `"pbcopy"` to a comment in `app.py` | `test_only_the_clipboard_module_names_a_clipboard_tool` |

- [ ] **Step 8: Commit**

```bash
git add tests/address_sweep tests/test_address_rule.py tests/screens/test_address_icons_everywhere.py tests/test_address_sweep_registry.py
git commit -m "test: enforce the copy icon on every address in every dashboard"
```

---

## Task 10: Docs and the full suite

**Last.** Sole owner of `CLAUDE.md`, `README.md`, `.claude/skills/terminal-layout/SKILL.md`, `docs/address_copy_PRD.md`.

- [ ] **Step 1: CLAUDE.md, a new Conventions entry** (after "Escape every third-party string…")

```markdown
**Every displayed 0x address carries a copy icon, and so does every name that stands in for one.**
Render addresses only through `widgets/address.py`: `address_text` for an address or a name backed
by one, `address_prose` for third-party text that may contain addresses, `short_hex` for any other
hex such as a transaction hash (no icon). The icon is `⧉` with a Textual `@click` action on the glyph
only, calling `app.copy_address`, which `copy_action.CopyAddressMixin` runs through
`maxpane_dashboard/clipboard.py`: native tool first (`pbcopy`; Apple Terminal ignores the OSC 52 that
`App.copy_to_clipboard` writes), OSC 52 second, and the status bar says `copied`, `unconfirmed` or
`unavailable`, whichever is true. Validation is `fullmatch`, never `^…$`, because `$` accepts a
trailing newline and the address is interpolated into an action string. The icon costs
`ICON_COLS = 2`; a panel grows where it has slack and shortens its displayed address where a pin
would move, and the window rule (8/6 at 17 cells) is surf's anti-poisoning form. **None of this is
optional**: `tests/test_address_rule.py` fails on a private address formatter,
`tests/screens/test_address_icons_everywhere.py` fails on an address that reaches the screen
without its icon, and `tests/test_address_sweep_registry.py` fails on a dashboard the sweep does not
render. No test may reach the real clipboard: `tests/conftest.py` replaces the runner suite-wide.
```

- [ ] **Step 2: terminal-layout SKILL.md.** Under "Measuring and fitting text", add:

```markdown
* **An address costs `widgets/address.ICON_COLS` more than its text.** Every displayed 0x address
  carries a copy icon. Where adding it would move a pin, the displayed address gives up the two
  cells instead (`short_address`, window rule 8/6 at 17 cells), and the trade is recorded in the
  pin's `#:` block together with its anti-poisoning cost.
```

- [ ] **Step 3: README.** Under the keys and interaction section, add one line: `Click ⧉ beside any address to copy it.`

- [ ] **Step 4: The PRD status line.** In `docs/address_copy_PRD.md`, change `**Status:** design approved 2026-09-14, not yet planned or built.` to `**Status:** built; enforced by tests/test_address_rule.py, tests/screens/test_address_icons_everywhere.py and tests/test_address_sweep_registry.py.`

- [ ] **Step 5: The full suite, as the merge gate**

Run: `.venv/bin/python -m pytest`
Expected: green, about 25 minutes. Do not background it. Report the exact summary line. Failures in another package's files are findings, not repairs.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md .claude/skills/terminal-layout/SKILL.md docs/address_copy_PRD.md
git commit -m "docs: the copy icon is a repo rule, and the tests that make it one"
```

---

## Self-review

**Spec coverage**

| PRD section | Implemented by |
|---|---|
| §1 rule, icon, names, prose, tx hashes excluded, hidden dashboards | Tasks 0, 2–8; tx hashes via `short_hex` |
| §2 measured facts | Global Constraints; the surf-feed guard in Task 2; the cursor note in Task 3 |
| §3.1 validation, `fullmatch` (AMENDED) | Task 0 `ADDRESS_RE` and its injection test |
| §3.2 `address_text`, `short_address`, window rule (AMENDED), case preserved | Task 0; curator lower-casing in Task 3 |
| §3.3 prose with hex boundaries | Task 0 `PROSE_ADDRESS_RE`; used in Task 2 |
| §3.4 click guard | Task 0 `is_copy_click`; used in Task 2 `feed.py` |
| §4 native then OSC 52, honest messages, ownership-safe clear, never reads | Task 1 |
| §5 per-panel width, pins held, trades recorded | Recipe step 6; the pins named in Tasks 2, 3, 4 |
| §6 pre-shortened data | Tasks 2 (`surf_signals`), 3 (`curator_list_filters`), 4 (`fwa_manager`, `fwa_signals`) |
| §7 E1 | Task 9 `test_address_rule.py` |
| §7 E2 | Task 9 `test_address_icons_everywhere.py` |
| §7 E3 | Task 9 `test_address_sweep_registry.py` |
| §7 E4 | Task 0 validation tests; Task 1 invalid-address action test |
| §7 E5 | Task 1 `tests/conftest.py`; Task 9 tool-name source test |
| §7 E6 | Task 1 message and ownership tests |
| §8 templates and docs | Task 8 templates; Task 10 docs |
| §9 candidate modules | Tasks 2–8 file lists |
| §10 work packages | Wave order; Tasks 0–10 |
| §11 consequences | Task 3 (cursor), Task 1 (unconfirmed), recipe step 6 (trades), Task 9 (DOTA address-free) |
| §12 won't do | Global Constraints |

**Type consistency.** Every task uses the frozen names: `address_text(address, *, label=None, width=None, style="")`, `short_address(address, width)`, `short_hex(value, width)`, `copy_action(address)`, `is_copy_click(event)`, `COPY_GLYPH`, `ICON_COLS`, `MIN_SHORT_COLS`; `clipboard.copy_text(text, *, osc52, runner=None, which, platform)` returning one of `COPIED` / `UNCONFIRMED` / `UNAVAILABLE`; `clipboard.copy_message(outcome, address)`; `CopyAddressMixin.action_copy_address(address)`; `StatusBar.message`; `icon_targets(app) -> list[(x, y, address | None)]`; `CopyRecorder.copied`. The action string is `app.copy_address('0x…')` in `copy_action`, in `is_copy_click`'s prefix, and in `icon_targets`' pattern.

**Deliberate adaptation points.** Tasks 3, 4 and 9 look up an existing harness class or `GAMES` id shape they cannot know from here, and Tasks 5–8 fill `SEEDED` from each widget's real `update_data` keys. Each is marked **before Step 2**, with the assertion fixed as the contract, so an agent adapts the lookup, never the claim.
