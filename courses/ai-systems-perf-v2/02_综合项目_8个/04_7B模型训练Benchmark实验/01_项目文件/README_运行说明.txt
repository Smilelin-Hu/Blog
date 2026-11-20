04｜7B 模型训练性能 Benchmark
========================

实验目标
--------

先完成7B训练容量规划，再用缩小GPT代理模型验证统一的吞吐、MFU和显存口径。

推荐运行顺序
------------

Level 0：python3 capacity_planner.py --output reports/capacity.json
Level 1：bash run_proxy.sh auto
Level 2/可选：bash run_proxy.sh cuda

交付结果
--------

reports/capacity.json、代理模型结果与 reports/benchmark_report.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
