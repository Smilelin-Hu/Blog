# 附录 1：基于 DeepSpeed/Megatron 完成 7B 模型的分布式训练

本附录给出项目一的完整实施方案：从零完成一个 7B 大模型的分布式训练全流程。方案以 **DeepSpeed** 为主线、**Llama-2-7B** 为目标模型、**单机多卡**为部署场景，同时给出 Megatron-LM 的补充方案供进阶参考。

**项目目标**：

- 在 2–8 张 GPU 上完成 7B 模型的分布式训练（微调）。
- 使用 DeepSpeed ZeRO-3 作为显存优化策略。
- 训练稳定运行至少 1000 步，无 OOM、无 Loss Spike。
- MFU（模型算力利用率）达到 35% 以上。

**硬件要求**：

- 最低配置：2 张 A100 80GB。
- 推荐配置：4–8 张 A100/H100 + NVLink 互联。
- 替代方案：2 张以上 RTX 3090/4090（24GB）配合 ZeRO-3 + CPU Offload。

## 1. 环境准备

### 1.1 创建 Conda 环境

```bash
# 创建Python 3.10环境
conda create -n llm_train python=3.10 -y
conda activate llm_train
```

### 1.2 安装 PyTorch

根据 GPU 的 CUDA 版本选择 PyTorch。以 CUDA 11.8 为例：

```bash
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu118
```

**兼容性提示**：如需使用 FlashAttention 等高级特性，建议 PyTorch ≥ 2.0；不同硬件平台（如昇腾 NPU）需安装对应的 `torch_npu` 插件。

### 1.3 安装核心库

```bash
pip install transformers==4.36.0 \
    datasets==2.14.0 \
    accelerate==0.24.0 \
    deepspeed==0.12.4 \
    sentencepiece==0.1.99 \
    protobuf==3.20.3 \
    tensorboard==2.14.0 \
    trl==0.7.1 \
    peft==0.7.0
```

**版本说明**：以上组合经过验证；若使用更新版本需注意兼容性，DeepSpeed 0.12.4 是较稳定的选择。

### 1.4 验证安装

```bash
# 验证PyTorch和CUDA
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"

# 验证DeepSpeed
ds_report
```

`ds_report` 会输出 DeepSpeed 检测到的 CUDA、PyTorch、NCCL 版本及可用优化算子（如 FusedAdam、FusedLamb）。

### 1.5 （可选）安装 FlashAttention

```bash
pip install flash-attn --no-build-isolation
```

若安装失败（常见于旧版 CUDA 或 GCC），可尝试预编译 wheel，或用 `xformers` 替代：

```bash
pip install xformers
```

## 2. 模型获取

### 2.1 获取 Llama-2-7B 权重

**方式一：通过 Hugging Face 下载**。Llama-2 需要 Meta 授权，需先在 Hugging Face 的 `meta-llama/Llama-2-7b-hf` 页面申请访问权限。

```bash
# 输入Access Token后下载
huggingface-cli download meta-llama/Llama-2-7b-hf --local-dir ./models/llama-2-7b
```

**方式二：使用国内镜像**（如遇网络问题）。

```bash
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download meta-llama/Llama-2-7b-hf --local-dir ./models/llama-2-7b
```

**方式三：使用其他开源模型**。无法获取 Llama-2 授权时可选：

- **Qwen-7B**：`Qwen/Qwen-7B`（需申请）。
- **Baichuan2-7B**：`baichuan-inc/Baichuan2-7B-Base`。
- **DeepSeek-V2-Lite**：`deepseek-ai/DeepSeek-V2-Lite`。
- **Mistral-7B**：`mistralai/Mistral-7B-v0.1`（Apache 2.0，无需申请）。

### 2.2 验证模型文件

下载完成后目录应包含：

```text
./models/llama-2-7b/
├── config.json
├── generation_config.json
├── model-00001-of-00002.safetensors
├── model-00002-of-00002.safetensors
├── model.safetensors.index.json
├── special_tokens_map.json
├── tokenizer.json
├── tokenizer.model
└── tokenizer_config.json
```

## 3. 数据准备

