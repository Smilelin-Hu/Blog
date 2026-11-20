#!/usr/bin/env python3
import argparse
import heapq
import random
import statistics


def percentile(values, q):
    values = sorted(values)
    i = min(len(values) - 1, int((len(values) - 1) * q))
    return values[i]


def make_requests(n, qps, seed):
    rng = random.Random(seed)
    now = 0.0
    reqs = []
    for i in range(n):
        now += rng.expovariate(qps) * 1000.0
        # 混合短/长 Prompt 与短/长输出，单位为 token。
        prompt = rng.choice([128, 256, 512, 2048, 4096])
        output = rng.choice([32, 64, 128, 256])
        reqs.append((i, now, prompt, output))
    return reqs


def run_monolithic(reqs, workers, p_ms_per_token, d_ms_per_token):
    heap = [0.0] * workers
    heapq.heapify(heap)
    ttft, tpot, e2e = [], [], []
    for _, arrival, pin, pout in reqs:
        free = heapq.heappop(heap)
        start = max(arrival, free)
        p_ms = pin * p_ms_per_token
        first = start + p_ms + d_ms_per_token
        finish = first + max(0, pout - 1) * d_ms_per_token
        heapq.heappush(heap, finish)
        ttft.append(first - arrival)
        tpot.append(d_ms_per_token)
        e2e.append(finish - arrival)
    return ttft, tpot, e2e


def run_disagg(reqs, p_workers, d_workers, p_ms_per_token,
               d_ms_per_token, xfer_base_ms, gbps, kv_bytes_per_token):
    p_heap = [0.0] * p_workers
    d_heap = [0.0] * d_workers
    heapq.heapify(p_heap)
    heapq.heapify(d_heap)
    ttft, tpot, e2e, xfers = [], [], [], []

    for _, arrival, pin, pout in reqs:
        p_free = heapq.heappop(p_heap)
        p_start = max(arrival, p_free)
        p_done = p_start + pin * p_ms_per_token
        heapq.heappush(p_heap, p_done)

        kv_bytes = pin * kv_bytes_per_token
        xfer_ms = xfer_base_ms + kv_bytes * 8 / (gbps * 1e9) * 1000
        xfers.append(xfer_ms)
        kv_ready = p_done + xfer_ms

        d_free = heapq.heappop(d_heap)
        d_start = max(kv_ready, d_free)
        first = d_start + d_ms_per_token
        finish = first + max(0, pout - 1) * d_ms_per_token
        heapq.heappush(d_heap, finish)

        ttft.append(first - arrival)
        tpot.append(d_ms_per_token)
        e2e.append(finish - arrival)
    return ttft, tpot, e2e, xfers


def report(name, ttft, tpot, e2e, ttft_slo, tpot_slo):
    good = sum(a <= ttft_slo and b <= tpot_slo for a, b in zip(ttft, tpot))
    print(f"\n[{name}]")
    print(f"TTFT p50/p99: {percentile(ttft,.50):.1f}/{percentile(ttft,.99):.1f} ms")
    print(f"TPOT p50/p99: {percentile(tpot,.50):.1f}/{percentile(tpot,.99):.1f} ms")
    print(f"E2E  p50/p99: {percentile(e2e,.50):.1f}/{percentile(e2e,.99):.1f} ms")
    print(f"Goodput requests: {good}/{len(ttft)} ({good/len(ttft):.1%})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=500)
    p.add_argument("--qps", type=float, default=3.0)
    p.add_argument("--mono-workers", type=int, default=4)
    p.add_argument("--p-workers", type=int, default=1)
    p.add_argument("--d-workers", type=int, default=3)
    p.add_argument("--prefill-ms-per-token", type=float, default=0.04)
    p.add_argument("--decode-ms-per-token", type=float, default=8.0)
    p.add_argument("--p-specialization-speedup", type=float, default=2.0)
    p.add_argument("--d-specialization-speedup", type=float, default=2.0)
    p.add_argument("--xfer-base-ms", type=float, default=0.3)
    p.add_argument("--link-gbps", type=float, default=100.0)
    p.add_argument("--kv-bytes-per-token", type=int, default=131072)
    p.add_argument("--ttft-slo-ms", type=float, default=500.0)
    p.add_argument("--tpot-slo-ms", type=float, default=20.0)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    reqs = make_requests(a.requests, a.qps, a.seed)

    mono = run_monolithic(reqs, a.mono_workers,
                          a.prefill_ms_per_token, a.decode_ms_per_token)
    dis = run_disagg(reqs, a.p_workers, a.d_workers,
                     a.prefill_ms_per_token / a.p_specialization_speedup,
                     a.decode_ms_per_token / a.d_specialization_speedup,
                     a.xfer_base_ms, a.link_gbps, a.kv_bytes_per_token)

    report("monolithic", *mono, a.ttft_slo_ms, a.tpot_slo_ms)
    report("disaggregated", *dis[:3], a.ttft_slo_ms, a.tpot_slo_ms)
    print(f"KV transfer mean/p99: {statistics.mean(dis[3]):.2f}/"
          f"{percentile(dis[3], .99):.2f} ms")
    print("注意：这是教学排队模型，不是硬件性能结论。")


if __name__ == "__main__":
    main()
