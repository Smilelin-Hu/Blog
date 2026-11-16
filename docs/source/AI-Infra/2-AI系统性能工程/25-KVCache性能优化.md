# KV Cache 性能优化

本篇从显存占用、访问效率与分页管理出发优化 KV Cache，提高长上下文与高并发推理能力。

自回归 LLM 每生成一个 Token，都需要关注之前的 Token。如果每一步都重新计算全部历史 Key 与 Value，生成第 $t$ 个 Token 时会重复执行大量已经完成的工作。KV Cache 保存各层历史 Attention 的 Key/Value，让 Decode 只计算新 Token 的投影，再读取历史缓存完成 Attention。

它用显存换计算，却很快成为服务容量与 Decode 带宽的核心约束：上下文越长，KV 线性增长；并发越高，在途 Token 总数越多；Decode 每步都要读取历史 KV；请求长度动态变化，连续预留会产生碎片；Prefix 复用、Offload 与解耦推理又把它变成跨请求、跨设备的数据资产。

## 1. 内容概览

- 从 Attention 计算推导 KV Cache 的作用与容量公式。
- MHA、GQA、MQA、MLA 对 KV 容量与带宽的影响。
- 连续预留、Paged KV、Block Table 与内部/外部碎片。
- Prefix Cache 的命中条件、收益、驱逐与多租户安全。
- KV 低精度、滑动窗口、Offload、重算与跨节点传输的评价方法。
- KV 容量、带宽、命中率与 Goodput 的统一模型。
- 用真实流量诊断 OOM、Preemption、Cache Thrash 与 TPOT 上升。

## 2. 核心直觉：KV Cache 是「Attention 的历史索引」

单层 Self-Attention 计算：

$$
Q = XW_Q,\quad K = XW_K,\quad V = XW_V
$$

$$
Attention(Q,K,V) = softmax\left(\frac{QK^T}{\sqrt{d}} + Mask\right)V
$$

在 Decode 第 $t$ 步，历史 Token 的 $K_1 \ldots K_{t-1}$ 与 $V_1 \ldots V_{t-1}$ 不会改变。只需计算新 Token 的 $Q_t, K_t, V_t$，把 $K_t, V_t$ 追加进缓存，再执行：

$$
O_t = softmax\left(\frac{Q_t[K_1,\ldots,K_t]^T}{\sqrt{d}}\right)[V_1,\ldots,V_t]
$$

因此 KV Cache 消除了历史 K/V 投影的重复计算，但没有消除对历史 KV 的读取。上下文越长，单步读取量越大；KV 优化既是容量问题，也是 HBM 带宽问题。

## 3. KV Cache 容量模型

### 3.1 每 Token 容量

对常见 Decoder-only Transformer：

$$
M_{token} = 2 \cdot L \cdot H_{kv} \cdot D_{head} \cdot B_{elem}
$$

其中 2 表示 Key 与 Value，$L$ 是层数，$H_{kv}$ 是 KV Head 数，$D_{head}$ 是每个 Head 维度，$B_{elem}$ 是每元素字节数。一个请求当前序列长度为 $S$ 时 $M_{request} = S \cdot M_{token}$；在线系统所有活动请求：

$$
M_{active} = M_{token} \cdot \sum_{i=1}^{N} S_i
$$

容量取决于所有在途 Token 总数，而不仅是最大并发数。

### 3.2 示例

假设 32 层、8 个 KV Head、Head Dim 128、FP16/BF16 KV：

$$
M_{token} = 2 \times 32 \times 8 \times 128 \times 2 = 131072\ bytes = 128\ KiB
$$

一个 4096 Token 请求约占 512 MiB KV；32 个同长度请求约占 16 GiB。这个例子没有包含权重、Activation、Workspace、CUDA Graph、通信 Buffer 与碎片。

### 3.3 MHA、GQA 与 MQA

