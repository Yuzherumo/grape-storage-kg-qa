# 鲜食葡萄储藏知识图谱问答（葡萄冷库「能查证」的技术助手）

> 农客松 2026 · 主赛道 · **方向二「生命系统」**（农业 / 食品）
> 状态：M9 综述入源 ｜ 测试 `118 passed / 2 skipped` ｜ 图谱 **74 节点 / 108 条关系**｜**61 条 verified（国标条文 51 + 综述原文 10）** ｜ 数据 **十项校验** 全绿 ｜ **无 API Key、断网也能跑** ｜ 在线模式已实测（`deepseek-chat`，1.3~2.8 s/题）
> 演示地址：`http://127.0.0.1:8501`（`.\run.ps1` 一键启动）

---

## 1. 它解决什么问题

鲜食葡萄采后损耗，大多不是「没有技术」，而是**规范没人读得下去**：国标和综述里写清了温度、湿度、SO₂ 禁忌、灰霉处置，但一线的人手里只有一句「大概放冷库吧」。

本作品把规范拆成**可查询、可溯源、可冲突表达**的知识图谱，再让大模型**只能引用图谱证据**回答，输出「结论 + 依据 `[E#]` + 现在该做什么」。

| 谁在用 | 什么场景 | 他会怎么问 | 系统给什么 |
|---|---|---|---|
| 种植户 / 合作社 | 采后待入库，参数不会设 | 「阳光玫瑰放冷库该调到多少度？」 | 温度区间 + 预冷时限 + 分步操作 + 来源 |
| 冷库管理员 | 贮藏期发现霉 / 发软 / 掉粒 | 「冷库里葡萄长白毛了怎么办？」 | 最可能病害 + 立即处置 + 诱因规避 |
| 采购 / 质检 | 到货判残值与剩余货架期 | 「和巨峰比哪个更耐放？」 | 品种耐贮性基线 + 判定指标 |
| 农技员 / 学生 | 学习对比、写材料要引用 | 「SO₂ 熏蒸对阳光玫瑰安全吗？」 | 禁忌 + 争议来源并列 + 替代方案 |

## 2. 30 秒跑起来

```powershell
# 1) 首次：一键安装环境（自动找 Python 3.10+、建 .venv、装依赖、跑数据/Cypher 校验）
.\install.ps1

# 2) 一键启动（数据十项校验 → Cypher 静态校验 → 图谱自检 → 起服务）
.\run.ps1
#    → http://127.0.0.1:8501

# 只想自检、不启动服务
.\run.ps1 -Check
```

> 打包/换机器：`.\scripts\make_release.ps1` 生成不含密钥与 PDF 的干净快照（见 [packaging.md](docs/packaging.md)）。
> **公网 Demo**：三种上线方式（Streamlit Cloud / 魔搭创空间 / 本地内网穿透）见 [deploy.md](docs/deploy.md)；临时公网地址可跑 `.\scripts\run_public_tunnel.ps1`。
> `install.ps1` 已处理「打包版 Python 无 ensurepip」的情况（改用基础解释器的 `pip --python` 安装）。

没有 API Key 也能完整演示：系统自动进入**离线模板模式**，答案仍带 `[E#]` 引用、来源与分步动作。
要启用 DeepSeek 在线生成：把 key 填进 `.env` 的 `DEEPSEEK_API_KEY`（见 `.env.example`；`.env` 不进仓库、不进交付包）。

## 5. 界面（参考 DeepSeek 网页版）

- 左侧极简侧栏：新建对话、后端/模型状态、设置（离线/大字/Top-K/Cypher）、图谱规模与词表、最近提问；
- 中间单列对话流（约 820px）：用户消息右侧浅蓝气泡，助手回答正文 + 「依据 · N 条证据」可折叠卡片（`[E1]` 角标、已核验/待核验标签、来源与条款）；
- 底部圆角输入框与建议问题卡片；浅色/深色跟随系统，大字模式适配投影与农户。

## 5.1 架构与关键设计

```
用户提问（农户口语：青提搁冷库多少度 / 长白毛咋办）
  → 归一化（全角、语气词、₂→2）
  → 实体链接  app/linking.py     词典最长匹配 + 拉丁词边界 + 口语别名 + 症状词
  → 意图路由  app/planner.py     触发词加权 → 实体先验 → 句式模式 → 低分澄清
  → 参数化查询 app/store/         LocalStore（纯标准库）/ Neo4jStore（Cypher 模板）
  → 证据 Evidence                 三元组 + 值 + 来源(s) + 定位 + 状态 + 置信
  → 生成      app/qa.py           DeepSeek（OpenAI 兼容）或离线模板
  → 后校验                         引用校验 + 数值一致性（单位/区间/越界）
  → AnswerResult                  app/ui.py 渲染（证据表 / Cypher / 大字模式）
```

