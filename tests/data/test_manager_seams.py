"""Branch 10 WP-B: the constructor seams that make ``data/`` a library.

Seven managers used to build their client, their cache and their cache path
inside ``__init__`` with no way in from outside, and three clients read an
environment variable **at import** and froze it into a signature default
(``ocm_client._RPC_URL``, ``CatTownClient.RPC_URL``, ``FrenPetClient.INDEXER_DB``).
Both shapes are fine for one TUI process that owns the user's home directory
and is configured once; both are fatal for a hosting backend that serves two
configurations, or any configuration the process did not have at import time.

What each test here pins:

* **Managers.** Each module's import-time default (``_CACHE_DIR`` /
  ``_CACHE_FILE``) is redirected into ``tmp_path`` and **seeded** with a
  populated cache file, written by that manager's own cache class. A manager
  built with ``cache_path=`` (ocm: ``cache_file=``) and an injected fake client
  must then come up *empty* (it did not load the seeded file), must hold the
  injected client object itself, and after one ``fetch_and_compute()`` plus a
  save must have written to ``cache_path`` while leaving the seeded file
  byte-for-byte unchanged. Seeding is the point: an *absent* module default
  cannot distinguish "loaded the right file" from "loaded the wrong, missing
  one", which is how WP-B review finding I1 got through -- reverting only the
  ``load_from_file`` call in all eight managers left every test green.
  ``pathlib.Path.home`` is additionally made to raise for the whole test as a
  backstop for any *runtime* home read (there are none left; the surviving
  reads are the import-time constants, which the seeding is what covers).
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

import time
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
from maxpane_dashboard.data.surf_manager import SurfManager
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
from tests.data.test_surf_manager import (  # noqa: E402
    FakeClock as _SurfFakeClock,
    FakeSurfClient as _SurfFakeClient,
)
from tests.data.test_surf_manager_pool4 import FakePool4Client as _SurfFakePool4Client  # noqa: E402

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared scaffolding
# ---------------------------------------------------------------------------


def _forbid_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any *runtime* ``Path.home()`` read fails loudly for the rest of the test.

    This is a backstop, not the load/save guard.  ``_CACHE_DIR = Path.home() /
    ".maxpane"`` is evaluated at **import**, so by the time this runs the module
    constants are plain ``Path`` objects and a manager that ignores
    ``cache_path`` touches ``home`` not at all.  What catches that is
    :func:`_assert_cache_path_is_both_halves`.
    """

    def _raise(*_a: Any, **_k: Any):
        raise AssertionError("home touched")

    monkeypatch.setattr(Path, "home", _raise)


def _poison_path(
    monkeypatch: pytest.MonkeyPatch, module: Any, tmp_path: Path, name: str
) -> Path:
    """Redirect the module's import-time cache default into ``tmp_path``.

    The returned file is the one a manager that ignored ``cache_path`` would
    read and write.  It is *seeded* (see below), so both halves of the seam are
    observable: a wrong **load** picks the seeded state up, a wrong **save**
    changes the seeded file's bytes.
    """
    poisoned_dir = tmp_path / "module_default"
    poisoned_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(module, "_CACHE_DIR", poisoned_dir)
    monkeypatch.setattr(module, "_CACHE_FILE", poisoned_dir / name)
    return poisoned_dir / name


