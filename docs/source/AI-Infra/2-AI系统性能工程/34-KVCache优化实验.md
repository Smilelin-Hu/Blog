# KV Cache 优化实验

本项目通过可运行实验分析 KV Cache 的容量、带宽与调度瓶颈，并验证分页和复用策略。

目标是把 KV Cache 从一个公式变成可测量、可调度、可回归的系统资源：完成容量估算、连续分配与分页分配对照、Block Size 扫描、共享前缀命中实验，以及真实服务中的 KV 容量、抢占、TTFT 和吞吐分析。

```text
模型结构 → 每 Token KV 字节 → 理论 Token 容量
→ 分页与碎片模拟 → 服务端 KV 配置
→ 重复前缀负载 → 命中/未命中对照
→ 并发与上下文扫描 → SLO、抢占、显存回归
```

Level 0 纯 Python 可运行。Level 1 适配常见 NVIDIA GPU 上的 vLLM。Level 2 的 KV 量化、跨 GPU/NVLink、Host Offload 与 Disaggregated KV Transfer 必须在真实支持的硬件和框架版本上验证。

## 1. 内容概览与交付物

做完之后应当能够：从层数、KV Head、Head Dimension、精度计算每 Token KV 字节；区分理论容量、可用容量、内部碎片、外部碎片和运行峰值；理解 Paged KV Cache 如何把请求生命周期映射到固定大小 Block；解释 MHA、GQA、MQA 对 KV 容量的影响；构造有命中和无命中的 Prefix Cache A/B 实验；用服务日志识别 Preemption、Recompute、Swap、OOM 与低命中率；同时优化容量、TTFT、TPOT、吞吐和正确性，而不是只追求显存占满。

前置知识：Attention 与 KV Cache、Continuous Batching、流式推理指标相关内容，以及 vLLM 推理优化项目；Transformer Attention、Continuous Batching、流式推理指标；Python 3.10+；真实服务实验需要 vLLM 和可用模型。

```text
kv-cache-project/
├── kv_cache_lab.py
├── prefix_cache_benchmark.py
├── reports/
│   ├── capacity.json
│   ├── fragmentation.json
│   ├── prefix_off.json
│   ├── prefix_on.json
│   └── analysis.md
└── logs/
    ├── server_prefix_off.log
    └── server_prefix_on.log
```

`reports/analysis.md` 需要回答：理论容量与引擎实测容量差多少、差值来自哪里；Block Size 变化时碎片与吞吐是否同向；Prefix 命中组与未命中组的 TTFT 差多少；第一次 Preemption 出现在哪个并发；结论的模型配置、版本与长度分布边界是什么。

## 2. 核心直觉：KV Cache 是「按活跃 Token 计费」的显存池

对 Decoder-only Transformer，单 Token 的 KV Cache 粗略字节数：

$$
Bytes_{token} = 2 \times L \times H_{kv} \times D_{head} \times B_{dtype}
$$

- 2：Key 与 Value；
- $L$：层数；
- $H_{kv}$：KV Head 数；
- $D_{head}$：每个 Head 的维度；
- $B_{dtype}$：每元素字节数。

请求长度为 S，并发为 C：

$$
M_{KV} \approx C \times S \times Bytes_{token}
$$

这个公式没有包含 Block 元数据、Padding、Allocator、CUDA Graph、工作区和碎片。真实可用 Token 容量应由服务启动日志与实测共同确认。

公式里最容易被写错的是 $H_{kv}$。MHA 下 KV Head 数等于 Query Head 数，GQA 下若干 Query Head 共享一组 KV Head，MQA 下全部 Query Head 共享一组。因此 GQA/MQA 通过减少 $H_{kv}$ 显著降低 KV Cache，但不会把 Query Head 的计算量按同样比例消除——Attention 的 QK/PV 矩阵乘仍按 Query Head 数展开，省下的是显存与 KV 读取带宽，不是全部算力。

另一个常见误用是把 $S$ 取成模型声明的最大上下文。容量规划可以用它做上界，但真实占用取决于请求长度分布，用最大值估算会严重低估可并发数。

## 3. 分页与碎片模型

