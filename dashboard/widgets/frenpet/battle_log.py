"""Detailed battle history for FrenPet Pet View."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from dashboard.analytics.frenpet_battle import (
    calculate_reward_risk_ratio,
    calculate_win_probability,
)


def _format_time(timestamp: int | float) -> str:
    """Convert unix timestamp to HH:MM display format."""
    try:
        t = time.localtime(int(timestamp))
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


class BattleLog(Vertical):
    """Scrolling log of recent battles for a specific pet."""

    DEFAULT_CSS = """
    BattleLog {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    BattleLog > .bl-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BattleLog > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    BattleLog > .bl-footer {
        width: 100%;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("BATTLE LOG", classes="bl-title")
        yield RichLog(id="bl-log", wrap=True, highlight=True, markup=True)
        yield Static("[dim]  --[/]", id="bl-footer", classes="bl-footer")

    def update_data(self, attacks: list[dict], pet_id: int) -> None:
        """Show recent battles involving this pet.

        Each attack dict should contain:
            ``timestamp``, ``attacker_id``, ``defender_id``, ``won`` (bool),
            ``reward`` (int), and optionally ``attacker_atk``, ``attacker_def``,
            ``defender_atk``, ``defender_def``, ``attacker_score``,
            ``defender_score``.
        """
        log = self.query_one("#bl-log", RichLog)

        # Filter to attacks involving this pet
        pet_attacks = [
            a for a in attacks
            if a.get("attacker_id") == pet_id or a.get("defender_id") == pet_id
        ]

        if not pet_attacks:
            if not self._seen_keys:
                log.write("[dim]  No battles yet[/]")
            self.query_one("#bl-footer", Static).update("[dim]  --[/]")
            return

        wins = 0
        losses = 0
        total_ratio = 0.0
        total_ev = 0.0
        battle_count = 0

        for attack in reversed(pet_attacks):
            ts = attack.get("timestamp", 0)
            atk_id = attack.get("attacker_id", 0)
            def_id = attack.get("defender_id", 0)
            won = attack.get("won", False)
            reward = attack.get("reward", 0)

            key = f"{ts}:{atk_id}:{def_id}"
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)

            # Determine if we were the attacker
            is_attacker = atk_id == pet_id
            opponent_id = def_id if is_attacker else atk_id

            # Calculate win prob and ratio if stats available
            opp_atk = attack.get("defender_atk" if is_attacker else "attacker_atk", 0)
            opp_def = attack.get("defender_def" if is_attacker else "attacker_def", 0)
            my_atk = attack.get("attacker_atk" if is_attacker else "defender_atk", 0)
            my_score = attack.get("attacker_score" if is_attacker else "defender_score", 0)
            opp_score = attack.get("defender_score" if is_attacker else "attacker_score", 0)

            # Win probability
            if my_atk > 0 and opp_def > 0:
                win_prob = calculate_win_probability(my_atk, opp_def)
                prob_str = f"{win_prob * 100:.0f}%"
            else:
                win_prob = 0.0
                prob_str = "--"

            # Ratio
            if my_score > 0 and my_atk > 0 and opp_score > 0 and opp_def > 0:
                ratio = calculate_reward_risk_ratio(
                    float(my_score), my_atk, float(opp_score), opp_def,
                )
                ratio_str = f"{ratio:.1f}"
                total_ratio += ratio
            else:
                ratio_str = "--"

            # Result formatting
            if won:
                result_str = "[green]Won[/]"
                delta_str = f"[green]+{int(reward):,}[/]"
                wins += 1
            else:
                result_str = "[red]Lost[/]"
                delta_str = f"[red]-{int(reward):,}[/]"
                losses += 1

            time_str = _format_time(ts)
            opp_stats = f"({opp_atk}/{opp_def})" if opp_atk > 0 else ""

            log.write(
                f"  [dim]{time_str}[/]  #{opponent_id} {opp_stats} "
                f"{prob_str} {result_str}  {delta_str}  [dim]ratio {ratio_str}[/]"
            )

            battle_count += 1
            total_ev += reward if won else -reward

        # Summary footer
        total = wins + losses
        if total > 0:
            win_rate = wins / total * 100
            avg_ratio = total_ratio / total if total_ratio > 0 else 0.0
            ev_per = total_ev / total
            ev_sign = "+" if ev_per >= 0 else ""
            self.query_one("#bl-footer", Static).update(
                f"  [dim]Win rate ({total}):[/] [bold white]{win_rate:.0f}%[/]   "
                f"[dim]Avg ratio:[/] [bold white]{avg_ratio:.1f}x[/]   "
                f"[dim]EV/battle:[/] [bold white]{ev_sign}{int(ev_per):,}[/]"
            )
