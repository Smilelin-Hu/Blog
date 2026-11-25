# Multimodal：图像预处理、输入字节与端到端延迟

多模态请求的延迟不只在模型：图像分辨率决定预处理成本与输入字节数，进而影响传输与 prefill。本课用分辨率扫描把「预处理时间」与「推理时间」分开计量，并核验输入字节随分辨率真实变化、所有变体真实提交——避免把预处理开销算进模型延迟、或只跑部分变体就下结论。

## 1. 机制要点

- **两段计量**：预处理（解码/缩放/编码）与推理（prefill+decode）分开计时；混在一起无法定位优化点。
- **字节证据**：payload bytes 随分辨率变化是预处理真实生效的证据；字节不变说明缩放没落地。
- **变体完整性**：分辨率扫描的每个变体都要真实提交并留响应 hash，缺变体的扫描有偏。

## 2. 实验闭环

```bash
python lesson/13-media-preprocess/run.py --check-only
python lesson/13-media-preprocess/run.py --output results/lesson-13-fixture.json
python lesson/13-media-preprocess/run.py --real --endpoint http://vlm:8000 --resolutions 224,448,896 \
  --output results/gpu_result.json
```

- **输入**：VLM 端点、分辨率扫描配置、图像集。
- **输出**：resolution sweep、payload bytes、response hashes。
- **验收**：图像字节随分辨率变化；所有变体提交；预处理与推理时间分离。

## 3. 判读纪律

- 延迟归因先看两段计量：端到端变慢时先区分预处理还是推理，再谈优化。
- 响应 hash 留存用于复算与去重核对；无 hash 的扫描不可复核。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

多模态训练系统侧对照 [多模态与扩散模型训练系统](/source/AI-Infra/1-大模型训练优化/31-多模态与扩散模型训练系统)；本课聚焦 serving 侧预处理与延迟分离计量。