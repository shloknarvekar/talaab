"""Tests for district-scale processing: boundary, grid of cells, core ownership, merge, fixed grid."""

import pytest

from pipeline.cell import PIXEL_M, _overlap, fixed_grid
from pipeline.district import area_km2, contains, grid_cells, in_core, load_boundary, merge_cells

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]],
                                             [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6], [0.4, 0.4]]]}  # with a hole


def test_contains_respects_holes_and_multipolygons():
    assert contains(SQUARE, 0.1, 0.1)
    assert not contains(SQUARE, 0.5, 0.5)  # in the hole
    assert not contains(SQUARE, 1.5, 0.5)
    multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"], [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]]]}
    assert contains(multi, 2.5, 2.5) and contains(multi, 0.1, 0.9)


def test_area_of_one_degree_square_at_equator():
    one = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    assert area_km2(one) == pytest.approx(12_364, rel=0.01)  # 111.2 km x 111.2 km


def test_latur_boundary_area_matches_official_figure():
    b = load_boundary("latur-district")
    assert area_km2(b["geometry"]) == pytest.approx(7_157, rel=0.02)  # official 7,157 km2


def test_grid_covers_every_point_of_the_district_exactly_once():
    b = load_boundary("latur-district")
    cells = grid_cells(b)
    assert len(cells) == 42
    w, s, e, n = b["bbox"]
    inside = 0
    for i in range(1, 60):
        for j in range(1, 60):
            lon, lat = w + (e - w) * i / 60, s + (n - s) * j / 60
            if contains(b["geometry"], lon, lat):
                inside += 1
                owners = [c["id"] for c in cells if in_core(c["core"], lon, lat)]
                assert len(owners) == 1, (lon, lat, owners)
    assert inside > 1000


def test_cells_overlap_their_neighbours():
    c = grid_cells(load_boundary("latur-district"))[0]
    assert c["bbox"][0] < c["core"][0] and c["bbox"][2] > c["core"][2]
    assert c["bbox"][1] < c["core"][1] and c["bbox"][3] > c["core"][3]


def test_in_core_is_half_open_so_shared_edges_have_one_owner():
    left, right = [0, 0, 1, 1], [1, 0, 2, 1]
    assert not in_core(left, 1.0, 0.5) and in_core(right, 1.0, 0.5)


def _pond(pid, lon, lat, dates):
    return {"id": pid, "lon": lon, "lat": lat, "history": [{"date": d, "areaHa": 5.0, "valid": True} for d in dates]}


def test_merge_keeps_ponds_inside_and_marks_unseen_passes_invalid():
    cells = [
        {"scenes": [{"date": "2024-01-16", "id": "A"}, {"date": "2024-01-21", "id": "A2"}],
         "ponds": [_pond("c00-00-P001", 0.2, 0.2, ["2024-01-16", "2024-01-21"]), _pond("c00-00-P002", 0.5, 0.5, ["2024-01-16"])]},
        {"scenes": [{"date": "2024-01-16", "id": "B"}, {"date": "2024-01-26", "id": "B3"}],
         "ponds": [_pond("c00-01-P001", 0.8, 0.8, ["2024-01-16", "2024-01-26"])]},
    ]
    scenes, ponds = merge_cells(cells, SQUARE)
    assert [s["date"] for s in scenes] == ["2024-01-16", "2024-01-21", "2024-01-26"]
    assert [p["id"] for p in ponds] == ["c00-00-P001", "c00-01-P001"]  # P002 sits in the hole
    p1 = ponds[0]["history"]
    assert [h["date"] for h in p1] == ["2024-01-16", "2024-01-21", "2024-01-26"]
    assert p1[2] == {"date": "2024-01-26", "areaHa": 0.0, "valid": False}  # not observed, not "dry"
    assert len(cells[0]["ponds"][0]["history"]) == 2  # inputs are not mutated


def test_overlap_fraction():
    assert _overlap([0, 0, 2, 2], [0, 0, 1, 1]) == 1.0
    assert _overlap([0.5, 0, 2, 2], [0, 0, 1, 1]) == pytest.approx(0.5)
    assert _overlap([5, 5, 6, 6], [0, 0, 1, 1]) == 0.0


def test_fixed_grid_is_snapped_to_10_m_and_consistent():
    bbox = [76.455, 18.315, 76.635, 18.495]
    (left, bottom, right, top), shape, affine = fixed_grid(bbox, "EPSG:32643")
    assert all(v % PIXEL_M == 0 for v in (left, bottom, right, top))
    assert shape == (round((top - bottom) / PIXEL_M), round((right - left) / PIXEL_M))
    assert affine.a == PIXEL_M and affine.e == -PIXEL_M and (affine.c, affine.f) == (left, top)
    assert fixed_grid(bbox, "EPSG:32643") == ((left, bottom, right, top), shape, affine)  # same grid every date
