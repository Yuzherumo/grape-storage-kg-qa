# 问答评测报告（docs/eval_results.md）

> 由 `scripts/eval_qa.py` 自动生成（离线模式：`allow_llm=False`，不联网、不需 API key）。
> 重新生成：`.\.venv\Scripts\python.exe scripts\eval_qa.py`

- 生成时间：2026-11-21 19:09:31
- 后端：`local`；图谱统计：`{'backend': 'local', 'nodes': 48, 'rels': 71, 'varieties': 8, 'conditions': 21, 'indicators': 13, 'diseases': 6, 'sources': 11, 'unresolved_edges': 0, 'data_files': ['triples_shine_muscat.csv', 'triples.csv']}`
- 总判定：**FAIL** —— 核心题 0/5 通过；越界探针 0/1 通过；口语变体意图命中 12/12（门槛 10）；实体命中 12/12

## 表 1：典型问题与越界探针（Q1~Q6）

问题 | 意图 | 证据数 | 引用数 | 引用有效 | 数值校验 | 步骤数 | 结论
---|---|---|---|---|---|---|---
阳光玫瑰放冷库该调到多少度？ | temperature | 1 | 3 | 是 | unsourced_number:0.78 | 1 | 失败：数值告警: unsourced_number:0.78
冷库里葡萄长白毛了怎么办？ | disease_control | 6 | 11 | 是 | unsourced_number:0.80,unsourced_number:0.76,unsourced_number:-0.5,unsourced_number:0.74,unsourced_number:0.72,unsourced_number:0.70 | 3 | 失败：数值告警: unsourced_number:0.80,unsourced_number:0.76,unsourced_number:-0.5,unsourced_number:0.74,unsourced_number:0.72,unsourced_number:0.70
葡萄发软掉粒是咋回事？ | quality_indicator | 1 | 3 | 是 | unsourced_number:0.72 | 1 | 失败：数值告警: unsourced_number:0.72
用 SO₂ 熏阳光玫瑰行不行？ | contraindication | 3 | 6 | 是 | unsourced_number:0.72,unsourced_number:0.64,unsourced_number:0.68 | 1 | 失败：数值告警: unsourced_number:0.72,unsourced_number:0.64,unsourced_number:0.68
阳光玫瑰和巨峰哪个更能放？ | variety_compare | 6 | 10 | 是 | unsourced_number:0.78,unsourced_number:0.72,unsourced_number:0.68,unsourced_number:0.66,unsourced_number:0.64 | 3 | 失败：数值告警: unsourced_number:0.78,unsourced_number:0.72,unsourced_number:0.68,unsourced_number:0.66,unsourced_number:0.64
-18℃ 冻起来能存一年吗？ | temperature | 6 | 9 | 否 | unsourced_number:0.78,unsourced_number:0.68,unsourced_number:0.64,unsourced_number:0.62 | 3 | 失败：数值告警: unsourced_number:0.78,unsourced_number:0.68,unsourced_number:0.64,unsourced_number:0.62

## 表 2：12 条农户口语变体（意图路由命中）

变体 | 期望意图 | 实际意图 | 命中
---|---|---|---
u01 这葡萄放库里得几度啊 | temperature | temperature (1.00) | ✅
u02 搁冷库能存到过年不 | shelf_life | shelf_life (0.75) | ✅
u03 白毛是不是没救了 | disease_control | disease_control (0.90) | ✅
u04 放两个月还行不行 | shelf_life | shelf_life (1.00) | ✅
u05 阳光玫瑰搁多少度合适啊 | temperature | temperature (0.85) | ✅
u06 香印青提库里头湿度得调到多少 | humidity | humidity (0.72) | ✅
u07 巨峰跟红提哪个耐放些 | variety_compare | variety_compare (0.67) | ✅
u08 打SO2对晴王是不是不好使啊 | contraindication | contraindication (0.37) | ✅
u09 灰霉病咋防啊搁冷库里 | disease_control | disease_control (0.72) | ✅
u10 葡萄掉粒软塌塌的还能要不 | quality_indicator | quality_indicator (1.00) | ✅
u11 气调库O2调到3个点中不中 | atmosphere | atmosphere (0.85) | ✅
u12 阳光玫瑰糖度多少才算好 | quality_indicator | quality_indicator (0.64) | ✅

## 失败明细

- Q1 阳光玫瑰放冷库该调到多少度？ → 失败：数值告警: unsourced_number:0.78
- Q2 冷库里葡萄长白毛了怎么办？ → 失败：数值告警: unsourced_number:0.80,unsourced_number:0.76,unsourced_number:-0.5,unsourced_number:0.74,unsourced_number:0.72,unsourced_number:0.70
- Q3 葡萄发软掉粒是咋回事？ → 失败：数值告警: unsourced_number:0.72
- Q4 用 SO₂ 熏阳光玫瑰行不行？ → 失败：数值告警: unsourced_number:0.72,unsourced_number:0.64,unsourced_number:0.68
- Q5 阳光玫瑰和巨峰哪个更能放？ → 失败：数值告警: unsourced_number:0.78,unsourced_number:0.72,unsourced_number:0.68,unsourced_number:0.66,unsourced_number:0.64
- Q6 -18℃ 冻起来能存一年吗？ → 失败：数值告警: unsourced_number:0.78,unsourced_number:0.68,unsourced_number:0.64,unsourced_number:0.62

## 判定口径

- 核心题（Q1~Q5）：证据 ≥1、答案带有效 `[E#]` 且落在 `cited_ids`、意图正确、期望谓词存在、必需关键词命中、无 `out_of_range`/`unsourced_number` 数值告警。
- 越界探针（Q6）：答案不得出现证据外温度，不得宣称证据外的存放条件。
- 口语变体：意图与 `data/utterances.csv` 标注一致；12 条中命中 ≥10 为通过。
- 该报告与 `pytest tests/test_e2e_questions.py tests/test_planner.py tests/test_linking.py` 口径一致。
