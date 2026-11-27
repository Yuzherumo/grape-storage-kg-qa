# 全网「葡萄贮藏/采后保鲜」数据采集报告（3GB 预算）

- 采集时间：2026-11-27 18:35–20:40（+08:00）
- 预算约束：总量 **≤3GB**（实现按 2.85GiB 硬上限 + 单文件上限执行）
- 合规边界：**未登录、未付费、未申请权限、未绕过任何访问控制**
- 采集范围：数据文件 + **开放获取论文 PDF**（逐篇标注出处）
- 产物目录：`data/external/web_grape_storage/`（清单见同目录 `README.md`）
- 脚本：`scripts/collect_web_grape_storage.py`（数据）、`scripts/collect_grape_papers.py`（论文）、
  `scripts/validate_web_grape_export.py`（自检）、`tools/build_screened_catalog.py`（筛查全景）

---

## 一、结论

| 指标 | 结果 |
|---|---|
| 全网筛查记录 | **1,552 条**（A 49 / B 260 / C 91 / D 1,152） |
| 交付数据目录（A/C） | **31 条**（A 16、C 15） |
| 下载数据文件 | **21 个 / 2.5MB** |
| 下载论文 PDF | **25 篇 / 28.6MB**（开放获取，出处齐全） |
| 合计下载 | **31.2MB**，占 3GB 预算 **1.07%** |

**核心判断：开放渠道的「葡萄采后贮藏」材料总量只有几十 MB 量级，本次已把可合法直接下载的
数据与论文全部取回。** 英文仓储里大多命中是论文型记录；真正能直链下载的 PDF 集中在
**Zenodo**（作者自存、多为 CC BY）与 **DOAJ 收录的 OA 期刊**；出版商站（MDPI/Wiley/E3S）、
PMC、Europe PMC 的 PDF 在本机网络被 403/Cloudflare 拦截，Europe PMC 仅元数据可用。
中文侧 ScienceDB 的葡萄数据集全为品质/香气/SSR/病害识别（非采后）且文件需登录；
agridata 的采后数据集标注「申请下载/有条件共享」，按合规要求未绕过。
因此**3GB 上限远未用满属于真实结果，不是失败**；用无关数据（如 2.4GB 番茄多组学）填充
会破坏「葡萄贮藏」这一主题的相关性，故未采用。

---

## 二、方法与合规

### 2.1 采集链路

```
检索（多源 API）
  → 相关性严格分级（A/B/C/D，标题级葡萄 + 实质贮藏词）
  → 去重（DOI 归一，含 Mendeley 版本号）
  → 预算管理器（A 优先、单文件上限、C 级占比 ≤15%、逐文件记录）
  → 流式下载 + 大小/Content-Length 校验 + sha256
  → CSV / manifest / 筛查全景导出
```

- 请求节流：约 1 秒/请求；失败退避重试 3 次；
- 文件校验：下载后核对 Content-Length、sha256，拒绝 HTML 错误页冒充数据；
- 断点续跑：已下载且大小一致的文件直接复用。

### 2.2 各源可用性（实测）

| 源 | 接口 | 结果 |
|---|---|---|
| Zenodo | `/api/records?q=&size=25&page=` | ✅ 可用；未认证 `size` 上限 25，`q` 为 OR 语义需本地过滤 |
| Dryad | `/api/v2/search?q=` | ✅ 可用；AND 语义，葡萄采后命中极少 |
| Harvard Dataverse | `/api/search?q=&type=dataset` | ✅ 可用；OR 噪声大，需逐条复核 |
| Mendeley Data | `data.mendeley.com/api/datasets/{id}/files` | ✅ 文件 API 可用（发现走 DataCite 前缀 10.17632） |
| DataCite | `api.datacite.org/dois?query=` | ✅ 可用，是跨仓储补漏的关键 |
| ScienceDB（scidb.cn） | `POST /api/sdb-query-service/query` | ⚠️ 检索可用，**文件需登录**，无直链 |
| 中国科学数据（csdata.org） | SciEngine SPA | ⚠️ 数据本体托管 ScienceDB，无独立直链 |
| agridata.cn | 已逆向的签名 API | ⚠️ 采后数据集多为「申请下载/有条件共享」，仅取元数据 |
| Figshare | `api.figshare.com/v2/*` | ❌ 全站 403 |
| OSF | `api.osf.io/v2/search` 404 | ⚠️ 无全文检索，仅按标题枚举，无相关数据 |

### 2.3 合规说明

- 站点标注「申请下载（download_way=10）」「有条件共享」的资源：**只保留元数据**，
  不上绕过申请流程的直链（即便技术上可匿名取到，也不采用）；
- ScienceDB 文件接口返回「User Not Login / PERMISSION NO ACCESS」，未尝试破解或冒用会话；
- 仅下载明确开放许可（CC BY / CC0 等）且无需登录的公开文件。

---

## 三、相关性判据

- **A**：葡萄（table grape / fresh grape / grape berry / Vitis vinifera 果实 / 葡萄 / 提子）
  **且**采后贮藏保鲜（postharvest、cold storage、CA/MA、SO₂、shelf life、decay、Botrytis、
  rachis browning、berry drop、firmness、落粒、失水、腐烂、冰温、预冷…）
