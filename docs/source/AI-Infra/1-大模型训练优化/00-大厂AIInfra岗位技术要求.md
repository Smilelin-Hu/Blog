# 大厂 AI Infra 岗位技术要求

根据 2026 年最新招聘信息与行业趋势，AI Infra（AI 基础设施）岗位的技术要求可归纳为多个核心维度。本文先按岗位方向拆分门槛，再逐维度列出技能要求，最后给出能力分级与本系列课件的学习路径映射。

## 1. 岗位方向细分

「AI Infra」不是一个岗位，而是五条技能栈差异很大的方向。投递与准备前应先确定主攻线，避免把八张技能表平铺成「什么都要会」。

| 方向 | 核心问题 | 硬门槛 | 主要落在 |
|---|---|---|---|
| 训练 Infra | 让千亿模型在万卡上跑满 MFU 且可恢复 | 3D 并行、显存与重计算、NCCL 与拓扑、检查点与弹性 | 主题一、主题二 |
| 推理 Infra | 在 SLO 约束下把每 Token 成本压到最低 | KV Cache、批处理与调度、量化、投机解码、PD 分离 | 主题二、主题三 |
| 平台 Infra | 让多团队自助、可配额、可审计地拿到算力 | K8s Operator、队列与抢占、工作负载 API、交付与供应链 | 主题四 |
| 数据与后训练 Infra | 让能力可复现地被数据与 RL 流水线生产出来 | 数据管线与去重、SFT/偏好 Schema、Rollout 与权重同步、评测 | 主题五 |
| 异构与内核 | 把算子与编译栈榨到硬件极限 | CUDA/Triton、CUTLASS、编译栈、国产芯片适配 | 主题一、主题二 |

方向之间并非互斥：推理 Infra 需要平台能力做 Fleet 运营，后训练 Infra 需要训练与推理两套系统知识。但**主门槛只有一条**，其余是协作面。

## 2. 编程语言与基础能力

| 技能 | 要求说明 |
|---|---|
| Python | 必备，用于模型训练脚本、数据 pipeline、自动化工具 |
| C++ / CUDA | 高频要求，用于 Kernel/算子开发、推理引擎优化、底层性能调优 |
| Go | 部分岗位加分，用于基础设施服务开发（Operator、Gateway、控制面） |
| Rust | 新兴加分项，出现在部分推理引擎与高性能数据组件中 |

字节跳动、腾讯、Meta 等头部大厂均将「精通 PyTorch + C++/CUDA」列为核心门槛。

**编译栈与算子库**是 2026 年算子岗的实际技能栈，只写「会 CUDA」已不足以区分候选人：

- **Triton**：Python 语法写 GPU Kernel，是当前算子开发的主流入口
- **torch.compile / TorchInductor**：图捕获、融合与代码生成，需能判断 graph break 与重编译代价
- **CUTLASS / CuTe**：GEMM mainloop 与 epilogue 的模板化抽象，高性能算子的复用基座
- **CUDA Graph**：消除 Kernel launch 开销，Decode 阶段的关键手段
- **MLIR / TVM / XLA**：跨后端编译与自动调优，异构与专用加速器方向高频

对应课件：[Triton Kernel 开发](/source/AI-Infra/2-AI系统性能工程/14-TritonKernel开发)、[torch.compile 深度解析](/source/AI-Infra/2-AI系统性能工程/20-torchcompile深度解析)、[编译器栈与算子库](/source/AI-Infra/2-AI系统性能工程/38-编译器栈与算子库-MLIR-TVM-XLA-CUTLASS-CuTe)。

## 3. 大模型训练优化

这是 AI Infra 最核心的方向之一，主要技术要求分四块。

**分布式训练框架**

- **DeepSpeed**（ZeRO-1/2/3、Offload）
- **Megatron-LM**（张量并行、流水线并行）
- **FSDP / FSDP2**（Fully Sharded Data Parallel）
- **3D Parallelism**（DP + TP + PP 组合），进阶需掌握 EP 与 CP 的五维组合
- **TorchTitan** 等新一代原生并行方案

**训练加速技术**

- 混合精度训练（BF16/FP8），含 FP8 缩放策略与溢出回退
- **FlashAttention** 及其变体
- Gradient Checkpoint / Activation Checkpointing，含选择性重计算
- 长序列优化（Ring Attention、DeepSpeed-Ulysses、YaRN/LongRoPE）
- MoE（Mixture of Experts）路由与 Expert Parallel 优化
- 流水线调度进阶：Interleaved 1F1B、Zero Bubble、DualPipe 的计算-通信重叠
- 模型压缩训练：知识蒸馏、结构化剪枝与稀疏化

