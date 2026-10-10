# ICLR 2027 中文论文导航

一个使用 TypeScript + Vite 的静态论文导航站。支持官方研究方向 → 细分主题、交叉标签、中英文及英文摘要搜索、单篇/筛选结果分享、JSON/CSV 导出、手机布局与手动增量更新。

## 当前状态：全量元数据已核验，中文分类进行中

- 已核验 **42,358 篇有效投稿、21 个官方方向**，全部具有英文摘要；采集完成于 2026-10-10 17:02（北京时间）。
- **29 篇**已有中文标题、导读与语义分类，**42,329 篇**待处理；200 篇分层校准中已处理 21 篇，覆盖全部官方方向。词表仍是草案。
- 网站：https://lish529.github.io/iclr2027-guide-cn/ 。源码：https://github.com/lish529/iclr2027-guide-cn 。
- `snapshotKind: complete` 仅表示元数据集合已核验；`publicationMode: metadata-preview` 表示中文内容尚未完成。主题标签统计仅反映已处理论文。
- 无 PDF 下载、额外付费模型调用或定时任务。全量语义分类尚需继续处理，不把关键词匹配视为分类。

## 本地运行

需要 Node.js 22、npm 和 Python 3.12。Python 管道仅使用标准库。

```sh
npm ci
npm run dev -- --port 5173
```

打开终端显示的本地地址。发布构建与检查：

```sh
npm test
npm run data:check
npm run build
npm run preview -- --port 4173
```

已生成的 `dist/` 必须通过 HTTP 服务器访问，不支持直接双击 `index.html`：模块脚本、Worker 与 JSON 数据均需要正常 HTTP 路径。

## 采集与更新

数据来自 OpenReview API v2：

```text
GET https://api2.openreview.net/notes
content.venueid = ICLR.cc/2027/Conference/Submission
limit = 1000
sort = number:asc
```

只读取元数据，不请求 PDF。公开 API 无需验证时可以直接运行；如接口要求验证，先完成官方登录/验证流程。浏览器会话不一定与命令行共享；管道也接受当前会话中已经安全配置的 `OPENREVIEW_TOKEN`，不会写入文件或日志。不要把登录凭据提交到仓库。

```sh
# 首次采集；网络中断后再次运行会接着上次检查点继续
npm run data:fetch

# 新快照：重新读取有效投稿并进行第二轮 ID/总数核验
python3 scripts/pipeline.py fetch --new

# 为助手准备完整标题、摘要、关键词和官方方向，默认每批 20 篇
npm run data:prepare
```

两轮完整采集的唯一 ID 集合与总数必须一致，才会写入 `complete` 快照。列表期间发生变化会保存 `incomplete` 状态，必须重新核对。未完成采集不会把缺席论文误判成撤稿；成功核验后，原有但不在新集合中的论文保留历史记录并标为 `inactive`（不擅自断言具体退出原因）。网络或认证失败保留此前有效快照与检查点。

首次样本初始化脚本 `python3 scripts/import_samples.py` 仅导入已实际读取的网页数据，若已有快照则拒绝覆盖；**它不是全量采集器**。

## 分类流程

1. 对新快照运行 `prepare`，先阅读 `data/batches/<run>/calibration.json` 中按官方方向轮转的约 200 篇样本。
2. 以 `data/taxonomy.json` 为初始词表，校准细分类别的边界；补齐本届实际官方方向的中文名称，保留其英文原值。
3. 固定词表版本，将 `stage` 改为 `calibrated`，记录抽样 ID 和校准结论后再进行全量分类。当前 `2027.0-draft` **未完成此步骤**。
4. 当前助手逐批阅读完整摘要，按 `CLASSIFICATION.md` 输出结构化结果；**管道不会用关键词或空模板冒充语义分类**。
5. 导入校验通过的分类结果；生成文件必须写在 `work/`，避免被原始分类扫描误读。

```sh
python3 scripts/pipeline.py ingest work/classification-batch.json
npm run data:build
npm run data:check
```

每篇通过 `sourceFingerprint` 绑定标题、摘要、关键词和官方方向；只有这些字段变化或词表版本变化才失效。评分、时间戳变化不触发重新分类。失效记录仍保存在分类源文件中，网页标为待处理，不能继续展示过时导读。

所有已处理记录保存在 `data/annotations/records.json`，避免多批文件发生重复 ID。缺少摘要或不能确定分类的论文用 `review` 明确记录，不标为已完成。

## 数据接口

| 文件/字段 | 用途 |
| --- | --- |
| `data/raw/snapshot.json` | 原始快照和采集来源；不进入 Git |
| `data/taxonomy.json` | 分类词表、中文方向映射和版本 |
| `data/annotations/records.json` | 可追溯的中文内容、标签、来源指纹、判断依据 |
| `public/data/manifest.json` | 覆盖状态、时间、官方数量、分类进度、目录与搜索分片 |
| `public/data/index.json.gz` | 不含英文摘要的卡片索引 |
| `public/data/details-*.json.gz` | 每片最多 500 篇，展开时加载原摘要和分类依据 |
| `public/data/search-*.json.gz` | 首次搜索时由 Worker 以 3 路并发加载，显示进度 |
| `manifest.detailShards` | 全部详情分片地址，可用于批量获取 JSON |

页面默认只展示 active 投稿；单篇链接可以查阅已保留的 inactive 记录并看到状态提示。多标签采用交集。默认按投稿编号倒序，不表示质量。评分值保留为 `null`。

分享参数：`?q=关键词&area=官方方向&sub=细分类别&tag=标签1&tag=标签2&page=2`。单篇：`?paper=OpenReviewID`。导出按钮导出当前筛选结果，并注明快照类型；搜索尚未完成时暂不允许导出不完整结果。

## 分类验收与 GitHub Pages

每个一级方向复核至少 10 篇，不足则全查；另外复核待复核、跨领域和“其他”记录。将实际复核结果写入 `data/qa.json`：

```json
{
  "snapshotFinishedAt": "与 manifest.finishedAt 完全一致",
  "reviewedIds": ["实际逐篇复核过的 ID"],
  "notes": "记录分类边界修正、中文导读事实核对和遗留问题"
}
```

全部中文分类交付前（元数据预览不代表通过此验收）：

```sh
python3 scripts/pipeline.py check --release
npm test
npm run build
```

检查要求完整快照、官方总数一致、无未处理论文、词表已校准和每个方向抽查覆盖。待复核论文可以存在，但必须明确标记并已在复核记录中说明。

GitHub Pages 已设置为 GitHub Actions 发布。工作流支持明确标注的样本预览、已核验元数据预览和通过 `check --release` 的分类交付三个阶段；不会把分类未完成的快照当成全量分类成果。

数据按需手动刷新后提交更新；工作流不定时抓取，也不持有 OpenReview 或模型凭据。

## 数据规模与验证

压缩索引约 5.8 MiB；详情和搜索独立分片，浏览器用原生 Gzip 解压。无需把 42,358 个摘要同时渲染到页面。详情缓存最多 8 片；导出按当前筛选顺序分批装载相关详情，不另存超过 GitHub 单文件限制的大 JSON。完整导出仍需要浏览器在内存中组装文件，低内存设备建议先筛选。

`npm test` 验证搜索、筛选、URL、CSV、压缩数据读取以及断点恢复、增量变化与分类指纹。`data:check` 核对所有发布 ID、摘要详情、搜索索引、一级/二级数量和分类进度。`data:check -- --release` 额外要求完整分类与质量复核，目前会拒绝尚未完成的分类快照。

分类校准进度在 `data/calibration-progress.json`。此记录不等于最终分类质量验收。