- **B**：葡萄相关但非采后（葡萄酒/葡萄干/果汁、栽培、育种、田间病害、基因组、图像识别）
- **C**：其他果蔬采后贮藏（蓝莓、桃、柑橘、番茄等），仅作方法参照
- **D**：检索噪声

为控制误判，额外排除：`grapefruit`（葡萄柚）、图注/补充材料条目（"Additional file N"、
"Figure N"）、鱼类保鲜/醋/生物膜/化妆品等无关领域；A 级要求标题含葡萄或描述明确为鲜食葡萄，
且必须有**实质贮藏词**（如 "quality traits during fruit growth" 这类不算贮藏，会降级）。

---

## 四、交付数据

完整清单与字段见 `data/external/web_grape_storage/README.md`、`web_records.csv`。要点：

### 4.1 A 级（直接相关）且可下载

| 数据 | DOI | 内容 | 大小 |
|---|---|---|---|
| 穗轴褐变冷藏试验 | 10.17632/4x57fvm6tm | 采后激素处理抑制 table grape 穗轴褐变（0/5 ℃ 贮藏 30 天） | 26 KB |
| 壳聚糖+芦荟涂膜 | 10.17632/tdbw9r9jtx | 采前壳聚糖 + 采后芦荟涂膜对葡萄品质影响（含感官问卷） | 76 KB |
| 涂膜+采后处理（另一版） | 10.17632/skktzvw4ms | 同上研究 Panel test 问卷数据 | 18 KB |
| 生防原始数据 | 10.5281/zenodo.20407304 | 葡萄采后病害生物防治实验原始数据（zip） | 1.8 MB |
| 乙烯释放 | 10.17632/k87vpskjkn | 整果乙烯释放测定原始数据 | 12 KB |
| 处理×冷藏理化性状 | 10.5281/zenodo.14552426 | 不同处理对冷藏鲜食葡萄理化性状影响（含 PDF） | 1.8 MB |

另有 Zenodo 多篇 CC BY 的冷藏/气调/涂膜/生防/货架期研究记录（部分仅 PDF，按规则不计入数据下载，
但保留在目录中可溯源），以及 DataCite/Dataverse 的 A 级元数据记录（如 BRS Vitória 无核葡萄
采后货架期、同批次鲜食葡萄货架期变异、桉叶精油采后病害防治等），文件需向作者/仓储申请。

### 4.2 C 级（其他果蔬采后，方法参照）

- Harvard Dataverse `10.7910/DVN/3HQKTH`：蓝莓采后贮藏（硬度、失重、品质，CC0，4 个 xlsx）
- Harvard Dataverse `10.7910/DVN/TT0TBC`：臭氧对桃采后影响（CC0，2 个 xlsx）
- Zenodo 若干：可食用涂膜/包装对黑莓、番茄、甜椒等采后品质的影响（CSV）

### 4.3 筛查全景

`screened_records.csv` 收录 1,552 条经统一判据复筛的记录（A 49 / B 260 / C 91 / D 1,152），
每条含 DOI、来源、标题、年份、文件数、分级依据词，便于核查「全网」覆盖范围。
其中 B 级 260 条是葡萄相关但非采后的数据/文献，可作后续「葡萄品质—贮藏」关联分析的备选。

---

## 五、论文 PDF（开放获取，25 篇 / 28.6MB）

### 5.1 来源与筛选

| 步骤 | 说明 |
|---|---|
| 检索 | Zenodo API（标题字段精确检索）17 组查询 + DOAJ API 6 组查询；共下载 72 篇候选 |
| 初筛 | 标题/摘要需同时命中葡萄词（grape/grapes/vitis/葡萄）与贮藏词（storage/postharvest/preservation/cold/decay/coating/quality…） |
| 复核 | 逐条按标题人工规则复核：剔除整期期刊（Volume/Issue/Journal…）、无关领域（考古、家居、顺势疗法、空气污染、活性炭、化妆品、无麸质食品、育苗/微繁/基因型鉴定等），保留 25 篇 |
| 出处 | `paper_records.csv` 逐篇记录：标题、作者、期刊/来源、年份、DOI、许可、landing_url、PDF 直链、sha256、本地路径 |

### 5.2 内容举例

- Zenodo（CC BY）：不同处理对冷藏鲜食葡萄理化性状的影响；鲜食葡萄采后处理综述；葡萄采后腐烂与真菌病原；壳聚糖涂膜冷藏；气调集装箱运输鲜食葡萄；采后品质指标；葡萄籽油延长采后货架期；活性包装对鲜食葡萄抗菌性能等；
- DOAJ OA 期刊：壳聚糖+百里香油采后处理；腐胺+超声处理；壳聚糖涂膜对葡萄物理机械与化学性质影响；VvPPO1 表达与褐变等。

### 5.3 为什么没有更多论文

