"""Render-only custom filter controls for THE LIST's curator view."""

from __future__ import annotations

from typing import Mapping

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.css.query import NoMatches
from textual.widgets import Checkbox, Input, Label, Select, Static


RANGE_FIELDS = (
    (
        "JOIN",
        (
            ("join_min", "join from"),
            ("join_max", "join to"),
            ("hour_min", "hour from"),
            ("hour_max", "hour to"),
        ),
    ),
    (
        "SCORE",
        (
            ("rank_min", "rank from"),
            ("rank_max", "rank to"),
            ("points_min", "points from"),
            ("points_max", "points to"),
        ),
    ),
    (
        "CONTRIBUTION",
        (
            ("credit_min", "credit from"),
            ("credit_max", "credit to"),
            ("weight_min", "weight from"),
            ("weight_max", "weight to"),
            ("deposits_min", "deposits from"),
            ("deposits_max", "deposits to"),
        ),
    ),
)

FAMILIES = ("amount", "sequence", "cadence", "gas", "funding")
FAMILY_LABELS = {
    "amount": "matching amounts",
    "sequence": "consecutive joins",
    "cadence": "cadence",
    "gas": "gas fingerprint",
    "funding": "shared funding",
}

_RANGE_NAMES = tuple(
    field for _category, fields in RANGE_FIELDS for field, _label in fields
)
_SELECT_OPTIONS = {
    "ens": (("Any", "any"), ("Set", "set"), ("Unset", "unset")),
    "window": (("Any", "any"), ("Grace", "grace"), ("Judged", "judged")),
    "band": (
        ("Any", "any"),
        ("Clean", "clean"),
        ("Low", "low"),
        ("High", "high"),
        ("Unknown", "unknown"),
    ),
}


class CuratorListFilterEditor(Vertical):
    """A primitive-value editor; validation and filtering live outside it."""

    DEFAULT_CSS = """
    CuratorListFilterEditor {
        width: 100%;
        height: 100%;
        padding: 0 2;
        overflow-y: auto;
    }
    CuratorListFilterEditor .curator-filter-category {
        height: auto;
        margin-bottom: 1;
    }
    CuratorListFilterEditor .curator-filter-fields {
        height: auto;
        layout: grid;
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-gutter: 0 1;
    }
    CuratorListFilterEditor .curator-filter-field {
        width: 100%;
        min-width: 14;
    }
    CuratorListFilterEditor.compact-filter .curator-filter-fields {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    CuratorListFilterEditor .filter-invalid {
        border: tall $error;
    }
    CuratorListFilterEditor #curator-filter-error {
        height: 1;
        color: $error;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._error_field: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="curator-filter-error", markup=False)
        for category, fields in RANGE_FIELDS:
            with Vertical(classes="curator-filter-category"):
                yield Label(category)
                with Grid(classes="curator-filter-fields"):
                    for field, placeholder in fields:
                        yield Input(
                            placeholder=placeholder,
                            type="number",
                            valid_empty=True,
                            compact=True,
                            id=f"filter-{field.replace('_', '-')}",
                            classes="curator-filter-field",
                        )
        with Vertical(classes="curator-filter-category"):
            yield Label("IDENTITY")
            with Grid(classes="curator-filter-fields"):
                yield Select(
                    _SELECT_OPTIONS["ens"],
                    allow_blank=False,
                    value="any",
                    compact=True,
                    id="filter-ens",
                    classes="curator-filter-field",
                )
        with Vertical(classes="curator-filter-category"):
            yield Label("WINDOW")
            with Grid(classes="curator-filter-fields"):
                yield Select(
                    _SELECT_OPTIONS["window"],
                    allow_blank=False,
                    value="any",
                    compact=True,
                    id="filter-window",
                    classes="curator-filter-field",
                )
                yield Select(
                    _SELECT_OPTIONS["band"],
                    allow_blank=False,
                    value="any",
                    compact=True,
                    id="filter-band",
                    classes="curator-filter-field",
                )
                yield Checkbox(
                    "whale deposits",
                    compact=True,
                    id="filter-whale",
                    classes="curator-filter-field",
                )
        with Vertical(classes="curator-filter-category"):
            yield Label("LINKED PATTERNS")
            with Grid(classes="curator-filter-fields"):
                for family in FAMILIES:
                    yield Checkbox(
                        FAMILY_LABELS[family],
                        compact=True,
                        id=f"filter-family-{family}",
                        classes="curator-filter-field",
                    )

    def on_resize(self, _event=None) -> None:
        self.set_class(self.content_size.width < 100, "compact-filter")

    def values(self) -> dict[str, object]:
        """Return the raw values expected by the pure filter model."""
        values: dict[str, object] = {
            field: self.query_one(
                f"#filter-{field.replace('_', '-')}", Input
            ).value
            for field in _RANGE_NAMES
        }
        values.update(
            {
                field: self.query_one(f"#filter-{field}", Select).value
                for field in _SELECT_OPTIONS
            }
        )
        values["whale"] = self.query_one("#filter-whale", Checkbox).value
        values["families"] = frozenset(
            family
            for family in FAMILIES
            if self.query_one(f"#filter-family-{family}", Checkbox).value
        )
        return values

    def set_values(self, values: Mapping[str, object]) -> None:
        """Reset the draft, then show the supplied primitive values."""
        for field in _RANGE_NAMES:
            self.query_one(
                f"#filter-{field.replace('_', '-')}", Input
            ).value = ""
        for field in _SELECT_OPTIONS:
            self.query_one(f"#filter-{field}", Select).value = "any"
        self.query_one("#filter-whale", Checkbox).value = False
        for family in FAMILIES:
            self.query_one(f"#filter-family-{family}", Checkbox).value = False

        for field in _RANGE_NAMES:
            value = values.get(field)
            if value is not None:
                self.query_one(
                    f"#filter-{field.replace('_', '-')}", Input
                ).value = str(value)
        for field, options in _SELECT_OPTIONS.items():
            value = values.get(field, "any")
            allowed = {option for _label, option in options}
            if isinstance(value, str) and value in allowed:
                self.query_one(f"#filter-{field}", Select).value = value
        self.query_one("#filter-whale", Checkbox).value = values.get("whale") is True
        raw_families = values.get("families", frozenset())
        try:
            families = frozenset(raw_families)
        except TypeError:
            families = frozenset()
        for family in FAMILIES:
            self.query_one(f"#filter-family-{family}", Checkbox).value = family in families

    def clear_error(self) -> None:
        """Clear the visible error and its field marker."""
        if self._error_field is not None:
            try:
                self.query_one(
                    f"#filter-{self._error_field.replace('_', '-')}"
                ).remove_class("filter-invalid")
            except NoMatches:
                pass
        self.query_one("#curator-filter-error", Static).update("")
        self._error_field = None

    def show_error(self, field: str | None, message: str) -> None:
        """Name one invalid control, if it exists, and keep focus on it."""
        self.clear_error()
        self._error_field = field
        if field is not None:
            try:
                control = self.query_one(f"#filter-{field.replace('_', '-')}")
            except NoMatches:
                control = None
            if control is not None:
                control.add_class("filter-invalid")
                control.focus()
        self.query_one("#curator-filter-error", Static).update(message)
