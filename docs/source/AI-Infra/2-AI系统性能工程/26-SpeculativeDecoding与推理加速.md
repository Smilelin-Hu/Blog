# Speculative Decoding 与推理加速

本篇讲清 Speculative Decoding 的验证与接受机制，掌握在保证输出质量前提下加速推理的方法。

大模型 Decode 阶段有一个近乎反直觉的特点：每一步只生成一个 Token，矩阵规模很小，却要把整套模型权重从显存读一遍。GPU 往往不是算不动，而是每次只干了一点活就必须等待下一步。

Speculative Decoding（推测解码）不改变目标模型，而是让一个更便宜的「草稿器」先猜若干 Token，再让目标模型一次并行验证。猜得准，目标模型一次前向就提交多个 Token；猜错，只丢弃错误后缀并按目标模型修正。它优化的是串行轮数，不是简单地把模型量化或缩小。

## 1. 内容概览

四个问题贯穿全篇：为什么一次验证多个 Token 可能比逐 Token 解码快；为什么「草稿猜错」仍能保持目标模型分布；何时推测解码会加速、何时反而变慢；如何在消费级 GPU、数据中心 GPU 与真实推理框架中测量它。

具体内容包括：草稿、验证、接受、拒绝、修正与 KV Cache 回滚的区分；平均每轮提交 Token 数与粗略加速比的推导；严格拒绝采样为何能保持目标分布；Draft/Target、N-gram、Medusa、EAGLE、MTP 等路线的比较；用 acceptance rate、accepted length、draft/verify latency 与 TPOT 判断瓶颈。

## 2. 核心直觉：把时间上的串行改成一次空间并行

普通 Decode 生成 4 个 Token，需要目标模型连续运行 4 次：

![串行 Decode 四次前向 vs 推测解码一次验证](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l26_02.png)

推测解码先让便宜的草稿器提出 `d1,d2,d3,d4`，目标模型用因果掩码一次计算这 4 个位置的分布：

![推测解码：草稿串行提议，目标一次并行验证](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l26_01.png)

目标模型仍然要读权重，但一次读权重服务了多个候选位置。小 Batch Decode 原本常受显存带宽与串行依赖限制，验证阶段把更多算术工作塞进同一次前向，可能提高算术强度与 GPU 利用率。

关键不是「猜得越多越好」，而是**每轮期望提交 Token 数的增长，必须超过草稿与验证成本的增长**。


## 3. 算法原理

### 3.1 Greedy 场景

若温度为 0，目标模型每个位置取 argmax。草稿 Token 与目标 argmax 相等就接受，从左到右遇到第一次不相等即停止；错误位置由目标模型 Token 替换，后续草稿全部丢弃。

例如草稿为 `A B X Y`，目标验证结果为 `A B C ...`，本轮提交 `A B C`。虽然 `X Y` 被计算过，但输出与普通 greedy 解码一致。

### 3.2 Sampling 场景：不能只比较 Token 是否相等

设目标分布为 $p(x)$、草稿分布为 $q(x)$。从 $q$ 采样候选 $x$ 后，以

$$
a(x) = \min\left(1, \frac{p(x)}{q(x)}\right)
$$

的概率接受。若拒绝，则从修正分布采样：

$$
p'(x) = \frac{\max(0, p(x)-q(x))}{\sum_y \max(0, p(y)-q(y))}
$$

这个「接受—修正」过程使最终样本仍来自目标分布 $p$。因此理论上的 lossless 指「输出分布不变」，不是「固定随机种子下每次文本逐字相同」。浮点舍入、批形变化、并行采样与随机数消费顺序仍可能导致单次输出不同。

工程上要特别检查：草稿与目标使用相同 tokenizer 与词表映射；temperature、top-p、top-k 等参数在验证器中一致；拒绝后使用修正分布而不是随便重采样；greedy equality 与 sampling convergence 分开测试；质量检查不能只看几条人工样例。

### 3.3 一轮状态变化

1. 调度器为请求预留最多 $K$ 个草稿 Token 的 KV 空间。
2. 草稿器生成线性链或候选树。
3. 目标模型在一次前向中验证候选。
4. 采样器得到最长可接受前缀。
5. 提交接受 Token 与一个目标修正 Token。
6. 释放或回滚被拒绝后缀占用的 KV Block。
7. 进入下一轮，直到 EOS 或长度上限。

