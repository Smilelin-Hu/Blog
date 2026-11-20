# Multimodal：图像预处理、输入字节与端到端延迟

生成多个真实图像尺寸，分别记录编码成本、请求大小和模型端到端延迟。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/13-media-preprocess/run.py --check-only
python lesson/13-media-preprocess/run.py --output results/lesson-13-media-preprocess-fixture.json
python lesson/13-media-preprocess/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_VISION_MODEL_ID --image data/sample.png \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- local image
- vision-language endpoint
- Pillow

## 输出

- resolution sweep
- payload bytes
- response hashes

## 验收

- image bytes change with resolution
- all variants are submitted
- preprocess and inference time are separate

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
