# 来源清单（docs/sources.md）

> 数据口径：**不编造**。每条三元组的 `source_ids/locator/quote` 可追到下表；拿不到原文页码的一律 `status=anchor` 并在 `triples.csv` 的 `note` 写明待核验点。
> 升级为 `verified` 的流程：拿到原文 → 补 `locator`（条款号/图号/页码）+ 抄录 `quote` → 人工核对数值 → 改 `status=verified` 并重跑 `scripts/validate_data.py` 与 `scripts/gen_cypher.py --check`。

## 1. 来源表（`data/sources.csv`，11 条）

| id | 题名 | 类型 | 年 | 检索途径 | 在图谱中的用途 | 可获取性 |
|---|---|---|---|---|---|---|
| `gbt16862_2026` | **鲜食葡萄冷藏技术（GB/T 16862-2026）** | 国标 | 2026 | 全国标准信息公共服务平台 openstd，按标准号直查（2026-03-31 发布、2026-10-01 实施；主管/归口：中华全国供销合作总社） | P0：温度 0±0.5℃、RH 90~95%、预冷、冷藏期等硬条件 | 在线预览；正文需购买/机构访问 |
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
- 当前 71 条中 B/G/H 组全部 ≥2 来源（SO₂×阳光玫瑰为 3 来源）。
- `status`：`anchor`＝按公开描述/摘要入图、原文条级未核；`verified`＝已拿到原文并抄录 locator/quote。当前全库为 `anchor`（诚实策略）。
- `confidence`：0.50~0.82，按来源等级（国标 > 综述 > 论文 > 行业资料）与一致性人工设定。

## 3. 已知冲突与保留策略

| 冲突点 | 处理 |
|---|---|
| SO₂ 对阳光玫瑰：一方认为可用低剂量、一方报告果面漂白/风味劣变 | **不合成单一结论**，保留 CONTRA（severity=高）与 ALTERNATIVE（焦亚硫酸盐缓释片/1-MCP）两侧证据，答案并列陈述并注明来源 |
| 冰温贮藏数据来自红地球 | `note` 明确「品种来源为红地球，阳光玫瑰需另验证」，UI 显示「待核验」 |
| 玫瑰香耐贮性无数值 | 留空不编造，`note` 写「待补文献回填」 |

## 4. 复现与核验命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py     # 九项校验（含来源外键、双来源规则）
.\.venv\Scripts\python.exe scripts\gen_cypher.py --check # CSV→Cypher 无漂移
.\.venv\Scripts\python.exe -m pytest tests -q            # 结构/链路/评测测试
```
