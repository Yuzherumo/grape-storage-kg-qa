# 来源清单（docs/sources.md）

> 数据口径：**不编造**。每条三元组的 `source_ids/locator/quote` 可追到下表；拿不到原文页码的一律 `status=anchor` 并在 `triples.csv` 的 `note` 写明待核验点。
> 升级为 `verified` 的流程：拿到原文 → 补 `locator`（条款号/图号/页码）+ 抄录 `quote` → 人工核对数值 → 改 `status=verified` 并重跑 `scripts/validate_data.py` 与 `scripts/gen_cypher.py --check`。

## 1. 来源表（`data/sources.csv`，19 条）

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
| `review_gwq_2002` | 葡萄贮藏保鲜技术研究进展 | 综述 | 2002 | 果树学报, 19(5): 326-329 | 呼吸强度/预冷/冰温/高 CO₂ 褐变与异味（6 条升级依据） | **已获取 PDF（用户提供）** |
| `review_sqs_2024` | 鲜食葡萄保鲜技术研究进展 | 综述 | 2024 | 江苏农业科学, 52(4): 17-22，DOI 10.15889/j.issn.1002-1302.2024.04.003 | 1-MCP（阳光玫瑰 1 μL/L、乙烯拮抗、落粒）3 条升级依据 | **已获取 PDF（用户提供）** |
| `review_so2_zyf` | 二氧化硫在鲜食葡萄保鲜中的应用研究进展 | 综述 | 2024 | 现代食品科技, 40(6): 311-317，DOI 10.13982/j.mfst.1673-9078.2024.6.0645 | SO₂ 抑菌/品质效应/过量伤害（漂白、落粒、裂果、风味劣变） | **已获取 PDF（用户提供）** |
| `review_plant_wy_2022` | 植物提取物在葡萄保鲜中的应用研究进展 | 综述 | 2022 | 保鲜与加工, 22(4): 116-120，DOI 10.3969/j.issn.1009-6221.2022.04.015 | 葡萄采后主要病害（灰霉/炭疽等）与植物提取物抑菌 | **已获取 PDF（用户提供）** |
| `review_dy_2017` | 鲜食葡萄保鲜研究新进展 | 综述 | 2017 | 绿色科技, 2017(5) | 品种耐贮性规律（欧亚种>美洲种、晚熟>早熟等） | **已获取 PDF（用户提供）** |
| `moa_storage_2023` | 葡萄贮藏保鲜操作规程 | 行业资料 | 2023 | 农业农村部官网 scs.moa.gov.cn（2023-02-03） | 温度/湿度、预冷 12h、SO₂ 伤害、包装、出库期、SO₂×红地球 | **已获取网页全文** |
| `moa_quality_2023` | 葡萄全程质量安全风险管控指南 | 行业资料 | 2023 | 农业农村部官网 jgs.moa.gov.cn（2023-06-30） | 全流程管控；贮藏/包装/运输要求（本轮引用其品种温度分类与包装口径） | **已获取网页全文** |
| `paper_kyoho_temp_2018` | 贮藏温度对巨峰葡萄采后生理和贮藏品质的影响 | 论文 | 2018 | 食品研究与开发, 39(21): 192-197；DOI 10.3969/j.issn.1005-6521.2018.21.032 | 0/5/10/25℃ 对照：失重率、落粒率、腐烂率、呼吸强度（7 条 AFFECTS/预冷依据） | **已获取网页全文** |

## 2. 证据强度与分组规则

- **B 组**（`CONTRA_INDICATED_FOR`）、**G 组**（`ALTERNATIVE_TO`）、**H 组**（`INDICATES`）每条 **≥2 个来源**，否则 `note` 必须写「单来源，建议后续实验验证」，UI 显示「单来源」徽标。
- 当前 115 条中 B/G/H 组均 ≥2 来源，或在 `note` 声明「单来源，建议后续实验验证」：新增 `SO₂×红地球` 为农业农村部单来源，已按规则声明，UI 显示「单来源」。
- `status`：`anchor`＝按公开描述/摘要入图、原文条级未核；`verified`＝已拿到原文并抄录 locator/quote。当前 **69 条 `verified`**（其中 `source_ids` 含国标 `gbt16862_2026` 的 53 条、仅其他来源的 16 条；§2.2 的 10 条综述原文 verified 中有 2 条同时含国标来源；§2.3 为新增 MOA/2018 来源 8 条）、**46 条 `anchor`**（诚实策略；校验器强制 verified 必须有 quote，anchor 空 quote 必须在 note 写「待核验」）。
- `confidence`：0.50~0.95，按来源等级（国标 > 综述 > 论文 > 行业资料）与一致性人工设定。

