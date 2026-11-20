# ZeRO（零冗余优化器）原理与实战

## 1. ZeRO 的三个阶段：ZeRO-1/2/3 的设计思想

### 1.1 显存冗余的三个来源

混合精度训练下，模型状态（参数、梯度、优化器状态）的显存占用可以用 **$16\Phi$**（$\Phi$ 为参数量）来估算：FP16 参数 $2\Phi$、FP16 梯度 $2\Phi$、FP32 主权重副本 $4\Phi$、Adam 的一阶动量与二阶方差共 $8\Phi$。

在传统的数据并行（DDP）中，**每个 GPU 都完整存储了这三部分数据**。当模型规模增大时，显存需求线性增长。ZeRO 的核心思想就是：**既然每个 GPU 都存了同样的东西，为什么不让它们各存一部分？**

ZeRO 将优化分为三个阶段，**每个阶段逐步扩展分片范围**。

### 1.2 ZeRO-1：优化器状态分片

**分片对象**：仅对优化器状态进行分片（包括 Adam 的 FP32 主权重、一阶动量 $m$ 和二阶方差 $v$），模型参数和梯度仍保持完整拷贝。

**工作流程**：

- **前向传播**：每个 GPU 独立计算本地参数的输出，无需通信。
- **反向传播**：梯度计算完成后，通过 AllReduce 同步所有 GPU 的梯度（这一步与 DDP 相同）。
- **参数更新**：每个 GPU 仅使用**本地分片的优化器状态**更新**对应的参数分片**，更新完成后合并所有分片得到完整模型。

**显存优化效果**：以 $N$ 路分片、基准 $16\Phi$ 计，

- 参数：$2\Phi$（不变）
- 梯度：$2\Phi$（不变）
- 优化器状态（含 FP32 主参与 m/v）：$12\Phi / N$
- **总计：$4\Phi + 12\Phi/N$**

当 $N=8$ 时为 $5.5\Phi$，相对 DDP 的 $16\Phi$ 降幅约 **65.6%**。

一个常见的口径差异：若把「4P」按「参数 1P + 梯度 1P + 动量方差 2P」计、且不再单列 FP32 主参，则有 $4P \rightarrow 2.25P$ 的写法。两种写法描述的降幅不同（62.5% vs 65.6%），做容量规划时先声明口径。

**适用场景**：优化器状态占显存比例高的场景（如使用 Adam 的大模型），以及硬件资源有限、需要支持更大批次训练的场景。

### 1.3 ZeRO-2：优化器状态 + 梯度分片

**分片对象**：在 ZeRO-1 的基础上，进一步对梯度进行分片。

**工作流程**：

- **前向传播**：与 ZeRO-1 相同，每个 GPU 独立计算。
- **反向传播**：每个 GPU 只保留本地参数对应的梯度分片，通过 ReduceScatter 聚合（而非完整 AllReduce），得到分片梯度。
- **参数更新**：使用分片的优化器状态更新参数分片。

**显存优化效果**：

- 参数：$2\Phi$（不变）
- 梯度：$2\Phi / N$
- 优化器状态：$12\Phi / N$
- **总计：$2\Phi + 14\Phi/N$**

当 $N=8$ 时为 $3.75\Phi$。当 $N$ 足够大时，显存占用趋近于 $2\Phi$，即仅需存储一份完整的 FP16 参数副本。

**通信量**：ZeRO-2 的通信量与数据并行一致，仍为约 $2M$（$M$ 为模型参数量）。

### 1.4 ZeRO-3：优化器状态 + 梯度 + 参数全分片

**分片对象**：在 ZeRO-2 的基础上，将 16 位模型参数也在各个进程间进行分片。

**工作流程**：

- 每个 GPU 仅存储**分片后的参数**（而非完整副本）。
- 在前向和反向传播期间，ZeRO-3 会**自动收集（AllGather）和重新分片（Partition）** 参数。
- 计算完成后，参数被释放，仅保留分片。

**显存优化效果**：

