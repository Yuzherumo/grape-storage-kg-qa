# 测试与验证记录

本文记录**实际执行过**的测试、命令与结果，并区分「已运行通过」「代码存在但未实际验证」「尚未完成」三类，避免把历史结果当作当前结论。

## 1. 记录口径

- 记录时间：2026-11-22（Asia/Shanghai）。
- 代码状态：本地工作区基于 commit `9093d90`（已包含可靠性加固、CI 修复与 2026-11-22 数据更新），无未提交改动；本文结果来自该工作区的一次完整运行。
- 测试环境：Windows 11（10.0.26100）、Python 3.12.14、pytest 9.2.0、Streamlit 1.67.0、openai 3.57.0、pandas 3.1.1、Kùzu 0.11.3、ruff 0.17.6、coverage 7.17.4。
- 详细依赖版本由 `scripts/env_check.py` 生成到 [env_check.md](env_check.md)。

## 2. 测试命令与结果

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量测试 | `python -m pytest tests -q` | **287 passed / 2 skipped**（共收集 289 条） |
| 覆盖率 | `python -m pytest tests -q --cov=app --cov-report=term` | 通过，TOTAL **82%**（`app/ui.py` 不计入覆盖） |
| 数据校验 | `python scripts/validate_data.py` | 十项检查通过，错误 0，告警 2 |
| Cypher 静态校验 | `python scripts/validate_cypher.py` | 13 个 `.cypher` 文件通过 |
| Cypher 生成漂移 | `python scripts/gen_cypher.py --check` | 通过，生成物与 CSV 一致 |
| 图谱查询实跑 | `python scripts/verify_cypher_engine.py` | 通过：节点 74 / 关系 108，6 题与本地后端一致 |
| 黄金集评测 | `python scripts/eval_qa.py` | PASS：核心 5/5、越界探针 1/1、口语意图 12/12、实体命中 12/12 |
| Lint | `ruff check app.py app scripts tests` | 通过 |

两条 skip 的原因：

1. `tests/test_backend_parity.py` 中依赖真实 Neo4j 服务的用例：未安装 `neo4j` 驱动、也没有运行中的 Neo4j；
2. 标记为 `llm` 的联网用例：默认跳过，需 `RUN_LLM=1` 或 `-m llm` 才运行。

### 2.1 数据校验细节

- `validate_data.py` 输出「总数据行：192」（58 实体 + 115 三元组 + 19 来源）；
- 两条告警是 **anchor 的 quote 为空**（`triples.csv` 46 行、`triples_shine_muscat.csv` 11 行），符合「anchor 只需 locator + note 待核验」的规则，不是失败；
- `check10` 确认 S2a 快照是主数据的严格子集；
- `validate_cypher.py` 校验标签/关系类型/参数/MERGE 计数/10 个意图模板覆盖。

### 2.2 图谱查询实跑（Kùzu）

`scripts/verify_cypher_engine.py` 在 Kùzu 0.11.3 内存库中：

- 从 CSV 建 5 类节点表与 9 张关系表，灌入 **77 节点 / 115 关系**，与 CSV 精确比对；
- 对 6 道题（温度、病害处置、品质判断、禁忌、品种对比、越界温度）执行等价 Cypher，结果与本地后端一致（本地证据集合是 Cypher 结果的子集）；
- 4 条 verified 条文三元组定点命中（阳光玫瑰→RH 90~95%、灰霉病→焦亚硫酸盐缓释片、巨峰→耐贮性、黑斑病→采前降雨）。

Kùzu 是嵌入式 openCypher 引擎，**不是 Neo4j 服务端**；它证明的是数据模型与查询语义可执行，不等价于 Neo4j 的约束、并发与 HTTP/Bolt 行为。详见 [neo4j_verify.md](neo4j_verify.md)。

### 2.3 问答链路评测

`docs/eval_results.md`（2026-11-22 生成）结果：

| 问题 | 意图 | 证据数 | 引用数 | 数值校验 | 结论 |
|---|---|---|---|---|---|
| 阳光玫瑰放冷库该调到多少度？ | temperature | 5 | 11 | 通过 | 通过 |
| 冷库里葡萄长白毛了怎么办？ | disease_control | 6 | 11 | 通过 | 通过 |
| 葡萄发软掉粒是咋回事？ | quality_indicator | 3 | 7 | 通过 | 通过 |
| 用 SO₂ 熏阳光玫瑰行不行？ | contraindication | 3 | 7 | 通过 | 通过 |
| 阳光玫瑰和巨峰哪个更能放？ | variety_compare | 13 | 11 | 通过 | 通过 |
| -18℃ 冻起来能存一年吗？ | temperature | 6 | 7 | out_of_range（预期） | 通过 |

12 条口语变体的意图命中均为 12/12，最弱的是 `u08`（`打SO2对晴王是不是不好使啊`，contraindication，置信度 0.37，仍命中）。

### 2.4 引用与数值校验验证

由测试与评测共同覆盖：

