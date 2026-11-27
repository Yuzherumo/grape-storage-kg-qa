# 测试与验证记录

> **状态说明（2026-11-27）**：§1–§2 为 v1.4 数据 / v1.4.1 交付修复的**当前口径**；§3 起保留 2026-11-22 的**历史运行记录**（当时 287 passed、Kùzu 74 节点/108 关系），仅作追溯，不作为当前结论。
> 当前图谱：**108 节点 / 125 关系（63 知识实体 + 45 来源节点，verified 69 / anchor 56）**，规范值由 `scripts/report_stats.py` 从 `data/` 实时计算。
> 本地复测（2026-11-27）：**pytest 418 passed / 2 skipped、覆盖率 83%、黄金集 28/28**；CI 尚未在 v1.4.1 的 commit 上运行——推送后由 GitHub Actions 复核，本文不声称新 commit 已有 CI run。

本文记录**实际执行过**的测试、命令与结果，并区分「当前已验证」「代码存在但未实际验证」「尚未完成」三类。

## 1. 记录口径

- 当前口径记录时间：2026-11-27（Asia/Shanghai）；历史部分记录时间：2026-11-22。
- 代码状态：本地工作区为 v1.4 数据 + v1.4.1 交付修复（提交后回填 commit）；历史结果来自 commit `9093d90`。
- 测试环境：Windows 11（10.0.26100）、Python 3.12.14、pytest 9.2.0、Streamlit 1.67.0、openai 3.57.0、pandas 3.1.1、Kùzu 0.11.3、ruff 0.17.6、coverage 7.17.4。
- 详细依赖版本由 `scripts/env_check.py` 生成到 [env_check.md](env_check.md)（该文件为自动生成，更新数据后需重新生成）。

## 2. 当前测试命令与结果

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量测试 | `python -m pytest tests -q` | **418 passed / 2 skipped**（2 条 skip 的原因见下） |
| 覆盖率 | `python -m pytest tests -q --cov=app --cov-report=term-missing --cov-fail-under=80` | **83%**（`app/ui.py` 不计入；`app/store/neo4j_store.py` 因无服务为 0%） |
| 数据校验 | `python scripts/validate_data.py` | 十项检查通过，错误 0，告警 2；总数据行 **233**（63 实体 + 125 三元组 + 45 来源） |
| Cypher 静态校验 | `python scripts/validate_cypher.py` | 13 个 `.cypher` 文件通过 |
| Cypher 生成漂移 | `python scripts/gen_cypher.py --check` | 通过，生成物与 CSV 一致 |
| 图谱查询实跑 | `python scripts/verify_cypher_engine.py` | 通过：**108 节点 / 125 关系**，6 题与本地后端一致 |
| 黄金集评测 | `python scripts/eval_qa.py` | **28/28 通过**（answer 19 + refuse 9）：意图 100%、主实体覆盖 100%、引用有效率 100%、数值一致率 100%、拒答准确率 9/9、口语变体 12/12；Q6 命中 `out_of_range`；exit 0 |
| Lint | `ruff check app.py app scripts tests tools` | All checks passed |
| 文档数字一致性 | `python scripts/check_docs_consistency.py` | 通过（0 漂移） |
| CI | GitHub Actions | 本地全绿；v1.4.1 推送后由 Actions 复核（见 §4） |

两条 skip 的原因：

1. `tests/test_backend_parity.py` 中依赖真实 Neo4j 服务的用例：未安装 `neo4j` 驱动、也没有运行中的 Neo4j；
2. 标记为 `llm` 的联网用例：默认跳过，需 `RUN_LLM=1` 或 `-m llm` 才运行。

### 2.1 数据校验细节

