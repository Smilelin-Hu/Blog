# Model Loading：权重清单、CPU 装载、H2D 与首轮生成

模型加载是一条多阶段流水线：权重清单解析 → CPU 装载 → H2D 搬运 → 首轮生成。各阶段成本量级不同（磁盘/内存/PCIe/算力），合并计时会掩盖瓶颈阶段。本课要求阶段不合并计量、模型真实跑在 CUDA 上、本地路径的权重清单 hash 可复现——清单不可复现时「加载优化」无法归因到具体权重版本。

## 1. 机制要点

- **阶段分离**：清单解析、CPU 装载、H2D、首轮生成四段分开计时；H2D 受 PCIe 带宽约束，常是被忽视的大头。
- **CUDA 真实性**：加载完成不等于在 GPU 上跑；首轮生成必须落在 CUDA 设备，否则计时口径错。
- **清单可复现**：本地权重路径的 manifest hash 可复算，加载结论才能绑定到权重版本。

## 2. 实验闭环

```bash
python lesson/21-model-loading/run.py --check-only
python lesson/21-model-loading/run.py --output results/lesson-21-fixture.json
python lesson/21-model-loading/run.py --real --model /models/target --output results/gpu_result.json
```

- **输入**：本地权重路径、CUDA GPU。
- **输出**：load phase breakdown、first generation、weight manifest hash。
- **验收**：阶段不合并；模型跑在 CUDA；本地路径 manifest 可复现。

## 3. 判读纪律

- 阶段 breakdown 是加载优化的唯一入口：只报总加载时间无法定位优化点。
- manifest hash 与权重版本绑定留存：换权重不重算 hash 的对比无效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

加载与冷启动的 serving 侧展开见本册 [22-Cold-Start](/source/推理优化课程册/22-Cold-Start：重复加载首请求与Warm请求)；权重供应链对照 [GitOps：环境晋级与渐进式发布](/source/AI-Infra/4-AI平台工程/24-GitOps-环境晋级与渐进式发布)。