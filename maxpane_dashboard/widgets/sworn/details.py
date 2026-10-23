"""Claimant facts and accepted evidence, shared by the explorer and popup."""
from rich.text import Text
from rich.style import Style
from textual import events, on
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import address_prose, address_text
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from . import EXPLORER
from .art import SwornArt


# Reviewed deployment provenance; these links are not a source of live metrics.
SOURCES = ('https://swornbyswarm.sites.imd.fun/',
           'https://github.com/identity-md-launches/launch-2404-renderer-composer-registry/tree/c4ff3238390fc51962fb67e86affc20cf418126e')


def card_counts(card):
    if not card:
        return None, None, None
    meta = card.get('metadata') or {}
    ids = meta.get('traits')
    ids = [n for n in ids if type(n) is int and 100 <= n < 1400] if isinstance(ids, list) else None
    community = next((a.get('value') for a in meta.get('attributes', [])
                      if a.get('trait_type') == 'community_count'), None)
    return (len({n // 100 for n in ids}) if ids is not None else None,
            len(ids) if ids is not None else None,
            community if type(community) is int and community >= 0 else None)


def fact_text(card, *, extended=False):
    text = Text()
    if not card:
        return text
    meta = card.get('metadata') or {}
    for label, key in (('Claimant', 'claimant'), ('Holder', 'holder')):
        text.append(label + '  ', style='dim')
        text.append_text(address_text(card.get(key), width=25, explorer=EXPLORER)).append('\n')
    text.append('Facts belong to the original claimant.\n', style='dim')
    text.append(f"\nBlock {card.get('block', '—')} · as of {hhmm(card.get('observed_at'), unknown='—')}\n\n", style='dim')
    attrs = meta.get('attributes') or []
    for attribute in attrs:
        name, value = flatten(attribute.get('trait_type')), flatten(attribute.get('value'))
        if name in ('Claimant', 'community_count') or name.startswith('Community '):
            continue
        text.append_text(address_prose(name + '  ', style='dim', explorer=EXPLORER))
        text.append_text(address_prose(value + '\n', style='dim' if value == 'none' else 'green', explorer=EXPLORER))
    if not extended:
        return text
    text.append('\nSOURCE\n\n', style='bold')
    for index, label in enumerate(('Official Sworn site ↗', 'Pinned source · c4ff3238 ↗')):
        text.append(label, style=Style(link=SOURCES[index], meta={'@click': f'screen.open_source({index})'})).append('\n')
    text.append('\nCATALOG FACT IDS\n\n', style='bold')
    text.append(' · '.join(str(identifier) for identifier in meta.get('traits') or []) or 'No accepted catalog facts')
    text.append('\n')
    text.append('\nCOMMUNITY\n\n', style='bold')
    community = meta.get('community') or []
    total = card_counts(card)[2]
    text.append(f"{len(community)} shown / {total if total is not None else '—'} accepted\n", style='dim')
    names = {a.get('trait_type'): a.get('value') for a in attrs}
    for identifier in community:
        text.append_text(address_prose(f"#{identifier}  {flatten(names.get(f'Community {identifier}', ''))}\n", explorer=EXPLORER))
    text.append('\nACCEPTED EVIDENCE\n\n', style='bold')
    text.append('Direct facts are frozen at mint.\nA missing accepted fact is not a negative proof.\n', style='dim')
    for proof in meta.get('oracle') or []:
        text.append_text(address_prose(f"\n#{proof.get('traitId')} {flatten(proof.get('name'))}\n", style='bold', explorer=EXPLORER))
        text.append(f"{flatten(proof.get('evidence'))} · {flatten(proof.get('template'))}\n")
        text.append(f"Blocks {proof.get('fromBlock', '—')}–{proof.get('toBlock', '—')}\n")
        text.append(f"Panel {proof.get('minPanelSize', '—')} · quorum {proof.get('minQuorum', '—')}\n")
        text.append('Target ').append_text(address_text(proof.get('target'), width=25, explorer=EXPLORER)).append('\n')
        text.append('Request ' + flatten(proof.get('requestId')) + '\n')
        text.append('Oracle  ' + flatten(proof.get('oracleRequestId')) + '\n')
    text.append('\nMint block ' + str(card.get('minted_at_block') or '—'), style='dim')
    if meta.get('description'):
        text.append('\n\nONCHAIN METADATA\n\n', style='bold')
        text.append_text(address_prose(flatten(meta['description']), explorer=EXPLORER))
    return text


class SwornFacts(PanelBase):
    TITLE = 'WALLET FACTS'
    DEFAULT_CSS = '''
    SwornFacts {height: 1fr; min-height: 10;}
    SwornFacts VerticalScroll {height: 1fr; min-height: 1; scrollbar-gutter: stable;}
    SwornFacts .sworn-facts-text {height: auto; padding: 0 1;}
    '''
    def compose_body(self):
        with VerticalScroll():
            yield Static(Text(), classes='sworn-facts-text')

    def show_card(self, card):
        self.query_one('.sworn-facts-text', Static).update(fact_text(card))


class SwornDetailScreen(RecordDetailScreen):
    ID_PREFIX = 'sworn-popup'
    # Measured after the live preview: at 95 columns the existing modal frame
    # leaves 43 cells for art beside the fixed 46-cell facts rail. At 94 the
    # stacked layout keeps both readable. Its outer viewport also scrolls when
    # the 12-row artwork floor exceeds a short terminal's modal content height.
    DEFAULT_CSS = '''
    SwornDetailScreen .record-detail-box {max-width: 180;}
    SwornDetailScreen .record-detail-scroll {overflow-y: auto;}
    SwornDetailScreen #sworn-popup-body {height: 100%; min-height: 12;}
    SwornDetailScreen #sworn-popup-art {width: 1fr; height: 100%;}
    SwornDetailScreen #sworn-popup-facts {width: 46; height: 100%; scrollbar-gutter: stable;}
    SwornDetailScreen.compact #sworn-popup-body {layout: vertical; height: auto;}
    SwornDetailScreen.compact .record-detail-scroll {overflow-y: auto;}
    SwornDetailScreen.compact #sworn-popup-art {width: 100%; height: 22;}
    SwornDetailScreen.compact #sworn-popup-facts {width: 100%; height: auto;}
    '''
    def compose_sections(self):
        with Horizontal(id='sworn-popup-body'):
            yield SwornArt(id='sworn-popup-art')
            with VerticalScroll(id='sworn-popup-facts'):
                yield Static(fact_text(self.row, extended=True))

    def on_mount(self):
        super().on_mount()
        self.query_one(SwornArt).update_art(self.row.get('art'))
        self.query_one('#sworn-popup-facts').focus()
        self.set_class(self.size.width < 95, 'compact')

    def on_resize(self):
        super().on_resize()
        self.set_class(self.size.width < 95, 'compact')

    def _title(self):
        self.query_one('.record-detail-title', Static).update(Text(f"SWORN #{self.row['token_id']} · WALLET & FACTS", style='bold'))

    def action_open_source(self, index):
        if type(index) is int and 0 <= index < len(SOURCES):
            self.app.open_url(SOURCES[index])

    @on(events.ScreenSuspend)
    def _release_art(self):
        self.query_one(SwornArt).release()

    @on(events.ScreenResume)
    def _resume_art(self):
        self.query_one(SwornArt).resume()
