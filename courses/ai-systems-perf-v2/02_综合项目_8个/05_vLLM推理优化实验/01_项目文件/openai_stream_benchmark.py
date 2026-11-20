#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def one_request(url, model, prompt, max_tokens, timeout, request_id):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        method="POST",
    )
    start = time.perf_counter()
    first_content = None
    content_events = 0
    completion_tokens = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                usage = event.get("usage")
                if usage and usage.get("completion_tokens") is not None:
                    completion_tokens = int(usage["completion_tokens"])
                choices = event.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    if delta.get("content"):
                        content_events += 1
                        if first_content is None:
                            first_content = time.perf_counter()
        end = time.perf_counter()
        if first_content is None:
            raise RuntimeError("响应完成但没有收到内容 Token")
        output_tokens = completion_tokens or content_events
        e2e = end - start
        ttft = first_content - start
        tpot = (e2e - ttft) / (output_tokens - 1) if output_tokens > 1 else None
        return {
            "id": request_id,
            "ok": True,
            "ttft_s": ttft,
            "e2e_s": e2e,
            "tpot_s": tpot,
            "output_tokens": output_tokens,
            "token_count_source": "usage" if completion_tokens is not None else "content_events",
        }
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as error:
        return {"id": request_id, "ok": False, "error": repr(error)}


def main():
    parser = argparse.ArgumentParser(description="OpenAI SSE 推理 Benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--prompt-words", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ttft-slo", type=float, default=1.0)
    parser.add_argument("--tpot-slo", type=float, default=0.05)
    parser.add_argument("--output", default="reports/benchmark.json")
    args = parser.parse_args()
    if min(args.requests, args.concurrency, args.max_tokens,
           args.prompt_words, args.timeout) <= 0:
        raise ValueError("负载参数必须大于 0")

    prompt = "请用简洁语言解释 AI 系统性能工程。 " * args.prompt_words
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    wall_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(one_request, url, args.model, prompt, args.max_tokens,
                        args.timeout, request_id)
            for request_id in range(args.requests)
        ]
        rows = [future.result() for future in concurrent.futures.as_completed(futures)]
    wall = time.perf_counter() - wall_start

    successful = [row for row in rows if row["ok"]]
    ttft = [row["ttft_s"] for row in successful]
    e2e = [row["e2e_s"] for row in successful]
    tpot = [row["tpot_s"] for row in successful if row["tpot_s"] is not None]
    output_tokens = sum(row["output_tokens"] for row in successful)
    good = [
        row for row in successful
        if row["ttft_s"] <= args.ttft_slo
        and row["tpot_s"] is not None
        and row["tpot_s"] <= args.tpot_slo
    ]
    result = {
        "model": args.model,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "successful": len(successful),
        "success_rate": len(successful) / args.requests,
        "wall_seconds": wall,
        "request_throughput": len(successful) / wall,
        "output_token_throughput": output_tokens / wall,
        "goodput_requests_per_second": len(good) / wall,
        "ttft_s": {"p50": percentile(ttft, 0.50), "p95": percentile(ttft, 0.95),
                   "p99": percentile(ttft, 0.99)},
        "tpot_s": {"p50": percentile(tpot, 0.50), "p95": percentile(tpot, 0.95),
                   "p99": percentile(tpot, 0.99)},
        "e2e_s": {"p50": percentile(e2e, 0.50), "p95": percentile(e2e, 0.95),
                  "p99": percentile(e2e, 0.99)},
        "token_count_sources": sorted(set(
            row["token_count_source"] for row in successful
        )),
        "errors": [row for row in rows if not row["ok"]],
        "raw": sorted(rows, key=lambda row: row["id"]),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
