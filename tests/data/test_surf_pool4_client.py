"""Tests for ``maxpane_dashboard.data.surf_pool4_client`` (WP6).

**Zero network, and proved structurally.** Every test drives the client through
an ``httpx.MockTransport``; :func:`test_no_socket_is_reachable_from_this_file`
scans this module's own source and fails on any ``httpx.AsyncClient(`` built
without an explicit ``transport=``, because that is a live socket waiting for a
CI runner with connectivity. ``tests/test_fwa_guardrails.py`` is the precedent
and this is that guard, narrowed to one file.

Three transport doubles, and they are not interchangeable:

* ``_no_network`` raises ``AssertionError``, which is neither an
  ``httpx.HTTPError`` nor a ``ValueError`` nor a ``RuntimeError``, so it sails
  through every ``except`` in the client and out of the test. It proves a code
  path performed **no I/O at all**.
* ``_offline`` raises ``httpx.ConnectError`` — a real transport failure the
  client classifies — so it models a total outage and every ``fetch_*``
  degrades to ``None`` through its normal retry/rotation path.
* :class:`RecordingTransport` keeps every ``(url, method, payload)``, which is
  how the four-pool separation is **asserted on the URLs the transport was
  actually handed** rather than assumed from a constant.

Every payload replayed here is a committed capture under
``tests/fixtures/surf/pool4/``, served back by **calldata**, not by position.
That is deliberate: the handler answers whatever the client asks, so a test
passes only if the client independently builds the same calldata WP1 captured
against the live chain. Expected values are decoded from those files, never
typed from memory.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import surf_client
from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data import surf_pool4_client as C
from maxpane_dashboard.data import surf_v4
from maxpane_dashboard.data.surf_models import (
    POOL4_DISCOVERY_STATES,
    POOL4_NETWORKS,
)
from maxpane_dashboard.data.surf_pool4_client import Pool4Client

# Imported rather than hand-typed (A18): a wire-model rename becomes a
# collection error here instead of a panel full of ``None``.
from tests.data.test_surf_pool4_models import CONSTRUCTOR_KWARGS

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "pool4"

SEPOLIA, MAINNET = POOL4_NETWORKS

#: Longer than the walk may follow, so the cap is what stops it.
_LONG_CHAIN = 8
_NOT_DISCOVERED, _ADOPTED, _REJECTED = POOL4_DISCOVERY_STATES

#: The gate names a rejection detail cites, taken from WP3's own vocabulary.
#: Hand-typing them here would be a copy of a neighbour's string that goes
#: stale the moment they reword it — and a rewording is not a defect, so the
#: red would be noise. What these assertions mean is "the detail names the gate
#: that failed", and that survives any rewording.
_GATE_FLAGS, _GATE_PERMISSIONS, _GATE_TOKEN = P.FINGERPRINT_GATES[:3]


def load(name: str) -> Any:
    with open(FIXTURES / f"{name}.json") as fh:
        return json.load(fh)


def load_request(name: str) -> Any:
    with open(FIXTURES / f"{name}.request.json") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(
        f"test attempted real network access: {request.method} {request.url}",
        request=request,
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, method, payload_or_None)``."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[tuple[str, str, Any]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                try:
                    payload = json.loads(request.content)
                except ValueError:
                    payload = None
            self.requests.append((str(request.url), request.method, payload))
            return handler(request)

        super().__init__(_wrapped)

    def urls(self) -> list[str]:
        return [u for (u, _m, _p) in self.requests]

    def calldata(self) -> list[str]:
        """Every ``eth_call`` ``data`` word this transport was handed."""
        out: list[str] = []
        for (_u, _m, payload) in self.requests:
            for entry in _entries(payload):
                if entry.get("method") == "eth_call":
                    out.append(str(entry["params"][0].get("data", "")).lower())
        return out

    def log_ranges(self) -> list[tuple[int, int]]:
        """Every ``(fromBlock, toBlock)`` this transport was asked for."""
        out: list[tuple[int, int]] = []
        for (_u, _m, payload) in self.requests:
            for entry in _entries(payload):
                if entry.get("method") == "eth_getLogs":
                    flt = entry["params"][0]
                    out.append((int(flt["fromBlock"], 16), int(flt["toBlock"], 16)))
        return out


def _entries(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    return [payload] if isinstance(payload, dict) else []


def _client_on(transport: httpx.BaseTransport, **kw: Any) -> Pool4Client:
    return Pool4Client(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _raising_client(**kw: Any) -> Pool4Client:
    """Must not be asked for anything — proves zero I/O."""
    return _client_on(httpx.MockTransport(_no_network), **kw)


def _offline_client(**kw: Any) -> Pool4Client:
    """Every request fails at the socket — the total-outage double."""
    return _client_on(httpx.MockTransport(_offline), **kw)


# ---------------------------------------------------------------------------
# Fixture replay — served by calldata, never by position
# ---------------------------------------------------------------------------


def answers_by_calldata(fixture: str) -> dict[tuple[str, str], Any]:
    """``(contract, calldata) -> raw return`` from a committed capture pair.

    The capture's ``.request.json`` body and its ``.json`` response are joined
    on the JSON-RPC ``id``. Serving by calldata is what makes the replay an
    assertion rather than a fixture read: the client has to build the same
    bytes WP1 sent to the live chain or it gets nothing back.
    """
    body = load_request(fixture)["body"]
    if isinstance(body, dict):
        body = [body]
    response = load(fixture)["response"]
    if isinstance(response, dict):
        response = [response]
    by_id = {e.get("id"): e for e in response}
    out: dict[tuple[str, str], Any] = {}
    for entry in body:
        answer = by_id.get(entry.get("id"))
        if answer is None or "result" not in answer:
            continue
        params = entry["params"][0]
        out[(str(params["to"]).lower(), str(params["data"]).lower())] = (
            answer["result"]
        )
    return out


def replay_handler(
    *fixtures: str,
    block_number: int | None = None,
    overrides: dict[tuple[str, str], Any] | None = None,
    reverting: set[str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler that answers whatever calldata the client asks for.

    *overrides* replaces one answer (``None`` deletes it, so the getter goes
    silent). *reverting* is a set of lowercase calldata the handler answers
    with a JSON-RPC error, the way a getter the contract does not implement
    does on a real node.
    """
    table: dict[tuple[str, str], Any] = {}
    for fixture in fixtures:
        table.update(answers_by_calldata(fixture))
    for key, value in (overrides or {}).items():
        if value is None:
            table.pop(key, None)
        else:
            table[key] = value
    dead = {d.lower() for d in (reverting or set())}
    head = block_number if block_number is not None else load(fixtures[0]).get(
        "block_number"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        entries = _entries(payload)
        out = []
        for entry in entries:
            rid = entry.get("id")
            if entry.get("method") == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": rid, "result": hex(head or 0)})
                continue
            params = entry["params"][0]
            key = (str(params["to"]).lower(), str(params["data"]).lower())
            if key[1] in dead:
                out.append({
                    "jsonrpc": "2.0", "id": rid,
                    "error": {"code": 3, "message": "execution reverted"},
                })
                continue
            if key in table:
                out.append({"jsonrpc": "2.0", "id": rid, "result": table[key]})
            else:
                # Unknown calldata: the honest answer a node gives for a
                # getter that is not there. NOT a hidden test pass.
                out.append({"jsonrpc": "2.0", "id": rid, "result": "0x"})
        body: Any = out if isinstance(payload, list) else out[0]
        return httpx.Response(200, json=body)

    return handler


def log_handler(fixture: str) -> Callable[[httpx.Request], httpx.Response]:
    """Serve one captured ``eth_getLogs`` window for any range asked."""
    result = load(fixture)["response"]["result"]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": payload.get("id"), "result": result}
        )

    return handler


HOOK = load("hook_state_healthy")["addresses"]["hook"]
VAULT = load("hook_state_healthy")["addresses"]["vault"]
DRIPPER = load("hook_state_healthy")["addresses"]["dripper"]
TOKEN = load("hook_state_healthy")["addresses"]["token"]
POOL_MANAGER = load("pool_slot0")["pool_manager"]
POOL_ID = load("pool_slot0")["pool_id"]


# ---------------------------------------------------------------------------
# 1. The four pools, and the measurements behind the Sepolia ones
# ---------------------------------------------------------------------------


def test_there_are_four_pools_not_two():
    client = _raising_client()
    pools = {
        (SEPOLIA, "state"): client.state_endpoints(SEPOLIA),
        (SEPOLIA, "logs"): client.log_endpoints(SEPOLIA),
        (MAINNET, "state"): client.state_endpoints(MAINNET),
        (MAINNET, "logs"): client.log_endpoints(MAINNET),
    }
    for key, urls in pools.items():
        assert urls, f"{key} has no endpoints"
    sepolia = set(pools[(SEPOLIA, "state")]) | set(pools[(SEPOLIA, "logs")])
    mainnet = set(pools[(MAINNET, "state")]) | set(pools[(MAINNET, "logs")])
    assert not (sepolia & mainnet), (
        "a URL shared between two chains is how a Sepolia read silently "
        "answers with mainnet state"
    )


def test_the_mainnet_pools_agree_with_surf_client():
    """Redundancy plus an agreement test — never a derivation.

    ``surf_client.py`` is a 3,200-line shared file with another owner, so its
    URLs are transcribed rather than imported. Deriving them would make this
    assertion compare a constant against itself and it could never fail again.
    """
    assert C.MAINNET_STATE_RPCS == [
        surf_client.STATE_RPC_PRIMARY, *surf_client.STATE_RPC_FALLBACKS
    ]
    assert C.MAINNET_LOG_RPCS == list(surf_client.LOG_RPCS)


def test_the_error_pattern_tables_agree_with_surf_client():
    assert C._ENDPOINT_LIMITATION_PATTERNS == (
        surf_client._ENDPOINT_LIMITATION_PATTERNS
    )
    assert C._RANGE_LIMITATION_PATTERNS == surf_client._RANGE_LIMITATION_PATTERNS
    assert C._MALFORMED_REQUEST_CODES == surf_client._MALFORMED_REQUEST_CODES


def test_the_log_window_constants_agree_with_surf_client():
    assert C.LOG_WINDOW_BLOCKS == surf_client.LOG_WINDOW_BLOCKS
    assert C._LOG_MIN_WINDOW == surf_client._LOG_MIN_WINDOW
    assert C._LOG_MAX_SHRINKS == surf_client._LOG_MAX_SHRINKS


def test_the_banned_list_contains_every_host_surf_client_bans():
    for host in surf_client._BANNED_RPC_HOSTS:
        assert host in C._BANNED_RPC_HOSTS, (
            f"{host} is banned in surf_client and reachable here"
        )


def test_sepolia_serves_logs_from_publicnode_and_the_plan_body_was_wrong():
    """A11, re-measured 2026-09-01. The plan's §3 ban is the defect.

    §3 says "publicnode is BANNED from ``SEPOLIA_LOG_RPCS``", reasoning by
    analogy from mainnet. Measured, Sepolia publicnode served a 400-block
    archive window (90 logs) *and* the 30-call getter round twice back to
    back. It is the primary of both Sepolia pools; the mainnet split is a fact
    about mainnet publicnode, not about the vendor.
    """
    client = _raising_client()
    assert any("publicnode" in u for u in client.log_endpoints(SEPOLIA))
    assert any("publicnode" in u for u in client.state_endpoints(SEPOLIA))
    assert client.state_endpoints(SEPOLIA)[0] == client.log_endpoints(SEPOLIA)[0]


def test_mainnet_logs_never_go_to_publicnode():
    """Mainnet publicnode refuses archive ``eth_getLogs`` (CLAUDE.md hazards)."""
    client = _raising_client()
    assert all("publicnode" not in u for u in client.log_endpoints(MAINNET))
    assert "publicnode" in client.state_endpoints(MAINNET)[0]


def test_1rpc_is_a_sepolia_state_fallback_and_never_a_log_endpoint():
    """Measured: it caps ``eth_getLogs`` at 50 blocks (``-32602``).

    It also 429s on the *second* 30-call batch of a burst, asking for an
    OnFinality key — so it may be a fallback (reached only when the primary is
    already failing) and must never be the primary.
    """
    client = _raising_client()
    state = client.state_endpoints(SEPOLIA)
    assert any("1rpc.io" in u for u in state)
    assert "1rpc.io" not in state[0]
    assert all("1rpc.io" not in u for u in client.log_endpoints(SEPOLIA))


def test_tenderly_sepolia_serves_logs_and_never_state():
    """Measured: ``-32005 rate limit exceeded`` on a 30-call batch, cold.

    A 3-call probe passes, which is why measuring with the batch the client
    actually sends is the whole point — a toy probe would have put a host in
    the state pool that cannot serve one real getter round.
    """
    client = _raising_client()
    assert any("tenderly" in u for u in client.log_endpoints(SEPOLIA))
    assert all("tenderly" not in u for u in client.state_endpoints(SEPOLIA))


@pytest.mark.parametrize(
    "url",
    [
        "https://eth.llamarpc.com",            # 521, origin down
        "https://rpc.ankr.com/eth",            # now keyed
        "https://cloudflare-eth.com",          # -32046 on every call
        "https://mainnet.infura.io/v3/x",      # keyed
        "https://sepolia.drpc.org",            # code 35, "free plan"
        "https://rpc.sepolia.org",             # HTTP 404, no JSON-RPC
        "https://endpoints.omniatech.io/v1/eth/sepolia/public",  # 521
    ],
)
@pytest.mark.parametrize(
    "kwarg",
    ["sepolia_state_rpcs", "sepolia_log_rpcs",
     "mainnet_state_rpcs", "mainnet_log_rpcs"],
)
def test_a_banned_host_is_rejected_at_construction(url, kwarg):
    with pytest.raises(ValueError):
        Pool4Client(
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network)),
            **{kwarg: [url]},
        )


