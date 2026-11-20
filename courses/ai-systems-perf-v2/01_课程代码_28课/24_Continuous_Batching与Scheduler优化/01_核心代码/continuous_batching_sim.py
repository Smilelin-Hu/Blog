#!/usr/bin/env python3
import argparse
import copy
import math
import random
import statistics
from dataclasses import dataclass, field


@dataclass
class Request:
    rid: int
    arrival_ms: float
    prompt_tokens: int
    output_tokens: int
    prompt_remaining: int = 0
    generated: int = 0
    first_token_ms: float | None = None
    finish_ms: float | None = None
    token_times: list[float] = field(default_factory=list)

    def reset(self):
        self.prompt_remaining = self.prompt_tokens
        self.generated = 0
        self.first_token_ms = None
        self.finish_ms = None
        self.token_times = []
        return self


def percentile(values, q):
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
    return values[index]


def make_workload(args):
    rng = random.Random(args.seed)
    now = 0.0
    requests = []
    for rid in range(args.requests):
        if rid:
            now += rng.expovariate(args.request_rate / 1000.0)
        prompt = rng.randint(args.prompt_min, args.prompt_max)
        output = rng.randint(args.output_min, args.output_max)
        requests.append(Request(rid, now, prompt, output).reset())
    return requests


def static_batching(source, args):
    requests = copy.deepcopy(source)
    waiting, completed = [], []
    next_id, now = 0, 0.0
    total_slots = useful_slots = 0

    while len(completed) < len(requests):
        while next_id < len(requests) and requests[next_id].arrival_ms <= now:
            waiting.append(requests[next_id])
            next_id += 1

        if not waiting:
            now = max(now, requests[next_id].arrival_ms)
            continue

        batch = waiting[: args.max_seqs]
        del waiting[: len(batch)]

        # 静态 Prompt Batch 按最长 Prompt Padding。
        padded_prefill_tokens = len(batch) * max(r.prompt_tokens for r in batch)
        now += args.base_ms + padded_prefill_tokens * args.prefill_ms_per_token

        width = len(batch)
        max_output = max(r.output_tokens for r in batch)
        for step in range(max_output):
            now += args.base_ms + width * args.decode_ms_per_seq
            total_slots += width
            for r in batch:
                if step < r.output_tokens:
                    useful_slots += 1
                    r.generated += 1
                    r.token_times.append(now)
                    if r.first_token_ms is None:
                        r.first_token_ms = now
                    if r.generated == r.output_tokens:
                        r.finish_ms = now

            while next_id < len(requests) and requests[next_id].arrival_ms <= now:
                waiting.append(requests[next_id])
                next_id += 1

        completed.extend(batch)

    return completed, now, useful_slots / total_slots


def continuous_batching(source, args):
    requests = copy.deepcopy(source)
    waiting, running, completed = [], [], []
    next_id, now = 0, 0.0

    while len(completed) < len(requests):
        while next_id < len(requests) and requests[next_id].arrival_ms <= now:
            waiting.append(requests[next_id])
            next_id += 1

        if not running and not waiting:
            now = max(now, requests[next_id].arrival_ms)
            continue

        token_budget = args.token_budget
        decode_reqs = [r for r in running if r.prompt_remaining == 0]
        decode_reqs = decode_reqs[:token_budget]
        token_budget -= len(decode_reqs)

        # 先推进已有的 Partial Prefill，再接收新请求。
        prefill_plan = []
        for r in [x for x in running if x.prompt_remaining > 0]:
            if token_budget <= 0:
                break
            take = min(r.prompt_remaining, token_budget)
            prefill_plan.append((r, take))
            token_budget -= take

        while waiting and len(running) < args.max_seqs and token_budget > 0:
            r = waiting[0]
            if not args.chunked_prefill and r.prompt_remaining > token_budget:
                break
            waiting.pop(0)
            running.append(r)
            take = min(r.prompt_remaining, token_budget)
            prefill_plan.append((r, take))
            token_budget -= take

        prefill_tokens = sum(take for _, take in prefill_plan)
        if not decode_reqs and prefill_tokens == 0:
            # 容量配置不可能推进请求，防止静默死循环。
            raise RuntimeError("scheduler made no progress; increase token budget")

        now += (
            args.base_ms
            + prefill_tokens * args.prefill_ms_per_token
            + len(decode_reqs) * args.decode_ms_per_seq
        )

        for r, take in prefill_plan:
            r.prompt_remaining -= take

        for r in decode_reqs:
            r.generated += 1
            r.token_times.append(now)
            if r.first_token_ms is None:
                r.first_token_ms = now
            if r.generated == r.output_tokens:
                r.finish_ms = now
                completed.append(r)

        finished_ids = {r.rid for r in completed}
        running = [r for r in running if r.rid not in finished_ids]

    useful = sum(r.output_tokens for r in completed)
    return completed, now, 1.0 if useful else 0.0


def summarize(name, requests, makespan, slot_efficiency):
    ttft = [r.first_token_ms - r.arrival_ms for r in requests]
    e2e = [r.finish_ms - r.arrival_ms for r in requests]
    itl = []
    for r in requests:
        itl.extend(b - a for a, b in zip(r.token_times, r.token_times[1:]))
    outputs = sum(r.output_tokens for r in requests)
    duration_s = makespan / 1000.0
    print(f"\n=== {name} ===")
    print(f"Makespan              : {makespan:.2f} ms")
    print(f"Request throughput    : {len(requests) / duration_s:.2f} req/s")
    print(f"Output throughput     : {outputs / duration_s:.2f} token/s")
    print(f"TTFT P50 / P99        : {percentile(ttft, .50):.2f} / {percentile(ttft, .99):.2f} ms")
    print(f"E2E  P50 / P99        : {percentile(e2e, .50):.2f} / {percentile(e2e, .99):.2f} ms")
    print(f"ITL  P50 / P99        : {percentile(itl, .50):.2f} / {percentile(itl, .99):.2f} ms")
    print(f"Decode slot efficiency: {slot_efficiency * 100:.2f}%")


def parse_args():
    p = argparse.ArgumentParser(description="Static vs continuous batching simulator")
    p.add_argument("--requests", type=int, default=120)
    p.add_argument("--request-rate", type=float, default=300.0)
    p.add_argument("--prompt-min", type=int, default=32)
    p.add_argument("--prompt-max", type=int, default=512)
    p.add_argument("--output-min", type=int, default=8)
    p.add_argument("--output-max", type=int, default=96)
    p.add_argument("--max-seqs", type=int, default=16)
    p.add_argument("--token-budget", type=int, default=512)
    p.add_argument("--base-ms", type=float, default=0.12)
    p.add_argument("--prefill-ms-per-token", type=float, default=0.003)
    p.add_argument("--decode-ms-per-seq", type=float, default=0.055)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--chunked-prefill", action=argparse.BooleanOptionalAction, default=True)
    return p.parse_args()


def main():
    args = parse_args()
    if args.token_budget < args.max_seqs:
        raise ValueError("token_budget should be >= max_seqs")
    workload = make_workload(args)
    static_result = static_batching(workload, args)
    continuous_result = continuous_batching(workload, args)
    summarize("Static request-level batching", *static_result)
    summarize("Continuous iteration-level batching", *continuous_result)
    print("\nModel boundary: numbers are synthetic; compare policies, not hardware speed.")


if __name__ == "__main__":
    main()
