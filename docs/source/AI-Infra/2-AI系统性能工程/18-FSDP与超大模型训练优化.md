# FSDP 与超大模型训练优化

本篇掌握 FSDP 的参数分片、通信与显存模型，构建可扩展的超大模型训练方案。

DDP 解决的是「同一个模型如何用更多 GPU 更快训练」，FSDP 解决的是「单卡根本放不下的模型如何训练」。它不只是把权重切开，而是把参数、梯度与优化器状态都切到不同 rank，并在计算某一层前临时拼回所需参数。因此 FSDP 不是一个开关，而是一套显存与通信调度系统，需要回答三个工程问题：为什么分片后仍会 OOM、为什么 FSDP 可能比 DDP 慢，以及如何为模型选择分片粒度、混合精度、激活重计算与 CPU Offload。

PyTorch 官方主线把基于 DTensor、逐参数分片的 `fully_shard` 称为 FSDP2，旧的 `FullyShardedDataParallel` 通常称为 FSDP1。新项目优先采用 FSDP2，同时需要理解 FSDP1 配置的对应关系。

## 1. 内容概览

- 从训练状态组成推导 DDP、ZeRO 与 FSDP 的单卡显存。
- All-Gather、Reduce-Scatter、Reshard 的生命周期。
- FSDP1 的 FlatParameter 与 FSDP2 的 DTensor 逐参数分片。
- Transformer Block 分片边界的选择。
- 混合精度、激活重计算、梯度累积与 CPU Offload 的组合。
- 用峰值显存、Step Time、tokens/s 与通信暴露时间评价优化。

## 2. 核心直觉：分片保存，按需借用

四张 GPU、四层模型时，DDP 的做法是每张卡都放完整四层，只给不同数据：

![每卡常驻状态：DDP 全复制 vs ZeRO-3 分片](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l18_02.png)

FSDP 的静止状态更像仓库分区：


计算某个 Block 前，各 rank 通过 All-Gather 临时取得这个 Block 的完整参数；完成计算后释放完整参数，只保留自己的分片。反向得到完整梯度后，再通过 Reduce-Scatter 完成求和并只留下本 rank 的梯度片。**参数是借来的，状态才是自己的。**

## 3. 训练显存花在哪里

设模型有 $P$ 个参数，每参数的常驻参数、梯度、优化器状态分别占 $b_p, b_g, b_o$ 字节，暂不计激活与临时缓冲：

$$
M_{state} = P(b_p + b_g + b_o)
$$

一个常见保守规划是 FP32 主参数 4 B、FP32 梯度 4 B、Adam 一阶与二阶状态共 8 B，即 $M_{state}\approx 16P$ 字节。这不是所有训练栈的固定常数：低精度参数、低精度梯度、额外 master weight、8-bit optimizer 都会改变它。工程上应把字节数做成输入，而不是背「每参数 16 字节」。

**DDP**：每个 rank 保留全部模型状态，$M_{DDP}\approx M_{state}+M_{act}+M_{temp}$，增加 GPU 数量不会降低单卡模型状态显存。

**ZeRO 与 FSDP**（数据并行规模 $N$）：

| 方案 | 参数 | 梯度 | 优化器状态 |
| --- | --- | --- | --- |
| DDP / ZeRO-0 | 复制 | 复制 | 复制 |
| ZeRO-1 | 复制 | 复制 | 分片 |
| ZeRO-2 | 复制 | 分片 | 分片 |
| ZeRO-3 / FULL_SHARD | 分片 | 分片 | 分片 |

完全分片的理想常驻状态为 $M_{sharded}\approx M_{state}/N$，但真实峰值还要加上临时与预取部分：

$$
M_{peak} \approx \frac{M_{state}}{N} + M_{active\ group} + M_{prefetch} + M_{act} + M_{comm} + M_{fragment}
$$

`active group` 是当前临时 All-Gather 出来的完整参数组，`prefetch` 是为隐藏通信而提前拉取的下一组参数。于是得到重要结论：**分片降低的是常驻状态，峰值仍由「最大完整参数组 + 激活 + 预取」决定**，这就是分片后仍会 OOM 的原因。

## 4. 一次 FSDP2 迭代发生了什么

以一个 Transformer Block 为一个分片组、`reshard_after_forward=True` 时：

![FSDP2 一次迭代：分片常驻、按需 AllGather](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l18_01.png)

### 4.1 为什么要两次 All-Gather

