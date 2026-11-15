# DataTrove、NeMo Curator、Ray 与 Spark 数据流

## 1. 本文要解决的工程问题

团队先选了框架再设计数据流，结果小文件、GPU 推理、Shuffle 和失败重放分别落在不合适的执行模型里，迁移成本高于处理成本。

本文围绕一个可执行判断展开：怎样在 DataTrove、NeMo Curator、Ray 与 Spark 之间选择可重放的数据执行面？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![数据流与执行面选择](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l06_01.png)

## 2. 本文交付物与判定标准

本文的核心决定是：先按算子状态、数据规模、资源类型、流式需求和容错语义拆工作负载，再选择 DataTrove、NeMo Curator、Ray Data 或 Spark。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：同一逻辑流水线在候选执行面上使用相同输入和门禁，报告吞吐、峰值内存、重试语义、产物一致性与运维复杂度。

围绕“DataTrove、NeMo Curator、Ray 与 Spark 数据流”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“DataTrove、NeMo Curator、Ray 与 Spark 数据流”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

单机样例用于验证接口和语义，不能外推目标集群上的调度、网络和对象存储成本。

### 3.1 业务背景与失败模式

大模型数据流水线同时包含顺序扫描、逐文档 Map、过滤、统计、模型推理、全局去重、分组聚合、Join、Shuffle、采样与分片写出。它既有大量可流式的窄依赖，也有必须重分布数据的宽依赖；既有 CPU 文本算子，也有 GPU 分类器和 Embedding；既要求吞吐，又要求对象级血缘、确定性、失败重跑与发布总账。任何单一框架都不会自动满足所有目标。

DataTrove 强调由 Reader、Filter、Extractor、Writer 等处理块组成的可复用语料流水线，以及由不同 Executor 执行同一 Pipeline；NeMo Curator 提供面向文本与多模态数据整理的 Stage、Task 和执行后端，把 CPU/GPU 资源与处理步骤结合；Ray Data 把数据集逻辑计划翻译成流式物理算子，以 Task 或 Actor 执行批处理和模型推理；Spark 则以成熟的分区、Stage、Shuffle、容错、SQL/DataFrame 与大规模集群生态处理结构化和宽依赖工作负载。四者解决问题的抽象层次并不完全相同，因此不是简单“四选一”。

工程上最危险的决策是因为团队熟悉某个 API，就把所有阶段硬塞进去：在文档 Pipeline 里实现一次全局 Join，在 Spark Python UDF 里逐条加载 GPU 模型，在 Ray Actor 中把全部数据收集到 Driver，或只靠任务完成标记宣称数据发布完整。这些方案小样本能跑，大规模时会暴露网络、序列化、显存、重试语义与正确性问题。

本文从数据流语义出发：先区分窄依赖与宽依赖、批与流、Task 与 Actor、物理分区与逻辑文档；再理解四类工具最擅长的边界；最后设计可混合使用但不丢 Manifest、Recipe 和血缘的一条生产流水线。目标不是背诵参数，而是能够解释为什么某一 Stage 由某一执行引擎承担、失败后从哪里恢复、数据如何对账以及成本如何归属。

### 3.2 学习目标与能力清单

### 2.1 能力目标

完成后应能把语料处理 DAG 拆成可流式 Map/Filter、状态化 Actor、分组/Join/Shuffle、GPU Batch Inference 和 Materialization 边界；能解释 DataTrove Pipeline Block 与 Executor、NeMo Curator Pipeline/Stage/Task/Backend、Ray Data Logical/Physical Operator 与 Block、Spark DataFrame/RDD Partition 与 Stage 之间的关系；能依据状态、资源、数据倾斜、容错与生态选择执行路径。

还应能为每个 Stage 定义输入输出 Manifest、分区函数、资源预算、幂等提交、重试范围和统计总账；能识别 Driver OOM、对象存储爆炸、Shuffle 热点、Python 序列化、Actor 模型重复加载、GPU 批次不均与小文件问题；能用 CPU 机制实验模拟流式窄依赖和宽依赖屏障，并在通用 CUDA GPU 上验证单 GPU Actor/进程对固定数据分片的真实消费。

### 2.2 验收边界

本文不宣称某个框架在所有集群上绝对更快。吞吐取决于数据格式、对象存储、集群网络、Python/C++ 边界、资源规格、版本和配置，必须在固定 Manifest 上实测。示例中的框架比较是工程模型，不是品牌排名。API 会演进，生产实现应以当时锁定的官方版本与文档为准。

