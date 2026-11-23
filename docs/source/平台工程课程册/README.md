# 平台工程课程册

按课程原课次顺序整理的实验笔记：每课一篇，先讲机制，再给实验闭环（Fixture/真实路径、输入输出与验收），最后落判读纪律。与 [AI Infra 主题笔记](/source/AI-Infra/README) 的区别在于组织方式——主题笔记按知识域重组，本册保留课次顺序，聚焦「实验怎么做、结论怎么判」。

## 目录

- [AI-Platform-Engineering-全景与参考架构](/source/平台工程课程册/01-AI-Platform-Engineering-全景与参考架构)
- [平台需求、用户旅程与平台即产品](/source/平台工程课程册/02-平台需求、用户旅程与平台即产品)
- [Kubernetes-API、控制器与-Operator-平台模式](/source/平台工程课程册/03-Kubernetes-API、控制器与-Operator-平台模式)
- [面向-AI-工作负载的-Kubernetes-基础](/source/平台工程课程册/04-面向-AI-工作负载的-Kubernetes-基础)
- [GPU-节点软件栈与-NVIDIA-GPU-Operator](/source/平台工程课程册/05-GPU-节点软件栈与-NVIDIA-GPU-Operator)
- [GPU-资源抽象：Device-Plugin、CDI、DRA-与设备健康](/source/平台工程课程册/06-GPU-资源抽象：Device-Plugin、CDI、DRA-与设备健康)
- [GPU-分区、共享与多租户隔离](/source/平台工程课程册/07-GPU-分区、共享与多租户隔离)
- [AI-集群高性能网络与拓扑](/source/平台工程课程册/08-AI-集群高性能网络与拓扑)
- [AI-数据与模型制品的存储和分发](/source/平台工程课程册/09-AI-数据与模型制品的存储和分发)
- [Kubernetes-调度器与-AI-资源碎片](/source/平台工程课程册/10-Kubernetes-调度器与-AI-资源碎片)
- [Gang-Scheduling-与分布式作业原子准入](/source/平台工程课程册/11-Gang-Scheduling-与分布式作业原子准入)
- [Kueue-队列、配额、公平共享与抢占](/source/平台工程课程册/12-Kueue-队列、配额、公平共享与抢占)
- [Volcano-调度策略与在线离线混部](/source/平台工程课程册/13-Volcano-调度策略与在线离线混部)
- [拓扑感知调度、ResourceFlavor-与-DRA](/source/平台工程课程册/14-拓扑感知调度、ResourceFlavor-与-DRA)
- [弹性容量、Spot、节点自动扩缩与中断治理](/source/平台工程课程册/15-弹性容量、Spot、节点自动扩缩与中断治理)
- [Slurm-GPU-集群与-Kubernetes-的边界和协同](/source/平台工程课程册/16-Slurm-GPU-集群与-Kubernetes-的边界和协同)
- [分布式-AI-工作负载-API：JobSet、LeaderWorkerSet-与失败语义](/source/平台工程课程册/17-分布式-AI-工作负载-API：JobSet、LeaderWorkerSet-与失败语义)
- [Kubeflow-平台组件、Profiles-与多用户隔离](/source/平台工程课程册/18-Kubeflow-平台组件、Profiles-与多用户隔离)
- [Kubeflow-Trainer-V2-与训练运行时产品化](/source/平台工程课程册/19-Kubeflow-Trainer-V2-与训练运行时产品化)
- [KubeRay：RayCluster、RayJob、RayService-与多层扩缩](/source/平台工程课程册/20-KubeRay：RayCluster、RayJob、RayService-与多层扩缩)
- [Kubeflow-Pipelines-V2、Katib-与实验工作流](/source/平台工程课程册/21-Kubeflow-Pipelines-V2、Katib-与实验工作流)
- [模型注册、制品版本与端到端血缘](/source/平台工程课程册/22-模型注册、制品版本与端到端血缘)
- [KServe-模型服务控制面与声明式生命周期](/source/平台工程课程册/23-KServe-模型服务控制面与声明式生命周期)
- [GitOps、环境晋级与渐进式发布](/source/平台工程课程册/24-GitOps、环境晋级与渐进式发布)
- [云原生-CI-CD、制品供应链与发布证明](/source/平台工程课程册/25-云原生-CI-CD、制品供应链与发布证明)
- [AI-平台统一可观测性与资源归因](/source/平台工程课程册/26-AI-平台统一可观测性与资源归因)
- [AI-Platform-SRE：SLO、故障演练与自动修复](/source/平台工程课程册/27-AI-Platform-SRE：SLO、故障演练与自动修复)
- [多租户安全、策略与审计](/source/平台工程课程册/28-多租户安全、策略与审计)
- [GPU-FinOps、容量规划与成本归属](/source/平台工程课程册/29-GPU-FinOps、容量规划与成本归属)
- [多集群控制面、自助门户与平台最终架构](/source/平台工程课程册/30-多集群控制面、自助门户与平台最终架构)
- [GPU-Ready-Kubernetes-集群基线](/source/平台工程课程册/31-GPU-Ready-Kubernetes-集群基线)
- [多租户-GPU-批处理与配额平台](/source/平台工程课程册/32-多租户-GPU-批处理与配额平台)
- [声明式分布式训练平台](/source/平台工程课程册/33-声明式分布式训练平台)
- [模型持续交付与安全发布平台](/source/平台工程课程册/34-模型持续交付与安全发布平台)
- [AI-Platform-SRE、安全与-FinOps-控制台](/source/平台工程课程册/35-AI-Platform-SRE、安全与-FinOps-控制台)
- [企业级自助-AI-平台](/source/平台工程课程册/36-企业级自助-AI-平台)

## 判读总纪律

- 默认 Fixture/模拟只验证控制逻辑；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置不足返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据；负例与失败注入对照必做。