### 3.1 数据格式

准备 JSON Lines 格式的训练数据，每行一个 JSON 对象：

```json
{"instruction": "解释什么是机器学习", "output": "机器学习是人工智能的一个分支，它使计算机能够从数据中学习并改进..."}
{"instruction": "写一首关于秋天的诗", "output": "秋风萧瑟天气凉，草木摇落露为霜..."}
{"instruction": "如何提高学习效率", "output": "提高学习效率可以从以下几个方面入手：1. 制定明确的学习计划..."}
```

文件结构：

```text
./data/
├── train.jsonl    # 训练集
└── eval.jsonl     # 验证集（可选）
```

建议训练集至少 **1000–5000 条**高质量样本，验证集约 **100–200 条**。

### 3.2 数据加载

```python
# data_utils.py
from datasets import load_dataset

def load_training_data(train_path: str, eval_path: str | None = None):
    data_files = {"train": train_path}
    if eval_path:
        data_files["eval"] = eval_path
    return load_dataset("json", data_files=data_files)

# 使用示例
if __name__ == "__main__":
    dataset = load_training_data("data/train.jsonl", "data/eval.jsonl")
    print(f"训练集大小: {len(dataset['train'])}")
    if "eval" in dataset:
        print(f"验证集大小: {len(dataset['eval'])}")
    print(f"样本示例: {dataset['train'][0]}")
```

### 3.3 数据格式化

指令微调（SFT）需要把数据格式化为模型可接受的对话格式：

```python
# format_utils.py
def format_instruction(example):
    """将instruction-output格式转换为模型输入格式"""
    return {
        "text": f"<s>[INST] {example['instruction']} [/INST] {example['output']} </s>"
    }

def preprocess_dataset(dataset):
    """对整个数据集应用格式化"""
    return dataset.map(format_instruction)
```

## 4. DeepSpeed 配置

### 4.1 创建 `ds_config.json`

```json
{
  "train_batch_size": 32,
  "micro_batch_size_per_gpu": 4,
  "gradient_accumulation_steps": 1,
  "bf16": { "enabled": true },
  "zero_optimization": {
    "stage": 3,
    "offload_optimizer": {
      "device": "cpu",
      "pin_memory": true
    },
    "offload_param": {
      "device": "cpu",
      "pin_memory": true
    },
    "allgather_partitions": true,
    "allgather_bucket_size": 5e8,
    "reduce_scatter": true,
    "reduce_bucket_size": 5e8,
    "overlap_comm": true,
    "contiguous_gradients": true,
    "sub_group_size": 1e9,
    "stage3_prefetch_bucket_size": 5e8,
    "stage3_param_persistence_threshold": 1e6,
    "stage3_max_live_parameters": 1e9,
    "stage3_max_reuse_distance": 1e9,
    "stage3_gather_16bit_weights_on_model_save": true
  },
  "activation_checkpointing": {
    "partition_activations": true,
    "cpu_checkpointing": false,
    "contiguous_memory_optimization": true,
    "number_checkpoints": 4,
    "synchronize_checkpoint_boundary": false,
    "profile": false
  },
  "steps_per_print": 50,
  "wall_clock_breakdown": false
}
```

### 4.2 关键参数解读

| 参数 | 作用 | 调优提示 |
|---|---|---|
| `stage` | ZeRO 阶段 | 3 = 参数/梯度/优化器全分片 |
| `offload_optimizer.device` | 优化器状态卸载目标 | `cpu` 省显存但变慢 |
| `offload_param.device` | 参数卸载目标 | 仅 ZeRO-3 有效，最吃 PCIe |
| `overlap_comm` | 通信与计算重叠 | 通常保持 `true` |
| `contiguous_gradients` | 梯度放在连续缓冲 | 减少显存碎片 |
| `stage3_prefetch_bucket_size` | 预取桶大小 | 越大重叠越好，但占显存 |
| `stage3_param_persistence_threshold` | 小层不参与分片的阈值 | 避免小层频繁 AllGather |
| `activation_checkpointing.number_checkpoints` | 重计算切分数 | 4 是常用起点 |

