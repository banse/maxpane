"""``widgets/explorer.py``: the explorers, the URLs, the action and its parser.

Validated on both ends: :func:`open_action` refuses to write what
:func:`parse_open_action` would not read back, and the URL is rebuilt from the
parsed parts, never taken from the action text.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from maxpane_dashboard.widgets import address as A
from maxpane_dashboard.widgets import explorer as X

ADDR = "0x" + "abcdef0123" * 4          # 40 hex
TX = "0x" + "ab" * 32                   # 64 hex
MIXED = "0x" + "AbCdEf0123" * 4


def test_the_three_explorers_and_their_origins():
    assert X.ETHEREUM == X.Explorer("etherscan", "https://etherscan.io")
    assert X.BASE == X.Explorer("basescan", "https://basescan.org")
    assert X.SEPOLIA == X.Explorer("sepolia", "https://sepolia.etherscan.io")
    assert X.EXPLORERS == {"etherscan": X.ETHEREUM, "basescan": X.BASE, "sepolia": X.SEPOLIA}
    assert X.KINDS == ("address", "tx")


def test_an_explorer_is_frozen():
    with pytest.raises(Exception):
        X.ETHEREUM.base_url = "https://evil.example"  # type: ignore[misc]


def test_urls_hang_off_the_origin_and_keep_the_case():
    assert X.address_url(X.ETHEREUM, ADDR) == f"https://etherscan.io/address/{ADDR}"
    assert X.address_url(X.BASE, MIXED) == f"https://basescan.org/address/{MIXED}"
    assert X.tx_url(X.SEPOLIA, TX) == f"https://sepolia.etherscan.io/tx/{TX}"
    assert X.url_for(X.ETHEREUM, "address", ADDR) == X.address_url(X.ETHEREUM, ADDR)
    assert X.url_for(X.ETHEREUM, "tx", TX) == X.tx_url(X.ETHEREUM, TX)


def test_validation_is_fullmatch_on_40_or_64_hex_only():
    assert X.is_address(ADDR) and X.is_address(MIXED)
    assert X.is_tx_hash(TX)
    assert not X.is_address(TX) and not X.is_tx_hash(ADDR)
    for bad in (ADDR + "\n", ADDR[:-1] + "'", ADDR + "0", ADDR[:-1], None, 12, "", "vitalik.eth",
                "0x" + "g" * 40):
        assert not X.is_address(bad), repr(bad)
    for bad in (TX + "\n", TX + "0", TX[:-1], None, 12, "", "0x" + "g" * 64):
        assert not X.is_tx_hash(bad), repr(bad)


def test_the_address_pattern_agrees_with_the_address_helper():
    """Restated in both modules (the helper imports this one); an agreement
    test binds the two literals, the ``_GAME_CYCLE`` shape."""
    assert X.ADDRESS_RE.pattern == A.ADDRESS_RE.pattern
    assert X.ADDRESS_RE.flags == A.ADDRESS_RE.flags
    for value in (ADDR, MIXED, TX, ADDR + "\n", ADDR[:-1], "", None):
        assert X.is_address(value) is A.is_address(value), repr(value)


def test_urls_refuse_an_invalid_value_rather_than_write_it():
    for bad in (ADDR + "\n", ADDR[:-1], TX, "", None, "0x" + "g" * 40):
        with pytest.raises(ValueError):
            X.address_url(X.ETHEREUM, bad)
    for bad in (TX + "\n", TX[:-1], ADDR, "", None):
        with pytest.raises(ValueError):
            X.tx_url(X.ETHEREUM, bad)
    with pytest.raises(ValueError):
        X.url_for(X.ETHEREUM, "nft", ADDR)


def test_for_network_maps_the_three_words_and_nothing_else():
    assert X.for_network("MAINNET") is X.ETHEREUM
    assert X.for_network("SEPOLIA") is X.SEPOLIA
    assert X.for_network("BASE") is X.BASE
    for unknown in (None, "", "mainnet", "Mainnet", " MAINNET", "POLYGON", "—", 1, ["MAINNET"], {}):
        assert X.for_network(unknown) is None, repr(unknown)


def test_for_chain_id_maps_the_three_ids_and_nothing_else():
    assert X.for_chain_id(1) is X.ETHEREUM
    assert X.for_chain_id(11155111) is X.SEPOLIA
    assert X.for_chain_id(8453) is X.BASE
    for unknown in (None, "1", 1.0, True, False, 0, -1, 137, 10, [1], {}):
        assert X.for_chain_id(unknown) is None, repr(unknown)


def test_for_chain_id_agrees_with_the_swarm_data_layer_in_both_directions():
    """Every chain id ``data/surf_swarm._NETWORKS`` names maps here to the
    explorer :func:`for_network` gives its word (a swarm row resolves its
    ``chain_id`` directly, a pool4 panel its network word: the two paths must
    land on the same explorer), and every id this module maps to an explorer
    whose word the swarm data layer knows is an id that layer names -- so an
    id added on one side and not the other, or one mapped to the wrong
    explorer, fails here rather than linking a row to the wrong chain.
    """
    from maxpane_dashboard.data.surf_swarm import _NETWORKS

    assert _NETWORKS, "the swarm data layer names no chain at all"
    by_word = {cid: X.for_network(word) for cid, word in _NETWORKS.items()}
    assert all(e is not None for e in by_word.values()), by_word
    assert {cid: X.for_chain_id(cid) for cid in _NETWORKS} == by_word
    known_words = {X.for_network(word) for word in _NETWORKS.values()}
    assert {cid for cid, e in X._CHAIN_IDS.items() if e in known_words} == set(_NETWORKS)


@pytest.mark.parametrize("explorer", list(X.EXPLORERS.values()), ids=lambda e: e.name)
@pytest.mark.parametrize("kind,value", [("address", ADDR), ("address", MIXED), ("tx", TX)])
def test_every_explorer_round_trips_both_kinds(explorer, kind, value):
    action = X.open_action(explorer, kind, value)
    assert action == f"app.open_explorer({explorer.name!r}, {kind!r}, {value!r})"
    assert X.parse_open_action(action) == (explorer, kind, value)


def test_open_action_refuses_what_it_could_not_parse_back():
    with pytest.raises(ValueError):
        X.open_action(X.ETHEREUM, "address", TX)
    with pytest.raises(ValueError):
        X.open_action(X.ETHEREUM, "tx", ADDR)
    with pytest.raises(ValueError):
        X.open_action(X.ETHEREUM, "nft", ADDR)
    with pytest.raises(ValueError):
        X.open_action(X.ETHEREUM, "address", ADDR + "\n")
    with pytest.raises(ValueError):
        X.open_action(X.Explorer("blockscout", "https://blockscout.com"), "address", ADDR)
    with pytest.raises(ValueError):
        X.open_action(X.Explorer("etherscan", "https://evil.example"), "address", ADDR)


def test_parse_open_action_rejects_every_foreign_shape():
    good = X.open_action(X.ETHEREUM, "address", ADDR)
    for bad in (
        good.replace("etherscan", "blockscout"),         # foreign explorer name
        good.replace("etherscan", "Etherscan"),          # case
        good.replace("a", "g", 1),                       # not hex
        good.replace("'address'", "'nft'"),              # unknown kind
        X.open_action(X.ETHEREUM, "tx", TX).replace("'tx'", "'address'"),  # kind/value mismatch
        good + " ",                                      # trailing junk
        good + "; app.quit()",
        good[:-1],                                       # no closing parenthesis
        good.replace("'", '"'),                          # not what open_action writes
        good.replace(", ", ","),                         # spacing is part of the shape
        "x" + good,                                      # leading junk
        f"app.open_explorer('etherscan', 'address', '{ADDR[:-1]}')",   # 39 hex
        f"app.open_explorer('etherscan', 'address', '{ADDR}0')",       # 41 hex
        f"app.open_explorer('etherscan', 'tx', '{ADDR}')",             # an address as a tx
        "app.open_explorer()",
        "app.copy_address('%s')" % ADDR,
        "app.toggle()",
        "",
    ):
        assert X.parse_open_action(bad) is None, bad


def test_parse_open_action_tolerates_non_strings():
    for value in (None, 5, b"app.open_explorer('etherscan', 'address', '0x')", ["x"], object(), {}):
        assert X.parse_open_action(value) is None


def test_the_module_stays_pure():
    """``re`` and ``dataclasses`` only: no Rich, no Textual, no I/O, no ``data/``."""
    tree = ast.parse(pathlib.Path(X.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    allowed = {"__future__", "re", "dataclasses"}
    assert imported <= allowed, f"`explorer` reaches {sorted(imported - allowed)}"
