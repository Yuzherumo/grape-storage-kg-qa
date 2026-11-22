# 实施规格（docs/spec.md）—— 数据与验收口径（历史规划文档）

> **状态说明（2026-11-22）**：本文件是项目早期（M1-M3）的数据与验收规格，保留用于追溯实体清单与 schema 冻结过程。
> 当前数据规模已从「68 条目标」增长到 108 条，**当前统计口径以 [data.md](data.md) 为准**；实体 id 与谓词约束仍有效。

> 配套 `docs/api.md`（接口契约）与本文件（数据/实体/三元组/验收）。两份都读完再动手。
> 赛道：农客松 2026 主赛道 · 方向二「生命系统」（农业/食品 · 鲜食葡萄采后贮藏）。
> 规则：不编造来源；不编造数值；拿不到原文的数值一律 `status=anchor` 并在 `note` 写明待核验点。

## 1. 实体清单（节点 id 必须用下表，便于跨模块引用）

### 1.1 品种 Variety（8）
| id | name | aliases（分号） | species |
|---|---|---|---|
| `shine_muscat` | 阳光玫瑰 | Shine Muscat;香印;晴王;青提;香印青提 | 欧美杂交种 |
| `kyoho` | 巨峰 | Kyoho;巨峰葡萄 | 欧美杂交种 |
| `red_globe` | 红地球 | Red Globe;红提 | 欧亚种 |
| `summer_black` | 夏黑 | 夏黑无核 | 欧美杂交种 |
| `muscat_hamburg` | 玫瑰香 | Muscat Hamburg | 欧亚种 |
| `crimson_seedless` | 克瑞森无核 | Crimson Seedless | 欧亚种 |
| `hutai_8` | 户太八号 | 户太8号 | 欧美杂交种 |
| `victoria` | 维多利亚 | Victoria | 欧亚种 |

### 1.2 储藏条件 Condition（30）
| id | name | category | value_min | value_max | unit |
|---|---|---|---|---|---|
| `cold_0` | 低温冷藏 0±0.5℃ | 温度 | -0.5 | 0.5 | ℃ |
| `cold_neg1` | 低温冷藏 -1~0℃ | 温度 | -1 | 0 | ℃ |
| `ice_temp` | 冰温贮藏 -0.5~0℃ | 温度 | -0.5 | 0 | ℃ |
| `rh_90_95` | 相对湿度 90~95% | 湿度 | 90 | 95 | % |
| `rh_low` | 低湿环境 RH<90% | 湿度 | 0 | 90 | % |
| `ca_o2` | 气调 O₂ 3~5% | 气调 | 3 | 5 | % |
| `ca_co2` | 气调 CO₂ 1~3% | 气调 | 1 | 3 | % |
| `high_co2` | 高 CO₂ >5% | 气调 | 5 | 10 | % |
| `so2_fumigation` | SO₂ 熏蒸 | 化学 | | | |
| `so2_pad` | 焦亚硫酸盐缓释片 | 化学 | | | |
| `mcp_1` | 1-MCP 处理 | 化学 | | | |
| `ozone` | 臭氧处理 | 化学 | | | |
| `precool_fast` | 快速预冷（12h 内至 0℃） | 采后操作 | | | |
| `no_damage_harvest` | 无伤采收 | 采后操作 | | | |
| `mechanical_injury` | 机械伤 | 环境风险 | | | |
| `room_temp_storage` | 常温贮运 | 环境风险 | | | |
| `high_humid_condensation` | 高湿结露 | 环境风险 | | | |
| `high_temp_humid` | 高温高湿 | 环境风险 | | | |
| `microperforated_film` | 微孔保鲜膜 | 包装 | | | |
| `cold_chain_transport` | 冷链运输 | 采后操作 | | | |
| `wound` | 伤口 | 环境风险 | | | |
| `temp_fluctuation` | 冷藏温度波动 ±0.5℃ | 温度 | -0.5 | 0.5 | ℃ |
| `daily_intake_limit` | 每天入库量 ≤ 库容 10% | 采后操作 | | | |
| `storage_density` | 冷藏密度 ≤ 200 kg/m³ | 采后操作 | | | |
| `precool_forced` | 压差预冷 0~1℃ | 采后操作 | | | |
| `sales_env` | 销售环境 0~10℃ | 温度 | | | |
| `archive_record` | 档案记录保存 ≥2 年 | 采后操作 | | | |
| `package_weight` | 包装容重 ≤ 8 kg | 包装 | | | |
| `pre_harvest_rain` | 采前降雨 | 环境风险 | | | |
| `warehouse_disinfection` | 库房消杀 | 化学 | | | |

