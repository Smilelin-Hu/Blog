# 可恢复的异步 Agentic RL 后训练平台

![可恢复的异步 Agentic RL 后训练平台](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l36_01.png)

## 1. 项目目标

本项目把前五个项目的数据、Reward、训练与血缘能力组合成持续运行的 Agentic RL 平台。平台负责调度带工具与环境的长轨迹，执行有界异步 Rollout，发布 Policy Bundle，收集 Reward 与 Verifier 证据，按陈旧和算法合同消费 Experience，并在组件崩溃、网络分区和版本回滚后恢复到可证明的提交边界。

目标不是堆出最多分布式组件，而是在正确性基线之上逐步增加吞吐。CPU 机制实验验证租约、幂等、陈旧门禁和恢复状态机；通用 CUDA 路径验证小模型权重发布、Rollout 与 Trainer 的真实边界；多节点配置是生产参考，未拥有目标集群时必须标记 `skipped`，不能虚构吞吐、RPO 或 RTO。

## 2. 平台角色与数据流

Task Service 发布版本化任务和环境合同。Scheduler 根据任务配方、长度预算、风险和资源放置创建逻辑请求。Rollout Worker 取得租约、加载 Policy Bundle、执行模型与工具交互，产生 Trajectory。Environment Manager 提供隔离沙箱、快照、工具凭证和副作用账本。Reward/Verifier Service 输出版本化评分与证据。Experience Sealer 条件封口完整 Group。Trainer 消费通过门禁的 Experience 并提交 Checkpoint。Policy Publisher 把训练布局转换为推理布局并原子发布。

![平台角色与产物责任顺序](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l36_02.png)

沿箭头依次看各个对象，箭头表示本节讨论的依赖或处理顺序。环境交互位于 Rollout 内部，图只概括产物责任顺序。

Registry 保存 Policy、Runtime、Reward、Environment、Schema 和 Recipe 版本。Queue 只承载工作引用，不作为唯一事实源。Event Store 记录状态转换，Manifest Store 保存不可变数据与 Checkpoint，Lineage 连接 Task、Trajectory、Experience、Batch、Checkpoint 和 Deployment。Observability 同时覆盖业务、数据、模型、系统和成本平面。

严格同步模式作为基线：固定 Policy 产生一轮完整数据，Trainer 更新并发布后才进入下一轮。有界异步模式允许 Rollout 和训练重叠，但设置最大版本差、墙钟 TTL、最大在途 Token、Group 版本一致和 Ratio 门禁。开放异步只能作为受控研究分支，不默认用于生产。

## 3. 身份与状态机

Attempt 可以重试，逻辑 Experience 只提交一次。

逻辑身份包括 `task_id`、`request_id`、`episode_id`、`group_id`、`experience_id`、`batch_id`、`optimizer_commit_id` 和 `policy_bundle_id`。物理执行使用 `attempt_id` 与 `lease_id`。同一 Episode 因超时可有多个 Attempt，但只有一个能封口为可消费结果；重复 Attempt 保留成本与故障证据。

请求状态为 Created、Leased、Running、Paused、Sealing、Sealed、Rewarded、Accepted、Committed，以及 Terminal Failed、Invalid、Expired 和 Superseded。每个转换带前置状态、操作 ID、控制器任期和事件版本。服务重试同一操作 ID 得到相同结果；未知状态不能默认继续。

训练提交把 Batch 清单与当前 Checkpoint 绑定。Trainer 完成优化器更新后写候选 Checkpoint 和 Commit Record，全部哈希验证后才推进活动步并 Ack 数据。恢复以 Commit Record 为准，避免 Ack 后崩溃丢数据或权重更新后崩溃重复训练。

## 4. Agent 环境与 Partial Rollout

跨版本续跑必须有算法合同，不能悄悄拼接。

每个环境定义镜像、工具 Schema、网络策略、资源限制、超时、初始化快照、可观察状态和终局判定。工具调用记录请求、响应哈希、副作用 ID 和幂等键。高风险外部动作在模拟或审批环境执行，不允许训练策略直接访问真实生产凭证。

