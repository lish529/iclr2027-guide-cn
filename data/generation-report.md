# ICLR 2027 分类生成报告

- 发布模式：`metadata-preview`
- 有效投稿：42,358
- 当前结构有效中文记录：1,406
- 尚未处理：40,952
- 固定词表：`2027.0-draft`（`calibrated`）

## “后训练更新几何”优先集

- 高召回候选：1,091 篇
- 核心论文：117 篇
- 数学方法参考：60 篇
- 排除：914 篇
- 近邻排除项抽查：200 篇；经再次独立严格裁决后补入 8 篇（core 4、method-reference 4）
- 入选论文：177 篇，其中复核并复用原有效记录 2 篇，新生成 175 篇
- 摘要忠实度复核：177 / 177；复核时修正 72 篇
- 无效记录、未知 ID、待复核占位：均为 0

筛选依据完整标题、摘要、关键词和 Primary Area；关键词只用于召回。结果保存在 `data/research-interest-screening.json` 和 `data/research-interest-report.json`。本专题完成不代表 42,358 篇已全量分类，也不构成论文质量排名。

## “异构模型合并与迁移”专题

- 高召回候选：3,773 篇
- 核心论文：693 篇
- 方法参考：88 篇
- 排除：2,992 篇
- 近邻排除项分层抽查：300 篇；第一轮纳入项另经独立严格裁决
- 入选论文：781 篇，其中复核并复用原有效记录 98 篇，新生成 683 篇
- 摘要忠实度复核：781 / 781；复核时修正 76 篇
- 无效记录、未知 ID、未处理入选记录：均为 0

筛选清单与生成报告分别保存在 `data/heterogeneous-transfer-screening.json` 和 `data/heterogeneous-transfer-report.json`。专题通过 `?topic=heterogeneous-model-transfer` 进入，并继续保持 `metadata-preview`。

## 全量后台 API 状态

此前 OpenAI 公共 Batch API 预检因连接重置停止，未提交计费任务，输入/输出 token 与估算费用均为 0。本次优先集由当前助手逐篇处理，不将该网络失败写成语义“待复核”。
