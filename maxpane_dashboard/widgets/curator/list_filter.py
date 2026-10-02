"""Render-only custom filter controls for THE LIST's curator view."""

from __future__ import annotations

from typing import Mapping

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Button, Checkbox, Input, Label, Select

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.explorer import BASE, ETHEREUM, Explorer
from maxpane_dashboard.widgets.filter_editor import FilterEditorBase

#: The chains the NFT HOLDERS editor's ``Select`` offers, as ``(label,
#: value)``: the one place that vocabulary is typed in this package.
NFT_CHAIN_OPTIONS: tuple[tuple[str, str], ...] = (("Ethereum", "ethereum"), ("Base", "base"))

#: A custom collection's *contract* address lives on one chain -- unlike a
#: wallet, which is the same on Ethereum and Base -- so its link resolves per
#: row through this allowlist, keyed by the Select's own values; a chain word
#: outside it links nothing rather than guessing (widgets/explorer.py's rule,
#: fix round 1 C1 of Branch 4). Hand-typed beside ``NFT_CHAIN_OPTIONS``;
#: ``tests/widgets/test_curator_address_icons.py`` binds the two to each other
#: and to ``data/curator_list_filters.NFT_CHAINS`` (a widget may not import
#: ``data/``).
NFT_CHAIN_EXPLORERS: dict[str, Explorer] = {"ethereum": ETHEREUM, "base": BASE}


#: The address's own display budget in the selected-collections grid, when
#: there is no real name to show instead: :data:`MIN_SHORT_COLS`'s own
#: value (curator's historic 4/4 form), so the label never grows past what
#: ``custom_nft_label``'s own windowed fallback already promises. The icon
#: adds ``ICON_COLS`` on top.
_NFT_LABEL_ADDRESS_COLS = 11


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
        ("Review", "review"),
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


class CuratorListFilterEditor(FilterEditorBase):
    """A primitive-value editor; validation and filtering live outside it.

    The chrome (error line, group grid, ranges, selects, actions) is
    ``widgets/filter_editor.FilterEditorBase``'s; WHALE, LINKED PATTERNS and
    NFT HOLDERS are THE LIST's own.
    """

    ERROR_ID = "curator-filter-error"
    RANGE_FIELDS = _RANGE_NAMES
    SELECT_OPTIONS = _SELECT_OPTIONS
    APPLY_MESSAGE = FilterApplyRequested
    RESET_MESSAGE = FilterResetRequested

    DEFAULT_CSS = """
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
    """

    def __init__(
        self,
        *args,
        nft_choices: tuple[tuple[str, str, str], ...] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._nft_choices = tuple(nft_choices)
        self._custom_nfts: tuple[dict[str, str], ...] = ()

    @staticmethod
    def _nft_key(chain: str, address: str) -> str:
        return f"{chain}:{address.casefold()}"

    def compose(self) -> ComposeResult:
        yield self.error_line()
        with Grid(classes="filter-groups"):
            for title, fields in FILTER_GROUPS:
                yield self.range_group(title, fields)
            for title, field in OPTION_GROUPS:
                yield self.select_group(title, field)
            yield self.titled_group(
                "WHALE DEPOSIT",
                Checkbox(
                    "25 ETH or more", compact=True,
                    id="filter-whale", classes="filter-field",
                ),
            )
        yield self.section_title("LINKED PATTERNS")
        with Grid(classes="filter-groups"):
            for family in FAMILIES:
                yield self.titled_group(
                    FAMILY_TITLES[family],
                    Checkbox(
                        FAMILY_LABELS[family], compact=True,
                        id=f"filter-family-{family}",
                        classes="filter-field",
                    ),
                )
        yield self.section_title("NFT HOLDERS")
        with Grid(classes="curator-filter-nft-presets"):
            for index, (label, _chain, _address) in enumerate(self._nft_choices):
                yield Checkbox(label, compact=True, id=f"filter-nft-choice-{index}")
        with Grid(classes="curator-filter-nft-custom-grid"):
            with Horizontal(classes="curator-filter-nft-add-row"):
                yield Select(
                    NFT_CHAIN_OPTIONS,
                    allow_blank=False, value="ethereum", compact=True,
                    id="filter-nft-chain",
                )
                yield Input(
                    placeholder="0x collection address", id="filter-nft-address"
                )
                yield Button("+", id="filter-nft-add", compact=True)
            yield Grid(id="filter-nft-custom-list")
        yield self.actions()

    def values(self) -> dict[str, object]:
        """Return the raw values expected by the pure filter model."""
        values = super().values()
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
        super().set_values(values)
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

    def other_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "filter-nft-add":
            self.post_message(NftCollectionAddRequested(
                str(self.query_one("#filter-nft-chain", Select).value),
                self.query_one("#filter-nft-address", Input).value,
            ))
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
            # A fallback label (no real resolved/reader-chosen name) is the
            # address itself, windowed -- shown here as a real, clickable
            # ``address_text`` over the collection's own ``.address`` field
            # rather than as the plain, CSS-ellipsised string
            # ``custom_nft_label`` produces for the *prose* filter summary.
            # A real name renders as before, unchanged. ``is_fallback`` is
            # computed by the screen (``_nft_primitive``), not here: widgets
            # may not import ``data/``
            # (test_no_curator_widget_imports_data_or_analytics), so this
            # widget cannot call ``is_custom_nft_fallback_label`` itself.
            if value.get("is_fallback", False):
                # The contract's own chain, not the package's wallet
                # explorer: a Base collection links to Basescan, an unknown
                # chain word to nothing (NFT_CHAIN_EXPLORERS above).
                content = address_text(
                    str(value["address"]).strip().lower(),
                    width=_NFT_LABEL_ADDRESS_COLS,
                    explorer=NFT_CHAIN_EXPLORERS.get(value["chain"]),
                )
            else:
                content = value["label"]
            container.mount(Horizontal(
                Label(content, markup=False),
                Button(
                    "×", id=f"filter-nft-remove-{index}",
                    name=key, compact=True,
                ),
                classes="curator-filter-nft-selected",
            ))

    def set_nft_add_pending(self, pending: bool) -> None:
        self.query_one("#filter-nft-add", Button).disabled = pending
