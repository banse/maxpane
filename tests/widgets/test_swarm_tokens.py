"""Mock market widgets preserve unknown values, LP states and row identity."""

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.widgets.swarm_tokens import (
    BestPlays, NewlyLaunched, TokenActivity, TokensHero, TokensTable,
)


NOW = 1_800_000_000


def token(**overrides):
    return dict(dict(id="eth-sc", launch_id=1175, symbol="SC", name="Swarm Coin",
        chain="eth", launched_at=NOW - 172800, price_usd=0.0042,
        change_24h=24.8, mcap_usd=420000, volume_24h=82100,
        buys_24h=412, sells_24h=208, paired_amount=788, paired_symbol="IMD",
        lp_state="two-sided", sparkline=[1, 2, 2, 3, 4, 5, 6, 8],
        verdict="swarm", status="live"), **overrides)


class Probe(App):
    CSS = """
    TokensTable { width: 145; height: 22; }
    TokensTable DataTable { height: 1fr; scrollbar-size: 1 1; }
    TokensHero { height: 8; }
    TokensHeroBox { width: 1fr; height: 7; }
    NewlyLaunched, BestPlays, TokenActivity { width: 47; height: 12; }
    RichLog { min-width: 1; height: 1fr; scrollbar-size: 1 1; }
    """

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.selected = []

    def compose(self):
        yield self.widget

    def on_tokens_table_selected(self, message):
        self.selected.append(message.token)


def painted(app):
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


async def test_table_renders_all_columns_unknowns_zero_and_sparse_series():
    table = TokensTable()
    async with Probe(table).run_test(size=(149, 45)) as pilot:
        rows = [token(), token(id="eth-new", symbol="NEW", price_usd=None,
            volume_24h=0, paired_amount=0, lp_state="one-token", sparkline=[1]),
            token(id="rh-unknown", symbol="UNKNOWN", price_usd=0,
                volume_24h=None, paired_amount=None, lp_state="unknown", sparkline=None)]
        table.update_data(tokens=rows, as_of=NOW)
        await pilot.pause()
        output = painted(pilot.app)
        for expected in ("PAIRED LP", "PRICE 24H", "VERDICT", "swarm", "788 IMD", "0 IMD", "▁▂▂▃▄▅▆█"):
            assert expected in output
        assert 'LP STATE' not in output and 'one-token' not in output
        line = next(row for row in output.splitlines() if "NEW" in row)
        assert "$0" in line and "--" in line and "new" in line
        line = next(row for row in output.splitlines() if "UNKNOWN" in row)
        assert "$0" in line and "--" in line
        assert not table.query_one(DataTable).show_horizontal_scrollbar


async def test_selection_survives_reordered_refresh_and_rows_are_not_capped():
    table = TokensTable()
    async with Probe(table).run_test(size=(149, 45)) as pilot:
        rows = [token(id=f"eth-{i}", symbol=f"COIN{i}") for i in range(31)]
        table.update_data(tokens=rows, as_of=NOW)
        native = table.query_one(DataTable)
        native.move_cursor(row=25)
        await pilot.pause()
        assert table.selected_token()["id"] == "eth-25"
        table.update_data(tokens=list(reversed(rows)), as_of=NOW)
        await pilot.pause()
        assert native.row_count == 31
        assert table.selected_token()["id"] == "eth-25"
        native.focus()
        await pilot.press("enter")
        assert pilot.app.selected[-1]["id"] == "eth-25"
        table.update_data(tokens=[], as_of=NOW)
        await pilot.pause()
        assert table.selected_token() is None
        assert "No matching tokens" in painted(pilot.app)


async def test_lp_states_have_distinct_color_and_markup_is_literal():
    panel = NewlyLaunched()
    async with Probe(panel).run_test(size=(149, 45)) as pilot:
        rows = [token(id=state, symbol="[/x]", lp_state=state)
                for state in ("two-sided", "one-token", "one-quote", "withdrawn", "unknown")]
        panel.update_data(newly_launched=rows, as_of=NOW)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        colors = {}
        for state in ("two-sided", "one-token", "one-quote", "withdrawn"):
            colors[state] = next(segment.style.color for strip in strips for segment in strip if state in segment.text)
        assert colors["two-sided"] != colors["one-token"] != colors["withdrawn"]
        assert colors["one-token"] == colors["one-quote"]
        unknown = next(segment for strip in strips for segment in strip if "unknown" in segment.text)
        neutral = unknown.style.color.get_truecolor()
        assert max(neutral) - min(neutral) < 16  # ANSI white may be slightly warm.
        assert "[/x]" in painted(pilot.app)


