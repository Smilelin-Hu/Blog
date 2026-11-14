# 一次多出几个 Token：MTP、DFlash 与调度式验证

投机解码的下半场都在回答同一个问题：**在「一次前向」里，怎样榨出更多可被接受的前缀？** 五条路线分别从「原生预测头」「并行出块」「加深草拟」「树状覆盖」「按置信度裁剪」入手。

## 1. MTP：模型自带的预测头

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l05_01.png" width="78%" alt="MTP 部署" />
  <p>图 1：MTP 复用 Target 的 embedding/hidden，额外预测未来若干 token</p>
</div>

优势很直接：不必再部署一个独立小模型；可能复用 Target 的 embedding 与 hidden；训练阶段就已经注入了未来 token 监督；checkpoint 与 Target 结构天然关联。

但有一条必须写死的判断：**「模型里有 MTP 模块」不等于「线上打开一个参数就加速」**。还要看 Runtime 是否支持、head 质量、验证路径、并发与硬件。

### 1.1 训练目标 ≠ Serving 收益

训练时常见的目标是：

$$
\mathcal{L} = \mathcal{L}_{next} + \lambda\sum_{k=1}^{K}\mathcal{L}_{mtp,k}
$$

它的目的可能是改善表示、提高样本效率、或为将来的投机推理留出 head。Serving 只关心：

$$
\text{Speedup} = f(\text{HeadQuality}, \text{HeadCost}, \text{VerifyCost}, \text{Concurrency})
$$

一个训练上有益的 head，如果推理时算得重、接受率又不高，**未必适合上线**。

### 1.2 Depth 不是越大越好

```text
Depth 1 → 平均接受 1.8 / 轮
Depth 2 → 2.5
Depth 4 → 3.0
Depth 8 → 3.1，但 verify cost 明显上升
```

线上最优深度要靠真实数据扫，而不是照抄模型配置。

### 1.3 域适配与 LoRA 叠加

MTP 学的是未来 token 的条件分布。若上线分布与训练分布不同（\(P_{train} \ne P_{serve}\)），接受率会掉。实践中会对 code / math / reasoning / customer-service / JSON-tool-call 分别做轻量微调或校准，但必须验证：**只调 MTP 是否保持了 Target 主模型的输出分布不变**。

更隐蔽的组合是 Multi-LoRA：

```text
Base + LoRA A     Base + LoRA B
```

Target 分布已经变了，原来针对 Base 训练的 MTP 是否还有高接受率，需要单独测。四种策略：Base 共用（接受下降）、热门 LoRA 单独适配、低流量 LoRA 关闭 MTP、Router 按 adapter 选 speculator 策略。

### 1.4 Checkpoint 生命周期

```text
Target model revision / Target tokenizer revision
MTP speculator revision / MTP depth
Training dataset & version / Runtime version / Compatibility hash
```

不能只叫 `mtp_final.pt`——Target 一升级，旧 MTP 可能直接不兼容。

### 1.5 成本模型

$$
T_{MTP} = T_{feature} + T_{heads}(K) + T_{verify}(K) + T_{commit}
$$

多个 head 真正并行时 \(T_{heads}(K)\) 增长很慢；如果实现仍串行、或退化成许多小 Kernel，优势会被 Runtime 开销吃掉。

## 2. DFlash：一次出一块

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l06_01.png" width="78%" alt="DFlash block diffusion" />
  <p>图 2：把未来位置初始化成 mask，在一次轻量前向里并行产出整块候选</p>
</div>

### 2.1 块是怎么形成的

```text
AR Drafter：      x1 → x2(条件 x1) → x3(条件 x1,x2) ...
Block-Diffusion： context | [MASK][MASK][MASK][MASK] → 一次前向出整块
```

Drafter 同时看三样东西：Target 的上下文 hidden states、未来 mask 位置、以及 block 内允许的非因果交互。

$$
q_\theta\left(x_{t+1:t+K} \mid H_{target}, M_{1:K}\right)
$$

关键不在「像图像扩散那样走很多步」，而在**块内 token 可以并行预测**。

### 2.2 为什么必须吃 Target 的 hidden

只给一个小 Drafter 原始 token 上下文，它没有足够容量准确预测多个未来位置。Target 已经算出了对上下文的丰富表示：

$$
H_{target} = \{h_t^{(l_1)}, h_t^{(l_2)}, \ldots\}
$$

把它喂给 Drafter，等于「Target 先做高质量理解，Drafter 再借这份理解快速猜」。这也是 DFlash 不是通用独立 diffusion LLM 的原因。

### 2.3 非因果 draft attention 为什么可以

AR Target 的因果性不可破坏，但 **Drafter 只是提出候选**，最终仍由 AR Target 验证。所以 draft 内部可以让多个 mask 位置互相通信：

```text
Mask1 ←→ Mask2 ←→ Mask3 ←→ Mask4
   ↖        ↑        ↑        ↗
      Target Context Features
```

### 2.4 块越大越好吗

$$
T_{eff}^{DF} = \frac{t_{block}(K) + T_V(K) + T_O}{E[A(K)]}
$$

Block Size 同时改变五件事：Drafter 计算、后缀准确率、Target 验证 token 数、被拒 token 数、verifier batch occupancy。

若逐位置存活概率是 0.95 / 0.90 / 0.82 / 0.70 / 0.55 / 0.40，把 block 从 4 扩到 16，后面十来个位置几乎不可能通过——只会增加草拟、增加验证、占掉 GPU token budget，把高并发吞吐拖坏。

## 3. DFlare：给更深的 Drafter 配更好的条件

当 Drafter 变深时，所有层共享同一个「窄瓶颈」注入点会浪费容量。Layer-wise fusion 改为每层取自己的加权组合：

