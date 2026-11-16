# 推理引擎横向对比与选型：vLLM、SGLang、TensorRT-LLM 与 Dynamo

33 是 vLLM 单引擎调优，24 是控制面；本文补引擎间架构差异与选型判据。先澄清层级：**Dynamo 是分布式编排层，不是引擎**——它可坐在 vLLM/SGLang/TRT-LLM 之上做 PD 分离与 KV 路由，跨层对比会得出错误结论。

## 1. 分层与定位

| 组件 | 层 | 核心机制 | 生态位 |
|---|---|---|---|
| vLLM | 引擎 | PagedAttention、continuous batching、APC | 模型覆盖与硬件广度最大 |
| SGLang | 引擎 | RadixAttention 前缀树、原生约束解码 | 共享前缀/agent/结构化输出 |
| TensorRT-LLM | 引擎 | 编译图、kernel autotune、in-flight batching | NVIDIA 单卡极致效率 |
| Dynamo | 编排 | PD 分离、KV-aware 路由、多引擎后端 | 集群级控制面（24/27 的商用对照） |

## 2. 架构差异决定性能形态

- **vLLM**：PagedAttention 解决 KV 碎片，automatic prefix caching 做精确复用；调度公平性与生态成熟度是强项，time-to-production 最短，多硬件（含非 NVIDIA）支持最广。
- **SGLang**：RadixAttention 把前缀组织成跨请求基数树，多轮/agent/few-shot 的共享前缀命中率显著高于平铺 APC；约束解码（xgrammar 系）原生集成，结构化输出场景延迟稳。
- **TensorRT-LLM**：ahead-of-time build engine（图优化 + kernel autotune），编译后吞吐/延迟领先；代价是 build 成本、模型覆盖滞后、与 NVIDIA 栈强耦合——「极致效率」要用「上线速度」换。
- 2026 年多方基准的共识：**没有全场景赢家**。共享前缀重 → SGLang；NVIDIA 单卡极致 → TRT-LLM；通用生产与多硬件 → vLLM。

## 3. 选型决策矩阵

| 维度 | 倾向 |
|---|---|
| 共享前缀比例高（agent/多轮/few-shot） | SGLang |
| 结构化输出比例高 | SGLang |
| 仅 NVIDIA、形状稳定、追极致 | TRT-LLM |
| 多硬件/国产适配、模型杂 | vLLM |
| 集群级 PD 分离与 KV 路由 | Dynamo 或自研控制面（24/27） |

量化与投机解码的支持矩阵要逐项验：FP8/INT4/AWQ 后端、EAGLE/MTP 支持在各引擎不同代版本差异大，选型表必须带版本号。

## 4. 基准方法学与验收

- 统一口径：同硬件、同模型、同量化、同 SLO；用生产 trace 回放负载形状，报 TTFT/TPOT/goodput 与每有效 token 成本，**不只报峰值吞吐**。
- 中间指标解释差异：prefix 命中率、投机接受率、build/冷启动时间进 TCO。
- 常见坑：跨论文比不同口径的峰值；引擎版本漂移；benchmark 过拟合固定形状。

## 5. 迁移与共存

OpenAI-compatible API 作迁移边界（16 网关），多引擎共存 + 按负载路由（17）；引擎切换走回归门禁（29 篇第 6 节 + 主题五 37），先证质量不变再谈性能收益。

## 写在最后

下一篇：[语义缓存与请求级复用：Semantic Cache 与 Prompt Cache](/source/AI-Infra/3-大模型推理优化工程/39-语义缓存与请求级复用-SemanticCache-PromptCache)。