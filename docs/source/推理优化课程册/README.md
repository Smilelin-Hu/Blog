# 推理优化课程册

按课次整理的推理优化实验笔记：每课一篇，先讲机制，再给实验闭环（Fixture / 真实路径、输入输出与验收），最后落判读纪律。与 [AI Infra 主题笔记](/source/AI-Infra/README) 的区别在于组织方式——主题笔记按知识域重组，本册保留课程原课次顺序，聚焦「实验怎么做、结论怎么判」。

全册 30 课实验 + 6 个综合项目，按课程原课次顺序整理完毕。

## 目录

- [00-CUDA基线：矩阵计算显存与同步计时](/source/推理优化课程册/00-CUDA基线：矩阵计算显存与同步计时)
- [01-投机解码：Draft提议与Target验证](/source/推理优化课程册/01-投机解码：Draft提议与Target验证)
- [02-EAGLE-3：多层Target特征抽取与融合](/source/推理优化课程册/02-EAGLE-3：多层Target特征抽取与融合)
- [03-P-EAGLE：并行候选分支与批量验证](/source/推理优化课程册/03-P-EAGLE：并行候选分支与批量验证)
- [04-MTP-Serving：原生多Token预测头部署核验](/source/推理优化课程册/04-MTP-Serving：原生多Token预测头部署核验)
- [05-Block-Draft：候选块宽度深度与验证成本](/source/推理优化课程册/05-Block-Draft：候选块宽度深度与验证成本)
- [06-DFlare：Drafter特征融合的层数扩展](/source/推理优化课程册/06-DFlare：Drafter特征融合的层数扩展)
- [07-Diffusion-Draft-Tree：树预算叶路径与批量验证](/source/推理优化课程册/07-Diffusion-Draft-Tree：树预算叶路径与批量验证)
- [08-DSpark：按Draft置信度决定是否提议](/source/推理优化课程册/08-DSpark：按Draft置信度决定是否提议)
- [09-Speculator-Artifact：版本绑定与双端点Smoke](/source/推理优化课程册/09-Speculator-Artifact：版本绑定与双端点Smoke)
- [10-Reasoning-Token：输出预算完成率与尾延迟](/source/推理优化课程册/10-Reasoning-Token：输出预算完成率与尾延迟)
- [11-Agentic-Task：并行分支汇聚与端到端证据](/source/推理优化课程册/11-Agentic-Task：并行分支汇聚与端到端证据)
- [12-Grammar：受约束JSON输出与逐请求校验](/source/推理优化课程册/12-Grammar：受约束JSON输出与逐请求校验)
- [13-Multimodal：图像预处理输入字节与端到端延迟](/source/推理优化课程册/13-Multimodal：图像预处理输入字节与端到端延迟)
- [14-Compound-AI：分类证据生成与回答链路](/source/推理优化课程册/14-Compound-AI：分类证据生成与回答链路)
- [15-Gateway开销：直连与Gateway成对计量](/source/推理优化课程册/15-Gateway开销：直连与Gateway成对计量)
- [16-Replica-Set：Inflight与EWMA负载路由](/source/推理优化课程册/16-Replica-Set：Inflight与EWMA负载路由)
- [17-Prefix-Cache：前缀亲和选路与缓存指标](/source/推理优化课程册/17-Prefix-Cache：前缀亲和选路与缓存指标)
- [18-LoRA-Adapter：多模型ID交替与切换延迟](/source/推理优化课程册/18-LoRA-Adapter：多模型ID交替与切换延迟)
- [19-Multi-Model-Pool：热门突发与冷模型穿插](/source/推理优化课程册/19-Multi-Model-Pool：热门突发与冷模型穿插)
- [20-Model-Registry：稳定版Canary门禁与回滚](/source/推理优化课程册/20-Model-Registry：稳定版Canary门禁与回滚)
- [21-Model-Loading：权重清单CPU装载H2D与首轮生成](/source/推理优化课程册/21-Model-Loading：权重清单CPU装载H2D与首轮生成)
- [22-Cold-Start：重复加载首请求与Warm请求](/source/推理优化课程册/22-Cold-Start：重复加载首请求与Warm请求)
- [23-Control-Plane：Desired-Actual-Diff与Probe](/source/推理优化课程册/23-Control-Plane：Desired-Actual-Diff与Probe)
- [24-Heterogeneous-GPU：逐卡容量与延迟画像](/source/推理优化课程册/24-Heterogeneous-GPU：逐卡容量与延迟画像)
- [25-GPU-Bin-Packing：分配打洞与大块探针](/source/推理优化课程册/25-GPU-Bin-Packing：分配打洞与大块探针)
- [26-LLM-Autoscaling：容量校准需求窗口与状态机](/source/推理优化课程册/26-LLM-Autoscaling：容量校准需求窗口与状态机)
- [27-Capacity-Planning：并发×输出长度实测矩阵](/source/推理优化课程册/27-Capacity-Planning：并发×输出长度实测矩阵)
- [28-Distributed-Trace：CPU-CUDA-Span与Chrome-Trace](/source/推理优化课程册/28-Distributed-Trace：CPU-CUDA-Span与Chrome-Trace)
- [29-Inference-Economics：Token吞吐功耗与成本](/source/推理优化课程册/29-Inference-Economics：Token吞吐功耗与成本)
- [30-项目一：Next-Generation-Speculator-Benchmark](/source/推理优化课程册/30-项目一：Next-Generation-Speculator-Benchmark)
- [31-项目二：异构推理工作负载基准平台](/source/推理优化课程册/31-项目二：异构推理工作负载基准平台)
- [32-项目三：生产级AI-Gateway与Smart-Router](/source/推理优化课程册/32-项目三：生产级AI-Gateway与Smart-Router)
- [33-项目四：多租户多模型多LoRA-Serving](/source/推理优化课程册/33-项目四：多租户多模型多LoRA-Serving)
- [34-项目五：GPU-Fleet-Planner与SLA感知扩缩容](/source/推理优化课程册/34-项目五：GPU-Fleet-Planner与SLA感知扩缩容)
- [35-项目六：生产级LLM推理平台](/source/推理优化课程册/35-项目六：生产级LLM推理平台)

## 判读总纪律

- 默认 Fixture 只验证控制逻辑；加 `--real` 才进入真实 CUDA / 端点路径。
- 只有 `source=measured` 的报告可用于性能或发布结论。
- 真实前置条件不足时 `status=precondition_failed`、退出码 2，不回退 CPU 冒充实测。
- 投机类课次一律先验「输出与贪心基线一致」，再谈加速；acceptance 必须可由 trace 复算。