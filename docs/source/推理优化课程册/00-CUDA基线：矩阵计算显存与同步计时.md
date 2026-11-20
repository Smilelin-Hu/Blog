# CUDA 基线：矩阵计算、显存与同步计时

推理优化的一切结论都要落在可复现的计时上，而计时的第一道坑是 CUDA 的异步语义：kernel 发射返回不代表执行完成。本课把「矩阵计算 + 显存占用 + 同步计时」作为基线实验，先建立一把可信的尺子，再谈任何优化收益。

## 1. 为什么同步计时是基线的第一件事

CPU 侧调用 CUDA kernel 后立即返回，若用 host 时钟直接包裹调用区间，量到的是发射开销而非执行时间。可信计时只有两条路：

- **CUDA Event**：在 stream 上记录起止 event，`elapsed_time` 量的是设备侧区间，天然包含排队与执行；
- **显式同步后计时**：`torch.cuda.synchronize()` 之后再读 host 时钟，代价是把异步流水线拍平，只适合粗粒度核对。

显存占用同理要看峰值而非瞬时：`max_memory_allocated` 与 `memory_reserved` 口径不同，前者是分配器高峰、后者含缓存池，混用会得出矛盾的「优化收益」。

## 2. 实验闭环

实验入口为单文件 `run.py`，默认跑确定性 Fixture 只验证控制逻辑；加 `--real` 才进入真实 CUDA 路径：

```bash
python lesson/00-cuda-baseline/run.py --check-only
python lesson/00-cuda-baseline/run.py --output results/lesson-00-fixture.json
python lesson/00-cuda-baseline/run.py --real --output results/gpu_result.json
```

- **输入**：CUDA GPU；矩阵规模与迭代次数作为扫描变量。
- **输出**：kernel 计时序列、显存峰值、同步方式标记。
- **验收**：计时口径自洽（event 与同步后计时在误差带内一致）、显存峰值可复算、规模扫描单调性符合预期。

真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 3. 判读纪律

- 只有 `source=measured` 的报告可以用于性能或发布结论；Fixture 结果只证明控制逻辑正确。
- 计时报告必须带同步方式、迭代次数、warmup 次数与规模参数，缺一项即不可比。
- 基线一旦确立就冻结口径：后续课次的收益都相对这把尺子度量，中途换计时方式等于换尺子。

## 4. 与主题笔记的关系

本课是实验基线，方法论层面的指标体系（MFU/HFU、带宽墙、数量级估算）见 [AI 系统性能工程](/source/AI-Infra/2-AI系统性能工程/README) 与 [GPU 性能分析方法](/source/AI-Infra/2-AI系统性能工程/12-GPU性能分析方法)。