07｜Disaggregated Inference 系统设计
=================================

实验目标
--------

形成Prefill/Decode解耦系统的容量、接口、故障、部署与验证闭环。

推荐运行顺序
------------

Level 0：python3 disagg_capacity_planner.py --output reports/capacity.json
Level 1：bash run_sweeps.sh
Level 2/可选：在隔离集群审阅并修改deployment目录，不应直接用于生产

交付结果
--------

容量结果、架构文档、API契约、故障矩阵、部署模板与 validation_report.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
