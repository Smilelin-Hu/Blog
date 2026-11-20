#!/usr/bin/env python3
import argparse
import json
import math
import random
import statistics
import time
import urllib.request
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def request(url, model, prompt, max_tokens, timeout):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.load(response)
    elapsed = time.perf_counter() - start
    usage = body.get("usage") or {}
    return elapsed, usage.get("prompt_tokens"), usage.get("completion_tokens")


def main():
    parser = argparse.ArgumentParser(description="Prefix Cache A/B Benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--prefix-words", type=int, default=512)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="reports/prefix.json")
    args = parser.parse_args()
    if min(args.requests, args.prefix_words, args.max_tokens, args.timeout) <= 0:
        raise ValueError("负载参数必须大于 0")

    rng = random.Random(args.seed)
    shared_prefix = "统一系统知识：AI 性能工程需要可复现测量。 " * args.prefix_words
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    shared_times, random_times = [], []
    token_rows = []
    for index in range(args.requests):
        suffix = f"请求 {index}：解释 KV Cache 的作用。"
        elapsed, prompt_tokens, completion_tokens = request(
            url, args.model, shared_prefix + suffix, args.max_tokens, args.timeout
        )
        shared_times.append(elapsed)
        token_rows.append((prompt_tokens, completion_tokens))

        nonce = " ".join(str(rng.getrandbits(64)) for _ in range(args.prefix_words))
        elapsed, _, _ = request(
            url, args.model, nonce + suffix, args.max_tokens, args.timeout
        )
        random_times.append(elapsed)

    result = {
        "requests_per_group": args.requests,
        "shared_prefix_latency_s": {
            "p50": percentile(shared_times, 0.50),
            "p95": percentile(shared_times, 0.95),
            "mean": statistics.mean(shared_times),
        },
        "random_prefix_latency_s": {
            "p50": percentile(random_times, 0.50),
            "p95": percentile(random_times, 0.95),
            "mean": statistics.mean(random_times),
        },
        "usage_samples": token_rows,
        "warning": "文本 Word 数不等于 Token 数；正式报告以服务 Usage/模型 Tokenizer 为准。",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
