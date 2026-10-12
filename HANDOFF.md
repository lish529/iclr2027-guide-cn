# 给接续模型的任务：ICLR 2027 中文论文数据处理

## 你接手什么

在本项目目录工作：

```text
/Users/lisongheng/Documents/Codex/2026-10-10/https-openreview-net-group-id-iclr/outputs/iclr2027-guide-cn
```

这是一个已有源码、已采集数据、已发布网站的项目。你的默认职责是 **论文数据生成与自检**，最终独立质量复核、网站收尾和发布由原助手接续。用户后续指令优先于本说明。

网站：https://lish529.github.io/iclr2027-guide-cn/

本次固定快照有 **42,358 篇有效投稿、21 个官方方向**，采集完成于北京时间 2026-10-10 17:02:36。2026-10-10 完成固定 200 篇校准后，共有 208 篇中文分类有效，42,150 篇待处理；实际进度仍以检查命令为准。

不重新抓取 OpenReview，不下载 PDF，不修改原始快照。不要把已采集完成理解为中文分类已完成。不要调用未经用户授权的额外收费 API；若你本身在用户指定的模型/编辑器内工作，使用该入口的已授权能力即可。

**阶段 A 的 200 篇试跑已经完成，分类词表和边界已校准；后续只在用户确认后执行阶段 B 的剩余全量处理。** 不需要每一小批都请求继续。不能把“一次授权全量处理”理解成将四万篇塞进一个上下文。

## 先读取这些文件

1. `CLASSIFICATION.md`：分类与中文写作协议。
2. `data/taxonomy.json`：官方方向中文映射、已校准的二级类别和标签词表。
3. `data/annotations/records.json`：已有语义结果，保留并复用有效记录。
4. `data/calibration-plan.json` 与 `data/calibration-progress.json`：固定 200 篇样本及已完成部分。
5. `scripts/pipeline.py`：现有准备、导入、构建与发布检查入口。
6. `scripts/classification_status.py`：只读取本地源数据，不构建、不发布的覆盖检查入口。
7. `README.md`、`VALIDATION.md`：现有网站能力和验证边界。

首先运行：

```sh
python3 scripts/classification_status.py --write data/classification-status.json
```

原始输入在 `data/raw/snapshot.json`，这是 **本地保留但 Git 忽略**的文件。`data/batches/` 与 `work/` 也被忽略。仅克隆 GitHub 仓库不能获得这些本地接续材料。原始快照很大，请用脚本读取、按需分批，不要把整个 JSON 打印进模型上下文。

## 阶段 A：固定 200 篇试跑（已完成，不要重跑）

原始固定样本：`data/batches/1791623291529186000/calibration.json`。

未处理的 179 篇曾拆成 9 批（每批最多 20 篇），现已全部导入：

```text
work/handoff/calibration-input/manifest.json
work/handoff/calibration-input/batch-0001.json
...
work/handoff/calibration-input/batch-0009.json
```

这些文件只作为校准过程检查点保留。接续时不要重新随机抽样或再次生成；校准结论见 `data/calibration-review.json`。

每批完整阅读标题、英文摘要、关键词和 Primary Area，输出到 `work/classification-results/`；先校验，再导入。例如：

```sh
python3 scripts/pipeline.py ingest work/classification-results/calibration-0001.json
python3 scripts/classification_status.py --write data/classification-status.json
```

本阶段已完成，校准报告保存在 `data/calibration-review.json`，包含：

- 当前快照时间、当前词表版本、固定样本的 200 个 ID。
- 哪些 ID 已实际处理、哪些仍需重试或语义复核。
- 拟新增/合并/拆分类别，每项的理由和对应论文 ID。
- 容易混淆的类别边界：主要任务、核心贡献与所用方法的区别。
- 中文标题/导读的具体自查记录及发现的问题，不只写“全部通过”。
- 实际生成模型/入口（知道什么写什么，不能猜内部型号）。

`data/calibration-progress.json` 已记录完成状态。网站数据和线上版本尚未更新。

## 阶段 B：固定词表后，连续完成全量数据

收到阶段 B 指令后，直接使用 `data/taxonomy.json` 中 `stage: calibrated` 的现有词表和 `CLASSIFICATION.md` 中的固定边界。若确有系统性缺口才提出新版本，并补充迁移说明；不要在正式批次中随意改类。

**更换词表版本会使旧版本结果失效。** 当前 208 篇记录均匹配现版本。若未来变更版本，必须重新核对受影响记录；不能只批量修改版本号冒充重新核对，也不能修改源内容指纹掩盖输入变化。

生成剩余队列：

```sh
python3 scripts/pipeline.py prepare --size 20
```

使用命令实际输出的新目录，不要假设目录名固定。`prepare` 新生成的 `calibration.json` 不替代阶段 A 的固定样本；批量阶段只使用 `batch-*.json`。

每批建议 10–20 篇，可根据实际上下文和输出上限调整。每一条都必须依据完整摘要进行语义判断，不允许用关键词映射器、固定模板或截断摘要代替。正式批次开始后不随意增删词表；发现系统性边界问题时记录受影响 ID，修正规则并重处理相关论文。

