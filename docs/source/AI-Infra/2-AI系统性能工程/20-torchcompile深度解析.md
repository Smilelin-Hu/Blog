# torch.compile 深度解析

本篇拆解 `torch.compile` 的图捕获、编译与回退机制，掌握适用场景、性能收益与常见 Graph Break。

`torch.compile` 不是一个「打开就必然加速」的开关，而是一套把 Python/PyTorch 程序捕获为计算图、跨算子优化并生成目标代码的编译系统。除了 API，更重要的是建立完整的性能工程判断链：编译器看到了多大的图、为什么发生 Graph Break、哪些 Guard 导致重编译、冷启动成本何时能摊平，以及如何证明收益来自 Kernel Fusion、调度或更低的 Runtime 开销。

## 1. 内容概览

- TorchDynamo、FX、AOTAutograd、TorchInductor、Triton/C++ 代码生成的分工。
- Graph Break、Guard Failure、Recompile 与编译失败的区别。
- 首次编译、预热后稳态、显存与数值误差的正确测量。
- `fullgraph`、`dynamic`、编译模式与局部禁用的使用边界。
- 用日志定位图断裂、Guard 与动态 Shape 问题。
- 编译投资的盈亏平衡点估算，以及线上缓存与回退策略。

三个工程问题贯穿全篇：这个工作负载适不适合编译；编译后为什么快、为什么没变快、或者为什么更慢；如何让动态输入、多卡训练与生产服务既获得收益又避免编译风暴。

## 2. 核心直觉：用一次编译换很多次更便宜的执行

PyTorch eager 模式逐个执行算子，灵活、容易调试，但 Python 调度、算子边界、临时 Tensor 与大量小 Kernel 会产生开销。编译器尝试把一段程序视为整体：

```text
Python/PyTorch 程序
        │
        ▼
TorchDynamo 捕获可编译区域
        │ FX Graph
        ▼
AOTAutograd 生成前向/反向图
        │
        ▼
TorchInductor 做融合、调度和代码生成
        │
        ├── GPU：常见为 Triton / CUDA 相关代码
        └── CPU：常见为 C++ / 向量化代码
```

这像把一条每天走很多次的土路修成高速公路。修路有成本，通车后每次更快；如果只走一次，修路反而亏。如果输入形状不断变化，编译器还可能不断「重修不同规格的路」。

因此适用特征通常是：同一模型或训练 Step 会重复运行很多次；图中有可融合的 Pointwise、归一化、归约等算子；Python 控制流与 I/O 没有频繁切断图；Shape 集合有限，或者动态维度能被合理泛化；冷启动可以预热、缓存或在部署阶段被吸收。

## 3. 编译栈的系统原理

### 3.1 TorchDynamo：从 Python 字节码捕获图

TorchDynamo 在 Python Frame 层观察字节码，把能安全表示的 PyTorch 运算捕获为 FX Graph。它不会盲目假设所有条件永远成立，而是为编译结果生成 Guard，例如：输入 Tensor 的 dtype、device、rank 或部分 Shape；某个 Python 常量或对象身份；Module 的训练/推理状态；全局变量、默认设备或 Autocast 状态。

下次调用时 Guard 成立就复用已编译结果；Guard 失败则可能重新捕获并编译新版本。

### 3.2 FX Graph：可变换的中间表示

FX Graph 把算子与数据依赖表示为节点与边。与逐行 Python 相比，它让后端看到更大的优化范围：删除冗余操作、安排内存生命周期、融合多个算子、选择实现。

### 3.3 AOTAutograd：提前生成前向和反向图

训练时 Autograd 原本边执行边记录。AOTAutograd 通过函数化等变换提前得到前向图与反向图，使编译器能跨越 Autograd 边界优化。它也必须处理 Mutation、Alias 与保存用于反向的中间值，所以训练图通常比纯推理更复杂。

### 3.4 TorchInductor：融合、调度与代码生成

TorchInductor 是默认编译后端，优化方向包括：将多个 Pointwise/Reduction 操作融合为更少的 Kernel；减少中间 Tensor 的显存写回与再次读取；降低 Python 与 Dispatcher 的调用次数；为目标设备选择布局、Tile 与并行策略；在 GPU 上生成或调用 Triton/外部高性能库，在 CPU 上生成向量化代码。