| 结构 | KV Head 数 | KV 容量 | Decode 读取 |
| --- | --- | --- | --- |
| MHA | 通常等于 Query Head | 最大 | 最大 |
| GQA | 多个 Query Head 共享一组 KV | 较小 | 较小 |
| MQA | 所有 Query Head 共享一个 KV Head | 最小 | 最小 |

GQA/MQA 是模型结构，不是部署时随意切换的 Runtime 参数。转换 Head 结构通常需要训练或专门权重变换及质量验证。

### 3.4 TP 下的 KV

张量并行可把 KV Head 分散到 Rank，每 Rank 容量常近似下降到 $1/TP$，但具体取决于 Head 数是否可整除、是否复制 KV Head、Attention Backend 与模型结构。不能直接用「总 KV / 卡数」替代框架启动日志与实测。

## 4. 连续预留为什么浪费显存

朴素 Runtime 可能为每个请求预留 `[max_seq_len]` 的连续 KV，内部碎片率为

$$
Waste_{contiguous} = 1 - \frac{\sum_i S_i}{N \cdot S_{max}}
$$

请求输出长度未知，按最大长度预留会浪费；按当前长度频繁扩容又会复制大 Tensor、产生外部碎片与地址变化。

## 5. Paged KV 与 Block Table

### 5.1 基本结构

Paged KV 把物理缓存拆成固定 Token 数的 Block，请求维护逻辑 Block 到物理 Block 的映射：

```text
请求 A 逻辑 Block:  [0] [1] [2]
                     │   │   │
物理 Block 池:      #7  #2  #9   （物理上不连续）

请求 B 逻辑 Block:  [0] [1]
                     │   │
物理 Block 池:      #7  #4       （#7 为共享只读 Prefix）
```

逻辑连续不要求物理连续。请求增长时只申请新 Block，完成或取消后归还 Block。

### 5.2 Paged 内部碎片

Block Size 为 $P$ Token、请求长度 $S_i$：

$$
Allocated_i = \left\lceil\frac{S_i}{P}\right\rceil P,\qquad Waste_{paged} = 1 - \frac{\sum_i S_i}{\sum_i Allocated_i}
$$

每请求最多浪费 $P-1$ 个尾部 Token。Block 小可减少尾部浪费，却增加 Block Table、哈希、调度与寻址开销；Block 大则相反。

### 5.3 PagedAttention 解决什么

PagedAttention 让 Attention Kernel 根据 Block Table 访问非连续物理 KV。内存管理与 Kernel 必须协同，否则仅有分页分配器而 Kernel 仍要求连续 Tensor，就无法避免拼接/复制。

收益包括按需增长、完成/取消后快速回收、支持连续组批、共享只读 Prefix Block、更灵活的抢占/Offload/跨设备传输。它并非「零浪费」：仍有尾 Block、元数据、对齐、多个 KV Pool 与保留水位。

## 6. KV Cache 生命周期

- **分配**：Scheduler 在执行前根据本轮新 Token 数预留 Block。预留失败应触发等待、拒绝或抢占，而不是让 Kernel 运行到 OOM。
- **写入**：Prefill 批量写入 Prompt KV；Decode 每步追加一个或多个 Token。热路径应写入预分配槽位，避免每步 `torch.cat` 复制全部历史。
- **引用计数**：共享 Prefix Block 可被多个请求引用。只有引用计数为 0 的 Block 才能成为可驱逐候选；修改共享 Block 需要 Copy-on-Write 或新的尾 Block。
- **释放**：请求完成、失败或取消时必须释放私有 Block；网络断开要把取消传到 Scheduler/Executor/KV Manager。只丢弃 HTTP 响应会造成 KV 泄漏与无效 Decode。
- **驱逐**：LRU（驱逐最久未访问且无引用的 Block）、Priority + LRU（先按业务/重算价值分级）、Prefix-depth-aware（保留更常用的共享前缀）、Cost-aware（比较重算、传输、命中概率与 Deadline）。

驱逐的真实成本：

$$
Cost_{evict} = P_{reuse} \cdot (T_{reload} + T_{recompute} + T_{queue\ risk})
$$

