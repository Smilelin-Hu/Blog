# Linux、Docker、Kubernetes GPU 性能优化

本篇从 Linux、容器与 Kubernetes 全链路定位 GPU 之外的系统瓶颈，让训练和推理环境稳定高效。

GPU 利用率低，不一定是 GPU Kernel 慢。数据可能卡在磁盘、CPU 解码、NUMA 远端内存、Pinned Memory、容器共享内存、CPU CFS 配额或 Kubernetes 错误调度上。此时继续优化 CUDA Kernel，往往等于给堵车中的跑车换发动机。

方法上不提供「复制粘贴永久修改所有 sysctl」的激进脚本，而是可复现的工程方法：**先采集基线，再只改一个变量，记录回滚方法，最后用端到端 Goodput 验证。**

## 1. 内容概览

- Linux 调度、NUMA、Page Cache、Swap、THP、Pinned Memory 如何影响 GPU。
- NVIDIA Driver、CUDA Driver API、CUDA Runtime、Toolkit 与容器内用户态库的分层。
- NVIDIA Container Toolkit 的正确配置与验证。
- cgroup v2 指标定位 CPU Throttling、Memory Pressure 与 OOM。
- Docker 的 CPU / Memory / `/dev/shm` / IPC / NUMA 配置影响。
- Kubernetes GPU Resource、QoS、CPU Manager 与 Topology Manager。
- 整卡、Time-Slicing、MPS 与 MIG 的共享和隔离语义。

## 2. 核心直觉：GPU 是流水线末端的消费者

![ai2-09-L21](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l09_01.png)

系统吞吐受最慢阶段限制：

$$
R_{pipeline} \le \min\left(R_{storage}, R_{decode}, R_{collate}, R_{H2D}, R_{GPU}\right)
$$

若 GPU 每个 Batch 计算 40 ms、数据准备却要 55 ms，那么 GPU 再快 50% 也不会让端到端吞吐提高 50%。真正要优化的是 55 ms 的上游阶段，或者用预取把它与 GPU 计算重叠。

## 3. 从主机到容器的 GPU 软件栈

```text
应用：PyTorch / JAX / TensorFlow / vLLM
用户态库：CUDA Runtime、cuBLAS、cuDNN、NCCL
容器接口：NVIDIA Container Toolkit / CDI / Runtime Hook
主机内核态：NVIDIA Kernel Driver
硬件：GPU、PCIe/NVLink、NUMA、NIC、Storage
```

关键规则：

- NVIDIA 内核驱动由主机安装并与主机 Kernel 匹配。
- 容器镜像通常携带应用所需的 CUDA 用户态 Runtime 和库。
- NVIDIA Container Toolkit 把设备和兼容的驱动能力暴露给容器。
- 容器内的 CUDA Toolkit 版本不应超过主机驱动可支持范围。
- `nvidia-smi` 显示的 CUDA Version 是驱动最高兼容能力，不等于当前 Python Wheel 编译所用版本。
- `nvcc --version` 只说明本地 Toolkit 编译器，不证明 PyTorch 正在使用它。

排查时至少同时记录：

```bash
uname -a
nvidia-smi
nvcc --version || true
python -c 'import torch; print(torch.__version__, torch.version.cuda)'
```

## 4. Linux 性能原理

### 4.1 CPU 调度与 GPU Bubble

GPU Launch、DataLoader、Tokenizer、NCCL Progress 和网络处理都需要 CPU。若线程被频繁迁移、被 CFS 配额 Throttle、与系统中断争抢，GPU Timeline 会出现空洞。一次 Step 可分解为

$$
T_{step} = T_{GPU} + T_{input,exposed} + T_{comm,exposed} + T_{runtime} + T_{sync}
$$

`exposed` 表示没有被并行隐藏的部分。CPU 优化的目标不是追求 100% CPU 利用率，而是降低关键路径上的等待和抖动。

```bash
mpstat -P ALL 1
pidstat -wt -p <PID> 1
vmstat 1
perf stat -p <PID> -e context-switches,cpu-migrations,page-faults
```

### 4.2 NUMA：CPU、内存、GPU 和 NIC 的距离

双路服务器中，CPU 访问本地 NUMA Memory 通常比远端更快、更稳定。GPU 也挂在特定 PCIe Root/NUMA Node 下。若 GPU 0 的 DataLoader 线程属于 NUMA 0，却从 NUMA 1 分配大块 Pinned Memory，H2D 路径会多一次跨 Socket 传输。

