# GPU 能耗、功耗墙与数据中心效率

「能耗」在 01/23/28/36 的指标清单里只是并列项；本文给它独立的测量与取舍框架：从芯片功耗墙到设施 PUE，再到每 Token 能耗与碳口径。工程纪律不变——先声明测量边界，再谈优化。

## 1. 测量层级：从 NVML 到电表

- **芯片级**：NVML/DCGM 的 power.draw 与能量计数器；注意板级与芯片级口径差（显存、VRM 损耗是否计入）。
- **整机级**：BMC/IPMI 整机电源，含 CPU、内存、风扇、PSU 损耗。Epoch AI（2025）的口径：GPU 约占 AI 数据中心峰值功率的 40%，其余是冷却、网络、存储与闲置——只盯 GPU 读数会系统性低估。
- **设施级**：PUE = 设施总功率 / IT 功率；风冷典型 1.3–1.6，液冷 1.1–1.2 档。
- **J/token**：$\text{J/token} = \int P\,dt / N_{tokens}$。MLPerf Power 方法学区分墙测与计数器估算；任何能效数字必须声明负载率、SLO 与测量边界，否则不可比。

## 2. 功耗墙与 throttling

- 杠杆：power cap（`nvidia-smi -pl`）、时钟上限；throttle reasons 区分 sw power cap 与 thermal。
- **训练**：功耗与吞吐常呈亚线性——降 5% 功率可能只丢 2% 吞吐，能耗最优工作点不在满功率；用单变量扫描找 J/step 最低点。
- **推理 decode**：memory-bound、算力单元闲置，power cap 效果有限。2026 年《The Illusion of Power Capping in LLM Decode》指出：功率读数下降不等于 J/token 改善——吞吐下降改变了分母，账面「省电」可能是幻觉。prefill compute-bound 才敏感。
- **预测性节流**：throttLL'eM（HPCA'25）利用 SLO slack 预测性降频，把「延迟裕量」换成能耗，是在线 serving 的可行杠杆。

## 3. 每 Token 能耗的优化杠杆

| 杠杆 | 机制 | 口径提醒 |
|---|---|---|
| batching/利用率 | 摊薄闲置功率 | 低负载率下 J/token 恶化主因 |
| 量化/KV 压缩 | 降带宽能量 | 与 37 联动，精度门禁同守 |
| PD 分离 | prefill/decode 各跑最优工作点 | 呼应主题三 27 |
| 投机解码 | 算力换带宽 | 能耗账随接受率变化 |
| 冷却/余热回收 | 降 PUE | 设施侧，非软件杠杆 |

软件优化本身就是能耗杠杆：Crusoe（2026）同硬件下调优推理栈，每输出 token 能耗降 26.9%。TokenPowerBench（AAAI'26）一类基准把跨模型/跨硬件的能效测量标准化，选型时可引用其口径。

## 4. 碳口径与容量规划

- carbon = 能耗 × 电网碳强度（时变、地域变）；carbon-aware 调度把作业移到低碳时段/区域，用延迟换碳，需声明 SLO 代价。
- 容量规划先算功率：机架功率密度决定单架 GPU 数（风冷 10–20 kW/架 vs 液冷 40–100+ kW/架），**功率是先于算力的第一约束**；B200 一代整机架方案即由此驱动。
- 验收：J/token 仪表盘（负载率、SLO、边界三声明）；power cap 单变量实验；PUE 用实测而非铭牌。

## 写在最后

下一个主题：[主题三 大模型推理优化工程](/source/AI-Infra/3-大模型推理优化工程/README)。