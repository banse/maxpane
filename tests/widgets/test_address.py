import ast
import pathlib

import pytest

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets import address as A
from maxpane_dashboard.widgets import explorer as X

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


# -- explorer links (refactor programme 2026-09, Branch 4 WP-A) -------------------------


_COPY = Style(meta={"@click": f"app.copy_address('{ADDR}')"})


def _spans(text: Text) -> list[tuple[int, int, Style | str]]:
    return [(s.start, s.end, s.style) for s in text.spans]


def _links(text: Text) -> list[tuple[str, str, tuple]]:
    """(covered text, OSC 8 link, parsed open action) for every span carrying either."""
    out = []
    for span in text.spans:
        if not isinstance(span.style, Style):
            continue
        parsed = X.parse_open_action(span.style.meta.get("@click"))
        if span.style.link or parsed:
            out.append((text.plain[span.start:span.end], span.style.link, parsed))
    return out


def test_explorer_none_renders_byte_and_style_identically_to_before_the_links():
    """The literals were computed from ``git show 307255a:…/address.py`` (the
    module before ``explorer=`` existed) and pasted; ``Text.__eq__`` compares
    plain, base style and spans."""
    full = Text("0xabcdef0123abcdef0123abcdef0123abcdef0123 ⧉")
    full.stylize(_COPY, 43, 44)
    assert A.address_text(ADDR) == full
    assert _spans(A.address_text(ADDR)) == [(43, 44, _COPY)]

    window = Text("0xabcdef01…ef0123 ⧉", style="bold")
    window.stylize(_COPY, 18, 19)
    assert A.address_text(ADDR, width=17, style="bold") == window
    assert _spans(A.address_text(ADDR, width=17, style="bold")) == [(18, 19, _COPY)]

    label = Text("vitalik… ⧉")
    label.stylize(_COPY, 9, 10)
    assert A.address_text(ADDR, label="vitalik.eth", width=8) == label
    assert _spans(A.address_text(ADDR, label="vitalik.eth", width=8)) == [(9, 10, _COPY)]

    invalid = Text("0xabcdef0123abcd…")
    assert A.address_text(ADDR + "\n", width=17) == invalid
    assert _spans(A.address_text(ADDR + "\n", width=17)) == []

    prose = Text(
        "sent to 0xabcdef0123abcdef0123abcdef0123abcdef0123 ⧉, tx "
        "0xabababababababababababababababababababababababababababababababab and "
        "(0xabcdef0123abcdef0123abcdef0123abcdef0123 ⧉)",
        style="dim",
    )
    prose.stylize(_COPY, 51, 52)
    prose.stylize(_COPY, 172, 173)
    got = A.address_prose(f"sent to {ADDR}, tx {TX} and ({ADDR})", style="dim")
    assert got == prose
    assert _spans(got) == [(51, 52, _COPY), (172, 173, _COPY)]
    assert got.style == "dim"


def test_the_link_is_on_the_shown_span_only_and_the_glyph_keeps_the_copy_action():
    t = A.address_text(ADDR, width=17, explorer=X.ETHEREUM)
    assert t.plain == A.short_address(ADDR, 17) + " " + A.COPY_GLYPH
    url = X.address_url(X.ETHEREUM, ADDR)
    assert _links(t) == [(A.short_address(ADDR, 17), url, (X.ETHEREUM, "address", ADDR))]
    assert _actions(t) == [
        (A.short_address(ADDR, 17), X.open_action(X.ETHEREUM, "address", ADDR)),
        (A.COPY_GLYPH, A.copy_action(ADDR)),
    ]
    assert t.spans[0].end == len(A.short_address(ADDR, 17)), "the separating space is not linked"


def test_the_link_sits_on_top_of_the_callers_style():
    t = A.address_text(ADDR, explorer=X.BASE, style="bold")
    assert t.style == "bold"
    assert t.spans[0].style == Style(
        link=X.address_url(X.BASE, ADDR), meta={"@click": X.open_action(X.BASE, "address", ADDR)}
    )
    assert t.spans[0].style.bold is None, "the span adds the link, it does not restate the style"


def test_window_and_label_forms_link_the_full_address():
    url = X.address_url(X.SEPOLIA, ADDR)
    for kwargs in ({"width": 11}, {"width": 17}, {"label": "vitalik.eth"}, {"label": "名前名前", "width": 5}):
        t = A.address_text(ADDR, explorer=X.SEPOLIA, **kwargs)
        [(shown, link, parsed)] = _links(t)
        assert shown == t.plain[: -A.ICON_COLS], kwargs
        assert link == url and parsed == (X.SEPOLIA, "address", ADDR), kwargs


def test_an_invalid_address_gets_neither_link_nor_icon_with_an_explorer():
    for bad in (ADDR + "\n", "0xdead')", "", None, "vitalik.eth", TX):
        t = A.address_text(bad, explorer=X.ETHEREUM)
        assert A.COPY_GLYPH not in t.plain, repr(bad)
        assert _links(t) == [] and _actions(t) == [], repr(bad)
        assert A.address_text(bad, explorer=X.ETHEREUM) == A.address_text(bad), repr(bad)


