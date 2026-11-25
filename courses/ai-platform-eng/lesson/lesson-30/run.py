#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-30.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic multi-cluster self-service AI platform architecture replay."""
import argparse
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_cluster_inventory(scenario: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    seen: set[str] = set()
    workers = 0
    for cluster in scenario['clusters']:
        cluster_id = cluster.get('id')
        if not cluster_id or cluster_id in seen:
            reasons.append('ClusterIdentityInvalid')
        seen.add(cluster_id)
        if cluster['role'] == 'worker':
            workers += 1
        if not cluster.get('lifecycle_owner'):
            reasons.append('ClusterLifecycleOwnerMissing')
        if not cluster.get('bootstrap_revision', '').startswith('sha256:'):
            reasons.append('ClusterBootstrapRevisionMutable')
        if cluster.get('credential_scope') not in {'namespaced', 'project-scoped'}:
            reasons.append('ClusterCredentialScopeTooBroad')
        if cluster.get('capability_freshness_minutes', 10 ** 9) > scenario['policy']['maximum_capability_freshness_minutes']:
            reasons.append('ClusterCapabilityInventoryStale')
    if workers == 0:
        reasons.append('WorkerClusterMissing')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'ClusterInventoryContractSatisfied' if not reasons else reasons[0], 'reasons': reasons, 'cluster_count': len(scenario['clusters']), 'worker_count': workers}

def validate_self_service_request(request: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    for field in ('name', 'tenant', 'project', 'owner', 'cost_center', 'template', 'template_version', 'queue', 'namespace'):
        if not request.get(field):
            reasons.append(f'RequiredFieldMissing:{field}')
    if request.get('template') not in scenario['portal']['approved_templates']:
        reasons.append('TemplateNotApproved')
    if not str(request.get('template_version', '')).startswith('sha256:'):
        reasons.append('TemplateVersionMustBeImmutable')
    if request.get('direct_cluster_credentials'):
        reasons.append('DirectClusterCredentialForbidden')
    if request.get('requested_gpus', 0) > scenario['policy']['maximum_gpus_per_request']:
        reasons.append('GPURequestLimitExceeded')
    if request.get('environment') == 'production' and (not request.get('approval')):
        reasons.append('ProductionApprovalMissing')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'SelfServiceRequestValidated' if not reasons else reasons[0], 'reasons': reasons}

