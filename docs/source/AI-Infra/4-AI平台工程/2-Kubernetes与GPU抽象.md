# Kubernetes 与 GPU 抽象：从节点栈到设备分配

平台的地基是「声明 → 协调 → 证据」这条链。在 GPU 场景下，这条链要穿过驱动、容器工具链、设备插件与 kubelet，任何一环断了，用户看到的都只是「Pod Pending / ContainerCreating」。

## 1. Kubernetes 提供了什么

三件事：

1. **声明式 API**：用户提交对象（Pod / Job / Deployment / CRD），而不是执行命令；
2. **控制循环**：控制器不断比较期望与实际，把系统拉向期望；
3. **调度器**：把对象放到满足约束的节点上，但它只看**声明的资源量**，不看实时利用率。

由此带来一个必须记住的推论：**调度器按整数账本工作。** 一个请求了 GPU 却只做 CPU 预处理的 Pod 仍然占着卡——这保证了所有权，但会降低利用率。正确解法是优化工作流、拆任务或选用共享产品，而不是从账本里强行回收「看起来空闲」的卡。

## 2. Operator 模式：把运维知识写成控制器

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l03_01.png" width="78%" alt="Operator 模式" />
  <p>图 1：CRD 描述期望，控制器持续协调，状态与事件构成证据</p>
</div>

Operator = **自定义资源（CRD）+ 控制器**。它的价值不是「把几个 YAML 打包成 Helm Chart」，而是：

- 新节点出现时补齐组件；
- 节点不需要某组件时避免误装；
- 配置变更时滚动协调；
- 组件失败时用状态与事件暴露偏差。

评估 Operator 是否工作，要看三层证据：

| 层 | 证据 | 回答 |
|---|---|---|
| 策略层 | CR 的 Conditions | 协调器认为整体如何 |
| 覆盖层 | DaemonSet/Deployment 的 Desired/Ready/Unavailable | 组件装到了多少节点 |
| 节点层 | 节点上的 Pod 日志与宿主状态 | 这台机器到底哪里坏了 |

**直接从一条业务 Pod 报错跳到「重装 Operator」，会丢掉故障层次。**

## 3. GPU 节点的软件栈

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l05_01.png" width="78%" alt="GPU 节点软件栈" />
  <p>图 2：驱动 → 容器工具链 → Device Plugin → 发现/监控/验证，逐层依赖</p>
</div>

一条完整的链：**内核模块（驱动）→ 用户态库 → Container Toolkit（运行时注入）→ Device Plugin（资源发布）→ GFD（标签）→ DCGM/Exporter（指标）→ Validator（验收）**。

四个常见断言，每一个都需要独立证据：

- Operator Deployment Running ≠ 驱动已加载；
- Driver DaemonSet 覆盖 ≠ 内核模块能加载（内核头文件、Secure Boot、nouveau 冲突都可能挡住）；
- Toolkit Pod 成功 ≠ 运行时配置生效（GPU 容器仍启动不了）；
- Device Plugin 起来 ≠ 已向 kubelet 注册（调度器看不到资源）。

### 3.1 GPU Operator 管理的是依赖图

管理员提交 `ClusterPolicy` 一类的期望，控制器据此创建驱动、Toolkit、Device Plugin、GFD、DCGM 与 Validator 等 Operand。

三个边界要写进平台契约：

1. **不是兼容层**：OS、内核、GPU 型号、容器运行时、K8s 版本必须在支持矩阵内；网络、镜像仓库、Secure Boot 密钥、内核头文件仍是平台责任；
2. **多节点池需要分策略**：部分节点预装驱动、部分由 Operator 管理，不同代际 GPU 要求不同分支——单一策略表达不了，就用分池或分集群，别让两套管理器在同一节点竞争；
3. **它不提供产品承诺**：不替你决定何时驱逐训练、不保证某框架在特定 NCCL 拓扑上性能正常。

### 3.2 DaemonSet 的升级冲击

DaemonSet 保证「一节点一份」，但不保证「同时更新安全」。GPU 节点价值高、单节点 8 卡，`maxUnavailable=1` 就损失 8 张卡；按百分比滚动可能让大池瞬间失去大量容量。

平台侧要做的：限制谁能改 ClusterPolicy、锁定镜像来源与摘要、审计 HostPath/特权挂载，并在每批升级中观察 **Node Allocatable 与新 Pod 启动**，而不是只看 DaemonSet Ready。

### 3.3 驱动层的三个经典坑

| 坑 | 现象 | 处理 |
|---|---|---|
| 内核与模块不匹配 | 节点自动升级内核后重启，GPU 全失效 | 记录 OS/内核/驱动分支/模块来源，作为不可拆的节点基线；扩容先验证再入池 |
| nouveau 冲突 | 开源驱动先绑定设备，专有模块接管失败 | 节点镜像或启动参数禁用冲突模块，重建 initramfs 并重启 |
| Secure Boot | 模块签名不被信任，加载被拒 | 用受信密钥签名或走 MOK 流程；不要试图在业务 Pod 里绕过 |

「镜像里装 CUDA」修不了宿主驱动：CUDA 镜像提供编译器与运行库，无法替换内核模块。

### 3.4 可用性要从用户请求反向定义

用户要的不是「节点在线」，而是「Pod 按时拿到一台符合属性的健康设备，CUDA 初始化成功，数据路径与互联满足要求，并持续跑到结果完成」。

