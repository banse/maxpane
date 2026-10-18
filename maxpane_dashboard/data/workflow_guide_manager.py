"""Serve the bundled historical document without acquisition or polling."""

from copy import deepcopy

from maxpane_dashboard.data.workflow_guide_catalog import CATALOG
from maxpane_dashboard.data.workflow_guide_models import Snapshot


class WorkflowGuideManager:
    """Retain one local snapshot; callers receive independent nested values."""

    def __init__(self) -> None:
        self._snapshot: Snapshot = {"workflow_guide": deepcopy(CATALOG)}

    def get_snapshot(self) -> Snapshot:
        return deepcopy(self._snapshot)

    async def fetch_and_compute(self) -> Snapshot:
        return self.get_snapshot()
