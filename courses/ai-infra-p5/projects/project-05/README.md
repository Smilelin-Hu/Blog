# project-05：可按显存缩放的 SFT 到 DPO 到 GRPO/RLVR 流水线

本项目把 lesson-19, lesson-24, lesson-25, lesson-26 的机制组合成一次端到端验收。项目运行器读取各课的 fixture，逐项执行同一实现，并把状态、关键指标和失败检查汇总到 `results/project.json`。

```bash
python projects/project-05/run.py
python projects/project-05/run_gpu.py
```

项目通过要求所有组成机制均为 `passed`，且报告保留每个子实验的对象级证据。CUDA 路径只验证 `masked_loss` 的真实单进程设备路径；无 CUDA 时结构化跳过。它不证明完整项目已经在生产集群、对象存储或分布式训练框架上达到性能目标。

完成实验后建议保存项目报告、所用 fixture 的校验和、失败注入结果和结论边界。删除本目录 `results/` 即可清理运行产物。

## 策略参数更新实验

这个实验使用只有两个动作的分类策略。SFT 的交叉熵、带冻结参考项的 DPO 和组内优势驱动的裁剪更新都会实际修改策略参数。先观察 SFT 后动作概率，再核对 DPO 的参考差是否固定，最后检查零方差组与行为概率。它没有语言上下文、价值网络或分布式并行，不能用结果推断 LLM 的能力提升。

```bash
python projects/project-05/train_toy_policy.py
```
