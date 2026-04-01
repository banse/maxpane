"""FrenPet branding widget — wordmark in brand style (fren=bold, pet=thin)."""

from __future__ import annotations

from textual.widgets import Static


class FrenPetLogo(Static):
    """FrenPet wordmark: 'fren' bold, 'pet' thin, matching brand guidelines."""

    DEFAULT_CSS = """
    FrenPetLogo {
        width: auto;
        height: auto;
        padding: 1 2;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("[bold]fren[/][dim]pet[/]", **kwargs)