## 7. Automatic Prefix Caching

### 7.1 核心思想

多个请求若拥有完全相同的 Token Prefix，可共享已计算 KV：

```text
请求 A: [系统提示词 512 Token][用户问题 A]
请求 B: [系统提示词 512 Token][用户问题 B]
                ↑ 只计算一次，B 直接引用缓存 Block
```

只需为共享部分计算一次，其余请求直接引用缓存 Block，可降低 TTFT、Prefill FLOPs 与重复显存。

### 7.2 命中必须以 Token 为准

看起来相同的文本可能因 Chat Template、空格、特殊 Token、Tokenizer Revision、图片占位符或 Adapter 不同而产生不同 Token IDs。安全的 Cache Key 至少应绑定：完整前缀 Token 或链式 Block Hash；模型与权重 Revision；Tokenizer 与 Chat Template；LoRA/Adapter、RoPE/位置相关配置；多模态输入哈希；租户/安全 Salt。不能只用原始字符串或用户可控短 Hash。

### 7.3 Block 粒度命中

若 Block Size 为 16，两个请求共享 30 个 Token，通常只有前 16 个完整 Token Block 可直接命中；尾部 14 Token 可能需要重算或使用支持 Partial Reuse 的实现：

$$
HitTokens = \left\lfloor\frac{SharedPrefix}{P}\right\rfloor P
$$

### 7.4 不是所有请求都受益

适合：长且重复的系统提示词；多轮会话历史；Few-shot 模板；同一文档上的多次问答；Beam/并行 Sampling 的共享 Prompt。

不适合：Prompt 几乎完全不同；Cache 工作集远大于容量并持续 Thrash；Prefix 很短，Hash/元数据成本接近重算；多租户隔离不允许共享。

### 7.5 安全边界

Prefix 命中时间可能泄露其他租户是否使用过某个 Prompt；错误 Cache Key 还可能造成状态串用。多租户系统应使用安全哈希、模型/Adapter 隔离、租户 Salt 与访问控制，并评估时间侧信道。

## 8. 低精度 KV Cache

将 KV 从 FP16/BF16 降到 8-bit，理论容量与读取字节约减半：

$$
M_{KV}^{8bit} \approx \frac{1}{2} M_{KV}^{16bit}
$$

但端到端收益取决于：Attention Kernel 是否原生支持该格式；Scale 粒度与额外元数据；写入时量化、读取时反量化成本；HBM 带宽是否真是瓶颈；长上下文任务的质量误差；GPU 架构与框架 Backend。

CLI 接受 `fp8` 不等于当前 GPU 一定走高效原生路径。必须检查启动日志、Kernel、硬件能力，并做模型质量与端到端 TPOT 对照。FP4/NVFP4 等更新格式只能在真实支持的 Blackwell 软件与硬件路径中验证，不能用 FP16 截断模拟。

## 9. 滑动窗口、稀疏保留与模型结构

若模型采用 Sliding Window Attention，只需保留最近 $W$ 个 Token 的相关层 KV：

$$
M_{layer} \propto \min(S, W)
$$

部分模型混合 Full Attention 与 Local Attention，各层缓存形态不同，需要 Hybrid KV Manager。擅自丢弃全注意力层的旧 KV 会改变模型语义。

MQA/GQA、MLA、State Space/Mamba 与跨 Attention 都有不同缓存结构。现代 Runtime 可能创建多个 KV Pool，「统一每层同一 Block」不再适用于全部模型。

## 10. Offload 与多级缓存

### 10.1 层级与收益条件

Offload 扩大容量，不会让慢介质变成 HBM。传输时间近似

$$
T_{move} = T_{fixed} + \frac{Bytes}{Bandwidth}
$$

只有满足以下关系才可能有净收益：

$$
P_{hit} \cdot T_{recompute} > T_{lookup} + T_{move} + T_{contention}
$$

### 10.2 消费级双卡边界

