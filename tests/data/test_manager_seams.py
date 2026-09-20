"""Branch 10 WP-B: the constructor seams that make ``data/`` a library.

Seven managers used to build their client, their cache and their cache path
inside ``__init__`` with no way in from outside, and three clients read an
environment variable **at import** and froze it into a signature default
(``ocm_client._RPC_URL``, ``CatTownClient.RPC_URL``, ``FrenPetClient.INDEXER_DB``).
Both shapes are fine for one TUI process that owns the user's home directory
and is configured once; both are fatal for a hosting backend that serves two
configurations, or any configuration the process did not have at import time.

What each test here pins:

* **Managers.** With ``cache_path=`` (ocm: ``cache_file=``) pointing into
  ``tmp_path`` and an injected fake client, one full ``fetch_and_compute()``
  cycle plus a save must leave the module's own default path *untouched*.
  The module defaults are redirected to ``tmp_path/forbidden``, a directory
  nothing may create, so a manager that ignores the injected path is caught by
  the file it writes rather than by a claim about the file it writes.
  ``pathlib.Path.home`` is additionally made to raise for the whole test, which
  catches any *runtime* home read (there are none left; the surviving reads are
  the import-time ``_CACHE_DIR`` constants, which the ``forbidden`` redirection
  is what covers).
* **The payload is unchanged.** Four managers already have a committed key
  contract (bakery, base, frenpet, talismans) and this file imports it rather
  than restating it. The other four (cattown, dota, ttt, ocm) have none
  anywhere in the repo, so the anchor is derived instead: the seam-built
  manager's key set must equal the key set of the same manager built the way
  it is built today, with the same fake data. Neither anchor is hand-typed
  here, and a manager that returned ``{}`` fails both.
* **Clients.** An environment variable set *after* the module was imported is
  honoured by the next instance; an explicit argument beats the variable; with
  the variable unset the documented module/class default is what is used.
* **talismans' log pool.** ``_get_logs`` must iterate the *injected* pool, and
  a banned host must be refused at construction rather than at the first call.

Zero network: every client here is a fake, and the one place a transport is
installed (:func:`test_the_talismans_log_pool_is_what_get_logs_iterates`) uses
one that records the URL and raises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from maxpane_dashboard.data import base_manager as base_manager_mod
from maxpane_dashboard.data import cattown_client as cattown_client_mod
from maxpane_dashboard.data import cattown_manager as cattown_manager_mod
from maxpane_dashboard.data import dota_manager as dota_manager_mod
from maxpane_dashboard.data import frenpet_client as frenpet_client_mod
from maxpane_dashboard.data import frenpet_manager as frenpet_manager_mod
from maxpane_dashboard.data import manager as bakery_manager_mod
from maxpane_dashboard.data import ocm_client as ocm_client_mod
from maxpane_dashboard.data import ocm_manager as ocm_manager_mod
from maxpane_dashboard.data import talismans_client as talismans_client_mod
from maxpane_dashboard.data import talismans_manager as talismans_manager_mod
from maxpane_dashboard.data import ttt_manager as ttt_manager_mod
from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.data.cattown_client import CatTownClient
from maxpane_dashboard.data.cattown_manager import CatTownManager
from maxpane_dashboard.data.dota_manager import DOTAManager
from maxpane_dashboard.data.frenpet_client import FrenPetClient
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.ocm_client import OCMClient
from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.data.talismans_client import TalismansClient
from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.data.ttt_manager import TTTManager

# The fakes and the key contracts are imported from the manager test files that
# already own them, so this file adds no second copy of either.  Every one of
# those files is byte-unchanged by WP-B.
from tests.data.test_base_manager import (  # noqa: E402
    CORE_KEYS as BASE_CORE_KEYS,
    OVERVIEW_KEYS as BASE_OVERVIEW_KEYS,
    _FakeClient as _BaseFakeClient,
)
from tests.data.test_cattown_manager import (  # noqa: E402
    _Client as _CatTownFakeClient,
    _entry as _cattown_entry,
    _snapshot as _cattown_snapshot,
)
from tests.data.test_dota_manager import (  # noqa: E402
    _Client as _DotaFakeClient,
    _hero as _dota_hero,
    _state as _dota_state,
)
from tests.data.test_frenpet_manager import (  # noqa: E402
    EXPECTED_KEYS as FRENPET_KEYS,
    _make_snapshot as _frenpet_snapshot,
)
from tests.data.test_manager_contract import (  # noqa: E402
    REQUIRED_KEYS as BAKERY_KEYS,
    _snapshot as _bakery_snapshot,
)
from tests.data.test_manager_ev_catalog import _StubClient as _BakeryStubClient  # noqa: E402
from tests.data.test_ocm_manager import (  # noqa: E402
    _StubClient as _OCMStubClient,
    _T0 as _OCM_T0,
    _snap as _ocm_snap,
)
from tests.data.test_talismans_manager import (  # noqa: E402
    _FakeClient as _TalismansFakeClient,
    _REQUIRED_KEYS as TALISMANS_KEYS,
)
from tests.data.test_ttt_manager import (  # noqa: E402
    FakeClient as _TTTFakeClient,
    FakePrice as _TTTFakePrice,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared scaffolding
# ---------------------------------------------------------------------------


def _forbid_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any *runtime* ``Path.home()`` read fails loudly for the rest of the test."""

    def _raise(*_a: Any, **_k: Any):
        raise AssertionError("home touched")

    monkeypatch.setattr(Path, "home", _raise)


