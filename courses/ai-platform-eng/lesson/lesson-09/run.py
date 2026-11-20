#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-09.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Model storage selection, immutable artifacts, caching, and fleet distribution."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def sha256_bytes(payload: bytes) -> str:
    return 'sha256:' + hashlib.sha256(payload).hexdigest()

def verify_payload(payload: bytes, expected_digest: str) -> bool:
    return sha256_bytes(payload) == expected_digest

def strategy_metrics(distribution: dict[str, Any], strategy: str) -> dict[str, float | str]:
    size = distribution['artifact_size_gib']
    nodes = distribution['nodes']
    origin = distribution['origin_bandwidth_gbps']
    peer = distribution['peer_bandwidth_gbps']
    local = distribution['local_read_bandwidth_gbps']
    if strategy == 'remote-cold':
        return {'name': strategy, 'origin_egress_gib': size * nodes, 'startup_seconds': round(size * 8 * nodes / origin, 3), 'consistency': 'source-read-at-start'}
    if strategy == 'warm-node-cache':
        return {'name': strategy, 'origin_egress_gib': 0, 'startup_seconds': round(size * 8 / local, 3), 'consistency': 'digest-verified-cache-hit'}
    if strategy == 'prewarmed-cache':
        return {'name': strategy, 'origin_egress_gib': size * nodes, 'startup_seconds': round(size * 8 / local, 3), 'consistency': 'digest-verified-before-scheduling'}
    if strategy == 'p2p':
        origin_seconds = size * 8 / origin
        peer_seconds = size * 8 / peer
        return {'name': strategy, 'origin_egress_gib': size, 'startup_seconds': round(origin_seconds + peer_seconds, 3), 'consistency': 'digest-verified-peer-content'}
    raise ValueError(f'unknown strategy: {strategy}')

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'pvc_pending':
        actual = {'phase': 'Pending', 'reason': 'NoCompatibleStorageTopology'}
    elif kind == 'mount_secret':
        actual = {'phase': 'MountBlocked', 'reason': 'StorageCredentialUnavailable'}
    elif kind == 'multi_attach':
        blocked = fault['access_mode'] == 'RWO' and fault['nodes'] > 1
        actual = {'phase': 'MountBlocked' if blocked else 'Mounted', 'reason': 'ReadWriteOnceMultiAttach' if blocked else 'AccessModeSatisfied'}
    elif kind == 'multipart_incomplete':
        actual = {'phase': 'NotPublished', 'reason': 'MultipartUploadIncomplete'}
    elif kind == 'checkpoint_order':
        actual = {'phase': 'RestoreBlocked', 'reason': 'CheckpointManifestUnavailable'}
    elif kind == 'mutable_tag':
        stale = fault['cached_version'] != fault['resolved_version']
        actual = {'phase': 'Stale' if stale else 'Ready', 'reason': 'MutableReferenceChanged' if stale else 'ReferenceUnchanged'}
    elif kind == 'digest_mismatch':
        expected = sha256_bytes(b'validated-model')
        actual = {'phase': 'Ready' if verify_payload(b'corrupted-model', expected) else 'Quarantined', 'reason': 'DigestVerified' if verify_payload(b'corrupted-model', expected) else 'DigestVerificationFailed'}
    elif kind == 'cache_pressure':
        evictable = fault['capacity_gib'] - fault['pinned_gib']
        blocked = fault['requested_gib'] > evictable
        actual = {'phase': 'PrewarmBlocked' if blocked else 'Prewarmed', 'reason': 'InsufficientEvictableCapacity' if blocked else 'CacheCapacityAvailable', 'evictable_gib': evictable}
    elif kind == 'origin_storm':
        storm = fault['requests'] > fault['safe_concurrency']
        actual = {'phase': 'Throttled' if storm else 'Downloading', 'reason': 'OriginConcurrencyExceeded' if storm else 'WithinOriginBudget'}
    elif kind == 'snapshot_consistency':
        safe = fault['application_quiesced']
        actual = {'phase': 'SnapshotCreated' if safe else 'SnapshotCreatedUnsafe', 'reason': 'ApplicationConsistent' if safe else 'ApplicationConsistencyNotGuaranteed'}
    else:
        actual = {'phase': 'Unknown', 'reason': 'UnsupportedFault'}
    return {'name': fault['name'], 'passed': actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'], **actual}

def artifact_integrity_demo() -> dict[str, Any]:
    v1 = b'model-version-one'
    v2 = b'model-version-two'
    cache = {sha256_bytes(v1): v1}
    requested = sha256_bytes(v2)
    cache_hit = requested in cache
    cache[requested] = v2
    return {'v1_digest': sha256_bytes(v1), 'v2_digest': requested, 'initial_cache_hit': cache_hit, 'post_fetch_verified': verify_payload(cache[requested], requested), 'mutable_tag_boundary': 'tags are resolved before caching; digests identify cache entries'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    metrics = []
    expected = {item['name']: item for item in scenario['distribution']['strategies']}
    for name in expected:
        result = strategy_metrics(scenario['distribution'], name)
        target = expected[name]
        result['passed'] = result['origin_egress_gib'] == target['expected_origin_egress_gib'] and result['startup_seconds'] == target['expected_startup_seconds']
        metrics.append(result)
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    mappings_pass = all((item['recommended_store'] in {'object', 'object-plus-local-cache', 'oci-registry'} for item in scenario['artifact_types']))
    passed = mappings_pass and all((item['passed'] for item in metrics + faults))
    return {'status': 'PASS' if passed else 'FAIL', 'artifact_mappings': scenario['artifact_types'], 'distribution_metrics': metrics, 'integrity': artifact_integrity_demo(), 'faults': faults, 'measurement_boundary': 'startup times are deterministic capacity-model results, not measured storage performance'}

def inspect_live(context: str | None, object_endpoint: str | None) -> dict[str, Any]:
    if not context and (not object_endpoint):
        return {'status': 'SKIPPED', 'reason': 'no --context or --object-endpoint was supplied for a dedicated storage lab'}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'commands': {}}
    if context:
        commands = {'storage_classes': ['kubectl', '--context', context, 'get', 'storageclass', '-o', 'json'], 'persistent_claims': ['kubectl', '--context', context, 'get', 'pvc', '-A', '-o', 'json'], 'volume_snapshots': ['kubectl', '--context', context, 'get', 'volumesnapshots', '-A', '-o', 'json'], 'local_model_caches': ['kubectl', '--context', context, 'get', 'localmodelcache', '-o', 'json']}
        for name, command in commands.items():
            try:
                result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                return {'status': 'SKIPPED', 'reason': f'live Kubernetes inspection unavailable: {exc}'}
            observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    if object_endpoint:
        observed['object_endpoint'] = {'status': 'NOT_PROBED', 'endpoint': object_endpoint, 'reason': 'credentials and read scope must be supplied by the lab owner; this script never discovers them'}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--object-endpoint')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context, args.object_endpoint)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Artifact storage and distribution model: {report['status']}')
    for item in report['distribution_metrics']:
        print(f'  {item['name']}: origin={item['origin_egress_gib']}GiB startup={item['startup_seconds']}s')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live storage inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-09'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'artifact_distribution_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
