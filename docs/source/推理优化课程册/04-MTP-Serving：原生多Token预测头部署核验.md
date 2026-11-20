# MTP Serving：原生多 Token 预测头的部署核验

MTP（Multi-Token Prediction）把「多 token 提议」做进模型本体：主 head 之外挂若干 MTP head，一次 target 前向同时产出主输出与未来多个位置的候选。与外挂 draft 模型不同，MTP 的候选与主输出共享同一次前向的 hidden，部署核验的重点是 head 的启用方式、候选口径与验证闭环是否与训练期一致。

![Target hidden 复用：主 head 与 MTP head 各预测一位](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l04_03.png)

## 1. 机制要点

- **共享前向**：主 head 与 MTP head 复用同一次 target 前向的 hidden，候选几乎零额外前向成本。
- **head 顺序语义**：MTP head k 预测 t+k+1 位置，候选链的顺序与掩码必须和训练期定义一致，错序会静默降低接受率。
- **部署开关**：serving 侧需显式启用 MTP 候选与验证路径；只加载权重不开 head 等于退化为普通自回归。

## 2. 实验闭环

```bash
python lesson/04-mtp-serving/run.py --check-only
python lesson/04-mtp-serving/run.py --output results/lesson-04-fixture.json
python lesson/04-mtp-serving/run.py --real --model /models/mtp-target --output results/gpu_result.json
```

- **输入**：带 MTP head 的 target 模型、head 启用配置、CUDA GPU。
- **输出**：逐 head acceptance、启用/未启用对照 token/s、候选与主输出 token IDs。
- **验收**：启用 MTP 后输出与贪心基线一致；逐 head acceptance 可复算；head 错序对照实验接受率显著下降（证明顺序语义生效）。

## 3. 判读纪律

- 部署核验先验「开关真实生效」：启用/未启用对照的 token/s 与 acceptance 差异必须可见，否则配置可能没落地。
- 逐 head 报 acceptance：整体数字会掩盖某个 head 失效（例如 head 2 接受率近零）。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

MTP serving 的部署与核验展开见 [MTP Serving：原生多 Token 预测头的部署](/source/AI-Infra/3-大模型推理优化工程/05-MTPServing-原生多Token预测头的部署)；本课聚焦 head 启用与顺序语义的实验反证。