# P/D解耦API契约

## Prefill请求

```json
{"request_id":"req-0001","model":"Qwen/Qwen2.5-0.5B-Instruct","input_token_ids":[1,2,3],"max_output_tokens":64}
```

## Prefill响应

```json
{"request_id":"req-0001","kv_handle":"kv:req-0001:1","prompt_tokens":3,"expires_at_ms":60000}
```

## Decode请求

```json
{"request_id":"req-0001","kv_handle":"kv:req-0001:1","max_output_tokens":64}
```

## 语义要求

`request_id`必须幂等；KV句柄必须包含版本并设置过期时间；重试不得重复扣费或生成多条并行会话。
错误至少区分容量拒绝、KV不存在、KV过期、模型版本不一致、传输失败和Decode超时。
