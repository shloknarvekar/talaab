"""Copy the satellite pipeline package + Lambda handlers into .build/pipeline-fn (the SAM CodeUri).

    python backend/scripts/stage_pipeline_fn.py      # run before `sam build`
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".build" / "pipeline-fn"

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "pipeline" / "boundaries").mkdir(parents=True)
for f in (ROOT / "pipeline").glob("*.py"):
    shutil.copy2(f, OUT / "pipeline" / f.name)
(OUT / "pipeline" / "__init__.py").touch()
for f in (ROOT / "pipeline" / "boundaries").glob("*.json"):
    shutil.copy2(f, OUT / "pipeline" / "boundaries" / f.name)
for f in (ROOT / "backend" / "pipeline_lambda").glob("*_handler.py"):
    shutil.copy2(f, OUT / f.name)
print(f"staged {sum(1 for _ in OUT.rglob('*') if _.is_file())} files -> {OUT}")
