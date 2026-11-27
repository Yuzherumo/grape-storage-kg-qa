# 交付打包说明（docs/packaging.md）

> 目标：把「什么该交、什么不该交、怎么交、评委怎么跑」一次说清，避免把密钥、第三方 PDF 或外部原始数据打包出去。

## 1. 交付物对照（比赛要求 → 本仓库位置）

| 比赛要求 | 交付形式 | 位置 |
|---|---|---|
| 在线 Demo | 本机可运行演示（无公网时按录屏/现场演示） | `.\run.ps1` → `http://127.0.0.1:8501` |
| 200 字简介 | Markdown 定稿（200 字以内） | `docs/submission.md` |
| 代码仓库 / ANS 作品快照 | 干净 zip 快照 + 可选 git bundle（开发历史） | `.\scripts\make_release.ps1 -Version v1.4.1` → `dist/` |
| 原创与 AI 使用说明 | Markdown | `docs/ai_usage.md` |
| 3 分钟录屏（建议） | 分镜脚本（视频待录） | `docs/demo_script.md` |
| 评测证据 | 自动生成报告 | `docs/eval_results.md` |
| 来源清单 | 45 条来源；69 条 verified（按 source_ids 计 53 条引用国标） | `docs/sources.md`、`docs/data.md` |

## 2. 打包原则：白名单收录、黑名单强校验

**收录（白名单）**：`app/ data/ graph/ scripts/ tools/ tests/ docs/ .github/ .streamlit/`、`README.md`、`LICENSE`、`requirements.txt`、`pyproject.toml`、`pytest.ini`、`.env.example`、`.gitignore`、`run.ps1`、`install.ps1`、`app.py`（云端入口）。

其中 `data/` 只带图谱数据（entities/triples/sources/descriptions/schema/黄金集等）与 `data/external` 的**元数据**（`paper_records.csv`、`manifest.json`、`README.md` 等）；外部原始转储不随包分发。

**排除（黑名单，打包后逐条强校验）**：
| 项 | 原因 |
|---|---|
| `.env` | 含真实 `DEEPSEEK_API_KEY`；只保留 `.env.example` |
| `.streamlit/secrets.toml` | 云端密钥文件；只保留 `.streamlit/secrets.toml.example` |
| `*.pdf` 及任何 `%PDF` 魔数内容 | 第三方标准/论文原件，版权原因不随包分发；只保留题录与条级摘录（按魔数扫描，防无扩展名 PDF 漏网） |
| `data/external/**/files/`、`papers/`、`details/`、`datasets_all_hits.csv`、`search_hit_pairs.csv`、`_direct_candidates.json`、`_grape_all.json` | 外部原始数据/论文，体积大（约 31 MB）、许可各异，只带元数据 |
| `.venv/ .tools/ .refs/ .tmp/` | 本机环境、下载物、缓存 |
| `.git/` | 如需开发历史，用 `-WithGitBundle` 另生成 `git bundle` |
| `__pycache__/ .pytest_cache/ dist/ *.log` | 缓存与产物 |

打包脚本会对生成后的 zip **再解包校验一次**：出现 `.env`、任何 PDF 内容、外部原始数据目录、`.venv`、`.refs`、`.git` 等文件即失败；同时断言**条目数 ≤ 200、体积 ≤ 3 MB**，防止再次误收 9 MB 级原始数据。

## 3. 一键打包

```powershell
# 校验 + 测试 + 打包（推荐，版本号用当前交付版本）
.\scripts\make_release.ps1 -Version v1.4.1

# 跳过测试（时间紧）
.\scripts\make_release.ps1 -Version v1.4.1 -SkipTests

# 额外保留开发历史（原创性证据）
.\scripts\make_release.ps1 -Version v1.4.1 -WithGitBundle
```

产物（`dist/`，已 gitignore）：
- `grape-storage-kg-qa-v1.4.1.zip` —— 干净快照
- `grape-storage-kg-qa-v1.4.1.zip.sha256` —— 校验和
- `MANIFEST-v1.4.1.md` —— 包含/排除清单、代码版本（commit + 是否有未提交改动）与评审运行步骤
- 可选 `grape-storage-kg-qa-v1.4.1.bundle` —— git 历史

> 包大小 / 文件数 / SHA256 以本次生成的 `MANIFEST-v1.4.1.md` 与同名 `.sha256` 为准，本文不预填数字。

## 4. 本机资料（不随包分发）

- 国标 PDF、5 篇综述原文、25 篇开放获取论文与外部数据集原件统一放在 **`.refs/`** 与 `data/external/**/{papers,files,details}/`（已 gitignore 或打包排除），仅用于本机核对引文；打包脚本不会收录。
- 若需要把原件给评委核对，单独用赛事平台附件/网盘提供，并注明版权归属。

## 5. 打包后自检清单

1. 解压到**全新目录**，运行 `.\install.ps1` → 应成功建 `.venv` 并装依赖；
2. `.\run.ps1 -Check` → 十项数据校验 + Cypher 静态校验 + 图谱加载（**108 节点 / 125 关系**）全过；
3. `.\run.ps1` → 8501 打开，示例问题可答（离线模式）；
4. `python -m pytest tests -q` → 全量通过数见 v1.4.1 复测记录（不要把历史值当当前值）；
5. 搜索包内不应出现 `sk-`、`.env`、`%PDF`、`data/external/**/files|papers`；`MANIFEST-v1.4.1.md` 应记录本次代码版本。

## 6. 验收记录

- **v1.4.1（当前交付版本）**：打包脚本已修正「`data/` 整体收录导致外部原始数据 + 4 篇无扩展名论文进入 9 MB 包」的问题。**包信息以 `dist/MANIFEST-v1.4.1.md` 与同名 `.sha256` 为准**——打包脚本会把实际大小/文件数/SHA256/代码版本（commit 及是否有未提交改动）写入清单，本文不重复硬编码，避免「文档写 SHA → 改文档 → SHA 变」的循环。
- 历史记录（仅供参考，不作为当前交付物）：v1.1 包 `dist/grape-storage-kg-qa-v1.1.zip`（约 937 KB / 94 文件，对应 2026-11-22 旧代码与数据）；其统计口径已过期。

## 7. 已知未完成项

- 公网 Demo **尚未更新到 v1.4**：魔搭空间最近上传仍为 2026-11-22 版本，需用有账号者上传新的运行包后按 [deploy.md](deploy.md) §E 复核（上传前不得声称线上已更新）；
- 3 分钟录屏与问答态截图（脚本已就绪，需人工录制）；
- ANS 平台快照需按平台要求上传（使用本章生成的 `dist/grape-storage-kg-qa-v1.4.1.zip` + 可选 git bundle 作为快照内容）。
