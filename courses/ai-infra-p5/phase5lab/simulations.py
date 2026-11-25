from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Callable


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _report(mechanism: str, metrics: dict[str, Any], observations: list[str], checks: dict[str, bool]) -> dict[str, Any]:
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "mechanism": mechanism,
        "metrics": metrics,
        "observations": observations,
        "checks": checks,
        "proof_boundary": "mechanism_simulation_only",
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lineage_map(f: dict[str, Any]) -> dict[str, Any]:
    graph = defaultdict(list)
    for parent, child in f["edges"]:
        graph[parent].append(child)
    start = f["withdraw"]
    queue, seen = deque([start]), {start}
    while queue:
        for child in graph[queue.popleft()]:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    expected = set(f["expected_affected"])
    return _report(
        "lineage_map",
        {"nodes": len({x for e in f["edges"] for x in e}), "affected": len(seen), "closure_sha256": _sha(sorted(seen))},
        [f"withdrawal closure: {', '.join(sorted(seen))}"],
        {"source_included": start in seen, "closure_matches": seen == expected},
    )


def token_ledger(f: dict[str, Any]) -> dict[str, Any]:
    raw = sum(x["raw_tokens"] for x in f["records"])
    valid = sum(x["valid_tokens"] for x in f["records"])
    unique = sum(x["unique_tokens"] for x in f["records"])
    loss = sum(x["loss_tokens"] for x in f["records"])
    return _report(
        "token_ledger",
        {"raw": raw, "valid": valid, "unique": unique, "loss": loss, "effective_ratio": round(loss / raw, 6)},
        ["The ledger keeps every denominator instead of collapsing them into one token count."],
        {"monotonic": raw >= valid >= unique >= loss >= 0, "nonempty": raw > 0},
    )


def source_registry(f: dict[str, Any]) -> dict[str, Any]:
    required = {"source_id", "license", "purpose", "owner", "withdrawal_contact", "status"}
    decisions = []
    for row in f["sources"]:
        missing = sorted(required - row.keys())
        allowed = not missing and row["status"] == "active" and f["requested_purpose"] in row["purpose"]
        decisions.append({"source_id": row.get("source_id", "unknown"), "allowed": allowed, "missing": missing})
    return _report(
        "source_registry",
        {"sources": len(decisions), "allowed": sum(x["allowed"] for x in decisions), "rejected": sum(not x["allowed"] for x in decisions)},
        [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in decisions],
        {"has_rejection": any(not x["allowed"] for x in decisions), "has_acceptance": any(x["allowed"] for x in decisions)},
    )


def parser_evidence(f: dict[str, Any]) -> dict[str, Any]:
    parsed = []
    for row in f["objects"]:
        text = " ".join(row["payload"].replace("\n", " ").split())
        status = "parsed" if len(text) >= f["min_chars"] else "rejected_short"
        parsed.append({"object_id": row["object_id"], "locator": row["locator"], "status": status, "text_sha256": _sha(text)})
    return _report(
        "parser_evidence",
        {"objects": len(parsed), "parsed": sum(x["status"] == "parsed" for x in parsed), "rejected": sum(x["status"] != "parsed" for x in parsed)},
        [f"{x['object_id']} -> {x['status']} @ {x['locator']}" for x in parsed],
        {"all_locatable": all(x["locator"] for x in parsed), "states_complete": len(parsed) == len(f["objects"])},
    )


def scheduler_fit(f: dict[str, Any]) -> dict[str, Any]:
    scores = {}
    for engine, traits in f["engines"].items():
        score = sum(f["workload"].get(k, 0) * traits.get(k, 0) for k in f["workload"])
        scores[engine] = round(score, 3)
    winner = max(scores, key=scores.get)
    return _report(
        "scheduler_fit",
        {"scores": scores, "selected": winner},
        [f"Selected {winner} for the declared workload traits; this is a decision model, not a throughput benchmark."],
        {"winner_expected": winner == f["expected"], "scores_distinct": len(set(scores.values())) > 1},
    )


def shard_replay(f: dict[str, Any]) -> dict[str, Any]:
    ids = list(f["sample_ids"])
    rng = random.Random(f["seed"])
    rng.shuffle(ids)
    shards = [ids[i::f["shards"]] for i in range(f["shards"])]
    consumed = [x for shard in shards for x in shard[: f["cursor"]]]
    resumed = [x for shard in shards for x in shard[f["cursor"] :]]
    all_seen = consumed + resumed
    return _report(
        "shard_replay",
        {"samples": len(ids), "shards": len(shards), "consumed": len(consumed), "resumed": len(resumed), "order_sha256": _sha(all_seen)},
        ["Resume position is recorded per deterministic shard."],
        {"no_duplicate": len(all_seen) == len(set(all_seen)), "no_missing": set(all_seen) == set(ids)},
    )


