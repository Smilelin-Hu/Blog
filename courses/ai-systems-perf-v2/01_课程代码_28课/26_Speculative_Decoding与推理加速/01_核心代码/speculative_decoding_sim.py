#!/usr/bin/env python3
import argparse
import random


def expected_tokens(alpha: float, k: int) -> float:
    if abs(alpha - 1.0) < 1e-12:
        return k + 1.0
    return (1.0 - alpha ** (k + 1)) / (1.0 - alpha)


def run(tokens, k, alpha, target_ms, draft_ms, verify_base_ms,
        verify_per_token_ms, overhead_ms, seed):
    rng = random.Random(seed)
    emitted = rounds = accepted = proposed = rejected = 0
    spec_ms = 0.0

    while emitted < tokens:
        rounds += 1
        a = 0
        for _ in range(k):
            proposed += 1
            if rng.random() < alpha:
                a += 1
                accepted += 1
            else:
                break

        # 接受前缀后，总有一个来自目标分布的 token 可提交；末尾截断。
        committed = min(a + 1, tokens - emitted)
        emitted += committed
        rejected += k - a
        spec_ms += (k * draft_ms + verify_base_ms
                    + k * verify_per_token_ms + overhead_ms)

    base_ms = tokens * target_ms
    empirical_n = tokens / rounds
    theoretical_n = expected_tokens(alpha, k)
    print(f"tokens={tokens} k={k} alpha={alpha:.3f}")
    print(f"rounds={rounds} empirical_tokens/round={empirical_n:.3f}")
    print(f"theoretical_tokens/round={theoretical_n:.3f}")
    print(f"accepted/proposed={accepted}/{proposed} ({accepted/max(1, proposed):.3f})")
    print(f"rejected_or_unused_slots={rejected}")
    print(f"baseline_ms={base_ms:.2f} speculative_ms={spec_ms:.2f}")
    print(f"estimated_speedup={base_ms/spec_ms:.3f}x")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=4096)
    p.add_argument("--draft-k", type=int, default=4)
    p.add_argument("--acceptance", type=float, default=0.75)
    p.add_argument("--target-ms", type=float, default=8.0)
    p.add_argument("--draft-ms", type=float, default=0.45)
    p.add_argument("--verify-base-ms", type=float, default=8.5)
    p.add_argument("--verify-per-token-ms", type=float, default=0.25)
    p.add_argument("--overhead-ms", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    if not 0.0 <= a.acceptance <= 1.0 or a.draft_k < 1:
        p.error("acceptance 必须在 [0,1]，draft-k 必须 >= 1")
    run(a.tokens, a.draft_k, a.acceptance, a.target_ms, a.draft_ms,
        a.verify_base_ms, a.verify_per_token_ms, a.overhead_ms, a.seed)