def _redirect_module_default(
    monkeypatch: pytest.MonkeyPatch, module: Any, tmp_path: Path, name: str
) -> Path:
    """Point the module's import-time cache default at a forbidden directory.

    Returned so the caller can assert it was never created.  This is the guard
    that actually bites: ``_CACHE_DIR`` / ``_CACHE_FILE`` are computed from
    ``Path.home()`` once, at import, so patching ``Path.home`` later cannot see
    a manager that falls back to them.
    """
    forbidden = tmp_path / "forbidden"
    monkeypatch.setattr(module, "_CACHE_DIR", forbidden)
    monkeypatch.setattr(module, "_CACHE_FILE", forbidden / name)
    return forbidden


def _seam_path(tmp_path: Path, name: str) -> Path:
    """The injected cache path, in a directory that already exists."""
    seam_dir = tmp_path / "seam"
    seam_dir.mkdir(exist_ok=True)
    return seam_dir / name


class _NoNetworkClient:
    """Stands in for the client ``__init__`` builds when nothing is injected.

    Every attribute is an awaitable that raises, so a legacy-construction
    reference run that forgot to install its double fails loudly instead of
    exercising a degradation path and agreeing with the seam run for the wrong
    reason.
    """

    def __getattr__(self, name: str):
        async def _raise(*_a: Any, **_k: Any):
            raise AssertionError(f"unscripted client call: {name}")

        return _raise


class _FakePriceClient:
    """``PriceClient`` without an ``httpx.AsyncClient`` behind it."""

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.closed = False

    async def get_eth_usd(self) -> float:
        return 3800.0

    async def close(self) -> None:
        self.closed = True


class _FrenPetFakeClient:
    """The FrenPet surface ``fetch_and_compute`` reaches in spectator mode."""

    def __init__(self) -> None:
        self.closed = False

    async def fetch_snapshot(self, _wallet: str | None, *, remote_only: bool = True):
        return _frenpet_snapshot()

    async def get_recent_attacks(self, limit: int = 50) -> list[dict[str, Any]]:
        return []

    async def close(self) -> None:
        self.closed = True


def _assert_isolated(seam_path: Path, forbidden: Path) -> None:
    assert seam_path.exists(), f"nothing was written to the injected {seam_path}"
    assert not forbidden.exists(), (
        f"the manager fell back to its module default: {forbidden} was created"
    )


# ---------------------------------------------------------------------------
# Managers -- the four with a committed key contract
# ---------------------------------------------------------------------------


