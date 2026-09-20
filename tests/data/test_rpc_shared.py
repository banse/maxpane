"""MEDI-17: what the RPC clients share is shared, and what diverges stays split.

MEDI-17 read the eight ``data/*_client.py`` modules as one duplicated ``_rpc``
and proposed extracting "the hardened ttt/talismans ``_rpc``" into a single
module every client would use. Half of that is right and half of it would be a
regression, so this file pins both halves.

**Shared, and must stay shared.** An AST scan across the five on-chain clients
found twelve module-level functions existing as two or three *byte-identical*
copies -- the whole minimal ABI codec. ``fwa_client`` said so out loud
("copied verbatim from ``talismans_client``"). Solidity's ABI is a published
encoding: a fix to one copy is a fix all of them need. Same for the JSON-RPC
envelope, the "this host is dead" status set, the pacing arithmetic and the
owns-my-httpx-client lifecycle. Those now live in
:mod:`maxpane_dashboard.data.evm_abi` and
:mod:`maxpane_dashboard.data.rpc_common`, and the tests below fail if a client
pastes a private copy back -- the failure mode
``tests/widgets/test_sparkline_common.py`` was written for.

**Diverged, and must stay diverged.** The five ``_rpc`` bodies implement five
different error policies, each pinned by its own tests and each encoding a
fact about a chain or a provider: talismans' typed classification feeds its
log-window shrinking; ttt runs two endpoint pools because publicnode batches
``eth_call`` and 403s archive ``eth_getLogs``; fwa rotates on any error body;
cattown deliberately does *not* rotate on a revert; ocm has one endpoint.
Forcing them through one function would either strip the hardening off the
top four or impose it on the bottom four. The last section asserts each client
still owns its ``_rpc``, so a future "let's just unify these" arrives as a
failing test with the argument attached rather than as a silent outage.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from maxpane_dashboard.data import (
    base_client,
    cattown_client,
    curator_nft_holders,
    dota_client,
    evm_abi,
    frenpet_client,
    fwa_client,
    fwa_logs,
    ocm_client,
    rpc_common,
    talismans_client,
    ttt_client,
)

# ---------------------------------------------------------------------------
# The cast
# ---------------------------------------------------------------------------

#: Every module that owns an ``httpx`` client, and the class in it that does.
#:
#: The last two are **not** ``*_client.py`` files, and that is exactly why they
#: are listed by hand: the MEDI-17 hoist globbed ``data/*_client.py``, so
#: ``fwa_logs`` (FWA's Pool B log module) kept a private dead-code set, a
#: private JSON-RPC envelope, inline pacing and a hand-rolled lifecycle for
#: three releases without any guard here seeing it (Branch 10 survey §8.1-2),
#: and ``curator_nft_holders`` was never scanned at all. A new module that
#: talks to a chain belongs in this dict on the day it lands.
ALL_CLIENTS = {
    base_client: "BaseChainClient",
    cattown_client: "CatTownClient",
    curator_nft_holders: "NftHolderClient",
    dota_client: "DOTAClient",
    frenpet_client: "FrenPetClient",
    fwa_client: "FWAClient",
    fwa_logs: "FWALogClient",
    ocm_client: "OCMClient",
    talismans_client: "TalismansClient",
    ttt_client: "TTTClient",
}

#: The subset that speaks JSON-RPC to a chain **and owns a ``_rpc`` method**:
#: this list drives the "keep your own error policy" guard at the bottom.
#: ``fwa_logs`` is deliberately absent -- its transport entry point is
#: ``_post`` and its error policy is the kind classifier
#: ``_classify_rpc_error``, which Branch 10's P4 keeps local.
RPC_CLIENTS = [
    cattown_client,
    fwa_client,
    ocm_client,
    talismans_client,
    ttt_client,
]

#: Everything that builds a JSON-RPC envelope, whatever it calls the method
#: that sends it. Wider than :data:`RPC_CLIENTS` on purpose.
JSONRPC_MODULES = [*RPC_CLIENTS, curator_nft_holders, fwa_logs]

#: Private names each client binds by importing from ``evm_abi``, mapped to
#: the shared function they must resolve to. A client is free not to need a
#: given helper; it is not free to define its own.
CODEC_ALIASES = {
    "_strip0x": evm_abi.strip0x,
    "_pad_left": evm_abi.pad_left,
    "_pad_address": evm_abi.pad_address,
    "_addr_from_topic": evm_abi.addr_from_topic,
    "_decode_uint": evm_abi.decode_uint,
    "_decode_uint256": evm_abi.decode_uint256,
    "_decode_address": evm_abi.decode_address,
    "_encode_uint": evm_abi.encode_uint,
    "_encode_address": evm_abi.encode_address,
    "_encode_call3": evm_abi.encode_call3,
    "_encode_aggregate3": evm_abi.encode_aggregate3,
    "_decode_aggregate3_result": evm_abi.decode_aggregate3_result,
}

#: Names no ``*_client.py`` may *define*. Both spellings are listed: the
#: private alias a client binds it under, and the public name in ``evm_abi``,
#: so neither a pasted copy nor a renamed one slips through.
FORBIDDEN_DEFS = set(CODEC_ALIASES) | {
    name for name in evm_abi.__all__ if name.islower()
} | {"jsonrpc_payload", "pace"}

#: Per-module exemptions from :data:`FORBIDDEN_DEFS`, one name at a time --
#: never a whole module, so every other forbidden name still scans it.
#:
#: ``fwa_logs._strip0x`` is **not** ``evm_abi.strip0x``: it also strips an
#: uppercase ``0X`` (``hex_str.startswith(("0x", "0X"))``), which the shared
#: function does not. Binding the shared one would be a silent behaviour
#: change to every FWA log decoder, so Branch 10 WP-C left the copy where it
#: was rather than force it. Reconciling the two is its own Tier 0: widen
#: ``evm_abi.strip0x`` and delete this entry, or record why ``0X`` matters to
#: FWA alone.
CODEC_EXEMPTIONS = {fwa_logs: {"_strip0x"}}


def _module_source(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


#: Every ``data/*_client.py`` on disk, not just the ones imported above:
#: ``curator_client``, ``surf_client`` and ``surf_pool4_client`` carry error
#: tables too and were never in ``ALL_CLIENTS``.
_DATA_DIR = Path(rpc_common.__file__).parent


def _module_level_defs(module) -> set[str]:
    return {
        node.name
        for node in ast.parse(_module_source(module)).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _client_class_defs(module, class_name: str) -> set[str]:
    tree = ast.parse(_module_source(module))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"{module.__name__} has no class {class_name}")


# ---------------------------------------------------------------------------
# 1. the ABI codec is one definition, imported everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module", list(ALL_CLIENTS), ids=lambda m: m.__name__.rsplit(".", 1)[-1]
)
def test_no_client_redefines_a_shared_codec_helper(module) -> None:
    """A pasted helper body must fail this test, not ship quietly.

    Identity (below) is satisfiable by an import; this reads the source, so a
    client that copies the function *and* shadows the import is caught too.
    """
    forked = (
        _module_level_defs(module) & FORBIDDEN_DEFS
    ) - CODEC_EXEMPTIONS.get(module, set())
    assert not forked, (
        f"{module.__name__} defines {sorted(forked)} instead of importing from "
        "data/evm_abi.py or data/rpc_common.py. These were byte-identical in "
        "up to three clients before MEDI-17; a private copy re-opens the fork "
        "and fixes to it reach no other dashboard."
    )


@pytest.mark.parametrize(
    "module", list(ALL_CLIENTS), ids=lambda m: m.__name__.rsplit(".", 1)[-1]
)
def test_codec_aliases_resolve_to_the_shared_functions(module) -> None:
    """Whatever a client binds these names to must *be* the shared object."""
    exempt = CODEC_EXEMPTIONS.get(module, set())
    for alias, shared in CODEC_ALIASES.items():
        if alias in exempt:
            continue  # a divergent copy, named and justified at CODEC_EXEMPTIONS
        bound = getattr(module, alias, None)
        if bound is None:
            continue  # this client does not need that helper -- fine
        assert bound is shared, (
            f"{module.__name__}.{alias} is not {shared.__module__}."
            f"{shared.__name__}; it is {bound!r}"
        )


def test_the_codec_is_actually_reached_by_the_clients() -> None:
    """Nothing in ``evm_abi`` is an orphan, and no RPC client opted out.

    Without this, ``test_codec_aliases_resolve...`` would pass vacuously: a
    client that silently stopped importing anything at all satisfies "every
    alias you bind is the shared one" trivially.
    """
    reached: set = set()
    for module in ALL_CLIENTS:
        bound = {
            shared
            for alias, shared in CODEC_ALIASES.items()
            if getattr(module, alias, None) is shared
        }
        if module in RPC_CLIENTS:
            assert len(bound) >= 2, (
                f"{module.__name__} is an on-chain client that binds almost "
                "none of the shared codec -- did it grow a private copy?"
            )
        reached |= bound
    orphans = set(CODEC_ALIASES.values()) - reached
    assert not orphans, (
        f"{sorted(f.__name__ for f in orphans)} in data/evm_abi.py is used by "
        "no client. Shared modules earn their place by being used; delete it "
        "or move it back to its one caller."
    )
    for module in (cattown_client, ocm_client):
        assert module._decode_uint256 is evm_abi.decode_uint256
        assert module._pad_address is evm_abi.pad_address


def test_the_aggregate3_selector_has_one_value() -> None:
    """FWA's selector table and the shared codec must not drift apart.

    ``fwa_client`` keeps its own ``SELECTORS`` map (it is the FWA ABI
    reconnaissance record, and other tests read it); the codec has the
    selector too because :func:`evm_abi.encode_aggregate3` prefixes it. Two
    sources, one value -- asserted rather than assumed. ``talismans`` and
    ``ttt`` used to declare a third and fourth copy; they no longer do.
    """
    assert fwa_client._SEL_AGGREGATE3 == evm_abi.SEL_AGGREGATE3 == "0x82ad56cb"
    assert fwa_client.ZERO_ADDRESS == evm_abi.ZERO_ADDRESS == "0x" + "0" * 40
    for module in (talismans_client, ttt_client):
        assert "0x82ad56cb" not in _module_source(module), (
            f"{module.__name__} re-declares the aggregate3 selector"
        )


# ---------------------------------------------------------------------------
# 2. the shared codec behaves (so a mutation to it is caught here too)
# ---------------------------------------------------------------------------


def test_encode_call3_strips_the_0x_from_calldata() -> None:
    """FWA TRAP 4: a retained ``0x`` embeds ``30 78`` and the node rejects it."""
    encoded = evm_abi.encode_call3("0x" + "ab" * 20, "0xdeadbeef")
    assert "0x" not in encoded
    assert encoded.endswith("deadbeef" + "0" * 56)


def test_aggregate3_calldata_carries_exactly_one_0x() -> None:
    calldata = evm_abi.encode_aggregate3(
        [("0x" + "11" * 20, "0xaabbccdd", True), ("0x" + "22" * 20, "0x", False)]
    )
    assert calldata.startswith("0x82ad56cb")
    assert calldata.count("0x") == 1


def test_decode_aggregate3_keeps_a_failed_subcall_in_its_slot() -> None:
    """A decoder that drops failures mis-aligns the whole batch."""
    ok = evm_abi.encode_uint(1) + evm_abi.encode_uint(0x40) + evm_abi.encode_uint(32)
    ok += evm_abi.encode_uint(7)
    bad = evm_abi.encode_uint(0) + evm_abi.encode_uint(0x40) + evm_abi.encode_uint(0)
    offsets = evm_abi.encode_uint(64) + evm_abi.encode_uint(64 + len(ok) // 2)
    payload = (
        evm_abi.encode_uint(0x20)
        + evm_abi.encode_uint(2)
        + offsets
        + ok
        + bad
    )
    results = evm_abi.decode_aggregate3_result("0x" + payload)
    assert [success for success, _ in results] == [True, False]
    assert evm_abi.decode_uint(results[0][1]) == 7
    assert results[1][1] == "0x"


def test_decode_aggregate3_degrades_instead_of_raising() -> None:
    assert evm_abi.decode_aggregate3_result("0x") == []
    assert evm_abi.decode_aggregate3_result("0xdeadbeef") == []


@pytest.mark.parametrize(
    ("hex_data", "expected"),
    [("0x", 0), ("0x" + "0" * 64, 0), ("0x" + "0" * 63 + "f", 15), ("ff", 255)],
)
def test_decode_uint_and_its_cattown_spelling_agree(hex_data, expected) -> None:
    assert evm_abi.decode_uint(hex_data) == expected
    assert evm_abi.decode_uint256(hex_data) == expected


def test_the_one_codec_exemption_is_a_real_divergence() -> None:
    """``CODEC_EXEMPTIONS`` stands on a behaviour difference, not on inertia.

    If this ever fails because the two agree, delete the entry: the guard
    above should be scanning that name again.
    """
    assert CODEC_EXEMPTIONS == {fwa_logs: {"_strip0x"}}
    assert fwa_logs._strip0x is not evm_abi.strip0x
    assert fwa_logs._strip0x("0Xdeadbeef") == "deadbeef"
    assert evm_abi.strip0x("0Xdeadbeef") == "0Xdeadbeef"


def test_decode_address_zero_fills_an_empty_word() -> None:
    assert evm_abi.decode_address("0x") == evm_abi.ZERO_ADDRESS
    assert evm_abi.decode_address("0x" + "0" * 24 + "ab" * 20) == "0x" + "ab" * 20


# ---------------------------------------------------------------------------
# 3. the transport atoms
# ---------------------------------------------------------------------------


def test_dead_endpoint_codes_are_not_re_declared() -> None:
    """The 10-code set was copied four ways; it must live in one place.

    The 52x half is Cloudflare's and is ``>= 500`` without being transient,
    which is the whole reason the set exists. Re-declaring it locally is how
    one client's set drifts from another's.
    """
    assert rpc_common.ENDPOINT_DEAD_CODES == frozenset(
        {401, 402, 403, 451, 521, 522, 523, 524, 525, 526}
    )
    for module in ALL_CLIENTS:
        source = _module_source(module)
        assert "521, 522, 523" not in source, (
            f"{module.__name__} re-declares the dead-endpoint status codes; "
            "import ENDPOINT_DEAD_CODES from data/rpc_common.py instead"
        )
    for module in (cattown_client, fwa_client, fwa_logs, talismans_client):
        assert module._ENDPOINT_DEAD_CODES is rpc_common.ENDPOINT_DEAD_CODES


#: The module-level names that must hold a *binding* to a shared table.
_SHARED_TABLE_NAMES = (
    "_ENDPOINT_LIMITATION_PATTERNS",
    "_RANGE_LIMITATION_PATTERNS",
    "_RESULT_CAP_MARKERS",
    "_RANGE_CAP_MARKERS",
)

#: Every module that classifies an RPC error message: the eight
#: ``data/*_client.py`` plus ``fwa_logs.py``, which is not one and was
#: therefore invisible to the glob this guard used to run (Branch 10 §8.1).
_CLASSIFIER_SOURCES = sorted(_DATA_DIR.glob("*_client.py")) + [_DATA_DIR / "fwa_logs.py"]

#: The tables Branch 10 **decided** to keep local (P4). ``talismans`` and
#: ``fwa_logs`` do not answer "is this a limitation?" with a boolean; they
#: answer it with a *kind* (``result_cap`` / ``range_cap`` / ``timeout`` ...)
#: that their pagers consume as data alongside ``suggested_to``. Hoisting
#: those is a Tier 1 per client with its own fixture run -- filed as
#: follow-up #65, deliberately not done in Branch 10. Each entry is proved to
#: still be a literal below, so a stale exemption cannot sit here unnoticed.
_P4_LOCAL_TABLES = {
    ("talismans_client.py", "_RESULT_CAP_MARKERS"),
    ("talismans_client.py", "_RANGE_CAP_MARKERS"),
    ("fwa_logs.py", "_RESULT_CAP_MARKERS"),
}

#: The only node types a binding expression may contain: a name, a dotted
#: name, and ``+`` between them (``curator_client`` composes two shared
#: families). A ``Constant``, ``Tuple``, ``List``, ``Set`` or ``Call``
#: anywhere inside means a table was restated rather than bound.
_BINDING_NODES = (ast.Name, ast.Attribute, ast.BinOp, ast.Add, ast.Load)


def _table_assignments(path: Path) -> list[tuple[str, ast.expr]]:
    """Top-level assignments to a :data:`_SHARED_TABLE_NAMES` name."""
    found: list[tuple[str, ast.expr]] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id] if node.value is not None else []
        else:
            continue
        for name in targets:
            if name in _SHARED_TABLE_NAMES:
                found.append((name, node.value))
    return found


def _is_a_binding(value: ast.expr) -> bool:
    return all(isinstance(node, _BINDING_NODES) for node in ast.walk(value))


@pytest.mark.guard
def test_error_pattern_tables_are_not_re_declared() -> None:
    """The fragment tables are evidence, and evidence lives in one place.

    Four Ethereum clients each hand-typed the "this endpoint can't" table and
    they had already drifted: ``curator_client`` dropped ``api key`` while
    restating the rest, ``personal token`` survived only in ``ttt_client``, and
    drpc's routing triplet only in ``curator_client``. Every one of those is a
    refusal the other pools can meet. Since Branch 10 the tables live in
    ``data/rpc_classify.py`` with their provider attributions, and a client
    *binds* one rather than restating it.

    The *policy* around them is untouched and must stay per client -- which
    table is bound, what a non-dict error means, whether a malformed code is
    consulted -- so this guard only forbids the restatement.

    Shaped on the AST rather than on the text (WP-A review M5): the substring
    form asserted ``f"{name} = (" not in source``, which reads
    ``_ENDPOINT_LIMITATION_PATTERNS = tuple([...])`` -- or a list, or a set,
    or a line broken after the ``=`` -- as compliant.
    """
    offenders: list[str] = []
    seen: set[tuple[str, str]] = set()
    for path in _CLASSIFIER_SOURCES:
        for name, value in _table_assignments(path):
            seen.add((path.name, name))
            if (path.name, name) in _P4_LOCAL_TABLES:
                continue
            if _is_a_binding(value):
                continue
            offenders.append(
                f"{path.name}:{value.lineno} {name} = "
                f"{type(value).__name__} literal"
            )
    assert not offenders, (
        f"{offenders} restate a table instead of binding one from "
        "data/rpc_classify.py. The four Ethereum copies had already drifted "
        "against each other before Branch 10; a fifth would drift too."
    )

    # Anti-vacuity: the walk must actually have reached the modules it claims
    # to guard, including the one the old glob could not see.
    assert ("ttt_client.py", "_ENDPOINT_LIMITATION_PATTERNS") in seen
    assert ("curator_client.py", "_RANGE_LIMITATION_PATTERNS") in seen
    assert ("fwa_logs.py", "_RESULT_CAP_MARKERS") in seen
    assert _P4_LOCAL_TABLES <= seen


@pytest.mark.guard
def test_every_p4_exemption_is_still_a_literal_that_would_fail() -> None:
    """A stale allow-set entry is a hole in the guard above, not a comment.

    Each exempted table must still BE a restated literal: the moment one
    becomes a binding, the exemption stops excusing anything and must be
    deleted so the name is guarded again.
    """
    by_module = {path.name: _table_assignments(path) for path in _CLASSIFIER_SOURCES}
    for file_name, table in sorted(_P4_LOCAL_TABLES):
        values = [v for name, v in by_module[file_name] if name == table]
        assert len(values) == 1, f"{file_name} no longer assigns {table} exactly once"
        assert not _is_a_binding(values[0]), (
            f"{file_name}:{values[0].lineno} {table} is now a binding, so its "
            "P4 exemption excuses nothing -- drop it from _P4_LOCAL_TABLES"
        )


def test_jsonrpc_envelope_is_built_in_one_place() -> None:
    assert rpc_common.jsonrpc_payload(7, "eth_call", [{"to": "0x0"}, "latest"]) == {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "eth_call",
        "params": [{"to": "0x0"}, "latest"],
    }
    for module in JSONRPC_MODULES:
        assert "jsonrpc_payload(" in _module_source(module), (
            f"{module.__name__} hand-rolls the JSON-RPC envelope"
        )
        assert '"jsonrpc": "2.0"' not in _module_source(module)


async def test_pace_never_sleeps_on_a_first_call_or_a_zero_interval() -> None:
    """Both cases must still advance the clock -- the copies all did."""
    assert await rpc_common.pace(0.0, 5.0) > 0
    assert await rpc_common.pace(1.0, 0.0) > 0


async def test_pace_is_self_correcting() -> None:
    """A call that was already slow pays no extra delay."""
    import time

    long_ago = time.monotonic() - 10.0
    started = time.monotonic()
    await rpc_common.pace(long_ago, 0.25)
    assert time.monotonic() - started < 0.2


@pytest.mark.parametrize(
    ("module", "class_name"),
    list(ALL_CLIENTS.items()),
    ids=lambda v: v if isinstance(v, str) else v.__name__.rsplit(".", 1)[-1],
)
def test_every_client_inherits_the_owned_client_lifecycle(module, class_name) -> None:
    """``close`` / ``__aenter__`` / ``__aexit__`` were identical in all of them."""
    cls = getattr(module, class_name)
    assert issubclass(cls, rpc_common.OwnedHttpClient)
    overridden = _client_class_defs(module, class_name) & {
        "close",
        "__aenter__",
        "__aexit__",
    }
    assert not overridden, (
        f"{class_name} re-implements {sorted(overridden)}; the shared mixin in "
        "data/rpc_common.py already does exactly this for every module in "
        "ALL_CLIENTS"
    )


async def test_an_injected_http_client_is_not_closed_by_the_client() -> None:
    """The lifecycle contract, exercised once through a real client.

    An injected client belongs to the caller -- the tests inject one built on
    a mock transport, and closing it would break the next test to use it.
    """
    import httpx

    injected = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    async with ocm_client.OCMClient(http_client=injected) as client:
        assert client._owns_client is False
    assert injected.is_closed is False
    await injected.aclose()

    owned = ocm_client.OCMClient()
    assert owned._owns_client is True
    await owned.close()
    assert owned._client.is_closed is True


# ---------------------------------------------------------------------------
# 4. the divergence that must NOT be consolidated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module", RPC_CLIENTS, ids=lambda m: m.__name__.rsplit(".", 1)[-1]
)
def test_each_rpc_client_still_owns_its_error_policy(module) -> None:
    """``_rpc`` stays per-client. This is the load-bearing half of MEDI-17.

    Read :mod:`maxpane_dashboard.data.rpc_common`'s docstring before deleting
    this test. The five bodies are five *policies*, not five copies: which
    failures rotate, which retry, which raise, and what a caller learns from
    the exception. Each was shaped by a live outage and each is pinned by its
    own suite. A shared ``_rpc`` covering all five would be a policy switch
    larger than the five bodies, with every client's behaviour reachable from
    every other client's bug.
    """
    client_class = next(
        cls for mod, cls in ALL_CLIENTS.items() if mod is module
    )
    assert "_rpc" in _client_class_defs(module, client_class), (
        f"{module.__name__} no longer defines its own _rpc -- if that is "
        "deliberate, the rationale in data/rpc_common.py must be updated and "
        "the per-client error-policy tests re-verified, not deleted"
    )


def test_talismans_classifies_on_message_text_not_error_code() -> None:
    """One code, three meanings -- all read off the wire on 2026-07-27.

    Re-asserted here (and not only in the talismans suite) because it is the
    single fact that most tempts a would-be consolidator: a code-based
    classifier looks tidier and aborts the whole fallback chain.
    """
    classify = talismans_client._classify_rpc_error
    archive = {"code": -32602, "message": "Archive requests require a personal token"}
    range_cap = {"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}
    assert classify(archive).kind == "archive"
    assert classify(range_cap).kind == "range_cap"


def test_shrinking_is_narrower_than_retrying() -> None:
    """``rate_limit`` and ``archive`` must never shrink.

    A smaller window buys no quota, and the archive gate is on depth, not
    width. Retrying harder is how a keyless endpoint starts refusing you.
    """
    assert talismans_client._SHRINKABLE == {"range_cap", "result_cap", "timeout"}


def test_rate_limit_wording_wins_over_archive_wording() -> None:
    """A 429 body can read like a permanent archive gate. Order matters."""
    classified = talismans_client._classify_rpc_error(
        {"code": -32005, "message": "rate limit exceeded; request a personal token"}
    )
    assert classified.kind == "rate_limit"


def test_state_and_log_endpoint_pools_stay_separate() -> None:
    """publicnode batches ``eth_call`` and 403s archive ``eth_getLogs``."""
    for module in (talismans_client, ttt_client):
        assert module._LOG_RPCS != [module._PRIMARY_RPC, *module._FALLBACK_RPCS]
        assert module._LOG_RPCS, f"{module.__name__} lost its log pool"


@pytest.mark.parametrize(
    "module",
    [fwa_client, ttt_client, talismans_client],
    ids=["fwa", "ttt", "talismans"],
)
def test_banned_host_lists_still_raise_at_construction(module) -> None:
    """The keyless constraint is enforced by the constructor, not a comment."""
    assert module._BANNED_RPC_HOSTS
    banned = next(iter(module._BANNED_RPC_HOSTS))
    client_class = next(cls for mod, cls in ALL_CLIENTS.items() if mod is module)
    with pytest.raises(ValueError):
        getattr(module, client_class)(primary_rpc=f"https://{banned}/x")


def test_talismans_and_ttt_ban_exactly_the_same_hosts() -> None:
    """The copy is deliberate, and this is the agreement test that binds it.

    ``talismans_client._BANNED_RPC_HOSTS`` is a hand-typed copy of ttt's: the
    two run the same two-pool Ethereum-mainnet workload (state pool + archive
    ``eth_getLogs`` pool), so a host that is dead, keyed or silently truncating
    for one is all three for the other. Hoisting it into a shared module would
    be wrong for the same reason the five ``_rpc`` bodies stay split -- see
    ``fwa_client``, whose table is ttt's **plus** ``eth.drpc.org``, because fwa
    bans that host from its *state* pool only and still uses it for recent
    logs, where it works (``.claude/rules/data.md``, "RPC endpoints"). Update
    both tables or neither.
    """
    assert talismans_client._BANNED_RPC_HOSTS == ttt_client._BANNED_RPC_HOSTS
    assert fwa_client._BANNED_RPC_HOSTS - ttt_client._BANNED_RPC_HOSTS == {
        "eth.drpc.org"
    }


def test_the_rationale_for_not_sharing_rpc_is_written_down() -> None:
    """The argument lives next to the code it justifies, not in a commit message."""
    doc = inspect.getdoc(rpc_common) or ""
    for client in ("talismans", "ttt", "fwa", "cattown", "ocm"):
        assert client in doc, f"rpc_common's docstring no longer explains {client}"
