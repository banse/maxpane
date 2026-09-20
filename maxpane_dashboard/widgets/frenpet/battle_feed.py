"""Live battle event feed for FrenPet General View."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.panels import UNAVAILABLE


def _format_battle_time(timestamp: int | float) -> str:
    """Convert unix timestamp to HH:MM:SS display format."""
    try:
        t = time.localtime(int(timestamp))
        return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
    except (ValueError, OSError):
        return "??:??:??"


class BattleFeed(Vertical):
    """Auto-scrolling feed of recent battle events."""

    DEFAULT_CSS = """
    BattleFeed > .battle-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BattleFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    BattleFeed > .battle-footer {
        width: 100%;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()
        self._battle_rate: float | None = None
        self._avg_reward: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("BATTLE FEED (live)", classes="battle-title")
        yield RichLog(id="battle-log", wrap=True, highlight=True, markup=True)
        yield Static("[dim]  Battles/hr: --  Avg reward: --[/]", id="battle-footer", classes="battle-footer")

    def update_data(
        self,
        attacks: list[dict],
        battle_rate: float | None = None,
    ) -> None:
        """Append only new battle events, de-duplicated.

        Each attack dict is expected to have:
            timestamp, attacker_id, defender_id, won (bool), reward (int).

        *battle_rate* is ``None`` when the manager could not measure one --
        the attacks feed failed or the window cannot carry a rate -- and the
        footer then says ``unavailable`` rather than a rate nobody measured
        (follow-up #43). The footer is repainted on every call, including
        the empty-batch one, so an outage is visible as soon as it starts.
        """
        log = self.query_one("#battle-log", RichLog)
        self._battle_rate = battle_rate

        if not attacks:
            if not self._seen_keys:
                log.write("[dim]  No battles yet[/]")
            self._paint_footer()
            return

        # Calculate avg reward from this batch
        rewards = [a.get("reward", 0) for a in attacks if a.get("reward", 0) > 0]
        if rewards:
            self._avg_reward = sum(rewards) / len(rewards)

        # Attacks arrive newest-first; append oldest-first for natural scroll
        for attack in reversed(attacks):
            ts = attack.get("timestamp", 0)
            atk_id = attack.get("attacker_id", "?")
            def_id = attack.get("defender_id", "?")
            won = attack.get("won", False)

            key = f"{ts}:{atk_id}:{def_id}"
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)

            time_str = _format_battle_time(ts)
            if won:
                result = "[green]Won[/]"
            else:
                result = "[red]Lost[/]"

            log.write(
                f"  [dim]{time_str}[/]  #{atk_id} bonked #{def_id}  {result}"
            )

        self._paint_footer()

    def _paint_footer(self) -> None:
        rate = self._battle_rate
        if rate is None:
            rate_str = UNAVAILABLE
        else:
            rate_str = f"~{int(rate)}" if rate > 0 else "--"
        reward_str = f"{int(self._avg_reward):,}" if self._avg_reward > 0 else "--"
        self.query_one("#battle-footer", Static).update(
            f"  [dim]Battles/hr:[/] {rate_str}  [dim]Avg reward:[/] {reward_str}"
        )