编译器不会把所有 GEMM 都重写。成熟库中的矩阵乘通常仍由 cuBLAS、cuBLASLt 等库执行；收益可能来自 GEMM 前后的 Epilogue 融合、布局与调度，而不是替代 GEMM 本身。

## 4. Graph Break、Guard 与 Recompile

### 4.1 Graph Break 不等同于报错

默认 `fullgraph=False` 时，无法捕获的代码会结束当前编译区域，回到 Python 执行，再从后续可捕获位置建立新区域。程序可能正确运行，但图被切碎后会失去跨区域融合机会，并增加调度开销。

常见原因：数据依赖的 Python 控制流（如 `if tensor.sum() > 0`）；`.item()` 把 Tensor 值拉回 Python；日志、文件、网络与第三方 C 扩展；编译器暂不支持的 Python 或算子语义；对对象、容器或全局状态的复杂 Mutation。

`fullgraph=True` 要求一次调用被捕获为完整图，遇到 Graph Break 就报错。它适合测试与定位，不代表生产环境必须全图编译。

### 4.2 Guard 是正确性契约

Guard 不是「多余检查」。编译器可能针对特定 Shape、常量与布局生成专门代码，只有假设仍成立时才能安全复用。优化目标不是删除 Guard，而是避免没有业务价值的输入变化与 Python 状态变化。

### 4.3 Recompile 是缓存未命中

一次 Recompile 不一定有问题：首次遇到新 dtype 或新 Shape，生成新版本很合理。问题是无界增长。若请求长度几乎每次都不同，又没启用合适的动态 Shape，可能产生编译风暴、缓存淘汰与尾延迟尖峰。

PyTorch 对单个 Frame 的重编译缓存有上限，达到上限后的行为与版本、配置有关，不能把内部默认值当作稳定业务接口。应通过日志观察，并在业务层控制 Shape Bucket。

### 4.4 动态 Shape 的选择

`dynamic=None` 是常用默认：先按静态信息编译，检测到 Shape 变化后尝试泛化。`dynamic=True` 尝试更早生成可处理变化尺寸的代码；`dynamic=False` 更偏向每组 Shape 特化。

动态并非总是更快。优点是少编译几个版本、降低冷启动与缓存压力；代价是部分静态优化、常量折叠或 Autotune 选择空间变弱；边界是不同 rank、dtype、分支或布局仍可能需要不同版本。

生产中更常用的折中是「有限 Bucket + Bucket 内动态」，例如把序列长度归入 128、256、512、1024 四档。

## 5. 关键性能模型

### 5.1 编译投资的盈亏平衡点

设 $T_c$ 为首次捕获、编译与 Autotune 的总成本，$T_e$ 为 eager 单次稳态时间，$T_s$ 为 compiled 单次稳态时间，$N$ 为部署期复用次数：

$$
T_{eager} = N T_e,\qquad T_{compiled} = T_c + N T_s
$$

当 $T_s < T_e$ 时，盈亏平衡调用次数为

$$
N^* = \frac{T_c}{T_e - T_s}
$$

若编译耗时 20 秒、每次从 10 ms 降到 6 ms，则约需 5000 次调用才能摊平。若模型实例只处理 200 次请求就被回收，即便稳态快 40%，总体仍可能亏损。

### 5.2 融合为什么降低时间

对两个连续的内存受限算子，eager 可能执行：

```text
读 x → 算 a → 写临时 t
读 t → 算 b → 写 y
```

融合后可能成为：

```text
读 x → 算 a → 算 b → 写 y
```

中间 Tensor 不再往返全局显存，近似字节量从 $4S$ 降到 $2S$，同时 Kernel Launch 数量由 2 降到 1。真实收益还受 Cache、寄存器压力、占用率与算子库实现影响。

### 5.3 Amdahl 定律约束总体加速

若可编译部分占原时间比例 $p$、该部分加速 $s$ 倍：

$$
S = \frac{1}{(1-p) + p/s}
$$

如果数据加载、通信与 Python I/O 占 60%，再优秀的 Kernel Fusion 也只能优化剩下的 40%。必须结合性能分析方法看端到端 Critical Path。

