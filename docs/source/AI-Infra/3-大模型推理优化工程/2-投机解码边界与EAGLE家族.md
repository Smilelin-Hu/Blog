# 投机解码的收益边界：EAGLE-3 与 P-EAGLE

投机解码的思路很朴素：用一个便宜的小模型先猜几个 token，再让主模型并行验证。但「能猜」不等于「变快」——真正决定收益的是**每个有效 token 的成本**，而不是接受长度这一个数字。

## 1. 统一收益模型

一轮 speculate 的耗时：

$$
T_{round} = T_{draft}(K) + T_{prepare}(K) + T_{verify}(K) + T_{commit}(K)
$$

单位有效 token 的时间：

$$
T_{effective} = \frac{T_{round}}{E[A]}
$$

优化目标是 \(\min T_{effective}\)，而不是单独最大化 \(E[A]\)（平均提交长度）。

### 一个反例

| 方案 | 平均接受长度 | draft 耗时 | verify+其他 | \(T_{effective}\) |
|---|---|---|---|---|
| A | 5 | 10 ms | 5 ms | 15/5 = **3.0 ms/token** |
| B | 4 | 2 ms | 5 ms | 7/4 = **1.75 ms/token** |

方案 B 的接受长度更低，却快了近一倍。这个反例值得记住：**任何只报 acceptance rate 的 Speculator 评测都不完整。**

## 2. 四条 drafter 路线

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l02_01.png" width="80%" alt="投机解码的收益边界" />
  <p>图 1：草拟、准备、验证、提交四段共同决定单位 token 成本</p>
</div>

| 路线 | 代表 | 优势 | 代价 |
|---|---|---|---|
| 自回归特征草拟 | EAGLE 系列 | 候选有显式前缀依赖，草稿质量好 | 需要逐步 rollout |
| 并行多 token 草拟 | P-EAGLE、部分并行 MTP | 一次预测多个未来位置，串行深度低 | 越靠后的位置条件越弱 |
| 原生 MTP | 目标模型自带预测头 | 不必维护独立小模型 | 与特定模型结构绑定 |
| Block-Diffusion | DFlash 系 | 一次生成整块草稿 | 需要在缺少完整前缀依赖时保质量 |

四条路线的取舍其实是同一个问题的四种答案：**在「草稿质量」与「草拟串行深度」之间换位置**。

## 3. 高并发：别忘了 verifier capacity

离线单请求只关心一个用户的 TPOT；在线高并发下，验证本身要占 token batch：

$$
B_{verify} = \sum_i K_i
$$

64 个请求各验证 8 个候选，这一轮就是 512 个候选位置。即使每个请求的延迟下降，也会挤压其他请求的计算预算。所以系统级目标更接近：

$$
\max\ \frac{\text{AcceptedTokens}}{\text{GPUTime}}
$$

而不是 \(\max \text{AcceptedLength}\)。这也是后面 DSpark「按置信度与负载调整验证长度」的动机。

## 4. 五维评估法

只看接受率会看错方向，至少要五个维度：

1. **草稿质量**：acceptance rate、mean accepted length、prefix survival probability；
2. **草稿成本**：forward 次数、每次 FLOPs、是否需要 Target hidden states、是否增加权重/KV；
3. **验证成本**：验证 token 数、候选树节点数、attention mask 复杂度、高并发下的 batch occupancy；
4. **内存与部署**：Speculator 权重、额外 cache、模型兼容性、checkpoint 管理；
5. **负载适配**：代码、数学、模板文本、开放创作、长推理的可预测性差异极大——**不存在对所有 workload 固定最优的 Speculator**。

## 5. EAGLE-3：从「特征像」到「token 对」

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l03_01.png" width="80%" alt="EAGLE-3 结构" />
  <p>图 2：多层特征融合 + 直接 token 预测的训练目标</p>
</div>

### 5.1 训练目标为什么改

早期做法让 Drafter 回归 Target 的 hidden feature。问题是：**feature 空间距离变小，不保证最终 token 排名更接近 Target**。而投机解码真正拿到的收益，是 Target 接受了多少 token。

于是把目标直接写成未来 token 的交叉熵：

$$
\mathcal{L}_{draft} = -\sum_{j=1}^{K}\log q_\theta\left(x_{t+j}\mid \text{features},\ \text{draft context}\right)
$$

### 5.2 为什么要多层特征

Transformer 不同层的信息不同：浅层偏词法与局部，中层形成组合语义，深层接近 next-token 决策。只接最后一层，会丢掉对未来 rollout 有用的中间信号：

$$
z_t = \phi\left(h_t^{(l_1)}, h_t^{(l_2)}, \ldots, h_t^{(l_m)}\right),\qquad
q_\theta\left(x_{t+1:t+K}\mid z_t\right)
$$

\(\phi\) 可以是拼接、投影或专门的 fusion 模块。工程上真正要算的是：**取 Target 特征这件事，会不会增加存储、通信与训练开销。**

### 5.3 Training-Time Test

