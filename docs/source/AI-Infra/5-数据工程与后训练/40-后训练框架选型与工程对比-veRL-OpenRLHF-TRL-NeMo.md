# 后训练框架选型与工程对比：veRL、OpenRLHF、TRL 与 NeMo-Aligner

主题一 23 以 OpenRLHF 为分离部署案例，27/28 讲 RLHF 控制面与 Rollout 机制；本文补框架落地层：四个主流框架的架构差异、选型判据与迁移成本。先立边界：**框架解决「算法怎么在 GPU 上跑起来」，29–36 的控制面、陈旧度、可观测性与恢复语义是框架之外仍要自建的部分**，换框架不豁免这些工程。

## 1. 架构分野：colocate vs disaggregate

RLHF/RLVR 的核心工程矛盾是 rollout（推理引擎）与 train（训练引擎）的资源组织：

- **colocate（共置分时）**：同一组 GPU 上训练与推理交替执行，切换时做权重 resharding 与引擎 sleep/wake。显存利用率高、无需跨集群权重搬运，代价是切换开销与两引擎的显存峰值叠加。veRL 的 HybridFlow 是代表：单控制器编排 + worker 内混合引擎，3D-HybridEngine 在 train/rollout 间重分片。
- **disaggregate（分离）**：训练集群与 rollout 集群独立（Ray 编排），权重经网络同步。两侧可独立扩缩、rollout 可用满血推理引擎，代价是权重传输带宽与陈旧度管理（28/29 的口径）。OpenRLHF 是代表：Ray + vLLM + DeepSpeed 的组合，论文口径相对 colocate 基线有 1.2–1.7× 加速。

两种形态没有绝对优劣：GPU 紧张、模型中等规模 → colocate 省卡；超大规模、rollout 占比高（Agentic RL 长轨迹）→ disaggregate 弹性好。

## 2. 四框架对照

| 维度 | TRL | OpenRLHF | veRL | NeMo-Aligner |
|---|---|---|---|---|
| 定位 | HF 生态入口，算法最全 | Ray 分离式，生产 RLHF | HybridFlow 共置，算法/规模兼顾 | NVIDIA 栈深度优化 |
| 训练后端 | Accelerate/DeepSpeed/FSDP | DeepSpeed | FSDP/Megatron | Megatron |
| rollout 引擎 | 内置生成/vLLM | vLLM | vLLM/SGLang | TRT-LLM 加速 |
| 规模甜区 | 单机–中小集群 | 中大集群 | 中–大集群 | 大集群（NVIDIA） |
| 算法覆盖 | SFT/DPO/PPO/GRPO/KTO 等最全 | PPO/GRPO/REINFORCE++/DPO 系 | PPO/GRPO/DAPO 系 + 多模态/Agentic 扩展 | PPO/DPO/GRPO/SteerLM |
| 上手成本 | 最低 | 中（Ray 心智） | 中（配置面大） | 高（Megatron 心智） |

2026 格局：TRL 是算法实验与中小规模首选（新算法通常最先落地 TRL）；veRL 与 OpenRLHF 是大规模 RLVR/Agentic RL 的两个主流生产选项，前者共置省卡、后者分离弹性；NeMo-Aligner 绑定 NVIDIA 全栈（Megatron + TRT-LLM），已有 NeMo 预训练资产的团队延续成本最低。TorchTitan 等偏预训练框架不在此列，但常被拿来与后训练栈组合。

## 3. 选型判据

按顺序问四个问题：

1. **模型与集群规模**：70B 以下单机多卡 → TRL 足够；百卡级 RLVR → veRL/OpenRLHF；已有 Megatron 资产 → NeMo-Aligner。
2. **rollout 占比**：Agentic RL rollout 时间远超 train → 分离式 + 独立扩缩（OpenRLHF 或 veRL 的分离模式）；短轨迹数学 RL → 共置切换开销可接受。
3. **算法迭代速度**：研究团队要快速试新算法 → TRL 生态红利；算法稳定要吞吐 → 生产框架。
4. **团队栈与硬件**：Ray 经验、vLLM/SGLang 运维能力、是否 NVIDIA 独占，决定运维成本而非纸面性能。

纸面吞吐对比要带 workload 口径（模型尺寸、序列长、rollout/train 比例、硬件），跨 workload 的加速比数字不可直接外推。

## 4. 迁移成本与工程共性

迁移框架的真实成本不在训练脚本，而在四处：**数据 schema**（prompt/reward 字段与打包格式）、**reward/verifier 接口**（自定义奖励函数与沙箱验证的接入方式）、**checkpoint 格式**（Megatron ↔ FSDP ↔ HF 的转换与优化器状态丢失风险）、**控制面适配**（提交合同、指标埋点、恢复语义要重新对接 27/35/36）。评估迁移时先做这四项的 PoC，再谈吞吐收益。

无论选哪个框架，以下工程不变：训推权重一致性与陈旧度监控（29）、rollout 引擎重分片（28）、评测回归（37 的 harness 进 CI）、成本归因（33）。框架是「可替换的执行层」，这些才是平台的固定资产。

## 5. 验收

验收清单：选型决策记录含 workload 口径与四问答案、吞吐对比在同 workload 下复测、迁移 PoC 覆盖数据/reward/checkpoint/控制面四项、框架版本与 rollout 引擎版本 pin 并随评测存档、控制面工程（29–36）不依赖特定框架私有接口。

## 写在最后

主题五从数据基础设施一路补到评测、多模态数据、标注运营与框架选型，后训练链路的覆盖度缺口至此补齐。返回系列目录：[AI Infra 笔记总览](/source/AI-Infra/README)。