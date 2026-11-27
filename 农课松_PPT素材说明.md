# 农课松_PPT素材说明

## 一、交付文件

| 文件 | 用途 |
|---|---|
| `农课松_项目展示.pptx` | 正式答辩/项目展示用，12 页，16:9，可编辑 |
| `农课松_逐页讲解稿.md` | 与 12 页逐页对应的中文讲解词，标准版约 7 分钟 |
| `农课松_项目展示.pdf` | 用于快速预览/备份的 PDF 导出（如已生成） |
| 本文件 | 说明素材来源、数据依据、未使用素材和边界 |

**项目基线**：`3d0a2d6`（GitHub `main`）
**ModelScope 上传记录**：`7ac82cb`
**制作日期**：2026-11-22

---

## 二、真实项目数据（PPT 中所有统计口径）

### 1. 知识数据

| 项 | 值 | 来源 |
|---|---|---|
| 知识实体 | 63（品种 8 / 条件 35 / 指标 13 / 病害 7） | `data/entities.csv` |
| 知识三元组 | 125 | `data/triples.csv` |
| 知识来源 | 45（国标 1 / 综述 9 / 论文 31 / 行业资料 4） | `data/sources.csv` |
| 图谱节点 | 108（63 实体 + 45 来源节点） | `data/entities.csv + data/sources.csv` |
| verified / anchor | 69 / 56 | `data/triples.csv` 的 `status` 列 |
| 谓词类型 | 9 类 | `data/schema.json` |

PPT 中明确区分“63 个知识实体”和“108 个图谱节点”，没有把 125 条关系全部描述为已核验知识。

### 2. 测试与部署

| 项 | 值 | 来源 |
|---|---|---|
| pytest | 426 passed / 2 skipped | 当前仓库实测（2026-11-22） |
| Ruff | 通过 | `ruff check app.py app scripts tests` |
| 数据校验 | 十项通过，0 errors，2 warnings | `scripts/validate_data.py` |
| GitHub CI | test + windows-scripts 均通过 | run `44987585590`（head `3d0a2d6`） |
| 部署一致性 | ModelScope 仓库与本机运行文件 26/26 一致（统一 CRLF 后逐字节比对） | 2026-11-22 部署检查 |
| 空间健康 | `/_stcore/health` 200，首页 200，状态 Running | ModelScope 公开接口 |

说明：PPT 使用的最新实测为 **426 passed / 2 skipped**；README §11 已同步为本轮实测结果，历史 287 只保留在 `docs/validation.md` 的状态说明中，不作为当前结论。

### 3. 六个典型问题

| 问题 | 实际系统表现 | 依据 |
|---|---|---|
| 巨峰贮藏湿度要求？ | 明确拒答，未调用 LLM | 巨峰没有湿度边；证据为空 |
| 巨峰预冷要多久？ | 在线 LLM 回答 12h、0℃；E1/E2 引用有效 | `a_kyoho_precool`、`c_precool_decay` |
| 葡萄运输温度多少？ | 明确拒答，不拿普通冷藏温度代替 | 缺少运输温度数值 |
| 常温放几天会坏？ | 数值校验拦截无来源天数，回退模板 | 常温 AFFECTS 证据 + 校验器 |
| 1-MCP 怎么用？ | 引用匹配未通过，回退模板 | 1-MCP 证据 + 校验器 |
| 阳光玫瑰和巨峰哪个更耐放？ | 模板回退 + 保留 anchor 待核验提示 | E11/E13 为 anchor |

其中“在线 LLM 回答”来自**部署仓库代码 + 数据在本地调用在线 LLM**的复测；不是公网浏览器端六题全通过。

---

## 三、PPT 使用的真实图片/素材

### 1. 真实运行界面截图（初始界面）

- PPT 文件：第 8 页左侧
- 来源：`docs/assets/ui_home.png`
- 制作副本：`_ppt_assets/ui_home_real.png`
- 性质：项目真实 Streamlit 运行实例截图（ModelScope 实例），不是 AI 生成图片
- 说明：截图仅用于展示界面形态与信息层级；该截图不包含 API Key、环境变量或敏感路径。

**限制**：当前沙箱环境没有可用的浏览器自动化，无法重新抓取“输入问题后显示问答结果”的浏览器截图；因此第 8 页保留真实初始界面截图，实际问答内容用右侧 `AnswerResult` 字段卡呈现（明确标注为重绘，不是伪造 UI）。如需要完整问答态截图，需在可运行浏览器的环境中人工补拍后替换。

### 2. 知识图谱图像

- PPT 文件：第 4 页主图、第 8 页缩略图
- 文件：
  - `_ppt_assets/graph_overview_current.png`
  - `_ppt_assets/graph_shine_current.png`
- 生成脚本：`.tmp/make_ppt_assets.py`（使用 `app/graph_view.py` 的图布局与真实 `data/`）
- 性质：**由当前真实知识数据生成的图谱可视化**，不是界面截图，也不是虚构示意图
- 图中标题/副标题标注了当前规模：63 个知识实体、125 条关系、45 条来源；图例按实体类型着色，来源节点通过 `source_ids` 挂在关系属性上，不画在主图中。

### 3. 真实输出字段重绘

- PPT 文件：第 8 页右侧两张卡、第 6 页和第 9 页的答案/证据卡
- 来源：`AnswerResult`、`Evidence` 的实际字段，包括 `subject / predicate / object / status / source_ids / locator / cited_ids / warnings`
- 性质：**按真实字段重绘的展示卡，不是冒充的界面截图**
- PPT 第 8 页有明确标注：“界面截图为真实运行实例；右侧卡片按真实 AnswerResult 字段重绘，不是伪造的软件截图。”

### 4. 未使用的素材

- 旧 `docs/pitch_deck.pptx` 中的旧版页面没有作为新版素材复用；旧版统计（108 条等）已过期。
- 未使用包含 ModelScope 环境变量/API Key 的配置截图；避免泄露敏感信息。
- 未使用任何 AI 生成的“假软件界面”或虚构运行结果。
- 未使用图库/网络图片；封面葡萄图形是 PPT 内可编辑的几何形状。

---

## 四、数据与结论边界

PPT 中明确保留以下边界，答辩时也按此口径回答：

1. **没有宣称农业知识准确率、F1、召回率或用户满意度**；测试数字只说明工程与证据边界的验证结果。
2. **没有声称完全消除大模型幻觉**；引用/数值校验是规则启发式，不等同于语义蕴含（NLI）。
3. **没有把 125 条三元组都说成 verified**；69 verified / 56 anchor 已分开标注。
4. **没有把本地复测说成公网浏览器测试**；六题结果来自部署仓库代码与数据在本地调用在线 LLM。
5. **没有宣称真实生产效果、用户数量、合作单位或比赛成绩**。
6. **没有把 ModelScope 上传 commit 与 GitHub commit 混写**：GitHub 基线 `3d0a2d6`，ModelScope 上传记录 `7ac82cb`。

---

## 五、可复现依据

- 知识数据：`data/entities.csv`、`data/triples.csv`、`data/sources.csv`
- 核心代码：`app/linking.py`、`app/planner.py`、`app/qa.py`、`app/store/local_store.py`、`app/llm.py`
- 测试：`tests/`（含本轮 anchor/引用边界测试）
- 文档：`README.md`、`docs/architecture.md`、`docs/data.md`、`docs/validation.md`、`docs/limitations.md`
- 部署：GitHub `main` `3d0a2d6`；ModelScope 上传记录 `7ac82cb`
- 图片生成脚本：`.tmp/make_ppt_assets.py`
- PPT 生成脚本：`.tmp/make_ppt.py`