Partial Rollout 区分自然 EOS、长度限制、墙钟限制、工具暂停、主动抢占、用户取消与环境故障。可暂停状态包括对话 Token、KV 或可重建上下文、环境快照、工具副作用、随机状态、Policy 与 Runtime 合同。无法一致恢复时，Partial 只能用于诊断或特定过程监督，不能伪装成可续跑状态。

时间截断允许 Critic Bootstrap 的前提是状态仍合法且 Critic 版本明确；环境损坏不能无条件 Bootstrap。续跑完成后抽样比较截断估值与最终回报。训练配方限制 Partial 轨迹、Token、任务和截断位置占比，并始终保留完整任务成功锚点。

## 5. 权重发布与资源放置

Policy Bundle 包含训练 Checkpoint、推理权重分片、Tokenizer、模板、采样默认、Runtime 兼容、量化、哈希和谱系。发布先在临时前缀生成全部分片，再写 Manifest 并注册 Ready。Worker 在请求边界切换，进行小规模加载验证和 Golden Prompt 桥接；中途切版被禁止。

CUDA 环境可采用时分复用或一 Rollout 一 Trainer。生产集群可以 Colocate 以减少传输，也可以 Disaggregate 独立扩缩。决策基于模型大小、KV、环境等待、网络拓扑、更新频率、故障域和新鲜有效吞吐。资源声明按 GPU、显存、CPU、环境槽位、Token 预算和拓扑，而不是只按 Pod 数量。

权重同步记录发布大小、转换、传输、加载、Warmup、Fleet 完成与旧版本 Drain 时间。增量或共享内存方案必须有完整权重校验回退。任何 Worker 加载失败都不应让路由器假设它已切版。

## 6. 建议仓库

```text
agentic_rl_platform/
  api/
  schemas/task.json
  schemas/experience.json
  schemas/policy_bundle.json
  services/scheduler/
  services/rollout/
  services/environment/
  services/reward/
  services/sealer/
  services/trainer/
  services/publisher/
  services/registry/
  workflows/recovery/
  deploy/local/
  deploy/kubernetes/
  tests/state_machine/
  tests/fault_injection/
  dashboards/
  runbooks/
```

本地部署使用进程或容器模拟服务，SQLite 或 PostgreSQL 保存控制状态，文件或对象存储保存 Manifest。生产部署可使用 Kubernetes、队列、关系数据库和对象存储，但框架可替换。合同测试必须独立于具体队列，避免把供应商语义写进算法。

## 7. CPU 机制实验：租约、陈旧与幂等提交

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `projects/project-06/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python projects/project-06/run.py
python projects/project-06/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

超时不证明旧进程死亡，必须由持久化条件阻止双写。

```python
import json
from dataclasses import dataclass

@dataclass
class Experience:
    experience_id: str
    behavior_version: int
    created_at: int
    state: str = "sealed"
    winner_attempt: str | None = None

class ControlPlane:
    def __init__(self):
        self.items = {}
        self.commits = set()

    def seal(self, item, attempt_id):
        current = self.items.setdefault(item.experience_id, item)
        if current.winner_attempt is None:
            current.winner_attempt = attempt_id
            return "accepted_attempt"
        return "duplicate_attempt" if current.winner_attempt != attempt_id else "idempotent"

    def consume(self, experience_id, current_version, now, max_lag=1, ttl=20):
        item = self.items[experience_id]
        if current_version - item.behavior_version > max_lag:
            return "reject_policy_lag"
        if now - item.created_at > ttl:
            return "reject_wall_clock_age"
        item.state = "accepted"
        return "accepted"

    def commit(self, commit_id, experience_ids):
        if commit_id in self.commits:
            return "idempotent"
        if any(self.items[x].state != "accepted" for x in experience_ids):
            return "invalid_state"
        self.commits.add(commit_id)
        for item in experience_ids:
            self.items[item].state = "committed"
        return "committed"

plane = ControlPlane()
item = Experience("exp-1", behavior_version=3, created_at=100)
assert plane.seal(item, "attempt-a") == "accepted_attempt"
assert plane.seal(item, "attempt-b") == "duplicate_attempt"
assert plane.consume("exp-1", current_version=4, now=110) == "accepted"
assert plane.commit("step-8", ["exp-1"]) == "committed"
assert plane.commit("step-8", ["exp-1"]) == "idempotent"

