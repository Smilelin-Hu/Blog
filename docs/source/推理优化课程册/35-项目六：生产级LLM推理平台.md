# 项目六：Production LLM Inference Platform

把前面所有组件连成一次完整运行：版本注册 → Canary → Gateway 选路 → 配额 → 故障回退 → 扩缩容 → 成本证据。项目级验收是平台闭环的总检查：非法生命周期迁移必须失败、候选被 shadow 对比、失败候选把流量交回 stable、所有预留结算、终态显式声明。任何一环「静默通过」，平台结论都不可信。

## 1. 项目闭环

```bash
python project/06-inference-platform/run.py --check-only
python project/06-inference-platform/run.py --output results/project-06-fixture.json
python project/06-inference-platform/run.py --real --platform-url http://platform:8000 \
  --output results/gpu_result.json
```

- **输入**：平台端点、版本注册表、含失败注入的请求流、需求曲线。
- **输出**：生命周期迁移记录、shadow 对比报告、回退记录、配额结算、成本证据、显式终态。
- **验收**：非法迁移失败；候选 shadow 对比；失败候选回流量到 stable；预留全结算；终态显式。

## 2. 判读纪律

- 非法迁移注入必做：不注入证明不了状态机守卫真实生效。
- 成本证据与课次 29 口径对齐（电价供给、工作期功耗采样、生成 token 计数）。
- 只有 `source=measured` 的报告可用于性能或发布结论。

## 3. 关联

课次基础见本册 [20-Model-Registry](/source/推理优化课程册/20-Model-Registry：稳定版Canary门禁与回滚)、[23-Control-Plane](/source/推理优化课程册/23-Control-Plane：Desired-Actual-Diff与Probe)、[29-Inference-Economics](/source/推理优化课程册/29-Inference-Economics：Token吞吐功耗与成本)；主题展开见 [生产级 LLM Inference Platform](/source/AI-Infra/3-大模型推理优化工程/36-生产级LLMInferencePlatform)。