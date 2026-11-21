# 接口契约（docs/api.md）

> 冻结时间：T+1。**所有成员按本文件并行开发；改契约先改 `app/contracts.py` + 本文件，并通知 Lead。**
> 写区划分见 §9。任何一方不得修改他人写区的文件。

## 1. 数据契约（CSV，UTF-8，逗号分隔，首行表头）

### 1.1 `data/entities.csv`（节点）
| 列 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 英文蛇形唯一 id，如 `shine_muscat` / `cold_0` |
| `label` | ✅ | `Variety` / `Condition` / `QualityIndicator` / `Disease` / `Source` |
| `name` | ✅ | 中文规范名，如来 阳光玫瑰 |
| `aliases` |  | 分号分隔，**含农户口语/商品名/错别字**：`Shine Muscat;香印;晴王;青提` |
| `category` |  | Condition 用：温度/湿度/气调/化学/物理/包装/采后操作/环境风险 |
| `value_min` / `value_max` / `unit` |  | Condition、QualityIndicator 用 |
| `stage` |  | 预冷/贮藏/出库 |
| `direction` |  | QualityIndicator 用：higher_better / lower_better / target |
| `method` |  | QualityIndicator 测量方法 |
| `species` / `berry_color` / `seedless` / `maturity` / `region` |  | Variety 用 |
| `pathogen_latin` / `symptom` |  | Disease 用；`symptom` 必须含农户口述症状（长白毛/软烂） |
| `source_ids` |  | 分号分隔 |
| `note` |  | 备注 |

### 1.2 `data/triples.csv`（边，唯一数据源；Cypher 由它生成）
```
sid, subject, subject_type, predicate, object, object_type, value, value_min, value_max, unit,
stage, effect, level, severity, efficacy, reason, source_ids, locator, quote, status, confidence, note
```
- `predicate ∈` `REQUIRES / CONTRA_INDICATED_FOR / AFFECTS / SUSCEPTIBLE_TO / PREVENTED_BY / INDUCED_BY / ALTERNATIVE_TO / INDICATES / HAS_INDICATOR_VALUE`
- `source_ids` 分号分隔多值。**B 组（CONTRA_INDICATED_FOR）、G 组（ALTERNATIVE_TO）、H 组（INDICATES）必须 ≥2 个来源**；确只有 1 篇支撑时 `note` 必须写「单来源，建议后续实验验证」。
- `status ∈ {verified, anchor}`；`confidence ∈ [0,1]`；`locator` 必填；`verified` **必须**有可引用的 `quote`（校验器检查 8 强制），`anchor` 允许空 quote 但 `note` 必须说明待核验点。
- 类型-谓词组合：`REQUIRES`(Variety→Condition)、`CONTRA_INDICATED_FOR`(Condition→Variety)、`AFFECTS`(Condition→QualityIndicator)、`SUSCEPTIBLE_TO`(Variety→Disease)、`PREVENTED_BY`(Disease→Condition)、`INDUCED_BY`(Disease→Condition)、`ALTERNATIVE_TO`(Condition→Condition)、`INDICATES`(QualityIndicator→Disease)、`HAS_INDICATOR_VALUE`(Variety→QualityIndicator)。

### 1.3 `data/sources.csv`
`id, title, authors, year, venue, type, doi_url, access, note`；`type ∈ {国标, 综述, 论文, 行业资料}`；`access ∈ {public, paywalled}`。

### 1.4 `data/triples_shine_muscat.csv`
与 `triples.csv` **同列**，只含阳光玫瑰相关 20 行（S2a 门禁产物）。

### 1.5 `data/utterances.csv`（口语路由黄金集）
`id, utterance, expected_intent, expected_entity_ids, note`（`expected_entity_ids` 分号分隔，可为空）。

### 1.6 `data/eval_questions.csv`
`id, question, expected_intent, expected_predicate, must_keywords, forbidden_keywords, kind`（`must_keywords`/`forbidden_keywords` 分号分隔；`kind ∈ {core, probe}`）。

## 2. 共享数据结构
定义在 `app/contracts.py`（Lead 写区）：`EntityHit`、`Evidence`、`QuerySpec`、`AnswerResult`、`INTENTS`、告警码常量。
**不要绕过 contracts.py 自定义同名字段**（否则 UI 与测试会炸）。