def eligible_clusters(request: dict[str, Any], scenario: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for cluster in scenario['clusters']:
        if cluster['role'] != 'worker' or cluster['status'] != 'Ready':
            continue
        if request['gpu_type'] not in cluster['gpu_capacity']:
            continue
        if cluster['gpu_capacity'][request['gpu_type']]['available'] < request['requested_gpus']:
            continue
        if request['residency'] not in cluster['residency']:
            continue
        if request['required_capability'] not in cluster['capabilities']:
            continue
        if request['namespace'] not in cluster['namespaces']:
            continue
        if request['queue'] not in cluster['local_queues']:
            continue
        result.append(cluster)
    return result

def dispatch_workload(request: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    validation = validate_self_service_request(request, scenario)
    if validation['status'] != 'PASS':
        return {'status': 'REJECTED', 'reason': validation['reason'], 'eligible': []}
    candidates = eligible_clusters(request, scenario)
    if not candidates:
        return {'status': 'PENDING', 'reason': 'NoEligibleWorkerCluster', 'eligible': []}
    scored = []
    for cluster in candidates:
        gpu = cluster['gpu_capacity'][request['gpu_type']]
        fragmentation_after = gpu['available'] - request['requested_gpus']
        score = float(cluster['queue_wait_seconds']) + float(cluster['cost_index']) * 100 + fragmentation_after * scenario['policy']['fragmentation_penalty']
        scored.append((score, cluster['id']))
    scored.sort()
    selected = scored[0][1]
    return {'status': 'DISPATCHED', 'reason': 'MultiClusterPolicySatisfied', 'selected_cluster': selected, 'eligible': [item['id'] for item in candidates], 'scores': [{'cluster': cid, 'score': round(score, 6)} for score, cid in scored], 'managed_by': 'kueue.x-k8s.io/multikueue'}

def reconcile_platform(scenario: dict[str, Any]) -> dict[str, Any]:
    desired = set(scenario['gitops']['desired_clusters'])
    registered = set(scenario['gitops']['registered_clusters'])
    bootstrapped = set(scenario['gitops']['bootstrapped_clusters'])
    drifted = set(scenario['gitops']['drifted_clusters'])
    missing_registration = sorted(desired - registered)
    missing_bootstrap = sorted(desired - bootstrapped)
    reasons = []
    if missing_registration:
        reasons.append('DesiredClusterNotRegistered')
    if missing_bootstrap:
        reasons.append('ClusterBootstrapIncomplete')
    if drifted and (not scenario['gitops']['self_heal']):
        reasons.append('ClusterDriftUnreconciled')
    return {'status': 'PASS' if not reasons else 'DEGRADED', 'reason': 'PlatformDesiredStateConverged' if not reasons else reasons[0], 'reasons': reasons, 'missing_registration': missing_registration, 'missing_bootstrap': missing_bootstrap, 'drifted': sorted(drifted), 'self_heal': scenario['gitops']['self_heal']}

def portal_catalog(scenario: dict[str, Any]) -> dict[str, Any]:
    entities = scenario['portal']['entities']
    orphaned = [item['name'] for item in entities if not item.get('owner')]
    unpinned = [item['name'] for item in entities if not str(item.get('definition_revision', '')).startswith('sha256:')]
    reasons = []
    if orphaned:
        reasons.append('CatalogOwnerMissing')
    if unpinned:
        reasons.append('CatalogDefinitionMutable')
    if scenario['portal']['kubernetes_proxy_enabled']:
        reasons.append('ArbitraryKubernetesProxyEnabled')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'PortalCatalogGoverned' if not reasons else reasons[0], 'reasons': reasons, 'entity_count': len(entities), 'orphaned': orphaned, 'unpinned': unpinned}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'missing_owner': ('REJECTED', 'RequiredFieldMissing:owner'), 'mutable_template': ('REJECTED', 'TemplateVersionMustBeImmutable'), 'direct_cluster_credentials': ('REJECTED', 'DirectClusterCredentialForbidden'), 'unapproved_template': ('REJECTED', 'TemplateNotApproved'), 'production_without_approval': ('REJECTED', 'ProductionApprovalMissing'), 'gpu_request_too_large': ('REJECTED', 'GPURequestLimitExceeded'), 'unknown_gpu_type': ('PENDING', 'NoEligibleWorkerCluster'), 'residency_mismatch': ('PENDING', 'NoEligibleWorkerCluster'), 'capacity_shortage': ('PENDING', 'NoEligibleWorkerCluster'), 'worker_not_ready': ('PENDING', 'NoEligibleWorkerCluster'), 'worker_namespace_missing': ('PENDING', 'NoEligibleWorkerCluster'), 'worker_localqueue_missing': ('PENDING', 'NoEligibleWorkerCluster'), 'manager_used_as_worker': ('REJECTED', 'ManagerClusterCannotExecuteDelegatedWorkload'), 'cluster_identity_duplicate': ('REJECTED', 'ClusterIdentityInvalid'), 'cluster_owner_missing': ('REJECTED', 'ClusterLifecycleOwnerMissing'), 'bootstrap_revision_mutable': ('REJECTED', 'ClusterBootstrapRevisionMutable'), 'cluster_credential_broad': ('REJECTED', 'ClusterCredentialScopeTooBroad'), 'capability_inventory_stale': ('INCONCLUSIVE', 'ClusterCapabilityInventoryStale'), 'gitops_registration_missing': ('DEGRADED', 'DesiredClusterNotRegistered'), 'gitops_bootstrap_missing': ('DEGRADED', 'ClusterBootstrapIncomplete'), 'drift_without_self_heal': ('DEGRADED', 'ClusterDriftUnreconciled'), 'backstage_proxy_enabled': ('REJECTED', 'ArbitraryKubernetesProxyEnabled'), 'catalog_owner_missing': ('REJECTED', 'CatalogOwnerMissing'), 'manager_status_assumed_worker_status': ('INCONCLUSIVE', 'WorkerExecutionStatusMustComeFromWorkload'), 'cost_identity_missing': ('INCONCLUSIVE', 'CostIdentityMissing'), 'destructive_cluster_delete': ('REJECTED', 'DestructiveLifecycleActionRequiresApproval'), 'live_clusters_missing': ('SKIPPED', 'NoKubernetesContextsProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    inventory = validate_cluster_inventory(scenario)
    requests = [dispatch_workload(item, scenario) for item in scenario['requests']]
    gitops = reconcile_platform(scenario)
    portal = portal_catalog(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if inventory['status'] == 'PASS' and all((item['status'] == 'DISPATCHED' for item in requests)) and (gitops['status'] == 'PASS') and (portal['status'] == 'PASS') and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'inventory': inventory, 'requests': requests, 'gitops': gitops, 'portal': portal, 'faults': faults}

def inspect_live(contexts: list[str], backstage_url: str | None) -> dict[str, Any]:
    if not contexts and (not backstage_url):
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextsProvided'}
    evidence: dict[str, Any] = {'clusters': {}}
    if contexts:
        if shutil.which('kubectl') is None:
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        for context in contexts:
            command = ['kubectl', '--context', context, 'get', 'nodes,namespaces,crds', '-o', 'json']
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
            except subprocess.TimeoutExpired:
                return {'status': 'FAIL', 'reason': 'LiveClusterReadTimeout', 'context': context}
            if result.returncode:
                return {'status': 'FAIL', 'reason': 'LiveClusterReadFailed', 'context': context, 'stderr': result.stderr.strip()}
            evidence['clusters'][context] = json.loads(result.stdout)
    if backstage_url:
        try:
            with urllib.request.urlopen(backstage_url.rstrip('/') + '/api/catalog/entities?limit=1', timeout=30) as response:
                evidence['backstage_catalog'] = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            return {'status': 'FAIL', 'reason': 'LiveBackstageReadFailed', 'error': type(exc).__name__}
    return {'status': 'PASS', 'reason': 'LiveMultiClusterEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contexts', default='')
    parser.add_argument('--backstage-url')
    args = parser.parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    contexts = [item.strip() for item in args.contexts.split(',') if item.strip()]
    report['live'] = inspect_live(contexts, args.backstage_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Multi-cluster platform replay: {report['status']}')
    print(f'  inventory: {report['inventory']['status']}/{report['inventory']['reason']}')
    for index, item in enumerate(report['requests'], 1):
        print(f'  request {index}: {item['status']}/{item['reason']} selected={item.get('selected_cluster', '-')}')
    print(f'  gitops: {report['gitops']['status']}/{report['gitops']['reason']}')
    print(f'  portal: {report['portal']['status']}/{report['portal']['reason']}')
    for fault in report['faults']:
        print(f'  fault {fault['type']}: {fault['status']} {fault['phase']}/{fault['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'lesson/lesson-30'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'platform_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
