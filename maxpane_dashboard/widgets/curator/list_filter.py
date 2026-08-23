"""Render-only custom filter controls for THE LIST's curator view."""

from __future__ import annotations

from typing import Mapping

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Button, Checkbox, Input, Label, Select, Static


FILTER_GROUPS = (
    ("JOIN", (("join_min", "from"), ("join_max", "to"))),
    ("HOUR JOINED", (("hour_min", "from"), ("hour_max", "to"))),
    ("RANK", (("rank_min", "from"), ("rank_max", "to"))),
    ("POINTS", (("points_min", "from"), ("points_max", "to"))),
    ("CREDIT", (("credit_min", "from"), ("credit_max", "to"))),
    ("WEIGHT", (("weight_min", "from"), ("weight_max", "to"))),
    ("DEPOSITS", (("deposits_min", "from"), ("deposits_max", "to"))),
)

OPTION_GROUPS = (
    ("ENS", "ens"),
    ("WINDOW", "window"),
    ("LINK BAND", "band"),
)

FAMILIES = ("amount", "sequence", "cadence", "gas", "funding")
FAMILY_LABELS = {
    "amount": "matching amounts",
    "sequence": "consecutive joins",
    "cadence": "cadence",
    "gas": "gas fingerprint",
    "funding": "shared funding",
}
FAMILY_TITLES = {
    "amount": "AMOUNT",
    "sequence": "SEQUENCE",
    "cadence": "CADENCE",
    "gas": "GAS",
    "funding": "FUNDING",
}

