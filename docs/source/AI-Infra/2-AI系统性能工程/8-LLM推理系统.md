# LLM 推理系统：调度、KV Cache 与架构解耦

训练优化的是「多久训完」，推理优化的是「每 token 多少钱、每个用户等多久」。这两个目标经常互相拉扯：同一套 GPU、同一个模型，并发越高系统吞吐越大，但每用户越慢。

## 1. 推理的两个阶段，两种资源画像

```text
Client → Gateway → 准入控制/队列 → Tokenizer/Scheduler → Worker
                                                          ├─ Prefill：整段 prompt，偏计算
                                                          └─ Decode：逐 token，偏访存
```

| 阶段 | 计算特征 | 主要瓶颈 | 优化目标 |
|---|---|---|---|
| Prefill | 大矩阵乘、可批处理 | 算力、TTFT | 输入 tokens/s、TTFT |
| Decode | 每步只处理少量 token，要读全部权重与 KV | 显存带宽、KV 容量 | TPOT、输出 tokens/s |

它们是两种不同的流水线，却被长期塞进同一组 GPU——这就是后面 PD 分离要解决的问题。

## 2. Continuous Batching 与调度

静态批的问题是「等最慢的那个」：一个 batch 里只要有一条长输出，其余请求都得陪跑。**连续批处理**改为按迭代重组：每一步都可以有新请求进来、完成的请求退出。

调度器要同时权衡四件事：

- **TTFT**：新请求多久能看到第一个 token；
- **TPOT**：已开始生成的请求是否流畅；
- **公平性**：不能让长请求饿死短请求，也不能反过来；
- **效率**：批次越大，单位 token 成本越低。

常见手段：**chunked prefill**（把长 Prompt 切块，与 Decode 混批，避免一次长 Prefill 把 TPOT 拉爆）、**抢占**（KV 不够时把某些请求换出/重算）、**优先级**（交互流量优先于离线批处理）。所有选择最终都要落到一条：**在 SLO 约束下最大化 Goodput**。

## 3. KV Cache：容量、碎片与生命周期

### 3.1 容量模型

$$
M_{token} = 2 \cdot L \cdot H_{kv} \cdot D_{head} \cdot B_{elem}
$$

（2 表示 K 与 V。）长度为 \(S\) 的请求 \(M_{req} = S \cdot M_{token}\)，系统总量取决于**所有在途 token 之和**，而不是并发数：

$$
M_{active} = M_{token}\cdot\sum_{i=1}^{N} S_i
$$

例：32 层、8 个 KV Head、Head Dim 128、FP16：

$$
M_{token} = 2\times32\times8\times128\times2 = 131{,}072\ \text{B} = 128\ \text{KiB}
$$

一个 4096 token 的请求约 512 MiB；32 个同长度请求约 16 GiB——还不含权重、激活、workspace、Graph 与通信缓冲。

### 3.2 MHA / GQA / MQA

| 结构 | KV Head 数 | KV 容量 | Decode 读取 |
|---|---|---|---|
| MHA | 通常等于 Query Head | 最大 | 最大 |
| GQA | 多个 Query Head 共享一组 KV | 较小 | 较小 |
| MQA | 全部共享一个 KV Head | 最小 | 最小 |

要注意：GQA/MQA 是**模型结构**，不是部署时随手可切的开关；换结构需要训练或专门的权重变换与质量验证。

TP 下 KV 通常按 Head 分散，每 Rank 近似降到 \(1/TP\)，但取决于 Head 整除、是否复制 KV、Attention Backend——不能拿「总量/卡数」当答案。

### 3.3 为什么连续预留会浪费

朴素实现按 `max_seq_len` 预留连续空间：

$$
Waste_{contiguous} = 1 - \frac{\sum_i S_i}{N \cdot S_{max}}
$$

输出长度未知，按最大预留必然浪费；按当前长度频繁扩容又要复制大 Tensor、产生外部碎片。

### 3.4 Paged KV 与 PagedAttention

把物理缓存切成固定 Token 数的 Block，请求维护「逻辑 Block → 物理 Block」的映射，逻辑连续不要求物理连续：

