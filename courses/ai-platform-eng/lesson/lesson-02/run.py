#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-02.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate journeys and compile an AI platform product backlog."""
import argparse
import json
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

def load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)

def unique_index(items: list[dict[str, Any]], kind: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item.get('id')
        if not item_id:
            errors.append(f'{kind} item has no id')
        elif item_id in result:
            errors.append(f'duplicate {kind} id: {item_id}')
        else:
            result[item_id] = item
    return result

def validate_and_compile(scenario: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    personas = unique_index(scenario.get('personas', []), 'persona', errors)
    capabilities = unique_index(scenario.get('capabilities', []), 'capability', errors)
    metrics = unique_index(scenario.get('metrics', []), 'metric', errors)
    slos = unique_index(scenario.get('slos', []), 'slo', errors)
    journeys = unique_index(scenario.get('journeys', []), 'journey', errors)
    if not scenario.get('product_principles', {}).get('api_first'):
        errors.append('product principles must set api_first=true')
    for field in ('golden_path', 'escape_hatch', 'support_policy'):
        if not scenario.get('product_principles', {}).get(field):
            errors.append(f'product principles missing {field}')
    api_owners: dict[str, str] = {}
    for capability_id, capability in capabilities.items():
        owner = capability.get('owner')
        if owner not in personas:
            errors.append(f'capability {capability_id} has unknown owner {owner!r}')
        api = capability.get('api')
        if not api:
            errors.append(f'capability {capability_id} has no api')
        elif api in api_owners:
            errors.append(f'api {api!r} is shared by {api_owners[api]} and {capability_id}')
        else:
            api_owners[api] = capability_id
        if capability.get('priority') not in {'P0', 'P1', 'P2'}:
            errors.append(f'capability {capability_id} has invalid priority')
        if not capability.get('slos'):
            errors.append(f'capability {capability_id} has no slo')
        if not capability.get('metrics'):
            errors.append(f'capability {capability_id} has no metric')
        for slo_id in capability.get('slos', []):
            if slo_id not in slos:
                errors.append(f'capability {capability_id} references unknown slo {slo_id}')
        for metric_id in capability.get('metrics', []):
            if metric_id not in metrics:
                errors.append(f'capability {capability_id} references unknown metric {metric_id}')
    for slo_id, slo in slos.items():
        if slo.get('metric') not in metrics:
            errors.append(f'slo {slo_id} references unknown metric {slo.get('metric')}')
        if slo.get('operator') not in {'<=', '>=', '<', '>'}:
            errors.append(f'slo {slo_id} has invalid operator')
        if not isinstance(slo.get('target'), (int, float)):
            errors.append(f'slo {slo_id} has no numeric target')
        if not slo.get('window'):
            errors.append(f'slo {slo_id} has no window')
    pain_records: list[dict[str, Any]] = []
    persona_journeys: dict[str, int] = defaultdict(int)
    capability_score: dict[str, int] = defaultdict(int)
    for journey_id, journey in journeys.items():
        persona = journey.get('persona')
        if persona not in personas:
            errors.append(f'journey {journey_id} has unknown persona {persona!r}')
        else:
            persona_journeys[persona] += 1
        for required_field in ('trigger', 'outcome', 'owner'):
            if not journey.get(required_field):
                errors.append(f'journey {journey_id} missing {required_field}')
        expected_order = 1
        for step in journey.get('steps', []):
            if step.get('order') != expected_order:
                errors.append(f'journey {journey_id} expected step {expected_order}, got {step.get('order')}')
            expected_order += 1
            pain = step.get('pain', {})
            capability_ids = step.get('capabilities', [])
            if not pain.get('id') or not pain.get('description'):
                errors.append(f'journey {journey_id} step {step.get('order')} has incomplete pain')
                continue
            if not capability_ids:
                errors.append(f'pain {pain.get('id')} has no mapped capability')
            severity = pain.get('severity')
            frequency = pain.get('frequency')
            if severity not in range(1, 6) or frequency not in range(1, 6):
                errors.append(f'pain {pain.get('id')} severity/frequency must be 1..5')
                continue
            unknown = [item for item in capability_ids if item not in capabilities]
            if unknown:
                errors.append(f'pain {pain.get('id')} maps unknown capabilities: {', '.join(unknown)}')
            score = severity * frequency
            for capability_id in capability_ids:
                if capability_id in capabilities:
                    capability_score[capability_id] += score
                    if severity >= 5 and capabilities[capability_id].get('priority') == 'P2':
                        errors.append(f'critical pain {pain.get('id')} maps only to P2 capability {capability_id}')
            pain_records.append({'id': pain['id'], 'journey': journey_id, 'action': step.get('action'), 'severity': severity, 'frequency': frequency, 'score': score, 'capabilities': capability_ids})
    primary_personas = {journey.get('persona') for journey in journeys.values()}
    if len(primary_personas) < 3:
        warnings.append('fewer than three primary user personas have journeys')
    if not scenario.get('quota_products'):
        errors.append('no quota products defined')
    for quota in scenario.get('quota_products', []):
        for field in ('id', 'workload', 'gpu', 'max_hours', 'approval'):
            if field not in quota:
                errors.append(f'quota product missing {field}: {quota}')
    backlog = []
    for capability_id, capability in capabilities.items():
        backlog.append({'capability': capability_id, 'name': capability.get('name'), 'priority': capability.get('priority'), 'evidence_score': capability_score.get(capability_id, 0), 'owner': capability.get('owner'), 'api': capability.get('api')})
    priority_order = {'P0': 0, 'P1': 1, 'P2': 2}
    backlog.sort(key=lambda item: (priority_order[item['priority']], -item['evidence_score'], item['capability']))
    pain_records.sort(key=lambda item: (-item['score'], item['id']))
    return {'status': 'PASS' if not errors else 'FAIL', 'organization': scenario.get('organization'), 'summary': {'personas': len(personas), 'journeys': len(journeys), 'journey_steps': sum((len(j.get('steps', [])) for j in journeys.values())), 'pain_points': len(pain_records), 'capabilities': len(capabilities), 'apis': len(api_owners), 'slos': len(slos), 'metrics': len(metrics), 'quota_products': len(scenario.get('quota_products', []))}, 'top_pain_points': pain_records, 'mvp_backlog': backlog, 'errors': errors, 'warnings': warnings}

def check_live_api(base_url: str | None, timeout: float) -> dict[str, Any]:
    if not base_url:
        return {'status': 'SKIPPED', 'reason': 'no --base-url was supplied for a real platform API'}
    url = base_url.rstrip('/') + '/healthz'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(2048).decode('utf-8', errors='replace')
            return {'status': 'PASS' if response.status == 200 else 'FAIL', 'http_status': response.status, 'body': body}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {'status': 'FAIL', 'reason': str(exc)}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulated', 'live'), default='simulated')
    parser.add_argument('--base-url')
    parser.add_argument('--timeout', type=float, default=3.0)
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    report = validate_and_compile(load_json(args.scenario))
    if args.mode == 'live':
        report['live_api'] = check_live_api(args.base_url, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    summary = report['summary']
    print(f'Product requirement validation: {report['status']}')
    print(f'Journeys: {summary['journeys']} | Steps: {summary['journey_steps']} | Pain points: {summary['pain_points']}')
    print(f'Capabilities: {summary['capabilities']} | APIs: {summary['apis']} | SLOs: {summary['slos']} | Metrics: {summary['metrics']}')
    print(f'Quota products: {summary['quota_products']}')
    if args.mode == 'live':
        print(f'Live API check: {report['live_api']['status']}')
        if report['live_api']['status'] == 'SKIPPED':
            print(f'Reason: {report['live_api']['reason']}')
    if report['errors']:
        print('Errors:')
        for error in report['errors']:
            print(f'  - {error}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' and report.get('live_api', {}).get('status') != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-02'


def _emit_contract(status: str, source: str, **details) -> None:
    payload = {"status": status, "source": source, "entry": ENTRY_ID, **details}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _invoke_embedded(function, argv: list[str], source: str) -> int:
    import contextlib
    import io
    old_argv = sys.argv
    captured = io.StringIO()
    try:
        sys.argv = [str(Path(__file__).resolve()), *argv]
        try:
            with contextlib.redirect_stdout(captured):
                value = function()
            code = int(value or 0)
        except SystemExit as exc:
            code = int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 1
        except ModuleNotFoundError as exc:
            output = captured.getvalue().strip()
            if output:
                print(output)
            _emit_contract("precondition_failed", "none", reason=f"missing dependency: {exc.name}")
            return 2
    finally:
        sys.argv = old_argv
    output = captured.getvalue().strip()
    if output:
        print(output)
    if code == 2:
        _emit_contract("precondition_failed", "none", implementation_returncode=code)
        return 2
    status = "passed" if code == 0 else "failed"
    _emit_contract(status, source, implementation_returncode=code)
    return code


def _precondition_failed(reason: str, **details) -> int:
    _emit_contract("precondition_failed", "none", reason=reason, **details)
    return 2

def main() -> int:
    args = list(sys.argv[1:])
    if "--entry-info" in args:
        _emit_contract("ready", "none", implementation="standalone_single_file", authoritative_entry="run.py")
        return 0
    if "--check-only" in args:
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or False:
            return _precondition_failed("no declared live target capability is available", tools=tools, live_route_declared=True)
        _emit_contract("ready", "none", tools=tools)
        return 0
    if "--real" in args:
        args.remove("--real")
        if not args:
            return _precondition_failed("--real requires explicit live target arguments; no fixture fallback is allowed")
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or False:
            return _precondition_failed("no declared live target capability is available", tools=tools)
        forwarded = list(args)
        if "--scenario" not in forwarded:
            forwarded = ["--scenario", "scenario.json", *forwarded]
        if "--output" not in forwarded:
            forwarded = [*forwarded, "--output", "results/measured.json"]
        for item in ['--mode', 'live']:
            pass
        if True and "--mode" not in forwarded:
            forwarded = [['--mode', 'live'][0], ['--mode', 'live'][1], *forwarded]
        return _invoke_embedded(implementation_main, forwarded, "measured")
    return _invoke_embedded(implementation_main, args or ['--scenario', 'product_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
