# 技术说明（technical notes）

> 作品：鲜食葡萄储藏知识图谱问答（农客松 2026，主赛道·方向二「生命系统」）
> 在线体验：https://yuzherumo-grape-storage-kg-qa.ms.show
> 代码仓库：https://github.com/Yuzherumo/grape-storage-kg-qa
> 版本：v1.0（2026-11-22）

## 1. 作品定位

面向种植户、冷库管理员、采购/质检的技术问答系统：把现行国标 **GB/T 16862-2026《鲜食葡萄冷藏技术》** 与 5 篇综述中的储藏规范，拆成可查询、可溯源的知识图谱；用户用大白话提问，系统先识别品种/病害/条件实体，再参数化查图取证据，最后让大模型**只能依据证据**生成「结论 + 依据 + 现在该做什么」，并对引用与数字做机器校验；图谱没收录就明确拒答。

## 2. 系统架构

```
用户问题
 → 归一化（全角/口语/₂→2）
 → 实体链接（app/linking.py，词典最长匹配 + 拉丁词边界 + 口语别名 + 症状词）
 → 意图路由（app/planner.py，触发词加权 + 实体先验 + 句式模式 + 低分澄清）
 → 参数化查图（app/store/，LocalStore 纯标准库 / Neo4jStore Cypher 模板）
 → 证据 Evidence（三元组 + 值 + 来源 + 定位 + 状态 + 置信）
 → 生成（app/qa.py：DeepSeek OpenAI 兼容接口，或离线模板）
 → 后校验（引用校验 + 数值单位/区间/越界 + 覆盖守卫）
 → AnswerResult → Streamlit UI
```

技术栈：Python 3.12 + Streamlit 1.67 + 纯标准库数据层 + Neo4j 5 Cypher 脚本（可选后端）+ DeepSeek API（可选，缺省离线模板）。不依赖数据库即可运行。

**图谱可视化**：`app/graph_view.py` 纯标准库力导向布局；`app/graph_interactive.py` 生成自包含 HTML（内联 SVG + 原生 JS，无外部依赖、离线可用）：**点击节点**显示具体描述（类型/属性/备注/数值区间）与按谓词分组的关联事实（含数值、等级/严重度、来源），可点邻居跳转，支持缩放、拖拽、类型筛选与搜索。UI 侧栏「知识图谱视图」切换全图/阳光玫瑰子图；`scripts/export_graph.py` 导出 `docs/assets/*.svg`，PNG 版本随仓库提供，用于 PPT 与培训材料。

## 3. 知识图谱设计

| 项 | 内容 |
|---|---|
| 实体（5 类，59 实体 + 16 来源 = 74 节点） | Variety 8、Condition 30、QualityIndicator 13、Disease 7、Source 16 |
| 关系（9 种谓词，108 条） | REQUIRES 26、CONTRA_INDICATED_FOR 3、AFFECTS 19、SUSCEPTIBLE_TO 8、PREVENTED_BY 22、INDUCED_BY 7、ALTERNATIVE_TO 3、INDICATES 2、HAS_INDICATOR_VALUE 18 |
| 单源真相 | `data/entities.csv / triples.csv / sources.csv`，Cypher 由脚本生成（`scripts/gen_cypher.py`，`--check` 防漂移）；阳光玫瑰核心子集另有 `triples_shine_muscat.csv` 门禁快照 |
| 受控词表 | 谓词主/宾类型、数值单位与区间、来源外键；`scripts/validate_data.py` 十项校验（列完整、枚举、区间、类型-谓词组合、来源外键、B/G/H 双来源、S2a 快照严格子集等） |

## 4. 证据分级与溯源

每条三元组带 `source_ids + locator + quote + status + confidence`：

- **verified 61 条**：GB/T 16862-2026 条文 51 条（`7.3 冷藏条件`、`5.3.2 预冷`、`6.3.4 保鲜剂`、`附录A 表A.1`、`附录B 表B.1` 等条款号 + 原文摘录）+ 用户提供的 5 篇综述原文 10 条（PDF 页码/栏目 + 引文）；
- **anchor 47 条**：论文正文未获取，`note` 写明待核验点，UI 显示「待核验」，不冒充原文；
- 冲突不合成：SO₂ 对阳光玫瑰保留 CONTRA（禁忌，高）+ ALTERNATIVE（缓释片/1-MCP）两侧证据，答案并列陈述并注明争议。

## 5. 可信问答机制

1. **覆盖守卫**：typed intent 的证据必须触达命中实体，否则返回 `no_evidence`，不拿别的品种凑答案；
2. **引用校验**：答案里的 `[E#]` 必须存在于本轮证据；越界引用记 `invalid_citation`；
3. **数字校验**：单位/±区间感知，答案中数字必须来自证据（含多值区间、结构化值）；不在证据内的数字记 `unsourced_number`；问题数值超出证据温度区间时记 `out_of_range` 并明确「不可行」；
4. **模板兜底**：LLM 超时/不可用/未配置 key 时自动降级为模板答案，功能完整、仍带引用；
5. **多轮上下文**：仅当本轮没有新实体时继承上一轮实体，避免误覆盖。

## 6. 评测与验证

| 项 | 结果 |
|---|---|
| 离线测试 | **118 passed / 2 skipped**（2 skip：未装 neo4j 驱动的 parity 测试、默认跳过的 LLM 标记测试） |
| 黄金集 | 核心题 5/5、越界探针 1/1、口语变体意图 12/12、实体命中 12/12 |
| 数据校验 | 十项全绿（错误 0） |
| Cypher | 13 个 `.cypher` 静态校验通过（标签/关系/参数/计数/10 意图覆盖）+ 生成物无漂移；在嵌入式 openCypher 引擎 Kùzu 上实跑（74 节点/108 关系，6 题与本地后端一致） |
| 在线模式 | `deepseek-chat` 实测 6 题均有有效引用、无编造数字；Q6 正确触发越界；单题 1.3~2.8s，缓存命中 ~5ms |

## 7. 部署与复现

- **公网 Demo**：魔搭 ModelScope 创空间（Streamlit SDK，免费 CPU，Running；`_stcore/health`=ok）；
- **本地**：`.\install.ps1` → `.\run.ps1`（`http://127.0.0.1:8501`），无网络/无 Key 可跑；
- **打包**：`.\scripts\make_release.ps1` 生成不含密钥与 PDF 的干净快照（白名单 + 解包强校验 + SHA256）；
- **自检**：`.\run.ps1 -Check`（数据十项 + Cypher 静态校验 + 图谱加载）。

## 8. 已知限制

1. 图谱为演示级规模（108 条），覆盖阳光玫瑰 + 7 个对照品种、7 种病害（5 种与国标附录B 对齐），不是全领域知识库；
2. 47 条 anchor 依赖未获取的论文原文（主要在 2024 综述、包装工程综述、阳光玫瑰 SO₂/ClO₂ 论文等），已如实标注不冒充；
3. Neo4j 服务端未在本网络实跑（官方下载域名 403），以嵌入式引擎实跑 + 静态校验 + 便携安装脚本替代，详见 `docs/neo4j_verify.md`；
4. 云端免费实例会休眠，首次访问冷启动数十秒；在线模式依赖 DeepSeek API 可用性，离线模板为保底。

## 9. AI 使用说明

见 `docs/ai_usage.md`：AI 用于辅助编码、文档整理与多智能体协作开发；数值/来源/结论由人工核验口径把控，未编造来源、DOI 或条文；引用的标准与论文仅保留题录与条级摘录，PDF 原件不随作品分发。