**集群与数据**

- 万卡级集群训练经验
- 检查点（Checkpoint）策略与故障恢复：异步保存、分布式 Checkpoint、拓扑变化后的重分片恢复
- 慢节点（Straggler）检测与训练健康门禁——「变慢」比「挂掉」更常见也更贵
- 数据加载 pipeline 优化（减少 CPU/GPU 等待）

**容量与工期估算**

- 从参数量、Token 预算、MFU 与集群规模反推训练工期与成本
- 显存分项估算（参数/梯度/优化器/激活/KV）与并行策略选型
- 数量级估算能力是系统设计题的评分核心，不是「猜一个数」

美团、智谱、阶跃星辰等公司的 JD 中，分布式训练经验是「高频 + 硬性」要求。

对应课件：[混合并行](/source/AI-Infra/1-大模型训练优化/06-混合并行)、[ZeRO 原理与实战](/source/AI-Infra/1-大模型训练优化/12-ZeRO原理与实战)、[长上下文训练优化](/source/AI-Infra/1-大模型训练优化/24-长上下文训练优化)、[大规模训练的高可用](/source/AI-Infra/1-大模型训练优化/22-大规模训练的高可用)、[训练容量估算与完成期限规划](/source/AI-Infra/1-大模型训练优化/32-训练容量估算与完成期限规划)。

## 4. 大模型推理优化

2026 年推理优化是 AI Infra 面试的**绝对核心**，考察频率最高。

| 技术方向 | 具体内容 |
|---|---|
| KV Cache 管理 | PagedAttention、Radix Tree、Prefix Caching、KV 量化与多级存储 |
| 批处理策略 | Continuous Batching、Chunked Prefill、Dynamic Batching |
| 量化压缩 | GPTQ、AWQ、FP8/INT8/INT4、SmoothQuant、PTQ 与 QAT 的取舍 |
| 投机解码 | EAGLE-3、P-EAGLE、MTP、Medusa、Lookahead、Diffusion Draft 系 |
| Serving 框架 | vLLM、SGLang、TensorRT-LLM、Triton Inference Server、Dynamo |
| PD 分离 | Prefill-Decode 分离架构设计，含 Attention-FFN 分离与专家放置 |
| 新型负载 | Reasoning 长思考与 Test-Time Scaling、Agentic fan-out、结构化输出、多模态、Compound AI |
| 请求级复用 | 语义缓存（Semantic Cache）、Prompt Cache、命中经济性与误命中风险 |

**投机解码清单已换代**：Medusa/Lookahead 是 2024 年的代表方案，2026 年主流是 EAGLE-3 与原生 MTP 头，以及 DFlash/DFlare/DDTree/DSpark 这类扩散式草稿与树验证路线。面试深挖常落在「接受率、草稿成本与验证批量的盈亏平衡」而非名词复述。

**新型推理负载**已从加分项变成主战场：

- **Reasoning / Test-Time Scaling**：思考预算可控、deadline 与取消传播、无效 Token 的成本归属
- **Agentic Inference**：工具调用 fan-out 带来的内部 QPS 放大、长会话 KV 驻留、burstiness
- **Structured Output**：Grammar/FSM 约束解码、XGrammar、编译成本与命中率盈亏平衡
- **Multimodal**：Encoder 与 LLM 的异构流水、Media Cache、共卡时的 TPOT 放大
- **Compound AI**：Embedding → Reranker → LLM → 工具链的关键路径与重试语义

**推理平台与 Fleet 运营**是「推理平台岗」与「推理引擎岗」的分水岭：

- 模型生命周期与 Model Registry、权重分发与启动关键路径
- 冷启动优化：缓存、Warm Pool、GPU Memory Service
- 异构设备放置、拓扑亲和、GPU Bin Packing 与碎片治理
- SLA-aware Autoscaling、流量预测与 Headroom 容量规划
- Multi-LoRA 热切换、Multi-Model 热冷分层与稀疏流量

面经总结显示：「推理优化是绝对核心，PD 分离、KV Cache 管理、Continuous Batching 等工程架构设计被反复考察」。

