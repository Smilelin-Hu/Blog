# Compiler 与 Runtime：把逐张工单变成一张流程单

Eager 执行像「每道工序都单独开工单」：Python 调用一次、Dispatcher 分派一次、Kernel 启动一次。编译与 Runtime 优化做的是同一件事的两面——**编译减少工单数量，Runtime 降低提交工单的成本**。

## 1. 编译栈的四层

| 层 | 做什么 | 典型收益 |
|---|---|---|
| TorchDynamo | 在 Python Frame 层观察字节码，把可安全表示的运算捕获成 FX Graph | 把 Python 开销移出热路径 |
| FX Graph | 节点与边表示算子与依赖 | 让后端看到更大优化范围 |
| AOTAutograd | 提前函数化出前向图与反向图 | 跨越 Autograd 边界优化 |
| TorchInductor | 融合、调度、代码生成（GPU 生成 Triton/调外部库，CPU 生成向量化代码） | 少 Kernel、少中间读写 |

一个常见误区：以为编译器会「重写 GEMM」。成熟库里的矩阵乘通常仍由 cuBLAS/cuBLASLt 执行，收益多来自 GEMM 前后的 Epilogue 融合、布局与调度。

## 2. Graph Break、Guard 与 Recompile

**Graph Break 不等于报错**。`fullgraph=False` 时，捕获不了的代码会结束当前区域、回到 Python，再从后面重新开始。程序照跑，但图被切碎后失去跨区域融合与调度收益。

五个高频原因：

1. 数据依赖的 Python 控制流（`if tensor.sum() > 0`）；
2. `.item()` 把值拉回 Python；
3. 日志、文件、网络、第三方 C 扩展；
4. 编译器暂不支持的语义；
5. 对容器/全局状态的复杂 Mutation。

`fullgraph=True` 用于测试与定位，不代表生产必须全图。

**Guard 是正确性契约**，不是多余检查：编译器可能针对特定 Shape、常量与布局生成专门代码，只有假设成立才能安全复用。目标不是删 Guard，而是避免无业务价值的输入变化。

**Recompile 是缓存未命中**：首次遇到新 dtype/Shape 生成新版本很合理，问题是无界增长。请求长度每次都不同又没设 Bucket，就会出现编译风暴、缓存淘汰与尾延迟尖峰。

动态 Shape 的选择：

| 取值 | 行为 | 代价 |
|---|---|---|
| `dynamic=None` | 先静态编译，检测变化后再泛化 | 折中，常用默认 |
| `dynamic=True` | 尽早生成可处理变化尺寸的代码 | 部分静态优化与 Autotune 空间变弱 |
| `dynamic=False` | 按 Shape 特化 | 版本多、冷启动与缓存压力大 |

生产更常用「有限 Bucket + Bucket 内动态」：把序列长度归入 128/256/512/1024 四档。

## 3. 编译值不值：算盈亏平衡点

设编译总成本 \(T_c\)、eager 单次 \(T_e\)、compiled 单次 \(T_s\)、复用次数 \(N\)：

$$
T_{eager} = N T_e,\qquad T_{compiled} = T_c + N T_s,\qquad
N^\ast = \frac{T_c}{T_e - T_s}
$$

编译耗时 20 s、单次从 10 ms 降到 6 ms，需要约 5000 次调用才能摊平。**实例只处理 200 个请求就被回收的场景，稳态再快 40% 也是亏的。**

## 4. 融合为什么降时间

```text
eager：读 x → 算 a → 写临时 t → 读 t → 算 b → 写 y
融合： 读 x → 算 a → 算 b → 写 y
```

省掉的是中间 Tensor 的一次写与一次读，而不是多算了什么。这也是「融合收益 ≈ 访存收益」而非「算力收益」的原因。

## 5. Runtime：Launch 不是免费的

### 5.1 两条时间线与关键路径

$$
T_{host} = T_{python} + T_{framework} + \sum_{i=1}^{K} T_{launch,i} + T_{sync},\qquad
T_{gpu} = \sum_{i=1}^{K} T_{kernel,i} + T_{memory} + T_{dependency}
$$

$$
T_{step} \approx \max(T_{host\ submit},\ T_{gpu}) + T_{unhidden\ sync}
$$

当 \(T_{host\ submit} > T_{gpu}\)，GPU 在等 CPU——这就是 **Launch-bound**。它最典型的信号是：GPU 时间线上有规律的空洞、每个 Kernel 都很短、`nvidia-smi` 利用率长期偏低。

### 5.2 隐式同步是头号敌人

以下操作都可能让 CPU 等 GPU：`tensor.item()`、把 CUDA Tensor 打印成具体值、立刻拷回 pageable 内存、`torch.cuda.synchronize()`、某些内存分配与错误检查、读取尚未完成的 Event。