def test_prose_links_each_whole_address_and_never_a_transaction_hash():
    t = A.address_prose(f"sent to {ADDR}, tx {TX} and ({ADDR})", explorer=X.ETHEREUM)
    url = X.address_url(X.ETHEREUM, ADDR)
    assert _links(t) == [(ADDR, url, (X.ETHEREUM, "address", ADDR))] * 2
    assert [a for a, _ in _actions(t) if a == A.COPY_GLYPH] == [A.COPY_GLYPH] * 2
    assert t.plain == A.address_prose(f"sent to {ADDR}, tx {TX} and ({ADDR})").plain
    for span in t.spans:
        assert TX not in t.plain[span.start:span.end], "a hash span is never linked"


def test_hash_text_windows_through_short_hex_and_links_the_tx_page():
    plain = A.hash_text(TX, 17)
    assert plain == Text(A.short_hex(TX, 17))
    assert plain.plain == "0x" + TX[2:10] + "…" + TX[-6:]
    assert A.COPY_GLYPH not in plain.plain and _spans(plain) == []

    linked = A.hash_text(TX, 17, explorer=X.BASE, style="dim")
    assert linked.plain == plain.plain and linked.style == "dim"
    assert _links(linked) == [(plain.plain, X.tx_url(X.BASE, TX), (X.BASE, "tx", TX))]
    assert A.COPY_GLYPH not in linked.plain, "a hash never gets a copy icon"

    whole = A.hash_text(TX, 80, explorer=X.ETHEREUM)
    assert whole.plain == TX and _links(whole)[0][1] == X.tx_url(X.ETHEREUM, TX)


def test_hash_text_links_only_a_32_byte_hash_and_tolerates_junk():
    for not_a_tx in (ADDR, "0x" + "ab" * 31, "0x" + "ab" * 33, TX + "\n"):
        t = A.hash_text(not_a_tx, 17, explorer=X.ETHEREUM)
        assert _links(t) == [] and _spans(t) == [], repr(not_a_tx)
        assert t.plain == A.short_hex(not_a_tx, 17)
    for junk in (None, "", 12, b"x"):
        t = A.hash_text(junk, 17, explorer=X.ETHEREUM)
        assert t.plain == "--" and _spans(t) == [], repr(junk)
    assert A.hash_text("not hex", 17).plain == "not hex"


def test_is_explorer_click_only_for_linked_spans():
    assert A.is_explorer_click(_Evt({"@click": X.open_action(X.ETHEREUM, "address", ADDR)}))
    assert A.is_explorer_click(_Evt({"@click": X.open_action(X.BASE, "tx", TX)}))
    assert not A.is_explorer_click(_Evt({"@click": A.copy_action(ADDR)}))
    assert not A.is_copy_click(_Evt({"@click": X.open_action(X.ETHEREUM, "address", ADDR)}))
    assert not A.is_explorer_click(_Evt({"@click": X.open_action(X.ETHEREUM, "address", ADDR) + "x"}))
    assert not A.is_explorer_click(_Evt({"@click": "app.toggle()"}))
    assert not A.is_explorer_click(_Evt({}))
    assert not A.is_explorer_click(_Evt({"@click": 12}))
    assert not A.is_explorer_click(object())


def test_the_helper_reaches_only_the_explorer_module_beyond_rich():
    tree = ast.parse(pathlib.Path(A.__file__).read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    assert {m for m in modules if m.startswith("maxpane_dashboard")} == {"maxpane_dashboard.widgets.explorer"}


def test_a_forged_explorer_gets_no_link_and_never_a_crash():
    """Review of WP-A, Minor 1: ``url_for`` used to build a usable URL for any
    ``Explorer`` and only ``open_action`` raised -- inside the widget's render.
    Now the URL helpers refuse anything outside the allowlist and the address
    helpers degrade to an unlinked address (the icon still copies)."""
    forged = X.Explorer("blockscout", "https://evil.example")
    with pytest.raises(ValueError):
        X.address_url(forged, ADDR)
    with pytest.raises(ValueError):
        X.tx_url(forged, TX)
    same_name = X.Explorer("etherscan", "https://evil.example")
    with pytest.raises(ValueError):
        X.address_url(same_name, ADDR)
    for explorer in (forged, same_name):
        t = A.address_text(ADDR, explorer=explorer)
        assert _links(t) == [], explorer          # no link ...
        assert t == A.address_text(ADDR, explorer=None)   # ... and the icon still copies
        p = A.address_prose(f"from {ADDR} to", explorer=explorer)
        assert p == A.address_prose(f"from {ADDR} to", explorer=None)
        h = A.hash_text(TX, 17, explorer=explorer)
        assert _links(h) == [] and h.plain == A.short_hex(TX, 17)