Paged KV Cache 中的「回滚」通常是调整逻辑长度、引用计数或空闲块标记，不应复制整段 KV；若实现发生大规模显存搬运，回滚会成为新瓶颈。

## 4. 关键性能模型

### 4.1 平均每轮提交多少 Token

假设每个草稿 Token 独立地以固定概率 $\alpha$ 被接受，最多草拟 $K$ 个，每轮提交「接受前缀 + 一个目标 Token」：

$$
E[N] = 1 + \alpha + \alpha^2 + \cdots + \alpha^K = \frac{1-\alpha^{K+1}}{1-\alpha}
$$

当 $\alpha = 1$ 时 $E[N] = K+1$。真实系统的接受事件并不独立，EOS、候选树、变长草稿与采样策略也会改变结果，所以公式用于容量判断，不替代实测。

### 4.2 加速比近似

记 $t_T$ 为普通目标模型生成一个 Token 的时间，$t_D$ 为草稿器生成一个 Token 的时间，$t_V(K)$ 为目标模型验证 $K$ 个候选的时间，$t_O$ 为调度、采样、KV 管理等额外开销：

$$
S \approx \frac{E[N] \cdot t_T}{K \cdot t_D + t_V(K) + t_O}
$$

只有 $S > 1$ 才值得开启。它揭示三条重要规律：草稿器即使很准，若太慢也不会加速；$K$ 增大会增加潜在提交数，也会增加草稿与验证成本；大 Batch 下目标 GPU 已经饱和，$t_V(K)$ 可能接近线性增长，收益会消失。

### 4.3 服务指标

推测解码最常改善 TPOT/ITL，不一定改善 TTFT。应同时记录：

| 指标 | 含义 | 诊断价值 |
| --- | --- | --- |
| Acceptance rate | 被接受草稿 Token / 草稿 Token | 草稿与目标匹配度 |
| Mean accepted length | 每轮平均接受前缀长度 | 串行轮数减少程度 |
| Draft latency | 每轮草稿耗时 | 草稿是否过重 |
| Verify latency | 目标批量验证耗时 | 验证是否真正并行获益 |
| Rejected tokens | 被丢弃的草稿工作量 | 过深草稿的浪费 |
| TPOT / ITL | 输出 Token 间延迟 | 交互体验 |
| Tokens/s | 每秒输出 Token | 单请求或整体吞吐 |
| P50/P99 | 延迟分位数 | 尾延迟与调度抖动 |
| GPU 利用率/带宽 | 计算与内存状态 | 是否仍为低利用率 Decode |

## 5. 主要技术路线

| 路线 | 机制 | 代价与前提 |
| --- | --- | --- |
| Draft/Target 双模型 | 较小且 tokenizer 兼容的模型自回归提出 K 个候选，目标统一验证 | 多占一份权重与 KV；跨 GPU 放置引入 PCIe/NVLink 同步 |
| N-gram / Prompt Lookup / Suffix | 从 prompt、已生成文本或共享后缀结构找重复片段，不加载神经草稿 | 代码生成、文档复述、模板命中率高；开放创作命中率低 |
| Medusa | 目标模型上增加多个解码头并行预测未来位置，组成候选树 + tree attention | 需训练额外头；树宽、树深与验证成本联合调优 |
| EAGLE | 在特征空间而非只在 Token 空间外推未来状态，后续版本用动态树改善候选 | 依赖与目标匹配的 checkpoint 与运行时实现 |
| MTP | 目标模型原生未来 Token 预测模块充当草稿器（如 DeepSeek V3/R1） | 与训练、隐藏状态、KV 管理紧密耦合，不是命令行开关 |
| Self-Speculative / 层跳过 | 同一模型用部分层、早退或蒸馏分支草拟，再用完整层验证 | 需处理共享 KV、隐藏状态与图捕获；依赖关系可能限制并行 |

N-gram 路线显存与草稿计算开销小，适合作为消费级 GPU 的第一条实验路径。

## 6. 瓶颈分析方法

### 6.1 第一步：确认基线真的适合推测解码

优先选择低到中 QPS、小 Batch、Decode 占主导、目标模型内存带宽受限的负载。若服务已经通过 Continuous Batching 把 GPU 填满，推测解码可能只是扩大每轮 Token 数而没有减少总 GPU 时间。

### 6.2 第二步：分解一轮时间

