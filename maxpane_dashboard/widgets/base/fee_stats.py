"""Fee statistics panel for the Base Terminal Fee Monitor view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class FeeStats(Vertical):
    """Static panel showing fee claim statistics."""

    DEFAULT_CSS = """
    FeeStats > .fs-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FeeStats > .fs-body {
        width: 100%;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("FEE STATS", classes="fs-title")
        yield Static("[dim]  --[/]", id="fs-body", classes="fs-body")

    def update_data(self, stats: dict | None) -> None:
        """Update fee stats display.

        Expected keys:
            claims_1h, total_eth_1h, avg_claim_eth, largest_claim_eth,
            largest_claim_token, total_claimed_all.
        """
        body = self.query_one("#fs-body", Static)

        if not stats:
            body.update("[dim]  --[/]")
            return

        claims = stats.get("claims_1h", 0)
        total_eth = stats.get("total_eth_1h", 0)
        avg_claim = stats.get("avg_claim_eth", 0)
        largest = stats.get("largest_claim_eth", 0)
        largest_token = stats.get("largest_claim_token", "")

        try:
            total_val = float(total_eth)
            avg_val = float(avg_claim)
            largest_val = float(largest)
        except (ValueError, TypeError):
            total_val = avg_val = largest_val = 0

        largest_suffix = f" ({largest_token})" if largest_token else ""

        lines = [
            f"  Claims (1h):     [bold]{claims}[/]",
            f"  Total ETH (1h):  [bold]{total_val:.2f} ETH[/]",
            f"  Avg claim:       [bold]{avg_val:.3f} ETH[/]",
            f"  Largest (1h):    [bold]{largest_val:.2f} ETH[/]{largest_suffix}",
        ]
        body.update("\n".join(lines))
