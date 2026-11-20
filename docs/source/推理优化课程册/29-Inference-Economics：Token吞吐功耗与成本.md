# Inference Economics：Token 吞吐、GPU 功耗与成本

推理经济学的三个量：token 吞吐（产出）、每输出 token 能耗（J/token）、每百万输出 token 成本（$/M tokens）。三者都必须实测：电价由外部供给而非假设、功耗在工作期间采样（而非 idle 读数）、token 数来自生成记录（而非估算）。idle 功耗算出的「能效」和假设电价算出的「成本」都是账面幻觉。

## 1. 机制要点

- **J/token 口径**：能耗积分除以输出 token 数；功率采样必须覆盖工作区间，idle 采样会低估能耗。
- **成本口径**：$/M tokens = (功率×电价×时间 + 摊销) / 输出 token 数；电价必须显式供给。
- **吞吐与 SLO 联合**：脱离 SLO 谈吞吐会把违约请求算进产出，成本数字失真。

## 2. 实验闭环

```bash
python lesson/29-inference-economics/run.py --check-only
python lesson/29-inference-economics/run.py --output results/lesson-29-fixture.json
python lesson/29-inference-economics/run.py --real --endpoint http://serving:8000 --price-per-kwh 0.8 \
  --output results/gpu_result.json
```

- **输入**：serving 端点、显式电价、功率采样配置、请求集。
- **输出**：token throughput、energy per output token、cost per million output tokens。
- **验收**：电价供给而非假设；功耗工作期间采样；token 数来自生成。

## 3. 判读纪律

- 三个量同表报并附口径（采样窗口、SLO、电价来源）：缺任一口径的数字不可比。
- 功率采样曲线留存：单点功率读数不算能耗证据。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

成本与 SLO 全局优化的机制展开见 [Inference Economics：Cost per Token、SLO 与全局优化](/source/AI-Infra/3-大模型推理优化工程/30-InferenceEconomics-CostperToken-SLO与全局优化)；功耗墙对照 [GPU 能耗：功耗墙与数据中心效率](/source/AI-Infra/2-AI系统性能工程/39-GPU能耗-功耗墙与数据中心效率)。