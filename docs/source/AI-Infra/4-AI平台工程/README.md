# 主题四 AI Platform Engineering

以「平台即产品」为主线的 AI 基础设施工程笔记：从平台判断框架与用户旅程，到 Kubernetes 与 GPU 资源抽象、调度与队列、训练与推理工作负载 API、模型交付与供应链、可观测与 SRE、安全与 FinOps、多集群自助门户，最后以六个综合项目收口。

> 内容整理自开源书稿 [深入理解 AI Infra：量化分析与系统设计](https://github.com/bojieli/ai-infra-book)，作为参考笔记。

## 目录

### 导览与平台产品

- [00 课程导读](/source/AI-Infra/4-AI平台工程/00-课程导读)
- [01 AI Platform Engineering 全景与参考架构](/source/AI-Infra/4-AI平台工程/01-AIPlatformEngineering全景与参考架构)
- [02 平台需求、用户旅程与平台即产品](/source/AI-Infra/4-AI平台工程/02-平台需求-用户旅程与平台即产品)

### Kubernetes 与 GPU 资源底座

- [03 Kubernetes API、控制器与 Operator 平台模式](/source/AI-Infra/4-AI平台工程/03-KubernetesAPI-控制器与Operator平台模式)
- [04 面向 AI 工作负载的 Kubernetes 基础](/source/AI-Infra/4-AI平台工程/04-面向AI工作负载的Kubernetes基础)
- [05 GPU 节点软件栈与 NVIDIA GPU Operator](/source/AI-Infra/4-AI平台工程/05-GPU节点软件栈与NVIDIAGPUOperator)
- [06 GPU 资源抽象：Device Plugin、CDI、DRA 与设备健康](/source/AI-Infra/4-AI平台工程/06-GPU资源抽象-DevicePlugin-CDI-DRA与设备健康)
- [07 GPU 分区、共享与多租户隔离](/source/AI-Infra/4-AI平台工程/07-GPU分区-共享与多租户隔离)
- [08 AI 集群高性能网络与拓扑](/source/AI-Infra/4-AI平台工程/08-AI集群高性能网络与拓扑)
- [39 数据中心网络远程访问与拥塞可靠性](/source/AI-Infra/4-AI平台工程/39-数据中心网络远程访问与拥塞可靠性)
- [09 AI 数据与模型制品的存储和分发](/source/AI-Infra/4-AI平台工程/09-AI数据与模型制品的存储和分发)
- [38 平台基础设施即代码：Terraform、Crossplane 与环境一致性](/source/AI-Infra/4-AI平台工程/38-平台基础设施即代码-Terraform-Crossplane-环境一致性)

### 调度、队列与弹性容量

- [10 Kubernetes 调度器与 AI 资源碎片](/source/AI-Infra/4-AI平台工程/10-Kubernetes调度器与AI资源碎片)
- [11 Gang Scheduling 与分布式作业原子准入](/source/AI-Infra/4-AI平台工程/11-GangScheduling与分布式作业原子准入)
- [12 Kueue 队列、配额、公平共享与抢占](/source/AI-Infra/4-AI平台工程/12-Kueue队列-配额-公平共享与抢占)
- [13 Volcano 调度策略与在线离线混部](/source/AI-Infra/4-AI平台工程/13-Volcano调度策略与在线离线混部)
- [14 拓扑感知调度、ResourceFlavor 与 DRA](/source/AI-Infra/4-AI平台工程/14-拓扑感知调度-ResourceFlavor与DRA)
- [15 弹性容量、Spot、节点自动扩缩与中断治理](/source/AI-Infra/4-AI平台工程/15-弹性容量-Spot-节点自动扩缩与中断治理)
- [16 Slurm GPU 集群与 Kubernetes 的边界和协同](/source/AI-Infra/4-AI平台工程/16-SlurmGPU集群与Kubernetes的边界和协同)
- [40 Agent 任务运行环境与资源调度](/source/AI-Infra/4-AI平台工程/40-Agent任务运行环境与资源调度)

### AI 工作负载与 ML 生命周期

- [17 分布式 AI 工作负载 API：JobSet、LeaderWorkerSet 与失败语义](/source/AI-Infra/4-AI平台工程/17-分布式AI工作负载API-JobSet-LeaderWorkerSet与失败语义)
- [18 Kubeflow 平台组件、Profiles 与多用户隔离](/source/AI-Infra/4-AI平台工程/18-Kubeflow平台组件-Profiles与多用户隔离)
- [19 Kubeflow Trainer V2 与训练运行时产品化](/source/AI-Infra/4-AI平台工程/19-KubeflowTrainerV2与训练运行时产品化)
- [20 KubeRay：RayCluster、RayJob、RayService 与多层扩缩](/source/AI-Infra/4-AI平台工程/20-KubeRay-RayCluster-RayJob-RayService与多层扩缩)
- [21 Kubeflow Pipelines V2、Katib 与实验工作流](/source/AI-Infra/4-AI平台工程/21-KubeflowPipelinesV2-Katib与实验工作流)
- [22 模型注册、制品版本与端到端血缘](/source/AI-Infra/4-AI平台工程/22-模型注册-制品版本与端到端血缘)

### 模型交付与发布治理

- [23 KServe 模型服务控制面与声明式生命周期](/source/AI-Infra/4-AI平台工程/23-KServe模型服务控制面与声明式生命周期)
- [24 GitOps、环境晋级与渐进式发布](/source/AI-Infra/4-AI平台工程/24-GitOps-环境晋级与渐进式发布)
- [25 云原生 CI/CD、制品供应链与发布证明](/source/AI-Infra/4-AI平台工程/25-云原生CICD-制品供应链与发布证明)

### 可观测性、SRE、安全与 FinOps

- [26 AI 平台统一可观测性与资源归因](/source/AI-Infra/4-AI平台工程/26-AI平台统一可观测性与资源归因)
- [27 AI Platform SRE：SLO、故障演练与自动修复](/source/AI-Infra/4-AI平台工程/27-AIPlatformSRE-SLO-故障演练与自动修复)
- [28 多租户安全、策略与审计](/source/AI-Infra/4-AI平台工程/28-多租户安全-策略与审计)
- [29 GPU FinOps、容量规划与成本归属](/source/AI-Infra/4-AI平台工程/29-GPUFinOps-容量规划与成本归属)
- [37 密钥、凭据与秘密管理：Vault、External Secrets 与轮换](/source/AI-Infra/4-AI平台工程/37-密钥-凭据与秘密管理-Vault-ExternalSecrets-轮换)

### 多集群与自助平台

- [30 多集群控制面、自助门户与平台最终架构](/source/AI-Infra/4-AI平台工程/30-多集群控制面-自助门户与平台最终架构)

### 综合项目

- [31 GPU Ready Kubernetes 集群基线](/source/AI-Infra/4-AI平台工程/31-GPUReadyKubernetes集群基线)
- [32 多租户 GPU 批处理与配额平台](/source/AI-Infra/4-AI平台工程/32-多租户GPU批处理与配额平台)
- [33 声明式分布式训练平台](/source/AI-Infra/4-AI平台工程/33-声明式分布式训练平台)
- [34 模型持续交付与安全发布平台](/source/AI-Infra/4-AI平台工程/34-模型持续交付与安全发布平台)
- [35 AI Platform SRE、安全与 FinOps 控制台](/source/AI-Infra/4-AI平台工程/35-AIPlatformSRE-安全与FinOps控制台)
- [36 企业级自助 AI 平台](/source/AI-Infra/4-AI平台工程/36-企业级自助AI平台)
