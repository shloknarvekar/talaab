"""Alerts: only transitions are sent, keyed by location; replay regions never alert; text has no invented numbers."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from synth_measurements import generate  # noqa: E402

from api import store  # noqa: E402
from jobs import recompute  # noqa: E402
from jobs.alerts import alert_state, alert_timeline, format_alert, new_alerts  # noqa: E402
from logic.guard import invented_numbers  # noqa: E402


def pond(pid, lat, status, flag=None, dry_by=None):
    return {"id": pid, "lat": lat, "lon": 76.5, "place": f"near Village {pid}", "status": status, "flag": flag,
            "areaNowHa": 4.2, "maxAreaHa": 20.0, "shrinkVsNeighbours": 2.4 if flag else 1.0,
            "dryBy": dry_by or ({"earliest": "2026-10-13", "likely": "2026-10-16", "latest": "2026-10-23"} if status == "critical" else None)}


def snap(*ponds, as_of="2026-10-09"):
    return {"asOf": as_of, "ponds": list(ponds)}


def test_only_new_transitions_alert():
    first = snap(pond("P001", 18.36, "critical"), pond("P002", 18.37, "watch"), pond("P003", 18.38, "ok"))
    alerts = new_alerts({}, first)
    assert [(a["id"], a["reason"]) for a in alerts] == [("P001", "critical")]
    # next run: P001 still critical (no repeat), P002 now critical and flagged, P003 dried
    second = snap(pond("P001", 18.36, "critical"), pond("P002", 18.37, "critical", "faster-than-sun"), pond("P003", 18.38, "dry"))
    alerts = new_alerts(alert_state(first, None, new_alerts({}, first)), second)
    assert [(a["id"], a["reason"]) for a in alerts] == [("P003", "dry"), ("P002", "critical"), ("P002", "flag")]
    # a critical pond that dries is reported once as dry, never again as critical
    third = snap(pond("P001", 18.36, "dry"), pond("P002", 18.37, "critical", "faster-than-sun"), pond("P003", 18.38, "dry"))
    state2 = alert_state(second, alert_state(first, None, new_alerts({}, first)), alerts)
    assert [(a["id"], a["reason"]) for a in new_alerts(state2, third)] == [("P001", "dry")]


def test_district_email_lists_the_most_urgent_20():
    ponds = [pond(f"P{i:03d}", 18.0 + i / 100, "dry") for i in range(1, 4)] + \
            [pond(f"P{i:03d}", 18.0 + i / 100, "critical") for i in range(4, 31)]
    alerts = new_alerts({}, snap(*ponds))
    subject, body = format_alert("Latur district (live, 2026)", "2026-10-09", alerts, "x")
    assert subject.startswith("Talaab: 30 ponds need action")  # the subject counts everything
    assert "P001" in body and "P020" in body and "P021" not in body  # dry first, then critical, by id
    assert "...and 10 more alerts (10 more ponds): see the map." in body


def test_state_is_keyed_by_location_not_id():
    before = snap(pond("P001", 18.36, "critical"))
    renumbered = snap(pond("P004", 18.36, "critical"))  # same pond, new id after re-cleaning
    assert new_alerts(alert_state(before), renumbered) == []


def test_alert_text_uses_only_snapshot_numbers():
    s = snap(pond("P001", 18.36, "critical"), pond("P002", 18.37, "watch", "faster-than-sun"))
    subject, body = format_alert("Latur (live, 2026)", s["asOf"], new_alerts({}, s), "https://example.org")
    assert subject == "Talaab: 2 ponds need action in Latur (live, 2026)" and len(subject) <= 100
    one, _ = format_alert("Latur", s["asOf"], new_alerts({}, snap(pond("P001", 18.36, "critical"))), "x")
    assert one == "Talaab: 1 pond needs action in Latur"
    assert "P001 (near Village P001) turned CRITICAL" in body and "16 Oct 2026" in body
    assert "2.4x faster" in body and "not proof" in body and "https://example.org" in body
    # only snapshot numbers plus the fixed rules (30 days, 5%) may appear
    assert invented_numbers(body.replace("https://example.org", ""), s) <= {"30", "5"}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    for region in ("latur-2024-synthetic", "latur-2026", "latur-district-2026"):
        d = tmp_path / region
        d.mkdir()
        (d / "measurements.json").write_text(json.dumps(generate()), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    yield tmp_path
    store.clear_cache()


def fake_weather(lat, lon, today):
    obs = [{"date": (today - timedelta(days=i)).isoformat(), "et0": 6.0, "precip": 0.0} for i in range(60)]
    return obs, [{"date": (today + timedelta(days=i)).isoformat(), "et0": 7.0, "precip": 0.0} for i in range(1, 17)]


def test_live_recompute_sends_once_then_stays_quiet(data_dir):
    sent = []
    publish = lambda subject, body: sent.append((subject, body)) or True  # noqa: E731
    today = date(2024, 6, 16)
    first = recompute.recompute_region("latur-district-2026", today, fetch_weather=fake_weather, write_table=lambda r, s: 0, publish=publish)
    assert first["alertsSent"] > 0 and len(sent) == 1
    log = json.loads((data_dir / "latur-district-2026" / "alerts" / f"{today}.json").read_text(encoding="utf-8"))
    assert log["delivered"] is True and log["alerts"]
    again = recompute.recompute_region("latur-district-2026", today, fetch_weather=fake_weather, write_table=lambda r, s: 0, publish=publish)
    assert again["alertsSent"] == 0 and len(sent) == 1  # nothing new: no second email


def test_live_box_inside_the_district_never_emails(data_dir):
    # the live district covers the box, so the box is shown on the site but never emails (no duplicates)
    sent = []
    out = recompute.recompute_region("latur-2026", date(2024, 6, 16), fetch_weather=fake_weather,
                                     write_table=lambda r, s: 0, publish=lambda s, b: sent.append(s) or True)
    assert out["ponds"] > 0 and out["status"].get("critical", 0) + out["status"].get("dry", 0) > 0  # there was something to send
    assert out["alertsSent"] == 0 and sent == []


def test_replay_regions_never_alert(data_dir):
    sent = []
    out = recompute.recompute_region("latur-2024-synthetic", date(2024, 6, 16), write_table=lambda r, s: 0,
                                     publish=lambda s, b: sent.append(s) or True)
    assert out["alertsSent"] == 0 and sent == []
    files = sorted(f.name for f in (data_dir / "latur-2024-synthetic" / "alerts").iterdir())
    assert files == ["timeline.json"]  # only the simulated timeline: no send state, no sent-alert logs


def test_without_a_topic_nothing_is_published(monkeypatch):
    monkeypatch.delenv("ALERT_TOPIC_ARN", raising=False)
    assert recompute.sns_publish("s", "b") is False


def test_replay_timeline_is_simulated_and_ordered(data_dir):
    from api import handler

    recompute.recompute_region("latur-2024-synthetic", date(2024, 6, 16), write_table=lambda r, s: 0,
                               publish=lambda s, b: pytest.fail("replay must not publish"))
    store.clear_cache()
    r = handler.lambda_handler({"routeKey": "GET /alerts", "queryStringParameters": {"region": "latur-2024-synthetic"}}, None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and body["simulated"] is True and body["events"]
    dates = [e["asOf"] for e in body["events"]]
    assert dates == sorted(dates)
    reasons = {a["reason"] for e in body["events"] for a in e["alerts"]}
    assert {"critical", "dry", "flag"} <= reasons  # the synthetic season has all three
    assert handler.lambda_handler({"routeKey": "GET /alerts", "queryStringParameters": {"region": "latur-2024"}}, None)["statusCode"] == 404


def test_live_timeline_lists_sent_alerts(data_dir):
    recompute.recompute_region("latur-district-2026", date(2024, 6, 16), fetch_weather=fake_weather, write_table=lambda r, s: 0,
                               publish=lambda s, b: True)
    timeline = json.loads((data_dir / "latur-district-2026" / "alerts" / "timeline.json").read_text(encoding="utf-8"))
    assert timeline["simulated"] is False and timeline["events"][0]["delivered"] is True


def test_flickering_tiny_pond_alerts_dry_only_once():
    seq = [snap(pond("P011", 18.40, s), as_of=f"2024-03-{d:02d}") for s, d in
           (("watch", 1), ("dry", 6), ("ok", 11), ("dry", 16), ("dry", 21))]
    events = alert_timeline(seq, "Latur", "x")
    assert [(e["asOf"], [a["reason"] for a in e["alerts"]]) for e in events] == [("2024-03-06", ["dry"])]


def test_unsent_alerts_are_not_remembered():
    s = snap(pond("P001", 18.36, "critical"))
    pending = new_alerts({}, s)
    assert new_alerts(alert_state(s, None, []), s) == []          # status unchanged: no transition
    assert alert_state(s, None, [])["18.36,76.5"]["alerted"] == []  # but nothing recorded as sent
    assert alert_state(s, None, pending)["18.36,76.5"]["alerted"] == ["critical"]