前向结束后立刻释放完整参数能获得最低峰值显存，但反向计算该层时必须重新 All-Gather。若不在前向后 Reshard，就能少一次参数 All-Gather，却要更久地保留完整参数。这是典型的空间—通信交换：

| 选择 | 峰值显存 | 参数通信 | 适合场景 |
| --- | --- | --- | --- |
| 前向后立即 Reshard | 低 | 较高 | 模型逼近显存上限 |
| 前向后保留完整参数 | 高 | 较低 | 模型较小、通信成为主瓶颈 |

### 4.2 通信量近似

Ring All-Gather 或 Reduce-Scatter 对总大小 $S$ 的张量，每 rank 传输量粗略为

$$
V_{AG} \approx V_{RS} \approx \frac{N-1}{N}S
$$

若每步对全部参数执行两次 All-Gather 与一次 Reduce-Scatter：

$$
V_{FSDP} \approx 3\frac{N-1}{N}P\,b_{comm}
$$

DDP 对梯度执行一次 Ring All-Reduce（可视为 Reduce-Scatter 加 All-Gather）：

$$
V_{DDP} \approx 2\frac{N-1}{N}P\,b_g
$$

这解释了为什么「模型明明能放进单卡」时 FSDP 未必比 DDP 快：FSDP 的首要价值是容量，吞吐需要靠合理分组、低精度通信与计算通信重叠争取。

### 4.3 暴露通信时间

设一个 Step 的计算时间 $T_c$、通信总时间 $T_m$、成功隐藏在计算后的部分 $T_h$：

$$
T_{step} = T_c + T_m - T_h + T_{other}
$$

优化目标不是让 $T_m$ 消失，而是让 $T_h$ 尽量接近 $T_m$。Nsight Systems 时间线上应看到下一层 All-Gather 与当前层计算重叠、当前层 Reduce-Scatter 与前一层反向计算重叠。


## 5. FSDP1 与 FSDP2

**FSDP1** 用 `FullyShardedDataParallel` 包装 Module，通常把一组参数展平为 FlatParameter 再切片，常见配置包括 `ShardingStrategy.FULL_SHARD`、`MixedPrecision`、`auto_wrap_policy`、`BackwardPrefetch`、`CPUOffload`、`limit_all_gathers`。它仍大量存在于生产代码中，阅读旧项目必须会，但新项目不应无理由继续绑定旧接口。

**FSDP2** 使用 `fully_shard(module)` 原地改变 Module，并把参数表示为沿第 0 维切分的 DTensor。它不再依赖 FlatParameter，参数全名保持稳定，更容易与其他 DTensor 并行方式组合。最重要的接口变化不是名字，而是「通信分组显式化」：

```python
# 正确方向：从叶子层到根模块，bottom-up
for block in model.blocks:
    fully_shard(block, mesh=mesh)
fully_shard(model, mesh=mesh)
```

每次 `fully_shard` 对应一个通信组。若只对根模型调用一次，所有参数可能形成一个巨大组：前向开始前做一次大 All-Gather、反向结束后做一次大 Reduce-Scatter，几乎没有层间重叠空间。

## 6. 分片粒度：最关键的性能旋钮

设每个分片组参数量 $G$、通信启动延迟 $\alpha$、有效带宽 $B$：

$$
T_{group} \approx \alpha + \frac{G}{B}
$$

组太小则 Collective 数量多、启动延迟与调度开销累积；组太大则峰值显存高、通信晚启动、难以与逐层计算重叠。Transformer 的第一选择通常是「一层 Block 一个组」，然后依据 Profile 调整：Block 很小时可把相邻 Block 合并；单个 Block 很大时可继续按 Attention / MLP 分组，但要防止 Collective 过碎；Embedding 与 LM Head 是否权重共享需要验证分片与 checkpoint 行为；只包根模块通常只适合教学或极小模型，不是高性能默认方案。

## 7. 超大模型的组合优化

### 7.1 混合精度

FSDP2 的 `MixedPrecisionPolicy` 可分别控制临时完整参数与梯度归约的 dtype。常见策略是：常驻分片参数与优化器状态保持 FP32；All-Gather 后的计算参数用 BF16；Reduce-Scatter 使用 BF16 以减小通信，或 FP32 以优先稳定性。Ampere、Ada、Hopper、Blackwell 都可运行 BF16 路径，但最终仍应通过 `torch.cuda.is_bf16_supported()` 检测。FP8/FP4 不是通用基线，也不能用消费级双卡做等价验证。

