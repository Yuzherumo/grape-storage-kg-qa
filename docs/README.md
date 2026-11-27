# 文档索引

本目录按用途分为四类：公开技术文档、竞赛/演示材料、运维与交付、自动生成的报告。README 只保留项目总览，详细内容放在这里。

## 公开技术文档

| 文档 | 内容 | 适合读者 |
|---|---|---|
| [architecture.md](architecture.md) | 系统架构、一次提问的完整路径、模块与代码对应、异常降级 | 开发、技术评审 |
| [data.md](data.md) | 数据文件、实体/关系/来源统计口径、证据分级、校验规则 | 数据、技术评审 |
| [validation.md](validation.md) | 测试命令、实际结果、未验证项、CI 状态、历史记录 | 技术评审、复现者 |
| [limitations.md](limitations.md) | 覆盖范围、数据与 LLM 限制、校验边界、部署限制 | 评审、使用者 |
| [api.md](api.md) | 数据结构、模块函数签名、稳定性承诺 | 二次开发 |
| [spec.md](spec.md) | 数据 schema 契约、实体清单、校验规则（含早期规划说明） | 数据维护 |
| [sources.md](sources.md) | 45 条来源清单、国标/综述/指南条文摘录、科普描述来源 | 溯源核对 |
| [technical_notes.md](technical_notes.md) | 一页技术摘要（数据口径、可信机制与验证结果） | 评审、答辩 |
| [agridata_grape_postharvest.md](agridata_grape_postharvest.md) | 国家农业科学数据中心外部抓取的方法、分级与结论 | 数据、合规 |
| [web_grape_storage.md](web_grape_storage.md) | 全网开放获取文献/数据采集的方法与许可说明 | 数据、合规 |
| [neo4j_verify.md](neo4j_verify.md) | Neo4j 未实跑的原因、Cypher 静态校验与 Kùzu 替代验证 | 图数据库评审 |
| [eval_results.md](eval_results.md) | 自动生成的问答评测报告 | 技术评审 |
| [eval_results.json](eval_results.json) | 评测报告的机器可读版本（同一脚本生成） | 复现、自动核对 |
| [env_check.md](env_check.md) | 自动生成的依赖与后端的本机自检 | 复现者 |
| [ai_usage.md](ai_usage.md) | AI 参与环节与人工把关、数据合规 | 评审 |

## 竞赛 / 演示材料

| 文档 | 内容 |
|---|---|
| [demo_script.md](demo_script.md) | 3 分钟录屏分镜与话术 |
| [submission.md](submission.md) | 200 字简介与一页要点 |
| [ans_fill_values.md](ans_fill_values.md) | 提交页逐项填写对照（内部使用） |
| `pitch_deck.pptx`（演示文稿；`assets/nongkesong_pitch_deck.pdf` 为展示用导出件） | 答辩/提交用（提交材料以赛事平台附件为准） |

## 运维与交付

| 文档 | 内容 |
|---|---|
| [deploy.md](deploy.md) | 公网部署（魔搭/Streamlit Cloud/隧道/云服务器）与线上核验 |
| [packaging.md](packaging.md) | 交付包白名单、排除项、打包与自检流程 |

## 自动生成

以下文件由脚本生成，修改数据或环境后应重新生成，不要手改：

| 文件 | 生成命令 |
|---|---|
| `eval_results.md` | `python scripts/eval_qa.py` |
| `eval_results.json` | `python scripts/eval_qa.py`（同一脚本同时生成） |
| `env_check.md` | `python scripts/env_check.py` |
| `docs/assets/graph_*.svg` | `python scripts/export_graph.py` |

## 相关图片

- `assets/ui_home.png`：运行中的界面截图（来自真实部署实例）；
- `assets/graph_overview.png` / `graph_shine_muscat.png`：由 `data/` 生成的知识图谱可视化（非界面截图）。