`Evidence` 关键字段：`eid / subject / predicate / object / value / unit / value_min / value_max / properties / source_ids / source_titles / locator / quote / status / confidence / score`。
`AnswerResult` 关键字段：`question / entities / intent / intent_confidence / evidence / answer / steps / cited_ids / mode / elapsed_ms / query_cypher / warnings / llm_meta`。

## 3. linking（`app/linking.py`，store-builder 写区）
```
load_catalog(entities_csv_path) -> Catalog          # 启动时构建词表（name + aliases，长词优先）
link_entities(question, catalog, *, max_hits=8) -> list[EntityHit]
```
规则：全角转半角、去空格与语气词；最长匹配优先；同一 node_id 多处命中取 score 最高；不做拼音/编辑距离（不在本期范围）。

## 4. planner（`app/planner.py`，Lead 写区）
```
route(question, hits) -> (intent: str, confidence: float, candidates: list[tuple[str, float]])
build_query(intent, hits, k=6) -> QuerySpec
```
- 三级路由：L2 触发词加权 + 实体标签先验 + 句式模式分；最高分 < 0.35 时 `confidence` 低，UI 走澄清提示；无实体无触发词 → `general`。
- **路由兜底覆盖（M6 加固）**：①「怎么做/怎么用/剂量」+ 命中 `Condition` → 强制 `general`（实体中心检索，避免套错处置清单）；②「有什么关系/为什么/怎么引起」+ 命中 `Disease` → `disease_risk`（回答诱因，而不是给处置清单）。
- 归一化含中文数字与「零下」：`零下18度`/`零下十八度` → `-18度`（供越界检测使用）。
- `build_query` 只产出参数，不拼 Cypher 字符串。
- 触发词表放 `app/planner_rules.py`（Lead 写区，供 qa-tester 只读引用做断言）。

## 5. GraphStore（`app/store/`，store-builder 写区）
```
class GraphStore:  # base.py
    name: str                      # "local" | "neo4j"
    def execute(spec: QuerySpec) -> list[Evidence]
    def stats() -> dict            # {"nodes": int, "rels": int, "varieties": int, ...}
    def health() -> tuple[bool, str]
```
- `LocalStore(data_dir)`：从 CSV 建内存邻接表，纯标准库，`GRAPH_BACKEND=local` 默认。
- `Neo4jStore(uri, user, password)`：执行 `graph/queries/*.cypher`（共 **10** 个模板，含 `general`）；连接失败 → 抛 `BackendFallback`，**由工厂回落 local**（UI 收到 `warnings += backend_fallback`）。
- `QuerySpec.params` 约定（两种后端一致，未知 key 忽略）：`variety_ids / condition_ids / indicator_ids / disease_ids / entity_ids / keywords / question / k`。其中 `entity_ids` **仅 `general` 兜底使用**；`condition_ids` 仅 `contraindication` 意图做精确过滤 —— 否则「冷库→cold_0」会把温度结果窄化成 1 条，且 local 与 neo4j 过滤口径不一致（parity）。
- 证据排序：`score = 0.5*confidence + 0.3*status权重(verified=1,anchor=0.6) + 0.2*实体命中度`，降序后按 (subject,predicate,object) 去重，截断 `k`。
- `eid` 由 qa 层统一分配（`E1..En`），store 返回时留空字符串。

## 6. qa（`app/qa.py`，Lead 写区）
```
answer_question(question, *, store, llm=None, k=6, allow_llm=True, steps=True) -> AnswerResult
build_prompt(question, evidence) -> list[dict]      # OpenAI messages
compose_steps(evidence, intent) -> list[str]        # ≤3 步，无证据返回 []
verify_citations(answer, evidence) -> tuple[list[str], list[str]]
check_numbers(answer, evidence) -> list[str]        # 返回告警码/文本
```
流程：normalize → link（词表按 mtime 缓存）→ route → build_query → store.execute → eid 分配 → **覆盖校验**（typed 意图下证据必须触达命中实体，否则返回「图谱未收录」而不是回退全库）→ 排序（优先与命中实体相连的证据，再按 store 分数）→ 去重截断 →（allow_llm 且 key 可用 → LLM；否则模板）→ 引用校验（无有效引用重试 1 次，再失败转模板并加 `no_citation`）→ 最终答案确定后**重算 `cited_ids`**（覆盖分步动作里的引用）→ 数值校验 → 组装 AnswerResult。
`mode="template"` 时答案必须仍带 `[E#]`、`steps` 与来源；`steps` 为空时不输出空的「现在该做什么」段（`general` 意图不硬编动作）。

