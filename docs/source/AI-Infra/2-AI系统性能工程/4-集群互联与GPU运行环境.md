# 集群互联与 GPU 运行环境

多卡性能由**最窄的那条数据通道**决定。机内看 NVLink，机上互联看 IB/RoCE，两者之间还有一层容易被忽视的东西：Linux、容器与 K8s 把 GPU 交到你手里时的实际状态。

## 1. 三类链路

### 1.1 PCIe：通用 I/O 骨干

PCIe 是所有设备的基础通路：GPU↔CPU、GPU↔NIC、GPU↔NVMe。它的优势是通用，劣势是带宽与拓扑不保证均等——跨 Root Complex、跨 NUMA 之后，同一次拷贝可能慢一个档次。

### 1.2 CUDA P2P 不等于 NVLink

P2P（peer-to-peer）是**能力**：允许设备间直接访问对端显存；NVLink 是**具体物理链路**。P2P 可以跑在 PCIe 上，也可以跑在 NVLink 上。看到「支持 P2P」不能推断「有 NVLink」，实际走哪条路要看 `nvidia-smi topo -m`。

### 1.3 NVLink 与 NVSwitch

- **NVLink** 是 GPU 间高带宽链路；Grace CPU 与 GPU 之间的 NVLink-C2C 是另一回事（芯粒级互联，一致性与系统语义不同）。
- **NVSwitch** 是专用交换芯片，把更多 GPU 组织成一个高带宽 Fabric：

```text
GPU 0 ─┐
GPU 1 ─┤
GPU 2 ─┼─ NVSwitch Fabric ─ 任意目标 GPU
 ...   │
GPU N ─┘
```

NVSwitch 提升的是连接度、双向带宽与可预测性，但它**不会消除**：Collective 的必要数据量、Kernel 启动与协议延迟、热点与并发争用、跨域之后的 IB/RoCE 瓶颈，以及 Rank 放置/切分/同步的不当。

另一个常见误解：NVLink 不会让多卡自动变成「对任意程序透明的共享内存」，你仍然要通过 CUDA、NCCL、NVSHMEM 或框架的通信算子。

### 1.4 Scale-Up 与 Scale-Out

```text
GPU ─ HBM/GDDR
 └─ PCIe/NVLink ─ 单节点 / 单 NVLink 域（Scale-Up）
      └─ NIC + IB/RoCE/Ethernet ─ 多节点（Scale-Out）
```

跨层级的 Collective 通常需要分层算法，不能把全部 Rank 当成同质全互联。

## 2. 产品能力必须按 SKU 判断

| 架构 | 示例 | 互联定位 |
|---|---|---|
| Ampere | RTX 3080 | PCIe，无 NVLink |
| Ampere | RTX 3090 / 3090 Ti | 可选两卡 NVLink Bridge（需装桥并由拓扑确认） |
| Ampere | A100 | PCIe / SXM，部分系统有桥或 NVSwitch |
| Ada | RTX 4090 / L40S | PCIe，无 NVLink |
| Hopper | H100 / H200 | PCIe、SXM、NVL/HGX，NVLink 能力取决于形态 |
| Blackwell | RTX 5090 | PCIe Gen5，无 NVLink（消费级 Blackwell ≠ NVLink 5） |
| Blackwell | B100 / B200 / GB200 | NVLink 5，NVL/HGX 系统可含 NVSwitch |

官方规格里：H100 SXM 的 NVLink 总带宽 900 GB/s、H100 NVL 为 600 GB/s；GB200 NVL72 的 72-GPU 域聚合通信带宽 130 TB/s、单 GPU NVLink 5 约 1.8 TB/s。这些是**特定产品配置的双向或聚合规格**，不要拿来跟一次单向 P2P Copy 的有效带宽直接比。

## 3. 拓扑识别

| 标记 | 含义 | 性能直觉 |
|---|---|---|
| `X` | 自身 | 非通信路径 |
| `NV#` | # 条 NVLink | 常见高速 P2P |
| `PIX` | 至多一个 PCIe Bridge | PCIe 中较短 |
| `PXB` | 多个 PCIe Bridge，不过 Host Bridge | 更长、可能共享上行 |
| `PHB` | 过 PCIe Host Bridge | 常见跨 Root |
| `NODE` | 同 NUMA 内跨 Host Bridge | 更复杂 |
| `SYS` | 过 NUMA 间 CPU 互联 | 最需警惕的单机路径 |

```bash
nvidia-smi --query-gpu=index,name,compute_cap,pci.bus_id,memory.total --format=csv
nvidia-smi topo -m
nvidia-smi topo -mp      # 只看 PCI 路径，确认 Fabric 之下的回退路径
nvidia-smi nvlink --status
lspci -tv
numactl -H
```

**拓扑检查五问**：