async def test_the_bakery_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete ``self._cache_path = ...`` in ``manager.DataManager.__init__``
    (or revert either ``load_from_file`` / ``save_to_file`` call to
    ``_CACHE_FILE``) and ``tmp_path/forbidden`` is created -- red here."""
    forbidden = _redirect_module_default(
        monkeypatch, bakery_manager_mod, tmp_path, "history_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "history_cache.json")

    mgr = DataManager(
        poll_interval=30,
        client=_BakeryStubClient([_bakery_snapshot(fetched_at=1_700_000_000.0)]),
        cache_path=seam,
    )
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert BAKERY_KEYS <= set(data)
    _assert_isolated(seam, forbidden)


async def test_the_base_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete ``self._cache_path = ...`` in ``base_manager.BaseManager.__init__``
    (or revert either cache call to ``_CACHE_FILE``) and this reddens on
    ``tmp_path/forbidden``."""
    forbidden = _redirect_module_default(
        monkeypatch, base_manager_mod, tmp_path, "base_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "base_cache.json")

    mgr = BaseManager(
        poll_interval=30, remote_only=True, client=_BaseFakeClient(), cache_path=seam
    )
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert (BASE_CORE_KEYS | BASE_OVERVIEW_KEYS) <= set(data)
    _assert_isolated(seam, forbidden)


async def test_the_frenpet_manager_takes_a_client_a_cache_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete ``self._cache_path = ...`` in ``frenpet_manager`` and this reddens
    on ``tmp_path/forbidden``; drop the ``cache`` parameter and the injected
    cache object below is no longer the one the manager fills."""
    forbidden = _redirect_module_default(
        monkeypatch, frenpet_manager_mod, tmp_path, "frenpet_cache.json"
    )
    monkeypatch.setattr(frenpet_manager_mod, "PriceClient", _FakePriceClient)
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "frenpet_cache.json")

    injected_cache = frenpet_manager_mod.FrenPetCache(max_history=120)
    mgr = FrenPetManager(
        poll_interval=30,
        client=_FrenPetFakeClient(),
        cache=injected_cache,
        cache_path=seam,
    )
    assert mgr.cache is injected_cache
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert FRENPET_KEYS <= set(data)
    _assert_isolated(seam, forbidden)


async def test_the_talismans_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``self._cache_path.parent.mkdir(...)`` to ``_CACHE_DIR.mkdir(...)``
    -- or either cache call to ``_CACHE_FILE`` -- and ``tmp_path/forbidden`` is
    created, which is red here."""
    forbidden = _redirect_module_default(
        monkeypatch, talismans_manager_mod, tmp_path, "talismans_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "talismans_cache.json")

    mgr = TalismansManager(
        poll_interval=30, client=_TalismansFakeClient(), cache_path=seam
    )
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert TALISMANS_KEYS <= set(data)
    _assert_isolated(seam, forbidden)


# ---------------------------------------------------------------------------
# Managers -- the four whose key contract is derived, not committed
# ---------------------------------------------------------------------------


async def test_the_cattown_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two managers, one fake snapshot: the seam-built one must answer the same
    keys as the legacy-built one.  Delete ``self._cache_path = ...`` in
    ``cattown_manager`` and ``tmp_path/forbidden`` is created -- red here."""
    forbidden = _redirect_module_default(
        monkeypatch, cattown_manager_mod, tmp_path, "cattown_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "cattown_cache.json")

    def _client() -> Any:
        return _CatTownFakeClient(_cattown_snapshot([_cattown_entry(4.25)]), raffle=250)

    # Legacy: the client class patched out, the cache path the module default.
    monkeypatch.setattr(cattown_manager_mod, "CatTownClient", _NoNetworkClient)
    monkeypatch.setattr(
        cattown_manager_mod, "_CACHE_FILE", tmp_path / "legacy_cattown.json"
    )
    legacy = CatTownManager(poll_interval=30)
    legacy.client = _client()
    legacy_keys = set(await legacy.fetch_and_compute())
    monkeypatch.setattr(cattown_manager_mod, "_CACHE_FILE", forbidden / "c.json")

    mgr = CatTownManager(poll_interval=30, client=_client(), cache_path=seam)
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert legacy_keys, "the reference run produced no keys at all"
    assert set(data) == legacy_keys
    _assert_isolated(seam, forbidden)


async def test_the_dota_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape as cattown.  Revert ``self._cache_path.parent.mkdir(...)`` to
    ``_CACHE_DIR.mkdir(...)`` in ``dota_manager`` and ``tmp_path/forbidden`` is
    created at construction -- red here."""
    forbidden = _redirect_module_default(
        monkeypatch, dota_manager_mod, tmp_path, "dota_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "dota_cache.json")

    def _client() -> Any:
        return _DotaFakeClient(_dota_state([_dota_hero("Axe")]))

    monkeypatch.setattr(dota_manager_mod, "DOTAClient", _NoNetworkClient)
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    monkeypatch.setattr(dota_manager_mod, "_CACHE_DIR", legacy_dir)
    monkeypatch.setattr(dota_manager_mod, "_CACHE_FILE", legacy_dir / "dota.json")
    legacy = DOTAManager(poll_interval=30)
    legacy.client = _client()
    legacy_keys = set(await legacy.fetch_and_compute())
    monkeypatch.setattr(dota_manager_mod, "_CACHE_DIR", forbidden)
    monkeypatch.setattr(dota_manager_mod, "_CACHE_FILE", forbidden / "dota.json")

    mgr = DOTAManager(poll_interval=30, client=_client(), cache_path=seam)
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert legacy_keys, "the reference run produced no keys at all"
    assert set(data) == legacy_keys
    _assert_isolated(seam, forbidden)


async def test_the_ttt_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape.  Revert ``self._cache_path.parent.mkdir(...)`` to
    ``_CACHE_DIR.mkdir(...)`` in ``ttt_manager``, or drop the ``cache_path``
    argument, and ``tmp_path/forbidden`` is created -- red here."""
    forbidden = _redirect_module_default(
        monkeypatch, ttt_manager_mod, tmp_path, "ttt_cache.json"
    )
    monkeypatch.setattr(ttt_manager_mod, "PriceClient", _TTTFakePrice)
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "ttt_cache.json")

    monkeypatch.setattr(ttt_manager_mod, "TTTClient", _NoNetworkClient)
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_DIR", legacy_dir)
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_FILE", legacy_dir / "ttt.json")
    legacy = TTTManager(poll_interval=30)
    legacy.client = _TTTFakeClient()
    legacy_keys = set(await legacy.fetch_and_compute())
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_DIR", forbidden)
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_FILE", forbidden / "ttt.json")

    mgr = TTTManager(poll_interval=30, client=_TTTFakeClient(), cache_path=seam)
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert legacy_keys, "the reference run produced no keys at all"
    assert set(data) == legacy_keys
    _assert_isolated(seam, forbidden)


async def test_the_ocm_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ocm already had ``client=`` and ``cache_file=``; WP-B adds ``cache=``.
    Drop the ``cache`` parameter and the ``mgr.cache is injected_cache``
    assertion below reddens; revert ``self._cache_file`` and ``forbidden`` is
    created."""
    forbidden = _redirect_module_default(
        monkeypatch, ocm_manager_mod, tmp_path, "ocm_cache.json"
    )
    _forbid_home(monkeypatch)
    seam = _seam_path(tmp_path, "ocm_cache.json")

    def _snaps() -> list[Any]:
        return [_ocm_snap(fetched_at=_OCM_T0)]

    legacy = OCMManager(
        poll_interval=60,
        client=_OCMStubClient(_snaps()),
        cache_file=tmp_path / "legacy_ocm.json",
    )
    legacy_keys = set(await legacy.fetch_and_compute())

    injected_cache = ocm_manager_mod.OCMCache(max_history=120)
    mgr = OCMManager(
        poll_interval=60,
        client=_OCMStubClient(_snaps()),
        cache=injected_cache,
        cache_file=seam,
    )
    assert mgr.cache is injected_cache
    data = await mgr.fetch_and_compute()
    mgr.save_cache()

    assert legacy_keys, "the reference run produced no keys at all"
    assert set(data) == legacy_keys
    _assert_isolated(seam, forbidden)


# ---------------------------------------------------------------------------
# Clients -- the environment is read at construction, not at import
# ---------------------------------------------------------------------------


async def test_the_ocm_endpoint_env_is_read_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ocm_client`` is imported long before this line runs, so a value set
    here is *after* import by definition.  Restore ``rpc_url: str = _RPC_URL``
    as the signature default and the first assertion reddens."""
    monkeypatch.setenv(ocm_client_mod._RPC_URL_ENV, "https://set-after-import.example")
    client = OCMClient()
    try:
        assert client._rpc_url == "https://set-after-import.example"
    finally:
        await client.close()

    explicit = OCMClient(rpc_url="https://explicit.example")
    try:
        assert explicit._rpc_url == "https://explicit.example", (
            "an explicit argument must beat the environment"
        )
    finally:
        await explicit.close()

    monkeypatch.delenv(ocm_client_mod._RPC_URL_ENV, raising=False)
    default = OCMClient()
    try:
        assert default._rpc_url == ocm_client_mod._RPC_URL
    finally:
        await default.close()

    # The module constant is still the documented default *and* still a
    # monkeypatch target -- several suites redirect endpoints that way.
    monkeypatch.setattr(ocm_client_mod, "_RPC_URL", "https://patched.example")
    patched = OCMClient()
    try:
        assert patched._rpc_url == "https://patched.example"
    finally:
        await patched.close()


async def test_the_cattown_endpoint_env_is_read_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore ``rpc_url: str = RPC_URL`` as the signature default and the first
    assertion reddens; the class attribute stays the documented default."""
    monkeypatch.setenv(CatTownClient.RPC_URL_ENV, "https://base-after-import.example")
    client = CatTownClient()
    try:
        assert client._rpc_url == "https://base-after-import.example"
        # The primary is never also a fallback, and that dedupe must follow the
        # *resolved* URL, not the (now ``None``) argument.
        assert client._rpc_url not in client._fallback_rpcs
    finally:
        await client.close()

    explicit = CatTownClient(rpc_url="https://explicit.example")
    try:
        assert explicit._rpc_url == "https://explicit.example"
    finally:
        await explicit.close()

    monkeypatch.delenv(CatTownClient.RPC_URL_ENV, raising=False)
    default = CatTownClient()
    try:
        assert default._rpc_url == CatTownClient.RPC_URL
    finally:
        await default.close()

    monkeypatch.setattr(cattown_client_mod.CatTownClient, "RPC_URL", "https://patched.example")
    patched = CatTownClient()
    try:
        assert patched._rpc_url == "https://patched.example"
    finally:
        await patched.close()


async def test_the_frenpet_indexer_env_is_read_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore ``indexer_db: str = INDEXER_DB`` as the signature default and the
    first assertion reddens.  ``""`` stays a legitimate explicit argument: it
    is how a caller says "no indexer", so only ``None`` means "resolve it"."""
    monkeypatch.setenv(FrenPetClient.INDEXER_DB_ENV, "/tmp/set-after-import.db")
    client = FrenPetClient()
    try:
        assert client._indexer_db == "/tmp/set-after-import.db"
    finally:
        await client.close()

    explicit = FrenPetClient(indexer_db="")
    try:
        assert explicit._indexer_db == "", (
            "an explicit empty path must beat the environment, not fall back to it"
        )
    finally:
        await explicit.close()

    monkeypatch.delenv(FrenPetClient.INDEXER_DB_ENV, raising=False)
    default = FrenPetClient()
    try:
        assert default._indexer_db == FrenPetClient.INDEXER_DB
    finally:
        await default.close()


# ---------------------------------------------------------------------------
# talismans -- the log pool is configuration, and a banned host is refused
# ---------------------------------------------------------------------------


async def test_the_talismans_log_pool_is_what_get_logs_iterates() -> None:
    """Change ``_get_logs`` back to the module constant ``_LOG_RPCS`` and the
    recorded hosts are tenderly/drpc/publicnode instead of the injected pair --
    red here.  The transport records and raises, so no socket is opened."""
    seen: list[str] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        raise httpx.ConnectError("no network in tests", request=request)

    transport = httpx.MockTransport(_handler)
    injected = ["https://log-a.example", "https://log-b.example"]
    client = TalismansClient(
        log_rpcs=injected, http_client=httpx.AsyncClient(transport=transport)
    )
    try:
        logs, watermark = await client._get_logs("0xa", [], 0, 10)
    finally:
        await client.close()

    assert logs == [] and watermark == -1
    assert seen, "no request was attempted at all"
    assert set(seen) == set(injected), seen
    assert not any(
        host in url
        for url in seen
        for host in ("tenderly", "drpc", "publicnode")
    ), f"the module-level pool was used instead of the injected one: {seen}"


async def test_a_banned_talismans_log_host_is_refused_at_construction() -> None:
    """Delete the ``for url in [...]`` ban loop in ``TalismansClient.__init__``
    and this reddens.  The keyless/liveness constraint is enforced by the
    constructor, not by a comment next to the pool."""
    assert talismans_client_mod._BANNED_RPC_HOSTS
    banned = next(iter(talismans_client_mod._BANNED_RPC_HOSTS))

    with pytest.raises(ValueError, match="banned RPC host"):
        TalismansClient(log_rpcs=[f"https://{banned}/x"])
    with pytest.raises(ValueError, match="banned RPC host"):
        TalismansClient(primary_rpc=f"https://{banned}/x")

    # The shipped defaults must themselves pass the gate, or every dashboard
    # start-up raises.
    default = TalismansClient()
    try:
        assert default._log_rpcs == talismans_client_mod._LOG_RPCS
    finally:
        await default.close()