$$
Allocated_i = \left\lceil \frac{S_i}{P} \right\rceil P,\qquad
Waste_{paged} = 1 - \frac{\sum_i S_i}{\sum_i Allocated_i}
$$

每个请求最多浪费 \(P-1\) 个尾部 Token。Block 小则尾部浪费少、但元数据与调度开销大；Block 大则相反。

**PagedAttention 的贡献是让 Kernel 按 Block Table 访问非连续 KV**——只做分页分配器而 Kernel 仍要求连续，等于白做。

收益：按需增长、快速回收、支持连续批、可共享只读 Prefix、便于抢占/offload/跨设备传输。但它不是零浪费：尾 Block、元数据、对齐、多池与水位都还在。

### 3.5 生命周期五段

1. **分配**：Scheduler 在执行前按本轮新 token 预留 Block，失败就等待/拒绝/抢占，而不是让 Kernel 跑到 OOM；
2. **写入**：Prefill 批量写、Decode 每步追加；热路径写预分配槽位，别每步 `torch.cat` 复制历史；
3. **引用计数**：共享 Prefix Block 被多个请求引用，计数归零才可驱逐；改写共享块要走 Copy-on-Write；
4. **释放**：完成/失败/取消都要释放；**客户端断连必须把取消传到 Scheduler 与 KV Manager**，否则就是 KV 泄漏 + 无效 Decode；
5. **驱逐**：LRU、Priority+LRU、Prefix-depth-aware、Cost-aware 各有取舍，驱逐的真实成本是

$$
Cost_{evict} = P_{reuse}\cdot\left(T_{reload} + T_{recompute} + T_{queue\ risk}\right)
$$

## 4. 投机解码：用便宜的计算换昂贵的串行

Decode 慢在「一次只能出一个 token」的串行性。投机解码让一个小而快的 drafter 连续猜 \(k\) 个 token，再由主模型**并行验证**：前缀被接受就一次前进多个 token，第一个不匹配处截断。

决定收益的三个变量：

- **接受率 \(\alpha\)**：猜中比例，直接决定「一次能推进几个 token」；
- **drafter 成本比 \(c\)**：小模型的单步代价相对主模型的比例；
- **并行验证的开销**：验证 \(k\) 个候选通常接近一次前向的量级。

$$
\text{期望加速} \approx \frac{1 + k\alpha}{1 + k c}
$$

它清楚说明了边界：\(\alpha\) 低或 \(c\) 高时，投机解码可能**比不做还慢**。工程上要盯三件事：接受率分布（按任务类型差异巨大）、drafter 与主模型的分布对齐（否则长尾任务掉点）、以及验证阶段的批处理效率。

## 5. PD 分离：让两种流水线各做擅长的事

### 5.1 共置的干扰

```text
Request → [同一组 GPU]  Prefill + Decode + Prefill + Decode ...
```

没有跨实例 KV 传输、部署简单；但一条长 Prompt 进批，会拉长其他请求的下一 token 等待。为了保 TPOT 只能限制 Prefill 或切块，反过来又伤 TTFT 与 Prefill 吞吐。

### 5.2 解耦后的分工

```text
                     控制面：注册、路由、负载、租约、故障恢复
                              │
Client → Gateway/Router → Prefill Pool ──KV Data Plane──▶ Decode Pool → Stream
```

- **P Pool**：大批、强计算、高 TP，优化 TTFT 与输入 tokens/s；
- **D Pool**：连续批处理、大 KV 容量、高带宽，优化 TPOT 与输出 tokens/s；
- **Router**：同时看 P 队列、D 的可用 KV Block、前缀命中、拓扑与 SLO；
- **Planner**：独立调整 P/D 数量，甚至可以异构硬件。

解耦不是「所有请求都走远程 Prefill」：短 Prompt、低负载或链路拥塞时，**D 节点本地 Prefill 可能更快**——这叫 conditional disaggregation / mixed pool。

### 5.3 八步生命周期

1. Gateway 解析请求、采样参数、模型/Adapter、上下文长度与 SLO；
2. Router 选 P Worker，并预选/预约 D Worker；
3. P 完成 Prefill，产生首 token logits 与分层 KV Block；
4. 发布 KV 元数据（请求 ID、block ID、shape、dtype、位置、目标地址）；
5. 数据面把 KV 从 P 的 HBM 传到 D 的 HBM，或写入共享 KV Store；
6. D 确认 KV 完整可见，接管并开始连续 Decode；
7. 流式 token 经 Gateway 返回；
8. 结束/取消/超时后，两侧释放 KV、租约与元数据。