真实硬件路径要求至少一张 CUDA GPU 与可用 PyTorch。若不满足，输出结构化 `skipped`，不把 CPU 数据当作 CUDA 实测。CUDA 实验验证资源放置、分片、批处理、聚合和错误边界，不代表大集群网络与调度性能。

### 2.3 与相邻篇目的边界

前一篇定义了 WARC、HTML、PDF、代码与对话的解析契约，本文把这些 Document/Unit 作为数据流输入；下一篇深入数据格式、Shard、索引、流式读取与缓存。本文会讨论物理布局对执行的影响，但不展开每种格式的编码细节。去重、质量、混合与后训练篇目会复用这里的 DAG/Shuffle/GPU Stage 模型。

### 3.3 实验准备与责任边界

### 3.1 记录级无状态 Map

无状态 Map 对每个 Document 或 Unit 独立变换，例如 Unicode 规范候选、长度统计、规则特征和 Token 计数。它只有窄依赖：一个输入分区可在本地生成对应输出，不需要与其他分区交换。相邻无状态 Map 通常可以融合，减少序列化与中间写出。

融合并非越多越好。不同 Stage 可能有不同资源、依赖和失败语义；把轻量解析与高风险模型推理融合，会使重试昂贵且镜像巨大。是否融合要看资源兼容、重用中间结果、观测边界与发布需求，而不是只看少一次函数调用。

### 3.2 Filter 与 Side Output

Filter 把记录分为保留与拒绝，但生产系统不能只返回布尔值。拒绝记录至少产生 reason_code、Stage、Recipe 和必要统计；高风险对象还需 Side Output 到隔离区。输入数等于保留、拒绝、隔离与失败之和。框架若只支持 `filter()`，可在前一 Map 生成 decision 字段，再分别写出候选与审计统计。

过滤率高会改变下游分区平衡。若九成记录在早期删除，原有分区可能出现大量空任务；可以在明确 Materialization 后 Coalesce，但重分区会影响稳定顺序和恢复，需保存新 Manifest。

### 3.3 FlatMap

解析、分块和附件展开是一对多 FlatMap。一个输入可能产生零到许多 Unit，必须设置输出数量/字节预算并保存父子关系。只看输出记录数无法判断输入覆盖，因此 Document 级终态和 Unit 级结果分开对账。FlatMap 是重尾来源：一本 PDF 或一个大仓库可产生数万个 Unit，分片估算要用历史展开率。

### 3.4 Stateful Map 与 Actor

模型推理、Tokenizer、语言识别和复杂解析器常需昂贵初始化。用长寿 Actor 在进程内复用模型/Grammar/连接，比每 Task 加载一次高效。Actor 同时引入状态风险：缓存污染、内存增长、随机状态、配置热更新和任务失败后的重建。业务输出必须只依赖明确输入和固定模型，Actor 内部缓存只能优化，不能改变语义。

Actor 池大小由 GPU/CPU 和模型副本决定。一个 Actor 占一 GPU 并用批次推理是常见路径；小模型可多个 Actor 共享 GPU 但会竞争显存与 Kernel；大模型可能跨 GPU 张量并行，这又改变 Stage 调度单位。资源声明必须对应真实占用。

### 3.5 GroupBy 与 Reduce

语言/域统计、域名计数、哈希桶去重和质量直方图需要按 Key 聚合。若 Key 分布跨分区，就触发 Shuffle。优先使用可结合的局部聚合：每分区先生成 Count/Sketch/TopK，再跨分区 Merge，减少网络。把所有文档按域名 `groupBy` 成列表容易让热点域 OOM，改用 `reduceByKey` 式累计或有界结构。

聚合函数必须满足并行重排需要的结合性，浮点求和顺序仍可能产生微小差异。需要确定性时使用整数计数、固定精度或稳定归并顺序，并声明成本。

### 3.6 Join

Source Registry、退出列表、域名评分、去重代表与基准污染清单需要 Join。小维表可广播到 Worker，避免全量 Shuffle；大表按稳定 Key 共分区或使用存储系统索引。广播前验证大小与版本，Driver 收集大表会 OOM。Join 类型决定总账：inner 会丢无匹配记录，left join 能显式保留 Unknown；治理字段通常不应 inner 静默删除。

Join 输入与输出都固定 Manifest/Version。外部在线 KV 查询看似省 Shuffle，却引入服务延迟、限流与运行中值变化；可以使用快照、批量预取或带版本 Decision Token。

### 3.7 Shuffle

