"""SITES (``widgets/surf/swarm_sites.py``), swarm v2 WP6.

Unwired until WP7; the three ``widget_wp_common.md`` contract checks are
imposed here against ``SWARM_WIDGET_SIGNATURES["SurfSwarmSites"]``. Every
assertion is against composited output; the tx link is read off the
compositor through ``tests/widgets/address_probe.link_targets``.
"""

from __future__ import annotations

import inspect
import re

from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.address import COPY_GLYPH
from maxpane_dashboard.widgets.surf.swarm_sites import (
    CID_COLS,
    COMPACT_WIDTH,
    FULL_WIDTH,
    TIGHT_WIDTH,
    SurfSwarmSites,
    _window_cid,
)
from tests.widgets.address_probe import link_targets
from tests.widgets.surf_compositing import composite_lines

SIG = SWARM_WIDGET_SIGNATURES["SurfSwarmSites"]
ROW_KEYS = SURF_ROW_KEYS["swarm_site_rows"]
GUTTER = SurfSwarmSites.GUTTER_COLS

SIZE = (140, 20)
AS_OF = "04:06"
TX = "0x" + "9d" * 32
CID = "bafybeig4xxfxbhkxsmautrga6yjuqcv76bctmkhsw6l5kb4qgw4dprla"  # 59 chars, the corpus shape


def _site(**over) -> dict:
    """One site row in the frozen ``swarm_site_rows`` shape (corpus values)."""
    row = dict(
        label="roll", ens_name="roll.site.identitymd.eth", cid=CID, bytes=2_445_908,
        status="named", tx_hash=TX, block_number=26_021_387,
        job_id="115a2caa-323b-411a-bc39-e69977e85e34", superseded_by=None, failure=None,
    )
    row.update(over)
    return row


async def _sites(size=SIZE, **kwargs) -> str:
    return "\n".join(await composite_lines(SurfSwarmSites, size, **kwargs))


def _data_lines(text: str) -> list[str]:
    lines = text.split("\n")
    header = next(i for i, line in enumerate(lines) if "label" in line and "ens" in line)
    return [line for line in lines[header + 1:] if line.strip()]


class _Probe(App):
    def compose(self):
        yield SurfSwarmSites()


