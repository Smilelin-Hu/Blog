# 从 Common Crawl 到可训练语料

![从 Common Crawl 到可训练语料](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l31_01.png)

## 1. 项目目标与证明边界

这个项目把公开网页抓取的原始 WARC 记录转换成可发布、可删除、可复现的 Train-ready 语料。交付物不是一个“清洗后的 JSONL”，而是一条能够回答来源、许可、解析、过滤、去重、隐私、质量、分片和发布决策的数据供应链。任何文档被保留或删除，都有稳定身份、阶段状态、原因码和统计证据。

机制实验可在 CPU 与少量本地样本上运行，用于证明内容寻址、规则顺序、MinHash 候选、确定性分片和 Manifest 重放。真实运行路径使用 Common Crawl 索引与 WARC Range Request 处理代表性分片；没有网络、对象存储或足够磁盘时输出结构化 `skipped`，不把内置样例包装成真实抓取。小样本只能证明机制和管线正确，不能证明互联网级语言覆盖、重复率、吞吐或版权结论。

## 2. 范围、输入与输出

输入包括抓取快照标识、允许域与禁止域规则、许可与退出策略、WARC 路径清单、解析器版本、过滤 Recipe、PII 策略、去重阈值、质量模型版本、目标语言和发布 Token 预算。每项配置都进入不可变 Recipe，而不是散落在脚本参数和人工记录中。

输出包括原始引用清单、规范文档、阶段决策日志、重复簇、隐私命中、质量分数、Train-ready 分片、全局 Manifest、数据卡和撤回索引。训练文件只承载消费所需字段；审计证据保存在控制平面资产中，二者通过 `document_id`、`release_id` 和内容哈希连接。

项目不尝试证明某个网页可用于任意商业用途。来源许可、robots、服务条款、版权与隐私判断需要组织法务和治理流程。工程系统负责保存证据、执行版本化策略、阻断未知来源和传播撤回，而不是用一个“公开可访问”布尔值替代授权判断。

## 3. 总体架构

数据面依次经过 Snapshot Resolver、WARC Fetcher、Record Decoder、HTML Parser、Canonicalizer、Boundary Cleaner、Language Router、Quality Filter、PII Scanner、Exact Dedup、Fuzzy Dedup、Benchmark Decontamination、Tokenizer、Sharder 和 Publisher。每个算子读取不可变输入资产，写入新资产与逐文档决策，不在原地覆盖。

每个转换都保存输入身份、配方与拒绝原因。

控制面包含 Source Registry、Recipe Registry、Run Controller、Asset Catalog、Lineage Store、Policy Engine、Metric Store 和 Release Gate。运行控制器把一个 Recipe 展开为 DAG，阶段提交使用输入 Manifest 哈希、算子版本和输出 Manifest 哈希。失败重试复用逻辑 Stage ID，物理 Attempt 独立记录，只有一个 Attempt 能条件提交。

删除面使用 Tombstone Registry。收到域、URL、文档哈希或主体标识的合法撤回后，先解析受影响源文档，再沿血缘定位规范文档、重复代表、训练分片、Release 和 Checkpoint。未来消费立即阻断，已发布资产生成新版本，模型影响进入独立治理流程。删除不能仅在最新 JSONL 执行字符串搜索，因为规范化、去重代表选择和 Packing 已经改变物理形态。

## 4. 目录与资产合同

建议仓库目录如下：

```text
commoncrawl_pipeline/
  configs/sources.yaml
  configs/recipes/v1.yaml
  schemas/source_record.json
  schemas/document.json
  schemas/decision.json
  src/resolve_snapshot.py
  src/fetch_warc.py
  src/parse_html.py
  src/filter_document.py
  src/deduplicate.py
  src/publish_release.py
  tests/fixtures/
  tests/test_replay.py
  artifacts/manifests/
  artifacts/metrics/
  artifacts/data_cards/
```

源记录至少包含 `source_id`、抓取快照、WARC 路径、记录偏移、长度、URL、抓取时间、响应状态、MIME、Payload 哈希和策略版本。规范文档包含稳定 `document_id`、父源记录、标题、正文、语言、结构块、规范化版本和内容哈希。决策记录包含阶段、动作、原因码、阈值、算子版本、时间和证据摘要。所有标识都由规范序列化后的确定字段计算，不能使用随机 UUID 替代可重算身份。

Release Manifest 列出 Recipe、上游资产、Tokenizer、Shard 算法、随机种子、每个分片的哈希、文档数、有效 Token、原因统计和数据卡位置。训练恢复只接受 Manifest 中登记且哈希匹配的分片；目录里多出一个文件不能自动进入训练。