不要只测总 tokens/s。至少对以下区间加 NVTX 或 profiler 标记：

![推测解码服务流水线：草稿与验证的阶段衔接](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l26_03.png)

若 `draft` 占比高，缩小草稿模型或用 N-gram；若 `target_verify` 随 $K$ 近线性增长，减小 $K$ 或检查 attention/kernel；若 `prepare/rewind` 高，检查 Python 调度、动态 shape、block 管理与同步。

### 6.3 第三步：画 acceptance 与 K 的二维表

分别在真实 prompt 集、不同 temperature、不同输出类型与不同并发下测量 $K = 1,2,4,6,8$。最优 $K$ 是工作负载属性，不是模型常量。

### 6.4 第四步：检查正确性

Greedy 与普通解码逐 Token 相等；Sampling 用大量样本的 Token 频率/统计检验接近目标分布；EOS、停止词、结构化输出、logprobs、LoRA 与量化路径分别测试；被拒绝 Token 的 KV 不得污染后续输出。

## 7. 环境准备

Level 0 仅需 Python 3.9+。Level 1 使用隔离环境安装 PyTorch；CUDA wheel 必须按 PyTorch 官方安装页选择，不要把系统 CUDA 版本直接当作 wheel 标签。

```bash
python3 -m venv .venv-specdecode
source .venv-specdecode/bin/activate
python -m pip install --upgrade pip
# CPU 通用路径
python -m pip install "torch>=2.3"

python - <<'PY'
import torch
print("PyTorch:", torch.__version__)
print("CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print("GPU:", p.name)
    print("Compute Capability:", f"{p.major}.{p.minor}")
    print("VRAM GiB:", round(p.total_memory / 2**30, 2))
PY
```

## 8. Level 0：CPU 蒙特卡洛容量模拟器

保存为 `speculative_decoding_sim.py`：

```python
#!/usr/bin/env python3
import argparse
import random

def expected_tokens(alpha: float, k: int) -> float:
    if abs(alpha - 1.0) < 1e-12:
        return k + 1.0
    return (1.0 - alpha ** (k + 1)) / (1.0 - alpha)

def run(tokens, k, alpha, target_ms, draft_ms, verify_base_ms,
        verify_per_token_ms, overhead_ms, seed):
    rng = random.Random(seed)
    emitted = rounds = accepted = proposed = rejected = 0
    spec_ms = 0.0

    while emitted < tokens:
        rounds += 1
        a = 0
        for _ in range(k):
            proposed += 1
            if rng.random() < alpha:
                a += 1
                accepted += 1
            else:
                break

        # 接受前缀后，总有一个来自目标分布的 token 可提交；末尾截断。
        committed = min(a + 1, tokens - emitted)
        emitted += committed
        rejected += k - a
        spec_ms += (k * draft_ms + verify_base_ms
                    + k * verify_per_token_ms + overhead_ms)

    base_ms = tokens * target_ms
    empirical_n = tokens / rounds
    theoretical_n = expected_tokens(alpha, k)
    print(f"tokens={tokens} k={k} alpha={alpha:.3f}")
    print(f"rounds={rounds} empirical_tokens/round={empirical_n:.3f}")
    print(f"theoretical_tokens/round={theoretical_n:.3f}")
    print(f"accepted/proposed={accepted}/{proposed} ({accepted/max(1, proposed):.3f})")
    print(f"rejected_or_unused_slots={rejected}")
    print(f"baseline_ms={base_ms:.2f} speculative_ms={spec_ms:.2f}")
    print(f"estimated_speedup={base_ms/spec_ms:.3f}x")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=4096)
    p.add_argument("--draft-k", type=int, default=4)
    p.add_argument("--acceptance", type=float, default=0.75)
    p.add_argument("--target-ms", type=float, default=8.0)
    p.add_argument("--draft-ms", type=float, default=0.45)
    p.add_argument("--verify-base-ms", type=float, default=8.5)
    p.add_argument("--verify-per-token-ms", type=float, default=0.25)
    p.add_argument("--overhead-ms", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    if not 0.0 <= a.acceptance <= 1.0 or a.draft_k < 1:
        p.error("acceptance 必须在 [0,1]，draft-k 必须 >= 1")
    run(a.tokens, a.draft_k, a.acceptance, a.target_ms, a.draft_ms,
        a.verify_base_ms, a.verify_per_token_ms, a.overhead_ms, a.seed)
```