Shuffle 把相同 Key 记录送到相同目标分区，代价包括序列化、网络、磁盘 spill、文件和失败重算。去重、全局排序、随机重排、Join、GroupBy 与 Repartition 都可能触发。设计 DAG 时应把 Shuffle 当显式物理边界，估算输入字节、Key 数、倾斜、目标分区和本地磁盘。

Shuffle 后的元素顺序通常不应假设稳定。需要确定性数据发布时，在目标分区内按稳定 Key 排序，并让 Shard ID 依赖分区函数与输入版本。全局排序成本很高，若训练只需确定性伪随机顺序，可以用哈希 Key 分区并分区内排序。

### 3.8 Barrier 与 Materialization

物化增加存储成本，但可以缩短故障重算链。

有些 Stage 需要所有上游结果完成才能继续：全局阈值计算、去重代表选择、数据卡发布和一致性检查。Materialization 把流式 DAG 切成可恢复 Commit，允许下游只读已验证结果。边界太少会让失败重算长链，边界太多会产生 IO 与小文件。选择依据是宽依赖、昂贵 Stage、跨资源池、复用和治理发布。

Materialization 不是随便写临时目录。它需要输入/输出 Manifest、Schema、统计、摘要和原子 Commit，只有完成标记与总账同时成立才可消费。

## 4. DataTrove：面向语料处理块与任务恢复的 Pipeline

### 4.1 核心心智模型

DataTrove 把 Reader、Extractor、Filter、Stats、Writer 等步骤组成 Pipeline，再交给本地、多进程或集群 Executor。Pipeline 步骤描述文档如何流过，Executor 描述任务在哪里运行。相同步骤可迁移执行环境，适合把语料清洗逻辑与调度平台分离。

工程价值在于常见语料操作有统一 Document 和统计接口，步骤可组合，执行器能按 Task 并行并记录日志、统计与完成情况。它更接近“领域化流水线工具箱”，而不是通用 SQL/Shuffle 引擎。全局去重往往需要多 Stage Pipeline 和中间结果，而不是在单条生成器链里解决。

### 4.2 Reader 与文件分配

Reader 决定哪些输入文件/Shard 由哪个 Task 消费。任务数必须与文件布局和成本匹配；大量小文件造成打开请求，少量巨文件造成长尾。若重跑时改变总 Task 数，文件到 Task 的分配可能变化，完成标记不再安全复用。因此输入 Manifest、Task 数和分配算法属于执行身份。

自定义 Reader 要保证每个 Document 稳定 ID、Source/Shard 血缘和错误终态。不能让某一行 JSON 异常终止整个文件且无偏移记录，也不能在 Reader 内部随机列目录。输入列表在 Job 创建时固定。

### 4.3 Pipeline Block

每个 Block 应有单一语义、明确配置和可聚合 Stats。轻量、相同资源的逐文档 Block 可以在进程内流式串联，避免中间落盘。需要全局信息、GPU、不同安全边界或复用的 Block 拆成新 Stage。Block 输出不得依赖隐藏全局变量或处理顺序。

Filter 返回保留/拒绝时同步更新 reason 统计；Writer 只写当前 Task 临时位置，完成后原子提交。自定义 Block 把版本与代码摘要进入 Recipe，不能用类名代表全部语义。

### 4.4 Executor 与 Task 完成

Executor 负责启动多个 Task、写日志和统计、记录完成 Task 并在重启时跳过已完成部分。完成标记只能表示该 Task 输出已完整提交，不能在 Writer 尚未 flush 或对象未可见时先写。日志目录不能被不同 Pipeline 共用，否则配置、完成与统计覆盖。

重跑必须保持输入、Pipeline、Task 总数与分配不变。若改变过滤阈值或任务数，创建新 Job/日志路径与输出前缀。生产系统在 DataTrove 完成记录之外再做 Manifest 总账和发布 Commit，避免把文件存在当数据正确。

### 4.5 统计

DataTrove 步骤可记录样本处理、过滤与原因统计。统计在 Task 内累积再归并，比每 Document 写监控指标高效。自定义指标需可结合、类型稳定并限制 Key 基数；Source ID、URL 不直接成为监控标签。Task stats 也进入 Job 总账，发现输入与输出不平时阻止发布。

统计文件与内容输出有同一 Task Attempt 关系。推测/重试产生多个 Attempt 时只聚合获胜提交，否则指标翻倍。长期分析保留 Recipe、Source 和时间切片。

### 4.6 适合与不适合