## 5. 实施步骤

### 5.1 注册来源与快照

先冻结 Common Crawl 快照和 WARC 路径范围，再为来源域绑定许可、地域、敏感级别、抓取预算与退出方式。未知策略进入隔离，不允许“先抓后补”。对索引查询结果保存原始响应哈希，保证未来能说明路径清单从何而来。

### 5.2 Range Fetch 与原始证据

使用 WARC 偏移和长度做 Range Request，响应经过长度、哈希、记录头和 Payload 校验后写入内容寻址缓存。HTTP 重试以源记录身份幂等，限制并发、带宽和退避。缓存命中仍核对哈希；缓存键必须包含快照、路径、偏移和长度，避免不同记录串线。

### 5.3 解析与正文边界

规范文本仍需能够定位原始证据。

解压 WARC，解析 HTTP 响应，再按 MIME 路由 HTML、纯文本、PDF 或拒绝路径。HTML 保留 DOM 证据、标题、段落、列表与代码块，删除导航、脚注和广告时记录规则。解析失败不是空文档，应保存 `parse_error` 类别与样本，用于版本回归。

### 5.4 规范化与语言路由

Unicode 规范化、控制字符、空白折叠、URL 标准化和不可见字符处理必须有版本。原文哈希与规范文哈希同时保存。语言识别输出分布与置信度，低置信和混合语言进入专门桶，不用单一 Top-1 标签硬切。

### 5.5 质量、隐私与安全

规则层检查正文长度、字母比例、重复行、模板密度、链接密度和异常字符；模型层输出质量、领域、难度和风险分数。PII 扫描区分邮箱、电话、密钥、地址与高风险身份信息，动作可以删除字段、局部遮盖、整文档隔离或升级人工复核。所有分数保留模型版本与校准窗口。

### 5.6 去重与去污染

代表选择必须兼顾质量、用途与确定性。

先按规范内容哈希精确去重，再用 Shingle、MinHash 与 LSH 产生模糊候选，对候选做 Jaccard 复核并形成连通簇。代表选择综合来源策略、质量、长度和抓取时间，并保存被代表关系。基准去污染使用题面、答案、段落和子串多视图匹配；命中后保留基准版本、匹配位置和动作，不能只保存一个污染率。

### 5.7 Tokenize、分片与发布

任何硬失败阻止版本可见。

Tokenizer 版本固定后计算有效 Token，按稳定哈希映射分片，再在分片内用固定种子排列。发布门禁检查输入覆盖、Schema、原因守恒、重复簇、PII 红线、污染红线、Token 预算、分片哈希和重放一致性。通过后写就绪标记；消费者不读取半完成目录。

## 6. CPU 机制实验

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `projects/project-01/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python projects/project-01/run.py
python projects/project-01/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

下面的程序用内置文档演示规范身份、精确去重、近似候选、原因码和稳定分片。它不替代生产 HTML 解析、PII 模型和互联网规模 LSH，但可以作为 CI 中的小型正确性测试。

```python
import hashlib
import json
import re
from collections import defaultdict

DOCS = [
    {"url": "https://a.example/1", "text": "Reliable data needs lineage and replay evidence."},
    {"url": "https://b.example/2", "text": "Reliable  data needs lineage and replay evidence!"},
    {"url": "https://c.example/3", "text": "Contact admin@example.org for the private build token."},
    {"url": "https://d.example/4", "text": "A distinct article about deterministic sharding."},
]

def canonicalize(text):
    text = re.sub(r"\s+", " ", text.strip().lower())
    return re.sub(r"[^a-z0-9@. ]", "", text)

def stable_id(value):
    return hashlib.sha256(value.encode()).hexdigest()

def shingles(text, width=3):
    words = text.split()
    return {" ".join(words[i:i + width]) for i in range(max(1, len(words) - width + 1))}

def jaccard(left, right):
    return len(left & right) / max(1, len(left | right))

