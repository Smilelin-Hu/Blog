# vLLM 推理优化

本项目围绕 vLLM 推理服务完成压测、瓶颈分析与参数调优，优化吞吐、延迟和并发能力。

重点不是把模型「启动起来」，而是把服务推进到「能用 SLO 驱动调优」：搭建 OpenAI 兼容服务，构造固定输入/输出长度的并发负载，测量 TTFT、TPOT、端到端延迟、请求吞吐、输出 Token 吞吐与成功率，然后只改变一个调度或内存参数完成优化闭环。

```text
容量估算 → 服务冷启动 → 单并发正确性
→ 并发扫描 → 找到饱和拐点 → 调整 Scheduler/KV/Prefix/并行
→ 重复 Benchmark → SLO 回归门禁 → 保存配置与原始结果
```

Level 0 使用纯 Python 模拟排队与 Prefill/Decode 竞争，不需要 GPU。Level 1 面向常见 NVIDIA GPU 并自动记录环境。Level 2 才验证 Tensor Parallel、FP8/FP4、NVLink 或架构专属 Kernel；没有对应硬件时不宣称完成这些特性验证。

## 1. 内容概览与交付物

做完之后应当能够：区分 TTFT、TPOT/ITL、E2E Latency、QPS、Tokens/s 与 Goodput；理解 Continuous Batching、Chunked Prefill、KV Cache 与 Scheduler 的耦合；使用 OpenAI 兼容流式接口测量首 Token 与生成阶段；扫描并发而不是只测最大吞吐；根据 SLO 找到最大可接受负载；正确调节 `max_num_batched_tokens`、`max_num_seqs`、模型长度和显存利用率；识别 OOM、抢占、排队、Tokenizer、网络与客户端瓶颈；生成可重复的服务配置、环境快照和回归报告。

前置知识：LLM 推理系统相关内容（Continuous Batching、PagedAttention、Prefill/Decode 分离）；Linux、Python、HTTP/SSE 与基本 GPU 监控；可下载且许可允许使用的 Hugging Face 模型；vLLM、驱动、CUDA 与 PyTorch 必须使用兼容组合，安装前锁定目标版本。

```text
vllm-serving-project/
├── scheduler_sim.py
├── openai_stream_benchmark.py
├── run_sweep.sh
├── reports/
│   ├── environment.txt
│   ├── server_command.txt
│   ├── baseline_c1.json
│   ├── baseline_c8.json
│   ├── optimized_c8.json
│   └── analysis.md
└── logs/
    └── server.log
```

`reports/analysis.md` 至少需要回答：饱和拐点出现在哪个并发；拐点前后 TTFT P95 与 TPOT P95 分别怎么变；改动的那个参数带来了什么收益、付出了什么代价；错误与抢占是否为零；结论的硬件、模型、长度与版本边界是什么。

## 2. 核心直觉：最优点在吞吐与排队之间

若并发从 1 增加到 C，GPU Batch 变大，通常会提高计算效率；但请求会在 Scheduler 和 Batch 中等待，TTFT 与 TPOT 也可能变差。

$$
Latency = T_{queue} + T_{prefill} + T_{decode} + T_{network}
$$

$$
TTFT = T_{queue} + T_{prefill} + T_{first\ decode} + T_{network,first}
$$

生成 N 个输出 Token 时，可用近似：

$$
TPOT \approx \frac{E2E - TTFT}{N - 1}
$$

分母是首 Token 之后的「Token 间隔数」，因此当 $N \le 1$ 时 TPOT 无定义，Benchmark 必须避免除零。这一点在代码里体现为 `tpot = None`，而不是 0 或 `inf`——把无定义写成 0 会让 P50 被人为拉低。

吞吐最大点不一定满足交互 SLO。定义：

$$
Goodput = \frac{N_{TTFT \le S_{TTFT}\ \land\ TPOT \le S_{TPOT}}}{T_{wall}}
$$

分子只统计「同时满足两条 SLO」的成功请求，失败请求与超时请求不计入。本项目最终选择 Goodput 最大且错误率、P95/P99 满足约束的配置，而不是 Token/s 最大的配置。