| 决策 | 为什么 | 位置 |
|---|---|---|
| **规则优先、LLM 只做翻译** | 实体与意图可确定性测试；40 分完成度不被 API 稳定性拖累 | `planner.py` / `qa.py` || **双后端，本地优先** | 现场无 Neo4j/Docker 也能跑；Cypher 脚本按交付要求完整提供 | `app/store/` |
| **数据单一真相** | CSV → Cypher 生成，杜绝两边改漏 | `scripts/gen_cypher.py` |
| **条级溯源 + anchor/verified 双档** | 与国标条文逐字对应的升 `verified`（带条款号+原文摘录），拿不到原文的标「待核验」，不冒充条文 | `data/triples.csv` |
| **双层幻觉拦截** | 引用 `[E#]` 必须存在；数字必须落在证据区间内，否则告警 | `qa.verify_citations` / `qa.check_numbers` |
| **答案落地成动作** | 方向二要的是「一用就懂」，第三段固定为分步操作 | `qa.compose_steps` |

## 4. 知识图谱

- **74 节点**：品种 8、储藏条件 30、品质指标 13、病害 7、来源 16（`Source` 为溯源辅助节点，不进实体链接词表）
- **108 条关系 / 9 种谓词**：`REQUIRES`(26)、`CONTRA_INDICATED_FOR`(3)、`AFFECTS`(19)、`SUSCEPTIBLE_TO`(8)、`PREVENTED_BY`(22)、`INDUCED_BY`(7)、`ALTERNATIVE_TO`(3)、`INDICATES`(2)、`HAS_INDICATOR_VALUE`(18)
- **10 个查询模板**：`graph/queries/*.cypher`（温度/湿度/气调/耐贮性/病害处置/病害风险/品质判断/品种对比/禁忌/兜底）
- **证据分级**：**61 条 `verified`**（国标条文 51 条 + 用户提供的 5 篇综述原文 10 条；quote=原文、locator=条款号/PDF 页码栏目）、**47 条 `anchor`**（其余论文正文未获取，note 写明待核验点）

三元组示例（前两条已 `verified`，其余 `anchor`）：

| 主体 | 谓词 | 客体 | 值与单位 | 来源/分级 |
|---|---|---|---|---|
| 阳光玫瑰 | REQUIRES | 相对湿度 90~95% | 92.5 % | 国标 §7.3 / **verified** |
| 巨峰 | REQUIRES | 低温冷藏 -1~0℃ | -1~0 ℃ | 国标 §7.3 / **verified** |
| 焦亚硫酸盐缓释片 | PREVENTED_BY（灰霉病→缓释片） | — | 国标 §6.3.4+附录B / **verified** |
| SO₂ 熏蒸 | CONTRA_INDICATED_FOR | 阳光玫瑰 | severity=高 | 中文论文 + SCI 论文 / anchor |
| 阳光玫瑰 | HAS_INDICATOR_VALUE | 耐贮性 | 2~4 月 | 综述 / anchor |

数据流：`data/entities.csv + triples.csv`（唯一真相）→ `scripts/gen_cypher.py` → `graph/init_nodes.cypher`、`init_rels.cypher`（MERGE 幂等）；`scripts/validate_data.py` **十项**校验作为加载前门禁（含「S2a 快照必须是主数据严格子集」的一致性检查）。

## 5. 降级与失败模式（稳定性 = 40 分完成度）

| 场景 | 行为 |
|---|---|
| 无 `DEEPSEEK_API_KEY` / 401 | 模板模式，答案仍含 `[E#]`、来源、分步动作 |
| 超时 / 断网 | 重试 2 次 → 模板模式，`warnings += llm_timeout` |
| 图谱无证据 | 明说「未检索到」，给可换问法，绝不编造 |
| **命中实体但无对应数据**（如「维多利亚怎么存」「1-MCP 怎么用」） | **覆盖校验**拦截：不回退到别的品种/条件凑答案，明确「图谱未收录该问题」（`no_evidence`） |
| **答案引用了不存在的 `[E#]`** | `invalid_citation:E#` 告警，UI 黄色提示 |
| 「怎么做/怎么用」问句 | 走实体中心检索（1-MCP/臭氧等），不复用 SO₂ 禁忌处置清单 |
| 口语 / 错别字 / ₂ 下标 | 别名 + 症状词 + 归一化命中（12 条口语黄金集 12/12） |
| 越界问题（-18℃ 冷冻） | 区间推理 → 「不可行」+ `out_of_range` 告警 |
| Neo4j 连不上 | 自动回落 `local`，UI 徽标提示 |
| 意图不明确 | 低置信 → 澄清兜底，不硬答 |

## 6. 评测（离线可复现）