适合：大量独立文档的读取、解析、规则清洗、质量特征、语言过滤、采样和写出；基于文件/Task 的可恢复批处理；希望复用语料领域组件。需要精心设计：全局模糊去重、大规模 Join、多轮迭代算法、强交互 SQL 和异构 GPU 流水。后者可以分阶段使用专用组件，再把结果回到 DataTrove Document 流。

不应把“不擅长”理解为不能实现，而是实现的物理代价、运维复杂度和团队可见性是否合理。选型必须看主导 Stage。

## 5. NeMo Curator：资源感知的数据整理 Stage

### 5.1 核心抽象

NeMo Curator 面向大规模文本、图像、视频与音频数据整理，使用 Pipeline 组织 Processing Stage，Task 类型承载 DocumentBatch、ImageBatch、VideoTask 等工作，执行后端把 Stage 映射到分布式资源。它把数据整理算法与 CPU/GPU 资源声明结合，适合模型化分类、Embedding、去重与多模态处理。

Stage 可能是简单处理，也可能是 Composite Stage，在执行计划中分解为多个步骤。设计时要查看真正物理 Stage、Materialization 和资源，而不能只凭顶层一行 API 判断成本。

### 5.2 Backend 选择

后端能力随版本演进，常见 Ray Data/Actor Pool 路径以及面向流式、自动扩缩和容错的执行引擎。选择后端看 Task 类型、是否流式、模型是否需要 Actor 状态、Stage 能否融合、集群资源与故障需求。Recipe 必须锁定 NeMo Curator 及后端版本，因为默认执行行为可能改变。

团队不应把后端当透明细节。相同 Pipeline 在不同后端的分区、顺序、故障与指标可能不同，需要分别做 Golden 与性能验收。

### 5.3 CPU/GPU Stage

文本规则与解析使用 CPU Stage，模型分类、Embedding、视觉/视频特征使用 GPU Stage。每 Stage 声明 CPU、GPU 与内存，调度器才能做资源放置。CPU 预处理和 GPU 推理可以流式衔接，但两侧吞吐不匹配时需要有界 Block/Batch 和背压。

GPU Stage 通常使用 Actor 复用模型。初始化加载权重、Tokenizer 和编译 Warmup 计入启动成本；批次按 Token、像素或帧而非记录数装箱；OOM 降级属于显式 Variant。通用 CUDA 可各放一个 Actor 处理独立批次，但不自动代表多机扩展。

### 5.4 多模态 Task

Image、Video、Audio 的成本单位不同：像素、帧数、时长、编码与模型决定资源。把它们塞进通用 DocumentBatch 会失去调度信息。专用 Task 保留媒体对象、片段和派生关系；文本输出仍进入统一 Unit/Edge 契约。跨模态 Pipeline 在 Caption、Embedding 或相似度处 Join，需要明确宽依赖。

多模态容器的安全预算、临时磁盘和解码器版本与前一篇一致。执行框架不会替代恶意媒体隔离。

### 5.5 适合与不适合

适合：希望使用已有大模型数据整理 Stage、GPU/多模态资源管线、分布式分类/Embedding 和去重组件；需要把资源配置与数据处理统一。需要谨慎：版本快速演进、后端默认优化、第三方依赖与集群环境；团队必须锁版本、读物理计划并维护自身 Manifest/Policy 层。

若企业已有成熟 Spark 数据湖治理，可以让 Spark 负责大表 Join/统计，NeMo Curator 负责 GPU Stage，二者以 Released Manifest 交接。不要在共享活动目录中隐式交接。

## 6. Ray Data：流式 Block 与 Task/Actor 混合执行

### 6.1 Dataset 与 Block

Ray Data 的 Dataset 由多个 Block 组成。读取、Map、Filter、Map Batches、Shuffle 和写出形成逻辑计划，执行时优化为物理 Operator 流。Block 是调度、传递和内存管理的重要单位，不等于单条 Document。合适 Block 大小平衡并发、调度开销、内存与 GPU 批处理。

执行通常延迟到 Materialize、写出或迭代消费等 Action。仅构建 Dataset 变量不代表 Job 已运行。调试必须查看执行 Stats 和物理计划，而不是从代码行数猜 Stage。

## 写在最后

执行面选定后，数据的物理组织方式直接决定吞吐与恢复语义。下一篇：[训练数据格式、分片、索引、流式读取与缓存](/source/AI-Infra/5-数据工程与后训练/07-训练数据格式-分片-索引-流式读取与缓存)。