"""Build the web map and publish it on AWS Amplify Hosting (manual deployment, no GitHub link needed).

    python backend/scripts/deploy_web.py [--skip-build]

Creates the Amplify app "talaab" and branch "main" in us-west-2 the first time, then uploads
web/dist as a zip and waits until the deployment is live. Prints the public URL.
Cost: within the Amplify free tier for this traffic.
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DIST = WEB / "dist"
REGION = "us-west-2"
APP_NAME = "talaab"
BRANCH = "main"


def get_or_create_app(amp) -> str:
    for app in amp.list_apps(maxResults=100)["apps"]:
        if app["name"] == APP_NAME:
            return app["appId"]
    app = amp.create_app(name=APP_NAME, platform="WEB",
                         description="Talaab: per-pond dry-by countdowns for drought districts",
                         tags={"project": "talaab"})["app"]
    print(f"created Amplify app {app['appId']}")
    return app["appId"]


def ensure_branch(amp, app_id: str) -> None:
    names = [b["branchName"] for b in amp.list_branches(appId=app_id)["branches"]]
    if BRANCH not in names:
        amp.create_branch(appId=app_id, branchName=BRANCH, stage="PRODUCTION")
        print(f"created branch {BRANCH}")


def build() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=WEB, check=True)
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def zip_dist() -> bytes:
    out = ROOT / ".build" / "web-dist.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in DIST.rglob("*"):
            if path.is_file():
                z.write(path, path.relative_to(DIST).as_posix())  # forward slashes for Amplify
    return out.read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    if not args.skip_build:
        build()
    if not (DIST / "index.html").is_file():
        sys.exit("web/dist/index.html missing: build failed?")

    amp = boto3.client("amplify", region_name=REGION)
    app_id = get_or_create_app(amp)
    ensure_branch(amp, app_id)

    dep = amp.create_deployment(appId=app_id, branchName=BRANCH)
    body = zip_dist()
    req = urllib.request.Request(dep["zipUploadUrl"], data=body, method="PUT", headers={"Content-Type": "application/zip"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 (pre-signed AWS URL)
        if r.status != 200:
            sys.exit(f"upload failed: HTTP {r.status}")
    amp.start_deployment(appId=app_id, branchName=BRANCH, jobId=dep["jobId"])
    print(f"uploaded {len(body) / 1e6:.1f} MB, deployment job {dep['jobId']} started")

    for _ in range(60):
        status = amp.get_job(appId=app_id, branchName=BRANCH, jobId=dep["jobId"])["job"]["summary"]["status"]
        if status in ("SUCCEED", "FAILED", "CANCELLED"):
            break
        time.sleep(5)
    print(f"deployment {status}")
    if status != "SUCCEED":
        sys.exit(1)
    print(f"live at https://{BRANCH}.{app_id}.amplifyapp.com")


if __name__ == "__main__":
    main()