连续预留若按最大上下文 $S_{max}$ 为每个请求分配：

$$
Waste_{contiguous} = \sum_i (S_{max} - S_i)
$$

分页分配 Block Size 为 K：

$$
Reserved_i = \left\lceil \frac{S_i}{K} \right\rceil K
$$

$$
Waste_{paged} = \sum_i (Reserved_i - S_i)
$$

两式的差别在于「浪费的上界」：连续预留的浪费随请求长度方差线性增长，最坏情况下一条 32 Token 的请求也要占满 4096 Token 的空间；分页预留的浪费每条请求不超过 $K-1$ 个 Token，与长度分布几乎无关。

若长度在 $[S_{min}, S_{max}]$ 上近似均匀分布，单请求内部碎片的期望约为 $(K-1)/2$，于是：

$$
Waste_{paged} \approx n \cdot \frac{K-1}{2}
$$

较小 Block 减少内部碎片，但会增加 Block Table、调度和 Kernel 元数据成本。最佳 Block Size 是系统实验结果，不由碎片公式单独决定。

## 4. Level 0：容量与分页模拟器

### 4.1 kv_cache_lab.py

脚本分两个模式：`capacity` 做纯公式换算，`fragmentation` 用随机长度序列对比连续预留与分页预留。

保存为 `kv_cache_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import json
import math
import random
import statistics
from pathlib import Path

def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)

def capacity(args):
    bytes_per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.dtype_bytes
    usable_bytes = args.kv_memory_gib * (1024 ** 3) * args.safe_utilization
    token_capacity = math.floor(usable_bytes / bytes_per_token)
    request_capacity = math.floor(token_capacity / args.tokens_per_request)
    return {
        "bytes_per_token": bytes_per_token,
        "kib_per_token": bytes_per_token / 1024,
        "usable_kv_gib": args.kv_memory_gib * args.safe_utilization,
        "theoretical_token_capacity": token_capacity,
        "theoretical_request_capacity": request_capacity,
        "warning": "不含 Block 元数据、工作区、图捕获、Allocator 和运行峰值。",
    }

def fragmentation(args):
    rng = random.Random(args.seed)
    lengths = [rng.randint(args.min_tokens, args.max_tokens) for _ in range(args.requests)]
    contiguous_reserved = args.requests * args.max_tokens
    paged_reserved = sum(math.ceil(length / args.block_size) * args.block_size
                         for length in lengths)
    used = sum(lengths)
    return {
        "requests": args.requests,
        "block_size": args.block_size,
        "used_tokens": used,
        "contiguous_reserved_tokens": contiguous_reserved,
        "paged_reserved_tokens": paged_reserved,
        "contiguous_utilization": used / contiguous_reserved,
        "paged_utilization": used / paged_reserved,
        "paged_internal_fragmentation_tokens": paged_reserved - used,
        "length_p50": percentile(lengths, 0.50),
        "length_p95": percentile(lengths, 0.95),
        "mean_length": statistics.mean(lengths),
        "warning": "模拟器不包含真实请求生命周期、Prefix 共享、抢占或 Kernel 成本。",
    }

def main():
    parser = argparse.ArgumentParser(description="KV Cache 容量与分页实验")
    parser.add_argument("--mode", choices=["capacity", "fragmentation"], required=True)
    parser.add_argument("--layers", type=int, default=32)
    parser.add_argument("--kv-heads", type=int, default=8)
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--dtype-bytes", type=float, default=2)
    parser.add_argument("--kv-memory-gib", type=float, default=8)
    parser.add_argument("--safe-utilization", type=float, default=0.90)
    parser.add_argument("--tokens-per-request", type=int, default=4096)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--min-tokens", type=int, default=32)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="reports/kv_cache.json")
    args = parser.parse_args()
    numeric = [args.layers, args.kv_heads, args.head_dim, args.dtype_bytes,
               args.kv_memory_gib, args.tokens_per_request, args.requests,
               args.min_tokens, args.max_tokens, args.block_size]
    if any(value <= 0 for value in numeric):
        raise ValueError("容量与负载参数必须大于 0")
    if args.min_tokens > args.max_tokens:
        raise ValueError("min-tokens 不能大于 max-tokens")
    if not 0 < args.safe_utilization <= 1:
        raise ValueError("safe-utilization 必须位于 (0, 1]")

    result = capacity(args) if args.mode == "capacity" else fragmentation(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
```

