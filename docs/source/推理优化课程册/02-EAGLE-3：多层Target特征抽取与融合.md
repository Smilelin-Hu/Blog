# EAGLE-3：多层 Target 特征抽取与融合路径

EAGLE 系草稿器不在 token 空间自回归，而在 target 的 hidden 特征空间做外推：用 target 前向留下的特征训练一个轻量 head，推理期只跑 head 就能提议候选。EAGLE-3 的关键改动是抽取多层 target 特征并融合，让 draft 同时看到词法、句法与任务层信息，缓解单层特征对外推步数的限制。

![EAGLE-3：多层 Target 特征抽取与融合路径](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y13_l02_01.png)

## 1. 机制要点

- **特征来源**：低层 hidden 携带局部词法信息、中层携带句法语义、高层携带任务意图；融合（concat + MLP）后作为 draft head 的输入。
- **training-time test**：训练期让 head 在「target 真实特征」与「head 自回归外推特征」两种输入下都对齐 target 分布，推理期才敢只跑外推路径。
- **成本结构**：推理期 draft 侧只跑 head 与融合层，不跑 target 全模型；验证仍由 target 一次前向完成。

## 2. 实验闭环

```bash
python lesson/02-eagle-feature-path/run.py --check-only
python lesson/02-eagle-feature-path/run.py --output results/lesson-02-fixture.json
python lesson/02-eagle-feature-path/run.py --real --model /models/target --output results/gpu_result.json
```

- **输入**：target 模型与多层特征抽取配置、CUDA GPU。
- **输出**：各层特征贡献消融、acceptance 随外推步数的衰减曲线、cycle trace。
- **验收**：多层融合相对单层基线的 acceptance 提升可复算；输出与贪心基线一致；特征路径标记完整（哪些层参与融合可追溯）。

## 3. 判读纪律

- 消融要逐层做：只报「多层比单层好」不够，要给出每层的边际贡献，否则无法判断融合是否冗余。
- 衰减曲线比单点 acceptance 更有信息：外推 4 步与 8 步的接受率决定实际 draft 长度上限。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

EAGLE-3 的训练期测试与直接 token 预测对照见 [EAGLE-3：Training-Time Test 与直接 Token 预测](/source/AI-Infra/3-大模型推理优化工程/03-EAGLE-3-Training-TimeTest与直接Token预测)；本课聚焦特征路径的实验消融口径。