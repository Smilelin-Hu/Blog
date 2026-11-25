# Grammar：受约束 JSON 输出与逐请求校验

结构化输出靠约束解码（grammar/JSON schema）保证格式合法：后端在解码期按 schema 掩码非法 token。本课核验约束真实下发到后端（而非仅客户端事后过滤）、每个响应都被解析校验、非法输出必须判失败——三者缺一，「schema 通过率」就可能是事后修补出来的假数字。

## 1. 机制要点

- **约束下发**：schema 必须进入后端解码路径（grammar/掩码），客户端事后 parse 只能发现错误不能防止错误。
- **逐请求校验**：每个响应独立 parse + schema 校验；抽样校验会漏掉间歇性非法输出。
- **失败语义**：非法输出判 acceptance 失败，不允许「parse 失败但算通过」的口径。

## 2. 实验闭环

```bash
python lesson/12-structured-output/run.py --check-only
python lesson/12-structured-output/run.py --output results/lesson-12-fixture.json
python lesson/12-structured-output/run.py --real --endpoint http://serving:8000 --schema schema.json \
  --output results/gpu_result.json
```

- **输入**：serving 端点、JSON schema、请求集。
- **输出**：request records、schema pass rate、parse failures。
- **验收**：schema 下发到后端；每个响应都被解析；非法输出判失败。

## 3. 判读纪律

- 通过率要附 parse failures 明细：只有 pass rate 没有失败明细的报告不可复算。
- 约束生效要有反证：去掉 schema 的对照应出现非法输出，证明约束真实在起作用。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

结构化输出与约束解码的机制展开见[Structured Output Serving：Grammar、FSM 与 XGrammar](/source/AI-Infra/3-大模型推理优化工程/13-StructuredOutputServing-Grammar-FSM与XGrammar)；本课聚焦逐请求校验的实验口径。