### 4.3 ZeRO 阶段选择指南

| 显存缺口 | 建议阶段 | 代价 |
|---|---|---|
| 参数 + 梯度 + 优化器状态都放得下 | ZeRO-0（纯 DDP） | 无 |
| 只差优化器状态那份显存 | ZeRO-1 | 通信量不变，通信次数略增 |
| 梯度也放不下 | ZeRO-2 | 通信量≈2M，需 ReduceScatter |
| 参数本身放不下 | ZeRO-3 | 通信量≈3M，需要预取 |
| 连 CPU 内存也紧张 | ZeRO-3 + NVMe Offload | I/O 成为主要瓶颈 |

## 5. 训练脚本

### 5.1 完整 `train.py`

```python
import argparse
import os
from dataclasses import dataclass, field

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


@dataclass
class ScriptArgs:
    model_name_or_path: str = "./models/llama-2-7b"
    train_file: str = "data/train.jsonl"
    eval_file: str | None = "data/eval.jsonl"
    output_dir: str = "./output"
    max_seq_length: int = 2048
    use_lora: bool = False
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    deepspeed: str = "ds_config.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model_name_or_path", default=ScriptArgs.model_name_or_path)
    p.add_argument("--train_file", default=ScriptArgs.train_file)
    p.add_argument("--eval_file", default=ScriptArgs.eval_file)
    p.add_argument("--output_dir", default=ScriptArgs.output_dir)
    p.add_argument("--per_device_train_batch_size", type=int, default=4)
    p.add_argument("--gradient_accumulation_steps", type=int, default=8)
    p.add_argument("--num_train_epochs", type=float, default=3)
    p.add_argument("--learning_rate", type=float, default=2e-5)
    p.add_argument("--max_seq_length", type=int, default=2048)
    p.add_argument("--logging_steps", type=int, default=10)
    p.add_argument("--save_steps", type=int, default=500)
    p.add_argument("--deepspeed", default="ds_config.json")
    p.add_argument("--use_lora", action="store_true")
    p.add_argument("--lora_r", type=int, default=8)
    p.add_argument("--lora_alpha", type=int, default=16)
    p.add_argument("--lora_dropout", type=float, default=0.05)
    return p.parse_args()


def main():
    args = parse_args()

    # 1. 加载模型
    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        torch_dtype=torch.bfloat16,
        use_cache=False,          # 训练时禁用KV cache
        trust_remote_code=True,
    )

    # 1b. 可选：使用LoRA
    if args.use_lora:
        print("Applying LoRA...")
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

    # 2. 加载分词器
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name_or_path,
        trust_remote_code=True,
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 3. 加载数据集
    print(f"Loading dataset from {args.train_file}...")
    data_files = {"train": args.train_file}
    if args.eval_file:
        data_files["eval"] = args.eval_file
    dataset = load_dataset("json", data_files=data_files)

    # 4. 数据预处理
    def format_instruction(example):
        text = f"<s>[INST] {example['instruction']} [/INST] {example['output']} </s>"
        return {"text": text}

    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=args.max_seq_length,
            padding=False,
        )

    for split in list(dataset.keys()):
        dataset[split] = dataset[split].map(format_instruction)
        dataset[split] = dataset[split].map(
            tokenize_function,
            batched=True,
            remove_columns=dataset[split].column_names,
        )

    # 5. 数据整理器
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,  # 因果语言模型不使用MLM
    )

    # 6. 训练参数
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.num_train_epochs,
        learning_rate=args.learning_rate,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=3,
        bf16=True,
        gradient_checkpointing=True,
        deepspeed=args.deepspeed,
        report_to="tensorboard",
        ddp_find_unused_parameters=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("eval"),
        data_collator=data_collator,
        tokenizer=tokenizer,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
```

### 5.2 脚本关键设计说明

**BF16 vs FP16**：脚本使用 `bf16=True` 而非 `fp16=True`。BF16 的动态范围与 FP32 相同，不易产生梯度下溢，是大模型训练的更优选择；若硬件不支持 BF16（如 V100），改为 `fp16=True`。

