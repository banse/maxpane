import pytest
from rich.console import Console

from maxpane_dashboard.widgets import address, explorer


WALLET = '0x1234567890abcdef1234567890abcdef12345678'


def test_wallet_link_preserves_copy_and_full_target_with_ens_label():
    text = address.wallet_text(WALLET, label='owner.eth', width=18, explorer=explorer.IMD)
    segments = list(Console().render(text))
    shown = next(s for s in segments if 'owner.eth' in s.text)
    assert shown.style.link == f'https://explorer.imd.fun/wallet/{WALLET}'
    assert explorer.parse_open_action(shown.style.meta['@click']) == (explorer.IMD, 'wallet', WALLET)
    icon = next(s for s in segments if '⧉' in s.text)
    assert icon.style.link is None
    assert WALLET in icon.style.meta['@click']


@pytest.mark.parametrize('value', [WALLET + '\n', WALLET + "');evil()", 'owner.eth', None])
def test_wallet_route_rejects_non_addresses(value):
    assert not explorer.is_valid(explorer.IMD, 'wallet', value)
    with pytest.raises(ValueError):
        explorer.url_for(explorer.IMD, 'wallet', value)


def test_wallet_kind_is_only_available_on_imd():
    for target in (explorer.ETHEREUM, explorer.BASE, explorer.SITES):
        assert not explorer.is_valid(target, 'wallet', WALLET)
