"""CAPABILITY (``widgets/surf/swarm_capability.py``), swarm v2 WP6.

Unwired until WP7, so the contract test's per-class checks do not see this
class yet; the three checks ``widget_wp_common.md`` names are imposed here,
bound to the frozen export ``SWARM_WIDGET_SIGNATURES["SurfSwarmCapability"]``.
Every assertion is against composited output (``rules/widgets.md``).
"""

from __future__ import annotations

import inspect
import re

from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.surf.swarm_capability import (
    COMPACT_WIDTH,
    FULL_WIDTH,
    TIGHT_WIDTH,
    SurfSwarmCapability,
)
from tests.widgets.surf_compositing import composite_lines

SIG = SWARM_WIDGET_SIGNATURES["SurfSwarmCapability"]
ROW_KEYS = SURF_ROW_KEYS["swarm_skill_rows"]
GUTTER = SurfSwarmCapability.GUTTER_COLS

#: Wide enough for the ``full`` tier and tall enough for the whole catalogue.
SIZE = (120, 40)
AS_OF = "04:06"


def _row(**over) -> dict:
    """One skill row in the frozen ``swarm_skill_rows`` shape (corpus values)."""
    row = dict(
        skill_id="build-contract-project", version=2, role="implement", kind="code",
        tier=1, judge="verifier-rerun", checks="foundry", requires=[],
    )
    row.update(over)
    return row


SUMMARY = {
    "total": 30,
    "by_role": [
        {"role": "reference", "count": 7}, {"role": "implement", "count": 19},
        {"role": "tests", "count": 2}, {"role": "review", "count": 1},
        {"role": "integrate", "count": 1},
    ],
    "by_judge": [{"judge": "verifier-paths", "count": 14}],
    "requires_count": 11,
}


async def _cap(size=SIZE, **kwargs) -> str:
    return "\n".join(await composite_lines(SurfSwarmCapability, size, **kwargs))


def _data_lines(text: str) -> list[str]:
    """Painted rows under the header, excluding the title/blank/header rows."""
    lines = text.split("\n")
    header = next(i for i, line in enumerate(lines) if "skill" in line and "role" in line)
    return [line for line in lines[header + 1:] if line.strip()]


# -- the frozen contract ------------------------------------------------------------


def test_the_hand_row_is_the_frozen_shape():
    assert set(_row()) == set(ROW_KEYS) and len(_row()) == len(ROW_KEYS)


def test_update_data_names_exactly_the_frozen_signature_and_takes_kwargs():
    params = list(inspect.signature(SurfSwarmCapability.update_data).parameters.values())
    named = [p.name for p in params if p.kind is not p.VAR_KEYWORD and p.name != "self"]
    assert tuple(named) == SIG
    assert any(p.kind is p.VAR_KEYWORD for p in params), "the screen splats the whole dict"


async def test_no_args_and_all_none_render_unavailable_not_no_data():
    for kwargs in ({}, {key: None for key in SIG}):
        text = await _cap(**kwargs)
        assert "unavailable" in text, text
        assert "No data" not in text, text
        assert "CAPABILITY" in text


async def test_an_empty_list_is_a_real_negative_and_differs_from_none():
    text = await _cap(swarm_skill_rows=[], swarm_scores_as_of_hhmm=AS_OF)
    assert "No data" in text, text
    assert "unavailable" not in text, text


def test_the_row_tuples_agree_with_the_column_count():
    width = len(SurfSwarmCapability.COLUMNS)
    assert width == len(SurfSwarmCapability.COLUMN_SPECS) == 7
    assert len(SurfSwarmCapability.EMPTY_ROW) == width
    assert len(SurfSwarmCapability.LOADING_ROW) == width


# -- cells ---------------------------------------------------------------------------


async def test_null_tier_and_judge_render_a_dash_never_none():
    text = await _cap(swarm_skill_rows=[_row(tier=None, judge=None, checks=None)],
                      swarm_scores_as_of_hhmm=AS_OF)
    line = _data_lines(text)[0]
    assert "None" not in text
    assert line.count("--") == 4, line  # tier, judge, checks and the empty requires


async def test_requires_is_joined_and_empty_is_a_dash():
    """No captured skill lists two entries; a pair joins with ``, `` and, at 19
    cells against the 14-cell column, clips with a visible ``…``."""
    text = await _cap(swarm_skill_rows=[_row(requires=["network", "tool:audio"]), _row(requires=[]),
                                        _row(requires=["runtime:codex"])],
                      swarm_scores_as_of_hhmm=AS_OF)
    first, second, third = _data_lines(text)[:3]
    assert "network, tool" in first and "…" in first, first
    assert "tool:audio" not in first
    assert second.rstrip().endswith("--"), second
    assert "runtime:codex" in third, third


