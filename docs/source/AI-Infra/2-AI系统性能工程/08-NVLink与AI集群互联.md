# NVLink、NVSwitch 与 AI 集群互联

本篇解析 NVLink、NVSwitch 与多机网络的互联路径，建立大规模 AI 集群通信性能的整体认识。

单卡性能回答「一个 GPU 能算多快」，互联性能回答「很多 GPU 能否像一个系统那样工作」。当模型、参数、梯度、激活或 KV Cache 必须跨设备移动时，瓶颈往往从 Tensor Core 转移到 PCIe、NVLink、NVSwitch、NUMA 和节点网络。

重点不是背诵某代 NVLink 的峰值，而是学会回答四个工程问题：数据要经过哪条路径、每步移动多少字节、路径的有效带宽与固定延迟是多少、通信能否与计算重叠。

## 1. 内容概览

- PCIe、NVLink、NVSwitch、NVLink-C2C 与 InfiniBand/RoCE 的角色分工。
- `nvidia-smi topo -m` 的 `PIX/PXB/PHB/NODE/SYS/NV#` 怎么读。
- 延迟—带宽模型、Ring AllReduce、分层 AllReduce 的估算。
- CUDA P2P 可访问、实际传输路径、NVLink 连接三者的区别。
- 拓扑感知的 Rank 映射：DP / TP / PP / EP 各自的敏感点。

## 2. 本篇要点

1. 区分 PCIe、NVLink、NVSwitch、NVLink-C2C 与 InfiniBand/RoCE 的角色。
2. 正确解读 `nvidia-smi topo -m` 的拓扑标记。
3. 用延迟—带宽模型估算 P2P、Ring AllReduce 和分层 AllReduce 时间。
4. 区分 CUDA P2P 可访问、实际传输路径与 NVLink 连接。
5. 用 PyTorch 与 `nccl-tests` 测量 GPU 间有效带宽、延迟与正确性。
6. 识别 NUMA、PCIe Root Complex、ACS/IOMMU、主机中转和网络超售造成的瓶颈。

## 3. 核心直觉：多 GPU 性能由最窄的数据通道决定

把 AI 集群想成城市交通系统：Tensor Core 是工厂产能；HBM/GDDR 是厂内传送带；NVLink 是 GPU 之间的高速专线；NVSwitch 是连接多条高速专线的交换枢纽；PCIe 是兼容范围广的通用道路；InfiniBand/RoCE/Ethernet 是跨主机、跨机架网络。

增加 GPU 数量相当于增加工厂。若原料与半成品仍要经过一座窄桥，总产出不会线性增加。所以多 GPU 优化的第一原则是：**先找最窄的那条通道，再谈它值不值得加宽。**

## 4. 互联架构原理

### 4.1 PCIe：通用 I/O 骨干

PCIe 连接 GPU、CPU、NIC、NVMe 与 PCIe Switch。两块 GPU 即使都标为 PCIe x16，它们之间的路径也可能不同：

```text
较短路径：GPU 0 ─ PCIe Switch ─ GPU 1

较长路径：GPU 0 ─ Root Complex ─ CPU/NUMA Interconnect
                                  └─ Root Complex ─ GPU 1
```

路径越长，通常固定延迟越高，且更容易与网卡、存储或其他 GPU 争用共享上行链路。PCIe 标称带宽是链路能力，不等于 P2P Payload 带宽；编码、协议、事务大小、方向、拓扑和软件路径都会造成差异。

### 4.2 CUDA P2P 不等于 NVLink

需要区分三件事：

1. **Peer Access 能力**：一个 GPU 是否可以访问另一个 GPU 的显存地址。
2. **传输路径**：数据经过 NVLink、PCIe P2P，还是回退到主机内存中转。
3. **有效性能**：给定消息大小和方向下的实际 GB/s 与微秒延迟。

`torch.cuda.can_device_access_peer(0, 1)` 返回 `True`，只说明 CUDA P2P 能力可用，不证明存在 NVLink。反过来，硬件有 NVLink 也不保证软件、驱动、容器权限和拓扑配置都正确。

### 4.3 NVLink：GPU 间的高速 Scale-Up 链路

NVLink 是 NVIDIA 的高速互联，常用于 GPU-GPU；也存在 Grace CPU 与 GPU 间的 NVLink-C2C。二者不能简单当成同一种「显卡桥」：