### 7.2 激活重计算

FSDP 主要减少模型状态，激活显存仍与 batch、序列长度、隐藏维度和层数相关；对长序列模型，激活可能重新成为第一瓶颈。Activation Checkpointing 只保存部分边界激活、反向时重跑前向：

$$
M_{act}\downarrow, \qquad FLOPs\uparrow
$$

判断它是否值得，不要只看峰值显存下降，还要看降低显存后能否增加 micro-batch、序列长度或减少梯度累积，从而提高最终 Goodput。

### 7.3 梯度累积

$$
B_{global} = B_{micro} \times N_{DP} \times K_{accum}
$$

前 $K-1$ 个 micro-batch 不应进行完整梯度同步，最后一个再同步，否则只是把通信重复了 $K$ 次。FSDP2 可通过梯度同步控制接口（如 `set_requires_gradient_sync`）实现；接口在不同 PyTorch 小版本可能变化，生产代码要对照所用版本文档。

### 7.4 CPU Offload

把参数分片、梯度与优化器状态移到主机内存能救 OOM，但 PCIe 传输与 CPU optimizer step 可能显著降低吞吐。使用前检查：每个进程的 CPU 内存总量是否足够；多进程锁页内存是否把主机内存耗尽；GPU 是否在等待 H2D/D2H；NUMA 绑定是否让 GPU 访问远端 CPU 内存。消费级双卡的优先顺序通常是 BF16 → FSDP2 → 激活重计算 → 调小 micro-batch → 最后才考虑 CPU Offload。

### 7.5 Hybrid Sharding

多节点时可在节点内做 FULL_SHARD、节点间复制同一份 shard，使高频 All-Gather/Reduce-Scatter 留在 NVLink/NVSwitch 或节点内 PCIe 域，跨节点只承担副本间归约。双卡单机不需要 Hybrid Sharding；它适合「节点内互联快、节点间网络相对慢」的集群，而不是 GPU 越多就一定启用。

### 7.6 分布式 Checkpoint

不要在每个 rank 上先聚合完整模型再 `torch.save`——大模型可能在保存时造成 GPU OOM、CPU OOM 或 rank 0 长时间停顿。FSDP2 的 sharded state dict 以 DTensor 表示，优先使用 PyTorch Distributed Checkpoint 保存分片状态，并在恢复时支持改变 world size 的重分片。Checkpoint 需要单独压测：记录保存时长、恢复时长、峰值 CPU 内存、存储带宽与训练暂停时间。能成功保存不等于能在故障窗口内恢复。

## 8. 瓶颈分析方法

### 8.1 先建立四组指标

| 维度 | 指标 | 典型问题 |
| --- | --- | --- |
| 容量 | peak allocated/reserved、OOM 点 | 分片组或激活过大 |
| 速度 | step time、tokens/s、samples/s | 通信或重计算过重 |
| 通信 | AG/RS 时长、暴露尾部、带宽 | 拓扑差、粒度不当 |
| 正确性 | loss、梯度范数、checkpoint 恢复 | dtype、累积或状态保存错误 |

### 8.2 诊断决策树

![FSDP 异常归因：OOM 按峰值阶段，非 OOM 按症状](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l18_03.png)

### 8.3 最小实验法

每次只改一个变量，并固定随机种子、模型、输入 shape、warmup 与测量步数：DDP 基线 → FSDP2（只改并行策略）→ FSDP2 + 按 Block 分组 → 再分别测试 BF16、Checkpoint、梯度累积、Offload。每次同时保存吞吐、峰值显存与 loss。

## 9. Level 0：无 GPU 显存规划器

不模拟真实 Collective，也不能替代 GPU 测量，用于在申请机器前排除明显不可能的配置。保存为 `fsdp_memory_planner.py`：