> 最后一组 9 个条件为 M8 从 GB/T 16862-2026 条文新增（§7.4.1/§5.2/§7.2/§5.3.2/§8.2/§9/§6.1.1.2/附录B），对应三元组均为 `verified`。

### 1.3 品质指标 QualityIndicator（13）
`respiration` 呼吸强度（lower_better）、`ethylene` 乙烯释放率（lower_better）、`decay_rate` 腐烂率 %（lower_better）、`berry_drop` 落粒率 %（lower_better）、`browning_index` 褐变指数（lower_better）、`weight_loss` 失重率 %（lower_better）、`stem_browning` 果梗褐变（lower_better）、`off_flavor` 异味/风味偏离（lower_better）、`shelf_life` 耐贮性 月（higher_better）、`ssc` 可溶性固形物SSC %（higher_better）、`ta` 可滴定酸TA %（target）、`firmness` 硬度（target）、`vc` 维生素C（higher_better）

### 1.4 病害 Disease（7，前 5 种与国标附录B 表B.1 对齐）
| id | name | pathogen_latin | symptom（农户口述，必须含口语） |
|---|---|---|---|
| `gray_mold` | 灰霉病 | Botrytis cinerea | 长白毛、灰霉层、果梗发霉、软腐水渍 |
| `rhizopus_rot` | 根霉腐败病 | Rhizopus migricans | 软烂、破皮流水、常温下长粗白色丝体（黑毛） |
| `blue_mold` | 青霉病 | Penicillium spp. | 青绿色霉斑、霉味 |
| `anthracnose` | 炭疽病 | Colletotrichum gloeosporioides | 凹陷褐斑、腐烂斑扩展 |
| `sour_rot` | 酸腐病 | — | 酸臭味、流汁、发软 |
| `black_mold` | 黑斑病 | Alternaria spp. | 果刷棕褐色凹陷斑、后期掉粒 |
| `green_mold` | 绿霉病 | Cladosporium herbarum | 果梗黑褐色腐烂斑、出库后长绿色霉层 |

> M8 校正：原「黑霉病 Aspergillus niger」「根霉病 R. stolonifer」与国标附录B 不符，已按国标更正为「黑斑病 Alternaria spp.」「根霉腐败病 R. migricans」；新增绿霉病。炭疽病/酸腐病国标未列，保留但相关证据仍为 `anchor`。

### 1.5 来源 Source（10~20，`data/sources.csv`）
必须真实可检索。建议覆盖：
1. `gbt16862_2026` GB/T 16862-2026《鲜食葡萄冷藏技术》，type=国标，access=paywalled（openstd 有在线预览）
2. `review_grape_storage` 葡萄采后贮藏保鲜技术研究进展（中文核心期刊综述）
3. `review_shine_muscat` 阳光玫瑰葡萄贮藏保鲜研究进展（综述）
4. `review_ca` 气调贮藏/自发气调在葡萄保鲜中的应用（综述）
5. `paper_so2_1mcp_shine` 1-MCP 和 SO₂ 处理对阳光玫瑰葡萄贮藏品质及风味的影响（论文）
6. `paper_clo2_so2_shine` ClO₂/SO₂ 处理阳光玫瑰的转录组-代谢组分析（论文，SCI）
7. `paper_so2_grape` SO₂ 类保鲜剂对葡萄采后品质的影响（论文）
8. `paper_ice_temp` 冰温/近冰温贮藏葡萄（论文）
9. `ops_grape_storage` 葡萄贮藏保鲜操作规程（行业资料）
10. `std_local_cold` 葡萄冷藏地方/行业标准（行业资料）

**禁止**编造作者/期刊/DOI；`doi_url` 不确定就留空并在 `note` 写「待补链接」。每条来源在 `docs/sources.md` 里写清检索途径。

