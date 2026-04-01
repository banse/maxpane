"""Unified game snapshot model returned by GameDataClient.fetch_all()."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.models import (
    ActivityEvent,
    AgentConfig,
    BakerySummary,
    Season,
)


class GameSnapshot(BaseModel):
    """A point-in-time snapshot of the entire game state.

    Produced by ``GameDataClient.fetch_all()`` and consumed by the
    dashboard rendering layer and the ``DataCache`` accumulator.
    """

    model_config = ConfigDict(frozen=True)

    season: Season
    bakeries: list[BakerySummary]
    activity: list[ActivityEvent]
    agent_config: AgentConfig
    eth_price_usd: float
    fetched_at: float
    """``time.time()`` epoch when this snapshot was assembled."""