1. GPU 对之间是 `NV#`、`PIX`、`PXB`、`PHB` 还是 `SYS`？
2. GPU 与目标 NIC 是否在同一 NUMA / PCIe 局部域？
3. P2P 能力矩阵是否对称且真能用？
4. 链路宽度、代际、速率有没有降级？
5. 容器/虚拟机/IOMMU/ACS 是否改写了直通或 P2P 路径？

## 4. 两个性能模型

### 4.1 延迟—带宽

$$
T_{msg} = \alpha + \frac{S}{B_{eff}}
$$

\(\alpha\) 是软件、协议、调度与链路的固定延迟，\(B_{eff}\) 是该消息大小与方向下的有效带宽。小消息由 \(\alpha\) 主导，大消息由 \(S/B_{eff}\) 主导——**用 1 GiB Copy 测出的 GB/s 回答不了 4 KiB 控制消息的延迟**。

### 4.2 Ring AllReduce 的代价

$$
V_{ring} = 2\frac{N-1}{N}S,\qquad
T_{ring} \approx 2(N-1)\alpha + 2\frac{N-1}{N}\frac{S}{B_{eff}}
$$

通信量趋于 \(2S\) 与 \(N\) 无关，但步数 \(2(N-1)\) 让延迟随 \(N\) 增长。Ring 对大消息友好，树/递归倍增对小消息更优——NCCL 会按消息大小、拓扑与版本选算法。

### 4.3 `algbw` 与 `busbw`

`nccl-tests` 的 `algbw` 是算法层的 Payload 吞吐；为了跨 Collective 比较，AllReduce 常归一化成总线带宽：

$$
busbw = algbw \times 2\frac{N-1}{N}
$$

`busbw` 既不是某条物理链路的单向实测，也不该直接与厂商「全双工聚合带宽」对比。

## 5. 运行环境：GPU 是流水线末端的消费者

主机侧的每一个抖动都会变成 GPU 的空闲。常见链路：

```text
存储/对象存储 → page cache → CPU 解码与预处理 → pinned buffer → H2D → GPU
```

### 5.1 Linux 侧

- **CPU 调度**：CPU 被别的进程抢走，GPU 就出现气泡；容器 CPU 配额过低时 DataLoader 会饿死 GPU。
- **NUMA**：CPU、内存、GPU、NIC 各有归属；跨 NUMA 的 H2D 与网络吞吐都会下降。`numactl -H` 看清拓扑，绑定到同一节点通常立刻见效。
- **affinity 与线程池**：`OMP_NUM_THREADS`、DataLoader worker 数、主进程绑定要一起调；worker 太多反而互相抢核。
- **Swap**：一旦换页，延迟不可预测；训练机通常直接关掉 swap。
- **Page cache 与 readahead**：顺序读大文件受益于预读；随机读小文件则收益有限。
- **THP（透明大页）**：减少 TLB miss，但对分配延迟与碎片敏感，需实测。
- **CPU 频率与 C-state**：省电策略造成频率抖动，表现为周期性 step 变慢。
- **GPU persistence / clock**：`nvidia-persistenced` 避免上下文反复初始化；时钟与功耗上限决定了「标称峰值」能否维持。

### 5.2 Docker 侧

- **驱动与用户态版本**：宿主驱动必须支持容器所需的 CUDA 用户态；镜像里看到 `nvcc` 不代表运行路径正确。
- **cgroup 限制**：CPU quota、memory limit、pids limit 都会间接伤害 GPU 利用率；`/dev/shm` 默认偏小，多进程数据加载容易报错。
- **ulimit / IPC**：文件句柄与共享内存段不足会在高并发下才暴露。
- **不要覆盖宿主驱动组件**：镜像里塞一套驱动库，等于给后面埋一颗随机崩溃的雷。

### 5.3 Kubernetes 侧

- **device plugin** 把 GPU 作为扩展资源暴露给 Pod（`nvidia.com/gpu`），GPU Operator 负责驱动、Container Toolkit、device plugin、GFD 与 DCGM 的部署；
- **拓扑管理器 / 亲和性**：能保证 CPU、内存、GPU 落在同一 NUMA，但需要 kubelet 策略配合，否则「拿到了卡，拿到了错的核」；
- **MIG**：把一张卡切成多个实例，隔离性好但单实例带宽与显存受限，适合小模型多租户，不适合大训练；
- **调度即性能**：同样的 AllReduce，可能走机内 NVLink，也可能绕 PCIe 与跨机网络——GPU、NUMA、NIC 与网络拓扑必须作为调度输入，而不是部署后的偶然结果。

## 写在最后

互联决定了「多卡能多快」，运行环境决定了「标称性能能不能兑现」。下一篇真正下到 Kernel 层：CUDA 编程模型、访存优化、性能分析方法、算子融合与 Triton。
