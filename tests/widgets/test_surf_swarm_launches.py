"""LAUNCHES (``widgets/surf/swarm_launches.py``), swarm v2 WP6.

Unwired until WP7; the three ``widget_wp_common.md`` contract checks are
imposed here against ``SWARM_WIDGET_SIGNATURES["SurfSwarmLaunches"]``. Every
assertion is against composited output; links and icons are read off the
compositor through ``tests/widgets/address_probe``.
"""

from __future__ import annotations

import inspect
import re

from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.address import COPY_GLYPH
from maxpane_dashboard.widgets.surf.swarm_launches import (
    ADDR_COLS,
    COMPACT_WIDTH,
    FULL_WIDTH,
    TIGHT_ADDR_COLS,
    TIGHT_WIDTH,
    SurfSwarmLaunches,
)
from tests.widgets.address_probe import icon_targets, link_targets
from tests.widgets.surf_compositing import composite_lines

SIG = SWARM_WIDGET_SIGNATURES["SurfSwarmLaunches"]
ROW_KEYS = SURF_ROW_KEYS["swarm_launch_rows"]
GUTTER = SurfSwarmLaunches.GUTTER_COLS

SIZE = (140, 24)
AS_OF = "04:06"
ADDR = "0x" + "81" * 20
ADDR2 = "0x" + "73" * 20
TX = "0x" + "cd" * 32
REPO = "https://github.com/Identity-md/launch-62-build-independently-review-streaming"


def _artifact(address=ADDR, name="MerkleDistributor") -> dict:
    return {"role": "distributor", "name": name, "address": address,
            "tx_hash": TX, "block_number": 9_400_000}


def _launch(**over) -> dict:
    """One launch row in the frozen ``swarm_launch_rows`` shape (corpus values)."""
    row = dict(
        launch_number=62, kind="evm_project", status="live", chain_id=11155111,
        repo_url=REPO, commit="192743350ad9bd9b1b0be3f2522147fe142672f0",
        parked_reason=None, artifact_count=3, created_ts=1_758_400_000.0,
        updated_ts=1_758_400_060.0,
        artifacts=[_artifact(), _artifact(ADDR2, "LaunchToken"), _artifact(ADDR2, "Pool")],
    )
    row.update(over)
    return row


SUMMARY = {
    "by_status": [{"status": "abandoned", "count": 10}, {"status": "live", "count": 19},
                  {"status": "parked", "count": 1}],
    "by_kind": [{"kind": "evm_project", "count": 15}, {"kind": "univ4_hook", "count": 15}],
    "by_chain": [{"chain_id": 11155111, "count": 20}, {"chain_id": 1, "count": 10}],
}


async def _launches(size=SIZE, **kwargs) -> str:
    return "\n".join(await composite_lines(SurfSwarmLaunches, size, **kwargs))


def _data_lines(text: str) -> list[str]:
    lines = text.split("\n")
    header = next(i for i, line in enumerate(lines) if "status" in line and "repo" in line)
    return [line for line in lines[header + 1:] if line.strip()]


class _Probe(App):
    def compose(self):
        yield SurfSwarmLaunches()


async def _probe(rows, size=SIZE, **extra):
    """``(text, icons, link urls)`` read off the compositor for *rows*."""
    async with _Probe().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfSwarmLaunches)
        widget.update_data(swarm_launch_rows=rows, swarm_scores_as_of_hhmm=AS_OF, **extra)
        await pilot.pause()
        text = "\n".join("".join(seg.text for seg in strip)
                         for strip in pilot.app.screen._compositor.render_strips())
        urls = sorted({url for _x, _y, _n, _k, _v, url in link_targets(pilot.app) if url})
        return text, icon_targets(pilot.app), urls


# -- the frozen contract ------------------------------------------------------------


def test_the_hand_row_is_the_frozen_shape():
    assert set(_launch()) == set(ROW_KEYS) and len(_launch()) == len(ROW_KEYS)


def test_update_data_names_exactly_the_frozen_signature_and_takes_kwargs():
    params = list(inspect.signature(SurfSwarmLaunches.update_data).parameters.values())
    named = [p.name for p in params if p.kind is not p.VAR_KEYWORD and p.name != "self"]
    assert tuple(named) == SIG
    assert any(p.kind is p.VAR_KEYWORD for p in params)


