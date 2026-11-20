# 项目一：Next-Generation Speculator Benchmark

把课次 01–09 的投机解码验收串成一次成对基准：同一工作负载打到「禁用 Speculator」与「启用 Speculator」两个独立端点，校验输出等价与部署归因。项目级验收比课次更严：每个请求必须到达两端点、target/采样/工作负载身份一致、候选输出等于基线、部署证据把候选绑定到 artifact——四条缺一，基准结论不可用于发布。

## 1. 项目闭环

```bash
python project/01-speculator-benchmark/run.py --check-only
python project/01-speculator-benchmark/run.py --output results/project-01-fixture.json
python project/01-speculator-benchmark/run.py --real --baseline-url http://base:8000 --candidate-url http://cand:8001 \
  --output results/gpu_result.json
```

- **输入**：基线/候选独立端点、同一工作负载、artifact manifest。
- **输出**：成对延迟/吞吐差、输出等价证明、部署归因证据。
- **验收**：每请求到达两端点；target/采样/工作负载身份匹配；候选输出等于基线；部署证据绑定候选到 artifact。

## 2. 判读纪律

- 成对差值附请求级记录与身份快照；身份不匹配的整轮作废。
- 输出等价先于性能结论：不等价时「加速」无意义。
- 只有 `source=measured` 的报告可用于性能或发布结论。

## 3. 关联

课次基础见本册 [01-投机解码](01-投机解码：Draft提议与Target验证)、[09-Speculator-Artifact](09-Speculator-Artifact：版本绑定与双端点Smoke)；主题展开见 [新一代 Speculator Benchmark](/source/AI-Infra/3-大模型推理优化工程/31-新一代SpeculatorBenchmark)。