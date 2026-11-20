# project-03：Continued Pretraining 与 SFT 数据配方工厂

本项目把 lesson-14, lesson-15, lesson-16, lesson-18, lesson-19, lesson-21 的机制组合成一次端到端验收。项目运行器读取各课的 fixture，逐项执行同一实现，并把状态、关键指标和失败检查汇总到 `results/project.json`。

```bash
python projects/project-03/run.py
python projects/project-03/run_gpu.py
```

项目通过要求所有组成机制均为 `passed`，且报告保留每个子实验的对象级证据。CUDA 路径只验证 `masked_loss` 的真实单进程设备路径；无 CUDA 时结构化跳过。它不证明完整项目已经在生产集群、对象存储或分布式训练框架上达到性能目标。

完成实验后建议保存项目报告、所用 fixture 的校验和、失败注入结果和结论边界。删除本目录 `results/` 即可清理运行产物。