### 5.4 尾延迟模型

服务端 P99 可能由稳态执行、重编译、Autotune、显存回收与队列等待共同决定：

$$
L_{request} = L_{queue} + L_{compile\ miss} + L_{execute} + L_{sync}
$$

只报告预热后的平均延迟，会掩盖线上最危险的编译缓存未命中。

## 6. 编译范围与模式选择

### 6.1 在哪里编译

优先从「能覆盖主要计算、又能保持边界稳定」的最高层开始：

1. 推理：编译完整 `nn.Module` 的计算部分，I/O、Tokenizer 与后处理留在外面。
2. 训练：先编译模型前向；收益不足时再评估训练 Step 或 Compiled Autograd。
3. 重复 Block：整图编译冷启动过大时，编译共享结构的 Transformer Block，形成 Regional Compilation。
4. 分布式：通常在 DDP 包装前编译内层 Module；FSDP、TP 与编译的组合需按当前 PyTorch 官方示例验证。

现代 PyTorch 为 `nn.Module` 提供 `.compile()`，它会让 Module 的 `__call__` 走编译路径；`torch.compile(fn_or_module)` 仍适合函数或需要返回独立包装对象的场景。

### 6.2 常用模式

| 模式 | 主要目标 | 常见代价 | 适合场景 |
| --- | --- | --- | --- |
| `default` | 编译成本与稳态性能平衡 | 不保证最低延迟 | 首次基线 |
| `reduce-overhead` | 降低 Python/Launch 开销，可能使用 CUDA Graph 相关优化 | 可能增加显存；输入/控制流有限制 | 小 Batch、Launch-bound 推理 |
| `max-autotune` | 搜索更优 Kernel/配置 | 首次编译显著变慢 | 长生命周期、重复 Shape |

可用模式、内部实现与后端选项会随 PyTorch、设备与构建变化。先以 `default` 建立基线再逐项测量，不要把某个模式名等同于固定优化集合。

## 7. 瓶颈分析方法

### 7.1 四阶段诊断

1. **正确性**：相同权重与输入，对比 eager/compiled 输出或梯度。
2. **可编译性**：查看 Graph Break、Guard 与 Recompile 日志。
3. **收益来源**：比较 Kernel 数量、显存流量、CPU Launch 空洞与稳态时间。
4. **经济性**：把首次编译、缓存复用次数、实例生命周期与 P99 纳入总成本。

### 7.2 推荐日志

```bash
TORCH_LOGS="graph_breaks,recompiles,guards,dynamic" \
python torch_compile_lab.py --device auto --vary-shapes
```

日志量可能很大，先在最小复现中使用。若完整模型需要跨 Frame 分析，可按当前 PyTorch 文档使用 `TORCH_TRACE` 与 `tlparse`；这类工具接口变化较快，应锁定与 PyTorch 匹配的版本。

### 7.3 快速决策树

```text
结果错误？ ──是→ 缩小模型；检查随机数、Mutation、Alias、精度和自定义算子
   │否
   ▼
首次很慢但稳态快？ ──是→ 计算 N*；预热、缓存、Regional Compilation
   │否
   ▼
频繁 Recompile？ ──是→ 看 Guard；固定状态、Shape Bucket、评估 dynamic
   │否
   ▼
Graph Break 多？ ──是→ 去掉 .item()/I/O；局部重写或 disable 难编译区域
   │否
   ▼
Kernel 少但仍不快？ ──→ 查 GEMM 占比、数据/通信、寄存器压力和真实端到端瓶颈
```

## 8. Level 0：无 GPU 的编译收益规划实验

下面的纯 Python 程序不模拟编译器内部实现，而是训练上线前最关键的经济性判断。保存为 `compile_roi_planner.py`：

