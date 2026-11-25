import json
import torch

if not torch.cuda.is_available():
    raise SystemExit("需要 NVIDIA CUDA GPU")

cc = torch.cuda.get_device_capability(0)
name = torch.cuda.get_device_name(0)
if not (cc == (8, 9) or cc[0] >= 9):
    raise SystemExit(f"{name}, CC {cc}: 无 FP8 Tensor Core，使用 BF16/FP16 回退")

import transformer_engine.pytorch as te
from transformer_engine.common import recipe

torch.manual_seed(7)
in_features = 768       # 维度可被 16 整除
out_features = 3072
tokens = 2048

layer = te.Linear(in_features, out_features, bias=True).cuda()
x = torch.randn(tokens, in_features, device="cuda")

if cc[0] >= 10:
    recipes = {
        "fp8_delayed_scaling": recipe.DelayedScaling(
            fp8_format=recipe.Format.HYBRID
        ),
        "nvfp4": recipe.NVFP4BlockScaling(),
    }
else:
    recipes = {
        "fp8_delayed_scaling": recipe.DelayedScaling(
            fp8_format=recipe.Format.HYBRID
        )
    }

with torch.no_grad():
    reference = layer(x).float()
    output = {"gpu": name, "cc": cc}
    for label, lowp_recipe in recipes.items():
        # 预热并让 recipe 状态建立起来
        for _ in range(5):
            with te.autocast(enabled=True, recipe=lowp_recipe):
                y = layer(x)
        torch.cuda.synchronize()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(20):
            with te.autocast(enabled=True, recipe=lowp_recipe):
                y = layer(x)
        end.record()
        end.synchronize()
        rel = (torch.linalg.vector_norm(y.float() - reference) /
               torch.linalg.vector_norm(reference)).item()
        output[label] = {
            "mean_ms": start.elapsed_time(end) / 20,
            "relative_l2_error": rel,
            "finite": bool(torch.isfinite(y).all()),
        }

print(json.dumps(output, ensure_ascii=False, indent=2))
