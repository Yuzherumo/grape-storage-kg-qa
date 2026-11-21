# 鲜食葡萄储藏知识图谱问答（葡萄冷库「能查证」的技术助手）

> 农客松 2026 · 主赛道 · **方向二「生命系统」**（农业 / 食品）
> 状态：M5 验收通过 ｜ 测试 `95 passed / 2 skipped` ｜ 图谱 **59 节点 / 71 条关系** ｜ **无 API Key、断网也能跑** ｜ 在线模式已实测（`deepseek-chat`，1.3~2.8 s/题）
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
# 1) 首次：创建虚拟环境并装依赖（本机 Python 3.12；见 docs/env_check.md）
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 一键启动（自动做数据校验 → 图谱自检 → 起服务）
.\run.ps1
#    → http://127.0.0.1:8501

# 只想自检、不启动服务
.\run.ps1 -Check
```

没有 API Key 也能完整演示：系统自动进入**离线模板模式**，答案仍带 `[E#]` 引用、来源与分步动作。
要启用 DeepSeek 在线生成：把 key 填进 `.env` 的 `DEEPSEEK_API_KEY`（见 `.env.example`）。

## 3. 架构与关键设计

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
| **规则优先、LLM 只做翻译** | 实体与意图可确定性测试；40 分完成度不被 API 稳定性拖累 | `planner.py` / `qa.py` |
| **双后端，本地优先** | 现场无 Neo4j/Docker 也能跑；Cypher 脚本按交付要求完整提供 | `app/store/` |
| **数据单一真相** | CSV → Cypher 生成，杜绝两边改漏 | `scripts/gen_cypher.py` |
| **条级溯源 + anchor 诚实标注** | 拿不到原文的数值标「待核验」，不冒充国标条文 | `data/triples.csv` |
| **双层幻觉拦截** | 引用 `[E#]` 必须存在；数字必须落在证据区间内，否则告警 | `qa.verify_citations` / `qa.check_numbers` |
| **答案落地成动作** | 方向二要的是「一用就懂」，第三段固定为分步操作 | `qa.compose_steps` |

## 4. 知识图谱

- **59 节点**：品种 8、储藏条件 21、品质指标 13、病害 6、来源 11（`Source` 为溯源辅助节点，不进实体链接词表）
- **71 条关系 / 9 种谓词**：`REQUIRES`、`CONTRA_INDICATED_FOR`、`AFFECTS`、`SUSCEPTIBLE_TO`、`PREVENTED_BY`、`INDUCED_BY`、`ALTERNATIVE_TO`、`INDICATES`、`HAS_INDICATOR_VALUE`
- **10 个查询模板**：`graph/queries/*.cypher`（温度/湿度/气调/耐贮性/病害处置/病害风险/品质判断/品种对比/禁忌/兜底）

三元组示例（均为 `status=anchor`，`note` 写明待核验点）：

| 主体 | 谓词 | 客体 | 值与单位 | 来源 |
|---|---|---|---|---|
| 阳光玫瑰 | REQUIRES | 低温冷藏 0±0.5℃ | 0 ℃ | GB/T 16862-2026 + 综述 |
| SO₂ 熏蒸 | CONTRA_INDICATED_FOR | 阳光玫瑰 | severity=高 | 中文论文 + SCI 论文 |
| 灰霉病 | PREVENTED_BY | 快速预冷（12h 内至 0℃） | efficacy=中 | 综述 + 国标 |
| 阳光玫瑰 | HAS_INDICATOR_VALUE | 耐贮性 | 2~4 月 | 综述 |

数据流：`data/entities.csv + triples.csv`（唯一真相）→ `scripts/gen_cypher.py` → `graph/init_nodes.cypher`、`init_rels.cypher`（MERGE 幂等）；`scripts/validate_data.py` 九项校验作为加载前门禁。

## 5. 降级与失败模式（稳定性 = 40 分完成度）

| 场景 | 行为 |
|---|---|
| 无 `DEEPSEEK_API_KEY` / 401 | 模板模式，答案仍含 `[E#]`、来源、分步动作 |
| 超时 / 断网 | 重试 2 次 → 模板模式，`warnings += llm_timeout` |
| 图谱无证据 | 明说「未检索到」，给可换问法，绝不编造 |
| 口语 / 错别字 / ₂ 下标 | 别名 + 症状词 + 归一化命中（12 条口语黄金集 12/12） |
| 越界问题（-18℃ 冷冻） | 区间推理 → 「不可行」+ `out_of_range` 告警 |
| Neo4j 连不上 | 自动回落 `local`，UI 徽标提示 |
| 意图不明确 | 低置信 → 澄清兜底，不硬答 |

## 6. 评测（离线可复现）

```
.\.venv\Scripts\python.exe -m pytest tests -q      # → 95 passed, 2 skipped（无网可跑）
.\.venv\Scripts\python.exe scripts\eval_qa.py      # → docs/eval_results.md
```

`docs/eval_results.md` 当前结果：**核心题 5/5、越界探针 1/1、口语变体意图 12/12、实体命中 12/12**。
Q1~Q6 证据数 2/6/1/3/6/6，引用全部有效，数值校验全部通过，Q6 触发预期的 `out_of_range`。

在线模式（2026-11-21 实测，`deepseek-chat`）：6 题全部 `mode=llm`，引用全部有效、**无 `unsourced_number`**，Q6 仍正确触发 `out_of_range`，单题 1.3~2.8 s；`RUN_LLM=1 pytest tests -m llm` → 1 passed（真实 LLM 分支下引用仍可核验）。
判定口径（证据非空、引用有效、±区间/单位数值校验、意图与谓词、越界探针）见报告末尾。

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
├─ run.ps1                     # 一键启动（数据校验 → 图谱自检 → Streamlit）
├─ requirements.txt / .env.example / pytest.ini / README.md
├─ data/                       # 唯一数据源
│  ├─ entities.csv             # 48 个实体节点（含农户口语别名、病害症状）
│  ├─ triples.csv              # 71 条三元组
│  ├─ triples_shine_muscat.csv # 20 条阳光玫瑰核心三元组（M1 门禁产物）
│  ├─ sources.csv              # 11 条来源（国标/综述/论文/行业标准）
│  ├─ utterances.csv           # 12 条农户口语黄金集
│  ├─ eval_questions.csv       # 5 典型 + 1 越界探针
│  └─ schema.json              # 类型/谓词枚举、分组与双来源规则
├─ graph/                      # schema.cypher + 生成物 + 10 个查询模板
├─ app/                        # contracts / planner / qa / llm / linking / store / ui
├─ scripts/                    # validate_data / gen_cypher / eval_qa / env_check / load_neo4j
├─ tests/                      # 96 个测试
└─ docs/                       # api / spec / sources / eval_results / demo_script / submission / ai_usage
```

## 9. 命令速查

| 目的 | 命令 |
|---|---|
| 一键启动 | `.\run.ps1` |
| 只自检 | `.\run.ps1 -Check` |
| 数据九项校验 | `.\.venv\Scripts\python.exe scripts\validate_data.py` |
| CSV→Cypher 生成/漂移检查 | `.\.venv\Scripts\python.exe scripts\gen_cypher.py` / `--check` |
| 全量测试 | `.\.venv\Scripts\python.exe -m pytest tests -q` |
| 评测报告 | `.\.venv\Scripts\python.exe scripts\eval_qa.py` |
| 单问 CLI（离线） | `.\.venv\Scripts\python.exe -m app.qa "阳光玫瑰放冷库该调到多少度？" --no-llm` |
| 导入 Neo4j（可选） | `.\.venv\Scripts\python.exe scripts\load_neo4j.py`（先装 `neo4j` 驱动） |

## 10. 诚实声明与已知限制

1. **全库 `status=anchor`**：GB/T 16862-2026 与多数论文正文需购买/机构访问，数值按摘要与公开描述入图，`note` 写明待核验点；对外表述为「国标/综述指出」，不称「条文原文」。
2. **Neo4j 未在真实实例执行**：Cypher 脚本完整交付且由 CSV 生成、幂等校验通过，但本机无 Docker/WSL/兼容 JDK，未做实库验证；演示默认走本地后端。
3. **数据规模**：71 条是演示级图谱，覆盖阳光玫瑰 + 6 个对照品种，不是全领域知识库。
4. **LLM 在线模式**：已用 `deepseek-chat` 实测通过（答案带 `[E#]`、无编造数字）；key 只存本机 `.env`（已 gitignore，不入库），换机器需自行配置。无 key 时功能完整但答案是模板拼装（非自然语言润色）。
5. 玫瑰香耐贮性等个别数值留空未编造，`note` 标注「待补文献回填」。

## 11. 原创与 AI 使用

- 代码、数据、文档在 2026-11-21 从空仓库开始开发，git 历史即开发过程证据；依赖全部为公开开源库（streamlit / openai / pandas / python-dotenv / pytest）。
- AI 使用情况（DeepSeek 辅助编码与文案、多智能体协作开发）已在 `docs/ai_usage.md` 如实说明；数值、来源、结论均由人工核验口径把控，未编造来源或 DOI。

## 12. 交付物清单

| 交付物 | 位置 |
|---|---|
| 在线 Demo | `.\run.ps1` → `http://127.0.0.1:8501` |
| 200 字简介 | `docs/submission.md` |
| 代码仓库 | 本仓库（git 历史） |
| 图谱与 Cypher 快照 | `data/`、`graph/`（ANS 作品快照可直接打包） |
| 原创与 AI 使用说明 | `docs/ai_usage.md` |
| 3 分钟录屏脚本 | `docs/demo_script.md` |
| 评测证据 | `docs/eval_results.md` |
| 来源清单 | `docs/sources.md` |
