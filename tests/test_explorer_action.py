"""Explorer links open the page, and nothing else (refactor programme 2026-09, Branch 4).

A linked address carries ``app.open_explorer(name, kind, value)``;
``ExplorerLinkMixin.action_open_explorer`` re-validates all three against the
allowlists, rebuilds the URL from the parts that passed and hands it to
``App.open_url``. Zero browsers: every harness here mixes in
``address_probe.LinkRecorder`` (records ``open_url``, opens nothing), and
``tests/conftest.py`` refuses ``webbrowser.open`` suite-wide.

Mutation-checked (2026-09-20):
* ``action_open_explorer`` opening ``f"https://{name}/{kind}/{value}"`` from
  the action's own parts, validation skipped -> the foreign-name case of
  ``test_an_invalid_action_opens_nothing_and_says_unavailable`` fails (a
  ``https://blockscout/…`` URL was opened), 16 of 24 here in all;
* ``address_text`` never stylising the shown span -> the address-click test
  and the separating-space test here fail, plus three in ``test_address.py``;
* ``address_prose`` appending the address with a stray style ->
  ``test_address.py::test_explorer_none_renders_byte_and_style_identically_…``
  fails and nothing else does.
"""

from __future__ import annotations

import webbrowser

import pytest
from rich.text import Text
from textual.app import App
from textual.widgets import Static

from maxpane_dashboard import explorer_action as EA
from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.widgets import explorer as X
from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text, hash_text, job_text, site_text
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.widgets.address_probe import CopyRecorder, LinkRecorder, icon_targets, link_targets

ADDR = "0x" + "abcdef0123" * 4
TX = "0x" + "ab" * 32


class _App(LinkRecorder, CopyRecorder, ExplorerLinkMixin, App):
    EXPLORER_MESSAGE_S = 60.0  # the message must still be there when we look

    def compose(self):
        line = Text("who ")
        line.append_text(address_text(ADDR, width=17, explorer=X.ETHEREUM))
        line.append("  tx ")
        line.append_text(hash_text(TX, 17, explorer=X.BASE))
        yield Static(line, id="s")
        yield StatusBar()


def _message(app) -> str:
    return app.screen.query_one(StatusBar).message


async def test_a_click_on_the_address_text_opens_its_page_and_says_so():
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        cells = [t for t in link_targets(app) if t[2] == "etherscan"]
        assert cells, "the address is linked on screen"
        x, y, name, kind, value, url = cells[0]
        assert (name, kind, value, url) == ("etherscan", "address", ADDR, X.address_url(X.ETHEREUM, ADDR))
        assert x == 4, "the link starts where the address does"
        assert len(cells) == 17, "every cell of the window, no more"
        await pilot.click(offset=(x + 3, y))
        await pilot.pause()
        assert app.opened == [X.address_url(X.ETHEREUM, ADDR)]
        assert app.copied == []
        assert _message(app) == "opened etherscan"


async def test_a_click_on_the_hash_opens_its_tx_page():
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        cells = [t for t in link_targets(app) if t[3] == "tx"]
        assert cells and cells[0][2] == "basescan" and cells[0][5] == X.tx_url(X.BASE, TX)
        assert len(cells) == 17
        await pilot.click(offset=(cells[-1][0], cells[-1][1]))
        await pilot.pause()
        assert app.opened == [X.tx_url(X.BASE, TX)]
        assert _message(app) == "opened basescan"


JOB = "a2cf385f-8c95-46e1-b184-a8fe2f732edb"


class _JobApp(LinkRecorder, CopyRecorder, ExplorerLinkMixin, App):
    EXPLORER_MESSAGE_S = 60.0

    def compose(self):
        yield Static(Text("job ").append_text(job_text(JOB, 8, explorer=X.IMD)), id="s")
        yield StatusBar()


