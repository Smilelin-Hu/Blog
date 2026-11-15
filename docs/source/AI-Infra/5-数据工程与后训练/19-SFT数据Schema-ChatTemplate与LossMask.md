# SFT 数据 Schema、Chat Template 与 Loss Mask

## 1. 本文要解决的工程问题

一条对话在页面上看起来正确，模板渲染后却把 system、user 或 padding Token 计入 Loss；训练可以收敛，但模型学到的目标已经变了。

本文围绕一个可执行判断展开：怎样保证 SFT Schema、Chat Template、Loss Mask 与训练目标完全一致？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![SFT 数据 Schema 与 Loss Mask](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l19_01.png)

## 2. 本文交付物与判定标准

本文的核心决定是：把 SFT Schema、Chat Template、角色边界、截断策略和 Loss Mask 放到同一套黄金样本测试里。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：每种样本类型都能展示渲染文本与逐 Token 标签，数据集统计有效监督 Token 和被截断回答比例。

围绕“SFT 数据 Schema、Chat Template 与 Loss Mask”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“SFT 数据 Schema、Chat Template 与 Loss Mask”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

Loss Mask 测试不评判回答事实性、风格或安全性，这些需要独立数据与评测门禁。

### 3.1 业务背景与失败模式

本文讲解监督微调数据如何从业务样本变成真正参与梯度的 Token。表面上，SFT 数据只是 Prompt 与 Answer 或一组 Messages；工程上，任何 Chat Template、特殊 Token、角色边界、截断、Packing 与 Loss Mask 的微小错误，都可能让训练目标发生根本变化，而且训练仍然能正常运行、Loss 仍然会下降。

这类问题比显式崩溃更危险。把 User Token 计入 Loss，模型会学习复述提问；EOS 缺失会让生成不易停止；多轮对话只监督最后一轮与监督全部 Assistant 轮次会形成不同能力；工具调用 JSON 被截断，训练器可能把不完整结构当正确答案；Packing 若跨样本注意力或 Mask 边界错误，会产生数据泄漏和无效梯度。

本文建立从原始 SFT Sample、规范 Messages、模板渲染、Tokenization、截断、Packing、Label 与 Loss Mask 到训练 Batch 的完整契约。重点不是背诵某个框架 API，而是能够用可执行测试证明“哪些 Token 正在被训练、为什么”。

### 3.2 学习目标与能力清单

完成后应当能够：

1. 区分 Text、Prompt—Completion、Messages、多轮、Tool Calling、结构化输出和多模态 SFT Schema。
2. 设计一个规范中间表示，把来源 Schema 与模型模板解耦。
3. 解释 Chat Template、Tokenizer、特殊 Token 和模型权重为什么必须绑定版本。
4. 正确构造 Completion-only、Assistant-only、全序列和分段加权 Loss Mask。
5. 处理多轮对话、System、Tool Call、Tool Result、Thinking 与 Final Answer 的监督边界。
6. 设计截断策略，避免只保留开头、切断角色、工具调用或答案。
7. 实现 Packing 并验证 Sample Boundary、Position、Attention 与 Label Shift。
8. 检测零监督 Token、重复 BOS/EOS、未知特殊 Token、模板漂移和数据泄漏。
9. 通过机制实验逐 Token 展示渲染、Mask、截断和 Packing。
10. 通过真实 CUDA 实验在本地 Hugging Face Causal LM 上比较全序列与 Assistant-only 监督；缺少本地模型或 CUDA 时返回 `skipped`。

### 3.3 实验准备与责任边界

需要理解 Causal Language Modeling、Token、Cross Entropy 与基本 Python。机制实验使用标准库实现字符级教学 Tokenizer，目的是让每个边界可见；真实训练路径依赖 PyTorch 与 Transformers，并要求通过 `--model-path` 指向本地已有 Causal LM，不在脚本中静默联网下载。

