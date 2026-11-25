08｜AI Systems Performance Engineering 综合项目
============================================

实验目标
--------

完成从SLO、基线、假设、优化、正确性、成本到回滚的端到端性能工程闭环。

推荐运行顺序
------------

Level 0：bash run_capstone.sh
Level 1：把capstone_runner.py中的基线与候选函数替换为合法目标工作负载后复测
Level 2/可选：使用Profiler或集群实验时把原始证据保存到baseline/candidate/traces

交付结果
--------

baseline、candidate、五份报告、命令记录和可回滚交付

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