```python
#!/usr/bin/env python3
import argparse

def main():
    p = argparse.ArgumentParser(description="torch.compile ROI planner")
    p.add_argument("--compile-seconds", type=float, default=20.0)
    p.add_argument("--eager-ms", type=float, default=10.0)
    p.add_argument("--compiled-ms", type=float, default=6.0)
    p.add_argument("--calls", type=int, nargs="+", default=[100, 1000, 5000, 20000])
    p.add_argument("--variants", type=int, default=1,
                   help="实际会生成的编译版本数量")
    args = p.parse_args()

    if min(args.compile_seconds, args.eager_ms, args.compiled_ms) < 0:
        raise SystemExit("时间不能为负数")
    if args.variants < 1 or any(n < 1 for n in args.calls):
        raise SystemExit("variants 和 calls 必须为正整数")

    compile_ms = args.compile_seconds * 1000.0 * args.variants
    delta = args.eager_ms - args.compiled_ms
    if delta > 0:
        break_even = compile_ms / delta
        print(f"break_even_calls={break_even:.1f}")
    else:
        break_even = float("inf")
        print("break_even_calls=never (compiled steady-state is not faster)")

    print("calls eager_total_s compiled_total_s net_saved_s decision")
    for n in args.calls:
        eager_total = n * args.eager_ms
        compiled_total = compile_ms + n * args.compiled_ms
        saved = (eager_total - compiled_total) / 1000.0
        decision = "compile" if saved > 0 else "eager"
        print(f"{n:5d} {eager_total/1000:13.3f} "
              f"{compiled_total/1000:16.3f} {saved:11.3f} {decision}")

if __name__ == "__main__":
    main()
```

运行：

```bash
python3 compile_roi_planner.py
python3 compile_roi_planner.py --compile-seconds 20 --eager-ms 10 \
  --compiled-ms 6 --variants 4 --calls 1000 5000 20000 50000
```

预期现象：默认参数约在 5000 次调用达到盈亏平衡；当编译版本从 1 增至 4，编译投入变为四倍，盈亏平衡点也约变为四倍。这解释了为什么无界动态 Shape 会吞掉稳态收益。

## 9. Level 1：通用 PyTorch CPU/CUDA 实验

该实验自动检测 PyTorch、CUDA、GPU 名称、Compute Capability 与显存，不硬编码具体显卡，并分别报告首次 compiled 调用与预热后的稳态时间。保存为 `torch_compile_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import copy
import statistics
import time

import torch
from torch import nn

class Block(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.norm = nn.LayerNorm(width)
        self.fc1 = nn.Linear(width, width * 2)
        self.fc2 = nn.Linear(width * 2, width)

    def forward(self, x):
        residual = x
        x = self.norm(x)
        x = self.fc2(torch.nn.functional.gelu(self.fc1(x)))
        # 保留多个可融合的 pointwise 运算，便于观察编译收益
        x = torch.sigmoid(x) * x + 0.1 * torch.tanh(x)
        return residual + x

class Model(nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        self.blocks = nn.ModuleList([Block(width) for _ in range(depth)])

    def forward(self, x):
        for block in self.blocks:
            x = block(x)
        return x

def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)

def timed(model, x, warmup, steps, device):
    with torch.inference_mode():
        for _ in range(warmup):
            model(x)
        sync(device)
        samples = []
        for _ in range(steps):
            t0 = time.perf_counter()
            model(x)
            sync(device)
            samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), statistics.quantiles(samples, n=20)[18]

def parse_dynamic(value):
    return {"auto": None, "true": True, "false": False}[value]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--compile-mode", default="default",
                   choices=["default", "reduce-overhead", "max-autotune"])
    p.add_argument("--dynamic", default="auto", choices=["auto", "true", "false"])
    p.add_argument("--fullgraph", action="store_true")
    p.add_argument("--vary-shapes", action="store_true")
    args = p.parse_args()

    if not hasattr(torch, "compile"):
        raise SystemExit("当前 PyTorch 不提供 torch.compile，请升级到受支持的稳定版本")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("请求了 CUDA，但当前 PyTorch/驱动不可用")
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )

    torch.manual_seed(0)
    torch.set_float32_matmul_precision("high")
    eager = Model(args.width, args.depth).eval().to(device)
    compiled = copy.deepcopy(eager)

    print(f"torch={torch.__version__} device={device}")
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(device)
        print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
              f"vram_gib={prop.total_memory / 2**30:.2f} cuda={torch.version.cuda}")
        torch.cuda.reset_peak_memory_stats(device)

    x = torch.randn(args.batch, args.width, device=device)
    dynamic = parse_dynamic(args.dynamic)
    compiled.compile(mode=args.compile_mode,
                     fullgraph=args.fullgraph,
                     dynamic=dynamic)

    with torch.inference_mode():
        expected = eager(x)
        sync(device)
        t0 = time.perf_counter()
        actual = compiled(x)
        sync(device)
        first_compiled_ms = (time.perf_counter() - t0) * 1000.0
    torch.testing.assert_close(actual, expected, rtol=2e-3, atol=2e-3)

    eager_p50, eager_p95 = timed(eager, x, args.warmup, args.steps, device)
    comp_p50, comp_p95 = timed(compiled, x, args.warmup, args.steps, device)
    print(f"first_compiled_call_ms={first_compiled_ms:.3f}")
    print(f"eager_p50_ms={eager_p50:.3f} eager_p95_ms={eager_p95:.3f}")
    print(f"compiled_p50_ms={comp_p50:.3f} compiled_p95_ms={comp_p95:.3f}")
    print(f"steady_speedup={eager_p50 / comp_p50:.3f}x")

    if args.vary_shapes:
        print("vary_shapes_begin")
        with torch.inference_mode():
            for batch in [8, 16, 24, 32, 48, 64, 16, 32]:
                value = torch.randn(batch, args.width, device=device)
                t0 = time.perf_counter()
                compiled(value)
                sync(device)
                print(f"batch={batch:2d} call_ms={(time.perf_counter()-t0)*1000:.3f}")
        print("vary_shapes_end")

    if device.type == "cuda":
        print(f"peak_allocated_mib={torch.cuda.max_memory_allocated(device)/2**20:.1f}")
        print(f"peak_reserved_mib={torch.cuda.max_memory_reserved(device)/2**20:.1f}")

if __name__ == "__main__":
    main()
```