- `validate_data.py` 输出「总数据行：233」（63 实体 + 125 三元组 + 45 来源）；
- 两条告警是 **anchor 的 quote 为空**（`triples.csv` 46 行、`triples_shine_muscat.csv` 11 行），符合「anchor 只需 locator + note 待核验」的规则，不是失败；
- `check10` 确认 S2a 快照（20 条）是主数据的严格子集；
- `validate_cypher.py` 校验标签/关系类型/参数/MERGE 计数/10 个意图模板覆盖；`gen_cypher.py --check` 确认 `graph/init_*.cypher` 与 CSV 无漂移。

### 2.2 图谱查询实跑（Kùzu）

`scripts/verify_cypher_engine.py` 在 Kùzu 0.11.3 内存库中：

- 从 CSV 建 5 类节点表与 9 张关系表，灌入 **108 节点 / 125 关系**，与 CSV 精确比对；
- 对 6 道题（温度、病害处置、品质判断、禁忌、品种对比、越界温度）执行等价 Cypher，结果与本地后端一致（本地证据集合是 Cypher 结果的子集）；
- 4 条 verified 条文三元组定点命中（阳光玫瑰→RH 90~95%、灰霉病→焦亚硫酸盐缓释片、巨峰→耐贮性、黑斑病→采前降雨）。

Kùzu 是嵌入式 openCypher 引擎，**不是 Neo4j 服务端**；它证明的是数据模型与查询语义可执行，不等价于 Neo4j 的约束、并发与 HTTP/Bolt 行为。详见 [neo4j_verify.md](neo4j_verify.md)。

### 2.3 问答链路评测

评测集已由固定的 6 题扩到 **28 题（answer 19 + refuse 9）**，由 `scripts/eval_qa.py` 重新生成 [eval_results.md](eval_results.md) 与 `eval_results.json`。当前结果：**28/28 通过**——意图命中 100%、主实体覆盖 100%、引用有效率 100%、数值一致率 100%、应拒答准确率 9/9、关键词覆盖 100%；口语变体 12/12；Q6（-18℃）命中 `out_of_range`。2026-11-22 的旧评测结果保留在 §6 历史记录中，不作为当前结论。

### 2.4 引用与数值校验验证

由测试与评测共同覆盖：

- 引用缺失/不存在：`verify_citations()` 返回告警，评测与 `test_numbers.py`、`test_qa_validation.py` 覆盖；
- 引用与事实句不匹配：`citation_mismatch`，允许纠正一次后回退模板；
- 证据外数字：`unsourced_number`；超出温度区间：`out_of_range`；
- 仅凭 anchor 给高风险参数：`anchor_high_risk` 并回退模板；
- 空问题、无实体、图谱无证据、数据文件缺失等路径：`test_qa_validation.py`、`test_e2e_questions.py` 覆盖。

这些是**规则启发式校验**，不能证明自然语言层面的语义正确性，详见 [limitations.md](limitations.md)。

### 2.5 UI 与安全回归

- `tests/test_ui_security.py` 覆盖动态文本 HTML 转义、图谱 JSON 数据块不能逃逸、危险字符处理等；
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
  - `test`（Ubuntu + Python 3.12）：ruff（含 `tools/`）、规范统计、文档数字一致性、数据十项校验、Cypher 静态校验、生成漂移、Kùzu 实跑、BOM 检查、pytest + 覆盖率（`--cov-fail-under=80`）、外部数据导出校验（原始批次存在时）、离线评测生成；
  - `windows-scripts`（Windows + PowerShell 5.1）：5 个 `.ps1` 的语法检查。
- 最新运行：**v1.4.1 的 commit 尚无 CI run**；推送后由 GitHub Actions 复核，以 Actions 页面实际 run 号为准（本文不预填新 run 号）。
- 历史运行（2026-11-22）：最近一次通过为 run `44987585590`（head `3d0a2d6`）；此前 run `44980363203`（head `a73f89e`）亦通过。历史问题已修复：
  1. 早期 Kùzu 步骤在 CI 中报 `ModuleNotFoundError: No module named 'app'`（缺 `PYTHONPATH`）→ 脚本自举 `sys.path` + CI job 级 `PYTHONPATH`；
  2. Windows job 的 BOM 检查在 runner 上失败（本地同样文件均带 BOM）→ 将 BOM 检查移到 Ubuntu 的字节级检查，Windows job 保留 PowerShell 5.1 语法门禁。