async def test_hero_distinguishes_empty_from_unknown_coverage():
    hero = TokensHero()
    async with Probe(hero).run_test(size=(149, 45)) as pilot:
        hero.update_data(metrics=dict(total=0, new_24h=0, volume_24h=None,
            volume_known=0, two_sided=0, one_sided=0, unknown=0, other=0))
        await pilot.pause()
        assert "0 deployed" in painted(pilot.app)
        assert "0 launches" in painted(pilot.app)
        assert "$0" not in painted(pilot.app)
        hero.update_data(metrics=dict(total=2, new_24h=1, volume_24h=0,
            volume_known=1, two_sided=1, one_sided=1, unknown=0, other=0))
        await pilot.pause()
        assert "$0" in painted(pilot.app)
        assert "1/2 volumes known" in painted(pilot.app)


@pytest.mark.parametrize("widget,kwargs,expected", [
    (NewlyLaunched, dict(newly_launched=[token(launched_at=NOW - 240)], as_of=NOW), ("4m", "SC", "ETH", "two-sided")),
    (BestPlays, dict(gainers=[token()], losers=[token(symbol="FROG", chain="rh", change_24h=-10.6)]), ("GAINERS", "LOSERS", "+24.8%", "-10.6%", "RH")),
    (TokenActivity, dict(activity=[dict(ts=NOW, kind="BUY", token_id="eth-sc", amount=42.6, asset="IMD")], tokens=[token()]), ("BUY", "ETH", "SC", "42.6 IMD")),
    (TokenActivity, dict(activity=[dict(ts=NOW, kind="LP READ", token_id="eth-sc", amount=None, asset="")], tokens=[token()]), ("LP READ ETH", "SC", "--")),
])
async def test_supporting_panels_render_columns(widget, kwargs, expected):
    panel = widget()
    async with Probe(panel).run_test(size=(149, 45)) as pilot:
        panel.update_data(**kwargs)
        await pilot.pause()
        for value in expected:
            assert value in painted(pilot.app)


async def test_sparkline_keeps_the_full_window_and_never_pads_sparse_history_with_zero():
    table = TokensTable()
    async with Probe(table).run_test(size=(149, 45)) as pilot:
        table.update_data(tokens=[token(sparkline=[8] + [0] * 23),
            token(id="sparse", symbol="SPARSE", sparkline=[1, 8])], as_of=NOW)
        await pilot.pause()
        assert "█"+"▁"*19 in painted(pilot.app)
        sparse = next(line for line in painted(pilot.app).splitlines() if "SPARSE" in line)
        assert "                  ▁█" in sparse


async def test_supporting_column_headers_match_and_leave_a_blank_row():
    colors=[]
    for panel,values,header in (
        (NewlyLaunched(),dict(newly_launched=[token()],as_of=NOW),'AGE'),
        (BestPlays(),dict(gainers=[token()],losers=[]),'GAINERS'),
    ):
        async with Probe(panel).run_test(size=(149,45)) as pilot:
            panel.update_data(**values)
            await pilot.pause()
            strips=pilot.app.screen._compositor.render_strips()
            index=next(i for i,s in enumerate(strips) if header in s.text)
            assert not strips[index+1].text.strip()
            assert 'SC' in strips[index+2].text
            colors.append(next(s.style.color for s in strips[index] if header in s.text))
    assert colors[0]==colors[1]


def test_model_widget_signatures_match_the_renderers():
    import inspect
    from maxpane_dashboard.data.swarm_tokens_models import WIDGET_SIGNATURES
    from maxpane_dashboard.widgets import swarm_tokens
    for name,keys in WIDGET_SIGNATURES.items():
        parameters=tuple(inspect.signature(getattr(swarm_tokens,name).update_data).parameters)
        assert parameters==('self',*keys)


async def test_best_plays_is_explicitly_top_five():
    panel = BestPlays()
    async with Probe(panel).run_test(size=(149, 45)) as pilot:
        panel.update_data(gainers=[token(symbol=f"RANK{i}", lp_state="one-token" if i == 1 else "two-sided")
                                  for i in range(1, 8)], losers=[])
        await pilot.pause()
        output = painted(pilot.app)
        assert "TOP 5" in output and "RANK5" in output
        assert "RANK6" not in output and "RANK7" not in output
        assert "* RANK1" in output and "* one-sided" in output

