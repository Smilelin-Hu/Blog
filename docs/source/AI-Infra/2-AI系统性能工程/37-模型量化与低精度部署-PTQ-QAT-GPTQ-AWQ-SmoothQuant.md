# 模型量化与低精度部署：PTQ、QAT、GPTQ、AWQ 与 SmoothQuant

07 讲数值格式与训练侧 AMP/FP8；本文讲部署侧的权重量化方法学：校准集、逐层敏感度与精度回归。边界先划清：训练侧 FP8 用动态缩放保梯度，部署侧量化用静态校准压权重，两套口径不混用。

## 1. 量化分类与误差来源

| 形态 | 典型 | 收益面 | 瓶颈假设 |
|---|---|---|---|
| W4A16 | GPTQ/AWQ | decode 吞吐、显存 | memory-bound |
| W8A8 | SmoothQuant | prefill 算力 | compute-bound |
| KV 量化 | FP8/INT8 KV | 容量与带宽 | 长上下文 |

误差三来源：权重舍入误差、激活 outlier 通道、校准分布偏移。逐层敏感度不同——attention 与 MLP、首尾层往往更敏感，这是混合精度量化的依据。

**PTQ vs QAT**：PTQ 只做校准，成本小时级；QAT 训练期插 fake-quant，≤4bit 精度更好但要完整训练跑（成本账对照主题一 30 的蒸馏路线）。

## 2. Weight-only：GPTQ 与 AWQ

- **GPTQ**：逐层二阶补偿（OBS/Hessian 路数），量化一列即用剩余权重补偿误差；低比特精度好，但校准慢（大模型小时级）、对校准集敏感。
- **AWQ**：观察到约 1% 显著权重通道主导激活误差，用 per-channel 等价缩放保护显著通道——不改权重本身、改缩放分布；无需求逆，校准快。405B 规模的对照实验（arXiv 2409.11055）显示 AWQ 精度退化总体小于 GPTQ。
- 工程参数：group size（g128 常见）、校准集几百到几千条且域匹配；kernel 后端（Marlin、exllama、vLLM 集成）决定实测加速，选型时先验后端支持。

## 3. W8A8：SmoothQuant 与 outlier 迁移

激活 outlier 使 A8 直接量化误差爆炸。SmoothQuant 用逐通道等价变换把难度离线迁移：

\[Y = (X \, \text{diag}(s)^{-1}) (\text{diag}(s) \, W)\]

数学不变，但 $X$ 与 $W$ 的量化难度被 $s$ 平衡；迁移强度 $\alpha$ 是核心超参。OmniQuant 等变体把 $s$ 与 clip 阈值变成可学习。适用 prefill/compute-bound 场景；decode 仍 memory-bound，W4A16 更划算——**按负载形态选形态，而不是按比特数选**。

## 4. QAT 与低比特边界

QAT 用 straight-through estimator 穿 fake-quant 反向；≤4bit 或端侧/安全关键场景的精度要求才值得付一次完整训练。可与蒸馏叠加：FP16 原模型当教师，量化学生同时学任务与抗舍入。2026 年的生产共识仍是 PTQ + 回归门禁为主，QAT 作为低比特兜底。

## 5. 校准、敏感度与精度回归方法学

- **校准集**：域覆盖、长度分布匹配生产流量；去污染（呼应主题五 12），避免校准集与评测集重叠造成「假精度」。
- **逐层敏感度**：以 perplexity delta 或 Hessian trace 排序，敏感层留 BF16、其余 INT4 的混合精度；搜索成本用代理指标控制。
- **回归矩阵**：perplexity + 下游基准 + 长上下文 needle + 生成质量人评抽样；门禁阈值在量化**之前**定好（评测体系见主题五 37）。
- **性能验收**：decode tokens/s 对照权重字节数带宽模型，prefill TTFT 对照算力模型；理论加速与实测加速差距超过阈值就查 kernel 与调度，而不是接受「量化了就该快」。

## 6. 工程取舍

| 场景 | 推荐 | 理由 |
|---|---|---|
| 云端 decode 降本 | W4A16 AWQ | 带宽收益直接、校准快 |
| prefill 重/高并发 | W8A8 SmoothQuant | 算力面收益 |
| 端侧极压 | QAT + 蒸馏 | 低比特精度兜底 |
| 长上下文容量 | KV FP8 | 与权重量化正交叠加 |

常见坑：把量化当无损开关（33 已提醒）；校准集过拟合；kernel 不支持导致实测零加速；与投机解码叠加后验收分布变化未重测。

## 写在最后

下一篇：[编译器栈与算子库：MLIR、TVM、XLA、CUTLASS 与 CuTe](/source/AI-Infra/2-AI系统性能工程/38-编译器栈与算子库-MLIR-TVM-XLA-CUTLASS-CuTe)。