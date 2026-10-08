import pytest

from logic.flags import FLAG, faster_than_sun, relative_shrink_rate, sun_share_mm


def pond(pid, slope, area, status="watch"):
    return {"id": pid, "slopeHaPerDay": slope, "maxAreaHa": area, "status": status}


def test_relative_rate():
    assert relative_shrink_rate(-0.5, 50.0) == pytest.approx(0.01)
    with pytest.raises(ValueError):
        relative_shrink_rate(-0.5, 0)


def test_three_times_faster_pond_is_flagged():
    # neighbours all lose 0.5%/day; P004 loses 1.5%/day under the same sun
    ponds = [
        pond("P001", -0.50, 100.0),
        pond("P002", -0.20, 40.0),
        pond("P003", -0.10, 20.0),
        pond("P004", -0.45, 30.0),
    ]
    out = faster_than_sun(ponds)
    assert out["P004"]["shrinkVsNeighbours"] == pytest.approx(3.0)
    assert out["P004"]["flag"] == FLAG
    for pid in ("P001", "P002", "P003"):
        assert out[pid]["flag"] is None
        assert out[pid]["shrinkVsNeighbours"] == pytest.approx(1.0)


def test_small_pond_not_flagged_even_if_fast():
    ponds = [pond("P001", -0.5, 100.0), pond("P002", -0.2, 40.0), pond("P003", -0.06, 1.5)]
    out = faster_than_sun(ponds)
    assert out["P003"]["shrinkVsNeighbours"] >= 2
    assert out["P003"]["flag"] is None


def test_dry_ponds_excluded_from_median_and_not_flagged():
    ponds = [
        pond("P001", -0.5, 100.0),
        pond("P002", -0.2, 40.0),
        pond("P003", -0.4, 20.0),
        pond("P009", -5.0, 10.0, status="dry"),
    ]
    out = faster_than_sun(ponds)
    # median r of non-dry ponds = median(0.005, 0.005, 0.02) = 0.005; dry P009 (0.5/day) ignored
    assert out["P003"]["shrinkVsNeighbours"] == pytest.approx(4.0)
    assert out["P003"]["flag"] == FLAG
    assert out["P009"] == {"shrinkVsNeighbours": None, "flag": None}


def test_unfitted_ponds_and_non_shrinking_region():
    ponds = [pond("P001", None, 50.0, "unknown"), pond("P002", 0.1, 40.0, "ok"), pond("P003", 0.0, 20.0, "ok")]
    out = faster_than_sun(ponds)
    assert all(v == {"shrinkVsNeighbours": None, "flag": None} for v in out.values())


def test_sun_share():
    et0 = [{"date": f"2024-03-{d:02d}", "et0": 5.0} for d in range(1, 32)]
    et0.append({"date": "2024-04-01", "et0": None})
    assert sun_share_mm(et0, "2024-03-01", "2024-03-10") == 50.0
    assert sun_share_mm(et0, "2024-03-25", "2024-04-05") == 35.0


def test_stable_tanks_do_not_drag_the_baseline_down():
    # late season: two big stable tanks + three normally shrinking ponds; nobody is pumping
    ponds = [pond("P001", 0.0, 90.0, "ok"), pond("P002", 0.01, 60.0, "ok"),
             pond("P003", -0.10, 20.0), pond("P004", -0.06, 12.0), pond("P005", -0.05, 10.0)]
    out = faster_than_sun(ponds)
    assert all(v["flag"] is None for v in out.values())
    assert out["P003"]["shrinkVsNeighbours"] == pytest.approx(1.0)


def test_too_few_shrinking_peers_means_no_flag():
    ponds = [pond("P001", -0.5, 10.0), pond("P002", -0.05, 10.0), pond("P003", 0.0, 10.0, "ok")]
    assert all(v == {"shrinkVsNeighbours": None, "flag": None} for v in faster_than_sun(ponds).values())