运行三组对照：

```bash
python speculative_decoding_sim.py --draft-k 4 --acceptance 0.80
python speculative_decoding_sim.py --draft-k 8 --acceptance 0.80
python speculative_decoding_sim.py --draft-k 4 --acceptance 0.35
```

预期现象：高接受率下单轮提交 Token 数增加；但 $K$ 从 4 增到 8 并不保证继续加速，因为草稿与验证成本也增加。低接受率时推测路径可能慢于基线。模拟数字是输入参数推导的容量结果，不代表任何具体 GPU。

## 9. Level 1：通用 PyTorch 验证批处理微基准

这个实验不下载 LLM，而是测量系统核心机制：「目标网络运行 K 次」与「把 K 个位置合成一次验证」之间的差异。它是 kernel/调度微基准，不声称生成语义等价。保存为 `verify_batch_benchmark.py`：

```python
#!/usr/bin/env python3
import argparse
import time
import torch
from torch import nn

def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)

def bench(fn, device, warmup=10, iters=50):
    for _ in range(warmup):
        fn()
    sync(device)
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    sync(device)
    return (time.perf_counter() - t0) * 1000 / iters

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--hidden", type=int, default=2048)
    p.add_argument("--draft-k", type=int, default=4)
    p.add_argument("--acceptance", type=float, default=0.75)
    p.add_argument("--iters", type=int, default=50)
    a = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    print("device=", device, "torch=", torch.__version__)
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(0)
        print("gpu=", prop.name, "cc=", f"{prop.major}.{prop.minor}",
              "vram_GiB=", round(prop.total_memory / 2**30, 2))

    target = nn.Sequential(
        nn.Linear(a.hidden, 4 * a.hidden, bias=False), nn.GELU(),
        nn.Linear(4 * a.hidden, a.hidden, bias=False)
    ).to(device=device, dtype=dtype).eval()
    draft = nn.Sequential(
        nn.Linear(a.hidden, a.hidden // 2, bias=False), nn.ReLU(),
        nn.Linear(a.hidden // 2, a.hidden, bias=False)
    ).to(device=device, dtype=dtype).eval()

    x = torch.randn(a.batch, a.hidden, device=device, dtype=dtype)
    xk = torch.randn(a.batch * a.draft_k, a.hidden,
                     device=device, dtype=dtype)

    @torch.inference_mode()
    def target_sequential():
        y = x
        for _ in range(a.draft_k):
            y = target(y)
        return y

    @torch.inference_mode()
    def target_verify_batch():
        return target(xk)

    @torch.inference_mode()
    def draft_sequential():
        y = x
        for _ in range(a.draft_k):
            y = draft(y)
        return y

    seq_ms = bench(target_sequential, device, iters=a.iters)
    verify_ms = bench(target_verify_batch, device, iters=a.iters)
    draft_ms = bench(draft_sequential, device, iters=a.iters)
    alpha = a.acceptance
    expected = ((1 - alpha ** (a.draft_k + 1)) / (1 - alpha)
                if alpha < 1 else a.draft_k + 1)
    one_target_ms = seq_ms / a.draft_k
    estimated = expected * one_target_ms / (draft_ms + verify_ms)

    print(f"K sequential target calls: {seq_ms:.3f} ms")
    print(f"one batched target verify: {verify_ms:.3f} ms")
    print(f"K draft calls: {draft_ms:.3f} ms")
    print(f"expected committed/round: {expected:.3f}")
    print(f"model-only estimated speedup: {estimated:.3f}x")
    print("注意：未计入 attention、KV、采样、调度和回滚开销。")

if __name__ == "__main__":
    main()
```

运行命令：

```bash
python verify_batch_benchmark.py --batch 1 --hidden 2048 --draft-k 4
python verify_batch_benchmark.py --batch 16 --hidden 2048 --draft-k 4
python verify_batch_benchmark.py --batch 1 --hidden 2048 --draft-k 8
```

显存不足时使用 `--hidden 1024`。预期现象是小 Batch 时一次批量验证通常比 K 次目标调用更有效；Batch 增大后目标调用本身已有较高利用率，优势可能缩小。结果必须连同 GPU 型号、Compute Capability、PyTorch/CUDA 版本与参数保存。

## 10. Level 2：真实框架专项实验

### 10.1 vLLM：先从无草稿模型的 N-gram 开始