```bash
numactl -H
nvidia-smi topo -m
cat /sys/bus/pci/devices/0000:XX:YY.Z/numa_node
numastat -p <PID>
```

仅用于 A/B 的绑定示例：

```bash
numactl --cpunodebind=0 --membind=0 python train.py
```

不要假设 NUMA 0 一定连接 GPU 0；先看实际 PCI Bus ID 与拓扑。

### 4.3 CPU Affinity、Thread Pool 与 DataLoader

过少 CPU Worker 会饿死 GPU；过多 Worker 会造成：Context Switch 增多；Page Cache 和内存压力增加；多个 BLAS/OpenMP Thread Pool 过度订阅；每个 Worker 复制 Python 对象放大 Host RAM；容器 CPU Limit 内严重 Throttling。

先固定隐式线程数再扫描 Worker：

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
```

```python
loader = DataLoader(
    dataset,
    batch_size=batch_size,
    num_workers=workers,
    pin_memory=torch.cuda.is_available(),
    persistent_workers=workers > 0,
    prefetch_factor=2 if workers > 0 else None,
)
```

`pin_memory=True` 不是无条件越多越好：Pinned Page 不能被普通方式换出，占用过大会挤压系统内存，并受 `ulimit -l`、cgroup 与 OS 策略影响。

### 4.4 Swap 与内存压力

训练进程发生 Swap-in 会带来毫秒到秒级停顿。先观察再决定策略：

```bash
free -h
swapon --show
vmstat 1
cat /proc/pressure/memory
cat /proc/<PID>/status | rg 'VmRSS|VmSwap|VmLck'
```

`vm.swappiness=0` 并不是通用答案：它倾向避免匿名页换出，但不能解决容量不足，也不保证绝不 Swap。生产节点应结合 OOM 策略、Checkpoint、作业优先级与共享负载决定，改动时先记录原值以便回滚。

### 4.5 Page Cache、Readahead 与 Checkpoint

Page Cache 能显著加速重复读取，但首次读取、随机小文件和远程文件系统的行为不同。Checkpoint 写入会产生 Dirty Page Burst，可能与训练读数据、NCCL 网络或同盘日志争用。

```bash
iostat -xz 1
cat /proc/meminfo | rg 'Cached|Dirty|Writeback'
cat /proc/pressure/io
```

不要在共享生产机用 `drop_caches` 作为日常「优化」——它会破坏其他任务的缓存，只适合获得授权的隔离基准环境。

### 4.6 Transparent Huge Pages

THP 用更大页降低 CPU TLB 压力，也可能引入 Compaction、分配延迟与尾延迟变化。

```bash
cat /sys/kernel/mm/transparent_hugepage/enabled
cat /proc/meminfo | rg 'AnonHugePages|HugePages'
```

`always`、`madvise`、`never` 应以工作负载实测选择。GPU HBM Page、CUDA Unified Memory 与 Linux Host THP 是不同层次，不能混为一谈。

### 4.7 CPU Frequency、C-State 与 GPU Persistence

```bash
cpupower frequency-info
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
nvidia-smi --query-gpu=index,name,persistence_mode,pstate,clocks.sm,power.draw,temperature.gpu --format=csv
sudo nvidia-smi -pm 1
```

更高频率与更浅 C-State 可能降低抖动，也会增加功耗、温度和噪声；对长时间 GPU 训练，CPU 不是瓶颈时强制最高频只会降低性能/瓦特。Persistence Mode 主要减少作业之间的 Cold Start，不会直接提高 Kernel FLOPS；锁定 Application Clock、Power Limit 或 Exclusive Process Mode 影响多租户，必须由管理员操作并记录回滚值。

## 5. Docker 性能原理

### 5.1 容器不是虚拟 GPU

Linux 容器共享主机 Kernel，GPU Kernel 仍在真实设备执行。正确配置时，计算 Kernel 本身通常没有虚拟机式模拟开销。容器场景的性能问题更多来自：CPU Quota/Cpuset；Memory Limit、OOM 与 Swap；`/dev/shm` 太小；OverlayFS 小文件与写放大；容器网络；缺失 RDMA、IPC Lock、NUMA 或设备权限；镜像与 Host Driver/Runtime 不兼容。

### 5.2 CPU Quota 与 CFS Throttling

假设容器每周期允许 CPU 时间 $Q$、周期长度 $P$：

$$
\mathrm{CPU}_{quota} = \frac{Q}{P}
$$

达到 Quota 后，即使主机还有空闲 CPU，容器也可能等到下一周期。DataLoader 常表现为平均 CPU 不高，但 `nr_throttled` 与 `throttled_usec` 增长。

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

A/B 对比：

```bash
docker run --rm --cpus=4 ubuntu:24.04 nproc
docker run --rm --cpuset-cpus=0-3 --cpuset-mems=0 ubuntu:24.04 nproc
```

### 5.3 `/dev/shm` 与多进程 DataLoader

Docker 默认共享内存通常较小。PyTorch 多进程、NCCL SHM Transport、Python Multiprocessing 可能出现 `Bus error`、`No space left on device`（但磁盘还有空间）、Worker 意外退出、隐式回退或吞吐下降。

```bash
df -h /dev/shm
docker run --rm --shm-size=8g <image> <command>
```

`--ipc=host` 可共享主机 IPC Namespace，但扩大隔离边界，不应作为默认答案；优先显式设置 `--shm-size`，Kubernetes 用 Memory-backed `emptyDir`。

### 5.4 镜像与文件系统

- 数据集与 Checkpoint 使用显式 Volume，不写入容器可写层。
- 大量小文件先做 Shard/Tar/Parquet 布局优化。
- 多阶段构建减小镜像。
- 依赖版本锁定，镜像使用不可变 Digest。
- 编译缓存放持久 Volume 并按架构隔离。
- 镜像拉取时间与运行时吞吐分开统计。

### 5.5 NVIDIA Container Toolkit 验证

主机先有可用 NVIDIA Driver，再安装 Toolkit：

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
```

