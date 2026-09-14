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


# -- label hardening (final review F2) ------------------------------------------


def test_a_non_string_label_is_ignored_and_never_raises():
    for bad in (123, 4.5, b"bytes", ["list"], object()):
        t = A.address_text(ADDR, label=bad, width=17)
        assert t.plain == A.short_address(ADDR, 17) + " " + A.COPY_GLYPH, bad
        assert _actions(t) == [(A.COPY_GLYPH, A.copy_action(ADDR))]


def test_a_label_cannot_break_or_stretch_its_row():
    t = A.address_text(ADDR, label="whale\n.eth\tis\r\n  here")
    assert t.plain == "whale .eth is here " + A.COPY_GLYPH
    assert "\n" not in t.plain and "\t" not in t.plain and "\r" not in t.plain
    assert A.address_text(ADDR, label="a b\xa0c").plain == "a b c " + A.COPY_GLYPH


def test_a_label_cannot_paint_a_second_icon():
    for spoof in ("x ⧉", "⧉x", "x⧉⧉y"):
        t = A.address_text(ADDR, label=spoof)
        assert t.plain.count(A.COPY_GLYPH) == 1, (spoof, t.plain)
        assert t.plain.endswith(" " + A.COPY_GLYPH)
        assert _actions(t) == [(A.COPY_GLYPH, A.copy_action(ADDR))]


def test_a_label_emptied_by_hardening_falls_back_to_the_address():
    for empty in (" \n\t ", "⧉", " ⧉ "):
        assert A.address_text(ADDR, label=empty, width=17).plain == A.short_address(ADDR, 17) + " " + A.COPY_GLYPH


def test_an_invalid_value_cannot_break_its_row_or_fake_an_icon():
    t = A.address_text("not\nan ⧉ address")
    assert t.plain == "not an address"
    assert _actions(t) == []


# -- the one copy-action parser (final review F4) ----------------------------------


def test_parse_copy_action_is_the_inverse_of_copy_action():
    assert A.parse_copy_action(A.copy_action(ADDR)) == ADDR
    mixed = "0x" + "AbCdEf0123" * 4
    assert A.parse_copy_action(A.copy_action(mixed)) == mixed


def test_parse_copy_action_refuses_invalid_hex_and_trailing_junk():
    good = A.copy_action(ADDR)
    for bad in (
        good.replace("a", "g", 1),             # not hex
        A.copy_action(ADDR[:-1]),              # 39 hex
        good + " ",                            # trailing junk
        good + "; app.quit()",
        good[:-1],                             # no closing parenthesis
        good.replace("'", '"'),                # not what copy_action writes
        "x" + good,                            # leading junk
        "app.copy_address()",
        "app.toggle()",
        "",
    ):
        assert A.parse_copy_action(bad) is None, bad


def test_parse_copy_action_tolerates_non_strings_and_str_styled_spans():
    for value in (None, 5, b"app.copy_address('0x')", ["x"], object()):
        assert A.parse_copy_action(value) is None
    text = Text("name", style="bold")
    text.append(" ")
    text.append_text(A.address_text(ADDR))
    text.stylize("italic", 0, 2)               # a span whose style is a plain str
    found = [
        A.parse_copy_action((getattr(span.style, "meta", None) or {}).get("@click"))
        for span in text.spans
    ]
    assert [f for f in found if f] == [ADDR]
    assert any(isinstance(span.style, str) for span in text.spans), "fixture sanity"


def test_is_copy_click_uses_the_parser_and_tolerates_odd_meta():
    assert not A.is_copy_click(_Evt({"@click": A.copy_action(ADDR) + "x"}))
    assert not A.is_copy_click(_Evt({"@click": 12}))

    class _OddStyle:
        meta = "not a dict"

    class _OddEvt:
        style = _OddStyle()

    assert not A.is_copy_click(_OddEvt())
