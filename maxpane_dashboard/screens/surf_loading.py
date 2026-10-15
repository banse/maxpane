"""Surf-only loading chrome, driven by running requests rather than data age."""
from textual import events, on

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.status_bar import StatusBar


class SurfStatusBar(StatusBar):
    def _ordinary_status(self, last_updated_seconds_ago, error_count, poll_interval):
        return super()._ordinary_status(last_updated_seconds_ago, 0, poll_interval)


class SurfDashboardScreen(DashboardScreen):
    """Keep cached panels visible while an animated title reports real work."""

    LOADING_CHROME = "_chrome"
    _loading_timer = None
    _loading_frame = 0
    _loading_text = ""
    _background_loading = False
    _loading_projection = False
    _projection_due = False

    @property
    def loading_suffix(self):
        return self._loading_text

    def _loading_view(self):
        return getattr(self, "_mode", None)

    @on(events.ScreenResume)
    def _resume_loading(self):
        if self._loading_timer is None:
            self._loading_timer = self.set_interval(0.2, self._tick_loading)
        self.call_after_refresh(self._tick_loading)

    @on(events.ScreenSuspend)
    @on(events.Unmount)
    def _stop_loading(self):
        if self._loading_timer is not None:
            self._loading_timer.stop()
            self._loading_timer = None
        self._background_loading = False
        self._loading_text = ""
        self._loading_projection = False
        self._projection_due = False

    def _reads_pending(self):
        loading = getattr(self._data_manager, "is_loading", None)
        return bool(loading(self._loading_view())) if loading else False

    def _tick_loading(self):
        if not self.is_current:
            return
        background = self._reads_pending()
        # Project completed detached reads without offering another request.
        if self._background_loading and not background:
            self._projection_due = True
        if self._projection_due and not self._refresh_in_flight:
            self._projection_due = False
            if callable(getattr(self._data_manager, "get_snapshot", None)):
                self._loading_projection = True
                self.start_refresh()
        self._background_loading = background
        busy = self._refresh_in_flight or background
        text = ""
        if busy:
            frame = "◐◓◑◒"[self._loading_frame % 4]
            self._loading_frame += 1
            text = f" · {frame} loading"
        if text != self._loading_text:
            self._loading_text = text
            getattr(self, self.LOADING_CHROME)()

    async def _guarded_refresh(self):
        try:
            await super()._guarded_refresh()
        finally:
            # Observe tasks offered by this refresh before yielding to them.
            # Even a read finishing before the next timer tick gets repainted.
            if self.is_current:
                self._background_loading = self._background_loading or self._reads_pending()
                # Repaint after this worker exits, so its replacement cannot
                # cancel the worker that callers are still joining.
                self.call_after_refresh(self._tick_loading)

    async def _fetch_data(self):
        if self._loading_projection:
            self._loading_projection = False
            return self._data_manager.get_snapshot()
        return await super()._fetch_data()
