"""Popup facts distinguish counted community facts and the bounded list."""
from pathlib import Path
import pytest

from textual.app import App
from textual.widgets import Static

from maxpane_dashboard.widgets.sworn.details import SwornDetailScreen, SOURCES
from maxpane_dashboard.widgets.sworn.art import SwornArt
from tests.widgets.test_sworn_explorer import payload, painted, CLAIMANT


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    def on_mount(self):
        card = payload()['sworn_selected']
        card['metadata']['oracle'] = [dict(traitId=10001, name='[blue]exact', evidence='chain',
            template='T3', fromBlock=90, toBlock=123, minPanelSize=5, minQuorum=3,
            requestId='0x'+'a'*64, oracleRequestId='0x'+'b'*64, target=CLAIMANT)]
        self.push_screen(SwornDetailScreen(card))


async def test_popup_exposes_bounded_community_and_original_evidence_without_markup():
    async with Harness().run_test(size=(149, 60)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert 'SWORN #10 · WALLET & FACTS' in output
        assert '1 shown / 40 accepted' in output
        assert '#10001  [red]literal' in output
        assert '#10001 [blue]exact' in output
        assert 'Panel 5 · quorum 3' in output
        assert 'Blocks 90–123' in output
        assert output.count('⧉') == 3
        text = pilot.app.screen.query_one('#sworn-popup-facts Static', Static).render()
        # IDs are bytes32 request identifiers, never guessed transaction links.
        assert not any('a'*64 in str(span.style) or 'b'*64 in str(span.style) for span in text.spans)


async def test_popup_narrow_mode_keeps_art_and_facts_reachable():
    async with Harness().run_test(size=(80, 45)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.has_class('compact')
        viewport = screen.query_one('.record-detail-scroll')
        assert viewport.max_scroll_y > 0


@pytest.mark.parametrize('width', [94, 95, 96])
async def test_popup_boundary_keeps_square_art_and_scrollable_facts(width):
    async with Harness().run_test(size=(width, 45)) as pilot:
        screen = pilot.app.screen
        await pilot.pause()
        assert screen.has_class('compact') == (width < 95)
        art = screen.query_one(SwornArt)
        art.update_art(dict(png='', pixels=[['00ff41'] * 128 for _ in range(128)], hash='green-test-square'))
        await pilot.pause()
        image_rows = [strip.text for strip in art._rows if '▀' in strip.text]
        assert image_rows
        assert abs(image_rows[0].count('▀') - 2 * len(image_rows)) <= 1
        assert art.region.right <= width
        outer = screen.query_one('.record-detail-scroll')
        outer.scroll_end(animate=False)
        await pilot.pause()
        facts = screen.query_one('#sworn-popup-facts')
        assert facts.region.right <= width
        assert facts.max_scroll_y > 0 or outer.max_scroll_y > 0


async def test_short_popup_scrolls_instead_of_clipping_art_floor_and_close_hint():
    async with Harness().run_test(size=(149, 18)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        outer = screen.query_one('.record-detail-scroll')
        assert outer.max_scroll_y > 0
        outer.scroll_end(animate=False)
        await pilot.pause()
        assert screen.query_one('#sworn-popup-body').region.bottom <= outer.region.bottom
        assert 'PRESS SPACE OR ESC TO CLOSE' in painted(pilot.app)


async def test_popup_source_links_are_pinned_and_open_only_named_sources():
    async with Harness().run_test(size=(149, 60)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        output = painted(pilot.app)
        assert 'Official Sworn site ↗' in output
        assert 'Pinned source · c4ff3238 ↗' in output
        opened = []
        pilot.app.open_url = opened.append
        screen.action_open_source(0)
        screen.action_open_source(1)
        screen.action_open_source(-1)
        screen.action_open_source(True)
        assert opened == list(SOURCES)