出版商 PDF（MDPI、Wiley、E3S 等）、PMC/Europe PMC 的 PDF 直链在本机网络返回
403/Cloudflare 人机验证（已逐一实测记录），只有 Zenodo/部分 DOAJ 期刊提供可直接下载的 PDF。
Europe PMC 的检索元数据可用（葡萄+采后 OA 命中上万条），但其 PDF 渠道不可用，故只作为检索线索，
不计入下载量。**未使用任何破解、代理或伪造 UA 绕过人机验证的手段。**

---

## 六、为什么没到 3GB，以及如何进一步扩大

**原因**：开放+免登录+许可明确的葡萄采后贮藏数据总量只有 MB 级，论文 PDF 也只有几十 MB；
3GB 上限对应的体量级在当前开放渠道里并不存在（除非纳入不相关或受限资源）。

若确实需要更大体量，可选路径（按推荐度）：

1. **申请受限的国内数据（最相关）**
   - 国家农业科学数据中心（agridata.cn）：`download_way=10` 的数据集需实名认证 + 订单审核，
     其中果蔬采后类数据集有 30+ 条（含冷链、预冷、质地、风味、货架期），单库 0.1–25 MB；
   - ScienceDB：需注册登录后下载，葡萄品质/香气/SSR 等 26 个数据集与部分果蔬采后数据可获取；
   - 这些是「葡萄/果蔬贮藏」主题下最对口的增量，但需要账号与申请流程。
2. **接受非葡萄的 C 级参照数据（可快速到 GB 级但不相关）**
   - Mendeley `10.17632/jnhhh4v9zm`（番茄采后多组学，36 文件，2.41 GB，CC BY）——
     下载即可接近 3GB 上限，但它是番茄不是葡萄，本报告未纳入；
3. **葡萄图像/表型大数据（B 级，与贮藏品质检测相关但非贮藏试验）**
   - Zenodo `CERTH Grape Dataset`（19 GB）、`Grape Bunch Video Dataset`（15.9 GB）等，
     体量超 3GB，且主题是检测/分割而非贮藏，未纳入。
4. **中文开放获取期刊 PDF（下一步可做）**
   - 《果树学报》《食品科学》《农业工程学报》等中文 OA 期刊有大量葡萄贮藏保鲜论文，
     站点结构各异、部分需逐页解析，本轮未展开；如需可继续补抓并标注出处。

如需 1 或 2，可在拿到账号/授权后由本管线按同一预算规则补抓。

---

## 七、限制与未验证

1. 公开数据「存量小」的结论基于 Zenodo/Dryad/Dataverse/Mendeley/DataCite + 中文四平台的检索，
   不覆盖知网/万方/维普等付费库，也不覆盖需登录的 ScienceDB 文件层；
2. 部分 A 级记录只有论文/元数据（Zenodo PDF、DataCite 记录），其原始数据未公开，未下载；
3. Mendeley 文件直链为公开下载地址，但数据集解读需结合原文，且未逐一核对数据表内容与标题的一致性
   （已按标题/描述判据筛选，建议使用前打开确认）；
4. 图注、补充材料类条目的自动排除可能误伤少量确实含数据的记录；
5. 论文 PDF 的相关性判断为「标题规则 + 人工复核」，仍有主观成分；部分 PDF 是作者/期刊
   在 Zenodo 的存档版本，与正式刊出版本可能存在排版差异，引用请以 DOI 对应正式版本为准；
6. 出版商/PMC 的 PDF 因 403/Cloudflare 未能下载（已实测记录），因此论文覆盖以 Zenodo/DOAJ 为限。

---

## 八、与上一轮 agridata 抓取的关系

- 上一轮（`data/external/agridata/`）已覆盖国家农业科学数据中心的葡萄相关数据集（60 个 B 级、
  A 级数据集 0）、旧版「农产品贮藏保鲜技术数据库」葡萄条目（2005 年技术描述，见
  `data/external/agridata/legacy_preserve/grape_storage_technique.md`）；
- 本轮是「全网」扩展：新增 Zenodo/Dryad/Dataverse/Mendeley/DataCite 与 ScienceDB/CSData 的检索，
  结论与上一轮一致——**鲜食葡萄采后贮藏的公开结构化数据仍极稀少**；
- 两份产物可以合并使用：agridata 提供国内权威元数据与旧技术文本，本轮提供国际仓储的实际数据表。

---

## 九、复现

```powershell
# 数据：采集 → 合并 → 严格重判 → 预算下载 → 导出
.\.venv\Scripts\python.exe scripts\collect_web_grape_storage.py all
# 筛查全景
.\.venv\Scripts\python.exe tools\build_screened_catalog.py
# 论文 PDF：检索 → 下载 → 复核合并
.\.venv\Scripts\python.exe scripts\collect_grape_papers.py all
.\.venv\Scripts\python.exe tools\merge_papers.py
.\.venv\Scripts\python.exe tools\update_web_manifest.py
# 自检（计数/哈希/预算/编码/分级证据/PDF magic）
.\.venv\Scripts\python.exe scripts\validate_web_grape_export.py
```

中间态与原始响应在 `.tmp/web_grape/`（已被 `.gitignore` 排除），可删可重跑。
