# Capacity Planning：并发 × 输出长度实测矩阵

容量规划的核心是「并发 × 输出长度」二维实测矩阵：每个格子独立请求实测 P95 延迟/吞吐，可行前沿（feasible frontier）由实测 P95 划出而非线性外推。两轴都必须真实变化、每格独立请求——复用请求或单轴扫描画出的「容量面」是假的，SLO 承诺会落在不可行区。

## 1. 机制要点

- **二维矩阵**：并发与输出长度交互影响批处理与 KV 占用，单轴扫描无法捕捉交互效应。
- **独立请求**：每格独立请求集，避免缓存/预热跨格污染。
- **实测前沿**：可行前沿用实测 P95 划界；外推前沿会把 SLO 承诺放进未验证区。

## 2. 实验闭环

```bash
python lesson/27-capacity-matrix/run.py --check-only
python lesson/27-capacity-matrix/run.py --output results/lesson-27-fixture.json
python lesson/27-capacity-matrix/run.py --real --endpoint http://serving:8000 --concurrency 1,8,32 --out-lens 128,512,2048 \
  --output results/gpu_result.json
```

- **输入**：serving 端点、并发×输出长度网格、SLO 阈值。
- **输出**：capacity matrix、feasible frontier、raw records。
- **验收**：两轴都变化；每格独立请求；前沿用实测 P95。

## 3. 判读纪律

- 矩阵要附 raw records：聚合矩阵不可复算时前沿不可审计。
- SLO 承诺只落在实测可行区内；外推区承诺必须标注未验证。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

容量规划与 headroom 的机制展开见 [Capacity Planning：流量预测、Headroom 与 GPU Fleet](/source/AI-Infra/3-大模型推理优化工程/28-CapacityPlanning-流量预测-Headroom与GPUFleet)；本课聚焦实测矩阵与可行前沿的口径。