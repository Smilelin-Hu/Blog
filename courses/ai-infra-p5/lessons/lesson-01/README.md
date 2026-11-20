# lesson-01：大模型数据与后训练基础设施全景

## 实验目的

对象合同、血缘闭包与检查点反查。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-01/run.py
python lessons/lesson-01/run_gpu.py
```

机制结果写入 `lessons/lesson-01/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `lineage_map`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

任取一个检查点，可以正向追到训练输入，也可以反向追到原始来源、处理配方、Reward 与策略版本。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

本课验证对象和血缘关系，不用单机模拟结果替代多节点吞吐或模型能力结论。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
