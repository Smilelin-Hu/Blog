# lesson-07：训练数据格式、分片、索引、流式读取与缓存

## 实验目的

确定性分片、游标与恢复后守恒。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-07/run.py
python lessons/lesson-07/run_gpu.py
```

机制结果写入 `lessons/lesson-07/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `shard_replay`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

固定样本集在冷缓存、热缓存和恢复运行后保持样本身份与顺序可解释，同时输出 I/O 等待、有效 Token 吞吐和缓存命中。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

本课只比较数据供给路径；模型计算、网络拓扑和并行策略需要在目标训练环境单独测量。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
