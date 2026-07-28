"""Single-flight refresh scheduling shared by every dashboard screen.

Every screen used to hand-copy the same three lines::

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="<game>-refresh")

    def _schedule_refresh(self) -> None:          # <- the 30 s interval timer
        self.run_worker(self._do_refresh(), exclusive=True, name="<game>-refresh")

    def action_refresh(self) -> None:             # <- the "r" key
        self.run_worker(self._do_refresh(), exclusive=True, name="<game>-refresh")

which carries two distinct async defects (code review 2026-07-04, MEDI-34 and
MEDI-35).  Both are fixed here, once, so that the twelve screens *and* the
copy-source in ``templates/screen_template.py`` share one implementation instead
of twelve chances to reintroduce them.

MEDI-34 — interval overrun livelock (``exclusive=True`` cancels the wrong side)
------------------------------------------------------------------------------
``set_interval(poll_interval, self._schedule_refresh)`` and
``run_worker(..., exclusive=True)`` sit on the same node and group, so a tick
that fires while the previous refresh is still running *cancels* it and starts
over.  Under sustained RPC degradation — the canonical case is a hanging primary
endpoint, where each sequential call burns its full timeout before falling
back — every cycle overruns the interval, so every cycle is killed at the same
point and restarted from zero: the dashboard never completes a single refresh,
widgets stay on placeholders forever, and the RPC traffic continues.  The
multi-endpoint fallback is nullified precisely when it is needed.

The fix is **skip, never queue** — the same semantics
:class:`~maxpane_dashboard.data.fwa_manager.FWAManager` uses for its position
sweep.  A tick that finds a refresh in flight is dropped: queueing a
multi-second refresh behind a 30 s cadence only guarantees the screen renders a
block from ten minutes ago, and cancelling guarantees it renders nothing at all.
The in-flight flag is raised *synchronously* in :meth:`RefreshGuard.start_refresh`,
before ``run_worker`` returns, because a worker coroutine does not begin
executing until the next event-loop iteration and two ticks can land inside that
window.

MEDI-35 — app-node prefetch racing the screen's first refresh
-------------------------------------------------------------
``MaxPaneApp.on_mount`` starts a worker named ``"prefetch"`` **on the app node**
that calls ``manager.fetch_and_compute()`` while the splash is showing.  When the
dashboard screen resumes it calls ``fetch_and_compute()`` on the *same manager*.
Textual's ``exclusive=True`` only cancels workers whose ``worker.node`` is the
same node (``worker_manager.cancel_group``), so the screen's exclusive worker
cannot and does not cancel the app's prefetch: the two run concurrently.  Both
first-run log scans then read the same ``last_seen_block == 0`` watermark and
both apply every event, double-counting event-derived metrics and persisting the
doubled totals to the on-disk cache.

The fix is the review's first suggestion, and it is the one available from the
screen side: the guarded refresh **joins the startup prefetch** before touching
the manager, so the first screen fetch starts after the prefetch's watermark
update rather than alongside it.  Joining rather than skipping is deliberate —
the prefetch's return value is discarded, so the screen must still fetch to get
a payload to render; it just does so against a warm cache.

Screens opt in by inheriting :class:`RefreshGuard` *before* ``Screen`` and
setting :attr:`RefreshGuard.REFRESH_WORKER_NAME`; the three scheduling methods
are then inherited and there is nothing left to copy incorrectly.
"""

from __future__ import annotations

import asyncio
import logging

from textual.worker import Worker, WorkerState

logger = logging.getLogger(__name__)

#: Name of the app-node worker started by ``MaxPaneApp.on_mount`` to warm the
#: initial game's manager while the splash screen is up.  Kept as a constant so
#: the coupling between app and screens is one greppable symbol.
PREFETCH_WORKER_NAME = "prefetch"


async def _join(worker: Worker) -> None:
    """Wait for *worker* to finish, swallowing its outcome but not our own cancel.

    Deliberately not :meth:`textual.worker.Worker.wait`: that method awaits the
    worker's task inside a ``try/except asyncio.CancelledError`` and converts
    what it catches into ``WorkerCancelled``.  When the cancellation being
    delivered is *ours* — app shutdown cancelling this screen's refresh — that
    conversion swallows it, and the refresh would carry on fetching after the
    app has asked it to stop.  Awaiting the task through :func:`asyncio.wait`
    keeps our cancellation ours, never raises the prefetch's exception, and
    never cancels the prefetch.
    """
    task = getattr(worker, "_task", None)
    if task is not None:
        await asyncio.wait({task})
        return
    try:  # pragma: no cover - only if Textual drops Worker._task
        await worker.wait()
    except Exception as exc:
        logger.debug("Startup prefetch did not complete cleanly: %s", exc)


