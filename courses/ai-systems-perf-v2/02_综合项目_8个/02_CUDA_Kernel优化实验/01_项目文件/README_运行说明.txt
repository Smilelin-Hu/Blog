02｜CUDA Kernel 优化项目
=====================

实验目标
--------

用 Reduction 对比全局原子、Shared Memory 归约与 Warp Shuffle 的性能和正确性。

推荐运行顺序
------------

Level 0：python3 reduction_cost_model.py --output reports/cost_model.json
Level 1：bash build_and_run.sh
Level 2/可选：bash run_sweep.sh

交付结果
--------

reports/cost_model.json、reports/size_sweep.csv、Nsight 报告与 analysis.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