双 RTX 3080 20GB 常通过 PCIe，活动 Decode 每 Token 往返 Host KV 通常代价很高。可以学习 Pinned Memory、异步传输与冷会话恢复，但不能把 PCIe 实验当作 NVLink-C2C、NVSwitch 或 GPUDirect RDMA 的等价模拟。

### 10.3 分布式 KV 传输

Prefill/Decode 解耦需要把 KV 从 Prefill Worker 传到 Decode Worker。除了带宽，还要考虑 Block 格式与布局兼容、目标端预留、传输完成事件、请求路由与 Cache Locality、失败重试/重复传输/状态一致性、跨租户加密与访问控制。

NCCL 擅长 Collective；NIXL/KV Connector 类接口更聚焦点到点或外部 KV 状态传输。二者不是互相替代关系。

## 11. 瓶颈分析方法

### 11.1 容量指标

总/空闲 KV Block；KV 使用率与 Watermark；活动、可复用、Offloaded、Pinned Block 数；每请求 Token、Block 与尾部浪费；Preemption、Recompute、Eviction 与 OOM；分配/释放速率与泄漏趋势。

### 11.2 Cache 指标

Prefix 查询次数；Token Hit Rate（而不只是请求 Hit Rate）；命中后节省的 Prefill Token 与 TTFT；LRU/优先级驱逐；Thrash（刚驱逐后很快重新加载）；不同租户/模板的工作集大小。

$$
HitRate_{token} = \frac{ReusedPrefixTokens}{EligiblePrefixTokens}
$$

一个请求只命中 16/4096 Token，按请求统计仍算「命中」，却几乎无收益。

### 11.3 性能症状

| 症状 | 优先检查 | 常见根因 |
| --- | --- | --- |
| 并发上升后 OOM | KV Block、Workspace、Graph Pool | 容量估算漏项、Watermark 太高 |
| TPOT 随上下文增长 | KV 读取、Attention Kernel、HBM | Decode 受内存带宽限制 |
| TTFT 波动大 | Prefix Hit、Eviction、Prefill Queue | Cache Thrash、模板不稳定 |
| GPU 有空间却申请失败 | 最大连续块、Allocator/Pool | 连续预留、外部碎片 |
| 取消后 KV 不释放 | 引用计数、Request 生命周期 | 取消未传播、引用泄漏 |
| Offload 后 P99 恶化 | H2D/D2H、Page Fault、PCIe | 热数据误驱逐、无预取/重叠 |
| Prefix 命中异常低 | Token IDs、Block 边界、Revision | Template/Tokenizer/Adapter 不一致 |
| Prefix 命中高但收益低 | 命中 Token 数、Prompt 长度 | 命中太短、Hash/调度成本占比高 |

### 11.4 诊断顺序

1. 用模型配置计算每 Token 理论 KV。
2. 从启动日志记录实际 Block Size、Block 数、Dtype 与 KV 容量。
3. 对比理论值与实测水位，差额归入 Workspace、Graph Pool、通信 Buffer 与碎片。
4. 按请求长度分布估算在途 Token 总数，检查是否长期贴近 Watermark。
5. 统计 Preemption/Recompute/Eviction 次数，并与 ITL 尖峰时间对齐。
6. 分别测 Token Hit Rate 与命中节省的 Prefill Token，判断 Prefix Cache 是否真有收益。
7. 单变量改动（Block Size、KV 水位、KV dtype、Prefix 开关、Offload 策略），用相同流量复测 Goodput。

## 12. Level 0：容量与碎片实验

纯 Python 对比连续预留与 Paged 分配的容量效率，并模拟 Prefix 命中。保存为 `kv_cache_planner.py`：

