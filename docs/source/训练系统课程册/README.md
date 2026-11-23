# 训练系统课程册

按课程原课次顺序整理的实验笔记：每课一篇，先讲机制，再给实验闭环（Fixture/真实路径、输入输出与验收），最后落判读纪律。与 [AI Infra 主题笔记](/source/AI-Infra/README) 的区别在于组织方式——主题笔记按知识域重组，本册保留课次顺序，聚焦「实验怎么做、结论怎么判」。

## 目录

- [大模型数据与后训练基础设施全景](/source/训练系统课程册/01-大模型数据与后训练基础设施全景)
- [语料规模、质量、独特性与训练价值的度量](/source/训练系统课程册/02-语料规模、质量、独特性与训练价值的度量)
- [面向训练的数据湖、资产目录与血缘架构](/source/训练系统课程册/03-面向训练的数据湖、资产目录与血缘架构)
- [数据源战略、许可边界与-Source-Registry](/source/训练系统课程册/04-数据源战略、许可边界与-Source-Registry)
- [WARC、HTML、PDF、代码与对话数据解析](/source/训练系统课程册/05-WARC、HTML、PDF、代码与对话数据解析)
- [DataTrove、NeMo-Curator、Ray-与-Spark-数据流](/source/训练系统课程册/06-DataTrove、NeMo-Curator、Ray-与-Spark-数据流)
- [训练数据格式、分片、索引、流式读取与缓存](/source/训练系统课程册/07-训练数据格式、分片、索引、流式读取与缓存)
- [文本规范化、语言识别与内容边界清洗](/source/训练系统课程册/08-文本规范化、语言识别与内容边界清洗)
- [启发式质量过滤与数据画像](/source/训练系统课程册/09-启发式质量过滤与数据画像)
- [模型化质量评分、领域分类与难度建模](/source/训练系统课程册/10-模型化质量评分、领域分类与难度建模)
- [精确、模糊、段落与子串去重](/source/训练系统课程册/11-精确、模糊、段落与子串去重)
- [语义去重、聚类、多样性保持与基准去污染](/source/训练系统课程册/12-语义去重、聚类、多样性保持与基准去污染)
- [隐私、安全、版权、投毒与数据退出机制](/source/训练系统课程册/13-隐私、安全、版权、投毒与数据退出机制)
- [领域分类、采样权重与数据课程](/source/训练系统课程册/14-领域分类、采样权重与数据课程)
- [DoReMi、RegMix-与代理模型驱动的混合优化](/source/训练系统课程册/15-DoReMi、RegMix-与代理模型驱动的混合优化)
- [Tokenization、样本构造、Packing-与长上下文数据](/source/训练系统课程册/16-Tokenization、样本构造、Packing-与长上下文数据)
- [确定性-Sharding、Shuffle、断点续读与数据发布门禁](/source/训练系统课程册/17-确定性-Sharding、Shuffle、断点续读与数据发布门禁)
- [Continued-Pretraining-与-Mid-training-数据设计](/source/训练系统课程册/18-Continued-Pretraining-与-Mid-training-数据设计)
- [SFT-数据-Schema、Chat-Template-与-Loss-Mask](/source/训练系统课程册/19-SFT-数据-Schema、Chat-Template-与-Loss-Mask)
- [合成指令、响应、推理轨迹与自改进数据](/source/训练系统课程册/20-合成指令、响应、推理轨迹与自改进数据)
- [SFT-数据选择、混合、去污染与消融](/source/训练系统课程册/21-SFT-数据选择、混合、去污染与消融)
- [人类偏好、AI-Feedback-与-On-policy-偏好数据](/source/训练系统课程册/22-人类偏好、AI-Feedback-与-On-policy-偏好数据)
- [Reward-Model、Process-Reward-与奖励可靠性](/source/训练系统课程册/23-Reward-Model、Process-Reward-与奖励可靠性)
- [DPO、IPO、KTO、ORPO、SimPO-与离线偏好系统](/source/训练系统课程册/24-DPO、IPO、KTO、ORPO、SimPO-与离线偏好系统)
- [PPO、GRPO、RLOO、DAPO-与长推理训练](/source/训练系统课程册/25-PPO、GRPO、RLOO、DAPO-与长推理训练)
- [RLVR、环境、拒绝采样与-Agentic-数据飞轮](/source/训练系统课程册/26-RLVR、环境、拒绝采样与-Agentic-数据飞轮)
- [RLHF-数据流图与分布式控制面](/source/训练系统课程册/27-RLHF-数据流图与分布式控制面)
- [Rollout-引擎、权重同步、重分片与资源放置](/source/训练系统课程册/28-Rollout-引擎、权重同步、重分片与资源放置)
- [同步、异步、Partial-Rollout、陈旧度与训练—推理不一致](/source/训练系统课程册/29-同步、异步、Partial-Rollout、陈旧度与训练—推理不一致)
- [可观测性、检查点、容错、成本与持续后训练](/source/训练系统课程册/30-可观测性、检查点、容错、成本与持续后训练)
- [从-Common-Crawl-到可训练语料](/source/训练系统课程册/31-从-Common-Crawl-到可训练语料)
- [可版本化、可追责的数据湖与血缘控制面](/source/训练系统课程册/32-可版本化、可追责的数据湖与血缘控制面)
- [Continued-Pretraining-与-SFT-数据配方工厂](/source/训练系统课程册/33-Continued-Pretraining-与-SFT-数据配方工厂)
- [合成数据、偏好数据与-Reward-Model-工厂](/source/训练系统课程册/34-合成数据、偏好数据与-Reward-Model-工厂)
- [可按显存缩放的-SFT-到-DPO-到-GRPO-RLVR-流水线](/source/训练系统课程册/35-可按显存缩放的-SFT-到-DPO-到-GRPO-RLVR-流水线)
- [可恢复的异步-Agentic-RL-后训练平台](/source/训练系统课程册/36-可恢复的异步-Agentic-RL-后训练平台)

## 判读总纪律

- 默认 Fixture/模拟只验证控制逻辑；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置不足返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据；负例与失败注入对照必做。
