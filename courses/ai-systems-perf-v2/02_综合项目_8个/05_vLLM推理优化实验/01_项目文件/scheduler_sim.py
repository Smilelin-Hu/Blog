#!/usr/bin/env python3
import argparse
import heapq
import json
import random
import statistics


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    weight = position - low
    return values[low] * (1 - weight) + values[high] * weight


def simulate(requests, arrival_rate, max_sequences, token_budget,
             prefill_tokens, output_tokens, tick_ms, seed):
    rng = random.Random(seed)
    arrivals = []
    now = 0.0
    for request_id in range(requests):
        now += rng.expovariate(arrival_rate) * 1000.0
        heapq.heappush(arrivals, (now, request_id))

    waiting = []
    running = []
    completed = []
    clock = 0.0
    while len(completed) < requests:
        while arrivals and arrivals[0][0] <= clock:
            arrival, request_id = heapq.heappop(arrivals)
            waiting.append({
                "id": request_id,
                "arrival": arrival,
                "prefill_left": prefill_tokens,
                "decode_left": output_tokens,
                "first_token": None,
            })
        while waiting and len(running) < max_sequences:
            running.append(waiting.pop(0))

        budget = token_budget
        for request in list(running):
            if budget <= 0:
                break
            if request["prefill_left"] > 0:
                consumed = min(request["prefill_left"], budget)
                request["prefill_left"] -= consumed
                budget -= consumed
            elif request["decode_left"] > 0 and budget > 0:
                request["decode_left"] -= 1
                budget -= 1
                if request["first_token"] is None:
                    request["first_token"] = clock + tick_ms

        clock += tick_ms
        for request in list(running):
            if request["decode_left"] == 0:
                completed.append({
                    "ttft_ms": request["first_token"] - request["arrival"],
                    "e2e_ms": clock - request["arrival"],
                })
                running.remove(request)

        if not running and not waiting and arrivals and arrivals[0][0] > clock:
            clock = arrivals[0][0]

    ttft = [item["ttft_ms"] for item in completed]
    e2e = [item["e2e_ms"] for item in completed]
    return {
        "requests": requests,
        "wall_seconds": clock / 1000.0,
        "request_throughput": requests / (clock / 1000.0),
        "output_token_throughput": requests * output_tokens / (clock / 1000.0),
        "ttft_p50_ms": percentile(ttft, 0.50),
        "ttft_p95_ms": percentile(ttft, 0.95),
        "e2e_p50_ms": percentile(e2e, 0.50),
        "e2e_p95_ms": percentile(e2e, 0.95),
        "mean_ttft_ms": statistics.mean(ttft),
        "warning": "离散事件模型用于理解趋势，不是 vLLM 或 GPU 性能预测。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--arrival-rate", type=float, default=8.0)
    parser.add_argument("--max-sequences", type=int, default=16)
    parser.add_argument("--token-budget", type=int, default=512)
    parser.add_argument("--prefill-tokens", type=int, default=256)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--tick-ms", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if min(args.requests, args.arrival_rate, args.max_sequences,
           args.token_budget, args.prefill_tokens, args.output_tokens,
           args.tick_ms) <= 0:
        raise ValueError("所有负载参数必须大于 0")
    print(json.dumps(simulate(**vars(args)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