old = Experience("exp-old", behavior_version=1, created_at=70)
plane.seal(old, "attempt-c")
assert plane.consume("exp-old", current_version=4, now=110) == "reject_policy_lag"
print(json.dumps({"states": {key: value.state for key, value in plane.items.items()}, "commits": sorted(plane.commits)}, indent=2))
```

实验应扩展为随机故障状态机测试：在 Lease 前后、封口前后、Reward 前后和 Commit 前后重复操作，验证没有请求消失、逻辑 Experience 最多提交一次、旧数据被明确拒绝。CPU 实验不证明真实队列的性能，但提供实现必须满足的 Golden 语义。

## 8. 通用 CUDA 桥接路径

单卡基线可以使用小模型与受限环境，先严格串行执行 Rollout、释放推理状态、训练和版本发布；多卡扩展再验证角色分离、数据并行与权重同步。记录各阶段时间、权重大小、峰值显存、生成 Token、完整成功、环境作废和 Checkpoint。依赖探测如下：

```python
import json
import os

try:
    import torch
    checks = {
        "cuda": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count(),
        "memory_gib": [round(torch.cuda.get_device_properties(i).total_memory / 1024 ** 3, 1) for i in range(torch.cuda.device_count())],
        "policy_model": bool(os.environ.get("POLICY_MODEL")),
        "environment_image": bool(os.environ.get("ENVIRONMENT_IMAGE")),
    }
except Exception as exc:
    checks = {"cuda": False, "error": type(exc).__name__}