推荐使用 0.5B 到 1.5B 量级、本地许可证允许实验的模型，在单张可用 CUDA GPU 上使用小 Batch、梯度累积与可选 LoRA。本文不会把 Tiny 模型短训练结果写成模型能力结论，只验证训练语义、吞吐、显存和 Loss 组成。没有 CUDA、模型或依赖时必须输出结构化 `skipped`。

## 4. SFT 样本怎样变成训练 Token

### 4.1 SFT 的数学对象

对 Token 序列 $x_1,\ldots,x_T$，Causal LM 最常见目标是预测下一个 Token：

$$\mathcal{L}=-\frac{1}{\sum_t m_t}\sum_{t=1}^{T-1}m_{t+1}\log p_\theta(x_{t+1}\mid x_{\le t})$$

$m_t$ 是 Loss Mask。它决定位置 $t$ 的目标 Token 是否贡献梯度。输入上下文即使 Mask 为零，仍然参与前向并影响后续预测；Mask 不是把 Prompt 从模型输入删除，而是不给 Prompt Token 自身计算监督损失。

Labels 在多数实现中与 Input IDs 同长度，训练函数内部把 Logits 向左、Labels 向右 Shift。需要忽略的位置通常写为 `-100`。若数据预处理已经手工 Shift，Trainer 又 Shift 一次，会错位预测。

Loss 归一化分母也很重要。按有效 Token 求平均与先按样本平均再按 Batch 平均，会给长短响应不同权重。分布式训练还要确认跨 Rank 聚合使用全局有效 Token，避免每卡长度差异产生偏权。

### 4.2 全序列与 Completion-only

全序列 Loss 让模型学习 Prompt 与 Response 的每个 Token。对纯文本持续预训练合理；对指令微调，Prompt 通常是条件而非目标。若把 User 内容计入 Loss，模型会花计算学习用户分布，甚至在对话中生成 User 角色。

Completion-only 只监督当前答案部分，适用于单轮 Prompt—Completion。它要求准确找到 Prompt 结束与 Completion 开始的 Token 边界。不能先分别 Tokenize Prompt 和 Completion 再简单拼接并假设结果等于整体 Tokenize，因为某些 Tokenizer 的边界合并、前导空格与特殊 Token 会改变编码。

稳妥方法是在统一模板渲染时生成字符或片段 Span，再通过支持 Offset Mapping 的 Tokenizer 映射；或使用模板原生的 Assistant Mask 功能；如果只能通过特殊标记定位，必须验证标记在所有输入中唯一并以预期 Token 序列出现。

### 4.3 Assistant-only 与多轮对话

多轮对话可能有多个 Assistant Turn。Assistant-only 通常监督所有 Assistant 内容，User、System、Tool Result 和角色控制 Token 不监督。另一种策略只监督最后 Assistant Turn，用于把前面对话作为示例上下文但只优化当前回答。

两种策略不能只用“找到最后一个 Assistant 标记”隐式决定。Dataset Schema 或 Training Recipe 应明确 `supervised_turns=all_assistant`、`last_assistant` 或具体 Turn ID。多轮数据若前面 Assistant 回答质量较低，全部监督会传播错误；只监督最后一轮又浪费高质量历史答案。

角色控制 Token 是否监督需单独决定。很多模板把 `<|assistant|>` 或 Header Token 放在 Assistant Span 外，只监督正文；有些训练希望模型学会正确生成角色终止标记，会监督 Assistant 结束符。边界测试必须逐 Token 展示。

### 4.4 数据 Schema 的多样性

常见原始形式包括单字段 `text`、`prompt/completion`、`instruction/input/output`、OpenAI 风格 `messages`、`conversations`、`chosen/rejected`、工具调用、图片加文本和领域自定义字段。直接让训练代码支持所有形式会形成大量条件分支。

建议先转换为规范 Sample。最小字段包括稳定 `sample_id`、Source 与父 Document、Messages、目标 Turn、工具定义、附件引用、质量与能力标签、Schema Version。原始字段保留在血缘层，不要求全部复制进训练 Shard。

