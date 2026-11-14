# Speculator 工程化：训练、评测、发布与漂移

一个 Speculator 在论文里快 2 倍，上线后却可能什么都没变快。原因通常不在算法，而在工程：训练数据与线上分布不一致、评测指标选错、发布没有绑定版本、上线后接受率悄悄漂移。

## 1. 训练数据：分布比算法更重要

常见数据来源五类：

1. 通用 instruction 数据；
2. coding / math 专项数据；
3. 真实匿名化 serving trace；
4. online teacher rollout；
5. 结构化输出与工具调用数据。

原因很直接：acceptance 依赖的是线上未来的条件分布。

$$
P_{serve}\left(x_{future}\mid context\right)
$$

一旦训练与线上偏移，\(D_{KL}(P_{serve}\Vert P_{train})\) 上升，最先反应出来的就是**逐位置接受率下降**。所以 Speculator 的数据工程优先级高于「换个更花哨的草拟器」。

## 2. 离线评测的四组指标

| 组别 | 指标 | 为什么需要 |
|---|---|---|
| Token | top-1 accuracy、position-wise accuracy、prefix survival、mean accepted length | 决定「能接受多长」 |
| Cost | draft forward 次数、draft ms、额外显存、验证节点/Token 数 | 决定「值不值」 |
| End-to-End | TPOT、output token/s、batch throughput、P50/P99、GPU-hour/output token | 决定「真实收益」 |
| Quality | 语义一致性、结构化输出合法、LoRA/量化/stop sequence 组合路径 | 决定「能不能发」 |

第三组最容易被忽略：**离线单请求快，不代表在线批量也快**；第四组最容易被跳过：lossless 投机仍需验证实现没有改变 Target 的语义，结构化输出、LoRA、量化任意组合都要单独测。

## 3. Speculator Registry

一个可运营的 registry 至少记录：

```yaml
speculator_id: dflash-qwen3-8b-code-v3
target_model: qwen3-8b
model_revision: ...
tokenizer_revision: ...
algorithm: dflash
max_draft_tokens: 16
training_domain: code
runtime_min_version: ...
verified_hardware: [H100, B200]
compatibility:
  lora: conditional
  structured_output: tested
status: canary
```

四个价值：防止 Target 升级后错误复用旧 Speculator；支持 Canary/Rollback；让 Router 能按负载选型；保留真实性能证据（而不是论文数字）。

## 4. 动态 Speculator 策略

候选集合可以是：

```text
No speculation / MTP / EAGLE-3 / P-EAGLE / DFlash / DSpark
```

策略输入：model id、adapter id、请求域、prompt 长度、预期输出长度、当前并发、近期接受率、SLO 档位。
策略输出：用哪个算法、草拟深度/块大小、验证预算。

一个可用的打分：

$$
\mathrm{Score}_j = \mathrm{PredictedSavedTime}_j - \lambda_1 \mathrm{VerifyCost}_j - \lambda_2 \mathrm{MemoryCost}_j
$$

$$
j^\ast = \arg\max_j \mathrm{Score}_j
$$

**若所有 \(\mathrm{Score}_j \le 0\)，就直接关闭 speculation。** 这条兜底规则比任何调参都重要——它防止「配置里开了投机就永远开着」。

## 5. Acceptance Drift

上线后接受率下降的常见原因：模型版本变化、业务域变化、新 LoRA 上线、Prompt 模板改动、采样参数改动。

所以监控至少要按五个维度切分：**model / adapter / tenant-domain / concurrency bucket / algorithm**。只报全局平均 acceptance，完全可能掩盖某个大客户已经退化。

## 6. Canary 与回滚

```text
5% 流量 → 检查正确性 / P99 / acceptance / GPU cost
   ↓ 通过
25% → 50% → 100%
   ↓ 任一步失败
回滚到已验证 speculator（并保留问题请求用于复现）
```

关键点：Canary 的对照组必须跑**同一个 workload 与同一套配置**，否则你比较的是两个世界。

## 7. 一页检查清单

- [ ] 训练数据包含线上主流域，并记录数据版本
- [ ] 四组指标齐全，离线已分域出数
- [ ] Registry 绑定 target/tokenizer/runtime 版本
- [ ] 策略有「全负则关闭」的兜底
- [ ] Drift 监控按 model/adapter/tenant/并发/算法切分
- [ ] Canary 有对照与回滚路径
- [ ] 性能发布同时通过质量门禁（结构、采样、结束原因）

## 写在最后

投机解码这条线到这里闭环：算法决定上限，数据分布决定实得，评测口径决定能不能发现问题，发布流程决定出问题时能不能退回来。

下一段换负载：Reasoning、Agentic、Structured、Multimodal、Compound AI——这五类工作负载会把「一次请求 = 一次 Prefill + 一段 Decode」这个假设逐一打破。
