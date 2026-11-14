# 全栈架构与 DeepSeek 案例

GPU 是工厂里最贵的那台机器，但不是整座工厂。上游每 8 ms 才送来一个 batch，换一张算力翻倍的卡，端到端吞吐几乎不会翻倍；反过来，如果 H2D 拷贝与计算能并行，原本相加的两段时间会变成取最大值。

第二个直觉同样重要：**平均利用率不是因果证据**。50% 的 GPU 利用率可能来自数据不足、小 Kernel 碎片、CPU launch gap、跨 NUMA 访问、同步通信、显存换入换出，也可能只是采样窗口把「满载—空闲」的周期平均了。先建跨层时间线，再动参数。

## 1. 全栈分层地图

| 层 | 典型组件 | 性能职责 | 常见问题 |
|---|---|---|---|
| 产品与入口 | API Gateway、队列、限流 | 接收、排队、优先级、回压 | 排队爆炸、重试风暴、P99 抖动 |
| 应用与模型 | 训练循环、LLM Server、模型结构 | 定义工作负载与正确性 | 序列过长、batch 不合适、动态形状 |
| 调度与并行 | Continuous Batching、TP/PP/DP/EP | 合批、放置、切分、重叠 | 气泡、负载不均、队头阻塞 |
| 框架 | PyTorch、JAX | 张量语义、自动微分、分布式 | eager 开销、隐式同步、对象分配 |
| 编译器与 DSL | torch.compile、XLA、Triton | 图捕获、融合、代码生成 | graph break、重编译、错误特化 |
| 加速库 | cuBLAS、cuDNN、NCCL、FlashAttention | 高性能算子与集合通信 | 算法选择不佳、形状不友好 |
| Runtime 与驱动 | CUDA Runtime/Driver、streams | 内存、提交、同步、设备管理 | launch gap、上下文抖动 |
| OS 与容器 | Linux、cgroup、NUMA、Docker | 隔离与设备暴露 | CPU 限流、page fault、拓扑错配 |
| 集群控制 | Kubernetes、Device Plugin | 发现、调度、生命周期 | 驱动漂移、标签缺失、错误放置 |
| 硬件与网络 | CPU/DRAM/PCIe/GPU/HBM/NVLink/NIC | 执行计算与搬字节 | 带宽、延迟、容量、功耗限制 |

这不是严格调用栈：NCCL 会穿过 CUDA、驱动与网络；`torch.matmul` 可能被编译融合，也可能落到 cuBLAS；容器并不虚拟出一块 GPU，而是通过主机驱动使用它。分层的价值是**划清证据范围**，不是制造边界。

### 三个正交平面

- **数据平面**：张量、token、梯度、KV Cache、检查点真正移动与计算的路径，直接决定稳态吞吐与单请求关键路径；
- **控制平面**：资源声明、调度、版本、健康检查、扩缩容、故障恢复，决定能不能稳定拿到资源并维持 Goodput；
- **可观测平面**：metrics、trace、profile、日志，必须能把入口请求、CPU 线程、CUDA stream、collective 与具体 worker 关联起来。

常见误区是让控制平面介入每个细粒度操作：每个小请求都走一次远程决策，控制延迟就进了数据热路径。正确做法是控制面下发策略、数据面本地快速执行、用有界队列做回压。

## 2. 一条训练 step 的真实旅程

```text
对象存储/并行文件系统
      ↓ 读取、解码、shuffle
CPU DataLoader → pinned host memory
      ↓ H2D copy
GPU forward → loss → backward
      ↓ 梯度 bucket
NCCL collective（AllReduce / ReduceScatter / AllGather）
      ↓
optimizer update → checkpoint / metrics
```

性能好的系统不会机械串行：worker 预取下一批；pinned memory + 独立 stream 发起异步 H2D；反向产出梯度桶后立即通信；checkpoint 后台写；下一 step 与当前 step 的非关键工作重叠。

但「异步 API」不等于真正重叠，需要同时满足五条：

1. 两段工作之间没有未满足的数据依赖；
2. 硬件有可并行的执行资源与路径；
3. 使用了正确的 stream、event 与缓冲区生命周期；
4. 没有 `.item()`、日志、分配器或默认 stream 引入隐式同步；
5. 上下游速率匹配，缓冲足够但不过量。

控制平面方面：K8s 通过 device plugin 暴露 `nvidia.com/gpu`，GPU Operator 自动化驱动、Container Toolkit、device plugin、GFD 与 DCGM 的部署。它们保证「资源能被可靠发现与使用」，但不会自动给你最佳拓扑或最佳 batch size——**跨节点调度会改变数据平面**：同样的 AllReduce，可能走机内 NVLink，也可能绕 PCIe 与跨机网络。

