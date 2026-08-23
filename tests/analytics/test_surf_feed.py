"""Threading rules for the announce channel, ported from 0xTXT.

The channel is permissionless, so every rule here has to survive a hostile
or degenerate input: a reply with no post before it, an answer to nobody, a
malformed timestamp, two items in the same second.
"""
import json
from pathlib import Path

from maxpane_dashboard.analytics.surf_feed import build_threads

_ANN = "0x200e710acaa6a93bbc77146026328c40f1d60fb1"
_ASKER = "0x6eacf11c0000000000000000000000000000dead"
_OTHER = "0xef5212b20000000000000000000000000000beef"


def _item(ts, kind, tx, frm=_ANN, to=_ANN, text="x"):
    return {"ts": ts, "kind": kind, "from_addr": frm, "to_addr": to,
            "from_label": None, "text": text, "tx_hash": tx}


def test_a_reply_nests_under_the_post_that_preceded_it():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "reply", "0xq", frm=_ASKER, to=_ANN),
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xpost"]
    assert [(r["item"]["tx_hash"], r["depth"]) for r in threads[0]["replies"]] == [("0xq", 1)]


def test_an_answer_nests_under_the_reply_from_the_address_it_was_sent_to():
    """The rule that makes this a reply-to-a-reply rather than a second reply.

    0xTXT's `inboundByAuthor`: an answer's parent is the most recent inbound
    reply from the address the answer is addressed to.
    """
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "reply", "0xq1", frm=_OTHER, to=_ANN),
        _item(300, "reply", "0xq2", frm=_ASKER, to=_ANN),
        _item(400, "answer", "0xa", frm=_ANN, to=_ASKER),
    ])
    rows = {r["item"]["tx_hash"]: r for r in threads[0]["replies"]}
    assert rows["0xa"]["depth"] == 2
    assert rows["0xa"]["parent_tx_hash"] == "0xq2"   # _ASKER's, not _OTHER's


def test_an_answer_to_nobody_falls_back_to_the_root_at_depth_one():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(400, "answer", "0xa", frm=_ANN, to=_ASKER),
    ])
    row = threads[0]["replies"][0]
    assert row["depth"] == 1 and row["parent_tx_hash"] == "0xpost"


def test_a_reply_with_no_post_before_it_stays_top_level():
    """The channel has these -- replies that predate the first self-post.

    Dropping them would be silent data loss on a permissionless feed.
    """
    threads = build_threads([_item(50, "reply", "0xorphan", frm=_ASKER, to=_ANN)])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xorphan"]
    assert threads[0]["depth"] == 0 and threads[0]["replies"] == []


def test_actions_and_funds_are_never_threaded():
    """R3: the brief's own version of this test asserted a conditional
    *expression*, not a conditional *assertion* -- `assert X if cond else
    True` evaluates to `assert True` whenever `cond` is false, which passes
    no matter what `X` is. Replaced with real assertions on all three rows,
    looked up by `tx_hash` rather than by index so the test does not depend
    on an ordering it is not testing.
    """
    threads = build_threads([
        _item(100, "self", "0xpost"),
        _item(200, "action", "0xact", frm=_ANN, to=_OTHER),
        _item(300, "fund", "0xfund", frm=_OTHER, to=_ANN),
    ])
    assert {t["item"]["tx_hash"] for t in threads} == {"0xpost", "0xact", "0xfund"}
    by_hash = {t["item"]["tx_hash"]: t for t in threads}
    assert by_hash["0xpost"]["replies"] == []
    assert by_hash["0xact"]["depth"] == 0 and by_hash["0xact"]["replies"] == []
    assert by_hash["0xfund"]["depth"] == 0 and by_hash["0xfund"]["replies"] == []


def test_roots_come_back_newest_first_and_replies_oldest_first():
    threads = build_threads([
        _item(100, "self", "0xold"),
        _item(150, "reply", "0xr1", frm=_ASKER, to=_ANN),
        _item(160, "reply", "0xr2", frm=_OTHER, to=_ANN),
        _item(300, "self", "0xnew"),
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xnew", "0xold"]
    old = [t for t in threads if t["item"]["tx_hash"] == "0xold"][0]
    assert [r["item"]["tx_hash"] for r in old["replies"]] == ["0xr1", "0xr2"]


def test_equal_timestamps_break_on_tx_hash_not_on_input_order():
    """`ts` alone is not a total order and `nonce` is per-sender.

    Two items in the same second must thread identically however the caller
    happened to order them, or the panel reshuffles between refreshes.
    """
    a = _item(100, "self", "0xaaa")
    b = _item(100, "self", "0xbbb")
    assert [t["item"]["tx_hash"] for t in build_threads([a, b])] == \
           [t["item"]["tx_hash"] for t in build_threads([b, a])]


def test_a_malformed_item_is_skipped_and_never_raises():
    threads = build_threads([
        _item(100, "self", "0xpost"),
        {"ts": "not-a-number", "kind": "reply"},
        None,
        "not a dict",
    ])
    assert [t["item"]["tx_hash"] for t in threads] == ["0xpost"]


def test_the_captured_channel_threads_the_way_the_screen_shows_it():
    raw = json.loads(
        (Path(__file__).parent.parent / "fixtures/surf/feed/threaded_channel.json").read_text()
    )
    threads = build_threads(raw["items"])
    assert any(
        r["depth"] == 2 for t in threads for r in t["replies"]
    ), "the capture contains an answer to a reply; threading must find it"


def test_an_inbound_reply_does_not_leak_across_a_new_root():
    """Fix round 1: `inbound_by_author` must reset on every `self`.

    Root A gets a reply from ASKER. Root B opens. An answer to ASKER must
    not resolve to root A's reply -- that reply lives in a different
    thread's `replies` list, so nesting the answer at depth 2 under root B
    with a `parent_tx_hash` root B never contains is wrong linkage: no
    crash, nothing dropped, but the screen would show a nested reply whose
    parent is nowhere in its own thread, while root A's real question
    looks unanswered.
    """
    threads = build_threads([
        _item(100, "self", "0xrootA"),
        _item(150, "reply", "0xqA", frm=_ASKER, to=_ANN),
        _item(200, "self", "0xrootB"),
        _item(250, "answer", "0xa", frm=_ANN, to=_ASKER),
    ])
    by_hash = {t["item"]["tx_hash"]: t for t in threads}
    root_b_reply_hashes = {r["item"]["tx_hash"] for r in by_hash["0xrootB"]["replies"]}
    assert "0xa" in root_b_reply_hashes
    answer_row = next(r for r in by_hash["0xrootB"]["replies"] if r["item"]["tx_hash"] == "0xa")
    # No inbound reply exists in root B's own thread, so this must fall
    # back to depth 1 under root B -- not depth 2 pointing at 0xqA, which
    # lives in root A.
    assert answer_row["depth"] == 1
    assert answer_row["parent_tx_hash"] == "0xrootB"
    assert all(r["item"]["tx_hash"] != "0xa" for r in by_hash["0xrootA"]["replies"])
