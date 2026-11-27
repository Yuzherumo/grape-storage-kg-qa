# 国家农业科学数据中心「鲜食葡萄采后储藏」数据抓取报告

- 抓取时间：2026-11-27 15:02–15:45（+08:00）
- 抓取对象：<http://www.agridata.cn>（国家农业科学数据中心）、<http://www.agridata.ac.cn>（北京农业数字信息资源中心，原 8888 端口旧站）
- 运行环境：Windows 11 + Python 3.12.14（项目 `.venv`；纯标准库实现，无第三方依赖）
- 是否登录：**未登录、未注册、未提交任何数据下载申请**
- 抓取代码：`scripts/fetch_agridata_grape.py`、`scripts/fetch_legacy_preserve.py`、`tools/agridata_client.py`、`tools/agridata_crypto.py`

---

## 一、结论先说

| 问题 | 结论 |
|---|---|
| 主站（agridata.cn）有没有「鲜食葡萄采后贮藏」专门数据集？ | **没有。** 45 个检索词、253 次检索请求、5408 条去重命中里，**A 级（名称/关键词为葡萄且含采后贮藏词）数据集 = 0 条** |
| 最接近的是哪些？ | ① 1 条**国家自然科学基金项目**「鲜食葡萄果穗采运全周期的落粒-伤粒生物力学机制与规律研究」；② 60 条**葡萄数据集**（栽培/品质/病害/种质，非采后）；③ 38 条**其他果蔬采后**数据集（苹果、荔枝、竹笋、鲜切猕猴桃等，可做方法参照） |
| 用户给的旧站 `advanced_search.aspx?TITLE=保鲜技术` | **8888 端口服务已整体不可用**（根路径、检索页、default.aspx 全部 HTTP 500）。同一机构 80 端口站点仍在线，改用其「农业专题数据库 → 农产品贮藏保鲜技术数据库」抓取 |
| 该旧库里有葡萄吗？ | **有，1 条，内容完整**：葡萄贮藏保鲜技术（10 种贮藏方式、SO₂ 熏蒸剂量、过氧化钙/仲丁胺保鲜、好果率等），见 `data/external/agridata/legacy_preserve/grape_storage_technique.md` |
| 用户给的 DOI `10.12205/A0002.20230228.00.ds.3476` | 已解析：Handle 记录指向旧路由 `data.html#/datadetail?id=291300`（该路由已 404），实际数据集为**郑州果树所「2012—2017 年优势产区落叶果树农家品种资源调查数据集」**（id=291300，15MB，CC BY-NC-ND），**属种质资源调查，不是采后贮藏数据**；文件未取到（见 §5） |

**一句话交付**：站点上没有现成的「鲜食葡萄采后储藏」数据集；本次可用的直接材料是旧站「农产品贮藏保鲜技术数据库」里那 1 条葡萄条目，其余葡萄数据都在栽培/品质/病害/种质方向，已按 A/B/C 分级整理成表，每条都带 gid、CSTR/DOI、来源 URL 与判定依据。

---

## 二、主站（agridata.cn）怎么抓的

站点是 jQuery + Vue 的混合前端，`/api` 请求都套一层签名信封（逆向前端 `frontend/js/request.js`、`common.js` 得到）：

```json
POST /api/app/dataset/search/list
{
  "common": {
    "appId": "947bc872d4134a91a0ffaedac05fdb14",
    "timestamp": "<毫秒>", "nonce": "<6位>", "encrypted": false,
    "appToken": "md5(appId + aes16 + timestamp + nonce)",
    "aes16": "RSA_PKCS1v15(aes16, 站点公钥) → base64"
  },
  "json": { "resourceType": "DATASET_INFO", "custom": {"searchText": "...", "filter": []},
            "pageNumber": 1, "pageSize": 100 }
}
```

服务端把 `{code,data}` 信封整体加密后再 base64 放进外层 `data` 字段，密钥就是本次请求自造的 `aes16`（AES-128-ECB + PKCS#7），因此客户端必须自己持有 `aes16` 才能解出数据 —— 这也是纯 `requests` 直接抓会拿到密文的原因。

本项目用**纯标准库**复现了这条链路（`tools/agridata_crypto.py`）：

- DER 解析 SubjectPublicKeyInfo 取 `(n, e)`，手写 PKCS#1 v1.5 填充 + `pow(m, e, n)`，行为对齐前端 `jsencrypt`；
- AES-128-ECB 解密（S 盒按定义生成，用 FIPS-197 C.1 官方向量自检 `self_test()`）；装了 `cryptography` 时自动走 OpenSSL 快路径（大数据集回包快 3 个数量级）。