## 3. 一次推理请求的路径

```text
Client
  ↓ Gateway / 认证 / 配额
  ↓ 准入控制 + 请求队列
  ↓ Tokenizer + Scheduler + Continuous Batching
  ↓ Model Worker
      ├─ Prefill：整段 prompt，偏计算
      └─ Decode：逐 token，频繁读权重与 KV Cache
  ↓ Detokenize / 流式返回
```

拆成 API server、调度器、GPU worker 后，有三个约束：

- **准入控制必须知道容量**：只看 QPS 不看输入/输出长度，队列会突然失稳；
- **调度器必须理解阶段差异**：Prefill 与 Decode 的计算、带宽、延迟目标完全不同；
- **KV Cache 既是容量问题也是带宽问题**：它决定最大并发，也参与每一步 Decode 的访存。

模型 worker 的 CUDA 时间降 20%，若排队占总延迟 70%，端到端收益依然有限；盲目加大 batch 会提高总 Tokens/s，却恶化 TTFT 与单用户 TPOT。因此要同时保留四类观测：请求级 trace（E2E/TTFT/ITL）、调度器指标（队列、抢占、batch 组成、KV 使用率）、worker 指标（CPU gap、Kernel、显存、通信）、业务结果（超时率、SLO 内 Goodput）。

## 4. 执行层的接力：一次 matmul 的六步

1. Python/框架创建张量操作，走 eager 或进入捕获的计算图；
2. 编译器做形状特化、融合与代码生成，未编译路径直接分派后端；
3. cuBLAS 按 dtype、形状、布局与硬件挑实现；
4. CUDA Runtime 管 stream、event、内存与 launch，并调用驱动；
5. 驱动把工作提交给 GPU，SM/Tensor Core 计算，缓存、HBM 与互联搬数据；
6. CPU 只在显式/隐式同步、数据依赖或资源不足时等待。

这解释了为什么「Kernel 已经很快」仍可能系统慢：Python 发不满、图在反复重编译、布局触发额外拷贝、进程被 cgroup 限流、PCIe 跨 NUMA、多卡通信走低带宽路径。

**容器不是性能魔法**：GPU 容器共享宿主内核与驱动，最常见兼容原则是「宿主驱动必须支持容器所需的 CUDA 用户态版本」。容器还会继承 CPU quota、cpuset、内存限制、`/dev/shm` 与 ulimit——GPU 训练容器只分到很少 CPU，DataLoader 就会饿死 GPU；`/dev/shm` 太小会让多进程加载报错。

## 5. DeepSeek 案例：把关键路径重画一遍

### 5.1 先把事实说准

| 项目 | 官方公开口径 |
|---|---|
| 总参数 | 671B |
| 每 token 激活参数 | 约 37B |
| 预训练数据 | 14.8T tokens |
| 训练集群 | 2,048 张 H800 |
| routed experts | 每层 256 个，token 选 8 个 |
| 共享专家 | 每层另有 shared expert 路径 |
| 主要结构 | MLA、DeepSeekMoE、MTP |
| 训练系统 | FP8 混合精度、DualPipe、跨节点 EP、通信-计算重叠 |
| 训练 GPU 时间 | 2.788M H800 GPU-hours |

三个容易被传错的地方：

1. **「37B 激活」**是每个 token 穿过的注意力 + 共享路径 + 被选专家的总量，不是「每个专家 37B」；
2. **557.6 万美元**是「2.788M GPU-hours × 2 美元/GPU-hour」的**最终训练运行**成本估算，不含数据获取清洗、失败实验、人力、机房与网络，也不是 R1 的全部成本；
3. **H800 的瓶颈在互联**：机内 NVLink 400 GB/s、跨节点 IB 50 GB/s，远低于本地计算与 HBM 供给——不能笼统说成「HBM 带宽低」。

### 5.2 五个动作

1. **少算**：MoE 让每 token 只激活少量专家；MTP 让一次前向承担更多训练信号；
2. **少存、少搬**：MLA 压缩推理时的 KV 表示；dispatch 用更低精度；
3. **算得更便宜**：细粒度缩放的 FP8 与定制 GEMM；
4. **把等待藏起来**：DualPipe、双 batch overlap、通信 Kernel 与计算并行；
5. **让最慢者不拖全局**：负载均衡、node-limited routing、冗余专家、运行时均衡。

