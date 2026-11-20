#!/usr/bin/env python3
import argparse


def main():
    p = argparse.ArgumentParser(description="torch.compile ROI planner")
    p.add_argument("--compile-seconds", type=float, default=20.0)
    p.add_argument("--eager-ms", type=float, default=10.0)
    p.add_argument("--compiled-ms", type=float, default=6.0)
    p.add_argument("--calls", type=int, nargs="+", default=[100, 1000, 5000, 20000])
    p.add_argument("--variants", type=int, default=1,
                   help="实际会生成的编译版本数量")
    args = p.parse_args()

    if min(args.compile_seconds, args.eager_ms, args.compiled_ms) < 0:
        raise SystemExit("时间不能为负数")
    if args.variants < 1 or any(n < 1 for n in args.calls):
        raise SystemExit("variants 和 calls 必须为正整数")

    compile_ms = args.compile_seconds * 1000.0 * args.variants
    delta = args.eager_ms - args.compiled_ms
    if delta > 0:
        break_even = compile_ms / delta
        print(f"break_even_calls={break_even:.1f}")
    else:
        break_even = float("inf")
        print("break_even_calls=never (compiled steady-state is not faster)")

    print("calls eager_total_s compiled_total_s net_saved_s decision")
    for n in args.calls:
        eager_total = n * args.eager_ms
        compiled_total = compile_ms + n * args.compiled_ms
        saved = (eager_total - compiled_total) / 1000.0
        decision = "compile" if saved > 0 else "eager"
        print(f"{n:5d} {eager_total/1000:13.3f} "
              f"{compiled_total/1000:16.3f} {saved:11.3f} {decision}")


if __name__ == "__main__":
    main()
