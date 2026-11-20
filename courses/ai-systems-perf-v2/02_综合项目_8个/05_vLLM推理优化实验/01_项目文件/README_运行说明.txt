05｜vLLM 推理优化
==============

实验目标
--------

用排队模拟和OpenAI兼容接口基准寻找满足TTFT、TPOT与Goodput约束的并发配置。

推荐运行顺序
------------

Level 0：python3 scheduler_sim.py --requests 100 --output-tokens 64
Level 1：export SERVED_MODEL=服务实际模型名; bash run_sweep.sh
Level 2/可选：export MODEL_PATH=模型路径; bash start_server_example.sh

交付结果
--------

reports/c*.json、reports/server_command.txt、logs/server.log 与 reports/analysis.md

验收规则
--------

- 记录操作系统、Python、框架、CUDA、驱动、GPU及完整命令。
- 基线和候选方案保持输入形状、随机种子、精度和正确性标准一致。
- 报告P50/P95或项目规定的尾部指标，不用单次最快结果代表性能。
- 区分脚本模型推导、本机实验观察和可推广结论。
- 不支持的GPU专项应明确记录为skipped，不伪造等价结果。
