# 来源清单（docs/sources.md）

> 数据口径：**不编造**。每条三元组的 `source_ids/locator/quote` 可追到下表；拿不到原文页码的一律 `status=anchor` 并在 `triples.csv` 的 `note` 写明待核验点。
> 升级为 `verified` 的流程：拿到原文 → 补 `locator`（条款号/图号/页码）+ 抄录 `quote` → 人工核对数值 → 改 `status=verified` 并重跑 `scripts/validate_data.py` 与 `scripts/gen_cypher.py --check`。

## 1. 来源表（`data/sources.csv`，11 条）

| id | 题名 | 类型 | 年 | 检索途径 | 在图谱中的用途 | 可获取性 |
|---|---|---|---|---|---|---|
| `gbt16862_2026` | **鲜食葡萄冷藏技术（GB/T 16862-2026）** | 国标 | 2026 | 全国标准信息公共服务平台 openstd，按标准号直查（2026-03-31 发布、2026-10-01 实施，代替 GB/T 16862-2008；主管/归口：中华全国供销合作总社） | P0：冷藏温度/湿度（§7.3）、预冷时限（§5.3.2）、SO₂ 缓释保鲜剂（§6.3.4）、运输温度（§8.1）、附录A 理化指标、附录B 病害防治 | **已获取全文 PDF（用户提供，pdfminer 提取文本，逐条核对）**；openstd 在线预览 |
| `review_grape_storage` | 鲜食葡萄采后保鲜技术研究进展 | 综述 | 2024 | 《保鲜与加工》2024 vol.24 no.12，DOI 10.3969/j.issn.1009-6221.2024.12.019 | 生理与品质变化、处理方式、AFFECTS 边 | 付费 |
| `review_shine_muscat` | 阳光玫瑰葡萄采后保鲜研究进展 | 综述 | 2023 | 万方/维普检索（万方检索号 `ncqjg-xk202324017`） | 阳光玫瑰特异性：SO₂ 敏感、落粒、果梗褐变 | 付费；作者/期刊待补 |
| `review_packaging_logistics` | 葡萄物流及贮藏保鲜包装技术研究现状与展望 | 综述 | 2023 | 《包装工程》2023 vol.44 no.23（CNKI） | 包装/微孔膜/自发气调与物流环节 | 付费；作者/DOI 待补 |
| `review_table_grape_en` | Postharvest Preservation Strategies for Table Grapes: A Comprehensive Review from Practical Methods to Future Developments | 综述 | 2025 | PubMed PMID 40872088 | 英文综述交叉印证（硬度/乙烯/处理） | 公开 |
| `paper_so2_1mcp_shine` | 1-MCP 和 SO₂ 处理对阳光玫瑰葡萄贮藏品质及风味的影响 | 论文 | — | 中国农业学术服务平台（agri.nais.net.cn） | 1-MCP 与 SO₂ 对风味/品质的影响 | 付费；元数据待补 |
| `paper_so2_pad_1mcp_shine` | 1-MCP pretreatment combined with SO₂ preservation pad delays postharvest senescence and softening of Shine Muscat grapes… | 论文 | 2026 | Food Chemistry，PII S0308814626027688（ScienceDirect） | 阳光玫瑰 SO₂ 保鲜片 + 1-MCP 协同与软化机理 | 付费 |
| `paper_clo2_so2_shine` | An integrated transcriptomic and metabolomic analysis of Shine Muscat grapes: Flavor, appearance… under on-tree vs. low-temperature ClO₂/SO₂ storage | 论文 | — | CNKI Scholar / ScienceDirect | SO₂/ClO₂ 对阳光玫瑰风味与外观的证据（含争议） | 付费 |
| `paper_ice_temp` | 1-MCP 结合 ClO₂ 处理对冰温贮藏红提葡萄生理品质的影响 | 论文 | — | sciencechina 可检索 | 冰温贮藏（红地球/红提实证；**阳光玫瑰需另验证**，note 已注明） | 付费 |
| `paper_ca_water_crystal` | 基于主成分和相关性分析不同自发气调袋包装对水晶葡萄采后贮藏品质的影响 | 论文 | — | 维普 | 自发气调/微孔膜 AFFECTS 与替代方案 | 付费 |
| `ops_grape_ny1199` | 葡萄保鲜技术规范（NY/T 1199-2006） | 行业标准 | 2006 | 中国标准服务网 cssn.net.cn / 国家数字标准馆 | 行业操作口径（处置措施、包装） | 付费；正文待获取 |

## 2. 证据强度与分组规则

