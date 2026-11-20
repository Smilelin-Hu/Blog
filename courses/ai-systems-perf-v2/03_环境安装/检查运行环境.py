#!/usr/bin/env python3
import importlib.util
import json
import platform
import shutil
import subprocess
import sys


def command_version(command, args):
    path = shutil.which(command)
    if not path:
        return {"available": False}
    result = subprocess.run([path, *args], text=True, capture_output=True)
    text = (result.stdout or result.stderr).strip().splitlines()
    return {"available": True, "path": path, "version": text[0] if text else "unknown"}


report = {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "tools": {
        "nvcc": command_version("nvcc", ["--version"]),
        "nvidia_smi": command_version("nvidia-smi", ["--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        "nsys": command_version("nsys", ["--version"]),
        "ncu": command_version("ncu", ["--version"]),
        "vllm": command_version("vllm", ["--version"]),
    },
}
if importlib.util.find_spec("torch"):
    import torch
    report["torch"] = {
        "version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpus": [
            {
                "index": i,
                "name": torch.cuda.get_device_name(i),
                "capability": list(torch.cuda.get_device_capability(i)),
                "memory_gib": round(torch.cuda.get_device_properties(i).total_memory / 2**30, 2),
            }
            for i in range(torch.cuda.device_count())
        ],
    }
else:
    report["torch"] = {"available": False}
print(json.dumps(report, indent=2, ensure_ascii=False))