几处设计细节：

- **`--dtype-bytes` 用 float**：便于表达 FP8（1 字节）甚至混合精度下的等效字节数，而不局限于整数类型。
- **`--safe-utilization` 独立于显存总量**：把「安全余量」显式建模成一个参数，而不是隐含在总量里。默认 0.90 表示预留 10% 给元数据与峰值波动，这个值应由实测校准。
- **`request_capacity` 用整除**：容量规划要的是「能同时容纳多少条完整请求」，向下取整比四舍五入安全。
- **`contiguous_reserved` 用 `max_tokens` 而非实际最大长度**：刻画的是「按声明上限预留」这一最坏策略，正是连续分配被诟病的地方。
- **两个 `warning` 字段写进 JSON**：让结果文件自带口径声明，避免脱离上下文后被误当成实测容量。
- **参数校验前置**：`min_tokens > max_tokens`、`safe_utilization` 越界都会直接抛错，而不是产出看似合理的错误数字。

### 4.2 运行容量实验

```bash
mkdir -p reports
python kv_cache_lab.py --mode capacity \
  --layers 32 --kv-heads 8 --head-dim 128 --dtype-bytes 2 \
  --kv-memory-gib 8 --tokens-per-request 4096 \
  --output reports/capacity.json
```

将 `kv-heads` 从 32 改为 8、再改为 1，对比 MHA、GQA、MQA 的理论容量。参数必须来自实际模型配置，不能从模型名称猜测。

按上述公式手工推导（32 层、Head Dim 128、BF16、8 GiB KV 池、安全系数 0.90，即可用 7.2 GiB），三组结果如下：

| 注意力形态 | $H_{kv}$ | Bytes/token | KiB/token | 理论 Token 容量 | 4096 Token 请求数 |
| --- | --- | --- | --- | --- | --- |
| MHA | 32 | 524288 | 512 | 14745 | 3 |
| GQA | 8 | 131072 | 128 | 58982 | 14 |
| MQA | 1 | 16384 | 16 | 471859 | 115 |

这张表是公式推导值，不是实测值，但足以说明量级：同样 8 GiB 的 KV 池，MHA 只够 3 条 4K 请求，GQA 够 14 条，MQA 够 115 条。KV Head 数每减半，可并发数就翻倍——这是 GQA 成为主流配置的直接原因。

同时也暴露了另一个事实：默认 GQA 配置下每 Token 就要 128 KiB，一条 4K 请求占 512 MiB。所谓「8 GiB 显存能跑很多并发」的直觉，在长上下文场景下完全不成立。

### 4.3 运行碎片实验

```bash
for block in 8 16 32 64; do
  python kv_cache_lab.py --mode fragmentation \
    --requests 1000 --min-tokens 32 --max-tokens 4096 \
    --block-size "$block" \
    --output "reports/fragmentation_block_${block}.json"
done
```

1000 条请求、长度在 32～4096 上均匀分布，期望总用量约 $1000 \times (32+4096)/2 = 2.064 \times 10^6$ Token，连续预留固定为 $4.096 \times 10^6$ Token。按 $(K-1)/2$ 的期望碎片推导：

| Block Size | 连续预留利用率 | 分页预留利用率（期望） | 平均内部碎片/请求 | 1000 条总碎片 |
| --- | --- | --- | --- | --- |
| 8 | ≈0.504 | ≈0.998 | ≈3.5 Token | ≈3500 Token |
| 16 | ≈0.504 | ≈0.996 | ≈7.5 Token | ≈7500 Token |
| 32 | ≈0.504 | ≈0.993 | ≈15.5 Token | ≈15500 Token |
| 64 | ≈0.504 | ≈0.985 | ≈31.5 Token | ≈31500 Token |

