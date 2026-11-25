# 项目四：Multi-Tenant, Multi-Model and Multi-LoRA Serving

多租户 serving 的公平性靠加权公平调度 + Token 配额 + 驻留淘汰共同保证。项目级验收：至少两租户/两模型/两 adapter、每个被接受预留最终结算、每个 LoRA 请求显式带 adapter、公平调度器真实被 exercising（而非退化为 FIFO）。配额不结算或 adapter 隐式默认，都会让多租户隔离形同虚设。

## 1. 项目闭环

```bash
python project/04-multitenant-lora/run.py --check-only
python project/04-multitenant-lora/run.py --output results/project-04-fixture.json
python project/04-multitenant-lora/run.py --real --endpoint http://mt:8000 --tenants t1,t2 --adapters a1,a2 \
  --output results/gpu_result.json
```

- **输入**：多租户端点、租户/模型/adapter 集、加权请求流。
- **输出**：公平调度记录、配额结算记录、adapter 选路 trace、驻留淘汰记录。
- **验收**：≥2 租户/模型/adapter；每接受预留结算；LoRA 请求显式 adapter；公平调度被 exercising。

## 2. 判读纪律

- 公平性要附逐租户份额时序：只报「配置了加权」不算公平生效。
- 淘汰记录与淘汰后首请求延迟对齐：淘汰代价要可见。
- 只有 `source=measured` 的报告可用于性能或发布结论。

## 3. 关联

课次基础见本册 [18-LoRA-Adapter](/source/推理优化课程册/18-LoRA-Adapter：多模型ID交替与切换延迟)、[19-Multi-Model-Pool](/source/推理优化课程册/19-Multi-Model-Pool：热门突发与冷模型穿插)；主题展开见 [Multi-Tenant, Multi-Model 与 Multi-LoRA Serving](/source/AI-Infra/3-大模型推理优化工程/34-Multi-Tenant-Multi-Model与Multi-LoRAServing)。