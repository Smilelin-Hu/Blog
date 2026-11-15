# Tensor Core 与低精度计算优化

本篇讲清 Tensor Core 与低精度计算的工作机制，帮你在速度、显存与数值稳定性之间取得平衡。

低精度是现代 AI 性能工程里最容易「看起来懂了、实际用错了」的领域。把 FP32 Tensor 转成 FP16 只是一种数据类型转换；只有算子、形状、布局、硬件和软件栈共同满足条件，计算才可能进入 Tensor Core 高吞吐路径。即使 Kernel 变快，数值溢出、额外量化、数据搬运或其他非矩阵算子也可能让端到端性能没有提升。

## 1. 内容概览

- Tensor Core 与普通 CUDA Core 的分工、MMA 的基本语义。
- 存储 dtype、输入计算 dtype、乘法精度、累加精度的区别。
- FP32 / TF32 / FP16 / BF16 / FP8（E4M3、E5M2）/ NVFP4 / INT8 与 INT4 的权衡。
- AMP、Loss Scaling、Amax 与缩放因子。
- 「转成低精度却没提速」的形状、布局、算子与端到端原因。
- Ampere / Ada / Hopper / Blackwell 的能力矩阵与回退路径。

## 2. 本篇要点

1. 解释 Tensor Core 与普通 CUDA Core 的分工，以及 MMA 的基本语义。
2. 区分存储 dtype、输入计算 dtype、乘法精度和累加精度。
3. 理解各低精度格式的精度与动态范围权衡。
4. 解释 AMP、Loss Scaling、Amax 与缩放因子的作用。
5. 识别「转换成低精度但没有提速」的端到端原因。
6. 同时验证速度、显存、误差、溢出和模型质量，不把峰值 FLOPS 当业务结论。

## 3. 核心直觉：Tensor Core 是「矩阵块流水线」

普通标量 FMA 是 $d = a \times b + c$；Tensor Core 面向矩阵块执行 MMA（Matrix Multiply-Accumulate）：$D = A \times B + C$。

它不是「一条指令完成任意大小矩阵」。大 GEMM 会被库或 Kernel 切成层级 Tile：

```text
完整 GEMM
└── Thread Block / Cluster Tile
    └── Warp / Warpgroup Tile
        └── Tensor Core MMA Tile
```

高吞吐来自以下条件同时满足：Tile 形状与硬件 MMA 形状匹配；A、B 按要求布局、对齐并及时搬到片上；有足够工作填满 SM；多级流水隐藏 Global/Shared Memory 延迟；累加器和缩放不成为额外瓶颈；输出精度满足模型要求。

所以「Tensor Core 更快」的完整表述应是：**在形状、布局、精度与数据供给都匹配时，矩阵块乘加能进入专用数据通路**。

## 4. Tensor Core 的系统原理

### 4.1 矩阵乘法为什么适合专用单元

对 $A \in \mathbb{R}^{M \times K}$、$B \in \mathbb{R}^{K \times N}$：

$$
C_{ij} = \sum_{k=1}^{K} A_{ik} B_{kj}, \qquad \mathrm{FLOPs} = 2MNK
$$

当 Tile 中的 A、B 被重复使用时，GEMM 具有较高算术强度。Tensor Core 把固定形状的小矩阵乘累加映射到专用数据通路，Warp 或 Warpgroup 负责提交分片、持有累加器并协调搬运。

### 4.2 Tensor Core 不负责所有算子

容易从 Tensor Core 获益：GEMM、BMM、Linear；卷积的部分实现；Attention 中的 QK 与 PV 矩阵乘；MoE Expert MLP 的 grouped GEMM；某些结构化稀疏矩阵乘。

不一定直接加速：Softmax、LayerNorm/RMSNorm；Sampling、Top-k、Tokenizer；很小的逐元素 Kernel；不规则 Gather/Scatter；CPU 调度、通信、I/O。

如果一次训练 Step 中 GEMM 只占 50%，即使 GEMM 理想加速 4 倍，Amdahl 上界也只有

$$
S = \frac{1}{(1-0.5) + 0.5/4} = 1.6
$$

### 4.3 输入、累加与输出可以是不同精度

低精度计算常见模式：

```text
低精度 A × 低精度 B → 较高精度 Accumulator → 指定输出 dtype
```

例如 FP16/BF16 输入可以使用 FP32 累加器，既提高乘法吞吐，又降低长点积累计误差。不要只看 Tensor 的存储 dtype；库实际选择的 MMA 指令和 accumulation mode 才决定计算路径。

## 5. 数值格式全景