换算成显存更直观：在 128 KiB/token 的默认模型下，Block 从 8 增到 64，1000 条请求的内部碎片从约 0.43 GiB 增到约 3.85 GiB；而按最大长度连续预留的浪费高达约 203 万 Token，折合超过 240 GiB——远超任何单卡 KV 池。这就是分页机制存在的根本理由。

表中数字为均匀分布下的期望推导，实际运行会因随机种子产生小幅波动，应以脚本输出的 `used_tokens` 与 `paged_internal_fragmentation_tokens` 为准。

### 4.4 预期现象

分页预留比按最大长度连续预留更接近实际使用量；Block 越小，模拟内部碎片通常越低。但模拟器没有计入元数据和 Kernel 成本，不能据此宣布最小 Block 一定最快。

真实系统里 Block 变小的代价有三处：Block Table 条目数增加带来的索引与调度开销；Attention Kernel 需要处理更多不连续块，访存局部性变差；Prefix Cache 的哈希粒度变细，命中判定与共享管理成本上升。因此碎片曲线单调下降、吞吐曲线却可能先升后降，最优点必须实测。

## 5. Level 1：真实 vLLM KV Cache 实验

### 5.1 环境记录

沿用 vLLM 推理优化项目的隔离环境，并保存：

```bash
mkdir -p reports logs
{
  date -Iseconds
  nvidia-smi -L
  nvidia-smi topo -m
  python --version
  vllm --version
  vllm serve --help=all | rg "cache|block|swap|offload|max-model-len"
} 2>&1 | tee reports/environment.txt
```

最后一条命令把当前版本所有与 KV 相关的参数名落盘。Block Size、Swap Space、CPU Offload、Prefix Caching 的开关形态在不同版本差异很大，实验记录里必须附上这份帮助输出，否则后续无法复现。

### 5.2 基线服务

```bash
export MODEL_ID="your-org/your-model"
vllm serve "$MODEL_ID" \
  --host 127.0.0.1 --port 8000 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  2>&1 | tee logs/server_prefix_off.log
```

记录启动日志中的 KV Cache 容量。不要从总显存减权重后直接宣称剩余全部属于 KV；Runtime 还需要工作区、CUDA Graph 和临时张量。

理论容量与实测容量的差值本身就是一项结论。若引擎报告的 Token 容量明显低于公式值，常见原因是：权重之外的激活与工作区、CUDA Graph 捕获占用的显存池、Block 元数据、以及引擎自身保留的安全余量。把这个差值量化并归因，比单纯报一个「能跑多少并发」更有价值。

## 6. Prefix Cache A/B 客户端

### 6.1 prefix_cache_benchmark.py

下面脚本生成「共享长前缀」和「随机前缀」两组请求。为了避免把网络并发混入命中实验，默认串行发送并比较热身后的端到端延迟。更完整的 TTFT/TPOT 应复用 vLLM 推理优化项目的流式客户端。

保存为 `prefix_cache_benchmark.py`：

```python
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
```

这个脚本的实验设计有四点值得注意：

1. **交替发送而非分组发送**：每轮先发共享前缀请求、再发随机前缀请求。这样两组的系统状态（温度、时钟、缓存池占用）尽量接近，避免「先跑完 A 组再跑 B 组」引入的时间漂移。
2. **随机前缀用 64 位随机数拼接**：`rng.getrandbits(64)` 保证 Token 序列几乎不可能与共享前缀重合，命中率接近零，构成干净的对照组。
3. **`stream=False` 测端到端**：这里刻意不测 TTFT，因为非流式接口的 E2E 已包含完整 Prefill 与 Decode。要分离 Prefill 收益必须换流式客户端，这也是脚本定位说明里强调复用上一个项目流式客户端的原因。
4. **`usage_samples` 保存 Prompt/Completion Token 数**：用于验证两组的输入长度确实可比。若共享组与随机组的 `prompt_tokens` 差异很大，说明 Word 数到 Token 数的映射不一致，延迟对比就失去意义。

`--max-tokens 32` 的短输出是刻意选择：让 Prefill 在 E2E 中占主导，从而放大前缀复用的收益信号。若输出很长，Decode 时间会淹没 Prefill 差异。

