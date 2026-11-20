#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def erlang_c_wait(arrival_rate, service_seconds, servers):
    offered = arrival_rate * service_seconds
    rho = offered / servers
    if rho >= 1:
        return math.inf, rho
    series = sum(offered ** n / math.factorial(n) for n in range(servers))
    tail = offered ** servers / math.factorial(servers) / (1 - rho)
    probability_wait = tail / (series + tail)
    wait_seconds = probability_wait * service_seconds / (servers * (1 - rho))
    return wait_seconds, rho


def main():
    parser = argparse.ArgumentParser(description="P/D 解耦容量规划器")
    parser.add_argument("--arrival-rate", type=float, default=4.0)
    parser.add_argument("--prefill-workers", type=int, default=2)
    parser.add_argument("--decode-workers", type=int, default=4)
    parser.add_argument("--prefill-ms", type=float, default=200.0)
    parser.add_argument("--decode-ms-per-token", type=float, default=20.0)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--input-tokens", type=int, default=2048)
    parser.add_argument("--layers", type=int, default=32)
    parser.add_argument("--kv-heads", type=int, default=8)
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--dtype-bytes", type=float, default=2.0)
    parser.add_argument("--link-gbps", type=float, default=100.0)
    parser.add_argument("--link-efficiency", type=float, default=0.70)
    parser.add_argument("--fixed-transfer-ms", type=float, default=0.2)
    parser.add_argument("--output", default="reports/capacity.json")
    args = parser.parse_args()

    positive = [args.arrival_rate, args.prefill_workers, args.decode_workers,
                args.prefill_ms, args.decode_ms_per_token, args.output_tokens,
                args.input_tokens, args.layers, args.kv_heads, args.head_dim,
                args.dtype_bytes, args.link_gbps]
    if any(value <= 0 for value in positive):
        raise ValueError("容量参数必须大于 0")
    if not 0 < args.link_efficiency <= 1:
        raise ValueError("link-efficiency 必须位于 (0, 1]")

    kv_bytes_per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.dtype_bytes
    kv_bytes = args.input_tokens * kv_bytes_per_token
    effective_bytes_per_second = args.link_gbps * 1e9 / 8 * args.link_efficiency
    transfer_seconds = args.fixed_transfer_ms / 1000 + kv_bytes / effective_bytes_per_second
    required_link_bytes_per_second = args.arrival_rate * kv_bytes
    link_utilization = required_link_bytes_per_second / effective_bytes_per_second

    prefill_service = args.prefill_ms / 1000
    decode_service = args.decode_ms_per_token / 1000 * args.output_tokens
    prefill_wait, prefill_rho = erlang_c_wait(
        args.arrival_rate, prefill_service, args.prefill_workers
    )
    decode_wait, decode_rho = erlang_c_wait(
        args.arrival_rate, decode_service, args.decode_workers
    )
    stable = all(value < 1 for value in (prefill_rho, decode_rho, link_utilization))

    if stable:
        ttft = (prefill_wait + prefill_service + transfer_seconds +
                decode_wait + args.decode_ms_per_token / 1000)
        e2e = ttft + (args.output_tokens - 1) * args.decode_ms_per_token / 1000
    else:
        ttft = None
        e2e = None

    result = {
        "stable": stable,
        "kv": {
            "bytes_per_token": kv_bytes_per_token,
            "mib_per_request": kv_bytes / 2**20,
            "required_link_gbps": required_link_bytes_per_second * 8 / 1e9,
            "effective_link_gbps": args.link_gbps * args.link_efficiency,
            "link_utilization": link_utilization,
            "transfer_ms": transfer_seconds * 1000,
        },
        "prefill": {
            "workers": args.prefill_workers,
            "utilization": prefill_rho,
            "mean_queue_ms": None if math.isinf(prefill_wait) else prefill_wait * 1000,
        },
        "decode": {
            "workers": args.decode_workers,
            "utilization": decode_rho,
            "mean_queue_ms": None if math.isinf(decode_wait) else decode_wait * 1000,
        },
        "latency_estimate": {
            "ttft_ms": None if ttft is None else ttft * 1000,
            "e2e_ms": None if e2e is None else e2e * 1000,
        },
        "warning": (
            "Erlang-C 假设泊松到达、指数服务时间与同质 Worker；"
            "未包含 Batch、抢占、长尾、KV 元数据和故障。"
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
