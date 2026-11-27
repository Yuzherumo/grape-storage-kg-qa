# 技术摘要（technical notes）

> 本页是面向评审的一页技术摘要；详细内容分别见 [architecture.md](architecture.md)、[data.md](data.md)、[validation.md](validation.md)、[limitations.md](limitations.md)。

## 1. 作品定位

面向鲜食葡萄采后贮藏与保鲜管理的知识图谱增强问答系统。把 GB/T 16862-2026《鲜食葡萄冷藏技术》与相关综述拆成可溯源的知识图谱；提问时先做实体链接与意图路由，参数化检索证据，再由大语言模型在证据约束下生成「结论 + 依据 + 现在该做什么」，并对引用与数值做机器校验；图谱未覆盖的问题明确拒答。

## 2. 技术路线

```text
问题 → 归一化/实体链接 → 意图路由 → 参数化查图 → 证据（三元组+来源+定位+状态）
     → 覆盖守卫/越界检测 → 模板或 LLM 生成 → 引用与数值校验 → AnswerResult → UI
```

规则负责「问的是什么、该查什么」，图谱负责「有什么证据」，LLM 负责把证据写成自然语言；生成内容必须通过引用与数值校验，校验失败回退模板或拒答。完整模块与函数对应关系见 [architecture.md](architecture.md)。

技术栈：Python 3.12、Streamlit 1.67、纯标准库数据层；本地后端无需数据库，Neo4j 5 为可选后端；LLM 使用 OpenAI 兼容接口（默认 DeepSeek），未配置时自动使用离线模板。

## 3. 数据口径

- 知识实体 **63**（品种 8、条件 35、指标 13、病害 7）；来源节点 **45**；图谱节点 **108**（63 + 45）。
- 三元组 **125**：`verified` 69、`anchor` 56；9 种谓词。
- 科普描述 28 个节点；阳光玫瑰 S2a 快照 20 条。
- 数据唯一真相是 `data/*.csv`，Cypher 由脚本生成；统计口径、来源清单与核验规则见 [data.md](data.md)、[sources.md](sources.md)。

## 4. 可信机制

1. 覆盖守卫：typed 意图的证据必须触达命中的品种/病害主实体，否则 `no_evidence`；
2. 引用校验：`[E#]` 必须存在且与事实句相关，缺失/不匹配允许纠正一次，失败回退模板；
3. 数值校验：单位/区间感知，证据外数字记 `unsourced_number`，温度越界记 `out_of_range`；
4. 证据分级：`verified` 可作确定结论；`anchor` 必须标「待核验」，高风险参数只给方向；
5. 失败降级：无 Key/超时/401/429/5xx/图谱不可用等均有明确告警与模板兜底。

- 安全护栏：明显提示注入（忽略证据/系统指令/编造数据）直接拒答；药剂、熏蒸、剂量等高风险主题附加 `high_risk_topic` 告警；`AnswerResult` 支持 `to_json()` 结构化输出。

以上校验是规则启发式，不能替代语义级事实核查，边界见 [limitations.md](limitations.md)。

## 5. 验证结果（2026-11-27，v1.4.1 交付修复后本地复测）

| 项 | 结果 |
|---|---|
| pytest | **426 passed / 2 skipped**（2 skipped：Neo4j 驱动、默认跳过的 LLM 联网用例） |
| 覆盖率 | **83%**（`--cov=app`；`app/ui.py` 不计入，`neo4j_store.py` 0%） |
| 数据校验 | 十项通过，错误 0，告警 2（46 条 anchor quote 为空，符合规则）；总数据行 233 |
| Cypher | 静态校验与生成漂移通过；Kùzu 实跑 108 节点/125 关系，6 题与本地后端一致 |
| 黄金集 | **28/28 通过**（answer 19 + refuse 9）：意图、主实体覆盖、引用有效、数值一致均 100%，拒答准确率 9/9，口语变体 12/12，Q6 命中 `out_of_range` |
| Lint / 文档 | ruff All checks passed；`check_docs_consistency.py` 0 漂移 |
| CI | **本地全绿；推送后由 GitHub Actions 复核**（最近一次历史 run `44987585590` 为 `3d0a2d6` 基线） |

| 部署 | 公网 Demo 仍为 2026-11-22 旧版，v1.4 尚未上传（以 [deploy.md](deploy.md) 为准） |

详细命令、在线 LLM 历史记录与 CI 状态见 [validation.md](validation.md)。

## 6. 部署与复现

- 当前基线：v1.4 数据 + v1.4.1 交付修复的本地交付版本（提交后回填 commit）；
- 公网演示：<https://yuzherumo-grape-storage-kg-qa.ms.show>（魔搭创空间，**仍是旧版，待上传**；上传记录 `7ac82cb` 为 2026-11-22）；
- 本地：`.\install.ps1` → `.\run.ps1` → `http://127.0.0.1:8501`；无 Key/断网可用；
- 部署与打包细节见 [deploy.md](deploy.md)、[packaging.md](packaging.md)。

## 7. 限制与 AI 使用

- 限制摘要：演示级数据规模、56 条 anchor 待核验、Neo4j 服务端未实跑、校验为启发式、在线 LLM 有随机性；完整列表见 [limitations.md](limitations.md)。
- AI 参与编码、文档与多智能体协作，数值/来源由人工把关；详见 [ai_usage.md](ai_usage.md)。
