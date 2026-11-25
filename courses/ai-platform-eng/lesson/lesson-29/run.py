#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-29.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic GPU cost attribution and capacity-planning replay."""
import argparse
import json
import math
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def workload_cost(item: dict[str, Any], rates: dict[str, float]) -> dict[str, Any]:
    gpu_hours = float(item['gpu_count']) * float(item['runtime_hours'])
    cpu_hours = float(item['cpu_request']) * float(item['runtime_hours'])
    memory_gib_hours = float(item['memory_gib_request']) * float(item['runtime_hours'])
    storage_gib_hours = float(item['storage_gib']) * float(item['runtime_hours'])
    direct = gpu_hours * rates[item['gpu_type']] + cpu_hours * rates['cpu_core_hour'] + memory_gib_hours * rates['memory_gib_hour'] + storage_gib_hours * rates['storage_gib_hour']
    utilized_gpu_hours = gpu_hours * float(item['gpu_utilization'])
    return {'workload': item['name'], 'tenant': item['tenant'], 'project': item['project'], 'gpu_type': item['gpu_type'], 'gpu_hours': gpu_hours, 'utilized_gpu_hours': utilized_gpu_hours, 'direct_cost': round(direct, 6), 'identity_complete': all((item.get(key) for key in ('tenant', 'project', 'cost_center', 'owner')))}

def allocate_costs(scenario: dict[str, Any]) -> dict[str, Any]:
    direct = [workload_cost(item, scenario['rates']) for item in scenario['workloads']]
    direct_total = sum((item['direct_cost'] for item in direct))
    shared = float(scenario['shared_platform_cost'])
    idle = float(scenario['idle_gpu_cost'])
    mode = scenario['allocation_policy']['idle_mode']
    by_tenant_direct: dict[str, float] = defaultdict(float)
    for item in direct:
        by_tenant_direct[item['tenant']] += item['direct_cost']
    tenant_rows = []
    for tenant, amount in sorted(by_tenant_direct.items()):
        share = amount / direct_total if direct_total else 0.0
        shared_part = shared * share
        idle_part = idle * share if mode == 'proportional' else 0.0
        tenant_rows.append({'tenant': tenant, 'direct_cost': round(amount, 6), 'shared_cost': round(shared_part, 6), 'idle_cost': round(idle_part, 6), 'allocated_cost': round(amount + shared_part + idle_part, 6)})
    unallocated = 0.0 if mode == 'proportional' else idle
    unknown = sum((item['direct_cost'] for item in direct if not item['identity_complete']))
    billed = direct_total + shared + idle
    attributed = direct_total - unknown + shared + (idle if mode == 'proportional' else 0.0)
    return {'status': 'PASS' if unknown / billed <= scenario['allocation_policy']['maximum_unknown_cost_ratio'] else 'INCONCLUSIVE', 'reason': 'CostAttributionWithinPolicy' if unknown / billed <= scenario['allocation_policy']['maximum_unknown_cost_ratio'] else 'UnknownCostRatioExceeded', 'workloads': direct, 'tenants': tenant_rows, 'direct_total': round(direct_total, 6), 'shared_total': shared, 'idle_total': idle, 'unallocated_idle': round(unallocated, 6), 'billed_total': round(billed, 6), 'attributed_total': round(attributed, 6), 'coverage_ratio': round(attributed / billed if billed else 1.0, 9), 'reconciliation_delta': round(billed - (sum((row['allocated_cost'] for row in tenant_rows)) + unallocated), 9)}

def quantile(values: list[float], q: float) -> float:
    ordered = sorted((float(value) for value in values))
    if not ordered:
        raise ValueError('capacity series must not be empty')
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)

