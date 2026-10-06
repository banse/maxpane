"""LAUNCHES: production first, token-first artifacts and evidence verdicts.

Rows retain their own chain explorer; Sepolia is dim and production has a
bold diamond cue. The popup receives a deep copy through SwarmTableBase.
"""
from __future__ import annotations

from maxpane_dashboard.widgets.surf._launch_liquidity import liquidity_cell

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import ICON_COLS, MIN_SHORT_COLS, address_text, is_address
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.analytics.surf_swarm_signals import launch_verdict_label
from maxpane_dashboard.widgets.address import site_text
from maxpane_dashboard.widgets.surf._fmt import SITE_EXPLORER
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.surf._fmt import DASH
from maxpane_dashboard.widgets.surf._swarm_chain import CHAIN_COLS, chain_word
from maxpane_dashboard.widgets.surf._swarm_table import (
    CELL_PADDING,
    SwarmTableBase,
    table_cols,
)

__all__ = [
    "ADDR_COLS",
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "PARKED_MIN_COLS",
    "TIGHT_ADDR_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmLaunches",
]

# Rendered cell budgets, excluding DataTable's two padding cells per column.
_NUMBER_COLS = 6
_TICKER_COLS = 11  # A3.2: compact symbol or launch-number fallback.
_SITE_COLS = 16  # A3.2: linked site label, clipped before its table boundary.
_VERDICT_COLS = 10  # A3.2: the longest verdict, "-- pending".
_KIND_COLS = 13
_STATUS_COLS = 9
_REPO_COLS = 24
ADDR_COLS = 17
TIGHT_ADDR_COLS = MIN_SHORT_COLS
_PLUS_COLS = 4
_ARTIFACTS_COLS = ADDR_COLS + ICON_COLS + _PLUS_COLS  # 23
_TIGHT_ARTIFACTS_COLS = TIGHT_ADDR_COLS + ICON_COLS + _PLUS_COLS  # 17
PARKED_MIN_COLS = len("parked reason")  # 13, elastic above this floor
_TIGHT_REPO_COLS = _REPO_COLS