CI 通过只代表上述静态/离线步骤通过，不覆盖真实 Neo4j、在线 LLM、真实浏览器 UI 与数据/文档之外的人工核验（见第 5 节）。

## 5. 已运行 / 未验证 / 未完成

### 5.1 当前已验证（2026-11-27）

- pytest 418 passed / 2 skipped，覆盖率 83%，ruff All checks passed；
- 数据十项校验（0 错误 / 2 告警，总数据行 233）、Cypher 静态校验与生成漂移检查；
- Kùzu 实跑 108 节点 / 125 关系，6 题与本地后端一致，4 条 verified 定点核对；
- 黄金集 28/28（answer 19 + refuse 9）、口语变体 12/12、Q6 `out_of_range`；
- `scripts/report_stats.py` 与 `scripts/check_docs_consistency.py`（文档数字 0 漂移）；
- `AppTest` 为核心的 UI 回归（非像素级）；
- 历史（2026-11-22）：pytest 287 passed / 2 skipped、覆盖率 82%，对应当时测试集，仅供参考。

### 5.2 代码存在、但未在本次验证

- **Neo4j 真实服务**：未启动、未导入、未跑双后端一致性测试（`test_backend_parity` 处于 skipped）；
- **在线 LLM 当前版本**：最近一次实测是 2026-11-21 的旧代码，当前工作区改动后未复测；
- **真实浏览器 UI**：未做自动化截图/视觉回归；
- **Linux/macOS 安装脚本**：`install.ps1`/`run.ps1` 为 PowerShell；POSIX 仅按 README 手动命令推断，未在 Linux 实机验证；
- **v1.4.1 交付包**：打包脚本已修正（排除外部原始数据、按 %PDF 魔数拦截、白名单含 `tools/`），最终包体/SHA 待打包后回填。

### 5.3 尚未完成

- 46 条 anchor 仍无逐字 quote（原文核验）；
- 人工评分集（可读性/可执行性/引用准确性）；
- 跨机器复现记录（至少一台非当前开发机）；
- v1.4.1 的 CI run 与交付包信息（commit / 包大小 / SHA）待 push 与重打包后由交付负责人回填。

## 6. 历史记录

| 日期 | 版本/提交 | 结果 | 说明 |
|---|---|---|---|
| 2026-11-21 | M9（`7e34732` 前后） | 118 条通过 / 2 跳过；在线 LLM 6 题通过 | 当时测试规模较小；后续可靠性加固新增测试 |
| 2026-11-22 | `9093d90`（数据更新后） | 287 passed / 2 skipped；覆盖率 82%；数据/Cypher/Kùzu/eval 通过；CI run `44984323892` 双 job 通过 | 新增 3 来源、7 三元组；本文历史部分据此 |
| 2026-11-22 | 远端 `4099009` | CI 在 Kùzu 步骤失败 | `ModuleNotFoundError: app`，随后修复 |
| 2026-11-22 | 远端 `a73f89e` | CI 两个 job 全部通过（run `44980363203`） | 当时 Ubuntu test + Windows scripts |
| 2026-11-27 | v1.4.1 本地交付版本（待提交） | 418 passed / 2 skipped；覆盖率 83%；黄金集 28/28；数据十项校验 0 错误 2 告警；ruff/check_docs 通过 | 63 实体 / 45 来源 / 108 节点 / 125 关系；69 verified / 56 anchor；新增 25 篇开放获取文献、5 条件、6 关系；CI run 待 push 后复核 |

历史数据只对应其记录时的代码与数据，不能直接当作当前版本结论。
