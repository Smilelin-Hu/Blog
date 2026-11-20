from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase5lab.simulations import run_scenario, write_report

EXPERIMENT_ID = "lesson-13"
SCENARIO = "governance"


def main() -> int:
    fixture = json.loads((Path(__file__).with_name("fixture.json")).read_text(encoding="utf-8"))
    report = run_scenario(SCENARIO, fixture)
    report["experiment_id"] = EXPERIMENT_ID
    write_report(report, Path(__file__).with_name("results") / "simulation.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
