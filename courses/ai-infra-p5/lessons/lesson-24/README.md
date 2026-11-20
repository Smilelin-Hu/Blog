# lesson-24：DPO、IPO、KTO、ORPO、SimPO 与离线偏好系统

## 实验目的

离线偏好目标的 Margin 与长度归一。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-24/run.py
python lessons/lesson-24/run_gpu.py
```

机制结果写入 `lessons/lesson-24/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `offline_preference`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

候选方法共享数据切片、起始策略和评测预算，报告目标函数、参考策略、有效样本与主要超参数。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

离线偏好优化依赖收集数据的覆盖范围，无法凭目标函数消除数据缺失。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。

本课 run.py 的现有 fixture 实现无参考项的逻辑偏好代理目标，不是标准 DPO；带冻结参考项的可运行对照见 projects/project-05/train_toy_policy.py。