- 参数：$2\Phi / N$
- 梯度：$2\Phi / N$
- 优化器状态：$12\Phi / N$
- **总计：$16\Phi / N$**

当 $N=64$ 时，显存占用仅为传统数据并行的 **1/64**；$N=8$ 时为 $2\Phi$。这使得在有限显存的 GPU 上训练千亿甚至万亿参数模型成为可能。

**通信代价**：ZeRO-3 以**更多通信换取更低显存**。由于参数需要在计算时动态收集，ZeRO-3 的通信量高于 ZeRO-2——这正是 ZeRO-3 的核心权衡。

### 1.5 三个阶段对比总结

| 阶段 | 参数 | 梯度 | 优化器状态 | 单卡合计 | 通信量 |
|---|---|---|---|---|---|
| DDP | $2\Phi$ | $2\Phi$ | $12\Phi$ | $16\Phi$ | $2M$ |
| ZeRO-1 | $2\Phi$ | $2\Phi$ | $12\Phi/N$ | $4\Phi + 12\Phi/N$ | 约 $2M$ |
| ZeRO-2 | $2\Phi$ | $2\Phi/N$ | $12\Phi/N$ | $2\Phi + 14\Phi/N$ | 约 $2M$ |
| ZeRO-3 | $2\Phi/N$ | $2\Phi/N$ | $12\Phi/N$ | $16\Phi/N$ | 约 $3M$ |

**选型建议**：

- **ZeRO-1**：优化器状态是瓶颈时使用（如使用 Adam 的大模型）。
- **ZeRO-2**：梯度和优化器状态共同构成瓶颈时使用（大多数中等规模场景的默认选择）。
- **ZeRO-3**：模型参数本身无法放入单卡时使用（千亿以上参数模型）。

![ZeRO 三阶段分片对比：优化器状态→梯度→参数](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y1_l12_01.png)

## 2. ZeRO-3 的参数分片与动态收集机制

ZeRO-3 是整个 ZeRO 系列中最复杂也最精妙的部分。理解它的工作机制，是理解「如何用通信换显存」的关键。

### 2.1 核心思想：从「常驻」到「按需」

在 ZeRO-2 及更早的方案中，模型参数是**常驻 GPU** 的——每张卡上都保存了一份完整的参数副本，无论是否正在计算该层。

ZeRO-3 做了一个根本性的改变：**让参数从「常驻 GPU」变成「按需聚合、用完即还」**。

- **平时**：参数以分片形式（$1/N$）存储在各自的 GPU 上，不占用完整显存。
- **计算时**：在需要使用某一层参数进行前向或反向传播时，通过 AllGather 从所有 GPU 上收集该层的完整参数。
- **计算后**：立即释放完整参数，回到分片状态。

### 2.2 Hook 机制：ZeRO-3 的工程实现

ZeRO-3 对 PyTorch 模型的改造本质上是一套 **Hook 系统**：

- 在每个模块的**前向入口**插入参数 AllGather 逻辑。
- 在每个模块的**前向出口**插入参数释放（Partition）逻辑。
- 在每个模块的**反向入口**同样插入 AllGather 逻辑。
- 在每个模块的**反向出口**同样插入释放逻辑。
- 在每个参数的梯度累积完成后插入归约逻辑。

这套 Hook 系统管理着两条生命周期：

1. **参数的生命周期**（模块级 Hook）：进入模块时 AllGather，退出时 Partition。
2. **梯度的生命周期**（参数级 Hook）：梯度计算完成后归约到对应的分片。

### 2.3 前向传播的完整时序

以某个 Transformer 层（Layer N）的前向传播为例，ZeRO-3 的执行时序如下。

**步骤 1：Pre-Forward Hook 触发**

- 检测到即将执行 Layer N 的前向计算。
- 从参数队列中取出 Layer N 的参数信息。
- 发起异步 AllGather，从所有 GPU 上收集 Layer N 的完整参数。

**步骤 2：等待参数就绪**

- 计算流（Default Stream）等待 AllGather 完成。
- 如果通信已完成 → 立即继续；如果通信未完成 → 产生等待（「气泡」）。

**步骤 3：执行前向计算**