### 6.2 A/B 实验步骤

第一步，关闭 Prefix Cache 启动服务，热身后运行：

```bash
export SERVED_MODEL="your-served-model-name"
python prefix_cache_benchmark.py --model "$SERVED_MODEL" \
  --output reports/prefix_off.json
```

第二步，停止服务，使用当前版本帮助确认 Prefix Caching 参数名，然后开启：

```bash
vllm serve --help=all | rg "prefix"
vllm serve "$MODEL_ID" \
  --host 127.0.0.1 --port 8000 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-caching \
  2>&1 | tee logs/server_prefix_on.log
```

第三步，使用相同模型、Prompt、请求顺序和输出长度复测：

```bash
python prefix_cache_benchmark.py --model "$SERVED_MODEL" \
  --output reports/prefix_on.json
```

首次共享 Prefix 请求用于填充缓存，不应与热命中请求混在一个结论中。正式实验应分别报告 Cold、Warm Hit 与 Random Miss。

具体做法是把共享组的第 1 条单独列为 Cold Fill，第 2 条起列为 Warm Hit，随机组全部列为 Miss，三组分别给 P50/P95。若把 Cold Fill 混入 Warm Hit，命中率收益会被系统性低估；反之若只报 Warm Hit 而不报 Cold，则会高估线上真实收益——线上总有首次请求。

## 7. 并发与上下文容量扫描

复用 vLLM 推理优化项目的流式 Benchmark，构造：

| 负载 | 输入 | 输出 | 目标 |
| --- | --- | --- | --- |
| Decode-heavy | 128 | 1024 | TPOT、KV 增长 |
| Prefill-heavy | 4096 | 64 | TTFT、Prefix 命中 |
| Long-context | 8192+ | 128 | 容量、抢占、OOM |
| Mixed | 分布 | 分布 | 生产 Goodput |

每种负载扫描并发，记录 Server 日志、GPU 显存、TTFT P95、TPOT P95、Token/s、成功率、Preemption 和 Cache Hit 指标。

四种负载压的是不同资源：Decode-heavy 的 KV 随时间线性增长，主要考验容量与抢占；Prefill-heavy 的 KV 一次性分配，主要考验算力与调度分块；Long-context 直接把单请求容量推到边界，最容易触发 OOM；Mixed 才接近生产，用于最终的 Goodput 判定。只用一种负载得出的「最优配置」通常无法迁移。

Long-context 一行需要额外注意：`8192+` 已超过基线服务的 `--max-model-len 4096`，必须同步调整服务配置，否则请求会被直接拒绝，测到的不是容量边界而是参数校验。

## 8. Level 2：专属实验与边界

### 8.1 KV Cache 低精度

当前 vLLM 版本、模型与 GPU 若支持 KV Cache 量化，可做 FP8 KV A/B。必须先查看当前帮助与官方支持矩阵，验证模型质量和数值稳定性。FP8 KV 减少字节数不代表端到端必然加速；量化/反量化、Kernel 与带宽瓶颈都会影响结果。

按公式，$B_{dtype}$ 从 2 降到 1 会让每 Token 字节减半、理论容量翻倍。但收益能否兑现取决于三点：Attention Kernel 是否原生支持 FP8 KV 读取（否则需要反量化回 BF16，带宽收益被抵消）；量化缩放因子的存储与计算开销；长上下文下累积的数值误差是否影响输出质量。因此 FP8 KV 的实验必须同时报容量、TPOT 与质量三类指标。

Ampere RTX 3080/3090 不应被宣称为 Hopper FP8 实验；Ada RTX 4090 也不属于 Blackwell。H100/H200 属于 Hopper，RTX 5090/B100/B200/GB200 属于 Blackwell。FP4 KV 或计算只有在真实支持的硬件、框架和 Kernel 上才可验证。

### 8.2 CPU Offload / Swap

Host KV 或 Swap 可能扩大容量，但引入 PCIe/NUMA/页锁定与尾延迟。实验必须报告：

- Host Memory 与 NUMA 绑定；
- PCIe/NVLink/NVSwitch 拓扑；
- 命中与换入换出字节；
- TTFT/TPOT P95/P99；
- CPU 内存压力和 OOM 风险。