ready = checks.get("cuda") and checks.get("gpu_count", 0) >= 1 and checks.get("policy_model") and checks.get("environment_image")
print(json.dumps({"status": "ready" if ready else "skipped", "reason": None if ready else "single_gpu_agentic_path_unavailable", "checks": checks}))
```

同步基线通过后，实验分支允许最大 Lag 一并重叠下一轮 Rollout 与当前训练。每条 Experience 保存行为版本和生成端 Logprob，消费时重算 Ratio。固定任务、生成 Token、训练 Token 和停止规则，比较原始吞吐、新鲜有效吞吐、完整任务成功、Ratio 尾部、达到门槛时间和总成本。

本地 CUDA 结果只证明小规模链路。生产集群还需要多节点权重广播、拓扑、Gang 调度、抢占、DRA、对象存储和数据库高可用验证。报告中把“本地实测”“配置审查”和“尚未实测”明确分开。

## 9. 调度与背压

同时计量长任务覆盖，避免只剩容易完成的任务。

Scheduler 按任务配方分桶，保留长任务、安全任务和低频能力配额。优先级由业务权重、年龄、预计成本和风险组成，不能简单让最短任务优先。队列容量按预计 Token、环境槽位与 KV 预算衡量。实际完成分布与目标提交分布持续比较。

背压从 Trainer 与 Reward 向 Rollout 传播。当新鲜库存足够、队列年龄升高或下游故障时暂停新任务；使用滞回与冷却避免振荡。环境故障触发按任务簇熔断，不能让剩余快任务无上限占据训练配方。过期结果进入隔离或离线用途，并保留成本。

## 10. 陈旧门禁与算法合同

消费门禁依次检查 Schema、租户、Task 与 Group 身份、Policy/Runtime/Reward/Environment 版本、墙钟 TTL、Group 完整、行为 Logprob、Ratio、KL 代理、终止原因、Mask 和成本字段。拒绝结果包含机器可读原因，不能只有 `invalid`。

最大 Policy Lag 并非唯一标准。版本更新频率变化时，同一个 Lag 代表不同墙钟和参数距离；因此联合高低 Ratio 分位、Clip Fraction 和 Approx KL。阈值来自同步基线桥接，并随模型、任务、Runtime 和 Reward 升级重新校准。

GRPO Group 成员必须共享行为合同。若最后一个成员超时，按预先规则等待、整组作废或使用安全降级；禁止用新 Policy 样本补齐旧 Group。Partial 成员占比、Bootstrap 与 Loss 权重进入配方和评测。

## 11. 联合 Checkpoint 与恢复

在每个间隙注入失败，检查是否漏学或重复更新。

联合 Checkpoint 包含 Trainer 权重与优化器、Policy Bundle、数据消费游标、已提交 Batch、活动租约摘要、队列快照、任务配方、Reward 与环境版本、控制器任期和事件 Store 位置。不是所有在途 Payload 都要复制进 Checkpoint，但必须能由身份重新获取、作废或重建。

恢复流程先选取最新完整 Commit Record，验证对象哈希和版本注册；启动控制面为只读，重建投影与租约；过期旧租约，新 Attempt 接管；区分已封口未 Reward、已 Reward 未消费、已消费未提交和已提交未发布；最后恢复 Trainer 并发布路由。每一步有守恒检查，失败就停止而不是跳过。

RPO 按“最多丢失多少已接受但未提交的有效 Experience”定义，RTO 按“恢复到稳定新鲜有效吞吐所需时间”定义。只报告服务 Pod 启动时间不合格。单机与多节点分别建立现实阈值，未经实测的目标只能标为 SLO 草案。

## 12. 故障注入计划

每次记录状态守恒和影响范围，不只看服务恢复。

在 Task 提交、队列入队、Worker 租约、环境副作用、Trajectory 上传、条件封口、Reward 写入、Batch 消费、优化器更新、Checkpoint 注册、Policy 转换和路由切换前后杀死组件。加入队列重复投递、数据库延迟、对象存储部分上传、节点时钟偏差、网络分区、GPU OOM、Reward 漏洞和环境镜像升级。

每次注入记录请求守恒、重复 Attempt、重复提交、数据污染、RPO、RTO、成本和人工步骤。关键断言是没有无状态归属的请求、没有同一逻辑数据重复训练、没有 Ready 指向不完整对象、没有混版 Group、没有把环境故障训练成策略失败。

网络分区尤其要验证单领导。旧控制器失去租约后不能继续发布 Policy；新控制器接管前核对活动 Commit。双主比暂时停机更危险，因此控制平面不确定时选择停止推进。

## 13. 可观测性与成本

业务平面看任务提交、完整成功、长任务覆盖与安全；数据平面看 Group、Partial、淘汰、Schema 和配方差异；模型平面看 Reward、Ratio、KL、Entropy、长度和 Verifier；系统平面看队列 Token、年龄、GPU、环境槽位、权重加载和 Checkpoint；成本平面聚合 GPU、CPU、工具、存储、网络、失败与等待。

关键 SLO 包括新鲜有效吞吐、队列年龄高分位、Policy Lag 高分位、Group 完成、环境作废、训练提交重复为零、Checkpoint 成功、恢复时间和每条合格完整轨迹成本。指标标签控制基数，单个 Experience 通过 Trace 查询。在线聚合应能由不可变事件离线重算。

## 14. 发布与持续训练

两套状态机可共享证据，但不能共用一个无审计指针。

新 Checkpoint 先成为 Candidate，运行固定能力、安全、长任务、工具和红队评测；通过后小流量 Canary 生成，不立即替换全部 Rollout。观察行为分布、完整成功、环境成本和 Reward 分歧，再逐步扩大。Serving 发布与 Training Policy 发布是两个状态机，可以共享证据但不能混为同一指针。

事故时冻结 Reward、Trainer 提交和 Policy 发布，停止相关新任务，保存队列与事件现场。根据影响回滚 Policy、隔离 Experience 或恢复同步模式。所有人工动作写回控制面并带操作 ID、负责人和到期条件。

## 15. 验收标准

功能验收要求六个主要角色可运行，Task 到 Checkpoint 血缘完整，严格同步完成至少两轮，有界异步完成桥接。正确性验收要求状态机属性测试、重复投递、训练最多一次、版本与 Group 门禁、Partial 语义、行为概率重算和联合恢复通过。

性能验收同时报告原始和新鲜有效吞吐、Warmup、Drain、队列年龄、达到固定质量门槛时间与总成本。质量验收使用固定任务、多种子、完整成功和安全红线。恢复验收至少在五个关键阶段注入故障，RPO/RTO 按真实证据报告。多节点未运行的项目只能通过配置与演练计划审查，不能计为集群实测。

## 16. 演示脚本

演示先提交一个短任务、一个长工具任务和一个环境故障任务，展示身份、租约和状态。完成严格同步一轮并发布 Policy。第二轮开启 Lag 一流水，展示旧数据门禁与背压。随后在 Trajectory 封口后杀死 Worker，证明重复 Attempt 不会重复训练；再在 Checkpoint 注册中断，恢复到完整 Commit。

最后热更新一个有缺陷的 Reward，红队触发异常后冻结版本、导出受影响 Experience 与 Checkpoint、切回同步和旧 Reward。演示结束时展示完整任务质量、有效吞吐、成本和恢复证据，而不是只展示服务都处于 Running。

## 17. 排障与最终交付

吞吐下降先分解 Rollout、环境、Reward、门禁和 Trainer；队列增长先看 Token 与年龄而非条数。Ratio 异常检查 Token、模板、Runtime 和 Logprob；Group 完成下降检查任务长度、环境与版本切换；恢复重复检查 Commit 与 Ack 顺序；Policy 混版检查 Worker 实际加载报告和路由缓存。

最终交付服务代码或可执行骨架、Schema、状态机、部署配置、CPU 属性测试、单卡基线配置、生产容量模型、Policy Bundle 协议、联合 Checkpoint、故障矩阵、仪表盘、告警、Runbook、演示记录、成本报告和限制清单。平台完成的标志不是“持续在跑”，而是每条学习信号都有合同、每次更新都有提交、每个故障都有边界、每项性能收益都有质量与成本证据。

## 18. 生产架构十二问

### 18.1 队列消失后能否恢复

队列不是唯一事实源。给定 Task、状态事件、Manifest 与 Commit，应能重建未完成工作并为其发放新租约。重建前先过期旧租约和控制器任期，避免旧 Worker 恢复后与新 Attempt 同时封口。

### 18.2 Policy 发布是否真正原子

故意让一个分片上传失败、一个 Worker 加载失败和路由缓存延迟。未完成 Bundle 不得 Ready，失败 Worker 不得接新版本请求，旧 Worker 按 Drain 合同继续。请求记录实际版本而非控制面期望版本。

### 18.3 环境副作用是否幂等

工具动作携带逻辑操作 ID，重试先查询已执行结果。无法幂等的外部动作使用模拟、审批或补偿事务，并在训练中隔离真实生产权限。续跑演练必须证明不会重复支付、发送或写入不可逆状态。

### 18.4 多维陈旧是否独立

制造 Policy 新但 Reward 旧、Policy 旧但环境新、Runtime 改变但版本号不变的样本，门禁给出不同原因。原始维度保留在 Experience 和指标中，综合决策可升级；不能只保存一个总陈旧分。

### 18.5 快任务是否改写配方

固定提交一半长工具、一半短任务，比较完成、封口和训练消费分布。消费器按任务宏配额校正，长任务有保留容量与年龄优先。总体 Token 吞吐不能掩盖长任务从梯度中消失。

### 18.6 Reward 故障是否污染训练

Reward 服务超时、返回 NaN、尺度跳变或被利用时，相关 Experience 进入隔离并触发熔断。Trainer 不能用零分默认值继续。事故演练导出已经消费的 Reward 版本、Batch 与 Checkpoint，并能冻结 Policy 发布。

### 18.7 Trainer Ack 顺序是否安全

分别在权重更新、Checkpoint 写入、Commit 注册和队列 Ack 前后杀死 Trainer。恢复后数据既不丢失也不重复更新。若协议只能提供至少一次执行，要用逻辑提交 ID 实现最多一次学习效果并保存重复 Attempt。

### 18.8 控制器是否可能双主

制造数据库与控制器网络分区，旧任期失效后所有发布和状态写入必须被条件事务拒绝。新领导先核对 Commit、Policy 和租约再推进。系统在不确定时停止更新，比两个 Policy 谱系同时活动更安全。

### 18.9 背压是否形成振荡

对 Reward 和 Trainer 施加周期性降速，观察队列 Token、年龄、Worker 开关和有效吞吐。使用滞回、平滑和最大变化率控制。只按瞬时条数扩缩会在反馈延迟下过冲，制造更多陈旧和加载成本。

### 18.10 恢复时间是否包含稳定化

RTO 从故障开始计算到控制状态恢复、Worker 加载、队列新鲜且有效吞吐稳定，不是 Pod 变绿。恢复报告包括人工判断、Warmup、旧数据分类与新 Checkpoint 时间。未实测的数字只能作为目标。

### 18.11 异步收益是否超过复杂度

固定质量与预算比较同步和有界异步的门槛时间、总成本、故障恢复与值守负担。若原始吞吐增加但淘汰、环境成本和事故风险抵消收益，应保留同步或更紧边界。异步程度不是成熟度排名。

### 18.12 能否在一分钟内冻结污染

值班人员应有单一受审计操作，停止新 Trainer 提交、Policy 发布和相关 Reward 任务，同时保存现场而非清空队列。操作幂等、可验证、可回滚，并展示受影响版本与在途数量。快速安全停止是持续训练平台的核心能力。

## 19. 用真实进程崩溃检验一次提交

实验使用 SQLite 将一个整数模型状态和提交账本放入同一事务。子进程分别在提交前、提交后直接退出，父进程重新打开数据库并重试；最终检查权重只增加一次、提交只有一条、同一 Batch 携带不同内容时被拒绝。GPU 权重通常不在同一个数据库事务中，因此这个实验只提供原子提交的可读基线，不能证明跨队列、对象存储和 GPU 的分布式一次效果。

```bash
python projects/project-06/durable_commit.py
```

下面代码直接取自实验包同名文件。运行报告保存在该项目的 `results/` 中；失败记录不改写为成功。

```python
"""Durable single-database commit and failure injection. No distributed guarantee."""
from __future__ import annotations
import argparse,json,sqlite3,subprocess,sys,tempfile
from pathlib import Path