vLLM 的当前接口使用 JSON 形式的 `--speculative-config`。下面命令只示范配置结构，模型、显存利用率与最大长度应按本机调整：

```bash
vllm serve /path/to/target-model \
  --speculative-config '{
    "method":"ngram",
    "num_speculative_tokens":4,
    "prompt_lookup_min":2,
    "prompt_lookup_max":5
  }'
```

双模型路径：

```bash
vllm serve /path/to/target-model \
  --speculative-config '{
    "method":"draft_model",
    "model":"/path/to/tokenizer-compatible-draft-model",
    "num_speculative_tokens":4,
    "draft_tensor_parallel_size":1
  }'
```

先用 `vllm --version` 与对应版本文档核对字段，不要把旧版 `--speculative-model` 示例与新版 `--speculative-config` 混用。基线与优化必须使用相同 prompt、采样参数、并发与输出长度，并记录 acceptance 与 P50/P99 TPOT。

### 10.2 TensorRT-LLM：能力随版本变化

TensorRT-LLM 的 LLM API 可配置 Draft/Target、NGram、EAGLE 3、MTP 等路线：

```python
from tensorrt_llm import LLM
from tensorrt_llm.llmapi import NGramDecodingConfig

config = NGramDecodingConfig(
    max_draft_len=3,
    max_matching_ngram_size=4,
    is_public_pool=False,
)
llm = LLM("/path/to/target-model", speculative_config=config)
```

具体类名与支持矩阵以安装版本文档为准。MTP 需要模型原生支持，EAGLE 需要匹配 checkpoint；不能把 N-gram 的成功运行视为 MTP/EAGLE 的等价验证。

## 11. 硬件适配与边界

| 层级 | 硬件 | 建议实验 | 不能据此声称 |
| --- | --- | --- | --- |
| Level 0 | 任意 CPU | 容量模型、接受率与 K 扫描 | 真实 GPU 加速比 |
| Level 1 | 任意 PyTorch CPU/CUDA | 连续目标调用 vs 批量验证 | 完整 LLM 端到端收益 |
| Ampere | RTX 3080/3090、A100 | FP16/BF16 能力检测后做小 Batch 验证；3090 可容纳更大草稿 | 3080 双卡具备 NVLink |
| Ada | RTX 4090、L40/L40S | 单卡目标 + 轻量草稿或 N-gram | RTX 4090 属于 Blackwell |
| Hopper | H100/H200 | 数据中心框架、FP8 模型、CUDA Graph 专项 | 消费卡可等价模拟 Hopper |
| Blackwell | RTX 5090、B100/B200/GB200 | 新低精度与专用 kernel 的框架实测 | RTX 5090 等同 B200/GB200 |

双 RTX 3080 20GB 上，优先把目标与轻量草稿放在同一张卡，或先使用 N-gram。把草稿放到第二张卡会经过 PCIe 传输与跨设备同步，只有端到端实测证明收益后才保留。消费级 3080 之间通常没有 NVLink，不能套用 A100/H100 NVLink 结论。

## 12. 结果分析模板

建议每组实验保存：

```text
模型/量化：
GPU/CC/显存：
框架/PyTorch/CUDA：
Prompt 数据集：
并发与 batch：
采样参数：
K / 草稿方法：
Acceptance rate：
Mean accepted length：
Draft / Verify / Rewind ms：
Baseline vs Spec TTFT：
Baseline vs Spec TPOT：
Baseline vs Spec tokens/s：
P50/P99：
正确性检查：
```

如果 TPOT 下降而 TTFT 上升，这是合理现象：初始化草稿器或图捕获增加首 Token 成本。若平均接受长度很高但仍变慢，重点看草稿器耗时、跨 GPU 同步、动态 shape、验证 kernel 与 Python 调度，而不是继续提高接受率。

## 13. 常见错误与排查

**开启后反而变慢**：可能是 Batch 已很大、草稿模型过重、$K$ 过大、接受率低、验证 kernel 未优化或 CPU 调度占比高。先分解一轮耗时，再分别扫描并发与 $K$。

**草稿接受率接近零**：检查 tokenizer、词表大小、special token、chat template、模型家族、量化方式与采样参数。仅仅「参数量更小」不代表它是合格草稿模型。