### 5.4 控制面与数据面必须分离

控制面传「小而关键」的元数据；数据面传数百 MB 甚至数 GB 的 KV。若用 Python HTTP 服务转发 KV，会出现 HBM→CPU→序列化→内核网络栈→CPU→HBM 的多次复制。

生产路径通常是 NCCL P2P、UCX、RDMA、GPUDirect RDMA、NIXL 或 Moonbeam/Mooncake 一类传输引擎。注意定位差异：**NIXL 是面向推理的点对点数据移动抽象（可覆盖 GPU/CPU 内存与存储），NCCL 擅长 GPU 集体通信**，两者不是替代关系。

### 5.5 KV 不只是一个 Tensor

D 要正确续跑，至少要拿到并校验：每层 K/V 与有效 token 数；block/page 布局、dtype、head 数与 head dim；RoPE 位置、position ids、滑动窗口状态；tokenizer、权重版本、量化格式、Adapter 标识；采样参数与随机数状态；TP rank 与 KV shard 映射。

P 与 D 的 TP 度不同时，KV 分片还要重排/重分片；异构硬件带来成本优势，也带来 dtype、Kernel、拓扑与容量规划的复杂度。

### 5.6 三种搬运模式

| 模式 | 机制 | 优点 | 风险 |
|---|---|---|---|
| Push | P 主动推到已选 D | 延迟直接、易做流水 | 必须提前选 D，背压复杂 |
| Pull | D 拿到元数据后拉取 | D 可按容量决定时机 | Prefill 完成后可能多等一次协调 |
| Shared Store | P 写分布式 KV 池，D 按 key 读 | 易复用、迁移与多级缓存 | 元数据、一致性、存储与网络更复杂 |

长上下文、多轮对话、前缀复用更适合 KV-centric 架构；单轮短请求未必摊得薄额外编排成本。

### 5.7 四个必算的公式

$$
B_{KV} = S \cdot B_{token}
$$

$$
T_{xfer} \approx T_{setup} + \frac{B_{KV}}{BW_{eff}} + T_{sync},\qquad
BW_{required} \ge \frac{B_{KV}}{T_{budget} - T_{setup} - T_{sync}}
$$

$$
TTFT_{disagg} = Q_P + T_P + T_{xfer} + Q_D + T_{first\_decode}
$$

$$
E2E = TTFT_{disagg} + N_{out}\cdot TPOT_D
$$

共置路径没有 \(T_{xfer}\)，但 \(Q\) 与 TPOT 会被混部干扰。**解耦的目标不是让每一项都变小，而是让更多请求同时满足 TTFT 与 TPOT 的 SLO**：

$$
\mathrm{Goodput} = \frac{\text{同时满足 TTFT、TPOT 与正确性 SLO 的请求数}}{\text{时间}}
$$

只看总 tokens/s 会掩盖尾延迟：P 快但 D 堵，照样大量迟到。

## 6. MoE 推理：把稀疏变成新的瓶颈

MoE 把「稠密计算」换成「稀疏计算 + 调度」：

- **专家分布**：\(N_E\) 个专家分到各卡；
- **Dispatch / Combine**：两次 All-to-All；
- **Grouped GEMM**：按专家聚合 token 后批量计算；
- **专家热点**：路由不均会让某张卡成为长尾。

工程要点：batch 要足够大才能让每个专家的 GEMM 有形状效率；EP 规模受限时会退化成大量小 GEMM；All-to-All 的 P50/P99 差异往往比平均值更能解释 TPOT 抖动。DeepSeek 的路线（MLA 压 KV、node-limited routing 限制跨节点、为通信保留 SM）在前面第二篇已经展开。

## 写在最后

推理系统的优化顺序是：先把 KV 管好（容量与碎片），再把批处理调好（TTFT/TPOT 的取舍），再用投机与解耦改变结构性瓶颈。第二期的课程部分到这里结束，最后一篇是八个综合项目的交付标准与常见坑。
