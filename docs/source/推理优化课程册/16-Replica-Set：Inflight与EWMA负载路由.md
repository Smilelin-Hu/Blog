# Replica Set：基于 Inflight 与 EWMA 的负载路由

多副本路由的核心信号是 inflight（在飞请求数）与 EWMA（指数加权移动平均延迟）：前者反映即时占用，后者反映近期处理能力。本课核验路由决策真实在每请求前执行、inflight 真实结算（请求完成即减）、失败副本真实变为不可选——三者缺一，路由就是摆设或会把流量送进坏副本。

## 1. 机制要点

- **inflight 结算**：请求完成/失败都要结算 inflight；只增不减会让副本「看起来永远忙」，路由退化为轮询。
- **EWMA 语义**：平滑延迟信号抑制瞬时抖动；半衰期选择决定对突变的响应速度。
- **失败剔除**：失败副本进入不可选集合（含恢复探针），否则路由持续把流量送进坏副本。

## 2. 实验闭环

```bash
python lesson/16-load-router/run.py --check-only
python lesson/16-load-router/run.py --output results/lesson-16-fixture.json
python lesson/16-load-router/run.py --real --replicas http://r1:8000,http://r2:8001,http://r3:8002 \
  --output results/gpu_result.json
```

- **输入**：副本集（含可注入失败的副本）、请求流。
- **输出**：decision trace、endpoint state、request results。
- **验收**：每请求前执行选择；inflight 结算；失败副本不可选。

## 3. 判读纪律

- decision trace 要含选择时点与信号快照：事后补的路由日志不算证据。
- 失败注入对照必做：注入后该副本选择次数应归零（恢复探针除外）。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

路由与 KV locality 的机制展开见 [Prefix/Session 与 KV Locality Routing](/source/AI-Infra/3-大模型推理优化工程/18-Prefix-Session与KV-LocalityRouting)；本课聚焦 inflight/EWMA 信号真实性的实验核验。