- 离散 GPU NVLink 关注 GPU 间高带宽传输。
- NVLink-C2C 是封装/模块级 CPU-GPU 芯粒互联，具有不同的一致性与系统语义。
- 支持与带宽取决于 GPU SKU、板卡形态和整机设计。

NVLink 也不自动把多块 GPU 变成对任意程序透明的统一共享内存；应用仍需使用 CUDA、NCCL、NVSHMEM、框架通信算子或支持 Fabric 的内存机制。

### 4.4 NVSwitch：构建多 GPU NVLink 域

点对点 NVLink 桥适合少量 GPU。NVSwitch 作为专用交换芯片，把更多 GPU 组织成高带宽 NVLink Fabric：

```text
GPU 0 ─┐
GPU 1 ─┤
GPU 2 ─┼─ NVSwitch Fabric ─ 任意目标 GPU
 ...   │
GPU N ─┘
```

NVSwitch 提高连接度、双向带宽和可预测性，并支持整机级拓扑设计。它不能消除：Collective 的必要数据量；Kernel 启动和协议延迟；热点、路由和并发流量争用；跨 NVLink 域后的 InfiniBand/RoCE 瓶颈；Rank 放置、消息切分和同步不当。

### 4.5 Scale-Up 与 Scale-Out

```text
GPU ─ HBM/GDDR
 └─ PCIe/NVLink ─ 单节点或单 NVLink 域（Scale-Up）
      └─ NIC + InfiniBand/RoCE/Ethernet ─ 多节点（Scale-Out）
```

Scale-Up 让少量或数十块 GPU 低延迟协同；Scale-Out 让系统扩展到更多节点。跨层级 Collective 通常需要分层算法，不能把所有 Rank 当作同质全互联。

![互联层次：多 GPU 性能由最窄的数据通道决定](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l08_01.png)

## 5. 产品能力矩阵：必须按 SKU 与整机判断

| 架构 | 示例产品 | 互联定位 | 实验结论 |
| --- | --- | --- | --- |
| Ampere | RTX 3080 | PCIe，无 NVLink | 双卡做 PCIe/P2P 基线 |
| Ampere | RTX 3090/3090 Ti | 可选两卡 NVLink Bridge | 必须安装桥并由拓扑确认 |
| Ampere | A100 | PCIe/SXM；部分系统有桥或 NVSwitch | 按 PCIe、SXM、HGX 形态区分 |
| Ada Lovelace | RTX 4090 | PCIe，无 NVLink | 既不是 Blackwell，也不假设专用互联 |
| Ada Lovelace | L40/L40S | PCIe，无 NVLink | 适合 PCIe 与网络基线 |
| Hopper | H100/H200 | PCIe、SXM、NVL/HGX 等形态 | NVLink 4 能力取决于形态与系统 |
| Blackwell | RTX 5090 | PCIe Gen5，无 NVLink | 消费级 Blackwell 不等于 NVLink 5 |
| Blackwell | B100/B200/GB200 | NVLink 5；NVL/HGX 系统可含 NVSwitch | 数据中心专项实验 |

官方规格中，H100 SXM 的 NVLink 总带宽标为 900 GB/s，H100 NVL 标 600 GB/s；GB200 NVL72 的 72-GPU NVLink 域标为 130 TB/s 聚合通信带宽、单 GPU NVLink 5 为 1.8 TB/s 量级。这些是特定产品配置的双向或聚合规格，不应与一次单向 P2P Copy 的有效带宽直接比较。

对双 RTX 3080 20GB 环境，正确预期是：两卡通过 PCIe 路径通信，没有可安装的 NVLink Bridge；是否支持直接 P2P、走 `PIX/PXB/PHB/SYS` 中哪条路径，必须由实际主板、CPU、BIOS、驱动与 `nvidia-smi topo -m` 决定。

## 6. 拓扑识别

### 6.1 `nvidia-smi topo -m` 图例

| 标记 | 含义 | 性能直觉 |
| --- | --- | --- |
| `X` | 当前设备自身 | 非通信路径 |
| `NV#` | 经过由 # 条 NVLink 组成的连接 | 常见高速 GPU P2P |
| `PIX` | 至多经过一个 PCIe Bridge/Switch | PCIe 中较短路径 |
| `PXB` | 经过多个 PCIe Bridge，不经过 Host Bridge | 路径更长、可能共享上行 |
| `PHB` | 经过 PCIe Host Bridge / CPU Root Complex | 常见跨 Root 路径 |
| `NODE` | 同 NUMA Node 内跨 PCIe Host Bridge | 比简单 PIX/PXB 更复杂 |
| `SYS` | 还经过 NUMA 节点间 CPU 互联 | 单机中最需警惕的路径 |

