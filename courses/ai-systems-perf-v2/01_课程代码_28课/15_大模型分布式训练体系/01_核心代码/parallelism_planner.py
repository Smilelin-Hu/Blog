#!/usr/bin/env python3
import argparse
import json


GIB = 1024 ** 3


def model_state_bytes(params, dp, zero_stage):
    # 经典混合精度 Adam 粗略模型：参数2B、梯度2B、主参数4B、动量8B。
    if zero_stage == 0:
        return 16 * params
    if zero_stage == 1:
        return 4 * params + 12 * params / dp
    if zero_stage == 2:
        return 2 * params + 14 * params / dp
    if zero_stage == 3:
        return 16 * params / dp
    raise ValueError("zero_stage 必须为 0、1、2 或 3")


def main():
    p = argparse.ArgumentParser(description="分布式训练并行度与静态显存规划器")
    p.add_argument("--params-b", type=float, default=7.0)
    p.add_argument("--world-size", type=int, default=8)
    p.add_argument("--tp", type=int, default=1)
    p.add_argument("--pp", type=int, default=1)
    p.add_argument("--micro-batch", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--pipeline-microbatches", type=int, default=None)
    p.add_argument("--zero-stage", type=int, default=0)
    p.add_argument("--sequence-length", type=int, default=4096)
    p.add_argument("--hidden-size", type=int, default=4096)
    p.add_argument("--layers", type=int, default=32)
    args = p.parse_args()

    if min(args.world_size, args.tp, args.pp, args.micro_batch,
           args.grad_accum, args.sequence_length, args.hidden_size,
           args.layers) <= 0:
        raise ValueError("并行度、Batch 和模型形状必须为正数")
    model_parallel = args.tp * args.pp
    if args.world_size % model_parallel != 0:
        raise ValueError("world_size 必须能被 tp × pp 整除")

    dp = args.world_size // model_parallel
    total_params = args.params_b * 1e9
    local_partition_params = total_params / model_parallel
    global_batch = args.micro_batch * args.grad_accum * dp
    state_bytes = model_state_bytes(
        local_partition_params, dp, args.zero_stage
    )

    m = args.pipeline_microbatches or args.grad_accum
    bubble = 0.0 if args.pp == 1 else (args.pp - 1) / (m + args.pp - 1)

    # 仅用于比较形状规模，不等同于真实激活显存。
    activation_elements_proxy = (
        args.micro_batch * args.sequence_length * args.hidden_size
        * (args.layers / args.pp)
    )

    # 仅是普通 DDP 梯度环形 All-Reduce 的粗略通信量。
    grad_bytes = 2 * local_partition_params
    ddp_ring_bytes = 0.0 if dp == 1 else 2 * (dp - 1) / dp * grad_bytes

    result = {
        "degrees": {"world": args.world_size, "dp": dp,
                    "tp": args.tp, "pp": args.pp},
        "global_batch": global_batch,
        "local_partition_params_b": local_partition_params / 1e9,
        "zero_stage": args.zero_stage,
        "approx_model_state_gib_per_rank": state_bytes / GIB,
        "simple_pipeline_bubble_fraction": bubble,
        "activation_elements_proxy": activation_elements_proxy,
        "ddp_ring_gradient_traffic_gib_per_rank": ddp_ring_bytes / GIB,
        "warnings": [
            "显存估算不含激活、通信缓冲、临时Workspace和碎片",
            "activation_elements_proxy不是激活显存公式",
            "ZeRO/FSDP的真实通信模式不能用普通DDP流量替代",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