class _NoNetworkClient:
    """What ``__init__`` builds when nothing is injected -- and it cannot dial.

    Every attribute is an awaitable that raises.  Patched into all eight
    manager modules so that a manager which ignores ``client=`` fails loudly
    instead of constructing a real ``httpx.AsyncClient`` and opening sockets
    from a test (hard constraint 3).  The identity assertion in
    :func:`_assert_cache_path_is_both_halves` is what actually pins the seam;
    this class is the safety net under it.
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


def _history_size(mgr: Any) -> Any:
    """The six ``SeriesCache`` subclasses all expose this; 0 means "not loaded"."""
    return mgr.cache.history_size


async def _assert_cache_path_is_both_halves(
    *,
    build: Any,
    probe: Any,
    poison: Path,
    seam: Path,
    makes_dir: bool,
) -> tuple[Any, dict[str, Any]]:
    """Pin the **load** half, the **save** half and the **client** seam at once.

    ``build(path)`` returns ``(manager, client, cache_or_None)``; ``probe(mgr)``
    returns something falsy for a cache nothing was loaded into and truthy for
    one that read a populated file.

    The mechanism, because the obvious one does not work: asserting that the
    module default "was never created" is a no-op for the load half -- there is
    nothing at that path to load, so a manager still reading ``_CACHE_FILE``
    reads an absent file and comes up empty exactly as if it had obeyed
    ``cache_path``.  (That was WP-B review finding I1: reverting only the
    ``load_from_file`` call in all eight managers left every test green.)  So
    the module default is **seeded** with a populated cache file written by the
    manager's own cache class, and then:

    * a manager pointed at the seeded file must load it (anti-vacuity -- without
      this, "the cache is empty" would pass against a file nothing can read);
    * the manager pointed at ``cache_path`` must **not** have loaded it;
    * after a cycle and a save, the seeded file must be byte-for-byte what it
      was -- which is what a wrong save changes.
    """
    poison.parent.mkdir(parents=True, exist_ok=True)
    if not makes_dir:
        seam.parent.mkdir(parents=True, exist_ok=True)

    # 1. Seed the module default with a real, populated cache file.
    seeder, seeder_client, _ = build(poison)
    # Checked here as well as in step 3 so that a manager which ignores
    # ``client=`` fails on the seam it broke rather than on whatever its
    # self-built client does next (WP-B review finding I2: the self-built
    # client opened real sockets, which hard constraint 3 forbids).
    assert seeder.client is seeder_client, (
        "the manager built its own client instead of using the injected one"
    )
    await seeder.fetch_and_compute()
    seeder.save_cache()
    poison_bytes = poison.read_bytes()
    assert poison_bytes, "the seed step wrote nothing; the checks below are vacuous"

    # 2. Anti-vacuity: that file *is* loadable by this manager.
    control, _, _ = build(poison)
    assert probe(control), (
        "the seeded module-default file did not load; step 3 would pass for the "
        "wrong reason"
    )

    # 3. The load half: pointed at cache_path, the manager must come up empty.
    mgr, injected_client, injected_cache = build(seam)
    assert not probe(mgr), (
        "the manager loaded its module default instead of the injected cache_path"
    )
    assert mgr.client is injected_client, (
        "the manager built its own client instead of using the injected one"
    )
    if injected_cache is not None:
        assert mgr.cache is injected_cache
    if makes_dir:
        assert seam.parent.is_dir(), (
            "the cache directory was created somewhere other than cache_path's parent"
        )

    # 4. The save half: cache_path is written, the module default is not.
    data = await mgr.fetch_and_compute()
    mgr.save_cache()
    assert seam.exists(), f"nothing was written to the injected {seam}"
    assert poison.read_bytes() == poison_bytes, (
        "the manager wrote to its module default instead of the injected path"
    )
    return mgr, data


# ---------------------------------------------------------------------------
# Managers -- the four with a committed key contract
# ---------------------------------------------------------------------------


async def test_the_bakery_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``manager.py``'s ``load_from_file`` call to ``str(_CACHE_FILE)``
    and step 3 reddens (the seeded two-bakery history is loaded); revert its
    ``save_to_file`` call and step 4 reddens (the seeded file's bytes change);
    drop ``client=`` and the identity assertion reddens."""
    poison = _poison_path(
        monkeypatch, bakery_manager_mod, tmp_path, "history_cache.json"
    )
    monkeypatch.setattr(bakery_manager_mod, "GameDataClient", _NoNetworkClient)
    _forbid_home(monkeypatch)

    def _build(path: Path):
        client = _BakeryStubClient([_bakery_snapshot(fetched_at=time.time())])
        return (
            DataManager(poll_interval=30, client=client, cache_path=path),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "history_cache.json",
        makes_dir=False,
    )
    assert BAKERY_KEYS <= set(data)


