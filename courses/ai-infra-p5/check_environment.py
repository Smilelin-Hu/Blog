from __future__ import annotations

import importlib.util
import json
import platform

report = {"python": platform.python_version(), "torch_installed": importlib.util.find_spec("torch") is not None}
if report["torch_installed"]:
    import torch
    report.update({"torch": torch.__version__, "cuda_available": torch.cuda.is_available(), "cuda_device_count": torch.cuda.device_count()})
else:
    report.update({"cuda_available": False, "cuda_device_count": 0})
print(json.dumps(report, ensure_ascii=False, indent=2))