规范化不是把所有任务转成一段 Text 后丢失角色。Messages 中每个 Content Part 保留类型、原始顺序、可监督属性和结构 ID。模板渲染是后续派生步骤，可随目标模型重建。

### 4.5 规范 Message 中间表示

一条 Message 至少有 `role`、`content` 和稳定 `message_id`。Content 可以是文本，也可以是类型化 Parts：Text、Image Reference、Audio、Tool Call、Tool Result、Structured Object。把所有内容强制字符串化会丢失边界和验证能力。

Tool Call 应包含调用 ID、工具名与参数对象，Tool Result 引用调用 ID。这样可以验证每个结果有对应调用、顺序正确、并发调用没有串线。只保存渲染后的 JSON 字符串难以区分原始参数与转义问题。

规范层还应标记 `supervision`。值可以是 `target`、`context`、`ignore` 或带权重。它描述数据策划意图，最终 Token Mask 由模板与 Tokenizer 解释。两层分开可以发现“策划说监督，但截断后没有目标”的问题。

### 4.6 Chat Template 的职责

Chat Template 把规范 Messages 变成模型训练与推理使用的序列，决定角色 Header、分隔、BOS、EOS、换行、工具声明与 Generation Prompt。它不是展示层格式，而是模型学习协议。

训练与推理模板不一致会导致分布偏移。训练把 Assistant Header 写成一种 Token 序列，服务端使用另一种，模型可能降低遵循与停止表现。Gateway、推理引擎和训练器应从同一模板版本生成或运行等价测试。

Template Version 应绑定模板文本摘要、Tokenizer Version、特殊 Token 映射和渲染库版本。只记录模型名称不够，因为同一权重可被不同模板包装。修改一个换行也可能改变 Token 边界。

### 4.7 `add_generation_prompt` 的含义

推理时常需要在对话末尾添加 Assistant 起始标记，告诉模型接下来生成 Assistant 内容。训练样本已经包含目标 Assistant Message 时，通常不应再额外添加空的 Generation Prompt，否则会出现重复 Header 或多余结尾。

构建 Prompt-only 输入用于在线生成时，应启用适合模型的 Generation Prompt；构建完整训练文本时根据模板契约关闭。代码不能在所有路径固定同一布尔值。

测试包含三种情况：最后一条是 User、最后一条是 Assistant、最后一条是 Tool Result。逐一检查渲染末尾与推理服务一致。工具模型可能需要 Tool Result 后重新开启 Assistant，与普通 User 末尾不同。

### 4.8 BOS、EOS 与 Padding

BOS 表示序列开始，EOS 表示一个生成单元结束，Padding 用于对齐 Batch。不同模型可能没有 BOS、共享 EOS 与 Padding，或使用多个结束 Token。不要用通用假设覆盖模型配置。

重复 BOS 常见于模板显式写入 BOS 字符串，同时 Tokenizer 调用又自动添加。重复 EOS 可能让模型过早停止或浪费监督；缺少 EOS 让模型不学习何时结束。测试应检查最终 ID 序列，而不仅看可读字符串。

若把 EOS 作为 Padding Token，Attention Mask 与 Label 必须确保 Padding EOS 不贡献 Loss，否则长短样本会训练大量虚假结束。真实回答结尾 EOS 应监督，填充位置 EOS 应忽略；两者 Token ID 相同，语义由 Mask 区分。

### 4.9 特殊 Token 的原子性

模板字符串看起来像 `<|assistant|>`，不代表 Tokenizer 把它编码为一个 Special Token。若没有注册，它可能被拆成多个普通 Token，模型需要逐字符生成，边界定位也会失败。

检查词表中 Token ID、`all_special_tokens`、Encode 长度与 Skip Special Tokens 解码。新增特殊 Token 后需要调整 Embedding 矩阵并训练相应行，不能只改 Tokenizer 文件而继续使用旧模型词表大小。