这里有一个容易忽略的口径细节：Goodput 的分母是整段压测墙钟时间，包含尾部排空阶段。因此并发扫描时若各组的 `requests` 数量不同，Goodput 不可直接横向比较，必须固定请求总数。

## 3. Level 0：Continuous Batching 排队模拟

### 3.1 scheduler_sim.py

模拟器把服务抽象成三个量：同时运行的序列上限 `max_sequences`、每个调度 Tick 可处理的 Token 预算 `token_budget`、以及每个请求的 Prefill 与 Decode 长度。Prefill 优先消耗预算，预算有剩余才轮到 Decode——这正是「长 Prefill 阻塞 Decode」的最小可复现模型。

保存为 `scheduler_sim.py`：

```python
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
```

几处刻意的设计值得单独说明：

- **到达过程用指数分布**：`rng.expovariate(arrival_rate)` 生成相邻请求间隔，对应泊松到达。这与「固定并发闭环压测」是两种负载模型，模拟器回答的是「给定到达率，系统会不会堆积」，而 Level 1 的客户端回答的是「给定并发，服务能撑多少」。
- **Tick 是离散步长，不是真实 Kernel 时间**：`tick_ms` 只是把「一个调度迭代」映射到时间轴的比例尺，改它等比例缩放所有延迟，不改变排队结构。
- **Decode 每 Tick 最多推进 1 个 Token**：这刻画了自回归生成的串行性，也是为什么增大 Token Budget 对 Decode 吞吐的帮助远小于对 Prefill 的帮助。
- **空转时直接跳到下一个到达**：避免在没有请求的时间段里空跑 Tick，保证 `wall_seconds` 反映真实负载窗口。
- **`simulate(**vars(args))`**：参数名与函数签名严格一致，改参数时两处必须同步，否则会抛 `TypeError` 而不是静默用默认值。

### 3.2 运行命令

```bash
python scheduler_sim.py --arrival-rate 4 --max-sequences 8 --token-budget 256
python scheduler_sim.py --arrival-rate 16 --max-sequences 8 --token-budget 256
python scheduler_sim.py --arrival-rate 16 --max-sequences 32 --token-budget 1024
```

三组构成一条递进链：第一组是欠载基线，第二组把到达率提高 4 倍但服务能力不变，第三组同时放宽序列上限与 Token 预算。

### 3.3 预期现象

当到达速率超过服务能力，排队快速增加，P95 TTFT 比吞吐更早恶化。这里可以用排队论给出一个粗略的判据：单请求的服务时间约为

$$
T_{service} \approx \left\lceil \frac{P_{prefill}}{B_{tick}} \right\rceil \cdot t_{tick} + N_{out} \cdot t_{tick}
$$

其中 $P_{prefill}$ 是 Prefill Token 数、$B_{tick}$ 是每 Tick 分给该请求的预算、$N_{out}$ 是输出 Token 数。默认参数下 Prefill 256、预算 256、输出 128、Tick 10 ms，单请求独占时约 $(1 + 128) \times 10 = 1290$ ms；`max_sequences=8` 时理论服务能力约 $8 / 1.29 \approx 6.2$ req/s。因此到达率 4 仍在容量内，到达率 16 已明显过载——这解释了为什么第二组的 P95 TTFT 会先于吞吐崩掉。

增加并发容量或 Token Budget 可能提高吞吐，也可能让单个 Tick 更昂贵；这个简化模型没有 GPU Kernel、KV 容量、Prefix Cache 或抢占，因此只能用于形成假设，不能写成实测结论。第三组把预算提到 1024 后，模拟器里 Prefill 一次就能吃完，但真实 GPU 上单批 1024 Token 的 Prefill 会显著拉长该 Tick 的执行时间，Decode 请求的 TPOT 反而可能变差——这个差异正是 Level 1 必须实测的原因。

## 4. Level 1：安装与启动 vLLM