CPU 模拟无法等价验证真实传输带宽和尾延迟。

这里的量级对比很关键：GPU HBM 带宽通常在数百 GB/s 到数 TB/s，而 PCIe 4.0 x16 单向理论约 32 GB/s、实际有效更低。换入一条 4K 请求的 KV（默认配置下约 512 MiB）在 PCIe 上就需要十几毫秒量级，足以让该请求的 TPOT 出现明显尖刺。因此 Offload 的收益是「容量」，代价是「尾延迟」，只对可容忍抖动的批处理场景划算。

### 8.3 多 GPU KV

Tensor Parallel 通常让每卡保存相应分片 KV，但具体布局取决于引擎与 Attention 实现。只有具备 NVLink/NVSwitch 的系统才能验证其互联收益；双 RTX 3080 一般以 PCIe 为基线。

TP 下每卡 KV 约为总量的 $1/N$（按 KV Head 切分时），这确实缓解了单卡容量压力，但每层 Attention 后的 All-Reduce 会把互联延迟引入每个 Token 的生成路径。容量收益与延迟代价必须一起报告，不能只写「显存够了」。

## 9. 结果分析

### 9.1 容量与服务指标表

| 配置 | KV dtype | Block | Prefix | 并发 | TTFT P95 | TPOT P95 | tok/s | Peak GiB | Preemptions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 待测 | 待测 | Off | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| Paged Tune | 待测 | 待测 | Off | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| Prefix On | 待测 | 待测 | On | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |

`Preemptions` 列必须来自引擎日志计数，而不是推测。它是判断「是否越过稳定容量点」最直接的证据：只要该列非零，对应的吞吐数字就不能作为可持续工作点。

### 9.2 结论规则

- 理论容量大于实测：差值来自工作区、图捕获、元数据、碎片与安全余量；
- Prefix Warm Hit 只改善重复长前缀：这是预期边界，不是随机负载回归；
- 更小 Block 碎片更少但吞吐下降：元数据/调度/Kernel 成本可能变高；
- 并发升高后抢占出现：已经越过稳定容量点，最大吞吐未必满足 SLO；
- 低精度 KV 容量上升但质量或 TPOT 变差：必须按产品目标决策，不能只看显存。

这五条规则的共同点是「收益必须附代价」。任何只写单侧指标的结论（容量翻倍、碎片下降、命中提升）都不足以支撑配置变更，因为 KV Cache 的每一项优化几乎都在容量、延迟、质量三者之间做交换。

## 10. 常见错误与排查

### 10.1 KV 公式中的 Head 数用错

使用 KV Head 数，而不是 Query Head 数。GQA/MQA 两者不同，应读取模型配置。把 GQA 模型的 Query Head 数代入公式，会把容量低估数倍。

### 10.2 把 Max Context 当每个请求实际使用

容量规划可用上界，但真实碎片和平均容量依请求长度分布。必须报告 P50/P95/P99 长度。

### 10.3 Prefix A/B 的请求不一致

除 Prefix Cache 开关外，模型、Prompt、输出、顺序、并发和服务配置必须一致。尤其注意重启服务后 CUDA Graph 重新捕获带来的冷启动差异，两组都要充分热身。

### 10.4 把第一条请求当命中

缓存需要填充。Cold Fill、Warm Hit 与 Miss 应分开统计。

### 10.5 只看 `nvidia-smi` 已用显存

总已用显存不能区分权重、KV、工作区和图池。结合引擎日志、Profiler 和容量公式。vLLM 通常会按 `gpu_memory_utilization` 预先占住显存，因此 `nvidia-smi` 的读数在压测前后几乎不变，无法反映 KV 实际使用率。

### 10.6 Offload 后平均延迟正常就宣布成功

换入换出通常影响尾部。必须看 P95/P99、Preemption、PCIe 和 Host 内存压力。

### 10.7 用随机 Prompt 测缓存

随机 Prefix 不可复用。应构造业务真实共享 System Prompt、文档前缀或多轮会话。

## 11. 优化前后对照

