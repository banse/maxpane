"""Shared chrome for a primitive-value filter editor: THE LIST's ``f``, surf RECORD's ``f``.

Hoisted out of ``widgets/curator/list_filter.py`` when surf's RECORD filter needed the
same editor (``docs/surf_record_filter_spec.md``). The base owns what both carry: the
error line, the titled-group grid (four columns, two below :attr:`COMPACT_BELOW` content
columns), from/to range inputs, ``any``-defaulted selects, the APPLY FILTER / RESET ALL
row, ``values()`` / ``set_values()`` over the declared :attr:`RANGE_FIELDS` and
:attr:`SELECT_OPTIONS`, and the error marker. Validation and filtering live outside it:
the editor hands primitive values up and shows the error it is told about.

Each subclass posts its **own** apply/reset messages (:attr:`APPLY_MESSAGE`,
:attr:`RESET_MESSAGE`) -- THE LIST's are curator's alone
(``tests/test_curator_registration.py``'s CR-01 guard). Textual dispatches a handler on
every class in the MRO, so a subclass never overrides ``on_button_pressed``: it handles
its own buttons in :meth:`other_button_pressed`.
"""

from __future__ import annotations

from typing import ClassVar, Mapping

from textual.containers import Grid, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

APPLY_ID = "filter-apply"
RESET_ID = "filter-reset-all"


def field_id(field: str) -> str:
    """The control id for a value field: ``join_min`` -> ``filter-join-min``."""
    return f"filter-{field.replace('_', '-')}"


class FilterEditorBase(Vertical):
    """A primitive-value editor; a subclass declares its fields and composes its groups."""

    #: The error line's id; curator keeps ``curator-filter-error``.
    ERROR_ID: ClassVar[str] = "filter-error"
    #: Every from/to ``Input`` the editor composes, by value field.
    RANGE_FIELDS: ClassVar[tuple[str, ...]] = ()
    #: Every ``Select`` the editor composes: field -> ``(label, value)`` options, ``any`` first.
    SELECT_OPTIONS: ClassVar[Mapping[str, tuple[tuple[str, str], ...]]] = {}
    APPLY_MESSAGE: ClassVar[type[Message]]
    RESET_MESSAGE: ClassVar[type[Message]]
    #: Content columns under which the group grid drops to two columns.
    COMPACT_BELOW: ClassVar[int] = 100

    DEFAULT_CSS = """
    FilterEditorBase {
        width: 100%;
        height: 100%;
        padding: 0 2;
        overflow-y: auto;
    }
    FilterEditorBase .filter-groups {
        height: auto;
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-gutter: 0 1;
    }
    FilterEditorBase.compact-filter .filter-groups {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    FilterEditorBase .filter-group {
        height: auto;
        min-width: 14;
        margin-bottom: 1;
    }
    FilterEditorBase .filter-group-title,
    FilterEditorBase .filter-section-title {
        height: 1;
        color: $text-muted;
    }
    FilterEditorBase .filter-range {
        height: 3;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 1;
    }
    FilterEditorBase .filter-group Select,
    FilterEditorBase .filter-group Checkbox {
        height: 3;
    }
    FilterEditorBase .filter-field {
        width: 100%;
        min-width: 14;
    }
    FilterEditorBase .filter-actions {
        width: 100%;
        height: 3;
        align: center middle;
    }
    FilterEditorBase .filter-actions Button {
        margin: 0 1;
    }
    FilterEditorBase .filter-invalid {
        border: tall $error;
    }
    FilterEditorBase .filter-error {
        height: 1;
        color: $error;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._error_field: str | None = None

    # -- builders -----------------------------------------------------------

    def error_line(self) -> Static:
        return Static("", id=self.ERROR_ID, classes="filter-error", markup=False)

    @staticmethod
    def titled_group(title: str, *controls: Widget) -> Vertical:
        return Vertical(
            Label(title, classes="filter-group-title"),
            *controls,
            classes="filter-group",
        )

    def range_group(self, title: str, fields: tuple[tuple[str, str], ...]) -> Vertical:
        """A titled from/to pair: ``fields`` is ``((field, placeholder), …)``."""
        return self.titled_group(
            title,
            Grid(*(
                Input(
                    placeholder=placeholder,
                    type="number",
                    valid_empty=True,
                    compact=True,
                    id=field_id(field),
                    classes="filter-field",
                )
                for field, placeholder in fields
            ), classes="filter-range"),
        )

    def select_group(self, title: str, field: str) -> Vertical:
        return self.titled_group(
            title,
            Select(
                self.SELECT_OPTIONS[field], allow_blank=False,
                value="any", compact=True,
                id=field_id(field),
                classes="filter-field",
            ),
        )

    @staticmethod
    def section_title(text: str) -> Label:
        return Label(text, classes="filter-section-title")

    @staticmethod
    def actions() -> Horizontal:
        return Horizontal(
            Button("APPLY FILTER", id=APPLY_ID, compact=True),
            Button("RESET ALL", id=RESET_ID, compact=True),
            classes="filter-actions",
        )

    # -- values -------------------------------------------------------------

    def values(self) -> dict[str, object]:
        """The raw range and select values, keyed by field."""
        values: dict[str, object] = {
            field: self.query_one(f"#{field_id(field)}", Input).value
            for field in self.RANGE_FIELDS
        }
        values.update({
            field: self.query_one(f"#{field_id(field)}", Select).value
            for field in self.SELECT_OPTIONS
        })
        return values

    def set_values(self, values: Mapping[str, object]) -> None:
        """Reset every range and select, then show the supplied ones.

        A select value outside its declared options stays ``any``.
        """
        for field in self.RANGE_FIELDS:
            value = values.get(field)
            self.query_one(f"#{field_id(field)}", Input).value = (
                "" if value is None else str(value)
            )
        for field, options in self.SELECT_OPTIONS.items():
            value = values.get(field, "any")
            allowed = {option for _label, option in options}
            self.query_one(f"#{field_id(field)}", Select).value = (
                value if isinstance(value, str) and value in allowed else "any"
            )

    # -- events -------------------------------------------------------------

    def on_resize(self, _event=None) -> None:
        self.set_class(self.content_size.width < self.COMPACT_BELOW, "compact-filter")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == APPLY_ID:
            self.post_message(self.APPLY_MESSAGE())
        elif event.button.id == RESET_ID:
            self.post_message(self.RESET_MESSAGE())
        else:
            self.other_button_pressed(event)

    def other_button_pressed(self, event: Button.Pressed) -> None:
        """A subclass's own buttons; the base has none."""

    # -- error --------------------------------------------------------------

    def clear_error(self) -> None:
        """Clear the visible error and its field marker."""
        if self._error_field is not None:
            try:
                self.query_one(f"#{field_id(self._error_field)}").remove_class(
                    "filter-invalid"
                )
            except NoMatches:
                pass
        self.query_one(f"#{self.ERROR_ID}", Static).update("")
        self._error_field = None

    def show_error(self, field: str | None, message: str) -> None:
        """Name one invalid control, if it exists, and keep focus on it."""
        self.clear_error()
        self._error_field = field
        if field is not None:
            try:
                control = self.query_one(f"#{field_id(field)}")
            except NoMatches:
                control = None
            if control is not None:
                control.add_class("filter-invalid")
                control.focus()
        self.query_one(f"#{self.ERROR_ID}", Static).update(message)
