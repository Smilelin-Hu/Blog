# 编译器栈与算子库：MLIR、TVM、XLA、CUTLASS 与 CuTe

20 的 torch.compile/Inductor 覆盖图编译层；本文往下补一层：IR 基础设施（MLIR）、自动调度（TVM）、整图编译（XLA）、模板算子库（CUTLASS/CuTe）。分工一句话：编译器解决「自动生成与融合」，算子库解决「手写级性能天花板」，生产系统两者混用。

## 1. 分层全景

| 层 | 代表 | 输入 → 输出 | 性能来源 |
|---|---|---|---|
| 图编译 | XLA、Inductor | 计算图 → 融合 kernel | fusion、内存规划 |
| 自动调度 | TVM/Ansor、MetaSchedule | 算子描述 → schedule | 搜索空间 + 成本模型 |
| IR 基础设施 | MLIR | 多层 dialect → LLVM/硬件 | 渐进 lowering、语义保留 |
| 模板算子库 | CUTLASS | tile 配置 → GEMM/attention | mainloop/epilogue 组装 |
| 布局代数 | CuTe | shape×stride → 硬件映射 | TMA/线程-值映射统一抽象 |

Triton 居于编译器与算子库之间：block 级编程模型，shared memory 与 pipelining 交给编译器；LLM kernel 生态的主战场在 Triton 与 CUTLASS 两端。

## 2. MLIR：dialect 基础设施

多级 dialect（tensor/linalg/affine/gpu/nvgpu）渐进 lowering：tensor 语义与硬件层级需要中间表示，直接落 LLVM IR 会丢掉融合与布局信息。生态位：IREE 运行时、Triton 的 MLIR 后端、XLA 的 HLO→LHLO；2026 年 CUTLASS 也推出 compiler stack——CuTe IR dialect 建模布局代数并带 lowering pass（Cutegen），手写级抽象开始进入编译管线。工程价值：自定义算子以 dialect 接入统一管线，而不是黑盒 call 打断融合。

## 3. TVM 与自动调度

Relax/Relay IR + Ansor/MetaSchedule：搜索空间 + 成本模型 + 进化搜索。强项是跨硬件（CPU/ARM/GPU/NPU）自动调优，弱项是搜索时间复杂 kernel 的上限。LLM 场景 shape 多变，auto-schedule 容易过拟合单一 shape，换 shape 性能悬崖——这是生态向 Triton/CUTLASS 迁移的原因之一。

## 4. XLA 与整图编译

HLO fusion、内存规划、SPMD partitioner（GSPMD），TPU 原生；GPU 后端经 LHLO→LLVM，dot 落 cuBLAS/CUTLASS。与 Inductor 的对照：XLA 整图 ahead-of-time、JAX 生态；Inductor 容忍 graph break、PyTorch 动态图生态。fusion 规则决定 elementwise/reduce 的合并边界，是性能差异的第一来源。

## 5. CUTLASS 与 CuTe：性能天花板

- **CUTLASS 3.x/4.x**：mainloop（TMA、warp-specialized、ping-pong/cooperative）+ epilogue（EVT 融合树）组装；collective builder 按架构自动选 tile/cluster/stage。2026 版本进一步给出可复用 mainloop 与 TMA epilogue helper、Python Epilogue Fusion Configuration。
- **CuTe**：layout 代数（shape×stride）统一描述 thread/value/tile 映射，TMA descriptor 自动生成；CuTe DSL 把这套抽象 Python 化，手写级性能不再绑定 C++ 模板。
- **attention kernel 库**：FlashAttention-3 一类实现基于 CUTLASS/CuTe；「优先复用成熟库」（07/13/14 的提名）的底气在于 mainloop/epilogue 的工程量远超业务团队自研预算。

## 6. 选型与验收

| 需求 | 选择 | 理由 |
|---|---|---|
| 跨硬件自动调优 | TVM | 搜索空间覆盖广 |
| TPU/JAX 整图 | XLA | 原生 partitioner |
| PyTorch 动态图 | Inductor/Triton | graph break 容忍 |
| 极致 GEMM/attention | CUTLASS/CuTe | 天花板最高 |
| 自定义 IR/算子接入 | MLIR | 语义保留、渐进 lowering |

- 验收：与 cuBLAS/FlashAttention 基线单变量对比，看 achieved TFLOPS 与带宽利用率；compiler 产出 kernel 先过数值正确性门禁再谈性能。
- 常见坑：auto-schedule 过拟合 shape；fusion 改变数值复现性；CUTLASS 跨代 API 漂移带来的维护成本。

## 写在最后

下一篇：[GPU 能耗、功耗墙与数据中心效率](/source/AI-Infra/2-AI系统性能工程/39-GPU能耗-功耗墙与数据中心效率)。