def run(docs, shards=4):
    output, exact = [], {}
    for item in docs:
        canonical = canonicalize(item["text"])
        doc_id = stable_id(canonical)
        reason = "keep"
        if re.search(r"[\w.+-]+@[\w.-]+", canonical):
            reason = "reject_pii_email"
        elif doc_id in exact:
            reason = "reject_exact_duplicate"
        exact.setdefault(doc_id, item["url"])
        output.append({
            "document_id": doc_id,
            "url": item["url"],
            "canonical": canonical,
            "decision": reason,
            "shard": int(doc_id[:8], 16) % shards,
        })
    kept = [x for x in output if x["decision"] == "keep"]
    fuzzy = []
    for i, left in enumerate(kept):
        for right in kept[i + 1:]:
            score = jaccard(shingles(left["canonical"]), shingles(right["canonical"]))
            if score >= 0.7:
                fuzzy.append({"left": left["document_id"], "right": right["document_id"], "score": score})
    return {"documents": output, "fuzzy_candidates": fuzzy}

first = run(DOCS)
second = run(list(reversed(DOCS)))
assert sorted((x["document_id"], x["shard"]) for x in first["documents"]) == sorted(
    (x["document_id"], x["shard"]) for x in second["documents"]
)
print(json.dumps(first, ensure_ascii=False, indent=2))
```

验收时应看到相同规范内容获得相同身份和分片，邮箱文档被原因码隔离，输入顺序变化不改变身份与分片。近似候选是否出现取决于 Shingle 阈值，生产实现还要测候选召回与精确复核误报。

## 7. 真实数据运行路径

真实路径先做一个固定快照、固定域和固定记录数的 Pilot，再扩大规模。运行前验证网络、磁盘、WARC 库与对象存储；条件不足时输出结构化状态：

```python
import importlib.util
import json
import os
import shutil

requirements = {
    "warcio": importlib.util.find_spec("warcio") is not None,
    "network_enabled": os.environ.get("ALLOW_COMMONCRAWL_NETWORK") == "1",
    "disk_at_least_100gb": shutil.disk_usage(".").free >= 100 * 1024 ** 3,
}
if not all(requirements.values()):
    print(json.dumps({"status": "skipped", "reason": "real_data_requirements_unavailable", "checks": requirements}))
else:
    print(json.dumps({"status": "ready", "snapshot": os.environ.get("CC_SNAPSHOT", "must_be_explicit")}))
