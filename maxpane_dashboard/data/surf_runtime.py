"""Per-package npm cache validation, shared by load and consumption."""
import math

from maxpane_dashboard.data.npm_registry_client import RUNTIME_PACKAGES, npm_version


def coerce_runtime_slot(payload, *, now):
    if not isinstance(payload, dict):
        return None
    clean = {}
    for runtime, point in payload.items():
        if runtime not in RUNTIME_PACKAGES or not isinstance(point, dict):
            continue
        if set(point) != {'version', 'checked_ts'}:
            continue
        version, stamp = point['version'], point['checked_ts']
        if version is not None and npm_version(version) is None:
            continue
        if (isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp) or stamp < 0 or stamp > now):
            continue
        clean[runtime] = {'version':version, 'checked_ts':stamp}
    return clean
