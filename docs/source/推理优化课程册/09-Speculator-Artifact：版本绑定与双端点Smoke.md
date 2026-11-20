# Speculator Artifact：版本绑定与双端点 Smoke Benchmark

投机解码的上线单元不是「模型」而是「artifact」：draft 权重、target 权重、head 配置、解码参数共同构成一个可版本化的制品。本课核验 artifact 身份绑定（manifest 与 served model 一致）与双端点成对 smoke benchmark（基线端点 vs 候选端点），确保上线结论可归因到具体制品版本。

## 1. 机制要点

- **身份绑定**：manifest 声明的 target/draft 版本必须与实际 served 模型一致；错绑会让接受率与延迟结论归因错误。
- **成对 smoke**：基线与候选两个独立端点成对跑同一请求集，差值才是候选制品的净效应。
- **完整性**：所有请求对都必须完成，缺对的差值统计有偏。

## 2. 实验闭环

```bash
python lesson/09-speculator-artifact/run.py --check-only
python lesson/09-speculator-artifact/run.py --output results/lesson-09-fixture.json
python lesson/09-speculator-artifact/run.py --real --baseline-url http://base:8000 --candidate-url http://cand:8001 \
  --output results/gpu_result.json
```

- **输入**：基线/候选两个端点、artifact manifest、请求集。
- **输出**：artifact identity、metrics evidence、paired smoke result。
- **验收**：manifest target 与 served model 一致；候选是独立端点；所有请求对完整。

## 3. 判读纪律

- 身份证据先于性能证据：manifest 与 served 模型不一致时，整轮 smoke 作废。
- 成对差值要附请求级记录，聚合数字 alone 不接受。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

制品供应链与发布证明的平台侧展开见 [GitOps：环境晋级与渐进式发布](/source/AI-Infra/4-AI平台工程/24-GitOps-环境晋级与渐进式发布)；本课聚焦推理制品的身份绑定与成对 smoke。