def test_the_mainnet_drpc_log_endpoint_survives_the_sepolia_drpc_ban():
    """``sepolia.drpc.org`` is banned; ``eth.drpc.org`` is not.

    The ban is by hostname, so banning the Sepolia one must not take out the
    mainnet log endpoint that works. This is the assertion that would have
    caught a ban written as ``"drpc.org"``.
    """
    assert "sepolia.drpc.org" in C._BANNED_RPC_HOSTS
    assert "eth.drpc.org" not in C._BANNED_RPC_HOSTS
    client = _raising_client()
    assert any("eth.drpc.org" in u for u in client.log_endpoints(MAINNET))


def test_every_endpoint_is_keyless():
    client = _raising_client()
    for network in POOL4_NETWORKS:
        for url in client.state_endpoints(network) + client.log_endpoints(network):
            assert not re.search(r"[0-9a-fA-F]{24,}", url), f"{url} looks keyed"
            assert "key" not in url.lower() and "token" not in url.lower()


# ---------------------------------------------------------------------------
# 2. Error classification — on message text, from the captured probes
# ---------------------------------------------------------------------------


def _probe(label: str) -> dict:
    for probe in load("rpc_error_states")["probes"]:
        if probe["label"] == label:
            return probe
    raise AssertionError(f"no probe {label}")


def test_the_two_minus_32602s_mean_different_things_and_are_classified_apart():
    """CLAUDE.md's rule, with the captured evidence behind it.

    ``rpc_error_states.json`` holds two live ``-32602`` bodies: 1rpc's
    shrinkable log cap and publicnode's genuinely malformed request. Code-first
    classification calls both malformed, stops rotating, and turns the one
    recoverable error in the set into a dead panel.
    """
    capped = _probe("range_capped_getLogs")["response"]["error"]
    malformed = _probe("malformed_params")["response"]["error"]
    assert capped["code"] == malformed["code"] == -32602

    assert C._is_range_limitation(capped) is True
    assert C._is_range_limitation(malformed) is False
    assert C._looks_like_endpoint_limitation(capped) is True
    assert C._looks_like_endpoint_limitation(malformed) is False


async def test_a_reverting_getter_degrades_its_entry_without_rotating_the_pool():
    """``execution reverted`` is the *contract's* answer, not the host's.

    The transcribed classifier would rotate on it — ``code 3`` matches no
    message pattern and is not in ``_MALFORMED_REQUEST_CODES``, so it errs
    toward "try the next endpoint". That is right for a single call and wrong
    for a batch, and the batch path never asks: a **per-entry** error becomes
    that entry's ``None`` and the round returns. Rotating instead would ask
    every endpoint in the pool for the same getter a differently-built mainnet
    hook simply does not implement (plan R1), turning one dark field into three
    wasted round trips per refresh.

    Pinned on the URL count rather than on the classifier, because the
    classifier is not what decides it.
    """
    err = _probe("unknown_selector_revert")["response"]["error"]
    assert err["code"] == 3 and err["message"] == "execution reverted"

    dead = {P.encode_getter(P.HOOK_SELECTORS["capFloor"])}
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", reverting=dead)
    )
    client = _client_on(transport)
    state = await client.fetch_hook_state(HOOK, network=SEPOLIA)
    assert state.cap_floor_wei is None
    assert len(transport.urls()) == 1, (
        "a reverted getter rotated the pool: " + repr(transport.urls())
    )


def test_the_measured_sepolia_drpc_and_tenderly_errors_rotate():
    """Both real 4xx bodies this package captured must read as "this host"."""
    drpc = {"code": 35,
            "message": "chain is not available on free plan, "
                       "please upgrade to paid plan"}
    tenderly = {"code": -32005, "message": "rate limit exceeded"}
    assert C._looks_like_endpoint_limitation(drpc) is True
    assert C._looks_like_endpoint_limitation(tenderly) is True
    assert C._is_range_limitation(drpc) is False
    assert C._is_range_limitation(tenderly) is False


# ---------------------------------------------------------------------------
# 3. Structural: no socket, no textual, no widget
# ---------------------------------------------------------------------------


def _code_only(source: str) -> str:
    """Source with docstrings and comments blanked, line numbers preserved."""
    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    source = re.sub(r'(?s)""".*?"""', blank, source)
    source = re.sub(r"(?s)'''.*?'''", blank, source)
    return re.sub(r"#[^\n]*", blank, source)


def test_no_socket_is_reachable_from_this_file():
    """Structural: every test here drives a transport, never a socket.

    Asserted by construction rather than by running offline — an HTTP client
    built without an explicit ``transport=`` is a live socket waiting for a CI
    runner with connectivity, and it would pass every assertion in this file on
    a machine that happens to have the chain reachable.
    """
    code = _code_only(Path(__file__).read_text(encoding="utf-8"))
    banned = [
        f"{mod}.{call}" for mod, call in (
            ("requests", "get"), ("requests", "post"),
            ("urllib", "request"), ("socket", "socket"),
        )
    ]
    for needle in banned:
        assert needle not in code, f"this file may reach the network: {needle}"

    for match in re.finditer(r"httpx\.(?:Async)?Client\(", code):
        tail = code[match.end():match.end() + 400]
        depth, closing = 1, len(tail)
        for i, ch in enumerate(tail):
            depth += (ch == "(") - (ch == ")")
            if depth == 0:
                closing = i
                break
        lineno = code[:match.start()].count("\n") + 1
        assert "transport=" in tail[:closing], (
            f"{Path(__file__).name}:{lineno} builds an httpx client with no "
            "explicit transport — every pool4 client test must be hermetic"
        )

    assert "http_client" in Pool4Client.__init__.__code__.co_varnames


def test_the_client_reaches_no_widget_no_textual_and_no_second_client():
    """Contract §0.5's import boundary for ``surf_pool4_client``, structurally.

    ``surf_v4`` and ``evm_abi`` are beyond §0.5's literal three-name list and
    are here on purpose: both are the repo's existing stdlib-only codecs, and
    re-implementing a slot derivation or a uint decode is exactly what
    CLAUDE.md's "reuse before you build" forbids. A17 already made the same
    call for WP3 and told WP8 to enforce the *property*, not the table.
    """
    tree = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    for banned in ("textual", "aiohttp", "requests"):
        assert not any(m == banned or m.startswith(banned + ".") for m in modules)
    assert not any(".widgets" in m or m.startswith("widgets") for m in modules)
    assert not any(".analytics" in m for m in modules)
    assert "maxpane_dashboard.data.surf_client" not in modules, (
        "importing surf_client would re-couple this module to the shared file "
        "the whole package exists to stay out of"
    )


def test_no_constant_in_this_module_hardcodes_the_vault_decimals():
    """A18/A22: the hardcode must not return wearing a name.

    24 is a *Sepolia* measurement. The mainnet vault does not exist and nothing
    binds its ``_decimalsOffset()`` to Sepolia's, so a constant would reproduce
    the 10⁶ share-price defect at the switchover — silently, because both wrong
    forms render as plausible numbers.
    """
    code = _code_only(Path(C.__file__).read_text(encoding="utf-8"))
    assert "POOL4_VAULT_DECIMALS" not in code
    assert not re.search(r"\b10\s*\*\*\s*24\b", code)
    assert not re.search(r"\b1e24\b", code)
    assert not re.search(r"decimals\s*=\s*24\b", code)


# ---------------------------------------------------------------------------
# 4. Four-pool separation — asserted on the URLs actually handed over
# ---------------------------------------------------------------------------


#: The hostnames each pool is allowed to reach, restated here rather than
#: derived from the client's constants.
#:
#: This is the whole point of the separation tests, and getting it wrong is a
#: live defect this package caught in its own first draft: an earlier version
#: asserted ``url in C.SEPOLIA_LOG_RPCS``, which compares the constant under
#: test against itself and stays green when the Sepolia log pool is repointed
#: at a mainnet URL. Redundancy plus an agreement test is the repo's pattern
#: (``_GAME_CYCLE``, ``NETWORK_WORDS``) and it is what makes these bite.
_EXPECTED_HOSTS = {
    (SEPOLIA, "state"): {"ethereum-sepolia-rpc.publicnode.com", "1rpc.io"},
    (SEPOLIA, "logs"): {"ethereum-sepolia-rpc.publicnode.com", "gateway.tenderly.co"},
    (MAINNET, "state"): {"ethereum-rpc.publicnode.com", "gateway.tenderly.co",
                         "rpc.mevblocker.io"},
    (MAINNET, "logs"): {"gateway.tenderly.co", "eth.drpc.org"},
}


def _hosts(urls: list[str]) -> set[str]:
    from urllib.parse import urlparse
    return {(urlparse(u).hostname or "").lower() for u in urls}


def test_the_four_pools_are_the_hosts_this_package_measured():
    client = _raising_client()
    for (network, kind), expected in _EXPECTED_HOSTS.items():
        urls = (client.state_endpoints(network) if kind == "state"
                else client.log_endpoints(network))
        assert _hosts(urls) == expected, f"{network}/{kind} pool drifted"


def _assert_reached(transport: RecordingTransport, network: str, kind: str) -> None:
    """Every URL handed to the transport belongs to that one pool, and to no other.

    Two independent assertions on purpose. The first is against the
    hand-restated ``_EXPECTED_HOSTS`` (so repointing a pool reddens it); the
    second is against the *other three* pools' constants (so a URL that
    somehow satisfies the first but is also in a sibling pool still reddens).
    """
    urls = transport.urls()
    assert urls, "no request was made at all"
    assert _hosts(urls) <= _EXPECTED_HOSTS[(network, kind)], (
        f"a {network}/{kind} read reached {sorted(_hosts(urls))}"
    )

    # Subset membership alone is NOT enough, and a mutation caught this test
    # being too weak: the mainnet state and log pools both contain
    # ``gateway.tenderly.co``, so routing a state call through the log pool
    # reached a URL that is a member of both and the subset check stayed green.
    # The URLs seen must be the pool's own PREFIX, in order — which pins which
    # list was walked, not merely which hosts were touched.
    pool = {
        (SEPOLIA, "state"): C.SEPOLIA_STATE_RPCS,
        (SEPOLIA, "logs"): C.SEPOLIA_LOG_RPCS,
        (MAINNET, "state"): C.MAINNET_STATE_RPCS,
        (MAINNET, "logs"): C.MAINNET_LOG_RPCS,
    }[(network, kind)]
    seen_in_order = list(dict.fromkeys(urls))
    assert seen_in_order == pool[:len(seen_in_order)], (
        f"a {network}/{kind} read walked {seen_in_order}, which is not the "
        f"head of that pool {pool}"
    )
    others = {
        (SEPOLIA, "state"): C.SEPOLIA_STATE_RPCS,
        (SEPOLIA, "logs"): C.SEPOLIA_LOG_RPCS,
        (MAINNET, "state"): C.MAINNET_STATE_RPCS,
        (MAINNET, "logs"): C.MAINNET_LOG_RPCS,
    }
    other_chain = MAINNET if network == SEPOLIA else SEPOLIA
    forbidden = set(others[(other_chain, "state")]) | set(others[(other_chain, "logs")])
    assert not (set(urls) & forbidden), (
        f"a {network} read reached a {other_chain} URL: {sorted(set(urls) & forbidden)}"
    )


async def test_a_sepolia_state_read_never_reaches_a_mainnet_url():
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    await client.fetch_hook_state(HOOK, network=SEPOLIA)
    _assert_reached(transport, SEPOLIA, "state")


async def test_a_sepolia_log_read_never_reaches_a_mainnet_or_state_url():
    transport = RecordingTransport(log_handler("flow_logs_full"))
    client = _client_on(transport)
    await client.fetch_flow_logs(HOOK, 11_609_600, 11_610_000, network=SEPOLIA)
    _assert_reached(transport, SEPOLIA, "logs")
    # 1rpc caps eth_getLogs at 50 blocks: it is a state fallback and must
    # never appear on a log read.
    assert all("1rpc.io" not in u for u in transport.urls())


async def test_a_mainnet_read_never_reaches_a_sepolia_url():
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", block_number=25_883_917)
    )
    client = _client_on(transport)
    await client.fetch_hook_state(HOOK, network=MAINNET)
    _assert_reached(transport, MAINNET, "state")
    assert all("sepolia" not in u.lower() for u in transport.urls())


async def test_an_unrecognised_network_word_reaches_no_endpoint_at_all():
    """A closed vocabulary (A5), enforced at the transport boundary.

    ``"BASE"`` is a producer bug, not a new chain. A permissive default here —
    "fall back to mainnet" — would let a Sepolia-shaped read answer with
    mainnet state, which is R4's failure exactly, one layer lower than the
    network word on a panel title.
    """
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    assert await client.fetch_hook_state(HOOK, network="BASE") is None
    assert await client.fetch_vault_state(VAULT, network="BASE") is None
    assert await client.fetch_dripper_state(DRIPPER, network="BASE") is None
    assert await client.fetch_flow_logs(HOOK, 1, 2, network="BASE") is None
    assert await client.fetch_block_number(network="BASE") is None
    assert transport.requests == [], "an unknown network reached an endpoint"


