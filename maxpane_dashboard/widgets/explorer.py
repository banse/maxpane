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

One allowlisted explorer is not a chain's: :data:`IMD` opens a swarm job's
page on ``explorer.imd.fun`` (owner, 2026-09-22, RECORD's job column), and
:data:`SITES` opens a swarm site through the eth.limo gateway (owner,
2026-09-23, SITES' ens column): only a ``<label>.site.identitymd.eth`` name,
and only as ``https://<label>.site.identitymd.eth.limo/`` -- the label is
the one part the value supplies. Each explorer names the kinds it serves, so a job link on etherscan, or an
address on the IMD explorer, is refused like a malformed value.

:data:`ADDRESS_RE` restates ``widgets/address.ADDRESS_RE`` because this module
sits below the address helper (which imports it) and may not import it back;
``tests/widgets/test_explorer.py`` holds the agreement test that binds the two
patterns, the ``_GAME_CYCLE`` shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "ADDRESS_RE", "BASE", "ETHEREUM", "EXPLORERS", "Explorer", "IMD", "JOB_ID_RE", "KINDS",
    "SEPOLIA", "SITES", "SITE_RE", "TX_HASH_RE", "address_url", "for_chain_id", "for_network",
    "is_address", "is_job_id", "is_site", "is_tx_hash", "is_valid", "job_url", "open_action",
    "parse_open_action", "site_url", "tx_url", "url_for",
]

#: Matched with ``fullmatch``, never ``^…$`` (PRD §3.1 AMENDED): the value is
#: interpolated into an action string and into a URL.
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")

#: A transaction hash: ``0x`` + 64 hex, ``fullmatch`` only.
TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")

#: A swarm job id: a canonical lower-case UUID, ``fullmatch`` only -- the
#: shape the swarm serves and the IMD explorer's ``/jobs/`` path takes.
JOB_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: A swarm site's ENS name: one lower-case LDH label (letters, digits, inner
#: hyphens, at most 63) under ``site.identitymd.eth`` -- the shape every
#: ``/sites`` name has had. Group 1 is the label, the only part a URL takes.
SITE_RE = re.compile(r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.site\.identitymd\.eth")

#: The page kinds a link can open; each explorer serves a subset.
KINDS = ("address", "tx", "job", "site")


@dataclass(frozen=True)
class Explorer:
    """One public explorer: its allowlist name and the origin its pages hang off."""

    name: str
    base_url: str
    kinds: tuple[str, ...] = ("address", "tx")


ETHEREUM = Explorer("etherscan", "https://etherscan.io")
BASE = Explorer("basescan", "https://basescan.org")
SEPOLIA = Explorer("sepolia", "https://sepolia.etherscan.io")
#: The IMD swarm's own explorer: job pages only, never a chain's address or tx.
IMD = Explorer("imd", "https://explorer.imd.fun", ("job",))
#: A swarm site's eth.limo gateway: site pages only. The base URL is the
#: suffix every link's host must end in; :func:`site_url` puts the label first.
SITES = Explorer("sites", "https://site.identitymd.eth.limo", ("site",))

#: The allowlist every action round-trips through, by name.
EXPLORERS: dict[str, Explorer] = {e.name: e for e in (ETHEREUM, BASE, SEPOLIA, IMD, SITES)}

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
_ACTION_RE = re.compile(
    r"app\.open_explorer\('([a-z]+)', '([a-z]+)', '(0x[0-9a-fA-F]+|[0-9a-f-]{36}|[a-z0-9.-]+)'\)")


def is_address(value: object) -> bool:
    """True only for a whole, well-formed 0x address."""
    return isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None


def is_tx_hash(value: object) -> bool:
    """True only for a whole, well-formed 32-byte transaction hash."""
    return isinstance(value, str) and TX_HASH_RE.fullmatch(value) is not None


def is_job_id(value: object) -> bool:
    """True only for a whole, canonical lower-case UUID."""
    return isinstance(value, str) and JOB_ID_RE.fullmatch(value) is not None


def is_site(value: object) -> bool:
    """True only for a whole ``<label>.site.identitymd.eth`` name (:data:`SITE_RE`)."""
    return isinstance(value, str) and SITE_RE.fullmatch(value) is not None


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
    if kind == "job":
        return is_job_id(value)
    if kind == "site":
        return is_site(value)
    return False


def is_valid(explorer: object, kind: object, value: object) -> bool:
    """True when *explorer* is allowlisted, serves *kind*, and *value* is one.

    The one check behind every link: the writer (:func:`open_action`), the
    parser and the app's action (``explorer_action``) all ask it.
    """
    return (isinstance(explorer, Explorer) and EXPLORERS.get(explorer.name) == explorer
            and isinstance(kind, str) and kind in explorer.kinds and _valid(kind, value))


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


def job_url(explorer: Explorer, job_id: str) -> str:
    """``https://…/jobs/<uuid>`` for a **validated** job id; ``ValueError`` otherwise."""
    if not is_job_id(job_id):
        raise ValueError("not a job id")
    return f"{_allowlisted(explorer).base_url}/jobs/{job_id}"


def site_url(explorer: Explorer, ens_name: str) -> str:
    """``https://<label>.site.identitymd.eth.limo/`` for a **validated** site
    name; ``ValueError`` otherwise. The host is the allowlisted origin with
    the validated label in front -- nothing else of the value reaches it."""
    match = SITE_RE.fullmatch(ens_name) if isinstance(ens_name, str) else None
    if match is None:
        raise ValueError("not a site name")
    scheme, _, host = _allowlisted(explorer).base_url.partition("://")
    return f"{scheme}://{match.group(1)}.{host}/"


def url_for(explorer: Explorer, kind: str, value: str) -> str:
    """The page for *kind* on an explorer that serves it; ``ValueError`` on anything else."""
    if not is_valid(explorer, kind, value):
        raise ValueError("not a link this explorer serves")
    if kind == "address":
        return address_url(explorer, value)
    if kind == "tx":
        return tx_url(explorer, value)
    if kind == "site":
        return site_url(explorer, value)
    return job_url(explorer, value)


def open_action(explorer: Explorer, kind: str, value: str) -> str:
    """The ``@click`` action for a **validated** explorer, kind and value.

    ``app.open_explorer('etherscan', 'address', '0x…')``. Raises ``ValueError``
    rather than write an action for a value it would not parse back.
    """
    if not is_valid(explorer, kind, value):
        raise ValueError(f"not a {kind} this explorer serves")
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
    if explorer is None or not is_valid(explorer, kind, value):
        return None
    return explorer, kind, value