对应课件：[KV Cache 性能优化](/source/AI-Infra/2-AI系统性能工程/25-KVCache性能优化)、[模型量化与低精度部署](/source/AI-Infra/2-AI系统性能工程/37-模型量化与低精度部署-PTQ-QAT-GPTQ-AWQ-SmoothQuant)、[推理引擎横向对比与选型](/source/AI-Infra/3-大模型推理优化工程/38-推理引擎横向对比与选型-vLLM-SGLang-TensorRT-LLM-Dynamo)、[Reasoning LLM Serving](/source/AI-Infra/3-大模型推理优化工程/11-ReasoningLLMServing-长思考与Test-TimeScaling)、[Agentic Inference](/source/AI-Infra/3-大模型推理优化工程/12-AgenticInference-工具调用-Fan-out与长会话)。

## 5. 数据工程与后训练

2026 年「后训练 Infra / RL Infra」已是独立招聘方向，不再只是加分项。模型能力差异越来越多来自数据与后训练流水线，而非预训练规模。

**数据供应链**

- 大规模语料处理框架：DataTrove、NeMo Curator、Ray Data、Spark
- 数据湖、资产目录与血缘；来源许可与 Source Registry
- 多格式解析（WARC/HTML/PDF/代码/对话）与证据保留
- 清洗、质量过滤与数据画像；精确/模糊/语义去重与基准去污染
- 领域分类、采样权重与数据课程；DoReMi/RegMix 等混合优化
- Tokenization、样本构造、Packing 与长上下文数据
- 确定性 Sharding/Shuffle、断点续读与数据发布门禁

**后训练数据与算法系统**

- SFT 数据 Schema、Chat Template 与 Loss Mask 的逐 Token 正确性
- 合成指令/响应/推理轨迹与自改进闭环
- 人类偏好、AI Feedback 与 On-policy 偏好数据；标注平台与人工标注运营
- Reward Model、Process Reward 与奖励可靠性（Reward Hacking 治理）
- 离线偏好优化：DPO/IPO/KTO/ORPO/SimPO
- 在线 RL：PPO/GRPO/RLOO/DAPO 与长推理训练
- RLVR、可验证环境、拒绝采样与 Agentic 数据飞轮

**后训练系统工程**

- RLHF 数据流图与分布式控制面；Rollout 引擎、权重同步与重分片
- 同步/异步/Partial Rollout、陈旧度与训练—推理不一致
- 后训练框架选型：veRL、OpenRLHF、TRL、NeMo-Aligner
- 评测体系与基准工程：能力、安全、幻觉与评测 Harness
- 多模态数据工程：图文/视频/音频对齐与跨模态去重

对应课件：[SFT 数据 Schema、Chat Template 与 Loss Mask](/source/AI-Infra/5-数据工程与后训练/19-SFT数据Schema-ChatTemplate与LossMask)、[Rollout 引擎、权重同步、重分片与资源放置](/source/AI-Infra/5-数据工程与后训练/28-Rollout引擎-权重同步-重分片与资源放置)、[同步、异步、Partial Rollout、陈旧度与训练—推理不一致](/source/AI-Infra/5-数据工程与后训练/29-同步-异步-PartialRollout-陈旧度与训练—推理不一致)、[后训练框架选型与工程对比](/source/AI-Infra/5-数据工程与后训练/40-后训练框架选型与工程对比-veRL-OpenRLHF-TRL-NeMo)。

## 6. 系统与底层基础设施

**GPU 与硬件**

- GPU 架构理解（NVIDIA Hopper/Blackwell、昇腾达芬奇核心等）
- 专用加速器架构与选型（TPU、Trainium、自研 NPU）的取舍判据
- 超节点物理组织与内存池：Scale-up 域、NVLink/NVSwitch 拓扑、内存语义与 CXL
- GPU 能耗、功耗墙与数据中心效率：功率封顶、时钟 throttling、PUE、每 Token 能耗
- CUDA 编程与 Kernel 优化
- NCCL 通信优化、RDMA/InfiniBand 网络调优、拥塞控制与远程访问可靠性

**集群调度**

- Kubernetes + GPU 调度（Volcano、Kueue、Kubeflow）
- Slurm、Ray 集群管理，以及二者的边界与协同
- 资源调度与弹性扩缩容、Spot 中断治理

**存储与 I/O**