普通蒸馏先构造「正确答案」，再让学生逼近。但 Speculator 上线后，第 2、3、4 个候选是建立在**它自己猜的前缀**之上的：

```text
训练：永远从正确前缀继续      → 上线：经常从自己猜的前缀继续
```

这就是 exposure mismatch。Training-Time Test 的做法是训练阶段就主动运行 Drafter，让样本分布更接近真实 rollout 分布。

### 5.4 位置级准确率与 prefix survival

假设未来 5 个位置的准确率是 90% / 75% / 58% / 40% / 25%。若验证只取「最长正确前缀」，后两个位置的低准确率几乎不产生收益。真正该看的是：

$$
P(A \ge k) = P(d_1 \text{ accepted}, \ldots, d_k \text{ accepted}),\qquad
E[A] = \sum_{k \ge 1} P(A \ge k)
$$

这个式子比「所有位置平均准确率」更接近实际加速：**每一段前缀的存活概率相乘，长前缀的衰减是指数的。**

### 5.5 训练数据从哪来

EAGLE 类训练需要 Target 的隐藏状态，两条管线各有代价：

| 方式 | 优点 | 缺点 |
|---|---|---|
| Offline features（预跑 Target 存盘） | 训练时不加载 Target | 特征巨大；数据集/修订/层选择一变就要重建；I/O 成瓶颈 |
| Online features（训练时现跑） | 数据新鲜、流程简单、易在线采样 | Target forward 显著抬高训练成本 |

### 5.6 评测要看什么

不要只看 validation loss，至少同时记录：top-1 token accuracy、position-wise accuracy、mean accepted length、tree acceptance、draft ms/round、verify ms/round、端到端 TPOT。

## 6. P-EAGLE：并行草拟的两个陷阱

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l04_01.png" width="80%" alt="P-EAGLE 并行草拟" />
  <p>图 3：多头并行预测 t+1…t+K，用分布条件补上「未来的条件」</p>
</div>

### 6.1 并行的问题

```text
并行：当前 hidden → head1→t+1, head2→t+2, head3→t+3, head4→t+4
自回归：t+1 → 作为条件 → t+2 → 作为条件 → t+3
```

并行版本在预测 \(t+4\) 时并不知道 \(t+1..t+3\) 最终是什么，于是深层位置近乎盲猜。P-EAGLE 要解决的不是「并行输出四个 logits」，而是**如何在并行计算时给深层位置足够的条件信息**。

### 6.2 把草拟深度看成多任务

$$
q_k\left(x_{t+k}\mid h_t\right),\ k = 1,\ldots,K;\qquad
\mathcal{L} = \sum_{k=1}^{K} w_k \mathcal{L}_k
$$

深位置更难，可以给不同权重。更关键的是让条件包含前序位置的**分布信息**（而非离散采样 token），从而既能并行构造，又保留依赖：

$$
q_k\left(x_{t+k}\mid h_t, q_1, \ldots, q_{k-1}\right)
$$

### 6.3 两个主要风险

**Suffix accuracy decay**：越靠后条件越弱，准确率下降。设 \(p_k\) 为「前 \(k-1\) 都接受时第 \(k\) 个也接受」的概率：

$$
P(A \ge k) = \prod_{i=1}^{k} p_i
$$

一个位置稍降，长前缀存活率就快速塌陷——这解释了为什么「并行 K 开大」经常不划算。

**Verification waste**：并行草拟很便宜，容易把 \(K\) 开大；但 Target 仍要验证每个位置：

$$
T_V(K) = a + bK + cK^2_{mask}
$$

草拟成本近似常数，浪费却被转移到 verifier。

### 6.4 何时真的更快

$$
\frac{E[A_P]}{T_D^{P} + T_V^{P}} > \frac{E[A_{AR}]}{T_D^{AR} + T_V^{AR}}
$$

其中 AR 的草拟成本 \(T_D^{AR}(K) \approx K t_d\)，而并行草拟 \(T_D^{P}(K) \approx t_{base} + \Delta(K)\)。若 \(\Delta(K)\) 增长缓慢，就能在相近草拟延迟下给出更多候选——但只有上式成立时才有意义。

### 6.5 域适配是硬约束

并行草拟对工作负载分布极其敏感：代码补全有强局部结构，数学推理有固定模式，开放创作的不确定性高。评测必须分域报告 position-wise acceptance：

- coding
- math / reasoning
- general chat
- structured / template
- bilingual / multilingual

**在一个域上把接受率做到 4.0，不代表在另一个域上不会退化到 1.5。**

## 写在最后

投机解码的边界已经清晰：草稿质量、草拟代价、验证代价、并发挤压，四者共同决定是否值得启用。EAGLE-3 用「直接 token 目标 + 多层特征 + 训练期自测」抬高接受率，P-EAGLE 用并行多头压低串行深度——但后者必须付 suffix decay 与 verification waste 的代价。

下一篇继续在「一次出多少 token」这条轴上走：MTP 的原生预测头、DFlash 的 block diffusion、DFlare 的层融合扩容、DDTree 的树验证、DSpark 的置信度调度。