```python
#!/usr/bin/env python3
import argparse
import random


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--layers", type=int, default=32)
    p.add_argument("--kv-heads", type=int, default=8)
    p.add_argument("--head-dim", type=int, default=128)
    p.add_argument("--kv-bytes", type=float, default=2.0)
    p.add_argument("--requests", type=int, default=64)
    p.add_argument("--max-seq", type=int, default=4096)
    p.add_argument("--mean-seq", type=int, default=1200)
    p.add_argument("--block", type=int, default=16)
    p.add_argument("--prefix", type=int, default=512)
    p.add_argument("--shared-ratio", type=float, default=0.6)
    p.add_argument("--seed", type=int, default=5)
    args = p.parse_args()
    if min(args.layers, args.kv_heads, args.head_dim, args.requests,
           args.max_seq, args.block) <= 0:
        raise SystemExit("参数必须为正数")

    rng = random.Random(args.seed)
    per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.kv_bytes
    seqs = [min(args.max_seq, max(1, int(rng.expovariate(1.0 / args.mean_seq))))
            for _ in range(args.requests)]
    total = sum(seqs)
    mib = 2 ** 20

    contiguous = args.requests * args.max_seq
    paged = sum(-(-s // args.block) * args.block for s in seqs)
    shared_reqs = int(args.requests * args.shared_ratio)
    # 只有完整 Block 可复用，且不能超过请求自身长度
    prefix_saved = sum(min(s, args.prefix) // args.block * args.block
                       for s in seqs[:shared_reqs])

    print(f"kv_bytes_per_token={per_token:.0f} ({per_token/1024:.1f} KiB)")
    print(f"active_tokens={total} kv_gib={total*per_token/2**30:.3f}")
    print(f"contiguous_tokens={contiguous} waste={1-total/contiguous:.3f} "
          f"kv_gib={contiguous*per_token/2**30:.3f}")
    print(f"paged_tokens={paged} waste={1-total/paged:.3f} "
          f"kv_gib={paged*per_token/2**30:.3f}")
    print(f"prefix_shared_requests={shared_reqs} reusable_tokens={prefix_saved} "
          f"saved_gib={prefix_saved*per_token/2**30:.3f}")
    print(f"token_hit_rate={prefix_saved/total:.3f}")
    print("block_size paged_tokens waste tail_waste_per_req")
    for blk in [1, 8, 16, 32, 64, 128]:
        alloc = sum(-(-s // blk) * blk for s in seqs)
        print(f"{blk:10d} {alloc:12d} {1-total/alloc:6.3f} {(alloc-total)/args.requests:18.1f}")
    print("kv_bytes kv_gib_for_active relative_capacity")
    for b in [2.0, 1.0, 0.5]:
        gib = total * per_token * (b / args.kv_bytes) / 2 ** 30
        print(f"{b:8.2f} {gib:18.3f} {args.kv_bytes/b:17.2f}x")


if __name__ == "__main__":
    main()
```

运行：

```bash
python3 kv_cache_planner.py
python3 kv_cache_planner.py --kv-heads 32 --mean-seq 3000 --block 32
python3 kv_cache_planner.py --prefix 2048 --shared-ratio 0.9 --block 16
```

预期现象：连续预留的浪费随长度方差增大而急剧上升；Paged 浪费只与 Block 尾部有关，Block 从 16 增到 128 时每请求尾部浪费明显增加；GQA（`--kv-heads 8`）相对 MHA（`--kv-heads 32`）把容量降到约 1/4；KV 8-bit 再减半。Prefix 收益要用 Token Hit Rate 衡量：共享比例高但前缀很短时，节省的 Token 占比可能很低。

## 13. Level 1：追加写入与读取带宽实验