- 高性能存储（JuiceFS、Alluxio、Ceph）
- 数据格式优化（TFRecord、Parquet、LMDB、WebDataset、Token Bin/Idx）
- 检查点读写优化与制品分发（P2P、缓存加速、Digest 模型）

**性能剖析**

- Nsight Systems/Compute、PyTorch Profiler
- Roofline、排队论、通信模型与 Amdahl 定律的建模能力
- 训练/推理瓶颈分析与优化，区分计算受限、访存受限与通信受限

滴滴 AI Infra 存储方向岗位明确要求「熟悉 Linux 内核文件系统、IO 子系统、分布式存储协议」。

对应课件：[GPU 架构深度解析](/source/AI-Infra/2-AI系统性能工程/05-GPU架构深度解析)、[超节点物理组织与内存池](/source/AI-Infra/2-AI系统性能工程/43-超节点物理组织与内存池)、[GPU 能耗、功耗墙与数据中心效率](/source/AI-Infra/2-AI系统性能工程/39-GPU能耗-功耗墙与数据中心效率)、[数量级估算与系统设计方法论](/source/AI-Infra/2-AI系统性能工程/40-数量级估算与系统设计方法论)。

## 7. AI 平台工程

平台岗的门槛不是「会装 K8s」，而是**能把算力组织成可自助、可配额、可审计的产品能力**。

**声明式 API 与控制面**

- Kubernetes API、控制器模式与 Operator 开发（CRD、Reconcile、状态机、幂等）
- GPU 资源抽象：Device Plugin、CDI、DRA 与设备健康
- GPU 分区与共享：MIG、vGPU、时间切片及其隔离强度差异
- 分布式工作负载 API：JobSet、LeaderWorkerSet 与失败语义
- Kubeflow Trainer V2、KubeRay、KServe 的运行时产品化

**调度、队列与弹性**

- Gang Scheduling 与分布式作业原子准入
- Kueue 队列、配额、公平共享与抢占；Volcano 在线离线混部
- 拓扑感知调度、ResourceFlavor；Slurm 与 K8s 协同
- 弹性容量、Spot、节点自动扩缩与中断时间预算

**交付与供应链**

- 模型注册、制品版本与端到端血缘
- GitOps、环境晋级与渐进式发布（Argo CD/Rollouts）
- 云原生 CI/CD、制品供应链与发布证明（SBOM、Provenance、签名验证）
- 基础设施即代码：Terraform、Crossplane、Cluster API 与环境一致性

**平台产品化**

- 平台需求、用户旅程与「平台即产品」的能力抽象
- 多集群控制面、自助门户（Backstage）与开发者体验
- Agent 任务运行环境与资源调度：沙箱、工具执行、副作用幂等

对应课件：[Kubernetes API、控制器与 Operator 平台模式](/source/AI-Infra/4-AI平台工程/03-KubernetesAPI-控制器与Operator平台模式)、[Kueue 队列、配额、公平共享与抢占](/source/AI-Infra/4-AI平台工程/12-Kueue队列-配额-公平共享与抢占)、[多集群控制面、自助门户与平台最终架构](/source/AI-Infra/4-AI平台工程/30-多集群控制面-自助门户与平台最终架构)。

## 8. 可观测性、SRE 与可靠性

性能剖析（Nsight/Profiler）回答「为什么慢」，生产可观测性回答「现在是否健康、坏了影响谁、能否恢复」。二者是不同能力，JD 中常被混为一谈。

- **统一可观测性**：Metrics/Logs/Traces 三支柱，跨训练、推理、数据与平台平面的共同身份（run_id、request_id、policy_version）
- **资源归因**：GPU 利用率、显存、通信与成本按租户/作业/模型归属，避免「总量正常、个体异常」
- **SLO 与错误预算**：TTFT/TPOT/Goodput 的 SLO 定义、错误预算消耗与发布节奏联动
- **发布可靠性**：Trace、Canary、Drain、隔离与暖回滚；在途请求保护
- **故障演练与自动修复**：故障注入矩阵、RPO/RTO 实测、单领导与双主防护
- **训练与后训练可靠性**：检查点合同、恢复语义（至多一次/至少一次/恰好一次）、陈旧度门禁
- **质量回归**：幻觉率、拒答率、格式正确率与版本漂移的在线门禁——可用性绿色不代表质量合格

