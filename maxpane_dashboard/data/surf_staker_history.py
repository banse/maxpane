"""Validated private checkpoints for the lifetime sIMD balance fold."""
from copy import deepcopy
import re

from maxpane_dashboard.data.surf_pool4_market import ZERO_ADDRESS

REPLAY_BLOCKS = 12
_ADDRESS = re.compile(r'0x[0-9a-f]{40}')
_WORD = re.compile(r'0x[0-9a-fA-F]{64}')
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


def checkpoint(value, network, vault, head):
    """Old slots and malformed/private cursors are rebuild hints, never proof."""
    if not isinstance(value, dict) or value.get('network') != network or value.get('vault') != vault.lower():
        return None
    block, anchor, balances = value.get('block'), value.get('anchor'), value.get('balances')
    if (type(block) is not int or type(anchor) is not int
            or not 0 <= anchor <= block + 1 <= head + 1 or not isinstance(balances, dict)):
        return None
    if any(not isinstance(addr, str) or not _ADDRESS.fullmatch(addr) or addr == ZERO_ADDRESS
           or type(amount) is not int or amount <= 0 for addr, amount in balances.items()):
        return None
    return deepcopy(value)


def transfers(logs, start, head):
    """Reject malformed/removed/conflicting events; deduplicate exact repeats."""
    if not isinstance(logs, list):
        return None
    rows = {}
    for log in logs:
        if not isinstance(log, dict):
            return None
        topics = log.get('topics')
        if not isinstance(topics, list) or not topics or not isinstance(topics[0], str):
            return None
        if topics[0].lower() != TRANSFER:
            continue
        if (len(topics) != 3 or any(not isinstance(t, str) or not _WORD.fullmatch(t) for t in topics)
                or not isinstance(log.get('data'), str) or not _WORD.fullmatch(log['data'])
                or log.get('removed', False) is not False):
            return None
        try:
            block, index = int(log['blockNumber'], 16), int(log['logIndex'], 16)
        except (KeyError, ValueError, TypeError):
            return None
        if not start <= block <= head or index < 0:
            return None
        key = block, index
        row = (block, '0x' + topics[1][-40:].lower(), '0x' + topics[2][-40:].lower(), int(log['data'], 16))
        if key in rows and rows[key] != row:
            return None
        rows[key] = row
    return [rows[key] for key in sorted(rows)]


def fold(prior, rows, *, network, vault, anchor, head):
    """Checkpoint before the replay tail; apply that tail afresh each tick."""
    balances = dict(prior['balances']) if prior else {}
    stable_block = max(anchor - 1, head - REPLAY_BLOCKS, prior['block'] if prior else -1)
    stable = dict(balances)
    complete = True
    for block, sender, receiver, amount in rows:
        if sender != ZERO_ADDRESS:
            balances[sender] = balances.get(sender, 0) - amount
            complete &= balances[sender] >= 0
        if receiver != ZERO_ADDRESS:
            balances[receiver] = balances.get(receiver, 0) + amount
        balances = {addr: balance for addr, balance in balances.items() if balance != 0}
        if block <= stable_block:
            stable = dict(balances)
    history = dict(network=network, vault=vault.lower(), anchor=anchor,
                   block=stable_block, balances=stable) if complete else None
    return {addr: balance for addr, balance in balances.items() if balance > 0}, history