# ---------------------------------------------------------------------------
# 5. Total outage — None everywhere, and no method raises
# ---------------------------------------------------------------------------


async def _every_fetch(client: Pool4Client) -> dict[str, Any]:
    return {
        "hook": await client.fetch_hook_state(
            HOOK, network=SEPOLIA, token_addr=TOKEN),
        "vault": await client.fetch_vault_state(VAULT, network=SEPOLIA),
        "dripper": await client.fetch_dripper_state(
            DRIPPER, network=SEPOLIA, token_addr=TOKEN),
        "slot0": await client.fetch_pool_slot0(
            POOL_ID, network=SEPOLIA, pool_manager=POOL_MANAGER),
        "logs": await client.fetch_flow_logs(
            HOOK, 11_609_600, 11_610_000, network=SEPOLIA),
        "events": await client.fetch_flow_events(
            HOOK, 11_609_600, 11_610_000, network=SEPOLIA),
        "block": await client.fetch_block_number(network=SEPOLIA),
        "verify": await client.verify_hook(
            HOOK, network=SEPOLIA, expected_token=TOKEN),
        "transaction": await client.fetch_transaction(
            "0x" + "ab" * 32, network=SEPOLIA),
        "vault_path": await client.resolve_vault_path(
            DRIPPER, network=SEPOLIA),
        "distributor": await client.fetch_distributor_state(
            DRIPPER, network=SEPOLIA),
        "docs": await client.fetch_docs_page(),
    }


async def test_a_total_outage_degrades_to_none_and_never_raises():
    """Every public method, through a socket that always fails.

    ``None``, never ``0`` and never ``[]``: an empty flow list would read as
    "nothing traded" and a zero counter would be persisted and outlive the
    outage that produced it.
    """
    results = await _every_fetch(_offline_client())
    for name, value in results.items():
        assert value is None, f"{name} returned {value!r} through a dead transport"


async def test_constructing_the_client_performs_no_io():
    client = _raising_client()
    assert client.state_endpoints(SEPOLIA)
    await client.close()  # injected client is the caller's; close must not fetch


# ---------------------------------------------------------------------------
# 6. The hook round
# ---------------------------------------------------------------------------


async def test_the_hook_round_asks_exactly_the_getters_the_capture_asked():
    """Selector agreement with the live capture, not with our own constants.

    The replay handler answers by calldata, so this passes only if the client
    independently builds the same 30 four-byte words WP1 sent to the chain.
    """
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    await client.fetch_hook_state(HOOK, network=SEPOLIA)

    captured = {
        str(e["params"][0]["data"]).lower()
        for e in load_request("hook_state_healthy")["body"]
    }
    assert len(captured) == 30
    # The capture predates mainnet, so the round is now the captured thirty
    # PLUS the two getters the mainnet hook grew. Asserted as an exact set —
    # a superset test would let a silently dropped getter through.
    extra = {
        P.encode_getter(P.HOOK_SELECTORS[name]).lower()
        for name in C.MAINNET_HOOK_GETTERS
    }
    assert extra == {"0x55e62941", "0xdb445ee8"}
    assert set(transport.calldata()) == captured | extra
    assert len(captured | extra) == 32


async def test_the_hook_round_never_asks_for_a_vault():
    """A3: the hook has **no** ``vault()`` getter and must not be asked for one.

    A field with no getter behind it is an invitation to fill it by scraping the
    announce channel, which is the one way this address must never be obtained.
    The path is ``rewardsRecipient()`` -> RewardDripper -> ``dripper.vault()``.
    """
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    state = await client.fetch_hook_state(HOOK, network=SEPOLIA)

    vault_selector = P.selector("vault()")
    assert all(not d.startswith(vault_selector) for d in transport.calldata())
    assert "vault" not in CONSTRUCTOR_KWARGS[type(state)]
    assert state.rewards_recipient is not None


async def test_hook_state_replays_the_capture_field_for_field():
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", "token_state")
    )
    client = _client_on(transport)
    state = await client.fetch_hook_state(
        HOOK, network=SEPOLIA, token_addr=TOKEN)

    fixture = load("hook_state_healthy")
    assert state.block_number == fixture["block_number"]
    assert state.token.lower() == TOKEN.lower()
    assert state.pool_manager.lower() == POOL_MANAGER.lower()
    assert state.pool_id == load("pool_slot0")["pool_id"]
    # The token's own supply, read off the token and not off the hook.
    supply = int(
        [e for e in load("token_state")["response"] if e["id"] == 1][0]["result"], 16
    )
    assert state.total_supply_wei == supply
    # Every field the capture answered is a number, not None.
    assert state.bps_denominator and state.reward_share_bps
    assert state.backstop_tick_lower is not None
    assert state.backstop_tick_upper is not None
    assert state.backstop_liquidity is not None


async def test_a_reverting_getter_degrades_one_field_not_the_round():
    """Plan R1 control (a). The hook is unverified source.

    ``hook_state_partial`` is the shape of a differently-built mainnet hook:
    three getters the launch-3 contract does not implement. A getter that
    reverts is one ``None`` inside an otherwise-healthy model, never a dropped
    round and never a dead panel.
    """
    dead = {P.encode_getter(P.HOOK_SELECTORS[n]) for n in
            ("capFloor", "refTick", "totalBurned")}
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", reverting=dead)
    )
    client = _client_on(transport)
    state = await client.fetch_hook_state(HOOK, network=SEPOLIA)

    assert state is not None
    assert state.cap_floor_wei is None
    assert state.ref_tick is None
    assert state.total_burned_wei is None
    # …and everything else still read.
    assert state.token is not None
    assert state.tokens_in_pool_wei is not None
    assert state.total_rewarded_wei is not None


async def test_an_empty_return_is_a_failed_read_never_a_zero():
    """A10, and the sharpest edge in this module.

    ``eth_call`` to an address with no code returns ``"0x"`` with **no error**
    (``rpc_error_states.json``, probe ``call_to_an_empty_address``), and
    ``evm_abi.decode_uint("")`` returns ``0``. Unguarded, a supply of zero and
    a backlog of zero get decoded, rendered and *persisted* — a sentinel that
    outlives the outage.
    """
    empty = _probe("call_to_an_empty_address")["response"]["result"]
    assert empty == "0x"

    supply_call = P.encode_getter(P.ERC20_SELECTORS["totalSupply"])
    transport = RecordingTransport(replay_handler(
        "hook_state_healthy",
        overrides={(TOKEN.lower(), supply_call.lower()): "0x"},
    ))
    client = _client_on(transport)
    state = await client.fetch_hook_state(
        HOOK, network=SEPOLIA, token_addr=TOKEN)
    assert state.total_supply_wei is None
    assert state.total_supply_wei != 0


async def test_omitting_the_token_address_leaves_the_supply_none():
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    state = await client.fetch_hook_state(HOOK, network=SEPOLIA)
    assert state.total_supply_wei is None
    assert state.token is not None


# ---------------------------------------------------------------------------
# 7. The vault — A22, and the most dangerous single line in the contract
# ---------------------------------------------------------------------------


async def test_decimals_is_read_first_and_the_share_price_is_asked_at_ten_to_it():
    """A22/A14. ``convertToAssets(10 ** decimals)``, never ``convertToAssets(1e18)``.

    The capture's own ``convertToAssets_millionth_of_a_share`` entry is the
    wrong-argument answer preserved as evidence: on a 24-decimal vault
    ``1e18`` is a *millionth* of a share and the honest number that comes back
    renders as ``0.0000013 IMD/share`` — a dead-looking vault, with no error
    anywhere. Both wrong forms are plausible on screen, so nothing downstream
    would catch it.
    """
    transport = RecordingTransport(replay_handler("vault_state"))
    client = _client_on(transport)
    state = await client.fetch_vault_state(VAULT, network=SEPOLIA)

    fixture = load("vault_state")
    assert state.decimals == fixture["vault_decimals"] == 24

    right = P.encode_convert_to_assets(10 ** state.decimals).lower()
    wrong = P.encode_convert_to_assets(10 ** 18).lower()
    sent = transport.calldata()
    assert right in sent
    assert wrong not in sent, "asked the price of a millionth of a share"

    # …and the argument is the one the corrected capture used.
    assert right == str(
        [e["params"][0]["data"] for e in load_request("vault_state")["body"]
         if e["id"] == 9][0]
    ).lower()

    # decimals is read BEFORE the round that uses it: two POSTs, and the first
    # one asks nothing else.
    assert len(transport.requests) == 2
    first_call_data = [
        e["params"][0]["data"] for e in _entries(transport.requests[0][2])
        if e.get("method") == "eth_call"
    ]
    assert first_call_data == [P.encode_getter(P.VAULT_SELECTORS["decimals"])]


async def test_the_share_price_follows_the_live_decimals_not_a_constant():
    """The switchover test: 24 is a Sepolia measurement, not a law.

    Serving ``decimals() == 18`` — a mainnet vault built with no offset — must
    move the ``convertToAssets`` argument with it. A hardcoded 24 passes every
    other test in this file and is wrong by 10⁶ the day mainnet lands.
    """
    decimals_call = P.encode_getter(P.VAULT_SELECTORS["decimals"])
    eighteen = "0x" + format(18, "064x")
    transport = RecordingTransport(replay_handler(
        "vault_state",
        overrides={(VAULT.lower(), decimals_call.lower()): eighteen},
    ))
    client = _client_on(transport)
    state = await client.fetch_vault_state(VAULT, network=SEPOLIA)

    assert state.decimals == 18
    assert P.encode_convert_to_assets(10 ** 18).lower() in transport.calldata()
    assert P.encode_convert_to_assets(10 ** 24).lower() not in transport.calldata()


async def test_an_unread_decimals_does_not_ask_convert_to_assets_at_all():
    """A22: a wrong-argument answer must never be laundered into a right field.

    A dark row is recoverable; a plausible wrong number is not. Every other
    vault field still reads — the degradation is per field, as everywhere else.
    """
    decimals_call = P.encode_getter(P.VAULT_SELECTORS["decimals"])
    transport = RecordingTransport(replay_handler(
        "vault_state", reverting={decimals_call},
    ))
    client = _client_on(transport)
    state = await client.fetch_vault_state(VAULT, network=SEPOLIA)

    assert state.decimals is None
    assert state.share_price_wei is None
    convert = P.VAULT_SELECTORS["convertToAssets"].lower()
    assert all(not d.startswith(convert) for d in transport.calldata())
    assert state.total_assets_wei is not None
    assert state.total_shares_raw is not None


async def test_the_vault_replays_the_capture_and_cross_checks_to_1_302986():
    """The capture's own self-validating cross-check (A22), recomputed here."""
    transport = RecordingTransport(replay_handler("vault_state"))
    client = _client_on(transport)
    state = await client.fetch_vault_state(VAULT, network=SEPOLIA)

    assets = state.total_assets_wei / 10 ** 18
    shares = state.total_shares_raw / 10 ** state.decimals
    price = state.share_price_wei / 10 ** 18
    assert round(assets / shares, 6) == round(price, 6) == 1.302986
    # The two wrong forms, spelled out so the assertion above cannot be
    # mistaken for a tautology: both are plausible and both are wrong.
    assert round(state.total_shares_raw / 10 ** 18) == 21_010_977_789
    assert state.share_price_wei / 10 ** 18 != state.total_assets_wei / (
        state.total_shares_raw or 1)


async def test_the_second_vault_round_is_pinned_to_the_first_rounds_block():
    transport = RecordingTransport(replay_handler("vault_state"))
    client = _client_on(transport)
    await client.fetch_vault_state(VAULT, network=SEPOLIA)

    block = load("vault_state")["block_number"]
    tags = [
        e["params"][1] for e in _entries(transport.requests[1][2])
        if e.get("method") == "eth_call"
    ]
    assert tags and set(tags) == {hex(block)}


