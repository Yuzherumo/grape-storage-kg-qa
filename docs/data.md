# 知识图谱数据说明

本文描述 `data/` 下数据文件的组织方式、当前规模、字段含义、核验规则与统计口径。数据文件的机器可读约束见 [spec.md](spec.md)，接口定义见 [api.md](api.md)。

## 1. 统计口径（先看这一节）

| 术语 | 数量 | 说明 |
|---|---|---|
| **知识实体** | **63** | 品种 8、储藏条件 35、品质指标 13、病害 7；参与实体链接与问答检索 |
| **来源节点** | **45** | 国标 1、综述 9、论文 31、行业资料 4；只用于溯源，不进入实体链接词表 |
| **图谱节点** | **108** | = 63 知识实体 + 45 来源节点（Neo4j / Kùzu 中的节点总数） |
| **三元组** | **125** | 9 种谓词；`verified` 69、`anchor` 56 |
| **科普描述** | **28** | 8 品种 / 7 病害 / 13 指标，见 `descriptions.csv` |
| **S2a 快照** | **20** | 阳光玫瑰核心三元组，必须是主数据的严格子集 |
| **数据总行数** | **233** | 63 + 125 + 45（`validate_data.py` 统计口径） |

> 注意：不要把 108 说成「108 个知识实体」。108 是图谱节点数，其中 45 个是来源节点。

统计依据：对 `data/entities.csv`、`data/triples.csv`、`data/sources.csv` 逐行计数（不含表头），并由 `scripts/validate_data.py` 的「总数据行」输出交叉核对。计算方式：

```powershell
.\.venv\Scripts\python.exe -c "import csv;print(len(list(csv.DictReader(open('data/entities.csv',encoding='utf-8-sig')))))"
```

## 2. 数据文件

| 文件 | 内容 | 使用方 |
|---|---|---|
| `data/entities.csv` | 63 个知识实体：id、label、name、别名、类别、数值区间、阶段/方向/方式、品种属性、病害症状与病原、note | 实体链接词表、图谱节点、描述 |
| `data/triples.csv` | 125 条三元组：subject/object 名称与类型、predicate、数值/单位、effect/level/severity、source_ids、locator、quote、status、confidence、note | 问答检索、Cypher 生成、评测 |
| `data/sources.csv` | 45 条来源：id、题名、作者、年份、期刊/出处、类型、可获取性、备注 | 证据溯源、来源展示 |
| `data/descriptions.csv` | 28 个节点的科普描述：summary、detail、来源名称/链接、许可备注 | 图谱节点详情 |
| `data/triples_shine_muscat.csv` | 20 条阳光玫瑰核心三元组（M1 门禁快照），必须与主数据逐字段一致 | 数据校验（检查10） |
| `data/schema.json` | 标签/谓词枚举、类型-谓词组合、实体目标、校验规则、分组与置信度定义 | 校验脚本、生成脚本、测试 |
| `data/utterances.csv` | 12 条农户口语变体与期望意图/实体 | 评测与回归测试 |
| `data/eval_questions.csv` | 5 条典型问题 + 1 条越界探针 | 评测脚本 |
| `graph/schema.cypher`、`graph/init_nodes.cypher`、`graph/init_rels.cypher` | 由 CSV 生成的 Neo4j 初始脚本（MERGE 幂等） | Neo4j / 便携安装 |
| `graph/queries/*.cypher` | 10 个参数化查询模板（温度、湿度、气调、耐贮性、病害处置、病害风险、品质、品种对比、禁忌、兜底） | Neo4j 后端 |

## 3. 实体分布

### 品种（8）

| id | 名称 | 说明 |
|---|---|---|
| `shine_muscat` | 阳光玫瑰 | 主线品种；对 SO₂ 敏感、采后易落粒与果梗褐变 |
| `kyoho` | 巨峰 | 欧美杂交种，中熟 |
| `red_globe` | 红地球 | 红提，欧亚种，晚熟耐贮 |
| `summer_black` | 夏黑 | 早熟无核 |
| `muscat_hamburg` | 玫瑰香 | 中晚熟；耐贮性 ≤5 个月（MOA 2023 优质果口径，已回填） |
| `crimson_seedless` | 克瑞森无核 | 晚熟无核 |
| `hutai_8` | 户太八号 | 巨峰系选育 |
| `victoria` | 维多利亚 | 中早熟 |

### 储藏条件（35）

按类别：采后操作 7、环境风险 6、温度 5、化学 7、气调 4、湿度 2、包装 4。条件包含温度/湿度/气调指标，也包含预冷、入库密度、包装容重、SO₂ 缓释片、1-MCP、臭氧、冰温、销售环境、档案记录等条文型条目。

### 品质指标（13）