**Gradient Checkpointing**：通过 `gradient_checkpointing=True` 启用激活值重计算，以少量计算时间换取大量显存。

**LoRA 支持**：通过 `--use_lora` 启用参数高效微调，大幅降低显存需求。

## 6. 启动训练

### 6.1 单机多卡（推荐）

```bash
# 单机8卡
deepspeed --num_gpus=8 train.py \
    --model_name_or_path ./models/llama-2-7b \
    --train_file data/train.jsonl \
    --eval_file data/eval.jsonl \
    --output_dir ./output \
    --per_device_train_batch_size 4 \
    --gradient_accumulation_steps 8 \
    --num_train_epochs 3 \
    --learning_rate 2e-5 \
    --max_seq_length 2048 \
    --deepspeed ds_config.json \
    --logging_steps 10 \
    --save_steps 500
```

**显存紧张时用 LoRA**：

```bash
deepspeed --num_gpus=4 train.py \
    --model_name_or_path ./models/llama-2-7b \
    --train_file data/train.jsonl \
    --output_dir ./output \
    --per_device_train_batch_size 2 \
    --gradient_accumulation_steps 16 \
    --deepspeed ds_config.json \
    --use_lora \
    --lora_r 8 \
    --lora_alpha 16
```

### 6.2 多机多卡

**节点 0（Master）**：

```bash
deepspeed --num_gpus=8 \
    --num_nodes=2 \
    --master_addr=<node0_ip> \
    --master_port=29500 \
    train.py \
    --model_name_or_path ./models/llama-2-7b \
    --train_file /shared/data/train.jsonl \
    --output_dir /shared/output \
    --deepspeed ds_config.json \
    --per_device_train_batch_size 4
```

**节点 1（Worker）**：命令相同，`--master_addr` 指向节点 0。

### 6.3 使用 torchrun 启动（PyTorch 原生）

```bash
torchrun --nnodes=1 \
    --nproc_per_node=8 \
    --master_port=29500 \
    train.py \
    --model_name_or_path ./models/llama-2-7b \
    --train_file data/train.jsonl \
    --output_dir ./output \
    --deepspeed ds_config.json \
    --per_device_train_batch_size 4
```

## 7. 训练监控与验证

### 7.1 启动 TensorBoard

```bash
tensorboard --logdir=./output --port=6006
```

在浏览器打开 `http://localhost:6006` 查看 Loss 曲线与学习率变化。

### 7.2 实时 GPU 监控

```bash
# 每秒刷新一次
watch -n 1 nvidia-smi

# 查看进程级GPU使用情况
nvidia-smi pmon
```

### 7.3 验证训练结果

```python
# inference_test.py
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "./output"  # 或最佳检查点路径
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained(model_path)

prompt = "[INST] 解释什么是机器学习 [/INST]"
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(
    **inputs,
    max_new_tokens=256,
    temperature=0.7,
    do_sample=True,
    top_p=0.9,
)
response = tokenizer.decode(outputs[0], skip_special_tokens=True)
print(response)
```

## 8. Megatron-LM 补充方案（进阶）

预训练场景或追求极致性能时，可用 Megatron-LM 替代 DeepSpeed。

### 8.1 环境准备

```bash
git clone https://github.com/NVIDIA/Megatron-LM.git
cd Megatron-LM
pip install -r requirements.txt
```

### 8.2 7B 模型并行配置

2 节点 × 8 卡（16 卡）训练 7B 模型：

| 并行维度 | 取值 | 说明 |
|---|---|---|
| TP | 2 | 单层权重切到 2 卡，通信量可控 |
| PP | 4 | 32 层切成 4 个 Stage，每 Stage 8 层 |
| DP | 2 | 两条流水线处理不同数据 |
| 合计 | 16 | $2 \times 4 \times 2 = 16$ |

**约束检查**：

- $\mathrm{TP} \times \mathrm{PP} \times \mathrm{DP} = $ 总 GPU 数（2×4×2=16）✓
- `hidden-size` 能被 `tensor-model-parallel-size` 整除（4096÷2=2048）✓
- `num-attention-heads` 能被 `tensor-model-parallel-size` 整除（32÷2=16）✓

