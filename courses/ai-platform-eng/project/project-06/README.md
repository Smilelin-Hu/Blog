# project-06：企业级自助 AI 平台

本目录对应综合项目 6。它提供一个有界、确定性的机制模拟，以及一个需要显式环境参数的真实系统入口。

## 模拟路径

在实验包根目录运行：

```bash
python3 projects/project-06/run.py
```

模拟读取 `enterprise_scenario.json`，执行 `enterprise_platform.py`，把报告写入 `results/project-06/enterprise_platform_report.json`。重复运行会覆盖该单元自己的报告，不会访问云账号或创建真实集群资源。

模拟能够证明策略、状态转移、失败分类和报告合同在给定场景下按预期工作；它不能证明真实 GPU 性能、网络吞吐、控制器兼容性、云容量或生产 SLO。

## 真实环境路径

先执行只读前置检查：

```bash
python3 projects/project-06/run.py --real --check-only
python3 projects/project-06/enterprise_platform.py --help
```

确认隔离环境、权限、成本上限和清理范围后，把主脚本帮助中列出的真实参数传给入口：

```bash
python3 projects/project-06/run.py --real -- <真实环境参数>
```

没有 Kubernetes、GPU、Slurm 或所需外部端点时，前置检查或主脚本必须返回 `SKIPPED` 及原因。检测到工具只表示可以继续检查，不代表真实实验已经 PASS。任何实际运行都应记录硬件、数量、软件版本、精度或并发、工作负载和时间窗口。

## 输入与文件

- `enterprise_platform.py`
- `enterprise_scenario.json`
- `run.py`：安全模拟入口。
- `run.py --real`：真实能力检查与参数转发入口。
- `requirements-gpu.txt`：可选真实依赖说明。

## 指标

- 首次成功时间
- 自助完成率
- 跨集群派发成功率
- 平台请求 SLO
- 单位工作负载成本

## 验收标准

- 普通用户无需集群管理员权限
- 统一入口可提交训练与部署
- 策略与配额在派发前执行
- 多集群状态成本和审计可聚合
- 报告必须区分 PASS、FAIL 与 SKIPPED，并为失败或跳过提供明确原因。
- 输出不能把模拟数据描述为真实硬件或真实控制面的测量结果。

## 常见失败与清理

参数缺失应先查看主脚本 `--help`；权限、CRD、设备或端点缺失按运行合同报告 SKIPPED 或 FAIL。模拟只写 `results/project-06/`，可直接删除该目录。真实路径的资源必须在隔离命名空间或专用环境中创建，并按照主脚本及课程页面列出的顺序回收；不应对生产集群直接执行故障注入。

## 统一实验入口

本目录只有 `run.py` 是可执行入口。默认运行随包 Fixture；`python run.py --check-only` 只检查真实路径前提；`python run.py --real` 才进入真实、本地或 GPU 路径。