def connect(path):
    db=sqlite3.connect(path);db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS model(id INTEGER PRIMARY KEY, weight INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO model VALUES (1,0)')
    db.execute('CREATE TABLE IF NOT EXISTS commits(batch TEXT PRIMARY KEY, delta INTEGER NOT NULL)');db.commit();return db

def commit(path,batch,delta,crash):
    db=connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT delta FROM commits WHERE batch=?',(batch,)).fetchone()
        if old:
            if old[0]!=delta:raise ValueError('same batch identity with conflicting content')
            db.rollback();return 'duplicate'
        db.execute('UPDATE model SET weight=weight+? WHERE id=1',(delta,))
        if crash=='before_commit':
            import os;os._exit(71)
        db.execute('INSERT INTO commits VALUES (?,?)',(batch,delta));db.commit()
        if crash=='after_commit':
            import os;os._exit(72)
        return 'committed'
    finally:db.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--crash',default='none');a=parser.parse_args()
    if a.worker:commit(a.worker,'batch-1',3,a.crash);return 0
    results=[]
    with tempfile.TemporaryDirectory(prefix='course-commit-') as folder:
        for mode,code in [('before_commit',71),('after_commit',72)]:
            path=str(Path(folder)/(mode+'.sqlite'));connect(path).close()
            p=subprocess.run([sys.executable,__file__,'--worker',path,'--crash',mode],timeout=20)
            assert p.returncode==code
            outcome=commit(path,'batch-1',3,'none');db=connect(path)
            weight=db.execute('SELECT weight FROM model').fetchone()[0];count=db.execute('SELECT COUNT(*) FROM commits').fetchone()[0];db.close()
            assert weight==3 and count==1
            try:commit(path,'batch-1',4,'none')
            except ValueError:conflict=True
            else:conflict=False
            assert conflict
            results.append({'crash':mode,'retry':outcome,'weight':weight,'commits':count,'conflicting_retry_rejected':conflict})
    report={'status':'passed','cases':results,'boundary':'Single SQLite transaction stores both toy model state and commit. Separate GPU weights, queues, leadership and multi-node failures are not covered.'}
    out=Path(__file__).with_name('results');out.mkdir(exist_ok=True);(out/'durable_commit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
```

## 写在最后

数据工程与后训练六个项目到此收束，整条链路从原始字节一直贯通到可恢复的训练平台。返回系列目录：[AI Infra 笔记总览](/source/AI-Infra/README)。