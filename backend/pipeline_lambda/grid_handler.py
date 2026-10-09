"""Step Functions first task: the district's grid cells, so a scheduled run needs no cell list in its input.

Event: {"boundary": "latur-district", "onlyCells": ["c03-02", ...] (optional, for test runs)}
Returns {"cells": [{"id", "core", "bbox"}], "areaKm2"}.
"""
import json

from pipeline.district import area_km2, grid_cells, load_boundary


def lambda_handler(event, context):
    boundary = load_boundary(event["boundary"])
    cells = grid_cells(boundary)
    if event.get("onlyCells"):
        keep = set(event["onlyCells"])
        cells = [c for c in cells if c["id"] in keep]
    out = {"cells": cells, "areaKm2": round(area_km2(boundary["geometry"]))}
    print(json.dumps({"msg": "grid", "boundary": event["boundary"], "cells": len(cells), "areaKm2": out["areaKm2"]}))
    return out
