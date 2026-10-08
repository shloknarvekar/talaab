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
from jobs.alerts import alert_state, format_alert, new_alerts  # noqa: E402
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
    alerts = new_alerts(alert_state(first), second)
    assert [(a["id"], a["reason"]) for a in alerts] == [("P003", "dry"), ("P002", "critical"), ("P002", "flag")]
    # a critical pond that dries is reported once as dry, never again as critical
    third = snap(pond("P001", 18.36, "dry"), pond("P002", 18.37, "critical", "faster-than-sun"), pond("P003", 18.38, "dry"))
    assert [(a["id"], a["reason"]) for a in new_alerts(alert_state(second), third)] == [("P001", "dry")]


def test_state_is_keyed_by_location_not_id():
    before = snap(pond("P001", 18.36, "critical"))
    renumbered = snap(pond("P004", 18.36, "critical"))  # same pond, new id after re-cleaning
    assert new_alerts(alert_state(before), renumbered) == []


def test_alert_text_uses_only_snapshot_numbers():
    s = snap(pond("P001", 18.36, "critical"), pond("P002", 18.37, "watch", "faster-than-sun"))
    subject, body = format_alert("Latur (live, 2026)", s["asOf"], new_alerts({}, s), "https://example.org")
    assert subject == "Talaab: 2 ponds need action in Latur (live, 2026)" and len(subject) <= 100
    assert "P001 (near Village P001) turned CRITICAL" in body and "16 Oct 2026" in body
    assert "2.4x faster" in body and "not proof" in body and "https://example.org" in body
    # only snapshot numbers plus the fixed rules (30 days, 5%) may appear
    assert invented_numbers(body.replace("https://example.org", ""), s) <= {"30", "5"}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    for region in ("latur-2024-synthetic", "latur-2026"):
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
    first = recompute.recompute_region("latur-2026", today, fetch_weather=fake_weather, write_table=lambda r, s: 0, publish=publish)
    assert first["alertsSent"] > 0 and len(sent) == 1
    log = json.loads((data_dir / "latur-2026" / "alerts" / f"{today}.json").read_text(encoding="utf-8"))
    assert log["delivered"] is True and log["alerts"]
    again = recompute.recompute_region("latur-2026", today, fetch_weather=fake_weather, write_table=lambda r, s: 0, publish=publish)
    assert again["alertsSent"] == 0 and len(sent) == 1  # nothing new: no second email


def test_replay_regions_never_alert(data_dir):
    sent = []
    out = recompute.recompute_region("latur-2024-synthetic", date(2024, 6, 16), write_table=lambda r, s: 0,
                                     publish=lambda s, b: sent.append(s) or True)
    assert out["alertsSent"] == 0 and sent == []
    assert not (data_dir / "latur-2024-synthetic" / "alerts").exists()


def test_without_a_topic_nothing_is_published(monkeypatch):
    monkeypatch.delenv("ALERT_TOPIC_ARN", raising=False)
    assert recompute.sns_publish("s", "b") is False
