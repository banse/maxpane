"""The news hero projects existing cache snapshots without fetching anything."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_news_hero as hero


@pytest.fixture
def snapshot():
    return dict(
        data={"sig_post_state": "fired", "sig_thread_state": "watch", "sig_gate_state": "ok",
              "price_series": [[980, 8], [990, 9]]},
        channel={"items": [dict(kind="self", ts=970, text="official"),
                            dict(kind="reply", ts=980, text="community"),
                            dict(kind="answer", ts=999, text="official answer")]},
        activity={"rows": [dict(ts=990, wallet_label="dev", kind="deploy")]},
        market={"imd_price_usd": 9, "imd_change_24h_pct": -2.5, "eth_usd": 2000},
        launchpad={}, boards={"nft_holders": 400, "nft_written": 1, "nft_transfers_24h": 0.0},
        sources={name: {"state": "ok", "read_ts": 990.0}
                 for name in ("channel", "activity", "market", "nft", "chain", "logs", "pad", "swarm")},
        signal_read_ts=995.0, poll_interval=30, wallet_count=2, now=1000.0,
    )


def test_contract_and_same_record_preview_ages(snapshot):
    from maxpane_dashboard.data.surf_models import SURF_KEYS, SURF_NEWS_WIDGET_SIGNATURES
    assert "surf_news_hero" in SURF_KEYS
    assert SURF_NEWS_WIDGET_SIGNATURES == {"SurfNewsHero": {"surf_news_hero": "surf_news_hero"}}
    result = hero.project(**snapshot)
    assert set(result) == {"announcement", "reply", "signals", "activity", "market", "boards"}
    assert result["announcement"] == dict(state="ok", read_ts=990, text="official", age_s=30)
    assert result["reply"] == dict(state="ok", read_ts=990, text="community", age_s=20)
    assert result["signals"] == dict(state="ok", read_ts=995, fired=1, watch=1, quiet=1, known=3, total=11)
    assert result["activity"]["rows"] == [dict(age_s=10, wallet_label="dev", kind="deploy")]
    assert result["activity"]["wallet_count"] == 2
    assert result["market"] == dict(state="ok", read_ts=990, price_usd=9, change_24h_pct=-2.5, points=[8.0, 9.0])
    assert result["boards"] == dict(state="ok", read_ts=990, holders=400, written=1, moves_24h=0)


def test_projected_sections_and_activity_rows_match_frozen_model_fields(snapshot):
    from maxpane_dashboard.data.surf_models import SURF_NEWS_HERO_FIELDS, SURF_NEWS_ACTIVITY_FIELDS
    result = hero.project(**snapshot)
    assert set(SURF_NEWS_HERO_FIELDS) == set(result)
    for name, fields in SURF_NEWS_HERO_FIELDS.items():
        assert set(fields) == set(result[name])
        assert len(fields) == len(set(fields))
    assert SURF_NEWS_ACTIVITY_FIELDS == ("age_s", "wallet_label", "kind")
    assert all(set(row) == set(SURF_NEWS_ACTIVITY_FIELDS) for row in result["activity"]["rows"])


def test_empty_is_distinct_from_unread_and_unknown_is_not_quiet(snapshot):
    snapshot.update(channel={"items": []}, activity={"rows": []}, data={})
    result = hero.project(**snapshot)
    assert result["announcement"]["state"] == result["reply"]["state"] == "ok"
    assert result["announcement"]["text"] is result["reply"]["text"] is None
    assert result["activity"]["rows"] == []
    assert result["signals"]["known"] == result["signals"]["quiet"] == 0
    assert result["signals"]["state"] == "unavailable"
    snapshot.update(channel=None, activity=None)
    result = hero.project(**snapshot)
    assert result["announcement"]["state"] == result["reply"]["state"] == "unavailable"
    assert result["activity"]["rows"] is None
    assert result["activity"]["state"] == "unavailable"


def test_projection_validates_persisted_rows_numbers_and_series(snapshot):
    before = deepcopy(snapshot)
    snapshot["channel"]["items"] += [None, {"kind": "self", "ts": True, "text": "bad"},
                                      {"kind": "self", "ts": 1001, "text": "future"},
                                      {"kind": "reply", "ts": 999, "text": 4}]
    snapshot["activity"]["rows"] += [None, dict(ts=999, wallet_label="dev", kind=[]),
                                       dict(ts=999, wallet_label="outsider", kind="deploy")]
    snapshot["data"]["price_series"] += [None, [990, True], [990, float("nan")], [2000, 50], [990, -1]]
    snapshot["boards"].update(nft_holders=True, nft_written=-2)
    snapshot["market"]["imd_change_24h_pct"] = float("inf")
    result = hero.project(**snapshot)
    assert result["announcement"]["text"] == "official"
    assert result["reply"]["text"] == "community"
    assert result["activity"]["rows"] == [dict(age_s=10, wallet_label="dev", kind="deploy")]
    assert result["market"]["points"] == [8, 9]
    assert result["market"]["change_24h_pct"] is None
    assert result["boards"]["holders"] is result["boards"]["written"] is None
    assert result["boards"]["moves_24h"] == 0
    assert before["channel"]["items"] == snapshot["channel"]["items"][:3]


def test_latest_preview_and_activity_are_sorted_and_bounded(snapshot):
    snapshot["channel"]["items"] = [dict(kind="reply", ts=999-i, text=f"reply {i}") for i in range(30)] + [dict(kind="self", ts=900, text="old official")]
    snapshot["activity"]["rows"] = [dict(ts=980+i, wallet_label="ops", kind=f"call{i}") for i in range(10)]
    result = hero.project(**snapshot)
    assert result["announcement"]["text"] == "old official"
    assert result["announcement"]["age_s"] == 100
    assert result["reply"]["text"] == "reply 0"
    assert [row["kind"] for row in result["activity"]["rows"]] == ["call9", "call8", "call7"]
    assert result["activity"]["wallet_count"] == 2


def test_chain_price_uses_its_own_clock_and_fallback_only_needs_market(snapshot):
    snapshot["launchpad"]["sqrt_price_x96"] = 2**96
    snapshot["sources"]["pad"] = dict(state="stale", read_ts=800)
    snapshot["data"]["imd_price_usd"] = 123  # older full-cycle output is not the captured slot
    result = hero.project(**snapshot)["market"]
    assert result["price_usd"] == 2000
    assert result["read_ts"] == 800
    assert result["state"] == "stale"
    snapshot["launchpad"]["sqrt_price_x96"] = "bad cache value"
    result = hero.project(**snapshot)["market"]
    assert result["price_usd"] == 9
    assert result["read_ts"] == 990
    assert result["state"] == "ok"


def test_zero_usd_conversion_preserves_native_chain_price_selection(snapshot):
    snapshot["launchpad"]["sqrt_price_x96"] = 2**96
    snapshot["market"]["eth_usd"] = 0
    snapshot["sources"]["pad"] = dict(state="ok", read_ts=900)
    result = hero.project(**snapshot)["market"]
    assert result["price_usd"] == 0
    assert result["state"] == "ok"
    assert result["read_ts"] == 900


def test_known_detector_freshness_ignores_unrelated_sources(snapshot):
    snapshot["sources"]["nft"] = dict(state="stale", read_ts=100)
    snapshot["sources"]["market"] = dict(state="unavailable", read_ts=None)
    snapshot["sources"]["swarm"] = dict(state="stale", read_ts=100)
    assert hero.project(**snapshot)["signals"]["state"] == "ok"
    snapshot["sources"]["channel"] = dict(state="stale", read_ts=500)
    assert hero.project(**snapshot)["signals"]["state"] == "stale"
    snapshot["sources"]["channel"] = dict(state="ok", read_ts=990)
    snapshot["now"] = 1040
    result = hero.project(**snapshot)["signals"]
    assert result["state"] == "stale"
    assert result["read_ts"] == 995


@pytest.mark.parametrize("read_ts,failed,expected", [(990, False, "ok"), (900, False, "stale"), (990, True, "stale"), (None, False, "unavailable"), (1001, False, "unavailable"), (True, False, "unavailable")])
def test_source_read_clocks_never_become_projection_time(read_ts, failed, expected):
    source = hero.source(read_ts, now=1000, ttl=90, failed=failed)
    assert source["state"] == expected
    assert source["read_ts"] == (None if expected == "unavailable" else read_ts)