$$
z_j = \sum_i \alpha_{j,i}\, P_i\left(h^{(l_i)}\right)
$$

```text
Target L_a ─┬─→ Fusion_for_D1 → Draft1
Target L_b ─┼─→ Fusion_for_D2 → Draft2
Target L_c ─┼─→ Fusion_for_D3 → Draft3
Target L_d ─┴─→ Fusion_for_D4 → Draft4
```

加深能提升位置间交互、复杂模式拟合与结构化域（代码/数学）的预测力，但成本也涨：

$$
\max_{L}\ \frac{E[A(L)]}{T_{draft}(L) + T_{verify}(L)}
$$

**目标是最大化这个比值，而不是最大化 depth。** 另外，capacity 与数据规模必须一起扩：参数涨、训练 token 与域覆盖不涨，只会过拟合，深层学不到稳定增益。

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l07_01.png" width="78%" alt="DFlare 层融合" />
  <p>图 4：不同 Draft 层取不同的 Target 层组合，而不是共享同一个窄瓶颈</p>
</div>

## 4. DDTree：用树覆盖分支

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l08_01.png" width="78%" alt="DDTree 树验证" />
  <p>图 3：把线性的 block 候选换成树，用 ancestor-only mask 一次验证多条路径</p>
</div>

### 4.1 线性后缀为什么脆

```text
线性：A → C → E → F
树：       A
         /   \
        C     D
       / \   / \
      E  F  E   F
```

如果 Target 在第 2 个位置更偏好 D，线性后缀立刻被截断；树只要真实路径落在树里，就可能继续接受更多 token。

### 4.2 候选树不是笛卡尔积

每位置保留 \(b\) 个、深度 \(K\)，节点量是：

$$
N = \sum_{d=1}^{K} b^d
$$

\(b=4, K=8\) 已经不可接受。所以必须在节点预算 \(B\) 下挑「最值得验证」的路径：

$$
\mathrm{Score}(path) = \prod_k q_k(x_k),\qquad
\log \mathrm{Score} = \sum_k \log q_k(x_k)
$$

用 best-first / 堆逐步扩高分路径，直到耗尽预算。

### 4.3 一个必须理解的概念边界

Diffusion Drafter 的每位置分布更像是「在整块条件下这个位置像什么」，而 Target 的接受是**严格前缀判定**：第 3 个 token 有效，必须建立在前两个都属于同一正确前缀之上。**marginal probability 不是路径概率**——这正是后续 tree scoring / cost-aware budget 继续改进的地方。

### 4.4 树验证的硬约束

Target 一次前向要让每个节点只看自己的祖先，不能看兄弟：

```text
Root ├─ A ├─ C
     │    └─ D   ← D 可看 Root,A,D；不可看 C
     └─ B ├─ E
          └─ F
```

mask 一旦写错让分支看见兄弟，就破坏了因果语义，验证结果不再对应真实自回归路径。

## 5. DSpark：把「猜多长」变成运行时决策

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l09_01.png" width="78%" alt="DSpark 调度" />
  <p>图 4：重 backbone 跑一次 + 轻量串行模块补依赖，再按置信度与负载决定验证长度</p>
</div>

### 5.1 半自回归草拟

```text
Heavy Parallel Backbone（一次）
      ↓
轻量 Sequential Module（块内建依赖）
      ↓
更稳定的 t1, t2, t3 …
```

如果轻量串行部分的成本远小于重跑完整 Drafter，就能用少量额外延迟换明显的后缀质量。

### 5.2 置信度决定验证长度

定义前缀存活概率 \(s_k = P(A \ge k)\)（通常单调下降），若模型还能预测 \(\hat{s}_k \approx P(A\ge k \mid \text{features})\)，系统就可以不再「一刀切 8 个候选」：

$$
K_r^\ast = \arg\max_K \frac{E[A_r(K)]}{T_V(K) + Cost_{capacity}(K)}
$$

```text
Request A：置信度高 → 验证 12
Request B：置信度低 → 验证 4
```

### 5.3 负载感知

```text
Verifier batch capacity = 1024 positions
64 requests × 16 candidates = 1024
```

如果其中很多后缀注定被拒，整轮 GPU 就被低价值 token 填满。于是策略随负载切换：

- 低负载：允许更长 speculation，追求单用户速度；
- 高负载：更保守，砍掉低置信候选，保总吞吐；
- 交互 SLO 紧：优先高价值短 block；
- 离线任务：允许更激进的吞吐策略。

到这一步，Speculator 已经不是一个 checkpoint 的静态属性，而是 **Runtime / Serving 的一部分**。

## 6. 五条路线的横向对比

| 路线 | 一次产出的形态 | 主要收益来源 | 主要风险 |
|---|---|---|---|
| MTP | 原生多头，顺序位置 | 省掉独立小模型、复用 Target 表示 | 深度与验证成本；LoRA/版本兼容 |
| DFlash | 并行整块（mask block） | 草拟成本随 K 增长慢 | 后缀衰减；block 过大挤占 verifier |
| DFlare | 更深 Drafter + 分层融合 | 复杂域接受率提升 | 草拟延迟上升；需同步扩数据 |
| DDTree | 树形候选 | 覆盖分支、提高路径命中 | 节点预算爆炸；mask 易错 |
| DSpark | 置信度自适应的块 | 按需分配验证预算 | 需要 reliability 的置信估计与负载信号 |

## 写在最后

这五条路线的共同趋势很清楚：从「改模型」走向「改调度」。下一步就是把这套能力工程化——训练什么数据、用什么指标验收、怎么发布、上线后怎么监控漂移。下一篇看 Speculator 的工程化闭环。
