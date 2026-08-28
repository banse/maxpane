"""Non-blocking umbrella manager for the two FWA dashboard modes.

PULLS owns first paint.  NETWORK refreshes in one reused background task and
is harvested only when it is already complete; a slow or stuck ecosystem
adapter therefore cannot extend the existing dashboard's refresh latency.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from typing import Any

from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    FWA_UMBRELLA_DATA_KEYS,
    blank_network_payload,
)
from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS

logger = logging.getLogger(__name__)


class FWACompositeManager:
    """Return PULLS immediately plus the latest complete NETWORK snapshot."""

    def __init__(
        self,
        poll_interval: int = 30,
        *,
        pulls_manager: Any = None,
        ecosystem_manager: Any = None,
    ) -> None:
        if pulls_manager is None:
            from maxpane_dashboard.data.fwa_manager import FWAManager

            pulls_manager = FWAManager(poll_interval=poll_interval)
        if ecosystem_manager is None:
            from maxpane_dashboard.data.fwa_ecosystem_manager import FWAEcosystemManager

            ecosystem_manager = FWAEcosystemManager(poll_interval=poll_interval)

        self.poll_interval = poll_interval
        self.pulls_manager = pulls_manager
        self.ecosystem_manager = ecosystem_manager
        self._network_task: asyncio.Task | None = None
        self._latest_network = blank_network_payload()
        self._closed = False

    @property
    def _error_count(self) -> int:
        """Compatibility surface used by ``FWAScreen``'s outer failure guard."""

        pulls = getattr(self.pulls_manager, "_error_count", 0)
        network = getattr(self.ecosystem_manager, "_error_count", 0)
        try:
            return int(pulls or 0) + int(network or 0)
        except (TypeError, ValueError, OverflowError):
            return 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Return the exact umbrella contract without awaiting live NETWORK work."""

        self._start_or_reuse_network_refresh()
        try:
            pulls_raw = await self.pulls_manager.fetch_and_compute()
        except Exception as exc:  # noqa: BLE001 -- preserve a renderable first paint
            logger.debug("FWA PULLS refresh failed at composite boundary: %s", exc)
            pulls_raw = None

        # This is a non-blocking state check: ``result()`` is called only after
        # ``done()``.  An unfinished NETWORK task is deliberately left running.
        self._harvest_network_if_done()

        payload = self._normalise_pulls(pulls_raw)
        payload.update(deepcopy(self._latest_network))
        # Keep the contract assertion executable in production without letting
        # an assertion take down the screen if a future edit breaks the seam.
        if tuple(payload) != FWA_UMBRELLA_DATA_KEYS:
            logger.error("FWA composite produced an out-of-order umbrella payload")
            payload = {
                key: payload.get(key)
                for key in FWA_UMBRELLA_DATA_KEYS
            }
        return payload

    def _start_or_reuse_network_refresh(self) -> None:
        if self._closed:
            return
        self._harvest_network_if_done()
        if self._network_task is not None:
            return
        task = asyncio.create_task(
            self.ecosystem_manager.fetch_and_compute(),
            name="fwa-network-refresh",
        )
        # Retrieving a completed task's exception prevents a detached failure
        # warning.  The result remains available for the next harvest.
        task.add_done_callback(self._observe_network_completion)
        self._network_task = task

    @staticmethod
    def _observe_network_completion(task: asyncio.Task) -> None:
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    def _harvest_network_if_done(self) -> None:
        task = self._network_task
        if task is None or not task.done():
            return
        self._network_task = None
        if task.cancelled():
            return
        try:
            raw = task.result()
        except Exception as exc:  # noqa: BLE001 -- last-good remains visible
            logger.debug("FWA NETWORK refresh failed: %s", exc)
            return
        snapshot = self._normalise_network(raw)
        if snapshot is not None:
            # One assignment publishes all 40 keys together.
            self._latest_network = snapshot

    @staticmethod
    def _normalise_pulls(raw: Any) -> dict[str, Any]:
        payload = dict.fromkeys(FWA_DATA_KEYS)
        if isinstance(raw, dict):
            for key in FWA_DATA_KEYS:
                if key in raw:
                    payload[key] = raw[key]
        return payload

    @staticmethod
    def _normalise_network(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        if tuple(raw) != FWA_NETWORK_DATA_KEYS:
            logger.error("Rejected incomplete or reordered FWA NETWORK snapshot")
            return None
        return deepcopy(raw)

    async def close(self) -> None:
        """Cancel NETWORK and close both owned managers exactly once."""

        if self._closed:
            return
        self._closed = True

        task = self._network_task
        self._network_task = None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

        for label, manager in (
            ("PULLS", self.pulls_manager),
            ("NETWORK", self.ecosystem_manager),
        ):
            try:
                await manager.close()
            except Exception as exc:  # noqa: BLE001 -- close the remaining child too
                logger.debug("closing FWA %s manager failed: %s", label, exc)


__all__ = ["FWACompositeManager"]