不同特殊 Token 不能共享无意 ID。工具、图片代用标记和对话结束符各有职责。迁移模板时建立完整映射和兼容测试，防止一个旧 EOS 在新模型被解释成普通文本。

### 4.10 Tokenizer 边界合并

对字节级 BPE 或 SentencePiece，`encode(prompt)+encode(answer)` 不一定等于 `encode(prompt+answer)`。前导空格、换行和相邻字符会影响子词合并。若 Mask 边界按分开长度计算，可能偏移一个或多个 Token。

正确方式是对完整渲染文本一次 Tokenize，再使用 Offset Mapping 或模板返回的 Assistant Mask。Offset 映射要处理 Special Token 常无字符跨度、Unicode 规范化和 Fast Tokenizer 支持差异。

若使用 Sentinel 标记，在渲染后定位并移除，必须证明 Sentinel 不会出现在用户内容、不会被模板转义、编码序列唯一。对抗样本应包含伪造角色标记，防止用户文本改变监督边界。

### 4.11 Loss Mask 是数据资产

Loss Mask 不只是运行时临时张量。它由 Sample 监督意图、Template、Tokenizer、截断和 Packing 共同产生，应在 Train-ready Sequence 中保存或可确定重建，并有 Version。

质量报告至少给出有效目标 Token 数、比例、按角色与任务分布、零目标样本、仅 EOS 样本、截断损失和每 Sample 监督 Turn 数。平均比例正常仍可能掩盖某切片全零。

训练 Run 记录实际有效 Token，而不是只报告 Input Token。全序列与 Assistant-only 使用相同名义 Batch，梯度信号量不同；学习率与总 Token 比较需要有效分母。

### 4.12 Label Shift 的常见错误

![Label Shift 的常见错误](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l19_02.png)

许多 Causal LM 实现接收未 Shift Labels，在 Forward 内用位置 $t$ 的 Logits 预测位置 $t+1$。若预处理提前把 Labels 左移，再由模型 Shift，会让输入预测两步后的 Token。

Mask 必须跟随目标位移，不能把输入角色直接贴到 Logit 位置。

另一错误是 Mask 应用在输入位置而不是目标位置。Assistant 第一个 Token 由前一个 Header 位置的 Logits 预测，Labels 数组中 Assistant Token 所在位置应有效。通过一个五 Token 手算例子最容易验证。

Padding 方向也影响位置。左 Padding 常用于生成 Batch，训练可能右 Padding。若 Position IDs 与 Attention Mask 处理不当，左 Padding 可改变相对位置。机制实验直接输出每个输入位置、目标位置与 Mask。

### 4.13 截断不是简单切片

序列超过最大长度时，取前 $L$ 个 Token 可能保留全部 Prompt 却删除 Assistant 答案，产生零监督样本；取后 $L$ 个可能丢失 System 与任务定义；中间截断可能切断工具 JSON 或角色 Header。

策略应按数据类型设计。单轮 SFT 可预留最小 Completion 预算，Prompt 超长时按结构压缩或拒绝；多轮对话可删除最早完整 Turn 并保留 System 与最后目标；工具轨迹按 Step 边界截断；长文问答保留问题与相关证据片段。

任何截断都记录原始 Token、保留 Token、删除的角色与目标、是否切断结构。截断后重新验证至少一个目标 Token、结束符、工具配对和模板合法。

### 4.14 Prompt 截断与 Answer 截断

Prompt 过长时，可以从左、右或结构化选择。左截断保留最近上下文，适合对话；右截断保留开头任务，适合固定说明；检索问答可按相关性选择证据。不能用统一侧别处理所有任务。

Answer 截断更危险，因为模型被训练生成不完整答案。若必须限制长度，可以要求生成数据阶段产生受控长度，或在完整语义边界截断并加正常结束。硬切后追加 EOS 会教模型在半个 JSON 或半句中结束。