这五个动作互相牵动：MoE 省了计算却增加 All-to-All；为了让专家 GEMM 够大，推理需要更大全局 batch，进一步推动跨节点 EP；EP 变大通信变重，于是需要 DeepEP 与重叠。**系统优化就是不断把瓶颈换成更可管理的瓶颈**。

### 5.3 从结构到基础设施的因果链

**MoE 的账**：

$$
\mathrm{FLOPs}_{dense} \propto 2 N_{token} d_{model} d_{ff},\qquad
\mathrm{FLOPs}_{moe} \propto 2 N_{token} K d_{model} d_e + \mathrm{FLOPs}_{router}
$$

总容量随专家数 \(E\) 增长，每 token 计算随 \(K\) 增长，只要 \(K \ll E\) 就能解耦「容量」与「激活计算」。代价是路由 → dispatch → grouped GEMM → combine 这条不规则路径，以及 All-to-All 与负载均衡。

**无辅助损失的负载均衡**：维护每个专家的动态偏置参与选择，按近期负载调整，而不直接改变专家输出：

$$
e^\ast = \mathrm{TopK}_e\left(s_e(x) + b_e\right),\qquad
b_e \leftarrow b_e + \eta(\bar{n} - n_e)
$$

真正要看的是最忙那个专家而不是平均值：

$$
\mathrm{Imbalance} = \frac{\max_e n_e}{\mathrm{mean}_e n_e}
$$

**node-limited routing**：限制一个 token 的目标专家最多散布到若干个节点，把更多流量留在高带宽域。这是典型的「机械同理心」——路由器不只知道哪个专家合适，还知道专家摆在哪。

**MLA 压缩的是 KV 表示**，不是删头。标准 MHA 的 KV Cache：

$$
M_{MHA/token} = L \times 2 \times H_{kv} \times D_h \times B
$$

MLA 存低秩潜变量 + RoPE 部分：

$$
M_{MLA/token} \approx L \times (D_{latent} + D_{rope}) \times B
$$

按 V3 公开配置（\(L=61\)、latent rank 512、RoPE 64、BF16）估算：

$$
61 \times (512 + 64) \times 2 = 70{,}272\ \text{bytes/token} \approx 70.272\ \text{KB/token}
$$

这个数字直接决定最大并发、长上下文容量与 Decode 的内存流量；代价是额外投影、专用 Kernel 与实现复杂度。

**FP8 不是「全都变 8 bit」**：activation 用 tile-wise scaling、weight 用 block-wise scaling，敏感路径保留高精度：

$$
q = \mathrm{clip}\left(\mathrm{round}\left(\frac{x}{s}\right), q_{min}, q_{max}\right),\qquad \hat{x} = s q
$$

缩放粒度越细，局部动态范围越匹配，但 scale 元数据、量化 Kernel 与布局转换开销越高。收益可能来自三处（Tensor Core 吞吐、HBM 流量、dispatch 网络字节），但形状小、量化开销大、Kernel 不支持时，理论倍数并不自动兑现。

**DualPipe** 让微批从流水线两端双向进入，并把 forward/backward 与通信重叠。串行代价与理想重叠的对比：

$$
T_{serial} = M(C + T),\qquad
T_{overlap} \approx C + T + (M-1)\max(C, T)
$$

真实实现还要处理 forward、backward-input、backward-weight、stage 放置、激活内存与依赖——官方仓库明确说明需要为模型实现专门的 `overlapped_forward_backward`，不是一个 Python 双线程就能搞定。

**为通信保留 SM**：定制跨节点 All-to-All Kernel 会占掉一部分 SM，让网络搬运与计算并行：

$$
T_{step} \approx \max\left(T_{compute}(SM_{compute}), T_{comm}(SM_{comm})\right) + T_{unhidden}
$$

给通信的 SM 太少，数据注入不及时；给太多，GEMM 变慢。最佳比例取决于消息量、EP 规模、NVLink/RDMA、GEMM 形状与 Kernel 实现，**不存在通用常数**。

**MTP** 把训练与推理连起来：训练时每个位置承载多个 token 的预测目标，推理时额外预测头充当候选、由主模型验证——推测解码因此有了「自带的 drafter」。

## 写在最后

全栈视角的价值在于把「慢」定位到某一层、某一平面、某一段时间上，再决定改哪里。下一篇下沉到硬件：GPU 微架构、显存体系、Tensor Core 与低精度，以及多卡互联与容器化运行环境——把「为什么慢」从系统语言翻译成硬件语言。
