# Compound AI：分类、证据生成与回答链路

Compound AI 系统把请求拆成有序阶段：分类（路由/意图）→ 证据生成（检索/工具）→ 回答。链路正确性依赖三件事：阶段按序执行、下游输入真实包含上游输出（lineage 可连）、任一阶段失败即停链（不允许带着坏证据继续回答）。本课用有序阶段记录与 lineage 链接核验闭环。

## 1. 机制要点

- **有序执行**：阶段顺序是语义契约（先分类再检索再回答），乱序会让证据与意图错配。
- **lineage 链接**：下游输入必须可追溯到上游输出 ID；断链意味着中间结果被替换或丢弃。
- **失败停链**：上游失败时下游不得用默认值/空证据继续，否则最终回答看似正常实则无据。

## 2. 实验闭环

```bash
python lesson/14-compound-chain/run.py --check-only
python lesson/14-compound-chain/run.py --output results/lesson-14-fixture.json
python lesson/14-compound-chain/run.py --real --endpoint http://compound:8000 --output results/gpu_result.json
```

- **输入**：compound 端点、含失败注入的任务集。
- **输出**：ordered stage records、lineage links、final output hash。
- **验收**：三阶段按序执行；下游输入包含上游输出；失败停链。

## 3. 判读纪律

- 失败注入是必做对照：不注入失败就证明不了「失败停链」真实生效。
- final hash 与 lineage 对齐复核：hash 一致但 lineage 断链的记录判无效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

Compound AI serving 的组件与链路展开见 [Compound AI Serving：Embedding、Reranker、LLM 与工具链](/source/AI-Infra/3-大模型推理优化工程/15-CompoundAIServing-Embedding-Reranker-LLM与工具链)；本课聚焦链路闭环与失败语义的实验口径。