不要把主机的 `/usr/lib` 整目录手工挂入容器；Toolkit 会按设备请求与 Driver Capability 处理设备与库。Podman 等 Runtime 可用 CDI，是否采用取决于 Runtime 与 Toolkit 版本。

## 6. Kubernetes GPU 性能原理

### 6.1 GPU 是扩展资源

安装 NVIDIA Device Plugin 或 GPU Operator 后，节点通常暴露 `nvidia.com/gpu`。GPU Resource 只能按整数请求，不能请求 `500m`。标准 Pod 可只写 `limits`（会作为 Request）；若同时写 Request 与 Limit，两者必须相等。

```yaml
resources:
  requests:
    cpu: "4"
    memory: 16Gi
    nvidia.com/gpu: "1"
  limits:
    cpu: "4"
    memory: 16Gi
    nvidia.com/gpu: "1"
```

### 6.2 QoS 与 CPU 独占

要获得 `Guaranteed` QoS，Pod 内每个 Container 的 CPU/Memory Request 与 Limit 必须满足条件。结合 kubelet `CPU Manager static`，具有整数 CPU Request 的合格容器可获得独占 CPU Set，减少迁移与共享干扰。

```bash
kubectl get pod <pod> -o jsonpath='{.status.qosClass}{"\n"}'
kubectl exec <pod> -- cat /sys/fs/cgroup/cpuset.cpus.effective
kubectl exec <pod> -- cat /sys/fs/cgroup/cpu.stat
```

CPU Limit 过紧时，即使 Guaranteed Pod 也可能在突发预处理阶段 Throttle；优化目标是稳定供应而非盲目压缩 Request。

### 6.3 Topology Manager 的真实边界

Kubelet Topology Manager 协调 CPU Manager、Device Manager 等 Hint Provider，在**单节点**内尝试把 CPU、内存和设备对齐到合适 NUMA Node。策略包括 `none`（不对齐）、`best-effort`（尽量对齐，失败仍准入）、`restricted`（无可接受拓扑时拒绝）、`single-numa-node`（要求单 NUMA Node 首选对齐）。

它不是跨节点网络拓扑调度器，也不保证多 GPU Request 总能得到同一 NVLink Clique；机架、交换机、Rail、NVLink Domain 等信息仍需 Node Label、Affinity、DRA/专用调度扩展表达。

### 6.4 整卡、Time-Slicing、MPS 与 MIG

| 方式 | 共享方式 | 显存隔离 | 故障隔离 | 适合场景 |
| --- | --- | --- | --- | --- |
| 整卡 | 独占设备 | 强 | 较强 | 训练、稳定推理基线 |
| Time-Slicing | 时间复用 | 无 | 无，同一 Fault Domain | 低负载开发/轻推理 |
| CUDA MPS | 多进程并发与配额能力 | 有限/依配置 | 弱于 MIG | 小 Kernel、多进程吞吐 |
| MIG | 硬件分区 | 有 | 有 | 支持 MIG 的数据中心 GPU 多租户 |