async def test_a_dead_second_vault_round_keeps_the_decimals_it_read():
    """Half an answer is better than none, and it is still all ``None`` elsewhere."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] > 1:
            raise httpx.ConnectError("second round down", request=request)
        return replay_handler("vault_state")(request)

    client = _client_on(httpx.MockTransport(handler))
    state = await client.fetch_vault_state(VAULT, network=SEPOLIA)
    assert state is not None
    assert state.decimals == 24
    assert state.total_assets_wei is None
    assert state.share_price_wei is None


# ---------------------------------------------------------------------------
# 8. The dripper
# ---------------------------------------------------------------------------


async def test_the_dripper_round_replays_and_names_the_vault():
    transport = RecordingTransport(replay_handler("dripper_state", "token_state"))
    client = _client_on(transport)
    state = await client.fetch_dripper_state(
        DRIPPER, network=SEPOLIA, token_addr=TOKEN)

    assert state.vault.lower() == VAULT.lower()
    assert state.token.lower() == TOKEN.lower()
    assert state.drip_rate_per_second_wei is not None
    assert state.can_drip in (True, False)


async def test_the_backlog_is_balance_of_the_dripper_on_the_token():
    """It is not a dripper getter, so it must ride against the token contract."""
    transport = RecordingTransport(replay_handler("dripper_state", "token_state"))
    client = _client_on(transport)
    state = await client.fetch_dripper_state(
        DRIPPER, network=SEPOLIA, token_addr=TOKEN)

    wanted = P.encode_balance_of(DRIPPER).lower()
    assert wanted in transport.calldata()
    targets = {
        str(e["params"][0]["to"]).lower()
        for e in _entries(transport.requests[0][2])
        if e.get("method") == "eth_call"
        and str(e["params"][0]["data"]).lower() == wanted
    }
    assert targets == {TOKEN.lower()}
    assert state.balance_wei is not None


async def test_no_token_address_leaves_the_backlog_none_never_zero():
    transport = RecordingTransport(replay_handler("dripper_state"))
    client = _client_on(transport)
    state = await client.fetch_dripper_state(DRIPPER, network=SEPOLIA)
    assert state.balance_wei is None
    assert state.vault is not None


# ---------------------------------------------------------------------------
# 9. The v4 pool
# ---------------------------------------------------------------------------


async def test_pool_slot0_matches_the_captured_expectations():
    transport = RecordingTransport(replay_handler("pool_slot0"))
    client = _client_on(transport)
    state = await client.fetch_pool_slot0(
        POOL_ID, network=SEPOLIA, pool_manager=POOL_MANAGER)

    expected = load("pool_slot0")["expected"]
    assert state.sqrt_price_x96 == expected["sqrt_price_x96"]
    assert state.tick == expected["tick"]
    assert state.lp_fee == expected["lp_fee"]
    assert state.liquidity == expected["liquidity"]
    assert state.pool_id_source == "hook"


async def test_pool_slot0_derives_its_slots_through_surf_v4_not_locally():
    transport = RecordingTransport(replay_handler("pool_slot0"))
    client = _client_on(transport)
    await client.fetch_pool_slot0(
        POOL_ID, network=SEPOLIA, pool_manager=POOL_MANAGER)

    fixture = load("pool_slot0")
    slot0_key, liquidity_key = surf_v4.pool_state_slots(
        POOL_ID, fixture["mapping_slot"])
    assert slot0_key == fixture["slot0_key"]
    assert liquidity_key == fixture["liquidity_key"]
    assert P.encode_extsload(slot0_key).lower() in transport.calldata()
    assert P.encode_extsload(liquidity_key).lower() in transport.calldata()


async def test_an_unread_slot0_is_none_not_a_zero_price():
    """A price of 0 renders as a free token; the pool is real, so ``None``."""
    transport = RecordingTransport(replay_handler(
        "pool_slot0",
        overrides={
            (POOL_MANAGER.lower(),
             P.encode_extsload(load("pool_slot0")["slot0_key"]).lower()): "0x",
        },
    ))
    client = _client_on(transport)
    state = await client.fetch_pool_slot0(
        POOL_ID, network=SEPOLIA, pool_manager=POOL_MANAGER)
    assert state.sqrt_price_x96 is None
    assert state.tick is None
    assert state.liquidity == load("pool_slot0")["expected"]["liquidity"]


async def test_a_malformed_pool_id_never_reaches_the_network():
    client = _raising_client()
    assert await client.fetch_pool_slot0(
        "0xdeadbeef", network=SEPOLIA, pool_manager=POOL_MANAGER) is None


# ---------------------------------------------------------------------------
# 10. Flow logs
# ---------------------------------------------------------------------------


async def test_the_full_window_replays_every_captured_log():
    transport = RecordingTransport(log_handler("flow_logs_full"))
    client = _client_on(transport)
    logs = await client.fetch_flow_logs(
        HOOK, 11_609_600, 11_610_000, network=SEPOLIA)
    assert len(logs) == load("flow_logs_full")["log_count"] == 90
    assert all("blockTimestamp" in log for log in logs), (
        "decode_flow_events reads blockTimestamp; without it every row loses "
        "its age. Measured present on both Sepolia log endpoints."
    )


async def test_flow_events_go_through_wp3s_decoder_unchanged():
    transport = RecordingTransport(log_handler("flow_logs_mixed"))
    client = _client_on(transport)
    rows = await client.fetch_flow_events(
        HOOK, 11_609_700, 11_609_760, network=SEPOLIA)
    expected = P.decode_flow_events(load("flow_logs_mixed")["response"]["result"])
    assert rows == expected
    assert rows, "the mixed window carries a buy and several sells"
    # The representable zero: a buy burns nothing and that is a fact, not a
    # missing read.
    buys = [r for r in rows if r.side == "buy"]
    assert buys and all(r.burned_wei == 0 and r.stakers_wei == 0 for r in buys)


async def test_a_quiet_window_is_empty_and_a_dead_pool_is_none():
    """``[]`` is swept-and-quiet; ``None`` is could-not-look. Never the same."""
    transport = RecordingTransport(log_handler("flow_logs_empty"))
    client = _client_on(transport)
    assert await client.fetch_flow_logs(
        HOOK, 11_605_000, 11_605_100, network=SEPOLIA) == []
    assert await client.fetch_flow_events(
        HOOK, 11_605_000, 11_605_100, network=SEPOLIA) == []

    dead = _offline_client()
    assert await dead.fetch_flow_logs(
        HOOK, 11_605_000, 11_605_100, network=SEPOLIA) is None
    assert await dead.fetch_flow_events(
        HOOK, 11_605_000, 11_605_100, network=SEPOLIA) is None


async def test_a_partial_sweep_is_none_rather_than_a_short_list():
    """A window missing its middle produces a burn total that is simply wrong.

    Per-field degradation is right for getters, where each field stands alone.
    It is wrong for a sum: ``reconcile_counters`` adds these logs up, and a
    short list would publish a confident, wrong number instead of an absent one.
    """
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        if seen["n"] == 1:
            return log_handler("flow_logs_full")(request)
        raise httpx.ConnectError("page two down", request=request)

    client = _client_on(httpx.MockTransport(handler), log_window_blocks=200)
    assert await client.fetch_flow_logs(
        HOOK, 11_609_600, 11_610_000, network=SEPOLIA) is None


async def test_a_page_that_answers_with_no_result_fails_the_whole_sweep():
    """The other half of the partial-sweep rule, and a different branch.

    An endpoint that answers HTTP 200 with ``"result": null`` has not served
    the window — but it has not errored either, so the retry ladder never sees
    it. Returning the pages collected so far would publish a silently short
    log set, and ``reconcile_counters`` sums these.
    """
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        payload = json.loads(request.content)
        if seen["n"] == 1:
            return log_handler("flow_logs_full")(request)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload.get("id"), "result": None})

    client = _client_on(httpx.MockTransport(handler), log_window_blocks=200)
    assert await client.fetch_flow_logs(
        HOOK, 11_609_600, 11_610_000, network=SEPOLIA) is None
    assert seen["n"] >= 2, "the second page was never asked for"


# ---------------------------------------------------------------------------
# eth_getTransactionByHash — the S15 provenance re-fetch
# ---------------------------------------------------------------------------
#
# There is no committed ``eth_getTransactionByHash`` capture (WP1 owns
# fixtures and this method postdates the corpus), so the node shape is built
# from a REAL announce-wallet self-post in ``announce_undiscovered.json``
# rather than invented: its hash, its from, its to and its raw input are the
# mainnet channel's own bytes. Only the JSON-RPC envelope around them is mine.


def _self_post_row() -> dict:
    """The first genuine announce self-post in the committed mainnet corpus."""
    data = load("announce_undiscovered")
    announce = data["announce"].lower()
    for item in data["response"]["items"]:
        frm = (item.get("from") or {}).get("hash", "").lower()
        to = (item.get("to") or {}).get("hash", "").lower()
        if frm == announce and to == announce:
            return item
    raise AssertionError("no self-post in announce_undiscovered.json")


def _node_tx(row: dict | None = None, **overrides: Any) -> dict:
    """That self-post in ``eth_getTransactionByHash`` shape."""
    row = row or _self_post_row()
    tx = {
        "hash": row["hash"],
        "from": (row.get("from") or {}).get("hash"),
        "to": (row.get("to") or {}).get("hash"),
        "input": row["raw_input"],
        "blockNumber": hex(row["block_number"]),
        "value": "0x0",
    }
    tx.update(overrides)
    return tx


def tx_handler(
    result: Any, *, expect_method: str = "eth_getTransactionByHash"
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer any batch with *result* for every entry."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        entries = _entries(payload)
        for entry in entries:
            assert entry.get("method") == expect_method, entry.get("method")
        out = [{"jsonrpc": "2.0", "id": e.get("id"), "result": result}
               for e in entries]
        return httpx.Response(200, json=out if isinstance(payload, list) else out[0])
    return handler


async def test_the_provenance_refetch_returns_the_nodes_own_transaction():
    """S15: the cache says where to look, the chain stays the authority.

    Provenance is re-derived each cycle from a 25-row channel window, and at
    2.55 days/post that window turns over in ~64 days — so a genuine mainnet
    adoption would lapse back to Sepolia two months after it was announced.
    Re-reading the *transaction* fixes that without letting the cache nominate
    anything, which is the line A27 drew.

    The fields are returned undecoded, as the node spells them: WP3 owns the
    provenance predicate and this client does not guess at its contract.
    """
    row = _self_post_row()
    transport = RecordingTransport(tx_handler(_node_tx(row)))
    client = _client_on(transport)
    tx = await client.fetch_transaction(row["hash"], network=MAINNET)

    assert tx is not None
    assert tx["from"].lower() == tx["to"].lower() == load(
        "announce_undiscovered")["announce"].lower()
    assert tx["input"] == row["raw_input"]
    assert tx["hash"] == row["hash"]
    # Exactly one request, and it asked the question we meant to ask.
    assert len(transport.requests) == 1
    entry = _entries(transport.requests[0][2])[0]
    assert entry["method"] == "eth_getTransactionByHash"
    assert entry["params"] == [row["hash"].lower()]


async def test_a_transaction_that_is_not_the_one_we_asked_for_is_refused():
    """A client that returns the wrong transaction must not be believed.

    **This check is WP6's, not WP3's**, and the reason is that only this layer
    can give the right answer. A hash mismatch is a fact about the *endpoint* —
    confused, stale, or hostile — and its correct outcome is ``None``, "we
    could not read". A pure provenance predicate returns a provenance verdict,
    so the loudest thing it could say is "not a self-post", which would report
    a broken endpoint as an attack. The check has to live where ``None`` is
    expressible, and that is here.

    It is also the only layer that knows the question: the pure predicate is
    handed an answer and never sees the hash that was requested.
    """
    row = _self_post_row()
    other = "0x" + "ab" * 32
    transport = RecordingTransport(tx_handler(_node_tx(row, hash=other)))
    client = _client_on(transport)
    assert await client.fetch_transaction(row["hash"], network=MAINNET) is None
    assert transport.requests, "it must actually have asked before refusing"


async def test_a_transaction_with_no_hash_field_cannot_be_identified():
    """Identity unconfirmable is identity refused, not identity assumed."""
    row = _self_post_row()
    tx = _node_tx(row)
    tx.pop("hash")
    client = _client_on(httpx.MockTransport(tx_handler(tx)))
    assert await client.fetch_transaction(row["hash"], network=MAINNET) is None


@pytest.mark.parametrize("result", [None, {}, "", [], "0x", 0])
async def test_an_empty_or_null_transaction_is_a_failed_read(result):
    """A10's sibling: "the call did not fail" is not "the transaction exists".

    ``null`` is what a node returns for an unknown hash **and** for a hash it
    simply does not have — behind, pruned, or answering for the wrong chain.
    One endpoint cannot tell those apart, so this is ``None`` and never a
    provenance answer: reporting it as "not a self-post" would drop an
    adoption that is still perfectly good the moment an RPC has a bad minute.
    """
    row = _self_post_row()
    client = _client_on(httpx.MockTransport(tx_handler(result)))
    assert await client.fetch_transaction(row["hash"], network=MAINNET) is None


async def test_a_contract_creation_keeps_its_null_to_and_is_not_a_failed_read():
    """``to: null`` is a real fact about a real transaction.

    It makes the transaction *not a self-post* — which is a provenance answer,
    and provenance answers are WP3's to give. Swallowing it here as ``None``
    would hide a genuine "this is not what you were told it was" behind "we
    could not read".
    """
    row = _self_post_row()
    client = _client_on(httpx.MockTransport(tx_handler(_node_tx(row, to=None))))
    tx = await client.fetch_transaction(row["hash"], network=MAINNET)
    assert tx is not None
    assert tx["to"] is None
    assert tx["from"] is not None


async def test_a_pending_transaction_is_passed_through_for_wp3_to_judge():
    """``blockNumber: null`` means unmined, and that is not a read failure.

    Passed through deliberately, and **named in WP6's report** rather than
    silently handled: whether an unmined self-post establishes provenance is a
    real question, and WP6's recommendation is that it must not — a transaction
    that never mines is a claim, not a fact. The field is right there in the
    payload so the predicate can require it; this test exists so that decision
    is made by someone rather than defaulted into.
    """
    row = _self_post_row()
    client = _client_on(
        httpx.MockTransport(tx_handler(_node_tx(row, blockNumber=None))))
    tx = await client.fetch_transaction(row["hash"], network=MAINNET)
    assert tx is not None
    assert tx["blockNumber"] is None


@pytest.mark.parametrize(
    ("bad", "why"),
    [
        (None, "not a string"),
        (12345, "not a string"),
        ("", "empty"),
        ("0x", "prefix only"),
        ("0x" + "ab" * 31, "31 bytes — too short"),
        ("0x" + "ab" * 33, "33 bytes — too long"),
        ("0x" + "zz" * 32, "not hex"),
        ("０" * 64, "FULLWIDTH digits — int() takes these, ascii does not"),
        ("0x" + "ab" * 31 + "a​" + "b", "zero-width space"),
        ("../../etc/passwd", "path traversal"),
        ("0x" + "ab" * 32 + "?a=1", "query-string smuggling"),
    ],
)
async def test_a_malformed_hash_never_reaches_a_url_or_a_json_body(bad, why):
    """The hash comes back out of ``~/.maxpane/``, so it is third-party input.

    Same argument that makes a hand-edited discovery payload third-party
    input, and it is validated *before* it can become part of a URL or a
    JSON-RPC body. Proved with the raising transport: a malformed hash costs
    zero round trips, so a corrupted cache cannot even be used to make this
    client talk to an endpoint.
    """
    client = _raising_client()
    assert await client.fetch_transaction(bad, network=MAINNET) is None, why


def test_the_hash_validator_refuses_what_wp3s_address_validator_refuses():
    """Agreement test: one rule, two copies, neither importing the other.

    ``surf_pool4._hex_body`` is private to WP3 and free to be renamed without
    telling anyone, so reaching across the boundary into a ``_`` name is a
    dependency neither side agreed to. Redundancy plus an agreement test is
    the repo's answer when a rule must not diverge and cannot be shared.

    The class both copies exist for: Python's ``int`` accepts every Unicode
    decimal digit that ``ascii`` refuses, so FULLWIDTH digits parse as a hex
    number. WP3 found it producing ``has_pool4_flags() == True`` on a string
    ``checksum_address`` crashed on; here it would have put non-ASCII into a
    URL and a JSON-RPC body wearing a valid shape.
    """
    fullwidth_addr = "０" * 40
    fullwidth_hash = "０" * 64
    # The hazard is real: int() takes both.
    assert int(fullwidth_addr, 16) == 0
    assert int(fullwidth_hash, 16) == 0
    # And both validators refuse them anyway.
    assert P.address_flag_word(fullwidth_addr) is None
    assert C._tx_hash_body(fullwidth_hash) is None
    # Neither accepts the other's length, so a hash can never be read as an
    # address (WP3's "'Long' is not padding") nor an address as a hash.
    assert C._tx_hash_body("0x" + "ab" * 20) is None
    assert P.address_flag_word("0x" + "ab" * 32) is None


async def test_the_refetch_normalises_the_hash_it_sends():
    """Mixed case in, one canonical lowercase question out."""
    row = _self_post_row()
    shouty = "0x" + row["hash"][2:].upper()
    transport = RecordingTransport(tx_handler(_node_tx(row)))
    client = _client_on(transport)
    tx = await client.fetch_transaction(shouty, network=MAINNET)
    assert tx is not None
    entry = _entries(transport.requests[0][2])[0]
    assert entry["params"] == [row["hash"].lower()]


async def test_a_mainnet_hash_goes_to_mainnet_and_a_sepolia_hash_to_sepolia():
    """Four-pool separation extends to the provenance re-fetch.

    ``eth_getTransactionByHash`` is a state call, so it rides the state pool —
    and a mainnet hash asked on Sepolia endpoints would answer ``null``, which
    this client reads as a failed read. That failure mode is silent by
    construction, which is why the separation is asserted on the URLs the
    transport was actually handed rather than trusted.
    """
    row = _self_post_row()

    mainnet = RecordingTransport(tx_handler(_node_tx(row)))
    await _client_on(mainnet).fetch_transaction(row["hash"], network=MAINNET)
    _assert_reached(mainnet, MAINNET, "state")

    sepolia = RecordingTransport(tx_handler(_node_tx(row)))
    await _client_on(sepolia).fetch_transaction(row["hash"], network=SEPOLIA)
    _assert_reached(sepolia, SEPOLIA, "state")

    # Stated twice, cheaply, because the wrong-chain failure is silent: a
    # mainnet hash asked on Sepolia comes back ``null``, which reads as a
    # failed read rather than as a routing bug.
    assert all("sepolia" in u.lower() for u in sepolia.urls())
    assert all("sepolia" not in u.lower() for u in mainnet.urls())


async def test_the_refetch_on_an_unknown_network_reaches_no_endpoint():
    transport = RecordingTransport(tx_handler(_node_tx()))
    client = _client_on(transport)
    assert await client.fetch_transaction(
        _self_post_row()["hash"], network="BASE") is None
    assert transport.requests == []


async def test_an_endpoint_limitation_rotates_then_the_refetch_gives_up():
    """Classified on message text, like everything else here."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        payload = json.loads(request.content)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": _entries(payload)[0].get("id"),
            "error": {"code": -32005, "message": "rate limit exceeded"}})

    client = _client_on(httpx.MockTransport(handler))
    assert await client.fetch_transaction(
        _self_post_row()["hash"], network=MAINNET) is None
    # It rotated rather than giving up on the first host.
    assert len(set(seen)) == len(C.MAINNET_STATE_RPCS)