先将结果原子写入 `work/classification-results/`，再通过 `ingest` 合并到主文件。原始模型输出与已校验结果分开保存。每批或一小组批次落盘，不把数百批只留在对话里。全量主文件只有一个写入者；多个进程同时调用 `ingest` 会存在覆盖风险，禁止这样合并。用户另行授权并行模型调用时，生成文件可以独立写，合并仍要串行。

不要求手工复制 4 万个指纹：可以在本批次生成时将输入 ID 与其 `fingerprint`、词表版本冻结保存，模型只输出语义字段，再由脚本严格按本批 ID 补齐元数据。补齐时必须用 **实际生成时的输入**；拒绝缺失、重复或不属于本批的 ID。不能事后用最新快照的指纹给过时内容背书。

本阶段连续推进，直到每个有效 ID 都有有效的 `complete` 或 `review` 记录。因输出格式、网络、配额或中断失败的论文属于待重试，不属于语义“待复核”；不要为了消除未处理计数将失败或未读论文批量标成 `review`。

## 每篇必须产生的记录

保存到 `data/annotations/records.json`，字段至少如下：

```json
{
  "id": "真实投稿 ID",
  "sourceFingerprint": "该次输入给出的 fingerprint",
  "taxonomyVersion": "当前固定词表版本",
  "classification": "complete",
  "titleZh": "忠实的中文标题，保留方法名",
  "summaryZh": "50–100 字中文一句话导读，说明研究问题和核心方法，只写摘要支持的内容",
  "subcategory": "固定词表中的一个二级类别",
  "tags": ["最多 5 个不重复的词表标签"],
  "reason": "简要说明主研究问题/贡献为什么对应这个类别",
  "method": "model-read-full-abstract",
  "model": "实际使用的模型标识；未知时明确写 unknown",
  "annotatedAt": "实际生成时间"
}
```

`method` 应按真实执行方式填写。直接由交互助手阅读可写 `assistant-read-full-abstract`；通过外部模型批量生成可写 `model-read-full-abstract`。不要把生成模型伪装成原助手。

信息确实不足或归类边界不确定时，使用 `classification: review`，写明具体原因；仍应尽可能提供忠实标题与导读。“其他”不是省事的默认类别。原始 Primary Area 不重新分配，评分保持未知，不作录用/质量排名。

**`data/annotations/` 只放可导入的论文记录，报告和日志不要放进去。** 当前读取器会扫描这个目录的所有 JSON，放入统计报告会破坏读取。

## 数据阶段应交付哪些文件

| 文件 | 内容 |
| --- | --- |
| `data/annotations/records.json` | 所有有效投稿的中文标题、导读、主细类、标签、依据与溯源字段；保留历史记录 |
| `data/taxonomy.json`、`data/taxonomy-notes.md` | 固定词表、版本与边界规则 |
| `data/calibration-plan.json`、`data/calibration-progress.json`、`data/calibration-review.json` | 200 篇试跑及具体校准结论 |
| `data/classification-status.json` | 用提供的脚本重新生成；含缺失、无效、待复核及“其他”ID |
| `data/generation-log.jsonl` | 每批时间、输入批次、词表版本、模型、尝试次数、成功/失败 ID；有真实用量时记录 tokens/费用，没有则填 null |
| `data/generation-report.md` | 实际完成情况、模型与执行方式、剩余问题、类别分布异常及复核建议 |
| `work/classification-results/` | 已落盘的原始批次与重试结果，便于恢复；不要放凭据 |

`data/qa.json` 留给最后的独立质量复核；不要为了通过发布检查捏造 reviewedIds。模型自检可以写进 `calibration-review.json` 与 `generation-report.md`。

阶段 B 的结构与覆盖完成条件：

```sh
python3 scripts/classification_status.py --write data/classification-status.json --require-processed
```

命令应退出 0，输出 `total: 42358`、`missing: 0`、`invalid: 0`、`unprocessed: 0`、`allActiveProcessed: true`，且 `complete + review = 42358`。允许真实的语义待复核，必须在报告中明确数量与原因。这个检查**不证明语义分类正确，也不等于最终验收**。

不要只告诉用户“跑完了”。报告实际 counts、所用词表版本、输出文件、失败重试情况和全部复核入口。

## 中断怎样恢复

重新打开本目录后先读本文件和源数据覆盖报告，再运行 `classification_status.py`。主记录文件是权威进度；日志和对话摘要只是辅助。如果某批原始结果存在但尚未导入，先验证并导入；失效或失败部分重新生成。不要从第一篇重跑，不要重新读完整的过去对话来推测进度。

若配额或运行时限迫使你暂停，在 `data/generation-report.md` 写清最后成功导入的批次、尚未导入的输出文件和下一批位置，不宣称全部完成。

## 留给原助手的工作

原助手将检查至少每个官方方向 10 篇（共至少 210 篇，本快照所有方向均超过 10 篇），另复核跨领域、待复核和“其他”案例；核对中文内容的摘要忠实度，发现系统性问题则回退重跑相关部分。然后生成 `data/qa.json`，重建静态数据、检查性能和页面、通过发布条件并更新 GitHub Pages。

在默认的数据交接范围内，不修改 `src/`、`public/data/`、`.github/workflows/`，不运行发布命令、不推送 GitHub，也不更换全量采集快照。若数据处理确实需要工具修复，可修改/新增 `scripts/` 和对应测试，但必须说明变更；不能削弱验证条件来使结果看似通过。
