# PyTorch训练基础与性能分析

### 1.1. 一个“能跑”的训练循环 vs. 一个“好用”的训练循环
很多初学者写的训练循环长这样：
```text
for epoch in range(num_epochs):
    for batch in dataloader:
        outputs = model(batch)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
```
这段代码确实“能跑”，但在工业级项目中远远不够。它缺少了太多关键要素：设备管理、梯度裁剪、学习率调度、验证评估、日志记录……更重要的是，它没有为后续的性能分析预留任何接口。
一个**工业级标准的训练循环**，应该像一架仪表的飞机——每一个关键指标都可观测、每一个环节都可控。
### 1.2. 标准训练循环的完整实现
下面是一个融合了工业界最佳实践的PyTorch训练循环模板：
```text

    for inputs, labels in dataloader:
        inputs = inputs.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        outputs = model(inputs)
        loss = criterion(outputs, labels)

        total_loss += loss.item()
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

    return total_loss / len(dataloader), correct / total

# ---------- 6. 主训练流程 ----------
for epoch in range(1, num_epochs + 1):
    train_loss = train_one_epoch(epoch, model, train_loader, optimizer, criterion, scaler, scheduler)
    val_loss, val_acc = evaluate(model, val_loader, criterion)

    logging.info(f"Epoch {epoch}: Train Loss={train_loss:.4f}, Val Loss={val_loss:.4f}, Val Acc={val_acc:.4f}")
```
### 1.3. 代码中的关键优化点解读
上面的模板中包含了几个容易被忽视但至关重要的细节：
`pin_memory=True`：将CPU端的数据存储在锁页内存（Page-Locked Memory）中，GPU可以直接从锁页内存中读取数据，**大幅加速CPU→GPU的数据传输**。如果不开启，数据传输速度可能降低30-50%。
`non_blocking=True`：在`to(device)`时使用非阻塞传输，允许CPU在数据传输的同时继续执行后续指令，实现**数据传输与计算的重叠**。
`set_to_none=True`：在`optimizer.zero_grad()`中使用`set_to_none`而不是默认的`zero_grad`。前者直接将梯度张量置为None，后者需要将梯度张量中的所有元素清零——前者更高效，且能释放显存。
**混合精度训练（**`autocast`** + **`GradScaler`**）**：使用FP16/BF16进行前向和反向传播，用FP32进行梯度累加和参数更新。这能将**显存占用降低约40%，计算速度提升1.5-3倍**。
**梯度裁剪（**`clip_grad_norm_`**）**：防止梯度爆炸导致训练不稳定，是大模型训练的标配。
## 2. 使用`torch.profiler`进行单卡性能分析
有了规范的训练循环之后，下一步就是**测量它跑得怎么样**。`torch.profiler`是PyTorch官方提供的性能分析工具，可以记录CPU/GPU的操作耗时、内存使用、CUDA内核执行等详细信息。
### 2.1. profiler的基本用法
最简单的用法是用`with`语句包裹想要分析的代码段：
```text
# 创建profiler实例
with profile(
    activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],  # 同时分析CPU和GPU
    record_shapes=True,   # 记录张量形状
    profile_memory=True,  # 记录内存使用
) as prof:
    # 执行一个训练步骤
    inputs = inputs.to(device)
    labels = labels.to(device)

    with record_function("forward"):
        outputs = model(inputs)
        loss = criterion(outputs, labels)

    with record_function("backward"):
        scaler.scale(loss).backward()

    with record_function("optimizer"):
        scaler.step(optimizer)
        scaler.update()

# 打印分析结果
print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=15))
```
**关键参数说明**：
- `activities`：指定要分析的硬件平台。**在GPU上运行时，一定要同时包含**`CPU`**和**`CUDA`，否则只能看到CPU端的kernel启动开销，看不到GPU上的实际执行时间。
- `record_shapes`：记录每个操作输入张量的形状，便于分析不同尺寸下的性能差异。
- `profile_memory`：记录显存使用情况，对于大模型训练至关重要。
- `record_function`：自定义标记，让分析结果中能清晰区分前向、反向、优化器等不同阶段。
### 2.2. 进阶用法：Schedule采样
对于长时间的训练任务，不需要对每一步都做profiling——那样会产生海量数据，且影响训练速度。使用`schedule`参数可以**按需采样**：
```text
from torch.profiler import profile, schedule

# 配置采样策略：跳过前10步，预热2步，实际记录3步，重复5次
my_schedule = schedule(
    skip_first=10,  # 跳过前10步（训练初期不稳定）
    wait=1,         # 等待1步（不记录）
    warmup=2,       # 预热2步（让GPU达到稳定状态，不记录）
    active=3,       # 实际记录3步
    repeat=5        # 重复上述周期5次
)

with profile(
    activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
    schedule=my_schedule,
    on_trace_ready=torch.profiler.tensorboard_trace_handler("./profiler_logs/"),
) as prof:
    for step in range(num_steps):
        # 训练代码...
        prof.step()  # 必须调用，通知profiler进入下一步
```
这个配置会：跳过前10步 → 等待1步 → 预热2步 → 记录3步 → 重复5次。`on_trace_ready` 参数指定了分析完成后自动将结果导出到TensorBoard。
### 2.3. 导出与可视化
`profiler`支持两种主要的可视化方式：
**方式一：Chrome Tracing（JSON格式）**
```text
prof.export_chrome_trace("trace.json")
```
生成的文件可以在Chrome浏览器中打开`chrome://tracing`并加载，看到**每个操作的时间线视图**，非常直观地展示CPU和GPU的活动重叠情况。
**方式二：TensorBoard**
```text
# 在profile初始化时指定
on_trace_ready=torch.profiler.tensorboard_trace_handler("./profiler_logs/")
```
然后在终端运行`tensorboard --logdir ./profiler_logs/`，可以在TensorBoard的**Performance Profile**面板中查看详细的算子统计和内存分析。
## 3. 识别训练瓶颈：计算密集 vs. 访存密集
拿到了profiler的输出之后，最关键的能力是**读懂它**——判断当前训练任务的瓶颈到底在哪里。这是选择优化方向的前提。
### 3.1. 两种基本瓶颈类型
在深度学习训练中，性能瓶颈主要分为两大类：
**计算密集（Compute-Bound）**：
- **特征**：GPU的计算单元（CUDA Core/Tensor Core）满负荷运转，但显存带宽利用率不高
- **典型场景**：大矩阵乘法（如Transformer的FFN层）、大卷积核
- **表现为**：GPU利用率（`nvidia-smi`中的GPU-Util）接近100%，且持续稳定
- **优化方向**：使用更高效的算子（如FlashAttention）、混合精度训练、Tensor Core优化
**访存密集（Memory-Bound）**：
- **特征**：GPU的计算单元经常“饿死”——等待数据从显存中搬运过来
- **典型场景**：小算子（如LayerNorm、Softmax、Dropout）、频繁的逐元素操作
- **表现为**：GPU利用率不高或波动大，但显存带宽利用率接近上限
- **优化方向**：算子融合（将多个小算子合并成一个）、减少中间结果的显存读写
### 3.2. 如何从profiler输出中判断
**方法一：观察**`key_averages()`**的输出**
```text
print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=15))
```
输出会列出每个操作的总耗时。重点关注：
- **如果排名前列的都是矩阵乘法（如**`aten::mm`**、**`aten::bmm`**）** → 很可能是计算密集
- **如果排名前列的都是逐元素操作（如**`aten::add`**、**`aten::mul`**）或归一化（**`aten::layer_norm`**）** → 很可能是访存密集
- **如果**`cuda_time_total`**和**`cpu_time_total`**差距很大** → 说明GPU在等待CPU下发任务，可能是CPU端瓶颈
**方法二：观察GPU利用率曲线**
在TensorBoard的Profiler面板中，可以看到GPU利用率的时序图：
> [内嵌电子表格，分享态无法直接读取内容]
**方法三：使用Nsight Systems进行系统级分析**
当`torch.profiler`提供的信息不够深入时，可以使用NVIDIA的**Nsight Systems**进行系统级性能分析。它能提供：
- CPU各个核心的负载分布
- CUDA kernel的启动和执行时间线
- 内存传输（CPU↔GPU）的带宽利用情况
- 系统调用的耗时
### 3.3. 一个实战判断流程
当拿到一个训练任务时，可以按以下流程快速判断瓶颈类型：
```text
第2步：运行 profiler，查看 top 操作的类型
├── 主要是 mm/bmm/conv → 确认是计算密集 → 优化方向：混合精度、Tensor Core、FlashAttention
└── 主要是 element-wise 操作 → 访存密集 → 优化方向：算子融合

第3步：检查 DataLoader 配置
├── num_workers 是否合理？pin_memory 是否开启？
├── 如果数据加载是瓶颈 → 增加 num_workers、开启 pin_memory、使用更快的存储
└── 如果数据加载正常 → 检查是否有频繁的 CPU↔GPU 拷贝或日志打印
```
### 3.4. 一个典型误区
很多初学者看到GPU利用率不高，第一反应是“GPU不够强”——这是错误的。**GPU利用率不高，99%的情况下是软件层面的问题**，而不是硬件的问题。
常见的真正原因包括：
- 数据加载太慢，GPU在空等（增加`num_workers`，开启`pin_memory`）
- 小算子太多，kernel启动开销占比过高（使用算子融合）
- 频繁的CPU↔GPU同步（减少`.item()`调用，使用异步传输）
- 日志打印或指标计算过于频繁（减少每步的日志输出）

## 写在最后

下一篇：[数据并行（Data Parallelism）](/source/AI-Infra/1-大模型训练优化/04-数据并行.md)。