- 参数已完整就绪，执行 Layer N 的前向计算。
- 产生激活值（供反向传播使用）。

**步骤 4：Post-Forward Hook 触发**

- 前向计算完成，立即执行 Partition。
- 释放 Layer N 的完整参数，回到分片状态。
- 此时其他层的参数仍处于分片状态，不占用显存。

**步骤 5：预取（Prefetch）优化**

- 在计算 Layer N 的同时，**提前**发起 Layer N+1 的异步 AllGather。
- 这样当 Layer N 计算完成时，Layer N+1 的参数可能已经就绪。
- 实现通信与计算的重叠，**隐藏通信延迟**。

### 2.4 反向传播的对称性

ZeRO-3 的反向传播对参数的管理方式与前向**完全对称**：

- **Pre-Backward Hook**：AllGather 收集当前层的完整参数（用于计算梯度）。
- **反向计算**：使用完整参数计算梯度。
- **Post-Backward Hook**：Partition 释放完整参数。
- **梯度归约**：梯度计算完成后，通过 AllReduce/ReduceScatter 将梯度归约到对应的分片。

这种对称性使得 ZeRO-3 的实现非常优雅——前向和反向走的是同一套流程。

### 2.5 通信与计算的重叠

ZeRO-3 通过**预取（Prefetch）** 机制实现通信与计算的重叠：

- ZeRO-3 维护一个**预取缓冲区（Prefetch Buffer）**，大小可配置。
- 在当前层计算的同时，提前发起**后续多层**参数的 AllGather。
- 通过将多个层的 AllGather **融合（Fuse）** 成一次更大的 AllGather，减少通信次数。

这与集合通信一篇中的「通信与计算重叠」一脉相承——把通信开销隐藏在计算过程中。

### 2.6 进阶：ZeRO-Offload 与 ZeRO-Infinity

ZeRO-3 还可以与**卸载（Offload）** 技术结合，进一步扩展可训练的模型规模。

**ZeRO-Offload**：将优化器状态和梯度卸载到 CPU 内存，GPU 仅保留 FP16 参数用于计算。这使得在有限的 GPU 显存上可以训练**高达 130 亿参数**的模型。

**ZeRO-Infinity**：ZeRO-Offload 的下一代。除了优化器状态和梯度，还能将**更多的模型权重**卸载到 CPU 甚至 NVMe 内存，具有更高效的带宽利用率和通信与计算重叠能力。

## 3. 使用 DeepSpeed 配置 ZeRO 的实战演练

ZeRO 最主流的实现是微软的 **DeepSpeed** 框架。DeepSpeed 将 ZeRO 的配置简化为 JSON 配置文件中的几个参数，**无需修改训练代码**。

### 3.1 环境准备

```bash
pip install deepspeed
ds_report
```

`ds_report` 会报告 DeepSpeed 检测到的 CUDA 版本、PyTorch 版本以及 NCCL 等信息。

### 3.2 ZeRO-2 配置实战

以下是一个可用的 ZeRO-2 配置文件（`ds_config_zero2.json`）：

```json
{
  "train_batch_size": 32,
  "gradient_accumulation_steps": 1,
  "fp16": {
    "enabled": true,
    "loss_scale": 0,
    "initial_scale_power": 16
  },
  "zero_optimization": {
    "stage": 2,
    "allgather_partitions": true,
    "reduce_scatter": true,
    "overlap_comm": true,
    "contiguous_gradients": true,
    "reduce_bucket_size": 5e8,
    "allgather_bucket_size": 5e8
  },
  "optimizer": {
    "type": "AdamW",
    "params": {
      "lr": 0.001,
      "betas": [0.9, 0.999],
      "eps": 1e-8,
      "weight_decay": 0.01
    }
  },
  "scheduler": {
    "type": "WarmupLR",
    "params": {
      "warmup_min_lr": 0,
      "warmup_max_lr": 0.001,
      "warmup_num_steps": 1000
    }
  }
}
```

**关键参数解读**：