async def test_the_base_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``base_manager.py``'s ``load_from_file`` call to ``_CACHE_FILE``
    and step 3 reddens (the seeded three-token price history is loaded); revert
    the save and step 4 reddens; drop ``client=`` and the identity assertion
    reddens -- which is the one that would otherwise let a real
    ``BaseChainClient`` open sockets."""
    poison = _poison_path(monkeypatch, base_manager_mod, tmp_path, "base_cache.json")
    monkeypatch.setattr(base_manager_mod, "BaseChainClient", _NoNetworkClient)
    _forbid_home(monkeypatch)

    def _build(path: Path):
        client = _BaseFakeClient()
        return (
            BaseManager(
                poll_interval=30, remote_only=True, client=client, cache_path=path
            ),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "base_cache.json",
        makes_dir=False,
    )
    assert (BASE_CORE_KEYS | BASE_OVERVIEW_KEYS) <= set(data)


async def test_the_frenpet_manager_takes_a_client_a_cache_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``frenpet_manager.py``'s ``load_from_file`` call to ``_CACHE_FILE``
    and step 3 reddens (the seeded five-pet history is loaded); revert the save
    and step 4 reddens; drop ``client=`` or ``cache=`` and the two identity
    assertions redden."""
    poison = _poison_path(
        monkeypatch, frenpet_manager_mod, tmp_path, "frenpet_cache.json"
    )
    monkeypatch.setattr(frenpet_manager_mod, "FrenPetClient", _NoNetworkClient)
    monkeypatch.setattr(frenpet_manager_mod, "PriceClient", _FakePriceClient)
    _forbid_home(monkeypatch)

    def _build(path: Path):
        client = _FrenPetFakeClient()
        cache = frenpet_manager_mod.FrenPetCache(max_history=120)
        return (
            FrenPetManager(
                poll_interval=30, client=client, cache=cache, cache_path=path
            ),
            client,
            cache,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "frenpet_cache.json",
        makes_dir=False,
    )
    assert FRENPET_KEYS <= set(data)


async def test_the_talismans_manager_takes_a_client_and_a_cache_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``talismans_manager.py``'s ``load_from_file`` call to
    ``_CACHE_FILE`` and step 3 reddens (``operations_total`` comes back as 1
    from the seeded file instead of 0); revert the save, or revert
    ``self._cache_path.parent.mkdir`` to ``_CACHE_DIR.mkdir``, and step 4 or the
    ``makes_dir`` assertion reddens; drop ``client=`` and the identity assertion
    reddens."""
    poison = _poison_path(
        monkeypatch, talismans_manager_mod, tmp_path, "talismans_cache.json"
    )
    monkeypatch.setattr(talismans_manager_mod, "TalismansClient", _NoNetworkClient)
    _forbid_home(monkeypatch)

    def _build(path: Path):
        client = _TalismansFakeClient()
        return (
            TalismansManager(poll_interval=30, client=client, cache_path=path),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        # ``known_ids`` is seeded with the 1,536 genesis ids by ``__init__``
        # itself, so it is non-empty for a fresh cache too and cannot tell the
        # two apart.  The cumulative operation counter can.
        probe=lambda mgr: mgr.cache.operations_total,
        poison=poison,
        seam=tmp_path / "seam" / "talismans_cache.json",
        makes_dir=True,
    )
    assert TALISMANS_KEYS <= set(data)


# ---------------------------------------------------------------------------
# Managers -- the four whose key contract is derived, not committed
# ---------------------------------------------------------------------------


async def test_the_cattown_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revert ``cattown_manager.py``'s ``load_from_file`` call to ``_CACHE_FILE``
    and step 3 reddens; revert the save and step 4 reddens; drop ``client=`` and
    the identity assertion reddens.  The key set is checked against a
    legacy-built manager rather than a hand-typed list, because ``cattown_models``
    carries no ``*_KEYS`` tuple."""
    _forbid_home(monkeypatch)

    def _client() -> Any:
        return _CatTownFakeClient(_cattown_snapshot([_cattown_entry(4.25)]), raffle=250)

    # Reference run: built the way it is built today, its own cache file.
    monkeypatch.setattr(cattown_manager_mod, "CatTownClient", _NoNetworkClient)
    monkeypatch.setattr(
        cattown_manager_mod, "_CACHE_FILE", tmp_path / "legacy_cattown.json"
    )
    legacy = CatTownManager(poll_interval=30)
    legacy.client = _client()
    legacy_keys = set(await legacy.fetch_and_compute())
    assert legacy_keys, "the reference run produced no keys at all"

    poison = _poison_path(
        monkeypatch, cattown_manager_mod, tmp_path, "cattown_cache.json"
    )

    def _build(path: Path):
        client = _client()
        return (
            CatTownManager(poll_interval=30, client=client, cache_path=path),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "cattown_cache.json",
        makes_dir=False,
    )
    assert set(data) == legacy_keys