对应课件：[AI 平台统一可观测性与资源归因](/source/AI-Infra/4-AI平台工程/26-AI平台统一可观测性与资源归因)、[AI Platform SRE：SLO、故障演练与自动修复](/source/AI-Infra/4-AI平台工程/27-AIPlatformSRE-SLO-故障演练与自动修复)、[Observability 与 Reliability](/source/AI-Infra/3-大模型推理优化工程/29-Observability与Reliability-Trace-Canary-Drain与隔离)。

## 9. 安全、合规与多租户治理

2026 年大厂 JD 已普遍出现「模型服务安全」「数据合规」「多租户隔离」，这一维度从「锦上添花」变成硬门槛。

- **多租户隔离**：租户模型、Namespace 与虚拟控制面、身份联邦与工作负载身份、RBAC 纯加法语义与有效权限计算
- **运行时与网络隔离**：Pod 安全标准、Seccomp/AppArmor、gVisor/Kata、NetworkPolicy 与东西向隔离
- **密钥与凭据管理**：Vault、External Secrets、Secrets Store CSI、最小权限与轮换
- **推理侧在线护栏**：Prompt Injection 与 Jailbreak 检测、输入输出内容过滤、在线 PII、拒答策略与水印
- **数据侧治理**：隐私与版权、投毒与后门检测、数据退出与删除证明、血缘影响传播
- **审计与合规留存**：Audit Policy、事件溯源、留存期、取证与跨租户查询脱敏
- **供应链准入**：签名验证准入、策略即代码、例外审批与策略漂移治理

对应课件：[多租户安全、策略与审计](/source/AI-Infra/4-AI平台工程/28-多租户安全-策略与审计)、[密钥、凭据与秘密管理](/source/AI-Infra/4-AI平台工程/37-密钥-凭据与秘密管理-Vault-ExternalSecrets-轮换)、[推理安全与在线护栏](/source/AI-Infra/3-大模型推理优化工程/37-推理安全与在线护栏-PromptInjection-Jailbreak-内容过滤)、[隐私、安全、版权、投毒与数据退出机制](/source/AI-Infra/5-数据工程与后训练/13-隐私-安全-版权-投毒与数据退出机制)。

## 10. 成本与容量效率

「资源利用率优化」「成本优化」是 JD 高频词，但很少有人说清口径。这一维度的核心是**把工程指标换算成钱，并知道分母是什么**。

- **推理经济学**：Cost per Token、每请求成本、SLO 约束下的全局优化；区分 GPU-ms 与美元口径
- **计量与配额**：Token 计量生命周期（预估/保留/结算/释放）、流式 Usage 与幂等结算、租户有效成本归属
- **GPU FinOps**：容量规划、成本归属、showback/chargeback、闲置与碎片成本
- **效率指标**：MFU/HFU、Goodput（而非裸吞吐）、新鲜有效吞吐（扣除陈旧淘汰）
- **弹性与中断经济学**：Spot 折扣与中断成本、预留与容量块、扩缩容的冷启动代价
- **能耗成本**：每 Token 能耗、功率封顶对吞吐的影响、PUE 与数据中心效率
- **无效工作计入成本**：失败重试、被拒请求、环境作废、重复生成都必须留在分子里

对应课件：[Inference Economics：Cost per Token、SLO 与全局优化](/source/AI-Infra/3-大模型推理优化工程/30-InferenceEconomics-CostperToken-SLO与全局优化)、[GPU FinOps、容量规划与成本归属](/source/AI-Infra/4-AI平台工程/29-GPUFinOps-容量规划与成本归属)、[OpenAI-Compatible AI Gateway：计量、配额与租户治理](/source/AI-Infra/3-大模型推理优化工程/16-OpenAI-CompatibleAIGateway-计量-配额与租户治理)。

## 11. 加分项（差异化竞争力）

| 加分方向 | 说明 |
|---|---|
| 开源贡献 | PyTorch、vLLM、SGLang、DeepSpeed、veRL 等核心框架 PR |
| 异构芯片 | 昇腾、TPU、自研芯片适配经验 |
| 端边云协同 | 端侧压缩与移动端推理、端边云切分与全链路交互时延 |
| 多模态/扩散训练系统 | VLM 与 Diffusion 的并行切分、变长样本与显存特征 |
| 超节点与内存池 | Scale-up 域设计、内存语义互联、CXL 与池化调度 |
| 编译器与自动调优 | MLIR/TVM/XLA 后端、自动调优与算子库贡献 |

