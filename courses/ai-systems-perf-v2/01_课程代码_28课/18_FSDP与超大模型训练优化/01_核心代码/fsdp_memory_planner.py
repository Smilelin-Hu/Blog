#!/usr/bin/env python3
import argparse

GB = 1024 ** 3


def gib(x):
    return x / GB


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--params-b", type=float, default=7.0,
                   help="参数量，单位十亿")
    p.add_argument("--world-size", type=int, default=2)
    p.add_argument("--param-bytes", type=float, default=4)
    p.add_argument("--grad-bytes", type=float, default=4)
    p.add_argument("--optim-bytes", type=float, default=8)
    p.add_argument("--comm-param-bytes", type=float, default=2)
    p.add_argument("--largest-group-mb", type=float, default=512)
    p.add_argument("--activation-gb", type=float, default=4)
    p.add_argument("--prefetch-groups", type=int, default=1)
    p.add_argument("--fragment-ratio", type=float, default=0.10)
    args = p.parse_args()

    if args.world_size < 1:
        raise SystemExit("world-size 必须 >= 1")

    params = args.params_b * 1e9
    state = params * (args.param_bytes + args.grad_bytes + args.optim_bytes)
    ddp = state + args.activation_gb * GB

    group = args.largest_group_mb * 1024 ** 2
    # 当前组 + 提前拉取组；真实框架还会有通信缓冲和 allocator 碎片。
    fsdp_raw = (
        state / args.world_size
        + group * args.comm_param_bytes / args.param_bytes
          * (1 + args.prefetch_groups)
        + args.activation_gb * GB
    )
    fsdp = fsdp_raw * (1 + args.fragment_ratio)

    n = args.world_size
    ring = (n - 1) / n if n > 1 else 0
    ddp_comm = 2 * ring * params * args.grad_bytes
    fsdp_comm = 3 * ring * params * args.comm_param_bytes

    print(f"参数量: {args.params_b:.2f}B, world_size={n}")
    print(f"完整模型状态: {gib(state):.2f} GiB")
    print(f"DDP 单卡粗估: {gib(ddp):.2f} GiB")
    print(f"FSDP 单卡峰值粗估: {gib(fsdp):.2f} GiB")
    print(f"DDP 每 rank/step 通信粗估: {gib(ddp_comm):.2f} GiB")
    print(f"FSDP 每 rank/step 通信粗估: {gib(fsdp_comm):.2f} GiB")
    print("边界：不含 CUDA context、临时算子、真实预取生命周期和 checkpoint I/O。")


if __name__ == "__main__":
    main()
