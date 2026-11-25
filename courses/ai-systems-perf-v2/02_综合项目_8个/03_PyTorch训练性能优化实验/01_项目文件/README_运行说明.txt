03｜PyTorch 训练性能优化
===================

实验目标
--------

比较基线与优化训练步骤，并用自动回归门禁同时约束性能和损失。

推荐运行顺序
------------

Level 0：bash run_compare.sh cpu
Level 1：bash run_compare.sh auto
Level 2/可选：python3 train_benchmark.py --device cuda --mode optimized --compile --output reports/optimized_compile.json

交付结果
--------

reports/baseline.json、reports/optimized.json、reports/profile/ 与 reports/comparison.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