- 引用缺失/不存在：`verify_citations()` 返回告警，评测与 `test_numbers.py`、`test_qa_validation.py` 覆盖；
- 引用与事实句不匹配：`citation_mismatch`，允许纠正一次后回退模板；
- 证据外数字：`unsourced_number`；超出温度区间：`out_of_range`；
- 仅凭 anchor 给高风险参数：`anchor_high_risk` 并回退模板；
- 空问题、无实体、图谱无证据、数据文件缺失等路径：`test_qa_validation.py`、`test_e2e_questions.py` 覆盖。

这些是**规则启发式校验**，不能证明自然语言层面的语义正确性，详见 [limitations.md](limitations.md)。

### 2.5 UI 与安全回归

- `tests/test_ui_security.py`（30 条）覆盖动态文本 HTML 转义、图谱 JSON 数据块不能逃逸、危险字符处理等；
- 使用 Streamlit `AppTest` 进行无浏览器回归（页面加载、开关切换、示例问题点击）；
- **没有**进行真实浏览器像素级检查（截图/布局/字体溢出）——当前环境无可用浏览器自动化。`docs/assets/ui_home.png` 是运行中实例的真实截图，不是生成图。

## 3. 在线 LLM 模式（历史记录）

2026-11-21 使用 `deepseek-chat` 实测 6 道题（当时的代码版本，非当前工作区）：

- 6 题全部 `mode=llm`，引用全部有效，无 `unsourced_number`；
- Q6（-18℃）仍正确触发 `out_of_range`；
- 单题耗时 1.3~2.8 s，缓存命中约 5 ms；
- `RUN_LLM=1 pytest tests -m llm` → 1 passed。

**当前工作区的 `app/qa.py`、`app/llm.py` 在上次实测后有改动（增加了 LLM 答案规则校验与回退）**，因此这次在线结果不能直接作为当前版本的验证结论。若需当前版本的在线结论，应在配置 Key 后重跑上述命令并记录。

## 4. GitHub Actions（CI）状态

- 工作流：`.github/workflows/ci.yml`，包含两个 job：
  - `test`（Ubuntu + Python 3.12）：ruff、数据校验、Cypher 静态校验、生成漂移、Kùzu 实跑、pytest + coverage、eval；
  - `windows-scripts`（Windows + PowerShell 5.1）：5 个 `.ps1` 的语法检查。
- 最新运行（run `44980363203`，head `a73f89e`）：**两个 job 全部通过**。
- 历史问题已修复：
  1. 早期 Kùzu 步骤在 CI 中报 `ModuleNotFoundError: No module named 'app'`（缺 `PYTHONPATH`）→ 脚本自举 `sys.path` + CI job 级 `PYTHONPATH`；
  2. Windows job 的 BOM 检查在 runner 上失败（本地同样文件均带 BOM）→ 将 BOM 检查移到 Ubuntu 的字节级检查，Windows job 保留 PowerShell 5.1 语法门禁。

CI 通过只代表上述静态/离线步骤通过，不覆盖真实 Neo4j、在线 LLM、真实浏览器 UI（见第 5 节）。

## 5. 已运行 / 未验证 / 未完成

### 5.1 已经实际运行并通过

- 本地 pytest 全量（287 passed / 2 skipped）、覆盖率 82%；
- 数据十项校验、Cypher 静态校验、生成漂移检查；
- Kùzu 实跑（74/108，6 题一致，4 条定点核对）；
- 离线黄金集评测（5/5、1/1、12/12、12/12）；
- `AppTest` 为核心的 UI 回归（非像素级）；
- 打包脚本在本机的干净目录验收（见 [packaging.md](packaging.md)，历史记录）。

### 5.2 代码存在、但未在本次验证

- **Neo4j 真实服务**：未启动、未导入、未跑双后端一致性测试（`test_backend_parity` 处于 skipped）；
- **在线 LLM 当前版本**：最近一次实测是 2026-11-21 的旧代码，当前工作区改动后未复测；
- **真实浏览器 UI**：未做自动化截图/视觉回归；
- **Linux/macOS 安装脚本**：`install.ps1`/`run.ps1` 为 PowerShell；POSIX 仅按 README 手动命令推断，未在 Linux 实机验证。

### 5.3 尚未完成

- 46 条 anchor 的原文核验；
- 人工评分集（可读性/可执行性/引用准确性）；
- 跨机器复现记录（至少一台非当前开发机）。

## 6. 历史记录

| 日期 | 版本/提交 | 结果 | 说明 |
|---|---|---|---|
| 2026-11-21 | M9（`7e34732` 前后） | 118 条通过 / 2 跳过；在线 LLM 6 题通过 | 当时测试规模较小；后续可靠性加固新增测试 |
| 2026-11-22 | `9093d90`（数据更新后） | 287 passed / 2 skipped；覆盖率 82%；数据/Cypher/Kùzu/eval 通过；CI run `44984323892` 双 job 通过 | 本文主要记录；新增 3 来源、7 三元组 |
| 2026-11-22 | 远端 `4099009` | CI 在 Kùzu 步骤失败 | `ModuleNotFoundError: app`，随后修复 |
| 2026-11-22 | 远端 `a73f89e` | **CI 两个 job 全部通过** | 当前记录；Ubuntu test + Windows scripts |

历史数据只对应其记录时的代码与数据，不能直接当作当前版本结论。
