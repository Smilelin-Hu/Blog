# lesson-30：可观测性、检查点、容错、成本与持续后训练

## 实验目的

联合检查点、恢复守恒与有效成本。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-30/run.py
python lessons/lesson-30/run_gpu.py
```

机制结果写入 `lessons/lesson-30/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `checkpoint`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

故障演练验证 RPO/RTO、幂等和语义连续性；成本报告区分原始 GPU 时间、空闲、重试与最终有效 Token。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

课程提供可执行基线和生产配置入口，不承诺在未测试集群上的恢复时间或成本数字。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