### 9.1 安装与运行

```bash
python3 -m venv .venv-compile
source .venv-compile/bin/activate
python -m pip install --upgrade pip
# 按 https://pytorch.org/get-started/locally/ 选择与本机匹配的稳定构建
```

CPU 基线与常见 NVIDIA GPU：

```bash
python torch_compile_lab.py --device cpu --width 512 --depth 3 \
  --warmup 5 --steps 20

nvidia-smi
python torch_compile_lab.py --device cuda --compile-mode default
python torch_compile_lab.py --device cuda --compile-mode reduce-overhead
python torch_compile_lab.py --device cuda --compile-mode max-autotune
```

动态 Shape 与重编译、Graph Break 严格检查：

```bash
TORCH_LOGS="recompiles,dynamic" python torch_compile_lab.py \
  --device auto --vary-shapes --dynamic false

TORCH_LOGS="recompiles,dynamic" python torch_compile_lab.py \
  --device auto --vary-shapes --dynamic true

TORCH_LOGS="graph_breaks" python torch_compile_lab.py \
  --device auto --fullgraph
```

### 9.2 预期现象

- 第一次 compiled 调用通常远慢于稳态，因为包含捕获、代码生成、编译，`max-autotune` 还可能做更多搜索。
- GPU 上的收益通常比小型 CPU 实验更明显，但不保证；矩阵乘占比很高且算子已高度优化时，提升可能有限。
- `reduce-overhead` 对小 Batch、许多短 Kernel 的场景更可能有利，也可能增加显存。
- `dynamic=false` 配合多种 Batch 可能看到更多 Recompile；`dynamic=true` 可能减少版本数，但稳态快慢需实测。
- 首次运行还可能受 CUDA Context、库加载与磁盘缓存影响；跨进程冷启动要单独重复测试。

### 9.3 结果分析模板

| 项目 | Eager | Compiled | 如何解释 |
| --- | --- | --- | --- |
| 首次调用 | 记录值 | 记录值 | 不混入稳态平均 |
| P50 稳态 | 记录值 | 记录值 | 计算 Speedup |
| P95 稳态 | 记录值 | 记录值 | 观察抖动 |
| Kernel 数量 | Profile | Profile | 判断是否融合 |
| 峰值 allocated | 记录值 | 记录值 | 检查显存副作用 |
| 编译版本数 | 日志 | 日志 | 识别编译风暴 |
| 最大误差 | 0 | 记录值 | 先过正确性门槛 |