关键接口：

| 用途 | 接口 |
|---|---|
| 数据集检索 | `POST /api/app/dataset/search/list` |
| 分面过滤 | `POST /api/app/dataset/search/facet`（过滤字段用 `property_right_unit_facet`、`keywords_facet`、`data_type` 等） |
| 数据集详情 | `POST /api/app/dataset/detail/{resource_type}/{gid}` |
| 公开文件直链 | 检索记录 `hj_entity_url`（仅 `download_way ∈ {0,5}` 有直链） |

礼让措施：每次请求间隔约 1 秒 + 0–0.5 秒抖动；`robots.txt` 仅 `Disallow: /console/`，本次未访问 `/console/`，未登录、未申请下载。

---

## 三、检索口径与覆盖

45 个检索词，分四组（`scripts/fetch_agridata_grape.py` 中 `QUERIES`）：

| 组 | 关键词 | 说明 |
|---|---|---|
| grape | 葡萄、鲜食葡萄、提子 | 兜底全量葡萄命中（站点检索为模糊匹配，含 OR 语义） |
| grape_postharvest | 葡萄 贮藏 / 储藏 / 保鲜 / 采后 / 冷藏 / 预冷 / 气调 / 二氧化硫 / 货架期 / 冷链 / 耐贮 / 保鲜剂 / 贮藏保鲜 / 采后生理 / 腐烂 / 落粒 / 冰温 / 熏硫 / 保鲜纸 / 果梗 / 穗轴 / 灰霉病，以及鲜食葡萄 贮藏 / 保鲜 | 针对采后场景 |
| postharvest_general | 果实 采后、果蔬 保鲜、贮藏保鲜、二氧化硫 保鲜、保鲜剂、冷链物流、货架期、预冷 | 找其他果蔬采后数据做对照（只取前 3 页，不穷举） |
| cultivar | 阳光玫瑰、夏黑、巨峰、红地球、美人指、克瑞森、无核白、火焰无核、妮娜皇后、蓝宝石葡萄 | 数据集常以品种命名而不写「葡萄」二字，补漏 |

结果：**253 次检索请求 → 5408 条去重命中**（站点同一接口会混入「国家自然科学基金项目库」等非数据集记录：数据集 4486 条、科研项目 922 条）。另有 154 条抓取了详情元数据（成功率 100%）。

---

## 四、相关性分级与结果

判据全部落到 `evidence_*` 字段，可逐条复核（见 `data/external/agridata/datasets_grape_postharvest.csv`）：

| 级别 | 判定规则 | 结果 |
|---|---|---|
| A | 名称或关键词明确是葡萄/主栽品种 **且** 出现采后贮藏词（采后/贮藏/保鲜/冷藏/气调/SO₂/货架期/落粒/腐烂…） | **1 条，且是科研项目，不是数据集** |
| B | 名称或关键词是葡萄/主栽品种，但主题不是采后贮藏 | 71 条（数据集 60 + 项目 11） |
| C | 果蔬类采后贮藏，但主体不是葡萄 | 39 条（数据集 38 + 项目 1） |
| D | 其余（含「仅在简介里顺带提葡萄」、稻麦种子耐储藏、渔港名录等） | 5297 条（保留在 `datasets_all_hits.csv` 供审计） |

为避免中文同词误导，专门做了三处排除（都在代码注释里写明）：

1. `葡萄糖 / 葡萄球菌 / 葡萄膜炎 / 葡萄孢 / 葡萄牙` 不算葡萄 → 否则「葡萄糖代谢」「灰葡萄孢」「葡萄牙农业数据」会被误判；
2. `贮藏营养 / 越冬贮藏 / 枝条贮藏` 不算采后贮藏 → 否则「葡萄砧木枝条贮藏营养数据集」会被误判为 A 级；
3. C 级要求「果蔬语境」→ 否则水稻种子耐储藏、甘薯块根储藏会被算成采后。

**A 级那一条**（唯一直接命中）：

> 鲜食葡萄果穗采运全周期的落粒-伤粒生物力学机制与规律研究（国家自然科学基金项目库，起始 2019-01-01）
> 关键词：力学与动力学分析；生物力学特性；落粒-伤粒；葡萄果穗；采运全周期

它说明「鲜食葡萄采后落粒/伤粒」在基金项目层面确有研究，但站点没有对应的公开数据集。

---