注意：Agent Infra、RLHF/RL Infra、多模态推理在 2026 年已进入核心要求（见第 4、5 节），不再适合作为差异化加分项定位。

## 12. 面试考察重点

根据 2026 年最新面经，AI Infra 面试通常包含五类：

1. **系统设计题**（占比最高）：设计百万 QPS 推理服务、长上下文训练基础设施、多租户 GPU 平台。评分核心是**数量级估算**——显存/算力/带宽/工期/成本能否自洽推导，而非组件名词堆叠。
2. **手撕代码**：CUDA Kernel、并行算法、分布式通信逻辑、PagedAttention 的块表管理。
3. **工程深挖**：vLLM/SGLang 源码理解、PagedAttention 实现细节、量化原理与校准、投机解码接受率与盈亏平衡。
4. **性能分析**：给定训练日志或 Profiler 输出定位瓶颈并提出优化方案，需说明证据与单变量对照。
5. **评测与质量门禁**：如何证明优化没有损害质量——基线、护栏指标、污染隔离、多种子与置信区间。

一个反复出现的失分点：把「更快」当成结论，却说不清分母（裸吞吐 vs Goodput）、口径（GPU-ms vs 美元）与护栏（质量/安全/成本）。

对应课件：[数量级估算与系统设计方法论](/source/AI-Infra/2-AI系统性能工程/40-数量级估算与系统设计方法论)、[模型架构资源消耗量化](/source/AI-Infra/2-AI系统性能工程/41-模型架构资源消耗量化)、[LLM 评测体系与基准工程](/source/AI-Infra/5-数据工程与后训练/37-LLM评测体系与基准工程-能力-安全-幻觉-harness)。

## 13. 能力分级与学习路径

### 13.1 三级能力门槛

| 级别 | 判定标准 | 典型证据 |
|---|---|---|
| 必备 | 能独立跑通并解释一条完整链路 | 单卡/多卡训练与推理基准、显存与吞吐口径正确、能定位常见瓶颈 |
| 进阶 | 能在约束下做取舍并证明收益 | 单变量对照实验、SLO 与成本护栏、可复现 benchmark、故障恢复演练 |
| 专家 | 能设计系统并承担长期运营 | 万卡训练或生产推理平台、控制面与恢复语义设计、开源贡献、跨团队平台产品 |

### 13.2 技能维度 → 课件映射

