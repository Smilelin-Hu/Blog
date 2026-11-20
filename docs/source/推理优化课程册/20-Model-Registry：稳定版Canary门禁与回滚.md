# Model Registry：稳定版、Canary 门禁与回滚

模型发布走 registry 状态机：stable → canary → 全量或回滚。canary 门禁由真实请求记录计算（错误率/延迟/SLO 违约），门禁失败时探针流量路由回 stable。本课核验三件事：canary 真实收到非零流量、门禁由记录计算（而非拍阈值）、门禁失败后探针真实回到 stable——三者缺一，灰度就是形同虚设或误杀。

## 1. 机制要点

- **非零 canary 流量**：canary 没流量就没有门禁证据，「通过」只是默认值。
- **门禁可复算**：gate 值必须能由请求记录复算（窗口、指标、阈值明确），否则门禁不可审计。
- **失败回滚路径**：门禁失败后探针回 stable 是安全网；回滚路径不生效时坏版本会持续吃流量。

## 2. 实验闭环

```bash
python lesson/20-canary-release/run.py --check-only
python lesson/20-canary-release/run.py --output results/lesson-20-fixture.json
python lesson/20-canary-release/run.py --real --registry http://registry:8000 --stable-url http://s:8001 --canary-url http://c:8002 \
  --output results/gpu_result.json
```

- **输入**：registry、stable/canary 端点、含失败注入的请求流。
- **输出**：state transitions、gate calculation、post-decision probes。
- **验收**：canary 非零流量；gate 由记录计算；失败门禁把探针路由回 stable。

## 3. 判读纪律

- 状态迁移要附时点与触发证据：无触发记录的迁移不算闭环。
- 失败注入必做：不注入失败就证明不了回滚路径真实生效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

发布治理的平台侧展开见 [GitOps：环境晋级与渐进式发布](/source/AI-Infra/4-AI平台工程/24-GitOps-环境晋级与渐进式发布)；本课聚焦 canary 门禁与回滚路径的实验核验。