## 五、两个用户给定入口的核查结果

### 5.1 `http://www.agridata.ac.cn:8888/Web/advanced_search.aspx?TITLE=保鲜技术`

- DNS 正常（`www.agridata.ac.cn → 123.127.162.175`），但 **8888 端口整站 500**：`/`、`/Web/`、`/Web/advanced_search.aspx`（GB2312/UTF-8 两种参数编码）、`/Web/default.aspx` 全部返回 `HTTP 500 Internal Server Error`（393 字节错误页）。
- 同机构 **80 端口仍在线**（`http://www.agridata.ac.cn/Web`，北京农业数字信息资源中心），但它没有旧版那种按标题检索的入口，只有分类目录：`POST /DataList/GetInfo`（目录树）+ `POST /DataList/GridnewsListJson`（栏目列表）。
- 该目录里「贮藏加工与营养保健 → **农产品贮藏保鲜技术数据库**」（tableID=102）保存了 187 条果蔬贮藏记录，表结构为：`果蔬类别 | 果蔬名称 | 贮藏特性 | 贮藏方法 | 主要贮藏病害及防治 | 上市质量标准`。
- 其中 **葡萄条目 1 条（row id=12）**，原文包含 10 类贮藏方法：吊挂、膜袋、果筐、缸藏、沟藏、棚窖、平房、冷库、SO₂ 处理、防腐保鲜剂；含具体剂量（硫磺 1.5–2 g/m³、2–3 g/m³、2–4 g/m³；SO₂ 0.5% 帐容积；仲丁胺 1 g/2 kg；过氧化钙 1 g/2 kg；CT 保鲜片 3 kg 果 5 片）、温湿度（−1.5–0 ℃、RH 90%–92%）与好果率（95%、98.5%）等。
- 整理稿：`data/external/agridata/legacy_preserve/grape_storage_technique.md`；结构化 CSV：`preserve_db_grape.csv`；全库：`preserve_db_all.csv`。

> ⚠️ 该库入库日期为 2005 年，属**面向生产的旧版技术描述**，SO₂ 剂量等须与现行标准（如 GB/T 16862《鲜食葡萄冷藏技术》、NY/T 1046 等）核对后使用。

### 5.2 `https://dx.doi.org/10.12205/A0002.20230228.00.ds.3476`

解析过程（全部为真实请求）：

| 通道 | 结果 |
|---|---|
| `https://dx.doi.org/10.12205/A0002.20230228.00.ds.3476` | HTTP 600 页面「DOI Cannot Connect to Server」——DOI 已注册，但目标服务器连不上 |
| `https://hdl.handle.net/api/handles/10.12205/A0002.20230228.00.ds.3476` | ✅ 返回 URL 值 `https://www.agridata.cn/data.html#/datadetail?id=291300` |
| `https://api.datacite.org/dois/...`、`api.crossref.org/works/...` | 均 404（该前缀不在 DataCite/Crossref） |
| 旧路由 `https://www.agridata.cn/data.html` | 已 404（新站改为 `/dataset/detail/{type}/{gid}`） |
| 用 CSTR 片段反查站内索引 | 命中 `CSTR:17058.11.A0002.20230221.00.ds.3476`，再取详情，`id == 291300` **实测确认与 Handle 目标一致** |

结论数据集（详见 `data/external/agridata/doi_resolution.json`）：

- 名称：**2012—2017 年优势产区落叶果树农家品种资源调查数据集**
- gid：`ac6ee8c3ba4e41129e941e277da32a01`；站内 id：`291300`；CSTR：`CSTR:17058.11.A0002.20230221.00.ds.3476`；DOI：`10.12205/A0002.20230228.00.ds.3476`；发布日期 2023-02-21
- 产权单位：中国农业科学院郑州果树研究所（A0002 = 郑州果树所）；15MB；下载方式「在线下载」；许可 **CC BY-NC-ND**
- 与本任务关系：**弱 / 非采后方向**。它是落叶果树（含葡萄）农家品种的种质资源与植物学性状调查；站内另有葡萄子集「2012-2017年全国落叶果树农家品种（葡萄）资源照片」（`CSTR:17058.11.A0002.20201216.22.ds.0029`），属照片资料。
- 文件下载：站点给出 `/ProcessDic/…638805017693812360.zip`，实测 `www.agridata.cn/file/…`、`/api/app/file/download/…` 均返回 404/「文件不存在」，`a.agridata.cn/...` 返回 403 —— 需登录态或文件已迁移，本次未登录故**只保留元数据，未取得 15MB 原文件**（已如实记录在 `doi_resolution.json` 的 `file_download` 字段）。