| 能力维度 | 主题 | 代表篇目 | 综合项目 |
|---|---|---|---|
| 并行与显存 | 一 | [混合并行](/source/AI-Infra/1-大模型训练优化/06-混合并行)、[ZeRO](/source/AI-Infra/1-大模型训练优化/12-ZeRO原理与实战)、[显存占用分析](/source/AI-Infra/1-大模型训练优化/11-大模型显存占用分析) | [DeepSpeed Megatron 7B 分布式训练](/source/AI-Infra/1-大模型训练优化/27-附录1-项目一——基于DeepSpeedMegatron完成一个7B模型的分布式训练) |
| 通信与集群 | 一 / 二 | [NCCL 深度剖析](/source/AI-Infra/1-大模型训练优化/09-NCCL深度剖析与调优)、[NVLink 与集群互联](/source/AI-Infra/2-AI系统性能工程/08-NVLink与AI集群互联) | [千卡通信瓶颈分析](/source/AI-Infra/1-大模型训练优化/29-附录3-项目三——模拟千卡集群场景下的通信瓶颈分析与优化方案设计) |
| 算子与编译栈 | 二 | [CUDA 编程模型](/source/AI-Infra/2-AI系统性能工程/10-CUDA编程模型)、[Triton Kernel](/source/AI-Infra/2-AI系统性能工程/14-TritonKernel开发)、[编译器栈与算子库](/source/AI-Infra/2-AI系统性能工程/38-编译器栈与算子库-MLIR-TVM-XLA-CUTLASS-CuTe) | [CUDA Kernel 优化项目](/source/AI-Infra/2-AI系统性能工程/30-CUDAKernel优化项目) |
| 性能方法论 | 二 | [性能指标体系](/source/AI-Infra/2-AI系统性能工程/02-AI系统性能指标体系)、[数量级估算](/source/AI-Infra/2-AI系统性能工程/40-数量级估算与系统设计方法论) | [7B 训练性能 Benchmark](/source/AI-Infra/2-AI系统性能工程/32-7B模型训练性能Benchmark) |
| 推理引擎内核 | 二 / 三 | [KV Cache](/source/AI-Infra/2-AI系统性能工程/25-KVCache性能优化)、[Continuous Batching](/source/AI-Infra/2-AI系统性能工程/24-ContinuousBatching与Scheduler优化)、[PD 分离](/source/AI-Infra/2-AI系统性能工程/27-DisaggregatedInference架构) | [vLLM 推理优化](/source/AI-Infra/2-AI系统性能工程/33-vLLM推理优化)、[Disaggregated Inference 设计](/source/AI-Infra/2-AI系统性能工程/35-DisaggregatedInference系统设计) |
| 生成加速 | 三 | [EAGLE-3](/source/AI-Infra/3-大模型推理优化工程/03-EAGLE-3-Training-TimeTest与直接Token预测)、[MTP Serving](/source/AI-Infra/3-大模型推理优化工程/05-MTPServing-原生多Token预测头的部署) | [新一代 Speculator Benchmark](/source/AI-Infra/3-大模型推理优化工程/31-新一代SpeculatorBenchmark) |
| 新型负载 | 三 | [Reasoning Serving](/source/AI-Infra/3-大模型推理优化工程/11-ReasoningLLMServing-长思考与Test-TimeScaling)、[Agentic Inference](/source/AI-Infra/3-大模型推理优化工程/12-AgenticInference-工具调用-Fan-out与长会话)、[Structured Output](/source/AI-Infra/3-大模型推理优化工程/13-StructuredOutputServing-Grammar-FSM与XGrammar) | [新型推理工作负载基准平台](/source/AI-Infra/3-大模型推理优化工程/32-新型推理工作负载基准平台) |
| Gateway 与 Fleet | 三 | [AI Gateway](/source/AI-Infra/3-大模型推理优化工程/16-OpenAI-CompatibleAIGateway-计量-配额与租户治理)、[冷启动优化](/source/AI-Infra/3-大模型推理优化工程/23-ColdStartOptimization-缓存-WarmPool与GPUMemoryService)、[Autoscaling](/source/AI-Infra/3-大模型推理优化工程/27-LLMAutoscaling-Queue-Token与SLA-awarePlanner) | [生产级 AI Gateway](/source/AI-Infra/3-大模型推理优化工程/33-生产级AIGateway与SmartRouter)、[GPU Fleet Planner](/source/AI-Infra/3-大模型推理优化工程/35-GPUFleetPlanner与Autoscaler) |
| 平台底座与调度 | 四 | [Operator 平台模式](/source/AI-Infra/4-AI平台工程/03-KubernetesAPI-控制器与Operator平台模式)、[Kueue](/source/AI-Infra/4-AI平台工程/12-Kueue队列-配额-公平共享与抢占)、[JobSet/LWS](/source/AI-Infra/4-AI平台工程/17-分布式AI工作负载API-JobSet-LeaderWorkerSet与失败语义) | [GPU Ready 集群基线](/source/AI-Infra/4-AI平台工程/31-GPUReadyKubernetes集群基线)、[多租户配额平台](/source/AI-Infra/4-AI平台工程/32-多租户GPU批处理与配额平台) |
| 交付与供应链 | 四 | [模型注册与血缘](/source/AI-Infra/4-AI平台工程/22-模型注册-制品版本与端到端血缘)、[GitOps](/source/AI-Infra/4-AI平台工程/24-GitOps-环境晋级与渐进式发布)、[CI/CD 与发布证明](/source/AI-Infra/4-AI平台工程/25-云原生CICD-制品供应链与发布证明) | [模型持续交付与安全发布平台](/source/AI-Infra/4-AI平台工程/34-模型持续交付与安全发布平台) |
| 数据供应链 | 五 | [数据湖与血缘](/source/AI-Infra/5-数据工程与后训练/03-面向训练的数据湖-资产目录与血缘架构)、[DataTrove/Ray/Spark](/source/AI-Infra/5-数据工程与后训练/06-DataTrove-NeMoCurator-Ray与Spark数据流)、[去重](/source/AI-Infra/5-数据工程与后训练/11-精确-模糊-段落与子串去重) | [从 Common Crawl 到可训练语料](/source/AI-Infra/5-数据工程与后训练/31-从CommonCrawl到可训练语料) |
| 后训练与 RL | 五 | [SFT Schema 与 Loss Mask](/source/AI-Infra/5-数据工程与后训练/19-SFT数据Schema-ChatTemplate与LossMask)、[PPO/GRPO 家族](/source/AI-Infra/5-数据工程与后训练/25-PPO-GRPO-RLOO-DAPO与长推理训练)、[RLVR 与 Agentic 飞轮](/source/AI-Infra/5-数据工程与后训练/26-RLVR-环境-拒绝采样与Agentic数据飞轮) | [可恢复的异步 Agentic RL 平台](/source/AI-Infra/5-数据工程与后训练/36-可恢复的异步AgenticRL后训练平台) |
| 可观测与 SRE | 三 / 四 / 五 | [统一可观测性](/source/AI-Infra/4-AI平台工程/26-AI平台统一可观测性与资源归因)、[Platform SRE](/source/AI-Infra/4-AI平台工程/27-AIPlatformSRE-SLO-故障演练与自动修复) | [SRE、安全与 FinOps 控制台](/source/AI-Infra/4-AI平台工程/35-AIPlatformSRE-安全与FinOps控制台) |
| 安全与合规 | 三 / 四 / 五 | [多租户安全](/source/AI-Infra/4-AI平台工程/28-多租户安全-策略与审计)、[在线护栏](/source/AI-Infra/3-大模型推理优化工程/37-推理安全与在线护栏-PromptInjection-Jailbreak-内容过滤)、[数据退出机制](/source/AI-Infra/5-数据工程与后训练/13-隐私-安全-版权-投毒与数据退出机制) | [企业级自助 AI 平台](/source/AI-Infra/4-AI平台工程/36-企业级自助AI平台) |
| 成本与容量 | 三 / 四 | [Inference Economics](/source/AI-Infra/3-大模型推理优化工程/30-InferenceEconomics-CostperToken-SLO与全局优化)、[GPU FinOps](/source/AI-Infra/4-AI平台工程/29-GPUFinOps-容量规划与成本归属) | [生产级 LLM Inference Platform](/source/AI-Infra/3-大模型推理优化工程/36-生产级LLMInferencePlatform) |