同步不是一律错误，错误在于**把同步放在高频热路径里，或者根本不知道它存在**。

### 5.3 优化顺序：从低风险到高约束

1. 删掉不必要的同步与 Python 标量往返；
2. `inference_mode`、批处理、预分配；
3. Kernel Fusion 减少 Launch 数与中间流量；
4. 异步 H2D + pinned memory + Stream，让搬运与计算重叠；
5. `torch.compile` 自动捕获与融合；
6. 对稳定热路径上 CUDA Graph；
7. 必要时 Persistent Kernel 或自定义 Runtime。

Graph 与 Fusion 解决的不是同一个问题：**Fusion 把多个算子变成更少的 Kernel，Graph 让仍然存在的多个 Kernel 以更低的 Host 开销被重放**。两者可以叠加。

## 6. CUDA Graph

### 6.1 对象模型与生命周期

- **Node**：Kernel、Memcpy、Memset、Event、Host Function、子图；
- **Edge**：依赖；
- `cudaGraph_t`：图定义；`cudaGraphExec_t`：验证并优化后的可执行实例。

```text
Warmup → Capture / 显式建图 → cudaGraph_t → Instantiate → cudaGraphExec_t → Replay × N → Destroy
```

`Instantiate` 会做拓扑验证、资源准备与调度优化，**不能把它算进稳态延迟**。

### 6.2 Capture 与 Replay 的成本模型

```cpp
cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal);
kernel_a<<<grid, block, 0, stream>>>(...);
kernel_b<<<grid, block, 0, stream>>>(...);
cudaStreamEndCapture(stream, &graph);
```

$$
T_{normal} = K \cdot T_{launch} + T_{gpu},\qquad
T_{graph} = T_{graph\ launch} + T_{gpu} + T_{input\ update}
$$

理论节省 \(\Delta T \approx K T_{launch} - T_{graph\ launch} - T_{input\ update}\)。这只是直觉模型：Driver 可能批量提交、Kernel 可并发、输入 Copy 也可能成为关键路径——最终仍要 Profile。

### 6.3 五个硬约束

1. **固定虚拟地址**：Replay 读写与 Capture 时相同的地址，业务输入要先 `copy_` 进 `static_input`；
2. **静态 Shape 与布局**：不同 batch/长度/dtype 通常要不同 Graph，生产用有限 Bucket（batch 1/2/4/8 × seq 128/256/512/1024），但 Bucket 太多会带来捕获成本与内存池压力；
3. **Capture 期间不能 CPU-GPU 同步**：`.item()` 会破坏捕获；Tokenizer、日志、IO、Python 分支都应放在 Graph 外；
4. **Warmup 必须先完成**：Context 初始化、cuBLAS 算法选择、JIT、Allocator 扩容、通信器初始化都要在 Capture 之前做完（PyTorch 建议在 side stream 上热身）；
5. **Graph 私有内存池**：为地址稳定而存在，多个 Graph 各持一池会显著增加显存，只有生命周期不重叠且语义安全时才共享。

## 7. Runtime 优化的判断依据

所有 Runtime 手段最终都在改三件事之一：**减少提交次数、缩短关键路径、隐藏等待**。

判断流程：

1. 先看 `T_host_submit` 与 `T_gpu` 谁大（决定是不是 Launch-bound）；
2. 若是，先删同步与标量往返（成本最低）；
3. 再考虑融合（减少 K）；
4. 再考虑 Graph（降低每次提交的代价）；
5. 最后才考虑 Persistent Kernel（复杂度最高）。

反之，若 GPU 时间线本来就满，Graph 基本没有收益——它不减少 GPU 工作量。

## 8. Profiler 体系的位置

- `torch.profiler`：算子级分布、`record_shapes`、`profile_memory`、`schedule` 采样、Chrome Trace / TensorBoard 导出；
- `torch.utils.benchmark`：带预热与同步的微基准；
- Nsight Systems：CPU/GPU/通信的端到端时间线，看重叠与空洞；
- Nsight Compute：单 Kernel 计数器（带宽、occupancy、Tensor Core 活动）；
- NVTX：给时间线加业务语义。

顺序永远是：**先系统时间线（nsys），再算子分布（profiler），最后单 Kernel 计数器（ncu）**。反过来做，容易把「一个不重要的 Kernel」优化到极致。

## 写在最后

编译与 Runtime 解决的是「提交与调度」的开销。下一篇进入推理系统：Prefill/Decode 的资源差异、Continuous Batching、KV Cache、投机解码、PD 分离与 MoE 推理——那里每一毫秒都要同时面对延迟与成本。