### 8.3 启动脚本示例

```bash
    --num-layers 32 \
    --hidden-size 4096 \
    --num-attention-heads 32 \
    --seq-length 2048 \
    --micro-batch-size 4 \
    --global-batch-size 64 \
    --tensor-model-parallel-size 2 \
    --pipeline-model-parallel-size 4 \
    --train-iters 10000 \
    --lr 3e-4 \
    --bf16 \
    --log-interval 10 \
    --save-interval 500 \
    --eval-interval 500 \
    --eval-iters 100
```

### 8.4 Megatron 与 DeepSpeed 的选择

| 维度 | Megatron-LM | DeepSpeed |
|---|---|---|
| 强项 | TP/PP 切分、通信重叠、极致 MFU | ZeRO 显存分片、Offload、易用 |
| 改造成本 | 高（需要模型代码适配） | 低（配置文件即可） |
| 典型场景 | 大规模预训练、追求峰值 | 微调、显存受限的单机多卡 |
| 组合方式 | 用 Megatron 做 TP/PP，用 DeepSpeed 做 ZeRO | 同上 |

## 9. 常见问题与排查

### 9.1 NCCL 初始化失败

**现象**：`RuntimeError: NCCL error: unhandled system error`。

**解决**：

1. 检查所有 GPU 是否可见：`nvidia-smi`。
2. 设置网络接口：`export NCCL_SOCKET_IFNAME=eth0`。
3. 检查 NCCL 版本兼容性。

### 9.2 OOM（显存溢出）

**现象**：`RuntimeError: CUDA out of memory`。

**排查**：

1. 检查 `micro_batch_size_per_gpu` 是否过大（7B 模型建议 2–4）。
2. 确认 ZeRO-3 已启用。
3. 启用 CPU Offload：`"offload_optimizer": {"device": "cpu"}`。
4. 启用激活值重计算：`"activation_checkpointing": {...}`。
5. 使用 LoRA 减少可训练参数。

### 9.3 训练速度慢

**现象**：每步耗时过长，GPU 利用率低。

**排查**：

1. 检查 `overlap_comm: true` 是否启用。
2. 增加 `allgather_bucket_size` 与 `reduce_bucket_size`。
3. 检查数据加载瓶颈（`num_workers`）。
4. 确认 NVLink/InfiniBand 正常工作。

### 9.4 Loss 不收敛或出现 NaN

**现象**：Loss 不下降或出现 `nan`/`inf`。

**排查**：

1. 检查学习率是否过高（7B 微调建议 1e-5 到 3e-5）。
2. 确认数据格式正确、无异常样本。
3. 检查梯度裁剪：`"gradient_clipping": 1.0`。
4. 尝试用 BF16 替代 FP16。
5. 减小学习率或增加预热步数。

## 10. 验收清单

| 验收项 | 标准 | 自查方式 |
|---|---|---|
| 环境可用 | `ds_report` 正常，GPU 数量符合预期 | 命令行输出 |
| 分布式启动 | 2–8 卡进程组建立成功 | 日志中见 rank/world_size |
| 稳定性 | 连续 1000 步无 OOM、无 Loss Spike | 训练日志 |
| 效率 | MFU > 35% | 按公式计算并留档 |
| 可恢复 | 从 Checkpoint 恢复后 loss 连续 | 中断后重启 |
| 效果 | 验证集 loss 下降，生成样例可读 | 推理脚本 |

## 11. 参考资源

- DeepSpeed 官方文档：https://www.deepspeed.ai/
- Megatron-LM GitHub：https://github.com/NVIDIA/Megatron-LM
- Hugging Face Transformers 文档：https://huggingface.co/docs/transformers
- 本系列相关篇目：ZeRO 原理与实战、混合精度训练、算子融合与图优化

## 写在最后

下一篇：[附录 2：端到端性能分析并优化至目标 MFU](/source/AI-Infra/1-大模型训练优化/28-附录2-项目二——对训练任务进行端到端的性能分析并优化至目标MFU)。
