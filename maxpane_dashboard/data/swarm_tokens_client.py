"""Complete launch catalogue pages on the existing keyless swarm host pool."""
from copy import deepcopy

from maxpane_dashboard.data.surf_swarm_client import SwarmClient, parse_job_id


class SwarmTokensClient(SwarmClient):
    async def fetch_page(self, *, before: int | None = None,
                         limit: int = 500) -> list[dict] | None:
        """Numeric exclusive cursor; malformed pages never certify completeness."""
        if (type(limit) is not int or not 1 <= limit <= 500
                or before is not None and (type(before) is not int or before <= 0)):
            return None
        params = {'limit': str(limit)}
        if before is not None:
            params['before'] = str(before)
        body = await self._get('/launches', params=params)
        rows = body.get('launches') if isinstance(body, dict) else None
        if not isinstance(rows, list) or len(rows) > limit:
            return None
        seen, previous = set(), before
        for row in rows:
            if (not isinstance(row, dict) or parse_job_id(row.get('id')) is None
                    or type(row.get('launchNumber')) is not int or row['launchNumber'] <= 0
                    or type(row.get('chainId')) is not int
                    or not isinstance(row.get('status'), str)
                    or not isinstance(row.get('artifacts'), list)
                    or any(not isinstance(a, dict) for a in row['artifacts'])):
                return None
            if row['id'] in seen or previous is not None and row['launchNumber'] >= previous:
                return None
            seen.add(row['id'])
            previous = row['launchNumber']
        return deepcopy(rows)
