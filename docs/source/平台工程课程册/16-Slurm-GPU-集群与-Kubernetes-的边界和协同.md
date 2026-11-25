# Slurm-GPU-集群与-Kubernetes-的边界和协同

Slurm 与 K8s 边界协同：HPC 批调度与云原生服务各擅其长。

## 1. 机制要点

- Slurm 擅长大批 HPC 作业，K8s 擅长服务化
- 边界清晰避免两套调度互相抢资源

## 2. 实验闭环

```bash
python3 lessons/lesson-16/run.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：Slurm 擅长大批 HPC 作业，K8s 擅长服务化；边界清晰避免两套调度互相抢资源

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·16-SlurmGPU集群与Kubernetes的边界和协同](/source/AI-Infra/4-AI平台工程/16-SlurmGPU集群与Kubernetes的边界和协同)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
