"""Pure folds for the seat ledger's camelCase records (Surf has different row keys)."""
from collections import defaultdict
from statistics import median


def record_state(row: dict) -> str | None:
    status = row.get('workStatus') or row.get('outcome')
    return row.get('jobState') if status in (None, 'accepted') else status


def record_window(rows: list[dict], cap: int, open_only: bool) -> list[dict]:
    return [r for r in rows if not open_only or record_state(r) != 'completed'][:max(40, min(400, cap))]


def answer_preview(row: dict) -> str | None:
    text = row.get('oracleAnswer') if row.get('oracleRequestId') else row.get('reply')
    if not isinstance(text, str) or not text:
        return None
    first = text.splitlines()[0]
    # The display boundary applies its 160-character cap after this sentence selection.
    return first.split('. ', 1)[0] + ('.' if '. ' in first else '')


def node_rows(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row.get('nodeKey') or '(plane unread)'].append(row)
    result = []
    for key, group in groups.items():
        counts = {word: sum(r.get('outcome') == word for r in group)
                  for word in ('accepted', 'rejected', 'failed', 'pending')}
        local = [r for r in group if (r.get('source') or {}).get('row') == 'local']
        duration = [r['durationS'] for r in local if r.get('durationS') is not None]
        output = [(r.get('tokens') or {})['output'] for r in local if (r.get('tokens') or {}).get('output') is not None]
        detailed = [r for r in group if r.get('detailRead')]
        payer_known = [r for r in detailed if r.get('paid') is not None]
        result.append(dict(nodeKey=key, role=next((r.get('role') for r in group if r.get('role')), None),
                           attempts=len(group), **counts, acceptedPercent=100 * counts['accepted'] / len(group),
                           durationP50S=median(duration) if duration else None,
                           outputTokensP50=median(output) if output else None,
                           paid=sum(r['paid'] is True for r in payer_known) if payer_known else None,
                           launch=sum(bool(r.get('launchLinked')) for r in detailed) if detailed else None,
                           detailsRead=len(detailed), lastSubmittedUtc=max((r.get('submittedUtc') for r in group
                                                                          if r.get('submittedUtc')), default=None)))
    return sorted(result, key=lambda r: (-r['attempts'], r['nodeKey']))
