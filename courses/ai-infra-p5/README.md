# 大模型数据工程与后训练基础设施：配套实验

本实验包对应课程的 30 节课与 6 个综合项目。建议先阅读对应章节，再运行实验、检查结果并修改输入观察变化。

## 目录说明

- `lessons/lesson-01` 至 `lessons/lesson-30`：逐课实验、输入数据与使用说明。
- `projects/project-01` 至 `projects/project-06`：综合项目的机制实验。
- `phase5lab/`：各实验共用的算法实现与 CUDA 探针，运行时需要保留。
- 各课及项目中的 `examples/`：与正文配套的代码阅读材料。

## 开始运行

CPU 机制实验使用 Python 3.10 或更高版本，仅依赖标准库，不下载模型或数据。在解压后的根目录打开终端，执行：

```bash
python check_environment.py
python lessons/lesson-01/run.py
```

第一课的结果保存在 `lessons/lesson-01/results/simulation.json`。查看其中的 `metrics`、`observations` 和 `checks`，并结合该课 README 理解结果。

批量运行所有机制实验：

```bash
python run_all_simulations.py
```

批量运行包含 30 个课内入口、6 个项目入口，以及项目五的策略更新实验和项目六的故障恢复实验，共 38 个入口。

## GPU 实验

GPU 探针需要 PyTorch 与可用的 NVIDIA CUDA GPU，依赖见 `requirements-gpu.txt`。先检查环境，再按各课 README 运行相应入口：

```bash
python run_all_gpu.py --check-only
python lessons/lesson-01/run_gpu.py
```

`--check-only` 只检查环境，不启动实验。`run_gpu.py` 运行单进程 CUDA 基础计算，用于观察设备执行和相关指标。完整模型训练与分布式部署需要按课程中的方案另行配置和实现。

## 综合项目

各项目 README 列出相关课程、运行命令、结果位置和检查条件。项目五与项目六还提供以下独立实验：

```bash
python projects/project-05/train_toy_policy.py
python projects/project-06/durable_commit.py
```

前者用小规模策略观察 SFT、DPO 和组内优势更新；后者通过子进程退出与数据库重启检查原子提交和重试行为。

## 阅读示例代码

`examples/` 中的文本文件对应课程讲解的代码、配置和目录示例，供阅读与扩展。部分片段需要其他模块、模型或数据，不能直接作为完整程序运行；请先使用各课 README 中的实验入口。

## 查看结果与清理

实验输出保存在相应目录的 `results/`。`passed` 表示当前输入满足检查条件，`failed` 表示需要查看失败项，`skipped` 表示缺少所需运行环境。

CPU 机制实验用于理解算法和状态变化，不能据此推算 GPU 吞吐或模型能力。修改输入前建议保留原始 `fixture.json`，方便对照。删除对应目录的 `results/` 即可清理运行产物。