**显存突然不足**：草稿权重、草稿 KV、目标验证的扩张 Token、CUDA Graph 静态 buffer 都会额外占显存。降低 `num_speculative_tokens`、最大 Batch、最大长度，或使用无模型 N-gram。

**输出与基线不一致**：Greedy 模式先做逐 Token equality；Sampling 模式不要只比较单次字符串，核对拒绝采样实现、随机数、logits processor、停止条件与浮点精度，并做分布统计。

## 14. 量化补充：验证成本与草稿长度的动态选择

第 4 节的公式代入实测数字后有几个反直觉结论。**平均口径要用总时间除总 token**：两轮各 1.5 ms、分别输出 1 和 5 个 token，平均每 token 0.5 ms；若把每轮的 1.5 与 0.3 ms/token 等权平均会得 0.9 ms——让只输出一个 token 的轮次占了相同权重。**验证几乎不增加一轮的时间**：RTX PRO 6000 batch 1、2K 上下文普通 decode 一轮 26.26 ms，验证 5 个位置读的权重与 KV 相同，多出 4 行矩阵运算约 65 GFLOP 按峰值 62% 计仅约 0.2 ms；DFlash 每轮并行生成 7 草稿验证 8 位置，中位 15.2 ms 与普通一步 16.9 ms 相当。因此即使接受率很低也仍有加速：两符号分布下草稿 AAAA（$a=1/4$，$\mathbb E[N]\approx1.33$）每 token 约 19.8 ms，BBBB（$a=3/4$，$\mathbb E[N]\approx3.05$）约 8.64 ms，都快于 26.26 ms——每轮至少保底一个 token。但草稿查询有成本预算：要优于普通 decode，AAAA 留给查询的时间约 8.7 ms、BBBB 约 53.9 ms；准备工作也要摊销，建索引 2 s、每 token 省 17.6 ms，约 114 个 token 回本，索引提前建好多请求共用则摊得更薄。

**串行与并行草稿的取舍随接受率翻转**。DFlash 权重约 1.95 GiB，按 batch 1 有效带宽 588 GB/s 前向一次约 3.57 ms：逐个生成 4 草稿要 14.28 ms，并行一次只要 3.57 ms；每轮平均输出 3 个时串行每 token 约 13.5 ms、并行约 9.9 ms。但若并行草稿接受率低、平均输出降为 2，并行反而升到 14.9 ms 慢于串行——更快的草稿生成省了 10.7 ms，每轮输出减少却抬高了分摊。

**草稿长度的边际条件**：长度 $m$ 的平均输出 $\mathbb E[N_m]=1+\sum_{j=1}^{m}\prod_{i=1}^{j}a_i$，从 $m-1$ 增到 $m$ 多输出 $\Delta N=\prod_{i=1}^{m}a_i$、多耗时 $\Delta T$，加长划算的条件是

$$
\frac{\Delta T}{\Delta N}<\frac{T}{N}.
$$

接受概率逐项相乘，越靠后的草稿越难保住，加长越难回本。预设形状还会让 $\Delta T$ 跳变：验证 4 或 5 个 token 都补齐到 8 行图时加一个很便宜，从 8 增到 9 要换 16 行图、计算突增。实测：Qwen3-8B/DFlash 短提取任务并发 1，普通 decode、K7、K15 完整耗时中位约 90.0、30.6、29.4 ms——普通改 K7 省约 59 ms，K7 改 K15 只再省 1.2 ms；还出现两种块长都只接受一个草稿的轮次，K7 丢 6 个、K15 丢 14 个，输出相同而大验证块白算。并发也改变收益：低负载时多行验证用闲置算力，高负载时普通批处理已充分共享权重，草稿与验证还要争资源。动态策略因此是：接受概率高、加位置便宜的请求加长草稿；前几个位置就常被拒或要换更大形状的缩短块长，并给目标与草稿模型的 KV 留出空间（25 篇第 15 节的容量账）。

## 写在最后

推测解码的收益来自「一次读权重服务多个候选位置」，因此它天然偏爱小 Batch、带宽受限的 Decode 负载；一旦 GPU 已被大 Batch 填满，或草稿与回滚开销超过节省的串行轮数，它就会失效。下一篇把视角拉到集群层面，看 Prefill 与 Decode 解耦如何在系统架构上消除两阶段的相互干扰。

下一篇：[Disaggregated Inference 架构](/source/AI-Infra/2-AI系统性能工程/27-DisaggregatedInference架构)。