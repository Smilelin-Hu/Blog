#!/usr/bin/env python3
import argparse
import json
import math
import random
import statistics
import struct
import time


def float_to_bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def bits_to_float(x):
    return struct.unpack("<f", struct.pack("<I", x & 0xFFFFFFFF))[0]


def round_fp32_fraction(x, keep_fraction_bits):
    """模拟保留 FP32 exponent，只减少 fraction bits；使用近似 RNE 位舍入。"""
    bits = float_to_bits(x)
    exponent = (bits >> 23) & 0xFF
    if exponent == 0xFF or keep_fraction_bits >= 23:
        return x
    drop = 23 - keep_fraction_bits
    # round-to-nearest-even：bias 加上保留结果最低位。
    lsb = (bits >> drop) & 1
    rounding_bias = (1 << (drop - 1)) - 1 + lsb
    rounded = bits + rounding_bias
    mask = ~((1 << drop) - 1) & 0xFFFFFFFF
    return bits_to_float(rounded & mask)


def to_tf32(x):
    return round_fp32_fraction(x, 10)


def to_bf16(x):
    return round_fp32_fraction(x, 7)


def to_fp16(x):
    try:
        return struct.unpack("<e", struct.pack("<e", float(x)))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def quantize_int(values, bits, symmetric=True):
    if symmetric:
        qmax = 2 ** (bits - 1) - 1
        qmin = -qmax
        amax = max(abs(v) for v in values) or 1.0
        scale = amax / qmax
        q = [max(qmin, min(qmax, round(v / scale))) for v in values]
        dq = [v * scale for v in q]
        zero_point = 0
    else:
        qmin, qmax = 0, 2**bits - 1
        vmin, vmax = min(values), max(values)
        scale = (vmax - vmin) / max(qmax - qmin, 1) or 1.0
        zero_point = round(qmin - vmin / scale)
        q = [max(qmin, min(qmax, round(v / scale) + zero_point))
             for v in values]
        dq = [(v - zero_point) * scale for v in q]
    return q, dq, scale, zero_point


def error_stats(reference, actual):
    finite_pairs = [(a, b) for a, b in zip(reference, actual)
                    if math.isfinite(a) and math.isfinite(b)]
    abs_err = [abs(a - b) for a, b in finite_pairs]
    signal = math.sqrt(sum(a * a for a, _ in finite_pairs) /
                       max(len(finite_pairs), 1))
    rmse = math.sqrt(sum(x * x for x in abs_err) /
                     max(len(abs_err), 1))
    return {
        "max_abs_finite": max(abs_err, default=0.0),
        "mean_abs_finite": statistics.fmean(abs_err) if abs_err else 0.0,
        "rmse": rmse,
        "relative_rmse": rmse / max(signal, 1e-30),
        "finite_pair_count": len(finite_pairs),
        "inf_count": sum(math.isinf(x) for x in actual),
        "zero_count": sum(x == 0.0 for x in actual),
    }


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def level0(samples, seed, tile_multiple):
    rng = random.Random(seed)
    # 对数跨度用于同时观察大数、小数、溢出与下溢。
    values = []
    for _ in range(samples):
        sign = -1.0 if rng.random() < 0.5 else 1.0
        exponent = rng.uniform(-8.0, 5.0)
        values.append(sign * (10.0 ** exponent))

    formats = {
        "tf32_sim": [to_tf32(x) for x in values],
        "bf16_sim": [to_bf16(x) for x in values],
        "fp16_python": [to_fp16(x) for x in values],
    }

    small = [rng.gauss(0.0, 1.0) for _ in range(4096)]
    _, int8_deq, int8_scale, _ = quantize_int(small, 8)
    _, int4_deq, int4_scale, _ = quantize_int(small, 4)

    a = [rng.gauss(0.0, 1.0) for _ in range(4096)]
    b = [rng.gauss(0.0, 1.0) for _ in range(4096)]
    dot_ref = dot(a, b)
    dots = {
        "fp32_python": dot_ref,
        "tf32_inputs_fp64_acc": dot([to_tf32(x) for x in a],
                                     [to_tf32(x) for x in b]),
        "bf16_inputs_fp64_acc": dot([to_bf16(x) for x in a],
                                     [to_bf16(x) for x in b]),
        "fp16_inputs_fp64_acc": dot([to_fp16(x) for x in a],
                                     [to_fp16(x) for x in b]),
    }

    shapes = []
    for m, n, k in [(127, 127, 127), (128, 128, 128),
                    (511, 1025, 4095), (512, 1024, 4096)]:
        mp = math.ceil(m / tile_multiple) * tile_multiple
        np = math.ceil(n / tile_multiple) * tile_multiple
        kp = math.ceil(k / tile_multiple) * tile_multiple
        shapes.append({
            "shape": [m, n, k],
            "padded": [mp, np, kp],
            "useful_compute_ratio": (m * n * k) / (mp * np * kp),
        })

    return {
        "format_error": {name: error_stats(values, result)
                         for name, result in formats.items()},
        "integer_quantization": {
            "int8": {"scale": int8_scale,
                     "error": error_stats(small, int8_deq)},
            "int4": {"scale": int4_scale,
                     "error": error_stats(small, int4_deq)},
        },
        "dot_product": {
            name: {"value": value,
                   "relative_error": abs(value - dot_ref) /
                                     max(abs(dot_ref), 1e-30)}
            for name, value in dots.items()
        },
        "shape_padding_model": shapes,
        "warning": "数值模拟不等于对应 Tensor Core 硬件执行",
    }


