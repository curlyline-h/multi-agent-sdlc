"""
Repairs and verifies end-to-end Backend + Frontend code completeness across
completed scenario directories (`scen_003`..`scen_037`) that ran before
Error #6 (`src/file.ts` placeholder) and `code_completeness.py` were introduced.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agents.src.shared.code_completeness import (
    ensure_backend_tasks_and_routes_wired,
    ensure_frontend_completeness,
    find_missing_local_imports,
)

SCENARIOS = ["scen_003", "scen_008", "scen_012", "scen_020", "scen_024", "scen_037"]

for scen_id in SCENARIOS:
    out_dir = ROOT / "output" / scen_id
    if not out_dir.exists():
        continue
    print(f"\n================ Repairing & Verifying {scen_id} ================")
    design_path = out_dir / "docs" / "03_system_design.md"
    tasks_path = out_dir / "docs" / "04_task_breakdown.md"
    sql_path = out_dir / "db" / "init.sql"

    design_doc = design_path.read_text(encoding="utf-8", errors="replace") if design_path.exists() else ""
    tasks_str = tasks_path.read_text(encoding="utf-8", errors="replace") if tasks_path.exists() else ""
    db_schema = sql_path.read_text(encoding="utf-8", errors="replace") if sql_path.exists() else ""

    be = ensure_backend_tasks_and_routes_wired(out_dir, tasks_str, design_doc, db_schema)
    fe = ensure_frontend_completeness(out_dir, tasks_str, design_doc, db_schema)
    missing = find_missing_local_imports(out_dir)
    print(f"[{scen_id}] Backend wired: {be} | Frontend resolved: {fe} | Remaining missing imports: {len(missing)}")