## 2.1 国标条文引用（53 条 verified，按 `source_ids` 计）
> 来源：GB/T 16862-2026《鲜食葡萄冷藏技术》全文 PDF（用户提供）。**仅引用条级摘录，未转载标准全文。**
>
> **口径**：`status=verified` 且 `source_ids` 含 `gbt16862_2026` 的三元组共 **53** 条（第三轮补齐前为 46 条）。
> 第三轮来源核对：quote/locator 明确引用国标条款或附录 A/B、且 `status=verified` 的 7 条（`e_gray_so2pad`、`f_black_hot`、`f_blue_wound`、`f_gray_wound`、`f_rhizopus_mech`、`sm_ind_ssc`、`sm_ind_ta`）已逐条回查 GB/T 16862-2026 PDF 提取文本（`.tmp/std_text.txt`），quote 与原文一致后在该行 `source_ids` 末尾补挂 `gbt16862_2026`，故 46→53。

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

**未升级（仍 anchor）的关键项**：阳光玫瑰 0±0.5℃（工程/文献口径，国标通用区间为 -1~0℃）、各品种耐贮性月数、SO₂ 熏蒸×阳光玫瑰禁忌（国标仅规范缓释保鲜剂，熏蒸风险依据 §3.1「二氧化硫伤害」定义+文献+综述）、AFFECTS 因果强度。

## 2.2 综述原文引用（10 条 verified，其中 `c_cold0_decay`、`c_precool_decay` 同时含国标来源）

> 来源：用户提供的 5 篇综述 PDF（见 §1 后 5 行）。**仅引用条级摘录，未转载全文。**

| 综述 | 支撑的三元组（sid） | 引文要点 |
|---|---|---|
| 关文强 2002 果树学报 | `sm_aff_resp`、`c_cold0_decay` | 低温明显抑制葡萄呼吸强度、酶活性及真菌生长繁殖 |
| 关文强 2002 | `c_precool_decay` | 采后及时预冷减少果梗失水/褐变/脱粒并抑制真菌繁殖 |
| 关文强 2002 | `c_highco2_browning`、`c_highco2_offflavor` | CO₂ 再升高引起果粒褐变；>15% CO₂ 有异味 |
| 关文强 2002 | `g_ice_alt_cold_neg1` | 冰温贮藏弥补一般冷藏贮期短、烂果多的缺陷 |
| 张一帆 2024 现代食品科技 | `sm_contra_so2` | 不同品种对 SO₂ 敏感性不同；过量致漂白、落粒、裂果、风味劣变 |
| 邵千朔 2024 江苏农业科学 | `sm_req_1mcp` | 阳光玫瑰 1 μL/L 1-MCP 采前喷施/采后熏蒸可改善贮后品质 |
| 邵千朔 2024 | `sm_aff_berrydrop_1mcp` | 1-MCP+辐照复合处理抑制腐烂率、掉粒率、失重率（note 标注为复合处理） |
| 邵千朔 2024 | `sm_aff_ethylene_1mcp` | 1-MCP 是乙烯拮抗抑制剂 |

## 2.3 MOA 指南与 2018 温度试验（8 条 verified）

> 来源：农业农村部《葡萄贮藏保鲜操作规程》（2023）、《葡萄全程质量安全风险管控指南》（2023）、许蕙金兰等《贮藏温度对巨峰葡萄采后生理和贮藏品质的影响》（2018）。均为公开网页全文，条目级摘录。