async def test_a_hostile_skill_id_renders_literally_and_never_raises():
    """A lone ``[`` is not a tag and is escaped so it prints; a complete ``[/x]``
    run and a ``[$success]`` theme token are stripped rather than parsed."""
    rows = [_row(skill_id="oracle[assess"), _row(skill_id="[/x]oracle"),
            _row(skill_id="[$success]theme", role="[$warning]")]
    text = await _cap(swarm_skill_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert "oracle[assess" in lines[0], lines[0]
    assert "oracle" in lines[1] and "[/x]" not in text
    assert "theme" in lines[2]


async def test_a_non_dict_row_is_skipped_and_the_rest_land():
    text = await _cap(swarm_skill_rows=[42, _row(), "junk", _row(skill_id="second")],
                      swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 2, lines
    assert "second" in lines[1]


async def test_the_catalogue_is_not_capped():
    rows = [_row(skill_id=f"skill-{i:02d}") for i in range(30)]
    text = await _cap(swarm_skill_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    assert "skill-29" in text, "ROW_CAP must be None: the catalogue is the content"


# -- title -----------------------------------------------------------------------------


async def test_the_title_carries_the_marker_only_when_it_is_real():
    with_marker = await _cap(swarm_skill_rows=[_row()], swarm_scores_as_of_hhmm=AS_OF)
    assert f"CAPABILITY · as of {AS_OF}" in with_marker
    for as_of in (None, ""):
        text = await _cap(swarm_skill_rows=[_row()], swarm_scores_as_of_hhmm=as_of)
        assert "as of" not in text, text
        assert "CAPABILITY" in text


# -- footer ----------------------------------------------------------------------------


async def test_the_footer_summarises_the_catalogue_by_role_count_desc():
    text = await _cap(swarm_skill_rows=[_row()], swarm_skill_summary=SUMMARY,
                      swarm_scores_as_of_hhmm=AS_OF)
    for part in ("30 skills", "19 implement", "7 reference", "2 tests", "11 requires"):
        assert part in text, (part, text)
    assert text.index("19 implement") < text.index("7 reference") < text.index("2 tests")


async def test_the_footer_is_one_line_clipped_to_the_panel_not_a_table_row():
    """83 cells of summary against a widest cell of 24: the footer is a line
    under the table, clipped once to the panel's width with a visible ``…``."""
    lines = (await _cap(swarm_skill_rows=[_row()], swarm_skill_summary=SUMMARY,
                        swarm_scores_as_of_hhmm=AS_OF)).split("\n")
    footer = next(line for line in lines if "30 skills" in line)
    assert "11 requires" in footer, footer
    assert footer.index("30 skills") < footer.index("19 implement") < footer.index("11 requires")
    narrow = (await _cap((TIGHT_WIDTH + GUTTER, 40), swarm_skill_rows=[_row()],
                         swarm_skill_summary=SUMMARY, swarm_scores_as_of_hhmm=AS_OF)).split("\n")
    footer = next(line for line in narrow if "30 skills" in line)
    assert "…" in footer and "11 requires" not in footer, footer
    assert len(footer.rstrip()) <= TIGHT_WIDTH + GUTTER


async def test_a_footer_suppresses_no_data_when_there_are_no_rows():
    text = await _cap(swarm_skill_rows=[], swarm_skill_summary=SUMMARY,
                      swarm_scores_as_of_hhmm=AS_OF)
    assert "30 skills" in text
    assert "No data" not in text, text


async def test_no_summary_means_no_footer():
    text = await _cap(swarm_skill_rows=[_row()], swarm_skill_summary=None,
                      swarm_scores_as_of_hhmm=AS_OF)
    assert "skills" not in text, text


async def test_a_hostile_role_word_in_the_summary_is_stripped_not_parsed():
    summary = dict(SUMMARY, by_role=[{"role": "[/x]implement", "count": 19}])
    text = await _cap(swarm_skill_rows=[_row()], swarm_skill_summary=summary,
                      swarm_scores_as_of_hhmm=AS_OF)
    assert "19 implement" in text and "[/x]" not in text


# -- tiers -----------------------------------------------------------------------------

_FULL = FULL_WIDTH + GUTTER + 5
_COMPACT = FULL_WIDTH + GUTTER - 1
_TIGHT = COMPACT_WIDTH + GUTTER - 1


def test_the_derived_tier_widths_land_inside_their_tiers():
    assert _COMPACT >= COMPACT_WIDTH + GUTTER
    assert _TIGHT >= TIGHT_WIDTH + GUTTER
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0


async def test_requires_survives_every_tier_while_checks_then_judge_shed():
    row = [_row(requires=["network"])]
    full = await _cap((_FULL, 20), swarm_skill_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    compact = await _cap((_COMPACT, 20), swarm_skill_rows=row, swarm_scores_as_of_hhmm=AS_OF)
    tight = await _cap((_TIGHT, 20), swarm_skill_rows=row, swarm_scores_as_of_hhmm=AS_OF)

    for text in (full, compact, tight):
        assert "requires" in text and "network" in text, text

    assert "checks" in full and "judge" in full and "foundry" in full
    assert "‹" not in full

    assert "checks" not in compact and "foundry" not in compact, compact
    assert "judge" in compact and "verifier-rerun" in compact
    assert "‹" in compact

    assert "judge" not in tight and "verifier-rerun" not in tight, tight
    assert "checks" not in tight
    assert "‹" in tight


async def test_the_full_tier_hides_no_column_at_its_own_threshold():
    """The threshold is arithmetic over the column constants; this measures it
    in situ -- the table must not be scrolling a column out of view."""

    class _A(App):
        def compose(self):
            yield SurfSwarmCapability()

    async with _A().run_test(size=(FULL_WIDTH + GUTTER, 20)) as pilot:
        widget = pilot.app.query_one(SurfSwarmCapability)
        widget.update_data(swarm_skill_rows=[_row(requires=["network"])],
                           swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        assert table.max_scroll_x == 0
        assert len(table.columns) == 7
        text = "\n".join("".join(seg.text for seg in strip)
                         for strip in pilot.app.screen._compositor.render_strips())
        assert re.search(r"skill\s+v\s+role\s+tier\s+judge\s+checks\s+requires", text), text
        assert "‹" not in text
