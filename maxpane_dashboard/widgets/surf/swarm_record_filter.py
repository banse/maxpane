"""RECORD's ``f`` filter editor: THE LIST's editor chrome over one seat's own rows.

``docs/surf_record_filter_spec.md``. ``widgets/filter_editor.FilterEditorBase``
owns the error line, the group grid, the ranges, the dropdowns and APPLY / RESET;
this module adds the three checkbox groups whose options are the seat's own
(NODE, STATE, MODEL), rebuilt by :meth:`SurfRecordFilterEditor.load` each time
the editor opens. Several raw model ids sharing one short label share one box.

Render-only: validation (``parse_record_filter``) and the clock live in the
screen. Every label here is a third-party string and reaches its ``Checkbox`` as
a pre-built ``rich.text.Text``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.message import Message
from textual.widgets import Checkbox, Static

from maxpane_dashboard.analytics.range_filters import range_text
from maxpane_dashboard.analytics.surf_record_filter import (
    ANSWER_STATES,
    PANEL_STATES,
    WHEN_SECONDS,
    RecordFilter,
)
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.filter_editor import FilterEditorBase
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from maxpane_dashboard.widgets.surf._fmt import mmdd_hhmm, short_model
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES

__all__ = [
    "ANSWER_LABELS", "BOX_GROUPS", "PANEL_LABELS", "READ_NOTE", "RecordFilterApplyRequested",
    "RecordFilterResetRequested", "SurfRecordFilterEditor", "WHEN_LABELS", "choice_label",
    "filter_summary",
]


class RecordFilterApplyRequested(Message):
    """APPLY FILTER on RECORD's editor (THE LIST's ``FilterApplyRequested`` is curator's)."""


class RecordFilterResetRequested(Message):
    """RESET ALL on RECORD's editor: clear the draft, apply nothing."""


#: Dropdown words, keyed by the analytics vocabulary they select; a key the
#: analytics module drops or adds without a label fails at import here.
WHEN_LABELS = {"24h": "Last 24 h", "7d": "Last 7 days", "30d": "Last 30 days"}
PANEL_LABELS = {"agreed": "Agreed", "outvoted": "Outvoted", "no_quorum": "No quorum",
                "assessing": "Assessing", "blocked": "Blocked", "off_panel": "Off panel",
                "unavailable": "Unavailable"}
ANSWER_LABELS = {"replied": "Replied", "no_reply": "No reply", "not_served": "Not served",
                 "unavailable": "Unavailable"}


def _options(labels: Mapping[str, str], keys) -> tuple[tuple[str, str], ...]:
    return (("Any", "any"), *((labels[key], key) for key in keys))


_SELECTS = {
    "when": _options(WHEN_LABELS, WHEN_SECONDS),
    "panel": _options(PANEL_LABELS, PANEL_STATES),
    "answer": _options(ANSWER_LABELS, ANSWER_STATES),
}

#: The checkbox groups: value field, title, container id, what an empty group says.
BOX_GROUPS = (
    ("nodes", "NODE", "record-filter-nodes", "no nodes yet"),
    ("states", "STATE", "record-filter-states", "no states yet"),
    ("models", "MODEL", "record-filter-models", "no models read yet"),
)

#: Under the groups: why MODEL to TOK can leave rows undecided.
READ_NOTE = "MODEL to TOK need a read: rows not read yet are counted under RECORD, never hidden"

#: A box label's budget: a group is at least 14 cells, the box glyph takes 4.
_LABEL_COLS = 16


def _selected(raw: object) -> frozenset:
    """A stored box group's values; a string or a non-iterable selects nothing."""
    if raw is None or isinstance(raw, str):
        return frozenset()
    try:
        return frozenset(raw)
    except TypeError:
        return frozenset()


def choice_label(field: str, value: str) -> str:
    """The words a NODE / STATE / MODEL option shows (and RECORD's summary reuses)."""
    if field == "nodes":
        title = NODE_TITLES.get(value)
        return title.lower() if title else rowfit.clip(strip_tags(flatten(value)), _LABEL_COLS)
    if field == "models":
        return rowfit.clip(short_model(value) or strip_tags(flatten(value)), _LABEL_COLS)
    return rowfit.clip(strip_tags(flatten(value)), _LABEL_COLS)


def filter_summary(spec: RecordFilter) -> str:
    """The applied filter in RECORD's footer words: ``oracle · outvoted · since 09-25 14:00``.

    Groups in the editor's order; inside a group the ticked options read
    ``or``. WHEN is the fixed cutoff applied, never the dropdown's word.
    """
    parts = []
    for field in ("nodes", "states"):
        chosen = getattr(spec, field)
        if chosen:
            parts.append(" or ".join(sorted({choice_label(field, value) for value in chosen})))
    if spec.since_ts is not None:
        parts.append(f"since {mmdd_hhmm(spec.since_ts)}")
    if spec.models:
        parts.append(" or ".join(sorted({choice_label("models", value) for value in spec.models})))
    if spec.panel in PANEL_LABELS:
        parts.append(f"panel {PANEL_LABELS[spec.panel].lower()}")
    if spec.answer in ANSWER_LABELS:
        parts.append(ANSWER_LABELS[spec.answer].lower())
    for clause in (range_text("took ", spec.took_min, spec.took_max, unit=" min"),
                   range_text("tok ", spec.tok_min, spec.tok_max)):
        if clause:
            parts.append(clause)
    return " · ".join(parts)


