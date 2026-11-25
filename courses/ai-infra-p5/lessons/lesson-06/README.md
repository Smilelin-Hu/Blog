# lesson-06：DataTrove、NeMo Curator、Ray 与 Spark 数据流

## 实验目的

执行框架与工作负载特征匹配。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-06/run.py
python lessons/lesson-06/run_gpu.py
```

机制结果写入 `lessons/lesson-06/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `scheduler_fit`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

同一逻辑流水线在候选执行面上使用相同输入和门禁，报告吞吐、峰值内存、重试语义、产物一致性与运维复杂度。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

单机样例用于验证接口和语义，不能外推目标集群上的调度、网络和对象存储成本。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