_SPECS = (
    ("number", "#", _NUMBER_COLS),
    ("ticker", "ticker", _TICKER_COLS),
    ("status", "status", _STATUS_COLS),
    ("chain", "chain", CHAIN_COLS),
    ("token", "token", _ARTIFACTS_COLS),
    ("site", "site", _SITE_COLS),
    ("verdict", "verdict", _VERDICT_COLS),
    ("liq", "liq", 12),
    ("kind", "kind", _KIND_COLS),
    ("repo", "repo", _REPO_COLS),
    ("parked", "parked reason", PARKED_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_ROOMY = tuple(key for key in _ALL if key != "liq")
_COMPACT = tuple(key for key in _ALL if key not in ("kind", "repo", "liq"))
_TIGHT = tuple(key for key in _COMPACT if key not in ("parked", "site"))
# full: 144 cells + 22 padding = 166; roomy: 132 + 20 = 152;
# compact: 95 + 16 = 111;
# tight: 60 + 12 = 72 (token shrinks from 23 to 17).
FULL_WIDTH = table_cols(w for k, _l, w in _SPECS)
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)
TIGHT_WIDTH = table_cols(_TIGHT_ARTIFACTS_COLS if k == "token" else w
                         for k, _l, w in _SPECS if k in _TIGHT)

#: Colour looked up on the **raw** status word; the text beside it is escaped.
_STATUS_COLOURS = {"live": "green", "admitted": "yellow", "parked": "yellow", "abandoned": "dim"}

#: The one host whose prefix is dropped to ``owner/name`` -- exactly this
#: string, so ``https://github.com.evil.example/…`` keeps its full form.
_GITHUB = "https://github.com/"


def _repo_label(url, cols: int = _REPO_COLS) -> str:
    if not isinstance(url, str) or not url:
        return DASH
    prefix = "https://github.com/identity-md-launches/"
    shown = url[len(prefix):] if url.startswith(prefix) else (url[len(_GITHUB):] if url.startswith(_GITHUB) else url)
    return sanitize_cell(shown, cols) or DASH


def _artifacts_cell(item: dict, addr_cols: int) -> Text | str:
    """Token, hook, then first artifact: one copy/link unit and the rest count."""
    artifacts = item.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return DASH
    first = next((a for role in ("token", "hook") for a in artifacts
                  if isinstance(a, dict) and a.get("role") == role), artifacts[0])
    explorer = for_chain_id(item.get("chain_id"))
    if isinstance(first, dict) and is_address(first.get("address")):
        cell = address_text(first["address"], width=addr_cols, explorer=explorer)
    elif isinstance(first, dict):
        name = strip_tags(first.get("name")) or DASH
        cell = Text(rowfit.clip(name, addr_cols + ICON_COLS))
    else:
        cell = Text(DASH)
    count = item.get("artifact_count")
    total = count if isinstance(count, int) and not isinstance(count, bool) else len(artifacts)
    if total > 1:
        cell.append(rowfit.clip(f" +{total - 1}", _PLUS_COLS), style="dim")
    return cell


class SurfSwarmLaunches(SwarmTableBase):
    """Production-first launches with token, site and attestation verdict."""

    TITLE = "LAUNCHES"
    TABLE_ID = "surf-swarm-launches-table"
    #: Twelve production rows followed by twelve non-production rows, each newest first.
    ROW_CAP = 24
    SELECTABLE = True

    class Selected(SwarmTableBase.Selected):
        pass
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "roomy": _ROOMY, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("roomy", FULL_WIDTH - 14), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING,) + ("",) * 10
    EMPTY_ROW = ("--", "No data") + ("",) * 9

    def update_data(
        self,
        swarm_launch_rows=None,
        swarm_launch_summary=None,
        swarm_scores_as_of_hhmm=None,
        swarm_network=None,
        swarm_launches_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict. ``swarm_network`` is accepted
        and never painted: the chain word is per row (module docstring)."""
        if isinstance(swarm_launch_rows, list):
            ordered = sorted((r for r in swarm_launch_rows if isinstance(r, dict)),
                             key=lambda r: r.get("launch_number") if type(r.get("launch_number")) is int else -1, reverse=True)
            production = [r for r in ordered if r.get("production") is True][:12]
            other = [r for r in ordered if r.get("production") is not True][:12]
            swarm_launch_rows = production + other
        self.store(swarm_launch_rows, swarm_launches_as_of_hhmm, swarm_launch_summary)

    def column_plan(self, tier: str, budget: int) -> tuple[tuple[str, str, int], ...]:
        """Elastic reason; tight keeps ticker/verdict and narrows the token."""
        plan = []
        keep = self.TIER_COLUMNS[tier]
        tier_width = dict(self.LADDER.steps)[tier]
        if tier != "full" and budget >= tier_width + 14:
            keep = (*keep, "liq")
        fixed = [w for k, _l, w in _SPECS if k in keep and k != "parked"]
        if tier == "tight":
            fixed = [
                _TIGHT_ARTIFACTS_COLS if w == _ARTIFACTS_COLS else
                _TIGHT_REPO_COLS if w == _REPO_COLS else w
                for w in fixed
            ]
        spare = budget - table_cols(fixed) - CELL_PADDING
        for key, label, width in _SPECS:
            if key not in keep:
                continue
            if key == "token" and tier == "tight":
                width = _TIGHT_ARTIFACTS_COLS
            elif key == "repo" and tier == "tight":
                width = _TIGHT_REPO_COLS
            elif key == "parked":
                width = max(PARKED_MIN_COLS, spare)
            plan.append((key, label, width))
        return tuple(plan)

    def _parked_cols(self) -> int:
        return next((w for k, _l, w in (self._installed or ()) if k == "parked"), PARKED_MIN_COLS)

    def build_cells(self, item: dict) -> dict[str, str | Text]:
        raw_status = item.get("status")
        status = sanitize_cell(raw_status, _STATUS_COLS) or DASH
        colour = _STATUS_COLOURS.get(raw_status) if isinstance(raw_status, str) else None
        if colour:
            status = f"[{colour}]{status}[/]"

        addr_cols = TIGHT_ADDR_COLS if self._tier == "tight" else ADDR_COLS
        repo_cols = _TIGHT_REPO_COLS if self._tier == "tight" else _REPO_COLS

        parked_cols = self._parked_cols()
        reason = strip_tags(item.get("parked_reason"))
        if cell_len(reason) > parked_cols and "parked" in self._keys:
            self._clipped = True
        number = item.get("launch_number")
        number_text = str(number) if isinstance(number, int) and not isinstance(number, bool) else DASH
        production = item.get("production") is True
        if production:
            number_text = "◆ " + number_text
        if cell_len(number_text) > _NUMBER_COLS:
            self._clipped = True
        ticker = DASH
        if production and item.get("kind") != "evm_contracts":
            ticker = "$" + flatten(item["ticker"]) if item.get("ticker") else f"#{number}"
        cells = {
            "number": rowfit.clip(number_text, _NUMBER_COLS),
            "kind": sanitize_cell(item.get("kind"), _KIND_COLS) or DASH,
            "status": status,
            "chain": sanitize_cell(chain_word(item.get("chain_id")), CHAIN_COLS),
            "repo": _repo_label(item.get("repo_url"), repo_cols),
            "token": _artifacts_cell(item, addr_cols),
            "ticker": Text(rowfit.clip(ticker, _TICKER_COLS)),
            "site": site_text(item.get("site_ens_name") or item.get("site_label"), _SITE_COLS, label=item.get("site_label"), explorer=SITE_EXPLORER)
                    if item.get("site_label") or item.get("site_ens_name") else Text(DASH),
            "verdict": Text(rowfit.clip(launch_verdict_label(item.get("verdict")) if production else DASH, _VERDICT_COLS), style={
                "swarm": "green", "mismatch": "red", "failed": "red",
            }.get((item.get("verdict") or {}).get("state"), "dim") if production else "dim"),
            "liq": liquidity_cell(item),
            "parked": sanitize_cell(reason, parked_cols),
        }

        for key, value in cells.items():
            text = value.copy() if isinstance(value, Text) else Text.from_markup(value)
            text.stylize("bold" if production else "dim")
            cells[key] = text
        return cells

    BLANK_FOOTER = True
