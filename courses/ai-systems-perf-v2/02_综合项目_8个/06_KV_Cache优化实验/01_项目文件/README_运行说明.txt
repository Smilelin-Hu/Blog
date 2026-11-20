06｜KV Cache 优化实验
==================

实验目标
--------

估算KV容量和分页碎片，并对Prefix Cache开关做严格A/B测试。

推荐运行顺序
------------

Level 0：python3 kv_cache_lab.py --mode capacity --output reports/capacity.json
Level 1：export SERVED_MODEL=服务实际模型名; bash run_prefix_ab.sh
Level 2/可选：分别启动Prefix Cache关闭与开启的同一模型服务后执行A/B脚本

交付结果
--------

reports/capacity.json、reports/fragmentation.json、Prefix A/B结果与 reports/analysis.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
