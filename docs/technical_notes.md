# 技术摘要（technical notes）

> 本页是面向评审的一页技术摘要；详细内容分别见 [architecture.md](architecture.md)、[data.md](data.md)、[validation.md](validation.md)、[limitations.md](limitations.md)。

## 1. 作品定位

面向鲜食葡萄采后贮藏与保鲜管理的知识图谱增强问答系统。把 GB/T 16862-2026《鲜食葡萄冷藏技术》与相关综述拆成可溯源的知识图谱；提问时先做实体链接与意图路由，参数化检索证据，再由大语言模型在证据约束下生成「结论 + 依据 + 现在该做什么」，并对引用与数值做机器校验；图谱未覆盖的问题明确拒答。

## 2. 技术路线

```text
问题 → 归一化/实体链接 → 意图路由 → 参数化查图 → 证据（三元组+来源+定位+状态）
     → 覆盖守卫/越界检测 → 模板或 LLM 生成 → 引用与数值校验 → AnswerResult → UI
```

规则负责「问的是什么、该查什么」，图谱负责「有什么证据」，LLM 只负责把证据写成自然语言。完整模块与函数对应关系见 [architecture.md](architecture.md)。

技术栈：Python 3.12、Streamlit 1.67、纯标准库数据层；本地后端无需数据库，Neo4j 5 为可选后端；LLM 使用 OpenAI 兼容接口（默认 DeepSeek），未配置时自动使用离线模板。

## 3. 数据口径

- 知识实体 **58**（品种 8、条件 30、指标 13、病害 7）；来源节点 **19**；图谱节点 **77**（58 + 19）。
- 三元组 **115**：`verified` 69、`anchor` 46；9 种谓词。
- 科普描述 28 个节点；阳光玫瑰 S2a 快照 20 条。
- 数据唯一真相是 `data/*.csv`，Cypher 由脚本生成；统计口径、来源清单与核验规则见 [data.md](data.md)、[sources.md](sources.md)。

## 4. 可信机制

1. 覆盖守卫：typed 意图的证据必须触达命中的品种/病害主实体，否则 `no_evidence`；
2. 引用校验：`[E#]` 必须存在且与事实句相关，缺失/不匹配允许纠正一次，失败回退模板；
3. 数值校验：单位/区间感知，证据外数字记 `unsourced_number`，温度越界记 `out_of_range`；
4. 证据分级：`verified` 可作确定结论；`anchor` 必须标「待核验」，高风险参数只给方向；
5. 失败降级：无 Key/超时/401/429/5xx/图谱不可用等均有明确告警与模板兜底。

以上校验是规则启发式，不能替代语义级事实核查，边界见 [limitations.md](limitations.md)。

## 5. 验证结果（2026-11-22，当前工作区）

| 项 | 结果 |
|---|---|
| pytest | 289 收集，287 passed / 2 skipped；覆盖率 82% |
| 数据校验 | 十项通过，错误 0，告警 2（anchor quote 为空，符合规则） |
| Cypher | 静态校验通过、生成物无漂移；Kùzu 实跑 77 节点/115 关系，6 题与本地后端一致 |
| 黄金集 | 核心题 5/5、越界探针 1/1、口语意图 12/12、实体命中 12/12 |

详细命令、在线 LLM 历史记录与 CI 状态见 [validation.md](validation.md)。

## 6. 部署与复现

- 公网演示：<https://yuzherumo-grape-storage-kg-qa.ms.show>（魔搭创空间）；
- 本地：`.\install.ps1` → `.\run.ps1` → `http://127.0.0.1:8501`；无 Key/断网可用；
- 部署与打包细节见 [deploy.md](deploy.md)、[packaging.md](packaging.md)。

## 7. 限制与 AI 使用

- 限制摘要：演示级数据规模、46 条 anchor 待核验、Neo4j 服务端未实跑、校验为启发式、在线 LLM 有随机性；完整列表见 [limitations.md](limitations.md)。
- AI 参与编码、文档与多智能体协作，数值/来源由人工把关；详见 [ai_usage.md](ai_usage.md)。