```
.\.venv\Scripts\python.exe -m pytest tests -q      # → 118 passed, 2 skipped（无网可跑）
.\.venv\Scripts\python.exe scripts\eval_qa.py      # → docs/eval_results.md
```

`docs/eval_results.md` 当前结果：**核心题 5/5、越界探针 1/1、口语变体意图 12/12、实体命中 12/12**。
Q1~Q6 证据数 2/6/1/3/6/6，引用全部有效，数值校验全部通过，Q6 触发预期的 `out_of_range`。

在线模式（2026-11-21 实测，`deepseek-chat`）：6 题全部 `mode=llm`，引用全部有效、**无 `unsourced_number`**，Q6 仍正确触发 `out_of_range`，单题 1.3~2.8 s；`RUN_LLM=1 pytest tests -m llm` → 1 passed（真实 LLM 分支下引用仍可核验）。

Cypher 实跑（无 Neo4j 服务端时）：`scripts/verify_cypher_engine.py` 在嵌入式 openCypher 引擎 **Kùzu** 上建表灌数 **74 节点 / 108 关系**，6 题与本地后端结果一致、4 条 verified 条文定点命中；`scripts/validate_cypher.py` 对 13 个 `.cypher` 文件做标签/关系/参数/计数静态校验。详见 [neo4j_verify.md](docs/neo4j_verify.md)。
判定口径（证据非空、引用有效、±区间/单位数值校验、意图与谓词、越界探针）见报告末尾。
M6 加固回归：`tests/test_regression_m6.py`（20 条）覆盖「覆盖校验防张冠李戴 / 怎么做路由 / 因果路由 / 零下归一化 / 空指标占位文案 / 无效引用告警 / 证据重排 / 十项数据校验」。

## 7. 与方向二「生命系统」的契合

| 评分口径 | 本作品回应 |
|---|---|
| 回应具体真实需求 | 阳光玫瑰采后损耗：入库参数、SO₂ 用错、灰霉爆发、出库时机 |
| 目标用户与场景清楚 | 4 类用户 × 4 场景（见 §1） |
| AI 对解决问题有实际帮助 | AI 只把「证据」翻成可执行步骤，每句可溯源；无证据直说没收录 |
| 农业技术走完最后一里地 | 口语容错、大字模式、离线可用、分步动作、条级来源 |

## 8. 目录结构

```
.
├─ install.ps1                 # 一键装环境（自动处理无 pip 的打包版 Python）
├─ run.ps1                     # 一键启动（数据校验 → Cypher 校验 → 图谱自检 → Streamlit）
├─ app.py                      # 云端部署入口（Streamlit Cloud / 魔搭创空间默认找 app.py）
├─ LICENSE                     # 版权声明（团队所有，赛事评审使用）
├─ requirements.txt / pyproject.toml / pytest.ini / .env.example / README.md
├─ .streamlit/                 # 主题配置 + Secrets 模板（云端部署用，secrets.toml 不提交）
├─ data/                       # 唯一数据源
│  ├─ entities.csv             # 58 个实体节点（含农户口语别名、病害症状）
│  ├─ triples.csv              # 108 条三元组（61 verified / 47 anchor）
│  ├─ triples_shine_muscat.csv # 20 条阳光玫瑰核心三元组（M1 门禁产物）
│  ├─ sources.csv              # 16 条来源（国标/5 篇综述/论文/行业标准）
│  ├─ utterances.csv           # 12 条农户口语黄金集
│  ├─ eval_questions.csv       # 5 典型 + 1 越界探针
│  └─ schema.json              # 类型/谓词枚举、分组与双来源规则
├─ graph/                      # schema.cypher + 生成物 + 10 个查询模板
├─ app/                        # contracts / planner / qa / llm / linking / store / ui
├─ scripts/                    # validate_data / validate_cypher / verify_cypher_engine / gen_cypher / eval_qa / env_check / load_neo4j / setup_neo4j_portable / make_release
├─ tests/                      # 120 个测试（118 passed / 2 skipped，含 M6/M8 回归）
├─ docs/                       # api / spec / sources / eval_results / neo4j_verify / packaging / deploy / demo_script / submission / ai_usage
├─ .refs/                      # 本机文献 PDF（gitignore，不随包分发）
└─ dist/                       # 打包产物（gitignore）
```

## 9. 命令速查