---

## 六、产出清单

目录：`data/external/agridata/`（详见同目录 `README.md`）

| 文件 | 内容 |
|---|---|
| `datasets_grape_postharvest.csv` | A/B/C 共 111 条，含判定依据、来源链接、CSTR/DOI、下载方式、许可 |
| `datasets_relevant_only.csv` | 上述中的数据集 98 条 |
| `projects_literature_relevant.csv` | 上述中的科研项目 13 条 |
| `datasets_tier_a.csv` | A 级 1 条（附证据字段） |
| `datasets_all_hits.csv` | 5408 条全量命中（含 D 级，供审计与复算） |
| `grape_datasets_index.md` | 人读索引：A 级单列、B 级按主题（种质/栽培/病虫害/品质/采后）分组、C 级参照 |
| `search_hit_pairs.csv` | 24322 行「关键词 ↔ gid」对应关系 |
| `details/<gid>.json` | 154 条详情原始回包 |
| `files/` | 6 个公开直链文件（葡萄果实性状、水分需求、砧木营养、酿酒葡萄矿质、巨峰葡萄园土壤、苹果品质） |
| `legacy_preserve/` | 旧站贮藏保鲜库：全库 187 条、葡萄 1 条、可读整理稿 |
| `doi_resolution.json` | DOI 解析全链路证据 |
| `manifest.json` | 抓取参数、计数、策略、产出对账 |

数值对账（`manifest.json`）：唯一命中 5408 = A 1 + B 71 + C 39 + D 5297；记录类型 = 数据集 4486 + 项目 922；详情成功 154/154；文件成功 6/6。

---

## 七、复现

```powershell
# 主站：检索 → 分级 → 详情 → 按详情复核 → 下载公开文件 → 导出
.\.venv\Scripts\python.exe scripts\fetch_agridata_grape.py all

# 只补某一组检索词（可选：grape / grape_postharvest / postharvest_general / cultivar）
.\.venv\Scripts\python.exe scripts\fetch_agridata_grape.py search --groups cultivar

# 旧站贮藏保鲜库（含葡萄条目整理稿）
.\.venv\Scripts\python.exe scripts\fetch_legacy_preserve.py

# 客户端加解密自检（FIPS-197 向量）
.\.venv\Scripts\python.exe tools\agridata_crypto.py
```

中间态与原始回包在 `.tmp/agridata/`（已被 `.gitignore` 排除），可删可重跑。

---

## 八、限制与未验证项（如实声明）

1. **主站检索是模糊匹配**（多词近似 OR），5408 条命中里 D 级 5297 条噪声；结论「A 级数据集 0 条」依赖分级规则，规则已写进代码与本报告，可复核或按需调整。
2. **葡萄登录/申请后可见的数据未覆盖**：站点 `download_way=10`（申请下载）的葡萄数据集需实名认证 + 订单审核，本次按合规要求未申请，这些数据集的原始文件未获取。
3. **旧站 8888 端口不可用**，无法核对用户原链接页面的检索结果；80 端口同库内容已抓，但不能保证与旧版 advanced_search 的检索范围等价。
4. **DOI 目标文件未取得**（见 §5.2），且 DOI 官方解析（doi.org）当前本身报「Cannot Connect to Server」，不是本地网络问题。
5. 旧站葡萄条目为 **2005 年生产性描述**，不是试验观测数据，剂量/温湿度需按现行标准复核；其「主要贮藏病害及防治」「上市质量标准」两字段在原库为空。
6. 站点未提供数据集的完整字段级数据字典；CSV 字段含义取自详情接口原始键名（如 `sci_identification` = 科技资源标识符 CSTR，`data_set_doi` = 数据集 DOI）。

---

## 九、版权与使用

- 主站数据集的许可各不相同，CSV 的 `usage_notes` 列保留站点原文（例如 DOI 数据集为 CC BY-NC-ND 4.0），使用前请以各数据集详情页声明为准；站点整体要求标注来源（原始 `refer_standard`/`thankWay` 字段已保留在 CSV 中）。
- 旧站（北京农业数字信息资源中心）页面标注「版权所有：北京市农林科学院农业信息与经济研究所」，抓取内容仅供研究引用，转载/商用需另行获得许可。
- 本次抓取遵守站点 `robots.txt`（仅禁止 `/console/`），全程未登录、未注册、未提交下载申请，未对站点造成写操作。
