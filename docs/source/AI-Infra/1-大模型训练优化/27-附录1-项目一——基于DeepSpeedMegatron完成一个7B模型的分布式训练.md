# 附录1：项目一——基于DeepSpeed Megatron完成一个7B模型的分布式训练

## 1. 项目概述
本附录提供项目一的完整实施方案，从零开始完成一个7B大模型的分布式训练全流程。为便于上手，本方案以**DeepSpeed**为主线、**Llama-2-7B**为目标模型、**单机多卡**为部署场景，同时提供Megatron-LM的补充方案供进阶参考。
**项目目标**：
- 在2-8张GPU上完成7B模型的分布式训练（微调）
- 使用DeepSpeed ZeRO-3作为优化策略
- 训练稳定运行至少1000步，无OOM、无Loss Spike
- MFU（模型算力利用率）达到35%以上
**硬件要求**：
- 最低配置：2张A100 80GB GPU
- 推荐配置：4-8张A100/H100 GPU + NVLink互联
- 替代方案：2张以上RTX 3090/4090（24GB）配合ZeRO-3 + CPU Offload
### 2.1. 创建Conda环境
```text
# 创建Python 3.10环境
conda create -n llm_train python=3.10 -y
conda activate llm_train
```
### 2.2. 安装PyTorch
根据GPU的CUDA版本选择合适的PyTorch版本。以CUDA 11.8为例：
```bash
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu118
```
**兼容性提示**：如需使用FlashAttention等高级特性，建议PyTorch ≥ 2.0。不同硬件平台（如昇腾NPU）需安装对应的`torch_npu`插件。
### 2.3. 安装核心库
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
**版本说明**：以上版本组合经过验证，若使用更新的版本需注意兼容性。DeepSpeed 0.12.4是当前较稳定的版本。
### 2.4. 验证安装
```text
# 验证PyTorch和CUDA
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"

# 验证DeepSpeed
ds_report
```
`ds_report`命令会输出DeepSpeed检测到的CUDA版本、PyTorch版本、NCCL版本及可用的优化算子（如FusedAdam、FusedLamb等）。
### 2.5. （可选）安装FlashAttention
FlashAttention可显著加速长序列训练【16†L0】：
```bash
pip install flash-attn --no-build-isolation
```
若安装失败（常见于旧版CUDA或GCC），可尝试预编译wheel或使用`xformers`作为替代：
```bash
pip install xformers
```
### 3.1. 获取Llama-2-7B模型权重
**方式一：通过Hugging Face下载**
Llama-2需要Meta官方授权，首先需在[Hugging Face](https://huggingface.co/meta-llama/Llama-2-7b-hf)页面申请访问权限。
```text
# 输入Access Token

# 下载模型
huggingface-cli download meta-llama/Llama-2-7b-hf --local-dir ./models/llama-2-7b
```
**方式二：使用国内镜像（如遇网络问题）**
```bash
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download meta-llama/Llama-2-7b-hf --local-dir ./models/llama-2-7b
```
**方式三：使用其他开源模型**
若无法获取Llama-2授权，可使用以下替代模型：
- **Qwen-7B**：`Qwen/Qwen-7B`（需申请）
- **Baichuan2-7B**：`baichuan-inc/Baichuan2-7B-Base`
- **DeepSeek-V2-Lite**：`deepseek-ai/DeepSeek-V2-Lite`
- **Mistral-7B**：`mistralai/Mistral-7B-v0.1`（Apache 2.0授权，无需申请）
### 3.2. 验证模型文件
下载完成后，检查目录应包含以下文件：
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
### 4.1. 数据格式
准备JSON Lines格式的训练数据，每条数据为一个JSON对象：
```json
{"instruction": "解释什么是机器学习", "output": "机器学习是人工智能的一个分支，它使计算机能够从数据中学习并改进..."}
{"instruction": "写一首关于秋天的诗", "output": "秋风萧瑟天气凉，草木摇落露为霜..."}
{"instruction": "如何提高学习效率", "output": "提高学习效率可以从以下几个方面入手：1. 制定明确的学习计划..."}
```
**文件结构**：
```text
./data/
├── train.jsonl    # 训练集
└── eval.jsonl     # 验证集（可选）
```
建议训练集至少包含**1000-5000条**高质量样本，验证集约**100-200条**。
### 4.2. 数据加载脚本
```text
            "train": train_path,
            "eval": eval_path
        }
    )
    return dataset

# 使用示例
if __name__ == "__main__":
    dataset = load_training_data()
    print(f"训练集大小: {len(dataset['train'])}")
    print(f"验证集大小: {len(dataset['eval'])}")
    print(f"样本示例: {dataset['train'][0]}")
```
### 4.3. 数据格式化函数
对于指令微调（SFT），需要将数据格式化为模型可接受的对话格式：
```python
# format_utils.py
def format_instruction(example):
    """将instruction-output格式转换为模型输入格式"""
    # Llama-2的对话格式
    return {
        "text": f"<s>[INST] {example['instruction']} [/INST] {example['output']} </s>"
    }

# 批量格式化
def preprocess_dataset(dataset):
    """对整个数据集应用格式化"""
    return dataset.map(format_instruction)
```
### 5.1. 创建DeepSpeed配置文件
创建`ds_config.json`：
```text
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
### 5.2. 关键参数解读
> [内嵌电子表格，分享态无法直接读取内容]
### 5.3. ZeRO阶段选择指南
> [内嵌电子表格，分享态无法直接读取内容]
### 6.1. 完整训练脚本
创建`train.py`：
```python
        use_cache=False,  # 训练时禁用KV cache
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
    dataset = load_dataset(
        "json",
        data_files={
            "train": args.train_file,
            "eval": args.eval_file if args.eval_file else None,
        }
    )

    # 4. 数据预处理函数
    def format_instruction(example):
        """将instruction-output格式转换为模型输入"""
        text = f"<s>[INST] {example['instruction']} [/INST] {example['output']} </s>"
        return {"text": text}

    def tokenize_function(examples):
        """对文本进行分词"""
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=args.max_seq_length,
            padding=False,
        )

    # 应用预处理
    if "train" in dataset:
        dataset["train"] = dataset["train"].map(format_instruction)
        dataset["train"] = dataset["train"].map(
            tokenize_function,
            batched=True,
            remove_columns=dataset["train"].column_names,
        )

    if "eval" in dataset and dataset["eval"] is not None:
        dataset["eval"] = dataset["eval"].map(format_instruction)
        dataset["eval"] = dataset["eval"].map(
            tokenize_function,
            batched=True,
            remove_columns=dataset["eval"].column_names,
        )

    # 5. 数据整理器
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,  # 因果语言模型不使用MLM
    )

    # 6. 训练参数
    training_args = TrainingArguments(
```
### 6.2. 脚本关键设计说明
**BF16 vs FP16**：脚本使用`bf16=True`而非`fp16=True`。BF16的动态范围与FP32相同，不易产生梯度下溢，是大模型训练的更优选择【15†L0】。若硬件不支持BF16（如V100），可改为`fp16=True`。
**Gradient Checkpointing**：通过`gradient_checkpointing=True`启用激活值重计算，以少量计算时间换取大量显存【13†L0】。
**LoRA支持**：通过`--use_lora`参数可启用参数高效微调，大幅降低显存需求。
### 7.1. 单机多卡训练（推荐）
使用DeepSpeed启动器：
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
**使用LoRA（显存紧张时）**：
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
### 7.2. 多机多卡训练
**节点0（Master）**：
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
**节点1（Worker）**：
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
### 7.3. 使用torchrun启动（PyTorch原生）
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
### 8.1. 启动TensorBoard
在训练过程中或训练完成后，启动TensorBoard查看训练曲线：
```text
tensorboard --logdir=./output --port=6006
```
在浏览器中打开`[http://localhost:6006](http://localhost:6006)`，查看Loss曲线、学习率变化等。
### 8.2. 实时GPU监控
使用`nvidia-smi`实时监控GPU利用率和显存占用：
```bash
# 每秒刷新一次
watch -n 1 nvidia-smi

# 查看进程级GPU使用情况
nvidia-smi pmon
```
### 8.3. 验证训练结果
训练完成后，使用以下脚本进行简单验证：
```python
# inference_test.py
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "./output"  # 或最佳检查点路径
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(model_path)

# 测试生成
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
## 9. 第八部分：Megatron-LM补充方案（进阶）
对于预训练场景或追求极致性能的开发者，可使用Megatron-LM替代DeepSpeed。
### 9.1. 环境准备
```bash
git clone https://github.com/NVIDIA/Megatron-LM.git
cd Megatron-LM
pip install -r requirements.txt
```
### 9.2. 7B模型并行配置
对于2节点×8卡（16卡）的7B模型训练：
> [内嵌电子表格，分享态无法直接读取内容]
**约束检查**：
- `TP × PP × DP = 总GPU数`（2×4×2=16）✓
- `hidden-size`能被`tensor-model-parallel-size`整除（4096÷2=2048）✓
- `num-attention-heads`能被`tensor-model-parallel-size`整除（32÷2=16）✓
### 9.3. 启动脚本示例
```text
    --log-interval 10 \
    --save-interval 500 \
    --eval-interval 500 \
    --eval-iters 100
```
### 9.4. Megatron vs DeepSpeed选择建议
> [内嵌电子表格，分享态无法直接读取内容]
### 10.1. NCCL初始化失败
**现象**：
```text
RuntimeError: NCCL error: unhandled system error
```
**解决方案**：
1. 检查所有GPU是否可见：`nvidia-smi`
2. 设置网络接口：`export NCCL_SOCKET_IFNAME=eth0`
3. 检查NCCL版本兼容性
### 10.2. OOM（显存溢出）
**现象**：
```text
RuntimeError: CUDA out of memory
```
**排查步骤**：
1. 检查`train_micro_batch_size_per_gpu`是否过大（7B模型建议2-4）
2. 确认ZeRO-3已启用
3. 启用CPU Offload：`"offload_optimizer": {"device": "cpu"}`
4. 启用激活值重计算：`"activation_checkpointing": {...}`
5. 使用LoRA减少可训练参数
### 10.3. 训练速度慢
**现象**：每步耗时过长，GPU利用率低
**排查步骤**：
1. 检查`overlap_comm: true`是否启用
2. 增加`allgather_bucket_size`和`reduce_bucket_size`
3. 检查数据加载瓶颈（`num_workers`）
4. 确认NVLink/InfiniBand正常工作
### 10.4. Loss不收敛或出现NaN
**现象**：Loss不下降或出现`nan`/`inf`
**排查步骤**：
1. 检查学习率是否过高（7B微调建议1e-5到3e-5）
2. 确认数据格式正确，无异常样本
3. 检查梯度裁剪：`"gradient_clipping": 1.0`
4. 尝试使用BF16替代FP16【15†L0】
5. 减小学习率或增加预热步数
## 11. 验收清单
> [内嵌电子表格，分享态无法直接读取内容]
## 12. 参考资源
- DeepSpeed官方文档：[https://www.deepspeed.ai/](https://www.deepspeed.ai/)
- Megatron-LM GitHub：[https://github.com/NVIDIA/Megatron-LM](https://github.com/NVIDIA/Megatron-LM)
- Hugging Face Transformers文档：[https://huggingface.co/docs/transformers](https://huggingface.co/docs/transformers)
- 本篇程后文（ZeRO原理与实战）、后文（混合精度训练）、后文（算子融合与图优化）

## 写在最后

下一篇：[附录2：项目二——对训练任务进行端到端的性能分析并优化至目标MFU](/source/AI-Infra/1-大模型训练优化/28-附录2-项目二——对训练任务进行端到端的性能分析并优化至目标MFU.md)。
