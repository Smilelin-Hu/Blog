# 系统性能课程册

按课程原课次顺序整理的实验笔记：每课一篇，先讲机制，再给实验闭环（Fixture/真实路径、输入输出与验收），最后落判读纪律。与 [AI Infra 主题笔记](/source/AI-Infra/README) 的区别在于组织方式——主题笔记按知识域重组，本册保留课次顺序，聚焦「实验怎么做、结论怎么判」。

## 目录

- [AI-Systems-Performance-Engineering-概述](/source/系统性能课程册/01-AI-Systems-Performance-Engineering-概述)
- [AI-系统性能指标体系](/source/系统性能课程册/02-AI-系统性能指标体系)
- [现代-AI-系统全栈架构](/source/系统性能课程册/03-现代-AI-系统全栈架构)
- [DeepSeek-案例](/source/系统性能课程册/04-DeepSeek-案例)
- [GPU-架构深度解析](/source/系统性能课程册/05-GPU-架构深度解析)
- [GPU-Memory-体系优化](/source/系统性能课程册/06-GPU-Memory-体系优化)
- [Tensor-Core-与低精度计算优化](/source/系统性能课程册/07-Tensor-Core-与低精度计算优化)
- [NVLink、NVSwitch-与-AI-集群互联](/source/系统性能课程册/08-NVLink、NVSwitch-与-AI-集群互联)
- [Linux、Docker、Kubernetes-GPU-性能优化](/source/系统性能课程册/09-Linux、Docker、Kubernetes-GPU-性能优化)
- [CUDA-编程模型](/source/系统性能课程册/10-CUDA-编程模型)
- [GPU-Memory-访问优化](/source/系统性能课程册/11-GPU-Memory-访问优化)
- [GPU-性能分析方法](/source/系统性能课程册/12-GPU-性能分析方法)
- [Kernel-Fusion-与高性能算子开发](/source/系统性能课程册/13-Kernel-Fusion-与高性能算子开发)
- [Triton-Kernel-开发](/source/系统性能课程册/14-Triton-Kernel-开发)
- [大模型分布式训练体系](/source/系统性能课程册/15-大模型分布式训练体系)
- [NCCL-深度优化](/source/系统性能课程册/16-NCCL-深度优化)
- [GPU-通信性能优化](/source/系统性能课程册/17-GPU-通信性能优化)
- [FSDP-与超大模型训练优化](/source/系统性能课程册/18-FSDP-与超大模型训练优化)
- [PyTorch-性能分析体系](/source/系统性能课程册/19-PyTorch-性能分析体系)
- [torch.compile-深度解析](/source/系统性能课程册/20-torch.compile-深度解析)
- [CUDA-Graph-与-Runtime-优化](/source/系统性能课程册/21-CUDA-Graph-与-Runtime-优化)
- [AI-Runtime-优化思想](/source/系统性能课程册/22-AI-Runtime-优化思想)
- [LLM-推理系统架构](/source/系统性能课程册/23-LLM-推理系统架构)
- [Continuous-Batching-与-Scheduler-优化](/source/系统性能课程册/24-Continuous-Batching-与-Scheduler-优化)
- [KV-Cache-性能优化](/source/系统性能课程册/25-KV-Cache-性能优化)
- [Speculative-Decoding-与推理加速](/source/系统性能课程册/26-Speculative-Decoding-与推理加速)
- [Disaggregated-Inference-架构](/source/系统性能课程册/27-Disaggregated-Inference-架构)
- [MoE-推理与未来-AI-Runtime](/source/系统性能课程册/28-MoE-推理与未来-AI-Runtime)
- [GPU性能分析实验](/source/系统性能课程册/29-GPU性能分析实验)
- [CUDA_Kernel优化实验](/source/系统性能课程册/30-CUDA_Kernel优化实验)
- [PyTorch训练性能优化实验](/source/系统性能课程册/31-PyTorch训练性能优化实验)
- [7B模型训练Benchmark实验](/source/系统性能课程册/32-7B模型训练Benchmark实验)
- [vLLM推理优化实验](/source/系统性能课程册/33-vLLM推理优化实验)
- [KV_Cache优化实验](/source/系统性能课程册/34-KV_Cache优化实验)
- [Disaggregated_Inference设计实验](/source/系统性能课程册/35-Disaggregated_Inference设计实验)
- [AI_Systems_Performance_Engineering综合实验](/source/系统性能课程册/36-AI_Systems_Performance_Engineering综合实验)

## 判读总纪律

- 默认 Fixture/模拟只验证控制逻辑；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置不足返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据；负例与失败注入对照必做。