### 4.1 环境隔离

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip uv
uv pip install "vllm==0.23.0"
python -m pip freeze > reports/requirements-lock.txt
vllm --version
vllm serve --help=all > reports/vllm-serve-help.txt
```

版本示例用于复现实验快照，不代表永远推荐。若官方稳定版、驱动或 GPU 支持矩阵已变化，应新建环境测试，不在原环境原地升级。

`vllm serve --help=all` 的输出必须落盘。vLLM 的调度与内存参数名在版本间变动频繁（例如 Prefix Caching 的开关形态、Chunked Prefill 的默认值），后续所有调优命令都以这份帮助为准，而不是以记忆中的参数名为准。

### 4.2 自动记录环境

```bash
mkdir -p reports logs
{
  date -Iseconds
  uname -a
  nvidia-smi -L
  nvidia-smi topo -m
  nvidia-smi --query-gpu=name,driver_version,memory.total,pci.bus_id,pstate,power.limit --format=csv
  python --version
  vllm --version
} 2>&1 | tee reports/environment.txt
```

这份快照里有两项经常被跳过但影响结论：`nvidia-smi topo -m` 决定多卡实验到底走 NVLink 还是 PCIe；`pstate` 与 `power.limit` 决定 GPU 是否处于降频状态。消费级卡在长时间压测后触发热限频，会让「后测的配置更慢」这种伪结论出现，因此性能对照实验应交替顺序或重复多轮。

### 4.3 启动基线服务

用一个当前机器能容纳、且许可允许使用的模型替换 `MODEL_ID`：

```bash
export MODEL_ID="your-org/your-model"
vllm serve "$MODEL_ID" \
  --host 127.0.0.1 --port 8000 \
  --dtype auto \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  2>&1 | tee logs/server.log
```

另开终端验证：

```bash
curl -s http://127.0.0.1:8000/v1/models | python -m json.tool
```

完整启动命令要另存到 `reports/server_command.txt`，包括所有环境变量。日志里应重点记录引擎报告的 KV Cache 可用 Token 数、CUDA Graph 捕获情况与最大并发序列数——这三个数字是后续解释抢占与吞吐拐点的直接证据。

如果模型超出单卡容量，不要盲目把显存利用率设为 1。应选择更小模型、合法量化版本、Tensor Parallel 或容量更大的 GPU，并记录改变后的问题定义。`gpu_memory_utilization` 是「引擎可占用的显存比例上限」，不是「KV Cache 比例」；把它推到 0.98 会压缩运行期临时张量与图捕获的余量，反而更容易 OOM。

## 5. 完整流式负载生成器

### 5.1 openai_stream_benchmark.py

脚本只依赖 Python 标准库，通过 SSE 流记录首个内容事件和完成时间。若服务返回 Usage，就使用精确 Completion Token；否则退化为内容事件数，并在结果中明确标记估算。

保存为 `openai_stream_benchmark.py`：

```python
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
```

这个客户端里有六处决定了数据可信度的细节：

1. **TTFT 以「第一个非空 `delta.content`」计时**，而不是以收到第一个 SSE 事件计时。Chat 接口的首个事件常常只带 `role`，若把它算作首 Token，TTFT 会被系统性低估。
2. **`stream_options={"include_usage": True}`** 让服务端在流末尾回传精确 Token 数。`token_count_source` 字段把 `usage` 与 `content_events` 两种口径显式写进结果，避免事后无法判断 TPOT 分母的来源。
3. **`output_tokens = completion_tokens or content_events`**：Usage 缺失时退化为事件计数。一个事件可能包含多个 Token（服务端聚合发送），因此这是估算值，报告里必须标注。
4. **`temperature=0.0`** 固定采样，让不同配置下的输出长度尽量一致；但贪心解码不保证长度完全相同，所以仍要保存 `raw` 中的逐请求 Token 数。
5. **`tpot=None` 而非 0**：单 Token 输出时 TPOT 无定义，且这类请求会被 Goodput 判定排除（条件里要求 `tpot_s is not None`），这是保守口径。
6. **`raw` 按 `id` 排序后完整保存**：聚合指标可以复算，异常请求可以回溯。只保存 P95 的报告无法做回归对比。

并发模型是 `ThreadPoolExecutor` 的闭环压测：始终维持 `concurrency` 个在途请求，一个完成立刻补一个。它与真实线上「开环泊松到达」不同——闭环压测在服务变慢时会自动降低到达率，因此测出的尾延迟通常比同等平均负载的开环场景乐观。做 SLO 结论时应说明这一点。

### 5.2 单并发正确性

先从 `/v1/models` 返回结果中取得真实 Served Model Name：

```bash
export SERVED_MODEL="your-served-model-name"
python openai_stream_benchmark.py --model "$SERVED_MODEL" \
  --requests 3 --concurrency 1 --max-tokens 32 \
  --output reports/smoke.json
