"""Public block-explorer links for the addresses and transaction hashes on screen.

Plan: ``docs/refactor_programme_2026_09.md`` Branch 4. A displayed address is
an OSC 8 hyperlink (Cmd+click in the terminal) **and** carries a Textual
``@click`` action that opens the same page through
``explorer_action.ExplorerLinkMixin``; this module names the explorers, builds
the URLs and is the one writer and the one reader of that action string, the
way ``widgets/address.py`` is for ``app.copy_address``.

Read-only: a link opens a public web page in the user's browser. Nothing here
fetches, signs or sends anything, and the app itself makes no request.

Pure: ``re`` and ``dataclasses`` only. No Rich, no Textual, no I/O, no ``data/``.
An unknown chain gets **no** link, never a guessed one (:func:`for_network`).

:data:`ADDRESS_RE` restates ``widgets/address.ADDRESS_RE`` because this module
sits below the address helper (which imports it) and may not import it back;
``tests/widgets/test_explorer.py`` holds the agreement test that binds the two
patterns, the ``_GAME_CYCLE`` shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "ADDRESS_RE", "BASE", "ETHEREUM", "EXPLORERS", "Explorer", "KINDS", "SEPOLIA",
    "TX_HASH_RE", "address_url", "for_chain_id", "for_network", "is_address",
    "is_tx_hash", "open_action", "parse_open_action", "tx_url", "url_for",
]

#: Matched with ``fullmatch``, never ``^…$`` (PRD §3.1 AMENDED): the value is
#: interpolated into an action string and into a URL.
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")

#: A transaction hash: ``0x`` + 64 hex, ``fullmatch`` only.
TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")

#: The two page kinds a link can open.
KINDS = ("address", "tx")


@dataclass(frozen=True)
class Explorer:
    """One public explorer: its allowlist name and the origin its pages hang off."""

    name: str
    base_url: str


ETHEREUM = Explorer("etherscan", "https://etherscan.io")
BASE = Explorer("basescan", "https://basescan.org")
SEPOLIA = Explorer("sepolia", "https://sepolia.etherscan.io")

#: The allowlist every action round-trips through, by name.
EXPLORERS: dict[str, Explorer] = {e.name: e for e in (ETHEREUM, BASE, SEPOLIA)}

#: Network words as surf spells them (``surf_models.POOL4_NETWORKS``,
#: ``_swarm_chain.chain_word``): upper-case, exact. Case matters -- a word this
#: table was not taught is an unknown chain, not a sloppy spelling.
_NETWORKS: dict[str, Explorer] = {
    "MAINNET": ETHEREUM,
    "SEPOLIA": SEPOLIA,
    "BASE": BASE,
}

#: Chain ids as a swarm row carries them (``data/surf_swarm._NETWORKS``,
#: ``_swarm_chain.CHAIN_ID_WORDS``) plus Base. ``tests/widgets/test_explorer.py``
#: binds this table to the words: every id surf's data layer names maps here
#: to the explorer :func:`for_network` gives its word, and back.
_CHAIN_IDS: dict[int, Explorer] = {
    1: ETHEREUM,
    11155111: SEPOLIA,
    8453: BASE,
}

_ACTION_PREFIX = "app.open_explorer("
#: The exact shape :func:`open_action` writes -- three ``repr`` strings of
#: quote-free values, ``", "`` between them -- so a ``fullmatch`` plus the
#: allowlist checks *is* the inverse; ``tests/widgets/test_explorer.py``
#: round-trips every explorer and kind through both functions to bind them.
_ACTION_RE = re.compile(r"app\.open_explorer\('([a-z]+)', '([a-z]+)', '(0x[0-9a-fA-F]+)'\)")


def is_address(value: object) -> bool:
    """True only for a whole, well-formed 0x address."""
    return isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None


def is_tx_hash(value: object) -> bool:
    """True only for a whole, well-formed 32-byte transaction hash."""
    return isinstance(value, str) and TX_HASH_RE.fullmatch(value) is not None


def for_network(word: object) -> Explorer | None:
    """The explorer for a network word, or ``None`` for anything not taught here."""
    if not isinstance(word, str):
        return None
    return _NETWORKS.get(word)


def for_chain_id(chain_id: object) -> Explorer | None:
    """The explorer for a numeric chain id, or ``None`` for anything not taught here.

    An allowlist, not a pass-through, like :func:`for_network`: ``bool`` is
    excluded before the ``int`` check because ``True``/``False`` are ``int``
    subclasses and neither is a chain id.
    """
    if isinstance(chain_id, bool) or not isinstance(chain_id, int):
        return None
    return _CHAIN_IDS.get(chain_id)


def _valid(kind: str, value: object) -> bool:
    if kind == "address":
        return is_address(value)
    if kind == "tx":
        return is_tx_hash(value)
    return False


def _allowlisted(explorer: object) -> Explorer:
    """``explorer`` itself when it is one of :data:`EXPLORERS`; ``ValueError`` otherwise.

    A URL is only ever built for an allowlisted explorer, so no caller of
    :func:`address_url` / :func:`tx_url` can be handed a usable link to a
    host this module does not name (review of WP-A, Minor 1).
    """
    if not isinstance(explorer, Explorer) or EXPLORERS.get(explorer.name) != explorer:
        raise ValueError("not an allowlisted explorer")
    return explorer


def address_url(explorer: Explorer, address: str) -> str:
    """``https://…/address/0x…`` for a **validated** address on an allowlisted explorer;
    ``ValueError`` otherwise."""
    if not is_address(address):
        raise ValueError("not an address")
    return f"{_allowlisted(explorer).base_url}/address/{address}"


def tx_url(explorer: Explorer, tx_hash: str) -> str:
    """``https://…/tx/0x…`` for a **validated** transaction hash; ``ValueError`` otherwise."""
    if not is_tx_hash(tx_hash):
        raise ValueError("not a transaction hash")
    return f"{_allowlisted(explorer).base_url}/tx/{tx_hash}"


def url_for(explorer: Explorer, kind: str, value: str) -> str:
    """:func:`address_url` or :func:`tx_url` by ``kind``; ``ValueError`` on anything else."""
    if kind == "address":
        return address_url(explorer, value)
    if kind == "tx":
        return tx_url(explorer, value)
    raise ValueError("not a link kind")


def open_action(explorer: Explorer, kind: str, value: str) -> str:
    """The ``@click`` action for a **validated** explorer, kind and value.

    ``app.open_explorer('etherscan', 'address', '0x…')``. Raises ``ValueError``
    rather than write an action for a value it would not parse back.
    """
    if explorer.name not in EXPLORERS or EXPLORERS[explorer.name] != explorer:
        raise ValueError("not an allowlisted explorer")
    if not _valid(kind, value):
        raise ValueError(f"not a {kind}")
    return f"{_ACTION_PREFIX}{explorer.name!r}, {kind!r}, {value!r})"


def parse_open_action(action: object) -> tuple[Explorer, str, str] | None:
    """``(explorer, kind, value)`` an open action names, or ``None``.

    The exact inverse of :func:`open_action`: an allowlisted name, a known
    kind, a value valid for that kind, and nothing else -- a foreign name,
    malformed hex, trailing text or a non-string is ``None``. The URL is never
    taken from the action; a reader rebuilds it from these parts.
    """
    if not isinstance(action, str):
        return None
    match = _ACTION_RE.fullmatch(action)
    if match is None:
        return None
    name, kind, value = match.groups()
    explorer = EXPLORERS.get(name)
    if explorer is None or kind not in KINDS or not _valid(kind, value):
        return None
    return explorer, kind, value
