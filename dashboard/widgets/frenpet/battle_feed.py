"""Live battle event feed for FrenPet General View."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


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
        self._battle_rate: float = 0.0
        self._avg_reward: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("BATTLE FEED (live)", classes="battle-title")
        yield RichLog(id="battle-log", wrap=True, highlight=True, markup=True)
        yield Static("[dim]  Battles/hr: --  Avg reward: --[/]", id="battle-footer", classes="battle-footer")

    def update_data(
        self,
        attacks: list[dict],
        battle_rate: float = 0.0,
    ) -> None:
        """Append only new battle events, de-duplicated.

        Each attack dict is expected to have:
            timestamp, attacker_id, defender_id, won (bool), reward (int).
        """
        log = self.query_one("#battle-log", RichLog)

        if not attacks:
            if not self._seen_keys:
                log.write("[dim]  No battles yet[/]")
            return

        # Calculate avg reward from this batch
        rewards = [a.get("reward", 0) for a in attacks if a.get("reward", 0) > 0]
        if rewards:
            self._avg_reward = sum(rewards) / len(rewards)

        self._battle_rate = battle_rate

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

        # Update footer stats
        rate_str = f"~{int(self._battle_rate)}" if self._battle_rate > 0 else "--"
        reward_str = f"{int(self._avg_reward):,}" if self._avg_reward > 0 else "--"
        self.query_one("#battle-footer", Static).update(
            f"  [dim]Battles/hr:[/] {rate_str}  [dim]Avg reward:[/] {reward_str}"
        )