呼吸强度、乙烯释放率、腐烂率、落粒率、褐变指数、失重率、果梗褐变、异味/风味偏离、耐贮性、可溶性固形物 SSC、可滴定酸 TA、硬度、维生素 C。

### 病害（7）

灰霉病、根霉腐败病、青霉病、炭疽病、酸腐病、黑斑病、绿霉病。其中灰霉病、青霉病、黑斑病、绿霉病、根霉腐败病与 GB/T 16862-2026 附录 B 对齐；炭疽病、酸腐病依据综述/植物病理学通识，标注为待核验。

## 4. 关系分布（125 条）

| 谓词 | 数量 | 含义 |
|---|---|---|
| `REQUIRES` | 27 | 品种需要某储藏条件 |
| `PREVENTED_BY` | 24 | 病害可通过某条件/处理预防或处置 |
| `AFFECTS` | 32 | 条件影响某品质指标 |
| `HAS_INDICATOR_VALUE` | 18 | 品种的指标基线（含数值区间） |
| `SUSCEPTIBLE_TO` | 8 | 品种易感某病害 |
| `INDUCED_BY` | 7 | 病害的诱因 |
| `CONTRA_INDICATED_FOR` | 4 | 条件对某品种禁忌（含严重度） |
| `ALTERNATIVE_TO` | 3 | 条件/方案之间的替代关系 |
| `INDICATES` | 2 | 指标指示某病害 |

其中带数值（`value` 或 `value_min/max`）的关系 35 条。

## 5. 来源（45 条）

| id | 类型 | 年份 | 可获取性 | 题名（截断） |
|---|---|---|---|---|
| `gbt16862_2026` | 国标 | 2026 | 已获取全文 | 鲜食葡萄冷藏技术（GB/T 16862-2026） |
| `review_grape_storage` | 综述 | 2024 | 付费 | 鲜食葡萄采后保鲜技术研究进展 |
| `review_shine_muscat` | 综述 | 2023 | 付费 | 阳光玫瑰葡萄采后保鲜研究进展 |
| `review_packaging_logistics` | 综述 | 2023 | 付费 | 葡萄物流及贮藏保鲜包装技术研究现状与展望 |
| `review_table_grape_en` | 综述 | 2025 | 公开 | Postharvest Preservation Strategies for Table Grapes |
| `paper_so2_1mcp_shine` | 论文 | — | 付费 | 1-MCP 和 SO₂ 处理对阳光玫瑰葡萄贮藏品质及风味的影响 |
| `paper_so2_pad_1mcp_shine` | 论文 | 2026 | 付费 | 1-MCP pretreatment combined with SO₂ preservation pad… |
| `paper_clo2_so2_shine` | 论文 | — | 付费 | …Shine Muscat grapes: flavor, appearance… under ClO₂/SO₂ storage |
| `paper_ice_temp` | 论文 | — | 付费 | 1-MCP 结合 ClO₂ 处理对冰温贮藏红提葡萄生理品质的影响 |
| `paper_ca_water_crystal` | 论文 | — | 付费 | 不同自发气调袋包装对水晶葡萄采后贮藏品质的影响 |
| `ops_grape_ny1199` | 行业资料 | 2006 | 付费 | 葡萄保鲜技术规范（NY/T 1199-2006） |
| `review_gwq_2002` | 综述 | 2002 | 已获取 PDF | 葡萄贮藏保鲜技术研究进展 |
| `review_sqs_2024` | 综述 | 2024 | 已获取 PDF | 鲜食葡萄保鲜技术研究进展 |
| `review_so2_zyf` | 综述 | 2024 | 已获取 PDF | 二氧化硫在鲜食葡萄保鲜中的应用研究进展 |
| `review_plant_wy_2022` | 综述 | 2022 | 已获取 PDF | 植物提取物在葡萄保鲜中的应用研究进展 |
| `review_dy_2017` | 综述 | 2017 | 已获取 PDF | 鲜食葡萄保鲜研究新进展 |
| `moa_storage_2023` | 行业资料 | 2023 | 公开 | 葡萄贮藏保鲜操作规程（农业农村部） |
| `moa_quality_2023` | 行业资料 | 2023 | 公开 | 葡萄全程质量安全风险管控指南（农业农村部） |
| `paper_kyoho_temp_2018` | 论文 | 2018 | 公开 | 贮藏温度对巨峰葡萄采后生理和贮藏品质的影响 |
| `agridata_legacy_2005` | 行业资料 | 2005 | 公开 | 葡萄贮藏保鲜技术（农产品贮藏保鲜技术数据库旧版专题页） |

可获取性统计：`public` 31 条、`paywalled` 14 条。