对比「每步 `torch.cat` 重建缓存」与「预分配槽位追加」的成本差异，并测量长上下文下的 KV 读取带宽。保存为 `kv_append_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import statistics
import time

import torch


def sync():
    torch.cuda.synchronize()


def bench(fn, warmup, iters):
    for _ in range(warmup):
        fn()
    sync()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        sync()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--layers", type=int, default=8)
    p.add_argument("--kv-heads", type=int, default=8)
    p.add_argument("--head-dim", type=int, default=128)
    p.add_argument("--context", type=int, default=2048)
    p.add_argument("--steps", type=int, default=128)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--iters", type=int, default=5)
    args = p.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU")

    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(device)
    print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
          f"torch={torch.__version__}")
    shape = (args.layers, 2, args.batch, args.kv_heads, args.head_dim)
    per_token_bytes = 2 * args.layers * args.kv_heads * args.head_dim * 2

    def cat_path():
        cache = torch.randn(*shape, args.context, device=device, dtype=torch.float16)
        for _ in range(args.steps):
            new = torch.randn(*shape, 1, device=device, dtype=torch.float16)
            cache = torch.cat([cache, new], dim=-2)   # 每步复制全部历史
        return cache

    def prealloc_path():
        cache = torch.empty(*shape, args.context + args.steps,
                            device=device, dtype=torch.float16)
        cache[..., :args.context, :].normal_()
        for t in range(args.steps):
            cache[..., args.context + t, :] = torch.randn(
                *shape, device=device, dtype=torch.float16)
        return cache[..., :args.context + args.steps, :]

    cat_ms = bench(cat_path, 1, args.iters)
    pre_ms = bench(prealloc_path, 1, args.iters)
    print(f"cat_append_ms={cat_ms:.3f} prealloc_append_ms={pre_ms:.3f} "
          f"speedup={cat_ms/pre_ms:.3f}x")

    # 读取带宽：模拟 Decode 每步扫描全部历史 KV
    kv = torch.randn(*shape, args.context, device=device, dtype=torch.float16)
    q = torch.randn(args.batch, args.kv_heads, 1, args.head_dim,
                    device=device, dtype=torch.float16)

    def read_all():
        k = kv[:, 0]                                  # [B, H, S, D]
        scores = torch.matmul(q, k.transpose(-1, -2))
        return scores.softmax(dim=-1)

    read_ms = bench(read_all, 3, args.iters)
    read_bytes = kv.numel() * kv.element_size()
    print(f"context={args.context} kv_read_mib={read_bytes/2**20:.2f} "
          f"read_ms={read_ms:.4f} effective_gib_s={read_bytes/2**30/(read_ms/1000):.1f}")
    print(f"kv_bytes_per_token={per_token_bytes} "
          f"total_kv_gib={per_token_bytes*args.context*args.batch/2**30:.3f}")
    print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")


if __name__ == "__main__":
    main()
```

运行与检查点：

```bash
python kv_append_lab.py --context 512 --steps 128
python kv_append_lab.py --context 4096 --steps 128
python kv_append_lab.py --context 4096 --steps 128 --kv-heads 32
nsys profile --trace=cuda,nvtx,osrt -o kv_append python kv_append_lab.py
```

`cat_append_ms` 随 `context` 增长而快速上升（每步复制 $O(S)$ 数据），`prealloc_append_ms` 基本只与 `steps` 相关；`effective_gib_s` 给出该上下文下 Attention 读 KV 的有效带宽，可与显卡 HBM 峰值带宽对比判断是否带宽受限；`kv-heads` 从 8 增到 32 时读取量与耗时近似线性增长，直观体现 GQA 的带宽收益。峰值 reserved 上升主要来自预分配缓存，属于预期。

## 14. Level 2：架构与部署边界

| 环境 | 可验证内容 | 边界 |
| --- | --- | --- |
| 纯 CPU | 容量模型、碎片率、Prefix Token Hit Rate | 任何带宽与 Kernel 结论 |
| 单张 RTX 3080/4090 | 追加写入 vs cat、KV 读取带宽、Block Size 权衡、8-bit KV 路径 | 大模型多 Pool、FP8 原生路径视架构而定 |
| 双卡 PCIe | 冷会话 Offload 到 Host、Pinned Memory 异步恢复 | 每 Token 往返 Host 的代价、NVLink-C2C/RDMA 等价性 |
| A100/H100 | 大 KV 容量、TP 下 KV 分片、解耦式 KV 传输 | 消费卡无法复现的互联带宽 |
| Blackwell | FP4/NVFP4 KV 与更新 Backend | 不能用 FP16 截断模拟低精度真实吞吐 |

