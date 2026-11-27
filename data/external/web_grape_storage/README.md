# 全网鲜食葡萄采后贮藏数据采集（≤3GB 预算）

- 采集时间：2026-11-27 18:35–19:20（+08:00）
- 数据源：Zenodo、Dryad、Harvard Dataverse、Mendeley Data、DataCite（跨仓储目录），
  以及队友对 ScienceDB（scidb.cn）、中国科学数据（csdata.org）、国家农业科学数据中心（agridata.cn）的侦察
- 合规：**未登录、未付费、未申请任何权限**；站点标注「申请下载 / 有条件共享」的资源只保留元数据
- 预算：总上限 2.85 GiB（硬性低于 3GB）、单文件 ≤400 MiB

## 结论速览

| 指标 | 数值 |
|---|---|
| 全网筛查记录 | **1,552 条**（A 49 / B 260 / C 91 / D 1,152） |
| 交付数据目录（A/C 且带可下载文件或受限元数据） | **31 条**（A 16、C 15） |
| 下载的数据文件 | **21 个 / 2.5 MB** |
| 下载的论文 PDF | **25 篇 / 28.6 MB**（开放获取，逐篇标注出处） |
| 合计下载 | **31.2 MB**，占 3GB 预算 **1.07%** |
| 数据文件类型 | xlsx / csv / txt / zip；论文为 PDF |

**为什么只有 31 MB？** 开放、免登录、许可明确的「葡萄采后贮藏」材料总量本来就只有这个量级：
英文仓储里大多命中是论文型记录，真正可直接下载的 PDF 集中在 **Zenodo**（作者自存）与
**DOAJ 收录的 OA 期刊**；出版商站（MDPI/Wiley/E3S）、PMC、Europe PMC 的 PDF 在本机网络
被 403/Cloudflare 拦截，无法下载（已如实记录，不伪造成功）。中文 ScienceDB 的葡萄数据集
全为品质/香气/SSR/病害识别（非采后）且文件需登录；agridata 的采后数据集标注
「申请下载/有条件共享」，本次不绕过申请流程。**3GB 是上限而不是目标**，用无关数据
（如 2.4GB 番茄多组学）填充只会破坏相关性。

## 文件说明

| 文件 | 内容 |
|---|---|
| `web_records.csv` | 交付数据目录 31 条：tier、来源、DOI、标题、许可、access（open/apply）、证据词、本地文件 |
| `web_records_tier_a.csv` | 其中 A 级 16 条（直接相关：葡萄 × 采后贮藏） |
| `web_files.csv` | 已下载 21 个数据文件：URL、字节、sha256、本地路径、许可 |
| `download_skipped.csv` | 跳过/失败明细（含原因） |
| `screened_records.csv` | **筛查全景 1,552 条**（A/B/C/D），用于核查覆盖范围 |
| `paper_records.csv` | **论文 25 篇**：标题、作者、期刊、年份、DOI、许可、landing_url、PDF 直链、sha256、本地路径 |
| `papers/<source>/` | 论文 PDF 文件 |
| `files/<source>/<doi>/` | 实际数据文件 |
| `manifest.json` | 计数、预算（含论文）、各源统计、合规策略 |

## 相关性分级

- **A**：葡萄（table grape / fresh grape / Vitis 果实 / 葡萄）且采后贮藏保鲜（postharvest、cold storage、
  CA、SO₂、shelf life、decay、rachis browning、berry drop、firmness、落粒、失水、腐烂…）
- **B**：葡萄相关但非采后（葡萄酒/葡萄干/果汁、栽培、育种、田间病害、基因组、图像识别）
- **C**：其他果蔬采后贮藏（蓝莓、桃、柑橘、番茄等），仅作方法参照
- **D**：检索噪声（README 中「葡萄」字样以外的同词异义、无关领域）

判据要求标题含葡萄（或描述明确为鲜食葡萄），且标题/描述有**实质贮藏词**；
并排除 `grapefruit`、图注/补充材料条目、鱼类/醋/生物膜等无关领域。

## 主要命中（A 级，可下载数据的）

