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
    bakeries: list[BakerySummary] | None
    """``None`` when the bakeries sub-fetch failed; ``[]`` when it answered
    and the board is empty. Two facts a reader must be able to tell apart
    (follow-up #35): the first is ``unavailable``, the second ``No data``."""
    activity: list[ActivityEvent] | None
    """Same contract: ``None`` could not look, ``[]`` looked and found nothing."""
    agent_config: AgentConfig
    eth_price_usd: float
    fetched_at: float
    """``time.time()`` epoch when this snapshot was assembled."""