| 格式 | 典型构成 | 直觉 | 常见用途 |
| --- | --- | --- | --- |
| FP32 | 1 sign + 8 exp + 23 frac | 范围和精度都较好 | 主权重、敏感归约、基准 |
| TF32 | 1 + 8 + 10（计算路径） | FP32 范围、接近 FP16 尾数精度 | Ampere+ 的 FP32 GEMM/Conv 加速 |
| BF16 | 1 + 8 + 7 | 范围接近 FP32，精度较粗 | 现代训练主力半精度 |
| FP16 | 1 + 5 + 10 | 精度较 BF16 高、范围较小 | 训练、推理、消费卡通用路径 |
| FP8 E4M3 | 1 + 4 + 3 | 精度较好、范围较小 | 前向/激活等场景 |
| FP8 E5M2 | 1 + 5 + 2 | 范围更大、精度更低 | 梯度等大范围场景 |
| NVFP4 | 4-bit 值 + 分层 scale | 极低存储与吞吐路径 | Blackwell 低精度训练/推理 |
| INT8/INT4 | 整数 + scale/zero point | 规则、便于量化 | 推理权重/激活量化 |

TF32 不是常规模型存储格式：PyTorch 中 Tensor 仍是 `float32`，cuBLAS/cuDNN 等后端可在受支持操作内部用 TF32 读取较少的有效尾数位并在更高精度中累加。

### 5.1 动态范围与精度是两条轴

浮点数可抽象为 $x = (-1)^s \times (1.m) \times 2^{e-bias}$：exponent 位决定主要动态范围，fraction 位决定相邻可表示数之间的精细程度。

BF16 保留 8 位 exponent，所以比 FP16 更不容易溢出，但只有 7 位 fraction，单次数值舍入更粗；FP16 有 10 位 fraction，但 exponent 只有 5 位，最大有限值 65504，更容易 overflow/underflow。

所以「BF16 精度低于 FP16」只描述尾数分辨率；在训练中，BF16 的大范围往往带来更稳定的整体行为。

### 5.2 FP8 不是 `.to(float8)` 就结束

FP8 的有限范围和较少有效位要求缩放：

$$
x_{fp8} = \mathrm{cast}_{fp8}(x \times s), \qquad \hat{x} = \mathrm{cast}_{high}(x_{fp8}) / s
$$

缩放策略需要决定：用历史 Amax 还是当前 Amax；每 Tensor、每通道还是每 Block 一个 scale；scale 多久更新；分布式训练时 Amax 是否跨 Rank 归约；前向、反向是否使用不同 FP8 格式。

NVIDIA Transformer Engine 的作用不是「所有层自动降到最低精度」，而是为受支持模块管理低精度配方、Amax、scale、量化缓存与高性能 Kernel。哪些操作进入 FP8/NVFP4，仍受 recipe、形状、框架版本与硬件支持约束。

### 5.3 NVFP4 不是普通 INT4

NVFP4 使用浮点值与分层缩放表达数据，与常见的对称 INT4 权重量化不同：表示集合不同、scale 结构不同、硬件 MMA 路径不同、校准与精度行为不同。文件里写着「4-bit」并不能证明能走 NVFP4 Tensor Core。

没有 Blackwell 与对应软件栈时，可以模拟 4-bit 量化误差，但不能声称验证了 NVFP4 吞吐。

## 6. 混合精度训练

### 6.1 Autocast：按算子选择 dtype

AMP 不是把整个模型无脑转半精度。Autocast 按算子策略选择：GEMM/Conv 等适合低精度的算子用 FP16/BF16；某些归约、损失和敏感算子保留 FP32；输出 dtype 按算子规则传播。

```python
with torch.autocast(device_type="cuda", dtype=torch.float16):
    output = model(inputs)
    loss = loss_fn(output, target)

# backward 不建议额外包在 autocast 中
scaler.scale(loss).backward()
scaler.step(optimizer)
scaler.update()
```

### 6.2 Loss Scaling：解决 FP16 梯度下溢

小梯度在 FP16 中可能舍入为 0。若把 Loss 乘以尺度 $S$：$L' = S \cdot L$，则反向梯度也被放大：$\nabla L' = S \cdot \nabla L$。优化器更新前再除以 $S$，数学上恢复原梯度。动态 GradScaler 在检测到 Inf/NaN 时跳过更新并减小 scale，稳定时逐渐增大。

### 6.3 Master Weight 与 Optimizer State

混合精度训练可能仍维护 FP32 主权重或 FP32 Optimizer State，因此 FP16/BF16 前向并不意味着训练显存严格减半：

$$
M_{train} \approx M_{model\ copy} + M_{master} + M_{grad} + M_{optimizer} + M_{activation} + M_{workspace}
$$

AMP 常显著减少激活和部分算子流量，但总节省取决于优化器与框架实现。

