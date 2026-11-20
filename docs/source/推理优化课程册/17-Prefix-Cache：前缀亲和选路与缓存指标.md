# Prefix Cache：前缀亲和选路与缓存指标

前缀缓存的收益依赖「同前缀请求落到同副本」：亲和选路把相同 prefix key 的请求稳定路由到同一健康副本，命中缓存省 prefill。本课核验三件事：同 key 稳定落在单健康副本、缓存指标真实参与决策（有 cache evidence）、请求真实到达所选端点（而非日志声称）。重复请求的延迟衰减是命中生效的直接证据。

## 1. 机制要点

- **亲和稳定性**：同 prefix key 在副本健康期间应稳定落同一副本；频繁跳副本会让缓存失效。
- **cache evidence**：路由决策要带缓存指标输入（命中块数/命中率），无证据的「亲和」可能只是哈希巧合。
- **到达真实性**：decision trace 的所选端点必须与请求实际到达端点一致，防止「日志路由」与「真实路由」两张皮。

## 2. 实验闭环

```bash
python lesson/17-prefix-affinity/run.py --check-only
python lesson/17-prefix-affinity/run.py --output results/lesson-17-fixture.json
python lesson/17-prefix-affinity/run.py --real --replicas http://r1:8000,http://r2:8001 --prefix-keys k1,k2 \
  --output results/gpu_result.json
```

- **输入**：副本集、prefix key 集、重复请求序列。
- **输出**：affinity trace、cache metric delta inputs、latencies by repetition。
- **验收**：同 key 稳定单健康副本；指标含 cache evidence；请求真实到达所选端点。

## 3. 判读纪律

- 命中证据看重复延迟衰减：第 2/3 次同前缀请求的 prefill 延迟应显著低于首次，否则缓存没生效。
- 副本故障注入后亲和应迁移且缓存重建可见：稳定不等于粘死坏副本。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

前缀缓存与 KV 分布的机制展开见 [Prefix/Session 与 KV Locality Routing](/source/AI-Infra/3-大模型推理优化工程/18-Prefix-Session与KV-LocalityRouting) 与 [KV 分布：多级存储与状态恢复](/source/AI-Infra/3-大模型推理优化工程/41-KV分布-多级存储与状态恢复)；本课聚焦亲和与命中证据的实验口径。