容量公式、碎片模型、命中条件与生命周期管理是架构无关的；带宽阈值、低精度原生支持与 Offload 收益必须在目标硬件上实测。上线前至少完成三件事：用启动日志校正理论容量、用真实长度分布压出 Watermark 与抢占频率、用 Token Hit Rate 验证 Prefix Cache 的实际收益。

## 15. 量化补充：前缀保留与共享的收益账

第 6 节的驱逐成本公式可以代入具体数字。设前缀再用概率 $p_h$、重算时间 $T_r$、取回准备时间 $T_f$、维护时间 $T_m$，期望净节省

$$
V_h=p_h(T_r-T_f)-T_m,
$$

保留划算的条件是 $p_h>T_m/(T_r-T_f)$。6144 token 公共前缀 KV 占 864 MiB，RTX PRO 6000 上重算需要 96.5 TFLOP（按 batch 1 prefill 实测 BF16 峰值 62% 计约 307.9 ms），换出主机后经 PCIe Gen5 x16（64 GB/s）取回约 14.2 ms、维护取一次换出同值：阈值仅 **4.8%**，命中概率 50% 时平均省 132.7 ms；换 PCIe Gen4（32 GB/s）取回与维护各 28.3 ms，阈值升到 **10.1%**——换出释放了加速器空间，但只有前缀足够常用才抵消得了取回与维护。

值得保留不等于优先保留：同样 864 MiB 缓存，存一个 6144 token 大前缀省 132.7 ms，存三个 2048 token 小前缀（各重算 94.7 ms、取回维护各 4.7 ms、命中率同 50%）合计省 120.9 ms——重算时间随前缀长度超线性增长（6144 的 prefill 是 2048 的 3.25 倍），单位容量收益 A 约 0.154 ms/MiB 对 B 约 0.140 ms/MiB，按这个排序比较大小不同的前缀。另一个前提是前缀能保留到下次使用：12 轮 Agent 回放共 19556 输入 token，6 GiB 池命中 16304、只需重处理 3252，1 GiB 池零命中全量重算；把相邻两轮等待加 0.2 s 命中数不变——**增容量保留了可复用前缀，单纯延后请求没有同样效果**。

共享与分页省的是不同部分的内存。四分支实验：公共前缀 95 块、每分支私有 9 块，四张块表共 416 次引用而物理块只有 $95+4\times9=131$，比独立保存减约 69%；写时复制只复制共享尾块（已填 3 token 的块要分头追加时先取私有副本），已填满的只读块继续共享。整批容量：16 条长请求共享前 6144 token（864 MiB），每请求私有 $8192-6144+255=2303$ token 按 16 token/块需 324 MiB，合计 $864+16\times324=6048$ MiB，对照独立保存的 19008 MiB 放进 12 GiB 预留；一般地 $b$ 条占 $864+324b$ MiB，容量上限从 10 条独立请求升到 35 条共享。释放的两个条件也有实测时差：取消调用约 1.6 ms 返回，对应 104 个块直到约 31 ms 才释放——接口返回只表示停止调度，已提交的加速器操作完成后块才回空闲池，后续请求才不会覆盖旧请求在读的数据。内存不足时还可抢占重算：1 GiB KV 池发生一次抢占、比正常多调度 1805 token，2 GiB 池则没有——抢占把内存暂让给别人，代价是恢复时重复计算。

## 写在最后

KV Cache 把「重复计算」换成了「容量与带宽」，因此优化必须同时算两笔账：空间上靠 Paged 分配与共享 Prefix 降低浪费，时间上靠低精度、GQA 与高效 Attention Kernel 降低每步读取。下一篇转向计算侧，看 Speculative Decoding 如何用一次验证多个 Token 来突破 Decode 的串行瓶颈。

下一篇：[Speculative Decoding 与推理加速](/source/AI-Infra/2-AI系统性能工程/26-SpeculativeDecoding与推理加速)。