```python
#!/usr/bin/env python3
import argparse

GB = 1024 ** 3

def gib(x):
    return x / GB

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--params-b", type=float, default=7.0, help="参数量，单位十亿")
    p.add_argument("--world-size", type=int, default=2)
    p.add_argument("--param-bytes", type=float, default=4)
    p.add_argument("--grad-bytes", type=float, default=4)
    p.add_argument("--optim-bytes", type=float, default=8)
    p.add_argument("--comm-param-bytes", type=float, default=2)
    p.add_argument("--largest-group-mb", type=float, default=512)
    p.add_argument("--activation-gb", type=float, default=4)
    p.add_argument("--prefetch-groups", type=int, default=1)
    p.add_argument("--fragment-ratio", type=float, default=0.10)
    a = p.parse_args()
    if a.world_size < 1:
        raise SystemExit("world-size 必须 >= 1")

    params = a.params_b * 1e9
    state = params * (a.param_bytes + a.grad_bytes + a.optim_bytes)
    ddp = state + a.activation_gb * GB
    group = a.largest_group_mb * 1024 ** 2
    # 当前组 + 提前拉取组；真实框架还会有通信缓冲和 allocator 碎片
    fsdp_raw = (state / a.world_size
                + group * a.comm_param_bytes / a.param_bytes * (1 + a.prefetch_groups)
                + a.activation_gb * GB)
    fsdp = fsdp_raw * (1 + a.fragment_ratio)

    n = a.world_size
    ring = (n - 1) / n if n > 1 else 0
    ddp_comm = 2 * ring * params * a.grad_bytes
    fsdp_comm = 3 * ring * params * a.comm_param_bytes

    print(f"参数量: {a.params_b:.2f}B, world_size={n}")
    print(f"完整模型状态: {gib(state):.2f} GiB")
    print(f"DDP 单卡粗估: {gib(ddp):.2f} GiB")
    print(f"FSDP 单卡峰值粗估: {gib(fsdp):.2f} GiB")
    print(f"DDP 每 rank/step 通信粗估: {gib(ddp_comm):.2f} GiB")
    print(f"FSDP 每 rank/step 通信粗估: {gib(fsdp_comm):.2f} GiB")
    print("边界：不含 CUDA context、临时算子、真实预取生命周期和 checkpoint I/O。")

if __name__ == "__main__":
    main()
```

```bash
python3 fsdp_memory_planner.py --params-b 7 --world-size 2 \
  --largest-group-mb 512 --activation-gb 4
python3 fsdp_memory_planner.py --params-b 7 --world-size 8 \
  --largest-group-mb 256 --activation-gb 4
```

预期现象：world size 增大时模型状态分片部分近似按 $1/N$ 降低，但激活与完整参数组不随 $N$ 同比例下降；FSDP 通信粗估可能高于 DDP。

## 10. Level 1：双卡 DDP 与 FSDP2 对照

环境准备（GPU 用户优先从 PyTorch 官方安装选择器取得与驱动兼容的命令）：

```bash
python -m pip install "torch>=2.8,<2.14"
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.device_count())"
nvidia-smi topo -m
```

保存为 `fsdp2_benchmark.py`：