所以 SLI 至少包含：资源**可发布率**、请求到绑定时间、绑定到 CUDA 初始化时间、验证任务成功率、因设备健康导致的重试率、升级期间的可用容量。**一堆节点绿灯，队列仍可能长时间没容量。**

## 4. GPU 作为扩展资源

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l06_01.png" width="78%" alt="GPU 资源抽象" />
  <p>图 3：Device Plugin 把物理设备变成可调度账本，PodResources 把它映射回真实 UUID</p>
</div>

### 4.1 整数账本与容器级分配

- 扩展资源写在容器 `limits` 中，通常只声明 limit，由系统补出 request；
- **GPU 请求是容器级**：一个 Pod 里两个容器各请求 GPU，会按各自请求分配，不要假设 Pod 内自动共享；
- Init Container 的请求也计入资源计算，模板不应隐藏设备占用。

### 4.2 数量与身份分离

调度阶段只决定**节点**；具体设备 ID 由节点上的 kubelet Device Manager 在容器创建前选择。所以调度器知道「还有两张」，未必知道最后是 UUID-A 还是 UUID-B。

插件可以用 `GetPreferredAllocation` 帮 kubelet 在本节点选更合适的设备（例如同 NUMA），但它是**偏好提示**，不保证采用，也无法修正「调度器选错了节点」。

推论：**不要把正确性建立在偏好上。** 如果必须拿到特定拓扑否则跑不了，要用可验证的硬约束、资源池或 DRA。

### 4.3 归因：PodResources API

设备身份必须在分配后可观察。`PodResourcesLister` 让受信任的监控组件查询「哪个 Pod、哪个容器用了哪个设备」，再由 DCGM 按 UUID 归因。

只有 `request: 1 GPU` 的 PodSpec，事故人员无法知道是哪张卡坏了。这个 Socket 能看到整节点工作负载，**不能挂进任意 Notebook**。

## 5. Device Plugin 的六步生命周期

```text
注册（Registration）→ 发布（ListAndWatch）→ 分配（Allocate）
→ 偏好（GetPreferredAllocation）→ 启动前准备（PreStartContainer）→ 升级
```

### 5.1 注册只是建立合作关系

插件在固定目录（`/var/lib/kubelet/device-plugins/kubelet.sock`）向 kubelet 注册 Socket、API 版本与资源名。**注册成功不代表发现了设备，也不代表 Allocate 一定成功。**

两个高频故障：Socket 未创建/权限错误/API 不兼容导致注册失败；kubelet 重启会清理插件目录里的旧 Socket，插件必须监测并重新注册——否则进程还在 Running，却不再提供资源。

### 5.2 ListAndWatch 与 Capacity/Allocatable

插件以流的方式报告设备列表与健康状态。设备变 Unhealthy 时：

- **Allocatable 减少，Capacity 通常不变**；
- 二者差值可以触发设备故障告警；
- 已分配到该设备的 Pod **不会自动换卡**，需要靠工作负载重建与检查点恢复——静默切卡会破坏上下文、显存与结果语义。

### 5.3 Allocate 必须幂等

Allocate 把「设备节点、挂载、环境变量、CDI 设备名」等注入计划返回给运行时。注意三个层次：Allocate 成功 ≠ 运行时执行成功 ≠ 应用初始化成功。

kubelet 与运行时故障会让调用边界不清，所以插件必须能安全处理重试；失败日志要区分「设备不健康 / 准备失败 / CDI 名生成失败 / 内部错误」。

### 5.4 PreStartContainer 与插件升级

PreStart 用于每次容器启动前的设备准备（重置、初始化），失败会阻止容器启动，所以要考虑可重复性与超时。

插件本身也是容量控制面：给它合适的 Priority、资源请求与容忍，避免被普通压力驱逐；同时限制权限与镜像来源。

## 6. CDI 与 DRA：更丰富的设备表达

- **CDI（Container Device Interface）**：用标准化规格描述「容器需要哪些设备节点、挂载与环境变量」，让注入与运行时解耦，插件返回一个 CDI 设备名即可；
- **DRA（Dynamic Resource Allocation）**：用「资源类 + 资源声明 + 结构化参数」表达需求（例如显存下限、互联要求、共享策略），把「整数账本 + 节点级偏好」升级为可调度的结构化约束。

实践判断：需要**跨节点的属性选择**或**受控共享**时，整数账本加偏好提示不够用，DRA 类模型更合适；只是简单整卡分配时，传统 Device Plugin 仍然最稳。

## 7. 一张排障顺序表

| 现象 | 先看 | 再看 |
|---|---|---|
| Pod Pending（无可用资源） | Node Allocatable / 配额 / 队列 | 设备是否 Unhealthy、是否缺型号 |
| ContainerCreating 卡住 | kubelet 事件 + 插件 Allocate 日志 | CDI 名是否生成、运行时是否报错 |
| Pod Running 但 CUDA 初始化失败 | 宿主驱动与内核模块 | 容器 Toolkit 配置、镜像 CUDA 版本 |
| 训练跑着跑着卡死 | DCGM 指标 + dmesg | 是否 Xid/ECC、是否被 ListAndWatch 标记 Unhealthy |

顺序的核心是**从下往上**：先确认节点与设备，再看插件与运行时，最后才怀疑业务代码。

## 写在最后

这一篇讲的是「资源怎么变成账本，账本怎么变回真实设备」。下一篇继续在同一层：GPU 分区、共享与多租户隔离，高性能网络与拓扑，以及数据与模型制品的存储与分发。
