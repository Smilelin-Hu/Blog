# project-06：可恢复的异步 Agentic RL 后训练平台

本项目把 lesson-27, lesson-28, lesson-29, lesson-30 的机制组合成一次端到端验收。项目运行器读取各课的 fixture，逐项执行同一实现，并把状态、关键指标和失败检查汇总到 `results/project.json`。

```bash
python projects/project-06/run.py
python projects/project-06/run_gpu.py
```

项目通过要求所有组成机制均为 `passed`，且报告保留每个子实验的对象级证据。CUDA 路径只验证 `weight_sync` 的真实单进程设备路径；无 CUDA 时结构化跳过。它不证明完整项目已经在生产集群、对象存储或分布式训练框架上达到性能目标。

完成实验后建议保存项目报告、所用 fixture 的校验和、失败注入结果和结论边界。删除本目录 `results/` 即可清理运行产物。

## 崩溃与恢复实验

实验使用 SQLite 将一个整数模型状态和提交账本放入同一事务。子进程分别在提交前、提交后直接退出，父进程重新打开数据库并重试；最终检查权重只增加一次、提交只有一条、同一 Batch 携带不同内容时被拒绝。GPU 权重通常不在同一个数据库事务中，因此这个实验只提供原子提交的可读基线，不能证明跨队列、对象存储和 GPU 的分布式一次效果。

```bash
python projects/project-06/durable_commit.py
```
