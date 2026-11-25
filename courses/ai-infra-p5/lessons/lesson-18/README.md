# lesson-18：Continued Pretraining 与 Mid-training 数据设计

## 实验目的

持续预训练领域数据与通用回放配方。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-18/run.py
python lessons/lesson-18/run_gpu.py
```

机制结果写入 `lessons/lesson-18/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `cpt_recipe`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

同预算候选配方同时报告目标域、通用域和安全切片，并保存起始检查点、数据版本与学习率轨迹。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

小模型和短训练可筛选明显错误配方，不能完整预测目标模型的遗忘与涌现能力。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