class RefreshGuard:
    """Skip-not-queue refresh scheduling for dashboard screens.

    Mix in *before* :class:`textual.screen.Screen`::

        class TalismansScreen(RefreshGuard, Screen):
            REFRESH_WORKER_NAME = "talismans-refresh"

    and implement ``async def _do_refresh(self) -> None``.  The mixin supplies
    :meth:`_do_initial_refresh`, :meth:`_schedule_refresh` and
    :meth:`action_refresh`; a screen should not call ``run_worker`` on
    ``_do_refresh`` itself.

    Deliberately has no ``__init__``: the state lives in class-level defaults
    that are shadowed by instance attributes on first write, so mixing it in
    never disturbs a screen's constructor signature.
    """

    #: Worker name, per screen.  Only used for logging and worker introspection.
    REFRESH_WORKER_NAME: str = "refresh"

    #: True from the moment a refresh worker is scheduled until its coroutine
    #: has finished, failed or been cancelled.
    _refresh_in_flight: bool = False

    #: Count of ticks dropped because a refresh was still running.  Not
    #: displayed anywhere; it is the observable a test can assert on and a
    #: cheap health signal when debugging a degraded endpoint.
    _refresh_skipped: int = 0

    # ------------------------------------------------------------------
    # Scheduling entry points (inherited by every screen)
    # ------------------------------------------------------------------

    def _do_initial_refresh(self) -> None:
        """Trigger the immediate refresh that fills the screen on resume."""
        self.start_refresh()

    def _schedule_refresh(self) -> None:
        """Interval-timer callback.  Dropped if a refresh is still running."""
        self.start_refresh()

    def action_refresh(self) -> None:
        """Immediate refresh triggered by the ``r`` keybinding."""
        self.start_refresh()

    # ------------------------------------------------------------------
    # The guard itself
    # ------------------------------------------------------------------

    def start_refresh(self) -> Worker | None:
        """Start a refresh unless one is already in flight.

        Returns:
            The worker, or ``None`` if this call was skipped.
        """
        if self._refresh_in_flight:
            self._refresh_skipped += 1
            logger.debug(
                "%s: refresh still in flight — tick skipped (skipped, never "
                "queued; %d so far)",
                self.REFRESH_WORKER_NAME,
                self._refresh_skipped,
            )
            return None

        # Raised *before* run_worker: the worker coroutine does not start until
        # the next event-loop iteration, and a second tick landing in that
        # window would otherwise pass the guard and cancel this one.
        self._refresh_in_flight = True
        try:
            return self.run_worker(
                self._guarded_refresh(),
                exclusive=True,
                name=self.REFRESH_WORKER_NAME,
            )
        except Exception:
            # run_worker only fails if the screen is not mounted; leaving the
            # flag raised would wedge the screen permanently.
            self._refresh_in_flight = False
            raise

    async def _guarded_refresh(self) -> None:
        """Join the startup prefetch, run one refresh, then lower the flag."""
        try:
            await self._await_startup_prefetch()
            await self._do_refresh()
        finally:
            # finally, not else: a cancelled or failed refresh must not wedge
            # the screen on placeholders for the rest of the session.
            self._refresh_in_flight = False

    async def _await_startup_prefetch(self) -> None:
        """Wait for the app-node startup prefetch, if it is still running.

        Cheap and idempotent: after the prefetch has finished this walks a list
        that no longer contains it.  Never propagates — a prefetch that failed
        or was cancelled is not this screen's problem, and the app's own
        ``_prefetch`` already logs it.
        """
        try:
            app = self.app
        except Exception:
            # Screen not mounted (or no active app): nothing to race with.
            return

        for worker in list(getattr(app, "workers", ())):
            if worker.name != PREFETCH_WORKER_NAME or worker.node is self:
                continue
            if worker.state is WorkerState.PENDING:
                # Scheduled in this same event-loop iteration but not started;
                # Worker.wait() rejects PENDING workers, so give it the one
                # iteration it needs and re-read the state.
                await asyncio.sleep(0)
            if not worker.is_running:
                continue
            logger.debug(
                "%s: joining startup prefetch before first fetch",
                self.REFRESH_WORKER_NAME,
            )
            await _join(worker)

    # Screens must provide this.
    async def _do_refresh(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
