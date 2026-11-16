# 主题三 大模型推理优化工程

从一次推理请求走到一套生产级推理平台：先统一三个平面与证据口径，再深入下一代生成加速（EAGLE-3、P-EAGLE、MTP、DFlash 系）、新型推理负载（reasoning / agentic / structured / multimodal / compound）、Gateway 与路由、多模型与多 LoRA、权重分发与冷启动、GPU Fleet 控制面与推理经济学，最后以六个综合项目收口。

> 内容整理自开源书稿 [深入理解 AI Infra：量化分析与系统设计](https://github.com/bojieli/ai-infra-book)，作为参考笔记。

## 目录

### 导览与工程模型

- [00 课程导览](/source/AI-Infra/3-大模型推理优化工程/00-课程导览)
- [01 从推理引擎性能到生产级推理平台](/source/AI-Infra/3-大模型推理优化工程/01-从推理引擎性能到生产级推理平台)
- [38 推理引擎横向对比与选型：vLLM、SGLang、TensorRT-LLM 与 Dynamo](/source/AI-Infra/3-大模型推理优化工程/38-推理引擎横向对比与选型-vLLM-SGLang-TensorRT-LLM-Dynamo)

### 下一代生成加速与 Speculator 工程

- [02 经典 Speculative Decoding 之后的性能边界](/source/AI-Infra/3-大模型推理优化工程/02-经典SpeculativeDecoding之后的性能边界)
- [03 EAGLE-3：Training-Time Test 与直接 Token 预测](/source/AI-Infra/3-大模型推理优化工程/03-EAGLE-3-Training-TimeTest与直接Token预测)
- [04 P-EAGLE：并行 Drafter 与长上下文训练](/source/AI-Infra/3-大模型推理优化工程/04-P-EAGLE-并行Drafter与长上下文训练)
- [05 MTP Serving：原生多 Token 预测头的部署](/source/AI-Infra/3-大模型推理优化工程/05-MTPServing-原生多Token预测头的部署)
- [06 DFlash：Block Diffusion Speculative Decoding](/source/AI-Infra/3-大模型推理优化工程/06-DFlash-BlockDiffusionSpeculativeDecoding)
- [07 DFlare：Layer-wise Fusion 与 Drafter 扩容](/source/AI-Infra/3-大模型推理优化工程/07-DFlare-Layer-wiseFusion与Drafter扩容)
- [08 DDTree：Diffusion Draft Tree 与树验证](/source/AI-Infra/3-大模型推理优化工程/08-DDTree-DiffusionDraftTree与树验证)
- [09 DSpark：置信度调度与负载感知验证](/source/AI-Infra/3-大模型推理优化工程/09-DSpark-置信度调度与负载感知验证)
- [10 Speculator 工程化：训练、评测、发布与漂移](/source/AI-Infra/3-大模型推理优化工程/10-Speculator工程化-训练-评测-发布与漂移)

### 新型推理工作负载

- [11 Reasoning LLM Serving：长思考与 Test-Time Scaling](/source/AI-Infra/3-大模型推理优化工程/11-ReasoningLLMServing-长思考与Test-TimeScaling)
- [12 Agentic Inference：工具调用、Fan-out 与长会话](/source/AI-Infra/3-大模型推理优化工程/12-AgenticInference-工具调用-Fan-out与长会话)
- [13 Structured Output Serving：Grammar、FSM 与 XGrammar](/source/AI-Infra/3-大模型推理优化工程/13-StructuredOutputServing-Grammar-FSM与XGrammar)
- [14 Multimodal Serving：Encoder、Media Cache 与异构流水](/source/AI-Infra/3-大模型推理优化工程/14-MultimodalServing-Encoder-MediaCache与异构流水)
- [15 Compound AI Serving：Embedding、Reranker、LLM 与工具链](/source/AI-Infra/3-大模型推理优化工程/15-CompoundAIServing-Embedding-Reranker-LLM与工具链)

### Gateway、路由与模型多路复用

- [16 OpenAI-Compatible AI Gateway：计量、配额与租户治理](/source/AI-Infra/3-大模型推理优化工程/16-OpenAI-CompatibleAIGateway-计量-配额与租户治理)
- [17 Distributed Replica Routing：负载、队列与预计完成时间](/source/AI-Infra/3-大模型推理优化工程/17-DistributedReplicaRouting-负载-队列与预计完成时间)
- [18 Prefix、Session 与 KV-Locality Routing](/source/AI-Infra/3-大模型推理优化工程/18-Prefix-Session与KV-LocalityRouting)
- [19 Multi-LoRA Serving：Adapter 缓存与热切换](/source/AI-Infra/3-大模型推理优化工程/19-Multi-LoRAServing-Adapter缓存与热切换)
- [20 Multi-Model Serving：热冷模型与稀疏流量](/source/AI-Infra/3-大模型推理优化工程/20-Multi-ModelServing-热冷模型与稀疏流量)
- [39 语义缓存与请求级复用：Semantic Cache 与 Prompt Cache](/source/AI-Infra/3-大模型推理优化工程/39-语义缓存与请求级复用-SemanticCache-PromptCache)

### 分布式推理与端边云部署

- [40 Attention-FFN 分离与专家放置](/source/AI-Infra/3-大模型推理优化工程/40-Attention-FFN分离与专家放置)
- [41 KV 分布、多级存储与状态恢复](/source/AI-Infra/3-大模型推理优化工程/41-KV分布-多级存储与状态恢复)
- [42 端边云协同与全链路交互时延](/source/AI-Infra/3-大模型推理优化工程/42-端边云协同与全链路交互时延)

### 生命周期、启动与 GPU Fleet

- [21 Model Registry 与 Inference Deployment 生命周期](/source/AI-Infra/3-大模型推理优化工程/21-ModelRegistry与InferenceDeployment生命周期)
- [22 Weight Distribution：大模型权重分发与启动关键路径](/source/AI-Infra/3-大模型推理优化工程/22-WeightDistribution-大模型权重分发与启动关键路径)
- [23 Cold Start Optimization：缓存、Warm Pool 与 GPU Memory Service](/source/AI-Infra/3-大模型推理优化工程/23-ColdStartOptimization-缓存-WarmPool与GPUMemoryService)
- [24 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo](/source/AI-Infra/3-大模型推理优化工程/24-LLMServingControlPlane-RayServe-KServe与Dynamo)
- [25 Heterogeneous GPU Placement：异构设备与拓扑亲和性](/source/AI-Infra/3-大模型推理优化工程/25-HeterogeneousGPUPlacement-异构设备与拓扑亲和性)
- [26 GPU Bin Packing：并行组、碎片与放置算法](/source/AI-Infra/3-大模型推理优化工程/26-GPUBinPacking-并行组-碎片与放置算法)
- [27 LLM Autoscaling：Queue、Token 与 SLA-aware Planner](/source/AI-Infra/3-大模型推理优化工程/27-LLMAutoscaling-Queue-Token与SLA-awarePlanner)
- [28 Capacity Planning：流量预测、Headroom 与 GPU Fleet](/source/AI-Infra/3-大模型推理优化工程/28-CapacityPlanning-流量预测-Headroom与GPUFleet)

### 可靠性与推理经济学

- [29 Observability 与 Reliability：Trace、Canary、Drain 与隔离](/source/AI-Infra/3-大模型推理优化工程/29-Observability与Reliability-Trace-Canary-Drain与隔离)
- [30 Inference Economics：Cost per Token、SLO 与全局优化](/source/AI-Infra/3-大模型推理优化工程/30-InferenceEconomics-CostperToken-SLO与全局优化)
- [37 推理安全与在线护栏：Prompt Injection、Jailbreak 与内容过滤](/source/AI-Infra/3-大模型推理优化工程/37-推理安全与在线护栏-PromptInjection-Jailbreak-内容过滤)

### 综合项目

- [31 新一代 Speculator Benchmark](/source/AI-Infra/3-大模型推理优化工程/31-新一代SpeculatorBenchmark)
- [32 新型推理工作负载基准平台](/source/AI-Infra/3-大模型推理优化工程/32-新型推理工作负载基准平台)
- [33 生产级 AI Gateway 与 Smart Router](/source/AI-Infra/3-大模型推理优化工程/33-生产级AIGateway与SmartRouter)
- [34 Multi-Tenant、Multi-Model 与 Multi-LoRA Serving](/source/AI-Infra/3-大模型推理优化工程/34-Multi-Tenant-Multi-Model与Multi-LoRAServing)
- [35 GPU Fleet Planner 与 Autoscaler](/source/AI-Infra/3-大模型推理优化工程/35-GPUFleetPlanner与Autoscaler)
- [36 生产级 LLM Inference Platform](/source/AI-Infra/3-大模型推理优化工程/36-生产级LLMInferencePlatform)
