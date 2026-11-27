# 问答评测报告（docs/eval_results.md）

> 由 `scripts/eval_qa.py` 自动生成（离线模式：`allow_llm=False`，不联网、不需 API key）。
> 重新生成：`.\\.venv\\Scripts\\python.exe scripts\\eval_qa.py`

- 生成时间：2026-11-27 21:12:52
- 后端：`local`；图谱统计：`{'backend': 'local', 'nodes': 63, 'rels': 125, 'varieties': 8, 'conditions': 35, 'indicators': 13, 'diseases': 7, 'sources': 45, 'unresolved_edges': 0, 'data_files': ['triples_shine_muscat.csv', 'triples.csv']}`
- 总判定：**PASS** —— 题目 28/28 通过；答对 19 题 / 拒答 9 题

## 1. 汇总指标

指标 | 数值 | 说明
---|---|---
意图准确率 | 100.00% | expected_status=answer 的题，意图须与期望一致
主实体覆盖 | 100.00% | 17 道题链到实体，且实体出现在答案/证据中
引用有效率 | 100.00% | 答案中每个 [E#] 都属于证据且进入 cited_ids
数值一致率 | 100.00% | 无 out_of_range / unsourced_number（越界探针要求 out_of_range）
拒答准确率 | 100.00% | refuse 题须 no_evidence、无证据、无引用
关键词通过率 | 100.00% | must_keywords 命中且 forbidden_keywords 不出现（19 题适用）
谓词覆盖率 | 100.00% | 证据中须出现该意图的期望谓词
口语变体意图命中 | 12/12（100.00%，门槛 10） | 实体命中 100.00%
题目通过/失败 | 28/0 | 失败：无

意图覆盖（题数）：

意图 | temperature | humidity | atmosphere | shelf_life | disease_control | disease_risk | quality_indicator | variety_compare | contraindication | general
---|---|---|---|---|---|---|---|---|---|---|
题数 | 3 | 1 | 1 | 2 | 3 | 2 | 2 | 2 | 2 | 10

## 2. 逐题结果

题目 | 类型 | 状态 | 意图（期望/实际） | 证据 | 引用 | 引用有效 | 数值 | 关键词 | 主实体 | 结论
---|---|---|---|---|---|---|---|---|---|---
Q1 阳光玫瑰放冷库该调到多少度？ | core | answer | temperature / temperature | 5 | 5 | 是 | 通过 | 是 | 是 | 通过
Q2 冷库里葡萄长白毛了怎么办？ | core | answer | disease_control / disease_control | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q3 葡萄发软掉粒是咋回事？ | core | answer | quality_indicator / quality_indicator | 4 | 4 | 是 | 通过 | 是 | 是 | 通过
Q4 用 SO₂ 熏阳光玫瑰行不行？ | core | answer | contraindication / contraindication | 2 | 2 | 是 | 通过 | 是 | 是 | 通过
Q5 阳光玫瑰和巨峰哪个更能放？ | core | answer | variety_compare / variety_compare | 13 | 9 | 是 | 通过 | 是 | 是 | 通过
Q6 -18℃ 冻起来能存一年吗？ | probe | answer | temperature / temperature | 6 | 5 | 是 | out_of_range（预期） | 是 | — | 通过
Q7 冷库湿度多少合适？ | core | answer | humidity / humidity | 4 | 4 | 是 | 通过 | 是 | — | 通过
Q8 气调贮藏氧气浓度多少？ | core | answer | atmosphere / atmosphere | 2 | 2 | 是 | 通过 | 是 | 是 | 通过
Q9 阳光玫瑰能放多久？ | core | answer | shelf_life / shelf_life | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q10 巨峰能贮藏几个月？ | core | answer | shelf_life / shelf_life | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q11 葡萄青霉病怎么防治？ | core | answer | disease_control / disease_control | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q12 灰霉病是怎么引起的？ | core | answer | disease_risk / disease_risk | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q13 葡萄为什么会长白毛？ | core | answer | disease_risk / disease_risk | 6 | 5 | 是 | 通过 | 是 | 是 | 通过
Q14 哪些条件会让葡萄掉粒？ | core | answer | quality_indicator / quality_indicator | 3 | 3 | 是 | 通过 | 是 | 是 | 通过
Q15 巨峰和红地球哪个耐贮？ | core | answer | variety_compare / variety_compare | 9 | 8 | 是 | 通过 | 是 | 是 | 通过
Q16 玫瑰香能用SO2熏吗？ | core | answer | contraindication / contraindication | 2 | 2 | 是 | 通过 | 是 | 是 | 通过
Q17 葡萄怎么预冷？ | core | answer | general / general | 4 | 4 | 是 | 通过 | 是 | 是 | 通过
Q18 冷藏温度波动多少合适？ | core | answer | general / general | 1 | 1 | 是 | 通过 | 是 | 是 | 通过
Q19 苹果冷藏温度多少合适？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q20 梨冷藏温度多少？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q21 香蕉能放多久？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q22 龙眼怎么贮藏？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q23 葡萄农残限量是多少？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q24 葡萄运输温度多少？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q25 葡萄霜霉病怎么防治？ | refuse | refuse | disease_control / disease_control | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q26 葡萄什么时候采收？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q27 妮娜皇后冷藏温度多少？ | refuse | refuse | general / general | 0 | 0 | 是 | 通过 | 是 | — | 通过
Q28 阳光玫瑰放冷库几度 | core | answer | temperature / temperature | 5 | 5 | 是 | 通过 | 是 | 是 | 通过

## 3. 拒答题明细（expected_status=refuse）

题目 | 期望意图 | 实际意图 | 证据数 | 引用数 | 结论
---|---|---|---|---|---
Q19 苹果冷藏温度多少合适？ | general | general | 0 | 0 | 通过
Q20 梨冷藏温度多少？ | general | general | 0 | 0 | 通过
Q21 香蕉能放多久？ | general | general | 0 | 0 | 通过
Q22 龙眼怎么贮藏？ | general | general | 0 | 0 | 通过
Q23 葡萄农残限量是多少？ | general | general | 0 | 0 | 通过
Q24 葡萄运输温度多少？ | general | general | 0 | 0 | 通过
Q25 葡萄霜霉病怎么防治？ | disease_control | disease_control | 0 | 0 | 通过
Q26 葡萄什么时候采收？ | general | general | 0 | 0 | 通过
Q27 妮娜皇后冷藏温度多少？ | general | general | 0 | 0 | 通过

## 4. 12 条农户口语变体（意图路由命中）

变体 | 期望意图 | 实际意图 | 命中
---|---|---|---
u01 这葡萄放库里得几度啊 | temperature | temperature (1.00) | ✅
u02 搁冷库能存到过年不 | shelf_life | shelf_life (0.83) | ✅
u03 白毛是不是没救了 | disease_control | disease_control (0.90) | ✅
u04 放两个月还行不行 | shelf_life | shelf_life (1.00) | ✅
u05 阳光玫瑰搁多少度合适啊 | temperature | temperature (0.85) | ✅
u06 香印青提库里头湿度得调到多少 | humidity | humidity (0.72) | ✅
u07 巨峰跟红提哪个耐放些 | variety_compare | variety_compare (0.66) | ✅
u08 打SO2对晴王是不是不好使啊 | contraindication | contraindication (0.40) | ✅
u09 灰霉病咋防啊搁冷库里 | disease_control | disease_control (0.75) | ✅
u10 葡萄掉粒软塌塌的还能要不 | quality_indicator | quality_indicator (1.00) | ✅
u11 气调库O2调到3个点中不中 | atmosphere | atmosphere (0.89) | ✅
u12 阳光玫瑰糖度多少才算好 | quality_indicator | quality_indicator (0.64) | ✅

## 5. 已知缺陷（记录，不在 Phase 4 写区修复）

- 包装×禁忌组合在 local 后端 0 证据：如「包装前SO2熏蒸有什么禁忌」走 contraindication，但禁忌检索按 condition_ids 过滤（SO2 熏蒸与包装容重无交集），属数据/模板缺口而非路由缺陷
- 无上下文追问仍走 temperature 全库例外：「那多少度」在无上文时返回全库温度证据（有上下文时已正确继承，见多轮测试）
- Neo4j 服务端仍未实跑：双后端一致性用例默认 skip（缺 neo4j 驱动/运行中服务），本地后端与 CSV 一致
- LLM 语义级忠实度仍靠规则启发式校验（引用/数值/关键词/字面相关），不是 NLI 语义蕴含判定

## 6. 判定口径

1. 答对题（expected_status=answer）：证据 ≥1、答案含有效 `[E#]` 且引用落在 evidence/cited_ids 内、意图与期望一致、证据含期望谓词、关键词命中、数值无告警（越界探针必须有 out_of_range）。
2. 拒答题（expected_status=refuse）：必须 `no_evidence`、证据为空、答案无 `[E#]` 引用；不得为了「看起来完整」而返回别的品种/条件。
3. 期望值来源：`data/triples.csv` 的关系与数值 + 行为目标（离域/未收录必须拒答），不为让脚本变绿而放宽。
4. 口语变体：意图与 `data/utterances.csv` 标注一致，12 条中命中 ≥10 为通过。
5. 硬性失败 = 任一题不通过或口语变体命中 < 门槛；此时退出码为 1。