# ---------------------------------------------------------------------------
# 14. Mainnet, 2026-09-02 — the vault walk, the Distributor, the docs source
# ---------------------------------------------------------------------------
#
# Every mainnet value below was read from the chain by this package on
# 2026-09-02 (scratchpad/wp6/wp6_probe_mainnet_walk2.py), not copied from
# ``docs/imd_pool4_mainnet.md``. Where the two agree it is because the chain
# said so twice.

HOOK_MAINNET = "0xc6c965bd164c483e87d0b550671798e9a3602840"
DISTRIBUTOR = "0x9046739E1535B40EfBe6AB3f45d0024b690eCA30"
DRIPPER_MAINNET = "0xe6D3De6daEAf327fCA42745f1998FcD989e00884"
VAULT_MAINNET = "0x9efa934d9fad4ae28c998a40195646b965a97247"
DRIPPER_SEPOLIA = "0x4dBE172254033aAC3a3374Fb10b422605B0B449B"


def _word(value: int) -> str:
    return "0x" + format(value, "064x")


def _addr_word(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:].lower()


def walk_handler(
    graph: dict[str, dict[str, str | None]]
) -> Callable[[httpx.Request], httpx.Response]:
    """A little chain: ``{address: {"vault": addr|None, "dripper": addr|None}}``.

    A getter with no entry reverts, which is what a contract that does not
    implement it really does.
    """
    sel_vault = P.encode_getter(P.selector("vault()")).lower()
    sel_dripper = P.encode_getter(P.selector("dripper()")).lower()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        out = []
        for entry in _entries(payload):
            params = entry["params"][0]
            node = graph.get(str(params["to"]).lower(), {})
            data = str(params["data"]).lower()
            key = {sel_vault: "vault", sel_dripper: "dripper"}.get(data)
            target = node.get(key) if key else None
            if target is None:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "error": {"code": 3, "message": "execution reverted"}})
            else:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "result": _addr_word(target)})
        return httpx.Response(200, json=out)

    return handler


async def test_the_sepolia_shape_stops_at_one_hop():
    """``rewardsRecipient()`` IS the dripper there, and it answers ``vault()``."""
    transport = RecordingTransport(walk_handler({
        DRIPPER_SEPOLIA.lower(): {"vault": VAULT, "dripper": None},
    }))
    client = _client_on(transport)
    walked = await client.resolve_vault_path(DRIPPER_SEPOLIA, network=SEPOLIA)

    assert walked["vault"].lower() == VAULT.lower()
    assert walked["dripper"].lower() == DRIPPER_SEPOLIA.lower()
    assert [a.lower() for a in walked["path"]] == [DRIPPER_SEPOLIA.lower()]
    assert len(transport.requests) == 1


async def test_the_mainnet_shape_walks_one_hop_further_without_being_told():
    """The break A3 could not have anticipated, and the fix that adapts.

    Mainnet inserted a Reward Distributor between the hook and the Dripper, so
    the old two-hop path called ``vault()`` on the Distributor — which has no
    such method — and vault and dripper reads failed outright. Confirmed
    against the live chain: ``distributor.vault()`` reverts,
    ``distributor.dripper()`` returns ``0xe6D3…0884``, and that dripper's
    ``vault()`` returns the sIMD vault ``0x9efa…7247``.
    """
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DRIPPER_MAINNET},
        DRIPPER_MAINNET.lower(): {"vault": VAULT_MAINNET, "dripper": None},
    }))
    client = _client_on(transport)
    walked = await client.resolve_vault_path(DISTRIBUTOR, network=MAINNET)

    assert walked["vault"].lower() == VAULT_MAINNET.lower()
    assert walked["dripper"].lower() == DRIPPER_MAINNET.lower()
    assert [a.lower() for a in walked["path"]] == [
        DISTRIBUTOR.lower(), DRIPPER_MAINNET.lower()]
    assert len(transport.requests) == 2


async def test_neither_hop_count_is_hardcoded_because_both_are_live():
    """The Distributor exists on mainnet and not on Sepolia, simultaneously.

    So neither shape is "the" path: a hardcoded three would break Sepolia
    exactly as the hardcoded two broke mainnet. This drives the *same* client
    over both graphs and asserts it spent a different number of round trips on
    each — which a fixed hop count cannot do in one direction or the other.
    """
    sep = RecordingTransport(walk_handler({
        DRIPPER_SEPOLIA.lower(): {"vault": VAULT, "dripper": None}}))
    main = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DRIPPER_MAINNET},
        DRIPPER_MAINNET.lower(): {"vault": VAULT_MAINNET, "dripper": None}}))

    a = await _client_on(sep).resolve_vault_path(DRIPPER_SEPOLIA, network=SEPOLIA)
    b = await _client_on(main).resolve_vault_path(DISTRIBUTOR, network=MAINNET)

    assert a["vault"] and b["vault"]
    assert len(sep.requests) == 1 and len(main.requests) == 2
    assert len(a["path"]) == 1 and len(b["path"]) == 2


async def test_each_hop_asks_both_questions_in_one_batch():
    """``vault()`` and ``dripper()`` together — one round trip per hop, not two."""
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DRIPPER_MAINNET},
        DRIPPER_MAINNET.lower(): {"vault": VAULT_MAINNET, "dripper": None}}))
    await _client_on(transport).resolve_vault_path(DISTRIBUTOR, network=MAINNET)
    for (_u, _m, payload) in transport.requests:
        datas = [str(e["params"][0]["data"]).lower() for e in _entries(payload)]
        assert sorted(datas) == sorted([
            P.encode_getter(P.selector("vault()")).lower(),
            P.encode_getter(P.selector("dripper()")).lower()])


async def test_a_self_referential_dripper_stops_immediately():
    """The cycle check earns its keep here, separately from the hop cap.

    A contract whose ``dripper()`` returns itself would otherwise cost the
    whole hop budget on every single refresh, forever.
    """
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DISTRIBUTOR}}))
    walked = await _client_on(transport).resolve_vault_path(
        DISTRIBUTOR, network=MAINNET)
    assert walked["vault"] is None
    assert len(walked["path"]) == 1
    assert len(transport.requests) == 1


async def test_a_two_node_cycle_stops_at_the_revisit():
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DRIPPER_MAINNET},
        DRIPPER_MAINNET.lower(): {"vault": None, "dripper": DISTRIBUTOR}}))
    walked = await _client_on(transport).resolve_vault_path(
        DISTRIBUTOR, network=MAINNET)
    assert walked["vault"] is None
    assert [a.lower() for a in walked["path"]] == [
        DISTRIBUTOR.lower(), DRIPPER_MAINNET.lower()]
    assert len(transport.requests) == 2


async def test_a_chain_longer_than_the_cap_is_abandoned():
    """An unbounded follow is its own hazard; the cap is what bounds it."""
    links = ["0x%040x" % (i + 1) for i in range(_LONG_CHAIN)]
    graph = {
        links[i].lower(): {"vault": None, "dripper": links[i + 1]}
        for i in range(len(links) - 1)
    }
    graph[links[-1].lower()] = {"vault": None, "dripper": None}
    transport = RecordingTransport(walk_handler(graph))
    walked = await _client_on(transport).resolve_vault_path(
        links[0], network=MAINNET)
    assert walked["vault"] is None
    assert len(transport.requests) == C._MAX_VAULT_HOPS
    assert len(walked["path"]) == C._MAX_VAULT_HOPS


async def test_a_zero_address_dripper_is_not_a_hop():
    """``0x000…0`` means "not set", and calling it would only return ``"0x"``."""
    zero = "0x" + "0" * 40
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": zero}}))
    walked = await _client_on(transport).resolve_vault_path(
        DISTRIBUTOR, network=MAINNET)
    assert walked["vault"] is None
    assert len(walked["path"]) == 1
    assert len(transport.requests) == 1


async def test_a_walk_that_found_nothing_is_not_a_walk_that_could_not_look():
    """Two different answers, and this is one of the few places both fit.

    A chain that was read and simply does not lead to a vault returns its dict
    with ``vault: None``. A chain that could not be read at all returns
    ``None``. Collapsing them would make an RPC outage indistinguishable from
    a deployment whose dripper is unset.
    """
    read_it = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": None}}))
    walked = await _client_on(read_it).resolve_vault_path(
        DISTRIBUTOR, network=MAINNET)
    assert walked is not None and walked["vault"] is None

    assert await _offline_client().resolve_vault_path(
        DISTRIBUTOR, network=MAINNET) is None


@pytest.mark.parametrize(
    "bad", [None, 12345, "", "0x", "not-an-address", "0x" + "ab" * 32, "０" * 40])
async def test_a_malformed_recipient_never_reaches_an_endpoint(bad):
    assert await _raising_client().resolve_vault_path(bad, network=MAINNET) is None