```

Smoke 阶段要确认三件事：`success_rate` 为 1.0；`token_count_sources` 只含 `usage`（说明服务端支持精确计数）；`tpot_s.p50` 非空（说明输出确实多于 1 个 Token）。任何一项不满足，先修客户端与服务配置，不要进入并发扫描。

### 5.3 并发扫描

保存为 `run_sweep.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${SERVED_MODEL:?请先 export SERVED_MODEL=...}"
mkdir -p reports
for concurrency in 1 2 4 8 16 32; do
  python openai_stream_benchmark.py \
    --model "$SERVED_MODEL" \
    --requests 100 \
    --concurrency "$concurrency" \
    --max-tokens 128 \
    --prompt-words 64 \
    --ttft-slo 1.0 \
    --tpot-slo 0.05 \
    --output "reports/c${concurrency}.json"
done
```

```bash
chmod +x run_sweep.sh
./run_sweep.sh
```

`set -euo pipefail` 保证任何一组失败立即中止，不会留下「一半配置有数据、一半没有」的报告；开头的 `SERVED_MODEL` 必填校验在变量未设置时直接报错退出，避免用空模型名跑完整轮扫描。

扫描的读法是找拐点而不是找最大值：把六组的 `output_token_throughput`、`ttft_s.p95`、`tpot_s.p95`、`goodput_requests_per_second` 画在同一张横轴为并发的图上。吞吐曲线的斜率变平、而 P95 开始陡升的那个并发，就是 SLO 约束下的候选工作点。

## 6. 使用 vLLM 官方 Benchmark 交叉验证

当前版本应先查看帮助，确认参数名：

```bash
vllm bench serve --help=all | tee reports/vllm-bench-help.txt
```

典型随机负载命令：

```bash
vllm bench serve \
  --backend openai-chat \
  --base-url http://127.0.0.1:8000 \
  --endpoint /v1/chat/completions \
  --model "$SERVED_MODEL" \
  --dataset-name random \
  --random-input-len 512 \
  --random-output-len 128 \
  --num-prompts 200 \
  --max-concurrency 8 \
  --save-result