统计 Answer 截断率、受影响能力和长度分位。大量截断说明数据与上下文预算不匹配，应重构样本或使用更长训练，而不是把问题隐藏在 Data Collator。

### 4.15 多轮窗口选择

对话超过上下文时，常保留 System、最近若干轮和当前目标。窗口选择以完整 Message 为单位，计算模板渲染后的 Token 预算，因为角色 Header 也占 Token。

前文可能包含后续指代、工具状态和用户约束。简单删最早轮会让当前回答无法解释。可以用依赖标记、摘要或任务生成时控制长度，但摘要产生新派生内容，需要版本与质量验证。

若一个 Assistant Turn 是监督目标，依赖的 User Turn 必须保留。窗口算法先选择目标，再向前扩展必要上下文，最后填充可选历史。无法在预算内保留最小闭包的样本应拒绝或路由长上下文模型。

### 4.16 Packing 的目的

![Packing 与注意力隔离](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l19_03.png)

先看坐标和对角块：有色格可见，灰色格不可见。块内下三角可见、块间不可见；EOS 本身不是隔离墙。

短 SFT 样本逐条 Padding 会浪费计算。Packing 把多个样本 Token 拼入固定长度 Sequence，提高有效 Token 比例。它改变物理序列，不应改变每个 Sample 监督语义。

Packing 必须保留 Sample Boundary、每个 Token 的 Loss Mask 和必要 Attention 隔离。有些 Causal LM 训练允许 Pack 内后一个样本看到前一个样本，这会产生跨样本上下文泄漏；可以通过 Block-diagonal Attention、Position Reset 或在应用可接受时用 EOS 隔断并明确风险。

仅插 EOS 不保证 Attention 隔离，模型仍能关注前文。是否可接受取决于框架、模型与实验。实验报告区分“Token 拼接”与“真正边界隔离”，不能用同一个 Packing 词掩盖。

### 4.17 Packing 的 Bin Packing 问题

给定不同长度样本和固定 Sequence 长度，目标是减少剩余空位，同时满足边界与任务约束。这接近 Bin Packing。First Fit、First Fit Decreasing、Best Fit 与在线缓冲各有吞吐、随机性和内存权衡。

按长度降序能提高填充率，却会重排数据并让相似长度集中。若长度与任务、语言或难度相关，Batch 分布会改变。可以在有限 Shuffle Buffer 内按长度分桶，再随机选择，平衡局部效率与全局混合。

Packing 质量至少报告每 Pack 样本数、有效 Token 比例、剩余 Token、长度分布与任务混合。只报告平均填充率会掩盖长尾 Pack 和某类样本一直被延迟。

在线 Packing 需要决定未填满 Pack 何时 Flush。等待更多短样本提高利用率却增加数据延迟和缓冲内存。离线 Train-ready 构建更容易全局优化并发布确定结果。

### 4.18 Position ID 是否重置

多个样本 Pack 后，后一个样本 Position 可从零重新开始，也可延续前一个。绝对位置 Embedding 模型对两种方案响应不同；RoPE 模型也会因位置影响旋转频率。框架必须与 Attention 边界和模型实现一致。

若 Block-diagonal Attention 隔离样本，重置 Position 最接近单样本训练。若模型 Kernel 不支持每段重置，连续 Position 实现简单，但短样本会被训练在更高位置，可能改变分布。

Position Reset 不能单靠在 `position_ids` 写零判断正确，还要验证 Flash Attention、Sequence Packing 元数据和并行框架是否消费该字段。有的高性能路径忽略手工 Position，静默使用连续值。

测试相同 Sample 单独运行与 Pack 后运行，在 Dropout 关闭时比较其有效 Token Logits。若目标是语义等价，差异应在数值容差内；否则报告设计差异。

### 4.19 Attention Boundary

