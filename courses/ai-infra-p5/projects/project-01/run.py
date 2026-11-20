from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase5lab.simulations import run_scenario, write_report

COMPONENTS = [(4, 'source_registry'), (5, 'parser_evidence'), (8, 'normalization'), (9, 'filter_calibration'), (11, 'minhash_dedup')]


def main() -> int:
    children = []
    for number, scenario in COMPONENTS:
        path = ROOT / "lessons" / f"lesson-{number:02d}" / "fixture.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        report = run_scenario(scenario, fixture)
        children.append({"lesson": f"lesson-{number:02d}", "status": report["status"], "metrics": report["metrics"], "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    output = {"status": "passed" if all(x["status"] == "passed" for x in children) else "failed", "project_id": "project-01", "components": children, "proof_boundary": "composed_mechanism_simulation_only"}
    write_report(output, Path(__file__).with_name("results") / "project.json")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
