# 国产 GPGPU AI 推理优化工程师培养方案

> 适配岗位：海光信息 AI 算法优化工程师 / 国产 GPGPU 框架适配工程师（成都双流）
> 个人基础：C\+\+ 大学水平、Python/PyTorch 熟练、CUDA 零基础
> 每日投入：2 小时
> 总周期：24 周（约 5\.5 个月），周末额外投入可压缩至 20 周
> 资源逻辑：DataWhale 负责入门引路与习题巩固，工业级开源仓库负责深度实战与岗位匹配，国产生态资源精准对接海光 DCU
> 
> 

---

## 一、培养总览

### （一）核心能力闭环

1. 底层基础：计算机体系结构 \+ C\+\+ 工程化 \+ Linux 性能分析 \+ PyTorch 底层

2. 并行计算：CUDA/HIP Kernel 编程 \+ CUTLASS/CK 高性能算子库 \+ 性能剖面调优

3. 推理框架：CV 与 LLM 全栈推理引擎部署、量化优化、源码级二次开发

4. 编译器方向：Triton 算子开发 \+ XLA/IREE 通用编译体系

5. 国产适配：海光 DCU/DTK 生态 \+ 框架插件化适配方法论 \+ 系统级优化

6. 业务落地：LLM/VLM/搜推广多场景端到端性能优化

### （二）阶段划分与时间分配

|阶段|周期|核心目标|
|---|---|---|
|第一阶段：基础筑基期|3 周|补齐硬件、C\+\+、系统、模型底层四大基础，平滑进入 GPU 开发|
|第二阶段：核心技术期|8 周|精通 CUDA/HIP 并行编程，掌握 JD 点名的全部推理框架|
|第三阶段：专项深耕期|5 周|深入 AI 编译器、国产 GPGPU 适配、业务场景优化|
|第四阶段：实战落地期|6 周|完成 3 个硬核项目，形成可写进简历的作品集|
|第五阶段：面试冲刺期|2 周|简历包装、题库梳理、模拟面试|

### （三）每日 2 小时标准分配

- 40 分钟：理论学习（读文档、看教程、理解原理）

- 1 小时 10 分钟：动手实操（写代码、编译环境、排错、完成练习）

- 10 分钟：当日复盘（记录知识点、踩坑点、未解决问题）

---

## 学习渠道与入口（在哪里学）

本方案全部资源均为免费公开渠道，按「中文在线文档 \+ GitHub 源码 \+ 官方文档 \+ B 站视频 \+ 海光社区」组合使用。下面先给平台总览，再给第一阶段每周的精准可点击入口，点开即学，无需再自行搜索。

### （一）五大学习平台总览