> 另有 25 篇开放获取文献来源（`web_*`，来源类型均为「论文」），题录、DOI、许可与本地文件见 `data/external/web_grape_storage/paper_records.csv`；其中 5 个处理条件（壳聚糖涂膜、百里香精油涂膜、腐胺+超声、葡萄籽油、气调集装箱运输）和 6 条 AFFECTS 关系已抽取入图，全部为 anchor。部分来源的题录字段（作者、DOI）仍不完整，已在 `sources.md` 标注，不影响当前引用展示。

## 6. 证据分级：`verified` 与 `anchor`

| 状态 | 数量 | 含义 | 展示 |
|---|---|---|---|
| `verified` | 69 | 已获取原文，`quote` 为条级摘录，`locator` 为条款号/页码栏目 | 「已核验」 |
| `anchor` | 56 | 原文未获取；`locator` 必填，`note` 写明待核验点 | 「待核验」 |

`verified` 的构成需要说明清楚：

- 按**升级依据**：51 条依据 GB/T 16862-2026 条文升级，10 条依据用户提供的 5 篇综述原文升级，8 条依据农业农村部 2023 指南与 2018 温度试验论文升级；
- 按**当前 `source_ids`**：69 条 verified 中有 53 条引用国标、16 条仅引用其他来源（含 8 条原有综述/论文与 8 条新增 MOA/论文）；其中 `c_cold0_decay`、`c_precool_decay` 同时含国标与综述来源。

两种口径不矛盾：10 条综述升级中 2 条同时保留国标来源；新增 8 条 verified 来自 MOA 指南（2 条）、2018 温度试验论文（5 条）与回填玫瑰香耐贮性（1 条）。文档统一写「69 条 verified（51 条按国标条文、10 条按综述原文、8 条按 MOA/2018 论文）」，精确统计以 `source_ids` 为准。

校验器强制：`verified` 必须有非空 `quote`；`anchor` 必须有 `locator`，且 `note` 含「待核验」。`confidence` 是人工设定的来源置信度，不是统计概率；排序中 `verified` 权重 1.0、`anchor` 0.6。

## 7. 溯源方式

1. 每条三元组的 `source_ids` 用分号分隔多个来源 id，必须存在于 `sources.csv`；
2. `locator` 记录条款号（如 `7.3 冷藏条件`、`附录B 表B.1`）或 PDF 页码/栏目；
3. `quote` 记录条级原文摘录（标准只保留条级摘录，不转载全文）；
4. 问答时 `Evidence` 把 `source_ids` 映射为来源标题，与 `locator` 一起显示在证据卡中；
5. 图谱节点与可交互视图中，`source_ids` 同样随边属性保留，可追溯到来源。

## 8. 数据校验规则（十项）

`scripts/validate_data.py` 加载前执行以下检查，任一错误即退出非 0：

1. 列完整性：三张 CSV 表头与 `schema.json` 的 `csv_columns` 一致；
2. 枚举合法：`label`、`predicate`、`status`、来源 `type`/`access`、`direction`/`effect`/`severity`/`efficacy`/`category`/`stage`；
3. 数值区间：`value_min <= value <= value_max`，且均为数值；
4. 类型-谓词组合合法：`predicate_type_combos`；
5. `source_ids` 外键存在：均在 `sources.csv`；
6. B/G/H 组双来源（或 `note` 声明单来源）；
7. 阳光玫瑰行数 ≥ 20；
8. `locator` 非空率 100%；
9. `triples` 的 subject/object 能在 `entities.csv` 按名称找到且类型一致；
10. S2a 快照必须是主数据的严格子集（逐字段一致）。

当前结果：**通过，错误 0，告警 2**（46 条 anchor 的 quote 为空、S2a 快照 11 条 quote 为空，均符合 anchor 规则）。此外 `scripts/validate_cypher.py` 校验 Cypher 标签/关系/参数/计数，`scripts/gen_cypher.py --check` 校验 CSV 与生成物无漂移。

## 9. 数据流

```text
data/*.csv
  → scripts/validate_data.py        十项校验
  → scripts/gen_cypher.py          生成 graph/init_nodes.cypher、init_rels.cypher
  → LocalStore（默认）              运行时读取 CSV 建索引
  → Neo4jStore（可选）              执行 graph/queries/*.cypher
```

CSV 是唯一数据源；不要手改 `graph/init_*.cypher`，修改后运行 `gen_cypher.py` 重新生成。

## 10. 相关文档

- 来源清单与条文/综述摘录：[sources.md](sources.md)
- 数据契约（实体/关系/分组/冻结清单）：[spec.md](spec.md)
- 数据校验与问答验证结果：[validation.md](validation.md)
- 数据规模与核验限制：[limitations.md](limitations.md)
