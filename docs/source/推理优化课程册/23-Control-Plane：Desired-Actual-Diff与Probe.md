# Serving Control Plane：Desired/Actual Diff 与 Probe

控制面靠 reconcile 闭环：声明 desired revision，发现所有端点，比对 actual 状态，diff 驱动动作。本课核验三件事：desired revision 显式声明、每个端点都被发现（无遗漏）、diff 为空仅当证据匹配（而非探针缺失导致的假空）。假空 diff 会让控制面以为一切正常而停止修复。

## 1. 机制要点

- **desired 显式化**：revision 必须显式声明并版本化，隐式默认会让 reconcile 目标漂移。
- **发现完整性**：端点发现遗漏会让 diff 漏掉坏副本，控制面「看不见」即「不修」。
- **diff 空的条件**：diff 为空必须建立在探针证据齐全之上；探针失败/缺失时 diff 应为 unknown 而非空。

## 2. 实验闭环

```bash
python lesson/23-control-plane/run.py --check-only
python lesson/23-control-plane/run.py --output results/lesson-23-fixture.json
python lesson/23-control-plane/run.py --real --control-url http://cp:8000 --desired-rev r2 \
  --output results/gpu_result.json
```

- **输入**：控制面端点、显式 desired revision、端点集（含可注入探针失败）。
- **输出**：reconciliation actions、actual state、probe records。
- **验收**：desired revision 显式；每端点被发现；diff 空仅当证据匹配。

## 3. 判读纪律

- 探针失败注入必做：注入后 diff 应变 unknown/非空并触发修复动作，证明「假空」被防住。
- reconcile 动作要附触发 diff 快照：无 diff 依据的动作不算闭环。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

控制面机制展开见 [LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo](/source/AI-Infra/3-大模型推理优化工程/24-LLMServingControlPlane-RayServe-KServe与Dynamo)；平台侧控制器模式对照 [Kubernetes API：控制器与 Operator 平台模式](/source/AI-Infra/4-AI平台工程/03-KubernetesAPI-控制器与Operator平台模式)。