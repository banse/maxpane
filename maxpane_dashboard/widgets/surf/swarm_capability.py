"""CAPABILITY: the swarm's skill catalogue, one row per skill (swarm v2, WP6).

A :class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase` --
the tiered-table mechanics (width ladder, columns re-installed on a tier
change, the ``as of`` marker and widen hint in the title, ``None`` vs ``[]``,
the footer line) are the base's; this module knows the seven columns and the
summary footer.

Third-party text
----------------
Skill ids, versions, roles, tiers, judges, checks and every ``requires`` entry
are strings the swarm's operators chose; each goes through
``markup_safety.sanitize_cell`` (flatten, strip bracket runs, clip on
``cell_len``, escape) before it meets the table, and a footer word through
``strip_tags`` into the base's pre-built ``rich.text.Text``. A complete
``[/x]`` run is therefore *removed*, not shown -- ``rules/widgets.md``'s
sanitiser contract, which wins over a brief's "renders literally" (a lone
``[`` does render literally).

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules
only. No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.surf._fmt import DASH
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols

__all__ = [
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "TIGHT_WIDTH",
    "SurfSwarmCapability",
]

# -- CAPABILITY -------------------------------------------------------------

# Column budgets, in rendered cells, measured against the committed corpus
# ``tests/fixtures/surf/swarm/v2/skills.json`` (30 skills, 2026-09-21). The
# vocabulary is the operators' and not closed, so a value that outgrows its
# cell is clipped with a visible ``…`` by ``sanitize_cell``, never a reason
# to move a pin.

#: ``skill``: the widest captured id is 24 cells; fits whole.
_SKILL_COLS = 24
#: ``v``: an int version (``2`` today); three cells hold ``999``.
_VERSION_COLS = 3
#: ``role``: ``reference`` (9) is the widest of implement/integrate/reference/
#: review/tests.
_ROLE_COLS = 9
#: ``tier``: one digit or ``--``; the header itself is the widest thing (4).
_TIER_COLS = 4
#: ``judge``: ``verifier-paths`` / ``verifier-rerun`` (14).
_JUDGE_COLS = 14
#: ``checks``: a str ≤ 7 today (``foundry``) or null -> ``--``.
_CHECKS_COLS = 7
#: ``requires``: entries are capability tokens (``network``, ``tool:audio``,
#: ``runtime:codex`` -- 13, the widest) and no skill lists more than one
#: today; ``, ``-joined when one does, clipped visibly then. Never shed: the
#: plan calls this column the point of the panel.
_REQUIRES_COLS = 14

_SPECS = (
    ("skill", "skill", _SKILL_COLS),
    ("version", "v", _VERSION_COLS),
    ("role", "role", _ROLE_COLS),
    ("tier", "tier", _TIER_COLS),
    ("judge", "judge", _JUDGE_COLS),
    ("checks", "checks", _CHECKS_COLS),
    ("requires", "requires", _REQUIRES_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "checks")
_TIGHT = tuple(key for key in _COMPACT if key != "judge")

#: ``full``: all seven columns -- 89 cells. The table's own need; the panel
#: adds :attr:`SwarmTableBase.GUTTER_COLS` for its scrollbar (the catalogue is
#: 30 rows and scrolls in any body-sized slot).
FULL_WIDTH = table_cols(w for k, _l, w in _SPECS)                    # 89
#: ``compact``: ``checks`` shed (the cheapest column that is not the point of
#: the panel) -- 80.
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)  # 80
#: ``tight``: ``judge`` shed too; ``requires`` stays at every tier -- 64.
TIGHT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _TIGHT)      # 64


def _requires_cell(value) -> str:
    """``requires`` as ``a, b``; ``--`` for ``[]``/``None``; a str passes as is."""
    if isinstance(value, (list, tuple)):
        parts = [strip_tags(entry) for entry in value]
        joined = ", ".join(part for part in parts if part)
    else:
        joined = strip_tags(value)
    return sanitize_cell(joined, _REQUIRES_COLS) or DASH


class SurfSwarmCapability(SwarmTableBase):
    """CAPABILITY -- ``skill · v · role · tier · judge · checks · requires``."""

    TITLE = "CAPABILITY"
    TABLE_ID = "surf-swarm-capability-table"
    #: The catalogue is the content: every skill, no cap (30 today).
    ROW_CAP = None
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING, "", "", "", "", "", "")
    EMPTY_ROW = ("No data", "", "", "", "", "", "")

    def update_data(
        self,
        swarm_skill_rows=None,
        swarm_skill_summary=None,
        swarm_scores_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``SWARM_WIDGET_SIGNATURES``)."""
        self.store(swarm_skill_rows, swarm_scores_as_of_hhmm, swarm_skill_summary)

    def build_cells(self, item: dict) -> dict[str, str]:
        return {
            "skill": sanitize_cell(item.get("skill_id"), _SKILL_COLS) or DASH,
            "version": fmt_int(item.get("version")),
            "role": sanitize_cell(item.get("role"), _ROLE_COLS) or DASH,
            "tier": fmt_int(item.get("tier")),
            "judge": sanitize_cell(item.get("judge"), _JUDGE_COLS) or DASH,
            "checks": sanitize_cell(item.get("checks"), _CHECKS_COLS) or DASH,
            "requires": _requires_cell(item.get("requires")),
        }

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """``30 skills · 19 implement · 7 reference · … · 11 requires``."""
        if not isinstance(summary, dict):
            return None
        parts = [f"{fmt_int(summary.get('total'))} skills"]
        by_role = summary.get("by_role")
        if isinstance(by_role, list):
            counted = [
                entry for entry in by_role
                if isinstance(entry, dict) and fmt_int(entry.get("count")) != DASH
            ]
            counted.sort(key=lambda entry: -int(entry.get("count")))
            parts.extend(
                f"{fmt_int(entry.get('count'))} {strip_tags(entry.get('role')) or DASH}"
                for entry in counted
            )
        parts.append(f"{fmt_int(summary.get('requires_count'))} requires")
        return tuple(parts)