async def test_the_dota_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape as cattown, plus the directory check: revert
    ``self._cache_path.parent.mkdir(...)`` to ``_CACHE_DIR.mkdir(...)`` in
    ``dota_manager`` and the ``makes_dir`` assertion reddens; revert the load
    and step 3 reddens; revert the save and step 4 reddens."""
    _forbid_home(monkeypatch)

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
    assert legacy_keys, "the reference run produced no keys at all"

    poison = _poison_path(monkeypatch, dota_manager_mod, tmp_path, "dota_cache.json")

    def _build(path: Path):
        client = _client()
        return (
            DOTAManager(poll_interval=30, client=client, cache_path=path),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "dota_cache.json",
        makes_dir=True,
    )
    assert set(data) == legacy_keys


async def test_the_ttt_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape.  Revert ``ttt_manager.py``'s ``load_from_file`` call to
    ``_CACHE_FILE`` and step 3 reddens (the seeded ``last_seen_block``
    watermarks come back); revert the save, or the ``mkdir``, and step 4 or the
    ``makes_dir`` assertion reddens."""
    _forbid_home(monkeypatch)
    monkeypatch.setattr(ttt_manager_mod, "PriceClient", _TTTFakePrice)
    monkeypatch.setattr(ttt_manager_mod, "TTTClient", _NoNetworkClient)

    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_DIR", legacy_dir)
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_FILE", legacy_dir / "ttt.json")
    legacy = TTTManager(poll_interval=30)
    legacy.client = _TTTFakeClient()
    legacy_keys = set(await legacy.fetch_and_compute())
    assert legacy_keys, "the reference run produced no keys at all"

    poison = _poison_path(monkeypatch, ttt_manager_mod, tmp_path, "ttt_cache.json")

    def _build(path: Path):
        client = _TTTFakeClient()
        return (
            TTTManager(poll_interval=30, client=client, cache_path=path),
            client,
            None,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        # ``TTTCache`` is an event cache, not a ``SeriesCache``: the scan
        # watermark is what a restored file carries.
        probe=lambda mgr: dict(mgr.cache.last_seen_block),
        poison=poison,
        seam=tmp_path / "seam" / "ttt_cache.json",
        makes_dir=True,
    )
    assert set(data) == legacy_keys