常用检查命令：

```bash
nvidia-smi --query-gpu=index,name,compute_cap,pci.bus_id,memory.total --format=csv
nvidia-smi topo -m
nvidia-smi topo -mp
nvidia-smi nvlink --status
lspci -tv
numactl -H
```

部分驱动版本使用 `nvidia-smi nvlink -s`；不支持 NVLink 的产品会报告无活动链路或不支持。`topo -mp` 排除 NVLink、只展示 PCI 路径，适合确认 Fabric 下方的回退路径。

### 6.2 拓扑检查五问

1. GPU 对之间是 `NV#`、`PIX`、`PXB`、`PHB` 还是 `SYS`？
2. GPU 与目标 NIC 是否处于同一 NUMA/PCIe 局部域？
3. P2P 能力矩阵是否对称且实际可用？
4. 链路宽度、代际和速率是否降级？
5. 容器、虚拟机、IOMMU/ACS 是否改变了直通或 P2P 路径？

## 7. 关键性能模型

### 7.1 延迟—带宽模型

$$
T_{msg} = \alpha + \frac{S}{B_{eff}}
$$

$\alpha$ 是软件、协议、调度与链路的固定延迟；$B_{eff}$ 是该消息大小与方向下的有效带宽；$S$ 是实际 Payload 字节数。小消息由 $\alpha$ 主导，大消息由 $S/B_{eff}$ 主导。用 1 GiB Copy 测出的 GB/s 不能回答 4 KiB 控制消息的延迟。

### 7.2 Ring AllReduce

Ring AllReduce 可分解为 ReduceScatter 与 AllGather。若有 $N$ 个 Rank、每 Rank 逻辑消息大小 $S$，理想 Ring 中每 Rank 通信量为

$$
V_{ring} = 2\frac{N-1}{N}S, \qquad
T_{ring} \approx 2(N-1)\alpha + 2\frac{N-1}{N}\frac{S}{B_{eff}}
$$

Ring 对大消息带宽效率高，但步数随 $N$ 增长；树或递归倍增算法对小消息通常更有延迟优势，实际 NCCL 会结合消息大小、拓扑、协议和版本选算法。

### 7.3 `algbw` 与 `busbw`

`nccl-tests` 的 `algbw` 表示算法观察到的 Payload 吞吐。为便于跨 Collective 比较，AllReduce 的近似总线带宽归一化为

$$
\mathrm{busbw} = \mathrm{algbw} \times 2\frac{N-1}{N}
$$

不要把 `busbw` 当成某条物理链路的单向实测，也不要直接与厂商「全双工聚合带宽」数字比较。

### 7.4 通信占比与扩展效率

若单卡计算时间 $T_c$、多卡通信时间 $T_{comm}$、可重叠部分 $T_{overlap}$：

$$
T_{step} \approx T_c + T_{comm} - T_{overlap}, \qquad
\eta \approx \frac{T_c}{T_{step}}
$$

互联优化不只是增大带宽；增大 Bucket、减少同步、计算通信重叠、调整并行策略都在改变这个分母。

### 7.5 分层 AllReduce

设每节点 $G$ 块 GPU、共 $M$ 个节点，常见思路是：节点内用 NVLink/NVSwitch 或本地 PCIe 归约；节点间只让代表流或分片通过 NIC；节点内再广播/AllGather。简化模型：

$$
T_{hier} \approx T_{intra-reduce} + T_{inter-allreduce} + T_{intra-broadcast}
$$

真实实现可能使用多 Rail、多 Channel、ReduceScatter/AllGather 和并发流，模型用于定位层级瓶颈，不替代基准测试。

## 8. Collective 与工作负载的关系