def set_tf32(torch, enabled):
    """兼容 PyTorch 新 fp32_precision API 与旧 allow_tf32 API。"""
    mode = "tf32" if enabled else "ieee"
    try:
        torch.backends.cuda.matmul.fp32_precision = mode
        return "fp32_precision"
    except (AttributeError, RuntimeError, TypeError):
        torch.backends.cuda.matmul.allow_tf32 = enabled
        return "allow_tf32"


def cuda_median_ms(torch, fn, repeat, warmup=5):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    samples = []
    for _ in range(repeat):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        fn()
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end))
    return statistics.median(samples)


def cpu_median_ms(fn, repeat, warmup=2):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def torch_level(matrix_n, repeat, train_steps, hidden, batch):
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "未安装 PyTorch"}

    use_cuda = torch.cuda.is_available() and torch.version.cuda is not None
    device = torch.device("cuda" if use_cuda else "cpu")
    output = {
        "available": True,
        "torch_version": torch.__version__,
        "device": str(device),
    }
    if use_cuda:
        name = torch.cuda.get_device_name(0)
        cc = torch.cuda.get_device_capability(0)
        output.update({
            "gpu": name,
            "compute_capability": f"{cc[0]}.{cc[1]}",
            "cuda_runtime": torch.version.cuda,
            "bf16_supported": bool(torch.cuda.is_bf16_supported()),
            "capability_notes": {
                "tf32": cc[0] >= 8,
                "fp8_tensor_core": cc == (8, 9) or cc[0] >= 9,
                "blackwell_low_precision": cc[0] >= 10,
            },
        })

    torch.manual_seed(7)
    a32 = torch.randn((matrix_n, matrix_n), device=device,
                      dtype=torch.float32)
    b32 = torch.randn((matrix_n, matrix_n), device=device,
                      dtype=torch.float32)

    timer = (lambda fn: cuda_median_ms(torch, fn, repeat)) \
        if use_cuda else (lambda fn: cpu_median_ms(fn, repeat))

    # IEEE FP32 reference；CUDA 上显式关闭 TF32。
    if use_cuda:
        set_tf32(torch, False)
    reference = torch.mm(a32, b32)
    if use_cuda:
        torch.cuda.synchronize()

    results = []

    def add_result(label, a, b, configure=None):
        if configure:
            api = configure()
        else:
            api = None
        try:
            ms = timer(lambda: torch.mm(a, b))
            result = torch.mm(a, b).float()
            if use_cuda:
                torch.cuda.synchronize()
            diff = result - reference
            rel_l2 = (torch.linalg.vector_norm(diff) /
                      torch.linalg.vector_norm(reference)).item()
            tflops = (2 * matrix_n**3) / (ms / 1000) / 1e12
            results.append({
                "mode": label,
                "input_dtype": str(a.dtype),
                "median_ms": ms,
                "effective_tflops": tflops,
                "relative_l2_error_vs_ieee_fp32": rel_l2,
                "control_api": api,
            })
        except RuntimeError as exc:
            results.append({"mode": label, "skipped": True,
                            "reason": str(exc).splitlines()[0]})

    if use_cuda:
        add_result("fp32_ieee", a32, b32,
                   lambda: set_tf32(torch, False))
        add_result("fp32_tf32_allowed", a32, b32,
                   lambda: set_tf32(torch, True))
    else:
        add_result("fp32_cpu", a32, b32)

    add_result("fp16", a32.to(torch.float16), b32.to(torch.float16))
    if not use_cuda or torch.cuda.is_bf16_supported():
        add_result("bf16", a32.to(torch.bfloat16),
                   b32.to(torch.bfloat16))
    else:
        results.append({"mode": "bf16", "skipped": True,
                        "reason": "当前 CUDA 设备/栈未报告 BF16 支持"})
    output["matmul"] = {"n": matrix_n, "results": results}

    # 最小训练实验：相同初始权重，比较 FP32 与 AMP 的 Step 时间和稳定性。
    if train_steps > 0:
        import copy
        model_base = torch.nn.Sequential(
            torch.nn.Linear(hidden, hidden * 2),
            torch.nn.GELU(),
            torch.nn.Linear(hidden * 2, hidden),
        ).to(device)
        x = torch.randn((batch, hidden), device=device)
        target = torch.randn((batch, hidden), device=device)

        def run_train(use_amp, amp_dtype):
            model = copy.deepcopy(model_base)
            opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
            scaler_enabled = use_cuda and use_amp and amp_dtype == torch.float16
            try:
                scaler = torch.amp.GradScaler("cuda", enabled=scaler_enabled)
            except TypeError:
                scaler = torch.cuda.amp.GradScaler(enabled=scaler_enabled)
            times, losses = [], []
            for _ in range(train_steps):
                if use_cuda:
                    torch.cuda.synchronize()
                start = time.perf_counter()
                opt.zero_grad(set_to_none=True)
                with torch.autocast(
                    device_type=device.type,
                    dtype=amp_dtype,
                    enabled=use_amp,
                ):
                    pred = model(x)
                    loss = torch.nn.functional.mse_loss(pred, target)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
                if use_cuda:
                    torch.cuda.synchronize()
                times.append((time.perf_counter() - start) * 1000)
                losses.append(float(loss.detach()))
            return {
                "median_step_ms": statistics.median(times[2:] or times),
                "first_loss": losses[0],
                "last_loss": losses[-1],
                "finite": all(math.isfinite(x) for x in losses),
                "grad_scaler_enabled": scaler_enabled,
            }

        train = {"fp32": run_train(False, torch.float32)}
        if use_cuda:
            preferred = (torch.bfloat16 if torch.cuda.is_bf16_supported()
                         else torch.float16)
            train[str(preferred)] = run_train(True, preferred)
        else:
            # CPU autocast 仅作为流程回退，不代表 Tensor Core。
            train["cpu_bfloat16_autocast"] = run_train(True, torch.bfloat16)
        output["training"] = {
            "steps": train_steps,
            "batch": batch,
            "hidden": hidden,
            "runs": train,
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--tile-multiple", type=int, default=16)
    parser.add_argument("--torch", action="store_true")
    parser.add_argument("--matrix-n", type=int, default=1024)
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--train-steps", type=int, default=0)
    parser.add_argument("--hidden", type=int, default=1024)
    parser.add_argument("--batch", type=int, default=256)
    args = parser.parse_args()

    output = {"level0": level0(args.samples, args.seed,
                               args.tile_multiple)}
    if args.torch:
        output["level1"] = torch_level(
            args.matrix_n, args.repeat, args.train_steps,
            args.hidden, args.batch
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