```

Pilot 至少覆盖成功 HTML、非 HTML、压缩损坏、字符集异常、重定向、模板页、长文、短文、混合语言、重复、PII 和基准命中。扩大规模前用固定 Golden Set 比较解析块、正文哈希和原因码；任何解析器或规则升级都生成差异报告，而不是直接覆盖旧 Release。

## 8. 指标、阈值与验收

核心指标包括请求成功率、WARC 校验失败率、解析成功率、正文保留率、语言置信度、规则删除率、模型质量分布、PII 命中与动作分布、精确重复率、模糊候选召回、簇大小、污染命中、有效 Token 比例、每百万文档成本和每十亿有效 Token 成本。

逐阶段守恒比最后一个文件大小更能说明完成度。

阈值不能脱离样本。重复召回率使用人工或合成标注对，PII 报告每类精确率与召回率，质量门禁使用领域和语言切片。发布必须满足文档状态守恒：输入总数等于保留、拒绝、隔离和技术失败之和；每个技术失败有可重试身份；每个保留文档能回溯源记录和全部决策。

最终验收运行两次相同 Recipe。允许墙钟与物理文件布局变化，但 Release Manifest、逻辑文档、原因统计、分片成员和内容哈希必须一致。然后改变一个规则版本，差异只出现在受该规则影响的文档，并形成新 Release。最后提交一条 Tombstone，确认未来读取被阻断、派生 Release 可定位且影响报告完整。

## 9. 演示脚本

比较删除原因与分布，不只展示更高保留率。

演示从一个文档 ID 开始，依次展示源 WARC 坐标、原始 Payload 哈希、解析块、规范化差异、每阶段决策、重复簇、训练分片与数据卡。随后重放相同 Recipe 证明输出一致，再升级一个过滤规则展示版本差异，最后执行撤回并展示影响传播。演示不以“跑完脚本”为结束，而以每个结论都有可查询证据为结束。

## 10. 排障手册

解析保留率突降时，先按 MIME、域、字符集、WARC 状态和解析器版本切片，检查源分布变化与代码回归。重复率突升时，区分新增模板、规范化过强、哈希错误与 LSH 参数变化。Token 成本升高时，分解抓取重试、解析 CPU、Shuffle、模型评分、对象存储和无效文档比例。

分片不一致时，不要先重跑覆盖；冻结两次 Manifest，比较输入清单、规范序列化、哈希实现、种子、并行归并顺序和库版本。PII 漏检事故发生后，冻结相关 Release，保存命中证据，升级扫描器并沿血缘重扫；不要只修最新数据而忽略历史 Checkpoint 影响。

## 11. 最终交付清单

交付可执行配置、Schema、机制测试、真实 Pilot 命令、Golden Set、阶段 Manifest、原因字典、指标快照、数据卡、Tombstone 演练、成本报告和已知限制。所有命令从空目录可重建；所有外部依赖有版本；所有真实结果带硬件、软件、快照、样本范围和采集口径。做到这些，项目才从一次性清洗脚本升级为可运营的数据产品。

## 12. 生产评审十二问

### 12.1 来源是否真的被冻结

评审随机抽取一个训练文档，必须能还原快照、WARC 路径、偏移、长度、URL、抓取时间、响应头与 Payload 哈希。若只能找到当前网页或一个域名，就无法证明训练时消费的原始字节，也无法在网页变化后重放。

### 12.2 许可未知怎样处置

示例数据可演示流程，不能替代真实来源授权。

未知不是允许。Source Registry 应把缺少许可、地域、退出或用途合同的来源路由到隔离，发布门禁按策略版本阻断。人工例外需要负责人、范围、依据和到期时间，不能在配置中永久写一个无来源的 `allow=true`。

### 12.3 解析升级怎样比较

新旧解析器在固定 Golden Set 和分层随机样本上并行运行，比较正文块、标题、代码、语言、长度和失败原因。差异按域与 MIME 聚合，并抽查新增与丢失内容。通过后生成新 Asset 版本，旧解析结果仍可查询。

### 12.4 清洗规则是否过强

删除率上升不代表质量提升。对每条规则保存触发位置和删除片段，检查语言、领域、长度与来源切片，特别关注少数语言、代码和结构化文档。用下游小规模训练或代理指标验证边际价值，不能只以文件变小验收。

### 12.5 去重代表怎样选

重复簇代表选择要确定且可解释，综合来源策略、质量、完整度、时间和许可。代表被撤回时，不能自动让原本低质量或无许可成员复活；应重新执行当前代表策略和全部发布门禁，形成新版本。

### 12.6 PII 漏检怎样止损

冻结受影响 Release 的新租约，保存扫描器版本和漏检样本，修复后沿血缘重扫规范文档与派生分片。输出受影响训练 Run 和 Checkpoint，交由治理流程决定回滚或再训练。只删除对象存储中的一行不能完成模型影响处置。

### 12.7 污染率怎样解释

污染报告要给基准版本、匹配视图、阈值、命中位置和任务切片。高召回规则可能删除合法共享知识，低召回规则会遗漏改写。用合成正负对和人工抽样估计误差，并明确去污染只覆盖已登记基准。

### 12.8 并行度变化是否可复现

分别用不同 Worker 数运行同一小 Release，逻辑文档、决策、簇、分片成员和 Manifest 哈希应一致。若物理文件顺序变化，发布层必须规范化。任何依赖 Task 完成顺序的代表选择或随机采样都会在扩容后改变数据。

### 12.9 分片倾斜怎样处理

稳定哈希保证成员可重算，却不自动保证 Token 均衡。评审同时检查每片文档数、Token、长文和域分布；必要时使用两级桶或带容量约束的确定性分配。调整算法必须产生新 Shard 版本并验证训练恢复语义。

### 12.10 失败重试是否守恒

允许重算，不允许生成无法解释的重复可见版本。

统计源记录总数与成功、永久拒绝、隔离、可重试失败和技术作废必须守恒。重试只新增 Attempt，不新增逻辑输入。达到上限的失败进入明确终态和死信资产，不能从分母消失来美化处理成功率。

### 12.11 成本是否包含无效工作

抓取 404、损坏记录、解析失败、模型过滤、重复删除、PII 隔离和重跑都消耗 CPU、网络与存储，必须留在每十亿有效 Token 成本的分子。优化前后同时比较质量和有效 Token，避免用更激进删除制造虚假低成本。

### 12.12 发布能否安全撤销

消费者通过 Release 身份读取，不能直接追 `latest` 目录。撤回时先阻断新租约、保留已有 Run 证据，再生成替代 Release 并按组织策略处理活动训练。演练要覆盖训练正处于分片中间的情况，明确继续、暂停或从新版本恢复的边界。

## 写在最后

语料供应链跑通后，下一步是把它升级为可版本化、可追责的控制面。下一篇：[可版本化、可追责的数据湖与血缘控制面](/source/AI-Infra/5-数据工程与后训练/32-可版本化-可追责的数据湖与血缘控制面)。