| 类型 | 来源 | 内容 | 大小 |
|---|---|---|---|
| 数据集 | Mendeley `10.17632/4x57fvm6tm` | 采后激素处理抑制鲜食葡萄穗轴褐变（冷藏 30 天） | 26 KB xlsx |
| 数据集 | Mendeley `10.17632/tdbw9r9jtx` | 壳聚糖 + 芦荟涂膜对采后葡萄品质的影响（含感官问卷） | 76 KB xlsx |
| 数据集 | Mendeley（另一版本） | 同上研究的 Panel test 问卷数据 | 18 KB xlsx |
| 数据集 | Zenodo `10.5281/zenodo.20407304` | 葡萄采后病害生物防治原始实验数据 | 1.8 MB zip |
| 数据集 | Mendeley `10.17632/k87vpskjkn` | 整果乙烯释放测定原始数据（乙烯与贮藏寿命相关） | 12 KB xlsx |
| 论文附带数据 | Zenodo `10.5281/zenodo.14552426` | 不同处理对冷藏鲜食葡萄理化性状影响（PDF 文章 + 数据） | 1.8 MB |
| 论文附带数据 | Zenodo（多篇） | 冷藏/气调/涂膜/生防/货架期研究（CC BY） | 各 0.3–1.6 MB |

C 级参照：Harvard Dataverse 蓝莓采后贮藏（硬度、失重、品质，CC0）、臭氧对桃采后影响（CC0）等。

## 论文 PDF（25 篇，逐篇标注出处）

`paper_records.csv` 每篇给出：标题、作者、期刊/来源、年份、DOI、许可、landing_url、
PDF 直链、sha256、本地路径。全部来自**开放获取**渠道：

- **Zenodo**（作者/期刊自存，多为 CC BY）：如「不同处理对冷藏鲜食葡萄理化性状的影响」
  「鲜食葡萄采后处理综述」「葡萄采后腐烂与真菌病原」「壳聚糖涂膜冷藏」「气调集装箱运输」
  「采后品质指标」「葡萄籽油延长采后货架期」等；
- **DOAJ 收录 OA 期刊**中给出可直接下载 PDF 的论文：如壳聚糖/百里香油采后处理、
  腐胺+超声处理、壳聚糖涂膜对葡萄物理机械与化学性质的影响、VvPPO1 与褐变等。

被排除的 47 篇（整期期刊、无关领域、仅元数据）已移到 `.tmp/web_grape/papers_rejected/`，
不进入交付清单。**引用时请按 DOI/期刊信息标注原始出处**，本仓库只做采集与整理。

## 使用注意

- 各文件许可以记录 `license` 列为准（多为 CC BY 4.0 / CC0）；引用数据请保留 DOI，
  引用论文请按 `paper_records.csv` 的期刊/作者/年份标注原始出处（本仓库只做采集整理，不替代原刊引用）。
- Mendeley Data 的文件直链为公开下载地址，但**数据集本身仍是论文配套数据**，解读需结合原文。
- 中文受限资源的获取途径见 `docs/web_grape_storage.md` 的「如何进一步扩大数据量」。

## 接入知识图谱（2026-11-27）

- 25 篇开放获取论文已登记为 `data/sources.csv` 的 `web_*` 来源（论文类型）；题录/DOI/许可/本地文件见 `paper_records.csv`。
- `dataset_index.csv` 把 5 个可下载数据集映射到条件/指标，作为后续 Dataset 节点的候选；本轮未把数据集标题直接当事实。
- 从 6 篇可对应现有 schema 的论文中抽取 6 条 `AFFECTS` anchor：壳聚糖涂膜→耐贮性/腐烂率、百里香精油涂膜→腐烂率、腐胺+超声→耐贮性、葡萄籽油→失重率、气调集装箱运输→耐贮性；新增 5 个 `Condition` 实体。
- 论文中的涂膜/精油/超声等处理浓度与品种差异较大，本轮不把摘要数值直接升级为 verified，也不把处理后数据与本地标准参数混合。
- 当前图谱：63 个知识实体、125 条关系、45 条来源（108 节点，69 verified / 56 anchor）；`validate_data.py` 0 errors / 2 warnings；测试数见 `README.md` §11（v1.4.1：418 passed / 2 skipped，覆盖率 83%）。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts\collect_web_grape_storage.py all
.\.venv\Scripts\python.exe tools\build_screened_catalog.py
.\.venv\Scripts\python.exe scripts\collect_grape_papers.py all
.\.venv\Scripts\python.exe tools\merge_papers.py
.\.venv\Scripts\python.exe tools\update_web_manifest.py
.\.venv\Scripts\python.exe scripts\validate_web_grape_export.py
```
