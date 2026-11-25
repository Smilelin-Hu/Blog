from __future__ import annotations

import json
import platform
import time
from typing import Any


def _skipped(experiment_id: str, reason: str) -> dict[str, Any]:
    return {"status": "skipped", "experiment_id": experiment_id, "reason": reason, "proof_boundary": "no_gpu_measurement"}


def run_gpu_probe(experiment_id: str, mode: str, scale: int = 1) -> dict[str, Any]:
    try:
        import torch
    except Exception as exc:
        return _skipped(experiment_id, f"PyTorch unavailable: {type(exc).__name__}: {exc}")
    if not torch.cuda.is_available():
        return _skipped(experiment_id, "CUDA device unavailable")

    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(device)
    torch.manual_seed(7)
    dim = min(256 * max(scale, 1), 1024)
    torch.cuda.reset_peak_memory_stats(device)
    torch.cuda.synchronize(device)
    start = time.perf_counter()

    metrics: dict[str, Any]
    if mode == "masked_loss":
        batch, seq, vocab = 4 * scale, 128 * scale, 2048
        logits = torch.randn(batch, seq, vocab, device=device, dtype=torch.float16, requires_grad=True)
        labels = torch.randint(0, vocab, (batch, seq), device=device)
        mask = torch.arange(seq, device=device)[None, :] >= seq // 3
        mask = mask.expand(batch, -1)
        loss = torch.nn.functional.cross_entropy(logits.float().reshape(-1, vocab), labels.reshape(-1), reduction="none")
        value = (loss.reshape(batch, seq) * mask).sum() / mask.sum()
        value.backward()
        metrics = {"loss": float(value.detach()), "supervised_tokens": int(mask.sum())}
    elif mode == "embedding_similarity":
        x = torch.randn(dim * 4, dim, device=device, dtype=torch.float16)
        x = torch.nn.functional.normalize(x.float(), dim=-1)
        sim = x @ x.T
        metrics = {"vectors": x.shape[0], "dimension": x.shape[1], "mean_similarity": float(sim.mean())}
    elif mode == "sampling":
        logits = torch.randn(dim * 8, 4096, device=device, dtype=torch.float16)
        probs = torch.softmax(logits.float(), dim=-1)
        samples = torch.multinomial(probs, num_samples=1)
        metrics = {"rows": logits.shape[0], "vocab": logits.shape[1], "sample_checksum": int(samples.sum())}
    elif mode == "weight_sync":
        source = torch.randn(dim, dim * 8, device=device, dtype=torch.float16)
        target = torch.empty_like(source)
        for _ in range(8):
            target.copy_(source)
        metrics = {"copied_bytes": source.numel() * source.element_size() * 8, "checksum": float(target[:8, :8].float().sum())}
    elif mode == "checkpoint_state":
        weights = torch.randn(dim, dim, device=device, dtype=torch.float16)
        optimizer = torch.randn(dim, dim, device=device, dtype=torch.float32)
        snapshot = torch.cat([weights.float().flatten()[:4096], optimizer.flatten()[:4096]]).cpu()
        metrics = {"snapshot_values": snapshot.numel(), "snapshot_checksum": float(snapshot.sum())}
    else:
        x = torch.randn(dim, dim, device=device, dtype=torch.float16)
        y = torch.randn(dim, dim, device=device, dtype=torch.float16)
        z = x @ y
        metrics = {"matrix_dim": dim, "checksum": float(z.float().mean())}

    torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - start
    return {
        "status": "passed",
        "experiment_id": experiment_id,
        "mode": mode,
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "device": props.name,
            "device_count": torch.cuda.device_count(),
            "total_memory_bytes": props.total_memory,
        },
        "metrics": {
            **metrics,
            "elapsed_seconds": elapsed,
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
        },
        "proof_boundary": "single_process_cuda_path_only",
    }


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