## 2. 关系类型（9）
`REQUIRES`、`CONTRA_INDICATED_FOR`、`AFFECTS`、`SUSCEPTIBLE_TO`、`PREVENTED_BY`、`INDUCED_BY`、`ALTERNATIVE_TO`、`INDICATES`、`HAS_INDICATOR_VALUE`（方向/属性见 docs/api.md §1.2）。

## 3. S2a：20 条阳光玫瑰三元组（M1 门禁，先做这个）
即 `data/triples_shine_muscat.csv` 的 20 行（内容见批准计划 §5.3）：
1 阳光玫瑰-REQUIRES-低温冷藏 0±0.5℃；2 -RH90~95%；3 -气调O₂3~5%；4 -气调CO₂1~3%；5 -快速预冷12h；6 -1-MCP 1μL/L×12h；7 -冰温-0.5~0℃；8 -CONTRA_INDICATED_FOR-SO₂熏蒸（severity=高，双来源）；9 -HAS_INDICATOR_VALUE-耐贮性2~4月；10 -SSC≥16%；11 -TA≤0.35%；12 -SUSCEPTIBLE_TO-灰霉病(高)；13 -炭疽病(中)；14 -酸腐病(低)；15 低温冷藏-AFFECTS-呼吸强度(decrease)；16 1-MCP-AFFECTS-落粒率(decrease)；17 1-MCP-AFFECTS-乙烯释放率(decrease)；18 RH90~95%-AFFECTS-失重率(decrease)；19 SO₂熏蒸-AFFECTS-褐变指数(increase)；20 灰霉病-PREVENTED_BY-快速预冷(efficacy=中)。

## 4. S2b：补足到 68 条（保底 50）
按批准计划 §5.4 的 A~I 九组（A14 B3 C18 D8 E8 F6 G3 H2 I6）。**B/G/H 组每条 ≥2 来源或 note 声明单来源**。优先补：品种对比必需（I 组 8 条品种耐贮性）、病害处置（E 组）、禁忌（B 组）。

## 5. 校验器 `scripts/validate_data.py` 必查（退出码非 0 即失败）
1. 列完整性；2. 枚举合法（label/predicate/status/type/access/direction）；3. 数值区间 `value_min<=value<=value_max`；4. 类型-谓词组合合法；5. `source_ids` 外键存在于 sources.csv；6. B/G/H 双来源或 note 声明；7. 阳光玫瑰行数 ≥20；8. `locator` 非空率 100%；9. entities 中引用的 id 与 triples 中 subject/object 名称可对应（按 name 匹配）；10. S2a 快照 `triples_shine_muscat.csv` 必须是主数据的严格子集（逐字段一致）。

## 6. Cypher 生成与导入
- `scripts/gen_cypher.py`：读 entities.csv/triples.csv → 生成 `graph/init_nodes.cypher`、`graph/init_rels.cypher`（MERGE 幂等，节点中文 name，关系属性含 source_ids/locator/quote/status/confidence）；`--check` 模式比对已生成文件是否有漂移。
- `graph/schema.cypher` 手写：5 类唯一约束 + name/category 索引。
- `scripts/load_neo4j.py`：可选，读 `.env` 的 NEO4J_*，导入并打印 count 校验（无服务时给出友好提示，不报错崩）。

## 7. 验收（对应计划 §4.5/§5.6/§6.5/§8.3/§7.2）
- S1：schema.json + 三个 cypher 可执行幂等 + `gen_cypher --check` 通过。
- S2a：20 行 + validate 通过 + Q1 能答。S2b：≥50/目标 68 + validate 全过。
- S3：CLI 一问一答带 `[E#]`/证据/分步；离线可用；12 条口语变体意图命中 ≥10/12。
- S4：8501 一屏（结论/依据/步骤/证据/Cypher）+ 大字模式 + 离线徽标。
- S5：`pytest -q` 全绿；`docs/eval_results.md` 可复现。

## 8. 时间与优先级
- T+0.5~3 出 S1；T+3~9 出 S2a（先 20 条，别贪多）；T+9~18 补 S2b。
- 来不及就保底 50 条；B/G/H 双来源与 Q1~Q6 所需数据优先。