告警码（`AnswerResult.warnings`）：

| 告警 | 含义 |
|---|---|
| `no_evidence` | 无证据 / 命中实体无对应数据（覆盖校验拦截） |
| `no_citation` | 答案没有任何有效 `[E#]` 引用 |
| `invalid_citation:E#` | 答案引用了不存在的证据编号 |
| `unsourced_number:<num>` | 答案里的数字在证据中找不到来源 |
| `out_of_range:<num><unit>` / `out_of_range` | 数值超出证据区间（含问题级越界检测） |
| `single_source` | B/G/H 组证据仅 1 个来源 |
| `low_confidence_intent` | 意图置信度 < 0.35 |
| `llm_timeout` / `llm_unavailable` | 模型超时/不可用，已降级模板 |
| `backend_fallback` | Neo4j 不可用，已回落 local |

模板答案格式（离线/降级）：
- 结论：由证据值直接拼（如「阳光玫瑰适宜冷藏温度为 0±0.5 ℃」）
- 依据：`[E1] 阳光玫瑰 -REQUIRES-> 低温冷藏 0±0.5℃（GB/T 16862-2026）`
- 现在该做什么：由 `compose_steps` 生成，≤3 步

## 7. llm（`app/llm.py`，Lead 写区）
```
class LLMClient:
    available: bool
    def complete(messages, *, timeout=20, retries=2) -> str
    last_usage: dict            # {"model","prompt_tokens","completion_tokens"}
```
DeepSeek 走 OpenAI 兼容接口：`base_url=https://api.deepseek.com`，`model=deepseek-chat`。
`DEEPSEEK_API_KEY` 为空 → `available=False`，qa 自动走模板。超时/401/网络错误 → 抛 `LLMUnavailable`（qa 捕获后降级，加 `llm_timeout`/`llm_unavailable`）。

## 8. UI 消费点（`app/ui.py`，ui-builder 写区）
| UI 元素 | 取自 |
|---|---|
| 顶部徽标（后端/模型/离线） | `store.name`、`llm.available`、`AnswerResult.mode` |
| 答案三段 | `answer`（Markdown）+ `steps`（编号列表）+ `cited_ids`（高亮 `[E#]`） |
| 证据表 | `evidence[]`：eid/subject/predicate/object/value+unit/source_titles/status/confidence |
| 依据角标 | `cited_ids` ∩ 证据 `eid`；未引用证据灰显 |
| 告警条 | `warnings[]`（`out_of_range` 黄、`unsourced_number:*` 黄、`no_evidence` 红） |
| 查询详情（折叠） | `query_cypher[]`、`elapsed_ms`、`llm_meta` |
| 大字模式 | 侧栏开关 → 注入 CSS 放大字号/对比度 |
| 图谱统计 | `store.stats()` |

UI **不得**自行调用 DeepSeek、不得改 `answer` 文本；只渲染 `AnswerResult`。

## 9. 写区与任务归属
| 写区 | 归属 | 内容 |
|---|---|---|
| `app/contracts.py`、`app/planner.py`、`app/planner_rules.py`、`app/qa.py`、`app/llm.py`、`app/config.py` | Lead | 契约、路由、管线、模型调用、配置 |
| `data/`、`graph/`、`scripts/gen_cypher.py`、`scripts/validate_data.py`、`scripts/load_neo4j.py` | kg-builder | schema、数据、Cypher 生成、校验 |
| `app/store/`、`app/linking.py`、`graph/queries/` | store-builder | 双后端、实体链接、查询模板 |
| `app/ui.py` | ui-builder | Streamlit 界面 |
| `tests/`、`scripts/eval_qa.py`、`scripts/env_check.py`、`data/utterances.csv` | qa-tester | 测试、评测、黄金集 |
| `README.md`、`.env.example`、`requirements.txt`、`run.ps1`、`.gitignore`、`docs/` | Lead | 文档与入口 |

## 10. 稳定性承诺（测试可依赖）
- `Evidence` 与 `AnswerResult` 的字段名本期不变。
- `mode` 恒为 `llm`/`template`；`warnings` 恒为 `list[str]`。
- `template` 模式**确定性**：同输入两次结果完全一致（`elapsed_ms` 除外）。
- `answer_question(..., allow_llm=False)` 不触网。