| 并行方式 | 典型通信 | 对互联的敏感点 |
| --- | --- | --- |
| DDP | 梯度 AllReduce | 大消息带宽、计算通信重叠 |
| FSDP/ZeRO | 参数 AllGather、梯度 ReduceScatter | Bucket、预取、峰值带宽与显存 |
| Tensor Parallel | 每层 AllReduce/AllGather | 极度依赖低延迟 Scale-Up |
| Pipeline Parallel | Stage 间激活 P2P | 相邻 Rank 映射、Microbatch Bubble |
| Context/Sequence Parallel | Attention 分片通信 | 消息规模与序列长度 |
| MoE Expert Parallel | AllToAll | 路由不均衡、双向带宽、尾延迟 |
| 解耦推理 | KV Cache 迁移 | 点对点大对象、网络与内存带宽 |

拓扑映射原则：通信最密集的 Rank 优先放在最快、最稳定的局部域中——TP 组优先留在同一 NVSwitch 域；DP 更适合跨节点，因为梯度通信更容易做大 Bucket 和重叠。这是经验起点，不是固定规则。

## 9. 瓶颈分析方法

### 9.1 确认问题确实是通信

观察：GPU Kernel 之间是否有长时间 NCCL/P2P 区间；Step Time 是否随 Rank 数快速恶化；通信时间是否随消息大小近似线性增长；GPU 利用率下降时 NIC/NVLink/PCIe 是否繁忙；是否存在某个 Rank 明显更慢造成全局等待。

### 9.2 把通信拆成四层

```text
应用：并行策略、Bucket、同步频率、负载均衡
Collective：Ring/Tree、Channel、Protocol、Rank Mapping
传输：P2P、SHM、NET、GPUDirect RDMA、主机中转
硬件：NVLink/NVSwitch、PCIe、NUMA、NIC、交换网络
```

只调 NCCL 环境变量而不确认上层消息模式，通常无法解决根因。

### 9.3 做消息大小扫描

至少测三个区间：小消息（暴露启动与同步延迟）、中消息（暴露算法切换与分块效果）、大消息（逼近持续带宽与共享链路上限）。必须保留 Size、Latency、`algbw`、`busbw`、错误数、拓扑、版本和 GPU 时钟/功耗状态。

### 9.4 做 A/B 隔离

单 GPU 与多 GPU；同 NUMA 与跨 NUMA；相邻 GPU 对与最远 GPU 对；P2P 与显式 Host-Staged；单进程与多进程；节点内与节点间；默认 NCCL 与仅用于诊断的传输禁用选项。禁用某条路径只能用于定位，不能把「绕开硬件」当作生产优化。

## 10. 完整可运行实验：模型、拓扑与双 GPU Copy

脚本分两级：Level 0 纯 Python 跑通信模型；Level 1 若安装 PyTorch，自动检测 GPU、CC、P2P 与拓扑，并测试双卡 Copy。