不要把本机测量值写成「某张卡一定加速多少」或「所有 CPU 都会变慢」。结果依赖 Shape、dtype、PyTorch/Triton 版本、驱动、功耗、时钟与 Cache 状态。

## 10. Level 2：架构专项实验与边界

### 10.1 正确的硬件映射

| 架构 | 示例硬件 | 可观察重点 |
| --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | TF32/BF16、融合、通用 Inductor 基线 |
| Ada Lovelace | RTX 4090、L40/L40S | 更强 Tensor Core/推理基线；4090 不是 Blackwell |
| Hopper | H100/H200 | FP8/Transformer Engine 生态与数据中心部署 |
| Blackwell | RTX 5090、B100/B200/GB200 | 新低精度与更新编译后端支持 |

`torch.compile` 本身不要求 NVLink、NVSwitch、FP8 或 FP4。没有对应硬件时，CPU 或任意受支持 CUDA GPU 都可学习捕获、Guard、重编译与融合；但无法用软件模拟来证明 FP8/FP4 Tensor Core 的真实吞吐。

### 10.2 双 RTX 3080 可执行路径

每张 RTX 3080 分别运行单卡基准，再对比编译前后；多卡训练时先确保每个 rank 使用相同 Shape Bucket：

```bash
CUDA_VISIBLE_DEVICES=0 python torch_compile_lab.py --device cuda
CUDA_VISIBLE_DEVICES=1 python torch_compile_lab.py --device cuda
nvidia-smi topo -m
```

消费级 RTX 3080 多卡通常通过 PCIe 通信。`torch.compile` 优化本地计算图，不会自动消除 DDP All-Reduce；端到端收益需要同时检查计算—通信重叠。

### 10.3 查看生成代码和时间线

要证明收益来自融合而非偶然，需要看到 Inductor 实际生成的 Kernel：

```bash
TORCH_COMPILE_DEBUG=1 python torch_compile_lab.py --device cuda
TORCHINDUCTOR_CACHE_DIR=./inductor_cache python torch_compile_lab.py --device cuda
```

调试目录中通常包含 FX Graph 的文本形式、调度与融合决策日志，以及 `output_code.py` 中生成的 Triton/C++ Kernel。检查要点：

- 原本多个 Pointwise 算子是否合并进同一个 Kernel，中间 Tensor 是否被消除。
- GEMM 是否仍走 `extern_kernels.mm`（cuBLAS），Epilogue 是否被融合进相邻 Kernel。
- Kernel 的 `num_warps`、Tile 与 mask 处理是否合理，是否存在明显的冗余读写。
- 用 Profiler 对比编译前后的 Kernel 数量与 CPU Launch 空洞，再用 Nsight Systems 确认 GPU 时间线是否更紧凑。

生成代码与缓存目录属于实现细节，接口随版本变化；只作为诊断证据，不要在生产逻辑里依赖其路径或命名。

### 10.4 生产落地清单

- **预热与缓存**：部署阶段用代表性 Shape 完成预热，持久化 Inductor 缓存目录，避免每个实例重复付编译成本。
- **Shape Bucket**：业务侧把变长输入归入有限档位，档位内允许动态，档位间接受少量版本。
- **回退路径**：编译失败或数值异常时可退回 eager，保留开关与告警；不要在请求热路径里临时切换模式。
- **局部禁用**：对难编译区域使用 `torch._dynamo.disable` 或 `torch.compiler.disable` 隔离，保住其余部分的融合收益。
- **观测指标**：稳态 P50/P95、编译版本数、Recompile 次数、缓存命中率、峰值显存与最大数值误差，全部纳入回归。
- **生命周期核算**：按实例实际复用次数对照 $N^*$ 判断是否值得编译，短生命周期实例优先 eager 或 Regional Compilation。

## 11. 量化补充：多面体调度与形状特化的成本账