### 13.3 按方向的推荐路径

- **训练 Infra**：主题一 00–25 → 主题二 05–18 → 主题一 26–29 项目 → 主题四 11–19（平台侧协作面）
- **推理 Infra**：主题二 23–28 → 主题三 02–20 → 主题三 21–30 → 主题三 31–36 项目
- **平台 Infra**：主题四 03–16 → 17–25 → 26–30 → 31–36 项目 → 主题三 24–28（推理平台协作面）
- **数据与后训练 Infra**：主题五 01–17 → 18–26 → 27–30 → 31–36 项目 → 主题一 23、主题三 11–12
- **异构与内核**：主题二 05–14 → 38–43 → 主题一 16–17、25 → 主题二 29–30 项目

## 14. 薪资参考（2026 年）

| 经验 | 年薪范围 |
|---|---|
| 校招 / 1–3 年 | 40–80 万（大厂专项计划可达 100 万+） |
| 3–5 年 | 80–150 万 |
| 5 年+ 资深/专家 | 150–300 万+ |

社招 AI Infra 工程师年薪普遍在 80–120 万区间，头部大厂可达 150 万以上。

**口径说明**：上表为公开渠道汇总的区间，未区分 base 与 total（含股票/签字费）、未区分地域与职级体系，也未区分方向稀缺度（推理与后训练方向通常高于通用平台方向）。实际 offer 受面试评级、股票归属周期与业务预算影响极大，区间只宜用于定位量级，不宜作为谈判锚点。

## 写在最后

AI Infra 是一个「交叉学科」岗位，要求候选人同时具备**深度学习算法理解**、**分布式系统工程能力**和**底层性能优化技能**。2026 年行业最稀缺的人才画像为：**能手写 CUDA Kernel、深入理解 vLLM 源码、有万卡集群训练经验**的工程师；同时，**能把数据与后训练流水线做成可复现系统**、**能把算力做成可自助可审计的平台产品**这两类画像的稀缺度正在快速上升。

技能表只是索引，真正的门槛是「可验证的证据」：可复现的 benchmark、单变量对照的优化结论、能恢复的故障演练、能归属的成本账本。本系列五个主题与 28 个综合项目正是按这个标准组织的。

下一篇：[大模型训练的时代背景与挑战](/source/AI-Infra/1-大模型训练优化/01-大模型训练的时代背景与挑战)。