async def test_a_click_on_a_job_id_opens_its_imd_explorer_page():
    """Owner, 2026-09-22: RECORD's job cell opens explorer.imd.fun/jobs/<uuid>."""
    app = _JobApp()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        cells = [t for t in link_targets(app) if t[3] == "job"]
        assert [t[0] for t in cells] == list(range(4, 12))
        await pilot.click(offset=(cells[3][0], cells[3][1]))
        await pilot.pause()
        assert app.opened == [f"https://explorer.imd.fun/jobs/{JOB}"]
        assert app.copied == []
        assert _message(app) == "opened imd"


SITE = "mswap.site.identitymd.eth"


class _SiteApp(LinkRecorder, CopyRecorder, ExplorerLinkMixin, App):
    EXPLORER_MESSAGE_S = 60.0

    def compose(self):
        yield Static(Text("ens ").append_text(site_text(SITE, 33, explorer=X.SITES)), id="s")
        yield StatusBar()


async def test_a_click_on_a_site_name_opens_its_eth_limo_page():
    """Owner, 2026-09-23: SITES' ens cell opens https://<label>.site.identitymd.eth.limo/."""
    app = _SiteApp()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        cells = [t for t in link_targets(app) if t[3] == "site"]
        assert [t[0] for t in cells] == list(range(4, 4 + len(SITE)))
        await pilot.click(offset=(cells[5][0], cells[5][1]))
        await pilot.pause()
        assert app.opened == ["https://mswap.site.identitymd.eth.limo/"]
        assert app.copied == []
        assert _message(app) == "opened sites"


def test_site_text_fits_and_links_only_a_site_name():
    linked = site_text(SITE, 33, explorer=X.SITES)
    assert linked.plain == SITE and COPY_GLYPH not in linked.plain
    assert {span.style.link for span in linked.spans} == {"https://mswap.site.identitymd.eth.limo/"}
    assert site_text(SITE, 10, explorer=X.SITES).plain == "mswap.sit…"
    assert site_text(SITE, 33).spans == [], "no explorer, no link"
    for bad in ("mswap.evil.eth", "a\nb.site.identitymd.eth", "MSWAP.site.identitymd.eth"):
        out = site_text(bad, 33, explorer=X.SITES)
        assert out.spans == [] and "\n" not in out.plain, bad
    assert site_text(None, 33, explorer=X.SITES).plain == "--"
    assert site_text(SITE, 33, explorer=X.IMD).spans == [], "an explorer that serves no site"


async def test_a_click_on_the_glyph_copies_and_opens_nothing():
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        [(x, y, target)] = icon_targets(app)
        assert target == ADDR
        assert not [t for t in link_targets(app) if (t[0], t[1]) == (x, y)], "the glyph is not a link"
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]
        assert app.opened == []
        assert _message(app) == ""


async def test_the_separating_space_is_neither_link_nor_icon():
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        await pilot.pause()
        [(x, y, _)] = icon_targets(app)
        linked = {(t[0], t[1]) for t in link_targets(app)}
        assert (x - 1, y) not in linked and (x - 2, y) in linked


@pytest.mark.parametrize("name,kind,value", [
    ("blockscout", "address", ADDR),          # foreign explorer name
    ("Etherscan", "address", ADDR),           # case is part of the allowlist
    ("etherscan", "nft", ADDR),               # unknown kind
    ("etherscan", "address", ADDR + "\n"),    # malformed value
    ("etherscan", "address", ADDR[:-1]),
    ("etherscan", "address", TX),             # a hash where an address is claimed
    ("etherscan", "tx", ADDR),                # an address where a hash is claimed
    ("etherscan", "address", "https://evil.example"),
    (None, "address", ADDR),
    ("etherscan", None, ADDR),
    ("etherscan", "address", None),
    (X.ETHEREUM, "address", ADDR),            # the object, not its name: not what an action carries
    ("imd", "address", ADDR),                 # the IMD explorer serves jobs only
    ("etherscan", "job", "a2cf385f-8c95-46e1-b184-a8fe2f732edb"),  # a job is not a chain page
    ("imd", "job", "A2CF385F-8C95-46E1-B184-A8FE2F732EDB"),        # canonical lower case only
    ("imd", "job", "a2cf385f-8c95-46e1-b184-a8fe2f732edb/../x"),
])
async def test_an_invalid_action_opens_nothing_and_says_unavailable(name, kind, value):
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        app.action_open_explorer(name, kind, value)
        await pilot.pause()
        assert app.opened == []
        assert _message(app) == EA.UNAVAILABLE == "explorer unavailable"