- **B 组**（`CONTRA_INDICATED_FOR`）、**G 组**（`ALTERNATIVE_TO`）、**H 组**（`INDICATES`）每条 **≥2 个来源**，否则 `note` 必须写「单来源，建议后续实验验证」，UI 显示「单来源」徽标。
- 当前 108 条中 B/G/H 组全部 ≥2 来源（SO₂×阳光玫瑰为 3 来源）。
- `status`：`anchor`＝按公开描述/摘要入图、原文条级未核；`verified`＝已拿到原文并抄录 locator/quote。当前 **51 条 `verified`**（GB/T 16862-2026 条文）、**57 条 `anchor`**（诚实策略；校验器强制 verified 必须有 quote，anchor 空 quote 必须在 note 写「待核验」）。
- `confidence`：0.50~0.82，按来源等级（国标 > 综述 > 论文 > 行业资料）与一致性人工设定。

## 2.1 国标条文引用（51 条 verified）

> 来源：GB/T 16862-2026《鲜食葡萄冷藏技术》全文 PDF（用户提供）。**仅引用条级摘录，未转载标准全文。**

| 条款 | 条文摘录（入图 quote） | 升级/新增的三元组（sid 或组） |
|---|---|---|
| §7.3 冷藏条件 | 葡萄适宜冷藏温度为-1℃~0℃，相对湿度为90%~95%。 | `a_kyoho_cold_neg1`、`a_red_globe_cold_neg1`、`a_muscat_rh`、`sm_req_rh`、`sm_req_cold_neg1`、`hutai_req_cold_neg1`、`victoria_req_cold_neg1`、`hutai_req_rh`、`victoria_req_rh` |
| §7.4.1 温湿度管理 | 冷藏期间应保持库温和湿度稳定，温度波动幅度不超过±0.5℃，相对湿度波动幅度不超过±5%。 | `sm_req_temp_fluct` |
| §5.2 码垛 | 每天入库量不超过库容量的10%。 | `sm_req_intake` |
| §5.3.2 预冷条件 | 冷库预冷 -1~0℃、压差预冷 0~1℃，宜在采后12h内将果实中心温度降至0℃。 | `sm_req_precool`、`sm_req_forced` |
| §7.2 入库 | 有效空间冷藏密度应不超过 200kg/m³。 | `sm_req_density` |
| §6.1.1.2 外包装 | 纸箱容重不宜超过8kg…… | `sm_req_pkg_weight` |
| §6.3.4 保鲜剂(纸) | 放置二氧化硫类缓释保鲜剂(纸)并封袋/箱；葡萄不应产生二氧化硫伤害。 | `e_gray_so2pad` 等缓释剂防治边 |
| §8.1 运输 | 运输温度宜控制在0℃~5℃…… | `a_victoria_coldchain` |
| §8.2 销售 | 销售环境温度宜控制在0℃~10℃…… | `sm_req_sales` |
| §9 档案记录 | 记录应保存两年以上。 | `sm_req_archive` |
| 附录A 表A.1 | 各品种可溶性固形物≥、可滴定酸≤（8 品种） | `sm_ind_ssc`、`sm_ind_ta`、`i_{巨峰/红地球/夏黑/玫瑰香/维多利亚}_{ssc,ta}` |
| 附录B 表B.1 | 5 种病害（灰霉/青霉/黑斑/绿霉/根霉腐败）症状、发病条件、防治措施 | `e_{gray/blue/black/green/rhizo}_cold`、`..._disinfect`、`..._so2pad`、`f_green_wound` 等；并升级 `f_gray_wound`/`f_blue_wound`/`f_rhizopus_mech`/`f_black_hot` |

**未升级（仍 anchor）的关键项**：阳光玫瑰 0±0.5℃（工程/文献口径，国标通用区间为 -1~0℃）、各品种耐贮性月数、SO₂ 熏蒸×阳光玫瑰禁忌（国标仅规范缓释保鲜剂，熏蒸风险依据 §3.1「二氧化硫伤害」定义+文献）、AFFECTS 因果强度。

## 3. 已知冲突与保留策略

| 冲突点 | 处理 |
|---|---|
| SO₂ 对阳光玫瑰：一方认为可用低剂量、一方报告果面漂白/风味劣变 | **不合成单一结论**，保留 CONTRA（severity=高）与 ALTERNATIVE（焦亚硫酸盐缓释片/1-MCP）两侧证据，答案并列陈述并注明来源 |
| 冰温贮藏数据来自红地球 | `note` 明确「品种来源为红地球，阳光玫瑰需另验证」，UI 显示「待核验」 |
| 玫瑰香耐贮性无数值 | 留空不编造，`note` 写「待补文献回填」 |

## 4. 复现与核验命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py     # 十项校验（含来源外键、双来源规则、快照一致性）
.\.venv\Scripts\python.exe scripts\gen_cypher.py --check # CSV→Cypher 无漂移
.\.venv\Scripts\python.exe -m pytest tests -q            # 结构/链路/评测测试
```