| 层次 | 基线 | 优化 | 验证 |
| --- | --- | --- | --- |
| 模型 | MHA/GQA 固定 | 合理 KV Head | 质量与容量 |
| 分配 | 最大长度预留 | Paged Block | 碎片与吞吐 |
| 复用 | 重算 Prefill | Prefix Cache | Cold/Hit/Miss |
| 精度 | BF16/FP16 KV | 支持的低精度 KV | 质量、容量、TPOT |
| 容量 | 激进并发 | SLO 驱动并发 | Preemption/Goodput |
| 层级 | GPU Only | 合法 Offload | PCIe、NUMA、P99 |

六个层次的可改动成本递增：模型结构需要重新训练或选择 checkpoint，分配与复用只需改服务配置，精度与 Offload 还牵涉硬件支持。因此调优顺序应从上往下逐层排除，先确认容量规划口径正确，再动配置，最后才考虑精度与层级扩展。

## 12. 常见追问与解答

### 12.1 KV Cache 每 Token 字节数由什么决定

层数、KV Head 数、Head Dimension、K/V 两份张量和元素精度。与 Query Head 数、隐藏层 FFN 维度无关。

### 12.2 PagedAttention 主要解决什么问题

它用固定大小 Block 按需管理非连续 KV，减少按最大长度预留造成的浪费，并支持更灵活的请求生命周期与共享。附带收益是 Block 粒度的引用计数让 Prefix 共享成为可能。

### 12.3 Block 越小越好吗

不一定。内部碎片降低，但 Block Table、调度和 Kernel 元数据成本可能上升。

### 12.4 Prefix Cache 什么时候收益最大

共享前缀长、命中率高且 Prefill 成本占比较大时。随机短 Prompt 收益有限。

### 12.5 为什么 GQA 能减少 KV 显存

多个 Query Head 共享较少的 KV Head，缓存的 K/V Head 数下降。Query 侧计算量基本不变，因此 GQA 主要省显存与 KV 读带宽。

### 12.6 KV Offload 的主要风险

跨 PCIe/网络传输增加带宽压力和尾延迟，还受 NUMA、Pinned Memory、Host 容量和故障恢复影响。

## 13. 延伸练习

1. 对同一隐藏维度扫描 KV Head 数，计算每 Token 字节与并发容量。
2. 用真实请求长度分布替换均匀随机分布，比较 Block Size。
3. 分开报告 Prefix Cold、Warm Hit、Random Miss 的 TTFT。
4. 扫描最大模型长度，记录引擎 KV Token Capacity。
5. 制造容量压力，找到第一次 Preemption 前的最大稳定并发。
6. 若硬件支持，比较 BF16 与 FP8 KV 的容量、质量和 TPOT。
7. 加入 Host Offload，记录 PCIe 与 P99。
8. 把 KV 容量门禁加入服务发布 CI。

## 14. 项目验收 Checklist

- KV 公式使用实际层数、KV Head、Head Dimension 与 dtype。
- 理论容量与引擎实测容量都已保存。
- 已扫描 Block Size 并同时看碎片与性能。
- 已构造 Prefix Cold/Hit/Miss 三组负载。
- 已报告 TTFT、TPOT、Token/s、显存、命中与 Preemption。
- 已扫描上下文与并发，找到稳定容量边界。
- Offload 实验包含 PCIe/NUMA 与尾延迟。
- CPU 模拟没有被写成 GPU 或 vLLM 实测。
- FP8/FP4 只在真实支持的硬件与工具链上验证。
- 所有结论注明模型、版本、长度分布、并发和硬件。

## 写在最后

KV Cache 的实验价值在于把「显存够不够」这个模糊问题拆成四个可测量的量：每 Token 字节、可用 Token 容量、碎片率、抢占次数。四者对齐之后，并发与上下文长度的配置就不再靠试错。下一个项目把视角从单实例内部拉到实例之间，讨论 Prefill 与 Decode 解耦后的系统设计。

下一篇：[Disaggregated Inference 系统设计](/source/AI-Infra/2-AI系统性能工程/35-DisaggregatedInference系统设计)。