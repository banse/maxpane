"""Mock market widgets preserve unknown values, LP states and row identity."""

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.widgets.swarm_tokens import (
    BestPlays, NewlyLaunched, TokenActivity, TokensHero, TokensTable,
)


async def test_live_history_keeps_gaps_and_stale_quotes_are_marked():
    table = TokensTable()
    async with Probe(table).run_test(size=(149, 45)) as pilot:
        table.update_data(tokens=[token(sparkline=[1, None, 3, None, 5],
                                        market_state='stale')], as_of=NOW)
        await pilot.pause()
        text = painted(pilot.app)
        assert '▁ ▄ █' in text
        assert '~$0.0042' in text


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
    TokensHero { height: 9; }
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


async def test_newly_launched_reuses_paired_amounts_and_keeps_markup_literal():
    panel = NewlyLaunched()
    async with Probe(panel).run_test(size=(149, 45)) as pilot:
        panel.update_data(newly_launched=[token(symbol="[/x]"),
            token(id="zero",symbol="ZERO",paired_amount=0,paired_symbol="ETH"),
            token(id="missing",symbol="MISSING",paired_amount=None)], as_of=NOW)
        await pilot.pause()
        output=painted(pilot.app)
        assert "PAIRED LP" in output and "LP STATE" not in output
        assert "788 IMD" in output and "0 ETH" in output and "[/x]" in output
        assert "--" in next(line for line in output.splitlines() if "MISSING" in line)
        assert "two-sided" not in output


async def test_liquidity_hero_displays_imd_then_eth_and_marks_partial_totals():
    hero=TokensHero()
    async with Probe(hero).run_test(size=(149,45)) as pilot:
        hero.update_data(tokens_hero={'liquidity': dict(state='partial', read_ts=NOW,
            imd=788, eth=2.5, partial=True, known=2, total=3)})
        await pilot.pause()
        lines=painted(pilot.app).splitlines()
        imd=next(i for i,line in enumerate(lines) if '788 IMD' in line)
        assert '2.5 ETH' in lines[imd+1]
        assert '≥' in lines[imd] and '≥' in lines[imd+1]
        hero.update_data(tokens_hero={'liquidity': dict(state='ok', read_ts=NOW,
            imd=0, eth=None, partial=False, known=1, total=1)})
        await pilot.pause()
        assert '0 IMD' in painted(pilot.app) and '-- ETH' in painted(pilot.app)
        assert '≥' not in painted(pilot.app)


async def test_hero_distinguishes_empty_from_unknown_coverage():
    from tests.screens.test_surf_news_hero_demo import painted as card_text
    hero = TokensHero()
    async with Probe(hero).run_test(size=(149, 45)) as pilot:
        hero.update_data(tokens_hero={
            'tokens': dict(state='ok', read_ts=NOW, tracked=0, new_24h=0, chains=0),
            'volume': dict(state='unavailable', read_ts=None, amount=None, known=0, total=2)})
        await pilot.pause()
        tokens_text = card_text(pilot.app, hero.query_one('#hero-tokens'))
        assert any('tracked' in row and '0' in row for row in tokens_text.splitlines())
        assert any('new 24h' in row and '0' in row for row in tokens_text.splitlines())
        assert 'unavailable' in card_text(pilot.app, hero.query_one('#hero-volume'))
        hero.update_data(tokens_hero={'volume': dict(state='partial', read_ts=NOW,
            amount=0, known=1, total=2)})
        await pilot.pause()
        volume_text = card_text(pilot.app, hero.query_one('#hero-volume'))
        assert '╭─╮' in volume_text and '1/2 known' in volume_text


@pytest.mark.parametrize("widget,kwargs,expected", [
    (NewlyLaunched, dict(newly_launched=[token(launched_at=NOW - 240)], as_of=NOW), ("4m", "SC", "ETH", "788 IMD")),
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