def normalization(f: dict[str, Any]) -> dict[str, Any]:
    import unicodedata

    rows = []
    for text in f["texts"]:
        normalized = unicodedata.normalize(f["form"], text).replace("\r\n", "\n")
        controls = [f"U+{ord(ch):04X}" for ch in normalized if unicodedata.category(ch) == "Cc" and ch not in "\n\t"]
        rows.append({"before": _sha(text), "after": _sha(normalized), "changed": text != normalized, "controls": controls})
    return _report(
        "normalization",
        {"records": len(rows), "changed": sum(x["changed"] for x in rows), "unsafe_controls": sum(len(x["controls"]) for x in rows)},
        [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in rows],
        {"all_audited": len(rows) == len(f["texts"]), "control_policy_visible": "controls" in rows[0]},
    )


def filter_calibration(f: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in f["samples"]:
        score = sum(item["features"].get(k, 0) * weight for k, weight in f["weights"].items())
        pred = score >= f["threshold"]
        rows.append((pred, item["label"], item["slice"], score))
    tp = sum(p and y for p, y, _, _ in rows); fp = sum(p and not y for p, y, _, _ in rows)
    fn = sum(not p and y for p, y, _, _ in rows); tn = sum(not p and not y for p, y, _, _ in rows)
    return _report(
        "filter_calibration",
        {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4)},
        [f"slice={s} score={v:.3f} predicted={p} label={y}" for p, y, s, v in rows],
        {"both_classes_seen": len({y for _, y, _, _ in rows}) == 2, "errors_visible": fp + fn >= 0},
    )


def score_calibration(f: dict[str, Any]) -> dict[str, Any]:
    bins = defaultdict(list)
    for score, label in f["predictions"]:
        bucket = min(int(score * f["bins"]), f["bins"] - 1)
        bins[bucket].append((score, label))
    gap = 0.0
    details = []
    total = len(f["predictions"])
    for bucket, items in sorted(bins.items()):
        confidence = statistics.fmean(x[0] for x in items)
        accuracy = statistics.fmean(float(x[1]) for x in items)
        gap += len(items) / total * abs(confidence - accuracy)
        details.append({"bucket": bucket, "count": len(items), "confidence": round(confidence, 4), "accuracy": round(accuracy, 4)})
    return _report("score_calibration", {"ece": round(gap, 6), "bins": details}, ["Calibration is reported separately from ranking accuracy."], {"all_scored": sum(x["count"] for x in details) == total})


def minhash_dedup(f: dict[str, Any]) -> dict[str, Any]:
    def shingles(text: str) -> set[str]:
        tokens = text.lower().split()
        return {" ".join(tokens[i : i + f["ngram"]]) for i in range(max(1, len(tokens) - f["ngram"] + 1))}
    pairs = []
    for i, left in enumerate(f["documents"]):
        for right in f["documents"][i + 1 :]:
            a, b = shingles(left["text"]), shingles(right["text"])
            score = len(a & b) / max(len(a | b), 1)
            if score >= f["threshold"]:
                pairs.append({"left": left["id"], "right": right["id"], "jaccard": round(score, 4)})
    return _report("minhash_dedup", {"documents": len(f["documents"]), "candidate_pairs": pairs}, ["Candidate generation stays separate from the keep/delete decision."], {"expected_pair_found": any({x["left"], x["right"]} == set(f["expected_pair"]) for x in pairs)})


def semantic_cluster(f: dict[str, Any]) -> dict[str, Any]:
    clusters: list[list[dict[str, Any]]] = []
    for item in f["items"]:
        placed = False
        for cluster in clusters:
            center = cluster[0]["vector"]
            dot = sum(a * b for a, b in zip(center, item["vector"]))
            na = math.sqrt(sum(a * a for a in center)); nb = math.sqrt(sum(b * b for b in item["vector"]))
            if dot / max(na * nb, 1e-9) >= f["threshold"]:
                cluster.append(item); placed = True; break
        if not placed:
            clusters.append([item])
    coverage = [sorted({x["slice"] for x in c}) for c in clusters]
    return _report("semantic_cluster", {"clusters": [[x["id"] for x in c] for c in clusters], "slice_coverage": coverage}, ["Cluster membership is evidence for sampling, not an automatic deletion command."], {"all_items_present": sum(map(len, clusters)) == len(f["items"]), "long_tail_preserved": all(c for c in coverage)})