```python
#!/usr/bin/env python3
"""通用 GPU 互联实验：Level 0 模型 + Level 1 可选 PyTorch 实测。"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass


@dataclass
class Link:
    name: str
    bandwidth_gbs: float
    latency_us: float


def transfer_ms(size_mib, link, steps=1, volume_factor=1.0):
    size_bytes = size_mib * 1024**2 * volume_factor
    return steps * link.latency_us / 1000.0 + size_bytes / (link.bandwidth_gbs * 1e9) * 1000.0


def ring_allreduce_ms(size_mib, ranks, link):
    if ranks < 2:
        return 0.0
    steps = 2 * (ranks - 1)
    volume = 2 * (ranks - 1) / ranks
    return steps * link.latency_us / 1000.0 + transfer_ms(size_mib, link, steps=0, volume_factor=volume)


def recursive_doubling_ms(size_mib, ranks, link):
    if ranks < 2:
        return 0.0
    steps = math.ceil(math.log2(ranks))
    return transfer_ms(size_mib, link, steps=steps, volume_factor=steps)


def hierarchical_ms(size_mib, gpus_per_node, nodes, intra, inter):
    if nodes < 2:
        return ring_allreduce_ms(size_mib, gpus_per_node, intra)
    local_steps = math.ceil(math.log2(max(gpus_per_node, 1)))
    local_reduce = transfer_ms(size_mib, intra, local_steps, local_steps)
    inter_reduce = ring_allreduce_ms(size_mib, nodes, inter)
    local_broadcast = transfer_ms(size_mib, intra, local_steps, local_steps)
    return local_reduce + inter_reduce + local_broadcast


def run_level0(args):
    intra = Link("intra", args.intra_gbs, args.intra_latency_us)
    inter = Link("inter", args.inter_gbs, args.inter_latency_us)
    rows = []
    for size in args.sizes_mib:
        for algorithm, comm_ms in (
            ("ring", ring_allreduce_ms(size, args.ranks, intra)),
            ("recursive_doubling_teaching_model",
             recursive_doubling_ms(size, args.ranks, intra)),
            ("hierarchical_teaching_model",
             hierarchical_ms(size, args.gpus_per_node, args.nodes, intra, inter)),
        ):
            efficiency = args.compute_ms / (args.compute_ms + comm_ms)
            rows.append({
                "size_mib": size,
                "algorithm": algorithm,
                "comm_ms": round(comm_ms, 4),
                "compute_ms": args.compute_ms,
                "efficiency_without_overlap": round(efficiency, 4),
            })
    return {
        "warning": "All bandwidth/latency inputs are user assumptions, not measured hardware specs.",
        "intra_link": asdict(intra),
        "inter_link": asdict(inter),
        "ranks": args.ranks,
        "results": rows,
    }


def command_output(argv):
    if not shutil.which(argv[0]):
        return f"{argv[0]} not found"
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
    text = (result.stdout or result.stderr).strip()
    return text if text else f"exit_code={result.returncode}"


def benchmark_cross_device_copy(torch, src_device, dst_device, size_mib, warmup, repeat):
    elements = size_mib * 1024**2 // 4
    with torch.cuda.device(src_device):
        src = torch.arange(elements, dtype=torch.float32, device=src_device)
    with torch.cuda.device(dst_device):
        dst = torch.empty(elements, dtype=torch.float32, device=dst_device)

    for _ in range(warmup):
        dst.copy_(src, non_blocking=True)
    torch.cuda.synchronize(src_device)
    torch.cuda.synchronize(dst_device)

    start = time.perf_counter()
    for _ in range(repeat):
        dst.copy_(src, non_blocking=True)
    torch.cuda.synchronize(src_device)
    torch.cuda.synchronize(dst_device)
    elapsed_s = (time.perf_counter() - start) / repeat

    idx = torch.tensor([0, elements // 2, elements - 1], device=dst_device)
    got = dst[idx].cpu()
    expected = torch.tensor([0, elements // 2, elements - 1], dtype=torch.float32)
    return {
        "size_mib": size_mib,
        "latency_ms": round(elapsed_s * 1000, 4),
        "effective_gib_s": round((size_mib / 1024.0) / elapsed_s, 3),
        "sample_correct": bool(torch.equal(got, expected)),
        "label": "cross-device copy; interpret with topology/P2P data",
    }


def benchmark_host_staged(torch, src_device, dst_device, size_mib, warmup, repeat):
    elements = size_mib * 1024**2 // 4
    with torch.cuda.device(src_device):
        src = torch.ones(elements, dtype=torch.float32, device=src_device)
    host = torch.empty(elements, dtype=torch.float32, pin_memory=True)
    with torch.cuda.device(dst_device):
        dst = torch.empty(elements, dtype=torch.float32, device=dst_device)

    def one_copy():
        host.copy_(src, non_blocking=True)
        torch.cuda.synchronize(src_device)
        dst.copy_(host, non_blocking=True)
        torch.cuda.synchronize(dst_device)

    for _ in range(warmup):
        one_copy()
    start = time.perf_counter()
    for _ in range(repeat):
        one_copy()
    elapsed_s = (time.perf_counter() - start) / repeat
    return {
        "size_mib": size_mib,
        "latency_ms": round(elapsed_s * 1000, 4),
        "effective_payload_gib_s": round((size_mib / 1024.0) / elapsed_s, 3),
        "sample_correct": float(dst[0].item()) == 1.0 and float(dst[-1].item()) == 1.0,
        "label": "explicit GPU->pinned-host->GPU baseline; two transfer legs",
    }


def run_level1(args):
    try:
        import torch
    except ImportError:
        return {"skipped": "PyTorch not installed; Level 0 remains fully usable."}

    result = {
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "topology": command_output(["nvidia-smi", "topo", "-m"]),
        "nvlink_status": command_output(["nvidia-smi", "nvlink", "--status"]),
    }
    if not torch.cuda.is_available():
        result["skipped"] = "CUDA unavailable."
        return result

    count = torch.cuda.device_count()
    result["gpus"] = [
        {
            "index": i,
            "name": torch.cuda.get_device_name(i),
            "compute_capability": list(torch.cuda.get_device_capability(i)),
            "memory_gib": round(torch.cuda.get_device_properties(i).total_memory / 1024**3, 2),
        }
        for i in range(count)
    ]
    result["peer_access_matrix"] = [
        [True if i == j else bool(torch.cuda.can_device_access_peer(i, j)) for j in range(count)]
        for i in range(count)
    ]
    if count < 2:
        result["skipped"] = "Need at least two visible CUDA GPUs for copy benchmark."
        return result

    result["copy_0_to_1"] = []
    result["host_staged_0_to_1"] = []
    for size in args.gpu_sizes_mib:
        try:
            result["copy_0_to_1"].append(
                benchmark_cross_device_copy(torch, 0, 1, size, args.warmup, args.repeat))
            result["host_staged_0_to_1"].append(
                benchmark_host_staged(torch, 0, 1, size, args.warmup, args.repeat))
        except RuntimeError as exc:
            result.setdefault("errors", []).append({"size_mib": size, "error": str(exc)})
            break
    return result


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--level", choices=("0", "1", "all"), default="all")
    p.add_argument("--sizes-mib", type=float, nargs="+", default=[0.004, 1, 64, 1024])
    p.add_argument("--ranks", type=int, default=8)
    p.add_argument("--gpus-per-node", type=int, default=4)
    p.add_argument("--nodes", type=int, default=2)
    p.add_argument("--intra-gbs", type=float, default=25.0)
    p.add_argument("--intra-latency-us", type=float, default=8.0)
    p.add_argument("--inter-gbs", type=float, default=12.5)
    p.add_argument("--inter-latency-us", type=float, default=20.0)
    p.add_argument("--compute-ms", type=float, default=50.0)
    p.add_argument("--gpu-sizes-mib", type=int, nargs="+", default=[4, 64, 256])
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--repeat", type=int, default=20)
    return p.parse_args()


def main():
    args = parse_args()
    output = {}
    if args.level in ("0", "all"):
        output["level0"] = run_level0(args)
    if args.level in ("1", "all"):
        output["level1"] = run_level1(args)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

### 10.1 运行与预期现象

```bash
python interconnect_lab.py --level 0
python interconnect_lab.py --level 0 \
  --ranks 8 --gpus-per-node 4 --nodes 2 \
  --intra-gbs 25 --intra-latency-us 8 \
  --inter-gbs 12.5 --inter-latency-us 20 \
  --compute-ms 50