async def test_the_walk_keeps_to_its_own_networks_pool():
    transport = RecordingTransport(walk_handler({
        DISTRIBUTOR.lower(): {"vault": None, "dripper": DRIPPER_MAINNET},
        DRIPPER_MAINNET.lower(): {"vault": VAULT_MAINNET, "dripper": None}}))
    await _client_on(transport).resolve_vault_path(DISTRIBUTOR, network=MAINNET)
    _assert_reached(transport, MAINNET, "state")


# ---------------------------------------------------------------------------
# The Reward Distributor
# ---------------------------------------------------------------------------

#: Live mainnet reads, 2026-09-02. The chain and the docs agree exactly here,
#: which is worth stating because it is not true of every number in this build.
_DISTRIBUTOR_LIVE = {
    "stakingBps": 3000,
    "nftBps": 3000,
    "stakingEarned": 3148978964642206159,
    "bondingEarned": 4198638619522941546,
    "nftEarned": 3148978964642206163,
    "heldBonding": 4198638619522941546,
    "heldNft": 3148978964642206163,
}


def distributor_handler(
    values: dict[str, int] | None = None,
    *,
    reverting: set[str] = frozenset(),
) -> Callable[[httpx.Request], httpx.Response]:
    values = _DISTRIBUTOR_LIVE if values is None else values
    table = {
        P.encode_getter(P.selector(sig)).lower(): name
        for name, sig in C.DISTRIBUTOR_SIGNATURES.items()
    }
    addrs = {"dripper": DRIPPER_MAINNET, "asset": TOKEN, "owner": HOOK_MAINNET}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        out = []
        for entry in _entries(payload):
            if entry.get("method") == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "result": hex(25_883_917)})
                continue
            name = table.get(str(entry["params"][0]["data"]).lower())
            if name is None or name in reverting:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "error": {"code": 3, "message": "execution reverted"}})
            elif name in addrs:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "result": _addr_word(addrs[name])})
            else:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "result": _word(values[name])})
        return httpx.Response(200, json=out)

    return handler


async def test_the_distributor_reads_its_recovered_interface():
    transport = RecordingTransport(distributor_handler())
    state = await _client_on(transport).fetch_distributor_state(
        DISTRIBUTOR, network=MAINNET)

    assert state["stakingBps"] == 3000
    assert state["nftBps"] == 3000
    assert state["dripper"].lower() == DRIPPER_MAINNET.lower()
    assert state["asset"].lower() == TOKEN.lower()
    assert state["block_number"] == 25_883_917
    # The counters the doc quotes, to the wei.
    assert state["bondingEarned"] == state["heldBonding"] == 4198638619522941546
    assert state["nftEarned"] == state["heldNft"] == 3148978964642206163


def test_bonding_has_no_getter_and_none_is_invented():
    """It is the remainder, and the client refuses to make that look like a read.

    ``10000 - stakingBps - nftBps`` = 4000, measured. Returning a
    ``bondingBps`` key from a method whose every other key is a chain read
    would make a derived number indistinguishable from a read one — the exact
    habit "read values live, never hardcode a documented one" exists to break.
    Where the derivation lands is WP0's decision, not this client's.
    """
    assert "bondingBps" not in C.DISTRIBUTOR_SIGNATURES
    assert not any("bonding" in n.lower() and n.endswith("Bps")
                   for n in C.DISTRIBUTOR_SIGNATURES)
    # The two halves it IS derived from are both read.
    assert "stakingBps" in C.DISTRIBUTOR_SIGNATURES
    assert "nftBps" in C.DISTRIBUTOR_SIGNATURES
    assert 10000 - _DISTRIBUTOR_LIVE["stakingBps"] - _DISTRIBUTOR_LIVE["nftBps"] == 4000


def test_no_state_changing_selector_is_in_the_distributor_interface():
    """The recovered interface has three; this repo has no signer.

    Absent deliberately rather than merely unused: a selector table is where
    someone reaches when they want to "just call it once".
    """
    for banned in ("distribute()", "setDripper(address)",
                   "emergencyWithdraw(address)"):
        assert banned not in C.DISTRIBUTOR_SIGNATURES.values()
    code = _code_only(Path(C.__file__).read_text(encoding="utf-8"))
    for banned in ("distribute", "setDripper", "emergencyWithdraw"):
        assert banned not in code


async def test_the_distributor_degrades_field_by_field():
    transport = RecordingTransport(
        distributor_handler(reverting={"nftBps", "heldNft"}))
    state = await _client_on(transport).fetch_distributor_state(
        DISTRIBUTOR, network=MAINNET)
    assert state["nftBps"] is None
    assert state["heldNft"] is None
    assert state["stakingBps"] == 3000
    assert state["dripper"] is not None


async def test_a_distributor_outage_is_none_and_reaches_only_mainnet():
    assert await _offline_client().fetch_distributor_state(
        DISTRIBUTOR, network=MAINNET) is None
    transport = RecordingTransport(distributor_handler())
    await _client_on(transport).fetch_distributor_state(
        DISTRIBUTOR, network=MAINNET)
    _assert_reached(transport, MAINNET, "state")


# ---------------------------------------------------------------------------
# The docs page — a widened trust surface, kept small and visible
# ---------------------------------------------------------------------------

_DOCS_HTML = (
    "<html><body><h1>pool4</h1>"
    "<p>hook <code>0xc6c965bd164c483e87d0b550671798e9a3602840</code></p>"
    "<p>vault <code>0x9efa934d9fad4ae28c998a40195646b965a97247</code></p>"
    "</body></html>"
)


def docs_handler(
    body: bytes = _DOCS_HTML.encode(),
    status: int = 200,
    headers: dict | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers=headers or {})
    return handler


async def test_the_docs_page_comes_back_raw():
    transport = RecordingTransport(docs_handler())
    text = await _client_on(transport).fetch_docs_page()
    assert text == _DOCS_HTML
    assert transport.requests[0][1] == "GET"
    assert transport.urls() == [C.DOCS_URL]


async def test_the_docs_text_is_not_normalised_because_s16_depends_on_it():
    """S16: ``ADDRESS_RE`` must see the bytes the server sent.

    ``0x`` + U+202E + 40 hex digits renders as one thing and *is* another, and
    the regex's leading anchor is what refuses it. Strip, case-fold, HTML
    unescape or NFKC anywhere upstream of extraction and that control is
    disarmed two modules away, silently. So the page round-trips exactly —
    including the bidi override, the entity, the leading whitespace and the
    mixed case.
    """
    hostile = (
        "  \n<p>&#48;x hook: 0x\u202ec6c965bd164c483e87d0b550671798e9a3602840</p>\n"
        "<P>MiXeD 0xC6C965BD164C483E87D0B550671798E9A3602840</P>  \n"
    )
    client = _client_on(httpx.MockTransport(docs_handler(hostile.encode())))
    text = await client.fetch_docs_page()
    assert text == hostile
    assert "\u202e" in text
    assert "&#48;" in text
    assert text != text.strip()
    assert any(c.isupper() for c in text)


async def test_only_the_allowlisted_docs_host_is_fetched():
    """The operator widened the trust surface to one page. This keeps it one."""
    client = _raising_client()
    for url in ("https://evil.example/docs",
                "https://pool4.imd.fun.evil.example/docs",
                "http://localhost:8545/docs",
                "file:///etc/passwd"):
        assert await client.fetch_docs_page(url) is None


async def test_a_redirect_is_never_followed():
    transport = RecordingTransport(docs_handler(
        b"", status=302, headers={"location": "https://evil.example/docs"}))
    client = _client_on(transport)
    assert await client.fetch_docs_page() is None
    assert len(transport.requests) == 1, "it followed the redirect"
    assert "evil.example" not in " ".join(transport.urls())


async def test_an_oversized_page_is_refused_by_the_header_and_by_the_bytes():
    """The header is advisory; the byte count is the gate.

    A server that lies about ``content-length`` is exactly the server a cap
    exists for, so both are checked and the second one is the one that binds.
    """
    honest = RecordingTransport(docs_handler(
        b"x", headers={"content-length": str(C._DOCS_MAX_BYTES + 1)}))
    assert await _client_on(honest).fetch_docs_page() is None

    liar = RecordingTransport(docs_handler(
        b"x" * (C._DOCS_MAX_BYTES + 1), headers={"content-length": "3"}))
    assert await _client_on(liar).fetch_docs_page() is None

    fine = RecordingTransport(docs_handler(
        _DOCS_HTML.encode(), headers={"content-length": "not a number"}))
    assert await _client_on(fine).fetch_docs_page() == _DOCS_HTML


@pytest.mark.parametrize("status", [403, 404, 500, 521])
async def test_a_broken_docs_server_is_none_never_no_candidate(status):
    """A failed fetch is "we could not read", never "there is no candidate".

    Same distinction as everywhere else here, and it matters more on this path
    than most: "no candidate" would silently keep the view on Sepolia while
    mainnet is live, which is the exact state this source exists to end.
    """
    client = _client_on(httpx.MockTransport(docs_handler(b"", status=status)))
    assert await client.fetch_docs_page() is None


async def test_an_empty_docs_body_is_a_failed_read():
    client = _client_on(httpx.MockTransport(docs_handler(b"")))
    assert await client.fetch_docs_page() is None


async def test_a_docs_outage_is_none():
    assert await _offline_client().fetch_docs_page() is None


def test_the_docs_source_is_beside_the_four_pools_and_not_in_them():
    """Stated as a test because "which shelf" is a claim about trust, not filing.

    An RPC answers with consensus data; this is one operator's mutable HTML.
    Shelving them together would read as equal standing, and the only
    mitigation this source has is that its weakness stays visible. It is also
    not chain-scoped — one page describes the deployment whatever network the
    view is showing — so a pool entry would imply a Sepolia docs page that
    does not exist.
    """
    client = _raising_client()
    for network in POOL4_NETWORKS:
        for url in client.state_endpoints(network) + client.log_endpoints(network):
            assert "imd.fun" not in url
    assert C.DOCS_URL.startswith("https://")
    from urllib.parse import urlparse as _u
    assert (_u(C.DOCS_URL).hostname or "") in C._DOCS_HOSTS
    # And it takes no network argument, because it has no network.
    assert "network" not in inspect.signature(
        Pool4Client.fetch_docs_page).parameters


# ---------------------------------------------------------------------------
# The two mainnet hook getters
# ---------------------------------------------------------------------------


def test_wp3s_hook_table_carries_the_two_mainnet_getters():
    """Agreement test, and it replaces a second copy a mutation found dead.

    This module briefly carried its own ``MAINNET_HOOK_SIGNATURES`` and
    appended it to the hook round. Dropping that block changed nothing — WP3
    had landed both selectors in ``HOOK_SELECTORS`` and the round was already
    getting them — so the local table was a second spelling of somebody else's
    constant, which is the divergence "reuse before you build" exists to
    prevent. It is gone; this is what stands in its place.

    Independent confirmation of the recovery, too: these selectors are in no
    public signature database, and ``keccak`` reproduces both from the docs'
    own vocabulary exactly.
    """
    assert P.selector("capDecayTokensPerDay()") == "0x55e62941"
    assert P.selector("inventoryCap()") == "0xdb445ee8"
    for name in C.MAINNET_HOOK_GETTERS:
        assert name in P.HOOK_SELECTORS, f"WP3's hook table lost {name}"
    assert P.HOOK_SELECTORS["capDecayTokensPerDay"] == "0x55e62941"
    assert P.HOOK_SELECTORS["inventoryCap"] == "0xdb445ee8"

    # No selector literal is pasted into this module: they are computed, in
    # WP3's table, from the signature strings.
    code = _code_only(Path(C.__file__).read_text(encoding="utf-8"))
    for pasted in ("0x55e62941", "0xdb445ee8"):
        assert pasted not in code, "selector pasted rather than computed"


def test_both_new_getters_answer_on_sepolia_too_so_the_premise_was_wrong():
    """**Measured, and it refutes the task's premise.**

    The two getters were described as mainnet-only, existing on no Sepolia
    hook. Probed against the live launch-3 Sepolia hook on 2026-09-02, both
    answer::

        capDecayTokensPerDay()  mainnet 1000e18 (1,000 IMD/day)
                                sepolia 2**128-1  (uint128 max — no decay)
        inventoryCap()          mainnet 5487.3465e18, 12 wei under tokensInPool
                                sepolia 472,569,750.77e18, EQUAL to tokensInPool

    Control, same probe: ``vault()`` and a fabricated selector both revert on
    both hooks, so the two really are implemented rather than swallowed by a
    fallback.

    This is recorded because it changes how the degradation test must be
    built. "Point it at Sepolia and watch the fields go ``None``" would have
    passed for the wrong reason — Sepolia answers — and the guard would have
    been protecting nothing. The absence case is therefore driven with a
    getter made to revert, which is what a differently-built future hook
    actually looks like.
    """
    assert C.MAINNET_HOOK_GETTERS == ("capDecayTokensPerDay", "inventoryCap")
    assert 2 ** 128 - 1 == 340282366920938463463374607431768211455


async def test_a_hook_without_the_new_getters_loses_two_fields_not_the_round():
    """The absence direction, driven by a revert rather than by a chain."""
    dead = {P.encode_getter(P.HOOK_SELECTORS[name])
            for name in C.MAINNET_HOOK_GETTERS}
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", reverting=dead))
    state = await _client_on(transport).fetch_hook_state(HOOK, network=SEPOLIA)

    assert state is not None
    assert state.cap_decay_tokens_per_day_wei is None
    assert state.inventory_cap_wei is None
    assert state.tokens_in_pool_wei is not None
    assert state.token is not None
    assert state.total_burned_wei is not None


