# OpenAI-Compatible API：直连与 Gateway 成对开销

Gateway 提供鉴权、路由、计量等能力，也引入额外延迟。本课用成对实验量「直连 vs 经 Gateway」的净开销：同一模型 ID、同一 payload、请求顺序交替（消除时间漂移），成对差值才是 Gateway 的真实成本；失败率也要成对比较，避免只比延迟不比可用性。

![推理 Gateway 请求处理链](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l16_03.png)

## 1. 机制要点

- **成对设计**：直连与 Gateway 两路径跑同一请求集，差值归因于 Gateway 本身。
- **顺序交替**：请求顺序交替平衡时间漂移（负载波动、缓存预热），否则差值混入环境噪声。
- **同模型同 payload**：两路径必须 serve 同一 model ID、payload 逐字节一致，否则差值不可归因。

## 2. 实验闭环

```bash
python lesson/15-gateway-overhead/run.py --check-only
python lesson/15-gateway-overhead/run.py --output results/lesson-15-fixture.json
python lesson/15-gateway-overhead/run.py --real --direct-url http://model:8000 --gateway-url http://gw:8001 \
  --output results/gpu_result.json
```

- **输入**：直连端点、Gateway 端点、同一请求集。
- **输出**：paired deltas、order-balanced records、failure comparison。
- **验收**：请求顺序交替；payload 一致；两端点 serve 同一 model ID。

## 3. 判读纪律

- 开销报成对差值分布（P50/P99），不报单点均值；尾延迟开销往往才是 Gateway 的真实代价。
- 失败比较与延迟比较同表：Gateway 降延迟但抬失败率时净收益为负。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

Gateway 组件与路由机制展开见[OpenAI-Compatible AI Gateway：计量、配额与租户治理](/source/AI-Infra/3-大模型推理优化工程/16-OpenAI-CompatibleAIGateway-计量-配额与租户治理) 与 [Prefix/Session 与 KV Locality Routing](/source/AI-Infra/3-大模型推理优化工程/18-Prefix-Session与KV-LocalityRouting)；本课聚焦成对开销计量。