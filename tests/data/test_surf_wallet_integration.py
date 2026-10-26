"""The retained child borrows the Boardroom's existing clients."""
from tests.data.test_surf_manager import _manager

async def test_parent_owns_wallet_child_and_closes_it_before_borrowed_clients(tmp_path, monkeypatch):
    monkeypatch.setattr('pathlib.Path.home',lambda:tmp_path)
    parent=_manager(tmp_path)
    closed=[]
    class Chain:
        async def close(self): closed.append('chain')
    parent._launch_rpc_clients={8453:Chain(),4663:Chain()}
    wallet='0x'+'1'*40
    child=parent.wallet_manager(wallet)
    assert child is parent.wallet_manager('0x'+'2'*40)
    assert child.get_snapshot()['wallet_snapshot']['wallet']==wallet
    assert child.client.swarm is parent.swarm_client
    assert child.evidence.clients[1] is parent.client
    close=child.close
    async def close_child():
        assert not closed and not parent.client.closed
        await close(); closed.append('wallet')
    child.close=close_child
    await parent.close()
    assert closed==['wallet','chain','chain'] and parent.client.closed
