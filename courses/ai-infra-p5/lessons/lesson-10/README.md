# lesson-10：模型化质量评分、领域分类与难度建模

## 实验目的

质量评分器的置信度校准。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-10/run.py
python lessons/lesson-10/run_gpu.py
```

机制结果写入 `lessons/lesson-10/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `score_calibration`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

分类器按来源、语言、长度和领域切片评估；阈值选择展示精确率、召回率与人工复核成本的取舍。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

模型化评分是可版本化的代理信号，不能替代许可证、安全检查或下游训练消融。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