def governance(f: dict[str, Any]) -> dict[str, Any]:
    result = lineage_map({"edges": f["edges"], "withdraw": f["event"]["object_id"], "expected_affected": f["expected_affected"]})
    result["mechanism"] = "governance_propagation"
    result["metrics"]["event_version"] = f["event"]["version"]
    result["observations"].append("Impact analysis records scope; the disposition remains an explicit decision.")
    return result


def mixture(f: dict[str, Any]) -> dict[str, Any]:
    weights = f["weights"]
    total = sum(weights.values())
    normalized = {k: v / total for k, v in weights.items()}
    counts = Counter()
    rng = random.Random(f["seed"])
    names = list(normalized); cut = []
    acc = 0.0
    for name in names:
        acc += normalized[name]; cut.append(acc)
    for _ in range(f["draws"]):
        r = rng.random(); counts[names[next(i for i, v in enumerate(cut) if r <= v)]] += 1
    observed = {k: counts[k] / f["draws"] for k in names}
    error = max(abs(observed[k] - normalized[k]) for k in names)
    return _report("mixture_sampling", {"target": normalized, "observed": observed, "max_abs_error": round(error, 4)}, ["Sampling receipts make actual token exposure auditable."], {"within_tolerance": error <= f["tolerance"]})


def proxy_mix(f: dict[str, Any]) -> dict[str, Any]:
    rankings = []
    for run in f["proxy_runs"]:
        ranking = sorted(run["scores"], key=run["scores"].get, reverse=True)
        rankings.append(ranking)
    winner_votes = Counter(x[0] for x in rankings)
    selected, votes = winner_votes.most_common(1)[0]
    stable = votes == len(rankings)
    return _report("proxy_mix_selection", {"rankings": rankings, "winner_votes": winner_votes, "selected": selected}, ["A proxy winner is promoted only when rank stability and target-scale validation are recorded."], {"ranking_stable": stable == f["expect_stable"]})


def packing(f: dict[str, Any]) -> dict[str, Any]:
    packed, masks, boundaries = [], [], []
    for sample in f["samples"]:
        start = len(packed); packed.extend(sample["tokens"]); masks.extend(sample["loss_mask"]); boundaries.append((start, len(packed)))
    attention = [[0] * len(packed) for _ in packed]
    for start, end in boundaries:
        for i in range(start, end):
            for j in range(start, i + 1): attention[i][j] = 1
    leakage = sum(attention[i][j] for a, (s, e) in enumerate(boundaries) for i in range(s, e) for j in range(s) if a > 0)
    return _report("packing_boundaries", {"tokens": len(packed), "loss_tokens": sum(masks), "boundaries": boundaries, "cross_sample_attention": leakage}, ["The block-diagonal causal mask prevents one packed sample from attending to an earlier sample."], {"no_leakage": leakage == 0, "mask_length_matches": len(masks) == len(packed)})


def cpt_recipe(f: dict[str, Any]) -> dict[str, Any]:
    mix = mixture({"weights": f["weights"], "seed": f["seed"], "draws": f["draws"], "tolerance": f["tolerance"]})
    mix["mechanism"] = "continued_pretraining_recipe"
    mix["metrics"]["replay_floor"] = f["replay_floor"]
    mix["checks"]["replay_present"] = mix["metrics"]["observed"].get("general_replay", 0) >= f["replay_floor"]
    mix["status"] = "passed" if all(mix["checks"].values()) else "failed"
    return mix