async def test_no_args_and_all_none_render_unavailable_not_no_data():
    for kwargs in ({}, {key: None for key in SIG}):
        text = await _launches(**kwargs)
        assert "unavailable" in text, text
        assert "No data" not in text
        assert "LAUNCHES" in text


async def test_an_empty_list_is_a_real_negative_and_differs_from_none():
    text = await _launches(swarm_launch_rows=[], swarm_scores_as_of_hhmm=AS_OF)
    assert "No data" in text and "unavailable" not in text, text


def test_the_row_tuples_agree_with_the_column_count():
    width = len(SurfSwarmLaunches.COLUMNS)
    assert width == len(SurfSwarmLaunches.COLUMN_SPECS) == 7
    assert len(SurfSwarmLaunches.EMPTY_ROW) == width
    assert len(SurfSwarmLaunches.LOADING_ROW) == width
    assert SurfSwarmLaunches.ROW_CAP == 12


# -- artifacts: one icon per row, linked to the row's own chain (R-C, E7) -----------


async def test_the_copy_icon_appears_once_per_row_with_artifacts():
    rows = [_launch(), _launch(launch_number=61, artifacts=[], artifact_count=0),
            _launch(launch_number=60)]
    text, icons, _urls = await _probe(rows)
    assert len(icons) == 2, icons
    assert all(copied == ADDR for _x, _y, copied in icons), icons
    lines = _data_lines(text)
    assert COPY_GLYPH in lines[0] and COPY_GLYPH not in lines[1] and COPY_GLYPH in lines[2]
    assert "--" in lines[1], lines[1]


async def test_five_artifacts_show_the_first_and_plus_four():
    arts = [_artifact(), _artifact(ADDR2), _artifact(ADDR2), _artifact(ADDR2), _artifact(ADDR2)]
    text = await _launches(swarm_launch_rows=[_launch(artifacts=arts, artifact_count=5)],
                           swarm_scores_as_of_hhmm=AS_OF)
    assert f"{COPY_GLYPH} +4" in text, text
    one = await _launches(swarm_launch_rows=[_launch(artifacts=[_artifact()], artifact_count=1)],
                          swarm_scores_as_of_hhmm=AS_OF)
    assert "+" not in _data_lines(one)[0], one


async def test_a_sepolia_row_links_its_address_on_sepolia_etherscan():
    _text, _icons, urls = await _probe([_launch(chain_id=11155111)])
    assert urls == [f"https://sepolia.etherscan.io/address/{ADDR}"], urls


async def test_a_mainnet_row_links_on_etherscan():
    _text, _icons, urls = await _probe([_launch(chain_id=1)])
    assert urls == [f"https://etherscan.io/address/{ADDR}"], urls


async def test_an_unknown_or_missing_chain_links_nothing_but_keeps_the_icon():
    for chain_id in (None, 999_999_999, "1"):
        text, icons, urls = await _probe([_launch(chain_id=chain_id)])
        assert urls == [], (chain_id, urls)
        assert len(icons) == 1, (chain_id, icons)
        assert "—" in _data_lines(text)[0], text


async def test_an_artifact_with_an_invalid_address_shows_its_name_with_no_icon():
    bad = _artifact(address="0xnotanaddress", name="Merkle[/x]Distributor")
    text, icons, urls = await _probe([_launch(artifacts=[bad], artifact_count=1)])
    assert icons == [] and urls == []
    assert "MerkleDistributor" in text and "[/x]" not in text, text


# -- the other cells -------------------------------------------------------------------


async def test_the_chain_word_is_per_row_and_the_network_kwarg_is_not_painted():
    rows = [_launch(chain_id=11155111), _launch(launch_number=3, chain_id=1)]
    text = await _launches(swarm_launch_rows=rows, swarm_scores_as_of_hhmm=AS_OF,
                           swarm_network="BASE")
    first, second = _data_lines(text)[:2]
    assert "SEPOLIA" in first and "MAINNET" in second
    assert "BASE" not in text