async def test_a_falsy_injected_ocm_client_is_still_the_injected_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``client or OCMClient()`` built a real network client for any falsy
    injected object; the seam reads ``is None`` like the other seven managers
    (whole-branch review Minor 4). Revert the ``or`` and this reddens on the
    identity assert -- the ordinary seam test cannot see it because its fake
    is truthy. Revert the ``if cache_file`` truthiness and the empty-path arm
    reddens: ``cache_file=""`` must NOT fall back to ``~/.maxpane``."""
    _forbid_home(monkeypatch)
    monkeypatch.setattr(ocm_manager_mod, "OCMClient", _NoNetworkClient)

    class _FalsyClient(_NoNetworkClient):
        def __bool__(self) -> bool:
            return False

    fake = _FalsyClient()
    mgr = OCMManager(poll_interval=60, client=fake, cache_file=tmp_path / "c.json")
    assert mgr.client is fake, "a falsy injected client was replaced by a real one"
    assert mgr._cache_file == tmp_path / "c.json"
    monkeypatch.chdir(tmp_path)  # Path("") is the cwd; keep its mkdir inside tmp_path
    empty = OCMManager(poll_interval=60, client=_FalsyClient(), cache_file="")
    assert empty._cache_file != ocm_manager_mod._CACHE_FILE, (
        "an empty cache_file fell back to the module default"
    )


async def test_the_ocm_manager_seam_serves_the_same_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ocm already had ``client=`` and ``cache_file=``; WP-B adds ``cache=``.
    Revert ``ocm_manager.py``'s ``load_from_file`` call to ``_CACHE_FILE`` and
    step 3 reddens; revert the save and step 4 reddens; drop ``cache=`` and the
    ``mgr.cache is`` assertion reddens."""
    _forbid_home(monkeypatch)
    monkeypatch.setattr(ocm_manager_mod, "OCMClient", _NoNetworkClient)

    def _snaps() -> list[Any]:
        return [_ocm_snap(fetched_at=time.time())]

    legacy = OCMManager(
        poll_interval=60,
        client=_OCMStubClient(_snaps()),
        cache_file=tmp_path / "legacy_ocm.json",
    )
    legacy_keys = set(await legacy.fetch_and_compute())
    assert legacy_keys, "the reference run produced no keys at all"

    poison = _poison_path(monkeypatch, ocm_manager_mod, tmp_path, "ocm_cache.json")

    def _build(path: Path):
        client = _OCMStubClient(_snaps())
        cache = ocm_manager_mod.OCMCache(max_history=120)
        return (
            OCMManager(
                poll_interval=60, client=client, cache=cache, cache_file=path
            ),
            client,
            cache,
        )

    _, data = await _assert_cache_path_is_both_halves(
        build=_build,
        probe=_history_size,
        poison=poison,
        seam=tmp_path / "seam" / "ocm_cache.json",
        makes_dir=True,  # OCMManager has always created its cache file's parent
    )
    assert set(data) == legacy_keys


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
    """The *log pool* arm of the ban, which is WP-B's new seam.

    Delete ``*self._log_rpcs`` from the ``for url in [...]`` ban loop in
    ``TalismansClient.__init__`` and this reddens.  The ``primary_rpc`` arm and
    the "the table is not empty" check live in
    ``test_rpc_shared.py::test_banned_host_lists_still_raise_at_construction``,
    which WP-B fix round 1 extended to talismans; they are deliberately not
    repeated here.
    """
    banned = next(iter(talismans_client_mod._BANNED_RPC_HOSTS))

    with pytest.raises(ValueError, match="banned RPC host"):
        TalismansClient(log_rpcs=[f"https://{banned}/x"])

    # The shipped defaults must themselves pass the gate, or every dashboard
    # start-up raises.
    default = TalismansClient()
    try:
        assert default._log_rpcs == talismans_client_mod._LOG_RPCS
    finally:
        await default.close()


async def test_the_surf_seat_is_injected_never_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The saved seat reaches ``SurfManager`` only as ``seat=`` -- the
    caller reads ``~/.maxpane/config.toml``, the data layer reads no
    configuration of its own. ``MAXPANE_IMD_SEAT`` was retired 2026-09-21;
    set here it must change nothing. The swarm double raises on any call,
    so construction is provably not a network read either."""
    def _build(**kw: Any) -> SurfManager:
        return SurfManager(
            cache_path=tmp_path / "surf_seam.json",
            client=_SurfFakeClient(),
            pool4_client=_SurfFakePool4Client(),
            swarm_client=_NoNetworkClient(),
            clock=_SurfFakeClock(),
            **kw,
        )

    monkeypatch.setenv("MAXPANE_IMD_SEAT", "1548")
    unset = _build()
    try:
        assert unset._seat_saved is None, "the retired env var must not pick a seat"
        assert not hasattr(unset, "_seat_cursor"), "cursor selection is retired"
    finally:
        await unset.close()

    explicit = _build(seat="463")
    try:
        assert explicit._seat_saved == "463"
    finally:
        await explicit.close()
