# Model Registry 与 Inference Deployment 生命周期

## 1. 课程定位

本文回答的问题是“如何把不可变模型制品、运行配置和部署状态组成可回滚发布单元？”。分析从 Model Registry 与不可变模型制品的关系开始，随后落到计算模型、实现路径和发布验收。Model Registry 与 Inference Deployment 生命周期会同时受到工作负载、模型修订、运行时调度、显存容量、并发状态与服务等级约束。正文会把相关机制还原成 Model Registry 等可观察实体，再据此划定收益条件与额外成本。

证据分为机制模拟和真实 CUDA 测量。前者用可控变量观察 Model Registry 怎样影响不可变模型制品，后者把框架、Kernel、内存和硬件成本计入结果。两条路径使用不同来源标签，并保留 Model Registry 相关环境与限制；参数组合可以随版本改变，证据链仍要支持复现、定位和回退。

## 2. 学习目标

1. 准确解释 Model Registry、不可变模型制品和推理运行配置之间的状态与资源关系。
2. 使用“deployable_revision = hash(model, tokenizer, template, engine_config, capability_metadata)”建立可计算的收益边界并解释全部变量。
3. 围绕制品校验时间、部署就绪时间、Canary 成功率和发布失败率设计可复现实验。
4. 识别同一标签被覆盖导致不可复现、模型与 Tokenizer 或模板错配和进程健康但真实推理失败等典型失败模式。
5. 对“如何把不可变模型制品、运行配置和部署状态组成可回滚发布单元？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 Model Registry 与 Inference Deployment 生命周期需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Model Registry 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Model Registry 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Model Registry 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Model Registry 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

评估 Model Registry 与 Inference Deployment 生命周期时，先不要回答“打开以后能快多少”。需要固定模型与修订、输入输出长度分布、到达过程、并发、采样、缓存状态、制品校验时间口径、服务等级和硬件环境，再评审“定义制品与配置边界”和“选择摘要和签名策略”。这些条件共同决定收益、成本和资源竞争。

分析范围由八个可观察概念组成：Model Registry、不可变模型制品、推理运行配置、Deployment Revision、能力元数据、发布状态机、Canary、回滚单元。算法层的变化会经运行时和平台层传到暖修订成本与发布失败率。每个概念都像 Model Registry 一样绑定具体状态、责任边界、观测字段和故障表现。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：上线的是不可变 Revision + 可回滚 Deployment，而不是一个“模型文件名”

只有把模型、Speculator、Adapter、量化配置和 Serving 配置都纳入可追踪版本关系，平台才能安全灰度与回滚。

### 3.1 Model Registry

保存“模型是什么”：

```text
model_id
revision
architecture
precision
tokenizer
context_limit
compatibility
status
```

### 3.2 Artifact Store

保存“模型文件在哪里”：

```text
s3://...
oss://...
local cache
shared filesystem
```

### 3.3 Deployment

保存“模型现在如何运行”：

```text
replica count
GPU type
parallel group
runtime image
router config
SLO tier
```

同一个 model revision 可以有多个 Deployment。

### 为什么 revision 必须不可变

最危险的做法：

```text
model/latest/
```

今天和明天指向不同权重，却复用同一个缓存/Speculator/Adapter 元数据。

生产上更推荐 content/revision immutable：

```text
model=qwen-x
revision=sha256:abcd...
```

Alias 负责可变：

```text
chat-pro → revision A
```

升级时切 Alias，不修改旧 Artifact。

### Compatibility Graph

一个模型并不是孤立文件：

```text
Target Model
├─ Tokenizer
├─ Quantization Config
├─ Chat Template
├─ LoRA Adapters
├─ Speculator
├─ Structured Output Backend Compatibility
└─ Runtime Version
```

可以把兼容关系看成图。

例如 Speculator 只有在：

$$TargetRevision=R_t$$

且：

$$RuntimeVersion\ge V_{min}$$

时可启用。

否则 Router/Controller 应拒绝部署，而不是运行到一半才报错。

### Deployment 状态机

```text
REGISTERED
   ↓
STAGING
   ↓
LOADING
   ↓
WARMING
   ↓
READY
   ↓
DRAINING
   ↓
STOPPED / RETIRED
```

### REGISTERED

Registry 元数据存在，但没有资源。

### STAGING

分配节点、准备镜像/权重。

### LOADING

权重正在进入本地/Host/GPU。

### WARMING

Runtime 初始化、必要 Graph/Kernel/Cache 预热。

### READY

才可以接受生产流量。

### DRAINING

停止接收新请求，但让已有长请求完成或在 Deadline 后终止。

### Readiness 与 Liveness

### Liveness

进程是否还活着。

### Readiness

是否真的能接请求。

一个 Pod 已经 `Running`，但模型还在下载 100GB 权重：

```text
liveness = true
readiness = false
```

如果 Router 只看进程存活就导流，会让首批用户直接撞到 loading 状态。

### Model Manifest

内部 Registry 可以有 Manifest，但对外交付的实验包不需要暴露平台内部 manifest。

一个生产 manifest 示例：

```yaml
model_id: reasoning-pro
revision: r20260812
artifacts:
  weights: ...
  tokenizer: ...
precision: bf16
runtime:
  type: vllm
  min_version: ...
resources:
  gpu_memory_gib: 72
compatibility:
  speculator: dflash-r3
  adapters:
    - finance-v2
```

重点是可机读，Control Plane 才能自动验证。

### 发布与回滚

## 写在最后

发布单元确定之后，真正的启动关键路径落在权重如何到达节点。下一篇：[Weight Distribution：大模型权重分发与启动关键路径](/source/AI-Infra/3-大模型推理优化工程/22-WeightDistribution-大模型权重分发与启动关键路径)。