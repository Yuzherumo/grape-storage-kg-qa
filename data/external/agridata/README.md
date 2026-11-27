# 国家农业科学数据中心 · 鲜食葡萄采后储藏相关数据（外部抓取）

本目录是「鲜食葡萄储藏知识图谱问答系统」的**外部数据抓取产物**，不属于图谱数据源
（`data/*.csv` 仍是图谱唯一真相）。抓取脚本见 `scripts/fetch_agridata_grape.py`、
`scripts/fetch_legacy_preserve.py`，完整方法与结论见
[`docs/agridata_grape_postharvest.md`](../../../docs/agridata_grape_postharvest.md)。

- 抓取时间：2026-11-27（+08:00）
- 来源：<http://www.agridata.cn>（国家农业科学数据中心）、<http://www.agridata.ac.cn>（北京农业数字信息资源中心）
- 合规：未登录、未注册、未申请下载；请求间隔约 1 秒；`robots.txt` 仅禁止 `/console/`，未访问

## 结论速览

主站**没有**「鲜食葡萄采后贮藏」专门数据集（A 级数据集 0 条）。
站点最接近的材料是：

1. 旧站「农产品贮藏保鲜技术数据库」中的**葡萄贮藏保鲜条目 1 条**（`legacy_preserve/`，内容完整，含 SO₂ 熏蒸剂量、10 种贮藏方式）；
2. 主站 1 条**科研项目**「鲜食葡萄果穗采运全周期的落粒-伤粒生物力学机制与规律研究」；
3. 主站 60 条**葡萄数据集**（栽培、品质、病害、种质方向，非采后）与 38 条**其他果蔬采后**数据集（苹果、荔枝、竹笋、鲜切猕猴桃等，可作方法参照）。

## 文件说明

| 文件 | 行/条数 | 说明 |
|---|---|---|
| `datasets_grape_postharvest.csv` | 111 | A/B/C 三级汇总表；每行带 `tier`、`tier_reason`、`evidence_*` 判定依据、`detail_url` |
| `datasets_relevant_only.csv` | 98 | 上表的**数据集**子集（主要交付物） |
| `projects_literature_relevant.csv` | 13 | 上表的**科研项目**子集（基金项目库记录） |
| `datasets_tier_a.csv` | 1 | A 级：唯一同时满足「葡萄 + 采后」的记录（项目，非数据集） |
| `datasets_all_hits.csv` | 5408 | 全量检索命中（含 D 级噪声），供审计复算 |
| `grape_datasets_index.md` | — | 人读索引：B 级按主题分组（种质/栽培/病虫害/品质/采后），附 C 级参照 |
| `search_hit_pairs.csv` | 24322 | 「检索词 ↔ gid」对应关系 |
| `details/<gid>.json` | 154 | 数据集详情原始回包（含 DOI、引用格式、使用说明等） |
| `files/` | 6 | 站点公开直链下载的文件（xlsx/rar），已做文件头与结构核验 |
| `legacy_preserve/preserve_db_all.csv` | 187 | 旧站「农产品贮藏保鲜技术数据库」全库 |
| `legacy_preserve/preserve_db_grape.csv` | 1 | 其中的葡萄条目（结构化） |
| `legacy_preserve/grape_storage_technique.md` | — | 葡萄条目可读整理稿（原文，未改写） |
| `legacy_preserve/grape_details.json` | 1 | 葡萄条目详情页文本 |
| `doi_resolution.json` | — | 用户给定 DOI 的解析全链路证据与落地数据集元数据 |
| `manifest.json` | — | 抓取参数、计数对账、下载与分级统计 |

## 关键字段

| 字段 | 含义 |
|---|---|
| `tier` | A=葡萄+采后；B=葡萄但非采后；C=果蔬采后但非葡萄；D=其余 |
| `record_kind` | `dataset` 数据集 / `project` 科研项目（站点同一接口混排） |
| `gid` | 站点数据集全局 id，详情 URL 为 `http://www.agridata.cn/dataset/detail/{resource_type}/{gid}` |
| `sci_identification` | 科技资源标识符（CSTR），可作为长期引用标识 |
| `data_set_doi` / `article_doi` | 数据集 DOI / 关联论文 DOI |
| `download_way` | 0/5=在线下载（公开直链），3/4=外链，10=申请下载（需实名） |
| `refer_standard` | 站点原文引用格式 |
| `evidence_grape` / `evidence_postharvest` | 支撑分级判定的命中词，便于人工复核 |

## 使用注意

- 各数据集许可不同（例如 `CSTR:17058.11.A0002…ds.3476` 为 CC BY-NC-ND 4.0），
  使用前请以 CSV 中 `usage_notes` / 详情页声明为准，并保留 `refer_standard` 的引用格式。
- 旧站葡萄条目入库于 2005 年，是面向生产的技术描述，**不是试验观测数据**；
  SO₂ 剂量、温湿度须与现行标准（GB/T 16862、NY/T 1046 等）核对后使用。
- 旧站页脚标注「版权所有：北京市农林科学院农业信息与经济研究所」，转载/商用需另行授权。

## 接入知识图谱（2026-11-27）

外部文件不直接等同于事实，接入时做了以下约束：

- 新增来源 `agridata_legacy_2005`（行业资料 / 公开，旧站专题页），并在来源 note 中登记本目录 CSV；没有把 111 行项目/数据集标题逐条当成知识事实。
- 只从旧版技术页抽取 4 条与现有实体直接对应的 `anchor` 关系：
  - `e_gray_so2_fumigation`：灰霉病 `PREVENTED_BY` SO₂ 熏蒸；
  - `e_blue_so2_fumigation`：青霉病 `PREVENTED_BY` SO₂ 熏蒸；
  - `c_so2_stembrowning`：SO₂ 熏蒸 `AFFECTS` 果梗褐变（过量风险，increase）；
  - `c_so2_decay`：SO₂ 熏蒸 `AFFECTS` 腐烂率（机制性描述，decrease）。
- 不在 KG 中提供旧版药剂/熏蒸剂量建议；六六六等已淘汰/高风险内容未入图。
- 旧版中的吊挂、膜袋、果筐、缸藏、沟藏、棚窖、平房等方法暂未新增实体：现有 4 类业务标签和 35 个条件没有对应位置，且这些旧方法缺少可直接入指标的明确结论；避免产生孤立节点或把旧经验写成现代规范。
- 当前图谱口径（以 `scripts/report_stats.py` 为准）：**63 实体 / 45 来源 / 108 节点 / 125 关系（69 verified / 56 anchor）**；`validate_data.py` 0 errors / 2 warnings；测试数见 `README.md` §11（v1.4.1：418 passed / 2 skipped）。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts\fetch_agridata_grape.py all
.\.venv\Scripts\python.exe scripts\fetch_legacy_preserve.py
```
