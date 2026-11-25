01｜GPU 性能分析实验
===============

实验目标
--------

建立 Roofline 方向判断、PyTorch 基准、系统时间线与 Kernel 指标的证据链。

推荐运行顺序
------------

Level 0：python3 roofline_planner.py --output reports/roofline.json
Level 1：python3 gpu_profiling_lab.py --device auto --mode all --output reports/benchmark.json
Level 2/可选：bash run_profiler.sh

交付结果
--------

reports/roofline.json、reports/benchmark.json、Profiler 报告与 analysis.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
