# 项目三：Production AI Gateway and Smart Router

把网关全链路串成一次运行：租户配额预留 → 负载选路 → Prefix 亲和 → 请求发送 → 失败反馈 → 一次故障转移。项目级验收聚焦闭环结算：每个被接受请求都有决策记录、失败主副本在重试时被排除、prefix 亲和有状态、配额预留最终结算——预留不结算的网关会「配额泄漏」，运行越久可用配额越少。

## 1. 项目闭环

```bash
python project/03-smart-router/run.py --check-only
python project/03-smart-router/run.py --output results/project-03-fixture.json
python project/03-smart-router/run.py --real --gateway-url http://gw:8000 --replicas http://r1:8001,http://r2:8002 \
  --output results/gpu_result.json
```

- **输入**：gateway、副本集（含可注入失败）、多租户请求流。
- **输出**：决策 trace、故障转移记录、配额结算记录、亲和状态。
- **验收**：每接受请求有决策；失败主副本重试时被排除；prefix 亲和有状态；预留结算。

## 2. 判读纪律

- 故障转移必做注入对照：不注入失败证明不了排除逻辑生效。
- 配额结算要附终态快照：终态预留不归零即泄漏。
- 只有 `source=measured` 的报告可用于性能或发布结论。

## 3. 关联

课次基础见本册 [15-Gateway开销](15-Gateway开销：直连与Gateway成对计量)、[16-Replica-Set](16-Replica-Set：Inflight与EWMA负载路由)、[17-Prefix-Cache](17-Prefix-Cache：前缀亲和选路与缓存指标)；主题展开见 [生产级 AI Gateway 与 Smart Router](/source/AI-Infra/3-大模型推理优化工程/33-生产级AIGateway与SmartRouter)。