"""Pure canonical identifiers shared by swarm reads and analytics."""
from uuid import UUID


def parse_job_id(value: object) -> str | None:
    """A canonical UUID path component, shared with answer cache validation."""
    if not isinstance(value, str):
        return None
    try:
        return value if str(UUID(value)) == value else None
    except ValueError:
        return None