_RANGE_NAMES = tuple(
    field for _title, fields in FILTER_GROUPS for field, _placeholder in fields
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


class NftCollectionAddRequested(Message):
    def __init__(self, chain: str, address: str) -> None:
        super().__init__()
        self.chain = chain
        self.address = address


class NftCollectionRemoveRequested(Message):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class FilterResetRequested(Message):
    pass


class FilterApplyRequested(Message):
    pass


class CuratorListFilterEditor(Vertical):
    """A primitive-value editor; validation and filtering live outside it."""

    DEFAULT_CSS = """
    CuratorListFilterEditor {
        width: 100%;
        height: 100%;
        padding: 0 2;
        overflow-y: auto;
    }
    CuratorListFilterEditor .curator-filter-groups {
        height: auto;
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-gutter: 0 1;
    }
    CuratorListFilterEditor.compact-filter .curator-filter-groups {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    CuratorListFilterEditor .curator-filter-group {
        height: auto;
        min-width: 14;
        margin-bottom: 1;
    }
    CuratorListFilterEditor .curator-filter-group-title,
    CuratorListFilterEditor .curator-filter-section-title {
        height: 1;
        color: $text-muted;
    }
    CuratorListFilterEditor .curator-filter-range {
        height: 3;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 1;
    }
    CuratorListFilterEditor .curator-filter-group Select,
    CuratorListFilterEditor .curator-filter-group Checkbox {
        height: 3;
    }
    CuratorListFilterEditor .curator-filter-nft-presets {
        height: 3;
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
    }
    CuratorListFilterEditor .curator-filter-nft-custom-grid {
        height: auto;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 1;
    }
    CuratorListFilterEditor .curator-filter-nft-add-row {
        width: 100%;
        height: 3;
    }
    CuratorListFilterEditor #filter-nft-custom-list {
        width: 100%;
        min-width: 0;
        height: auto;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 1;
    }
    CuratorListFilterEditor .curator-filter-field {
        width: 100%;
        min-width: 14;
    }
    CuratorListFilterEditor #filter-nft-chain { width: 14; }
    CuratorListFilterEditor #filter-nft-address { width: 1fr; }
    CuratorListFilterEditor #filter-nft-add,
    CuratorListFilterEditor .curator-filter-nft-selected Button {
        width: 5;
        min-width: 5;
    }
    CuratorListFilterEditor .curator-filter-nft-selected {
        width: 100%;
        max-width: 100%;
        height: 1;
        overflow-x: hidden;
    }
    CuratorListFilterEditor .curator-filter-nft-selected Label {
        width: 1fr;
        min-width: 0;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        overflow-x: hidden;
    }
    CuratorListFilterEditor .curator-filter-actions {
        width: 100%;
        height: 3;
        align: center middle;
    }
    CuratorListFilterEditor .curator-filter-actions Button {
        margin: 0 1;
    }
    CuratorListFilterEditor .filter-invalid {
        border: tall $error;
    }
    CuratorListFilterEditor #curator-filter-error {
        height: 1;
        color: $error;
    }
    """

    def __init__(
        self,
        *args,
        nft_choices: tuple[tuple[str, str, str], ...] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._error_field: str | None = None
        self._nft_choices = tuple(nft_choices)
        self._custom_nfts: tuple[dict[str, str], ...] = ()

    @staticmethod
    def _nft_key(chain: str, address: str) -> str:
        return f"{chain}:{address.casefold()}"

    def _titled_group(self, title: str, *controls):
        return Vertical(
            Label(title, classes="curator-filter-group-title"),
            *controls,
            classes="curator-filter-group",
        )

    def compose(self) -> ComposeResult:
        yield Static("", id="curator-filter-error", markup=False)
        with Grid(classes="curator-filter-groups"):
            for title, fields in FILTER_GROUPS:
                yield self._titled_group(
                    title,
                    Grid(*(
                        Input(
                            placeholder=placeholder,
                            type="number",
                            valid_empty=True,
                            compact=True,
                            id=f"filter-{field.replace('_', '-')}",
                            classes="curator-filter-field",
                        )
                        for field, placeholder in fields
                    ), classes="curator-filter-range"),
                )
            for title, field in OPTION_GROUPS:
                yield self._titled_group(
                    title,
                    Select(
                        _SELECT_OPTIONS[field], allow_blank=False,
                        value="any", compact=True,
                        id=f"filter-{field}",
                        classes="curator-filter-field",
                    ),
                )
            yield self._titled_group(
                "WHALE DEPOSIT",
                Checkbox(
                    "25 ETH or more", compact=True,
                    id="filter-whale", classes="curator-filter-field",
                ),
            )
        yield Label("LINKED PATTERNS", classes="curator-filter-section-title")
        with Grid(classes="curator-filter-groups"):
            for family in FAMILIES:
                yield self._titled_group(
                    FAMILY_TITLES[family],
                    Checkbox(
                        FAMILY_LABELS[family], compact=True,
                        id=f"filter-family-{family}",
                        classes="curator-filter-field",
                    ),
                )
        yield Label("NFT HOLDERS", classes="curator-filter-section-title")
        with Grid(classes="curator-filter-nft-presets"):
            for index, (label, _chain, _address) in enumerate(self._nft_choices):
                yield Checkbox(label, compact=True, id=f"filter-nft-choice-{index}")
        with Grid(classes="curator-filter-nft-custom-grid"):
            with Horizontal(classes="curator-filter-nft-add-row"):
                yield Select(
                    (("Ethereum", "ethereum"), ("Base", "base")),
                    allow_blank=False, value="ethereum", compact=True,
                    id="filter-nft-chain",
                )
                yield Input(
                    placeholder="0x collection address", id="filter-nft-address"
                )
                yield Button("+", id="filter-nft-add", compact=True)
            yield Grid(id="filter-nft-custom-list")
        with Horizontal(classes="curator-filter-actions"):
            yield Button("APPLY FILTER", id="filter-apply", compact=True)
            yield Button("RESET ALL", id="filter-reset-all", compact=True)

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
        selected = []
        for index, (label, chain, address) in enumerate(self._nft_choices):
            if self.query_one(f"#filter-nft-choice-{index}", Checkbox).value:
                selected.append({
                    "label": label, "chain": chain, "address": address,
                })
        values["nft_collections"] = tuple(selected) + self._custom_nfts
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

        predefined = {
            self._nft_key(chain, address): index
            for index, (_label, chain, address) in enumerate(self._nft_choices)
        }
        for index in range(len(self._nft_choices)):
            self.query_one(f"#filter-nft-choice-{index}", Checkbox).value = False
        custom = []
        for raw in values.get("nft_collections", ()):
            if not isinstance(raw, Mapping):
                continue
            chain = raw.get("chain")
            address = raw.get("address")
            label = raw.get("label")
            if not (
                isinstance(chain, str)
                and isinstance(address, str)
                and isinstance(label, str)
            ):
                continue
            value = {
                "label": label,
                "chain": chain,
                "address": address.casefold(),
            }
            index = predefined.get(self._nft_key(chain, address))
            if index is None:
                custom.append(value)
            else:
                self.query_one(f"#filter-nft-choice-{index}", Checkbox).value = True
        self.set_custom_nfts(custom)
        self.query_one("#filter-nft-chain", Select).value = "ethereum"
        self.query_one("#filter-nft-address", Input).value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "filter-nft-add":
            self.post_message(NftCollectionAddRequested(
                str(self.query_one("#filter-nft-chain", Select).value),
                self.query_one("#filter-nft-address", Input).value,
            ))
        elif event.button.id == "filter-apply":
            self.post_message(FilterApplyRequested())
        elif event.button.id == "filter-reset-all":
            self.post_message(FilterResetRequested())
        elif event.button.id and event.button.id.startswith("filter-nft-remove-"):
            self.post_message(NftCollectionRemoveRequested(str(event.button.name)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-nft-address":
            self.post_message(NftCollectionAddRequested(
                str(self.query_one("#filter-nft-chain", Select).value),
                event.value,
            ))

    def set_custom_nfts(self, values) -> None:
        self._custom_nfts = tuple(dict(value) for value in values)
        try:
            container = self.query_one("#filter-nft-custom-list", Grid)
        except NoMatches:
            return
        container.remove_children()
        for index, value in enumerate(self._custom_nfts):
            key = self._nft_key(value["chain"], value["address"])
            container.mount(Horizontal(
                Label(value["label"], markup=False),
                Button(
                    "×", id=f"filter-nft-remove-{index}",
                    name=key, compact=True,
                ),
                classes="curator-filter-nft-selected",
            ))

    def set_nft_add_pending(self, pending: bool) -> None:
        self.query_one("#filter-nft-add", Button).disabled = pending

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
