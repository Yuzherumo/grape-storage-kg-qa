# 问答评测报告（docs/eval_results.md）

> 由 `scripts/eval_qa.py` 自动生成（离线模式：`allow_llm=False`，不联网、不需 API key）。
> 重新生成：`.\.venv\Scripts\python.exe scripts\eval_qa.py`

- 生成时间：2026-11-21 20:39:57
- 后端：`local`；图谱统计：`{'backend': 'local', 'nodes': 58, 'rels': 108, 'varieties': 8, 'conditions': 30, 'indicators': 13, 'diseases': 7, 'sources': 11, 'unresolved_edges': 0, 'data_files': ['triples_shine_muscat.csv', 'triples.csv']}`
- 总判定：**PASS** —— 核心题 5/5 通过；越界探针 1/1 通过；口语变体意图命中 12/12（门槛 10）；实体命中 12/12

## 表 1：典型问题与越界探针（Q1~Q6）

问题 | 意图 | 证据数 | 引用数 | 引用有效 | 数值校验 | 步骤数 | 结论
---|---|---|---|---|---|---|---
阳光玫瑰放冷库该调到多少度？ | temperature | 5 | 11 | 是 | 通过 | 3 | 通过
冷库里葡萄长白毛了怎么办？ | disease_control | 6 | 11 | 是 | 通过 | 3 | 通过
葡萄发软掉粒是咋回事？ | quality_indicator | 1 | 3 | 是 | 通过 | 1 | 通过
用 SO₂ 熏阳光玫瑰行不行？ | contraindication | 3 | 7 | 是 | 通过 | 2 | 通过
阳光玫瑰和巨峰哪个更能放？ | variety_compare | 13 | 11 | 是 | 通过 | 3 | 通过
-18℃ 冻起来能存一年吗？ | temperature | 6 | 7 | 是 | out_of_range（预期） | 1 | 通过

## 表 2：12 条农户口语变体（意图路由命中）

变体 | 期望意图 | 实际意图 | 命中
---|---|---|---
u01 这葡萄放库里得几度啊 | temperature | temperature (1.00) | ✅
u02 搁冷库能存到过年不 | shelf_life | shelf_life (0.75) | ✅
u03 白毛是不是没救了 | disease_control | disease_control (0.90) | ✅
u04 放两个月还行不行 | shelf_life | shelf_life (1.00) | ✅
u05 阳光玫瑰搁多少度合适啊 | temperature | temperature (0.85) | ✅
u06 香印青提库里头湿度得调到多少 | humidity | humidity (0.72) | ✅
u07 巨峰跟红提哪个耐放些 | variety_compare | variety_compare (0.66) | ✅
u08 打SO2对晴王是不是不好使啊 | contraindication | contraindication (0.37) | ✅
u09 灰霉病咋防啊搁冷库里 | disease_control | disease_control (0.72) | ✅
u10 葡萄掉粒软塌塌的还能要不 | quality_indicator | quality_indicator (1.00) | ✅
u11 气调库O2调到3个点中不中 | atmosphere | atmosphere (0.85) | ✅
u12 阳光玫瑰糖度多少才算好 | quality_indicator | quality_indicator (0.64) | ✅

## 失败明细

无。

## 判定口径

1. 证据：核心题必须有 ≥1 条图谱证据，答案只依据这些证据作答（离线模板同口径）。
2. 引用有效性：答案中每个 `[E#]` 都必须对应 `evidence` 里的 eid，且出现在 `cited_ids` 中；核心题引用数为 0 即失败。
3. 数值校验（±区间/单位）：答案中带单位的数字与证据同单位族（℃/%/月/h）区间比对，区间外报 `out_of_range`；
   证据里找不到来源的数字报 `unsourced_number`；模板答案由证据拼装，不应出现上述任一告警。
4. 意图与谓词：意图须等于本表 `expected_intent`，证据中须出现 `expected_predicate` 关系，必需关键词须命中。
5. 越界探针：问题请求证据外条件（如 -18℃）时必须触发 `out_of_range` 告警，且答案不得出现证据外温度或「可存一年」类编造结论。
- 口语变体：意图与 `data/utterances.csv` 标注一致；12 条中命中 ≥10 为通过。
- 该报告与 `pytest tests -q`（test_e2e_questions / test_planner / test_linking / test_numbers）同口径。