async def test_repo_is_owner_slash_name_for_github_and_unmangled_otherwise():
    rows = [_launch(), _launch(launch_number=2, repo_url="https://gitlab.com/o/r"),
            _launch(launch_number=1, repo_url="https://github.com.evil.example/o/r")]
    text = await _launches(swarm_launch_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    first, second, third = _data_lines(text)[:3]
    assert "Identity-md/launch-62-build" in first and "https://" not in first, first
    assert "https://gitlab.com/o/r" in second, second
    assert "https://github.com.evil.ex" in third, third


async def test_status_is_escaped_and_coloured_on_the_raw_word():
    # Row 0 is the focused table's cursor row and paints in the cursor style,
    # so the two probed rows sit below it.
    rows = [_launch(launch_number=3, status="[/x]parked"), _launch(launch_number=2, status="live"),
            _launch(launch_number=1, status="abandoned")]
    async with _Probe().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmLaunches)
        widget.update_data(swarm_launch_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows_text = ["".join(seg.text for seg in strip) for strip in strips]
        y_live = next(y for y, r in enumerate(rows_text) if " live " in r)
        y_gone = next(y for y, r in enumerate(rows_text) if "abandoned" in r)
        live_style = pilot.app.screen.get_style_at(rows_text[y_live].index("live"), y_live)
        gone_style = pilot.app.screen.get_style_at(rows_text[y_gone].index("abandoned"), y_gone)
        # Textual paints ``green`` as the ANSI theme's triplet (index 2), so the
        # colour is compared to the theme's own resolution, not to the name;
        # ``dim`` it resolves into a colour blended toward the background, so
        # the abandoned word is asserted to differ from the row's plain text.
        green = pilot.app.ansi_theme.ansi_colors[2]
        plain = pilot.app.screen.get_style_at(rows_text[y_gone].index("evm_project"), y_gone)
        assert live_style.color is not None and live_style.color.get_truecolor() == green, live_style
        assert gone_style.color != plain.color, (gone_style, plain)
        assert gone_style.color.get_truecolor() != green
        assert "[/x]" not in "\n".join(rows_text) and "parked" in "\n".join(rows_text)


async def test_a_hostile_parked_reason_renders_without_raising():
    rows = [_launch(status="parked", parked_reason="manifest: [[x]/y] broken"),
            _launch(launch_number=2, status="parked", parked_reason="stuck[reason")]
    text = await _launches(swarm_launch_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    first, second = _data_lines(text)[:2]
    assert "manifest:" in first and "broken" in first and "[/x]" not in text, first
    assert "stuck[reason" in second, second


async def test_a_clipped_parked_reason_lights_the_title_hint_at_the_full_tier():
    """The plan says the reason wraps; a base-rendered ``DataTable`` row is one
    line, so the cell is clipped with ``…`` and the title says so."""
    short = await _launches(swarm_launch_rows=[_launch(status="parked", parked_reason="no token")],
                            swarm_scores_as_of_hhmm=AS_OF)
    assert "no token" in short and "‹" not in short, short
    long = await _launches(swarm_launch_rows=[_launch(status="parked", parked_reason="x" * 197)],
                           swarm_scores_as_of_hhmm=AS_OF)
    assert "…" in long and "‹" in long, long


async def test_a_non_dict_row_is_skipped_and_the_cap_holds():
    """``TableLeaderboard`` caps the *items* first and skips a non-dict without
    a gap, so a junk item inside the cap costs one line and never raises."""
    clean = [_launch(launch_number=n) for n in range(20, 0, -1)]
    lines = _data_lines(await _launches((SIZE[0], 40), swarm_launch_rows=clean,
                                        swarm_scores_as_of_hhmm=AS_OF))
    assert len(lines) == 12, len(lines)
    assert lines[0].lstrip().startswith("20") and lines[-1].lstrip().startswith("9")
    lines = _data_lines(await _launches((SIZE[0], 40), swarm_launch_rows=[42] + clean,
                                        swarm_scores_as_of_hhmm=AS_OF))
    assert len(lines) == 11, len(lines)
    assert lines[0].lstrip().startswith("20") and lines[-1].lstrip().startswith("10")


# -- title and footer ------------------------------------------------------------------


async def test_the_title_carries_the_marker_only_when_it_is_real():
    assert f"LAUNCHES · as of {AS_OF}" in await _launches(swarm_launch_rows=[_launch()],
                                                         swarm_scores_as_of_hhmm=AS_OF)
    for as_of in (None, ""):
        text = await _launches(swarm_launch_rows=[_launch()], swarm_scores_as_of_hhmm=as_of)
        assert "as of" not in text and "LAUNCHES" in text


async def test_the_footer_counts_by_status_desc_and_suppresses_no_data():
    text = await _launches(swarm_launch_rows=[], swarm_launch_summary=SUMMARY,
                           swarm_scores_as_of_hhmm=AS_OF)
    for part in ("30 launches", "19 live", "10 abandoned", "1 parked"):
        assert part in text, (part, text)
    assert text.index("19 live") < text.index("10 abandoned") < text.index("1 parked")
    assert "No data" not in text


async def test_no_summary_means_no_footer():
    text = await _launches(swarm_launch_rows=[_launch()], swarm_scores_as_of_hhmm=AS_OF)
    assert "launches" not in text, text


# -- tiers ---------------------------------------------------------------------------------

_FULL = FULL_WIDTH + GUTTER + 5
_COMPACT = FULL_WIDTH + GUTTER - 1
_TIGHT = COMPACT_WIDTH + GUTTER - 1


def test_the_derived_tier_widths_land_inside_their_tiers():
    assert _COMPACT >= COMPACT_WIDTH + GUTTER
    assert _TIGHT >= TIGHT_WIDTH + GUTTER
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert ADDR_COLS > TIGHT_ADDR_COLS


async def test_compact_sheds_kind_and_tight_sheds_the_reason_and_narrows_the_address():
    row = [_launch(status="parked", parked_reason="no token")]
    full = await _launches((_FULL, 20), swarm_launch_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    compact = await _launches((_COMPACT, 20), swarm_launch_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    tight = await _launches((_TIGHT, 20), swarm_launch_rows=row, swarm_scores_as_of_hhmm=AS_OF)

    head = ADDR[: 2 + 8]           # the 17-cell window keeps 0x + 8 hex
    tight_head = ADDR[: 2 + 4] + "…"  # the 11-cell window keeps 0x + 4 hex

    assert "kind" in full and "evm_project" in full and "parked reason" in full
    assert head in full and "‹" not in full, full

    assert "kind" not in compact and "evm_project" not in compact, compact
    assert "parked reason" in compact and "no token" in compact
    assert head in compact and "‹" in compact

    assert "parked reason" not in tight and "no token" not in tight, tight
    assert head not in tight and tight_head in tight, tight
    assert COPY_GLYPH in tight and "‹" in tight
    for text in (full, compact, tight):
        assert "SEPOLIA" in text and "Identity-md/" in text, text


async def test_the_full_tier_hides_no_column_at_its_own_threshold():
    async with _Probe().run_test(size=(FULL_WIDTH + GUTTER, 20)) as pilot:
        widget = pilot.app.query_one(SurfSwarmLaunches)
        widget.update_data(swarm_launch_rows=[_launch()], swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        assert table.max_scroll_x == 0
        assert len(table.columns) == 7
        text = "\n".join("".join(seg.text for seg in strip)
                         for strip in pilot.app.screen._compositor.render_strips())
        assert re.search(r"#\s+kind\s+status\s+chain\s+repo\s+artifacts\s+parked reason", text), text
        assert "‹" not in text


async def test_the_parked_reason_column_takes_every_spare_column():
    reason = "y" * 60
    narrow = await _launches((FULL_WIDTH + GUTTER, 20), swarm_launch_rows=[_launch(parked_reason=reason)],
                             swarm_scores_as_of_hhmm=AS_OF)
    wide = await _launches((FULL_WIDTH + GUTTER + 60, 20), swarm_launch_rows=[_launch(parked_reason=reason)],
                           swarm_scores_as_of_hhmm=AS_OF)
    assert "…" in narrow and "‹" in narrow, narrow
    assert reason in wide and "‹" not in wide, wide