标准二维 Causal Mask 只禁止看未来，Pack 中后一个样本仍能看前一个样本。Block-diagonal Causal Mask 要求每个 Token 只能看同一 Sample 中不晚于自己的位置。

显式四维 Mask 直观但内存昂贵。高性能 Attention 常使用每段累积长度 `cu_seqlens`、Segment ID 或 Packed Sequence 接口，在 Kernel 内部建立边界。数据层需要输出正确段长并测试。

边界错误可能不影响 Loss 形状，也不报错。可以构造两个极端样本：后样本答案只有看到前样本秘密才可预测。若 Pack 训练或前向显著利用秘密，说明泄漏。

即使允许跨样本 Attention，也要在实验中明确它是一种近似。随机 Pack 可让泄漏像噪声，固定任务排序则可能形成系统伪相关。

### 4.20 Pack 内的 EOS 与分隔符

边界由结构和位置决定，不仅由 Token 值决定。

每个 Sample 结尾通常保留 EOS，告诉模型在该回答结束。下一个 Sample 从 BOS 或角色 Header 开始。若删除中间 EOS，只在 Pack 末尾放一个，模型会学习把多条无关对话连成一段。

重复 BOS 是否保留取决于模型训练协议。有些 Packed 实现为每段保留 BOS 并重置位置，有些只在整 Pack 开头。必须与模型原始预训练和模板契约一致，通过单样本—Pack 等价测试验证。

中间 Padding 不应出现，Pack 尽量连续；最后不足部分 Padding，Attention 与 Loss 都屏蔽。若固定块切分跨越 Sample，不得把后半段当独立无上下文序列，除非显式设计状态延续。

### 4.21 Loss Mask 的边界单元测试

最重要测试不是训练 Loss 下降，而是对一条最小对话打印 Token ID、Token 文本、角色、Message ID、是否输入可见、是否监督和目标位置。人工能够逐行核对。

测试覆盖空 System、多个 User、多个 Assistant、Tool、包含角色字符串的用户输入、Emoji、中文、前导空格、超长截断和只有一个答案 Token。每个 Case 有期望 Mask，不使用训练框架动态结果作为唯一真值。

变更模板、Tokenizer 或库版本时自动运行快照 Diff。快照变化不一定错误，但必须审批。只比较总 Token 数不够，要比较每个监督 Span 与特殊 Token。

### 4.22 零监督与低监督样本

零监督样本可能来自答案为空、模板未识别角色、全部目标被截断、Mask 定位失败或 Schema 错误。它仍消耗前向计算，但 Loss 分母为零，某些实现产生 NaN，另一些静默返回零。

发布门禁拒绝零目标，统计有效 Token 低于阈值的样本。只有 EOS 一个目标通常也没有训练价值，需单独计数。结构任务可能答案很短，应按任务设阈值而不是全局删除。

训练运行再次统计每 Batch 有效 Token。如果 Data Collator、动态截断或并行切分在发布后改变 Mask，运行时门禁能捕获。连续多个零目标 Batch 应立即失败。

### 4.23 Role 顺序验证

并非所有对话都严格 System—User—Assistant 交替，工具调用会插入 Tool，多个 User 消息也可能由产品日志产生。但每个模板支持的有限状态机必须明确。

验证器检查允许的起始角色、Assistant 前是否有请求、Tool Result 是否引用未完成调用、结束角色是否符合训练目标、空内容是否允许。非法记录进入 Quarantine，不由模板猜测修复。

若业务需要合并连续同角色消息，产生新规范 Sample 并记录 Recipe。静默拼接会改变边界和标注可追踪性。不同来源的角色命名映射也要版本化。

### 4.24 System Message 的监督

## 写在最后

监督边界确定后，指令与响应本身也可以由模型合成。下一篇：[合成指令、响应、推理轨迹与自改进数据](/source/AI-Infra/5-数据工程与后训练/20-合成指令-响应-推理轨迹与自改进数据)。