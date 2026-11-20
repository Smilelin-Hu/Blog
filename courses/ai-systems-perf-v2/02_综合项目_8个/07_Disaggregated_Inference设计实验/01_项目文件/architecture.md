# Prefill/Decode解耦架构说明

## 目标与SLO

记录目标TTFT、TPOT、Goodput、成本和故障恢复时间。

## 数据路径

Client → Router → Prefill Pool → KV Transfer → Decode Pool → Client。

## 容量与拓扑

记录Prefill/Decode副本数、GPU型号、NUMA、PCIe/NVLink、网络有效带宽和KV传输预算。

## 路由与背压

明确会话亲和、队列上限、Admission Control、超时、重试和过载降级。

## 观测与回退

最少采集两阶段队列、服务时间、KV字节、传输延迟、错误率和单体模式回退条件。