async def test_a_hook_with_the_new_getters_carries_both_values():
    """The presence direction, at the live mainnet numbers."""
    cap_decay, inventory = 1000 * 10 ** 18, 5487346496874821818834
    overrides = {
        (HOOK.lower(), P.encode_getter(P.HOOK_SELECTORS[name]).lower()): _word(v)
        for name, v in (("capDecayTokensPerDay", cap_decay),
                        ("inventoryCap", inventory))
    }
    transport = RecordingTransport(
        replay_handler("hook_state_healthy", overrides=overrides))
    state = await _client_on(transport).fetch_hook_state(HOOK, network=MAINNET)

    assert state.cap_decay_tokens_per_day_wei == cap_decay
    assert state.inventory_cap_wei == inventory


# ---------------------------------------------------------------------------
# 15. Candidate answers — evidence for WP3's ranking, never a verdict
# ---------------------------------------------------------------------------


async def test_candidate_answers_are_shaped_for_wp3s_ranking():
    """The ``answers_by_addr`` input ``ranked_discovery`` declares.

    It exists so adjudication happens once, in the layer that owns it. Before
    it, a consumer that needed ``ranked_discovery`` could not reach the raw
    answers and had to re-derive ranking for itself — two copies of one rule.
    """
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    answers = await _client_on(transport).fetch_candidate_answers(
        [HOOK], network=SEPOLIA)

    assert set(answers) == {P.checksum_address(HOOK)}
    entry = answers[P.checksum_address(HOOK)]
    # Exactly the evidence a fingerprint needs, and every gate name is WP3's.
    assert set(entry) <= set(P.HOOK_SELECTORS)
    for gate in ("token", "rewardShareBps", "BPS_DENOMINATOR",
                 "burnSink", "poolManager"):
        assert P.answered(entry[gate])
    # And it feeds WP3's pure function without translation.
    state, _detail = P.fingerprint_verdict(HOOK, entry, TOKEN)
    assert state == _ADOPTED


async def test_both_paths_reach_the_same_verdict_for_the_same_address():
    """The agreement test, and the reason the fetch is shared code.

    ``verify_hook`` and ``fetch_candidate_answers`` must gather *identical*
    evidence, or the two paths can disagree about one address — which is the
    divergence the new method exists to remove, reappearing one layer down.
    They call one private round for exactly that reason; this asserts the
    property rather than the implementation, so hoisting it differently later
    still has to keep it true.
    """
    for fixture_overrides, addr, token in (
        ({}, HOOK, TOKEN),
        # a contract that answers nothing: rejected, naming the same gate
        ({(HOOK.lower(), P.encode_getter(P.HOOK_SELECTORS[g]).lower()): "0x"
          for g in ("token", "rewardShareBps", "BPS_DENOMINATOR",
                    "burnSink", "poolManager", "getHookPermissions")},
         HOOK, TOKEN),
        # right shape, stranger's token
        ({(HOOK.lower(), P.encode_getter(P.HOOK_SELECTORS["token"]).lower()):
          "0x" + "0" * 24 + "5afe" + "0" * 36}, HOOK, TOKEN),
    ):
        via_verify = await _client_on(httpx.MockTransport(
            replay_handler("hook_state_healthy", overrides=fixture_overrides)
        )).verify_hook(addr, network=SEPOLIA, expected_token=token)
        answers = await _client_on(httpx.MockTransport(
            replay_handler("hook_state_healthy", overrides=fixture_overrides)
        )).fetch_candidate_answers([addr], network=SEPOLIA)

        entry = (answers or {}).get(P.checksum_address(addr), {})
        state, detail = P.fingerprint_verdict(addr, entry, token)
        assert (state, detail) == (via_verify.state, via_verify.detail), (
            "the two paths disagree about one address"
        )


async def test_the_permissions_omission_rule_is_the_same_on_both_paths():
    """A silent ``getHookPermissions`` must fall through, not reject (A8).

    If only one path applied the rule, an address would be adopted through
    ``verify_hook`` and rejected through the ranking path, or the reverse.
    """
    perms = P.encode_getter(P.HOOK_SELECTORS["getHookPermissions"]).lower()
    overrides = {(HOOK.lower(), perms): "0x"}
    answers = await _client_on(httpx.MockTransport(
        replay_handler("hook_state_healthy", overrides=overrides)
    )).fetch_candidate_answers([HOOK], network=SEPOLIA)
    entry = answers[P.checksum_address(HOOK)]
    assert "getHookPermissions" not in entry
    assert P.fingerprint_verdict(HOOK, entry, TOKEN)[0] == _ADOPTED


async def test_an_unflagged_candidate_gets_no_round_trip_and_no_entry():
    """The map cannot be used to adjudicate an address that failed the flags.

    The arithmetic gate runs before the network here exactly as it does in
    ``verify_hook``, so a self-post or a docs page naming twenty decoys costs
    zero ``eth_call``s — and, more importantly, the returned map has no entry a
    consumer could feed to a fingerprint.
    """
    decoys = [load("announce_adversarial_flag_mismatch")["attacker_addresses"][
        "candidate"], "0x" + "11" * 20, "not-an-address", None]
    answers = await _raising_client().fetch_candidate_answers(
        decoys, network=MAINNET)
    assert answers == {}


async def test_the_candidate_sweep_is_capped_because_both_sources_are_writable():
    """A ``0x2840`` address mines in ~20,000 tries: 500 of them is seconds.

    Without a cap one edited docs page turns a refresh into 500 getter rounds —
    an RPC amplifier built out of the filter meant to prevent one.
    """
    many = [
        P.checksum_address("0x" + format(i, "036x") + "2840")
        for i in range(1, 41)
    ]
    many = [a for a in many if a and P.has_pool4_flags(a)]
    assert len(many) > C._MAX_CANDIDATE_ROUNDS, "the fixture must exceed the cap"

    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    await _client_on(transport).fetch_candidate_answers(many, network=MAINNET)
    assert len(transport.requests) == C._MAX_CANDIDATE_ROUNDS


async def test_nothing_worth_asking_is_empty_and_a_dead_pool_is_none():
    assert await _raising_client().fetch_candidate_answers(
        [], network=SEPOLIA) == {}
    assert await _raising_client().fetch_candidate_answers(
        None, network=SEPOLIA) == {}
    assert await _offline_client().fetch_candidate_answers(
        [HOOK], network=SEPOLIA) is None


async def test_candidate_answers_keep_to_their_networks_state_pool():
    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    await _client_on(transport).fetch_candidate_answers([HOOK], network=SEPOLIA)
    _assert_reached(transport, SEPOLIA, "state")


def test_the_client_never_adjudicates_a_candidate_itself():
    """Exposing evidence must not become exposing a verdict.

    Raw answers *look* adoptable, and the failure mode is a future consumer —
    or this module — writing ``if answers["token"] == IMD: adopt``. That is
    A27's "the fingerprint is not authority" one layer over. The verdict has
    exactly one home, and this scan says so structurally: the only place a
    token answer is compared to an expected token is inside WP3's
    ``fingerprint_verdict``, which this module calls and does not reimplement.
    """
    code = _code_only(Path(C.__file__).read_text(encoding="utf-8"))
    for adjudication in ("_same_addr", "POOL4_REQUIRED_FLAGS",
                         "expected_token ==", "== expected_token",
                         "HOOK_FLAG_", "_STATE_REJECTED"):
        assert adjudication not in code, (
            f"{adjudication} in the client: adjudication has one home"
        )
    assert "fingerprint_verdict" in code
    # …and the one gate the client DOES apply is the cheap arithmetic filter,
    # which narrows and never adopts.
    assert "has_pool4_flags" in code


def test_verify_hooks_signature_survived_the_new_method():
    """The tripwire did its job: it forced the conversation, not a silent edit.

    ``verify_hook(..., return_answers=True)`` was the other shape on offer. It
    would have made one name mean two return types, and it would have tripped
    this assertion for a reason that has nothing to do with provenance —
    training the next reader to edit the tripwire rather than think. A separate
    method leaves the pinned property untouched.
    """
    assert list(inspect.signature(Pool4Client.verify_hook).parameters) == [
        "self", "addr", "network", "expected_token"]
    assert "return_answers" not in inspect.signature(
        Pool4Client.verify_hook).parameters
    # The new method is equally provenance-blind: bare addresses, no rows, no
    # announce address, no transaction hash.
    params = list(inspect.signature(Pool4Client.fetch_candidate_answers).parameters)
    assert params == ["self", "addrs", "network"]


# ---------------------------------------------------------------------------
# 11. The livelock
# ---------------------------------------------------------------------------


class _SuggestingProvider:
    """A provider whose "suggested range" decrements one block per round trip.

    This is the real failure CLAUDE.md's hazard table names. A client that
    follows the suggestion verbatim converges on a one-block window one block
    at a time and never terminates.
    """

    def __init__(self) -> None:
        self.suggested = 0xB12790
        self.asked: list[tuple[int, int]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        self.asked.append((int(flt["fromBlock"], 16), int(flt["toBlock"], 16)))
        self.suggested -= 1
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload.get("id"),
            "error": {
                "code": -32602,
                "message": (
                    "eth_getLogs is limited to 0 - 50 blocks range, "
                    f"suggested toBlock {hex(self.suggested)}"
                ),
            },
        })


async def test_a_suggested_retry_range_is_never_followed():
    provider = _SuggestingProvider()
    client = _client_on(httpx.MockTransport(provider))
    result = await client.fetch_flow_logs(
        HOOK, 11_609_600, 11_610_000, network=SEPOLIA)

    assert result is None, "an unservable window is a failed read"
    assert provider.asked, "the client never asked at all"
    # Bounded: shrinks are capped, so the request count cannot run away.
    assert len(provider.asked) <= 64, (
        f"{len(provider.asked)} round trips — this is the livelock"
    )
    # And no request followed a suggestion: every toBlock the client asked for
    # is one it computed itself.
    suggested = {0xB12790 - i for i in range(len(provider.asked) + 2)}
    followed = [pair for pair in provider.asked[1:] if pair[1] in suggested]
    assert not followed, f"followed a provider's suggested range: {followed}"


async def test_the_window_halves_and_then_succeeds():
    """The recoverable half of the same error class: halve, bounded, and page."""
    cap = 700
    spans: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        span = hi - lo + 1
        spans.append(span)
        if span > cap:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload.get("id"),
                "error": {"code": -32602,
                          "message": f"eth_getLogs is limited to 0 - {cap} blocks"},
            })
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload.get("id"), "result": []})

    client = _client_on(httpx.MockTransport(handler))
    result = await client.fetch_flow_logs(
        HOOK, 11_000_000, 11_002_399, network=SEPOLIA)

    assert result == []
    # 2400 -> 1200 -> 600: halvings of our own window, never the provider's
    # numbers, and each attempt starts the sweep over.
    assert spans[0] == C.LOG_WINDOW_BLOCKS
    assert spans[1] == C.LOG_WINDOW_BLOCKS // 2
    assert spans[2] == C.LOG_WINDOW_BLOCKS // 4
    assert all(s <= cap for s in spans[2:])


async def test_the_shrink_ladder_stops_at_the_floor():
    """A provider capping below ``_LOG_MIN_WINDOW`` is abandoned, not chased.

    1rpc's live 50-block cap is exactly this shape. It is why 1rpc is not in
    the log pool at all — and why, if it ever were, the client would give up
    rather than issue thousands of 50-block pages.
    """
    asked: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        asked.append(int(flt["toBlock"], 16) - int(flt["fromBlock"], 16) + 1)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload.get("id"),
            "error": {"code": -32602,
                      "message": "eth_getLogs is limited to 0 - 50 blocks range"},
        })

    # 600 rather than the default 2400 on purpose: from 2400 the three
    # permitted shrinks land exactly on 300, so the floor is never reached and
    # a mutation that lowered it to one block would change nothing. From 600
    # the ladder would run 600 -> 300 -> 150 -> 75 without the floor, so this
    # is the window at which the constant is load-bearing.
    client = _client_on(httpx.MockTransport(handler), log_window_blocks=600)
    assert await client.fetch_flow_logs(
        HOOK, 11_000_000, 11_002_399, network=SEPOLIA) is None
    assert asked, "the client never asked at all"
    assert min(asked) >= C._LOG_MIN_WINDOW, (
        f"shrank past the floor: {asked}"
    )
    assert len(asked) <= C._LOG_MAX_SHRINKS + 2


# ---------------------------------------------------------------------------
# 12. verify_hook — the second gate, and a forgeable one (A27)
# ---------------------------------------------------------------------------