Inductor 之外，另一条编译路线把调度写成数学映射。华为开源的 AKG 面向昇腾 NPU，用多面体编译器自动安排循环顺序、分块、片上缓冲与搬移。以 $4096^3$ GEMM（BF16 输入、FP32 输出，137.4 GFLOPs）为例：朴素三重循环每个输出元素都从片外读操作数，输入读取量高达 256 GiB；取输出 tile $64\times64$、归约 tile 32 后降到约 4 GiB（64 倍），代价是每 tile 保留 16 KiB FP32 累加器。isl schedule 的本质是给每个语句实例 $S(i,j,k)$ 分配整数坐标再按字典序执行：

$$
S(i,j,k)\mapsto(\lfloor i/64\rfloor,\lfloor j/64\rfloor,\lfloor k/32\rfloor,i\bmod64,j\bmod64,k\bmod32).
$$

映射保持实例与数组下标不变，只改执行时间坐标；同一份 schedule 可直接写成片上搬移映射（A/B 各 4 KiB 进 L1，累加器 16 KiB 驻 L0，双缓冲则输入槽翻倍），编译器据此判断容量、插入搬移、安排复用点，再生成 MTE/Cube/Vector 与同步代码。TileLang-Ascend 是同一数据流的另一种表达：`T.copy/T.mma` 写分块数据流，`T.Pipelined` 与 `alloc_L1/L0A/L0B/L0C` 写调度与存储，DeepSeek TileKernels 于 2026 年 9 月加入昇腾后端，同一组 Python 接口可跑 NVIDIA GPU 与昇腾 NPU。AKG 靠 isl 自动产生调度，TileLang 让程序员直接写出更多调度决定——对照 42 篇第 2 节，这正是昇腾「硬件效率与软件适配共同承担」的编译侧。

候选实现的筛选按固定顺序：固定目标（形状、精度、误差、调用频数）→ 列候选（tile、循环序、缓冲数、融合范围）→ 查可行性（共享内存、寄存器、对齐、依赖，两类容量不能互借）→ 估时间（计算量、实际读写、启动与布局转换）→ 实测选择并保留相近候选。评价必须针对编译后的程序（源码分开的算子可能已被融合），且要按真实调用比例加权：某算子 A/B 两形状原实现均 10 μs，新实现 A 5 μs、B 20 μs，平均时间 $\overline T_{\mathrm{new}}=20-15p$ μs，**只有 A 的调用占比 $p>2/3$ 时新实现才更快**——各出现一次反而慢 25%，A 调用 100 次 B 一次则加速约 1.9 倍。

形状特化值不值，用准备成本 $P$ 与每组执行时间 $T$ 算盈亏平衡 $T_{\mathrm{total}}=P+rT$。10 次 FFN 一组（8 次 256 行＋1536＋2048，共 5632 行），512/2048 两桶补齐后执行 8192 行、多算 45%，但 MFU 从通用 20% 提到分桶 40%、特化 50%：

| 策略 | 一次性准备 P | 每组执行 T |
|---|---:|---:|
| 通用 | 100 ms | 17.0 ms |
| 分桶 | 400 ms | 12.4 ms |
| 逐形状特化 | 900 ms | 6.8 ms |

分桶比通用多 300 ms 准备、每组省 4.6 ms，约 65 组回本；特化再比分桶多 500 ms、每组再省 5.6 ms，约 90 组回本——1-64 组通用最省，65-89 组分桶，90 组起特化；程序已缓存则准备成本为零，特化从第一组起最快。这与第 10.4 节的 $N^*$ 生命周期核算是同一笔账。自动调优同理：搜索耗 10 分钟、每次省 5 μs，需 $1.2\times10^8$ 次调用才抵消（每秒 1 万次约 3.3 小时，每秒 100 次约 14 天）——**调优越久，越要优先优化高频、长期使用的形状**。

## 写在最后

`torch.compile` 的价值判断可以压缩成一句话：先看它捕获到多大的图，再看融合省掉多少显存流量与 Launch，最后用 $N^*$ 与 P99 确认这笔投资在真实生命周期里是否划算。下一篇进入 CUDA Graph 与 Runtime 优化，看当 Kernel 已经足够融合、瓶颈只剩提交开销时，如何把整段执行序列固化下来。

下一篇：[CUDA Graph 与 Runtime 优化](/source/AI-Infra/2-AI系统性能工程/21-CUDAGraph与Runtime优化)。