# 第五期 数据工程与后训练

从「模型能力从哪来」这条线出发的工程笔记：语料度量与数据供应链、数据湖与资产目录、解析与清洗、质量与去重、治理与混合、训练数据交付、合成数据与 SFT 配方、偏好与奖励、RL 与 RLVR，最后以可恢复的后训练平台收口。

## 目录

### 导览与数据度量

- [00-课程内容介绍](/source/AI-Infra/5-数据工程与后训练/00-课程内容介绍)
- [01-大模型数据与后训练基础设施全景](/source/AI-Infra/5-数据工程与后训练/01-大模型数据与后训练基础设施全景)
- [02-语料规模、质量、独特性与训练价值的度量](/source/AI-Infra/5-数据工程与后训练/02-语料规模-质量-独特性与训练价值的度量)

### 数据湖、来源与解析

- [03-面向训练的数据湖、资产目录与血缘架构](/source/AI-Infra/5-数据工程与后训练/03-面向训练的数据湖-资产目录与血缘架构)
- [04-数据源战略、许可边界与 Source Registry](/source/AI-Infra/5-数据工程与后训练/04-数据源战略-许可边界与SourceRegistry)
- [05-WARC、HTML、PDF、代码与对话数据解析](/source/AI-Infra/5-数据工程与后训练/05-WARC-HTML-PDF-代码与对话数据解析)
- [06-DataTrove、NeMo Curator、Ray 与 Spark 数据流](/source/AI-Infra/5-数据工程与后训练/06-DataTrove-NeMoCurator-Ray与Spark数据流)
- [07-训练数据格式、分片、索引、流式读取与缓存](/source/AI-Infra/5-数据工程与后训练/07-训练数据格式-分片-索引-流式读取与缓存)

### 清洗、质量与去重

- [08-文本规范化、语言识别与内容边界清洗](/source/AI-Infra/5-数据工程与后训练/08-文本规范化-语言识别与内容边界清洗)
- [09-启发式质量过滤与数据画像](/source/AI-Infra/5-数据工程与后训练/09-启发式质量过滤与数据画像)
- [10-模型化质量评分、领域分类与难度建模](/source/AI-Infra/5-数据工程与后训练/10-模型化质量评分-领域分类与难度建模)
- [11-精确、模糊、段落与子串去重](/source/AI-Infra/5-数据工程与后训练/11-精确-模糊-段落与子串去重)
- [12-语义去重、聚类、多样性保持与基准去污染](/source/AI-Infra/5-数据工程与后训练/12-语义去重-聚类-多样性保持与基准去污染)

### 治理、混合与数据交付

- [13-隐私、安全、版权、投毒与数据退出机制](/source/AI-Infra/5-数据工程与后训练/13-隐私-安全-版权-投毒与数据退出机制)
- [14-领域分类、采样权重与数据课程](/source/AI-Infra/5-数据工程与后训练/14-领域分类-采样权重与数据课程)
- [15-DoReMi、RegMix 与代理模型驱动的混合优化](/source/AI-Infra/5-数据工程与后训练/15-DoReMi-RegMix与代理模型驱动的混合优化)
- [16-Tokenization、样本构造、Packing 与长上下文数据](/source/AI-Infra/5-数据工程与后训练/16-Tokenization-样本构造-Packing与长上下文数据)
- [17-确定性 Sharding、Shuffle、断点续读与数据发布门禁](/source/AI-Infra/5-数据工程与后训练/17-确定性Sharding-Shuffle-断点续读与数据发布门禁)

### 继续预训练与 SFT 数据

- [18-Continued Pretraining 与 Mid-training 数据设计](/source/AI-Infra/5-数据工程与后训练/18-ContinuedPretraining与Mid-training数据设计)
- [19-SFT 数据 Schema、Chat Template 与 Loss Mask](/source/AI-Infra/5-数据工程与后训练/19-SFT数据Schema-ChatTemplate与LossMask)
- [20-合成指令、响应、推理轨迹与自改进数据](/source/AI-Infra/5-数据工程与后训练/20-合成指令-响应-推理轨迹与自改进数据)
- [21-SFT 数据选择、混合、去污染与消融](/source/AI-Infra/5-数据工程与后训练/21-SFT数据选择-混合-去污染与消融)

### 偏好、奖励与强化学习

- [22-人类偏好、AI Feedback 与 On-policy 偏好数据](/source/AI-Infra/5-数据工程与后训练/22-人类偏好-AIFeedback与On-policy偏好数据)
- [23-Reward Model、Process Reward 与奖励可靠性](/source/AI-Infra/5-数据工程与后训练/23-RewardModel-ProcessReward与奖励可靠性)
- [24-DPO、IPO、KTO、ORPO、SimPO 与离线偏好系统](/source/AI-Infra/5-数据工程与后训练/24-DPO-IPO-KTO-ORPO-SimPO与离线偏好系统)
- [25-PPO、GRPO、RLOO、DAPO 与长推理训练](/source/AI-Infra/5-数据工程与后训练/25-PPO-GRPO-RLOO-DAPO与长推理训练)
- [26-RLVR、环境、拒绝采样与 Agentic 数据飞轮](/source/AI-Infra/5-数据工程与后训练/26-RLVR-环境-拒绝采样与Agentic数据飞轮)

### 后训练系统与运营

- [27-RLHF 数据流图与分布式控制面](/source/AI-Infra/5-数据工程与后训练/27-RLHF数据流图与分布式控制面)
- [28-Rollout 引擎、权重同步、重分片与资源放置](/source/AI-Infra/5-数据工程与后训练/28-Rollout引擎-权重同步-重分片与资源放置)
- [29-同步、异步、Partial Rollout、陈旧度与训练—推理不一致](/source/AI-Infra/5-数据工程与后训练/29-同步-异步-PartialRollout-陈旧度与训练—推理不一致)
- [30-可观测性、检查点、容错、成本与持续后训练](/source/AI-Infra/5-数据工程与后训练/30-可观测性-检查点-容错-成本与持续后训练)

### 综合项目

- [31-从 Common Crawl 到可训练语料](/source/AI-Infra/5-数据工程与后训练/31-从CommonCrawl到可训练语料)
- [32-可版本化、可追责的数据湖与血缘控制面](/source/AI-Infra/5-数据工程与后训练/32-可版本化-可追责的数据湖与血缘控制面)
- [33-Continued Pretraining 与 SFT 数据配方工厂](/source/AI-Infra/5-数据工程与后训练/33-ContinuedPretraining与SFT数据配方工厂)
- [34-合成数据、偏好数据与 Reward Model 工厂](/source/AI-Infra/5-数据工程与后训练/34-合成数据-偏好数据与RewardModel工厂)
- [35-可按显存缩放的 SFT 到 DPO 到 GRPO/RLVR 流水线](/source/AI-Infra/5-数据工程与后训练/35-可按显存缩放的SFT到DPO到GRPORLVR流水线)
- [36-可恢复的异步 Agentic RL 后训练平台](/source/AI-Infra/5-数据工程与后训练/36-可恢复的异步AgenticRL后训练平台)