Device Plugin 的 Time-Slicing Replica 不是「虚拟小 GPU」，也不提供显存或故障隔离——一个 Pod OOM/异常可能影响共享者。MPS 与 Time-Slicing 互斥；MIG 只在支持的 GPU 与配置上可用。消费卡 RTX 3080/3090、4090、5090 不支持 MIG；A100、H100/H200 及部分更新数据中心产品可按 SKU 配置。没有 MIG 硬件时不能用容器配额模拟等价隔离。

### 6.5 GPU Operator 的角色

GPU Operator 可管理 Driver、Container Toolkit、Device Plugin、GPU Feature Discovery、DCGM Exporter、MIG Manager 等组件。它减少生命周期管理工作，但不会自动解决：错误的 Pod CPU/Memory Request；数据集局部性；跨节点拓扑；用户代码中的同步与 DataLoader 问题；共享策略带来的干扰。

## 7. 瓶颈分析方法

### 7.1 四层漏斗

```text
业务：Tokens/s、Samples/s、P99、SLO、失败率
应用：Data Time、Compute Time、Communication Time、Queue Time
容器：CPU Throttle、Memory Event、/dev/shm、Block/Network I/O
节点：NUMA、Frequency、PSI、Storage、PCIe、GPU/NIC Topology
```

只有四层指标在同一时间轴上，才能避免「GPU Util 低所以加 GPU」这种结论。

### 7.2 诊断决策树

![GPU 利用率低：按 Timeline 与环境分层归因](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l09_02.png)

## 8. 只读审计脚本

诊断第一步永远是「只读采集」，不改配置：

```python
#!/usr/bin/env python3
"""只读系统审计：不修改 sysctl、CPU Governor、GPU Clock 或容器配置。"""

import json
import platform
import shutil
import subprocess
from pathlib import Path


def read_text(path, default="unavailable"):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, PermissionError):
        return default


def run(argv, timeout=10):
    if not shutil.which(argv[0]):
        return {"available": False, "command": argv, "output": "command not found"}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return {"available": True, "command": argv, "returncode": p.returncode,
                "output": (p.stdout or p.stderr).strip()}
    except subprocess.TimeoutExpired:
        return {"available": True, "command": argv, "timeout": True}


def parse_cpu_max(text):
    parts = text.split()
    if len(parts) != 2:
        return {"raw": text, "quota_cpus": None}
    quota, period = parts
    if quota == "max":
        return {"raw": text, "quota_cpus": "unlimited"}
    try:
        return {"raw": text, "quota_cpus": round(int(quota) / int(period), 3)}
    except (ValueError, ZeroDivisionError):
        return {"raw": text, "quota_cpus": None}


def audit():
    return {
        "host": {
            "uname": platform.uname()._asdict(),
            "cpu_count": len(__import__("os").sched_getaffinity(0)) if hasattr(__import__("os"), "sched_getaffinity") else None,
            "meminfo": read_text("/proc/meminfo"),
            "thp": read_text("/sys/kernel/mm/transparent_hugepage/enabled"),
            "pressure_memory": read_text("/proc/pressure/memory"),
            "pressure_io": read_text("/proc/pressure/io"),
        },
        "cgroup": {
            "cpu_max": parse_cpu_max(read_text("/sys/fs/cgroup/cpu.max")),
            "cpu_stat": read_text("/sys/fs/cgroup/cpu.stat"),
            "memory_current": read_text("/sys/fs/cgroup/memory.current"),
            "memory_events": read_text("/sys/fs/cgroup/memory.events"),
            "cpuset_effective": read_text("/sys/fs/cgroup/cpuset.cpus.effective"),
            "shm": run(["df", "-h", "/dev/shm"]),
        },
        "gpu": {
            "smi": run(["nvidia-smi"]),
            "topo": run(["nvidia-smi", "topo", "-m"]),
            "peer_and_cc": run(["nvidia-smi", "--query-gpu=index,name,compute_cap,memory.total,pstate",
                                "--format=csv,noheader"]),
        },
        "numa": run(["numactl", "-H"]),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2, default=str))
```

把这份 JSON 与业务指标（Tokens/s、P99）放在同一时间窗，就能判断瓶颈在主机、容器还是 GPU。Level 2 再做 Docker / Kubernetes 对照部署，一次只改一个变量。

## 写在最后

这一篇的核心不是「调更多参数」，而是把 GPU 之外的四层（主机、容器、编排、共享策略）纳入同一张证据网。下一篇进入 CUDA 编程模型，开始从代码层解释 Kernel 的行为。

下一篇：[CUDA 编程模型](/source/AI-Infra/2-AI系统性能工程/10-CUDA编程模型)。
