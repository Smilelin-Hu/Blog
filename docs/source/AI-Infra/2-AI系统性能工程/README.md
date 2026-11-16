# 第二期 AI 系统性能工程

从一次 Kernel 到一套可测量、可诊断、可优化、可回归的 AI 系统：性能方法论与指标体系、GPU 微架构与显存、CUDA 与算子、分布式训练与通信、Compiler 与 Runtime、LLM 推理系统，最后以八个综合项目收口。

## 目录

### 导览与性能方法论

- [00 课程导览](/source/AI-Infra/2-AI系统性能工程/00-课程导览)
- [01 AI Systems Performance Engineering 概述](/source/AI-Infra/2-AI系统性能工程/01-AI-Systems-Performance-Engineering概述)
- [02 AI 系统性能指标体系](/source/AI-Infra/2-AI系统性能工程/02-AI系统性能指标体系)
- [03 现代 AI 系统全栈架构](/source/AI-Infra/2-AI系统性能工程/03-现代AI系统全栈架构)
- [04 DeepSeek 案例——软件优化如何突破硬件限制](/source/AI-Infra/2-AI系统性能工程/04-DeepSeek案例——软件优化如何突破硬件限制)

### GPU 硬件与运行环境

- [05 GPU 架构深度解析](/source/AI-Infra/2-AI系统性能工程/05-GPU架构深度解析)
- [06 GPU Memory 体系优化](/source/AI-Infra/2-AI系统性能工程/06-GPUMemory体系优化)
- [07 Tensor Core 与低精度计算优化](/source/AI-Infra/2-AI系统性能工程/07-TensorCore与低精度计算优化)
- [08 NVLink、NVSwitch 与 AI 集群互联](/source/AI-Infra/2-AI系统性能工程/08-NVLink与AI集群互联)
- [09 Linux、Docker、Kubernetes GPU 性能优化](/source/AI-Infra/2-AI系统性能工程/09-LinuxDocker与KubernetesGPU性能优化)

### CUDA 与高性能算子

- [10 CUDA 编程模型](/source/AI-Infra/2-AI系统性能工程/10-CUDA编程模型)
- [11 GPU Memory 访问优化](/source/AI-Infra/2-AI系统性能工程/11-GPUMemory访问优化)
- [12 GPU 性能分析方法](/source/AI-Infra/2-AI系统性能工程/12-GPU性能分析方法)
- [13 Kernel Fusion 与高性能算子开发](/source/AI-Infra/2-AI系统性能工程/13-KernelFusion与高性能算子开发)
- [14 Triton Kernel 开发](/source/AI-Infra/2-AI系统性能工程/14-TritonKernel开发)

### 分布式训练与通信

- [15 大模型分布式训练体系](/source/AI-Infra/2-AI系统性能工程/15-大模型分布式训练体系)
- [16 NCCL 深度优化](/source/AI-Infra/2-AI系统性能工程/16-NCCL深度优化)
- [17 GPU 通信性能优化](/source/AI-Infra/2-AI系统性能工程/17-GPU通信性能优化)
- [18 FSDP 与超大模型训练优化](/source/AI-Infra/2-AI系统性能工程/18-FSDP与超大模型训练优化)

### Compiler 与 Runtime

- [19 PyTorch 性能分析体系](/source/AI-Infra/2-AI系统性能工程/19-PyTorch性能分析体系)
- [20 torch.compile 深度解析](/source/AI-Infra/2-AI系统性能工程/20-torchcompile深度解析)
- [21 CUDA Graph 与 Runtime 优化](/source/AI-Infra/2-AI系统性能工程/21-CUDAGraph与Runtime优化)
- [22 AI Runtime 优化思想](/source/AI-Infra/2-AI系统性能工程/22-AIRuntime优化思想)

### LLM 推理系统

- [23 LLM 推理系统架构](/source/AI-Infra/2-AI系统性能工程/23-LLM推理系统架构)
- [24 Continuous Batching 与 Scheduler 优化](/source/AI-Infra/2-AI系统性能工程/24-ContinuousBatching与Scheduler优化)
- [25 KV Cache 性能优化](/source/AI-Infra/2-AI系统性能工程/25-KVCache性能优化)
- [26 Speculative Decoding 与推理加速](/source/AI-Infra/2-AI系统性能工程/26-SpeculativeDecoding与推理加速)
- [27 Disaggregated Inference 架构](/source/AI-Infra/2-AI系统性能工程/27-DisaggregatedInference架构)
- [28 MoE 推理与未来 AI Runtime](/source/AI-Infra/2-AI系统性能工程/28-MoE推理与未来AIRuntime)

### 综合项目

- [29 GPU 性能分析实验](/source/AI-Infra/2-AI系统性能工程/29-GPU性能分析实验)
- [30 CUDA Kernel 优化项目](/source/AI-Infra/2-AI系统性能工程/30-CUDAKernel优化项目)
- [31 PyTorch 训练性能优化](/source/AI-Infra/2-AI系统性能工程/31-PyTorch训练性能优化)
- [32 7B 模型训练性能 Benchmark](/source/AI-Infra/2-AI系统性能工程/32-7B模型训练性能Benchmark)
- [33 vLLM 推理优化](/source/AI-Infra/2-AI系统性能工程/33-vLLM推理优化)
- [34 KV Cache 优化实验](/source/AI-Infra/2-AI系统性能工程/34-KVCache优化实验)
- [35 Disaggregated Inference 系统设计](/source/AI-Infra/2-AI系统性能工程/35-DisaggregatedInference系统设计)
- [36 AI Systems Performance Engineering 综合项目](/source/AI-Infra/2-AI系统性能工程/36-AISystemsPerformanceEngineering综合项目)

### 待填充专题

- [37 模型量化与低精度部署：PTQ、QAT、GPTQ、AWQ 与 SmoothQuant](/source/AI-Infra/2-AI系统性能工程/37-模型量化与低精度部署-PTQ-QAT-GPTQ-AWQ-SmoothQuant)
- [38 编译器栈与算子库：MLIR、TVM、XLA、CUTLASS 与 CuTe](/source/AI-Infra/2-AI系统性能工程/38-编译器栈与算子库-MLIR-TVM-XLA-CUTLASS-CuTe)
- [39 GPU 能耗、功耗墙与数据中心效率](/source/AI-Infra/2-AI系统性能工程/39-GPU能耗-功耗墙与数据中心效率)