"""End-to-end check of the LIVE API. Run before recording the demo.

    python backend/scripts/smoke_test.py [--api https://...execute-api.us-west-2.amazonaws.com]

Read-only except POST /plan (template plans; with AI on, it may start one cached AI plan per
date and language). Exit code 0 = all checks passed.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com"
results = []


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read() or b"{}"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), time.time() - t


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    api = ap.parse_args().api.rstrip("/")

    s, b, dt = call("GET", f"{api}/hello")
    check("GET /hello", s == 200 and b.get("service") == "talaab", f"{dt:.2f}s")

    s, b, dt = call("GET", f"{api}/regions")
    regions = b.get("regions", []) if s == 200 else []
    check("GET /regions", s == 200 and regions, f"{[r['id'] for r in regions]}")
    check("whole district listed", any(r["id"] == "latur-district-2024" for r in regions))

    for r in regions:
        rid, last = r["id"], r["last"]
        s, doc, dt = call("GET", f"{api}/ponds?region={rid}&asOf={last}")
        ponds = doc.get("ponds", []) if s == 200 else []
        shape_ok = all({"id", "lat", "lon", "status", "history", "dryBy", "daysLeft", "flag"} <= set(p) for p in ponds)
        check(f"GET /ponds {rid} @ {last}", s == 200 and doc.get("asOf") == last and ponds and shape_ok,
              f"{len(ponds)} ponds, {dt:.2f}s")
        if ponds:
            s, p, _ = call("GET", f"{api}/ponds/{ponds[0]['id']}?region={rid}&asOf={last}")
            check(f"GET /ponds/{ponds[0]['id']} {rid}", s == 200 and p.get("id") == ponds[0]["id"])
        s, _, _ = call("GET", f"{api}/ponds?region={rid}&asOf=1999-01-01")
        check(f"GET /ponds {rid} before first snapshot -> 404", s == 404)
        for lang in ("en", "mr"):
            s, plan, dt = call("POST", f"{api}/plan", {"region": rid, "asOf": last, "language": lang})
            check(f"POST /plan {rid} {lang}", s == 200 and plan.get("markdown") and plan.get("status") in ("ready", "generating", "template"),
                  f"status={plan.get('status')} source={plan.get('source')} {dt:.2f}s")
        s, _, _ = call("GET", f"{api}/backtest?region={rid}")
        check(f"GET /backtest {rid}", s in (200, 404), "available" if s == 200 else "not generated yet")
        s, al, _ = call("GET", f"{api}/alerts?region={rid}")
        check(f"GET /alerts {rid}", s == 200 and isinstance(al.get("events"), list),
              f"{len(al.get('events', []))} event(s), {'simulated' if al.get('simulated') else 'sent'}")

    s, _, _ = call("GET", f"{api}/ponds?asOf=not-a-date")
    check("bad asOf -> 400", s == 400)

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