def _hook_answer_handler(
    addr: str, answers: dict[str, Any]
) -> Callable[[httpx.Request], httpx.Response]:
    """Serve a fixture's ``eth_call_answers`` map by selector."""
    by_calldata = {
        P.encode_getter(P.HOOK_SELECTORS[name]).lower(): raw
        for name, raw in answers.items()
        if name in P.HOOK_SELECTORS
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        out = []
        for entry in _entries(payload):
            data = str(entry["params"][0]["data"]).lower()
            raw = by_calldata.get(data)
            out.append({
                "jsonrpc": "2.0", "id": entry.get("id"),
                "result": raw if raw is not None else "0x",
            })
        return httpx.Response(200, json=out)

    return handler


def _adversary(fixture: str) -> tuple[str, dict[str, Any], dict]:
    data = load(fixture)
    addr, answers = next(iter(data["eth_call_answers"].items()))
    return addr, answers, data


async def test_a_flag_failing_candidate_costs_no_round_trip():
    """The 0x840 attack (A8), and the RPC-amplifier defence in one test.

    ``announce_adversarial_flag_mismatch.json`` encodes the address every
    version of the docs claimed the real hook carries. The gate is an
    **equality** test on the low 14 bits and it is pure arithmetic, so a
    self-post naming twenty decoys costs zero ``eth_call``s, not twenty.
    """
    addr = load("announce_adversarial_flag_mismatch")["attacker_addresses"][
        "candidate"]
    client = _raising_client()          # raises on ANY request
    verdict = await client.verify_hook(
        addr, network=MAINNET,
        expected_token=load("announce_adversarial_flag_mismatch")[
            "known_mainnet_imd"],
    )
    assert verdict.state == _REJECTED
    assert _GATE_FLAGS in verdict.detail
    assert verdict.hook_addr is None


async def test_the_silent_contract_is_rejected_and_never_adopted():
    """A candidate with the right flag word that answers nothing (A10).

    Every getter returns ``"0x"`` with no error. "The call did not error" is
    not "the getter answered", and an unreadable candidate is a **rejection**,
    never a "try again" the caller may carry forward.
    """
    addr, answers, data = _adversary("announce_adversarial_dead_getters")
    client = _client_on(httpx.MockTransport(_hook_answer_handler(addr, answers)))
    verdict = await client.verify_hook(
        addr, network=MAINNET, expected_token=data["known_mainnet_imd"])
    assert verdict.state == _REJECTED
    assert data["expected"]["verdict_detail_names"] in verdict.detail
    assert verdict.hook_addr is None


async def test_a_strangers_token_is_rejected_even_when_everything_else_agrees():
    """A hook-shaped contract whose ``token()`` is somebody else's ERC-20.

    Worth keeping and worth not overselling. ``token()`` is answered by the
    *candidate's own contract*, so this gate catches an attacker who did not
    bother to return the real mainnet IMD address — and nothing else (A27).
    It is a correctness check on a careless forgery, not a security boundary;
    the boundary is provenance, upstream.
    """
    addr, answers, data = _adversary("announce_adversarial_wrong_token")
    client = _client_on(httpx.MockTransport(_hook_answer_handler(addr, answers)))
    verdict = await client.verify_hook(
        addr, network=MAINNET, expected_token=data["known_mainnet_imd"])
    assert verdict.state == _REJECTED
    assert _GATE_TOKEN in verdict.detail
    assert verdict.hook_addr is None


async def test_verify_hook_judges_the_address_alone_and_knows_no_provenance():
    """Why provenance had to move upstream of this method (amendment A27).

    ``verify_hook`` takes a bare address string. It cannot tell one that came
    from an announce-wallet self-post from one that came from a hand-edited
    cache file, a community reply, or a stranger's inbound transaction — and it
    never could. Its signature has no room for the question, and the
    ``Pool4Discovery`` it returns leaves ``source_tx_hash`` ``None`` even on an
    adoption, because this method has nothing to put there.

    That blindness is not a gap to be closed here. The fingerprint behind it is
    **forgeable by construction**: a ``0x2840``-shaped address was mined in
    ~16,000 tries by the security pass and 20,141 by WP3 in under a second,
    four of the five getters are liveness checks any deployed contract passes,
    and ``token()`` is a value the candidate's own contract chooses. A
    fingerprint run against an address of unknown origin therefore proves
    nothing about the address, however thoroughly it ran. Only a transaction
    signed by the announce wallet is unforgeable, and that check belongs
    upstream in ``candidate_addresses``, where the caller still holds the
    transaction.

    **This test carried a false name until 2026-09-02.** It was
    ``test_a_persisted_adoption_is_re_verified_against_the_chain``, and it
    described a cache-file defence that no longer exists: WP7 removed the
    persisted address from the candidate set and WP3 deleted
    ``surf_pool4.reverify_persisted``, so nothing re-nominates an address from
    storage. The old promise was true only of the committed fixture, whose flag
    word is ``0x0000``; against anyone actually trying it, it returned
    *adopted*. A reassuring name over a defence a live demo defeats in twenty
    seconds is worse than no name, because someone greps for the protection and
    finds it.

    The address below is still the hostile payload's and must still be
    rejected — but it is safe because it never reaches ``verify_hook`` at all,
    not because ``verify_hook`` caught it.
    """
    # The signature has no room for the question, and this assertion is a
    # deliberate tripwire on the one place the pressure will come back. A27's
    # F5 contemplates re-establishing provenance from a persisted transaction
    # hash; doing that here would turn this red, and whoever turns it green
    # must show they are re-establishing provenance rather than bypassing it.
    params = list(inspect.signature(Pool4Client.verify_hook).parameters)
    assert params == ["self", "addr", "network", "expected_token"], (
        f"verify_hook grew a parameter: {params}. If it is a provenance "
        "source, read amendment A27 before making this pass — the persisted "
        "path was removed because it reached a fingerprint without one."
    )

    # The fixture's ``expected`` block still describes the retired defence and
    # is deliberately not read; only the address and the known token are.
    data = load("discovery_persisted_hostile")
    addr = data["persisted_payload"]["pool4_hook_addr"]
    client = _raising_client()
    verdict = await client.verify_hook(
        addr, network=MAINNET, expected_token=data["known_mainnet_imd"])
    assert verdict.state == _REJECTED
    assert verdict.hook_addr is None
    assert verdict.source_tx_hash is None


async def test_the_real_hook_is_adopted():
    """The other direction of A8: the gate must not reject the genuine hook.

    ``low14 == 0x840`` — the constant the plan, the PRD and the mechanics doc
    all mandated — rejects this address, and pool4 would never be discovered on
    any chain. The live capture is the evidence: ``getHookPermissions()``
    returns ``0x2840`` and it equals the address's own low fourteen bits.
    """
    flags = load("hook_flags_reference")
    assert flags["flag_word_int"] == P.POOL4_REQUIRED_FLAGS == 0x2840
    assert flags["address_low_14_bits"][HOOK] == "0x2840"

    transport = RecordingTransport(replay_handler("hook_state_healthy"))
    client = _client_on(transport)
    verdict = await client.verify_hook(
        HOOK, network=SEPOLIA, expected_token=TOKEN)
    assert verdict.state == _ADOPTED
    assert verdict.hook_addr.lower() == HOOK.lower()
    assert verdict.token_addr.lower() == TOKEN.lower()
    assert verdict.network == SEPOLIA
    # Even an adoption carries no provenance out of here: this method never
    # saw a transaction. The caller supplies ``source_tx_hash`` from the
    # self-post it matched, or nobody does. (A27)
    assert verdict.source_tx_hash is None
    # One round for one candidate — six getters, no block-number ride-along.
    assert len(transport.requests) == 1


async def test_a_disagreeing_get_hook_permissions_is_a_rejection():
    """Two independent sources, and they must agree when both speak.

    The address's low 14 bits are what the PoolManager enforces;
    ``getHookPermissions()`` is the contract's own claim. A contract claiming
    permissions its address does not carry is claiming to be something else.
    """
    perms_call = P.encode_getter(P.HOOK_SELECTORS["getHookPermissions"]).lower()
    lying = "0x" + ("0" * 64) * 14          # claims no permissions at all
    transport = RecordingTransport(replay_handler(
        "hook_state_healthy",
        overrides={(HOOK.lower(), perms_call): lying},
    ))
    client = _client_on(transport)
    verdict = await client.verify_hook(
        HOOK, network=SEPOLIA, expected_token=TOKEN)
    assert verdict.state == _REJECTED
    assert _GATE_PERMISSIONS in verdict.detail


async def test_a_silent_get_hook_permissions_still_adopts_on_the_address_bits():
    """Recorded so it is not relitigated: absence is not disagreement.

    The v4 permission field IS the address's low fourteen bits and the
    PoolManager enforces those; ``getHookPermissions()`` is corroboration.
    Requiring it would reject a mainnet hook built without that member — A8's
    own catastrophic direction, where pool4 is never discovered on any chain.
    Requiring it to *agree* when it speaks costs nothing, which is the test
    above.
    """
    perms_call = P.encode_getter(P.HOOK_SELECTORS["getHookPermissions"]).lower()
    transport = RecordingTransport(replay_handler(
        "hook_state_healthy",
        overrides={(HOOK.lower(), perms_call): "0x"},
    ))
    client = _client_on(transport)
    verdict = await client.verify_hook(
        HOOK, network=SEPOLIA, expected_token=TOKEN)
    assert verdict.state == _ADOPTED
    assert verdict.hook_addr.lower() == HOOK.lower()


async def test_a_verify_hook_outage_is_none_not_a_rejection():
    """"We could not look" is not a verdict.

    Persisting ``rejected`` from an outage would make a transient RPC failure
    look like a settled fact about the protocol, and the caller would drop a
    genuine adoption.
    """
    client = _offline_client()
    assert await client.verify_hook(
        HOOK, network=SEPOLIA, expected_token=TOKEN) is None


# ---------------------------------------------------------------------------
# 13. The house rules, swept
# ---------------------------------------------------------------------------


async def test_no_model_field_is_ever_a_zero_sentinel_under_total_outage():
    """Identity, not equality — ``0 == False`` and A2 is that bug exactly."""
    client = _client_on(httpx.MockTransport(
        replay_handler("hook_state_healthy", overrides={})))

    def all_none(model) -> bool:
        return all(
            getattr(model, name) is None for name in CONSTRUCTOR_KWARGS[type(model)]
        )

    # A responding endpoint that answers every call with "0x" is the
    # empty-address case (A10) writ large: every field must be None, none 0.
    def empty(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": e.get("id"), "result": "0x"}
            for e in _entries(payload)
        ])

    client = _client_on(httpx.MockTransport(empty))
    hook = await client.fetch_hook_state(
        HOOK, network=SEPOLIA, token_addr=TOKEN)
    dripper = await client.fetch_dripper_state(
        DRIPPER, network=SEPOLIA, token_addr=TOKEN)
    assert all_none(hook)
    assert all_none(dripper)
    # Spelled out once more with an identity check, because ``0 == False`` and
    # ``value in (None, False, 0)`` is the shape A2 caught passing while a
    # field defaulted to zero. ``is None`` cannot be satisfied by a 0.
    for model in (hook, dripper):
        for name in CONSTRUCTOR_KWARGS[type(model)]:
            value = getattr(model, name)
            assert value is None, f"{type(model).__name__}.{name} == {value!r}"


async def test_the_batch_primitive_writes_none_for_a_failed_entry_never_zero():
    """The sentinel rule at the one place it is actually decidable.

    Mutating this ``None`` to ``0`` leaves every model in this file all-``None``
    anyway, because WP3's ``answered()`` rejects a non-string — measured, not
    assumed. That is defence in depth working, and it is also why the rule has
    to be asserted *here*: a test that can only observe the decoded models
    cannot see this line change, so it would advertise a protection it does not
    have. Asserted with ``is None``, not ``== None``, and not ``in (None, 0)``
    — ``0 == False`` is A2's bug exactly.
    """
    def half_broken(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        out = []
        for i, entry in enumerate(_entries(payload)):
            if i == 0:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "error": {"code": 3, "message": "execution reverted"}})
            else:
                out.append({"jsonrpc": "2.0", "id": entry.get("id"),
                            "result": "0x" + format(7, "064x")})
        return httpx.Response(200, json=out)

    client = _client_on(httpx.MockTransport(half_broken))
    results = await client._rpc_state_batch(
        SEPOLIA,
        [("eth_call", [{"to": HOOK, "data": "0x01"}, "latest"]),
         ("eth_call", [{"to": HOOK, "data": "0x02"}, "latest"])],
    )
    assert results is not None
    assert results[0] is None, f"a failed batch entry became {results[0]!r}"
    assert results[1] == "0x" + format(7, "064x")


async def test_a_per_entry_batch_error_is_none_and_never_a_zero():
    """The corruption that outlives the outage, at its source.

    A batch entry that comes back carrying an ``error`` object is a *failed
    read*. Writing ``0`` there would make the manager unable to tell "the RPC
    is down" from "the counter is zero", and the zero then gets persisted into
    the cache and into the reserve series, where no later healthy tick removes
    it. Covered separately from the ``"0x"`` case above because it is a
    different branch: ``"0x"`` is a *successful* response with an empty body.
    """
    def erroring(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": e.get("id"),
             "error": {"code": 3, "message": "execution reverted"}}
            for e in _entries(payload)
        ])

    client = _client_on(httpx.MockTransport(erroring))
    hook = await client.fetch_hook_state(
        HOOK, network=SEPOLIA, token_addr=TOKEN)
    dripper = await client.fetch_dripper_state(
        DRIPPER, network=SEPOLIA, token_addr=TOKEN)
    vault = await client.fetch_vault_state(VAULT, network=SEPOLIA)
    slot0 = await client.fetch_pool_slot0(
        POOL_ID, network=SEPOLIA, pool_manager=POOL_MANAGER)

    for model in (hook, dripper, vault):
        for name in CONSTRUCTOR_KWARGS[type(model)]:
            value = getattr(model, name)
            assert value is None, f"{type(model).__name__}.{name} == {value!r}"
    assert slot0.sqrt_price_x96 is None and slot0.liquidity is None
    assert slot0.tick is None and slot0.lp_fee is None
