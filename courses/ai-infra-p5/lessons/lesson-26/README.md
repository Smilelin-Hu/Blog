# lesson-26：RLVR、环境、拒绝采样与 Agentic 数据飞轮

## 实验目的

RLVR 验证器绕过与对抗样本。机制实验用于检查对象关系、算法或状态转换是否满足本课定义；CUDA 路径只验证一条真实单进程 GPU 计算路径，不把本机结果外推成集群性能。

## 运行环境

- Python 3.10 或更高版本。
- 机制实验只使用标准库。
- CUDA 路径需要 PyTorch 与可用 NVIDIA CUDA GPU。

## 运行命令

```bash
python lessons/lesson-26/run.py
python lessons/lesson-26/run_gpu.py
```

机制结果写入 `lessons/lesson-26/results/simulation.json`。CUDA 不可用时，第二条命令输出 `status=skipped` 并正常退出，本次不执行 GPU 计算。

## 输入与参数

`fixture.json` 是固定的小规模反例集，场景名为 `verifier_attack`。可复制 fixture 后修改阈值、状态、策略版本或样本，观察验收项怎样变化。原始 fixture 不包含生产数据，也不代表真实数据分布。

## 验收标准

任务集覆盖正常、边界和诱骗样本；同一轨迹在固定环境和验证器版本下能复算奖励与终止状态。

`run.py` 只有在全部 `checks` 为真时返回成功。失败结果仍会写入 `results/`，方便查看哪项检查未通过。

## 证明边界

程序奖励降低主观标注成本，不保证验证器无漏洞，也不覆盖开放域行为的全部质量。

删除运行产物时可直接移除本目录的 `results/`；程序不会创建外部服务、云资源或后台任务。
