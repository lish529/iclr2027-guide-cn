# ICLR 2027 中文论文导航

一个使用 TypeScript + Vite 的静态论文导航站。支持官方研究方向 → 细分主题、交叉标签、中英文及英文摘要搜索、单篇/筛选结果分享、JSON/CSV 导出、手机布局与手动增量更新。

## 当前状态：可用样本预览，尚非全量交付

- 已读取并逐篇整理 **8 篇真实公开投稿**，覆盖 7 个作者填写的官方方向。
- 每篇包括完整原摘要、中文标题、50–100 字导读、二级分类、交叉标签和分类依据。
- OpenReview 浏览器验证页显示已通过，但命令行 API 仍返回 `403 ChallengeRequiredError`，浏览器直接访问 API 也被客户端阻止。**有效投稿总数未核验，约 200 篇分层校准尚未完成，全量分类尚未完成。**
- GitHub 已登录，已创建公共仓库 https://github.com/lish529/iclr2027-guide-cn 。代码上传与 Pages 发布状态见后续更新。
- `public/data/manifest.json` 始终明确标记 `snapshotKind: sample`，全量发布检查会主动拒绝这个样本快照；工作流允许先发布带明显样本标识的预览，不能将其标为全量完成。
- 没有下载 PDF，没有调用额外付费模型 API，没有设置定时任务。

OpenReview 命令行登录采集入口：`python3 scripts/login_fetch.py`。账号、密码和双重验证码只在本地交互终端输入，不回显；登录后自动采集，token 仅留在当前进程。

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
| `public/data/index.json` | 不含英文摘要的卡片索引 |
| `public/data/papers/<id>.json` | 用户展开时加载的原摘要和分类依据 |
| `public/data/search-*.json` | 首次搜索时由 Worker 加载的全文索引 |
| `public/data/all-papers.json` | 完整导出数据，含 inactive 历史记录 |

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

全量发布前：

```sh
python3 scripts/pipeline.py check --release
npm test
npm run build
```

检查要求完整快照、官方总数一致、无未处理论文、词表已校准和每个方向抽查覆盖。待复核论文可以存在，但必须明确标记并已在复核记录中说明。

登录你的 GitHub 账号后，新建公共仓库 `iclr2027-guide-cn`，上传此项目（排除 `.gitignore` 中的内容），设置默认分支 `main`。在 Settings → Pages 选择 **GitHub Actions**。工作流 `.github/workflows/pages.yml` 会安装依赖、执行检查、构建并发布；样本只以明确标注的预览发布，正式快照必须通过完整验收。最终地址形如 `https://<你的用户名>.github.io/iclr2027-guide-cn/`。这是地址格式说明，**当前没有可用的线上发布地址**。

数据按需手动刷新后提交更新；工作流不定时抓取，也不持有 OpenReview 或模型凭据。

## 已执行验证

- 6 项 TypeScript 测试：中英文检索、联合筛选、摘要检索 ID、分享链接、CSV 转义、待处理记录检索。
- 7 项 Python 测试：断点恢复、重复 ID、修改指纹、部分采集防误撤稿、过时分类拒收、缺摘要/ID 校验、样本发布阻断。
- TypeScript 类型检查、Vite 生产构建、发布数据数量与索引一致性检查通过。
- 浏览器验证：英文摘要独有词检索、摘要展开、LLM + Agent 交集、JSON/CSV 导出、空结果、单篇深链接、390px 手机分类筛选；未发现横向溢出或控制台错误。
- **尚未验证**：全量 API 采集、整届分类质量、大规模真实数据性能、GitHub 在线部署。这些不能用样本验证替代。
