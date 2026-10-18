"""App factories must never construct or expose data managers on Textual's thread."""
import threading
from types import SimpleNamespace

import pytest

from maxpane_dashboard import app as app_module
from tests.test_app_startup import MANAGER_ATTRS


FACTORIES = (
    'DataManager', 'FrenPetManager', 'BaseManager', 'CatTownManager',
    'OCMManager', 'DOTAManager', 'TTTManager', 'TalismansManager',
    'SurfManager', 'CuratorManager', 'FWAManager',
)


def test_app_construction_does_not_load_any_manager(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('manager/cache constructed on the UI thread')
    for name in FACTORIES:
        monkeypatch.setattr(app_module, name, forbidden)
    app = app_module.MaxPaneApp(wallet_address='0x' + '1' * 40, seat=420)
    assert all(getattr(app, attr) is not None for attr in MANAGER_ATTRS)


@pytest.mark.asyncio
async def test_all_app_managers_and_shared_frenpet_cache_belong_to_reader(monkeypatch):
    created = []
    closed = []

    class Manager:
        def __init__(self, kind, **kwargs):
            self.kind, self.kwargs = kind, kwargs
            self.cache = SimpleNamespace(history=[])
            self.wallet = kwargs.get('wallet') or None
            self._wallet_address = kwargs.get('wallet_address')
            self.seat = kwargs.get('seat')
            self.seats = (self.seat, None, None, None)
            created.append((self, threading.get_ident()))

        def set_hub_seats(self, seats):
            self.seats = tuple(seats)

        def get_hub_seats(self):
            return self.seats

        def set_seat(self, seat):
            self.seat = seat

        def probe(self):
            return self.kind, self.kwargs, threading.get_ident()

        async def close(self):
            closed.append((self, threading.get_ident()))

    for name in FACTORIES:
        monkeypatch.setattr(app_module, name, lambda _name=name, **kw: Manager(_name, **kw))
    app = app_module.MaxPaneApp(poll_interval=45, surfboard_seats=(420, 7, None, None))
    try:
        # A variant may be the first FrenPet screen opened.
        await app._frenpet_wallet_manager.invoke('probe')
        for attr in MANAGER_ATTRS:
            await getattr(app, attr).invoke('probe')
        assert len(created) == len(MANAGER_ATTRS)
        reader_threads = {ident for _, ident in created}
        assert len(reader_threads) == 1
        assert threading.get_ident() not in reader_threads
        frenpet = [obj for obj, _ in created if obj.kind == 'FrenPetManager']
        assert len(frenpet) == 4
        assert all(obj.cache is frenpet[0].cache for obj in frenpet)
        surf = next(obj for obj, _ in created if obj.kind == 'SurfManager')
        assert surf.seat == 420
        assert surf.seats == (420, 7, None, None)
        assert surf.kwargs['poll_interval'] == 45
    finally:
        await app._reader.close()
    assert {id(obj) for obj, _ in closed} == {id(obj) for obj, _ in created}
    assert {ident for _, ident in closed} == reader_threads
