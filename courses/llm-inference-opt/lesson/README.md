# 课时实验

每个编号目录都是独立实验，只需进入对应目录查看 `README.md` 和运行 `run.py`。

- `run.py`：默认运行 Fixture；加 `--real` 才进入真实 CUDA 或端点路径。
- `requirements.txt`：本类实验的依赖说明。
- 内部运行库已并入各自的 `run.py`，压缩包不再暴露构建脚本、测试、清单或源码库目录。

## 目录

- `00-cuda-baseline/` — CUDA Baseline：矩阵计算、显存与同步计时
- `01-speculative-decode/` — Speculative Decoding：Draft 提议与 Target 验证
- `02-eagle-feature-path/` — EAGLE-3：多层 Target 特征抽取与融合路径
- `03-parallel-drafter/` — P-EAGLE：并行候选分支与 Target 批量验证
- `04-mtp-serving/` — MTP Serving：原生多 Token 预测头的部署核验
- `05-block-draft/` — Block Draft：候选块宽度、深度与验证成本
- `06-dflare-scaling/` — DFlare：Drafter 特征融合的层数扩展
- `07-diffusion-tree/` — Diffusion Draft Tree：树预算、叶路径与批量验证
- `08-confidence-scheduler/` — DSpark：按 Draft 置信度决定是否提议
- `09-speculator-artifact/` — Speculator Artifact：版本绑定与双端点 Smoke Benchmark
- `10-reasoning-tokens/` — Reasoning Token：输出预算、完成率与尾延迟
- `11-agentic-dag/` — Agentic Task：并行分支、汇聚与端到端证据
- `12-structured-output/` — Grammar：受约束 JSON 输出与逐请求校验
- `13-media-preprocess/` — Multimodal：图像预处理、输入字节与端到端延迟
- `14-compound-chain/` — Compound AI：分类、证据生成与回答链路
- `15-gateway-overhead/` — OpenAI-Compatible API：直连与 Gateway 成对开销
- `16-load-router/` — Replica Set：基于 Inflight 与 EWMA 的负载路由
- `17-prefix-affinity/` — Prefix Cache：前缀亲和选路与缓存指标
- `18-lora-switch/` — LoRA Adapter：多模型 ID 交替请求与切换延迟
- `19-model-pool/` — Multi-Model Pool：热门模型突发与冷模型穿插
- `20-canary-release/` — Model Registry：稳定版、Canary 门禁与回滚
- `21-model-loading/` — Model Loading：权重清单、CPU 装载、H2D 与首轮生成
- `22-cold-start/` — Cold Start：重复加载、首请求与 Warm 请求
- `23-control-plane/` — Serving Control Plane：Desired/Actual Diff 与 Probe
- `24-heterogeneous-gpu/` — Heterogeneous GPU：逐卡容量与延迟画像
- `25-fragmentation/` — GPU Bin Packing：分配、打洞与大块探针
- `26-autoscaling/` — LLM Autoscaling：容量校准、需求窗口与状态机
- `27-capacity-matrix/` — Capacity Planning：并发 × 输出长度实测矩阵
- `28-profiler-trace/` — Distributed Trace：PyTorch CPU/CUDA Span 与 Chrome Trace
- `29-inference-economics/` — Inference Economics：Token 吞吐、GPU 功耗与成本