|平台|入口网址|形式|主要用途|
|---|---|---|---|
|**DataWhale 在线文档**|[llm\-algo\-leetcode 在线版](https://datawhalechina.github.io/llm-algo-leetcode/)|中文 Notebook，可在线运行|入门引路、边学边练、刷题巩固|
|**GitHub**|[github\.com](https://github.com/datawhalechina/llm-algo-leetcode)|源码仓库|clone 代码、看源码、提交作业、归档作品集|
|**NVIDIA / AMD 官方文档**|[CUDA 文档](https://docs.nvidia.com/cuda/cuda-c-programming-guide/) / [ROCm 文档](https://rocm.docs.amd.com/)<br>|权威技术文档|查准 API、原理、官方最佳实践|
|**B 站视频**|[bilibili\.com](https://www.bilibili.com)|免费视频课程|入门预热、难点听讲、配合实操|
|**海光光合开发者社区**|[developer\.sourcefind\.cn](https://developer.sourcefind.cn/)|国产 DCU 专属文档/镜像/视频|DTK 下载、DCU 教程、框架适配样例|

### （二）第一阶段每周精准入口（点开即学）

|周次|学习主题|去哪学（点击直达）|形式|
|---|---|---|---|
|**第 1 周**|体系结构与 GPGPU 硬件原理|- [llm\-algo\-leetcode 在线版](https://datawhalechina.github.io/llm-algo-leetcode/)：Part01 硬件与系统<br>- [CUDA 编程指南](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)：第 3、4 章编程模型与硬件实现<br>- [海光 DTK 与 DCU 介绍](https://developer.sourcefind.cn/dtk)|在线文档 \+ 官方文档|
|**第 2 周**|C\+\+ 工程能力强化|- [modern\-cpp\-tutorial](https://github.com/changkun/modern-cpp-tutorial)：智能指针、移动语义、泛型、并发<br>- [cmake\-examples](https://github.com/ttroy50/cmake-examples)：工程构建与库链接<br>- [googletest](https://github.com/google/googletest)：单元测试|GitHub 中文教程 \+ 示例|
|**第 3 周**|Linux 性能工具 \+ PyTorch 底层|- [Brendan Gregg perf 指南](https://www.brendangregg.com/perf.html)<br>- [FlameGraph 火焰图](https://github.com/brendangregg/FlameGraph) / [perf\-tools](https://github.com/brendangregg/perf-tools)<br>- [thorough\-pytorch](https://github.com/datawhalechina/thorough-pytorch)：自定义算子章节<br>- [diy\-llm](https://github.com/datawhalechina/diy-llm)：Transformer 基础<br>- [图解 Transformer](https://jalammar.github.io/illustrated-transformer/)|官方文档 \+ GitHub \+ 图解|

### （三）配套视频课程（B 站，入门难点配合看）

- [NVIDIA 现代 CUDA C\+\+ 编程课程（官方，含 Colab 练习）](https://www.bilibili.com/video/BV1VLSnBqEe1/)

- [小彭老师：用现代 C\+\+ 的方式打开 CUDA（中文讲解，适合零基础）](https://www.bilibili.com/video/BV1ndhCzXEXm/)

- [NVIDIA CUDA 官方入门课（中文字幕）](https://www.bilibili.com/video/BV1yr4AzKETn/)

### （四）使用与访问提示

- **先在线浏览，再 clone 实操：**先用 DataWhale 的 GitHub Pages 在线版理解结构，再到对应 GitHub 仓库点「Code → Download ZIP」或用 git clone 拉到本地动手。

- **国内访问 GitHub 慢：**可改用 Gitee 镜像搜索同名仓库，或注册后通过 GitHub 桌面端拉取；文档类资源优先用 GitHub Pages 在线版，速度更快。

- **视频与文档比例：**每天 2 小时中视频不超过 40 分钟，其余时间必须动手写代码、跑示例，避免只看不动手。

- **海光 DCU 资源：**DTK 安装包、适配框架、预置镜像均在光合社区免费下载；无 DCU 卡时，先用 AMD ROCm 生态完成等价练习，方法可平移。

- **作业归档：**所有练习统一放到自己的 GitHub 仓库，保持提交记录，后续直接作为简历作品集。

---

## 二、第一阶段：基础筑基期（第 1\-3 周）

核心原则：跳过重复入门内容，精准补岗位刚需能力；所有知识点配套可运行的开源示例，避免纯理论学习。每周 6 个学习日 \+ 1 个弹性缓冲日。

### 第 1 周：计算机体系结构与 GPGPU 硬件原理

周核心目标：建立 SIMT 并行思维，吃透 GPU 内存层次与性能瓶颈本质，熟悉海光 DCU 硬件体系。

#### Day 1：CPU 体系结构与性能基础

理论学习（40 分钟）：

1. CPU 缓存层次：L1/L2/L3 缓存、缓存命中、缓存行、局部性原理

2. 流水线、分支预测、NUMA 多核架构基础

3. 计算访存比（算术强度）概念，区分计算密集型与访存密集型任务

配套资源：`llm-algo-leetcode` Part01 硬件与系统开篇章节 \+ 《计算机组成与设计》缓存章节。

动手实操（60 分钟）：

1. 使用 `htop`、`lscpu` 查看本机 CPU 核心、缓存、NUMA 拓扑

2. 运行简易循环计算程序，观察 CPU 占用与缓存命中率变化

当日复盘（10 分钟）：记录缓存局部性对程序性能的影响，整理 3 个提升缓存命中率的手段。

#### Day 2：GPGPU SIMT 执行模型

理论学习（40 分钟）：

1. SIMT 单指令多线程执行模型，与 CPU SIMD 的核心区别

2. 线程层级：Grid / Block / Thread 的组织方式与全局索引计算

3. Warp 调度、分支分化（Branch Divergence）的产生原因与性能影响

配套资源：CUDA 官方编程指南第 3 章「编程模型」\+ `llm-algo-leetcode` GPU 编程基础章节。

动手实操（60 分钟）：

1. 推导 2D Grid/Block 下的全局线程索引计算公式

2. 手绘 SIMT 执行模型示意图，标注 SM、Warp、线程、寄存器的对应关系

当日复盘（10 分钟）：用自己的话解释「为什么分支分化会降低 GPU 性能」。

#### Day 3：GPU 五层内存模型

理论学习（40 分钟）：

1. 寄存器 / 共享内存 / L2 缓存 / 全局内存 / 本地内存的容量、延迟、带宽差异

2. 访存合并（Memory Coalescing）的原理与生效条件

3. Shared Memory Bank 冲突的产生原因与规避方法

配套资源：CUDA 官方编程指南第 4 章「硬件实现」\+ `GPU-Programming` 内存优化讲义。

动手实操（60 分钟）：

1. 整理对比表格：五种内存的访问延迟、带宽、容量、作用、可编程性

2. 分析「向量加法」和「矩阵乘法」分别属于访存密集还是计算密集型任务

当日复盘（10 分钟）：记录 3 种优化 GPU 访存性能的核心手段。

#### Day 4：SM 流多处理器架构与性能指标

理论学习（40 分钟）：

1. SM 内部组成：运算单元（CUDA Core/Tensor Core）、调度器、寄存器堆、共享内存

2. Occupancy（占用率）概念：活跃 Warp 数与最大 Warp 数的比值

3. GPU 核心性能指标：算力（FLOPS）、显存带宽、功耗、显存容量

配套资源：NVIDIA Ampere 架构白皮书 \+ `llm-algo-leetcode` 性能分析章节。

动手实操（60 分钟）：

1. 查询 NVIDIA A100、RTX 3090 的 FP32 算力、显存带宽、显存容量参数

2. 计算一个 GEMM 算子的理论计算访存比，判断其瓶颈类型

当日复盘（10 分钟）：总结「判断一个算子瓶颈在计算还是访存」的通用方法。

#### Day 5：AMD ROCm 与海光 DCU 生态

理论学习（40 分钟）：

1. AMD CDNA 架构特点，ROCm 软件栈组成（HIP、rocBLAS、MIGraphX、RCCL）

2. 海光 DCU 产品定位、K100/K200 系列硬件规格

3. 海光 DTK 工具链与标准 ROCm 的关系与差异

配套资源：海光光合开发者社区产品介绍页 \+ ROCm 官方生态概览。

动手实操（60 分钟）：

1. 浏览海光开发者社区，整理 DCU 开发环境搭建、工具链、样例代码三大板块入口

2. 补充硬件参数对比表，加入海光 DCU K200 的完整参数

当日复盘（10 分钟）：记录海光 DCU 与 NVIDIA GPU 的 3 点核心差异。

#### Day 6：周作业：主流 GPGPU 硬件参数对比报告

理论学习（40 分钟）：回顾本周体系结构核心知识点，梳理性能优化的底层逻辑。

动手实操（60 分钟）：

1. 完成《主流 GPGPU 硬件参数对比表》，覆盖 NVIDIA A100、AMD MI100、海光 DCU K200

2. 对比维度：FP32/FP16 算力、显存带宽、显存容量、功耗、典型适用场景

3. 补充 200 字选型结论：不同业务场景下的硬件选型建议

当日复盘（10 分钟）：本周知识点总复盘，标记未理解透彻的内容。

#### Day 7：弹性缓冲日

补完未完成的练习，回看薄弱知识点，或休息调整。

### 第 2 周：C\+\+ 工程能力强化

周核心目标：补齐现代 C\+\+ 特性、CMake 工程构建、调试与单元测试能力，能独立开发小型数值计算库。

#### Day 1：现代 C\+\+ 核心：智能指针与 RAII

理论学习（40 分钟）：

1. RAII 核心思想、内存管理本质

2. `unique_ptr`、`shared_ptr`、`weak_ptr` 的用法、区别与适用场景

3. 裸指针、智能指针的性能差异与常见误用

配套资源：`modern-cpp-tutorial` 第 3 章「内存管理」。

动手实操（60 分钟）：

1. 用智能指针实现简易动态数组类，支持自动内存释放

2. 编写测试用例，验证 `shared_ptr` 引用计数的变化逻辑

当日复盘（10 分钟）：记录智能指针的 3 个常见误用场景。

#### Day 2：移动语义、右值引用与拷贝控制

理论学习（40 分钟）：

1. 左值、右值、右值引用的概念

2. 移动构造、移动赋值、`std::move` 的作用与性能收益

3. 拷贝控制：构造、析构、拷贝构造、拷贝赋值、移动构造

配套资源：`modern-cpp-tutorial` 第 2 章「语言特性」右值引用部分。

动手实操（60 分钟）：

1. 为矩阵类添加移动构造与移动赋值函数

2. 对比拷贝和移动两种方式的性能差异（计时统计）

当日复盘（10 分钟）：总结适合使用移动语义提升性能的场景。

#### Day 3：模板泛型编程与 STL 性能注意事项

理论学习（40 分钟）：

1. 函数模板、类模板基础，模板特化与偏特化

2. STL 常用容器（vector、map、unordered\_map）的性能特点与适用场景

3. 泛型编程在算子库、推理框架中的作用

配套资源：`modern-cpp-tutorial` 第 4 章「泛型编程」。

动手实操（60 分钟）：

1. 将矩阵运算库改造成模板类，同时支持 FP16、FP32 两种精度

2. 对比 vector 按值插入和 emplace\_back 的性能差异

当日复盘（10 分钟）：记录模板编程的 2 个优势与 2 个常见坑。

#### Day 4：CMake 工程构建体系

理论学习（40 分钟）：

1. CMake 基础语法：变量、编译选项、头文件路径、库链接

2. 静态库、动态库的生成与链接方法

3. 第三方依赖引入的两种方式：find\_package 与 add\_subdirectory

配套资源：`cmake-examples` 01\-basic、02\-sub\-projects 全部示例。

动手实操（60 分钟）：

1. 用 CMake 重构矩阵运算库，拆分为「矩阵静态库」\+「测试程序」两个目标

2. 跑通完整编译流程，验证库链接正确性

当日复盘（10 分钟）：记录 CMake 编译常见报错与排查方法。

#### Day 5：GDB 调试与 Google Test 单元测试

理论学习（40 分钟）：

1. GDB 核心命令：断点、单步执行、栈回溯、变量查看、内存打印

2. 单元测试的意义，gtest 基础用法：TEST 宏、断言、测试套件

3. Google C\+\+ 编码规范核心要点（命名、头文件、内存管理）

配套资源：GDB 官方速查手册 \+ `googletest` 官方入门示例。

动手实操（60 分钟）：

1. 用 GDB 调试矩阵乘法程序，定位人为制造的数组越界 bug

2. 为矩阵运算库接入 gtest，编写 3 个以上单元测试用例

当日复盘（10 分钟）：整理 5 个最高频使用的 GDB 命令。

#### Day 6：周作业：矩阵运算库完整交付

理论学习（40 分钟）：回顾高性能编码原则：内存对齐、缓存友好、分支预测优化。

动手实操（60 分钟）：

1. 完善矩阵运算库：支持 FP16/FP32 精度、矩阵加法、矩阵乘法

2. 补充完整单元测试，确保所有接口正确性

3. 用 GDB 全流程调试，确认无内存越界、泄漏问题

当日复盘（10 分钟）：本周 C\+\+ 知识点总复盘，标记薄弱项。

#### Day 7：弹性缓冲日

补全代码与文档，或补充学习并发编程、Lambda 等拓展内容。

### 第 3 周：Linux 性能工具 \+ PyTorch 底层进阶

周核心目标：掌握性能优化标配工具链，吃透 PyTorch 自定义算子机制，夯实 Transformer 基础。

#### Day 1：Shell 脚本自动化与文本处理

理论学习（40 分钟）：

1. Shell 脚本基础：变量、循环、条件判断、参数传递

2. 文本处理三剑客：grep、awk、sed 基础用法

3. 自动化压测脚本的设计思路

配套资源：《鸟哥的 Linux 私房菜》Shell 编程章节。

动手实操（60 分钟）：

1. 编写 Shell 脚本，循环调用矩阵运算库，自动统计每次运行耗时

2. 用 awk 提取运行日志中的耗时数据，计算平均耗时

当日复盘（10 分钟）：记录 Shell 脚本调试的常用方法。

#### Day 2：perf 性能分析与火焰图

理论学习（40 分钟）：

1. `perf stat`：统计 CPU 周期、指令数、缓存命中率

2. `perf record / perf report`：采集并查看热点函数

3. on\-CPU 火焰图生成方法与瓶颈定位逻辑

配套资源：`perf-tools` 基础示例 \+ `FlameGraph` 官方使用说明。

动手实操（60 分钟）：

1. 用 perf 采集矩阵乘法程序的热点函数分布

2. 用 FlameGraph 生成 on\-CPU 火焰图，定位最耗时的函数

当日复盘（10 分钟）：总结 perf 定位性能问题的标准流程。

#### Day 3：Docker 环境基础

理论学习（40 分钟）：

1. 镜像、容器、Dockerfile 核心概念

2. 容器内开发、环境隔离、端口映射方法

3. GPU 容器（nvidia\-docker / rocm\-docker）基础

配套资源：Docker 官方入门指南。

动手实操（60 分钟）：

1. 编写 Dockerfile，将矩阵运算库打包到 Ubuntu 镜像中

2. 在容器内编译运行，验证环境一致性

当日复盘（10 分钟）：记录容器化开发的 3 个核心优势。

#### Day 4：Transformer 核心原理与 KV Cache

理论学习（40 分钟）：

1. 自注意力机制完整计算流程：Q/K/V 生成、注意力分数计算、加权求和

2. 多头注意力的作用与计算逻辑

3. KV Cache 的原理，推理阶段显存与速度的权衡

配套资源：`diy-llm` Transformer 章节 \+ The Illustrated Transformer。

动手实操（60 分钟）：

1. 手绘 Transformer Encoder 结构图，标注每个模块的维度变化

2. 推导 KV Cache 的显存占用计算公式

当日复盘（10 分钟）：用自己的话解释 KV Cache 为什么能加速推理。

#### Day 5：PyTorch 自定义算子与底层机制

理论学习（40 分钟）：

1. PyTorch 自动微分原理、算子注册机制

2. C\+\+ 扩展（Torch API）开发流程：编写、编译、Python 端调用

3. TorchScript 与 ONNX 导出基础

配套资源：`thorough-pytorch` 自定义算子章节 \+ PyTorch 官方 C\+\+ 扩展教程。

动手实操（60 分钟）：

1. 用纯 PyTorch 张量操作实现简化版多头注意力

2. 与 `torch.nn.MultiheadAttention` 做精度对比，控制误差在 1e\-5 以内

当日复盘（10 分钟）：记录自定义算子开发的标准步骤。

#### Day 6：周作业：性能分析报告 \+ 手写 Attention 交付

理论学习（40 分钟）：回顾本周性能工具与模型基础知识点。

动手实操（60 分钟）：

1. 输出矩阵运算库性能分析报告：包含火焰图截图、热点函数分析、优化建议

2. 完善手写多头注意力代码，补充精度校验脚本，整理为完整可运行工程

当日复盘（10 分钟）：第一阶段整体复盘，列出进入 CUDA 学习前需要补充的薄弱点。

#### Day 7：弹性缓冲日

补全作业与文档，休整过渡，准备进入第二阶段 CUDA 编程学习。

### 第一阶段验收标准

1. 能独立讲清 SIMT 执行模型、五层内存结构，说明访存合并、分支分化对性能的影响

2. 能用 C\+\+ \+ CMake \+ gtest 独立完成小型数值计算库，会用 GDB 调试常规问题

3. 能用 perf \+ 火焰图定位 C\+\+ 程序性能热点，读懂基础 on\-CPU 火焰图

4. 能讲清 Transformer Attention 计算流程，能手写实现并与官方算子完成精度对齐

---

## 三、第二阶段：核心技术期（第 4\-11 周）

核心原则：原理学习 \+ 官方示例 \+ 动手调优三位一体，所有框架不满足于部署使用，必须理解核心设计与优化逻辑。

### 模块 A：并行计算与算子开发（第 4\-7 周）

#### 第 4 周：CUDA 编程入门

核心学习目标：掌握 CUDA 编程模型，能独立编写基础 Kernel，理解线程层级与内存模型。

核心内容：

1. CUDA 编程模型：Grid/Block/Thread 线程层级、内存模型、同步机制

2. 基础 Kernel 开发：向量加法、规约运算、分块矩阵乘法

3. Kernel 启动、内存拷贝、Stream 异步流

配套资源：`cuda-samples` 官方示例库、CUDA 官方编程指南、`llm-algo-leetcode` CUDA 模块。

必做实战：

1. 跑通 5 个以上官方 CUDA 示例，修改参数观察性能变化

2. 手写分块 GEMM Kernel，利用共享内存降低全局内存访问

周验收标准：能独立编写并调试基础 CUDA Kernel，理解访存合并、共享内存的作用。

#### 第 5 周：CUDA 性能优化与剖面分析

核心学习目标：掌握 GPU 性能优化方法论，能用工具定位 Kernel 瓶颈，完成经典算子优化。

核心内容：

1. 优化方法论：访存合并、Shared Memory Bank 冲突、Occupancy 优化、指令级并行

2. 性能工具：Nsight Compute / Nsight Systems 定位 Kernel 瓶颈

3. 经典算子优化：GEMM、Reduce、Softmax、LayerNorm

配套资源：CUDA Best Practices Guide、Nsight Compute 官方教程。

必做实战：

1. 用 Nsight Compute 分析自研 GEMM Kernel，定位访存、算力、分支瓶颈

2. 完成 GEMM Kernel 至少 30% 的性能提升，输出优化前后对比报告

周验收标准：能讲清 GPU 性能优化的核心维度，能用工具定位并解决基础 Kernel 性能问题。

#### 第 6 周：HIP 编程与国产芯片迁移基础

核心学习目标：掌握 HIP 编程模型，能完成 CUDA 到 HIP 的算子迁移，熟悉 ROCm 工具链。

核心内容：

1. HIP 编程模型、CUDA 与 HIP API 语法映射、HIP Runtime 接口

2. hipify\-perl / hipify\-clang 自动迁移工具的使用与局限

3. ROCm 工具链、海光 DTK 开发环境架构

配套资源：`rocm-examples` 官方示例、HIPIFY 官方工具、海光 DTK 使用指南。

必做实战：

1. 用 hipify\-clang 将第 4 周的 CUDA GEMM Kernel 迁移为 HIP 版本

2. 修复自动转换的编译与精度问题，rocprof 对比性能差异

3. 整理《CUDA 到 HIP 迁移常见问题与解决方案》文档

周验收标准：能独立完成简单 CUDA 算子到 HIP 的迁移，理解两者的核心差异。

#### 第 7 周：高性能算子库（CUTLASS / CK）

核心学习目标：掌握工业级高性能算子库的使用与设计思想，对标岗位日常开发工具。

核心内容：

1. CUTLASS：NVIDIA 端高性能算子库，Tiling 分块架构、GEMM/Conv 算子调用

2. Composable Kernel（CK）：ROCm/海光 DCU 核心算子库，算子组合设计理念

3. 两大库的设计差异与适用场景

配套资源：CUTLASS 官方仓库与 GEMM 教程、CK 官方 Hello World 教程。

必做实战：

1. 分别用 CUTLASS 和 CK 实现 FP16 GEMM 算子，跑通性能测试

2. 对比两者的理论算力达成率，分析设计差异与适用场景

周验收标准：能调用两大算子库实现基础算子，理解其核心优化思想。

### 模块 B：全栈推理框架掌握（第 8\-11 周）

#### 第 8 周：CV 类推理框架（ONNX Runtime \+ PPL \+ TensorRT）

核心学习目标：掌握 CV 场景三大推理框架，理解图编译与算子融合的核心逻辑。

核心内容：

1. ONNX 模型导出规范、ORT 图优化、量化、自定义算子开发

2. PPLNN 推理框架架构、CV 场景部署、国产硬件适配模式

3. TensorRT 图编译原理：算子融合、常量折叠、INT8/FP8 量化、Plugin 插件

配套资源：`trt-samples-for-hackathon-cn` 中文实战、ONNX Runtime 官方仓库、PPLNN 开源仓库。

必做实战：

1. YOLOv8 导出 ONNX，分别用 ONNX Runtime 和 TensorRT 部署

2. 开启 TensorRT INT8 量化，完成精度校验与性能对比

周验收标准：能独立完成 CV 模型从 PyTorch 到推理引擎的全流程部署与量化。

#### 第 9 周：LLM 推理框架（vLLM \+ LMDeploy \+ TGI）

核心学习目标：掌握三大主流 LLM 推理引擎，吃透 PagedAttention、连续批处理等核心技术。

核心内容：

1. vLLM：PagedAttention 原理、连续批处理、调度器架构、多卡并行

2. LMDeploy：Turbomind 引擎、W4A16 量化、KV Cache 管理、多模态支持

3. TGI：HuggingFace 生产级推理服务、动态批处理、在线服务架构

配套资源：vLLM 官方仓库与文档、LMDeploy 官方中文教程、TGI 官方仓库。

必做实战：

1. 分别用 vLLM、LMDeploy 部署 Qwen\-7B 模型

2. 编写统一压测脚本，对比首 token 延迟、吞吐、显存占用三大指标

周验收标准：能讲清 vLLM 与 LMDeploy 的核心设计差异，能独立完成大模型部署与压测。

#### 第 10 周：AI 模板编译器（AITemplate）

核心学习目标：理解静态代码生成型推理编译器的设计思想，掌握 AITemplate 的使用。

核心内容：

1. AITemplate 设计理念：Python 声明式 API、静态代码生成、算子深度融合

2. 多硬件后端适配机制、与 TensorRT 的优劣势对比

配套资源：AITemplate 官方仓库与文档。

必做实战：

1. 将 ViT 模型通过 AITemplate 编译部署

2. 对比 AITemplate 与 TensorRT 的推理性能、显存占用、编译耗时

周验收标准：能讲清 AITemplate 与 TensorRT 的核心区别与适用场景。

#### 第 11 周：推理框架横向评测与选型

核心学习目标：建立框架选型方法论，形成体系化的推理优化认知。

必做实战：

1. 输出《主流 AI 推理框架横向评测报告》，覆盖性能、显存、易用性、适配成本 4 个维度

2. 针对延迟优先、吞吐优先、显存优先三类场景给出选型建议

周验收标准：能独立完成任意模型从训练到推理的全流程优化方案设计。

---

## 四、第三阶段：专项深耕期（第 12\-16 周）

核心原则：聚焦岗位核心竞争力，重点深耕国产 GPGPU 适配与 LLM/VLM 优化，编译器方向以理解原理 \+ 跑通 Demo 为主。

### 第 12 周：Triton 算子开发 \+ XLA 图编译

核心学习目标：掌握跨硬件算子开发范式，理解图编译器的核心优化逻辑。

核心内容：

1. OpenAI Triton 编程模型、算子开发流程、自动调优机制、ROCm 后端支持

2. XLA 编译原理：HLO IR、算子融合、图下沉、PyTorch XLA 适配

配套资源：Triton 官方教程、PyTorch XLA 官方文档、`llm-algo-leetcode` Triton 章节。

必做实战：

1. 用 Triton 实现简化版 PagedAttention Kernel

2. 对比 Triton Kernel 与 CUDA 原生 Kernel 的性能与开发效率

3. 开启 XLA 优化 PyTorch LLM 推理，测试性能收益与精度损失

周验收标准：能独立编写基础 Triton 算子，理解其跨硬件适配的核心优势。

### 第 13 周：IREE 通用 MLIR 编译器

核心学习目标：理解通用硬件编译器的设计思想，掌握 MLIR 基础概念。

核心内容：

1. MLIR 基础、Dialect 机制、Linalg 张量方言

2. IREE 编译流程、HAL 硬件抽象层、多硬件后端适配逻辑

3. 国产芯片适配 IREE 的技术路径

配套资源：IREE 官方示例仓库。

必做实战：

1. 将 PyTorch 模型通过 torch\-mlir 导入 IREE，编译到 GPU 后端并验证推理

2. 梳理 IREE 适配国产 GPGPU 的技术路径

周验收标准：能讲清 MLIR、Dialect、HAL 等核心概念，理解通用编译器的价值。

### 第 14 周：国产 GPGPU 适配方法论

核心学习目标：建立国产芯片适配的完整认知，掌握分层适配与问题排查思路。

核心内容：

1. 国产 GPGPU 生态现状：海光 DCU、寒武纪、摩尔线程等厂商适配模式

2. 适配层级划分：算子层、框架层、业务层

3. 通用适配问题：算子缺失、精度漂移、性能不达标、通信库兼容、显存管理差异

4. 海光 DCU DTK 软件栈：HIP、rocBLAS、rocFFT、RCCL、MIGraphX

配套资源：FlagOS 国产硬件插件体系、海光光合开发者社区。

必做实战：

1. 精读 FlagOS vLLM 插件源码，梳理插件化适配的核心分层

2. 输出《vLLM 适配海光 DCU 完整技术路径与风险评估报告》

周验收标准：能讲清国产 GPGPU 适配的三层架构，识别算子、通信、量化三大类核心风险。

### 第 15 周：ROCm 环境框架适配实战

核心学习目标：动手完成推理框架的 ROCm 源码编译，积累真实适配踩坑经验。

核心内容：

1. PyTorch ROCm 后端源码编译

2. 推理框架 ROCm 版本编译踩坑：算子替换、依赖库适配

3. ROCm 性能工具：rocprof、rocm\-smi、Omniperf

配套资源：vLLM ROCm 后端官方适配文档、ROCm 性能工具官方指南。

必做实战：

1. 源码编译 ROCm 版本 vLLM，跑通 Qwen\-7B 模型

2. 用 rocprof 做性能剖面，定位 DCU 环境下的推理瓶颈

3. 记录完整编译踩坑与优化文档

周验收标准：能独立完成推理框架的 ROCm 源码编译与基础性能分析。

### 第 16 周：LLM/VLM 推理深度优化

核心学习目标：掌握大模型推理的深度优化手段，完成业务场景端到端优化。

核心内容：

1. Prefill/Decode 阶段瓶颈分析、调度策略优化

2. 量化技术：AWQ/GPTQ/FP8/INT4 原理、精度损失控制

3. 推测解码、前缀缓存、长上下文优化

4. 多模态模型：ViT 图像编码器瓶颈、跨模态融合优化

配套资源：vLLM/SGLang 官方优化指南、各量化算法原论文。

必做实战：

1. 对 Qwen\-VL 多模态模型进行端到端性能优化

2. 覆盖 KV Cache 优化、量化、Prefill/Decode 调度调优三个维度

3. 实现整体吞吐提升 20% 以上，输出优化报告

周验收标准：能独立完成大模型推理的瓶颈定位与全链路优化。

---

## 五、第四阶段：实战落地期（第 17\-22 周）

核心目标：完成 3 个硬核项目，100% 覆盖 JD 关键词，形成可直接展示的作品集。代码与文档统一归档个人 GitHub。

### 项目一：高性能算子开发与跨硬件迁移（第 17\-18 周）

项目定位：底层能力证明，对应 JD「GPU Kernel 编程、CUTLASS/CK、国产芯片适配」。

项目内容：基于 CUTLASS 与 CK 分别实现 FlashAttention v2 算子，完成 CUDA 到 HIP 全流程迁移；通过 Nsight Compute/rocprof 定位瓶颈，完成分块、双缓冲、访存合并多级优化。

核心交付物：

1. CUDA 与 HIP 双版本可运行算子源码

2. 精度校验脚本与单元测试

3. 性能优化报告（优化前后对比、带宽/算力利用率分析）

4. CUDA 到 HIP 迁移踩坑文档

覆盖关键词：CUDA、HIP、CUTLASS、CK、GPU Kernel、FlashAttention、性能优化、国产 GPGPU 适配。

### 项目二：多推理引擎大模型部署与横向评测（第 19\-20 周）

项目定位：框架广度证明，对应 JD「TensorRT/PPL/ORT/vLLM/LMDeploy/AITemplate」全栈要求。

项目内容：搭建统一评测平台，完成 TensorRT、ONNX Runtime、vLLM、LMDeploy、AITemplate 五大引擎对 Qwen\-VL 多模态模型的部署适配；实现自动化压测，覆盖不同并发、长度、量化精度场景，输出完整选型报告。

核心交付物：

1. 五大引擎一键部署脚本

2. 自动化压测平台（采集延迟、吞吐、显存指标）

3. 多维度横向评测报告与业务选型建议

覆盖关键词：TensorRT、onnxruntime、vllm、lmdeploy、aitemplate、VLM、推理优化、量化。

### 项目三：国产 GPGPU 推理框架适配与系统级优化（第 21\-22 周）

项目定位：岗位精准匹配，对应 JD「国产加速芯片适配、推理框架开发、系统级优化」。

项目内容：基于 ROCm 环境模拟海光 DCU 平台，参考 FlagOS 插件架构，为 vLLM 开发轻量化硬件适配插件；实现自定义 Attention 算子注册、内存管理接口适配、RCCL 多卡通信兼容；完成端到端性能分析与瓶颈定位。

核心交付物：

1. vLLM 硬件适配插件源码

2. 海光 DCU 迁移适配方案文档

3. 性能评测报告与风险评估清单

覆盖关键词：国产 GPGPU、框架适配、系统级优化、HIP、ROCm、PyTorch、推理框架开发。

---

## 六、第五阶段：面试冲刺期（第 23\-24 周）

### （一）简历优化

1. 按 STAR 法则包装 3 个核心项目，全部量化优化收益（如「性能提升 30%」「吞吐提升 25%」）

2. 确保 JD 每条任职要求都有对应技能/项目支撑

### （二）面试题库梳理

1. 基础题：GPU 体系结构、CUDA/HIP 核心概念、推理优化通用技术

2. 框架题：各推理框架原理、优劣势、业务选型

3. 场景题：国产适配常见问题排查、性能瓶颈定位流程、业务优化方案

4. 项目深挖：每个项目的技术难点、解决方案、决策依据、踩坑经验

### （三）行业调研

海光 DCU 产品路线、生态布局、行业竞品对比；国产 AI 芯片行业现状与发展趋势。

### （四）模拟面试

针对技术面、部门经理面模拟演练，优化表达逻辑。

---

## 七、全量开源资源索引表

|类别|资源名称|地址|适用阶段|
|---|---|---|---|
|入门引路|llm\-algo\-leetcode|[https://github\.com/datawhalechina/llm\-algo\-leetcode](https://github.com/datawhalechina/llm-algo-leetcode)|全阶段|
||thorough\-pytorch|[https://github\.com/datawhalechina/thorough\-pytorch](https://github.com/datawhalechina/thorough-pytorch)|第一阶段|
||diy\-llm|[https://github\.com/datawhalechina/diy\-llm](https://github.com/datawhalechina/diy-llm)|第一、二阶段|
|C\+\+ 工程化|modern\-cpp\-tutorial|[https://github\.com/changkun/modern\-cpp\-tutorial](https://github.com/changkun/modern-cpp-tutorial)|第一阶段|
||cmake\-examples|[https://github\.com/ttroy50/cmake\-examples](https://github.com/ttroy50/cmake-examples)|第一阶段|
||googletest|[https://github\.com/google/googletest](https://github.com/google/googletest)|全阶段|
|Linux 性能|FlameGraph|[https://github\.com/brendangregg/FlameGraph](https://github.com/brendangregg/FlameGraph)|第一、三阶段|
||perf\-tools|[https://github\.com/brendangregg/perf\-tools](https://github.com/brendangregg/perf-tools)|第一阶段|
|CUDA/HIP 算子|cuda\-samples|[https://github\.com/NVIDIA/cuda\-samples](https://github.com/NVIDIA/cuda-samples)|第二阶段|
||rocm\-examples|[https://github\.com/ROCm/rocm\-examples](https://github.com/ROCm/rocm-examples)|第二、三阶段|
||HIPIFY|[https://github\.com/ROCm/HIPIFY](https://github.com/ROCm/HIPIFY)|第二阶段|
|高性能算子库|CUTLASS|[https://github\.com/NVIDIA/cutlass](https://github.com/NVIDIA/cutlass)|第二阶段|
||Composable Kernel|[https://github\.com/ROCm/composable\_kernel](https://github.com/ROCm/composable_kernel)|第二、三阶段|
||ROCm AITER|[https://github\.com/ROCm/aiter](https://github.com/ROCm/aiter)|第二、四阶段|
|推理框架|trt\-samples\-for\-hackathon\-cn|[https://github\.com/NVIDIA/trt\-samples\-for\-hackathon\-cn](https://github.com/NVIDIA/trt-samples-for-hackathon-cn)|第二阶段|
||vLLM|[https://github\.com/vllm\-project/vllm](https://github.com/vllm-project/vllm)|第二、三、四阶段|
||LMDeploy|[https://github\.com/InternLM/lmdeploy](https://github.com/InternLM/lmdeploy)|第二阶段|
||AITemplate|[https://github\.com/facebookincubator/AITemplate](https://github.com/facebookincubator/AITemplate)|第二阶段|
||PPLNN|[https://github\.com/openppl\-public/pplnn](https://github.com/openppl-public/pplnn)|第二阶段|
|AI 编译器|Triton 官方教程|[https://github\.com/openai/triton](https://github.com/openai/triton)|第三阶段|
||IREE|[https://github\.com/iree\-org/iree](https://github.com/iree-org/iree)|第三阶段|
|国产适配|FlagOS 插件体系|[https://github\.com/flagos\-ai](https://github.com/flagos-ai)|第三、四阶段|
||海光光合开发者社区|[https://developer\.sourcefind\.cn/](https://developer.sourcefind.cn/)|全阶段|

---

## 八、能力自检清单

* [ ] 熟悉计算机体系结构与 GPGPU SIMT 架构，理解 GPU 内存层次与执行模型

* [ ] 精通 C\+\+/Python，具备 Linux 下工程开发与性能分析能力

* [ ] 熟练掌握 CUDA/HIP Kernel 编程，能独立完成算子开发与性能优化

* [ ] 熟悉 CUTLASS/CK 至少一个高性能算子库

* [ ] 熟练使用 TensorRT、ONNX Runtime、vLLM、LMDeploy 中至少 3 种推理框架

* [ ] 了解 AITemplate、TGI、PPL 等其他推理框架的特点与适用场景

* [ ] 了解 Triton/XLA/IREE 等 AI 编译器原理与使用

* [ ] 深入理解 LLM/VLM/搜推广中至少一个领域的模型与优化方法

* [ ] 掌握国产 GPGPU 适配方法论，了解海光 DCU/DTK 生态

* [ ] 具备端到端性能分析与系统级优化能力

---

## 九、执行原则与避坑建议

1. 优先级原则：优先完成必做实战任务，拓展内容按需补充；所有知识点以「能跑通、能调优、能讲清」为验收标准

2. 代码优先：GPU 编程与推理优化的核心经验都来自编译报错、性能调错、环境踩坑，每天保证至少 1 小时动手

3. 重点倾斜：把最多时间留给 CUDA/HIP、vLLM、ROCm 适配、性能分析四大核心，IREE、搜推广等先掌握核心概念

4. 持续沉淀：所有踩坑记录、优化报告、项目文档统一归档 GitHub，既是简历素材也是面试一手资料

5. 弹性机制：每周预留 1 天缓冲，遇到卡壳不用硬赶进度，把问题解决透再往下走

6. 每周复盘：每周日花 30 分钟复盘知识点、踩坑点、未解决问题

## 十、市场需求驱动的能力增量（2026 最新）

结合 2026 年海光、曙光、腾讯、百川、上海人工智能实验室、AMD 等真实招聘 JD 与技术趋势调研，现有五阶段框架在「引擎广度、MoE、分布式服务、线上工程」上存在缺口。本章给出 6 个增量模块，原则上不额外大幅延长周期，通过替换深化现有周内容、扩展实战项目完成，建议在第 16 周后用 2\-3 周专项消化。

### （一）市场需求与现有方案缺口对照

|市场高频要求（JD 原文信号）|现有方案现状|增量动作|
|---|---|---|
|vLLM、SGLang、TensorRT\-LLM 至少掌握 1\-2 种|vLLM 完整，SGLang 较弱，TensorRT\-LLM 缺失|模块 1：补齐 SGLang 与 TensorRT\-LLM|
|懂 Transformer/Attention/MoE，DeepSeek 落地|MoE 仅概念提及，无专项|模块 2：MoE 推理优化专项|
|PD 分离、张量并行、线上部署|有概念，无分布式架构实操|模块 3：PD 分离与分布式推理|
|高并发、低延迟、高可靠、千卡集群|偏单机优化，缺线上服务工程|模块 4：生产级服务化与云原生|
|长上下文、KV Cache 优化|覆盖较浅|模块 5：长上下文与 KV Cache 压缩|
|FP8/FP4、Blackwell、国产替代认知|FP8 仅列举，无国产格局横向|模块 6：新一代量化与国产算力格局|

### （二）模块 1：补齐三大引擎（SGLang / TensorRT\-LLM）

#### 市场依据

腾讯、百川、上海人工智能实验室 JD 均将 vLLM、SGLang、TensorRT\-LLM 并列，要求具备源码阅读、二次开发或调优经验。

#### 学习要点

- **SGLang：**RadixAttention 前缀缓存、零开销连续批调度、结构化输出、MoE serving 优势、PD 分离支持

- **TensorRT\-LLM：**inflight batching、Paged KV Cache、自定义 Plugin、FP8/FP4、Blackwell 硬件深度优化；注意其仅部分开源、C\+\+ 栈较重

#### 开源资源

- [SGLang 仓库](https://github.com/sgl-project/sglang) / [SGLang 官方文档](https://docs.sglang.io/)

- [TensorRT\-LLM 仓库](https://github.com/NVIDIA/TensorRT-LLM)

### （三）模块 2：MoE 推理优化专项（DeepSeek 核心场景）

#### 市场依据

DeepSeek\-R1/V3、Mixtral、Qwen\-MoE 是当前推理落地最大场景，AMD 等 JD 明确要求理解 MoE 与专家并行。

#### 学习要点

- MoE 结构：专家、路由、top\-k 选择、专家负载均衡

- 专家并行 EP、Wide\-EP、EP\+TP 组合切分

- FusedMoE 内核、分组 GEMM、All\-to\-All 集合通信

- 专家分页与卸载（expert paging/offload）、解决专家负载不均与显存受限

#### 开源资源

- [vLLM MoE 实现](https://github.com/vllm-project/vllm)、[SGLang MoE 优化](https://github.com/sgl-project/sglang)

- [ROCm AITER](https://github.com/ROCm/aiter)、[FlashInfer](https://github.com/flashinfer-ai/flashinfer)

### （四）模块 3：PD 分离与分布式推理

#### 市场依据

上海人工智能实验室明确点名 PD 分离，是大规模、高并发推理的标准架构，可对 Prefill 与 Decode 独立伸缩。

#### 学习要点

- Prefill 与 Decode 阶段瓶颈差异及分离部署

- KV Cache 跨实例、跨内存层级传输与卸载

- LLM 感知请求路由，避免 KV 重复计算

- NVIDIA Dynamo 分布式推理框架的调度与编排

#### 开源资源

- [NVIDIA Dynamo 仓库](https://github.com/ai-dynamo/dynamo) / [Dynamo 文档](https://docs.nvidia.com/dynamo/)

### （五）模块 4：生产级服务化与云原生

#### 市场依据

曙光社招 JD 强调「高并发、低延迟、高可靠」，线上服务工程能力是区分单机优化与量产落地的关键。

#### 学习要点

- 容器化、Kubernetes、GPU device plugin

- KServe 推理编排：声明模型来源、运行时与资源

- HPA 基于 GPU 利用率/并发数自动扩缩容：快扩容、慢缩容、minReplicas 保证高可用

- 服务网关、SLO 指标（TTFT、ITL）、Prometheus \+ Grafana 可观测

#### 开源资源

- [KServe 仓库](https://github.com/kserve/kserve)、[Dynamo 可观测组件](https://github.com/ai-dynamo/dynamo)

### （六）模块 5：长上下文与 KV Cache 压缩

#### 市场依据

NVIDIA GTC 将超长上下文列为重点，DeepSeek MLA 是当前开源模型中显著减小 KV Cache 的代表方法。

#### 学习要点

- 注意力演进：MHA → MQA → GQA → MLA，理解 MLA 低秩联合压缩、仅缓存潜向量

- KV Cache 量化（FP8 KV）、分页与 CPU 卸载

- 稀疏注意力、block\-sparse attention，降低长序列算力开销

#### 开源资源

- [DeepSeek\-V3 技术报告（MLA 章节）](https://arxiv.org/pdf/2412.19437)

- [FlashInfer](https://github.com/flashinfer-ai/flashinfer)、[AITER](https://github.com/ROCm/aiter)

### （七）模块 6：新一代量化与国产算力格局

#### 学习要点

- FP8 混合精度与 FP8 KV Cache、Blackwell 原生 FP4 加速

- 国产算力格局：2025 年国产 AI 芯片出货约 165 万张、占比约 41%；华为昇腾出货第一，平头哥第二，寒武纪、昆仑芯并列第三

- 「七雄」认知：海光、寒武纪、摩尔线程、沐曦、天数智芯、壁仞、燧原；海光走通用 GPGPU 路线，强在生态兼容

#### 开源资源

- [TensorRT\-LLM 量化实践](https://github.com/NVIDIA/TensorRT-LLM)、[海光光合社区](https://developer.sourcefind.cn/)

### （八）增量能力融入时间线

|增量模块|建议时间|融入方式|
|---|---|---|
|模块 1 引擎补齐|第 9 周扩展|与 vLLM 同期部署 SGLang，TensorRT\-LLM 做对照|
|模块 2 MoE|第 16 周深化|用 DeepSeek 小尺寸 MoE 模型做 EP 与 FusedMoE 调优|
|模块 3 PD 分离|第 14\-15 周|用 Dynamo 跑通 Prefill/Decode 分离最小示例|
|模块 4 服务化|第 16 周后 1 周|K8s \+ KServe 部署 vLLM，配 HPA 与监控面板|
|模块 5 长上下文|第 16 周|结合 MLA 与 FP8 KV 做显存对比实验|
|模块 6 量化与格局|穿插/周末|行业认知为主，量化实验并入模块 2、5|

### （九）建议新增第 4 个实战项目

**项目名称：**基于 Dynamo 的 DeepSeek MoE 分布式推理与云原生服务部署。

**核心内容：**在 ROCm/CUDA 环境部署 DeepSeek 小尺寸 MoE 模型，完成专家并行与 FusedMoE 调优；通过 Dynamo 实现 PD 分离与 KV 传输；在 K8s \+ KServe 上发布服务，配置 HPA 与 Prometheus 监控，输出 SLO（TTFT/ITL）与吞吐、成本（TCO）报告。

**覆盖关键词：**MoE、专家并行、PD 分离、Dynamo、K8s、KServe、可观测、自动扩缩容、FP8、生产级服务。

### （十）增量能力自检

- 能讲清 vLLM、SGLang、TensorRT\-LLM 三者设计差异与选型

- 能独立完成 MoE 模型的专家并行部署，解释 All\-to\-All 与 FusedMoE 优化点

- 能用 Dynamo 跑通 PD 分离，说明 KV Cache 传输路径

- 能在 K8s 上发布推理服务并配置基于 GPU 指标的自动扩缩容与监控

- 能讲清 MLA/GQA/MQA 区别，以及 FP8 KV、FP4 对显存与吞吐的影响

- 能说出国产主要算力厂商格局与海光 DCU 的路线定位

---

> （注：部分内容由豆包工作 AI 生成）
