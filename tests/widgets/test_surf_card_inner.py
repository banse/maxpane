"""Pure shared inset colors and cell-aware rich text padding."""
import pytest
from rich.console import Console
from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.card_inner import inner_styles, padded_inner_row
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.oracles import _OracleCard
from maxpane_dashboard.widgets.surf.work import _WorkHeroCard


@pytest.mark.parametrize("active", [False, True])
def test_palette_separates_labels_values_and_active_digits(active):
    label, value, digit = inner_styles({"foreground": "#55bb44", "background": "#112233"}, active=active, text_color="#eeeeee")
    assert label == Style(color="green", bgcolor="#112233", dim=False)
    assert value == Style(color="#55bb44", bgcolor="#112233", dim=False)
    assert digit == (label if active else Style(color="#eeeeee", bgcolor="#112233", dim=False))


@pytest.mark.parametrize("inside", [0, 1, 2, 5, 12])
def test_padding_keeps_edge_cells_and_preserves_literal_rich_content(inside):
    original = Text("中[/x] address", style=Style(link="https://example.com"))
    original.stylize(Style(meta={"@click": "copy_address('full')"}), 0, 1)
    fitted = padded_inner_row(original, inside)
    assert original.plain == "中[/x] address"
    assert fitted.cell_len == inside
    if inside >= 2:
        assert fitted.plain.startswith(" ") and fitted.plain.endswith(" ")
    if inside >= 5:
        style = fitted.get_style_at_offset(Console(), 1)
        assert style.link == "https://example.com"
        assert style.meta["@click"] == "copy_address('full')"


def test_padding_centers_compact_faces_inside_the_reserved_edges():
    assert padded_inner_row(Text("123"), 10, align="center").plain == "   123    "


class CardHarness(App):
    CSS = "Screen { background: $background; color: $text; } NewsHeroCard { width: 24; }"

    def __init__(self, card_type, record):
        super().__init__()
        self.card_type, self.record = card_type, record
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield self.card_type(self.record)


@pytest.mark.parametrize("card_type,key,accent,frame_color,bright", [
    (NewsHeroCard, "ordinary", True, "accent", True),
    (NewsHeroCard, "ordinary", False, None, False),
    (_WorkHeroCard, "work-blocked", True, "red", False),
    (_OracleCard, "oracle-assessing", True, "yellow", False),
    (_OracleCard, "oracle-attested", True, "green", True),
    (_OracleCard, "oracle-blocked", True, "red", False),
])
@pytest.mark.parametrize("digits", ["7", "1.23e+14"])
async def test_composited_readout_uses_final_frame_and_pads_only_text(
        monkeypatch, card_type, key, accent, frame_color, bright, digits):
    monkeypatch.delenv("NO_COLOR", raising=False)
    record = HeroRecord(key, "CARD", "HEADING", "FOOTER", digits=digits, accent=accent, subtitle="SUBTITLE")
    async with CardHarness(card_type, record).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        app, card = pilot.app, pilot.app.query_one(NewsHeroCard)
        rows = [strip.crop(card.region.x, card.region.right).text for strip in
                app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
        top = next(index for index, row in enumerate(rows) if "┌" in row)
        left, right = rows[top].index("┌"), rows[top].index("┐")
        frame = app.screen.get_style_at(card.region.x + left, card.region.y + top)
        if frame_color is not None:
            expected = app.get_css_variables()["accent"] if frame_color == "accent" else frame_color
            assert frame.color.get_truecolor(app.ansi_theme) == Color.parse(expected).get_truecolor(app.ansi_theme)
        digit_color = (app.ansi_theme.ansi_colors[3] if frame_color == "red" else
                       app.ansi_theme.ansi_colors[2] if bright else
                       card.rich_style.color.get_truecolor() if frame_color is None else
                       Color.parse(app.get_css_variables()["foreground"]).get_truecolor())
        for index, row in enumerate(rows[top + 1:top + 4], top + 1):
            if "e" in digits:
                assert row[left + 1] == row[right - 1] == " "
            for x in range(left + 1, right):
                if row[x].isspace():
                    continue
                style = app.screen.get_style_at(card.region.x + x, card.region.y + index)
                assert style.color.get_truecolor() == digit_color and not style.dim
        for y, caption in ((top, "HEADING"), (top + 4, "SUBTITLE")):
            x = rows[y].index(caption)
            style = app.screen.get_style_at(card.region.x + x, card.region.y + y)
            assert style.color == frame.color
