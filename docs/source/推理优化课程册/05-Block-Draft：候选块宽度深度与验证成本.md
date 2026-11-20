# Block Draft：候选块宽度、深度与验证成本

Block Draft 把候选组织成「宽度 w × 深度 d」的块：每步给 w 个候选、连续提议 d 步，target 一次前向验证 w×d 个位置。宽度换单步覆盖、深度换连续接受长度，两者共同决定验证成本；块越大接受期望越高，但验证位置数按乘积增长，收益存在拐点。

![Block Draft：候选块宽度 × 深度决定验证成本](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y13_l05_01.png)

## 1. 机制要点

- **宽度 w**：单步多候选提高「该步至少一个命中」的概率，代价是该步验证位置 ×w。
- **深度 d**：连续提议步数决定一次验证最多接受多长前缀；接受率随深度衰减，深尾候选大多被浪费。
- **成本乘积**：验证位置数 = w×d，一次前向的 batch 维随之增长；显存与算力预算给出 (w, d) 的可行域。

## 2. 实验闭环

```bash
python lesson/05-block-draft/run.py --check-only
python lesson/05-block-draft/run.py --output results/lesson-05-fixture.json
python lesson/05-block-draft/run.py --real --model /models/target --width 3 --depth 3 \
  --output results/gpu_result.json
```

- **输入**：target 模型、(w, d) 扫描网格、CUDA GPU。
- **输出**：各 (w, d) 的 acceptance、验证耗时、端到端 token/s、接受路径 trace。
- **验收**：输出与贪心基线一致；acceptance 与验证耗时随 (w, d) 的曲面可复算；存在可识别的收益拐点而非单调递增。

## 3. 判读纪律

- 报最优点必须附扫描网格：只报一个 (w, d) 的「最佳」没有说服力，拐点要在曲面上可见。
- 区分「接受期望」与「净收益」：接受率高但验证成本更高时净收益为负，两者要分开报。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

块状草稿与扩散式投机解码的机制对照见 [DFlash：Block Diffusion Speculative Decoding](/source/AI-Infra/3-大模型推理优化工程/06-DFlash-BlockDiffusionSpeculativeDecoding)；本课聚焦 (w, d) 预算曲面的实验口径。