```

自写客户端用于理解指标和回归门禁；官方 Benchmark 用于与 vLLM 当前实现口径对齐。两者结果不一致时，先检查 Prompt Tokenizer、输出 Token、请求到达模型、Endpoint 和是否忽略 EOS。

一个高频差异来源是 EOS：`--random-output-len` 指定的是上限，若模型提前生成结束符，实际输出 Token 会短于设定值，Token/s 与 TPOT 都会随之偏移。官方工具通常提供忽略 EOS 的开关，做严格长度对照时应显式确认其状态，并在报告中写明。

## 7. 参数调优顺序

### 7.1 固定模型长度

`max_model_len` 会影响可预留的 KV 容量。不要把模型声明的最大 Context 无条件作为服务配置；根据真实输入、输出与 SLO 选择。

原因是引擎按最大长度参与容量与调度规划：把 128K 上下文声明给一个实际只用 2K 的业务，会白白压缩可并发序列数。正确做法是先统计线上请求长度分布的 P95/P99，再取一个略高于 P99 的值，并保留少量超长请求的降级路径。

### 7.2 扫描调度容量

先用当前版本帮助确认参数：

```bash
vllm serve --help=all | rg "max-num-batched-tokens|max-num-seqs|chunked-prefill"
```

常见方向：

- 增大 `max_num_batched_tokens`：可能提高 Prefill 吞吐，但增加单批执行时间与 KV 压力；
- 增大 `max_num_seqs`：可能提高并发，但增加调度和 KV 占用；
- Chunked Prefill：帮助长 Prefill 与 Decode 共享调度，但最优 Token Budget 依负载而变；
- Prefix Caching：只对可复用 Prefix 有意义，随机 Prompt 不应期待收益。

两个参数的作用维度不同：`max_num_batched_tokens` 限制「一个迭代处理多少 Token」，主要影响 Prefill 分块粒度与单迭代时长；`max_num_seqs` 限制「一个迭代容纳多少条序列」，主要影响 Decode Batch 宽度。Decode-heavy 负载通常先受后者约束，Prefill-heavy 负载先受前者约束，因此调优前应先判断负载类型。

### 7.3 观察容量事件

同时采集：

```bash
nvidia-smi dmon -s pucvmet -d 1 -o DT > reports/gpu_dmon.csv
```

检查 Server 日志中的 KV Cache、Preemption、OOM、CUDA Graph、Engine Restart 与错误请求。显存利用率高不等于 Goodput 高。

`dmon` 的字段组合 `pucvmet` 覆盖功耗、利用率、时钟、显存、ECC、温度等，`-o DT` 附加日期与时间戳，便于和压测 JSON 的时间轴对齐。抢占的典型信号是：吞吐在某个并发之后突然下降，同时日志出现 preemption/recompute 计数增长——这说明 KV 池已经不足以容纳在途序列，引擎被迫回收并重算。

### 7.4 一次只改一个参数

| 实验 | 改变量 | 其他条件 |
| --- | --- | --- |
| A | 基线 | 固定 |
| B | Batched Token Budget | 与 A 相同 |
| C | Max Sequences | 与最佳 B 相同 |
| D | Prefix Caching | 使用重复 Prefix 负载 |
| E | Tensor Parallel | 模型、Token、并发相同 |

这张表的关键在「其他条件」列：C 组的基线是「最佳 B」而不是 A，属于逐步爬山；D 组必须换负载，否则随机 Prefix 下开关缓存毫无差别，会得出「Prefix Caching 无效」的错误结论；E 组要求模型、Token、并发完全一致，否则比较的是两个不同问题。

每组实验都要保存完整启动命令与原始 JSON，`optimized_c8.json` 只对应最终选定的那一组配置。

## 8. Level 2：架构专项与多 GPU

| 架构 | 示例 | 可选验证 |
| --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | FP16/BF16（按卡能力）、Tensor Parallel；RTX 3090 特定型号可有 NVLink |
| Ada Lovelace | RTX 4090、L40/L40S | FP16/BF16、PCIe 多卡；RTX 4090 无 NVLink |
| Hopper | H100/H200 | FP8、Transformer Engine、NVLink/NVSwitch 数据中心场景 |
| Blackwell | RTX 5090、B100/B200/GB200 | FP8/FP4 与新 Kernel，必须匹配工具链 |

多 GPU 启动示例：

```bash
CUDA_VISIBLE_DEVICES=0,1 vllm serve "$MODEL_ID" \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85
```

Tensor Parallel 是否更快取决于模型是否放得下、矩阵规模与互联。双 RTX 3080 通常走 PCIe，不应写成 NVLink 实验。只有实际具备 NVLink/NVSwitch 的系统才能验证其收益。

从通信量角度可以给出一个判断边界：TP 在每个 Transformer 层通常引入两次 All-Reduce，单层通信量约为

$$
Bytes_{TP} \approx 2 \times 2 \times \frac{B \cdot S \cdot H \cdot b}{1} \cdot \frac{N-1}{N}
$$

其中 $B \cdot S$ 是批内 Token 数、$H$ 是隐藏维度、$b$ 是元素字节数、$N$ 是 TP 路数。Decode 阶段 $S=1$，单次通信量很小但频次极高（每层每 Token 一次），此时延迟主导而非带宽主导，PCIe 上的 TP 往往得不偿失；Prefill 阶段 $S$ 很大，带宽主导，TP 的收益更容易体现。这解释了为什么「TP=2 让 TTFT 变好、TPOT 变差」是常见现象。

量化不是无损的通用性能开关。必须同时验证模型质量、支持的 Kernel、显存、TTFT、TPOT 和吞吐；Hopper/Blackwell 的 FP8/FP4 结果不能迁移到 Ampere/Ada。

## 9. 结果分析

### 9.1 SLO 表

| 配置 | 并发 | TTFT P95 | TPOT P95 | E2E P95 | Output tok/s | Goodput req/s | 成功率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 1 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| Baseline | 8 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| Optimized | 8 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |

表中所有数字必须来自同一模型、同一 Token 分布、同一硬件与同一版本组合，并在表下注明 SLO 阈值（默认 TTFT 1.0 s、TPOT 0.05 s）。没有实测数据时保留「待测」，不要用估算值填充后当成结论。

### 9.2 典型现象

- 并发上升、Token 吞吐上升、TTFT 恶化：Batch 收益与排队同时发生；
- TTFT 好但 TPOT 差：Decode 批次过重、抢占或内存压力；
- GPU 利用率低且 TTFT 高：客户端到达不足、CPU/Tokenizer、模型加载或调度瓶颈；
- 吞吐突然下降且日志出现 Preemption：KV 容量不足或并发/长度配置过高；
- Prefix Caching 无收益：前缀不相同、缓存命中低或 Prefill 占比小；
- TP=2 比 TP=1 慢：模型本来能单卡运行，通信成本超过分片收益。

第三条与第四条最容易误判。GPU 利用率低时，直觉是「服务不够快」，但真实原因常在服务之外：客户端线程数不足、Tokenizer 在 CPU 上串行、HTTP 连接复用未开启。区分方法是同时看客户端 CPU 与服务端日志的 running/waiting 序列数——若 waiting 长期为 0 而 GPU 空闲，瓶颈在负载生成侧。

## 10. 常见错误与排查

### 10.1 Served Model Name 不一致

先请求 `/v1/models`，客户端的 `model` 必须匹配服务端名称。使用 `--served-model-name` 自定义别名时尤其容易出错。

### 10.2 TTFT 等于完整响应时间

客户端没有真正读取流，或服务未返回 SSE。确认 `stream=true`，以第一个非空内容事件计 TTFT。若用 `requests` 库一次性 `response.json()`，测到的永远是 E2E。

### 10.3 TPOT 计算错误

TPOT 分母通常是首 Token 后的 Token 间隔数，即 N-1。只有一个输出 Token 时应为 `null`。写成 N 会系统性低估 TPOT，且输出越短偏差越大。

### 10.4 Prompt 长度不受控

「重复若干单词」不等于固定 Token。正式结果应使用目标模型 Tokenizer 构造精确长度，并保存 Token 数分布。本项目的 `--prompt-words` 只用于快速形成趋势，跨模型比较时必须换成精确 Token 构造。

### 10.5 客户端先饱和

观察客户端 CPU、连接、文件描述符与网络。服务端 GPU 空闲而客户端吞吐封顶时，应分离 Load Generator。Python 标准库客户端在高并发下的 SSE 逐行解析本身就有可观 CPU 开销，必要时改用多进程或专用压测工具。

### 10.6 把 OOM 解决为显存利用率 1.0

更高利用率减少运行余量，可能增加抢占或 OOM。先降低模型长度、并发或选择合适并行/量化方案。

### 10.7 只测离线吞吐

离线吞吐不包含真实到达、排队和 SLO。在线服务必须测 TTFT、TPOT、尾延迟与 Goodput。

### 10.8 随机负载验证 Prefix Cache

随机 Prefix 命中率接近零。应构造共享 System Prompt 或固定长前缀的成对实验。

## 11. 优化前后对照

| 层次 | 基线问题 | 优化方向 | 证据 |
| --- | --- | --- | --- |
| 请求 | 长度不可控 | 固定 Token 分布 | 输入/输出直方图 |
| 调度 | 并发过低/过高 | 扫描拐点 | TTFT/TPOT/吞吐 |
| Prefill | 长请求阻塞 Decode | Chunk/Budget 调整 | 时间线与 P95 |
| KV | 抢占/OOM | 长度、并发、缓存配置 | 日志与显存 |
| 计算 | Kernel/精度不合适 | 合法量化/架构 Kernel | 质量与性能 |
| 多卡 | 通信暴露 | TP 与拓扑匹配 | 单卡/双卡对照 |

六个层次自上而下排列，恰好对应排查顺序：先确认负载口径可信，再看调度，再看 Prefill/Decode 竞争，再看容量事件，最后才动计算精度与并行。顺序颠倒会导致把负载构造问题误诊为 Kernel 问题。

## 12. 常见追问与解答

### 12.1 Continuous Batching 为什么能提高吞吐

它在每个调度迭代动态加入新请求、移除完成请求，使 Decode Batch 保持较高占用，减少静态 Batch 的空槽。静态 Batch 必须等最慢的请求结束才能整批替换，长短请求混合时 GPU 大量时间在算 Padding。

### 12.2 TTFT 与 TPOT 分别受什么影响

TTFT 主要受排队和 Prefill 影响；TPOT 反映生成阶段每个后续 Token 的节奏，受 Decode Batch、KV、内存带宽、抢占与调度影响。因此优化 TTFT 的手段（Chunked Prefill、Prefix Cache、提高 Prefill 优先级）与优化 TPOT 的手段（控制 Decode Batch 宽度、减少抢占）并不相同，甚至互相冲突。

### 12.3 为什么最大吞吐配置不一定是生产最优

最大吞吐可能伴随不可接受的 TTFT/TPOT 尾延迟。生产应在 SLO 约束下最大化 Goodput。

### 12.4 `gpu_memory_utilization` 越高越好吗

不是。它会影响可用于 KV Cache 的容量，但过高会压缩运行余量，增加 OOM 或不稳定风险。合理值应通过「提高利用率 → 观察抢占与错误率」的实验确定，而不是直接取上限。

### 12.5 Prefix Cache 什么时候有效

多个请求共享可缓存的 Token Prefix 且 Prefill 成本显著时有效；随机、短或低重复 Prefix 的收益有限。典型高收益场景是长 System Prompt、RAG 固定文档前缀与多轮对话历史。

### 12.6 为什么 Tensor Parallel 可能降低单请求性能

每层计算被切分后需要跨卡通信；若单卡已能高效运行，通信和同步成本可能超过并行收益。Decode 阶段的小消息高频 All-Reduce 对互联延迟尤其敏感。

## 13. 延伸练习

1. 扫描并发 1～64，画 TTFT P95、TPOT P95、Token/s 和 Goodput 曲线。
2. 构造短输入长输出、长输入短输出、长输入长输出三种负载。
3. 扫描 `max_num_batched_tokens`，找到交互 SLO 下最优值。
4. 构造 80% 共享 Prefix 的请求，验证 Prefix Cache 命中收益。
5. 比较单卡和双卡 TP；分析通信与模型容量的权衡。
6. 故意降低 KV 容量，观察 Preemption、P95 和吞吐变化。
7. 让客户端与服务端分机，区分网络和服务时间。
8. 用 vLLM 官方 Benchmark 复测自写客户端，并解释口径差异。

## 14. 项目验收 Checklist

- 已锁定 vLLM、PyTorch、CUDA、驱动和模型版本。
- 已记录服务完整启动命令和 `/v1/models`。
- 已固定输入/输出 Token 分布与请求到达模型。
- 已测 TTFT、TPOT、E2E、QPS、Token/s、成功率与 Goodput。
- 已扫描并发并找到 SLO 饱和拐点。
- 每次只修改一个 Scheduler/KV/并行参数。
- 已检查服务日志中的 OOM、Preemption 和 Engine 错误。
- 已排除客户端、Tokenizer 与网络瓶颈。
- CPU 模拟未被写成 vLLM/GPU 实测。
- NVLink、FP8、FP4 只在真实支持硬件上验证。
- 所有性能结论都附带模型、长度、并发、硬件和 SLO 边界。

## 写在最后

这个项目的核心不是某个「最优参数组合」，而是一条可重复的证据链：固定负载口径 → 扫描并发找拐点 → 单变量改动 → 用 Goodput 与日志事件验证。参数会随版本变化，方法不会。下一个项目把镜头对准服务里最稀缺的资源——KV Cache，从容量公式一路做到分页、碎片与共享前缀的实测。

下一篇：[KV Cache 优化实验](/source/AI-Infra/2-AI系统性能工程/34-KVCache优化实验)。