| 目的 | 命令 |
|---|---|
| 安装环境（首次） | `.\install.ps1`（`-Force` 重建 venv） |
| 一键启动 | `.\run.ps1` |
| 只自检 | `.\run.ps1 -Check` |
| **打包交付快照** | `.\scripts\make_release.ps1 -Version v1.0`（可选 `-WithGitBundle`） |
| 临时公网地址（cloudflared） | `.\scripts\run_public_tunnel.ps1`（需本地 8501 已启动） |
| 数据十项校验 | `.\.venv\Scripts\python.exe scripts\validate_data.py` |
| Cypher 静态校验（标签/关系/参数/计数） | `.\.venv\Scripts\python.exe scripts\validate_cypher.py` |
| 嵌入式 openCypher 实跑（Kùzu，无需 Neo4j） | `.\.venv\Scripts\python.exe scripts\verify_cypher_engine.py` |
| 便携版 Neo4j（需 JDK21+Neo4j zip） | `.\scripts\setup_neo4j_portable.ps1`（或 `-JdkZip/-Neo4jZip` 指定本地 zip） |
| CSV→Cypher 生成/漂移检查 | `.\.venv\Scripts\python.exe scripts\gen_cypher.py` / `--check` |
| 全量测试 | `.\.venv\Scripts\python.exe -m pytest tests -q` |
| 评测报告 | `.\.venv\Scripts\python.exe scripts\eval_qa.py` |
| 单问 CLI（离线） | `.\.venv\Scripts\python.exe -m app.qa "阳光玫瑰放冷库该调到多少度？" --no-llm` |
| 导入 Neo4j（可选） | `.\.venv\Scripts\python.exe scripts\load_neo4j.py`（先装 `neo4j` 驱动） |

## 10. 诚实声明与已知限制

1. **证据分级：61 条 verified + 47 条 anchor**：已获取 **GB/T 16862-2026 全文 PDF** 与 **5 篇综述 PDF（用户提供）**。国标条文直接支撑的 51 条、综述原文直接支撑的 10 条已升级 `verified`（带条款号 / PDF 页码栏目 + 原文摘录）；其余 47 条因论文正文未获取仍 `anchor` 并在 `note` 写待核验点。**未转载标准或论文全文，仅引用条级摘录。**
2. **Neo4j 服务端**：官方下载域名（`dist.neo4j.org` / `dist.neo4j.com`）在当前网络**一律 403**，本机也无 JDK 21/Aura 账号，因此没有启动 Neo4j 服务端。替代方案已落地：**① 在嵌入式 openCypher 引擎 Kùzu 上真跑等价查询**（74 节点/108 关系建表灌数、6 题与本地后端一致、4 条 verified 条文定点命中）；**② Cypher 脚本静态校验**（标签/关系/参数/MERGE 计数/10 意图覆盖）；**③ 便携版脚本** `scripts/setup_neo4j_portable.ps1`（拿到 zip 后一条命令完成 JDK+Neo4j+导入+幂等校验）。详见 `docs/neo4j_verify.md`；演示默认走本地后端。
3. **数据规模**：108 条是演示级图谱，覆盖阳光玫瑰 + 7 个对照品种、9 个国标条文条件、7 种病害（其中 5 种与国标附录B 对齐），不是全领域知识库。
4. **LLM 在线模式**：已用 `deepseek-chat` 实测通过（答案带 `[E#]`、无编造数字）；key 只存本机 `.env`（已 gitignore，不入库），换机器需自行配置。无 key 时功能完整但答案是模板拼装（非自然语言润色）。
5. 玫瑰香耐贮性等个别数值留空未编造，`note` 标注「待补文献回填」。

## 11. 原创与 AI 使用

- 代码、数据、文档在 2026-11-21 从空仓库开始开发，git 历史即开发过程证据；依赖全部为公开开源库（streamlit / openai / pandas / python-dotenv / pytest）。
- AI 使用情况（DeepSeek 辅助编码与文案、多智能体协作开发）已在 `docs/ai_usage.md` 如实说明；数值、来源、结论均由人工核验口径把控，未编造来源或 DOI。

## 12. 交付物清单

| 交付物 | 位置 |
|---|---|
| 在线 Demo | 本地 `.\run.ps1` → `http://127.0.0.1:8501`；公网见 `docs/deploy.md`（Streamlit Cloud / 魔搭创空间 / 临时隧道） |
| 200 字简介 | `docs/submission.md` |
| 代码仓库 / 干净快照 | `.\scripts\make_release.ps1` → `dist/*.zip`（含 MANIFEST + SHA256；可选 git bundle） |
| 图谱与 Cypher 快照 | 已包含在上面的 zip 中（`data/`、`graph/`） |
| 原创与 AI 使用说明 | `docs/ai_usage.md` |
| 3 分钟录屏脚本 | `docs/demo_script.md`（视频待录） |
| 评测证据 | `docs/eval_results.md` |
| 来源清单 | `docs/sources.md` |
| 打包规则说明 | `docs/packaging.md`（白名单/排除项/评审运行步骤） |

> 交付包**不含** `.env`（真实 key）与 `*.pdf`（第三方文献原件）；文献 PDF 统一放本机 `.refs/`，仅题录与条级摘录随包分发。