async def test_the_url_is_rebuilt_from_the_allowlist_never_from_the_caller():
    app = _App()
    async with app.run_test(size=(80, 6)) as pilot:
        app.action_open_explorer("sepolia", "tx", TX)
        await pilot.pause()
        assert app.opened == [f"https://sepolia.etherscan.io/tx/{TX}"]
        assert _message(app) == "opened sepolia"


async def test_a_browser_that_cannot_open_is_unavailable_not_a_crash():
    class _Broken(ExplorerLinkMixin, App):
        EXPLORER_MESSAGE_S = 60.0

        def compose(self):
            yield StatusBar()

        def open_url(self, url, *, new_tab=True):
            raise OSError("no browser")

    app = _Broken()
    async with app.run_test(size=(80, 6)) as pilot:
        app.action_open_explorer("etherscan", "address", ADDR)
        await pilot.pause()
        assert _message(app) == EA.UNAVAILABLE


async def test_a_screen_without_a_status_bar_does_not_raise():
    class _Bare(LinkRecorder, ExplorerLinkMixin, App):
        pass

    app = _Bare()
    async with app.run_test() as pilot:
        app.action_open_explorer("basescan", "address", ADDR)
        await pilot.pause()
        assert app.opened == [X.address_url(X.BASE, ADDR)]


async def test_the_message_clears_itself_but_never_a_newer_one():
    class _Quick(LinkRecorder, ExplorerLinkMixin, App):
        EXPLORER_MESSAGE_S = 0.01

        def compose(self):
            yield StatusBar()

    app = _Quick()
    async with app.run_test(size=(80, 6)) as pilot:
        app.action_open_explorer("etherscan", "address", ADDR)
        assert _message(app) == "opened etherscan"
        for _ in range(50):  # bounded: an observable state, not the wall clock
            await pilot.pause(0.01)
            if _message(app) == "":
                break
        assert _message(app) == ""
        app.action_open_explorer("etherscan", "address", ADDR)
        app.screen.query_one(StatusBar).set_message("exporting…")
        for _ in range(5):
            await pilot.pause(0.01)
        assert _message(app) == "exporting…", "a newer message is never cleared by an older poster"


# -- the suite never opens a browser (PRD §7 E8) ---------------------------------------


def test_the_suite_forbids_the_real_browser():
    with pytest.raises(AssertionError, match="real browser"):
        webbrowser.open("https://example.invalid/")


async def test_textuals_own_open_url_reaches_the_guard_under_run_test():
    """Proves the guard sits where Textual goes: an app *without* the recorder
    calling ``App.open_url`` under ``run_test`` is stopped by the fixture."""
    app = App()
    async with app.run_test():
        with pytest.raises(AssertionError, match="real browser"):
            app.open_url("https://example.invalid/")


# -- the real app -------------------------------------------------------------------------


def test_the_real_app_mixes_the_explorer_action_in_ahead_of_app():
    assert MaxPaneApp.action_open_explorer is ExplorerLinkMixin.action_open_explorer
    mro = MaxPaneApp.__mro__
    assert mro.index(CopyAddressMixin) < mro.index(ExplorerLinkMixin) < mro.index(App)


def test_the_two_mixins_share_one_status_poster():
    """One owner for the clear-only-your-own rule (CLAUDE.md reuse)."""
    import ast
    import inspect

    from maxpane_dashboard import copy_action, status_message

    for module in (copy_action, EA):
        tree = ast.parse(inspect.getsource(module))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "post_status_message" in names, module.__name__
        assert "StatusBar" not in names, f"{module.__name__} posts through status_message, not on its own"
    assert status_message.post_status_message is copy_action.post_status_message is EA.post_status_message