- `stage`：ZeRO 阶段，取 1/2/3。
- `overlap_comm`：把通信与反向计算重叠起来，通常保持开启。
- `contiguous_gradients`：把梯度放在连续的缓冲区里，减少显存碎片。
- `reduce_bucket_size` / `allgather_bucket_size`：归约与聚合的桶大小，直接影响通信次数与重叠效果。

### 3.3 ZeRO-3 配置实战

当模型大到连 ZeRO-2 也无法容纳时，需要升级到 ZeRO-3：

```json
{
  "train_batch_size": 32,
  "zero_optimization": {
    "stage": 3,
    "offload_optimizer": {
      "device": "cpu",
      "pin_memory": true
    },
    "overlap_comm": true,
    "contiguous_gradients": true,
    "sub_group_size": 1e9,
    "reduce_bucket_size": 5e8,
    "stage3_prefetch_bucket_size": 5e8,
    "stage3_param_persistence_threshold": 1e6,
    "stage3_max_live_parameters": 1e9,
    "stage3_max_reuse_distance": 1e9,
    "stage3_gather_16bit_weights_on_model_save": true
  }
}
```

**ZeRO-3 特有参数解读**：

- `stage3_prefetch_bucket_size`：预取缓冲区大小，决定提前拉取多少参数。
- `stage3_param_persistence_threshold`：小于该参数量的层不参与分片，留在显存常驻，避免频繁 AllGather。
- `stage3_max_live_parameters` / `stage3_max_reuse_distance`：控制同时在显存里的完整参数上限，以及多远之后的层才会复用它。
- `stage3_gather_16bit_weights_on_model_save`：保存检查点时把分片聚合成完整权重。

### 3.4 启动训练

**方式一：使用 deepspeed 命令**

```bash
deepspeed --num_gpus=8 train.py \
    --deepspeed ds_config_zero3.json \
    --model_name_or_path /path/to/model \
    --per_device_train_batch_size 4 \
    --max_steps 10000
```

**方式二：在训练脚本中集成**，训练循环用一个包装后的 engine：

```python
model_engine, optimizer, _, _ = deepspeed.initialize(
    model=model,
    model_parameters=model.parameters(),
    config=ds_config,
)

for batch in trainloader:
    inputs = batch["input_ids"].to(model_engine.device)
    labels = batch["labels"].to(model_engine.device)

    outputs = model_engine(inputs)
    loss = nn.CrossEntropyLoss()(outputs, labels)

    model_engine.backward(loss)   # ZeRO 的通信在这一步内部完成
    model_engine.step()
```

启动命令：

```bash
deepspeed --num_gpus=8 train.py --deepspeed ds_config_zero3.json
```

整个过程中，**训练代码几乎不需要修改**——ZeRO 的所有优化都通过 DeepSpeed 的配置文件完成。这正是 DeepSpeed 的设计哲学：**让大模型训练的门槛降到最低**。

### 3.5 ZeRO 配置的进阶调优

**调优原则**：

1. **显存充足时优先选择较低 Stage**：Stage 越低，通信开销越小，训练速度越快。
2. **显存不足时升级 Stage**：从 Stage 1 → 2 → 3，逐步增加分片范围。
3. **启用卸载（Offload）作为最后手段**：CPU 卸载会显著降低训练速度（因为 CPU-GPU 带宽远低于 GPU 显存带宽），仅在 GPU 显存实在不够时使用。

**分桶大小（Bucket Size）调优**：

- 更大的桶 → 更少的通信次数 → 更低的延迟开销。
- 更小的桶 → 更早触发通信 → 更好的通信与计算重叠。
- 需要在两者之间找到平衡点，通常从 `5e8`（500 MB）开始调优。

**ZeRO-3 的预取调优**：

- `stage3_prefetch_bucket_size` 控制预取缓冲区大小。
- 更大的预取缓冲区 → 更多的参数被提前加载 → 更好的重叠效果。
- 但过大的缓冲区会占用额外显存。

## 写在最后

下一篇：[激活值重计算（Activation Recomputation）](/source/AI-Infra/1-大模型训练优化/13-激活值重计算)。
