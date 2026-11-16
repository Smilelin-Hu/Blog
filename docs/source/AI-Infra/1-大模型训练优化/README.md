# 主题一 大模型训练优化

从岗位画像出发，沿着「并行策略 → 通信与集群 → 显存与计算效率 → 数据与稳定性 → 实战项目」走完一遍大模型训练系统的主干。

## 目录

### 岗位与基础

- [00 大厂 AI Infra 岗位技术要求](/source/AI-Infra/1-大模型训练优化/00-大厂AIInfra岗位技术要求)
- [01 大模型训练的时代背景与挑战](/source/AI-Infra/1-大模型训练优化/01-大模型训练的时代背景与挑战)
- [02 训练硬件基础与性能指标](/source/AI-Infra/1-大模型训练优化/02-训练硬件基础与性能指标)
- [03 PyTorch 训练基础与性能分析](/source/AI-Infra/1-大模型训练优化/03-PyTorch训练基础与性能分析)

### 并行策略

- [04 数据并行（Data Parallelism）](/source/AI-Infra/1-大模型训练优化/04-数据并行)
- [05 模型并行（Model Parallelism）](/source/AI-Infra/1-大模型训练优化/05-模型并行)
- [06 混合并行（Hybrid Parallelism）](/source/AI-Infra/1-大模型训练优化/06-混合并行)
- [07 专家并行（Expert Parallelism）与 MoE 训练](/source/AI-Infra/1-大模型训练优化/07-专家并行与MoE训练)

### 通信与集群

- [08 集合通信原语（Collective Communication）](/source/AI-Infra/1-大模型训练优化/08-集合通信原语)
- [09 NCCL 深度剖析与调优](/source/AI-Infra/1-大模型训练优化/09-NCCL深度剖析与调优)
- [10 大规模集群通信优化](/source/AI-Infra/1-大模型训练优化/10-大规模集群通信优化)

### 显存与计算效率

- [11 大模型显存占用分析](/source/AI-Infra/1-大模型训练优化/11-大模型显存占用分析)
- [12 ZeRO（零冗余优化器）原理与实战](/source/AI-Infra/1-大模型训练优化/12-ZeRO原理与实战)
- [13 激活值重计算（Activation Recomputation）](/source/AI-Infra/1-大模型训练优化/13-激活值重计算)
- [14 CPU/NPU 卸载（Offloading）](/source/AI-Infra/1-大模型训练优化/14-CPUNPU卸载)
- [15 混合精度训练（Mixed Precision Training）](/source/AI-Infra/1-大模型训练优化/15-混合精度训练)
- [16 算子融合（Kernel Fusion）与图优化](/source/AI-Infra/1-大模型训练优化/16-算子融合与图优化)
- [17 CUDA Triton 算子开发入门](/source/AI-Infra/1-大模型训练优化/17-CUDATriton算子开发入门)
- [30 模型蒸馏与稀疏化训练](/source/AI-Infra/1-大模型训练优化/30-模型蒸馏与稀疏化训练)

### 数据与稳定性

- [18 高效数据加载与预处理](/source/AI-Infra/1-大模型训练优化/18-高效数据加载与预处理)
- [19 数据存储与格式优化](/source/AI-Infra/1-大模型训练优化/19-数据存储与格式优化)
- [20 训练稳定性保障](/source/AI-Infra/1-大模型训练优化/20-训练稳定性保障)
- [21 训练可观测性体系建设](/source/AI-Infra/1-大模型训练优化/21-训练可观测性体系建设)
- [22 大规模训练的高可用（High Availability）](/source/AI-Infra/1-大模型训练优化/22-大规模训练的高可用)
- [23 强化学习训练（RLHF/DPO）](/source/AI-Infra/1-大模型训练优化/23-强化学习训练)
- [24 长上下文训练优化](/source/AI-Infra/1-大模型训练优化/24-长上下文训练优化)
- [25 国产芯片适配与异构计算](/source/AI-Infra/1-大模型训练优化/25-国产芯片适配与异构计算)
- [31 多模态与扩散模型训练系统](/source/AI-Infra/1-大模型训练优化/31-多模态与扩散模型训练系统)

### 实战与附录项目

- [26 综合实战项目](/source/AI-Infra/1-大模型训练优化/26-综合实战项目)
- [27 附录 1：基于 DeepSpeed Megatron 完成 7B 模型的分布式训练](/source/AI-Infra/1-大模型训练优化/27-附录1-项目一——基于DeepSpeedMegatron完成一个7B模型的分布式训练)
- [28 附录 2：端到端性能分析并优化至目标 MFU](/source/AI-Infra/1-大模型训练优化/28-附录2-项目二——对训练任务进行端到端的性能分析并优化至目标MFU)
- [29 附录 3：千卡集群场景下的通信瓶颈分析与优化方案设计](/source/AI-Infra/1-大模型训练优化/29-附录3-项目三——模拟千卡集群场景下的通信瓶颈分析与优化方案设计)
