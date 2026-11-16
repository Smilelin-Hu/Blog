# 推理安全与在线护栏：Prompt Injection、Jailbreak 与内容过滤

主题五 13 是数据侧（投毒/注入/退出），主题四 28 是平台侧（身份/RBAC）；本文补 serving 链路侧：注入检测、越狱分类、输入输出内容过滤、在线 PII、拒答策略与水印。先立共识：guardrail 是 detective control，单层必被绕过，纵深防御才是工程形态。

## 1. 威胁模型与分层职责

- **direct jailbreak**：用户直接诱导违规输出。
- **indirect prompt injection**：指令藏在外联内容（网页、文档、工具返回）里，agentic 场景下可劫持工具调用权限，危害大于 direct。

| 层 | 归属 | 职责 |
|---|---|---|
| 数据侧 | 主题五 13 | 投毒、版权、退出机制 |
| 平台侧 | 主题四 28 | 身份、RBAC、运行时隔离、审计 |
| serving 侧 | 本文 | 输入/输出/动作三道 guard |

## 2. 输入侧：注入与越狱检测

- 分类器路线：PromptGuard/LlamaGuard 系微调小模型做注入/越狱二分类；启发式路线：指令-数据分离、delimiter/spotlighting 标记外部内容；辅以 perplexity/改写一致性检测。
- 实证边界：Hackett et al.（LLMSec 2025）与 arXiv 2504.11168 的自适应攻击可绕过主流 guardrail——**检测率与误报率必须同时报**，且按攻击集版本持续重测。
- indirect 注入的工程核心是权限分离：外部内容一律当数据；工具调用白名单 + 参数校验；高风险动作 human-in-the-loop（呼应 agent 系列 HITL）。检测器只是纵深的一层。

## 3. 输出侧：内容过滤、PII 与水印

- moderation 分类器 + 规则层：PII 用 regex/NER，凭据泄漏检测呼应 16 篇第 14 节的敏感日志口径。
- **流式过滤**：逐句增量审核 vs 整段审核，取舍是延迟与泄漏窗口——已吐出的 token 收不回，高敏场景宁可牺牲流式体验。
- 拒答策略：过拒伤可用性、漏拒伤安全；拒答率双向进 29 篇第 6 节质量门禁，安全与质量共用一套回归。
- 水印：生成侧统计水印用于溯源，对 paraphrase 鲁棒性有限，定位是「事后取证」而非「事前阻止」。

## 4. 工程形态：延迟、误报与纵深

- guardrail 独立服务/sidecar，小模型 CPU/GPU 混部，与 prefill 并行跑，延迟预算几十 ms 级；批量与缓存摊薄成本。
- 误报处置：白名单、申诉通道、灰度放量；red team 对抗回归集持续更新，攻击集与 benign 集双门禁。
- 纵深清单：guardrail + 权限分离 + 运行时隔离（主题四 28 篇第 6 节）+ 审计留存（主题四 28 篇第 8 节）。「guardrails alone are not enough」是 2025–2026 生产文献的一致结论。

## 5. 验收

攻击集绕过率、benign 集误报率、P99 附加延迟、流式泄漏窗口四项进验收单；red team 周期演练；与 29 篇第 6 节门禁耦合验证（注入劣化输出要能被质量门禁抓住）。

## 写在最后

下一篇：[推理引擎横向对比与选型：vLLM、SGLang、TensorRT-LLM 与 Dynamo](/source/AI-Infra/3-大模型推理优化工程/38-推理引擎横向对比与选型-vLLM-SGLang-TensorRT-LLM-Dynamo)。