## 7. Tensor Core 性能模型

### 7.1 计算时间与转换时间

$$
T_{low} = T_{cast} + T_{scale} + T_{layout} + T_{mma} + T_{epilogue} + T_{sync}
$$

若输入原本是 FP32、而矩阵很小，`cast + scale` 可能比节省的 MMA 时间还大。更理想的系统让数据在多个算子间保持低精度，并融合 scale、bias、activation 等 Epilogue。

### 7.2 可达 Tensor Core 利用率

$$
\mathrm{MFU}_{tc} = \frac{2MNK / t}{P_{peak,dtype}}
$$

必须确保分母与实际 dtype、稀疏性口径一致：dense 与 2:4 sparse 峰值不能混用；boost clock 与持续功耗状态不能混用；FP8、NVFP4、FP16 峰值不能混用；单 GPU 与整机/整柜数字不能混用。

### 7.3 Shape Efficiency

假设实现需要把维度补齐到 Tile 倍数 $q$：

$$
M' = \lceil M/q \rceil q,\quad N' = \lceil N/q \rceil q,\quad K' = \lceil K/q \rceil q,\quad
\eta_{shape} = \frac{MNK}{M'N'K'}
$$

小而不规则的矩阵可能产生大量 padding 或尾块，使 Tensor Core 峰值难以转化为吞吐。实际库支持多种 Tile，$q=8/16$ 只是教学模型。

### 7.4 端到端加速上界

若低精度可加速部分占比 $p$、该部分加速 $s$：

$$
S_{end} = \frac{1}{(1-p) + p/s}
$$

再考虑精度失败重跑、通信、I/O 和 Batch 变化，实际 Goodput 可能更低。最终目标应是满足质量/SLO 的 tokens/s 或 samples/s，而不是单个 GEMM 的 TFLOPS。

## 8. 架构能力矩阵

| 架构 | 常见产品 | 典型 CC | 能力定位 |
| --- | --- | --- | --- |
| Ampere | A100、RTX 3080/3090 | 8.0 / 8.6 | TF32、BF16、FP16、INT8/INT4 Tensor Core；无 FP8 Tensor Core |
| Ada Lovelace | RTX 4090、L40/L40S | 8.9 | 第四代 Tensor Core，增加 FP8 输入能力 |
| Hopper | H100/H200 | 9.0 | FP8 Transformer Engine、第四代 Tensor Core、数据中心训练路径 |
| Blackwell 数据中心 | B100/B200/GB200 | 10.x | 第五代 Tensor Core、FP8/FP6/FP4，TE 支持 MXFP8/NVFP4 |
| Blackwell GeForce | RTX 5090 | 12.x | 消费级目标，支持格式集合不等于 B200 软件能力完全相同 |

注意：

- RTX 4090 是 Ada，不是 Blackwell。
- Ada 的 FP8 硬件输入能力不代表任意 PyTorch 运算都会自动使用 FP8。
- Hopper 的代表性 FP8 训练路径不等于支持 Blackwell NVFP4。
- RTX 5090 与 B200 都是 Blackwell，但应分别编译、检测并验证。
- Ampere 上安装 Transformer Engine 可以使用其 FP16/BF16 优化组件，但不能产生真实 FP8 Tensor Core 执行。

### 8.1 形状与布局要求

不同 cuBLASLt、CUTLASS、Transformer Engine 与框架版本对形状有不同约束。常见经验：GEMM 的 M/N/K 尽量是 8 或 16 的倍数；FP8 Transformer Engine Linear 常要求相关维度可被 16 整除；指针对齐与 Leading Dimension 会影响向量化 load；Batch 太小或 K 太小可能填不满 GPU；Grouped GEMM 需同时考虑每组大小与负载均衡。

这些是选型起点，不是「不是 16 倍数就绝对不用 Tensor Core」的定律——现代库可处理尾块，只是效率可能下降。

## 9. 瓶颈分析方法

### 9.1 确认实际执行路径

检查：输入、权重、输出和 accumulator dtype；GPU 名称与 Compute Capability；PyTorch、CUDA、cuBLAS/cuDNN/TE 版本；Matmul 由 cuBLAS/cuBLASLt、CUTLASS、Triton 还是自定义 Kernel 执行；Nsight Compute 中 Tensor Pipe 是否活跃；是否发生隐式 cast、layout transform 或 fallback。

### 9.2 同时测速度与误差

至少记录：Median/P50 与 P99 延迟；samples/s 或 tokens/s；有效 TFLOPS；峰值显存；相对误差、最大误差；Inf/NaN 比例；最终模型指标（Loss、PPL、Accuracy、Reward）。

### 9.3 区分五类失败

| 现象 | 常见原因 | 优先动作 |
| --- | --- | --- |
| dtype 已变但速度不变 | 算子太小、未走 Tensor Core | 放大 Shape，查 Kernel 与 Tensor Pipe |
| Kernel 快但 Step 不快 | 非 GEMM、通信、I/O 占比高 | 端到端时间线 + Amdahl |
| FP16 出现 NaN | 溢出、Loss Scale、敏感算子 | GradScaler、BF16、保留 FP32 |
| BF16 稳定但误差偏大 | 尾数更短、累计/归约敏感 | 高精度累加、局部 FP32 |
| FP8/FP4 没收益 | scale/layout 开销或 fallback | 融合量化、增大 GEMM、查 recipe |

### 9.4 建立精度门禁

优化不能只通过速度测试，建议建立分级门禁：

```text
单算子误差 → 小模型收敛 → 固定评测集 → 长时间稳定性 → 线上 SLO/质量
```

如果低精度让失败率增加，Goodput 可能下降，即使单次成功请求更快。

## 10. 完整可运行实验：格式、误差与 AMP

```python
"""Numerical behaviour of low-precision formats (pure Python + optional torch)."""

import math
import struct
import sys


def fp16_range():
    return 65504.0, 6.103515625e-05  # max finite, min normal


def bf16_round(x):
    # 用截断尾数模拟 bf16（1+8+7）：保留高 16 位
    packed = struct.pack(">f", float(x))
    return struct.unpack(">f", packed[:2] + b"\x00\x00")[0]


def quantize_fp8_sim(x, scale, bits=3, exp_bits=4):
    """粗略模拟 E4M3：指数限幅 + 尾数截断，用来说明缩放与截断的误差。"""
    y = x * scale
    if y == 0:
        return 0.0
    sign = -1.0 if y < 0 else 1.0
    y = abs(y)
    max_finite = 448.0  # E4M3 常见最大有限值
    y = min(y, max_finite)
    exponent = math.floor(math.log2(y))
    mant = y / (2 ** exponent) - 1.0
    step = 2.0 ** -bits
    mant = math.floor(mant / step) * step
    return sign * (1.0 + mant) * (2 ** exponent) / scale


def demo():
    values = [1e-8, 1e-5, 1e-3, 1.0, 1e3, 1e5]
    max_f16, min_norm_f16 = fp16_range()
    print(f"{'x':>10} {'fp16':>12} {'bf16':>12} {'fp8(s=1)':>12} {'fp8(s=1024)':>14}")
    for v in values:
        f16 = v if min_norm_f16 <= abs(v) <= max_f16 else (float("inf") if abs(v) > max_f16 else 0.0)
        print(f"{v:>10.0e} {f16:>12.4g} {bf16_round(v):>12.4g} "
              f"{quantize_fp8_sim(v, 1.0):>12.4g} {quantize_fp8_sim(v, 1024.0):>14.4g}")


def torch_demo():
    import torch
    print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
    if not torch.cuda.is_available():
        return
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    n = 4096
    a32 = torch.randn(n, n, device="cuda", dtype=torch.float32)
    ref = a32 @ a32
    for dt in (torch.float16, torch.bfloat16):
        a = a32.to(dt)
        out = (a @ a).float()
        err = (out - ref).abs()
        print(f"{str(dt):>16} max_err={err.max().item():.3e} "
              f"rel={((out - ref).norm() / ref.norm()).item():.3e}")

    s = torch.cuda.Event(True); e = torch.cuda.Event(True)
    for dt in (torch.float32, torch.bfloat16):
        a = a32.to(dt)
        for _ in range(5):
            a @ a
        torch.cuda.synchronize(); s.record()
        for _ in range(20):
            a @ a
        e.record(); torch.cuda.synchronize()
        ms = s.elapsed_time(e) / 20
        print(f"{str(dt):>16} {ms:.3f} ms  {2 * n**3 / (ms / 1000) / 1e12:.1f} TFLOPS")


if __name__ == "__main__":
    demo()
    if "--torch" in sys.argv:
        torch_demo()
```

Level 0 部分只用来建立「范围与精度是两条轴」的直觉；Level 1 在真实 GPU 上量化误差与 TFLOPS，才能判断这次低精度改造到底拿到了多少。

## 11. FP8 缩放策略与 Transformer Engine

<!-- TODO: 待填充 -->

## 写在最后

低精度的判断标准不是「换成 FP16 了吗」，而是「端到端 Goodput 是否在质量约束下变好」。下一篇进入集群互联：单卡再快，数据过不去也没用。

下一篇：[NVLink、NVSwitch 与 AI 集群互联](/source/AI-Infra/2-AI系统性能工程/08-NVLink与AI集群互联)。
