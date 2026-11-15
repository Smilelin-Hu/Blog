# ZeRO（零冗余优化器）原理与实战

### 1.1. 显存冗余的三个来源
在后文中我们学过，混合精度训练下，模型状态（参数、梯度、优化器状态）的显存占用可以用公式 **16Φ**（Φ为参数量）来估算——参数2Φ、梯度2Φ、优化器状态12Φ（Adam优化器需要维护FP32精度的动量m和方差v，共8Φ，再加上FP32的参数副本4Φ）。
在传统的数据并行（DDP）中，**每个GPU都完整存储了这三部分数据**。当模型规模增大时，显存需求线性增长。ZeRO的核心思想就是：**既然每个GPU都存了同样的东西，为什么不让它们各存一部分呢？**
ZeRO将优化分为三个阶段，**每个阶段逐步扩展分片范围**。
### 1.2. ZeRO-1：优化器状态分片
**分片对象**：仅对优化器状态进行分片（包括Adam的FP32权重、一阶动量m和二阶方差v），模型参数和梯度仍保持完整拷贝。
**工作流程**：
- **前向传播**：每个GPU独立计算本地参数的输出，无需通信
- **反向传播**：梯度计算完成后，通过AllReduce同步所有GPU的梯度（这一步与DDP相同）
- **参数更新**：每个GPU仅使用**本地分片的优化器状态**更新**对应的参数分片**，更新完成后合并所有分片得到完整模型
**显存优化效果**：
假设参数量为P，传统数据并行下单卡显存需求为：
- 参数：P
- 优化器状态：2P（Adam的动量和方差）
- 梯度：P
- **总计：4P**
ZeRO-1将优化器状态分片到N个GPU后：
- 参数：P（不变）
- 优化器状态：2P/N
- 梯度：P（不变）
- **总计：(2 + 2/N)P**
当N=8时，显存占用从4P降至2.25P，**减少约62.5%**。
**适用场景**：ZeRO-1适用于优化器状态占显存比例高的场景（如使用Adam优化器的大模型），以及硬件资源有限、需要支持更大批次训练的场景。
### 1.3. ZeRO-2：优化器状态 + 梯度分片
**分片对象**：在ZeRO-1的基础上，进一步对梯度进行分片。
**工作流程**：
- **前向传播**：与ZeRO-1相同，每个GPU独立计算
- **反向传播**：每个GPU仅计算本地参数对应的梯度分片，计算完成后通过AllReduce聚合所有分片，得到完整梯度
- **参数更新**：使用分片的优化器状态更新参数分片
**显存优化效果**：
ZeRO-2的单卡显存需求为：
- 参数：P（不变）
- 优化器状态：2P/N
- 梯度：P/N
- **总计：(1 + 3/N)P**
当N=8时，显存占用从4P降至1.375P，**减少约75%**，显著优于ZeRO-1。当N足够大时（如N=64），显存占用趋近于P，即仅需存储一份完整的参数副本。
**通信量**：ZeRO-2的通信量与数据并行一致，仍为2M（M为模型参数量）。
### 1.4. ZeRO-3：优化器状态 + 梯度 + 参数全分片
**分片对象**：在ZeRO-2的基础上，将16位模型参数也在各个进程间进行分片。
**工作流程**：
- 每个GPU仅存储**分片后的参数**（而非完整副本）
- 在前向和反向传播期间，ZeRO-3会**自动收集（AllGather）和重新分片（Partition）** 参数
- 计算完成后，参数被释放，仅保留分片
**显存优化效果**：
ZeRO-3的单卡显存需求为：
- 参数：P/N
- 优化器状态：2P/N
- 梯度：P/N
- **总计：4P/N**
当N=64时，显存占用仅为传统数据并行的**1/64**。这使得在有限显存的GPU上训练千亿甚至万亿参数模型成为可能。
**通信代价**：ZeRO-3以**更多通信换取更低显存**。由于参数需要在计算时动态收集，ZeRO-3的通信量高于ZeRO-2。这正是ZeRO-3的核心权衡——用通信换显存。
### 1.5. 三个阶段对比总结
> [内嵌电子表格，分享态无法直接读取内容]
**选型建议**：
- **ZeRO-1**：优化器状态是瓶颈时使用（如使用Adam的大模型）
- **ZeRO-2**：梯度和优化器状态共同构成瓶颈时使用（大多数中等规模场景的默认选择）
- **ZeRO-3**：模型参数本身无法放入单卡时使用（千亿以上参数模型）
## 2. ZeRO-3的参数分片与动态收集机制
ZeRO-3是整个ZeRO系列中最复杂也最精妙的部分。理解它的工作机制，是理解“如何用通信换显存”的关键。
### 2.1. 核心思想：从“常驻”到“按需”
在ZeRO-2及更早的方案中，模型参数是**常驻GPU**的——每张卡上都保存了一份完整的参数副本，无论是否正在计算该层。
ZeRO-3做了一个根本性的改变：**让参数从“常驻GPU”变成“按需聚合、用完即还”**。
具体来说：
- **平时**：参数以分片形式（1/N）存储在各自的GPU上，不占用完整显存
- **计算时**：在需要使用某一层参数进行前向或反向传播时，通过AllGather从所有GPU上收集该层的完整参数
- **计算后**：立即释放完整参数，回到分片状态
### 2.2. Hook机制：ZeRO-3的工程实现
ZeRO-3对PyTorch模型的改造本质上是一套 **Hook系统**：
- 在每个模块的**前向入口**插入参数AllGather逻辑
- 在每个模块的**前向出口**插入参数释放（Partition）逻辑
- 在每个模块的**反向入口**同样插入AllGather逻辑
- 在每个模块的**反向出口**同样插入释放逻辑
- 在每个参数的梯度累积完成后插入归约逻辑
这套Hook系统管理着两条生命周期：
1. **参数的生命周期**（模块级Hook）：进入模块时AllGather，退出时Partition
2. **梯度的生命周期**（参数级Hook）：梯度计算完成后归约到对应的分片
### 2.3. 前向传播的完整时序
以某个Transformer层（Layer N）的前向传播为例，ZeRO-3的执行时序如下：
**步骤1：Pre-Forward Hook触发**
- 检测到即将执行Layer N的前向计算
- 从参数队列中取出Layer N的参数信息
- 发起异步AllGather，从所有GPU上收集Layer N的完整参数
**步骤2：等待参数就绪**
- 计算流（Default Stream）等待AllGather完成
- 如果通信已完成 → 立即继续
- 如果通信未完成 → 产生等待（“气泡”）
**步骤3：执行前向计算**
- 参数已完整就绪，执行Layer N的前向计算
- 产生激活值（供反向传播使用）
**步骤4：Post-Forward Hook触发**
- 前向计算完成，立即执行Partition
- 释放Layer N的完整参数，回到分片状态
- **关键**：此时其他层的参数仍处于分片状态，不占用显存
**步骤5：预取（Prefetch）优化**
- 在计算Layer N的同时，**提前**发起Layer N+1的异步AllGather
- 这样当Layer N计算完成时，Layer N+1的参数可能已经就绪
- 实现通信与计算的重叠，**隐藏通信延迟**
### 2.4. 反向传播的对称性
ZeRO-3的反向传播对参数的管理方式与前向**完全对称**：
- **Pre-Backward Hook**：AllGather收集当前层的完整参数（用于计算梯度）
- **反向计算**：使用完整参数计算梯度
- **Post-Backward Hook**：Partition释放完整参数
- **梯度归约**：梯度计算完成后，通过AllReduce/ReduceScatter将梯度归约到对应的分片
这种对称性使得ZeRO-3的实现非常优雅——前向和反向走的是同一套流程。
### 2.5. 通信与计算的重叠
ZeRO-3通过**预取（Prefetch）** 机制实现通信与计算的重叠：
- ZeRO-3维护一个**预取缓冲区（Prefetch Buffer）**，大小可配置
- 在当前层计算的同时，提前发起**后续多层**参数的AllGather
- 通过将多个层的AllGather**融合（Fuse）** 成一次更大的AllGather，减少通信次数
这种设计与我们在后文学习的“通信与计算重叠”一脉相承——将通信开销隐藏在计算过程中。
### 2.6. ZeRO-3的进阶：ZeRO-Offload与ZeRO-Infinity
ZeRO-3还可以与**卸载（Offload）** 技术结合，进一步扩展可训练的模型规模：
**ZeRO-Offload**：将优化器状态和梯度卸载到CPU内存，GPU仅保留FP16参数用于计算。这使得在有限的GPU显存上可以训练**高达130亿参数**的模型。
**ZeRO-Infinity**：ZeRO-Offload的下一代。除了优化器状态和梯度，还能将**更多的模型权重**卸载到CPU甚至NVMe内存。具有更高效的带宽利用率和通信与计算的重叠能力。
## 3. 使用DeepSpeed配置ZeRO的实战演练
ZeRO最主流的实现是微软的**DeepSpeed**框架。DeepSpeed将ZeRO的配置简化为JSON配置文件中的几个参数，**无需修改训练代码**。
### 3.1. DeepSpeed环境准备
**安装DeepSpeed**：
```bash
pip install deepspeed
```
**检查CUDA兼容性**：
```text
ds_report
```
该命令会报告DeepSpeed检测到的CUDA版本、PyTorch版本以及NCCL等信息。
### 3.2. ZeRO-2配置实战
以下是一个完整的ZeRO-2配置文件（`ds_config_zero2.json`）：
```text
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
> [内嵌电子表格，分享态无法直接读取内容]
### 3.3. ZeRO-3配置实战
当模型大到连ZeRO-2也无法容纳时，需要升级到ZeRO-3：
```text
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
**ZeRO-3特有参数解读**：
> [内嵌电子表格，分享态无法直接读取内容]
### 3.4. 启动训练
**方式一：使用deepspeed命令**
```bash
deepspeed --num_gpus=8 train.py \
    --deepspeed ds_config_zero3.json \
    --model_name_or_path /path/to/model \
    --per_device_train_batch_size 4 \
    --max_steps 10000
```
**方式二：在训练脚本中集成**
```text
for batch in trainloader:
    loss = model_engine(batch)
    model_engine.backward(loss)
    model_engine.step()
```
### 3.5. ZeRO配置的进阶调优
**调优原则**：
1. **显存充足时优先选择较低Stage**：Stage越低，通信开销越小，训练速度越快
2. **显存不足时升级Stage**：从Stage 1 → 2 → 3，逐步增加分片范围
3. **启用卸载（Offload）作为最后手段**：CPU卸载会显著降低训练速度（因为CPU-GPU带宽远低于GPU显存带宽），仅在GPU显存实在不够时使用
**分桶大小（Bucket Size）调优**：
- 更大的桶 → 更少的通信次数 → 更低的延迟开销
- 更小的桶 → 更早触发通信 → 更好的通信与计算重叠
- 需要在两者之间找到平衡点，通常从5e8（500MB）开始调优
**ZeRO-3的预取调优**：
- `stage3_prefetch_bucket_size`控制预取缓冲区大小
- 更大的预取缓冲区 → 更多的参数被提前加载 → 更好的重叠效果
- 但过大的缓冲区会占用额外显存
### 3.6. 一个完整的实战示例
以下是一个使用DeepSpeed ZeRO-3训练7B模型的完整示例：
```text
    )

    # 4. 训练循环
    for epoch in range(10):
        for batch in trainloader:
            # 将数据移到GPU
            inputs = batch["input_ids"].to(model_engine.device)
            labels = batch["labels"].to(model_engine.device)

            # 前向传播
            outputs = model_engine(inputs)
            loss = nn.CrossEntropyLoss()(outputs, labels)

            # 反向传播 + 优化器更新（ZeRO的通信在这里自动完成）
            model_engine.backward(loss)
            model_engine.step()

            # 打印loss
            if model_engine.global_steps % 100 == 0:
                print(f"Step {model_engine.global_steps}: loss = {loss.item():.4f}")

if __name__ == "__main__":
    main()
```
启动命令：
```bash
deepspeed --num_gpus=8 train.py --deepspeed ds_config_zero3.json
```
整个过程中，**训练代码几乎不需要修改**——ZeRO的所有优化都通过DeepSpeed的配置文件完成。这正是DeepSpeed的设计哲学：**让大模型训练的门槛降到最低**。

## 写在最后

下一篇：[激活值重计算（Activation Recomputation）](/source/AI-Infra/1-大模型训练优化/13-激活值重计算.md)。