async def _urls(rows, size=SIZE) -> list[str]:
    async with _Probe().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfSwarmSites)
        widget.update_data(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        return sorted({url for _x, _y, _n, _k, _v, url in link_targets(pilot.app) if url})


# -- the frozen contract ------------------------------------------------------------


def test_the_hand_row_is_the_frozen_shape():
    assert set(_site()) == set(ROW_KEYS) and len(_site()) == len(ROW_KEYS)


def test_update_data_names_exactly_the_frozen_signature_and_takes_kwargs():
    params = list(inspect.signature(SurfSwarmSites.update_data).parameters.values())
    named = [p.name for p in params if p.kind is not p.VAR_KEYWORD and p.name != "self"]
    assert tuple(named) == SIG
    assert any(p.kind is p.VAR_KEYWORD for p in params)


async def test_no_args_and_all_none_render_unavailable_not_no_data():
    for kwargs in ({}, {key: None for key in SIG}):
        text = await _sites(**kwargs)
        assert "unavailable" in text and "No data" not in text, text
        assert "SITES" in text


async def test_an_empty_list_is_a_real_negative_and_differs_from_none():
    text = await _sites(swarm_site_rows=[], swarm_scores_as_of_hhmm=AS_OF)
    assert "No data" in text and "unavailable" not in text, text


def test_the_row_tuples_agree_with_the_column_count():
    width = len(SurfSwarmSites.COLUMNS)
    assert width == len(SurfSwarmSites.COLUMN_SPECS) == 5
    assert len(SurfSwarmSites.EMPTY_ROW) == width
    assert len(SurfSwarmSites.LOADING_ROW) == width
    assert SurfSwarmSites.ROW_CAP == 10


# -- cells -------------------------------------------------------------------------------


SITE_URL = "https://roll.site.identitymd.eth.limo/"


async def test_the_tx_links_on_etherscan_mainnet_with_no_icon():
    assert await _urls([_site()]) == [f"https://etherscan.io/tx/{TX}", SITE_URL]
    text = await _sites(swarm_site_rows=[_site()], swarm_scores_as_of_hhmm=AS_OF)
    assert COPY_GLYPH not in text, "a hash is outside the copy rule"
    assert TX[: 2 + 8] in text, text


async def test_a_value_that_is_not_a_tx_hash_renders_plain_and_unlinked():
    assert await _urls([_site(tx_hash="0x" + "9d" * 20)]) == [SITE_URL]
    assert await _urls([_site(tx_hash=None)]) == [SITE_URL]
    text = await _sites(swarm_site_rows=[_site(tx_hash=None)], swarm_scores_as_of_hhmm=AS_OF)
    assert _data_lines(text)[0].rstrip().endswith("--"), text


async def test_the_cid_window_keeps_its_head_and_its_tail():
    text = await _sites(swarm_site_rows=[_site()], swarm_scores_as_of_hhmm=AS_OF)
    line = _data_lines(text)[0]
    window = _window_cid(CID, CID_COLS)
    assert window in line, (window, line)
    assert "…" in window and window.startswith("bafybeig") and window.endswith(CID[-7:])
    assert len(window) == CID_COLS
    assert CID not in text


def test_window_cid_is_cell_measured_and_degrades_to_a_dash():
    assert _window_cid(None, 16) == "--"
    assert _window_cid("", 16) == "--"
    assert _window_cid("short", 16) == "short"
    wide = _window_cid("漢" * 40, 16)
    from rich.cells import cell_len
    assert cell_len(wide) <= 16 and "…" in wide, wide
    assert _window_cid("[/x]" + CID, 16) == _window_cid(CID, 16)


async def test_size_is_compact_bytes_and_a_dash_when_unknown():
    rows = [_site(bytes=2_445_908), _site(label="tiny", bytes=584), _site(label="none", bytes=None),
            _site(label="str", bytes="17211")]
    text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    big, tiny, none, as_str = _data_lines(text)[:4]
    assert "2.4M" in big, big
    assert " 584 " in tiny and "584.0" not in tiny, tiny
    assert "--" in none, none
    assert "17.2K" in as_str, as_str


async def test_the_ens_name_opens_its_eth_limo_site_with_no_icon():
    """Owner 2026-09-23: a click on ``mswap.site.identitymd.eth`` opens
    ``https://mswap.site.identitymd.eth.limo/``."""
    rows = [_site(label="mswap", ens_name="mswap.site.identitymd.eth", tx_hash=None)]
    assert await _urls(rows) == ["https://mswap.site.identitymd.eth.limo/"]
    text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    assert "mswap.site.identitymd.eth" in text and COPY_GLYPH not in text, text


async def test_a_name_outside_site_identitymd_eth_shows_but_never_links():
    for name in ("mswap.evil.eth", "a.b.site.identitymd.eth", "MSWAP.site.identitymd.eth",
                 "x.site.identitymd.eth[/x]"):
        rows = [_site(ens_name=name, tx_hash=None)]
        assert await _urls(rows) == [], name
        text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        assert _data_lines(text), (name, text)


async def test_replaced_and_nameless_rows_are_left_out():
    """Owner 2026-09-23: the build replaced by ``work`` and the two queued
    builds with no ENS name (88 attempts, "no static export") do not show."""
    rows = [_site(label="work", ens_name="work.site.identitymd.eth"),
            _site(label=None, ens_name="work.site.identitymd.eth",
                  superseded_by="c828b3f1-6dfd-41ac-bc6c-f5ab0ccdf67d"),
            _site(label="old", status="superseded"),
            _site(label=None, ens_name=None, status="queued", tx_hash=None,
                  failure="no static export: nothing named index.html"),
            _site(label="cmns", ens_name="cmns.site.identitymd.eth")]
    text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 2 and "work" in lines[0] and "cmns" in lines[1], lines
    assert "→" not in text and "static export" not in text and "old" not in text, text


async def test_a_list_that_filters_to_nothing_is_no_data_not_unavailable():
    rows = [_site(ens_name=None, status="queued"), _site(superseded_by="x")]
    text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    assert "No data" in text and "unavailable" not in text.lower(), text


async def test_the_label_is_coloured_on_the_raw_status_and_escaped():
    # Row 0 is the focused table's cursor row and paints in the cursor style,
    # so the two probed rows sit below it.
    rows = [_site(label="odd[one", status="[/x]named"), _site(status="named"),
            _site(label="gone", status="failed", ens_name="gone.site.identitymd.eth")]
    async with _Probe().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSites)
        widget.update_data(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows_text = ["".join(seg.text for seg in strip) for strip in strips]
        y_named = next(y for y, r in enumerate(rows_text) if " roll " in r)
        y_failed = next(y for y, r in enumerate(rows_text) if " gone " in r)
        named = pilot.app.screen.get_style_at(rows_text[y_named].index("roll"), y_named)
        failed = pilot.app.screen.get_style_at(rows_text[y_failed].index("gone"), y_failed)
        # Textual paints ``green``/``red`` as the ANSI theme's triplets (indices
        # 2 and 1), so colour is compared to the theme's own resolution.
        palette = pilot.app.ansi_theme.ansi_colors
        assert named.color is not None and named.color.get_truecolor() == palette[2], named
        assert failed.color is not None and failed.color.get_truecolor() == palette[1], failed
        assert "odd[one" in "\n".join(rows_text) and "[/x]" not in "\n".join(rows_text)


async def test_the_panel_claims_no_reachability():
    """PRD §3: SITES shows what was published, never whether it answers."""
    rows = [_site(), _site(label="gone", status="failed", ens_name=None, failure="pin failed"),
            _site(label="old", status="superseded", superseded_by="roll")]
    text = await _sites(swarm_site_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    assert re.search(r"\b(up|down|online|offline)\b", text, re.I) is None, text


async def test_a_non_dict_row_is_skipped_and_the_cap_holds():
    """A non-dict is left out with the hidden rows, before the cap, so junk
    and hidden rows never cost one of the ten lines and never raise."""
    clean = [_site(label=f"s{n:02d}") for n in range(15)]
    text = await _sites((SIZE[0], 30), swarm_site_rows=clean, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 10, len(lines)
    assert "s00" in lines[0] and "s09" in lines[-1] and "s10" not in text
    junk = [42, _site(label="gone", ens_name=None), _site(label="old", superseded_by="s00")]
    text = await _sites((SIZE[0], 30), swarm_site_rows=junk + clean, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 10, len(lines)
    assert "s00" in lines[0] and "s09" in lines[-1] and "s10" not in text


async def test_the_title_carries_the_marker_only_when_it_is_real():
    assert f"SITES · as of {AS_OF}" in await _sites(swarm_site_rows=[_site()],
                                                   swarm_scores_as_of_hhmm=AS_OF)
    for as_of in (None, ""):
        text = await _sites(swarm_site_rows=[_site()], swarm_scores_as_of_hhmm=as_of)
        assert "as of" not in text and "SITES" in text


# -- tiers ------------------------------------------------------------------------------

_FULL = FULL_WIDTH + GUTTER + 5
_COMPACT = FULL_WIDTH + GUTTER - 1
_TIGHT = COMPACT_WIDTH + GUTTER - 1


def test_the_derived_tier_widths_land_inside_their_tiers():
    assert _COMPACT >= COMPACT_WIDTH + GUTTER
    assert _TIGHT >= TIGHT_WIDTH + GUTTER
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0


async def test_compact_sheds_size_and_tight_sheds_cid_while_ens_and_tx_survive():
    row = [_site()]
    full = await _sites((_FULL, 12), swarm_site_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    compact = await _sites((_COMPACT, 12), swarm_site_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    tight = await _sites((_TIGHT, 12), swarm_site_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    window = _window_cid(CID, CID_COLS)

    assert "size" in full and "2.4M" in full and window in full and "‹" not in full, full
    assert "size" not in compact and "2.4M" not in compact, compact
    assert window in compact and "‹" in compact
    assert "cid" not in tight.split("\n")[2] and window not in tight, tight
    assert "‹" in tight
    for text in (full, compact, tight):
        assert "roll.site.identitymd.eth" in text and TX[: 2 + 8] in text, text


async def test_the_full_tier_hides_no_column_at_its_own_threshold():
    async with _Probe().run_test(size=(FULL_WIDTH + GUTTER, 12)) as pilot:
        widget = pilot.app.query_one(SurfSwarmSites)
        widget.update_data(swarm_site_rows=[_site()], swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        assert table.max_scroll_x == 0
        assert len(table.columns) == 5
        text = "\n".join("".join(seg.text for seg in strip)
                         for strip in pilot.app.screen._compositor.render_strips())
        assert re.search(r"label\s+ens\s+size\s+cid\s+tx", text), text
        assert "‹" not in text