class SurfRecordFilterEditor(FilterEditorBase):
    """NODE · STATE · WHEN · MODEL / PANEL · ANSWER · TOOK · TOK, ANDed."""

    ERROR_ID = "record-filter-error"
    RANGE_FIELDS = ("took_min", "took_max", "tok_min", "tok_max")
    SELECT_OPTIONS = _SELECTS
    APPLY_MESSAGE = RecordFilterApplyRequested
    RESET_MESSAGE = RecordFilterResetRequested

    #: The group gap is padding here, not THE LIST's ``margin-bottom``: a
    #: grid row is sized to its tallest group's content and the margin is then
    #: taken out of it, which costs THE LIST only its controls' blank last
    #: line but would cut a box group's last option off in silence. The
    #: compact dropdowns and from/to fields draw on one line, so they get one
    #: (the AGENT body has about sixteen rows at its pin).
    DEFAULT_CSS = """
    SurfRecordFilterEditor .filter-group {
        margin-bottom: 0;
        padding-bottom: 1;
    }
    SurfRecordFilterEditor .filter-group Select,
    SurfRecordFilterEditor .filter-group .filter-range {
        height: 1;
    }
    SurfRecordFilterEditor .filter-group .record-filter-boxes {
        height: auto;
    }
    SurfRecordFilterEditor .filter-group .record-filter-boxes Checkbox {
        height: 1;
    }
    SurfRecordFilterEditor .record-filter-empty {
        height: 1;
        color: $text-muted;
    }
    SurfRecordFilterEditor .record-filter-note {
        width: 100%;
        height: auto;
        color: $text-muted;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: Per box group: ``(checkbox id, the raw values it stands for)``, in order.
        self._boxes: dict[str, list[tuple[str, frozenset[str]]]] = {
            field: [] for field, *_rest in BOX_GROUPS
        }

    def compose(self) -> ComposeResult:
        yield self.error_line()
        boxes = {field: (title, box_id) for field, title, box_id, _empty in BOX_GROUPS}
        with Grid(classes="filter-groups"):
            for field in ("nodes", "states"):
                title, box_id = boxes[field]
                yield self.titled_group(title, Vertical(id=box_id, classes="record-filter-boxes"))
            yield self.select_group("WHEN", "when")
            title, box_id = boxes["models"]
            yield self.titled_group(title, Vertical(id=box_id, classes="record-filter-boxes"))
            yield self.select_group("PANEL", "panel")
            yield self.select_group("ANSWER", "answer")
            yield self.range_group("TOOK · minutes", (("took_min", "from"), ("took_max", "to")))
            yield self.range_group("TOK · output", (("tok_min", "from"), ("tok_max", "to")))
        # A note, not a heading: it wraps where a section title would scroll
        # the editor sideways (82 cells against a 60-column terminal).
        yield Static(Text(READ_NOTE), classes="record-filter-note")
        yield self.actions()

    async def load(self, choices: Mapping[str, Sequence[str]], values: Mapping[str, object]) -> None:
        """Rebuild the checkbox groups from *choices*, then show *values*.

        Awaited, so the previous boxes are gone before their ids are reused.
        """
        for field, _title, box_id, empty in BOX_GROUPS:
            container = self.query_one(f"#{box_id}", Vertical)
            await container.remove_children()
            selected = _selected(values.get(field))
            grouped: dict[str, set[str]] = {}
            for value in choices.get(field) or ():
                if isinstance(value, str) and value:
                    grouped.setdefault(choice_label(field, value), set()).add(value)
            entries = []
            widgets = []
            for index, (label, raw) in enumerate(grouped.items()):
                box_id_n = f"{box_id}-{index}"
                entries.append((box_id_n, frozenset(raw)))
                widgets.append(Checkbox(Text(label), value=bool(raw & selected),
                                        compact=True, id=box_id_n))
            self._boxes[field] = entries
            await container.mount_all(widgets or [Static(Text(empty), classes="record-filter-empty")])
        self.set_values(values)

    def values(self) -> dict[str, object]:
        values = super().values()
        for field, entries in self._boxes.items():
            ticked: set[str] = set()
            for box_id, raw in entries:
                if self.query_one(f"#{box_id}", Checkbox).value:
                    ticked |= raw
            values[field] = frozenset(ticked)
        return values

    def set_values(self, values: Mapping[str, object]) -> None:
        """Reset the draft, then show the supplied primitive values."""
        super().set_values(values)
        for field, entries in self._boxes.items():
            selected = _selected(values.get(field))
            for box_id, raw in entries:
                self.query_one(f"#{box_id}", Checkbox).value = bool(raw & selected)