```python
#!/usr/bin/env python3
import argparse, contextlib, os, time
import torch
import torch.distributed as dist
import torch.nn as nn
from torch.distributed.device_mesh import init_device_mesh
from torch.nn.parallel import DistributedDataParallel as DDP

class Block(nn.Module):
    def __init__(self, hidden, expansion=4):
        super().__init__()
        self.norm = nn.LayerNorm(hidden)
        self.fc1 = nn.Linear(hidden, hidden * expansion, bias=False)
        self.fc2 = nn.Linear(hidden * expansion, hidden, bias=False)

    def forward(self, x):
        h = self.norm(x)
        h = torch.nn.functional.gelu(self.fc1(h), approximate="tanh")
        return x + self.fc2(h)

class TinyTransformer(nn.Module):
    def __init__(self, hidden, layers):
        super().__init__()
        self.blocks = nn.ModuleList([Block(hidden) for _ in range(layers)])
        self.norm = nn.LayerNorm(hidden)

    def forward(self, x):
        for block in self.blocks:
            x = block(x)
        return self.norm(x)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["ddp", "fsdp2"], required=True)
    p.add_argument("--hidden", type=int, default=1024)
    p.add_argument("--layers", type=int, default=8)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--seq", type=int, default=256)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--accum", type=int, default=1)
    p.add_argument("--lr", type=float, default=1e-3)
    return p.parse_args()

def main():
    args = parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("Level 1 需要 NVIDIA GPU；无 GPU 请运行 Level 0。")
    dist.init_process_group("nccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    device = torch.device("cuda", local_rank)
    torch.manual_seed(2026); torch.cuda.manual_seed_all(2026)
    if world < 2:
        raise SystemExit("请用 torchrun 启动至少 2 个进程。")

    model = TinyTransformer(args.hidden, args.layers).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    if args.mode == "ddp":
        model = DDP(model, device_ids=[local_rank])
    else:
        try:
            from torch.distributed.fsdp import fully_shard, MixedPrecisionPolicy
        except ImportError as exc:
            raise SystemExit("当前 PyTorch 没有 FSDP2，请安装受支持版本。") from exc
        mesh = init_device_mesh("cuda", (world,))
        mp = MixedPrecisionPolicy(param_dtype=compute_dtype, reduce_dtype=compute_dtype)
        # 关键：Block 先分片，根模型最后分片
        for block in model.blocks:
            fully_shard(block, mesh=mesh, mp_policy=mp, reshard_after_forward=True)
        fully_shard(model, mesh=mesh, mp_policy=mp)

    # 必须在 FSDP2 处理参数后创建 optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def one_step():
        optimizer.zero_grad(set_to_none=True)
        loss_value = 0.0
        for micro in range(args.accum):
            sync = micro == args.accum - 1
            if args.mode == "fsdp2":
                model.set_requires_gradient_sync(sync)
                sync_ctx = contextlib.nullcontext()
            else:
                sync_ctx = contextlib.nullcontext() if sync else model.no_sync()
            x = torch.randn(args.batch, args.seq, args.hidden, device=device, dtype=compute_dtype)
            target = torch.zeros_like(x)
            with sync_ctx:
                out = model(x)
                loss = (out.float() - target.float()).square().mean() / args.accum
                loss.backward()
            loss_value += loss.detach().float().item()
        optimizer.step()
        return loss_value

    for _ in range(args.warmup):
        one_step()
    dist.barrier(); torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    start, last_loss = time.perf_counter(), 0.0
    for _ in range(args.steps):
        last_loss = one_step()
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start

    stat = torch.tensor([elapsed,
                         torch.cuda.max_memory_allocated() / 1024**3,
                         torch.cuda.max_memory_reserved() / 1024**3], device=device)
    dist.all_reduce(stat, op=dist.ReduceOp.MAX)
    if rank == 0:
        tokens = args.batch * world * args.accum * args.steps * args.seq
        print({"mode": args.mode, "world_size": world,
               "params_m": round(total_params / 1e6, 2), "dtype": str(compute_dtype),
               "step_ms_max_rank": round(stat[0].item() * 1000 / args.steps, 3),
               "tokens_per_s": round(tokens / stat[0].item(), 1),
               "peak_alloc_gib_max_rank": round(stat[1].item(), 3),
               "peak_reserved_gib_max_rank": round(stat[2].item(), 3),
               "last_loss": round(last_loss, 6)})
    dist.destroy_process_group()

if __name__ == "__main__":
    main()
```

先用小模型确认正确性，再放大规模做对照：

```bash
torchrun --standalone --nproc-per-node=2 fsdp2_benchmark.py \
  --mode ddp --hidden 512 --layers 4 --batch 2 --seq 128 --steps 10
torchrun --standalone --nproc-per-node=2 fsdp2_benchmark.py \
  --mode fsdp2 --hidden 512 --layers 4 --batch 2 --seq 128 --steps 10
# 放大到接近显存上限，观察峰值与吞吐的变化
torchrun --standalone --nproc-per-node=2 fsdp2_benchmark.py \
  --mode fsdp2 --hidden 2048 --layers 16 --batch 2 --seq 512 --steps 20
```

判读要点：两种模式的 loss 轨迹应可比（同种子、同全局 Batch、同 dtype 策略）；`step_ms_max_rank` 取最慢 rank，才是同步训练的真实步耗时；FSDP2 的 `peak_alloc` 应显著低于 DDP，而 `tokens_per_s` 未必更高——若更低，先看 AG/RS 暴露时间与分片粒度，再决定是否值得为容量付出吞吐代价。`--accum` 大于 1 时对照 Collective 数量，确认非最后微步没有触发完整同步。

## 写在最后

FSDP 的本质是「用通信换容量」：常驻状态按 $1/N$ 下降，峰值却由最大完整参数组、激活与预取共同决定。分片粒度、Reshard 策略与混合精度是三个最值得扫描的旋钮。下一篇转向 PyTorch 侧的性能分析体系，把这些判断落到可复现的证据上。

下一篇：[PyTorch 性能分析体系](/source/AI-Infra/2-AI系统性能工程/19-PyTorch性能分析体系)。