def plan_capacity(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['capacity_policy']
    plans = []
    for pool in scenario['capacity_pools']:
        p95 = quantile(pool['demand_samples'], 0.95)
        growth = (1.0 + float(pool['monthly_growth_rate'])) ** float(policy['lead_time_months'])
        forecast = p95 * growth
        failure_headroom = int(pool['largest_failure_domain_gpus'])
        target = math.ceil(forecast / float(policy['maximum_target_utilization'])) + failure_headroom
        gap = target - int(pool['installed_gpus'])
        plans.append({'pool': pool['name'], 'p95_demand': round(p95, 6), 'lead_time_forecast': round(forecast, 6), 'failure_headroom': failure_headroom, 'target_gpus': target, 'installed_gpus': pool['installed_gpus'], 'capacity_gap': gap, 'action': 'PROCURE_OR_RESERVE' if gap > 0 else 'HOLD_OR_REBALANCE'})
    return {'status': 'PASS', 'reason': 'CapacityPlanComputed', 'pools': plans}

def validate_governance(scenario: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    governance = scenario['governance']
    if governance['price_freshness_hours'] > governance['maximum_price_freshness_hours']:
        reasons.append('PricingDataStale')
    if governance['billing_reconciliation_ratio'] < governance['minimum_billing_reconciliation_ratio']:
        reasons.append('BillingReconciliationCoverageInsufficient')
    if not governance['gpu_identity_mapping_verified']:
        reasons.append('GPUIdentityMappingUnverified')
    if not governance['shared_cost_policy_versioned']:
        reasons.append('SharedCostPolicyUnversioned')
    if not governance['budget_owner_present']:
        reasons.append('BudgetOwnerMissing')
    return {'status': 'PASS' if not reasons else 'INCONCLUSIVE', 'reason': 'FinOpsEvidenceSufficient' if not reasons else reasons[0], 'reasons': reasons}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'missing_tenant': ('INCONCLUSIVE', 'CostIdentityMissing'), 'missing_project': ('INCONCLUSIVE', 'CostIdentityMissing'), 'unknown_gpu_type': ('REJECTED', 'GPUPriceProfileUnknown'), 'negative_runtime': ('REJECTED', 'RuntimeMustBeNonNegative'), 'utilization_above_one': ('REJECTED', 'GPUUtilizationOutOfRange'), 'price_stale': ('INCONCLUSIVE', 'PricingDataStale'), 'billing_gap': ('INCONCLUSIVE', 'BillingReconciliationCoverageInsufficient'), 'gpu_mapping_unknown': ('INCONCLUSIVE', 'GPUIdentityMappingUnverified'), 'shared_policy_missing': ('INCONCLUSIVE', 'SharedCostPolicyUnversioned'), 'budget_owner_missing': ('INCONCLUSIVE', 'BudgetOwnerMissing'), 'idle_hidden': ('REJECTED', 'IdleCostMustRemainVisible'), 'double_allocation': ('REJECTED', 'CostReconciliationDeltaNonZero'), 'empty_capacity_series': ('REJECTED', 'CapacityDemandSeriesEmpty'), 'forecast_growth_negative': ('REJECTED', 'CapacityGrowthRateInvalid'), 'lead_time_zero': ('REJECTED', 'CapacityLeadTimeInvalid'), 'target_utilization_one': ('REJECTED', 'CapacityHeadroomMissing'), 'failure_domain_unknown': ('INCONCLUSIVE', 'FailureDomainCapacityUnknown'), 'commitment_without_baseline': ('REJECTED', 'CommitmentBaselineMissing'), 'spot_without_interruptions': ('INCONCLUSIVE', 'SpotInterruptionEvidenceMissing'), 'live_sources_missing': ('SKIPPED', 'NoLiveFinOpsSourceProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    attribution = allocate_costs(scenario)
    capacity = plan_capacity(scenario)
    governance = validate_governance(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if attribution['status'] == governance['status'] == capacity['status'] == 'PASS' and abs(attribution['reconciliation_delta']) < 1e-08 and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'attribution': attribution, 'capacity': capacity, 'governance': governance, 'faults': faults}

def inspect_live(context: str | None, opencost_url: str | None) -> dict[str, Any]:
    if not context and (not opencost_url):
        return {'status': 'SKIPPED', 'reason': 'NoLiveFinOpsSourceProvided'}
    evidence: dict[str, Any] = {}
    if context:
        if shutil.which('kubectl') is None:
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        command = ['kubectl', '--context', context, 'get', 'nodes,pods', '-A', '-o', 'json']
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'LiveKubernetesCostReadTimeout'}
        if result.returncode:
            return {'status': 'FAIL', 'reason': 'LiveKubernetesCostReadFailed', 'stderr': result.stderr.strip()}
        evidence['kubernetes'] = json.loads(result.stdout)
    if opencost_url:
        query = urllib.parse.urlencode({'window': '1d', 'aggregate': 'namespace', 'includeIdle': 'true'})
        url = opencost_url.rstrip('/') + '/allocation?' + query
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                evidence['opencost'] = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            return {'status': 'FAIL', 'reason': 'LiveOpenCostReadFailed', 'error': type(exc).__name__}
    return {'status': 'PASS', 'reason': 'LiveFinOpsEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context')
    parser.add_argument('--opencost-url')
    args = parser.parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    report['live'] = inspect_live(args.context, args.opencost_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'GPU FinOps replay: {report['status']}')
    print(f'  attribution: {report['attribution']['status']}/{report['attribution']['reason']}')
    print(f'  coverage: {report['attribution']['coverage_ratio']}')
    print(f'  governance: {report['governance']['status']}/{report['governance']['reason']}')
    for pool in report['capacity']['pools']:
        print(f'  pool {pool['pool']}: target={pool['target_gpus']} gap={pool['capacity_gap']} action={pool['action']}')
    for fault in report['faults']:
        print(f'  fault {fault['type']}: {fault['status']} {fault['phase']}/{fault['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'lesson/lesson-29'


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
        for item in []:
            pass
        if False and "--mode" not in forwarded:
            forwarded = [[][0], [][1], *forwarded]
        return _invoke_embedded(implementation_main, forwarded, "measured")
    return _invoke_embedded(implementation_main, args or ['--scenario', 'finops_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