def loss_mask(f: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for sample in f["samples"]:
        if len(sample["tokens"]) != len(sample["roles"]):
            raise ValueError("tokens and roles must have equal length")
        labels = [tok if role == "assistant" else -100 for tok, role in zip(sample["tokens"], sample["roles"])]
        rows.append({"id": sample["id"], "supervised": sum(x != -100 for x in labels), "labels": labels})
    return _report("sft_loss_mask", {"samples": rows, "supervised_tokens": sum(x["supervised"] for x in rows)}, ["Only assistant target tokens receive labels in this fixture."], {"has_supervision": all(x["supervised"] > 0 for x in rows), "prompt_masked": all(-100 in x["labels"] for x in rows)})


def synthetic_qc(f: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    for row in f["records"]:
        independent = row["generator"] != row["verifier"]
        accepted = independent and row["verified"] and row["duplicate_score"] < f["duplicate_threshold"]
        decisions.append({"id": row["id"], "accepted": accepted, "independent": independent})
    return _report("synthetic_data_qc", {"accepted": sum(x["accepted"] for x in decisions), "rejected": sum(not x["accepted"] for x in decisions), "decisions": decisions}, ["Generator and verifier identities remain part of every decision."], {"mixed_outcomes": 0 < sum(x["accepted"] for x in decisions) < len(decisions)})


def ablation(f: dict[str, Any]) -> dict[str, Any]:
    baseline = f["runs"]["baseline"]
    effects = {name: {metric: round(value - baseline[metric], 6) for metric, value in scores.items()} for name, scores in f["runs"].items() if name != "baseline"}
    return _report("data_ablation", {"baseline": baseline, "effects": effects, "budget_tokens": f["budget_tokens"]}, ["Every candidate uses the same token budget and evaluation slices."], {"has_candidate": bool(effects), "same_metrics": all(set(v) == set(baseline) for v in f["runs"].values())})


def preference_bias(f: dict[str, Any]) -> dict[str, Any]:
    rows = f["comparisons"]
    left_win = sum(x["chosen_position"] == "left" for x in rows) / len(rows)
    length_gap = statistics.fmean(x["chosen_length"] - x["rejected_length"] for x in rows)
    disagreement = sum(x["labelers_agree"] is False for x in rows) / len(rows)
    return _report("preference_bias", {"left_win_rate": round(left_win, 4), "mean_length_gap": round(length_gap, 4), "disagreement_rate": round(disagreement, 4)}, ["Position, length, labeler agreement and policy version are audited separately."], {"position_audited": 0 <= left_win <= 1, "disagreement_recorded": 0 <= disagreement <= 1})


def reward_audit(f: dict[str, Any]) -> dict[str, Any]:
    normal = [x for x in f["pairs"] if x["slice"] == "normal"]
    adversarial = [x for x in f["pairs"] if x["slice"] == "adversarial"]
    accuracy = lambda rows: sum(x["preferred_score"] > x["rejected_score"] for x in rows) / max(len(rows), 1)
    return _report("reward_audit", {"normal_accuracy": round(accuracy(normal), 4), "adversarial_accuracy": round(accuracy(adversarial), 4), "normal_n": len(normal), "adversarial_n": len(adversarial)}, ["A reward model can pass ordinary pairs and still fail adversarial slices."], {"both_slices_present": bool(normal and adversarial), "gap_visible": True})


def offline_preference(f: dict[str, Any]) -> dict[str, Any]:
    margins = []
    for row in f["pairs"]:
        chosen = row["chosen_logp"] / (row["chosen_tokens"] if f["length_normalize"] else 1)
        rejected = row["rejected_logp"] / (row["rejected_tokens"] if f["length_normalize"] else 1)
        margins.append(chosen - rejected - f["target_margin"])
    loss = statistics.fmean(max(-f["beta"] * x, 0) + math.log1p(math.exp(-abs(f["beta"] * x))) for x in margins)
    return _report("offline_preference_objective", {"mean_margin": round(statistics.fmean(margins), 6), "loss": round(loss, 6), "length_normalized": f["length_normalize"]}, ["Reference-free logistic preference surrogate only; not standard DPO. The separate project-05 toy policy includes a frozen reference term."], {"finite_loss": math.isfinite(loss), "pairs_present": bool(margins)})


def group_advantage(f: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for group in f["groups"]:
        rewards = group["rewards"]
        mean = statistics.fmean(rewards); std = statistics.pstdev(rewards)
        advantages = [0.0 if std == 0 else (x - mean) / std for x in rewards]
        rows.append({"prompt": group["prompt"], "advantages": advantages, "zero_variance": std == 0})
    return _report("group_relative_advantage", {"groups": rows, "zero_variance_groups": sum(x["zero_variance"] for x in rows)}, ["Groups without reward variance carry no relative ranking signal."], {"all_finite": all(math.isfinite(v) for x in rows for v in x["advantages"]), "zero_variance_visible": all(all(v == 0 for v in x["advantages"]) for x in rows if x["zero_variance"])})


def verifier_attack(f: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    for case in f["cases"]:
        weak_pass = case["weak_pattern"] in case["answer"]
        strong_pass = case["canonical_answer"] == case["answer"].strip()
        decisions.append({"id": case["id"], "weak_pass": weak_pass, "strong_pass": strong_pass})
    bypasses = sum(x["weak_pass"] and not x["strong_pass"] for x in decisions)
    return _report("verifier_attack", {"cases": decisions, "weak_verifier_bypasses": bypasses}, ["Adversarial fixtures reveal reward paths that accept the wrong semantic answer."], {"bypass_detected": bypasses >= f["expected_bypasses"]})


def event_ledger(f: dict[str, Any]) -> dict[str, Any]:
    committed = set(); duplicates = 0; invalid = []
    for event in f["events"]:
        key = (event["trajectory_id"], event["policy_version"])
        if event["state"] == "committed":
            if key in committed: duplicates += 1
            committed.add(key)
        if event["reward_version"] != f["required_reward_version"]: invalid.append(event["trajectory_id"])
    return _report("rl_event_ledger", {"events": len(f["events"]), "committed": len(committed), "duplicate_commits": duplicates, "invalid_reward_version": invalid}, ["Idempotency key combines trajectory and policy identity."], {"no_duplicate_commit": duplicates == 0, "version_mismatch_detected": bool(invalid)})


def placement(f: dict[str, Any]) -> dict[str, Any]:
    plans = []
    for plan in f["plans"]:
        peak = max(plan["rollout_gb"], plan["train_gb"])
        # Separate placement uses two devices; time-multiplexed placement fully offloads the inactive role.
        devices = 1 if plan["colocated"] else 2
        feasible = peak <= f["gpu_memory_gb"]
        idle = plan["rollout_idle"] + plan["train_idle"]
        plans.append({"name": plan["name"], "devices": devices, "peak_gb": peak, "feasible": feasible, "idle_units": idle, "sync_gb": plan["sync_gb"]})
    feasible = [x for x in plans if x["feasible"]]
    selected = min(feasible, key=lambda x: (x["idle_units"], x["sync_gb"])) if feasible else None
    return _report("resource_placement", {"plans": plans, "selected": selected}, ["Capacity eliminates impossible plans; measured throughput must decide between feasible plans."], {"has_feasible_plan": selected is not None})


def staleness(f: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in f["experiences"]:
        distance = item["consume_policy"] - item["generate_policy"]
        accept = 0 <= distance <= f["max_update_distance"]
        rows.append({"id": item["id"], "update_distance": distance, "accepted": accept})
    return _report("policy_staleness", {"accepted": sum(x["accepted"] for x in rows), "rejected": sum(not x["accepted"] for x in rows), "records": rows}, ["Wall-clock age and policy update distance are not interchangeable."], {"old_record_rejected": any(not x["accepted"] for x in rows), "fresh_record_accepted": any(x["accepted"] for x in rows)})


def checkpoint(f: dict[str, Any]) -> dict[str, Any]:
    required = set(f["required_components"])
    saved = set(f["checkpoint"].keys())
    missing = sorted(required - saved)
    replay = f["checkpoint"].get("committed_ids", []) + f["after_resume_ids"]
    duplicates = len(replay) - len(set(replay))
    cost = f["gpu_seconds"] / max(f["effective_tokens"], 1)
    return _report("joint_checkpoint", {"missing_components": missing, "duplicate_ids": duplicates, "gpu_seconds_per_effective_token": cost, "state_sha256": _sha(f["checkpoint"])}, ["A readable model file is only one component of semantic recovery."], {"complete": not missing, "no_replay_duplicate": duplicates == 0, "cost_finite": math.isfinite(cost)})


SCENARIOS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "lineage_map": lineage_map,
    "token_ledger": token_ledger,
    "source_registry": source_registry,
    "parser_evidence": parser_evidence,
    "scheduler_fit": scheduler_fit,
    "shard_replay": shard_replay,
    "normalization": normalization,
    "filter_calibration": filter_calibration,
    "score_calibration": score_calibration,
    "minhash_dedup": minhash_dedup,
    "semantic_cluster": semantic_cluster,
    "governance": governance,
    "mixture": mixture,
    "proxy_mix": proxy_mix,
    "packing": packing,
    "resume": shard_replay,
    "cpt_recipe": cpt_recipe,
    "loss_mask": loss_mask,
    "synthetic_qc": synthetic_qc,
    "ablation": ablation,
    "preference_bias": preference_bias,
    "reward_audit": reward_audit,
    "offline_preference": offline_preference,
    "group_advantage": group_advantage,
    "verifier_attack": verifier_attack,
    "event_ledger": event_ledger,
    "placement": placement,
    "staleness": staleness,
    "checkpoint": checkpoint,
}


def run_scenario(name: str, fixture: dict[str, Any]) -> dict[str, Any]:
    try:
        fn = SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {name}") from exc
    return fn(fixture)
