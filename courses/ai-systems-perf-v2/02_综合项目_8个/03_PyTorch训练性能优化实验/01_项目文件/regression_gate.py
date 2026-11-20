#!/usr/bin/env python3
import argparse
import json


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--max-regression", type=float, default=0.05)
    parser.add_argument("--max-loss-delta", type=float, default=0.20)
    args = parser.parse_args()

    baseline = load(args.baseline)
    candidate = load(args.candidate)
    if baseline["batch_size"] != candidate["batch_size"]:
        raise SystemExit("FAIL: batch_size 不一致，不能直接比较")
    if candidate["valid_step_ratio"] < 1.0:
        raise SystemExit("FAIL: 存在非有限损失或无效 Step")

    ratio = candidate["p50_step_ms"] / baseline["p50_step_ms"]
    loss_delta = abs(candidate["final_loss"] - baseline["final_loss"])
    print(f"p50_ratio={ratio:.4f}, loss_delta={loss_delta:.6f}")
    if ratio > 1.0 + args.max_regression:
        raise SystemExit("FAIL: P50 Step Time 超过回归阈值")
    if loss_delta > args.max_loss_delta:
        raise SystemExit("FAIL: 损失差异超过阈值")
    print("PASS")


if __name__ == "__main__":
    main()