python interconnect_lab.py --level 1 --gpu-sizes-mib 4 64 256
```

默认带宽、延迟只是教学输入，不代表 RTX 3080、PCIe、NVLink 或网络的官方性能；正确做法是把实测结果回填为参数。

预期现象：几 KiB 小消息中低步数模型常更有优势；消息增大后带宽项主导，Ring 的通信量优势更明显；降低 `inter-gbs` 会让分层模型迅速受节点间网络限制；`comm_ms` 增大时 `efficiency_without_overlap` 下降；增大 `compute-ms` 会提高表面效率，但不代表通信本身变快。

### 10.2 双 RTX 3080 20GB 的预期

- 拓扑不会显示 `NV#`；
- 可能显示 `PIX/PXB/PHB/SYS`，取决于主板和 CPU；
- P2P 可能可用，也可能因平台、IOMMU/ACS 或虚拟化限制不可用；
- Cross-Device Copy 通常优于显式 Host-Staged，但不是所有平台的必然结论；
- 256 MiB 测试约为每卡额外占用数百 MiB，20GB 显存足够；若系统已有负载，可改为 `4 32 128`。

### 10.3 计时边界

计时必须包含同步点，否则会把「异步提交」误当成「传输完成」；但同步点本身也会引入开销。公平比较要么两侧都同步，要么都用事件计时。真实系统的并发 Channel、协议、缓存、拓扑路由、GPU Clock 与主机噪声都会让实测偏离教学模型，模型只用于判断「哪个变量最敏感」。

## 写在最后

互联优化的结论永远是「具体集群 + 具体拓扑 + 具体消息模式」的产物。下一篇把视角从裸机挪到运行环境：Linux、Docker、Kubernetes 这三层如何悄悄吃掉性能。

下一篇：[Linux、Docker、Kubernetes GPU 性能优化](/source/AI-Infra/2-AI系统性能工程/09-LinuxDocker与KubernetesGPU性能优化)。