| 来源 | 支撑的三元组（sid） | 引文要点 |
|---|---|---|
| MOA 贮藏操作规程 | `a_kyoho_precool`、`b_redglobe_contra_so2`、`i_muscat_hamburg_shelf` | 巨峰系预冷≤12h；红地球对 SO₂ 敏感、不能大量使用；优质玫瑰香≤5 个月 |
| MOA 全程管控指南 | 本轮用于交叉核对品种温度分类与包装/运输口径 | 欧美杂交种 -1±0.5℃、欧亚种晚熟 -0.5±0.5℃、中早熟 0±0.5℃；每件≤5kg |
| 2018 温度试验 | `c_cold0_berrydrop`、`c_cold0_weightloss`、`c_roomtemp_decay`、`c_roomtemp_berrydrop`、`c_roomtemp_weightloss` | 0℃ 42d 失重<6%、落粒<10%；25℃ 7d 腐烂 3.3%→23.0% |

## 2.4 科普描述来源（`data/descriptions.csv`，28 个节点）

> 节点详情中的科普段落为**改写引用**，非逐字转载；来源与许可在 CSV 的 `source_name / source_url / license_note` 中逐条注明。

| 节点 | 来源 | 链接 |
|---|---|---|
| 阳光玫瑰 | 科普中国《从夏黑到阳光玫瑰》+ 湖南农康《浅谈阳光玫瑰葡萄》 | [kepuchina](https://h5.kepuchina.cn/scientificwebsite/article?id=759763) |
| 巨峰 | 科普中国《巨峰葡萄》 | [kepuchina](https://cloud.kepuchina.cn/h5/detail?id=6974098159198248960) |
| 红地球（红提） | 科普中国《红提》 | [kepuchina](https://cloud.kepuchina.cn/h5/detail?id=6974097864569249793) |
| 夏黑 | 科普中国《夏黑无核葡萄》 | [kepuchina](https://cloud.kepuchina.cn/h5/detail?id=6974092622310146048) |
| 玫瑰香 | 科普中国《玫瑰香》 | [kepuchina](https://www.kepuchina.cn/xc/201712/t20171218_307896.shtml) |
| 克瑞森无核 | 科普中国《克瑞森葡萄》 | [kepuchina](https://cloud.kepuchina.cn/h5/detail?id=6974091333425696768) |
| 维多利亚 | 科普中国《维多利亚葡萄》 | [kepuchina](https://cloud.kepuchina.cn/newSearch/imgText?from=1&id=6974088772480000000&is_self=2) |
| 户太八号 | 百度百科《户太八号葡萄》 | [baike](https://bkso.baidu.com/item/%E6%88%B7%E5%A4%AA%E5%85%AB%E5%8F%B7%E8%91%A1%E8%90%84/4369241) |
| 7 种病害 | GB/T 16862-2026 附录B + 科普中国《葡萄贮藏期常见病害》 | [longshang](https://m-longshang.965333.com/p/10967.html) |
| 13 项指标 | GB/T 16862-2026 附录A / 综述指标体系 | 见 CSV 各行 |

许可说明：科普中国内容版权归原作者，百度百科内容仅作科普参考；本作品对上述内容进行了改写与压缩，并保留来源链接；标准只引用条级摘录。

## 3. 已知冲突与保留策略

| 冲突点 | 处理 |
|---|---|
| SO₂ 对阳光玫瑰：一方认为可用低剂量、一方报告果面漂白/风味劣变 | **不合成单一结论**，保留 CONTRA（severity=高）与 ALTERNATIVE（焦亚硫酸盐缓释片/1-MCP）两侧证据，答案并列陈述并注明来源 |
| 冰温贮藏数据来自红地球 | `note` 明确「品种来源为红地球，阳光玫瑰需另验证」，UI 显示「待核验」 |
| 玫瑰香耐贮性无数值 | 原留空；2026-11-22 按 MOA 2023「优质玫瑰香不超过5个月」回填 `value_max=5`，标 verified 并保留 quote |
| 红地球耐贮性：综述 4~6 月 vs MOA 西部约3个月/东部≤2.5个月 | 保留原 4~6 月区间与 anchor，`note` 写明冲突，待进一步核验，不强行合并 |
| 包装容重：GB ≤8kg vs MOA ≤10kg（宜≤5kg） | 保留 GB 的 `package_weight` 口径；MOA 作为补充说明，不新增冲突节点 |

## 4. 复现与核验命令

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py     # 十项校验（含来源外键、双来源规则、快照一致性）
.\.venv\Scripts\python.exe scripts\gen_cypher.py --check # CSV→Cypher 无漂移
.\.venv\Scripts\python.exe -m pytest tests -q            # 结构/链路/评测测试
```
